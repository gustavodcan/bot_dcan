import os
from azure.storage.fileshare import ShareFileClient
from config import (
    AZURE_FILE_ACCOUNT_NAME,
    AZURE_FILE_ACCOUNT_KEY,
    AZURE_FILE_SHARE_NAME
)

def salvar_imagem_azure(local_path, nome_destino):
    file_client = ShareFileClient.from_connection_string(
        conn_str=(
            f"DefaultEndpointsProtocol=https;"
            f"AccountName={AZURE_FILE_ACCOUNT_NAME};"
            f"AccountKey={AZURE_FILE_ACCOUNT_KEY};"
            f"EndpointSuffix=core.windows.net"
        ),
        share_name=AZURE_FILE_SHARE_NAME,
        file_path=nome_destino
    )

    with open(local_path, "rb") as data:
        file_client.upload_file(data)

    print(f"✅ Arquivo enviado como: {nome_destino}")

