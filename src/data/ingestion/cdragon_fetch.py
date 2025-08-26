# src/cdragon_fetch.py
import os
import json
import requests
from tenacity import retry, stop_after_attempt, wait_fixed

from utils.dotenv_loader import load_nearest_dotenv

# Load environment variables
load_nearest_dotenv(start_path=__file__, override=False)


# Defer reading environment variables until runtime to avoid import-time KeyErrors.
def _get_env(name: str, default=None, required: bool = False):
    val = os.getenv(name, default)
    if required and (val is None or val == ""):
        raise RuntimeError(f"Environment variable {name} is required but not set.")
    return val


def _get_units_url():
    return _get_env("CDRAGON_UNITS_URL", required=True)


def _get_items_url():
    return _get_env("CDRAGON_ITEMS_URL", required=True)


def _get_traits_url():
    return _get_env("CDRAGON_TRAITS_URL", required=True)


def _get_set_key():
    return _get_env("SET_KEY", "TFTSet15")


HEADERS = {"User-Agent": "tft-poc/1.0 (+azure-ai-foundry)"}


@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
def get_json(url: str):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def _effects_to_text(effects):
    if isinstance(effects, dict):
        return "; ".join([f"{k}: {v}" for k, v in effects.items()])
    if isinstance(effects, list):
        return "; ".join([json.dumps(x, ensure_ascii=False) for x in effects])
    return str(effects) if effects is not None else ""


def fetch_units():
    units_url = _get_units_url()
    data = get_json(units_url)
    if _get_set_key() not in data:
        set_keys = sorted([k for k in data.keys() if k.startswith("TFTSet")])
        if not set_keys:
            raise RuntimeError("No TFTSet keys in team-planner JSON.")
        set_key = set_keys[-1]
    else:
        set_key = _get_set_key()

    units = []
    for e in data[set_key]:
        # Keep your sample fields; 'tier' may be 'cost' in some exports—copy over if missing
        unit = {
            "character_id": e.get("character_id"),
            "display_name": e.get("display_name"),
            "tier": e.get("tier") or e.get("cost"),
            "traits": e.get("traits", []),  # expect array of {name,id,amount}
            "set_id": set_key,
            "source_url": units_url,
        }
        units.append(unit)

    return units


def fetch_traits():
    traits_url = _get_traits_url()
    data = get_json(traits_url)
    traits = []
    # CDragon tfttraits.json can be list or dict; normalize accordingly
    if isinstance(data, dict):
        iterable = data.get("traits") or data.values()
    else:
        iterable = data

    for e in iterable:
        traits.append(
            {
                "display_name": e.get("name") or e.get("display_name"),
                "trait_id": e.get("trait_id") or e.get("apiName"),
                "set": e.get("set") or "TFTSet15",
                "tooltip_text": e.get("tooltip_text") or e.get("description", ""),
                "conditional_trait_sets": e.get("levels") or e.get("conditional_trait_sets") or [],
                "source_url": traits_url,
            }
        )

    return traits


def _load_item_components_map():
    """
    Mapping keyed by nameId (e.g., 'TFT_Item_InfinityEdge') with:
        { "components": ["B.F. Sword", "Sparring Gloves"] }
    """
    path = os.path.join(os.path.dirname(__file__), "item_components_set15.json")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_items():
    items_url = _get_items_url()
    data = get_json(items_url)
    comp_map = _load_item_components_map()
    items = []
    iterable = data.get("items") if isinstance(data, dict) else data

    for e in iterable or []:
        nameId = e.get("id") or e.get("apiName") or e.get("nameId")
        name = e.get("name") or e.get("display_name") or nameId

        rec = {
            "nameId": nameId,
            "name": name,
            "set_id": "TFTSet15",
            "source_url": items_url,
        }

        if nameId in comp_map:
            rec["components"] = comp_map[nameId].get("components", [])
        items.append(rec)

    return items
