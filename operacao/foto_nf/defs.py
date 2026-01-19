import re, logging

logger = logging.getLogger(__name__)

def extrair_chave_acesso(texto):
    # Remove quebras de linha e normaliza texto
    texto = texto.replace("\n", " ")
    
    numeros = re.findall(r"\d+", texto)
    numeros_validos = [n for n in numeros if 4 <= len(n) <= 6]

    if len(numeros_validos) >= 10:
        matches = " ".join(numeros_validos)
        
    logger.debug(f"Texto extraido da nota: {matches}")

    for bloco in matches:
        chave = re.sub(r'\D', '', bloco)  # Remove tudo que não for número
        if len(chave) == 44:
            return chave

    return None  # Se nenhuma chave válida encontrada

    if chave:
        logger.debug(f"🔑 Chave de acesso encontrada: {chave}")
    else:
        logger.debug("❌ Chave de acesso não encontrada.")
