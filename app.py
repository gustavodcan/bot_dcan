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

def detectar_cliente_por_texto(texto):
    texto = texto.lower()

    if "ticket de pesagem recebimento" in texto:
        return "rio das pedras"
    elif "mahle" in texto:
        return "mahle"
    elif "orizon" in texto:
        return "orizon"
    elif "cdr pedreira" in texto or "cor pedreira" in texto:
        return "cdr"
    elif "serviço autônomo" in texto or "servico autonomo" in texto:
        return "saae"
    elif "gerdau" in texto:
        return "gerdau"
    elif "arcelormittal" in texto:
        return "arcelormittal"
    else:
        return "cliente_desconhecido"

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

    # Nota fiscal
    nf_match = re.search(r"fiscal[:\-]?\s*([\d]+)", texto, re.IGNORECASE)
    nota_val = nf_match.group(1) if nf_match else "NÃO ENCONTRADO"

    # BRM
    brm_match = re.search(r"brm\s+mes[:\-]?\s*(\d+)", texto, re.IGNORECASE)
    brm_val = brm_match.group(1) if brm_match else "NÃO ENCONTRADO"

    # Peso líquido: captura todos os números que aparecem sozinhos em uma linha
    numeros = re.findall(r"^\s*(\d{4,6})\s*$", texto, re.MULTILINE)
    print(f"Números isolados encontrados: {numeros}")

    peso_liquido = "NÃO ENCONTRADO"

    if len(numeros) == 1:
        peso_liquido = numeros[0]
    elif len(numeros) > 1:
        try:
            # Soma todos menos o último
            valores = list(map(int, numeros[:-1]))
            peso_liquido = str(sum(valores))
        except Exception as e:
            print(f"[❌] Erro ao somar pesos: {e}")
            peso_liquido = "NÃO ENCONTRADO"

    print("🎯 Dados extraídos:")
    print(f"Nota Fiscal: {nota_val}")
    print(f"BRM MES: {brm_val}")
    print(f"Peso Líquido: {peso_liquido}")

    return {
        "nota_fiscal": nota_val,
        "brm_mes": brm_val,
        "peso_liquido": peso_liquido
    }

def extrair_dados_cliente_gerdau(img, texto):
    print("[GERDAU] Extraindo dados...")
    print("📜 Texto para extração:")
    print(texto)

    # Ticket: exatamente 8 dígitos
    ticket_match = re.search(r"\b(\d{8})\b", texto)
    ticket_val = ticket_match.group(1) if ticket_match else "NÃO ENCONTRADO"

    # Nota fiscal: número antes do primeiro hífen
    matches_nota = re.findall(r"\b(\d{3,10})-\d{1,3}\b", texto)
    if matches_nota:
        nota_fiscal_val = matches_nota[0]

    # Peso líquido: procura por 'xx,xxx to' sem horário na linha
    peso_liquido_val = "NÃO ENCONTRADO"
    linhas = texto.splitlines()
    for linha in linhas:
        match = re.search(r"\b(\d{2,3}[.,]\d{3})\s+to\b", linha)
        if match and not re.search(r"\d{2}:\d{2}:\d{2}", linha):
            peso_liquido_val = match.group(1).replace(",", ".")
            break

    print("🎯 Dados extraídos:")
    print(f"Ticket: {ticket_val}")
    print(f"Nota Fiscal: {nota_fiscal_val}")
    print(f"Peso Líquido: {peso_liquido_val}")

    return {
        "ticket": ticket_val,
        "nota_fiscal": nota_fiscal_val,
        "peso_liquido": peso_liquido_val
    }

