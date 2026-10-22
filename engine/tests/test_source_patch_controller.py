"""Pre-fence proof ownership, exactly-once application and terminal receipts."""
from copy import deepcopy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine.source_patch_controller import (
    SourcePatchController, SourcePatchPorts, SourcePatchApplyError, apply_to_engine)


def request(**changes):
    return {"cmd": "source_patch", "action": "apply", "request_id": "patch-1", "document_id": "1",
            "capture_id": "1"*32, "ticket": "1", "generation": "1",
            "recipe_document_id": "2"*32, "recipe_revision": "0",
            "polygon": [[.6, .3], [.8, .3], [.8, .6]], "offset": [-.4, 0.], **changes}


def fixture():
    events, calls, prepared = [], [], []
    status = {"document_id": "1", "history": {"undo_steps": 0, "redo_steps": 0}, "counts": {"repair": 0}}
    reload = [False]
    def proof(p):
        prepared.append(p["request_id"])
        return {**{k: p[k] for k in ("document_id", "capture_id", "ticket", "generation", "recipe_document_id", "recipe_revision")},
                "params": {"version": "source-patch-v1", "polygon": deepcopy(p["polygon"]), "offset": list(p["offset"])},
                "weight": np.ones((10, 12), np.uint8)}
    def apply(value):
        calls.append(value)
        status["counts"]["repair"] += 1
        return {"op_id": len(calls), "applied": 1}
    ports = SourcePatchPorts(lambda: None, lambda: status["document_id"], proof, apply,
                             lambda: deepcopy(status), lambda: reload[0])
    owner = SourcePatchController(ports, events.append)
    owner.capture = SimpleNamespace(invalidate=lambda: None)
    return owner, status, events, calls, prepared, reload


def test_apply_requires_prepared_owned_proof_and_receipt_waits_for_history():
    owner, status, events, calls, prepared, _ = fixture()
    p = request()
    with pytest.raises(ValueError, match="prepared"):
        owner.handle(p)
    assert owner.prepare(p)
    owner.handle(p)
    assert calls and prepared == ["patch-1"] and not events
    p["polygon"][0][0] = .9
    assert calls[0]["params"]["polygon"][0][0] == .6
    status["history"]["undo_steps"] = 1
    owner.finish(p)
    result = events[-1]
    assert result["success"] and result["history"]["undo_steps"] == 1
    assert not result["outcome_unknown"] and not result["requires_reload"]


def test_cached_retry_never_requires_a_live_capture_or_applies_again():
    owner, _, events, calls, prepared, _ = fixture()
    p = request()
    assert owner.prepare(p)
    owner.handle(p); owner.finish(p)
    assert not owner.prepare(p)
    owner.finish(p)
    assert events[-1]["success"] and events[-1]["replayed"]
    assert len(calls) == len(prepared) == 1
    different = request(offset=[-.3, 0.])
    assert not owner.prepare(different)
    owner.finish(different)
    assert not events[-1]["success"] and len(calls) == 1


def test_exact_zero_displacement_is_no_change_without_a_history_step():
    owner, _, events, calls, prepared, _ = fixture()
    p = request(offset=[0., 0.])
    assert not owner.prepare(p)
    owner.finish(p)
    assert events[-1]["success"] and events[-1]["no_change"]
    assert events[-1]["history"]["undo_steps"] == 0 and not calls and prepared


def test_stale_document_and_bad_requests_do_not_consume_capture():
    owner, _, events, calls, prepared, _ = fixture()
    for p in (request(document_id="2"), request(request_id="\ud800"), request(extra="unknown")):
        assert not owner.prepare(p)
        owner.finish(p)
        assert not events[-1]["success"] and not events[-1]["outcome_unknown"]
        assert len(json.dumps(events[-1]).encode()) < 16384
    assert not calls and not prepared


def test_apply_failure_and_history_failure_never_claim_completion():
    owner, _, events, _, _, reload = fixture()
    def failure(_proof):
        raise SourcePatchApplyError("rolled back", rolled_back=True)
    object.__setattr__(owner.ports, "apply", failure)
    p = request()
    assert owner.prepare(p)
    owner.handle(p); owner.finish(p)
    assert not events[-1]["success"] and not events[-1]["outcome_unknown"]
    owner, _, events, _, _, reload = fixture()
    assert owner.prepare(p)
    owner.handle(p); owner.finish(p, "history failed")
    assert not events[-1]["success"] and events[-1]["outcome_unknown"]


