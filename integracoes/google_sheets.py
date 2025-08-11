import json
import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_SHEETS_PATH
from datetime import datetime

def conectar_google_sheets():
    with open(GOOGLE_SHEETS_PATH, 'r') as f:
        cred_json_str = f.read()
    cred_info = json.loads(cred_json_str)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(cred_info, scopes=scopes)
    client = gspread.authorize(creds)
    return client
def _get_sheet():
    client = conectar_google_sheets()
    # ajuste NOME DA PLANILHA e da ABA se diferente
    sh = client.open("tickets_dcan")
    ws = sh.worksheet("tickets_dcan")
    return ws

def _map_header(ws):
    """Retorna dict {nome_coluna: indice_coluna} lendo a primeira linha."""
    header = ws.row_values(1)
    return {col.strip(): idx+1 for idx, col in enumerate(header)}

def _find_or_create_row_by_viagem(ws, numero_viagem: str, header_map: dict):
    # tenta achar a linha pelo valor exato na coluna "Numero Viagem"
    col_name = "Numero Viagem"
    col_idx = header_map.get(col_name)
    if not col_idx:
        raise RuntimeError(f"Coluna '{col_name}' não encontrada na planilha.")

    # Procura todas as ocorrências
    cells = ws.findall(numero_viagem)
    for c in cells or []:
        if c.col == col_idx:
            return c.row

    # não achou: cria uma nova linha (append) com Número Viagem preenchido
    # garante o tamanho do row com base no header
    nova_linha = [""] * len(header_map)
    nova_linha[col_idx-1] = numero_viagem
    ws.append_row(nova_linha)
    # a nova linha é a última
    return ws.row_count

def atualizar_viagem_nf(numero_viagem: str, telefone: str, chave_acesso: str, nota_fiscal: str, data_envio: str = None):
    ws = _get_sheet()
    header = _map_header(ws)
    row = _find_or_create_row_by_viagem(ws, numero_viagem, header)

    data_envio = data_envio or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    updates = {
        "Data Envio NF": data_envio,            
        "Telefone Envio NF": telefone,
        "Chave de Acesso": chave_acesso,
        "Nota Fiscal": nota_fiscal,
    }

    batch = []
    for col_name, value in updates.items():
        col_idx = header.get(col_name)
        if col_idx:
            batch.append({
                "range": gspread.utils.rowcol_to_a1(row, col_idx),
                "values": [[value]]
            })
    if batch:
        ws.batch_update([{"range": b["range"], "values": b["values"]} for b in batch])

def atualizar_viagem_ticket(numero_viagem: str, telefone: str, ticket: str, peso: str, origem: str, data_envio: str = None):
    ws = _get_sheet()
    header = _map_header(ws)
    row = _find_or_create_row_by_viagem(ws, numero_viagem, header)

    data_envio = data_envio or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    updates = {
        "Data Envio Ticket": data_envio,
        "Telefone Envio Ticket": telefone,
        "Ticket": ticket,
        "Peso": peso,
        "Origem": origem,
    }

    batch = []
    for col_name, value in updates.items():
        col_idx = header.get(col_name)
        if col_idx:
            batch.append({
                "range": gspread.utils.rowcol_to_a1(row, col_idx),
                "values": [[value]]
            })
    if batch:
        ws.batch_update([{"range": b["range"], "values": b["values"]} for b in batch])
