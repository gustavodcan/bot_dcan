import logging, os, requests
from mensagens import enviar_mensagem

logger = logging.getLogger(__name__)

def tratar_estado_aguardando_km_manutencao(numero, texto_recebido, conversas):
    km_checklist = str(texto_recebido).strip()
    msg = (
        f"📋 Recebi os dados:\n"
        f"KM: {km_checklist}\n"
    )
    enviar_mensagem(numero, msg)
    conversas[numero] = {"estado": "finalizado"}
    return {"status": "finalizado", "mensagem": msg}
