from flask import Flask, request, jsonify
import requests
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import re
import os

app = Flask(__name__)
conversas = {}

pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

INSTANCE_ID = os.getenv("INSTANCE_ID")
API_TOKEN = os.getenv("API_TOKEN")
CLIENT_TOKEN = os.getenv("CLIENT_TOKEN")

clientes_validos = ["arcelormittal", "gerdau", "raízen", "mahle", "orizon", "cdr", "saae"]

def preprocessar_imagem(img_path):
    img = Image.open(img_path).convert("L")  # escala de cinza
    img = img.filter(ImageFilter.MedianFilter())  # remove ruído
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.5)  # aumenta contraste
    img = img.point(lambda x: 0 if x < 160 else 255)  # binariza (preto e branco)
    return img

def limpar_texto_ocr(texto):
    texto = texto.lower()
    texto = texto.replace("kg;", "kg:")
    texto = texto.replace("kg)", "kg:")
    texto = texto.replace("ko:", "kg:")
    texto = texto.replace("liq", "líquido")
    texto = texto.replace("outros docs", "outros_docs")
    texto = re.sub(r"[^\w\s:/\.,-]", "", texto)  # remove símbolos bizarros
    texto = re.sub(r"\s{2,}", " ", texto)
    return texto

def ocr_azure(imagem_bytes, endpoint, key):
    ocr_url = f"{endpoint}/vision/v3.2/ocr"
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/octet-stream"
    }

    response = requests.post(ocr_url, headers=headers, data=imagem_bytes)
    response.raise_for_status()
    return response.json()

