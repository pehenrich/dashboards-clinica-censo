from main import query, periodo_datas
inicio, fim = periodo_datas('30d')
r = query("SELECT TOP 10 RTRIM(smm.SMM_ESP) as esp, RTRIM(esp.esp_nome) as nome, COUNT(*) as qtd FROM smm JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM LEFT JOIN esp ON esp.esp_cod=smm.SMM_ESP WHERE osm.osm_dthr BETWEEN '" + inicio + "' AND '" + fim + " 23:59:59' AND osm.osm_atend IN ('ASS','EME','CRG','TAM') AND smm.SMM_SFAT IN ('A','F','P') GROUP BY RTRIM(smm.SMM_ESP), RTRIM(esp.esp_nome) ORDER BY qtd DESC")
for x in r: print(x)
