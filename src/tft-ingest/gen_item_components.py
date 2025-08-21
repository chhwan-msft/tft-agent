import os
import json
import re
import requests
from bs4 import BeautifulSoup

CDRAGON_ITEMS_URL = os.getenv(
    "CDRAGON_ITEMS_URL",
    "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/tftitems.json",
)
MOBALYTICS_URL = "https://mobalytics.gg/tft/items/combined"
BLITZ_URL = "https://blitz.gg/tft/items/overview"

OUT = os.path.join(os.path.dirname(__file__), "item_components_set15.json")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; tft-recipe-bot/1.0; +POC)", "Accept-Language": "en-US,en;q=0.9"}


def norm(s: str) -> str:
    s = s.strip().lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[\.]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def load_cdragon_items():
    r = requests.get(CDRAGON_ITEMS_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    iterable = data.get("items") if isinstance(data, dict) else data
    by_display = {}
    by_id = {}
    for e in iterable or []:
        nameId = e.get("id") or e.get("apiName") or e.get("nameId")
        disp = e.get("name") or e.get("display_name") or nameId
        if not nameId or not disp:
            continue
        by_display[norm(disp)] = nameId
        by_id[nameId] = disp
    return by_display, by_id


def parse_mobalytics():
    r = requests.get(MOBALYTICS_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    mapping = {}
    cards = soup.find_all(["article", "div", "section"])
    for c in cards:
        title = c.find(["h2", "h3", "h4"])
        if not title:
            continue
        item_name = title.get_text(strip=True)
        if not item_name:
            continue
        text = c.get_text(" ", strip=True)
        if "Recipe" not in text and "Components" not in text:
            continue
        comp_labels = []
        for li in c.find_all("li"):
            t = li.get_text(" ", strip=True)
            if t and len(t) <= 40:
                comp_labels.append(t)
        comp_labels = [x for x in comp_labels if x.lower() not in ("recipe", "components")]
        if len(comp_labels) >= 2:
            mapping[item_name] = comp_labels[:2]
    return mapping


def parse_blitz():
    r = requests.get(BLITZ_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    mapping = {}
    cards = soup.find_all(["article", "section", "div"])
    for c in cards:
        hdr = c.find(["h3", "h2", "h4"])
        if not hdr:
            continue
        item_name = hdr.get_text(strip=True)
        t = c.get_text(" ", strip=True)
        m = re.search(r"([A-Za-z0-9\.\'’\- ]+)\s\+\s([A-Za-z0-9\.\'’\- ]+)", t)
        if m:
            a = m.group(1).strip()
            b = m.group(2).strip()
            mapping[item_name] = [a, b]
    return mapping


def merge_to_nameId(cdragon_by_display, recipes_by_display):
    out = {}
    missed = []
    for disp, comps in recipes_by_display.items():
        key = cdragon_by_display.get(norm(disp))
        if not key:
            missed.append(disp)
            continue
        out[key] = {"components": comps, "components_ids": []}
    return out, missed


def merge_into_file(new_map: dict):
    if os.path.exists(OUT):
        with open(OUT, "r", encoding="utf-8") as f:
            current = json.load(f)
    else:
        current = {}
    for k, v in new_map.items():
        current.setdefault(k, v)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    print(f"[gen_item_components] Wrote {len(current)} items to {OUT}")


def main():
    cdragon_by_display, _ = load_cdragon_items()
    print(f"[gen_item_components] Loaded {len(cdragon_by_display)} items from CDragon")

    merged_display = {}
    try:
        moba = parse_mobalytics()
        print(f"[gen_item_components] Mobalytics parsed: {len(moba)} items")
        merged_display.update(moba)
    except Exception as e:
        print("[gen_item_components] Mobalytics scrape failed:", e)

    try:
        blitz = parse_blitz()
        print(f"[gen_item_components] Blitz parsed: {len(blitz)} items")
        for k, v in blitz.items():
            merged_display.setdefault(k, v)
    except Exception as e:
        print("[gen_item_components] Blitz scrape failed:", e)

    nameId_map, misses = merge_to_nameId(cdragon_by_display, merged_display)
    if misses:
        print("[gen_item_components] Could not map some item names to nameId:")
        for m in sorted(set(misses))[:20]:
            print("  -", m)
        if len(misses) > 20:
            print(f"  (+{len(misses) - 20} more)")

    merge_into_file(nameId_map)


if __name__ == "__main__":
    main()
