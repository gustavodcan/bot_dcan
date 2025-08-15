import os
from google.oauth2.service_account import Credentials
import gspread

# Liga/desliga aviso automático ao subir (Render)
NOTIFICAR_VIAGENS_ON_START = os.getenv("NOTIFICAR_VIAGENS_ON_START", "1") == "1"

# Nome da planilha e aba
SHEET_NAME = "tickets_dcan"
WORKSHEET_NAME = "tickets_dcan"

def conectar_google_sheets():
    cred_json_str = os.getenv("GOOGLE_CREDS_JSON")
    if not cred_json_str:
        raise RuntimeError("Variável de ambiente GOOGLE_CREDS_JSON não encontrada.")
    
    import json
    cred_info = json.loads(cred_json_str)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(cred_info, scopes=scopes)
    client = gspread.authorize(creds)
    return client

def carregar_viagens_ativas():
    """Busca na planilha todas as viagens com status 'ok'."""
    client = conectar_google_sheets()
    ws = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    dados = ws.get_all_records()

    viagens_ativas = []
    for row in dados:
        if str(row.get("Status", "")).strip().lower() == "ok":
            viagens_ativas.append({
                "numero_viagem": str(row.get("Numero Viagem", "")).strip(),
                "data": str(row.get("Data", "")).strip(),
                "placa": str(row.get("Placa", "")).strip(),
                "telefone_motorista": str(row.get("Telefone Motorista", "")).strip(),
                "motorista": str(row.get("Motorista", "")).strip(),
                "rota": str(row.get("Rota", "")).strip(),
                "remetente": str(row.get("Remetente", "")).strip()
            })
    return viagens_ativas

# Inicializa as viagens na carga do módulo
VIAGENS = carregar_viagens_ativas()

# Mapa rápido: telefone -> número da viagem
VIAGEM_POR_TELEFONE = {v["telefone_motorista"]: v["numero_viagem"] for v in VIAGENS}

def get_viagens_por_telefone(telefone: str):
    return [v for v in VIAGENS if v.get("telefone_motorista") == telefone]

VIAGEM_ATIVA_POR_TELEFONE = {}

def set_viagem_ativa(telefone: str, numero_viagem: str):
    VIAGEM_ATIVA_POR_TELEFONE[telefone] = numero_viagem

def get_viagem_ativa(telefone: str):
    return VIAGEM_ATIVA_POR_TELEFONE.get(telefone)
