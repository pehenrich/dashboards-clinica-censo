with open("C:/Dashboard/backend/whatsapp_sender.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find and remove the Producao do Mes block from montar_manha
remove_start = None
remove_end = None
for i, l in enumerate(lines):
    if '    msg += n + "*Producao do Mes*" + n' in l and remove_start is None:
        remove_start = i
    if remove_start and '    return msg' in l:
        remove_end = i
        break

print(f"Remove lines {remove_start+1} to {remove_end}")
prod_mes_block = "".join(lines[remove_start:remove_end])
print("Block:", prod_mes_block[:100])

# Remove from montar_manha
lines = lines[:remove_start] + lines[remove_end:]

# Find montar_fechamento return msg and insert before it
for i, l in enumerate(lines):
    if '    msg += n + "_Dashboard Clinica - " + datetime.now().strftime("%H:%M") + "_"' in l:
        if i > 400:  # make sure it is in montar_fechamento
            lines.insert(i, prod_mes_block)
            print(f"Inserted at line {i+1}")
            break

with open("C:/Dashboard/backend/whatsapp_sender.py", "w", encoding="utf-8") as f:
    f.writelines(lines)
print("OK")
