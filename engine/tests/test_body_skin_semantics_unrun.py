"""AUTHORED / UNRUN contract fixtures for optional actual body-skin transport.

Synthetic arrays below test transport and refusal contracts, not model quality,
body/person ownership, native processing or photographic/product acceptance.
No product imports, tests, inference or builds were executed during authoring.
"""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest
from lumaretouch_engine import body_skin_semantics as SUPPORT
from lumaretouch_engine import people_binding as B
from lumaretouch_engine import people_state as S
from lumaretouch_engine import people_snapshot as SNAP
from lumaretouch_engine import people_retained_analysis as RA
from lumaretouch_engine.people_render_runtime import verify_analysis


def fixture(*, derived=False, body_skin=True, face_skin=True):
    # Transport-only values labelled as test evidence, never model measurements.
    lm=np.full((478,3),.5,np.float32)
    lm[0,:2]=[.2,.2];lm[1,:2]=[.8,.8]
    masks={'skin':np.full((2,3),.9,np.float32),
           'hair':np.zeros((2,3),np.float32),'clothes':np.zeros((2,3),np.float32),
           'background':np.zeros((2,3),np.float32)}
    if face_skin:masks['face_skin']=np.full((2,3),.7,np.float32)
    if body_skin:masks['body_skin']=np.array([[0.,.3,.8],[.2,.6,1.]],np.float32)
    proof=None if not derived else {'sha256':'a'*64,'width':6,'height':4,
        'proxy_width':3,'proxy_height':2,'proxy_sha256':'d'*64}
    pc=SimpleNamespace(backend='mediapipe',semantic_model_sha256='b'*64,
        detector_model_sha256='c'*64,landmarks=lm,all_landmarks=[lm],masks=masks,
        input_source_binding=proof,detection_limit=32,detection_limit_reached=False)
    state,rows,refusals=B.bind(S.empty(),'a'*64,pc,source_dimensions=(6,4),initialize=True)
    assert not refusals
    key=next(iter(rows))
    return pc,state,key,rows


def test_only_named_body_skin_is_copied_readonly_without_ownership():
    pc,state,key,rows=fixture();row=rows[key]
    np.testing.assert_array_equal(row['body_skin'],pc.masks['body_skin'])
    assert not np.array_equal(row['body_skin'],pc.masks['skin'])
    assert not np.array_equal(row['body_skin'],pc.masks['face_skin'])
    assert not row['body_skin'].flags.writeable
    assert not np.shares_memory(row['body_skin'],pc.masks['body_skin'])
    before=row['body_skin'].copy();pc.masks['body_skin'][:]=0
    np.testing.assert_array_equal(row['body_skin'],before)
    assert state['persons']=={} and state['links']==[] and state['association_revision']==0
    assert 'body_ref' not in row and 'person_id' not in row
    assert row['body_skin_observation']=={
        'contract':SUPPORT.CONTRACT,'source_sha256':'a'*64,
        'semantic_model_sha256':'b'*64,'detector_model_sha256':'c'*64,
        'producer_width':3,'producer_height':2}


def test_missing_body_skin_never_uses_merged_face_or_instance_support():
    pc,state,key,rows=fixture(body_skin=False)
    pc.masks['person']=np.ones((2,3),np.float32)
    assert SUPPORT.body_skin_support(pc) is None
    assert rows[key]['body_skin'] is None and rows[key]['body_skin_observation'] is None
    verify_analysis(state['faces'][key],rows[key],(2,3))


def test_empty_actual_body_skin_is_observed_not_replaced_by_other_classes():
    pc,_,_,_=fixture();pc.masks['body_skin'][:]=0
    fields=SUPPORT.analysis_fields(pc,'a'*64,(6,4))
    assert not np.any(fields['body_skin']) and fields['body_skin_observation'] is not None


@pytest.mark.parametrize('bad',[np.array([[np.nan]],np.float32),np.array([[np.inf]],np.float32),
    np.array([[-.1]],np.float32),np.array([[1.1]],np.float32),
    np.zeros((1,1,1),np.float32),np.zeros((0,1),np.float32)])
