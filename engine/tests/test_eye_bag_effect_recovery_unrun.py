# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Synthetic ownership and numerical fixtures, not photo QA."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine import people_effects as E
from lumaretouch_engine import eye_bag_effect_recovery as F
from lumaretouch_engine import effect_recovery_state as R
from lumaretouch_engine import facial_wrinkle_recovery as OWNER

REF = {'asset_sha256': 'a'*64, 'face_instance_id': 'face-one', 'analysis_revision': 2}


def field(value, *, ref=REF, stage=F.TARGET):
    weight = np.full((2, 3), value, np.uint8)
    return {'face_ref': deepcopy(ref), 'stage': stage, 'weight': weight,
        'content_sha256': sha256(weight.tobytes()).hexdigest(), 'recipe_sha256': 'b'*64}


def test_full_recovery_preserves_other_stage_current_rgb():
    current = np.full((2, 3, 3), .35, np.float32)
    unrelated = E.LocalEffect(REF, 'eye_detail', (0, 0, 2, 3),
        delta=np.full_like(current, .07))
    mixed, _ = E.apply('eye_detail', current, [unrelated])
    eye = E.LocalEffect(REF, F.TARGET, (0, 0, 2, 3), delta=np.full_like(current, .1))
    result, _ = E.apply(F.TARGET, mixed, [unrelated, eye],
        recovery={(REF['face_instance_id'], F.TARGET): field(255)})
    np.testing.assert_array_equal(result, mixed)
    assert np.any(result != current)  # Other stage is not erased back to source.


def test_zero_recovery_is_exact_existing_stage():
    current = np.full((2, 3, 3), .35, np.float32)
    eye = E.LocalEffect(REF, F.TARGET, (0, 0, 2, 3), delta=np.full_like(current, .1))
    original, _ = E.apply(F.TARGET, current, [eye])
    result, _ = E.apply(F.TARGET, current, [eye],
        recovery={(REF['face_instance_id'], F.TARGET): field(0)})
    np.testing.assert_array_equal(result, original)


@pytest.mark.parametrize('wrong', [field(255, ref={**REF, 'face_instance_id': 'other-face'}),
                                  field(255, stage='eye_detail')])
def test_other_face_or_family_refused(wrong):
    with pytest.raises(ValueError, match='another face'):
        E.verify_recovery(REF, F.TARGET, wrong, (2, 3))


def test_new_target_is_separate_face_owned_family():
    assert F.TARGET in OWNER.FACE_TARGETS and R.target(F.TARGET) == F.TARGET
    assert F.TARGET != 'eye_bag_ridge_visibility' and F.TARGET != 'eye_detail'
    with pytest.raises(ValueError):
        OWNER.check_row({'target': F.TARGET}, {'sha256': 'a'*64})


def test_full_render_stages_candidate_assets_without_live_swap(monkeypatch):
    from lumaretouch_engine import full_candidate_render as FULL
    transaction = {'target': F.TARGET, 'context': {'source': 'owned'},
        'before': {'graph': 'old'}, 'candidate': {'graph': 'candidate'},
        'assets': {'new': 'immutable-vector'}, 'no_change': False}
    proof = {'before': {'source_proof': 'same', 'people_sha256': 'before'},
        'after': {'source_proof': 'same', 'people_sha256': 'after'}, 'path_stamp': [1, 2]}
    engine = SimpleNamespace(support={'old': 'untouched'})
    context = {'people_support_assets': transaction['assets']}
    monkeypatch.setattr(F, '_identity', lambda *args: (deepcopy(proof), ({'path': 'file'}, {},
        SimpleNamespace(document_id='doc', revision=3), context)))
    calls = []
    def render(*args, **kwargs):
        calls.append(kwargs)
        key = 'after' if 'staged_people_context' in kwargs else 'before'
        return object(), {**proof[key], 'source_size': [1200, 800], 'output_size': [1200, 800]}
    monkeypatch.setattr(FULL, 'render', render)
    monkeypatch.setattr(F, '_display', lambda rgb, proof: ('MOCK-not-image', (800, 533)))
    result, retained = F.render(engine, transaction)
    assert calls[0] == {'people_graph': transaction['before']}
    assert calls[1]['staged_people_context']['people_support_assets'] == transaction['assets']
    assert engine.support == {'old': 'untouched'}
    assert result['quality'] == 'full-source-render-srgb8'
    assert 'prepared' not in retained['transaction']


