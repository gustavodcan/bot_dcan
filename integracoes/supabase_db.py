import os, psycopg2, logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("SUPABASE_DB_URL")

def conectar_db():
    """Tenta conectar direto no 5432. 
    Se der erro, tenta via pgbouncer (6543)."""
    try:
        logger.debug("[SUPABASE] Tentando conectar no Postgres (porta 5432)...")
        return psycopg2.connect(DATABASE_URL, connect_timeout=30)
    except Exception as e:
        logger.warning(f"[SUPABASE] Falha no 5432: {e}. Tentando pooling 6543...")
        # troca porta para 6543 (pgbouncer)
        if DATABASE_URL and ":5432" in DATABASE_URL:
            alt_url = DATABASE_URL.replace(":5432", ":6543")
            return psycopg2.connect(alt_url, connect_timeout=30)
        raise

def salvar_viagem(dados):
    try:
        conn = conectar_db()
        cur = conn.cursor()
        cur.execute("""
            insert into viagens (
                numero_viagem, data, telefone_motorista, motorista, placa, rota, remetente, status
            ) values (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            dados.get("numero_viagem"),
            dados.get("data"),
            dados.get("placa"),
            dados.get("telefone_motorista"),
            dados.get("motorista"),
            dados.get("rota"),
            dados.get("remetente"),
            dados.get("destinatario"),
            dados.get("emite_nf"),
            dados.get("status", "pendente"),
        ))
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"[SUPABASE] Viagem {dados.get('numero_viagem')} salva com sucesso.")
    except Exception:
        logger.error("[SUPABASE] Erro ao salvar viagem", exc_info=True)
