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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeoutError

# Adiciona o diretório do backend ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importa as funções necessárias
from whatsapp_sender import enviar_resumo, buscar_producao_hoje, enviar_meta_atingida, enviar_arquivo_whatsapp
from email_sender import enviar_email

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whatsapp_config.json")

# Pool dedicado pra chamadas de envio -- protege o laço principal do
# scheduler contra travar pra sempre se uma chamada de rede (WPPConnect)
# ficar pendurada sem retornar (já aconteceu: erro "[Errno 22]" intermitente
# no Windows deixou a thread do scheduler travada por horas sem nenhum ciclo).
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wpp-send")

def _com_timeout(func, timeout, *args, **kwargs):
    """Roda func num worker à parte; se não voltar dentro do timeout, desiste
    e segue o laço do scheduler (o worker pode ficar pendurado sozinho, mas
    não trava mais os próximos ciclos de 30s)."""
    future = _pool.submit(func, *args, **kwargs)
    return future.result(timeout=timeout)


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

_EMAILS_RELATORIO_SEMANAL = ["paulo.czrnhak@icds.org.br", "adailson.araujo@icds.org.br"]


def _corpo_email_relatorio_semanal(inicio_iso, fim_iso):
    inicio_br = f"{inicio_iso[8:10]}/{inicio_iso[5:7]}/{inicio_iso[0:4]}"
    fim_br = f"{fim_iso[8:10]}/{fim_iso[5:7]}/{fim_iso[0:4]}"
    return (
        "Prezados Sr. Paulo Czrnhak e Sr. Adailson Silva,\n\n"
        f"Encaminhamos o relatório semanal de previsão de agendamentos da Clínica Censo, "
        f"referente ao período de {inicio_br} a {fim_br}.\n\n"
        "O documento em anexo apresenta a quantidade de agendamentos por médico, distribuída "
        "por dia da semana e por turno (manhã/tarde), a previsão de produção da semana com base "
        "nos agendamentos confirmados, e a média de produção das últimas semanas, para fins de "
        "acompanhamento e planejamento.\n\n"
        "Este e-mail é enviado de forma automática. Havendo dúvidas ou necessidade de ajustes, "
        "permanecemos à disposição.\n\n"
        "Atenciosamente,\n"
        "Coordenação de Tecnologia da Informação e Inovação - Clínica Censo"
    )


