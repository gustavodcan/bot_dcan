import os, re, logging, requests, pdfplumber, cv2, zxingcpp
from datetime import datetime
from mensagens import enviar_mensagem, enviar_botoes_sim_nao, enviar_lista_viagens, enviar_botao_encerrarconversa
from integracoes.google_vision import preprocessar_imagem, ler_texto_google_ocr
from operacao.foto_ticket.defs import limpar_texto_ocr
from operacao.foto_nf.defs import extrair_chave_acesso
import xml.etree.ElementTree as ET
import numpy as np
from integracoes.a3soft.client import login_obter_token, receber_xml, enviar_nf
from viagens import get_viagens_por_telefone, set_viagem_ativa, get_viagem_ativa, carregar_viagens_ativas, VIAGENS
from integracoes.supabase_db import atualizar_viagem

logger = logging.getLogger(__name__)

def iniciar_fluxo_nf(numero, conversas):
    VIAGENS.clear()
    VIAGENS.extend(carregar_viagens_ativas(status_filtro="FALTA NOTA"))
    viagens = get_viagens_por_telefone(numero)

    if not viagens:
        enviar_mensagem(
            numero,
            "⚠️ Não encontrei uma *viagem ativa* vinculada ao seu número. Por favor, fale com seu programador."
        )
        conversas.pop(numero, None)
        return {"status": "sem viagem"}

    if len(viagens) == 1:
        selecionada = viagens[0]
        conversas.setdefault(numero, {})["numero_viagem_selecionado"] = selecionada["numero_viagem"]
        set_viagem_ativa(numero, selecionada["numero_viagem"])
        enviar_mensagem(
            numero,
            f"🧭 Viagem selecionada: *{selecionada['numero_viagem']}* — {selecionada['remetente']} — {selecionada['data']} — {selecionada['placa']} · {selecionada['rota']}\n\n"
            "Agora, envie a *imagem da nota fiscal*."
        )
        conversas[numero]["estado"] = "aguardando_imagem_nf"
        return {"status": "aguardando imagem nf"}

    conversas.setdefault(numero, {})["opcoes_viagem_nf"] = viagens
    conversas[numero]["estado"] = "selecionando_viagem_nf"
    enviar_lista_viagens(numero, viagens, "Escolha uma das viagens abaixo para continuar o envio da NF.")
    return {"status": "aguardando escolha viagem nf"}


def tratar_estado_selecionando_viagem_nf(numero, row_id_recebido, conversas, texto_recebido):
    if texto_recebido == "encerrar_conversa":
        enviar_mensagem(numero, "❌ Conversa Encerrada.\n" "⚠️ Para continuar, envie uma nova mensagem para iniciar novamente.")
        conversas.pop(numero, None)
        return {"status": "finalizado"}
        
    viagens = conversas.get(numero, {}).get("opcoes_viagem_nf", [])
    if not viagens:
        enviar_mensagem(numero, "❌ Não encontrei opções de viagem para este número. Fale com seu programador(a).")
        conversas.pop(numero, None)
        return {"status": "sem opções"}

    logger.debug(f"[DEBUG] selectedRowId recebido: {repr(row_id_recebido)}")

    # Caso venha como "option0", "option1", etc.
    if row_id_recebido.startswith("option"):
        try:
            indice = int(row_id_recebido.replace("option", ""))
            if 0 <= indice < len(viagens):
                numero_viagem = viagens[indice]["numero_viagem"]
                logger.debug(f"[DEBUG] Viagem selecionada pelo índice: {numero_viagem}")
            else:
                enviar_botao_encerrarconversa(numero, "❌ Selecione uma viagem da lista, ou cancele a conversa abaixo para reiniciar")
                conversas[numero]["estado"] = "selecionando_viagem_nf"
                return {"status": "seleção inválida"}
        except ValueError:
            enviar_mensagem(numero, "❌ Erro ao interpretar opção.")
            return {"status": "erro"}
    else:
        # Caso já venha direto como numero_viagem
        numero_viagem = row_id_recebido

    # Procura a viagem selecionada
    selecionada = next((v for v in viagens if str(v["numero_viagem"]) == str(numero_viagem)), None)

    if not selecionada:
        enviar_botao_encerrarconversa(numero, "❌ Selecione uma viagem da lista, ou cancele a conversa abaixo para reiniciar")
        conversas[numero]["estado"] = "selecionando_viagem_nf"
        return {"status": "seleção inválida"}

    conversas[numero]["numero_viagem_selecionado"] = selecionada["numero_viagem"]
    set_viagem_ativa(numero, selecionada["numero_viagem"])
    conversas[numero].pop("opcoes_viagem_nf", None)

    enviar_mensagem(
        numero,
        f"🧭 Viagem selecionada: *{selecionada['numero_viagem']}* — {selecionada['data']} — {selecionada['placa']} · {selecionada['rota']}\n\n"
        "Agora, envie a *imagem da nota fiscal*."
    )
    conversas[numero]["estado"] = "aguardando_imagem_nf"
    return {"status": "viagem selecionada"}

