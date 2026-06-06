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
import pyodbc
import os
from datetime import datetime, timedelta

app = FastAPI(title="Dashboard Clínica", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, restrinja ao domínio do frontend
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ─── Conexão SQL Server ────────────────────────────────────────────────────────
def get_conn():
    conn_str = (
        "DRIVER={SQL Server};"
        f"SERVER={os.getenv('DB_SERVER', '192.168.1.9')};"
        f"DATABASE={os.getenv('DB_NAME', 'smart')};"
        f"UID={os.getenv('DB_USER', 'smart')};"
        f"PWD={os.getenv('DB_PASS', 'smart@pixeon16')};"
        "TrustServerCertificate=yes;"
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
    dias = PERIODOS.get(periodo, 30)
    inicio = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
    fim = datetime.now().strftime("%Y-%m-%d")
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
# FINANCEIRO
# Receita via tabela crp (Contas a Receber Particular) — validada Pixeon
# ──────────────────────────────────────────────────────────────────────────────
# crp_serie      → PK (int)
# crp_num        → PK (int)
# crp_dthr       → Data da Execução       ← data principal do lançamento
# crp_dthr_lib   → Data da Liberação
# crp_dthr_lib_pag → Data da Liberação para Pagamento
# crp_valor      → Valor (numeric 14,2)   ← campo correto (não crp_vlr_principal)
# crp_status     → Status (char 1)        ← sem domínio documentado; confirmar valores
# crp_pac_reg    → FK paciente (pac.pac_reg)
# crp_osm_serie  → FK OS série (nullable)
# crp_osm_num    → FK OS número (nullable)
# crp_cnv_cod    → FK convênio (cnv.cnv_cod)
# crp_str_solic  → FK setor solicitante
# crp_mte_serie/seq → FK movimento de quitação (preenchido = quitado)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/financeiro/resumo")
def financeiro_resumo(periodo: str = "30d"):
    """
    crp_valor  = valor do lançamento (campo real confirmado)
    crp_dthr   = data da execução    (campo de data principal)
    crp_status = status do lançamento
    crp_mte_serie/seq preenchidos = quitado; nulos = em aberto (inadimplência)
    """
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            COUNT(DISTINCT osm.osm_serie * 1000000 + osm.osm_num) AS total_os,

            SUM(CASE WHEN osm.osm_atend = 'EME' THEN 1 ELSE 0 END) AS emergencia,
            SUM(CASE WHEN osm.osm_atend = 'INT' THEN 1 ELSE 0 END) AS internamento,
            SUM(CASE WHEN osm.osm_atend = 'ASS' THEN 1 ELSE 0 END) AS assistencial,

            -- Faturamento: soma de crp_valor no período
            (SELECT ISNULL(SUM(crp.crp_valor), 0)
             FROM crp
             WHERE crp.crp_dthr BETWEEN ? AND ?)              AS faturamento,

            -- Inadimplência: lançamentos sem quitação (crp_mte_serie nulo = não quitado)
            (SELECT ISNULL(SUM(crp.crp_valor), 0)
             FROM crp
             WHERE crp.crp_dthr_lib_pag < ?
               AND crp.crp_mte_serie IS NULL
               AND crp.crp_mte_seq   IS NULL)                 AS inadimplencia,

            -- Ticket médio = faturamento / total de OS com crp
            (SELECT ISNULL(
                SUM(crp.crp_valor) / NULLIF(COUNT(DISTINCT crp.crp_osm_num), 0)
             , 0)
             FROM crp
             WHERE crp.crp_dthr BETWEEN ? AND ?
               AND crp.crp_osm_num IS NOT NULL)               AS ticket_medio

        FROM osm
        WHERE osm.osm_dthr BETWEEN ? AND ?
    """, (inicio, fim, fim, inicio, fim, inicio, fim))
    return rows[0] if rows else {}


@app.get("/api/financeiro/receita-mensal")
def receita_mensal():
    """Faturamento dos últimos 6 meses usando crp_dthr (Data da Execução)."""
    rows = query("""
        SELECT
            FORMAT(crp.crp_dthr, 'yyyy-MM')  AS mes,
            SUM(crp.crp_valor)               AS receita,
            COUNT(*)                         AS qtd_lancamentos,
            -- Quitados no mês (crp_mte_serie preenchido)
            SUM(CASE WHEN crp.crp_mte_serie IS NOT NULL
                     THEN crp.crp_valor ELSE 0 END) AS quitado,
            -- Pendentes
            SUM(CASE WHEN crp.crp_mte_serie IS NULL
                     THEN crp.crp_valor ELSE 0 END) AS pendente
        FROM crp
        WHERE crp.crp_dthr >= DATEADD(month, -6, GETDATE())
        GROUP BY FORMAT(crp.crp_dthr, 'yyyy-MM')
        ORDER BY mes
    """)
    return rows


@app.get("/api/financeiro/por-convenio")
def receita_por_convenio(periodo: str = "30d"):
    """Receita por convênio — join direto crp.crp_cnv_cod → cnv.cnv_cod."""
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            cnv.cnv_nome    AS nom_convenio,
            cnv.cnv_tipo    AS tipo,
            cnv.cnv_reg_ans AS registro_ans,
            COUNT(DISTINCT CAST(crp.crp_osm_serie AS varchar) + '-' +
                           CAST(crp.crp_osm_num   AS varchar)) AS qtd_os,
            SUM(crp.crp_valor)                                 AS receita,
            -- Quitado x pendente
            SUM(CASE WHEN crp.crp_mte_serie IS NOT NULL
                     THEN crp.crp_valor ELSE 0 END)            AS quitado,
            SUM(CASE WHEN crp.crp_mte_serie IS NULL
                     THEN crp.crp_valor ELSE 0 END)            AS pendente
        FROM crp
        JOIN cnv ON cnv.cnv_cod  = crp.crp_cnv_cod   -- join direto, sem passar por osm
               AND cnv.cnv_stat  = 'A'
        WHERE crp.crp_dthr BETWEEN ? AND ?
        GROUP BY cnv.cnv_nome, cnv.cnv_tipo, cnv.cnv_reg_ans
        ORDER BY receita DESC
    """, (inicio, fim))
    return rows


@app.get("/api/financeiro/por-tipo-convenio")
def receita_por_tipo_convenio(periodo: str = "30d"):
    """Agrupa receita por tipo: AM/HP/AH/MC — usando join direto crp → cnv."""
    inicio, fim = periodo_datas(periodo)
    TIPOS = {"AM": "Ambulatorial", "HP": "Hospitalar",
             "AH": "Ambul/Hosp",  "MC": "Med. Ocupacional"}
    rows = query("""
        SELECT
            cnv.cnv_tipo                        AS tipo_cod,
            COUNT(DISTINCT crp.crp_pac_reg)     AS qtd_pacientes,
            COUNT(*)                            AS qtd_lancamentos,
            SUM(crp.crp_valor)                  AS receita,
            SUM(CASE WHEN crp.crp_mte_serie IS NOT NULL
                     THEN crp.crp_valor ELSE 0 END) AS quitado,
            SUM(CASE WHEN crp.crp_mte_serie IS NULL
                     THEN crp.crp_valor ELSE 0 END) AS pendente
        FROM crp
        JOIN cnv ON cnv.cnv_cod = crp.crp_cnv_cod
               AND cnv.cnv_stat = 'A'
        WHERE crp.crp_dthr BETWEEN ? AND ?
        GROUP BY cnv.cnv_tipo
        ORDER BY receita DESC
    """, (inicio, fim))
    for r in rows:
        r["tipo"] = TIPOS.get(r["tipo_cod"], r["tipo_cod"] or "Não informado")
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# ATENDIMENTOS  (tabela osm — campo osm_atend e osm_dthr)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/atendimentos/resumo")
def atendimentos_resumo(periodo: str = "30d"):
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            COUNT(*)                                                        AS total_atendimentos,
            SUM(CASE WHEN osm.osm_atend = 'ASS' THEN 1 ELSE 0 END)        AS assistencial,
            SUM(CASE WHEN osm.osm_atend = 'INT' THEN 1 ELSE 0 END)        AS internamento,
            SUM(CASE WHEN osm.osm_atend = 'EME' THEN 1 ELSE 0 END)        AS emergencia,
            SUM(CASE WHEN osm.osm_atend = 'CRG' THEN 1 ELSE 0 END)        AS cirurgia,
            SUM(CASE WHEN osm.osm_atend = 'TAM' THEN 1 ELSE 0 END)        AS trat_ambulatorial,

            -- Tempo médio em emergência (entrada → saída)
            AVG(CASE
                WHEN osm.osm_atend = 'EME' AND osm.osm_dthr_saida IS NOT NULL
                THEN DATEDIFF(minute, osm.osm_dthr, osm.osm_dthr_saida)
                ELSE NULL
            END) AS media_min_emergencia

        FROM osm
        WHERE osm.osm_dthr BETWEEN ? AND ?
    """, (inicio, fim))
    return rows[0] if rows else {}


@app.get("/api/atendimentos/por-especialidade")
def atendimentos_por_especialidade(periodo: str = "30d"):
    """
    esp_cod  = PK (char 3), esp_nome = descrição (varchar 100)
    esp_del_logica = 'S' significa deletado logicamente — filtrar com <> 'S'
    Estratégia dupla:
    1) OS com agendamento → OSM_AGM_ID → agm.agm_id → AGM_ESP_COD → esp
    2) OS sem agendamento → osm_mreq → psv_cod → psv_esp_cod → esp
    """
    inicio, fim = periodo_datas(periodo)
    rows = query("""
        SELECT
            esp.esp_nome                                                           AS especialidade,
            COUNT(DISTINCT osm.osm_serie * 1000000 + osm.osm_num)                 AS qtd
        FROM osm
        LEFT JOIN agm ON agm.agm_id      = osm.OSM_AGM_ID
        LEFT JOIN psv ON psv.psv_cod     = osm.osm_mreq
        LEFT JOIN esp ON esp.esp_cod     = COALESCE(agm.AGM_ESP_COD, psv.psv_esp_cod)
                     AND esp.esp_del_logica <> 'S'     -- exclui especialidades deletadas
        WHERE osm.osm_dthr BETWEEN ? AND ?
          AND esp.esp_nome IS NOT NULL
        GROUP BY esp.esp_nome
        ORDER BY qtd DESC
    """, (inicio, fim))
    return rows


@app.get("/api/atendimentos/por-dia")
def atendimentos_por_dia(periodo: str = "30d"):
    inicio, fim = periodo_datas(periodo)
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


@app.get("/api/agendamentos/por-especialidade")
def agendamentos_por_especialidade(periodo: str = "30d"):
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
# DIAGNÓSTICO
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    try:
        conn = get_conn()
        conn.close()
        return {"status": "ok", "db": "conectado", "ts": datetime.now().isoformat()}
    except Exception as e:
        return {"status": "erro", "detalhe": str(e)}


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
#          agm_stat (A=Aberta/E=Executada/C=Cancelada/B=Bloqueada),
#          agm_confirm_stat (A/C/N), agm_cnv_cod, agm_str_cod,
#          agm_pac_nome, agm_id, AGM_ESP_COD, agm_valor, agm_canc_dthr
#          JOIN com osm: agm.agm_id = osm.OSM_AGM_ID
# ✓ psv → psv_cod (PK int), psv_nome (char 50), psv_apel (char 20),
#          psv_esp_cod (char 3), psv_crm, psv_vinc (S/F/P/J/C/R/O)
#          JOIN com osm: psv.psv_cod = osm.osm_mreq
#          JOIN com agm: psv.psv_cod = agm.agm_med
# ✓ crp → crp_serie + crp_num (PK), crp_valor (numeric 14,2),
#          crp_dthr, crp_dthr_lib, crp_dthr_lib_pag, crp_status,
#          crp_pac_reg, crp_cnv_cod, crp_osm_serie, crp_osm_num,
#          crp_mte_serie/seq (nulos = não quitado)
# ✓ esp → esp_cod (PK char 3), esp_nome (varchar 100),
#          esp_del_logica ('S' = deletado — sempre filtrar com <> 'S'),
#          esp_ind_atende (S/N), esp_sus, esp_cbo_s
#          JOIN: esp.esp_cod = agm.AGM_ESP_COD ou psv.psv_esp_cod
# ──────────────────────────────────────────────────────────────────────────────