def enviar_mensagem(numero, texto):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{API_TOKEN}/send-text"
    payload = {"phone": numero, "message": texto}
    headers = {
        "Content-Type": "application/json",
        "Client-Token": CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    print(f"[🟢 Texto simples enviado] Status {res.status_code}: {res.text}")


def enviar_botoes_sim_nao(numero, mensagem):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{API_TOKEN}/send-button-list"
    payload = {
        "phone": numero,
        "message": mensagem,
        "buttonList": {
            "buttons": [
                {"id": "sim", "label": "Sim"},
                {"id": "nao", "label": "Não"}
            ]
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    print(f"[🟦 Botões enviados] Status {res.status_code}: {res.text}")


def enviar_lista_clientes(numero, mensagem):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{API_TOKEN}/send-option-list"
    payload = {
        "phone": numero,
        "message": mensagem,
        "optionList": {
            "title": "Clientes DCAN",
            "buttonLabel": "Escolha o cliente",
            "options": [
                {"id": "arcelormittal", "title": "ArcelorMittal"},
                {"id": "gerdau", "title": "Gerdau"},
                {"id": "mahle", "title": "Mahle"},
                {"id": "raízen", "title": "Raízen"},
                {"id": "orizon", "title": "Orizon"},
                {"id": "cdr", "title": "CDR"},
                {"id": "saae", "title": "SAAE"},
            ]
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    print(f"[🟪 Lista enviada] Status {res.status_code}: {res.text}")


def extrair_dados_cliente_cdr(img, texto):
    print("📜 [CDR] Texto detectado:")
    print(texto)

    ticket = re.search(r"mtr[’']?s?:?\s*(\d{5,})", texto)
    outros_docs = re.search(r"outros[_\s]?docs[:\-]?\s*(\d+)", texto)
    peso_liquido = re.search(r"peso\s+líquido\s*\(kg\)[:\-]?\s*(\d{4,6})", texto)

    return {
        "ticket": ticket.group(1) if ticket else "NÃO ENCONTRADO",
        "outros_docs": outros_docs.group(1) if outros_docs else "NÃO ENCONTRADO",
        "peso_liquido": peso_liquido.group(1) if peso_liquido else "NÃO ENCONTRADO"
    }

def extrair_dados_cliente_arcelormittal(img, texto):
    print(f"[{cliente.upper()}] Começando extração de dados...")
    print("📜 Texto recebido para extração:")
    print(texto)
    
    peso = re.search(r"^Tara\s+\d{2}/\d{2}\s+\d{2}:\d{2}\s+(\d+)", texto, re.MULTILINE)
    nf = re.search(r"Fiscal[:\-]?\s*([\d/]+)", texto, re.IGNORECASE)
    brm = re.search(r"BRM MES[:\-]?\s*(\d+)", texto, re.IGNORECASE)

    return {
        "peso_tara": peso.group(1) if peso else "NÃO ENCONTRADO",
        "nota_fiscal": nf.group(1) if nf else "NÃO ENCONTRADO",
        "brm_mes": brm.group(1) if brm else "NÃO ENCONTRADO"
    }

def extrair_dados_cliente_gerdau(img, texto):
    return {"nota_fiscal": "placeholder", "peso_tara": "placeholder", "numero_viagem": "placeholder"}

def extrair_dados_cliente_raízen(img, texto):
    return {"protocolo": "placeholder", "peso_liquido": "placeholder", "doc_referencia": "placeholder"}

def extrair_dados_cliente_mahle(img, texto):
    return {"lote": "placeholder", "peso": "placeholder", "nota_fiscal": "placeholder"}

def extrair_dados_cliente_orizon(img, texto):
    return {"codigo": "placeholder", "peso": "placeholder", "documento": "placeholder"}

def extrair_dados_cliente_saae(img, texto):
    return {"protocolo": "placeholder", "volume": "placeholder", "data": "placeholder"}

def extrair_dados_da_imagem(caminho_imagem, cliente):
    img = preprocessar_imagem(caminho_imagem)
    img.save("preprocessado.jpg")
    with open("preprocessado.jpg", "rb") as f:
        imagem_bytes = f.read()


    # Chaves falsas - substitui pelas reais no ambiente
    AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT", "https://ocr-bot-dcan.cognitiveservices.azure.com")
    AZURE_KEY = os.getenv("AZURE_KEY", "EO6zkOWHACWpvBqvCSChh9kVh30qboMx9Q6dI52UFnnt7unNo4HLJQQJ99BGACZoyfiXJ3w3AAAFACOGspAv")

        try:
        ocr_json = ocr_azure(imagem_bytes, AZURE_ENDPOINT, AZURE_KEY)
    except Exception as e:
        print(f"❌ Erro ao chamar Azure OCR: {e}")
        return {"erro": "Falha no OCR"}

    # Junta todo o texto OCR em uma string só
    texto = ""
    for region in ocr_json.get("regions", []):
        for line in region.get("lines", []):
            for word in line["words"]:
                texto += word["text"] + " "

    print(f"📜 Texto detectado ({cliente}):")
    print(texto)

    cliente = cliente.lower()
    match cliente:
        case "cdr":
            return extrair_dados_cliente_cdr(None, texto)
        case "arcelormittal":
            return extrair_dados_cliente_arcelormittal(None, texto)
        case "gerdau":
            return extrair_dados_cliente_gerdau(None, texto)
        case "raízen":
            return extrair_dados_cliente_raízen(None, texto)
        case "mahle":
            return extrair_dados_cliente_mahle(None, texto)
        case "orizon":
            return extrair_dados_cliente_orizon(None, texto)
        case "saae":
            return extrair_dados_cliente_saae(None, texto)
        case _:
            return {
                "ticket": "CLIENTE NÃO SUPORTADO",
                "outros_docs": "CLIENTE NÃO SUPORTADO",
                "peso_liquido": "CLIENTE NÃO SUPORTADO"
            }


# funções enviar_mensagem, enviar_botoes_sim_nao, enviar_lista_clientes seguem iguais...

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print("🛰️ Webhook recebido:")
    print(data)

    tipo = data.get("type")
    numero = data.get("phone") or data.get("from")

    texto_recebido = (
        data.get("buttonsResponseMessage", {}).get("buttonId") or
        data.get("listResponseMessage", {}).get("selectedRowId") or
        data.get("text", {}).get("message", "")
    ).strip().lower()

    estado = conversas.get(numero, {}).get("estado")

    if tipo != "ReceivedCallback":
        return jsonify(status="ignorado")

    if not estado:
        enviar_botoes_sim_nao(numero, "👋 Olá! Tudo bem? Sou o bot de tickets da DCAN Transportes.\nVocê é motorista em viagem pela DCAN?")
        conversas[numero] = {"estado": "aguardando_confirmacao_motorista"}
        return jsonify(status="aguardando confirmação de motorista")

    if estado == "aguardando_confirmacao_motorista":
        if texto_recebido in ['sim', 's']:
            enviar_lista_clientes(numero, "✅ Perfeito! Para qual cliente a descarga foi realizada?")
            conversas[numero]["estado"] = "aguardando_cliente"
    
        elif texto_recebido in ['não', 'nao', 'n']:
            enviar_mensagem(numero, "📞 Peço por gentileza então, que entre em contato com o número (XX) XXXX-XXXX. Obrigado!")
            conversas.pop(numero)
        else:
            enviar_botoes_sim_nao(numero, "❓ Por favor, clique em *Sim* ou *Não*.")
        return jsonify(status="resposta motorista")

    if estado == "aguardando_cliente":
        if texto_recebido in clientes_validos:
            conversas[numero]["dados"] = {"cliente": texto_recebido.title()}
            enviar_mensagem(numero, f"🚚 Obrigado! Cliente informado: {texto_recebido.title()}.\nPor gentileza, envie a foto do ticket.")
            conversas[numero]["estado"] = "aguardando_imagem"
        else:
            enviar_lista_clientes(numero, "❓ Por favor, selecione um cliente da lista abaixo.")
        return jsonify(status="verificação cliente")

    if estado == "aguardando_imagem":
        if "image" in data and data["image"].get("mimeType", "").startswith("image/"):
            url_img = data["image"]["imageUrl"]
            try:
                img_res = requests.get(url_img)
                if img_res.status_code == 200:
                    with open("ticket.jpg", "wb") as f:
                        f.write(img_res.content)
                else:
                    enviar_mensagem(numero, "❌ Erro ao baixar a imagem. Tente novamente.")
                    return jsonify(status="erro ao baixar")
            except Exception:
                enviar_mensagem(numero, "❌ Erro ao baixar a imagem. Tente novamente.")
                return jsonify(status="erro ao baixar")

            cliente = conversas[numero]["dados"].get("cliente", "").lower()
            dados = extrair_dados_da_imagem("ticket.jpg", cliente)

            # Monta a mensagem com base no cliente
            match cliente:
                case "cdr":
                    msg = (
                        f"📋 Recebi os dados:\n"
                        f"Cliente: {cliente.title()}\n"
                        f"Ticket: {dados.get('ticket')}\n"
                        f"Outros Docs: {dados.get('outros_docs')}\n"
                        f"Peso Líquido: {dados.get('peso_liquido')}\n\n"
                        f"Está correto?"
                    )
                case "gerdau":
                    msg = (
                        f"📋 Recebi os dados:\n"
                        f"Cliente: Gerdau\n"
                        f"Nota Fiscal: {dados.get('nota_fiscal')}\n"
                        f"Peso Tara: {dados.get('peso_tara')}\n"
                        f"Nº Viagem: {dados.get('numero_viagem')}\n\n"
                        f"Está correto?"
                    )
                case "raízen":
                    msg = (
                        f"📋 Recebi os dados:\n"
                        f"Cliente: Raízen\n"
                        f"Protocolo: {dados.get('protocolo')}\n"
                        f"Peso Líquido: {dados.get('peso_liquido')}\n"
                        f"Doc Referência: {dados.get('doc_referencia')}\n\n"
                        f"Está correto?"
                    )
                case "mahle":
                    msg = (
                        f"📋 Recebi os dados:\n"
                        f"Cliente: Mahle\n"
                        f"Lote: {dados.get('lote')}\n"
                        f"Peso: {dados.get('peso')}\n"
                        f"Nota Fiscal: {dados.get('nota_fiscal')}\n\n"
                        f"Está correto?"
                    )
                case "orizon":
                    msg = (
                        f"📋 Recebi os dados:\n"
                        f"Cliente: Orizon\n"
                        f"Código: {dados.get('codigo')}\n"
                        f"Peso: {dados.get('peso')}\n"
                        f"Documento: {dados.get('documento')}\n\n"
                        f"Está correto?"
                    )
                case "saae":
                    msg = (
                        f"📋 Recebi os dados:\n"
                        f"Cliente: SAAE\n"
                        f"Protocolo: {dados.get('protocolo')}\n"
                        f"Volume: {dados.get('volume')}\n"
                        f"Data: {dados.get('data')}\n\n"
                        f"Está correto?"
                    )
                case _:
                    msg = (
                        f"📋 Recebi os dados:\n"
                        f"Cliente: {cliente.title()}\n"
                        f"Peso Tara: {dados.get('peso_tara')}\n"
                        f"Nota Fiscal: {dados.get('nota_fiscal')}\n"
                        f"BRM: {dados.get('brm_mes')}\n\n"
                        f"Está correto?"
                    )

            conversas[numero]["dados"].update(dados)
            conversas[numero]["estado"] = "aguardando_confirmacao"
            enviar_botoes_sim_nao(numero, msg)
            os.remove("ticket.jpg")
            return jsonify(status="imagem processada")
        else:
            enviar_mensagem(numero, "📸 Por favor, envie uma imagem do ticket para prosseguir.")
            return jsonify(status="aguardando imagem")

    if estado == "aguardando_confirmacao":
        if texto_recebido in ['sim', 's']:
            enviar_mensagem(numero, "✅ Dados confirmados! Salvando as informações. Obrigado!")
            conversas.pop(numero)
        elif texto_recebido in ['não', 'nao', 'n']:
            enviar_mensagem(numero, "🔁 OK! Por favor, envie a foto do ticket novamente.")
            conversas[numero]["estado"] = "aguardando_imagem"
        else:
            enviar_botoes_sim_nao(numero, "❓ Por favor, clique em *Sim* ou *Não*.")
        return jsonify(status="confirmação final")

    return jsonify(status="sem ação definida")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000, debug=True)
