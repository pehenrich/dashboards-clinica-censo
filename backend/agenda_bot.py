# -*- coding: utf-8 -*-
"""
Bot de WhatsApp — disponibilidade de agenda por especialidade, para a
recepção e qualquer setor consultarem direto num grupo do WhatsApp, sem
precisar abrir o Smart. Reaproveita a mesma sessão WPPConnect já conectada
e o OPENAI_API_KEY já configurado (mesmo usado em /api/briefing).

Mesmo padrão mention-based + poll + dedup do bot de chamados do NetMonitor
(monitores.py, checar_whatsapp_chamados): só processa mensagem que MENCIONA
o número conectado, pra não responder conversa normal do grupo. Import de
`main` é sempre tardio (dentro das funções) pra evitar ciclo de import,
já que main.py importa scheduler.py no startup e scheduler.py importa
este módulo.
"""
import os
import re
import json
import sqlite3
import time
from datetime import datetime, timezone

import httpx

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agenda_bot.db")
_WPP_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whatsapp_config.json")
_cache_meu_lid: dict[str, str] = {}
_RE_MENCAO = re.compile(r"@\d+\s*")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS mensagens_vistas (
            mensagem_id TEXT PRIMARY KEY,
            visto_em    TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS seed_feito (
            id       INTEGER PRIMARY KEY CHECK (id = 1),
            feito_em TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def _carregar_wpp_config():
    if not os.path.exists(_WPP_CONFIG_PATH):
        return None
    with open(_WPP_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _obter_meu_lid_no_grupo(session: str, token: str, base: str, grupo_id: str):
    """ID (lid, serializado) que representa a própria sessão dentro do
    grupo — aparece em mentionedJidList quando alguém marca o número
    conectado. Descoberto via group-members (campo isMe), cacheado."""
    if grupo_id in _cache_meu_lid:
        return _cache_meu_lid[grupo_id]
    try:
        resp = httpx.get(
            f"{base}/api/{session}/group-members/{grupo_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        membros = data.get("response", data) if isinstance(data, dict) else data
        for m in membros or []:
            if m.get("isMe"):
                lid = (m.get("id") or {}).get("_serialized")
                if lid:
                    _cache_meu_lid[grupo_id] = lid
                    return lid
    except Exception:
        pass
    return None


def _extrair_especialidade(pergunta: str):
    """Usa o helper OpenAI já configurado no main.py (mesmo do /api/briefing)
    pra extrair a especialidade médica de uma pergunta em linguagem natural."""
    from main import _call_openai

    system = (
        "Você identifica qual especialidade, setor ou tipo de exame/atendimento está sendo perguntado em uma "
        'mensagem de funcionário de clínica sobre disponibilidade de agenda (ex: "temos dermatologista?", '
        '"tem ultrassonografia essa semana?", "vaga de nutrição"). Responda APENAS com esse termo em português, '
        "capitalizado, na forma como aparece numa lista de especialidades de clínica (ex: Dermatologia, "
        "Cardiologia, Ultrassonografia, Nutrição, Psicologia, Pediatria, Ortopedia, Medicina Ocupacional), sem "
        "mais nenhum texto. Se a mensagem não menciona nada identificável como especialidade/setor/exame, "
        "responda exatamente: NENHUMA"
    )
    try:
        resposta = _call_openai(pergunta, system=system).strip()
    except Exception:
        return None
    if not resposta or resposta.upper().startswith("NENHUMA"):
        return None
    return resposta


def _extrair_intencao(pergunta: str):
    """Classifica a pergunta entre 'especialidade' (ex: "temos dermatologista?"),
    'medico' (ex: "Dr. Malcher atende aqui?") e 'hoje' (ex: "quais médicos têm
    agenda aberta hoje?") — usado pelo chat interno do Dashboard, que responde
    os três tipos de pergunta na mesma tela.
    Retorna (tipo, valor) ou (None, None) se não identificar nenhum dos três."""
    from main import _call_openai

    system = (
        "Você classifica uma mensagem de funcionário de clínica sobre agenda médica. Responda EXATAMENTE em duas "
        "linhas, sem mais nada:\n"
        "TIPO: especialidade OU medico OU hoje OU nenhuma\n"
        "VALOR: <especialidade em português, ex: Dermatologia> OU <nome do médico como foi mencionado, sem "
        "\"Dr.\"/\"Dra.\", ex: Malcher> OU deixe em branco se TIPO for hoje ou nenhuma\n\n"
        'Use "medico" quando a pergunta mencionar um nome ou sobrenome de médico específico (ex: "Dr. Malcher '
        'atende aqui?", "a Dra. Fernanda tem vaga?"). Use "especialidade" quando perguntar sobre uma '
        'especialidade/setor/exame genérico (ex: "temos dermatologista?", "tem ultrassonografia?"), sem nome '
        'próprio. Use "hoje" quando a pergunta pedir uma lista geral de quais médicos têm agenda/vaga disponível '
        'hoje, sem citar especialidade nem médico específico (ex: "quais médicos têm agenda aberta hoje?", "quem '
        'atende hoje?", "tem algum médico com vaga hoje?"). Use "nenhuma" se não conseguir identificar nenhum dos '
        "três."
    )
    try:
        resposta = _call_openai(pergunta, system=system).strip()
    except Exception:
        return None, None

    tipo, valor = None, None
    for linha in resposta.splitlines():
        limpa = linha.strip()
        if limpa.upper().startswith("TIPO:"):
            tipo = limpa.split(":", 1)[1].strip().lower()
        elif limpa.upper().startswith("VALOR:"):
            valor = limpa.split(":", 1)[1].strip()
    if tipo == "hoje":
        return "hoje", None
    if tipo not in ("especialidade", "medico") or not valor:
        return None, None
    return tipo, valor


def _formatar_resposta(resultado: dict) -> str:
    if not resultado.get("encontrada"):
        return (
            f'Não encontrei horários disponíveis para "{resultado.get("especialidade_buscada")}" nos próximos '
            f"30 dias. Pode ser que não tenhamos essa especialidade ativa agora, ou a agenda ainda não foi "
            f"liberada — vale confirmar direto com a coordenação."
        )

    linhas = [f"📅 *{resultado['especialidade_encontrada']}* — horários disponíveis:\n"]
    for m in resultado["medicos"]:
        linhas.append(f"*Dr(a). {m['medico_nome']}*")
        for d in m["proximas_datas"]:
            data_fmt = datetime.strptime(d["data"], "%Y-%m-%d").strftime("%d/%m")
            horarios = ", ".join(d["horarios"][:6])
            sobra = len(d["horarios"]) - 6
            mais = f" (+{sobra})" if sobra > 0 else ""
            linhas.append(f"  {data_fmt}: {horarios}{mais}")
        linhas.append("")
    return "\n".join(linhas).strip()


def checar_agenda_bot(grupo_id: str) -> tuple[str, int, str]:
    """
    Busca mensagens novas no grupo `grupo_id` e responde as que MENCIONAM
    o número conectado com a disponibilidade de agenda da especialidade
    perguntada. Mesmo padrão de dedup + seed do bot de chamados: na
    primeiríssima execução só semeia o histórico do grupo, sem responder
    nada (evita responder tudo que já tinha sido perguntado antes do bot
    existir).
    """
    inicio = time.monotonic()
    cfg = _carregar_wpp_config()
    if not cfg:
        return "down", 0, "whatsapp_config.json não encontrado"

    session = cfg.get("wppconnect_session", "myinstance")
    token = cfg.get("wppconnect_token", "")
    base = cfg.get("wppconnect_url", "http://localhost:21465")

    meu_lid = _obter_meu_lid_no_grupo(session, token, base, grupo_id)
    if not meu_lid:
        return "down", 0, "Não consegui identificar o próprio número no grupo (group-members)"

    try:
        resp = httpx.get(
            f"{base}/api/{session}/get-messages/{grupo_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"count": 30},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        mensagens = data.get("response", data) if isinstance(data, dict) else data
        if not isinstance(mensagens, list):
            mensagens = []
    except Exception as e:
        return "down", int((time.monotonic() - inicio) * 1000), str(e)[:200]

    mensagens.sort(key=lambda m: m.get("timestamp") or 0)

    conn = get_conn()
    seed_feito = conn.execute("SELECT COUNT(*) AS n FROM seed_feito").fetchone()["n"] > 0
    vistas = {r["mensagem_id"] for r in conn.execute("SELECT mensagem_id FROM mensagens_vistas").fetchall()}

    agora = datetime.now(timezone.utc).isoformat()
    respondidas = 0
    for m in mensagens:
        mid = m.get("id")
        if not mid or mid in vistas:
            continue
        conn.execute("INSERT OR IGNORE INTO mensagens_vistas (mensagem_id, visto_em) VALUES (?,?)", (mid, agora))

        if not seed_feito or m.get("fromMe") or m.get("type") != "chat":
            continue

        mencoes = m.get("mentionedJidList") or []
        mencionou = any((mc.get("_serialized") == meu_lid) for mc in mencoes if isinstance(mc, dict))
        if not mencionou:
            continue

        texto_msg = (m.get("body") or m.get("content") or "").strip()
        pergunta = _RE_MENCAO.sub("", texto_msg).strip()
        if not pergunta:
            continue

        especialidade = _extrair_especialidade(pergunta)
        if not especialidade:
            resposta_txt = ('Não entendi qual especialidade você quer consultar. Pode perguntar assim: '
                             '"temos dermatologista disponível?"')
        else:
            from main import buscar_disponibilidade_especialidade
            resultado = buscar_disponibilidade_especialidade(especialidade)
            resposta_txt = _formatar_resposta(resultado)

        from whatsapp_sender import enviar_wppconnect
        try:
            enviar_wppconnect(resposta_txt, grupo_id)
            respondidas += 1
        except Exception:
            pass

    if not seed_feito:
        conn.execute("INSERT OR IGNORE INTO seed_feito (id, feito_em) VALUES (1, ?)", (agora,))

    conn.commit()
    conn.close()

    tempo_ms = int((time.monotonic() - inicio) * 1000)
    detalhe = f"{respondidas} pergunta(s) respondida(s)" if seed_feito else "Histórico inicial do grupo semeado (sem responder)"
    return "up", tempo_ms, detalhe
