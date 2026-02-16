import os, re, logging, requests, pdfplumber, cv2, zxingcpp
from datetime import datetime
from mensagens import enviar_mensagem, enviar_botoes_sim_nao, enviar_lista_viagens
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


def tratar_estado_selecionando_viagem_nf(numero, row_id_recebido, conversas):
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

def _read_code128(img) -> str | None:
    try:
        res = zxingcpp.read_barcodes(img, formats=[zxingcpp.BarcodeFormat.Code128])
    except TypeError:
        res = zxingcpp.read_barcodes(img)

    if not res:
        return None

    for r in res:
        txt = (r.text or "").strip()
        if txt:
            return txt
    return None

def _variants(bgr):
    out = [bgr]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    out.append(gray)

    # melhora contraste
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    eq = clahe.apply(gray)
    out.append(eq)

    # binarização
    thr = cv2.adaptiveThreshold(eq, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 31, 2)
    out.append(thr)
    out.append(cv2.bitwise_not(thr))

    # alguns bindings preferem BGR
    out.append(cv2.cvtColor(eq, cv2.COLOR_GRAY2BGR))
    out.append(cv2.cvtColor(thr, cv2.COLOR_GRAY2BGR))
    return out

def _rotations(img):
    return [
        img,
        cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE),
        cv2.rotate(img, cv2.ROTATE_180),
        cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE),
    ]

def _try_decode_full(img) -> str | None:
    # tenta em variantes e rotações
    for v in _variants(img):
        for r in _rotations(v):
            txt = _read_code128(r)
            if txt:
                return txt
    return None

def _looks_like_barcode_only(img) -> bool:
    """
    Heurística simples: imagem com muitas linhas verticais finas (padrão barcode)
    e pouca complexidade textual.
    Não é ciência exata, mas ajuda a evitar crop quando já veio recortado.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 60, 180)

    h, w = edges.shape[:2]
    # conta "densidade" de bordas
    edge_density = edges.mean() / 255.0  # 0..1

    # projeta bordas na horizontal: barcode tende a ter muitas bordas em colunas
    col_sum = edges.sum(axis=0) / 255.0
    # se muitas colunas têm borda, é forte indicador de barcode
    cols_with_edges = np.mean(col_sum > (0.08 * h))  # % colunas com bastante borda

    # ajuste conservador pra não dar falso positivo demais
    return (edge_density > 0.03 and cols_with_edges > 0.35)

def ler_texto_codigo_barras_imagem(caminho_imagem: str, logger=None) -> str | None:
    img = cv2.imread(caminho_imagem)
    if img is None:
        return None

    # Upscale geral
    h, w = img.shape[:2]
    if max(h, w) < 2000:
        img = cv2.resize(img, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

    if logger:
        hh, ww = img.shape[:2]
        logger.debug(f"[NF] Barcode scan adaptativo: {ww}x{hh}")

    # 1) tenta imagem inteira
    txt = _try_decode_full(img)
    if txt:
        return txt

    # 2) se parece que já veio recortada (barcode-only), NÃO faz crop agressivo
    if _looks_like_barcode_only(img):
        if logger:
            logger.debug("[NF] Imagem parece ser recorte de barcode; evitando crop por grid.")
        return None  # não achou nem full, então não inventa crop que pode piorar

    # 3) fallback: grid crops com overlap (sem assumir posição)
    H, W = img.shape[:2]

    # tamanhos de janela (percentuais do doc)
    window_scales = [
        (0.55, 0.35),  # janela "larga"
        (0.70, 0.45),  # maior
        (0.40, 0.30),  # menor
    ]

    # overlap (passo menor = mais tentativas, mais lento)
    step_factor = 0.35

    for ws, hs in window_scales:
        win_w = int(W * ws)
        win_h = int(H * hs)
        if win_w < 300 or win_h < 200:
            continue

        step_x = max(50, int(win_w * step_factor))
        step_y = max(50, int(win_h * step_factor))

        for y in range(0, H - win_h + 1, step_y):
            for x in range(0, W - win_w + 1, step_x):
                crop = img[y:y+win_h, x:x+win_w]

                # upscale extra no crop
                ch, cw = crop.shape[:2]
                crop2 = cv2.resize(crop, (cw * 2, ch * 2), interpolation=cv2.INTER_CUBIC)

                txt = _try_decode_full(crop2)
                if txt:
                    if logger:
                        logger.debug(f"[NF] ✅ Barcode encontrado em grid crop x={x},y={y},w={win_w},h={win_h}")
                    return txt

    return None

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

    ## Tenta ler código de barras ##
    texto = ""

    if mime_type.startswith("image/"):
        try:
            barcode_txt = ler_texto_codigo_barras_imagem("nota.jpg")
            if barcode_txt:
                logger.debug(f"[NF] ✅ Texto do código de barras encontrado: {barcode_txt}")
                texto = barcode_txt  # <-- isso garante o "teleporte" pro checkpoint
            else:
                logger.debug("[NF] Barcode não encontrado na imagem, seguindo para OCR.")
        except Exception:
            logger.error("[NF] Erro ao tentar ler código de barras (OpenCV)", exc_info=True)
            
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
