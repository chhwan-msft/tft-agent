import os
import json
import io
from azure.storage.blob import BlobServiceClient


def ensure_container(client, name: str):
    try:
        client.create_container(name)
    except Exception:
        pass


def upload_jsonl(container: str, blob_name: str, records: list):
    bsc = BlobServiceClient.from_connection_string(os.environ["AZURE_STORAGE_CONNECTION_STRING"])
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
