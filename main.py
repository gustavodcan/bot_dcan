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
from operacao.foto_ticket.orizon import extrair_dados_cliente_orizon
from integracoes.google_vision import (ler_texto_google_ocr, preprocessar_imagem)
from operacao.falar_programador.contato import encaminhar_para_setor, tratar_descricao_setor
from operacao.foto_ticket.saae import tratar_estado_aguardando_destino_saae, extrair_dados_cliente_saae
from mensagens import (enviar_mensagem, enviar_botoes_sim_nao, enviar_lista_setor, enviar_opcoes_operacao)
from operacao.foto_nf.estados import tratar_estado_aguardando_confirmacao_chave, tratar_estado_aguardando_imagem_nf
from operacao.foto_ticket.estados import tratar_estado_aguardando_confirmacao, tratar_estado_aguardando_nota_manual, tratar_estado_aguardando_imagem, processar_confirmacao_final
from config import (AZURE_FILE_ACCOUNT_NAME, AZURE_FILE_ACCOUNT_KEY, AZURE_FILE_SHARE_NAME, CERTIFICADO_BASE64, CERTIFICADO_SENHA, INFOSIMPLES_TOKEN, CHAVE_AES, GOOGLE_SHEETS_PATH, GOOGLE_CREDS_PATH, GOOGLE_CREDS_JSON, INSTANCE_ID, API_TOKEN, CLIENT_TOKEN)

import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)

app = Flask(__name__)
conversas = {}

#Identifica o tipo de mensagem recebida
@app.route('/webhook', methods=['POST'])
def webhook():
    global conversas
    data = request.json
    logger.debug("🛰️ Webhook recebido:")
    logger.debug(data)

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
            enviar_mensagem(numero, "🔧 Entrar em contato com o programador ainda está em desenvolvimento. Em breve estará disponível!")
            conversas[numero]["estado"] = "finalizado"
            conversas.pop(numero, None)
        return jsonify(status="resposta motorista")

    if estado.startswith("aguardando_descricao_"):
        tratar_descricao_setor(numero, mensagem_original.strip(), conversas)

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
        logger.debug(f"🚨 Erro detectado: {e}")
        return jsonify({"status": "erro", "msg": str(e)}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000, debug=True)
