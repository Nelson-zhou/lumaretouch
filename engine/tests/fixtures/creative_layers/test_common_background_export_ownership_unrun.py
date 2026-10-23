"""AUTHORED / UNRUN: inactive retained key and direct export ownership fences.

These are regression specifications only, not evidence that export was run.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import common_background_source as C
from lumaretouch_engine import creative_derived_common_background as D
from lumaretouch_engine import creative_derived_global_recovery as G
from lumaretouch_engine import common_background_recovery as R
from lumaretouch_engine import local_mask_state as M
from test_common_background_recovery_unrun import snapshot, background


def provenance(monkeypatch):
    monkeypatch.setattr(M, 'file_stamp', lambda _path: (1, 2, 3))
    monkeypatch.setattr(M, 'source_digest', lambda _path: 'a' * 64)


@pytest.mark.parametrize('enabled', [True, False])
def test_reviewed_clear_retains_key_through_derived_rebound_without_compositing(monkeypatch, enabled):
    from lumaretouch_engine.export import ExportSpec
    from lumaretouch_engine.creative_document_base import require_rebound_spec
    from lumaretouch_engine.ops import matting
    provenance(monkeypatch)
    snap = snapshot(active=False, enabled=enabled)
    snap['common_background_path'] = 'original'
    snap['common_background_stamp'] = [1, 2, 3]
    snap['creative_recovery_context'] = G.capture(snap, snap['effect_recovery'], 'original')
    spec = ExportSpec(creative_base=snap['creative_base'], strength=0.,
        effect_recovery=deepcopy(snap['effect_recovery']),
        creative_recovery_context=deepcopy(snap['creative_recovery_context']),
        effect_recovery_path='original', effect_recovery_stamp=[1, 2, 3])
    assert C.configure_export(spec, snap, for_document=True) is False
    R.configure_export(spec, snap)
    restored = D.spec_state(spec)
    assert restored['_bg']['key_recipe'] == snap['_bg']['key_recipe']
    assert restored['_bg']['active'] is False
    assert spec.common_background_key is None and spec.common_background_color is None
    require_rebound_spec(spec)
    monkeypatch.setattr(matting, 'key_matte_np', lambda *_args, **_kwargs: pytest.fail('Inactive key must not rasterize'))
    C.prepare_export(spec, np.zeros((4, 4, 3), np.float32))
    C.finish_export(spec)
    R.export_prepare(spec)
    R.verify_export(spec)
    assert spec.bg_matte is None and spec.bg_ref is None


def test_inactive_retained_key_is_copied_without_retaining_cached_matte(monkeypatch):
    provenance(monkeypatch)
    snap = snapshot(active=False)
    snap['_bg']['matte'] = np.ones((4, 4), np.uint8)
    spec = SimpleNamespace(creative_base=snap['creative_base'], bg_matte=None, bg_ref=None)
    C.configure_export(spec, snap, for_document=True)
    assert 'matte' not in spec._common_background_retained
    snap['_bg']['key_recipe']['reference'][0] = .1
    assert D.spec_state(spec)['_bg']['key_recipe']['reference'][0] == .9


@pytest.mark.parametrize('field', ['key', 'color', 'matte', 'background'])
def test_inactive_retained_intent_cannot_implicitly_reactivate(field):
    snap = snapshot(active=False)
    spec = SimpleNamespace(creative_base=snap['creative_base'], bg_matte=None, bg_ref=None)
    C.configure_export(spec, snap, for_document=True)
    if field == 'key': spec.common_background_key = deepcopy(snap['_bg']['key_recipe'])
    elif field == 'color': spec.common_background_color = tuple(snap['_bg']['bg'])
    elif field == 'matte': spec.bg_matte = np.zeros((4, 4), np.float32)
    else: spec.bg_ref = tuple(snap['_bg']['bg'])
    with pytest.raises(ValueError):
        D.spec_state(spec)


def test_direct_original_spec_cannot_replay_version_two_before_source_verification(monkeypatch):
    snap = snapshot()
    spec = SimpleNamespace(creative_base=None, common_background_key=snap['_bg']['key_recipe'],
        common_background_color=tuple(snap['_bg']['bg']), common_background_path='original',
        common_background_stamp=[1, 2, 3], bg_matte=None, bg_ref=None)
    monkeypatch.setattr(M, 'verify_source', lambda *_args, **_kwargs: pytest.fail('v2 must be rejected before original replay'))
    with pytest.raises(ValueError, match='original source'):
        C.prepare_export(spec, np.zeros((4, 4, 3), np.uint8))


def test_direct_derived_spec_cannot_replay_version_one(monkeypatch):
    snap = snapshot()
    old = background(snap['effect_recovery']['source'], version=1)
    spec = SimpleNamespace(creative_base=snap['creative_base'], common_background_key=old['key_recipe'],
        common_background_color=tuple(old['bg']), common_background_path='original',
        common_background_stamp=[1, 2, 3], bg_matte=None, bg_ref=None)
    monkeypatch.setattr(D, 'verify_pixels', lambda *_args, **_kwargs: pytest.fail('v1 must be rejected before derived replay'))
    with pytest.raises(ValueError):
        C.prepare_export(spec, np.zeros((4, 4, 3), np.float32))


@pytest.mark.parametrize('derived', [False, True])
def test_inactive_direct_metadata_cannot_hide_wrong_owner_version(derived):
    snap = snapshot(active=False)
    retained = deepcopy(snap['_bg'])
    retained.pop('matte')
    if derived:
        retained = background(snap['effect_recovery']['source'], active=False, version=1)
        retained.pop('matte')
    spec = SimpleNamespace(creative_base=snap['creative_base'] if derived else None,
        _common_background_retained=retained, common_background_key=None,
        common_background_color=None, common_background_path='original',
        common_background_stamp=[1, 2, 3], bg_matte=None, bg_ref=None)
    with pytest.raises(ValueError):
        C.prepare_export(spec, np.zeros((4, 4, 3), np.float32))
    with pytest.raises(ValueError):
        C.finish_export(spec)


def test_inactive_key_still_checks_original_provenance(monkeypatch):
    provenance(monkeypatch)
    snap = snapshot(active=False)
    snap['common_background_path'] = 'original'
    snap['common_background_stamp'] = [1, 2, 3]
    spec = SimpleNamespace(creative_base=snap['creative_base'], bg_matte=None, bg_ref=None)
    C.configure_export(spec, snap, for_document=True)
    monkeypatch.setattr(M, 'source_digest', lambda _path: 'b' * 64)
    with pytest.raises(ValueError):
        C.prepare_export(spec, np.zeros((4, 4, 3), np.float32))


def test_inactive_key_cannot_be_copied_to_another_batch_target():
    snap = snapshot(active=False)
    spec = SimpleNamespace(creative_base=snap['creative_base'], bg_matte=None, bg_ref=None)
    with pytest.raises(ValueError):
        C.configure_export(spec, snap, for_document=False)