def _enviar_relatorio_semanal_agenda(numero):
    """Gera o PDF visual da agenda da semana por médico e manda por WhatsApp
    (arquivo) e e-mail (anexo, linguagem formal para diretoria/gerência) —
    disparado toda segunda de manhã."""
    from main import gerar_pdf_agenda_semanal, agenda_semanal_por_medico  # import tardio: evita ciclo (main.py importa scheduler no startup)

    dados = agenda_semanal_por_medico()
    pdf_path = gerar_pdf_agenda_semanal()
    try:
        resultado_wpp = enviar_arquivo_whatsapp(pdf_path, "📅 Agenda da semana por médico", numeros=numero)
        resultado_email = enviar_email(
            _EMAILS_RELATORIO_SEMANAL,
            "Relatório Semanal de Previsão de Agendamentos — Clínica Censo",
            _corpo_email_relatorio_semanal(dados["inicio"], dados["fim"]),
            anexo_path=pdf_path,
        )
        return {"whatsapp": resultado_wpp, "email": resultado_email}
    finally:
        try: os.remove(pdf_path)
        except OSError: pass


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
                log.info(f"Disparando turno={turno} numero={numero}")
                print(f"[Scheduler] {agora.strftime('%H:%M')} — disparando {turno}")
                try:
                    resultado = _com_timeout(enviar_resumo, 60, _query_func, turno=turno, numero=numero)
                    log.info(f"Envio ok: {resultado}")
                    print(f"[Scheduler] Envio ok")
                    # So marca como enviado se TODAS as mensagens do turno saírem
                    # com sucesso -- uma falha transitoria (ex: token WPPConnect
                    # expirado logo apos restart) tenta de novo no proximo ciclo
                    # (30s) em vez de perder o envio do dia. Turno "fechamento"
                    # manda duas mensagens (fechamento + previa), "manha" so uma.
                    if "envio" in resultado:
                        envios = [resultado["envio"]]
                    else:
                        envios = [resultado[k]["envio"] for k in ("fechamento", "previa") if k in resultado]
                    if envios and all(e.get("ok") for e in envios):
                        ultimo_envio[chave] = True
                except _FutureTimeoutError:
                    log.error("Erro no envio: timeout (>60s), tentando de novo no proximo ciclo")
                    print("[Scheduler] Erro: timeout no envio")
                except Exception as e:
                    log.error(f"Erro no envio: {e}")
                    print(f"[Scheduler] Erro: {e}")

        # ── Aviso de meta do dia/sábado batida — dispara uma vez, assim que a
        # produção acumulada de hoje alcança a meta configurada ────────────────
        if not eh_domingo:
            chave_meta = f"{agora.strftime('%Y-%m-%d')}-meta"
            if chave_meta not in ultimo_envio:
                try:
                    dados_meta = _com_timeout(buscar_producao_hoje, 60, _query_func)
                    if dados_meta["meta"] > 0 and dados_meta["producao"] >= dados_meta["meta"]:
                        log.info(f"Meta batida: producao={dados_meta['producao']} meta={dados_meta['meta']}")
                        print(f"[Scheduler] {agora.strftime('%H:%M')} — meta do dia batida, disparando aviso")
                        resultado = _com_timeout(enviar_meta_atingida, 60, _query_func, numero=numero)
                        log.info(f"Envio meta ok: {resultado['envio']}")
                        # So marca como enviado depois de confirmar sucesso -- senao uma
                        # falha transitoria (ex: token WPPConnect expirado) perde o aviso
                        # pro resto do dia, sem tentar de novo no proximo ciclo (30s).
                        if resultado["envio"]["ok"]:
                            ultimo_envio[chave_meta] = True
                except _FutureTimeoutError:
                    log.error("Erro ao verificar meta: timeout (>60s), tentando de novo no proximo ciclo")
                    print("[Scheduler] Erro ao verificar meta: timeout")
                except Exception as e:
                    log.error(f"Erro ao verificar meta: {e}")
                    print(f"[Scheduler] Erro ao verificar meta: {e}")

        # ── Relatório semanal (agenda por médico) — toda segunda de manhã ──────
        eh_segunda = dia_semana == 0
        if eh_segunda:
            chave_semanal = f"{agora.strftime('%Y-%m-%d')}-agenda-semanal"
            if chave_semanal not in ultimo_envio and agora.hour == 7 and agora.minute == 30:
                try:
                    log.info("Disparando relatorio semanal de agenda por medico")
                    print(f"[Scheduler] {agora.strftime('%H:%M')} — disparando relatório semanal de agenda")
                    resultado = _com_timeout(_enviar_relatorio_semanal_agenda, 90, numero)
                    log.info(f"Relatorio semanal: {resultado}")
                    if resultado["whatsapp"].get("ok") or resultado["email"].get("ok"):
                        ultimo_envio[chave_semanal] = True
                except _FutureTimeoutError:
                    log.error("Erro no relatorio semanal: timeout (>90s), tentando de novo no proximo ciclo")
                    print("[Scheduler] Erro: timeout no relatorio semanal")
                except Exception as e:
                    log.error(f"Erro no relatorio semanal: {e}")
                    print(f"[Scheduler] Erro no relatorio semanal: {e}")

        # ── Bot de agenda por especialidade (WhatsApp) — roda todo ciclo se
        # AGENDA_BOT_GRUPO_ID estiver configurado no .env ────────────────────
        grupo_agenda_bot = os.environ.get("AGENDA_BOT_GRUPO_ID", "").strip()
        if grupo_agenda_bot:
            try:
                from agenda_bot import checar_agenda_bot
                status, tempo_ms, detalhe = _com_timeout(checar_agenda_bot, 30, grupo_agenda_bot)
                if status == "down":
                    log.error(f"Erro no agenda_bot: {detalhe}")
            except _FutureTimeoutError:
                log.error("Erro no agenda_bot: timeout (>30s)")
            except Exception as e:
                log.error(f"Erro no agenda_bot: {e}")

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
