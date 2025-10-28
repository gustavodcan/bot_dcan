# integracoes/a3soft/routes.py
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
    """
    Body esperado do SEU endpoint (interno): { "chaveAcesso":"..." }
    Obs: o token é sempre obtido agora, na hora do POST, via /login.
    """
    js = request.get_json(force=True)
    chave = js.get("chaveAcesso")
    if not chave:
        return jsonify({"ok": False, "error": "chaveAcesso_obrigatoria"}), 400

    # 1) sempre pega token
    auth = login_obter_token()
    if not auth.get("ok"): 
        return jsonify({"ok": False, "error": f"auth_falhou: {auth.get('error')}"}), 502
    token = auth["token"]

    # 2) chama ReceberXML com token + chaveAcesso
    res = receber_xml(token=token, chave_acesso=chave)
    return jsonify(res), (200 if res.get("ok") else 502)

@a3soft_bp.post("/enviar-nf")
def post_enviar_nf():
    """
    Body (interno): { "numeroViagem": 0, "chaveAcesso":"..." }
    O token é obtido automaticamente antes de enviar.
    """
    js = request.get_json(force=True)
    faltando = [k for k in ["numeroViagem","chaveAcesso"] if js.get(k) in [None,""]]
    if faltando:
        return jsonify({"ok": False, "error": f"campos_obrigatorios: {', '.join(faltando)}"}), 400

    auth = login_obter_token()
    if not auth.get("ok"): 
        return jsonify({"ok": False, "error": f"auth_falhou: {auth.get('error')}"}), 502
    token = auth["token"]

    res = enviar_nf(token=token, numero_viagem=js["numeroViagem"], chave_acesso=js["chaveAcesso"])
    return jsonify(res), (200 if res.get("ok") else 502)

@a3soft_bp.post("/enviar-ticket")
def post_enviar_ticket():
    """
    Body (interno):
      { "numeroViagem":0, "numeroNota":"...", "ticketBalanca":"...", "peso":0,
        "foto": { "nome":"...", "base64":"..." } (opcional) }
    O token é obtido automaticamente antes de enviar.
    """
    js = request.get_json(force=True)
    faltando = [k for k in ["numeroViagem","numeroNota","ticketBalanca","peso"] if js.get(k) in [None,""]]
    if faltando:
        return jsonify({"ok": False, "error": f"campos_obrigatorios: {', '.join(faltando)}"}), 400

    auth = login_obter_token()
    if not auth.get("ok"): 
        return jsonify({"ok": False, "error": f"auth_falhou: {auth.get('error')}"}), 502
    token = auth["token"]

    foto = js.get("foto") or {}
    res = enviar_ticket(
        token=token,
        numero_viagem=js["numeroViagem"],
        numero_nota=js["numeroNota"],
        ticket_balanca=js["ticketBalanca"],
        peso=js["peso"],
        foto_nome=foto.get("nome"),
        foto_base64=foto.get("base64"),
    )
    return jsonify(res), (200 if res.get("ok") else 502)
