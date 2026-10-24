# -*- coding: utf-8 -*-
"""
Prontuário eletrônico de consultas (módulo Atendimento) — banco local (SQLite),
separado de qualquer tabela do Smart. Decisão explícita: mais fácil iterar no
formato sem depender de homologação/aprovação no ERP (RCL só grava em
smart_hml hoje, e o módulo Nexo do Smart nunca foi usado nesta instalação).
Busca de CID-10 continua reaproveitando a tabela `CID` do Smart (read-only).
"""
import os
import sqlite3
import hashlib
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prontuario_eletronico.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def inicializar_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS consultas (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            pac_reg             INTEGER NOT NULL,
            paciente_nome       TEXT,
            medico_psv_cod      INTEGER NOT NULL,
            medico_nome         TEXT,
            medico_login        TEXT,
            modelo_atendimento  TEXT NOT NULL DEFAULT 'livre'
                                CHECK (modelo_atendimento IN ('livre','primeira_consulta','continuidade')),
            registro_texto      TEXT NOT NULL DEFAULT '',
            possui_alergia      TEXT NOT NULL DEFAULT 'N' CHECK (possui_alergia IN ('S','N')),
            alergia_detalhe     TEXT,
            hipotese_texto      TEXT NOT NULL DEFAULT '',
            status              TEXT NOT NULL DEFAULT 'aberto'
                                CHECK (status IN ('aberto','finalizado','cancelado')),
            retorno_necessario  TEXT CHECK (retorno_necessario IN ('S','N')),
            retorno_quando      TEXT,
            assinado_em         TEXT,
            assinado_por        TEXT,
            assinatura_hash     TEXT,
            iniciado_em         TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            finalizado_em       TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_consultas_pac ON consultas(pac_reg);
        CREATE INDEX IF NOT EXISTS ix_consultas_medico_status ON consultas(medico_psv_cod, status);

        CREATE TABLE IF NOT EXISTS consulta_cid (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            consulta_id  INTEGER NOT NULL REFERENCES consultas(id) ON DELETE CASCADE,
            cid_cod      TEXT NOT NULL,
            cid_desc     TEXT
        );

        CREATE TABLE IF NOT EXISTS prescricoes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            consulta_id   INTEGER NOT NULL REFERENCES consultas(id) ON DELETE CASCADE,
            medicamento   TEXT NOT NULL,
            posologia     TEXT,
            quantidade    TEXT,
            uso_continuo  TEXT NOT NULL DEFAULT 'N' CHECK (uso_continuo IN ('S','N')),
            criado_em     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS atestados (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            consulta_id   INTEGER NOT NULL REFERENCES consultas(id) ON DELETE CASCADE,
            texto         TEXT NOT NULL,
            dias          INTEGER,
            data_inicio   TEXT,
            cid_cod       TEXT,
            criado_em     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS encaminhamentos (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            consulta_id    INTEGER NOT NULL REFERENCES consultas(id) ON DELETE CASCADE,
            especialidade  TEXT NOT NULL,
            texto          TEXT,
            criado_em      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS grupos_medicamentos (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            medico_login   TEXT NOT NULL,
            nome           TEXT NOT NULL,
            compartilhado  TEXT NOT NULL DEFAULT 'N' CHECK (compartilhado IN ('S','N')),
            criado_em      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS grupos_medicamentos_itens (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo_id      INTEGER NOT NULL REFERENCES grupos_medicamentos(id) ON DELETE CASCADE,
            medicamento   TEXT NOT NULL,
            posologia     TEXT,
            quantidade    TEXT,
            uso_continuo  TEXT NOT NULL DEFAULT 'N' CHECK (uso_continuo IN ('S','N'))
        );
    """)
    conn.commit()
    conn.close()


def listar_grupos_medicamentos(medico_login: str):
    """Grupos do próprio médico + grupos marcados como compartilhados por qualquer um."""
    conn = get_conn()
    grupos = conn.execute("""
        SELECT * FROM grupos_medicamentos
        WHERE medico_login = ? OR compartilhado = 'S'
        ORDER BY nome
    """, (medico_login,)).fetchall()
    resultado = []
    for g in grupos:
        itens = conn.execute("SELECT * FROM grupos_medicamentos_itens WHERE grupo_id=?", (g["id"],)).fetchall()
        d = dict(g)
        d["itens"] = [dict(i) for i in itens]
        d["proprio"] = g["medico_login"] == medico_login
        resultado.append(d)
    conn.close()
    return resultado


def criar_grupo_medicamentos(medico_login: str, nome: str, compartilhado: bool, itens: list):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO grupos_medicamentos (medico_login, nome, compartilhado) VALUES (?,?,?)",
        (medico_login, nome, "S" if compartilhado else "N"),
    )
    grupo_id = cur.lastrowid
    for it in itens:
        conn.execute("""
            INSERT INTO grupos_medicamentos_itens (grupo_id, medicamento, posologia, quantidade, uso_continuo)
            VALUES (?,?,?,?,?)
        """, (grupo_id, it["medicamento"], it.get("posologia", ""), it.get("quantidade", ""),
              "S" if it.get("uso_continuo") in ("S", True) else "N"))
    conn.commit()
    conn.close()
    return grupo_id


def remover_grupo_medicamentos(grupo_id: int, medico_login: str):
    """Só o dono apaga — evita um médico apagar grupo compartilhado de outro."""
    conn = get_conn()
    conn.execute("DELETE FROM grupos_medicamentos WHERE id=? AND medico_login=?", (grupo_id, medico_login))
    conn.commit()
    conn.close()


def _consulta_completa(conn, consulta_id):
    c = conn.execute("SELECT * FROM consultas WHERE id=?", (consulta_id,)).fetchone()
    if not c:
        return None
    d = dict(c)
    d["cids"] = [dict(r) for r in conn.execute(
        "SELECT * FROM consulta_cid WHERE consulta_id=? ORDER BY id", (consulta_id,))]
    d["prescricoes"] = [dict(r) for r in conn.execute(
        "SELECT * FROM prescricoes WHERE consulta_id=? ORDER BY id", (consulta_id,))]
    d["atestados"] = [dict(r) for r in conn.execute(
        "SELECT * FROM atestados WHERE consulta_id=? ORDER BY id", (consulta_id,))]
    d["encaminhamentos"] = [dict(r) for r in conn.execute(
        "SELECT * FROM encaminhamentos WHERE consulta_id=? ORDER BY id", (consulta_id,))]
    return d


def iniciar_consulta(pac_reg, paciente_nome, medico_psv_cod, medico_nome, medico_login, modelo_atendimento="livre"):
    """Retoma uma consulta já aberta pro mesmo paciente/médico, ou cria uma nova."""
    conn = get_conn()
    existente = conn.execute("""
        SELECT id FROM consultas
        WHERE pac_reg=? AND medico_psv_cod=? AND status='aberto'
        ORDER BY id DESC LIMIT 1
    """, (pac_reg, medico_psv_cod)).fetchone()
    if existente:
        consulta_id = existente["id"]
    else:
        cur = conn.execute("""
            INSERT INTO consultas (pac_reg, paciente_nome, medico_psv_cod, medico_nome, medico_login, modelo_atendimento)
            VALUES (?,?,?,?,?,?)
        """, (pac_reg, paciente_nome, medico_psv_cod, medico_nome, medico_login, modelo_atendimento))
        conn.commit()
        consulta_id = cur.lastrowid
    d = _consulta_completa(conn, consulta_id)
    conn.close()
    return d


def obter_consulta(consulta_id):
    conn = get_conn()
    d = _consulta_completa(conn, consulta_id)
    conn.close()
    return d


def atualizar_consulta(consulta_id, campos: dict):
    permitidos = {"modelo_atendimento", "registro_texto", "possui_alergia", "alergia_detalhe", "hipotese_texto"}
    sets, valores = [], []
    for k, v in campos.items():
        if k in permitidos:
            sets.append(f"{k}=?")
            valores.append(v)
    if not sets:
        return obter_consulta(consulta_id)
    conn = get_conn()
    valores.append(consulta_id)
    conn.execute(f"UPDATE consultas SET {', '.join(sets)} WHERE id=?", valores)
    conn.commit()
    d = _consulta_completa(conn, consulta_id)
    conn.close()
    return d


def adicionar_cid(consulta_id, cid_cod, cid_desc):
    conn = get_conn()
    conn.execute("INSERT INTO consulta_cid (consulta_id, cid_cod, cid_desc) VALUES (?,?,?)",
                 (consulta_id, cid_cod, cid_desc))
    conn.commit()
    conn.close()


def remover_cid(consulta_id, cid_id):
    conn = get_conn()
    conn.execute("DELETE FROM consulta_cid WHERE id=? AND consulta_id=?", (cid_id, consulta_id))
    conn.commit()
    conn.close()


def adicionar_prescricao(consulta_id, medicamento, posologia, quantidade, uso_continuo):
    conn = get_conn()
    conn.execute("""
        INSERT INTO prescricoes (consulta_id, medicamento, posologia, quantidade, uso_continuo)
        VALUES (?,?,?,?,?)
    """, (consulta_id, medicamento, posologia, quantidade, "S" if uso_continuo else "N"))
    conn.commit()
    conn.close()


def remover_prescricao(consulta_id, item_id):
    conn = get_conn()
    conn.execute("DELETE FROM prescricoes WHERE id=? AND consulta_id=?", (item_id, consulta_id))
    conn.commit()
    conn.close()


def adicionar_atestado(consulta_id, texto, dias, data_inicio, cid_cod):
    conn = get_conn()
    conn.execute("""
        INSERT INTO atestados (consulta_id, texto, dias, data_inicio, cid_cod)
        VALUES (?,?,?,?,?)
    """, (consulta_id, texto, dias, data_inicio, cid_cod))
    conn.commit()
    conn.close()


def remover_atestado(consulta_id, item_id):
    conn = get_conn()
    conn.execute("DELETE FROM atestados WHERE id=? AND consulta_id=?", (item_id, consulta_id))
    conn.commit()
    conn.close()


def adicionar_encaminhamento(consulta_id, especialidade, texto):
    conn = get_conn()
    conn.execute("""
        INSERT INTO encaminhamentos (consulta_id, especialidade, texto)
        VALUES (?,?,?)
    """, (consulta_id, especialidade, texto))
    conn.commit()
    conn.close()


def remover_encaminhamento(consulta_id, item_id):
    conn = get_conn()
    conn.execute("DELETE FROM encaminhamentos WHERE id=? AND consulta_id=?", (item_id, consulta_id))
    conn.commit()
    conn.close()


def finalizar_consulta(consulta_id, retorno_necessario, retorno_quando, assinar, assinado_por):
    """
    Assinatura eletrônica simples: não é certificado ICP-Brasil (exigiria uma
    Autoridade Certificadora real por trás, tipo birdID/VIDAS) — é um hash
    SHA-256 do conteúdo completo da consulta + login de quem confirmou +
    timestamp, guardado junto. Serve como evidência de integridade/autoria
    interna, não tem o mesmo peso jurídico de uma assinatura ICP-Brasil.
    """
    conn = get_conn()
    d = _consulta_completa(conn, consulta_id)
    if not d:
        conn.close()
        return None

    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    assinatura_hash = None
    assinado_em = None
    if assinar:
        conteudo = "|".join([
            str(d["id"]), d["registro_texto"] or "", d["hipotese_texto"] or "",
            ",".join(c["cid_cod"] for c in d["cids"]),
            assinado_por or "", agora,
        ])
        assinatura_hash = hashlib.sha256(conteudo.encode("utf-8")).hexdigest()
        assinado_em = agora

    conn.execute("""
        UPDATE consultas SET
            status='finalizado', retorno_necessario=?, retorno_quando=?,
            assinado_em=?, assinado_por=?, assinatura_hash=?, finalizado_em=?
        WHERE id=?
    """, (retorno_necessario, retorno_quando, assinado_em,
          assinado_por if assinar else None, assinatura_hash, agora, consulta_id))
    conn.commit()
    d = _consulta_completa(conn, consulta_id)
    conn.close()
    return d


def historico_paciente(pac_reg, limite=15):
    """
    Histórico completo (com CIDs, prescrições, atestados, encaminhamentos de
    cada consulta) — usado tanto pra lista simples do "Histórico de
    atendimento" quanto pro resumo gerado por IA, que precisa do conteúdo de
    verdade, não só título/status.
    """
    conn = get_conn()
    ids = conn.execute("""
        SELECT id FROM consultas WHERE pac_reg=? ORDER BY iniciado_em DESC LIMIT ?
    """, (pac_reg, limite)).fetchall()
    resultado = [_consulta_completa(conn, r["id"]) for r in ids]
    conn.close()
    return resultado
