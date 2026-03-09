# ===== Standard library =====
import re
import logging
import os

# ===== Local: mensagens =====
from mensagens import enviar_mensagem

# ===== Local: integracoes =====
from integracoes.google_vision import (
    preprocessar_imagem,
    ler_texto_google_ocr,
)

# ===== Local: clientes =====
from operacao.foto_ticket.cdr import extrair_dados_cliente_cdr
from operacao.foto_ticket.arcelormittal import extrair_dados_cliente_arcelormittal
from operacao.foto_ticket.gerdau import extrair_dados_cliente_gerdau
from operacao.foto_ticket.mahle import extrair_dados_cliente_mahle
from operacao.foto_ticket.orizon import extrair_dados_cliente_orizon
from operacao.foto_ticket.rio_das_pedras import extrair_dados_cliente_rio_das_pedras
from operacao.foto_ticket.saae import extrair_dados_cliente_saae
from operacao.foto_ticket.ternium import extrair_dados_cliente_ternium
from operacao.foto_ticket.eucatex import extrair_dados_cliente_eucatex
from operacao.foto_ticket.gescrap import extrair_dados_cliente_gescrap
from operacao.foto_ticket.veolia_gerdau import extrair_dados_cliente_veolia_gerdau

logger = logging.getLogger(__name__)

def extrair_dados_por_cliente(cliente, texto_ocr):
    match cliente:
        case "cdr":
            return extrair_dados_cliente_cdr(None, texto_ocr)
        case "veolia gerdau":
            return extrair_dados_cliente_veolia_gerdau(None, texto_ocr)
        case "arcelormittal":
            return extrair_dados_cliente_arcelormittal(None, texto_ocr)
        case "gerdau":
            return extrair_dados_cliente_gerdau(None, texto_ocr)
        case "ternium":
            return extrair_dados_cliente_ternium(None, texto_ocr)
        case "mahle":
            return extrair_dados_cliente_mahle(None, texto_ocr)
        case "orizon":
            return extrair_dados_cliente_orizon(None, texto_ocr)
        case "eucatex":
            return extrair_dados_cliente_eucatex(None, texto_ocr)
        case "gescrap":
            return extrair_dados_cliente_gescrap(None, texto_ocr)
        case "rio das pedras":
            return extrair_dados_cliente_rio_das_pedras(None, texto_ocr)
        case "proactiva":
            return extrair_dados_cliente_saae(None, texto_ocr)
        case _:
            return {
                "ticket": "CLIENTE NÃO SUPORTADO",
                "outros_docs": "CLIENTE NÃO SUPORTADO",
                "peso_liquido": "CLIENTE NÃO SUPORTADO"
            }

def detectar_cliente_por_texto(texto):
    texto = texto.lower()

    if "ticket de pesagem recebimento" in texto:
        return "rio das pedras"
    elif "veolia" in texto and "gerdau" in texto:
        return "veolia gerdau"
    elif "orizon" in texto:
        return "orizon"
    elif "cdr pedreira" in texto or "cor pedreira" in texto or "cgr três marias" in texto:
        return "cdr"
    elif "gerdau" in texto or "br-ml-pindamonhangaba" in texto:
        return "gerdau"
    elif "arcelormittal" in texto or "arcelor" in texto or "am iracemapolis" in texto or "brm" in texto or "celormittal" in texto or "arcelormit" in texto or "rcelormittal" in texto:
        return "arcelormittal"
    elif "ternium" in texto:
        return "ternium"
    elif "mahle" in texto:
        return "mahle"
    elif "eucatex" in texto:
        return "eucatex"
    elif "gescrap" in texto:
        return "gescrap"
    elif "serviço autônomo" in texto or "servico autonomo" in texto or "prefeitura do" in texto or "sistema produtor" in texto or "municipio de" in texto or "prefeitura municipal" in texto:
        return "proactiva"
    else:
        return "cliente_desconhecido"

def limpar_texto_ocr(texto):
    texto = texto.lower()
    #texto = texto.replace("liq", "líquido")
    texto = texto.replace("outros docs", "outros_docs")
    texto = re.sub(r"[^\w\s:/\.,-]", "", texto)
    texto = re.sub(r"\s{2,}", " ", texto)
    return texto
