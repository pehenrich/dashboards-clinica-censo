# -*- coding: utf-8 -*-
"""
jarvis.py
Assistente de consulta por voz/texto (Fase 1 da especificação: consulta sob
demanda, sem modo reunião ainda). Fluxo: pergunta em português -> GPT escolhe
UMA ferramenta (function calling de verdade, catálogo pensado pra crescer —
nada de só um punhado fixo de métricas financeiras) -> executa -> formata
resposta em texto -> opcionalmente gera PDF e envia por e-mail.

Decisões desta fase (fora da spec original, ajustadas à infra real do
Dashboard):
- STT (voz -> texto) e TTS (texto -> voz) são feitos no NAVEGADOR via Web
  Speech API / SpeechSynthesis, não aqui. A spec original previa Whisper
  local no servidor, mas isso exigiria instalar um stack de ML pesado
  (torch + modelo de ~1,5GB) num servidor de produção que já roda serviços
  críticos da clínica — desnecessário quando o navegador já faz STT/TTS em
  português de graça.
- LLM é o OpenAI (gpt-4o-mini) via OPENAI_API_KEY, que já existe configurada
  e em uso neste servidor (briefing de IA, bot de agenda) — evita precisar
  criar uma conta/cobrança nova só pro Jarvis (a spec original pedia Claude).
- E-mail reaproveita email_sender.py (Outlook Web via Playwright) — SMTP
  direto (Nodemailer, como a spec original sugeria) não funciona neste
  tenant M365 (SMTP AUTH desabilitado, sem admin pra habilitar).
- Nenhuma métrica é recalculada do zero: cada ferramenta chama a função já
  existente em main.py (ou usa a mesma fórmula de valor líquido já
  documentada em CLAUDE.md) — o Jarvis é só uma camada de interpretação de
  linguagem natural em cima do que o Dashboard já calcula. O catálogo de
  ferramentas (TOOLS) é o ponto de extensão: pra deixar o Jarvis responder
  sobre um novo tipo de dado, basta adicionar uma entrada nova aqui — o
  usuário pediu explicitamente que não fique travado num punhado fixo de
  perguntas financeiras.
"""
import os
import re
import json
import time
import difflib
import sqlite3
import tempfile
import html as html_mod
from datetime import datetime, timedelta

import httpx

# Atas de reuniao ficam num SQLite local, independente do banco Smart --
# mesmo padrao ja usado em chat_interno.db/guias.db -- sem isso, cada ata
# gerada sumia ao fechar a tela (bug real reportado: "nao tem como ver o
# historico de reuniao").
_DB_PATH_ATAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "atas_reuniao.db")


def _conn_atas():
    conn = sqlite3.connect(_DB_PATH_ATAS)
    conn.row_factory = sqlite3.Row
    return conn


