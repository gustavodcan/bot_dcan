import re, os, logging
from integracoes.google_vision import preprocessar_imagem, ler_texto_google_ocr
from mensagens import enviar_mensagem
from operacao.foto_ticket.cdr import extrair_dados_cliente_cdr
from operacao.foto_ticket.arcelormittal import extrair_dados_cliente_arcelormittal
from operacao.foto_ticket.gerdau import extrair_dados_cliente_gerdau
from operacao.foto_ticket.mahle import extrair_dados_cliente_mahle
from operacao.foto_ticket.orizon import extrair_dados_cliente_orizon
from operacao.foto_ticket.rio_das_pedras import extrair_dados_cliente_rio_das_pedras
from operacao.foto_ticket.saae import extrair_dados_cliente_saae

logger = logging.getLogger(__name__)

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

#Uso do OCR, conversação da imagem para o texto
def extrair_dados_da_imagem(caminho_imagem, numero):
    conversas[numero] = conversas.get(numero, {})
    
    img = preprocessar_imagem(caminho_imagem)
    img.save("preprocessado.jpg")
    with open("preprocessado.jpg", "rb") as f:
        imagem_bytes = f.read()

    try:
        img.save("ticket_pre_google.jpg")
        texto = ler_texto_google_ocr("ticket_pre_google.jpg")

    except Exception as e:
        print(f"❌ Erro no OCR Google: {e}")
        return {"erro": "Falha no OCR"}

    texto = limpar_texto_ocr(texto)
    conversas[numero]["ocr_texto"] = texto

    cliente_detectado = detectar_cliente_por_texto(texto)
    print(f"[🕵️] Cliente detectado automaticamente: {cliente_detectado}")

    #Detecta qual o cliente lido/extraido
    conversas[numero]["cliente"] = cliente_detectado

    if cliente_detectado == "cliente_desconhecido":
        enviar_mensagem(numero, "❌ Não consegui identificar o cliente a partir da imagem. Por favor, envie novamente com mais clareza ou entre em contato com seu programador.")
        return {"erro": "cliente não identificado"}

    # ⚠️ Fluxo especial pro SAAE
    if cliente_detectado == "saae":
        conversas[numero]["estado"] = "aguardando_destino_saae"
        enviar_mensagem(numero, "🛣️ Cliente SAAE detectado!\nPor favor, informe a *origem da carga*\n(ex: ETA Vitória).")
        return {"status": "aguardando destino saae"}

    from operacao.foto_ticket.defs import extrair_dados_por_cliente
    
    #Adiciona o cliente no dicionário
    dados = extrair_dados_por_cliente(cliente_detectado, texto)
    return dados
