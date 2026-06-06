with open("C:/Dashboard/backend/main.py", "r", encoding="utf-8") as f:
    c = f.read()

old = "          AND RTRIM(smm.SMM_ESP) IN ('CLI','PED','ORT','CAR','DER','GIN','RUM','GAS','URO','PNE','END','OFT','CIR','VAR','PRO','ANE','HAM','INF','MAM','MAS')"
new = "          AND RTRIM(smk.SMK_CTF) IN ('39', 'CONS')"

# Need to also add the JOIN
old2 = "        LEFT JOIN esp ON esp.esp_cod = smm.SMM_ESP\n        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'\n          AND osm.osm_atend IN ('ASS','EME','CRG','TAM')\n          AND smm.SMM_SFAT IN ('A','F','P')\n          AND RTRIM(smm.SMM_ESP) IN ('CLI','PED','ORT','CAR','DER','GIN','RUM','GAS','URO','PNE','END','OFT','CIR','VAR','PRO','ANE','HAM','INF','MAM','MAS')"
new2 = "        LEFT JOIN esp ON esp.esp_cod = smm.SMM_ESP\n        JOIN smk ON smk.SMK_TIPO = smm.SMM_TPCOD AND smk.SMK_COD = smm.SMM_COD\n        WHERE osm.osm_dthr BETWEEN '{inicio}' AND '{fim} 23:59:59'\n          AND osm.osm_atend IN ('ASS','EME','CRG','TAM')\n          AND smm.SMM_SFAT IN ('A','F','P')\n          AND RTRIM(smk.SMK_CTF) IN ('39', 'CONS')"

if old2 in c:
    c = c.replace(old2, new2)
    with open("C:/Dashboard/backend/main.py", "w", encoding="utf-8") as f:
        f.write(c)
    print("OK")
else:
    print("NAO ENCONTRADO")
    idx = c.find("SMM_ESP) IN ('CLI'")
    print(repr(c[max(0,idx-200):idx+100]))
