from main import query
from datetime import datetime
r = query("SELECT SUM(CASE WHEN MMA_TIPO_ES=\'E\' THEN MMA_VALOR ELSE -MMA_VALOR END) AS mov_junho FROM MMA WHERE MMA_DATA_MOV >= \'2026-06-01\' AND MMA_IND_CANCELADA <> \'S\'")
print("Movimentacao junho:", r)
r2 = query("SELECT SUM(MAT_QT_EST_ATUAL * MAT_VLR_PM) AS saldo_hoje FROM MAT WHERE MAT_DEL_LOGICA <> \'S\' AND MAT_QT_EST_ATUAL > 0")
print("Saldo hoje:", r2)