def extrair_dados_cliente_rio_das_pedras(img, texto):
    print("📜 [RIO DAS PEDRAS] Texto detectado:")
    print(texto)

    nota_val = "NÃO ENCONTRADO"
    peso_liquido_val = "NÃO ENCONTRADO"

    linhas = texto.lower().splitlines()

    # 🧾 Buscar número na linha que contém 'notas fiscais'
    for linha in linhas:
        if "notas fiscais" in linha:
            match_nf = re.search(r"\b(\d{6,})\b", linha)
            if match_nf:
                nota_val = match_nf.group(1)
                print(f"Nota fiscal encontrada: {nota_val}")
                break

    # ⚖️ Peso líquido — aceita "líquidouido", "líquldo", etc mesmo sem "peso" antes
    for linha in linhas:
        if re.search(r"l[ií1!|][qg][uúü][ií1!|][d0o][a-z]*[:：-]*", linha):
            print(f"[👁️] Linha suspeita de peso líquido: {linha}")
            match_peso = re.search(r"(\d{1,3}(?:[.,]\d{3}){1,2})\s*kg", linha)
            if match_peso:
                peso_raw = match_peso.group(1)
                print(f"[⚖️] Peso bruto capturado: {peso_raw}")
                try:
                    peso_limpo = peso_raw.replace(".", "").replace(",", "")
                    peso_liquido_val = str(int(peso_limpo))
                    print(f"[✅] Peso líquido final: {peso_liquido_val}")
                except Exception as e:
                    print(f"[❌] Erro ao converter peso: {e}")
                    peso_liquido_val = "NÃO ENCONTRADO"
                break

    print("🎯 Dados extraídos:")
    print(f"Nota Fiscal: {nota_val}")
    print(f"Peso Líquido: {peso_liquido_val}")

    return {
        "nota_fiscal": nota_val,
        "peso_liquido": peso_liquido_val,
        "ticket": "NÃO APLICÁVEL"
    }

def extrair_dados_cliente_mahle(img, texto):
    print("📜 [MAHLE] Texto detectado:")
    print(texto)

    linhas = texto.splitlines()
    ticket_val = "NÃO ENCONTRADO"
    peso_liquido_val = "NÃO ENCONTRADO"
    nota_fiscal_val = "NÃO ENCONTRADO"

    indice_peso_liquido = -1

    for i, linha in enumerate(linhas):
        linha_lower = linha.lower()

        # Ticket
        if "ticket de pesagem" in linha_lower:
            match_ticket = re.search(r"ticket de pesagem\s*[-:]?\s*(\d+)", linha_lower)
            if match_ticket:
                ticket_val = match_ticket.group(1)
                print(f"Ticket encontrado: {ticket_val}")

        # Peso líquido
        if "peso líquid" in linha_lower and peso_liquido_val == "NÃO ENCONTRADO":
            for j in range(i+1, len(linhas)):
                linha_peso = linhas[j].strip().lower()
                if "kg" in linha_peso:
                    # Aqui o regex atualizado:
                    # só captura número que não tenha hífen grudado antes
                    match = re.search(r"(?:^|[^-\d])(\d+[.,]?\d*)\s*kg", linha_peso)
                    if match:
                        peso_liquido_val = match.group(1).replace(",", ".")
                        indice_peso_liquido = j
                        print(f"Peso líquido encontrado: {peso_liquido_val}")
                        break
            if peso_liquido_val != "NÃO ENCONTRADO":
                break  # Sai do for principal quando encontrar peso líquido

    # Nota fiscal só depois do peso líquido
    if indice_peso_liquido != -1:
        for linha in linhas[indice_peso_liquido+1:]:
            if re.match(r"^\d{4,}$", linha.strip()):
                nota_fiscal_val = linha.strip()
                print(f"Nota fiscal encontrada: {nota_fiscal_val}")
                break

    print("🎯 Dados extraídos:")
    print(f"Ticket: {ticket_val}")
    print(f"Peso Líquido: {peso_liquido_val}")
    print(f"Nota Fiscal: {nota_fiscal_val}")

    return {
        "ticket": ticket_val,
        "peso_liquido": peso_liquido_val,
        "nota_fiscal": nota_fiscal_val
    }

def extrair_dados_cliente_orizon(img, texto):
    print("📜 [ORIZON] Texto detectado:")
    print(texto)

    ticket_val = "NÃO ENCONTRADO"
    peso_liquido_val = "NÃO ENCONTRADO"

    texto_lower = texto.lower()

    # --- Peso Líquido ---
    match_peso = re.search(
        r"peso[\s_]*l[ií1!|][qg][uúü][ií1!|][d0o][a-z]*kg[:：]{0,2}\s*([0-9]{4,6})",
        texto_lower
    )
    if match_peso:
        peso_liquido_val = match_peso.group(1)
        print(f"Peso líquido encontrado: {peso_liquido_val}")

    # --- Ticket (padrão tipo TB0000108249 ou variações) ---
    match_ticket = re.search(
        r"\b[tт][bв][оo0]?[0-9]{6,}\b",
        texto_lower
    )
    if match_ticket:
        ticket_val = match_ticket.group(0).upper()
        print(f"Operação (ticket) encontrada: {ticket_val}")

    print("🎯 Dados extraídos:")
    print(f"Ticket: {ticket_val}")
    print(f"Peso Líquido: {peso_liquido_val}")

    return {
        "ticket": ticket_val,
        "peso_liquido": peso_liquido_val,
        "nota_fiscal": "NÃO APLICÁVEL"
    }
    
