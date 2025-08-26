import re
import asyncio

from data.retrieval.retrieval import lookup_unit, lookup_item, lookup_trait


def _format_fact(kind: str, name: str | None, payload) -> str:
    """Create a short system message line for a retrieved fact.

    payload may be a string or a dict; prefer a 'description' field when available.
    """
    if isinstance(payload, dict):
        desc = payload.get("description") or payload.get("desc") or str(payload)
    else:
        desc = str(payload)

    if name:
        return f"[{kind}] {name}: {desc}"
    return f"[{kind}] {desc}"


def extract_entities(text: str) -> set:
    """Heuristic entity extractor: returns capitalized words and multi-word title-cased phrases.

    Falls back to an empty set when nothing obvious is found.
    """
    # Match sequences like "Dragon Knight" or single capitalized words like "ChoGath"
    title_matches = re.findall(r"(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", text)
    # Match all-caps tokens (ITEM_ABBR) and mixed-case words with internal caps
    other_matches = re.findall(r"\b[A-Z][A-Za-z0-9]{2,}\b", text)

    candidates = set([m.strip() for m in title_matches + other_matches if m and len(m.strip()) >= 2])
    return candidates


async def ground_text_and_add_to_history(text: str) -> tuple[int, str]:
    """Run lookups on extracted entities (or the full text as fallback) and add a single
    SYSTEM message containing all new facts discovered.

    Returns the number of new facts added.
    """

    # Optimization: first try a global search using the entire user text. This
    # often gives accurate contextual results and avoids noisy per-token entity
    # extraction that causes unnecessary re-runs of the orchestrator.
    try:
        global_unit_hits, global_item_hits, global_trait_hits = await asyncio.gather(
            lookup_unit(text), lookup_item(text), lookup_trait(text)
        )
        # If we found anything with the global query, use those results and skip
        # the per-entity lookups.
        if global_unit_hits or global_item_hits or global_trait_hits:
            unit_facts = global_unit_hits or []
            item_facts = global_item_hits or []
            trait_facts = global_trait_hits or []
            print(
                f"[grounding] Used global search: unit_facts={len(unit_facts)} item_facts={len(item_facts)} trait_facts={len(trait_facts)}"
            )
        else:
            candidates = extract_entities(text)
            if not candidates:
                # fallback to using the whole text if no entities found
                candidates = {text}

            # Fallback: per-entity lookups when global search returns nothing.
            unit_hits_lists = await asyncio.gather(*[lookup_unit(u) for u in candidates]) if candidates else []
            item_hits_lists = await asyncio.gather(*[lookup_item(i) for i in candidates]) if candidates else []
            trait_hits_lists = await asyncio.gather(*[lookup_trait(t) for t in candidates]) if candidates else []

            # Flatten and remove falsy/empty inner lists
            unit_facts = [h for sub in unit_hits_lists for h in (sub or [])]
            item_facts = [h for sub in item_hits_lists for h in (sub or [])]
            trait_facts = [h for sub in trait_hits_lists for h in (sub or [])]
            print(
                f"[grounding] Found {len(candidates)} candidates: unit_facts={len(unit_facts)} item_facts={len(item_facts)} trait_facts={len(trait_facts)}"
            )
    except Exception as e:
        # On any error in retrieval, fall back to empty lists (best-effort)
        print(f"[grounding] retrieval error: {e}")
        unit_facts = []
        item_facts = []
        trait_facts = []

    combined_lines = []
    added = 0

    for u in unit_facts:
        name = u.get("name") if isinstance(u, dict) else None
        combined_lines.append(_format_fact("unit", name, u))
        added += 1
    for it in item_facts:
        name = it.get("name") if isinstance(it, dict) else None
        combined_lines.append(_format_fact("item", name, it))
        added += 1
    for t in trait_facts:
        name = t.get("name") if isinstance(t, dict) else None
        combined_lines.append(_format_fact("trait", name, t))
        added += 1

    combined = None
    if combined_lines:
        # Combine into a single system message per grounding step
        combined = "Retrieved facts:\n" + "\n".join(combined_lines)

    return (added, combined)
