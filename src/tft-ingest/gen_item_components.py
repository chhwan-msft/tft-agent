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

    # Mobalytics uses nested divs with class names like:
    # parent: "m-jbp8l2 e5d3hmh5"
    # name container: direct child div with class "m-1lt86v1 e5d3hmh7" (the actual display name is in the next sibling div)
    # components container: sibling div with class "m-1d1ieym e5d3hmh4" containing <img alt="Component Name"/>
    parents = soup.select("div.m-jbp8l2.e5d3hmh5")
    print(f"[gen_item_components] Found {len(parents)} parent items in Mobalytics")
    for idx, p in enumerate(parents):
        # name marker div (contains an img and a child div with the display name)
        name_marker = p.select_one("div.m-1lt86v1.e5d3hmh7")
        if not name_marker:
            print(f"[gen_item_components] Skipping parent {idx} due to missing name marker")
            continue

        # primary name is in a child div with class like m-dll4w4 e5d3hmh3
        name_child = name_marker.select_one("div.m-dll4w4")
        if name_child and name_child.get_text(strip=True):
            item_name = name_child.get_text(strip=True)
        else:
            # fallback: remove images from name_marker and take remaining text
            for img in name_marker.find_all("img"):
                img.extract()
            item_name = name_marker.get_text(" ", strip=True)

        if not item_name:
            print(f"[gen_item_components] Skipping parent {idx} due to missing item name")
            continue

        # components container and component names from img alt attributes
        comp_div = p.select_one("div.m-1d1ieym.e5d3hmh4")
        comp_labels = []
        if comp_div:
            for img in comp_div.find_all("img", alt=True):
                alt = img.get("alt", "").strip()
                # Allow duplicates: some recipes use two of the same component (two img tags
                # with the same alt). Append every valid alt we find in document order.
                if alt and len(alt) <= 40:
                    comp_labels.append(alt)
        else:
            print(f"[gen_item_components] Skipping {item_name} due to missing components container")

        if len(comp_labels) >= 2:
            mapping[item_name] = comp_labels[:2]
        else:
            print(f"[gen_item_components] Skipping {item_name} due to insufficient components: {comp_labels}")

    return mapping


def merge_to_nameId(cdragon_by_display, recipes_by_display):
    out = {}
    missed = []
    for disp, comps in recipes_by_display.items():
        key = cdragon_by_display.get(norm(disp))
        if not key:
            missed.append(disp)
            continue
        out[key] = {"components": comps}
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
