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

def extrair_dados_da_imagem(caminho_imagem):
    img = Image.open(caminho_imagem)
    texto = pytesseract.image_to_string(img)

    print("📜 Texto detectado:")
    print(texto)

    peso = re.search(r"^Tara\s+\d{2}/\d{2}\s+\d{2}:\d{2}\s+(\d+)", texto, re.MULTILINE)
    nf = re.search(r"Fiscal[:\-]?\s*([\d/]+)", texto, re.IGNORECASE)
    brm = re.search(r"BRM MES[:\-]?\s*(\d+)", texto, re.IGNORECASE)

    return {
        "peso_tara": peso.group(1) if peso else "NÃO ENCONTRADO",
        "nota_fiscal": nf.group(1) if nf else "NÃO ENCONTRADO",
        "brm_mes": brm.group(1) if brm else "NÃO ENCONTRADO"
    }

def enviar_mensagem(numero, texto):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{API_TOKEN}/send-text"
    payload = {"phone": numero, "message": texto}
    headers = {"Content-Type": "application/json", "Client-Token": CLIENT_TOKEN}
    requests.post(url, json=payload, headers=headers)

def enviar_botoes_sim_nao(numero):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{API_TOKEN}/send-button"
    payload = {
        "phone": numero,
        "message": "Está correto? Por favor, selecione uma opção.",
        "buttons": [
            {"id": "btn_sim", "text": "Sim"},
            {"id": "btn_nao", "text": "Não"}
        ]
    }
    headers = {"Content-Type": "application/json", "Client-Token": CLIENT_TOKEN}
    requests.post(url, json=payload, headers=headers)

def enviar_lista_clientes(numero):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{API_TOKEN}/send-list-message"
    payload = {
        "phone": numero,
        "buttonText": "Escolher cliente",
        "description": "Para qual cliente foi a descarga?",
        "sections": [
            {
                "title": "Clientes disponíveis",
                "rows": [
                    {"id": "cliente_1", "title": "ArcelorMittal"},
                    {"id": "cliente_2", "title": "Gerdau"},
                    {"id": "cliente_3", "title": "Raizen"},
                    {"id": "cliente_4", "title": "ProActiva"},
                ]
            }
        ]
    }
    headers = {"Content-Type": "application/json", "Client-Token": CLIENT_TOKEN}
    requests.post(url, json=payload, headers=headers)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print("🛰️ Webhook recebido:")
    print(data)

    tipo = data.get("type")
    numero = data.get("phone") or data.get("from")
    texto_recebido = data.get("text", {}).get("message", "").strip().lower()
    estado = conversas.get(numero, {}).get("estado")

    if tipo != "ReceivedCallback":
        return jsonify(status="ignorado")

    # Botão SIM/NÃO
    if "buttonResponse" in data:
        resposta = data["buttonResponse"]["selectedDisplayText"].strip().lower()
        if estado == "aguardando_confirmacao":
            if resposta == "sim":
                enviar_mensagem(numero, "✅ Dados confirmados! Salvando as informações. Obrigado!")
                conversas.pop(numero, None)
            elif resposta == "não":
                enviar_mensagem(numero, "🔁 OK! Por favor, envie a foto do ticket novamente.")
                conversas[numero]["estado"] = "aguardando_imagem"
        elif estado == "aguardando_confirmacao_motorista":
            if resposta == "sim":
                enviar_lista_clientes(numero)
                conversas[numero]["estado"] = "aguardando_cliente"
            elif resposta == "não":
                enviar_mensagem(numero, "📞 Peço por gentileza que entre em contato com o número (XX) XXXX-XXXX.")
                conversas.pop(numero, None)
        return jsonify(status="resposta botão")

    # Lista de clientes
    if "listResponse" in data:
        cliente = data["listResponse"]["title"]
        conversas[numero] = {
            "estado": "aguardando_imagem",
            "dados": {"cliente": cliente}
        }
        enviar_mensagem(numero, f"🚚 Obrigado! Cliente informado: {cliente}.\nPor gentileza, envie a foto do ticket.")
        return jsonify(status="cliente selecionado")

    # Início da conversa
    if not estado:
        enviar_mensagem(numero, "👋 Olá! Tudo bem? Sou o bot de tickets da DCAN Transportes.\nVocê é motorista em viagem pela DCAN?")
        enviar_botoes_sim_nao(numero)
        conversas[numero] = {"estado": "aguardando_confirmacao_motorista"}
        return jsonify(status="aguardando confirmação de motorista")

    if estado == "aguardando_imagem":
        if "image" in data and data["image"].get("mimeType", "").startswith("image/"):
            url_img = data["image"]["imageUrl"]
            try:
                img_res = requests.get(url_img)
                with open("ticket.jpg", "wb") as f:
                    f.write(img_res.content)
            except Exception as e:
                enviar_mensagem(numero, "❌ Erro ao baixar a imagem. Tente novamente.")
                return jsonify(status="erro ao baixar")

            dados = extrair_dados_da_imagem("ticket.jpg")
            cliente = conversas[numero]['dados'].get('cliente', 'Desconhecido')
            msg = (
                f"📋 Recebi os dados:\n"
                f"Cliente: {cliente}\n"
                f"Peso: {dados['peso_tara']}\n"
                f"Nota Fiscal: {dados['nota_fiscal']}\n"
                f"BRM: {dados['brm_mes']}\n\n"
            )
            enviar_botoes_sim_nao(numero)
            conversas[numero]["estado"] = "aguardando_confirmacao"
            os.remove("ticket.jpg")
            return jsonify(status="imagem processada")
        else:
            enviar_mensagem(numero, "📸 Por favor, envie uma imagem do ticket para prosseguir.")
            return jsonify(status="aguardando imagem")

    if "text" in data and "message" in data["text"]:
        enviar_mensagem(numero, "📲 Use os botões disponíveis na conversa para continuar.")
        return jsonify(status="texto fora de contexto")

    return jsonify(status="sem ação definida")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000)
