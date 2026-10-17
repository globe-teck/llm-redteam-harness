import random

from harness import stats


def synth(p, n_items=200, n_runs=3, seed=0):
    rng = random.Random(seed)
    base_item = [rng.random() for _ in range(n_items)]
    return [[1 if base_item[i] < p else 0 for i in range(n_items)] for _ in range(n_runs)], base_item


def pair(p_base, drop, n_items=200, runs=3, seed=0):
    rng = random.Random(seed)
    u = [rng.random() for _ in range(n_items)]
    base = [[int(x < p_base) for x in u] for _ in range(runs)]
    cand = [[int(x < p_base - drop) for x in u] for _ in range(runs)]
    return base, cand


def test_holm_known_values():
    adj = stats.holm([0.01, 0.04, 0.03])
    assert [round(a, 4) for a in adj] == [0.03, 0.06, 0.06]


def test_bootstrap_ci_contains_mean_and_is_seeded():
    v = [0, 1] * 50
    lo, hi = stats.bootstrap_ci(v, seed=1)
    assert lo < 0.5 < hi
    assert stats.bootstrap_ci(v, seed=1) == (lo, hi)


def test_regression_rules():
    big_b, big_c = pair(0.8, 0.10)
    small_b, small_c = pair(0.8, 0.02, seed=1)
    none_b, none_c = pair(0.8, 0.0, seed=2)
    res = stats.detect_regressions({"big": big_b, "small": small_b, "none": none_b},
                                   {"big": big_c, "small": small_c, "none": none_c})
    assert res["big"]["regression"] and res["big"]["drop_pts"] >= 3
    assert not res["small"]["regression"]          # < 3 points
    assert not res["none"]["regression"]
    assert res["big"]["p_holm"] >= res["big"]["p"]


def test_requires_three_runs():
    b, c = pair(0.8, 0.2, runs=2)
    r = stats.detect_regressions({"f": b}, {"f": c})["f"]
    assert r["insufficient_runs"] and not r["regression"]


def test_precision_recall():
    assert stats.precision_recall({"a", "b"}, {"a"}) == (0.5, 1.0)
    assert stats.precision_recall(set(), set()) == (1.0, 1.0)


def test_subset_vs_random_and_lofo():
    base, cand = {}, {}
    for k, (fam, d) in enumerate([("A", 0.15), ("B", 0.15), ("C", 0.0), ("D", 0.0)]):
        base[fam], cand[fam] = pair(0.8, d, n_items=100, seed=k)
    # a "smart" subset: the items whose outcome flips (oracle-ish), 30 per family
    idx = {}
    for f in base:
        flips = [i for i in range(100) if base[f][0][i] != cand[f][0][i]]
        rest = [i for i in range(100) if i not in flips]
        idx[f] = (flips + rest)[:30]
    out = stats.subset_vs_random(base, cand, idx, n_random=30, seed=0)
    assert out["truth"] == ["A", "B"]
    assert out["recall"] == 1.0 and out["precision"] == 1.0
    assert out["random_recall_mean"] <= out["recall"]
    lofo = stats.leave_one_family_out(base, cand)
    assert lofo["full"] == ["A", "B"] and lofo["stable"]
    assert lofo["folds"]["A"]["regressions"] == ["B"]
