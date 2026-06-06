with open("C:/Dashboard/backend/main.py", "r", encoding="utf-8") as f:
    c = f.read()

idx = c.find("def estoque_sintetico(")
end = c.find("\n@app.get", idx)

new = '''def estoque_sintetico(data_inicio: str = "2024-01-01", data_fim: str = ""):
    from datetime import datetime
    fim = data_fim if data_fim else datetime.now().strftime("%Y-%m-%d")

    # Busca movimentacoes do periodo por grupo
    mov = query(f"""
        SELECT
            RTRIM(mat.MAT_GMM_COD)                                          AS grupo_cod,
            SUM(CASE WHEN mma.MMA_TIPO_ES='E' THEN mma.MMA_QTD   ELSE 0 END) AS qtd_entradas,
            SUM(CASE WHEN mma.MMA_TIPO_ES='E' THEN mma.MMA_VALOR ELSE 0 END) AS val_entradas,
            SUM(CASE WHEN mma.MMA_TIPO_ES='S' THEN mma.MMA_QTD   ELSE 0 END) AS qtd_saidas,
            SUM(CASE WHEN mma.MMA_TIPO_ES='S' THEN mma.MMA_VALOR ELSE 0 END) AS val_saidas,
            COUNT(DISTINCT mma.MMA_MAT_COD)                                 AS itens_mov
        FROM MMA mma
        JOIN MAT mat ON mat.MAT_COD = mma.MMA_MAT_COD AND mat.MAT_DEL_LOGICA <> 'S'
        WHERE mma.MMA_DATA_MOV BETWEEN '{data_inicio}' AND '{fim} 23:59:59'
          AND mma.MMA_IND_CANCELADA <> 'S'
        GROUP BY RTRIM(mat.MAT_GMM_COD)
    """)
    mov_map = {r["grupo_cod"].strip(): r for r in mov}

    # Saldo atual por grupo (posicao atual no MAT)
    saldos = query("""
        SELECT
            RTRIM(mat.MAT_GMM_COD)                          AS grupo_cod,
            COUNT(DISTINCT mat.MAT_COD)                     AS total_itens,
            SUM(CASE WHEN mat.MAT_QT_EST_ATUAL > 0
                     THEN mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM
                     ELSE 0 END)                            AS saldo_atual
        FROM MAT mat
        WHERE mat.MAT_DEL_LOGICA <> 'S'
        GROUP BY RTRIM(mat.MAT_GMM_COD)
    """)
    saldo_map = {r["grupo_cod"].strip(): r for r in saldos}

    # Grupos
    grupos = query("""
        SELECT RTRIM(GMM_COD) AS grupo_cod, RTRIM(GMM_NOME) AS grupo_nome
        FROM GMM WHERE RTRIM(GMM_COD) <> '0'
        ORDER BY GMM_NOME
    """)

    result = []
    for g in grupos:
        cod = g["grupo_cod"].strip()
        m = mov_map.get(cod, {})
        s = saldo_map.get(cod, {})
        if not m and not s.get("saldo_atual"):
            continue
        result.append({
            "grupo_cod":    cod,
            "grupo_nome":   g["grupo_nome"],
            "total_itens":  s.get("total_itens", 0),
            "saldo_atual":  round(s.get("saldo_atual") or 0, 2),
            "entradas":     round(m.get("val_entradas") or 0, 2),
            "saidas":       round(m.get("val_saidas")   or 0, 2),
            "qtd_entradas": m.get("qtd_entradas") or 0,
            "qtd_saidas":   m.get("qtd_saidas")   or 0,
        })

    result.sort(key=lambda x: x["grupo_nome"])
    return {
        "grupos": result,
        "totais": {
            "entradas":    round(sum(r["entradas"]    for r in result), 2),
            "saidas":      round(sum(r["saidas"]      for r in result), 2),
            "saldo_atual": round(sum(r["saldo_atual"] for r in result), 2),
        },
        "periodo": {"inicio": data_inicio, "fim": fim}
    }

'''

c = c[:idx] + new + c[end:]
with open("C:/Dashboard/backend/main.py", "w", encoding="utf-8") as f:
    f.write(c)
print("OK")
