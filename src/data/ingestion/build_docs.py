import json


def unit_to_doc(u: dict):
    traits = u.get("traits", [])
    trait_ids = [t.get("id") for t in traits if isinstance(t, dict) and t.get("id")]
    trait_names = [t.get("name") for t in traits if isinstance(t, dict) and t.get("name")]
    traits_str = ", ".join(trait_names)

    content = f"{u['display_name']} (Unit). Tier {u.get('tier') or u.get('cost')}. Traits: {traits_str}."
    return {
        "id": u.get("character_id"),
        "entity_type": "unit",
        "set_id": u.get("set_id", "TFTSet15"),
        "name": u.get("display_name"),
        "tier": u.get("tier") or u.get("cost"),
        "trait_ids": trait_ids,
        "trait_names": trait_names,
        "traits_json": json.dumps(traits, ensure_ascii=False),
        "url": u.get("source_url"),
        "content": content,
    }


def trait_to_doc(t: dict):
    cps = t.get("conditional_trait_sets", [])
    bps = []
    mins = []
    for c in cps:
        mn = c.get("min_units")
        mx = c.get("max_units") if "max_units" in c else None
        st = c.get("style_name") or c.get("style")
        if mn is not None:
            mins.append(mn)
        bps.append({"min": mn, "max": mx, "style": st})

    bp_str_parts = []
    for bp in bps:
        rng = f"{bp['min']}+" if bp["max"] in (None, 0) else f"{bp['min']}-{bp['max']}"
        bp_str_parts.append(f"{rng} {bp['style']}")
    bp_str = " | ".join(bp_str_parts) if bp_str_parts else ""

    content = f"{t.get('display_name')} (Trait)."
    if bp_str:
        content += f" Breakpoints: {bp_str}."
    if t.get("tooltip_text"):
        content += f" Tooltip: {t['tooltip_text']}"

    return {
        "id": t.get("trait_id"),
        "entity_type": "trait",
        "set_id": t.get("set", "TFTSet15"),
        "name": t.get("display_name"),
        "breakpoints_json": json.dumps(bps, ensure_ascii=False),
        "min_units": mins,
        "url": t.get("source_url"),
        "content": content,
    }


def item_to_doc(i: dict):
    comps = i.get("components", [])
    comps_str = ", ".join(comps)
    content = f"{i.get('name')} (Item)."
    if comps:
        content += f" Components: {comps_str}."
    return {
        "id": i.get("nameId") or i.get("id"),
        "entity_type": "item",
        "set_id": i.get("set_id", "TFTSet15"),
        "name": i.get("name"),
        "components": comps,
        "url": i.get("source_url"),
        "content": content,
    }
