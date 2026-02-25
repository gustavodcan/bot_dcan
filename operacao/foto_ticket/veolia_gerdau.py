# ===== Standard library =====
import re
import logging

logger = logging.getLogger(__name__)

def extrair_dados_cliente_veolia_gerdau(img, texto):
    logger.debug("📜 [Gerdau] Texto detectado:")
    logger.debug(texto)

    ticket_match = re.search(r"(?m)^(?:.*?\s*)?(\d{3,5}/\d{4})\s*$", texto)
    ticket_val = ticket_match.group(1).replace("/", "") if ticket_match else "NÃO ENCONTRADO"

    outros_docs = re.search(r"outros[\s_]*docs[.:;\-]*[:]?[\s]*([0-9]{4,})", texto)

    peso_liquido = re.search(
        r"peso[\s_]*l[iíoe]qu[iíoe]d(?:o|ouido|uido|oudo)?[\s_]*(?:kg)?[:：]{1,2}\s*([0-9]{4,6})",
        texto
    )

    # 🧠 Log de debug pro Render ou local
    logger.debug("🎯 Dados extraídos:")
    logger.debug(f"Ticket: {ticket_val}")
    logger.debug(f"Outros Docs: {outros_docs.group(1) if outros_docs else 'SEM NF'}")
    logger.debug(f"Peso Líquido: {peso_liquido.group(1) if peso_liquido else 'Não encontrado'}")

    return {
        "ticket": ticket_val,
        "nota_fiscal": outros_docs.group(1) if outros_docs else "SEM NF",
#        "outros_docs": outros_docs.group(1) if outros_docs else "NÃO ENCONTRADO",
        "peso_liquido": peso_liquido.group(1) if peso_liquido else "NÃO ENCONTRADO"
    }