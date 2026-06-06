with open("C:/Dashboard/backend/whatsapp_sender.py", "r", encoding="utf-8") as f:
    c = f.read()

# Fix montar_manha - add variable declarations
old = "    medicos_manha = dados.get(\"medicos_manha\", [])\n    medicos_tarde = dados.get(\"medicos_tarde\", [])"
new = """    medicos_manha = dados.get("medicos_manha", [])
    medicos_tarde = dados.get("medicos_tarde", [])
    prod_mes  = dados.get("producao_mes")         or 0
    projecao  = dados.get("projecao_mes")         or 0
    media_dia = dados.get("media_diaria")         or 0
    guias_mes = dados.get("guias_mes")            or 0
    dias_rest = dados.get("dias_uteis_restantes") or 0"""

c = c.replace(old, new)

# Fix montar_fechamento - add variable declarations
old2 = "    abs_m        = dados[\"abs_med\"]\n    prod         = fat.get(\"producao\") or 0"
new2 = """    abs_m        = dados["abs_med"]
    prod_mes     = dados.get("producao_mes")         or 0
    projecao     = dados.get("projecao_mes")         or 0
    media_dia    = dados.get("media_diaria")         or 0
    guias_mes    = dados.get("guias_mes")            or 0
    dias_rest    = dados.get("dias_uteis_restantes") or 0
    prod         = fat.get("producao") or 0"""

c = c.replace(old2, new2)

with open("C:/Dashboard/backend/whatsapp_sender.py", "w", encoding="utf-8") as f:
    f.write(c)
print("OK")