def test_private_render_proof_invalidates_changed_source_or_graph(monkeypatch):
    transaction = {'target': F.TARGET, 'candidate': {'version': 2}}
    review = {'transaction': transaction, 'identity': {'fingerprint': 'before'}}
    monkeypatch.setattr(F, '_identity', lambda *args: ({'fingerprint': 'changed'}, None))
    with pytest.raises(ValueError, match='source, repair, support or graph'):
        F.verify(object(), review)
    with pytest.raises(ValueError, match='candidate differs'):
        F.verify(object(), review, {'target': F.TARGET, 'candidate': {'version': 3}})


def test_presented_apply_and_commit_revalidate_private_full_proof():
    root = Path(__file__).parents[1] / 'src' / 'lumaretouch_engine'
    preview = (root / 'effect_recovery_preview.py').read_text()
    commit = (root / 'people_recovery.py').read_text()
    assert "verify(self.engine, record.get('eye_bag_full_review'))" in preview
    assert "verify(self.engine, record.get('eye_bag_full_review'), stage.people_recovery)" in preview
    assert "verify(engine, transaction.get('full_review'), transaction)" in commit
    assert 'from .eye_bag_preserve_host import _live' in (root / 'eye_bag_effect_recovery.py').read_text()


def test_new_family_cannot_fall_back_to_unconsumed_global_row():
    with pytest.raises(ValueError, match='face-local'):
        F.reject_global({'targets': [{'target': F.TARGET}]})
    F.reject_global({'targets': []})


def test_face_asset_roundtrip_retains_history_and_rejects_foreign_owner():
    from lumaretouch_engine import people_state as P, people_support_assets as BANK
    graph = P.empty()
    # Existing source validator's exact identity shape, not display dimensions.
    source = {'sha256': 'a'*64, 'width': 100, 'height': 120}
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'c'*64,
        'semantic_model_sha256': 'd'*64, 'landmark_digest': 'e'*64,
        'status': 'verified', 'source_width': 100, 'source_height': 120,
        'orientation': 'exif_normalized_once'}
    face = P.new_face(source['sha256'], [.1, .1, .9, .9], evidence)
    graph['faces'][face['face_instance_id']] = face
    ref = P.face_ref(face)
    row = {'target': F.TARGET, 'enabled': True,
        'owner': {'version': 1, 'source_sha256': source['sha256'],
            'landmarks_sha256': evidence['landmark_digest'], 'backend': 'mediapipe'},
        'recipe': {'version': 1, 'domain': 'source-normalized', 'objects': [{
            'id': 'recover-one', 'name': 'Recovery', 'kind': 'brush', 'enabled': True,
            'operation': 'add', 'opacity': 1., 'feather': 0.,
            'points': [[.3, .4], [.4, .4]], 'axes': [[.01, 0], [0, .01]]}]}}
    updated, assets = BANK.retain(graph, {}, ref, source, row)
    BANK.check_store(assets)
    assert BANK.resolve(updated, assets, ref, F.TARGET)['targets'] == [row]
    detached = BANK.detach(updated, ref, F.TARGET)
    assert F.TARGET not in detached['faces'][ref['face_instance_id']]['local_assets']
    assert BANK.resolve(updated, assets, ref, F.TARGET) is not None  # Undo bytes retained.
    changed = deepcopy(row); changed['owner']['landmarks_sha256'] = 'f'*64
    with pytest.raises(ValueError, match='another retained source analysis'):
        BANK.retain(graph, assets, ref, source, changed)
