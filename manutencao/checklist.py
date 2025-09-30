import logging, os, requests
from mensagens import enviar_mensagem

logger = logging.getLogger(__name__)

def tratar_estado_aguardando_km_manutencao (numero, texto_recebido, conversas):
    km_checklist = texto_recebido
    msg = (
        f"📋 Recebi os dados:\n"
        f"KM: {texto_recebido.title()}\n"
    )
    conversas[numero]["estado"] = "finalizado"
    conversas.pop(numero, None)
    return {"status": "finalizado"}
