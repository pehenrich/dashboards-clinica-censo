# -*- coding: utf-8 -*-
"""
Vigia a pasta de rede onde o prontuário escaneado é salvo, identifica
empresa+paciente pelo NOME DO ARQUIVO (padrão fixo "Empresa_NomeDoPaciente.pdf",
acertado com a enfermagem em 23/09/2026 — nunca por OCR/leitura de conteúdo,
que seria mais frágil e arriscado de mandar prontuário de alguém pra empresa
errada) e, quando casa com exatamente uma pendência 'Pendente', sobe pro
Nextcloud, gera o link público e manda por e-mail pra empresa (se o e-mail
dela estiver cadastrado em empresa_contatos).

Casamento é por igualdade exata após normalizar (maiúsculo, sem acento,
espaços colapsados) — 0 ou 2+ pendências batendo NÃO processa automático,
move pra "Revisar" pra alguém conferir manualmente. Prioriza nunca mandar
errado sobre nunca precisar de intervenção manual.

Um erro inesperado em UM arquivo (ex: outro processo pegou o mesmo arquivo
primeiro — aconteceu de verdade testando manualmente em paralelo ao
scheduler em 23/09/2026) não pode abortar o ciclo inteiro — por isso cada
arquivo é processado dentro do próprio try/except, os outros da mesma
varredura continuam normalmente.

Import tardio de nextcloud_sender/email_sender só dentro das funções que
usam (mesmo padrão do resto do projeto — evita ciclo de import com
scheduler.py/main.py).
"""
import os
import re
import shutil
import sqlite3
import unicodedata
from datetime import datetime

PASTA_WATCH = r"\\192.168.1.40\SEDE\Envio de Prontuarios - Nexcloud"
PASTA_PROCESSADOS = os.path.join(PASTA_WATCH, "Processados")
PASTA_REVISAR = os.path.join(PASTA_WATCH, "Revisar")

PRONTUARIOS_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prontuarios.db")


