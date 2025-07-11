import re
def extrair_dados_cliente_arcelormittal(img, texto):
    peso = re.search(r"^Tara\s+\d{2}/\d{2}\s+\d{2}:\d{2}\s+(\d+)", texto, re.MULTILINE)
    nf = re.search(r"Fiscal[:\-]?\s*([\d/]+)", texto, re.IGNORECASE)
    brm = re.search(r"BRM MES[:\-]?\s*(\d+)", texto, re.IGNORECASE)
    return {
        "peso_tara": peso.group(1) if peso else "NÃO ENCONTRADO",
        "nota_fiscal": nf.group(1) if nf else "NÃO ENCONTRADO",
        "brm_mes": brm.group(1) if brm else "NÃO ENCONTRADO"
    }
