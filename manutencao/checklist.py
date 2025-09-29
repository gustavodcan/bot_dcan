import logging, os, requests
from mensagens import enviar_mensagem

logger = logging.getLogger(__name__)

if estado == "aguardando_placa_manutencao":
  enviar_mensagem(numero, f"✏️ Por favor, envie a placa do veículo.")
  else:
    enviar_lista_setor(numero, "❌ Opção inválida. Por favor, escolha uma opção da lista.")
  return jsonify(status="resposta motorista")
