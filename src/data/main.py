import argparse
import os

from utils.dotenv_loader import load_nearest_dotenv

from azure.search.documents.indexes.models import FieldMapping, InputFieldMappingEntry
from ingestion.blob_upload import upload_jsonl
from ingestion.build_docs import item_to_doc, trait_to_doc, unit_to_doc
from ingestion.cdragon_fetch import fetch_items, fetch_traits, fetch_units
from ingestion.create_indexes import create_items_index, create_traits_index, create_units_index
from ingestion.indexers import create_blob_datasource, create_embedding_skillset, create_indexer, run_indexer


def _load_dotenv():
    loaded = load_nearest_dotenv(start_path=__file__, override=False)
    if loaded:
        print(f"Loaded .env from {loaded}")
    else:
        print("No .env file found; relying on environment variables")


def main():
    _load_dotenv()

    parser = argparse.ArgumentParser(description="Run TFT ingest pipeline steps")
    parser.add_argument("--all", action="store_true", help="Run all steps in order")
    parser.add_argument("--fetch", action="store_true", help="Fetch units, items, and traits from cdragon")
    parser.add_argument("--upload", action="store_true", help="Upload generated jsonl to blob storage")
    parser.add_argument("--create-indexes", action="store_true", help="Create Azure Search indexes")
    parser.add_argument("--create-datasources", action="store_true", help="Create blob datasources")
    parser.add_argument("--create-skillsets", action="store_true", help="Create embedding skillsets")
    parser.add_argument("--create-indexers", action="store_true", help="Create indexers")
    parser.add_argument("--run-indexers", action="store_true", help="Run indexers")

    args = parser.parse_args()

    # If --all, enable all steps
    flags = {
        "fetch": args.all or args.fetch,
        "upload": args.all or args.upload,
        "create_indexes": args.all or args.create_indexes,
        "create_datasources": args.all or args.create_datasources,
        "create_skillsets": args.all or args.create_skillsets,
        "create_indexers": args.all or args.create_indexers,
        "run_indexers": args.all or args.run_indexers,
    }

    if not any(flags.values()):
        parser.print_help()
        return

    units = items = traits = None

    # Fetch step (creates normalized docs)
    if flags["fetch"] or flags["upload"]:
        print("Fetching units/items/traits...")
        units = [unit_to_doc(u) for u in fetch_units()]
        items = [item_to_doc(i) for i in fetch_items()]
        traits = [trait_to_doc(t) for t in fetch_traits()]

    # Upload to Blob
    if flags["upload"]:
        print("Uploading JSONL to blob storage...")
        if units is None or items is None or traits is None:
            # Ensure we have data
            units = [unit_to_doc(u) for u in fetch_units()] if units is None else units
            items = [item_to_doc(i) for i in fetch_items()] if items is None else items
            traits = [trait_to_doc(t) for t in fetch_traits()] if traits is None else traits
        upload_jsonl(os.environ["BLOB_CONTAINER_UNITS"], "units.jsonl", units)
        upload_jsonl(os.environ["BLOB_CONTAINER_ITEMS"], "items.jsonl", items)
        upload_jsonl(os.environ["BLOB_CONTAINER_TRAITS"], "traits.jsonl", traits)

    # Create Search indexes
    if flags["create_indexes"]:
        print("Creating search indexes...")
        create_units_index()
        create_items_index()
        create_traits_index()

    # Datasources
    if flags["create_datasources"]:
        print("Creating blob datasources...")
        create_blob_datasource("tftset15-units-ds", os.environ["BLOB_CONTAINER_UNITS"])
        create_blob_datasource("tftset15-items-ds", os.environ["BLOB_CONTAINER_ITEMS"])
        create_blob_datasource("tftset15-traits-ds", os.environ["BLOB_CONTAINER_TRAITS"])

    # Skillsets
    if flags["create_skillsets"]:
        print("Creating embedding skillsets...")
        create_embedding_skillset(
            "tftset15-units-ss",
            [
                InputFieldMappingEntry(name="text_vector", source="/document/pages/*/text_vector"),
                InputFieldMappingEntry(name="chunk", source="/document/pages/*"),
                InputFieldMappingEntry(name="id", source="/document/id"),
                InputFieldMappingEntry(name="entity_type", source="/document/entity_type"),
                InputFieldMappingEntry(name="set_id", source="/document/set_id"),
                InputFieldMappingEntry(name="name", source="/document/name"),
                InputFieldMappingEntry(name="tier", source="/document/tier"),
                InputFieldMappingEntry(name="trait_ids", source="/document/trait_ids"),
                InputFieldMappingEntry(name="trait_names", source="/document/trait_names"),
                InputFieldMappingEntry(name="traits_json", source="/document/traits_json"),
                InputFieldMappingEntry(name="url", source="/document/url"),
            ],
            target_index_name=os.environ.get("AZURE_SEARCH_INDEX_UNITS", ""),
        )
        create_embedding_skillset(
            "tftset15-items-ss",
            [
                InputFieldMappingEntry(name="text_vector", source="/document/pages/*/text_vector"),
                InputFieldMappingEntry(name="chunk", source="/document/pages/*"),
                InputFieldMappingEntry(name="id", source="/document/id"),
                InputFieldMappingEntry(name="entity_type", source="/document/entity_type"),
                InputFieldMappingEntry(name="set_id", source="/document/set_id"),
                InputFieldMappingEntry(name="name", source="/document/name"),
                InputFieldMappingEntry(name="components", source="/document/components"),
                InputFieldMappingEntry(name="url", source="/document/url"),
            ],
            target_index_name=os.environ.get("AZURE_SEARCH_INDEX_ITEMS", ""),
        )
        create_embedding_skillset(
            "tftset15-traits-ss",
            [
                InputFieldMappingEntry(name="text_vector", source="/document/pages/*/text_vector"),
                InputFieldMappingEntry(name="chunk", source="/document/pages/*"),
                InputFieldMappingEntry(name="id", source="/document/id"),
                InputFieldMappingEntry(name="entity_type", source="/document/entity_type"),
                InputFieldMappingEntry(name="set_id", source="/document/set_id"),
                InputFieldMappingEntry(name="name", source="/document/name"),
                InputFieldMappingEntry(name="breakpoints_json", source="/document/breakpoints_json"),
                InputFieldMappingEntry(name="min_units", source="/document/min_units"),
                InputFieldMappingEntry(name="url", source="/document/url"),
            ],
            target_index_name=os.environ.get("AZURE_SEARCH_INDEX_TRAITS", ""),
        )

    # Indexers
    if flags["create_indexers"]:
        print("Creating indexers...")
        create_indexer(
            name="tftset15-unit-idxr",
            datasource="tftset15-units-ds",
            skillset="tftset15-units-ss",
            target_index=os.environ["AZURE_SEARCH_INDEX_UNITS"],
            field_mappings=[
                # Use the 'id' from JSONL (DO NOT override with metadata_storage_path)
                FieldMapping(source_field_name="/id", target_field_name="id"),
                FieldMapping(source_field_name="/set_id", target_field_name="set_id"),
                FieldMapping(source_field_name="/entity_type", target_field_name="entity_type"),
                FieldMapping(source_field_name="/name", target_field_name="name"),
                FieldMapping(source_field_name="/tier", target_field_name="tier"),
                FieldMapping(source_field_name="/trait_ids", target_field_name="trait_ids"),
                FieldMapping(source_field_name="/trait_names", target_field_name="trait_names"),
                FieldMapping(source_field_name="/traits_json", target_field_name="traits_json"),
                FieldMapping(source_field_name="/content", target_field_name="chunk"),
                FieldMapping(source_field_name="/url", target_field_name="url"),
            ],
        )
        create_indexer(
            name="tftset15-item-idxr",
            datasource="tftset15-items-ds",
            skillset="tftset15-items-ss",
            target_index=os.environ["AZURE_SEARCH_INDEX_ITEMS"],
            field_mappings=[
                # Use the 'id' from JSONL (DO NOT override with metadata_storage_path)
                FieldMapping(source_field_name="/id", target_field_name="id"),
                FieldMapping(source_field_name="/set_id", target_field_name="set_id"),
                FieldMapping(source_field_name="/entity_type", target_field_name="entity_type"),
                FieldMapping(source_field_name="/name", target_field_name="name"),
                FieldMapping(source_field_name="/components", target_field_name="components"),
                FieldMapping(source_field_name="/content", target_field_name="chunk"),
                FieldMapping(source_field_name="/url", target_field_name="url"),
            ],
        )
        create_indexer(
            name="tftset15-trait-idxr",
            datasource="tftset15-traits-ds",
            skillset="tftset15-traits-ss",
            target_index=os.environ["AZURE_SEARCH_INDEX_TRAITS"],
            field_mappings=[
                # Use the 'id' from JSONL (DO NOT override with metadata_storage_path)
                FieldMapping(source_field_name="/id", target_field_name="id"),
                FieldMapping(source_field_name="/set_id", target_field_name="set_id"),
                FieldMapping(source_field_name="/entity_type", target_field_name="entity_type"),
                FieldMapping(source_field_name="/name", target_field_name="name"),
                FieldMapping(source_field_name="/breakpoints_json", target_field_name="breakpoints_json"),
                FieldMapping(source_field_name="/min_units", target_field_name="min_units"),
                FieldMapping(source_field_name="/content", target_field_name="chunk"),
                FieldMapping(source_field_name="/url", target_field_name="url"),
            ],
        )

    # Run indexers
    if flags["run_indexers"]:
        print("Running indexers...")
        run_indexer("tftset15-units-idxr")
        run_indexer("tftset15-items-idxr")
        run_indexer("tftset15-traits-idxr")


if __name__ == "__main__":
    main()
