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

# integracoes/a3soft/client.py (topo: sessão)
_session = requests.Session()
_retry = Retry(
    total=1,                  # menos tentativas pra não "comer" o erro real
    connect=1,
    read=1,
    backoff_factor=0.5,
    status_forcelist=[429, 502, 503, 504],  # tira 500 daqui p/ não virar ResponseError
    allowed_methods=["POST"],
    raise_on_status=False,    # importante: não explode em 5xx, devolve resp
)
_adapter = HTTPAdapter(max_retries=_retry)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)


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
    """
    Chama /TNFeController/XML.
    O servidor pode responder:
      - JSON: { "xml": "<xml ...>" } (às vezes com aspas/escapes problemáticos)
      - ou o XML direto como texto.
    Retorna {"ok": True, "xml": "<xml>...</xml>"} quando der certo.
    """
    url = _abs(A3SOFT_BASE_URL, A3SOFT_ENDPOINT_XML)  # ex: "/datasnap/rest/TNFeController/XML"
    body = {"token": token, "chaveAcesso": str(chave_acesso)}

    def _parse_response(r):
        txt = r.text or ""
        status = r.status_code
        if status >= 400:
            return {"ok": False, "status": status, "error": "http_error", "text": txt[:2000]}

        ct = (r.headers.get("Content-Type") or "").lower()

        # 1) Caso JSON normal
        if "json" in ct or txt.lstrip().startswith("{"):
            # Tenta JSON "de verdade" primeiro
            try:
                j = r.json()
                if isinstance(j, dict) and j.get("xml"):
                    return {"ok": True, "xml": j["xml"]}
                # Se por algum motivo não tem 'xml', cai no fallback de regex
            except Exception:
                pass

            # 2) Fallback regex: extrai o valor de "xml": "..."
            m = re.search(r'"xml"\s*:\s*"(.*)"\s*}\s*$', txt, flags=re.DOTALL)
            if m:
                xml_quoted = m.group(1)
                # desescapa \n, \t, \", \uXXXX etc.
                try:
                    xml_unescaped = bytes(xml_quoted, "utf-8").decode("unicode_escape")
                    return {"ok": True, "xml": xml_unescaped}
                except Exception as je:
                    return {"ok": False, "status": status, "error": f"json_regex_decode_error: {je}", "text": txt[:2000]}

            # 3) Se ainda não deu, retorna erro informativo
            return {"ok": False, "status": status, "error": "json_sem_campo_xml", "text": txt[:2000]}

        # 4) Não é JSON — assume XML direto
        return {"ok": True, "xml": txt}

    try:
        r = _session.post(url, json=body, headers=JSON_HDRS, timeout=(10, 60))
        res = _parse_response(r)
        if res["ok"]:
            return res

        # Fallback: tenta PUT se for erro típico de rota/método
        if res.get("status") in (404, 405):
            r2 = _session.put(url, json=body, headers=JSON_HDRS, timeout=(10, 60))
            return _parse_response(r2)

        return res

    except requests.exceptions.RetryError:
        try:
            r = requests.post(url, json=body, headers=JSON_HDRS, timeout=(10, 60))
            return _parse_response(r)
        except Exception as ee:
            return {"ok": False, "status": None, "error": f"fallback_exception: {ee}", "text": ""}

    except Exception as e:
        return {"ok": False, "status": None, "error": str(e), "text": ""}

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
