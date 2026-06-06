from main import query
import sys
sys.path.insert(0, "C:/Dashboard/backend")
r = query("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE '%SALDO%' OR TABLE_NAME LIKE '%FECH%' OR TABLE_NAME LIKE '%BALAN%' OR TABLE_NAME LIKE '%INV%' OR TABLE_NAME LIKE '%EST_MES%' ORDER BY TABLE_NAME")
for x in r: print(x)
