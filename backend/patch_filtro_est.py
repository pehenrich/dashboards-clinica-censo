with open("C:/Dashboard/backend/main.py", "r", encoding="utf-8") as f:
    c = f.read()

# 1. Add data_fim_est param to estoque_resumo
c = c.replace(
    'def estoque_resumo(periodo: str = "30d", data_inicio: str = "2026-01-02"):',
    'def estoque_resumo(periodo: str = "30d", data_inicio: str = "2026-01-02", data_fim_est: str = ""):'
)

# 2. Add fim_est calculation after periodo_datas in estoque_resumo
old_block = "    inicio, fim = periodo_datas(periodo)\n    kpis = query(f\"\"\""
new_block = """    inicio, fim = periodo_datas(periodo)
    from datetime import datetime as _dt
    fim_est = data_fim_est if data_fim_est else _dt.now().strftime("%Y-%m-%d")
    kpis = query(f\"\"\""""
c = c.replace(old_block, new_block, 1)

# 3. Update EXISTS filter to use data_inicio and fim_est
old_exists = """          AND EXISTS (
              SELECT 1 FROM MMA
              WHERE MMA_MAT_COD = mat.MAT_COD
                AND MMA_TIPO_ES = 'E'
                AND MMA_DATA_MOV >= '{data_inicio}'
                AND MMA_IND_CANCELADA <> 'S'
          )"""
new_exists = """          AND EXISTS (
              SELECT 1 FROM MMA
              WHERE MMA_MAT_COD = mat.MAT_COD
                AND MMA_DATA_MOV BETWEEN '{data_inicio}' AND '{fim_est} 23:59:59'
                AND MMA_IND_CANCELADA <> 'S'
          )"""
c = c.replace(old_exists, new_exists)

# 4. Update movs query to use data_inicio and fim_est
old_movs = "        WHERE MMA_DATA_MOV BETWEEN '{inicio}' AND '{fim} 23:59:59'\n          AND MMA_IND_CANCELADA <> 'S'"
new_movs = "        WHERE MMA_DATA_MOV BETWEEN '{data_inicio}' AND '{fim_est} 23:59:59'\n          AND MMA_IND_CANCELADA <> 'S'"
# Only replace inside estoque_resumo
idx = c.find("def estoque_resumo(")
end = c.find("\n@app.get", idx)
section = c[idx:end].replace(old_movs, new_movs)
c = c[:idx] + section + c[end:]

with open("C:/Dashboard/backend/main.py", "w", encoding="utf-8") as f:
    f.write(c)
print("OK")
print("data_fim_est:", c.count("data_fim_est"))
print("fim_est:", c.count("fim_est"))
