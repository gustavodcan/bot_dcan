from operacao.foto_ticket.cdr import extrair_dados_cliente_cdr
from operacao.foto_ticket.arcelormittal import extrair_dados_cliente_arcelormittal
from operacao.foto_ticket.gerdau import extrair_dados_cliente_gerdau
from operacao.foto_ticket.gerdaupinda import extrair_dados_cliente_gerdaupinda
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
        case "gerdau pindamonhangaba":
            return extrair_dados_cliente_gerdaupinda(None, texto_ocr)
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
