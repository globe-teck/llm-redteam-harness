"""Load test cases from YAML or JSONL."""
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CATEGORIES = {"prompt_injection", "jailbreak", "pii_leak", "benign"}
EXPECTS = {"refuse", "comply"}


@dataclass
class Case:
    id: str
    category: str
    prompt: str
    expect: str = "comply"
    system: str = ""
    leak_patterns: list = field(default_factory=list)
    must_contain: list = field(default_factory=list)


def _validate(raw):
    for key in ("id", "category", "prompt"):
        if key not in raw:
            raise ValueError(f"case missing '{key}': {raw}")
    if raw["category"] not in CATEGORIES:
        raise ValueError(f"{raw['id']}: unknown category {raw['category']}")
    if raw.get("expect", "comply") not in EXPECTS:
        raise ValueError(f"{raw['id']}: expect must be one of {sorted(EXPECTS)}")
    return Case(**{k: raw[k] for k in raw if k in Case.__dataclass_fields__})


def load_suite(path):
    path = Path(path)
    text = path.read_text()
    if path.suffix == ".jsonl":
        raws = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        data = yaml.safe_load(text) or {}
        raws = data.get("cases", data) if isinstance(data, dict) else data
    cases = [_validate(r) for r in raws]
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids")
    return cases
