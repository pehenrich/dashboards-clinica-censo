from main import query
r = query("SELECT TOP 1 INV_NUM, INV_DATA, INV_DT_CONTAGEM FROM INV ORDER BY INV_DATA DESC")
print(r)
