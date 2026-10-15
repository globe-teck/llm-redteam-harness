import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _block_network(monkeypatch):
    import urllib.request

    def boom(*a, **k):
        raise AssertionError("network access attempted in tests")
    monkeypatch.setattr(urllib.request, "urlopen", boom)


block_network = pytest.fixture(autouse=True)(_block_network)
