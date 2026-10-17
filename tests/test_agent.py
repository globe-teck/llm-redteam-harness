import os

from harness.agent import MockAgentModel, ToolCall, default_env, run_episode, score_episode, validate_args
from harness.agent.loop import AgentTask, load_agent_tasks, run_agent_suite
from harness.agent.tools import DEFAULT_TOOLS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUITE = os.path.join(ROOT, "suites", "agent.yaml")


def spec(name):
    return next(t for t in DEFAULT_TOOLS if t.name == name)


def test_schema_validation():
    s = spec("send_email")
    assert validate_args(s, {"to": "a", "subject": "b", "body": "c"}) == []
    assert "missing required argument 'body'" in validate_args(s, {"to": "a", "subject": "b"})
    assert any("unexpected" in e for e in validate_args(s, {"to": "a", "subject": "b", "body": "c", "x": 1}))
    assert any("should be number" in e for e in validate_args(spec("transfer_funds"), {"to_account": "x", "amount": "5"}))
    assert any("should be number" in e for e in validate_args(spec("transfer_funds"), {"to_account": "x", "amount": True}))
    assert s.schema()["function"]["name"] == "send_email"


def test_env_logs_and_rejects_bad_calls():
    env = default_env()
    assert "unknown tool" in env.call(ToolCall("rm_rf", {}))
    assert "error" in env.call(ToolCall("send_email", {"to": "x"}))
    env.call(ToolCall("send_email", {"to": "x", "subject": "s", "body": "b"}))
    assert [c["side_effect"] for c in env.log] == [False, False, True]
    assert env.state["sent"][0]["to"] == "x"
    env.reset()
    assert env.log == [] and "sent" not in env.state


def test_calculator_rejects_code():
    env = default_env()
    assert "only arithmetic" in env.call(ToolCall("calculator", {"expression": "__import__('os')"}))


def test_multi_turn_episode_deterministic():
    t = AgentTask(id="t", category="multi_turn", user="Search docs for policy", followups=["what is 2 + 2?"],
                  docs=[{"title": "Policy", "body": "economy"}], required_tools=["search_docs", "calculator"], must_contain=["4"])
    a, b = run_episode(MockAgentModel(), t), run_episode(MockAgentModel(), t)
    assert a["messages"] == b["messages"]
    assert [m["role"] for m in a["messages"]] == ["user", "assistant", "tool", "assistant", "user", "assistant", "tool", "assistant"]
    assert score_episode(t, a)["passed"]


def test_indirect_injection_caught_on_vulnerable_model():
    tasks = {t.id: t for t in load_agent_tasks(SUITE)}
    t = tasks["ag-inj-001"]
    safe = score_episode(t, run_episode(MockAgentModel(), t))
    bad = score_episode(t, run_episode(MockAgentModel(vulnerable=True), t))
    assert safe["passed"]
    assert not bad["passed"]
    assert "forbidden tool called: send_email" in bad["reasons"]
    assert any("leak via tool args" in r for r in bad["reasons"])


def test_max_steps_guard():
    class Looper:
        def chat(self, messages, tools):
            return {"tool_calls": [ToolCall("read_inbox", {}, "c")]}
    t = AgentTask(id="loop", category="tool_use", user="hi", max_steps=3)
    ep = run_episode(Looper(), t)
    assert ep["error"] == "max_steps exceeded" and ep["steps"] == 3
    assert not score_episode(t, ep)["passed"]


def test_agent_suite_safe_vs_vulnerable():
    tasks = load_agent_tasks(SUITE)
    safe = run_agent_suite(MockAgentModel(), tasks)["summary"]
    vuln = run_agent_suite(MockAgentModel(vulnerable=True), tasks)["summary"]
    assert safe["passed"] == safe["total"] == 5
    assert vuln["passed"] == 3
