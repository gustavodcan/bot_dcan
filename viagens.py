import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from integracoes.supabase_db import supabase  # usa o client já criado no módulo do supa

logger = logging.getLogger(__name__)

#Converte data americana para brasileira
def iso_to_br(data_iso: Optional[str]) -> str:
    if not data_iso:
        return ""
    try:
        #Suporta '2025-08-26'(date) e '2025-08-26T00:00:00Z'(timestamp)
        if "T" in data_iso:
            dt = datetime.fromisoformat(data_iso.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y")
        return datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        logger.debug(f"[DATA] Formato inesperado vindo do DB: {data_iso}")
        return str(data_iso)

#Consulta viagens no Supabase conforme StatusFiltro
def carregar_viagens_ativas(status_filtro: Optional=str) -> List[Dict[str, Any]]:
    try:
        query = (
            supabase
            .table("viagens")
            .select(
                "numero_viagem, data, placa, telefone_motorista, motorista, rota, "
                "remetente, destinatario, nota_fiscal, status"
            )
        )

        if status_filtro:
            query = query.eq("status", str(status_filtro).upper())
        else:
            query = query.neq("status", "OK")

        res = query.execute()
        rows = res.data or []

        viagens_ativas: List[Dict[str, Any]] = []
        for row in rows:
            viagens_ativas.append({
                "numero_viagem": str(row.get("numero_viagem") or "").strip(),
                "data": iso_to_br(row.get("data")),
                "placa": str(row.get("placa") or "").strip(),
                "telefone_motorista": str(row.get("telefone_motorista") or "").strip(),
                "motorista": str(row.get("motorista") or "").strip(),
                "rota": str(row.get("rota") or "").strip(),
                "remetente": str(row.get("remetente") or "").strip(),
                "nota_fiscal": str(row.get("nota_fiscal") or "").strip(),
                "destinatario": str(row.get("destinatario") or "").strip(),
                "status": str(row.get("status") or "").strip().upper(),
            })

        return viagens_ativas

    except Exception as e:
        logger.error(f"[SUPABASE] Erro ao carregar viagens: {e}", exc_info=True)
        return []

#Cache em memória
VIAGENS: List[Dict[str, Any]] = []
VIAGEM_POR_TELEFONE: Dict[str, str] = {}  #Telefone e Número da viagem
VIAGEM_ATIVA_POR_TELEFONE: Dict[str, str] = {}

#Atualiza os caches em memória com base no resultado do DB.
def refresh_viagens_cache(status_filtro: Optional[str] = None) -> None:
    global VIAGENS, VIAGEM_POR_TELEFONE
    VIAGENS = carregar_viagens_ativas(status_filtro=status_filtro)
    VIAGEM_POR_TELEFONE = {v.get("telefone_motorista", ""): v.get("numero_viagem", "") for v in VIAGENS}

def get_viagens_por_telefone(telefone: str) -> List[Dict[str, Any]]:
    return [v for v in VIAGENS if v.get("telefone_motorista") == telefone]

def set_viagem_ativa(telefone: str, numero_viagem: str):
    VIAGEM_ATIVA_POR_TELEFONE[telefone] = numero_viagem

def get_viagem_ativa(telefone: str) -> Optional[str]:
    return VIAGEM_ATIVA_POR_TELEFONE.get(telefone)

################################################################################################################################

#Consulta viagens no Supabase conforme NF_Filtro
def carregar_viagens_ativas_nf(nf_filtro: Optional[str] = None):

    try:
        query = (
            supabase
            .table("viagens")
            .select(
                "numero_viagem, data, placa, telefone_motorista, motorista, rota, "
                "remetente, destinatario, nota_fiscal, status"
            )
        )

        query = query.eq("nota_fiscal", int(nf_filtro))

        res = query.execute()
        rows = res.data or []

        viagens_ativas_nf: List[Dict[str, Any]] = []
        for row in rows:
            viagens_ativas_nf.append({
                "numero_viagem": str(row.get("numero_viagem") or "").strip(),
                "data": iso_to_br(row.get("data")),
                "placa": str(row.get("placa") or "").strip(),
                "telefone_motorista": str(row.get("telefone_motorista") or "").strip(),
                "motorista": str(row.get("motorista") or "").strip(),
                "rota": str(row.get("rota") or "").strip(),
                "remetente": str(row.get("remetente") or "").strip(),
                "nota_fiscal": str(row.get("nota_fiscal") or "").strip(),
                "destinatario": str(row.get("destinatario") or "").strip(),
                "status": str(row.get("status") or "").strip().upper(),
            })

        return viagens_ativas_nf

    logger.info(f"[DEBUG] nf_filtro recebido: {nf_filtro} ({type(nf_filtro)})")

    except Exception as e:
        logger.error(f"[SUPABASE] Erro ao carregar viagens: {e}", exc_info=True)
        return []

#Cache em memória
VIAGENS_NF: List[Dict[str, Any]] = []
VIAGEM_POR_NF: Dict[str, str] = {}  #Telefone e Número da viagem
VIAGEM_ATIVA_POR_NF: Dict[str, str] = {}

def get_viagens_por_nf(nota_fiscal: str) -> List[Dict[str, Any]]:
    return [v for v in VIAGENS_NF if v.get("nota_fiscal") == nota_fiscal]

def set_viagem_ativa_nf(nota_fiscal: str, numero_viagem: str):
    VIAGEM_ATIVA_POR_NF[nota_fiscal] = numero_viagem

def get_viagem_ativa_nf(nota_fiscal: str) -> Optional[str]:
    return VIAGEM_ATIVA_POR_NF.get(nota_fiscal)
