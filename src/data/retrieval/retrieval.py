from typing import Dict, Any, List
import os
import asyncio

from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery, QueryType, QueryCaptionType, QueryAnswerType
from azure.core.credentials import AzureKeyCredential


def _make_search_client(index_env: str) -> SearchClient:
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    api_key = os.environ.get("AZURE_SEARCH_ADMIN_KEY")
    index_name = os.environ.get(index_env)
    missing = [
        n
        for n, v in (("AZURE_SEARCH_ENDPOINT", endpoint), ("AZURE_SEARCH_ADMIN_KEY", api_key), (index_env, index_name))
        if not v
    ]
    if missing:
        raise RuntimeError("Missing environment variables for Azure Search: " + ", ".join(missing))
    credential = AzureKeyCredential(api_key)
    return SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)


def _search_index_sync(
    index_env: str, query_text: str, k: int = 3, vector_field: str = "text_vector"
) -> list[Dict[str, Any]]:
    """Synchronous search using a vectorizable text query; returns list of raw result dicts."""

    client = _make_search_client(index_env)
    index_name = os.environ.get(index_env)
    try:
        vq = VectorizableTextQuery(text=query_text, k_nearest_neighbors=k, fields=vector_field, exhaustive=True)
        results = client.search(
            search_text=None,
            vector_queries=[vq],
            top=k,
            query_type=QueryType.SEMANTIC,
            semantic_configuration_name=f"{index_name}-semantic-config",
            query_caption=QueryCaptionType.EXTRACTIVE,
            query_answer=QueryAnswerType.EXTRACTIVE,
        )
        out = []
        for r in results:
            # result is dict-like
            out.append(dict(r))
        return out
    finally:
        try:
            client.close()
        except Exception:
            pass


async def _search_index(
    index_env: str, query_text: str, k: int = 8, vector_field: str = "text_vector"
) -> list[Dict[str, Any]]:
    return await asyncio.to_thread(_search_index_sync, index_env, query_text, k, vector_field)


async def lookup_unit(name: str) -> List[Dict[str, Any]]:
    """Return up to top-5 matching unit documents as a list of dicts."""
    hits = await _search_index("AZURE_SEARCH_INDEX_UNITS", name, k=5)
    if not hits:
        return []
    out: List[Dict[str, Any]] = []
    for r in hits[:5]:
        out.append(
            {
                "name": r.get("name"),
                "tier": r.get("tier"),
                "trait_ids": r.get("trait_ids"),
                "trait_names": r.get("trait_names"),
                "chunk": r.get("chunk"),
            }
        )
    print(f"[Retrieval] Found {len(out)} unit hits.")
    return out


async def lookup_item(name: str) -> List[Dict[str, Any]]:
    """Return up to top-5 matching item documents as a list of dicts."""
    hits = await _search_index("AZURE_SEARCH_INDEX_ITEMS", name, k=5)
    if not hits:
        return []
    out: List[Dict[str, Any]] = []
    for r in hits[:5]:
        out.append(
            {
                "name": r.get("name"),
                "tier": r.get("tier"),
                "components": r.get("components"),
                "chunk": r.get("chunk"),
            }
        )
    print(f"[Retrieval] Found {len(out)} item hits.")
    return out


async def lookup_trait(name: str) -> List[Dict[str, Any]]:
    """Return up to top-5 matching trait documents as a list of dicts."""
    hits = await _search_index("AZURE_SEARCH_INDEX_TRAITS", name, k=5)
    if not hits:
        return []
    out: List[Dict[str, Any]] = []
    for r in hits[:5]:
        out.append(
            {
                "name": r.get("name"),
                "breakpoints": r.get("breakpoints"),
                "chunk": r.get("chunk"),
            }
        )
    print(f"[Retrieval] Found {len(out)} trait hits.")
    return out
