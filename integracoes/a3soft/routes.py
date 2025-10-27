import logging
from flask import Blueprint, request, jsonify
from .client import login_obter_token, receber_xml, enviar_nf, enviar_ticket

logger = logging.getLogger(__name__)
a3soft_bp = Blueprint("a3soft_bp", __name__)

@a3soft_bp.post("/token")
def obter_token():
    """
    POST /integracoes/a3soft/token
    Body opcional: { "login": "...", "senha": "..." }
    """
    js = request.get_json(silent=True) or {}
    res = login_obter_token(js.get("login"), js.get("senha"))
    return jsonify(res), (200 if res.get("ok") else 502)

@a3soft_bp.post("/receber-xml")
def post_receber_xml():
    """
    POST /integracoes/a3soft/receber-xml
    Body:
      { "token":"...", "xml":"<NFe>...</NFe>" }
    """
    js = request.get_json(force=True)
    token = js.get("token")
    xml   = js.get("xml")
    if not token:
        return jsonify({"ok": False, "error": "token_obrigatorio"}), 400
    if not xml:
        return jsonify({"ok": False, "error": "xml_obrigatorio"}), 400

    res = receber_xml(xml_str=xml, token=token)
    return jsonify(res), (200 if res.get("ok") else 502)

@a3soft_bp.post("/enviar-nf")
def post_enviar_nf():
    """
    POST /integracoes/a3soft/enviar-nf
    Body:
      { "token":"...", "numeroViagem": 0, "chaveAcesso":"..." }
    """
    js = request.get_json(force=True)
    token = js.get("token")
    numero_viagem = js.get("numeroViagem")
    chave_acesso  = js.get("chaveAcesso")

    missing = [k for k in ["token","numeroViagem","chaveAcesso"] if not js.get(k) and js.get(k) != 0]
    if missing:
        return jsonify({"ok": False, "error": f"campos_obrigatorios: {', '.join(missing)}"}), 400

    res = enviar_nf(token=token, numero_viagem=numero_viagem, chave_acesso=chave_acesso)
    return jsonify(res), (200 if res.get("ok") else 502)

@a3soft_bp.post("/enviar-ticket")
def post_enviar_ticket():
    """
    POST /integracoes/a3soft/enviar-ticket
    Body:
      {
        "token":"...",
        "numeroViagem": 0,
        "numeroNota": "string",
        "ticketBalanca": "string",
        "peso": 0,
        "foto": { "nome": "string", "base64": "string" }    # opcional
      }
    """
    js = request.get_json(force=True)
    token          = js.get("token")
    numero_viagem  = js.get("numeroViagem")
    numero_nota    = js.get("numeroNota")
    ticket_balanca = js.get("ticketBalanca")
    peso           = js.get("peso")
    foto           = js.get("foto") or {}
    foto_nome      = foto.get("nome")
    foto_base64    = foto.get("base64")

    missing = [k for k in ["token","numeroViagem","numeroNota","ticketBalanca","peso"] if js.get(k) in [None, ""]]
    if missing:
        return jsonify({"ok": False, "error": f"campos_obrigatorios: {', '.join(missing)}"}), 400

    res = enviar_ticket(
        token=token,
        numero_viagem=numero_viagem,
        numero_nota=numero_nota,
        ticket_balanca=ticket_balanca,
        peso=peso,
        foto_nome=foto_nome,
        foto_base64=foto_base64
    )
    return jsonify(res), (200 if res.get("ok") else 502)

