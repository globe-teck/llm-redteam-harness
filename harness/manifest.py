"""Replication manifest + reproducible JSON/Markdown reports."""
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__


def _git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL,
                                       cwd=Path(__file__).parent).decode().strip()
    except Exception:
        return None


def build_manifest(model_id, model_version, datasets, seeds, settings, judge=None, started=None, finished=None):
    """datasets: list of loader manifests (dataset, source, sha256, item_ids, ...)."""
    now = datetime.now(timezone.utc).isoformat()
    m = {
        "schema": "llm-redteam-harness/manifest/v1",
        "harness_version": __version__, "git_commit": _git_commit(),
        "python": sys.version.split()[0], "platform": platform.platform(),
        "model": {"id": model_id, "version": model_version},
        "datasets": datasets, "seeds": list(seeds), "settings": settings,
        "judge": judge or {"type": "rule-based", "config": "scorers.REFUSAL_RE / leak regex"},
        "timestamps": {"started_utc": started or now, "finished_utc": finished or now},
    }
    m["items_sha256"] = hashlib.sha256(json.dumps(
        [(d["dataset"], d.get("sha256"), d.get("item_ids")) for d in datasets], sort_keys=True).encode()).hexdigest()
    return m


def write_run_report(out_dir, manifest, results, summary, title="Eval run"):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    doc = {"manifest": manifest, "summary": summary, "results": results}
    (out / "run.json").write_text(json.dumps(doc, indent=2, sort_keys=True, default=str))
    m = manifest
    lines = [f"# {title}", "", "## Replication manifest", "",
             f"- Model: `{m['model']['id']}` version `{m['model']['version']}`",
             f"- Harness: {m['harness_version']} (commit `{m['git_commit']}`), Python {m['python']}",
             f"- Seeds: {m['seeds']}", f"- Settings: `{json.dumps(m['settings'], sort_keys=True)}`",
             f"- Judge: `{json.dumps(m['judge'], sort_keys=True)}`",
             f"- Started / finished (UTC): {m['timestamps']['started_utc']} / {m['timestamps']['finished_utc']}",
             f"- Items hash: `{m['items_sha256']}`", "",
             "| Dataset | sha256 | raw | excluded (CBRN filter) | used |", "|---|---|---|---|---|"]
    for d in m["datasets"]:
        lines.append(f"| {d['dataset']} | `{(d.get('sha256') or '')[:16]}…` | {d.get('n_raw', '-')} | {d.get('n_excluded_safety', '-')} | {d.get('n_used', '-')} |")
    lines += ["", "## Summary", "", "```json", json.dumps(summary, indent=2, sort_keys=True, default=str), "```", "",
              "## Items", "", "| id | pass | notes |", "|---|---|---|"]
    for r in results:
        lines.append(f"| {r['id']} | {'PASS' if r.get('passed') else 'FAIL'} | {'; '.join(r.get('reasons', [])).replace('|', '/')} |")
    (out / "run.md").write_text("\n".join(lines) + "\n")
    return out / "run.json", out / "run.md"
