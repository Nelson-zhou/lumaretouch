# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN body-reference protocol fixtures, not photo acceptance.

No collection, product import, native execution, inference or visual acceptance
was performed in this lane. Geometry/fit/apply doubles only expose wiring and
transaction ownership. Real numerical acceptance remains the existing Rust
solver's separate suite, plus future real-photo body/reference review.
"""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib

import numpy as np
import pytest

from lumaretouch_engine import people_state as P, people_associations as LINKS, face_scope as FACE
from lumaretouch_engine import body_pose_state as B, body_pose_evidence as E
from lumaretouch_engine import skin_reference_match_state as FACE_STATE
from lumaretouch_engine import skin_reference_match_runtime as F
from lumaretouch_engine import skin_reference_body_state as S, skin_reference_body_support as A
from lumaretouch_engine import skin_reference_body_runtime as R, skin_reference_body_composition as C
from lumaretouch_engine import skin_reference_match_native as N
from lumaretouch_engine.people_effects import LocalEffect
from lumaretouch_engine.portrait_fit_source import FullSource

BUDGET = 4 * 1024**3
SHA = 'a'*64
SHAPE = (96, 128)
BODY_WINDOWS = {'target1': (42, 8, 16, 20), 'target2': (62, 52, 16, 20)}
FACE_WINDOWS = {'target1': (8, 8, 12, 12), 'target2': (8, 52, 12, 12),
                'reference': (8, 98, 12, 12)}


def measured(reference_shape, target_shape):
    rc, tc = float(np.prod(reference_shape)), float(np.prod(target_shape))
    return N.MeasuredFit(tuple(reference_shape), tuple(target_shape),
        (N.MAX_LOG_LUMINANCE, N.MAX_LOG_CHROMA), (1., .1, .02, -.01),
        (1., rc, tc, rc, tc, rc, tc, -1.9, .12, -.21, -2., .1, -.2,
         .01, .01, .01, .01, .01, .01, .1, .02, -.01, 0., 1.)).checked()


def sample_bank(*, targets=1, reference='reference'):
    state = P.empty(); analyses = {}; persons = {}
    source = {'sha256': SHA, 'width': SHAPE[1], 'height': SHAPE[0], 'orientation': E.ORIENTATION}
    for index, key in enumerate(('target1', 'target2', 'reference')):
        cx = (.16, .46, .83)[index]
        landmarks = np.full((478, 3), (cx, .20, 0), np.float32)
        for i, landmark in enumerate(FACE.FACE_OVAL):
            angle = 2*np.pi*i/len(FACE.FACE_OVAL)
            landmarks[landmark, :2] = (cx+.08*np.cos(angle), .20+.10*np.sin(angle))
        evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b'*64,
            'semantic_model_sha256': 'c'*64, 'landmark_digest': hashlib.sha256(landmarks.tobytes()).hexdigest(),
            'status': 'verified', 'source_width': SHAPE[1], 'source_height': SHAPE[0],
            'orientation': E.ORIENTATION}
        face = P.new_face(SHA, [cx-.10, .06, cx+.10, .34], evidence)
        face['face_instance_id'] = key; state['faces'][key] = face
        state, person = LINKS.create_person(state); persons[key] = person
        state = LINKS.set_link(state, key, person, 'confirmed', user_confirmed=True)
        analyses[key] = {'face_ref': P.face_ref(face), 'evidence': evidence, 'landmarks': landmarks,
            'face_skin': np.ones(SHAPE, np.float32), 'excluded': np.zeros(SHAPE, np.float32),
            'body_skin': np.ones(SHAPE, np.float32),
            'face_skin_observation': {'contract': 'mediapipe-face-skin-edit-weight-v1',
                'source_sha256': SHA, 'semantic_model_sha256': 'c'*64,
                'producer_width': SHAPE[1], 'producer_height': SHAPE[0]},
            'body_skin_observation': {'contract': 'mediapipe-body-skin-edit-weight-v1',
                'source_sha256': SHA, 'semantic_model_sha256': 'c'*64, 'detector_model_sha256': 'b'*64,
                'producer_width': SHAPE[1], 'producer_height': SHAPE[0]}}
    body_bank = B.empty(); bodies = {}
    for key in ('target1', 'target2'):
        values = [{'index': i, 'x': .5, 'y': .5, 'z': 0., 'visibility': 0., 'presence': 0.}
                  for i in range(33)]
        record = E.create(source_frame=source, values=values, backend_version='fixture-only',
            backend_code_sha256='d'*64, model_id='synthetic-unit-fixture', model_sha256='e'*64,
            input_rgb_sha256='f'*64, input_dimensions=(SHAPE[1], SHAPE[0]))
        record['body_ref']['body_instance_id'] = 'body:'+key; bodies[key] = record
        body_bank = B.add_run(body_bank, {'source': source, 'records': [record],
            'detector_limit': 4, 'limit_reached': False, 'census_complete': False})
        body_bank = B.associate(body_bank, record['body_ref'], persons[key], state, user_confirmed=True)
    # Retain only after all association revisions are final.
    assets = {}; donor = P.face_ref(state['faces'][reference])
    for key in ('target1', 'target2')[:targets]:
        record = bodies[key]; y, x, h, w = BODY_WINDOWS[key]
        review = {'operation_id': S.OP, 'body_ref': record['body_ref'],
            'points_sha256': record['points_sha256'], 'visible': True, 'unoccluded': True,
            'ownership_confirmed': True, 'reference_unchanged': True,
            'recipe': {'version': 1, 'domain': 'source-normalized', 'objects': [{
                'id': 'body-scope-'+key, 'name': 'Synthetic independent body review', 'kind': 'brush',
                'enabled': True, 'operation': 'add', 'opacity': 1., 'feather': 0.,
                'points': [[(x+w/2)/SHAPE[1], (y+h/2)/SHAPE[0]]],
                'axes': [[w/(2*SHAPE[1]), 0.], [0., h/(2*SHAPE[0])]]}]}}
        ref = P.face_ref(state['faces'][key])
        state, assets = A.retain(state, assets, ref, donor, body_bank, analyses[key],
                                analyses[reference], review, confirmed=True)
        state = P.set_override(state, 'face', key, S.OP, '/amount', .7)
    pixels = np.linspace(.1, .8, np.prod(SHAPE)*3, dtype=np.float32).reshape(*SHAPE, 3)
    content = pixels.tobytes()
    full_source = FullSource(SHA, SHAPE[1], SHAPE[0], hashlib.sha256(content).hexdigest(),
                             16, 'original', len(content), content)
    return state, assets, analyses, full_source, body_bank


@pytest.fixture
def protocol(monkeypatch):
    calls = {'fit': [], 'geometry': [], 'apply': []}
    monkeypatch.setattr(R, 'available_estimate', lambda: BUDGET)
    monkeypatch.setattr(C, 'available_estimate', lambda: BUDGET)
    def geometry(state, assets, ref, body_bank, owner_row, donor_row, shape, *, byte_budget, cancelled):
        assert byte_budget > 0 and not cancelled()
        assert owner_row['body_skin'].shape == owner_row['excluded'].shape == donor_row['face_skin'].shape == shape
        assert owner_row['body_skin_observation']['producer_width'] == SHAPE[1]
        record, key = A.resolve(state, assets, ref, body_bank, owner_row, donor_row)
        donor = record['row']['reference_face_ref']; body_ref = record['row']['review']['body_ref']
        masks, details = [], {}
        for name, original in (('target', BODY_WINDOWS[ref['face_instance_id']]),
                               ('reference', FACE_WINDOWS[donor['face_instance_id']])):
            y, x, h, w = original
            window = (y*shape[0]//SHAPE[0], x*shape[1]//SHAPE[1],
                      max(1, h*shape[0]//SHAPE[0]), max(1, w*shape[1]//SHAPE[1]))
            y, x, h, w = window
            mask = np.zeros(shape, np.float32); mask[y:y+h, x:x+w] = 1
            mask.setflags(write=False); masks.append(mask)
            details[name] = {'face_ref': ref if name == 'target' else donor, 'source_window': list(window)}
            if name == 'target': details[name]['body_ref'] = body_ref
        calls['geometry'].append((ref['face_instance_id'], shape))
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
        result[take] += np.float32(.01)  # Protocol marker, NOT an alternative solver.
        return result
    monkeypatch.setattr(A, 'geometry', geometry)
    monkeypatch.setattr(N, 'fit', fit); monkeypatch.setattr(N, 'apply', apply)
    return calls


def prepare(data, *, application_shape=SHAPE, face_records=()):
    state, assets, analyses, source, body_bank = data
    return R.prepare_bank(state, SHA, source, analyses, assets=assets, body_bank=body_bank,
        application_shape=application_shape, byte_budget=BUDGET, face_records=face_records)


def face_record(body_record, *, target='target1', window=None, reference=None):
    body = body_record.amounts; window = FACE_WINDOWS[target] if window is None else window
    weights = np.frombuffer(np.ones(window[2:], np.float32).tobytes(), np.float32).reshape(window[2:])
    ref = {'asset_sha256': SHA, 'face_instance_id': target, 'analysis_revision': 0}
    params = F.Parameters(.7, measured(FACE_WINDOWS['reference'][2:], window[2:]),
        SHA, body.source_pixels_sha256, SHAPE, SHAPE, F._identity(ref),
        body.reference_identity if reference is None else reference, '9'*64,
        window, FACE_WINDOWS['reference'], window, F.coverage_digest(weights)).checked()
    return LocalEffect(ref, F.STAGE, window, weights=weights, amounts=params)


def test_neutral_and_old_face_v1_do_not_need_body_support_or_native(monkeypatch):
    monkeypatch.setattr(N, 'fit', lambda *a, **k: pytest.fail('Neutral cannot fit'))
    assert R.prepare_bank(P.empty(), SHA, None, None, assets=None, body_bank=None,
        application_shape=None, byte_budget=0) == ((), {})
    data = list(sample_bank()); data[0] = P.set_override(data[0], 'face', 'target1', S.OP, '/amount', 0.)
    data[0] = P.set_override(data[0], 'face', 'target1', FACE_STATE.OP, '/amount', .9)
    assert R.requests(data[0], SHA) == ()
    value = object()
    assert C.apply_records_np(value, ())[0] is value


def test_new_operation_inheritance_resolves_complete_set_and_conflicts():
    data = sample_bank(); state = P.set_override(data[0], 'face', 'target1', S.OP, '/amount', 0.)
    state = P.set_override(state, 'all_people', SHA, S.OP, '/amount', .3)
    state['faces']['target2']['enabled'] = False
    assert [ref['face_instance_id'] for ref, _ in R.requests(state, SHA)] == ['reference']
    state['groups'] = {'g1': {'label': 'A', 'priority': 1, 'face_ids': ['reference']},
                       'g2': {'label': 'B', 'priority': 1, 'face_ids': ['reference']}}
    state = P.set_override(state, 'group', 'g1', S.OP, '/amount', .2)
    state = P.set_override(state, 'group', 'g2', S.OP, '/amount', .8)
    with pytest.raises(ValueError, match='conflicting groups'): R.requests(state, SHA)


def test_body_only_selected_foreign_face_and_own_face_both_work(protocol):
    for donor in ('reference', 'target1'):
        data = sample_bank(reference=donor)
        records, facts = prepare(data); record = records[0]
        assert F.requests(data[0], SHA) == ()  # No face operation activation required.
        assert record.amounts.reference_identity[1] == donor
        assert record.amounts.owner_identity[1] == 'target1'
        assert record.amounts.body_identity[1] == 'body:target1'
        assert facts['target1']['reference_face_unchanged_by_this_operation'] is True


def test_foreign_reference_body_does_not_require_owner_face_skin(protocol):
    data = sample_bank()
    del data[2]['target1']['face_skin']; del data[2]['target1']['face_skin_observation']
    records, _ = prepare(data)
    assert len(records) == len(protocol['fit']) == 1


def test_each_body_fits_full_precision_independent_source_rois_once(protocol):
    data = sample_bank(targets=2); records, facts = prepare(data, application_shape=(48, 64))
    assert len(records) == len(protocol['fit']) == 2
    assert [grid for _, grid in protocol['geometry']] == [SHAPE, (48, 64), SHAPE, (48, 64)]
    ry, rx, rh, rw = FACE_WINDOWS['reference']
    for record, call in zip(records, protocol['fit']):
        y, x, h, w = BODY_WINDOWS[record.face_ref['face_instance_id']]
        assert np.array_equal(call[0], data[3].pixels[ry:ry+rh, rx:rx+rw])
        assert np.array_equal(call[2], data[3].pixels[y:y+h, x:x+w])
        assert call[0].shape != call[2].shape
        assert record.amounts.source_shape == SHAPE and record.amounts.application_shape == (48, 64)
        assert record.delta is None and record.chroma_shift is None and record.log_gain is None
        assert facts[record.face_ref['face_instance_id']]['fit_count_per_target'] == 1
        with pytest.raises(ValueError): record.weights.setflags(write=True)
        with pytest.raises(FrozenInstanceError): record.amounts.amount = .2


def test_current_edits_and_crop_parity_with_no_per_tile_fit(protocol):
    records, _ = prepare(sample_bank()); current = np.full((*SHAPE, 3), .4, np.float32)
    current[0, 0, 0] = -0.; before = current.copy()
    whole, facts = C.apply_records_np(current, records, byte_budget=BUDGET)
    assert facts['changed_pixels'] > 0 and np.all(protocol['apply'][0][0] == np.float32(.4))
    assert np.array_equal(current.view(np.uint32), before.view(np.uint32))
    assert np.array_equal(whole[:40].view(np.uint32), before[:40].view(np.uint32))
    tiled = current.copy()
    for y in range(0, SHAPE[0], 8):
        tiled[y:y+8], _ = C.apply_records_np(current[y:y+8], records, source_shape=SHAPE,
            origin=(y, 0), byte_budget=BUDGET)
    assert np.array_equal(tiled.view(np.uint32), whole.view(np.uint32))
    assert len(protocol['fit']) == 1


def test_joint_face_body_has_no_duplicate_contribution(protocol):
    body, _ = prepare(sample_bank()); face = face_record(body[0]); joint = (face, *body)
    assert R.validate_joint_records(joint, application_shape=SHAPE) == joint
    # Explicit same-owner overlap is refused rather than sequentially painted.
    overlap = face_record(body[0], window=body[0].window)
    with pytest.raises(ValueError, match='重叠'):
        C.apply_records_np(np.full((*SHAPE, 3), .4, np.float32), (overlap, *body), byte_budget=BUDGET)
    assert not protocol['apply']


def test_joint_conflict_outside_crop_still_refused_before_native(protocol):
    body, _ = prepare(sample_bank()); overlap = face_record(body[0], window=body[0].window)
    with pytest.raises(ValueError, match='重叠'):
        C.apply_records_np(np.full((8, SHAPE[1], 3), .4, np.float32), (overlap, *body),
                           source_shape=SHAPE, byte_budget=BUDGET)
    assert not protocol['apply']


def test_joint_reference_mismatch_and_selected_face_target_refused(protocol):
    body, _ = prepare(sample_bank())
    wrong = face_record(body[0], reference=(SHA, 'target2', 0))
    with pytest.raises(ValueError, match='selected reference'):
        R.validate_joint_records((wrong, *body), application_shape=SHAPE)
    own, _ = prepare(sample_bank(reference='target1'))
    # A different face target using target1 as donor is valid, but target1 itself
    # may not be painted by ANY face-reference record in the combined bank.
    valid_face = face_record(own[0], target='target2', reference=(SHA, 'target1', 0))
    R.validate_joint_records((valid_face, *own), application_shape=SHAPE)


def test_duplicate_body_identity_refused_even_with_disjoint_windows(protocol):
    records, _ = prepare(sample_bank(targets=2)); first, second = records
    second = replace(second, amounts=replace(second.amounts, body_identity=first.amounts.body_identity))
    with pytest.raises(ValueError, match='duplicate BodyRef'):
        R.validate_joint_records((first, second), application_shape=SHAPE)


@pytest.mark.parametrize('alter', ['source', 'grid', 'window', 'coverage', 'delta', 'recovery', 'body'])
def test_composition_refuses_mismatched_identity_coverage_and_algorithm(protocol, alter):
    records, _ = prepare(sample_bank()); record = records[0]; recovery = None
    if alter == 'source': record = replace(record, amounts=replace(record.amounts, source_sha256='f'*64))
    elif alter == 'grid': record = replace(record, amounts=replace(record.amounts, application_shape=(48, 64)))
    elif alter == 'window': record = replace(record, window=(0, 0, *record.window[2:]))
    elif alter == 'coverage': record = replace(record, weights=record.weights.copy())
    elif alter == 'delta': record = replace(record, delta=np.zeros((*record.window[2:], 3), np.float32))
    elif alter == 'recovery': recovery = {('target1', R.STAGE): {}}
    else: record = replace(record, amounts=replace(record.amounts, body_identity=('f'*64, 'body:target1', 0)))
    with pytest.raises(ValueError):
        C.apply_records_np(np.full((*SHAPE, 3), .4, np.float32), (record,), recovery, byte_budget=BUDGET)
    assert not protocol['apply']


@pytest.mark.parametrize('alter', ['array', 'hash', 'precision', 'source'])
def test_proxy_or_unverified_full_source_cannot_fit(protocol, alter):
    data = list(sample_bank())
    if alter == 'array': data[3] = data[3].pixels
    elif alter == 'hash': data[3] = replace(data[3], input_sha256='f'*64)
    elif alter == 'precision': data[3] = replace(data[3], kind='creative', source_bits=8)
    else: data[3] = replace(data[3], source_sha256='f'*64)
    with pytest.raises(ValueError): prepare(data)
    assert not protocol['fit']


def test_missing_body_consent_or_body_skin_cannot_reuse_face_review(protocol):
    data = list(sample_bank()); data[0] = A.detach(data[0], P.face_ref(data[0]['faces']['target1']))
    with pytest.raises(ValueError): prepare(data)
    data = list(sample_bank()); del data[2]['target1']['body_skin']
    with pytest.raises(ValueError): prepare(data)
    assert not protocol['fit']


def test_budget_and_initial_cancellation_precede_projection_or_fit(protocol, monkeypatch):
    data = sample_bank()
    monkeypatch.setattr(R, '_project', lambda *a, **k: pytest.fail('Must admit before projecting'))
    with pytest.raises(MemoryError):
        R.prepare_bank(data[0], SHA, data[3], data[2], assets=data[1], body_bank=data[4],
                       application_shape=SHAPE, byte_budget=1)
    with pytest.raises(InterruptedError):
        R.prepare_bank(data[0], SHA, data[3], data[2], assets=data[1], body_bank=data[4],
                       application_shape=SHAPE, byte_budget=BUDGET, cancelled=lambda: True)
    assert not protocol['fit']


@pytest.mark.parametrize('failure', ['error', 'cancel'])
def test_later_body_failure_has_no_partial_output(protocol, monkeypatch, failure):
    records, _ = prepare(sample_bank(targets=2)); apply = N.apply; count = 0
    def fail(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            if failure == 'cancel': raise InterruptedError('cancelled')
            raise RuntimeError('later body failed')
        return apply(*args, **kwargs)
    monkeypatch.setattr(N, 'apply', fail)
    current = np.full((*SHAPE, 3), .4, np.float32); before = current.copy()
    with pytest.raises((RuntimeError, InterruptedError)):
        C.apply_records_np(current, records, byte_budget=BUDGET)
    assert count == 2 and np.array_equal(current.view(np.uint32), before.view(np.uint32))


def test_later_native_strip_failure_reuses_one_fit_and_stays_private(protocol, monkeypatch):
    records, _ = prepare(sample_bank()); apply = N.apply; seen = []
    monkeypatch.setattr(N, 'MAX_APPLY_PIXELS', 64)
    def fail(current, coverage, fit, amount, **kwargs):
        assert current.shape[0]*current.shape[1] <= 64
        seen.append(fit)
        if len(seen) == 2: raise RuntimeError('later native strip failed')
        return apply(current, coverage, fit, amount, **kwargs)
    monkeypatch.setattr(N, 'apply', fail)
    current = np.full((*SHAPE, 3), .4, np.float32); before = current.copy()
    with pytest.raises(RuntimeError, match='later native strip'):
        C.apply_records_np(current, records, byte_budget=BUDGET)
    assert len(seen) == 2 and all(fit is records[0].amounts.measured_fit for fit in seen)
    assert len(protocol['fit']) == 1 and np.array_equal(current.view(np.uint32), before.view(np.uint32))


def test_later_fit_failure_leaves_graph_and_bank_untouched(protocol, monkeypatch):
    data = sample_bank(targets=2); original = deepcopy((data[0], data[1], data[4])); fit = N.fit; count = 0
    def fail(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2: raise ValueError('insufficient independent body evidence')
        return fit(*args, **kwargs)
    monkeypatch.setattr(N, 'fit', fail)
    with pytest.raises(ValueError, match='independent body evidence'): prepare(data)
    assert count == 2 and (data[0], data[1], data[4]) == original


def test_neutral_amount_endpoints_and_no_coverage_remain_exact(protocol):
    records, _ = prepare(sample_bank()); record = records[0]
    current = np.full((*SHAPE, 3), .4, np.float32); y, x, _, _ = record.window
    current[y, x] = (-0., 0., 0.); current[y, x+1] = 1.
    neutral = replace(record, amounts=replace(record.amounts, amount=0.))
    assert C.apply_records_np(current, (neutral,), byte_budget=BUDGET)[0] is current
    assert not protocol['apply']
    out, _ = C.apply_records_np(current, records, byte_budget=BUDGET)
    assert np.array_equal(out[y, x:x+2].view(np.uint32), current[y, x:x+2].view(np.uint32))


def test_corrupt_native_protected_output_is_refused(protocol, monkeypatch):
    records, _ = prepare(sample_bank()); y, x, _, _ = records[0].window
    current = np.full((*SHAPE, 3), .4, np.float32); current[y, x] = (-0., 0., 0.)
    def corrupt(current, *args, **kwargs):
        result = current.copy(); result[0, 0] = .01; return result
    monkeypatch.setattr(N, 'apply', corrupt)
    with pytest.raises(RuntimeError, match='protected or exact neutral'):
        C.apply_records_np(current, records, byte_budget=BUDGET)
    assert np.array_equal(current[y, x].view(np.uint32), np.array([-0., 0., 0.], np.float32).view(np.uint32))
