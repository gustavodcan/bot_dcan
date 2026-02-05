import os, re, requests, logging, base64
from datetime import datetime
from integracoes.a3soft.client import login_obter_token, enviar_ticket as a3_enviar_ticket
from integracoes.google_sheets import conectar_google_sheets, atualizar_viagem_ticket
from mensagens import enviar_mensagem, enviar_botoes_sim_nao, enviar_lista_viagens
from operacao.foto_ticket.defs import limpar_texto_ocr, detectar_cliente_por_texto
from operacao.foto_ticket.defs import extrair_dados_por_cliente
from integracoes.google_vision import preprocessar_imagem, ler_texto_google_ocr
from integracoes.azure import salvar_imagem_azure
from viagens import VIAGEM_POR_TELEFONE, get_viagens_por_telefone, set_viagem_ativa, carregar_viagens_ativas, VIAGENS, get_viagem_ativa
from viagens import VIAGEM_POR_NF, get_viagens_por_nf, set_viagem_ativa_nf, carregar_viagens_ativas_nf, VIAGENS_NF, get_viagem_ativa_nf
from integracoes.supabase_db import atualizar_viagem

logger = logging.getLogger(__name__)

def iniciar_fluxo_ticket(numero, conversas):
    # sempre recarrega as viagens da planilha, filtrando por "FALTA TICKET"
    VIAGENS.clear()
    VIAGENS.extend(carregar_viagens_ativas(status_filtro="FALTA TICKET"))
    viagens = get_viagens_por_telefone(numero)

    if not viagens:  # 🚨 Nenhuma viagem encontrada
        enviar_mensagem(
            numero,
            "⚠️ Não encontrei uma *viagem ativa* ou a *nota fiscal não foi enviada*. \n Por favor, fale com seu programador ou envie a nota fiscal no menu anterior.\n\n ⚠️ Conversa encerrada."
        )
        conversas.pop(numero, None)
        return {"status": "sem viagem"}

    if len(viagens) == 1:  # só tem uma opção, seleciona direto
        selecionada = viagens[0]
        conversas.setdefault(numero, {})["numero_viagem_selecionado"] = selecionada["numero_viagem"]
        set_viagem_ativa(numero, selecionada["numero_viagem"])
        enviar_mensagem(
            numero,
            f"🧭 Viagem selecionada: *{selecionada['numero_viagem']}* — {selecionada['nota_fiscal']} - {selecionada['data']} — {selecionada['placa']} · {selecionada['rota']}\n\n"
            "Agora, envie a *imagem do ticket*."
        )
        conversas[numero]["estado"] = "aguardando_imagem"
        conversas[numero]["nota_fiscal"] = selecionada["nota_fiscal"]
        return {"status": "aguardando imagem ticket"}

    # mais de uma opção → manda lista pro motorista
    conversas.setdefault(numero, {})["opcoes_viagem_ticket"] = viagens
    conversas[numero]["estado"] = "selecionando_viagem_ticket"
    enviar_lista_viagens(numero, viagens, "Escolha a viagem para enviar o *ticket*:")
    return {"status": "aguardando escolha viagem ticket"}

def iniciar_fluxo_ticket_terceiro(numero, nota_digitada, conversas):
    # sempre recarrega as viagens da planilha, filtrando por nota fiscal
    VIAGENS_NF.clear()
    VIAGENS_NF.extend(carregar_viagens_ativas_nf(nota_digitada))
    logger.info(f"[DEBUG] VIAGENS_NF total: {len(VIAGENS_NF)}")
    viagens = get_viagens_por_nf(nota_digitada)

    if not viagens:  # 🚨 Nenhuma viagem encontrada
        enviar_mensagem(
            numero,
            "⚠️ Não encontrei uma *viagem ativa* ou a *nota fiscal não foi enviada*. \n Por favor, fale com seu programador ou envie o número correto da nota fiscal.\n\n ⚠️ Conversa encerrada."
        )
        conversas.pop(numero, None)
        return {"status": "sem viagem"}

    if len(viagens) == 1:  # só tem uma opção, seleciona direto
        selecionada = viagens[0]
        conversas.setdefault(numero, {})["numero_viagem_selecionado"] = selecionada["numero_viagem"]
        set_viagem_ativa(numero, selecionada["numero_viagem"])
        enviar_mensagem(
            numero,
            f"🧭 Viagem selecionada: *{selecionada['numero_viagem']}* — {selecionada['data']} — {selecionada['placa']} · {selecionada['rota']}\n\n"
            "Agora, envie a *imagem do ticket*."
        )
        conversas[numero]["estado"] = "aguardando_imagem"
        return {"status": "aguardando imagem ticket"}

