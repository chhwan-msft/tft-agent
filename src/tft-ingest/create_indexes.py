import os

from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchField,
    SearchIndex,
    SearchableField,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

API = os.getenv("AZURE_SEARCH_API_VERSION", "2024-05-01-Preview")
VECTOR_SEARCH_PROFILE_NAME = "aml-profile"

# cached index client
_index_client = None


def get_index_client():
    global _index_client
    if _index_client is not None:
        return _index_client
    mi_client_id = os.environ.get("AZURE_MANAGED_IDENTITY_CLIENT_ID")
    if mi_client_id:
        cred = DefaultAzureCredential(managed_identity_client_id=mi_client_id)
    else:
        cred = DefaultAzureCredential()
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    if not endpoint:
        raise RuntimeError(
            "AZURE_SEARCH_ENDPOINT is not set. Make sure to load your .env before running or set the environment variable."
        )
    _index_client = SearchIndexClient(endpoint=endpoint, credential=cred)
    return _index_client


def _get_env(name: str, default=None, required: bool = False):
    val = os.getenv(name, default)
    if required and (val is None or val == ""):
        raise RuntimeError(f"Environment variable {name} is required but not set.")
    return val


def _common_vector_search(index_name: str):
    # create index-scoped names to match the pattern used in the example JSON
    algorithm_name = f"{index_name}-algorithm"
    profile_name = f"{index_name}-aiFoundryCatalog-text-profile"
    vectorizer_name = f"{index_name}-aiFoundryCatalog-text-vectorizer"

    hnsw_params = HnswParameters(metric=os.getenv("AOAI_EMBED_METRIC", "cosine"))
    hnsw_config = HnswAlgorithmConfiguration(name=algorithm_name, parameters=hnsw_params)

    aoai_params = AzureOpenAIVectorizerParameters(
        resource_url=_get_env("AOAI_RESOURCE_URI", required=True),
        deployment_name=_get_env("AOAI_EMBED_MODELNAME", required=True),
        api_key=_get_env("AOAI_API_KEY", required=True),
        model_name=os.getenv("AOAI_EMBED_MODELNAME", None),
    )
    aoai_vectorizer = AzureOpenAIVectorizer(vectorizer_name=vectorizer_name, parameters=aoai_params)

    profile = VectorSearchProfile(
        name=profile_name, algorithm_configuration_name=algorithm_name, vectorizer_name=vectorizer_name
    )

    return VectorSearch(profiles=[profile], algorithms=[hnsw_config], vectorizers=[aoai_vectorizer])


def _content_vector_field(index_name: str, field_name: str = "text_vector"):
    # Construct a SearchField for the vector field with the correct vector properties
    return SearchField(
        name=field_name,
        type="Collection(Edm.Single)",
        searchable=True,
        stored=True,
        vector_search_dimensions=int(os.getenv("AOAI_EMBED_DIM", os.getenv("AML_EMBED_DIM", "1536"))),
        vector_search_profile_name=f"{index_name}-aiFoundryCatalog-text-profile",
    )


def create_units_index():
    name = _get_env("AZURE_SEARCH_INDEX_UNITS", required=True)

    fields = [
        SearchField(
            name="chunk_id",
            type="Edm.String",
            searchable=True,
            filterable=False,
            stored=True,
            sortable=True,
            facetable=False,
            key=True,
            analyzer_name="keyword",
        ),
        SearchField(name="parent_id", type="Edm.String", searchable=False, filterable=True, stored=True),
        SearchField(name="chunk", type="Edm.String", searchable=True, stored=True),
        SimpleField(name="id", type="Edm.String"),
        SimpleField(name="set_id", type="Edm.String", filterable=True, facetable=True),
        SimpleField(name="entity_type", type="Edm.String", filterable=True, facetable=True),
        SearchableField(name="name", sortable=True),
        SimpleField(name="tier", type="Edm.Int32", filterable=True, facetable=True, sortable=True),
        SimpleField(name="trait_ids", type="Collection(Edm.String)", filterable=True, facetable=True),
        SimpleField(name="trait_names", type="Collection(Edm.String)", filterable=True, facetable=True),
        SimpleField(name="traits_json", type="Edm.String"),
        SimpleField(name="url", type="Edm.String"),
        _content_vector_field(name),
    ]

    # semantic config for units
    units_semantic_cfg = SemanticConfiguration(
        name=f"{name}-semantic-config",
        prioritized_fields=SemanticPrioritizedFields(
            title_field=SemanticField(field_name="name"),
            content_fields=[SemanticField(field_name="chunk"), SemanticField(field_name="id")],
        ),
    )
    units_semantic_settings = SemanticSearch(
        default_configuration_name=units_semantic_cfg.name, configurations=[units_semantic_cfg]
    )
    index = SearchIndex(
        name=name, fields=fields, vector_search=_common_vector_search(name), semantic_search=units_semantic_settings
    )

    client = get_index_client()
    client.create_or_update_index(index)
    print("Created index:", name)


