import os, requests, logging
from config import INSTANCE_ID, API_TOKEN, CLIENT_TOKEN

logger = logging.getLogger(__name__)

def enviar_lista_viagens(numero, viagens):
    
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{API_TOKEN}/send-option-list"
    options = []
    for v in viagens:
        options.append({
            "rowId": f"VIAGEM|{v['numero_viagem']}",
            "title": str(v["numero_viagem"]),
            "description": f"{v['placa']} · {v['rota']}"
        })
        
    payload = {
        "phone": numero,
        "message": "Escolha a coleta (viagem):",
        "buttonText": "Selecionar",
        "title": "Suas coletas",
        "options": options
    }
    
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            logger.error("[Z-API] Falha ao enviar lista. Status: %s | Corpo: %s",
                         r.status_code, r.text)
            return False
        logger.debug("[Z-API] List enviada para %s", numero)
        return True
    except Exception:
        logger.error("[Z-API] Erro inesperado ao enviar lista", exc_info=True)
        return False

def enviar_mensagem(numero, texto):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{API_TOKEN}/send-text"
    payload = {"phone": numero, "message": texto}
    headers = {
        "Content-Type": "application/json",
        "Client-Token": CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    logger.debug(f"[🟢 Texto simples enviado] Status {res.status_code}: {res.text}")

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
    logger.debug(f"[🟦 Botões enviados] Status {res.status_code}: {res.text}")

def enviar_lista_setor(numero, mensagem):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{API_TOKEN}/send-option-list"
    payload = {
        "phone": numero,
        "message": mensagem,
        "optionList": {
            "title": "Setores DCAN",
            "buttonLabel": "Escolha o setor",
            "options": [
                {"id": "comercial", "description": "(Cotações, Novos serviços e Parcerias)", "title": "Comercial"},
                {"id": "faturamento", "description": "(Contratos, Conhecimentos e Comprovantes)", "title": "Faturamento"},
                {"id": "financeiro",  "description": "(Pagamentos, Descontos e Dúvidas)", "title": "Financeiro"},
                {"id": "recursos humanos", "description": "(Vagas, Documentação e Benefícios)", "title": "Recursos Humanos"},
                {"id": "operacao", "description": "(Coletas, Entregas e Tickets)", "title": "Operação"},
            ]
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    logger.debug(f"[🟪 Lista enviada] Status {res.status_code}: {res.text}")

def enviar_opcoes_operacao(numero):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{API_TOKEN}/send-button-list"
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
        "Client-Token": CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    logger.debug(f"[🟦 Botões operação enviados] Status {res.status_code}: {res.text}")
