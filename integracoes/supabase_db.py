import os, psycopg2, logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("SUPABASE_DB_URL")

def conectar_db():
    return psycopg2.connect(DATABASE_URL)

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
            dados.get("telefone_motorista"),
            dados.get("motorista"),
            dados.get("placa"),
            dados.get("rota"),
            dados.get("remetente"),
            dados.get("status", "pendente"),
        ))
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"[SUPABASE] Viagem {dados.get('numero_viagem')} salva com sucesso.")
    except Exception:
        logger.error("[SUPABASE] Erro ao salvar viagem", exc_info=True)
