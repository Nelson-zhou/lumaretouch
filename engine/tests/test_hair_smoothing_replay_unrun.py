# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN retained manual-hair reopen/export contracts.

Synthetic measured bytes test transport/ownership only, not native numerics,
photographic quality, model accuracy, decode fidelity or runtime performance.
No product imports, tests, build, typecheck or inference ran during authoring.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import numpy as np
import pytest
from lumaretouch_engine import people_state as P, people_binding as B
from lumaretouch_engine import people_retained_analysis as RA, people_snapshot as SNAP
from lumaretouch_engine import hair_smoothing_state as S, hair_smoothing_support as SUPPORT
from lumaretouch_engine import hair_colour_replay as REPLAY, hair_colour_evidence as EVIDENCE
from lumaretouch_engine import people_algorithms as ALGORITHMS, people_open as OPEN
from test_hair_smoothing_support_unrun import fixture as support_fixture


def fixture(amount=.4):
    state, assets, ref, hair, semantic, proof, review = support_fixture()
    points = np.arange(478 * 3, dtype='<f4').reshape(478, 3) / np.float32(2000)
    face = state['faces'][ref['face_instance_id']]
    face['evidence']['landmark_digest'] = B.landmark_digest(points)
    state, assets = SUPPORT.retain(state, assets, ref, hair, review, proof,
        SUPPORT.retained_faces_digest(state, ref['asset_sha256'], hair))
    state = P.set_override(state, 'face', ref['face_instance_id'], S.OP, '/amount', amount)
    row = {'face_ref': ref, 'evidence': face['evidence'], 'landmarks': points}
    engine = SimpleNamespace(_precompute=None, _people_support=assets, _hair_colour_assets=hair,
        _hair_colour_evidence={EVIDENCE.identity(semantic): EVIDENCE.encode(semantic)},
        _people_landmarks=RA.retain({}, {ref['face_instance_id']: row}), _people_analyses={},
        _doc_path='synthetic-unread-original.png', _people_source=lambda: proof['source'],
        _people_owner=lambda: SimpleNamespace(snapshot=lambda: deepcopy(state)), _creative_base=None)
    return engine, state, proof['source'], ref, points


@pytest.mark.parametrize('amount', [.4, 0.])
def test_active_and_dormant_review_restore_exact_landmarks_without_new_semantics(amount):
    engine, state, source, ref, points = fixture(amount)
    bank = deepcopy(engine._people_support); hair = deepcopy(engine._hair_colour_assets)
    with mock.patch.object(EVIDENCE, 'current', side_effect=AssertionError('producer fallback')), \
         mock.patch.object(SUPPORT.M, 'raster', side_effect=AssertionError('replay must not raster or infer')):
        rows = REPLAY.analyses(engine, state, source)
    assert set(rows) == {ref['face_instance_id']} and engine._precompute is None
    actual = rows[ref['face_instance_id']]
    assert actual['face_ref'] == ref and actual['landmarks'].tobytes() == points.tobytes()
    assert not actual['landmarks'].flags.writeable
    assert actual['skin'] is None and actual['excluded'] is None
    assert 'face_skin' not in actual and 'body_skin' not in actual
    assert engine._people_support == bank and engine._hair_colour_assets == hair


@pytest.mark.parametrize('amount', [.4, 0.])
def test_people_open_short_circuits_before_face_producer_for_smoothing(amount):
    engine, state, source, ref, points = fixture(amount)
    decoded = SimpleNamespace(src_w=source['width'], src_h=source['height'], rgb=None)
    with mock.patch('lumaretouch_engine.local_mask_state.source_digest', return_value=source['sha256']), \
         mock.patch('lumaretouch_engine.face.build', side_effect=AssertionError('must not create model')):
        OPEN.prepare(engine, decoded, {})
    restored = engine._people_analyses[source['sha256']][ref['face_instance_id']]
    assert restored['landmarks'].tobytes() == points.tobytes() and engine._precompute is None


def test_pc_none_export_snapshot_has_measured_rows_not_fabricated_masks():
    engine, state, source, ref, points = fixture()
    assert engine._precompute is None
    rows = REPLAY.analyses(engine, state, source)
    frozen = SNAP.capture(state, source['sha256'], rows)
    actual = frozen['analyses'][ref['face_instance_id']]
    assert actual['landmarks'].tobytes() == points.tobytes()
    assert actual['excluded'] is None and actual['skin'] is None
    assert frozen['state'] == state and frozen['asset_sha256'] == source['sha256']
    # This is the existing no-precompute export capture consumer, not a new path.
    host = (Path(__file__).parents[1] / 'src/lumaretouch_engine/people_host.py').read_text()
    assert "if pc is None and binding is not None and state.get('_creative_base') is None:" in host
    assert 'restored=retained_hair_analyses(retained_host,graph,binding)' in host


