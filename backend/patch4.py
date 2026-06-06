with open("C:/Dashboard/backend/main.py", "r", encoding="utf-8") as f:
    c = f.read()

new_endpoints = '''
@app.get("/api/estoque/sintetico")
def estoque_sintetico(data_inicio: str = "2024-01-01", data_fim: str = ""):
    from datetime import datetime
    fim = data_fim if data_fim else datetime.now().strftime("%Y-%m-%d")
    rows = query(f"""
        SELECT
            RTRIM(gmm.GMM_COD) AS grupo_cod,
            RTRIM(gmm.GMM_NOME) AS grupo_nome,
            SUM(mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM) AS saldo_atual,
            ISNULL(SUM(CASE WHEN mma.MMA_TIPO_ES='E' THEN mma.MMA_VALOR ELSE 0 END),0) AS entradas,
            ISNULL(SUM(CASE WHEN mma.MMA_TIPO_ES='S' THEN mma.MMA_VALOR ELSE 0 END),0) AS saidas,
            COUNT(DISTINCT mat.MAT_COD) AS total_itens
        FROM GMM gmm
        LEFT JOIN MAT mat ON mat.MAT_GMM_COD = gmm.GMM_COD AND mat.MAT_DEL_LOGICA <> 'S'
        LEFT JOIN MMA mma ON mma.MMA_MAT_COD = mat.MAT_COD
            AND mma.MMA_DATA_MOV BETWEEN '{data_inicio}' AND '{fim} 23:59:59'
            AND mma.MMA_IND_CANCELADA <> 'S'
        WHERE gmm.GMM_COD <> '0'
        GROUP BY RTRIM(gmm.GMM_COD), RTRIM(gmm.GMM_NOME)
        HAVING COUNT(DISTINCT mat.MAT_COD) > 0
        ORDER BY grupo_nome
    """)
    return {
        "grupos": rows,
        "totais": {
            "entradas":    round(sum(r.get("entradas")    or 0 for r in rows), 2),
            "saidas":      round(sum(r.get("saidas")      or 0 for r in rows), 2),
            "saldo_atual": round(sum(r.get("saldo_atual") or 0 for r in rows), 2),
        },
        "periodo": {"inicio": data_inicio, "fim": fim}
    }


@app.get("/api/estoque/analitico")
def estoque_analitico(data_inicio: str = "2024-01-01", data_fim: str = "",
                      grupo_cod: str = "", busca: str = "", limite: int = 100):
    from datetime import datetime
    fim = data_fim if data_fim else datetime.now().strftime("%Y-%m-%d")
    fg = f"AND RTRIM(mat.MAT_GMM_COD) = '{grupo_cod}'" if grupo_cod else ""
    fb = f"AND RTRIM(mat.MAT_DESC_RESUMIDA) LIKE '%{busca}%'" if busca else ""
    rows = query(f"""
        SELECT TOP {limite}
            RTRIM(gmm.GMM_NOME) AS grupo_nome,
            mat.MAT_COD AS cod,
            RTRIM(mat.MAT_DESC_RESUMIDA) AS descricao,
            mat.MAT_VLR_PM AS pm_atual,
            mat.MAT_QT_EST_ATUAL AS qtd_atual,
            mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM AS saldo_atual,
            ISNULL(SUM(CASE WHEN mma.MMA_TIPO_ES='E' THEN mma.MMA_QTD   ELSE 0 END),0) AS qtd_entradas,
            ISNULL(SUM(CASE WHEN mma.MMA_TIPO_ES='E' THEN mma.MMA_VALOR ELSE 0 END),0) AS val_entradas,
            ISNULL(SUM(CASE WHEN mma.MMA_TIPO_ES='S' THEN mma.MMA_QTD   ELSE 0 END),0) AS qtd_saidas,
            ISNULL(SUM(CASE WHEN mma.MMA_TIPO_ES='S' THEN mma.MMA_VALOR ELSE 0 END),0) AS val_saidas,
            CASE WHEN mat.MAT_QT_EST_ATUAL = 0 THEN 'ZERADO'
                 WHEN mat.MAT_PT_RESSUPRIMENTO > 0
                      AND mat.MAT_QT_EST_ATUAL <= mat.MAT_PT_RESSUPRIMENTO THEN 'CRITICO'
                 ELSE 'NORMAL' END AS status_estoque
        FROM MAT mat
        LEFT JOIN GMM gmm ON RTRIM(gmm.GMM_COD) = RTRIM(mat.MAT_GMM_COD)
        LEFT JOIN MMA mma ON mma.MMA_MAT_COD = mat.MAT_COD
            AND mma.MMA_DATA_MOV BETWEEN '{data_inicio}' AND '{fim} 23:59:59'
            AND mma.MMA_IND_CANCELADA <> 'S'
        WHERE mat.MAT_DEL_LOGICA <> 'S'
          {fg}
          {fb}
        GROUP BY RTRIM(gmm.GMM_NOME), mat.MAT_COD, RTRIM(mat.MAT_DESC_RESUMIDA),
                 mat.MAT_VLR_PM, mat.MAT_QT_EST_ATUAL, mat.MAT_PT_RESSUPRIMENTO
        HAVING mat.MAT_QT_EST_ATUAL > 0
            OR SUM(CASE WHEN mma.MMA_TIPO_ES IS NOT NULL THEN 1 ELSE 0 END) > 0
        ORDER BY saldo_atual DESC
    """)
    return rows

'''

marker = '@app.get("/api/debug/estoque-grupos")'
if marker in c:
    c = c.replace(marker, new_endpoints + marker)
    with open("C:/Dashboard/backend/main.py", "w", encoding="utf-8") as f:
        f.write(c)
    print("OK - endpoints adicionados")
else:
    print("MARKER NOT FOUND")
