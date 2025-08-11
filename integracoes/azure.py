# integracoes/azure.py
import os, logging
from azure.storage.fileshare import ShareServiceClient
from azure.core.exceptions import ResourceExistsError
from config import AZURE_CONNECTION_STRING

logger = logging.getLogger(__name__)

def _ensure_share(share_client):
    try:
        share_client.create_share()
        logger.debug("[AZURE] Share criado.")
    except ResourceExistsError:
        logger.debug("[AZURE] Share já existe (ok).")
    except Exception:
        logger.error("[AZURE] Falha ao criar share.", exc_info=True)

def _ensure_directories(share_client, dir_path: str):
    if not dir_path:
        return
    current = ""
    for segment in dir_path.split("/"):
        if not segment:
            continue
        current = f"{current}/{segment}" if current else segment
        try:
            share_client.get_directory_client(current).create_directory()
            logger.debug(f"[AZURE] Diretório criado: {current}")
        except ResourceExistsError:
            logger.debug(f"[AZURE] Diretório já existe: {current}")
        except Exception:
            logger.error(f"[AZURE] Falha ao criar diretório: {current}", exc_info=True)
            raise

def salvar_imagem_azure(caminho_local: str, destino_relativo: str, share_name: str = "tickets"):
    rel = (destino_relativo or "").strip().replace("\\", "/").lstrip("/")
    if not rel:
        raise ValueError("destino_relativo inválido")

    parts = rel.split("/")
    filename = parts[-1]
    dir_path = "/".join(parts[:-1])

    service = ShareServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
    share_client = service.get_share_client(share_name)

    _ensure_share(share_client)
    _ensure_directories(share_client, dir_path)

    file_path_in_share = rel  
    file_client = share_client.get_file_client(file_path_in_share)

    with open(caminho_local, "rb") as data:
        file_client.upload_file(data)  
        logger.info(f"[AZURE] Upload ok: {share_name}/{file_path_in_share}")
