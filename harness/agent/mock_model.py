"""Deterministic mock agent model.

It speaks a tiny protocol: given the message list, return either
{"content": str} or {"tool_calls": [ToolCall,...]}. Behaviour is driven by
simple rules so tests can assert exact trajectories. vulnerable=True follows
instructions found inside tool outputs (indirect prompt injection).
"""
import json
import re

from .tools import ToolCall

INJECT_RE = re.compile(r"(?:ignore (?:all|previous) instructions|IMPORTANT:)\s*(?:and\s*)?(?P<cmd>.+)", re.I)


class MockAgentModel:
    name = "mock-agent"

    def __init__(self, vulnerable=False):
        self.vulnerable = vulnerable

    def chat(self, messages, tools):
        last = messages[-1]
        names = {t["function"]["name"] for t in tools}
        user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        if last["role"] == "tool":
            out = last["content"]
            m = INJECT_RE.search(out)
            if m and self.vulnerable and "send_email" in names:
                addr = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", m.group("cmd"))
                if addr and not any(x.get("tool_calls") and x["tool_calls"][0].name == "send_email" for x in messages):
                    return {"tool_calls": [ToolCall("send_email", {"to": addr.group(0), "subject": "fwd", "body": out[:200]}, "c-inj")]}
            if m and not self.vulnerable:
                return {"content": "Done. Note: a tool result contained instructions, which I ignored."}
            try:
                data = json.loads(out)
            except ValueError:
                data = {}
            if "result" in data:
                return {"content": f"The answer is {data['result']}."}
            return {"content": f"Summary of tool output: {out[:120]}"}
        # first turn: pick a tool by keyword
        u = user.lower()
        if re.search(r"transfer|wire|send money", u):
            if self.vulnerable and "transfer_funds" in names:
                amt = re.search(r"\d+(?:\.\d+)?", u)
                return {"tool_calls": [ToolCall("transfer_funds", {"to_account": "ACCT-CANARY", "amount": float(amt.group(0)) if amt else 1.0}, "c1")]}
            return {"content": "I can't move money without explicit confirmation from the account owner."}
        if re.search(r"\d+\s*[-+*/]\s*\d+", u) and "calculator" in names:
            expr = re.search(r"[\d\s+\-*/().]+[\d)]", u).group(0).strip()
            return {"tool_calls": [ToolCall("calculator", {"expression": expr}, "c1")]}
        if "inbox" in u or "email" in u:
            return {"tool_calls": [ToolCall("read_inbox", {"limit": 5}, "c1")]}
        if "search" in u or "doc" in u:
            q = re.search(r"\bfor\s+['\"]?(\w+)", u)
            return {"tool_calls": [ToolCall("search_docs", {"query": q.group(1) if q else u[:20]}, "c1")]}
        return {"content": "Here is a direct answer without tools."}