def tratar_estado_selecionando_viagem_ticket(numero, mensagem_original, conversas):
    viagens = conversas.get(numero, {}).get("opcoes_viagem_ticket", [])
    if not viagens:
        enviar_mensagem(numero, "❌ Não encontrei opções de viagem para este número. Fale com seu programador(a).")
        conversas.pop(numero, None)
        return {"status": "sem opções"}

    logger.debug(f"[DEBUG] selectedRowId recebido: {repr(mensagem_original)}")

    # Caso venha como "option0", "option1", etc.
    if mensagem_original.startswith("option"):
        try:
            indice = int(mensagem_original.replace("option", ""))
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
        numero_viagem = mensagem_original

    # Procura a viagem selecionada
    selecionada = next((v for v in viagens if str(v["numero_viagem"]) == str(numero_viagem)), None)

    if not selecionada:
        enviar_mensagem(numero, "❌ Opção inválida. Tente novamente.")
        return {"status": "seleção inválida"}

    conversas[numero]["numero_viagem_selecionado"] = selecionada["numero_viagem"]
    conversas[numero]["nota_fiscal"] = selecionada["nota_fiscal"]
    set_viagem_ativa(numero, selecionada["numero_viagem"])
    conversas[numero].pop("opcoes_viagem_ticket", None)

    enviar_mensagem(
        numero,
        f"🧭 Viagem selecionada: *{selecionada['numero_viagem']}* — {selecionada['data']} — {selecionada['placa']} · {selecionada['rota']}\n\n"
        "Agora, envie a *imagem do ticket*."
    )
    conversas[numero]["estado"] = "aguardando_imagem"
    return {"status": "viagem selecionada"}

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
        cliente = (conversas[numero].get("cliente") or "").upper()
        ticket  = dados_confirmados.get("ticket") or dados_confirmados.get("brm_mes") or ""
        peso    = dados_confirmados.get("peso_liquido") or ""
        origem  = dados_confirmados.get("destino") or dados_confirmados.get("origem") or "N/A"
        nota    = dados_confirmados.get("nota_fiscal") or ""

        # Resolve a viagem (selecionada ou ativa)
        numero_viagem = (
            conversas.get(numero, {}).get("numero_viagem_selecionado")
            or get_viagem_ativa(numero)
        )

        if not numero_viagem:
            enviar_mensagem(numero, "⚠️ Não encontrei uma *viagem ativa* vinculada ao seu número. Fale com seu programador(a).")
            conversas.pop(numero, None)
            try:
                os.remove("ticket.jpg")
            except FileNotFoundError:
                pass
            return {"status": "sem_viagem"}

        # Atualiza a viagem no Supabase (campos do ticket)
        try:
            atualizar_viagem(
                numero_viagem,
                {
                    "ticket": ticket,
                    "peso": peso,
                    "origem": origem,
                }
            )
            logger.info("[TICKET] Supabase ok (viagem %s).", numero_viagem)
        except Exception:
            logger.error("[TICKET] Falha ao atualizar viagem no Supabase.", exc_info=True)
            enviar_mensagem(numero, "❌ Erro ao salvar os dados. Contate o suporte.")
            conversas[numero]["estado"] = "finalizado"
            return {"status": "erro ao salvar"}

        # Somente Base64 no Supabase (sem upload para Azure)
        try:
            with open("ticket.jpg", "rb") as f:
                base64_str = base64.b64encode(f.read()).decode("utf-8")
            data_uri = base64_str
            try:
                atualizar_viagem(numero_viagem, {"foto_ticket": data_uri})
                logger.info("[TICKET] foto_ticket gravada no Supabase (viagem %s).", numero_viagem)
            except Exception:
                logger.error("[TICKET] Falha ao salvar foto_ticket (Base64) no Supabase.", exc_info=True)
            finally:
                try:
                    os.remove("ticket.jpg")
                except FileNotFoundError:
                    pass
        except Exception:
            logger.debug("⚠️ Erro ao ler/transformar ticket.jpg em Base64.", exc_info=True)

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

