# ===== Standard library =====
import re
import logging

logger = logging.getLogger(__name__)

def extrair_dados_cliente_arcelormittal(img, texto):
    logger.debug("📜 Texto recebido para extração:")
    logger.debug(texto)

    nf_match = re.search(r"fiscal[:\-]?\s*([\d]+)", texto, re.IGNORECASE)
    # Se não encontrar usando "fiscal", tenta buscar padrão tipo "10847/1"
    if not nf_match:
        alternativa_match = re.search(r"\b(\d{3,})(?=/[1-9][0-9]?)\b", texto)
        nota_val = alternativa_match.group(1) if alternativa_match else "NÃO ENCONTRADO"
    else:
        nota_val = nf_match.group(1)

    # BRM
    brm_match = re.search(r"[be][rfi](?:m|im)\s+mes[:\-]?\s*(\d+)", texto, re.IGNORECASE)
    brm_val = brm_match.group(1) if brm_match else "NÃO ENCONTRADO"

    # Peso líquido: captura todos os números que aparecem sozinhos em uma linha
    numeros = re.findall(r"^\s*(\d{4,6})\s*$", texto, re.MULTILINE)
    logger.debug(f"Números isolados encontrados: {numeros}")

    peso_liquido = "NÃO ENCONTRADO"

    try:
        # Pega sempre o último número da lista
        ultimo_numero = int(numeros[-1])

        # Busca a última linha que contém "pb XXXX kg"
        linhas_pb = re.findall(r"^.*pb\s+(\d{4,6})\s+kg.*$", texto, re.MULTILINE | re.IGNORECASE)
        if linhas_pb:
            valor_pb = int(linhas_pb[-1])
            peso_liquido = str(valor_pb - ultimo_numero)
        else:
            logger.debug("[❌] Valor entre 'pb' e 'kg' não encontrado.")
            peso_liquido = "NÃO ENCONTRADO"
    except Exception as e:
        logger.debug(f"[❌] Erro ao calcular peso líquido: {e}")
        peso_liquido = "NÃO ENCONTRADO"

    logger.debug("🎯 Dados extraídos:")
    logger.debug(f"Nota Fiscal: {nota_val}")
    logger.debug(f"BRM MES: {brm_val}")
    logger.debug(f"Peso Líquido: {peso_liquido}")

    return {
        "nota_fiscal": nota_val,
        "ticket": brm_val,
        "peso_liquido": peso_liquido
    }