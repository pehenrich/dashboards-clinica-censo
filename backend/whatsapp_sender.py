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

# Recepcoes exibidas na mensagem de fechamento, na ordem desejada
RECEPCOES_WPP = [
    ("RCN", "Consultorios"),
    ("RDI", "Diagnostico"),
    ("ROC", "Ocupacional"),
    ("RCI", "Censo Imagem"),
]


def _is_mult(m):
    """Multiprofissional = qualquer conselho que nao seja CRM (medicina).
    psv_esp_cod fica sempre vazio nesta base, entao nao da pra usar ele —
    PSV_CONSELHO (CRM/CRP/CRN/CRF/CRBM etc.) e o campo que realmente
    distingue medico de outros profissionais (nutricionista, psicologo...)."""
    conselho = m.get('conselho', '').strip().upper()
    return bool(conselho) and conselho != 'CRM'


def _classificar_servico(nome):
    """Classifica um servico em Consultas / Imagem / SADT (exames em geral)."""
    if not nome:
        return "SADT"
    n = nome.upper()
    if "CONSULTA" in n:
        return "Consultas"
    if ("RAIO" in n or "ULTRASSOM" in n or "ULTRASSONOGRAFIA" in n or "RADIOGRAFIA" in n
            or "TOMOGRAFIA" in n or "MAMOGRAFIA" in n or "DENSITOMETRIA" in n or "ECOCARDIOGRAMA" in n):
        return "Imagem"
    return "SADT"


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

def _carregar_metas_producao():
    """Lê metas_config.json (mesmo arquivo usado pelo dashboard/Painel TV) — chave 'producao'."""
    import json as _json
    try:
        with open("metas_config.json", encoding="utf-8") as f:
            cfg = _json.load(f).get("producao", {}) or {}
    except Exception:
        cfg = {}
    return {
        "meta_mensal": cfg.get("meta_mensal") or 1200000.0,
        "meta_diaria": cfg.get("meta_diaria") or 48000.0,
        "meta_sabado": cfg.get("meta_sabado") or cfg.get("meta_diaria") or 48000.0,
    }


