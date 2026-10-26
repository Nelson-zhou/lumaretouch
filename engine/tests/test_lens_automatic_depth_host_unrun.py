"""AUTHORED / UNRUN. Source fixtures only; no inference/download/build executed.

These fixtures use synthetic immutable assets only. They are NOT model, native,
real-photo, image-quality, cancellation-latency or performance acceptance.
"""
import hashlib
import json
import struct
from dataclasses import replace
import pytest
from lumaretouch_engine import lens_blur_stage as stage
from lumaretouch_engine import lens_blur_host as host


def source():
    owner = {'document_id': 'photo', 'document_epoch': 'epoch', 'document_revision': '1',
        'source': {'sha256': 'a'*64, 'width': 2, 'height': 2, 'orientation': stage.ORIENTATION}}
    return stage.CapturedSource(stage._json(owner), b'{}', struct.pack('<16f', *([.5,.5,.5,1]*4)),
        b'', b'', b'', 2, 2, stage._SEAL)


def test_arbitrary_wire_model_depth_is_not_admitted(monkeypatch):
    monkeypatch.setattr(stage, '_admit', lambda *args: None)
    # Only the genuine adapter path can create a sealed model CapturedDepth.
    with pytest.raises(ValueError):
        stage.capture_depth({'provenance': {'kind': 'model'}}, source(), budget=stage.Budget(200_000_000))


def test_model_native_depth_never_uses_u16_visualization():
    src = source()
    full = struct.pack('<4f', 0, .123456, .876543, 1)
    wire = {'owner': src.owner, 'provenance': {'kind': 'model'},
        'raster': {'width': 2, 'height': 2}}
    depth = stage.CapturedDepth(stage._json(wire), b'\0'*8, 'session', stage._SEAL,
        full, hashlib.sha256(full).hexdigest(), '{}')
    rendered = stage._full_depth(depth, 2, 2, lambda: False)
    assert rendered.astype('<f4', copy=False).tobytes() == full
    assert depth.retained_bytes >= len(full) + len(depth.raster_bytes)
    with pytest.raises(ValueError):
        stage._full_depth(replace(depth, full_depth_sha256='b'*64), 2, 2, lambda: False)


def test_model_command_requires_explicit_acknowledgement_before_adapter():
    src = source()
    command = {'version': 3, 'action': 'prepare_model_depth', 'request_id': 'request',
        'session_id': 'session', 'owner': src.owner, 'acknowledged_model': False}
    with pytest.raises(ValueError):
        stage.prepare_model_depth(command, src, model_root='/not-used', budget=stage.Budget(200_000_000))


def test_unready_setup_does_not_create_fake_depth(monkeypatch):
    from lumaretouch_engine import lens_depth_setup
    service = host.Service(object(), lambda _: None)
    marker = object()
    service.depth = marker
    monkeypatch.setattr(service, '_guard', lambda: None)
    monkeypatch.setattr(service, '_require', lambda command: None)
    monkeypatch.setattr(lens_depth_setup, 'model_status', lambda: {'ready': False, 'reason': 'missing verified runtime'})
    with pytest.raises(ValueError, match='missing verified runtime'):
        service.prepare_model_depth({'command': {}})
    assert service.depth is marker  # A failed readiness request does not erase manual work.


def test_model_replay_requires_original_acknowledgement():
    service = host.Service(object(), lambda _: None)
    service.source = source()
    service.session_id = 'session'
    wire = {'provenance': {'kind': 'model', 'acknowledgement_id': 'different-request'}}
    service.depth = stage.CapturedDepth(stage._json(wire), b'', 'session', stage._SEAL)
    service._require = lambda command: None
    request = {'cmd': 'lens_blur', 'action': 'prepare_model_depth', 'request_id': 'original', 'command': {}}
    old = {'sha': host.command_hash(request), 'session_id': 'session'}
    with pytest.raises(ValueError, match='superseded'):
        service._replay_read(request, old)
