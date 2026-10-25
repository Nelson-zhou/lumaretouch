# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: runtime protocol fixtures, not photographic acceptance.

Neither collection nor product imports have been executed in this lane. The
fit/apply doubles below expose routing and transactions, not Rust mathematics.
Real numerical tests live in test_skin_reference_match_native_unrun.py.
"""
from dataclasses import FrozenInstanceError, replace
import hashlib

import numpy as np
import pytest

from lumaretouch_engine import people_state as P, face_scope as FACE
from lumaretouch_engine import skin_reference_match_state as S
from lumaretouch_engine import skin_reference_match_support as A
from lumaretouch_engine import skin_reference_match_native as N
from lumaretouch_engine import skin_reference_match_runtime as R
from lumaretouch_engine import skin_reference_match_composition as C
from lumaretouch_engine.portrait_fit_source import FullSource

BUDGET = 4 * 1024**3
SHA = 'a' * 64
SHAPE = (48, 64)
WINDOWS = {'target1': (4, 4, 12, 10), 'target2': (27, 20, 10, 12),
           'reference': (10, 43, 14, 12)}


def measured(reference_shape, target_shape):
    rc, tc = float(np.prod(reference_shape)), float(np.prod(target_shape))
    return N.MeasuredFit(tuple(reference_shape), tuple(target_shape),
        (N.MAX_LOG_LUMINANCE, N.MAX_LOG_CHROMA), (1., .1, .02, -.01),
        (1., rc, tc, rc, tc, rc, tc, -1.9, .12, -.21, -2., .1, -.2,
         .01, .01, .01, .01, .01, .01, .1, .02, -.01, 0., 1.)).checked()


def sample_bank(*, targets=1):
    state = P.empty(); analyses = {}
    for index, key in enumerate(('target1', 'target2', 'reference')):
        cx = (.16, .40, .78)[index]
        landmarks = np.full((478, 3), (cx, .45, 0), dtype=np.float32)
        for i, landmark in enumerate(FACE.FACE_OVAL):
            angle = 2*np.pi*i/len(FACE.FACE_OVAL)
            landmarks[landmark, :2] = (cx+.10*np.cos(angle), .45+.15*np.sin(angle))
        evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b'*64,
            'semantic_model_sha256': 'c'*64, 'landmark_digest': hashlib.sha256(landmarks.tobytes()).hexdigest(),
            'status': 'verified', 'source_width': SHAPE[1], 'source_height': SHAPE[0],
            'orientation': 'exif_normalized_once'}
        face = P.new_face(SHA, [cx-.11, .25, cx+.11, .65], evidence)
        face['face_instance_id'] = key; state['faces'][key] = face
        analyses[key] = {'face_ref': P.face_ref(face), 'evidence': evidence, 'landmarks': landmarks,
            'face_skin': np.ones(SHAPE, dtype=np.float32), 'excluded': np.zeros(SHAPE, dtype=np.float32),
            'face_skin_observation': {'contract': 'mediapipe-face-skin-edit-weight-v1',
                'source_sha256': SHA, 'semantic_model_sha256': 'c'*64,
                'producer_width': SHAPE[1], 'producer_height': SHAPE[0]}}
    assets = {}; donor = P.face_ref(state['faces']['reference'])
    for key in ('target1', 'target2')[:targets]:
        state, assets = A.retain(state, assets, P.face_ref(state['faces'][key]), donor,
                                analyses[key], analyses['reference'], confirmed=True)
        state = P.set_override(state, 'face', key, S.OP, '/amount', .7)
    pixels = np.linspace(.1, .8, np.prod(SHAPE)*3, dtype=np.float32).reshape(*SHAPE, 3)
    content = pixels.tobytes(); digest = hashlib.sha256(content).hexdigest()
    source = FullSource(SHA, SHAPE[1], SHAPE[0], digest, 16, 'original', len(content), content)
    return state, assets, analyses, source


@pytest.fixture
def protocol(monkeypatch):
    calls = {'fit': [], 'geometry': [], 'apply': []}
    monkeypatch.setattr(R, 'available_estimate', lambda: BUDGET)
    monkeypatch.setattr(C, 'available_estimate', lambda: BUDGET)
    def geometry(state, assets, ref, target_row, donor_row, shape, *, byte_budget, cancelled):
        assert byte_budget > 0
        assert target_row['face_skin'].shape == donor_row['face_skin'].shape == shape
        assert target_row['face_skin_observation']['producer_width'] == SHAPE[1]
        record, key = A.resolve(state, assets, ref, target_row, donor_row)
        masks, details = [], {}
        for name, face_id in (('target', ref['face_instance_id']), ('reference', 'reference')):
            y, x, h, w = WINDOWS[face_id]
            window = (y*shape[0]//SHAPE[0], x*shape[1]//SHAPE[1],
                      max(1, h*shape[0]//SHAPE[0]), max(1, w*shape[1]//SHAPE[1]))
            y, x, h, w = window
            mask = np.zeros(shape, dtype=np.float32); mask[y:y+h, x:x+w] = 1
            mask.setflags(write=False); masks.append(mask)
            details[name] = {'source_window': list(window)}
        calls['geometry'].append((ref['face_instance_id'], shape, state))
        return *masks, {'source': record['source'], 'support_sha256': key, **details}
    def fit(reference, reference_weight, target, target_weight, *, byte_budget, cancelled):
        assert byte_budget > 0 and not cancelled()
        assert not reference.flags.writeable and not target.flags.writeable
        calls['fit'].append((reference.copy(), reference_weight.copy(), target.copy(), target_weight.copy()))
        return measured(reference.shape[:2], target.shape[:2])
    def apply(current, coverage, measured_fit, amount, *, byte_budget, cancelled):
        assert byte_budget > 0 and not cancelled()
        calls['apply'].append((current.copy(), coverage.copy(), measured_fit, amount))
        result = current.copy(); take = coverage > 0
        take &= ~np.all(current == 0, axis=-1) & ~np.all(current == 1, axis=-1)
        result[take] += np.float32(.01)  # Protocol marker, not the effect algorithm.
        return result
    monkeypatch.setattr(A, 'geometry', geometry)
    monkeypatch.setattr(N, 'fit', fit)
    monkeypatch.setattr(N, 'apply', apply)
    return calls


def prepare(data, *, application_shape=SHAPE):
    state, assets, analyses, source = data
    return R.prepare_bank(state, SHA, source, analyses, assets=assets,
                          application_shape=application_shape, byte_budget=BUDGET)


def test_neutral_needs_no_source_donor_support_or_core(monkeypatch):
    monkeypatch.setattr(N, 'fit', lambda *a, **k: pytest.fail('Neutral must not fit'))
    assert R.prepare_bank(P.empty(), SHA, None, None, assets=None,
        application_shape=None, byte_budget=0) == ((), {})
    current = object()
    assert C.apply_records_np(current, ()) == (current, {'stage': R.STAGE, 'changed_pixels': 0, 'overlap_pixels': 0})


def test_canonical_inheritance_and_conflicts_do_not_use_a_selected_list():
    state, _, _, _ = sample_bank()
    state = P.set_override(state, 'face', 'target1', S.OP, '/amount', 0.)
    state = P.set_override(state, 'all_people', SHA, S.OP, '/amount', .3)
    state['faces']['target2']['enabled'] = False
    assert [ref['face_instance_id'] for ref, _ in R.requests(state, SHA)] == ['reference']
    state['groups'] = {'g1': {'label': 'A', 'priority': 1, 'face_ids': ['reference']},
                       'g2': {'label': 'B', 'priority': 1, 'face_ids': ['reference']}}
    state = P.set_override(state, 'group', 'g1', S.OP, '/amount', .2)
    state = P.set_override(state, 'group', 'g2', S.OP, '/amount', .8)
    with pytest.raises(ValueError, match='conflicting groups'):
        R.requests(state, SHA)


def test_each_target_fits_independent_canonical_rois_once_before_projection(protocol):
    data = sample_bank(targets=2); source = data[3]
    effects, facts = prepare(data, application_shape=(24, 32))
    assert len(effects) == len(protocol['fit']) == 2
    assert [shape for _, shape, _ in protocol['geometry']] == [SHAPE, (24, 32), SHAPE, (24, 32)]
    donor = WINDOWS['reference']; ry, rx, rh, rw = donor
    for record, call in zip(effects, protocol['fit']):
        y, x, h, w = WINDOWS[record.face_ref['face_instance_id']]
        assert np.array_equal(call[0], source.pixels[ry:ry+rh, rx:rx+rw])
        assert np.array_equal(call[2], source.pixels[y:y+h, x:x+w])
        assert call[0].shape != call[2].shape
        assert record.amounts.source_shape == SHAPE
        assert record.amounts.resident_bytes() == 64 * 1024
        assert record.amounts.application_shape == (24, 32)
        assert record.delta is None and record.chroma_shift is None and record.log_gain is None
        assert facts[record.face_ref['face_instance_id']]['fit_count_per_target'] == 1
        with pytest.raises(ValueError):
            record.weights.setflags(write=True)
        with pytest.raises(FrozenInstanceError):
            record.amounts.amount = .4


def test_neutral_donor_analysis_is_still_required(protocol):
    data = sample_bank(); data[2].pop('reference')
    with pytest.raises(ValueError, match='target/reference analysis'):
        prepare(data)
    assert not protocol['fit']


def test_donor_cannot_be_active_or_differ_between_targets(protocol):
    data = list(sample_bank(targets=2))
    data[0] = P.set_override(data[0], 'face', 'reference', S.OP, '/amount', .2)
    with pytest.raises(ValueError):
        prepare(data)
    assert not protocol['fit']
    data = list(sample_bank(targets=2))
    data[0], data[1] = A.retain(data[0], data[1], P.face_ref(data[0]['faces']['target2']),
        P.face_ref(data[0]['faces']['target1']), data[2]['target2'], data[2]['target1'], confirmed=True)
    with pytest.raises(ValueError, match='agree on one'):
        prepare(data)
    assert not protocol['fit']


def test_disabled_other_faces_remain_reserved_in_geometry(protocol):
    data = sample_bank(); data[0]['faces']['target2']['enabled'] = False
    prepare(data)
    for _, _, state in protocol['geometry']:
        assert state['faces']['target2']['enabled'] is False
        assert state['faces']['target2']['box'] == data[0]['faces']['target2']['box']


@pytest.mark.parametrize('alter', ['array', 'hash', 'precision', 'source'])
def test_captured_source_contract_refuses_proxy_forgery(protocol, alter):
    data = list(sample_bank())
    if alter == 'array': data[3] = data[3].pixels
    if alter == 'hash': data[3] = replace(data[3], input_sha256='f'*64)
    if alter == 'precision': data[3] = replace(data[3], source_bits=8, kind='creative')
    if alter == 'source': data[3] = replace(data[3], source_sha256='f'*64)
    with pytest.raises(ValueError):
        prepare(data)
    assert not protocol['fit']


def test_budget_is_refused_before_projection_or_native_fit(protocol, monkeypatch):
    data = sample_bank()
    monkeypatch.setattr(R, '_project', lambda *a: pytest.fail('Preallocation admission must run first'))
    with pytest.raises(MemoryError):
        R.prepare_bank(data[0], SHA, data[3], data[2], assets=data[1],
                       application_shape=SHAPE, byte_budget=1)
    assert not protocol['fit']


def test_current_pixels_not_source_delta_and_crop_parity(protocol):
    records, _ = prepare(sample_bank())
    current = np.full((*SHAPE, 3), .4, dtype=np.float32); current[0, 0, 0] = -0.
    before = current.copy()
    whole, facts = C.apply_records_np(current, records, byte_budget=BUDGET)
    assert facts['changed_pixels'] > 0
    assert np.array_equal(current.view(np.uint32), before.view(np.uint32))
    assert np.array_equal(whole[0].view(np.uint32), before[0].view(np.uint32))
    assert np.all(protocol['apply'][0][0] == np.float32(.4))
    assembled = current.copy()
    for y in range(0, SHAPE[0], 8):
        tile, _ = C.apply_records_np(current[y:y+8], records, source_shape=SHAPE,
                                     origin=(y, 0), byte_budget=BUDGET)
        assembled[y:y+8] = tile
    assert np.array_equal(assembled.view(np.uint32), whole.view(np.uint32))
    assert len(protocol['fit']) == 1


def test_exact_zero_amount_and_outside_coverage_skip_native(protocol):
    records, _ = prepare(sample_bank()); record = records[0]
    current = np.full((*SHAPE, 3), .4, dtype=np.float32)
    neutral = replace(record, amounts=replace(record.amounts, amount=0.))
    assert C.apply_records_np(current, (neutral,), byte_budget=BUDGET)[0] is current
    outside = current[:2]
    assert C.apply_records_np(outside, records, source_shape=SHAPE,
                               byte_budget=BUDGET)[0] is outside
    assert not protocol['apply']


def test_overlap_is_rejected_before_any_native_apply(protocol):
    records, _ = prepare(sample_bank(targets=2)); first, second = records
    params = replace(second.amounts, application_window=first.window,
                     coverage_sha256=first.amounts.coverage_sha256)
    conflicting = replace(second, window=first.window, weights=first.weights, amounts=params)
    with pytest.raises(ValueError, match='overlaps'):
        C.apply_records_np(np.full((*SHAPE, 3), .4, np.float32), (first, conflicting), byte_budget=BUDGET)
    assert not protocol['apply']


@pytest.mark.parametrize('failure', ['error', 'cancel'])
def test_later_target_failure_publishes_no_partial_pixels(protocol, monkeypatch, failure):
    records, _ = prepare(sample_bank(targets=2))
    original = N.apply; calls = 0
    def fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            if failure == 'cancel': raise InterruptedError('cancelled')
            raise RuntimeError('later target failed')
        return original(*args, **kwargs)
    monkeypatch.setattr(N, 'apply', fail)
    current = np.full((*SHAPE, 3), .4, dtype=np.float32); before = current.copy()
    with pytest.raises((RuntimeError, InterruptedError)):
        C.apply_records_np(current, records, byte_budget=BUDGET)
    assert calls == 2 and np.array_equal(current.view(np.uint32), before.view(np.uint32))


@pytest.mark.parametrize('alter', ['source', 'grid', 'window', 'coverage', 'delta', 'recovery'])
def test_composition_refuses_mismatched_ownership_and_algorithm(protocol, alter):
    records, _ = prepare(sample_bank()); record = records[0]; recovery = None
    if alter == 'source': record = replace(record, amounts=replace(record.amounts, source_sha256='f'*64))
    if alter == 'grid': record = replace(record, amounts=replace(record.amounts, application_shape=(24, 32)))
    if alter == 'window': record = replace(record, window=(0, 0, *record.window[2:]))
    if alter == 'coverage': record = replace(record, weights=record.weights.copy())
    if alter == 'delta': record = replace(record, delta=np.zeros((*record.window[2:], 3), np.float32))
    if alter == 'recovery': recovery = {('target1', R.STAGE): {}}
    with pytest.raises(ValueError):
        C.apply_records_np(np.full((*SHAPE, 3), .4, np.float32), (record,), recovery, byte_budget=BUDGET)
    assert not protocol['apply']


def test_cancelled_preparation_has_no_result_or_fit(protocol):
    data = sample_bank()
    with pytest.raises(InterruptedError):
        R.prepare_bank(data[0], SHA, data[3], data[2], assets=data[1],
            application_shape=SHAPE, byte_budget=BUDGET, cancelled=lambda: True)
    assert not protocol['fit']


def test_native_apply_strips_reuse_one_fit_and_late_strip_is_private(protocol, monkeypatch):
    records, _ = prepare(sample_bank()); original = N.apply
    monkeypatch.setattr(N, 'MAX_APPLY_PIXELS', 64)
    seen = []
    def apply(current, coverage, fit, amount, **kwargs):
        assert current.shape[0]*current.shape[1] <= 64
        seen.append(fit)
        if len(seen) == 2:
            raise RuntimeError('second strip failed')
        return original(current, coverage, fit, amount, **kwargs)
    monkeypatch.setattr(N, 'apply', apply)
    current = np.full((*SHAPE, 3), .4, np.float32); before = current.copy()
    with pytest.raises(RuntimeError, match='second strip'):
        C.apply_records_np(current, records, byte_budget=BUDGET)
    assert len(seen) == 2 and all(fit is records[0].amounts.measured_fit for fit in seen)
    assert len(protocol['fit']) == 1 and np.array_equal(current.view(np.uint32), before.view(np.uint32))


def test_later_fit_refusal_never_mutates_graph_or_support(protocol, monkeypatch):
    from copy import deepcopy
    data = sample_bank(targets=2); state_before = deepcopy(data[0]); bank_before = deepcopy(data[1])
    fit = N.fit; count = 0
    def fail(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise ValueError('insufficient independent target evidence')
        return fit(*args, **kwargs)
    monkeypatch.setattr(N, 'fit', fail)
    with pytest.raises(ValueError, match='independent target evidence'):
        prepare(data)
    assert count == 2 and data[0] == state_before and data[1] == bank_before


def test_current_endpoint_bits_remain_exact_inside_reviewed_coverage(protocol):
    records, _ = prepare(sample_bank()); y, x, _, _ = records[0].window
    current = np.full((*SHAPE, 3), .4, np.float32)
    current[y, x] = (-0., 0., 0.); current[y, x+1] = 1.
    output, _ = C.apply_records_np(current, records, byte_budget=BUDGET)
    assert np.array_equal(output[y, x:x+2].view(np.uint32), current[y, x:x+2].view(np.uint32))


def test_corrupt_native_protected_output_is_refused(protocol, monkeypatch):
    records, _ = prepare(sample_bank()); y, x, _, _ = records[0].window
    current = np.full((*SHAPE, 3), .4, np.float32); current[y, x] = (-0., 0., 0.)
    def corrupt(current, *args, **kwargs):
        output = current.copy(); output[0, 0] = .01
        return output
    monkeypatch.setattr(N, 'apply', corrupt)
    with pytest.raises(RuntimeError, match='protected or exact neutral'):
        C.apply_records_np(current, records, byte_budget=BUDGET)
    assert np.array_equal(current[y, x].view(np.uint32), np.array([-0., 0., 0.], np.float32).view(np.uint32))
