import os
import requests

API = os.getenv("AZURE_SEARCH_API_VERSION", "2024-05-01-Preview")
BASE = f"{os.environ['AZURE_SEARCH_ENDPOINT']}/indexes"
HEADERS = {"Content-Type": "application/json", "api-key": os.environ["AZURE_SEARCH_ADMIN_KEY"]}


def _common_vector_search():
    return {
        "algorithms": [{"name": "hnsw", "kind": "hnsw"}],
        "profiles": [{"name": "aoai-profile", "algorithm": "hnsw", "vectorizer": "aoai-vectorizer"}],
        "vectorizers": [
            {
                "name": "aoai-vectorizer",
                "kind": "azureOpenAI",
                "azureOpenAIParameters": {
                    "resourceUri": os.environ["AOAI_RESOURCE_URI"],
                    "deploymentId": os.environ["AOAI_EMBED_DEPLOYMENT"],
                    "apiKey": os.environ["AOAI_API_KEY"],
                    "apiVersion": os.environ["AOAI_API_VERSION"],
                },
            }
        ],
    }


def _content_vector_field():
    return {
        "name": "contentVector",
        "type": "Collection(Single)",
        "searchable": True,
        "vectorSearchDimensions": int(os.getenv("AOAI_EMBED_DIM", "3072")),
        "vectorSearchProfile": "aoai-profile",
    }


def create_units_index():
    body = {
        "name": os.environ["AZURE_SEARCH_INDEX_UNITS"],
        "fields": [
            {"name": "id", "type": "String", "key": True},
            {"name": "set_id", "type": "String", "filterable": True, "facetable": True},
            {"name": "entity_type", "type": "String", "filterable": True, "facetable": True},
            {"name": "name", "type": "String", "searchable": True, "sortable": True},
            {"name": "tier", "type": "Int32", "filterable": True, "facetable": True, "sortable": True},
            {"name": "trait_ids", "type": "Collection(String)", "filterable": True, "facetable": True},
            {
                "name": "trait_names",
                "type": "Collection(String)",
                "searchable": True,
                "filterable": True,
                "facetable": True,
            },
            {"name": "traits_json", "type": "String"},
            {"name": "content", "type": "String", "searchable": True},
            {"name": "url", "type": "String"},
            _content_vector_field(),
        ],
        "vectorSearch": _common_vector_search(),
    }
    requests.delete(f"{BASE}/{body['name']}?api-version={API}", headers=HEADERS)
    r = requests.put(f"{BASE}/{body['name']}?api-version={API}", headers=HEADERS, json=body)
    r.raise_for_status()
    print("Created index:", body["name"])


def create_items_index():
    body = {
        "name": os.environ["AZURE_SEARCH_INDEX_ITEMS"],
        "fields": [
            {"name": "id", "type": "String", "key": True},
            {"name": "set_id", "type": "String", "filterable": True, "facetable": True},
            {"name": "entity_type", "type": "String", "filterable": True, "facetable": True},
            {"name": "name", "type": "String", "searchable": True, "sortable": True},
            {"name": "desc", "type": "String", "searchable": True},
            {"name": "effects_text", "type": "String", "searchable": True},
            {
                "name": "components",
                "type": "Collection(String)",
                "searchable": True,
                "filterable": True,
                "facetable": True,
            },
            {"name": "components_ids", "type": "Collection(String)", "filterable": True, "facetable": True},
            {"name": "content", "type": "String", "searchable": True},
            {"name": "url", "type": "String"},
            _content_vector_field(),
        ],
        "vectorSearch": _common_vector_search(),
    }
    requests.delete(f"{BASE}/{body['name']}?api-version={API}", headers=HEADERS)
    r = requests.put(f"{BASE}/{body['name']}?api-version={API}", headers=HEADERS, json=body)
    r.raise_for_status()
    print("Created index:", body["name"])


def create_traits_index():
    body = {
        "name": os.environ["AZURE_SEARCH_INDEX_TRAITS"],
        "fields": [
            {"name": "id", "type": "String", "key": True},
            {"name": "set_id", "type": "String", "filterable": True, "facetable": True},
            {"name": "entity_type", "type": "String", "filterable": True, "facetable": True},
            {"name": "name", "type": "String", "searchable": True, "sortable": True},
            {"name": "desc", "type": "String", "searchable": True},
            {"name": "breakpoints_json", "type": "String"},
            {"name": "min_units", "type": "Collection(Int32)", "filterable": True, "facetable": True},
            {"name": "content", "type": "String", "searchable": True},
            {"name": "url", "type": "String"},
            _content_vector_field(),
        ],
        "vectorSearch": _common_vector_search(),
    }
    requests.delete(f"{BASE}/{body['name']}?api-version={API}", headers=HEADERS)
    r = requests.put(f"{BASE}/{body['name']}?api-version={API}", headers=HEADERS, json=body)
    r.raise_for_status()
    print("Created index:", body["name"])