def _inicializar_db_atas():
    conn = _conn_atas()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS atas (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            data_inicio     TEXT NOT NULL,
            data_geracao    TEXT NOT NULL,
            duracao_min     REAL NOT NULL,
            participantes   TEXT,
            resumo          TEXT,
            decisoes_json   TEXT NOT NULL,
            acoes_json      TEXT NOT NULL,
            insights_json   TEXT NOT NULL,
            alertas_json    TEXT NOT NULL,
            transcricao     TEXT
        );

        CREATE TABLE IF NOT EXISTS acoes (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            ata_id_origem    INTEGER NOT NULL,
            acao             TEXT NOT NULL,
            responsavel      TEXT,
            prazo            TEXT,
            status           TEXT NOT NULL DEFAULT 'pendente',
            ata_id_concluido INTEGER,
            criado_em        TEXT NOT NULL,
            concluido_em     TEXT
        );
    """)
    conn.commit()
    conn.close()


def _salvar_ata(ata: dict) -> int:
    conn = _conn_atas()
    cur = conn.execute(
        """INSERT INTO atas
           (data_inicio, data_geracao, duracao_min, participantes, resumo,
            decisoes_json, acoes_json, insights_json, alertas_json, transcricao)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ata.get("data_inicio", ""), ata.get("data_geracao", ""), ata.get("duracao_min", 0),
            ata.get("participantes", ""), ata.get("resumo", ""),
            json.dumps(ata.get("decisoes") or [], ensure_ascii=False),
            json.dumps(ata.get("acoes") or [], ensure_ascii=False),
            json.dumps(ata.get("insights") or [], ensure_ascii=False),
            json.dumps(ata.get("alertas") or [], ensure_ascii=False),
            ata.get("transcricao", ""),
        ),
    )
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def _listar_acoes_pendentes() -> list:
    conn = _conn_atas()
    rows = conn.execute(
        "SELECT id, acao, responsavel, prazo, criado_em FROM acoes WHERE status = 'pendente' ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _criar_acao(ata_id: int, acao: str, responsavel: str, prazo: str) -> int:
    conn = _conn_atas()
    cur = conn.execute(
        "INSERT INTO acoes (ata_id_origem, acao, responsavel, prazo, status, criado_em) VALUES (?, ?, ?, ?, 'pendente', ?)",
        (ata_id, acao, responsavel, prazo, datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def _marcar_acao_concluida(acao_id: int, ata_id_concluido: int):
    conn = _conn_atas()
    conn.execute(
        "UPDATE acoes SET status = 'concluido', ata_id_concluido = ?, concluido_em = ? WHERE id = ? AND status = 'pendente'",
        (ata_id_concluido, datetime.now().strftime("%Y-%m-%d %H:%M"), acao_id),
    )
    conn.commit()
    conn.close()


def listar_atas_historico() -> list:
    """Lista resumida (sem transcrição completa, pra não pesar) pra tela de
    histórico de reuniões."""
    _inicializar_db_atas()
    conn = _conn_atas()
    rows = conn.execute(
        "SELECT id, data_inicio, duracao_min, participantes, resumo FROM atas ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def obter_ata_por_id(ata_id: int):
    """Reconstrói resolvidas/pendentes a partir da tabela acoes (fonte única
    de verdade, por ata_id_origem/ata_id_concluido) em vez de guardar uma 2a
    cópia em JSON -- assim ao reabrir uma ata antiga pelo histórico, o
    "resolvida nesta reunião" continua correto mesmo que reuniões mais
    recentes já tenham acontecido depois."""
    _inicializar_db_atas()
    conn = _conn_atas()
    row = conn.execute("SELECT * FROM atas WHERE id = ?", (ata_id,)).fetchone()
    if not row:
        conn.close()
        return None
    d = dict(row)
    d["decisoes"] = json.loads(d.pop("decisoes_json") or "[]")
    d["acoes"] = json.loads(d.pop("acoes_json") or "[]")
    d["insights"] = json.loads(d.pop("insights_json") or "[]")
    d["alertas"] = json.loads(d.pop("alertas_json") or "[]")

    resolvidas = conn.execute(
        "SELECT acao, responsavel, prazo FROM acoes WHERE ata_id_concluido = ?", (ata_id,)
    ).fetchall()
    pendentes = conn.execute(
        """SELECT acao, responsavel, prazo FROM acoes
           WHERE ata_id_origem < ? AND (ata_id_concluido IS NULL OR ata_id_concluido > ?)""",
        (ata_id, ata_id),
    ).fetchall()
    conn.close()
    d["acoes_resolvidas_nesta_reuniao"] = [dict(r) for r in resolvidas]
    d["acoes_pendentes_anteriores"] = [dict(r) for r in pendentes]
    return d

OPENAI_MODEL = "gpt-4o-mini"

_VLIQ = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"

# Mesma classificação de categoria de serviço usada em
# /api/financeiro/receita-por-tipo-servico (main.py) — reaproveitada aqui
# pra permitir consulta de ticket médio por categoria, que aquele endpoint
# não calcula (só soma total, sem contagem de OS).
_CATEG_EXPR = """
    CASE
      WHEN RTRIM(esp.esp_nome) = 'Analises Clinicas' THEN 'sangue'
      WHEN RTRIM(esp.esp_nome) IN ('Radiologia','Ultrassonografia') THEN 'imagem'
      WHEN sk.SMK_NOME LIKE 'CONSULTA%' THEN 'honorarios'
      WHEN RTRIM(esp.esp_nome) = 'Medicina Ocupacional' THEN 'ocupacional'
      ELSE 'outros'
    END
"""

_NOMES_CATEGORIA = {
    "sangue": "Exames de Sangue",
    "imagem": "Exames de Imagem",
    "honorarios": "Honorários Médicos",
    "ocupacional": "Medicina Ocupacional",
}

# osm.osm_str já guarda o setor real da OS (sem a ambiguidade RPS/ROC que
# existe em fle — ver main.py) — mapeamento direto nome-em-portugues -> cod.
_SETORES_OSM = {
    "ocupacional": "ROC",
    "diagnostico": "RDI",
    "consultorios": "RCN",
    "censo_imagem": "RCI",
    "cmi": "57",
}

# ── Skills: cada uma é uma métrica/consulta já existente no Dashboard ─────
SKILLS = {
    "resumo_operacional": {
        "descricao": (
            "Visão geral operacional: produção em R$, numero de OS, numero de "
            "pacientes, ticket médio, e variação percentual contra o período "
            "anterior equivalente. Use para perguntas gerais sobre produção, "
            "atendimentos ou volume de pacientes."
        ),
        "parametros": {
            "periodo": "string no formato mes:AAAA-MM, 7d, 30d, 90d ou ano",
            "setor": "assistencial | ocupacional | diagnostico | rci | todos (padrao todos)",
        },
    },
    "resumo_financeiro": {
        "descricao": (
            "Faturamento total, ticket médio geral e quebra por tipo de "
            "atendimento (assistencial, admissional, periódico, demissional, "
            "retorno ao trabalho, mudança de função, emergência, cirurgia) e "
            "por situação de faturamento (faturado / em aberto / pendente). "
            "Use para perguntas sobre faturamento, receita total ou situação "
            "de faturamento."
        ),
        "parametros": {"periodo": "string no formato mes:AAAA-MM, 7d, 30d, 90d ou ano"},
    },
    "receita_por_categoria": {
        "descricao": (
            "Receita total e quantidade de OS por categoria de serviço: Exames "
            "de Sangue (Laboratorio/Analises Clinicas), Exames de Imagem "
            "(Radiologia/Ultrassonografia), Honorarios Medicos (consultas) e "
            "Medicina Ocupacional. Use para perguntas sobre receita de uma "
            "categoria de serviço específica em qualquer período."
        ),
        "parametros": {"periodo": "string no formato mes:AAAA-MM, 7d, 30d, 90d ou ano"},
    },
    "ticket_medio_categoria": {
        "descricao": (
            "Ticket médio (valor médio por OS) e quantidade de atendimentos de "
            "UMA categoria especifica de servico. Use para perguntas do tipo "
            "'qual o ticket medio de exames de sangue'."
        ),
        "parametros": {
            "categoria": "sangue | imagem | honorarios | ocupacional",
            "periodo": "string no formato mes:AAAA-MM, 7d, 30d, 90d ou ano",
        },
    },
    "listar_atendimentos": {
        "descricao": (
            "Lista nominal de pacientes atendidos (com OS aberta) em um setor "
            "de recepção, num período. Use para perguntas do tipo 'lista de "
            "pacientes atendidos hoje na recepção ocupacional' ou 'quem foi "
            "atendido no diagnóstico essa semana'."
        ),
        "parametros": {
            "setor": "ocupacional | diagnostico | consultorios | censo_imagem | cmi",
            "periodo": "string no formato mes:AAAA-MM, hoje, 7d, 30d, 90d ou ano",
        },
    },
    "medicos_agenda_hoje": {
        "descricao": (
            "Agenda de hoje (manhã/tarde): marcações, atendidos e faltantes. "
            "SEM o parâmetro 'medico', traz todos os médicos do dia e o total "
            "geral. COM 'medico', filtra e traz SÓ os números daquele médico "
            "(nunca confundir com o total geral de todos). Use para perguntas "
            "do tipo 'quais médicos têm agenda hoje', 'quantos médicos estão "
            "atendendo hoje' ou 'quantos pacientes tem a Dra. X hoje'."
        ),
        "parametros": {"medico": "nome ou parte do nome do médico (opcional — omitir pra trazer todos)"},
    },
    "previsao_producao_dia": {
        "descricao": (
            "Previsão do faturamento/produção de HOJE, combinando o que já "
            "foi faturado com o que ainda está agendado (Consultórios) e a "
            "média histórica do mesmo dia da semana (demais recepções). Use "
            "para perguntas do tipo 'qual a previsão de produção do dia' ou "
            "'quanto devemos faturar hoje'."
        ),
        "parametros": {},
    },
    "previsao_producao_ano": {
        "descricao": (
            "Previsão de produção/faturamento pro restante do ano (total "
            "geral da clínica), baseada em sazonalidade histórica por mês. "
            "Use para perguntas do tipo 'qual a previsão de produção do ano' "
            "ou 'quanto vamos faturar esse ano', SEM menção a um setor/"
            "recepção específico."
        ),
        "parametros": {"ano": "ano no formato AAAA (padrao o ano corrente)"},
    },
    "atendimentos_por_setor": {
        "descricao": (
            "Quantidade de atendimentos (OS abertas) em CADA um dos 5 setores "
            "de recepção (Ocupacional, Consultórios, Diagnóstico, Censo "
            "Imagem, CMI), lado a lado, num período. Use para perguntas do "
            "tipo 'quantos atendimentos por recepção' ou 'divida os "
            "atendimentos por setor', sem pedir um setor específico."
        ),
        "parametros": {"periodo": "string no formato mes:AAAA-MM, hoje, 7d, 30d, 90d ou ano"},
    },
    "previsao_producao_ano_por_setor": {
        "descricao": (
            "Previsão de produção/faturamento pro restante do ano, SEGREGADA "
            "por CADA um dos 5 setores de recepção (Ocupacional, "
            "Consultórios, Diagnóstico, Censo Imagem, CMI). Use quando a "
            "pergunta pedir a previsão anual DIVIDIDA/SEGREGADA por setor ou "
            "recepção, em vez do total geral."
        ),
        "parametros": {"ano": "ano no formato AAAA (padrao o ano corrente)"},
    },
    "horarios_disponiveis": {
        "descricao": (
            "Horários disponíveis pra agendamento, por especialidade médica -- "
            "agrupado por médico e data. Use para perguntas do tipo 'tem "
            "horário de cardiologia essa semana' ou 'quais horários tem "
            "disponível pra pediatria'. Isso é consulta de disponibilidade -- "
            "NÃO agenda nada de verdade. Se o usuário perguntar de novo sobre "
            "a MESMA especialidade só mudando o período (ex: 'e semana que "
            "vem?', 'e mês que vem?'), chame de novo com o mesmo "
            "'especialidade' e o novo 'periodo'."
        ),
        "parametros": {
            "especialidade": "nome da especialidade (ex: cardiologia, pediatria, ginecologia, ortopedia)",
            "periodo": "proximos_30_dias (padrao) | essa_semana | semana_que_vem | mes_que_vem",
        },
    },
    "horarios_disponiveis_medico": {
        "descricao": (
            "Horários disponíveis pra agendamento de UM OU MAIS médicos "
            "específicos (busca por nome), com destaque pro PRÓXIMO horário "
            "livre de cada um. Use para perguntas do tipo 'quando o Dr. "
            "Fulano tem vaga' ou 'próximo horário da Dra. Fulana'. "
            "IMPORTANTE -- se a pergunta citar DOIS OU MAIS médicos pra "
            "comparar (ex: 'tem vaga com o Dr. X ou a Dra. Y', 'quem tem "
            "horario mais cedo, X ou Y'), voce DEVE colocar os nomes de "
            "TODOS eles numa unica chamada, separados por virgula, no MESMO "
            "parametro 'nome' (ex: \"Joao Silva, Maria Souza\") -- NUNCA "
            "escolha so um dos nomes citados e ignore o outro. Se o usuário "
            "perguntar de novo sobre o(s) MESMO(S) médico(s) só mudando o "
            "período (ex: 'e semana que vem?', 'e mês que vem?'), chame de "
            "novo com o mesmo 'nome' e o novo 'periodo'. Isso é consulta de "
            "disponibilidade -- NÃO agenda nada de verdade."
        ),
        "parametros": {
            "nome": "nome(s) do(s) medico(s) -- varios nomes SEMPRE juntos, separados por virgula, numa unica chamada quando a pergunta citar mais de um",
            "periodo": "proximos_30_dias (padrao) | essa_semana | semana_que_vem | mes_que_vem",
        },
    },
    "profissionais_por_especialidade": {
        "descricao": (
            "Lista de TODOS os profissionais/médicos de uma especialidade que "
            "atendem na clínica, independente de ter horário vago nos "
            "próximos dias (é um cadastro/diretório, não disponibilidade). "
            "Use para perguntas do tipo 'quais psicólogos atendem aqui', "
            "'quais profissionais de psicologia a clínica tem' -- diferente "
            "de perguntar sobre VAGA/horário disponível (aí use "
            "horarios_disponiveis)."
        ),
        "parametros": {"especialidade": "nome da especialidade (ex: psicologia, cardiologia, pediatria)"},
    },
}

# Schema de function-calling de verdade (OpenAI "tools") gerado a partir do
# SKILLS acima — permite o modelo escolher a ferramenta e os argumentos de
# forma estruturada, em vez de confiar em JSON solto no texto da resposta
# (mais robusto conforme o catálogo cresce além de 4-5 entradas).
def _tools_openai() -> list:
    tools = []
    for nome, info in SKILLS.items():
        props = {}
        required = []
        for p_nome, p_desc in info["parametros"].items():
            enum = None
            if "|" in p_desc and p_nome in ("setor", "categoria"):
                enum = [v.strip().split(" ")[0] for v in p_desc.split("|")]
            prop = {"type": "string", "description": p_desc}
            if enum:
                prop["enum"] = enum
            props[p_nome] = prop
            if p_nome in ("periodo", "especialidade", "nome"):
                required.append(p_nome)
        tools.append({
            "type": "function",
            "function": {
                "name": nome,
                "description": info["descricao"],
                "parameters": {"type": "object", "properties": props, "required": required},
            },
        })
    return tools

_SISTEMA_INTERPRETACAO = """Voce e a CIA (Censo + IA), assistente da Clinica Censo (ICDS). Voce conversa \
livremente sobre QUALQUER assunto, como um assistente normal (ChatGPT-style) \
-- bate-papo, duvidas gerais, perguntas pessoais, qualquer coisa. Mantenha o \
fio da conversa usando o historico de mensagens anteriores que vier junto.

Fale com jeito e expressoes de gaucho (Rio Grande do Sul): use "tche", "bah", \
"tri" (ex: "tri bom"), "capaz" (duvida), cumprimentos tipo "e ai, tche" -- um \
jeito mais direto e caloroso de falar, sem exagerar a ponto de ficar dificil \
de entender ou virar caricatura. Use isso tanto no bate-papo quanto ao \
responder com dados -- so nao deixe isso atrapalhar a clareza dos numeros.

Quando a pergunta puder ser respondida com dados REAIS do Dashboard da \
clinica, pare e chame UMA das ferramentas abaixo em vez de responder direto \
-- NUNCA invente numeros, estatisticas ou indicadores da clinica por conta \
propria. Se parecer uma pergunta sobre dado da clinica mas nenhuma ferramenta \
cobrir exatamente o que foi pedido, diga com honestidade que ainda nao tem \
acesso a esse dado especifico (em vez de inventar ou de chamar a ferramenta \
errada). Pra qualquer outro assunto (nao relacionado a dados da clinica), \
responda normalmente, em portugues, de forma natural e conversacional -- sem \
mencionar "ferramentas" ou "Dashboard" nessas respostas.

Data de hoje: {hoje}
{linha_nome_usuario}
IMPORTANTE: ao chamar uma ferramenta, use OBRIGATORIAMENTE o ano da data de \
hoje acima quando a pergunta citar um mes sem especificar o ano (ex: \
"outubro" sozinho = outubro do ano de hoje, NAO um ano do seu conhecimento \
de treinamento). Nunca gere um ano anterior a 2025 a nao ser que o usuario \
tenha digitado esse ano explicitamente.

Regras pro campo "periodo" (quando a ferramenta tiver esse parametro):
- Mes especifico citado por nome (ex: "outubro", "em setembro") -> "mes:AAAA-MM" (use o ano corrente se nao for citado)
- "esse mes"/"este mes" -> mes atual, "mes:AAAA-MM"
- "mes passado" -> mes anterior ao atual, "mes:AAAA-MM"
- "hoje" -> "hoje"
- "essa semana"/"ultimos 7 dias" -> "7d"
- "esse ano" -> "ano"
- Nenhum periodo citado -> "30d" (padrao, mes corrente ate hoje)
"""


def interpretar_pergunta(pergunta: str, historico: list = None, usuario_nome: str = "") -> dict:
    """Usa function-calling de verdade (OpenAI "tools") em vez de pedir JSON
    solto no texto -- mais confiavel conforme o catalogo de ferramentas
    cresce (o usuario pediu explicitamente pra nao ficar travado num punhado
    fixo de skills financeiras). Quando nenhuma ferramenta e chamada, o
    proprio conteudo da resposta do modelo vira a resposta conversacional
    (modo "ChatGPT", por pedido explicito do usuario) -- historico de
    mensagens anteriores entra na conversa pra manter o contexto entre
    perguntas (ver Jarvis.jsx, que guarda e reenvia o historico). usuario_nome
    vem do primeiro nome do usuario logado (sessionStorage "censo_user" no
    front), pra poder chamar a pessoa pelo nome na conversa."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return {"skill": None, "parametros": {}, "entendimento": "Configure a variavel OPENAI_API_KEY no servidor."}

    hoje = datetime.now().strftime("%Y-%m-%d (%A)")
    linha_nome_usuario = (
        f'Nome do usuario conversando: {usuario_nome}. Chame-o pelo nome logo no '
        f'cumprimento/primeira frase da conversa -- depois disso, so de vez em '
        f'quando, sem repetir em toda frase (fica forcado).'
        if usuario_nome else ""
    )
    system = _SISTEMA_INTERPRETACAO.format(hoje=hoje, linha_nome_usuario=linha_nome_usuario)
    mensagens = [{"role": "system", "content": system}]
    for turno in (historico or [])[-10:]:
        papel = "assistant" if turno.get("papel") == "assistant" else "user"
        texto = (turno.get("texto") or "").strip()
        if texto:
            mensagens.append({"role": papel, "content": texto})
    mensagens.append({"role": "user", "content": pergunta})
    try:
        res = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": OPENAI_MODEL,
                "max_tokens": 600,
                "temperature": 0.4,
                "messages": mensagens,
                "tools": _tools_openai(),
                "tool_choice": "auto",
            },
            timeout=30,
        )
        msg = res.json()["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return {
                "skill": None, "parametros": {},
                "entendimento": msg.get("content") or "Desculpa, nao consegui responder isso agora.",
            }
        call = tool_calls[0]["function"]
        parametros = json.loads(call.get("arguments") or "{}")
        return {"skill": call["name"], "parametros": parametros, "entendimento": None}
    except Exception as e:
        return {"skill": None, "parametros": {}, "entendimento": f"Erro ao interpretar a pergunta: {e}"}


def _corrigir_ano_periodo(periodo: str, pergunta: str) -> str:
    """Salvaguarda contra o LLM "chutar" o ano errado pra um mês citado sem
    ano (confirmado na prática: gpt-4o-mini devolveu 2023 pra "outubro" com a
    data de hoje passada certinha no prompt — viés do próprio conhecimento de
    treinamento do modelo). Não confia no LLM pro ano: se a pergunta não citar
    um ano de 4 dígitos explicitamente, recalcula aqui de forma determinística."""
    if not periodo or not periodo.startswith("mes:"):
        return periodo
    m = re.match(r"^mes:(\d{4})-(\d{2})$", periodo)
    if not m:
        return periodo
    mes = int(m.group(2))
    if re.search(r"\b(19|20)\d{2}\b", pergunta):
        return periodo  # ano citado explicitamente na pergunta — respeita
    now = datetime.now()
    ano_corrigido = now.year
    if mes > now.month:
        ano_corrigido -= 1  # mes ainda nao chegou neste ano -> deve ser o ano passado
    return f"mes:{ano_corrigido}-{mes:02d}"


def _receita_por_categoria(periodo: str) -> dict:
    """Receita + contagem de OS por categoria de servico, pra QUALQUER
    periodo (7d/30d/90d/ano/mes:/custom:) -- ao contrario de
    /api/financeiro/receita-por-tipo-servico (main.py), que só aceita um mês
    inteiro (ano+mes_ini+mes_fim), essa versão reusa a mesma classificação
    (_CATEG_EXPR) mas com periodo_datas(), pra não dar resultado errado
    quando o usuário pede algo como "últimos 7 dias" (bug real confirmado:
    a versão anterior ignorava period fora do formato mes: e computava o
    mês inteiro em silêncio)."""
    from main import query, periodo_datas

    inicio, fim = periodo_datas(periodo)

    row_total = query(f"""
        SELECT SUM({_VLIQ}) AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
    """)
    total_geral = round(float(row_total[0]["total"] or 0), 2) if row_total else 0.0

    rows = query(f"""
        SELECT {_CATEG_EXPR}                        AS categ,
               SUM({_VLIQ})                          AS total,
               COUNT(DISTINCT smm.SMM_OSM)            AS total_os
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
        JOIN esp ON esp.esp_cod = sk.SMK_ESP_COD
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY {_CATEG_EXPR}
    """)
    por_categ = {r["categ"]: r for r in rows}

    itens = []
    soma_categorizada = 0.0
    for cod, nome in _NOMES_CATEGORIA.items():
        d = por_categ.get(cod) or {}
        total = round(float(d.get("total") or 0), 2)
        soma_categorizada += total
        itens.append({"categoria": cod, "categoria_nome": nome, "total": total, "total_os": int(d.get("total_os") or 0)})
    outros_d = por_categ.get("outros") or {}
    itens.append({
        "categoria": "outros", "categoria_nome": "Outros",
        "total": round(total_geral - soma_categorizada, 2),
        "total_os": int(outros_d.get("total_os") or 0),
    })

    return {"periodo": periodo, "total_geral": total_geral, "itens": itens}


def _ticket_medio_categoria(categoria: str, periodo: str) -> dict:
    from main import query, periodo_datas

    if categoria not in _NOMES_CATEGORIA:
        categoria = "sangue"
    inicio, fim = periodo_datas(periodo)
    rows = query(f"""
        SELECT
            COUNT(DISTINCT smm.SMM_OSM)                                 AS total_os,
            SUM({_VLIQ})                                                AS total,
            SUM({_VLIQ}) / NULLIF(COUNT(DISTINCT smm.SMM_OSM), 0)       AS ticket_medio
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
        JOIN esp ON esp.esp_cod = sk.SMK_ESP_COD
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
          AND {_CATEG_EXPR} = '{categoria}'
    """)
    r = rows[0] if rows else {}
    return {
        "categoria": categoria,
        "categoria_nome": _NOMES_CATEGORIA[categoria],
        "periodo": periodo,
        "total_os": int(r.get("total_os") or 0),
        "total": round(float(r.get("total") or 0), 2),
        "ticket_medio": round(float(r.get("ticket_medio") or 0), 2),
    }


def _listar_atendimentos(setor: str, periodo: str) -> dict:
    """Lista nominal (não agregada) de pacientes com OS aberta num setor —
    complementa as skills financeiras com uma consulta operacional/clínica
    de verdade, por pedido explícito do usuário ("não só essas 4 skills")."""
    from main import query, periodo_datas

    cod = _SETORES_OSM.get(setor, (setor or "").upper())
    inicio, fim = periodo_datas(periodo)
    rows = query(f"""
        SELECT TOP 200
            RTRIM(pac.pac_nome)                 AS paciente,
            CONVERT(VARCHAR(16), osm.osm_dthr, 120) AS data_hora,
            RTRIM(ISNULL(cnv.cnv_nome, ''))      AS convenio,
            RTRIM(ISNULL(psv.psv_apel, ''))      AS profissional
        FROM osm
        JOIN pac ON pac.pac_reg = osm.osm_pac
        LEFT JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        LEFT JOIN psv ON psv.psv_cod = osm.osm_mreq
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND RTRIM(osm.osm_str) = '{cod}'
        ORDER BY osm.osm_dthr
    """)
    for r in rows:
        if r.get("paciente"):
            r["paciente"] = str(r["paciente"]).strip().title()
    return {"setor": setor, "periodo": periodo, "total_atendimentos": len(rows), "atendimentos": rows}


def _normalizar_nome(s: str) -> str:
    """Colapsa letras duplicadas consecutivas (GEOVANNA -> GEOVANA, BITTENCOURT
    -> BITENCOURT) pra tolerar a grafia que vem da voz/STT ou de como o
    usuário lembra o nome ser diferente da grafia exata no Smart -- bug real
    confirmado: "Geovana Bittencourt" não batia com "GEOVANNA BITENCOURT" no
    banco por causa dessa troca de letra dobrada."""
    s = (s or "").strip().upper()
    return re.sub(r"(.)\1+", r"\1", s)


def _medicos_agenda_hoje(medico: str = "") -> dict:
    from main import agendamentos_resumo_hoje
    r = agendamentos_resumo_hoje()
    stats = r.get("stats") or {}
    medicos = [
        {"medico": m.get("medico"), "turno": m.get("turno"), "hora_inicio": m.get("hora_inicio"),
         "hora_fim": m.get("hora_fim"), "marcacoes": m.get("marcacoes"), "atendidos": m.get("atendidos"),
         "faltantes": m.get("faltantes")}
        for m in (r.get("medicos_hoje") or [])
    ]

    termo = (medico or "").strip()

    # Se a pessoa falar o código do médico (psv_cod) em vez do nome, busca o
    # nome dele no Smart primeiro e reusa a mesma busca por nome abaixo --
    # os dados de agenda de hoje não trazem o código, só o nome/apelido.
    if termo.isdigit():
        from main import query
        encontrado_por_cod = query("SELECT RTRIM(psv_apel) AS apelido FROM psv WHERE psv_cod = ?", (int(termo),))
        if encontrado_por_cod:
            termo = encontrado_por_cod[0]["apelido"]

    if termo:
        # Pergunta sobre UM médico específico -- filtra a lista e recalcula
        # os totais só dele (bug real confirmado: sem esse filtro, o Jarvis
        # respondia com o agregado de TODOS os médicos quando perguntado
        # sobre um médico específico, ex. "quantos pacientes pra Dra. X" ->
        # respondia o total geral de 94, não os 26 dela).
        palavras_termo = _normalizar_nome(termo).split()
        encontrados = [
            m for m in medicos
            if all(p in _normalizar_nome(m["medico"] or "") for p in palavras_termo)
        ]
        if encontrados:
            return {
                "medico_buscado": medico,
                "encontrado": True,
                "marcacoes": sum(m["marcacoes"] or 0 for m in encontrados),
                "atendidos": sum(m["atendidos"] or 0 for m in encontrados),
                "faltantes": sum(m["faltantes"] or 0 for m in encontrados),
                "turnos": encontrados,
            }
        return {"medico_buscado": medico, "encontrado": False, "medicos_disponiveis_hoje": [m["medico"] for m in medicos]}

    return {
        "marcacoes": int(stats.get("marcacoes") or 0),
        "atendidos": int(stats.get("atendidos") or 0),
        "faltantes": int(stats.get("faltantes") or 0),
        "cancelados": int(stats.get("cancelados") or 0),
        "medicos_com_agenda": int(stats.get("medicos_agenda") or 0),
        "medicos": medicos,
    }


def _previsao_producao_dia() -> dict:
    from main import previsao_faturamento_hora
    r = previsao_faturamento_hora()
    nomes_setor = {s["cod"]: s["nome"] for s in (r.get("recepcoes") or [])}

    # previsao_faturamento_hora() já calcula por_recepcao EM CADA hora (mistura
    # real, pras horas que já passaram, com previsão, pras horas futuras) --
    # só faltava somar isso ao longo do dia pra virar "previsão do dia por
    # setor". A versão anterior descartava essa segregação e só expunha o
    # agregado total -- por isso o Jarvis não conseguia responder "por setor"
    # (bug real reportado pelo usuário).
    previsto_por_setor = {cod: 0.0 for cod in nomes_setor}
    for h in (r.get("horas") or []):
        for cod, valor in (h.get("por_recepcao") or {}).items():
            if cod in previsto_por_setor:
                previsto_por_setor[cod] += valor

    return {
        "total_dia_real": r.get("total_dia_real"),
        "total_dia_previsto": r.get("total_dia_previsto"),
        "aviso": r.get("aviso"),
        "previsto_por_recepcao": [
            {"setor": cod, "setor_nome": nomes_setor.get(cod, cod), "previsto": round(v, 2)}
            for cod, v in previsto_por_setor.items()
        ],
        "por_hora": [
            {"hora": h["hora"], "real": h["real_total"], "previsto": h["previsao_total"]}
            for h in (r.get("horas") or [])
        ],
    }


#  previsao_anual() (main.py) é uma query pesada (histórico de vários anos de
# smm+osm) -- confirmado que leva ~40-55s independente do tamanho da janela
# histórica pedida (não escala com anos_historico, então não é o volume de
# dados -- provável falta de índice, fora do escopo do Jarvis mexer). Sem
# cache, toda pergunta sobre previsão anual estourava o timeout do cliente.
# A previsão muda pouco ao longo do dia, então cache de 1h (mesmo TTL já
# usado em financeiro_recordes, em main.py, pro mesmo tipo de métrica).
_PREVISAO_ANO_CACHE = {}
_PREVISAO_ANO_TTL = 3600

def _atendimentos_por_setor(periodo: str) -> dict:
    """Contagem de OS por setor de recepção, lado a lado -- osm.osm_str já
    guarda o setor real (sem a ambiguidade RPS/ROC que existe em fle)."""
    from main import query, periodo_datas, RECEPCOES

    inicio, fim = periodo_datas(periodo)
    rows = query(f"""
        SELECT RTRIM(osm.osm_str) AS setor, COUNT(*) AS total
        FROM osm
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND RTRIM(osm.osm_str) IN ('RDI','ROC','RCN','RCI','57')
        GROUP BY RTRIM(osm.osm_str)
    """)
    por_setor = {r["setor"]: int(r["total"]) for r in rows}
    return {
        "periodo": periodo,
        "setores": [
            {"setor": cod, "setor_nome": nome, "atendimentos": por_setor.get(cod, 0)}
            for cod, nome in RECEPCOES.items()
        ],
    }


# Mesmo motivo do cache de previsao_anual (ver acima): producao_mensal_por_setor
# (main.py) tambem e uma query de varios anos de historico, e aqui e chamada
# 5x seguidas (uma por setor) -- sem cache, cada pergunta levaria ~10-15s.
_PREVISAO_ANO_SETOR_CACHE = {}

def _janela_datas(periodo: str):
    """Calcula (inicio, fim) pros termos de seguimento que vem dessa tela
    ("e semana que vem?", "e mes que vem?") -- periodo_datas() (main.py) não
    cobre "semana que vem"/"mes que vem" (só período RETROATIVO a partir de
    hoje), e essas duas são exatamente o tipo de pergunta de seguimento que o
    usuário reportou não funcionar (ficava sempre repetindo o mesmo "próximo
    horário", porque as ferramentas de disponibilidade não tinham NENHUM jeito
    de restringir a janela de busca)."""
    import calendar as _cal
    now = datetime.now()

    if periodo == "essa_semana":
        inicio = now
        fim = now + timedelta(days=(6 - now.weekday()))
        return inicio.strftime("%Y-%m-%d"), fim.strftime("%Y-%m-%d")

    if periodo == "semana_que_vem":
        inicio_semana_atual = now - timedelta(days=now.weekday())
        inicio = inicio_semana_atual + timedelta(days=7)
        fim = inicio + timedelta(days=6)
        return inicio.strftime("%Y-%m-%d"), fim.strftime("%Y-%m-%d")

    if periodo == "mes_que_vem":
        mes, ano = now.month + 1, now.year
        if mes > 12:
            mes, ano = 1, ano + 1
        ultimo = _cal.monthrange(ano, mes)[1]
        return f"{ano}-{mes:02d}-01", f"{ano}-{mes:02d}-{ultimo}"

    # "proximos_30_dias" (padrao) ou qualquer outra coisa nao reconhecida
    return now.strftime("%Y-%m-%d"), (now + timedelta(days=30)).strftime("%Y-%m-%d")


def _filtrar_janela(proximas_datas: list, inicio: str, fim: str) -> list:
    return [d for d in (proximas_datas or []) if inicio <= (d.get("data") or "") <= fim]


def _horarios_disponiveis(especialidade: str, periodo: str = "") -> dict:
    """Reaproveita buscar_disponibilidade_especialidade() (main.py), já usada
    pelo frontend de Agenda e pelo bot de WhatsApp -- não precisa da API
    externa AgendaSmart (que ficou travada na autenticação, formato de header
    não documentado) pra responder "tem horário disponível", já que o
    Dashboard já le essa mesma informação direto do Smart (view EX_HORARIOS).
    Busca com uma janela ampla (60 dias / 15 datas) e filtra pro período
    pedido depois -- sem isso, perguntas de seguimento tipo "e mês que vem?"
    não tinham como ser respondidas (bug real reportado pelo usuário: a CIA
    so repetia sempre a mesma 1a resposta, porque não existia nenhum jeito de
    restringir a busca a uma janela diferente)."""
    from main import buscar_disponibilidade_especialidade

    especialidade = (especialidade or "").strip()
    if not especialidade:
        return {"especialidade_buscada": especialidade, "encontrada": False, "horarios": []}

    inicio, fim = _janela_datas(periodo)
    r = buscar_disponibilidade_especialidade(especialidade, dias=60, limite_datas=15)
    linhas = []
    for m in (r.get("medicos") or [])[:10]:
        for d in _filtrar_janela(m.get("proximas_datas"), inicio, fim):
            horarios_dia = d.get("horarios") or []
            linhas.append({
                "medico": m.get("medico_nome"),
                "data": d.get("data"),
                "primeiro_horario": horarios_dia[0] if horarios_dia else None,
                "total_horarios_no_dia": len(horarios_dia),
                "horarios": ", ".join(horarios_dia),
            })
    return {
        "especialidade_buscada": r.get("especialidade_buscada", especialidade),
        "periodo_consultado": periodo or "proximos_30_dias",
        "encontrada": len(linhas) > 0,
        "horarios": linhas,
    }


_CACHE_APELIDOS_MEDICOS = {"lista": None, "ts": 0.0}
_CACHE_APELIDOS_TTL = 3600  # nomes de médico mudam raramente -- 1h é de sobra

def _resolver_nome_medico(termo: str) -> str:
    """Resolve o nome falado/digitado pro apelido EXATO cadastrado no Smart,
    tolerando nome composto fora de ordem e pequena variação de grafia (mesma
    normalização usada em medicos_agenda_hoje). Sem isso, buscar "Guilherme
    Steinmetz" não batia com "GUILHERME VERNASCHI STEINMTZ" no banco -- tem
    nome do meio e falta uma letra no sobrenome (bug real confirmado:
    buscar_disponibilidade_medico, em main.py, faz só um LIKE do termo
    inteiro, que falha nesses dois casos ao mesmo tempo)."""
    termo = (termo or "").strip()
    if not termo:
        return termo

    agora = time.time()
    if _CACHE_APELIDOS_MEDICOS["lista"] is None or agora - _CACHE_APELIDOS_MEDICOS["ts"] > _CACHE_APELIDOS_TTL:
        from main import query
        _CACHE_APELIDOS_MEDICOS["lista"] = [
            r["apelido"] for r in query("SELECT DISTINCT RTRIM(psv_apel) AS apelido FROM psv WHERE psv_apel IS NOT NULL")
        ]
        _CACHE_APELIDOS_MEDICOS["ts"] = agora

    palavras_termo = _normalizar_nome(termo).split()

    def bate(apelido: str) -> bool:
        # Tolera letra faltando/trocada/duplicada por palavra (ex: STEINMETZ
        # falado vs STEINMTZ cadastrado no Smart -- diferença de 1 letra no
        # meio, que _normalizar_nome sozinho não resolve, só duplicata).
        palavras_cand = _normalizar_nome(apelido).split()
        return all(
            any(difflib.SequenceMatcher(None, pt, pc).ratio() >= 0.8 for pc in palavras_cand)
            for pt in palavras_termo
        )

    candidatos = [a for a in _CACHE_APELIDOS_MEDICOS["lista"] if bate(a)]
    return candidatos[0] if len(candidatos) == 1 else termo


def _horarios_disponiveis_um_medico(nome: str, inicio: str, fim: str) -> dict:
    from main import buscar_disponibilidade_medico

    nome_resolvido = _resolver_nome_medico(nome)
    r = buscar_disponibilidade_medico(nome_resolvido, dias=60, limite_datas=15)
    linhas = []
    proximo = None
    for m in (r.get("medicos") or []):
        for d in _filtrar_janela(m.get("proximas_datas"), inicio, fim):
            horarios_dia = d.get("horarios") or []
            if proximo is None and horarios_dia:
                proximo = {"medico": m.get("medico_nome"), "data": d.get("data"), "horario": horarios_dia[0]}
            linhas.append({
                "medico": m.get("medico_nome"),
                "data": d.get("data"),
                "primeiro_horario": horarios_dia[0] if horarios_dia else None,
                "total_horarios_no_dia": len(horarios_dia),
                "horarios": ", ".join(horarios_dia),
            })
    return {
        "medico_buscado": nome,
        "encontrado": len(linhas) > 0,
        "proximo_horario": proximo,
        "horarios": linhas,
    }


def _horarios_disponiveis_medico(nome: str, periodo: str = "") -> dict:
    """Reaproveita buscar_disponibilidade_medico() (main.py) -- mesma ideia de
    _horarios_disponiveis(), mas buscando por médico específico em vez de
    especialidade. "proximo_horario" vem como campo separado, destacado, pra
    a resposta falada liderar com isso em vez de só listar tudo. Aceita VÁRIOS
    nomes separados por vírgula/" e "/" ou " pra comparar mais de um médico
    na mesma pergunta (bug real reportado: "tem vaga com o Dr. X ou a Dra. Y"
    não funcionava, só dava pra perguntar de um de cada vez)."""
    nome = (nome or "").strip()
    if not nome:
        return {"medico_buscado": nome, "encontrado": False, "proximo_horario": None, "horarios": []}

    inicio, fim = _janela_datas(periodo)
    # Só separa por "," e " ou " (nao por " e " -- sobrenome composto tipo
    # "Costa e Silva" existe de verdade e seria quebrado ao meio).
    nomes = [n.strip() for n in re.split(r",| ou ", nome, flags=re.IGNORECASE) if n.strip()]
    if len(nomes) <= 1:
        resultado = _horarios_disponiveis_um_medico(nome, inicio, fim)
        resultado["periodo_consultado"] = periodo or "proximos_30_dias"
        return resultado

    comparativo = [_horarios_disponiveis_um_medico(n, inicio, fim) for n in nomes]
    return {
        "medico_buscado": nome,
        "periodo_consultado": periodo or "proximos_30_dias",
        "encontrado": any(c["encontrado"] for c in comparativo),
        "comparativo": [
            {"medico_buscado": c["medico_buscado"], "encontrado": c["encontrado"], "proximo_horario": c["proximo_horario"]}
            for c in comparativo
        ],
        "horarios": [linha for c in comparativo for linha in c["horarios"]],
    }


def _profissionais_por_especialidade(especialidade: str) -> dict:
    """Diretório de profissionais de uma especialidade -- diferente de
    horarios_disponiveis (que só lista quem tem vaga nos próximos dias), essa
    cobre a pergunta genérica "quais psicólogos atendem aqui", que ficava sem
    resposta (bug real reportado: perguntar "quais profissionais de
    psicologia" não tinha NENHUMA ferramenta correspondente -- só existiam
    ferramentas de disponibilidade, que dão lista vazia se ninguém tiver vaga
    no momento, mesmo que existam profissionais cadastrados)."""
    from main import query

    especialidade = (especialidade or "").strip()
    if not especialidade:
        return {"especialidade_buscada": especialidade, "encontrada": False, "total": 0, "profissionais": []}

    rows = query("""
        SELECT DISTINCT RTRIM(psv.psv_apel) AS nome, RTRIM(v.especialidade) AS especialidade
        FROM V_ESP_MEDICO v
        JOIN psv ON psv.psv_cod = v.medico
        WHERE UPPER(v.especialidade) LIKE ?
        ORDER BY RTRIM(psv.psv_apel)
    """, (f"%{especialidade.upper()}%",))

    return {
        "especialidade_buscada": especialidade,
        "encontrada": len(rows) > 0,
        "total": len(rows),
        "profissionais": rows,
    }


def _previsao_producao_ano_por_setor(ano) -> dict:
    """Mesma decomposição sazonal clássica de previsao_anual() (main.py) --
    índice sazonal por mês x nível de tendência do ano corrente -- mas
    calculada aqui em Python sobre UMA única consulta cobrindo os 5 setores
    de uma vez. Chamar previsao_anual(setor=X) 5x seria 5x a mesma query
    lenta (~45s cada, confirmado que NÃO escala com filtro/volume -- é algo
    estrutural da query, não do tamanho do resultado) = minutos de espera."""
    from main import query, RECEPCOES

    ano_int = None
    if ano:
        try: ano_int = int(ano)
        except (TypeError, ValueError): pass
    chave = ano_int or "atual"

    agora = time.time()
    cache = _PREVISAO_ANO_SETOR_CACHE.get(chave)
    if cache and agora - cache["ts"] < _PREVISAO_ANO_TTL:
        return cache["dados"]

    now = datetime.now()
    ano_calc = ano_int or now.year
    anos_historico = 4

    rows = query(f"""
        SELECT YEAR(osm.osm_dthr) AS ano, MONTH(osm.osm_dthr) AS mes,
               RTRIM(osm.osm_str) AS setor,
               SUM({_VLIQ}) AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        WHERE osm.osm_dthr >= DATEADD(year, -{anos_historico + 1}, GETDATE())
          AND smm.SMM_SFAT IN ('A','F','P')
          AND RTRIM(osm.osm_str) IN ('RDI','ROC','RCN','RCI','57')
        GROUP BY YEAR(osm.osm_dthr), MONTH(osm.osm_dthr), RTRIM(osm.osm_str)
    """)

    mes_atual = now.month if ano_calc == now.year else 13
    meses_fechados = list(range(1, mes_atual))

    setores_resultado = []
    for cod in RECEPCOES:
        linhas = [r for r in rows if r["setor"] == cod]
        producao_ano_atual = {r["mes"]: float(r["total"] or 0) for r in linhas if r["ano"] == ano_calc}
        historico_por_mes = {m: [] for m in range(1, 13)}
        for r in linhas:
            if r["ano"] != ano_calc:
                historico_por_mes[r["mes"]].append(float(r["total"] or 0))

        # Setor novo (ex: CMI) pode não ter histórico nenhum ainda -- cai no
        # fallback (indice sazonal neutro) em vez de dividir por zero.
        valores_hist = [v for vs in historico_por_mes.values() for v in vs]
        media_geral_historico = sum(valores_hist) / len(valores_hist) if valores_hist else 0

        indice_sazonal = {}
        for m in range(1, 13):
            vals = historico_por_mes[m]
            media_mes = sum(vals) / len(vals) if vals else media_geral_historico
            indice_sazonal[m] = round(media_mes / media_geral_historico, 4) if media_geral_historico else 1.0

        niveis = [producao_ano_atual.get(m, 0) / indice_sazonal[m] for m in meses_fechados if indice_sazonal[m] > 0]
        nivel_tendencia = sum(niveis) / len(niveis) if niveis else media_geral_historico

        meses_restantes = [m for m in range(mes_atual, 13)]
        previsao_por_mes = {m: round(nivel_tendencia * indice_sazonal[m], 2) for m in meses_restantes}

        total_ja_produzido = sum(producao_ano_atual.get(m, 0) for m in range(1, mes_atual))
        total_mes_corrente_parcial = producao_ano_atual.get(mes_atual, 0.0) if ano_calc == now.year else 0.0
        total_previsto_restante = sum(previsao_por_mes.values())
        total_projetado_ano = total_ja_produzido + total_mes_corrente_parcial + total_previsto_restante

        setores_resultado.append({
            "setor": cod,
            "setor_nome": RECEPCOES.get(cod, cod),
            "total_ja_produzido": round(total_ja_produzido + total_mes_corrente_parcial, 2),
            "total_previsto_restante": round(total_previsto_restante, 2),
            "total_projetado_ano": round(total_projetado_ano, 2),
        })

    dados = {"ano": ano_calc, "setores": setores_resultado}
    _PREVISAO_ANO_SETOR_CACHE[chave] = {"ts": agora, "dados": dados}
    return dados


def _previsao_producao_ano(ano) -> dict:
    from main import previsao_anual
    kwargs = {}
    if ano:
        try: kwargs["ano"] = int(ano)
        except (TypeError, ValueError): pass
    chave = kwargs.get("ano", "atual")

    agora = time.time()
    cache = _PREVISAO_ANO_CACHE.get(chave)
    if cache and agora - cache["ts"] < _PREVISAO_ANO_TTL:
        return cache["dados"]

    r = previsao_anual(**kwargs)
    dados = {
        "ano": r.get("ano"),
        "total_ja_produzido": r.get("total_ja_produzido"),
        "total_previsto_restante": r.get("total_previsto_restante"),
        "total_projetado_ano": r.get("total_projetado_ano"),
        "meses": r.get("meses"),
    }
    _PREVISAO_ANO_CACHE[chave] = {"ts": agora, "dados": dados}
    return dados


def executar_skill(skill: str, parametros: dict) -> dict:
    from main import financeiro_resumo, home_resumo

    periodo = parametros.get("periodo") or "30d"

    if skill == "resumo_operacional":
        setor = parametros.get("setor") or "todos"
        if setor not in ("assistencial", "ocupacional", "diagnostico", "rci", "todos"):
            setor = "todos"
        r = home_resumo(periodo=periodo, setor=setor)
        return {
            "kpis": r.get("kpis"),
            "kpis_anterior": r.get("kpis_anterior"),
            "variacoes": r.get("variacoes"),
            "setor": setor,
            "periodo": periodo,
        }

    if skill == "resumo_financeiro":
        return financeiro_resumo(periodo=periodo)

    if skill == "receita_por_categoria":
        return _receita_por_categoria(periodo)

    if skill == "ticket_medio_categoria":
        categoria = (parametros.get("categoria") or "").strip().lower()
        return _ticket_medio_categoria(categoria, periodo)

    if skill == "listar_atendimentos":
        setor = (parametros.get("setor") or "").strip().lower()
        return _listar_atendimentos(setor, periodo)

    if skill == "medicos_agenda_hoje":
        return _medicos_agenda_hoje(parametros.get("medico") or "")

    if skill == "previsao_producao_dia":
        return _previsao_producao_dia()

    if skill == "previsao_producao_ano":
        return _previsao_producao_ano(parametros.get("ano"))

    if skill == "atendimentos_por_setor":
        return _atendimentos_por_setor(periodo)

    if skill == "previsao_producao_ano_por_setor":
        return _previsao_producao_ano_por_setor(parametros.get("ano"))

    if skill == "horarios_disponiveis":
        return _horarios_disponiveis(parametros.get("especialidade") or "", parametros.get("periodo") or "")

    if skill == "horarios_disponiveis_medico":
        return _horarios_disponiveis_medico(parametros.get("nome") or "", parametros.get("periodo") or "")

    if skill == "profissionais_por_especialidade":
        return _profissionais_por_especialidade(parametros.get("especialidade") or "")

    raise ValueError(f"Skill desconhecida: {skill}")


def formatar_resposta(pergunta: str, skill: str, parametros: dict, dados: dict) -> str:
    system = (
        "Voce e a CIA, assistente de voz da Clinica Censo (ICDS). Responda a "
        "pergunta do diretor em ate duas frases curtas, diretas, em portugues, "
        "usando SOMENTE os numeros fornecidos nos dados em JSON abaixo -- nunca "
        "invente ou arredonde valores de forma diferente do que foi passado. "
        "NUNCA some, subtraia ou calcule um numero novo a partir de dois "
        "campos dos dados -- se um total ja vem pronto num campo, use esse "
        "campo; se nao vier pronto, NAO tente calcula-lo (erro real ja "
        "confirmado: o modelo somou dois campos incompativeis e falou um "
        "total errado). "
        "Escreva os numeros em ALGARISMOS normais (ex: R$ 1.367.955,20 e 1.723 "
        "ordens de servico) -- NUNCA escreva o numero por extenso em palavras "
        "(nada de 'mil novecentos e vinte'); o texto sera lido em voz alta por "
        "um sintetizador de voz, que ja sabe pronunciar algarismos sozinho. "
        "Valores em reais usam o numero completo, SEMPRE com o prefixo 'R$' "
        "(ex: R$ 772.099,48, nunca so '772.099,48'), nunca abreviado como "
        "'mil' ou 'mi'. Use 'producao' pra volumes/quantidades e 'receita' pra "
        "valores em reais -- nunca a expressao 'receita de producao'. Se os "
        "dados tiverem uma LISTA longa de registros NOMINAIS (ex: lista de "
        "atendimentos/pacientes por nome), NAO leia item por item -- so diga "
        "a contagem total e que a lista esta sendo exibida na tela. "
        "EXCECAO -- pergunta sobre DIAS/HORARIOS DISPONIVEIS (campo "
        "'horarios'): isso e uma lista curta de verdade (poucas datas), e a "
        "pessoa quer OUVIR as datas, nao so ver na tela -- liste cada data "
        "em voz alta usando os campos 'data' + 'primeiro_horario' de cada "
        "item (ex: 'dia 22 de novembro as 9h, dia 23 as 10h30, dia 26 as "
        "8h30'). NUNCA leia o campo 'horarios' (string longa com TODOS os "
        "horarios daquele dia, separados por virgula) em voz alta -- ele e "
        "só pra tela; se quiser mencionar quantos horarios tem num dia, use "
        "o numero do campo 'total_horarios_no_dia' (ex: 'dia 26 tem 13 "
        "horarios livres, o primeiro as 8h30'), nunca enumere todos. Se os "
        "dados tiverem um campo 'proximo_horario' avulso (fora da lista "
        "'horarios'), COMECE a resposta por ele e DEPOIS mencione as demais "
        "datas da lista. Sem markdown, texto corrido. Fale com jeito gaucho "
        "(RS): pode usar "
        "'tche', 'bah', 'tri' etc, mas sem atrapalhar a clareza dos numeros."
    )
    # Listas de horarios/datas de agenda ficam com um limite bem maior (sao
    # curtas de verdade e precisam ser faladas por inteiro -- ver instrucao
    # acima); o corte de 5 itens continua valendo pra listas nominais
    # genuinamente longas (atendimentos/pacientes), que nao devem ser lidas.
    # "profissionais"/"medicos" ficam DE FORA de propósito -- são diretórios
    # que podem ter dezenas de nomes (ex: 61 psicólogos), não devem ser lidos
    # item por item mesmo sendo uma lista "curta" no sentido de agenda.
    _CHAVES_LISTA_LONGA = {"horarios", "comparativo", "meses", "por_hora"}
    dados_resumidos = dados
    if isinstance(dados, dict):
        dados_resumidos = {
            k: (v if k in _CHAVES_LISTA_LONGA or not isinstance(v, list) or len(v) <= 5
                else f"[{len(v)} itens -- ver tela]")
            for k, v in dados.items()
        }
    prompt = (
        f"Pergunta: {pergunta}\n\n"
        f"Skill usada: {skill}\nParametros: {json.dumps(parametros, ensure_ascii=False)}\n"
        f"Dados (unica fonte de verdade, nao use nenhum outro numero):\n"
        f"{json.dumps(dados_resumidos, ensure_ascii=False, default=str)}"
    )
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return "Configure a variavel OPENAI_API_KEY no servidor."
    try:
        res = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": OPENAI_MODEL,
                "max_tokens": 300,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=30,
        )
        return res.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Erro ao formatar a resposta: {e}"


def responder(pergunta: str, historico: list = None, usuario_nome: str = "") -> dict:
    interpretacao = interpretar_pergunta(pergunta, historico, usuario_nome)
    skill = interpretacao.get("skill")
    parametros = interpretacao.get("parametros") or {}
    if "periodo" in parametros:
        parametros["periodo"] = _corrigir_ano_periodo(parametros["periodo"], pergunta)

    if not skill or skill not in SKILLS:
        # Sem ferramenta chamada -> o proprio texto do modelo JA E a resposta
        # conversacional (modo "converse sobre qualquer coisa", nao mais um
        # erro de "nao identificado" -- ver _SISTEMA_INTERPRETACAO).
        return {
            "pergunta": pergunta,
            "skill": None,
            "parametros": parametros,
            "dados": None,
            "resposta_texto": interpretacao.get("entendimento") or "Desculpa, nao consegui responder isso agora.",
        }

    try:
        dados = executar_skill(skill, parametros)
    except Exception as e:
        return {
            "pergunta": pergunta,
            "skill": skill,
            "parametros": parametros,
            "dados": None,
            "resposta_texto": f"Erro ao buscar os dados: {e}",
        }

    resposta_texto = formatar_resposta(pergunta, skill, parametros, dados)
    return {
        "pergunta": pergunta,
        "skill": skill,
        "parametros": parametros,
        "dados": dados,
        "resposta_texto": resposta_texto,
    }


def _gerar_pdf(pergunta: str, resposta_texto: str, dados: dict) -> str:
    from playwright.sync_api import sync_playwright

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    def _linhas(d, prefixo=""):
        linhas = []
        listas = []
        for k, v in (d or {}).items():
            chave = f"{prefixo}{k}"
            if isinstance(v, dict):
                linhas.extend(_linhas(v, prefixo=f"{chave}.")[0])
            elif isinstance(v, list):
                if v and isinstance(v[0], dict):
                    listas.append((chave, v))
            else:
                linhas.append((chave, v))
        return linhas, listas

    linhas, listas = _linhas(dados)
    linhas_html = "".join(
        f"<tr><td>{html_mod.escape(str(k))}</td><td>{html_mod.escape(str(v))}</td></tr>"
        for k, v in linhas
    )

    tabelas_html = ""
    for nome_lista, itens in listas:
        colunas = list(itens[0].keys())
        cabecalho = "".join(f"<th>{html_mod.escape(c.replace('_', ' '))}</th>" for c in colunas)
        linhas_item = "".join(
            "<tr>" + "".join(f"<td>{html_mod.escape(str(item.get(c, '')))}</td>" for c in colunas) + "</tr>"
            for item in itens
        )
        tabelas_html += f"""
        <h2>{html_mod.escape(nome_lista.replace('_', ' '))} ({len(itens)})</h2>
        <table class="lista"><thead><tr>{cabecalho}</tr></thead><tbody>{linhas_item}</tbody></table>
        """

    doc_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
        @page {{ size: A4; margin: 20mm; }}
        body {{ font-family: Arial, sans-serif; color: #0F172A; margin: 0; }}
        h1 {{ font-size: 18px; border-bottom: 2px solid #2563EB; padding-bottom: 8px; }}
        h2 {{ font-size: 13px; color: #1E3A8A; margin-top: 24px; }}
        .pergunta {{ color: #64748B; font-size: 12px; margin-bottom: 16px; }}
        .resposta {{ font-size: 14px; font-weight: 700; background: #EFF6FF; padding: 12px 16px; border-radius: 8px; margin-bottom: 24px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
        td, th {{ padding: 6px 10px; border-bottom: 1px solid #E5E7EB; text-align: left; }}
        table:not(.lista) td:first-child {{ font-weight: 700; color: #475569; width: 45%; }}
        table.lista th {{ background: #F1F5F9; font-size: 10px; text-transform: uppercase; color: #64748B; }}
        .rodape {{ margin-top: 30px; font-size: 10px; color: #94A3B8; }}
    </style></head><body>
        <h1>CIA — Relatorio de Consulta</h1>
        <div class="pergunta">Pergunta: &quot;{html_mod.escape(pergunta)}&quot;</div>
        <div class="resposta">{html_mod.escape(resposta_texto)}</div>
        <table>{linhas_html}</table>
        {tabelas_html}
        <div class="rodape">Clinica Censo / ICDS — gerado em {agora} pela CIA</div>
    </body></html>"""

    pdf_path = os.path.join(tempfile.gettempdir(), f"jarvis_{int(datetime.now().timestamp()*1000)}.pdf")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page()
        page.set_content(doc_html)
        page.pdf(path=pdf_path, format="A4", print_background=True)
        browser.close()
    return pdf_path


def gerar_pdf_e_enviar(pergunta: str, resposta_texto: str, dados: dict, destinatario: str) -> dict:
    try:
        pdf_path = _gerar_pdf(pergunta, resposta_texto, dados)
    except Exception as e:
        return {"ok": False, "erro": f"Erro ao gerar PDF: {e}"}

    from email_sender import enviar_email
    resultado = enviar_email(
        destinatario,
        "CIA — Relatorio de Consulta",
        f"Pergunta: {pergunta}\n\n{resposta_texto}\n\nRelatorio completo em anexo.",
        anexo_path=pdf_path,
    )
    try:
        os.remove(pdf_path)
    except Exception:
        pass
    return resultado


# ══════════════════════════════════════════════════════════════════════════════
# MODO REUNIAO (Fase 2) — grava/transcreve (no navegador, igual o modo de
# consulta) e gera ata ao finalizar. SEM identificacao de quem fala por
# enquanto (decisao explicita do usuario: diarizacao fica pra depois, ou via
# Pyannote local -- stack pesado de ML, só compensa rodar durante reuniao de
# verdade, nao continuamente -- ou via nuvem, que manda audio pra fora e tem
# custo; nenhuma das duas decidida ainda).
# ══════════════════════════════════════════════════════════════════════════════

_SISTEMA_ATA = """Voce e a CIA, assistente da Clinica Censo (ICDS). Vai receber a transcricao \
completa de uma reuniao (sem identificacao de quem falou cada parte) e a lista \
de ACOES PENDENTES de reunioes anteriores, e deve gerar uma ATA estruturada.

DIFERENCA ENTRE DECISAO E ACAO (importante, nao confunda): "decisao" e uma \
ESCOLHA/DIRECAO que o grupo tomou (ex: "vamos usar o fornecedor X", \
"decidimos cancelar o evento") -- normalmente nao tem uma pessoa especifica \
EXECUTANDO uma tarefa depois. "acao" e uma TAREFA atribuida a alguem pra ser \
EXECUTADA (ex: "fulano vai fazer X ate sexta", "eu cuido disso"). SEMPRE que \
alguem se compromete a FAZER algo (com ou sem prazo dito), classifique como \
"acao", NUNCA como "decisao" -- mesmo que a tarefa em si tenha sido decidida \
na reuniao. Na duvida entre as duas, prefira "acao" se tiver um responsavel \
fazendo algo concreto.

REGRA CRITICA -- nunca invente: responsavel e prazo em decisoes/acoes novas SO \
entram se foram ditos EXPLICITAMENTE na transcricao. Se a transcricao nao \
mencionar quem ficou responsavel ou ate quando, use exatamente a string \
"a definir" nesses campos -- nunca chute um nome ou uma data. Da mesma forma, \
so inclua uma decisao/acao NOVA se ela realmente foi dita na reuniao -- nao \
invente itens pra preencher a ata. Se nao houve decisoes ou acoes novas claras, \
devolva listas vazias.

ACOES PENDENTES DE REUNIOES ANTERIORES: cada uma tem um "id". Se a transcricao \
mencionar EXPLICITAMENTE que uma dessas pendencias foi resolvida/concluida \
(ex: "ja fiz aquilo", "o pedido do reagente ja foi feito"), inclua o "id" \
dela na lista "acoes_concluidas_ids" da resposta. NUNCA marque uma pendencia \
como concluida so por estar relacionada ao assunto -- so se foi dito de forma \
clara que foi resolvida. Se nenhuma foi mencionada como resolvida, devolva \
lista vazia.

Responda SOMENTE com um JSON no formato exato:
{
  "resumo": "<2-4 frases resumindo do que se tratou a reuniao>",
  "decisoes": [{"decisao": "...", "responsavel": "... ou a definir", "prazo": "... ou a definir"}],
  "acoes": [{"acao": "...", "responsavel": "... ou a definir", "prazo": "... ou a definir"}],
  "acoes_concluidas_ids": [<ids das pendencias anteriores resolvidas nesta reuniao, lista vazia se nenhuma>],
  "insights": ["<no maximo 3 observacoes uteis, lista vazia se nao houver>"],
  "alertas": ["<no maximo 3 pontos que merecem atencao -- prazo apertado, divergencia, risco -- lista vazia se nao houver>"]
}
Responda em portugues, sem markdown dentro dos textos.
"""


def gerar_ata(transcricao: str, duracao_min: float = 0, participantes: str = "", data_inicio: str = "") -> dict:
    transcricao = (transcricao or "").strip()
    base = {
        "transcricao": transcricao,
        "duracao_min": round(duracao_min or 0, 1),
        "participantes": participantes or "",
        "data_inicio": data_inicio or datetime.now().strftime("%Y-%m-%d %H:%M"),
        "data_geracao": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    if not transcricao:
        return {**base, "resumo": "Reunião sem transcrição registrada.", "decisoes": [], "acoes": [], "insights": [], "alertas": [], "acoes_pendentes_anteriores": [], "acoes_resolvidas_nesta_reuniao": []}

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return {**base, "resumo": "Configure a variavel OPENAI_API_KEY no servidor.", "decisoes": [], "acoes": [], "insights": [], "alertas": [], "acoes_pendentes_anteriores": [], "acoes_resolvidas_nesta_reuniao": []}

    _inicializar_db_atas()
    try:
        pendentes_antes = _listar_acoes_pendentes()
    except Exception:
        pendentes_antes = []

    prompt_usuario = f"ACOES PENDENTES DE REUNIOES ANTERIORES:\n{json.dumps(pendentes_antes, ensure_ascii=False)}\n\nTranscricao da reuniao de hoje:\n\n{transcricao}"

    try:
        res = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": OPENAI_MODEL,
                "max_tokens": 1200,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": _SISTEMA_ATA},
                    {"role": "user", "content": prompt_usuario},
                ],
            },
            timeout=45,
        )
        conteudo = json.loads(res.json()["choices"][0]["message"]["content"])
    except Exception as e:
        return {**base, "resumo": f"Erro ao gerar a ata: {e}", "decisoes": [], "acoes": [], "insights": [], "alertas": [], "acoes_pendentes_anteriores": pendentes_antes, "acoes_resolvidas_nesta_reuniao": []}

    resultado = {
        **base,
        "resumo": conteudo.get("resumo") or "",
        "decisoes": conteudo.get("decisoes") or [],
        "acoes": conteudo.get("acoes") or [],
        "insights": conteudo.get("insights") or [],
        "alertas": conteudo.get("alertas") or [],
    }

    resolvidas_ids = set()
    for v in (conteudo.get("acoes_concluidas_ids") or []):
        try: resolvidas_ids.add(int(v))
        except (TypeError, ValueError): pass

    try:
        resultado["id"] = _salvar_ata(resultado)
        # Ações novas ditas nesta reunião entram como pendentes a partir de
        # agora -- vão aparecer pra próxima reunião reconhecer se foram
        # concluídas (todo o sentido de rastrear entre reuniões, em vez de
        # cada ata ser um documento avulso e isolado).
        for a in resultado["acoes"]:
            _criar_acao(resultado["id"], a.get("acao", ""), a.get("responsavel", "a definir"), a.get("prazo", "a definir"))
        for acao_id in resolvidas_ids:
            _marcar_acao_concluida(acao_id, resultado["id"])
    except Exception as e:
        print(f"[CIA] Erro ao salvar ata/ações no historico: {e}")

    resultado["acoes_resolvidas_nesta_reuniao"] = [p for p in pendentes_antes if p["id"] in resolvidas_ids]
    resultado["acoes_pendentes_anteriores"] = [p for p in pendentes_antes if p["id"] not in resolvidas_ids]
    return resultado


def _gerar_pdf_ata(ata: dict) -> str:
    from playwright.sync_api import sync_playwright

    def _linhas_decisoes_acoes(itens, chave_principal):
        linhas = ""
        for it in itens:
            linhas += (
                f"<tr><td>{html_mod.escape(str(it.get(chave_principal, '')))}</td>"
                f"<td>{html_mod.escape(str(it.get('responsavel', 'a definir')))}</td>"
                f"<td>{html_mod.escape(str(it.get('prazo', 'a definir')))}</td></tr>"
            )
        return linhas

    decisoes_html = (
        f"<h2>Decisões</h2><table class='lista'><thead><tr><th>Decisão</th><th>Responsável</th><th>Prazo</th></tr></thead>"
        f"<tbody>{_linhas_decisoes_acoes(ata.get('decisoes') or [], 'decisao')}</tbody></table>"
        if ata.get("decisoes") else "<h2>Decisões</h2><p class='vazio'>Nenhuma decisão registrada.</p>"
    )
    acoes_html = (
        f"<h2>Ações</h2><table class='lista'><thead><tr><th>Ação</th><th>Responsável</th><th>Prazo</th></tr></thead>"
        f"<tbody>{_linhas_decisoes_acoes(ata.get('acoes') or [], 'acao')}</tbody></table>"
        if ata.get("acoes") else "<h2>Ações</h2><p class='vazio'>Nenhuma ação registrada.</p>"
    )
    insights_html = (
        "<h2>Insights</h2><ul>" + "".join(f"<li>{html_mod.escape(i)}</li>" for i in (ata.get("insights") or [])) + "</ul>"
        if ata.get("insights") else ""
    )
    alertas_html = (
        "<h2>Alertas</h2><ul class='alertas'>" + "".join(f"<li>{html_mod.escape(a)}</li>" for a in (ata.get("alertas") or [])) + "</ul>"
        if ata.get("alertas") else ""
    )
    resolvidas_html = (
        "<h2>Pendências resolvidas nesta reunião</h2><ul>" +
        "".join(f"<li>{html_mod.escape(p.get('acao',''))}</li>" for p in (ata.get("acoes_resolvidas_nesta_reuniao") or [])) + "</ul>"
        if ata.get("acoes_resolvidas_nesta_reuniao") else ""
    )
    pendentes_html = (
        f"<h2>Pendências em aberto (de reuniões anteriores)</h2><table class='lista'><thead><tr><th>Ação</th><th>Responsável</th><th>Prazo</th></tr></thead>"
        f"<tbody>{_linhas_decisoes_acoes(ata.get('acoes_pendentes_anteriores') or [], 'acao')}</tbody></table>"
        if ata.get("acoes_pendentes_anteriores") else ""
    )

    doc_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
        @page {{ size: A4; margin: 20mm; }}
        body {{ font-family: Arial, sans-serif; color: #0F172A; margin: 0; }}
        h1 {{ font-size: 18px; border-bottom: 2px solid #8B1A1A; padding-bottom: 8px; }}
        h2 {{ font-size: 13px; color: #8B1A1A; margin-top: 24px; }}
        .meta {{ font-size: 11px; color: #64748B; margin-bottom: 4px; }}
        .resumo {{ font-size: 13px; background: #FDF2F2; padding: 12px 16px; border-radius: 8px; margin-top: 16px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
        td, th {{ padding: 6px 10px; border-bottom: 1px solid #E5E7EB; text-align: left; }}
        table.lista th {{ background: #F1F5F9; font-size: 10px; text-transform: uppercase; color: #64748B; }}
        .vazio {{ font-size: 11px; color: #94A3B8; font-style: italic; }}
        ul {{ font-size: 12px; padding-left: 18px; }}
        ul.alertas li {{ color: #B91C1C; }}
        .transcricao {{ font-size: 10.5px; color: #475569; white-space: pre-wrap; background: #FAFAFA; padding: 12px; border-radius: 8px; margin-top: 10px; max-height: none; }}
        .rodape {{ margin-top: 30px; font-size: 10px; color: #94A3B8; }}
    </style></head><body>
        <h1>CIA — Ata de Reunião</h1>
        <div class="meta">Início: {html_mod.escape(str(ata.get('data_inicio','')))} · Duração: {ata.get('duracao_min',0)} min</div>
        <div class="meta">Participantes: {html_mod.escape(ata.get('participantes') or 'não informado')}</div>
        <div class="resumo">{html_mod.escape(ata.get('resumo',''))}</div>
        {decisoes_html}
        {acoes_html}
        {resolvidas_html}
        {pendentes_html}
        {insights_html}
        {alertas_html}
        <h2>Transcrição completa</h2>
        <div class="transcricao">{html_mod.escape(ata.get('transcricao',''))}</div>
        <div class="rodape">Clinica Censo / ICDS — gerado em {html_mod.escape(str(ata.get('data_geracao','')))} pela CIA</div>
    </body></html>"""

    pdf_path = os.path.join(tempfile.gettempdir(), f"ata_{int(datetime.now().timestamp()*1000)}.pdf")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page()
        page.set_content(doc_html)
        page.pdf(path=pdf_path, format="A4", print_background=True)
        browser.close()
    return pdf_path


def gerar_pdf_ata_e_enviar(ata: dict, destinatario: str) -> dict:
    try:
        pdf_path = _gerar_pdf_ata(ata)
    except Exception as e:
        return {"ok": False, "erro": f"Erro ao gerar PDF da ata: {e}"}

    from email_sender import enviar_email
    resultado = enviar_email(
        destinatario,
        "CIA — Ata de Reunião",
        f"Ata de reunião gerada em {ata.get('data_geracao','')}.\n\n{ata.get('resumo','')}\n\nAta completa em anexo.",
        anexo_path=pdf_path,
    )
    try:
        os.remove(pdf_path)
    except Exception:
        pass
    return resultado