def _calcular_metas(producao_mes: float, meta_mensal_fixa: float = None) -> dict:
    """
    Calcula META_MENSAL, meta_diaria, meta_dia_pct, meta_mes_pct e falta_meta
    com base na produção acumulada do mês e nas metas configuradas no dashboard
    (metas_config.json → "producao"): meta_diaria fixa nos dias de semana,
    meta_sabado aos sábados — mesmo critério usado no módulo Produção Mensal.

    meta_dia_pct → média diária real / meta diária de dia de semana  (100 = no alvo)
    meta_mes_pct → acumulado real / meta acumulada até hoje  (100 = no alvo)
    falta_meta   → quanto ainda falta para bater a meta mensal (>= 0)
    """
    import datetime as _dt

    _cfg = _carregar_metas_producao()
    META_MENSAL = meta_mensal_fixa if meta_mensal_fixa is not None else _cfg["meta_mensal"]
    meta_diaria = _cfg["meta_diaria"]
    meta_sabado = _cfg["meta_sabado"]

    hoje     = _dt.date.today()
    ano, mes = hoje.year, hoje.month

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

    def _meta_do_dia(d):
        data = _dt.date(ano, mes, d)
        if data in feriados or data.weekday() == 6:  # feriado ou domingo
            return 0.0
        if data.weekday() == 5:  # sabado
            return meta_sabado
        return meta_diaria

    dias_uteis_passados = sum(1 for d in range(1, hoje.day + 1) if _meta_do_dia(d) > 0)
    meta_acum      = sum(_meta_do_dia(d) for d in range(1, hoje.day + 1))   # meta acumulada até hoje
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

    # Médicos divididos por turno (manhã = antes das 12h, tarde = 12h+).
    # Pacientes e horário de cada turno contam só os agendamentos daquele
    # turno — quem atende manhã e tarde aparece nas duas listas, cada uma
    # com a contagem/horário específicos daquele período.
    medicos_raw = query_func(
        "SELECT TOP 20 RTRIM(psv.psv_apel) AS medico, "
        "RTRIM(ISNULL(psv.PSV_CONSELHO, '')) AS conselho, "
        "SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B') AND CAST(agm.agm_hini AS TIME) < '12:00' THEN 1 ELSE 0 END) AS marcacoes_manha, "
        "SUM(CASE WHEN agm.agm_pac > 0 AND agm.agm_stat NOT IN ('C','B') AND CAST(agm.agm_hini AS TIME) >= '12:00' THEN 1 ELSE 0 END) AS marcacoes_tarde, "
        "MIN(CASE WHEN CAST(agm.agm_hini AS TIME) < '12:00' THEN agm.agm_hini END) AS inicio_manha, "
        "MAX(CASE WHEN CAST(agm.agm_hini AS TIME) < '12:00' THEN agm.agm_hini END) AS fim_manha, "
        "MAX(CASE WHEN CAST(agm.agm_hini AS TIME) >= '12:00' THEN agm.agm_hini END) AS fim_tarde, "
        "MIN(agm.agm_hini) AS inicio_geral "
        "FROM agm "
        "JOIN psv ON psv.psv_cod = agm.agm_med "
        "WHERE CAST(agm.agm_hini AS DATE) = '" + hoje + "' AND agm.agm_pac > 0 "
        "GROUP BY RTRIM(psv.psv_apel), RTRIM(ISNULL(psv.PSV_CONSELHO,'')) "
        "ORDER BY MIN(agm.agm_hini)"
    )
    for r in medicos_raw:
        for k, v in r.items():
            if hasattr(v, "strftime"):
                r[k] = v.strftime("%H:%M")

    medicos_manha = [m for m in medicos_raw if (m.get('marcacoes_manha') or 0) > 0 and not _is_mult(m)]
    medicos_tarde = [m for m in medicos_raw if (m.get('marcacoes_tarde') or 0) > 0 and not _is_mult(m)]
    mult_manha    = [m for m in medicos_raw if (m.get('marcacoes_manha') or 0) > 0 and _is_mult(m)]
    mult_tarde    = [m for m in medicos_raw if (m.get('marcacoes_tarde') or 0) > 0 and _is_mult(m)]
    medicos = medicos_raw  # compatibilidade

    vagas_med = query_func(
        "SELECT TOP 10 RTRIM(psv.psv_apel) AS medico, COUNT(*) AS vagas "
        "FROM EX_HORARIOS eh LEFT JOIN psv ON psv.psv_cod = eh.HOR_MED "
        "WHERE eh.HOR_DATA = '" + hoje + "' "
        "GROUP BY RTRIM(psv.psv_apel) ORDER BY vagas DESC"
    )

    # Se hoje é sábado, o ticket médio usa só sábados anteriores (produção de
    # sábado tem perfil bem diferente de dia de semana) — senão, os últimos
    # 30 dias corridos como sempre.
    if datetime.now().weekday() == 5:
        _sabados = []
        _d = datetime.now().date() - timedelta(days=7)
        while len(_sabados) < 8:
            if _d.weekday() == 5:
                _sabados.append(_d.strftime("%Y-%m-%d"))
            _d -= timedelta(days=1)
        _datas_sql = ",".join("'" + s + "'" for s in _sabados)
        ticket = query_func(
            "SELECT SUM(smm.SMM_VLR - ISNULL(smm.SMM_VLR_DESCONTO,0) "
            "- ISNULL(smm.SMM_VLR_COPARTIC,0) + ISNULL(smm.SMM_AJUSTE_VLR,0)) "
            "/ NULLIF(COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num),0) AS ticket_medio "
            "FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num "
            "WHERE CAST(osm.osm_dthr AS DATE) IN (" + _datas_sql + ") "
            "AND smm.SMM_SFAT IN ('A','F','P')"
        )
    else:
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

    # Projeção ponderada: sábado pesa proporcionalmente menos que um dia de
    # semana (meta_sabado / meta_diaria) — mesmo critério do fechamento.
    from calendar import monthrange
    _cfg_proj_m = _carregar_metas_producao()
    _peso_sab_m = (_cfg_proj_m["meta_sabado"] / _cfg_proj_m["meta_diaria"]) if _cfg_proj_m["meta_diaria"] else 1.0
    hoje_dt   = datetime.now()
    dias_mes  = monthrange(hoje_dt.year, hoje_dt.month)[1]
    dia_atual = hoje_dt.day

    def _peso_dia_manha(d):
        wd = datetime(hoje_dt.year, hoje_dt.month, d).weekday()
        if wd == 6:      # domingo
            return 0.0
        if wd == 5:      # sabado
            return _peso_sab_m
        return 1.0

    dias_uteis_passados  = sum(_peso_dia_manha(d) for d in range(1, dia_atual + 1))
    dias_uteis_restantes = sum(_peso_dia_manha(d) for d in range(dia_atual + 1, dias_mes + 1))
    media_diaria  = producao_mes / max(dias_uteis_passados, 1e-6)
    projecao_mes  = producao_mes + (media_diaria * dias_uteis_restantes)

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

    # Produção por recepção (Consultórios/Diagnóstico/Ocupacional/Censo Imagem),
    # dividida em Consultas / Imagem / SADT (exames em geral)
    prod_recepcao_raw = query_func(
        "SELECT RTRIM(osm.osm_str) AS recepcao_cod, RTRIM(sk.SMK_NOME) AS servico_nome, "
        "SUM(smm.SMM_VLR-ISNULL(smm.SMM_VLR_DESCONTO,0)-ISNULL(smm.SMM_VLR_COPARTIC,0)+ISNULL(smm.SMM_AJUSTE_VLR,0)) AS producao "
        "FROM smm JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM "
        "JOIN smk sk ON sk.SMK_COD = smm.SMM_COD "
        "WHERE CAST(osm.osm_dthr AS DATE)='" + hoje + "' AND smm.SMM_SFAT IN ('A','F','P') "
        "AND RTRIM(osm.osm_str) IN ('RCN','RDI','ROC','RCI') "
        "GROUP BY RTRIM(osm.osm_str), RTRIM(sk.SMK_NOME)"
    )
    producao_por_recepcao = {cod: {"Consultas": 0.0, "Imagem": 0.0, "SADT": 0.0} for cod, _ in RECEPCOES_WPP}
    for r in prod_recepcao_raw:
        cod = r.get("recepcao_cod")
        if cod not in producao_por_recepcao:
            continue
        tipo = _classificar_servico(r.get("servico_nome"))
        producao_por_recepcao[cod][tipo] += float(r.get("producao") or 0)

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

    # Produção por médico que REALIZOU o atendimento (executor do servico,
    # nao quem apenas solicitou): COALESCE(SMM_MED, osm_mreq) e o mesmo
    # criterio "executado" usado em /api/financeiro/producao-mensal/profissionais.
    medicos = query_func(
        "SELECT TOP 20 RTRIM(psv.psv_apel) AS medico, "
        "RTRIM(ISNULL(esp.esp_nome, '')) AS especialidade, "
        "RTRIM(ISNULL(psv.psv_esp_cod, '')) AS esp_cod, "
        "RTRIM(ISNULL(psv.PSV_CONSELHO, '')) AS conselho, "
        "COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS guias, "
        "COUNT(DISTINCT osm.osm_pac) AS pacientes, "
        "SUM(smm.SMM_VLR-ISNULL(smm.SMM_VLR_DESCONTO,0)-ISNULL(smm.SMM_VLR_COPARTIC,0)+ISNULL(smm.SMM_AJUSTE_VLR,0)) AS producao "
        "FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num "
        "JOIN psv ON psv.psv_cod=COALESCE(smm.SMM_MED, osm.osm_mreq) "
        "LEFT JOIN esp ON esp.esp_cod=psv.psv_esp_cod "
        "WHERE CAST(osm.osm_dthr AS DATE)='" + hoje + "' AND smm.SMM_SFAT IN ('A','F','P') "
        "AND RTRIM(osm.osm_str) = 'RCN' "
        "GROUP BY RTRIM(psv.psv_apel), RTRIM(ISNULL(esp.esp_nome,'')), RTRIM(ISNULL(psv.psv_esp_cod,'')), RTRIM(ISNULL(psv.PSV_CONSELHO,'')) "
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

    # Agenda por profissional: todos que tinham agendamento no dia, com
    # marcacoes/atendimentos/absenteismo (mesmo criterio de "compareceram"
    # usado no resumo geral da agenda do dia).
    abs_med = query_func(
        "SELECT RTRIM(psv.psv_apel) AS medico, RTRIM(ISNULL(psv.PSV_CONSELHO,'')) AS conselho, "
        "SUM(CASE WHEN agm.agm_pac>0 AND agm.agm_stat NOT IN ('C','B') THEN 1 ELSE 0 END) AS marcacoes, "
        "SUM(CASE WHEN agm.agm_pac>0 AND agm.agm_stat NOT IN ('C','B') "
        "AND (agm.agm_stat='E' OR agm.AGM_OSM_SERIE IS NOT NULL OR om.osm_pac IS NOT NULL) THEN 1 ELSE 0 END) AS compareceram, "
        "SUM(CASE WHEN agm.agm_pac>0 AND agm.agm_stat NOT IN ('C','B','E') "
        "AND agm.AGM_OSM_SERIE IS NULL AND om.osm_pac IS NULL THEN 1 ELSE 0 END) AS faltantes "
        "FROM agm JOIN psv ON psv.psv_cod=agm.agm_med "
        "LEFT JOIN (SELECT DISTINCT osm_pac,osm_dthr,CAST(osm_dthr AS DATE) AS osm_data "
        "FROM osm WHERE CAST(osm_dthr AS DATE)='" + hoje + "') om "
        "ON om.osm_pac=agm.agm_pac AND om.osm_data=CAST(agm.agm_hini AS DATE) "
        "AND DATEDIFF(minute,agm.agm_hini,om.osm_dthr) BETWEEN -30 AND 180 "
        "WHERE CAST(agm.agm_hini AS DATE)='" + hoje + "' AND agm.agm_pac>0 "
        "GROUP BY RTRIM(psv.psv_apel), RTRIM(ISNULL(psv.PSV_CONSELHO,'')) "
        "HAVING SUM(CASE WHEN agm.agm_pac>0 AND agm.agm_stat NOT IN ('C','B') THEN 1 ELSE 0 END)>0 "
        "ORDER BY marcacoes DESC"
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

    # Projeção ponderada: sábado pesa proporcionalmente menos que um dia de
    # semana (meta_sabado / meta_diaria), mesmo critério do módulo Produção
    # Mensal — evita distorcer a média/projeção em meses com mais sábados.
    from calendar import monthrange
    _cfg_proj = _carregar_metas_producao()
    _peso_sab = (_cfg_proj["meta_sabado"] / _cfg_proj["meta_diaria"]) if _cfg_proj["meta_diaria"] else 1.0
    hoje_dt  = datetime.now()
    dias_mes = monthrange(hoje_dt.year, hoje_dt.month)[1]
    dia_atual = hoje_dt.day

    def _peso_dia_mes(d):
        wd = datetime(hoje_dt.year, hoje_dt.month, d).weekday()
        if wd == 6:      # domingo
            return 0.0
        if wd == 5:      # sabado
            return _peso_sab
        return 1.0

    dias_uteis_passados  = sum(_peso_dia_mes(d) for d in range(1, dia_atual+1))
    dias_uteis_restantes = sum(_peso_dia_mes(d) for d in range(dia_atual+1, dias_mes+1))
    media_diaria = producao_mes / max(dias_uteis_passados, 1e-6)
    projecao_mes = producao_mes + (media_diaria * dias_uteis_restantes)

    # Comparativo de producao: se hoje e sabado, usa a media dos ultimos 5
    # sabados (perfil de producao de sabado e bem diferente de dia de semana,
    # mesmo criterio ja usado no ticket medio); senao, mesmo dia do mes
    # anterior (ajustado se o mes anterior tiver menos dias).
    if datetime.now().weekday() == 5:
        _sabados_cmp = []
        _d = datetime.now().date() - timedelta(days=7)
        while len(_sabados_cmp) < 5:
            if _d.weekday() == 5:
                _sabados_cmp.append(_d.strftime("%Y-%m-%d"))
            _d -= timedelta(days=1)
        _datas_sql_cmp = ",".join("'" + s + "'" for s in _sabados_cmp)
        _prod_cmp_raw = query_func(
            "SELECT SUM(smm.SMM_VLR-ISNULL(smm.SMM_VLR_DESCONTO,0)-ISNULL(smm.SMM_VLR_COPARTIC,0)+ISNULL(smm.SMM_AJUSTE_VLR,0)) AS producao, "
            "COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS guias "
            "FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num "
            "WHERE CAST(osm.osm_dthr AS DATE) IN (" + _datas_sql_cmp + ") AND smm.SMM_SFAT IN ('A','F','P')"
        )
        _n_sabados    = len(_sabados_cmp)
        prod_mes_ant  = ((_prod_cmp_raw[0].get("producao") or 0) if _prod_cmp_raw else 0) / _n_sabados
        guias_mes_ant = ((_prod_cmp_raw[0].get("guias")    or 0) if _prod_cmp_raw else 0) / _n_sabados
        comp_label    = "Media ultimos 5 sabados"
    else:
        import calendar as _cal2
        _hoje_dt   = datetime.now()
        _mes_ant   = _hoje_dt.month - 1 or 12
        _ano_ant   = _hoje_dt.year if _hoje_dt.month > 1 else _hoje_dt.year - 1
        _ult_dia_mes_ant = _cal2.monthrange(_ano_ant, _mes_ant)[1]
        _dia_comp  = min(_hoje_dt.day, _ult_dia_mes_ant)
        _hoje_mes_ant = datetime(_ano_ant, _mes_ant, _dia_comp).strftime("%Y-%m-%d")
        _prod_cmp_raw = query_func(
            "SELECT SUM(smm.SMM_VLR-ISNULL(smm.SMM_VLR_DESCONTO,0)-ISNULL(smm.SMM_VLR_COPARTIC,0)+ISNULL(smm.SMM_AJUSTE_VLR,0)) AS producao, "
            "COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num) AS guias "
            "FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num "
            "WHERE CAST(osm.osm_dthr AS DATE)='" + _hoje_mes_ant + "' AND smm.SMM_SFAT IN ('A','F','P')"
        )
        prod_mes_ant  = (_prod_cmp_raw[0].get("producao") or 0) if _prod_cmp_raw else 0
        guias_mes_ant = (_prod_cmp_raw[0].get("guias")    or 0) if _prod_cmp_raw else 0
        comp_label    = "Mesmo dia mes passado (" + datetime.strptime(_hoje_mes_ant, "%Y-%m-%d").strftime("%d/%m") + ")"

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
        "producao_por_recepcao": producao_por_recepcao,
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
        "prod_mes_ant":         prod_mes_ant,
        "guias_mes_ant":        guias_mes_ant,
        "comp_label":           comp_label,
        "meta_mensal":          META_MENSAL,
        "meta_diaria":          meta_diaria,
        "meta_dia_pct":         meta_dia_pct,
        "meta_mes_pct":         meta_mes_pct,
        "falta_meta":           falta_meta,
    }


def buscar_dados_amanha(query_func):
    # A clinica nao funciona aos domingos: se "amanha" cair num domingo
    # (ou seja, hoje e sabado), a previa pula direto pra segunda-feira.
    _amanha_dt = datetime.now() + timedelta(days=1)
    _pulou_domingo = _amanha_dt.weekday() == 6
    if _pulou_domingo:
        _amanha_dt += timedelta(days=1)
    amanha = _amanha_dt.strftime("%Y-%m-%d")
    dia_semana = _amanha_dt.strftime("%A")
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

    # Se amanhã é sábado, usa ticket médio só de sábados anteriores.
    if _amanha_dt.weekday() == 5:
        _sabados_am = []
        _d_am = _amanha_dt.date() - timedelta(days=7)
        while len(_sabados_am) < 8:
            if _d_am.weekday() == 5:
                _sabados_am.append(_d_am.strftime("%Y-%m-%d"))
            _d_am -= timedelta(days=1)
        _datas_sql_am = ",".join("'" + s + "'" for s in _sabados_am)
        ticket = query_func(
            "SELECT SUM(smm.SMM_VLR-ISNULL(smm.SMM_VLR_DESCONTO,0)"
            "-ISNULL(smm.SMM_VLR_COPARTIC,0)+ISNULL(smm.SMM_AJUSTE_VLR,0))"
            "/NULLIF(COUNT(DISTINCT osm.osm_serie*1000000+osm.osm_num),0) AS ticket_medio "
            "FROM osm JOIN smm ON smm.SMM_OSM_SERIE=osm.osm_serie AND smm.SMM_OSM=osm.osm_num "
            "WHERE CAST(osm.osm_dthr AS DATE) IN (" + _datas_sql_am + ") "
            "AND smm.SMM_SFAT IN ('A','F','P')"
        )
    else:
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
        "amanha_fmt": _amanha_dt.strftime("%d/%m/%Y"),
        "dia_semana": dias_pt.get(dia_semana, dia_semana),
        "pulou_domingo": _pulou_domingo,
        "agd": agd[0] if agd else {},
        "medicos": medicos,
        "vagas_med": vagas_med,
        "ticket_medio": (ticket[0].get("ticket_medio") or 0) if ticket else 0,
    }


