import os, re, logging, requests, pdfplumber
from datetime import datetime
from mensagens import enviar_mensagem, enviar_botoes_sim_nao, enviar_lista_viagens
from integracoes.google_vision import preprocessar_imagem, ler_texto_google_ocr
from operacao.foto_ticket.defs import limpar_texto_ocr
from operacao.foto_nf.defs import extrair_chave_acesso
from integracoes.infosimples import consultar_nfe_completa
from viagens import get_viagens_por_telefone, set_viagem_ativa, get_viagem_ativa, carregar_viagens_ativas, VIAGENS
#from integracoes.google_sheets import atualizar_viagem_nf
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
            f"🧭 Viagem selecionada: *{selecionada['numero_viagem']}* — {selecionada['data']} — {selecionada['placa']} · {selecionada['rota']}\n\n"
            "Agora, envie a *imagem da nota fiscal*."
        )
        conversas[numero]["estado"] = "aguardando_imagem_nf"
        return {"status": "aguardando imagem nf"}

    conversas.setdefault(numero, {})["opcoes_viagem_nf"] = viagens
    conversas[numero]["estado"] = "selecionando_viagem_nf"
    enviar_lista_viagens(numero, viagens, "Escolha uma das viagens abaixo para continuar o envio da NF.")
    return {"status": "aguardando escolha viagem nf"}


def tratar_estado_selecionando_viagem_nf(numero, row_id_recebido, conversas):
    viagens = conversas.get(numero, {}).get("opcoes_viagem_nf", [])
    if not viagens:
        enviar_mensagem(numero, "❌ Não encontrei opções de viagem para este número. Fale com o despacho.")
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
                enviar_mensagem(numero, "❌ Opção inválida. Selecione novamente.")
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
        enviar_mensagem(numero, "❌ Opção inválida. Tente novamente.")
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

def extrair_texto_pdf(caminho_pdf):
    """Extrai texto nativo de PDFs usando pdfplumber."""
    texto = ""
    try:
        with pdfplumber.open(caminho_pdf) as pdf:
            for page in pdf.pages:
                texto += page.extract_text() or ""
    except Exception as e:
        logger.error(f"[PDF] Falha ao extrair texto direto: {e}")
    return texto.strip()

def tratar_estado_aguardando_imagem_nf(numero, data, conversas):
    url_arquivo = None
    mime_type = None
    nome_arquivo = None

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
        enviar_mensagem(numero, "📎 Envie uma *imagem* ou um *PDF* da nota fiscal.")
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
#                logger.debug(f"[NF] Texto extraído com pdfplumber: {repr(texto)[:500]}...")
            except Exception:
                logger.error("[NF] Falha ao extrair texto com pdfplumber", exc_info=True)

    # Log OCR bruto
#    logger.debug(f"[NF] OCR bruto/extraído: {repr(texto)[:500]}...")

    # Limpa texto
    texto = limpar_texto_ocr(texto)
    conversas[numero]["ocr_texto_nf"] = texto
#    logger.debug(f"[NF] Texto após limpeza: {repr(texto)[:500]}...")

    # Extrai chave
    chave = extrair_chave_acesso(texto)
    logger.debug(f"[NF] Resultado extração chave: {chave}")

    if not chave:
        enviar_mensagem(numero, "❌ Não consegui identificar a *chave de acesso* na nota. Por favor, envie novamente.")
        conversas[numero]["estado"] = "aguardando_imagem_nf"
        return {"status": "chave não encontrada"}

    logger.info(f"[NF] Chave encontrada com sucesso: {chave}")
    
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
        # ... (limpeza de arquivos)
        return {"status": "finalizado"}

    # resposta inválida
    enviar_botoes_sim_nao(numero, "❓ Por favor, clique em *Sim* ou *Não* para confirmar os dados da nota.")
    return {"status": "aguardando resposta válida dados nf"}
