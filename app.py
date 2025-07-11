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

def enviar_mensagem(numero, mensagem):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{API_TOKEN}/send-text"
    payload = {
        "phone": numero,
        "message": mensagem
    }
    requests.post(url, json=payload)

def enviar_botoes_sim_nao(numero, mensagem):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{API_TOKEN}/send-buttons"
    payload = {
        "phone": numero,
        "message": mensagem,
        "buttons": [
            {"buttonId": "sim", "buttonText": {"displayText": "Sim"}, "type": 1},
            {"buttonId": "nao", "buttonText": {"displayText": "Não"}, "type": 1}
        ]
    }
    requests.post(url, json=payload)

def enviar_lista_clientes(numero, mensagem):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{API_TOKEN}/send-list"
    payload = {
        "phone": numero,
        "message": mensagem,
        "sections": [
            {
                "title": "Clientes",
                "rows": [
                    {"rowId": cliente, "title": cliente.title()}
                    for cliente in clientes_validos
                ]
            }
        ],
        "buttonText": "Selecionar Cliente"
    }
    requests.post(url, json=payload)

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

            msg = (
                f"📋 Recebi os dados:\n"
                f"Cliente: {cliente.title()}\n"
                f"Ticket: {dados.get('ticket')}\n"
                f"Outros Docs: {dados.get('outros_docs')}\n"
                f"Peso Líquido: {dados.get('peso_liquido')}\n\n"
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
