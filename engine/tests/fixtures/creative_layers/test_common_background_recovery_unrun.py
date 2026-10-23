"""AUTHORED / UNRUN: common-background recovery consumer fences, not acceptance.

These fixtures deliberately keep the legacy/common target separate from the
dedicated ID compositor. No numerical or visual result is claimed here.
"""
from copy import deepcopy
from types import SimpleNamespace
import json
import numpy as np
import pytest
from lumaretouch_engine import common_background_recovery as R
from lumaretouch_engine import common_background_source as B
from lumaretouch_engine import creative_derived_global_recovery as G
from lumaretouch_engine import creative_derived_recovery as REVIEW
from lumaretouch_engine import creative_derived_source as D
from lumaretouch_engine import effect_recovery_state as S, local_mask_state as M
from lumaretouch_engine.creative_document_assets import make_asset


def base():
    rgba = np.zeros((4, 4, 4), dtype='<f4')
    rgba[..., 3] = 1
    return make_asset('rgba', 4, 4, rgba.tobytes(), original=b'original-provenance')


def recovery(source, *, enabled=True):
    stack = M.empty()['recipe']
    stack['objects'] = [{'id': 'recover-common', 'name': 'Recovery', 'enabled': True,
        'operation': 'add', 'kind': 'brush', 'opacity': 1., 'feather': 20.,
        'points': [[.5, .5]], 'axes': [[.1, 0.], [0., .1]]}]
    return {'version': 1, 'source': deepcopy(source),
            'targets': [{'target': 'background_replace', 'enabled': enabled, 'recipe': stack}]}


def background(source, *, active=True, version=2):
    recipe = {'version': version,
              'contract': 'legacy-color-key-effective-v2' if version == 2 else 'legacy-color-key-frozen-reference-v1',
              'source': deepcopy(source), 'reference': [.9, .9, .9],
              'reference_grid': [4, 4], 'tol': .1, 'softness': .05}
    if version == 2:
        recipe['original_sha256'] = 'a' * 64
    return {'active': active, 'backend': 'color_key', 'bg': [.2, .4, .6],
            'tol': .1, 'softness': .05, 'key_recipe': recipe, 'matte': None}


def snapshot(*, active=True, enabled=True):
    asset = base()
    source = D.binding({'creative_base': asset})
    return {'creative_base': asset, '_bg': background(source, active=active),
            'effect_recovery': recovery(source, enabled=enabled)}


def export_spec(monkeypatch, *, active=True, enabled=True):
    snap = snapshot(active=active, enabled=enabled)
    spec = SimpleNamespace(creative_base=snap['creative_base'],
        effect_recovery=deepcopy(snap['effect_recovery']),
        common_background_key=deepcopy(snap['_bg']['key_recipe']) if active else None,
        common_background_color=tuple(snap['_bg']['bg']) if active else None,
        common_background_path='original' if active else None,
        common_background_stamp=[1, 2, 3] if active else None,
        effect_recovery_path='original', effect_recovery_stamp=[1, 2, 3],
        bg_matte=np.full((4, 4), .25, dtype=np.float32) if active else None,
        bg_ref=tuple(snap['_bg']['bg']) if active else None,
        deform_amounts={}, landmarks=np.zeros((3, 3), np.float32))
    monkeypatch.setattr(B, 'finish_export', lambda _spec: None)
    if active:
        spec._common_canonical_pixels = (json.dumps(spec.common_background_key, sort_keys=True, allow_nan=False), 'd' * 64)
    R.configure_export(spec, snap)
    return spec


def test_common_and_id_recovery_are_distinct_accepted_targets():
    snap = snapshot()
    value = snap['effect_recovery']
    assert S.target('background_replace') != S.target('id_background')
    assert G.validate(value, value['source']) == value
    assert R.validate_state(snap, value) == value
    assert 'background_replace' in REVIEW.GLOBAL_TARGETS