def buscar_dados_resumo(query_func):
    return buscar_dados_fechamento(query_func)


# ── Montadores de mensagem ───────────────────────────────────────────────────

def montar_manha(dados):
    """Mensagem enxuta: só os números que importam pra começar o dia."""
    hoje_fmt   = datetime.now().strftime("%d/%m/%Y")
    agd        = dados["agd"]
    medicos    = dados["medicos"]
    ticket     = dados.get("ticket_medio") or 0
    marcacoes  = agd.get("marcacoes") or 0
    cancelados = agd.get("cancelados") or 0
    vagas_disp = agd.get("vagas_disp") or 0
    previsao   = marcacoes * ticket
    n          = "\n"

    msg  = "\U0001f305 *BOM DIA \u2014 AGENDA DE HOJE*" + n
    msg += "\U0001f4c5 " + hoje_fmt + n
    msg += "\u2501" * 28 + n + n

    msg += "  \U0001f468\u200d\u2695\ufe0f Profissionais:  *" + str(agd.get("medicos") or len(medicos)) + "*" + n
    msg += "  \U0001f9d1\u200d\U0001f91d\u200d\U0001f9d1 Pac. marcados:  *" + num(marcacoes) + "*" + n
    msg += "  \U0001f7e2 Vagas abertas:  *" + num(vagas_disp) + "*" + n
    if cancelados > 0:
        msg += "  \U0001f534 Cancelamentos:  *" + num(cancelados) + "*" + n

    if previsao > 0:
        msg += n + "💰 Previsao (se todos comparecerem):  *" + brl(previsao) + "*" + n

    medicos_manha = dados.get("medicos_manha", [])
    medicos_tarde = dados.get("medicos_tarde", [])
    mult_manha    = dados.get("mult_manha", [])
    mult_tarde    = dados.get("mult_tarde", [])

    def _linhas_manha(lista):
        out = ""
        for m in lista:
            ini  = m.get("inicio_manha", "")
            fim  = m.get("fim_manha", "")
            marc = m.get("marcacoes_manha") or 0
            out += "    • " + str(m["medico"]) + " — " + num(marc) + " pac. (" + ini + "–" + fim + ")" + n
        return out

    def _linhas_tarde(lista):
        out = ""
        for m in lista:
            fim  = m.get("fim_tarde", "")
            marc = m.get("marcacoes_tarde") or 0
            out += "    • " + str(m["medico"]) + " — " + num(marc) + " pac. (12:00–" + fim + ")" + n
        return out

    if medicos_manha or medicos_tarde:
        msg += n + "━" * 28 + n
        msg += "👨‍⚕️ *EQUIPE MEDICA*" + n
        if medicos_manha:
            msg += "  Manha:" + n + _linhas_manha(medicos_manha)
        if medicos_tarde:
            msg += "  Tarde:" + n + _linhas_tarde(medicos_tarde)

    if mult_manha or mult_tarde:
        msg += n + "🏥 *MULTIPROFISSIONAL*" + n
        if mult_manha:
            msg += "  Manha:" + n + _linhas_manha(mult_manha)
        if mult_tarde:
            msg += "  Tarde:" + n + _linhas_tarde(mult_tarde)

    msg += n + "\u2501" * 28 + n
    msg += "_Dashboard Clinica  \u2022  " + datetime.now().strftime("%H:%M") + "_"
    return msg


