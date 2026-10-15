"""JSON and Markdown report writers."""
import json
from pathlib import Path


def to_markdown(report, title="LLM red-team report"):
    s = report["summary"]
    lines = [f"# {title}", "",
             f"- Adapter: `{report.get('adapter', '?')}`  Suite: `{report.get('suite', '?')}`",
             f"- Passed: **{s['passed']}/{s['total']}** ({s['pass_rate']:.0%})  Errors: {s['errors']}  Retries: {s['retries']}",
             f"- Latency ms: p50 {s['latency_ms']['p50']} · p95 {s['latency_ms']['p95']} · max {s['latency_ms']['max']}",
             f"- Wall: {s['wall_s']}s · Throughput: {s['throughput_rps']} req/s · Concurrency: {s['concurrency']}",
             "", "| Category | Passed | Total |", "|---|---|---|"]
    for cat, c in sorted(s["by_category"].items()):
        lines.append(f"| {cat} | {c['passed']} | {c['total']} |")
    lines += ["", "| Case | Category | Expect | Result | Latency ms | Notes |", "|---|---|---|---|---|---|"]
    for r in report["results"]:
        ms = f"{r['latency_ms']:.1f}" if r["latency_ms"] is not None else "-"
        notes = "; ".join(r["reasons"]).replace("|", "\\|")
        lines.append(f"| {r['id']} | {r['category']} | {r['expect']} | {'PASS' if r['passed'] else 'FAIL'} | {ms} | {notes} |")
    return "\n".join(lines) + "\n"


def write_reports(report, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2))
    (out / "report.md").write_text(to_markdown(report))
    return out / "report.json", out / "report.md"
