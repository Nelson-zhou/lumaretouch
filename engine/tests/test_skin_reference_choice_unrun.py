# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: measured same-photo proposal, never review authority.

No collection, product import, test execution, build or inference was performed
while authoring. Synthetic anatomical rings are not model-produced evidence.
The protocol double below tests source/geometry routing, NOT photometry. Tests
using real_core require a separately authorized installed original Rust core;
a skip is not numerical or photographic acceptance.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math

import numpy as np
import pytest

from lumaretouch_engine import face_scope as FACE, people_state as P
from lumaretouch_engine import skin_reference_choice as C
from lumaretouch_engine import skin_reference_match_native as N
from lumaretouch_engine import skin_reference_match_support as A
from lumaretouch_engine.portrait_fit_source import FullSource
from lumaretouch_engine.ops.enhance import EYE_RING_LEFT, EYE_RING_RIGHT

SHA = 'a'*64
SHAPE = (256, 256)
BUDGET = 4*1024**3


def add_face(state, name, center, *, shape=SHAPE, enabled=True):
    cx, cy = center; rx, ry = .17, .31
    landmarks = np.full((478, 3), (cx, cy, 0.), dtype=np.float32)
    def ellipse(indices, x, y, width, height):
        angle = np.linspace(-np.pi/2, 3*np.pi/2, len(indices), endpoint=False)
        landmarks[list(indices), :2] = np.column_stack((x+width*np.cos(angle), y+height*np.sin(angle)))
    ellipse(FACE.FACE_OVAL, cx, cy, rx, ry)
    ellipse(EYE_RING_LEFT, cx-.4*rx, cy-.22*ry, .16*rx, .08*ry)
    ellipse(EYE_RING_RIGHT, cx+.4*rx, cy-.22*ry, .16*rx, .08*ry)
    ellipse(FACE.BROW_LEFT, cx+.4*rx, cy-.43*ry, .20*rx, .06*ry)
    ellipse(FACE.BROW_RIGHT, cx-.4*rx, cy-.43*ry, .20*rx, .06*ry)
    ellipse(FACE.LIPS, cx, cy+.5*ry, .25*rx, .09*ry)
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b'*64,
        'semantic_model_sha256': 'c'*64, 'landmark_digest': hashlib.sha256(landmarks.tobytes()).hexdigest(),
        'status': 'verified', 'source_width': SHAPE[1], 'source_height': SHAPE[0],
        'orientation': 'exif_normalized_once'}
    face = P.new_face(SHA, [cx-rx, cy-ry, cx+rx, cy+ry], evidence)
    face['face_instance_id'] = name; face['enabled'] = enabled; state['faces'][name] = face
    row = {'face_ref': P.face_ref(face), 'evidence': deepcopy(evidence), 'landmarks': landmarks,
        'face_skin': np.full(shape, .85, np.float32), 'excluded': np.zeros(shape, np.float32),
        'face_skin_observation': {'contract': 'mediapipe-face-skin-edit-weight-v1',
            'source_sha256': SHA, 'semantic_model_sha256': 'c'*64,
            'producer_width': shape[1], 'producer_height': shape[0]}}
    return row


def source_from(pixels):
    # TEST FIXTURE ONLY: production callers must use authenticated capture.
    content = np.ascontiguousarray(pixels, dtype=np.float32).tobytes()
    return FullSource(SHA, SHAPE[1], SHAPE[0], hashlib.sha256(content).hexdigest(),
                      16, 'original', len(content), content)


def sample(*, left=.40, right=.65, analysis_shape=SHAPE):
    state = P.empty()
    analyses = {key: add_face(state, key, (x, .50), shape=analysis_shape)
                for key, x in (('left', .25), ('right', .75))}
    pixels = np.full((*SHAPE, 3), left, np.float32); pixels[:, 128:] = right
    return state, analyses, source_from(pixels)


def propose(data, **kwargs):
    state, analyses, source = data
    return C.propose(state, SHA, source, analyses, byte_budget=BUDGET, **kwargs)


