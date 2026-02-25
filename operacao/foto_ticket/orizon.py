# ===== Standard library =====
import re
import logging

logger = logging.getLogger(__name__)

def extrair_dados_cliente_orizon(img, texto):
    logger.debug("📜 [ORIZON] Texto detectado:")
    logger.debug(texto)

    ticket_val = "NÃO ENCONTRADO"
    peso_liquido_val = "NÃO ENCONTRADO"

    texto_lower = texto.lower()

    # --- Peso Líquido ---
    match_peso = re.search(
        r"peso[\s_]*l[ií1!|][qg][uúü][ií1!|][d0o][a-z]*kg[:：]{0,2}\s*([0-9]{4,6})",
        texto_lower
    )
    if match_peso:
        peso_liquido_val = match_peso.group(1)
        logger.debug(f"Peso líquido encontrado: {peso_liquido_val}")

    # --- Ticket (padrão tipo TB0000108249 ou variações) ---
    match_ticket = re.search(
        r"\b[tт][bв][оo0]?([0-9]{6,})\b",
        texto_lower
    )
    if match_ticket:
        ticket_val = match_ticket.group(1)
        logger.debug(f"Operação (ticket) encontrada: {ticket_val}")

    logger.debug("🎯 Dados extraídos:")
    logger.debug(f"Ticket: {ticket_val}")
    logger.debug(f"Peso Líquido: {peso_liquido_val}")

    return {
        "ticket": ticket_val,
        "peso_liquido": peso_liquido_val,
        "nota_fiscal": "NÃO APLICÁVEL"
    }