import logging
import requests
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import NSDOCS_BASE_URL, NSDOCS_TOKEN, NSDOCS_EMPRESA_CNPJ

logger = logging.getLogger(__name__)

_session = requests.Session()
_retry = Retry(
    total=2, connect=2, read=2, backoff_factor=0.3,
    status_forcelist=[429, 502, 503, 504], allowed_methods=["GET","POST"]
)
_adapter = HTTPAdapter(max_retries=_retry)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)

def _abs(path: str) -> str:
    return urljoin(NSDOCS_BASE_URL.rstrip("/") + "/", path.lstrip("/"))

BASE_HEADERS = {
    "Authorization": f"Bearer {NSDOCS_TOKEN}",
    "Empresa-Cnpj": NSDOCS_EMPRESA_CNPJ,
    "Accept": "application/json; charset=utf-8",
    "Accept-Encoding": "gzip",
}

def consultar_documentos(chave_acesso: str):
    """
    GET /documentos?filtro={chave}&campos=emitente_nome,emitente_cnpj,destinatario_nome,destinatario_cnpj,numero,data_emissao,peso
    Retorno esperado: lista []
    """
    url = _abs("/documentos")
    params = {
        "filtro": chave_acesso,
        "campos": "emitente_nome,emitente_cnpj,destinatario_nome,destinatario_cnpj,numero,data_emissao,peso",
    }
    try:
        r = _session.get(url, headers=BASE_HEADERS, params=params, timeout=30)
        txt = (r.text or "").strip()
        try:
            data = r.json()
        except Exception:
            logger.error(f"[NSDOCS][GET] JSON inválido: status={r.status_code} body={txt[:800]}")
            return {"ok": False, "status": r.status_code, "error": "invalid_json", "text": txt[:800]}
        logger.debug(f"[NSDOCS][GET] {r.status_code} body={str(data)[:800]}")
        if r.status_code != 200:
            return {"ok": False, "status": r.status_code, "error": "http_error", "data": data}
        if not isinstance(data, list):
            return {"ok": False, "status": r.status_code, "error": "unexpected_schema", "data": data}
        return {"ok": True, "data": data}
    except Exception as e:
        logger.exception("[NSDOCS][GET] exceção")
        return {"ok": False, "status": None, "error": str(e)}

def consultar_chave_acesso(chave_acesso: str):
    """
    POST /consultar/dfe (x-www-form-urlencoded) body: documento={chave}
    Retorno 200 indica que indexou/consultou; depois chame GET novamente.
    """
    url = _abs("/consultar/dfe")
    headers = dict(BASE_HEADERS)
    # x-www-form-urlencoded
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    body = {"documento": chave_acesso}
    try:
        r = _session.post(url, headers=headers, data=body, timeout=30)
        txt = (r.text or "").strip()
        # pode ser que retorne texto simples; tenta json, mas não exige
        try:
            j = r.json()
        except Exception:
            j = txt
        logger.debug(f"[NSDOCS][POST dfe] {r.status_code} body={str(j)[:800]}")
        if r.status_code != 200:
            return {"ok": False, "status": r.status_code, "error": "http_error", "body": j}
        return {"ok": True, "data": j}
    except Exception as e:
        logger.exception("[NSDOCS][POST dfe] exceção")
        return {"ok": False, "status": None, "error": str(e)}

def buscar_ou_consultar_e_buscar(chave_acesso: str):
    """
    Orquestração: GET documentos; se vier vazio [], faz POST dfe; se 200, faz GET novamente.
    Retorna sempre um dict com lista em 'data' (pode ser vazia se continuar sem resultados).
    """
    # 1) GET inicial
    g1 = consultar_documentos(chave_acesso)
    if not g1.get("ok"):
        return g1
    if g1["data"]:
        return g1  # já achou

    # 2) vazio -> POST consultar/dfe
    p = consultar_chave_acesso(chave_acesso)
    if not p.get("ok"):
        return p

    # 3) GET novamente
    g2 = consultar_documentos(chave_acesso)
    return g2
