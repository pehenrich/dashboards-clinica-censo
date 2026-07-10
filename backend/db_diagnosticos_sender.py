"""
db_diagnosticos_sender.py
Consulta de status/laudo junto à DB Diagnósticos (protocolo DBSync, SOAP).

O envio do pedido (RecebeAtendimento) já é feito pelo próprio Smart Pixeon
(gera os arquivos Pedido_84_*.xml em C:\\Smart\\Aplic60). Este módulo só
CONSULTA — status do pedido e link do laudo em PDF — nunca envia pedido.

NumeroAtendimentoApoiado usa o formato "{osm_serie}.{osm_num}" (confirmado
nos XMLs legados gerados pelo Smart).
"""

import os
import zeep
import zeep.helpers

DB_DIAG_WSDL_URL = os.getenv("DB_DIAGNOSTICOS_WSDL_URL", "")
DB_DIAG_CODIGO   = os.getenv("DB_DIAGNOSTICOS_CODIGO_APOIADO", "")
DB_DIAG_SENHA    = os.getenv("DB_DIAGNOSTICOS_SENHA", "")

_client = None
_client_wsdl = None

def _get_client():
    # Relê do os.environ a cada chamada — o .env do main.py é carregado
    # DEPOIS deste módulo ser importado, então as constantes de módulo
    # (lidas no import) ficam vazias; o os.environ em si já está OK
    # no momento em que a rota é de fato chamada.
    global _client, _client_wsdl
    wsdl = os.getenv("DB_DIAGNOSTICOS_WSDL_URL", DB_DIAG_WSDL_URL)
    if _client is None or wsdl != _client_wsdl:
        _client = zeep.Client(wsdl=wsdl)
        _client_wsdl = wsdl
    return _client


def consultar_status(numero_atendimento: str) -> dict:
    """Status do pedido (ConsultaStatusAtendimento) — Aguardando, Liberado
    Clínico, Divulgada etc."""
    client = _get_client()
    resp = client.service.ConsultaStatusAtendimento(request={
        "CodigoApoiado": os.getenv("DB_DIAGNOSTICOS_CODIGO_APOIADO", DB_DIAG_CODIGO),
        "CodigoSenhaIntegracao": os.getenv("DB_DIAGNOSTICOS_SENHA", DB_DIAG_SENHA),
        "NumeroAtendimentoApoiado": numero_atendimento,
    })
    return zeep.helpers.serialize_object(resp, dict)


def buscar_laudo_pdf(numero_atendimento: str) -> dict:
    """Link do laudo em PDF (EnviaResultadoBase64). Retorna todos os exames
    liberados do atendimento se nenhum CodigoExameDB específico for pedido."""
    client = _get_client()
    resp = client.service.EnviaResultadoBase64(request={
        "CodigoApoiado": os.getenv("DB_DIAGNOSTICOS_CODIGO_APOIADO", DB_DIAG_CODIGO),
        "CodigoSenhaIntegracao": os.getenv("DB_DIAGNOSTICOS_SENHA", DB_DIAG_SENHA),
        "NumeroAtendimento": numero_atendimento,
    })
    return zeep.helpers.serialize_object(resp, dict)
