import json
import os

from harness.datasets import load_benchmark
from harness.manifest import build_manifest, write_run_report

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def test_manifest_fields_and_report(tmp_path):
    _, dm = load_benchmark("xstest", path=os.path.join(FX, "xstest_mini.csv"))
    m = build_manifest("mock", "0", [dm], seeds=[0, 1, 2], settings={"temperature": 0},
                       started="2026-01-01T00:00:00+00:00", finished="2026-01-01T00:00:01+00:00")
    for k in ("model", "datasets", "seeds", "settings", "judge", "timestamps", "items_sha256", "harness_version"):
        assert k in m
    assert m["datasets"][0]["item_ids"] == ["xstest-1", "xstest-2", "xstest-3"]
    j, md = write_run_report(tmp_path, m, [{"id": "xstest-1", "passed": True, "reasons": []}], {"passed": 1})
    doc = json.loads(j.read_text())
    assert doc["manifest"]["seeds"] == [0, 1, 2]
    assert "Replication manifest" in md.read_text()
    m2 = build_manifest("mock", "0", [dm], seeds=[0, 1, 2], settings={"temperature": 0},
                        started=m["timestamps"]["started_utc"], finished=m["timestamps"]["finished_utc"])
    assert m2["items_sha256"] == m["items_sha256"]
