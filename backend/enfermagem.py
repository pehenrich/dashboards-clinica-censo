# -*- coding: utf-8 -*-
"""
Módulo Enfermagem — fila de triagem das senhas do totem do Ocupacional. A
enfermagem usa essa tela pra ver quem tirou senha, chamar, identificar o
paciente (busca manual) e registrar sinais vitais no prontuário, SEM tirar a
senha da fila em que ela está.

Ponto crítico de design — o ciclo de vida da senha em `fle` (confirmado em
produção em 22/09/2026 testando uma senha real, OEP063):
1. Totem imprime a senha → linha em `fle` com FLE_STR_COD='RPS',
   FLE_STATUS='A', FLE_PSV_COD=<código da categoria, ex: 19="Outras
   Empresas">, FLE_PAC_REG=0 e FLE_OSM_SERIE/NUM nulos — ou seja, SEM
   paciente nem OS vinculados ainda. É esse o estágio "antes da recepção"
   que a enfermagem quer enxergar.
2. Só depois, quando a recepção identifica o paciente e linka a OS
   (pré-agendada), aparece OUTRA linha com FLE_STR_COD='ROC', FLE_PSV_COD já
   sendo o profissional real (ex: "Maria Nilva"), paciente e OS preenchidos.
Por isso `listar_fila` lê direto de `fle` com FLE_STR_COD='RPS', sem
join nenhum com osm/pac — não tem paciente pra juntar ainda. A enfermagem
precisa PESQUISAR o paciente manualmente (front-end usa
/api/atendimento/buscar-paciente) antes de lançar a triagem.

Por que "chamar" aqui é diferente da Coleta: `fle.FLE_STATUS` é a MESMA
coluna que a fila do médico (endpoint /api/atendimento/fila em main.py) usa
pra saber quem está esperando — filtrando estritamente FLE_STATUS='A'. Se a
triagem marcasse FLE_STATUS='X' (como a Coleta faz em /api/coleta/chamar), a
senha sumiria antes da recepção processar. Por isso `chamar()` aqui só grava
FLE_DTHR_ATENDIMENTO/FLE_USR_ATENDIMENTO, sem tocar em FLE_STATUS. Como
ainda não existe paciente/OS pra identificar a linha, a chave usada pra
`chamar()` é a chave real de `fle` nesse estágio: FLE_DTHR_CHEGADA (exata,
com milissegundos) + FLE_PSV_COD + FLE_STR_COD='RPS' — nunca só o número da
senha (reinicia todo dia, repete com anos de histórico — ver regra de
DELETE/UPDATE manual no CLAUDE.md, mesmo princípio se aplica aqui).

Não existe conceito de "já triado" nesse estágio — como o paciente ainda não
foi identificado, não dá pra checar RCL. "Chamado" (mostrar_chamados) usa só
FLE_DTHR_ATENDIMENTO.

Senha gerada pelo totem sai com um de 5 prefixos em FLE_BIP, um por
categoria de convênio/pagador (confirmado com a enfermagem em 22/09/2026:
"os prestadores são os seguintes utilizados para gerar senha no totem:
1099,18,17,23,19") — ver FILAS_TOTEM_OCUP.

Sinais vitais gravam na tabela RCL (prontuário real do Smart), com
RCL_COD='NOTASENF' — serviço "NOTAS DE ENFERMAGEM" já cadastrado e usado de
verdade em produção (~57 mil registros na investigação de 22/09/2026, texto
livre, SEM o formato estruturado "@#modelo@campo" que os templates de
Atendimento usam — não seguimos esse padrão aqui porque NOTASENF de fato não
usa ele, confirmado com exemplos reais). Igual ao resto do Dashboard que
escreve em RCL, grava SOMENTE em smart_hml até validação/aprovação — nunca
direto em produção.
"""
from datetime import datetime

import pyodbc

