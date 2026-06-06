with open("C:/Dashboard/backend/whatsapp_sender.py", "r", encoding="utf-8") as f:
    c = f.read()

old = """    msg += n + "*Producao do Mes*" + n
    msg += "  Acumulado:    *" + brl(prod_mes) + "* (" + num(int(guias_mes)) + " guias)" + n
    msg += "  Media diaria: *" + brl(media_dia) + "*" + n
    msg += "  Projecao mes: *" + brl(projecao) + "* (" + str(int(dias_rest)) + " dias uteis restantes)" + n
    msg += n + "_Dashboard Clinica - " + datetime.now().strftime("%H:%M") + "_"
    return msg
def montar_mensagem"""

new = """    msg += n + "_Dashboard Clinica - " + datetime.now().strftime("%H:%M") + "_"
    return msg
def montar_mensagem"""

c = c.replace(old, new)
with open("C:/Dashboard/backend/whatsapp_sender.py", "w", encoding="utf-8") as f:
    f.write(c)
print("OK")
