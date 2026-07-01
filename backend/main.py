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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# WhatsApp / Scheduler (importação opcional — não quebra se arquivos não existem)
try:
    from whatsapp_sender import enviar_resumo as _wpp_enviar
    from scheduler import set_query_func, iniciar_scheduler_em_background
    _WPP_AVAILABLE = True
except ImportError:
    _WPP_AVAILABLE = False
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

app = FastAPI(title="Dashboard Clínica", version="1.1.0")

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
from pydantic import BaseModel
from fastapi import HTTPException

# ── Todos os módulos disponíveis no sistema ───────────────────────────────────
TODOS_MODULOS = [
    {"id": "clinica",       "label": "Clínica"},
    {"id": "recepcao",      "label": "Recepção"},
    {"id": "producao",      "label": "Produção Mensal"},
    {"id": "pacientesdb",   "label": "Pacientes DB"},
    {"id": "estoque",       "label": "Estoque"},
    {"id": "painel_tv",     "label": "Painel TV"},
    {"id": "contratos",     "label": "Contratos"},
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


# ── Adicione no startup do FastAPI ────────────────────────────────────────────
# @app.on_event("startup")
# async def startup_event():
#     inicializar_tabela_permissoes()
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
    return [r["cp_modulo"] for r in rows]

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

@app.post("/api/home/briefing")
def home_briefing(payload: dict):
    prompt = payload.get("prompt", "")
    try:
        import os
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return {"texto": "Configure a variável OPENAI_API_KEY no servidor."}
        
        res = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "max_tokens": 300,
                "messages": [
                    {"role": "system", "content": "Você é um analista de gestão clínica especialista financeiro com insights revolucionarios, sempre dê dicas que você achar importante para aumentar a produção. Responda sempre em português brasileiro, de forma direta e profissional."},
                    {"role": "user", "content": prompt}
                ],
            },
            timeout=30,
        )
        data = res.json()
        texto = data["choices"][0]["message"]["content"]
        return {"texto": texto}
    except Exception as e:
        return {"texto": f"Erro: {str(e)}"}

@app.post("/api/home/briefing")
def home_briefing(payload: dict):
    prompt = payload.get("prompt", "")
    api_key = os.getenv("OPENAI_API_KEY", "")
    print(f"DEBUG API KEY: '{api_key[:10] if api_key else 'VAZIO'}'")
    ...

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
            USR_EMAIL              AS email
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

    # Admin vê tudo automaticamente se não tiver permissões configuradas
    if admin and not modulos:
        modulos = [m["id"] for m in TODOS_MODULOS]

    return {
        "ok":      True,
        "login":   login_str,
        "nome":    (u.get("nome_completo") or u.get("nome") or login_str).strip(),
        "nivel":   str(u.get("nivel") or "").strip(),
        "email":   str(u.get("email") or "").strip(),
        "admin":   admin,
        "modulos": modulos,
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

    # Projeção do mês
    hoje = date.today()
    dias_uteis_passados = len([r for r in por_dia if r.get("producao", 0) > 0])
    prod_acumulada = kpis_atual.get("producao", 0) or 0
    total_dias_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    dias_restantes = sum(
        1 for d in range(hoje.day + 1, total_dias_mes + 1)
        if date(hoje.year, hoje.month, d).weekday() != 6
    )
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
            "dias_uteis_passados": dias_uteis_passados,
            "dias_restantes":      dias_restantes,
            "acumulado":           round(prod_acumulada, 2),
        },
        "setor":   setor,
        "periodo": periodo,
    }


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
            u.usr_dt_last_login       AS ultimo_login
        FROM usr u
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
    for r in rows:
        r["recebido_caixa"] = mte_dict.get(r["mes"], 0)

    return rows
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
# PRODUÇÃO MENSAL — grade diária por tipo de atendimento
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/financeiro/producao-mensal")
def producao_mensal(ano: int = None, mes: int = None, meta_diaria: float = None, meta_mensal_fixa: float = 1200000.0):
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

    # Dias úteis restantes no mês (seg-sáb, a partir de amanhã)
    hoje = now.date()
    dias_restantes = 0
    if ano == hoje.year and mes == hoje.month:
        import datetime as dt
        for d in range(hoje.day + 1, ultimo_dia + 1):
            dia = dt.date(ano, mes, d)
            if dia.weekday() < 6:  # 0=seg ... 5=sáb
                dias_restantes += 1

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

    dias_uteis_mes = sum(
        1 for d in range(1, ultimo_dia + 1)
        if dt.date(ano, mes, d).weekday() < 6          # Seg(0) a Sáb(5)
        and dt.date(ano, mes, d) not in feriados        # não é feriado
    )

    # Dias úteis restantes (a partir de amanhã)
    if ano == hoje.year and mes == hoje.month:
        dias_restantes = sum(
            1 for d in range(hoje.day + 1, ultimo_dia + 1)
            if dt.date(ano, mes, d).weekday() < 6
            and dt.date(ano, mes, d) not in feriados
        )

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
        "dias_restantes":     dias_restantes,
        "dias_uteis_mes":     dias_uteis_mes,
    }
