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
    Chama /TNFeController/XML e devolve {"ok": True, "xml": "<xml...>"}.
    O servidor pode responder:
      - HTML contendo o XML (escapado ou não)
      - JSON {"xml":"..."} (raro)
      - XML puro
    """

    url = _abs(A3SOFT_BASE_URL, A3SOFT_ENDPOINT_XML)  # "/datasnap/rest/TNFeController/XML"
    body = {"token": token, "chaveAcesso": str(chave_acesso)}

    def _extract_xml_from_html(txt: str) -> str | None:
        """Tenta achar o XML dentro do HTML, lidando com escapes (&lt; &gt;)."""
        if not txt:
            return None

        # Se vier escapado, desescapa
        if "&lt;" in txt or "&gt;" in txt or "&quot;" in txt or "&amp;" in txt:
            txt = html.unescape(txt)

        # corta qualquer lixo antes/ depois — procura um início "plausível" de XML
        starts = ["<?xml", "<soap:Envelope", "<NFe", "<nfeProc", "<retConsNFeLog", "<nfeConsultaNFeLogResult"]
        start_idx = min([i for i in (txt.find(s) for s in starts) if i >= 0], default=-1)
        if start_idx < 0:
            return None
        cand = txt[start_idx:]

        # se houver fechamento de </html> depois, corta antes
        html_close = cand.lower().find("</html>")
        if html_close > 0:
            cand = cand[:html_close]

        # housekeeping: strip e tenta parsear "como está"
        cand = cand.strip()
        # se passar no XML parser, ótimo — se não, ainda assim devolvemos; quem chama decide/parsa/loga
        try:
            import xml.etree.ElementTree as ET
            ET.fromstring(cand)
            return cand
        except Exception:
            # Às vezes vem algum rodapé HTML residual; tente cortar após o último '>' de uma tag conhecida
            # tenta fechar em </soap:Envelope> ou </nfeProc>
            for end_tag in ["</soap:Envelope>", "</nfeProc>", "</retConsNFeLog>", "</nfeConsultaNFeLogResult>"]:
                j = cand.find(end_tag)
                if j > 0:
                    maybe = cand[: j + len(end_tag)]
                    try:
                        import xml.etree.ElementTree as ET
                        ET.fromstring(maybe)
                        return maybe
                    except Exception:
                        pass
            return cand  # devolve mesmo assim p/ o chamador logar/avaliar

    def _resp_to_dict(r: requests.Response) -> dict:
        txt = r.text or ""
        ct  = (r.headers.get("Content-Type") or "").lower()

        if r.status_code >= 400:
            return {"ok": False, "status": r.status_code, "error": "http_error", "text": txt[:2000]}

        # 1) HTML -> extrai XML
        if "html" in ct or txt.lstrip().lower().startswith("<!doctype html"):
            xml_candidate = _extract_xml_from_html(txt)
            if xml_candidate:
                return {"ok": True, "xml": xml_candidate}
            return {"ok": False, "status": r.status_code, "error": "html_sem_xml", "text": txt[:2000]}

        # 2) JSON -> tenta pegar campo xml
        if "json" in ct or txt.lstrip().startswith("{"):
            try:
                j = r.json()
                if isinstance(j, dict) and j.get("xml"):
                    return {"ok": True, "xml": j["xml"]}
            except Exception:
                # JSON malformado — tenta regex bruta
                m = re.search(r'"xml"\s*:\s*"(.*)"\s*}\s*$', txt, flags=re.DOTALL)
                if m:
                    return {"ok": True, "xml": m.group(1)}
            return {"ok": False, "status": r.status_code, "error": "json_sem_campo_xml", "text": txt[:2000]}

        # 3) Default: assume XML puro
        return {"ok": True, "xml": txt}

    try:
        r = _session.post(url, json=body, headers=JSON_HDRS, timeout=(10, 60))
        res = _resp_to_dict(r)
        if res["ok"]:
            return res

        # Fallback: alguns endpoints DataSnap aceitam PUT
        if res.get("status") in (404, 405):
            r2 = _session.put(url, json=body, headers=JSON_HDRS, timeout=(10, 60))
            return _resp_to_dict(r2)

        return res

    except requests.exceptions.RetryError:
        try:
            r = requests.post(url, json=body, headers=JSON_HDRS, timeout=(10, 60))
            return _resp_to_dict(r)
        except Exception as ee:
            return {"ok": False, "status": None, "error": f"fallback_exception: {ee}", "text": ""}
    except Exception as e:
        return {"ok": False, "status": None, "error": str(e), "text": ""}

def enviar_nf(token: str, numero_viagem: int, chave_acesso: str) -> dict:
    """
    POST /TMapaLogisticoController/ReceberNFe
    Body:
      { "token":"...", "numeroViagem": 0, "chaveAcesso":"..." }
    Retorna {"ok": True, "data": <json|texto>} ou {"ok": False, ...}
    """
    url = _abs(A3SOFT_BASE_URL, A3SOFT_ENDPOINT_NF)  # "/datasnap/rest/TMapaLogisticoController/ReceberNFe"
    body = {
        "token": token,
        "numeroViagem": int(numero_viagem),
        "chaveAcesso": str(chave_acesso),
    }

    try:
        r = _session.post(url, json=body, headers=JSON_HDRS, timeout=(10, 60))
        # alguns servidores respondem texto; tenta json mas aceita texto
        try:
            data = r.json()
        except Exception:
            data = (r.text or "").strip()

        if r.status_code >= 400:
            return {"ok": False, "status": r.status_code, "error": "http_error", "data": data}

        return {"ok": True, "data": data}

    except requests.exceptions.RetryError as e:
        return {"ok": False, "status": None, "error": f"retry_error: {e}"}
    except Exception as e:
        return {"ok": False, "status": None, "error": str(e)}

def enviar_ticket(
    token: str,
    numero_viagem: int,
    numero_nota: str,
    ticket_balanca: str,
    peso: int | float,
    valorMercadoria: int | float,
    quantidade: int | float,
    foto_nome: str | None = None,
    foto_base64: str | None = None
) -> dict:
    """
    POST /TMapaLogisticoController/TicketBalanca
    Body:
      {
        "token": "string",
        "numeroViagem": 0,
        "numeroNota": "string",
        "ticketBalanca": "string",
        "peso": 0,
        "valorMercadoria": 0,
        "quantidade": 0,
        "foto": {"nome": "string", "base64": "string"}  # opcional
      }
    """
    url = _abs(A3SOFT_BASE_URL, A3SOFT_ENDPOINT_TICKET)
    body = {
        "token": token,
        "numeroViagem": int(numero_viagem),
        "numeroNota": str(numero_nota),
        "ticketBalanca": str(ticket_balanca),
        "peso": float(peso),
        "valorMercadoria": float("1"),
        "quantidade": float("1"),
        "foto": {"nome": str(foto_nome), "base64": str(foto_base64)},
    }
    
    # 🔍 logs úteis
    try:
        import json
        foto_len = len(foto_base64 or "")
        #logger.debug(f"[A3/TICKET] Enviando body -> {json.dumps({**body, 'foto': {'nome': body['foto']['nome'], 'base64': f'<{foto_len} chars>'}}, ensure_ascii=False)[:2000]}")
    except Exception:
        #logger.debug(f"[A3/TICKET] Enviando body (repr) -> nome={body['foto']['nome']} base64_len={len(foto_base64 or '')}")

    try:
        r = _session.post(url, json=body, headers=JSON_HDRS, timeout=(10, 60))
        try:
            data = r.json()
        except Exception:
            data = (r.text or "").strip()

        #logger.debug(f"[A3/TICKET] Resposta HTTP {r.status_code} - corpo: {str(data)[:1000]}")

        if r.status_code >= 400:
            return {"ok": False, "status": r.status_code, "error": "http_error", "data": data}

        return {"ok": True, "data": data}
    except requests.exceptions.RetryError as e:
        logger.exception("[A3/TICKET] RetryError")
        return {"ok": False, "status": None, "error": f"retry_error: {e}"}
    except Exception as e:
        logger.exception("[A3/TICKET] Exceção geral")
        return {"ok": False, "status": None, "error": str(e)}
