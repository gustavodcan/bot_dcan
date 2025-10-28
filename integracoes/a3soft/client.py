# integracoes/a3soft/client.py
import logging, requests
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import (
    A3SOFT_BASE_URL, A3SOFT_LOGIN, A3SOFT_SENHA,
    A3SOFT_ENDPOINT_LOGIN, A3SOFT_ENDPOINT_XML,
    A3SOFT_ENDPOINT_NF, A3SOFT_ENDPOINT_TICKET
)

logger = logging.getLogger(__name__)

_session = requests.Session()
_retry = Retry(total=2, connect=2, read=2, backoff_factor=0.5,
               status_forcelist=[429,500,502,503,504], allowed_methods=["POST"])
_adapter = HTTPAdapter(max_retries=_retry)
_session.mount("http://", _adapter); _session.mount("https://", _adapter)

JSON_HDRS = {"Content-Type":"application/json","accept":"application/json"}

def _abs(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))

def login_obter_token(login: str | None=None, senha: str | None=None) -> dict:
    """Chama /login e retorna {"ok":True,"token":"...","data":{...}}"""
    url = _abs(A3SOFT_BASE_URL, A3SOFT_ENDPOINT_LOGIN)
    payload = {"wsautenticacao": login or A3SOFT_LOGIN, "wssenha": senha or A3SOFT_SENHA}
    try:
        r = _session.post(url, json=payload, headers=JSON_HDRS, timeout=(5,20))
        r.raise_for_status()
        data = r.json()
        tok = data.get("token")
        if not tok: return {"ok": False, "error":"token_ausente", "data": data}
        return {"ok": True, "token": tok, "data": data}
    except requests.exceptions.Timeout: return {"ok": False, "error":"timeout"}
    except requests.RequestException as e: return {"ok": False, "error": str(e)}
    except ValueError: return {"ok": False, "error":"invalid_json"}

def receber_xml(token: str, chave_acesso: str) -> dict:
    """POST /ReceberXML   Body: { "token":"...", "chaveAcesso":"..." }"""
    url = _abs(A3SOFT_BASE_URL, A3SOFT_ENDPOINT_XML)
    body = {"token": token, "chaveAcesso": str(chave_acesso)}
    try:
        r = _session.post(url, json=body, headers=JSON_HDRS, timeout=(5,60))
        r.raise_for_status()
        return {"ok": True, "data": r.json()}
    except Exception as e:
        logger.exception("[A3SOFT] Falha em ReceberXML"); return {"ok": False, "error": str(e)}

def enviar_nf(token: str, numero_viagem: int, chave_acesso: str) -> dict:
    """POST /ReceberNFe   Body: { "token":"...", "numeroViagem":0, "chaveAcesso":"..." }"""
    url = _abs(A3SOFT_BASE_URL, A3SOFT_ENDPOINT_NF)
    body = {"token": token, "numeroViagem": int(numero_viagem), "chaveAcesso": str(chave_acesso)}
    try:
        r = _session.post(url, json=body, headers=JSON_HDRS, timeout=(5,60))
        r.raise_for_status()
        return {"ok": True, "data": r.json()}
    except Exception as e:
        logger.exception("[A3SOFT] Falha em ReceberNFe"); return {"ok": False, "error": str(e)}

def enviar_ticket(token: str, numero_viagem: int, numero_nota: str,
                  ticket_balanca: str, peso: int | float,
                  foto_nome: str | None=None, foto_base64: str | None=None) -> dict:
    """
    POST /TicketBalanca
    Body: { "token":"...","numeroViagem":0,"numeroNota":"...","ticketBalanca":"...","peso":0,
            "foto":{"nome":"...","base64":"..."} (opcional) }
    """
    url = _abs(A3SOFT_BASE_URL, A3SOFT_ENDPOINT_TICKET)
    body = {
        "token": token,
        "numeroViagem": int(numero_viagem),
        "numeroNota": str(numero_nota),
        "ticketBalanca": str(ticket_balanca),
        "peso": float(peso),
    }
    if foto_nome and foto_base64:
        body["foto"] = {"nome": foto_nome, "base64": foto_base64}
    try:
        r = _session.post(url, json=body, headers=JSON_HDRS, timeout=(5,60))
        r.raise_for_status()
        return {"ok": True, "data": r.json()}
    except Exception as e:
        logger.exception("[A3SOFT] Falha em TicketBalanca"); return {"ok": False, "error": str(e)}
