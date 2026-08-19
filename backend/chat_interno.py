# -*- coding: utf-8 -*-
"""
Chat interno do Dashboard — canais fixos por setor + mensagens diretas (DM)
entre usuários. Armazenamento local (SQLite), independente do banco Smart
(igual ao padrão já usado em guias.db/organograma.db). Frontend faz polling
(sem WebSocket) — consistente com o resto do app.
"""
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_interno.db")

CANAIS_SETOR_PADRAO = [
    ("setor:geral",       "📢 Geral"),
    ("setor:recepcao",    "Recepção"),
    ("setor:laboratorio", "Laboratório"),
    ("setor:faturamento", "Faturamento"),
    ("setor:ti",          "TI"),
    ("setor:coordenacao", "Coordenação"),
]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS canais (
            id         TEXT PRIMARY KEY,
            tipo       TEXT NOT NULL,      -- 'setor' | 'dm' | 'grupo'
            nome       TEXT NOT NULL,
            criado_em  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS participantes (
            canal_id TEXT NOT NULL,
            login    TEXT NOT NULL,
            nome     TEXT NOT NULL,
            PRIMARY KEY (canal_id, login)
        );

        CREATE TABLE IF NOT EXISTS mensagens (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            canal_id         TEXT NOT NULL,
            remetente_login  TEXT NOT NULL,
            remetente_nome   TEXT NOT NULL,
            texto            TEXT NOT NULL,
            importante       INTEGER NOT NULL DEFAULT 0,
            criado_em        TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mensagens_canal ON mensagens(canal_id, criado_em);

        CREATE TABLE IF NOT EXISTS leitura (
            login           TEXT NOT NULL,
            canal_id        TEXT NOT NULL,
            ultima_leitura  TEXT NOT NULL,
            PRIMARY KEY (login, canal_id)
        );

        CREATE TABLE IF NOT EXISTS alertas_vistos (
            login        TEXT NOT NULL,
            mensagem_id  INTEGER NOT NULL,
            PRIMARY KEY (login, mensagem_id)
        );
    """)
    # coluna 'importante' pode nao existir em banco criado antes desta versao
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(mensagens)").fetchall()]
    if "importante" not in cols:
        conn.execute("ALTER TABLE mensagens ADD COLUMN importante INTEGER NOT NULL DEFAULT 0")
    conn.commit()

    agora = datetime.now(timezone.utc).isoformat()
    for cid, nome in CANAIS_SETOR_PADRAO:
        conn.execute(
            "INSERT OR IGNORE INTO canais (id, tipo, nome, criado_em) VALUES (?,?,?,?)",
            (cid, "setor", nome, agora),
        )
    conn.commit()
    conn.close()


def _dm_canal_id(login_a: str, login_b: str) -> str:
    a, b = sorted([login_a.strip().lower(), login_b.strip().lower()])
    return f"dm:{a}:{b}"


def obter_ou_criar_dm(login_a: str, nome_a: str, login_b: str, nome_b: str) -> str:
    cid = _dm_canal_id(login_a, login_b)
    conn = get_conn()
    existe = conn.execute("SELECT 1 FROM canais WHERE id = ?", (cid,)).fetchone()
    if not existe:
        agora = datetime.now(timezone.utc).isoformat()
        nome_canal = f"{nome_a} ↔ {nome_b}"
        conn.execute(
            "INSERT INTO canais (id, tipo, nome, criado_em) VALUES (?,?,?,?)",
            (cid, "dm", nome_canal, agora),
        )
        conn.commit()
    conn.close()
    return cid


def criar_grupo(nome: str, criador_login: str, criador_nome: str, participantes: list) -> str:
    """participantes: lista de {login, nome} — o criador é incluído
    automaticamente, não precisa vir na lista."""
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Nome do grupo não pode ser vazio")

    cid = f"grupo:{uuid.uuid4().hex[:12]}"
    conn = get_conn()
    agora = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT INTO canais (id, tipo, nome, criado_em) VALUES (?,?,?,?)", (cid, "grupo", nome, agora))

    membros = {(criador_login.strip().lower(), criador_nome)}
    for p in participantes or []:
        login_p = (p.get("login") or "").strip().lower()
        if login_p:
            membros.add((login_p, p.get("nome") or login_p))
    conn.executemany(
        "INSERT OR IGNORE INTO participantes (canal_id, login, nome) VALUES (?,?,?)",
        [(cid, login_p, nome_p) for login_p, nome_p in membros],
    )
    conn.commit()
    conn.close()
    return cid


def listar_participantes(canal_id: str):
    conn = get_conn()
    rows = conn.execute("SELECT login, nome FROM participantes WHERE canal_id = ? ORDER BY nome", (canal_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def listar_canais(login: str):
    """Canais de setor (visíveis a todos) + DMs e grupos em que esse login
    já participou, com contagem de não lidas."""
    conn = get_conn()
    login = login.strip().lower()

    canais_setor = conn.execute("SELECT id, tipo, nome FROM canais WHERE tipo = 'setor'").fetchall()
    canais_dm = conn.execute(
        "SELECT id, tipo, nome FROM canais WHERE tipo = 'dm' AND id LIKE ?",
        (f"%:{login}%",),
    ).fetchall()
    # LIKE acima pode dar falso positivo (login substring de outro) — filtra de verdade:
    canais_dm = [c for c in canais_dm if login in c["id"].split(":")[1:]]
    canais_grupo = conn.execute("""
        SELECT c.id, c.tipo, c.nome
        FROM canais c
        JOIN participantes p ON p.canal_id = c.id
        WHERE c.tipo = 'grupo' AND p.login = ?
    """, (login,)).fetchall()

    resultado = []
    for c in list(canais_setor) + canais_dm + list(canais_grupo):
        ultima_leitura = conn.execute(
            "SELECT ultima_leitura FROM leitura WHERE login = ? AND canal_id = ?",
            (login, c["id"]),
        ).fetchone()
        desde = ultima_leitura["ultima_leitura"] if ultima_leitura else "1970-01-01T00:00:00+00:00"
        nao_lidas = conn.execute(
            "SELECT COUNT(*) AS n FROM mensagens WHERE canal_id = ? AND criado_em > ? AND remetente_login <> ?",
            (c["id"], desde, login),
        ).fetchone()["n"]
        ultima_msg = conn.execute(
            "SELECT texto, remetente_nome, criado_em FROM mensagens WHERE canal_id = ? ORDER BY criado_em DESC LIMIT 1",
            (c["id"],),
        ).fetchone()
        resultado.append({
            "id": c["id"],
            "tipo": c["tipo"],
            "nome": c["nome"],
            "nao_lidas": nao_lidas,
            "ultima_mensagem": dict(ultima_msg) if ultima_msg else None,
        })
    conn.close()
    resultado.sort(key=lambda c: (c["ultima_mensagem"] or {}).get("criado_em", ""), reverse=True)
    return resultado


def listar_mensagens(canal_id: str, limite: int = 100):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, canal_id, remetente_login, remetente_nome, texto, importante, criado_em "
        "FROM mensagens WHERE canal_id = ? ORDER BY criado_em DESC LIMIT ?",
        (canal_id, limite),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def enviar_mensagem(canal_id: str, login: str, nome: str, texto: str, importante: bool = False):
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("Mensagem vazia")
    conn = get_conn()
    agora = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO mensagens (canal_id, remetente_login, remetente_nome, texto, importante, criado_em) VALUES (?,?,?,?,?,?)",
        (canal_id, login.strip().lower(), nome, texto, 1 if importante else 0, agora),
    )
    conn.execute(
        "INSERT INTO leitura (login, canal_id, ultima_leitura) VALUES (?,?,?) "
        "ON CONFLICT(login, canal_id) DO UPDATE SET ultima_leitura = excluded.ultima_leitura",
        (login.strip().lower(), canal_id, agora),
    )
    conn.commit()
    msg_id = cur.lastrowid
    conn.close()
    return {"id": msg_id, "canal_id": canal_id, "remetente_login": login.strip().lower(),
            "remetente_nome": nome, "texto": texto, "importante": importante, "criado_em": agora}


def _canais_visiveis_ids(conn, login: str):
    """IDs de todos os canais que esse login enxerga: setor (todos) + dm +
    grupo (onde participa) — mesma lógica de listar_canais, reaproveitada
    aqui pra escopar quais mensagens importantes valem alerta pra ele."""
    ids = [r["id"] for r in conn.execute("SELECT id FROM canais WHERE tipo = 'setor'").fetchall()]
    dm_rows = conn.execute("SELECT id FROM canais WHERE tipo = 'dm' AND id LIKE ?", (f"%:{login}%",)).fetchall()
    ids += [r["id"] for r in dm_rows if login in r["id"].split(":")[1:]]
    ids += [r["id"] for r in conn.execute(
        "SELECT c.id FROM canais c JOIN participantes p ON p.canal_id = c.id WHERE c.tipo='grupo' AND p.login = ?",
        (login,),
    ).fetchall()]
    return ids


def listar_alertas_novos(login: str):
    """Mensagens importantes, em qualquer canal visível pra esse login, que
    ele ainda não viu (não estão em alertas_vistos) e que não foram
    mandadas por ele mesmo — usado pelo popup global de mensagem importante."""
    conn = get_conn()
    login = login.strip().lower()
    canais_ids = _canais_visiveis_ids(conn, login)
    if not canais_ids:
        conn.close()
        return []

    placeholders = ",".join("?" for _ in canais_ids)
    rows = conn.execute(f"""
        SELECT m.id, m.canal_id, c.nome AS canal_nome, m.remetente_nome, m.texto, m.criado_em
        FROM mensagens m
        JOIN canais c ON c.id = m.canal_id
        WHERE m.importante = 1
          AND m.canal_id IN ({placeholders})
          AND m.remetente_login <> ?
          AND m.id NOT IN (SELECT mensagem_id FROM alertas_vistos WHERE login = ?)
        ORDER BY m.criado_em ASC
    """, (*canais_ids, login, login)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def marcar_alerta_visto(login: str, mensagem_id: int):
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO alertas_vistos (login, mensagem_id) VALUES (?,?)", (login.strip().lower(), mensagem_id))
    conn.commit()
    conn.close()


def marcar_lido(canal_id: str, login: str):
    conn = get_conn()
    agora = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO leitura (login, canal_id, ultima_leitura) VALUES (?,?,?) "
        "ON CONFLICT(login, canal_id) DO UPDATE SET ultima_leitura = excluded.ultima_leitura",
        (login.strip().lower(), canal_id, agora),
    )
    conn.commit()
    conn.close()
