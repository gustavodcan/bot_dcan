from flask import Flask, request, jsonify
import requests
from PIL import Image
import pytesseract
import re
import os
import traceback

app = Flask(__name__)
conversas = {}

pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

INSTANCE_ID = os.getenv("INSTANCE_ID")
API_TOKEN = os.getenv("API_TOKEN")
CLIENT_TOKEN = os.getenv("CLIENT_TOKEN")

clientes_validos = ["arcelormittal", "gerdau", "raízen", "mahle", "orizon", "cdr", "saae"]

# ... funções enviar_mensagem, enviar_botoes_sim_nao, enviar_lista_clientes, extrair_dados_cliente_* etc

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
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
                    # (repete para outros clientes como já estava...)
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

    except Exception as e:
        print("💥 ERRO DETECTADO NO WEBHOOK 💥")
        print(f"Tipo: {type(e).__name__}")
        print(f"Mensagem: {e}")
        traceback.print_exc()
        return jsonify(status="erro interno"), 500


@app.route('/debug', methods=['GET'])
def debug():
    return jsonify(conversas=conversas)
