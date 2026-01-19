import re, logging

logger = logging.getLogger(__name__)

def extrair_chave_acesso(texto):
    # Remove quebras de linha e normaliza texto
    texto = texto.replace("\n", " ")
    logger.debug(f"Texto extraido da nota: {texto}")

    match = re.search(
        r'(?:\b\d{4}(?:\s\d{4}){10}\b|\b\d{44}\b)',
        texto
    )

    if match:
        chave = re.sub(r'\D', '', match.group(0))
        logger.debug(f"🔑 Chave de acesso encontrada: {chave}")
        return chave

    logger.debug("❌ Chave de acesso não encontrada.")
    return None