# Adicione este endpoint no main.py logo após o /api/financeiro/producao-mensal

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
          AND CAST(agm.agm_hini AS DATE) = ?
        ORDER BY agm.agm_hini
    """, (cod_medico, data))
    STATUS  = {"A":"Aberto","E":"Executado","C":"Cancelado","B":"Bloqueado"}
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
          AND CAST(agm.agm_hini AS DATE) BETWEEN ? AND ?
        GROUP BY CAST(agm.agm_hini AS DATE)
        ORDER BY data
    """, (cod_medico, inicio, fim))
    for r in rows:
        if hasattr(r.get("data"), "strftime"):
            r["data"] = r["data"].strftime("%Y-%m-%d")
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

@app.get("/api/modulo/ocupacional/resumo")
def ocupacional_modulo_resumo(periodo: str = "30d"):
    inicio, fim = periodo_datas(periodo)
    fin = modulo_resumo_financeiro(inicio, fim, OCUP_CODES)
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
        SELECT TOP 10 cnv.cnv_nome AS empresa,
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

@app.get("/api/modulo/servicos/resumo")
def servicos_resumo(periodo: str = "30d"):
    """
    Serviços especializados identificados pelo campo SMM_ESP dos itens da OS.
    Inclui Psicologia (PSC), Nutrição (NUT), Fonoaudiologia (FON), etc.
    """
    inicio, fim = periodo_datas(periodo)
    codes_sql = ",".join(f"'{c}'" for c in SERVICOS_ESP_CODES)

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

    return {
        "financeiro": fin[0] if fin else {},
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

@app.get("/api/modulo/laboratorio/resumo")
def laboratorio_resumo(periodo: str = "30d", setor: str = ""):
    """
    setor: 'diagnostico' → exclui OSs ocupacionais (ASS only)
           'ocupacional' → apenas OSs ocupacionais (ADM,PER,DEM etc)
           ''            → todos
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

    return {
        "financeiro": fin[0] if fin else {},
        "por_tipo": por_tipo,
        "grupos": grupos,
        "por_convenio": conv,
        "por_dia": por_dia,
        "top_medicos": top_medicos,
    }


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
            -- Total de horários (vagas disponíveis + marcações)
            ISNULL((SELECT COUNT(*) FROM EX_HORARIOS WHERE HOR_DATA = '{hoje}'), 0)
            + SUM(CASE WHEN agm.agm_pac > 0 THEN 1 ELSE 0 END)             AS total_horarios,
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

@app.get("/api/modulo/agendamentos/resumo")
def agendamentos_modulo_resumo(periodo: str = "30d"):
    inicio, fim = periodo_datas(periodo)
    # Stats agendamento
    stats = query(f"""
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

@app.get("/api/painel/resumo-hoje")
def painel_resumo_hoje(meta_diaria: float = None, setor: str = ""):
    """KPIs do dia atual em tempo real."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    filtro_str = f"AND RTRIM(osm.osm_str) = '{setor}'" if setor else ""

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

    # Tempo de espera — lógica unificada para todos os setores:
    # FLE_DTHR_CHEGADA (chegada do paciente) → osm_dthr (abertura da OS = início do atendimento)
    # Deduplica com TOP 1 para pegar a chegada mais recente antes da OS de cada paciente
    filtro_str_espera = f"AND RTRIM(osm.osm_str) = '{setor}'" if setor else ""
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
                    (SELECT TOP 1 f2.FLE_DTHR_CHEGADA
                     FROM fle f2
                     WHERE f2.FLE_PAC_REG = osm.osm_pac
                       AND RTRIM(f2.FLE_STR_COD) = RTRIM(osm.osm_str)
                       AND CAST(f2.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
                       AND f2.FLE_DTHR_CHEGADA <= osm.osm_dthr
                       AND f2.FLE_PAC_REG > 0
                     ORDER BY f2.FLE_DTHR_CHEGADA DESC),
                    osm.osm_dthr
                ) AS espera_min
            FROM osm
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



@app.get("/api/painel/setores")
def painel_setores():
    """Setores ativos hoje — OSM como fonte principal, espera média via FLE."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    rows = query(f"""
        SELECT TOP 12
            RTRIM(osm.osm_str)                                   AS setor_cod,
            RTRIM(str.str_nome)                                  AS setor_nome,
            COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num)   AS atendimentos,
            -- espera media: FLE chegada → OS abertura, deduplificado por paciente
            (SELECT AVG(t.espera_min) FROM (
                SELECT DISTINCT osm2.osm_serie, osm2.osm_num,
                    DATEDIFF(minute,
                        (SELECT TOP 1 f2.FLE_DTHR_CHEGADA FROM fle f2
                         WHERE f2.FLE_PAC_REG = osm2.osm_pac
                           AND RTRIM(f2.FLE_STR_COD) = RTRIM(osm2.osm_str)
                           AND CAST(f2.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
                           AND f2.FLE_DTHR_CHEGADA <= osm2.osm_dthr
                           AND f2.FLE_PAC_REG > 0
                         ORDER BY f2.FLE_DTHR_CHEGADA DESC),
                        osm2.osm_dthr) AS espera_min
                FROM osm osm2
                WHERE CAST(osm2.osm_dthr AS DATE) = '{hoje}'
                  AND RTRIM(osm2.osm_str) = RTRIM(osm.osm_str)
            ) t WHERE t.espera_min BETWEEN 1 AND 120)            AS espera_media_min
        FROM osm
        LEFT JOIN str ON str.str_cod = osm.osm_str
        WHERE CAST(osm.osm_dthr AS DATE) = '{hoje}'
          AND osm.osm_str IS NOT NULL
          AND LTRIM(RTRIM(osm.osm_str)) <> ''
        GROUP BY RTRIM(osm.osm_str), RTRIM(str.str_nome)
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
# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS DOS PAINÉIS TV — Somente leitura da FLE
# Cole no main.py
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/painel-fila/senhas")
def painel_fila_senhas(limite: int = 8):
    """
    Painel TV — Senhas chamadas pela recepção (guichês).
    Fonte: FLE onde FLE_BIP está preenchido (senha do totem)
    e FLE_DTHR_ATENDIMENTO foi atualizado pelo Smart.
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    rows = query(f"""
        SELECT TOP {limite}
            RTRIM(ISNULL(fle.FLE_BIP, ''))                          AS senha,
            CAST(fle.FLE_ORDEM AS INT)                              AS ordem,
            RTRIM(psv.psv_apel)                                     AS psv_apel,
            RTRIM(psv.psv_nome)                                     AS psv_nome,
            RTRIM(ISNULL(esp.esp_nome,''))                          AS especialidade,
            RTRIM(fle.FLE_STR_COD)                                  AS setor,
            CONVERT(VARCHAR(5),fle.FLE_DTHR_ATENDIMENTO,108)        AS chamado_em,
            RTRIM(ISNULL(fle.fle_pac_nome,
                   RTRIM(ISNULL(pac.pac_nome,''))))                 AS pac_nome,
            fle.FLE_PREFERENCIAL                                    AS preferencial,
            DATEDIFF(minute, fle.FLE_DTHR_CHEGADA,
                     fle.FLE_DTHR_ATENDIMENTO)                      AS espera_min
        FROM fle
        JOIN psv ON psv.psv_cod = fle.FLE_PSV_COD
        LEFT JOIN esp ON esp.esp_cod = psv.psv_esp_cod
        LEFT JOIN pac ON pac.pac_reg = fle.FLE_PAC_REG
        WHERE CAST(fle.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
          AND fle.FLE_DTHR_ATENDIMENTO IS NOT NULL
          AND fle.FLE_BIP IS NOT NULL
          AND LTRIM(RTRIM(fle.FLE_BIP)) <> ''
        ORDER BY fle.FLE_DTHR_ATENDIMENTO DESC
    """)
    return rows


@app.get("/api/painel-fila/status-senhas")
def painel_fila_status_senhas():
    """
    Status das filas de senha por prestador — lateral do painel TV.
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
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
        GROUP BY fle.FLE_PSV_COD, RTRIM(psv.psv_apel),
                 RTRIM(ISNULL(esp.esp_nome,''))
        ORDER BY na_fila DESC
    """)
    return rows


@app.get("/api/painel-fila/pacientes")
def painel_fila_pacientes(limite: int = 8):
    """
    Painel TV — Pacientes chamados pelos médicos no Smart.
    Fonte: FLE onde FLE_LOC_COD foi preenchido pelo Smart
    ao chamar o paciente (sem FLE_BIP — são filas de consultório).
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    rows = query(f"""
        SELECT TOP {limite}
            RTRIM(ISNULL(fle.fle_pac_nome,
                   RTRIM(ISNULL(pac.pac_nome,''))))                 AS pac_nome,
            fle.FLE_PAC_REG                                         AS pac_reg,
            RTRIM(psv.psv_apel)                                     AS psv_apel,
            RTRIM(psv.psv_nome)                                     AS psv_nome,
            RTRIM(ISNULL(esp.esp_nome,''))                          AS especialidade,
            RTRIM(ISNULL(loc.LOC_NOME,''))                          AS local_nome,
            RTRIM(ISNULL(fle.FLE_LOC_COD,''))                       AS local_cod,
            RTRIM(fle.FLE_STR_COD)                                  AS setor,
            CONVERT(VARCHAR(5),fle.FLE_DTHR_ATENDIMENTO,108)        AS chamado_em,
            fle.FLE_PREFERENCIAL                                    AS preferencial,
            DATEDIFF(minute, fle.FLE_DTHR_CHEGADA,
                     fle.FLE_DTHR_ATENDIMENTO)                      AS espera_min
        FROM fle
        JOIN psv ON psv.psv_cod = fle.FLE_PSV_COD
        LEFT JOIN esp ON esp.esp_cod = psv.psv_esp_cod
        LEFT JOIN pac ON pac.pac_reg = fle.FLE_PAC_REG
        LEFT JOIN loc ON RTRIM(loc.LOC_COD) = RTRIM(fle.FLE_LOC_COD)
        WHERE CAST(fle.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
          AND fle.FLE_DTHR_ATENDIMENTO IS NOT NULL
          AND fle.FLE_LOC_COD IS NOT NULL
          AND LTRIM(RTRIM(fle.FLE_LOC_COD)) <> ''
        ORDER BY fle.FLE_DTHR_ATENDIMENTO DESC
    """)
    for r in rows:
        if r.get("pac_nome"):
            r["pac_nome"] = str(r["pac_nome"]).strip().title()
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
        GROUP BY fle.FLE_PSV_COD, RTRIM(psv.psv_apel),
                 RTRIM(ISNULL(esp.esp_nome,'')), RTRIM(ISNULL(loc.LOC_NOME,''))
        HAVING SUM(CASE WHEN fle.FLE_DTHR_ATENDIMENTO IS NULL
                         AND fle.FLE_STATUS = 'A' THEN 1 ELSE 0 END) > 0
        ORDER BY aguardando DESC
    """)
    return rows
# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS DOS PAINÉIS TV — Somente leitura da FLE
# Cole no main.py
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/painel-fila/senhas")
def painel_fila_senhas(limite: int = 8):
    """
    Painel TV — Senhas chamadas pela recepção (guichês).
    Fonte: FLE onde FLE_BIP está preenchido (senha do totem)
    e FLE_DTHR_ATENDIMENTO foi atualizado pelo Smart.
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    rows = query(f"""
        SELECT TOP {limite}
            RTRIM(ISNULL(fle.FLE_BIP, ''))                          AS senha,
            CAST(fle.FLE_ORDEM AS INT)                              AS ordem,
            RTRIM(psv.psv_apel)                                     AS psv_apel,
            RTRIM(psv.psv_nome)                                     AS psv_nome,
            RTRIM(ISNULL(esp.esp_nome,''))                          AS especialidade,
            RTRIM(fle.FLE_STR_COD)                                  AS setor,
            CONVERT(VARCHAR(5),fle.FLE_DTHR_ATENDIMENTO,108)        AS chamado_em,
            RTRIM(ISNULL(fle.fle_pac_nome,
                   RTRIM(ISNULL(pac.pac_nome,''))))                 AS pac_nome,
            fle.FLE_PREFERENCIAL                                    AS preferencial,
            DATEDIFF(minute, fle.FLE_DTHR_CHEGADA,
                     fle.FLE_DTHR_ATENDIMENTO)                      AS espera_min
        FROM fle
        JOIN psv ON psv.psv_cod = fle.FLE_PSV_COD
        LEFT JOIN esp ON esp.esp_cod = psv.psv_esp_cod
        LEFT JOIN pac ON pac.pac_reg = fle.FLE_PAC_REG
        WHERE CAST(fle.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
          AND fle.FLE_DTHR_ATENDIMENTO IS NOT NULL
          AND fle.FLE_BIP IS NOT NULL
          AND LTRIM(RTRIM(fle.FLE_BIP)) <> ''
        ORDER BY fle.FLE_DTHR_ATENDIMENTO DESC
    """)
    return rows


@app.get("/api/painel-fila/status-senhas")
def painel_fila_status_senhas():
    """
    Status das filas de senha por prestador — lateral do painel TV.
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
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

@app.get("/api/painel-fila/senhas")
def painel_fila_senhas(limite: int = 8):
    """
    Painel TV — Senhas chamadas pela recepção (guichês).
    Guichê = USR_NOME do operador que chamou (FLE_USR_ATENDIMENTO ou FLE_USR_LOGIN).
    FLE_STATUS = 'E' (totem + chamado) ou 'X' (chamado direto).
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    rows = query(f"""
        SELECT TOP {limite}
            RTRIM(ISNULL(fle.FLE_BIP, ''))                              AS senha,
            CAST(fle.FLE_ORDEM AS INT)                                  AS ordem,
            RTRIM(psv.psv_apel)                                         AS psv_apel,
            RTRIM(psv.psv_nome)                                         AS psv_nome,
            RTRIM(ISNULL(esp.esp_nome,''))                              AS especialidade,
            RTRIM(fle.FLE_STR_COD)                                      AS setor,
            CONVERT(VARCHAR(5),fle.FLE_DTHR_ATENDIMENTO,108)            AS chamado_em,
            RTRIM(ISNULL(fle.fle_pac_nome,
                   RTRIM(ISNULL(pac.pac_nome,''))))                     AS pac_nome,
            fle.FLE_PREFERENCIAL                                        AS preferencial,
            DATEDIFF(minute,fle.FLE_DTHR_CHEGADA,
                     fle.FLE_DTHR_ATENDIMENTO)                          AS espera_min,
            -- Quem chamou: FLE_USR_ATENDIMENTO (totem) ou FLE_USR_LOGIN (direto)
            RTRIM(ISNULL(
                ISNULL(usr_a.USR_NOME, fle.FLE_USR_ATENDIMENTO),
                ISNULL(usr_l.USR_NOME, fle.FLE_USR_LOGIN)
            ))                                                          AS operador_login,
            RTRIM(ISNULL(fle.FLE_USR_ATENDIMENTO, fle.FLE_USR_LOGIN))  AS guiche
        FROM fle
        JOIN psv ON psv.psv_cod = fle.FLE_PSV_COD
        LEFT JOIN esp ON esp.esp_cod = psv.psv_esp_cod
        LEFT JOIN pac ON pac.pac_reg = fle.FLE_PAC_REG
        LEFT JOIN usr usr_a ON RTRIM(usr_a.USR_LOGIN) = RTRIM(fle.FLE_USR_ATENDIMENTO)
        LEFT JOIN usr usr_l ON RTRIM(usr_l.USR_LOGIN) = RTRIM(fle.FLE_USR_LOGIN)
        WHERE CAST(fle.FLE_DTHR_CHEGADA AS DATE) = '{hoje}'
          AND fle.FLE_DTHR_ATENDIMENTO IS NOT NULL
          AND fle.FLE_BIP IS NOT NULL
          AND LTRIM(RTRIM(fle.FLE_BIP)) <> ''
        ORDER BY fle.FLE_DTHR_ATENDIMENTO DESC
    """)
    return rows


@app.get("/api/painel-fila/status-senhas")
def painel_fila_status_senhas():
    """
    Status das filas de senha por prestador — lateral do painel TV.
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
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

@app.get("/api/debug/scheduler-status")
def debug_scheduler_status():
    try:
        from scheduler import _query_func, HORARIOS
        return {
            "query_func_ok": _query_func is not None,
            "horarios": [f"{h:02d}:{m:02d} ({t})" for h,m,t in HORARIOS],
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
# MÓDULO RECEPÇÃO — Métricas por recepcionista
# ══════════════════════════════════════════════════════════════════════════════

RECEPCOES = {
    "RDI": "Recepção Diagnóstico",
    "ROC": "Recepção Ocupacional",
    "RPS": "Recepção Pro Saúde",
    "RCN": "Recepção Consultórios",
    "RCI": "Recepção Censo Imagem",
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
                CAST(fle.FLE_DTHR_CHEGADA AS DATE)                         AS data_cheg
            FROM fle
            WHERE fle.FLE_DTHR_CHEGADA BETWEEN '{inicio}' AND '{fim} 23:59:59'
              AND fle.FLE_PAC_REG > 0
              AND ISNULL(fle.FLE_USR_LOGIN, fle.FLE_USR_ATENDIMENTO) IS NOT NULL
              {filtro_setor}
        ),
        esperas AS (
            SELECT
                c.login_recep,
                c.setor_cod,
                c.FLE_PAC_REG,
                DATEDIFF(minute, c.FLE_DTHR_CHEGADA,
                    (SELECT TOP 1 o.osm_dthr FROM osm o
                     WHERE o.osm_pac = c.FLE_PAC_REG
                       AND CAST(o.osm_dthr AS DATE) = c.data_cheg
                       AND o.osm_dthr >= c.FLE_DTHR_CHEGADA
                     ORDER BY o.osm_dthr ASC)) AS espera_min
            FROM chegadas c
        ),
        financeiro AS (
            SELECT
                c.login_recep,
                c.setor_cod,
                SUM({vliq}) AS producao
            FROM chegadas c
            JOIN osm o ON o.osm_pac = c.FLE_PAC_REG
                      AND CAST(o.osm_dthr AS DATE) = c.data_cheg
            JOIN smm ON smm.SMM_OSM = o.osm_num AND smm.SMM_OSM_SERIE = o.osm_serie
            GROUP BY c.login_recep, c.setor_cod
        )
        SELECT
            c.login_recep,
            RTRIM(ISNULL(u.USR_NOME, c.login_recep))   AS nome_recep,
            c.setor_cod,
            ISNULL(RTRIM(str.str_nome), c.setor_cod)   AS setor_nome,
            COUNT(DISTINCT c.FLE_PAC_REG)               AS total_pacientes,
            AVG(CAST(
                CASE WHEN e.espera_min BETWEEN 0 AND 120 THEN e.espera_min ELSE NULL END
            AS FLOAT))                                   AS espera_media_min,
            ISNULL(f.producao, 0)                        AS producao_financeira
        FROM chegadas c
        LEFT JOIN esperas    e ON e.login_recep = c.login_recep
                              AND e.setor_cod   = c.setor_cod
                              AND e.FLE_PAC_REG = c.FLE_PAC_REG
        LEFT JOIN financeiro f ON f.login_recep = c.login_recep
                              AND f.setor_cod   = c.setor_cod
        LEFT JOIN str ON RTRIM(str.str_cod) = c.setor_cod
        LEFT JOIN usr u ON RTRIM(u.USR_LOGIN) = c.login_recep
        GROUP BY c.login_recep, RTRIM(ISNULL(u.USR_NOME, c.login_recep)),
                 c.setor_cod, ISNULL(RTRIM(str.str_nome), c.setor_cod),
                 ISNULL(f.producao, 0)
        ORDER BY total_pacientes DESC
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


@app.get("/api/health")
def health():
    try:
        conn = get_conn()
        conn.close()
        return {"status": "ok", "db": "conectado", "ts": datetime.now().isoformat()}
    except Exception as e:
        return {"status": "erro", "detalhe": str(e)}
    
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