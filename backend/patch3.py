with open("C:/Dashboard/backend/main.py", "r", encoding="utf-8") as f:
    c = f.read()

idx = c.find("def estoque_resumo(periodo")
end = c.find("\n@app", idx)
old = c[idx:end]

new = '''def estoque_resumo(periodo: str = "30d", data_inicio: str = "2024-01-01"):
    inicio, fim = periodo_datas(periodo)
    kpis = query(f"""
        SELECT
            COUNT(DISTINCT mat.MAT_COD) AS total_itens,
            SUM(CASE WHEN mat.MAT_QT_EST_ATUAL > 0 THEN 1 ELSE 0 END) AS com_estoque,
            SUM(CASE WHEN mat.MAT_QT_EST_ATUAL = 0 THEN 1 ELSE 0 END) AS zerados,
            SUM(CASE WHEN mat.MAT_PT_RESSUPRIMENTO > 0 AND mat.MAT_QT_EST_ATUAL <= mat.MAT_PT_RESSUPRIMENTO THEN 1 ELSE 0 END) AS abaixo_minimo,
            SUM(mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM) AS valor_total,
            SUM(CASE WHEN mat.MAT_IND_CURVA_ABC=\'A\' THEN mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM ELSE 0 END) AS valor_curva_a,
            SUM(CASE WHEN mat.MAT_IND_CURVA_ABC=\'B\' THEN mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM ELSE 0 END) AS valor_curva_b,
            SUM(CASE WHEN mat.MAT_IND_CURVA_ABC=\'C\' THEN mat.MAT_QT_EST_ATUAL * mat.MAT_VLR_PM ELSE 0 END) AS valor_curva_c
        FROM MAT mat
        WHERE mat.MAT_DEL_LOGICA <> \'S\'
          AND mat.MAT_QT_EST_ATUAL > 0
          AND EXISTS (
              SELECT 1 FROM MMA
              WHERE MMA_MAT_COD = mat.MAT_COD
                AND MMA_DATA_MOV >= \'{data_inicio}\'
                AND MMA_IND_CANCELADA <> \'S\'
          )
    """)
'''

c = c[:idx] + new + c[end:]
with open("C:/Dashboard/backend/main.py", "w", encoding="utf-8") as f:
    f.write(c)
print("OK")
