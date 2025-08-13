import os
import re
import logging
from datetime import datetime

import requests
from mensagens import enviar_mensagem, enviar_botoes_sim_nao, enviar_lista_viagens
from integracoes.google_vision import preprocessar_imagem, ler_texto_google_ocr
from operacao.foto_ticket.defs import limpar_texto_ocr
from operacao.foto_nf.defs import extrair_chave_acesso
from integracoes.infosimples import consultar_nfe_completa
from viagens import get_viagens_por_telefone, set_viagem_ativa, get_viagem_ativa
from integracoes.google_sheets import atualizar_viagem_nf

logger = logging.getLogger(__name__)

def iniciar_fluxo_nf(numero, conversas, mensagem_original=None):
    viagens = get_viagens_por_telefone(numero)

    if not viagens:
        enviar_mensagem(
            numero,
            "⚠️ Não encontrei uma *viagem ativa* vinculada ao seu número. Por favor, fale com o despacho."
        )
        conversas.pop(numero, None)
        return {"status": "sem viagem"}

    if len(viagens) == 1:
        v = viagens[0]
        conversas.setdefault(numero, {})["numero_viagem_selecionado"] = v["numero_viagem"]
        set_viagem_ativa(numero, v["numero_viagem"])
        enviar_mensagem(
            numero,
            f"🧭 Viagem selecionada: *{v['numero_viagem']}* — {v['placa']} · {v['rota']}\n\n"
            "Agora, envie a *imagem da nota fiscal*."
        )
        conversas[numero]["estado"] = "aguardando_imagem_nf"
        return {"status": "aguardando imagem nf"}

    conversas.setdefault(numero, {})["opcoes_viagem_nf"] = viagens
    conversas[numero]["estado"] = "selecionando_viagem_nf"
    enviar_lista_viagens(numero, viagens, "❌ Seleção inválida, por favor selecione novamente!")
    logger.warning("Viagem da lista:", mensagem_original)
    return {"status": "aguardando escolha viagem nf"}

def tratar_estado_selecionando_viagem_nf(numero, mensagem_original, conversas):
    viagens = conversas.get(numero, {}).get("opcoes_viagem_nf", [])
    if not viagens:
        enviar_mensagem(numero, "❌ Não encontrei opções de viagem para este número. Fale com seu programador.")
        conversas.pop(numero, None)
        return {"status": "sem opções"}

    row_id = (mensagem_original).strip()
    if not row_id:
        logger.warning("Viagem da lista:", mensagem_original)
        enviar_lista_viagens(numero, viagens, "❓ Toque em uma das opções da lista para selecionar a viagem.")
        return {"status": "aguardando seleção (list)"}

    numero_viagem = row_id

#    selecionada = next((v for v in viagens if str(v["numero_viagem"]) == str(numero_viagem)), None)
    selecionada = row_id
#    if not selecionada:
#        logger.warning("Viagem da lista:", mensagem_original)
#        enviar_lista_viagens(numero, viagens, "Opção inválida. Tente novamente.")
#        return {"status": "seleção inválida (list)"}

    conversas[numero]["numero_viagem_selecionado"] = selecionada["numero_viagem"]
    set_viagem_ativa(numero, selecionada["numero_viagem"])
    conversas[numero].pop("opcoes_viagem_nf", None)

    enviar_mensagem(
        numero,
        f"🧭 Viagem selecionada: *{selecionada['numero_viagem']}* — {selecionada['placa']} · {selecionada['rota']}\n\n"
        "Agora, envie a *imagem da nota fiscal*."
    )
    conversas[numero]["estado"] = "aguardando_imagem_nf"
    return {"status": "viagem selecionada"}


