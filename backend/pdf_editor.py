"""
Editor de PDF — troca pontual de uma palavra num documento (ex.: corrigir um
nome ou termo errado num ASO já emitido, sem precisar reemitir).

Como um PDF não guarda texto "reflowable" (não é um .docx), a troca é feita
por localizar a palavra, cobrir a área original com uma caixa branca
(redação) e escrever a palavra nova por cima, tentando casar fonte/tamanho/
cor do texto original. Funciona bem para trocas de uma palavra por outra de
tamanho parecido; se a palavra nova for bem mais longa que a original, pode
sobrepor o texto vizinho — isso é uma limitação inerente da técnica, não um
bug a corrigir.
"""
import fitz  # PyMuPDF

_PONTUACAO_BORDA = ".,;:!?()[]{}\"'“”‘’"


def _nucleo(palavra: str) -> str:
    return palavra.strip(_PONTUACAO_BORDA)


def _mapear_fonte(nome_fonte: str, negrito: bool, italico: bool) -> str:
    """Aproxima o nome de fonte embutido no PDF para uma das 14 fontes base
    do PyMuPDF (não dá pra reusar a fonte original sem extrair o arquivo dela)."""
    n = (nome_fonte or "").lower()
    if "courier" in n or "mono" in n:
        familia = "co"
        if negrito and italico: return "cobi"
        if negrito: return "cobo"
        if italico: return "coit"
        return "cour"
    if "times" in n or "serif" in n or "georgia" in n:
        if negrito and italico: return "tibi"
        if negrito: return "tibo"
        if italico: return "tiit"
        return "tiro"
    # default: familia sans-serif (Helvetica cobre bem Arial/Calibri/etc.)
    if negrito and italico: return "hebi"
    if negrito: return "hebo"
    if italico: return "heit"
    return "helv"


def _cor_rgb(color_int: int):
    r = ((color_int >> 16) & 255) / 255
    g = ((color_int >> 8) & 255) / 255
    b = (color_int & 255) / 255
    return (r, g, b)


def _localizar_palavras(page: "fitz.Page", palavra: str, case_sensitive: bool):
    """Retorna lista de dicts com rect, texto original e info de estilo
    (fonte/tamanho/cor) pra cada ocorrência EXATA da palavra na página
    (ignora pontuação colada, ex.: 'Censo,' bate com 'Censo')."""
    alvo = palavra if case_sensitive else palavra.lower()

    # spans com estilo, pra casar fonte/tamanho/cor de cada palavra
    spans = []
    for bloco in page.get_text("dict")["blocks"]:
        for linha in bloco.get("lines", []):
            for span in linha.get("spans", []):
                spans.append(span)

    def _estilo_no_ponto(rect: "fitz.Rect"):
        cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
        for span in spans:
            sb = fitz.Rect(span["bbox"])
            if sb.contains(fitz.Point(cx, cy)) or sb.intersects(rect):
                flags = span.get("flags", 0)
                negrito = bool(flags & 2**4) or "bold" in span.get("font", "").lower()
                italico = bool(flags & 2**1) or "italic" in span.get("font", "").lower() or "oblique" in span.get("font", "").lower()
                return {
                    "fonte": _mapear_fonte(span.get("font", ""), negrito, italico),
                    "tamanho": span.get("size", 11),
                    "cor": _cor_rgb(span.get("color", 0)),
                }
        return {"fonte": "helv", "tamanho": 11, "cor": (0, 0, 0)}

    ocorrencias = []
    for x0, y0, x1, y1, texto, block_no, line_no, word_no in page.get_text("words"):
        comparar = _nucleo(texto if case_sensitive else texto.lower())
        if comparar == alvo:
            rect = fitz.Rect(x0, y0, x1, y1)
            ocorrencias.append({
                "rect": rect,
                "texto_original": texto,
                "block": block_no,
                "line": line_no,
                **_estilo_no_ponto(rect),
            })
    return ocorrencias


def buscar_ocorrencias(pdf_bytes: bytes, palavra: str, case_sensitive: bool = False):
    """Pré-visualização: lista onde a palavra aparece, sem alterar o PDF."""
    palavra = palavra.strip()
    if not palavra:
        return {"total": 0, "paginas": []}

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    resultado_paginas = []
    total = 0
    try:
        for i, page in enumerate(doc):
            ocorrencias = _localizar_palavras(page, palavra, case_sensitive)
            if not ocorrencias:
                continue
            # contexto: junta as palavras da mesma linha de cada ocorrência
            palavras_da_pagina = page.get_text("words")
            contextos = []
            for oc in ocorrencias:
                da_linha = [w[4] for w in palavras_da_pagina if w[5] == oc["block"] and w[6] == oc["line"]]
                contextos.append(" ".join(da_linha))
            total += len(ocorrencias)
            resultado_paginas.append({
                "pagina": i + 1,
                "ocorrencias": len(ocorrencias),
                "contextos": contextos,
            })
    finally:
        doc.close()

    return {"total": total, "paginas": resultado_paginas}


def substituir_palavra(pdf_bytes: bytes, palavra_antiga: str, palavra_nova: str, case_sensitive: bool = False) -> bytes:
    """Troca todas as ocorrências (palavra inteira) de palavra_antiga por
    palavra_nova no PDF e devolve os bytes do PDF editado."""
    palavra_antiga = palavra_antiga.strip()
    palavra_nova = palavra_nova.strip()
    if not palavra_antiga or not palavra_nova:
        raise ValueError("Informe a palavra atual e a palavra nova.")

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        total_trocas = 0
        for page in doc:
            ocorrencias = _localizar_palavras(page, palavra_antiga, case_sensitive)
            if not ocorrencias:
                continue
            for oc in ocorrencias:
                rect = oc["rect"]
                # levemente maior pra cobrir antialiasing da borda do texto original
                cobertura = rect + (-0.75, -0.75, 0.75, 0.75)
                page.add_redact_annot(cobertura, fill=(1, 1, 1))
            page.apply_redactions()
            for oc in ocorrencias:
                rect = oc["rect"]
                ponto_base = fitz.Point(rect.x0, rect.y1 - rect.height * 0.15)
                page.insert_text(
                    ponto_base, palavra_nova,
                    fontname=oc["fonte"], fontsize=oc["tamanho"], color=oc["cor"],
                )
                total_trocas += 1
        if total_trocas == 0:
            raise ValueError(f'Palavra "{palavra_antiga}" não encontrada no documento.')
        return doc.tobytes()
    finally:
        doc.close()
