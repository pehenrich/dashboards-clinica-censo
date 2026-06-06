from main import query, periodo_datas
inicio, fim = periodo_datas("30d")
r = query(f"""
    SELECT COUNT(*) as total FROM MAT mat
    WHERE mat.MAT_DEL_LOGICA <> \'S\'
      AND mat.MAT_QT_EST_ATUAL > 0
      AND EXISTS (
          SELECT 1 FROM MMA
          WHERE MMA_MAT_COD = mat.MAT_COD
            AND MMA_DATA_MOV >= \'2024-01-01\'
            AND MMA_IND_CANCELADA <> \'S\'
      )
""")
print(r)
