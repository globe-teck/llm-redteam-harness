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
    args = ap.parse_args(argv)

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


if __name__ == "__main__":
    sys.exit(main())