def fit_result(shape, marker, *, count=512., weight=256., effective=300.):
    centre = (math.log(marker), 0., 0.)
    return N.MeasuredFit(shape, shape, (0., 0.), (1., 0., 0., 0.),
        (1., count, count, weight, weight, effective, effective,
         *centre, *centre, .01, .01, .01, .01, .01, .01, 0., 0., 0., 0., 1.)).checked()


@pytest.fixture
def protocol(monkeypatch):
    calls = []
    monkeypatch.setattr(C, 'available_estimate', lambda: BUDGET)
    def fit(reference, reference_weight, target, target_weight, *, limits, byte_budget, cancelled):
        assert limits == (0., 0.) and byte_budget > 0 and not cancelled()
        assert np.shares_memory(reference, target) and np.shares_memory(reference_weight, target_weight)
        assert not reference.flags.writeable and not reference_weight.flags.writeable
        assert reference.shape[:2] == reference_weight.shape
        # A routing marker, intentionally NOT an implementation of luminance.
        marker = float(reference[reference_weight > 0][0, 0])
        calls.append((reference.copy(), reference_weight.copy(), limits))
        return fit_result(reference_weight.shape, marker)
    monkeypatch.setattr(N, 'fit', fit)
    monkeypatch.setattr(N, 'apply', lambda *a, **k: pytest.fail('A proposal cannot render pixels'))
    return calls


def rows(result):
    return {row['face_ref']['face_instance_id']: row for row in result['candidates']}


def test_source_brightness_not_semantic_confidence_or_labels(protocol):
    data = sample(); state, analyses, source = data
    analyses['left']['face_skin'].fill(.99)
    analyses['right']['face_skin'].fill(.30)
    state['faces']['left']['labels'] = {'label': 'prefer me'}
    result = propose(data)
    assert result['reference_face_ref'] == P.face_ref(state['faces']['right'])
    assert result['automatic_status'] == 'proposed' and len(protocol) == 2
    assert rows(result)['left']['measurement']['effective_samples'] == rows(result)['right']['measurement']['effective_samples']
    assert result['source_pixels_sha256'] == source.input_sha256
    assert result['control_id'] == 'control:PC-32465:19'
    assert result['review_required'] and result['reference_face_exclusion_required']
    assert not result['body_extension_enabled'] and not result['fit_retained']


def test_proposal_is_pure_json_and_grants_no_relation_review_or_recipe(protocol):
    data = sample(); state, analyses, source = data
    before = deepcopy(state); raw = source._content
    arrays = {key: {name: row[name].copy() for name in ('face_skin', 'excluded', 'landmarks')}
              for key, row in analyses.items()}
    result = propose(data)
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    assert state == before and source._content is raw
    assert state['overrides'] == [] and all(not face['local_assets'] for face in state['faces'].values())
    for key, original in arrays.items():
        for name, value in original.items():
            np.testing.assert_array_equal(analyses[key][name], value)
    digest = result.pop('proposal_sha256'); assert A.content_digest(result) == digest
    with pytest.raises(ValueError, match='explicit'):
        A.retain(state, {}, P.face_ref(state['faces']['left']), P.face_ref(state['faces']['right']),
                 analyses['left'], analyses['right'])


@pytest.mark.parametrize('right', [.40, .4001, .407])
def test_exact_and_near_ties_never_choose_detector_order_or_confidence(protocol, right):
    data = sample(right=right)
    result = propose(data)
    assert result['reference_face_ref'] is None
    assert 'brightest-measurements-too-close' in result['automatic_blockers']
    assert len(result['ambiguous_face_refs']) == 2
    reverse = (deepcopy(data[0]), dict(reversed(list(data[1].items()))), data[2])
    reverse[0]['faces'] = dict(reversed(list(reverse[0]['faces'].items())))
    assert propose(reverse) == result


