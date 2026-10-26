# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN review/crop/transaction fixtures with synthetic test doubles.

These fixtures are not decoder/native/photo/UI/quality acceptance. No runtime,
product import, test, typecheck, build or inference ran during source authoring.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import hair_smoothing_host as H, hair_smoothing_review as I
from lumaretouch_engine import hair_smoothing_support as C, hair_smoothing_actions as A
from lumaretouch_engine import hair_colour_evidence as E, full_candidate_render as F
from test_hair_smoothing_support_unrun import fixture as support_fixture


def fixture(monkeypatch):
    state, assets, ref, hair, semantic, proof, review = support_fixture()
    source = proof['source']; target = {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': ref}
    row = {'path': 'synthetic-unread-original.png', 'document_id': 'document'}
    snapshot = {'fixture': 'no photograph read'}; version = SimpleNamespace(document_id='document', revision=7)
    rgb = np.full((64,64,3), .25, np.float32); rgb.setflags(write=False)
    engine = SimpleNamespace(_people_support=assets, _hair_colour_assets=hair,
        _hair_colour_evidence={E.identity(semantic): E.encode(semantic)},
        _people_targets={source['sha256']: target}, _people_cursors={source['sha256']: ref['face_instance_id']},
        _people_analyses={source['sha256']: {ref['face_instance_id']: {'face_ref': ref}}},
        _people_source=lambda: source, _people_binding=lambda: {'binding': 1}, _capture_state=lambda: snapshot,
        _document_versions=lambda: SimpleNamespace(version=lambda _: version), _docs=[row], _doc_index=0,
        fixture_pixels=rgb, fixture_delta=0., fixture_measurement='f'*64, fixture_calls=[])
    owner = SimpleNamespace(snapshot=lambda: deepcopy(state), fence=19); engine._people_owner=lambda: owner
    monkeypatch.setattr(H, '_single_document', lambda *args: None)
    monkeypatch.setattr(H, 'require_geometry', lambda *args: None)
    monkeypatch.setattr(F, 'identity', lambda *args, **kwargs: (
        {'source_proof': proof['source_proof'], 'document_id': 'document', 'revision': '7',
         'candidate_sha256': H._fingerprint(snapshot)}, state,
        {'people_graph': state, 'people_support_assets': engine._people_support}))
    def source_packet(owner, graph, capture, **kwargs):
        actual = deepcopy(proof); actual['input_sha256'] = sha256(owner.fixture_pixels.tobytes()).hexdigest()
        return SimpleNamespace(rgb=owner.fixture_pixels, analysis={'face_ref': ref}, proof=actual, resident_bytes=rgb.nbytes)
    monkeypatch.setattr(H, '_source', source_packet)
    def diagnostic(owner, graph, capture, candidate, candidate_assets, amount, expected_proof, **kwargs):
        image = I.full_image(np.full((64,64,3), (.1,.9,.9), np.float32))
        diagnostics = {'supported_pixels': 64, 'context_rejected_pixels': 10, 'directional_pixels': 0,
            'changed_pixels': 0, 'no_signal_reason': 'no_admitted_directional_signal', 'texture_scale_px': 2.,
            'runtime_quality_accepted': False}
        return image, owner.fixture_measurement, H._binding(source_packet(owner,graph,capture),capture), diagnostics
    monkeypatch.setattr(H, '_diagnostic', diagnostic)
    def render(owner, current, captured, document, revision, **kwargs):
        owner.fixture_calls.append(deepcopy(kwargs)); staged = kwargs.get('staged_people_context')
        result = np.full((64,64,3), .35, np.float32); result[30,30,0] += owner.fixture_delta
        return result, {'source_proof': proof['source_proof'], 'source_size': [64,64], 'output_size': [64,64],
            'hair_smoothing_measurements': [] if staged is None else [{'face_ref': ref,'measurement_key':owner.fixture_measurement}]}
    monkeypatch.setattr(F, 'render', render)
    return engine, state, target, {'review':review,'amount':.4}


def ready(monkeypatch):
    engine,state,target,payload = fixture(monkeypatch)
    reference = H.reference(engine,state,target,{})
    source_crop = H.crop(engine,state,target,{'reference_id':reference['reference_id'],'plane':'source','rect':[20,20,16,16]})
    preview = H.preview(engine,state,target,payload)
    return engine,state,target,payload,reference,source_crop,preview


def inspected(monkeypatch):
    values=ready(monkeypatch);engine,state,target,*_,preview=values;rect=[20,20,16,16]
    before=H.crop(engine,state,target,{'preview_id':preview['preview_id'],'plane':'before','rect':rect})
    after=H.crop(engine,state,target,{'preview_id':preview['preview_id'],'plane':'after','rect':rect})
    ack={'preview_id':preview['preview_id'],'reviewed':True,
        **{key+'_sha256':preview[key]['sha256'] for key in ('before','after','support')},
        'inspection':{'rect':rect,'before_sha256':before['image']['sha256'],'after_sha256':after['image']['sha256']}}
    return values,ack


def test_reference_binds_actual_original_hair_owner_not_body_or_colour_consent(monkeypatch):
    engine,state,target,_=fixture(monkeypatch);reference=H.reference(engine,state,target,{})
    assert 'bodies' not in reference and reference['family']=='hair_smoothing'
    assert all(len(reference[key])==64 for key in ('hair_colour_asset_sha256','ownership_review_key',
        'semantic_evidence_sha256','retained_faces_sha256'))
    assert reference['source_image']==I.full_image(engine.fixture_pixels) and engine._people_support=={}


def test_preview_needs_source_crop_and_does_not_publish(monkeypatch):
    engine,state,target,payload=fixture(monkeypatch);H.reference(engine,state,target,{})
    with pytest.raises(ValueError,match='1:1'):H.preview(engine,state,target,payload)
    assert engine._people_support=={} and not engine.fixture_calls


def test_no_direction_is_honest_preview_not_false_visible_change(monkeypatch):
    engine,state,target,*_,preview=ready(monkeypatch)
    assert preview['diagnostics']['changed_pixels']==0
    assert preview['diagnostics']['no_signal_reason']=='no_admitted_directional_signal'
    assert preview['before']['sha256']==preview['after']['sha256']
    assert preview['runtime_quality_accepted'] is False and engine._people_support=={}


def test_output_crop_must_be_actual_matching_source_rectangle(monkeypatch):
    engine,state,target,*_,preview=ready(monkeypatch)
    with pytest.raises(ValueError,match='same native source/output'):
        H.crop(engine,state,target,{'preview_id':preview['preview_id'],'plane':'after','rect':[21,20,16,16]})


def test_three_full_images_are_insufficient_without_actual_crop_pair(monkeypatch):
    engine,state,target,*_,preview=ready(monkeypatch)
    ack={'preview_id':preview['preview_id'],'reviewed':True,
        **{key+'_sha256':preview[key]['sha256'] for key in ('before','after','support')},
        'inspection':{'rect':[20,20,16,16],'before_sha256':'1'*64,'after_sha256':'2'*64}}
    with pytest.raises(ValueError,match='1:1'):H.confirm(engine,state,target,ack)
    assert engine._people_support=={}


def test_confirm_is_single_use_private_permit_not_new_history_owner(monkeypatch):
    values,ack=inspected(monkeypatch);engine,state,target,*_=values
    marks=[];candidate,result=H.confirm(engine,state,target,ack,mark_started=lambda:marks.append(True))
    assert marks==[True] and result['attached'] is True and result['amount']==.4
    assert candidate!=state and len(engine._people_support)==1
    with H.reviewed_transition(engine,state,candidate):
        assert H.require_transition(engine,state,candidate)==candidate
        H.verify_before_publish(engine,state,candidate)
    with pytest.raises(ValueError):
        with H.reviewed_transition(engine,state,candidate):pass
    with pytest.raises(ValueError):H.confirm(engine,state,target,ack)


@pytest.mark.parametrize('key',['before_sha256','after_sha256','support_sha256'])
def test_each_full_image_hash_is_exact_before_append(monkeypatch,key):
    values,ack=inspected(monkeypatch);engine,state,target,*_=values;ack[key]='0'*64
    with pytest.raises(ValueError):H.confirm(engine,state,target,ack)
    assert engine._people_support=={}


def test_rerendered_crop_pixels_cannot_change_under_old_comparison(monkeypatch):
    engine,state,target,*_,preview=ready(monkeypatch);engine.fixture_delta=.01
    with pytest.raises(ValueError,match='differ'):
        H.crop(engine,state,target,{'preview_id':preview['preview_id'],'plane':'after','rect':[20,20,16,16]})


def test_full_render_requires_source_and_output_dimensions_not_size_only(monkeypatch):
    engine,state,target,payload=fixture(monkeypatch);reference=H.reference(engine,state,target,{})
    H.crop(engine,state,target,{'reference_id':reference['reference_id'],'plane':'source','rect':[20,20,16,16]})
    monkeypatch.setattr(F,'render',lambda *args,**kwargs:(np.zeros((64,64,3),np.float32),
        {'source_size':[128,128],'output_size':[64,64],'source_proof':reference['source_proof'],'hair_smoothing_measurements':[]}))
    with pytest.raises(ValueError,match='output/source'):H.preview(engine,state,target,payload)


def test_foreign_operation_ack_and_source_override_are_rejected():
    _,_,ref,*_=support_fixture();target={'scope':'face','target_id':ref['face_instance_id'],'face_ref':ref}
    with pytest.raises(ValueError):A.check_action('neck_wrinkle_confirm',{},target)
    with pytest.raises(ValueError):A.check_action('hair_smoothing_reference',{'source':'anything'},target)