@pytest.mark.parametrize('active', [True, False])
def test_disabled_vectors_do_not_launder_foreign_key_source(active):
    snap = snapshot(active=active, enabled=False)
    snap['_bg']['key_recipe']['source']['sha256'] = 'f' * 64
    with pytest.raises(ValueError):
        R.validate_state(snap, snap['effect_recovery'])
    with pytest.raises(ValueError):
        G.validate_state(snap)


@pytest.mark.parametrize('backend', ['color_key', 'rvm', None])
def test_derived_recovery_never_adopts_original_matte_or_neural_cache(backend):
    snap = snapshot(enabled=False)
    snap['_bg'].pop('key_recipe')
    snap['_bg']['backend'] = backend
    snap['_bg']['matte'] = np.full((4, 4), 127, np.uint8)
    with pytest.raises(ValueError):
        R.validate_state(snap, snap['effect_recovery'])


def test_derived_and_original_recipe_versions_cannot_exchange_owners():
    snap = snapshot()
    source = snap['effect_recovery']['source']
    snap['_bg'] = background(source, version=1)
    with pytest.raises(ValueError):
        R.validate_state(snap, snap['effect_recovery'])
    snap = snapshot()
    del snap['creative_base']
    with pytest.raises(ValueError):
        R.validate_state(snap, snap['effect_recovery'])


def test_original_unversioned_recovery_keeps_original_only_ownership():
    snap = snapshot()
    del snap['creative_base']
    snap['_bg'].pop('key_recipe')
    snap['_bg']['backend'] = 'rvm'
    assert R.validate_state(snap, snap['effect_recovery']) == snap['effect_recovery']


def test_recovery_snapshot_requires_common_intent_even_without_active_rows(monkeypatch):
    snap = snapshot(enabled=False)
    monkeypatch.setattr(M, 'source_digest', lambda _path: 'a' * 64)
    snap['creative_recovery_context'] = G.capture(snap, snap['effect_recovery'], 'original')
    assert G.verify_snapshot(snap, 'original', (4, 4)) == snap['effect_recovery']
    snap['_bg']['key_recipe']['source']['sha256'] = 'b' * 64
    with pytest.raises(ValueError):
        G.verify_snapshot(snap, 'original', (4, 4))


@pytest.mark.parametrize('field', ['source', 'recipe', 'color', 'matte', 'geometry', 'active'])
def test_original_review_detects_each_common_consumer_change(monkeypatch, field):
    source = {'sha256': 'a' * 64, 'width': 4, 'height': 4}
    engine = SimpleNamespace(_effect_recovery=recovery(source))
    consumer = {'source': source, 'recipe': 'key-v1', 'color': [.2, .4, .6],
                'matte': 'b' * 64, 'geometry': 'initial', 'active': True}
    monkeypatch.setattr(R, 'context', lambda *_args, **_kwargs: deepcopy(consumer))
    record = {'target': 'background_replace', 'people_context': None,
              'global_context': REVIEW.global_context(engine, 'background_replace')}
    REVIEW.assert_review(engine, record)
    consumer[field] = 'changed'
    with pytest.raises(ValueError):
        REVIEW.assert_review(engine, record)


def test_common_review_cannot_be_relabelled_as_a_face_consumer(monkeypatch):
    engine = SimpleNamespace(_effect_recovery=S.empty())
    monkeypatch.setattr(R, 'context', lambda *_args, **_kwargs: {'active': False})
    record = {'target': 'background_replace', 'people_context': {'face_instance_id': 'unrelated'},
              'global_context': REVIEW.global_context(engine, 'background_replace')}
    with pytest.raises(ValueError):
        REVIEW.assert_review(engine, record)


