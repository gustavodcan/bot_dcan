import os, base64, logging, requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import CERTIFICADO_BASE64, CERTIFICADO_SENHA, CHAVE_AES, INFOSIMPLES_TOKEN

logger = logging.getLogger(__name__)

def aes_encrypt_urlsafe(texto: str, chave: str) -> str:
    key = chave.encode("utf-8")
    key = key.ljust(32, b"\0")[:32]
    cipher = AES.new(key, AES.MODE_ECB)
    texto_padded = pad(texto.encode("utf-8"), AES.block_size)
    encrypted = cipher.encrypt(texto_padded)
    b64 = base64.b64encode(encrypted).decode()
    return b64.replace("+", "-").replace("/", "_").rstrip("=")

def salvar_certificado_temporario() -> str:
    cert_bytes = base64.b64decode(CERTIFICADO_BASE64)
    caminho_cert = "/tmp/certificado_temp.pfx"
    with open(caminho_cert, "wb") as f:
        f.write(cert_bytes)
    return caminho_cert

def gerar_criptografia_infosimples(_caminho_cert: str):
    pkcs12_cert = aes_encrypt_urlsafe(CERTIFICADO_BASE64, CHAVE_AES)
    pkcs12_pass = aes_encrypt_urlsafe(CERTIFICADO_SENHA, CHAVE_AES)
    return pkcs12_cert, pkcs12_pass

_session = requests.Session()
_retry = Retry(
    total=2,                 
    connect=2,
    read=2,
    backoff_factor=0.5,      
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["POST"],  
)
_adapter = HTTPAdapter(max_retries=_retry)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)

_BASE_URL = "https://api.infosimples.com/api/v2/consultas/receita-federal/nfe"

def consultar_nfe_infosimples(chave_nfe: str, pkcs12_cert: str, pkcs12_pass: str) -> dict:
    payload = {
        "nfe": chave_nfe,
        "pkcs12_cert": pkcs12_cert,
        "pkcs12_pass": pkcs12_pass,
        "token": INFOSIMPLES_TOKEN,
        "timeout": 300,  
    }
    try:
        resp = _session.post(_BASE_URL, json=payload, timeout=(5, 20))  
        resp.raise_for_status()
        data = resp.json()
        logger.debug("📦 InfoSimples (crypto) OK")
        return data
    except requests.exceptions.Timeout:
        logger.error("⏳ Timeout ao consultar InfoSimples (crypto)", exc_info=True)
        return {"code": 504, "code_message": "Timeout ao consultar InfoSimples", "data": []}
    except requests.RequestException as e:
        logger.error(f"🌩️ Erro HTTP InfoSimples (crypto): {e}", exc_info=True)
        return {"code": 500, "code_message": str(e), "data": []}
    except ValueError as e:
        logger.error(f"🧩 JSON inválido InfoSimples (crypto): {e}", exc_info=True)
        return {"code": 500, "code_message": "Resposta inválida da InfoSimples", "data": []}

def consultar_nfe_completa(chave_nfe: str) -> dict:
    try:
        if not CERTIFICADO_BASE64 or not CERTIFICADO_SENHA or not INFOSIMPLES_TOKEN:
            raise ValueError("Variáveis de ambiente faltando (certificado/senha/token).")

        payload = {
            "nfe": chave_nfe,
            "pkcs12_cert": CERTIFICADO_BASE64,
            "pkcs12_pass": CERTIFICADO_SENHA,
            "token": INFOSIMPLES_TOKEN,
            "timeout": 300,  
        }

        resp = _session.post(_BASE_URL, json=payload, timeout=(10, 60))
        resp.raise_for_status()

        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("Resposta da API não é um objeto JSON.")

        logger.debug(f"📦 InfoSimples OK (code={data.get('code')}) para chave {chave_nfe}")

        return data

    except requests.exceptions.Timeout:
        logger.error("⏳ Timeout ao consultar InfoSimples", exc_info=True)
        return {"code": 504, "code_message": "Timeout ao consultar InfoSimples", "data": []}
    except requests.RequestException as e:
        logger.error(f"🌩️ Erro HTTP InfoSimples: {e}", exc_info=True)
        return {"code": 500, "code_message": str(e), "data": []}
    except ValueError as e:
        logger.error(f"🧩 Resposta inválida da InfoSimples: {e}", exc_info=True)
        return {"code": 500, "code_message": "Resposta inválida da InfoSimples", "data": []}
    except Exception as e:
        logger.error(f"❌ Erro inesperado ao consultar NF-e: {e}", exc_info=True)
        return {"code": 500, "code_message": "Erro interno", "errors": [str(e)], "data": []}
