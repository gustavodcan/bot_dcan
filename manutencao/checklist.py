import logging, os, re, requests
from mensagens import enviar_mensagem

logger = logging.getLogger(__name__)

def tratar_estado_aguardando_km_manutencao(numero, texto_recebido, conversas):
    km_checklist = re.sub(r"\D", "", str(texto_recebido))
#    if not km_checklist:
#        return None
#    try:
#        return int(km_checklist)
#    except ValueError:
#        return None
    
    conversas[numero]["dados"]["km"] = km_checklist
    enviar_mensagem(numero, "✅ KM anotado.\nQual a placa do veículo? (ex.: ABC1D23 ou ABC-1234)")
    conversas[numero] = {"estado": "aguardando_placa_manutencao"}
    return {"status": "km recebido"}

def tratar_estado_aguardando_placa_manutencao(numero, texto_recebido, conversas):
    placa = re.sub(r"[^A-Za-z0-9]", "", str(texto_recebido)).upper()
    conversas[numero]["dados"]["placa"] = placa
    enviar_mensagem(numero, "✅ Placa anotada.\nQual o problema relatado?")
    conversas[numero]["estado"] = "aguardando_problema_manutencao"
    return {"status": "aguardando_problema"}
    
def tratar_estado_aguardando_problema_manutencao(numero, texto_recebido, conversas):
        problema = str(texto_recebido).strip()
        if not problema:
            enviar_mensagem(numero, "❌ Me diga qual é o problema relatado (texto).")
            return {"status": "aguardando_problema"}

        conversas[numero]["dados"]["problema"] = problema
        # Monta o resumo final
        dados = conversas[numero]["dados"]
        resumo = (
            "📋 *Abertura de Manutenção*\n"
            f"• Placa: {dados['placa']}\n"
            f"• KM: {dados['km']}\n"
            f"• Problema: {dados['problema']}\n\n"
            f"A placa {dados['placa']} com KM {dados['km']} está com o problema: {dados['problema']}."
        )

        enviar_mensagem(numero, resumo)
        conversas.pop(numero, None)  # encerra o fluxo
        return {"status": "finalizado", "mensagem": resumo}
