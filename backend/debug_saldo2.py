from main import query
r = query("""
    SELECT 
        SUM(CASE WHEN MMA_TIPO_ES='E' THEN MMA_VALOR ELSE -MMA_VALOR END) AS saldo_periodo
    FROM MMA
    WHERE MMA_DATA_MOV >= '2026-01-02'
      AND MMA_IND_CANCELADA <> 'S'
""")
print("Saldo desde inventario:", r)
