import re

def extrair_dados_cliente_gerdaupinda(img, texto):
    print("📜 [Gerdau Pinda] Texto detectado:")
    print(texto)

    # 🎯 Ticket - captura número com ou sem barra e remove a barra depois
    ticket_match = re.search(r"(?:processo)[\s:]*([0-9/]{5,})", texto)
    ticket_val = ticket_match.group(1) if ticket_match else "NÃO ENCONTRADO"

    # 📄 Outros Docs - aceita ponto antes dos dois pontos, hífen, espaços, etc
    outros_docs = re.search(r"docto[:：]?\s*nf\s*[-–—]?\s*(\d{4,8})", texto, re.IGNORECASE)

    # ⚖️ Peso Líquido - aceita erros de OCR tipo 'liquiduido', ':' repetido, etc
    peso_liquido = re.search(
        r"(?i)[\s_]*l[ií]qu[ií]d(?:o|ouido|uido|oudo)?[\s_]*(?:kg)?[:：]{0,2}\s*\n?([0-9]{4,6})",
        texto
    )

    # 🧠 Log de debug pro Render ou local
    print("🎯 Dados extraídos:")
    print(f"Ticket: {ticket_val}")
    print(f"Outros Docs: {outros_docs.group(1) if outros_docs else 'Não encontrado'}")
    print(f"Peso Líquido: {peso_liquido.group(1) if peso_liquido else 'Não encontrado'}")

    return {
        "ticket": ticket_val,
        "outros_docs": outros_docs.group(1) if outros_docs else "NÃO ENCONTRADO",
        "peso_liquido": peso_liquido.group(1) if peso_liquido else "NÃO ENCONTRADO",
        "nota_fiscal": outros_docs.group(1) if outros_docs else "NÃO ENCONTRADO"
    }

def extrair_dados_cliente_gerdau(img, texto):
    print("[GERDAU] Extraindo dados...")
    print("📜 Texto para extração:")
    print(texto)

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

    print("🎯 Dados extraídos:")
    print(f"Ticket: {ticket_val}")
    print(f"Nota Fiscal: {nota_fiscal_val}")
    print(f"Peso Líquido: {peso_liquido_val}")

    return {
        "ticket": ticket_val,
        "nota_fiscal": nota_fiscal_val,
        "peso_liquido": peso_liquido_val
    }
