import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from supabase_db import supabase  # usa o client já criado no módulo do supa

logger = logging.getLogger(__name__)

# ------------ Helpers de data ------------
def iso_to_br(data_iso: Optional[str]) -> str:
    """
    Converte 'aaaa-mm-dd' -> 'dd/mm/aaaa' para exibição no app.
    """
    if not data_iso:
        return ""
    try:
        # suporta tanto '2025-08-26' (date) quanto '2025-08-26T00:00:00Z' (timestamp)
        if "T" in data_iso:
            dt = datetime.fromisoformat(data_iso.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y")
        return datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        logger.debug(f"[DATA] Formato inesperado vindo do DB: {data_iso}")
        return str(data_iso)

# ------------ Consulta principal ------------
def carregar_viagens_ativas(status_filtro: Optional=str) -> List[Dict[str, Any]]:
    """
    Busca viagens ativas no Supabase.
    - Se 'status_filtro' vier, filtra exatamente por esse status (case-insensitive).
    - Se não vier, retorna todas com status != 'OK'.
    Campos retornados seguem o shape antigo para minimizar mudanças no app.
    """
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
                "data": iso_to_br(row.get("data")),  # app usa dd/mm/aaaa
                "placa": str(row.get("placa") or "").strip(),
                "telefone_motorista": str(row.get("telefone_motorista") or "").strip(),
                "motorista": str(row.get("motorista") or "").strip(),
                "rota": str(row.get("rota") or "").strip(),
                "remetente": str(row.get("remetente") or "").strip(),
                # mantido por compatibilidade com o código existente
                "nota_fiscal": str(row.get("nota_fiscal") or "").strip(),
                # extra, caso queira consumir
                "destinatario": str(row.get("destinatario") or "").strip(),
                "status": str(row.get("status") or "").strip().upper(),
            })

        return viagens_ativas

    except Exception as e:
        logger.error(f"[SUPABASE] Erro ao carregar viagens: {e}", exc_info=True)
        return []

# ------------ Cache em memória (compat) ------------
VIAGENS: List[Dict[str, Any]] = []
VIAGEM_POR_TELEFONE: Dict[str, str] = {}  # telefone -> número da viagem
VIAGEM_ATIVA_POR_TELEFONE: Dict[str, str] = {}

def refresh_viagens_cache(status_filtro: Optional[str] = None) -> None:
    """
    Atualiza os caches em memória com base no resultado do DB.
    """
    global VIAGENS, VIAGEM_POR_TELEFONE
    VIAGENS = carregar_viagens_ativas(status_filtro=status_filtro)
    VIAGEM_POR_TELEFONE = {v.get("telefone_motorista", ""): v.get("numero_viagem", "") for v in VIAGENS}

def get_viagens_por_telefone(telefone: str) -> List[Dict[str, Any]]:
    return [v for v in VIAGENS if v.get("telefone_motorista") == telefone]

def set_viagem_ativa(telefone: str, numero_viagem: str):
    VIAGEM_ATIVA_POR_TELEFONE[telefone] = numero_viagem

def get_viagem_ativa(telefone: str) -> Optional[str]:
    return VIAGEM_ATIVA_POR_TELEFONE.get(telefone)
