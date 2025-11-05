import logging, os, requests
from mensagens import enviar_mensagem
from config import mapa_setores, ZAPI_INSTANCE_ID, ZAPI_API_TOKEN, ZAPI_CLIENT_TOKEN

logger = logging.getLogger(__name__)

# Redireciona mensagem digitada para número do setor
def encaminhar_para_setor(numero_usuario, setor, mensagem):
    numero_destino = mapa_setores.get(setor)

    if not numero_destino:
        logger.debug(f"Setor '{setor}' não encontrado.")
        return

    texto = f"📥 Atendimento automático\nPor favor, não responda.\n\n O telefone: {numero_usuario} solicitou contato do setor {setor.title()} através da seguinte mensagem:\n\n{mensagem}"

    url = f"https://api.z-api.io/instances/{os.getenv('ZAPI_INSTANCE_ID')}/token/{os.getenv('ZAPI_API_TOKEN')}/send-text"
    payload = {
        "phone": numero_destino,
        "message": texto
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": os.getenv("CLIENT_TOKEN")
    }
    res = requests.post(url, json=payload, headers=headers)
    logger.debug(f"[📨 Encaminhado para {setor}] Status {res.status_code}: {res.text}")

# Trata descrições fornecidas para setores não-operacionais
def tratar_descricao_setor(numero, mensagem_original, conversas):
    setor = conversas[numero].get("setor")
    if setor:
        encaminhar_para_setor(numero_usuario=numero, setor=setor, mensagem=mensagem_original)
        enviar_mensagem(numero, f"📨 Sua mensagem foi encaminhada ao setor {setor.title()}. Em breve alguém entrará em contato.")
        conversas[numero]["estado"] = "finalizado"
        conversas.pop(numero, None)
        return {"status": f"mensagem encaminhada para {setor}"}
    else:
        enviar_lista_setor(numero, "⚠️ Setor não identificado. Vamos começar novamente.")
        conversas[numero] = {"estado": "aguardando_setor"}
        return {"status": "setor nao identificado, aguardando setor"}
