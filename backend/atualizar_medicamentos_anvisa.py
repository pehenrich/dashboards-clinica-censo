# -*- coding: utf-8 -*-
"""
Atualiza backend/medicamentos_anvisa.db a partir do dado aberto oficial da
ANVISA (https://dados.anvisa.gov.br/dados/DADOS_ABERTOS_MEDICAMENTOS.csv,
atualizado diariamente pela própria agência, licença Creative Commons).
Roda sob demanda (não é agendado) — rodar de novo quando quiser atualizar a
base de medicamentos usada no autocomplete de Prescrição do módulo Atendimento.
Mantém só registros com SITUACAO_REGISTRO='Ativo', deduplicados por
(nome, princípio ativo).
"""
import csv
import sqlite3
import os
import urllib.request

URL = "https://dados.anvisa.gov.br/dados/DADOS_ABERTOS_MEDICAMENTOS.csv"
TMP_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_anvisa_tmp.csv")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "medicamentos_anvisa.db")


def main():
    print("baixando CSV da ANVISA...")
    urllib.request.urlretrieve(URL, TMP_CSV)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("DROP TABLE IF EXISTS medicamentos")
    conn.execute("""
        CREATE TABLE medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_produto TEXT NOT NULL,
            principio_ativo TEXT,
            classe_terapeutica TEXT
        )
    """)

    vistos = set()
    linhas = []
    total_lidas = 0
    with open(TMP_CSV, encoding="ISO-8859-1", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            total_lidas += 1
            if row.get("TIPO_PRODUTO") != "MEDICAMENTO" or row.get("SITUACAO_REGISTRO") != "Ativo":
                continue
            nome = (row.get("NOME_PRODUTO") or "").strip()
            principio = (row.get("PRINCIPIO_ATIVO") or "").strip()
            classe = (row.get("CLASSE_TERAPEUTICA") or "").strip()
            if not nome or "?" in nome:
                continue
            chave = (nome.upper(), principio.upper())
            if chave in vistos:
                continue
            vistos.add(chave)
            linhas.append((nome, principio, classe))

    conn.executemany("INSERT INTO medicamentos (nome_produto, principio_ativo, classe_terapeutica) VALUES (?,?,?)", linhas)
    conn.execute("CREATE INDEX ix_med_nome ON medicamentos(nome_produto COLLATE NOCASE)")
    conn.execute("CREATE INDEX ix_med_principio ON medicamentos(principio_ativo COLLATE NOCASE)")
    conn.commit()
    conn.close()
    os.remove(TMP_CSV)

    print(f"linhas lidas no CSV: {total_lidas}")
    print(f"medicamentos ativos importados (deduplicados): {len(linhas)}")


if __name__ == "__main__":
    main()
