import re, os, logging
from mensagens import enviar_mensagem, enviar_botoes_sim_nao

logger = logging.getLogger(__name__)

def extrair_dados_cliente_saae(img, texto):
    logger.debug("📜 [PROACTIVA] Texto detectado:")
    logger.debug(texto)

    ticket_match = re.search(r"(?m)^(?:.*?:\s*)?(\d{5}/\d{4})\s*$", texto)
    ticket_val = ticket_match.group(1).replace("/", "") if ticket_match else "NÃO ENCONTRADO"

    outros_docs = re.search(r"outros[\s_]*docs[.:;\-]*[:]?[\s]*([0-9]{4,})", texto)

    peso_liquido = re.search(
        r"peso[\s_]*l[iíoe]qu[iíoe]d(?:o|ouido|uido|oudo)?[\s_]*(?:kg)?[:：]{1,2}\s*([0-9]{4,6})",
        texto
    )

    # 🧠 Log de debug pro Render ou local
    logger.debug("🎯 Dados extraídos:")
    logger.debug(f"Ticket: {ticket_val}")
    logger.debug(f"Outros Docs: {outros_docs.group(1) if outros_docs else 'Não encontrado'}")
    logger.debug(f"Peso Líquido: {peso_liquido.group(1) if peso_liquido else 'Não encontrado'}")

    return {
        "ticket": ticket_val,
        "nota_fiscal": ticket_val,
        "outros_docs": outros_docs.group(1) if outros_docs else "NÃO ENCONTRADO",
        "peso_liquido": peso_liquido.group(1) if peso_liquido else "NÃO ENCONTRADO"
    }
    
def tratar_estado_aguardando_destino_saae(numero, texto_recebido, conversas):
    destino_digitado = texto_recebido.strip().title()

    if len(destino_digitado) < 2:
        enviar_mensagem(numero, "❌ Por favor, informe um destino válido.")
        return {"status": "destino inválido"}

    conversas[numero]["destino"] = destino_digitado

    try:
        texto_ocr = conversas[numero].get("ocr_texto", "")
        dados = extrair_dados_cliente_saae(None, texto_ocr)
    except Exception as e:
        enviar_mensagem(numero, f"❌ Erro ao extrair os dados do ticket.\nTente novamente.\nErro: {e}")
        conversas[numero]["estado"] = "aguardando_imagem"
        return {"status": "erro extração saae"}

    dados["destino"] = destino_digitado
    conversas[numero]["dados"] = dados
    conversas[numero]["estado"] = "aguardando_confirmacao"

    campos_obrigatorios = ["ticket", "peso_liquido", "destino"]
    dados_faltando = [campo for campo in campos_obrigatorios if not dados.get(campo) or "NÃO ENCONTRADO" in str(dados.get(campo)).upper()]

    if dados_faltando:
        enviar_mensagem(
            numero,
            f"⚠️ Não consegui identificar as seguintes informações: {', '.join(dados_faltando)}.\n"
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
        f"Cliente: PROACTIVA\n"
        f"Ticket: {dados.get('ticket')}\n"
        f"Peso Líquido: {dados.get('peso_liquido')}\n"
        f"Origem: {destino_digitado}\n\n"
        f"Está correto?"
    )
    conversas[numero]["estado"] = "aguardando_confirmacao"
    enviar_botoes_sim_nao(numero, msg)
    return {"status": "aguardando confirmação"}
