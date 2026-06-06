with open("C:/Dashboard/backend/main.py", "r", encoding="utf-8") as f:
    c = f.read()

idx = c.find("AND MMA_IND_CANCELADA <> \\'S\\'\n          )\n    \"\"\")\n\n@app.get(\"/api/estoque/posicao\")")
print("idx:", idx)
print(repr(c[idx:idx+80]))
