with open("C:/Dashboard/backend/main.py", "r", encoding="utf-8") as f:
    c = f.read()

c = c.replace('data_inicio: str = "2024-01-01"', 'data_inicio: str = "2026-01-02"')
c = c.replace('def estoque_giro(periodo: str = "30d", limite: int = 50):', 'def estoque_giro(periodo: str = "30d", limite: int = 50, data_inicio: str = "2026-01-02"):')
c = c.replace('def estoque_movimentacoes(periodo: str = "30d", tipo: str = ""):', 'def estoque_movimentacoes(periodo: str = "30d", tipo: str = "", data_inicio: str = "2026-01-02"):')
c = c.replace('def estoque_mov_por_dia(periodo: str = "30d"):', 'def estoque_mov_por_dia(periodo: str = "30d", data_inicio: str = "2026-01-02"):')
c = c.replace('def estoque_por_grupo(periodo: str = "30d"):', 'def estoque_por_grupo(periodo: str = "30d", data_inicio: str = "2026-01-02"):')
c = c.replace('def estoque_por_setor(periodo: str = "30d"):', 'def estoque_por_setor(periodo: str = "30d", data_inicio: str = "2026-01-02"):')
c = c.replace('def estoque_curva_abc():', 'def estoque_curva_abc(data_inicio: str = "2026-01-02"):')

with open("C:/Dashboard/backend/main.py", "w", encoding="utf-8") as f:
    f.write(c)
print("OK:", c.count("2026-01-02"))
