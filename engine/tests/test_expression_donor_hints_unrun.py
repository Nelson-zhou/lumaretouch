# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored fixtures, deliberately UNRUN: no builds/inference/runtime acceptance."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from lumaretouch_engine import expression_donor_hints as H
from lumaretouch_engine.people_binding import landmark_digest


def measured():
    points = [[.5, .5, 0.] for _ in range(478)]
    from lumaretouch_engine.picks import EYE_LEFT, EYE_RIGHT
    for eye in (EYE_LEFT, EYE_RIGHT):
        points[eye['inner']] = [.4, .5, 0.]
        points[eye['outer']] = [.6, .5, 0.]
        points[eye['upper']] = [.5, .48, 0.]
        points[eye['lower']] = [.5, .52, 0.]
    ref = {'asset_sha256': 'a'*64, 'face_instance_id': 'face-a', 'analysis_revision': 0}
    evidence = {'backend': 'mediapipe', 'status': 'verified', 'detector_model_sha256': 'b'*64,
                'semantic_model_sha256': 'c'*64, 'landmark_digest': landmark_digest(points),
                'source_width': 2000, 'source_height': 1000, 'orientation': 'exif_normalized_once'}
    face = {**ref, 'manual': False, 'evidence': evidence}
    return face, {'face_ref': ref, 'evidence': deepcopy(evidence), 'landmarks': points}


def test_exact_per_face_geometry_not_photo_level_aggregate():
    face, record = measured()
    assert H.eyelid_evidence(face, record) == pytest.approx(.1, abs=1e-5)
    record['face_ref']['analysis_revision'] += 1
    assert H.eyelid_evidence(face, record) is None


def test_corrupt_or_synthetic_geometry_is_unknown():
    face, record = measured()
    record['landmarks'][0][0] = .1
    assert H.eyelid_evidence(face, record) is None
    face, record = measured()
    face['manual'] = True
    assert H.eyelid_evidence(face, record) is None
    assert H.eyelid_evidence(face, None) is None


def test_geometry_order_unknown_last_no_best_or_auto_selection():
    rows = [{'document_id':'a','eye_aperture':None}, {'document_id':'b','eye_aperture':0.},
            {'document_id':'c','eye_aperture':.2}, {'document_id':'d','eye_aperture':.1}]
    assert [x['document_id'] for x in H.ordered(rows)] == ['c','d','b','a']
    assert rows[0]['document_id'] == 'a'


def test_optional_hint_failure_does_not_claim_manual_failure(monkeypatch):
    def failed(*args, **kwargs): raise ValueError('stale associated original')
    monkeypatch.setattr(H, 'collect', failed)
    assert H.safe_collect(None)['cohorts'] == []
    def cancelled(*args, **kwargs): raise InterruptedError('cancelled')
    monkeypatch.setattr(H, 'collect', cancelled)
    with pytest.raises(InterruptedError): H.safe_collect(None)


def test_transport_filename_is_bounded_and_not_a_path():
    label = H.filename('/tmp/' + '😀'*300 + '\n.png')
    assert len(label.encode('utf-16-le')) <= 512 and '\n' not in label and '/' not in label


def test_source_wiring_no_decoder_or_write_owner():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    source = (root/'engine/src/lumaretouch_engine/expression_donor_hints.py').read_text()
    assert "x['state'] == 'confirmed'" in source
    assert "I.verify(" in source and "replica['generation']" in source
    assert 'capture_file(' not in source and 'capture_original(' not in source
    assert '.commit(' not in source and 'pick_original_focus' not in source
