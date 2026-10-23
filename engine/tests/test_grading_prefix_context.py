"""Real narrow-lane integration tests, authored UNRUN for local acceptance."""
from types import SimpleNamespace
import numpy as np
import pytest

torch = pytest.importorskip('torch')
from lumaretouch_engine.vram import make_pipeline
from lumaretouch_engine.grading_prefix_cache import preview_context
from lumaretouch_engine.grading_prefix_context import narrow_context


def context():
    rgb = np.arange(16 * 16 * 3, dtype=np.uint8).reshape(16, 16, 3)
    pipe = make_pipeline('cpu', 16, 16, rgb)
    engine = SimpleNamespace(_vram=pipe, _strength=0.0, _channel=None,
        _params={'radius': 4, 'eps': 0.01, 'detail_gain': 1.0,
                 'mid_gain': 1.0, 'broad_gain': 1.0, 'texture_radius': 2},
        _load_id='test-document', _doc_path='test-source.png', _docs=[], _doc_index=-1,
        _colour_grading_preview_active=True)
    return engine


def test_real_provider_is_present_but_default_remains_off():
    e = context()
    assert narrow_context(e) is not None
    assert preview_context(e, 'colour_grading_preview', False) is None
    e._vram.grading_prefix_cache.enabled = True
    assert preview_context(e, 'colour_grading_preview', False) is not None


def test_real_exposure_hsl_cached_matches_full_pipeline_exactly():
    e = context(); p = e._vram
    p.set_exposure(ev=0.25)
    p.set_hsl((0.05, 0.1, 0.0) + (0.0,) * 21)
    expected = p.retouch(0.0, **e._params).clone()
    p.grading_prefix_cache.enabled = True
    key = preview_context(e, 'colour_grading_preview', False)
    assert key is not None
    current = lambda: preview_context(e, 'colour_grading_preview', False) == key
    builds = p.grading_prefix_cache.prefix_builds
    for _ in range(3):
        actual = p.retouch(0.0, **e._params, prefix_key=key, prefix_current=current)
        assert torch.equal(actual, expected)
    assert p.grading_prefix_cache.prefix_builds == builds + 1
    assert p.grading_prefix_cache.cache_hits == 2


def test_live_consumer_state_changes_key_without_history_revision():
    e = context(); p = e._vram
    p.grading_prefix_cache.enabled = True
    before = preview_context(e, 'colour_grading_preview', False)
    p.set_exposure(ev=0.5)
    after = preview_context(e, 'colour_grading_preview', False)
    assert before is not None and after is not None and before != after
    assert before.revision == after.revision
    p.hsl_bands = (0.1,) + (0.0,) * 23
    assert preview_context(e, 'colour_grading_preview', False) != after


@pytest.mark.parametrize('path,value', [
    ('repair_base', object()), ('people_prepared', object()),
    ('facial_wrinkle_layer', object()), ('under_eye_delta', object()),
    ('lip_makeup_delta', object()), ('brow_shape_field', object()),
    ('extended_tone_override', object()), ('manual_liquify.field', object()),
    ('manual_liquify.suspended', 'unresolved'), ('optics.suspended', 'unresolved'),
    ('sky_replacement.suspended', 'unresolved'), ('reference_color.active', True),
    ('semantic_colour.active', True), ('primary_calibration.active', True),
    ('fabric.amount', 0.2), ('crop_rotation', 10.0),
])
def test_runtime_non_noop_or_suspended_state_falls_back(path, value):
    e = context(); e._vram.grading_prefix_cache.enabled = True
    target = e._vram
    pieces = path.split('.')
    for part in pieces[:-1]: target = getattr(target, part)
    setattr(target, pieces[-1], value)
    assert preview_context(e, 'colour_grading_preview', False) is None


@pytest.mark.parametrize('mode,original', [('compare', True), ('colour_grading', False),
    ('colour_grading_cancel', False), ('inspection', False), ('export', False)])
def test_nonpreview_context_never_eligible(mode, original):
    e = context(); e._vram.grading_prefix_cache.enabled = True
    assert preview_context(e, mode, original) is None


def test_uncommitted_preview_owner_and_unknown_numeric_state_excluded():
    e = context(); e._vram.grading_prefix_cache.enabled = True
    e._optics_preview_owner = object()
    assert preview_context(e, 'colour_grading_preview', False) is None
    del e._optics_preview_owner
    e._vram.exposure_params = (float('nan'),) + (0.0,) * 6
    assert preview_context(e, 'colour_grading_preview', False) is None
