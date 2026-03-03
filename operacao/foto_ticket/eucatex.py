# ===== Standard library =====
import re
import logging

logger = logging.getLogger(__name__)

def extrair_dados_cliente_eucatex(img, texto):
    logger.debug("📜 Cliente Detectado: Eucatex")
    logger.debug(texto)
    
    # Ticket
    m_ticket_ectx = re.search(r"(?i)\bboleto\b[\s:]*([0-9/]{3,})", texto)
    ticket_val_ectx = m_ticket_ectx.group(1) if m_ticket_ectx else NAO_ENCONTRADO
    
    # Peso
    
    # Se achar 6 match's, selecionar a 5, se achar 5 match's selecionar a 5.
    matches_validos = []
    
    for linha in texto.splitlines():
        m = re.search(r"\b(\d{1,3}\s*[.,]\s*\d{3})\b", linha, flags=re.IGNORECASE)
        if m:
            matches_validos.append(m.group(1).replace(",", ".").replace(" ", ""))

    peso_liquido = None

    logger.debug(matches_validos)

    if len(matches_validos) == 6:
        peso_liquido = matches_validos[4]

    elif len(matches_validos) == 5:
        peso_liquido = matches_validos[4]

    logger.debug("🎯 Dados extraídos:")
    logger.debug(f"Nota Fiscal: {ticket_val_ectx}")
    logger.debug(f"Ticket: {ticket_val_ectx}")
    logger.debug(f"Peso Líquido: {peso_liquido}")

    return {
        "nota_fiscal": ticket_val_ectx,
        "ticket": ticket_val_ectx,
        "peso_liquido": peso_liquido
    }
