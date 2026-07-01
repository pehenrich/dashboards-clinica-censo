# -*- coding: utf-8 -*-
"""
whatsapp_sender.py
Envia resumo financeiro diario via WhatsApp.
Suporta: WPPConnect (local, sem Docker), Z-API, Evolution API
"""

import os
import requests
import time
from datetime import datetime, timedelta

WPP_PROVIDER       = os.getenv("WPP_PROVIDER",       "wppconnect")
WPPCONNECT_URL     = os.getenv("WPPCONNECT_URL",      "http://localhost:21465")
WPPCONNECT_SESSION = os.getenv("WPPCONNECT_SESSION",  "myinstance")
WPPCONNECT_TOKEN   = os.getenv("WPPCONNECT_TOKEN",    "")
ZAPI_INSTANCE      = os.getenv("ZAPI_INSTANCE",       "")
ZAPI_TOKEN         = os.getenv("ZAPI_TOKEN",          "")
ZAPI_CLIENT_TOKEN  = os.getenv("ZAPI_CLIENT_TOKEN",   "")
EVOLUTION_URL      = os.getenv("EVOLUTION_URL",       "http://localhost:8080")
EVOLUTION_KEY      = os.getenv("EVOLUTION_KEY",       "")
EVOLUTION_INST     = os.getenv("EVOLUTION_INST",      "censo")
DEST_NUMBERS       = os.getenv("WHATSAPP_DEST",       "5594999999999").split(",")


# ── Helpers de formatação ────────────────────────────────────────────────────

def brl(v):
    if v is None:
        return "R$ 0,00"
    return "R$ {:,.2f}".format(v).replace(",", "X").replace(".", ",").replace("X", ".")


def num(v):
    if v is None:
        return "0"
    return "{:,}".format(int(v)).replace(",", ".")


# ── Helper de metas ──────────────────────────────────────────────────────────

def _calcular_metas(producao_mes: float, meta_mensal_fixa: float = 1200000.0) -> dict:
    """
    Calcula META_MENSAL, meta_diaria, meta_dia_pct, meta_mes_pct e falta_meta
    com base na produção acumulada do mês e na meta mensal fixa.

    meta_dia_pct → média diária real / meta diária  (100 = no alvo)
    meta_mes_pct → acumulado real / meta acumulada até hoje  (100 = no alvo)
    falta_meta   → quanto ainda falta para bater a meta mensal (>= 0)
    """
    import datetime as _dt
    from calendar import monthrange as _mr

    hoje       = _dt.date.today()
    ano, mes   = hoje.year, hoje.month
    ultimo_dia = _mr(ano, mes)[1]

    # Feriados Parauapebas-PA (espelho exato do main.py)
    def _feriados(a: int):
        f = set()
        for m_, d_ in [(1,1),(4,21),(5,1),(9,7),(10,12),(11,2),(11,15),(11,20),(12,25)]:
            f.add(_dt.date(a, m_, d_))
        # Páscoa (algoritmo de Gauss)
        a_ = a % 19; b_ = a // 100; c_ = a % 100
        d__ = b_ // 4; e_ = b_ % 4; f_ = (b_+8)//25; g_ = (b_-f_+1)//3
        h_ = (19*a_+b_-d__-g_+15)%30; i_ = c_//4; k_ = c_%4
        l_ = (32+2*e_+2*i_-h_-k_)%7; m__ = (a_+11*h_+22*l_)//451
        month_ = (h_+l_-7*m__+114)//31; day_ = ((h_+l_-7*m__+114)%31)+1
        pascoa = _dt.date(a, month_, day_)
        f.add(pascoa - _dt.timedelta(days=2))   # Sexta-feira Santa
        f.add(pascoa + _dt.timedelta(days=60))  # Corpus Christi
        f.add(_dt.date(a, 8, 15))   # Adesão do Pará
        f.add(_dt.date(a, 5, 27))   # Aniversário de Parauapebas
        return f

    feriados = _feriados(ano)
    is_util  = lambda d: (
        _dt.date(ano, mes, d).weekday() < 6
        and _dt.date(ano, mes, d) not in feriados
    )

    dias_uteis_mes      = sum(1 for d in range(1, ultimo_dia + 1)  if is_util(d))
    dias_uteis_passados = sum(1 for d in range(1, hoje.day + 1)    if is_util(d))

    META_MENSAL    = meta_mensal_fixa
    meta_diaria    = round(META_MENSAL / dias_uteis_mes, 2) if dias_uteis_mes > 0 else 0.0
    meta_acum      = meta_diaria * max(dias_uteis_passados, 1)   # meta acumulada até hoje
    media_dia_real = producao_mes / max(dias_uteis_passados, 1)

    # >100 = acima da meta, <100 = abaixo
    meta_dia_pct = (media_dia_real / meta_diaria * 100) if meta_diaria > 0 else 0.0
    meta_mes_pct = (producao_mes   / meta_acum   * 100) if meta_acum   > 0 else 0.0
    falta_meta   = max(0.0, META_MENSAL - producao_mes)

    return {
        "META_MENSAL":  META_MENSAL,
        "meta_diaria":  meta_diaria,
        "meta_dia_pct": meta_dia_pct,
        "meta_mes_pct": meta_mes_pct,
        "falta_meta":   falta_meta,
    }


# ── Busca de dados ───────────────────────────────────────────────────────────

