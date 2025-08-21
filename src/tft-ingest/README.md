# TFT Set 15 — Data Ingestion & Azure AI Search Integration

This project ingests Teamfight Tactics (TFT) Set 15 static data (Units, Traits, Items) from CommunityDragon, enriches items with component recipes from community sources, and indexes everything into Azure AI Search using Integrated Vectorization (server-side embeddings + query-time vectorizer).

## Features

- Fetch live Set 15 data from CommunityDragon:
  - Units (with traits)
  - Traits (with breakpoints)
  - Items (with effects and component recipes)
- Generate a full item recipe mapping (keyed by nameId) from community sources such as Mobalytics and Blitz
- Normalize data into JSONL and upload to Azure Blob Storage
- Create Azure AI Search indexes (Units, Items, Traits) with integrated vectorization:
  - Azure OpenAI vectorizer for query-time embeddings
  - Index-time embedding skill (AzureOpenAIEmbeddingSkill)
  - SplitSkill included for future chunking support
- Run indexers to populate indexes with vectors and metadata

## Prerequisites

- Python 3.9+
- Azure resources:
  - Azure AI Search (preview API enabled)
  - Azure Blob Storage
  - Azure OpenAI deployment for embeddings (e.g., text-embedding-3-large)
- CommunityDragon endpoints (configured via the project's `.env`)

## Setup

1. Install dependencies

```
pip install -r requirements.txt
```

2. Configure `.env`

Fill in the values for:

- Azure AI Search: endpoint, admin key, index names
- Azure Blob Storage: connection string, container names
- Azure OpenAI: resource URI, API key, deployment name, API version
- CommunityDragon URLs (defaults for Set 15 are provided but can be overridden)

## Usage

### Step 1 — Generate item recipes

This scrapes Mobalytics and Blitz for Set 15 recipes, maps them to CDragon nameId values, and writes the result to `src/item_components_set15.json`:

```
python -m src.gen_item_components
```

If some items fail to map automatically, edit `src/item_components_set15.json` manually.

### Step 2 — Ingest and index

Fetch data, normalize it, upload JSONL files to blob storage, create indexes/skillsets/indexers, and run them:

```
python -m src.main
```

What this does:

- Uploads `units.jsonl`, `items.jsonl`, `traits.jsonl` to their respective blob containers
- Creates three Azure AI Search indexes: `tftset15-units`, `tftset15-items`, `tftset15-traits`
- Creates skillsets and indexers configured for integrated vectorization
- Runs indexers to populate indexes with vectors and metadata

## Testing / Example query

You can use the Azure Search REST API or the portal. Example POST (JSON body) against the items index:

```
POST https://<search-service>.search.windows.net/indexes/tftset15-items/docs/search?api-version=2024-05-01-Preview
api-key: <admin-key>
Content-Type: application/json

{
  "search": "Infinity Edge",
  "vectorQueries": [
    {
      "kind": "vector",
      "vectorizer": "aoai-vectorizer",
      "fields": "contentVector",
      "k": 5
    }
  ]
}
```

Or use curl (replace placeholders):

```
curl -s -X POST \
  "https://<search-service>.search.windows.net/indexes/tftset15-items/docs/search?api-version=2024-05-01-Preview" \
  -H "api-key: <admin-key>" \
  -H "Content-Type: application/json" \
  -d '{"search":"Infinity Edge","vectorQueries":[{"kind":"vector","vectorizer":"aoai-vectorizer","fields":"contentVector","k":5}]}'
```

## Notes

- Recipes: If scraping fails, manually edit `src/item_components_set15.json`.
- Chunking: `SplitSkill` is included for future chunking; currently the embedding is computed on the full content string.
- Patch updates: Re-run `python -m src.main` after major patches to refresh stats or add new items to the indexes.
