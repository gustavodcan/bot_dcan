#Importação de Bibliotecas
from datetime import datetime
from Crypto.Cipher import AES
from google.cloud import vision
from Crypto.Util.Padding import pad
from google.oauth2 import service_account
from flask import Flask, request, jsonify
import requests, re, os, json, gspread, base64
from PIL import Image, ImageEnhance, ImageFilter
from azure.storage.fileshare import ShareFileClient
from google.oauth2.service_account import Credentials
#Importação de de Defs e Estados
from integracoes.azure import salvar_imagem_azure
from integracoes.infosimples import consultar_nfe_completa
from operacao.foto_ticket.defs import extrair_dados_da_imagem
from operacao.foto_ticket.saae import extrair_dados_cliente_saae
from operacao.foto_ticket.orizon import extrair_dados_cliente_orizon
from operacao.foto_nf.estados import tratar_estado_aguardando_imagem_nf
from operacao.foto_ticket.estados import tratar_estado_aguardando_imagem
from operacao.foto_ticket.saae import tratar_estado_aguardando_destino_saae
from operacao.foto_ticket.estados import tratar_estado_aguardando_confirmacao
from operacao.foto_ticket.estados import tratar_estado_aguardando_nota_manual
from operacao.foto_nf.estados import tratar_estado_aguardando_confirmacao_chave
from integracoes.google_vision import (ler_texto_google_ocr, preprocessar_imagem)
from mensagens import (enviar_mensagem, enviar_botoes_sim_nao, enviar_lista_setor, enviar_opcoes_operacao)
from config import (AZURE_FILE_ACCOUNT_NAME, AZURE_FILE_ACCOUNT_KEY, AZURE_FILE_SHARE_NAME, CERTIFICADO_BASE64, CERTIFICADO_SENHA, INFOSIMPLES_TOKEN, CHAVE_AES, GOOGLE_SHEETS_PATH, GOOGLE_CREDS_PATH, GOOGLE_CREDS_JSON, INSTANCE_ID, API_TOKEN, CLIENT_TOKEN)

app = Flask(__name__)
conversas = {}

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

    if estado == "aguardando_confirmacao_chave":
        resultado = tratar_estado_aguardando_confirmacao_chave(numero, texto_recebido, conversas)
        return jsonify(resultado)
        
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
