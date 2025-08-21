import os
import requests

API = os.getenv("AZURE_SEARCH_API_VERSION", "2024-05-01-Preview")
BASE_DS = f"{os.environ['AZURE_SEARCH_ENDPOINT']}/datasources"
BASE_SS = f"{os.environ['AZURE_SEARCH_ENDPOINT']}/skillsets"
BASE_IDX = f"{os.environ['AZURE_SEARCH_ENDPOINT']}/indexers"
HEADERS = {"Content-Type": "application/json", "api-key": os.environ["AZURE_SEARCH_ADMIN_KEY"]}


def create_blob_datasource(name: str, container: str):
    body = {
        "name": name,
        "type": "azureblob",
        "credentials": {"connectionString": os.environ["AZURE_STORAGE_CONNECTION_STRING"]},
        "container": {"name": container},
    }
    requests.delete(f"{BASE_DS}/{name}?api-version={API}", headers=HEADERS)
    r = requests.put(f"{BASE_DS}/{name}?api-version={API}", headers=HEADERS, json=body)
    r.raise_for_status()
    print("Created datasource:", name)


def create_embedding_skillset(name: str):
    body = {
        "name": name,
        "skills": [
            {
                "@odata.type": "#Microsoft.Skills.Text.SplitSkill",
                "description": "Split content for potential chunked embeddings later",
                "context": "/document",
                "defaultLanguageCode": "en",
                "textSplitMode": "sentences",
                "maximumPageLength": 1000,
                "inputs": [{"name": "text", "source": "/document/content"}],
                "outputs": [{"name": "textItems", "targetName": "content_pages"}],
            },
            {
                "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
                "description": "Embed the primary content (single vector per doc)",
                "context": "/document",
                "inputs": [{"name": "text", "source": "/document/content"}],
                "outputs": [{"name": "embedding", "targetName": "contentVector"}],
                "azureOpenAIParameters": {
                    "resourceUri": os.environ["AOAI_RESOURCE_URI"],
                    "deploymentId": os.environ["AOAI_EMBED_DEPLOYMENT"],
                    "apiKey": os.environ["AOAI_API_KEY"],
                    "apiVersion": os.environ["AOAI_API_VERSION"],
                },
            },
        ],
    }
    requests.delete(f"{BASE_SS}/{name}?api-version={API}", headers=HEADERS)
    r = requests.put(f"{BASE_SS}/{name}?api-version={API}", headers=HEADERS, json=body)
    r.raise_for_status()
    print("Created skillset:", name)


def create_indexer(
    name: str,
    datasource: str,
    skillset: str,
    target_index: str,
    field_mappings: list = None,
    output_mappings: list = None,
):
    body = {
        "name": name,
        "dataSourceName": datasource,
        "skillsetName": skillset,
        "targetIndexName": target_index,
        "fieldMappings": field_mappings or [],
        "outputFieldMappings": output_mappings or [],
    }
    requests.delete(f"{BASE_IDX}/{name}?api-version={API}", headers=HEADERS)
    r = requests.put(f"{BASE_IDX}/{name}?api-version={API}", headers=HEADERS, json=body)
    r.raise_for_status()
    print("Created indexer:", name)


def run_indexer(name: str):
    r = requests.post(f"{BASE_IDX}/{name}/run?api-version={API}", headers=HEADERS)
    r.raise_for_status()
    print("Ran indexer:", name)