def test_dispatcher_prepares_before_fence_and_invalidation_then_finishes_after_history(monkeypatch):
    from lumaretouch_engine import server
    owner, status, events, calls, _, _ = fixture()
    order = []
    original = owner.prepare
    owner.prepare = lambda p: (order.append("prepare"), original(p))[1]
    owner.capture = SimpleNamespace(invalidate=lambda: order.append("invalidate"))
    engine = server.Engine.__new__(server.Engine)
    engine._source_patch_owner = owner
    engine._source_patch_controller = lambda: owner
    engine._fence_current_document = lambda: order.append("fence")
    engine._color_capture_controller = lambda: SimpleNamespace(invalidate=lambda: None)
    engine._cancel_snapshot = lambda *_: None
    engine._history_capture = lambda: order.append("history_before")
    def recorded(*args, **kwargs):
        assert kwargs["coalesce"] is False
        order.append("history_after")
        status["history"]["undo_steps"] += 1
    engine._history_record = recorded
    monkeypatch.setattr(server, "emit", events.append)
    table = {"source_patch": lambda p: (order.append("apply"), owner.handle(p))}
    engine._process_line(json.dumps(request()), table)
    assert order == ["prepare", "fence", "invalidate", "history_before", "apply", "history_after"]
    assert events[-1]["success"] and events[-1]["history"]["undo_steps"] == 1
    order.clear()
    engine._process_line(json.dumps(request()), table)
    assert order == ["prepare"] and len(calls) == 1 and events[-1]["replayed"]
    order.clear()
    engine._process_line(json.dumps(request(request_id="stale", document_id="2")), table)
    assert order == ["prepare"] and not events[-1]["success"]


@pytest.mark.parametrize("rollback_failure", [False, True])
def test_render_failure_restores_recipe_and_pipeline_then_reports_rollback(rollback_failure):
    old_ops, old_redo = [object()], [object()]
    class Pipe:
        def __init__(self):
            self.repair_ops, self.redo_ops = old_ops, old_redo
            self.repair_version = 4
            self.repair_base = object()
        def add_repair(self, op):
            self.repair_ops, self.redo_ops = self.repair_ops + [op], []
            self.repair_version += 1
            self.repair_base = object()
            return {"applied": 1, "repair_ms": 1.}
    pipe = Pipe()
    base = pipe.repair_base
    engine = SimpleNamespace(_vram=pipe, _repair_ops=old_ops, _redo_ops=old_redo, _op_seq=7,
                             doc_state=lambda: {"document_id": "1"})
    events, modes = [], []
    def render(mode):
        modes.append(mode)
        if mode == "source_patch" or rollback_failure:
            raise RuntimeError("injected render failure")
        return {"event": "frame", "mode": mode}
    engine._write_current_frame = render
    owner, _, _, _, _, _ = fixture()
    assert owner.prepare(request())
    proof = owner.pending["proof"]
    with pytest.raises(SourcePatchApplyError) as caught:
        apply_to_engine(engine, proof, events.append)
    assert caught.value.rolled_back is not rollback_failure
    assert engine._repair_ops is old_ops and engine._redo_ops is old_redo and engine._op_seq == 7
    assert pipe.repair_version == 4 and pipe.repair_base is base
    assert (engine._vram is None) is rollback_failure
    assert modes == ["source_patch", "source_patch_rollback"]
    assert bool(events) is not rollback_failure


def test_apply_state_rejects_bad_redo_before_changing_any_live_field():
    from lumaretouch_engine.server import Engine
    engine = Engine("source-patch-state-preflight")
    state = engine._capture_state()
    state["_strength"] = .8
    state["_redo_ops"] = [object()]
    before = engine._strength
    with pytest.raises(ValueError, match="RepairOp"):
        engine._apply_state(state)
    assert engine._strength == before and not engine._redo_ops
