with open("C:/Dashboard/backend/main.py", "r", encoding="utf-8") as f:
    c = f.read()

idx = c.find("def estoque_sintetico(")
end = c.find("\n@app.get", idx)

new = '''def estoque_sintetico(data_inicio: str = "2024-01-01", data_fim: str = ""):
    from datetime import datetime
    fim = data_fim if data_fim else datetime.now().strftime("%Y-%m-%d")

    # Saldo correto = entradas - saidas no periodo (acumulado desde o inicio do sistema)
    # Saldo fim periodo = saldo antes do periodo + entradas no periodo - saidas no periodo
    rows = query(f"""
        SELECT
            RTRIM(gmm.GMM_COD)                                              AS grupo_cod,
            RTRIM(gmm.GMM_NOME)                                             AS grupo_nome,
            COUNT(DISTINCT mat.MAT_COD)                                     AS total_itens,
            -- Saldo antes do periodo (entradas - saidas ate a data de inicio)
            ISNULL(SUM(CASE WHEN ant.MMA_TIPO_ES='E' THEN ant.MMA_VALOR
                            WHEN ant.MMA_TIPO_ES='S' THEN -ant.MMA_VALOR
                            ELSE 0 END), 0)                                 AS sld_mes_ant,
            -- Entradas no periodo
            ISNULL(SUM(CASE WHEN per.MMA_TIPO_ES='E' THEN per.MMA_VALOR ELSE 0 END), 0) AS entradas,
            -- Saidas no periodo
            ISNULL(SUM(CASE WHEN per.MMA_TIPO_ES='S' THEN per.MMA_VALOR ELSE 0 END), 0) AS saidas
        FROM GMM gmm
        JOIN MAT mat ON RTRIM(mat.MAT_GMM_COD) = RTRIM(gmm.GMM_COD)
                     AND mat.MAT_DEL_LOGICA <> 'S'
        -- Movimentacoes antes do periodo
        LEFT JOIN MMA ant ON ant.MMA_MAT_COD = mat.MAT_COD
                          AND ant.MMA_DATA_MOV < '{data_inicio}'
                          AND ant.MMA_IND_CANCELADA <> 'S'
        -- Movimentacoes no periodo
        LEFT JOIN MMA per ON per.MMA_MAT_COD = mat.MAT_COD
                          AND per.MMA_DATA_MOV BETWEEN '{data_inicio}' AND '{fim} 23:59:59'
                          AND per.MMA_IND_CANCELADA <> 'S'
        WHERE RTRIM(gmm.GMM_COD) <> '0'
          AND (ant.MMA_MAT_COD IS NOT NULL OR per.MMA_MAT_COD IS NOT NULL)
        GROUP BY RTRIM(gmm.GMM_COD), RTRIM(gmm.GMM_NOME)
        ORDER BY grupo_nome
    """)

    # saldo_atual = sld_mes_ant + entradas - saidas
    for r in rows:
        r["saldo_atual"] = round(
            (r.get("sld_mes_ant") or 0) +
            (r.get("entradas")    or 0) -
            (r.get("saidas")      or 0), 2
        )

    return {
        "grupos": rows,
        "totais": {
            "sld_mes_ant": round(sum(r.get("sld_mes_ant") or 0 for r in rows), 2),
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
