# src/cdragon_fetch.py
import os
import json
import requests
from tenacity import retry, stop_after_attempt, wait_fixed

UNITS_URL = os.getenv("CDRAGON_UNITS_URL")
ITEMS_URL = os.getenv("CDRAGON_ITEMS_URL")
TRAITS_URL = os.getenv("CDRAGON_TRAITS_URL")
SET_KEY = os.getenv("SET_KEY", "TFTSet15")

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
    data = get_json(UNITS_URL)
    if SET_KEY not in data:
        set_keys = sorted([k for k in data.keys() if k.startswith("TFTSet")])
        if not set_keys:
            raise RuntimeError("No TFTSet keys in team-planner JSON.")
        set_key = set_keys[-1]
    else:
        set_key = SET_KEY

    out = []
    for e in data[set_key]:
        # Keep your sample fields; 'tier' may be 'cost' in some exports—copy over if missing
        unit = {
            "character_id": e.get("character_id"),
            "display_name": e.get("display_name"),
            "tier": e.get("tier") or e.get("cost"),
            "traits": e.get("traits", []),  # expect array of {name,id,amount}
            "set_id": set_key,
            "source_url": UNITS_URL,
        }
        out.append(unit)
    return out


def fetch_traits():
    data = get_json(TRAITS_URL)
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
                "trait_id": e.get("id") or e.get("apiName"),
                "set": e.get("set") or "TFTSet15",
                "tooltip_text": e.get("desc") or e.get("description", ""),
                "conditional_trait_sets": e.get("levels") or e.get("conditional_trait_sets") or [],
                "source_url": TRAITS_URL,
            }
        )
    return traits


def _load_item_components_map():
    """
    Mapping keyed by nameId (e.g., 'TFT_Item_InfinityEdge') with:
      { "components": ["B.F. Sword", "Sparring Gloves"], "components_ids": [...] }
    """
    path = os.path.join(os.path.dirname(__file__), "item_components_set15.json")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_items():
    data = get_json(ITEMS_URL)
    comp_map = _load_item_components_map()
    items = []
    iterable = data.get("items") if isinstance(data, dict) else data

    for e in iterable or []:
        nameId = e.get("id") or e.get("apiName") or e.get("nameId")
        name = e.get("name") or e.get("display_name") or nameId
        desc = e.get("desc") or e.get("description") or ""
        effects_text = _effects_to_text(e.get("effects"))

        rec = {
            "nameId": nameId,
            "name": name,
            "desc": desc,
            "effects_text": effects_text,
            "set_id": "TFTSet15",
            "source_url": ITEMS_URL,
        }

        if nameId and nameId in comp_map:
            rec["components"] = comp_map[nameId].get("components", [])
            rec["components_ids"] = comp_map[nameId].get("components_ids", [])
        items.append(rec)