def extrair_dados_cliente_saae(img, texto):
    print("📜 [SAAE] Texto detectado:")
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

def extrair_dados_da_imagem(caminho_imagem, numero):
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

    cliente_detectado = detectar_cliente_por_texto(texto)
    print(f"[🕵️] Cliente detectado automaticamente: {cliente_detectado}")

    # 🚨 Adiciona isso aqui!
    conversas[numero]["cliente"] = cliente_detectado

    if cliente_detectado == "cliente_desconhecido":
        enviar_mensagem(numero, "❌ Não consegui identificar o cliente a partir da imagem. Por favor, envie novamente com mais clareza ou entre em contato com a DCAN.")
        return {"erro": "cliente não identificado"}

    match cliente_detectado:
        case "cdr":
            return extrair_dados_cliente_cdr(None, texto)
        case "arcelormittal":
            return extrair_dados_cliente_arcelormittal(None, texto)
        case "gerdau":
            return extrair_dados_cliente_gerdau(None, texto)
        case "rio das pedras":
            return extrair_dados_cliente_rio_das_pedras(None, texto)
        case "mahle":
            return extrair_dados_cliente_mahle(None, texto)
        case "orizon":
            dados_parciais = extrair_dados_cliente_orizon(None, texto)
            # Armazena os dados parciais
            conversas[numero]["estado"] = "aguardando_nota_orizon"
            conversas[numero]["dados_parciais"] = dados_parciais
            conversas[numero]["cliente"] = "orizon"
            enviar_mensagem(numero, "📄 Identifiquei que o cliente é *Orizon*.\nPor favor, me diga o número da *Nota Fiscal* agora.")
            # return {"status": "aguardando nota fiscal"}
        case "saae":
            return extrair_dados_cliente_saae(None, texto)
        case _:
            return {
                "ticket": "CLIENTE NÃO SUPORTADO",
                "outros_docs": "CLIENTE NÃO SUPORTADO",
                "peso_liquido": "CLIENTE NÃO SUPORTADO"
            }
    dados["cliente"] = cliente_detectado  # adiciona o cliente no dicionário
    return dados

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
            enviar_mensagem(numero, "✅ Perfeito! Por favor, envie a foto do ticket.")
            conversas[numero]["estado"] = "aguardando_imagem"
    
        elif texto_recebido in ['não', 'nao', 'n']:
            enviar_mensagem(numero, "📞 Peço por gentileza então, que entre em contato com o número (XX) XXXX-XXXX. Obrigado!")
            conversas.pop(numero)
        else:
            enviar_botoes_sim_nao(numero, "❓ Por favor, clique em *Sim* ou *Não*.")
        return jsonify(status="resposta motorista")

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

            dados = extrair_dados_da_imagem("ticket.jpg", numero)
            cliente = conversas[numero].get("cliente")

            if not cliente or cliente == "cliente_desconhecido":
                enviar_mensagem(numero, "❌ Cliente não identificado. Por favor, envie uma nova imagem ou fale com a DCAN.")
                conversas[numero]["estado"] = "aguardando_imagem"
                return jsonify(status="cliente desconhecido")

            if "dados" not in conversas[numero]:
                conversas[numero]["dados"] = {}

            conversas[numero]["dados"].update(dados)
            conversas[numero]["cliente"] = cliente
            conversas[numero]["estado"] = "aguardando_confirmacao"

            match cliente:
                case "cdr":
                    msg = (
                        f"📋 Recebi os dados:\n"
                        f"Cliente: CDR\n"
                        f"Ticket: {dados.get('ticket')}\n"
                        f"Nota Fiscal: {dados.get('outros_docs')}\n"
                        f"Peso Líquido: {dados.get('peso_liquido')}\n\n"
                        f"Está correto?"
                    )
                case "rio das pedras":
                    msg = (
                        f"📋 Recebi os dados:\n"
                        f"Cliente: Rio das Pedras\n"
                        f"Nota Fiscal: {dados.get('nota_fiscal')}\n"
                        f"Peso Líquido: {dados.get('peso_liquido')}\n"
                        f"Ticket: {dados.get('ticket')}\n\n"
                        f"Está correto?"
                    )
                case "mahle":
                    msg = (
                        f"📋 Recebi os dados:\n"
                        f"Cliente: Mahle\n"
                        f"Ticket: {dados.get('ticket')}\n"
                        f"Peso Líquido: {dados.get('peso_liquido')}\n"
                        f"Nota Fiscal: {dados.get('nota_fiscal')}\n\n"
                        f"Está correto?"
                    )
                case "orizon":
                    msg = (
                        f"📋 Recebi os dados:\n"
                        f"Cliente: Orizon\n"
                        f"Ticket: {dados.get('ticket')}\n"
                        f"Peso Líquido: {dados.get('peso_liquido')}\n"
                        f"Nota Fiscal: {dados.get('nota_fiscal', 'Não se aplica')}\n\n"
                        f"Está correto?"
                    )
                case "saae":
                    msg = (
                        f"📋 Recebi os dados:\n"
                        f"Cliente: SAAE\n"
                        f"Ticket: {dados.get('ticket')}\n"
                        f"Nota Fiscal: {dados.get('outros_docs')}\n"
                        f"Peso Líquido: {dados.get('peso_liquido')}\n\n"
                        f"Está correto?"
                    )
                case "gerdau":
                    msg = (
                        f"📋 Recebi os dados:\n"
                        f"Cliente: Gerdau\n"
                        f"Ticket: {dados.get('ticket')}\n"
                        f"Nota Fiscal: {dados.get('nota_fiscal')}\n"
                        f"Peso Líquido: {dados.get('peso_liquido')}\n\n"
                        f"Está correto?"
                    )
                case "arcelormittal":
                    msg = (
                        f"📋 Recebi os dados:\n"
                        f"Cliente: ArcelorMittal\n"
                        f"Peso Líquido: {dados.get('peso_liquido')}\n"
                        f"Nota Fiscal: {dados.get('nota_fiscal')}\n"
                        f"Ticket: {dados.get('brm_mes')}\n\n"
                        f"Está correto?"
                    )
                case _:
                    msg = (
                        f"⚠️ Cliente '{cliente}' ainda não é suportado no momento.\n"
                        f"Por favor, envie um novo ticket ou fale com a DCAN."
                    )

            enviar_botoes_sim_nao(numero, msg)
            os.remove("ticket.jpg")
            return jsonify(status="imagem processada")

        else:
            enviar_mensagem(numero, "📸 Por favor, envie uma imagem do ticket para prosseguir.")
            return jsonify(status="aguardando imagem")
            
    if estado == "aguardando_nota_orizon":
        nota_digitada = re.search(r"\b\d{4,}\b", texto_recebido)
    
        if nota_digitada:
            nota_val = nota_digitada.group(0)
            dados_parciais = conversas[numero].get("dados_parciais", {})
            dados_parciais["nota_fiscal"] = nota_val
            conversas[numero]["dados"] = dados_parciais
            conversas[numero]["estado"] = "aguardando_confirmacao"

        msg = (
            f"📋 Recebi os dados:\n"
            f"Cliente: Orizon\n"
            f"Ticket: {dados_parciais.get('ticket')}\n"
            f"Peso Líquido: {dados_parciais.get('peso_liquido')}\n"
            f"Nota Fiscal: {nota_val}\n\n"
            f"Está correto?"
        )
        enviar_botoes_sim_nao(numero, msg)
    else:
        enviar_mensagem(numero, "❌ Não entendi a nota fiscal. Por favor, envie apenas o número da nota (ex: *7878*).")
    return jsonify(status="nota fiscal recebida ou inválida")
    
    if estado == "aguardando_confirmacao":
        if texto_recebido in ['sim', 's']:
            enviar_mensagem(numero, "✅ Dados confirmados! Salvando as informações. Obrigado!")
            conversas.pop(numero)
        elif texto_recebido in ['não', 'nao', 'n']:
            enviar_mensagem(numero, "🔁 OK! Por favor, envie a foto do ticket novamente.")
            conversas[numero]["estado"] = "aguardando_imagem"
            conversas[numero].pop("cliente", None)
            conversas[numero].pop("dados", None)
        else:
            enviar_botoes_sim_nao(numero, "❓ Por favor, clique em *Sim* ou *Não*.")
        return jsonify(status="confirmação final")

    else:
        print(f"⚠️ Estado inesperado: {estado} para o número {numero}")
        enviar_mensagem(numero, "⚠️ Estado desconhecido. Por favor, envie a imagem do ticket novamente.")
        conversas[numero]["estado"] = "aguardando_imagem"
        return jsonify(status="estado inesperado")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000, debug=True)
