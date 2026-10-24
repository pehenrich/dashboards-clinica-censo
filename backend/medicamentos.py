# -*- coding: utf-8 -*-
"""
Autocomplete de medicamento pra Prescrição (módulo Atendimento). Busca por
nome comercial OU princípio ativo na base oficial de dados abertos da ANVISA
(medicamentos_anvisa.db — importado uma vez de
https://dados.anvisa.gov.br/dados/DADOS_ABERTOS_MEDICAMENTOS.csv via
_importar_anvisa.py, só registros com SITUACAO_REGISTRO='Ativo'; reimportar
esse script quando quiser atualizar a base). Sem dependência de API externa
em produção — consulta só a cópia local.
Prioriza, dentro dos resultados, o que aquele médico já prescreveu de verdade
pelo sistema (prontuario_eletronico.db) — assim o que ele mais usa sobe pro
topo, mas a busca nunca fica vazia só porque ninguém usou ainda.
"""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "medicamentos_anvisa.db")


def _uso_anterior(medico_login: str | None):
    """
    Por medicamento: quantas vezes já foi prescrito e qual foi a posologia/
    quantidade/uso contínuo da ÚLTIMA vez — pra sugerir/carregar a posologia
    automaticamente quando o médico escolhe algo que ele já prescreveu antes.
    """
    try:
        from prontuario_eletronico import get_conn
        conn = get_conn()
        filtro = "WHERE c.medico_login = ?" if medico_login else ""
        params = (medico_login,) if medico_login else ()
        rows = conn.execute(f"""
            SELECT p.medicamento, p.posologia, p.quantidade, p.uso_continuo, p.criado_em,
                COUNT(*) OVER (PARTITION BY p.medicamento) AS n,
                ROW_NUMBER() OVER (PARTITION BY p.medicamento ORDER BY p.criado_em DESC) AS rn
            FROM prescricoes p JOIN consultas c ON c.id = p.consulta_id
            {filtro}
        """, params).fetchall()
        conn.close()
        return {r["medicamento"].strip().upper(): r for r in rows if r["rn"] == 1}
    except Exception:
        return {}


def buscar(termo: str, medico_login: str | None = None, limite: int = 15):
    termo = termo.strip()
    if len(termo) < 2:
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    contem = f"%{termo}%"
    comeca = f"{termo}%"
    # Prioriza quem COMEÇA com o termo (nome do produto, depois princípio
    # ativo) antes de quem só contém o termo em algum lugar — sem isso, nome
    # genérico curto tipo "DIPIRONA" ficava atrás de marca de 5 letras tipo
    # "DIPBE" só porque a ordenação antiga era por tamanho do nome (bug real
    # confirmado: buscar "dipirona" não trazia "DIPIRONA" nos primeiros 15).
    rows = conn.execute("""
        SELECT nome_produto, principio_ativo,
            CASE
                WHEN nome_produto LIKE ? COLLATE NOCASE THEN 0
                WHEN principio_ativo LIKE ? COLLATE NOCASE THEN 1
                ELSE 2
            END AS rank_match
        FROM medicamentos
        WHERE nome_produto LIKE ? COLLATE NOCASE OR principio_ativo LIKE ? COLLATE NOCASE
        ORDER BY rank_match ASC, LENGTH(nome_produto) ASC
        LIMIT 200
    """, (comeca, comeca, contem, contem)).fetchall()
    conn.close()

    uso_anterior = _uso_anterior(medico_login)
    vistos = set()
    candidatos = []
    for r in rows:
        nome = r["nome_produto"].strip()
        chave = nome.upper()
        if chave in vistos:
            continue
        vistos.add(chave)
        u = uso_anterior.get(chave)
        candidatos.append({
            "nome": nome,
            "principio_ativo": (r["principio_ativo"] or "").strip(),
            "uso": u["n"] if u else 0,
            "ultima_posologia": u["posologia"] if u else "",
            "ultima_quantidade": u["quantidade"] if u else "",
            "ultimo_uso_continuo": (u["uso_continuo"] == "S") if u else False,
        })

    candidatos.sort(key=lambda c: -c["uso"])
    return candidatos[:limite]