def montar_fechamento(dados):
    """Mensagem enxuta: totais e metas, sem listar cada médico/convênio/empresa."""
    hoje_fmt     = datetime.now().strftime("%d/%m/%Y")
    fat          = dados["fat"]
    agd          = dados["agd"]
    prod_mes      = dados.get("producao_mes")         or 0
    projecao      = dados.get("projecao_mes")         or 0
    media_dia     = dados.get("media_diaria")         or 0
    guias_mes     = dados.get("guias_mes")            or 0
    prod_mes_ant  = dados.get("prod_mes_ant")         or 0
    comp_label    = dados.get("comp_label", "")
    meta_mensal   = dados.get("meta_mensal")          or 1200000.0
    meta_dia      = dados.get("meta_diaria")          or 0
    meta_dia_pct  = dados.get("meta_dia_pct")         or 0
    meta_mes_pct  = dados.get("meta_mes_pct")         or 0
    falta_meta    = dados.get("falta_meta")           or 0
    prod          = fat.get("producao") or 0
    total_os      = fat.get("total_os") or 0
    pacientes     = fat.get("pacientes") or 0
    producao_por_recepcao = dados.get("producao_por_recepcao") or {}
    agenda_med    = dados.get("abs_med") or []
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
    if prod_mes_ant:
        var_pct = ((prod - prod_mes_ant) / prod_mes_ant * 100) if prod_mes_ant > 0 else 0
        sinal   = "+" if var_pct >= 0 else ""
        msg += "  \U0001f4ca " + comp_label + ":  " + brl(prod_mes_ant) + n
        msg += "  \U0001f4c8 Variacao:  *" + sinal + "{:.1f}%".format(var_pct) + "*" + n
    msg += n
    msg += "  \U0001f4c4 Guias: *" + num(total_os) + "*   |   \U0001f465 Pacientes: *" + num(pacientes) + "*" + n

    # -- Por recepcao ------------------------------------------------------
    msg += n + "━" * 28 + n
    msg += "🔹 *PRODUCAO POR RECEPCAO*" + n
    for cod, nome in RECEPCOES_WPP:
        tipos = producao_por_recepcao.get(cod, {})
        total_recep = sum(tipos.values())
        if total_recep <= 0:
            continue
        msg += n + "  " + nome + ":  *" + brl(total_recep) + "*" + n
        partes = [tipo + " " + brl(tipos.get(tipo, 0)) for tipo in ("Consultas", "Imagem", "SADT") if tipos.get(tipo, 0) > 0]
        if partes:
            msg += "    " + "  |  ".join(partes) + n

    # -- Agenda por profissional: quem tinha agendamento no dia, quantidade
    # de atendimentos (comparecimentos) e absenteismo em % -------------------
    _EXCLUIR_PROFISSIONAIS = {"JESSICA OLIVEIRA"}
    agenda_med_filtrada = [
        m for m in agenda_med
        if str(m.get("medico", "")).strip().upper() not in _EXCLUIR_PROFISSIONAIS
    ]

    def _linha_agenda(m):
        m_marc = m.get("marcacoes") or 0
        m_comp = m.get("compareceram") or 0
        m_falt = m.get("faltantes") or 0
        m_abs_pct = (m_falt / m_marc * 100) if m_marc > 0 else 0
        return ("  • " + str(m["medico"]) + ":  " + num(m_marc) + " marc.  |  "
                + num(m_comp) + " atend.  |  " + "{:.0f}%".format(m_abs_pct) + " abs." + n)

    agenda_crm  = [m for m in agenda_med_filtrada if not _is_mult(m)]
    agenda_mult = [m for m in agenda_med_filtrada if _is_mult(m)]

    if agenda_crm:
        msg += n + "━" * 28 + n
        msg += "\U0001f4c5 *AGENDA POR MEDICO*" + n
        for m in agenda_crm:
            msg += _linha_agenda(m)

    if agenda_mult:
        msg += n + "\U0001f3e5 *AGENDA MULTIPROFISSIONAL*" + n
        for m in agenda_mult:
            msg += _linha_agenda(m)

    # ── Agenda ────────────────────────────────────────────────────────────────
    msg += n + "\u2501" * 28 + n
    msg += "\U0001f4c5 *AGENDA DO DIA*" + n
    msg += "  \U0001f4cc Marcacoes:     *" + num(marcacoes) + "*" + n
    msg += "  \u2705 Compareceram:  *" + num(compareceram) + "*  (" + "{:.1f}".format(taxa_comp) + "%)" + n
    msg += "  " + abs_tag + " Absenteismo:   *" + "{:.1f}".format(taxa_abs) + "%*  (" + num(faltantes) + " faltantes)" + n
    msg += "  \u274c Cancelamentos: *" + num(cancelados) + "*" + n

    # ── Metas ─────────────────────────────────────────────────────────────────
    sinal_dia = "+" if meta_dia_pct >= 100 else ""
    sinal_mes = "+" if meta_mes_pct >= 100 else ""
    msg += n + "\u2501" * 28 + n
    msg += "📈 *PRODUCAO ACUMULADA*" + n
    msg += "  Acumulado:    *" + brl(prod_mes) + "*  (" + num(int(guias_mes)) + " guias)" + n
    msg += "  Media diaria: *" + brl(media_dia) + "*  vs  *" + brl(meta_dia) + "*  (" + sinal_dia + "{:.1f}%".format(meta_dia_pct - 100) + ")" + n
    msg += "  Projecao mes: *" + brl(projecao) + "*  vs  *" + brl(meta_mensal) + "*  (" + sinal_mes + "{:.1f}%".format(meta_mes_pct - 100) + ")" + n
    msg += "  Falta p/ meta: *" + brl(falta_meta) + "*" + n

    msg += n + "\u2501" * 28 + n
    msg += "_Dashboard Clinica  \u2022  " + datetime.now().strftime("%H:%M") + "_"
    return msg


