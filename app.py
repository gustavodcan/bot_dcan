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

clientes_validos = ["arcelormittal", "gerdau", "proactiva", "raízen"]

from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import re

# Caminho da imagem reimportada
caminho_imagem = "/mnt/data/b5b01b75-d672-4df2-8a55-550d7bc05c18.jpg"

def extrair_dados_cliente_arcelormittal(img, texto):
    peso = re.search(r"^Tara\s+\d{2}/\d{2}\s+\d{2}:\d{2}\s+(\d+)", texto, re.MULTILINE)
    nf = re.search(r"Fiscal[:\-]?\s*([\d/]+)", texto, re.IGNORECASE)
    brm = re.search(r"BRM MES[:\-]?\s*(\d+)", texto, re.IGNORECASE)
    return {
        "peso_tara": peso.group(1) if peso else "NÃO ENCONTRADO",
        "nota_fiscal": nf.group(1) if nf else "NÃO ENCONTRADO",
        "brm_mes": brm.group(1) if brm else "NÃO ENCONTRADO"
    }

def extrair_dados_cliente_gerdau(img, texto):
    return extrair_dados_cliente_arcelormittal(img, texto)

def extrair_dados_cliente_proactiva(img, texto):
    return extrair_dados_cliente_arcelormittal(img, texto)

def extrair_dados_cliente_raízen(img, texto):
    return extrair_dados_cliente_arcelormittal(img, texto)

def extrair_dados_cliente_mahle(img, texto):
    return extrair_dados_cliente_arcelormittal(img, texto)

def extrair_dados_cliente_orizon(img, texto):
    return extrair_dados_cliente_arcelormittal(img, texto)

def extrair_dados_cliente_cdr(img, texto):
    return extrair_dados_cliente_arcelormittal(img, texto)

def extrair_dados_cliente_saae(img, texto):
    return extrair_dados_cliente_arcelormittal(img, texto)

def extrair_dados_da_imagem(caminho_imagem, cliente):
    img = Image.open(caminho_imagem)
    img = ImageOps.grayscale(img)
    img = img.point(lambda x: 0 if x < 150 else 255, '1')
    config = r'--psm 6'
    texto = pytesseract.image_to_string(img, config=config)

    print("📜 Texto detectado:")
    print(texto)

    cliente = cliente.lower()
    match cliente:
        case "arcelormittal":
            return extrair_dados_cliente_arcelormittal(img, texto)
        case "gerdau":
            return extrair_dados_cliente_gerdau(img, texto)
        case "proactiva":
            return extrair_dados_cliente_proactiva(img, texto)
        case "raízen":
            return extrair_dados_cliente_raízen(img, texto)
        case "mahle":
            return extrair_dados_cliente_mahle(img, texto)
        case "orizon":
            return extrair_dados_cliente_orizon(img, texto)
        case "cdr":
            return extrair_dados_cliente_cdr(img, texto)
        case "saae":
            return extrair_dados_cliente_saae(img, texto)
        case _:
            return {
                "peso_tara": "CLIENTE NÃO SUPORTADO",
                "nota_fiscal": "CLIENTE NÃO SUPORTADO",
                "brm_mes": "CLIENTE NÃO SUPORTADO"
            }

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
                {"id": "arcelormittal", "title": "ArcelorMittal", "description": ""},
                {"id": "gerdau", "title": "Gerdau", "description": ""},
                {"id": "mahle", "title": "Mahle", "description": ""},
                {"id": "raízen", "title": "Raízen", "description": ""},
                {"id": "orizon", "title": "Orizon", "description": ""},
                {"id": "cdr", "title": "CDR", "description": ""},
                {"id": "saae", "title": "SAAE", "description": ""},
            ]
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    print(f"[🟪 Lista enviada] Status {res.status_code}: {res.text}")

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

            cliente = conversas[numero]["dados"].get("cliente", "")
            dados = extrair_dados_da_imagem("ticket.jpg", cliente)
            msg = (
                f"📋 Recebi os dados:\n"
                f"Cliente: {conversas[numero]['dados'].get('cliente', 'Desconhecido')}\n"
                f"Peso: {dados['peso_tara']}\n"
                f"Nota Fiscal: {dados['nota_fiscal']}\n"
                f"BRM: {dados['brm_mes']}\n\n"
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

    if "text" in data and "message" in data["text"]:
        if estado == "aguardando_imagem":
            enviar_mensagem(numero, "📸 Por favor, envie uma imagem do ticket para prosseguir.")
        elif estado in ["aguardando_confirmacao_motorista", "aguardando_cliente", "aguardando_confirmacao"]:
            enviar_mensagem(numero, "❓ Por favor, siga as instruções anteriores ou clique nos botões.")
        else:
            enviar_botoes_sim_nao(numero, "👋 Olá! Você é motorista em viagem pela DCAN?")
            conversas[numero] = {"estado": "aguardando_confirmacao_motorista"}
        return jsonify(status="mensagem fora de contexto redirecionada")

    return jsonify(status="sem ação definida")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000, debug=True)
