from main import query
r = query("""
    SELECT DISTINCT MMA_TIPO_ES, COUNT(*) as qtd, SUM(MMA_VALOR) as valor
    FROM MMA 
    WHERE MMA_DATA_MOV >= '2026-01-01' AND MMA_DATA_MOV < '2026-01-05'
    GROUP BY MMA_TIPO_ES
    ORDER BY qtd DESC
""")
for x in r: print(x)
