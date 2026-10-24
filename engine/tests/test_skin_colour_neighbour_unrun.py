"""UNRUN source fixtures for manual/unresolved neighbour protection.

Authored only, with synthetic ownership records and mocked anatomy/native
solvers. These isolate command routing and conservative box-veto arithmetic;
they do not establish detector accuracy, native execution or portrait quality.
No imports, tests, inference or builds were executed while authoring this file.
"""
from copy import deepcopy
import hashlib
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest
from lumaretouch_engine import people_state as S
from lumaretouch_engine import people_edit as EDIT
from lumaretouch_engine import people_render_runtime as RT
from lumaretouch_engine import skin_colour_people as COLOUR
from lumaretouch_engine import skin_colour_support as SUPPORT
from lumaretouch_engine import skin_colour_state as RECIPE


ASSET='a'*64
BUDGET=512*1024*1024


def fixture():
    h,w=96,128
    lm=np.full((478,3),.5,np.float32)
    lm[0,:2]=[.2,.2];lm[1,:2]=[.8,.8]
    evidence={'backend':'mediapipe','detector_model_sha256':'c'*64,
        'semantic_model_sha256':'b'*64,
        'landmark_digest':hashlib.sha256(np.ascontiguousarray(lm,dtype='<f4').tobytes()).hexdigest(),
        'status':'verified','source_width':w,'source_height':h,
        'orientation':'exif_normalized_once'}
    face=S.new_face(ASSET,[.2,.2,.8,.8],evidence)
    key=face['face_instance_id'];state=S.empty();state['faces'][key]=face
    state=S.set_override(state,'face',key,RECIPE.OP,'/temperature',.2)
    skin=np.ones((h,w),np.float32);skin[:3,:]=0
    pc=SimpleNamespace(backend='mediapipe',detector_model_sha256='c'*64,semantic_model_sha256='b'*64,
        masks={'face_skin':skin},input_source_binding=None)
    row={'face_ref':S.face_ref(face),'evidence':deepcopy(evidence),'landmarks':lm,
         'excluded':np.zeros((h,w),np.float32),'skin':np.ones((h,w),np.float32),
         **SUPPORT.analysis_fields(pc,ASSET,(w,h))}
    source=np.full((h,w,3),.4,np.float32)
    return state,key,row,source


def colour_with_box(row,source,box):
    seen=[]
    def native(rgb,coverage,*controls):
        seen.append(coverage.copy())
        return rgb+coverage[...,None]*np.float32(.01)
    # Isolate the veto. Real geometry is covered separately, not fabricated here.
    with patch('lumaretouch_engine.face_scope.selected_face_skin',
               side_effect=lambda skin,*a,**kw:skin.copy()), \
         patch('lumaretouch_engine.skin_colour_native.apply',side_effect=native):
        records=COLOUR.prepare(row['face_ref'],row,[],source,
            {'version':1,'temperature':.2,'tint':0.},byte_budget=BUDGET,
            protected_boxes=[box])
    record=records[0];y,x,h,w=record.window
    coverage=np.zeros(source.shape[:2],np.float32)
    coverage[y:y+h,x:x+w]=seen[0]
    return record,coverage


@pytest.mark.parametrize('box',[
    [0.,0.,.1,.1],[.99,.01,1.,.99],[.5,.5,.501,.501],[.4,.25,.6,.75]])
def test_veto_protects_intersecting_pixel_footprints_at_edges_and_subpixels(box):
    _,_,row,source=fixture();before=source.copy();skin=row['face_skin'].copy()
    observation=deepcopy(row['face_skin_observation']);landmarks=row['landmarks'].copy()
    record,coverage=colour_with_box(row,source,box)
    h,w=coverage.shape;left,top,right,bottom=np.asarray(box)*[w,h,w,h]
    xs=np.arange(w)[None,:];ys=np.arange(h)[:,None]
    touches=(xs+1>=left)&(xs<=right)&(ys+1>=top)&(ys<=bottom)
    assert np.all(coverage[touches]==0)
    assert np.all((coverage>=0)&(coverage<=skin))
    assert np.any(coverage==1)
    assert record.facts['unresolved_neighbour_box_vetoes']==1
    assert record.facts['other_face_exclusions']==0
    np.testing.assert_array_equal(source,before)
    np.testing.assert_array_equal(row['face_skin'],skin)
    np.testing.assert_array_equal(row['landmarks'],landmarks)
    assert row['face_skin_observation']==observation


