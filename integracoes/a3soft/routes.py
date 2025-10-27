from flask import Blueprint, request, jsonify
from .client import login_obter_token, receber_xml, enviar_nf, enviar_ticket

a3soft_bp = Blueprint("a3soft_bp", __name__)

@a3soft_bp.post("/token")
def obter_token():
    js = request.get_json(silent=True) or {}
    res = login_obter_token(js.get("login"), js.get("senha"))
    return jsonify(res), (200 if res.get("ok") else 502)

@a3soft_bp.post("/receber-xml")
def post_receber_xml():
    js = request.get_json(force=True)
    token, xml = js.get("token"), js.get("xml")
    if not token or not xml:
        return jsonify({"ok": False, "error": "token_e_xml_obrigatorios"}), 400
    res = receber_xml(xml_str=xml, token=token)
    return jsonify(res), (200 if res.get("ok") else 502)

@a3soft_bp.post("/enviar-nf")
def post_enviar_nf():
    js = request.get_json(force=True)
    faltando = [k for k in ["token","numeroViagem","chaveAcesso"] if js.get(k) in [None, ""]]
    if faltando:
        return jsonify({"ok": False, "error": f"campos_obrigatorios: {', '.join(faltando)}"}), 400
    res = enviar_nf(js["token"], js["numeroViagem"], js["chaveAcesso"])
    return jsonify(res), (200 if res.get("ok") else 502)

@a3soft_bp.post("/enviar-ticket")
def post_enviar_ticket():
    js = request.get_json(force=True)
    faltando = [k for k in ["token","numeroViagem","numeroNota","ticketBalanca","peso"] if js.get(k) in [None, ""]]
    if faltando:
        return jsonify({"ok": False, "error": f"campos_obrigatorios: {', '.join(faltando)}"}), 400
    foto = js.get("foto") or {}
    res = enviar_ticket(
        token=js["token"],
        numero_viagem=js["numeroViagem"],
        numero_nota=js["numeroNota"],
        ticket_balanca=js["ticketBalanca"],
        peso=js["peso"],
        foto_nome=foto.get("nome"),
        foto_base64=foto.get("base64"),
    )
    return jsonify(res), (200 if res.get("ok") else 502)