def tratar_estado_aguardando_imagem_nf(numero, data, conversas, texto_recebido):
    url_arquivo = None
    mime_type = None
    nome_arquivo = None

    if texto_recebido == "encerrar_conversa":
        enviar_mensagem(numero, "❌ Conversa Encerrada.\n" "⚠️ Para continuar, envie uma nova mensagem para iniciar novamente.")
        conversas.pop(numero, None)
        return {"status": "finalizado"}
    
    if "image" in data:
        mime_type = data["image"].get("mimeType", "")
        url_arquivo = data["image"].get("imageUrl")
        nome_arquivo = "nota.jpg"
    elif "document" in data:
        mime_type = data["document"].get("mimeType", "")
        url_arquivo = data["document"].get("documentUrl")
        nome_arquivo = "nota.pdf"

    logger.debug(f"[NF] Recebido arquivo — MIME: {mime_type}, URL: {url_arquivo}, Nome: {nome_arquivo}")

    if not mime_type or (not mime_type.startswith("image/") and mime_type != "application/pdf"):
        enviar_botao_encerrarconversa(numero, "📎 Envie uma *imagem* ou *PDF* da nota fiscal. Ou cancele a conversa abaixo para reiniciar")
        return {"status": "aguardando imagem nf"}

    # Baixa arquivo
    try:
        res = requests.get(url_arquivo, timeout=20)
        if res.status_code != 200:
            enviar_mensagem(numero, "❌ Erro ao baixar o arquivo da nota. Tente novamente.")
            logger.error(f"[NF] Falha ao baixar arquivo ({res.status_code}) — URL: {url_arquivo}")
            return {"status": "erro ao baixar"}
        with open(nome_arquivo, "wb") as f:
            f.write(res.content)
        logger.debug(f"[NF] Arquivo salvo localmente: {nome_arquivo}, tamanho: {len(res.content)} bytes")
    except Exception:
        logger.error("[NF] Falha ao baixar arquivo", exc_info=True)
        enviar_mensagem(numero, "❌ Erro ao baixar o arquivo da nota. Tente novamente.")
        return {"status": "erro ao baixar"}

    ## Tenta ler código de barras ##
    texto = ""

