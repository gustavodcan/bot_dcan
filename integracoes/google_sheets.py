import json
import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_SHEETS_PATH

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
