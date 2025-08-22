import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

from cdragon_fetch import fetch_units, fetch_items, fetch_traits
from build_docs import unit_to_doc, item_to_doc, trait_to_doc
from blob_upload import upload_jsonl
from create_indexes import create_units_index, create_items_index, create_traits_index
from indexers import create_blob_datasource, create_embedding_skillset, create_indexer, run_indexer


def main():
    # Load .env located next to this file first (deterministic).
    # If it exists, allow it to override other env values.
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
        print(f"Loaded .env from {env_path}")
    else:
        # Fallback: let python-dotenv locate a .env (e.g., project root).
        found = find_dotenv()
        if found:
            load_dotenv(dotenv_path=found, override=False)
            print(f"Loaded .env from {found}")
        else:
            print("No .env file found; relying on environment variables")

    # --- Fetch & normalize ---
    units = [unit_to_doc(u) for u in fetch_units()]
    items = [item_to_doc(i) for i in fetch_items()]
    traits = [trait_to_doc(t) for t in fetch_traits()]

    # --- Upload to Blob ---
    upload_jsonl(os.environ["BLOB_CONTAINER_UNITS"], "units.jsonl", units)
    upload_jsonl(os.environ["BLOB_CONTAINER_ITEMS"], "items.jsonl", items)
    upload_jsonl(os.environ["BLOB_CONTAINER_TRAITS"], "traits.jsonl", traits)

    # --- Create Search indexes (with vectorizer) ---
    create_units_index()
    create_items_index()
    create_traits_index()

    # --- Datasources ---
    create_blob_datasource("tftset15-units-ds", os.environ["BLOB_CONTAINER_UNITS"])
    create_blob_datasource("tftset15-items-ds", os.environ["BLOB_CONTAINER_ITEMS"])
    create_blob_datasource("tftset15-traits-ds", os.environ["BLOB_CONTAINER_TRAITS"])

    # --- Skillsets (Split + Embedding) ---
    create_embedding_skillset("tftset15-units-ss")
    create_embedding_skillset("tftset15-items-ss")
    create_embedding_skillset("tftset15-traits-ss")

    # --- Indexers (map skill output to contentVector) ---
    create_indexer(
        name="tftset15-units-idxr",
        datasource="tftset15-units-ds",
        skillset="tftset15-units-ss",
        target_index=os.environ["AZURE_SEARCH_INDEX_UNITS"],
        output_mappings=[{"sourceFieldName": "/document/contentVector", "targetFieldName": "contentVector"}],
    )
    create_indexer(
        name="tftset15-items-idxr",
        datasource="tftset15-items-ds",
        skillset="tftset15-items-ss",
        target_index=os.environ["AZURE_SEARCH_INDEX_ITEMS"],
        output_mappings=[{"sourceFieldName": "/document/contentVector", "targetFieldName": "contentVector"}],
    )
    create_indexer(
        name="tftset15-traits-idxr",
        datasource="tftset15-traits-ds",
        skillset="tftset15-traits-ss",
        target_index=os.environ["AZURE_SEARCH_INDEX_TRAITS"],
        output_mappings=[{"sourceFieldName": "/document/contentVector", "targetFieldName": "contentVector"}],
    )

    # --- Run indexers ---
    run_indexer("tftset15-units-idxr")
    run_indexer("tftset15-items-idxr")
    run_indexer("tftset15-traits-idxr")


if __name__ == "__main__":
    main()