def buscar_dados_manha(query_func):
    hoje = datetime.now().strftime("%Y-%m-%d")

    agd = query_func(
        "SELECT "
        "SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B') THEN 1 ELSE 0 END) AS marcacoes, "
        "SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat = 'C' THEN 1 ELSE 0 END) AS cancelados, "
        "COUNT(DISTINCT agm.agm_med) AS medicos, "
        "ISNULL((SELECT COUNT(*) FROM EX_HORARIOS WHERE HOR_DATA = '" + hoje + "'), 0) AS vagas_disp "
        "FROM agm WHERE CAST(agm.agm_hini AS DATE) = '" + hoje + "'"
    )

    # Médicos divididos por turno (manhã = antes das 12h, tarde = 12h+)
    medicos_raw = query_func(
        "SELECT TOP 20 RTRIM(psv.psv_apel) AS medico, "
        "RTRIM(ISNULL(esp.esp_nome, '')) AS especialidade, "
        "RTRIM(ISNULL(psv.psv_esp_cod, '')) AS esp_cod, "
        "SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B') THEN 1 ELSE 0 END) AS marcacoes, "
        "MIN(agm.agm_hini) AS inicio, MAX(agm.agm_hini) AS fim "
        "FROM agm "
        "JOIN psv ON psv.psv_cod = agm.agm_med "
        "LEFT JOIN esp ON esp.esp_cod = psv.psv_esp_cod "
        "WHERE CAST(agm.agm_hini AS DATE) = '" + hoje + "' AND agm.agm_pac > 0 "
        "GROUP BY RTRIM(psv.psv_apel), RTRIM(ISNULL(esp.esp_nome,'')), RTRIM(ISNULL(psv.psv_esp_cod,'')) "
        "ORDER BY MIN(agm.agm_hini)"
    )
    for r in medicos_raw:
        for k, v in r.items():
            if hasattr(v, "strftime"):
                r[k] = v.strftime("%H:%M")

    # Códigos de especialidade multiprofissional (Pixeon)
    _MULT_CODES = {'PSC','NUT','FON','FIS','ENF','TER','FAR','ASS','SOC','PSQ','NEU','FIO'}

    def _is_mult(m):
        return m.get('esp_cod', '').strip().upper() in _MULT_CODES

    medicos_manha = [m for m in medicos_raw if m.get('inicio','') < '12:00' and not _is_mult(m)]
    medicos_tarde = [m for m in medicos_raw if m.get('inicio','') >= '12:00' and not _is_mult(m)]
    mult_manha    = [m for m in medicos_raw if m.get('inicio','') < '12:00' and _is_mult(m)]
    mult_tarde    = [m for m in medicos_raw if m.get('inicio','') >= '12:00' and _is_mult(m)]
    medicos = medicos_raw  # compatibilidade

    vagas_med = query_func(
        "SELECT TOP 10 RTRIM(psv.psv_apel) AS medico, COUNT(*) AS vagas "
        "FROM EX_HORARIOS eh LEFT JOIN psv ON psv.psv_cod = eh.HOR_MED "
        "WHERE eh.HOR_DATA = '" + hoje + "' "
        "GROUP BY RTRIM(psv.psv_apel) ORDER BY vagas DESC"
    )

    ticket = query_func(
        "SELECT SUM(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) "
        "- ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) "
        "/ NULLIF(COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num),0) AS ticket_medio "
        "FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num "
        "WHERE osm.osm_dthr BETWEEN DATEADD(day,-30,'" + hoje + "') AND DATEADD(day,-1,'" + hoje + "') "
        "AND smm.SMM_SFAT IN ('A','F','P')"
    )

    # Produção acumulada no mês
    mes_ini = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    prod_mes = query_func(
        "SELECT SUM(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) "
        "- ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) AS producao_mes, "
        "COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS guias_mes "
        "FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num "
        "WHERE osm.osm_dthr BETWEEN '" + mes_ini + "' AND '" + hoje + " 23:59:59' "
        "AND smm.SMM_SFAT IN ('A','F','P')"
    )
    producao_mes  = (prod_mes[0].get("producao_mes") or 0) if prod_mes else 0
    guias_mes     = (prod_mes[0].get("guias_mes")    or 0) if prod_mes else 0

    # Projeção: média diária x dias úteis restantes no mês
    from calendar import monthrange
    hoje_dt   = datetime.now()
    dias_mes  = monthrange(hoje_dt.year, hoje_dt.month)[1]
    dia_atual = hoje_dt.day
    dias_uteis_passados = sum(
        1 for d in range(1, dia_atual + 1)
        if datetime(hoje_dt.year, hoje_dt.month, d).weekday() < 6
    )
    dias_uteis_restantes = sum(
        1 for d in range(dia_atual + 1, dias_mes + 1)
        if datetime(hoje_dt.year, hoje_dt.month, d).weekday() < 6
    )
    media_diaria  = producao_mes / max(dias_uteis_passados, 1)
    projecao_mes  = producao_mes + (media_diaria * dias_uteis_restantes)

    # Produção mesmo dia ano anterior
    hoje_ano_ant = (datetime.now().replace(year=datetime.now().year-1)).strftime("%Y-%m-%d")
    prod_ano_ant = query_func(
        "SELECT SUM(smm.SMM_VLR-ISNULL(smm.SMM_VLR_DESCONTO,0)-ISNULL(smm.SMM_VLR_COPARTIC,0)+ISNULL(smm.SMM_AJUSTE_VLR,0)) AS producao, "
        "COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS guias, "
        "COUNT(DISTINCT osm.osm_pac) AS pacientes "
        "FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num "
        "WHERE CAST(osm.osm_dthr AS DATE)='" + hoje_ano_ant + "' AND smm.SMM_SFAT IN ('A','F','P')"
    )

    # ── Calcula metas (corrige Pylance: variáveis declaradas aqui) ───────────
    _metas       = _calcular_metas(float(producao_mes))
    META_MENSAL  = _metas["META_MENSAL"]
    meta_diaria  = _metas["meta_diaria"]
    meta_dia_pct = _metas["meta_dia_pct"]
    meta_mes_pct = _metas["meta_mes_pct"]
    falta_meta   = _metas["falta_meta"]

    return {
        "hoje": hoje,
        "agd": agd[0] if agd else {},
        "medicos": medicos,
        "medicos_manha": medicos_manha,
        "medicos_tarde": medicos_tarde,
        "mult_manha":    mult_manha,
        "mult_tarde":    mult_tarde,
        "vagas_med": vagas_med,
        "ticket_medio":         (ticket[0].get("ticket_medio") or 0) if ticket else 0,
        "producao_mes":         producao_mes,
        "guias_mes":            guias_mes,
        "media_diaria":         media_diaria,
        "projecao_mes":         projecao_mes,
        "dias_uteis_restantes": dias_uteis_restantes,
        "prod_ano_ant":         (prod_ano_ant[0].get("producao") or 0) if prod_ano_ant else 0,
        "guias_ano_ant":        (prod_ano_ant[0].get("guias")    or 0) if prod_ano_ant else 0,
        "hoje_ano_ant":         hoje_ano_ant,
        "meta_mensal":          META_MENSAL,
        "meta_diaria":          meta_diaria,
        "meta_dia_pct":         meta_dia_pct,
        "meta_mes_pct":         meta_mes_pct,
        "falta_meta":           falta_meta,
    }