def _get_conn():
    conn = sqlite3.connect(PRONTUARIOS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _normalizar(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", txt).strip().upper()


def _parse_nome_arquivo(nome_arquivo: str):
    """'Empresa_Nome Do Paciente.pdf' -> ('Empresa', 'Nome Do Paciente'), ou
    None se não tiver o separador '_' esperado."""
    base = re.sub(r"\.pdf$", "", nome_arquivo, flags=re.IGNORECASE)
    if "_" not in base:
        return None
    empresa, paciente = base.split("_", 1)
    empresa, paciente = empresa.strip(), paciente.strip()
    if not empresa or not paciente:
        return None
    return empresa, paciente


def _mover(caminho_origem: str, pasta_destino: str):
    if not os.path.exists(caminho_origem):
        return  # outro processo/ciclo já pegou esse arquivo primeiro — não é erro
    os.makedirs(pasta_destino, exist_ok=True)
    destino = os.path.join(pasta_destino, os.path.basename(caminho_origem))
    if os.path.exists(destino):
        raiz, ext = os.path.splitext(destino)
        destino = f"{raiz}_{datetime.now().strftime('%H%M%S')}{ext}"
    try:
        shutil.move(caminho_origem, destino)
    except FileNotFoundError:
        pass  # arquivo sumiu entre o Test e o move (outro ciclo concorrente) — não é erro


def _processar_um_arquivo(nome_arquivo, caminho, pendentes, conn, _log):
    """Retorna True se processou (foi pra Processados), False se foi pra Revisar."""
    parse = _parse_nome_arquivo(nome_arquivo)
    if not parse:
        _log(f"'{nome_arquivo}': nome fora do padrão Empresa_Paciente.pdf — movido pra Revisar")
        _mover(caminho, PASTA_REVISAR)
        return False

    empresa_arq, paciente_arq = parse
    empresa_norm, paciente_norm = _normalizar(empresa_arq), _normalizar(paciente_arq)
    candidatos = [
        p for p in pendentes
        if _normalizar(p["empresa"] or "") == empresa_norm and _normalizar(p["paciente"] or "") == paciente_norm
    ]

    if len(candidatos) != 1:
        motivo = "nenhuma pendência" if not candidatos else f"{len(candidatos)} pendências ambíguas"
        _log(f"'{nome_arquivo}': {motivo} pra '{paciente_arq}' / '{empresa_arq}' — movido pra Revisar")
        _mover(caminho, PASTA_REVISAR)
        return False

    registro = candidatos[0]
    if not os.path.exists(caminho):
        _log(f"'{nome_arquivo}': arquivo sumiu antes de ler (outro ciclo concorrente) — ignorado")
        return False
    with open(caminho, "rb") as f:
        conteudo = f.read()

    contato = conn.execute(
        "SELECT email, pasta_nextcloud FROM empresa_contatos WHERE empresa = ?", (registro["empresa"],)
    ).fetchone()
    pasta_destino = (contato["pasta_nextcloud"] if contato else None) or registro["empresa"]

    from nextcloud_sender import enviar_prontuario
    resultado_upload = enviar_prontuario(pasta_destino, nome_arquivo, conteudo)

    if not resultado_upload.get("ok"):
        _log(f"'{nome_arquivo}': falha no upload pro Nextcloud — {resultado_upload.get('erro')} — movido pra Revisar")
        _mover(caminho, PASTA_REVISAR)
        return False

    link = resultado_upload["link"]
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    email_empresa = (contato["email"] if contato else None) or None

    if email_empresa:
        from email_sender import enviar_email
        corpo = (
            f"Prezados,\n\n"
            f"Segue o link para acesso ao prontuário ocupacional de {registro['paciente']}:\n\n"
            f"{link}\n\n"
            f"Atenciosamente,\n"
            f"Clínica Censo"
        )
        resultado_email = enviar_email(email_empresa, f"Prontuário Ocupacional — {registro['paciente']}", corpo)
        if resultado_email.get("ok"):
            conn.execute("""
                UPDATE prontuarios_pendentes
                SET status='Enviado', dthr_envio=?, link_nextcloud=?, arquivo_nome=?, atualizado_em=?, atualizado_por=?
                WHERE id=?
            """, (agora, link, nome_arquivo, agora, "sincronização (nextcloud)", registro["id"]))
            _log(f"'{nome_arquivo}': enviado com sucesso pra {email_empresa}")
        else:
            conn.execute("""
                UPDATE prontuarios_pendentes
                SET link_nextcloud=?, arquivo_nome=?, observacao=?, atualizado_em=?, atualizado_por=?
                WHERE id=?
            """, (link, nome_arquivo, f"Link gerado mas falha no envio do e-mail: {resultado_email.get('erro')}",
                  agora, "sincronização (nextcloud)", registro["id"]))
            _log(f"'{nome_arquivo}': upload ok, falha no e-mail — {resultado_email.get('erro')}")
    else:
        conn.execute("""
            UPDATE prontuarios_pendentes
            SET link_nextcloud=?, arquivo_nome=?, observacao=?, atualizado_em=?, atualizado_por=?
            WHERE id=?
        """, (link, nome_arquivo, "Link gerado — e-mail da empresa não cadastrado, envie manualmente.",
              agora, "sincronização (nextcloud)", registro["id"]))
        _log(f"'{nome_arquivo}': upload ok, sem e-mail cadastrado pra '{registro['empresa']}'")

    conn.commit()
    _mover(caminho, PASTA_PROCESSADOS)
    return True


def processar_pasta_prontuarios(log=None) -> dict:
    """Roda um ciclo de varredura da pasta. `log` é opcional (objeto logging),
    usado pelo scheduler pra registrar o que aconteceu."""
    def _log(msg):
        if log:
            log.info(f"[ProntuariosWatcher] {msg}")

    if not os.path.isdir(PASTA_WATCH):
        return {"ok": False, "erro": f"Pasta não acessível: {PASTA_WATCH}"}

    arquivos = [
        f for f in os.listdir(PASTA_WATCH)
        if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(PASTA_WATCH, f))
    ]
    if not arquivos:
        return {"ok": True, "processados": 0, "revisar": 0}

    conn = _get_conn()
    pendentes = conn.execute(
        "SELECT id, paciente, empresa FROM prontuarios_pendentes WHERE status = 'Pendente'"
    ).fetchall()

    processados = 0
    revisar = 0

    for nome_arquivo in arquivos:
        caminho = os.path.join(PASTA_WATCH, nome_arquivo)
        if not os.path.exists(caminho):
            continue  # outro ciclo/processo já pegou esse arquivo primeiro
        try:
            if _processar_um_arquivo(nome_arquivo, caminho, pendentes, conn, _log):
                processados += 1
            else:
                revisar += 1
        except Exception as e:
            _log(f"'{nome_arquivo}': erro inesperado ({e}) — movido pra Revisar")
            _mover(caminho, PASTA_REVISAR)
            revisar += 1

    conn.close()
    return {"ok": True, "processados": processados, "revisar": revisar}
