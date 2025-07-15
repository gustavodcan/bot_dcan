from flask import Flask, request, jsonify
import requests
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import re
import os
import json
from google.oauth2 import service_account
from google.cloud import vision

app = Flask(__name__)
conversas = {}

pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

INSTANCE_ID = os.getenv("INSTANCE_ID")
API_TOKEN = os.getenv("API_TOKEN")
CLIENT_TOKEN = os.getenv("CLIENT_TOKEN")

clientes_validos = ["arcelormittal", "gerdau", "raízen", "mahle", "orizon", "cdr", "saae"]

def get_google_client():
    cred_path = "google_creds.json"
    if not os.path.exists(cred_path):
        raise FileNotFoundError("Arquivo de credencial não encontrado no caminho esperado.")

    with open(cred_path, "r") as f:
        creds_dict = json.load(f)

    credentials = service_account.Credentials.from_service_account_info(creds_dict)
    return vision.ImageAnnotatorClient(credentials=credentials)

def ler_texto_google_ocr(path_imagem):
    client = get_google_client()

    with open(path_imagem, "rb") as image_file:
        content = image_file.read()

    image = vision.Image(content=content)
    response = client.text_detection(image=image)
    texts = response.text_annotations

    return texts[0].description if texts else ""


def preprocessar_imagem(caminho):
    imagem = Image.open(caminho)

    # 2. Aumenta a imagem
    largura, altura = imagem.size
    imagem = imagem.resize((largura * 2, altura * 2), Image.LANCZOS)

    return imagem

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

    # 🎯 Ticket - captura número com ou sem barra e remove a barra depois
    ticket_match = re.search(r"(?:ticket|cket)[\s:]*([0-9/]{5,})", texto)
    ticket_val = ticket_match.group(1).replace("/", "") if ticket_match else "NÃO ENCONTRADO"

    # 📄 Outros Docs - aceita ponto antes dos dois pontos, hífen, espaços, etc
    outros_docs = re.search(r"outros[\s_]*docs[.:;\-]*[:]?[\s]*([0-9]{4,})", texto)

    # ⚖️ Peso Líquido - aceita erros de OCR tipo 'liquiduido', ':' repetido, etc
    peso_liquido = re.search(
        r"peso[\s_]*l[ií]qu[ií]d(?:o|ouido|uido|oudo)?[\s_]*(?:kg)?[:：]{1,2}\s*([0-9]{4,6})",
        texto
    )

    # 🧠 Log de debug pro Render ou local
    print("🎯 Dados extraídos:")
    print(f"Ticket: {ticket_val}")
    print(f"Outros Docs: {outros_docs.group(1) if outros_docs else 'Não encontrado'}")
    print(f"Peso Líquido: {peso_liquido.group(1) if peso_liquido else 'Não encontrado'}")

    return {
        "ticket": ticket_val,
        "outros_docs": outros_docs.group(1) if outros_docs else "NÃO ENCONTRADO",
        "peso_liquido": peso_liquido.group(1) if peso_liquido else "NÃO ENCONTRADO"
    }

def extrair_dados_cliente_arcelormittal(img, texto):
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
    print("📜 [GERDAU] Texto detectado:")
    print(texto)

    linhas = texto.splitlines()
    ticket_val = "NÃO ENCONTRADO"
    nf_val = "NÃO ENCONTRADO"
    peso_liquido_val = "NÃO ENCONTRADO"

    # 🎯 TICKET com exatamente 8 dígitos
    for linha in linhas:
        ticket_match = re.search(r"\b\d{8}\b", linha)
        if ticket_match:
            ticket_val = ticket_match.group()
            break

    # 📄 NOTA FISCAL antes do hífen
    for linha in linhas:
        nf_match = re.search(r"\b(\d+)-\d+\b", linha)
        if nf_match:
            nf_val = nf_match.group(1)
            break

    # ⚖️ PESO LÍQUIDO mais inteligente
    idx_linha_peso = -1
    for i, linha in enumerate(linhas):
        if "peso" in linha.lower() and "liqu" in linha.lower():
            idx_linha_peso = i
            break

    # Procura padrão "00,000 to" logo antes ou depois da linha
    if idx_linha_peso != -1:
        alvos = []
        if idx_linha_peso - 1 >= 0:
            alvos.append(linhas[idx_linha_peso - 1])
        if idx_linha_peso + 1 < len(linhas):
            alvos.append(linhas[idx_linha_peso + 1])
        if idx_linha_peso + 2 < len(linhas):
            alvos.append(linhas[idx_linha_peso + 2])

        for linha in alvos:
            match = re.search(r"\b(\d{2,3},\d{2,3})\s+to\b", linha)
            if match and not re.search(r"\d{2}:\d{2}:\d{2}", linha):  # ignora se tiver horário
                peso_liquido_val = match.group(1)
                break

    print("🎯 Dados extraídos:")
    print(f"Ticket: {ticket_val}")
    print(f"Nota Fiscal: {nf_val}")
    print(f"Peso Líquido: {peso_liquido_val}")

    return {
        "ticket": ticket_val,
        "nota_fiscal": nf_val,
        "peso_liquido": peso_liquido_val
    }

    
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

    try:
        img.save("ticket_pre_google.jpg")  # salvar temporário pra OCR
        texto = ler_texto_google_ocr("ticket_pre_google.jpg")
        os.remove("ticket_pre_google.jpg")
    except Exception as e:
        print(f"❌ Erro no OCR Google: {e}")
        return {"erro": "Falha no OCR"}

    texto = limpar_texto_ocr(texto)

    import sys
    print(f"📜 Texto detectado (cliente={cliente}):")
    print(texto)
    sys.stdout.flush()

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
                        f"Cliente: {cliente.title()}\n"
                        f"Ticket: {dados.get('ticket')}\n"
                        f"Nota Fiscal: {dados.get('nota_fiscal')}\n"
                        f"Peso Líquido: {dados.get('peso_liquido')}\n\n"
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
