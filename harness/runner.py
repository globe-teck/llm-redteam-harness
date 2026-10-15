"""Concurrent runner with retries, timeouts and latency metrics."""
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout

from .scorers import score


def percentile(values, pct):
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _call_with_retries(adapter, case, retries, timeout, backoff):
    attempts, last_err = 0, None
    with ThreadPoolExecutor(max_workers=1) as one:
        for attempt in range(retries + 1):
            attempts += 1
            t0 = time.perf_counter()
            fut = one.submit(adapter.complete, case.system, case.prompt)
            try:
                out = fut.result(timeout=timeout)
                return out, (time.perf_counter() - t0) * 1000, attempts, None
            except FutTimeout:
                last_err = f"timeout after {timeout}s"
            except Exception as e:  # adapter error: retry
                last_err = f"{type(e).__name__}: {e}"
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
    return None, None, attempts, last_err


def run(cases, adapter, concurrency=4, retries=2, timeout=30.0, backoff=0.05, judge=None):
    def one(case):
        resp, ms, attempts, err = _call_with_retries(adapter, case, retries, timeout, backoff)
        if err:
            res = {"passed": False, "refused": False, "reasons": [f"error: {err}"]}
        else:
            res = score(case, resp, judge)
        return {"id": case.id, "category": case.category, "expect": case.expect,
                "response": resp, "latency_ms": ms, "attempts": attempts, "error": err, **res}

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        results = list(pool.map(one, cases))
    wall = time.perf_counter() - t0
    return {"results": results, "summary": summarize(results, wall, concurrency)}


def summarize(results, wall_s, concurrency):
    lat = [r["latency_ms"] for r in results if r["latency_ms"] is not None]
    by_cat = {}
    for r in results:
        c = by_cat.setdefault(r["category"], {"total": 0, "passed": 0})
        c["total"] += 1
        c["passed"] += r["passed"]
    n = len(results)
    return {
        "total": n,
        "passed": sum(r["passed"] for r in results),
        "errors": sum(1 for r in results if r["error"]),
        "retries": sum(r["attempts"] - 1 for r in results),
        "pass_rate": round(sum(r["passed"] for r in results) / n, 4) if n else 0.0,
        "by_category": by_cat,
        "latency_ms": {"p50": round(percentile(lat, 50), 2), "p95": round(percentile(lat, 95), 2),
                       "max": round(max(lat), 2) if lat else 0.0},
        "wall_s": round(wall_s, 3),
        "throughput_rps": round(n / wall_s, 2) if wall_s else 0.0,
        "concurrency": concurrency,
    }
