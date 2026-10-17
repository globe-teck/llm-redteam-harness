"""Mandatory exclusion filter for chemical, biological, radiological, nuclear and other WMD items.

This filter is applied by load_benchmark() by default and cannot be turned off from the CLI.
It matches on category labels first and also screens prompt text with a keyword list,
so mis-labelled items are dropped too. False positives (dropping a harmless item) are acceptable;
false negatives are not.
"""
import re

EXCLUDED_CATEGORY_RE = re.compile(
    r"chem|bio|wmd|weapon[s_ ]of[ _]mass|cbrn|radiolog|nuclear|pathogen|toxin|explosive", re.I)

_TEXT_RE = re.compile(
    r"\b(nerve agent|sarin|vx\b|tabun|novichok|mustard gas|ricin|anthrax|botulinum|smallpox|"
    r"pathogen|bioweapon|biological weapon|chemical weapon|gain[- ]of[- ]function|enrich(?:ed|ing)? uranium|"
    r"dirty bomb|nuclear (?:weapon|device)|weaponi[sz]|toxin synthesis|precursor chemicals?|"
    r"synthesi[sz]e .{0,40}(?:toxin|agent|virus)|culture .{0,30}(?:bacteria|virus))", re.I)


def is_excluded(item):
    cats = " ".join(str(c) for c in (item.category, item.subcategory) if c)
    if EXCLUDED_CATEGORY_RE.search(cats):
        return True, f"category:{cats}"
    if _TEXT_RE.search(item.prompt or ""):
        return True, "keyword"
    return False, ""


def apply_safety_filter(items):
    kept, dropped = [], []
    for it in items:
        ex, why = is_excluded(it)
        (dropped if ex else kept).append((it, why) if ex else it)
    return kept, [{"id": it.id, "reason": why} for it, why in dropped]