def buscar_dados_fechamento(query_func):
    hoje = datetime.now().strftime("%Y-%m-%d")

    fat = query_func(
        "SELECT "
        "COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS total_os, "
        "COUNT(DISTINCT osm.osm_pac) AS pacientes, "
        "SUM(smm.SMM_VLR-ISNULL(smm.SMM_VLR_DESCONTO,0)-ISNULL(smm.SMM_VLR_COPARTIC,0)+ISNULL(smm.SMM_AJUSTE_VLR,0)) AS producao, "
        "COUNT(DISTINCT CASE WHEN osm.osm_atend IN ('ASS','EME','CRG','TAM') THEN osm.osm_serie*1000000+osm.osm_num END) AS assistencial, "
        "COUNT(DISTINCT CASE WHEN osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC') THEN osm.osm_serie*1000000+osm.osm_num END) AS ocupacional, "
        "SUM(CASE WHEN osm.osm_atend IN ('ASS','EME','CRG','TAM') THEN smm.SMM_VLR-ISNULL(smm.SMM_VLR_DESCONTO,0)-ISNULL(smm.SMM_VLR_COPARTIC,0)+ISNULL(smm.SMM_AJUSTE_VLR,0) ELSE 0 END) AS prod_assistencial, "
        "SUM(CASE WHEN osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC') THEN smm.SMM_VLR-ISNULL(smm.SMM_VLR_DESCONTO,0)-ISNULL(smm.SMM_VLR_COPARTIC,0)+ISNULL(smm.SMM_AJUSTE_VLR,0) ELSE 0 END) AS prod_ocupacional, "
        "SUM(CASE WHEN RTRIM(osm.osm_cnv)='PAR' THEN smm.SMM_VLR-ISNULL(smm.SMM_VLR_DESCONTO,0)-ISNULL(smm.SMM_VLR_COPARTIC,0)+ISNULL(smm.SMM_AJUSTE_VLR,0) ELSE 0 END) AS particular "
        "FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num "
        "WHERE CAST(osm.osm_dthr AS DATE)='" + hoje + "' AND smm.SMM_SFAT IN ('A','F','P')"
    )

    # Convênios assistencial (consultas/exames)
    convenios = query_func(
        "SELECT TOP 5 RTRIM(cnv.cnv_nome) AS nome, "
        "COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS guias, "
        "COUNT(DISTINCT osm.osm_pac) AS pacientes, "
        "SUM(smm.SMM_VLR-ISNULL(smm.SMM_VLR_DESCONTO,0)-ISNULL(smm.SMM_VLR_COPARTIC,0)+ISNULL(smm.SMM_AJUSTE_VLR,0)) AS producao "
        "FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num "
        "JOIN cnv ON cnv.cnv_cod=osm.osm_cnv "
        "WHERE CAST(osm.osm_dthr AS DATE)='" + hoje + "' AND smm.SMM_SFAT IN ('A','F','P') "
        "AND osm.osm_atend IN ('ASS','EME','CRG','TAM','LAB','RAD','USG') "
        "GROUP BY RTRIM(cnv.cnv_nome) ORDER BY producao DESC"
    )

    # Empresas ocupacional
    empresas = query_func(
        "SELECT TOP 5 RTRIM(cnv.cnv_nome) AS nome, "
        "COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS guias, "
        "COUNT(DISTINCT osm.osm_pac) AS pacientes, "
        "SUM(smm.SMM_VLR-ISNULL(smm.SMM_VLR_DESCONTO,0)-ISNULL(smm.SMM_VLR_COPARTIC,0)+ISNULL(smm.SMM_AJUSTE_VLR,0)) AS producao "
        "FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num "
        "JOIN cnv ON cnv.cnv_cod=osm.osm_cnv "
        "WHERE CAST(osm.osm_dthr AS DATE)='" + hoje + "' AND smm.SMM_SFAT IN ('A','F','P') "
        "AND osm.osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC') "
        "GROUP BY RTRIM(cnv.cnv_nome) ORDER BY producao DESC"
    )

    medicos = query_func(
        "SELECT TOP 10 RTRIM(psv.psv_apel) AS medico, "
        "RTRIM(ISNULL(esp.esp_nome, '')) AS especialidade, "
        "RTRIM(ISNULL(psv.psv_esp_cod, '')) AS esp_cod, "
        "COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS guias, "
        "COUNT(DISTINCT osm.osm_pac) AS pacientes, "
        "SUM(smm.SMM_VLR-ISNULL(smm.SMM_VLR_DESCONTO,0)-ISNULL(smm.SMM_VLR_COPARTIC,0)+ISNULL(smm.SMM_AJUSTE_VLR,0)) AS producao "
        "FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num "
        "JOIN psv ON psv.psv_cod=osm.osm_mreq "
        "LEFT JOIN esp ON esp.esp_cod=psv.psv_esp_cod "
        "WHERE CAST(osm.osm_dthr AS DATE)='" + hoje + "' AND smm.SMM_SFAT IN ('A','F','P') "
        "GROUP BY RTRIM(psv.psv_apel), RTRIM(ISNULL(esp.esp_nome,'')), RTRIM(ISNULL(psv.psv_esp_cod,'')) "
        "ORDER BY producao DESC"
    )

    agd = query_func(
        "SELECT "
        "SUM(CASE WHEN agm.agm_pac>0 AND agm.agm_stat NOT IN ('C','B') THEN 1 ELSE 0 END) AS marcacoes, "
        "SUM(CASE WHEN agm.agm_pac>0 AND agm.agm_stat='C' THEN 1 ELSE 0 END) AS cancelados, "
        "SUM(CASE WHEN agm.agm_pac>0 AND agm.agm_stat NOT IN ('C','B') "
        "AND (agm.agm_stat='E' OR agm.AGM_OSM_SERIE IS NOT NULL OR om.osm_pac IS NOT NULL) THEN 1 ELSE 0 END) AS compareceram, "
        "SUM(CASE WHEN agm.agm_pac>0 AND agm.agm_stat NOT IN ('C','B','E') "
        "AND agm.AGM_OSM_SERIE IS NULL AND om.osm_pac IS NULL THEN 1 ELSE 0 END) AS faltantes "
        "FROM agm "
        "LEFT JOIN (SELECT DISTINCT osm_pac,osm_dthr,CAST(osm_dthr AS DATE) AS osm_data "
        "FROM osm WHERE CAST(osm_dthr AS DATE)='" + hoje + "') om "
        "ON om.osm_pac=agm.agm_pac AND om.osm_data=CAST(agm.agm_hini AS DATE) "
        "AND DATEDIFF(minute,agm.agm_hini,om.osm_dthr) BETWEEN -30 AND 180 "
        "WHERE CAST(agm.agm_hini AS DATE)='" + hoje + "'"
    )

    abs_med = query_func(
        "SELECT TOP 5 RTRIM(psv.psv_apel) AS medico, "
        "SUM(CASE WHEN agm.agm_pac>0 AND agm.agm_stat NOT IN ('C','B') THEN 1 ELSE 0 END) AS marcacoes, "
        "SUM(CASE WHEN agm.agm_pac>0 AND agm.agm_stat NOT IN ('C','B','E') "
        "AND agm.AGM_OSM_SERIE IS NULL AND om.osm_pac IS NULL THEN 1 ELSE 0 END) AS faltantes "
        "FROM agm JOIN psv ON psv.psv_cod=agm.agm_med "
        "LEFT JOIN (SELECT DISTINCT osm_pac,osm_dthr,CAST(osm_dthr AS DATE) AS osm_data "
        "FROM osm WHERE CAST(osm_dthr AS DATE)='" + hoje + "') om "
        "ON om.osm_pac=agm.agm_pac AND om.osm_data=CAST(agm.agm_hini AS DATE) "
        "AND DATEDIFF(minute,agm.agm_hini,om.osm_dthr) BETWEEN -30 AND 180 "
        "WHERE CAST(agm.agm_hini AS DATE)='" + hoje + "' AND agm.agm_pac>0 "
        "GROUP BY RTRIM(psv.psv_apel) "
        "HAVING SUM(CASE WHEN agm.agm_pac>0 AND agm.agm_stat NOT IN ('C','B','E') "
        "AND agm.AGM_OSM_SERIE IS NULL AND om.osm_pac IS NULL THEN 1 ELSE 0 END)>0 "
        "ORDER BY faltantes DESC"
    )

    # Produção acumulada no mês
    mes_ini = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    prod_mes = query_func(
        "SELECT SUM(smm.SMM_VLR-ISNULL(smm.SMM_VLR_DESCONTO,0)-ISNULL(smm.SMM_VLR_COPARTIC,0)+ISNULL(smm.SMM_AJUSTE_VLR,0)) AS producao_mes, "
        "COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS guias_mes "
        "FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num "
        "WHERE osm.osm_dthr BETWEEN '" + mes_ini + "' AND '" + hoje + " 23:59:59' "
        "AND smm.SMM_SFAT IN ('A','F','P')"
    )
    producao_mes = (prod_mes[0].get("producao_mes") or 0) if prod_mes else 0
    guias_mes    = (prod_mes[0].get("guias_mes")    or 0) if prod_mes else 0

    from calendar import monthrange
    hoje_dt  = datetime.now()
    dias_mes = monthrange(hoje_dt.year, hoje_dt.month)[1]
    dia_atual = hoje_dt.day
    dias_uteis_passados  = sum(1 for d in range(1, dia_atual+1)  if datetime(hoje_dt.year, hoje_dt.month, d).weekday() < 6)
    dias_uteis_restantes = sum(1 for d in range(dia_atual+1, dias_mes+1) if datetime(hoje_dt.year, hoje_dt.month, d).weekday() < 6)
    media_diaria = producao_mes / max(dias_uteis_passados, 1)
    projecao_mes = producao_mes + (media_diaria * dias_uteis_restantes)

    # Produção mesmo dia ano anterior
    hoje_ano_ant = datetime.now().replace(year=datetime.now().year-1).strftime("%Y-%m-%d")
    prod_ano_ant = query_func(
        "SELECT SUM(smm.SMM_VLR-ISNULL(smm.SMM_VLR_DESCONTO,0)-ISNULL(smm.SMM_VLR_COPARTIC,0)+ISNULL(smm.SMM_AJUSTE_VLR,0)) AS producao, "
        "COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS guias "
        "FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num "
        "WHERE CAST(osm.osm_dthr AS DATE)='" + hoje_ano_ant + "' AND smm.SMM_SFAT IN ('A','F','P')"
    )

    # ── Calcula metas (corrige Pylance: variáveis declaradas aqui) ───────────
    _metas       = _calcular_metas(float(producao_mes))
    META_MENSAL  = _metas["META_MENSAL"]
    meta_diaria  = _metas["meta_diaria"]
    meta_dia_pct = _metas["meta_dia_pct"]
    meta_mes_pct = _metas["meta_mes_pct"]
    falta_meta   = _metas["falta_meta"]

    return {
        "hoje": hoje,
        "fat": fat[0] if fat else {},
        "convenios": convenios,
        "empresas": empresas,
        "medicos": medicos,
        "agd": agd[0] if agd else {},
        "abs_med": abs_med,
        "producao_mes":         producao_mes,
        "guias_mes":            guias_mes,
        "media_diaria":         media_diaria,
        "projecao_mes":         projecao_mes,
        "dias_uteis_restantes": dias_uteis_restantes,
        "prod_ano_ant":         (prod_ano_ant[0].get("producao") or 0) if prod_ano_ant else 0,
        "guias_ano_ant":        (prod_ano_ant[0].get("guias")    or 0) if prod_ano_ant else 0,
        "hoje_ano_ant":         hoje_ano_ant,
        "meta_mensal":          META_MENSAL,
        "meta_diaria":          meta_diaria,
        "meta_dia_pct":         meta_dia_pct,
        "meta_mes_pct":         meta_mes_pct,
        "falta_meta":           falta_meta,
    }


