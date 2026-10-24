"""UNRUN source fixtures for optional face-skin observation transport.

Authored only. These synthetic arrays test data contracts, not model accuracy,
portrait quality, anatomical coverage, native execution or product acceptance.
No product imports, tests, inference or builds were executed during authoring.
"""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest
from lumaretouch_engine import people_binding as B
from lumaretouch_engine import people_state as S
from lumaretouch_engine import people_snapshot as SNAP
from lumaretouch_engine import people_retained_analysis as RA
from lumaretouch_engine.people_render_runtime import verify_analysis
from lumaretouch_engine import skin_colour_support as SUPPORT


def fixture(*, derived=False, face_skin=True):
    # Deliberately synthetic transport-only coordinates, never an inference claim.
    lm=np.full((478,3),.5,np.float32)
    lm[0,:2]=[.2,.2];lm[1,:2]=[.8,.8]
    masks={'skin':np.full((2,3),.9,np.float32),
           'hair':np.zeros((2,3),np.float32),'clothes':np.zeros((2,3),np.float32),
           'background':np.zeros((2,3),np.float32)}
    if face_skin:masks['face_skin']=np.array([[0.,.3,.8],[.2,.6,1.]],np.float32)
    proof=None if not derived else {'sha256':'a'*64,'width':6,'height':4,
        'proxy_width':3,'proxy_height':2,'proxy_sha256':'d'*64}
    pc=SimpleNamespace(backend='mediapipe',semantic_model_sha256='b'*64,
        detector_model_sha256='c'*64,landmarks=lm,all_landmarks=[lm],masks=masks,
        input_source_binding=proof,detection_limit=32,detection_limit_reached=False)
    state,rows,refusals=B.bind(S.empty(),'a'*64,pc,source_dimensions=(6,4),initialize=True)
    assert not refusals
    key=next(iter(rows))
    return pc,state,key,rows


def test_only_actual_named_face_skin_is_copied_readonly():
    pc,_,key,rows=fixture()
    row=rows[key]
    np.testing.assert_array_equal(row['face_skin'],pc.masks['face_skin'])
    assert not np.array_equal(row['face_skin'],pc.masks['skin'])
    assert not row['face_skin'].flags.writeable
    assert not np.shares_memory(row['face_skin'],pc.masks['face_skin'])
    before=row['face_skin'].copy();pc.masks['face_skin'][:]=0
    np.testing.assert_array_equal(row['face_skin'],before)


def test_merged_skin_is_never_a_missing_face_skin_fallback():
    pc,state,key,rows=fixture(face_skin=False)
    assert SUPPORT.face_skin_support(pc) is None
    assert rows[key]['face_skin'] is None and rows[key]['face_skin_observation'] is None
    verify_analysis(state['faces'][key],rows[key],(2,3))


@pytest.mark.parametrize('bad',[np.array([[np.nan]],np.float32),np.array([[-.1]],np.float32),
    np.array([[1.1]],np.float32),np.zeros((1,1,1),np.float32),np.zeros((0,1),np.float32)])
def test_invalid_actual_class_is_not_replaced_or_clamped(bad):
    pc,_,_,_=fixture();pc.masks['face_skin']=bad
    with pytest.raises(ValueError):SUPPORT.face_skin_support(pc)


def test_missing_backend_or_loaded_model_evidence_stays_missing():
    pc,_,_,_=fixture();pc.backend='template'
    assert SUPPORT.face_skin_support(pc) is None
    pc.backend='mediapipe';pc.semantic_model_sha256=None
    assert SUPPORT.face_skin_support(pc) is None
    pc.semantic_model_sha256='b'*64;pc.detector_model_sha256=None
    assert SUPPORT.face_skin_support(pc) is None
    assert SUPPORT.analysis_fields(pc,'a'*64,(6,4)) == {'face_skin':None,'face_skin_observation':None}


def test_missing_detector_evidence_preserves_neutral_unresolved_snapshot():
    pc,_,_,_=fixture();pc.detector_model_sha256=None
    state,rows,refusals=B.bind(S.empty(),'a'*64,pc,source_dimensions=(6,4),initialize=True)
    assert not refusals
    key=next(iter(rows));row=rows[key]
    assert row['evidence']['status']=='unresolved'
    assert row['face_skin'] is None and row['face_skin_observation'] is None
    snap=SNAP.capture(state,'a'*64,rows)
    assert snap['analyses'][key]['face_skin'] is None
    # Existing unresolved evidence still refuses active measured-face consumers.
    with pytest.raises(ValueError,match='Real face analysis required'):
        verify_analysis(state['faces'][key],row,(2,3))


def test_legacy_analysis_has_no_new_required_fields_or_durable_schema_change():
    _,state,key,rows=fixture()
    row={k:v for k,v in rows[key].items() if k not in SUPPORT.FIELDS}
    verify_analysis(state['faces'][key],row,(2,3))
    snap=SNAP.capture(state,'a'*64,{key:row})
    assert not SUPPORT.FIELDS.intersection(snap['analyses'][key])
    store=RA.retain({},rows)
    assert set(next(iter(store.values())))=={'face_ref','evidence','landmarks'}
    assert RA.check_store(store)==store


@pytest.mark.parametrize('field,value',[('source_sha256','f'*64),('semantic_model_sha256','e'*64),
    ('producer_width',0),('producer_height',True),('contract','merged-skin')])