@pytest.mark.parametrize('box',[
    [-.1,0.,.5,.5],[0.,0.,1.1,1.],[.4,.2,.4,.8],
    [False,0.,.5,.5],[float('nan'),0.,.5,.5],[0.,0.,.5]])
def test_malformed_box_refuses_without_native_publication(box):
    _,_,row,source=fixture()
    with patch('lumaretouch_engine.face_scope.selected_face_skin',
               side_effect=lambda skin,*a,**kw:skin.copy()), \
         patch('lumaretouch_engine.skin_colour_native.apply') as native:
        with pytest.raises(ValueError,match='retained source-normalized box'):
            COLOUR.prepare(row['face_ref'],row,[],source,
                {'version':1,'temperature':.2,'tint':0.},byte_budget=BUDGET,
                protected_boxes=[box])
        native.assert_not_called()


def test_full_image_veto_refuses_instead_of_replacing_missing_support():
    _,_,row,source=fixture()
    with patch('lumaretouch_engine.face_scope.selected_face_skin',
               side_effect=lambda skin,*a,**kw:skin.copy()), \
         patch('lumaretouch_engine.skin_colour_native.apply') as native:
        with pytest.raises(ValueError,match='insufficient confidently visible'):
            COLOUR.prepare(row['face_ref'],row,[],source,
                {'version':1,'temperature':.2,'tint':0.},byte_budget=BUDGET,
                protected_boxes=[[0.,0.,1.,1.]])
        native.assert_not_called()


@pytest.mark.parametrize('disabled',[False,True])
def test_manual_add_and_disabled_unresolved_neighbour_are_veto_only(disabled):
    state,key,row,source=fixture();before=deepcopy(state)
    box=[.75,.1,.95,.8];h,w=source.shape[:2]
    command={'document_id':'doc-a','document_epoch':'workspace-a','document_revision':0,
        'state_revision':state['revision'],'association_revision':state['association_revision'],
        'target':{'scope':'face','target_id':key,'face_ref':S.face_ref(state['faces'][key])},
        'request_id':'manual-add','action':'manual_add','payload':{'box':box}}
    field=SimpleNamespace(fields=(None,None,None,None),resident_bytes=lambda:0)
    geometry=SimpleNamespace(delta=np.zeros((1,h,w,2),np.float32),owner=np.zeros((h,w),np.int32))
    seen=[]
    def skin_prepare(ref,analysis,others,pixels,recipe,**kwargs):
        assert ref==row['face_ref'] and analysis is row
        assert others==[] # No invented landmark row for the unresolved neighbour.
        assert kwargs['protected_boxes']==[box]
        assert kwargs['byte_budget']<BUDGET
        seen.append(kwargs['protected_boxes'])
        return []
    def prepare(candidate):
        if disabled:
            candidate=deepcopy(candidate)
            for face_id,face in candidate['faces'].items():
                if face_id!=key:face['enabled']=False
        return RT.prepare(candidate,ASSET,source,{key:row},byte_budget=BUDGET,document_id='doc-a')
    with patch.object(RT.A,'build_geometry',return_value=field), \
         patch.object(RT.E,'prepare',return_value=[]), \
         patch.object(RT,'combine',return_value=geometry), \
         patch.object(COLOUR,'prepare',side_effect=skin_prepare), \
         patch('lumaretouch_engine.eye_light_people.prepare',return_value=[]), \
         patch('lumaretouch_engine.hair_colour_runtime.prepare_bank',return_value=((),{})):
        staged=EDIT.stage(command,state,document_id='doc-a',document_epoch='workspace-a',
            document_revision=0,asset_sha256=ASSET,source_dimensions=(w,h),prepare=prepare)
    assert seen==[[box]]
    created=staged['state']['faces'][staged['created_id']]
    assert created['manual'] and created['evidence']['status']=='unresolved'
    assert created['evidence']['landmark_digest'] is None
    assert staged['prepared'] is not None
    assert state==before # Staging did not publish or mutate the original graph.
