import re

def extrair_dados_cliente_mahle(img, texto):
    print("📜 [MAHLE] Texto detectado:")
    print(texto)

    linhas = texto.splitlines()
    ticket_val = "NÃO ENCONTRADO"
    peso_liquido_val = "NÃO ENCONTRADO"
    nota_fiscal_val = "NÃO ENCONTRADO"

    indice_peso_liquido = -1

    for i, linha in enumerate(linhas):
        linha_lower = linha.lower()

        # Ticket
        if "ticket de pesagem" in linha_lower:
            match_ticket = re.search(r"ticket de pesagem\s*[-:]?\s*(\d+)", linha_lower)
            if match_ticket:
                ticket_val = match_ticket.group(1)
                print(f"Ticket encontrado: {ticket_val}")

        # Peso líquido
        if "peso líquid" in linha_lower and peso_liquido_val == "NÃO ENCONTRADO":
            for j in range(i+1, len(linhas)):
                linha_peso = linhas[j].strip().lower()
                if "kg" in linha_peso:
                    # Aqui o regex atualizado:
                    # só captura número que não tenha hífen grudado antes
                    match = re.search(r"(?:^|[^-\d])(\d+[.,]?\d*)\s*kg", linha_peso)
                    if match:
                        peso_liquido_val = match.group(1).replace(",", ".")
                        indice_peso_liquido = j
                        print(f"Peso líquido encontrado: {peso_liquido_val}")
                        break
            if peso_liquido_val != "NÃO ENCONTRADO":
                break  # Sai do for principal quando encontrar peso líquido

    # Nota fiscal só depois do peso líquido
    if indice_peso_liquido != -1:
        for linha in linhas[indice_peso_liquido+1:]:
            if re.match(r"^\d{4,}$", linha.strip()):
                nota_fiscal_val = linha.strip()
                print(f"Nota fiscal encontrada: {nota_fiscal_val}")
                break

    print("🎯 Dados extraídos:")
    print(f"Ticket: {ticket_val}")
    print(f"Peso Líquido: {peso_liquido_val}")
    print(f"Nota Fiscal: {nota_fiscal_val}")

    return {
        "ticket": ticket_val,
        "peso_liquido": peso_liquido_val,
        "nota_fiscal": nota_fiscal_val
    }

