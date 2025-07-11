import requests
import os

INSTANCE_ID = os.getenv("INSTANCE_ID")
API_TOKEN = os.getenv("API_TOKEN")
CLIENT_TOKEN = os.getenv("CLIENT_TOKEN")

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

def enviar_lista_clientes(numero, mensagem):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{API_TOKEN}/send-option-list"
    payload = {
        "phone": numero,
        "message": mensagem,
        "optionList": {
            "title": "Clientes DCAN",
            "buttonLabel": "Escolha o cliente",
            "options": [
                {"id": "arcelormittal", "title": "ArcelorMittal"},
                {"id": "gerdau", "title": "Gerdau"},
                {"id": "mahle", "title": "Mahle"},
                {"id": "raízen", "title": "Raízen"},
                {"id": "orizon", "title": "Orizon"},
                {"id": "cdr", "title": "CDR"},
                {"id": "saae", "title": "SAAE"}
            ]
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": CLIENT_TOKEN
    }
    res = requests.post(url, json=payload, headers=headers)
    print(f"[🟪 Lista enviada] Status {res.status_code}: {res.text}")
