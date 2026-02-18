import re, logging

logger = logging.getLogger(__name__)

NAO_ENCONTRADO = "NÃO ENCONTRADO"

def _encontrado(v: str) -> bool:
    return bool(v) and v != NAO_ENCONTRADO

def extrair_dados_cliente_gerdau(img, texto: str):
    logger.debug("[GERDAU] Extraindo dados...")
    logger.debug("📜 Texto para extração:")
    logger.debug(texto)

    # Gerdau Geral: ticket com 8 dígitos
    m_ticket_geral = re.search(r"^\s*\d{8,9}\s*$", texto)
    ticket_val = m_ticket_geral.group(1) if m_ticket_geral else NAO_ENCONTRADO

    # Gerdau Pinda: “processo: 74928/1” (5+ dígitos com possível “/”)
    m_ticket_pinda = re.search(r"(?i)\bprocesso\b[\s:]*([0-9/]{5,})", texto)
    ticket_val_pinda = m_ticket_pinda.group(1) if m_ticket_pinda else NAO_ENCONTRADO

    ticket_final = ticket_val if _encontrado(ticket_val) else ticket_val_pinda

    # Gerdau Pinda: "docto: nf 123456"
    m_outros_docs_pinda = re.search(r"(?i)docto[:：]?\s*nf\s*[-–—]?\s*(\d{4,10})", texto)
    nota_fiscal_pinda = (str(int(m_outros_docs_pinda.group(1))) if m_outros_docs_pinda else NAO_ENCONTRADO)
    
    # Gerdau Geral: padrão "12345-1" → pega o número antes do hífen
    matches_nota = re.findall(r"\b(\d{3,10})-\d{1,3}\b", texto)
    nota_fiscal_geral = (str(int(matches_nota[0])) if matches_nota else NAO_ENCONTRADO)

    nota_fiscal_final = (nota_fiscal_pinda if _encontrado(nota_fiscal_pinda) else nota_fiscal_geral)

    # Gerdau Geral : linha com "xx,xxx to" ou "xx.xxx to" e sem horário
    peso_liquido_geral = NAO_ENCONTRADO
    
    # Se achar 4 linhas (match's), selecionar a 3, se achar 5 linhas (match's) selecionar a 4.
    matches_validos = []

    for linha in texto.splitlines():
        m = re.search(r"\b(\d{1,3}\s*[.,]\s*\d{3})\s+to\b", linha, flags=re.IGNORECASE)
        if m:
            matches_validos.append(m.group(1).replace(",", ".").replace(" ", ""))

    peso_liquido_geral = None

    logger.debug(matches_validos)

    if len(matches_validos) == 4:
        peso_liquido_geral = matches_validos[2]  # 3º (índice 2)

    elif len(matches_validos) == 5:
        peso_liquido_geral = matches_validos[2]  # 3º (índice 3)

    # Gerdau Pinda: variações de "líquido" com 4–6 dígitos
    m_peso_pinda = re.search(r"(?i)[\s_]*l[ií]qu[ií]d(?:o|ouido|uido|oudo)?[\s_]*(?:kg)?[:：]{0,2}\s*\n?\s*([0-9]{4,6})",texto,)
    peso_liquido_pinda = m_peso_pinda.group(1) if m_peso_pinda else NAO_ENCONTRADO
    peso_liquido_final = (peso_liquido_geral if _encontrado(peso_liquido_geral) else peso_liquido_pinda)

    logger.debug("🎯 Dados extraídos (unificado):")
    logger.debug(f"Ticket (geral): {ticket_val} | Ticket (pinda): {ticket_val_pinda} | Final: {ticket_final}")
    logger.debug(f"NF (geral): {nota_fiscal_geral} | NF (pinda): {nota_fiscal_pinda} | Final: {nota_fiscal_final}")
    logger.debug(f"Peso (geral): {peso_liquido_geral} | Peso (pinda): {peso_liquido_pinda} | Final: {peso_liquido_final}")

    return {
        "ticket": ticket_final,
        "nota_fiscal": nota_fiscal_final,
        "peso_liquido": peso_liquido_final
    }
