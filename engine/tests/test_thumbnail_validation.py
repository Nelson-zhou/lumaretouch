"""Invalid thumbnail requests have deterministic errors even while a job runs."""
from types import SimpleNamespace

import pytest

from lumaretouch_engine import server


@pytest.mark.parametrize("edge,quality", [(8, 85), (256, 0), (256, "bad")])
def test_invalid_request_is_validated_before_busy_state(monkeypatch, edge, quality):
    events = []
    monkeypatch.setattr(server, "emit", events.append)
    engine = server.Engine.__new__(server.Engine)
    engine._thumbs = SimpleNamespace(is_alive=lambda: True)
    assert engine._start_thumbs([], edge, quality) is False
    assert len(events) == 1
    assert "缩略图参数非法" in events[0]["error"]


def test_valid_request_still_respects_busy_state(monkeypatch):
    events = []
    monkeypatch.setattr(server, "emit", events.append)
    engine = server.Engine.__new__(server.Engine)
    engine._thumbs = SimpleNamespace(is_alive=lambda: True)
    assert engine._start_thumbs([], 256, 85) is False
    assert "缩略图任务已在跑" in events[0]["error"]
