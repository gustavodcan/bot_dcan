#Importação de Bibliotecas
from flask import Flask, request, jsonify
from datetime import datetime
from PIL import Image, ImageEnhance, ImageFilter
from google.oauth2.service_account import Credentials
from google.cloud import vision
import requests, re, os, json, gspread

app = Flask(__name__)
conversas = {}

#Trazendo Variaveis do Render
INSTANCE_ID = os.getenv("INSTANCE_ID")
API_TOKEN = os.getenv("API_TOKEN")
CLIENT_TOKEN = os.getenv("CLIENT_TOKEN")

#Conexão do OCR Google
def get_google_vision_client():
    cred_path = "/etc/secrets/GOOGLE_CREDS_JSON"
    with open(cred_path, "r") as f:
        creds_dict = json.load(f)

    credentials = service_account.Credentials.from_service_account_info(creds_dict)
    return vision.ImageAnnotatorClient(credentials=credentials)

#Conexão do Planilha Google
def conectar_google_sheets():
    cred_path = "/etc/secrets/acc_servico"
    with open(cred_path, 'r') as f:
        cred_json_str = f.read()
    cred_info = json.loads(cred_json_str)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(cred_info, scopes=scopes)
    client = gspread.authorize(creds)
    return client

#Ativa o uso do OCR
def ler_texto_google_ocr(path_imagem):
    client = get_google_vision_client()

    with open(path_imagem, "rb") as image_file:
        content = image_file.read()

    image = vision.Image(content=content)
    response = client.text_detection(image=image)
    texts = response.text_annotations

    return texts[0].description if texts else ""

#Identificação de cliente através do texto extraído
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
    elif "arcelormittal" in texto or "arcelor" in texto or "am iracemapolis" in texto:
        return "arcelormittal"
    else:
        return "cliente_desconhecido"

#Pequeno processamento de imagem *upscaling*
def preprocessar_imagem(caminho):
    imagem = Image.open(caminho)

    largura, altura = imagem.size
    imagem = imagem.resize((largura * 2, altura * 2), Image.LANCZOS)

    return imagem

#Tratar texto OCR, deixar tudo em minisculo e caracteres
def limpar_texto_ocr(texto):
    texto = texto.lower()
    texto = texto.replace("kg;", "kg:")
    texto = texto.replace("kg)", "kg:")
    texto = texto.replace("ko:", "kg:")
    texto = texto.replace("liq", "líquido")
    texto = texto.replace("outros docs", "outros_docs")
    texto = re.sub(r"[^\w\s:/\.,-]", "", texto)
    texto = re.sub(r"\s{2,}", " ", texto)
    return texto

#Envia texto simples para "Motorista"
def enviar_mensagem(numero, texto):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{API_TOKEN}/send-text"
    payload = {"phone": numero, "message": texto}
    headers = {
        "Content-Type": "application/json",
        "Client-Token": CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    print(f"[🟢 Texto simples enviado] Status {res.status_code}: {res.text}")

#Envia "Sim" e "Não" simples para "Motorista
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

#Extraí Ticket, Nota Fiscal e Peso do cliente CDR
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
        "peso_liquido": peso_liquido.group(1) if peso_liquido else "NÃO ENCONTRADO",
        "nota_fiscal": outros_docs.group(1) if outros_docs else "NÃO ENCONTRADO"
    }

#Extraí Ticket, Nota Fiscal e Peso do cliente ArcelorMittal
def extrair_dados_cliente_arcelormittal(img, texto):
    print("📜 Texto recebido para extração:")
    print(texto)

    # Nota fiscal
    nf_match = re.search(r"fiscal[:\-]?\s*([\d]+)", texto, re.IGNORECASE)
    nota_val = nf_match.group(1) if nf_match else "NÃO ENCONTRADO"

    # BRM
    brm_match = re.search(r"[be][rfi](?:m|im)\s+mes[:\-]?\s*(\d+)", texto, re.IGNORECASE)
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
        "ticket": brm_val,
        "peso_liquido": peso_liquido
    }

#Extraí Ticket, Nota Fiscal e Peso do cliente Gerdau
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

#Extraí Ticket, Nota Fiscal e Peso do cliente Rio das Pedras
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
        "ticket": "N/A"
    }

#Extraí Ticket, Nota Fiscal e Peso do cliente Mahle
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

