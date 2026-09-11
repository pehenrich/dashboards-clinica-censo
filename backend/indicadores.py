# -*- coding: utf-8 -*-
"""
Indicadores de Gestão — cadastro de indicadores por setor e lançamento do
resultado apurado por período. Armazenamento local (SQLite), independente do
banco Smart (mesmo padrão de chat_interno.db/organograma.db). Catálogo inicial
seedado a partir da planilha "Base estrutural_Gerenciamento_Indicadores_
Clinica_Censo" fornecida pela gestão.
"""
import ast
import operator
import os
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "indicadores.db")

# Injetado por main.py no startup (mesmo padrão do scheduler.py:
# set_query_func) — indicadores.py não conecta direto no SQL Server, usa o
# helper query() já existente em main.py.
_query_func = None


def set_query_func(fn):
    global _query_func
    _query_func = fn


def slug_setor(nome):
    """Gera o id de módulo de permissão para um setor (ex.: 'RH / DP' -> 'rh_dp').
    Usado tanto para montar TODOS_MODULOS dinamicamente quanto no frontend
    (mesma lógica replicada em JS) para checar podeVer('indicadores_<slug>')."""
    nome = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode("ascii")
    nome = re.sub(r"[^a-zA-Z0-9]+", "_", nome).strip("_").lower()
    return nome

