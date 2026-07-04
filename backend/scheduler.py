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
import json

# Adiciona o diretório do backend ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importa as funções necessárias
from whatsapp_sender import enviar_resumo

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whatsapp_config.json")


def _carregar_config_wpp():
    """Lê whatsapp_config.json a cada verificação — assim mudanças feitas na
    tela de configuração (número de destino, horários) valem sem precisar
    reiniciar o backend."""
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _parse_hhmm(hhmm, default):
    try:
        h, m = str(hhmm).split(":")
        return int(h), int(m)
    except Exception:
        return default


def _horarios_configurados(cfg):
    """Horários de envio (hora, minuto, turno), lidos de whatsapp_config.json
    — cai para 07:00/17:00 se não houver configuração salva."""
    h_manha, m_manha = _parse_hhmm(cfg.get("horario_manha"), (7, 0))
    h_tarde, m_tarde = _parse_hhmm(cfg.get("horario_tarde"), (17, 0))
    return [
        (h_manha, m_manha, "manha"),
        (h_tarde, m_tarde, "fechamento"),
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

    cfg = _carregar_config_wpp()
    numero = cfg.get("numeros_destino") or None
    agora = datetime.now()
    for hora, minuto, turno in _horarios_configurados(cfg):
        if agora.hour == hora and agora.minute == minuto:
            print(f"[Scheduler] Disparando envio — turno={turno} às {agora.strftime('%H:%M')}")
            try:
                resultado = enviar_resumo(_query_func, turno=turno, numero=numero)
                print(f"[Scheduler] Envio concluído: {resultado['envio']}")
            except Exception as e:
                print(f"[Scheduler] Erro no envio: {e}")

def loop_scheduler():
    import logging
    logging.basicConfig(
        filename="C:\\Dashboard\\backend\\scheduler.log",
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    log = logging.getLogger()
    log.info("Scheduler iniciado.")
    _cfg_inicial = _carregar_config_wpp()
    print(f"[Scheduler] Iniciado. Horários programados: {[f'{h:02d}:{m:02d}' for h,m,_ in _horarios_configurados(_cfg_inicial)]}")
    ultimo_envio = {}

    while True:
        cfg        = _carregar_config_wpp()
        numero     = cfg.get("numeros_destino") or None
        horarios   = _horarios_configurados(cfg)
        agora      = datetime.now()
        dia_semana = agora.weekday()
        eh_domingo = dia_semana == 6
        eh_sabado  = dia_semana == 5

        for hora, minuto, turno in horarios:
            if eh_domingo:
                continue
            if eh_sabado and turno == "fechamento":
                if not (agora.hour == 11 and agora.minute == 30):
                    continue
            elif agora.hour != hora or agora.minute != minuto:
                continue

            chave = f"{agora.strftime('%Y-%m-%d')}-{turno}"
            if chave not in ultimo_envio:
                ultimo_envio[chave] = True
                log.info(f"Disparando turno={turno} numero={numero}")
                print(f"[Scheduler] {agora.strftime('%H:%M')} — disparando {turno}")
                try:
                    resultado = enviar_resumo(_query_func, turno=turno, numero=numero)
                    log.info(f"Envio ok: {resultado}")
                    print(f"[Scheduler] Envio ok")
                except Exception as e:
                    log.error(f"Erro no envio: {e}")
                    print(f"[Scheduler] Erro: {e}")

        hoje = datetime.now().strftime("%Y-%m-%d")
        ultimo_envio = {k: v for k, v in ultimo_envio.items() if k.startswith(hoje)}

        time.sleep(30)  # Verifica a cada 55 segundos

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
