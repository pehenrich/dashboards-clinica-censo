with open("C:/Dashboard/backend/main.py", "r", encoding="utf-8") as f:
    c = f.read()

idx = c.find("def estoque_sintetico(")
end = c.find("\n@app.get", idx)

new = '''def estoque_sintetico(data_inicio: str = "2024-01-01", data_fim: str = ""):
    from datetime import datetime
    fim = data_fim if data_fim else datetime.now().strftime("%Y-%m-%d")

    # Movimentacoes do periodo por grupo
    rows = query(f"""
        SELECT
            RTRIM(gmm.GMM_COD)                                              AS grupo_cod,
            RTRIM(gmm.GMM_NOME)                                             AS grupo_nome,
            COUNT(DISTINCT mat.MAT_COD)                                     AS total_itens,
            -- Saldo atual somente dos itens que tiveram movimentacao no periodo
            SUM(CASE WHEN mat.MAT_QT_EST_ATUAL > 0
                     THEN mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM
                     ELSE 0 END)                                            AS saldo_atual,
            SUM(CASE WHEN mma.MMA_TIPO_ES='E' THEN mma.MMA_VALOR ELSE 0 END) AS entradas,
            SUM(CASE WHEN mma.MMA_TIPO_ES='S' THEN mma.MMA_VALOR ELSE 0 END) AS saidas,
            SUM(CASE WHEN mma.MMA_TIPO_ES='E' THEN mma.MMA_QTD   ELSE 0 END) AS qtd_entradas,
            SUM(CASE WHEN mma.MMA_TIPO_ES='S' THEN mma.MMA_QTD   ELSE 0 END) AS qtd_saidas
        FROM MMA mma
        JOIN MAT mat ON mat.MAT_COD = mma.MMA_MAT_COD
                     AND mat.MAT_DEL_LOGICA <> 'S'
        JOIN GMM gmm ON RTRIM(gmm.GMM_COD) = RTRIM(mat.MAT_GMM_COD)
        WHERE mma.MMA_DATA_MOV BETWEEN '{data_inicio}' AND '{fim} 23:59:59'
          AND mma.MMA_IND_CANCELADA <> 'S'
          AND RTRIM(gmm.GMM_COD) <> '0'
        GROUP BY RTRIM(gmm.GMM_COD), RTRIM(gmm.GMM_NOME)
        ORDER BY grupo_nome
    """)

    for r in rows:
        for k in ["saldo_atual","entradas","saidas"]:
            if r.get(k) is not None:
                r[k] = round(float(r[k]), 2)

    return {
        "grupos": rows,
        "totais": {
            "entradas":    round(sum(r.get("entradas")    or 0 for r in rows), 2),
            "saidas":      round(sum(r.get("saidas")      or 0 for r in rows), 2),
            "saldo_atual": round(sum(r.get("saldo_atual") or 0 for r in rows), 2),
        },
        "periodo": {"inicio": data_inicio, "fim": fim}
    }

'''

c = c[:idx] + new + c[end:]
with open("C:/Dashboard/backend/main.py", "w", encoding="utf-8") as f:
    f.write(c)
print("OK")