def buscar_dados_amanha(query_func):
    amanha = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    dia_semana = (datetime.now() + timedelta(days=1)).strftime("%A")
    dias_pt = {
        "Monday": "Segunda-feira", "Tuesday": "Terca-feira",
        "Wednesday": "Quarta-feira", "Thursday": "Quinta-feira",
        "Friday": "Sexta-feira", "Saturday": "Sabado", "Sunday": "Domingo"
    }

    agd = query_func(
        "SELECT "
        "SUM(CASE WHEN agm.agm_pac>0 AND agm.agm_stat NOT IN ('C','B') THEN 1 ELSE 0 END) AS marcacoes, "
        "SUM(CASE WHEN agm.agm_pac>0 AND agm.agm_stat='C' THEN 1 ELSE 0 END) AS cancelados, "
        "COUNT(DISTINCT agm.agm_med) AS medicos, "
        "ISNULL((SELECT COUNT(*) FROM EX_HORARIOS WHERE HOR_DATA='" + amanha + "'),0) AS vagas_disp "
        "FROM agm WHERE CAST(agm.agm_hini AS DATE)='" + amanha + "'"
    )

    medicos = query_func(
        "SELECT TOP 15 RTRIM(psv.psv_apel) AS medico, "
        "SUM(CASE WHEN agm.agm_pac>0 AND agm.agm_stat NOT IN ('C','B') THEN 1 ELSE 0 END) AS marcacoes, "
        "MIN(agm.agm_hini) AS inicio, MAX(agm.agm_hini) AS fim "
        "FROM agm JOIN psv ON psv.psv_cod=agm.agm_med "
        "WHERE CAST(agm.agm_hini AS DATE)='" + amanha + "' AND agm.agm_pac>0 "
        "GROUP BY RTRIM(psv.psv_apel) ORDER BY MIN(agm.agm_hini)"
    )
    for r in medicos:
        for k, v in r.items():
            if hasattr(v, "strftime"):
                r[k] = v.strftime("%H:%M")

    vagas_med = query_func(
        "SELECT TOP 10 RTRIM(psv.psv_apel) AS medico, COUNT(*) AS vagas "
        "FROM EX_HORARIOS eh LEFT JOIN psv ON psv.psv_cod=eh.HOR_MED "
        "WHERE eh.HOR_DATA='" + amanha + "' "
        "GROUP BY RTRIM(psv.psv_apel) ORDER BY vagas DESC"
    )

    ticket = query_func(
        "SELECT SUM(smm.SMM_VLR-ISNULL(smm.SMM_VLR_DESCONTO,0)"
        "-ISNULL(smm.SMM_VLR_COPARTIC,0)+ISNULL(smm.SMM_AJUSTE_VLR,0))"
        "/NULLIF(COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num),0) AS ticket_medio "
        "FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num "
        "WHERE osm.osm_dthr BETWEEN DATEADD(day,-30,'" + amanha + "') AND DATEADD(day,-1,'" + amanha + "') "
        "AND smm.SMM_SFAT IN ('A','F','P')"
    )

    return {
        "amanha": amanha,
        "amanha_fmt": (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y"),
        "dia_semana": dias_pt.get(dia_semana, dia_semana),
        "agd": agd[0] if agd else {},
        "medicos": medicos,
        "vagas_med": vagas_med,
        "ticket_medio": (ticket[0].get("ticket_medio") or 0) if ticket else 0,
    }


def buscar_dados_resumo(query_func):
    return buscar_dados_fechamento(query_func)


# ── Montadores de mensagem ───────────────────────────────────────────────────

def montar_manha(dados):
    hoje_fmt   = datetime.now().strftime("%d/%m/%Y")
    agd        = dados["agd"]
    medicos    = dados["medicos"]
    vagas_med  = dados["vagas_med"]
    ticket     = dados.get("ticket_medio") or 0
    marcacoes  = agd.get("marcacoes") or 0
    cancelados = agd.get("cancelados") or 0
    vagas_disp = agd.get("vagas_disp") or 0
    previsao   = marcacoes * ticket
    n          = "\n"

    msg  = "\U0001f305 *BOM DIA \u2014 AGENDA DE HOJE*" + n
    msg += "\U0001f4c5 " + hoje_fmt + n
    msg += "\u2501" * 28 + n + n

    msg += "\U0001f4cb *RESUMO DA AGENDA*" + n
    msg += "  \U0001f468\u200d\u2695\ufe0f Profissionais:  *" + str(agd.get("medicos") or len(medicos)) + "*" + n
    msg += "  \U0001f9d1\u200d\U0001f91d\u200d\U0001f9d1 Pac. marcados:  *" + num(marcacoes) + "*" + n
    msg += "  \U0001f7e2 Vagas abertas:  *" + num(vagas_disp) + "*" + n
    if cancelados > 0:
        msg += "  \U0001f534 Cancelamentos:  *" + num(cancelados) + "*" + n

    if previsao > 0:
        msg += n + "\U0001f4b0 *PREVISAO DE PRODUCAO*" + n
        msg += "  Se todos comparecerem:" + n
        msg += "  \u27a4 *" + brl(previsao) + "*" + n
        msg += "  _(ticket medio 30d: " + brl(ticket) + ")_" + n

    medicos_manha = dados.get("medicos_manha", [])
    medicos_tarde = dados.get("medicos_tarde", [])
    mult_manha    = dados.get("mult_manha", [])
    mult_tarde    = dados.get("mult_tarde", [])

    # ── Equipe Médica ────────────────────────────────────────────────────────
    if medicos_manha or medicos_tarde:
        msg += n + "\u2501" * 28 + n
        msg += "\U0001fa7a *EQUIPE MEDICA*" + n
        if medicos_manha:
            msg += n + "  \U0001f324\ufe0f _Manha_" + n
            for m in medicos_manha:
                ini  = m.get("inicio", "")
                fim  = m.get("fim", "")
                marc = m.get("marcacoes") or 0
                msg += "  \u2022 " + str(m["medico"]) + n
                msg += "    " + num(marc) + " pac.  |  " + ini + " \u2013 " + fim + n
        if medicos_tarde:
            msg += n + "  \U0001f306 _Tarde_" + n
            for m in medicos_tarde:
                ini  = m.get("inicio", "")
                fim  = m.get("fim", "")
                marc = m.get("marcacoes") or 0
                msg += "  \u2022 " + str(m["medico"]) + n
                msg += "    " + num(marc) + " pac.  |  " + ini + " \u2013 " + fim + n
    elif medicos:
        medicos_sem_mult = [m for m in medicos if m not in mult_manha and m not in mult_tarde]
        if medicos_sem_mult:
            msg += n + "\u2501" * 28 + n
            msg += "\U0001fa7a *EQUIPE MEDICA*" + n
            for m in medicos_sem_mult:
                ini  = m.get("inicio", "")
                fim  = m.get("fim", "")
                marc = m.get("marcacoes") or 0
                msg += "  \u2022 " + str(m["medico"]) + n
                msg += "    " + num(marc) + " pac.  |  " + ini + " \u2013 " + fim + n

    # ── Equipe Multiprofissional ──────────────────────────────────────────────
    if mult_manha or mult_tarde:
        msg += n + "\u2501" * 28 + n
        msg += "\U0001f3e5 *EQUIPE MULTIPROFISSIONAL*" + n
        if mult_manha:
            msg += n + "  \U0001f324\ufe0f _Manha_" + n
            for m in mult_manha:
                ini  = m.get("inicio", "")
                fim  = m.get("fim", "")
                marc = m.get("marcacoes") or 0
                esp  = m.get("especialidade", "").strip()
                msg += "  \u2022 " + str(m["medico"])
                if esp:
                    msg += "  _(" + esp + ")_"
                msg += n
                msg += "    " + num(marc) + " pac.  |  " + ini + " \u2013 " + fim + n
        if mult_tarde:
            msg += n + "  \U0001f306 _Tarde_" + n
            for m in mult_tarde:
                ini  = m.get("inicio", "")
                fim  = m.get("fim", "")
                marc = m.get("marcacoes") or 0
                esp  = m.get("especialidade", "").strip()
                msg += "  \u2022 " + str(m["medico"])
                if esp:
                    msg += "  _(" + esp + ")_"
                msg += n
                msg += "    " + num(marc) + " pac.  |  " + ini + " \u2013 " + fim + n

    if vagas_med:
        msg += n + "\u2501" * 28 + n
        msg += "\U0001f513 *VAGAS DISPONIVEIS POR PROFISSIONAL*" + n
        for v in vagas_med:
            msg += "  \u2022 " + str(v["medico"]) + ":  *" + num(v["vagas"]) + " vagas*" + n

    msg += n + "\u2501" * 28 + n
    msg += "_Dashboard Clinica  \u2022  " + datetime.now().strftime("%H:%M") + "_"
    return msg


def montar_fechamento(dados):
    hoje_fmt     = datetime.now().strftime("%d/%m/%Y")
    fat          = dados["fat"]
    cnvs         = dados["convenios"]
    emps         = dados.get("empresas", [])
    meds         = dados["medicos"]
    agd          = dados["agd"]
    abs_m        = dados["abs_med"]
    prod_mes      = dados.get("producao_mes")         or 0
    projecao      = dados.get("projecao_mes")         or 0
    media_dia     = dados.get("media_diaria")         or 0
    guias_mes     = dados.get("guias_mes")            or 0
    dias_rest     = dados.get("dias_uteis_restantes") or 0
    prod_ano_ant  = dados.get("prod_ano_ant")         or 0
    guias_ano_ant = dados.get("guias_ano_ant")        or 0
    hoje_ano_ant  = dados.get("hoje_ano_ant", "")
    meta_mensal   = dados.get("meta_mensal")          or 1200000.0
    meta_dia      = dados.get("meta_diaria")          or 0
    meta_dia_pct  = dados.get("meta_dia_pct")         or 0
    meta_mes_pct  = dados.get("meta_mes_pct")         or 0
    falta_meta    = dados.get("falta_meta")           or 0
    prod          = fat.get("producao") or 0
    total_os      = fat.get("total_os") or 0
    pacientes     = fat.get("pacientes") or 0
    assistencial  = fat.get("assistencial") or 0
    ocupacional   = fat.get("ocupacional") or 0
    prod_ass      = fat.get("prod_assistencial") or 0
    prod_ocup     = fat.get("prod_ocupacional") or 0
    particular    = fat.get("particular") or 0
    marcacoes     = agd.get("marcacoes") or 0
    compareceram  = agd.get("compareceram") or 0
    faltantes     = agd.get("faltantes") or 0
    cancelados    = agd.get("cancelados") or 0
    taxa_abs      = (faltantes / marcacoes * 100) if marcacoes > 0 else 0
    taxa_comp     = (compareceram / marcacoes * 100) if marcacoes > 0 else 0
    abs_tag = "\u2705" if taxa_abs <= 10 else "\u26a0\ufe0f" if taxa_abs <= 25 else "\U0001f534"
    n       = "\n"

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    msg  = "\U0001f319 *FECHAMENTO DO DIA*" + n
    msg += "\U0001f4c5 " + hoje_fmt + n
    msg += "\u2501" * 28 + n + n

    # ── Produção total ────────────────────────────────────────────────────────
    msg += "\U0001f4b5 *PRODUCAO TOTAL*" + n
    msg += "  \u27a4 *" + brl(prod) + "*" + n
    if prod_ano_ant:
        from datetime import datetime as _dt2
        dias_pt = {"Monday":"Seg","Tuesday":"Ter","Wednesday":"Qua","Thursday":"Qui",
                   "Friday":"Sex","Saturday":"Sab","Sunday":"Dom"}
        dia_sem = dias_pt.get(_dt2.strptime(hoje_ano_ant, "%Y-%m-%d").strftime("%A"), "") if hoje_ano_ant else ""
        var_pct = ((prod - prod_ano_ant) / prod_ano_ant * 100) if prod_ano_ant > 0 else 0
        sinal   = "+" if var_pct >= 0 else ""
        msg += "  \U0001f4ca Mesmo dia " + hoje_ano_ant[:4] + " (" + dia_sem + "):  " + brl(prod_ano_ant) + n
        msg += "  \U0001f4c8 Variacao:  *" + sinal + "{:.1f}%".format(var_pct) + "*" + n
    msg += n
    msg += "  \U0001f4c4 Guias: *" + num(total_os) + "*   |   \U0001f465 Pacientes: *" + num(pacientes) + "*" + n

    # ── Por módulo ────────────────────────────────────────────────────────────
    msg += n + "\u2501" * 28 + n
    msg += "\U0001f539 *POR MODULO*" + n
    msg += "  \U0001fa7a Assistencial:  *" + brl(prod_ass) + "*  (" + num(assistencial) + " guias)" + n
    msg += "  \U0001f3ed Ocupacional:   *" + brl(prod_ocup) + "*  (" + num(ocupacional) + " guias)" + n
    if particular > 0:
        msg += "  \U0001f4b3 Particular:    *" + brl(particular) + "*" + n

    # ── Convênios ─────────────────────────────────────────────────────────────
    if cnvs:
        msg += n + "\u2501" * 28 + n
        msg += "\U0001f91d *CONVENIOS \u2014 ASSISTENCIAL*" + n
        for c in cnvs:
            nome = str(c["nome"])[:25].strip()
            msg += "  \u2022 " + nome + n
            msg += "    *" + brl(c["producao"]) + "*  |  " + num(c["guias"]) + " guias  |  " + num(c["pacientes"]) + " pac." + n

    # ── Empresas ──────────────────────────────────────────────────────────────
    if emps:
        msg += n + "\u2501" * 28 + n
        msg += "\U0001f3e2 *EMPRESAS \u2014 OCUPACIONAL*" + n
        for e in emps:
            nome = str(e["nome"])[:25].strip()
            msg += "  \u2022 " + nome + n
            msg += "    *" + brl(e["producao"]) + "*  |  " + num(e["guias"]) + " guias  |  " + num(e["pacientes"]) + " pac." + n

    # ── Equipe ────────────────────────────────────────────────────────────────
    if meds:
        _MULT_CODES_F = {'PSC','NUT','FON','FIS','ENF','TER','FAR','ASS','SOC','PSQ','NEU','FIO'}
        def _is_mult_f(m):
            return m.get('esp_cod', '').strip().upper() in _MULT_CODES_F
        meds_med  = [m for m in meds if not _is_mult_f(m)]
        meds_mult = [m for m in meds if _is_mult_f(m)]

        if meds_med:
            msg += n + "\u2501" * 28 + n
            msg += "\U0001fa7a *EQUIPE MEDICA*" + n
            for m in meds_med:
                msg += "  \u2022 " + str(m["medico"]) + n
                msg += "    *" + brl(m["producao"]) + "*  |  " + num(m["guias"]) + " guias  |  " + num(m["pacientes"]) + " pac." + n

        if meds_mult:
            msg += n + "\U0001f3e5 *EQUIPE MULTIPROFISSIONAL*" + n
            for m in meds_mult:
                esp = m.get("especialidade", "").strip()
                msg += "  \u2022 " + str(m["medico"])
                if esp:
                    msg += "  _(" + esp + ")_"
                msg += n
                msg += "    *" + brl(m["producao"]) + "*  |  " + num(m["guias"]) + " guias  |  " + num(m["pacientes"]) + " pac." + n

    # ── Agenda ────────────────────────────────────────────────────────────────
    msg += n + "\u2501" * 28 + n
    msg += "\U0001f4c5 *AGENDA DO DIA*" + n
    msg += "  \U0001f4cc Marcacoes:     *" + num(marcacoes) + "*" + n
    msg += "  \u2705 Compareceram:  *" + num(compareceram) + "*  (" + "{:.1f}".format(taxa_comp) + "%)" + n
    msg += "  " + abs_tag + " Absenteismo:   *" + "{:.1f}".format(taxa_abs) + "%*  (" + num(faltantes) + " faltantes)" + n
    msg += "  \u274c Cancelamentos: *" + num(cancelados) + "*" + n

    if abs_m:
        msg += n + "  _Maiores absenteismos:_" + n
        for a in abs_m:
            marc = a.get("marcacoes") or 1
            falt = a.get("faltantes") or 0
            pct  = falt / marc * 100
            msg += "  \u2022 " + str(a["medico"]) + ":  " + num(falt) + "/" + num(marc) + "  (" + "{:.0f}".format(pct) + "%)" + n

    # ── Metas ─────────────────────────────────────────────────────────────────
    sinal_dia = "+" if meta_dia_pct >= 100 else ""
    sinal_mes = "+" if meta_mes_pct >= 100 else ""
    msg += n + "\u2501" * 28 + n
    msg += "\U0001f3af *METAS DO MES*" + n
    msg += "  Meta mensal:  *" + brl(meta_mensal) + "*" + n
    msg += "  Meta diaria:  *" + brl(meta_dia) + "*" + n

    msg += n + "\U0001f4c8 *PRODUCAO ACUMULADA*" + n
    msg += "  Acumulado:    *" + brl(prod_mes) + "*  (" + num(int(guias_mes)) + " guias)" + n
    msg += "  Media diaria: *" + brl(media_dia) + "*  vs  *" + brl(meta_dia) + "*  (" + sinal_dia + "{:.1f}%".format(meta_dia_pct - 100) + ")" + n
    msg += "  Projecao mes: *" + brl(projecao) + "*  vs  *" + brl(meta_mensal) + "*  (" + sinal_mes + "{:.1f}%".format(meta_mes_pct - 100) + ")" + n
    msg += "  Falta p/ meta: *" + brl(falta_meta) + "*" + n

    msg += n + "\u2501" * 28 + n
    msg += "_Dashboard Clinica  \u2022  " + datetime.now().strftime("%H:%M") + "_"
    return msg


def montar_previa_amanha(dados):
    agd        = dados["agd"]
    medicos    = dados["medicos"]
    vagas_med  = dados["vagas_med"]
    ticket     = dados.get("ticket_medio") or 0
    marcacoes  = agd.get("marcacoes") or 0
    vagas_disp = agd.get("vagas_disp") or 0
    cancelados = agd.get("cancelados") or 0
    previsao   = marcacoes * ticket
    dia_sem    = dados["dia_semana"]
    amanha_fmt = dados["amanha_fmt"]
    n          = "\n"

    msg  = "*Previa de Amanha - " + dia_sem + " " + amanha_fmt + "*" + n + n
    msg += "*Agenda*" + n
    msg += "  Medicos com agenda: *" + str(agd.get("medicos") or len(medicos)) + "*" + n
    msg += "  Pacientes marcados: *" + num(marcacoes) + "*" + n
    msg += "  Vagas disponiveis:  *" + num(vagas_disp) + "*" + n
    if cancelados > 0:
        msg += "  Ja cancelados: " + num(cancelados) + n

    if previsao > 0:
        msg += n + "*Previsao de Producao*" + n
        msg += "  Potencial: *" + brl(previsao) + "*" + n
        msg += "  _(ticket medio 30d: " + brl(ticket) + ")_" + n

    if medicos:
        msg += n + "*Medicos Escalados*" + n
        for m in medicos:
            ini  = m.get("inicio", "")
            fim  = m.get("fim", "")
            marc = m.get("marcacoes") or 0
            msg += "  - " + str(m["medico"]) + ": " + num(marc) + " pac. (" + ini + "--" + fim + ")" + n

    if vagas_med:
        total_vagas = sum(v.get("vagas", 0) for v in vagas_med)
        msg += n + "*Vagas em Aberto: " + num(total_vagas) + "*" + n
        for v in vagas_med[:5]:
            msg += "  - " + str(v["medico"]) + ": " + num(v["vagas"]) + " vagas" + n

    msg += n + "_Dashboard Clinica - " + datetime.now().strftime("%H:%M") + "_"
    return msg


def montar_mensagem(dados, turno):
    if turno == "manha":
        return montar_manha(dados)
    return montar_fechamento(dados)


# ── Envio WPPConnect ─────────────────────────────────────────────────────────

def _wpp_regenerar_token():
    """Regenera o token do WPPConnect automaticamente."""
    try:
        session  = os.getenv("WPPCONNECT_SESSION", WPPCONNECT_SESSION)
        base     = os.getenv("WPPCONNECT_URL",     WPPCONNECT_URL)
        url      = base + "/api/" + session + "/THISISMYSECURETOKEN/generate-token"
        resp     = requests.post(url, timeout=10)
        data     = resp.json()
        novo_token = data.get("token", "")
        if novo_token:
            os.environ["WPPCONNECT_TOKEN"] = novo_token
            try:
                requests.post(
                    "http://localhost:8000/api/whatsapp/config",
                    params={
                        "provider": "wppconnect",
                        "wppconnect_session": session,
                        "wppconnect_token": novo_token,
                        "numero_destino": os.getenv("WPPCONNECT_NUMEROS", ""),
                        "ativo": "true"
                    },
                    timeout=5
                )
            except Exception:
                pass
            print(f"[WPPConnect] Token renovado automaticamente.")
            return novo_token
    except Exception as e:
        print(f"[WPPConnect] Falha ao renovar token: {e}")
    return None


def enviar_wppconnect(mensagem, numero):
    session   = os.getenv("WPPCONNECT_SESSION", WPPCONNECT_SESSION)
    token     = os.getenv("WPPCONNECT_TOKEN",   WPPCONNECT_TOKEN)
    base      = os.getenv("WPPCONNECT_URL",     WPPCONNECT_URL)
    num_clean = numero.strip().replace("+", "").replace(" ", "").replace("-", "")
    endpoint  = base + "/api/" + session + "/send-message"

    def _tentar(tok):
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + tok}
        payload = {"phone": num_clean + "@c.us", "message": mensagem, "isGroup": False}
        return requests.post(endpoint, headers=headers, json=payload, timeout=20)

    try:
        resp = _tentar(token)
        if resp.status_code == 401:
            print("[WPPConnect] Token expirado, regenerando...")
            novo = _wpp_regenerar_token()
            if novo:
                resp = _tentar(novo)
        resp.raise_for_status()
        return {"ok": True, "numero": numero, "status": resp.status_code}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "numero": numero, "erro": "WPPConnect nao encontrado em localhost:21465"}
    except requests.exceptions.Timeout:
        return {"ok": False, "numero": numero, "erro": "Timeout WPPConnect."}
    except Exception as e:
        return {"ok": False, "numero": numero, "erro": str(e)[:150]}


