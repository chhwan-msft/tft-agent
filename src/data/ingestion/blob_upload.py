import os
import json
import io
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from utils.dotenv_loader import load_nearest_dotenv

# Load environment variables
load_nearest_dotenv(start_path=__file__, override=False)


def ensure_container(client, name: str):
    try:
        client.create_container(name)
    except Exception:
        pass


def _get_blob_service_client():
    # Authenticate using Managed Identity via DefaultAzureCredential.
    # Requires AZURE_STORAGE_ACCOUNT to be set to the storage account name (no URL).
    account_name = os.environ.get("AZURE_STORAGE_ACCOUNT")
    if not account_name:
        raise RuntimeError(
            "AZURE_STORAGE_ACCOUNT is not set. Set it to your storage account name (e.g. 'mystorageacct')."
        )
    account_url = f"https://{account_name}.blob.core.windows.net"
    mi_client_id = os.environ.get("AZURE_MANAGED_IDENTITY_CLIENT_ID")
    if mi_client_id:
        cred = DefaultAzureCredential(managed_identity_client_id=mi_client_id)
    else:
        cred = DefaultAzureCredential()

    return BlobServiceClient(account_url=account_url, credential=cred)


def upload_jsonl(container: str, blob_name: str, records: list):
    bsc = _get_blob_service_client()
    ensure_container(bsc, container)

    data = io.BytesIO()
    for r in records:
        line = json.dumps(r, ensure_ascii=False) + "\n"
        data.write(line.encode("utf-8"))
    data.seek(0)
    bsc.get_container_client(container).upload_blob(
        name=blob_name, data=data, overwrite=True, content_type="application/json"
    )
    print(f"Uploaded {len(records)} records to blob: {container}/{blob_name}")
