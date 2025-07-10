if estado == "aguardando_confirmacao_motorista":
    if texto_recebido in ['sim', 's']:
        enviar_lista_clientes(numero, "✅ Perfeito! Para qual cliente a descarga foi realizada?")
        conversas[numero]["estado"] = "aguardando_cliente"
    elif texto_recebido in ['não', 'nao', 'n']:
        enviar_mensagem(numero, "📞 Peço por gentileza então, que entre em contato com o número (XX) XXXX-XXXX. Obrigado!")
        conversas.pop(numero)
    else:
        enviar_botoes_sim_nao(numero, "❓ Por favor, clique em *Sim* ou *Não*.")
    return jsonify(status="resposta motorista")

if estado == "aguardando_cliente":
    clientes_map = {
        "arcelormittal": "ArcelorMittal",
        "gerdau": "Gerdau",
        "proactiva": "ProActiva",
        "raizen": "Raízen"
    }
    cliente = clientes_map.get(texto_recebido, texto_recebido.capitalize())
    conversas[numero]["dados"] = {"cliente": cliente}
    enviar_mensagem(numero, f"🚚 Obrigado! Cliente informado: {cliente}.\nPor gentileza, envie a foto do ticket.")
    conversas[numero]["estado"] = "aguardando_imagem"
    return jsonify(status="cliente recebido")

if estado == "aguardando_confirmacao":
    if texto_recebido in ['sim', 's']:
        enviar_mensagem(numero, "✅ Dados confirmados! Salvando as informações. Obrigado!")
        conversas.pop(numero)
    elif texto_recebido in ['não', 'nao', 'n']:
        enviar_mensagem(numero, "🔁 OK! Por favor, envie a foto do ticket novamente.")
        conversas[numero]["estado"] = "aguardando_imagem"
    else:
        enviar_botoes_sim_nao(numero, "❓ Por favor, clique em *Sim* ou *Não*.")
    return jsonify(status="confirmação final")
