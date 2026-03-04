# ===== Standard library =====
import json
import logging
import time

# ===== Third-party =====
from flask import Flask, request, jsonify

# ===== Local: mensagens =====
from mensagens import (
    enviar_mensagem,
    enviar_botoes_sim_nao,
    enviar_lista_setor,
    enviar_opcoes_operacao,
    enviar_opcoes_ticket,
    enviar_opcoes_nf,
    enviar_botao_encerrarconversa,
    enviar_botao_voltar,
    enviar_confirmacao_nf,
)

# ===== Local: manutencao =====
from manutencao.checklist import (
    tratar_estado_aguardando_km_manutencao,
    tratar_estado_aguardando_placa_manutencao,
    tratar_estado_aguardando_problema_manutencao,
)

# ===== Local: tickets =====
from operacao.foto_ticket.estados import (
    tratar_estado_aguardando_nota_manual,
    tratar_estado_aguardando_imagem,
    processar_confirmacao_final,
    iniciar_fluxo_ticket,
    tratar_estado_selecionando_viagem_ticket,
    tratar_estado_aguardando_nota_ticket,
)

# ===== Local: nota fiscal =====
from operacao.foto_nf.estados import (
    tratar_estado_confirmacao_dados_nf,
    iniciar_fluxo_nf,
    tratar_estado_selecionando_viagem_nf,
    tratar_estado_aguardando_imagem_nf,
    tratar_estado_confirmacao_dados_acrescer_nf,
    iniciar_fluxo_acrescer_nf,
    tratar_estado_selecionando_viagem_acrescer_nf,
    tratar_estado_aguardando_imagem_acrescer_nf,
    tratar_estado_aguardando_confirmacao_nf,
)

# ===== Local: setor =====
from operacao.falar_programador.contato import (
    tratar_descricao_setor,
    encaminhar_para_setor,
)

