with open("C:/Dashboard/backend/main.py", "r", encoding="utf-8") as f:
    c = f.read()

c = c.replace(
    "('CLI','PED','ORT','CAR','DER','NEU','GIN','NRO','PSQ','RUM','GAS','URO','PNE','END','OFT','CIR','VAR','PRO','ANE','HAM','INF','MAM','MAS')",
    "('CLI','PED','ORT','CAR','DER','GIN','RUM','GAS','URO','PNE','END','OFT','CIR','VAR','PRO','ANE','HAM','INF','MAM','MAS')"
)
c = c.replace(
    "('PSC','NUT','FON','ENF','FIS','TER','FAR','ASS','SOC')",
    "('PSC','NUT','ENF','FIS','TER','FAR','ASS','SOC')"
)

with open("C:/Dashboard/backend/main.py", "w", encoding="utf-8") as f:
    f.write(c)
print("OK - NEU e FON removidos do assistencial")
