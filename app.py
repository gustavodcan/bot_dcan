#Importação de Bibliotecas
from flask import Flask, request, jsonify
import requests, re, os, json, gspread, base64
from PIL import Image, ImageEnhance, ImageFilter
from google.oauth2 import service_account
from google.cloud import vision
from google.oauth2.service_account import Credentials
from datetime import datetime
from azure.storage.fileshare import ShareFileClient
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

app = Flask(__name__)
conversas = {}

from mensagens import (enviar_mensagem, enviar_botoes_sim_nao, enviar_lista_setor, enviar_opcoes_operacao)
from config import (AZURE_FILE_ACCOUNT_NAME, AZURE_FILE_ACCOUNT_KEY, AZURE_FILE_SHARE_NAME, CERTIFICADO_BASE64, CERTIFICADO_SENHA, INFOSIMPLES_TOKEN, CHAVE_AES, GOOGLE_SHEETS_PATH, GOOGLE_CREDS_PATH, GOOGLE_CREDS_JSON, INSTANCE_ID, API_TOKEN, CLIENT_TOKEN)
from integracoes.google_vision import (ler_texto_google_ocr, preprocessar_imagem)
from integracoes.azure import salvar_imagem_azure
from integracoes.infosimples import consultar_nfe_completa
from operacao.foto_ticket.saae import extrair_dados_cliente_saae
from operacao.foto_ticket.orizon import extrair_dados_cliente_orizon
from operacao.foto_ticket.estados import tratar_estado_aguardando_imagem
from operacao.foto_ticket.estados import tratar_estado_aguardando_confirmacao
from operacao.foto_ticket.estados import tratar_estado_aguardando_nota_manual
from operacao.foto_ticket.saae import tratar_estado_aguardando_destino_saae
from operacao.foto_nf.estados import tratar_estado_aguardando_imagem_nf


# Processamento final após confirmação
def processar_confirmacao_final(numero):
    dados = conversas[numero]["dados"]

    payload = {
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cliente": conversas[numero].get("cliente", "").upper(),
        "ticket": dados.get("ticket"),
        "nota_fiscal": dados.get("nota_fiscal"),
        "peso": dados.get("peso_liquido"),
        "destino": dados.get("destino", "N/A"),
        "telefone": numero
    }

    # Envia os dados para a rota existente /enviar_dados
    try:
        requests.post("http://localhost:10000/enviar_dados", json=payload)
    except Exception as e:
        print(f"Erro ao enviar dados para /enviar_dados: {e}")

    nome_imagem = f"{payload['cliente']}/{payload['cliente']}_{payload['nota_fiscal']}.jpg"
    salvar_imagem_azure("ticket.jpg", nome_imagem)

    try:
        os.remove("ticket.jpg")
    except FileNotFoundError:
        pass

    enviar_mensagem(numero, "✅ Dados confirmados, Salvando as informações! Obrigado!")
    conversas.pop(numero)

def extrair_chave_confirmar(numero):
    texto = conversas[numero].get("ocr_texto", "")
    chave = extrair_chave_acesso(texto)

    if chave:
        conversas[numero]["chave_detectada"] = chave
        conversas[numero]["estado"] = "aguardando_confirmacao_chave"
        mensagem = (
            f"🔎 Encontrei a seguinte *chave de acesso* na nota:\n\n"
            f"{chave}\n\n"
            f"✅ Por favor, *confirme se está correta* antes de continuar."
        )
        enviar_botoes_sim_nao(numero, mensagem)
    else:
        enviar_mensagem(numero, "❌ Não consegui identificar a chave de acesso na nota. Por favor, envie novamente.")
        conversas[numero]["estado"] = "aguardando_imagem_nf"

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

# Redireciona mensagem digitada para número do setor
def encaminhar_para_setor(numero_usuario, setor, mensagem):
    mapa_setores = {
        "comercial": "5515997008800",
        "faturamento": "5515997008800",
        "financeiro": "5515997008800",
        "recursos humanos": "5515997008800"
    }
    numero_destino = mapa_setores.get(setor)
    if not numero_destino:
        print(f"Setor '{setor}' não encontrado.")
        return

    texto = f"📥 Atendimento automático\nPor favor, não responda.\n\n O telefone: {numero_usuario} solicitou contato do setor {setor.title()} através da seguinte mensagem:\n\n{mensagem}"

    url = f"https://api.z-api.io/instances/{os.getenv('INSTANCE_ID')}/token/{os.getenv('API_TOKEN')}/send-text"
    payload = {
        "phone": numero_destino,
        "message": texto
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": os.getenv("CLIENT_TOKEN")
    }
    res = requests.post(url, json=payload, headers=headers)
    print(f"[📨 Encaminhado para {setor}] Status {res.status_code}: {res.text}")

