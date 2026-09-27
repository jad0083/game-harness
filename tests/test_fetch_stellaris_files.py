"""scripts/fetch-stellaris-files.py pages reads larger than the agent's per-response cap."""

import importlib.util
import io
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fetch_stellaris_files", REPO / "scripts/fetch-stellaris-files.py")
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


class _Resp(io.BytesIO):
    def __init__(self, body: bytes, size: int):
        super().__init__(body)
        self.headers = {"X-File-Size": str(size)}


class PagingAgent(fetch.Agent):
    """Serves `data`, at most `cap` bytes per response, like agent >= 1.5.0."""

    def __init__(self, data: bytes, cap: int, sizes: list[int] | None = None):
        super().__init__("http://agent", "t")
        self.data, self.cap, self.sizes, self.calls = data, cap, sizes, []

    def _get(self, endpoint, **q):
        assert endpoint == "/files/read"
        off = int(q.get("offset", 0))
        self.calls.append(off)
        size = self.sizes[min(len(self.calls), len(self.sizes)) - 1] if self.sizes else len(self.data)
        return _Resp(self.data[off:off + self.cap], size)


def test_read_pages_until_the_whole_file_is_fetched():
    data = bytes(range(250))
    agent = PagingAgent(data, cap=100)
    assert agent.read("common/x.txt") == data
    assert agent.calls == [0, 100, 200]


def test_read_of_a_small_file_is_one_request():
    agent = PagingAgent(b"abc", cap=100)
    assert agent.read("x") == b"abc"
    assert agent.calls == [0]


def test_read_fails_when_the_file_changes_between_pages():
    agent = PagingAgent(bytes(250), cap=100, sizes=[250, 120])
    with pytest.raises(RuntimeError, match="changed"):
        agent.read("x")