@pytest.mark.parametrize('value', [S.empty(), recovery({'sha256': 'a' * 64, 'width': 4, 'height': 4}, enabled=False)])
def test_clear_and_disable_keep_the_explicit_review_consumer(monkeypatch, value):
    engine = SimpleNamespace(_effect_recovery=deepcopy(value))
    stage = SimpleNamespace(common_recovery_context={'active': True, 'matte': 'a' * 64})
    monkeypatch.setattr(R, 'context', lambda *_args, **_kwargs: {'active': False, 'matte': 'a' * 64})
    with pytest.raises(ValueError):
        R.assert_consumer(engine, stage)


def test_disabled_recovery_needs_no_export_matte_or_consumer_preparation():
    spec = SimpleNamespace(effect_recovery=recovery({'sha256': 'a' * 64, 'width': 4, 'height': 4}, enabled=False))
    R.export_prepare(spec)
    R.verify_export(spec)
    assert spec._common_recovery_consumer is None


def test_inactive_compositor_is_bound_without_fabricating_a_matte(monkeypatch):
    spec = export_spec(monkeypatch, active=False)
    R.export_prepare(spec)
    R.verify_export(spec)
    assert spec._common_recovery_consumer['active'] is False
    spec.bg_matte = np.zeros((4, 4), np.float32)
    spec.bg_ref = (.2, .4, .6)
    with pytest.raises(ValueError):
        R.verify_export(spec)


@pytest.mark.parametrize('change', ['matte', 'color', 'key', 'source', 'geometry', 'active', 'path', 'stamp'])
def test_export_binds_full_matte_recipe_source_geometry_and_activation(monkeypatch, change):
    spec = export_spec(monkeypatch)
    R.export_prepare(spec)
    R.verify_export(spec)
    if change == 'matte': spec.bg_matte[0, 0] = .9
    elif change == 'color': spec.bg_ref = (.1, .4, .6)
    elif change == 'key': spec.common_background_key['reference'][0] = .8
    elif change == 'source': spec.effect_recovery['source']['sha256'] = 'f' * 64
    elif change == 'geometry': spec.deform_amounts['smile'] = .2
    elif change == 'active': spec.bg_matte = spec.bg_ref = None
    elif change == 'path': spec.common_background_path = 'another-original'
    elif change == 'stamp': spec.common_background_stamp = [4, 5, 6]
    with pytest.raises(ValueError):
        R.verify_export(spec)


@pytest.mark.parametrize('matte', [np.zeros((2, 2), np.float32), np.zeros((4, 4), np.uint8),
                                  np.full((4, 4), np.nan, np.float32), np.full((4, 4), 1.1, np.float32)])
def test_export_never_substitutes_proxy_quantized_or_invalid_key_matte(monkeypatch, matte):
    spec = export_spec(monkeypatch)
    spec.bg_matte = matte
    with pytest.raises(ValueError):
        R.export_prepare(spec)


def test_enabled_export_cannot_skip_consumer_evidence(monkeypatch):
    spec = export_spec(monkeypatch)
    with pytest.raises(ValueError):
        R.verify_export(spec)
    del spec._common_recovery_recipe
    with pytest.raises(ValueError):
        R.export_prepare(spec)


def test_derived_export_requires_canonical_source_preparation_receipt(monkeypatch):
    spec = export_spec(monkeypatch)
    del spec._common_canonical_pixels
    with pytest.raises(ValueError):
        R.export_prepare(spec)


def test_export_geometry_binds_actual_snapshot_analysis_bytes(monkeypatch):
    spec = export_spec(monkeypatch)
    spec.people = {'analyses': {'face': {'landmarks': np.zeros((3, 3), np.float32)}}}
    R.export_prepare(spec)
    R.verify_export(spec)
    spec.people['analyses']['face']['landmarks'][0, 0] = .5
    with pytest.raises(ValueError):
        R.verify_export(spec)


def test_same_content_reallocation_does_not_invalidate_export_review(monkeypatch):
    spec = export_spec(monkeypatch)
    R.export_prepare(spec)
    spec.bg_matte = spec.bg_matte.copy()
    spec.landmarks = spec.landmarks.copy()
    R.verify_export(spec)