def enviar_zapi(mensagem, numero):
    inst  = os.getenv("ZAPI_INSTANCE",     ZAPI_INSTANCE)
    tok   = os.getenv("ZAPI_TOKEN",        ZAPI_TOKEN)
    ctok  = os.getenv("ZAPI_CLIENT_TOKEN", ZAPI_CLIENT_TOKEN)
    num_clean = numero.strip().replace("+", "").replace(" ", "").replace("-", "")
    endpoint = "https://api.z-api.io/instances/" + inst + "/token/" + tok + "/send-text"
    headers  = {"Content-Type": "application/json", "Client-Token": ctok}
    payload  = {"phone": num_clean, "message": mensagem}
    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=20)
        resp.raise_for_status()
        return {"ok": True, "numero": numero, "status": resp.status_code}
    except Exception as e:
        return {"ok": False, "numero": numero, "erro": str(e)[:150]}


def enviar_evolution(mensagem, numero):
    base     = os.getenv("EVOLUTION_URL",  EVOLUTION_URL)
    k        = os.getenv("EVOLUTION_KEY",  EVOLUTION_KEY)
    inst     = os.getenv("EVOLUTION_INST", EVOLUTION_INST)
    endpoint = base + "/message/sendText/" + inst
    headers  = {"Content-Type": "application/json", "apikey": k}
    payload  = {"number": numero.strip(), "text": mensagem, "delay": 1000}
    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        return {"ok": True, "numero": numero, "status": resp.status_code}
    except Exception as e:
        return {"ok": False, "numero": numero, "erro": str(e)[:150]}