def test_manual_override_keeps_automatic_evidence_and_review_required(protocol):
    data = sample(); manual = P.face_ref(data[0]['faces']['left'])
    result = propose(data, manual_reference=manual)
    assert result['reference_face_ref'] == manual
    assert result['automatic_reference_face_ref'] == P.face_ref(data[0]['faces']['right'])
    assert result['selection_mode'] == 'manual-override-proposal' and result['review_required']
    data = sample(right=.40)
    result = propose(data, manual_reference=P.face_ref(data[0]['faces']['right']))
    assert result['automatic_status'] == 'blocked' and result['reference_face_ref'] is not None


@pytest.mark.parametrize('fault', ['missing', 'merged-only', 'source-owner', 'landmark-digest',
    'landmark-shape', 'landmark-list', 'unresolved', 'excluded', 'canonical-dimensions', 'model'])
def test_missing_or_ambiguous_candidate_blocks_auto_not_silent_subset(protocol, fault):
    data = sample(); state, analyses, _ = data; bad = analyses['right']
    if fault == 'missing': analyses.pop('right')
    elif fault == 'merged-only': bad['skin'] = bad.pop('face_skin'); bad.pop('face_skin_observation')
    elif fault == 'source-owner': bad['face_ref']['asset_sha256'] = 'd'*64
    elif fault == 'landmark-digest': bad['landmarks'][0, 0] += .01
    elif fault == 'landmark-shape': bad['landmarks'] = bad['landmarks'][:477]
    elif fault == 'landmark-list': bad['landmarks'] = bad['landmarks'].tolist()
    elif fault == 'unresolved':
        state['faces']['right']['evidence']['status'] = 'unresolved'; bad['evidence']['status'] = 'unresolved'
    elif fault == 'excluded': bad['excluded'] = None
    elif fault == 'canonical-dimensions':
        state['faces']['right']['evidence']['source_width'] = 512; bad['evidence']['source_width'] = 512
    else: bad['face_skin_observation']['semantic_model_sha256'] = 'd'*64
    result = propose(data)
    assert result['reference_face_ref'] is None and rows(result)['right']['status'] == 'unavailable'
    assert 'enabled-face-measurement-unavailable' in result['automatic_blockers']
    assert len(protocol) == 1
    manual = P.face_ref(state['faces']['left'])
    assert propose(data, manual_reference=manual)['reference_face_ref'] == manual
    with pytest.raises(ValueError, match='no reliable'):
        propose(data, manual_reference=P.face_ref(state['faces']['right']))


def test_photometric_refusal_is_disclosed_and_does_not_choose_other_face(protocol, monkeypatch):
    original = N.fit
    def fit(reference, *args, **kwargs):
        if float(reference[0, 0, 0]) > .5:
            raise ValueError('Skin reference match Rust refused: insufficient reliable selected-reference evidence')
        return original(reference, *args, **kwargs)
    monkeypatch.setattr(N, 'fit', fit)
    result = propose(sample())
    assert result['reference_face_ref'] is None and rows(result)['right']['status'] == 'unavailable'
    assert rows(result)['right']['reason'] == 'source-measurement-refused'


@pytest.mark.parametrize('failure', [RuntimeError('native missing'), MemoryError('native resource refusal'),
                                      InterruptedError('cancelled')])
def test_native_failure_resource_refusal_and_cancellation_never_return_partial_proposal(protocol, monkeypatch, failure):
    def fail(*args, **kwargs): raise failure
    monkeypatch.setattr(N, 'fit', fail)
    with pytest.raises(type(failure), match=str(failure)):
        propose(sample())


@pytest.mark.parametrize('fault', ['transform', 'centres', 'shape', 'bounds'])
def test_self_fit_must_be_exact_symmetric_zero_shift(protocol, monkeypatch, fault):
    original = N.fit
    def bad(*args, **kwargs):
        result = original(*args, **kwargs)
        if fault == 'transform': return replace(result, transform=(1., .1, 0., 0.))
        if fault == 'shape': return replace(result, target_shape=(1024, 1024))
        diagnostics = list(result.diagnostics)
        if fault == 'centres': diagnostics[10] += .01; diagnostics[19] -= .01
        else: diagnostics[22] = 4.
        return replace(result, diagnostics=tuple(diagnostics))
    monkeypatch.setattr(N, 'fit', bad)
    result = propose(sample())
    assert result['reference_face_ref'] is None
    assert all(row['status'] == 'unavailable' for row in result['candidates'])


