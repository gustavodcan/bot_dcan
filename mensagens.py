import os, requests, logging
from config import ZAPI_INSTANCE_ID, ZAPI_API_TOKEN, ZAPI_CLIENT_TOKEN

logger = logging.getLogger(__name__)

#Cria lista(options) de viagens e envia para o motorista
def enviar_lista_viagens(numero, viagens, mensagem):
    if not ZAPI_INSTANCE_ID or not ZAPI_API_TOKEN or not ZAPI_CLIENT_TOKEN:
        logger.error("[Z-API] Variáveis de ambiente faltando: ZAPI_INSTANCE_ID/ZAPI_API_TOKEN/ZAPI_CLIENT_TOKEN.")
        return False

    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_API_TOKEN}/send-option-list"

    options = [{
        "rowId": str(v["numero_viagem"]), 
        "title": str(v["numero_viagem"]),
        "description": f"{v['data']} - NF{v['nota_fiscal']} - {v['rota']} - {v['placa']} - {v['remetente']}"
    } for v in viagens]

    lista_title = f"Suas coletas ativas:"

    payload = {
        "phone": numero,
        "message": mensagem or "Escolha a coleta (viagem):",
        "optionList": {
            "title": lista_title,
            "buttonLabel": "Selecionar",
            "options": options
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Client-Token": ZAPI_CLIENT_TOKEN
    }

    logger.debug(f"[DEBUG] Lista enviada para {numero}: {options}")

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=15)
        logger.debug(f"[🟪 Lista de viagens enviada para: {numero}] Status {res.status_code}: {res.text}")
        if res.status_code != 200:
            logger.error("[Z-API] Falha ao enviar lista: %s", res.text)
            return False
        return True
    except Exception:
        logger.error("[Z-API] Erro ao enviar lista interativa", exc_info=True)
        return False

#Envia mensagem simples baseada no "texto"
def enviar_mensagem(numero, texto):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_API_TOKEN}/send-text"
    payload = {"phone": numero, "message": texto}
    headers = {
        "Content-Type": "application/json",
        "Client-Token": ZAPI_CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    logger.debug(f"[🟢 Texto simples enviado para: {numero}] Status {res.status_code}: {res.text}")

#Envia botões de Sim ou Não
def enviar_botoes_sim_nao(numero, mensagem):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_API_TOKEN}/send-button-list"
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
        "Client-Token": ZAPI_CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    logger.debug(f"[🟦 Botões de Sim ou Não enviados para: {numero}] Status {res.status_code}: {res.text}")

#Envia botão para encerrar conversa
def enviar_botao_encerrarconversa(numero, mensagem):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_API_TOKEN}/send-button-list"
    payload = {
        "phone": numero,
        "message": mensagem,
        "buttonList": {
            "buttons": [
                {"id": "encerrar_conversa", "label": "Cancelar conversa."},
            ]
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": ZAPI_CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    logger.debug(f"[🟦 Botão de Encerrar Conversa enviado para: {numero}] Status {res.status_code}: {res.text}")

#Envia botão de voltar
def enviar_botao_voltar(numero, mensagem):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_API_TOKEN}/send-button-list"
    payload = {
        "phone": numero,
        "message": mensagem,
        "buttonList": {
            "buttons": [
                {"id": "voltar", "label": "Voltar ↩️."},
            ]
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": ZAPI_CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    logger.debug(f"[🟦 Botão de Voltar enviado para: {numero}] Status {res.status_code}: {res.text}")

#Cria(manualmente) lista de setores e envia para o motorista
def enviar_lista_setor(numero, mensagem):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_API_TOKEN}/send-option-list"
    payload = {
        "phone": numero,
        "message": mensagem,
        "optionList": {
            "title": "Setores DCAN",
            "buttonLabel": "Escolha o setor",
            "options": [
                {"id": "comercial", "description": "(Cotações, Novos serviços e Parcerias)", "title": "Comercial"},
                {"id": "faturamento", "description": "(Contratos, Conhecimentos e Comprovantes)", "title": "Faturamento"},
                {"id": "compras", "description": "(Parcerias de Compras, Equipamentos, Insumos e etc)", "title": "Compras"},
                {"id": "financeiro",  "description": "(Pagamentos, Descontos e Dúvidas)", "title": "Financeiro"},
                {"id": "recursos humanos", "description": "(Vagas, Documentação e Benefícios)", "title": "Recursos Humanos"},
                {"id": "operacao", "description": "(Coletas, Entregas e Tickets)", "title": "Operação"},
                {"id": "manutencao", "description": "(Checklist Manutenção)", "title": "Manutenção"},
            ]
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": ZAPI_CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    logger.debug(f"[🟪 Lista de setor enviado para: {numero}] Status {res.status_code}: {res.text}")

#Cria botões(manualmente) da operação e envia para motorista
def enviar_opcoes_operacao(numero):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_API_TOKEN}/send-button-list"
    payload = {
        "phone": numero,
        "message": "Você está falando com o setor de Operações. O que deseja fazer?",
        "buttonList": {
            "buttons": [
                {"id": "falar_programador", "label": "Falar com programador"},
                {"id": "foto_nf", "label": "Enviar foto NF"},
                {"id": "foto_ticket", "label": "Enviar foto ticket"}
            ]
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": ZAPI_CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    logger.debug(f"[🟦 Botões operação enviados para: {numero}] Status {res.status_code}: {res.text}")

#Cria botões(manualmente) da opções de ticket e envia para motorista
def enviar_opcoes_ticket(numero):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_API_TOKEN}/send-button-list"
    payload = {
        "phone": numero,
        "message": "Antes de nos enviar a foto do ticket, nos informe: Quem fez o carregamento dessa viagem?",
        "buttonList": {
            "buttons": [
                {"id": "eu_mesmo", "label": "Eu mesmo"},
                {"id": "outro_motorista", "label": "Outro motorista"},
                {"id": "voltar", "label": "Voltar"}
            ]
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": ZAPI_CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    logger.debug(f"[🟦 Botões opções Tickets enviados para: {numero}] Status {res.status_code}: {res.text}")

#Cria botões(manualmente) da opções de nf e envia para motorista
def enviar_opcoes_nf(numero):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_API_TOKEN}/send-button-list"
    payload = {
        "phone": numero,
        "message": "Antes de nos enviar a nota fiscal, nos informe: O que deseja enviar?",
        "buttonList": {
            "buttons": [
                {"id": "enviar_nf", "label": "Foto ou PDF da NF"},
                {"id": "adicionar_nf", "label": "Informação Adicional"},
                {"id": "voltar", "label": "Voltar"}
            ]
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": ZAPI_CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    logger.debug(f"[🟦 Botões opções NF enviados para: {numero}] Status {res.status_code}: {res.text}")

def enviar_confirmacao_nf(numero):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_API_TOKEN}/send-button-list"
    payload = {
        "phone": numero,
        "message": "⚠️ Essa opção deve ser utilizada apenas com instrução do seu programador, deseja realmente continuar?",
        "buttonList": {
            "buttons": [
                {"id": "confi_sim", "label": "Sim"},
                {"id": "confi_nao", "label": "Não"},
                {"id": "voltar", "label": "Voltar"}
            ]
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": ZAPI_CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    logger.debug(f"[🟦 Botões confirmação NF enviados para: {numero}] Status {res.status_code}: {res.text}")
