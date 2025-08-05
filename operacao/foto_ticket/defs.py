import re

from operacao.foto_ticket.cdr import extrair_dados_cliente_cdr
from operacao.foto_ticket.arcelormittal import extrair_dados_cliente_arcelormittal
from operacao.foto_ticket.gerdau import extrair_dados_cliente_gerdau
from operacao.foto_ticket.mahle import extrair_dados_cliente_mahle
from operacao.foto_ticket.orizon import extrair_dados_cliente_orizon
from operacao.foto_ticket.rio_das_pedras import extrair_dados_cliente_rio_das_pedras
from operacao.foto_ticket.saae import extrair_dados_cliente_saae

def extrair_dados_por_cliente(cliente, texto_ocr):
    match cliente:
        case "cdr":
            return extrair_dados_cliente_cdr(None, texto_ocr)
        case "arcelormittal":
            return extrair_dados_cliente_arcelormittal(None, texto_ocr)
        case "gerdau":
            return extrair_dados_cliente_gerdau(None, texto_ocr)
        case "mahle":
            return extrair_dados_cliente_mahle(None, texto_ocr)
        case "orizon":
            return extrair_dados_cliente_orizon(None, texto_ocr)
        case "rio das pedras":
            return extrair_dados_cliente_rio_das_pedras(None, texto_ocr)
        case "saae":
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
    elif "mahle" in texto:
        return "mahle"
    elif "br-ml-pindamonhangaba" in texto:
        return "gerdau pindamonhangaba"
    elif "orizon" in texto:
        return "orizon"
    elif "cdr pedreira" in texto or "cor pedreira" in texto:
        return "cdr"
    elif "serviço autônomo" in texto or "servico autonomo" in texto:
        return "saae"
    elif "gerdau" in texto:
        return "gerdau"
    elif "arcelormittal" in texto or "arcelor" in texto or "am iracemapolis" in texto or "brm" in texto:
        return "arcelormittal"
    else:
        return "cliente_desconhecido"

def limpar_texto_ocr(texto):
    texto = texto.lower()
    texto = texto.replace("liq", "líquido")
    texto = texto.replace("outros docs", "outros_docs")
    texto = re.sub(r"[^\w\s:/\.,-]", "", texto)
    texto = re.sub(r"\s{2,}", " ", texto)
    return texto
