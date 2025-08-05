import json
from google.cloud import vision
from google.oauth2 import service_account
from PIL import Image
from config import GOOGLE_CREDS_PATH

def get_google_vision_client():
    with open(GOOGLE_CREDS_PATH, "r") as f:
        creds_dict = json.load(f)
    credentials = service_account.Credentials.from_service_account_info(creds_dict)
    return vision.ImageAnnotatorClient(credentials=credentials)

def ler_texto_google_ocr(path_imagem):
    client = get_google_vision_client()

    with open(path_imagem, "rb") as image_file:
        content = image_file.read()

    image = vision.Image(content=content)
    response = client.text_detection(image=image)
    texts = response.text_annotations

    return texts[0].description if texts else ""

def preprocessar_imagem(caminho):
    imagem = Image.open(caminho)
    largura, altura = imagem.size
    imagem = imagem.resize((largura * 2, altura * 2), Image.LANCZOS)
    return imagem

