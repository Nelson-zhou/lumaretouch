# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: catalog-bound reference-choice host protocol only.

No test collection/execution, product import, native/model inference, build or
hardware probe occurred during authoring. Existing synthetic review fixture,
mock capture and fake measured diagnostics exercise host routing/fences only;
they are not genuine source authentication, photometry or visual acceptance.
"""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import math
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine import skin_reference_choice_host as H
from lumaretouch_engine import people_state as P
from lumaretouch_engine.portrait_fit_source import FullSource
from test_skin_reference_body_review_unrun import host as body_host, display, ASSET

BUDGET = 4 * 1024**3


def fake_measured(state, source, pixels, manual):
    """Explicit protocol double, not a replacement luminance implementation."""
    candidates = []
    for index, (_, face) in enumerate(sorted(state['faces'].items())):
        row = {'face_ref': P.face_ref(face), 'status': 'disabled'}
        if face['enabled']:
            row.update(status='measured', measurement={
                'log_luminance': -2.0 + index * .1, 'linear_luminance': math.exp(-2.0 + index * .1),
                'initial_log_luminance_mad': .01, 'robust_sample_count': 512,
                'robust_weight': 256., 'effective_samples': 300., 'retained_weight_fraction': .9},
                source_window=[0, 0, 32, 32], support_sha256='9'*64,
                evidence=deepcopy(face['evidence']), landmark_digest=face['evidence']['landmark_digest'],
                face_skin_observation={'contract': 'mediapipe-face-skin-edit-weight-v1',
                    'source_sha256': ASSET, 'semantic_model_sha256': 'c'*64,
                    'producer_width': 128, 'producer_height': 64},
                protected_face_boxes=len(state['faces'])-1,
                protected_actual_face_ovals=len(state['faces'])-1)
        candidates.append(row)
    run = state['analysis_runs'].get(ASSET)
    value = {'version': H.CHOICE.VERSION, 'operation_id': H.FACE.S.OP,
        'control_id': H.FACE.S.CONTROL_ID, 'method': H.CHOICE.METHOD,
        'source': deepcopy(source), 'source_stage': H.FACE.SUPPORT.SOURCE_STAGE,
        'source_pixels_sha256': pixels.input_sha256, 'source_kind': pixels.kind,
        'source_bits': pixels.source_bits, 'source_encoding': H.R.N.ENCODING,
        'state_revision': state['revision'], 'association_revision': state['association_revision'],
        'candidate_scope': 'all-enabled-retained-same-source-faces', 'census_complete': False,
        'detector_limit_reached': None if run is None else run['limit_reached'],
        'candidates': candidates, 'read_only_proposal': True, 'review_required': True,
        'reference_face_exclusion_required': True, 'body_extension_enabled': False,
        'fit_retained': False, 'portable': False, 'memory_admission_bytes': 256 * 1024**2,
        'limitations': ['protocol-double-not-real-photometry'],
        **H.CHOICE._selection(candidates, run, manual)}
    value['proposal_sha256'] = H.FACE.digest(value)
    return value


@pytest.fixture
def choice(body_host, monkeypatch):
    h = body_host
    content = np.full((128, 256, 3), .4, np.float32).tobytes()
    h.pixels = FullSource(ASSET, 256, 128, sha256(content).hexdigest(), 16,
                         'original', H.SOURCE.memory_estimate(h.source), content)
    h.captures = []; h.decoded = []; h.measurements = []; h.measurement_budgets = []; h.verify_calls = []
    monkeypatch.setattr(H, 'available_estimate', lambda: BUDGET)
    monkeypatch.setattr(H.FACE, 'snapshot_key', H.BODY.snapshot_key)
    for module in (H.FACE, H.BODY):
        monkeypatch.setattr(module, '_source_display',
            lambda engine, source: (display(b'FAKE SOURCE DISPLAY'), h.pixels.input_sha256))
        original = module._verify_source
        def verify(engine, state, target, entry, *, original=original, module=module):
            h.verify_calls.append(module.S.OP)
            return original(engine, state, target, entry)
        monkeypatch.setattr(module, '_verify_source', verify)
    monkeypatch.setattr(H.FACE.S, 'capability', lambda: {
        'skin_reference_match_available': True, 'skin_reference_match_reason': None})
    def capture(engine, *, expected_source, byte_budget, cancelled):
        h.captures.append(byte_budget)
        assert engine is h.engine and expected_source == h.source
        if cancelled():
            raise InterruptedError('Synthetic capture cancelled')
        if H.SOURCE.memory_estimate(expected_source) > byte_budget:
            raise MemoryError('Synthetic decode budget refused before any pixels')
        h.decoded.append(True)
        return h.pixels
    monkeypatch.setattr(H.SOURCE, 'capture', capture)
    def measured(state, asset, pixels, analyses, *, byte_budget, manual_reference, cancelled):
        assert asset == ASSET and pixels is h.pixels
        assert analyses is h.engine._people_analyses[ASSET]
        assert byte_budget < BUDGET and not cancelled()
        h.measurements.append((manual_reference, sorted(analyses)))
        h.measurement_budgets.append(byte_budget)
        return fake_measured(state, h.source, pixels, manual_reference)
    monkeypatch.setattr(H.CHOICE, 'propose', measured)
    # No numerical apply, source relation retention or commit can be reached.
    monkeypatch.setattr(H.FACE.SUPPORT, 'retain', lambda *a, **k: pytest.fail('Proposal cannot retain support'))
    yield h
    store = h.engine.__dict__.get('_skin_reference_match_reviews')
    if store is not None:
        store['images'].directory.cleanup()


def request(h, family='face', **extra):
    module = H.FAMILIES[family][0]
    catalog = module.catalogue(h.engine, h.owner.snapshot(), h.target, {})
    h.verify_calls.clear()
    return {'family': family, 'source_review_sha256': catalog['source_review_sha256'], **extra}


def run(h, payload, **options):
    return H.propose(h.engine, h.owner.snapshot(), h.target, payload,
                     byte_budget=options.pop('byte_budget', BUDGET), **options)


@pytest.mark.parametrize('family', ['face', 'body'])
def test_family_exact_receipt_echo_json_and_no_side_effects(choice, family):
    h = choice; payload = request(h, family); state = h.owner.snapshot()
    before = deepcopy((h.engine._people_support, h.engine._people_cursors,
                       h.engine._people_targets, h.engine.body_bank))
    module, name = H.FAMILIES[family]; store = h.engine.__dict__[name]
    # An unrelated expired pending item must not be pruned by this read.
    store['pending']['unchanged'] = {'expires': 0, 'claimed': False}
    pending = deepcopy(store['pending']); sources = list(store['sources'])
    result = run(h, payload)
    assert set(result) == H.REPORT_FIELDS
    assert result['operation_id'] == module.S.OP and result['family'] == family
    assert result['proposal']['operation_id'] == H.FACE.S.OP
    assert result['skin_reference_choice_request'] == payload
    assert 'manual_reference' not in result['skin_reference_choice_request']
    assert result['source_pixels_sha256'] == h.pixels.input_sha256
    assert len(h.verify_calls) == 3 and set(h.verify_calls) == {module.S.OP}
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    assert result['read_only_proposal'] and result['source_image_load_required'] and result['review_required']
    assert not result['grants_consent'] and not result['render_committed'] and not result['portable']
    assert h.owner.snapshot() == state and h.engine.renders == [] and h.engine.writes == []
    assert before == (h.engine._people_support, h.engine._people_cursors,
                      h.engine._people_targets, h.engine.body_bank)
    assert store['pending'] == pending and list(store['sources']) == sources
    proof = result.pop('report_sha256'); assert H.FACE.digest(result) == proof


@pytest.mark.parametrize('manual', [None, 'first'])
def test_explicit_null_and_manual_override_are_not_silently_normalized(choice, manual):
    h = choice; ref = None if manual is None else h.refs[manual]
    payload = request(h, manual_reference=deepcopy(ref)); result = run(h, payload)
    assert result['skin_reference_choice_request'] == payload
    assert 'manual_reference' in result['skin_reference_choice_request']
    if ref is not None:
        assert result['proposal']['reference_face_ref'] == ref
        assert result['proposal']['selection_mode'] == 'manual-override-proposal'
        assert result['proposal']['automatic_reference_face_ref'] != ref


@pytest.mark.parametrize('fault', ['unknown-family', 'missing-family', 'extra', 'foreign-manual',
    'cursor-target', 'wrong-family-receipt', 'unknown-receipt', 'expired', 'mutated-receipt'])
def test_exact_schema_and_family_source_receipt_fail_before_decode(choice, fault):
    h = choice; payload = request(h); target = deepcopy(h.target)
    if fault == 'unknown-family': payload['family'] = 'merged'
    elif fault == 'missing-family': del payload['family']
    elif fault == 'extra': payload['ownership_confirmed'] = True
    elif fault == 'foreign-manual': payload['manual_reference'] = {**h.refs['first'], 'asset_sha256': '0'*64}
    elif fault == 'cursor-target': target = {'scope': 'face', 'target_id': 'first', 'face_ref': h.refs['first']}
    elif fault == 'wrong-family-receipt': payload['family'] = 'body'
    elif fault == 'unknown-receipt': payload['source_review_sha256'] = '0'*64
    else:
        entry = h.engine._skin_reference_match_reviews['sources'][payload['source_review_sha256']]
        if fault == 'expired': entry['expires'] = 0
        else: entry['source_review']['source_pixels_sha256'] = '0'*64
    with pytest.raises(ValueError):
        H.propose(h.engine, h.owner.snapshot(), target, payload, byte_budget=BUDGET)
    assert h.decoded == [] and h.measurements == []


@pytest.mark.parametrize('when', ['capture', 'measure'])
@pytest.mark.parametrize('change', ['graph', 'load', 'revision', 'path', 'repair',
    'source', 'body-bank', 'analysis', 'unavailable-analysis', 'support', 'catalog-replaced', 'expired'])
def test_before_after_fences_discard_stale_result(choice, monkeypatch, when, change):
    h = choice
    if change == 'unavailable-analysis':
        del h.engine._people_analyses[ASSET]['first']
    payload = request(h)
    def mutate():
        if change == 'graph': h.owner.fence += 1
        elif change == 'load': h.engine._load_id = 'new-load'
        elif change == 'revision': h.version.revision += 1
        elif change == 'path': h.engine.row['path'] = '/synthetic/new.png'
        elif change == 'repair': h.engine.current['repair'] = 'changed'
        elif change == 'source': h.engine.current['source'] = '0'*64
        elif change == 'body-bank': h.engine.body_bank['revision'] += 1
        elif change == 'analysis': h.engine._people_analyses[ASSET]['first']['excluded'][0, 0] = .3
        elif change == 'unavailable-analysis':
            h.engine._people_analyses[ASSET]['first'] = {'face_ref': h.refs['first']}
        elif change == 'support': h.engine._people_support['0'*64] = {}
        else:
            entries = h.engine._skin_reference_match_reviews['sources']
            old = entries[payload['source_review_sha256']]
            if change == 'expired': old['expires'] = 0
            else: entries[payload['source_review_sha256']] = dict(old)
    module, attr = (H.SOURCE, 'capture') if when == 'capture' else (H.CHOICE, 'propose')
    original = getattr(module, attr)
    def interrupted(*args, **kwargs):
        value = original(*args, **kwargs); mutate(); return value
    monkeypatch.setattr(module, attr, interrupted)
    with pytest.raises(ValueError): run(h, payload)
    assert h.engine.renders == [] and h.engine.writes == []


def test_native_precision_and_catalog_original_digest_are_mandatory(choice, monkeypatch):
    h = choice; payload = request(h)
    original = H.SOURCE.capture
    monkeypatch.setattr(H.SOURCE, 'capture', lambda *a, **k:
        replace(original(*a, **k), input_sha256='0'*64))
    with pytest.raises(ValueError, match='original pixels'): run(h, payload)
    assert h.measurements == []


def test_actual_resident_backing_charged_before_decode(choice):
    h = choice; payload = request(h)
    backing = np.empty((1024, 1024, 4), np.float32)
    h.engine._src_rgb = backing[:1, :1, :3]
    assert H._resident_bytes(h.engine._src_rgb) >= H.HOST_FIXED_BYTES + backing.nbytes
    with pytest.raises(MemoryError):
        run(h, payload, byte_budget=H.HOST_FIXED_BYTES + backing.nbytes)
    assert h.decoded == [] and h.measurements == []


def test_capture_admission_receives_budget_minus_live_source_and_analyses(choice):
    h = choice; payload = request(h); result = run(h, payload)
    memory = result['memory']
    assert memory['resident_input_bytes'] > H.HOST_FIXED_BYTES
    assert h.captures == [memory['capture_byte_budget']]
    assert memory['verification_workspace_bytes'] >= H.VERIFY_FIXED_BYTES
    assert memory['capture_byte_budget'] == BUDGET - memory['resident_input_bytes'] - memory['verification_workspace_bytes']
    assert memory['estimated_peak_bytes'] <= memory['total_byte_budget']


def test_tiny_budget_cannot_enter_family_snapshot_or_document_capture(choice, monkeypatch):
    h = choice; payload = request(h)
    monkeypatch.setattr(H.FACE, '_verify_source',
        lambda *a, **k: pytest.fail('Verifier would allocate an unadmitted people snapshot'))
    h.engine._people_preset_capture = lambda: pytest.fail('Document capture preceded admission')
    with pytest.raises(MemoryError, match='before any snapshot'):
        run(h, payload, byte_budget=1)
    assert h.captures == [] and h.measurements == [] and h.verify_calls == []


def test_shared_producer_planes_are_charged_per_face_before_snapshot(choice, monkeypatch):
    h = choice; payload = request(h)
    plane = np.empty((256, 256), np.float32)
    h.engine._precompute = SimpleNamespace(masks={name: plane for name in
        ('hair', 'clothes', 'background', 'skin', 'face_skin', 'body_skin')})
    entry = h.engine._skin_reference_match_reviews['sources'][payload['source_review_sha256']]
    state = h.owner.snapshot()
    workspace = H._verification_workspace(h.engine, state, entry)
    # Eight output planes per retained face even though all six producer names
    # share ONE array. Snapshot copies cannot use resident-storage deduplication.
    assert workspace >= H.VERIFY_FIXED_BYTES + (8 * len(state['faces']) + 16) * plane.nbytes
    required = H._resident_inputs(h.engine, state, None, entry) + workspace
    monkeypatch.setattr(H.FACE, '_verify_source',
        lambda *a, **k: pytest.fail('Shared-plane snapshot entered without complete admission'))
    with pytest.raises(MemoryError, match='before allocation'):
        run(h, payload, byte_budget=required - 1)
    assert h.captures == [] and h.measurements == [] and h.verify_calls == []


@pytest.mark.parametrize('when,verified', [('capture', 1), ('measure', 2)])
def test_post_capture_guards_reserve_snapshots_with_full_source_resident(choice, monkeypatch, when, verified):
    h = choice; payload = request(h)
    entry = h.engine._skin_reference_match_reviews['sources'][payload['source_review_sha256']]
    low = {'active': False}
    resident = H._resident_inputs(h.engine, h.owner.snapshot(), h.engine.current, entry)
    workspace = H._verification_workspace(h.engine, h.owner.snapshot(), entry)
    # This would fit the retained source without snapshot copies, but not the
    # source PLUS the family verifier's complete transient allocation reserve.
    insufficient = resident + workspace + h.pixels.owned_bytes - 1
    monkeypatch.setattr(H, 'available_estimate', lambda: insufficient if low['active'] else BUDGET)
    module, attr = (H.SOURCE, 'capture') if when == 'capture' else (H.CHOICE, 'propose')
    original = getattr(module, attr)
    def lower_headroom(*args, **kwargs):
        value = original(*args, **kwargs); low['active'] = True; return value
    monkeypatch.setattr(module, attr, lower_headroom)
    with pytest.raises(MemoryError, match='before allocation'):
        run(h, payload)
    assert len(h.verify_calls) == verified
    assert len(h.measurements) == (0 if when == 'capture' else 1)
    assert h.engine.writes == [] and h.engine.renders == []


def test_report_preserves_actual_allowance_when_headroom_recovers(choice, monkeypatch):
    h = choice; payload = request(h); headroom = {'value': BUDGET}
    monkeypatch.setattr(H, 'available_estimate', lambda: headroom['value'])
    original_verify = H.FACE._verify_source
    def verify(*args, **kwargs):
        value = original_verify(*args, **kwargs)
        if len(h.verify_calls) == 1:
            headroom['value'] = BUDGET // 2
        return value
    monkeypatch.setattr(H.FACE, '_verify_source', verify)
    original_capture = H.SOURCE.capture
    def capture(*args, **kwargs):
        value = original_capture(*args, **kwargs); headroom['value'] = BUDGET; return value
    monkeypatch.setattr(H.SOURCE, 'capture', capture)
    memory = run(h, payload)['memory']
    assert memory['capture_byte_budget'] == h.captures[-1]
    assert memory['measurement_byte_budget'] == h.measurement_budgets[-1]
    assert memory['measurement_byte_budget'] > memory['capture_byte_budget']


def test_later_resident_growth_does_not_relabel_historical_measurement_allowance(choice, monkeypatch):
    h = choice; payload = request(h); original = H.CHOICE.propose
    def measured(*args, **kwargs):
        value = original(*args, **kwargs)
        # Unrelated retained display buffer growth; no source/recipe mutation.
        h.engine._src_rgb = np.empty((128, 128, 3), np.float32)
        return value
    monkeypatch.setattr(H.CHOICE, 'propose', measured)
    result = run(h, payload); memory = result['memory']
    reserved = memory['resident_input_bytes'] + memory['verification_workspace_bytes']
    assert memory['measurement_byte_budget'] == h.measurement_budgets[-1]
    assert memory['measurement_byte_budget'] > memory['total_byte_budget'] - reserved
    assert reserved + result['proposal']['memory_admission_bytes'] <= memory['estimated_peak_bytes'] <= memory['total_byte_budget']


@pytest.mark.parametrize('fault', ['extra', 'extra-row', 'nan', 'missing-face', 'manual-substitute', 'consent'])
def test_final_strict_measured_report_rejects_schema_or_authority_drift(choice, monkeypatch, fault):
    h = choice; payload = request(h, manual_reference=h.refs['first'])
    original = H.CHOICE.propose
    def malformed(*args, **kwargs):
        value = original(*args, **kwargs)
        if fault == 'extra': value['automatic_ack'] = True
        elif fault == 'extra-row': value['candidates'][0]['body_permission'] = True
        elif fault == 'nan': value['candidates'][0]['measurement']['log_luminance'] = float('nan')
        elif fault == 'missing-face': value['candidates'].pop()
        elif fault == 'manual-substitute': value['reference_face_ref'] = h.refs['second']
        else: value['review_required'] = False
        if fault != 'nan':
            value['proposal_sha256'] = H.FACE.digest({k: v for k, v in value.items() if k != 'proposal_sha256'})
        return value
    monkeypatch.setattr(H.CHOICE, 'propose', malformed)
    with pytest.raises(ValueError): run(h, payload)
    assert h.engine.writes == []


@pytest.mark.parametrize('failure', [MemoryError('resources'), RuntimeError('native unavailable'),
                                   InterruptedError('cancelled')])
def test_native_failure_and_cancellation_propagate_without_fallback(choice, monkeypatch, failure):
    h = choice; payload = request(h)
    def fail(*args, **kwargs): raise failure
    monkeypatch.setattr(H.CHOICE, 'propose', fail)
    with pytest.raises(type(failure), match=str(failure)): run(h, payload)
    assert h.engine.writes == [] and h.engine.renders == []


def test_malformed_read_identified_without_ever_becoming_a_write():
    assert H.read_only({'cmd': 'people', 'action': H.ACTION, 'payload': None})
    assert not H.read_only({'cmd': 'people', 'action': 'skin_reference_choice_confirm'})
    assert H.ACTIONS == H.READS
