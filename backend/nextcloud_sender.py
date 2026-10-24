# -*- coding: utf-8 -*-
"""
Upload do prontuário escaneado pro Nextcloud (pasta da própria empresa) e
geração do link público de compartilhamento, pro módulo de Envio de
Prontuários (Ocupacional). Erros são sempre capturados e devolvidos, nunca
propagados — mesmo padrão de whatsapp_sender.py/email_sender.py.

Credenciais em backend/.env (NEXTCLOUD_URL/USER/APP_PASSWORD). O servidor só
é alcançável pelo endereço interno (192.168.1.7), mas o link mandado pro
cliente precisa do endereço externo (NEXTCLOUD_EXTERNAL_HOST) — por isso o
host do link retornado pela API é reescrito antes de devolver.

TrustServerCertificate equivalente (verify=False): o Nextcloud interno usa
certificado autoassinado, mesmo padrão já aceito pro resto da infra interna
(SQL Server, Dashboard) neste projeto.
"""
import os
from urllib.parse import quote, urlsplit, urlunsplit

import httpx


def _cfg():
    url = os.getenv("NEXTCLOUD_URL", "").rstrip("/")
    if url.endswith("/index.php"):
        url = url[: -len("/index.php")]
    return {
        "url": url,
        "user": os.getenv("NEXTCLOUD_USER", "").strip(),
        "senha": os.getenv("NEXTCLOUD_APP_PASSWORD", "").strip(),
        "host_externo": os.getenv("NEXTCLOUD_EXTERNAL_HOST", "").strip(),
    }


def listar_pastas() -> dict:
    """Lista as pastas (nível raiz) do Nextcloud — usado na tela de
    configuração empresa→pasta, pra escolher de uma lista em vez de digitar
    o nome à mão (nome da pasta nem sempre bate com o nome da empresa no
    Smart, confirmado em produção em 23/09/2026)."""
    cfg = _cfg()
    if not cfg["url"] or not cfg["user"] or not cfg["senha"]:
        return {"ok": False, "erro": "Nextcloud não configurado (.env)", "pastas": []}
    auth = (cfg["user"], cfg["senha"])
    base = f"{cfg['url']}/remote.php/dav/files/{quote(cfg['user'], safe='')}/"
    try:
        r = httpx.request("PROPFIND", base, auth=auth, verify=False, timeout=30, headers={"Depth": "1"})
        if r.status_code != 207:
            return {"ok": False, "erro": f"Falha ao listar pastas ({r.status_code})", "pastas": []}
        import re as _re
        from urllib.parse import unquote
        hrefs = _re.findall(r"<d:href>(.*?)</d:href>", r.text)
        prefixo = _re.sub(r"^https?://[^/]+", "", base)
        pastas = []
        for h in hrefs:
            if not h.endswith("/") or h == prefixo:
                continue
            nome = unquote(h[len(prefixo):]).rstrip("/")
            if nome:
                pastas.append(nome)
        return {"ok": True, "pastas": sorted(pastas, key=str.upper)}
    except Exception as e:
        return {"ok": False, "erro": str(e), "pastas": []}


def enviar_prontuario(pasta: str, nome_arquivo: str, conteudo: bytes) -> dict:
    """
    Sobe `conteudo` (bytes do PDF) pra `pasta` no Nextcloud (cria a pasta se
    não existir) e gera um link público de compartilhamento. `pasta` deve
    ser o nome exato da pasta já existente (configurada em empresa_contatos)
    ou, na ausência de configuração, o texto do campo empresa — nome da
    pasta não bate automaticamente com o nome da empresa no Smart (confirmado
    em produção em 23/09/2026), por isso a resolução é feita por quem chama.
    Retorna {"ok": True, "link": str} ou {"ok": False, "erro": str}.
    """
    cfg = _cfg()
    if not cfg["url"] or not cfg["user"] or not cfg["senha"]:
        return {"ok": False, "erro": "Nextcloud não configurado (NEXTCLOUD_URL/USER/APP_PASSWORD no .env)"}

    auth = (cfg["user"], cfg["senha"])
    pasta = pasta.strip()
    webdav_base = f"{cfg['url']}/remote.php/dav/files/{quote(cfg['user'], safe='')}"
    pasta_enc = quote(pasta, safe="")
    arquivo_enc = quote(nome_arquivo, safe="")

    try:
        # Garante que a pasta da empresa existe — MKCOL falha com 405 se já
        # existir, o que é esperado e ignorado (não é erro de verdade).
        r_mkcol = httpx.request("MKCOL", f"{webdav_base}/{pasta_enc}", auth=auth, verify=False, timeout=20)
        if r_mkcol.status_code not in (201, 405):
            return {"ok": False, "erro": f"Falha ao acessar/criar pasta '{pasta}' ({r_mkcol.status_code})"}

        r_put = httpx.put(
            f"{webdav_base}/{pasta_enc}/{arquivo_enc}",
            auth=auth, verify=False, timeout=120, content=conteudo,
        )
        if r_put.status_code not in (201, 204):
            return {"ok": False, "erro": f"Falha no upload ({r_put.status_code}): {r_put.text[:200]}"}

        r_share = httpx.post(
            f"{cfg['url']}/ocs/v2.php/apps/files_sharing/api/v1/shares",
            auth=auth, verify=False, timeout=20,
            headers={"OCS-APIRequest": "true", "Accept": "application/json"},
            data={"path": f"/{pasta}/{nome_arquivo}", "shareType": 3, "format": "json"},
        )
        if r_share.status_code not in (200, 201):
            return {"ok": False, "erro": f"Falha ao gerar link público ({r_share.status_code}): {r_share.text[:300]}"}

        link = (r_share.json().get("ocs") or {}).get("data", {}).get("url")
        if not link:
            return {"ok": False, "erro": "Nextcloud não devolveu link no compartilhamento"}

        if cfg["host_externo"]:
            partes = urlsplit(link)
            link = urlunsplit(partes._replace(netloc=cfg["host_externo"]))

        return {"ok": True, "link": link}
    except Exception as e:
        return {"ok": False, "erro": str(e)}
