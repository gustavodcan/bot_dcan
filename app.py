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

    # Regex ajustadas para pegar os dados com mais flexibilidade
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
    headers = {
        "Content-Type": "application/json",
        "Client-Token": CLIENT_TOKEN
    }
    try:
        res = requests.post(url, json=payload, headers=headers)
        print(f"Mensagem enviada para {numero}: {res.status_code}")
        print(f"Response da API: {res.text}")
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")

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

    if not estado:
        enviar_mensagem(numero, "👋 Olá! Tudo bem? Sou o bot de tickets da DCAN Transportes.\nPor acaso você seria motorista em viagem pela DCAN?")
        conversas[numero] = {"estado": "aguardando_confirmacao_motorista"}
        return jsonify(status="aguardando confirmação de motorista")

    if estado == "aguardando_confirmacao_motorista":
        if texto_recebido in ['sim', 's']:
            enviar_mensagem(numero, "✅ Perfeito! Para qual cliente a descarga foi realizada? ArcelorMittal, Gerdau, Raízen ou ProActiva?")
            conversas[numero]["estado"] = "aguardando_cliente"
        elif texto_recebido in ['não', 'nao', 'n']:
            enviar_mensagem(numero, "📞 Peço por gentileza então, que entre em contato com o número (XX) XXXX-XXXX. Obrigado!")
            conversas.pop(numero)
        else:
            enviar_mensagem(numero, "❓ Por favor, responda apenas SIM ou NÃO.")
        return jsonify(status="resposta motorista")

    if estado == "aguardando_cliente":
        cliente = texto_recebido.capitalize()
        conversas[numero]["dados"] = {"cliente": cliente}
        enviar_mensagem(numero, f"🚚 Obrigado! Cliente informado: {cliente}.\nPor gentileza, envie a foto do ticket.")
        conversas[numero]["estado"] = "aguardando_imagem"
        return jsonify(status="cliente recebido")

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
            except Exception as e:
                enviar_mensagem(numero, "❌ Erro ao baixar a imagem. Tente novamente.")
                return jsonify(status="erro ao baixar")

            dados = extrair_dados_da_imagem("ticket.jpg")
            msg = (
                f"📋 Recebi os dados:\n"
                f"Cliente: {conversas[numero]['dados'].get('cliente', 'Desconhecido')}\n"
                f"Peso Tara: {dados['peso_tara']}\n"
                f"Nota Fiscal: {dados['nota_fiscal']}\n"
                f"BRM MES: {dados['brm_mes']}\n\n"
                f"Está correto? Responda SIM ou NÃO."
            )
            conversas[numero]["estado"] = "aguardando_confirmacao"
            enviar_mensagem(numero, msg)
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
            enviar_mensagem(numero, "❓ Por favor, responda apenas SIM ou NÃO.")
        return jsonify(status="confirmação final")

    if "text" in data and "message" in data["text"]:
        if estado == "aguardando_imagem":
            enviar_mensagem(numero, "📸 Por favor, envie uma imagem do ticket para prosseguir.")
        elif estado in ["aguardando_confirmacao_motorista", "aguardando_cliente", "aguardando_confirmacao"]:
            enviar_mensagem(numero, "❓ Por favor, siga as instruções anteriores ou responda com SIM/NÃO.")
        else:
            enviar_mensagem(numero, "👋 Olá! Tudo bem? Sou o bot de tickets da DCAN Transportes.\nPor acaso você seria motorista em viagem pela DCAN?")
            conversas[numero] = {"estado": "aguardando_confirmacao_motorista"}
        return jsonify(status="mensagem fora de contexto redirecionada")

    return jsonify(status="sem ação definida")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000)
