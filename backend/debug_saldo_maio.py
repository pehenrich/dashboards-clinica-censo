from main import query
# Calcular saldo fim de abril (= saldo inicio de maio) pela MMA
r = query("""
    SELECT 
        RTRIM(mat.MAT_GMM_COD) AS grupo,
        SUM(CASE WHEN mma.MMA_TIPO_ES=\'E\' THEN mma.MMA_VALOR ELSE -mma.MMA_VALOR END) AS saldo_acum
    FROM MMA mma
    JOIN MAT mat ON mat.MAT_COD = mma.MMA_MAT_COD AND mat.MAT_DEL_LOGICA <> \'S\'
    WHERE mma.MMA_DATA_MOV < \'2026-05-01\'
      AND mma.MMA_IND_CANCELADA <> \'S\'
    GROUP BY RTRIM(mat.MAT_GMM_COD)
    ORDER BY grupo
""")
total = sum(x["saldo_acum"] or 0 for x in r)
print(f"Total saldo antes de maio: R$ {total:,.2f}")
print("Esperado pelo PDF: R$ 24.690,20")
for x in r: print(x)
