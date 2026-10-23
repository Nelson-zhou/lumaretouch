"""AUTHORED / UNRUN: bounded source-owned spill paint intent and raster routing.

No product imports, collection, tests, raster worker or numerical inference ran
while authoring. The routing double is not a native correctness claim. The
separate real-raster fixture requires the matching installed Rust worker; it is
also UNRUN. Neither fixture establishes visual quality, parity or performance.
"""
from copy import deepcopy
import json

import numpy as np
import pytest

from lumaretouch_engine import local_mask_recipe as R
from lumaretouch_engine import local_mask_state as M
from lumaretouch_engine import spill_removal_coverage as C
from lumaretouch_engine import spill_removal_paint_vectors as P

SOURCE = {'sha256': 'a' * 64, 'width': 80, 'height': 40}


def stroke(ident='stroke-1', mode='erase', **changes):
    return {'id': ident, 'mode': mode, 'points': [[.25, .5], [.75, .5]],
            'radius': .1, 'opacity': .6, 'feather': 0., **changes}


def manual(objects=None, source=SOURCE):
    if objects is None:
        objects = [{'id': 'manual', 'name': 'Reviewed manual coverage',
                    'enabled': True, 'kind': 'radial', 'operation': 'add',
                    'opacity': 1., 'feather': 0., 'center': [.5, .5],
                    'axes': [[.4, 0.], [0., .4]]}]
    mask = M.check({'source': deepcopy(source), 'semantic_owner': None,
                    'recipe': {**M.empty()['recipe'], 'objects': deepcopy(objects)}})
    return {'version': 1, 'reviewed': True, 'mask': mask,
            'recipe_sha256': C.digest(mask)}


def redigest(value):
    value['recipe_sha256'] = C.digest(value['mask'])
    return value


def test_legacy_binding_validation_keeps_exact_version_and_serialization():
    old = manual()
    serialized = json.dumps(old, sort_keys=True, separators=(',', ':'))
    assert C.VERSION == 1
    assert C.check_binding(old) == old
    assert json.dumps(C.check_binding(old), sort_keys=True, separators=(',', ':')) == serialized
    assert old['version'] == 1


def test_automatic_paint_begins_with_one_canonical_full_coverage_object():
    raw = [stroke(), stroke('restore-1', 'restore')]
    original = deepcopy((SOURCE, raw))
    result = P.append(None, SOURCE, raw)
    objects = result['mask']['recipe']['objects']
    assert result['version'] == 2 and result['reviewed'] is True
    assert objects[0] == C.automatic_base()
    assert [obj['operation'] for obj in objects] == ['add', 'subtract', 'add']
    assert [obj['kind'] for obj in objects] == ['full', 'brush', 'brush']
    assert result['mask']['semantic_owner'] is None
    assert result['recipe_sha256'] == C.digest(result['mask'])
    assert (SOURCE, raw) == original
    assert set(result) == {'version', 'reviewed', 'mask', 'recipe_sha256'}


def test_existing_manual_order_visibility_and_geometry_are_preserved_without_full_base():
    base = manual()
    first = base['mask']['recipe']['objects'][0]
    objects = [first, {**deepcopy(first), 'id': 'exclude', 'operation': 'subtract'},
               {**deepcopy(first), 'id': 'clip', 'operation': 'intersect', 'enabled': False}]
    old = manual(objects)
    before = deepcopy(old)
    result = P.append(old, SOURCE, [stroke()])
    assert old == before and old['version'] == 1
    assert result['mask']['recipe']['objects'][:-1] == before['mask']['recipe']['objects']
    assert not any(obj['kind'] == 'full' for obj in result['mask']['recipe']['objects'])
    result['mask']['recipe']['objects'][0]['center'][0] = .2
    assert old == before


def test_repeated_append_retains_single_full_base_and_prior_strokes():
    first = P.append(None, SOURCE, [stroke()])
    before = deepcopy(first)
    second = P.append(first, SOURCE, [stroke('restore-1', 'restore')])
    assert first == before
    assert second['mask']['recipe']['objects'][:-1] == first['mask']['recipe']['objects']
    assert sum(obj['kind'] == 'full' for obj in second['mask']['recipe']['objects']) == 1


