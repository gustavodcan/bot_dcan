import re

def extrair_dados_cliente_rio_das_pedras(img, texto):
    print("📜 [RIO DAS PEDRAS] Texto detectado:")
    print(texto)

    nota_val = "NÃO ENCONTRADO"
    peso_liquido_val = "NÃO ENCONTRADO"

    linhas = texto.lower().splitlines()

    # 🧾 Buscar número na linha que contém 'notas fiscais'
    for linha in linhas:
        if "notas fiscais" in linha:
            match_nf = re.search(r"\b(\d{6,})\b", linha)
            if match_nf:
                nota_val = match_nf.group(1)
                print(f"Nota fiscal encontrada: {nota_val}")
                break

    # ⚖️ Peso líquido — aceita "líquidouido", "líquldo", etc mesmo sem "peso" antes
    for linha in linhas:
        if re.search(r"l[ií1!|][qg][uúü][ií1!|][d0o][a-z]*[:：-]*", linha):
            print(f"[👁️] Linha suspeita de peso líquido: {linha}")
            match_peso = re.search(r"(\d{1,3}(?:[.,]\d{3}){1,2})\s*kg", linha)
            if match_peso:
                peso_raw = match_peso.group(1)
                print(f"[⚖️] Peso capturado: {peso_raw}")
                try:
                    peso_limpo = peso_raw.replace(".", "").replace(",", "")
                    peso_liquido_val = str(int(peso_limpo))
                    print(f"[✅] Peso líquido final: {peso_liquido_val}")
                except Exception as e:
                    print(f"[❌] Erro ao converter peso: {e}")
                    peso_liquido_val = "NÃO ENCONTRADO"
                break

    print("🎯 Dados extraídos:")
    print(f"Nota Fiscal: {nota_val}")
    print(f"Peso Líquido: {peso_liquido_val}")

    return {
        "nota_fiscal": nota_val,
        "peso_liquido": peso_liquido_val,
        "ticket": "N/A"
    }
