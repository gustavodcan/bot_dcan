import os, logging
from azure.storage.fileshare import ShareServiceClient
from azure.core.exceptions import ResourceExistsError

logger = logging.getLogger(__name__)

ACCOUNT_NAME = os.getenv("AZURE_FILE_ACCOUNT_NAME", "").strip()
ACCOUNT_KEY  = os.getenv("AZURE_FILE_ACCOUNT_KEY", "").strip()
DEFAULT_SHARE = os.getenv("AZURE_SHARE_NAME", "tickets").strip()

def _get_service_client() -> ShareServiceClient:
    if not ACCOUNT_NAME or not ACCOUNT_KEY:
        raise RuntimeError(
            "Defina AZURE_FILE_ACCOUNT_NAME e AZURE_FILE_ACCOUNT_KEY no ambiente."
        )
    account_url = f"https://{ACCOUNT_NAME}.file.core.windows.net"
    return ShareServiceClient(account_url=account_url, credential=ACCOUNT_KEY)

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
    for seg in dir_path.split("/"):
        if not seg:
            continue
        current = f"{current}/{seg}" if current else seg
        try:
            share_client.get_directory_client(current).create_directory()
            logger.debug(f"[AZURE] Diretório criado: {current}")
        except ResourceExistsError:
            logger.debug(f"[AZURE] Diretório já existe: {current}")
        except Exception:
            logger.error(f"[AZURE] Falha ao criar diretório: {current}", exc_info=True)
            raise

def salvar_imagem_azure(caminho_local: str, destino_relativo: str, share_name: str | None = None):
    share = (share_name or DEFAULT_SHARE).strip()
    if not share:
        raise ValueError("Nome do share inválido.")

    rel = (destino_relativo or "").replace("\\", "/").strip().lstrip("/")
    if not rel:
        raise ValueError("destino_relativo inválido.")

    parts = rel.split("/")
    filename = parts[-1]
    dir_path = "/".join(parts[:-1])

    service = _get_service_client()
    share_client = service.get_share_client(share)

    _ensure_share(share_client)
    _ensure_directories(share_client, dir_path)

    file_client = share_client.get_file_client(rel)
    with open(caminho_local, "rb") as data:
        file_client.upload_file(data)
        logger.info(f"[AZURE] Upload OK: {share}/{rel}")
