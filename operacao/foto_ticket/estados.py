import os, re, requests
from datetime import datetime
from integracoes.google_sheets import conectar_google_sheets
from mensagens import enviar_mensagem, enviar_botoes_sim_nao
from operacao.foto_ticket.defs import limpar_texto_ocr, detectar_cliente_por_texto
from operacao.foto_ticket.defs import extrair_dados_por_cliente
from integracoes.google_vision import preprocessar_imagem, ler_texto_google_ocr
from integracoes.azure import salvar_imagem_azure

def tratar_estado_aguardando_imagem(numero, data, conversas):
    if "image" not in data or not data["image"].get("mimeType", "").startswith("image/"):
        enviar_mensagem(numero, "📸 Por favor, envie uma imagem do ticket para prosseguir.")
        return {"status": "aguardando imagem"}

    url_img = data["image"]["imageUrl"]
    try:
        img_res = requests.get(url_img)
        if img_res.status_code == 200:
            with open("ticket.jpg", "wb") as f:
                f.write(img_res.content)
        else:
            enviar_mensagem(numero, "❌ Erro ao baixar a imagem. Tente novamente.")
            return {"status": "erro ao baixar"}
    except Exception:
        enviar_mensagem(numero, "❌ Erro ao baixar a imagem. Tente novamente.")
        return {"status": "erro ao baixar"}

    img = preprocessar_imagem("ticket.jpg")
    img.save("ticket_pre_google.jpg")
    texto = ler_texto_google_ocr("ticket_pre_google.jpg")

    texto = limpar_texto_ocr(texto)
    conversas[numero] = conversas.get(numero, {})
    conversas[numero]["ocr_texto"] = texto

    cliente = detectar_cliente_por_texto(texto)
    conversas[numero]["cliente"] = cliente
    if cliente == "cliente_desconhecido":
        enviar_mensagem(numero, "❌ Não consegui identificar o cliente. Envie outra foto ou fale com o programador.")
        conversas[numero]["estado"] = "aguardando_imagem"
        return {"status": "cliente não identificado"}

    if cliente == "saae":
        conversas[numero]["estado"] = "aguardando_destino_saae"
        enviar_mensagem(numero, "🛣️ Cliente SAAE detectado! Informe a *origem da carga* (ex: ETA Vitória).")
        return {"status": "aguardando destino saae"}

    dados = extrair_dados_por_cliente(cliente, texto)

    if dados.get("erro"):
        conversas[numero]["estado"] = "aguardando_imagem"
        enviar_mensagem(numero, "❌ Erro ao processar os dados. Envie uma nova imagem.")
        return {"status": "erro ao extrair dados"}

    conversas[numero]["dados"] = dados
    nota = dados.get("nota_fiscal", "").strip().upper()

    if cliente == "orizon" or (cliente == "cdr" and nota in ["NÃO ENCONTRADO", "", None]):
        conversas[numero]["estado"] = "aguardando_nota_manual"
        enviar_mensagem(numero, "🧾 Por favor, envie o número da nota fiscal para continuar\n(Ex: *7878*).")
        return {"status": "solicitando nota manual"}

    ticket_ou_brm = dados.get("ticket") or dados.get("brm_mes")
    campos_obrigatorios = {
        "ticket ou brm_mes": ticket_ou_brm,
        "peso_liquido": dados.get("peso_liquido"),
        "nota_fiscal": dados.get("nota_fiscal")
    }

    dados_faltando = [
        nome for nome, valor in campos_obrigatorios.items()
        if not valor or "NÃO ENCONTRADO" in str(valor).upper()
    ]

    if dados_faltando:
        enviar_mensagem(
            numero,
            "⚠️ Não consegui identificar todas as informações. "
            "Por favor, tire uma nova foto do ticket com mais nitidez e envie novamente."
        )
        conversas[numero]["estado"] = "aguardando_imagem"
        conversas[numero].pop("dados", None)
        try:
            os.remove("ticket.jpg")
        except FileNotFoundError:
            pass
        return {"status": "dados incompletos"}

    msg = (
        f"📋 Recebi os dados:\n"
        f"Cliente: {cliente.title()}\n"
        f"Ticket: {ticket_ou_brm}\n"
        f"Peso Líquido: {dados.get('peso_liquido')}\n"
        f"Nota Fiscal: {dados.get('nota_fiscal') or 'Não encontrada'}\n\n"
        f"Está correto?"
    )
    conversas[numero]["estado"] = "aguardando_confirmacao"
    enviar_botoes_sim_nao(numero, msg)
    return {"status": "aguardando confirmação"}

