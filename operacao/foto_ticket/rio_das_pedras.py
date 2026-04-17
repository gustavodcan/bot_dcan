# ===== Standard library =====
import re
import logging

logger = logging.getLogger(__name__)

def extrair_dados_cliente_rio_das_pedras(img, texto):
    logger.debug("📜 [RIO DAS PEDRAS] Texto detectado:")
    logger.debug(texto)

    nota_val = "NÃO ENCONTRADO"
    peso_liquido_val = "NÃO ENCONTRADO"

    linhas = texto.lower().splitlines()

    # 🧾 Buscar número na linha que contém 'notas fiscais'
    for linha in linhas:
        if "notas fiscais" in linha:
            match_nf = re.search(r"\b(\d{6,})\b", linha)
            if match_nf:
                nota_val = match_nf.group(1)
                logger.debug(f"Nota fiscal encontrada: {nota_val}")
                break

    # ⚖️ Peso líquido — aceita "líquidouido", "líquldo", etc mesmo sem "peso" antes
    for linha in linhas:
        if re.search(r"l[ií1!|][qg][uúü][ií1!|][d0o][a-z]*[:：-]*", linha):
            logger.debug(f"[👁️] Linha suspeita de peso líquido: {linha}")
            match_peso = re.search(r"(\d{1,3}(?:[.,]\d{3}){1,2})\s*k[g9]", linha)
            if match_peso:
                peso_raw = match_peso.group(1)
                logger.debug(f"[⚖️] Peso capturado: {peso_raw}")
                try:
                    peso_limpo = peso_raw.replace(",", "").replace(".", ",")
                    peso_liquido_val = str(int(float(peso_limpo)))
                    logger.debug(f"[✅] Peso líquido final: {peso_liquido_val}")
                except Exception as e:
                    logger.debug(f"[❌] Erro ao converter peso: {e}")
                    peso_liquido_val = "NÃO ENCONTRADO"
                break

    logger.debug("🎯 Dados extraídos:")
    logger.debug(f"Nota Fiscal: {nota_val}")
    logger.debug(f"Peso Líquido: {peso_liquido_val}")

    return {
        "nota_fiscal": nota_val,
        "peso_liquido": peso_liquido_val,
        "ticket": "N/A"
    }