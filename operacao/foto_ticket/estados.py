import os
import re
import requests
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

