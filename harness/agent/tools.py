"""Tool-call schemas and a deterministic simulated tool environment.

Nothing here touches the network or the filesystem: every tool is a pure
function over an in-memory state dict, so episodes are reproducible.
"""
import copy
import json
from dataclasses import dataclass, field

_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
          "array": list, "object": dict}


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict                 # JSON-schema subset: {"type":"object","properties":..,"required":[..]}
    fn: object = None                # fn(state, **args) -> str|dict
    side_effect: bool = False        # True for tools that change the world (send, pay, delete)

    def schema(self):
        """OpenAI-style function schema (for adapters that support tool calling)."""
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                                                 "parameters": self.parameters}}


@dataclass
class ToolCall:
    name: str
    arguments: dict = field(default_factory=dict)
    id: str = ""


def validate_args(spec, args):
    """Return a list of validation errors (empty if valid)."""
    errs = []
    if not isinstance(args, dict):
        return ["arguments must be an object"]
    props = spec.parameters.get("properties", {})
    for req in spec.parameters.get("required", []):
        if req not in args:
            errs.append(f"missing required argument '{req}'")
    for k, v in args.items():
        if k not in props:
            if spec.parameters.get("additionalProperties", False) is False:
                errs.append(f"unexpected argument '{k}'")
            continue
        t = props[k].get("type")
        if t and not isinstance(v, _TYPES[t]) or (t in ("integer", "number") and isinstance(v, bool)):
            errs.append(f"argument '{k}' should be {t}")
        if "enum" in props[k] and v not in props[k]["enum"]:
            errs.append(f"argument '{k}' not in {props[k]['enum']}")
    return errs


class SimulatedToolEnv:
    """Holds tool specs plus mutable world state; logs every call."""

    def __init__(self, tools, state=None):
        self.tools = {t.name: t for t in tools}
        self.initial_state = copy.deepcopy(state or {})
        self.reset()

    def reset(self):
        self.state = copy.deepcopy(self.initial_state)
        self.log = []

    def schemas(self):
        return [t.schema() for t in self.tools.values()]

    def call(self, tc):
        spec = self.tools.get(tc.name)
        if spec is None:
            out = {"error": f"unknown tool '{tc.name}'"}
        else:
            errs = validate_args(spec, tc.arguments)
            out = {"error": "; ".join(errs)} if errs else spec.fn(self.state, **tc.arguments)
        self.log.append({"name": tc.name, "arguments": tc.arguments, "output": out,
                         "side_effect": bool(spec and spec.side_effect and "error" not in (out if isinstance(out, dict) else {}))})
        return out if isinstance(out, str) else json.dumps(out, sort_keys=True)


# ---- a small default world: inbox, documents, fake payments (all canary data) ----

def _read_inbox(state, limit=5):
    return {"emails": state["inbox"][:limit]}


def _search_docs(state, query):
    q = query.lower()
    return {"results": [d for d in state["docs"] if q in d["title"].lower() or q in d["body"].lower()]}


def _send_email(state, to, subject, body):
    state.setdefault("sent", []).append({"to": to, "subject": subject, "body": body})
    return {"status": "sent", "to": to}


def _transfer_funds(state, to_account, amount):
    state.setdefault("transfers", []).append({"to_account": to_account, "amount": amount})
    return {"status": "ok"}


def _calc(state, expression):
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        return {"error": "only arithmetic allowed"}
    return {"result": eval(expression, {"__builtins__": {}})}  # noqa: S307 - charset restricted above


DEFAULT_TOOLS = [
    ToolSpec("read_inbox", "Read recent emails.", {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []}, _read_inbox),
    ToolSpec("search_docs", "Search internal documents.", {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}, _search_docs),
    ToolSpec("send_email", "Send an email.", {"type": "object", "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}, "required": ["to", "subject", "body"]}, _send_email, side_effect=True),
    ToolSpec("transfer_funds", "Move money (simulated).", {"type": "object", "properties": {"to_account": {"type": "string"}, "amount": {"type": "number"}}, "required": ["to_account", "amount"]}, _transfer_funds, side_effect=True),
    ToolSpec("calculator", "Evaluate arithmetic.", {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}, _calc),
]


def default_env(inbox=None, docs=None):
    return SimulatedToolEnv(DEFAULT_TOOLS, {"inbox": inbox or [], "docs": docs or []})
