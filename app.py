from flask import Flask, request, jsonify
import requests
from PIL import Image
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

def extrair_dados_cliente_cdr(img, texto):
    print("📜 [CDR] Texto detectado:")
    print(texto)

    ticket = re.search(r"ticket[:\-]?\s*(\d{5,}/\d{4})", texto, re.IGNORECASE)
    outros_docs = re.search(r"outros\s+docs\.?\s*[:\-]?\s*(\d+)", texto, re.IGNORECASE)
    peso_liquido = re.search(r"peso\s+líquido.*?[:\-]?\s*(\d[\d\.,]*)", texto, re.IGNORECASE)

    return {
        "ticket": ticket.group(1) if ticket else "NÃO ENCONTRADO",
        "outros_docs": outros_docs.group(1) if outros_docs else "NÃO ENCONTRADO",
        "peso_liquido": peso_liquido.group(1) if peso_liquido else "NÃO ENCONTRADO"
    }

def extrair_dados_da_imagem(caminho_imagem, cliente):
    img = Image.open(caminho_imagem)
    texto = pytesseract.image_to_string(img)

    print("📜 Texto detectado:")
    print(texto)

    cliente = cliente.lower()
    match cliente:
        case "cdr":
            return extrair_dados_cliente_cdr(img, texto)
        case _:
            return {
                "ticket": "CLIENTE NÃO SUPORTADO",
                "outros_docs": "CLIENTE NÃO SUPORTADO",
                "peso_liquido": "CLIENTE NÃO SUPORTADO"
            }

def enviar_mensagem(numero, texto):
    print(f"[ENVIO DE MENSAGEM] {numero}: {texto}")

def enviar_botoes_sim_nao(numero, mensagem):
    print(f"[ENVIO DE BOTÕES] {numero}: {mensagem}")

def enviar_lista_clientes(numero, mensagem):
    print(f"[ENVIO DE LISTA] {numero}: {mensagem}")

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

    return jsonify(status="sem ação definida")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000, debug=True)