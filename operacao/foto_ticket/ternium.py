import re, logging
logger = logging.getLogger(__name__)

def extrair_dados_cliente_ternium(img, texto):
    logger.debug("📜 Cliente Detectado: Ternium")
    logger.debug(texto)

    # Nota
    nf_match = re.search(r"\bitem:\s*(?:\[?n\]?\s*)?(\d+)-", texto, re.IGNORECASE)
    nota_val = nf_match.group(1) if nf_match else None
    
    # Ticket
    ticket_match = re.search(r"\bpesagem:\s*(\d+)", texto, re.IGNORECASE)
    ticket_val = ticket_match.group(1) if ticket_match else None

    # Peso
    peso = re.search(r"\bl[íi]qu[ií]do:\s*(\d+)", texto, re.IGNORECASE)
    peso_liquido = peso.group(1) if peso else None

    logger.debug("🎯 Dados extraídos:")
    logger.debug(f"Nota Fiscal: {nota_val}")
    logger.debug(f"Ticket: {ticket_val}")
    logger.debug(f"Peso Líquido: {peso_liquido}")

    return {
        "nota_fiscal": nota_val,
        "ticket": ticket_val,
        "peso_liquido": peso_liquido
    }
