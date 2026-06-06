with open("C:/Dashboard/backend/main.py", "r", encoding="utf-8") as f:
    c = f.read()
from main import query
r = query("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'smk' ORDER BY ORDINAL_POSITION")
for x in r: print(x)