@pytest.mark.parametrize('width,height,axes', [
    (80, 40, [[.05, 0.], [0., .1]]),
    (40, 80, [[.1, 0.], [0., .05]]),
    (40, 40, [[.1, 0.], [0., .1]]),
])
def test_radius_uses_true_source_min_dimension_not_display_grid(width, height, axes):
    result = P.append(None, {**SOURCE, 'width': width, 'height': height}, [stroke()])
    obj = result['mask']['recipe']['objects'][-1]
    assert obj['axes'] == axes
    assert obj['points'] == [[.25, .5], [.75, .5]]
    assert obj['opacity'] == .6 and obj['feather'] == 0.


@pytest.mark.parametrize('key,value', [
    ('id', ''), ('id', 'bad/id'), ('id', 1), ('id', 'x' * 65),
    ('id', C.AUTOMATIC_BASE_ID), ('mode', 'add'), ('mode', 'subtract'),
    ('mode', False), ('mode', []), ('points', []), ('points', ((.5, .5),)),
    ('points', [(.5, .5)]), ('points', [[.5]]), ('points', [[.5, .5, .5]]),
    ('points', [[-.01, .5]]), ('points', [[.5, 1.01]]),
    ('points', [[True, .5]]), ('points', [[float('nan'), .5]]),
    ('points', [[float('inf'), .5]]), ('points', [[.5, .5]] * 1025),
    ('radius', 0.), ('radius', .000099), ('radius', .500001),
    ('radius', True), ('radius', float('nan')), ('radius', float('inf')),
    ('opacity', -.01), ('opacity', 1.01), ('opacity', True),
    ('opacity', float('nan')), ('feather', -.01), ('feather', 100.01),
    ('feather', True), ('feather', float('inf')),
])
def test_strict_stroke_fields_numbers_coordinates_and_bounds(key, value):
    with pytest.raises(ValueError):
        P.append(None, SOURCE, [stroke(**{key: value})])


@pytest.mark.parametrize('extra', [
    {'source': SOURCE}, {'mask': {}}, {'alpha': [[1.]]}, {'pixels': 'copied-source'},
    {'axes': [[1., 0.], [0., 1.]]}, {'kind': 'full'}, {'enabled': False},
])
def test_stroke_cannot_supply_pixels_masks_source_or_recipe_fields(extra):
    with pytest.raises(ValueError):
        P.append(None, SOURCE, [stroke(**extra)])


def test_missing_field_and_empty_or_oversized_batch_are_rejected():
    missing = stroke()
    missing.pop('feather')
    for raw in ([missing], [], (), None, [stroke(str(n)) for n in range(64)]):
        with pytest.raises(ValueError):
            P.append(None, SOURCE, raw)


def test_closed_numeric_endpoints_and_source_edge_points_are_admitted():
    result = P.append(None, SOURCE, [
        stroke('minimum', radius=.0001, opacity=0., feather=0., points=[[0., 0.]]),
        stroke('maximum', 'restore', radius=.5, opacity=1., feather=100., points=[[1., 1.]]),
    ])
    assert len(result['mask']['recipe']['objects']) == 3


def test_retained_objects_and_all_points_share_the_existing_hard_budgets():
    result = P.append(None, SOURCE, [stroke(str(n)) for n in range(63)])
    assert len(result['mask']['recipe']['objects']) == 64
    with pytest.raises(ValueError):
        P.append(result, SOURCE, [stroke('too-many')])
    points = [[.5, .5]] * 1024
    result = P.append(None, SOURCE, [stroke(str(n), points=points) for n in range(8)])
    assert sum(len(obj.get('points', [])) for obj in result['mask']['recipe']['objects']) == 8192
    with pytest.raises(ValueError):
        P.append(result, SOURCE, [stroke('one-extra', points=[[.5, .5]])])
    with pytest.raises(ValueError):
        P.append(None, SOURCE, [stroke(str(n), points=points) for n in range(9)])


def test_duplicate_new_or_retained_ids_are_rejected_without_mutation():
    with pytest.raises(ValueError):
        P.append(None, SOURCE, [stroke(), stroke()])
    old = manual()
    before = deepcopy(old)
    with pytest.raises(ValueError):
        P.append(old, SOURCE, [stroke('manual')])
    assert old == before


@pytest.mark.parametrize('source', [
    None, {**SOURCE, 'sha256': 'b' * 64}, {**SOURCE, 'width': 81},
    {**SOURCE, 'height': 41}, {**SOURCE, 'height': True},
])
def test_foreign_source_or_missing_identity_cannot_adopt_reviewed_coverage(source):
    with pytest.raises(ValueError):
        P.append(manual(), source, [stroke()])


def test_oversized_source_fails_even_when_only_tiny_display_strokes_are_present():
    with pytest.raises(ValueError):
        P.append(None, {**SOURCE, 'width': 65537}, [stroke()])