#Extraí Ticket, Nota Fiscal e Peso do cliente Orizon
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

#Extraí Ticket, Nota Fiscal e Peso do cliente SAAE
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
        "nota_fiscal": ticket_val,
        "outros_docs": outros_docs.group(1) if outros_docs else "NÃO ENCONTRADO",
        "peso_liquido": peso_liquido.group(1) if peso_liquido else "NÃO ENCONTRADO"
    }

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
        try:
            os.remove("ticket.jpg")
        except FileNotFoundError:
            pass
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
        case "saae":
            return extrair_dados_cliente_saae(None, texto)
        case _:
            return {
                "ticket": "CLIENTE NÃO SUPORTADO",
                "outros_docs": "CLIENTE NÃO SUPORTADO",
                "peso_liquido": "CLIENTE NÃO SUPORTADO"
            }
    #Adiciona o cliente no dicionário
    dados["cliente"] = cliente_detectado
    return dados

#Identifica o tipo de mensagem recebida
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
        
    #Se o bot não esta aguardando nada:
    if not estado:
        enviar_botoes_sim_nao(numero, "👋 Olá! Tudo bem?\nSou o bot de tickets da DCAN Transportes.\n\nVocê é motorista em viagem pela DCAN?")
        conversas[numero] = {"estado": "aguardando_confirmacao_motorista"}
        return jsonify(status="aguardando confirmação de motorista")

    #Se o bot esta aguardando "sim" ou "não" do motorista:
    if estado == "aguardando_confirmacao_motorista":
        if texto_recebido in ['sim', 's']:
            enviar_mensagem(numero, "✅ Perfeito! Por favor, envie a foto do ticket.")
            conversas[numero]["estado"] = "aguardando_imagem"
        elif texto_recebido in ['não', 'nao', 'n']:
            enviar_mensagem(numero, "📞 Peço por gentileza então, que entre em contato com o número (11) 91253-8457.\nObrigado!")
            conversas.pop(numero)
        else:
            enviar_botoes_sim_nao(numero, "❓ Por favor, clique em *Sim* ou *Não*.")
        return jsonify(status="resposta motorista")

    #Se o bot esta aguardando a foto do motorista:
    if estado == "aguardando_imagem":
        if "image" in data and data["image"].get("mimeType", "").startswith("image/"):
            url_img = data["image"]["imageUrl"]
            try:
                img_res = requests.get(url_img)
                if img_res.status_code == 200:
                    with open("ticket.jpg", "wb") as f:
                        f.write(img_res.content)
                #Quebra de url ou tempo de resposta
                else:
                    enviar_mensagem(numero, "❌ Erro ao baixar a imagem. Tente novamente.")
                    return jsonify(status="erro ao baixar")
            except Exception:
                enviar_mensagem(numero, "❌ Erro ao baixar a imagem. Tente novamente.")
                return jsonify(status="erro ao baixar")

            dados = extrair_dados_da_imagem("ticket.jpg", numero)

            #Para o fluxo se cliente for SAAE e espera destino
            if dados.get("status") == "aguardando destino saae":
                return jsonify(status="aguardando destino saae")

            #Continua normal para os outros
            cliente = conversas[numero].get("cliente")

            if dados.get("erro") == "cliente não identificado":
                conversas[numero]["estado"] = "aguardando_imagem"
                return jsonify(status="cliente desconhecido (mensagem já enviada)")

            conversas[numero]["cliente"] = cliente
            conversas[numero]["dados"] = dados
            try:
                os.remove("ticket.jpg")
            except FileNotFoundError:
                pass

            #Se o cliente for Orizon, já solicita nota
            nota = dados.get("nota_fiscal", "").strip().upper()
            if cliente == "orizon" or (cliente == "cdr" and nota in ["NÃO ENCONTRADO", "", None]):
                conversas[numero]["estado"] = "aguardando_nota_manual"
                enviar_mensagem(numero, "🧾 Por favor, envie o número da nota fiscal para continuar\n(Ex: *7878*).")
                return jsonify(status="solicitando nota manual")

            #Checagem de campos obrigatórios com valores reais
            ticket_ou_brm = dados.get("ticket") or dados.get("brm_mes")
            campos_obrigatorios = {
                "ticket ou brm_mes": ticket_ou_brm,
                "peso_liquido": dados.get("peso_liquido"),
                "nota_fiscal": dados.get("nota_fiscal")
            }

            dados_faltando = [
                nome for nome, valor in campos_obrigatorios.items()
                if not valor or "NÃO ENCONTRADO" in str(valor).upper()
            ]

            #Se estiver faltando qualquer dado essencial
            if dados_faltando:
                enviar_mensagem(
                    numero,
                    f"⚠️ Não consegui identificar todas informações\n"
                    "Por favor, tire uma nova foto do ticket com mais nitidez e envie novamente."
                )
                conversas[numero]["estado"] = "aguardando_imagem"
                conversas[numero].pop("dados", None)
                try:
                    os.remove("ticket.jpg")
                except FileNotFoundError:
                    pass
                return jsonify(status="dados incompletos, aguardando nova imagem")

            #Mensagem padrão para confirmação
            msg = (
                f"📋 Recebi os dados:\n"
                f"Cliente: {cliente.title()}\n"
                f"Ticket: {ticket_ou_brm}\n"
                f"Peso Líquido: {dados.get('peso_liquido')}\n"
                f"Nota Fiscal: {dados.get('nota_fiscal') or dados.get('outros_docs') or 'Não encontrada'}\n\n"
                f"Está correto?"
            )
            conversas[numero]["estado"] = "aguardando_confirmacao"
            enviar_botoes_sim_nao(numero, msg)
            return jsonify(status="dados extraídos e aguardando confirmação")

        else:
            enviar_mensagem(numero, "📸 Por favor, envie uma imagem do ticket para prosseguir.")
            return jsonify(status="aguardando imagem")
            
    #Se o bot esta aguardando o numero da nota:
    if estado == "aguardando_nota_manual":
        nota_digitada = re.search(r"\b\d{4,}\b", texto_recebido)
        if nota_digitada:
            nota_val = nota_digitada.group(0)

            #Recupera os dados atuais e o cliente
            dados_atuais = conversas[numero].get("dados", {})
            cliente = conversas[numero].get("cliente")
            texto_ocr = conversas[numero].get("ocr_texto", "")

            #Se os dados anteriores estão bugados, reexecuta extração só para Orizon
            if cliente == "orizon":
                novos_dados = extrair_dados_cliente_orizon(None, texto_ocr)
                dados_atuais.update(novos_dados)  # atualiza ticket e peso_liquido

            #Atualiza nota manual
            dados_atuais["nota_fiscal"] = nota_val
            conversas[numero]["dados"] = dados_atuais


            #Checagem de campos obrigatórios
            campos_obrigatorios = ["ticket", "peso_liquido", "nota_fiscal"]
            dados_faltando = [campo for campo in campos_obrigatorios if not dados_atuais.get(campo) or "NÃO ENCONTRADO" in str(dados_atuais.get(campo)).upper()]

            #Se estiver faltando qualquer dado essencial
            if dados_faltando:
                enviar_mensagem(
                    numero,
                    f"⚠️ Não consegui identificar todas informações\n"
                    "Por favor, tire uma nova foto do ticket com mais nitidez e envie novamente."
                )
                conversas[numero]["estado"] = "aguardando_imagem"
                conversas[numero].pop("dados", None)
                try:
                    os.remove("ticket.jpg")
                except FileNotFoundError:
                    pass
                return jsonify(status="dados incompletos, aguardando nova imagem")

            msg = (
                f"📋 Recebi os dados:\n"
                f"Cliente: {cliente.title()}\n"
                f"Ticket: {dados_atuais.get('ticket', 'NÃO ENCONTRADO') or dados_atuais.get('brm_mes', 'NÃO ENCONTRADO')}\n"
                f"Peso Líquido: {dados_atuais.get('peso_liquido', 'NÃO ENCONTRADO')}\n"
                f"Nota Fiscal: {nota_val}\n\n"
                f"Está correto?"
            )
            conversas[numero]["estado"] = "aguardando_confirmacao"
            enviar_botoes_sim_nao(numero, msg)
        else:
            enviar_mensagem(numero, "❌ Por favor, envie apenas o número da nota.\n(Ex: *7878*).")
        return jsonify(status="nota fiscal recebida ou inválida")

    #Bot está aguardando Origem SAAE
    if estado == "aguardando_destino_saae":
        destino_digitado = texto_recebido.strip().title()

        if len(destino_digitado) < 2:
            enviar_mensagem(numero, "❌ Por favor, informe um destino válido.")
            return jsonify(status="destino inválido")

        #Armazena o destino
        conversas[numero]["destino"] = destino_digitado

        #Continua a extração com base na imagem anterior
        try:
            dados = extrair_dados_cliente_saae(None, conversas[numero].get("ocr_texto", ""))
        except Exception as e:
            enviar_mensagem(numero, f"❌ Erro ao extrair os dados do ticket.\nTente novamente.\nErro: {e}")
            conversas[numero]["estado"] = "aguardando_imagem"
            return jsonify(status="erro extração saae")

        dados["destino"] = destino_digitado
        conversas[numero]["dados"] = dados
        conversas[numero]["estado"] = "aguardando_confirmacao"

        #Checagem de campos obrigatórios
        campos_obrigatorios = ["ticket", "peso_liquido", "destino"]
        dados_faltando = [campo for campo in campos_obrigatorios if not dados.get(campo) or "NÃO ENCONTRADO" in str(dados.get(campo)).upper()]

         #Se estiver faltando qualquer dado essencial
        if dados_faltando:
            enviar_mensagem(
                numero,
                f"⚠️ Não consegui identificar as seguintes informações: {', '.join(dados_faltando)}.\n"
                "Por favor, tire uma nova foto do ticket com mais nitidez e envie novamente."
              )
            conversas[numero]["estado"] = "aguardando_imagem"
            conversas[numero].pop("dados", None)
            try:
                os.remove("ticket.jpg")
            except FileNotFoundError:
                pass
            return jsonify(status="dados incompletos, aguardando nova imagem")

        msg = (
            f"📋 Recebi os dados:\n"
            f"Cliente: SAAE\n"
            f"Ticket: {dados.get('ticket')}\n"
            f"Peso Líquido: {dados.get('peso_liquido')}\n"
            f"Origem: {destino_digitado}\n\n"
            f"Está correto?"
        )
        enviar_botoes_sim_nao(numero, msg)
        return jsonify(status="destino recebido e aguardando confirmação")

    #Bot aguardando confirmação "Sim" e "Não" dos dados extraídos
    if estado == "aguardando_confirmacao":
        if texto_recebido in ['sim', 's']:
            dados_confirmados = conversas[numero]["dados"]
        
            #Preparar dados para envio ao Sheets
            payload = {
                "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "cliente": conversas[numero].get("cliente"),
                "ticket": dados_confirmados.get("ticket"),
                "nota_fiscal": dados_confirmados.get("nota_fiscal"),
                "peso": dados_confirmados.get("peso_liquido"),
                "destino": dados_confirmados.get("destino", "N/A"),
                "telefone": numero
            }
            #Enviando "Ok" para o Motorista
            requests.post("https://bot-dcan.onrender.com/enviar_dados", json=payload)
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

    # Estado inesperado
    enviar_mensagem(numero, "⚠️ Estado desconhecido. Por favor, envie a imagem do ticket novamente.")
    conversas[numero]["estado"] = "aguardando_imagem"
    return jsonify(status="estado inesperado")

#Bloco de dados à serem enviados ao Sheets
@app.route('/enviar_dados', methods=['POST'])
def enviar_dados():
    try:
        dados = request.json  # espera receber JSON no corpo da requisição
        data = dados.get("data")
        cliente = dados.get("cliente")
        cliente = cliente.upper() if cliente else ''
        ticket = dados.get("ticket")
        nota_fiscal = dados.get("nota_fiscal")
        peso = dados.get("peso")
        destino = dados.get("destino")
        destino = destino.upper() if cliente else ''
        telefone = dados.get("telefone")

        client = conectar_google_sheets()
        planilha = client.open("tickets_dcan").worksheet("tickets_dcan")
        planilha.append_row([data or '', cliente or '', ticket or '', nota_fiscal or '', peso or '', destino or '', telefone or ''])

        return jsonify({"status": "sucesso", "msg": "Dados enviados para Google Sheets!"})
    except Exception as e:
        print(f"🚨 Erro detectado: {e}")
        return jsonify({"status": "erro", "msg": str(e)}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000, debug=True)
