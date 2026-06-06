from main import query, periodo_datas
inicio, fim = periodo_datas('30d')
r = query("SELECT TOP 10 ISNULL(RTRIM(med.psv_apel), RTRIM(med.psv_nome)) AS medico, COUNT(*) as qtd, SUM(smm.SMM_VLR) as valor FROM smm JOIN osm ON osm.osm_serie=smm.SMM_OSM_SERIE AND osm.osm_num=smm.SMM_OSM JOIN psv med ON med.psv_cod=smm.SMM_MED LEFT JOIN esp ON esp.esp_cod=smm.SMM_ESP WHERE osm.osm_dthr BETWEEN '" + inicio + "' AND '" + fim + " 23:59:59' AND osm.osm_atend IN ('ASS','EME','CRG','TAM') AND smm.SMM_SFAT IN ('A','F','P') AND RTRIM(smm.SMM_ESP)='CLI' GROUP BY ISNULL(RTRIM(med.psv_apel), RTRIM(med.psv_nome)) ORDER BY qtd DESC")
for x in r: print(x)