def test_invalid_actual_class_is_not_replaced_or_clamped(bad):
    pc,_,_,_=fixture();pc.masks['body_skin']=bad
    with pytest.raises(ValueError):SUPPORT.body_skin_support(pc)


@pytest.mark.parametrize('field,value',[('backend','template'),('semantic_model_sha256',None),
    ('semantic_model_sha256','b'*63),('detector_model_sha256',None),('detector_model_sha256','C'*64)])
def test_missing_actual_model_evidence_remains_missing(field,value):
    pc,_,_,_=fixture();setattr(pc,field,value)
    assert SUPPORT.body_skin_support(pc) is None
    assert SUPPORT.analysis_fields(pc,'a'*64,(6,4))=={'body_skin':None,'body_skin_observation':None}


def test_unresolved_evidence_preserves_a_neutral_snapshot_not_active_support():
    pc,_,_,_=fixture();pc.detector_model_sha256=None
    state,rows,refusals=B.bind(S.empty(),'a'*64,pc,source_dimensions=(6,4),initialize=True)
    assert not refusals
    key=next(iter(rows));row=rows[key]
    assert row['evidence']['status']=='unresolved'
    assert row['body_skin'] is None and row['body_skin_observation'] is None
    snap=SNAP.capture(state,'a'*64,rows)
    assert snap['analyses'][key]['body_skin'] is None
    with pytest.raises(ValueError,match='Real face analysis required'):
        verify_analysis(state['faces'][key],row,(2,3))


def test_old_rows_without_either_optional_pair_and_store_schema_remain_valid():
    _,state,key,rows=fixture()
    row={k:v for k,v in rows[key].items() if k not in SUPPORT.FIELDS and
         k not in ('face_skin','face_skin_observation')}
    verify_analysis(state['faces'][key],row,(2,3))
    snap=SNAP.capture(state,'a'*64,{key:row})
    assert not SUPPORT.FIELDS.intersection(snap['analyses'][key])
    _,_,full=SNAP.at_dimensions(snap,(2,3))
    assert not SUPPORT.FIELDS.intersection(full[key])
    store=RA.retain({},rows)
    assert set(next(iter(store.values())))=={'face_ref','evidence','landmarks'}
    assert RA.check_store(store)==store


@pytest.mark.parametrize('field,value',[('source_sha256','f'*64),('semantic_model_sha256','e'*64),
    ('detector_model_sha256','e'*64),('producer_width',0),('producer_height',True),
    ('producer_width',1000001),('contract','merged-skin')])
def test_source_models_and_producer_observation_fences_reject_mismatch(field,value):
    _,state,key,rows=fixture();row=deepcopy(rows[key])
    row['body_skin_observation'][field]=value
    with pytest.raises(ValueError):verify_analysis(state['faces'][key],row,(2,3))


@pytest.mark.parametrize('missing',['body_skin','body_skin_observation'])
def test_unpaired_fields_are_refused_before_snapshot_copy(missing):
    _,state,key,rows=fixture();row=deepcopy(rows[key]);row.pop(missing)
    with pytest.raises(ValueError):verify_analysis(state['faces'][key],row,(2,3))
    with pytest.raises(ValueError):SNAP.capture(state,'a'*64,{key:row})


def test_none_support_cannot_claim_observation_or_wrong_grid():
    _,state,key,rows=fixture();row=deepcopy(rows[key]);row['body_skin']=None
    with pytest.raises(ValueError):verify_analysis(state['faces'][key],row,(2,3))
    with pytest.raises(ValueError):SUPPORT.check_analysis_fields(rows[key],(4,6))
    row=deepcopy(rows[key]);row['body_skin']=row['body_skin'].astype(np.float64)
    with pytest.raises(ValueError):SUPPORT.check_analysis_fields(row)