# (setor, indicador, objetivo, formula, meta_sugerida, periodicidade)
SEED_INDICADORES = [
    ("Ocupacional", "Taxa de devolução de documentos para correção", "Monitorar taxa de devolução de documentos para correção", "Apuração mensal de taxa de devolução de documentos para correção", "Acompanhamento e melhoria contínua", "Mensal"),
    ("Ocupacional", "Atendimentos no mês por CPF", "Monitorar atendimentos no mês por CPF", "Apuração mensal de atendimentos no mês por CPF", "Conforme demanda e planejamento", "Mensal"),
    ("Ocupacional", "Taxa de documentos de entrega no prazo", "Monitorar taxa de documentos de entrega no prazo", "Apuração mensal de taxa de documentos de entrega no prazo", "Acompanhamento e melhoria contínua", "Mensal"),
    ("Ocupacional", "Taxa de encaminhamentos para especialidades médicas", "Monitorar taxa de encaminhamentos para especialidades médicas", "Apuração mensal de taxa de encaminhamentos para especialidades médicas", "Acompanhamento e melhoria contínua", "Mensal"),
    ("Ocupacional", "Quantidade de elaboração de PCMSO", "Monitorar quantidade de elaboração de PCMSO", "Apuração mensal de quantidade de elaboração de PCMSO", "Conforme demanda e planejamento", "Mensal"),
    ("Ocupacional", "Quantidade de documentos por PCMSO", "Monitorar quantidade de documentos por PCMSO", "Apuração mensal de quantidade de documentos por PCMSO", "Conforme demanda e planejamento", "Mensal"),
    ("Ocupacional", "Números de exames realizados ocupacionais", "Monitorar números de exames realizados ocupacionais", "Apuração mensal de números de exames realizados ocupacionais", "Conforme demanda e planejamento", "Mensal"),
    ("Ocupacional", "Taxa de retificação de laudos", "Monitorar taxa de retificação de laudos", "Apuração mensal de taxa de retificação de laudos", "Acompanhamento e melhoria contínua", "Mensal"),
    ("Ocupacional", "Taxa de repetição de imagem", "Monitorar taxa de repetição de imagem", "Apuração mensal de taxa de repetição de imagem", "Acompanhamento e melhoria contínua", "Mensal"),
    ("Ocupacional", "Tempo médio de espera da recepção", "Monitorar tempo médio de espera da recepção", "Apuração mensal de tempo médio de espera da recepção", "Conforme demanda e planejamento", "Mensal"),
    ("Ocupacional", "Notificações", "Controlar ocorrências notificadas", "Total de notificações registradas", "100% registradas", "Mensal"),

    ("Consultório", "Tempo médio de espera da recepção", "Melhorar experiência do paciente", "Soma do tempo de espera / total de atendidos", "Até 20 min", "Mensal"),
    ("Consultório", "Consultas agendadas", "Medir demanda programada", "Total de agendamentos", "Conforme capacidade", "Diário/Mensal"),
    ("Consultório", "Consultas canceladas", "Controlar perdas de agenda", "Total de cancelamentos", "< 10% dos agendados", "Mensal"),
    ("Consultório", "Consultas reagendadas", "Monitorar remarcações", "Total de reagendamentos", "Monitoramento", "Mensal"),
    ("Consultório", "Consultas realizadas", "Medir produção efetiva", "Total de atendimentos realizados", "> 85% dos agendados", "Mensal"),
    ("Consultório", "Absenteísmo de agendas", "Reduzir não comparecimento", "Faltas / agendados x 100", "< 5%", "Mensal"),
    ("Consultório", "Confirmações de agenda", "Melhorar comparecimento", "Confirmados / agendados x 100", "> 90%", "Diário/Mensal"),
    ("Consultório", "USG realizadas", "Monitorar USG realizadas", "Apuração mensal de USG realizadas", "Conforme demanda e planejamento", "Mensal"),
    ("Consultório", "USG agendadas", "Monitorar USG agendadas", "Apuração mensal de USG agendadas", "Conforme demanda e planejamento", "Mensal"),
    ("Consultório", "USG canceladas", "Monitorar USG canceladas", "Apuração mensal de USG canceladas", "Conforme demanda e planejamento", "Mensal"),
    ("Consultório", "USG reagendadas", "Monitorar USG reagendadas", "Apuração mensal de USG reagendadas", "Conforme demanda e planejamento", "Mensal"),
    ("Consultório", "USG absenteísmo de agenda", "Monitorar USG absenteísmo de agenda", "Apuração mensal de USG absenteísmo de agenda", "Conforme demanda e planejamento", "Mensal"),
    ("Consultório", "Guias geradas x guias entregues", "Monitorar guias geradas x guias entregues", "Apuração mensal de guias geradas x guias entregues", "Conforme demanda e planejamento", "Mensal"),

    ("Diagnóstico", "Guias geradas x guias entregues", "Monitorar guias geradas x guias entregues", "Apuração mensal de guias geradas x guias entregues", "Conforme demanda e planejamento", "Mensal"),
    ("Diagnóstico", "Tempo médio de espera da recepção", "Monitorar tempo médio de espera da recepção", "Apuração mensal de tempo médio de espera da recepção", "Conforme demanda e planejamento", "Mensal"),

    ("Laboratório", "Exames realizados", "Medir produção diagnóstica", "Total de exames realizados", "Conforme demanda", "Mensal"),
    ("Laboratório", "Coletas realizadas", "Medir volume de coletas", "Total de coletas", "Conforme demanda", "Mensal"),
    ("Laboratório", "Tempo de liberação de laudos internos", "Ganhar agilidade operacional", "Soma do tempo de liberação / total de exames", "Dentro do prazo padrão", "Mensal"),
    ("Laboratório", "Índice de recoleta", "Controlar falhas na coleta", "Total de recoletas", "< 2%", "Mensal"),
    ("Laboratório", "Tempo médio de comunicação de resultados críticos", "Acompanhar produtividade", "Total processado no período", "Conforme demanda", "Mensal"),
    ("Laboratório", "Perda de amostras", "Reduzir desperdícios", "Total de perdas registradas", "Zero ou mínimo possível", "Mensal"),
    ("Laboratório", "Taxa de conformidade check list gineco-uretral", "Monitorar taxa de conformidade check list gineco-uretral", "Apuração mensal de taxa de conformidade check list gineco-uretral", "Acompanhamento e melhoria contínua", "Mensal"),
    ("Laboratório", "Taxa conformidade de controle de qualidade externo", "Monitorar taxa conformidade de controle de qualidade externo", "Apuração mensal de taxa conformidade de controle de qualidade externo", "Acompanhamento e melhoria contínua", "Mensal"),
    ("Laboratório", "Taxa de laudos retificados", "Monitorar taxa de laudos retificados", "Apuração mensal de taxa de laudos retificados", "Acompanhamento e melhoria contínua", "Mensal"),
    ("Laboratório", "Índice de recoleta de laboratório de apoio externo", "Monitorar índice de recoleta de laboratório de apoio externo", "Apuração mensal de índice de recoleta de laboratório de apoio externo", "Acompanhamento e melhoria contínua", "Mensal"),

    ("Faturamento", "Valor faturado", "Medir resultado do faturamento", "Soma dos valores faturados", "Crescimento sustentável", "Mensal"),
    ("Faturamento", "Taxa de guias entregues dentro dos prazos", "Medir produtividade do setor", "Total de guias faturadas", "Conforme produção", "Mensal"),
    ("Faturamento", "Taxa de prontuários entregues dentro dos prazos", "Monitorar perdas financeiras", "Total de glosas no período", "Redução contínua", "Mensal"),
    ("Faturamento", "Percentual de glosa", "Avaliar qualidade do faturamento", "Glosas / faturado x 100", "< 3%", "Mensal"),
    ("Faturamento", "Atendimentos por convênio", "Medir produção por convênio", "Total de atendimentos por guia", "Conforme demanda e planejamento", "Mensal"),
    ("Faturamento", "Atendimentos particulares", "Medir produção particular", "Total de atendimentos particulares", "Conforme demanda e planejamento", "Mensal"),
    ("Faturamento", "Valor produção", "Medir efetividade da reversão", "Valor recuperado / valor glosado x 100", "Crescente", "Mensal"),
    ("Faturamento", "Valor represado", "Monitorar valor represado", "Apuração mensal de valor represado", "Conforme demanda e planejamento", "Mensal"),

    ("RH / DP", "Total de colaboradores", "Acompanhar quadro funcional", "Total ativo no período", "Monitoramento", "Mensal"),
    ("RH / DP", "Admissões", "Controlar entradas", "Total de admissões", "Monitoramento", "Mensal"),
    ("RH / DP", "Desligamentos", "Controlar saídas", "Total de desligamentos", "Monitoramento", "Mensal"),
    ("RH / DP", "Turnover", "Avaliar rotatividade", "Desligamentos / total de colaboradores x 100", "< 5% ao mês", "Mensal"),
    ("RH / DP", "Absenteísmo de colaboradores", "Medir faltas internas", "Horas de ausência / horas previstas x 100", "Redução contínua", "Mensal"),
    ("RH / DP", "Horas de treinamento", "Medir desenvolvimento", "Total de horas aplicadas", "Crescente", "Mensal/Trimestral"),

    ("Almoxarifado", "Entradas de materiais", "Controlar abastecimento", "Total de entradas", "Monitoramento", "Mensal"),
    ("Almoxarifado", "Saídas de materiais", "Controlar consumo", "Total de saídas", "Monitoramento", "Mensal"),
    ("Almoxarifado", "Perdas e vencimentos", "Reduzir desperdícios", "Total de itens perdidos/vencidos", "Redução contínua", "Mensal"),
    ("Almoxarifado", "Giro de estoque", "Medir movimentação", "Consumo médio / estoque médio", "Conforme perfil do item", "Mensal"),
    ("Almoxarifado", "Taxa de conformidade de acuracidade de inventário", "Monitorar taxa de conformidade de acuracidade de inventário", "Apuração mensal de taxa de conformidade de acuracidade de inventário", "Acompanhamento e melhoria contínua", "Mensal"),
    ("Almoxarifado", "Taxa de desabastecimento", "Monitorar taxa de desabastecimento", "Apuração mensal de taxa de desabastecimento", "Acompanhamento e melhoria contínua", "Mensal"),

    ("Comercial", "Novos clientes/empresas", "Medir expansão comercial", "Total de novos contratos/clientes", "Crescimento mensal", "Mensal"),
    ("Comercial", "Propostas enviadas", "Medir atividade comercial", "Total de propostas enviadas", "Crescente", "Semanal/Mensal"),
    ("Comercial", "Propostas convertidas", "Medir efetividade de vendas", "Total de propostas fechadas", "Crescente", "Mensal"),
    ("Comercial", "Taxa de conversão", "Avaliar desempenho comercial", "Propostas convertidas / propostas enviadas x 100", "> 20%", "Mensal"),
    ("Comercial", "Receita por novos contratos", "Medir retorno comercial", "Soma da receita dos novos contratos", "Crescimento sustentável", "Mensal"),
    ("Comercial", "Perda de clientes", "Monitorar evasão", "Clientes perdidos / clientes ativos x 100", "Redução contínua", "Mensal"),
    ("Comercial", "Número de ações in company", "Monitorar número de ações in company", "Apuração mensal de número de ações in company", "Conforme demanda e planejamento", "Mensal"),
    ("Comercial", "Número de visitas realizadas", "Monitorar número de visitas realizadas", "Apuração mensal de número de visitas realizadas", "Conforme demanda e planejamento", "Mensal"),

    ("TI", "Taxa de disponibilidade do link de internet", "Monitorar taxa de disponibilidade do link de internet", "Apuração mensal de taxa de disponibilidade do link de internet", "Acompanhamento e melhoria contínua", "Mensal"),
    ("TI", "Taxa de chamado por status", "Monitorar taxa de chamado por status", "Apuração mensal de taxa de chamado por status", "Acompanhamento e melhoria contínua", "Mensal"),
    ("TI", "Chamados abertos", "Medir demanda de suporte", "Total de chamados abertos", "Monitoramento", "Mensal"),
    ("TI", "Tempo médio de atendimento", "Ganhar agilidade no suporte", "Soma do tempo / total de chamados", "Redução contínua", "Mensal"),
    ("TI", "Disponibilidade dos sistemas", "Garantir operação", "Tempo disponível / tempo total x 100", "> 99%", "Mensal"),
    ("TI", "Taxa de chamado aprovados", "Monitorar taxa de chamado aprovados", "Apuração mensal de taxa de chamado aprovados", "Acompanhamento e melhoria contínua", "Mensal"),
]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS indicadores (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            setor         TEXT NOT NULL,
            indicador     TEXT NOT NULL,
            objetivo      TEXT,
            formula       TEXT,
            meta          TEXT,
            periodicidade TEXT,
            responsavel   TEXT,
            ativo         INTEGER NOT NULL DEFAULT 1,
            criado_em     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS resultados (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            indicador_id   INTEGER NOT NULL,
            periodo        TEXT NOT NULL,
            resultado      TEXT,
            status         TEXT,
            plano_acao     TEXT,
            atualizado_em  TEXT NOT NULL,
            atualizado_por TEXT,
            UNIQUE(indicador_id, periodo)
        );
        CREATE INDEX IF NOT EXISTS idx_resultados_periodo ON resultados(periodo);

        CREATE TABLE IF NOT EXISTS variaveis (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            indicador_id INTEGER NOT NULL,
            chave        TEXT NOT NULL,
            label        TEXT NOT NULL,
            tipo         TEXT NOT NULL CHECK(tipo IN ('automatico','manual')),
            calculo_id   TEXT,
            ordem        INTEGER NOT NULL DEFAULT 0,
            UNIQUE(indicador_id, chave)
        );

        CREATE TABLE IF NOT EXISTS variavel_valores (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            variavel_id    INTEGER NOT NULL,
            periodo        TEXT NOT NULL,
            valor          REAL,
            atualizado_em  TEXT NOT NULL,
            atualizado_por TEXT,
            UNIQUE(variavel_id, periodo)
        );
    """)
    conn.commit()

    # Migração: coluna 'expressao' pode não existir em banco criado antes desta versão.
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(indicadores)").fetchall()]
    if "expressao" not in cols:
        conn.execute("ALTER TABLE indicadores ADD COLUMN expressao TEXT")
        conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM indicadores").fetchone()[0]
    if total == 0:
        agora = datetime.now(timezone.utc).isoformat()
        conn.executemany(
            "INSERT INTO indicadores (setor, indicador, objetivo, formula, meta, periodicidade, responsavel, ativo, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, 1, ?)",
            [(s, i, o, f, m, p, agora) for (s, i, o, f, m, p) in SEED_INDICADORES],
        )
        conn.commit()
    conn.close()


def listar_setores():
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT setor FROM indicadores WHERE ativo = 1 ORDER BY setor").fetchall()
    conn.close()
    return [r["setor"] for r in rows]


def listar_indicadores(periodo, setor=None):
    """Catálogo de indicadores ativos + resultado lançado no período informado (se houver)."""
    conn = get_conn()
    sql = """
        SELECT i.id, i.setor, i.indicador, i.objetivo, i.formula, i.meta, i.periodicidade, i.responsavel, i.expressao,
               r.resultado, r.status, r.plano_acao, r.atualizado_em, r.atualizado_por
        FROM indicadores i
        LEFT JOIN resultados r ON r.indicador_id = i.id AND r.periodo = ?
        WHERE i.ativo = 1
    """
    params = [periodo]
    if setor:
        sql += " AND i.setor = ?"
        params.append(setor)
    sql += " ORDER BY i.setor, i.indicador"
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def criar_indicador(setor, indicador, objetivo, formula, meta, periodicidade, responsavel):
    conn = get_conn()
    agora = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO indicadores (setor, indicador, objetivo, formula, meta, periodicidade, responsavel, ativo, criado_em) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
        (setor, indicador, objetivo, formula, meta, periodicidade, responsavel, agora),
    )
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def atualizar_indicador(indicador_id, setor, indicador, objetivo, formula, meta, periodicidade, responsavel):
    conn = get_conn()
    cur = conn.execute(
        "UPDATE indicadores SET setor=?, indicador=?, objetivo=?, formula=?, meta=?, periodicidade=?, responsavel=? WHERE id=?",
        (setor, indicador, objetivo, formula, meta, periodicidade, responsavel, indicador_id),
    )
    atualizados = cur.rowcount
    conn.commit()
    conn.close()
    if atualizados == 0:
        raise ValueError("Indicador não encontrado.")


def salvar_expressao(indicador_id, expressao):
    """Expressão usada pra calcular o resultado a partir das variáveis
    cadastradas (ex.: 'desligamentos / colaboradores * 100'). None/'' remove
    o cálculo automático e o indicador volta a aceitar resultado manual."""
    conn = get_conn()
    cur = conn.execute("UPDATE indicadores SET expressao=? WHERE id=?", (expressao or None, indicador_id))
    atualizados = cur.rowcount
    conn.commit()
    conn.close()
    if atualizados == 0:
        raise ValueError("Indicador não encontrado.")


def excluir_indicador(indicador_id):
    """Soft delete — preserva o histórico de resultados já lançado."""
    conn = get_conn()
    cur = conn.execute("UPDATE indicadores SET ativo = 0 WHERE id = ?", (indicador_id,))
    atualizados = cur.rowcount
    conn.commit()
    conn.close()
    if atualizados == 0:
        raise ValueError("Indicador não encontrado.")


def lancar_resultado(indicador_id, periodo, resultado, status, plano_acao, usuario):
    conn = get_conn()
    existe = conn.execute("SELECT id FROM indicadores WHERE id = ?", (indicador_id,)).fetchone()
    if not existe:
        conn.close()
        raise ValueError("Indicador não encontrado.")
    agora = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO resultados (indicador_id, periodo, resultado, status, plano_acao, atualizado_em, atualizado_por)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(indicador_id, periodo) DO UPDATE SET
            resultado = excluded.resultado,
            status = excluded.status,
            plano_acao = excluded.plano_acao,
            atualizado_em = excluded.atualizado_em,
            atualizado_por = excluded.atualizado_por
    """, (indicador_id, periodo, resultado, status, plano_acao, agora, usuario))
    conn.commit()
    conn.close()


