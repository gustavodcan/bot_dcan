# ===== Standard library =====
import re
import logging

logger = logging.getLogger(__name__)

def extrair_dados_cliente_gescrap(img, texto):
    logger.debug("📜 Cliente Detectado: Gescrap")
    logger.debug(texto)
    
    # Ticket
    m_ticket_ectx = re.search(r"(?<!\d)(\d{7})(?!\d)", texto)
    ticket_val_ectx = m_ticket_ectx.group(1) if m_ticket_ectx else None
    
    # Peso
    
    # Se achar 6 match's, selecionar a 5, se achar 5 match's selecionar a 5.
    matches_validos = []
    
    matches = re.findall(r"\b(\d{4,5})\s+[k][g,q]\b", texto)

    matches_validos = [
        m.replace(",", ".").replace(" ", "")
        for m in matches
    ]
    
    peso_liquido = None

    logger.debug(matches_validos)

    if len(matches_validos) == 4:
        peso_liquido = matches_validos[3]

    elif len(matches_validos) == 3:
        peso_liquido = matches_validos[2]

    logger.debug("🎯 Dados extraídos:")
    logger.debug(f"Nota Fiscal: {ticket_val_gescrap}")
    logger.debug(f"Ticket: {ticket_val_gescrap}")
    logger.debug(f"Peso Líquido: {peso_liquido}")

    return {
        "nota_fiscal": ticket_val_gescrap,
        "ticket": ticket_val_gescrap,
        "peso_liquido": peso_liquido
    }
