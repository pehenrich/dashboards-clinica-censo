# -*- coding: utf-8 -*-
"""
Cliente da API oficial de Agendamento da Pixeon Smart ("Documentação da API de
Agendamento - SMART", portalcliente.pixeon.com, PDF obtido em 14/09/2026) —
NÃO é o banco SQL Server direto, é uma API HTTP separada, com sessão própria
(login/senha/aplicativo -> token).

Usada pra resolver disponibilidade de horário de forma confiável: a tabela
AGD (grade de horários) usa uma codificação legada de shading de tela (bytes
CP437 tipo ▒/█, sem correspondência clara e verificável com ocupação real —
investigado e descartado, ver commit/conversa de 14/09/2026) — a API oficial
evita esse problema porque quem calcula a disponibilidade é o próprio Smart.

Configuração necessária em backend/.env (nenhum valor "chutado" aqui —
preencher com os dados reais da Pixeon antes de usar):
    SMART_API_BASE_URL   ex.: https://smart.pixeon.com
    SMART_API_LOGIN
    SMART_API_SENHA
    SMART_API_APLICATIVO  ex.: "SmartWeb" (nome que a Pixeon cadastrar pra essa integração)

ATENÇÃO — pontos da doc que não ficaram 100% explícitos e precisam ser
confirmados no primeiro teste real (usar rollback/ambiente de teste, nunca
assumir que está certo sem validar):
  - Como o Token é enviado nas chamadas além de Sessão/Renovação/Delete (a doc
    só lista "Token" como parâmetro de entrada nesses 3 endpoints de sessão;
    pros demais, assumido aqui como header HTTP "Token" — ajustar se a Pixeon
    usar outro nome/formato, ex. "Authorization: Bearer <token>").
  - Formato exato de data esperado por DataIni/DataFim (a doc mostra exemplo
    "2022-02-22T13" — sem minutos/segundos claros; usando ISO 8601 completo
    por padrão, ajustar se a API for estrita quanto ao formato).
"""
import os
import requests
from datetime import datetime

_token_cache = {"token": None, "obtido_em": None}


def _base_url():
    url = os.environ.get("SMART_API_BASE_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("SMART_API_BASE_URL não configurada em backend/.env — API de agendamento Pixeon indisponível.")
    return url


def configurado():
    """True se as variáveis de ambiente mínimas já foram preenchidas."""
    return bool(os.environ.get("SMART_API_BASE_URL") and os.environ.get("SMART_API_LOGIN") and os.environ.get("SMART_API_SENHA"))


def _login():
    resp = requests.post(f"{_base_url()}/api/Sessao", json={
        "login": os.environ.get("SMART_API_LOGIN", ""),
        "senha": os.environ.get("SMART_API_SENHA", ""),
        "Aplicativo": os.environ.get("SMART_API_APLICATIVO", "SmartWeb"),
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    token = data.get("Token")
    if not token:
        raise RuntimeError(f"Login na API de Agendamento Pixeon não retornou Token: {data}")
    _token_cache["token"] = token
    _token_cache["obtido_em"] = datetime.now()
    return token


def _chamar(metodo, caminho, **kwargs):
    token = _token_cache["token"] or _login()
    headers = kwargs.pop("headers", {})
    headers["Token"] = token
    resp = requests.request(metodo, f"{_base_url()}{caminho}", headers=headers, timeout=20, **kwargs)
    if resp.status_code in (401, 403):
        # token expirado/invalido -> loga de novo e tenta uma unica vez
        token = _login()
        headers["Token"] = token
        resp = requests.request(metodo, f"{_base_url()}{caminho}", headers=headers, timeout=20, **kwargs)
    resp.raise_for_status()
    return resp.json()


def consultar_disponibilidade(data_ini, data_fim, procedimento_id, convenio_id, unidade_id,
                               plano_id=None, cep=None,
                               profissional_executante_id=None, profissional_solicitante_id=None):
    """
    POST /api/Agenda — consulta a grade real de horários livres, calculada
    pelo próprio Smart (substitui a tentativa de decodificar AGD na unha).
    """
    procedimento = {
        "ProcedimentoId": procedimento_id,
        "ConvenioId": convenio_id,
        "UnidadeId": unidade_id,
    }
    if plano_id:
        procedimento["PlanoId"] = plano_id
    if profissional_executante_id:
        procedimento["ProfissionalExecutanteId"] = profissional_executante_id
    if profissional_solicitante_id:
        procedimento["ProfissionalSolicitanteId"] = profissional_solicitante_id

    body = {
        "DataIni": data_ini,
        "DataFim": data_fim,
        "ListaProcedimento": [procedimento],
    }
    if cep:
        body["PacCep"] = cep

    return _chamar("POST", "/api/Agenda", json=body)