def historico_resultados(indicador_id, limite=12):
    conn = get_conn()
    rows = conn.execute(
        "SELECT periodo, resultado, status, plano_acao, atualizado_em, atualizado_por "
        "FROM resultados WHERE indicador_id = ? ORDER BY periodo DESC LIMIT ?",
        (indicador_id, limite),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _ultimos_periodos(periodo_final, n=12):
    """Lista de n períodos YYYY-MM terminando em periodo_final, em ordem crescente."""
    y, m = (int(p) for p in periodo_final.split("-"))
    periodos = []
    for _ in range(n):
        periodos.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(periodos))


def dashboard_setor(setor, periodo, n_periodos=12):
    """Indicadores ativos do setor com resultado do período atual + histórico
    de status dos últimos n_periodos (pra timeline visual), independente de o
    resultado ser numérico ou texto livre."""
    conn = get_conn()
    inds = conn.execute(
        "SELECT id, indicador, objetivo, formula, meta, periodicidade, responsavel, expressao "
        "FROM indicadores WHERE setor = ? AND ativo = 1 ORDER BY indicador",
        (setor,),
    ).fetchall()
    periodos = _ultimos_periodos(periodo, n_periodos)
    placeholders = ",".join("?" for _ in periodos)

    saida = []
    for ind in inds:
        rows = conn.execute(
            f"SELECT periodo, resultado, status, plano_acao FROM resultados "
            f"WHERE indicador_id = ? AND periodo IN ({placeholders})",
            (ind["id"], *periodos),
        ).fetchall()
        por_periodo = {r["periodo"]: dict(r) for r in rows}
        historico = [por_periodo.get(p) or {"periodo": p, "resultado": None, "status": None, "plano_acao": None} for p in periodos]
        atual = por_periodo.get(periodo)
        saida.append({
            "id": ind["id"], "indicador": ind["indicador"], "objetivo": ind["objetivo"],
            "formula": ind["formula"], "meta": ind["meta"], "periodicidade": ind["periodicidade"],
            "responsavel": ind["responsavel"], "expressao": ind["expressao"],
            "resultado": atual["resultado"] if atual else None,
            "status": atual["status"] if atual else None,
            "plano_acao": atual["plano_acao"] if atual else None,
            "historico": historico,
        })
    conn.close()
    return saida