@pytest.mark.parametrize('missing', ['support', 'manual-owner', 'semantic', 'landmarks'])
@pytest.mark.parametrize('amount', [.4, 0.])
def test_missing_required_smoothing_evidence_refuses_instead_of_requesting_inference(missing, amount):
    engine, state, source, ref, _ = fixture(amount)
    if missing == 'support': engine._people_support = {}
    elif missing == 'manual-owner': engine._hair_colour_assets = {}
    elif missing == 'semantic': engine._hair_colour_evidence = {}
    else: engine._people_landmarks = {}
    with mock.patch.object(EVIDENCE, 'current', side_effect=AssertionError('new evidence requested')):
        with pytest.raises(ValueError): REPLAY.analyses(engine, state, source)
    assert engine._precompute is None


def test_nonzero_intent_without_independent_review_is_not_repaired_by_replay():
    engine, state, source, ref, _ = fixture()
    state = SUPPORT.detach(state, ref)
    with pytest.raises(ValueError, match='independent retained'):
        REPLAY.analyses(engine, state, source)


def test_changed_source_census_including_disabled_claim_requires_review_not_detection():
    engine, state, source, ref, _ = fixture()
    other = deepcopy(state['faces'][ref['face_instance_id']])
    other.update(face_instance_id='disabled-owner', enabled=False, local_assets={})
    state['faces']['disabled-owner'] = other
    with pytest.raises(ValueError, match='Retained source people'):
        REPLAY.analyses(engine, state, source)


def test_foreign_source_and_unrelated_nonzero_operations_are_not_admitted_as_hair_only():
    engine, state, source, ref, _ = fixture()
    assert REPLAY.analyses(engine, state, {**source, 'sha256': 'f'*64}) is None
    changed = P.set_override(state, 'face', ref['face_instance_id'], ALGORITHMS.DEFORM,
                             sorted(ALGORITHMS.defaults()[ALGORITHMS.DEFORM])[0], .2)
    assert REPLAY.analyses(engine, changed, source) is None
    shared = P.set_override(state, 'all_people', source['sha256'], S.OP, '/amount', .2)
    with pytest.raises(ValueError, match='shared inheritance'):
        REPLAY.analyses(engine, shared, source)


def test_dormant_pointer_is_still_validated_and_never_stripped_to_make_replay_pass():
    engine, state, source, ref, _ = fixture(0.)
    key = state['faces'][ref['face_instance_id']]['local_assets'][S.KIND]['content_sha256']
    engine._people_support[key]['row']['review']['texture_scale'] *= 1.1
    before = deepcopy(state)
    with pytest.raises(ValueError): REPLAY.analyses(engine, state, source)
    assert state == before and S.KIND in state['faces'][ref['face_instance_id']]['local_assets']


def change_after_review(engine, state, ref, change):
    """Later edits retain the old review's immutable bytes, not current consent."""
    if change in ('added-enabled-face', 'added-disabled-face'):
        other = P.new_face(ref['asset_sha256'], [.01, .01, .1, .1], {
            'backend': 'manual', 'detector_model_sha256': None, 'semantic_model_sha256': None,
            'landmark_digest': None, 'status': 'unresolved', 'source_width': 64, 'source_height': 64,
            'orientation': 'exif_normalized_once'}, manual=True)
        other['enabled'] = change == 'added-enabled-face'
        state['faces'][other['face_instance_id']] = other
    elif change == 'changed-ownership':
        current = SUPPORT.H.resolve(state, engine._hair_colour_assets, ref)
        paint = deepcopy(current['support']); paint['objects'][0]['points'] = [[.35, .5]]
        reviewed = SUPPORT.H.reviewed(ref, current['source'], paint, current['semantic_model_sha256'],
            evidence_sha=current['semantic_evidence_sha256'], confirmed=True)
        state, engine._hair_colour_assets = SUPPORT.H.retain(state, engine._hair_colour_assets, reviewed)
    elif change == 'detached-ownership':
        state = SUPPORT.H.detach(state, ref)
    else:
        raise AssertionError('Unknown synthetic later edit')
    engine._people_owner = lambda: SimpleNamespace(snapshot=lambda: deepcopy(state))
    return state


