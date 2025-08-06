import os
import requests
from mensagens import enviar_mensagem, enviar_botoes_sim_nao
from integracoes.google_vision import preprocessar_imagem, ler_texto_google_ocr
from operacao.foto_ticket.defs import limpar_texto_ocr
from operacao.foto_nf.defs import extrair_chave_acesso

def tratar_estado_aguardando_imagem_nf(numero, data, conversas):
    if "image" not in data or not data["image"].get("mimeType", "").startswith("image/"):
        enviar_mensagem(numero, "📸 Por favor, envie uma imagem da nota fiscal.")
        return {"status": "aguardando imagem nf"}

    url_img = data["image"]["imageUrl"]
    try:
        img_res = requests.get(url_img)
        if img_res.status_code == 200:
            with open("nota.jpg", "wb") as f:
                f.write(img_res.content)
        else:
            enviar_mensagem(numero, "❌ Erro ao baixar a imagem da nota. Tente novamente.")
            return {"status": "erro ao baixar"}
    except Exception:
        enviar_mensagem(numero, "❌ Erro ao baixar a imagem da nota. Tente novamente.")
        return {"status": "erro ao baixar"}

    img = preprocessar_imagem("nota.jpg")
    img.save("nota_pre_google.jpg")
    texto = ler_texto_google_ocr("nota_pre_google.jpg")
    texto = limpar_texto_ocr(texto)

    conversas[numero]["ocr_texto"] = texto
    chave = extrair_chave_acesso(texto)

    if chave:
        conversas[numero]["chave_detectada"] = chave
        conversas[numero]["estado"] = "aguardando_confirmacao_chave"
        mensagem = (
            f"🔎 Encontrei a seguinte *chave de acesso* na nota:\n\n"
            f"{chave}\n\n"
            f"✅ Por favor, *confirme se está correta* antes de continuar."
        )
        enviar_botoes_sim_nao(numero, mensagem)
        return {"status": "chave extraída e aguardando confirmação"}
    else:
        enviar_mensagem(numero, "❌ Não consegui identificar a chave de acesso na nota. Por favor, envie novamente.")
        conversas[numero]["estado"] = "aguardando_imagem_nf"
        return {"status": "chave não encontrada"}
