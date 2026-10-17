"""Statistics for comparing eval runs (stdlib only, seeded, deterministic).

Data model: scores[family][run] -> list of per-item 0/1 (or float) scores, aligned by item
across runs. A *family* is a group of items (e.g. a benchmark category).

Regression rule (all three must hold):
  * mean drop of >= 3 percentage points (candidate vs baseline),
  * Holm-corrected one-sided p < 0.05 across families,
  * at least 3 runs on each side.
"""
import math
import random
from statistics import mean

MIN_DROP_PTS = 3.0
ALPHA = 0.05
MIN_RUNS = 3


def run_means(runs):
    return [mean(r) for r in runs]


def bootstrap_ci(values, n_boot=2000, level=0.95, seed=0, stat=mean):
    """Percentile bootstrap CI of stat(values)."""
    rng = random.Random(seed)
    v = list(values)
    if not v:
        return (float("nan"), float("nan"))
    boots = sorted(stat([rng.choice(v) for _ in v]) for _ in range(n_boot))
    lo = boots[int((1 - level) / 2 * n_boot)]
    hi = boots[min(n_boot - 1, int((1 + level) / 2 * n_boot))]
    return (lo, hi)


def paired_permutation_p(base_runs, cand_runs, n_perm=5000, seed=0):
    """One-sided p-value for H1: candidate < baseline.

    Uses per-item means across runs, then a paired sign-flip permutation test on the
    item-level differences (exact if 2^n <= n_perm)."""
    b = [mean(col) for col in zip(*base_runs)]
    c = [mean(col) for col in zip(*cand_runs)]
    d = [bi - ci for bi, ci in zip(b, c)]
    obs = sum(d)
    nz = [x for x in d if x != 0]
    if not nz:
        return 1.0
    n = len(nz)
    if 2 ** n <= n_perm:
        count = total = 0
        for mask in range(2 ** n):
            s = sum(x if (mask >> i) & 1 else -x for i, x in enumerate(nz))
            count += s >= obs - 1e-12
            total += 1
        return count / total
    rng = random.Random(seed)
    count = sum(1 for _ in range(n_perm) if sum(x if rng.random() < 0.5 else -x for x in nz) >= obs - 1e-12)
    return (count + 1) / (n_perm + 1)


def holm(pvals):
    """Holm-Bonferroni adjusted p-values (same order as input)."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj, running = [0.0] * m, 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvals[i]))
        adj[i] = running
    return adj


def detect_regressions(base, cand, min_drop=MIN_DROP_PTS, alpha=ALPHA, min_runs=MIN_RUNS, seed=0, families=None):
    """base/cand: {family: [run_scores, ...]}. Returns {family: {...}}."""
    fams = sorted(families if families is not None else (set(base) & set(cand)))
    rows, ps = {}, []
    for f in fams:
        bm, cm = run_means(base[f]), run_means(cand[f])
        drop = (mean(bm) - mean(cm)) * 100
        p = paired_permutation_p(base[f], cand[f], seed=seed)
        rows[f] = {"base_mean": mean(bm), "cand_mean": mean(cm), "drop_pts": drop, "p": p,
                   "n_runs": (len(base[f]), len(cand[f])), "n_items": len(base[f][0]),
                   "ci_drop_pts": tuple(x * 100 for x in bootstrap_ci(
                       [mean(b) - mean(c) for b, c in zip(zip(*base[f]), zip(*cand[f]))], seed=seed))}
        ps.append(p)
    for f, pa in zip(fams, holm(ps)):
        r = rows[f]
        r["p_holm"] = pa
        enough = min(r["n_runs"]) >= min_runs
        r["regression"] = bool(enough and r["drop_pts"] >= min_drop and pa < alpha)
        r["insufficient_runs"] = not enough
    return rows


def precision_recall(predicted, truth):
    predicted, truth = set(predicted), set(truth)
    tp = len(predicted & truth)
    prec = tp / len(predicted) if predicted else (1.0 if not truth else 0.0)
    rec = tp / len(truth) if truth else 1.0
    return prec, rec


def _subset(scores, idx):
    return {f: [[run[i] for i in idx[f]] for run in runs] for f, runs in scores.items()}


def subset_vs_random(base, cand, subset_idx, cost=None, n_random=200, seed=0, **kw):
    """How well does a cheap item subset recover full-suite regressions, vs random subsets
    of equal cost? subset_idx: {family: [item indices]}. cost: {family: [per-item cost]}
    (default 1 each). Random baselines draw items per family until the subset's per-family
    cost is matched."""
    truth = {f for f, r in detect_regressions(base, cand, seed=seed, **kw).items() if r["regression"]}
    pred = {f for f, r in detect_regressions(_subset(base, subset_idx), _subset(cand, subset_idx), seed=seed, **kw).items() if r["regression"]}
    p, r = precision_recall(pred, truth)
    rng = random.Random(seed)
    rp, rr = [], []
    for _ in range(n_random):
        ridx = {}
        for f, runs in base.items():
            n = len(runs[0])
            c = cost[f] if cost else [1.0] * n
            budget = sum(c[i] for i in subset_idx[f])
            perm, chosen, spent = list(range(n)), [], 0.0
            rng.shuffle(perm)
            for i in perm:
                if spent + c[i] <= budget + 1e-9:
                    chosen.append(i)
                    spent += c[i]
            ridx[f] = chosen or perm[:1]
        rpred = {f for f, x in detect_regressions(_subset(base, ridx), _subset(cand, ridx), seed=seed, **kw).items() if x["regression"]}
        a, b = precision_recall(rpred, truth)
        rp.append(a)
        rr.append(b)
    return {"truth": sorted(truth), "subset_pred": sorted(pred), "precision": p, "recall": r,
            "random_precision_mean": mean(rp), "random_recall_mean": mean(rr),
            "random_recall_ci": bootstrap_ci(rr, seed=seed)}


def leave_one_family_out(base, cand, **kw):
    """Re-run detection with each family held out (changes the Holm family size).
    Returns, per held-out family, which regressions remain; plus a stability flag."""
    fams = sorted(set(base) & set(cand))
    full = {f for f, r in detect_regressions(base, cand, **kw).items() if r["regression"]}
    out = {}
    for held in fams:
        rest = [f for f in fams if f != held]
        got = {f for f, r in detect_regressions(base, cand, families=rest, **kw).items() if r["regression"]}
        out[held] = {"regressions": sorted(got), "consistent": got == (full - {held})}
    return {"full": sorted(full), "folds": out, "stable": all(v["consistent"] for v in out.values())}
