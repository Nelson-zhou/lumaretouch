# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN facial-colour-evenness ownership/support contracts.

No imports, collection, execution, tests, inference, builds or typechecks were
run during authoring. Synthetic arrays and digests are schema fixtures, NOT real
detector evidence or photographic acceptance. Real face/semantic validation,
anatomical rasterization, source admission and budget paths are exercised; only
native available/prepare/apply numerical boundaries are doubled. These doubles
do not prove the Rust robust reference, guided filter, ABI or image quality.
"""
from copy import deepcopy
import hashlib
from unittest.mock import patch

import numpy as np
import pytest

from lumaretouch_engine import face_scope as FACE
from lumaretouch_engine import people_effects as EFFECTS
from lumaretouch_engine import skin_colour_support as SUPPORT
from lumaretouch_engine import skin_evenness_layer as L, skin_evenness_native as N
from lumaretouch_engine import skin_evenness_state as S
from lumaretouch_engine.ops.enhance import EYE_RING_LEFT, EYE_RING_RIGHT

ACTIVE = {'version': 1, 'amount': .6}
BUDGET = 512*1024**2
LUMA = np.array([.2126, .7152, .0722], np.float64)


def synthetic_observation(size=256, *, producer_size=64, source_size=1024):
    """Synthetic topology with genuine validators, not authentic model output.

    The durable, producer and current grids intentionally differ. Source-size
    metadata is explicit so integration callers can bind actual test RGB bytes
    without claiming a small fixture is an original-resolution photograph.
    """
    lm = np.full((478, 3), [.5, .48, 0.], dtype='<f4')
    def ellipse(indices, cx, cy, rx, ry):
        theta = np.linspace(-np.pi/2, 3*np.pi/2, len(indices), endpoint=False)
        lm[list(indices), :2] = np.column_stack((cx+rx*np.cos(theta), cy+ry*np.sin(theta)))
    ellipse(FACE.FACE_OVAL, .5, .48, .32, .42)
    ellipse(EYE_RING_LEFT, .37, .39, .052, .025)
    ellipse(EYE_RING_RIGHT, .63, .39, .052, .025)
    ellipse(FACE.BROW_LEFT, .63, .30, .065, .022)
    ellipse(FACE.BROW_RIGHT, .37, .30, .065, .022)
    ellipse(FACE.LIPS, .5, .69, .085, .035)
    ref = {'asset_sha256': 'a'*64, 'face_instance_id': 'synthetic-evenness-face',
           'analysis_revision': 0}
    evidence = {
        'backend': 'mediapipe', 'detector_model_sha256': 'b'*64,
        'semantic_model_sha256': 'c'*64, 'landmark_digest': hashlib.sha256(lm.tobytes()).hexdigest(),
        'status': 'verified', 'source_width': source_size, 'source_height': source_size,
        'orientation': 'exif_normalized_once',
    }
    yy, xx = np.mgrid[:size, :size]
    source = np.empty((size, size, 3), np.float32)
    source[..., 0] = .56+.04*np.sin(xx/max(1., size*.17))
    source[..., 1] = .42+.025*yy/size
    source[..., 2] = .34+.02*np.cos(yy/max(1., size*.21))
    analysis = {
        'face_ref': deepcopy(ref), 'evidence': evidence, 'landmarks': lm,
        'excluded': np.zeros((size, size), np.float32),
        # Deliberately broad merged skin is not the permission for this effect.
        'skin': np.ones((size, size), np.float32),
        'face_skin': np.full((size, size), .9, np.float32),
        'face_skin_observation': {
            'contract': SUPPORT.CONTRACT, 'source_sha256': ref['asset_sha256'],
            'semantic_model_sha256': evidence['semantic_model_sha256'],
            'producer_width': producer_size, 'producer_height': producer_size,
        },
    }
    return ref, analysis, source


def native_prepare_double(calls):
    """Small source-dependent HWC2 mark, NOT a robust/guided native solver."""
    def prepare(source_rgb, coverage, amount, *, radius, cancelled=None):
        assert source_rgb.dtype == coverage.dtype == np.float32
        assert source_rgb.shape[:2] == coverage.shape
        assert not source_rgb.flags.writeable and not coverage.flags.writeable
        assert source_rgb.flags.c_contiguous and coverage.flags.c_contiguous
        assert type(radius) is int and 4 <= radius <= 256
        if cancelled is not None and cancelled():
            raise InterruptedError('Synthetic native prepare cancelled')
        calls.append({'source': source_rgb.copy(), 'coverage': coverage.copy(),
                      'amount': amount, 'radius': radius})
        # Test the admission boundary, not the hidden reference/filter solution.
        _, observable = L._reference_admission(source_rgb, coverage)
        field = np.zeros((*coverage.shape, 2), np.float32)
        field[..., 0] = coverage * observable * np.float32(.018*amount) * source_rgb[..., 0]
        field[..., 1] = coverage * observable * np.float32(-.014*amount) * source_rgb[..., 2]
        field.setflags(write=False)
        return field
    return prepare


def _linear(rgb):
    rgb = np.asarray(rgb, dtype=np.float64)
    return np.where(rgb <= .04045, rgb/12.92, ((rgb+.055)/1.055)**2.4)


def native_apply_double(calls=None):
    """Pointwise current-Y-preserving boundary double, not ABI/GPU acceptance."""
    def apply(current_rgb, shift, *, cancelled=None):
        if cancelled is not None and cancelled():
            raise InterruptedError('Synthetic native apply cancelled')
        if calls is not None:
            calls.append({'current': current_rgb.copy(), 'shift': shift.copy()})
        linear = _linear(current_rgb)
        y = linear @ LUMA
        field = shift.astype(np.float64)
        multiplier = np.stack((np.exp(field[..., 0]), np.ones(y.shape), np.exp(field[..., 1])), axis=2)
        changed = linear*multiplier
        changed_y = changed @ LUMA
        changed *= np.divide(y, changed_y, out=np.ones_like(y), where=changed_y > 0)[..., None]
        # Common-vector contraction toward current RGB, never channel clipping
        # that would change Y. This is a numerical pointwise boundary double.
        delta = changed-linear
        safe = np.where(delta != 0, delta, 1.)
        bound = np.where(delta > 0, (1.-linear)/safe,
                         np.where(delta < 0, -linear/safe, 1.))
        scale = np.minimum(1., np.min(bound, axis=2))
        scale = np.where(scale < 1., scale*(1.-1e-12), scale)
        changed = linear+delta*scale[..., None]
        encoded = np.where(changed <= .0031308, changed*12.92, 1.055*changed**(1/2.4)-.055)
        changed_pixels = (np.any(shift != 0, axis=2) & np.any(delta != 0, axis=2)
                          & (scale > 0) & ~np.all(current_rgb == 0, axis=2)
                          & ~np.all(current_rgb == 1, axis=2))
        output = np.array(np.where(changed_pixels[..., None], encoded, current_rgb),
                          dtype=np.float32, order='C', copy=True)
        return output
    return apply


def prepare(ref, analysis, source, **kwargs):
    calls = []
    with patch.object(N, 'available', return_value=True), \
            patch.object(N, 'prepare', side_effect=native_prepare_double(calls)):
        records = L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET, **kwargs)
    return records, calls


def full_coverage(record, call, shape):
    coverage = np.zeros(shape, np.float32)
    y, x, h, w = record.window
    coverage[y:y+h, x:x+w] = call['coverage']
    return coverage


def _redigest(analysis):
    analysis['evidence']['landmark_digest'] = hashlib.sha256(
        np.ascontiguousarray(analysis['landmarks'], dtype='<f4').tobytes()).hexdigest()


def test_exact_zero_bypasses_source_support_budget_and_native_work():
    with patch.object(N, 'available', side_effect=AssertionError('neutral native probe')), \
            patch.object(N, 'prepare', side_effect=AssertionError('neutral native solve')), \
            patch.object(N, 'apply', side_effect=AssertionError('neutral native application')):
        assert L.prepare(None, None, None, S.neutral(), byte_budget=0,
                         protected_boxes='unused', cancelled='unused') == []


def test_real_validators_admit_owned_readonly_two_channel_field_without_rgb_delta():
    ref, analysis, source = synthetic_observation()
    source_before = source.copy()
    skin_before = analysis['face_skin'].copy()
    excluded_before = analysis['excluded'].copy()
    records, calls = prepare(ref, analysis, source)
    assert len(records) == len(calls) == 1
    record = records[0]
    y, x, h, w = record.window
    assert record.stage == 'skin_evenness' and record.face_ref == ref
    assert record.delta is None and record.chroma_shift.shape == (h, w, 2)
    assert record.chroma_shift.dtype == np.float32 and not record.chroma_shift.flags.writeable
    assert record.chroma_shift.flags.c_contiguous
    np.testing.assert_array_equal(calls[0]['source'], source[y:y+h, x:x+w])
    assert not np.shares_memory(record.chroma_shift, source)
    assert record.facts['source_dimensions'] == [1024, 1024]
    assert record.facts['render_dimensions'] == [256, 256]
    assert record.facts['face_skin_observation']['producer_width'] == 64
    assert record.facts['reference_samples'] >= 64
    assert record.facts['review'] == 'explicit-strength-and-canonical-before-after'
    assert record.facts['body_extension'] == {'enabled': False}
    assert record.facts['reason'] is None
    np.testing.assert_array_equal(source, source_before)
    np.testing.assert_array_equal(analysis['face_skin'], skin_before)
    np.testing.assert_array_equal(analysis['excluded'], excluded_before)


def test_current_source_window_keeps_all_own_samples_and_true_two_radius_halo():
    ref, analysis, source = synthetic_observation(size=512)
    # Smaller face well inside image makes unnecessary full-frame work visible.
    analysis['landmarks'][:, :2] = .5+(analysis['landmarks'][:, :2]-.5)*.6
    _redigest(analysis)
    records, calls = prepare(ref, analysis, source)
    record, call = records[0], calls[0]
    y, x, h, w = record.window
    assert 0 < x and 0 < y and x+w < 512 and y+h < 512
    assert h*w < 512**2
    oval = analysis['landmarks'][list(FACE.FACE_OVAL), :2]*512
    halo = 2*call['radius']+1
    assert x <= np.floor(oval[:, 0].min())-halo
    assert y <= np.floor(oval[:, 1].min())-halo
    assert x+w >= np.ceil(oval[:, 0].max())+1+halo
    assert y+h >= np.ceil(oval[:, 1].max())+1+halo
    np.testing.assert_array_equal(call['source'], source[y:y+h, x:x+w])
    coverage = full_coverage(record, call, source.shape[:2])
    raw = FACE.selected_face_skin(analysis['face_skin'], analysis['landmarks'])
    assert np.all(coverage <= raw)
    assert not np.any(raw[:y]) and not np.any(raw[y+h:])
    assert not np.any(raw[:, :x]) and not np.any(raw[:, x+w:])


def test_anatomy_eyes_brows_lips_outer_footprints_and_semantic_holes_stay_zero():
    ref, analysis, source = synthetic_observation()
    analysis['face_skin'][130:143, 111:127] = 0
    analysis['excluded'][142:150, 151:170] = 1
    records, calls = prepare(ref, analysis, source)
    coverage = full_coverage(records[0], calls[0], source.shape[:2])
    assert not np.any(coverage[130:143, 111:127])
    assert not np.any(coverage[142:150, 151:170])
    for indices in (EYE_RING_LEFT, EYE_RING_RIGHT, FACE.BROW_LEFT, FACE.BROW_RIGHT, FACE.LIPS):
        x, y = analysis['landmarks'][list(indices), :2].mean(axis=0)*256
        assert coverage[int(y), int(x)] == 0
    xx = np.arange(256, dtype=np.float64)[None, :]+.5
    yy = np.arange(256, dtype=np.float64)[:, None]+.5
    oval = analysis['landmarks'][list(FACE.FACE_OVAL), :2]*256
    inside, distance = FACE._polygon_field(xx, yy, oval)
    assert not np.any(coverage[~inside | (distance <= np.sqrt(.5))])
    assert not np.any(coverage[235:])  # No body extension from merged skin.
    assert not np.any(records[0].chroma_shift[calls[0]['coverage'] == 0])


def test_all_retained_foreign_boxes_are_protection_not_ownership_or_reference():
    ref, analysis, source = synthetic_observation()
    # Runtime must supply enabled, disabled and unresolved retained neighbours.
    # The layer neither filters them nor invents landmark/identity matches.
    boxes = [(.22, .46, .35, .66), (.65, .46, .78, .66)]
    records, calls = prepare(ref, analysis, source, protected_boxes=boxes)
    coverage = full_coverage(records[0], calls[0], source.shape[:2])
    assert records[0].facts['protected_face_boxes'] == 2
    for left, top, right, bottom in boxes:
        assert not np.any(coverage[int(np.ceil(top*256)):int(np.floor(bottom*256)),
                                   int(np.ceil(left*256)):int(np.floor(right*256))])
    assert np.any(coverage[120:160, 110:140])
    with patch.object(N, 'prepare', side_effect=AssertionError('fully protected face reached native')):
        with pytest.raises(ValueError, match='reference samples'):
            L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET,
                      protected_boxes=[(.15, .02, .85, .95)])


@pytest.mark.parametrize('box', [(0, 0, 0, 1), (-.1, 0, .5, 1), (0, 0, 2, 1),
                                (0, 0, float('nan'), 1), (False, 0, .5, 1), (0, 0, .5)])
def test_invalid_foreign_box_is_not_silently_ignored(box):
    ref, analysis, source = synthetic_observation()
    with patch.object(N, 'prepare', side_effect=AssertionError('invalid box reached native')):
        with pytest.raises(ValueError):
            L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET, protected_boxes=[box])


@pytest.mark.parametrize('fault', [
    'ref', 'backend', 'status', 'detector', 'semantic', 'digest', 'landmarks', 'aspect',
    'missing_skin', 'unpaired', 'observation_source', 'observation_model', 'observation_contract',
    'producer_zero', 'producer_bool', 'skin_grid', 'skin_dtype', 'skin_nan', 'skin_range',
    'excluded_missing', 'excluded_grid', 'excluded_dtype', 'excluded_nan', 'excluded_range',
])
def test_forged_missing_stale_and_cross_source_evidence_refuses_before_native(fault):
    ref, analysis, source = synthetic_observation()
    if fault == 'ref': analysis['face_ref']['analysis_revision'] += 1
    elif fault == 'backend': analysis['evidence']['backend'] = 'template'
    elif fault == 'status': analysis['evidence']['status'] = 'synthetic'
    elif fault == 'detector': analysis['evidence']['detector_model_sha256'] = None
    elif fault == 'semantic': analysis['evidence']['semantic_model_sha256'] = None
    elif fault == 'digest': analysis['evidence']['landmark_digest'] = 'f'*64
    elif fault == 'landmarks': analysis['landmarks'][10, 0] += .01
    elif fault == 'aspect': analysis['evidence']['source_width'] = 512
    elif fault == 'missing_skin':
        analysis.pop('face_skin'); analysis.pop('face_skin_observation')
    elif fault == 'unpaired': analysis.pop('face_skin_observation')
    elif fault == 'observation_source': analysis['face_skin_observation']['source_sha256'] = 'e'*64
    elif fault == 'observation_model': analysis['face_skin_observation']['semantic_model_sha256'] = 'e'*64
    elif fault == 'observation_contract': analysis['face_skin_observation']['contract'] = 'merged-skin'
    elif fault == 'producer_zero': analysis['face_skin_observation']['producer_width'] = 0
    elif fault == 'producer_bool': analysis['face_skin_observation']['producer_height'] = True
    elif fault == 'skin_grid': analysis['face_skin'] = np.ones((64, 64), np.float32)
    elif fault == 'skin_dtype': analysis['face_skin'] = analysis['face_skin'].astype(np.float64)
    elif fault == 'skin_nan': analysis['face_skin'][0, 0] = np.nan
    elif fault == 'skin_range': analysis['face_skin'][0, 0] = 1.1
    elif fault == 'excluded_missing': analysis['excluded'] = None
    elif fault == 'excluded_grid': analysis['excluded'] = np.zeros((64, 64), np.float32)
    elif fault == 'excluded_dtype': analysis['excluded'] = analysis['excluded'].astype(np.float64)
    elif fault == 'excluded_nan': analysis['excluded'][0, 0] = np.nan
    elif fault == 'excluded_range': analysis['excluded'][0, 0] = -.1
    with patch.object(N, 'prepare', side_effect=AssertionError('invalid evidence reached native')) as native:
        with pytest.raises(ValueError):
            L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET)
    native.assert_not_called()


@pytest.mark.parametrize('rgb', [[0., 0., 0.], [.09, .09, .09], [.999, .999, .999],
                                [.5, .4, .01]])
def test_missing_photometric_reference_is_refusal_not_successful_identity(rgb):
    ref, analysis, source = synthetic_observation()
    source[:] = rgb
    with patch.object(N, 'prepare', side_effect=AssertionError('missing reference reached native')) as native:
        with pytest.raises(ValueError, match='reference samples'):
            L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET)
    native.assert_not_called()


def test_low_confidence_or_foreign_only_usable_samples_cannot_supply_reference():
    ref, analysis, source = synthetic_observation()
    analysis['face_skin'][:] = .7
    with pytest.raises(ValueError, match='reference samples'):
        L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET)
    analysis['face_skin'][:] = .9
    source[:] = .01
    source[120:160, 95:145] = [.56, .42, .34]
    with pytest.raises(ValueError, match='reference samples'):
        L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET,
                  protected_boxes=[(95/256, 120/256, 145/256, 160/256)])


def test_partly_unobservable_source_is_zero_in_field_not_silently_filled():
    ref, analysis, source = synthetic_observation()
    source[125:144, 115:136] = .001
    records, calls = prepare(ref, analysis, source)
    y, x, _, _ = records[0].window
    assert not np.any(records[0].chroma_shift[125-y:144-y, 115-x:136-x])
    assert np.any(calls[0]['coverage'][125-y:144-y, 115-x:136-x])


def test_exact_sample_admission_threshold_is_not_weight_mass_or_a_fabricated_reference():
    source = np.full((8, 8, 3), [.56, .42, .34], np.float32)
    coverage = np.ones((8, 8), np.float32)
    count, observable = L._reference_admission(source, coverage)
    assert count == 64 and np.all(observable)
    coverage[0, 0] = .74
    with pytest.raises(ValueError, match='reference samples'):
        L._reference_admission(source, coverage)


@pytest.mark.parametrize('fault', ['nan', 'low', 'high', 'dtype', 'channels'])
def test_invalid_current_source_rgb_is_refused_not_clipped_or_coerced(fault):
    ref, analysis, source = synthetic_observation()
    if fault == 'nan': source[0, 0, 0] = np.nan
    elif fault == 'low': source[0, 0, 0] = -.01
    elif fault == 'high': source[0, 0, 0] = 1.01
    elif fault == 'dtype': source = source.astype(np.float64)
    elif fault == 'channels': source = source[..., :2]
    with patch.object(N, 'prepare', side_effect=AssertionError('invalid source reached native')) as native:
        with pytest.raises(ValueError):
            L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET)
    native.assert_not_called()


def test_small_source_and_degenerate_geometry_refuse_without_scale_fallback():
    ref, analysis, source = synthetic_observation(size=32)
    with pytest.raises(ValueError, match='radius'):
        L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET)
    ref, analysis, source = synthetic_observation()
    analysis['landmarks'][:, :2] = .5
    _redigest(analysis)
    with pytest.raises(ValueError, match='radius'):
        L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET)


def test_full_grid_and_source_window_budgets_precede_large_array_validation():
    ref, analysis, source = synthetic_observation()
    # Invalid evidence/source would fail differently if large validation began.
    source[0, 0] = np.nan
    baseline = source.shape[0]*source.shape[1]*L._HOST_BYTES_PER_PIXEL+L._FIXED_BYTES
    with pytest.raises(ValueError, match='source validation exceeds memory budget before allocation'):
        L.prepare(None, None, source, ACTIVE, byte_budget=1)
    with pytest.raises(ValueError, match='source-window working set exceeds memory budget before allocation'):
        L.prepare(ref, analysis, source, ACTIVE, byte_budget=baseline)


@pytest.mark.parametrize('fault', ['shape', 'dtype', 'nan', 'protected', 'vector_bound', 'unobservable'])
def test_invalid_native_field_cannot_publish_an_rgb_delta_or_protected_change(fault):
    ref, analysis, source = synthetic_observation()
    source[130:134, 120:124] = .001
    def invalid(rgb, coverage, amount, *, radius, cancelled=None):
        if fault == 'shape': return np.zeros(rgb.shape, np.float32)
        if fault == 'dtype': return np.zeros((*coverage.shape, 2), np.float64)
        field = np.zeros((*coverage.shape, 2), np.float32)
        if fault == 'nan': field[0, 0, 0] = np.nan
        elif fault == 'protected': field[tuple(np.argwhere(coverage == 0)[0])][0] = .01
        elif fault == 'vector_bound': field[tuple(np.argwhere(coverage >= .8)[0])] = [.08, .08]
        elif fault == 'unobservable':
            _, observable = L._reference_admission(rgb, coverage)
            field[tuple(np.argwhere((coverage > 0) & ~observable)[0])][0] = .01
        return field
    with patch.object(N, 'available', return_value=True), patch.object(N, 'prepare', side_effect=invalid):
        with pytest.raises(ValueError):
            L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET)


def test_native_identity_with_real_reference_is_not_a_missing_reference_claim():
    ref, analysis, source = synthetic_observation()
    with patch.object(N, 'available', return_value=True), \
            patch.object(N, 'prepare', side_effect=lambda rgb, coverage, *a, **k:
                         np.zeros((*coverage.shape, 2), np.float32)):
        record = L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET)[0]
    assert record.facts['reason'] == 'no-source-chroma-correction'
    assert record.facts['reference_samples'] >= 64 and not np.any(record.chroma_shift)


@pytest.mark.parametrize('message', ['missing reliable reference', 'insufficient guided context'])
def test_native_reference_or_context_refusal_never_becomes_zero_success(message):
    ref, analysis, source = synthetic_observation()
    with patch.object(N, 'available', return_value=True), \
            patch.object(N, 'prepare', side_effect=ValueError(message)):
        with pytest.raises(ValueError, match=message):
            L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET)


def test_missing_native_and_cancellation_never_publish_partial_field():
    ref, analysis, source = synthetic_observation()
    with patch.object(N, 'available', return_value=False):
        with pytest.raises(RuntimeError, match='unavailable'):
            L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET)
    with patch.object(N, 'prepare', side_effect=AssertionError('cancelled source reached native')):
        with pytest.raises(InterruptedError):
            L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET, cancelled=lambda: True)
    cancelled = [False]
    def cancel_after_prepare(rgb, coverage, *a, **k):
        cancelled[0] = True
        return np.zeros((*coverage.shape, 2), np.float32)
    with patch.object(N, 'available', return_value=True), patch.object(N, 'prepare', side_effect=cancel_after_prepare):
        with pytest.raises(InterruptedError):
            L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET, cancelled=lambda: cancelled[0])


def test_rebuild_changes_actual_source_scale_not_the_retained_producer_dimensions():
    ref, analysis, source = synthetic_observation(size=256, producer_size=64)
    small, small_calls = prepare(ref, analysis, source)
    ref, analysis, source = synthetic_observation(size=512, producer_size=64)
    large, large_calls = prepare(ref, analysis, source)
    assert large_calls[0]['radius'] > small_calls[0]['radius']
    assert large[0].facts['render_dimensions'] == [512, 512]
    assert large[0].facts['source_dimensions'] == [1024, 1024]
    assert large[0].facts['face_skin_observation']['producer_width'] == 64
    assert large[0].chroma_shift.shape[:2] != small[0].chroma_shift.shape[:2]


def test_prepared_field_applies_to_current_stage_without_rerunning_source_estimation():
    ref, analysis, source = synthetic_observation()
    records, calls = prepare(ref, analysis, source)
    current = np.array(source*.78+np.array([.04, .03, .02], np.float32), dtype=np.float32)
    before = current.copy()
    application_calls = []
    with patch.object(N, 'prepare', side_effect=AssertionError('pointwise stage recomputed source reference')), \
            patch.object(N, 'apply', side_effect=native_apply_double(application_calls)):
        output, facts = EFFECTS.apply('skin_evenness', current, records)
    assert len(calls) == len(application_calls) == 1
    y, x, h, w = records[0].window
    np.testing.assert_array_equal(application_calls[0]['current'], current[y:y+h, x:x+w])
    np.testing.assert_allclose(_linear(output) @ LUMA, _linear(current) @ LUMA, atol=1e-7, rtol=0)
    np.testing.assert_array_equal(current, before)
    coverage = full_coverage(records[0], calls[0], current.shape[:2])
    np.testing.assert_array_equal(output[coverage == 0], current[coverage == 0])
    assert np.any(output != current) and facts['stage'] == 'skin_evenness'


def test_native_owned_output_cannot_alias_published_field_or_future_source_changes():
    ref, analysis, source = synthetic_observation()
    retained = []
    def capture(rgb, coverage, *a, **k):
        result = native_prepare_double([])(rgb, coverage, *a, **k)
        result.setflags(write=True)
        retained.append(result)
        return result
    with patch.object(N, 'available', return_value=True), patch.object(N, 'prepare', side_effect=capture):
        record = L.prepare(ref, analysis, source, ACTIVE, byte_budget=BUDGET)[0]
    before = record.chroma_shift.copy()
    source[:] = 0; analysis['face_skin'][:] = 0; retained[0][:] = 0
    np.testing.assert_array_equal(record.chroma_shift, before)
    assert not np.shares_memory(record.chroma_shift, retained[0])
