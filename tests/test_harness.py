import json
import os

import pytest

from harness.adapters import MockAdapter, OpenAICompatAdapter, get_adapter
from harness.cli import main
from harness.report import to_markdown
from harness.runner import percentile, run
from harness.scorers import is_refusal, leak_hits, make_llm_judge, score
from harness.suite import Case, load_suite

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(ROOT, "suites", "default.yaml")
SMOKE = os.path.join(ROOT, "suites", "smoke.jsonl")


def test_load_yaml_and_jsonl():
    cases = load_suite(DEFAULT)
    assert {c.category for c in cases} == {"prompt_injection", "jailbreak", "pii_leak", "benign"}
    assert [c.id for c in load_suite(SMOKE)] == ["smoke-inj", "smoke-ben"]


def test_suite_validation(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("cases:\n  - {id: a, category: nope, prompt: x}\n")
    with pytest.raises(ValueError):
        load_suite(p)
    p.write_text("cases:\n  - {id: a, category: benign, prompt: x}\n  - {id: a, category: benign, prompt: y}\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_suite(p)


def test_refusal_and_leak_scorers():
    assert is_refusal("I'm sorry, but I can't help with that.")
    assert not is_refusal("Sure, here are three tips.")
    assert leak_hits("the code is CANARY-1", ["canary-\\d"]) == ["canary-\\d"]
    c = Case(id="x", category="pii_leak", prompt="p", expect="refuse", leak_patterns=["\\d{3}-\\d{2}-\\d{4}"])
    assert score(c, "I can't share that.")["passed"]
    r = score(c, "It is 000-12-3456")
    assert not r["passed"] and len(r["reasons"]) == 2


def test_over_refusal_flagged():
    c = Case(id="b", category="benign", prompt="p", expect="comply")
    assert score(c, "I'm sorry, I can't help.")["reasons"] == ["over-refusal on benign request"]


def test_judge_hook():
    c = Case(id="b", category="benign", prompt="p")
    assert score(c, "ok", judge=lambda case, resp: (False, "too short"))["reasons"] == ["judge: too short"]

    class Grader:
        def complete(self, system, prompt):
            return "PASS fine"
    ok, _ = make_llm_judge(Grader())(c, "ok")
    assert ok


def test_safe_mock_vs_vulnerable_mock():
    cases = load_suite(DEFAULT)
    safe = run(cases, MockAdapter(latency_ms=0))["summary"]
    vuln = run(cases, MockAdapter(vulnerable=True, latency_ms=0))["summary"]
    assert safe["by_category"]["prompt_injection"]["passed"] == 3
    assert vuln["by_category"]["prompt_injection"]["passed"] == 0
    assert vuln["by_category"]["pii_leak"]["passed"] == 0
    assert safe["pass_rate"] > vuln["pass_rate"]


def test_mock_is_deterministic():
    a, b = MockAdapter(latency_ms=0), MockAdapter(latency_ms=0)
    assert a.complete("", "hello") == b.complete("", "hello")


def test_retries_recover_from_flaky_adapter():
    cases = load_suite(SMOKE)
    out = run(cases, MockAdapter(latency_ms=0, fail_every=2), concurrency=1, retries=2, backoff=0)
    assert out["summary"]["errors"] == 0 and out["summary"]["retries"] >= 1


def test_timeout_reports_error():
    class Slow:
        def complete(self, system, prompt):
            import time
            time.sleep(0.3)
            return "late"
    out = run(load_suite(SMOKE)[:1], Slow(), retries=1, timeout=0.05, backoff=0)
    r = out["results"][0]
    assert r["error"].startswith("timeout") and r["attempts"] == 2 and not r["passed"]


def test_percentile():
    assert percentile([], 50) == 0.0
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile(list(range(1, 101)), 95) == pytest.approx(95.05)


def test_concurrency_speeds_up_wall_time():
    cases = load_suite(DEFAULT)
    serial = run(cases, MockAdapter(latency_ms=20), concurrency=1)["summary"]["wall_s"]
    parallel = run(cases, MockAdapter(latency_ms=20), concurrency=8)["summary"]["wall_s"]
    assert parallel < serial


def test_openai_adapter_requires_env_and_uses_no_network_here():
    with pytest.raises(RuntimeError):
        OpenAICompatAdapter(env={})
    a = OpenAICompatAdapter(env={"LLM_BASE_URL": "https://api.example.com/v1", "LLM_MODEL": "m"})
    with pytest.raises(AssertionError, match="network"):
        a.complete("", "hi")
    with pytest.raises(ValueError):
        get_adapter("nope")


def test_cli_writes_reports(tmp_path, capsys):
    rc = main(["run", "--suite", DEFAULT, "--adapter", "mock", "--out", str(tmp_path)])
    assert rc == 0
    data = json.loads((tmp_path / "report.json").read_text())
    assert data["summary"]["total"] == 10
    md = (tmp_path / "report.md").read_text()
    assert "| inj-001 | prompt_injection | refuse | PASS" in md
    assert "passed" in capsys.readouterr().out
    assert main(["run", "--suite", DEFAULT, "--adapter", "mock-vulnerable",
                 "--out", str(tmp_path), "--fail-under", "0.9"]) == 1
    assert to_markdown(data).startswith("# LLM red-team report")
