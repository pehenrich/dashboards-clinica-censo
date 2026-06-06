with open("C:/Dashboard/backend/whatsapp_sender.py", "r", encoding="utf-8") as f:
    c = f.read()

# Fix montar_manha vars
old1 = "    medicos_manha = dados.get(\"medicos_manha\", [])\n    medicos_tarde = dados.get(\"medicos_tarde\", [])"
new1 = """    medicos_manha = dados.get("medicos_manha", [])
    medicos_tarde = dados.get("medicos_tarde", [])
    prod_mes      = dados.get("producao_mes")         or 0
    projecao      = dados.get("projecao_mes")         or 0
    media_dia     = dados.get("media_diaria")         or 0
    guias_mes     = dados.get("guias_mes")            or 0
    dias_rest     = dados.get("dias_uteis_restantes") or 0
    prod_ano_ant  = dados.get("prod_ano_ant")         or 0
    guias_ano_ant = dados.get("guias_ano_ant")        or 0
    hoje_ano_ant  = dados.get("hoje_ano_ant", "")"""
c = c.replace(old1, new1)

# Fix montar_fechamento vars
old2 = "    abs_m        = dados[\"abs_med\"]\n    prod         = fat.get(\"producao\") or 0"
new2 = """    abs_m         = dados["abs_med"]
    prod_mes      = dados.get("producao_mes")         or 0
    projecao      = dados.get("projecao_mes")         or 0
    media_dia     = dados.get("media_diaria")         or 0
    guias_mes     = dados.get("guias_mes")            or 0
    dias_rest     = dados.get("dias_uteis_restantes") or 0
    prod_ano_ant  = dados.get("prod_ano_ant")         or 0
    guias_ano_ant = dados.get("guias_ano_ant")        or 0
    hoje_ano_ant  = dados.get("hoje_ano_ant", "")
    prod          = fat.get("producao") or 0"""
c = c.replace(old2, new2)

with open("C:/Dashboard/backend/whatsapp_sender.py", "w", encoding="utf-8") as f:
    f.write(c)
print("OK:", c.count("prod_mes"))
