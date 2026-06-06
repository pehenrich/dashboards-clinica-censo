from main import query
r = query("SELECT CTF_TIPO, CTF_COD, CTF_NOME, CTF_CATEG FROM ctf WHERE CTF_NOME LIKE '%Consul%' OR CTF_NOME LIKE '%consul%'")
for x in r: print(x)
