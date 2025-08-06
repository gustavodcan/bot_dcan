import re

def extrair_chave_acesso(texto):
    # Remove quebras de linha e normaliza texto
    texto = texto.replace("\n", " ")

    # Busca blocos de números com possível espaço entre eles
    matches = re.findall(r'((?:\d{4,6}\s*){10,})', texto)

    for bloco in matches:
        chave = re.sub(r'\D', '', bloco)  # Remove tudo que não for número
        if len(chave) == 44:
            return chave

    return None  # Se nenhuma chave válida encontrada

    if chave:
        print(f"🔑 Chave de acesso encontrada: {chave}")
    else:
        print("❌ Chave de acesso não encontrada.")
