import os, base64, requests, json, logging
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from config import CERTIFICADO_BASE64, CERTIFICADO_SENHA, CHAVE_AES, INFOSIMPLES_TOKEN

logger = logging.getLogger(__name__)

def aes_encrypt_urlsafe(texto, chave):
    key = chave.encode('utf-8')
    key = key.ljust(32, b'\0')[:32]
    cipher = AES.new(key, AES.MODE_ECB)
    texto_padded = pad(texto.encode('utf-8'), AES.block_size)
    encrypted = cipher.encrypt(texto_padded)
    b64 = base64.b64encode(encrypted).decode()
    return b64.replace('+', '-').replace('/', '_').rstrip('=')

def salvar_certificado_temporario():
    cert_bytes = base64.b64decode(CERTIFICADO_BASE64)
    caminho_cert = "/tmp/certificado_temp.pfx"
    with open(caminho_cert, "wb") as f:
        f.write(cert_bytes)
    return caminho_cert

def gerar_criptografia_infosimples(caminho_cert):
    pkcs12_cert = aes_encrypt_urlsafe(CERTIFICADO_BASE64, CHAVE_AES)
    pkcs12_pass = aes_encrypt_urlsafe(CERTIFICADO_SENHA, CHAVE_AES)
    return pkcs12_cert, pkcs12_pass

def consultar_nfe_infosimples(chave_nfe, pkcs12_cert, pkcs12_pass):
    url = "https://api.infosimples.com/api/v2/consultas/receita-federal/nfe"
    payload = {
        "nfe": chave_nfe,
        "pkcs12_cert": pkcs12_cert,
        "pkcs12_pass": pkcs12_pass,
        "token": INFOSIMPLES_TOKEN,
        "timeout": 300
    }

    response = requests.post(url, json=payload)
    try:
        return response.json()
    finally:
        response.close()

def consultar_nfe_completa(chave_nfe):
    try:
        if not all([CERTIFICADO_BASE64, CERTIFICADO_SENHA, INFOSIMPLES_TOKEN]):
            raise ValueError("Variáveis de ambiente faltando.")

        url = "https://api.infosimples.com/api/v2/consultas/receita-federal/nfe"
        payload = {
            "nfe": chave_nfe,
            "pkcs12_cert": CERTIFICADO_BASE64,
            "pkcs12_pass": CERTIFICADO_SENHA,
            "token": INFOSIMPLES_TOKEN,
            "timeout": 300
        }

        response = requests.post(url, json=payload)
        logger.debug("📦 Resposta bruta InfoSimples:", response.text)

        resultado = response.json()
        if not resultado:
            raise ValueError("Resposta da API veio vazia.")

        return resultado

    except Exception as e:
        logger.debug("❌ Erro inesperado ao consultar NF-e:", str(e))
        return {
            "code": 500,
            "code_message": "Erro interno",
            "errors": [str(e)]
        }

