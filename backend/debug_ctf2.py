from main import query
r = query("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME IN ('ctf','smk_ctf','ctf_smk') ORDER BY TABLE_NAME, ORDINAL_POSITION")
for x in r: print(x)
r2 = query("SELECT TOP 5 * FROM ctf")
for x in r2: print(x)
