import os

# Liga/desliga aviso automático ao subir (Render)
NOTIFICAR_VIAGENS_ON_START = os.getenv("NOTIFICAR_VIAGENS_ON_START", "1") == "1"

# Base de viagens
VIAGENS = [
    {"numero_viagem": "1006","placa": "FZL9I99", "telefone_motorista": "5511912538457", "motorista": "Desenvolvimento Dcan", "rota": "Pindamonhangaba x Tremembé", "remetente": "SUPERLAMINAÇÃO"},
    {"numero_viagem": "1007","placa": "FZL9I99", "telefone_motorista": "5511912538457", "motorista": "Desenvolvimento Dcan", "rota": "Pindamonhangaba x Tremembé", "remetente": "SUPERLAMINAÇÃO"},
    {"numero_viagem": "1008","placa": "FZL9I99", "telefone_motorista": "5511912538457", "motorista": "Desenvolvimento Dcan", "rota": "Pindamonhangaba x Tremembé", "remetente": "SUPERLAMINAÇÃO"},
]

# Mapa rápido: telefone -> número da viagem
VIAGEM_POR_TELEFONE = {v["telefone_motorista"]: v["numero_viagem"] for v in VIAGENS}

def get_viagem_por_telefone(telefone: str):
    """Retorna dict da viagem pelo telefone (ou None)."""
    for v in VIAGENS:
        if v["telefone_motorista"] == telefone:
            return v
    return None