_CONN_STR_PROD = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=tcp:192.168.1.9,1433;"
    "DATABASE=SMART;"
    "UID=smart;"
    "PWD=smart@pixeon16;"
    "TrustServerCertificate=yes;"
    "Encrypt=no;"
)
_CONN_STR_HML = _CONN_STR_PROD.replace("DATABASE=SMART;", "DATABASE=smart_hml;")


def _get_conn():
    return pyodbc.connect(_CONN_STR_PROD)


def _get_conn_hml():
    return pyodbc.connect(_CONN_STR_HML)


def _query(sql, params=()):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


RCL_COD_TRIAGEM = "NOTASENF"

# Senha gerada pelo totem do Ocupacional sai com um de 5 prefixos em FLE_BIP,
# um por categoria de convênio/pagador — são essas 5 categorias que a
# enfermagem entende como "fila" (confirmado com a enfermagem em 22/09/2026:
# "os prestadores são os seguintes utilizados para gerar senha no totem:
# 1099,18,17,23,19"), cruzado com o cadastro FLE_CFG_SENHA + nome em PSV pra
# achar o prefixo de cada uma. Esse "PSV_COD" é só a chave da categoria/
# contador de senha em FLE_CFG_SENHA — NÃO é o profissional real que atende
# (esse continua em fle.FLE_PSV_COD, ex: "Maria Nilva", "Médico Censo",
# populado à parte e irrelevante pra esse filtro). Lista fixa porque são
# categorias de convênio estáveis, ao contrário de prestador/posto.
FILAS_TOTEM_OCUP = [
    {"codigo": 19,   "prefixo": "OEP", "nome": "Outras Empresas"},
    {"codigo": 1099, "prefixo": "QVI", "nome": "Qualidade de Vida"},
    {"codigo": 18,   "prefixo": "PAR", "nome": "Particular"},
    {"codigo": 23,   "prefixo": "POC", "nome": "Prior Ocupacional"},
    {"codigo": 17,   "prefixo": "VAL", "nome": "Vale"},
]
_PREFIXO_POR_CODIGO = {f["codigo"]: f["prefixo"] for f in FILAS_TOTEM_OCUP}


def listar_filas_disponiveis(dias: int = 30):
    """
    As 5 filas/categorias do totem do Ocupacional, com contagem de senhas
    recebidas nos últimos `dias` dias em cada uma (só informativo, pra
    enfermagem ver volume) — ordenado por volume.
    """
    contagem = {f["codigo"]: 0 for f in FILAS_TOTEM_OCUP}
    condicoes = " OR ".join(
        f"RTRIM(fle.FLE_BIP) LIKE '{f['prefixo']}%'" for f in FILAS_TOTEM_OCUP
    )
    rows = _query(f"""
        SELECT LEFT(RTRIM(fle.FLE_BIP), 3) AS prefixo, COUNT(*) AS qtd
        FROM fle
        WHERE fle.FLE_DTHR_CHEGADA >= DATEADD(day, -?, GETDATE())
          AND RTRIM(fle.FLE_STR_COD) = 'ROC'
          AND ({condicoes})
        GROUP BY LEFT(RTRIM(fle.FLE_BIP), 3)
    """, (dias,))
    qtd_por_prefixo = {r["prefixo"]: r["qtd"] for r in rows}
    for f in FILAS_TOTEM_OCUP:
        contagem[f["codigo"]] = qtd_por_prefixo.get(f["prefixo"], 0)
    return sorted(
        ({**f, "qtd": contagem[f["codigo"]]} for f in FILAS_TOTEM_OCUP),
        key=lambda f: -f["qtd"],
    )


def _filtro_prefixos(fila_codigos: str) -> str:
    """fila_codigos (códigos de FILAS_TOTEM_OCUP, separados por vírgula) →
    filtro pelos prefixos de FLE_BIP correspondentes. Código desconhecido é
    ignorado silenciosamente; nenhum código válido = fila vazia (não
    'todos')."""
    prefixos = []
    for c in (fila_codigos or "").split(","):
        c = c.strip()
        if c.lstrip("-").isdigit() and int(c) in _PREFIXO_POR_CODIGO:
            prefixos.append(_PREFIXO_POR_CODIGO[int(c)])
    if not prefixos:
        return "AND 1=0"
    condicoes = " OR ".join(f"RTRIM(fle.FLE_BIP) LIKE '{p}%'" for p in prefixos)
    return f"AND ({condicoes})"


