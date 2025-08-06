import os, re, requests, logging
from mensagens import enviar_mensagem, enviar_botoes_sim_nao
from integracoes.google_vision import preprocessar_imagem, ler_texto_google_ocr
from operacao.foto_ticket.defs import limpar_texto_ocr
from operacao.foto_nf.defs import extrair_chave_acesso
from datetime import datetime
from integracoes.infosimples import consultar_nfe_completa

logger = logging.getLogger(__name__)

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

def tratar_estado_aguardando_confirmacao_chave(numero, texto_recebido, conversas):
    if texto_recebido not in ['sim', 's']:
        enviar_mensagem(numero, "❌ Resposta inválida. Por favor, confirme a chave com *Sim* ou *Não*.")
        return {"status": "aguardando confirmação chave"}

    chave = conversas[numero].get("chave_detectada")
    if not chave:
        enviar_mensagem(numero, "❌ Chave não encontrada. Por favor, envie a nota novamente.")
        conversas[numero]["estado"] = "aguardando_imagem_nf"
        return {"status": "chave ausente"}

    enviar_mensagem(numero, "✅ Obrigado! A chave foi confirmada. Consultando a nota...")

    try:
        resultado = consultar_nfe_completa(chave)

        if not resultado or resultado.get("code") != 200:
            msg = f"❌ Erro ao consultar a nota.\n🔧 Motivo: {resultado.get('code_message', 'Desconhecido')}"
            if resultado.get("errors"):
                msg += "\n\n" + "\n".join(f"- {e}" for e in resultado["errors"])
            enviar_mensagem(numero, msg)
            conversas[numero]["estado"] = "finalizado"
            return {"status": "erro ao consultar NF-e"}

        dados_raw = resultado.get("data", {})
        dados = dados_raw[0] if isinstance(dados_raw, list) else dados_raw

        emitente = dados.get("emitente", {})
        emitente_nome = emitente.get("nome") or emitente.get("nome_fantasia") or "Não informado"
        emitente_cnpj = emitente.get("cnpj") or "Não informado"

        destinatario = dados.get("destinatario", {})
        destinatario_nome = destinatario.get("nome") or destinatario.get("nome_fantasia") or "Não informado"
        destinatario_cnpj = destinatario.get("cnpj") or "Não informado"

        nfe = dados.get("nfe", {})
        nfe_numero = nfe.get("numero") or "Não informado"
        nfe_emissao_raw = nfe.get("data_emissao") or ""
        try:
            dt = datetime.strptime(nfe_emissao_raw[:19], "%d/%m/%Y %H:%M:%S")
            nfe_emissao = dt.strftime("%d/%m/%Y")
        except Exception:
            nfe_emissao = "Não informado"

        transporte = dados.get("transporte", {})
        transporte_modalidade = transporte.get("modalidade_frete") or "Não informado"
        modalidade_numeros = ''.join(re.findall(r'\d+', transporte_modalidade))

        volumes = transporte.get("volumes", [])
        primeiro_volume = volumes[0] if isinstance(volumes, list) and volumes else {}
        peso_bruto = primeiro_volume.get("peso_bruto") or "Não informado"

        resposta = (
            f"✅ *Nota consultada com sucesso!*\n\n"
            f"*Emitente:* {emitente_nome}\n"
            f"*Emitente CNPJ:* {emitente_cnpj}\n"
            f"*Destinatário:* {destinatario_nome}\n"
            f"*Destinatário CNPJ:* {destinatario_cnpj}\n"
            f"*Número:* {nfe_numero}\n"
            f"*Emissão:* {nfe_emissao}\n"
            f"*Modalidade:* {modalidade_numeros}\n"
            f"*Peso Bruto:* {peso_bruto}"
        )

        enviar_mensagem(numero, resposta)
        conversas[numero]["estado"] = "finalizado"
        return {"status": "finalizado"}

    except Exception as e:
        enviar_mensagem(numero, f"❌ Erro inesperado ao processar a nota:\n{str(e)}")
        conversas[numero]["estado"] = "finalizado"
        return {"status": "erro inesperado"}

    finally:
        conversas[numero].pop("chave_detectada", None)
        conversas.pop(numero, None)
    return jsonify(status="finalizado")
