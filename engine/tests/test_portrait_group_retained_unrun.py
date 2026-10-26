"""AUTHORED / UNRUN. No build, runtime, quality or performance acceptance."""
from copy import deepcopy
import pytest
from lumaretouch_engine import portrait_group_retained as R
from lumaretouch_engine.preset_store import builtin_docs


def finish():
    return {'modules': {'lnx.skin_finish.v1': {'recipe': {
        'version': 1, 'whitening': 0.1, 'rosiness': 0.05}}}}


def test_retained_family_is_not_legacy_smoothing():
    assert R.support(finish()) == {'supported': True, 'reason': None, 'mode': 'retained_people'}
    legacy = {'modules': {'lnx.skin.v1': {'strength': 0.45}}}
    assert not R.retained(legacy)
    assert R.support(legacy)['mode'] == 'legacy_scalar'
    mixed = finish(); mixed['modules'].update(legacy['modules'])
    assert R.support(mixed)['supported'] is False


def test_true_texture_family_can_combine_without_semantic_alias():
    preset = finish()
    preset['modules']['lnx.skin_texture.v1'] = {'recipe': {'version': 1, 'texture': -0.1, 'clarity': 0.0}}
    assert R.support(preset)['supported']
    preset['modules']['lnx.skin_texture.v1']['recipe']['texture'] = -1.01
    assert not R.support(preset)['supported']


def test_neutral_nonfinite_and_embedded_support_do_not_authorize_group():
    for value in (float('nan'), float('inf'), -0.1, True):
        p = finish(); p['modules']['lnx.skin_finish.v1']['recipe']['whitening'] = value
        assert not R.support(p)['supported']
    p = finish(); p['modules']['lnx.skin_finish.v1']['mask'] = 'source-mask'
    assert not R.support(p)['supported']
    p = finish(); p['modules']['lnx.skin_finish.v1']['recipe'].update(whitening=0, rosiness=0)
    assert not R.support(p)['supported']


def test_real_builtin_catalogue_exposes_distinct_review_required_choices():
    docs = {doc['id']: doc for doc in builtin_docs()}
    for identity, operation in (('portrait-group-finish', 'lnx.skin_finish.v1'),
                                ('portrait-group-texture', 'lnx.skin_texture.v1')):
        assert set(docs[identity]['modules']) == {operation}
        assert R.support(docs[identity])['supported']
    assert 'lnx.skin.v1' in docs['portrait-soft']['modules']


def test_global_recipe_can_join_but_never_replace_retained_face_intent():
    p = finish()
    p['modules'].update({'lnx.exposure.v1': {'ev': 0.15},
                         'lnx.white_balance.v1': {'temperature_shift': 100, 'tint_shift': 0.01}})
    assert R.support(p)['supported']
    p['modules']['lnx.exposure.v1']['ev'] = float('nan')
    assert not R.support(p)['supported']
    p['modules']['lnx.exposure.v1']['ev'] = 0.15
    p['modules']['lnx.skin_finish.v1']['recipe'].update(whitening=0, rosiness=0)
    assert not R.support(p)['supported']


def test_mixed_builtin_is_real_and_keeps_global_and_face_scopes_explicit():
    doc = next(p for p in builtin_docs() if p['id'] == 'portrait-group-wedding-start')
    assert set(doc['modules']) == {'lnx.exposure.v1', 'lnx.white_balance.v1',
                                  'lnx.skin_finish.v1', 'lnx.skin_texture.v1'}
    assert R.support(doc)['supported']


def test_global_projection_restores_presence_without_copying_portrait_data():
    from lumaretouch_engine import portrait_group_mixed_history as H
    current = {'_exposure': (1, 100, .1, 0, 0, 0, 0), '_wb_options': {'version': 1},
               '_exposure_ref_k': 6500, '_repair_ops': ['target-only'], '_precompute': object()}
    before = {'_exposure': (0,) * 7, '_exposure_ref_k': None}
    restored = H.desired(current, before)
    assert H.projection(restored) == before
    assert '_wb_options' not in restored
    assert restored['_repair_ops'] == ['target-only']
    assert restored['_precompute'] is current['_precompute']
    assert current['_exposure'][0] == 1


def test_unrecognized_global_marker_is_never_treated_as_graph_only_history():
    from lumaretouch_engine import portrait_group_mixed_history as H
    for malformed in ({}, {'version': 2}, {'version': 1, 'modules': {'lnx.skin.v1': {}}}):
        with pytest.raises((ValueError, KeyError, TypeError)):
            H.check({H.KEY: malformed})
    assert H.check({'ops': ['lnx.people_graph.v1']}) is None