def test_source_model_and_observation_fences_reject_mismatch(field,value):
    _,state,key,rows=fixture();row=deepcopy(rows[key])
    row['face_skin_observation'][field]=value
    with pytest.raises(ValueError):verify_analysis(state['faces'][key],row,(2,3))


def test_unpaired_or_wrong_render_grid_support_is_refused():
    _,state,key,rows=fixture();row=deepcopy(rows[key])
    row.pop('face_skin_observation')
    with pytest.raises(ValueError):verify_analysis(state['faces'][key],row,(2,3))
    with pytest.raises(ValueError):verify_analysis(state['faces'][key],rows[key],(4,6))


def test_derived_observation_uses_its_effective_source_and_exact_input_grid():
    pc,state,key,rows=fixture(derived=True)
    verify_analysis(state['faces'][key],rows[key],(2,3))
    assert rows[key]['face_skin_observation']['source_sha256']=='a'*64
    pc.input_source_binding['sha256']='f'*64
    with pytest.raises(ValueError):SUPPORT.analysis_fields(pc,'a'*64,(6,4))
    pc.input_source_binding['sha256']='a'*64;pc.input_source_binding['proxy_width']=6
    with pytest.raises(ValueError):SUPPORT.analysis_fields(pc,'a'*64,(6,4))


def test_snapshot_owns_support_and_resampling_preserves_observation_extent():
    _,state,key,rows=fixture()
    snap=SNAP.capture(state,'a'*64,rows);captured=snap['analyses'][key]
    assert not np.shares_memory(captured['face_skin'],rows[key]['face_skin'])
    assert captured['face_skin_observation'] is not rows[key]['face_skin_observation']
    # Stub only the interpolation dependency, not the snapshot/ownership logic.
    cv2=SimpleNamespace(INTER_LINEAR=1,resize=lambda value,size,interpolation:
        np.repeat(np.repeat(value,2,axis=0),2,axis=1))
    with patch.dict('sys.modules',{'cv2':cv2}):
        _,_,full=SNAP.at_dimensions(snap,(4,6))
    row=full[key]
    assert row['face_skin'].shape==(4,6) and not row['face_skin'].flags.writeable
    assert row['face_skin_observation']==captured['face_skin_observation']
    assert (row['face_skin_observation']['producer_width'],row['face_skin_observation']['producer_height'])==(3,2)
    np.testing.assert_array_equal(row['landmarks'],captured['landmarks'])
    assert captured['face_skin'].shape==(2,3)


def test_retained_landmarks_restore_only_current_matching_semantic_model():
    pc,state,key,rows=fixture(derived=True);store=RA.retain({},rows)
    restored=RA.restore_missing(state,store,'a'*64,pc,{})
    verify_analysis(state['faces'][key],restored[key],(2,3))
    np.testing.assert_array_equal(restored[key]['face_skin'],pc.masks['face_skin'])
    assert not np.shares_memory(restored[key]['face_skin'],pc.masks['face_skin'])
    pc.semantic_model_sha256='e'*64
    assert RA.restore_missing(state,store,'a'*64,pc,{})=={}


def test_export_semantic_budget_refuses_before_resize_or_target_copy():
    _,state,key,rows=fixture()
    snap=SNAP.capture(state,'a'*64,rows)
    cv2=SimpleNamespace(INTER_LINEAR=1,resize=lambda *args,**kwargs:
        (_ for _ in ()).throw(AssertionError('Resize must not start before admission')))
    with patch.dict('sys.modules',{'cv2':cv2}), patch.object(SNAP.np,'array',
            side_effect=AssertionError('Target copy must not start before admission')):
        with pytest.raises(ValueError,match='memory budget before allocation'):
            SNAP.at_dimensions(snap,(4,6),byte_budget=1)
    assert snap['analyses'][key]['face_skin'].shape==(2,3)


def test_export_admission_counts_all_planes_and_preserves_legacy_callers():
    _,state,key,rows=fixture()
    snap=SNAP.capture(state,'a'*64,rows)
    # 3 semantic planes * 6 pixels * 4 bytes, plus one same-grid 24-byte scratch.
    with pytest.raises(ValueError,match='memory budget before allocation'):
        SNAP.at_dimensions(snap,(2,3),byte_budget=95)
    _,_,admitted=SNAP.at_dimensions(snap,(2,3),byte_budget=96)
    _,_,legacy=SNAP.at_dimensions(snap,(2,3))
    np.testing.assert_array_equal(admitted[key]['face_skin'],legacy[key]['face_skin'])


def test_actual_export_passes_remaining_budget_before_pixel_normalization():
    _,state,_,rows=fixture()
    snap=SNAP.capture(state,'a'*64,rows);snap['document_id']='doc-a'
    source=np.zeros((4,6,3),np.uint8)
    from lumaretouch_engine.people_engine_runtime import prepare_export
    with patch.object(SNAP,'at_dimensions',side_effect=ValueError('admission sentinel')) as dimensions:
        with pytest.raises(ValueError,match='admission sentinel'):
            prepare_export(snap,source,None,byte_budget=4096,document_id='doc-a')
    assert dimensions.call_args.kwargs['byte_budget']==4096-source.nbytes-4*6*36
