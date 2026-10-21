"""A collector's total timeout must not shrink to its internal polling interval."""
from types import SimpleNamespace
import pytest
import test_protocol as protocol


def test_collection_survives_a_quiet_poll_within_total_budget(monkeypatch):
    clock=iter([0.0,0.0,10.1])
    monkeypatch.setattr(protocol,'time',SimpleNamespace(monotonic=lambda:next(clock)))
    class Peer:
        calls=0
        def next_event(self,timeout):
            self.calls+=1
            assert timeout==10.0
            if self.calls==1: raise TimeoutError('no event during this poll')
            return {'event':'image_ready','ok':True}
    peer=Peer()
    assert protocol._collect(peer,'image_ready',timeout=240)['image_ready'][0]['ok']
    assert peer.calls==2


def test_collection_still_enforces_total_budget(monkeypatch):
    clock=iter([0.0,0.0,6.0])
    monkeypatch.setattr(protocol,'time',SimpleNamespace(monotonic=lambda:next(clock)))
    class Peer:
        def next_event(self,timeout): raise TimeoutError('quiet')
    with pytest.raises(AssertionError,match='5.*image_ready'):
        protocol._collect(Peer(),'image_ready',timeout=5)


def test_real_engine_error_is_not_swallowed():
    peer=SimpleNamespace(next_event=lambda timeout:{'event':'error','error':'broken decoder'})
    with pytest.raises(AssertionError,match='broken decoder'):
        protocol._collect(peer,'image_ready',timeout=5)