# ── Motor de fórmulas ─────────────────────────────────────────────────────────
# Cada indicador pode ter uma `expressao` (ex.: "desligamentos / colaboradores
# * 100") calculada em cima de `variaveis` cadastradas pra ele. Cada variável é
# 'automatico' (valor vem de uma consulta já validada contra o Smart, catálogo
# abaixo) ou 'manual' (alguém digita o número daquele período — mas quem soma/
# divide continua sendo o sistema, não a pessoa).

_OPERADORES = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
    ast.Mod: operator.mod,
}


def avaliar_formula(expressao, variaveis):
    """Avalia uma expressão aritmética (+ - * / ( ) sobre nomes de variáveis).
    Não usa eval() — só percorre nós de AST explicitamente permitidos, então
    não há risco de execução de código arbitrário mesmo que a expressão venha
    de um cadastro livre no admin."""
    try:
        arvore = ast.parse(expressao, mode="eval")
    except SyntaxError:
        raise ValueError("Fórmula com sintaxe inválida.")

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in variaveis:
                raise ValueError(f"Variável '{node.id}' não cadastrada.")
            valor = variaveis[node.id]
            if valor is None:
                raise ValueError(f"Variável '{node.id}' ainda sem valor no período.")
            return float(valor)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERADORES:
            return _OPERADORES[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERADORES:
            return _OPERADORES[type(node.op)](_eval(node.operand))
        raise ValueError("Fórmula usa uma construção não permitida (só +, -, *, /, parênteses e nomes de variáveis).")

    try:
        return _eval(arvore)
    except ZeroDivisionError:
        raise ValueError("Divisão por zero na fórmula.")


def _periodo_para_datas(periodo):
    """'YYYY-MM' -> (primeiro dia, primeiro dia do mês seguinte), pra WHERE data >= ? AND data < ?."""
    y, m = (int(p) for p in periodo.split("-"))
    ini = f"{y:04d}-{m:02d}-01"
    y2, m2 = (y, m + 1) if m < 12 else (y + 1, 1)
    fim = f"{y2:04d}-{m2:02d}-01"
    return ini, fim


def _calc_coletas_realizadas_lab(periodo):
    ini, fim = _periodo_para_datas(periodo)
    rows = _query_func(
        "SELECT COUNT(*) AS qtd FROM smm WHERE SMM_DTHR_COLETA >= ? AND SMM_DTHR_COLETA < ?",
        (ini, fim),
    )
    return rows[0]["qtd"] if rows else 0


CALCULOS_AUTOMATICOS = {
    "coletas_realizadas_lab": {
        "label": "Coletas realizadas no período (Smart)",
        "fn": _calc_coletas_realizadas_lab,
    },
}


def listar_calculos_automaticos():
    return [{"id": k, "label": v["label"]} for k, v in CALCULOS_AUTOMATICOS.items()]


def listar_variaveis(indicador_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, chave, label, tipo, calculo_id, ordem FROM variaveis WHERE indicador_id = ? ORDER BY ordem, id",
        (indicador_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def criar_variavel(indicador_id, chave, label, tipo, calculo_id, ordem=0):
    if tipo not in ("automatico", "manual"):
        raise ValueError("Tipo de variável inválido.")
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", chave or ""):
        raise ValueError("Chave da variável deve ser um nome simples (letras, números, _), sem espaços.")
    if tipo == "automatico" and calculo_id not in CALCULOS_AUTOMATICOS:
        raise ValueError("Cálculo automático não encontrado.")
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO variaveis (indicador_id, chave, label, tipo, calculo_id, ordem) VALUES (?, ?, ?, ?, ?, ?)",
            (indicador_id, chave, label, tipo, calculo_id if tipo == "automatico" else None, ordem),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError(f"Já existe uma variável com a chave '{chave}' nesse indicador.")
    finally:
        conn.close()


def excluir_variavel(variavel_id):
    conn = get_conn()
    cur = conn.execute("DELETE FROM variaveis WHERE id = ?", (variavel_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise ValueError("Variável não encontrada.")


def lancar_valor_variavel(variavel_id, periodo, valor, usuario):
    conn = get_conn()
    var = conn.execute("SELECT tipo FROM variaveis WHERE id = ?", (variavel_id,)).fetchone()
    if not var:
        conn.close()
        raise ValueError("Variável não encontrada.")
    if var["tipo"] != "manual":
        conn.close()
        raise ValueError("Essa variável é calculada automaticamente — não dá pra lançar valor manual nela.")
    agora = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO variavel_valores (variavel_id, periodo, valor, atualizado_em, atualizado_por)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(variavel_id, periodo) DO UPDATE SET
            valor = excluded.valor, atualizado_em = excluded.atualizado_em, atualizado_por = excluded.atualizado_por
    """, (variavel_id, periodo, valor, agora, usuario))
    conn.commit()
    conn.close()


def _valor_variavel(conn, variavel, periodo):
    if variavel["tipo"] == "automatico":
        calc = CALCULOS_AUTOMATICOS.get(variavel["calculo_id"])
        if not calc or _query_func is None:
            return None
        try:
            return calc["fn"](periodo)
        except Exception as e:
            print(f"[Indicadores] Erro ao calcular '{variavel['calculo_id']}' ({periodo}): {e}")
            return None
    row = conn.execute(
        "SELECT valor FROM variavel_valores WHERE variavel_id = ? AND periodo = ?",
        (variavel["id"], periodo),
    ).fetchone()
    return row["valor"] if row else None


def calcular_indicador(indicador_id, periodo):
    """Retorna {resultado, erro, variaveis: [{chave,label,tipo,valor,pendente}]}
    pro indicador no período — junta variáveis automáticas (calculadas na hora)
    e manuais (o que já foi lançado), e avalia a expressão cadastrada."""
    conn = get_conn()
    ind = conn.execute("SELECT expressao FROM indicadores WHERE id = ?", (indicador_id,)).fetchone()
    if not ind:
        conn.close()
        raise ValueError("Indicador não encontrado.")
    variaveis_cad = conn.execute(
        "SELECT id, chave, label, tipo, calculo_id FROM variaveis WHERE indicador_id = ? ORDER BY ordem, id",
        (indicador_id,),
    ).fetchall()

    valores = {}
    detalhe = []
    for v in variaveis_cad:
        valor = _valor_variavel(conn, v, periodo)
        valores[v["chave"]] = valor
        detalhe.append({
            "id": v["id"], "chave": v["chave"], "label": v["label"], "tipo": v["tipo"],
            "calculo_id": v["calculo_id"], "valor": valor, "pendente": valor is None,
        })
    conn.close()

    resultado, erro = None, None
    if ind["expressao"] and variaveis_cad:
        try:
            resultado = avaliar_formula(ind["expressao"], valores)
            resultado = round(resultado, 2)
        except ValueError as e:
            erro = str(e)
    elif ind["expressao"] and not variaveis_cad:
        erro = "Fórmula cadastrada, mas nenhuma variável definida ainda."

    return {"resultado": resultado, "erro": erro, "variaveis": detalhe}
