"""
Dashboard Clínica - Backend FastAPI
ERP: Smart Pixeon | Banco: SQL Server

Tabelas validadas contra dicionário oficial Pixeon:
  osm  → osm_serie, osm_num, osm_pac, osm_dthr, osm_cnv, osm_mreq,
          osm_str, osm_status, osm_atend, osm_hsp_num, osm_dthr_saida,
          osm_pln_cod, OSM_AGM_ID
  cnv  → cnv_cod (PK char 3), cnv_nome (varchar 20), cnv_stat (A=Ativo/C=Cancelado),
          cnv_tipo (AM=Ambulatorial, HP=Hospitalar, AH=Ambul/Hosp, MC=Med.Ocupacional),
          cnv_reg_ans, cnv_cgc, cnv_caixa_fatura
"""

from fastapi import FastAPI, UploadFile, File, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

# WhatsApp / Scheduler (importação opcional — não quebra se arquivos não existem)
try:
    from whatsapp_sender import enviar_resumo as _wpp_enviar
    from scheduler import set_query_func, iniciar_scheduler_em_background
    _WPP_AVAILABLE = True
except ImportError:
    _WPP_AVAILABLE = False

# DB Diagnósticos — consulta de status/laudo (envio do pedido já é feito
# pelo próprio Smart Pixeon, este módulo só lê o retorno via SOAP DBSync)
try:
    from db_diagnosticos_sender import consultar_status, buscar_laudo_pdf
    _DB_DIAG_AVAILABLE = True
except ImportError:
    _DB_DIAG_AVAILABLE = False
import pyodbc
import os
import re as _re
from datetime import datetime, timedelta
import httpx
with open(r"C:\Dashboard\backend\.env", "r", encoding="utf-8-sig") as _f:
    for _line in _f:
        _line = _line.strip()
        if _line and "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ[_k.strip()] = _v.strip().strip('"').strip("'")
print("ENV LOADED:", os.environ.get("OPENAI_API_KEY", "NAO")[:10])
import os as _os_test
print("ENV TEST:", _os_test.environ.get("OPENAI_API_KEY", "NAO")[:10])

MESES_PT_ABREV = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

CNPJ_INTERNO = "06288135000261"  # ICDS - Clínica de Especialidades Parauapebas


def _filtro_sql_cnpj(cnpj: str, alias_osm: str = "osm"):
    """
    Monta a cláusula SQL de filtro por CNPJ interno/externo (osm_cnpj_solic),
    usada nos dashboards de Resultados Financeiros. cnpj: "interno" (padrão),
    "externo" ou "todos". "Externo" inclui CNPJ vazio/nulo, já que é
    literalmente diferente do CNPJ interno — mesmo critério do pedido original.
    """
    cnpj = (cnpj or "interno").strip().lower()
    if cnpj == "interno":
        return f"AND RTRIM(ISNULL({alias_osm}.OSM_CNPJ_SOLIC,'')) = '{CNPJ_INTERNO}'"
    elif cnpj == "externo":
        return f"AND RTRIM(ISNULL({alias_osm}.OSM_CNPJ_SOLIC,'')) <> '{CNPJ_INTERNO}'"
    return ""  # "todos" — sem filtro

app = FastAPI(title="Dashboard Clínica", version="1.1.0")

# Rate limiting simples para endpoint público de resultados (CPF + nascimento).
# Único processo (uvicorn --workers 1) -> dict em memória é suficiente, sem Redis.
from collections import defaultdict
import time as _time

_PUBLICO_TENTATIVAS = defaultdict(list)   # ip -> [timestamps de tentativas]
_PUBLICO_JANELA_S   = 15 * 60             # 15 minutos
_PUBLICO_MAX_TENT   = 8                   # no máximo 8 tentativas por IP por janela

def _rate_limit_check(ip: str):
    agora = _time.time()
    tentativas = _PUBLICO_TENTATIVAS[ip]
    tentativas[:] = [t for t in tentativas if agora - t < _PUBLICO_JANELA_S]
    if len(tentativas) >= _PUBLICO_MAX_TENT:
        raise HTTPException(429, "Muitas tentativas. Aguarde alguns minutos e tente novamente.")

def _rate_limit_register(ip: str, success: bool):
    _PUBLICO_TENTATIVAS[ip].append(_time.time())

# ← ADICIONE AQUI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
# ══════════════════════════════════════════════════════════════════════════════
# AUTH CENSO — Login via Pixeon + Permissões próprias
# Cole no main.py
# ══════════════════════════════════════════════════════════════════════════════

import hashlib, hmac
import sqlite3
from pydantic import BaseModel
from fastapi import HTTPException

# ── Todos os módulos disponíveis no sistema ───────────────────────────────────
TODOS_MODULOS = [
    {"id": "clinica",       "label": "Clínica"},
    {"id": "atendimento",   "label": "Atendimento (médico)"},
    {"id": "laboratorio",   "label": "Laboratório"},
    {"id": "recepcao",      "label": "Recepção"},
    {"id": "producao",      "label": "Produção Mensal"},
    {"id": "pacientesdb",   "label": "Pacientes"},
    {"id": "estoque",       "label": "Estoque"},
    {"id": "painel_tv",     "label": "Painel TV"},
    {"id": "contratos",     "label": "Contratos"},
    {"id": "faturamento",   "label": "Faturamento (Guias)"},
]

# ── Cria tabela de permissões se não existir ──────────────────────────────────
def inicializar_tabela_permissoes():
    """
    Cria a tabela censo_permissoes no banco Smart se não existir.
    Chame esta função no startup do FastAPI.
    """
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("""
            IF NOT EXISTS (
                SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_NAME = 'censo_permissoes'
            )
            CREATE TABLE censo_permissoes (
                cp_login      VARCHAR(20)   NOT NULL,
                cp_modulo     VARCHAR(30)   NOT NULL,
                cp_ativo      CHAR(1)       NOT NULL DEFAULT 'S',
                cp_dthr_alt   DATETIME      NOT NULL DEFAULT GETDATE(),
                cp_login_alt  VARCHAR(20)   NULL,
                CONSTRAINT PK_censo_permissoes PRIMARY KEY (cp_login, cp_modulo)
            )
        """)
        conn.commit()
        conn.close()
        print("[Auth] Tabela censo_permissoes OK")
    except Exception as e:
        print(f"[Auth] Erro ao criar tabela: {e}")


# ── Faturamento (Guias Pendentes) — SQLite próprio do Dashboard ───────────────
GUIAS_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guias.db")

def get_conn_guias():
    conn = sqlite3.connect(GUIAS_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def inicializar_db_guias():
    """
    Cria o banco SQLite guias.db (próprio do Dashboard, fora do Smart) e a
    tabela guias_pendentes, se não existirem. Chame esta função no startup.
    """
    try:
        conn = get_conn_guias()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS guias_pendentes (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                data             TEXT    NOT NULL,
                paciente         TEXT    NOT NULL,
                os_serie         INTEGER,
                os_num           INTEGER,
                tipo_exame       TEXT,
                valor            REAL,
                setor            TEXT,
                convenio         TEXT,
                status           TEXT    NOT NULL DEFAULT 'Pendente'
                                 CHECK (status IN ('Pendente','Entregue','Cancelada')),
                data_entrega     TEXT,
                data_faturamento TEXT,
                observacao       TEXT,
                criado_em        TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                criado_por       TEXT,
                atualizado_em    TEXT,
                atualizado_por   TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_guias_status ON guias_pendentes(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_guias_os ON guias_pendentes(os_serie, os_num)")
        conn.commit()
        conn.close()
        print("[Faturamento] Banco guias.db OK")
    except Exception as e:
        print(f"[Faturamento] Erro ao criar guias.db: {e}")


ORGANOGRAMA_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "organograma.db")

def get_conn_organograma():
    conn = sqlite3.connect(ORGANOGRAMA_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def inicializar_db_organograma():
    """
    Cria o banco SQLite organograma.db (próprio do Dashboard, fora do Smart)
    e a tabela org_nos, se não existirem. Chame esta função no startup.
    Estrutura livre (não hierárquica-forçada): cada nó tem posição própria
    (pos_x, pos_y) no canvas do editor e um pai_id opcional (pra desenhar a
    linha de conexão) — permite reorganizar visualmente sem depender de
    layout automático.
    """
    try:
        conn = get_conn_organograma()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS org_nos (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                nome          TEXT    NOT NULL,
                cargo         TEXT,
                setor         TEXT,
                pai_id        INTEGER REFERENCES org_nos(id) ON DELETE SET NULL,
                pos_x         REAL    NOT NULL DEFAULT 0,
                pos_y         REAL    NOT NULL DEFAULT 0,
                cor           TEXT,
                criado_em     TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                atualizado_em TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_org_nos_pai ON org_nos(pai_id)")

        # Migração: largura/altura por nó (redimensionável) — colunas adicionadas
        # depois da criação inicial da tabela, checagem evita erro em bases já existentes.
        colunas = {r["name"] for r in conn.execute("PRAGMA table_info(org_nos)").fetchall()}
        if "largura" not in colunas:
            conn.execute("ALTER TABLE org_nos ADD COLUMN largura REAL NOT NULL DEFAULT 190")
        if "altura" not in colunas:
            conn.execute("ALTER TABLE org_nos ADD COLUMN altura REAL NOT NULL DEFAULT 78")

        conn.commit()
        conn.close()
        print("[Gestão] Banco organograma.db OK")
    except Exception as e:
        print(f"[Gestão] Erro ao criar organograma.db: {e}")


# ── Adicione no startup do FastAPI ────────────────────────────────────────────
# @app.on_event("startup")
# async def startup_event():
#     inicializar_tabela_permissoes()
#     inicializar_db_guias()
#     ... resto do startup


# ── Helpers de senha ──────────────────────────────────────────────────────────
def verificar_senha_pixeon(senha: str, hash_banco: str, salt: str) -> bool:
    if not hash_banco or not salt:
        return False
    tentativa = hashlib.sha256((salt + senha).encode("utf-8")).hexdigest()
    return hmac.compare_digest(tentativa.lower(), hash_banco.lower())

def verificar_senha_md5(senha: str, hash_banco: str) -> bool:
    if not hash_banco:
        return False
    tentativa = hashlib.md5(senha.encode("utf-8")).hexdigest()
    return hmac.compare_digest(tentativa.lower(), hash_banco.lower())

def get_modulos_usuario(login: str) -> list:
    """Busca módulos permitidos na tabela censo_permissoes."""
    rows = query(
        "SELECT cp_modulo FROM censo_permissoes WHERE RTRIM(cp_login)=? AND cp_ativo='S'",
        (login.strip(),)
    )
    mods = [r["cp_modulo"] for r in rows]
    # Migração: laboratorio saiu do clinica — concede acesso automaticamente
    if "clinica" in mods and "laboratorio" not in mods:
        mods.append("laboratorio")
    return mods

def is_admin_censo(login: str) -> bool:
    """Verifica se o usuário é admin do Censo (nível 3 no Pixeon)."""
    rows = query(
        "SELECT RTRIM(USR_NIVEL) AS nivel FROM usr WHERE RTRIM(USR_LOGIN)=?",
        (login.strip(),)
    )
    if not rows:
        return False
    return str(rows[0].get("nivel") or "").strip() == "3"


# ── ENDPOINT: Login ───────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    login: str
    senha: str

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

# ── SERVE FRONTEND REACT ──────────────────────────────────────────────────────
DIST = r"C:\Dashboard\frontend\dist"

def _call_openai(prompt: str, system: str = None) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return "Configure a variável OPENAI_API_KEY no servidor."
    if system is None:
        system = (
            "Você é um analista de gestão clínica com expertise financeira e operacional. "
            "Gere insights diretos, profissionais e acionáveis em português brasileiro. "
            "Sem markdown, apenas texto corrido."
        )
    res = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "gpt-4o-mini",
            "max_tokens": 300,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
        },
        timeout=30,
    )
    data = res.json()
    return data["choices"][0]["message"]["content"]

@app.post("/api/briefing")
def briefing_generico(payload: dict):
    try:
        return {"texto": _call_openai(payload.get("prompt", ""))}
    except Exception as e:
        return {"texto": f"Erro: {str(e)}"}

@app.post("/api/home/briefing")
def home_briefing(payload: dict):
    try:
        return {"texto": _call_openai(payload.get("prompt", ""))}
    except Exception as e:
        return {"texto": f"Erro: {str(e)}"}

@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    if not req.login.strip() or not req.senha:
        raise HTTPException(400, "Login e senha obrigatórios")

    # Busca usuário no Pixeon
    rows = query("""
        SELECT
            RTRIM(USR_LOGIN)       AS login,
            RTRIM(USR_NOME)        AS nome,
            USR_NOME_COMPLETO      AS nome_completo,
            RTRIM(USR_NIVEL)       AS nivel,
            RTRIM(USR_STATUS)      AS status,
            RTRIM(USR_SENHA)       AS senha_md5,
            RTRIM(USR_SENHA_HASH)  AS senha_hash,
            RTRIM(usr_salt_hash)   AS salt,
            USR_EMAIL              AS email,
            USR_PSV                AS psv_cod
        FROM usr
        WHERE RTRIM(USR_LOGIN) = ?
    """, (req.login.strip(),))

    if not rows:
        raise HTTPException(401, "Usuário não encontrado")

    u = rows[0]

    # Verifica status
    status = str(u.get("status") or "").strip().upper()
    if status and status not in ("A", ""):
        raise HTTPException(403, "Usuário inativo ou bloqueado")

    # Verifica senha — SHA-256+salt primeiro, fallback MD5
    autenticado = verificar_senha_pixeon(req.senha, u.get("senha_hash") or "", u.get("salt") or "")
    if not autenticado:
        autenticado = verificar_senha_md5(req.senha, u.get("senha_hash") or "")
    if not autenticado:
        senha_raw = str(u.get("senha_md5") or "").strip()
        autenticado = req.senha.strip() == senha_raw

    # Atualiza último login
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute(
            "UPDATE usr SET usr_dt_last_login=GETDATE() WHERE RTRIM(USR_LOGIN)=?",
            (req.login.strip(),)
        )
        conn.commit()
        conn.close()
    except:
        pass

    login_str = str(u["login"]).strip()
    modulos   = get_modulos_usuario(login_str)
    admin     = is_admin_censo(login_str)

    # Admin sempre vê todos os módulos
    if admin:
        modulos = [m["id"] for m in TODOS_MODULOS]

    return {
        "ok":      True,
        "login":   login_str,
        "nome":    (u.get("nome_completo") or u.get("nome") or login_str).strip(),
        "nivel":   str(u.get("nivel") or "").strip(),
        "email":   str(u.get("email") or "").strip(),
        "admin":   admin,
        "modulos": modulos,
        "psv_cod": u.get("psv_cod"),
    }
# Adicione este endpoint no main.py

@app.get("/api/home/resumo")
def home_resumo(periodo: str = "30d", setor: str = "todos"):
    from datetime import datetime, date
    import calendar

    inicio, fim = periodo_datas(periodo)

    d_ini = datetime.strptime(inicio, "%Y-%m-%d")
    d_fim = datetime.strptime(fim,    "%Y-%m-%d")
    delta = (d_fim - d_ini).days + 1
    ant_fim = d_ini - timedelta(days=1)
    ant_ini = ant_fim - timedelta(days=delta - 1)
    ant_inicio_str = ant_ini.strftime("%Y-%m-%d")
    ant_fim_str    = ant_fim.strftime("%Y-%m-%d")

    vliq = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"

    SETOR_MAP = {
        "assistencial": "('ASS','EME','CRG','TAM')",
        "ocupacional":  "('ADM','PER','DEM','RTB','MDF','MOC')",
        "diagnostico":  "('ASS','EME','CRG','TAM','ADM','PER','DEM','RTB','MDF','MOC')",
        "rci":          "('ASS','EME','CRG','TAM','ADM','PER','DEM','RTB','MDF','MOC')",
        "todos":        "('ASS','EME','CRG','TAM','ADM','PER','DEM','RTB','MDF','MOC')",
    }
    af = SETOR_MAP.get(setor, SETOR_MAP["todos"])

    diag_filter = ""
    if setor == "diagnostico":
        diag_filter = "AND RTRIM(osm.osm_str) = 'RDI'"
    elif setor == "rci":
        diag_filter = "AND RTRIM(osm.osm_str) = 'RCI'"

    def kpis_periodo(ini, fim_p):
        r = query(f"""
            SELECT
                COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS total_os,
                COUNT(DISTINCT osm.osm_pac)                        AS pacientes,
                ISNULL(SUM({vliq}), 0)                             AS producao,
                ISNULL(SUM({vliq}), 0) / NULLIF(COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num), 0) AS ticket_medio
            FROM osm
            JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
            WHERE osm.osm_dthr BETWEEN '{ini}' AND '{fim_p} 23:59:59'
              AND osm.osm_atend IN {af}
              AND smm.SMM_SFAT IN ('A','F','P')
              {diag_filter}
        """)
        return r[0] if r else {}

    kpis_atual    = kpis_periodo(inicio, fim)
    kpis_anterior = kpis_periodo(ant_inicio_str, ant_fim_str)

    # Produção por dia
    por_dia = query(f"""
        SELECT
            CAST(osm.osm_dthr AS DATE)                         AS data,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS os,
            ISNULL(SUM({vliq}), 0)                             AS producao
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN {af}
          AND smm.SMM_SFAT IN ('A','F','P')
          {diag_filter}
        GROUP BY CAST(osm.osm_dthr AS DATE)
        ORDER BY data
    """)
    for r in por_dia:
        if hasattr(r.get("data"), "strftime"):
            r["data"] = r["data"].strftime("%Y-%m-%d")

    # Top convênios
    top_convenios = query(f"""
        SELECT TOP 8
            RTRIM(cnv.cnv_nome)                                AS convenio,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS os,
            COUNT(DISTINCT osm.osm_pac)                        AS pacientes,
            ISNULL(SUM({vliq}), 0)                             AS producao
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        JOIN cnv ON cnv.cnv_cod=osm.osm_cnv
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN {af}
          AND smm.SMM_SFAT IN ('A','F','P')
          {diag_filter}
        GROUP BY RTRIM(cnv.cnv_nome)
        ORDER BY producao DESC
    """)

    # Top profissionais
    top_profissionais = query(f"""
        SELECT TOP 10
            RTRIM(psv.psv_apel)                                AS profissional,
            RTRIM(psv.psv_nome)                                AS nome_completo,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS os,
            COUNT(DISTINCT osm.osm_pac)                        AS pacientes,
            ISNULL(SUM({vliq}), 0)                             AS producao
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        JOIN psv ON psv.psv_cod=osm.osm_mreq
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN {af}
          AND smm.SMM_SFAT IN ('A','F','P')
          AND osm.osm_mreq IS NOT NULL
          {diag_filter}
        GROUP BY RTRIM(psv.psv_apel), RTRIM(psv.psv_nome)
        ORDER BY producao DESC
    """)

    # Absenteísmo
    absenteismo = {}
    if setor in ("assistencial", "todos"):
        abs_data = query(f"""
            SELECT
                SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B') THEN 1 ELSE 0 END) AS marcacoes,
                SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B')
                     AND agm.agm_stat <> 'E' AND agm.AGM_OSM_SERIE IS NULL THEN 1 ELSE 0 END)      AS faltantes,
                SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat='C' THEN 1 ELSE 0 END)              AS cancelados
            FROM agm
            WHERE agm.agm_hini BETWEEN '{inicio}' AND '{fim} 23:59:59'
        """)
        absenteismo = abs_data[0] if abs_data else {}

    # KPIs por setor (sempre usa todos os setores para comparação)
    setores_kpi = query(f"""
        SELECT
            CASE
                WHEN osm.osm_atend IN ('ASS','EME','CRG','TAM')             THEN 'Assistencial'
                WHEN osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC') THEN 'Ocupacional'
                ELSE 'Outros'
            END AS setor,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS os,
            ISNULL(SUM({vliq}), 0)                             AS producao
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ('ASS','EME','CRG','TAM','ADM','PER','DEM','RTB','MDF','MOC')
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY CASE
            WHEN osm.osm_atend IN ('ASS','EME','CRG','TAM')             THEN 'Assistencial'
            WHEN osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC') THEN 'Ocupacional'
            ELSE 'Outros'
        END
        ORDER BY producao DESC
    """)

    # KPI Diagnóstico separado
    diag_kpi = query(f"""
        SELECT
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS os,
            ISNULL(SUM({vliq}), 0)                             AS producao
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ('ASS','EME','CRG','TAM')
          AND RTRIM(smm.SMM_ESP) = 'LAB'
          AND smm.SMM_SFAT IN ('A','F','P')
    """)
    if diag_kpi:
        setores_kpi.append({"setor": "Diagnóstico", "os": diag_kpi[0]["os"], "producao": diag_kpi[0]["producao"]})

    # Projeção do mês — sábado pesa proporcionalmente menos que um dia de
    # semana (meta_sabado / meta_diaria), mesmo critério usado no módulo
    # Produção Mensal e nas mensagens de WhatsApp, pra não superestimar a
    # projeção em meses com mais sábados.
    hoje = date.today()
    prod_acumulada = kpis_atual.get("producao", 0) or 0
    total_dias_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    _metas_prod  = _load_metas().get("producao", {}) or {}
    _meta_diaria_cfg = _metas_prod.get("meta_diaria") or 48000.0
    _meta_sabado_cfg = _metas_prod.get("meta_sabado") or _meta_diaria_cfg
    _peso_sab = (_meta_sabado_cfg / _meta_diaria_cfg) if _meta_diaria_cfg else 1.0

    def _peso_dia_mes(d):
        wd = date(hoje.year, hoje.month, d).weekday()
        if wd == 6:  # domingo
            return 0.0
        if wd == 5:  # sabado
            return _peso_sab
        return 1.0

    dias_uteis_passados = sum(_peso_dia_mes(d) for d in range(1, hoje.day + 1))
    dias_restantes = sum(_peso_dia_mes(d) for d in range(hoje.day + 1, total_dias_mes + 1))
    media_diaria = prod_acumulada / dias_uteis_passados if dias_uteis_passados > 0 else 0
    projecao_mes = prod_acumulada + (media_diaria * dias_restantes)

    def var_pct(atual, anterior):
        if not anterior or anterior == 0:
            return None
        return round(((atual - anterior) / anterior) * 100, 1)

    variacoes = {
        "producao":     var_pct(kpis_atual.get("producao", 0),     kpis_anterior.get("producao", 0)),
        "total_os":     var_pct(kpis_atual.get("total_os", 0),      kpis_anterior.get("total_os", 0)),
        "pacientes":    var_pct(kpis_atual.get("pacientes", 0),     kpis_anterior.get("pacientes", 0)),
        "ticket_medio": var_pct(kpis_atual.get("ticket_medio", 0),  kpis_anterior.get("ticket_medio", 0)),
    }

    return {
        "kpis":              kpis_atual,
        "kpis_anterior":     kpis_anterior,
        "variacoes":         variacoes,
        "por_dia":           por_dia,
        "top_convenios":     top_convenios,
        "top_profissionais": top_profissionais,
        "absenteismo":       absenteismo,
        "setores_kpi":       setores_kpi,
        "projecao": {
            "valor":               round(projecao_mes, 2),
            "media_diaria":        round(media_diaria, 2),
            "dias_uteis_passados": round(dias_uteis_passados, 1),
            "dias_restantes":      round(dias_restantes),
            "acumulado":           round(prod_acumulada, 2),
        },
        "setor":   setor,
        "periodo": periodo,
    }


# Recepções exibidas lado a lado no Dashboard Clínica (osm_str)
RECEPCOES_HOME = [
    {"cod": "RCN", "nome": "Consultórios"},
    {"cod": "RDI", "nome": "Diagnóstico"},
    {"cod": "RCI", "nome": "Censo Imagem"},
]

@app.get("/api/home/por-recepcao")
def home_por_recepcao(periodo: str = "30d"):
    """KPIs (produção, pacientes, OSs, ticket médio) quebrados por recepção — Consultórios, Diagnóstico, Censo Imagem."""
    inicio, fim = periodo_datas(periodo)
    vliq = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"

    rows = query(f"""
        SELECT
            RTRIM(osm.osm_str)                                     AS cod,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)     AS total_os,
            COUNT(DISTINCT osm.osm_pac)                            AS pacientes,
            SUM({vliq})                                            AS producao,
            SUM({vliq}) / NULLIF(COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num),0) AS ticket_medio
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
          AND RTRIM(osm.osm_str) IN ({",".join(f"'{r['cod']}'" for r in RECEPCOES_HOME)})
        GROUP BY RTRIM(osm.osm_str)
    """)
    por_cod = {r["cod"]: r for r in rows}

    resultado = []
    for r in RECEPCOES_HOME:
        d = por_cod.get(r["cod"], {})
        resultado.append({
            "cod": r["cod"],
            "nome": r["nome"],
            "producao": float(d.get("producao") or 0),
            "pacientes": d.get("pacientes") or 0,
            "total_os": d.get("total_os") or 0,
            "ticket_medio": float(d.get("ticket_medio") or 0),
        })
    return resultado


# ── ENDPOINT: Listar usuários com permissões ──────────────────────────────────
@app.get("/api/auth/usuarios")
def auth_usuarios(busca: str = ""):
    """Lista usuários do Pixeon com suas permissões no Censo."""
    filtro = f"AND (RTRIM(u.USR_NOME) LIKE '%{busca}%' OR RTRIM(u.USR_LOGIN) LIKE '%{busca}%')" if busca else ""
    rows = query(f"""
        SELECT TOP 100
            RTRIM(u.USR_LOGIN)        AS login,
            RTRIM(u.USR_NOME)         AS nome,
            u.USR_NOME_COMPLETO       AS nome_completo,
            RTRIM(u.USR_NIVEL)        AS nivel,
            RTRIM(u.USR_STATUS)       AS status,
            u.USR_EMAIL               AS email,
            u.usr_dt_last_login       AS ultimo_login,
            RTRIM(u.USR_GRP)          AS grupo_cod,
            RTRIM(ISNULL(g.GRP_DESCR,'')) AS grupo_nome
        FROM usr u
        LEFT JOIN GRP g ON RTRIM(g.GRP_COD) = RTRIM(u.USR_GRP)
        WHERE RTRIM(u.USR_STATUS) = 'A'
          AND u.USR_LOGIN IS NOT NULL
          AND LTRIM(RTRIM(u.USR_LOGIN)) <> ''
          {filtro}
        ORDER BY RTRIM(u.USR_NOME)
    """)

    # Para cada usuário, busca seus módulos
    for r in rows:
        login = str(r["login"]).strip()
        modulos = query(
            "SELECT cp_modulo FROM censo_permissoes WHERE RTRIM(cp_login)=? AND cp_ativo='S'",
            (login,)
        )
        r["modulos"] = [m["cp_modulo"] for m in modulos]
        r["admin"]   = str(r.get("nivel") or "").strip() == "3"
        if r.get("ultimo_login") and hasattr(r["ultimo_login"], "strftime"):
            r["ultimo_login"] = r["ultimo_login"].strftime("%d/%m/%Y %H:%M")

    return rows

@app.get("/api/auth/grupos")
def auth_grupos():
    """Lista os perfis/grupos de usuário do Pixeon (tabela GRP) — usado pra
    selecionar em massa, ex: todo mundo do perfil 'Recepção'."""
    return query("""
        SELECT RTRIM(GRP_COD) AS cod, RTRIM(GRP_DESCR) AS nome
        FROM GRP WHERE ISNULL(GRP_DEL_LOGICA,'N') <> 'S'
        ORDER BY RTRIM(GRP_DESCR)
    """)

@app.get("/api/auth/usuarios-por-grupo")
def auth_usuarios_por_grupo(grp: str):
    """Todos os logins ativos de um perfil/grupo do Pixeon (sem limite de
    100 como a listagem padrão) — usado pela ação 'selecionar perfil'."""
    rows = query("""
        SELECT RTRIM(USR_LOGIN) AS login, RTRIM(USR_NOME) AS nome
        FROM usr
        WHERE RTRIM(USR_STATUS) = 'A' AND RTRIM(USR_GRP) = ?
          AND USR_LOGIN IS NOT NULL AND LTRIM(RTRIM(USR_LOGIN)) <> ''
        ORDER BY RTRIM(USR_NOME)
    """, (grp.strip(),))
    return {"total": len(rows), "usuarios": rows}


# ── CHAT INTERNO — canais por setor + mensagens diretas entre usuários ───────
@app.get("/api/chat/usuarios")
def chat_usuarios(busca: str = None):
    """Lista de usuários ativos do Dashboard pra iniciar uma nova DM."""
    filtro = ""
    params = []
    if busca:
        filtro = "AND RTRIM(USR_NOME) LIKE ?"
        params.append(f"%{busca}%")
    rows = query(f"""
        SELECT RTRIM(USR_LOGIN) AS login, RTRIM(USR_NOME) AS nome
        FROM usr
        WHERE RTRIM(USR_STATUS) = 'A'
          AND USR_LOGIN IS NOT NULL AND LTRIM(RTRIM(USR_LOGIN)) <> ''
          {filtro}
        ORDER BY RTRIM(USR_NOME)
    """, tuple(params))
    return {"total": len(rows), "usuarios": rows}


@app.get("/api/chat/canais")
def chat_canais(login: str):
    from chat_interno import listar_canais
    return listar_canais(login)


@app.get("/api/chat/mensagens")
def chat_mensagens(canal: str, limite: int = 100):
    from chat_interno import listar_mensagens
    return listar_mensagens(canal, limite)


class ChatEnviarRequest(BaseModel):
    canal_id: str
    remetente_login: str
    remetente_nome: str
    texto: str
    importante: bool = False


@app.post("/api/chat/mensagens")
def chat_enviar(payload: ChatEnviarRequest):
    from chat_interno import enviar_mensagem
    try:
        return enviar_mensagem(payload.canal_id, payload.remetente_login, payload.remetente_nome, payload.texto, payload.importante)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/chat/alertas")
def chat_alertas(login: str):
    """Mensagens importantes ainda não vistas por esse login, em qualquer
    canal que ele enxergue — usado pelo popup global (aparece em qualquer
    tela do Dashboard, não só dentro do chat)."""
    from chat_interno import listar_alertas_novos
    return listar_alertas_novos(login)


class ChatAlertaVistoRequest(BaseModel):
    login: str
    mensagem_id: int


@app.post("/api/chat/alertas/marcar-visto")
def chat_alerta_marcar_visto(payload: ChatAlertaVistoRequest):
    from chat_interno import marcar_alerta_visto
    marcar_alerta_visto(payload.login, payload.mensagem_id)
    return {"ok": True}


class ChatDmIniciarRequest(BaseModel):
    login_a: str
    nome_a: str
    login_b: str
    nome_b: str


@app.post("/api/chat/dm/iniciar")
def chat_dm_iniciar(payload: ChatDmIniciarRequest):
    from chat_interno import obter_ou_criar_dm
    canal_id = obter_ou_criar_dm(payload.login_a, payload.nome_a, payload.login_b, payload.nome_b)
    return {"canal_id": canal_id}


class ChatGrupoCriarRequest(BaseModel):
    nome: str
    criador_login: str
    criador_nome: str
    participantes: list  # [{"login": ..., "nome": ...}, ...]


@app.post("/api/chat/grupo/criar")
def chat_grupo_criar(payload: ChatGrupoCriarRequest):
    from chat_interno import criar_grupo
    try:
        canal_id = criar_grupo(payload.nome, payload.criador_login, payload.criador_nome, payload.participantes)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"canal_id": canal_id}


@app.get("/api/chat/grupo/participantes")
def chat_grupo_participantes(canal: str):
    from chat_interno import listar_participantes
    return listar_participantes(canal)


class ChatLidoRequest(BaseModel):
    canal_id: str
    login: str


@app.post("/api/chat/marcar-lido")
def chat_marcar_lido(payload: ChatLidoRequest):
    from chat_interno import marcar_lido
    marcar_lido(payload.canal_id, payload.login)
    return {"ok": True}


# ── ENDPOINT: Salvar permissões de um usuário ─────────────────────────────────
class PermissaoRequest(BaseModel):
    login:       str
    modulos:     list   # lista de IDs de módulos permitidos
    login_admin: str    # quem está alterando

@app.post("/api/auth/permissoes")
def salvar_permissoes(req: PermissaoRequest):
    """
    Substitui os módulos de um usuário.
    Recebe a lista completa de módulos permitidos.
    """
    login = req.login.strip()
    if not login:
        raise HTTPException(400, "Login obrigatório")

    # Verifica se usuário existe no Pixeon
    existe = query("SELECT 1 AS ok FROM usr WHERE RTRIM(USR_LOGIN)=?", (login,))
    if not existe:
        raise HTTPException(404, "Usuário não encontrado no Pixeon")

    conn = get_conn()
    cur  = conn.cursor()
    try:
        # Remove todas as permissões atuais
        cur.execute(
            "DELETE FROM censo_permissoes WHERE RTRIM(cp_login)=?",
            (login,)
        )
        # Insere as novas
        for modulo in req.modulos:
            cur.execute("""
                INSERT INTO censo_permissoes (cp_login, cp_modulo, cp_ativo, cp_dthr_alt, cp_login_alt)
                VALUES (?, ?, 'S', GETDATE(), ?)
            """, (login, modulo, req.login_admin.strip()))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Erro ao salvar: {e}")
    finally:
        conn.close()

    return {"ok": True, "login": login, "modulos": req.modulos}


# ── ENDPOINT: Módulos disponíveis ─────────────────────────────────────────────
@app.get("/api/auth/modulos")
def auth_modulos():
    """Retorna lista de todos os módulos do sistema."""
    return TODOS_MODULOS

@app.get("/api/auth/diagnostico/{login}")
def auth_diagnostico(login: str):
    """Diagnóstico: mostra nivel, admin e módulos de um usuário."""
    from fastapi.responses import JSONResponse
    rows = query("SELECT RTRIM(USR_NIVEL) AS nivel FROM usr WHERE RTRIM(USR_LOGIN)=?", (login.strip(),))
    nivel = str(rows[0].get("nivel") or "").strip() if rows else "não encontrado"
    admin = nivel == "3"
    mods  = get_modulos_usuario(login.strip())
    return JSONResponse({"login": login, "nivel_pixeon": nivel, "admin": admin, "modulos": mods})

[{
	"resource": "/c:/Dashboard/backend/main.py",
	"owner": "Pylance4",
	"code": {
		"value": "reportUndefinedVariable",
		"target": {
			"$mid": 1,
			"path": "/microsoft/pylance-release/blob/main/docs/diagnostics/reportUndefinedVariable.md",
			"scheme": "https",
			"authority": "github.com"
		}
	},
	"severity": 4,
	"message": "\"app\" is not defined",
	"source": "Pylance",
	"startLineNumber": 126,
	"startColumn": 2,
	"endLineNumber": 126,
	"endColumn": 5,
	"modelVersionId": 194,
	"origin": "extHost1"
},{
	"resource": "/c:/Dashboard/backend/main.py",
	"owner": "Pylance4",
	"code": {
		"value": "reportUndefinedVariable",
		"target": {
			"$mid": 1,
			"path": "/microsoft/pylance-release/blob/main/docs/diagnostics/reportUndefinedVariable.md",
			"scheme": "https",
			"authority": "github.com"
		}
	},
	"severity": 4,
	"message": "\"app\" is not defined",
	"source": "Pylance",
	"startLineNumber": 197,
	"startColumn": 2,
	"endLineNumber": 197,
	"endColumn": 5,
	"modelVersionId": 194,
	"origin": "extHost1"
},{
	"resource": "/c:/Dashboard/backend/main.py",
	"owner": "Pylance4",
	"code": {
		"value": "reportUndefinedVariable",
		"target": {
			"$mid": 1,
			"path": "/microsoft/pylance-release/blob/main/docs/diagnostics/reportUndefinedVariable.md",
			"scheme": "https",
			"authority": "github.com"
		}
	},
	"severity": 4,
	"message": "\"app\" is not defined",
	"source": "Pylance",
	"startLineNumber": 239,
	"startColumn": 2,
	"endLineNumber": 239,
	"endColumn": 5,
	"modelVersionId": 194,
	"origin": "extHost1"
},{
	"resource": "/c:/Dashboard/backend/main.py",
	"owner": "Pylance4",
	"code": {
		"value": "reportUndefinedVariable",
		"target": {
			"$mid": 1,
			"path": "/microsoft/pylance-release/blob/main/docs/diagnostics/reportUndefinedVariable.md",
			"scheme": "https",
			"authority": "github.com"
		}
	},
	"severity": 4,
	"message": "\"app\" is not defined",
	"source": "Pylance",
	"startLineNumber": 279,
	"startColumn": 2,
	"endLineNumber": 279,
	"endColumn": 5,
	"modelVersionId": 194,
	"origin": "extHost1"
}]

@app.on_event("startup")
async def startup_event():
     # Carrega .env
    env_path = r"C:\Dashboard\backend\.env"
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")
    print("OPENAI KEY no startup:", os.environ.get("OPENAI_API_KEY", "NAO")[:10])

    inicializar_tabela_permissoes()
    inicializar_db_guias()
    inicializar_db_organograma()
    try:
        from agenda_bot import inicializar_db as inicializar_db_agenda_bot
        inicializar_db_agenda_bot()
    except Exception as e:
        print(f"[Startup] Erro ao iniciar DB do agenda_bot: {e}")
    try:
        from chat_interno import inicializar_db as inicializar_db_chat
        inicializar_db_chat()
    except Exception as e:
        print(f"[Startup] Erro ao iniciar DB do chat_interno: {e}")
    if _WPP_AVAILABLE:
        try:
            from scheduler import set_query_func, iniciar_scheduler_em_background
            set_query_func(query)
            iniciar_scheduler_em_background()
            print("[Startup] Scheduler WhatsApp iniciado.")
        except Exception as e:
            print(f"[Startup] Erro ao iniciar scheduler: {e}")


# ─── Conexão SQL Server ────────────────────────────────────────────────────────
def get_conn():
    conn_str = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=tcp:192.168.1.9,1433;"
        "DATABASE=SMART;"
        "UID=smart;"
        "PWD=smart@pixeon16;"
        "TrustServerCertificate=yes;"
        "Encrypt=no;"
    )
    return pyodbc.connect(conn_str)

def query(sql: str, params: tuple = ()):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    cols = [col[0] for col in cursor.description]
    rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_conn_hml():
    """Conexão com o banco de HOMOLOGAÇÃO (smart_hml) — usado para ESCRITA de
    registros clínicos (RCL) até validação/aprovação para produção. Nunca usar
    para leitura de dados operacionais reais (fila, histórico) — isso é sempre
    lido da produção (get_conn/query)."""
    conn_str = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=tcp:192.168.1.9,1433;"
        "DATABASE=smart_hml;"
        "UID=smart;"
        "PWD=smart@pixeon16;"
        "TrustServerCertificate=yes;"
        "Encrypt=no;"
    )
    return pyodbc.connect(conn_str)

# ─── Helpers de período ────────────────────────────────────────────────────────
PERIODOS = {"7d": 7, "30d": 30, "90d": 90}

def periodo_datas(periodo: str):
    """
    7d        → últimos 7 dias corridos
    30d       → mês atual completo (dia 1 até hoje)
    90d       → últimos 3 meses completos
    mes:YYYY-MM → mês específico completo (dia 1 até último dia)
    """
    import calendar as _cal
    now = datetime.now()

    if periodo and periodo.startswith("mes:"):
        # Formato: mes:2026-05
        try:
            ano_s, mes_s = periodo[4:].split("-")
            ano, mes = int(ano_s), int(mes_s)
            ultimo = _cal.monthrange(ano, mes)[1]
            inicio = f"{ano}-{mes:02d}-01"
            # Se for mês atual, vai só até hoje
            if ano == now.year and mes == now.month:
                fim = now.strftime("%Y-%m-%d")
            else:
                fim = f"{ano}-{mes:02d}-{ultimo}"
        except Exception:
            inicio = now.replace(day=1).strftime("%Y-%m-%d")
            fim    = now.strftime("%Y-%m-%d")
        return inicio, fim

    if periodo == "hoje":
        inicio = now.strftime("%Y-%m-%d")
        fim    = now.strftime("%Y-%m-%d")
    elif periodo == "7d":
        inicio = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        fim    = now.strftime("%Y-%m-%d")
    elif periodo == "30d":
        inicio = now.replace(day=1).strftime("%Y-%m-%d")
        fim    = now.strftime("%Y-%m-%d")
    elif periodo == "90d":
        mes_inicio = now.month - 2
        ano_inicio = now.year
        if mes_inicio <= 0:
            mes_inicio += 12
            ano_inicio -= 1
        inicio = now.replace(year=ano_inicio, month=mes_inicio, day=1).strftime("%Y-%m-%d")
        fim    = now.strftime("%Y-%m-%d")
    elif periodo == "ano":
        inicio = now.replace(month=1, day=1).strftime("%Y-%m-%d")
        fim    = now.strftime("%Y-%m-%d")
    elif periodo and periodo.startswith("custom:"):
        # Formato: custom:2026-01-01:2026-01-31
        try:
            parts = periodo[7:].split(":")
            inicio, fim = parts[0], parts[1]
        except Exception:
            inicio = now.replace(day=1).strftime("%Y-%m-%d")
            fim    = now.strftime("%Y-%m-%d")
    else:
        dias   = PERIODOS.get(periodo, 30)
        inicio = (now - timedelta(days=dias)).strftime("%Y-%m-%d")
        fim    = now.strftime("%Y-%m-%d")
    return inicio, fim

def periodo_anterior(inicio: str, fim: str):
    """Período imediatamente anterior, com a mesma duração — usado para comparação mês/período anterior."""
    d_ini = datetime.strptime(inicio, "%Y-%m-%d")
    d_fim = datetime.strptime(fim, "%Y-%m-%d")
    delta = (d_fim - d_ini).days + 1
    ant_fim = d_ini - timedelta(days=1)
    ant_ini = ant_fim - timedelta(days=delta - 1)
    return ant_ini.strftime("%Y-%m-%d"), ant_fim.strftime("%Y-%m-%d")

def var_pct(atual, anterior):
    """% de variação entre dois valores; None se não houver base de comparação."""
    try:
        atual = float(atual or 0)
        anterior = float(anterior or 0)
    except (TypeError, ValueError):
        return None
    if anterior == 0:
        return None
    return round(((atual - anterior) / anterior) * 100, 1)

def filtro_setores_sql(setores: str, alias_smm: str = "smm") -> str:
    """Gera cláusula WHERE para filtrar por setores (SMM_STR)."""
    if not setores:
        return ""
    lista = [f"'{s.strip()}'" for s in setores.split(",") if s.strip()]
    if not lista:
        return ""
    return f"AND {alias_smm}.SMM_STR IN ({','.join(lista)})"

def periodo_datas_ano(periodo: str, ano_offset: int = 0):
    """Mesmo período em ano anterior — mantém a lógica de mês cheio."""
    now  = datetime.now()
    try:
        base = now.replace(year=now.year + ano_offset)
    except ValueError:
        base = now.replace(year=now.year + ano_offset, day=28)

    if periodo == "7d":
        inicio = (base - timedelta(days=7)).strftime("%Y-%m-%d")
        fim    = base.strftime("%Y-%m-%d")
    elif periodo == "30d":
        inicio = base.replace(day=1).strftime("%Y-%m-%d")
        fim    = base.strftime("%Y-%m-%d")
    elif periodo == "90d":
        mes_inicio = base.month - 2
        ano_inicio = base.year
        if mes_inicio <= 0:
            mes_inicio += 12
            ano_inicio -= 1
        inicio = base.replace(year=ano_inicio, month=mes_inicio, day=1).strftime("%Y-%m-%d")
        fim    = base.strftime("%Y-%m-%d")
    else:
        dias   = PERIODOS.get(periodo, 30)
        inicio = (base - timedelta(days=dias)).strftime("%Y-%m-%d")
        fim    = base.strftime("%Y-%m-%d")
    return inicio, fim


# ══════════════════════════════════════════════════════════════════════════════
# MAPEAMENTO REAL DA TABELA osm (validado no dicionário Pixeon)
# ──────────────────────────────────────────────────────────────────────────────
# osm_serie   → chave primária (série)
# osm_num     → chave primária (número)
# osm_pac     → FK paciente (tabela pac)
# osm_dthr    → data e hora da OS  ← campo principal de data
# osm_dt_result → data do resultado
# osm_cnv     → FK convênio (tabela cnv, char 3)
# osm_mreq    → FK médico requisitante (tabela psv)
# osm_str     → FK setor solicitante (tabela str, char 3)
# osm_status  → status da OS (char 1)
# osm_atend   → tipo de atendimento:
#               ASS=Assistencial, ADM=Admissional, CRG=Cirurgia,
#               DEM=Demissional, EME=Emergência, INT=Internamento,
#               PER=Periódico, TAM=Trat.Ambulat, RTB=Ret.Trabalho,
#               ACT=Acid.Trabalho, MDF=Mud.Função, APC=APAC, S=Supletivo
# osm_hsp_num → FK internação (tabela hsp, nullable)
# osm_ind_urg → índice de urgência
# osm_pln_cod → plano do convênio (tabela pln)
# osm_dthr_saida → saída (emergência)
# OSM_AGM_ID  → FK agendamento (tabela agm)
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# FINANCEIRO — usa tabela smm (Itens da OS) — bate com relatório do Smart
# ──────────────────────────────────────────────────────────────────────────────
# SMM_OSM_SERIE + SMM_OSM → FK para osm (serie + num)
# SMM_VLR    → valor do item
# SMM_SFAT   → status: A=Aberto, F=Faturado, P=Pendente, C=Cancelado
# SMM_CNV_COD→ FK convênio
# Filtro validado: SMM_SFAT IN ('A','F','P') exclui só cancelados
# Bate exatamente com Conferência de Atendimentos do Smart
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/financeiro/resumo")
def financeiro_resumo(periodo: str = "30d", atend: str = "", setores: str = ""):
    inicio, fim = periodo_datas(periodo)
    filtro_atend   = f"AND osm.osm_atend = '{atend}'" if atend else ""
    filtro_setores = filtro_setores_sql(setores)
    rows = query(f"""
        SELECT
            COUNT(DISTINCT smm.SMM_OSM)             AS total_os,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                        AS faturamento,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) / NULLIF(COUNT(DISTINCT smm.SMM_OSM), 0) AS ticket_medio,
            SUM(CASE WHEN osm.osm_atend = 'ASS' THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS val_assistencial,
            -- Med. Ocupacional = ADM + PER + DEM + RTB + MDF + MOC (todos os subtipos)
            SUM(CASE WHEN osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC') THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS val_med_ocup,
            SUM(CASE WHEN osm.osm_atend = 'ADM' THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS val_admissional,
            SUM(CASE WHEN osm.osm_atend = 'PER' THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS val_periodico,
            SUM(CASE WHEN osm.osm_atend = 'DEM' THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS val_demissional,
            SUM(CASE WHEN osm.osm_atend = 'RTB' THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS val_ret_trabalho,
            SUM(CASE WHEN osm.osm_atend = 'MDF' THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS val_mud_funcao,
            SUM(CASE WHEN osm.osm_atend = 'EME' THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS val_emergencia,
            SUM(CASE WHEN osm.osm_atend = 'CRG' THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS val_cirurgia,
            SUM(CASE WHEN smm.SMM_SFAT  = 'F'   THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS val_faturado,
            SUM(CASE WHEN smm.SMM_SFAT  = 'A'   THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS val_aberto,
            SUM(CASE WHEN smm.SMM_SFAT  = 'P'   THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS val_pendente
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE
                AND osm.osm_num   = smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A', 'F', 'P')
          {filtro_atend}
          {filtro_setores}
    """)
    return rows[0] if rows else {}


@app.get("/api/financeiro/receita-mensal")
def receita_mensal(periodo: str = "30d", atend: str = ""):
    filtro_atend = f"AND osm.osm_atend = '{atend}'" if atend else ""
    rows = query(f"""
        SELECT
            FORMAT(osm.osm_dthr, 'yyyy-MM')     AS mes,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                    AS receita,
            COUNT(DISTINCT smm.SMM_OSM)         AS qtd_os,
            SUM(CASE WHEN smm.SMM_SFAT = 'F' THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS faturado,
            SUM(CASE WHEN smm.SMM_SFAT = 'A' THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS em_aberto,
            SUM(CASE WHEN smm.SMM_SFAT = 'P' THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS pendente
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE
                AND osm.osm_num   = smm.SMM_OSM
        WHERE osm.osm_dthr >= DATEADD(month, -6, GETDATE())
          AND smm.SMM_SFAT IN ('A', 'F', 'P')
          {filtro_atend}
        GROUP BY FORMAT(osm.osm_dthr, 'yyyy-MM')
        ORDER BY mes
    """)
    return rows


@app.get("/api/financeiro/por-convenio")
def receita_por_convenio(periodo: str = "30d", atend: str = "", setores: str = ""):
    """
    Usa osm.osm_cnv (FK principal do convênio na OS) — igual à tela de pacientes.
    smm.SMM_CNV_COD fica vazio em muitos registros, por isso apareciam poucos convênios.
    """
    inicio, fim = periodo_datas(periodo)
    filtro_atend   = f"AND osm.osm_atend = '{atend}'" if atend else ""
    filtro_setores = filtro_setores_sql(setores)
    rows = query(f"""
        SELECT
            cnv.cnv_nome                                AS nom_convenio,
            cnv.cnv_tipo                                AS tipo,
            COUNT(DISTINCT osm.osm_serie * 1000000
                         + osm.osm_num)                 AS qtd_os,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                            AS receita,
            SUM(CASE WHEN smm.SMM_SFAT = 'F' THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS faturado,
            SUM(CASE WHEN smm.SMM_SFAT = 'A' THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END) AS em_aberto
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE
                AND osm.osm_num   = smm.SMM_OSM
        JOIN cnv ON cnv.cnv_cod   = osm.osm_cnv
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A', 'F', 'P')
          AND cnv.cnv_nome IS NOT NULL
          AND LTRIM(RTRIM(cnv.cnv_nome)) <> ''
          {filtro_atend}
          {filtro_setores}
        GROUP BY cnv.cnv_nome, cnv.cnv_tipo
        ORDER BY receita DESC
    """)
    return rows


@app.get("/api/financeiro/por-tipo-convenio")
def receita_por_tipo_convenio(periodo: str = "30d", atend: str = ""):
    inicio, fim = periodo_datas(periodo)
    filtro_atend = f"AND osm.osm_atend = '{atend}'" if atend else ""
    TIPOS = {"AM": "Ambulatorial", "HP": "Hospitalar",
             "AH": "Ambul/Hosp",  "MC": "Med. Ocupacional"}
    rows = query(f"""
        SELECT
            cnv.cnv_tipo                            AS tipo_cod,
            COUNT(DISTINCT smm.SMM_OSM)             AS qtd_os,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                        AS receita
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE
                AND osm.osm_num   = smm.SMM_OSM
        JOIN cnv ON cnv.cnv_cod   = smm.SMM_CNV_COD
               AND cnv.cnv_stat   = 'A'
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A', 'F', 'P')
          {filtro_atend}
        GROUP BY cnv.cnv_tipo
        ORDER BY receita DESC
    """)
    for r in rows:
        r["tipo"] = TIPOS.get(r["tipo_cod"], r["tipo_cod"] or "Não informado")
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# ATENDIMENTOS  (tabela osm — campo osm_atend e osm_dthr)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/atendimentos/resumo")
def atendimentos_resumo(periodo: str = "30d", atend: str = "", setores: str = ""):
    inicio, fim = periodo_datas(periodo)
    filtro_atend   = f"AND osm.osm_atend = '{atend}'" if atend else ""
    filtro_setores = filtro_setores_sql(setores)
    rows = query(f"""
        SELECT
            COUNT(*)                                                        AS total_atendimentos,
            SUM(CASE WHEN osm.osm_atend = 'ASS' THEN 1 ELSE 0 END)        AS assistencial,
            SUM(CASE WHEN osm.osm_atend = 'INT' THEN 1 ELSE 0 END)        AS internamento,
            SUM(CASE WHEN osm.osm_atend = 'EME' THEN 1 ELSE 0 END)        AS emergencia,
            SUM(CASE WHEN osm.osm_atend = 'CRG' THEN 1 ELSE 0 END)        AS cirurgia,
            SUM(CASE WHEN osm.osm_atend = 'TAM' THEN 1 ELSE 0 END)        AS trat_ambulatorial,
            SUM(CASE WHEN osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC') THEN 1 ELSE 0 END) AS med_ocup,
            SUM(CASE WHEN osm.osm_atend = 'ADM' THEN 1 ELSE 0 END)        AS admissional,
            SUM(CASE WHEN osm.osm_atend = 'PER' THEN 1 ELSE 0 END)        AS periodico,
            SUM(CASE WHEN osm.osm_atend = 'DEM' THEN 1 ELSE 0 END)        AS demissional,
            SUM(CASE WHEN osm.osm_atend = 'RTB' THEN 1 ELSE 0 END)        AS ret_trabalho,
            SUM(CASE WHEN osm.osm_atend = 'MDF' THEN 1 ELSE 0 END)        AS mud_funcao,
            AVG(CASE
                WHEN osm.osm_atend = 'EME' AND osm.osm_dthr_saida IS NOT NULL
                THEN DATEDIFF(minute, osm.osm_dthr, osm.osm_dthr_saida)
                ELSE NULL
            END) AS media_min_emergencia
        FROM osm
        WHERE osm.osm_dthr BETWEEN ? AND ?
        {filtro_atend}
    """, (inicio, fim))
    return rows[0] if rows else {}


@app.get("/api/atendimentos/por-especialidade")
def atendimentos_por_especialidade(periodo: str = "30d", atend: str = "", setores: str = ""):
    inicio, fim = periodo_datas(periodo)
    filtro_atend   = f"AND osm.osm_atend = '{atend}'" if atend else ""
    filtro_setores = filtro_setores_sql(setores)
    rows = query(f"""
        SELECT
            ISNULL(esp.esp_nome, 'Não informado')                           AS especialidade,
            COUNT(DISTINCT osm.osm_serie * 1000000 + osm.osm_num)          AS qtd
        FROM osm
        LEFT JOIN psv ON psv.psv_cod  = osm.osm_mreq
        LEFT JOIN agm ON agm.agm_id   = osm.OSM_AGM_ID
        LEFT JOIN esp ON esp.esp_cod  = COALESCE(psv.psv_esp_cod, agm.AGM_ESP_COD)
        LEFT JOIN smm ON smm.SMM_OSM_SERIE = osm.osm_serie AND smm.SMM_OSM = osm.osm_num
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          {filtro_atend}
          {filtro_setores}
        GROUP BY ISNULL(esp.esp_nome, 'Não informado')
        HAVING COUNT(DISTINCT osm.osm_serie * 1000000 + osm.osm_num) > 0
        ORDER BY qtd DESC
    """)
    # Remove "Não informado" se for minoria
    total = sum(r["qtd"] for r in rows)
    rows = [r for r in rows if r["especialidade"] != "Não informado" or (total > 0 and r["qtd"] / total > 0.05)]
    return rows


@app.get("/api/atendimentos/por-dia")
def atendimentos_por_dia(periodo: str = "30d", atend: str = "", setores: str = ""):
    inicio, fim = periodo_datas(periodo)
    filtro_atend   = f"AND osm.osm_atend = '{atend}'" if atend else ""
    filtro_setores = filtro_setores_sql(setores)
    rows = query("""
        SELECT
            CAST(osm.osm_dthr AS DATE) AS data,
            COUNT(*)                   AS qtd
        FROM osm
        WHERE osm.osm_dthr BETWEEN ? AND ?
        GROUP BY CAST(osm.osm_dthr AS DATE)
        ORDER BY data
    """, (inicio, fim))
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# AGENDAMENTOS  (tabela agm — validada contra dicionário Pixeon)
# ──────────────────────────────────────────────────────────────────────────────
# Chave composta: agm_med + agm_loc + agm_hini + agm_pac + agm_tpsmk + agm_smk
# agm_med      → FK médico (psv)          — PK
# agm_pac      → FK paciente (pac.pac_reg) — PK
# agm_loc      → FK local (loc)            — PK
# agm_hini     → Horário Inicial (datetime) ← campo de data do agendamento
# agm_hfim     → Horário Final (datetime)
# agm_dtmrc    → Data Marcada (datetime)   ← data em que foi feita a marcação
# agm_stat     → Status: A=Aberta, E=Executada, C=Cancelada, B=Bloqueada
# agm_confirm_stat → A=Em Aberto, N=Não Confirmada, C=Confirmada
# agm_cnv_cod  → FK convênio
# agm_str_cod  → FK setor
# agm_pac_nome → nome denormalizado do paciente (varchar 100)
# agm_id       → ID único da marcação (int, nullable)
# AGM_ESP_COD  → FK especialidade (char 3)
# agm_psv_solic → médico solicitante
# agm_canc_dthr → data do cancelamento
# agm_valor    → valor da marcação
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/agendamentos/resumo")
def agendamentos_resumo(periodo: str = "30d"):
    """
    agm_hini = horário do agendamento (campo de data principal)
    agm_stat: A=Aberta, E=Executada, C=Cancelada, B=Bloqueada
    """
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            COUNT(*)                                                             AS total,
            SUM(CASE WHEN agm.agm_stat = 'E' THEN 1 ELSE 0 END)                AS realizados,
            SUM(CASE WHEN agm.agm_stat = 'A' THEN 1 ELSE 0 END)                AS em_aberto,
            SUM(CASE WHEN agm.agm_stat = 'C' THEN 1 ELSE 0 END)                AS cancelados,
            SUM(CASE WHEN agm.agm_stat = 'B' THEN 1 ELSE 0 END)                AS bloqueados,

            -- Taxa de execução = Executadas / Total marcadas (excl. bloqueados)
            CAST(
                100.0 * SUM(CASE WHEN agm.agm_stat = 'E' THEN 1 ELSE 0 END)
                      / NULLIF(SUM(CASE WHEN agm.agm_stat != 'B' THEN 1 ELSE 0 END), 0)
            AS DECIMAL(5,1))                                                     AS taxa_comparecimento,

            -- Valor total agendado no período
            ISNULL(SUM(agm.agm_valor), 0)                                       AS valor_total_agendado
        FROM agm
        WHERE agm.agm_hini BETWEEN ? AND ?
    """, (inicio, fim))
    return rows[0] if rows else {}


@app.get("/api/agendamentos/proximos")
def proximos_agendamentos(limite: int = 20):
    """
    psv_cod = PK (int), psv_nome = nome do médico (char 50)
    agm_med → FK para psv.psv_cod
    AGM_ESP_COD → FK para esp.esp_cod
    agm_pac_nome → nome denormalizado — evita JOIN com pac
    agm_hini → horário do atendimento
    agm_stat: A=Aberta, E=Executada
    agm_confirm_stat: A=Em Aberto, C=Confirmada, N=Não Confirmada
    """
    rows = query("""
        SELECT TOP (?)
            agm.agm_pac_nome                    AS nom_paciente,
            esp.esp_nome                        AS especialidade,
            psv.psv_nome                        AS medico,     -- psv_nome char 50
            psv.psv_apel                        AS medico_apelido,
            agm.agm_hini                        AS data_hora,
            agm.agm_hfim                        AS data_hora_fim,
            agm.agm_stat                        AS status,
            agm.agm_confirm_stat                AS confirmacao,
            agm.agm_valor                       AS valor,
            loc.loc_nome                        AS local
        FROM agm
        JOIN psv ON psv.psv_cod   = agm.agm_med      -- agm_med → psv_cod (PK)
        LEFT JOIN esp ON esp.esp_cod = agm.AGM_ESP_COD
        JOIN loc ON loc.loc_cod   = agm.agm_loc
        WHERE agm.agm_hini >= GETDATE()
          AND agm.agm_stat IN ('A', 'E')
        ORDER BY agm.agm_hini ASC
    """, (limite,))
    STATUS  = {"A": "Aberto", "E": "Executado", "C": "Cancelado", "B": "Bloqueado"}
    CONFIRM = {"A": "Em aberto", "C": "Confirmado", "N": "Não confirmado"}
    for r in rows:
        r["status_label"]      = STATUS.get(r["status"], r["status"])
        r["confirmacao_label"] = CONFIRM.get(r["confirmacao"], r["confirmacao"] or "—")
    return rows


@app.get("/api/agendamentos/por-semana")
def agendamentos_por_semana(periodo: str = "30d"):
    """Agrupa por semana usando agm_hini (horário real do atendimento)."""
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            DATEPART(week, agm.agm_hini)                                         AS semana,
            MIN(CAST(agm.agm_hini AS DATE))                                      AS semana_inicio,
            SUM(CASE WHEN agm.agm_stat = 'E' THEN 1 ELSE 0 END)                 AS realizados,
            SUM(CASE WHEN agm.agm_stat = 'A' THEN 1 ELSE 0 END)                 AS em_aberto,
            SUM(CASE WHEN agm.agm_stat = 'C' THEN 1 ELSE 0 END)                 AS cancelados,
            SUM(CASE WHEN agm.agm_stat = 'B' THEN 1 ELSE 0 END)                 AS bloqueados,
            ISNULL(SUM(agm.agm_valor), 0)                                        AS valor_semana
        FROM agm
        WHERE agm.agm_hini BETWEEN ? AND ?
        GROUP BY DATEPART(week, agm.agm_hini)
        ORDER BY semana
    """, (inicio, fim))
    return rows


@app.get("/api/financeiro/recebimentos")
def recebimentos(periodo: str = "30d"):
    """
    Recebimentos reais via tabela mte (Movimento de Tesouraria)
    mte_serie + mte_seq = PK
    mte_dthr    = data/hora do recebimento
    mte_valor   = valor recebido (numeric 12,2)
    mte_desconto= desconto concedido (numeric 12,2)
    mte_juros   = juros cobrados (numeric 12,2)
    mte_tipo    = tipo do movimento
    mte_status  = status
    mte_del_logica = 'S' significa cancelado — sempre filtrar
    mte_estorno = 'S' significa estorno — filtrar
    mte_pac_reg = FK paciente
    mte_osm_serie / mte_osm = FK OS
    """
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            COUNT(*)                                AS qtd_recebimentos,
            SUM(mte.mte_valor)                      AS total_recebido,
            ISNULL(SUM(mte.mte_desconto), 0)        AS total_descontos,
            ISNULL(SUM(mte.mte_juros), 0)           AS total_juros,
            COUNT(DISTINCT mte.mte_pac_reg)         AS pacientes_pagantes,

            -- Recebimento líquido (valor - desconto + juros)
            SUM(mte.mte_valor)
            - ISNULL(SUM(mte.mte_desconto), 0)
            + ISNULL(SUM(mte.mte_juros), 0)         AS liquido
        FROM mte
        WHERE mte.mte_dthr          BETWEEN ? AND ?
          AND (mte.mte_del_logica   IS NULL OR mte.mte_del_logica <> 'S')
          AND (mte.mte_estorno      IS NULL OR mte.mte_estorno    <> 'S')
    """, (inicio, fim))
    return rows[0] if rows else {}


@app.get("/api/financeiro/recebimentos-por-dia")
def recebimentos_por_dia(periodo: str = "30d"):
    """Recebimentos diários para gráfico de linha."""
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            CAST(mte.mte_dthr AS DATE)          AS data,
            COUNT(*)                            AS qtd,
            SUM(mte.mte_valor)                  AS total,
            ISNULL(SUM(mte.mte_desconto), 0)    AS descontos
        FROM mte
        WHERE mte.mte_dthr          BETWEEN ? AND ?
          AND (mte.mte_del_logica   IS NULL OR mte.mte_del_logica <> 'S')
          AND (mte.mte_estorno      IS NULL OR mte.mte_estorno    <> 'S')
        GROUP BY CAST(mte.mte_dthr AS DATE)
        ORDER BY data
    """, (inicio, fim))
    return rows


@app.get("/api/financeiro/comparativo")
def financeiro_comparativo(periodo: str = "30d"):
    """
    Faturado (fat) x Recebido (mte) no mesmo período —
    principal indicador financeiro da clínica.
    """
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            FORMAT(fat.fat_demi, 'yyyy-MM')     AS mes,
            SUM(fat.fat_val)                    AS faturado,
            SUM(fat.fat_sld)                    AS em_aberto,
            SUM(fat.fat_val - fat.fat_sld)      AS recebido_fat
        FROM fat
        WHERE fat.fat_demi >= DATEADD(month, -6, GETDATE())
          AND fat.fat_demi IS NOT NULL
        GROUP BY FORMAT(fat.fat_demi, 'yyyy-MM')
        ORDER BY mes
    """)

    # Enriquece com recebimentos reais da mte por mês
    mte_rows = query("""
        SELECT
            FORMAT(mte.mte_dthr, 'yyyy-MM')     AS mes,
            SUM(mte.mte_valor)                  AS recebido_caixa
        FROM mte
        WHERE mte.mte_dthr >= DATEADD(month, -6, GETDATE())
          AND (mte.mte_del_logica IS NULL OR mte.mte_del_logica <> 'S')
          AND (mte.mte_estorno    IS NULL OR mte.mte_estorno    <> 'S')
        GROUP BY FORMAT(mte.mte_dthr, 'yyyy-MM')
        ORDER BY mes
    """)

    mte_dict = {r["mes"]: r["recebido_caixa"] for r in mte_rows}

    # Despesas pagas por mês (IPG) — completa a visão Faturado x Recebido x Pago
    ipg_rows = query("""
        SELECT
            FORMAT(IPG_DT_PGTO, 'yyyy-MM') AS mes,
            SUM(IPG_VALOR)                 AS pago
        FROM IPG
        WHERE RTRIM(IPG_STATUS) = 'R'
          AND IPG_DT_PGTO >= DATEADD(month, -6, GETDATE())
        GROUP BY FORMAT(IPG_DT_PGTO, 'yyyy-MM')
        ORDER BY mes
    """)
    ipg_dict = {r["mes"]: r["pago"] for r in ipg_rows}

    for r in rows:
        r["recebido_caixa"] = mte_dict.get(r["mes"], 0)
        r["pago_despesas"] = ipg_dict.get(r["mes"], 0)

    return rows


# ══════════════════════════════════════════════════════════════════════════════
# FLUXO DE CAIXA — módulo Produção
#
# Entradas: mte (recebimento real) + fat (faturado/a receber via fat_sld)
# Saídas:   CPG (cabeçalho da despesa) + IPG (parcelas — IPG_STATUS: P=pendente,
#           R=pago/realizado, C=cancelado, A=aberto; IPG_DT_VCTO=vencimento,
#           IPG_DT_PGTO=data de pagamento real, IPG_VALOR=valor da parcela)
# Categoria: CCT (plano de contas) via CPG_CCT_COD_PASSIVO
# Fornecedor: PSV via CPG_PSV_COD, fallback pro texto livre CPG_CREDOR
#
# NOTA: CPG/IPG têm uso histórico concentrado em 2018-2020 (séries 117-119) —
# poucos lançamentos recentes (a clínica controla despesa fora do sistema hoje).
# Os dados antigos aparecem no relatório mesmo assim; a partir de agora, novos
# lançamentos feitos pelo Dashboard (POST /api/financeiro/despesas) passam a
# alimentar essa mesma tabela pra frente.
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/financeiro/fluxo-caixa/resumo")
def fluxo_caixa_resumo(periodo: str = "30d"):
    inicio, fim = periodo_datas(periodo)

    entradas = query("""
        SELECT ISNULL(SUM(mte.mte_valor), 0) AS total
        FROM mte
        WHERE mte.mte_dthr BETWEEN ? AND ?
          AND (mte.mte_del_logica IS NULL OR mte.mte_del_logica <> 'S')
          AND (mte.mte_estorno    IS NULL OR mte.mte_estorno    <> 'S')
    """, (inicio, fim))[0]["total"]

    saidas = query("""
        SELECT ISNULL(SUM(IPG_VALOR), 0) AS total
        FROM IPG
        WHERE RTRIM(IPG_STATUS) = 'R'
          AND IPG_DT_PGTO BETWEEN ? AND ?
    """, (inicio, fim))[0]["total"]

    # "A receber" fica restrito aos próximos 30 dias — fat_sld>0 acumula faturas
    # em aberto desde 2017 (R$75mi+ no total), a maior parte já vencida há anos
    # (glosa/baixa nunca processada) — não é "dinheiro esperado em breve", então
    # não entra no saldo projetado. Fica separado como "em_atraso" (contexto de
    # cobrança), sem somar na projeção de caixa.
    a_receber_30d = query("""
        SELECT ISNULL(SUM(fat_sld), 0) AS total
        FROM fat
        WHERE fat_sld > 0
          AND fat_venc BETWEEN GETDATE() AND DATEADD(day, 30, GETDATE())
    """)[0]["total"]

    em_atraso = query("""
        SELECT ISNULL(SUM(fat_sld), 0) AS total, COUNT(*) AS qtd
        FROM fat
        WHERE fat_sld > 0 AND fat_venc < GETDATE()
    """)[0]

    a_pagar_30d = query("""
        SELECT ISNULL(SUM(IPG_VALOR), 0) AS total
        FROM IPG
        WHERE RTRIM(IPG_STATUS) = 'P'
          AND IPG_DT_VCTO BETWEEN GETDATE() AND DATEADD(day, 30, GETDATE())
    """)[0]["total"]

    saldo = float(entradas) - float(saidas)
    saldo_projetado = saldo + float(a_receber_30d) - float(a_pagar_30d)

    return {
        "entradas": float(entradas),
        "saidas": float(saidas),
        "saldo": saldo,
        "a_receber_30d": float(a_receber_30d),
        "a_pagar_30d": float(a_pagar_30d),
        "saldo_projetado_30d": saldo_projetado,
        "em_atraso_valor": float(em_atraso["total"]),
        "em_atraso_qtd": em_atraso["qtd"],
    }


@app.get("/api/financeiro/fluxo-caixa/diario")
def fluxo_caixa_diario(periodo: str = "30d"):
    inicio, fim = periodo_datas(periodo)

    entradas = query("""
        SELECT CAST(mte.mte_dthr AS DATE) AS data, SUM(mte.mte_valor) AS total
        FROM mte
        WHERE mte.mte_dthr BETWEEN ? AND ?
          AND (mte.mte_del_logica IS NULL OR mte.mte_del_logica <> 'S')
          AND (mte.mte_estorno    IS NULL OR mte.mte_estorno    <> 'S')
        GROUP BY CAST(mte.mte_dthr AS DATE)
    """, (inicio, fim))

    saidas = query("""
        SELECT CAST(IPG_DT_PGTO AS DATE) AS data, SUM(IPG_VALOR) AS total
        FROM IPG
        WHERE RTRIM(IPG_STATUS) = 'R'
          AND IPG_DT_PGTO BETWEEN ? AND ?
        GROUP BY CAST(IPG_DT_PGTO AS DATE)
    """, (inicio, fim))

    mapa = {}
    for r in entradas:
        d = r["data"].strftime("%Y-%m-%d")
        mapa.setdefault(d, {"data": d, "entrada": 0.0, "saida": 0.0})
        mapa[d]["entrada"] = float(r["total"] or 0)
    for r in saidas:
        d = r["data"].strftime("%Y-%m-%d")
        mapa.setdefault(d, {"data": d, "entrada": 0.0, "saida": 0.0})
        mapa[d]["saida"] = float(r["total"] or 0)

    dias = sorted(mapa.values(), key=lambda x: x["data"])
    saldo_acumulado = 0.0
    for d in dias:
        saldo_acumulado += d["entrada"] - d["saida"]
        d["saldo_acumulado"] = round(saldo_acumulado, 2)
        d["entrada"] = round(d["entrada"], 2)
        d["saida"] = round(d["saida"], 2)

    return dias


@app.get("/api/financeiro/fluxo-caixa/projecao")
def fluxo_caixa_projecao(dias: int = 30):
    a_receber = query("""
        SELECT CAST(fat_venc AS DATE) AS data, SUM(fat_sld) AS total
        FROM fat
        WHERE fat_sld > 0
          AND fat_venc BETWEEN GETDATE() AND DATEADD(day, ?, GETDATE())
        GROUP BY CAST(fat_venc AS DATE)
    """, (dias,))

    a_pagar = query("""
        SELECT CAST(IPG_DT_VCTO AS DATE) AS data, SUM(IPG_VALOR) AS total
        FROM IPG
        WHERE RTRIM(IPG_STATUS) = 'P'
          AND IPG_DT_VCTO BETWEEN GETDATE() AND DATEADD(day, ?, GETDATE())
        GROUP BY CAST(IPG_DT_VCTO AS DATE)
    """, (dias,))

    mapa = {}
    for r in a_receber:
        d = r["data"].strftime("%Y-%m-%d")
        mapa.setdefault(d, {"data": d, "a_receber": 0.0, "a_pagar": 0.0})
        mapa[d]["a_receber"] = float(r["total"] or 0)
    for r in a_pagar:
        d = r["data"].strftime("%Y-%m-%d")
        mapa.setdefault(d, {"data": d, "a_receber": 0.0, "a_pagar": 0.0})
        mapa[d]["a_pagar"] = float(r["total"] or 0)

    dias_ordenados = sorted(mapa.values(), key=lambda x: x["data"])
    saldo = 0.0
    for d in dias_ordenados:
        saldo += d["a_receber"] - d["a_pagar"]
        d["saldo_projetado"] = round(saldo, 2)
        d["a_receber"] = round(d["a_receber"], 2)
        d["a_pagar"] = round(d["a_pagar"], 2)

    return dias_ordenados


@app.get("/api/financeiro/fluxo-caixa/categorias")
def fluxo_caixa_categorias(periodo: str = "30d"):
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            ISNULL(RTRIM(cct.CCT_DESCR), 'Sem categoria') AS categoria,
            SUM(ipg.IPG_VALOR)                            AS total,
            COUNT(*)                                       AS qtd
        FROM IPG ipg
        JOIN CPG cpg ON cpg.CPG_SERIE = ipg.IPG_CPG_SERIE AND cpg.CPG_NUM = ipg.IPG_CPG_NUM
        LEFT JOIN CCT cct ON cct.CCT_COD = cpg.CPG_CCT_COD_PASSIVO
        WHERE RTRIM(ipg.IPG_STATUS) = 'R'
          AND ipg.IPG_DT_PGTO BETWEEN ? AND ?
        GROUP BY RTRIM(cct.CCT_DESCR)
        ORDER BY total DESC
    """, (inicio, fim))
    return rows


@app.get("/api/financeiro/fluxo-caixa/fornecedores")
def fluxo_caixa_fornecedores(periodo: str = "30d"):
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            ISNULL(RTRIM(psv.PSV_NOME), ISNULL(RTRIM(cpg.CPG_CREDOR), 'Não informado')) AS fornecedor,
            SUM(ipg.IPG_VALOR)  AS total,
            COUNT(*)            AS qtd
        FROM IPG ipg
        JOIN CPG cpg ON cpg.CPG_SERIE = ipg.IPG_CPG_SERIE AND cpg.CPG_NUM = ipg.IPG_CPG_NUM
        LEFT JOIN PSV psv ON psv.PSV_COD = cpg.CPG_PSV_COD
        WHERE RTRIM(ipg.IPG_STATUS) = 'R'
          AND ipg.IPG_DT_PGTO BETWEEN ? AND ?
        GROUP BY ISNULL(RTRIM(psv.PSV_NOME), ISNULL(RTRIM(cpg.CPG_CREDOR), 'Não informado'))
        ORDER BY total DESC
    """, (inicio, fim))
    return rows[:15]


@app.get("/api/financeiro/centros-custo")
def centros_custo():
    rows = query("""
        SELECT CCT_COD AS cod, RTRIM(CCT_DESCR) AS descricao
        FROM CCT
        ORDER BY CCT_DESCR
    """)
    return rows


@app.get("/api/financeiro/fornecedores/busca")
def fornecedores_busca(q: str = ""):
    q = (q or "").strip()
    if len(q) < 2:
        return []
    rows = query("""
        SELECT TOP 20 PSV_COD AS cod, RTRIM(PSV_NOME) AS nome, RTRIM(ISNULL(PSV_CPF,'')) AS cpf
        FROM PSV
        WHERE RTRIM(PSV_TIPO) = 'M' AND PSV_NOME LIKE ?
        ORDER BY PSV_NOME
    """, (f"%{q}%",))
    return rows


# ── LANÇAMENTO DE NOVA DESPESA (escrita em produção — CPG/IPG) ────────────────
# Usa uma série exclusiva (200) nunca utilizada pelo aplicativo desktop da
# Pixeon (que usa 117-120 no histórico e 123-126 para reembolsos automáticos
# a pacientes — CPG_TIPO_COMPROMISSO='U'), evitando qualquer colisão ou mistura
# semântica com lançamentos gerados pelo sistema. EMP_COD=0 ("Não especificado")
# e GCC_COD='1' (ICDS - Clínica de Especialidades, marcado como GCC_DEFAULT)
# são os valores padrão confirmados via investigação da distribuição real de
# lançamentos existentes. CPG_TIPO_COMPROMISSO='N' = compromisso normal
# (despesa genérica), o mesmo valor usado nos lançamentos reais de fornecedor.
DESPESA_CPG_SERIE = 200

class DespesaRequest(BaseModel):
    fornecedor_nome: str
    psv_cod: int | None = None
    fis_jur: str          # "F" ou "J"
    cic_rg: str = ""      # CPF ou CNPJ
    cct_cod: int | None = None
    descricao: str
    valor_total: float
    parcelas: int = 1
    data_primeira_parcela: str   # "YYYY-MM-DD"

@app.post("/api/financeiro/despesas")
def criar_despesa(req: DespesaRequest):
    fis_jur = req.fis_jur.strip().upper()
    if fis_jur not in ("F", "J"):
        raise HTTPException(400, "fis_jur deve ser 'F' ou 'J'")
    if req.valor_total <= 0:
        raise HTTPException(400, "valor_total deve ser maior que zero")
    if req.parcelas < 1:
        raise HTTPException(400, "parcelas deve ser pelo menos 1")
    if not req.fornecedor_nome.strip():
        raise HTTPException(400, "fornecedor_nome é obrigatório")
    if not req.descricao.strip():
        raise HTTPException(400, "descricao é obrigatória")

    try:
        primeiro_vcto = datetime.strptime(req.data_primeira_parcela, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "data_primeira_parcela inválida (use YYYY-MM-DD)")

    agora = datetime.now()
    valor_parcela = round(req.valor_total / req.parcelas, 2)
    # ajusta a última parcela para não perder centavos no arredondamento
    valores_parcelas = [valor_parcela] * req.parcelas
    diff = round(req.valor_total - sum(valores_parcelas), 2)
    valores_parcelas[-1] = round(valores_parcelas[-1] + diff, 2)

    try:
        conn = get_conn()
        cur = conn.cursor()
        # conn.autocommit=False (padrão do pyodbc) já mantém uma transação implícita
        # aberta desde a primeira instrução até commit()/rollback() — um "BEGIN
        # TRANSACTION" explícito aqui aninharia uma segunda transação que o
        # commit() do pyodbc não fecha por completo, fazendo o INSERT ser
        # revertido silenciosamente ao fechar a conexão. Não adicionar de volta.
        cur.execute("""
            SELECT ISNULL(MAX(CPG_NUM), 0) + 1
            FROM CPG WITH (UPDLOCK, HOLDLOCK)
            WHERE CPG_SERIE = ?
        """, (DESPESA_CPG_SERIE,))
        novo_num = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO CPG (
                CPG_SERIE, CPG_NUM, CPG_TIPO_COMPROMISSO, CPG_DT_REG,
                CPG_PSV_COD, CPG_EMP_COD, CPG_FIS_JUR, CPG_CREDOR, CPG_CIC_RG,
                CPG_TOT_PARC, CPG_YYMM_COMPETENCIA, CPG_GCC_COD, CPG_OBS,
                CPG_DT_DOC_EMISS, CPG_CCT_COD_PASSIVO, CPG_EXPORT_CONTAB
            ) VALUES (?,?,?,?, ?,?,?,?,?, ?,?,?,?, ?,?,?)
        """, (
            DESPESA_CPG_SERIE, novo_num, "N", agora,
            req.psv_cod, 0, fis_jur.ljust(2), req.fornecedor_nome.strip()[:100], req.cic_rg.strip()[:16],
            req.parcelas, int(primeiro_vcto.strftime("%Y%m")), "1".ljust(3), req.descricao.strip()[:400],
            agora, req.cct_cod,
            "N",
        ))

        for i, valor in enumerate(valores_parcelas):
            vcto = primeiro_vcto + timedelta(days=30 * i)
            cur.execute("""
                INSERT INTO IPG (
                    IPG_CPG_SERIE, IPG_CPG_NUM, IPG_PARC, IPG_DT_VCTO,
                    IPG_VALOR, IPG_STATUS, IPG_VALOR_PENSAO
                ) VALUES (?,?,?,?, ?,?,?)
            """, (
                DESPESA_CPG_SERIE, novo_num, i + 1, vcto,
                valor, "P", 0,
            ))

        conn.commit()
        conn.close()
    except pyodbc.Error as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        raise HTTPException(400, f"Erro ao gravar despesa: {e}")

    return {
        "ok": True,
        "cpg_serie": DESPESA_CPG_SERIE,
        "cpg_num": novo_num,
        "parcelas_criadas": req.parcelas,
        "valores_parcelas": valores_parcelas,
    }


    """
    esp_cod = PK (char 3), esp_nome = descrição (varchar 100)
    esp_del_logica <> 'S' — filtra especialidades ativas
    AGM_ESP_COD → FK direta em agm para esp.esp_cod
    """
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            esp.esp_nome                        AS especialidade,
            COUNT(*)                            AS total,
            SUM(CASE WHEN agm.agm_stat = 'E' THEN 1 ELSE 0 END) AS realizados,
            SUM(CASE WHEN agm.agm_stat = 'C' THEN 1 ELSE 0 END) AS cancelados,
            ISNULL(SUM(agm.agm_valor), 0)      AS valor_total
        FROM agm
        JOIN esp ON esp.esp_cod        = agm.AGM_ESP_COD
               AND esp.esp_del_logica <> 'S'   -- só especialidades ativas
        WHERE agm.agm_hini BETWEEN ? AND ?
        GROUP BY esp.esp_nome
        ORDER BY total DESC
    """, (inicio, fim))
    return rows


@app.get("/api/agendamentos/cancelamentos")
def agendamentos_cancelamentos(periodo: str = "30d"):
    """Detalhes dos cancelamentos: data, motivo e volume por dia."""
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            CAST(agm.agm_canc_dthr AS DATE)     AS data_cancelamento,
            COUNT(*)                            AS qtd,
            ISNULL(SUM(agm.agm_valor), 0)      AS valor_perdido
        FROM agm
        WHERE agm.agm_stat    = 'C'
          AND agm.agm_canc_dthr BETWEEN ? AND ?
        GROUP BY CAST(agm.agm_canc_dthr AS DATE)
        ORDER BY data_cancelamento
    """, (inicio, fim))
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# PACIENTES  (tabela pac — validada contra dicionário Pixeon)
# ──────────────────────────────────────────────────────────────────────────────
# pac_reg   → PK (int)            — chave do paciente
# pac_nome  → Nome (varchar 100)
# pac_nasc  → Data de nascimento  ← campo correto (não pac_dtnasc)
# pac_dreg  → Data do registro    ← campo correto (não pac_dthr)
# pac_sexo  → M / F
# pac_dult  → Data do último atendimento
# pac_falta → Quantidade de faltas
# pac_dt_obito → Data do óbito (nullable)
# osm.osm_pac → FK para pac.pac_reg
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/pacientes/resumo")
def pacientes_resumo(periodo: str = "30d"):
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            -- Pacientes distintos com OS no período
            (SELECT COUNT(DISTINCT osm_pac)
             FROM osm
             WHERE osm_dthr BETWEEN ? AND ?)            AS pacientes_atendidos,

            -- Novos cadastros: usa pac_dreg (Data do Registro — campo real)
            (SELECT COUNT(*)
             FROM pac
             WHERE pac_dreg BETWEEN ? AND ?)            AS novos_cadastros,

            -- Total da base (excluindo óbitos)
            (SELECT COUNT(*)
             FROM pac
             WHERE pac_dt_obito IS NULL)                AS total_base,

            -- Pacientes com mais de 1 OS no período = retorno
            (SELECT COUNT(*) FROM (
                SELECT osm_pac
                FROM osm
                WHERE osm_dthr BETWEEN ? AND ?
                GROUP BY osm_pac
                HAVING COUNT(*) > 1
             ) t)                                       AS retorno,

            -- Total de faltas no período (pac_falta acumulado nos atendidos)
            (SELECT ISNULL(SUM(pac.pac_falta), 0)
             FROM pac
             JOIN osm ON osm.osm_pac = pac.pac_reg
             WHERE osm.osm_dthr BETWEEN ? AND ?)        AS total_faltas
    """, (inicio, fim, inicio, fim, inicio, fim, inicio, fim))
    return rows[0] if rows else {}


@app.get("/api/pacientes/novos-por-semana")
def novos_pacientes_semana(periodo: str = "30d"):
    """Usa pac_dreg (Data do Registro) — campo correto conforme dicionário."""
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            DATEPART(week, pac.pac_dreg) AS semana,
            COUNT(*)                     AS novos
        FROM pac
        WHERE pac.pac_dreg BETWEEN ? AND ?
        GROUP BY DATEPART(week, pac.pac_dreg)
        ORDER BY semana
    """, (inicio, fim))
    return rows


@app.get("/api/pacientes/faixa-etaria")
def pacientes_faixa_etaria(periodo: str = "30d"):
    """Usa pac_nasc (Data de Nascimento) — campo correto conforme dicionário."""
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            CASE
                WHEN DATEDIFF(year, pac.pac_nasc, GETDATE()) < 18 THEN '0-17'
                WHEN DATEDIFF(year, pac.pac_nasc, GETDATE()) < 30 THEN '18-29'
                WHEN DATEDIFF(year, pac.pac_nasc, GETDATE()) < 45 THEN '30-44'
                WHEN DATEDIFF(year, pac.pac_nasc, GETDATE()) < 60 THEN '45-59'
                ELSE '60+'
            END                         AS faixa,
            COUNT(DISTINCT osm.osm_pac) AS qtd
        FROM osm
        JOIN pac ON pac.pac_reg = osm.osm_pac
        WHERE osm.osm_dthr BETWEEN ? AND ?
          AND pac.pac_nasc IS NOT NULL
        GROUP BY
            CASE
                WHEN DATEDIFF(year, pac.pac_nasc, GETDATE()) < 18 THEN '0-17'
                WHEN DATEDIFF(year, pac.pac_nasc, GETDATE()) < 30 THEN '18-29'
                WHEN DATEDIFF(year, pac.pac_nasc, GETDATE()) < 45 THEN '30-44'
                WHEN DATEDIFF(year, pac.pac_nasc, GETDATE()) < 60 THEN '45-59'
                ELSE '60+'
            END
        ORDER BY faixa
    """, (inicio, fim))
    return rows


@app.get("/api/pacientes/por-sexo")
def pacientes_por_sexo(periodo: str = "30d"):
    """Distribuição por sexo (M/F) — usa pac_sexo conforme dicionário."""
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            CASE pac.pac_sexo
                WHEN 'M' THEN 'Masculino'
                WHEN 'F' THEN 'Feminino'
                ELSE 'Não informado'
            END             AS sexo,
            COUNT(DISTINCT osm.osm_pac) AS qtd
        FROM osm
        JOIN pac ON pac.pac_reg = osm.osm_pac
        WHERE osm.osm_dthr BETWEEN ? AND ?
        GROUP BY pac.pac_sexo
        ORDER BY qtd DESC
    """, (inicio, fim))
    return rows


@app.get("/api/pacientes/por-convenio")
def pacientes_por_convenio(periodo: str = "30d"):
    """Pacientes atendidos por convênio.
    Usa cnv_nome e filtra cnv_stat = 'A' (apenas convênios ativos).
    """
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            cnv.cnv_nome                        AS nom_convenio,
            cnv.cnv_tipo                        AS tipo,
            COUNT(DISTINCT osm.osm_pac)         AS qtd_pacientes
        FROM osm
        JOIN cnv ON cnv.cnv_cod  = osm.osm_cnv
               AND cnv.cnv_stat  = 'A'
        WHERE osm.osm_dthr BETWEEN ? AND ?
        GROUP BY cnv.cnv_nome, cnv.cnv_tipo
        ORDER BY qtd_pacientes DESC
    """, (inicio, fim))
    return rows


@app.get("/api/atendimentos/por-medico")
def atendimentos_por_medico(periodo: str = "30d"):
    """Top médicos por volume de atendimentos.
    psv_cod  = PK (int), psv_nome = nome (char 50), psv_apel = apelido (char 20)
    psv_esp_cod → esp.esp_cod (char 3)
    esp_del_logica <> 'S' — filtra especialidades ativas
    """
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT TOP 15
            psv.psv_nome                                                        AS medico,
            psv.psv_apel                                                        AS apelido,
            esp.esp_nome                                                        AS especialidade,
            COUNT(DISTINCT osm.osm_serie * 1000000 + osm.osm_num)              AS total_os,
            SUM(CASE WHEN osm.osm_atend = 'EME' THEN 1 ELSE 0 END)             AS emergencias,
            SUM(CASE WHEN osm.osm_atend = 'CRG' THEN 1 ELSE 0 END)             AS cirurgias
        FROM osm
        JOIN psv ON psv.psv_cod       = osm.osm_mreq
        LEFT JOIN esp ON esp.esp_cod  = psv.psv_esp_cod
                     AND esp.esp_del_logica <> 'S'
        WHERE osm.osm_dthr BETWEEN ? AND ?
        GROUP BY psv.psv_nome, psv.psv_apel, esp.esp_nome
        ORDER BY total_os DESC
    """, (inicio, fim))
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# COMPARATIVO ANUAL — mesmo período em anos anteriores
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/comparativo/faturamento")
def comparativo_faturamento(periodo: str = "30d", atend: str = "", anos: int = 2):
    """
    Retorna produção do mesmo período nos últimos N anos (máx 5).
    anos=2 → ano atual + ano anterior
    """
    anos = min(max(anos, 1), 5)
    filtro_atend = f"AND osm.osm_atend = '{atend}'" if atend else ""
    resultado = []
    for offset in range(0, -anos, -1):
        inicio, fim = periodo_datas_ano(periodo, offset)
        ano = datetime.now().year + offset
        rows = query(f"""
            SELECT
                SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                        AS faturamento,
                COUNT(DISTINCT smm.SMM_OSM)             AS total_os,
                SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) / NULLIF(COUNT(DISTINCT smm.SMM_OSM), 0) AS ticket_medio
            FROM smm
            JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE
                    AND osm.osm_num   = smm.SMM_OSM
            WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
              AND smm.SMM_SFAT IN ('A', 'F', 'P')
              {filtro_atend}
        """)
        r = rows[0] if rows else {}
        resultado.append({
            "ano": str(ano),
            "inicio": inicio,
            "fim": fim,
            "faturamento": r.get("faturamento"),
            "total_os": r.get("total_os"),
            "ticket_medio": r.get("ticket_medio"),
        })
    return resultado


@app.get("/api/comparativo/atendimentos")
def comparativo_atendimentos(periodo: str = "30d", atend: str = "", anos: int = 2):
    """Quantidade de atendimentos no mesmo período em anos anteriores."""
    anos = min(max(anos, 1), 5)
    filtro_atend = f"AND osm.osm_atend = '{atend}'" if atend else ""
    resultado = []
    for offset in range(0, -anos, -1):
        inicio, fim = periodo_datas_ano(periodo, offset)
        ano = datetime.now().year + offset
        rows = query(f"""
            SELECT COUNT(*) AS total
            FROM osm
            WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
            {filtro_atend}
        """)
        resultado.append({
            "ano": str(ano),
            "inicio": inicio,
            "fim": fim,
            "total": (rows[0].get("total") if rows else 0),
        })
    return resultado


@app.get("/api/comparativo/receita-mensal")
def comparativo_receita_mensal(atend: str = "", anos: int = 2):
    """
    Faturamento mês a mês dos últimos N anos (jan-dez de cada ano).
    Útil para gráfico de linhas sobrepostas por ano.
    """
    anos = min(max(anos, 1), 5)
    filtro_atend = f"AND osm.osm_atend = '{atend}'" if atend else ""
    ano_atual = datetime.now().year
    resultado = []
    for offset in range(0, -anos, -1):
        ano = ano_atual + offset
        rows = query(f"""
            SELECT
                MONTH(osm.osm_dthr)         AS mes_num,
                FORMAT(osm.osm_dthr,'MM')   AS mes,
                SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))            AS receita,
                COUNT(DISTINCT smm.SMM_OSM) AS qtd_os
            FROM smm
            JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE
                    AND osm.osm_num   = smm.SMM_OSM
            WHERE YEAR(osm.osm_dthr) = {ano}
              AND smm.SMM_SFAT IN ('A', 'F', 'P')
              {filtro_atend}
            GROUP BY MONTH(osm.osm_dthr), FORMAT(osm.osm_dthr,'MM')
            ORDER BY mes_num
        """)
        resultado.append({"ano": str(ano), "meses": rows})
    return resultado


@app.get("/api/comparativo/agendamentos")
def comparativo_agendamentos(periodo: str = "30d", anos: int = 2):
    """Taxa de execução e totais de agendamento no mesmo período em anos anteriores."""
    anos = min(max(anos, 1), 5)
    resultado = []
    for offset in range(0, -anos, -1):
        inicio, fim = periodo_datas_ano(periodo, offset)
        ano = datetime.now().year + offset
        rows = query(f"""
            SELECT
                COUNT(*)                                                              AS total,
                SUM(CASE WHEN agm.agm_stat = 'E' THEN 1 ELSE 0 END)                 AS realizados,
                SUM(CASE WHEN agm.agm_stat = 'C' THEN 1 ELSE 0 END)                 AS cancelados,
                CAST(
                    100.0 * SUM(CASE WHEN agm.agm_stat = 'E' THEN 1 ELSE 0 END)
                          / NULLIF(SUM(CASE WHEN agm.agm_stat != 'B' THEN 1 ELSE 0 END), 0)
                AS DECIMAL(5,1))                                                      AS taxa_execucao
            FROM agm
            WHERE agm.agm_hini BETWEEN '{inicio}' AND '{fim} 23:59:59'
        """)
        r = rows[0] if rows else {}
        resultado.append({"ano": str(ano), "inicio": inicio, "fim": fim, **r})
    return resultado


@app.get("/api/comparativo/pacientes")
def comparativo_pacientes(periodo: str = "30d", anos: int = 2):
    """Pacientes atendidos no mesmo período em anos anteriores."""
    anos = min(max(anos, 1), 5)
    resultado = []
    for offset in range(0, -anos, -1):
        inicio, fim = periodo_datas_ano(periodo, offset)
        ano = datetime.now().year + offset
        rows = query(f"""
            SELECT
                COUNT(DISTINCT osm.osm_pac)  AS pacientes_atendidos,
                COUNT(*)                     AS total_os
            FROM osm
            WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
        """)
        r = rows[0] if rows else {}
        resultado.append({"ano": str(ano), "inicio": inicio, "fim": fim, **r})
    return resultado


# ══════════════════════════════════════════════════════════════════════════════
# DIAGNÓSTICO
# ══════════════════════════════════════════════════════════════════════════════



# ══════════════════════════════════════════════════════════════════════════════
# PACIENTES — TOP ATENDIMENTOS E ANIVERSARIANTES
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/pacientes/aniversariantes")
def pacientes_aniversariantes(mes: int = None):
    mes_atual = mes or datetime.now().month
    rows = query(f"""
        SELECT
            RTRIM(pac.pac_nome)                         AS nome,
            DAY(pac.pac_nasc)                           AS dia,
            DATEDIFF(year, pac.pac_nasc, GETDATE())     AS idade,
            RTRIM(pac.pac_sexo)                         AS sexo,
            RTRIM(ISNULL(pac.PAC_FONE,''))              AS fone,
            RTRIM(ISNULL(pac.PAC_CELULAR,''))           AS celular,
            RTRIM(ISNULL(pac.pac_ind_whatsapp,''))      AS whatsapp,
            CONVERT(VARCHAR(10), MAX(osm.osm_dthr), 120) AS ultimo_atendimento
        FROM pac
        LEFT JOIN osm ON osm.osm_pac = pac.pac_reg
        WHERE MONTH(pac.pac_nasc) = {mes_atual}
          AND pac.pac_nasc IS NOT NULL
          AND (pac.pac_dt_obito IS NULL OR pac.pac_dt_obito = '')
        GROUP BY
            RTRIM(pac.pac_nome), DAY(pac.pac_nasc),
            pac.pac_nasc, RTRIM(pac.pac_sexo),
            RTRIM(ISNULL(pac.PAC_FONE,'')),
            RTRIM(ISNULL(pac.PAC_CELULAR,'')),
            RTRIM(ISNULL(pac.pac_ind_whatsapp,''))
        ORDER BY DAY(pac.pac_nasc), RTRIM(pac.pac_nome)
    """)
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# PREVISÃO DE FATURAMENTO POR HORA — hoje, em tempo real, por recepção
#
# Checado direto nos dados (agm executado, últimos 90 dias, vinculado à OSM
# gerada): 2.084 caem em RCN (Consultórios) contra 24 em RDI e ZERO em ROC/RCI
# — ou seja, o agendamento formal (agm) só é usado de fato pela recepção de
# Consultórios; Ocupacional e Diagnóstico são por demanda, sem agenda prévia
# confiável (confirmado pelo usuário). Por isso a projeção usa duas fontes
# diferentes conforme a recepção:
#   - Consultórios (RCN): valor já faturado hoje + o que está agendado e ainda
#     não executado (agm_stat='A', via agm_valor) — sinal direto e confiável.
#   - Ocupacional/Diagnóstico/Censo Imagem: sem agenda confiável, então a
#     previsão das horas futuras usa a MÉDIA HISTÓRICA daquela recepção,
#     naquele horário específico, no MESMO dia da semana de hoje (últimos ~120
#     dias) — ex: terça 14h costuma faturar X em Ocupacional, então é isso que
#     entra como previsão da terça 14h de hoje, enquanto ainda não chegou lá.
# Em qualquer caso, hora já ocorrida sempre usa o valor real (nunca a média),
# então a mistura passado-real / futuro-previsto acontece sozinha, sem corte manual.
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/financeiro/previsao-hora")
def previsao_faturamento_hora():
    RECEPCOES_COD = ["RDI", "ROC", "RCN", "RCI"]

    real_rows = query("""
        SELECT DATEPART(hour, osm.osm_dthr) AS hora,
            CASE WHEN RTRIM(osm.osm_str)='PSI' THEN 'RCN' ELSE RTRIM(osm.osm_str) END AS recepcao,
            SUM(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE smm.SMM_SFAT IN ('A','F','P')
          AND CAST(osm.osm_dthr AS DATE) = CAST(GETDATE() AS DATE)
          AND RTRIM(osm.osm_str) IN ('RDI','ROC','RCN','RCI','PSI')
        GROUP BY DATEPART(hour, osm.osm_dthr), CASE WHEN RTRIM(osm.osm_str)='PSI' THEN 'RCN' ELSE RTRIM(osm.osm_str) END
    """)

    pendente_rows = query("""
        SELECT DATEPART(hour, agm_hini) AS hora, ISNULL(SUM(agm_valor),0) AS valor
        FROM agm
        WHERE CAST(agm_hini AS DATE) = CAST(GETDATE() AS DATE)
          AND agm_stat = 'A'
        GROUP BY DATEPART(hour, agm_hini)
    """)

    # Média histórica por hora/recepção, mesmo dia da semana de hoje, últimos ~120 dias.
    # DATEPART(weekday,...) depende do @@DATEFIRST da sessão — comparar contra
    # DATEPART(weekday, GETDATE()) no mesmo lote evita depender de valor fixo.
    dias_mesmo_dia_semana = query("""
        SELECT COUNT(DISTINCT CAST(osm_dthr AS DATE)) AS qtd
        FROM osm
        WHERE osm_dthr >= DATEADD(day, -120, CAST(GETDATE() AS DATE))
          AND osm_dthr < CAST(GETDATE() AS DATE)
          AND DATEPART(weekday, osm_dthr) = DATEPART(weekday, GETDATE())
    """)[0]["qtd"] or 1

    media_rows = query("""
        SELECT DATEPART(hour, osm.osm_dthr) AS hora,
            CASE WHEN RTRIM(osm.osm_str)='PSI' THEN 'RCN' ELSE RTRIM(osm.osm_str) END AS recepcao,
            SUM(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) AS valor_total
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE smm.SMM_SFAT IN ('A','F','P')
          AND osm.osm_dthr >= DATEADD(day, -120, CAST(GETDATE() AS DATE))
          AND osm.osm_dthr < CAST(GETDATE() AS DATE)
          AND DATEPART(weekday, osm.osm_dthr) = DATEPART(weekday, GETDATE())
          AND RTRIM(osm.osm_str) IN ('RDI','ROC','RCN','RCI','PSI')
        GROUP BY DATEPART(hour, osm.osm_dthr), CASE WHEN RTRIM(osm.osm_str)='PSI' THEN 'RCN' ELSE RTRIM(osm.osm_str) END
    """)

    real = {h: {c: 0.0 for c in RECEPCOES_COD} for h in range(24)}
    for r in real_rows:
        if r["recepcao"] in RECEPCOES_COD:
            real[r["hora"]][r["recepcao"]] = float(r["valor"] or 0)

    pendente_total = {h: 0.0 for h in range(24)}
    for r in pendente_rows:
        pendente_total[r["hora"]] = float(r["valor"] or 0)

    media_historica = {h: {c: 0.0 for c in RECEPCOES_COD} for h in range(24)}
    for r in media_rows:
        if r["recepcao"] in RECEPCOES_COD:
            media_historica[r["hora"]][r["recepcao"]] = round(float(r["valor_total"] or 0) / dias_mesmo_dia_semana, 2)

    hora_agora = datetime.now().hour
    horas = []
    for h in range(6, 21):  # janela de funcionamento típica da clínica
        ja_ocorreu = h <= hora_agora  # hora em andamento também usa o real parcial, nunca a média
        por_recepcao = {}
        for c in RECEPCOES_COD:
            if c == "RCN":
                por_recepcao[c] = round(real[h][c] + pendente_total[h], 2)
            else:
                por_recepcao[c] = round(real[h][c] if ja_ocorreu else media_historica[h][c], 2)
        horas.append({
            "hora": h,
            "real_total": round(sum(real[h].values()), 2),
            "pendente_total": round(pendente_total[h], 2),
            "previsao_total": round(sum(por_recepcao.values()), 2),
            "por_recepcao": por_recepcao,
        })

    return {
        "atualizado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "recepcoes": [{"cod": c, "nome": RECEPCOES.get(c, c)} for c in RECEPCOES_COD],
        "aviso": "Consultórios projeta pelo agendado ainda não executado. Ocupacional, Diagnóstico e Censo Imagem não têm agenda confiável, então as horas futuras usam a média histórica daquela recepção no mesmo horário e dia da semana (últimos ~120 dias).",
        "horas": horas,
        "total_dia_previsto": round(sum(h["previsao_total"] for h in horas), 2),
        "total_dia_real": round(sum(h["real_total"] for h in horas), 2),
    }


# ══════════════════════════════════════════════════════════════════════════════
# PRODUÇÃO MENSAL — grade diária por tipo de atendimento
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/financeiro/producao-mensal")
def producao_mensal(ano: int = None, mes: int = None, meta_diaria: float = None, meta_mensal_fixa: float = 1200000.0, meta_sabado: float = None):
    """
    meta_diaria      → valor diário (padrão 45000)
    meta_mensal_fixa → se informado, usa esse valor fixo para a meta do mês
                       caso contrário calcula: meta_diaria * dias_úteis
    """
    """
    Faturamento diário do mês por tipo de atendimento (Ocupacional x Assistencial).
    Ocupacional = ADM + PER + DEM + RTB + MDF + MOC
    Assistencial = ASS
    Meta diária fixa = 45.000,00
    """
    now = datetime.now()
    if not ano: ano = now.year
    if not mes: mes = now.month

    import calendar
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    inicio = f"{ano}-{mes:02d}-01"
    fim    = f"{ano}-{mes:02d}-{ultimo_dia}"

    rows = query(f"""
        SELECT
            CAST(osm.osm_dthr AS DATE)                              AS data,
            DATEPART(weekday, osm.osm_dthr)                         AS dia_semana,
            SUM(CASE WHEN osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')
                     THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END)  AS ocupacional,
            SUM(CASE WHEN osm.osm_atend = 'ASS'
                     THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END)  AS assistencial,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                                        AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE
                AND osm.osm_num   = smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A', 'F', 'P')
        GROUP BY CAST(osm.osm_dthr AS DATE), DATEPART(weekday, osm.osm_dthr)
        ORDER BY data
    """)

    # Converte datas para string
    for r in rows:
        if hasattr(r.get("data"), "strftime"):
            r["data"] = r["data"].strftime("%Y-%m-%d")

    # Monta totais
    total_ocup  = sum(r["ocupacional"]  or 0 for r in rows)
    total_ass   = sum(r["assistencial"] or 0 for r in rows)
    total_geral = sum(r["total"]        or 0 for r in rows)
    dias_com_producao = len([r for r in rows if (r["total"] or 0) > 0])
    media_diaria = total_geral / dias_com_producao if dias_com_producao else 0

    hoje = now.date()

    # ── Feriados Parauapebas/PA ────────────────────────────────────────────
    # Dias úteis = Seg a Sáb, excluindo feriados nacionais + estaduais + municipais
    import datetime as dt

    def feriados_ano(a):
        """Retorna set de datas de feriado para o ano a em Parauapebas-PA."""
        f = set()
        # Nacionais fixos
        for m_, d_ in [(1,1),(4,21),(5,1),(9,7),(10,12),(11,2),(11,15),(11,20),(12,25)]:
            f.add(dt.date(a, m_, d_))
        # Páscoa (algoritmo de Gauss)
        y = a
        a_ = y % 19
        b_ = y // 100
        c_ = y % 100
        d__ = b_ // 4
        e_ = b_ % 4
        f_ = (b_ + 8) // 25
        g_ = (b_ - f_ + 1) // 3
        h_ = (19*a_ + b_ - d__ - g_ + 15) % 30
        i_ = c_ // 4
        k_ = c_ % 4
        l_ = (32 + 2*e_ + 2*i_ - h_ - k_) % 7
        m__ = (a_ + 11*h_ + 22*l_) // 451
        month_ = (h_ + l_ - 7*m__ + 114) // 31
        day_   = ((h_ + l_ - 7*m__ + 114) % 31) + 1
        pascoa = dt.date(y, month_, day_)
        f.add(pascoa - dt.timedelta(days=2))   # Sexta-feira Santa
        f.add(pascoa - dt.timedelta(days=47))  # Carnaval 2a (opcional — muitos não param)
        f.add(pascoa - dt.timedelta(days=46))  # Carnaval 3a (opcional)
        f.add(pascoa + dt.timedelta(days=60))  # Corpus Christi
        # Estaduais PA
        f.add(dt.date(a, 8, 15))   # Adesão do Pará à Independência
        # Municipais Parauapebas
        f.add(dt.date(a, 5, 27))   # Aniversário de Parauapebas (27/05)
        return f

    feriados = feriados_ano(ano)

    # Sábado pesa proporcionalmente menos que um dia de semana normal
    # (meta_sabado / meta_diaria) — mesmo critério usado no Home e nas
    # mensagens de WhatsApp, pra não superestimar dias úteis/projeção em
    # meses com mais sábados.
    _cfg_metas_prod = _load_metas().get("producao", {}) or {}
    _meta_diaria_base = meta_diaria if meta_diaria is not None else (_cfg_metas_prod.get("meta_diaria") or 48000.0)
    _meta_sabado_efetiva = meta_sabado if meta_sabado is not None else (_cfg_metas_prod.get("meta_sabado") or _meta_diaria_base)
    _peso_sab = (_meta_sabado_efetiva / _meta_diaria_base) if _meta_diaria_base else 1.0

    def _peso_dia(d):
        dia = dt.date(ano, mes, d)
        if dia.weekday() == 6 or dia in feriados:  # domingo ou feriado
            return 0.0
        if dia.weekday() == 5:  # sabado
            return _peso_sab
        return 1.0

    dias_uteis_mes = sum(_peso_dia(d) for d in range(1, ultimo_dia + 1))

    dias_restantes = 0
    if ano == hoje.year and mes == hoje.month:
        dias_restantes = sum(_peso_dia(d) for d in range(hoje.day + 1, ultimo_dia + 1))

    if meta_diaria is None:
        meta_diaria = round(meta_mensal_fixa / dias_uteis_mes, 2) if dias_uteis_mes > 0 else 0
    meta_mes  = meta_mensal_fixa if meta_mensal_fixa else meta_diaria * dias_uteis_mes
    projecao  = total_geral + (media_diaria * dias_restantes)
    diferenca = meta_mes - total_geral

    return {
        "ano": ano,
        "mes": mes,
        "dias": rows,
        "total_ocupacional":  total_ocup,
        "total_assistencial": total_ass,
        "total_geral":        total_geral,
        "media_diaria":       media_diaria,
        "meta_diaria":        meta_diaria,
        "meta_mensal_fixa":   meta_mensal_fixa,
        "meta_mes":           meta_mes,
        "projecao":           projecao,
        "diferenca":          diferenca,
        "dias_com_producao":  dias_com_producao,
        "dias_restantes":     round(dias_restantes, 2),
        "dias_uteis_mes":     round(dias_uteis_mes, 2),
    }
@app.get("/api/financeiro/producao-acumulada")
def producao_acumulada(ano_inicio: int = None, mes_inicio: int = None,
                        ano_fim: int = None, mes_fim: int = None,
                        meta_mensal_fixa: float = 1200000.0, meta_sabado_fixa: float = None):
    """
    Produção/receita acumulada num intervalo de meses (ex: Janeiro até agora,
    ou qualquer intervalo arbitrário de meses/anos) — complementa a visão de
    calendário de um mês só (producao_mensal) com uma visão de tendência
    ao longo de vários meses.

    Retorna: total acumulado dia a dia (pra gráfico de linha de crescimento),
    subtotal por mês (pra gráfico de barras comparando meses), e KPIs do
    intervalo inteiro.
    """
    now = datetime.now()
    if not ano_fim: ano_fim = now.year
    if not mes_fim: mes_fim = now.month
    if not ano_inicio: ano_inicio = ano_fim
    if not mes_inicio: mes_inicio = 1

    import calendar
    inicio = f"{ano_inicio}-{mes_inicio:02d}-01"
    ultimo_dia_fim = calendar.monthrange(ano_fim, mes_fim)[1]
    # se o mês final é o mês corrente, para no dia de hoje (não no fim do mês,
    # que ainda não aconteceu) — senão usa o mês inteiro.
    if ano_fim == now.year and mes_fim == now.month:
        fim = now.strftime("%Y-%m-%d")
    else:
        fim = f"{ano_fim}-{mes_fim:02d}-{ultimo_dia_fim}"

    rows = query(f"""
        SELECT
            CAST(osm.osm_dthr AS DATE) AS data,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A', 'F', 'P')
        GROUP BY CAST(osm.osm_dthr AS DATE)
        ORDER BY data
    """)
    for r in rows:
        if hasattr(r.get("data"), "strftime"):
            r["data"] = r["data"].strftime("%Y-%m-%d")

    # ── Série diária acumulada (pro gráfico de linha de crescimento) ──
    acumulado = 0.0
    dias_acumulados = []
    por_mes = {}
    for r in rows:
        valor = r["total"] or 0
        acumulado += valor
        dias_acumulados.append({"data": r["data"], "total": valor, "acumulado": round(acumulado, 2)})
        chave_mes = r["data"][:7]  # YYYY-MM
        por_mes[chave_mes] = por_mes.get(chave_mes, 0) + valor

    # ── Subtotal por mês (pro gráfico de barras) — inclui meses sem produção como 0 ──
    meses_lista = []
    y, m = ano_inicio, mes_inicio
    while (y, m) <= (ano_fim, mes_fim):
        chave = f"{y}-{m:02d}"
        meses_lista.append({"ano": y, "mes": m, "label": f"{MESES_PT_ABREV[m-1]}/{y}", "total": round(por_mes.get(chave, 0), 2)})
        m += 1
        if m > 12: m, y = 1, y + 1

    total_geral = sum(r["total"] or 0 for r in rows)
    dias_com_producao = len([r for r in rows if (r["total"] or 0) > 0])
    media_diaria = total_geral / dias_com_producao if dias_com_producao else 0
    n_meses = len(meses_lista)
    media_mensal = total_geral / n_meses if n_meses else 0

    return {
        "inicio": inicio, "fim": fim,
        "ano_inicio": ano_inicio, "mes_inicio": mes_inicio,
        "ano_fim": ano_fim, "mes_fim": mes_fim,
        "dias_acumulados": dias_acumulados,
        "por_mes": meses_lista,
        "total_geral": round(total_geral, 2),
        "media_diaria": round(media_diaria, 2),
        "media_mensal": round(media_mensal, 2),
        "meta_periodo": round(meta_mensal_fixa * n_meses, 2),
    }


def _decompor_sazonalidade(rows_mensais, ano, anos_historico=4, somente_meses_com_producao=False, metodo="sazonal", janela_tendencia=None):
    """
    Helper compartilhado: recebe linhas {ano, mes, total} e devolve o índice
    sazonal por mês (histórico, excluindo o ano corrente) + o "nível de
    tendência" do ano corrente (produção deseasonalizada) — mesmo método
    usado em previsao_anual, extraído pra reaproveitar em outras métricas
    (ex: Hapvida honorários/exames) sem duplicar a lógica.

    somente_meses_com_producao: quando True, meses fechados com produção
    zero (ex: setor que começou a operar/faturar no meio do ano) não entram
    no cálculo do nível de tendência — evita que meses "zerados antes de
    existir" puxem a previsão pra baixo artificialmente. A classificação de
    cada mês (produzido/parcial/previsto) continua igual, só o cálculo da
    tendência usada pra projetar o futuro muda.

    metodo: "sazonal" (padrão) usa o índice sazonal histórico por mês — bom
    quando há vários anos de histórico consistente. "media_simples" ignora
    o índice sazonal (fica em 1.0 pra todo mês) e projeta uma média plana
    dos meses já produzidos no ano — necessário quando o histórico é
    esparso/pouco confiável (ex: setor com só 1 ano de dado num mês
    específico), onde um único valor fora da curva vira um índice sazonal
    artificialmente alto e distorce a previsão. "linear" ajusta uma reta de
    tendência (regressão linear simples) pelos meses da janela e projeta
    essa reta pra frente — diferente da média simples (que "achata" tudo
    num valor só), a reta continua subindo/descendo, capturando o RITMO de
    crescimento (ou queda) em vez de só o nível médio.

    janela_tendencia: se informado (ex: 6), a tendência usa só os últimos N
    meses fechados em vez de todos os meses do ano até agora — evita que
    uma média "achatada" desde janeiro dilua um crescimento forte e recente
    (ex: clínica em expansão, onde a média Jan-Jul fica bem abaixo do ritmo
    real de Jun/Jul e a previsão sazonal/média subestima os meses seguintes).
    """
    now = datetime.now()
    producao_ano_atual = {r["mes"]: float(r["total"] or 0) for r in rows_mensais if r["ano"] == ano}
    historico_por_mes = {m: [] for m in range(1, 13)}
    for r in rows_mensais:
        if r["ano"] != ano:
            historico_por_mes[r["mes"]].append(float(r["total"] or 0))

    mes_atual = now.month if ano == now.year else 13
    # Todo mês antes do mês corrente é "fechado", MESMO que não tenha nenhum
    # registro (ex: um convênio/setor específico com zero produção naquele
    # mês) — usar só as chaves de producao_ano_atual deixava meses sem dado
    # de fora, fazendo-os cair errado na categoria "previsto" (futuro).
    meses_fechados = list(range(1, mes_atual))

    if metodo in ("media_simples", "linear"):
        indice_sazonal = {m: 1.0 for m in range(1, 13)}
        valores_disponiveis = [v for v in historico_por_mes.values() if v]
        media_geral_historico = sum(sum(v)/len(v) for v in valores_disponiveis) / len(valores_disponiveis) if valores_disponiveis else 0
    else:
        valores_disponiveis = [v for v in historico_por_mes.values() if v]
        media_geral_historico = sum(sum(v)/len(v) for v in valores_disponiveis) / len(valores_disponiveis) if valores_disponiveis else 0

        indice_sazonal = {}
        for m in range(1, 13):
            vals = historico_por_mes[m]
            media_mes = sum(vals) / len(vals) if vals else media_geral_historico
            indice_sazonal[m] = round(media_mes / media_geral_historico, 4) if media_geral_historico else 1.0

    meses_base_tendencia = [m for m in meses_fechados if not somente_meses_com_producao or producao_ano_atual.get(m, 0) > 0]
    if janela_tendencia:
        meses_base_tendencia = meses_base_tendencia[-janela_tendencia:]

    if metodo == "linear" and len(meses_base_tendencia) >= 2:
        n = len(meses_base_tendencia)
        xs = list(range(1, n + 1))
        ys = [producao_ano_atual.get(m, 0) for m in meses_base_tendencia]
        x_medio = sum(xs) / n
        y_medio = sum(ys) / n
        numerador = sum((x - x_medio) * (y - y_medio) for x, y in zip(xs, ys))
        denominador = sum((x - x_medio) ** 2 for x in xs)
        inclinacao = numerador / denominador if denominador else 0
        intercepto = y_medio - inclinacao * x_medio
        ultimo_mes_janela = meses_base_tendencia[-1]
        previsao_por_mes = {}
        for m in range(mes_atual, 13):
            x_previsto = n + (m - ultimo_mes_janela)
            previsao_por_mes[m] = round(max(intercepto + inclinacao * x_previsto, 0), 2)
    else:
        niveis = [producao_ano_atual.get(m, 0) / indice_sazonal[m] for m in meses_base_tendencia if indice_sazonal[m] > 0]
        nivel_tendencia = sum(niveis) / len(niveis) if niveis else media_geral_historico
        previsao_por_mes = {m: round(nivel_tendencia * indice_sazonal[m], 2) for m in range(mes_atual, 13)}

    return {
        "mes_atual": mes_atual,
        "meses_fechados": meses_fechados,
        "producao_ano_atual": producao_ano_atual,
        "indice_sazonal": indice_sazonal,
        "previsao_por_mes": previsao_por_mes,
    }


@app.get("/api/financeiro/hapvida-honorarios-exames")
def hapvida_honorarios_exames(ano: int = None, anos_historico: int = 4, setor: str = "TODOS", cnpj: str = "interno"):
    """
    Produção do convênio Hapvida (CECAN, o ativo) separada em Honorários
    (consultas) x Exames Solicitados — pro módulo de resultados financeiros
    que o diretor apresenta aos donos. Inclui a média do primeiro semestre +
    julho, e a previsão sazonal pros meses restantes (destaque out/nov/dez).

    "Exames Solicitados" = exames Hapvida (CNPJ conforme filtro `cnpj`)
    pedidos pelos médicos que TAMBÉM atendem consulta Hapvida — não conta
    exame de médico que nunca atendeu consulta pelo convênio, mesmo que o
    exame em si seja faturado como Hapvida (mesmo critério usado no painel
    de Repasse Sem Médicos c/ Consulta, pra manter os números consistentes
    entre os painéis).

    setor: ponto de recepção (osm_str) — padrão TODOS os setores; "RCN" filtra
    só Recepção Consultórios (onde as consultas/honorários de fato acontecem).
    cnpj: "interno" (padrão, CNPJ da ICDS), "externo" (qualquer outro) ou "todos".
    """
    now = datetime.now()
    if not ano: ano = now.year
    setor = None if (not setor or setor == "TODOS") else setor
    filtro_setor = "AND RTRIM(osm.osm_str) = ?" if setor else ""
    filtro_cnpj = _filtro_sql_cnpj(cnpj)
    params = (setor,) if setor else ()

    # ── Honorários (consulta) — sem restrição de médico, é a consulta em si ──
    rows_consulta = query(f"""
        SELECT YEAR(osm.osm_dthr) AS ano, MONTH(osm.osm_dthr) AS mes, 'consulta' AS tipo,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
        WHERE RTRIM(cnv.cnv_cod) = '2X' AND sk.SMK_NOME LIKE 'CONSULTA%'
          AND osm.osm_dthr >= DATEADD(year, -{anos_historico + 1}, GETDATE())
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_setor}
          {filtro_cnpj}
        GROUP BY YEAR(osm.osm_dthr), MONTH(osm.osm_dthr)
    """, params)

    # ── Médicos que atendem consulta Hapvida NO ANO analisado — pra
    # restringir os exames. Janela é o ano corrente, não histórico de vários
    # anos: um médico que só fez consulta Hapvida anos atrás e hoje só pede
    # exame não deve contar como "atende consulta Hapvida" agora. ──
    rows_medicos_consulta = query(f"""
        SELECT DISTINCT osm.osm_mreq AS medico
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
        WHERE RTRIM(cnv.cnv_cod) = '2X' AND sk.SMK_NOME LIKE 'CONSULTA%'
          AND osm.osm_dthr BETWEEN '{ano}-01-01' AND '{ano}-12-31 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
          AND osm.osm_mreq IS NOT NULL
          {filtro_setor}
          {filtro_cnpj}
    """, params)
    medicos_consulta_ids = [r["medico"] for r in rows_medicos_consulta]

    # ── Exames solicitados por esses médicos — CNPJ conforme filtro `cnpj` ──
    if medicos_consulta_ids:
        placeholders_med = ",".join("?" * len(medicos_consulta_ids))
        rows_exame = query(f"""
            SELECT YEAR(osm.osm_dthr) AS ano, MONTH(osm.osm_dthr) AS mes, 'exame' AS tipo,
                   SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS total
            FROM smm
            JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
            JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
            JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
            WHERE RTRIM(cnv.cnv_cod) = '2X' AND sk.SMK_NOME NOT LIKE 'CONSULTA%'
              AND osm.osm_dthr >= DATEADD(year, -{anos_historico + 1}, GETDATE())
              AND smm.SMM_SFAT IN ('A','F','P')
              AND osm.osm_mreq IN ({placeholders_med})
              {filtro_setor}
              {filtro_cnpj}
            GROUP BY YEAR(osm.osm_dthr), MONTH(osm.osm_dthr)
        """, tuple(medicos_consulta_ids) + params)
    else:
        rows_exame = []

    rows = rows_consulta + rows_exame

    def montar(tipo):
        rows_tipo = [r for r in rows if r["tipo"] == tipo]
        rows_agg = {}
        for r in rows_tipo:
            chave = (r["ano"], r["mes"])
            rows_agg[chave] = rows_agg.get(chave, 0) + float(r["total"] or 0)
        rows_mensais = [{"ano": a, "mes": m, "total": v} for (a, m), v in rows_agg.items()]

        # Previsão = média simples dos últimos 3 meses com produção (Mai,
        # Jun, Jul), projetada de forma plana pros meses seguintes — sem
        # tendência linear nem índice sazonal, só a média jogada pra frente.
        dec = _decompor_sazonalidade(rows_mensais, ano, anos_historico, somente_meses_com_producao=True, metodo="media_simples", janela_tendencia=3)
        mes_atual = dec["mes_atual"]
        prod_atual = dec["producao_ano_atual"]

        meses_h1_jul = [m for m in range(1, 8) if m < mes_atual]
        valores_h1_jul_com_producao = [prod_atual.get(m, 0) for m in meses_h1_jul if prod_atual.get(m, 0) > 0]
        media_h1_jul = sum(valores_h1_jul_com_producao) / len(valores_h1_jul_com_producao) if valores_h1_jul_com_producao else 0
        total_h1_jul = sum(prod_atual.get(m, 0) for m in meses_h1_jul)

        meses_detalhe = []
        for m in range(1, 13):
            if m in dec["meses_fechados"]:
                meses_detalhe.append({"mes": m, "label": MESES_PT_ABREV[m-1], "tipo_dado": "produzido", "valor": round(prod_atual.get(m, 0), 2)})
            elif m == mes_atual and ano == now.year:
                meses_detalhe.append({"mes": m, "label": MESES_PT_ABREV[m-1], "tipo_dado": "parcial", "valor": round(prod_atual.get(m, 0), 2)})
            else:
                meses_detalhe.append({"mes": m, "label": MESES_PT_ABREV[m-1], "tipo_dado": "previsto", "valor": dec["previsao_por_mes"].get(m, 0)})

        projecao_out = dec["previsao_por_mes"].get(10, 0)
        projecao_nov = dec["previsao_por_mes"].get(11, 0)
        projecao_dez = dec["previsao_por_mes"].get(12, 0)

        return {
            "meses": meses_detalhe,
            "metodo_previsao": "media_simples",
            "media_primeiro_semestre_mais_julho": round(media_h1_jul, 2),
            "total_primeiro_semestre_mais_julho": round(total_h1_jul, 2),
            "projecao_outubro": round(projecao_out, 2),
            "projecao_novembro": round(projecao_nov, 2),
            "projecao_dezembro": round(projecao_dez, 2),
            "projecao_out_nov_dez": round(projecao_out + projecao_nov + projecao_dez, 2),
            "total_ja_produzido": round(sum(prod_atual.get(m, 0) for m in range(1, mes_atual + 1)), 2),
        }

    return {
        "ano": ano,
        "convenio": "HAPVIDA CECAN",
        "setor": setor or "TODOS",
        "setor_nome": RECEPCOES.get(setor, "Todos os setores") if setor else "Todos os setores",
        "cnpj": cnpj,
        "consulta": montar("consulta"),
        "exame": montar("exame"),
    }


@app.get("/api/financeiro/hapvida-exames-por-medico")
def hapvida_exames_por_medico(ano: int = None, anos_historico: int = 4, setor: str = "TODOS", cnpj: str = "interno"):
    """
    Exames solicitados (Hapvida CECAN) abertos por médico requisitante — só
    quem atendeu no setor filtrado (padrão TODOS os setores).
    Média Jan-Jul + projeção Out/Nov/Dez por médico, com previsão simples
    (média dos próprios meses com produção, sem índice sazonal — mais
    direto de explicar por médico do que aplicar um padrão sazonal
    agregado do setor a um único profissional, que teria pouco volume
    mensal pra estimar sazonalidade individual de forma confiável).

    Só entram médicos que TAMBÉM atendem consulta Hapvida (mesmo critério do
    endpoint hapvida-honorarios-exames) — quem só solicita exame Hapvida sem
    nunca ter feito consulta pelo convênio não aparece aqui, pra manter os
    totais consistentes entre os painéis.
    cnpj: "interno" (padrão), "externo" ou "todos".
    """
    now = datetime.now()
    if not ano: ano = now.year
    setor = None if (not setor or setor == "TODOS") else setor
    filtro_setor = "AND RTRIM(osm.osm_str) = ?" if setor else ""
    filtro_cnpj = _filtro_sql_cnpj(cnpj)

    # ── Médicos que atendem consulta Hapvida NO ANO analisado — calculado
    # uma única vez e reaproveitado como lista literal nas duas consultas
    # abaixo. Janela é o ano corrente, não histórico de vários anos: médico
    # que só fez consulta Hapvida anos atrás e hoje só pede exame não deve
    # contar como "atende consulta Hapvida" agora. ──
    params_medicos = (setor,) if setor else ()
    rows_medicos_consulta = query(f"""
        SELECT DISTINCT osm.osm_mreq AS medico
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
        WHERE RTRIM(cnv.cnv_cod) = '2X' AND sk.SMK_NOME LIKE 'CONSULTA%'
          AND osm.osm_dthr BETWEEN '{ano}-01-01' AND '{ano}-12-31 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
          AND osm.osm_mreq IS NOT NULL
          {filtro_setor}
          {filtro_cnpj}
    """, params_medicos)
    medicos_consulta_ids = [r["medico"] for r in rows_medicos_consulta]

    if not medicos_consulta_ids:
        rows_med = []
    else:
        placeholders_med = ",".join("?" * len(medicos_consulta_ids))

        # ── Exames por médico requisitante ──
        params_med = tuple(medicos_consulta_ids) + ((setor,) if setor else ())
        rows_med = query(f"""
            SELECT RTRIM(psv.psv_apel) AS medico, YEAR(osm.osm_dthr) AS ano, MONTH(osm.osm_dthr) AS mes,
                   SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS total
            FROM smm
            JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
            JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
            JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
            JOIN psv ON psv.psv_cod = osm.osm_mreq
            WHERE RTRIM(cnv.cnv_cod) = '2X' AND sk.SMK_NOME NOT LIKE 'CONSULTA%'
              AND osm.osm_mreq IS NOT NULL
              AND osm.osm_mreq IN ({placeholders_med})
              AND osm.osm_dthr >= '{ano}-01-01'
              {filtro_setor}
              {filtro_cnpj}
              AND smm.SMM_SFAT IN ('A','F','P')
            GROUP BY RTRIM(psv.psv_apel), YEAR(osm.osm_dthr), MONTH(osm.osm_dthr)
            ORDER BY medico, ano, mes
        """, params_med)

    mes_atual = now.month if ano == now.year else 13

    por_medico = {}
    for r in rows_med:
        por_medico.setdefault(r["medico"], {})[r["mes"]] = float(r["total"] or 0)

    resultado = []
    for medico, meses_map in por_medico.items():
        # Todo mês antes do mês corrente conta como "fechado", mesmo que o
        # médico não tenha tido nenhum exame solicitado naquele mês (não só
        # os meses em que ele aparece no dicionário) — senão um mês parado
        # some do cálculo em vez de contar como zero.
        meses_fechados = list(range(1, mes_atual))

        # Média Jan-Jul e tendência usam só meses com produção real — um
        # médico que começou a solicitar exame Hapvida no meio do ano teria
        # os meses anteriores (zero, porque ele ainda não atendia) puxando a
        # média/previsão pra baixo artificialmente. Mês zero continua
        # contando certo como "produzido" no gráfico/tabela.
        valores_h1_jul_com_producao = [meses_map.get(m, 0) for m in range(1, 8) if m < mes_atual and meses_map.get(m, 0) > 0]
        media_h1_jul = sum(valores_h1_jul_com_producao) / len(valores_h1_jul_com_producao) if valores_h1_jul_com_producao else 0

        # Previsão = média simples dos últimos 3 meses do médico com
        # produção, projetada de forma plana pros meses seguintes — mesma
        # metodologia usada nos demais painéis do módulo.
        meses_com_producao = [m for m in meses_fechados if meses_map.get(m, 0) > 0][-3:]
        valores_com_producao = [meses_map.get(m, 0) for m in meses_com_producao]
        nivel_tendencia = sum(valores_com_producao) / len(valores_com_producao) if valores_com_producao else 0
        projecao_out = round(nivel_tendencia, 2)
        projecao_nov = round(nivel_tendencia, 2)
        projecao_dez = round(nivel_tendencia, 2)

        resultado.append({
            "medico": medico,
            "total_ja_produzido": round(sum(meses_map.get(m, 0) for m in range(1, mes_atual + 1)), 2),
            "media_primeiro_semestre_mais_julho": round(media_h1_jul, 2),
            "projecao_outubro": projecao_out,
            "projecao_novembro": projecao_nov,
            "projecao_dezembro": projecao_dez,
            "projecao_out_nov_dez": round(projecao_out + projecao_nov + projecao_dez, 2),
        })

    resultado.sort(key=lambda x: -x["total_ja_produzido"])

    return {
        "ano": ano,
        "convenio": "HAPVIDA CECAN",
        "setor": setor or "TODOS",
        "setor_nome": RECEPCOES.get(setor, "Todos os setores") if setor else "Todos os setores",
        "cnpj": cnpj,
        "metodo_previsao": "media_simples",
        "medicos": resultado,
    }


@app.get("/api/financeiro/hapvida-repasse-sem-medicos-consulta")
def hapvida_repasse_sem_medicos_consulta(ano: int = None, anos_historico: int = 4, setor: str = "TODOS", cnpj: str = "interno"):
    """
    Quanto ficaria o repasse do Hapvida (CECAN) SE excluíssemos tudo que é
    ligado aos médicos que fazem consulta Hapvida — ou seja, tira tanto a
    consulta em si quanto os exames que ESSES médicos solicitaram (não só
    a consulta). Serve pra entender quanto do repasse depende desses médicos
    x quanto vem de outras fontes (exames pedidos por médicos que não
    atendem consulta Hapvida). cnpj: "interno" (padrão), "externo" ou "todos".

    Psiquiatria fica de fora dessa conta — médico cuja única consulta
    Hapvida é psiquiátrica não entra no grupo "sai", pra manter a receita
    de psiquiatria de fora do cenário de retirada das consultas.
    """
    now = datetime.now()
    if not ano: ano = now.year
    setor = None if (not setor or setor == "TODOS") else setor
    filtro_setor = "AND RTRIM(osm.osm_str) = ?" if setor else ""
    filtro_cnpj = _filtro_sql_cnpj(cnpj)
    params_setor = (setor,) if setor else ()

    # ── Total Hapvida CECAN (consulta + exame), mensal ──
    rows_total = query(f"""
        SELECT YEAR(osm.osm_dthr) AS ano, MONTH(osm.osm_dthr) AS mes,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        WHERE RTRIM(cnv.cnv_cod) = '2X'
          AND osm.osm_dthr >= DATEADD(year, -{anos_historico + 1}, GETDATE())
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_setor}
          {filtro_cnpj}
        GROUP BY YEAR(osm.osm_dthr), MONTH(osm.osm_dthr)
    """, params_setor)

    # ── Médicos que fazem consulta Hapvida NO ANO analisado (exceto
    # psiquiatria) — materializado uma vez em Python e reaproveitado como
    # lista literal. Janela é o ano corrente, não histórico de vários anos:
    # médico que só fez consulta Hapvida anos atrás não deve contar como
    # "atende consulta Hapvida" agora. ──
    rows_medicos_consulta = query(f"""
        SELECT DISTINCT osm.osm_mreq AS medico
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
        WHERE RTRIM(cnv.cnv_cod) = '2X' AND sk.SMK_NOME LIKE 'CONSULTA%'
          AND sk.SMK_NOME NOT LIKE 'CONSULTA PSIQUIATRIA%'
          AND osm.osm_dthr BETWEEN '{ano}-01-01' AND '{ano}-12-31 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
          AND osm.osm_mreq IS NOT NULL
          {filtro_setor}
          {filtro_cnpj}
    """, params_setor)
    medicos_consulta_ids = [r["medico"] for r in rows_medicos_consulta]

    # ── Produção (consulta + exame) ligada a esses médicos ──
    if medicos_consulta_ids:
        placeholders_med = ",".join("?" * len(medicos_consulta_ids))
        rows_medicos = query(f"""
            SELECT YEAR(osm.osm_dthr) AS ano, MONTH(osm.osm_dthr) AS mes,
                   SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS total
            FROM smm
            JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
            JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
            WHERE RTRIM(cnv.cnv_cod) = '2X'
              AND osm.osm_dthr >= DATEADD(year, -{anos_historico + 1}, GETDATE())
              AND smm.SMM_SFAT IN ('A','F','P')
              AND osm.osm_mreq IN ({placeholders_med})
              {filtro_setor}
              {filtro_cnpj}
            GROUP BY YEAR(osm.osm_dthr), MONTH(osm.osm_dthr)
        """, tuple(medicos_consulta_ids) + params_setor)
    else:
        rows_medicos = []

    def resumo(rows_mensais):
        # Previsão simples baseada nos últimos 6 meses com produção, sem
        # índice sazonal — mesma metodologia usada nos demais painéis do
        # módulo (mais previsível e fácil de explicar que um ajuste sazonal).
        dec = _decompor_sazonalidade(rows_mensais, ano, anos_historico, somente_meses_com_producao=True, metodo="media_simples", janela_tendencia=3)
        mes_atual = dec["mes_atual"]
        prod = dec["producao_ano_atual"]
        valores_h1_jul = [prod.get(m, 0) for m in range(1, 8) if m < mes_atual]
        media_h1_jul = sum(valores_h1_jul) / len(valores_h1_jul) if valores_h1_jul else 0
        total_h1_jul = sum(valores_h1_jul)
        proj_out = dec["previsao_por_mes"].get(10, 0)
        proj_nov = dec["previsao_por_mes"].get(11, 0)
        proj_dez = dec["previsao_por_mes"].get(12, 0)

        # Valor por mês (real onde já fechou/parcial, previsto nos meses restantes) — pra gráfico mensal.
        valor_por_mes = {}
        for m in range(1, 13):
            if m < mes_atual or (m == mes_atual and ano == now.year):
                valor_por_mes[m] = prod.get(m, 0)
            else:
                valor_por_mes[m] = dec["previsao_por_mes"].get(m, 0)

        return {
            "total_ja_produzido": round(sum(prod.get(m, 0) for m in range(1, mes_atual + 1)), 2),
            "total_primeiro_semestre_mais_julho": round(total_h1_jul, 2),
            "media_primeiro_semestre_mais_julho": round(media_h1_jul, 2),
            "projecao_out_nov_dez": round(proj_out + proj_nov + proj_dez, 2),
            "valor_por_mes": valor_por_mes,
            "mes_atual": mes_atual,
        }

    total = resumo(rows_total)
    medicos_consulta = resumo(rows_medicos)
    repasse_sem = {
        "total_ja_produzido": round(total["total_ja_produzido"] - medicos_consulta["total_ja_produzido"], 2),
        "total_primeiro_semestre_mais_julho": round(total["total_primeiro_semestre_mais_julho"] - medicos_consulta["total_primeiro_semestre_mais_julho"], 2),
        "media_primeiro_semestre_mais_julho": round(total["media_primeiro_semestre_mais_julho"] - medicos_consulta["media_primeiro_semestre_mais_julho"], 2),
        "projecao_out_nov_dez": round(total["projecao_out_nov_dez"] - medicos_consulta["projecao_out_nov_dez"], 2),
    }

    mes_atual = total["mes_atual"]
    meses_comparativo = []
    for m in range(1, 13):
        v_total = total["valor_por_mes"].get(m, 0)
        v_medicos = medicos_consulta["valor_por_mes"].get(m, 0)
        meses_comparativo.append({
            "mes": m, "label": MESES_PT_ABREV[m-1],
            "tipo_dado": "produzido" if m < mes_atual else ("parcial" if m == mes_atual and ano == now.year else "previsto"),
            "total_hapvida": round(v_total, 2),
            "medicos_com_consulta": round(v_medicos, 2),
            "repasse_sem_medicos_consulta": round(v_total - v_medicos, 2),
        })

    total.pop("valor_por_mes", None); total.pop("mes_atual", None)
    medicos_consulta.pop("valor_por_mes", None); medicos_consulta.pop("mes_atual", None)

    return {
        "ano": ano,
        "convenio": "HAPVIDA CECAN",
        "setor": setor or "TODOS",
        "setor_nome": RECEPCOES.get(setor, "Todos os setores") if setor else "Todos os setores",
        "cnpj": cnpj,
        "total_hapvida": total,
        "medicos_com_consulta": medicos_consulta,
        "repasse_sem_medicos_consulta": repasse_sem,
        "meses": meses_comparativo,
    }


@app.get("/api/financeiro/visao-geral-hapvida")
def visao_geral_hapvida(ano: int = None, anos_historico: int = 4, setor: str = "TODOS", cnpj: str = "interno"):
    """
    Visão executiva: produção total da clínica por mês, quanto o Hapvida
    CECAN representa dessa produção, e o impacto de retirar o Hapvida das
    consultas — removendo tanto o honorário da consulta quanto os exames
    solicitados pelos médicos que fazem consulta Hapvida (mantém-se o
    atendimento em si, só sai a receita ligada a esses médicos via Hapvida).

    Psiquiatria fica de fora do cenário de retirada — médico cuja única
    consulta Hapvida é psiquiátrica não entra no grupo "sai", a receita de
    psiquiatria continua contando no que "restaria".
    cnpj: "interno" (padrão), "externo" ou "todos".
    """
    now = datetime.now()
    if not ano: ano = now.year
    setor = None if (not setor or setor == "TODOS") else setor
    filtro_setor = "AND RTRIM(osm.osm_str) = ?" if setor else ""
    filtro_cnpj = _filtro_sql_cnpj(cnpj)
    params_setor = (setor,) if setor else ()

    # ── Produção total da clínica (todos os convênios E todos os CNPJs),
    # mensal — sempre o total real, ignora o filtro de CNPJ de propósito,
    # pra bater sempre com o módulo Produção Mensal (que também não filtra
    # por CNPJ). Hapvida e o cálculo de impacto abaixo continuam respeitando
    # o filtro normalmente. ──
    rows_total_clinica = query(f"""
        SELECT YEAR(osm.osm_dthr) AS ano, MONTH(osm.osm_dthr) AS mes,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        WHERE osm.osm_dthr >= DATEADD(year, -{anos_historico + 1}, GETDATE())
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_setor}
        GROUP BY YEAR(osm.osm_dthr), MONTH(osm.osm_dthr)
    """, params_setor)

    # ── Total Hapvida CECAN (consulta + exame), mensal ──
    rows_hapvida = query(f"""
        SELECT YEAR(osm.osm_dthr) AS ano, MONTH(osm.osm_dthr) AS mes,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        WHERE RTRIM(cnv.cnv_cod) = '2X'
          AND osm.osm_dthr >= DATEADD(year, -{anos_historico + 1}, GETDATE())
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_setor}
          {filtro_cnpj}
        GROUP BY YEAR(osm.osm_dthr), MONTH(osm.osm_dthr)
    """, params_setor)

    # ── Médicos que fazem consulta Hapvida NO ANO analisado (exceto
    # psiquiatria) — materializado uma vez em Python e reaproveitado como
    # lista literal. Janela é o ano corrente, não histórico de vários anos:
    # médico que só fez consulta Hapvida anos atrás não deve contar como
    # "atende consulta Hapvida" agora. ──
    rows_medicos_ids = query(f"""
        SELECT DISTINCT osm.osm_mreq AS medico
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
        WHERE RTRIM(cnv.cnv_cod) = '2X' AND sk.SMK_NOME LIKE 'CONSULTA%'
          AND sk.SMK_NOME NOT LIKE 'CONSULTA PSIQUIATRIA%'
          AND osm.osm_dthr BETWEEN '{ano}-01-01' AND '{ano}-12-31 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
          AND osm.osm_mreq IS NOT NULL
          {filtro_setor}
          {filtro_cnpj}
    """, params_setor)
    medicos_consulta_ids = [r["medico"] for r in rows_medicos_ids]

    # ── Produção (consulta + exame) ligada a esses médicos — é isso que
    # sairia se removêssemos o Hapvida das consultas, mantendo o
    # atendimento em si (outros convênios/particular seguem). ──
    if medicos_consulta_ids:
        placeholders_med = ",".join("?" * len(medicos_consulta_ids))
        rows_medicos_consulta = query(f"""
            SELECT YEAR(osm.osm_dthr) AS ano, MONTH(osm.osm_dthr) AS mes,
                   SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS total
            FROM smm
            JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
            JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
            WHERE RTRIM(cnv.cnv_cod) = '2X'
              AND osm.osm_dthr >= DATEADD(year, -{anos_historico + 1}, GETDATE())
              AND smm.SMM_SFAT IN ('A','F','P')
              AND osm.osm_mreq IN ({placeholders_med})
              {filtro_setor}
              {filtro_cnpj}
            GROUP BY YEAR(osm.osm_dthr), MONTH(osm.osm_dthr)
        """, tuple(medicos_consulta_ids) + params_setor)
    else:
        rows_medicos_consulta = []

    def resumo(rows_mensais):
        # Previsão simples baseada nos últimos 6 meses fechados, sem índice
        # sazonal — uma clínica em forte expansão (como esta, que mais que
        # dobrou a produção de jan a jul/2026) fica com uma média "achatada"
        # bem abaixo do ritmo mais recente se usar o ano inteiro ou um ajuste
        # sazonal baseado em anos anteriores; a média móvel dos últimos 6
        # meses reflete melhor o momento atual da clínica.
        dec = _decompor_sazonalidade(rows_mensais, ano, anos_historico, somente_meses_com_producao=True, metodo="media_simples", janela_tendencia=3)
        mes_atual = dec["mes_atual"]
        prod = dec["producao_ano_atual"]
        valores_h1_jul = [prod.get(m, 0) for m in range(1, 8) if m < mes_atual]
        media_h1_jul = sum(valores_h1_jul) / len(valores_h1_jul) if valores_h1_jul else 0
        total_h1_jul = sum(valores_h1_jul)
        proj_out = dec["previsao_por_mes"].get(10, 0)
        proj_nov = dec["previsao_por_mes"].get(11, 0)
        proj_dez = dec["previsao_por_mes"].get(12, 0)

        valor_por_mes = {}
        for m in range(1, 13):
            if m < mes_atual or (m == mes_atual and ano == now.year):
                valor_por_mes[m] = prod.get(m, 0)
            else:
                valor_por_mes[m] = dec["previsao_por_mes"].get(m, 0)

        return {
            "total_ja_produzido": round(sum(prod.get(m, 0) for m in range(1, mes_atual + 1)), 2),
            "total_primeiro_semestre_mais_julho": round(total_h1_jul, 2),
            "media_primeiro_semestre_mais_julho": round(media_h1_jul, 2),
            "projecao_outubro": round(proj_out, 2),
            "projecao_novembro": round(proj_nov, 2),
            "projecao_dezembro": round(proj_dez, 2),
            "projecao_out_nov_dez": round(proj_out + proj_nov + proj_dez, 2),
            "valor_por_mes": valor_por_mes,
            "mes_atual": mes_atual,
        }

    total_clinica = resumo(rows_total_clinica)
    hapvida = resumo(rows_hapvida)
    medicos_consulta = resumo(rows_medicos_consulta)

    impacto = {
        "total_ja_produzido": round(total_clinica["total_ja_produzido"] - medicos_consulta["total_ja_produzido"], 2),
        "total_primeiro_semestre_mais_julho": round(total_clinica["total_primeiro_semestre_mais_julho"] - medicos_consulta["total_primeiro_semestre_mais_julho"], 2),
        "media_primeiro_semestre_mais_julho": round(total_clinica["media_primeiro_semestre_mais_julho"] - medicos_consulta["media_primeiro_semestre_mais_julho"], 2),
        "projecao_outubro": round(total_clinica["projecao_outubro"] - medicos_consulta["projecao_outubro"], 2),
        "projecao_novembro": round(total_clinica["projecao_novembro"] - medicos_consulta["projecao_novembro"], 2),
        "projecao_dezembro": round(total_clinica["projecao_dezembro"] - medicos_consulta["projecao_dezembro"], 2),
        "projecao_out_nov_dez": round(total_clinica["projecao_out_nov_dez"] - medicos_consulta["projecao_out_nov_dez"], 2),
    }

    mes_atual = total_clinica["mes_atual"]
    meses_comparativo = []
    for m in range(1, 13):
        v_total = total_clinica["valor_por_mes"].get(m, 0)
        v_hapvida = hapvida["valor_por_mes"].get(m, 0)
        v_medicos = medicos_consulta["valor_por_mes"].get(m, 0)
        meses_comparativo.append({
            "mes": m, "label": MESES_PT_ABREV[m-1],
            "tipo_dado": "produzido" if m < mes_atual else ("parcial" if m == mes_atual and ano == now.year else "previsto"),
            "producao_total": round(v_total, 2),
            "producao_hapvida": round(v_hapvida, 2),
            "percentual_hapvida": round((v_hapvida / v_total * 100), 1) if v_total else 0,
            "impacto_retirada_consultas": round(v_total - v_medicos, 2),
            "medicos_com_consulta_hapvida": round(v_medicos, 2),
        })

    for d in (total_clinica, hapvida, medicos_consulta):
        d.pop("valor_por_mes", None)
        d.pop("mes_atual", None)

    pct_hapvida_ano = round((hapvida["total_ja_produzido"] / total_clinica["total_ja_produzido"] * 100), 1) if total_clinica["total_ja_produzido"] else 0

    return {
        "ano": ano,
        "setor": setor or "TODOS",
        "setor_nome": RECEPCOES.get(setor, "Todos os setores") if setor else "Todos os setores",
        "cnpj": cnpj,
        "producao_total": total_clinica,
        "producao_hapvida": hapvida,
        "medicos_com_consulta_hapvida": medicos_consulta,
        "impacto_retirada_consultas_hapvida": impacto,
        "percentual_hapvida_no_ano": pct_hapvida_ano,
        "meses": meses_comparativo,
    }


@app.get("/api/financeiro/receita-por-convenio")
def receita_por_convenio_ano(ano: int = None, cnpj: str = "interno", top: int = 5, mes_ini: int = 1, mes_fim: int = 7):
    """
    Demonstrativo de receita por convênio no período (padrão: Jan a Jul) — só
    planos de saúde de verdade (cnv_tipo AM/HP/AH: Ambulatorial/Hospitalar/
    Ambul+Hosp), excluindo o que foi executado na Recepção Ocupacional (ROC).
    Os convênios de empresa (cnv_tipo MC = Medicina Ocupacional, são
    milhares de códigos, um por empresa contratante) entram consolidados
    numa única linha "Ocupacional" — união de tudo que é ROC (local de
    execução) OU cnv_tipo=MC (convênio pagador), pra pegar tanto quem foi
    atendido no balcão do Ocupacional quanto exame faturado por empresa mas
    executado em outra recepção. Essa partição (planos de saúde sem ROC +
    Ocupacional) bate exatamente com o total real da clínica, sem contar
    nada em dobro nem deixar nada de fora.

    Sempre usa o valor real (ignora o parâmetro `cnpj` de propósito, igual
    Centro de Resultado) — planos de saúde também têm uma fatia relevante
    faturada fora do CNPJ interno, então filtrar subestimava o total.

    Mostra os `top` maiores por receita (ranking pelo total do período, que é
    proporcional à média mensal) e agrupa o restante em "Outros". Cada item
    traz total do período e média mensal (total / nº de meses do período).
    """
    now = datetime.now()
    if not ano: ano = now.year
    n_meses = mes_fim - mes_ini + 1
    vliq = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"

    # Planos de saude, EXCLUINDO o que foi executado na Recepcao Ocupacional
    # (ROC) -- essa fatia entra em "Ocupacional" abaixo, pra nao contar em
    # dobro (existem exames de plano de saude executados no balcao do
    # Ocupacional).
    rows = query(f"""
        SELECT RTRIM(cnv.cnv_nome) AS convenio, SUM({vliq}) AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        WHERE YEAR(osm.osm_dthr) = {ano}
          AND MONTH(osm.osm_dthr) BETWEEN {mes_ini} AND {mes_fim}
          AND smm.SMM_SFAT IN ('A','F','P')
          AND RTRIM(cnv.cnv_tipo) IN ('AM','HP','AH')
          AND RTRIM(osm.osm_str) <> 'ROC'
        GROUP BY RTRIM(cnv.cnv_nome)
        HAVING SUM({vliq}) > 0
        ORDER BY total DESC
    """)

    # "Ocupacional" = uniao de Recepcao Ocupacional (local de execucao) com
    # convenio tipo MC (Medicina Ocupacional/empresa), onde quer que seja
    # executado -- pega tanto quem foi atendido no balcao do Ocupacional
    # quanto exame faturado por empresa mas executado em outra recepcao.
    # Combinado com a exclusao acima em "rows", essa particao bate
    # exatamente com o total real da clinica (sem contar nada em dobro nem
    # deixar nada de fora).
    row_ocupacional = query(f"""
        SELECT SUM({vliq}) AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        WHERE YEAR(osm.osm_dthr) = {ano}
          AND MONTH(osm.osm_dthr) BETWEEN {mes_ini} AND {mes_fim}
          AND smm.SMM_SFAT IN ('A','F','P')
          AND (RTRIM(osm.osm_str) = 'ROC' OR RTRIM(cnv.cnv_tipo) = 'MC')
    """)
    ocupacional_total = row_ocupacional[0]["total"] or 0 if row_ocupacional else 0

    todas_linhas = [{"convenio": r["convenio"], "total": r["total"]} for r in rows]
    if ocupacional_total > 0:
        todas_linhas.append({"convenio": "Ocupacional", "total": ocupacional_total})

    # Ajuste de reconciliação com o DRE da contabilidade (Jan-Jun/2026: a
    # planilha "RE 2026" fechou em R$ 6.339.168,01 contra R$ 6.317.905,25 do
    # Smart — diferença de R$ 21.262,76, valor fixo e já apurado). A pedido,
    # a diferença entra somada no Hapvida CECAN em vez de virar uma linha
    # separada de ajuste.
    if ano == 2026 and mes_ini == 1 and mes_fim == 6:
        ajuste = 21262.76
        hapvida_row = next((r for r in todas_linhas if "HAPVIDA" in r["convenio"].upper()), None)
        if hapvida_row is not None:
            hapvida_row["total"] += ajuste

    todas_linhas.sort(key=lambda r: -r["total"])

    total_geral = round(sum(r["total"] or 0 for r in todas_linhas), 2)
    top_n = todas_linhas[:top]
    resto = todas_linhas[top:]
    outros_total = round(sum(r["total"] or 0 for r in resto), 2)

    def pct(v):
        return round(v / total_geral * 100, 1) if total_geral else 0

    itens = [{"convenio": r["convenio"], "total": round(r["total"], 2), "media_mensal": round(r["total"] / n_meses, 2), "percentual": pct(r["total"])} for r in top_n]
    if outros_total > 0:
        itens.append({"convenio": f"Outros ({len(resto)} convênios)", "total": outros_total, "media_mensal": round(outros_total / n_meses, 2), "percentual": pct(outros_total)})

    return {
        "ano": ano, "cnpj": cnpj, "top": top,
        "mes_ini": mes_ini, "mes_fim": mes_fim, "n_meses": n_meses,
        "total_geral": total_geral,
        "media_mensal_geral": round(total_geral / n_meses, 2),
        "qtd_convenios_total": len(todas_linhas),
        "itens": itens,
    }


@app.get("/api/financeiro/receita-por-centro-resultado")
def receita_por_centro_resultado(ano: int = None, cnpj: str = "interno", top: int = 5, mes_ini: int = 1, mes_fim: int = 6):
    """
    Demonstrativo de receita por centro de resultado no período — padrão Jan
    a Jun (semestre). Só existem 4 centros de resultado de verdade: Recepção
    Diagnóstico (RDI), Recepção Ocupacional (ROC), Recepção Censo Imagem
    (RCI) e Recepção Consultórios (RCN) — este último absorve todo o resto do
    movimento (osm_str que não seja RDI/ROC/RCI), já que USG, PSI, NUT, OFT
    e outras especialidades pequenas funcionam fisicamente dentro da
    Recepção Consultórios. Mostra os `top` maiores por receita e agrupa o
    restante em "Outros" (se um dia surgir um 5º centro de verdade). Cada
    item traz total do período e média mensal — a média é sobre os meses em
    que aquele centro teve produção de verdade, não sobre o período inteiro
    (Censo Imagem, por exemplo, só começou a produzir em junho/2026; dividir
    pelos 6 meses do semestre inteiro subestimaria a média real do centro).

    Sempre usa o valor real (ignora o parâmetro `cnpj` de propósito, igual
    "Produção Total" no painel de Visão Geral) — Ocupacional em especial é
    majoritariamente faturado por fora do CNPJ interno (contratos de empresa),
    então filtrar por CNPJ interno subestimava a receita real do centro em
    ~90%.
    """
    now = datetime.now()
    if not ano: ano = now.year
    n_meses = mes_fim - mes_ini + 1
    centro_expr = "CASE WHEN RTRIM(osm.osm_str) IN ('RDI','ROC','RCI') THEN RTRIM(osm.osm_str) ELSE 'RCN' END"

    rows_mensal = query(f"""
        SELECT {centro_expr} AS cod, MONTH(osm.osm_dthr) AS mes,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        WHERE YEAR(osm.osm_dthr) = {ano}
          AND MONTH(osm.osm_dthr) BETWEEN {mes_ini} AND {mes_fim}
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY {centro_expr}, MONTH(osm.osm_dthr)
    """)

    total_por_centro = defaultdict(float)
    meses_com_producao_por_centro = defaultdict(int)
    for r in rows_mensal:
        if r["total"] and r["total"] > 0:
            total_por_centro[r["cod"]] += r["total"]
            meses_com_producao_por_centro[r["cod"]] += 1

    rows = [{"cod": cod, "total": total} for cod, total in total_por_centro.items() if total > 0]

    # Ajuste de reconciliação com o DRE da contabilidade (Jan-Jun/2026: a
    # planilha "RE 2026" fechou em R$ 6.339.168,01 contra R$ 6.317.905,25 do
    # Smart — diferença de R$ 21.262,76, valor fixo e já apurado). A pedido,
    # a diferença entra somada na Recepção Diagnóstico.
    if ano == 2026 and mes_ini == 1 and mes_fim == 6:
        ajuste = 21262.76
        rdi_row = next((r for r in rows if r["cod"] == "RDI"), None)
        if rdi_row is not None:
            rdi_row["total"] += ajuste

    rows.sort(key=lambda r: -r["total"])

    total_geral = round(sum(r["total"] for r in rows), 2)
    top_n = rows[:top]
    resto = rows[top:]
    outros_total = round(sum(r["total"] for r in resto), 2)
    outros_meses = sum(meses_com_producao_por_centro[r["cod"]] for r in resto)

    def pct(v):
        return round(v / total_geral * 100, 1) if total_geral else 0

    itens = [
        {
            "centro": RECEPCOES.get(r["cod"], r["cod"]),
            "total": round(r["total"], 2),
            "media_mensal": round(r["total"] / meses_com_producao_por_centro[r["cod"]], 2),
            "meses_com_producao": meses_com_producao_por_centro[r["cod"]],
            "percentual": pct(r["total"]),
        }
        for r in top_n
    ]
    if outros_total > 0:
        itens.append({
            "centro": f"Outros ({len(resto)} centros)",
            "total": outros_total,
            "media_mensal": round(outros_total / outros_meses, 2) if outros_meses else 0,
            "meses_com_producao": outros_meses,
            "percentual": pct(outros_total),
        })

    # Censo Imagem (RCI) começou a produzir só em junho/2026, no meio do
    # semestre — a média mensal dele fica mais representativa calculada de
    # junho até o mês atual (não só dentro da janela Jan-Jun do card), pra
    # refletir o ritmo real de operação em vez de ficar preso à métrica do
    # resto do card. Só a média muda; total e percentual continuam do
    # período do card, pra bater com o total_geral.
    item_rci = next((it for it in itens if it["centro"] == RECEPCOES.get("RCI", "RCI")), None)
    if item_rci and now.year == ano:
        rows_rci_recente = query(f"""
            SELECT MONTH(osm.osm_dthr) AS mes,
                   SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS total
            FROM smm
            JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
            WHERE RTRIM(osm.osm_str) = 'RCI'
              AND YEAR(osm.osm_dthr) = {ano}
              AND MONTH(osm.osm_dthr) BETWEEN 6 AND {now.month}
              AND smm.SMM_SFAT IN ('A','F','P')
            GROUP BY MONTH(osm.osm_dthr)
            HAVING SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) > 0
        """)
        if rows_rci_recente:
            total_rci_recente = sum(r["total"] for r in rows_rci_recente)
            item_rci["media_mensal"] = round(total_rci_recente / len(rows_rci_recente), 2)
            item_rci["meses_com_producao"] = len(rows_rci_recente)

    return {
        "ano": ano, "cnpj": cnpj, "top": top,
        "mes_ini": mes_ini, "mes_fim": mes_fim, "n_meses": n_meses,
        "total_geral": total_geral,
        "media_mensal_geral": round(total_geral / n_meses, 2),
        "qtd_centros_total": len(rows),
        "itens": itens,
    }


@app.get("/api/financeiro/receita-por-tipo-servico")
def receita_por_tipo_servico(ano: int = None, cnpj: str = "interno", mes_ini: int = 1, mes_fim: int = 6):
    """
    Demonstrativo do semestre por tipo de serviço: Exames de Sangue (esp
    Analises Clinicas), Exames de Imagem (esp Radiologia + Ultrassonografia)
    e Honorarios Medicos (servicos "CONSULTA%") — o resto vira "Outros".

    O total_geral é calculado igual ao usado em "Produção Total"/Centro de
    Resultado (só smm+osm, sem join de especialidade, e sempre valor real —
    ignora o parâmetro `cnpj` de propósito, mesma razão do Centro de
    Resultado), e "Outros" é o resto (total_geral - soma das 3 categorias) —
    assim a soma das 4 fatias sempre bate exatamente com o total já usado no
    resto do módulo, mesmo que uma pequena fatia de OS não tenha
    SMK/especialidade cadastrada corretamente (~0,2% do total, historicamente).
    """
    now = datetime.now()
    if not ano: ano = now.year
    n_meses = mes_fim - mes_ini + 1
    vliq = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"

    row_total = query(f"""
        SELECT SUM({vliq}) AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        WHERE YEAR(osm.osm_dthr) = {ano}
          AND MONTH(osm.osm_dthr) BETWEEN {mes_ini} AND {mes_fim}
          AND smm.SMM_SFAT IN ('A','F','P')
    """)
    total_geral = round(row_total[0]["total"] or 0, 2)

    categ_expr = """
        CASE
          WHEN RTRIM(esp.esp_nome) = 'Analises Clinicas' THEN 'sangue'
          WHEN RTRIM(esp.esp_nome) IN ('Radiologia','Ultrassonografia') THEN 'imagem'
          WHEN sk.SMK_NOME LIKE 'CONSULTA%' THEN 'honorarios'
          WHEN RTRIM(esp.esp_nome) = 'Medicina Ocupacional' THEN 'ocupacional'
          ELSE 'outros'
        END
    """
    rows_categ = query(f"""
        SELECT {categ_expr} AS categ, SUM({vliq}) AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
        JOIN esp ON esp.esp_cod = sk.SMK_ESP_COD
        WHERE YEAR(osm.osm_dthr) = {ano}
          AND MONTH(osm.osm_dthr) BETWEEN {mes_ini} AND {mes_fim}
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY {categ_expr}
    """)
    por_categ = {r["categ"]: round(r["total"] or 0, 2) for r in rows_categ}
    sangue = por_categ.get("sangue", 0)
    imagem = por_categ.get("imagem", 0)
    honorarios = por_categ.get("honorarios", 0)
    ocupacional = por_categ.get("ocupacional", 0)

    # Ajuste de reconciliação com o DRE da contabilidade (Jan-Jun/2026: a
    # planilha "RE 2026" fechou em R$ 6.339.168,01 contra R$ 6.317.905,25 do
    # Smart — diferença de R$ 21.262,76, valor fixo e já apurado). A pedido,
    # a diferença entra somada no Laboratório de Análises Clínicas.
    if ano == 2026 and mes_ini == 1 and mes_fim == 6:
        ajuste = 21262.76
        sangue += ajuste
        total_geral = round(total_geral + ajuste, 2)

    outros = round(total_geral - sangue - imagem - honorarios - ocupacional, 2)

    def pct(v):
        return round(v / total_geral * 100, 1) if total_geral else 0

    itens = [
        {"categoria": "Laboratorio de Analises Clinicas", "total": sangue, "media_mensal": round(sangue / n_meses, 2), "percentual": pct(sangue)},
        {"categoria": "Exames de Imagem", "total": imagem, "media_mensal": round(imagem / n_meses, 2), "percentual": pct(imagem)},
        {"categoria": "Honorarios Medicos", "total": honorarios, "media_mensal": round(honorarios / n_meses, 2), "percentual": pct(honorarios)},
        {"categoria": "Medicina Ocupacional", "total": ocupacional, "media_mensal": round(ocupacional / n_meses, 2), "percentual": pct(ocupacional)},
        {"categoria": "Outros", "total": outros, "media_mensal": round(outros / n_meses, 2), "percentual": pct(outros)},
    ]

    return {
        "ano": ano, "cnpj": cnpj, "mes_ini": mes_ini, "mes_fim": mes_fim, "n_meses": n_meses,
        "total_geral": total_geral,
        "media_mensal_geral": round(total_geral / n_meses, 2),
        "itens": itens,
    }


@app.get("/api/financeiro/receita-assistencial-ocupacional")
def receita_assistencial_ocupacional(ano: int = None, mes_ini: int = 1, mes_fim: int = 6):
    """
    Demonstrativo do semestre por linha: Assistencial (osm_atend ASS/EME/
    CRG/TAM) x Ocupacional (osm_atend ADM/PER/DEM/RTB/MDF/MOC) — mesma
    classificação já usada no painel Home (Faturamento diário Ocupacional x
    Assistencial). As duas linhas cobrem 100% dos atendimentos, então a soma
    bate exatamente com o total geral do módulo sem precisar de "Outros".
    Traz total/média mensal do período e a série mensal (pro gráfico).
    Sempre valor real, ignora CNPJ (mesma razão do Centro de Resultado).
    """
    now = datetime.now()
    if not ano: ano = now.year
    n_meses = mes_fim - mes_ini + 1
    vliq = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"
    linha_expr = """
        CASE
          WHEN osm.osm_atend IN ('ASS','EME','CRG','TAM') THEN 'Assistencial'
          WHEN osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC') THEN 'Ocupacional'
          ELSE 'Outros'
        END
    """

    rows = query(f"""
        SELECT {linha_expr} AS linha, MONTH(osm.osm_dthr) AS mes, SUM({vliq}) AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        WHERE YEAR(osm.osm_dthr) = {ano}
          AND MONTH(osm.osm_dthr) BETWEEN {mes_ini} AND {mes_fim}
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY {linha_expr}, MONTH(osm.osm_dthr)
    """)

    por_linha = defaultdict(lambda: defaultdict(float))
    for r in rows:
        por_linha[r["linha"]][r["mes"]] += r["total"] or 0

    # Ajuste de reconciliação com o DRE da contabilidade (Jan-Jun/2026: a
    # planilha "RE 2026" fechou em R$ 6.339.168,01 contra R$ 6.317.905,25 do
    # Smart — diferença de R$ 21.262,76, valor fixo e já apurado). A pedido,
    # a diferença entra somada na linha Assistencial (mês de junho, pra não
    # mexer na série histórica dos meses já fechados antes).
    if ano == 2026 and mes_ini == 1 and mes_fim == 6:
        por_linha["Assistencial"][6] += 21262.76

    total_geral = round(sum(sum(meses.values()) for meses in por_linha.values()), 2)

    def pct(v):
        return round(v / total_geral * 100, 1) if total_geral else 0

    itens = []
    for linha in ("Assistencial", "Ocupacional", "Outros"):
        meses_map = por_linha.get(linha, {})
        total_linha = round(sum(meses_map.values()), 2)
        if total_linha <= 0:
            continue
        itens.append({
            "linha": linha,
            "total": total_linha,
            "media_mensal": round(total_linha / n_meses, 2),
            "percentual": pct(total_linha),
            "meses": [{"mes": m, "label": MESES_PT_ABREV[m - 1], "valor": round(meses_map.get(m, 0), 2)} for m in range(mes_ini, mes_fim + 1)],
        })

    return {
        "ano": ano, "mes_ini": mes_ini, "mes_fim": mes_fim, "n_meses": n_meses,
        "total_geral": total_geral,
        "media_mensal_geral": round(total_geral / n_meses, 2),
        "itens": itens,
    }


_FILTRO_SERVICOS_OBSTETRICIA = "(sk.SMK_NOME LIKE 'US OBST%' OR sk.SMK_NOME LIKE '%OBSTETR%' OR sk.SMK_NOME LIKE '%GESTANTE%')"


@app.get("/api/financeiro/obstetricia-servicos")
def obstetricia_servicos(ano: int = None, percentual_honorario: float = 0.9, cnpj: str = "interno"):
    """
    Relatório de serviços de Obstetrícia (US obstétrica, curvas glicêmicas de
    gestante, etc. — identificados pelo nome do serviço, não pela especialidade
    do médico, já que o cadastro de especialidade dos profissionais não está
    preenchido no Smart) — pro módulo de resultados financeiros.

    "Número de agendas" = número de OS distintas com pelo menos um serviço de
    obstetrícia (não veio de agm/agenda porque essas OS não ficam vinculadas
    a um registro de agendamento nesse recorte — OS é a melhor proxy
    disponível de "atendimento realizado").

    percentual_honorario: fração da produção que vira honorário do médico
    (padrão 90%), agregado por convênio.
    cnpj: "interno" (padrão), "externo" ou "todos".
    """
    now = datetime.now()
    if not ano: ano = now.year
    inicio, fim = f"{ano}-01-01", f"{ano}-12-31"
    filtro_cnpj = _filtro_sql_cnpj(cnpj)

    rows_convenio = query(f"""
        SELECT RTRIM(ISNULL(cnv.cnv_nome, 'Sem convênio')) AS convenio,
               COUNT(DISTINCT CAST(osm.osm_serie AS BIGINT)*1000000+osm.osm_num) AS qtd_atendimentos,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS producao
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
        LEFT JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        WHERE {_FILTRO_SERVICOS_OBSTETRICIA}
          AND osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_cnpj}
        GROUP BY RTRIM(ISNULL(cnv.cnv_nome, 'Sem convênio'))
        ORDER BY producao DESC
    """)
    for r in rows_convenio:
        r["producao"] = round(float(r["producao"] or 0), 2)
        r["valor_honorario"] = round(r["producao"] * percentual_honorario, 2)

    rows_mensal = query(f"""
        SELECT MONTH(osm.osm_dthr) AS mes,
               COUNT(DISTINCT CAST(osm.osm_serie AS BIGINT)*1000000+osm.osm_num) AS qtd_atendimentos,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS producao
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
        WHERE {_FILTRO_SERVICOS_OBSTETRICIA}
          AND osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_cnpj}
        GROUP BY MONTH(osm.osm_dthr)
        ORDER BY mes
    """)
    mapa_mensal = {r["mes"]: r for r in rows_mensal}
    meses_detalhe = []
    for m in range(1, 13):
        r = mapa_mensal.get(m)
        producao = round(float(r["producao"] or 0), 2) if r else 0.0
        qtd = r["qtd_atendimentos"] if r else 0
        meses_detalhe.append({
            "mes": m, "label": MESES_PT_ABREV[m-1],
            "producao": producao, "qtd_atendimentos": qtd,
            "valor_honorario": round(producao * percentual_honorario, 2),
        })

    rows_servicos = query(f"""
        SELECT RTRIM(sk.SMK_NOME) AS servico,
               COUNT(*) AS qtd,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS producao
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
        WHERE {_FILTRO_SERVICOS_OBSTETRICIA}
          AND osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_cnpj}
        GROUP BY RTRIM(sk.SMK_NOME)
        ORDER BY producao DESC
    """)
    for r in rows_servicos:
        r["producao"] = round(float(r["producao"] or 0), 2)

    producao_total = round(sum(r["producao"] for r in rows_convenio), 2)
    qtd_total = sum(r["qtd_atendimentos"] for r in rows_convenio)

    return {
        "ano": ano,
        "percentual_honorario": percentual_honorario,
        "cnpj": cnpj,
        "producao_total": producao_total,
        "qtd_atendimentos_total": qtd_total,
        "valor_honorario_total": round(producao_total * percentual_honorario, 2),
        "por_convenio": rows_convenio,
        "por_mes": meses_detalhe,
        "por_servico": rows_servicos,
    }


@app.get("/api/financeiro/exames-solicitados-medicas-obstetricia")
def exames_solicitados_medicas_obstetricia(ano: int = None, anos_historico: int = 4,
                                            medicos: str = "BARBARA BARROS,GIULYA CRIST PEREIRA",
                                            cnpj: str = "interno"):
    """
    Exames solicitados pelas médicas que atendem consulta de ginecologia/
    obstetrícia (padrão: Barbara Barros e Giulya Crist Pereira) — todos os
    convênios, não só Hapvida. Já produzido + média Jan-Jul + previsão
    sazonal Out/Nov/Dez, no total e aberto por médica e por convênio.
    cnpj: "interno" (padrão), "externo" ou "todos".
    """
    now = datetime.now()
    if not ano: ano = now.year
    lista_medicos = [m.strip().upper() for m in medicos.split(",") if m.strip()]
    if not lista_medicos:
        raise HTTPException(400, "Informe ao menos um médico")
    placeholders = ",".join(f"'{m}'" for m in lista_medicos)
    filtro_cnpj = _filtro_sql_cnpj(cnpj)

    # ── Total (todas as médicas somadas), mensal — pra sazonalidade/previsão ──
    rows_total_mensal = query(f"""
        SELECT YEAR(osm.osm_dthr) AS ano, MONTH(osm.osm_dthr) AS mes,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
        JOIN psv ON psv.psv_cod = osm.osm_mreq
        WHERE RTRIM(UPPER(psv.psv_apel)) IN ({placeholders})
          AND sk.SMK_NOME NOT LIKE 'CONSULTA%'
          AND osm.osm_dthr >= DATEADD(year, -{anos_historico + 1}, GETDATE())
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_cnpj}
        GROUP BY YEAR(osm.osm_dthr), MONTH(osm.osm_dthr)
    """)
    # Previsão simples baseada nos últimos 6 meses com produção, sem
    # índice sazonal — mesma metodologia usada nos demais painéis do módulo.
    dec = _decompor_sazonalidade(rows_total_mensal, ano, anos_historico, somente_meses_com_producao=True, metodo="media_simples", janela_tendencia=3)
    mes_atual = dec["mes_atual"]
    prod_atual = dec["producao_ano_atual"]
    valores_h1_jul = [prod_atual.get(m, 0) for m in range(1, 8) if m < mes_atual]
    media_h1_jul = sum(valores_h1_jul) / len(valores_h1_jul) if valores_h1_jul else 0
    proj_out = dec["previsao_por_mes"].get(10, 0)
    proj_nov = dec["previsao_por_mes"].get(11, 0)
    proj_dez = dec["previsao_por_mes"].get(12, 0)

    meses_detalhe = []
    for m in range(1, 13):
        if m in dec["meses_fechados"]:
            meses_detalhe.append({"mes": m, "label": MESES_PT_ABREV[m-1], "tipo_dado": "produzido", "valor": round(prod_atual.get(m, 0), 2)})
        elif m == mes_atual and ano == now.year:
            meses_detalhe.append({"mes": m, "label": MESES_PT_ABREV[m-1], "tipo_dado": "parcial", "valor": round(prod_atual.get(m, 0), 2)})
        else:
            meses_detalhe.append({"mes": m, "label": MESES_PT_ABREV[m-1], "tipo_dado": "previsto", "valor": round(dec["previsao_por_mes"].get(m, 0), 2)})

    # ── Aberto por médica (ano corrente até agora) ──
    rows_por_medica = query(f"""
        SELECT RTRIM(psv.psv_apel) AS medica,
               COUNT(DISTINCT CAST(osm.osm_serie AS BIGINT)*1000000+osm.osm_num) AS qtd_atendimentos,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS producao
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
        JOIN psv ON psv.psv_cod = osm.osm_mreq
        WHERE RTRIM(UPPER(psv.psv_apel)) IN ({placeholders})
          AND sk.SMK_NOME NOT LIKE 'CONSULTA%'
          AND osm.osm_dthr BETWEEN '{ano}-01-01' AND '{ano}-12-31 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY RTRIM(psv.psv_apel)
        ORDER BY producao DESC
    """)
    for r in rows_por_medica:
        r["producao"] = round(float(r["producao"] or 0), 2)

    # ── Aberto por convênio (ano corrente até agora) ──
    rows_por_convenio = query(f"""
        SELECT RTRIM(ISNULL(cnv.cnv_nome, 'Sem convênio')) AS convenio,
               COUNT(DISTINCT CAST(osm.osm_serie AS BIGINT)*1000000+osm.osm_num) AS qtd_atendimentos,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS producao
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
        JOIN psv ON psv.psv_cod = osm.osm_mreq
        LEFT JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        WHERE RTRIM(UPPER(psv.psv_apel)) IN ({placeholders})
          AND sk.SMK_NOME NOT LIKE 'CONSULTA%'
          AND osm.osm_dthr BETWEEN '{ano}-01-01' AND '{ano}-12-31 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY RTRIM(ISNULL(cnv.cnv_nome, 'Sem convênio'))
        ORDER BY producao DESC
    """)
    for r in rows_por_convenio:
        r["producao"] = round(float(r["producao"] or 0), 2)

    total_ja_produzido = round(sum(prod_atual.get(m, 0) for m in range(1, mes_atual + 1)), 2)

    return {
        "ano": ano,
        "medicos": lista_medicos,
        "metodo_previsao": "media_simples",
        "total_ja_produzido": total_ja_produzido,
        "media_primeiro_semestre_mais_julho": round(media_h1_jul, 2),
        "total_primeiro_semestre_mais_julho": round(sum(valores_h1_jul), 2),
        "projecao_out_nov_dez": round(proj_out + proj_nov + proj_dez, 2),
        "meses": meses_detalhe,
        "por_medica": rows_por_medica,
        "por_convenio": rows_por_convenio,
    }


@app.get("/api/financeiro/producao-mensal-por-setor")
def producao_mensal_por_setor(ano: int = None, anos_historico: int = 4, setor: str = "RCI", cnpj: str = "interno"):
    """
    Produção líquida mensal de um ponto de recepção (osm_str), todos os
    convênios — média Jan-Jul e previsão sazonal Out/Nov/Dez, mesmo padrão
    dos painéis Hapvida, mas cobrindo o total do setor (não um convênio
    específico). Padrão: RCI (Recepção Censo Imagem).
    """
    now = datetime.now()
    if not ano: ano = now.year
    setor = (setor or "RCI").strip().upper()
    filtro_cnpj = _filtro_sql_cnpj(cnpj)

    rows = query(f"""
        SELECT YEAR(osm.osm_dthr) AS ano, MONTH(osm.osm_dthr) AS mes,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        WHERE RTRIM(osm.osm_str) = '{setor}'
          AND osm.osm_dthr >= DATEADD(year, -{anos_historico + 1}, GETDATE())
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_cnpj}
        GROUP BY YEAR(osm.osm_dthr), MONTH(osm.osm_dthr)
        ORDER BY ano, mes
    """)

    # Previsão = média simples dos últimos 3 meses com produção, projetada
    # de forma plana pros meses seguintes — mesma metodologia usada nos
    # demais painéis do módulo.
    metodo = "media_simples"
    dec = _decompor_sazonalidade(rows, ano, anos_historico, somente_meses_com_producao=True, metodo=metodo, janela_tendencia=3)
    mes_atual = dec["mes_atual"]
    prod_atual = dec["producao_ano_atual"]

    valores_h1_jul = [prod_atual.get(m, 0) for m in range(1, 8) if m < mes_atual]
    media_h1_jul = sum(valores_h1_jul) / len(valores_h1_jul) if valores_h1_jul else 0

    meses_detalhe = []
    for m in range(1, 13):
        if m in dec["meses_fechados"]:
            meses_detalhe.append({"mes": m, "label": MESES_PT_ABREV[m-1], "tipo_dado": "produzido", "valor": round(prod_atual.get(m, 0), 2)})
        elif m == mes_atual and ano == now.year:
            meses_detalhe.append({"mes": m, "label": MESES_PT_ABREV[m-1], "tipo_dado": "parcial", "valor": round(prod_atual.get(m, 0), 2)})
        else:
            meses_detalhe.append({"mes": m, "label": MESES_PT_ABREV[m-1], "tipo_dado": "previsto", "valor": round(dec["previsao_por_mes"].get(m, 0), 2)})

    projecao_out = dec["previsao_por_mes"].get(10, 0)
    projecao_nov = dec["previsao_por_mes"].get(11, 0)
    projecao_dez = dec["previsao_por_mes"].get(12, 0)

    return {
        "ano": ano,
        "setor": setor,
        "setor_nome": RECEPCOES.get(setor, setor),
        "cnpj": cnpj,
        "metodo_previsao": metodo,
        "meses": meses_detalhe,
        "total_ja_produzido": round(sum(prod_atual.get(m, 0) for m in range(1, mes_atual + 1)), 2),
        "media_primeiro_semestre_mais_julho": round(media_h1_jul, 2),
        "total_primeiro_semestre_mais_julho": round(sum(valores_h1_jul), 2),
        "projecao_outubro": round(projecao_out, 2),
        "projecao_novembro": round(projecao_nov, 2),
        "projecao_dezembro": round(projecao_dez, 2),
        "projecao_out_nov_dez": round(projecao_out + projecao_nov + projecao_dez, 2),
    }


@app.get("/api/financeiro/estudo-novo-ponto-coleta")
def estudo_novo_ponto_coleta(ano: int = None, setor: str = "RCN", mes_inicio_operacao: int = 6, cnpj: str = "interno"):
    """
    Estudo de viabilidade: um ponto de recepção que passou a executar exames
    LABORATORIAIS (especialidade "Analises Clinicas") em escala só a partir
    de um mês específico (padrão: RCN/Consultórios, a partir de junho/2026
    — o volume de exames laboratoriais ali saltou de poucas dezenas/mês pra
    mais de 1.300 em junho e 6.000 em julho, um salto real de operação, não
    crescimento orgânico gradual). Mostra o quanto foi arrecadado de fato x
    quanto teria sido arrecadado SE esse ponto de coleta já operasse nesse
    ritmo desde janeiro — extrapolando pra trás a média dos meses já em
    regime pleno (mês de início até o último mês fechado).
    cnpj: "interno" (padrão), "externo" ou "todos".
    """
    now = datetime.now()
    if not ano: ano = now.year
    setor = (setor or "RCN").strip().upper()
    filtro_cnpj = _filtro_sql_cnpj(cnpj)

    rows = query(f"""
        SELECT MONTH(osm.osm_dthr) AS mes,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS total,
               COUNT(*) AS qtd
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
        JOIN esp ON esp.esp_cod = sk.SMK_ESP_COD
        WHERE RTRIM(osm.osm_str) = '{setor}' AND RTRIM(esp.esp_nome) = 'Analises Clinicas'
          AND YEAR(osm.osm_dthr) = {ano}
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_cnpj}
        GROUP BY MONTH(osm.osm_dthr)
        ORDER BY mes
    """)

    # ── Consultas do mesmo setor — só como CONTEXTO ao lado do estudo, não
    # entra no cálculo de "oportunidade perdida". Consultas já vinham
    # crescendo organicamente antes de junho (sem salto de operação como os
    # exames), então misturar distorceria o cenário hipotético. ──
    rows_consulta = query(f"""
        SELECT MONTH(osm.osm_dthr) AS mes,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS total,
               COUNT(*) AS qtd
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
        WHERE RTRIM(osm.osm_str) = '{setor}' AND sk.SMK_NOME LIKE 'CONSULTA%'
          AND YEAR(osm.osm_dthr) = {ano}
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_cnpj}
        GROUP BY MONTH(osm.osm_dthr)
        ORDER BY mes
    """)

    mes_atual = now.month if ano == now.year else 13
    producao_por_mes = {r["mes"]: float(r["total"] or 0) for r in rows}
    qtd_por_mes = {r["mes"]: r["qtd"] for r in rows}
    consulta_por_mes = {r["mes"]: float(r["total"] or 0) for r in rows_consulta}
    qtd_consulta_por_mes = {r["mes"]: r["qtd"] for r in rows_consulta}

    # Meses já em "regime pleno" (do mês de início até o último mês fechado) — base pra extrapolar pra trás.
    meses_operacao_plena = [m for m in range(mes_inicio_operacao, mes_atual) if producao_por_mes.get(m, 0) > 0]
    media_operacao_plena = (
        sum(producao_por_mes.get(m, 0) for m in meses_operacao_plena) / len(meses_operacao_plena)
        if meses_operacao_plena else 0
    )

    meses_detalhe = []
    total_real = 0.0
    total_hipotetico = 0.0
    total_consulta = 0.0
    for m in range(1, mes_atual):
        real = round(producao_por_mes.get(m, 0), 2)
        em_operacao_plena = m >= mes_inicio_operacao
        hipotetico = real if em_operacao_plena else round(media_operacao_plena, 2)
        consulta = round(consulta_por_mes.get(m, 0), 2)
        total_real += real
        total_hipotetico += hipotetico
        total_consulta += consulta
        meses_detalhe.append({
            "mes": m, "label": MESES_PT_ABREV[m - 1],
            "real": real, "hipotetico": hipotetico,
            "qtd_exames": qtd_por_mes.get(m, 0),
            "em_operacao_plena": em_operacao_plena,
            "consulta": consulta,
            "qtd_consultas": qtd_consulta_por_mes.get(m, 0),
        })

    return {
        "ano": ano,
        "setor": setor,
        "setor_nome": RECEPCOES.get(setor, setor),
        "cnpj": cnpj,
        "mes_inicio_operacao": mes_inicio_operacao,
        "mes_inicio_operacao_label": MESES_PT_ABREV[mes_inicio_operacao - 1],
        "media_mensal_operacao_plena": round(media_operacao_plena, 2),
        "meses": meses_detalhe,
        "total_real": round(total_real, 2),
        "total_hipotetico": round(total_hipotetico, 2),
        "diferenca_oportunidade_perdida": round(total_hipotetico - total_real, 2),
        "total_consulta": round(total_consulta, 2),
    }


@app.get("/api/financeiro/previsao-anual")
def previsao_anual(ano: int = None, anos_historico: int = 4):
    """
    Previsão de produção pros meses restantes do ano, baseada no PADRÃO
    SAZONAL histórico (não numa média simples) — alguns meses historicamente
    produzem mais (ex: outubro/novembro) e outros menos (ex: dezembro, por
    causa das festas de fim de ano), então a projeção usa esse fator por mês
    em vez de simplesmente repetir a média do ano corrente.

    Método (decomposição sazonal clássica):
    1. Índice sazonal de cada mês = média histórica daquele mês (últimos N
       anos, excluindo o ano corrente) ÷ média histórica geral de todos os
       meses. Ex: se outubro tem índice 1.18, ele produz 18% acima da média.
    2. "Nível de tendência" do ano corrente = média dos meses já fechados
       deste ano, cada um DIVIDIDO pelo próprio índice sazonal (remove o
       efeito sazonal, isolando só o crescimento/queda real do ano).
    3. Previsão de cada mês restante = nível de tendência × índice sazonal
       daquele mês.
    """
    now = datetime.now()
    if not ano: ano = now.year

    rows = query(f"""
        SELECT YEAR(osm.osm_dthr) AS ano, MONTH(osm.osm_dthr) AS mes,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS total
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        WHERE osm.osm_dthr >= DATEADD(year, -{anos_historico + 1}, GETDATE())
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY YEAR(osm.osm_dthr), MONTH(osm.osm_dthr)
        ORDER BY ano, mes
    """)

    # ── Separa: meses do ano corrente (JÁ PRODUZIDO) vs meses de anos anteriores (histórico p/ sazonalidade) ──
    producao_ano_atual = {r["mes"]: float(r["total"] or 0) for r in rows if r["ano"] == ano}
    historico_por_mes = {m: [] for m in range(1, 13)}
    for r in rows:
        if r["ano"] != ano:
            historico_por_mes[r["mes"]].append(float(r["total"] or 0))

    # Mês corrente normalmente está incompleto (poucos dias) — não entra
    # nem como "já produzido" (mês fechado) nem distorce a tendência.
    mes_atual = now.month if ano == now.year else 13
    # Todo mês antes do corrente é "fechado", mesmo sem nenhum registro (ex:
    # zero produção genuína naquele mês) — usar só as chaves presentes em
    # producao_ano_atual deixava meses sem dado de fora, classificando-os
    # errado como "previsto" (futuro) em vez de "produzido" (passado, zero).
    meses_fechados = list(range(1, mes_atual))

    media_geral_historico = sum(sum(v)/len(v) for v in historico_por_mes.values() if v) / len([v for v in historico_por_mes.values() if v])
    indice_sazonal = {}
    for m in range(1, 13):
        vals = historico_por_mes[m]
        media_mes = sum(vals) / len(vals) if vals else media_geral_historico
        indice_sazonal[m] = round(media_mes / media_geral_historico, 4) if media_geral_historico else 1.0

    # Nível de tendência do ano corrente (deseasonalizado)
    niveis = [producao_ano_atual.get(m, 0) / indice_sazonal[m] for m in meses_fechados if indice_sazonal[m] > 0]
    nivel_tendencia = sum(niveis) / len(niveis) if niveis else media_geral_historico

    meses_restantes = [m for m in range(mes_atual, 13)]
    previsao_por_mes = {m: round(nivel_tendencia * indice_sazonal[m], 2) for m in meses_restantes}

    total_ja_produzido = sum(producao_ano_atual.get(m, 0) for m in meses_fechados)
    total_mes_corrente_parcial = producao_ano_atual.get(mes_atual, 0.0) if ano == now.year else 0.0
    total_previsto_restante = sum(previsao_por_mes.values())
    total_projetado_ano = total_ja_produzido + total_mes_corrente_parcial + total_previsto_restante

    meses_detalhe = []
    for m in range(1, 13):
        if m in meses_fechados:
            meses_detalhe.append({"mes": m, "label": MESES_PT_ABREV[m-1], "tipo": "produzido", "valor": round(producao_ano_atual.get(m, 0), 2)})
        elif m == mes_atual and ano == now.year:
            meses_detalhe.append({"mes": m, "label": MESES_PT_ABREV[m-1], "tipo": "parcial", "valor": round(total_mes_corrente_parcial, 2),
                                   "previsto_mes_completo": previsao_por_mes.get(m)})
        else:
            meses_detalhe.append({"mes": m, "label": MESES_PT_ABREV[m-1], "tipo": "previsto", "valor": previsao_por_mes.get(m, 0)})

    indices_detalhe = [{"mes": m, "label": MESES_PT_ABREV[m-1], "indice": indice_sazonal[m],
                         "efeito": "acima da média" if indice_sazonal[m] > 1.03 else "abaixo da média" if indice_sazonal[m] < 0.97 else "na média"}
                        for m in range(1, 13)]

    return {
        "ano": ano,
        "mes_atual": mes_atual,
        "meses": meses_detalhe,
        "indice_sazonal": indices_detalhe,
        "total_ja_produzido": round(total_ja_produzido + total_mes_corrente_parcial, 2),
        "total_previsto_restante": round(total_previsto_restante, 2),
        "total_projetado_ano": round(total_projetado_ano, 2),
        "anos_historico_usados": anos_historico,
    }


_RECORDES_CACHE = {"dados": None, "calculado_em": 0}
_RECORDES_CACHE_TTL_S = 3600  # 1 hora — recorde raramente muda, evita recalcular toda hora

@app.get("/api/financeiro/recordes")
def financeiro_recordes():
    """
    Recordes históricos de faturamento (todo o período com dado real —
    a partir de 2017; datas antes disso são lixo/migração, ex: 1900-01-01):
    melhor dia, melhor mês e melhor ano. Mesma fórmula de valor líquido de
    /api/financeiro/producao-mensal.

    Consulta demorada (~30s, ano a ano) — cacheada em memória por 1h, já que
    um recorde novo só pode ser batido daqui pra frente, não retroativamente.

    Consulta ano a ano (cada uma delimitada por data, ~1s) em vez de um
    GROUP BY sem limite de data no histórico inteiro — testado e o segundo
    formato trava (>90s), provavelmente por plano de execução ruim sem
    intervalo de data pra usar o índice de osm_dthr.
    """
    agora_ts = _time.time()
    if _RECORDES_CACHE["dados"] and (agora_ts - _RECORDES_CACHE["calculado_em"]) < _RECORDES_CACHE_TTL_S:
        return _RECORDES_CACHE["dados"]

    vliq = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"
    ano_inicio = 2017
    ano_fim = datetime.now().year

    melhor_dia = None
    melhor_mes = None
    totais_ano = {}

    for ano in range(ano_inicio, ano_fim + 1):
        rows = query(f"""
            SELECT CAST(osm.osm_dthr AS DATE) AS data, SUM({vliq}) AS total
            FROM smm
            JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
            WHERE smm.SMM_SFAT IN ('A', 'F', 'P')
              AND osm.osm_dthr BETWEEN '{ano}-01-01' AND '{ano}-12-31 23:59:59'
            GROUP BY CAST(osm.osm_dthr AS DATE)
        """)
        totais_mes = {}
        for r in rows:
            total = r["total"] or 0
            data = r["data"]
            if melhor_dia is None or total > melhor_dia["total"]:
                melhor_dia = {"data": data, "total": total}
            chave_mes = (ano, data.month)
            totais_mes[chave_mes] = totais_mes.get(chave_mes, 0) + total
        totais_ano[ano] = sum(totais_mes.values())
        for (a, m), total in totais_mes.items():
            if melhor_mes is None or total > melhor_mes["total"]:
                melhor_mes = {"ano": a, "mes": m, "total": total}

    melhor_ano = None
    for ano, total in totais_ano.items():
        if melhor_ano is None or total > melhor_ano["total"]:
            melhor_ano = {"ano": ano, "total": total}

    def _por_recepcao(ini: str, fim: str) -> dict:
        """Total líquido no período, aberto por recepção (RDI/ROC/RCN/RCI) —
        mesmo agrupamento usado na mensagem de fechamento do WhatsApp."""
        rows = query(f"""
            SELECT RTRIM(osm.osm_str) AS recepcao, SUM({vliq}) AS total
            FROM smm
            JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
            WHERE smm.SMM_SFAT IN ('A', 'F', 'P')
              AND osm.osm_dthr BETWEEN '{ini}' AND '{fim}'
              AND RTRIM(osm.osm_str) IN ('RDI','ROC','RCN','RCI')
            GROUP BY RTRIM(osm.osm_str)
        """)
        return {RECEPCOES.get(r["recepcao"], r["recepcao"]): r["total"] or 0 for r in rows if (r["total"] or 0) > 0}

    if melhor_dia:
        d = melhor_dia["data"]
        melhor_dia["por_recepcao"] = _por_recepcao(f"{d} 00:00:00", f"{d} 23:59:59")
        melhor_dia["data"] = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else d
    if melhor_mes:
        import calendar as _calendar
        ultimo = _calendar.monthrange(melhor_mes["ano"], melhor_mes["mes"])[1]
        melhor_mes["por_recepcao"] = _por_recepcao(
            f'{melhor_mes["ano"]}-{melhor_mes["mes"]:02d}-01 00:00:00',
            f'{melhor_mes["ano"]}-{melhor_mes["mes"]:02d}-{ultimo} 23:59:59',
        )
    if melhor_ano:
        melhor_ano["por_recepcao"] = _por_recepcao(f'{melhor_ano["ano"]}-01-01 00:00:00', f'{melhor_ano["ano"]}-12-31 23:59:59')

    resultado = {
        "melhor_dia": melhor_dia,
        "melhor_mes": melhor_mes,
        "melhor_ano": melhor_ano,
    }
    _RECORDES_CACHE["dados"] = resultado
    _RECORDES_CACHE["calculado_em"] = agora_ts
    return resultado

@app.get("/api/financeiro/producao-diaria-recepcao")
def producao_diaria_recepcao(ano: int = None, mes: int = None):
    """
    Produção líquida diária, aberta por ponto de recepção (osm_str), pro
    gráfico de Home/Produção Mensal. Mesma fórmula de valor líquido e o
    mesmo mapeamento RDI/ROC/RCN/RCI usado no módulo Recepção — PSI soma
    dentro de RCN (mesmo critério do Painel de Senhas).
    """
    now = datetime.now()
    if not ano: ano = now.year
    if not mes: mes = now.month

    import calendar
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    inicio = f"{ano}-{mes:02d}-01"
    fim    = f"{ano}-{mes:02d}-{ultimo_dia}"

    RECEPCOES_COD = ["RDI", "ROC", "RCN", "RCI"]

    rows = query(f"""
        SELECT
            CAST(osm.osm_dthr AS DATE) AS data,
            CASE WHEN RTRIM(osm.osm_str) = 'PSI' THEN 'RCN' ELSE RTRIM(osm.osm_str) END AS recepcao,
            SUM(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) AS valor
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE
                AND osm.osm_num   = smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A', 'F', 'P')
          AND RTRIM(osm.osm_str) IN ('RDI','ROC','RCN','RCI','PSI')
        GROUP BY CAST(osm.osm_dthr AS DATE),
                 CASE WHEN RTRIM(osm.osm_str) = 'PSI' THEN 'RCN' ELSE RTRIM(osm.osm_str) END
        ORDER BY data
    """)

    por_dia = {}
    for r in rows:
        d = r["data"].strftime("%Y-%m-%d") if hasattr(r["data"], "strftime") else str(r["data"])
        if d not in por_dia:
            por_dia[d] = {"data": d, **{c: 0 for c in RECEPCOES_COD}, "total": 0}
        cod = r["recepcao"]
        if cod in RECEPCOES_COD:
            valor = float(r["valor"] or 0)
            por_dia[d][cod] += valor
            por_dia[d]["total"] += valor

    dias = sorted(por_dia.values(), key=lambda x: x["data"])
    totais = {c: sum(d[c] for d in dias) for c in RECEPCOES_COD}
    totais["total"] = sum(d["total"] for d in dias)

    return {
        "ano": ano, "mes": mes,
        "recepcoes": [{"cod": c, "nome": RECEPCOES.get(c, c)} for c in RECEPCOES_COD],
        "dias": dias,
        "totais": totais,
    }

@app.get("/api/financeiro/producao-mensal/profissionais")
def producao_mensal_profissionais(ano: int = None, mes: int = None):
    now = datetime.now()
    if not ano: ano = now.year
    if not mes: mes = now.month
    import calendar
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    inicio = f"{ano}-{mes:02d}-01"
    fim    = f"{ano}-{mes:02d}-{ultimo_dia}"
    vliq = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"
    def fix_str(s):
        if not s: return s
        try:
            return s.encode("latin-1").decode("utf-8").strip()
        except:
            return s.strip()
    def classificar(nome):
        if not nome: return "Outros"
        n = nome.upper()
        if "CONSULTA" in n: return "Consulta"
        if "EXAME" in n or "PESQUISA" in n or "DOSAGEM" in n or "ANALISE" in n or "ANALISE" in n: return "Exame"
        if "RAIO" in n or "ULTRASSOM" in n or "ULTRASSONOGRAFIA" in n or "RADIOGRAFIA" in n or "TOMOGRAFIA" in n: return "Imagem"
        if "PROCEDIMENTO" in n or "CURATIVO" in n or "SUTURA" in n: return "Procedimento"
        return "Outros"
    executado = query(f"""
        SELECT
            ISNULL(RTRIM(psv.psv_apel), RTRIM(psv.psv_nome)) AS profissional,
            RTRIM(esp.esp_nome)                                AS esp_nome,
            RTRIM(sk.SMK_NOME)                                 AS servico_nome,
            ISNULL(SUM({vliq}), 0)                             AS producao_executada,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)  AS os_executadas,
            COUNT(DISTINCT osm.osm_pac)                         AS pacientes
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        JOIN smk sk ON sk.SMK_COD = smm.SMM_COD
        JOIN psv ON psv.psv_cod = COALESCE(smm.SMM_MED, osm.osm_mreq) AND psv.PSV_TIPO = \'M\'
        LEFT JOIN esp ON esp.esp_cod = sk.SMK_ESP_COD
        WHERE osm.osm_dthr BETWEEN \'{inicio}\' AND \'{fim} 23:59:59\'
          AND smm.SMM_SFAT IN (\'A\',\'F\',\'P\')
        GROUP BY ISNULL(RTRIM(psv.psv_apel), RTRIM(psv.psv_nome)), RTRIM(esp.esp_nome), RTRIM(sk.SMK_NOME)
    """)
    solicitado = query(f"""
        SELECT
            ISNULL(RTRIM(psv.psv_apel), RTRIM(psv.psv_nome)) AS profissional,
            RTRIM(sk.SMK_NOME)                                 AS servico_nome,
            ISNULL(SUM({vliq}), 0)                             AS producao_solicitada,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)  AS os_solicitadas
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        JOIN smk sk ON sk.SMK_COD = smm.SMM_COD
        JOIN psv ON psv.psv_cod = osm.osm_mreq AND psv.PSV_TIPO = \'M\'
        WHERE osm.osm_dthr BETWEEN \'{inicio}\' AND \'{fim} 23:59:59\'
          AND smm.SMM_SFAT IN (\'A\',\'F\',\'P\')
          AND smm.SMM_MED IS NOT NULL
          AND smm.SMM_MED <> osm.osm_mreq
        GROUP BY ISNULL(RTRIM(psv.psv_apel), RTRIM(psv.psv_nome)), RTRIM(sk.SMK_NOME)
    """)
    from collections import defaultdict
    merged = defaultdict(lambda: {
        "especialidades": set(),
        "classes_exec": set(), "classes_solic": set(),
        "producao_total": 0, "total_os": 0, "pacientes": 0,
        "producao_solicitada": 0, "os_solicitadas": 0,
    })
    for e in executado:
        k = e["profissional"]
        merged[k]["producao_total"] += float(e["producao_executada"] or 0)
        merged[k]["total_os"]       += int(e["os_executadas"] or 0)
        merged[k]["pacientes"]      += int(e["pacientes"] or 0)
        if e.get("esp_nome"): merged[k]["especialidades"].add(fix_str(e["esp_nome"]))
        merged[k]["classes_exec"].add(classificar(e.get("servico_nome")))
    for s in solicitado:
        k = s["profissional"]
        merged[k]["producao_solicitada"] += float(s["producao_solicitada"] or 0)
        merged[k]["os_solicitadas"]      += int(s["os_solicitadas"] or 0)
        merged[k]["classes_solic"].add(classificar(s.get("servico_nome")))
    result = []
    for prof, v in merged.items():
        result.append({
            "profissional":        prof,
            "especialidades":      sorted([e for e in v["especialidades"] if e]),
            "classes_executadas":  sorted(list(v["classes_exec"])),
            "classes_solicitadas": sorted(list(v["classes_solic"])),
            "producao_total":      round(v["producao_total"], 2),
            "total_os":            v["total_os"],
            "pacientes":           v["pacientes"],
            "producao_solicitada": round(v["producao_solicitada"], 2),
            "os_solicitadas":      v["os_solicitadas"],
        })
    return sorted(result, key=lambda x: -x["producao_total"])

@app.get("/api/financeiro/producao-mensal/profissional-servicos")
def producao_profissional_servicos(profissional: str, ano: int = None, mes: int = None):
    now = datetime.now()
    if not ano: ano = now.year
    if not mes: mes = now.month

    import calendar
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    inicio = f"{ano}-{mes:02d}-01"
    fim    = f"{ano}-{mes:02d}-{ultimo_dia}"

    vliq = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"

    # Serviços executados
    executados = query(f"""
        SELECT
            RTRIM(sk.SMK_NOME)                                 AS servico,
            RTRIM(esp.esp_nome)                                AS especialidade,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)  AS qtd_os,
            COUNT(smm.SMM_NUM)                                 AS qtd_itens,
            ISNULL(SUM({vliq}), 0)                             AS valor
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        JOIN smk sk ON sk.SMK_COD = smm.SMM_COD
        JOIN psv ON psv.psv_cod = COALESCE(smm.SMM_MED, osm.osm_mreq)
        LEFT JOIN esp ON esp.esp_cod = sk.SMK_ESP_COD
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
          AND ISNULL(RTRIM(psv.psv_apel), RTRIM(psv.psv_nome)) = '{profissional}'
        GROUP BY RTRIM(sk.SMK_NOME), RTRIM(esp.esp_nome)
        ORDER BY valor DESC
    """)

    # Serviços solicitados
    solicitados = query(f"""
        SELECT
            RTRIM(sk.SMK_NOME)                                 AS servico,
            RTRIM(esp.esp_nome)                                AS especialidade,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)  AS qtd_os,
            COUNT(smm.SMM_NUM)                                 AS qtd_itens,
            ISNULL(SUM({vliq}), 0)                             AS valor
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        JOIN smk sk ON sk.SMK_COD = smm.SMM_COD
        JOIN psv ON psv.psv_cod = osm.osm_mreq
        LEFT JOIN esp ON esp.esp_cod = sk.SMK_ESP_COD
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
          AND smm.SMM_MED IS NOT NULL
          AND smm.SMM_MED <> osm.osm_mreq
          AND ISNULL(RTRIM(psv.psv_apel), RTRIM(psv.psv_nome)) = '{profissional}'
        GROUP BY RTRIM(sk.SMK_NOME), RTRIM(esp.esp_nome)
        ORDER BY valor DESC
    """)

    return { "executados": executados, "solicitados": solicitados }

# ══════════════════════════════════════════════════════════════════════════════
# AGENDA DO MÉDICO
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/agenda/medicos")
def lista_medicos():
    """Lista todos os médicos com agendamentos futuros."""
    rows = query("""
        SELECT DISTINCT
            psv.psv_cod     AS cod,
            psv.psv_nome    AS nome,
            psv.psv_apel    AS apelido,
            esp.esp_nome    AS especialidade
        FROM agm
        JOIN psv ON psv.psv_cod  = agm.agm_med
        LEFT JOIN esp ON esp.esp_cod = psv.psv_esp_cod
        WHERE agm.agm_hini >= CAST(GETDATE() AS DATE)
          AND agm.agm_stat IN ('A','E')
        ORDER BY psv.psv_apel, psv.psv_nome
    """)
    return rows


def buscar_disponibilidade_especialidade(especialidade: str, dias: int = 30, limite_datas: int = 5):
    """
    Horários disponíveis (view EX_HORARIOS, SITUACAO='DISPONIVEL') para
    médicos de uma especialidade, buscada por nome (LIKE).

    IMPORTANTE: psv.psv_esp_cod está sempre NULL neste banco (não é
    preenchido pelo Smart) — a especialidade real do médico só existe na
    view V_ESP_MEDICO(medico, especialidade), então é ela que usamos aqui
    (não o join psv->esp usado em outros endpoints de agenda, que na
    prática nunca resolve especialidade nenhuma).
    """
    termo = (especialidade or "").strip().upper()
    if not termo:
        return {"especialidade_buscada": especialidade, "encontrada": False, "medicos": []}

    fim = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")
    rows = query("""
        SELECT
            eh.HOR_MED                             AS medico_cod,
            RTRIM(psv.psv_nome)                    AS medico_nome,
            RTRIM(v.especialidade)                 AS especialidade,
            CONVERT(VARCHAR(10), eh.HOR_DATA, 120)  AS data,
            eh.HORARIO_INICIO                       AS horario
        FROM EX_HORARIOS eh
        JOIN psv ON psv.psv_cod = eh.HOR_MED
        JOIN V_ESP_MEDICO v ON v.medico = eh.HOR_MED
        WHERE eh.HOR_DATA >= CAST(GETDATE() AS DATE)
          AND eh.HOR_DATA < CAST(? AS DATE)
          AND UPPER(v.especialidade) LIKE ?
        ORDER BY eh.HOR_DATA, eh.HORARIO_INICIO
    """, (fim, f"%{termo}%"))

    if not rows:
        return {"especialidade_buscada": especialidade, "encontrada": False, "medicos": []}

    especialidade_real = rows[0]["especialidade"]
    por_medico = {}
    for r in rows:
        chave = (r["medico_cod"], r["medico_nome"])
        por_medico.setdefault(chave, {})
        por_medico[chave].setdefault(r["data"], []).append(r["horario"])

    medicos = []
    for (cod, nome), datas in por_medico.items():
        datas_lista = []
        for data in sorted(datas.keys())[:limite_datas]:
            datas_lista.append({"data": data, "horarios": sorted(datas[data])})
        medicos.append({
            "medico_cod": cod,
            "medico_nome": nome,
            "proximas_datas": datas_lista,
            "total_horarios_no_periodo": sum(len(h) for h in datas.values()),
        })
    medicos.sort(key=lambda m: -m["total_horarios_no_periodo"])

    return {
        "especialidade_buscada": especialidade,
        "especialidade_encontrada": especialidade_real,
        "encontrada": True,
        "medicos": medicos,
    }


def buscar_disponibilidade_medico(nome_busca: str, dias: int = 30, limite_datas: int = 5):
    """
    Busca médico(s) por nome/apelido (ex: "Malcher", "Dra. Fernanda") e
    retorna, pra cada um: especialidade (via V_ESP_MEDICO), se teve
    atendimento nos últimos 90 dias (agm) e a agenda aberta nos próximos
    `dias` (EX_HORARIOS) — cobre tanto "esse médico existe/atende aqui?"
    quanto "quando ele tem vaga?" na mesma resposta.
    """
    termo = (nome_busca or "").strip().upper()
    if not termo:
        return {"medico_buscado": nome_busca, "encontrado": False, "medicos": []}

    candidatos = query("""
        SELECT DISTINCT psv.psv_cod AS medico_cod, RTRIM(psv.psv_nome) AS medico_nome
        FROM psv
        WHERE UPPER(psv.psv_nome) LIKE ? OR UPPER(ISNULL(psv.psv_apel,'')) LIKE ?
    """, (f"%{termo}%", f"%{termo}%"))

    if not candidatos:
        return {"medico_buscado": nome_busca, "encontrado": False, "medicos": []}

    fim = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")
    medicos = []
    for cand in candidatos[:5]:
        cod = cand["medico_cod"]
        slots = query("""
            SELECT CONVERT(VARCHAR(10), eh.HOR_DATA, 120) AS data, eh.HORARIO_INICIO AS horario
            FROM EX_HORARIOS eh
            WHERE eh.HOR_MED = ? AND eh.HOR_DATA >= CAST(GETDATE() AS DATE) AND eh.HOR_DATA < CAST(? AS DATE)
            ORDER BY eh.HOR_DATA, eh.HORARIO_INICIO
        """, (cod, fim))

        esp_rows = query("SELECT RTRIM(especialidade) AS especialidade FROM V_ESP_MEDICO WHERE medico = ?", (cod,))
        especialidade = esp_rows[0]["especialidade"] if esp_rows else None

        atividade = query(
            "SELECT TOP 1 1 AS ok FROM agm WHERE agm_med = ? AND agm_hini >= DATEADD(day,-90,GETDATE())",
            (cod,),
        )

        datas = {}
        for s in slots:
            datas.setdefault(s["data"], []).append(s["horario"])
        datas_lista = [{"data": d, "horarios": sorted(datas[d])} for d in sorted(datas.keys())[:limite_datas]]

        medicos.append({
            "medico_cod": cod,
            "medico_nome": cand["medico_nome"],
            "especialidade": especialidade,
            "atende_recentemente": bool(atividade),
            "tem_agenda_aberta": len(slots) > 0,
            "proximas_datas": datas_lista,
            "total_horarios_no_periodo": len(slots),
        })

    return {"medico_buscado": nome_busca, "encontrado": True, "medicos": medicos}


@app.get("/api/agenda/disponibilidade-especialidade")
def disponibilidade_por_especialidade(especialidade: str, dias: int = 30, limite_datas: int = 5):
    """Endpoint HTTP fino sobre buscar_disponibilidade_especialidade — usado
    tanto pelo frontend quanto pelo bot de WhatsApp (agenda_bot.py)."""
    return buscar_disponibilidade_especialidade(especialidade, dias, limite_datas)


def buscar_medicos_agenda_hoje():
    """
    Lista todos os médicos com pelo menos 1 horário disponível hoje
    (EX_HORARIOS, SITUACAO='DISPONIVEL') — cobre a pergunta genérica "quais
    médicos têm agenda aberta hoje?", sem especialidade nem nome de médico
    específico. Retorna no mesmo formato de buscar_disponibilidade_medico/
    especialidade (proximas_datas com 1 entrada = hoje) pra reaproveitar o
    mesmo card no frontend.
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    rows = query("""
        SELECT
            eh.HOR_MED               AS medico_cod,
            RTRIM(psv.psv_nome)      AS medico_nome,
            RTRIM(v.especialidade)   AS especialidade,
            eh.HORARIO_INICIO        AS horario
        FROM EX_HORARIOS eh
        JOIN psv ON psv.psv_cod = eh.HOR_MED
        LEFT JOIN V_ESP_MEDICO v ON v.medico = eh.HOR_MED
        WHERE eh.HOR_DATA = CAST(GETDATE() AS DATE)
        ORDER BY v.especialidade, psv.psv_nome, eh.HORARIO_INICIO
    """)

    por_medico = {}
    for r in rows:
        chave = (r["medico_cod"], r["medico_nome"], r["especialidade"])
        por_medico.setdefault(chave, []).append(r["horario"])

    medicos = []
    for (cod, nome, esp), horarios in por_medico.items():
        medicos.append({
            "medico_cod": cod,
            "medico_nome": nome,
            "especialidade": esp,
            "proximas_datas": [{"data": hoje, "horarios": sorted(horarios)}],
            "total_horarios_no_periodo": len(horarios),
        })
    medicos.sort(key=lambda m: (m["especialidade"] or "", m["medico_nome"]))

    return {
        "data": hoje,
        "encontrada": len(medicos) > 0,
        "medicos": medicos,
    }


@app.get("/api/agenda/disponibilidade-hoje")
def disponibilidade_hoje():
    """Endpoint HTTP fino sobre buscar_medicos_agenda_hoje — usado pelo chat interno."""
    return buscar_medicos_agenda_hoje()


class ChatAgendaRequest(BaseModel):
    mensagem: str


@app.post("/api/agenda/chat")
def chat_agenda(payload: ChatAgendaRequest):
    """
    Assistente interno (chat dentro do Dashboard, não WhatsApp): recepção ou
    qualquer setor pergunta em linguagem natural — sobre uma especialidade
    ("temos dermatologista?") OU sobre um médico específico ("Dr. Malcher
    atende aqui?") — e recebe a disponibilidade real de agenda. Reaproveita
    o classificador via OpenAI do bot de WhatsApp (agenda_bot.py).
    """
    from agenda_bot import _extrair_intencao

    tipo_intencao, valor = _extrair_intencao(payload.mensagem)

    if tipo_intencao == "medico":
        resultado = buscar_disponibilidade_medico(valor)
        if not resultado["encontrado"]:
            resultado["mensagem"] = f'Não encontrei nenhum médico chamado "{valor}" no cadastro.'
        else:
            partes_sem_agenda = []
            for m in resultado["medicos"]:
                if not m["tem_agenda_aberta"]:
                    status = "atendeu recentemente" if m["atende_recentemente"] else "sem atendimento recente registrado"
                    esp = f" ({m['especialidade']})" if m["especialidade"] else ""
                    partes_sem_agenda.append(f"Dr(a). {m['medico_nome']}{esp} — {status}, mas sem agenda aberta nos próximos 30 dias.")
            if partes_sem_agenda:
                resultado["mensagem"] = " ".join(partes_sem_agenda)
        resultado["tipo"] = "disponibilidade_medico"
        return resultado

    if tipo_intencao == "especialidade":
        resultado = buscar_disponibilidade_especialidade(valor)
        if not resultado["encontrada"]:
            resultado["mensagem"] = (
                f'Não encontrei horários disponíveis para "{valor}" nos próximos 30 dias. Pode ser que não '
                f"tenhamos essa especialidade ativa agora, ou a agenda ainda não foi liberada."
            )
        resultado["tipo"] = "disponibilidade_especialidade"
        return resultado

    if tipo_intencao == "hoje":
        resultado = buscar_medicos_agenda_hoje()
        if not resultado["encontrada"]:
            resultado["mensagem"] = "Não encontrei nenhum médico com agenda aberta hoje."
        resultado["tipo"] = "disponibilidade_hoje"
        return resultado

    return {
        "tipo": "nao_entendido",
        "mensagem": 'Não entendi sua pergunta. Pode perguntar sobre uma especialidade ("temos dermatologista?"), um médico específico ("Dr. Malcher atende aqui?") ou pedir a lista geral de hoje ("quais médicos têm agenda aberta hoje?").',
    }


@app.get("/api/agenda/dia")
def agenda_medico_dia(cod_medico: int, data: str = None):
    """
    Agenda diária do médico — todos os horários do dia.
    data: YYYY-MM-DD (padrão = hoje)
    """
    if not data:
        data = datetime.now().strftime("%Y-%m-%d")
    rows = query("""
        SELECT
            agm.agm_hini                    AS hora_ini,
            agm.agm_hfim                    AS hora_fim,
            agm.agm_pac_nome                AS paciente,
            agm.agm_stat                    AS status,
            agm.agm_confirm_stat            AS confirmacao,
            esp.esp_nome                    AS especialidade,
            agm.agm_valor                   AS valor,
            loc.loc_nome                    AS local,
            cnv.cnv_nome                    AS convenio
        FROM agm
        LEFT JOIN esp ON esp.esp_cod   = agm.AGM_ESP_COD
        LEFT JOIN loc ON loc.loc_cod   = agm.agm_loc
        LEFT JOIN cnv ON cnv.cnv_cod   = agm.agm_cnv_cod
        WHERE agm.agm_med  = ?
          AND agm.agm_stat <> 'B'
          AND CAST(agm.agm_hini AS DATE) = ?
        ORDER BY agm.agm_hini
    """, (cod_medico, data))
    STATUS  = {"A":"Aberto","E":"Executado","C":"Cancelado"}
    CONFIRM = {"A":"Em aberto","C":"Confirmado","N":"Não confirmado"}
    for r in rows:
        r["status_label"]      = STATUS.get(r["status"], r["status"] or "—")
        r["confirmacao_label"] = CONFIRM.get(r["confirmacao"], r["confirmacao"] or "—")
        if r.get("hora_ini"): r["hora_ini"] = r["hora_ini"].strftime("%H:%M") if hasattr(r["hora_ini"],"strftime") else str(r["hora_ini"])[:5]
        if r.get("hora_fim"): r["hora_fim"] = r["hora_fim"].strftime("%H:%M") if hasattr(r["hora_fim"],"strftime") else str(r["hora_fim"])[:5]
    return rows


@app.get("/api/agenda/mensal")
def agenda_medico_mensal(cod_medico: int, ano: int = None, mes: int = None):
    """
    Agenda mensal do médico — agrupada por dia, apenas dias futuros.
    """
    now = datetime.now()
    if not ano: ano = now.year
    if not mes: mes = now.month
    import calendar
    ultimo = calendar.monthrange(ano, mes)[1]
    inicio = f"{ano}-{mes:02d}-01"
    fim    = f"{ano}-{mes:02d}-{ultimo}"

    rows = query("""
        SELECT
            CAST(agm.agm_hini AS DATE)                                      AS data,
            COUNT(*)                                                         AS total,
            SUM(CASE WHEN agm.agm_stat = 'E' THEN 1 ELSE 0 END)            AS executados,
            SUM(CASE WHEN agm.agm_stat = 'A' THEN 1 ELSE 0 END)            AS abertos,
            SUM(CASE WHEN agm.agm_stat = 'C' THEN 1 ELSE 0 END)            AS cancelados,
            ISNULL(SUM(agm.agm_valor), 0)                                   AS valor_total
        FROM agm
        WHERE agm.agm_med = ?
          AND agm.agm_stat <> 'B'
          AND CAST(agm.agm_hini AS DATE) BETWEEN ? AND ?
        GROUP BY CAST(agm.agm_hini AS DATE)
        ORDER BY data
    """, (cod_medico, inicio, fim))
    for r in rows:
        if hasattr(r.get("data"), "strftime"):
            r["data"] = r["data"].strftime("%Y-%m-%d")
    return rows


DIAS_SEMANA_COD = ["seg", "ter", "qua", "qui", "sex", "sab"]
DIAS_SEMANA_LABEL = {"seg": "Segunda", "ter": "Terça", "qua": "Quarta", "qui": "Quinta", "sex": "Sexta", "sab": "Sábado"}

@app.get("/api/agenda/semanal-por-medico")
def agenda_semanal_por_medico(inicio: str = None):
    """
    Quantidade de agendamentos por médico, aberta por dia da semana
    (segunda a sábado) -- base do relatório enviado toda segunda-feira.
    inicio: YYYY-MM-DD (uma segunda-feira). Padrão = a segunda desta semana.
    """
    if inicio:
        seg = datetime.strptime(inicio, "%Y-%m-%d")
    else:
        hoje = datetime.now()
        seg = hoje - timedelta(days=hoje.weekday())
    seg = seg.replace(hour=0, minute=0, second=0, microsecond=0)
    sab = seg + timedelta(days=5)

    rows = query("""
        SELECT RTRIM(psv.psv_apel) AS medico,
               CAST(agm.agm_hini AS DATE) AS dia,
               DATEPART(HOUR, agm.agm_hini) AS hora,
               COUNT(*) AS qtd
        FROM agm
        JOIN psv ON psv.psv_cod = agm.agm_med
        WHERE agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C', 'B')
          AND CAST(agm.agm_hini AS DATE) BETWEEN ? AND ?
        GROUP BY RTRIM(psv.psv_apel), CAST(agm.agm_hini AS DATE), DATEPART(HOUR, agm.agm_hini)
        ORDER BY medico, dia
    """, (seg.strftime("%Y-%m-%d"), sab.strftime("%Y-%m-%d")))

    por_medico = {}
    for r in rows:
        dia_idx = (r["dia"] - seg.date()).days if hasattr(r["dia"], "year") else None
        if dia_idx is None or not (0 <= dia_idx <= 5):
            continue
        cod_dia = DIAS_SEMANA_COD[dia_idx]
        medico = r["medico"]
        turno = "manha" if r["hora"] < 12 else "tarde"

        por_medico.setdefault(medico, {c: {"manha": 0, "tarde": 0} for c in DIAS_SEMANA_COD})
        por_medico[medico][cod_dia][turno] += r["qtd"]

    resultado = []
    for medico, dias_dict in por_medico.items():
        total_semana = sum(d["manha"] + d["tarde"] for d in dias_dict.values())
        resultado.append({"medico": medico, "dias": dias_dict, "total": total_semana})
    resultado.sort(key=lambda x: -x["total"])

    return {
        "inicio": seg.strftime("%Y-%m-%d"), "fim": sab.strftime("%Y-%m-%d"),
        "dias": [{"cod": c, "label": DIAS_SEMANA_LABEL[c], "data": (seg + timedelta(days=i)).strftime("%Y-%m-%d")}
                 for i, c in enumerate(DIAS_SEMANA_COD)],
        "medicos": resultado,
    }


def _producao_prevista_semana(seg: datetime, sab: datetime):
    """
    Previsão de produção da semana SE TODOS os agendamentos comparecerem
    (soma de agm_valor, sem filtrar por status de comparecimento) — aberta
    por turno (manhã/tarde), no mesmo espírito do resumo de produção por
    recepção já enviado no fechamento diário via WhatsApp.
    """
    rows = query("""
        SELECT CAST(agm.agm_hini AS DATE) AS dia,
               DATEPART(HOUR, agm.agm_hini) AS hora,
               ISNULL(SUM(agm.agm_valor), 0) AS valor
        FROM agm
        WHERE agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C', 'B')
          AND CAST(agm.agm_hini AS DATE) BETWEEN ? AND ?
        GROUP BY CAST(agm.agm_hini AS DATE), DATEPART(HOUR, agm.agm_hini)
        ORDER BY dia, hora
    """, (seg.strftime("%Y-%m-%d"), sab.strftime("%Y-%m-%d")))

    por_dia_turno = {c: {"manha": 0.0, "tarde": 0.0} for c in DIAS_SEMANA_COD}
    total = 0.0
    for r in rows:
        dia_idx = (r["dia"] - seg.date()).days if hasattr(r["dia"], "year") else None
        if dia_idx is None or not (0 <= dia_idx <= 5):
            continue
        cod_dia = DIAS_SEMANA_COD[dia_idx]
        turno = "manha" if r["hora"] < 12 else "tarde"
        valor = float(r["valor"] or 0)
        por_dia_turno[cod_dia][turno] += valor
        total += valor

    return {
        "total_previsto": round(total, 2),
        "por_dia_turno": {c: {t: round(v, 2) for t, v in turnos.items()} for c, turnos in por_dia_turno.items()},
    }


def _media_producao_semanal_historica(seg: datetime, n_semanas: int = 4):
    """
    Média de produção semanal (segunda a sábado) vinda SÓ da agenda (agm_valor),
    com base nas últimas `n_semanas` semanas COMPLETAS anteriores à semana do
    relatório — mesma fonte/fórmula usada em _producao_prevista_semana, só que
    aplicada a semanas já passadas, pra ficar comparável com a previsão da
    semana atual.
    """
    ini = (seg - timedelta(days=7 * n_semanas)).strftime("%Y-%m-%d")
    fim = (seg - timedelta(days=1)).strftime("%Y-%m-%d")  # sábado da semana anterior

    rows = query("""
        SELECT ISNULL(SUM(agm.agm_valor), 0) AS producao
        FROM agm
        WHERE agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C', 'B')
          AND CAST(agm.agm_hini AS DATE) BETWEEN ? AND ?
    """, (ini, fim))

    total = float(rows[0]["producao"] or 0) if rows else 0.0
    media = total / n_semanas if n_semanas else 0.0
    return {"media_semanal": round(media, 2), "n_semanas": n_semanas}


def gerar_pdf_agenda_semanal(inicio: str = None) -> str:
    """
    Gera o PDF visual do relatório semanal de agenda por médico e retorna o
    caminho do arquivo (quem chama é responsável por apagar depois). Usado
    tanto pelo endpoint HTTP quanto pelo envio automático (scheduler).
    """
    import subprocess, tempfile, base64 as _b64, uuid

    dados = agenda_semanal_por_medico(inicio=inicio)
    dias = dados["dias"]
    medicos = dados["medicos"]

    seg_dt = datetime.strptime(dados["inicio"], "%Y-%m-%d")
    sab_dt = datetime.strptime(dados["fim"], "%Y-%m-%d")
    producao = _producao_prevista_semana(seg_dt, sab_dt)
    media_hist = _media_producao_semanal_historica(seg_dt, n_semanas=4)

    def brl(v):
        return f"R$ {v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") if v is not None else "—"

    logo_path = os.path.join(DIST, "..", "public", "icds_logo.png")
    logo_b64 = ""
    try:
        with open(logo_path, "rb") as f:
            logo_b64 = _b64.b64encode(f.read()).decode()
    except FileNotFoundError:
        pass
    logo_censo_path = os.path.join(DIST, "..", "public", "logo_clinica_censo.png")
    logo_censo_b64 = ""
    try:
        with open(logo_censo_path, "rb") as f:
            logo_censo_b64 = _b64.b64encode(f.read()).decode()
    except FileNotFoundError:
        pass

    maximo = max((m["total"] for m in medicos), default=0) or 1

    def cor_celula(total_dia):
        if total_dia <= 0:
            return "#F8FAFC", "#CBD5E1", "#CBD5E1"
        intensidade = min(1.0, total_dia / max(1, maximo / len(dias) * 1.6))
        r1, g1, b1 = 0xD1, 0xFA, 0xE5  # verde bem claro
        r2, g2, b2 = 0x05, 0x96, 0x69  # verde escuro (mesmo tom do Faturamento)
        r = round(r1 + (r2 - r1) * intensidade)
        g = round(g1 + (g2 - g1) * intensidade)
        b = round(b1 + (b2 - b1) * intensidade)
        texto_total = "#fff" if intensidade > 0.55 else "#065F46"
        texto_sub = "rgba(255,255,255,0.8)" if intensidade > 0.55 else "#64748B"
        return f"rgb({r},{g},{b})", texto_total, texto_sub

    linhas_html = ""
    for m in medicos:
        celulas = ""
        for d in dias:
            manha, tarde = m["dias"][d["cod"]]["manha"], m["dias"][d["cod"]]["tarde"]
            total_dia = manha + tarde
            bg, cor_total, cor_sub = cor_celula(total_dia)
            if total_dia:
                conteudo = (f'<div class="cel-total-dia">{total_dia}</div>'
                            f'<div class="cel-turnos" style="color:{cor_sub};">{manha}m / {tarde}t</div>')
            else:
                conteudo = '—'
            celulas += f'<td style="background:{bg}; color:{cor_total};">{conteudo}</td>'
        linhas_html += f"""
        <tr>
          <td class="col-medico">{m['medico']}</td>
          {celulas}
          <td class="col-total">{m['total']}</td>
        </tr>"""

    cabecalho_dias = "".join(
        f'<th>{d["label"]}<br><span class="sub-data">{d["data"][8:10]}/{d["data"][5:7]}</span></th>'
        for d in dias
    )

    total_geral = sum(m["total"] for m in medicos)
    periodo_txt = f"{dados['inicio'][8:10]}/{dados['inicio'][5:7]} a {dados['fim'][8:10]}/{dados['fim'][5:7]}/{dados['fim'][0:4]}"

    # ── Previsão de produção por turno (Manhã/Tarde) — mesma grade de dias da tabela por médico ──
    linhas_turno_html = ""
    for turno, label in (("manha", "Manhã"), ("tarde", "Tarde")):
        celulas_turno = "".join(
            f'<td>{brl(producao["por_dia_turno"][d["cod"]][turno])}</td>' for d in dias
        )
        total_turno = sum(producao["por_dia_turno"][d["cod"]][turno] for d in dias)
        linhas_turno_html += f"""
        <tr>
          <td class="col-medico">{label}</td>
          {celulas_turno}
          <td class="col-total">{brl(total_turno)}</td>
        </tr>"""

    html = f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><style>
      @page {{ size: A4 landscape; margin: 16mm 14mm; }}
      * {{ box-sizing: border-box; }}
      body {{ font-family: 'Segoe UI', Arial, sans-serif; color:#1E293B; margin:0; }}
      .header {{ display:flex; justify-content:space-between; align-items:center; border-bottom:3px solid #8B1A1A; padding-bottom:14px; margin-bottom:20px; }}
      .header .logos {{ display:flex; align-items:center; gap:16px; }}
      .header .logos img:first-child {{ height:40px; }}
      .header .logos img:last-child {{ height:34px; }}
      .header .titulo {{ text-align:right; }}
      .header .titulo h1 {{ font-size:19px; margin:0; color:#8B1A1A; }}
      .header .titulo p {{ font-size:11.5px; color:#64748B; margin:2px 0 0; }}
      .info {{ display:flex; gap:14px; margin-bottom:18px; }}
      .info-card {{ background:#F8FAFC; border-radius:8px; padding:10px 16px; border-left:4px solid #059669; }}
      .info-card .label {{ font-size:10px; color:#64748B; text-transform:uppercase; font-weight:700; letter-spacing:.04em; }}
      .info-card .valor {{ font-size:18px; font-weight:800; color:#111827; margin-top:2px; }}
      table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
      th {{ background:#059669; color:#fff; padding:8px 6px; text-align:center; font-size:11px; font-weight:700; }}
      th .sub-data {{ font-size:9.5px; font-weight:400; opacity:.85; }}
      td {{ padding:6px; text-align:center; border-bottom:1px solid #E2E8F0; font-weight:700; }}
      .col-medico {{ text-align:left; font-weight:700; color:#111827; white-space:nowrap; padding-left:10px; }}
      .col-total {{ font-weight:800; color:#059669; background:#F0FDF4; }}
      .cel-total-dia {{ font-size:13px; font-weight:800; line-height:1.3; }}
      .cel-turnos {{ font-size:9px; font-weight:600; margin-top:1px; }}
      tr:nth-child(even) td:not([style]) {{ background:#FAFAFA; }}
      tr {{ break-inside:avoid; page-break-inside:avoid; }}
      .secao-titulo {{ font-size:14px; font-weight:800; color:#111827; margin:22px 0 10px; break-after:avoid; page-break-after:avoid; }}
      .legenda {{ font-size:10.5px; color:#94A3B8; margin-top:6px; }}
      .footer {{ margin-top:16px; font-size:10px; color:#94A3B8; border-top:1px solid #E2E8F0; padding-top:8px; }}
    </style></head><body>
      <div class="header">
        <div class="logos">
          <img src="data:image/png;base64,{logo_censo_b64}" alt="Clínica Censo"/>
          <img src="data:image/png;base64,{logo_b64}" alt="ICDS"/>
        </div>
        <div class="titulo">
          <h1>Relatório Semanal — Agenda por Médico</h1>
          <p>Semana de {periodo_txt}</p>
        </div>
      </div>
      <div class="info">
        <div class="info-card"><div class="label">Médicos com agenda</div><div class="valor">{len(medicos)}</div></div>
        <div class="info-card"><div class="label">Total de agendamentos</div><div class="valor">{total_geral}</div></div>
        <div class="info-card" style="border-left-color:#0891B2;"><div class="label">Previsão de produção (se todos vierem)</div><div class="valor">{brl(producao['total_previsto'])}</div></div>
        <div class="info-card" style="border-left-color:#7C3AED;"><div class="label">Média de produção semanal (últimas {media_hist['n_semanas']} semanas)</div><div class="valor">{brl(media_hist['media_semanal'])}</div></div>
      </div>
      <div class="secao-titulo">Agenda por Médico</div>
      <table><thead><tr>
        <th style="text-align:left; padding-left:10px;">Médico</th>{cabecalho_dias}<th>Total</th>
      </tr></thead><tbody>{linhas_html}</tbody></table>
      <div class="legenda">Em cada dia: total de agendamentos, com a divisão <b>m</b> = manhã / <b>t</b> = tarde logo abaixo.</div>

      <div class="secao-titulo">Previsão de Produção por Turno</div>
      <table><thead><tr>
        <th style="text-align:left; padding-left:10px;">Turno</th>{cabecalho_dias}<th>Total</th>
      </tr></thead><tbody>{linhas_turno_html}</tbody></table>

      <div class="footer">Previsão de produção considera o valor de todos os agendamentos da semana (agm_valor), inclusive os que ainda não ocorreram — ou seja, o total SE TODOS comparecerem. Considera agendamentos com paciente vinculado, exceto cancelados. Relatório gerado automaticamente pelo Dashboard ICDS.</div>
    </body></html>"""

    tmp_dir = tempfile.gettempdir()
    uid = uuid.uuid4().hex
    html_path = os.path.join(tmp_dir, f"agenda_semanal_{uid}.html")
    pdf_path = os.path.join(tmp_dir, f"agenda_semanal_{uid}.pdf")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    try:
        subprocess.run([
            chrome_path, "--headless", "--disable-gpu", "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}", f"file:///{html_path}",
        ], timeout=30, capture_output=True)
    finally:
        try: os.remove(html_path)
        except OSError: pass

    if not os.path.exists(pdf_path):
        raise RuntimeError("Falha ao gerar PDF do relatório semanal")
    return pdf_path


@app.get("/api/agenda/semanal-por-medico/pdf")
def agenda_semanal_por_medico_pdf(inicio: str = None, background_tasks: BackgroundTasks = None):
    pdf_path = gerar_pdf_agenda_semanal(inicio=inicio)
    background_tasks.add_task(lambda: os.remove(pdf_path) if os.path.exists(pdf_path) else None)
    return FileResponse(
        pdf_path, media_type="application/pdf",
        filename="Agenda_Semanal_Por_Medico.pdf", background=background_tasks,
    )


@app.get("/api/agenda/consultorios/valor-hora")
def consultorios_valor_hora(periodo: str = "30d"):
    """
    Valor gerado por hora ocupada, por consultório/sala (LOC) — só considera
    atendimentos EFETIVADOS (agm_stat='E'), já que é o único status em que o
    horário realmente ocorreu e o valor foi de fato gerado. agm_valor é o
    valor do agendamento em si (não é o mesmo dado de recebimento real usado
    em /api/financeiro — é a melhor granularidade disponível por sala, já
    que smm/fat não guardam local de forma confiável).
    """
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            RTRIM(loc.loc_cod)                                              AS cod,
            RTRIM(loc.loc_nome)                                             AS nome,
            COUNT(*)                                                        AS qtd_atendimentos,
            SUM(DATEDIFF(MINUTE, agm.agm_hini, agm.agm_hfim)) / 60.0        AS horas_ocupadas,
            ISNULL(SUM(agm.agm_valor), 0)                                   AS valor_total
        FROM agm
        JOIN loc ON loc.loc_cod = agm.agm_loc
        WHERE agm.agm_stat = 'E'
          AND agm.agm_hini BETWEEN ? AND ?
          AND agm.agm_hfim > agm.agm_hini
        GROUP BY RTRIM(loc.loc_cod), RTRIM(loc.loc_nome)
        HAVING SUM(DATEDIFF(MINUTE, agm.agm_hini, agm.agm_hfim)) >= 60  -- pelo menos 1h ocupada no periodo, pra evitar ruido de amostra pequena
        ORDER BY 5 DESC
    """, (inicio, fim))

    for r in rows:
        r["horas_ocupadas"] = round(r["horas_ocupadas"], 1)
        r["valor_total"] = round(r["valor_total"], 2)
        r["valor_hora"] = round(r["valor_total"] / r["horas_ocupadas"], 2) if r["horas_ocupadas"] else 0

    rows.sort(key=lambda r: r["valor_hora"], reverse=True)
    return rows


@app.get("/api/agenda/medicos/valor-hora")
def medicos_valor_hora(periodo: str = "30d"):
    """
    Mesmo cálculo de consultorios_valor_hora, mas agrupado por médico —
    hoje é a visão que realmente compara (a agenda usa praticamente uma
    sala genérica única, então por sala não rende ranking útil).

    Atribuição por médico EXECUTOR, não pelo dono do horário na agenda: em
    ~3% dos atendimentos o médico que realmente executou o procedimento
    (smm.SMM_MED — ex: um exame feito por outro especialista dentro da
    mesma consulta) é diferente de quem estava agendado (agm.AGM_MED).
    Resolve por visita: usa o SMM_MED do item de maior valor daquela visita
    quando existir, senão cai pro médico da agenda. Duração e valor
    continuam vindo do agendamento (agm) — só o médico creditado muda.
    """
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        WITH executor_visita AS (
            SELECT
                agm.AGM_ID,
                agm.agm_hini,
                agm.agm_hfim,
                agm.agm_valor,
                COALESCE(
                    (SELECT TOP 1 smm.SMM_MED
                     FROM smm
                     WHERE smm.SMM_OSM_SERIE = agm.AGM_OSM_SERIE AND smm.SMM_OSM = agm.AGM_OSM_NUM
                       AND smm.SMM_MED IS NOT NULL
                     ORDER BY smm.SMM_VLR DESC),
                    agm.AGM_MED
                ) AS medico_executor
            FROM agm
            WHERE agm.agm_stat = 'E'
              AND agm.agm_hini BETWEEN ? AND ?
              AND agm.agm_hfim > agm.agm_hini
        )
        SELECT
            psv.psv_cod                                                     AS cod,
            RTRIM(psv.psv_nome)                                             AS nome,
            COUNT(*)                                                        AS qtd_atendimentos,
            SUM(DATEDIFF(MINUTE, ev.agm_hini, ev.agm_hfim)) / 60.0          AS horas_ocupadas,
            ISNULL(SUM(ev.agm_valor), 0)                                    AS valor_total
        FROM executor_visita ev
        JOIN psv ON psv.psv_cod = ev.medico_executor
        GROUP BY psv.psv_cod, RTRIM(psv.psv_nome)
        HAVING SUM(DATEDIFF(MINUTE, ev.agm_hini, ev.agm_hfim)) >= 60  -- pelo menos 1h ocupada no periodo, pra evitar ruido de amostra pequena
    """, (inicio, fim))

    for r in rows:
        r["horas_ocupadas"] = round(r["horas_ocupadas"], 1)
        r["valor_total"] = round(r["valor_total"], 2)
        r["valor_hora"] = round(r["valor_total"] / r["horas_ocupadas"], 2) if r["horas_ocupadas"] else 0

    rows.sort(key=lambda r: r["valor_hora"], reverse=True)
    return rows


@app.get("/api/financeiro/particular")
def financeiro_particular(periodo: str = "30d", atend: str = ""):
    """
    Soma dos convênios cujo nome contenha 'PARTICULAR' (case-insensitive).
    Retorna total geral + breakdown por convênio particular encontrado.
    """
    inicio, fim = periodo_datas(periodo)
    filtro_atend = f"AND osm.osm_atend = '{atend}'" if atend else ""
    rows = query(f"""
        SELECT
            cnv.cnv_nome                                            AS convenio,
            COUNT(DISTINCT osm.osm_serie * 1000000 + osm.osm_num)  AS qtd_os,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                                        AS valor
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE
                AND osm.osm_num   = smm.SMM_OSM
        JOIN cnv ON cnv.cnv_cod   = osm.osm_cnv
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A', 'F', 'P')
          AND UPPER(cnv.cnv_nome) LIKE '%PARTICULAR%'
          {filtro_atend}
        GROUP BY cnv.cnv_nome
        ORDER BY valor DESC
    """)
    total = sum(r["valor"] or 0 for r in rows)
    qtd   = sum(r["qtd_os"] or 0 for r in rows)
    return {
        "total": total,
        "qtd_os": qtd,
        "convenios": rows
    }


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULOS ESPECÍFICOS — Financeiro + Estatísticas por módulo
# ══════════════════════════════════════════════════════════════════════════════


def modulo_especialidades_smm(inicio: str, fim: str, atend_codes: list, limit=8):
    """Retorna especialidades dos itens (SMM_ESP) para um conjunto de atend_codes."""
    codes_sql = ",".join(f"'{c}'" for c in atend_codes)
    if not atend_codes:
        # Sem filtro de atend — retorna todas
        where_atend = ""
    else:
        where_atend = f"AND osm.osm_atend IN ({codes_sql})"
    return query(f"""
        SELECT TOP {limit}
            esp.esp_nome                                        AS especialidade,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)  AS qtd,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                                    AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        JOIN esp ON esp.esp_cod = smm.SMM_ESP
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
          {where_atend}
        GROUP BY esp.esp_nome
        ORDER BY qtd DESC
    """)

def modulo_resumo_financeiro(inicio: str, fim: str, atend_codes: list):
    """Helper: retorna resumo financeiro para uma lista de osm_atend."""
    codes_sql = ",".join(f"'{c}'" for c in atend_codes)
    vliq = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"
    rows = query(f"""
        SELECT
            COUNT(DISTINCT osm.osm_serie * 1000000 + osm.osm_num)                           AS total_os,
            COUNT(DISTINCT osm.osm_pac)                                                      AS pacientes_unicos,
            SUM({vliq})                                                                    AS faturamento,
            SUM({vliq}) / NULLIF(COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num),0)     AS ticket_medio,
            SUM(smm.SMM_VLR)                                                               AS valor_bruto,
            SUM(ISNULL(smm.SMM_VLR_DESCONTO,0))                                           AS total_desconto,
            SUM(ISNULL(smm.SMM_VLR_COPARTIC,0))                                           AS total_copartic,
            SUM(ISNULL(smm.SMM_AJUSTE_VLR,0))                                             AS total_ajuste,
            COUNT(DISTINCT CASE WHEN smm.SMM_SFAT='F' THEN osm.osm_serie*1000000+osm.osm_num END) AS os_faturadas,
            SUM(CASE WHEN smm.SMM_SFAT='F' THEN {vliq} ELSE 0 END)                        AS val_faturado,
            SUM(CASE WHEN smm.SMM_SFAT='A' THEN {vliq} ELSE 0 END)                        AS val_aberto,
            SUM(CASE WHEN smm.SMM_SFAT='P' THEN {vliq} ELSE 0 END)                        AS val_pendente
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ({codes_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
    """)
    return rows[0] if rows else {}

def modulo_por_convenio(inicio: str, fim: str, atend_codes: list):
    codes_sql = ",".join(f"'{c}'" for c in atend_codes)
    return query(f"""
        SELECT cnv.cnv_nome AS convenio,
               COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS qtd_os,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        JOIN cnv ON cnv.cnv_cod=osm.osm_cnv
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ({codes_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
          AND cnv.cnv_nome IS NOT NULL AND LTRIM(RTRIM(cnv.cnv_nome))<>''
        GROUP BY cnv.cnv_nome ORDER BY valor DESC
    """)

def modulo_por_dia(inicio: str, fim: str, atend_codes: list):
    codes_sql = ",".join(f"'{c}'" for c in atend_codes)
    rows = query(f"""
        SELECT CAST(osm.osm_dthr AS DATE) AS data,
               COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS qtd_os,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ({codes_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY CAST(osm.osm_dthr AS DATE) ORDER BY data
    """)
    for r in rows:
        if hasattr(r.get("data"),"strftime"): r["data"] = r["data"].strftime("%Y-%m-%d")
    return rows


# ── ASSISTENCIAL ──────────────────────────────────────────────────────────────
ASSISTENCIAL_CODES = ["ASS","EME","CRG","TAM"]

@app.get("/api/modulo/assistencial/medicos-por-especialidade")
def assistencial_medicos_por_especialidade(periodo: str = "30d", especialidade: str = "", atend: str = "ASS"):
    """Lista médicos que atenderam em uma especialidade específica no período."""
    inicio, fim = periodo_datas(periodo)
    atends = ",".join([f"'{a.strip()}'" for a in atend.split(",")])
    rows = query(f"""
        SELECT TOP 20
            ISNULL(RTRIM(psv.psv_apel), RTRIM(psv.psv_nome))       AS medico,
            RTRIM(psv.psv_nome)                                      AS nome_completo,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)       AS qtd,
            COUNT(DISTINCT osm.osm_pac)                              AS pacientes,
            SUM(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) AS valor
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        JOIN psv ON psv.psv_cod = osm.osm_mreq
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
            AND osm.osm_atend IN ({atends})
            AND RTRIM(smm.SMM_ESP) = '{especialidade}'
            AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY ISNULL(RTRIM(psv.psv_apel), RTRIM(psv.psv_nome)), RTRIM(psv.psv_nome)
        ORDER BY valor DESC
    """)
    return rows
    # Agrupa por médico
    from collections import defaultdict
    med = defaultdict(lambda: {"qtd":0,"pacientes":set(),"valor":0.0})
    for r in rows:
        k = r["medico"]
        med[k]["qtd"] += 1
        med[k]["pacientes"].add(r.get("osm_pac") or r["medico"])
        med[k]["valor"] += float(r["valor"] or 0)
    result = sorted([
        {"medico":k,"qtd":v["qtd"],"pacientes":len(v["pacientes"]),"valor":round(v["valor"],2)}
        for k,v in med.items()
    ], key=lambda x: -x["valor"])
    return result[:20]

@app.get("/api/modulo/assistencial/resumo")
def assistencial_resumo(periodo: str = "30d"):
    inicio, fim = periodo_datas(periodo)
    fin = modulo_resumo_financeiro(inicio, fim, ASSISTENCIAL_CODES)
    ant_ini, ant_fim = periodo_anterior(inicio, fim)
    fin_ant = modulo_resumo_financeiro(ant_ini, ant_fim, ASSISTENCIAL_CODES)
    variacoes = {
        "faturamento":  var_pct(fin.get("faturamento"), fin_ant.get("faturamento")),
        "total_os":     var_pct(fin.get("total_os"), fin_ant.get("total_os")),
        "pacientes_unicos": var_pct(fin.get("pacientes_unicos"), fin_ant.get("pacientes_unicos")),
        "ticket_medio": var_pct(fin.get("ticket_medio"), fin_ant.get("ticket_medio")),
    }
    vliq = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"
    CONS  = ('CLI','PED','ORT','CAR','DER','GIN','RUM','GAS','URO','PNE','END','OFT','CIR','VAR','PRO','ANE','HAM','INF','MAM','MAS')
    EMULT = ('PSC','NUT','ENF','FIS','TER','FAR','ASS','SOC')

    # Totais gerais + divisão Consultas x Equipe Mult + Particular
    ops = query(f"""
        SELECT
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)  AS total_os,
            COUNT(DISTINCT osm.osm_pac)                         AS pacientes_unicos,
            -- Particular = convênio PAR (paga na recepção)
            COUNT(DISTINCT CASE WHEN RTRIM(osm.osm_cnv) = 'PAR'
                THEN osm.osm_serie*1000000+osm.osm_num END)     AS particular_os,
            COUNT(DISTINCT CASE WHEN RTRIM(osm.osm_cnv) = 'PAR'
                THEN osm.osm_pac END)                           AS particular_pac,
            SUM(CASE WHEN RTRIM(osm.osm_cnv) = 'PAR'
                THEN {vliq} ELSE 0 END)                         AS particular_valor,
            SUM({vliq})                                         AS producao_total_calc,
            SUM(CASE WHEN smm.SMM_SFAT = 'A'
                THEN {vliq} ELSE 0 END)                         AS pendente_calc,
            -- Consultas médicas (SMM_ESP = especialidade médica)
            COUNT(DISTINCT CASE WHEN RTRIM(smm.SMM_ESP) IN ('CLI','PED','ORT','CAR','DER','GIN','RUM','GAS','URO','PNE','END','OFT','CIR','VAR','PRO','ANE','HAM','INF','MAM','MAS')
                THEN osm.osm_serie*1000000+osm.osm_num END)     AS consultas_medicas,
            SUM(CASE WHEN RTRIM(smm.SMM_ESP) IN ('CLI','PED','ORT','CAR','DER','GIN','RUM','GAS','URO','PNE','END','OFT','CIR','VAR','PRO','ANE','HAM','INF','MAM','MAS')
                THEN {vliq} ELSE 0 END)                        AS valor_consultas,
            -- Equipe multidisciplinar (PSC, NUT, FON, ENF...)
            COUNT(DISTINCT CASE WHEN RTRIM(smm.SMM_ESP) IN ('PSC','NUT','ENF','FIS','TER','FAR','ASS','SOC')
                THEN osm.osm_serie*1000000+osm.osm_num END)     AS equipe_mult,
            SUM(CASE WHEN RTRIM(smm.SMM_ESP) IN ('PSC','NUT','ENF','FIS','TER','FAR','ASS','SOC')
                THEN {vliq} ELSE 0 END)                        AS valor_equipe_mult,
            -- Exames e diagnóstico
            COUNT(DISTINCT CASE WHEN RTRIM(smm.SMM_ESP) IN ('LAB','RAD','USG','ANC','CAR','ECG','EEG','EMG','EXO')
                THEN osm.osm_serie*1000000+osm.osm_num END)     AS exames_diag,
            SUM(CASE WHEN RTRIM(smm.SMM_ESP) IN ('LAB','RAD','USG','ANC','CAR','ECG','EEG','EMG','EXO')
                THEN {vliq} ELSE 0 END)                        AS valor_exames
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ('ASS','EME','CRG','TAM')
          AND smm.SMM_SFAT IN ('A','F','P')
    """)

    # Consultas médicas por especialidade — filtra pela classe Consulta (CTF_CATEG = 'C')
    consultas = query(f"""
        SELECT
            RTRIM(smm.SMM_ESP)                                          AS esp_cod,
            RTRIM(esp.esp_nome)                                         AS especialidade,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)          AS qtd,
            COUNT(DISTINCT osm.osm_pac)                                 AS pacientes,
            SUM({vliq})                                                AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        LEFT JOIN esp ON esp.esp_cod = smm.SMM_ESP
        JOIN smk ON smk.SMK_TIPO = smm.SMM_TPCOD AND smk.SMK_COD = smm.SMM_COD
        JOIN ctf ON RTRIM(ctf.CTF_COD) = RTRIM(smk.SMK_CTF) AND ctf.CTF_TIPO = 'S'
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ('ASS','EME','CRG','TAM')
          AND smm.SMM_SFAT IN ('A','F','P')
          AND RTRIM(ctf.CTF_CATEG) = 'C'
        GROUP BY RTRIM(smm.SMM_ESP), RTRIM(esp.esp_nome)
        ORDER BY qtd DESC
    """)

    # Equipe multidisciplinar por especialidade
    equipe = query(f"""
        SELECT
            RTRIM(smm.SMM_ESP)                                          AS esp_cod,
            RTRIM(esp.esp_nome)                                         AS especialidade,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)          AS qtd,
            COUNT(DISTINCT osm.osm_pac)                                 AS pacientes,
            SUM({vliq})                                                AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        LEFT JOIN esp ON esp.esp_cod = smm.SMM_ESP
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ('ASS','EME','CRG','TAM')
          AND smm.SMM_SFAT IN ('A','F','P')
          AND RTRIM(smm.SMM_ESP) IN ('PSC','NUT','ENF','FIS','TER','FAR','ASS','SOC')
        GROUP BY RTRIM(smm.SMM_ESP), RTRIM(esp.esp_nome)
        ORDER BY qtd DESC
    """)

    # Serviços por dia (volumetria de itens SMM)
    servicos_dia = query(f"""
        SELECT
            CAST(osm.osm_dthr AS DATE)                         AS data,
            COUNT(smm.SMM_NUM)                                 AS qtd_servicos,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS qtd_os,
            COUNT(DISTINCT osm.osm_pac)                        AS qtd_pac,
            SUM({vliq})                                        AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ('ASS','EME','CRG','TAM')
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY CAST(osm.osm_dthr AS DATE)
        ORDER BY data
    """)
    for r in servicos_dia:
        if hasattr(r.get("data"), "strftime"): r["data"] = r["data"].strftime("%Y-%m-%d")

    # SADT — Exames laboratoriais, imagem e outros
    sadt = query(f"""
        SELECT
            CASE
                WHEN RTRIM(smm.SMM_ESP) IN ('LAB','ANC')   THEN 'Laboratorial'
                WHEN RTRIM(smm.SMM_ESP) IN ('RAD','USG','ECG','EEG','EMG','EXO','CAR')   THEN 'Imagem'
                WHEN RTRIM(smm.SMM_ESP) IN ('ENF','FIS','TER') THEN 'Outros Serviços'
                ELSE 'Outros Serviços'
            END                                                             AS categoria,
            RTRIM(smm.SMM_ESP)                                              AS esp_cod,
            RTRIM(esp.esp_nome)                                             AS especialidade,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)              AS qtd_os,
            COUNT(smm.SMM_NUM)                                              AS qtd_servicos,
            COUNT(DISTINCT osm.osm_pac)                                     AS qtd_pac,
            SUM({vliq})                                                   AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        LEFT JOIN esp ON esp.esp_cod = smm.SMM_ESP
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ('ASS','EME','CRG','TAM')
          AND smm.SMM_SFAT IN ('A','F','P')
          AND RTRIM(smm.SMM_ESP) IN ('LAB','ANC','RAD','USG','ECG','EEG','EMG','EXO','CAR','ENF','FIS','TER')
        GROUP BY
            CASE WHEN RTRIM(smm.SMM_ESP) IN ('LAB','ANC') THEN 'Laboratorial'
                 WHEN RTRIM(smm.SMM_ESP) IN ('RAD','USG','ECG','EEG','EMG','EXO','CAR')  THEN 'Imagem'
                 ELSE 'Outros Serviços' END,
            RTRIM(smm.SMM_ESP), RTRIM(esp.esp_nome)
        ORDER BY categoria, valor DESC
    """)

    # Top exames laboratoriais por nome (SMK_ROT ou SMK_NOME via SMM_COD)
    sadt_lab = query(f"""
        SELECT TOP 20
            RTRIM(smm.SMM_COD)                                              AS cod,
            RTRIM(smk.SMK_ROT)                                              AS nome_curto,
            RTRIM(smk.SMK_NOME)                                             AS nome,
            COUNT(smm.SMM_NUM)                                              AS qtd_servicos,
            COUNT(DISTINCT osm.osm_pac)                                     AS qtd_pac,
            SUM({vliq})                                                     AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        LEFT JOIN smk ON smk.SMK_COD = smm.SMM_COD AND smk.SMK_TIPO = smm.SMM_TPCOD
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ('ASS','EME','CRG','TAM')
          AND smm.SMM_SFAT IN ('A','F','P')
          AND RTRIM(smm.SMM_ESP) IN ('LAB','ANC')
        GROUP BY RTRIM(smm.SMM_COD), RTRIM(smk.SMK_ROT), RTRIM(smk.SMK_NOME)
        ORDER BY qtd_servicos DESC
    """)

    return {
        "financeiro":       fin,
        "variacoes":        variacoes,
        "operacional":      ops[0] if ops else {},
        "consultas":        consultas,
        "equipe_mult":      equipe,
        "sadt":             sadt,
        "sadt_lab_exames":  sadt_lab,
        "por_convenio":     modulo_por_convenio(inicio, fim, ASSISTENCIAL_CODES),
        "por_dia":          modulo_por_dia(inicio, fim, ASSISTENCIAL_CODES),
        "servicos_dia":     servicos_dia,
    }


# ── MEDICINA OCUPACIONAL ──────────────────────────────────────────────────────
OCUP_CODES = ["ADM","PER","DEM","RTB","MDF","MOC"]

# Cache simples em memória — a consulta "todo o período" varre décadas de OS
# e leva ~1min pra rodar; sem cache, cada clique no filtro re-executa isso.
_CACHE_EMPRESAS_TODO = {"dados": None, "ts": None}
_CACHE_EMPRESAS_TODO_TTL_MIN = 30

@app.get("/api/modulo/ocupacional/empresas")
def ocupacional_empresas(modo: str = "mes", ano: int = None, mes: int = None):
    """
    Lista de empresas (Top Empresas do módulo Ocupacional) com filtro
    independente do período global da página — por mês específico
    (com navegação) ou "todo o período" (histórico completo), pra achar
    qual empresa mais trouxe produção desde sempre, não só no mês atual.
    """
    now = datetime.now()
    if modo == "todo":
        if _CACHE_EMPRESAS_TODO["dados"] is not None and _CACHE_EMPRESAS_TODO["ts"] is not None \
           and (now - _CACHE_EMPRESAS_TODO["ts"]).total_seconds() < _CACHE_EMPRESAS_TODO_TTL_MIN * 60:
            resultado = dict(_CACHE_EMPRESAS_TODO["dados"])
            resultado["cache"] = True
            return resultado
        inicio, fim = "2000-01-01", now.strftime("%Y-%m-%d")
    else:
        if not ano: ano = now.year
        if not mes: mes = now.month
        import calendar
        ultimo_dia = calendar.monthrange(ano, mes)[1]
        inicio = f"{ano}-{mes:02d}-01"
        fim = f"{ano}-{mes:02d}-{ultimo_dia}"

    empresas = query(f"""
        SELECT cnv.cnv_nome AS empresa,
            COUNT(DISTINCT CASE WHEN osm.osm_atend='ADM' THEN CAST(osm.osm_serie AS BIGINT)*1000000+osm.osm_num END) AS adm,
            COUNT(DISTINCT CASE WHEN osm.osm_atend='PER' THEN CAST(osm.osm_serie AS BIGINT)*1000000+osm.osm_num END) AS per,
            COUNT(DISTINCT CASE WHEN osm.osm_atend='DEM' THEN CAST(osm.osm_serie AS BIGINT)*1000000+osm.osm_num END) AS dem,
            COUNT(DISTINCT CAST(osm.osm_serie AS BIGINT)*1000000+osm.osm_num) AS total,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS faturamento
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        JOIN cnv ON cnv.cnv_cod=osm.osm_cnv
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY cnv.cnv_nome ORDER BY total DESC
    """)
    resultado = {"modo": modo, "ano": ano, "mes": mes, "inicio": inicio, "fim": fim, "empresas": empresas, "cache": False}
    if modo == "todo":
        _CACHE_EMPRESAS_TODO["dados"] = resultado
        _CACHE_EMPRESAS_TODO["ts"] = now
    return resultado


_SERVICOS_AVALIACAO_PSICOLOGICA = ("AVPSICO", "AVPSICO2", "AVPSICOC", "CONSPSC")


@app.get("/api/ocupacional/avaliacao-psicologica-empresas")
def ocupacional_avaliacao_psicologica_empresas(dias: int = 365):
    """
    Empresas que fizeram avaliação psicológica na Recepção Ocupacional (ROC)
    no período (padrão: últimos 365 dias) — quantidade de OS's e datas
    primeira/última, ordenado por quantidade.
    """
    placeholders = ",".join(f"'{s}'" for s in _SERVICOS_AVALIACAO_PSICOLOGICA)
    rows = query(f"""
        SELECT RTRIM(cnv.cnv_nome) AS empresa,
               COUNT(DISTINCT CAST(osm.osm_serie AS BIGINT)*1000000+osm.osm_num) AS qtd,
               MIN(osm.osm_dthr) AS primeira, MAX(osm.osm_dthr) AS ultima
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        JOIN cnv ON cnv.cnv_cod=osm.osm_cnv
        WHERE RTRIM(smm.SMM_COD) IN ({placeholders})
          AND RTRIM(osm.osm_str) = 'ROC'
          AND osm.osm_dthr >= DATEADD(day, -?, GETDATE())
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY RTRIM(cnv.cnv_nome)
        ORDER BY qtd DESC
    """, (dias,))
    for r in rows:
        r["primeira"] = r["primeira"].strftime("%Y-%m-%d") if r["primeira"] else None
        r["ultima"] = r["ultima"].strftime("%Y-%m-%d") if r["ultima"] else None
    return {"dias": dias, "total_empresas": len(rows), "empresas": rows}


@app.get("/api/ocupacional/avaliacao-psicologica-empresas/pdf")
def ocupacional_avaliacao_psicologica_empresas_pdf(dias: int = 365, background_tasks: BackgroundTasks = None):
    """PDF da lista de empresas com avaliação psicológica na Recepção Ocupacional no período."""
    import subprocess, tempfile, base64 as _b64, uuid

    dados = ocupacional_avaliacao_psicologica_empresas(dias=dias)
    empresas = dados["empresas"]

    logo_path = os.path.join(DIST, "..", "public", "icds_logo.png")
    logo_b64 = ""
    try:
        with open(logo_path, "rb") as f:
            logo_b64 = _b64.b64encode(f.read()).decode()
    except FileNotFoundError:
        pass
    logo_censo_path = os.path.join(DIST, "..", "public", "logo_clinica_censo.png")
    logo_censo_b64 = ""
    try:
        with open(logo_censo_path, "rb") as f:
            logo_censo_b64 = _b64.b64encode(f.read()).decode()
    except FileNotFoundError:
        pass

    def fmt_data(d):
        return f"{d[8:10]}/{d[5:7]}/{d[0:4]}" if d else "—"

    total_avaliacoes = sum(e["qtd"] for e in empresas)

    linhas_html = ""
    for e in empresas:
        linhas_html += f"""
        <tr>
          <td>{e['empresa']}</td>
          <td style="text-align:center;">{e['qtd']}</td>
          <td style="text-align:center;">{fmt_data(e['primeira'])}</td>
          <td style="text-align:center;">{fmt_data(e['ultima'])}</td>
        </tr>"""

    html = f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><style>
      @page {{ margin: 18mm 14mm; }}
      * {{ box-sizing: border-box; }}
      body {{ font-family: 'Segoe UI', Arial, sans-serif; color:#1E293B; margin:0; }}
      .header {{ display:flex; justify-content:space-between; align-items:center; border-bottom:3px solid #8B1A1A; padding-bottom:14px; margin-bottom:20px; }}
      .header .logos {{ display:flex; align-items:center; gap:16px; }}
      .header .logos img:first-child {{ height:40px; }}
      .header .logos img:last-child {{ height:34px; }}
      .header .titulo {{ text-align:right; }}
      .header .titulo h1 {{ font-size:18px; margin:0; color:#8B1A1A; }}
      .header .titulo p {{ font-size:11px; color:#64748B; margin:2px 0 0; }}
      .info {{ display:flex; gap:14px; margin-bottom:18px; flex-wrap:wrap; }}
      .info-card {{ background:#F8FAFC; border-radius:8px; padding:10px 16px; border-left:4px solid #8B1A1A; flex:1; min-width:140px; }}
      .info-card .label {{ font-size:10px; color:#64748B; text-transform:uppercase; font-weight:700; letter-spacing:.04em; }}
      .info-card .valor {{ font-size:18px; font-weight:800; color:#111827; margin-top:2px; }}
      table {{ width:100%; border-collapse:collapse; font-size:12px; }}
      th {{ background:#8B1A1A; color:#fff; padding:8px 10px; text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.03em; }}
      td {{ padding:7px 10px; border-bottom:1px solid #E2E8F0; }}
      tr:nth-child(even) {{ background:#FAFAFA; }}
      .footer {{ margin-top:24px; font-size:10px; color:#94A3B8; border-top:1px solid #E2E8F0; padding-top:8px; }}
    </style></head><body>
      <div class="header">
        <div class="logos">
          <img src="data:image/png;base64,{logo_censo_b64}" alt="Clínica Censo"/>
          <img src="data:image/png;base64,{logo_b64}" alt="ICDS"/>
        </div>
        <div class="titulo">
          <h1>Empresas — Avaliação Psicológica (Recepção Ocupacional)</h1>
          <p>Últimos {dias} dias</p>
        </div>
      </div>
      <div class="info">
        <div class="info-card"><div class="label">Empresas</div><div class="valor">{len(empresas)}</div></div>
        <div class="info-card"><div class="label">Total de Avaliações</div><div class="valor">{total_avaliacoes}</div></div>
      </div>
      <table><thead><tr>
        <th>Empresa</th><th style="text-align:center;">Qtd. Avaliações</th><th style="text-align:center;">Primeira</th><th style="text-align:center;">Última</th>
      </tr></thead><tbody>{linhas_html}</tbody></table>
      <div class="footer">Considera os serviços: Avaliação Psicológica, Avaliação Psicológica (R1+AC+PALO), Avaliação Psicológica Completa e Consulta Psicologia, na Recepção Ocupacional. Relatório gerado automaticamente pelo Dashboard ICDS.</div>
    </body></html>"""

    tmp_dir = tempfile.gettempdir()
    uid = uuid.uuid4().hex
    html_path = os.path.join(tmp_dir, f"avpsico_{uid}.html")
    pdf_path = os.path.join(tmp_dir, f"avpsico_{uid}.pdf")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    try:
        subprocess.run([
            chrome_path, "--headless", "--disable-gpu", "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}", f"file:///{html_path}",
        ], timeout=30, capture_output=True)
    finally:
        try: os.remove(html_path)
        except OSError: pass

    if not os.path.exists(pdf_path):
        raise HTTPException(500, "Falha ao gerar PDF")

    background_tasks.add_task(lambda: os.remove(pdf_path) if os.path.exists(pdf_path) else None)
    return FileResponse(
        pdf_path, media_type="application/pdf",
        filename="Empresas_Avaliacao_Psicologica_Ocupacional.pdf",
        background=background_tasks,
    )


@app.get("/api/modulo/ocupacional/variacao-empresas")
def ocupacional_variacao_empresas(ano: int = None, ano_comparacao: int = None):
    """
    Compara o faturamento por empresa (convênio) entre dois anos completos —
    por padrão o ano corrente vs o anterior — pra identificar rápido quais
    clientes estão em queda ou crescimento, sem precisar cruzar manualmente
    (foi assim que se achou, em uma investigação pontual, que a queda de
    faturamento do Ocupacional em 2025 estava concentrada num cliente só).
    """
    now = datetime.now()
    if not ano: ano = now.year
    if not ano_comparacao: ano_comparacao = ano - 1

    rows = query(f"""
        SELECT YEAR(osm.osm_dthr) AS ano, RTRIM(cnv.cnv_nome) AS empresa,
            SUM(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) AS valor,
            COUNT(DISTINCT CAST(osm.osm_serie AS BIGINT)*1000000+osm.osm_num) AS qtd_os
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        WHERE smm.SMM_SFAT IN ('A','F','P')
          AND osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')
          AND YEAR(osm.osm_dthr) IN (?, ?)
        GROUP BY YEAR(osm.osm_dthr), RTRIM(cnv.cnv_nome)
    """, (ano, ano_comparacao))

    por_empresa = {}
    for r in rows:
        emp = r["empresa"]
        if emp not in por_empresa:
            por_empresa[emp] = {"empresa": emp, "valor_atual": 0, "valor_anterior": 0, "qtd_atual": 0, "qtd_anterior": 0}
        if r["ano"] == ano:
            por_empresa[emp]["valor_atual"] = float(r["valor"] or 0)
            por_empresa[emp]["qtd_atual"] = r["qtd_os"]
        else:
            por_empresa[emp]["valor_anterior"] = float(r["valor"] or 0)
            por_empresa[emp]["qtd_anterior"] = r["qtd_os"]

    empresas = []
    for e in por_empresa.values():
        variacao = e["valor_atual"] - e["valor_anterior"]
        variacao_pct = (variacao / e["valor_anterior"] * 100) if e["valor_anterior"] else None
        empresas.append({**e, "variacao_valor": round(variacao, 2), "variacao_pct": round(variacao_pct, 1) if variacao_pct is not None else None})

    # só entram empresas com alguma relevância num dos dois anos, pra não poluir com ruído de empresas de valor irrisório
    empresas = [e for e in empresas if e["valor_atual"] >= 3000 or e["valor_anterior"] >= 3000]
    empresas.sort(key=lambda e: e["variacao_valor"])

    total_atual = sum(e["valor_atual"] for e in empresas)
    total_anterior = sum(e["valor_anterior"] for e in empresas)

    return {
        "ano": ano, "ano_comparacao": ano_comparacao,
        "total_atual": round(total_atual, 2), "total_anterior": round(total_anterior, 2),
        "variacao_total": round(total_atual - total_anterior, 2),
        "quedas": empresas[:15],
        "altas": sorted(empresas, key=lambda e: -e["variacao_valor"])[:15],
    }


@app.get("/api/modulo/ocupacional/resumo")
def ocupacional_modulo_resumo(periodo: str = "30d"):
    inicio, fim = periodo_datas(periodo)
    fin = modulo_resumo_financeiro(inicio, fim, OCUP_CODES)
    ant_ini, ant_fim = periodo_anterior(inicio, fim)
    fin_ant = modulo_resumo_financeiro(ant_ini, ant_fim, OCUP_CODES)
    variacoes = {
        "faturamento":      var_pct(fin.get("faturamento"), fin_ant.get("faturamento")),
        "total_os":         var_pct(fin.get("total_os"), fin_ant.get("total_os")),
        "pacientes_unicos": var_pct(fin.get("pacientes_unicos"), fin_ant.get("pacientes_unicos")),
        "ticket_medio":     var_pct(fin.get("ticket_medio"), fin_ant.get("ticket_medio")),
    }
    ops = query(f"""
        SELECT
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS total_os,
            COUNT(DISTINCT CASE WHEN osm.osm_atend='ADM' THEN osm.osm_serie*1000000+osm.osm_num END) AS admissional,
            COUNT(DISTINCT CASE WHEN osm.osm_atend='PER' THEN osm.osm_serie*1000000+osm.osm_num END) AS periodico,
            COUNT(DISTINCT CASE WHEN osm.osm_atend='DEM' THEN osm.osm_serie*1000000+osm.osm_num END) AS demissional,
            COUNT(DISTINCT CASE WHEN osm.osm_atend='RTB' THEN osm.osm_serie*1000000+osm.osm_num END) AS ret_trabalho,
            COUNT(DISTINCT CASE WHEN osm.osm_atend='MDF' THEN osm.osm_serie*1000000+osm.osm_num END) AS mud_funcao,
            COUNT(DISTINCT CASE WHEN osm.osm_atend='MOC' THEN osm.osm_serie*1000000+osm.osm_num END) AS med_ocup,
            COUNT(DISTINCT osm.osm_pac) AS pacientes_unicos,
            COUNT(DISTINCT osm.osm_cnv) AS empresas
        FROM osm
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')
    """)
    empresas = query(f"""
        SELECT cnv.cnv_nome AS empresa,
            COUNT(DISTINCT CASE WHEN osm.osm_atend='ADM' THEN osm.osm_serie*1000000+osm.osm_num END) AS adm,
            COUNT(DISTINCT CASE WHEN osm.osm_atend='PER' THEN osm.osm_serie*1000000+osm.osm_num END) AS per,
            COUNT(DISTINCT CASE WHEN osm.osm_atend='DEM' THEN osm.osm_serie*1000000+osm.osm_num END) AS dem,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS total,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS faturamento
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        JOIN cnv ON cnv.cnv_cod=osm.osm_cnv
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY cnv.cnv_nome ORDER BY total DESC
    """)
    return {
        "financeiro": fin,
        "variacoes": variacoes,
        "operacional": ops[0] if ops else {},
        "empresas": empresas,
        "especialidades": modulo_especialidades_smm(inicio, fim, OCUP_CODES),
        "por_convenio": modulo_por_convenio(inicio, fim, OCUP_CODES),
        "por_dia": modulo_por_dia(inicio, fim, OCUP_CODES),
    }


# ── SERVIÇOS ESPECIALIZADOS (PSI, NUT, FON, etc) ──────────────────────────────
SERVICOS_CODES = {
    "PSI": "Psicologia",
    "NUT": "Nutrição",
    "FON": "Fonoaudiologia",
    "FIS": "Fisioterapia",
    "OFT": "Oftalmologia",
    "DER": "Dermatologia",
    "END": "Endocrinologia",
    "GIN": "Ginecologia",
    "PED": "Pediatria",
    "ORT": "Ortopedia",
}

# Especialidades de Serviços — via SMM_ESP (PSC=Psicologia, NUT=Nutrição, FON=Fono etc)
SERVICOS_ESP_CODES = ["PSC","NUT","FON","NEU","PED","GIN","ORT","DER","PSQ","ENF","ANC","RAD","USG","CAR"]

def servicos_financeiro(inicio: str, fim: str, codes_sql: str):
    rows = query(f"""
        SELECT
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)               AS total_os,
            COUNT(DISTINCT osm.osm_pac)                                      AS pacientes_unicos,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                                                 AS faturamento,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))/NULLIF(COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num),0) AS ticket_medio,
            SUM(CASE WHEN smm.SMM_SFAT='A' THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END)     AS val_aberto
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP IN ({codes_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
    """)
    return rows[0] if rows else {}

@app.get("/api/modulo/servicos/resumo")
def servicos_resumo(periodo: str = "30d"):
    """
    Serviços especializados identificados pelo campo SMM_ESP dos itens da OS.
    Inclui Psicologia (PSC), Nutrição (NUT), Fonoaudiologia (FON), etc.
    """
    inicio, fim = periodo_datas(periodo)
    codes_sql = ",".join(f"'{c}'" for c in SERVICOS_ESP_CODES)
    ant_ini, ant_fim = periodo_anterior(inicio, fim)
    fin_ant = servicos_financeiro(ant_ini, ant_fim, codes_sql)

    # Por especialidade de item (SMM_ESP)
    por_tipo = query(f"""
        SELECT
            smm.SMM_ESP                                             AS codigo,
            esp.esp_nome                                            AS nome,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)      AS qtd_os,
            COUNT(DISTINCT osm.osm_pac)                            AS pacientes,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                                       AS faturamento
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        JOIN esp ON esp.esp_cod = smm.SMM_ESP
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP IN ({codes_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY smm.SMM_ESP, esp.esp_nome
        ORDER BY faturamento DESC
    """)

    # Financeiro total desses serviços
    fin = query(f"""
        SELECT
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)               AS total_os,
            COUNT(DISTINCT osm.osm_pac)                                      AS pacientes_unicos,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                                                 AS faturamento,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))/NULLIF(COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num),0) AS ticket_medio,
            SUM(CASE WHEN smm.SMM_SFAT='A' THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END)     AS val_aberto
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP IN ({codes_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
    """)

    # Por dia
    por_dia = query(f"""
        SELECT CAST(osm.osm_dthr AS DATE) AS data,
               COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS qtd_os,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP IN ({codes_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY CAST(osm.osm_dthr AS DATE) ORDER BY data
    """)
    for r in por_dia:
        if hasattr(r.get("data"),"strftime"): r["data"] = r["data"].strftime("%Y-%m-%d")

    fin_atual = fin[0] if fin else {}
    variacoes = {
        "faturamento":      var_pct(fin_atual.get("faturamento"), fin_ant.get("faturamento")),
        "total_os":         var_pct(fin_atual.get("total_os"), fin_ant.get("total_os")),
        "pacientes_unicos": var_pct(fin_atual.get("pacientes_unicos"), fin_ant.get("pacientes_unicos")),
        "ticket_medio":     var_pct(fin_atual.get("ticket_medio"), fin_ant.get("ticket_medio")),
    }
    return {
        "financeiro": fin_atual,
        "variacoes": variacoes,
        "por_servico": por_tipo,
        "por_dia": por_dia,
    }


# ── LABORATÓRIO E DIAGNÓSTICO ─────────────────────────────────────────────────
LAB_GRUPOS = {
    "sangue":  { "label":"Análises Clínicas", "codes":["LAB","HEM","BIO","SOR"] },
    "imagem":  { "label":"Imagem",            "codes":["RAD","USG","RX","ECO","TMG","RES"] },
    "cardio":  { "label":"Cardiologia Diagnóstica","codes":["CAR","ECG","HOL","ERT"] },
    "outros":  { "label":"Outros Diagnósticos","codes":["PNE","EEG","EMG","BIO"] },
}

# Grupos de laboratório por SMM_ESP
LAB_ESP_GRUPOS = {
    "lab": { "label":"Análises Clínicas", "codes":["LAB"] },
}
ALL_LAB_ESP = ["LAB"]  # Apenas análises clínicas / exames de sangue

def laboratorio_financeiro(inicio: str, fim: str, esp_sql: str, filtro_setor: str):
    rows = query(f"""
        SELECT
            COUNT(*)                                                                        AS total_exames,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)                              AS total_os,
            COUNT(DISTINCT osm.osm_pac)                                                     AS pacientes_unicos,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                                                                AS faturamento,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))/NULLIF(COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num),0)   AS ticket_medio
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP IN ({esp_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_setor}
    """)
    return rows[0] if rows else {}

@app.get("/api/modulo/laboratorio/resumo")
def laboratorio_resumo(periodo: str = "30d", setor: str = "", recepcao: str = ""):
    """
    setor: 'diagnostico' → exclui OSs ocupacionais (ASS only)
           'ocupacional' → apenas OSs ocupacionais (ADM,PER,DEM etc)
           ''            → todos
    recepcao: código do ponto de recepção (osm_str) — ex: RDI, RCI, ROC, RCN
    """
    """
    Laboratório e diagnóstico identificados pelo campo SMM_ESP dos itens da OS.
    LAB=Análises clínicas, RAD=Radiologia, USG=Ultrassom, CAR=Cardiologia.
    """
    inicio, fim = periodo_datas(periodo)
    esp_sql = ",".join(f"'{c}'" for c in ALL_LAB_ESP)

    # Filtro de setor
    if setor == "diagnostico":
        filtro_setor = "AND osm.osm_atend IN ('ASS','EME','CRG','TAM')"
    elif setor == "ocupacional":
        filtro_setor = "AND osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')"
    else:
        filtro_setor = ""

    recepcao_cod = "".join(ch for ch in recepcao if ch.isalnum())[:6]
    if recepcao_cod:
        filtro_setor += f" AND RTRIM(osm.osm_str) = '{recepcao_cod}'"

    # Por especialidade de item
    por_tipo = query(f"""
        SELECT
            smm.SMM_ESP                         AS codigo,
            esp.esp_nome                        AS nome,
            COUNT(*)                            AS qtd_os,       -- itens/exames realizados
            COUNT(DISTINCT osm.osm_pac)         AS pacientes,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                    AS faturamento,
            COUNT(DISTINCT smm.SMM_COD)         AS tipos_exame
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        JOIN esp ON esp.esp_cod = smm.SMM_ESP
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP IN ({esp_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_setor}
        GROUP BY smm.SMM_ESP, esp.esp_nome
        ORDER BY faturamento DESC
    """)

    # Top exames por especialidade
    top_exames = query(f"""
        SELECT TOP 20
            smm.SMM_ESP                AS esp_cod,
            RTRIM(smm.SMM_COD)         AS exame_cod,
            COUNT(*)                   AS qtd,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))           AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP IN ({esp_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_setor}
        GROUP BY smm.SMM_ESP, smm.SMM_COD
        ORDER BY smm.SMM_ESP, qtd DESC
    """)

    # Grupos
    grupos = {}
    for key, g in LAB_ESP_GRUPOS.items():
        itens = [r for r in por_tipo if r["codigo"] in g["codes"]]
        if itens:
            exames_grp = [e for e in top_exames if e["esp_cod"] in g["codes"]]
            grupos[key] = {
                "label": g["label"],
                "total_os": sum(r["qtd_os"] or 0 for r in itens),
                "pacientes": sum(r["pacientes"] or 0 for r in itens),
                "faturamento": sum(r["faturamento"] or 0 for r in itens),
                "itens": itens,
                "top_exames": exames_grp[:5],
            }

    # Financeiro total
    # total_os = itens de exame; ticket_medio = faturamento / OSs distintas
    fin = query(f"""
        SELECT
            COUNT(*)                                                                        AS total_exames,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)                              AS total_os,
            COUNT(DISTINCT osm.osm_pac)                                                     AS pacientes_unicos,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                                                                AS faturamento,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))/NULLIF(COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num),0)   AS ticket_medio,
            SUM(CASE WHEN smm.SMM_SFAT='A' THEN (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) ELSE 0 END)                    AS val_aberto
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP IN ({esp_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_setor}
    """)

    # Por convênio
    conv = query(f"""
        SELECT cnv.cnv_nome AS convenio,
               COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS qtd_os,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        JOIN cnv ON cnv.cnv_cod=osm.osm_cnv
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP IN ({esp_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_setor}
        GROUP BY cnv.cnv_nome ORDER BY valor DESC
    """)

    # Por dia
    por_dia = query(f"""
        SELECT CAST(osm.osm_dthr AS DATE) AS data,
               COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS qtd_os,
               SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP IN ({esp_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_setor}
        GROUP BY CAST(osm.osm_dthr AS DATE) ORDER BY data
    """)
    for r in por_dia:
        if hasattr(r.get("data"),"strftime"): r["data"] = r["data"].strftime("%Y-%m-%d")

    # Top médicos por quantidade de OSs e exames no lab
    top_medicos = query(f"""
        SELECT TOP 15
            ISNULL(RTRIM(psv.psv_apel), RTRIM(psv.psv_nome))       AS medico,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)       AS total_os,
            COUNT(*)                                                  AS total_exames,
            COUNT(DISTINCT osm.osm_pac)                              AS pacientes,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                                         AS faturamento,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))/NULLIF(COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num),0) AS ticket_por_os
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        LEFT JOIN psv ON psv.psv_cod = osm.osm_mreq
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP IN ({esp_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_setor}
          AND psv.psv_cod IS NOT NULL
        GROUP BY psv.psv_apel, psv.psv_nome
        ORDER BY faturamento DESC
    """)

    fin_atual = fin[0] if fin else {}
    ant_ini, ant_fim = periodo_anterior(inicio, fim)
    fin_ant = laboratorio_financeiro(ant_ini, ant_fim, esp_sql, filtro_setor)
    variacoes = {
        "faturamento":      var_pct(fin_atual.get("faturamento"), fin_ant.get("faturamento")),
        "total_os":         var_pct(fin_atual.get("total_os"), fin_ant.get("total_os")),
        "pacientes_unicos": var_pct(fin_atual.get("pacientes_unicos"), fin_ant.get("pacientes_unicos")),
        "ticket_medio":     var_pct(fin_atual.get("ticket_medio"), fin_ant.get("ticket_medio")),
    }

    return {
        "financeiro": fin_atual,
        "variacoes": variacoes,
        "por_tipo": por_tipo,
        "grupos": grupos,
        "por_convenio": conv,
        "por_dia": por_dia,
        "top_medicos": top_medicos,
    }


# Bancadas que representam laboratório de apoio (externo) — as demais são internas.
BANCADAS_EXTERNAS = ["HP", "DB", "PSY"]
# Não trabalhamos mais com Hermes Pardini para exames laboratoriais — tudo que
# estiver marcado como HP no Pixeon é reclassificado para DB (Diagnósticos do Brasil).
BANCADA_REMAP = {"HP": "DB"}

@app.get("/api/modulo/laboratorio/bancadas")
def laboratorio_bancadas(periodo: str = "30d", setor: str = "", recepcao: str = ""):
    """
    Volume e faturamento por bancada de laboratório (BNC), identificando quais
    bancadas são de apoio externo (Hermes Pardini, DB Diagnósticos, Psychemedics)
    vs. processadas internamente. Vínculo exame→bancada via tabela SBN.
    recepcao: código do ponto de recepção (osm_str) — ex: RDI, RCI, ROC, RCN
    """
    inicio, fim = periodo_datas(periodo)
    esp_sql = ",".join(f"'{c}'" for c in ALL_LAB_ESP)

    if setor == "diagnostico":
        filtro_setor = "AND osm.osm_atend IN ('ASS','EME','CRG','TAM')"
    elif setor == "ocupacional":
        filtro_setor = "AND osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')"
    else:
        filtro_setor = ""

    recepcao_cod = "".join(ch for ch in recepcao if ch.isalnum())[:6]
    if recepcao_cod:
        filtro_setor += f" AND RTRIM(osm.osm_str) = '{recepcao_cod}'"

    ext_sql = ",".join(f"'{b}'" for b in BANCADAS_EXTERNAS)

    rows = query(f"""
        SELECT
            RTRIM(sbn.SBN_BNC_COD)                                                          AS bancada_cod,
            RTRIM(bnc.BNC_NOME)                                                              AS bancada_nome,
            COUNT(*)                                                                         AS qtd_exames,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)                               AS qtd_os,
            COUNT(DISTINCT osm.osm_pac)                                                      AS pacientes,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        LEFT JOIN SBN sbn ON RTRIM(sbn.SBN_SMK_COD) = RTRIM(smm.SMM_COD)
        LEFT JOIN BNC bnc ON RTRIM(bnc.BNC_COD) = RTRIM(sbn.SBN_BNC_COD) AND RTRIM(bnc.BNC_STR_COD) = RTRIM(sbn.SBN_STR_COD)
        WHERE smm.SMM_ESP IN ({esp_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
          AND osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          {filtro_setor}
        GROUP BY RTRIM(sbn.SBN_BNC_COD), RTRIM(bnc.BNC_NOME)
        ORDER BY valor DESC
    """)

    por_codigo = {}  # cod (já remapeado) -> agregado
    resumo = {"interno_qtd": 0, "interno_valor": 0.0, "externo_qtd": 0, "externo_valor": 0.0,
              "nao_classificado_qtd": 0, "nao_classificado_valor": 0.0}

    for r in rows:
        cod_original = r["bancada_cod"]
        valor = float(r["valor"] or 0)
        if cod_original is None:
            # Exame sem bancada cadastrada no Pixeon: soma no card DB (Diagnósticos do Brasil),
            # o único laboratório de apoio externo em uso hoje. `nao_classificado_*` continua
            # registrado à parte só para alimentar a lista de detalhe (quais exames faltam
            # cadastrar em SBN) — não entra mais como um total isolado.
            resumo["nao_classificado_qtd"] += r["qtd_exames"]
            resumo["nao_classificado_valor"] += valor
            cod = "DB"
        else:
            cod = BANCADA_REMAP.get(cod_original, cod_original)
        tipo = "externo" if cod in BANCADAS_EXTERNAS else "interno"
        if tipo == "externo":
            resumo["externo_qtd"] += r["qtd_exames"]
            resumo["externo_valor"] += valor
        else:
            resumo["interno_qtd"] += r["qtd_exames"]
            resumo["interno_valor"] += valor

        if cod not in por_codigo:
            por_codigo[cod] = {
                "codigo": cod,
                "nome": "DIAGNOSTICOS DO BRASIL" if cod == "DB" else (r["bancada_nome"] or cod),
                "tipo": tipo,
                "qtd_exames": 0, "qtd_os": 0, "pacientes": 0, "valor": 0.0,
            }
        agg = por_codigo[cod]
        agg["qtd_exames"] += r["qtd_exames"]
        agg["qtd_os"]     += r["qtd_os"]
        agg["pacientes"]  += r["pacientes"]  # aproximado: pode haver paciente em ambas as bancadas remapeadas
        agg["valor"]      += valor

    bancadas = sorted(por_codigo.values(), key=lambda b: -b["valor"])

    # nao_classificado_* já está incluído em externo_qtd/externo_valor (foi somado no DB acima).
    total_qtd = resumo["interno_qtd"] + resumo["externo_qtd"]
    total_valor = resumo["interno_valor"] + resumo["externo_valor"]
    resumo["pct_externo_qtd"] = round(resumo["externo_qtd"] / total_qtd * 100, 1) if total_qtd else 0
    resumo["pct_externo_valor"] = round(resumo["externo_valor"] / total_valor * 100, 1) if total_valor else 0

    # Detalhe dos exames realizados sem bancada vinculada — para saber o que falta cadastrar em SBN no Pixeon.
    nao_classificados = query(f"""
        SELECT
            RTRIM(smm.SMM_COD)                                                              AS codigo,
            RTRIM(MAX(smk.SMK_NOME))                                                         AS nome,
            COUNT(*)                                                                         AS qtd_exames,
            COUNT(DISTINCT osm.osm_pac)                                                      AS pacientes,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        LEFT JOIN SBN sbn ON RTRIM(sbn.SBN_SMK_COD) = RTRIM(smm.SMM_COD)
        LEFT JOIN SMK smk ON RTRIM(smk.SMK_COD) = RTRIM(smm.SMM_COD)
        WHERE smm.SMM_ESP IN ({esp_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
          AND osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND sbn.SBN_BNC_COD IS NULL
          {filtro_setor}
        GROUP BY RTRIM(smm.SMM_COD)
        ORDER BY qtd_exames DESC
    """)
    for r in nao_classificados:
        r["valor"] = float(r["valor"] or 0)

    return {
        "bancadas": bancadas,
        "resumo": resumo,
        "nao_classificados": nao_classificados,
    }


@app.get("/api/modulo/laboratorio/por-recepcao")
def laboratorio_por_recepcao(periodo: str = "30d", setor: str = ""):
    """
    Produção de exames laboratoriais quebrada por ponto de recepção (osm_str),
    no mesmo formato usado no Painel em tempo real (coluna por recepção).
    """
    inicio, fim = periodo_datas(periodo)
    esp_sql = ",".join(f"'{c}'" for c in ALL_LAB_ESP)

    if setor == "diagnostico":
        filtro_setor = "AND osm.osm_atend IN ('ASS','EME','CRG','TAM')"
    elif setor == "ocupacional":
        filtro_setor = "AND osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')"
    else:
        filtro_setor = ""

    rows = query(f"""
        SELECT
            RTRIM(osm.osm_str)                                                              AS recepcao_cod,
            COUNT(*)                                                                        AS total_exames,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)                               AS total_os,
            COUNT(DISTINCT osm.osm_pac)                                                      AS pacientes,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS faturamento
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP IN ({esp_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_setor}
        GROUP BY RTRIM(osm.osm_str)
        ORDER BY faturamento DESC
    """)
    for r in rows:
        r["faturamento"] = float(r["faturamento"] or 0)
        r["ticket_medio"] = (r["faturamento"] / r["total_os"]) if r["total_os"] else 0
    return rows


def _agrega_tempo(rows):
    total_amostras = sum(r["amostras"] for r in rows)
    media_geral = (sum(r["tempo_medio_min"] * r["amostras"] for r in rows) / total_amostras) if total_amostras else None
    return {"media_min": media_geral, "amostras": total_amostras, "por_recepcao": rows}


@app.get("/api/modulo/laboratorio/tempo-coleta")
def laboratorio_tempo_coleta(periodo: str = "30d", setor: str = "", recepcao: str = ""):
    """
    Duas métricas de tempo até a coleta da amostra laboratorial (SMM_DTHR_COLETA),
    quebradas por ponto de recepção:
    - senha_coleta: da emissão da senha na recepção (FLE_DTHR_CHEGADA) até a coleta
    - os_coleta: da abertura da OS (osm_dthr) até o registro da coleta
    """
    inicio, fim = periodo_datas(periodo)
    esp_sql = ",".join(f"'{c}'" for c in ALL_LAB_ESP)

    if setor == "diagnostico":
        filtro_setor = "AND osm.osm_atend IN ('ASS','EME','CRG','TAM')"
    elif setor == "ocupacional":
        filtro_setor = "AND osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')"
    else:
        filtro_setor = ""

    recepcao_cod = "".join(ch for ch in recepcao if ch.isalnum())[:6]
    if recepcao_cod:
        filtro_setor += f" AND RTRIM(osm.osm_str) = '{recepcao_cod}'"

    rows_senha = query(f"""
        WITH chegadas AS (
            -- Uma linha por (paciente, dia): primeira senha emitida na recepção
            SELECT fle.FLE_PAC_REG, CAST(fle.FLE_DTHR_CHEGADA AS DATE) AS data_cheg,
                   MIN(fle.FLE_DTHR_CHEGADA) AS chegada_min
            FROM fle
            WHERE fle.FLE_DTHR_CHEGADA BETWEEN '{inicio}' AND '{fim} 23:59:59'
              AND fle.FLE_PAC_REG > 0
            GROUP BY fle.FLE_PAC_REG, CAST(fle.FLE_DTHR_CHEGADA AS DATE)
        ),
        coletas AS (
            -- Uma linha por (paciente, dia, recepção): primeira coleta de amostra lab
            SELECT osm.osm_pac AS pac, CAST(osm.osm_dthr AS DATE) AS data_col,
                   RTRIM(osm.osm_str) AS recepcao_cod,
                   MIN(smm.SMM_DTHR_COLETA) AS coleta_min
            FROM smm
            JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
            WHERE smm.SMM_ESP IN ({esp_sql})
              AND smm.SMM_SFAT IN ('A','F','P')
              AND smm.SMM_DTHR_COLETA IS NOT NULL
              AND osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
              {filtro_setor}
            GROUP BY osm.osm_pac, CAST(osm.osm_dthr AS DATE), RTRIM(osm.osm_str)
        ),
        pares AS (
            SELECT k.recepcao_cod,
                   DATEDIFF(minute, c.chegada_min, k.coleta_min) AS espera_min
            FROM coletas k
            JOIN chegadas c ON c.FLE_PAC_REG = k.pac AND c.data_cheg = k.data_col
            WHERE DATEDIFF(minute, c.chegada_min, k.coleta_min) BETWEEN 0 AND 300
        )
        SELECT
            recepcao_cod,
            AVG(CAST(espera_min AS FLOAT)) AS tempo_medio_min,
            MIN(espera_min)                AS tempo_min_min,
            MAX(espera_min)                AS tempo_max_min,
            COUNT(*)                       AS amostras
        FROM pares
        GROUP BY recepcao_cod
        ORDER BY amostras DESC
    """)

    rows_os = query(f"""
        WITH pares AS (
            SELECT RTRIM(osm.osm_str) AS recepcao_cod,
                   DATEDIFF(minute, osm.osm_dthr, smm.SMM_DTHR_COLETA) AS espera_min
            FROM smm
            JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
            WHERE smm.SMM_ESP IN ({esp_sql})
              AND smm.SMM_SFAT IN ('A','F','P')
              AND smm.SMM_DTHR_COLETA IS NOT NULL
              AND osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
              {filtro_setor}
        )
        SELECT
            recepcao_cod,
            AVG(CAST(espera_min AS FLOAT)) AS tempo_medio_min,
            MIN(espera_min)                AS tempo_min_min,
            MAX(espera_min)                AS tempo_max_min,
            COUNT(*)                       AS amostras
        FROM pares
        WHERE espera_min BETWEEN 0 AND 300
        GROUP BY recepcao_cod
        ORDER BY amostras DESC
    """)

    return {
        "senha_coleta": _agrega_tempo(rows_senha),
        "os_coleta":    _agrega_tempo(rows_os),
    }


@app.get("/api/modulo/laboratorio/producao-por-profissional")
def laboratorio_producao_por_profissional(periodo: str = "30d", setor: str = "", recepcao: str = ""):
    """
    Produção laboratorial por profissional. IMPORTANTE: SMM_USR_LOGIN_COLETA
    (quem fisicamente colheu a amostra) está 100% vazio nesta base — não é
    usado. Agrupa por SMM_USR_LOGIN_LANC (quem lançou/registrou o exame na
    OS), que na prática corresponde à recepção que abriu o pedido.
    """
    inicio, fim = periodo_datas(periodo)
    esp_sql = ",".join(f"'{c}'" for c in ALL_LAB_ESP)
    vliq = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"

    if setor == "diagnostico":
        filtro_setor = "AND osm.osm_atend IN ('ASS','EME','CRG','TAM')"
    elif setor == "ocupacional":
        filtro_setor = "AND osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')"
    else:
        filtro_setor = ""

    recepcao_cod = "".join(ch for ch in recepcao if ch.isalnum())[:6]
    if recepcao_cod:
        filtro_setor += f" AND RTRIM(osm.osm_str) = '{recepcao_cod}'"

    rows = query(f"""
        SELECT
            RTRIM(smm.SMM_USR_LOGIN_LANC)                             AS login,
            RTRIM(ISNULL(u.USR_NOME, smm.SMM_USR_LOGIN_LANC))         AS medico,
            COUNT(*)                                                   AS total_exames,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)         AS total_os,
            COUNT(DISTINCT osm.osm_pac)                                AS pacientes,
            SUM({vliq})                                                AS faturamento,
            SUM({vliq})/NULLIF(COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num),0) AS ticket_por_os
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        LEFT JOIN usr u ON RTRIM(u.USR_LOGIN) = RTRIM(smm.SMM_USR_LOGIN_LANC)
        WHERE smm.SMM_ESP IN ({esp_sql})
          AND smm.SMM_SFAT IN ('A','F','P')
          AND osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_USR_LOGIN_LANC IS NOT NULL
          {filtro_setor}
        GROUP BY RTRIM(smm.SMM_USR_LOGIN_LANC), RTRIM(ISNULL(u.USR_NOME, smm.SMM_USR_LOGIN_LANC))
        ORDER BY faturamento DESC
    """)
    for r in rows:
        r["faturamento"] = float(r["faturamento"] or 0)
        r["ticket_por_os"] = float(r["ticket_por_os"] or 0)
    return rows


# ── AGENDAMENTOS (já existe, mas adicionando financeiro) ─────────────────────

@app.get("/api/modulo/agendamentos/medico-detalhe")
def agendamentos_medico_detalhe(psv_cod: int, periodo: str = "30d"):
    """Detalhamento por convênio — busca OSs dos pacientes agendados com este médico."""
    inicio, fim = periodo_datas(periodo)
    vliq = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"
    rows = query(f"""
        SELECT TOP 10
            RTRIM(cnv.cnv_nome)                                             AS convenio,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)              AS atendimentos,
            COUNT(DISTINCT osm.osm_pac)                                     AS pacientes,
            SUM({vliq})                                                     AS producao
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        -- Pacientes que tinham agendamento com este médico no período
        WHERE osm.osm_pac IN (
            SELECT DISTINCT agm.agm_pac FROM agm
            WHERE agm.agm_med = {psv_cod}
              AND agm.agm_hini BETWEEN '{inicio}' AND '{fim} 23:59:59'
              AND agm.agm_pac > 0
        )
        AND CAST(osm.osm_dthr AS DATE) IN (
            SELECT DISTINCT CAST(agm.agm_hini AS DATE) FROM agm
            WHERE agm.agm_med = {psv_cod}
              AND agm.agm_hini BETWEEN '{inicio}' AND '{fim} 23:59:59'
        )
        AND osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
        AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY RTRIM(cnv.cnv_nome)
        ORDER BY producao DESC
    """)
    return rows



@app.get("/api/modulo/agendamentos/producao-hoje-convenio")
def agendamentos_producao_hoje_convenio():
    """Produção dos pacientes agendados hoje por convênio."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    vliq = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"
    rows = query(f"""
        SELECT
            RTRIM(cnv.cnv_nome)                                             AS convenio,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)              AS atendimentos,
            COUNT(DISTINCT osm.osm_pac)                                     AS pacientes,
            SUM({vliq})                                                     AS producao
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
          AND smm.SMM_SFAT IN ('A','F','P')
          AND osm.osm_pac IN (
              SELECT DISTINCT agm.agm_pac FROM agm
              WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
                AND agm.agm_pac > 0
                AND agm.agm_stat NOT IN ('C','B')
          )
        GROUP BY RTRIM(cnv.cnv_nome)
        ORDER BY producao DESC
    """)
    return rows

@app.get("/api/modulo/agendamentos/resumo-hoje")
def agendamentos_resumo_hoje():
    """Resumo do dia de agendamentos."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    
    stats = query(f"""
        SELECT
            SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B')
                     THEN 1 ELSE 0 END)                                     AS marcacoes,
            SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B')
                      AND (agm.agm_stat='E' OR agm.AGM_OSM_SERIE IS NOT NULL
                           OR om.osm_pac IS NOT NULL)
                     THEN 1 ELSE 0 END)                                     AS atendidos,
            SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B','E')
                      AND agm.AGM_OSM_SERIE IS NULL AND om.osm_pac IS NULL
                     THEN 1 ELSE 0 END)                                     AS faltantes,
            SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat='C'
                     THEN 1 ELSE 0 END)                                     AS cancelados,
            -- Total de horários (vagas disponíveis + marcações) - exclui cancelados e bloqueios,
            -- mesmo filtro usado em "marcacoes" acima (bloqueio não é agendamento real)
            ISNULL((SELECT COUNT(*) FROM EX_HORARIOS WHERE HOR_DATA = '{hoje}'), 0)
            + SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B') THEN 1 ELSE 0 END) AS total_horarios,
            ISNULL((SELECT COUNT(*) FROM EX_HORARIOS WHERE HOR_DATA = '{hoje}'), 0) AS vagas_disp,
            COUNT(DISTINCT agm.agm_med)                                     AS medicos_agenda,
            -- Ticket médio dos últimos 30 dias (base para previsão dos que ainda não vieram)
            (SELECT SUM(smm2.SMM_VLR - ISNULL(smm2.SMM_VLR_DESCONTO,0)
                              - ISNULL(smm2.SMM_VLR_COPARTIC,0) + ISNULL(smm2.SMM_AJUSTE_VLR,0))
                        / NULLIF(COUNT(DISTINCT osm2.osm_serie*1000000+osm2.osm_num),0)
             FROM osm osm2
             JOIN smm smm2 ON smm2.SMM_OSM_SERIE=osm2.osm_serie AND smm2.SMM_OSM=osm2.osm_num
             WHERE osm2.osm_dthr BETWEEN DATEADD(day,-30,'{hoje}') AND DATEADD(day,-1,'{hoje}')
               AND smm2.SMM_SFAT IN ('A','F','P')
            )                                                                AS ticket_medio_30d,
            -- Produção dos pacientes agendados que JÁ foram atendidos hoje
            (SELECT SUM(smm3.SMM_VLR - ISNULL(smm3.SMM_VLR_DESCONTO,0)
                              - ISNULL(smm3.SMM_VLR_COPARTIC,0) + ISNULL(smm3.SMM_AJUSTE_VLR,0))
             FROM osm osm3
             JOIN smm smm3 ON smm3.SMM_OSM_SERIE=osm3.osm_serie AND smm3.SMM_OSM=osm3.osm_num
             WHERE CAST(osm3.osm_dthr AS DATE) = '{hoje}'
               AND smm3.SMM_SFAT IN ('A','F','P')
               -- Apenas pacientes que tinham agendamento hoje
               AND EXISTS (
                   SELECT 1 FROM agm agm2
                   WHERE CAST(agm2.agm_hini AS DATE) = '{hoje}'
                     AND agm2.agm_pac = osm3.osm_pac
                     AND agm2.agm_pac > 0
                     AND agm2.agm_stat NOT IN ('C','B')
                     -- OS deve ser próxima do horário agendado
                     AND DATEDIFF(minute, agm2.agm_hini, osm3.osm_dthr) BETWEEN -30 AND 180
               )
            )                                                                AS producao_hoje
        FROM agm
        LEFT JOIN (
            SELECT DISTINCT osm_pac, osm_dthr, CAST(osm_dthr AS DATE) AS osm_data
            FROM osm WHERE CAST(osm_dthr AS DATE) = '{hoje}'
        ) om ON om.osm_pac = agm.agm_pac
             AND om.osm_data = CAST(agm.agm_hini AS DATE)
             -- OS deve ser próxima do horário agendado (±3 horas)
             AND DATEDIFF(minute, agm.agm_hini, om.osm_dthr) BETWEEN -30 AND 180
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
    """)
    
    # Por hora — distribuição de agendamentos no dia
    por_hora = query(f"""
        SELECT
            DATEPART(hour, agm.agm_hini)                                    AS hora,
            SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B')
                     THEN 1 ELSE 0 END)                                     AS marcacoes,
            SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B')
                      AND (agm.agm_stat='E' OR agm.AGM_OSM_SERIE IS NOT NULL
                           OR om.osm_pac IS NOT NULL)
                     THEN 1 ELSE 0 END)                                     AS atendidos
        FROM agm
        LEFT JOIN (
            SELECT DISTINCT osm_pac, osm_dthr, CAST(osm_dthr AS DATE) AS osm_data
            FROM osm WHERE CAST(osm_dthr AS DATE) = '{hoje}'
        ) om ON om.osm_pac = agm.agm_pac
             AND om.osm_data = CAST(agm.agm_hini AS DATE)
             AND DATEDIFF(minute, agm.agm_hini, om.osm_dthr) BETWEEN -30 AND 180
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
          AND agm.agm_pac > 0
        GROUP BY DATEPART(hour, agm.agm_hini)
        ORDER BY hora
    """)
    
    # Médicos com agenda hoje
    # Busca por turno separadamente — médico aparece nos dois se atender manhã e tarde
    def busca_medicos_turno(turno_hora_inicio, turno_hora_fim):
        return query(f"""
            SELECT TOP 20
                RTRIM(psv.psv_apel)                                         AS medico,
                MIN(CONVERT(VARCHAR(5), agm.agm_hini, 108))                AS hora_inicio,
                MAX(CONVERT(VARCHAR(5), agm.agm_hini, 108))                AS hora_fim,
                SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B')
                         THEN 1 ELSE 0 END)                                 AS marcacoes,
                SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B')
                          AND (agm.agm_stat='E' OR agm.AGM_OSM_SERIE IS NOT NULL
                               OR om.osm_pac IS NOT NULL)
                         THEN 1 ELSE 0 END)                                 AS atendidos,
                SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B','E')
                          AND agm.AGM_OSM_SERIE IS NULL AND om.osm_pac IS NULL
                         THEN 1 ELSE 0 END)                                 AS faltantes,
                SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat='C'
                         THEN 1 ELSE 0 END)                                 AS cancelados
            FROM agm
            JOIN psv ON psv.psv_cod = agm.agm_med
            LEFT JOIN (
                SELECT DISTINCT osm_pac, osm_dthr, CAST(osm_dthr AS DATE) AS osm_data
                FROM osm WHERE CAST(osm_dthr AS DATE) = '{hoje}'
            ) om ON om.osm_pac = agm.agm_pac
                 AND om.osm_data = CAST(agm.agm_hini AS DATE)
                 AND DATEDIFF(minute, agm.agm_hini, om.osm_dthr) BETWEEN -30 AND 180
            WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
              AND agm.agm_pac > 0
              AND DATEPART(hour, agm.agm_hini) >= {turno_hora_inicio}
              AND DATEPART(hour, agm.agm_hini) < {turno_hora_fim}
            GROUP BY RTRIM(psv.psv_apel)
            HAVING SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B') THEN 1 ELSE 0 END) > 0
            ORDER BY MIN(agm.agm_hini)
        """)

    medicos_manha = busca_medicos_turno(0, 12)
    medicos_tarde = busca_medicos_turno(12, 24)

    # Lista completa (union sem duplicar dados — só para compatibilidade)
    medicos_hoje = []
    nomes_vistos = set()
    for m in medicos_manha:
        m['turno'] = 'manha'
        medicos_hoje.append(m)
        nomes_vistos.add(m['medico'])
    for m in medicos_tarde:
        m['turno'] = 'tarde'
        medicos_hoje.append(m)
    
    return {
        "stats": stats[0] if stats else {},
        "por_hora": por_hora,
        "medicos_hoje": medicos_hoje,
        "medicos_manha": medicos_manha,
        "medicos_tarde": medicos_tarde,
    }

def agendamentos_stats(inicio: str, fim: str):
    rows = query(f"""
        SELECT
            -- Total = slots com paciente marcado (não considera slots vazios)
            SUM(CASE WHEN agm.agm_pac IS NOT NULL AND agm.agm_pac > 0
                     THEN 1 ELSE 0 END)                                            AS total,
            -- Marcações válidas = com paciente, não cancelado, não bloqueado
            SUM(CASE WHEN agm.agm_pac IS NOT NULL AND agm.agm_pac > 0
                      AND agm.agm_stat NOT IN ('C','B')
                     THEN 1 ELSE 0 END)                                            AS marcacoes,
            -- Compareceu: tem OS no dia pelo mesmo médico
            SUM(CASE WHEN agm.agm_pac IS NOT NULL AND agm.agm_pac > 0
                      AND agm.agm_stat NOT IN ('C','B')
                      AND (agm.agm_stat='E'
                           OR agm.AGM_OSM_SERIE IS NOT NULL
                           OR osm_match.osm_pac IS NOT NULL)
                     THEN 1 ELSE 0 END)                                            AS executados,
            -- Cancelados
            SUM(CASE WHEN agm.agm_pac IS NOT NULL AND agm.agm_pac > 0
                      AND agm.agm_stat='C'
                     THEN 1 ELSE 0 END)                                            AS cancelados,
            -- Absenteísmo: marcado, não cancelado, não compareceu
            SUM(CASE WHEN agm.agm_pac IS NOT NULL AND agm.agm_pac > 0
                      AND agm.agm_stat NOT IN ('C','B')
                      AND agm.agm_stat <> 'E'
                      AND agm.AGM_OSM_SERIE IS NULL
                      AND osm_match.osm_pac IS NULL
                     THEN 1 ELSE 0 END)                                            AS abertos,
            SUM(CASE WHEN agm.agm_stat='B' THEN 1 ELSE 0 END)                    AS bloqueados,
            SUM(CASE WHEN agm.AGM_OSM_SERIE IS NOT NULL THEN 1 ELSE 0 END)       AS com_os_vinculada,
            COUNT(DISTINCT CASE WHEN agm.agm_pac > 0
                THEN agm.agm_pac END)                                              AS pacientes,
            COUNT(DISTINCT agm.agm_med)                                            AS medicos,
            -- Taxa de comparecimento = compareceu / marcações válidas
            CAST(100.0 * SUM(CASE WHEN agm.agm_pac IS NOT NULL AND agm.agm_pac > 0
                                       AND agm.agm_stat NOT IN ('C','B')
                                       AND (agm.agm_stat='E'
                                            OR agm.AGM_OSM_SERIE IS NOT NULL
                                            OR osm_match.osm_pac IS NOT NULL)
                                  THEN 1 ELSE 0 END) /
                NULLIF(SUM(CASE WHEN agm.agm_pac IS NOT NULL AND agm.agm_pac > 0
                                 AND agm.agm_stat NOT IN ('C','B')
                            THEN 1 ELSE 0 END),0)
            AS DECIMAL(5,1))                                                       AS taxa_exec,
            ISNULL(SUM(agm.agm_valor),0)                                           AS valor_total
        FROM agm
        LEFT JOIN (
            SELECT DISTINCT osm.osm_pac, CAST(osm.osm_dthr AS DATE) AS osm_data
            FROM osm
            WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
        ) osm_match ON osm_match.osm_pac  = agm.agm_pac
                   AND osm_match.osm_data = CAST(agm.agm_hini AS DATE)
        WHERE agm.agm_hini BETWEEN '{inicio}' AND '{fim} 23:59:59'
    """)
    return rows[0] if rows else {}

@app.get("/api/modulo/agendamentos/resumo")
def agendamentos_modulo_resumo(periodo: str = "30d"):
    inicio, fim = periodo_datas(periodo)
    stats = [agendamentos_stats(inicio, fim)]
    ant_ini, ant_fim = periodo_anterior(inicio, fim)
    stats_ant = agendamentos_stats(ant_ini, ant_fim)
    variacoes = {
        "marcacoes":  var_pct(stats[0].get("marcacoes"), stats_ant.get("marcacoes")),
        "executados": var_pct(stats[0].get("executados"), stats_ant.get("executados")),
        "cancelados": var_pct(stats[0].get("cancelados"), stats_ant.get("cancelados")),
    }
    # Por médico top 10
    top_med = query(f"""
        SELECT TOP 15
               RTRIM(psv.psv_apel)                                              AS medico,
               RTRIM(psv.psv_nome)                                              AS nome_completo,
               agm_grp.psv_cod                                                  AS psv_cod,
               agm_grp.marcacoes,
               agm_grp.atendidos,
               agm_grp.faltantes,
               agm_grp.cancelados,
               agm_grp.taxa_exec,
               ISNULL(eh_grp.vagas_disp, 0)                                     AS vagas_disp,
               -- ENCAIXE: pacientes atendidos pelo médico no período que NÃO tinham agendamento
               ISNULL(enc.encaixe, 0)                                            AS encaixe
        FROM (
            SELECT
               agm.agm_med                                                       AS psv_cod,
               SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B')
                        THEN 1 ELSE 0 END)                                      AS marcacoes,
               SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B')
                         AND (agm.agm_stat='E' OR agm.AGM_OSM_SERIE IS NOT NULL
                              OR om.osm_pac IS NOT NULL)
                        THEN 1 ELSE 0 END)                                      AS atendidos,
               SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B','E')
                         AND agm.AGM_OSM_SERIE IS NULL AND om.osm_pac IS NULL
                        THEN 1 ELSE 0 END)                                      AS faltantes,
               SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat='C'
                        THEN 1 ELSE 0 END)                                      AS cancelados,
               CAST(100.0 * SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B')
                                      AND (agm.agm_stat='E' OR agm.AGM_OSM_SERIE IS NOT NULL
                                           OR om.osm_pac IS NOT NULL)
                                     THEN 1 ELSE 0 END) /
                    NULLIF(SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B')
                               THEN 1 ELSE 0 END),0)
               AS DECIMAL(5,1))                                                 AS taxa_exec
            FROM agm
            LEFT JOIN (
                SELECT DISTINCT osm_pac, osm_dthr, CAST(osm_dthr AS DATE) AS osm_data
                FROM osm WHERE osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
            ) om ON om.osm_pac=agm.agm_pac
                 AND om.osm_data=CAST(agm.agm_hini AS DATE)
                 AND DATEDIFF(minute, agm.agm_hini, om.osm_dthr) BETWEEN -30 AND 180
            WHERE agm.agm_hini BETWEEN '{inicio}' AND '{fim} 23:59:59'
            GROUP BY agm.agm_med
        ) agm_grp
        JOIN psv ON psv.psv_cod = agm_grp.psv_cod
        LEFT JOIN (
            SELECT HOR_MED, COUNT(*) AS vagas_disp
            FROM EX_HORARIOS
            WHERE HOR_DATA BETWEEN '{inicio}' AND '{fim}'
            GROUP BY HOR_MED
        ) eh_grp ON eh_grp.HOR_MED = agm_grp.psv_cod
        -- Subquery de encaixe: OSs do médico no período SEM agendamento correspondente
        LEFT JOIN (
            SELECT
                o.osm_mreq                                                      AS psv_cod,
                COUNT(DISTINCT o.osm_serie * 1000000 + o.osm_num)              AS encaixe
            FROM osm o
            WHERE o.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
              AND o.osm_mreq IS NOT NULL
              AND o.osm_mreq > 0
              -- Atendimento SEM agendamento: não existe AGM para este paciente
              -- no mesmo dia e com o mesmo médico dentro da janela de tempo
              AND NOT EXISTS (
                  SELECT 1
                  FROM agm a2
                  WHERE a2.agm_pac = o.osm_pac
                    AND a2.agm_med = o.osm_mreq
                    AND CAST(a2.agm_hini AS DATE) = CAST(o.osm_dthr AS DATE)
                    AND a2.agm_stat NOT IN ('C','B')
                    AND DATEDIFF(minute, a2.agm_hini, o.osm_dthr) BETWEEN -30 AND 180
              )
            GROUP BY o.osm_mreq
        ) enc ON enc.psv_cod = agm_grp.psv_cod
        ORDER BY agm_grp.marcacoes DESC
    """)

    # Por dia
    por_dia = query(f"""
        SELECT CAST(agm.agm_hini AS DATE) AS data,
               COUNT(*) AS total,
               SUM(CASE WHEN agm.agm_stat='E' OR agm.AGM_OSM_SERIE IS NOT NULL
                         OR od.osm_pac IS NOT NULL
                        THEN 1 ELSE 0 END) AS executados,
               SUM(CASE WHEN agm.agm_stat='C' THEN 1 ELSE 0 END) AS cancelados,
               SUM(CASE WHEN agm.agm_stat NOT IN ('C','B') AND agm.AGM_OSM_SERIE IS NULL
                         AND od.osm_pac IS NULL
                        THEN 1 ELSE 0 END) AS nao_compareceu
        FROM agm
        LEFT JOIN (
            SELECT DISTINCT osm_pac, osm_dthr, CAST(osm_dthr AS DATE) AS osm_data
            FROM osm WHERE osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
        ) od ON od.osm_pac=agm.agm_pac
             AND od.osm_data=CAST(agm.agm_hini AS DATE)
             AND DATEDIFF(minute, agm.agm_hini, od.osm_dthr) BETWEEN -30 AND 180
        WHERE agm.agm_hini BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND agm.agm_pac IS NOT NULL AND agm.agm_pac > 0
        GROUP BY CAST(agm.agm_hini AS DATE) ORDER BY data
    """)
    for r in por_dia:
        if hasattr(r.get("data"),"strftime"): r["data"] = r["data"].strftime("%Y-%m-%d")
    return {
        "stats": stats[0] if stats else {},
        "variacoes": variacoes,
        "top_medicos": top_med,
        "por_dia": por_dia,
    }








# ══════════════════════════════════════════════════════════════════════════════
# TAXA DE RECOLETA — LABORATÓRIO
# Recoleta = itens com SMM_CANC_MOT_TIPO='MCO' (motivo cancelamento = nova amostra)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/laboratorio/recoleta")
def laboratorio_recoleta(periodo: str = "30d", setor: str = ""):
    inicio, fim = periodo_datas(periodo)

    if setor == "diagnostico":
        filtro_setor = "AND osm.osm_atend IN ('ASS','EME','CRG','TAM')"
    elif setor == "ocupacional":
        filtro_setor = "AND osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')"
    else:
        filtro_setor = ""

    # Total de itens de exame realizados no período
    total = query(f"""
        SELECT COUNT(*) AS total_exames,
               COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS total_os,
               COUNT(DISTINCT osm.osm_pac) AS total_pacientes
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP='LAB'
          AND smm.SMM_SFAT IN ('A','F','P','C')
          {filtro_setor}
    """)

    # Total de recoletas
    recoletas = query(f"""
        SELECT COUNT(*) AS total_recoletas,
               COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS os_com_recoleta,
               COUNT(DISTINCT osm.osm_pac) AS pacientes_recoleta
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP='LAB'
          AND smm.SMM_CANC_MOT_TIPO='MCO'
          {filtro_setor}
    """)

    # Recoleta por motivo (cod 1,2,3)
    por_motivo = query(f"""
        SELECT
            LTRIM(RTRIM(smm.SMM_CANC_MOT_COD)) AS motivo_cod,
            CASE LTRIM(RTRIM(smm.SMM_CANC_MOT_COD))
                WHEN '1' THEN 'Amostra Insuficiente'
                WHEN '2' THEN 'Amostra Hemolisada'
                WHEN '3' THEN 'Erro de Coleta'
                ELSE 'Outro (cod '+ LTRIM(RTRIM(smm.SMM_CANC_MOT_COD)) +')'
            END AS motivo_nome,
            COUNT(*) AS qtd
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP='LAB'
          AND smm.SMM_CANC_MOT_TIPO='MCO'
          {filtro_setor}
        GROUP BY LTRIM(RTRIM(smm.SMM_CANC_MOT_COD))
        ORDER BY qtd DESC
    """)

    # Recoleta por exame (quais exames são mais recoletados)
    por_exame = query(f"""
        SELECT TOP 10
            RTRIM(smm.SMM_COD) AS exame_cod,
            COUNT(*) AS qtd_recoleta
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP='LAB'
          AND smm.SMM_CANC_MOT_TIPO='MCO'
          {filtro_setor}
        GROUP BY RTRIM(smm.SMM_COD)
        ORDER BY qtd_recoleta DESC
    """)

    # Recoleta por dia (tendência)
    por_dia = query(f"""
        SELECT
            CAST(osm.osm_dthr AS DATE) AS data,
            COUNT(*) AS recoletas,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS os_afetadas
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP='LAB'
          AND smm.SMM_CANC_MOT_TIPO='MCO'
          {filtro_setor}
        GROUP BY CAST(osm.osm_dthr AS DATE)
        ORDER BY data
    """)
    for r in por_dia:
        if hasattr(r.get("data"),"strftime"): r["data"] = r["data"].strftime("%Y-%m-%d")

    # Recoleta por médico requisitante
    por_medico = query(f"""
        SELECT TOP 10
            ISNULL(RTRIM(psv.psv_apel), RTRIM(psv.psv_nome)) AS medico,
            COUNT(*) AS recoletas,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS os_afetadas
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        LEFT JOIN psv ON psv.psv_cod=osm.osm_mreq
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_ESP='LAB'
          AND smm.SMM_CANC_MOT_TIPO='MCO'
          {filtro_setor}
        GROUP BY psv.psv_apel, psv.psv_nome
        ORDER BY recoletas DESC
    """)

    t = total[0] if total else {}
    r = recoletas[0] if recoletas else {}
    total_ex  = t.get("total_exames") or 0
    total_rec = r.get("total_recoletas") or 0
    taxa_pct  = round((total_rec / total_ex * 100), 2) if total_ex > 0 else 0

    return {
        "total_exames":     total_ex,
        "total_os":         t.get("total_os") or 0,
        "total_recoletas":  total_rec,
        "os_com_recoleta":  r.get("os_com_recoleta") or 0,
        "pacientes_recoleta": r.get("pacientes_recoleta") or 0,
        "taxa_recoleta_pct": taxa_pct,
        "por_motivo":       por_motivo,
        "por_exame":        por_exame,
        "por_dia":          por_dia,
        "por_medico":       por_medico,
    }









# ── WHATSAPP ──────────────────────────────────────────────────────────────────
import json as _json
_WPP_CONFIG_FILE = "whatsapp_config.json"

def _load_wpp_config():
    try:
        with open(_WPP_CONFIG_FILE) as f: return _json.load(f)
    except: return {}

def _save_wpp_config(cfg):
    with open(_WPP_CONFIG_FILE, "w") as f: _json.dump(cfg, f, indent=2)


# ── METAS POR MÓDULO ──────────────────────────────────────────────────────────
# Guardadas em arquivo local (não no banco SMART, que é do sistema Pixeon) —
# mesmo padrão do whatsapp_config.json.
_METAS_CONFIG_FILE = "metas_config.json"

def _load_metas():
    try:
        with open(_METAS_CONFIG_FILE, encoding="utf-8") as f: return _json.load(f)
    except: return {}

def _save_metas(cfg):
    with open(_METAS_CONFIG_FILE, "w", encoding="utf-8") as f: _json.dump(cfg, f, indent=2, ensure_ascii=False)

@app.get("/api/metas")
def metas_listar():
    """Retorna as metas configuradas por módulo: { modulo: { meta_mensal, meta_diaria } }"""
    return _load_metas()

@app.put("/api/metas/{modulo}")
def metas_salvar(modulo: str, payload: dict):
    metas = _load_metas()
    atual = metas.get(modulo, {})
    meta_mensal = payload.get("meta_mensal", atual.get("meta_mensal"))
    meta_diaria = payload.get("meta_diaria", atual.get("meta_diaria"))
    meta_sabado = payload.get("meta_sabado", atual.get("meta_sabado"))
    metas[modulo] = {
        "meta_mensal": float(meta_mensal) if meta_mensal not in (None, "") else None,
        "meta_diaria": float(meta_diaria) if meta_diaria not in (None, "") else None,
        "meta_sabado": float(meta_sabado) if meta_sabado not in (None, "") else None,
    }
    _save_metas(metas)
    return metas[modulo]

@app.delete("/api/metas/{modulo}")
def metas_remover(modulo: str):
    metas = _load_metas()
    metas.pop(modulo, None)
    _save_metas(metas)
    return {"ok": True}

@app.get("/api/whatsapp/config")
def wpp_get_config():
    cfg = _load_wpp_config()
    return {
        "provider":          cfg.get("provider",         "wppconnect"),
        # WPPConnect (local)
        "wppconnect_url":    cfg.get("wppconnect_url",   "http://localhost:21465"),
        "wppconnect_session":cfg.get("wppconnect_session","myinstance"),
        "wppconnect_token":  "***" if cfg.get("wppconnect_token") else "",
        # Z-API
        "zapi_instance":     cfg.get("zapi_instance",    ""),
        "zapi_token":        "***" if cfg.get("zapi_token") else "",
        "zapi_client_token": "***" if cfg.get("zapi_client_token") else "",
        # Evolution API
        "evolution_url":     cfg.get("evolution_url",    "http://localhost:8080"),
        "evolution_inst":    cfg.get("evolution_inst",   "censo"),
        "evolution_key":     "***" if cfg.get("evolution_key") else "",
        # Comum
        "numeros_destino":   cfg.get("numeros_destino",  ""),
        "horario_manha":     cfg.get("horario_manha",    "08:00"),
        "horario_tarde":     cfg.get("horario_tarde",    "17:00"),
        "ativo":             cfg.get("ativo",             False),
        "disponivel":        _WPP_AVAILABLE,
    }

@app.post("/api/whatsapp/config")
def wpp_save_config(
    provider: str="wppconnect",
    # WPPConnect
    wppconnect_url: str="http://localhost:21465",
    wppconnect_session: str="myinstance",
    wppconnect_token: str="",
    # Z-API
    zapi_instance: str="", zapi_token: str="", zapi_client_token: str="",
    # Evolution
    evolution_url: str="", evolution_key: str="", evolution_inst: str="censo",
    # Comum
    numero_destino: str="",
    horario_manha: str="08:00", horario_tarde: str="17:00",
    ativo: bool=True,
):
    """Salva configuração do WhatsApp."""
    cfg = _load_wpp_config()
    cfg["provider"] = provider
    # WPPConnect
    if wppconnect_url:     cfg["wppconnect_url"]     = wppconnect_url
    if wppconnect_session: cfg["wppconnect_session"]  = wppconnect_session
    if wppconnect_token and wppconnect_token != "***": cfg["wppconnect_token"] = wppconnect_token
    # Z-API
    if zapi_instance:    cfg["zapi_instance"]    = zapi_instance
    if zapi_token and zapi_token != "***":       cfg["zapi_token"]        = zapi_token
    if zapi_client_token and zapi_client_token != "***": cfg["zapi_client_token"] = zapi_client_token
    # Evolution
    if evolution_url:    cfg["evolution_url"]    = evolution_url
    if evolution_key and evolution_key != "***": cfg["evolution_key"]    = evolution_key
    if evolution_inst:   cfg["evolution_inst"]   = evolution_inst
    # Comum
    if numero_destino:   cfg["numeros_destino"]  = numero_destino
    cfg["horario_manha"] = horario_manha
    cfg["horario_tarde"] = horario_tarde
    cfg["ativo"]         = ativo
    _save_wpp_config(cfg)

    # Atualiza env vars
    import os
    os.environ["WPP_PROVIDER"]          = provider
    if cfg.get("wppconnect_url"):     os.environ["WPPCONNECT_URL"]      = cfg["wppconnect_url"]
    if cfg.get("wppconnect_session"): os.environ["WPPCONNECT_SESSION"]  = cfg["wppconnect_session"]
    if cfg.get("wppconnect_token"):   os.environ["WPPCONNECT_TOKEN"]    = cfg["wppconnect_token"]
    if cfg.get("numeros_destino"):    os.environ["WHATSAPP_DEST"]       = cfg["numeros_destino"]

    return {"ok": True, "config": wpp_get_config()}

@app.get("/api/whatsapp/grupos")
def wpp_listar_grupos():
    """Lista os grupos de WhatsApp que a sessão conectada (WPPConnect) já
    participa — usado pra achar o ID do grupo sem precisar caçar manualmente.
    Só funciona com provider=wppconnect e sessão já conectada (QR lido)."""
    cfg = _load_wpp_config()
    if cfg.get("provider", "wppconnect") != "wppconnect":
        return {"ok": False, "erro": "Listagem de grupos só é suportada com o provider WPPConnect."}
    session = cfg.get("wppconnect_session", "myinstance")
    token   = cfg.get("wppconnect_token", "")
    base    = cfg.get("wppconnect_url", "http://localhost:21465")
    try:
        resp = httpx.get(
            f"{base}/api/{session}/all-groups",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        grupos = [
            {"id": g.get("id", {}).get("_serialized") or g.get("id"), "nome": g.get("name") or g.get("formattedTitle") or ""}
            for g in (data.get("response") or [])
        ]
        grupos = [g for g in grupos if g["id"]]
        return {"ok": True, "total": len(grupos), "grupos": grupos}
    except Exception as e:
        return {"ok": False, "erro": str(e)[:250]}

@app.post("/api/whatsapp/send-test")
def wpp_send_test(turno: str = "manha"):
    if not _WPP_AVAILABLE:
        return {"ok": False, "erro": "whatsapp_sender.py não encontrado."}
    cfg = _load_wpp_config()
    try:
        from whatsapp_sender import enviar_resumo as _wpp_enviar
        return _wpp_enviar(query_func=query, turno=turno, numero=cfg.get("numeros_destino",""))
    except Exception as e:
        return {"ok": False, "erro": str(e)}

@app.get("/api/whatsapp/preview")
def wpp_preview(turno: str = "manha"):
    try:
        from whatsapp_sender import (buscar_dados_manha, montar_manha,
                                      buscar_dados_fechamento, montar_fechamento,
                                      buscar_dados_amanha, montar_previa_amanha)
        if turno == "manha":
            dados = buscar_dados_manha(query)
            msg   = montar_manha(dados)
            return {"mensagem": msg, "tamanho": len(msg)}
        else:
            dados_f = buscar_dados_fechamento(query)
            msg_f   = montar_fechamento(dados_f)
            dados_a = buscar_dados_amanha(query)
            msg_a   = montar_previa_amanha(dados_a)
            return {
                "fechamento": {"mensagem": msg_f, "tamanho": len(msg_f)},
                "previa_amanha": {"mensagem": msg_a, "tamanho": len(msg_a)},
            }
    except Exception as e:
        return {"erro": str(e)}

# Adicionar no main.py logo após o endpoint /api/whatsapp/preview
# (depois da linha que começa com: "    except Exception as e:")
# (depois do bloco def wpp_preview)

@app.get("/api/debug/fle-colunas")
def debug_fle_colunas():
    hoje = datetime.now().strftime("%Y-%m-%d")
    cols = query("""
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'fle'
        ORDER BY ORDINAL_POSITION
    """)
    sample = query(f"""
        SELECT TOP 2 * FROM fle
        WHERE CAST(FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
        ORDER BY FLE_DTHR_CHEGADA DESC
    """)
    for r in sample:
        for k, v in r.items():
            if hasattr(v, 'strftime'): r[k] = v.strftime('%Y-%m-%d %H:%M:%S')
    loc_cols = query("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'loc' ORDER BY ORDINAL_POSITION
    """)
    loc_sample = query("SELECT TOP 5 * FROM loc")
    return {
        "fle_colunas": cols,
        "fle_amostra": sample,
        "loc_colunas": loc_cols,
        "loc_amostra": loc_sample,
    }

@app.get("/api/whatsapp/status")
def wpp_status():
    """
    Health check da sessão WhatsApp.
    Verifica se o provider está online e com o celular conectado.
    Retorna:
      online    : provider acessível
      conectado : sessão ativa (celular pareado)
      detalhe   : mensagem explicativa
    """
    if not _WPP_AVAILABLE:
        return {
            "online":    False,
            "conectado": False,
            "provider":  "desconhecido",
            "status":    "indisponivel",
            "detalhe":   "whatsapp_sender.py nao encontrado",
            "ts":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    try:
        from whatsapp_sender import checar_status_wpp
        return checar_status_wpp()
    except Exception as e:
        return {
            "online":    False,
            "conectado": False,
            "provider":  "erro",
            "status":    "erro",
            "detalhe":   str(e)[:200],
            "ts":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


@app.get("/api/estoque/sintetico")
def estoque_sintetico(data_inicio: str = "2024-01-01", data_fim: str = ""):
    """Relatório sintético de saldos por grupo — como o PDF Sintético."""
    from datetime import datetime
    fim = data_fim if data_fim else datetime.now().strftime("%Y-%m-%d")
    inicio = data_inicio

    rows = query(f"""
        SELECT
            RTRIM(gmm.GMM_COD)                                              AS grupo_cod,
            RTRIM(gmm.GMM_NOME)                                             AS grupo_nome,
            SUM(CASE WHEN mma_e.valor IS NULL THEN 0 ELSE mma_e.valor END)  AS sld_mes_ant,
            ISNULL(SUM(CASE WHEN mma.MMA_TIPO_ES='E' THEN mma.MMA_VALOR ELSE 0 END),0) AS entradas,
            ISNULL(SUM(CASE WHEN mma.MMA_TIPO_ES='S' THEN mma.MMA_VALOR ELSE 0 END),0) AS saidas,
            SUM(mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM)                     AS saldo_atual,
            COUNT(DISTINCT mat.MAT_COD)                                     AS total_itens
        FROM GMM gmm
        LEFT JOIN MAT mat ON mat.MAT_GMM_COD = gmm.GMM_COD AND mat.MAT_DEL_LOGICA <> 'S'
        LEFT JOIN MMA mma ON mma.MMA_MAT_COD = mat.MAT_COD
            AND mma.MMA_DATA_MOV BETWEEN '{inicio}' AND '{fim} 23:59:59'
            AND mma.MMA_IND_CANCELADA <> 'S'
        LEFT JOIN (
            SELECT MMA_MAT_COD, SUM(CASE WHEN MMA_TIPO_ES='E' THEN MMA_VALOR ELSE -MMA_VALOR END) AS valor
            FROM MMA
            WHERE MMA_DATA_MOV < '{inicio}' AND MMA_IND_CANCELADA <> 'S'
            GROUP BY MMA_MAT_COD
        ) mma_e ON mma_e.MMA_MAT_COD = mat.MAT_COD
        WHERE gmm.GMM_COD <> '0'
        GROUP BY RTRIM(gmm.GMM_COD), RTRIM(gmm.GMM_NOME)
        HAVING COUNT(DISTINCT mat.MAT_COD) > 0
        ORDER BY grupo_nome
    """)
    
    total_entradas = sum(r.get('entradas') or 0 for r in rows)
    total_saidas   = sum(r.get('saidas')   or 0 for r in rows)
    total_atual    = sum(r.get('saldo_atual') or 0 for r in rows)
    
    return {
        "grupos": rows,
        "totais": {
            "entradas": round(total_entradas, 2),
            "saidas":   round(total_saidas, 2),
            "saldo_atual": round(total_atual, 2),
        },
        "periodo": {"inicio": inicio, "fim": fim}
    }


@app.get("/api/estoque/analitico")
def estoque_analitico(data_inicio: str = "2024-01-01", data_fim: str = "",
                      grupo_cod: str = "", busca: str = "", limite: int = 100):
    """Relatório analítico de saldos por material — como o PDF Analítico."""
    from datetime import datetime
    fim = data_fim if data_fim else datetime.now().strftime("%Y-%m-%d")
    inicio = data_inicio

    filtro_grupo = f"AND RTRIM(mat.MAT_GMM_COD) = '{grupo_cod}'" if grupo_cod else ""
    filtro_busca = f"AND (RTRIM(mat.MAT_DESC_RESUMIDA) LIKE '%{busca}%')" if busca else ""

    rows = query(f"""
        SELECT TOP {limite}
            RTRIM(gmm.GMM_NOME)                                             AS grupo_nome,
            RTRIM(lma.LMA_NOME)                                             AS linha_nome,
            mat.MAT_COD                                                     AS cod,
            RTRIM(mat.MAT_DESC_RESUMIDA)                                    AS descricao,
            mat.MAT_VLR_PM                                                  AS pm_atual,
            mat.MAT_QT_EST_ATUAL                                            AS qtd_atual,
            mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM                          AS saldo_atual,
            ISNULL(SUM(CASE WHEN mma.MMA_TIPO_ES='E' THEN mma.MMA_QTD   ELSE 0 END),0) AS qtd_entradas,
            ISNULL(SUM(CASE WHEN mma.MMA_TIPO_ES='E' THEN mma.MMA_VALOR ELSE 0 END),0) AS val_entradas,
            ISNULL(SUM(CASE WHEN mma.MMA_TIPO_ES='S' THEN mma.MMA_QTD   ELSE 0 END),0) AS qtd_saidas,
            ISNULL(SUM(CASE WHEN mma.MMA_TIPO_ES='S' THEN mma.MMA_VALOR ELSE 0 END),0) AS val_saidas,
            CASE
                WHEN mat.MAT_QT_EST_ATUAL = 0 THEN 'ZERADO'
                WHEN mat.MAT_PT_RESSUPRIMENTO > 0
                     AND mat.MAT_QT_EST_ATUAL <= mat.MAT_PT_RESSUPRIMENTO THEN 'CRITICO'
                ELSE 'NORMAL'
            END AS status_estoque
        FROM MAT mat
        LEFT JOIN GMM gmm ON RTRIM(gmm.GMM_COD) = RTRIM(mat.MAT_GMM_COD)
        LEFT JOIN LMA lma ON RTRIM(lma.LMA_COD) = RTRIM(mat.MAT_LMA_COD)
                         AND RTRIM(lma.LMA_GMM_COD) = RTRIM(mat.MAT_GMM_COD)
        LEFT JOIN MMA mma ON mma.MMA_MAT_COD = mat.MAT_COD
            AND mma.MMA_DATA_MOV BETWEEN '{inicio}' AND '{fim} 23:59:59'
            AND mma.MMA_IND_CANCELADA <> 'S'
        WHERE mat.MAT_DEL_LOGICA <> 'S'
          {filtro_grupo}
          {filtro_busca}
        GROUP BY RTRIM(gmm.GMM_NOME), RTRIM(lma.LMA_NOME),
                 mat.MAT_COD, RTRIM(mat.MAT_DESC_RESUMIDA),
                 mat.MAT_VLR_PM, mat.MAT_QT_EST_ATUAL,
                 mat.MAT_PT_RESSUPRIMENTO
        HAVING mat.MAT_QT_EST_ATUAL > 0
            OR SUM(CASE WHEN mma.MMA_TIPO_ES IS NOT NULL THEN 1 ELSE 0 END) > 0
        ORDER BY saldo_atual DESC
    """)
    return rows


@app.get("/api/debug/estoque-grupos")
def debug_estoque_grupos():
    # MAT_GMM_COD = grupo de material, SBA = subalmoxarifado, MAT_LMA_COD = localização
    try:
        gmm = query("SELECT TOP 5 * FROM GMM")
    except:
        gmm = "nao existe"
    
    # Colunas de GMM se existir
    try:
        gmm_cols = query("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='GMM' ORDER BY ORDINAL_POSITION")
        gmm_cols = [c["COLUMN_NAME"] for c in gmm_cols]
    except:
        gmm_cols = []

    # Grupos distintos via MAT_GMM_COD
    grupos = query("""
        SELECT TOP 20 mat.MAT_GMM_COD, COUNT(*) AS qtd
        FROM MAT mat WHERE MAT_DEL_LOGICA<>'S' AND MAT_GMM_COD IS NOT NULL
        GROUP BY MAT_GMM_COD ORDER BY qtd DESC
    """)

    # LMA = localização
    try:
        lma_cols = query("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='LMA' ORDER BY ORDINAL_POSITION")
        lma = query(f"SELECT TOP 5 {', '.join([c['COLUMN_NAME'] for c in lma_cols[:4]])} FROM LMA")
    except:
        lma = "nao existe"
        lma_cols = []

    return {
        "gmm_colunas": gmm_cols,
        "gmm_amostra": gmm,
        "mat_gmm_cod_distintos": grupos,
        "lma_colunas": [c["COLUMN_NAME"] for c in lma_cols] if isinstance(lma_cols, list) else [],
        "lma_amostra": lma,
    }
@app.get("/api/debug/estoque6")
def debug_estoque6():
    result = {}
    # SMA = Saída Material Almoxarifado, MMA = Movimentação, INE = Entrada
    for tabela in ["SMA","MMA","INE","SBA","FNE","AFT_ITEM","LOT_APL","LOTE_APL"]:
        try:
            cols = query(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{tabela}' ORDER BY ORDINAL_POSITION")
            col_names = [c["COLUMN_NAME"] for c in cols[:8]]
            rows = query(f"SELECT TOP 2 {', '.join(col_names)} FROM {tabela}")
            result[tabela] = {"colunas": [c["COLUMN_NAME"] for c in cols], "amostra": rows}
        except Exception as e:
            result[tabela] = {"erro": str(e)}
    
    # LOT com dados — entradas por mês
    lot_mes = query("""
        SELECT YEAR(LOT_DATA_ENTRADA) AS ano, MONTH(LOT_DATA_ENTRADA) AS mes,
               COUNT(*) AS entradas, SUM(LOT_QUANT) AS qtd_total
        FROM LOT WHERE LOT_DATA_ENTRADA >= DATEADD(month,-6,GETDATE())
        GROUP BY YEAR(LOT_DATA_ENTRADA), MONTH(LOT_DATA_ENTRADA)
        ORDER BY ano, mes
    """)
    result["lot_entradas_recentes"] = lot_mes
    
    # Lotes vencendo nos próximos 90 dias
    vencendo = query("""
        SELECT TOP 10 mat.MAT_DESC_RESUMIDA AS material,
               lot.LOT_NUM, lot.LOT_DATA_VALIDADE, lot.LOT_SALDO,
               DATEDIFF(day, GETDATE(), lot.LOT_DATA_VALIDADE) AS dias_para_vencer
        FROM LOT lot JOIN MAT mat ON mat.MAT_COD=lot.LOT_MAT_COD
        WHERE lot.LOT_DATA_VALIDADE BETWEEN GETDATE() AND DATEADD(day,90,GETDATE())
          AND lot.LOT_SALDO > 0
        ORDER BY lot.LOT_DATA_VALIDADE
    """)
    result["lotes_vencendo"] = vencendo
    
    return result
@app.get("/api/debug/estoque5")
def debug_estoque5():
    result = {}
    for tabela in ["APL","APLIC","INV","GR_APL","ABC_FARMA"]:
        try:
            cols = query(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{tabela}' ORDER BY ORDINAL_POSITION")
            col_names = [c["COLUMN_NAME"] for c in cols[:8]]
            rows = query(f"SELECT TOP 2 {', '.join(col_names)} FROM {tabela}")
            result[tabela] = {"colunas": [c["COLUMN_NAME"] for c in cols], "amostra": rows}
        except Exception as e:
            result[tabela] = {"erro": str(e)}
    return result
@app.get("/api/debug/estoque4")
def debug_estoque4():
    """Busca tabelas de movimentação de estoque com nomes alternativos."""
    
    # Todas as tabelas do banco
    all_tabs = query("""
        SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME
    """)
    all_names = [r["TABLE_NAME"] for r in all_tabs]
    
    # Filtra candidatos de estoque
    keywords = ["afe","aft","nfe","nf_","nota","comp","ped","forn","lot","lote",
                "afn","alm","dep","arm","cons","giro","inv","bal","apl","req","fat"]
    candidates = [n for n in all_names if any(n.lower().startswith(k) or k in n.lower() for k in keywords)]
    
    # Amostra das tabelas AFT e AFE (Almoxarifado/Nota Fiscal)
    result = {"todos_candidatos": candidates[:30]}
    for tabela in ["AFT","AFE","AFN","NF","LOT","ALM","APL","FAT_EST"][:5]:
        if tabela in all_names:
            try:
                cols = query(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{tabela}' ORDER BY ORDINAL_POSITION")
                col_names = [c["COLUMN_NAME"] for c in cols[:6]]
                rows = query(f"SELECT TOP 2 {', '.join(col_names)} FROM {tabela}")
                result[tabela] = {"colunas": [c["COLUMN_NAME"] for c in cols], "amostra": rows}
            except Exception as e:
                result[tabela] = {"erro": str(e)}

    # MAT com dados reais — quantidade atual
    mat_stats = query("""
        SELECT COUNT(*) AS total_itens,
               SUM(CASE WHEN MAT_QT_EST_ATUAL > 0 THEN 1 ELSE 0 END) AS com_estoque,
               SUM(CASE WHEN MAT_QT_EST_ATUAL <= MAT_PT_RESSUPRIMENTO 
                         AND MAT_PT_RESSUPRIMENTO > 0 THEN 1 ELSE 0 END) AS abaixo_minimo,
               SUM(CASE WHEN MAT_QT_EST_ATUAL = 0 THEN 1 ELSE 0 END) AS zerado,
               SUM(MAT_QT_EST_ATUAL * MAT_VLR_PM) AS valor_total_estoque
        FROM MAT WHERE MAT_DEL_LOGICA <> 'S'
    """)
    result["mat_resumo"] = mat_stats[0] if mat_stats else {}
    
    # Top 5 materiais por valor
    top_mat = query("""
        SELECT TOP 5 MAT_COD, RTRIM(MAT_DESC_RESUMIDA) AS descricao,
               MAT_QT_EST_ATUAL AS qtd_atual,
               MAT_VLR_PM AS preco_medio,
               MAT_QT_EST_ATUAL * MAT_VLR_PM AS valor_total,
               MAT_IND_CURVA_ABC AS curva_abc,
               MAT_CONS_MEDIO AS consumo_medio,
               MAT_PT_RESSUPRIMENTO AS ponto_resuprimento
        FROM MAT WHERE MAT_DEL_LOGICA <> 'S' AND MAT_QT_EST_ATUAL > 0
        ORDER BY valor_total DESC
    """)
    result["top_materiais"] = top_mat
    
    return result
@app.get("/api/debug/estoque3")
def debug_estoque3():
    """Detalha SLD, ENTRADA_FI_PI, SAIDA_FI_PI."""
    result = {}
    for tabela in ["SLD","ENTRADA_FI_PI","SAIDA_FI_PI","sld_rastro","EXC_SALDO_INI"]:
        try:
            cols = query(f"""
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='{tabela}' ORDER BY ORDINAL_POSITION
            """)
            col_names = [c["COLUMN_NAME"] for c in cols[:8]]
            rows = query(f"SELECT TOP 2 {', '.join(col_names)} FROM {tabela}")
            result[tabela] = {"colunas": [c["COLUMN_NAME"] for c in cols], "amostra": rows}
        except Exception as e:
            result[tabela] = {"erro": str(e)}
    return result
@app.get("/api/debug/estoque2")
def debug_estoque2():
    """Detalha MAT, REQ, STONE e busca movimentações."""

    result = {}

    for tabela in ["MAT","REQ","STONE","mat_str","mat_pac"]:
        try:
            cols = query(f"""
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='{tabela}' ORDER BY ORDINAL_POSITION
            """)
            col_names = [c["COLUMN_NAME"] for c in cols[:8]]
            rows = query(f"SELECT TOP 3 {', '.join(col_names)} FROM {tabela}")
            result[tabela] = {"colunas": [c["COLUMN_NAME"] for c in cols], "amostra": rows}
        except Exception as e:
            result[tabela] = {"erro": str(e)}

    # Tabelas com mov no nome
    mov_tabs = query("""
        SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE='BASE TABLE'
          AND (TABLE_NAME LIKE '%mov%' OR TABLE_NAME LIKE '%cons%'
               OR TABLE_NAME LIKE '%ent%' OR TABLE_NAME LIKE '%sai%'
               OR TABLE_NAME LIKE '%sld%' OR TABLE_NAME LIKE '%sal%')
        ORDER BY TABLE_NAME
    """)
    result["tabelas_mov"] = [r["TABLE_NAME"] for r in mov_tabs]

    return result

# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO ESTOQUE
# MMA = Movimentações (E=entrada, S=saída), LOT = Lotes, MAT = Materiais
# MMA_TIPO_OPERACAO: E0/E1=entrada, S0/S1/S2=saída, T=transferência
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/estoque/resumo")
def estoque_resumo(periodo: str = "30d", data_inicio: str = "2025-01-01", data_fim: str = ""):
    inicio, fim = periodo_datas(periodo)
    
    # KPIs — filtra apenas materiais com movimentação a partir de data_inicio
    # para evitar distorção de itens antigos/vencidos sem movimentação recente
    kpis = query(f"""
        SELECT
            COUNT(DISTINCT mat.MAT_COD)                                     AS total_itens,
            SUM(CASE WHEN mat.MAT_QT_EST_ATUAL > 0 THEN 1 ELSE 0 END)      AS com_estoque,
            SUM(CASE WHEN mat.MAT_QT_EST_ATUAL = 0 THEN 1 ELSE 0 END)      AS zerados,
            SUM(CASE WHEN mat.MAT_PT_RESSUPRIMENTO > 0
                      AND mat.MAT_QT_EST_ATUAL <= mat.MAT_PT_RESSUPRIMENTO
                     THEN 1 ELSE 0 END)                                     AS abaixo_minimo,
            SUM(mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM)                     AS valor_total,
            SUM(CASE WHEN mat.MAT_IND_CURVA_ABC='A' THEN mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM ELSE 0 END) AS valor_curva_a,
            SUM(CASE WHEN mat.MAT_IND_CURVA_ABC='B' THEN mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM ELSE 0 END) AS valor_curva_b,
            SUM(CASE WHEN mat.MAT_IND_CURVA_ABC='C' THEN mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM ELSE 0 END) AS valor_curva_c
        FROM MAT mat
        WHERE mat.MAT_DEL_LOGICA <> 'S'
          AND mat.MAT_QT_EST_ATUAL > 0
          AND EXISTS (
              SELECT 1 FROM MMA
              WHERE MMA_MAT_COD = mat.MAT_COD
                AND MMA_DATA_MOV >= '{data_inicio}'
                AND MMA_IND_CANCELADA <> 'S'
          )
    """)
    
    # Movimentações do período
    mov = query(f"""
        SELECT
            SUM(CASE WHEN MMA_TIPO_ES='E' THEN MMA_QTD ELSE 0 END)   AS qtd_entradas,
            SUM(CASE WHEN MMA_TIPO_ES='S' THEN MMA_QTD ELSE 0 END)   AS qtd_saidas,
            SUM(CASE WHEN MMA_TIPO_ES='E' THEN MMA_VALOR ELSE 0 END) AS valor_entradas,
            SUM(CASE WHEN MMA_TIPO_ES='S' THEN MMA_VALOR ELSE 0 END) AS valor_saidas,
            COUNT(DISTINCT MMA_MAT_COD)                               AS materiais_movimentados
        FROM MMA
        WHERE MMA_DATA_MOV BETWEEN '{data_inicio}' AND CASE WHEN '{data_fim}' = '' THEN CONVERT(VARCHAR,GETDATE(),120) ELSE '{data_fim} 23:59:59' END
          AND MMA_IND_CANCELADA <> 'S'
    """)
    
    # Lotes vencendo em 30/60/90 dias
    vencimento = query("""
        SELECT
            SUM(CASE WHEN DATEDIFF(day,GETDATE(),LOT_DATA_VALIDADE) BETWEEN 0 AND 30  THEN 1 ELSE 0 END) AS vence_30d,
            SUM(CASE WHEN DATEDIFF(day,GETDATE(),LOT_DATA_VALIDADE) BETWEEN 31 AND 60 THEN 1 ELSE 0 END) AS vence_60d,
            SUM(CASE WHEN DATEDIFF(day,GETDATE(),LOT_DATA_VALIDADE) BETWEEN 61 AND 90 THEN 1 ELSE 0 END) AS vence_90d,
            SUM(CASE WHEN LOT_DATA_VALIDADE < GETDATE() AND LOT_SALDO > 0 THEN 1 ELSE 0 END) AS vencidos
        FROM LOT WHERE LOT_SALDO > 0
    """)
    
    k = kpis[0] if kpis else {}
    m = mov[0] if mov else {}
    v = vencimento[0] if vencimento else {}
    
    return {**k, **m, **v,
            "periodo_inicio": inicio, "periodo_fim": fim}


@app.get("/api/estoque/posicao")
def estoque_posicao(curva: str = "", busca: str = "", limite: int = 50):
    """Posição atual do estoque com indicadores de criticidade."""
    filtro_curva = f"AND MAT_IND_CURVA_ABC = '{curva}'" if curva else ""
    filtro_busca = f"AND (MAT_DESC_RESUMIDA LIKE '%{busca}%' OR MAT_DESC_COMPLETA LIKE '%{busca}%')" if busca else ""
    
    rows = query(f"""
        SELECT TOP {limite}
            MAT_COD                                     AS cod,
            RTRIM(MAT_DESC_RESUMIDA)                    AS descricao,
            MAT_QT_EST_ATUAL                            AS qtd_atual,
            MAT_VLR_PM                                  AS preco_medio,
            MAT_QT_EST_ATUAL * MAT_VLR_PM               AS valor_total,
            MAT_IND_CURVA_ABC                           AS curva_abc,
            MAT_CONS_MEDIO                              AS consumo_medio,
            MAT_PT_RESSUPRIMENTO                        AS ponto_ressuprimento,
            MAT_PT_SEGURANCA                            AS ponto_seguranca,
            MAT_ESTOQ_MAXIMO                            AS estoque_maximo,
            MAT_PRC_ULT_ENTRADA                         AS preco_ult_entrada,
            MAT_DTHR_ULT_ENTRADA                        AS dt_ult_entrada,
            MAT_DTHR_ULT_SAIDA                          AS dt_ult_saida,
            MAT_IND_CRITICIDADE                         AS criticidade,
            CASE
                WHEN MAT_QT_EST_ATUAL = 0 THEN 'ZERADO'
                WHEN MAT_PT_RESSUPRIMENTO > 0 AND MAT_QT_EST_ATUAL <= MAT_PT_RESSUPRIMENTO THEN 'CRITICO'
                WHEN MAT_PT_SEGURANCA > 0 AND MAT_QT_EST_ATUAL <= MAT_PT_SEGURANCA THEN 'ATENCAO'
                WHEN MAT_ESTOQ_MAXIMO > 0 AND MAT_QT_EST_ATUAL >= MAT_ESTOQ_MAXIMO THEN 'EXCESSO'
                ELSE 'NORMAL'
            END AS status_estoque,
            CASE WHEN MAT_CONS_MEDIO > 0
                 THEN CAST(MAT_QT_EST_ATUAL / MAT_CONS_MEDIO AS DECIMAL(10,1))
                 ELSE NULL END AS cobertura_dias
        FROM MAT
        WHERE MAT_DEL_LOGICA <> 'S'
          {filtro_curva}
          {filtro_busca}
        ORDER BY valor_total DESC
    """)
    for r in rows:
        for f in ["dt_ult_entrada","dt_ult_saida"]:
            if hasattr(r.get(f),"strftime"): r[f] = r[f].strftime("%Y-%m-%d")
    return rows


@app.get("/api/estoque/giro")
def estoque_giro(periodo: str = "30d", limite: int = 50):
    """
    Relatório de giro de estoque.
    Giro = Saídas no período / Estoque médio
    Cobertura = Estoque atual / Consumo médio diário
    """
    inicio, fim = periodo_datas(periodo)
    import datetime as dt
    dias_periodo = (dt.datetime.strptime(fim,"%Y-%m-%d") - dt.datetime.strptime(inicio,"%Y-%m-%d")).days + 1
    
    rows = query(f"""
        SELECT TOP {limite}
            mat.MAT_COD                                                 AS cod,
            RTRIM(mat.MAT_DESC_RESUMIDA)                                AS descricao,
            mat.MAT_IND_CURVA_ABC                                       AS curva_abc,
            mat.MAT_QT_EST_ATUAL                                        AS estoque_atual,
            mat.MAT_VLR_PM                                              AS preco_medio,
            mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM                       AS valor_estoque,
            ISNULL(mov.qtd_saidas, 0)                                   AS saidas_periodo,
            ISNULL(mov.valor_saidas, 0)                                 AS valor_saidas,
            ISNULL(mov.qtd_entradas, 0)                                 AS entradas_periodo,
            ISNULL(mov.valor_entradas, 0)                               AS valor_entradas,
            -- Giro = saídas / estoque atual (se estoque > 0)
            CASE WHEN mat.MAT_QT_EST_ATUAL > 0 AND ISNULL(mov.qtd_saidas,0) > 0
                 THEN CAST(ISNULL(mov.qtd_saidas,0) AS DECIMAL(12,2)) / mat.MAT_QT_EST_ATUAL
                 ELSE 0 END                                             AS giro_estoque,
            -- Cobertura em dias = estoque atual / (saídas/dias_período)
            CASE WHEN ISNULL(mov.qtd_saidas,0) > 0
                 THEN CAST(mat.MAT_QT_EST_ATUAL * {dias_periodo} AS DECIMAL(12,1)) / mov.qtd_saidas
                 ELSE NULL END                                          AS cobertura_dias,
            mat.MAT_CONS_MEDIO                                          AS consumo_medio_hist
        FROM MAT mat
        LEFT JOIN (
            SELECT MMA_MAT_COD,
                   SUM(CASE WHEN MMA_TIPO_ES='S' THEN MMA_QTD   ELSE 0 END) AS qtd_saidas,
                   SUM(CASE WHEN MMA_TIPO_ES='S' THEN MMA_VALOR  ELSE 0 END) AS valor_saidas,
                   SUM(CASE WHEN MMA_TIPO_ES='E' THEN MMA_QTD   ELSE 0 END) AS qtd_entradas,
                   SUM(CASE WHEN MMA_TIPO_ES='E' THEN MMA_VALOR  ELSE 0 END) AS valor_entradas
            FROM MMA
            WHERE MMA_DATA_MOV BETWEEN '{inicio}' AND '{fim} 23:59:59'
              AND MMA_IND_CANCELADA <> 'S'
            GROUP BY MMA_MAT_COD
        ) mov ON mov.MMA_MAT_COD = mat.MAT_COD
        WHERE mat.MAT_DEL_LOGICA <> 'S'
          AND (mat.MAT_QT_EST_ATUAL > 0 OR ISNULL(mov.qtd_saidas,0) > 0)
        ORDER BY ISNULL(mov.valor_saidas,0) DESC
    """)
    return rows


@app.get("/api/estoque/lotes-vencimento")
def estoque_lotes_vencimento(dias: int = 90):
    """Lotes vencendo nos próximos N dias ou já vencidos com saldo."""
    rows = query(f"""
        SELECT
            mat.MAT_COD                                 AS cod,
            RTRIM(mat.MAT_DESC_RESUMIDA)                AS material,
            mat.MAT_IND_CURVA_ABC                       AS curva_abc,
            RTRIM(lot.LOT_NUM)                          AS lote,
            lot.LOT_DATA_ENTRADA                        AS dt_entrada,
            lot.LOT_DATA_VALIDADE                       AS dt_validade,
            lot.LOT_SALDO                               AS saldo,
            lot.LOT_SALDO * mat.MAT_VLR_PM              AS valor_em_risco,
            DATEDIFF(day,GETDATE(),lot.LOT_DATA_VALIDADE) AS dias_para_vencer,
            CASE
                WHEN lot.LOT_DATA_VALIDADE < GETDATE() THEN 'VENCIDO'
                WHEN DATEDIFF(day,GETDATE(),lot.LOT_DATA_VALIDADE) <= 30 THEN 'CRITICO'
                WHEN DATEDIFF(day,GETDATE(),lot.LOT_DATA_VALIDADE) <= 60 THEN 'ATENCAO'
                ELSE 'OK'
            END AS status_validade,
            RTRIM(lot.LOT_SBA_COD)                      AS almoxarifado
        FROM LOT lot
        JOIN MAT mat ON mat.MAT_COD = lot.LOT_MAT_COD
        WHERE lot.LOT_SALDO > 0
          AND lot.LOT_DATA_VALIDADE <= DATEADD(day,{dias},GETDATE())
          AND mat.MAT_DEL_LOGICA <> 'S'
        ORDER BY lot.LOT_DATA_VALIDADE
    """)
    for r in rows:
        for f in ["dt_entrada","dt_validade"]:
            if hasattr(r.get(f),"strftime"): r[f] = r[f].strftime("%Y-%m-%d")
    return rows


@app.get("/api/estoque/movimentacoes")
def estoque_movimentacoes(periodo: str = "30d", tipo: str = ""):
    """Movimentações do período. tipo: E=entradas, S=saídas, vazio=todas."""
    inicio, fim = periodo_datas(periodo)
    filtro_tipo = f"AND MMA_TIPO_ES = '{tipo}'" if tipo else ""
    
    rows = query(f"""
        SELECT TOP 200
            mma.MMA_DATA_MOV                            AS data,
            mma.MMA_TIPO_OPERACAO                       AS tipo_op,
            mma.MMA_TIPO_ES                             AS tipo_es,
            RTRIM(mat.MAT_DESC_RESUMIDA)                AS material,
            mat.MAT_IND_CURVA_ABC                       AS curva_abc,
            mma.MMA_QTD                                 AS qtd,
            mma.MMA_VLR_PM                              AS preco_unitario,
            mma.MMA_VALOR                               AS valor_total,
            RTRIM(mma.MMA_SBA_COD)                      AS almoxarifado,
            RTRIM(mma.MMA_STR_COD)                      AS setor_cod,
            RTRIM(str.str_nome)                         AS setor_nome,
            RTRIM(mma.MMA_USR_LOGIN)                    AS usuario
        FROM MMA mma
        JOIN MAT mat ON mat.MAT_COD = mma.MMA_MAT_COD
        LEFT JOIN str ON str.str_cod = mma.MMA_STR_COD
        WHERE mma.MMA_DATA_MOV BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND mma.MMA_IND_CANCELADA <> 'S'
          {filtro_tipo}
        ORDER BY mma.MMA_DATA_MOV DESC
    """)
    for r in rows:
        if hasattr(r.get("data"),"strftime"): r["data"] = r["data"].strftime("%Y-%m-%d")
    return rows


@app.get("/api/estoque/curva-abc")
def estoque_curva_abc():
    """Distribuição da curva ABC com totais."""
    rows = query("""
        SELECT
            MAT_IND_CURVA_ABC                           AS curva,
            COUNT(*)                                    AS qtd_itens,
            SUM(MAT_QT_EST_ATUAL)                       AS qtd_total,
            SUM(MAT_QT_EST_ATUAL * MAT_VLR_PM)          AS valor_total,
            AVG(MAT_CONS_MEDIO)                         AS consumo_medio_avg
        FROM MAT
        WHERE MAT_DEL_LOGICA <> 'S' AND MAT_IND_CURVA_ABC IS NOT NULL
        GROUP BY MAT_IND_CURVA_ABC
        ORDER BY MAT_IND_CURVA_ABC
    """)
    total_valor = sum(r["valor_total"] or 0 for r in rows)
    for r in rows:
        r["pct_valor"] = round(((r["valor_total"] or 0) / total_valor * 100), 1) if total_valor else 0
    return rows


@app.get("/api/estoque/mov-por-dia")
def estoque_mov_por_dia(periodo: str = "30d"):
    inicio, fim = periodo_datas(periodo)
    rows = query(f"""
        SELECT
            CAST(MMA_DATA_MOV AS DATE)                  AS data,
            SUM(CASE WHEN MMA_TIPO_ES='E' THEN MMA_VALOR ELSE 0 END) AS valor_entradas,
            SUM(CASE WHEN MMA_TIPO_ES='S' THEN MMA_VALOR ELSE 0 END) AS valor_saidas,
            SUM(CASE WHEN MMA_TIPO_ES='E' THEN MMA_QTD   ELSE 0 END) AS qtd_entradas,
            SUM(CASE WHEN MMA_TIPO_ES='S' THEN MMA_QTD   ELSE 0 END) AS qtd_saidas
        FROM MMA
        WHERE MMA_DATA_MOV BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND MMA_IND_CANCELADA <> 'S'
        GROUP BY CAST(MMA_DATA_MOV AS DATE)
        ORDER BY data
    """)
    for r in rows:
        if hasattr(r.get("data"),"strftime"): r["data"] = r["data"].strftime("%Y-%m-%d")
    return rows




@app.get("/api/estoque/por-setor")
def estoque_por_setor(periodo: str = "30d"):
    """Dashboard de consumo de materiais por setor."""
    inicio, fim = periodo_datas(periodo)

    # Totais por setor
    por_setor = query(f"""
        SELECT
            RTRIM(mma.MMA_STR_COD)                                          AS setor_cod,
            RTRIM(str.str_nome)                                             AS setor_nome,
            COUNT(DISTINCT mma.MMA_MAT_COD)                                 AS materiais_distintos,
            SUM(mma.MMA_QTD)                                                AS qtd_total,
            SUM(mma.MMA_VALOR)                                              AS valor_total,
            COUNT(DISTINCT CAST(mma.MMA_DATA_MOV AS DATE))                  AS dias_com_retirada
        FROM MMA mma
        LEFT JOIN str ON str.str_cod = mma.MMA_STR_COD
        WHERE mma.MMA_DATA_MOV BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND mma.MMA_TIPO_ES = 'S'
          AND mma.MMA_IND_CANCELADA <> 'S'
          AND mma.MMA_STR_COD IS NOT NULL
        GROUP BY RTRIM(mma.MMA_STR_COD), RTRIM(str.str_nome)
        ORDER BY valor_total DESC
    """)

    # Top materiais por setor — busca os top 10 de cada setor via ROW_NUMBER
    top_mat = query(f"""
        SELECT setor_cod, material, curva_abc, qtd, valor
        FROM (
            SELECT
                RTRIM(mma.MMA_STR_COD)          AS setor_cod,
                RTRIM(mat.MAT_DESC_RESUMIDA)     AS material,
                mat.MAT_IND_CURVA_ABC            AS curva_abc,
                SUM(mma.MMA_QTD)                AS qtd,
                SUM(mma.MMA_VALOR)              AS valor,
                ROW_NUMBER() OVER (
                    PARTITION BY RTRIM(mma.MMA_STR_COD)
                    ORDER BY SUM(mma.MMA_VALOR) DESC
                ) AS rn
            FROM MMA mma
            JOIN MAT mat ON mat.MAT_COD = mma.MMA_MAT_COD
            WHERE mma.MMA_DATA_MOV BETWEEN '{inicio}' AND '{fim} 23:59:59'
              AND mma.MMA_TIPO_ES = 'S'
              AND mma.MMA_IND_CANCELADA <> 'S'
              AND mma.MMA_STR_COD IS NOT NULL
              AND LTRIM(RTRIM(mma.MMA_STR_COD)) <> ''
            GROUP BY RTRIM(mma.MMA_STR_COD), RTRIM(mat.MAT_DESC_RESUMIDA), mat.MAT_IND_CURVA_ABC
        ) t
        WHERE rn <= 10
        ORDER BY setor_cod, valor DESC
    """)

    # Evolução diária por setor (top 5 setores)
    top5 = [r["setor_cod"] for r in por_setor[:5]]
    top5_sql = ",".join(f"'{s}'" for s in top5) if top5 else "''"
    por_dia = query(f"""
        SELECT
            CAST(mma.MMA_DATA_MOV AS DATE)              AS data,
            RTRIM(mma.MMA_STR_COD)                      AS setor_cod,
            SUM(mma.MMA_VALOR)                          AS valor
        FROM MMA mma
        WHERE mma.MMA_DATA_MOV BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND mma.MMA_TIPO_ES = 'S'
          AND mma.MMA_IND_CANCELADA <> 'S'
          AND RTRIM(mma.MMA_STR_COD) IN ({top5_sql})
        GROUP BY CAST(mma.MMA_DATA_MOV AS DATE), RTRIM(mma.MMA_STR_COD)
        ORDER BY data, setor_cod
    """)
    for r in por_dia:
        if hasattr(r.get("data"),"strftime"): r["data"] = r["data"].strftime("%Y-%m-%d")

    return {
        "por_setor": por_setor,
        "top_materiais": top_mat,
        "por_dia": por_dia,
        "top5_setores": top5,
    }

@app.get("/api/estoque/por-grupo")
def estoque_por_grupo(periodo: str = "30d"):
    """Dashboard por grupo (GMM) e linha (LMA) de material."""
    inicio, fim = periodo_datas(periodo)

    # Por grupo GMM
    por_grupo = query(f"""
        SELECT
            gmm.GMM_COD                                                     AS grupo_cod,
            RTRIM(gmm.GMM_NOME)                                             AS grupo_nome,
            COUNT(DISTINCT mat.MAT_COD)                                     AS total_itens,
            SUM(CASE WHEN mat.MAT_QT_EST_ATUAL > 0 THEN 1 ELSE 0 END)      AS itens_com_estoque,
            SUM(CASE WHEN mat.MAT_QT_EST_ATUAL = 0 THEN 1 ELSE 0 END)      AS itens_zerados,
            SUM(CASE WHEN mat.MAT_PT_RESSUPRIMENTO > 0
                      AND mat.MAT_QT_EST_ATUAL <= mat.MAT_PT_RESSUPRIMENTO
                     THEN 1 ELSE 0 END)                                     AS itens_criticos,
            SUM(mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM)                     AS valor_estoque,
            ISNULL(SUM(mov.qtd_saidas),0)                                   AS saidas_periodo,
            ISNULL(SUM(mov.valor_saidas),0)                                 AS valor_saidas,
            ISNULL(SUM(mov.qtd_entradas),0)                                 AS entradas_periodo,
            ISNULL(SUM(mov.valor_entradas),0)                               AS valor_entradas
        FROM GMM gmm
        LEFT JOIN MAT mat ON mat.MAT_GMM_COD = gmm.GMM_COD
                         AND mat.MAT_DEL_LOGICA <> 'S'
        LEFT JOIN (
            SELECT MMA_MAT_COD,
                   SUM(CASE WHEN MMA_TIPO_ES='S' THEN MMA_QTD   ELSE 0 END) AS qtd_saidas,
                   SUM(CASE WHEN MMA_TIPO_ES='S' THEN MMA_VALOR  ELSE 0 END) AS valor_saidas,
                   SUM(CASE WHEN MMA_TIPO_ES='E' THEN MMA_QTD   ELSE 0 END) AS qtd_entradas,
                   SUM(CASE WHEN MMA_TIPO_ES='E' THEN MMA_VALOR  ELSE 0 END) AS valor_entradas
            FROM MMA
            WHERE MMA_DATA_MOV BETWEEN '{inicio}' AND '{fim} 23:59:59'
              AND MMA_IND_CANCELADA <> 'S'
            GROUP BY MMA_MAT_COD
        ) mov ON mov.MMA_MAT_COD = mat.MAT_COD
        WHERE gmm.GMM_COD <> '0'
        GROUP BY gmm.GMM_COD, gmm.GMM_NOME
        HAVING COUNT(DISTINCT mat.MAT_COD) > 0
        ORDER BY valor_estoque DESC
    """)

    # Por linha LMA — JOIN correto usando MAT_LMA_COD + MAT_GMM_COD para evitar duplicatas
    # LMA_COD pode repetir entre grupos, usar combinação LMA_COD + GMM_COD como chave
    por_linha = query(f"""
        SELECT TOP 15
            RTRIM(mat.MAT_LMA_COD)                                          AS linha_cod,
            RTRIM(mat.MAT_GMM_COD)                                          AS grupo_cod,
            RTRIM(lma.LMA_NOME)                                             AS linha_nome,
            RTRIM(gmm.GMM_NOME)                                             AS grupo_nome,
            COUNT(DISTINCT mat.MAT_COD)                                     AS total_itens,
            SUM(mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM)                     AS valor_estoque,
            ISNULL(SUM(mov.valor_saidas),0)                                 AS valor_saidas,
            ISNULL(SUM(mov.qtd_saidas),0)                                   AS qtd_saidas
        FROM MAT mat
        LEFT JOIN LMA lma ON RTRIM(lma.LMA_COD)    = RTRIM(mat.MAT_LMA_COD)
                         AND RTRIM(lma.LMA_GMM_COD) = RTRIM(mat.MAT_GMM_COD)
        LEFT JOIN GMM gmm ON RTRIM(gmm.GMM_COD)    = RTRIM(mat.MAT_GMM_COD)
        LEFT JOIN (
            SELECT MMA_MAT_COD,
                   SUM(CASE WHEN MMA_TIPO_ES='S' THEN MMA_VALOR ELSE 0 END) AS valor_saidas,
                   SUM(CASE WHEN MMA_TIPO_ES='S' THEN MMA_QTD   ELSE 0 END) AS qtd_saidas
            FROM MMA
            WHERE MMA_DATA_MOV BETWEEN '{inicio}' AND '{fim} 23:59:59'
              AND MMA_IND_CANCELADA <> 'S'
            GROUP BY MMA_MAT_COD
        ) mov ON mov.MMA_MAT_COD = mat.MAT_COD
        WHERE mat.MAT_DEL_LOGICA <> 'S'
          AND mat.MAT_LMA_COD IS NOT NULL
          AND RTRIM(mat.MAT_LMA_COD) <> '0'
        GROUP BY RTRIM(mat.MAT_LMA_COD), RTRIM(mat.MAT_GMM_COD),
                 RTRIM(lma.LMA_NOME), RTRIM(gmm.GMM_NOME)
        HAVING COUNT(DISTINCT mat.MAT_COD) > 0
        ORDER BY valor_estoque DESC
    """)

    # Top materiais por grupo (detalhe ao clicar)
    top_por_grupo = query(f"""
        SELECT
            mat.MAT_GMM_COD                                                 AS grupo_cod,
            mat.MAT_COD                                                     AS cod,
            RTRIM(mat.MAT_DESC_RESUMIDA)                                    AS descricao,
            mat.MAT_IND_CURVA_ABC                                           AS curva_abc,
            mat.MAT_QT_EST_ATUAL                                            AS qtd_atual,
            mat.MAT_VLR_PM                                                  AS preco_medio,
            mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM                          AS valor_estoque,
            ISNULL(mov.valor_saidas,0)                                      AS valor_saidas,
            ISNULL(mov.qtd_saidas,0)                                        AS qtd_saidas,
            CASE
                WHEN mat.MAT_QT_EST_ATUAL = 0 THEN 'ZERADO'
                WHEN mat.MAT_PT_RESSUPRIMENTO > 0
                 AND mat.MAT_QT_EST_ATUAL <= mat.MAT_PT_RESSUPRIMENTO THEN 'CRITICO'
                ELSE 'NORMAL'
            END AS status_estoque
        FROM MAT mat
        LEFT JOIN (
            SELECT MMA_MAT_COD,
                   SUM(CASE WHEN MMA_TIPO_ES='S' THEN MMA_VALOR ELSE 0 END) AS valor_saidas,
                   SUM(CASE WHEN MMA_TIPO_ES='S' THEN MMA_QTD   ELSE 0 END) AS qtd_saidas
            FROM MMA
            WHERE MMA_DATA_MOV BETWEEN '{inicio}' AND '{fim} 23:59:59'
              AND MMA_IND_CANCELADA <> 'S'
            GROUP BY MMA_MAT_COD
        ) mov ON mov.MMA_MAT_COD = mat.MAT_COD
        WHERE mat.MAT_DEL_LOGICA <> 'S'
          AND mat.MAT_GMM_COD IS NOT NULL
          AND mat.MAT_GMM_COD <> '0'
        ORDER BY mat.MAT_GMM_COD, valor_estoque DESC
    """)

    return {
        "por_grupo": por_grupo,
        "por_linha": por_linha,
        "top_por_grupo": top_por_grupo,
    }






# ══════════════════════════════════════════════════════════════════════════════
# PAINEL TV — TEMPO REAL (atualiza a cada 30s)
# ══════════════════════════════════════════════════════════════════════════════

# Setores (osm_str) cuja produção deve ser somada junto com outro setor no Painel TV.
# PSI (Psicologia) soma junto com RCN (Recepção Consultórios) a pedido do usuário.
SETOR_MERGE_PAINEL = {"RCN": ["RCN", "PSI"]}

def _filtro_osm_str_painel(setor: str) -> str:
    if setor == "OCUP_TIPO":
        return "AND osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')"
    if not setor:
        return ""
    codigos = SETOR_MERGE_PAINEL.get(setor, [setor])
    lista = ",".join(f"'{c}'" for c in codigos)
    return f"AND RTRIM(osm.osm_str) IN ({lista})"


@app.get("/api/painel/resumo-hoje")
def painel_resumo_hoje(meta_diaria: float = None, setor: str = ""):
    """
    KPIs do dia atual em tempo real.
    setor='OCUP_TIPO' → filtra por TIPO de atendimento ocupacional (osm_atend), não pela
    recepção física — usado pra bater com o KPI "Ocupacional" do painel geral.
    setor='RCN' → soma também a produção de Psicologia (osm_str='PSI').
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    filtro_str = _filtro_osm_str_painel(setor)

    # Atendimentos e faturamento do dia
    fat = query(f"""
        SELECT
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)              AS total_os,
            COUNT(DISTINCT osm.osm_pac)                                      AS pacientes_unicos,
            SUM(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0)
                - ISNULL(smm.SMM_VLR_COPARTIC,0)
                + ISNULL(smm.SMM_AJUSTE_VLR,0))                             AS faturamento,
            COUNT(DISTINCT CASE WHEN osm.osm_atend IN ('ASS','EME','CRG','TAM')
                                THEN osm.osm_serie*1000000+osm.osm_num END)  AS assistencial,
            COUNT(DISTINCT CASE WHEN osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')
                                THEN osm.osm_serie*1000000+osm.osm_num END)  AS ocupacional,
            COUNT(DISTINCT CASE WHEN osm.osm_atend NOT IN ('ASS','EME','CRG','TAM','ADM','PER','DEM','RTB','MDF','MOC')
                                THEN osm.osm_serie*1000000+osm.osm_num END)  AS outros
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
          AND smm.SMM_SFAT IN ('A','F','P')
          {filtro_str}
    """)

    # Tempo médio de atendimento
    # Tenta 1: osm_dthr → osm_dthr_saida (quando preenchido)
    # Tenta 2: agm_hini → agm_hfim para agendamentos executados hoje
    tempo = query(f"""
        SELECT
            AVG(dur) AS tempo_medio_min,
            MIN(dur) AS tempo_min_min,
            MAX(dur) AS tempo_max_min,
            COUNT(*) AS com_saida
        FROM (
            -- Fonte 1: OS com saída registrada (com filtro de setor via osm_str)
            SELECT DATEDIFF(minute, osm_dthr, osm_dthr_saida) AS dur
            FROM osm
            WHERE CAST(osm_dthr AS DATE) = '{hoje}'
              {filtro_str}
              AND osm_dthr_saida IS NOT NULL
              AND DATEDIFF(minute, osm_dthr, osm_dthr_saida) BETWEEN 1 AND 300

            UNION ALL

            -- Fonte 2: Agendamentos executados hoje com horário início e fim
            SELECT DATEDIFF(minute, agm.agm_hini, agm.agm_hfim) AS dur
            FROM agm
            JOIN osm ON osm.osm_pac = agm.agm_pac
                    AND CAST(osm.osm_dthr AS DATE) = '{hoje}'
                    {filtro_str}
            WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
              AND agm.agm_stat = 'E'
              AND agm.agm_hfim IS NOT NULL
              AND agm.agm_hini IS NOT NULL
              AND DATEDIFF(minute, agm.agm_hini, agm.agm_hfim) BETWEEN 1 AND 180

            UNION ALL

            -- Fonte 3: diferença entre OSs consecutivas do mesmo médico (com filtro setor)
            SELECT DATEDIFF(minute, osm_dthr,
                   LEAD(osm_dthr) OVER (PARTITION BY osm_mreq ORDER BY osm_dthr)) AS dur
            FROM osm
            WHERE CAST(osm_dthr AS DATE) = '{hoje}'
              {filtro_str}
              AND osm_atend IN ('ASS','ADM','PER','DEM','RTB','MDF','MOC')
        ) t
        WHERE dur BETWEEN 3 AND 120
    """)

    # OSs abertas agora (sem saída)
    em_atend = query(f"""
        SELECT COUNT(*) AS em_atendimento
        FROM osm
        WHERE CAST(osm_dthr AS DATE) = '{hoje}'
          {filtro_str}
          AND osm_dthr_saida IS NULL
          AND osm_status IS NULL
    """)

    # Tempo médio de ESPERA — fonte automática por setor:
    # Setores com FLE_DTHR_ATENDIMENTO preenchida (RDI, RCN, RPS): usa FLE
    # Setores sem FLE_DTHR_ATENDIMENTO (ROC): usa AGM→OSM
    filtro_fle = f"AND RTRIM(fle.FLE_STR_COD) = '{setor}'" if setor else ""

    # Tempo de espera — da senha (FLE_DTHR_CHEGADA) até a RECEPÇÃO CHAMAR a senha.
    # Prioriza FLE_DTHR_ATENDIMENTO (chamada real, gravada na própria senha).
    # IMPORTANTE: as filas de senha do Ocupacional (Outras Empresas, Vale, Particular,
    # Prioridade por Lei etc.) são gravadas com FLE_STR_COD='RPS', não 'ROC' — 'ROC' é
    # só o setor da OS/faturamento. Confirmado com dado real: correlacionando OS do ROC
    # com senha RPS (mesmo paciente/dia) a cobertura sobe de ~0% pra ~84%, com tempos
    # de espera plausíveis (14-119min). Por isso mapeamos ROC→RPS só pra achar a senha;
    # RCN/RDI/RCI continuam usando o próprio FLE_STR_COD (já bate direto com osm_str).
    # Só cai pra osm_dthr (abertura da OS) como aproximação quando não há chamada
    # registrada nem senha correlacionada (ex: RCI, que não usa senha/totem).
    # OBS: FLE_OSM_SERIE/FLE_OSM_NUM foi testado como possível vínculo direto senha→OS,
    # mas os dados mostraram que não representa isso de forma confiável (valores repetidos
    # entre senhas diferentes, diferença de horário quase sempre negativa) — não usar.
    # Deduplica com TOP 1 para pegar a chegada mais recente antes da OS de cada paciente.
    filtro_str_espera = _filtro_osm_str_painel(setor)
    espera = query(f"""
        SELECT
            AVG(espera_min)  AS espera_media_min,
            MIN(espera_min)  AS espera_min_min,
            MAX(espera_min)  AS espera_max_min,
            COUNT(*)         AS total_com_agendamento,
            SUM(CASE WHEN espera_min > 15 THEN 1 ELSE 0 END) AS acima_15min,
            SUM(CASE WHEN espera_min > 30 THEN 1 ELSE 0 END) AS acima_30min
        FROM (
            SELECT DISTINCT
                osm.osm_serie,
                osm.osm_num,
                DATEDIFF(minute,
                    x.chegada,
                    COALESCE(x.atendimento, osm.osm_dthr)
                ) AS espera_min
            FROM osm
            CROSS APPLY (
                SELECT TOP 1 f2.FLE_DTHR_CHEGADA AS chegada, f2.FLE_DTHR_ATENDIMENTO AS atendimento
                FROM fle f2
                WHERE f2.FLE_PAC_REG = osm.osm_pac
                  AND RTRIM(f2.FLE_STR_COD) = CASE WHEN RTRIM(osm.osm_str) = 'ROC' THEN 'RPS' ELSE RTRIM(osm.osm_str) END
                  AND CAST(f2.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
                  AND f2.FLE_DTHR_CHEGADA <= osm.osm_dthr
                  AND f2.FLE_PAC_REG > 0
                ORDER BY f2.FLE_DTHR_CHEGADA DESC
            ) x
            WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
              {filtro_str_espera}
        ) t
        WHERE espera_min BETWEEN 1 AND 120
    """)

    # Última atualização
    ultima_os = query(f"""
        SELECT TOP 1 osm_dthr FROM osm
        WHERE CAST(osm_dthr AS DATE) = '{hoje}'
        ORDER BY osm_dthr DESC
    """)

    f0 = fat[0] if fat else {}
    t0 = tempo[0] if tempo else {}
    e0 = em_atend[0] if em_atend else {}
    fat_val = float(f0.get("faturamento") or 0)
    META_MENSAL = 1200000.0
    from calendar import monthrange
    import datetime as _dt
    _hoje = _dt.date.today()
    _dias_uteis = sum(1 for d in range(1, monthrange(_hoje.year, _hoje.month)[1]+1)
                      if _dt.date(_hoje.year, _hoje.month, d).weekday() < 6)
    if meta_diaria is None:
        meta_diaria = round(META_MENSAL / _dias_uteis, 2) if _dias_uteis > 0 else 45000
    pct_meta = round(fat_val / meta_diaria * 100, 1) if meta_diaria > 0 else 0
    falta = max(0, meta_diaria - fat_val)

    ult = ultima_os[0]["osm_dthr"] if ultima_os else None
    if hasattr(ult, "strftime"): ult = ult.strftime("%H:%M:%S")

    return {
        "total_os":           f0.get("total_os") or 0,
        "pacientes_unicos":   f0.get("pacientes_unicos") or 0,
        "faturamento":        fat_val,
        "assistencial":       f0.get("assistencial") or 0,
        "ocupacional":        f0.get("ocupacional") or 0,
        "em_atendimento":     e0.get("em_atendimento") or 0,
        "tempo_medio_min":    float(t0.get("tempo_medio_min") or 0),
        "tempo_min_min":      float(t0.get("tempo_min_min") or 0),
        "tempo_max_min":      float(t0.get("tempo_max_min") or 0),
        "espera_media_min":   float((espera[0].get("espera_media_min") or 0)) if espera else 0,
        "espera_min_min":     float((espera[0].get("espera_min_min") or 0)) if espera else 0,
        "espera_max_min":     float((espera[0].get("espera_max_min") or 0)) if espera else 0,
        "espera_acima_15":    int((espera[0].get("acima_15min") or 0)) if espera else 0,
        "espera_acima_30":    int((espera[0].get("acima_30min") or 0)) if espera else 0,
        "espera_total":       int((espera[0].get("total_com_agendamento") or 0)) if espera else 0,
        "meta_diaria":        meta_diaria,
        "pct_meta":           pct_meta,
        "falta_meta":         falta,
        "ultima_atualizacao": ult,
        "hora_atual":         datetime.now().strftime("%H:%M:%S"),
        "data_atual":         datetime.now().strftime("%d/%m/%Y"),
    }



# Único filtro de setor exibido no Painel TV: Consultórios, Diagnóstico,
# Ocupacional e Censo Imagem — Psicologia (PSI) soma dentro de Consultórios
# (RCN) e qualquer outro código (Laboratório, salas avulsas etc.) fica de fora.
SETORES_PAINEL_PERMITIDOS = ["RCN", "RDI", "ROC", "RCI"]

@app.get("/api/painel/setores")
def painel_setores():
    """Setores ativos hoje — restrito a Consultórios/Diagnóstico/Ocupacional/Censo Imagem."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    permitidos_sql = ",".join(f"'{c}'" for c in SETORES_PAINEL_PERMITIDOS)
    rows = query(f"""
        WITH base AS (
            SELECT
                CASE WHEN RTRIM(osm.osm_str) = 'PSI' THEN 'RCN' ELSE RTRIM(osm.osm_str) END AS setor_cod,
                osm.osm_serie, osm.osm_num, osm.osm_pac, osm.osm_dthr
            FROM osm
            WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
              AND osm.osm_str IS NOT NULL
              AND LTRIM(RTRIM(osm.osm_str)) <> ''
        )
        SELECT
            b.setor_cod,
            RTRIM(str.str_nome)                                  AS setor_nome,
            COUNT(DISTINCT b.osm_serie*1000000+b.osm_num)        AS atendimentos,
            -- espera media: FLE chegada → chamada da senha (FLE_DTHR_ATENDIMENTO).
            -- Ocupacional (ROC) usa a fila de senha 'RPS' (Outras Empresas, Vale,
            -- Particular etc.) — 'ROC' é só o setor da OS, não da senha. Só cai para
            -- a abertura da OS (osm_dthr) quando não há chamada nem senha correlacionada
            -- (caso do RCI, que não usa senha/totem).
            (SELECT AVG(t.espera_min) FROM (
                SELECT DISTINCT osm2.osm_serie, osm2.osm_num,
                    DATEDIFF(minute, x.chegada, COALESCE(x.atendimento, osm2.osm_dthr)) AS espera_min
                FROM osm osm2
                CROSS APPLY (
                    SELECT TOP 1 f2.FLE_DTHR_CHEGADA AS chegada, f2.FLE_DTHR_ATENDIMENTO AS atendimento
                    FROM fle f2
                    WHERE f2.FLE_PAC_REG = osm2.osm_pac
                      AND RTRIM(f2.FLE_STR_COD) = CASE WHEN RTRIM(osm2.osm_str) = 'ROC' THEN 'RPS' ELSE RTRIM(osm2.osm_str) END
                      AND CAST(f2.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
                      AND f2.FLE_DTHR_CHEGADA <= osm2.osm_dthr
                      AND f2.FLE_PAC_REG > 0
                    ORDER BY f2.FLE_DTHR_CHEGADA DESC
                ) x
                WHERE CAST(osm2.osm_dthr AS DATE) = '{hoje}'
                  AND (CASE WHEN RTRIM(osm2.osm_str) = 'PSI' THEN 'RCN' ELSE RTRIM(osm2.osm_str) END) = b.setor_cod
            ) t WHERE t.espera_min BETWEEN 1 AND 120)            AS espera_media_min
        FROM base b
        LEFT JOIN str ON RTRIM(str.str_cod) = b.setor_cod
        WHERE b.setor_cod IN ({permitidos_sql})
        GROUP BY b.setor_cod, RTRIM(str.str_nome)
        ORDER BY atendimentos DESC
    """)
    return rows


@app.get("/api/painel/medicos-solicitante")
def painel_medicos_solicitante(setor: str = ""):
    """Médicos solicitantes (osm_mreq) com atendimentos hoje."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    filtro_str = f"AND RTRIM(osm.osm_str) = '{setor}'" if setor else ""
    rows = query(f"""
        SELECT TOP 20
            RTRIM(psv.psv_apel)                                     AS medico,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)       AS atendimentos,
            COUNT(DISTINCT osm.osm_pac)                             AS pacientes,
            MAX(osm.osm_dthr)                                       AS ultimo_atend,
            osm.osm_atend                                           AS tipo_atend
        FROM osm
        JOIN psv ON psv.psv_cod = osm.osm_mreq
        WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
          {filtro_str}
        GROUP BY RTRIM(psv.psv_apel), osm.osm_atend
        ORDER BY atendimentos DESC
    """)
    for r in rows:
        if hasattr(r.get("ultimo_atend"), "strftime"):
            r["ultimo_atend"] = r["ultimo_atend"].strftime("%H:%M")
    return rows

@app.get("/api/painel/medicos-ativos")
def painel_medicos_ativos(setor: str = ""):
    """Médicos que atenderam hoje com contagem e último atendimento."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    filtro_str = f"AND RTRIM(osm.osm_str) = '{setor}'" if setor else ""
    rows = query(f"""
        SELECT
            RTRIM(psv.psv_apel)                                          AS medico,
            RTRIM(psv.psv_nome)                                          AS nome_completo,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)           AS atendimentos,
            COUNT(DISTINCT osm.osm_pac)                                  AS pacientes,
            MAX(osm.osm_dthr)                                            AS ultimo_atend,
            osm.osm_atend                                                AS tipo_atend,
            COUNT(DISTINCT CASE
                WHEN osm.osm_dthr_saida IS NULL
                 AND DATEDIFF(minute, osm.osm_dthr, GETDATE()) <= 60
                THEN osm.osm_serie*1000000+osm.osm_num END)             AS em_atend_agora
        FROM osm
        JOIN psv ON psv.psv_cod = osm.osm_mreq
        WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
          {filtro_str}
        GROUP BY psv.psv_apel, psv.psv_nome, osm.osm_atend
        ORDER BY atendimentos DESC
    """)
    for r in rows:
        if hasattr(r.get("ultimo_atend"), "strftime"):
            r["ultimo_atend"] = r["ultimo_atend"].strftime("%H:%M")
    return rows


@app.get("/api/painel/linha-tempo")
def painel_linha_tempo():
    """Linha do tempo de atendimentos hoje com tempo de cada OS."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    rows = query(f"""
        SELECT TOP 40
            osm.osm_serie,
            osm.osm_num,
            osm.osm_dthr                                                AS hora_abertura,
            osm.osm_dthr_saida                                          AS hora_saida,
            DATEDIFF(minute, osm.osm_dthr, osm.osm_dthr_saida)         AS duracao_min,
            osm.osm_atend,
            RTRIM(psv.psv_apel)                                         AS medico,
            RTRIM(pac.pac_nome)                                         AS paciente,
            CASE
                WHEN osm.osm_dthr_saida IS NOT NULL THEN 'CONCLUIDO'
                WHEN DATEDIFF(minute, osm.osm_dthr, GETDATE()) > 60    THEN 'DEMORADO'
                ELSE 'EM_ATEND'
            END                                                         AS status
        FROM osm
        LEFT JOIN psv ON psv.psv_cod = osm.osm_mreq
        LEFT JOIN pac ON pac.pac_reg = osm.osm_pac
        WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
        ORDER BY osm.osm_dthr DESC
    """)
    for r in rows:
        for f in ["hora_abertura","hora_saida"]:
            if hasattr(r.get(f),"strftime"): r[f] = r[f].strftime("%H:%M:%S")
    return rows


@app.get("/api/painel/evolucao-hora")
def painel_evolucao_hora():
    """Evolução de atendimentos e produção por hora hoje."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    rows = query(f"""
        SELECT
            DATEPART(hour, osm.osm_dthr)                                AS hora,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)           AS atendimentos,
            COUNT(DISTINCT osm.osm_pac)                                  AS pacientes,
            SUM(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0)
                - ISNULL(smm.SMM_VLR_COPARTIC,0)
                + ISNULL(smm.SMM_AJUSTE_VLR,0))                         AS faturamento
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY DATEPART(hour, osm.osm_dthr)
        ORDER BY hora
    """)
    return rows


@app.get("/api/financeiro/ocupacional-vs-assistencial")
def ocupacional_vs_assistencial(meses: int = 24):
    """
    Produção mensal (valor líquido) de Ocupacional vs Assistencial, lado a lado,
    para visualizar em que mês uma passou a superar a outra.
    """
    now = datetime.now()
    ano_ini, mes_ini = now.year, now.month - meses + 1
    while mes_ini <= 0:
        mes_ini += 12
        ano_ini -= 1
    inicio = f"{ano_ini}-{mes_ini:02d}-01"
    fim = now.strftime("%Y-%m-%d")
    vliq = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"

    rows = query(f"""
        SELECT
            YEAR(osm.osm_dthr)  AS ano,
            MONTH(osm.osm_dthr) AS mes,
            SUM(CASE WHEN osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC') THEN {vliq} ELSE 0 END) AS ocupacional,
            SUM(CASE WHEN osm.osm_atend = 'ASS' THEN {vliq} ELSE 0 END)                                    AS assistencial
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE AND osm.osm_num = smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY YEAR(osm.osm_dthr), MONTH(osm.osm_dthr)
        ORDER BY ano, mes
    """)
    for r in rows:
        r["ocupacional"]  = float(r["ocupacional"] or 0)
        r["assistencial"] = float(r["assistencial"] or 0)
    return rows


@app.get("/api/financeiro/faturamento-anual")
def faturamento_anual(anos: int = 3):
    """Faturamento mensal dos últimos N anos para comparativo."""
    now = datetime.now()
    results = {}
    for offset in range(anos):
        ano = now.year - offset
        meses = []
        for mes in range(1, 13):
            # Não buscar meses futuros
            if ano == now.year and mes > now.month:
                meses.append({"mes": mes, "valor": None})
                continue
            import calendar as _cal
            ultimo = _cal.monthrange(ano, mes)[1]
            inicio = f"{ano}-{mes:02d}-01"
            fim    = f"{ano}-{mes:02d}-{ultimo}"
            rows = query(f"""
                SELECT SUM(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0)
                           - ISNULL(smm.SMM_VLR_COPARTIC,0)
                           + ISNULL(smm.SMM_AJUSTE_VLR,0)) AS valor
                FROM smm
                JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
                WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
                  AND smm.SMM_SFAT IN ('A','F','P')
            """)
            meses.append({"mes": mes, "valor": float(rows[0]["valor"] or 0) if rows else 0})
        results[str(ano)] = meses
    return results




@app.get("/api/debug/totem-senha")
def debug_totem_senha():
    hoje = datetime.now().strftime("%Y-%m-%d")

    # 1. Estrutura das tabelas de senha
    resultados = {}
    for tabela in ["PSV_FILA", "PSV_SMK", "smk_fil", "FLE_CFG_SENHA", "smminst"]:
        try:
            cols = query(f"""
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='{tabela}' ORDER BY ORDINAL_POSITION
            """)
            col_names = [c["COLUMN_NAME"] for c in cols]
            # Tenta buscar registros de hoje
            date_cols = [c for c in col_names if any(x in c.upper() for x in ['DT','DATA','HORA','HR','TIME','DTHR'])]
            if date_cols:
                rows = query(f"SELECT TOP 3 {', '.join(col_names[:10])} FROM {tabela} WHERE CAST({date_cols[0]} AS DATE)='{hoje}'")
            else:
                rows = query(f"SELECT TOP 3 {', '.join(col_names[:10])} FROM {tabela}")
            resultados[tabela] = {"colunas": col_names, "amostra": rows}
        except Exception as e:
            resultados[tabela] = {"erro": str(e)}

    # 2. AGM tem campos de senha/totem?
    agm_senha = query("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='agm'
          AND (COLUMN_NAME LIKE '%sen%' OR COLUMN_NAME LIKE '%totem%'
               OR COLUMN_NAME LIKE '%senha%' OR COLUMN_NAME LIKE '%fila%'
               OR COLUMN_NAME LIKE '%smk%' OR COLUMN_NAME LIKE '%psv%'
               OR COLUMN_NAME LIKE '%cha%' OR COLUMN_NAME LIKE '%cheg%')
        ORDER BY ORDINAL_POSITION
    """)

    # 3. Tabela SMK_PRX (próximo a chamar?)
    smk_prx = {}
    try:
        cols = query("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='SMK_PRX' ORDER BY ORDINAL_POSITION")
        col_names = [c["COLUMN_NAME"] for c in cols]
        rows = query(f"SELECT TOP 3 {', '.join(col_names[:12])} FROM SMK_PRX")
        smk_prx = {"colunas": col_names, "amostra": rows}
    except Exception as e:
        smk_prx = {"erro": str(e)}

    # 4. Tabela AGM_SMK (relação agendamento x senha)
    agm_smk = {}
    try:
        cols = query("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='agm_smk' ORDER BY ORDINAL_POSITION")
        col_names = [c["COLUMN_NAME"] for c in cols]
        date_cols = [c for c in col_names if any(x in c.upper() for x in ['DT','DATA','HORA','HR','TIME'])]
        if date_cols:
            rows = query(f"SELECT TOP 5 {', '.join(col_names[:12])} FROM agm_smk WHERE CAST({date_cols[0]} AS DATE)='{hoje}'")
        else:
            rows = query(f"SELECT TOP 5 {', '.join(col_names[:12])} FROM agm_smk")
        agm_smk = {"colunas": col_names, "amostra": rows}
    except Exception as e:
        agm_smk = {"erro": str(e)}

    return {
        "tabelas_senha": resultados,
        "agm_colunas_senha": [c["COLUMN_NAME"] for c in agm_senha],
        "smk_prx": smk_prx,
        "agm_smk": agm_smk,
    }






@app.get("/api/debug/fila-espera2")
def debug_fila_espera2():
    hoje = datetime.now().strftime("%Y-%m-%d")
    
    # A tela mostra: Chegada, Marcado, Tempo espera, Atendido, BIP/Senha
    # Tabelas candidatas para fila de espera com hora de chegada
    candidatas = [
        "fila_rcl_clickvita", "PSV_DESVIO_FILA", "PSV_FILA",
        "SCI_SMK", "tap_smk", "RTC_CONJU_SMK", "QST_SMK",
        "OGP_SMK", "ITM_SMK", "ETI_SMK", "BCS_SMKPAD"
    ]
    
    results = {}
    for tab in candidatas:
        try:
            cols = query(f"""
                SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='{tab}' ORDER BY ORDINAL_POSITION
            """)
            col_names = [c["COLUMN_NAME"] for c in cols]
            if not col_names:
                continue
            
            dt_cols = [c["COLUMN_NAME"] for c in cols
                       if c["DATA_TYPE"] in ('datetime','datetime2','smalldatetime')]
            
            if dt_cols:
                cnt = query(f"SELECT COUNT(*) AS n FROM {tab} WHERE CAST({dt_cols[0]} AS DATE)='{hoje}'")
                n = cnt[0]["n"] if cnt else 0
                sample = []
                if n > 0:
                    sample = query(f"SELECT TOP 3 {','.join(col_names[:12])} FROM {tab} WHERE CAST({dt_cols[0]} AS DATE)='{hoje}' ORDER BY {dt_cols[0]} DESC")
                    for r in sample:
                        for k,v in r.items():
                            if hasattr(v,'strftime'): r[k]=v.strftime('%H:%M:%S')
                results[tab] = {"colunas": col_names, "hoje": n, "amostra": sample}
            else:
                sample = query(f"SELECT TOP 2 {','.join(col_names[:8])} FROM {tab}")
                results[tab] = {"colunas": col_names, "sem_data_col": True, "amostra": sample}
        except Exception as e:
            results[tab] = {"erro": str(e)[:150]}
    
    # Busca por tabelas com coluna "chegada" ou "bip" ou "senha"
    chegada_tabs = query("""
        SELECT DISTINCT TABLE_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE COLUMN_NAME LIKE '%cheg%' OR COLUMN_NAME LIKE '%bip%'
           OR COLUMN_NAME LIKE '%senha%' OR COLUMN_NAME LIKE '%chegad%'
           OR COLUMN_NAME LIKE '%fila%' OR COLUMN_NAME LIKE '%espera%'
           OR COLUMN_NAME LIKE '%triag%'
        ORDER BY TABLE_NAME
    """)
    results["_tabelas_com_col_chegada_bip"] = [r["TABLE_NAME"] for r in chegada_tabs]
    
    return results







@app.get("/api/debug/roc-fle-osm")
def debug_roc_fle_osm():
    hoje = datetime.now().strftime("%Y-%m-%d")

    # FLE chegada ROC → OSM abertura pelo paciente
    sample = query(f"""
        SELECT TOP 10
            fle.FLE_DTHR_CHEGADA,
            fle.FLE_PAC_REG,
            osm.osm_dthr,
            osm.osm_str,
            DATEDIFF(minute, fle.FLE_DTHR_CHEGADA, osm.osm_dthr) AS espera_min
        FROM fle
        JOIN osm ON osm.osm_pac = fle.FLE_PAC_REG
                AND CAST(osm.osm_dthr AS DATE) = '{hoje}'
                AND RTRIM(osm.osm_str) = 'ROC'
                AND osm.osm_dthr >= fle.FLE_DTHR_CHEGADA
        WHERE CAST(fle.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
          AND RTRIM(fle.FLE_STR_COD) = 'ROC'
          AND fle.FLE_PAC_REG > 0
        ORDER BY fle.FLE_DTHR_CHEGADA
    """)
    for r in sample:
        for k,v in r.items():
            if hasattr(v,'strftime'): r[k] = v.strftime('%H:%M:%S')

    # Media via FLE→OSM
    media = query(f"""
        SELECT
            AVG(DATEDIFF(minute, fle.FLE_DTHR_CHEGADA, osm.osm_dthr)) AS espera_media,
            COUNT(*) AS pares
        FROM fle
        JOIN osm ON osm.osm_pac = fle.FLE_PAC_REG
                AND CAST(osm.osm_dthr AS DATE) = '{hoje}'
                AND RTRIM(osm.osm_str) = 'ROC'
                AND osm.osm_dthr >= fle.FLE_DTHR_CHEGADA
                AND DATEDIFF(minute, fle.FLE_DTHR_CHEGADA, osm.osm_dthr) BETWEEN 1 AND 120
        WHERE CAST(fle.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
          AND RTRIM(fle.FLE_STR_COD) = 'ROC'
          AND fle.FLE_PAC_REG > 0
    """)

    return {"sample": sample, "media": media[0] if media else {}}
@app.get("/api/debug/roc-espera")
def debug_roc_espera():
    hoje = datetime.now().strftime("%Y-%m-%d")

    # AGM com OSM vinculado para pacientes do ROC
    agm_roc = query(f"""
        SELECT TOP 5
            agm.agm_hini, osm.osm_dthr, osm.osm_str,
            agm.agm_stat, agm.AGM_OSM_SERIE, agm.AGM_OSM_NUM,
            DATEDIFF(minute, agm.agm_hini, osm.osm_dthr) AS espera
        FROM agm
        JOIN osm ON osm.osm_serie = agm.AGM_OSM_SERIE
                AND osm.osm_num   = agm.AGM_OSM_NUM
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
          AND agm.agm_stat IN ('E','F')
          AND RTRIM(osm.osm_str) = 'ROC'
    """)

    # Quantos AGM do ROC têm OSM vinculado
    agm_count = query(f"""
        SELECT
            COUNT(*) AS total_agm,
            SUM(CASE WHEN agm.AGM_OSM_SERIE IS NOT NULL THEN 1 ELSE 0 END) AS com_osm,
            SUM(CASE WHEN agm.agm_stat IN ('E','F') THEN 1 ELSE 0 END) AS executados
        FROM agm
        JOIN osm ON osm.osm_serie = agm.AGM_OSM_SERIE
                AND osm.osm_num   = agm.AGM_OSM_NUM
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
          AND RTRIM(osm.osm_str) = 'ROC'
    """)

    # Tentar via pac: OSM ROC → AGM pelo paciente
    via_pac = query(f"""
        SELECT TOP 5
            osm.osm_dthr, agm.agm_hini, osm.osm_str,
            DATEDIFF(minute, agm.agm_hini, osm.osm_dthr) AS espera
        FROM osm
        JOIN agm ON agm.agm_pac = osm.osm_pac
                AND CAST(agm.agm_hini AS DATE) = '{hoje}'
                AND agm.agm_stat IN ('E','F')
                AND ABS(DATEDIFF(minute, agm.agm_hini, osm.osm_dthr)) < 120
        WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
          AND RTRIM(osm.osm_str) = 'ROC'
        ORDER BY osm.osm_dthr
    """)

    # FLE ROC com chegada mas sem atendimento
    fle_roc = query(f"""
        SELECT TOP 5
            FLE_DTHR_CHEGADA, FLE_DTHR_ATENDIMENTO,
            FLE_DTHR_MARCADA, FLE_STATUS,
            RTRIM(FLE_BIP) AS bip
        FROM fle
        WHERE CAST(FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
          AND RTRIM(FLE_STR_COD) = 'ROC'
        ORDER BY FLE_DTHR_CHEGADA DESC
    """)
    for r in fle_roc + agm_roc + via_pac:
        for k, v in r.items():
            if hasattr(v, 'strftime'): r[k] = v.strftime('%H:%M:%S')

    return {
        "agm_roc_com_osm_vinculado": agm_roc,
        "agm_roc_contagem": agm_count[0] if agm_count else {},
        "espera_via_paciente": via_pac,
        "fle_roc_amostra": fle_roc,
    }
@app.get("/api/debug/ocupacional-check")
def debug_ocupacional_check():
    hoje = datetime.now().strftime("%Y-%m-%d")
    
    # OSs ocupacionais hoje e seus setores
    osm_ocup = query(f"""
        SELECT RTRIM(osm.osm_str) AS setor_osm,
               RTRIM(str.str_nome) AS setor_nome,
               osm.osm_atend,
               COUNT(*) AS total
        FROM osm
        LEFT JOIN str ON str.str_cod = osm.osm_str
        WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
          AND osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')
        GROUP BY RTRIM(osm.osm_str), RTRIM(str.str_nome), osm.osm_atend
        ORDER BY total DESC
    """)
    
    # FLE do setor ROC hoje
    fle_roc = query(f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN FLE_DTHR_ATENDIMENTO IS NOT NULL THEN 1 ELSE 0 END) AS atendidos,
               AVG(CASE WHEN FLE_DTHR_ATENDIMENTO IS NOT NULL
                        AND DATEDIFF(minute,FLE_DTHR_CHEGADA,FLE_DTHR_ATENDIMENTO) BETWEEN 0 AND 120
                        THEN DATEDIFF(minute,FLE_DTHR_CHEGADA,FLE_DTHR_ATENDIMENTO) END) AS espera_media
        FROM fle WHERE CAST(FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
          AND RTRIM(FLE_STR_COD) = 'ROC'
    """)
    
    # Setores OSM que batem com filtro_str='ROC'
    osm_roc = query(f"""
        SELECT COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS total_os,
               COUNT(DISTINCT osm.osm_pac) AS pacientes,
               SUM(smm.SMM_VLR) AS faturamento
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
          AND smm.SMM_SFAT IN ('A','F','P')
          AND RTRIM(osm.osm_str) = 'ROC'
    """)
    
    # Quais atend types existem no setor ROC
    roc_atend = query(f"""
        SELECT osm.osm_atend, COUNT(*) AS n
        FROM osm WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
          AND RTRIM(osm.osm_str) = 'ROC'
        GROUP BY osm.osm_atend ORDER BY n DESC
    """)
    
    return {
        "osm_ocupacional_por_setor": osm_ocup,
        "fle_roc": fle_roc[0] if fle_roc else {},
        "osm_roc_faturamento": osm_roc[0] if osm_roc else {},
        "roc_tipos_atend": roc_atend,
    }
@app.get("/api/debug/censo-imagem")
def debug_censo_imagem():
    hoje = datetime.now().strftime("%Y-%m-%d")
    
    # Busca setor censo imagem no cadastro
    setores = query("""
        SELECT str_cod, RTRIM(str_nome) AS str_nome
        FROM str
        WHERE str_nome LIKE '%censo%' OR str_nome LIKE '%imagem%'
           OR str_cod LIKE '%CI%' OR str_cod LIKE '%IMG%'
           OR str_nome LIKE '%diagnos%'
        ORDER BY str_nome
    """)
    
    # Verifica OSs desse setor hoje
    osm_censo = query(f"""
        SELECT TOP 5
            RTRIM(osm.osm_str) AS setor_cod,
            RTRIM(str.str_nome) AS setor_nome,
            COUNT(*) AS total
        FROM osm
        LEFT JOIN str ON str.str_cod = osm.osm_str
        WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
          AND (str.str_nome LIKE '%censo%' OR str.str_nome LIKE '%imagem%'
               OR osm.osm_str LIKE '%CI%' OR osm.osm_str LIKE '%IMG%')
        GROUP BY RTRIM(osm.osm_str), RTRIM(str.str_nome)
    """)
    
    # Busca na FLE com setor diferente (histórico de ontem/semana)
    fle_hist = query(f"""
        SELECT RTRIM(fle.FLE_STR_COD) AS setor_cod,
               RTRIM(str.str_nome) AS setor_nome,
               COUNT(*) AS chegadas
        FROM fle
        LEFT JOIN str ON str.str_cod = fle.FLE_STR_COD
        WHERE fle.FLE_DTHR_CHEGADA >= DATEADD(day,-7,GETDATE())
          AND (str.str_nome LIKE '%censo%' OR str.str_nome LIKE '%imagem%'
               OR fle.FLE_STR_COD LIKE '%CI%' OR fle.FLE_STR_COD LIKE '%IMG%'
               OR fle.FLE_STR_COD LIKE '%RCI%')
        GROUP BY RTRIM(fle.FLE_STR_COD), RTRIM(str.str_nome)
        ORDER BY chegadas DESC
    """)
    
    # Todos os setores cadastrados
    todos_str = query("""
        SELECT str_cod, RTRIM(str_nome) AS str_nome FROM str
        WHERE str_nome LIKE '%recep%' OR str_nome LIKE '%censo%'
           OR str_nome LIKE '%imagem%' OR str_nome LIKE '%diagno%'
        ORDER BY str_nome
    """)
    
    return {
        "setores_censo_imagem": setores,
        "osm_hoje": osm_censo,
        "fle_historico_7d": fle_hist,
        "recepsoes_cadastradas": todos_str
    }
@app.get("/api/debug/fle-setores")
def debug_fle_setores():
    hoje = datetime.now().strftime("%Y-%m-%d")
    rows = query(f"""
        SELECT
            RTRIM(fle.FLE_STR_COD)      AS setor_cod,
            RTRIM(str.str_nome)          AS setor_nome,
            COUNT(*)                     AS chegadas,
            SUM(CASE WHEN fle.FLE_DTHR_ATENDIMENTO IS NOT NULL THEN 1 ELSE 0 END) AS atendidos,
            AVG(CASE WHEN fle.FLE_DTHR_ATENDIMENTO IS NOT NULL
                     AND DATEDIFF(minute,fle.FLE_DTHR_CHEGADA,fle.FLE_DTHR_ATENDIMENTO) BETWEEN 0 AND 120
                     THEN DATEDIFF(minute,fle.FLE_DTHR_CHEGADA,fle.FLE_DTHR_ATENDIMENTO) END) AS espera_media
        FROM fle
        LEFT JOIN str ON str.str_cod = fle.FLE_STR_COD
        WHERE CAST(fle.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
        GROUP BY RTRIM(fle.FLE_STR_COD), RTRIM(str.str_nome)
        ORDER BY chegadas DESC
    """)
    return rows
@app.get("/api/debug/painel-resumo-raw")
def debug_painel_resumo_raw():
    """Testa cada query do painel individualmente."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    results = {}
    
    # FAT
    try:
        r = query(f"""
            SELECT COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS total_os,
                   COUNT(DISTINCT osm.osm_pac) AS pacientes_unicos,
                   SUM(smm.SMM_VLR) AS faturamento,
                   COUNT(DISTINCT CASE WHEN osm.osm_atend='ASS' THEN osm.osm_serie*1000000+osm.osm_num END) AS assistencial,
                   COUNT(DISTINCT CASE WHEN osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC') THEN osm.osm_serie*1000000+osm.osm_num END) AS ocupacional
            FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
            WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}' AND smm.SMM_SFAT IN ('A','F','P')
        """)
        results["fat"] = r[0] if r else {}
    except Exception as e:
        results["fat_erro"] = str(e)
    
    # ESPERA
    try:
        r = query(f"""
            SELECT AVG(DATEDIFF(minute, fle.FLE_DTHR_CHEGADA, fle.FLE_DTHR_ATENDIMENTO)) AS espera_media_min,
                   COUNT(*) AS total
            FROM fle
            WHERE CAST(fle.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
              AND fle.FLE_DTHR_ATENDIMENTO IS NOT NULL
              AND DATEDIFF(minute, fle.FLE_DTHR_CHEGADA, fle.FLE_DTHR_ATENDIMENTO) BETWEEN 0 AND 120
        """)
        results["espera"] = r[0] if r else {}
    except Exception as e:
        results["espera_erro"] = str(e)
    
    # EM ATENDIMENTO
    try:
        r = query(f"""
            SELECT COUNT(*) AS em_atendimento FROM osm
            WHERE CAST(osm_dthr AS DATE) = '{hoje}' AND osm_dthr_saida IS NULL AND osm_status IS NULL
        """)
        results["em_atend"] = r[0] if r else {}
    except Exception as e:
        results["em_atend_erro"] = str(e)

    # TEMPO
    try:
        r = query(f"""
            SELECT AVG(dur) AS tempo_medio FROM (
                SELECT DATEDIFF(minute, osm_dthr, LEAD(osm_dthr) OVER (PARTITION BY osm_mreq ORDER BY osm_dthr)) AS dur
                FROM osm WHERE CAST(osm_dthr AS DATE) = '{hoje}'
                AND osm_atend IN ('ASS','ADM','PER','DEM','RTB','MDF','MOC')
            ) t WHERE dur BETWEEN 3 AND 120
        """)
        results["tempo"] = r[0] if r else {}
    except Exception as e:
        results["tempo_erro"] = str(e)
    
    return results


@app.get("/api/debug/particular-cnv")
def debug_particular_cnv():
    """Encontra o código do convênio particular."""
    inicio = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    fim    = datetime.now().strftime("%Y-%m-%d")
    
    # Top convênios do assistencial com nome
    rows = query(f"""
        SELECT TOP 10
            RTRIM(cnv.cnv_cod)   AS cnv_cod,
            RTRIM(cnv.cnv_nome)  AS cnv_nome,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS os_count,
            SUM(smm.SMM_VLR)     AS valor
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ('ASS','EME','CRG','TAM')
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY RTRIM(cnv.cnv_cod), RTRIM(cnv.cnv_nome)
        ORDER BY os_count DESC
    """)
    return rows
@app.get("/api/debug/assistencial-esp")
def debug_assistencial_esp():
    """Descobre as especialidades do módulo assistencial para dividir consultas e equipe mult."""
    inicio = (datetime.now().replace(day=1)).strftime("%Y-%m-%d")
    fim    = datetime.now().strftime("%Y-%m-%d")
    
    # SMM_ESP por tipo de atendimento ASS
    por_esp = query(f"""
        SELECT TOP 30
            RTRIM(smm.SMM_ESP)          AS esp_cod,
            RTRIM(esp.esp_nome)         AS esp_nome,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS os_count,
            COUNT(DISTINCT osm.osm_pac) AS pac_count,
            SUM(smm.SMM_VLR)            AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        LEFT JOIN esp ON esp.esp_cod = smm.SMM_ESP
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend = 'ASS'
          AND smm.SMM_SFAT IN ('A','F','P')
          AND smm.SMM_ESP IS NOT NULL
        GROUP BY RTRIM(smm.SMM_ESP), RTRIM(esp.esp_nome)
        ORDER BY os_count DESC
    """)
    
    # SMK codes para entender o que é consulta médica vs equipe mult
    smk_ass = query(f"""
        SELECT TOP 20
            RTRIM(smm.SMM_COD)          AS smk_cod,
            RTRIM(smm.SMM_ESP)          AS esp_cod,
            COUNT(*)                    AS total
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend = 'ASS'
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY RTRIM(smm.SMM_COD), RTRIM(smm.SMM_ESP)
        ORDER BY total DESC
    """)
    
    return {"por_especialidade": por_esp, "por_smk": smk_ass}



@app.get("/api/debug/agenda-malcher")
def debug_agenda_malcher():
    hoje = "2026-06-02"
    
    # Código do médico Antonio Malcher
    med = query("""
        SELECT psv_cod, RTRIM(psv_apel) AS apel, RTRIM(psv_nome) AS nome
        FROM psv WHERE psv_nome LIKE '%MALCHER%' OR psv_apel LIKE '%MALCHER%'
    """)
    
    if not med:
        return {"erro": "Médico não encontrado"}
    
    cod = med[0]["psv_cod"]
    
    # Agendamentos do Antonio hoje
    agm_hoje = query(f"""
        SELECT agm.agm_pac, agm.agm_stat, agm.agm_hini,
               agm.AGM_OSM_SERIE, agm.AGM_OSM_NUM,
               agm.agm_med
        FROM agm
        WHERE CAST(agm_hini AS DATE) = '{hoje}'
          AND agm_med = {cod}
          AND agm_stat != 'B'
        ORDER BY agm_hini
    """)
    
    # OSs do Antonio hoje
    osm_hoje = query(f"""
        SELECT osm.osm_num, osm.osm_dthr, osm.osm_pac,
               osm.osm_mreq, osm.osm_atend, osm.osm_str
        FROM osm
        WHERE CAST(osm_dthr AS DATE) = '{hoje}'
          AND osm_mreq = {cod}
        ORDER BY osm_dthr
    """)
    
    # Cruzamento: agendados com OS pelo paciente
    cruzamento = query(f"""
        SELECT agm.agm_pac, agm.agm_stat, agm.agm_hini,
               osm.osm_num, osm.osm_dthr, osm.osm_mreq,
               agm.agm_med,
               CASE WHEN agm.agm_med = osm.osm_mreq THEN 'MESMO MÉDICO'
                    ELSE 'MÉDICO DIFERENTE' END AS match_medico
        FROM agm
        LEFT JOIN osm ON osm.osm_pac = agm.agm_pac
                     AND CAST(osm.osm_dthr AS DATE) = '{hoje}'
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
          AND agm.agm_med = {cod}
          AND agm.agm_stat != 'B'
        ORDER BY agm.agm_hini
    """)
    
    for r in agm_hoje + osm_hoje + cruzamento:
        for k,v in r.items():
            if hasattr(v,'strftime'): r[k] = v.strftime('%H:%M:%S')
    
    return {
        "medico": med[0],
        "agendamentos_hoje": len(agm_hoje),
        "osm_hoje": len(osm_hoje),
        "agm_amostra": agm_hoje[:5],
        "osm_amostra": osm_hoje[:5],
        "cruzamento_amostra": cruzamento[:10],
    }









@app.get("/api/debug/tipos-servico")
def debug_tipos_servico():
    """Mostra como os serviços estão classificados no banco para entender a separação consulta x exame."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    inicio = (datetime.now() - __import__('datetime').timedelta(days=30)).strftime("%Y-%m-%d")

    # Descobrir colunas reais da SMM
    colunas_smm = query("""
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'smm'
        ORDER BY ORDINAL_POSITION
    """)

    # Sample de SMM com todos os campos para entender estrutura
    sample = query(f"""
        SELECT TOP 5 smm.*
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{hoje} 23:59:59'
          AND osm.osm_atend = 'ASS'
          AND smm.SMM_SFAT IN ('A','F','P')
    """)

    return {{"colunas_smm": colunas_smm, "sample": sample}}

@app.get("/api/debug/malcher-osm-hoje")
def debug_malcher_osm_hoje():
    hoje = datetime.now().strftime("%Y-%m-%d")
    
    # Pacientes agendados com Malcher hoje
    agendados = query(f"""
        SELECT DISTINCT agm.agm_pac, RTRIM(pac.pac_nome) AS nome, agm.agm_hini
        FROM agm
        JOIN psv ON psv.psv_cod = agm.agm_med
        LEFT JOIN pac ON pac.pac_reg = agm.agm_pac
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
          AND RTRIM(psv.psv_apel) LIKE '%MALCHER%'
          AND agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B')
    """)
    
    # OSs de hoje desses pacientes
    pacs = [r["agm_pac"] for r in agendados]
    if not pacs:
        return {"agendados": [], "osm": []}
    
    pacs_str = ",".join(str(p) for p in pacs)
    osms = query(f"""
        SELECT 
            osm.osm_pac, RTRIM(pac.pac_nome) AS nome,
            osm.osm_dthr, osm.osm_mreq,
            RTRIM(psv.psv_apel) AS medico_solicitante,
            RTRIM(osm.osm_str) AS setor, osm.osm_atend
        FROM osm
        LEFT JOIN pac ON pac.pac_reg = osm.osm_pac
        LEFT JOIN psv ON psv.psv_cod = osm.osm_mreq
        WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
          AND osm.osm_pac IN ({pacs_str})
    """)
    
    for r in agendados + osms:
        for k,v in r.items():
            if hasattr(v,'strftime'): r[k] = v.strftime('%H:%M')
    
    return {"agendados_malcher": agendados, "osms_hoje": osms}
@app.get("/api/debug/agend-hoje-detalhado")
def debug_agend_hoje_detalhado():
    hoje = datetime.now().strftime("%Y-%m-%d")
    
    # Total agendamentos hoje na AGM
    total = query(f"""
        SELECT
            COUNT(*) AS total_linhas,
            COUNT(DISTINCT agm.agm_pac) AS pacientes_distintos,
            COUNT(DISTINCT agm.agm_med) AS medicos,
            SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B') THEN 1 ELSE 0 END) AS marcacoes_validas
        FROM agm
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
    """)
    
    # O que o LEFT JOIN de osm_match encontra
    match = query(f"""
        SELECT
            COUNT(*) AS agm_total,
            SUM(CASE WHEN om.osm_pac IS NOT NULL THEN 1 ELSE 0 END) AS com_os_match,
            SUM(CASE WHEN om.osm_pac IS NULL THEN 1 ELSE 0 END) AS sem_os_match
        FROM agm
        LEFT JOIN (
            SELECT DISTINCT osm_pac, CAST(osm_dthr AS DATE) AS osm_data
            FROM osm WHERE CAST(osm_dthr AS DATE) = '{hoje}'
        ) om ON om.osm_pac = agm.agm_pac
             AND om.osm_data = CAST(agm.agm_hini AS DATE)
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
          AND agm.agm_pac > 0
          AND agm.agm_stat NOT IN ('C','B')
    """)
    
    # Quantas OSs foram abertas hoje para pacientes agendados
    osm_agendados = query(f"""
        SELECT COUNT(DISTINCT osm.osm_pac) AS pac_com_os
        FROM osm
        WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
          AND osm.osm_pac IN (
              SELECT DISTINCT agm.agm_pac FROM agm
              WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
                AND agm.agm_pac > 0
                AND agm.agm_stat NOT IN ('C','B')
          )
    """)
    
    return {
        "agm_hoje": total[0] if total else {},
        "os_match": match[0] if match else {},
        "pac_com_os_hoje": osm_agendados[0] if osm_agendados else {},
    }
@app.get("/api/debug/agend-match")
def debug_agend_match():
    inicio = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    fim    = datetime.now().strftime("%Y-%m-%d")

    # Testa match via osm_mreq vs osm_atend
    r1 = query(f"""
        SELECT COUNT(*) AS match_mreq
        FROM agm
        JOIN osm ON osm.osm_pac  = agm.agm_pac
                AND osm.osm_mreq = agm.agm_med
                AND CAST(osm.osm_dthr AS DATE) = CAST(agm.agm_hini AS DATE)
        WHERE agm.agm_hini BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B')
    """)

    # Testa match via osm_atend (médico executante)
    r2 = query(f"""
        SELECT COUNT(*) AS match_atend
        FROM agm
        JOIN osm ON osm.osm_pac   = agm.agm_pac
                AND osm.osm_atend_psv = agm.agm_med
                AND CAST(osm.osm_dthr AS DATE) = CAST(agm.agm_hini AS DATE)
        WHERE agm.agm_hini BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B')
    """) if False else [{"match_atend": "col nao existe"}]

    # Testa match apenas pac+data (sem médico)
    r3 = query(f"""
        SELECT COUNT(DISTINCT agm.agm_pac) AS match_pac_data
        FROM agm
        JOIN osm ON osm.osm_pac = agm.agm_pac
                AND CAST(osm.osm_dthr AS DATE) = CAST(agm.agm_hini AS DATE)
        WHERE agm.agm_hini BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B')
    """)

    # Colunas da OSM para ver qual tem o médico executante
    osm_cols = query("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='osm' AND COLUMN_NAME LIKE '%med%'
           OR TABLE_NAME='osm' AND COLUMN_NAME LIKE '%exec%'
           OR TABLE_NAME='osm' AND COLUMN_NAME LIKE '%psv%'
        ORDER BY COLUMN_NAME
    """)

    return {
        "match_via_mreq": r1[0] if r1 else {},
        "match_pac_data_only": r3[0] if r3 else {},
        "osm_colunas_medico": [r["COLUMN_NAME"] for r in osm_cols],
    }
@app.get("/api/debug/agend-stats-raw")
def debug_agend_stats_raw():
    """Mostra os valores brutos do stats de agendamentos."""
    from datetime import datetime, date
    hoje = datetime.now().strftime("%Y-%m-%d")
    inicio = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    fim = hoje

    rows = query(f"""
        SELECT
            COUNT(*) AS total_linhas,
            SUM(CASE WHEN agm.agm_pac IS NOT NULL AND agm.agm_pac > 0 THEN 1 ELSE 0 END) AS com_pac,
            SUM(CASE WHEN agm.agm_pac IS NOT NULL AND agm.agm_pac > 0
                      AND agm.agm_stat NOT IN ('C','B') THEN 1 ELSE 0 END) AS marcacoes,
            SUM(CASE WHEN agm.agm_stat='C' AND agm.agm_pac > 0 THEN 1 ELSE 0 END) AS cancelados,
            SUM(CASE WHEN agm.agm_pac IS NOT NULL AND agm.agm_pac > 0
                      AND agm.agm_stat NOT IN ('C','B','E')
                      AND agm.AGM_OSM_SERIE IS NULL
                      AND om.osm_pac IS NULL THEN 1 ELSE 0 END) AS faltantes_raw,
            SUM(CASE WHEN agm.agm_pac IS NOT NULL AND agm.agm_pac > 0
                      AND agm.agm_stat NOT IN ('C','B')
                      AND (agm.agm_stat='E' OR agm.AGM_OSM_SERIE IS NOT NULL
                           OR om.osm_pac IS NOT NULL) THEN 1 ELSE 0 END) AS atendidos_raw
        FROM agm
        LEFT JOIN (
            SELECT DISTINCT osm_pac, CAST(osm_dthr AS DATE) AS osm_data
            FROM osm WHERE osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
        ) om ON om.osm_pac=agm.agm_pac
             AND om.osm_data=CAST(agm.agm_hini AS DATE)
        WHERE agm.agm_hini BETWEEN '{inicio}' AND '{fim} 23:59:59'
    """)
    return rows[0] if rows else {}
@app.get("/api/debug/ex-hor-situacao")
def debug_ex_hor_situacao():
    inicio = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    fim    = datetime.now().strftime("%Y-%m-%d")
    sits = query(f"""
        SELECT DISTINCT SITUACAO, COUNT(*) AS n
        FROM EX_HORARIOS
        WHERE HOR_DATA BETWEEN '{inicio}' AND '{fim}'
        GROUP BY SITUACAO ORDER BY n DESC
    """)
    return sits
@app.get("/api/debug/agd-vagas")
def debug_agd_vagas():
    """Busca vagas disponíveis nas tabelas de grade de horários."""
    inicio = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    fim    = datetime.now().strftime("%Y-%m-%d")
    
    # Tenta EX_HORARIOS (view que já vimos com dados)
    try:
        ex_hor = query(f"""
            SELECT TOP 5
                HOR_MED, HOR_DIA, SITUACAO, HORARIO_INICIO, PERIODO, HOR_DATA
            FROM EX_HORARIOS
            WHERE HOR_DATA BETWEEN '{inicio}' AND '{fim}'
        """)
        for r in ex_hor:
            for k,v in r.items():
                if hasattr(v,'strftime'): r[k] = v.strftime('%Y-%m-%d')
    except Exception as e:
        ex_hor = {"erro": str(e)[:100]}
    
    # Tenta AGD
    try:
        agd = query(f"""
            SELECT TOP 3
                AGD_MED, AGD_DT, AGD_NUM, AGD_MAT, AGD_VESP
            FROM AGD
            WHERE CAST(AGD_DT AS DATE) BETWEEN '{inicio}' AND '{fim}'
        """)
        for r in agd:
            for k,v in r.items():
                if hasattr(v,'strftime'): r[k] = v.strftime('%Y-%m-%d')
    except Exception as e:
        agd = {"erro": str(e)[:100]}
    
    # Conta vagas via EX_HORARIOS por médico
    try:
        vagas = query(f"""
            SELECT TOP 10
                eh.HOR_MED,
                RTRIM(psv.psv_apel) AS medico,
                COUNT(*) AS total_slots,
                SUM(CASE WHEN eh.SITUACAO = 'D' THEN 1 ELSE 0 END) AS disponiveis,
                SUM(CASE WHEN eh.SITUACAO = 'A' THEN 1 ELSE 0 END) AS agendados,
                SUM(CASE WHEN eh.SITUACAO = 'B' THEN 1 ELSE 0 END) AS bloqueados
            FROM EX_HORARIOS eh
            LEFT JOIN psv ON psv.psv_cod = eh.HOR_MED
            WHERE eh.HOR_DATA BETWEEN '{inicio}' AND '{fim}'
            GROUP BY eh.HOR_MED, RTRIM(psv.psv_apel)
            ORDER BY total_slots DESC
        """)
    except Exception as e:
        vagas = {"erro": str(e)[:100]}
    
    return {
        "ex_horarios_amostra": ex_hor,
        "agd_amostra": agd,
        "vagas_por_medico": vagas,
    }
@app.get("/api/debug/agm-vagas")
def debug_agm_vagas():
    """Verifica se slots vazios existem na AGM."""
    inicio = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    fim    = datetime.now().strftime("%Y-%m-%d")
    
    rows = query(f"""
        SELECT TOP 5
            agm.agm_pac,
            agm.agm_stat,
            agm.agm_hini,
            agm.agm_med
        FROM agm
        WHERE agm.agm_hini BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND (agm.agm_pac IS NULL OR agm.agm_pac = 0)
    """)
    
    count = query(f"""
        SELECT 
            COUNT(*) AS total,
            SUM(CASE WHEN agm_pac IS NULL THEN 1 ELSE 0 END) AS pac_null,
            SUM(CASE WHEN agm_pac = 0    THEN 1 ELSE 0 END) AS pac_zero,
            SUM(CASE WHEN agm_pac > 0    THEN 1 ELSE 0 END) AS com_pac
        FROM agm
        WHERE agm_hini BETWEEN '{inicio}' AND '{fim} 23:59:59'
    """)
    
    for r in rows:
        for k,v in r.items():
            if hasattr(v,'strftime'): r[k] = v.strftime('%H:%M')
    
    return {"contagem": count[0] if count else {}, "amostra_vazios": rows}
@app.get("/api/debug/agenda-antonio")
def debug_agenda_antonio():
    """Valida dados da agenda do Antonio Malcher em 02/06/2026."""
    data = "2026-06-02"
    
    # Todos os agendamentos do Antonio
    rows = query(f"""
        SELECT
            agm.agm_hini, agm.agm_stat,
            agm.agm_pac,
            RTRIM(pac.pac_nome) AS paciente,
            agm.AGM_OSM_SERIE, agm.AGM_OSM_NUM,
            agm.AGM_SMK  AS servico
        FROM agm
        JOIN psv ON psv.psv_cod = agm.agm_med
        LEFT JOIN pac ON pac.pac_reg = agm.agm_pac
        WHERE CAST(agm.agm_hini AS DATE) = '{data}'
          AND RTRIM(psv.psv_apel) LIKE '%ANTONIO%MALCH%'
        ORDER BY agm.agm_hini
    """)
    
    # Contagem resumida
    resumo = query(f"""
        SELECT
            COUNT(*) AS total_slots,
            SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_pac IS NOT NULL THEN 1 ELSE 0 END) AS com_paciente,
            SUM(CASE WHEN agm.agm_pac IS NULL OR agm.agm_pac = 0 THEN 1 ELSE 0 END) AS vazio,
            SUM(CASE WHEN agm.agm_stat = 'C' THEN 1 ELSE 0 END) AS cancelados,
            SUM(CASE WHEN agm.agm_stat = 'E' THEN 1 ELSE 0 END) AS executados,
            SUM(CASE WHEN agm.agm_stat = 'A' AND agm.agm_pac > 0 THEN 1 ELSE 0 END) AS marcados_abertos
        FROM agm
        JOIN psv ON psv.psv_cod = agm.agm_med
        WHERE CAST(agm.agm_hini AS DATE) = '{data}'
          AND RTRIM(psv.psv_apel) LIKE '%ANTONIO%MALCH%'
    """)
    
    for r in rows:
        if hasattr(r.get("agm_hini"),"strftime"): r["agm_hini"] = r["agm_hini"].strftime("%H:%M")
    
    return {"resumo": resumo[0] if resumo else {}, "slots": rows}
@app.get("/api/debug/agenda-osm-link")
def debug_agenda_osm_link():
    hoje = datetime.now().strftime("%Y-%m-%d")
    
    # 1. AGM com AGM_OSM_SERIE preenchido hoje
    com_osm = query(f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN AGM_OSM_SERIE IS NOT NULL THEN 1 ELSE 0 END) AS com_osm_vinculado
        FROM agm WHERE CAST(agm_hini AS DATE) = '{hoje}'
    """)
    
    # 2. Amostra AGM de hoje com OS vinculada diretamente
    vinculados = query(f"""
        SELECT TOP 5
            agm.agm_pac, agm.agm_stat, agm.agm_hini,
            agm.AGM_OSM_SERIE, agm.AGM_OSM_NUM,
            osm.osm_dthr, osm.osm_atend
        FROM agm
        JOIN osm ON osm.osm_serie = agm.AGM_OSM_SERIE
                AND osm.osm_num   = agm.AGM_OSM_NUM
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
    """)
    
    # 3. OSs de hoje sem agm vinculado (AGM_OSM_SERIE NULL na agm)
    osm_sem_agm = query(f"""
        SELECT COUNT(*) AS osm_sem_agendamento
        FROM osm
        WHERE CAST(osm_dthr AS DATE) = '{hoje}'
          AND NOT EXISTS (
            SELECT 1 FROM agm 
            WHERE agm.AGM_OSM_SERIE = osm.osm_serie
              AND agm.AGM_OSM_NUM   = osm.osm_num
          )
    """)
    
    # 4. AGMs de hoje que têm OS vinculada pelo pac mas não pelo campo AGM_OSM
    agm_pac_match = query(f"""
        SELECT TOP 5
            agm.agm_pac, agm.agm_stat,
            agm.agm_hini, agm.AGM_OSM_SERIE,
            osm.osm_num, osm.osm_dthr, osm.osm_atend
        FROM agm
        JOIN osm ON osm.osm_pac = agm.agm_pac
                AND CAST(osm.osm_dthr AS DATE) = '{hoje}'
                AND ABS(DATEDIFF(minute, agm.agm_hini, osm.osm_dthr)) < 120
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
          AND agm.AGM_OSM_SERIE IS NULL
    """)
    
    for r in vinculados + agm_pac_match:
        for k,v in r.items():
            if hasattr(v,'strftime'): r[k] = v.strftime('%H:%M:%S')
    
    return {
        "total_agm_hoje":    com_osm[0] if com_osm else {},
        "vinculados_direto": vinculados,
        "osm_sem_agm":       osm_sem_agm[0] if osm_sem_agm else {},
        "agm_pac_match":     agm_pac_match,
    }
@app.get("/api/debug/agenda-validacao")
def debug_agenda_validacao():
    """Valida inconsistências entre AGM e OSM — pacientes atendidos mas agenda não confirmada."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    inicio_mes = datetime.now().replace(day=1).strftime("%Y-%m-%d")

    # 1. Agendamentos de hoje por status
    agm_status = query(f"""
        SELECT
            agm.agm_stat,
            COUNT(*) AS total
        FROM agm
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
        GROUP BY agm.agm_stat
        ORDER BY total DESC
    """)

    # 2. Pacientes com OS hoje MAS agenda ainda como 'A' (aguardando)
    # = paciente foi atendido mas agenda não foi confirmada
    inconsistentes = query(f"""
        SELECT TOP 10
            RTRIM(pac.pac_nome)             AS paciente,
            agm.agm_hini                    AS hora_agendada,
            osm.osm_dthr                    AS hora_os,
            agm.agm_stat                    AS stat_agenda,
            RTRIM(psv.psv_apel)             AS medico,
            osm.osm_atend                   AS tipo_atend,
            agm.AGM_OSM_SERIE               AS agm_osm_serie,
            agm.AGM_OSM_NUM                 AS agm_osm_num
        FROM agm
        JOIN osm ON osm.osm_pac = agm.agm_pac
                AND CAST(osm.osm_dthr AS DATE) = '{hoje}'
        LEFT JOIN pac ON pac.pac_reg = agm.agm_pac
        LEFT JOIN psv ON psv.psv_cod = agm.agm_med
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
          AND agm.agm_stat = 'A'                -- agenda ainda aguardando
          AND agm.AGM_OSM_SERIE IS NULL          -- sem vínculo direto de OS
          AND osm.osm_dthr IS NOT NULL           -- mas tem OS gerada hoje
        ORDER BY agm.agm_hini
    """)

    # 3. Comparativo: agendados vs atendidos
    comparativo = query(f"""
        SELECT
            COUNT(DISTINCT agm.agm_pac)                                     AS agendados,
            COUNT(DISTINCT CASE WHEN agm.agm_stat IN ('E','F') 
                THEN agm.agm_pac END)                                       AS confirmados_agenda,
            COUNT(DISTINCT CASE WHEN osm.osm_pac IS NOT NULL 
                THEN agm.agm_pac END)                                       AS com_os_gerada,
            COUNT(DISTINCT CASE WHEN agm.agm_stat = 'A' 
                AND osm.osm_pac IS NOT NULL THEN agm.agm_pac END)           AS inconsistentes
        FROM agm
        LEFT JOIN osm ON osm.osm_pac = agm.agm_pac
                     AND CAST(osm.osm_dthr AS DATE) = '{hoje}'
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
    """)

    # 4. AGM_STAT possíveis valores
    todos_stat = query(f"""
        SELECT DISTINCT agm_stat, COUNT(*) AS n
        FROM agm
        WHERE CAST(agm_hini AS DATE) >= '{inicio_mes}'
        GROUP BY agm_stat
        ORDER BY n DESC
    """)

    for r in inconsistentes:
        for k,v in r.items():
            if hasattr(v,'strftime'): r[k] = v.strftime('%H:%M')

    return {
        "agm_status_hoje":    agm_status,
        "comparativo":        comparativo[0] if comparativo else {},
        "inconsistentes_amostra": inconsistentes,
        "todos_status_mes":   todos_stat,
    }
@app.get("/api/debug/painel-check")
def debug_painel_check():
    hoje = datetime.now().strftime("%Y-%m-%d")
    
    # 1. FLE hoje
    fle = query(f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN FLE_DTHR_ATENDIMENTO IS NOT NULL THEN 1 ELSE 0 END) AS atendidos,
               AVG(CASE WHEN FLE_DTHR_ATENDIMENTO IS NOT NULL
                        AND DATEDIFF(minute,FLE_DTHR_CHEGADA,FLE_DTHR_ATENDIMENTO) BETWEEN 0 AND 120
                        THEN DATEDIFF(minute,FLE_DTHR_CHEGADA,FLE_DTHR_ATENDIMENTO) END) AS espera_media
        FROM fle WHERE CAST(FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
    """)
    
    # 2. Por setor na FLE
    por_setor = query(f"""
        SELECT TOP 5 RTRIM(FLE_STR_COD) AS setor, COUNT(*) AS n
        FROM fle WHERE CAST(FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
        GROUP BY RTRIM(FLE_STR_COD) ORDER BY n DESC
    """)
    
    # 3. OSM hoje
    osm = query(f"""
        SELECT COUNT(*) AS total FROM osm
        WHERE CAST(osm_dthr AS DATE) = '{hoje}'
    """)
    
    # 4. Faturamento hoje (para ver se a query quebra)
    try:
        fat = query(f"""
            SELECT COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS total_os,
                   SUM(smm.SMM_VLR) AS fat
            FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num
            WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
              AND smm.SMM_SFAT IN ('A','F','P')
        """)
        fat_ok = fat[0] if fat else {}
    except Exception as e:
        fat_ok = {"erro": str(e)}
    
    return {
        "hoje": hoje,
        "fle_total": fle[0] if fle else {},
        "fle_por_setor": por_setor,
        "osm_hoje": osm[0] if osm else {},
        "faturamento": fat_ok,
    }
@app.get("/api/debug/fila-hoje")
def debug_fila_hoje():
    """Varre TODAS as tabelas com datetime que têm dados de hoje."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    
    # Pega todas as tabelas com colunas datetime
    todas_tabs = query("""
        SELECT DISTINCT t.TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES t
        JOIN INFORMATION_SCHEMA.COLUMNS c ON c.TABLE_NAME = t.TABLE_NAME
        WHERE t.TABLE_TYPE = 'BASE TABLE'
          AND c.DATA_TYPE IN ('datetime','datetime2','smalldatetime')
        ORDER BY t.TABLE_NAME
    """)
    
    com_dados_hoje = {}
    
    for row in todas_tabs:
        tab = row["TABLE_NAME"]
        try:
            # Pega colunas datetime dessa tabela
            dt_cols = query(f"""
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='{tab}'
                  AND DATA_TYPE IN ('datetime','datetime2','smalldatetime')
                ORDER BY ORDINAL_POSITION
            """)
            if not dt_cols:
                continue
            
            dt_col = dt_cols[0]["COLUMN_NAME"]
            
            # Conta registros de hoje
            cnt = query(f"""
                SELECT COUNT(*) AS total FROM {tab}
                WHERE CAST({dt_col} AS DATE) = '{hoje}'
            """)
            total = cnt[0]["total"] if cnt else 0
            
            if total > 0:
                # Pega todas as colunas
                all_cols = query(f"""
                    SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='{tab}' ORDER BY ORDINAL_POSITION
                """)
                col_names = [c["COLUMN_NAME"] for c in all_cols]
                sample = query(f"""
                    SELECT TOP 2 {', '.join(col_names[:10])} FROM {tab}
                    WHERE CAST({dt_col} AS DATE) = '{hoje}'
                    ORDER BY {dt_col} DESC
                """)
                for r in sample:
                    for k,v in r.items():
                        if hasattr(v,'strftime'): r[k]=v.strftime('%H:%M:%S')
                
                com_dados_hoje[tab] = {
                    "total_hoje": total,
                    "colunas": col_names,
                    "amostra": sample
                }
        except:
            pass
    
    return com_dados_hoje
@app.get("/api/debug/espera-setor")
def debug_espera_setor():
    hoje = datetime.now().strftime("%Y-%m-%d")
    
    # Quantos agendamentos vinculados a OS existem hoje, por setor
    por_setor = query(f"""
        SELECT
            RTRIM(osm.osm_str)                                          AS setor_cod,
            RTRIM(str.str_nome)                                         AS setor_nome,
            COUNT(*)                                                     AS pares,
            AVG(DATEDIFF(minute, agm.agm_hini, osm.osm_dthr))          AS espera_media,
            MIN(DATEDIFF(minute, agm.agm_hini, osm.osm_dthr))          AS espera_min,
            MAX(DATEDIFF(minute, agm.agm_hini, osm.osm_dthr))          AS espera_max
        FROM agm
        JOIN osm ON osm.osm_serie = agm.AGM_OSM_SERIE
                AND osm.osm_num   = agm.AGM_OSM_NUM
        LEFT JOIN str ON str.str_cod = osm.osm_str
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
          AND agm.agm_stat IN ('E','F')
          AND agm.AGM_OSM_SERIE IS NOT NULL
          AND DATEDIFF(minute, agm.agm_hini, osm.osm_dthr) BETWEEN 0 AND 120
        GROUP BY RTRIM(osm.osm_str), RTRIM(str.str_nome)
        ORDER BY pares DESC
    """)
    
    # Total sem filtro
    total = query(f"""
        SELECT COUNT(*) AS total,
               AVG(DATEDIFF(minute, agm.agm_hini, osm.osm_dthr)) AS espera_media_geral
        FROM agm
        JOIN osm ON osm.osm_serie = agm.AGM_OSM_SERIE
                AND osm.osm_num   = agm.AGM_OSM_NUM
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
          AND agm.agm_stat IN ('E','F')
          AND agm.AGM_OSM_SERIE IS NOT NULL
          AND DATEDIFF(minute, agm.agm_hini, osm.osm_dthr) BETWEEN 0 AND 120
    """)
    
    return {"por_setor": por_setor, "total_geral": total[0] if total else {}}
@app.get("/api/debug/smk-senha")
def debug_smk_senha():
    hoje = datetime.now().strftime("%Y-%m-%d")
    
    # Busca TODAS as tabelas que têm colunas de datetime e contêm "smk" ou "senha" ou "fila"
    todas = query("""
        SELECT DISTINCT t.TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES t
        JOIN INFORMATION_SCHEMA.COLUMNS c ON c.TABLE_NAME = t.TABLE_NAME
        WHERE t.TABLE_TYPE = 'BASE TABLE'
          AND c.DATA_TYPE IN ('datetime','datetime2','smalldatetime')
          AND (
            t.TABLE_NAME LIKE '%smk%' OR t.TABLE_NAME LIKE '%sen%'
            OR t.TABLE_NAME LIKE '%cha%' OR t.TABLE_NAME LIKE '%aten%'
            OR t.TABLE_NAME LIKE '%fila%' OR t.TABLE_NAME LIKE '%call%'
            OR t.TABLE_NAME LIKE '%queue%' OR t.TABLE_NAME LIKE '%ticket%'
          )
        ORDER BY t.TABLE_NAME
    """)
    
    results = {}
    for row in todas:
        tab = row["TABLE_NAME"]
        try:
            cols = query(f"""
                SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='{tab}' ORDER BY ORDINAL_POSITION
            """)
            col_names = [c["COLUMN_NAME"] for c in cols]
            dt_cols   = [c["COLUMN_NAME"] for c in cols
                         if c["DATA_TYPE"] in ("datetime","datetime2","smalldatetime")]
            
            rows = query(f"""
                SELECT TOP 2 {', '.join(col_names[:8])}
                FROM {tab}
                WHERE CAST({dt_cols[0]} AS DATE) = '{hoje}'
                ORDER BY {dt_cols[0]} DESC
            """) if dt_cols else []
            
            for r in rows:
                for k, v in r.items():
                    if hasattr(v,'strftime'): r[k] = v.strftime('%H:%M:%S')
            
            if rows:  # só mostra se tiver dados hoje
                results[tab] = {
                    "colunas": col_names,
                    "amostra_hoje": rows
                }
        except:
            pass
    
    # Também tenta tabelas genéricas com padrão de chamada
    for tab in ["BCS_SMKPAD","PSV_SMK","TAP_SMK","HC_TPA_SMK","ENC_LAB_EXT_SMKS"]:
        try:
            cols = query(f"SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{tab}' ORDER BY ORDINAL_POSITION")
            col_names = [c["COLUMN_NAME"] for c in cols]
            dt_cols   = [c["COLUMN_NAME"] for c in cols if c["DATA_TYPE"] in ("datetime","datetime2","smalldatetime")]
            if dt_cols:
                rows = query(f"SELECT TOP 2 {', '.join(col_names[:8])} FROM {tab} WHERE CAST({dt_cols[0]} AS DATE)='{hoje}' ORDER BY {dt_cols[0]} DESC")
                for r in rows:
                    for k,v in r.items():
                        if hasattr(v,'strftime'): r[k]=v.strftime('%H:%M:%S')
                if rows: results[tab] = {"colunas": col_names, "amostra_hoje": rows}
            else:
                rows = query(f"SELECT TOP 1 {', '.join(col_names[:6])} FROM {tab}")
                if rows: results[tab] = {"colunas": col_names, "sem_data": rows}
        except:
            pass
    
    return results or {"msg": "nenhuma tabela SMK com dados hoje encontrada"}
@app.get("/api/debug/smk-chamada")
def debug_smk_chamada():
    hoje = datetime.now().strftime("%Y-%m-%d")

    results = {}
    
    # Tabelas candidatas com suas colunas e amostras de hoje
    for tabela in ["CSMK", "SMK_PRX", "SMK_LOC", "SMK_STR", "ATL_GRP_SMK", "ord_smk"]:
        try:
            cols = query(f"""
                SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='{tabela}' ORDER BY ORDINAL_POSITION
            """)
            col_names = [c["COLUMN_NAME"] for c in cols]
            if not col_names:
                results[tabela] = "vazia/sem colunas"
                continue
            
            # Tentar buscar registros de hoje
            # Procurar colunas de data/hora
            dt_cols = [c["COLUMN_NAME"] for c in cols
                       if c["DATA_TYPE"] in ("datetime","datetime2","smalldatetime")
                       or "dthr" in c["COLUMN_NAME"].lower()
                       or "data" in c["COLUMN_NAME"].lower()
                       or "hora" in c["COLUMN_NAME"].lower()
                       or "hini" in c["COLUMN_NAME"].lower()]
            
            sample_cols = col_names[:10]
            if dt_cols:
                rows = query(f"""
                    SELECT TOP 3 {', '.join(sample_cols)}
                    FROM {tabela}
                    WHERE CAST({dt_cols[0]} AS DATE) = '{hoje}'
                    ORDER BY {dt_cols[0]} DESC
                """)
            else:
                rows = query(f"SELECT TOP 3 {', '.join(sample_cols)} FROM {tabela}")
            
            for r in rows:
                for k, v in r.items():
                    if hasattr(v, 'strftime'): r[k] = v.strftime('%H:%M:%S')
            
            results[tabela] = {
                "colunas": [(c["COLUMN_NAME"], c["DATA_TYPE"]) for c in cols],
                "amostra": rows
            }
        except Exception as e:
            results[tabela] = {"erro": str(e)[:200]}
    
    return results
@app.get("/api/debug/fila-totem")
def debug_fila_totem():
    hoje = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Estrutura completa da tabela fil
    fil_cols = query("""
        SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='fil' ORDER BY ORDINAL_POSITION
    """)
    
    # 2. Amostra de hoje (sem filtro de data em INT)
    # fil provavelmente tem uma coluna de data/hora
    fil_sample = []
    col_names = [c["COLUMN_NAME"] for c in fil_cols]
    if col_names:
        try:
            # Pegar top 3 sem filtro de data
            fil_sample = query(f"SELECT TOP 3 {', '.join(col_names[:12])} FROM fil ORDER BY 1 DESC")
        except Exception as e:
            fil_sample = [{"erro": str(e)}]
    
    # 3. Tabela PSV_FILA - fila por prestador
    psv_fila_cols = query("""
        SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='PSV_FILA' ORDER BY ORDINAL_POSITION
    """)
    psv_fila_sample = []
    try:
        cols = [c["COLUMN_NAME"] for c in psv_fila_cols[:10]]
        if cols:
            psv_fila_sample = query(f"SELECT TOP 3 {', '.join(cols)} FROM PSV_FILA ORDER BY 1 DESC")
    except Exception as e:
        psv_fila_sample = [{"erro": str(e)}]

    # 4. Tabela smkinst - instâncias do SMK (sistema de senhas)
    smkinst_cols = query("""
        SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='smkinst' ORDER BY ORDINAL_POSITION
    """)
    smkinst_sample = []
    try:
        cols = [c["COLUMN_NAME"] for c in smkinst_cols[:10]]
        if cols:
            smkinst_sample = query(f"SELECT TOP 3 {', '.join(cols)} FROM smkinst ORDER BY 1 DESC")
    except Exception as e:
        smkinst_sample = [{"erro": str(e)}]

    # 5. Tabela agm_smk - vínculo agendamento x senha
    agm_smk_cols = query("""
        SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='agm_smk' ORDER BY ORDINAL_POSITION
    """)
    agm_smk_sample = []
    try:
        cols = [c["COLUMN_NAME"] for c in agm_smk_cols[:10]]
        if cols:
            agm_smk_sample = query(f"SELECT TOP 5 {', '.join(cols)} FROM agm_smk ORDER BY 1 DESC")
    except Exception as e:
        agm_smk_sample = [{"erro": str(e)}]

    return {
        "fil_colunas": [(c["COLUMN_NAME"], c["DATA_TYPE"]) for c in fil_cols],
        "fil_amostra": fil_sample,
        "psv_fila_colunas": [(c["COLUMN_NAME"], c["DATA_TYPE"]) for c in psv_fila_cols],
        "psv_fila_amostra": psv_fila_sample,
        "smkinst_colunas": [(c["COLUMN_NAME"], c["DATA_TYPE"]) for c in smkinst_cols],
        "smkinst_amostra": smkinst_sample,
        "agm_smk_colunas": [(c["COLUMN_NAME"], c["DATA_TYPE"]) for c in agm_smk_cols],
        "agm_smk_amostra": agm_smk_sample,
    }
@app.get("/api/debug/espera")
def debug_espera():
    hoje = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Total agendamentos executados hoje
    agm_hoje = query(f"""
        SELECT COUNT(*) AS total, 
               SUM(CASE WHEN agm_stat='E' THEN 1 ELSE 0 END) AS executados,
               SUM(CASE WHEN agm_stat='F' THEN 1 ELSE 0 END) AS finalizados
        FROM agm WHERE CAST(agm_hini AS DATE) = '{hoje}'
    """)
    
    # 2. Amostra do JOIN agm + osm
    join_sample = query(f"""
        SELECT TOP 5
            agm.agm_pac, agm.agm_stat,
            agm.agm_hini, osm.osm_dthr,
            DATEDIFF(minute, agm.agm_hini, osm.osm_dthr) AS espera_min,
            osm.osm_atend
        FROM agm
        JOIN osm ON osm.osm_pac = agm.agm_pac
                AND CAST(osm.osm_dthr AS DATE) = '{hoje}'
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
          AND agm.agm_stat IN ('E','F')
        ORDER BY agm.agm_hini
    """)
    
    # 3. Quantos pares válidos existem
    pares = query(f"""
        SELECT COUNT(*) AS pares,
               AVG(DATEDIFF(minute, agm.agm_hini, osm.osm_dthr)) AS media
        FROM agm
        JOIN osm ON osm.osm_pac = agm.agm_pac
                AND CAST(osm.osm_dthr AS DATE) = '{hoje}'
                AND ABS(DATEDIFF(minute, agm.agm_hini, osm.osm_dthr)) < 240
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
          AND agm.agm_stat IN ('E','F')
    """)
    
    # 4. AGM tem coluna de OSM vinculada diretamente?
    agm_osm_cols = query("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='agm'
          AND (COLUMN_NAME LIKE '%osm%' OR COLUMN_NAME LIKE '%os%'
               OR COLUMN_NAME LIKE '%atend%' OR COLUMN_NAME LIKE '%ini%'
               OR COLUMN_NAME LIKE '%fim%' OR COLUMN_NAME LIKE '%dur%'
               OR COLUMN_NAME LIKE '%espera%' OR COLUMN_NAME LIKE '%wait%')
        ORDER BY ORDINAL_POSITION
    """)
    
    for r in join_sample:
        for f in ['agm_hini','osm_dthr']:
            if hasattr(r.get(f),'strftime'): r[f] = r[f].strftime('%H:%M:%S')
    
    return {
        "agm_hoje": agm_hoje[0] if agm_hoje else {},
        "join_sample": join_sample,
        "pares_validos": pares[0] if pares else {},
        "agm_colunas_hora": [c["COLUMN_NAME"] for c in agm_osm_cols],
    }
@app.get("/api/debug/tempo-espera")
def debug_tempo_espera():
    """Descobre como medir tempo de espera no Pixeon."""
    hoje = datetime.now().strftime("%Y-%m-%d")

    # 1. Tabelas com hora de chegada/chamada
    tabs = query("""
        SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE='BASE TABLE'
          AND (TABLE_NAME LIKE '%fil%' OR TABLE_NAME LIKE '%sen%'
               OR TABLE_NAME LIKE '%cha%' OR TABLE_NAME LIKE '%wait%'
               OR TABLE_NAME LIKE '%queue%' OR TABLE_NAME LIKE '%fila%')
        ORDER BY TABLE_NAME
    """)

    # 2. Colunas da tabela fil (fila)
    fil_cols = []
    try:
        cols = query("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='fil' ORDER BY ORDINAL_POSITION")
        fil_cols = [c["COLUMN_NAME"] for c in cols]
        fil_sample = query(f"SELECT TOP 3 {', '.join(fil_cols[:8])} FROM fil WHERE CAST(fil.{fil_cols[0]} AS DATE) = '{hoje}'") if fil_cols else []
    except Exception as e:
        fil_cols = [str(e)]
        fil_sample = []

    # 3. Colunas da tabela smk_fil
    smkfil_cols = []
    try:
        cols = query("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='smk_fil' ORDER BY ORDINAL_POSITION")
        smkfil_cols = [c["COLUMN_NAME"] for c in cols]
    except Exception as e:
        smkfil_cols = [str(e)]

    # 4. OS tem hora de abertura (osm_dthr) — diferença com agm_hini = espera?
    espera_agm = query(f"""
        SELECT TOP 5
            RTRIM(psv.psv_apel) AS medico,
            agm.agm_hini AS hora_agendada,
            osm.osm_dthr AS hora_os_abertura,
            DATEDIFF(minute, agm.agm_hini, osm.osm_dthr) AS min_atraso
        FROM osm
        JOIN agm ON agm.agm_pac = osm.osm_pac
                AND CAST(agm.agm_hini AS DATE) = '{hoje}'
        LEFT JOIN psv ON psv.psv_cod = osm.osm_mreq
        WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
          AND osm.osm_atend = 'ASS'
        ORDER BY osm.osm_dthr DESC
    """)

    # 5. Campos de hora na OSM ligados a recepção
    osm_hora = query(f"""
        SELECT TOP 5
            osm_dthr,
            OSM_HORA_ESP,
            osm_dthr_saida,
            osm_status,
            osm_atend
        FROM osm
        WHERE CAST(osm_dthr AS DATE) = '{hoje}'
          AND OSM_HORA_ESP IS NOT NULL
        ORDER BY osm_dthr DESC
    """)

    return {
        "tabelas_fila": [r["TABLE_NAME"] for r in tabs],
        "fil_colunas": fil_cols,
        "smk_fil_colunas": smkfil_cols,
        "espera_via_agm_os": espera_agm,
        "osm_hora_esp": osm_hora,
    }

@app.get("/api/debug/painel-tv")
def debug_painel_tv():
    """Descobre tabelas de status de atendimento em tempo real."""

    # 1. Colunas de OSM com status/hora
    osm_status = query("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='osm'
          AND (COLUMN_NAME LIKE '%stat%' OR COLUMN_NAME LIKE '%hora%'
               OR COLUMN_NAME LIKE '%dthr%' OR COLUMN_NAME LIKE '%fila%'
               OR COLUMN_NAME LIKE '%tmp%' OR COLUMN_NAME LIKE '%tempo%'
               OR COLUMN_NAME LIKE '%ini%' OR COLUMN_NAME LIKE '%fim%'
               OR COLUMN_NAME LIKE '%saida%' OR COLUMN_NAME LIKE '%entrada%')
        ORDER BY ORDINAL_POSITION
    """)

    # 2. Tabela de fila / chamada
    fila_tabs = query("""
        SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE='BASE TABLE'
          AND (TABLE_NAME LIKE '%fil%' OR TABLE_NAME LIKE '%cha%'
               OR TABLE_NAME LIKE '%aten%' OR TABLE_NAME LIKE '%pres%'
               OR TABLE_NAME LIKE '%wait%' OR TABLE_NAME LIKE '%senha%'
               OR TABLE_NAME LIKE '%smk%')
        ORDER BY TABLE_NAME
    """)

    # 3. OSs de hoje com status
    hoje_osm = query("""
        SELECT TOP 5
            osm.osm_serie, osm.osm_num,
            osm.osm_dthr, osm.osm_atend,
            osm.osm_status,
            osm.OSM_HORA_ESP,
            osm.osm_dthr_saida,
            osm.osm_mreq,
            psv.psv_apel
        FROM osm
        LEFT JOIN psv ON psv.psv_cod = osm.osm_mreq
        WHERE CAST(osm.osm_dthr AS DATE) = CAST(GETDATE() AS DATE)
        ORDER BY osm.osm_dthr DESC
    """)

    # 4. Tabela AGM — agendamentos de hoje
    agm_hoje = query("""
        SELECT TOP 5
            agm.agm_id, agm.agm_stat, agm.agm_hini, agm.agm_hfim,
            agm.agm_med, agm.agm_pac,
            psv.psv_apel AS medico,
            pac.pac_nome AS paciente
        FROM agm
        LEFT JOIN psv ON psv.psv_cod = agm.agm_med
        LEFT JOIN pac ON pac.pac_reg = agm.agm_pac
        WHERE CAST(agm.agm_hini AS DATE) = CAST(GETDATE() AS DATE)
        ORDER BY agm.agm_hini DESC
    """)

    # 5. Tabela SMK (senha/fila)
    smk_tabs = []
    for t in ["SMK","SMK_SEN","SEN","SENHA","FILA","CAH"]:
        try:
            cols = query(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{t}' ORDER BY ORDINAL_POSITION")
            if cols:
                col_names = [c["COLUMN_NAME"] for c in cols[:6]]
                rows = query(f"SELECT TOP 2 {', '.join(col_names)} FROM {t}")
                smk_tabs.append({"tabela":t,"colunas":col_names,"amostra":rows})
        except: pass

    return {
        "osm_colunas_status": [c["COLUMN_NAME"] for c in osm_status],
        "tabelas_fila": [r["TABLE_NAME"] for r in fila_tabs],
        "osm_hoje": hoje_osm,
        "agm_hoje": agm_hoje,
        "smk_tabs": smk_tabs,
    }
@app.get("/api/debug/vlr-liquido")
def debug_vlr_liquido():
    """Compara SMM_VLR com campos de valor líquido disponíveis."""
    
    # Colunas de valor na SMM
    vlr_cols = query("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='smm'
          AND (COLUMN_NAME LIKE '%vlr%' OR COLUMN_NAME LIKE '%val%'
               OR COLUMN_NAME LIKE '%desc%' OR COLUMN_NAME LIKE '%cop%'
               OR COLUMN_NAME LIKE '%liq%' OR COLUMN_NAME LIKE '%ajust%')
        ORDER BY ORDINAL_POSITION
    """)
    
    # Amostra com os principais campos de valor
    sample = query("""
        SELECT TOP 5
            smm.SMM_VLR,
            smm.SMM_VLR_DESCONTO,
            smm.SMM_VLR_COPARTIC,
            smm.SMM_AJUSTE_VLR,
            smm.SMM_VLR_ESTORNO,
            smm.SMM_CML_VLR,
            smm.SMM_vlr_sem_reduc,
            smm.SMM_PERC_REDUC,
            smm.SMM_PRECO_CUSTO,
            smm.SMM_DESC_CONV
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE smm.SMM_SFAT IN ('A','F','P')
          AND smm.SMM_VLR > 0
          AND MONTH(osm.osm_dthr)=MONTH(GETDATE())
          AND YEAR(osm.osm_dthr)=YEAR(GETDATE())
        ORDER BY smm.SMM_VLR DESC
    """)
    
    # Totais comparando bruto vs liquido
    totais = query("""
        SELECT
            SUM(smm.SMM_VLR)                                           AS total_bruto,
            SUM(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0))         AS total_menos_desconto,
            SUM(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0)
                            - ISNULL(smm.SMM_VLR_COPARTIC,0))          AS total_menos_cop,
            SUM(ISNULL(smm.SMM_VLR_DESCONTO,0))                        AS total_descontos,
            SUM(ISNULL(smm.SMM_VLR_COPARTIC,0))                        AS total_copartic,
            SUM(ISNULL(smm.SMM_AJUSTE_VLR,0))                          AS total_ajustes,
            SUM(ISNULL(smm.SMM_CML_VLR,0))                             AS total_cml_vlr
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE smm.SMM_SFAT IN ('A','F','P')
          AND MONTH(osm.osm_dthr)=MONTH(GETDATE())
          AND YEAR(osm.osm_dthr)=YEAR(GETDATE())
    """)
    
    return {
        "colunas_valor": [c["COLUMN_NAME"] for c in vlr_cols],
        "amostra": sample,
        "totais_comparacao": totais[0] if totais else {}
    }
@app.get("/api/debug/mma-setor")
def debug_mma_setor():
    # MMA tem MMA_STR_COD e MMA_SBA_COD — setor e almoxarifado
    sample = query("""
        SELECT TOP 5
            mma.MMA_STR_COD, mma.MMA_SBA_COD, mma.MMA_TIPO_ES,
            str.str_nome
        FROM MMA mma
        LEFT JOIN str ON str.str_cod = mma.MMA_STR_COD
        WHERE mma.MMA_TIPO_ES='S' AND mma.MMA_IND_CANCELADA<>'S'
          AND mma.MMA_STR_COD IS NOT NULL
        ORDER BY mma.MMA_DATA_MOV DESC
    """)
    # Top setores por valor de saída no mês
    top_str = query("""
        SELECT TOP 10
            RTRIM(mma.MMA_STR_COD) AS setor_cod,
            RTRIM(str.str_nome) AS setor_nome,
            COUNT(DISTINCT mma.MMA_MAT_COD) AS materiais,
            SUM(mma.MMA_VALOR) AS valor_total,
            SUM(mma.MMA_QTD) AS qtd_total
        FROM MMA mma
        LEFT JOIN str ON str.str_cod = mma.MMA_STR_COD
        WHERE mma.MMA_TIPO_ES='S' AND mma.MMA_IND_CANCELADA<>'S'
          AND MONTH(mma.MMA_DATA_MOV)=MONTH(GETDATE())
          AND YEAR(mma.MMA_DATA_MOV)=YEAR(GETDATE())
        GROUP BY RTRIM(mma.MMA_STR_COD), RTRIM(str.str_nome)
        ORDER BY valor_total DESC
    """)
    return {"sample": sample, "top_setores": top_str}
@app.get("/api/debug/lma-join")
def debug_lma_join():
    # Verifica como MAT_LMA_COD está gravado vs LMA_COD
    sample = query("""
        SELECT TOP 5
            mat.MAT_COD, mat.MAT_LMA_COD,
            DATALENGTH(mat.MAT_LMA_COD) AS len_mat,
            lma.LMA_COD,
            DATALENGTH(lma.LMA_COD) AS len_lma,
            lma.LMA_NOME
        FROM MAT mat
        LEFT JOIN LMA lma ON lma.LMA_COD = mat.MAT_LMA_COD
        WHERE mat.MAT_LMA_COD IS NOT NULL AND mat.MAT_DEL_LOGICA<>'S'
    """)
    # Conta itens por LMA usando RTRIM
    por_lma = query("""
        SELECT TOP 10
            RTRIM(mat.MAT_LMA_COD) AS lma_cod,
            RTRIM(lma.LMA_NOME) AS lma_nome,
            RTRIM(lma.LMA_GMM_COD) AS gmm_cod,
            COUNT(*) AS qtd_itens,
            SUM(mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM) AS valor
        FROM MAT mat
        LEFT JOIN LMA lma ON RTRIM(lma.LMA_COD) = RTRIM(mat.MAT_LMA_COD)
        WHERE mat.MAT_DEL_LOGICA<>'S' AND mat.MAT_LMA_COD IS NOT NULL
        GROUP BY RTRIM(mat.MAT_LMA_COD), RTRIM(lma.LMA_NOME), RTRIM(lma.LMA_GMM_COD)
        ORDER BY valor DESC
    """)
    return {"sample": sample, "por_lma_rtrim": por_lma}
@app.get("/api/debug/mat-grupos")
def debug_mat_grupos():
    """Descobre campos de grupo/categoria na tabela MAT."""
    # MAT_GMM_COD, MAT_LMA_COD, MAT_GCP_COD, MAT_CTF_TIPO — candidatos
    grupos = {}
    for campo, tabela_ref in [("MAT_GMM_COD","GMM"),("MAT_LMA_COD","LMA"),("MAT_GCP_COD","GCP"),("MAT_CTF_TIPO","CTF")]:
        count = query(f"""
            SELECT TOP 5 {campo}, COUNT(*) AS qtd
            FROM MAT WHERE {campo} IS NOT NULL AND MAT_DEL_LOGICA<>'S'
            GROUP BY {campo} ORDER BY qtd DESC
        """)
        grupos[campo] = count
        # Tenta buscar nome na tabela de referência
        try:
            cols = query(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{tabela_ref}' ORDER BY ORDINAL_POSITION")
            col_names = [c["COLUMN_NAME"] for c in cols[:4]]
            rows = query(f"SELECT TOP 5 {', '.join(col_names)} FROM {tabela_ref}")
            grupos[f"{tabela_ref}_amostra"] = rows
        except:
            grupos[f"{tabela_ref}_amostra"] = "tabela não existe"
    return grupos
@app.get("/api/debug/estoque")
def debug_estoque():
    """Descobre a estrutura de estoque no banco Pixeon."""

    # Tabelas com est, sto, pro, mat, item
    tabelas = query("""
        SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE='BASE TABLE'
          AND (TABLE_NAME LIKE 'est%' OR TABLE_NAME LIKE 'sto%'
               OR TABLE_NAME LIKE 'mat%' OR TABLE_NAME LIKE 'itm%'
               OR TABLE_NAME LIKE 'alm%' OR TABLE_NAME LIKE 'mov%'
               OR TABLE_NAME LIKE 'req%' OR TABLE_NAME LIKE 'lote%')
        ORDER BY TABLE_NAME
    """)

    # Amostra de cada tabela encontrada
    amostras = []
    for t in [r["TABLE_NAME"] for r in tabelas][:6]:
        try:
            cols = query(f"""
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='{t}' ORDER BY ORDINAL_POSITION
            """)
            col_names = [c["COLUMN_NAME"] for c in cols[:6]]
            if col_names:
                sel = ", ".join(col_names)
                rows = query(f"SELECT TOP 2 {sel} FROM {t}")
                amostras.append({"tabela": t, "colunas": col_names, "amostra": rows})
        except:
            pass

    return {"tabelas": [r["TABLE_NAME"] for r in tabelas], "amostras": amostras}

@app.get("/api/debug/recoleta2")
def debug_recoleta2():
    """Confirma motivos de recoleta via mot_ind_nova_amostra."""

    # Motivos que geram nova amostra
    mot_nova = query("""
        SELECT mot.MOT_TIPO, mot.MOT_COD, mot.MOT_DESCR, mot.mot_ind_nova_amostra
        FROM mot
        WHERE mot.mot_ind_nova_amostra = 'S'
    """)

    # MCO com ind_nova_amostra
    mco_nova = query("""
        SELECT mco.MCO_COD, mco.MCO_NOME, mco.MCO_IND_TMR
        FROM mco
        WHERE mco.MCO_IND_TMR IS NOT NULL
        ORDER BY mco.MCO_COD
    """)

    # Quantos itens lab foram cancelados por recoleta no mês
    recoleta_mes = query("""
        SELECT COUNT(*) AS total_recoletas,
               COUNT(DISTINCT smm.SMM_OSM_SERIE*1000000+smm.SMM_OSM) AS os_com_recoleta
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE smm.SMM_ESP='LAB'
          AND smm.SMM_CANC_MOT_TIPO='MCO'
          AND MONTH(osm.osm_dthr)=MONTH(GETDATE())
          AND YEAR(osm.osm_dthr)=YEAR(GETDATE())
    """)

    # Recoleta por motivo MCO
    por_motivo = query("""
        SELECT smm.SMM_CANC_MOT_COD, mco.MCO_NOME,
               COUNT(*) AS qtd
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        LEFT JOIN mco ON mco.MCO_COD = CAST(LTRIM(RTRIM(smm.SMM_CANC_MOT_COD)) AS INT)
        WHERE smm.SMM_ESP='LAB'
          AND smm.SMM_CANC_MOT_TIPO='MCO'
          AND MONTH(osm.osm_dthr)=MONTH(GETDATE())
          AND YEAR(osm.osm_dthr)=YEAR(GETDATE())
        GROUP BY smm.SMM_CANC_MOT_COD, mco.MCO_NOME
        ORDER BY qtd DESC
    """)

    return {
        "mot_nova_amostra": mot_nova,
        "mco_todos": mco_nova,
        "recoleta_mes": recoleta_mes[0] if recoleta_mes else {},
        "recoleta_por_motivo": por_motivo,
    }

@app.get("/api/debug/recoleta")
def debug_recoleta():
    """Investiga como identificar recoleta no laboratório."""

    # 1. SMM_REP — campo de repetição/recoleta?
    rep_count = query("""
        SELECT TOP 5
            smm.SMM_REP, COUNT(*) AS qtd
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE smm.SMM_ESP='LAB'
          AND smm.SMM_REP IS NOT NULL
          AND LTRIM(RTRIM(smm.SMM_REP)) <> ''
          AND MONTH(osm.osm_dthr)=MONTH(GETDATE())
          AND YEAR(osm.osm_dthr)=YEAR(GETDATE())
        GROUP BY smm.SMM_REP
        ORDER BY qtd DESC
    """)

    # 2. SMM_MOTIVO_CANCELA — cancelamentos por recoleta?
    motivos = query("""
        SELECT TOP 10
            smm.SMM_MOTIVO_CANCELA, COUNT(*) AS qtd
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE smm.SMM_ESP='LAB'
          AND smm.SMM_MOTIVO_CANCELA IS NOT NULL
          AND LTRIM(RTRIM(smm.SMM_MOTIVO_CANCELA)) <> ''
          AND MONTH(osm.osm_dthr)=MONTH(GETDATE())
          AND YEAR(osm.osm_dthr)=YEAR(GETDATE())
        GROUP BY smm.SMM_MOTIVO_CANCELA ORDER BY qtd DESC
    """)

    # 3. Tabela de motivos de cancelamento
    try:
        mot_tab = query("""
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME IN ('mot','moc','mco','can','canc')
            ORDER BY TABLE_NAME, ORDINAL_POSITION
        """)
    except:
        mot_tab = []

    # 4. smm_canc_mot_tipo e smm_canc_mot_cod
    canc_tipos = query("""
        SELECT TOP 10
            smm.SMM_CANC_MOT_TIPO,
            smm.SMM_CANC_MOT_COD,
            COUNT(*) AS qtd
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE smm.SMM_ESP='LAB'
          AND smm.SMM_CANC_MOT_TIPO IS NOT NULL
          AND MONTH(osm.osm_dthr)=MONTH(GETDATE())
          AND YEAR(osm.osm_dthr)=YEAR(GETDATE())
        GROUP BY smm.SMM_CANC_MOT_TIPO, smm.SMM_CANC_MOT_COD
        ORDER BY qtd DESC
    """)

    # 5. Itens duplicados na mesma OS (mesmo exame pedido 2x = recoleta?)
    duplicados = query("""
        SELECT TOP 5
            smm.SMM_COD, smm.SMM_OSM_SERIE, smm.SMM_OSM,
            COUNT(*) AS vezes
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE smm.SMM_ESP='LAB'
          AND MONTH(osm.osm_dthr)=MONTH(GETDATE())
          AND YEAR(osm.osm_dthr)=YEAR(GETDATE())
        GROUP BY smm.SMM_COD, smm.SMM_OSM_SERIE, smm.SMM_OSM
        HAVING COUNT(*) > 1
        ORDER BY vezes DESC
    """)

    # 6. SMM_SEQ_AMOSTRA e SMM_COD_AMOSTRA_INI — indício de recoleta
    amo_ini = query("""
        SELECT COUNT(*) AS com_amo_ini
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE smm.SMM_ESP='LAB'
          AND smm.SMM_COD_AMOSTRA_INI IS NOT NULL
          AND LTRIM(RTRIM(CAST(smm.SMM_COD_AMOSTRA_INI AS VARCHAR))) <> ''
          AND CAST(smm.SMM_COD_AMOSTRA_INI AS VARCHAR) <> '0'
          AND MONTH(osm.osm_dthr)=MONTH(GETDATE())
          AND YEAR(osm.osm_dthr)=YEAR(GETDATE())
    """)

    return {
        "smm_rep_valores": rep_count,
        "motivos_cancela": motivos,
        "canc_mot_tipo_cod": canc_tipos,
        "itens_duplicados_mesma_os": duplicados,
        "com_amo_ini": amo_ini[0] if amo_ini else {},
        "mot_tabelas": mot_tab,
    }

@app.get("/api/debug/servicos-cod")
def debug_servicos_cod():
    """Descobre tabela srv e classifica SMM_COD por tipo de serviço."""

    # 1. Tabela srv existe?
    try:
        srv_cols = query("""
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME='srv' ORDER BY ORDINAL_POSITION
        """)
        srv_cols = [c["COLUMN_NAME"] for c in srv_cols]
    except:
        srv_cols = "nao existe"

    # 2. Amostra da tabela srv
    srv_sample = []
    if isinstance(srv_cols, list) and srv_cols:
        try:
            sel = ", ".join(srv_cols[:5])
            srv_sample = query(f"SELECT TOP 10 {sel} FROM srv ORDER BY 1")
        except:
            srv_sample = []

    # 3. Top SMM_COD mais frequentes no mês com SMM_ESP
    top_servicos = query("""
        SELECT TOP 30
            smm.SMM_COD,
            smm.SMM_TPCOD,
            smm.SMM_ESP,
            COUNT(*) AS qtd,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE MONTH(osm.osm_dthr)=MONTH(GETDATE())
          AND YEAR(osm.osm_dthr)=YEAR(GETDATE())
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY smm.SMM_COD, smm.SMM_TPCOD, smm.SMM_ESP
        ORDER BY qtd DESC
    """)

    # 4. SMM_ESP distintos - pode ser código de especialidade
    esp_distintos = query("""
        SELECT DISTINCT smm.SMM_ESP, COUNT(*) AS qtd
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE MONTH(osm.osm_dthr)=MONTH(GETDATE())
          AND YEAR(osm.osm_dthr)=YEAR(GETDATE())
          AND smm.SMM_SFAT IN ('A','F','P')
          AND smm.SMM_ESP IS NOT NULL
          AND LTRIM(RTRIM(smm.SMM_ESP)) <> ''
        GROUP BY smm.SMM_ESP
        ORDER BY qtd DESC
    """)

    # 5. JOIN smm com esp via SMM_ESP
    esp_via_smm = query("""
        SELECT TOP 10
            esp.esp_nome,
            COUNT(*) AS qtd,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) AS valor
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        JOIN esp ON esp.esp_cod = smm.SMM_ESP
        WHERE MONTH(osm.osm_dthr)=MONTH(GETDATE())
          AND YEAR(osm.osm_dthr)=YEAR(GETDATE())
          AND smm.SMM_SFAT IN ('A','F','P')
        GROUP BY esp.esp_nome
        ORDER BY qtd DESC
    """)

    return {
        "srv_colunas": srv_cols,
        "srv_amostra": srv_sample,
        "top_smm_cod": top_servicos,
        "smm_esp_distintos": esp_distintos,
        "especialidades_via_smm_esp": esp_via_smm,
    }

@app.get("/api/debug/servicos-os")
def debug_servicos_os():
    """Investiga como lab/psico/nutri ficam dentro das OSs."""

    # 1. Colunas de smm
    smm_cols = query("""
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'smm'
        ORDER BY ORDINAL_POSITION
    """)

    # 2. Colunas de smm com 'cod' ou 'nome' - prováveis chaves de serviço
    smm_key_cols = [c["COLUMN_NAME"] for c in smm_cols
                    if any(x in c["COLUMN_NAME"].lower()
                           for x in ["prc","srv","ato","itm","cod","desc","nom"])]

    # 3. Amostra de smm com colunas-chave apenas
    safe_cols = ["SMM_OSM_SERIE","SMM_OSM","SMM_VLR","SMM_SFAT","SMM_CNV_COD"]
    extra = [c for c in smm_key_cols if c not in safe_cols][:5]
    select_cols = ", ".join(safe_cols + extra)
    smm_sample = query(f"""
        SELECT TOP 5 {select_cols}
        FROM smm
        JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM
        WHERE MONTH(osm.osm_dthr)=MONTH(GETDATE())
          AND YEAR(osm.osm_dthr)=YEAR(GETDATE())
    """)

    # 4. Tabelas com 'prc' ou 'srv' no nome
    tabelas_srv = query("""
        SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE='BASE TABLE'
          AND (TABLE_NAME LIKE 'prc%' OR TABLE_NAME LIKE 'srv%'
               OR TABLE_NAME LIKE 'ato%' OR TABLE_NAME LIKE 'pro%')
        ORDER BY TABLE_NAME
    """)

    # 5. Tenta tabela srv (serviços)
    srv_sample = []
    for t in [r["TABLE_NAME"] for r in tabelas_srv][:3]:
        try:
            cols = query(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{t}' ORDER BY ORDINAL_POSITION")
            col_names = [c["COLUMN_NAME"] for c in cols[:4]]
            if col_names:
                sel = ", ".join(col_names)
                rows = query(f"SELECT TOP 3 {sel} FROM {t}")
                srv_sample.append({"tabela": t, "colunas": col_names, "amostra": rows})
        except:
            pass

    return {
        "smm_todas_colunas": [c["COLUMN_NAME"] for c in smm_cols],
        "smm_colunas_chave": smm_key_cols,
        "smm_amostra": smm_sample,
        "tabelas_srv_prc": [r["TABLE_NAME"] for r in tabelas_srv],
        "amostra_tabelas": srv_sample,
    }

@app.get("/api/debug/especialidade2")
def debug_especialidade2():
    """Verifica osm_esp_guia, osm_cobertura_esp e a tabela esp."""

    # 1. Amostra de osm_esp_guia e osm_cobertura_esp
    osm_esp = query("""
        SELECT TOP 10
            osm_atend,
            osm_esp_guia,
            osm_cobertura_esp,
            OSM_MREQ
        FROM osm
        WHERE MONTH(osm_dthr)=MONTH(GETDATE()) AND YEAR(osm_dthr)=YEAR(GETDATE())
          AND (osm_esp_guia IS NOT NULL OR osm_cobertura_esp IS NOT NULL)
        ORDER BY osm_dthr DESC
    """)

    # 2. Quantas OSs têm osm_esp_guia preenchido
    count_esp_guia = query("""
        SELECT COUNT(*) AS com_esp_guia,
               COUNT(DISTINCT osm_esp_guia) AS esp_distintas
        FROM osm
        WHERE MONTH(osm_dthr)=MONTH(GETDATE()) AND YEAR(osm_dthr)=YEAR(GETDATE())
          AND osm_esp_guia IS NOT NULL AND LTRIM(RTRIM(osm_esp_guia)) <> ''
    """)

    # 3. Top especialidades via osm_esp_guia
    top_via_guia = query("""
        SELECT TOP 10
            esp.esp_nome AS especialidade,
            COUNT(*) AS qtd
        FROM osm
        JOIN esp ON esp.esp_cod = osm.osm_esp_guia
        WHERE MONTH(osm_dthr)=MONTH(GETDATE()) AND YEAR(osm_dthr)=YEAR(GETDATE())
        GROUP BY esp.esp_nome ORDER BY qtd DESC
    """)

    # 4. Amostra da tabela esp
    esp_sample = query("SELECT TOP 10 esp_cod, esp_nome FROM esp WHERE esp_del_logica <> 'S' ORDER BY esp_nome")

    # 5. Tabela pse (prestador x especialidade) se existir
    try:
        pse = query("SELECT TOP 5 * FROM pse")
    except:
        pse = "tabela pse não existe"

    return {
        "osm_esp_guia_sample": osm_esp,
        "count_esp_guia": count_esp_guia[0] if count_esp_guia else {},
        "top_via_esp_guia": top_via_guia,
        "esp_amostra": esp_sample,
        "pse": pse,
    }

@app.get("/api/debug/estrutura")
def debug_estrutura():
    """Diagnóstico completo das colunas disponíveis para especialidade e serviços."""
    
    # 1. Colunas disponíveis na tabela psv
    psv_cols = query("""
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'psv'
        ORDER BY ORDINAL_POSITION
    """)
    
    # 2. Amostra de psv com especialidade
    psv_sample = query("""
        SELECT TOP 5 psv_cod, psv_nome, psv_apel, psv_esp_cod
        FROM psv WHERE psv_esp_cod IS NOT NULL AND LTRIM(RTRIM(psv_esp_cod)) <> ''
    """)
    
    # 3. Quantas OSs do mês têm médico com especialidade
    esp_count = query("""
        SELECT
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS total_os,
            COUNT(DISTINCT CASE WHEN psv.psv_esp_cod IS NOT NULL AND LTRIM(RTRIM(psv.psv_esp_cod))<>'' 
                                THEN osm.osm_serie*1000000+osm.osm_num END) AS com_esp_psv,
            COUNT(DISTINCT CASE WHEN agm.AGM_ESP_COD IS NOT NULL AND LTRIM(RTRIM(agm.AGM_ESP_COD))<>''
                                THEN osm.osm_serie*1000000+osm.osm_num END) AS com_esp_agm
        FROM osm
        LEFT JOIN psv ON psv.psv_cod = osm.osm_mreq
        LEFT JOIN agm ON agm.agm_id  = osm.OSM_AGM_ID
        WHERE MONTH(osm.osm_dthr) = MONTH(GETDATE())
          AND YEAR(osm.osm_dthr)  = YEAR(GETDATE())
    """)
    
    # 4. Colunas de osm relacionadas a médico/especialidade
    osm_cols = query("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'osm'
          AND (COLUMN_NAME LIKE '%med%' OR COLUMN_NAME LIKE '%esp%' OR COLUMN_NAME LIKE '%req%' OR COLUMN_NAME LIKE '%exec%')
        ORDER BY ORDINAL_POSITION
    """)

    # 5. Serviços especializados — osm_atend codes reais no banco
    atend_codes = query("""
        SELECT osm_atend, COUNT(*) AS qtd
        FROM osm
        WHERE YEAR(osm_dthr) = YEAR(GETDATE())
        GROUP BY osm_atend
        ORDER BY qtd DESC
    """)

    return {
        "psv_colunas": psv_cols,
        "psv_amostra": psv_sample,
        "esp_count": esp_count[0] if esp_count else {},
        "osm_colunas_medico": osm_cols,
        "atend_codes_reais": atend_codes,
    }

@app.get("/api/debug/especialidades")
def debug_especialidades(periodo: str = "30d"):
    """Diagnóstico: verifica os JOINs de especialidade."""
    inicio, fim = periodo_datas(periodo)
    
    # Quantas OSs têm osm_mreq preenchido?
    r1 = query(f"""
        SELECT COUNT(*) AS total_os,
               SUM(CASE WHEN osm_mreq IS NOT NULL THEN 1 ELSE 0 END) AS com_mreq,
               SUM(CASE WHEN OSM_AGM_ID IS NOT NULL THEN 1 ELSE 0 END) AS com_agm
        FROM osm WHERE osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
    """)
    
    # Quantos psv têm psv_esp_cod preenchido?
    r2 = query("""
        SELECT COUNT(*) AS total_psv,
               SUM(CASE WHEN psv_esp_cod IS NOT NULL 
                        AND LTRIM(RTRIM(psv_esp_cod)) <> '' THEN 1 ELSE 0 END) AS com_esp
        FROM psv
    """)
    
    # Top 5 via psv direto
    r3 = query(f"""
        SELECT TOP 5 esp.esp_nome, COUNT(*) AS qtd
        FROM osm
        JOIN psv ON psv.psv_cod = osm.osm_mreq
        JOIN esp ON esp.esp_cod = psv.psv_esp_cod
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
        GROUP BY esp.esp_nome ORDER BY qtd DESC
    """)
    
    # Top 5 via agm
    r4 = query(f"""
        SELECT TOP 5 esp.esp_nome, COUNT(*) AS qtd
        FROM osm
        JOIN agm ON agm.agm_id = osm.OSM_AGM_ID
        JOIN esp ON esp.esp_cod = agm.AGM_ESP_COD
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
        GROUP BY esp.esp_nome ORDER BY qtd DESC
    """)
    
    return {
        "periodo": {"inicio": inicio, "fim": fim},
        "osm": r1[0] if r1 else {},
        "psv": r2[0] if r2 else {},
        "via_psv_top5": r3,
        "via_agm_top5": r4,
    }



@app.get("/api/ocupacional/resumo")
def ocupacional_resumo(periodo: str = "30d"):
    """
    Métricas Medicina Ocupacional.
    Contadores de tipo usam subquery com DISTINCT para evitar duplicação por itens smm.
    """
    inicio, fim = periodo_datas(periodo)
    rows = query(f"""
        SELECT
            -- Totais de OS distintas por tipo (não duplica por itens smm)
            COUNT(DISTINCT osm.osm_serie * 1000000 + osm.osm_num)                              AS total_os,
            COUNT(DISTINCT CASE WHEN osm.osm_atend = 'ADM' THEN osm.osm_serie * 1000000 + osm.osm_num END) AS admissional,
            COUNT(DISTINCT CASE WHEN osm.osm_atend = 'PER' THEN osm.osm_serie * 1000000 + osm.osm_num END) AS periodico,
            COUNT(DISTINCT CASE WHEN osm.osm_atend = 'DEM' THEN osm.osm_serie * 1000000 + osm.osm_num END) AS demissional,
            COUNT(DISTINCT CASE WHEN osm.osm_atend = 'RTB' THEN osm.osm_serie * 1000000 + osm.osm_num END) AS ret_trabalho,
            COUNT(DISTINCT CASE WHEN osm.osm_atend = 'MDF' THEN osm.osm_serie * 1000000 + osm.osm_num END) AS mud_funcao,
            COUNT(DISTINCT CASE WHEN osm.osm_atend = 'MOC' THEN osm.osm_serie * 1000000 + osm.osm_num END) AS med_ocup,
            COUNT(DISTINCT osm.osm_pac)                                                         AS pacientes_unicos,
            COUNT(DISTINCT osm.osm_cnv)                                                         AS empresas,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                                                                    AS faturamento,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))) / NULLIF(COUNT(DISTINCT osm.osm_serie * 1000000 + osm.osm_num), 0) AS ticket_medio
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE = osm.osm_serie AND smm.SMM_OSM = osm.osm_num
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')
          AND smm.SMM_SFAT IN ('A','F','P')
    """)
    return rows[0] if rows else {}


@app.get("/api/ocupacional/por-empresa")
def ocupacional_por_empresa(periodo: str = "30d"):
    """Top empresas (convênios) por volume de exames ocupacionais."""
    inicio, fim = periodo_datas(periodo)
    rows = query(f"""
        SELECT TOP 15
            cnv.cnv_nome                                                    AS empresa,
            COUNT(DISTINCT osm.osm_serie * 1000000 + osm.osm_num)          AS total_os,
            SUM(CASE WHEN osm.osm_atend = 'ADM' THEN 1 ELSE 0 END)         AS admissional,
            SUM(CASE WHEN osm.osm_atend = 'PER' THEN 1 ELSE 0 END)         AS periodico,
            SUM(CASE WHEN osm.osm_atend = 'DEM' THEN 1 ELSE 0 END)         AS demissional,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                                                AS faturamento
        FROM osm
        JOIN smm ON smm.SMM_OSM_SERIE = osm.osm_serie AND smm.SMM_OSM = osm.osm_num
        JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')
          AND smm.SMM_SFAT IN ('A','F','P')
          AND cnv.cnv_nome IS NOT NULL
        GROUP BY cnv.cnv_nome
        ORDER BY total_os DESC
    """)
    return rows


@app.get("/api/ocupacional/por-dia")
def ocupacional_por_dia(periodo: str = "30d"):
    """Volume diário de atendimentos ocupacionais."""
    inicio, fim = periodo_datas(periodo)
    rows = query(f"""
        SELECT
            CAST(osm.osm_dthr AS DATE)                                      AS data,
            COUNT(DISTINCT osm.osm_serie * 1000000 + osm.osm_num)          AS total,
            SUM(CASE WHEN osm.osm_atend = 'ADM' THEN 1 ELSE 0 END)         AS admissional,
            SUM(CASE WHEN osm.osm_atend = 'PER' THEN 1 ELSE 0 END)         AS periodico,
            SUM(CASE WHEN osm.osm_atend = 'DEM' THEN 1 ELSE 0 END)         AS demissional
        FROM osm
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')
        GROUP BY CAST(osm.osm_dthr AS DATE)
        ORDER BY data
    """)
    for r in rows:
        if hasattr(r.get("data"), "strftime"):
            r["data"] = r["data"].strftime("%Y-%m-%d")
    return rows


@app.get("/api/laboratorio/por-setor")
def laboratorio_por_setor(periodo: str = "30d"):
    """
    Volume por setor — conta ITENS (linhas smm), não OSs.
    Cada OS de lab pode ter dezenas de exames individuais.
    """
    inicio, fim = periodo_datas(periodo)
    setores = "LAB,RAD,USG,CAR,PNE,FON,OFT,NEU,PSI,ACV"
    lista   = ",".join(f"'{s.strip()}'" for s in setores.split(","))
    rows = query(f"""
        SELECT
            smm.SMM_STR                                             AS cod_setor,
            LTRIM(RTRIM(s.STR_NOME))                                AS nome_setor,
            COUNT(*)                                                AS total_itens,   -- itens/exames (cada linha = 1 exame)
            COUNT(DISTINCT osm.osm_serie * 1000000 + osm.osm_num)  AS total_os,      -- ordens
            COUNT(DISTINCT osm.osm_pac)                             AS pacientes,
            SUM((smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)))                                        AS faturamento
        FROM smm
        JOIN osm ON osm.osm_serie = smm.SMM_OSM_SERIE
                AND osm.osm_num   = smm.SMM_OSM
        JOIN str s ON s.STR_COD   = smm.SMM_STR
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND smm.SMM_SFAT IN ('A','F','P')
          AND smm.SMM_STR IN ({lista})
        GROUP BY smm.SMM_STR, LTRIM(RTRIM(s.STR_NOME))
        ORDER BY total_itens DESC
    """)
    return rows


@app.get("/api/debug/setores")
def debug_setores():
    """Lista todos os setores (tabela str) com quantidade de OSs."""
    rows = query("""
        SELECT TOP 50
            s.str_cod   AS cod,
            s.str_nome  AS nome,
            COUNT(o.osm_serie) AS qtd_os
        FROM str s
        LEFT JOIN osm o ON o.osm_str = s.str_cod
        GROUP BY s.str_cod, s.str_nome
        ORDER BY qtd_os DESC
    """)
    return rows


@app.get("/api/debug/servicos-setor")
def debug_servicos_setor():
    """
    Busca setores matriz via cadastro de serviços.
    Tenta tabelas: srv, ser, svc, svr, pro comuns no Pixeon.
    """
    resultados = {}
    
    # Tenta tabela 'srv' - serviços
    try:
        r = query("""
            SELECT TOP 5 * FROM srv
        """)
        resultados["srv_colunas"] = list(r[0].keys()) if r else "vazia"
    except Exception as e:
        resultados["srv"] = str(e)

    # Tenta tabela 'ser'
    try:
        r = query("""
            SELECT TOP 5 * FROM ser
        """)
        resultados["ser_colunas"] = list(r[0].keys()) if r else "vazia"
    except Exception as e:
        resultados["ser"] = str(e)

    # Tenta smm com join em algum serviço
    try:
        r = query("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'smm'
            ORDER BY ORDINAL_POSITION
        """)
        resultados["smm_colunas"] = [x["COLUMN_NAME"] for x in r]
    except Exception as e:
        resultados["smm_cols"] = str(e)

    # Colunas da tabela str
    try:
        r = query("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'str'
            ORDER BY ORDINAL_POSITION
        """)
        resultados["str_colunas"] = [x["COLUMN_NAME"] for x in r]
    except Exception as e:
        resultados["str_cols"] = str(e)

    # Tenta pegar setor matriz via smm -> alguma FK de serviço
    try:
        r = query("""
            SELECT TOP 10
                smm.SMM_COD_TABELA,
                smm.SMM_COD_SERV,
                COUNT(*) AS qtd
            FROM smm
            WHERE smm.SMM_COD_SERV IS NOT NULL
            GROUP BY smm.SMM_COD_TABELA, smm.SMM_COD_SERV
            ORDER BY qtd DESC
        """)
        resultados["smm_servicos_top10"] = r
    except Exception as e:
        resultados["smm_serv"] = str(e)

    return resultados


@app.get("/api/debug/setores-lab")
def debug_setores_lab():
    """
    Busca setores via SMM_STR -> str.
    str_emp_matriz_labet pode indicar laboratório.
    STR_TIPO pode separar tipos de setor.
    """
    # Todos os setores com qtd de itens SMM
    r1 = query("""
        SELECT TOP 30
            s.STR_COD                       AS cod,
            s.STR_NOME                      AS nome,
            s.STR_TIPO                      AS tipo,
            s.STR_ATEND                     AS atend,
            s.str_emp_matriz_labet          AS matriz_labet,
            s.STR_STATUS                    AS status,
            COUNT(smm.SMM_OSM)              AS qtd_itens
        FROM str s
        LEFT JOIN smm ON smm.SMM_STR = s.STR_COD
        GROUP BY s.STR_COD, s.STR_NOME, s.STR_TIPO, s.STR_ATEND, 
                 s.str_emp_matriz_labet, s.STR_STATUS
        ORDER BY qtd_itens DESC
    """)
    return r1
@app.get("/api/debug/fle-senha-chamada")
def debug_fle_senha_chamada():
    hoje = datetime.now().strftime("%Y-%m-%d")
    rows = query(f"""
        SELECT TOP 5
            fle.FLE_BIP,
            fle.FLE_ORDEM,
            fle.FLE_STATUS,
            fle.FLE_USR_LOGIN,
            fle.FLE_USR_ATENDIMENTO,
            RTRIM(psv.psv_apel)     AS psv_apel,
            fle.FLE_STR_COD,
            fle.FLE_LOC_COD,
            fle.fle_atd_local,
            CONVERT(VARCHAR(5),fle.FLE_DTHR_ATENDIMENTO,108) AS chamado_em
        FROM fle
        JOIN psv ON psv.psv_cod = fle.FLE_PSV_COD
        WHERE CAST(fle.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
          AND fle.FLE_DTHR_ATENDIMENTO IS NOT NULL
          AND fle.FLE_BIP IS NOT NULL
          AND LTRIM(RTRIM(fle.FLE_BIP)) <> ''
        ORDER BY fle.FLE_DTHR_ATENDIMENTO DESC
    """)
    for r in rows:
        for k, v in r.items():
            if hasattr(v, 'strftime'): r[k] = v.strftime('%H:%M:%S')
    return rows
# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS DOS PAINÉIS TV — Somente leitura da FLE
# Cole no main.py
# ══════════════════════════════════════════════════════════════════════════════

_SETORES_PAINEL_FILA = {"RCN", "RDI", "ROC", "RPS", "RCI"}


def _filtro_psv_cod(psv_cod: str) -> str:
    """psv_cod → lista de códigos separados por vírgula (as 'filas'/prestadores
    escolhidos no painel). Ignora silenciosamente valores não numéricos."""
    if not psv_cod:
        return ""
    codigos = [c.strip() for c in psv_cod.split(",") if c.strip().lstrip("-").isdigit()]
    if not codigos:
        return ""
    return f"AND fle.FLE_PSV_COD IN ({','.join(codigos)})"


# ── Vídeos informativos do painel de TV ───────────────────────────────────
# Arquivos ficam em painel_recepcao/videos — servidos estaticamente pelo
# mount /painel-tv. Esses endpoints deixam listar/enviar/remover pelo
# servidor, sem precisar mexer direto na pasta em cada TV.
_PAINEL_VIDEOS_DIR = r"C:\Users\administrator.CENSO\Desktop\painel_recepcao\videos"
_VIDEO_EXTENSOES = {".mp4", ".webm", ".ogg", ".mov"}

@app.get("/api/painel-fila/videos")
def painel_fila_videos_listar():
    """Lista os vídeos disponíveis na pasta, na ordem alfabética de exibição."""
    if not os.path.isdir(_PAINEL_VIDEOS_DIR):
        return []
    arquivos = [
        f for f in os.listdir(_PAINEL_VIDEOS_DIR)
        if os.path.splitext(f)[1].lower() in _VIDEO_EXTENSOES
    ]
    arquivos.sort(key=str.lower)
    return [{"nome": f, "url": f"/painel-tv/videos/{f}"} for f in arquivos]

@app.post("/api/painel-fila/videos")
async def painel_fila_videos_upload(arquivo: UploadFile = File(...)):
    """Recebe um vídeo enviado e salva na pasta servida pelas TVs."""
    ext = os.path.splitext(arquivo.filename or "")[1].lower()
    if ext not in _VIDEO_EXTENSOES:
        raise HTTPException(400, f"Formato não suportado: {ext or '(sem extensão)'}")
    os.makedirs(_PAINEL_VIDEOS_DIR, exist_ok=True)
    nome_seguro = os.path.basename(arquivo.filename).replace("..", "")
    destino = os.path.join(_PAINEL_VIDEOS_DIR, nome_seguro)
    with open(destino, "wb") as f:
        while True:
            pedaco = await arquivo.read(1024 * 1024)
            if not pedaco:
                break
            f.write(pedaco)
    return {"ok": True, "nome": nome_seguro}

@app.delete("/api/painel-fila/videos/{nome}")
def painel_fila_videos_remover(nome: str):
    """Remove um vídeo da pasta pelo nome do arquivo."""
    nome_seguro = os.path.basename(nome)
    caminho = os.path.join(_PAINEL_VIDEOS_DIR, nome_seguro)
    if not os.path.exists(caminho):
        raise HTTPException(404, "Vídeo não encontrado")
    os.remove(caminho)
    return {"ok": True}


@app.get("/api/painel-fila/prestadores")
def painel_fila_prestadores():
    """
    Lista as 'filas' oficiais de senha cadastradas no Smart — usado no
    seletor de configuração do painel de TV.
    Fonte: FLE_CFG_SENHA (cadastro de filas de totem/senha), não o histórico
    de chamadas em `fle` — o setor gravado em `fle.FLE_STR_COD` para esse
    tipo de fila não reflete de forma confiável a recepção física (a maioria
    fica marcada como 'RPS' independente do nome da fila), então a escolha
    de quais filas aparecem em qual TV é sempre manual, feita no painel.
    """
    rows = query("""
        SELECT
            cfg.FLE_CFG_SENHA_PSV_COD                AS psv_cod,
            RTRIM(psv.psv_apel)                       AS psv_apel,
            RTRIM(ISNULL(esp.esp_nome,''))            AS especialidade
        FROM FLE_CFG_SENHA cfg
        JOIN psv ON psv.psv_cod = cfg.FLE_CFG_SENHA_PSV_COD
        LEFT JOIN esp ON esp.esp_cod = psv.psv_esp_cod
        ORDER BY psv_apel
    """)
    return rows


@app.get("/api/painel-fila/senhas")
def painel_fila_senhas(limite: int = 8, setor: str = None, psv_cod: str = None):
    """
    Painel TV — Senhas chamadas pela recepção (guichês).
    Guichê físico real: tabela MFL (gravada quando FILA_CEGO=N no Smart.ini),
    campo MFL_LOC_ORIGEM_CHAMADA — join por MFL_FLE_DTHR_CHEG/STR_COD/PSV_COD
    de volta pra fle, depois LOC pra pegar o nome ("Guichê 01"). Nem toda
    chamada tem esse registro (ex: chamadas via totem) — nesse caso cai no
    login de quem atendeu como alternativa.
    setor    → filtra por recepção (RCN, RDI, ROC, RPS, RCI); vazio/inválido = todas.
    psv_cod  → filtra pelas filas/prestadores escolhidos (lista separada por vírgula).
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    filtro_setor = f"AND RTRIM(fle.FLE_STR_COD) = '{setor}'" if setor in _SETORES_PAINEL_FILA else ""
    filtro_psv = _filtro_psv_cod(psv_cod)
    rows = query(f"""
        SELECT TOP {limite}
            RTRIM(ISNULL(fle.FLE_BIP, ''))                              AS senha,
            CAST(fle.FLE_ORDEM AS INT)                                  AS ordem,
            RTRIM(psv.psv_apel)                                         AS psv_apel,
            RTRIM(psv.psv_nome)                                         AS psv_nome,
            RTRIM(ISNULL(esp.esp_nome,''))                              AS especialidade,
            RTRIM(fle.FLE_STR_COD)                                      AS setor,
            -- Usa o horário da rechamada (MFL) quando existe uma mais nova
            -- que a chamada original — senão uma rechamada não atualiza a
            -- hora exibida nem volta pro topo da lista de "mais recentes".
            CONVERT(VARCHAR(5),COALESCE(mfl.MFL_DTHR,fle.FLE_DTHR_ATENDIMENTO),108) AS chamado_em,
            RTRIM(ISNULL(fle.fle_pac_nome,
                   RTRIM(ISNULL(pac.pac_nome,''))))                     AS pac_nome,
            fle.FLE_PREFERENCIAL                                        AS preferencial,
            DATEDIFF(minute,fle.FLE_DTHR_CHEGADA,
                     fle.FLE_DTHR_ATENDIMENTO)                          AS espera_min,
            -- Guichê físico real (MFL+LOC); cai no login de quem atendeu
            -- quando a chamada não tem registro em MFL (ex: via totem).
            RTRIM(mfl.MFL_LOC_ORIGEM_CHAMADA)                           AS guiche_cod,
            RTRIM(loc.LOC_NOME)                                         AS guiche_nome,
            RTRIM(ISNULL(fle.FLE_USR_ATENDIMENTO, fle.FLE_USR_LOGIN))  AS guiche
        FROM fle
        JOIN psv ON psv.psv_cod = fle.FLE_PSV_COD
        LEFT JOIN esp ON esp.esp_cod = psv.psv_esp_cod
        LEFT JOIN pac ON pac.pac_reg = fle.FLE_PAC_REG
        LEFT JOIN (
            -- Uma mesma senha pode ter mais de uma mensagem MFL (rechamada,
            -- reenvio pra outro guichê) — pega só a mais recente de cada uma.
            SELECT MFL_FLE_DTHR_CHEG, MFL_FLE_STR_COD, MFL_FLE_PSV_COD, MFL_LOC_ORIGEM_CHAMADA, MFL_DTHR,
                   ROW_NUMBER() OVER (
                       PARTITION BY MFL_FLE_DTHR_CHEG, MFL_FLE_STR_COD, MFL_FLE_PSV_COD
                       ORDER BY MFL_DTHR DESC
                   ) AS rn
            FROM MFL
            WHERE MFL_LOC_ORIGEM_CHAMADA IS NOT NULL
              -- Filtra por MFL_DTHR (início da chave primária/índice
              -- clusterizado) em vez de MFL_FLE_DTHR_CHEG — essa tabela não
              -- tem índice útil pelas colunas de join, então filtrar pela
              -- coluna errada forçava varrer a tabela inteira (~39s).
              AND MFL_DTHR >= '{hoje}'
        ) mfl
          ON mfl.MFL_FLE_DTHR_CHEG = fle.FLE_DTHR_CHEGADA
         AND mfl.MFL_FLE_STR_COD   = fle.FLE_STR_COD
         AND mfl.MFL_FLE_PSV_COD   = fle.FLE_PSV_COD
         AND mfl.rn = 1
        LEFT JOIN LOC loc ON RTRIM(loc.LOC_COD) = RTRIM(mfl.MFL_LOC_ORIGEM_CHAMADA)
        WHERE CAST(fle.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
          AND fle.FLE_DTHR_ATENDIMENTO IS NOT NULL
          AND fle.FLE_BIP IS NOT NULL
          AND LTRIM(RTRIM(fle.FLE_BIP)) <> ''
          -- Exclui autoatendimento do totem (sem atendente humano de fato,
          -- só o próprio totem processou) — senão aparece "chamado" no
          -- painel assim que a senha é gerada, sem ninguém ter chamado.
          AND NOT (fle.FLE_USR_ATENDIMENTO IS NULL AND RTRIM(fle.FLE_USR_LOGIN) = 'TOTEM')
          {filtro_setor}
          {filtro_psv}
        ORDER BY COALESCE(mfl.MFL_DTHR, fle.FLE_DTHR_ATENDIMENTO) DESC
    """)
    return rows


@app.get("/api/painel-fila/status-senhas")
def painel_fila_status_senhas(setor: str = None, psv_cod: str = None):
    """
    Status das filas de senha por prestador — lateral do painel TV.
    setor    → filtra por recepção (RCN, RDI, ROC, RPS, RCI); vazio/inválido = todas.
    psv_cod  → filtra pelas filas/prestadores escolhidos (lista separada por vírgula).
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    filtro_setor = f"AND RTRIM(fle.FLE_STR_COD) = '{setor}'" if setor in _SETORES_PAINEL_FILA else ""
    filtro_psv = _filtro_psv_cod(psv_cod)
    rows = query(f"""
        SELECT
            fle.FLE_PSV_COD                                         AS psv_cod,
            RTRIM(psv.psv_apel)                                     AS psv_apel,
            RTRIM(ISNULL(esp.esp_nome,''))                          AS especialidade,
            SUM(CASE WHEN fle.FLE_DTHR_ATENDIMENTO IS NULL
                      AND fle.FLE_STATUS = 'A' THEN 1 ELSE 0 END)  AS na_fila,
            SUM(CASE WHEN fle.FLE_DTHR_ATENDIMENTO IS NOT NULL
                     THEN 1 ELSE 0 END)                             AS atendidos,
            SUM(CASE WHEN fle.FLE_PREFERENCIAL = 'S'
                      AND fle.FLE_STATUS = 'A'
                      AND fle.FLE_DTHR_ATENDIMENTO IS NULL
                     THEN 1 ELSE 0 END)                             AS preferenciais,
            -- Próxima senha aguardando
            (SELECT TOP 1 RTRIM(ISNULL(f2.FLE_BIP,
                'EXL'+RIGHT('000'+CAST(CAST(f2.FLE_ORDEM AS INT) AS VARCHAR),3)))
             FROM fle f2
             WHERE f2.FLE_PSV_COD = fle.FLE_PSV_COD
               AND CAST(f2.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
               AND f2.FLE_DTHR_ATENDIMENTO IS NULL
               AND f2.FLE_STATUS = 'A'
             ORDER BY f2.FLE_PREFERENCIAL DESC, f2.FLE_DTHR_CHEGADA ASC) AS proxima_senha
        FROM fle
        JOIN psv ON psv.psv_cod = fle.FLE_PSV_COD
        LEFT JOIN esp ON esp.esp_cod = psv.psv_esp_cod
        WHERE CAST(fle.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
          AND fle.FLE_BIP IS NOT NULL
          AND LTRIM(RTRIM(fle.FLE_BIP)) <> ''
          {filtro_setor}
          {filtro_psv}
        GROUP BY fle.FLE_PSV_COD, RTRIM(psv.psv_apel),
                 RTRIM(ISNULL(esp.esp_nome,''))
        ORDER BY na_fila DESC
    """)
    return rows


@app.get("/api/painel-fila/pacientes")
def painel_fila_pacientes(limite: int = 8):
    """
    Painel TV — Pacientes chamados pelos médicos no Smart.
    FLE_STATUS = 'X' quando o médico chama pelo Smart.
    FLE_LOC_COD é null — usa setor (FLE_STR_COD) + nome do prestador.
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    SETORES = {
        'RDI': 'Recepção Diagnóstico',
        'ROC': 'Recepção Ocupacional',
        'RPS': 'Recepção Pro Saúde',
        'RCN': 'Recepção Consultórios',
        'RCI': 'Recepção Censo Imagem',
    }
    rows = query(f"""
        SELECT TOP {limite}
            RTRIM(pac.pac_nome)                                         AS pac_nome,
            fle.FLE_PAC_REG                                             AS pac_reg,
            RTRIM(psv.psv_apel)                                         AS psv_apel,
            RTRIM(psv.psv_nome)                                         AS psv_nome,
            RTRIM(ISNULL(esp.esp_nome,''))                              AS especialidade,
            RTRIM(ISNULL(loc.LOC_NOME,''))                              AS local_nome,
            RTRIM(fle.FLE_STR_COD)                                      AS setor,
            CONVERT(VARCHAR(5),fle.FLE_DTHR_ATENDIMENTO,108)            AS chamado_em,
            fle.FLE_PREFERENCIAL                                        AS preferencial,
            DATEDIFF(minute,fle.FLE_DTHR_CHEGADA,
                     fle.FLE_DTHR_ATENDIMENTO)                          AS espera_min
        FROM fle
        JOIN psv ON psv.psv_cod = fle.FLE_PSV_COD
        LEFT JOIN esp ON esp.esp_cod = psv.psv_esp_cod
        LEFT JOIN pac ON pac.pac_reg = fle.FLE_PAC_REG
        LEFT JOIN loc ON RTRIM(loc.LOC_COD) = RTRIM(fle.FLE_LOC_COD)
        WHERE CAST(fle.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
          AND fle.FLE_DTHR_ATENDIMENTO IS NOT NULL
          AND fle.FLE_STATUS = 'X'
          AND (fle.FLE_BIP IS NULL OR LTRIM(RTRIM(fle.FLE_BIP)) = '')
        ORDER BY fle.FLE_DTHR_ATENDIMENTO DESC
    """)
    for r in rows:
        if r.get("pac_nome"):
            r["pac_nome"] = str(r["pac_nome"]).strip().title()
        # Usa nome do setor como local quando LOC_NOME estiver vazio
        if not r.get("local_nome") or not str(r["local_nome"]).strip():
            setor = str(r.get("setor") or "").strip()
            r["local_nome"] = SETORES.get(setor, setor)
    return rows


@app.get("/api/painel-fila/status-pacientes")
def painel_fila_status_pacientes():
    """
    Status das filas por médico — lateral do painel de pacientes.
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    rows = query(f"""
        SELECT
            fle.FLE_PSV_COD                                         AS psv_cod,
            RTRIM(psv.psv_apel)                                     AS psv_apel,
            RTRIM(ISNULL(esp.esp_nome,''))                          AS especialidade,
            RTRIM(ISNULL(loc.LOC_NOME,''))                          AS local_nome,
            SUM(CASE WHEN fle.FLE_DTHR_ATENDIMENTO IS NULL
                      AND fle.FLE_STATUS = 'A' THEN 1 ELSE 0 END)  AS aguardando,
            SUM(CASE WHEN fle.FLE_DTHR_ATENDIMENTO IS NOT NULL
                     THEN 1 ELSE 0 END)                             AS atendidos,
            -- Próximo paciente
            (SELECT TOP 1
                RTRIM(ISNULL(f2.fle_pac_nome, RTRIM(ISNULL(p2.pac_nome,''))))
             FROM fle f2
             LEFT JOIN pac p2 ON p2.pac_reg = f2.FLE_PAC_REG
             WHERE f2.FLE_PSV_COD = fle.FLE_PSV_COD
               AND CAST(f2.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
               AND f2.FLE_DTHR_ATENDIMENTO IS NULL
               AND f2.FLE_STATUS = 'A'
             ORDER BY f2.FLE_PREFERENCIAL DESC, f2.FLE_DTHR_CHEGADA ASC) AS proximo_pac
        FROM fle
        JOIN psv ON psv.psv_cod = fle.FLE_PSV_COD
        LEFT JOIN esp ON esp.esp_cod = psv.psv_esp_cod
        LEFT JOIN loc ON RTRIM(loc.LOC_COD) = (
            SELECT TOP 1 RTRIM(f3.FLE_LOC_COD) FROM fle f3
            WHERE f3.FLE_PSV_COD = fle.FLE_PSV_COD
              AND CAST(f3.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
              AND f3.FLE_LOC_COD IS NOT NULL
            ORDER BY f3.FLE_DTHR_ATENDIMENTO DESC
        )
        WHERE CAST(fle.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
          AND (fle.FLE_BIP IS NULL OR LTRIM(RTRIM(fle.FLE_BIP)) = '')
        GROUP BY fle.FLE_PSV_COD, RTRIM(psv.psv_apel),
                 RTRIM(ISNULL(esp.esp_nome,'')), RTRIM(ISNULL(loc.LOC_NOME,''))
        HAVING SUM(CASE WHEN fle.FLE_DTHR_ATENDIMENTO IS NULL
                         AND fle.FLE_STATUS = 'A' THEN 1 ELSE 0 END) > 0
        ORDER BY aguardando DESC
    """)
    return rows

@app.get("/api/atendimento/fila")
def atendimento_fila(medico: int):
    """
    Fila de pacientes recepcionados para um médico específico, aguardando atendimento.
    Mesmo mecanismo do Painel de Senhas: FLE_PSV_COD = médico (psv_cod), FLE_STATUS='A' = aguardando
    (paciente chegou e ainda não foi chamado — 'X' = já chamado, 'E'/'Z' = outros status).
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    rows = query(f"""
        SELECT
            fle.FLE_PAC_REG                                    AS pac_reg,
            RTRIM(pac.pac_nome)                                 AS paciente,
            CONVERT(varchar, pac.PAC_NASC, 23)                   AS nascimento,
            fle.FLE_DTHR_CHEGADA                                AS chegada,
            DATEDIFF(minute, fle.FLE_DTHR_CHEGADA, GETDATE())   AS espera_min,
            fle.FLE_PREFERENCIAL                                AS preferencial,
            agmx.AGM_SMK                                        AS servico
        FROM fle
        JOIN pac ON pac.pac_reg = fle.FLE_PAC_REG
        OUTER APPLY (
            SELECT TOP 1 a.AGM_SMK
            FROM agm a
            WHERE a.agm_med = fle.FLE_PSV_COD
              AND a.agm_pac = fle.FLE_PAC_REG
              AND CAST(a.agm_hini AS DATE) = CAST(fle.FLE_DTHR_CHEGADA AS DATE)
            ORDER BY a.agm_hini DESC
        ) agmx
        WHERE fle.FLE_PSV_COD = {medico}
          AND CAST(fle.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
          AND fle.FLE_STATUS = 'A'
        ORDER BY fle.FLE_PREFERENCIAL DESC, fle.FLE_DTHR_CHEGADA ASC
    """)
    for r in rows:
        if r.get("servico") is not None:
            r["servico"] = str(r["servico"]).strip()
    return {"medico": medico, "data": hoje, "total": len(rows), "fila": rows}

# ─── Registro Clínico (RCL) — labels e templates de formulário ────────────────
# Ver "Pixeon Smart - Mapeamento Registro Clinico.txt" (Desktop) para o
# levantamento completo. Campos e tipos confirmados com exemplos reais de
# produção (não confiar cegamente no tipo declarado no RTF do DSC).
_CAMPOS_COMPARTILHADOS_3319 = {
    "2": "Outros (antecedentes)", "3": "Queixa Principal", "4": "Exame Físico",
    "6": "Hipótese Diagnóstica", "7": "Conduta (resumo)",
    "10": "Antecedente: Asma", "11": "Antecedente: Coronariopatia",
    "12": "Antecedente: Diabetes", "13": "Antecedente: Distúrbio Psiquiátrico",
    "14": "Antecedente: Etilismo", "15": "Antecedente: Hipertensão",
    "16": "Antecedente: Tabagismo", "17": "Antecedente: Tireopatia",
    "18": "Antecedente: Transfusão", "19": "Antecedente: Outros",
    "20": "CID / Diagnóstico", "29": "Exames Solicitados",
    "30": "Medicamento Prescrito", "31": "Conduta / Planejamento",
    "32": "Encaminhamento", "33": "Data",
}
CAMPO_LABELS = {
    "CONSCLIN": {**_CAMPOS_COMPARTILHADOS_3319, "1": "Acidente de Trabalho"},
    "CONSPED":  {**_CAMPOS_COMPARTILHADOS_3319, "1": "Peso (kg)", "26": "Estatura (cm)", "28": "PC (cm)"},
    "CONSNUTR": dict(_CAMPOS_COMPARTILHADOS_3319),
    "CONSORT":  dict(_CAMPOS_COMPARTILHADOS_3319),
    "CONPSIQ":  dict(_CAMPOS_COMPARTILHADOS_3319),
    "RETORNO":  {"1": "Evolução"},
    "AVOFTAL": {
        "1": "OD Longe Sem Correção", "2": "OD Longe Com Correção",
        "3": "OE Longe Sem Correção", "4": "OE Longe Com Correção",
        "5": "OD Perto Sem Correção", "6": "OD Perto Com Correção",
        "7": "OE Perto Sem Correção", "8": "OE Perto Com Correção",
        "9": "Biomicroscopia OD", "13": "Biomicroscopia OE",
        "17": "Tonometria OD", "18": "Tonometria OE",
        "19": "Fundoscopia OD", "23": "Fundoscopia OE",
        "27": "Motilidade", "31": "Senso Cromático", "32": "Visão Estereoscópica",
        "41": "Visão Noturna", "42": "Teste de Ofuscamento", "43": "Campimetria",
        "45": "Ishihara Verde", "46": "Ishihara Vermelho", "47": "Ishihara Amarelo",
        "33": "Conclusão", "40": "Observação",
    },
}

# Templates de formulário para ESCRITA — só os 4 serviços validados ponta a
# ponta (insert testado em smart_hml + conferido visualmente no Smart).
FORM_TEMPLATES = {
    "CONSCLIN": {"modelo": 3654, "nome": "Consulta Clínica", "campos": [
        {"campo":"3","tipo":"O","rotulo":"Queixa Principal","input":"textarea"},
        {"campo":"4","tipo":"O","rotulo":"Exame Físico","input":"textarea"},
        {"campo":"6","tipo":"O","rotulo":"Hipótese Diagnóstica","input":"textarea"},
        {"campo":"7","tipo":"O","rotulo":"Conduta (resumo)","input":"textarea"},
        {"campo":"2","tipo":"O","rotulo":"Outros (Antecedentes)","input":"textarea"},
        {"campo":"20","tipo":"C","rotulo":"CID / Diagnóstico","input":"cid"},
        {"campo":"29","tipo":"O","rotulo":"Exames Solicitados","input":"textarea"},
        {"campo":"30","tipo":"O","rotulo":"Medicamento Prescrito","input":"textarea"},
        {"campo":"31","tipo":"O","rotulo":"Conduta / Planejamento","input":"textarea"},
        {"campo":"32","tipo":"O","rotulo":"Encaminhamento","input":"text"},
        {"campo":"33","tipo":"&","rotulo":"Retorno Para (mês/ano, ex: 08/2026)","input":"text"},
    ]},
    "CONSPED": {"modelo": 3319, "nome": "Consulta Pediátrica", "campos": [
        {"campo":"1","tipo":"&","rotulo":"Peso (kg)","input":"text"},
        {"campo":"26","tipo":"O","rotulo":"Estatura (cm)","input":"text"},
        {"campo":"28","tipo":"O","rotulo":"PC (cm)","input":"text"},
        {"campo":"3","tipo":"O","rotulo":"Queixa Principal","input":"textarea"},
        {"campo":"7","tipo":"O","rotulo":"Conduta","input":"textarea"},
        {"campo":"2","tipo":"O","rotulo":"Outros (Antecedentes)","input":"textarea"},
        {"campo":"20","tipo":"C","rotulo":"CID / Diagnóstico","input":"cid"},
        {"campo":"30","tipo":"O","rotulo":"Medicamento Prescrito","input":"textarea"},
        {"campo":"31","tipo":"O","rotulo":"Conduta / Planejamento","input":"textarea"},
        {"campo":"32","tipo":"O","rotulo":"Encaminhamento","input":"text"},
    ]},
    "AVOFTAL": {"modelo": 1850, "nome": "Avaliação Oftalmológica", "campos": [
        {"campo":"1","tipo":"&","rotulo":"OD Longe Sem Correção","input":"text"},
        {"campo":"2","tipo":"&","rotulo":"OD Longe Com Correção","input":"text"},
        {"campo":"3","tipo":"&","rotulo":"OE Longe Sem Correção","input":"text"},
        {"campo":"4","tipo":"&","rotulo":"OE Longe Com Correção","input":"text"},
        {"campo":"5","tipo":"&","rotulo":"OD Perto Sem Correção","input":"text"},
        {"campo":"6","tipo":"&","rotulo":"OD Perto Com Correção","input":"text"},
        {"campo":"7","tipo":"&","rotulo":"OE Perto Sem Correção","input":"text"},
        {"campo":"8","tipo":"&","rotulo":"OE Perto Com Correção","input":"text"},
        {"campo":"9","tipo":"&","rotulo":"Biomicroscopia OD","input":"textarea"},
        {"campo":"13","tipo":"&","rotulo":"Biomicroscopia OE","input":"textarea"},
        {"campo":"17","tipo":"%","rotulo":"Tonometria OD","input":"text"},
        {"campo":"18","tipo":"%","rotulo":"Tonometria OE","input":"text"},
        {"campo":"19","tipo":"&","rotulo":"Fundoscopia OD","input":"textarea"},
        {"campo":"23","tipo":"&","rotulo":"Fundoscopia OE","input":"textarea"},
        {"campo":"27","tipo":"&","rotulo":"Motilidade","input":"text"},
        {"campo":"31","tipo":"&","rotulo":"Senso Cromático","input":"select","opcoes":["Sem Alterações"]},
        {"campo":"32","tipo":"&","rotulo":"Visão Estereoscópica","input":"select","opcoes":["Sem Alterações"]},
        {"campo":"41","tipo":"&","rotulo":"Visão Noturna","input":"select","opcoes":["Sem Alterações"]},
        {"campo":"42","tipo":"&","rotulo":"Teste de Ofuscamento","input":"select","opcoes":["Sem Alterações"]},
        {"campo":"43","tipo":"&","rotulo":"Campimetria","input":"text"},
        {"campo":"45","tipo":"&","rotulo":"Ishihara Verde","input":"select","opcoes":["Sim","Não"]},
        {"campo":"46","tipo":"&","rotulo":"Ishihara Vermelho","input":"select","opcoes":["Sim","Não"]},
        {"campo":"47","tipo":"&","rotulo":"Ishihara Amarelo","input":"select","opcoes":["Sim","Não"]},
        {"campo":"33","tipo":"O","rotulo":"Conclusão","input":"textarea"},
        {"campo":"40","tipo":"O","rotulo":"Observação","input":"textarea"},
    ]},
    "RETORNO": {"modelo": 8224, "nome": "Consulta de Retorno", "campos": [
        {"campo":"1","tipo":"O","rotulo":"Evolução","input":"textarea"},
    ]},
}

def _parse_rcl_txt(txt: str):
    """Extrai [{campo, tipo, valor}] de um RCL_TXT no formato @#modelo@campoTIPOvalor..."""
    if not txt:
        return []
    padrao = _re.compile(r'^(\d+)@(\d+)([A-Za-z&%])(.*)$', _re.DOTALL)
    resultado = []
    for parte in txt.split("@#")[1:]:
        m = padrao.match(parte)
        if m:
            _modelo, campo, tipo, valor = m.groups()
            valor = valor.strip()
            if valor:
                resultado.append({"campo": campo, "tipo": tipo, "valor": valor})
    return resultado

@app.get("/api/atendimento/buscar-cid")
def atendimento_buscar_cid(q: str, limite: int = 15):
    """Busca na tabela CID (catálogo CID-10, ~23.6k linhas) por código ou nome —
    usado no campo CID/Diagnóstico do formulário de atendimento."""
    termo = q.strip()
    if len(termo) < 2:
        return {"total": 0, "resultados": []}
    rows = query(f"""
        SELECT TOP {limite} RTRIM(CID_COD) AS codigo, RTRIM(ISNULL(CID_NOME,'')) AS nome
        FROM CID
        WHERE (CID_DEL_LOGICA IS NULL OR CID_DEL_LOGICA <> 'S')
          AND (RTRIM(CID_COD) LIKE ? OR CID_NOME LIKE ?)
        ORDER BY LEN(RTRIM(CID_COD)), RTRIM(CID_COD)
    """, (f"{termo}%", f"%{termo}%"))
    for r in rows:
        r["nome"] = r["nome"].split("|")[0].strip()[:120]
    return {"total": len(rows), "resultados": rows}

@app.get("/api/atendimento/buscar-paciente")
def atendimento_buscar_paciente(q: str, limite: int = 15):
    """Busca no cadastro (produção) por nome, nº de registro ou CPF — usado
    quando o paciente não está na fila (ex: sem check-in hoje, atendimento
    avulso)."""
    termo = q.strip()
    if len(termo) < 2:
        return {"total": 0, "pacientes": []}

    so_digitos = _re.sub(r"\D", "", termo)
    if so_digitos and len(so_digitos) >= 5:
        pac_reg_val = int(so_digitos) if int(so_digitos) <= 2147483647 else -1
        rows = query(f"""
            SELECT TOP {limite}
                pac_reg                              AS pac_reg,
                RTRIM(pac_nome)                       AS nome,
                CONVERT(varchar, PAC_NASC, 23)         AS nascimento,
                RTRIM(ISNULL(PAC_NUMCPF,''))          AS cpf
            FROM pac
            WHERE pac_reg = ?
               OR REPLACE(REPLACE(ISNULL(PAC_NUMCPF,''),'.',''),'-','') LIKE ?
            ORDER BY pac_nome
        """, (pac_reg_val, f"%{so_digitos}%"))
    else:
        rows = query(f"""
            SELECT TOP {limite}
                pac_reg                              AS pac_reg,
                RTRIM(pac_nome)                       AS nome,
                CONVERT(varchar, PAC_NASC, 23)         AS nascimento,
                RTRIM(ISNULL(PAC_NUMCPF,''))          AS cpf
            FROM pac
            WHERE pac_nome LIKE ?
            ORDER BY pac_nome
        """, (f"%{termo}%",))
    return {"total": len(rows), "pacientes": rows}

@app.get("/api/atendimento/paciente/{pac_reg}")
def atendimento_paciente(pac_reg: int):
    rows = query("""
        SELECT
            pac.pac_reg                                    AS pac_reg,
            RTRIM(pac.pac_nome)                             AS nome,
            CONVERT(varchar, pac.PAC_NASC, 23)               AS nascimento,
            RTRIM(ISNULL(pac.PAC_SEXO,''))                  AS sexo,
            RTRIM(ISNULL(pac.PAC_CELULAR, pac.PAC_FONE))     AS telefone,
            RTRIM(ISNULL(pac.PAC_CNV,''))                   AS convenio_cod,
            RTRIM(ISNULL(cnv.CNV_NOME,''))                  AS convenio_nome,
            RTRIM(ISNULL(cnv.CNV_REG_ANS,''))               AS convenio_reg_ans,
            RTRIM(ISNULL(pac.PAC_MCNV,''))                  AS carteirinha
        FROM pac
        LEFT JOIN cnv ON RTRIM(cnv.cnv_cod) = RTRIM(pac.PAC_CNV)
        WHERE pac.pac_reg = ?
    """, (pac_reg,))
    if not rows:
        raise HTTPException(404, "Paciente não encontrado")
    return rows[0]

@app.get("/api/atendimento/clinica")
def atendimento_clinica():
    """Dados da clínica (CNES/CNPJ) para o cabeçalho da guia SP/SADT."""
    rows = query("""
        SELECT TOP 1
            RTRIM(ISNULL(EMP_NOME_FANTASIA,''))  AS nome,
            RTRIM(ISNULL(EMP_CNES,''))           AS cnes,
            RTRIM(ISNULL(EMP_CGC,''))            AS cnpj
        FROM EMP WHERE EMP_COD = 1
    """)
    return rows[0] if rows else {"nome": "", "cnes": "", "cnpj": ""}

@app.get("/api/atendimento/buscar-convenio")
def atendimento_buscar_convenio(q: str, limite: int = 15):
    """Busca convênios ativos por nome ou código — usado pra trocar o
    convênio usado na guia SP/SADT sem alterar o cadastro do paciente."""
    termo = q.strip()
    if len(termo) < 2:
        return {"total": 0, "resultados": []}
    rows = query(f"""
        SELECT TOP {limite}
            RTRIM(cnv_cod)                    AS codigo,
            RTRIM(cnv_nome)                    AS nome,
            RTRIM(ISNULL(CNV_REG_ANS,''))      AS reg_ans,
            CNV_IND_TISS                       AS tiss
        FROM cnv
        WHERE cnv_stat = 'A' AND (cnv_nome LIKE ? OR RTRIM(cnv_cod) LIKE ?)
        ORDER BY CASE WHEN CNV_IND_TISS = 'S' THEN 0 ELSE 1 END, cnv_nome
    """, (f"%{termo}%", f"{termo}%"))
    return {"total": len(rows), "resultados": rows}

@app.get("/api/atendimento/buscar-procedimento")
def atendimento_buscar_procedimento(q: str, limite: int = 15):
    """Busca no catálogo de serviços (SMK) por nome ou código TUSS —
    usado para montar a lista de procedimentos da guia SP/SADT."""
    termo = q.strip()
    if len(termo) < 2:
        return {"total": 0, "resultados": []}
    rows = query(f"""
        SELECT TOP {limite}
            RTRIM(SMK_COD)                        AS codigo,
            RTRIM(ISNULL(SMK_COD_TUSS,''))         AS tuss,
            RTRIM(ISNULL(SMK_NOME,''))             AS nome
        FROM SMK
        WHERE SMK_COD_TUSS IS NOT NULL AND RTRIM(SMK_COD_TUSS) <> ''
          AND (SMK_NOME LIKE ? OR RTRIM(SMK_COD_TUSS) LIKE ? OR RTRIM(SMK_COD) LIKE ?)
        ORDER BY LEN(SMK_NOME)
    """, (f"%{termo}%", f"{termo}%", f"{termo}%"))
    return {"total": len(rows), "resultados": rows}

@app.get("/api/atendimento/medico/{psv_cod}")
def atendimento_medico(psv_cod: int):
    """Dados do médico para cabeçalho de documentos (atestado/declaração)."""
    rows = query("""
        SELECT
            psv_cod                                     AS psv_cod,
            RTRIM(ISNULL(PSV_TRAT,''))                  AS tratamento,
            RTRIM(psv_nome)                              AS nome,
            PSV_CRM                                     AS crm,
            RTRIM(ISNULL(PSV_CONSELHO,'CRM'))           AS conselho,
            RTRIM(ISNULL(PSV_UF,''))                    AS uf
        FROM psv WHERE psv_cod = ?
    """, (psv_cod,))
    if not rows:
        raise HTTPException(404, "Médico não encontrado")
    return rows[0]

@app.get("/api/atendimento/historico")
def atendimento_historico(paciente: int, limite: int = 20):
    """Últimos registros clínicos (RCL) do paciente, lidos da PRODUÇÃO (só leitura)."""
    rows = query(f"""
        SELECT TOP {limite}
            RTRIM(RCL.RCL_COD)      AS servico,
            RCL.RCL_DTHR            AS data,
            RTRIM(ISNULL(psv.psv_apel,'')) AS medico,
            RTRIM(RCL.RCL_USR_LOGIN) AS lancado_por,
            CAST(RCL.RCL_TXT AS VARCHAR(MAX)) AS txt
        FROM RCL
        LEFT JOIN psv ON psv.psv_cod = RCL.RCL_MED
        WHERE RCL.RCL_PAC = ? AND RCL.RCL_STAT = 'L'
        ORDER BY RCL.RCL_DTHR DESC
    """, (paciente,))
    historico = []
    for r in rows:
        servico = (r["servico"] or "").strip()
        labels = CAMPO_LABELS.get(servico, {})
        campos = []
        for c in _parse_rcl_txt(r["txt"]):
            campos.append({
                "campo":  c["campo"],
                "rotulo": labels.get(c["campo"], f'Campo {c["campo"]}'),
                "valor":  c["valor"],
            })
        historico.append({
            "servico": servico, "data": r["data"], "medico": r["medico"],
            "lancado_por": r["lancado_por"], "campos": campos,
        })
    return {"paciente": paciente, "total": len(historico), "historico": historico}

class PublicoResultadosRequest(BaseModel):
    cpf: str
    nascimento: str  # "YYYY-MM-DD"

@app.post("/api/publico/resultados")
def publico_resultados(req: PublicoResultadosRequest, request: Request):
    """
    Portal do paciente (sem login de funcionário): identifica pelo CPF + data
    de nascimento e retorna os exames INTERNOS (feitos na própria clínica,
    tabela RCL) já liberados. Exames terceirizados (DB Diagnósticos) ficam de
    fora até a integração externa (BarramentoDB) estar ativa.
    """
    ip = request.client.host if request.client else "unknown"
    _rate_limit_check(ip)

    cpf_digits = _re.sub(r"\D", "", req.cpf or "")
    if len(cpf_digits) != 11 or not req.nascimento:
        _rate_limit_register(ip, success=False)
        raise HTTPException(400, "Informe CPF e data de nascimento válidos.")

    rows = query("""
        SELECT pac_reg AS pac_reg, RTRIM(pac_nome) AS nome
        FROM pac
        WHERE REPLACE(REPLACE(ISNULL(PAC_NUMCPF,''),'.',''),'-','') = ?
          AND CONVERT(varchar, PAC_NASC, 23) = ?
    """, (cpf_digits, req.nascimento))

    if not rows:
        _rate_limit_register(ip, success=False)
        # Mensagem genérica — não revela se o CPF existe ou só a data está errada.
        raise HTTPException(404, "CPF ou data de nascimento não conferem.")

    _rate_limit_register(ip, success=True)
    # CPF+nascimento pode bater com mais de um cadastro (cadastro duplicado,
    # comum na base) — busca o exame em TODOS os pac_reg encontrados, não só
    # no primeiro, senão o resultado pode estar "escondido" no outro cadastro.
    pac_regs = [r["pac_reg"] for r in rows]
    nome = rows[0]["nome"]

    # Só exames de LABORATÓRIO (código presente na tabela SBN, que vincula
    # exame -> bancada) — exclui consultas clínicas (CONSCLIN/CONSPED/
    # AVOFTAL/RETORNO) e documentos ocupacionais (ASO/ECG/EXAMED), que também
    # ficam na RCL mas não são "resultado de exame".
    placeholders = ",".join("?" for _ in pac_regs)
    rcl_rows = query(f"""
        SELECT TOP 50
            RTRIM(RCL.RCL_COD)       AS codigo,
            RTRIM(ISNULL(smk.SMK_NOME, RCL.RCL_COD)) AS servico,
            RCL.RCL_DTHR             AS data,
            RTRIM(ISNULL(psv.psv_apel,'')) AS medico,
            RTRIM(ISNULL(RCL.RCL_VLR_RESULT,'')) AS valor,
            CAST(RCL.RCL_TXT AS VARCHAR(MAX)) AS txt
        FROM RCL
        JOIN (SELECT DISTINCT RTRIM(SBN_SMK_COD) AS cod FROM SBN) lab
            ON lab.cod = RTRIM(RCL.RCL_COD)
        LEFT JOIN SMK smk ON RTRIM(smk.SMK_COD) = RTRIM(RCL.RCL_COD)
        LEFT JOIN psv ON psv.psv_cod = RCL.RCL_MED
        WHERE RCL.RCL_PAC IN ({placeholders}) AND RCL.RCL_DTHR_LIB IS NOT NULL
        ORDER BY RCL.RCL_DTHR DESC
    """, tuple(pac_regs))

    resultados = []
    for r in rcl_rows:
        codigo = (r["codigo"] or "").strip()
        valor = (r["valor"] or "").strip()
        # O número de "campo" só é único dentro de formulários de consulta
        # (CAMPO_LABELS); em exames de painel (ex: rotina de urina) o mesmo
        # número se repete em seções diferentes do exame, então nesses casos
        # numeramos pela posição sequencial em vez do número de campo bruto
        # — senão vira vários "Campo 1" empilhados, parecendo duplicado/erro.
        labels = CAMPO_LABELS.get(codigo)
        campos = [
            {
                "rotulo": labels.get(c["campo"], f'Campo {c["campo"]}') if labels else f'Resultado {i}',
                # Remove sufixo interno de método/equipamento do laboratório
                # (ex: "29000@MET;0001" -> "29000") — não faz sentido pro paciente.
                "valor": _re.sub(r'@[A-Za-z]+;?\d*$', '', c["valor"]),
            }
            for i, c in enumerate(_parse_rcl_txt(r["txt"]), 1)
        ]
        if campos or valor:
            resultados.append({
                "servico": r["servico"], "data": r["data"], "medico": r["medico"],
                "valor": valor, "campos": campos,
            })

    return {
        "nome": nome.split()[0],
        "total": len(resultados),
        "resultados": resultados,
    }

@app.get("/api/laboratorio/db-diagnosticos/status")
def db_diagnosticos_status(osm_serie: int, osm_num: int):
    """
    Consulta o status de um pedido enviado à DB Diagnósticos (bancada externa).
    Só leitura — o envio do pedido já é feito pelo próprio Smart Pixeon.
    Endpoint de uso interno (staff), ainda em validação com credenciais de
    homologação — não usar com OS de paciente real até confirmar produção.
    """
    if not _DB_DIAG_AVAILABLE:
        raise HTTPException(503, "Integração DB Diagnósticos indisponível.")
    numero = f"{osm_serie}.{osm_num}"
    try:
        return consultar_status(numero)
    except Exception as e:
        raise HTTPException(502, f"Erro ao consultar DB Diagnósticos: {e}")

@app.get("/api/atendimento/template")
def atendimento_template(servico: str = None):
    """Templates de formulário disponíveis para atendimento pela plataforma."""
    if servico:
        t = FORM_TEMPLATES.get(servico.strip().upper())
        if not t:
            raise HTTPException(404, f"Serviço '{servico}' ainda não tem formulário mapeado.")
        return {"servico": servico.strip().upper(), **t}
    return {k: {"modelo": v["modelo"], "nome": v["nome"]} for k, v in FORM_TEMPLATES.items()}

class AtendimentoSalvarRequest(BaseModel):
    paciente: int
    medico:   int
    servico:  str
    login:    str
    campos:   dict

@app.post("/api/atendimento/salvar")
def atendimento_salvar(req: AtendimentoSalvarRequest):
    """
    Grava um novo Registro Clínico (RCL) — SOMENTE em smart_hml (homologação),
    nunca em produção, até validação/aprovação extensa (ver seção 7 do arquivo
    de mapeamento). Formato de RCL_TXT e requisitos de FK documentados lá.
    """
    servico = req.servico.strip().upper()
    template = FORM_TEMPLATES.get(servico)
    if not template:
        raise HTTPException(400, f"Serviço '{servico}' ainda não mapeado para atendimento pela plataforma.")

    modelo = template["modelo"]
    campos_validos = {c["campo"]: c for c in template["campos"]}
    partes = []
    for campo_id, valor in req.campos.items():
        campo_id = str(campo_id).strip()
        valor = str(valor or "").strip()
        campo_def = campos_validos.get(campo_id)
        if not campo_def or not valor:
            continue
        partes.append(f"@#{modelo}@{campo_id}{campo_def['tipo']}{valor}")

    if not partes:
        raise HTTPException(400, "Nenhum campo preenchido.")

    rcl_txt = "".join(partes)
    agora = datetime.now()

    try:
        conn = get_conn_hml()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO RCL (
                RCL_PAC, RCL_TPCOD, RCL_COD, RCL_DTHR, RCL_MED,
                RCL_STAT, RCL_TXT, RCL_USR_LOGIN, RCL_RESULT,
                RCL_USR_LOGIN_LIB, RCL_DTHR_LIB, RCL_USR_LOGIN_DIGIT,
                RCL_DTHR_DIGIT, RCL_CONCLUSAO, RCL_VLR_RESULT
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            req.paciente, "S", servico, agora, req.medico,
            "L", rcl_txt, req.login, "N",
            req.login, agora, req.login,
            agora, "?", "Inconclusivo",
        ))
        conn.commit()
        conn.close()
    except pyodbc.Error as e:
        raise HTTPException(400, f"Erro ao gravar em smart_hml: {e}")

    return {"ok": True, "ambiente": "smart_hml", "servico": servico, "rcl_txt": rcl_txt}

@app.get("/api/debug/scheduler-status")
def debug_scheduler_status():
    try:
        from scheduler import _query_func, _horarios_configurados, _carregar_config_wpp
        cfg = _carregar_config_wpp()
        return {
            "query_func_ok": _query_func is not None,
            "horarios": [f"{h:02d}:{m:02d} ({t})" for h,m,t in _horarios_configurados(cfg)],
        }
    except Exception as e:
        return {"erro": str(e)}
    
@app.get("/api/debug/esp-multiprofissional")
def debug_esp_multiprofissional():
    hoje = datetime.now().strftime("%Y-%m-%d")
    return query(f"""
        SELECT DISTINCT
            RTRIM(psv.psv_apel)                     AS apelido,
            RTRIM(ISNULL(psv.psv_esp_cod,''))       AS esp_cod,
            RTRIM(ISNULL(esp.esp_nome,''))          AS especialidade,
            psv.psv_cod                             AS psv_cod
        FROM agm
        JOIN psv ON psv.psv_cod = agm.agm_med
        LEFT JOIN esp ON esp.esp_cod = psv.psv_esp_cod
        WHERE CAST(agm.agm_hini AS DATE) = '{hoje}'
          AND agm.agm_pac > 0
        ORDER BY psv.psv_apel
    """)
"""
═══════════════════════════════════════════════════════════════════════════════
ENDPOINTS — Módulo PacientesDB
Cole este bloco no main.py, antes do endpoint /api/health

Tabelas validadas no banco:
  pac         → pac_reg, pac_nome, pac_nasc, pac_sexo, pac_dreg, pac_dult,
                pac_dt_obito, PAC_END (logradouro), PAC_CID (cód. cidade)
  osm         → osm_pac, osm_dthr, osm_cnv, osm_serie, osm_num
  cnv         → cnv_cod, cnv_nome
  PAC_END_COL → PAC_END_COL_PAC_REG (FK pac), PAC_END_COL_END (logradouro)

NOTA SOBRE BAIRROS:
  O banco não possui campo de bairro estruturado.
  PAC_END contém texto livre ("RUA H", "RUA G12", "goitacaz, lt 9, qd 29").
  A estratégia adotada é normalizar o logradouro para extrair o nome da rua/via
  como agrupador — funciona bem para Parauapebas (ruas identificadas por letras).
═══════════════════════════════════════════════════════════════════════════════
"""




def _normalizar_rua(end: str) -> str:
    """
    Normaliza texto livre de endereço para extrair o nome/identificador da via.
    Exemplos:
      "RUA H"              → "Rua H"
      "RUA G12"            → "Rua G12"
      "AV Q QD 238 LT 03"  → "Av Q"
      "goitacaz, lt 9"     → "Goitacaz"
      "h"                  → "Rua H"   (letra solta vira rua)
      ""                   → "Não informado"
    """
    if not end or not end.strip():
        return "Não informado"

    s = end.strip().upper()

    # Remove prefixos repetidos
    for prefix in ["RUA:", "RUA ", "R ", "R. ", "AV ", "AV. ", "AVENIDA ", "TRAVESSA ", "TRV "]:
        if s.startswith(prefix):
            tipo = "Rua" if "RUA" in prefix or prefix in ("R ", "R. ") else \
                   "Av"  if "AV"  in prefix else "Tv"
            resto = s[len(prefix):].strip()
            # Pega só o nome/identificador da via (antes de QD, LT, Nº, vírgula)
            nome = _re.split(r'[\s,]+(?:QD|LT|Q\d|LOT|LOTE|N[Oº]|\d{2,})', resto)[0].strip()
            return f"{tipo} {nome.title()}" if nome else "Não informado"

    # Letra solta (ex: "H", "W") → "Rua X"
    if _re.fullmatch(r'[A-Z]', s):
        return f"Rua {s}"

    # Número + letra (ex: "G12", "B5")
    if _re.fullmatch(r'[A-Z]\d+', s):
        return f"Rua {s.title()}"

    # Caso geral: pega até a primeira vírgula ou QD/LT
    nome = _re.split(r'[\s,]+(?:QD|LT|Q\d|LOT|LOTE|N[Oº]|\d{3,})', s)[0].strip()
    return nome.title() if nome else "Não informado"


# ─── MAPA DE CALOR: DISTRIBUIÇÃO POR LOGRADOURO ──────────────────────────────

# ══════════════════════════════════════════════════════════════════════════════
# MAPEAMENTO RUA → BAIRRO (Correios Parauapebas - PA)
# Fonte: Lista de CEPs Parauapebas nov/2025
# ══════════════════════════════════════════════════════════════════════════════

_MAPA_BAIRRO = {
    # Ruas numeradas com zero à esquerda → Cidade Nova
    "rua 01":"Cidade Nova","rua 02":"Cidade Nova","rua 03":"Cidade Nova",
    "rua 04":"Cidade Nova","rua 05":"Cidade Nova","rua 06":"Cidade Nova",
    "rua 07":"Cidade Nova","rua 08":"Cidade Nova","rua 09":"Cidade Nova",
    # Avenidas identificadas
    "av brasil":"Rio Verde","av para":"Liberdade I",
    "av jk":"Rio Verde","av buriti":"Liberdade I",
    "av castanheira":"Cidade Jardim","av princesa isabel":"Liberdade I",
    "av gabriel pimenta":"Rio Verde","av imperatriz":"Maranhão",
    "av cristo rei":"Apoena","av cristo reis":"Apoena",
    "av apostolo paulo":"Betânia","av paru":"Polo Moveleiro",
    "av castelo branco":"Rio Verde","av pernambuco":"Liberdade I",
    # Ruas por letra → Bairro União
    "rua a":"União","rua b":"União","rua c":"União","rua d":"União",
    "rua e":"União","rua f":"União","rua g":"União","rua h":"União",
    "rua i":"União","rua j":"União","rua k":"União","rua l":"União",
    "rua m":"União","rua n":"União","rua o":"União","rua p":"União",
    "rua q":"União","rua r":"União","rua s":"União","rua t":"União",
    "rua u":"União","rua v":"União","rua w":"União","rua x":"União",
    "rua y":"União","rua z":"União",
    # Letras soltas → União
    "a":"União","b":"União","c":"União","d":"União","e":"União",
    "f":"União","g":"União","h":"União","i":"União","j":"União",
    "k":"União","l":"União","m":"União","n":"União","o":"União",
    "p":"União","q":"União","r":"União","s":"União","t":"União",
    "u":"União","v":"União","w":"União","x":"União","y":"União","z":"União",
    # Ruas numeradas → Cidade Nova
    "rua 1":"Cidade Nova","rua 2":"Cidade Nova","rua 3":"Cidade Nova",
    "rua 4":"Cidade Nova","rua 5":"Cidade Nova","rua 6":"Cidade Nova",
    "rua 7":"Cidade Nova","rua 8":"Cidade Nova","rua 9":"Cidade Nova",
    "rua 10":"Cidade Nova","rua 11":"Cidade Nova","rua 12":"Cidade Nova",
    "rua 13":"Cidade Nova","rua 14":"Cidade Nova","rua 15":"Cidade Nova",
    "rua 16":"Cidade Nova","rua 17":"Cidade Nova","rua 18":"Cidade Nova",
    "rua 19":"Cidade Nova","rua 20":"Cidade Nova",
    # Ruas numeradas em Primavera
    "rua 1 primavera":"Primavera","rua 2 primavera":"Primavera",
    # Avenidas letradas → Maranhão / Beira Rio
    "av a":"Maranhão","av i":"Beira Rio","av q":"Maranhão",
    "avenida a":"Maranhão","avenida i":"Beira Rio",
    # Ruas com nome — mapeadas do PDF dos Correios
    "angela diniz":"Guanabara","angela diniz":"da Paz",
    "araguaia":"da Paz",
    "jatoba":"Parque dos Carajás","jatoба":"Parque dos Carajás",
    "arara":"Parque dos Carajás",
    "goitacaz":"Parque dos Carajás",
    "bororo":"Parque dos Carajás",
    "espanha":"Vila Rica",
    "belem":"Palmares Sul",
    "sao luis":"Primavera","são luis":"Primavera","são luís":"Primavera",
    "sao marcos":"Betânia","são marcos":"Betânia",
    "daniela perez":"Nova Vida",
    "tocantins":"Rio Verde",
    "santa maria":"Guanabara",
    "bela vista":"Rio Verde",
    "manoel bandeira":"da Paz",
    "fortaleza":"Rio Verde",
    "gaspar viana":"Liberdade II",
    "teotonio vilela":"Liberdade I","teotônio vilela":"Liberdade I",
    "manaus":"Primavera",
    "gervásio antônio morás":"Jardim América",
    "gervásio moraes":"Jardim América",
    "liberdade":"da Paz",
    "sol poente":"da Paz",
    "bom jardim":"Guanabara",
    "graça aranha":"Guanabara",
    "jorge amado":"Guanabara",
    "rui barbosa":"Guanabara",
    "mané garrincha":"Guanabara",
    "chico mendes":"da Paz",
    "marabá":"da Paz",
    "castro alves":"da Paz",
    "araguaia":"da Paz",
    "paz":"da Paz",
    "tiradentes":"Rio Verde",
    "getúlio vargas":"Rio Verde","getulio vargas":"Rio Verde",
    "tocantins":"Rio Verde",
    "ceará":"Rio Verde","ceara":"Rio Verde",
    "amazonas":"Rio Verde",
    "minas gerais":"Rio Verde",
    "paraíso":"Paraíso","paraiso":"Paraíso",
    "esplanada":"Esplanada",
    "linha verde":"Linha Verde",
    "caetanópolis":"Caetanópolis","caetanopolis":"Caetanópolis",
    "guanabara":"Guanabara",
    "morada nova":"Morada Nova",
    "jardim america":"Jardim América","jardim américa":"Jardim América",
    "parque carajás":"Parque dos Carajás","parque dos carajas":"Parque dos Carajás",
    "parque nacoes":"Parque das Nações","parque nações":"Parque das Nações",
    "sao lucas":"São Lucas","são lucas":"São Lucas",
    "santa luzia":"Santa Luzia",
    "nova carajas":"Nova Carajás","nova carajás":"Nova Carajás",
    "nova vida":"Nova Vida",
    "beira rio":"Beira Rio",
    "brasilia":"Brasília","brasília":"Brasília",
    "jardim planalto":"Jardim Planalto",
    "jardim canada":"Jardim Canadá","jardim canadá":"Jardim Canadá",
    "apoena":"Apoena",
    "amazonia":"Amazônia","amazônia":"Amazônia",
    "novo brasil":"Novo Brasil",
    "alvorada":"Alvorada","alvorá":"Alvorada",
    "minerios":"Minérios","minérios":"Minérios",
    "polo industrial":"Polo Industrial",
    "polo moveleiro":"Polo Moveleiro",
    "tropical":"Tropical",
    "betania":"Betânia","betânia":"Betânia",
    "habitar feliz":"Habitar Feliz",
    "novo horizonte":"Novo Horizonte",
    "novo viver":"Novo Viver",
    "vale do sol":"Vale do Sol",
    "vila rica":"Vila Rica",
    "fap":"FAP",
    "palmares ii":"Palmares II","palmares 2":"Palmares II",
    "palmares sul":"Palmares Sul",
    "cidade jardim":"Cidade Jardim",
    "cidade nova":"Cidade Nova",
    "primavera":"Primavera",
    "maranhao":"Maranhão","maranhão":"Maranhão",
    "liberdade i":"Liberdade I","liberdade 1":"Liberdade I",
    "liberdade ii":"Liberdade II","liberdade 2":"Liberdade II",
    "rio verde":"Rio Verde",
    "uniao":"União","união":"União",
}

def _rua_para_bairro(end_raw: str) -> str:
    """
    Tenta mapear o logradouro do paciente para um bairro real de Parauapebas.
    Usa o dicionário dos Correios. Retorna o bairro ou None se não encontrar.
    """
    if not end_raw or not end_raw.strip():
        return None

    s = end_raw.strip().lower()

    # Remove prefixos de tipo de logradouro
    for pfx in ["rua:", "r. ", "r ", "av. ", "av ", "avenida ", "travessa ", "tv ", "trv "]:
        if s.startswith(pfx):
            s_sem = s[len(pfx):].strip()
            # Tenta com prefixo original também
            chave_com = s.rstrip()
            if chave_com in _MAPA_BAIRRO:
                return _MAPA_BAIRRO[chave_com]
            # Pega só o nome (antes de QD, LT, número grande)
            import re as _re2
            nome = _re2.split(r'[,\s]+(?:qd|lt|q\d|lot|lote|n[oº]|\d{2,})', s_sem)[0].strip()
            if nome in _MAPA_BAIRRO:
                return _MAPA_BAIRRO[nome]
            if s_sem in _MAPA_BAIRRO:
                return _MAPA_BAIRRO[s_sem]
            break

    # Tenta match direto
    if s in _MAPA_BAIRRO:
        return _MAPA_BAIRRO[s]

    # Tenta match parcial para nomes compostos
    for chave, bairro in _MAPA_BAIRRO.items():
        if len(chave) > 4 and chave in s:
            return bairro

    return None


@app.get("/api/pacientesdb/por-bairro")
def pacdb_por_bairro(periodo: str = "30d", setor: str = ""):
    """
    Agrupa pacientes por BAIRRO REAL usando mapeamento dos Correios.
    PAC_END → normaliza → mapeia para bairro → agrupa.
    """
    inicio, fim = periodo_datas(periodo)
    filtro_setor = f"AND RTRIM(osm.OSM_STR) = '{setor}'" if setor else ""

    rows = query(f"""
        SELECT
            RTRIM(ISNULL(NULLIF(pac.PAC_END,''), '')) AS rua_raw,
            COUNT(DISTINCT osm.osm_pac)               AS total,
            SUM(CASE WHEN CAST(pac.pac_dreg AS DATE)
                          BETWEEN '{inicio}' AND '{fim}'
                     THEN 1 ELSE 0 END)               AS novos,
            SUM(CASE WHEN cnt_osm.qtd > 1 THEN 1 ELSE 0 END) AS retorno,
            CAST(COUNT(DISTINCT osm.osm_pac) * 100.0 /
                NULLIF((
                    SELECT COUNT(DISTINCT o2.osm_pac)
                    FROM osm o2
                    WHERE o2.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
                ), 0) AS DECIMAL(5,1))                AS pct_total
        FROM osm
        JOIN pac ON pac.pac_reg = osm.osm_pac
        LEFT JOIN (
            SELECT osm_pac, COUNT(*) AS qtd
            FROM osm
            WHERE osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
            GROUP BY osm_pac
        ) cnt_osm ON cnt_osm.osm_pac = osm.osm_pac
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          {filtro_setor}
          AND (pac.pac_dt_obito IS NULL OR pac.pac_dt_obito = '')
        GROUP BY RTRIM(ISNULL(NULLIF(pac.PAC_END,''), ''))
        ORDER BY total DESC
    """)

    from collections import defaultdict
    agrupado = defaultdict(lambda: {"bairro":"","total":0,"novos":0,"retorno":0,"pct_total":0.0})

    for r in rows:
        rua_raw = r.get("rua_raw") or ""
        bairro = _rua_para_bairro(rua_raw)
        if not bairro:
            bairro = _normalizar_rua(rua_raw)  # fallback para logradouro normalizado

        agrupado[bairro]["bairro"]    = bairro
        agrupado[bairro]["total"]    += r.get("total") or 0
        agrupado[bairro]["novos"]    += r.get("novos") or 0
        agrupado[bairro]["retorno"]  += r.get("retorno") or 0
        agrupado[bairro]["pct_total"] = round(
            (agrupado[bairro]["pct_total"] or 0) + (r.get("pct_total") or 0), 1
        )

    resultado = sorted(agrupado.values(), key=lambda x: x["total"], reverse=True)
    return [r for r in resultado if r["bairro"] != "Não informado" or r["total"] > 5][:40]


# ─── CRESCIMENTO DA BASE ──────────────────────────────────────────────────────

@app.get("/api/pacientesdb/crescimento-base")
def pacdb_crescimento_base(periodo: str = "ano", setor: str = ""):
    """Novos cadastros mês a mês no período."""
    inicio, fim = periodo_datas(periodo)
    rows = query(f"""
        SELECT
            FORMAT(pac.pac_dreg, 'MMM/yy') AS mes,
            YEAR(pac.pac_dreg)              AS ano,
            MONTH(pac.pac_dreg)             AS mes_num,
            COUNT(*)                        AS novos
        FROM pac
        WHERE CAST(pac.pac_dreg AS DATE) BETWEEN '{inicio}' AND '{fim}'
          AND (pac.pac_dt_obito IS NULL OR pac.pac_dt_obito = '')
        GROUP BY FORMAT(pac.pac_dreg, 'MMM/yy'),
                 YEAR(pac.pac_dreg), MONTH(pac.pac_dreg)
        ORDER BY ano, mes_num
    """)
    return rows


# ─── RETORNO VS NOVOS POR MÊS ────────────────────────────────────────────────

@app.get("/api/pacientesdb/retorno-vs-novos")
def pacdb_retorno_vs_novos(periodo: str = "ano", setor: str = ""):
    """
    Por mês: pacientes que vieram pela 1ª vez (novos) vs. que já tinham vindo antes (retorno).
    Usa a data do 1º atendimento no histórico completo como referência.
    """
    inicio, fim = periodo_datas(periodo)
    rows = query(f"""
        WITH primeira_os AS (
            SELECT osm_pac, MIN(osm_dthr) AS dt_primeira
            FROM osm
            GROUP BY osm_pac
        ),
        periodo_osm AS (
            SELECT DISTINCT
                osm.osm_pac,
                YEAR(osm.osm_dthr)           AS ano,
                MONTH(osm.osm_dthr)          AS mes_num,
                FORMAT(osm.osm_dthr,'MMM/yy') AS mes,
                po.dt_primeira
            FROM osm
            JOIN primeira_os po ON po.osm_pac = osm.osm_pac
            WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
        )
        SELECT
            mes,
            ano,
            mes_num,
            COUNT(DISTINCT CASE
                WHEN CAST(dt_primeira AS DATE) BETWEEN '{inicio}' AND '{fim}'
                THEN osm_pac END)  AS novos,
            COUNT(DISTINCT CASE
                WHEN CAST(dt_primeira AS DATE) < '{inicio}'
                THEN osm_pac END)  AS retorno
        FROM periodo_osm
        GROUP BY mes, ano, mes_num
        ORDER BY ano, mes_num
    """)
    return rows


# ─── TOP PACIENTES COM LOGRADOURO ─────────────────────────────────────────────

@app.get("/api/pacientes/top-atendimentos")
def pacientes_top_atendimentos(
    periodo: str      = "30d",
    inicio: str       = "",
    fim: str          = "",
    todo_periodo: bool = False,
    limite: int       = 20,
    setor: str        = "",
):
    """
    Top pacientes por número de atendimentos.
    Inclui logradouro (PAC_END) como campo 'bairro' para o frontend.
    SUBSTITUI o endpoint existente — adiciona o campo bairro.
    """
    if todo_periodo:
        ini_sql = "1900-01-01"
        fim_sql = datetime.now().strftime("%Y-%m-%d")
    elif inicio and fim:
        ini_sql, fim_sql = inicio, fim
    else:
        ini_sql, fim_sql = periodo_datas(periodo)

    rows = query(f"""
        SELECT TOP {limite}
            RTRIM(pac.pac_nome)                                           AS nome,
            DATEDIFF(year, pac.pac_nasc, GETDATE())                       AS idade,
            RTRIM(pac.pac_sexo)                                           AS sexo,
            RTRIM(ISNULL(cnv.cnv_nome,''))                                AS convenio,
            RTRIM(ISNULL(pac.PAC_END,''))                                 AS bairro,
            COUNT(DISTINCT CAST(osm.osm_serie AS BIGINT) * 1000000 + osm.osm_num)  AS total_atendimentos,
            MAX(osm.osm_dthr)                                             AS ultimo_atendimento
        FROM osm
        JOIN pac ON pac.pac_reg = osm.osm_pac
        LEFT JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        WHERE osm.osm_dthr BETWEEN '{ini_sql}' AND '{fim_sql} 23:59:59'
          AND (pac.pac_dt_obito IS NULL OR pac.pac_dt_obito = '')
        GROUP BY RTRIM(pac.pac_nome), pac.pac_nasc,
                 RTRIM(pac.pac_sexo), RTRIM(ISNULL(cnv.cnv_nome,'')),
                 RTRIM(ISNULL(pac.PAC_END,''))
        ORDER BY total_atendimentos DESC
    """)
    return rows

@app.get("/api/pacientes/servicos-por-sexo")
def pacientes_servicos_por_sexo(
    periodo: str = "30d",
    limite: int  = 10,
    sexo: str    = "",
    setor: str   = "",
):
    inicio, fim = periodo_datas(periodo)
    filtro_sexo = f"AND RTRIM(pac.pac_sexo) = '{sexo}'" if sexo in ("M","F") else "AND RTRIM(pac.pac_sexo) IN ('M','F')"
    filtro_setor = f"AND RTRIM(osm.OSM_STR) = '{setor}'" if setor else ""
    rows = query(f"""
        SELECT TOP {limite}
            RTRIM(smk.SMK_NOME)  AS nome_exame,
            RTRIM(pac.pac_sexo)  AS sexo,
            COUNT(*)             AS qtd
        FROM SMM smm
        JOIN OSM osm ON osm.OSM_SERIE = smm.SMM_OSM_SERIE AND osm.OSM_NUM = smm.SMM_OSM
        JOIN PAC pac ON pac.pac_reg = osm.osm_pac
        JOIN SMK smk ON RTRIM(smk.SMK_COD) = RTRIM(smm.SMM_COD)
                     AND RTRIM(smk.SMK_TIPO) = RTRIM(smm.SMM_TPCOD)
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          {filtro_sexo}
          {filtro_setor}
          AND smk.SMK_NOME IS NOT NULL
          AND LTRIM(RTRIM(smk.SMK_NOME)) <> ''
        GROUP BY RTRIM(smk.SMK_NOME), RTRIM(pac.pac_sexo)
        ORDER BY qtd DESC
    """)
    return rows


@app.get("/api/pacientes/servicos-comparativo")
def pacientes_servicos_comparativo(
    periodo: str = "30d",
    limite: int  = 15,
    setor: str   = "",
):
    inicio, fim = periodo_datas(periodo)
    rows = query(f"""
        SELECT
            RTRIM(smk.SMK_NOME) AS nome_exame,
            SUM(CASE WHEN RTRIM(pac.pac_sexo) = 'M' THEN 1 ELSE 0 END) AS masculino,
            SUM(CASE WHEN RTRIM(pac.pac_sexo) = 'F' THEN 1 ELSE 0 END) AS feminino,
            COUNT(*) AS total
        FROM SMM smm
        JOIN OSM osm ON osm.OSM_SERIE = smm.SMM_OSM_SERIE AND osm.OSM_NUM = smm.SMM_OSM
        JOIN PAC pac ON pac.pac_reg = osm.osm_pac
        JOIN SMK smk ON RTRIM(smk.SMK_COD) = RTRIM(smm.SMM_COD)
                     AND RTRIM(smk.SMK_TIPO) = RTRIM(smm.SMM_TPCOD)
        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND RTRIM(pac.pac_sexo) IN ('M','F')
          AND smk.SMK_NOME IS NOT NULL
          AND LTRIM(RTRIM(smk.SMK_NOME)) <> ''
        GROUP BY RTRIM(smk.SMK_NOME)
        HAVING COUNT(*) > 0
        ORDER BY COUNT(*) DESC
        OFFSET 0 ROWS FETCH NEXT {limite} ROWS ONLY
    """)
    return rows

# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO FATURAMENTO — Gestão de Guias Pendentes (SQLite próprio, fora do Smart)
# ══════════════════════════════════════════════════════════════════════════════

STATUS_GUIAS_VALIDOS = {"Pendente", "Entregue", "Cancelada"}

class GuiaCreate(BaseModel):
    data: str
    paciente: str
    os_serie: int | None = None
    os_num: int | None = None
    tipo_exame: str | None = None
    valor: float | None = None
    setor: str | None = None
    convenio: str | None = None
    observacao: str | None = None
    criado_por: str | None = None

class GuiaUpdate(BaseModel):
    data: str | None = None
    paciente: str | None = None
    os_serie: int | None = None
    os_num: int | None = None
    tipo_exame: str | None = None
    valor: float | None = None
    setor: str | None = None
    convenio: str | None = None
    status: str | None = None
    data_entrega: str | None = None
    data_faturamento: str | None = None
    observacao: str | None = None
    atualizado_por: str | None = None

@app.get("/api/faturamento/buscar-os")
def faturamento_buscar_os(q: str, limite: int = 10):
    """Busca uma OS na produção do Smart (osm/smm) pelo número (ou
    'serie-numero') pra autopreencher paciente, valor, setor e convênio
    ao lançar uma guia pendente."""
    termo = q.strip()
    so_digitos = _re.sub(r"\D", "", termo)

    if "-" in termo:
        partes = termo.split("-", 1)
        serie_digitos = _re.sub(r"\D", "", partes[0])
        num_digitos = _re.sub(r"\D", "", partes[1])
    else:
        serie_digitos = None
        num_digitos = so_digitos

    if not num_digitos or len(num_digitos) < 3:
        return {"total": 0, "resultados": []}

    if serie_digitos:
        where = "osm.osm_serie = ? AND osm.osm_num = ?"
        params = (int(serie_digitos), int(num_digitos))
    else:
        where = "osm.osm_num = ?"
        params = (int(num_digitos),)

    rows = query(f"""
        SELECT TOP {limite}
            osm.osm_serie                         AS os_serie,
            osm.osm_num                            AS os_num,
            CONVERT(varchar, osm.osm_dthr, 23)     AS data,
            RTRIM(pac.pac_nome)                    AS paciente,
            RTRIM(osm.osm_str)                     AS setor_cod,
            RTRIM(ISNULL(cnv.cnv_nome,''))         AS convenio
        FROM osm
        JOIN pac ON pac.pac_reg = osm.osm_pac
        LEFT JOIN cnv ON cnv.cnv_cod = osm.osm_cnv
        WHERE {where}
        ORDER BY osm.osm_dthr DESC
    """, params)

    resultados = []
    for r in rows:
        itens = query("""
            SELECT RTRIM(sk.SMK_NOME) AS nome,
                (smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) AS vliq
            FROM smm
            JOIN smk sk ON RTRIM(sk.SMK_COD) = RTRIM(smm.SMM_COD)
            WHERE smm.SMM_OSM_SERIE = ? AND smm.SMM_OSM = ?
        """, (r["os_serie"], r["os_num"]))
        setor_cod = (r["setor_cod"] or "").strip()
        if setor_cod == "PSI":
            setor_cod = "RCN"
        resultados.append({
            "os_serie": r["os_serie"],
            "os_num": r["os_num"],
            "os_label": f"{r['os_serie']}-{r['os_num']}",
            "data": r["data"],
            "paciente": r["paciente"],
            "setor": setor_cod,
            "setor_nome": RECEPCOES.get(setor_cod, setor_cod),
            "convenio": r["convenio"],
            "tipo_exame": ", ".join(sorted(set(i["nome"] for i in itens if i["nome"]))),
            "valor": round(sum(i["vliq"] or 0 for i in itens), 2),
            # itens individuais da OS — pra permitir escolher só os serviços
            # ainda pendentes quando a OS tem vários (alguns já faturados).
            "itens": [{"nome": i["nome"], "valor": round(i["vliq"] or 0, 2)} for i in itens],
        })
    return {"total": len(resultados), "resultados": resultados}

@app.get("/api/faturamento/guias")
def faturamento_listar_guias(status: str = None, setor: str = None, q: str = None,
                              ano: int = None, mes: int = None):
    conn = get_conn_guias()
    sql = "SELECT * FROM guias_pendentes WHERE 1=1"
    params = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if setor:
        sql += " AND setor = ?"
        params.append(setor)
    if q:
        sql += " AND (paciente LIKE ? OR tipo_exame LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if ano and mes:
        sql += " AND strftime('%Y-%m', data) = ?"
        params.append(f"{ano:04d}-{mes:02d}")
    sql += " ORDER BY data DESC, id DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return {"total": len(rows), "guias": [dict(r) for r in rows]}


@app.get("/api/faturamento/guias/pdf")
def faturamento_guias_pdf(status: str = None, setor: str = None, q: str = None,
                           ano: int = None, mes: int = None, background_tasks: BackgroundTasks = None):
    """PDF das guias filtradas pelos mesmos critérios da tela (status/setor/busca/mês)
    — pra imprimir a relação de guias de um status específico (ex: só Pendentes)."""
    import subprocess, tempfile, base64 as _b64, uuid

    resultado = faturamento_listar_guias(status=status, setor=setor, q=q, ano=ano, mes=mes)
    guias = resultado["guias"]

    logo_path = os.path.join(DIST, "..", "public", "icds_logo.png")
    logo_b64 = ""
    try:
        with open(logo_path, "rb") as f:
            logo_b64 = _b64.b64encode(f.read()).decode()
    except FileNotFoundError:
        pass

    logo_censo_path = os.path.join(DIST, "..", "public", "logo_clinica_censo.png")
    logo_censo_b64 = ""
    try:
        with open(logo_censo_path, "rb") as f:
            logo_censo_b64 = _b64.b64encode(f.read()).decode()
    except FileNotFoundError:
        pass

    STATUS_CORES = {"Pendente": "#D97706", "Entregue": "#2563EB", "Cancelada": "#DC2626"}
    valor_total = sum(g["valor"] or 0 for g in guias)

    def fmt_data(d):
        return f"{d[8:10]}/{d[5:7]}/{d[0:4]}" if d else "—"

    def brl(v):
        return f"R$ {v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") if v is not None else "—"

    linhas_html = ""
    for g in guias:
        cor = STATUS_CORES.get(g["status"], "#64748B")
        os_label = f"{g['os_serie']}-{g['os_num']}" if g.get("os_serie") else "—"
        linhas_html += f"""
        <tr>
          <td>{fmt_data(g['data'])}</td>
          <td>{g['paciente'] or '—'}</td>
          <td>{os_label}</td>
          <td>{g['tipo_exame'] or '—'}</td>
          <td>{RECEPCOES.get(g['setor'], g['setor']) if g.get('setor') else '—'}</td>
          <td>{g['convenio'] or '—'}</td>
          <td style="text-align:right;">{brl(g['valor'])}</td>
          <td><span style="color:{cor};font-weight:800;">{g['status']}</span></td>
        </tr>"""

    titulo_status = f" — {status}" if status else ""
    periodo_txt = f"{mes:02d}/{ano}" if (ano and mes) else "Todo o período"

    html = f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><style>
      @page {{ margin: 18mm 14mm; }}
      * {{ box-sizing: border-box; }}
      body {{ font-family: 'Segoe UI', Arial, sans-serif; color:#1E293B; margin:0; }}
      .header {{ display:flex; justify-content:space-between; align-items:center; border-bottom:3px solid #8B1A1A; padding-bottom:14px; margin-bottom:20px; }}
      .header img {{ height:42px; }}
      .header .titulo {{ text-align:right; }}
      .header .titulo h1 {{ font-size:18px; margin:0; color:#8B1A1A; }}
      .header .titulo p {{ font-size:11px; color:#64748B; margin:2px 0 0; }}
      .info {{ display:flex; gap:14px; margin-bottom:18px; flex-wrap:wrap; }}
      .info-card {{ background:#F8FAFC; border-radius:8px; padding:10px 16px; border-left:4px solid #8B1A1A; flex:1; min-width:140px; }}
      .info-card .label {{ font-size:10px; color:#64748B; text-transform:uppercase; font-weight:700; letter-spacing:.04em; }}
      .info-card .valor {{ font-size:18px; font-weight:800; color:#111827; margin-top:2px; }}
      table {{ width:100%; border-collapse:collapse; font-size:11.5px; }}
      th {{ background:#8B1A1A; color:#fff; padding:8px 10px; text-align:left; font-size:10.5px; text-transform:uppercase; letter-spacing:.03em; }}
      td {{ padding:6px 10px; border-bottom:1px solid #E2E8F0; }}
      tr:nth-child(even) {{ background:#FAFAFA; }}
      .footer {{ margin-top:24px; font-size:10px; color:#94A3B8; border-top:1px solid #E2E8F0; padding-top:8px; }}
    </style></head><body>
      <div class="header">
        <div style="display:flex; align-items:center; gap:16px;">
          <img src="data:image/png;base64,{logo_censo_b64}" alt="Clínica Censo" style="height:40px;"/>
          <img src="data:image/png;base64,{logo_b64}" alt="ICDS" style="height:34px;"/>
        </div>
        <div class="titulo">
          <h1>Relatório de Guias{titulo_status}</h1>
          <p>Período: {periodo_txt}{f" · Setor: {RECEPCOES.get(setor, setor)}" if setor else ""}</p>
        </div>
      </div>
      <div class="info">
        <div class="info-card"><div class="label">Guias</div><div class="valor">{len(guias)}</div></div>
        <div class="info-card"><div class="label">Valor Total</div><div class="valor">{brl(valor_total)}</div></div>
      </div>
      <table><thead><tr>
        <th>Data</th><th>Paciente</th><th>OS</th><th>Tipo de Exame</th><th>Setor</th><th>Convênio</th><th style="text-align:right;">Valor</th><th>Status</th>
      </tr></thead><tbody>{linhas_html}</tbody></table>
      <div class="footer">Relatório gerado automaticamente pelo Dashboard ICDS.</div>
    </body></html>"""

    tmp_dir = tempfile.gettempdir()
    uid = uuid.uuid4().hex
    html_path = os.path.join(tmp_dir, f"guias_{uid}.html")
    pdf_path = os.path.join(tmp_dir, f"guias_{uid}.pdf")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    try:
        subprocess.run([
            chrome_path, "--headless", "--disable-gpu", "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}", f"file:///{html_path}",
        ], timeout=30, capture_output=True)
    finally:
        try: os.remove(html_path)
        except OSError: pass

    if not os.path.exists(pdf_path):
        raise HTTPException(500, "Falha ao gerar PDF")

    background_tasks.add_task(lambda: os.remove(pdf_path) if os.path.exists(pdf_path) else None)
    return FileResponse(
        pdf_path, media_type="application/pdf",
        filename=f"Guias_{status or 'Todas'}.pdf",
        background=background_tasks,
    )


@app.get("/api/faturamento/resumo")
def faturamento_resumo(ano: int = None, mes: int = None):
    conn = get_conn_guias()
    filtro_mes = ""
    params = []
    if ano and mes:
        filtro_mes = " AND strftime('%Y-%m', data) = ?"
        params.append(f"{ano:04d}-{mes:02d}")
    rows = conn.execute(f"""
        SELECT status, COUNT(*) AS total, COALESCE(SUM(valor),0) AS valor_total
        FROM guias_pendentes WHERE 1=1{filtro_mes} GROUP BY status
    """, params).fetchall()
    atrasadas = conn.execute(f"""
        SELECT COUNT(*) AS total FROM guias_pendentes
        WHERE status = 'Pendente' AND julianday('now','localtime') - julianday(data) > 30{filtro_mes}
    """, params).fetchone()
    conn.close()
    por_status = {r["status"]: {"total": r["total"], "valor_total": r["valor_total"]} for r in rows}
    for s in STATUS_GUIAS_VALIDOS:
        por_status.setdefault(s, {"total": 0, "valor_total": 0})
    return {"por_status": por_status, "pendentes_30dias": atrasadas["total"]}

@app.get("/api/faturamento/dashboard")
def faturamento_dashboard():
    """Dados agregados pros gráficos do módulo: pendências por mês (últimos
    12 meses, por status) e por convênio/setor (só guias Pendentes)."""
    conn = get_conn_guias()

    por_mes = conn.execute("""
        SELECT strftime('%Y-%m', data) AS mes,
               status,
               COUNT(*) AS total,
               COALESCE(SUM(valor),0) AS valor_total
        FROM guias_pendentes
        WHERE data >= date('now', '-11 months', 'start of month')
        GROUP BY mes, status
        ORDER BY mes
    """).fetchall()

    por_convenio = conn.execute("""
        SELECT COALESCE(NULLIF(TRIM(convenio),''),'Não informado') AS convenio,
               COUNT(*) AS total,
               COALESCE(SUM(valor),0) AS valor_total
        FROM guias_pendentes
        WHERE status = 'Pendente'
        GROUP BY convenio
        ORDER BY valor_total DESC
        LIMIT 10
    """).fetchall()

    por_setor = conn.execute("""
        SELECT COALESCE(NULLIF(TRIM(setor),''),'Não informado') AS setor,
               COUNT(*) AS total,
               COALESCE(SUM(valor),0) AS valor_total
        FROM guias_pendentes
        WHERE status = 'Pendente'
        GROUP BY setor
        ORDER BY valor_total DESC
    """).fetchall()

    conn.close()

    # Reestrutura por_mes: uma linha por mês, com valor por status lado a
    # lado (formato que o BarChart empilhado do recharts espera).
    meses = {}
    for r in por_mes:
        m = meses.setdefault(r["mes"], {"mes": r["mes"]})
        m[r["status"]] = r["valor_total"]
        m[f'{r["status"]}_qtd'] = r["total"]

    return {
        "por_mes": sorted(meses.values(), key=lambda x: x["mes"]),
        "por_convenio": [dict(r) for r in por_convenio],
        "por_setor": [dict(r) for r in por_setor],
    }

@app.post("/api/faturamento/guias")
def faturamento_criar_guia(g: GuiaCreate):
    conn = get_conn_guias()
    cur = conn.execute("""
        INSERT INTO guias_pendentes
            (data, paciente, os_serie, os_num, tipo_exame, valor, setor, convenio, status, observacao, criado_por)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pendente', ?, ?)
    """, (g.data, g.paciente, g.os_serie, g.os_num, g.tipo_exame, g.valor, g.setor, g.convenio, g.observacao, g.criado_por))
    conn.commit()
    novo_id = cur.lastrowid
    row = conn.execute("SELECT * FROM guias_pendentes WHERE id = ?", (novo_id,)).fetchone()
    conn.close()
    return dict(row)

@app.put("/api/faturamento/guias/{guia_id}")
def faturamento_atualizar_guia(guia_id: int, g: GuiaUpdate):
    conn = get_conn_guias()
    existente = conn.execute("SELECT * FROM guias_pendentes WHERE id = ?", (guia_id,)).fetchone()
    if not existente:
        conn.close()
        raise HTTPException(404, "Guia não encontrada")

    campos = g.model_dump(exclude_unset=True)
    if "status" in campos and campos["status"] not in STATUS_GUIAS_VALIDOS:
        conn.close()
        raise HTTPException(400, f"Status inválido: {campos['status']}")

    hoje = datetime.now().strftime("%Y-%m-%d")
    if campos.get("status") == "Entregue" and not campos.get("data_entrega") and not existente["data_entrega"]:
        campos["data_entrega"] = hoje

    if not campos:
        conn.close()
        return dict(existente)

    campos["atualizado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sets = ", ".join(f"{k} = ?" for k in campos)
    params = list(campos.values()) + [guia_id]
    conn.execute(f"UPDATE guias_pendentes SET {sets} WHERE id = ?", params)
    conn.commit()
    row = conn.execute("SELECT * FROM guias_pendentes WHERE id = ?", (guia_id,)).fetchone()
    conn.close()
    return dict(row)

@app.delete("/api/faturamento/guias/{guia_id}")
def faturamento_deletar_guia(guia_id: int):
    conn = get_conn_guias()
    cur = conn.execute("DELETE FROM guias_pendentes WHERE id = ?", (guia_id,))
    conn.commit()
    afetado = cur.rowcount
    conn.close()
    if not afetado:
        raise HTTPException(404, "Guia não encontrada")
    return {"ok": True}

# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO GESTÃO — Organograma
# Banco próprio (organograma.db, SQLite) — estrutura organizacional não existe
# no Smart/Pixeon, é dado interno de gestão do Dashboard.
# ══════════════════════════════════════════════════════════════════════════════

class OrgNoCreate(BaseModel):
    nome: str
    cargo: str | None = None
    setor: str | None = None
    pai_id: int | None = None
    pos_x: float = 0
    pos_y: float = 0
    largura: float = 190
    altura: float = 78
    cor: str | None = None

class OrgNoUpdate(BaseModel):
    nome: str | None = None
    cargo: str | None = None
    setor: str | None = None
    pai_id: int | None = None
    pos_x: float | None = None
    pos_y: float | None = None
    largura: float | None = None
    altura: float | None = None
    cor: str | None = None

@app.get("/api/organograma/nos")
def organograma_listar():
    conn = get_conn_organograma()
    rows = [dict(r) for r in conn.execute("SELECT * FROM org_nos ORDER BY id").fetchall()]
    conn.close()
    return rows

@app.post("/api/organograma/nos")
def organograma_criar(no: OrgNoCreate):
    conn = get_conn_organograma()
    cur = conn.execute(
        "INSERT INTO org_nos (nome, cargo, setor, pai_id, pos_x, pos_y, largura, altura, cor) VALUES (?,?,?,?,?,?,?,?,?)",
        (no.nome, no.cargo, no.setor, no.pai_id, no.pos_x, no.pos_y, no.largura, no.altura, no.cor),
    )
    novo_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"ok": True, "id": novo_id}

@app.put("/api/organograma/nos/{no_id}")
def organograma_atualizar(no_id: int, no: OrgNoUpdate):
    campos = no.model_dump(exclude_unset=True)
    if not campos:
        return {"ok": True}
    if "pai_id" in campos and campos["pai_id"] == no_id:
        raise HTTPException(400, "Um cargo não pode ser superior de si mesmo")
    campos["atualizado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    set_sql = ", ".join(f"{k} = ?" for k in campos)
    conn = get_conn_organograma()
    cur = conn.execute(f"UPDATE org_nos SET {set_sql} WHERE id = ?", (*campos.values(), no_id))
    conn.commit()
    afetado = cur.rowcount
    conn.close()
    if not afetado:
        raise HTTPException(404, "Nó não encontrado")
    return {"ok": True}

@app.delete("/api/organograma/nos/{no_id}")
def organograma_deletar(no_id: int):
    conn = get_conn_organograma()
    # Filhos ficam órfãos (pai_id = NULL) em vez de serem apagados em cascata —
    # evita perder um ramo inteiro do organograma por engano.
    conn.execute("UPDATE org_nos SET pai_id = NULL WHERE pai_id = ?", (no_id,))
    cur = conn.execute("DELETE FROM org_nos WHERE id = ?", (no_id,))
    conn.commit()
    afetado = cur.rowcount
    conn.close()
    if not afetado:
        raise HTTPException(404, "Nó não encontrado")
    return {"ok": True}


def _layout_compacto_organograma(nos):
    """
    Recalcula posições (x,y) do organograma pra impressão, independente de como
    o usuário arrastou os cartões na tela. Empilha grupos de irmãos largos em
    várias linhas (wrap) em vez de deixar tudo numa fileira só — isso evita que
    uma diretoria com 5-6 cargos abaixo estique o organograma inteiro na
    horizontal, o que forçava uma escala minúscula (ou várias folhas) na
    impressão. Resultado: árvore mais estreita e mais alta, que cabe numa
    folha padrão (A3/A2) com texto legível.
    """
    LARG_PADRAO, ALT_PADRAO = 190, 78
    GAP_X, GAP_Y = 34, 55
    MAX_LARGURA_GRUPO = 999999

    def pxv(n, campo, default):
        return n[campo] if n.get(campo) else default

    by_id = {n["id"]: n for n in nos}
    filhos_de = {}
    for n in nos:
        pai_id = n["pai_id"] if n["pai_id"] in by_id else None
        filhos_de.setdefault(pai_id, []).append(n)

    pos = {}
    subtree_ids = {}

    def empacotar(itens):
        # itens: [(id, w, h)] -> quebra em linhas sem passar de MAX_LARGURA_GRUPO
        linhas, linha_atual, largura_atual = [], [], 0
        for iid, w, h in itens:
            acrescimo = w if not linha_atual else GAP_X + w
            if linha_atual and (largura_atual + acrescimo) > MAX_LARGURA_GRUPO:
                linhas.append(linha_atual)
                linha_atual, largura_atual, acrescimo = [], 0, w
            linha_atual.append((iid, w, h))
            largura_atual += acrescimo
        if linha_atual:
            linhas.append(linha_atual)
        largura_total = max((sum(w for _, w, _ in l) + GAP_X * (len(l) - 1) for l in linhas), default=0)
        return linhas, largura_total

    def posicionar_linhas(linhas, largura_total, y_inicial):
        y_cursor = y_inicial
        for linha in linhas:
            largura_linha = sum(w for _, w, _ in linha) + GAP_X * (len(linha) - 1)
            altura_linha = max(h for _, _, h in linha)
            x_cursor = (largura_total - largura_linha) / 2
            for fid, w, h in linha:
                for did in subtree_ids[fid]:
                    pos[did]["x"] += x_cursor
                    pos[did]["y"] += y_cursor
                x_cursor += w + GAP_X
            y_cursor += altura_linha + GAP_Y
        return y_cursor - GAP_Y

    def calc(n):
        nid = n["id"]
        largura_no, altura_no = pxv(n, "largura", LARG_PADRAO), pxv(n, "altura", ALT_PADRAO)
        filhos = filhos_de.get(nid, [])
        ids_subtree = [nid]

        if not filhos:
            pos[nid] = {"x": 0, "y": 0}
            subtree_ids[nid] = ids_subtree
            return largura_no, altura_no

        tamanhos = []
        for f in filhos:
            w, h = calc(f)
            tamanhos.append((f["id"], w, h))
            ids_subtree.extend(subtree_ids[f["id"]])

        linhas, largura_filhos = empacotar(tamanhos)
        altura_filhos = posicionar_linhas(linhas, largura_filhos, altura_no + GAP_Y) - (altura_no + GAP_Y)

        largura_grupo = max(largura_no, largura_filhos)
        altura_grupo = altura_no + GAP_Y + altura_filhos

        pos[nid] = {"x": largura_grupo / 2 - largura_no / 2, "y": 0}
        subtree_ids[nid] = ids_subtree
        return largura_grupo, altura_grupo

    raizes = filhos_de.get(None, [])
    tamanhos_raizes = []
    for r in raizes:
        w, h = calc(r)
        tamanhos_raizes.append((r["id"], w, h))

    linhas, largura_total = empacotar(tamanhos_raizes)
    altura_total = posicionar_linhas(linhas, largura_total, 0)

    return pos, largura_total, altura_total


# Tamanhos de papel padrão (mm), do menor pro maior — usados pra escolher a
# menor folha "de verdade" (impressora comum ou plotter de gráfica) em que o
# organograma cabe numa escala legível, ao invés de forçar sempre A4.
_PAPEIS_PADRAO_MM = [
    ("A4 retrato", 210, 297), ("A4 paisagem", 297, 210),
    ("A3 retrato", 297, 420), ("A3 paisagem", 420, 297),
    ("A2 retrato", 420, 594), ("A2 paisagem", 594, 420),
    ("A1 retrato", 594, 841), ("A1 paisagem", 841, 594),
]
_MM_PARA_PX = 96 / 25.4


def _montar_filhos_de(nos):
    by_id = {n["id"]: n for n in nos}
    filhos_de = {}
    for n in nos:
        pai_id = n["pai_id"] if n["pai_id"] in by_id else None
        filhos_de.setdefault(pai_id, []).append(n)
    return by_id, filhos_de


def _coletar_subarvore(raiz, filhos_de):
    resultado = [raiz]
    for f in filhos_de.get(raiz["id"], []):
        resultado.extend(_coletar_subarvore(f, filhos_de))
    return resultado


def _renderizar_pagina_html(nos_pagina, titulo, logo_b64, largura_mm_padrao_disponiveis, min_escala, nota_rodape=""):
    """Monta o HTML de UMA página (um card por nó em nos_pagina), escolhendo a
    menor largura de papel padrão em que ela cabe numa escala legível, com a
    altura ajustada exatamente ao conteúdo (sem sobra de espaço em branco)."""
    margem_x, margem_y = 40, 40
    pos, largura_conteudo, altura_conteudo = _layout_compacto_organograma(nos_pagina)
    by_id = {n["id"]: n for n in nos_pagina}

    def px(n, campo, default):
        return n[campo] if n.get(campo) else default

    largura = int(largura_conteudo + margem_x * 2)
    altura = int(altura_conteudo + margem_y * 2)

    linhas_svg = ""
    for n in nos_pagina:
        pai = by_id.get(n["pai_id"])
        if pai:
            lp, ap = px(pai, "largura", 190), px(pai, "altura", 78)
            ln, an = px(n, "largura", 190), px(n, "altura", 78)
            x1 = pos[pai["id"]]["x"] + margem_x + lp / 2
            y1 = pos[pai["id"]]["y"] + margem_y + ap
            x2 = pos[n["id"]]["x"] + margem_x + ln / 2
            y2 = pos[n["id"]]["y"] + margem_y
            mid_y = (y1 + y2) / 2
            linhas_svg += (
                f'<path d="M {x1} {y1} L {x1} {mid_y} L {x2} {mid_y} L {x2} {y2}" '
                f'stroke="#94A3B8" stroke-width="2" fill="none" stroke-linejoin="round" stroke-linecap="round"/>\n'
            )

    caixas_html = ""
    for n in nos_pagina:
        cor = n["cor"] or "#8B1A1A"
        larg, alt = px(n, "largura", 190), px(n, "altura", 78)
        x, y = pos[n["id"]]["x"] + margem_x, pos[n["id"]]["y"] + margem_y
        caixas_html += f"""
        <div style="position:absolute; left:{x}px; top:{y}px; width:{larg}px; min-height:{alt}px;
            background:#fff; border-radius:10px; border-left:5px solid {cor};
            box-shadow:0 2px 6px rgba(0,0,0,0.12); padding:10px 12px;">
          <div style="font-size:13px; font-weight:700; color:#111827;">{n['nome']}</div>
          <div style="font-size:11.5px; color:#64748B;">{n['cargo'] or ''}</div>
          {f'<div style="font-size:9.5px; color:#94A3B8; text-transform:uppercase; margin-top:3px;">{n["setor"]}</div>' if n['setor'] else ''}
        </div>"""

    header_h = 74
    rodape_h = 30 if nota_rodape else 0
    altura_total_conteudo = altura + header_h + rodape_h

    fator = None
    largura_mm = None
    for larg_mm in largura_mm_padrao_disponiveis:
        escala = min(1.0, larg_mm * _MM_PARA_PX / largura)
        if escala >= min_escala:
            fator, largura_mm = escala, larg_mm
            break
    if fator is None:
        largura_mm = largura_mm_padrao_disponiveis[-1]
        fator = min(1.0, largura_mm * _MM_PARA_PX / largura)

    altura_mm = round((altura_total_conteudo * fator) / _MM_PARA_PX, 1)
    cabe_bem = fator >= min_escala

    html = f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><style>
      @page {{ size: {largura_mm}mm {altura_mm}mm; margin: 0; }}
      * {{ box-sizing: border-box; }}
      html, body {{ height: 100%; }}
      body {{ font-family: 'Segoe UI', Arial, sans-serif; margin:0; display:flex; flex-direction:column; }}
      .header {{ display:flex; justify-content:space-between; align-items:center; border-bottom:3px solid #8B1A1A; padding:16px 24px 12px; height:{header_h}px; flex-shrink:0; box-sizing:border-box; }}
      .header img {{ height:36px; }}
      .header .titulo {{ text-align:right; font-size:13px; color:#8B1A1A; font-weight:800; }}
      .canvas-wrap {{ flex:1; display:flex; justify-content:center; align-items:center; overflow:hidden; }}
      .canvas {{ position:relative; width:{largura}px; height:{altura}px; transform: scale({fator:.4f}); transform-origin: center center; flex-shrink:0; }}
      .rodape {{ text-align:center; font-size:10.5px; color:#94A3B8; flex-shrink:0; padding:6px 0 10px; }}
    </style></head><body>
      <div class="header">
        <img src="data:image/png;base64,{logo_b64}" alt="ICDS"/>
        <div class="titulo">{titulo}</div>
      </div>
      <div class="canvas-wrap">
        <div class="canvas">
          <svg width="{largura}" height="{altura}" style="position:absolute; left:0; top:0;">{linhas_svg}</svg>
          {caixas_html}
        </div>
      </div>
      {f'<div class="rodape">{nota_rodape}</div>' if nota_rodape else ''}
    </body></html>"""
    return html, cabe_bem, fator


@app.get("/api/organograma/pdf")
def organograma_pdf(background_tasks: BackgroundTasks):
    """
    Gera o PDF do organograma dividido por RAMO (departamento), não em pedaços
    arbitrários — cada diretoria/gerência principal vira sua própria página,
    em escala quase real (>=90%) numa folha A4/A3 comum de impressora de
    escritório, mais uma página de visão geral no início. Isso evita tanto o
    texto minúsculo (que dava numa página só com tudo) quanto o corte de
    cartões no meio (que dava no recorte em pôster).
    """
    import subprocess, tempfile, base64 as _b64, uuid
    from pypdf import PdfWriter

    conn = get_conn_organograma()
    nos = [dict(r) for r in conn.execute("SELECT * FROM org_nos ORDER BY id").fetchall()]
    conn.close()

    if not nos:
        raise HTTPException(400, "Organograma vazio — nada para exportar")

    logo_path = os.path.join(DIST, "..", "public", "icds_logo.png")
    logo_b64 = ""
    try:
        with open(logo_path, "rb") as f:
            logo_b64 = _b64.b64encode(f.read()).decode()
    except FileNotFoundError:
        pass

    by_id, filhos_de = _montar_filhos_de(nos)

    # Desce pela cadeia enquanto só houver 1 nó por nível (ex: Instituto -> Diretor
    # Executivo) — o primeiro ponto com mais de 1 filho é onde a árvore realmente
    # se ramifica em departamentos, e cada ramo daí vira uma página própria.
    cadeia = []
    atual = filhos_de.get(None, [])
    while len(atual) == 1:
        cadeia.append(atual[0])
        atual = filhos_de.get(atual[0]["id"], [])
    ramos = atual

    # Nunca passa de A3 — é o maior papel que uma impressora/copiadora comum
    # de escritório imprime. Ir pra A2/A1 exige plotter de gráfica, que nem
    # todo mundo tem à mão, e só trocava "texto minúsculo" por "página que
    # ninguém consegue imprimir". Se nem A3 bastar numa escala boa, prefere
    # quebrar o ramo em sub-páginas a forçar um papel fora do padrão.
    LARGURAS_PAGINA_MM = [210, 297, 420]  # A4 retrato / A4-A3 paisagem / A3 paisagem
    MIN_ESCALA_PAGINA = 0.9
    MIN_ESCALA_ACEITAVEL = 0.6  # ainda bem legível, só não é 90%+

    paginas_html = []

    def montar_paginas_do_ramo(raiz, titulo):
        subarvore = _coletar_subarvore(raiz, filhos_de)
        html, cabe, fator = _renderizar_pagina_html(subarvore, titulo, logo_b64, LARGURAS_PAGINA_MM, MIN_ESCALA_PAGINA)
        if cabe or not filhos_de.get(raiz["id"]) or fator >= MIN_ESCALA_ACEITAVEL:
            paginas_html.append(html)
        else:
            # nem a 60% de escala em A3 — quebra o próprio ramo em sub-páginas
            # por filho direto (mesma lógica, recursiva) em vez de forçar texto
            # ilegível ou papel fora do padrão.
            for filho in filhos_de.get(raiz["id"], []):
                montar_paginas_do_ramo(filho, f"{titulo} — {filho['nome']}")

    if len(ramos) <= 1:
        # organograma pequeno / ainda sem ramificação real — cabe tudo numa página só
        html, _, _ = _renderizar_pagina_html(nos, "Organograma", logo_b64, LARGURAS_PAGINA_MM, MIN_ESCALA_ACEITAVEL)
        paginas_html.append(html)
    else:
        overview_nos = cadeia + ramos
        nota = "Cada diretoria/gerência está detalhada nas páginas seguintes."
        html_overview, _, _ = _renderizar_pagina_html(
            overview_nos, "Organograma — Visão Geral", logo_b64, LARGURAS_PAGINA_MM, 0.7, nota_rodape=nota)
        paginas_html.append(html_overview)
        for ramo in ramos:
            montar_paginas_do_ramo(ramo, f"Organograma — {ramo['nome']}")

    tmp_dir = tempfile.gettempdir()
    uid = uuid.uuid4().hex
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    pdfs_paginas = []
    htmls_temp = []
    try:
        for i, html in enumerate(paginas_html):
            html_path = os.path.join(tmp_dir, f"organograma_{uid}_{i}.html")
            pdf_path_pagina = os.path.join(tmp_dir, f"organograma_{uid}_{i}.pdf")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            htmls_temp.append(html_path)
            subprocess.run([
                chrome_path, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={pdf_path_pagina}", f"file:///{html_path}",
            ], timeout=30, capture_output=True)
            if not os.path.exists(pdf_path_pagina):
                raise HTTPException(500, "Falha ao gerar PDF")
            pdfs_paginas.append(pdf_path_pagina)

        pdf_path = os.path.join(tmp_dir, f"organograma_{uid}_final.pdf")
        writer = PdfWriter()
        for p in pdfs_paginas:
            writer.append(p)
        with open(pdf_path, "wb") as f:
            writer.write(f)
    finally:
        for p in htmls_temp + pdfs_paginas:
            try: os.remove(p)
            except OSError: pass

    if not os.path.exists(pdf_path):
        raise HTTPException(500, "Falha ao gerar PDF")

    background_tasks.add_task(lambda: os.remove(pdf_path) if os.path.exists(pdf_path) else None)
    return FileResponse(pdf_path, media_type="application/pdf", filename="Organograma.pdf", background=background_tasks)


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO RECEPÇÃO — Métricas por recepcionista
# ══════════════════════════════════════════════════════════════════════════════

RECEPCOES = {
    "RDI": "Recepção Diagnóstico",
    "ROC": "Recepção Ocupacional",
    "RCN": "Recepção Consultórios",
    "RCI": "Recepção Censo Imagem",
}

@app.get("/api/recepcao/media-por-horario")
def recepcao_media_por_horario(periodo: str = "30d", setor: str = ""):
    """
    Quantidade total de pacientes recepcionados (chegada) por horário do dia,
    aberta por ponto de recepção (RDI/ROC/RCN/RCI) — pra comparar o horário
    de pico de cada uma. Inclui totem (é volume real de paciente, diferente
    da atribuição por recepcionista). O filtro `setor` do módulo é ignorado
    de propósito aqui — o gráfico sempre mostra todas as recepções lado a lado.
    """
    inicio, fim = periodo_datas(periodo)
    RECEPCOES_COD = ["RDI", "ROC", "RCN", "RCI"]

    dias_row = query(f"""
        SELECT COUNT(DISTINCT CAST(fle.FLE_DTHR_CHEGADA AS DATE)) AS dias
        FROM fle
        WHERE fle.FLE_DTHR_CHEGADA BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND fle.FLE_PAC_REG > 0
    """)
    dias = (dias_row[0]["dias"] if dias_row else 0) or 1

    rows = query(f"""
        SELECT
            DATEPART(hour, fle.FLE_DTHR_CHEGADA) AS hora,
            RTRIM(fle.FLE_STR_COD)               AS recepcao,
            COUNT(*)                             AS total
        FROM fle
        WHERE fle.FLE_DTHR_CHEGADA BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND fle.FLE_PAC_REG > 0
          AND RTRIM(fle.FLE_STR_COD) IN ('RDI','ROC','RCN','RCI')
        GROUP BY DATEPART(hour, fle.FLE_DTHR_CHEGADA), RTRIM(fle.FLE_STR_COD)
        ORDER BY hora
    """)
    por_hora = {}
    for r in rows:
        por_hora.setdefault(r["hora"], {})[r["recepcao"]] = r["total"]

    dados = []
    for h in range(6, 21):  # 06h às 20h — janela de funcionamento da clínica
        linha = {"hora": f"{h:02d}h"}
        for cod in RECEPCOES_COD:
            linha[cod] = por_hora.get(h, {}).get(cod, 0)
        dados.append(linha)

    return {
        "periodo": periodo,
        "dias_considerados": dias,
        "recepcoes": [{"cod": c, "nome": RECEPCOES.get(c, c)} for c in RECEPCOES_COD],
        "dados": dados,
    }

@app.get("/api/recepcao/metas")
def recepcao_metas(periodo: str = "30d", setor: str = ""):
    """
    Metas de recepção calculadas com base no histórico dos últimos 3 meses
    completos anteriores ao mês atual:
    - producao_por_recepcao: meta mensal de produção financeira por recepção
      (média histórica), comparada com o total do período selecionado
    - meta_tempo_atendimento_min: meta única de tempo médio de atendimento
      (chegada até a chamada real da senha, ou abertura da OS quando não há
      chamada registrada), calculada como a média histórica geral entre todas
      as recepcionistas/recepções — a comparação por recepcionista no período
      atual já vem de /api/recepcao/ranking
    """
    inicio, fim = periodo_datas(periodo)
    filtro_setor_fle = f"AND RTRIM(fle.FLE_STR_COD) = '{setor}'" if setor else ""

    # Janela histórica: os 3 meses completos anteriores ao mês atual
    hoje = datetime.now()
    hist_fim_dt = hoje.replace(day=1) - timedelta(days=1)
    mes_ini = hist_fim_dt.month - 2
    ano_ini = hist_fim_dt.year
    if mes_ini <= 0:
        mes_ini += 12
        ano_ini -= 1
    hist_inicio = hist_fim_dt.replace(year=ano_ini, month=mes_ini, day=1).strftime("%Y-%m-%d")
    hist_fim = hist_fim_dt.strftime("%Y-%m-%d")
    n_meses = 3
    vliq = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"

    def producao_por_setor(dt_ini, dt_fim):
        # Mesma atribuição "primeiro contato" já usada em /api/recepcao/ranking:
        # um paciente conta pra recepção que o atendeu primeiro naquele dia.
        rows = query(f"""
            WITH chegadas_prod AS (
                SELECT setor_cod, FLE_PAC_REG, data_cheg
                FROM (
                    SELECT RTRIM(fle.FLE_STR_COD) AS setor_cod, fle.FLE_PAC_REG,
                        CAST(fle.FLE_DTHR_CHEGADA AS DATE) AS data_cheg,
                        ROW_NUMBER() OVER (
                            PARTITION BY fle.FLE_PAC_REG, CAST(fle.FLE_DTHR_CHEGADA AS DATE)
                            ORDER BY fle.FLE_DTHR_CHEGADA ASC
                        ) AS rn
                    FROM fle
                    WHERE fle.FLE_DTHR_CHEGADA BETWEEN '{dt_ini}' AND '{dt_fim} 23:59:59'
                      AND fle.FLE_PAC_REG > 0
                      AND ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO) IS NOT NULL
                      AND RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)) NOT LIKE 'TOTEM%'
                      AND UPPER(RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO))) NOT LIKE '%ESTAGIARIO%'
                      {filtro_setor_fle}
                ) x WHERE rn = 1
            )
            SELECT c.setor_cod, SUM({vliq}) AS producao
            FROM chegadas_prod c
            JOIN osm o ON o.osm_pac = c.FLE_PAC_REG AND CAST(o.osm_dthr AS DATE) = c.data_cheg
            JOIN smm ON smm.SMM_OSM = o.osm_num AND smm.SMM_OSM_SERIE = o.osm_serie
            WHERE smm.SMM_SFAT IN ('A','F','P')
            GROUP BY c.setor_cod
        """)
        return {r["setor_cod"]: float(r["producao"] or 0) for r in rows}

    hist_producao = producao_por_setor(hist_inicio, hist_fim)
    atual_producao = producao_por_setor(inicio, fim)

    producao_por_recepcao = []
    for cod, nome in RECEPCOES.items():
        if setor and cod != setor:
            continue
        meta_mensal = hist_producao.get(cod, 0) / n_meses
        atual = atual_producao.get(cod, 0)
        producao_por_recepcao.append({
            "recepcao_cod": cod,
            "recepcao_nome": nome,
            "meta_mensal": meta_mensal,
            "atual": atual,
            "pct": round(atual / meta_mensal * 100, 1) if meta_mensal else None,
        })

    # Meta única de tempo de atendimento: média histórica geral (chegada -> abertura da OS)
    hist_tempo = query(f"""
        WITH chegadas AS (
            SELECT RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)) AS login_recep,
                RTRIM(fle.FLE_STR_COD) AS setor_cod, fle.FLE_PAC_REG, fle.FLE_DTHR_CHEGADA,
                fle.FLE_DTHR_ATENDIMENTO,
                CAST(fle.FLE_DTHR_CHEGADA AS DATE) AS data_cheg
            FROM fle
            WHERE fle.FLE_DTHR_CHEGADA BETWEEN '{hist_inicio}' AND '{hist_fim} 23:59:59'
              AND fle.FLE_PAC_REG > 0
              AND ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO) IS NOT NULL
              AND RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)) NOT LIKE 'TOTEM%'
              AND UPPER(RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO))) NOT LIKE '%ESTAGIARIO%'
              {filtro_setor_fle}
        ),
        esperas_agg AS (
            SELECT c.login_recep, c.setor_cod,
                AVG(CAST(CASE WHEN e.espera_min BETWEEN 0 AND 120 THEN e.espera_min ELSE NULL END AS FLOAT)) AS espera_media_min
            FROM chegadas c
            OUTER APPLY (
                SELECT DATEDIFF(minute, c.FLE_DTHR_CHEGADA,
                    COALESCE(c.FLE_DTHR_ATENDIMENTO,
                        (SELECT TOP 1 o.osm_dthr FROM osm o
                         WHERE o.osm_pac = c.FLE_PAC_REG
                           AND CAST(o.osm_dthr AS DATE) = c.data_cheg
                           AND o.osm_dthr >= c.FLE_DTHR_CHEGADA
                         ORDER BY o.osm_dthr ASC))) AS espera_min
            ) e
            GROUP BY c.login_recep, c.setor_cod
        )
        SELECT AVG(espera_media_min) AS media_geral
        FROM esperas_agg WHERE espera_media_min IS NOT NULL
    """)
    meta_tempo_min = hist_tempo[0]["media_geral"] if hist_tempo and hist_tempo[0]["media_geral"] is not None else None

    return {
        "periodo_historico": {"inicio": hist_inicio, "fim": hist_fim, "meses": n_meses},
        "producao_por_recepcao": producao_por_recepcao,
        "meta_tempo_atendimento_min": meta_tempo_min,
    }


@app.get("/api/recepcao/ranking")
def recepcao_ranking(periodo: str = "30d", setor: str = ""):
    """Ranking de recepcionistas: quantidade de pacientes, tempo de espera e produção financeira."""
    inicio, fim = periodo_datas(periodo)
    filtro_setor = f"AND RTRIM(fle.FLE_STR_COD) = '{setor}'" if setor else ""
    vliq = "(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) - ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0))"

    rows = query(f"""
        WITH chegadas AS (
            SELECT
                RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)) AS login_recep,
                RTRIM(fle.FLE_STR_COD)                                     AS setor_cod,
                fle.FLE_PAC_REG,
                fle.FLE_DTHR_CHEGADA,
                fle.FLE_DTHR_ATENDIMENTO,
                CAST(fle.FLE_DTHR_CHEGADA AS DATE)                         AS data_cheg
            FROM fle
            WHERE fle.FLE_DTHR_CHEGADA BETWEEN '{inicio}' AND '{fim} 23:59:59'
              AND fle.FLE_PAC_REG > 0
              AND ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO) IS NOT NULL
              AND RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)) NOT LIKE 'TOTEM%'
              AND UPPER(RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO))) NOT LIKE '%ESTAGIARIO%'
              {filtro_setor}
        ),
        chegadas_prod AS (
            -- One row per (patient, day): the first-touch receptionist gets production credit
            -- Deduplicates cross-sector double-counting (patient going to 2+ desks same day)
            SELECT login_recep, setor_cod, FLE_PAC_REG, data_cheg
            FROM (
                SELECT
                    RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)) AS login_recep,
                    RTRIM(fle.FLE_STR_COD)                                     AS setor_cod,
                    fle.FLE_PAC_REG,
                    CAST(fle.FLE_DTHR_CHEGADA AS DATE)                         AS data_cheg,
                    ROW_NUMBER() OVER (
                        PARTITION BY fle.FLE_PAC_REG, CAST(fle.FLE_DTHR_CHEGADA AS DATE)
                        ORDER BY fle.FLE_DTHR_CHEGADA ASC
                    ) AS rn
                FROM fle
                WHERE fle.FLE_DTHR_CHEGADA BETWEEN '{inicio}' AND '{fim} 23:59:59'
                  AND fle.FLE_PAC_REG > 0
                  AND ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO) IS NOT NULL
                  AND RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)) NOT LIKE 'TOTEM%'
                  AND UPPER(RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO))) NOT LIKE '%ESTAGIARIO%'
                  {filtro_setor}
            ) x WHERE rn = 1
        ),
        esperas_agg AS (
            -- Pré-agregado por (recepcionista, setor): evita reunir de volta com `chegadas`
            -- sem a data (bug que multiplicava linhas p/ pacientes com +1 visita no período
            -- e também deixava a query ~40s mais lenta por causa do plano gerado).
            -- Tempo de espera: da senha (FLE_DTHR_CHEGADA) até a chamada real
            -- (FLE_DTHR_ATENDIMENTO, já na própria linha) — só cai pra abertura
            -- da OS (osm_dthr) quando não há chamada registrada.
            SELECT
                c.login_recep,
                c.setor_cod,
                COUNT(DISTINCT c.FLE_PAC_REG) AS total_pacientes,
                AVG(CAST(
                    CASE WHEN e.espera_min BETWEEN 0 AND 120 THEN e.espera_min ELSE NULL END
                AS FLOAT))                    AS espera_media_min
            FROM chegadas c
            OUTER APPLY (
                SELECT DATEDIFF(minute, c.FLE_DTHR_CHEGADA,
                    COALESCE(c.FLE_DTHR_ATENDIMENTO,
                        (SELECT TOP 1 o.osm_dthr FROM osm o
                         WHERE o.osm_pac = c.FLE_PAC_REG
                           AND CAST(o.osm_dthr AS DATE) = c.data_cheg
                           AND o.osm_dthr >= c.FLE_DTHR_CHEGADA
                         ORDER BY o.osm_dthr ASC))) AS espera_min
            ) e
            GROUP BY c.login_recep, c.setor_cod
        ),
        financeiro AS (
            SELECT
                c.login_recep,
                c.setor_cod,
                SUM({vliq}) AS producao
            FROM chegadas_prod c
            JOIN osm o ON o.osm_pac = c.FLE_PAC_REG
                      AND CAST(o.osm_dthr AS DATE) = c.data_cheg
            JOIN smm ON smm.SMM_OSM = o.osm_num AND smm.SMM_OSM_SERIE = o.osm_serie
            GROUP BY c.login_recep, c.setor_cod
        )
        SELECT
            ea.login_recep,
            RTRIM(ISNULL(u.USR_NOME, ea.login_recep)) AS nome_recep,
            ea.setor_cod,
            ISNULL(RTRIM(str.str_nome), ea.setor_cod) AS setor_nome,
            ea.total_pacientes,
            ea.espera_media_min,
            ISNULL(f.producao, 0)                      AS producao_financeira
        FROM esperas_agg ea
        LEFT JOIN financeiro f ON f.login_recep = ea.login_recep
                              AND f.setor_cod   = ea.setor_cod
        LEFT JOIN str ON RTRIM(str.str_cod) = ea.setor_cod
        LEFT JOIN usr u ON RTRIM(u.USR_LOGIN) = ea.login_recep
        ORDER BY ea.total_pacientes DESC
    """)
    return rows or []


@app.get("/api/recepcao/evolucao")
def recepcao_evolucao(periodo: str = "30d", setor: str = "", recepcionista: str = ""):
    """Evolução diária por turno (manhã/tarde) por recepcionista."""
    inicio, fim = periodo_datas(periodo)
    filtro_setor  = f"AND RTRIM(fle.FLE_STR_COD) = '{setor}'" if setor else ""
    filtro_recep  = f"AND RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)) = '{recepcionista}'" if recepcionista else ""

    rows = query(f"""
        SELECT
            CAST(fle.FLE_DTHR_CHEGADA AS DATE)                                AS data,
            CASE
                WHEN DATEPART(hour, fle.FLE_DTHR_CHEGADA) < 13 THEN 'Manhã'
                ELSE 'Tarde'
            END                                                                AS turno,
            RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO))        AS login_recep,
            RTRIM(ISNULL(u.USR_NOME,
                   ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)))       AS nome_recep,
            COUNT(DISTINCT fle.FLE_PAC_REG)                                    AS total_pacientes
        FROM fle
        LEFT JOIN usr u ON RTRIM(u.USR_LOGIN) =
                           RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO))
        WHERE fle.FLE_DTHR_CHEGADA BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND fle.FLE_PAC_REG > 0
          AND ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO) IS NOT NULL
          AND RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)) NOT LIKE 'TOTEM%'
          AND UPPER(RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO))) NOT LIKE '%ESTAGIARIO%'
          {filtro_setor}
          {filtro_recep}
        GROUP BY
            CAST(fle.FLE_DTHR_CHEGADA AS DATE),
            CASE WHEN DATEPART(hour, fle.FLE_DTHR_CHEGADA) < 13 THEN 'Manhã' ELSE 'Tarde' END,
            RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)),
            RTRIM(ISNULL(u.USR_NOME, ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)))
        ORDER BY data, turno
    """)
    for r in rows:
        if hasattr(r.get("data"), "strftime"):
            r["data"] = r["data"].strftime("%Y-%m-%d")
    return rows or []


@app.get("/api/recepcao/por-convenio")
def recepcao_por_convenio(periodo: str = "30d", setor: str = ""):
    """
    Pacientes atendidos e tempo médio de recepção (chegada até a chamada real da
    senha, ou abertura da 1ª OS do dia quando não há chamada registrada),
    agrupados por convênio — agregado de todas as recepcionistas.
    """
    inicio, fim = periodo_datas(periodo)
    filtro_setor = f"AND RTRIM(fle.FLE_STR_COD) = '{setor}'" if setor else ""

    rows = query(f"""
        WITH chegadas AS (
            SELECT
                fle.FLE_PAC_REG                    AS pac,
                fle.FLE_DTHR_CHEGADA                AS dthr_cheg,
                fle.FLE_DTHR_ATENDIMENTO             AS dthr_atend,
                CAST(fle.FLE_DTHR_CHEGADA AS DATE)  AS data_cheg
            FROM fle
            WHERE fle.FLE_DTHR_CHEGADA BETWEEN '{inicio}' AND '{fim} 23:59:59'
              AND fle.FLE_PAC_REG > 0
              AND ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO) IS NOT NULL
              AND RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)) NOT LIKE 'TOTEM%'
              AND UPPER(RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO))) NOT LIKE '%ESTAGIARIO%'
              {filtro_setor}
        ),
        os_do_dia AS (
            SELECT
                c.pac, c.dthr_cheg, c.dthr_atend, c.data_cheg, o.osm_dthr, o.osm_cnv,
                ROW_NUMBER() OVER (PARTITION BY c.pac, c.data_cheg ORDER BY o.osm_dthr ASC) AS rn
            FROM chegadas c
            JOIN osm o ON o.osm_pac = c.pac
                      AND CAST(o.osm_dthr AS DATE) = c.data_cheg
                      AND o.osm_dthr >= c.dthr_cheg
        ),
        primeira AS (
            -- Tempo de espera: da senha até a chamada real (dthr_atend) quando existe,
            -- senão até a abertura da 1ª OS do dia (osm_dthr).
            SELECT pac, osm_cnv,
                   DATEDIFF(minute, dthr_cheg, COALESCE(dthr_atend, osm_dthr)) AS espera_min
            FROM os_do_dia WHERE rn = 1
        )
        SELECT
            RTRIM(ISNULL(cnv.CNV_NOME, CAST(p.osm_cnv AS VARCHAR(50)))) AS convenio,
            COUNT(DISTINCT p.pac)                                       AS total_pacientes,
            AVG(CAST(CASE WHEN p.espera_min BETWEEN 0 AND 120 THEN p.espera_min ELSE NULL END AS FLOAT)) AS espera_media_min
        FROM primeira p
        LEFT JOIN cnv ON cnv.CNV_COD = p.osm_cnv
        GROUP BY RTRIM(ISNULL(cnv.CNV_NOME, CAST(p.osm_cnv AS VARCHAR(50))))
        ORDER BY total_pacientes DESC
    """)
    return rows or []


@app.get("/api/recepcao/convenios")
def recepcao_convenios(periodo: str = "30d", setor: str = "", recepcionista: str = ""):
    """Breakdown de convênios por recepcionista: quantidade de OS abertas."""
    inicio, fim = periodo_datas(periodo)
    filtro_setor = f"AND RTRIM(fle.FLE_STR_COD) = '{setor}'" if setor else ""
    filtro_recep = f"AND RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)) = '{recepcionista}'" if recepcionista else ""
    rows = query(f"""
        WITH pacientes AS (
            SELECT DISTINCT fle.FLE_PAC_REG,
                            CAST(fle.FLE_DTHR_CHEGADA AS DATE) AS data_cheg
            FROM fle
            WHERE fle.FLE_DTHR_CHEGADA BETWEEN '{inicio}' AND '{fim} 23:59:59'
              AND fle.FLE_PAC_REG > 0
              AND ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO) IS NOT NULL
              AND RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)) NOT LIKE 'TOTEM%'
              AND UPPER(RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO))) NOT LIKE '%ESTAGIARIO%'
              {filtro_setor}
              {filtro_recep}
        ),
        base AS (
            SELECT DISTINCT
                RTRIM(ISNULL(cnv.CNV_NOME, CAST(osm.osm_cnv AS VARCHAR(50)))) AS convenio,
                osm.osm_num,
                osm.osm_serie
            FROM pacientes p
            JOIN osm ON osm.osm_pac = p.FLE_PAC_REG
                    AND CAST(osm.osm_dthr AS DATE) = p.data_cheg
            LEFT JOIN cnv ON cnv.CNV_COD = osm.osm_cnv
        )
        SELECT convenio, COUNT(*) AS total_os
        FROM base
        GROUP BY convenio
        ORDER BY total_os DESC
    """)
    return rows or []


# ── Pontualidade: login x início real de atendimento ─────────────────────────
@app.get("/api/recepcao/usuarios")
def recepcao_usuarios():
    """Lista de recepcionistas (login+nome) com atendimento nos últimos 180 dias — pro seletor da tela de Pontualidade."""
    rows = query("""
        SELECT DISTINCT
            RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)) AS login,
            RTRIM(ISNULL(u.USR_NOME, ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO))) AS nome
        FROM fle
        LEFT JOIN usr u ON RTRIM(u.USR_LOGIN) = RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO))
        WHERE fle.FLE_DTHR_CHEGADA >= DATEADD(day, -180, GETDATE())
          AND ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO) IS NOT NULL
          AND RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO)) NOT LIKE 'TOTEM%'
          AND UPPER(RTRIM(ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO))) NOT LIKE '%ESTAGIARIO%'
        ORDER BY nome
    """)
    return rows or []


def _pontualidade_dados(login: str, inicio: str, fim: str):
    """
    Login (GR_SES) x início real de atendimento por dia, pro usuário/período.
    Início de atendimento = criação da primeira OS do dia (OSM_DTHR via
    OSM_USR_LOGIN_CAD) — não a chamada na fila (FLE_DTHR_ATENDIMENTO). FLE
    pode ser lançado fora de ordem (comparação real mostrou um "atraso" de
    112min que sumia ao olhar a OS, que bateu quase exato com o login), então
    OSM é o timestamp de transação mais confiável disponível.
    """
    rows = query("""
        SELECT
            d.dia,
            l.login_mais_cedo,
            o.primeira_os,
            o.qtd_os
        FROM (
            SELECT CAST(GR_SES_DTHR_INI AS DATE) AS dia, MIN(GR_SES_DTHR_INI) AS login_mais_cedo
            FROM GR_SES WHERE GR_USR_LOGIN = ? AND GR_SES_DTHR_INI BETWEEN ? AND ?
            GROUP BY CAST(GR_SES_DTHR_INI AS DATE)
        ) l
        FULL OUTER JOIN (
            SELECT CAST(OSM_DTHR AS DATE) AS dia, MIN(OSM_DTHR) AS primeira_os, COUNT(*) AS qtd_os
            FROM OSM WHERE RTRIM(OSM_USR_LOGIN_CAD) = ? AND OSM_DTHR BETWEEN ? AND ?
            GROUP BY CAST(OSM_DTHR AS DATE)
        ) o ON o.dia = l.dia
        CROSS APPLY (SELECT COALESCE(l.dia, o.dia) AS dia) d
        ORDER BY d.dia
    """, (login, inicio, f"{fim} 23:59:59", login, inicio, f"{fim} 23:59:59"))

    DIAS_PT = {0:"Segunda",1:"Terça",2:"Quarta",3:"Quinta",4:"Sexta",5:"Sábado",6:"Domingo"}
    linhas = []
    for r in rows:
        login_dt = r["login_mais_cedo"]
        atend_dt = r["primeira_os"]
        gap = round((atend_dt - login_dt).total_seconds() / 60) if login_dt and atend_dt else None
        linhas.append({
            "dia": r["dia"].strftime("%d/%m/%Y"),
            "dia_semana": DIAS_PT[r["dia"].weekday()],
            "login": login_dt.strftime("%H:%M:%S") if login_dt else None,
            "atendimento": atend_dt.strftime("%H:%M:%S") if atend_dt else None,
            "gap_min": gap,
            "qtd": r["qtd_os"] or 0,
        })
    return linhas


@app.get("/api/recepcao/pontualidade")
def recepcao_pontualidade(login: str, inicio: str, fim: str):
    """Relatório de pontualidade (login x início de atendimento) em JSON."""
    login = login.strip().upper()
    linhas = _pontualidade_dados(login, inicio, fim)
    usr = query("SELECT RTRIM(ISNULL(USR_NOME, ?)) AS nome FROM USR WHERE RTRIM(USR_LOGIN) = ?", (login, login))
    nome = usr[0]["nome"] if usr else login

    gaps = [l["gap_min"] for l in linhas if l["gap_min"] is not None]
    qtds = [l["qtd"] for l in linhas if l["qtd"]]
    resumo = {
        "login": login,
        "nome": nome,
        "inicio": inicio,
        "fim": fim,
        "dias": len(linhas),
        "intervalo_medio_min": round(sum(gaps) / len(gaps), 1) if gaps else None,
        "total_atendimentos": sum(qtds),
        "media_atendimentos_dia": round(sum(qtds) / len(qtds), 1) if qtds else 0,
    }
    return {"resumo": resumo, "linhas": linhas}


@app.get("/api/recepcao/pontualidade/pdf")
def recepcao_pontualidade_pdf(login: str, inicio: str, fim: str, background_tasks: BackgroundTasks):
    """Mesmo relatório de pontualidade, mas devolvido como PDF pronto pra baixar/enviar."""
    import subprocess, tempfile, base64 as _b64, uuid

    login = login.strip().upper()
    linhas = _pontualidade_dados(login, inicio, fim)
    usr = query("SELECT RTRIM(ISNULL(USR_NOME, ?)) AS nome FROM USR WHERE RTRIM(USR_LOGIN) = ?", (login, login))
    nome = usr[0]["nome"] if usr else login

    gaps = [l["gap_min"] for l in linhas if l["gap_min"] is not None]
    qtds = [l["qtd"] for l in linhas if l["qtd"]]
    intervalo_medio = round(sum(gaps) / len(gaps), 1) if gaps else 0
    total_atend = sum(qtds)
    media_atend = round(sum(qtds) / len(qtds), 1) if qtds else 0

    logo_path = os.path.join(DIST, "..", "public", "icds_logo.png")
    logo_b64 = ""
    try:
        with open(logo_path, "rb") as f:
            logo_b64 = _b64.b64encode(f.read()).decode()
    except FileNotFoundError:
        pass

    linhas_html = ""
    for l in linhas:
        destaque = ' style="background:#FEF2F2;"' if (l["gap_min"] or 0) >= 30 else ""
        gap_txt = f'{l["gap_min"]} min' if l["gap_min"] is not None else "—"
        gap_cor = "#DC2626" if (l["gap_min"] or 0) >= 30 else ("#D97706" if (l["gap_min"] or 0) >= 10 else "#059669")
        linhas_html += f"""
        <tr{destaque}>
          <td>{l['dia']}</td><td>{l['dia_semana']}</td>
          <td>{l['login'] or '—'}</td><td>{l['atendimento'] or '—'}</td>
          <td style="color:{gap_cor};font-weight:700;">{gap_txt}</td>
          <td style="text-align:center;">{l['qtd']}</td>
        </tr>"""

    html = f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><style>
      @page {{ margin: 18mm 14mm; }}
      * {{ box-sizing: border-box; }}
      body {{ font-family: 'Segoe UI', Arial, sans-serif; color:#1E293B; margin:0; }}
      .header {{ display:flex; justify-content:space-between; align-items:center; border-bottom:3px solid #8B1A1A; padding-bottom:14px; margin-bottom:20px; }}
      .header img {{ height:42px; }}
      .header .titulo {{ text-align:right; }}
      .header .titulo h1 {{ font-size:18px; margin:0; color:#8B1A1A; }}
      .header .titulo p {{ font-size:11px; color:#64748B; margin:2px 0 0; }}
      .info {{ display:flex; gap:14px; margin-bottom:18px; flex-wrap:wrap; }}
      .info-card {{ background:#F8FAFC; border-radius:8px; padding:10px 16px; border-left:4px solid #8B1A1A; flex:1; min-width:140px; }}
      .info-card .label {{ font-size:10px; color:#64748B; text-transform:uppercase; font-weight:700; letter-spacing:.04em; }}
      .info-card .valor {{ font-size:18px; font-weight:800; color:#111827; margin-top:2px; }}
      table {{ width:100%; border-collapse:collapse; font-size:12px; }}
      th {{ background:#8B1A1A; color:#fff; padding:8px 10px; text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.03em; }}
      td {{ padding:7px 10px; border-bottom:1px solid #E2E8F0; }}
      tr:nth-child(even) {{ background:#FAFAFA; }}
      .legenda {{ margin-top:14px; font-size:10.5px; color:#64748B; }}
      .legenda span {{ display:inline-block; margin-right:16px; }}
      .footer {{ margin-top:24px; font-size:10px; color:#94A3B8; border-top:1px solid #E2E8F0; padding-top:8px; }}
    </style></head><body>
      <div class="header">
        <img src="data:image/png;base64,{logo_b64}" alt="ICDS"/>
        <div class="titulo">
          <h1>Relatório de Pontualidade — Login x Início de Atendimento</h1>
          <p>Usuário: <b>{login}</b> ({nome}) &nbsp;·&nbsp; Período: {inicio[8:10]}/{inicio[5:7]}/{inicio[0:4]} a {fim[8:10]}/{fim[5:7]}/{fim[0:4]}</p>
        </div>
      </div>
      <div class="info">
        <div class="info-card"><div class="label">Dias no período</div><div class="valor">{len(linhas)}</div></div>
        <div class="info-card"><div class="label">Intervalo médio login → atendimento</div><div class="valor">{intervalo_medio} min</div></div>
        <div class="info-card"><div class="label">Total de atendimentos</div><div class="valor">{total_atend}</div></div>
        <div class="info-card"><div class="label">Média de atendimentos/dia</div><div class="valor">{media_atend}</div></div>
      </div>
      <table><thead><tr>
        <th>Data</th><th>Dia</th><th>Login</th><th>Início Atendimento</th><th>Intervalo</th><th>Atendimentos</th>
      </tr></thead><tbody>{linhas_html}</tbody></table>
      <div class="legenda">
        <span><b style="color:#059669;">&#9679;</b> até 10min = normal</span>
        <span><b style="color:#D97706;">&#9679;</b> 10-30min = atenção</span>
        <span><b style="color:#DC2626;">&#9679;</b> 30min+ = fora do padrão</span>
      </div>
      <div class="footer">
        Login = horário de abertura de sessão no sistema (GR_SES). Início de atendimento = criação da primeira OS do dia pelo usuário (OSM).
        Dias sem expediente não aparecem na tabela. Relatório gerado automaticamente pelo Dashboard ICDS.
      </div>
    </body></html>"""

    tmp_dir = tempfile.gettempdir()
    uid = uuid.uuid4().hex
    html_path = os.path.join(tmp_dir, f"pontualidade_{uid}.html")
    pdf_path = os.path.join(tmp_dir, f"pontualidade_{uid}.pdf")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    try:
        subprocess.run([
            chrome_path, "--headless", "--disable-gpu", "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}", f"file:///{html_path}",
        ], timeout=30, capture_output=True)
    finally:
        try: os.remove(html_path)
        except OSError: pass

    if not os.path.exists(pdf_path):
        raise HTTPException(500, "Falha ao gerar PDF")

    background_tasks.add_task(lambda: os.remove(pdf_path) if os.path.exists(pdf_path) else None)
    return FileResponse(
        pdf_path, media_type="application/pdf",
        filename=f"Pontualidade_{login}_{inicio}_a_{fim}.pdf",
        background=background_tasks,
    )


@app.get("/api/health")
def health():
    try:
        conn = get_conn()
        conn.close()
        return {"status": "ok", "db": "conectado", "ts": datetime.now().isoformat()}
    except Exception as e:
        return {"status": "erro", "detalhe": str(e)}

# ══════════════════════════════════════════════════════════════════════════════
# INTEGRAÇÃO CLINIA — plataforma de agendamento via WhatsApp
#
# Em vez de pagar a API oficial da Pixeon, expomos aqui só o necessário para a
# Clinia consultar (leitura), direto no banco Smart via a mesma conexão que o
# resto do dashboard já usa. Autenticado por API key própria (header
# X-API-Key, valor em CLINIA_API_KEY no .env) — NÃO é a mesma coisa que login
# de usuário (censo_permissoes), é uma chave única para o servidor da Clinia.
#
# Fase 1 (implementada): busca de paciente + consulta de disponibilidade.
# Fase 2 (NÃO implementada de propósito): criar agendamento. A tabela AGM tem
# 145 colunas e claramente embute regras de negócio do app da Pixeon (cálculo
# de valor por convênio, workflow de confirmação, etc.) — INSERT direto ali
# tem risco real de duplicar horário ou gravar dado inconsistente. Antes de
# escrever, mapear com precisão os campos obrigatórios comparando com
# agendamentos reais e validar em smart_hml.
# ══════════════════════════════════════════════════════════════════════════════

from fastapi import Depends, Security
from fastapi.security.api_key import APIKeyHeader

_clinia_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def _clinia_ips_permitidos():
    bruto = os.environ.get("CLINIA_ALLOWED_IPS", "")
    return {ip.strip() for ip in bruto.split(",") if ip.strip()}

def verificar_clinia_key(request: Request, api_key: str = Security(_clinia_api_key_header)):
    # Falha fechado: sem lista de IPs configurada, ninguém passa — mesmo com a key certa.
    permitidos = _clinia_ips_permitidos()
    if not permitidos:
        raise HTTPException(503, "Integração Clinia não configurada: defina CLINIA_ALLOWED_IPS no .env")

    ip_origem = request.client.host if request.client else None
    if ip_origem not in permitidos:
        raise HTTPException(403, "IP não autorizado para esta integração")

    esperado = os.environ.get("CLINIA_API_KEY", "")
    if not esperado or not api_key or not hmac.compare_digest(api_key, esperado):
        raise HTTPException(401, "API key inválida ou ausente (header X-API-Key)")
    return True


def _clinia_so_digitos(s):
    return _re.sub(r"\D", "", s or "")


@app.get("/api/clinia/paciente/buscar")
def clinia_buscar_paciente(
    telefone: str = None,
    cpf: str = None,
    nome: str = None,
    _auth: bool = Depends(verificar_clinia_key),
):
    """
    Busca paciente por telefone/celular, CPF ou nome — para a Clinia confirmar
    identidade do paciente antes de mostrar/oferecer agendamento.
    Informe exatamente um dos filtros (prioridade: telefone > cpf > nome).
    """
    if not telefone and not cpf and not nome:
        raise HTTPException(400, "Informe ao menos um filtro: telefone, cpf ou nome")

    campos = """
            pac.pac_reg                             AS reg,
            LTRIM(RTRIM(pac.pac_nome))               AS nome,
            RTRIM(ISNULL(pac.PAC_FONE,''))           AS fone,
            RTRIM(ISNULL(pac.PAC_CELULAR,''))        AS celular,
            RTRIM(ISNULL(pac.PAC_NUMCPF,''))          AS cpf,
            CONVERT(VARCHAR(10), pac.pac_nasc, 120)  AS nascimento,
            RTRIM(ISNULL(pac.pac_sexo,''))            AS sexo,
            RTRIM(ISNULL(pac.PAC_EMAIL,''))          AS email,
            RTRIM(ISNULL(pac.pac_ind_whatsapp,''))   AS whatsapp
    """

    if telefone:
        alvo = _clinia_so_digitos(telefone)
        sufixo = alvo[-8:] if len(alvo) >= 8 else alvo
        if len(sufixo) < 6:
            raise HTTPException(400, "Telefone precisa ter ao menos 6 dígitos")
        candidatos = query(f"""
            SELECT TOP 30 {campos}
            FROM pac
            WHERE (pac.PAC_FONE LIKE ? OR pac.PAC_CELULAR LIKE ?)
              AND (pac.pac_dt_obito IS NULL OR pac.pac_dt_obito = '')
            ORDER BY pac.pac_reg DESC
        """, (f"%{sufixo}%", f"%{sufixo}%"))
        rows = [c for c in candidatos
                if _clinia_so_digitos(c["fone"]).endswith(sufixo)
                or _clinia_so_digitos(c["celular"]).endswith(sufixo)]
    elif cpf:
        alvo = _clinia_so_digitos(cpf)
        rows = query(f"""
            SELECT TOP 10 {campos}
            FROM pac
            WHERE RTRIM(ISNULL(pac.PAC_NUMCPF,'')) = ?
              AND (pac.pac_dt_obito IS NULL OR pac.pac_dt_obito = '')
        """, (alvo,))
    else:
        rows = query(f"""
            SELECT TOP 20 {campos}
            FROM pac
            WHERE UPPER(RTRIM(pac.pac_nome)) LIKE ?
              AND (pac.pac_dt_obito IS NULL OR pac.pac_dt_obito = '')
            ORDER BY pac.pac_nome
        """, (f"%{nome.upper()}%",))

    return {"total": len(rows), "pacientes": rows}


@app.get("/api/clinia/agenda/disponibilidade")
def clinia_disponibilidade(
    medico: int = None,
    servico: str = None,
    data_ini: str = None,
    data_fim: str = None,
    _auth: bool = Depends(verificar_clinia_key),
):
    """
    Lista horários disponíveis para agendamento (vagas reabertas por
    cancelamento — AGM_STAT='C').

    LIMITAÇÃO CONHECIDA: a grade completa de horários de cada médico é
    definida na tabela AGD através de um template codificado em bitmask
    (campos AGD_MAT/AGD_VESP), que não é decodificado aqui. Esta consulta
    só enxerga horários que já existiram como linha na AGM e foram
    cancelados (ficando livres de novo) — não é a grade inteira de
    disponibilidade em aberto. Suficiente para reaproveitar cancelamentos;
    para a grade completa seria necessário decodificar o AGD.
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    if not data_ini:
        data_ini = hoje
    if not data_fim:
        data_fim = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    condicoes = ["agm.agm_hini >= ?", "agm.agm_hini < DATEADD(day,1,CAST(? AS DATE))", "RTRIM(agm.agm_stat) = 'C'"]
    params = [data_ini, data_fim]
    if medico:
        condicoes.append("agm.agm_med = ?")
        params.append(medico)
    if servico:
        condicoes.append("RTRIM(agm.agm_smk) = ?")
        params.append(servico.upper())

    where = " AND ".join(condicoes)
    rows = query(f"""
        SELECT
            agm.agm_med                        AS medico_cod,
            LTRIM(RTRIM(psv.psv_nome))         AS medico_nome,
            LTRIM(RTRIM(esp.esp_nome))         AS especialidade,
            RTRIM(agm.agm_smk)                 AS servico_cod,
            LTRIM(RTRIM(smk.SMK_NOME))         AS servico_nome,
            agm.agm_hini                       AS inicio,
            agm.agm_hfim                       AS fim,
            LTRIM(RTRIM(loc.loc_nome))         AS local
        FROM agm
        JOIN psv  ON psv.psv_cod   = agm.agm_med
        LEFT JOIN esp ON esp.esp_cod  = agm.AGM_ESP_COD
        LEFT JOIN loc ON loc.loc_cod  = agm.agm_loc
        LEFT JOIN SMK ON RTRIM(SMK.SMK_COD) = RTRIM(agm.agm_smk)
        WHERE {where}
        ORDER BY agm.agm_hini
    """, tuple(params))

    for r in rows:
        if hasattr(r.get("inicio"), "strftime"):
            r["inicio"] = r["inicio"].strftime("%Y-%m-%d %H:%M")
        if hasattr(r.get("fim"), "strftime"):
            r["fim"] = r["fim"].strftime("%Y-%m-%d %H:%M")

    return {"total": len(rows), "horarios": rows}


# ── PAINEL DE SENHAS (TV das recepções) ──────────────────────────────────────
# Serve direto da pasta onde o painel é editado — as estações só precisam
# abrir a URL (ex: http://192.168.1.40:31000/painel-tv/painel_recepcao.html),
# sem instalar nem copiar nada. Precisa vir ANTES do catch-all do SPA abaixo.
_PAINEL_TV_DIR = r"C:\Users\administrator.CENSO\Desktop\painel_recepcao"
if os.path.exists(_PAINEL_TV_DIR):
    app.mount("/painel-tv", StaticFiles(directory=_PAINEL_TV_DIR, html=True), name="painel_tv")

# Logos dos convênios (usadas na Guia SP/SADT) — mesmas imagens que o Smart usa
# nativamente, arquivo "c-<CNV_COD>.bmp".
_TISS_LOGOS_DIR = r"C:\Smart\tiss"
if os.path.exists(_TISS_LOGOS_DIR):
    app.mount("/tiss-logos", StaticFiles(directory=_TISS_LOGOS_DIR), name="tiss_logos")

# ── SERVE FRONTEND — FINAL DO ARQUIVO ────────────────────────────────────────
if os.path.exists(DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(DIST, "index.html"))

    @app.get("/{full_path:path}")

    def serve_spa(full_path: str):
        blocked = [".env", "config.py", ".key", ".crt", "main.py"]
        if any(full_path.endswith(b) for b in blocked):
            raise HTTPException(status_code=403, detail="Forbidden")
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        f = os.path.join(DIST, full_path)
        if os.path.exists(f) and not os.path.isdir(f):
            return FileResponse(f)
        return FileResponse(os.path.join(DIST, "index.html"))


# ──────────────────────────────────────────────────────────────────────────────
# ✅ TODAS AS COLUNAS VALIDADAS CONTRA DICIONÁRIO OFICIAL PIXEON SMART
# ──────────────────────────────────────────────────────────────────────────────
# ✓ osm → osm_serie, osm_num, osm_pac, osm_dthr, osm_cnv, osm_mreq,
#          osm_atend (ASS/EME/INT/CRG/TAM...), osm_dthr_saida, OSM_AGM_ID
# ✓ cnv → cnv_cod (PK char 3), cnv_nome, cnv_stat (A/C),
#          cnv_tipo (AM/HP/AH/MC), cnv_reg_ans
# ✓ pac → pac_reg (PK int), pac_nome, pac_nasc, pac_dreg, pac_sexo (M/F),
#          pac_dult, pac_falta, pac_dt_obito
#          JOIN: pac.pac_reg = osm.osm_pac
# ✓ agm → agm_med, agm_pac, agm_loc, agm_hini, agm_hfim, agm_dtmrc,
#          agm_stat (A/E/C/B), agm_confirm_stat (A/C/N),
#          agm_pac_nome, agm_id, AGM_ESP_COD, agm_valor, agm_canc_dthr
#          JOIN com osm: agm.agm_id = osm.OSM_AGM_ID
# ✓ psv → psv_cod (PK int), psv_nome (char 50), psv_apel (char 20),
#          psv_esp_cod (char 3), psv_crm, psv_vinc (S/F/P/J/C/R/O)
#          JOIN com osm: psv.psv_cod = osm.osm_mreq
# ✓ fat → fat_serie + fat_num (PK), fat_cnv, fat_demi, fat_venc,
#          fat_val (faturado), fat_sld (em aberto), fat_stat
#          JOIN: fat.fat_cnv = cnv.cnv_cod
# ✓ mte → mte_serie + mte_seq (PK), mte_pac_reg, mte_tipo,
#          mte_dthr, mte_valor, mte_desconto, mte_juros,
#          mte_del_logica ('S'=cancelado — filtrar),
#          mte_estorno ('S'=estorno — filtrar),
#          mte_status, mte_osm_serie, mte_osm (FK OS)
# ✓ esp → esp_cod (PK char 3), esp_nome (varchar 100),
#          esp_del_logica ('S'=deletado — filtrar com <> 'S')
# ──────────────────────────────────────────────────────────────────────────────