def tratar_estado_aguardando_confirmacao(numero, texto_recebido, conversas):
    if texto_recebido in ['sim', 's']:
        dados_confirmados = conversas[numero]["dados"]

        payload = {
            "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cliente": conversas[numero].get("cliente", "").upper(),
            "ticket": dados_confirmados.get("ticket"),
            "nota_fiscal": dados_confirmados.get("nota_fiscal"),
            "peso": dados_confirmados.get("peso_liquido"),
            "destino": dados_confirmados.get("destino", "N/A"),
            "telefone": numero
        }

        try:
            client = conectar_google_sheets()
            planilha = client.open("tickets_dcan").worksheet("tickets_dcan")
            planilha.append_row([
                payload["data"], payload["cliente"], payload["ticket"],
                payload["nota_fiscal"], payload["peso"], payload["destino"],
                payload["telefone"]
            ])
        except Exception as e:
            print(f"❌ Erro ao salvar na planilha: {e}")
            enviar_mensagem(numero, "❌ Erro ao salvar os dados. Contate o suporte.")
            conversas[numero]["estado"] = "finalizado"
            return {"status": "erro ao salvar"}

        try:
            nome_imagem = f"{payload['cliente']}/{payload['cliente']}_{payload['nota_fiscal']}.jpg"
            salvar_imagem_azure("ticket.jpg", nome_imagem)
            os.remove("ticket.jpg")
        except Exception as e:
            print(f"⚠️ Erro ao salvar ou remover imagem: {e}")

        enviar_mensagem(numero, "✅ Dados confirmados, Salvando as informações! Obrigado!")
        conversas.pop(numero)
        return {"status": "finalizado"}

    elif texto_recebido in ['não', 'nao', 'n']:
        enviar_mensagem(numero, "🔁 OK! Por favor, envie a foto do ticket novamente.")
        conversas[numero]["estado"] = "aguardando_imagem"
        conversas[numero].pop("cliente", None)
        conversas[numero].pop("dados", None)
        return {"status": "aguardando nova imagem"}

    else:
        enviar_botoes_sim_nao(numero, "❓ Por favor, clique em *Sim* ou *Não*.")
        return {"status": "aguardando resposta válida"}

def tratar_estado_aguardando_nota_manual(numero, texto_recebido, conversas):
    nota_digitada = re.search(r"\b\d{4,}\b", texto_recebido)
    if not nota_digitada:
        enviar_mensagem(numero, "❌ Por favor, envie apenas o número da nota.\n(Ex: *7878*).")
        return {"status": "nota inválida"}

    nota_val = nota_digitada.group(0)
    dados_atuais = conversas[numero].get("dados", {})
    cliente = conversas[numero].get("cliente")
    texto_ocr = conversas[numero].get("ocr_texto", "")

    # Reextrai se for Orizon
    if cliente == "orizon":
        from operacao.foto_ticket.orizon import extrair_dados_cliente_orizon
        novos_dados = extrair_dados_cliente_orizon(None, texto_ocr)
        dados_atuais.update(novos_dados)

    dados_atuais["nota_fiscal"] = nota_val
    conversas[numero]["dados"] = dados_atuais

    campos_obrigatorios = ["ticket", "peso_liquido", "nota_fiscal"]
    dados_faltando = [
        campo for campo in campos_obrigatorios
        if not dados_atuais.get(campo) or "NÃO ENCONTRADO" in str(dados_atuais.get(campo)).upper()
    ]

    if dados_faltando:
        enviar_mensagem(
            numero,
            "⚠️ Não consegui identificar todas as informações.\n"
            "Por favor, tire uma nova foto do ticket com mais nitidez e envie novamente."
        )
        conversas[numero]["estado"] = "aguardando_imagem"
        conversas[numero].pop("dados", None)
        try:
            os.remove("ticket.jpg")
        except FileNotFoundError:
            pass
        return {"status": "dados incompletos, aguardando nova imagem"}

    msg = (
        f"📋 Recebi os dados:\n"
        f"Cliente: {cliente.title()}\n"
        f"Ticket: {dados_atuais.get('ticket') or dados_atuais.get('brm_mes')}\n"
        f"Peso Líquido: {dados_atuais.get('peso_liquido')}\n"
        f"Nota Fiscal: {nota_val}\n\n"
        f"Está correto?"
    )
    conversas[numero]["estado"] = "aguardando_confirmacao"
    enviar_botoes_sim_nao(numero, msg)
    return {"status": "aguardando confirmação"}

def processar_confirmacao_final(numero):
    dados = conversas[numero]["dados"]

    payload = {
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cliente": conversas[numero].get("cliente", "").upper(),
        "ticket": dados.get("ticket"),
        "nota_fiscal": dados.get("nota_fiscal"),
        "peso": dados.get("peso_liquido"),
        "destino": dados.get("destino", "N/A"),
        "telefone": numero
    }
    # Envia os dados para a rota existente /enviar_dados
    try:
        requests.post("http://localhost:10000/enviar_dados", json=payload)
    except Exception as e:
        print(f"Erro ao enviar dados para /enviar_dados: {e}")

    nome_imagem = f"{payload['cliente']}/{payload['cliente']}_{payload['nota_fiscal']}.jpg"
    salvar_imagem_azure("ticket.jpg", nome_imagem)

    try:
        os.remove("ticket.jpg")
    except FileNotFoundError:
        pass

    enviar_mensagem(numero, "✅ Dados confirmados, Salvando as informações! Obrigado!")
    conversas.pop(numero)
