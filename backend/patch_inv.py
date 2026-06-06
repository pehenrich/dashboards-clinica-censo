with open("C:/Dashboard/backend/main.py", "r", encoding="utf-8") as f:
    c = f.read()

# Add endpoint to get last inventory date
marker = '@app.get("/api/estoque/resumo")'

new_endpoint = '''@app.get("/api/estoque/ultimo-inventario")
def estoque_ultimo_inventario():
    """Retorna a data do último inventário realizado."""
    r = query("""
        SELECT TOP 1
            INV_NUM,
            CONVERT(VARCHAR(10), INV_DT_CONTAGEM, 120) AS data_inventario,
            CONVERT(VARCHAR(10), INV_DATA, 120)         AS data_registro
        FROM INV
        ORDER BY INV_DATA DESC
    """)
    if r:
        return r[0]
    return {"data_inventario": "2026-01-01", "data_registro": "2026-01-01"}


'''

c = c.replace(marker, new_endpoint + marker)
with open("C:/Dashboard/backend/main.py", "w", encoding="utf-8") as f:
    f.write(c)
print("OK")
