import os

from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexerClient
from azure.search.documents.indexes.models import (
    AzureOpenAIEmbeddingSkill,
    FieldMapping,
    IndexingParameters,
    InputFieldMappingEntry,
    OutputFieldMappingEntry,
    SearchIndexer,
    SearchIndexerDataContainer,
    SearchIndexerDataSourceConnection,
    SearchIndexerIndexProjection,
    SearchIndexerIndexProjectionSelector,
    SearchIndexerIndexProjectionsParameters,
    SearchIndexerSkillset,
    SplitSkill,
)

VECTOR_FIELD = "contentVector"  # 1024 dims for Cohere v3 English


def _get_search_endpoint():
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    if not endpoint:
        raise RuntimeError("AZURE_SEARCH_ENDPOINT is not set. Load .env or set the env var.")
    return endpoint


# Cached SearchIndexerClient (initialized lazily)
_indexer_client = None


def get_indexer_client():
    """Return a cached SearchIndexerClient. Honors AZURE_MANAGED_IDENTITY_CLIENT_ID if present.

    This ensures the client is created once and reused across functions in this module.
    """
    global _indexer_client
    if _indexer_client is not None:
        return _indexer_client

    mi_client_id = os.environ.get("AZURE_MANAGED_IDENTITY_CLIENT_ID")
    if mi_client_id:
        cred = DefaultAzureCredential(managed_identity_client_id=mi_client_id)
    else:
        cred = DefaultAzureCredential()

    _indexer_client = SearchIndexerClient(endpoint=_get_search_endpoint(), credential=cred)
    return _indexer_client


def create_blob_datasource(name: str, container: str):
    data_source = SearchIndexerDataSourceConnection(
        name=name,
        type="azureblob",
        connection_string=f"ResourceId=/subscriptions/{os.environ['AZURE_SUBSCRIPTION_ID']}/resourceGroups/{os.environ['AZURE_RESOURCE_GROUP']}/providers/Microsoft.Storage/storageAccounts/{os.environ['AZURE_STORAGE_ACCOUNT']}/;",
        container=SearchIndexerDataContainer(name=container),
    )

    indexer_client = get_indexer_client()
    indexer_client.create_or_update_data_source_connection(data_source)

    print("Created datasource:", name)


def create_embedding_skillset(
    name: str,
    inputFieldMappings: list[InputFieldMappingEntry],
    target_index_name: str = "",
    parent_key_field_name: str = "parent_id",
):
    # Build a skillset that matches the provided JSON structure:
    # 1) SplitSkill to chunk documents
    # 2) AzureOpenAIEmbeddingSkill to embed the pages

    split_inputs = [InputFieldMappingEntry(name="text", source="/document/content")]
    split_outputs = [OutputFieldMappingEntry(name="textItems", target_name="pages")]

    split_skill = SplitSkill(
        name="#1",
        description="Split skill to chunk documents",
        context="/document",
        default_language_code="en",
        text_split_mode="pages",
        maximum_page_length=2000,
        page_overlap_length=500,
        maximum_pages_to_take=0,
        unit="characters",
        inputs=split_inputs,
        outputs=split_outputs,
    )

    emb_inputs = [InputFieldMappingEntry(name="text", source="/document/pages/*")]
    emb_outputs = [OutputFieldMappingEntry(name="embedding", target_name="text_vector")]

    aoai_skill = AzureOpenAIEmbeddingSkill(
        name="#2",
        context="/document/pages/*",
        resource_url=os.environ["AOAI_RESOURCE_URI"],
        api_key=os.environ["AOAI_API_KEY"],
        deployment_name=os.environ["AOAI_EMBED_MODELNAME"],
        dimensions=int(os.environ.get("AOAI_EMBED_DIM", "1536")),
        model_name=os.environ.get("AOAI_EMBED_MODELNAME", None),
        inputs=emb_inputs,
        outputs=emb_outputs,
    )

    skillset = SearchIndexerSkillset(
        name=name,
        description="Skillset to chunk documents and generate embeddings",
        skills=[split_skill, aoai_skill],
    )

    # Build index projection selector and parameters per the JSON
    selector = SearchIndexerIndexProjectionSelector(
        target_index_name=(target_index_name or os.environ.get("AZURE_SEARCH_INDEX_ITEMS", "")),
        parent_key_field_name=parent_key_field_name,
        source_context="/document/pages/*",
        mappings=inputFieldMappings,
    )

    projections = SearchIndexerIndexProjection(
        selectors=[selector],
        parameters=SearchIndexerIndexProjectionsParameters(projection_mode="skipIndexingParentDocuments"),
    )

    # attach index projection (SDK expects 'index_projection')
    skillset.index_projection = projections

    client = get_indexer_client()
    client.create_or_update_skillset(skillset)

    print("Created skillset:", name)


def create_indexer(
    name: str,
    datasource: str,
    skillset: str,
    target_index: str,
    field_mappings: list[FieldMapping],
    output_field_mappings: list[FieldMapping] | None = None,
):
    # If your blobs are JSON (one object per blob), use parsingMode=json.
    # If you upload arrays (many objects per blob), use parsingMode=jsonArray.
    indexing_parameters = IndexingParameters(configuration={"parsingMode": "jsonLines"})

    # Default output mapping: map pages' text_vector to the index field 'text_vector'
    if output_field_mappings is None:
        output_field_mappings = [
            FieldMapping(source_field_name="/document/pages/*/text_vector", target_field_name="text_vector"),
        ]

    indexer = SearchIndexer(
        name=name,
        data_source_name=datasource,
        target_index_name=target_index,
        skillset_name=skillset,
        parameters=indexing_parameters,
        field_mappings=field_mappings,
        output_field_mappings=output_field_mappings,
    )

    indexer_client = get_indexer_client()
    indexer_client.create_or_update_indexer(indexer)

    print("Created indexer:", name)


def run_indexer(name: str):
    indexer_client = get_indexer_client()
    indexer_client.run_indexer(name)

    print("Ran indexer:", name)