def listar_fila(fila_codigos: str, mostrar_chamados: bool = False):
    """
    Senhas do totem aguardando identificação/triagem — lê `fle` direto, SEM
    join com osm/pac (a senha recém-impressa ainda não tem paciente nem OS
    vinculados, ver docstring do módulo). `chamado` vem de
    FLE_DTHR_ATENDIMENTO; não existe "já triado" nesse estágio.

    `fila_codigos` é uma lista de códigos de FILAS_TOTEM_OCUP separados por
    vírgula (categorias marcadas na tela de configuração) — a triagem
    enxerga a fila combinada de todas elas, não uma por vez.
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    filtro_psv = _filtro_prefixos(fila_codigos)
    filtro_chamado = "" if mostrar_chamados else "AND fle.FLE_DTHR_ATENDIMENTO IS NULL"

    rows = _query(f"""
        SELECT
            RTRIM(fle.FLE_BIP) AS senha,
            fle.FLE_DTHR_CHEGADA AS chegada_raw,
            fle.FLE_PREFERENCIAL AS preferencial,
            CAST(fle.FLE_ORDEM AS INT) AS ordem,
            fle.FLE_PSV_COD AS categoria_codigo,
            CASE WHEN fle.FLE_DTHR_ATENDIMENTO IS NOT NULL THEN 1 ELSE 0 END AS chamado,
            CONVERT(VARCHAR(5), fle.FLE_DTHR_ATENDIMENTO, 108) AS chamado_em
        FROM fle
        WHERE CAST(fle.FLE_DTHR_CHEGADA AS DATE) = ?
          AND RTRIM(fle.FLE_STR_COD) = 'RPS'
          AND fle.FLE_STATUS = 'A'
          {filtro_psv}
          {filtro_chamado}
        ORDER BY fle.FLE_PREFERENCIAL DESC, fle.FLE_ORDEM ASC
    """, (hoje,))
    for r in rows:
        chegada = r["chegada_raw"]
        r["chegada"] = chegada.strftime("%H:%M") if hasattr(chegada, "strftime") else None
        r["chegada_raw"] = chegada.isoformat() if hasattr(chegada, "isoformat") else chegada
    return rows


def chamar(chegada_raw: str, categoria_codigo: int, login: str):
    """
    Chama a senha pro Painel de Senhas SEM tirar da fila (não mexe em
    FLE_STATUS — ver nota no topo do arquivo). Como ainda não há
    paciente/OS pra identificar a linha, usa a chave real de fle nesse
    estágio: FLE_DTHR_CHEGADA (exata) + FLE_PSV_COD + FLE_STR_COD='RPS' —
    nunca o número da senha sozinho (reinicia todo dia). Grava em PRODUÇÃO,
    igual à Coleta, porque precisa refletir no Painel de Senhas de verdade.
    """
    conn = _get_conn()
    cur = conn.cursor()
    agora = datetime.now()
    try:
        cur.execute("""
            UPDATE fle SET FLE_DTHR_ATENDIMENTO=?, FLE_USR_ATENDIMENTO=?
            WHERE FLE_DTHR_CHEGADA=? AND FLE_PSV_COD=? AND RTRIM(FLE_STR_COD)='RPS' AND FLE_STATUS='A'
        """, (agora, login, datetime.fromisoformat(chegada_raw), categoria_codigo))
        atualizados = cur.rowcount
        conn.commit()
    except pyodbc.Error as e:
        conn.rollback()
        conn.close()
        raise RuntimeError(f"Erro ao chamar senha: {e}")
    conn.close()
    return {"ok": True, "itens_atualizados": atualizados}


# Rótulo/unidade de cada campo do formulário de sinais vitais — usado só pra
# montar o texto do prontuário (RCL_TXT), não existe estrutura de campos no
# NOTASENF (é texto livre puro).
_CAMPOS_TRIAGEM = [
    ("pa_sistolica",  "PA Sistólica",  "mmHg"),
    ("pa_diastolica", "PA Diastólica", "mmHg"),
    ("freq_cardiaca", "FC",            "bpm"),
    ("freq_resp",     "FR",            "irpm"),
    ("temperatura",   "Temp.",         "°C"),
    ("spo2",          "SpO2",          "%"),
    ("peso",          "Peso",          "kg"),
    ("altura",        "Altura",        "cm"),
    ("glicemia",      "Glicemia",      "mg/dL"),
]


def _montar_texto_triagem(campos: dict) -> str:
    agora = datetime.now()
    linha_sinais = "  ".join(
        f"{rotulo}: {campos[chave]}{unid}"
        for chave, rotulo, unid in _CAMPOS_TRIAGEM
        if str(campos.get(chave) or "").strip()
    )
    partes = [
        "TRIAGEM DE ENFERMAGEM — ATENDIMENTO OCUPACIONAL",
        f"Data: {agora.strftime('%d/%m/%Y %H:%M')}",
        "",
    ]
    if linha_sinais:
        partes.append(linha_sinais)
        partes.append("")
    obs = str(campos.get("observacoes") or "").strip()
    if obs:
        partes.append("Observações:")
        partes.append(obs)
    return "\r\n".join(partes)


def salvar_triagem(paciente: int, medico: int, campos: dict, login: str):
    """
    Grava a triagem (sinais vitais + observações) como um novo Registro
    Clínico (RCL_COD='NOTASENF') no prontuário do paciente. SOMENTE em
    smart_hml, nunca em produção — mesma cautela do resto do Dashboard que
    escreve em RCL (ver /api/atendimento/salvar em main.py).
    """
    texto = _montar_texto_triagem(campos)
    if not texto.strip():
        raise ValueError("Nenhum campo preenchido.")

    agora = datetime.now()
    conn = _get_conn_hml()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO RCL (
                RCL_PAC, RCL_TPCOD, RCL_COD, RCL_DTHR, RCL_MED,
                RCL_STAT, RCL_TXT, RCL_USR_LOGIN, RCL_RESULT,
                RCL_USR_LOGIN_LIB, RCL_DTHR_LIB, RCL_USR_LOGIN_DIGIT,
                RCL_DTHR_DIGIT, RCL_CONCLUSAO, RCL_VLR_RESULT
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            paciente, "S", RCL_COD_TRIAGEM, agora, medico,
            "L", texto, login, "N",
            login, agora, login,
            agora, "?", "Inconclusivo",
        ))
        conn.commit()
    except pyodbc.Error as e:
        conn.rollback()
        conn.close()
        raise RuntimeError(f"Erro ao gravar triagem em smart_hml: {e}")
    conn.close()
    return {"ok": True, "ambiente": "smart_hml", "rcl_txt": texto}


def historico(paciente: int, limite: int = 20):
    """Triagens anteriores do paciente — lê de PRODUÇÃO (nunca smart_hml pra leitura)."""
    rows = _query("""
        SELECT TOP (?) RCL_DTHR AS dthr, CAST(RCL_TXT AS VARCHAR(MAX)) AS texto,
               RTRIM(ISNULL(RCL_USR_LOGIN, '')) AS login
        FROM RCL
        WHERE RCL_PAC = ? AND RTRIM(RCL_COD) = 'NOTASENF'
        ORDER BY RCL_DTHR DESC
    """, (limite, paciente))
    for r in rows:
        if hasattr(r.get("dthr"), "strftime"):
            r["dthr"] = r["dthr"].strftime("%d/%m/%Y %H:%M")
    return rows
