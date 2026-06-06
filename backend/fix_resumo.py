with open("C:/Dashboard/backend/main.py", "r", encoding="utf-8") as f:
    c = f.read()

old = "                AND MMA_IND_CANCELADA <> 'S'\n          )\n    \"\"\")\n@app.get(\"/api/estoque/posicao\")"

new = """                AND MMA_IND_CANCELADA <> 'S'
          )
    \"\"\")

    kpi = kpis[0] if kpis else {}
    movs = query(f\"\"\"
        SELECT
            SUM(CASE WHEN MMA_TIPO_ES='E' THEN MMA_QTD   ELSE 0 END) AS qtd_entradas,
            SUM(CASE WHEN MMA_TIPO_ES='E' THEN MMA_VALOR ELSE 0 END) AS valor_entradas,
            SUM(CASE WHEN MMA_TIPO_ES='S' THEN MMA_QTD   ELSE 0 END) AS qtd_saidas,
            SUM(CASE WHEN MMA_TIPO_ES='S' THEN MMA_VALOR ELSE 0 END) AS valor_saidas,
            COUNT(DISTINCT MMA_MAT_COD) AS materiais_movimentados
        FROM MMA
        WHERE MMA_DATA_MOV BETWEEN '{inicio}' AND '{fim} 23:59:59'
          AND MMA_IND_CANCELADA <> 'S'
    \"\"\")
    mov = movs[0] if movs else {}
    return {
        "total_itens": kpi.get("total_itens") or 0,
        "com_estoque": kpi.get("com_estoque") or 0,
        "zerados": kpi.get("zerados") or 0,
        "abaixo_minimo": kpi.get("abaixo_minimo") or 0,
        "valor_total": float(kpi.get("valor_total") or 0),
        "valor_curva_a": float(kpi.get("valor_curva_a") or 0),
        "valor_curva_b": float(kpi.get("valor_curva_b") or 0),
        "valor_curva_c": float(kpi.get("valor_curva_c") or 0),
        "qtd_entradas": float(mov.get("qtd_entradas") or 0),
        "qtd_saidas": float(mov.get("qtd_saidas") or 0),
        "valor_entradas": float(mov.get("valor_entradas") or 0),
        "valor_saidas": float(mov.get("valor_saidas") or 0),
        "materiais_movimentados": mov.get("materiais_movimentados") or 0,
        "periodo_inicio": inicio,
        "periodo_fim": fim,
        "vence_30d": 0, "vence_60d": 0, "vence_90d": 0, "vencidos": 0,
    }

@app.get(\"/api/estoque/posicao\")"""

if old in c:
    c = c.replace(old, new)
    with open("C:/Dashboard/backend/main.py", "w", encoding="utf-8") as f:
        f.write(c)
    print("OK")
else:
    print("NAO ENCONTRADO - check quotes")
    idx = c.find("AND MMA_IND_CANCELADA <> ")
    print(repr(c[idx:idx+100]))