def montar_previa_amanha(dados):
    """Mensagem enxuta: só o essencial pra planejar amanhã."""
    agd        = dados["agd"]
    medicos    = dados["medicos"]
    ticket     = dados.get("ticket_medio") or 0
    marcacoes  = agd.get("marcacoes") or 0
    vagas_disp = agd.get("vagas_disp") or 0
    cancelados = agd.get("cancelados") or 0
    previsao   = marcacoes * ticket
    dia_sem    = dados["dia_semana"]
    amanha_fmt = dados["amanha_fmt"]
    pulou_domingo = dados.get("pulou_domingo", False)
    n          = "\n"

    titulo = ("Previa - " if pulou_domingo else "Previa de Amanha - ") + dia_sem + " " + amanha_fmt
    msg  = "*" + titulo + "*" + n + n
    if pulou_domingo:
        msg += "_(domingo sem atendimento — proxima previa e de segunda)_" + n + n
    msg += "*Agenda*" + n
    msg += "  Medicos com agenda: *" + str(agd.get("medicos") or len(medicos)) + "*" + n
    msg += "  Pacientes marcados: *" + num(marcacoes) + "*" + n
    msg += "  Vagas disponiveis:  *" + num(vagas_disp) + "*" + n
    if cancelados > 0:
        msg += "  Ja cancelados: " + num(cancelados) + n

    if previsao > 0:
        eh_sabado = dia_sem.strip().lower().startswith("sabado") or dia_sem.strip().lower().startswith("sábado")
        rotulo_ticket = "ticket medio sabados" if eh_sabado else "ticket medio 30d"
        msg += n + "*Previsao de Producao*" + n
        msg += "  Potencial: *" + brl(previsao) + "*" + n
        msg += "  _(" + rotulo_ticket + ": " + brl(ticket) + ")_" + n

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
