from main import query
# Ver colunas do INV
r = query("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'INV' ORDER BY ORDINAL_POSITION")
print("INV columns:", [x["COLUMN_NAME"] for x in r])
# Ver sample
r2 = query("SELECT TOP 3 * FROM INV")
for x in r2: print(x)