def test_true_source_work_admission_runs_before_binding_is_returned(monkeypatch):
    calls = []

    def reject(recipe, shape):
        calls.append((deepcopy(recipe), shape))
        raise ValueError('Synthetic full-source raster work refusal')

    monkeypatch.setattr(R, 'validate_budget', reject)
    with pytest.raises(ValueError, match='full-source'):
        P.append(None, SOURCE, [stroke()])
    assert len(calls) == 1 and calls[0][1] == (40, 80)
    assert len(calls[0][0]['objects']) == 2


@pytest.mark.parametrize('change', [
    lambda value: value.update(version=1),
    lambda value: value['mask']['recipe']['objects'][0].update(id='client-full'),
    lambda value: value['mask']['recipe']['objects'][0].update(name='Client full'),
    lambda value: value['mask']['recipe']['objects'].reverse(),
    lambda value: value['mask']['recipe']['objects'].pop(),
])
def test_full_base_requires_v2_exact_canonical_identity_and_first_position(change):
    result = P.append(None, SOURCE, [stroke()])
    change(result)
    with pytest.raises(ValueError):
        C.check_binding(redigest(result))


def test_v2_still_rejects_semantic_coverage_and_digest_tampering():
    result = P.append(None, SOURCE, [stroke()])
    result['mask']['recipe']['objects'][-1] = {
        'id': 'semantic', 'name': 'Not spill evidence', 'kind': 'semantic',
        'enabled': False, 'operation': 'add', 'channel': 'hair',
        'opacity': 1., 'feather': 0.,
    }
    with pytest.raises(ValueError):
        C.check_binding(redigest(result))
    result = P.append(None, SOURCE, [stroke()])
    result['mask']['recipe']['objects'][-1]['points'][0][0] = .9
    with pytest.raises(ValueError):
        C.check_binding(result)


def test_v2_replay_uses_existing_recipe_raster_on_requested_source_grid(monkeypatch):
    value = P.append(None, SOURCE, [stroke(), stroke('restore', 'restore')])
    calls = []

    def raster(recipe, shape):
        calls.append((deepcopy(recipe), shape))
        return np.full(shape, 128, dtype=np.uint8)

    monkeypatch.setattr(R, 'raster', raster)
    field = C.raster(value, (40, 80), source=SOURCE, full_source=True)
    assert calls == [(value['mask']['recipe'], (40, 80))]
    assert field.dtype == np.float32 and field.shape == (40, 80)
    np.testing.assert_array_equal(field, np.full((40, 80), 128 / 255., dtype=np.float32))
    with pytest.raises(ValueError):
        C.raster(value, (20, 40), source=SOURCE, full_source=True)
    with pytest.raises(ValueError):
        C.raster(value, (80, 160), source=SOURCE)
    with pytest.raises(ValueError):
        C.raster(value, (40, 80), source={**SOURCE, 'sha256': 'b' * 64})
    with pytest.raises(InterruptedError):
        C.raster(value, (40, 80), source=SOURCE, cancelled=lambda: True)
    assert len(calls) == 1


def test_native_repeated_partial_restore_uses_max_not_cumulative_addition_unrun():
    """Real Rust replay when run later; no numerical backend double or fallback."""
    source = {**SOURCE, 'width': 4, 'height': 4}
    geometry = {'points': [[.375, .375]], 'radius': .25, 'feather': 0.}
    erased = P.append(None, source, [stroke('erase-all', opacity=1., **geometry)])
    once = P.append(erased, source, [stroke('restore-once', 'restore', opacity=.5, **geometry)])
    twice = P.append(once, source, [stroke('restore-twice', 'restore', opacity=.5, **geometry)])
    once_field = C.raster(once, (4, 4), source=source, full_source=True)
    twice_field = C.raster(twice, (4, 4), source=source, full_source=True)
    np.testing.assert_array_equal(once_field, twice_field)
    assert twice_field[1, 1] == np.float32(128 / 255.)
    assert twice_field[3, 3] == 1.
    # Subtract is deliberately different: two partial erase strokes accumulate
    # in retained float composition before the final 8-bit coverage quantization.
    erased_twice = P.append(twice, source, [
        stroke('erase-partial-1', opacity=.25, **geometry),
        stroke('erase-partial-2', opacity=.25, **geometry),
    ])
    assert C.raster(erased_twice, (4, 4), source=source, full_source=True)[1, 1] == 0.
