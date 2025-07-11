import re
def extrair_dados_cliente_cdr(img, texto):
    ticket = re.search(r"ticket[:\-]?\s*(\d{5,}/\d{4})", texto, re.IGNORECASE)
    outros_docs = re.search(r"outros\s+docs\.?\s*[:\-]?\s*(\d+)", texto, re.IGNORECASE)
    peso_liquido = re.search(r"peso\s+líquido\s*\(kg\)\s*[:\-]?\s*(\d+)", texto, re.IGNORECASE)
    return {
        "ticket": ticket.group(1) if ticket else "NÃO ENCONTRADO",
        "outros_docs": outros_docs.group(1) if outros_docs else "NÃO ENCONTRADO",
        "peso_liquido": peso_liquido.group(1) if peso_liquido else "NÃO ENCONTRADO"
    }
