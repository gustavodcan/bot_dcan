import os
import gspread
from google.oauth2.service_account import Credentials

# Liga/desliga aviso automático ao subir (Render)
NOTIFICAR_VIAGENS_ON_START = os.getenv("NOTIFICAR_VIAGENS_ON_START", "1") == "1"

# Configuração Google Sheets
SPREADSHEET_NAME = "tickets_dcan"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Autenticação
creds = Credentials.from_service_account_file("credenciais.json", scopes=SCOPES)
gc = gspread.authorize(creds)

def carregar_viagens_ativas():
    """Lê a planilha e retorna apenas viagens com Status == 'OK'."""
    sh = gc.open(SPREADSHEET_NAME)
    worksheet = sh.sheet1
    dados = worksheet.get_all_records()

    viagens_ativas = []
    for row in dados:
        if str(row.get("Status", "")).strip().upper() == "OK":
            viagens_ativas.append({
                "numero_viagem": str(row.get("Numero Viagem", "")).strip(),
                "data": row.get("Data", ""),
                "placa": row.get("Placa", ""),
                "telefone_motorista": str(row.get("Telefone Motorista", "")).strip(),
                "motorista": row.get("Nome Motorista", ""),
                "rota": row.get("Rota", ""),
                "remetente": row.get("Remetente", "")
            })
    return viagens_ativas

# Carrega viagens ativas na inicialização
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