def test_detector_limit_and_incomplete_census_are_not_hidden(protocol):
    data = sample(); data[0]['analysis_runs'][SHA] = {'detector_limit': 2, 'limit_reached': True,
        'census_complete': False, 'notice': 'May omit faces'}
    result = propose(data)
    assert result['reference_face_ref'] is None and not result['census_complete']
    assert 'detector-limit-reached' in result['automatic_blockers']
    manual = P.face_ref(data[0]['faces']['right'])
    assert propose(data, manual_reference=manual)['reference_face_ref'] == manual
    data[0]['analysis_runs'][SHA]['limit_reached'] = False
    assert propose(data)['reference_face_ref'] == manual
    assert not propose(data)['census_complete']


def test_disabled_face_disclosed_not_ranked_still_protects_geometry(protocol):
    data = sample(); state, analyses, _ = data
    analyses['disabled'] = add_face(state, 'disabled', (.50, .50), enabled=False)
    result = propose(data)
    assert rows(result)['disabled']['status'] == 'disabled'
    assert len(result['ranked_face_refs']) == 2 and len(protocol) == 2
    assert rows(result)['left']['protected_face_boxes'] == 2
    assert rows(result)['left']['protected_actual_face_ovals'] == 2
    with pytest.raises(ValueError, match='enabled'):
        propose(data, manual_reference=P.face_ref(state['faces']['disabled']))


def test_actual_support_matches_existing_reviewed_geometry_without_granting_review(protocol):
    state, analyses, source = sample()
    left, right = P.face_ref(state['faces']['left']), P.face_ref(state['faces']['right'])
    reviewed, assets = A.retain(state, {}, left, right, analyses['left'], analyses['right'], confirmed=True)
    expected_left, expected_right, _ = A.geometry(reviewed, assets, left, analyses['left'], analyses['right'],
                                                SHAPE, byte_budget=BUDGET)
    anatomy = {key: row['landmarks'] for key, row in analyses.items()}
    for key, expected in (('left', expected_left), ('right', expected_right)):
        actual, window, _, _ = C._coverage(state, state['faces'][key], analyses[key], anatomy, SHAPE, lambda: False)
        np.testing.assert_array_equal(actual, expected)
        assert window == A._window(expected)
    assert not state['faces']['left']['local_assets']


def test_known_occluders_remove_support_and_whole_frame_skin_is_not_ownership(protocol):
    state, analyses, _ = sample(); anatomy = {key: row['landmarks'] for key, row in analyses.items()}
    analyses['left']['excluded'][150:170, 50:75] = 1
    support, _, _, _ = C._coverage(state, state['faces']['left'], analyses['left'], anatomy, SHAPE, lambda: False)
    assert not np.any(support[150:170, 50:75])
    assert not np.any(support[:, 128:]) and not np.any(support[:30])
    for indices in (EYE_RING_LEFT, EYE_RING_RIGHT, FACE.LIPS, FACE.BROW_LEFT, FACE.BROW_RIGHT):
        centre = analyses['left']['landmarks'][list(indices), :2].mean(axis=0)*[SHAPE[1], SHAPE[0]]
        x, y = map(int, centre)
        assert support[y, x] == 0


def test_proxy_semantics_are_projected_but_source_rgb_is_not(protocol):
    result = propose(sample(analysis_shape=(128, 128)))
    assert result['reference_face_ref']['face_instance_id'] == 'right'
    assert rows(result)['left']['face_skin_observation']['producer_width'] == 128
    assert result['source'] == {'sha256': SHA, 'width': 256, 'height': 256}
    assert protocol[0][0].shape[0] > 128  # Actual native-resolution face ROI.


