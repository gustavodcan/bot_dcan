import re, logging

logger = logging.getLogger(__name__)

def extrair_dados_cliente_gerdaupinda(img, texto):
    logger.debug("[GERDAU] Extraindo dados...")
    logger.debug("📜 Texto para extração:")
    logger.debug(texto)
    
    ticket_match_pinda = re.search(r"(?:processo)[\s:]*([0-9/]{5,})", texto)
    ticket_val_pinda = ticket_match.group(1) if ticket_match else "NÃO ENCONTRADO"

    outros_docs_pinda = re.search(r"docto[:：]?\s*nf\s*[-–—]?\s*(\d{4,8})", texto, re.IGNORECASE)
    
    peso_liquido_pinda = re.search(
        r"(?i)[\s_]*l[ií]qu[ií]d(?:o|ouido|uido|oudo)?[\s_]*(?:kg)?[:：]{0,2}\s*\n?([0-9]{4,6})",
        texto
    )

    # 🧠 Log de debug pro Render ou local
    logger.debug("🎯 Dados extraídos:")
    logger.debug(f"Ticket: {ticket_val}")
    logger.debug(f"Outros Docs: {outros_docs.group(1) if outros_docs else 'Não encontrado'}")
    logger.debug(f"Peso Líquido: {peso_liquido.group(1) if peso_liquido else 'Não encontrado'}")

    return {
        "ticket": ticket_val,
        "outros_docs": outros_docs.group(1) if outros_docs else "NÃO ENCONTRADO",
        "peso_liquido": peso_liquido.group(1) if peso_liquido else "NÃO ENCONTRADO",
        "nota_fiscal": outros_docs.group(1) if outros_docs else "NÃO ENCONTRADO"
    }

def extrair_dados_cliente_gerdau(img, texto):
    logger.debug("[GERDAU] Extraindo dados...")
    logger.debug("📜 Texto para extração:")
    logger.debug(texto)

    # Ticket: exatamente 8 dígitos
    ticket_match = re.search(r"\b(\d{8})\b", texto)
    ticket_val = ticket_match.group(1) if ticket_match else "NÃO ENCONTRADO"

    # Nota fiscal: número antes do primeiro hífen
    matches_nota = re.findall(r"\b(\d{3,10})-\d{1,3}\b", texto)
    if matches_nota:
        nota_fiscal_val = matches_nota[0]

    # Peso líquido: procura por 'xx,xxx to' sem horário na linha
    peso_liquido_val = "NÃO ENCONTRADO"
    linhas = texto.splitlines()
    for linha in linhas:
        match = re.search(r"\b(\d{2,3}[.,]\d{3})\s+to\b", linha)
        if match and not re.search(r"\d{2}:\d{2}:\d{2}", linha):
            peso_liquido_val = match.group(1).replace(",", ".")
            break

    logger.debug("🎯 Dados extraídos:")
    logger.debug(f"Ticket: {ticket_val}")
    logger.debug(f"Nota Fiscal: {nota_fiscal_val}")
    logger.debug(f"Peso Líquido: {peso_liquido_val}")

    return {
        "ticket": ticket_val,
        "nota_fiscal": nota_fiscal_val,
        "peso_liquido": peso_liquido_val
    }