#    if mime_type.startswith("image/"):
#        try:
#            barcode_txt = ler_texto_codigo_barras_imagem("nota.jpg")
#            if barcode_txt:
#                logger.debug(f"[NF] ✅ Texto do código de barras encontrado: {barcode_txt}")
#                texto = barcode_txt  # <-- isso garante o "teleporte" pro checkpoint
#            else:
#                logger.debug("[NF] Barcode não encontrado na imagem, seguindo para OCR.")
#        except Exception:
#            logger.error("[NF] Erro ao tentar ler código de barras (OpenCV)", exc_info=True)
            
    if not texto:
        if mime_type.startswith("image/"):
            logger.debug("[NF] Arquivo é imagem, rodando OCR com pré-processamento")
            img = preprocessar_imagem("nota.jpg")
            img.save("nota_pre_google.jpg")
            texto = ler_texto_google_ocr("nota_pre_google.jpg")

        elif mime_type == "application/pdf":
            logger.debug("[NF] Arquivo é PDF, tentando primeiro com Google OCR")
            texto = ler_texto_google_ocr("nota.pdf")

            if not texto.strip():
                logger.debug("[NF] Google OCR não retornou nada, tentando pdfplumber")
                try:
                    with pdfplumber.open("nota.pdf") as pdf:
                        texto_paginas = [page.extract_text() or "" for page in pdf.pages]
                        texto = "\n".join(texto_paginas)
                except Exception:
                    logger.error("[NF] Falha ao extrair texto com pdfplumber", exc_info=True)
    
    # Limpa texto
    texto = limpar_texto_ocr(texto)
    conversas[numero]["ocr_texto_nf"] = texto

    # Extrai chave
    chave = extrair_chave_acesso(texto)
    logger.debug(f"[NF] Resultado extração chave: {chave}")

    if not chave:
        enviar_mensagem(numero, "❌ Não consegui identificar a *chave de acesso* na nota. Por favor, envie novamente.")
        conversas[numero]["estado"] = "aguardando_imagem_nf"
        return {"status": "chave não encontrada"}

    logger.info(f"[NF] Chave encontrada com sucesso: {chave}")

    from integracoes.nsdocs.client import buscar_ou_consultar_e_buscar

    enviar_mensagem(numero, "🔎 Consultando dados da NF no NSDocs...")

    # sanitize chave
    import re
    chave = re.sub(r"\D", "", chave or "")
    if len(chave) != 44:
        enviar_mensagem(numero, "❌ Chave de acesso inválida (precisa de 44 dígitos).")
        conversas[numero]["estado"] = "aguardando_imagem_nf"
        return {"status": "chave inválida"}

    resp = buscar_ou_consultar_e_buscar(chave)
    if not resp.get("ok"):
        logger.error(f"[NSDOCS] Falha na consulta: {resp}")
        enviar_mensagem(numero, "⚠️ Não consegui consultar a NF agora. Por favor, tente novamente em instantes")
        return {"status": "erro_nsdocs", "detalhe": resp}

    lista = resp.get("data", [])
    if not lista:
        enviar_mensagem(numero, "⚠️ Não foram encontrados dados para essa chave. Confirme a imagem ou tente novamente.")
        conversas[numero]["estado"] = "aguardando_imagem_nf"
        return {"status": "nf_nao_encontrada"}

    # NSDocs retorna lista; usa o primeiro item
    item = lista[0] or {}
    emitente_nome = item.get("emitente_nome") or "Não informado"
    emitente_cnpj = item.get("emitente_cnpj") or "Não informado"
    destinatario_nome = item.get("destinatario_nome") or "Não informado"
    destinatario_cnpj = item.get("destinatario_cnpj") or "Não informado"
    numero_nf = str(item.get("numero") or "")
    data_emissao = item.get("data_emissao") or "Não informado"
    peso = item.get("peso")

    # guarda e segue o fluxo
    conversas[numero]["estado"] = "aguardando_confirmacao_dados_nf"
    conversas[numero]["nf_consulta"] = {
        "chave": chave,
        "emitente_nome": emitente_nome,
        "emitente_cnpj": emitente_cnpj,
        "destinatario_nome": destinatario_nome,
        "destinatario_cnpj": destinatario_cnpj,
        "numero": numero_nf,
        "emissao": data_emissao,
        "peso_bruto": peso,
    }

    msg = (
        "✅ *Nota encontrada! Confira os dados:*\n\n"
        f"*Emitente:* {emitente_nome}\n"
        f"*CNPJ Emitente:* {emitente_cnpj}\n"
        f"*Destinatário:* {destinatario_nome}\n"
        f"*CNPJ Destinatário:* {destinatario_cnpj}\n"
        f"*Número:* {numero_nf}\n"
        f"*Emissão:* {data_emissao}\n"
        f"*Peso Bruto:* {peso}\n\n"
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
            atualizar_viagem(
                numero_viagem,
                {
                    "chave_acesso": dados.get("chave") or "",
                    "nota_fiscal": dados.get("numero") or ""
                }
            )
        else:
            logger.warning(
                "[NF] Sem viagem selecionada/ativa na confirmação de NF para %s",
                numero
            )

        enviar_mensagem(numero, "✅ Perfeito! Dados confirmados. Obrigado! 🙌")
        conversas.pop(numero, None)
        # limpeza de arquivos
        return {"status": "finalizado"}

    # resposta inválida
    enviar_botoes_sim_nao(numero, "❓ Por favor, clique em *Sim* ou *Não* para confirmar os dados da nota.")
    return {"status": "aguardando resposta válida dados nf"}

##############################################################################################################################################################

                                               #ACRESCER NOTAS FISCAIS EM VIAGENS QUE JA POSSUEM NF#

##############################################################################################################################################################

def iniciar_fluxo_acrescer_nf(numero, conversas):
    VIAGENS.clear()
    VIAGENS.extend(carregar_viagens_ativas(status_filtro="FALTA TICKET"))
    viagens = get_viagens_por_telefone(numero)

    if not viagens:
        enviar_mensagem(
            numero,
            "⚠️ Não encontrei uma *viagem ativa* vinculada ao seu número. Por favor, fale com seu programador."
        )
        conversas.pop(numero, None)
        return {"status": "sem viagem"}

    if len(viagens) == 1:
        selecionada = viagens[0]
        conversas.setdefault(numero, {})["numero_viagem_selecionado"] = selecionada["numero_viagem"]
        set_viagem_ativa(numero, selecionada["numero_viagem"])
        enviar_mensagem(
            numero,
            f"🧭 Viagem selecionada: *{selecionada['numero_viagem']}* — {selecionada['remetente']} — {selecionada['data']} — {selecionada['placa']} · {selecionada['rota']}\n\n"
            "Agora, envie a *imagem da nota fiscal*."
        )
        conversas[numero]["estado"] = "aguardando_imagem_acrescer_nf"
        return {"status": "aguardando imagem nf"}

    conversas.setdefault(numero, {})["opcoes_viagem_acrescer_nf"] = viagens
    conversas[numero]["estado"] = "selecionando_viagem_acrescer_nf"
    enviar_lista_viagens(numero, viagens, "Escolha uma das viagens abaixo para continuar o envio da NF.")
    return {"status": "aguardando escolha viagem nf"}


def tratar_estado_selecionando_viagem_acrescer_nf(numero, row_id_recebido, conversas, texto_recebido):
    if texto_recebido == "encerrar_conversa":
        enviar_mensagem(numero, "❌ Conversa Encerrada.\n" "⚠️ Para continuar, envie uma nova mensagem para iniciar novamente.")
        conversas.pop(numero, None)
        return {"status": "finalizado"}
        
    viagens = conversas.get(numero, {}).get("opcoes_viagem_acrescer_nf", [])
    if not viagens:
        enviar_mensagem(numero, "❌ Não encontrei opções de viagem para este número. Fale com seu programador(a).")
        conversas.pop(numero, None)
        return {"status": "sem opções"}

    logger.debug(f"[DEBUG] selectedRowId recebido: {repr(row_id_recebido)}")

    # Caso venha como "option0", "option1", etc.
    if row_id_recebido.startswith("option"):
        try:
            indice = int(row_id_recebido.replace("option", ""))
            if 0 <= indice < len(viagens):
                numero_viagem = viagens[indice]["numero_viagem"]
                logger.debug(f"[DEBUG] Viagem selecionada pelo índice: {numero_viagem}")
            else:
                enviar_botao_encerrarconversa(numero, "❌ Selecione uma viagem da lista, ou cancele a conversa abaixo para reiniciar")
                conversas[numero]["estado"] = "selecionando_viagem_acrescer_nf"
                return {"status": "seleção inválida"}
        except ValueError:
            enviar_mensagem(numero, "❌ Erro ao interpretar opção.")
            return {"status": "erro"}
    else:
        # Caso já venha direto como numero_viagem
        numero_viagem = row_id_recebido

    # Procura a viagem selecionada
    selecionada = next((v for v in viagens if str(v["numero_viagem"]) == str(numero_viagem)), None)

    if not selecionada:
        enviar_botao_encerrarconversa(numero, "❌ Selecione uma viagem da lista, ou cancele a conversa abaixo para reiniciar")
        conversas[numero]["estado"] = "selecionando_viagem_acrescer_nf"
        return {"status": "seleção inválida"}

    conversas[numero]["numero_viagem_selecionado"] = selecionada["numero_viagem"]
    set_viagem_ativa(numero, selecionada["numero_viagem"])
    conversas[numero].pop("opcoes_viagem_acrescer_nf", None)

    enviar_mensagem(
        numero,
        f"🧭 Viagem selecionada: *{selecionada['numero_viagem']}* — {selecionada['data']} — {selecionada['placa']} · {selecionada['rota']}\n\n"
        "Agora, envie a *imagem da nota fiscal*."
    )
    conversas[numero]["estado"] = "aguardando_imagem_acrescer_nf"
    return {"status": "viagem selecionada"}

def tratar_estado_aguardando_imagem_acrescer_nf(numero, data, conversas, texto_recebido):
    url_arquivo = None
    mime_type = None
    nome_arquivo = None

    if texto_recebido == "encerrar_conversa":
        enviar_mensagem(numero, "❌ Conversa Encerrada.\n" "⚠️ Para continuar, envie uma nova mensagem para iniciar novamente.")
        conversas.pop(numero, None)
        return {"status": "finalizado"}
    
    if "image" in data:
        mime_type = data["image"].get("mimeType", "")
        url_arquivo = data["image"].get("imageUrl")
        nome_arquivo = "nota.jpg"
    elif "document" in data:
        mime_type = data["document"].get("mimeType", "")
        url_arquivo = data["document"].get("documentUrl")
        nome_arquivo = "nota.pdf"

    logger.debug(f"[NF] Recebido arquivo — MIME: {mime_type}, URL: {url_arquivo}, Nome: {nome_arquivo}")

    if not mime_type or (not mime_type.startswith("image/") and mime_type != "application/pdf"):
        enviar_botao_encerrarconversa(numero, "📎 Envie uma *imagem* ou *PDF* da nota fiscal. Ou cancele a conversa abaixo para reiniciar")
        return {"status": "aguardando imagem nf"}

    # Baixa arquivo
    try:
        res = requests.get(url_arquivo, timeout=20)
        if res.status_code != 200:
            enviar_mensagem(numero, "❌ Erro ao baixar o arquivo da nota. Tente novamente.")
            logger.error(f"[NF] Falha ao baixar arquivo ({res.status_code}) — URL: {url_arquivo}")
            return {"status": "erro ao baixar"}
        with open(nome_arquivo, "wb") as f:
            f.write(res.content)
        logger.debug(f"[NF] Arquivo salvo localmente: {nome_arquivo}, tamanho: {len(res.content)} bytes")
    except Exception:
        logger.error("[NF] Falha ao baixar arquivo", exc_info=True)
        enviar_mensagem(numero, "❌ Erro ao baixar o arquivo da nota. Tente novamente.")
        return {"status": "erro ao baixar"}
        
    texto = ""

    #Verificando se imagem ou NF
    if not texto:
        if mime_type.startswith("image/"):
            logger.debug("[NF] Arquivo é imagem, rodando OCR com pré-processamento")
            img = preprocessar_imagem("nota.jpg")
            img.save("nota_pre_google.jpg")
            texto = ler_texto_google_ocr("nota_pre_google.jpg")

        elif mime_type == "application/pdf":
            logger.debug("[NF] Arquivo é PDF, tentando primeiro com Google OCR")
            texto = ler_texto_google_ocr("nota.pdf")

            if not texto.strip():
                logger.debug("[NF] Google OCR não retornou nada, tentando pdfplumber")
                try:
                    with pdfplumber.open("nota.pdf") as pdf:
                        texto_paginas = [page.extract_text() or "" for page in pdf.pages]
                        texto = "\n".join(texto_paginas)
                except Exception:
                    logger.error("[NF] Falha ao extrair texto com pdfplumber", exc_info=True)
    
    # Limpa texto
    texto = limpar_texto_ocr(texto)
    conversas[numero]["ocr_texto_nf"] = texto

    # Extrai chave
    chave = extrair_chave_acesso(texto)
    logger.debug(f"[NF] Resultado extração chave: {chave}")

    if not chave:
        enviar_mensagem(numero, "❌ Não consegui identificar a *chave de acesso* na nota. Por favor, envie novamente.")
        conversas[numero]["estado"] = "aguardando_imagem_acrescer_nf"
        return {"status": "chave não encontrada"}

    logger.info(f"[NF] Chave encontrada com sucesso: {chave}")

    from integracoes.nsdocs.client import buscar_ou_consultar_e_buscar

    enviar_mensagem(numero, "🔎 Consultando dados da NF no NSDocs...")

    # sanitize chave
    import re
    chave = re.sub(r"\D", "", chave or "")
    if len(chave) != 44:
        enviar_mensagem(numero, "❌ Chave de acesso inválida (precisa de 44 dígitos).")
        conversas[numero]["estado"] = "aguardando_imagem_acrescer_nf"
        return {"status": "chave inválida"}

    resp = buscar_ou_consultar_e_buscar(chave)
    if not resp.get("ok"):
        logger.error(f"[NSDOCS] Falha na consulta: {resp}")
        enviar_mensagem(numero, "⚠️ Não consegui consultar a NF agora. Por favor, tente novamente em instantes")
        return {"status": "erro_nsdocs", "detalhe": resp}

    lista = resp.get("data", [])
    if not lista:
        enviar_mensagem(numero, "⚠️ Não foram encontrados dados para essa chave. Confirme a imagem ou tente novamente.")
        conversas[numero]["estado"] = "aguardando_imagem_acrescer_nf"
        return {"status": "nf_nao_encontrada"}

    # NSDocs retorna lista; usa o primeiro item
    item = lista[0] or {}
    emitente_nome = item.get("emitente_nome") or "Não informado"
    emitente_cnpj = item.get("emitente_cnpj") or "Não informado"
    destinatario_nome = item.get("destinatario_nome") or "Não informado"
    destinatario_cnpj = item.get("destinatario_cnpj") or "Não informado"
    numero_nf = str(item.get("numero") or "")
    data_emissao = item.get("data_emissao") or "Não informado"
    peso = item.get("peso")

    # guarda e segue o fluxo
    conversas[numero]["estado"] = "aguardando_confirmacao_dados_acrescer_nf"
    conversas[numero]["nf_consulta"] = {
        "chave": chave,
        "emitente_nome": emitente_nome,
        "emitente_cnpj": emitente_cnpj,
        "destinatario_nome": destinatario_nome,
        "destinatario_cnpj": destinatario_cnpj,
        "numero": numero_nf,
        "emissao": data_emissao,
        "peso_bruto": peso,
    }

    msg = (
        "✅ *Nota encontrada! Confira os dados:*\n\n"
        f"*Emitente:* {emitente_nome}\n"
        f"*CNPJ Emitente:* {emitente_cnpj}\n"
        f"*Destinatário:* {destinatario_nome}\n"
        f"*CNPJ Destinatário:* {destinatario_cnpj}\n"
        f"*Número:* {numero_nf}\n"
        f"*Emissão:* {data_emissao}\n"
        f"*Peso Bruto:* {peso}\n\n"
        "Está tudo correto?"
    )
    enviar_botoes_sim_nao(numero, msg)
    return {"status": "aguardando confirmação dados nf"}

def _append_unico(campo_atual: str, novo_valor: str):
    campo_atual = (campo_atual or "").strip()
    novo_valor = (str(novo_valor).strip() if novo_valor else "")

    if not novo_valor:
        return campo_atual, False

    itens = [x.strip() for x in campo_atual.split(",") if x.strip()]

    if novo_valor in itens:
        return campo_atual, True

    itens.append(novo_valor)
    return ",".join(itens), False

def tratar_estado_confirmacao_dados_acrescer_nf(numero, texto_recebido, conversas):
    texto = (texto_recebido or "").strip().lower()

    # dados extraídos da NF (do teu OCR/consulta)
    dados_nf = conversas.get(numero, {}).get("nf_consulta", {}) or {}

    # aqui eu assumo que tua viagem selecionada foi guardada antes
    # AJUSTA esse nome se o teu fluxo salva em outra chave
    selecionada = conversas.get(numero, {}).get("viagem_selecionada")

    if texto in ["não", "nao", "n"]:
        enviar_mensagem(numero, "🔁 Sem problemas! Por favor, envie a *imagem da nota* novamente.")
        conversas.setdefault(numero, {})["estado"] = "aguardando_imagem_acrescer_nf"
        conversas[numero].pop("nf_consulta", None)

        # limpeza de arquivos (não explode se não existir)
        for arq in ["nota.jpg", "nota_pre_google.jpg"]:
            try:
                os.remove(arq)
            except Exception:
                pass

        return {"status": "requisitado reenviar nf"}

    if texto in ["sim", "s"]:
        # pega numero_viagem de algum lugar confiável
        numero_viagem = (
            conversas.get(numero, {}).get("numero_viagem_selecionado")
            or get_viagem_ativa(numero)
        )

        if not numero_viagem:
            logger.warning("[NF] Sem viagem selecionada/ativa na confirmação de NF para %s", numero)
            enviar_mensagem(numero, "⚠️ Tô sem a viagem ativa aqui. Refaça a seleção da viagem, por favor.")
            return {"status": "sem viagem ativa"}

        # se tiver selecionada, atualiza estado de viagem ativa e cache
        #if selecionada and selecionada.get("numero_viagem"):
        #    conversas.setdefault(numero, {})["numero_viagem_selecionado"] = selecionada["numero_viagem"]
        #    set_viagem_ativa(numero, selecionada["numero_viagem"])

        # Se selecionada veio como string (ex: "100"), transforma em dict buscando no banco
        if isinstance(selecionada, str):
            try:
                num_viagem = int(selecionada.strip())
            except ValueError:
                num_viagem = None

            if num_viagem:
                selecionada = buscar_viagem_por_numero(num_viagem)  # você implementa/usa sua função
            else:
                selecionada = None

        # valores novos vindos da NF atual
        nova_chave = dados_nf.get("chave") or ""
        nova_nf = dados_nf.get("numero") or ""

        # valores atuais (preferência: vem da selecionada; senão considera vazio)
        chave_atual = selecionada("chave_acesso") if selecionada else ""
        nf_atual = selecionada("nota_fiscal") if selecionada else ""

        # faz append com verificação de duplicidade
        chave_final, chave_dup = _append_unico(chave_atual, nova_chave)
        nf_final, nf_dup = _append_unico(nf_atual, nova_nf)

        logger.debug(f"[NF] Chave Supa: {chave_atual} Chave Nova: {nova_chave}")
        logger.debug(f"[NF] Num NF Supa: {nf_atual} Num NF Nova: {nova_nf}")

        # se a NF já existe, avisa e não grava
        # (tu pode decidir se quer checar chave também; aqui o principal é NF)
        if nf_dup:
            enviar_mensagem(numero, f"A nota *{nova_nf}* já foi lançada nessa viagem. Por favor, tente novamente.")
            conversas.pop(numero, None)
            return {"status": "nf duplicada"}

        # grava no banco
        atualizar_viagem(
            numero_viagem,
            {
                "chave_acesso": chave_final,
                "nota_fiscal": nf_final,
            },
        )

        enviar_mensagem(numero, "✅ Fechou! Acrescentei a nota nessa viagem. Obrigado! 🙌")
        conversas.pop(numero, None)

        for arq in ["nota.jpg", "nota_pre_google.jpg"]:
            try:
                os.remove(arq)
            except Exception:
                pass

        return {"status": "finalizado"}

    # resposta inválida
    enviar_botoes_sim_nao(numero, "❓ Por favor, clique em *Sim* ou *Não* para confirmar os dados da nota.")
    return {"status": "aguardando resposta válida dados nf"}