# Trata descrições fornecidas para setores não-operacionais
def tratar_descricao_setor(numero, mensagem_original):
    setor = conversas[numero].get("setor")
    if setor:
        encaminhar_para_setor(numero_usuario=numero, setor=setor, mensagem=mensagem_original)
        enviar_mensagem(numero, f"📨 Sua mensagem foi encaminhada ao setor {setor.title()}. Em breve alguém entrará em contato.")
        conversas[numero]["estado"] = "finalizado"
        conversas.pop(numero, None)
    else:
        enviar_lista_setor(numero, "⚠️ Setor não identificado. Vamos começar novamente.")
        conversas[numero] = {"estado": "aguardando_setor"}

#Identifica o tipo de mensagem recebida
@app.route('/webhook', methods=['POST'])
def webhook():
    global conversas
    data = request.json
    print("🛰️ Webhook recebido:")
    print(data)

    tipo = data.get("type")
    numero = data.get("phone") or data.get("from")

    mensagem_original = (
        data.get("buttonsResponseMessage", {}).get("buttonId") or
        data.get("listResponseMessage", {}).get("selectedRowId") or
        data.get("text", {}).get("message", "")
    )

    texto_recebido = mensagem_original.strip().lower()

    estado = conversas.get(numero, {}).get("estado")

    if tipo != "ReceivedCallback":
        return jsonify(status="ignorado")
        
    #Se o bot não esta aguardando nada:
    if not estado:
        enviar_lista_setor(numero, "👋 Olá! Sou o bot de atendimento da DCAN Transportes.\n\n Como posso te ajudar?")
        conversas[numero] = {"estado": "aguardando_confirmacao_setor"}
        return jsonify(status="aguardando confirmação do setor")

    if estado == "aguardando_confirmacao_setor":
        if texto_recebido in ["comercial", "faturamento", "financeiro", "recursos humanos"]:
            conversas[numero] = {"estado": f"aguardando_descricao_{texto_recebido}", "setor": texto_recebido}
            enviar_mensagem(numero, f"✏️ Por favor, descreva brevemente o motivo do seu contato com o setor {texto_recebido.title()}.")
        elif texto_recebido == "operacao":
            conversas[numero] = {"estado": "aguardando_opcao_operacao"}
            enviar_opcoes_operacao(numero)
        else:
            enviar_lista_setor(numero, "❌ Opção inválida. Por favor, escolha uma opção da lista.")
        return jsonify(status="resposta motorista")

    #Se o bot esta aguardando "sim" ou "não" do motorista:
    if estado == "aguardando_opcao_operacao":
        if texto_recebido in ['foto_ticket']:
            enviar_mensagem(numero, "✅ Perfeito! Por favor, envie a foto do ticket.")
            conversas[numero]["estado"] = "aguardando_imagem"
        elif texto_recebido in ['foto_nf']:
            enviar_mensagem(numero, "📸 Por favor, envie a *foto da nota fiscal* agora.")
            conversas[numero]["estado"] = "aguardando_imagem_nf"
        else:
            enviar_mensagem(numero, "🔧 Entrrar em contato com o programador ainda está em desenvolvimento. Em breve estará disponível!")
            conversas[numero]["estado"] = "finalizado"
            conversas.pop(numero, None)
        return jsonify(status="resposta motorista")

    if estado.startswith("aguardando_descricao_"):
        tratar_descricao_setor(numero,  mensagem_original.strip())

    #Confirmando chave
    if estado == "aguardando_confirmacao_chave":
        if texto_recebido in ['sim', 's']:
            chave = conversas[numero]["chave_detectada"]
            enviar_mensagem(numero, "✅ Obrigado! A chave foi confirmada. Consultando a nota...")

            try:
                resultado = consultar_nfe_completa(chave)
                if not resultado:
                    raise ValueError("Resposta vazia da consulta.")

                if resultado.get("code") == 500 and "Erro interno" in resultado.get("code_message", ""):
                    enviar_mensagem(numero, "⚠️ *Erro interno na integração com InfoSimples.*\nFavor contatar o suporte.")
                    conversas[numero]["estado"] = "finalizado"

                elif resultado.get("code") == 200:
                    dados_raw = resultado.get("data", {})
                    if isinstance(dados_raw, list):
                        dados = dados_raw[0] if dados_raw else {}
                    elif isinstance(dados_raw, dict):
                        dados = dados_raw
                    else:
                        dados = {}

                    emitente = dados.get("emitente", {})
                    emitente_nome = emitente.get("nome") or emitente.get("nome_fantasia") or "Não informado"
                    emitente_cnpj = emitente.get("cnpj") or "Não informado"
                    
                    nfe = dados.get("nfe", {})
                    nfe_numero = nfe.get("numero") or "Não informado"
                    nfe_emissao_raw = nfe.get("data_emissao") or ""

                    try:
                        dt = datetime.strptime(nfe_emissao_raw[:19], "%d/%m/%Y %H:%M:%S")
                        nfe_emissao = dt.strftime("%d/%m/%Y")
                    except Exception:
                        nfe_emissao = "Não informado"
                
                    destinatario = dados.get("destinatario", {})
                    destinatario_nome = destinatario.get("nome") or destinatario.get("nome_fantasia") or "Não informado"
                    destinatario_cnpj = destinatario.get("cnpj") or "Não informado"
                    
                    transporte = dados.get("transporte", {})
                    transporte_modalidade = transporte.get("modalidade_frete") or "Não informado"
                    modalidade_numeros = ''.join(re.findall(r'\d+', transporte_modalidade))

                    volumes = transporte.get("volumes", [])
                    primeiro_volume = volumes[0] if isinstance(volumes, list) and volumes else {}
                    peso_bruto = primeiro_volume.get("peso_bruto") or "Não informado"

                    resposta = (
                        f"✅ *Nota consultada com sucesso!*\n\n"
                        f"*Emitente:* {emitente_nome}\n"
                        f"*Emitente CNPJ:* {emitente_cnpj}\n"
                        f"*Destinatário:* {destinatario_nome}\n"
                        f"*Destinatário CNPJ:* {destinatario_cnpj}\n"
                        f"*Número:* {nfe_numero}\n"
                        f"*Emissão:* {nfe_emissao}\n"
                        f"*Modalidade:* {modalidade_numeros}\n"
                        f"*Peso Bruto:* {peso_bruto}\n" 
                    )
                    enviar_mensagem(numero, resposta)
                    conversas[numero]["estado"] = "finalizado"

                else:
                    resposta = (
                        f"❌ *Erro ao consultar a nota.*\n"
                        f"🔧 Motivo: {resultado.get('code_message') or 'Erro desconhecido.'}\n"
                    )
                    if resultado.get("errors"):
                        resposta += "\nDetalhes:\n" + "\n".join(f"- {e}" for e in resultado["errors"])
                    enviar_mensagem(numero, resposta)
                    conversas[numero]["estado"] = "finalizado"

            except Exception as e:
                enviar_mensagem(numero, f"❌ Erro inesperado ao processar a nota:\n{str(e)}")
                conversas[numero]["estado"] = "finalizado"

            finally:
                conversas[numero].pop("chave_detectada", None)
                conversas.pop(numero, None)

            return jsonify(status="finalizado")

    if estado == "aguardando_imagem":
        resultado = tratar_estado_aguardando_imagem(numero, data, conversas)
        return jsonify(resultado)

    if estado == "aguardando_imagem_nf":
        resultado = tratar_estado_aguardando_imagem_nf(numero, data, conversas)
        return jsonify(resultado)
            
    if estado == "aguardando_nota_manual":
        resultado = tratar_estado_aguardando_nota_manual(numero, texto_recebido, conversas)
        return jsonify(resultado)

    if estado == "aguardando_destino_saae":
        resultado = tratar_estado_aguardando_destino_saae(numero, texto_recebido, conversas)
        return jsonify(resultado)

    if estado == "aguardando_confirmacao":
        resultado = tratar_estado_aguardando_confirmacao(numero, texto_recebido, conversas)
        return jsonify(resultado)
        
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

        from integracoes.google_sheets import conectar_google_sheets
        client = conectar_google_sheets()
        planilha = client.open("tickets_dcan").worksheet("tickets_dcan")
        planilha.append_row([data or '', cliente or '', ticket or '', nota_fiscal or '', peso or '', destino or '', telefone or ''])

        return jsonify({"status": "sucesso", "msg": "Dados enviados para Google Sheets!"})
    except Exception as e:
        print(f"🚨 Erro detectado: {e}")
        return jsonify({"status": "erro", "msg": str(e)}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000, debug=True)