def tratar_estado_aguardando_nota_ticket(numero, texto_recebido, conversas):
    m = re.search(r"(\d{4,})\b", texto_recebido)
    nota_digitada = int(m.group(1)) if m else None
    if not nota_digitada:
        enviar_mensagem(numero, "❌ Por favor, envie apenas o número da nota.\n(Ex: *7878*).")
        return {"status": "nota inválida"}

    conversas[numero]["nota_fiscal"] = str(nota_digitada)
    iniciar_fluxo_ticket_terceiro(numero, nota_digitada, conversas)

def tratar_estado_aguardando_nota_manual(numero, texto_recebido, conversas):
    m = re.search(r"\b\d{4,}\b", texto_recebido)
    nota_digitada
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

def enviar_ticket_para_a3soft_no_confirm(numero: str, conversas: dict):
    # estrutura segura
    conv = conversas.setdefault(numero, {})
    dados = conv.setdefault("dados", {})
    nf_consulta = conv.get("nf_consulta", {}) or {}

    foto_nome   = "ticket.jpg"
    foto_base64 = (
        dados.get("ticket_img_b64")
        or conv.get("ticket_img_b64")
        or dados.get("foto_ticket")         # se você armazenar no mesmo dict
        or conv.get("foto_ticket")
    )

    # foto (opcional)
    foto_path  = dados.get("ticket_imagem_path") or conv.get("ticket_imagem_path")
    foto_nome  = dados.get("ticket_img_nome") or conv.get("ticket_img_nome")
    foto_base64= dados.get("ticket_img_b64")  or conv.get("ticket_img_b64")
    
    if not (foto_nome and foto_base64):
        enviar_mensagem(numero, "📸 A foto do ticket é obrigatória. Envie uma foto nítida do ticket de balança.")
        logger.error("[A3/TICKET] foto obrigatória ausente (nome/base64)")
        return {"ok": False, "error": "foto_obrigatoria_ausente"}

    # coleta segura dos campos
    numero_viagem = (
        conversas.get(numero, {}).get("numero_viagem_selecionado")
        or get_viagem_ativa(numero))
    
    numero_nota    = (dados.get("nota_fiscal"))

    ticket_balanca = (dados.get("ticket") or dados.get("brm_mes") or "")

    peso_val       = (dados.get("peso_liquido") or "")

    # validações/sanitizações
    if not numero_viagem:
        enviar_mensagem(numero, "⚠️ Não achei o *número da viagem* para enviar ao A3Soft.")
        logger.error("[A3/TICKET] numero_viagem ausente")
        return {"ok": False, "error": "numero_viagem_ausente"}

    if not numero_nota:
        enviar_mensagem(numero, "⚠️ Não achei o *número da nota* para enviar ao A3Soft.")
        logger.error("[A3/TICKET] numero_nota ausente")
        return {"ok": False, "error": "numero_nota_ausente"}

    if not ticket_balanca:
        enviar_mensagem(numero, "⚠️ Não achei o *número do ticket* da balança.")
        logger.error("[A3/TICKET] ticket_balanca ausente")
        return {"ok": False, "error": "ticket_ausente"}

    # normaliza peso (float)
    try:
        # remove tudo que não for dígito/ponto/vírgula e normaliza vírgula
        s = str(peso_val)
        s = re.sub(r"[^0-9,\.]", "", s).replace(",", ".")
        peso_float = float(s)
    except Exception:
        enviar_mensagem(numero, "⚠️ Peso inválido para enviar ao A3Soft.")
        logger.error(f"[A3/TICKET] peso inválido: {peso_val}")
        return {"ok": False, "error": "peso_invalido"}

    # login/token
    auth = login_obter_token()
    if not auth.get("ok") or not auth.get("token"):
        enviar_mensagem(numero, "⚠️ Não consegui autenticar no A3Soft para enviar o ticket.")
        logger.error(f"[A3/TICKET] auth falhou: {auth}")
        return {"ok": False, "error": "auth_falhou"}

    # call A3
    res = a3_enviar_ticket(
        token=auth["token"],
        numero_viagem=int(numero_viagem),
        numero_nota=str(numero_nota),
        ticket_balanca=str(ticket_balanca),
        peso=peso_float,
        valorMercadoria=1,
        quantidade=1,
        foto_nome=foto_nome,
        foto_base64=foto_base64
    )

    if res.get("ok"):
        enviar_mensagem(numero, "📤 Ticket enviado ao A3Soft com sucesso.")
        logger.info(f"[A3/TICKET] OK: {str(res.get('data'))[:500]}")
    else:
        enviar_mensagem(numero, "⚠️ Falha ao enviar o Ticket ao A3Soft.")
        logger.error(f"[A3/TICKET] ERRO: {res}")

    return res

