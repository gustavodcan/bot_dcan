# ===== Standard library =====
import logging
import os
import requests
import re

# ===== Local: mensagens =====
from mensagens import (
    enviar_mensagem,
    enviar_lista_setor,
)

logger = logging.getLogger(__name__)

def _normalizar_validar_placa(texto: str):
    placa = re.sub(r"[^A-Za-z0-9]", "", str(texto)).upper()
    padrao_antigo = re.compile(r"^[A-Z]{3}\d{4}$")
    padrao_mercosul = re.compile(r"^[A-Z]{3}\d[A-Z]\d{2}$")
    if padrao_antigo.match(placa) or padrao_mercosul.match(placa):
        return placa
    return None

def tratar_estado_aguardando_km_manutencao(numero, texto_recebido, conversas):

    if texto_recebido == "voltar":
        enviar_lista_setor(numero, "Selecione o Setor.")
        conv = conversas.setdefault(numero, {"estado": "aguardando_confirmacao_setor", "dados": {}})
        conv.setdefault("dados", {})
        conv["estado"] = "aguardando_confirmacao_setor"
        return {"status": "aguardando_confirmacao_setor"}
    
    km_str = re.sub(r"\D", "", str(texto_recebido))
    if not km_str:
        enviar_mensagem(numero, "❌ Não entendi o KM. Envie só números (ex.: 120345).")
        return {"status": "aguardando_km"}

    conv = conversas.setdefault(numero, {"estado": "aguardando_km_manutencao", "dados": {}})
    conv.setdefault("dados", {})
    conv["dados"]["km"] = int(km_str)
    conv["estado"] = "aguardando_placa_manutencao"

    enviar_mensagem(numero, "✅ KM anotado.\nQual a placa do veículo? (ex.: ABC1D23 ou ABC-1234)")
    return {"status": "km_recebido"}

def tratar_estado_aguardando_placa_manutencao(numero, texto_recebido, conversas):
    placa = _normalizar_validar_placa(texto_recebido)
    if not placa:
        enviar_mensagem(numero, "❌ Placa inválida. Tente novamente (ex.: ABC1D23 ou ABC-1234).")
        return {"status": "aguardando_placa"}

    conv = conversas.setdefault(numero, {"estado": "aguardando_placa_manutencao", "dados": {}})
    conv.setdefault("dados", {})
    conv["dados"]["placa"] = placa
    conv["estado"] = "aguardando_problema_manutencao"

    enviar_mensagem(numero, "✅ Placa anotada.\nQual o problema relatado?")
    return {"status": "aguardando_problema"}

def tratar_estado_aguardando_problema_manutencao(numero, texto_recebido, conversas):
    problema = str(texto_recebido).strip()
    if not problema:
        enviar_mensagem(numero, "❌ Me diga qual é o problema relatado (texto).")
        return {"status": "aguardando_problema"}

    conv = conversas.get(numero) or {"dados": {}}
    conv.setdefault("dados", {})
    conv["dados"]["problema"] = problema

    dados = conv["dados"]
    placa = dados.get("placa", "—")
    km = dados.get("km", "—")

    resumo = (
        "📋 *Abertura de Manutenção*\n"
        f"• Placa: {placa}\n"
        f"• KM: {km}\n"
        f"• Problema: {problema}\n\n"
        f"A placa {placa} com KM {km} está com o problema: {problema}."
    )

    enviar_mensagem(numero, resumo)
    conversas.pop(numero, None)
    return {"status": "finalizado", "mensagem": resumo}