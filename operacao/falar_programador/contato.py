from mensagens import enviar_mensagem

# Redireciona mensagem digitada para número do setor
def encaminhar_para_setor(numero_usuario, setor, mensagem):
    mapa_setores = {
        "comercial": "5515997008800",
        "faturamento": "5515997008800",
        "financeiro": "5515997008800",
        "recursos humanos": "5515997008800"
    }
    numero_destino = mapa_setores.get(setor)
    if not numero_destino:
        print(f"Setor '{setor}' não encontrado.")
        return

    texto = f"📥 Atendimento automático\nPor favor, não responda.\n\n O telefone: {numero_usuario} solicitou contato do setor {setor.title()} através da seguinte mensagem:\n\n{mensagem}"

    url = f"https://api.z-api.io/instances/{os.getenv('INSTANCE_ID')}/token/{os.getenv('API_TOKEN')}/send-text"
    payload = {
        "phone": numero_destino,
        "message": texto
    }
    headers = {
        "Content-Type": "application/json",
        "Client-Token": os.getenv("CLIENT_TOKEN")
    }
    res = requests.post(url, json=payload, headers=headers)
    print(f"[📨 Encaminhado para {setor}] Status {res.status_code}: {res.text}")

# Trata descrições fornecidas para setores não-operacionais
def tratar_descricao_setor(numero, mensagem_original):
    setor = conversas[numero].get("setor")
    if setor:
        encaminhar_para_setor(numero_usuario=numero, setor=setor, mensagem=mensagem_original)
        enviar_mensagem(numero, f"📨 Sua mensagem foi encaminhada ao setor {setor.title()}. Em breve alguém entrará em contato.")
        conversas[numero]["estado"] = "finalizado"
        conversas.pop(numero, None)
    else:
        enviar_lista_setor(numero, "⚠️ Setor não identificado. Vamos começar novamente.")
        conversas[numero] = {"estado": "aguardando_setor"}