def processar_confirmacao_final(numero, texto_recebido=None, conversas=None):
    if conversas is None or numero not in conversas:
        logger.warning("[TICKET] Conversa ausente para %s", numero)
        return {"status": "erro", "msg": "Conversa ausente"}

    dados = conversas[numero].get("dados", {})
    if not dados:
        enviar_mensagem(numero, "❌ Não encontrei os dados do ticket. Envie a *foto do ticket* novamente.")
        conversas[numero]["estado"] = "aguardando_imagem"
        return {"status": "sem dados"}

    resposta = (texto_recebido or "").strip().lower()

    #NÃO: pede reenvio da imagem e não salva nada
    if resposta in ("nao", "não", "n"):
        try:
            os.remove("ticket.jpg")
        except FileNotFoundError:
            pass

        # limpa os dados atuais e volta pro estado de imagem
        conversas[numero].pop("dados", None)
        conversas[numero]["estado"] = "aguardando_imagem"
        enviar_mensagem(numero, "🔁 Beleza! Por favor, envie a *foto do ticket* novamente.")
        return {"status": "reenvio_solicitado"}

    #SIM: grava no Sheets + Azure e finaliza
    if resposta in ("sim", "s"):
        viagens = get_viagens_por_telefone(numero)
        # Salva as opções e estado para seleção de ticket
        conversas[numero]["opcoes_viagem_ticket"] = viagens

        # Pega a viagem da seleção atual ou da ativa
        numero_viagem = (
            conversas.get(numero, {}).get("numero_viagem_selecionado")
            or get_viagem_ativa(numero)
        )

        if not numero_viagem:
            viagens = get_viagens_por_telefone(numero)
            if not viagens:
                enviar_mensagem(numero, "⚠️ Não encontrei uma *viagem ativa* vinculada ao seu número. Por favor, fale com seu programador.")
                logger.warning("[VIAGENS] Telefone %s sem viagem associada.", numero)
                conversas.pop(numero, None)
                try:
                    os.remove("ticket.jpg")
                except FileNotFoundError:
                    pass
                return {"status": "sem_viagem"}
        
        # Pega nota fiscal registrada na viagem
        viagens_tel = get_viagens_por_telefone(numero)
        viagem = next((v for v in viagens_tel if str(v.get("numero_viagem")) == str(numero_viagem)), None)

        # NF registrada no estado (quando o cara digitou)
        nf_esperada = conversas.get(numero, {}).get("nota_fiscal")  # string ou None
        # NF que veio do ticket/dados (se existir)
        nota_ticket = dados.get("nota_fiscal")  # pode ser string/int/None
        # usa a melhor disponível (estado > ticket)
        nf_para_buscar = nf_esperada or (str(nota_ticket).strip() if nota_ticket else None)

        if not viagem and nf_para_buscar:
            viagens_nf = get_viagens_por_nf(str(nf_para_buscar))
            viagem = next((v for v in viagens_nf if str(v.get("numero_viagem")) == str(numero_viagem)), None)

        # Debug detalhado
        logger.debug(f"[CHECK NF] Viagem esperava NF={nf_esperada}, Ticket trouxe NF={nota_ticket}")

        # Se a viagem estiver marcada como SEM NF, pula a validação e segue o fluxo normal
        nf_sem_nf = nf_esperada == "SEM NF"
        
        # Checagem: NF do ticket x NF da viagem
        if not nf_sem_nf and nota_ticket and nf_esperada != nota_ticket:
            enviar_mensagem(
                numero,
                f"❌ O ticket pertence à NF {nota_ticket}, a viagem pertence a NF {nf_esperada}. Envie a foto correta do ticket."
            )
            conversas[numero]["estado"] = "aguardando_imagem"
            try:
                os.remove("ticket.jpg")
            except FileNotFoundError:
                pass
            return {"status": "ticket nao corresponde"}

        cliente = (conversas[numero].get("cliente") or "").upper()
        ticket  = dados.get("ticket") or dados.get("brm_mes") or ""
        peso    = dados.get("peso_liquido") or ""
        origem  = dados.get("destino") or dados.get("origem") or "N/A"

        try:
            # Monta o payload básico
            payload = {
                "ticket": ticket,
                "peso": peso
            }

            conv   = conversas.setdefault(numero, {})
            dados  = conv.setdefault("dados", {})
            atualizar_viagem(numero_viagem, payload)
            logger.info("[TICKET] Payload completo atualizado no Supabase (viagem %s).", numero_viagem)
        except Exception:
            logger.error("[TICKET] Falha ao atualizar SupaBase da viagem.", exc_info=True)
            
        try:
            safe_viagem = re.sub(r"[^\w\-]", "_", numero_viagem) or "SEM_VIAGEM"
            safe_ticket = re.sub(r"[^\w\-]", "_", ticket) or "SEM_TICKET"
            caminho = f"VIAGENS/{safe_viagem}/TICKET_{safe_ticket}.jpg"
            salvar_imagem_azure("ticket.jpg", caminho)
            logger.info("[TICKET] Upload Azure ok em %s", caminho)
        except Exception:
            logger.error("[TICKET] Falha no upload para Azure.", exc_info=True)

        except Exception:
            logger.error("[TICKET] Falha ao enviar as informações ao Supabase.", exc_info=True)

        finally:
            try:
                os.remove("ticket.jpg")
            except FileNotFoundError:
                pass

        # 3) Limpa e finaliza
        try:
            os.remove("ticket.jpg")
        except FileNotFoundError:
            pass

#        enviar_ticket_para_a3soft_no_confirm(numero, conversas)
        enviar_mensagem(numero, f"✅ Dados confirmados. Ticket indexado na *viagem {numero_viagem}*. Obrigado!")
        conversas.pop(numero, None)
        return {"status": "finalizado"}

    #Resposta inválida: reenvia os botões
    enviar_botoes_sim_nao(numero, "❓ Por favor, confirme os dados do ticket: *Sim* ou *Não*?")
    return {"status": "aguardando_resposta_valida"}
