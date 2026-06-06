with open("C:/Dashboard/backend/whatsapp_sender.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find montar_manha and check if prod_mes is declared there
in_manha = False
manha_start = 0
for i, l in enumerate(lines):
    if "def montar_manha(" in l:
        in_manha = True
        manha_start = i
    if in_manha and "prod_mes" in l and "dados.get" in l:
        print(f"Found prod_mes in montar_manha at line {i+1}: {repr(l)}")
        break
    if in_manha and i > manha_start + 5 and l.startswith("def "):
        print(f"prod_mes NOT found in montar_manha (ends at line {i+1})")
        break