def create_items_index():
    name = _get_env("AZURE_SEARCH_INDEX_ITEMS", required=True)

    fields = [
        SearchField(
            name="chunk_id",
            type="Edm.String",
            searchable=True,
            filterable=False,
            stored=True,
            sortable=True,
            facetable=False,
            key=True,
            analyzer_name="keyword",
        ),
        SearchField(name="parent_id", type="Edm.String", searchable=False, filterable=True, stored=True),
        SearchField(name="chunk", type="Edm.String", searchable=True, stored=True),
        SearchField(name="id", type="Edm.String", searchable=True, stored=True),
        SimpleField(name="set_id", type="Edm.String", filterable=True, facetable=True),
        SimpleField(name="entity_type", type="Edm.String", filterable=True, facetable=True),
        SearchableField(name="name", sortable=True),
        SearchableField(name="components", type="Collection(Edm.String)", filterable=True, facetable=True),
        SimpleField(name="url", type="Edm.String"),
        _content_vector_field(name),
    ]
    # insert the text_vector SearchField in the same order as the example JSON
    # ensure dimensions/profile are set by _content_vector_field
    # Create index with vector search config scoped to this index
    # semantic config for items
    items_semantic_cfg = SemanticConfiguration(
        name=f"{name}-semantic-config",
        prioritized_fields=SemanticPrioritizedFields(
            title_field=SemanticField(field_name="name"),
            content_fields=[
                SemanticField(field_name="chunk"),
                SemanticField(field_name="components"),
                SemanticField(field_name="id"),
            ],
        ),
    )
    items_semantic_settings = SemanticSearch(
        default_configuration_name=items_semantic_cfg.name, configurations=[items_semantic_cfg]
    )
    index = SearchIndex(
        name=name, fields=fields, vector_search=_common_vector_search(name), semantic_search=items_semantic_settings
    )
    client = get_index_client()
    client.create_or_update_index(index)
    print("Created index:", name)


def create_traits_index():
    name = _get_env("AZURE_SEARCH_INDEX_TRAITS", required=True)

    fields = [
        SearchField(
            name="chunk_id",
            type="Edm.String",
            searchable=True,
            filterable=False,
            stored=True,
            sortable=True,
            facetable=False,
            key=True,
            analyzer_name="keyword",
        ),
        SearchField(name="parent_id", type="Edm.String", searchable=False, filterable=True, stored=True),
        SearchField(name="chunk", type="Edm.String", searchable=True, stored=True),
        SimpleField(name="id", type="Edm.String"),
        SimpleField(name="set_id", type="Edm.String", filterable=True, facetable=True),
        SimpleField(name="entity_type", type="Edm.String", filterable=True, facetable=True),
        SearchableField(name="name", sortable=True),
        SimpleField(name="breakpoints_json", type="Edm.String"),
        SimpleField(name="min_units", type="Collection(Edm.Int32)", filterable=True, facetable=True),
        SimpleField(name="url", type="Edm.String"),
        _content_vector_field(name),
    ]

    # semantic config for traits
    traits_semantic_cfg = SemanticConfiguration(
        name=f"{name}-semantic-config",
        prioritized_fields=SemanticPrioritizedFields(
            title_field=SemanticField(field_name="name"),
            content_fields=[SemanticField(field_name="chunk"), SemanticField(field_name="id")],
        ),
    )
    traits_semantic_settings = SemanticSearch(
        default_configuration_name=traits_semantic_cfg.name, configurations=[traits_semantic_cfg]
    )
    index = SearchIndex(
        name=name, fields=fields, vector_search=_common_vector_search(name), semantic_search=traits_semantic_settings
    )
    client = get_index_client()
    client.create_or_update_index(index)
    print("Created index:", name)