@pytest.mark.parametrize('change', ['added-enabled-face', 'added-disabled-face',
                                  'changed-ownership', 'detached-ownership'])
def test_zero_review_reopens_and_exports_after_live_census_or_ownership_change(change):
    engine, state, source, ref, points = fixture(0.)
    old_support = deepcopy(engine._people_support)
    state = change_after_review(engine, state, ref, change)
    before = deepcopy(state)
    decoded = SimpleNamespace(src_w=source['width'], src_h=source['height'], rgb=None)
    with mock.patch.object(SUPPORT, 'resolve', side_effect=AssertionError('dormant live consent binding')), \
         mock.patch.object(SUPPORT, '_owners', side_effect=AssertionError('dormant current-owner census')), \
         mock.patch.object(EVIDENCE, 'current', side_effect=AssertionError('new semantic producer')), \
         mock.patch('lumaretouch_engine.local_mask_state.source_digest', return_value=source['sha256']), \
         mock.patch('lumaretouch_engine.face.build', side_effect=AssertionError('new face producer')):
        OPEN.prepare(engine, decoded, {})
        rows = REPLAY.analyses(engine, state, source)
        frozen = SNAP.capture(state, source['sha256'], rows)
    assert frozen['analyses'][ref['face_instance_id']]['landmarks'].tobytes() == points.tobytes()
    assert engine._people_analyses[source['sha256']][ref['face_instance_id']]['face_ref'] == ref
    assert engine._precompute is None and state == before and engine._people_support == old_support
    # Historical replay does not rewrite the old consent or authorize revival.
    active = P.set_override(state, 'face', ref['face_instance_id'], S.OP, '/amount', .4)
    with pytest.raises(ValueError): REPLAY.analyses(engine, active, source)


@pytest.mark.parametrize('change', ['added-disabled-face', 'changed-ownership', 'detached-ownership'])
def test_disabled_nonzero_review_is_historical_until_reenabled(change):
    engine, state, source, ref, _ = fixture(.4)
    state['faces'][ref['face_instance_id']]['enabled'] = False
    state = change_after_review(engine, state, ref, change)
    old_support = deepcopy(engine._people_support)
    with mock.patch.object(SUPPORT, 'resolve', side_effect=AssertionError('disabled live consent binding')), \
         mock.patch.object(SUPPORT, '_owners', side_effect=AssertionError('disabled current-owner census')):
        assert REPLAY.analyses(engine, state, source) == {}
    assert engine._people_support == old_support
    active = deepcopy(state); active['faces'][ref['face_instance_id']]['enabled'] = True
    with pytest.raises(ValueError): REPLAY.analyses(engine, active, source)


@pytest.mark.parametrize('enabled', [True, False])
@pytest.mark.parametrize('corruption', ['descriptor-kind', 'content-hash', 'historical-owner', 'historical-semantics'])
def test_dormant_pointer_still_rejects_exact_historical_corruption(enabled, corruption):
    engine, state, source, ref, _ = fixture(0.)
    state['faces'][ref['face_instance_id']]['enabled'] = enabled
    descriptor = state['faces'][ref['face_instance_id']]['local_assets'][S.KIND]
    record = engine._people_support[descriptor['content_sha256']]
    if corruption == 'descriptor-kind':
        descriptor['kind'] = 'hair_colour'
    elif corruption == 'content-hash':
        # Well-shaped but no longer the exact descriptor-pinned content.
        record['row']['retained_faces_sha256'] = 'f'*64
        unsigned = {**record, 'row': {k: v for k, v in record['row'].items() if k != 'review_key'}}
        record['row']['review_key'] = SUPPORT.content_digest(unsigned)
    elif corruption == 'historical-owner':
        key = record['row']['hair_colour_asset_sha256']
        engine._hair_colour_assets[key]['support']['objects'][0]['points'] = [[.25, .5]]
    else:
        key = record['row']['semantic_evidence_sha256']
        engine._hair_colour_evidence[key]['weight_sha256'] = 'f'*64
    before = deepcopy(state)
    with mock.patch.object(SUPPORT, 'resolve', side_effect=AssertionError('must not rebind dormant review')), \
         mock.patch.object(SUPPORT, '_owners', side_effect=AssertionError('must not check dormant live owners')):
        with pytest.raises(ValueError): REPLAY.analyses(engine, state, source)
    assert state == before and S.KIND in state['faces'][ref['face_instance_id']]['local_assets']
