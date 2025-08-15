import os

# Liga/desliga aviso automático ao subir (Render)
NOTIFICAR_VIAGENS_ON_START = os.getenv("NOTIFICAR_VIAGENS_ON_START", "1") == "1"

# Base de viagens
VIAGENS = [
    {"numero_viagem": "1006", "data": "14/08/2025", "placa": "FZL9I99", "telefone_motorista": "5511912538457", "motorista": "Desenvolvimento Dcan", "rota": "PIRACICABA-SPXIRACEMÁPOLIS-SP", "remetente": "SUPERLAMINAÇÃO"},
    {"numero_viagem": "1008", "data": "14/08/2025", "placa": "FZL9I99", "telefone_motorista": "5511912538457", "motorista": "Desenvolvimento Dcan", "rota": "EMBU DAS ARTES-SPXPINDAMONHANGABA-SP", "remetente": "SUPERLAMINAÇÃO"},
    {"numero_viagem": "1010", "data": "14/08/2025", "placa": "FZL9I99", "telefone_motorista": "5511912538457", "motorista": "Desenvolvimento Dcan", "rota": "SANTANA DE PARNAÍBA-SPXARAÇARIGUAMA-SP", "remetente": "SUPERLAMINAÇÃO"},
    {"numero_viagem": "1009", "data": "14/08/2025", "placa": "ALL4N99", "telefone_motorista": "5511969098799", "motorista": "Allo Allan Fallando", "rota": "Valorant x CS2", "remetente": "SUPERLAMINAÇÃO"},
]

# Mapa rápido: telefone -> número da viagem
VIAGEM_POR_TELEFONE = {v["telefone_motorista"]: v["numero_viagem"] for v in VIAGENS}

def get_viagens_por_telefone(telefone: str):
    return [v for v in VIAGENS if v.get("telefone_motorista") == telefone]

VIAGEM_ATIVA_POR_TELEFONE = {}

def set_viagem_ativa(telefone: str, numero_viagem: str):
    VIAGEM_ATIVA_POR_TELEFONE[telefone] = numero_viagem

def get_viagem_ativa(telefone: str):
    return VIAGEM_ATIVA_POR_TELEFONE.get(telefone)
