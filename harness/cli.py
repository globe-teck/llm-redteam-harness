"""Command-line interface: python3 -m harness run --suite suites/default.yaml --adapter mock"""
import argparse
import sys

from .adapters import get_adapter
from .report import write_reports
from .runner import run
from .scorers import make_llm_judge
from .suite import load_suite


def main(argv=None):
    ap = argparse.ArgumentParser(prog="harness", description="Small LLM eval and red-team harness.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a suite against an adapter")
    r.add_argument("--suite", default="suites/default.yaml", help="YAML or JSONL suite file")
    r.add_argument("--adapter", default="mock", choices=["mock", "mock-vulnerable", "openai"])
    r.add_argument("--judge", choices=["mock", "openai"], help="optional LLM-as-judge adapter")
    r.add_argument("--concurrency", type=int, default=4)
    r.add_argument("--retries", type=int, default=2)
    r.add_argument("--timeout", type=float, default=30.0, help="per-call timeout in seconds")
    r.add_argument("--out", default="reports", help="output directory for report.json / report.md")
    r.add_argument("--fail-under", type=float, default=None, help="exit 1 if pass rate is below this (0-1)")
    a = sub.add_parser("agent", help="run multi-turn tool-use tasks against the offline mock agent")
    a.add_argument("--suite", default="suites/agent.yaml")
    a.add_argument("--model", default="mock-agent", choices=["mock-agent", "mock-agent-vulnerable"])
    a.add_argument("--out", default="reports/agent")
    d = sub.add_parser("dataset", help="download a public benchmark, apply the CBRN filter, print the manifest")
    d.add_argument("name")
    d.add_argument("--path", help="local file (required for gated datasets)")
    d.add_argument("--limit", type=int)
    args = ap.parse_args(argv)
    if args.cmd == "agent":
        return _agent(args)
    if args.cmd == "dataset":
        import json
        from .datasets import load_benchmark
        items, man = load_benchmark(args.name, path=args.path, limit=args.limit)
        man = {k: v for k, v in man.items() if k not in ("item_ids", "excluded_ids")}
        print(json.dumps(man, indent=2))
        return 0

    cases = load_suite(args.suite)
    adapter = get_adapter(args.adapter)
    judge = make_llm_judge(get_adapter(args.judge)) if args.judge else None
    report = run(cases, adapter, concurrency=args.concurrency, retries=args.retries,
                 timeout=args.timeout, judge=judge)
    report.update(adapter=args.adapter, suite=args.suite)
    j, m = write_reports(report, args.out)
    s = report["summary"]
    print(f"{s['passed']}/{s['total']} passed ({s['pass_rate']:.0%}) | p50 {s['latency_ms']['p50']}ms "
          f"p95 {s['latency_ms']['p95']}ms | {s['throughput_rps']} req/s | wrote {j} and {m}")
    if args.fail_under is not None and s["pass_rate"] < args.fail_under:
        return 1
    return 0


def _agent(args):
    from .agent import MockAgentModel
    from .agent.loop import load_agent_tasks, run_agent_suite
    from .manifest import build_manifest, write_run_report
    from .datasets import sha256_file
    from datetime import datetime, timezone
    t0 = datetime.now(timezone.utc).isoformat()
    tasks = load_agent_tasks(args.suite)
    rep = run_agent_suite(MockAgentModel(vulnerable=args.model.endswith("vulnerable")), tasks)
    man = build_manifest(args.model, "builtin", [{"dataset": args.suite, "sha256": sha256_file(args.suite),
                         "item_ids": [t.id for t in tasks]}], seeds=[0], settings={"deterministic": True},
                         started=t0)
    j, m = write_run_report(args.out, man, rep["results"], rep["summary"], title="Agent tool-use run")
    s = rep["summary"]
    print(f"{s['passed']}/{s['total']} agent tasks passed | wrote {j} and {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