@pytest.mark.parametrize('field,value',[('sha256','f'*64),('width',7),('height',5),
    ('proxy_width',6),('proxy_height',4)])
def test_derived_source_and_exact_producer_grid_cannot_be_relabelled(field,value):
    pc,state,key,rows=fixture(derived=True)
    verify_analysis(state['faces'][key],rows[key],(2,3))
    pc.input_source_binding[field]=value
    with pytest.raises(ValueError):SUPPORT.analysis_fields(pc,'a'*64,(6,4))


def test_snapshot_owns_body_support_and_resampling_keeps_original_provenance():
    pc,state,key,rows=fixture(derived=True)
    snap=SNAP.capture(state,'a'*64,rows);captured=snap['analyses'][key]
    assert not np.shares_memory(captured['body_skin'],rows[key]['body_skin'])
    assert captured['body_skin_observation'] is not rows[key]['body_skin_observation']
    assert not captured['body_skin'].flags.writeable
    # Stub interpolation, not snapshot copying, field admission or verification.
    cv2=SimpleNamespace(INTER_LINEAR=1,resize=lambda value,size,interpolation:
        np.repeat(np.repeat(value,2,axis=0),2,axis=1))
    with patch.dict('sys.modules',{'cv2':cv2}):
        _,_,full=SNAP.at_dimensions(snap,(4,6))
    row=full[key]
    assert row['body_skin'].shape==(4,6) and not row['body_skin'].flags.writeable
    assert row['body_skin_observation']==captured['body_skin_observation']
    assert row['body_skin_observation'] is not captured['body_skin_observation']
    assert (row['body_skin_observation']['producer_width'],row['body_skin_observation']['producer_height'])==(3,2)
    np.testing.assert_array_equal(row['landmarks'],captured['landmarks'])
    assert captured['body_skin'].shape==(2,3) and pc.masks['body_skin'].shape==(2,3)
    copied=SUPPORT.check_analysis_fields(row,(4,6));copied['producer_width']=100
    assert row['body_skin_observation']['producer_width']==3


@pytest.mark.parametrize('field',['semantic_model_sha256','detector_model_sha256'])
def test_retained_landmarks_restore_body_skin_only_for_both_matching_models(field):
    pc,state,key,rows=fixture(derived=True);store=RA.retain({},rows)
    restored=RA.restore_missing(state,store,'a'*64,pc,{})
    verify_analysis(state['faces'][key],restored[key],(2,3))
    np.testing.assert_array_equal(restored[key]['body_skin'],pc.masks['body_skin'])
    assert not np.shares_memory(restored[key]['body_skin'],pc.masks['body_skin'])
    assert restored[key]['body_skin_observation']==rows[key]['body_skin_observation']
    setattr(pc,field,'e'*64)
    assert RA.restore_missing(state,store,'a'*64,pc,{})=={}


def test_restore_refuses_body_semantics_bound_to_another_derived_source():
    pc,state,_,rows=fixture(derived=True);store=RA.retain({},rows)
    pc.input_source_binding['sha256']='e'*64
    with pytest.raises(ValueError):RA.restore_missing(state,store,'a'*64,pc,{})


def test_export_body_plane_budget_refuses_before_any_resize_or_target_copy():
    _,state,key,rows=fixture();snap=SNAP.capture(state,'a'*64,rows)
    # Four planes at 24 pixels: 384 retained + 384 interpolation scratch.
    # 767 bytes would admit the old three planes, but not the actual fourth.
    cv2=SimpleNamespace(INTER_LINEAR=1,resize=lambda *args,**kwargs:
        (_ for _ in ()).throw(AssertionError('Resize must not start before admission')))
    with patch.dict('sys.modules',{'cv2':cv2}), patch.object(SNAP.np,'array',
            side_effect=AssertionError('Target copy must not start before admission')):
        with pytest.raises(ValueError,match='memory budget before allocation'):
            SNAP.at_dimensions(snap,(4,6),byte_budget=767)
    assert snap['analyses'][key]['body_skin'].shape==(2,3)