@pytest.mark.parametrize('fault', ['proxy', 'digest', 'hdr', 'nonfinite', 'precision'])
def test_authentic_full_source_boundary_is_not_caller_rgb_or_boolean(protocol, fault):
    data = list(sample()); source = data[2]
    if fault == 'proxy': data[2] = source.pixels
    elif fault == 'digest': data[2] = replace(source, input_sha256='d'*64)
    elif fault == 'precision': data[2] = replace(source, source_bits=8, kind='creative')
    else:
        pixels = source.pixels.copy(); pixels[0, 0, 0] = 1.01 if fault == 'hdr' else np.nan
        data[2] = source_from(pixels)
    with pytest.raises(ValueError): propose(data)
    assert not protocol


def test_memory_and_cancellation_refuse_before_native_or_geometry(protocol, monkeypatch):
    state, analyses, source = sample()
    with pytest.raises(MemoryError):
        C.propose(state, SHA, source, analyses, byte_budget=0)
    with pytest.raises(InterruptedError):
        C.propose(state, SHA, source, analyses, byte_budget=BUDGET, cancelled=lambda: True)
    assert not protocol


def test_callback_failure_is_not_relabelled_as_unavailable_candidate(protocol):
    calls = 0
    def cancellation():
        nonlocal calls
        calls += 1
        if calls == 4:
            raise ValueError('observer failed')
        return False
    with pytest.raises(RuntimeError, match='callback failed'):
        propose(sample(), cancelled=cancellation)


def test_extra_foreign_analysis_and_face_limit_refuse_without_truncation(protocol, monkeypatch):
    data = sample(); data[1]['foreign'] = deepcopy(data[1]['left'])
    with pytest.raises(ValueError, match='foreign/stale'):
        propose(data)
    monkeypatch.setattr(C, 'MAX_FACES', 1)
    with pytest.raises(ValueError, match='no silent truncation'):
        propose(sample())
    assert not protocol


def test_strided_analysis_backing_is_charged_and_no_candidate_list_can_omit_missing_face(protocol):
    state, analyses, source = sample()
    backing = np.ones((1024, 1024), np.float32)
    analyses['left']['unused'] = backing[:1, :1]
    assert C._analysis_bytes(analyses, state['faces']) >= backing.nbytes
    analyses.pop('right')
    result = C.propose(state, SHA, source, analyses, byte_budget=BUDGET)
    assert len(result['candidates']) == 2 and result['reference_face_ref'] is None


@pytest.fixture
def real_core(monkeypatch):
    try: library = N.native()
    except RuntimeError as error: pytest.skip('Original native core unavailable: ' + str(error))
    monkeypatch.setattr(C, 'available_estimate', lambda: BUDGET)
    monkeypatch.setattr(N, '_available_estimate', lambda: BUDGET)
    return library


def test_real_core_constant_source_luminance_not_confidence(real_core):
    data = sample(); data[1]['left']['face_skin'].fill(.99); data[1]['right']['face_skin'].fill(.30)
    result = propose(data)
    assert result['reference_face_ref']['face_instance_id'] == 'right'
    for key, encoded in (('left', np.float32(.40)), ('right', np.float32(.65))):
        expected = ((float(encoded)+.055)/1.055)**2.4
        assert rows(result)[key]['measurement']['linear_luminance'] == pytest.approx(expected, abs=2e-7)


@pytest.mark.parametrize('level', [0., 1.])
def test_real_core_unreliable_dark_or_clipped_face_blocks_automatic_choice(real_core, level):
    result = propose(sample(right=level))
    assert result['reference_face_ref'] is None and rows(result)['right']['status'] == 'unavailable'


def test_real_core_small_specular_patch_does_not_replace_robust_source_centre(real_core):
    data = list(sample(left=.40, right=.55)); baseline = propose(data)
    pixels = data[2].pixels.copy(); pixels[145:151, 55:61] = .98
    data[2] = source_from(pixels); result = propose(data)
    assert result['reference_face_ref'] == baseline['reference_face_ref']
    assert rows(result)['left']['measurement']['log_luminance'] == pytest.approx(
        rows(baseline)['left']['measurement']['log_luminance'], abs=2e-6)
