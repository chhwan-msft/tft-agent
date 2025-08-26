import re
import json
import asyncio
from .retrieval import lookup_unit, lookup_item, lookup_trait

# Simple in-memory cache of facts added to the chat history this session to avoid duplicates
seen_facts = set()


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


async def ground_text_and_add_to_history(text: str, seen: set) -> int:
    """Run lookups on extracted entities (or the full text as fallback) and add a single
    SYSTEM message containing all new facts discovered.

    Returns the number of new facts added.
    """
    candidates = extract_entities(text)
    if not candidates:
        # fallback to using the whole text if no entities found
        candidates = {text}

    unit_hits = await asyncio.gather(*[lookup_unit(u) for u in candidates]) if candidates else []
    item_hits = await asyncio.gather(*[lookup_item(i) for i in candidates]) if candidates else []
    trait_hits = await asyncio.gather(*[lookup_trait(t) for t in candidates]) if candidates else []

    # Filter out falsy results
    unit_facts = [h for h in unit_hits if h]
    item_facts = [h for h in item_hits if h]
    trait_facts = [h for h in trait_hits if h]

    # Debug logs: counts and small samples to inspect shapes
    try:
        print(
            f"[grounding] candidates={len(candidates)} unit_hits={len(unit_hits)} item_hits={len(item_hits)} trait_hits={len(trait_hits)}"
        )
        # Print first 3 entries of each (pretty JSON)
        if unit_facts:
            print("[grounding] unit_facts sample:", json.dumps(unit_facts[:3], ensure_ascii=False, indent=2))
        if item_facts:
            print("[grounding] item_facts sample:", json.dumps(item_facts[:3], ensure_ascii=False, indent=2))
        if trait_facts:
            print("[grounding] trait_facts sample:", json.dumps(trait_facts[:3], ensure_ascii=False, indent=2))
    except Exception as e:
        # Best-effort logging; don't crash on logging errors
        print(f"[grounding] logging error: {e}")

    combined_lines = []
    for u in unit_facts:
        name = u.get("name") if isinstance(u, dict) else None
        combined_lines.append(_format_fact("unit", name, u))
    for it in item_facts:
        name = it.get("name") if isinstance(it, dict) else None
        combined_lines.append(_format_fact("item", name, it))
    for t in trait_facts:
        name = t.get("name") if isinstance(t, dict) else None
        combined_lines.append(_format_fact("trait", name, t))

    combined = None
    if combined_lines:
        combined = "Retrieved facts:\n" + "\n".join(combined_lines)

    return combined


if __name__ == "__main__":
    # Simple CLI for manual testing: pass the question as an argument or via stdin
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Run ground_text_and_add_to_history(question) and print JSON result")
    parser.add_argument("question", nargs="?", help="Question to ground; if omitted, read from stdin")
    args = parser.parse_args()

    if args.question:
        question_text = args.question
    else:
        question_text = sys.stdin.read().strip()

    if not question_text:
        print("No question provided. Provide a question as an argument or via stdin.")
        sys.exit(2)

    result = asyncio.run(ground_text_and_add_to_history(question_text, seen_facts))
    # Print pretty JSON
    print(json.dumps(result, ensure_ascii=False, indent=2))
