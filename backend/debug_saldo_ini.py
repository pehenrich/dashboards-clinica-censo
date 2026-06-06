from main import query
r = query("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'EXC_SALDO_INI' ORDER BY ORDINAL_POSITION")
print("Columns:", [x["COLUMN_NAME"] for x in r])
r2 = query("SELECT TOP 3 * FROM EXC_SALDO_INI")
for x in r2: print(x)