def enviar_whatsapp_numero(mensagem, numero, **kwargs):
    provider = os.getenv("WPP_PROVIDER", WPP_PROVIDER)
    if provider == "wppconnect":
        return enviar_wppconnect(mensagem, numero)
    elif provider == "zapi":
        return enviar_zapi(mensagem, numero)
    else:
        return enviar_evolution(mensagem, numero)


def enviar_whatsapp(mensagem, numeros=None, **kwargs):
    if numeros is None:
        lista = DEST_NUMBERS
    elif isinstance(numeros, str):
        lista = [n.strip() for n in numeros.split(",") if n.strip()]
    else:
        lista = [n.strip() for n in numeros if n.strip()]

    resultados = []
    for n in lista:
        r = enviar_whatsapp_numero(mensagem, n)
        resultados.append(r)
        time.sleep(1)

    ok_count = sum(1 for r in resultados if r["ok"])
    return {"ok": ok_count > 0, "enviados": ok_count, "total": len(lista), "detalhes": resultados}


def enviar_resumo(query_func, turno="auto", numero=None):
    """Funcao principal - busca dados, monta e envia.
    Para turno='fechamento', envia duas mensagens: fechamento + previa de amanha.
    """
    if turno == "auto":
        turno = "manha" if datetime.now().hour < 13 else "fechamento"

    if turno == "manha":
        dados     = buscar_dados_manha(query_func)
        mensagem  = montar_manha(dados)
        resultado = enviar_whatsapp(mensagem, numeros=numero)
        print("[WhatsApp] " + datetime.now().strftime("%H:%M:%S") + " turno=manha ok=" + str(resultado["ok"]))
        return {"mensagem": mensagem, "envio": resultado}

    else:
        dados_fech = buscar_dados_fechamento(query_func)
        msg_fech   = montar_fechamento(dados_fech)
        r1 = enviar_whatsapp(msg_fech, numeros=numero)
        print("[WhatsApp] " + datetime.now().strftime("%H:%M:%S") + " fechamento ok=" + str(r1["ok"]))

        time.sleep(3)

        dados_amanha = buscar_dados_amanha(query_func)
        msg_amanha   = montar_previa_amanha(dados_amanha)
        r2 = enviar_whatsapp(msg_amanha, numeros=numero)
        print("[WhatsApp] " + datetime.now().strftime("%H:%M:%S") + " previa_amanha ok=" + str(r2["ok"]))

        return {
            "fechamento": {"mensagem": msg_fech,   "envio": r1},
            "previa":     {"mensagem": msg_amanha, "envio": r2},
        }


