"""Optional local-only adapter (llama.cpp via llama-cpp-python). Loads a GGUF file from disk;
it never makes network calls. Install with: pip install llama-cpp-python"""
import os


class LlamaCppAdapter:
    name = "llamacpp"

    def __init__(self, model_path, seed=0, max_tokens=64, temperature=0.0, n_ctx=1024, n_threads=None):
        from llama_cpp import Llama  # optional dependency
        self.model_path = model_path
        self.settings = {"seed": seed, "max_tokens": max_tokens, "temperature": temperature, "n_ctx": n_ctx}
        self.llm = Llama(model_path=model_path, n_ctx=n_ctx, seed=seed, verbose=False,
                         n_threads=n_threads or max(1, (os.cpu_count() or 2) // 2))

    def complete(self, system, prompt):
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        out = self.llm.create_chat_completion(messages=msgs, max_tokens=self.settings["max_tokens"],
                                              temperature=self.settings["temperature"], seed=self.settings["seed"])
        return out["choices"][0]["message"]["content"]