#Timeout global de inatividade
TIMEOUT_SECONDS = 60 * 10

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# silencia debug verborrágico de rede (Supabase/httpx/httpcore/h2)
for noisy in ("httpcore", "httpx", "h2", "hpack"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

app = Flask(__name__)
conversas = {}

#Identifica o tipo de mensagem recebida
@app.route('/webhook', methods=['POST']) 
def webhook(): 
    global conversas
    data = request.json
    #logger.debug("🛰️ Webhook recebido:")
    #logger.debug(data)

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

    #Checagem de inatividade
    agora = time.time()
    registro = conversas.get(numero)

    if registro:
        expira_em = registro.get("expira_em", 0)
        if expira_em and expira_em < agora:
            # Expirou: avisa e encerra
            enviar_mensagem(
                numero,
                "⚠️ *Inatividade detectada.* Encerrando a conversa.\n"
                "Para continuar, envie uma nova mensagem para iniciar novamente. ✅"
            )
            conversas.pop(numero, None)
            return jsonify(status="reiniciado por inatividade")

    #Se não expirou e já existe conversa, renova o prazo a cada mensagem recebida
    if registro and registro.get("estado"):
        conversas[numero]["expira_em"] = agora + TIMEOUT_SECONDS

    #Se o bot não esta aguardando nada:
    if not estado:
        enviar_lista_setor(numero, "👋 Olá! Sou o Deco, bot de atendimento da DCAN Transportes.\n\n Como posso te ajudar?")
        conversas[numero] = {"estado": "aguardando_confirmacao_setor", "expira_em": time.time() + TIMEOUT_SECONDS}
        return jsonify(status="aguardando confirmação do setor")

    #Define DEF seguinte baseado no setor recebido pelo usuário
    if estado == "aguardando_confirmacao_setor":
        if texto_recebido in ["comercial", "faturamento", "financeiro", "recursos humanos", "compras"]:
            conversas[numero] = {
                "estado": f"aguardando_descricao_{texto_recebido}",
                "setor": texto_recebido,
                "expira_em": time.time() + TIMEOUT_SECONDS
            }
            enviar_mensagem(numero, f"✏️ Por favor, descreva brevemente o motivo do seu contato com o setor {texto_recebido.title()}.")
        elif texto_recebido == "operacao":
            conversas[numero] = {"estado": "aguardando_opcao_operacao", "expira_em": time.time() + TIMEOUT_SECONDS}
            enviar_opcoes_operacao(numero)
        elif texto_recebido == "manutencao":
            enviar_botao_voltar(numero, "🛠️ Vamos abrir uma manutenção.\nQual o KM do veículo?")
            conversas[numero]["estado"] = "aguardando_km_manutencao"
        else:
            enviar_lista_setor(numero, "❌ Opção inválida. Por favor, escolha uma opção da lista.")
        return jsonify(status="resposta motorista")

    #Define DEF seguinte com base na seleção do usuário no setor "Operação"
    if estado == "aguardando_opcao_operacao":
        if texto_recebido in ['foto_ticket']:
            conversas[numero] = {"estado": "aguardando_opcao_ticket", "expira_em": time.time() + TIMEOUT_SECONDS}
            resultado = enviar_opcoes_ticket(numero)
            return jsonify(resultado)
        elif texto_recebido in ['foto_nf']:
            conversas[numero] = {"estado": "aguardando_opcao_nf", "expira_em": time.time() + TIMEOUT_SECONDS}
            resultado = enviar_opcoes_nf(numero)
            return jsonify(resultado)
        elif texto_recebido in ['falar_programador']:
            enviar_mensagem(numero, "🔧 Entrar em contato com o programador ainda está em desenvolvimento. Em breve estará disponível!")
            conversas[numero]["estado"] = "finalizado"
            conversas.pop(numero, None)
            return jsonify(status="resposta motorista")
        else:
            enviar_mensagem(numero, "❌ Opção inválida. Por favor, escolha uma opção válida acima.")
            conversas[numero]["estado"] = "aguardando_opcao_operacao"
            return {"status": "aguardando_opcao_operacao"}

    #Define DEF seguinte com base na seleção do usuário no setor "Operação"
    if estado == "aguardando_opcao_ticket":
        if texto_recebido in ['eu_mesmo']:
            resultado = iniciar_fluxo_ticket(numero, conversas)
            return jsonify(resultado)
        elif texto_recebido in ['voltar']:
            enviar_lista_setor(numero, "👋 Olá! Sou o Deco, bot de atendimento da DCAN Transportes.\n\n Como posso te ajudar?")
            conversas[numero] = {"estado": "aguardando_confirmacao_setor", "expira_em": time.time() + TIMEOUT_SECONDS}
            return jsonify(status="aguardando confirmação do setor")
        elif texto_recebido in ['outro_motorista']:
            conversas[numero]["estado"] = "aguardando_nota_ticket"
            enviar_mensagem(numero, "🧾 Por favor, envie o número da nota fiscal localizada no ticket.\n(Ex: *7878*).")
            return {"status": "solicitando nota ticket"}
        else:
            enviar_mensagem(numero, "❌ Opção inválida. Por favor, escolha uma opção válida acima.")
            conversas[numero]["estado"] = "aguardando_opcao_ticket"
            return {"status": "aguardando_opcao_ticket"}

    #Define DEF seguinte com base na seleção do usuário no setor "Operação"
    if estado == "aguardando_opcao_nf":
        if texto_recebido in ['enviar_nf']:
            resultado = iniciar_fluxo_nf(numero, conversas)
            return jsonify(resultado)
        elif texto_recebido in ['voltar']:
            enviar_lista_setor(numero, "👋 Olá! Sou o Deco, bot de atendimento da DCAN Transportes.\n\n Como posso te ajudar?")
            conversas[numero] = {"estado": "aguardando_confirmacao_setor", "expira_em": time.time() + TIMEOUT_SECONDS}
            return jsonify(status="aguardando confirmação do setor")
        elif texto_recebido in ['adicionar_nf']:
            resultado = enviar_confirmacao_nf(numero)
            conversas[numero]["estado"] = "aguardando_confirmacao_nf"
            return jsonify(resultado)
        else:
            enviar_mensagem(numero, "❌ Opção inválida. Por favor, escolha uma opção válida acima.")
            conversas[numero]["estado"] = "aguardando_opcao_ticket"
            return {"status": "aguardando_opcao_ticket"}

    #Manda para o DEF "Aguardando Confirmação NF" 
    if estado == "aguardando_confirmacao_nf":
        resultado = tratar_estado_aguardando_confirmacao_nf(numero, texto_recebido, conversas)
        return jsonify(resultado)
    
    #Manda para o DEF "Selecionando Viagem_NF" após seleção da viagem
    if estado == "selecionando_viagem_nf":
        numero_viagem = data.get("listResponseMessage", {}).get("selectedRowId", "")
        logger.debug(f"[DEBUG] selectedRowId recebido: {data.get('listResponseMessage', {}).get('selectedRowId')}")
        resultado = tratar_estado_selecionando_viagem_nf(numero, numero_viagem, conversas, texto_recebido)
        return jsonify(resultado)

    if estado == "selecionando_viagem_acrescer_nf":
        numero_viagem = data.get("listResponseMessage", {}).get("selectedRowId", "")
        logger.debug(f"[DEBUG] selectedRowId recebido: {data.get('listResponseMessage', {}).get('selectedRowId')}")
        resultado = tratar_estado_selecionando_viagem_acrescer_nf(numero, numero_viagem, conversas, texto_recebido)
        return jsonify(resultado)

    #Encaminha mensagem de assunto do usuário para o setor resposável
    if estado.startswith("aguardando_descricao_"):
        tratar_descricao_setor(numero, mensagem_original.strip(), conversas)
        return jsonify(status="descricao encaminhada")
        # OBS: o retorno acima evita usar uma variável 'resultado' não definida.

    #Manda para o DEF "Aguardando KM Manutencao" após seleção do checklist
    if estado == "aguardando_km_manutencao":
        resultado = tratar_estado_aguardando_km_manutencao(numero, texto_recebido, conversas)
        return jsonify(resultado)

    #Manda para o DEF "Aguardando Placa Manutencao" após seleção do checklist
    if estado == "aguardando_placa_manutencao":
        resultado = tratar_estado_aguardando_placa_manutencao(numero, texto_recebido, conversas)
        return jsonify(resultado)

    #Manda para o DEF "Aguardando Placa Manutencao" após seleção do checklist
    if estado == "aguardando_problema_manutencao":
        resultado = tratar_estado_aguardando_problema_manutencao(numero, texto_recebido, conversas)
        return jsonify(resultado)

    #Manda para o DEF "Aguardando Imagem Ticket" após envio da foto
    if estado == "aguardando_imagem":
        resultado = tratar_estado_aguardando_imagem(numero, data, conversas, texto_recebido)
        return jsonify(resultado)

    #Manda para o DEF "Aguardando Imagem NF" após envio da foto
    if estado == "aguardando_imagem_nf":
        resultado = tratar_estado_aguardando_imagem_nf(numero, data, conversas, texto_recebido)
        return jsonify(resultado)

    #Manda para o DEF "Aguardando Imagem NF" após envio da foto
    if estado == "aguardando_imagem_acrescer_nf":
        resultado = tratar_estado_aguardando_imagem_acrescer_nf(numero, data, conversas, texto_recebido)
        return jsonify(resultado)

    #Manda para o DEF "Confirmação Dados NF" após envio de "Sim" ou "Não"
    if estado == "aguardando_confirmacao_dados_nf":
        resultado = tratar_estado_confirmacao_dados_nf(numero, texto_recebido, conversas)
        return jsonify(resultado)

    #Manda para o DEF "Confirmação Dados NF" após envio de "Sim" ou "Não"
    if estado == "aguardando_confirmacao_dados_acrescer_nf":
        resultado = tratar_estado_confirmacao_dados_acrescer_nf(numero, texto_recebido, conversas)
        return jsonify(resultado)

    #Manda para o DEF "Aguardando NF Manual" após envio do número da nota fiscal
    if estado == "aguardando_nota_manual":
        resultado = tratar_estado_aguardando_nota_manual(numero, texto_recebido, conversas)
        return jsonify(resultado)

    #Manda para o DEF "Aguardando NF Ticket" após envio do número da nota fiscal localizada no ticket
    if estado == "aguardando_nota_ticket":
        resultado = tratar_estado_aguardando_nota_ticket(numero, texto_recebido, conversas)
        return jsonify(resultado)

    #Manda para o DEF "Selecionando Viagem_Ticket" após seleção da viagem
    if estado == "selecionando_viagem_ticket":
        resultado = tratar_estado_selecionando_viagem_ticket(numero, mensagem_original, conversas, texto_recebido)
        return jsonify(resultado)

   #Manda para o DEF "Aguardando Destino SAAE" após detecção do OCR 
    if estado == "aguardando_destino_saae":
        from operacao.foto_ticket.saae import tratar_estado_aguardando_destino_saae
        resultado = tratar_estado_aguardando_destino_saae(numero, texto_recebido, conversas)
        return jsonify(resultado)

    #Manda para o DEF "Aguardando Confirmação" após envio de "Sim" ou "Não"
    if estado == "aguardando_confirmacao":
        resultado = processar_confirmacao_final(numero, texto_recebido, conversas)
        return jsonify(resultado)

    def receber_xml_a3soft(chave_acesso: str) -> dict:
        """Faz login e chama o endpoint /ReceberXML do A3Soft"""
        from integracoes.a3soft.client import login_obter_token
        auth = login_obter_token()
        if not auth.get("ok"):
            return {"ok": False, "error": f"falha_login: {auth.get('error')}"}

        token = auth["token"]
        from integracoes.a3soft.client import receber_xml
        res = receber_xml(token=token, chave_acesso=chave_acesso)
        return res

    return jsonify({"status": "sem estado válido"})

#POST para recebimento de dados da viagem (A3)
@app.route("/notificar_viagem", methods=["POST"])
def notificar_viagem():
    # 1. Autenticação
    from config import DCAN_TOKEN_KEY
    
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer ") or auth_header.split(" ")[1] != DCAN_TOKEN_KEY:
        return jsonify({"status": "erro", "mensagem": "Não autorizado."}), 403

    try:
        # 2. Captura dados enviados pelo A3
        data = request.get_json(force=True)
        telefone_motorista = data.get("telefone_motorista")
        data_coleta = data.get("data_coleta")
        nome_motorista = data.get("nome_motorista")
        numero_viagem = data.get("numero_viagem")
        rota = data.get("rota")
        placa = data.get("placa")
        remetente = data.get("remetente")
        destinatario = data.get("destinatario")
#        emite_nf = data.get("emite_nf")

        # Validação rápida
        if not (telefone_motorista and numero_viagem and rota and placa):
            return jsonify({"status": "erro", "mensagem": "Campos obrigatórios ausentes."}), 400

        from integracoes.supabase_db import salvar_viagem

        try:
            salvar_viagem({
                "numero_viagem": numero_viagem,
                "data": data_coleta,
                "placa": placa,
                "telefone_motorista": telefone_motorista,
                "motorista": nome_motorista,
                "rota": rota,
                "remetente": remetente,
                "destinatario": destinatario,
#                "emite_nf": emite_nf,
            })
            logger.info(f"[A3] Viagem {numero_viagem} gravada no Supabase.")
        except Exception:
            logger.error("[A3] Falha ao gravar viagem no Supabase", exc_info=True)
            return jsonify({"status": "Viagem já lançada no sistema"}), 500

        from datetime import datetime
        
        # 3. Monta mensagem pro motorista
        mensagem = (
            f"👋 Olá {nome_motorista}!\n\n"
            f"Você será responsável pela viagem *{numero_viagem}*. Na data {datetime.strptime(data_coleta, '%Y-%m-%d').strftime('%d/%m/%Y')}.\n"
            f"🛣️ Rota: {rota}\n"
            f"🚛 Placa: {placa}\n"
            f"🏭 Remetente: {remetente}\n"
            f"🏭 Destinatário: {destinatario}\n\n"
            "O envio das informações: Nota Fiscal e Ticket estão sob sua responsabilidade! Bom trabalho! ✅"
        )

        # 4. Dispara via WhatsApp
        enviar_mensagem(telefone_motorista, mensagem)
        logger.info(f"[ERP] Viagem {numero_viagem} enviada ao motorista {telefone_motorista}")

        # 5. Retorno OK pro A3
        return jsonify({"status": "ok", "mensagem": "Viagem enviada ao motorista."}), 200

    except Exception as e:
        logger.error("[ERP] Falha ao processar notificação de viagem", exc_info=True)
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
