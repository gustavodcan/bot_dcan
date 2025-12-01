import os, logging
from supabase import create_client, Client
from datetime import datetime

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_DB_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def br_to_iso(data_str: str) -> str | None:
    #Converte 'dd/mm/aaaa' -> 'aaaa-mm-dd'.
    if not data_str:
        return None
    try:
#        return datetime.strptime(data_str, "%d/%m/%Y").date().isoformat()
        return datetime.strptime(data_str, "%Y/%m/%d").date().isoformat()
    except ValueError:
        raise ValueError(f"Data inválida: {data_str}")

def salvar_viagem(dados: dict):
    #Insere uma nova viagem no Supabase.
    try:
        res = supabase.table("viagens").insert({
            "numero_viagem": dados.get("numero_viagem"),
            "data": br_to_iso(dados.get("data")),
#            "data": dados.get("data"),
            "telefone_motorista": dados.get("telefone_motorista"),
            "motorista": dados.get("motorista"),
            "placa": dados.get("placa"),
            "rota": dados.get("rota"),
            "remetente": dados.get("remetente"),
            "destinatario": dados.get("destinatario")
#            "emite_nf": dados.get("emite_nf")
        }).execute()

        if res.data:
            logger.info(f"[SUPABASE] Viagem {dados.get('numero_viagem')} salva com sucesso.")
        else:
            logger.warning(f"[SUPABASE] Nenhum dado retornado ao salvar viagem {dados.get('numero_viagem')}.")

        return res
    except Exception:
        logger.error("[SUPABASE] Erro ao salvar viagem", exc_info=True)
        raise


def atualizar_viagem(numero_viagem: str, campos: dict):
    #Atualiza os campos de uma viagem existente (busca por numero_viagem).
    try:
        res = (
            supabase.table("viagens")
            .update(campos)
            .eq("numero_viagem", numero_viagem)
            .execute()
        )

        if res.data:
            logger.info(f"[SUPABASE] Viagem {numero_viagem} atualizada com sucesso.")
        else:
            logger.warning(f"[SUPABASE] Nenhuma linha atualizada para a viagem {numero_viagem}.")

        return res
    except Exception:
        logger.error(f"[SUPABASE] Erro ao atualizar viagem {numero_viagem}", exc_info=True)
        raise