# ── Health check da sessão WhatsApp ─────────────────────────────────────────

def checar_status_wpp() -> dict:
    """
    Verifica se o provider WhatsApp está online e com sessão ativa.
    Retorna dict com:
      online    : bool  — provider acessível
      conectado : bool  — sessão/celular conectado
      provider  : str   — wppconnect | zapi | evolution
      detalhe   : str   — mensagem descritiva
      ts        : str   — horário da verificação
    """
    provider = os.getenv("WPP_PROVIDER", WPP_PROVIDER)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── WPPConnect ────────────────────────────────────────────────────────────
    if provider == "wppconnect":
        session = os.getenv("WPPCONNECT_SESSION", WPPCONNECT_SESSION)
        token   = os.getenv("WPPCONNECT_TOKEN",   WPPCONNECT_TOKEN)
        base    = os.getenv("WPPCONNECT_URL",      WPPCONNECT_URL)
        url     = base + "/api/" + session + "/status-session"
        try:
            resp = requests.get(
                url,
                headers={"Authorization": "Bearer " + token},
                timeout=5
            )
            if resp.status_code == 401:
                # Token expirado — tenta renovar
                novo = _wpp_regenerar_token()
                if novo:
                    resp = requests.get(
                        url,
                        headers={"Authorization": "Bearer " + novo},
                        timeout=5
                    )
            data   = resp.json()
            status = data.get("status", "")   # CONNECTED | DISCONNECTED | CLOSED etc.
            state  = data.get("state",  "")
            conectado = status in ("CONNECTED", "isLogged") or state in ("CONNECTED",)
            return {
                "online":    True,
                "conectado": conectado,
                "provider":  "wppconnect",
                "status":    status or state,
                "detalhe":   "Sessao ativa" if conectado else "Sessao desconectada — escaneie o QR Code",
                "ts":        ts,
            }
        except requests.exceptions.ConnectionError:
            return {
                "online":    False,
                "conectado": False,
                "provider":  "wppconnect",
                "status":    "offline",
                "detalhe":   "WPPConnect nao encontrado em " + base + " — verifique se o servico esta rodando",
                "ts":        ts,
            }
        except Exception as e:
            return {
                "online":    False,
                "conectado": False,
                "provider":  "wppconnect",
                "status":    "erro",
                "detalhe":   str(e)[:200],
                "ts":        ts,
            }

    # ── Z-API ─────────────────────────────────────────────────────────────────
    elif provider == "zapi":
        inst  = os.getenv("ZAPI_INSTANCE",     ZAPI_INSTANCE)
        tok   = os.getenv("ZAPI_TOKEN",        ZAPI_TOKEN)
        ctok  = os.getenv("ZAPI_CLIENT_TOKEN", ZAPI_CLIENT_TOKEN)
        url   = f"https://api.z-api.io/instances/{inst}/token/{tok}/status"
        try:
            resp = requests.get(url, headers={"Client-Token": ctok}, timeout=5)
            data = resp.json()
            conectado = data.get("connected", False)
            return {
                "online":    True,
                "conectado": conectado,
                "provider":  "zapi",
                "status":    "connected" if conectado else "disconnected",
                "detalhe":   "Sessao ativa" if conectado else "Sessao desconectada — verifique o Z-API",
                "ts":        ts,
            }
        except Exception as e:
            return {
                "online":    False,
                "conectado": False,
                "provider":  "zapi",
                "status":    "erro",
                "detalhe":   str(e)[:200],
                "ts":        ts,
            }

    # ── Evolution API ─────────────────────────────────────────────────────────
    else:
        base = os.getenv("EVOLUTION_URL",  EVOLUTION_URL)
        k    = os.getenv("EVOLUTION_KEY",  EVOLUTION_KEY)
        inst = os.getenv("EVOLUTION_INST", EVOLUTION_INST)
        url  = base + "/instance/connectionState/" + inst
        try:
            resp = requests.get(url, headers={"apikey": k}, timeout=5)
            data = resp.json()
            state     = data.get("instance", {}).get("state", "") or data.get("state", "")
            conectado = state in ("open", "CONNECTED")
            return {
                "online":    True,
                "conectado": conectado,
                "provider":  "evolution",
                "status":    state,
                "detalhe":   "Sessao ativa" if conectado else "Sessao desconectada — escaneie o QR Code no Evolution",
                "ts":        ts,
            }
        except Exception as e:
            return {
                "online":    False,
                "conectado": False,
                "provider":  "evolution",
                "status":    "erro",
                "detalhe":   str(e)[:200],
                "ts":        ts,
            }