def test_same_grid_budget_counts_new_plane_and_missing_support_needs_no_copy():
    _,state,key,rows=fixture();snap=SNAP.capture(state,'a'*64,rows)
    # Four planes * six pixels * four bytes plus one 24-byte same-grid scratch.
    with pytest.raises(ValueError,match='memory budget before allocation'):
        SNAP.at_dimensions(snap,(2,3),byte_budget=119)
    _,_,admitted=SNAP.at_dimensions(snap,(2,3),byte_budget=120)
    np.testing.assert_array_equal(admitted[key]['body_skin'],snap['analyses'][key]['body_skin'])
    _,state,key,rows=fixture(body_skin=False);snap=SNAP.capture(state,'a'*64,rows)
    _,_,missing=SNAP.at_dimensions(snap,(2,3),byte_budget=96)
    assert missing[key]['body_skin'] is None


def test_body_transport_is_independent_of_optional_face_skin_class():
    _,state,key,rows=fixture(face_skin=False)
    assert rows[key]['face_skin'] is None and rows[key]['body_skin'] is not None
    verify_analysis(state['faces'][key],rows[key],(2,3))
    snap=SNAP.capture(state,'a'*64,rows)
    _,_,full=SNAP.at_dimensions(snap,(2,3),byte_budget=96)
    assert full[key]['face_skin'] is None and full[key]['body_skin'] is not None


def test_shared_photo_plane_never_associates_faces_and_snapshot_counts_every_copy():
    pc,_,_,_=fixture()
    other=pc.landmarks.copy();other[2,0]=.6
    pc.all_landmarks=[pc.landmarks,other]
    state,rows,refusals=B.bind(S.empty(),'a'*64,pc,source_dimensions=(6,4),initialize=True)
    assert not refusals and len(rows)==2
    first,second=rows.values()
    assert first['body_skin'] is second['body_skin']
    assert first['body_skin_observation'] is not second['body_skin_observation']
    assert state['persons']=={} and state['links']==[]
    snap=SNAP.capture(state,'a'*64,rows)
    one,two=snap['analyses'].values()
    assert not np.shares_memory(one['body_skin'],two['body_skin'])
    # Each retained face gets an owned export copy of all four planes. Shared
    # producer memory is not grounds for silently deduplicating planned copies.
    with pytest.raises(ValueError,match='memory budget before allocation'):
        SNAP.at_dimensions(snap,(2,3),byte_budget=215)
    _,_,full=SNAP.at_dimensions(snap,(2,3),byte_budget=216)
    assert len(full)==2


def test_region_reanalysis_carries_actual_class_and_rejects_changed_detector():
    from lumaretouch_engine import face as F, people_host_commands as C
    pc,state,key,rows=fixture()
    backend=SimpleNamespace(detector_model_sha256='c'*64,semantic_model_sha256='b'*64)
    engine=SimpleNamespace(_precompute=pc,_people_landmarks=RA.retain({},rows),
        _people_analyses={'a'*64:rows},_src_rgb=np.zeros((2,3,3),np.uint8),
        _people_source=lambda:{'sha256':'a'*64,'width':6,'height':4})
    with patch.object(F,'MediaPipeFace') as factory, patch.object(F,'detect_region',return_value=(pc.landmarks,None)):
        factory.return_value.__enter__.return_value=backend
        updated,ref=C.analyse(engine,state,S.face_ref(state['faces'][key]))
        row=engine._people_analyses['a'*64][key]
        verify_analysis(updated['faces'][key],row,(2,3))
        assert ref['analysis_revision']==1
        np.testing.assert_array_equal(row['body_skin'],pc.masks['body_skin'])
        old_store=deepcopy(engine._people_landmarks)
        backend.detector_model_sha256='e'*64
        with pytest.raises(ValueError,match='Body-skin observation source/models'):
            C.analyse(engine,updated,ref)
        assert engine._people_landmarks==old_store
        assert engine._people_analyses['a'*64][key] is row