def tratar_estado_aguardando_imagem_nf(numero, data, conversas):
    # valida imagem
    if "image" not in data or not data["image"].get("mimeType", "").startswith("image/"):
        enviar_mensagem(numero, "📸 Envie uma *imagem* da nota fiscal.")
        return {"status": "aguardando imagem nf"}

    numero_viagem = (
        conversas.get(numero, {}).get("numero_viagem_selecionado")
        or get_viagem_ativa(numero)
    )
    
    if not numero_viagem:
        enviar_mensagem(
            numero,
            "⚠️ Não encontrei uma *viagem ativa* vinculada ao seu número. Por favor, fale com seu programador."
        )
        conversas.pop(numero, None)
        return {"status": "sem viagem (nf bloqueada)"}
    
    # baixa imagem
    url_img = data["image"]["imageUrl"]
    try:
        res = requests.get(url_img, timeout=20)
        if res.status_code != 200:
            enviar_mensagem(numero, "❌ Erro ao baixar a imagem da nota. Tente novamente.")
            return {"status": "erro ao baixar"}
        with open("nota.jpg", "wb") as f:
            f.write(res.content)
    except Exception as e:
        logger.error("Falha ao baixar imagem da NF", exc_info=True)
        enviar_mensagem(numero, "❌ Erro ao baixar a imagem da nota. Tente novamente.")
        return {"status": "erro ao baixar"}

    # OCR
    img = preprocessar_imagem("nota.jpg")
    img.save("nota_pre_google.jpg")
    texto = ler_texto_google_ocr("nota_pre_google.jpg")
    texto = limpar_texto_ocr(texto)
    conversas[numero]["ocr_texto_nf"] = texto

    # extrai chave
    chave = extrair_chave_acesso(texto)
    if not chave:
        enviar_mensagem(numero, "❌ Não consegui identificar a *chave de acesso* na nota. Por favor, envie novamente.")
        conversas[numero]["estado"] = "aguardando_imagem_nf"
        return {"status": "chave não encontrada"}

    # consulta direta na InfoSimples (sem confirmar chave antes)
    enviar_mensagem(numero, "🔎 Localizando as informações da nota, um instante…")
    try:
        resultado = consultar_nfe_completa(chave)
    except Exception:
        logger.error("Erro inesperado consultando InfoSimples", exc_info=True)
        enviar_mensagem(numero, "❌ Ocorreu um erro ao consultar a nota. Envie a imagem novamente.")
        conversas[numero]["estado"] = "aguardando_imagem_nf"
        return {"status": "erro consulta"}

    if not resultado or resultado.get("code") != 200:
        msg = resultado.get("code_message", "Erro ao consultar a nota.")
        enviar_mensagem(numero, f"❌ {msg}\nPor favor, envie a imagem novamente.")
        conversas[numero]["estado"] = "aguardando_imagem_nf"
        return {"status": "consulta falhou"}

    # normaliza dados
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
    modalidade = transporte.get("modalidade_frete") or "Não informado"
    modalidade_num = "".join(re.findall(r"\d+", modalidade)) if modalidade else "Não informado"

    volumes = transporte.get("volumes", [])
    primeiro_volume = volumes[0] if isinstance(volumes, list) and volumes else {}
    peso_bruto = primeiro_volume.get("peso_bruto") or "Não informado"

    # guarda para possível reuso
    conversas[numero]["estado"] = "aguardando_confirmacao_dados_nf"
    conversas[numero]["nf_consulta"] = {
        "chave": chave,
        "emitente_nome": emitente_nome,
        "emitente_cnpj": emitente_cnpj,
        "destinatario_nome": destinatario_nome,
        "destinatario_cnpj": destinatario_cnpj,
        "numero": nfe_numero,
        "emissao": nfe_emissao,
        "modalidade": modalidade_num,
        "peso_bruto": peso_bruto,
    }

    # envia resumo para confirmação
    msg = (
        "✅ *Nota encontrada! Confira os dados:*\n\n"
        f"*Emitente:* {emitente_nome}\n"
        f"*CNPJ Emitente:* {emitente_cnpj}\n"
        f"*Destinatário:* {destinatario_nome}\n"
        f"*CNPJ Destinatário:* {destinatario_cnpj}\n"
        f"*Número:* {nfe_numero}\n"
        f"*Emissão:* {nfe_emissao}\n"
        f"*Modalidade Frete:* {modalidade_num}\n"
        f"*Peso Bruto:* {peso_bruto}\n\n"
        "Está tudo correto?"
    )
    enviar_botoes_sim_nao(numero, msg)
    return {"status": "aguardando confirmação dados nf"}
    
def tratar_estado_confirmacao_dados_nf(numero, texto_recebido, conversas):
    dados = conversas[numero].get("nf_consulta", {})

    # se respondeu NÃO: volta para enviar imagem
    if texto_recebido.lower() in ["não", "nao", "n"]:
        enviar_mensagem(numero, "🔁 Sem problemas! Por favor, envie a *imagem da nota* novamente.")
        conversas[numero]["estado"] = "aguardando_imagem_nf"
        # limpa dados anteriores
        conversas[numero].pop("nf_consulta", None)
        try:
            os.remove("nota.jpg")
            os.remove("nota_pre_google.jpg")
        except Exception:
            pass
        return {"status": "requisitado reenviar nf"}

    # se respondeu SIM: finaliza
    if texto_recebido.lower() in ["sim", "s"]:
        numero_viagem = (
            conversas.get(numero, {}).get("numero_viagem_selecionado")
            or get_viagem_ativa(numero)
        )

        if numero_viagem:
            atualizar_viagem_nf(
                numero_viagem=numero_viagem,
                telefone=numero,
                chave_acesso=dados.get("chave") or "",
                nota_fiscal=dados.get("numero") or ""
            )
        else:
            logger.warning("[NF] Sem viagem selecionada/ativa na confirmação de NF para %s", numero)

        enviar_mensagem(numero, "✅ Perfeito! Dados confirmados. Obrigado! 🙌")
        conversas.pop(numero, None)
        # ... (limpeza de arquivos)
        return {"status": "finalizado"}

    # resposta inválida
    enviar_botoes_sim_nao(numero, "❓ Por favor, clique em *Sim* ou *Não* para confirmar os dados da nota.")
    return {"status": "aguardando resposta válida dados nf"}
