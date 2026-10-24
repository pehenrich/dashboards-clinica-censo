# -*- coding: utf-8 -*-
"""
Backup diário dos bancos SQLite locais (guias.db, chat_interno.db,
atas_reuniao.db, organograma.db, indicadores.db, prontuario_eletronico.db,
medicamentos_anvisa.db, prontuarios.db, agenda_bot.db — qualquer *.db em
backend/, sem precisar listar nome por nome) + configs fora do banco
(metas_config.json, whatsapp_config.json). Esses arquivos não entram no Git
(backend/*.db é ignorado de propósito — são dados de cada instalação, não
código) e, até aqui, não tinham NENHUM backup — só existiam neste disco.

Dois destinos:
  1. Nextcloud (pasta "Backups Dashboard" na raiz) — reaproveita a mesma
     credencial WebDAV de nextcloud_sender.py. Esse é o que protege de
     verdade contra perda do disco/servidor.
  2. backend/backups/ localmente — cópia rápida extra (rotaciona, mantém só
     os últimos 7 dias), útil pra restaurar rápido sem depender da rede.

Cada .db é copiado via sqlite3 Connection.backup() (não um copy de arquivo
cru) pra garantir uma cópia consistente mesmo se o backend estiver com o
banco aberto/em uso no momento do backup.
"""
import os
import glob
import json
import sqlite3
import zipfile
from datetime import datetime, timedelta

from urllib.parse import quote
import httpx

_DIR = os.path.dirname(os.path.abspath(__file__))
_DIR_BACKUPS_LOCAIS = os.path.join(_DIR, "backups")
_RETENCAO_DIAS = 7
_PASTA_NEXTCLOUD = "Backups Dashboard"

_CONFIGS_EXTRAS = ["metas_config.json", "whatsapp_config.json"]


def _copiar_sqlite_consistente(caminho_origem: str, caminho_destino: str):
    origem = sqlite3.connect(caminho_origem)
    try:
        destino = sqlite3.connect(caminho_destino)
        try:
            origem.backup(destino)
        finally:
            destino.close()
    finally:
        origem.close()


def _montar_zip() -> str:
    os.makedirs(_DIR_BACKUPS_LOCAIS, exist_ok=True)
    nome_zip = f"backup_dashboard_{datetime.now().strftime('%Y-%m-%d_%H%M')}.zip"
    caminho_zip = os.path.join(_DIR_BACKUPS_LOCAIS, nome_zip)

    with zipfile.ZipFile(caminho_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for caminho_db in glob.glob(os.path.join(_DIR, "*.db")):
            nome = os.path.basename(caminho_db)
            tmp = os.path.join(_DIR_BACKUPS_LOCAIS, f"_tmp_{nome}")
            try:
                _copiar_sqlite_consistente(caminho_db, tmp)
                zf.write(tmp, arcname=nome)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)

        for nome_config in _CONFIGS_EXTRAS:
            caminho_config = os.path.join(_DIR, nome_config)
            if os.path.exists(caminho_config):
                zf.write(caminho_config, arcname=nome_config)

    return caminho_zip


def _enviar_para_nextcloud(caminho_zip: str) -> dict:
    url = os.getenv("NEXTCLOUD_URL", "").rstrip("/")
    if url.endswith("/index.php"):
        url = url[: -len("/index.php")]
    user = os.getenv("NEXTCLOUD_USER", "").strip()
    senha = os.getenv("NEXTCLOUD_APP_PASSWORD", "").strip()
    if not url or not user or not senha:
        return {"ok": False, "erro": "Nextcloud não configurado (.env)"}

    auth = (user, senha)
    webdav_base = f"{url}/remote.php/dav/files/{quote(user, safe='')}"
    pasta_enc = quote(_PASTA_NEXTCLOUD, safe="")
    nome_arquivo = os.path.basename(caminho_zip)
    arquivo_enc = quote(nome_arquivo, safe="")

    try:
        r_mkcol = httpx.request("MKCOL", f"{webdav_base}/{pasta_enc}", auth=auth, verify=False, timeout=20)
        if r_mkcol.status_code not in (201, 405):
            return {"ok": False, "erro": f"Falha ao acessar/criar pasta '{_PASTA_NEXTCLOUD}' ({r_mkcol.status_code})"}

        with open(caminho_zip, "rb") as f:
            conteudo = f.read()
        r_put = httpx.put(
            f"{webdav_base}/{pasta_enc}/{arquivo_enc}",
            auth=auth, verify=False, timeout=120, content=conteudo,
        )
        if r_put.status_code not in (201, 204):
            return {"ok": False, "erro": f"Falha no upload ({r_put.status_code}): {r_put.text[:200]}"}
        return {"ok": True, "tamanho_bytes": len(conteudo)}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


def _rotacionar_backups_locais():
    limite = datetime.now() - timedelta(days=_RETENCAO_DIAS)
    for caminho in glob.glob(os.path.join(_DIR_BACKUPS_LOCAIS, "backup_dashboard_*.zip")):
        try:
            if datetime.fromtimestamp(os.path.getmtime(caminho)) < limite:
                os.remove(caminho)
        except OSError:
            pass


def fazer_backup_diario() -> dict:
    """Ponto de entrada chamado pelo scheduler uma vez por dia. Nunca propaga
    exceção — mesmo padrão de whatsapp_sender.py/email_sender.py/nextcloud_sender.py."""
    try:
        caminho_zip = _montar_zip()
    except Exception as e:
        return {"ok": False, "erro": f"Falha ao montar backup: {e}"}

    resultado_nextcloud = _enviar_para_nextcloud(caminho_zip)
    _rotacionar_backups_locais()

    return {
        "ok": resultado_nextcloud.get("ok", False),
        "arquivo": os.path.basename(caminho_zip),
        "nextcloud": resultado_nextcloud,
    }


if __name__ == "__main__":
    print(fazer_backup_diario())
