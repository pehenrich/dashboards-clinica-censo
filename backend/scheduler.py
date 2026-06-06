"""
scheduler.py
Agendador de envio automático do resumo via WhatsApp.

Uso:
  python scheduler.py

Roda em background e envia:
  - 08:00 — Resumo da manhã (agenda do dia + movimento inicial)
  - 18:00 — Fechamento do dia (resultado final)

Mantenha este processo rodando junto com o backend.
No Windows, pode usar o Agendador de Tarefas para iniciar automaticamente.
"""

import time
import threading
from datetime import datetime
import sys
import os

# Adiciona o diretório do backend ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importa as funções necessárias
from whatsapp_sender import enviar_resumo

# Horários de envio (hora, minuto, turno)
HORARIOS = [
    (8,  0,  "manha"),       # 08:00 — Resumo da manhã
    (17, 0,  "fechamento"),  # 17:00 — Fechamento + prévia do dia seguinte
]

# Função query — importada do main.py em runtime
_query_func = None

def set_query_func(func):
    global _query_func
    _query_func = func

def verificar_e_enviar():
    """Verifica se é hora de enviar e dispara o envio."""
    global _query_func
    if _query_func is None:
        print("[Scheduler] query_func não configurada ainda.")
        return

    agora = datetime.now()
    for hora, minuto, turno in HORARIOS:
        if agora.hour == hora and agora.minute == minuto:
            print(f"[Scheduler] Disparando envio — turno={turno} às {agora.strftime('%H:%M')}")
            try:
                resultado = enviar_resumo(_query_func, turno=turno)
                print(f"[Scheduler] Envio concluído: {resultado['envio']}")
            except Exception as e:
                print(f"[Scheduler] Erro no envio: {e}")

def loop_scheduler():
    """Loop que verifica a cada 60 segundos."""
    print(f"[Scheduler] Iniciado. Horários programados: {[f'{h:02d}:{m:02d}' for h,m,_ in HORARIOS]}")
    ultimo_envio = {}

    while True:
        agora = datetime.now()
        chave = agora.strftime("%Y-%m-%d-%H-%M")

        # 0=seg, 1=ter, 2=qua, 3=qui, 4=sex, 5=sab, 6=dom
        dia_semana = agora.weekday()
        eh_domingo = dia_semana == 6
        eh_sabado  = dia_semana == 5

        for hora, minuto, turno in HORARIOS:
            # Domingo: não envia nada
            if eh_domingo:
                continue
            # Sábado: manhã normal, fechamento às 11:30
            if eh_sabado and turno == "fechamento":
                if not (agora.hour == 11 and agora.minute == 30):
                    continue
            elif agora.hour != hora or agora.minute != minuto:
                continue

            chave_turno = f"{agora.strftime('%Y-%m-%d')}-{turno}"
            if chave_turno not in ultimo_envio:
                ultimo_envio[chave_turno] = True
                print(f"[Scheduler] {agora.strftime('%H:%M')} — disparando {turno} (dia={dia_semana})")
                threading.Thread(
                    target=lambda t=turno: enviar_resumo(_query_func, turno=t),
                    daemon=True
                ).start()

        time.sleep(55)  # Verifica a cada 55 segundos

def iniciar_scheduler_em_background():
    """Inicia o scheduler em thread de background (chamado pelo main.py)."""
    t = threading.Thread(target=loop_scheduler, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    # Teste standalone — envia imediatamente
    from main import query as q
    set_query_func(q)
    resultado = enviar_resumo(q, turno="manha")
    print("Mensagem gerada:")
    print(resultado["mensagem"])
    print("\nResultado do envio:", resultado["envio"])
