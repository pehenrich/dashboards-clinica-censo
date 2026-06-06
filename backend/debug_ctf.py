from main import query
r = query("SELECT DISTINCT SMK_CTF, COUNT(*) as qtd FROM smk GROUP BY SMK_CTF ORDER BY qtd DESC")
for x in r: print(x)
