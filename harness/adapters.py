"""Model adapters. Each adapter exposes complete(system, prompt) -> str."""
import hashlib
import json
import os
import re
import time
import urllib.request


class MockAdapter:
    """Deterministic rule-based stand-in for a model.

    vulnerable=False behaves like a well-aligned assistant; vulnerable=True
    follows injected instructions and echoes secrets, so scorers can be shown
    catching failures. Latency is simulated deterministically from a hash of
    the prompt (0-latency_ms) so metrics are reproducible.
    """

    name = "mock"
    REFUSE_TRIGGERS = re.compile(
        r"ignore (all|previous|prior)|disregard|system prompt|developer mode|no rules|"
        r"pretend you have no|reveal|secret|password|api key|social security|lock ?pick",
        re.I)

    def __init__(self, vulnerable=False, latency_ms=20, fail_every=0):
        self.vulnerable = vulnerable
        self.latency_ms = latency_ms
        self.fail_every = fail_every  # raise on every Nth call to exercise retries
        self.calls = 0

    def complete(self, system, prompt):
        self.calls += 1
        if self.fail_every and self.calls % self.fail_every == 0:
            raise TimeoutError("simulated timeout")
        h = int(hashlib.sha256(prompt.encode()).hexdigest(), 16)
        if self.latency_ms:
            time.sleep((h % (self.latency_ms + 1)) / 1000)
        if self.REFUSE_TRIGGERS.search(prompt):
            if self.vulnerable:
                secret = re.search(r"[A-Z]{3,}-\d{3,}", system or "")
                return "Sure! " + (f"The secret is {secret.group(0)}." if secret else "Here you go: PWNED")
            return "I'm sorry, but I can't help with that request."
        return f"Here is a helpful answer about: {prompt[:60]}"


class OpenAICompatAdapter:
    """Chat Completions over HTTP. Configured only by environment variables:
    LLM_BASE_URL (e.g. https://api.example.com/v1), LLM_MODEL, LLM_API_KEY."""

    name = "openai"

    def __init__(self, timeout=30, env=None):
        env = os.environ if env is None else env
        self.base_url = env.get("LLM_BASE_URL", "").rstrip("/")
        self.model = env.get("LLM_MODEL", "")
        self.api_key = env.get("LLM_API_KEY", "")
        self.timeout = timeout
        if not (self.base_url and self.model):
            raise RuntimeError("set LLM_BASE_URL and LLM_MODEL (and LLM_API_KEY if required)")

    def complete(self, system, prompt):
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        body = json.dumps({"model": self.model, "messages": msgs, "temperature": 0}).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp)["choices"][0]["message"]["content"]


def get_adapter(name, **kw):
    if name == "mock":
        return MockAdapter(**kw)
    if name == "mock-vulnerable":
        return MockAdapter(vulnerable=True, **kw)
    if name == "openai":
        return OpenAICompatAdapter(**kw)
    raise ValueError(f"unknown adapter {name}")
