"""AUTHORED / UNRUN: derived portrait ownership and dispatch contracts.

Fake model identities/landmarks below are contract fixtures, not real inference
or photographic/numerical acceptance. No product imports or tests were executed
while authoring this file. Real MediaPipe + native effect QA remains external.
"""
from copy import deepcopy
from types import SimpleNamespace
import hashlib
import numpy as np
import pytest
from lumaretouch_engine import creative_derived_effects as C, creative_derived_source as D
from lumaretouch_engine import people_state as S, people_algorithms as A, body_pose_state as BODY
from lumaretouch_engine.creative_document_assets import make_asset


def fixture(monkeypatch):
    rgba=np.zeros((4,4,4),dtype='<f4');rgba[...,3]=1
    base=make_asset('rgba',4,4,rgba.tobytes(),original=b'original is provenance only')
    owned=D.binding({'_creative_base':base})
    points=np.zeros((478,3),dtype='<f4')
    evidence={'backend':'mediapipe','status':'verified','detector_model_sha256':'1'*64,
        'semantic_model_sha256':'2'*64,'landmark_digest':hashlib.sha256(points.tobytes()).hexdigest(),
        'source_width':4,'source_height':4,'orientation':'exif_normalized_once'}
    face=S.new_face(owned['sha256'],[.1,.1,.9,.9],evidence)
    state=S.empty();state['faces'][face['face_instance_id']]=face
    ref=S.face_ref(face);target={'scope':'face','target_id':ref['face_instance_id'],'face_ref':ref}
    context={'document_id':'doc','document_epoch':'epoch','document_revision':0,
        'state_revision':0,'association_revision':0,'target':target}
    rgb=np.full((4,4,3),128,np.uint8);rgb.setflags(write=False)
    pc=SimpleNamespace(backend='mediapipe',landmarks=points,masks={'skin':np.ones((4,4),np.float32)})
    engine=SimpleNamespace(_creative_base=base,_docs=[{'state':{'_creative_base':base}}],
        _people_support={},_precompute=pc,_load_id='load',_people_targets={owned['sha256']:target},
        _people_owner=lambda:SimpleNamespace(snapshot=lambda:deepcopy(state)),
        _people_binding=lambda:{'document_id':'doc','document_epoch':'epoch','document_revision':0,'asset_sha256':owned['sha256']},
        _people_managed=lambda:True,_people_source=lambda:owned,
        _body_bank=BODY.empty)
    monkeypatch.setattr(D,'analysis_rgb',lambda _:rgb)
    D.stamp_precompute(engine,pc,rgb)
    return engine,state,context,owned,rgb


def patch(context,operation='lnx.enhance.v1',path='/sclera',value=.3):
    return {**deepcopy(context),'cmd':'people','request_id':'request','action':'patch',
        'payload':{'patches':[{'operation_id':operation,'parameter_path':path,'value':value,'unset':False}]}}


@pytest.mark.parametrize('operation,path,value',[
    ('lnx.deform.v1','/slim_face',.2),('lnx.enhance.v1','/sclera',.2),
    ('lnx.facial_wrinkles.v1','/wrinkle_forehead',.2),('lnx.brow_shape.v1','/arch/left',.2),
    ('lnx.nose_shape.v1','/size',.2),('lnx.eye_shape.v1','/width/right',.2),
    ('lnx.mouth_shape.v1','/upper',.2),('lnx.lip_makeup.v1','/brightness',.2),
])
def test_guard_admits_only_audited_owned_operation_leaves(monkeypatch,operation,path,value):
    from lumaretouch_engine.creative_document_host import guard_command
    engine,state,context,owned,_=fixture(monkeypatch)
    command=patch(context,operation,path,value)
    assert C.is_local_command('people',command)
    guard_command(engine,'people',command)
    assert engine._people_owner().snapshot()==state


def test_registry_neutral_deform_is_complete_not_invalid_empty_input():
    assert A.specifications()[A.DEFORM][0]==dict.fromkeys(A.D.KINDS,0.)
    assert set(A.defaults()[A.DEFORM])=={'/'+key for key in A.D.KINDS}


@pytest.mark.parametrize('action',['select','target','analyse_face','manual_add','face_status'])
def test_local_cursor_and_manual_region_need_complete_envelopes(monkeypatch,action):
    from lumaretouch_engine.creative_document_host import guard_command
    engine,_,context,_,_=fixture(monkeypatch)
    payload={'box':[.2,.2,.8,.8]} if action=='manual_add' else {'enabled':False} if action=='face_status' else {}
    command={**context,'cmd':'people','request_id':'request','action':action,'payload':payload}
    guard_command(engine,'people',command)
    with pytest.raises(ValueError):guard_command(engine,'people',{'action':action,'target':{'scope':'face'}})


@pytest.mark.parametrize('name',['deform','enhance','brow_shape','nose_shape','eye_shape','mouth_shape','lip_makeup'])
def test_legacy_routes_require_owned_local_target_and_complete_recipe(monkeypatch,name):
    from lumaretouch_engine.creative_document_host import guard_command
    engine,_,context,_,_=fixture(monkeypatch)
    command={'cmd':name,'people_context':context}
    if name=='deform':command.update(action='set',amounts={'slim_face':.2})
    elif name=='enhance':command.update(action='set',sclera=.2)
    else:
        recipe=A.specifications()[C.LEGACY[name]][0]
        command.update(recipe=deepcopy(recipe),document_id='load',control='all')
        if name!='lip_makeup':command.update(base=deepcopy(recipe),request_id='request',gesture_id='gesture',face_id='face')
    guard_command(engine,name,command)
    invalid=deepcopy(command);invalid.pop('people_context')
    with pytest.raises(ValueError):guard_command(engine,name,invalid)
    invalid=deepcopy(command);invalid['people_context']['target']={'scope':'person','target_id':'someone','face_ref':None}
    with pytest.raises(ValueError):guard_command(engine,name,invalid)


@pytest.mark.parametrize('change',[
    lambda p:p['payload']['patches'][0].update(operation_id='lnx.hair_colour.v1'),
    lambda p:p['payload']['patches'][0].update(operation_id='lnx.eye_light.v1'),
    lambda p:p['payload']['patches'][0].update(parameter_path='/source_path',value='/original.jpg'),
    lambda p:p['payload']['patches'][0].update(value=True),
    lambda p:p['payload']['patches'][0].update(value=float('nan')),
    lambda p:p['payload']['patches'][0].update(path='/original.jpg'),
    lambda p:p['payload']['patches'].append(deepcopy(p['payload']['patches'][0])),
    lambda p:p.update(action='hair_reference',payload={}),
    lambda p:p.update(action='link',payload={}),
    lambda p:p.update(target={'scope':'group','target_id':'group','face_ref':None}),
])
def test_unknown_reference_shared_and_malformed_requests_stay_fenced(monkeypatch,change):
    from lumaretouch_engine.creative_document_host import guard_command
    engine,_,context,_,_=fixture(monkeypatch);command=patch(context);change(command)
    assert not C.is_local_command('people',command)
    with pytest.raises(ValueError):guard_command(engine,'people',command)


def test_stale_document_source_and_analysis_are_refused(monkeypatch):
    engine,state,context,owned,_=fixture(monkeypatch)
    command=patch(context);command['document_revision']=1
    with pytest.raises(ValueError,match='Stale'):C.require_command(engine,'people',command)
    command=patch(context);command['target']['face_ref']['asset_sha256']='a'*64
    with pytest.raises(ValueError):C.require_command(engine,'people',command)
    engine._precompute.input_source_binding['sha256']='b'*64
    with pytest.raises(ValueError,match='another composite'):C.require_command(engine,'people',patch(context))


def test_all_people_target_is_exact_current_derived_asset(monkeypatch):
    engine,_,context,owned,_=fixture(monkeypatch)
    context['target']={'scope':'all_people','target_id':owned['sha256'],'face_ref':None}
    C.require_command(engine,'people',patch(context))
    context['target']['target_id']='b'*64
    with pytest.raises(ValueError,match='another effective'):C.require_command(engine,'people',patch(context))


def test_current_graph_rejects_file_assets_shared_links_and_unsupported_intent(monkeypatch):
    _,state,context,owned,_=fixture(monkeypatch);key=context['target']['target_id']
    C.require_graph(state,owned)
    unsupported=S.set_override(state,'face',key,'lnx.unadapted.v1','/strength',.5)
    with pytest.raises(ValueError):C.require_graph(unsupported,owned)
    supported=S.set_override(state,'face',key,'lnx.enhance.v1','/sclera',.5)
    C.require_graph(supported,owned)
    local=deepcopy(state);local['faces'][key]['local_assets']['repair']={
        'owner':context['target']['face_ref'],'kind':'enhance','content_sha256':'3'*64}
    with pytest.raises(ValueError,match='support/recovery'):C.require_graph(local,owned)
    linked=deepcopy(state);linked['persons']['person']={'anonymous':True}
    linked['links']=[{'face_instance_id':key,'person_id':'person','state':'confirmed','confirmation_revision':0}]
    with pytest.raises(ValueError,match='shared'):C.require_graph(linked,owned)
    wrong=deepcopy(state);wrong['faces'][key]['evidence']['source_width']=5
    with pytest.raises(ValueError,match='extent'):C.require_graph(wrong,owned)


def test_original_graph_slice_stays_dormant_not_removed(monkeypatch):
    _,state,context,owned,_=fixture(monkeypatch)
    original=deepcopy(next(iter(state['faces'].values())))
    original['face_instance_id']='original';original['asset_sha256']='c'*64
    state['faces']['original']=original
    state=S.set_override(state,'face','original','lnx.hair_colour.v1','/strength',.7)
    before=deepcopy(state);C.require_graph(state,owned)
    assert state==before and state['overrides'][0]['value']==.7


def test_preview_forwarding_never_resolves_original_hair_or_body(monkeypatch):
    from lumaretouch_engine import people_owned_inputs as I, hair_colour_project as H
    engine,state,_,owned,rgb=fixture(monkeypatch)
    def forbidden(*args,**kwargs):raise AssertionError('Original hair resolver called')
    monkeypatch.setattr(H,'preview_kwargs',forbidden)
    inputs=I.preview(engine,state,body_source=owned)
    assert set(inputs)=={'creative_source','creative_proxy','hair_assets','hair_evidence','body_bank','body_source','body_source_pixels',*(name+'_assets' for name in ('eye_light','lipstick','blush_makeup','eyeliner','eyelash','brow_makeup','iris_makeup'))}
    assert inputs['creative_source']==owned and inputs['creative_proxy'] is rgb
    bad=BODY.empty();bad['analysis_runs']['a'*64]=[]
    with pytest.raises(ValueError):I.preview(engine,state,body_bank=bad)


def test_preview_checks_actual_pipeline_pixels_before_source_only_preparation(monkeypatch):
    import torch
    from lumaretouch_engine import people_engine_runtime as R
    engine,state,_,owned,rgb=fixture(monkeypatch);calls=[]
    pipe=SimpleNamespace(src_f32=torch.from_numpy(rgb.copy()).permute(2,0,1)[None].float()/255.,repair_base=None)
    def prepare(*args,**kwargs):calls.append((args,kwargs));return 'prepared'
    monkeypatch.setattr(R,'prepare',prepare)
    assert R.prepare_preview(pipe,state,owned['sha256'],{},byte_budget=256*1024**2,
        creative_source=owned,creative_proxy=rgb)=='prepared'
    assert calls[0][1]['creative_source']==owned
    np.testing.assert_array_equal(calls[0][0][2],rgb.astype(np.float32)/255.)
    pipe.src_f32=torch.zeros_like(pipe.src_f32)
    with pytest.raises(ValueError,match='pixels differ'):
        R.prepare_preview(pipe,state,owned['sha256'],{},byte_budget=256*1024**2,
            creative_source=owned,creative_proxy=rgb)
    assert len(calls)==1


def test_export_keeps_float_precision_and_never_calls_original_hair_inputs(monkeypatch):
    from lumaretouch_engine import people_engine_runtime as R, hair_colour_project as H
    engine,state,_,owned,_=fixture(monkeypatch);calls=[]
    snapshot={'state':state,'asset_sha256':owned['sha256'],'creative_source':owned,'analyses':{},'support_assets':{}}
    rgb=np.full((4,4,3),np.float32(.500013),np.float32)
    def forbidden(*args,**kwargs):raise AssertionError('Original-path export resolver called')
    def prepare(*args,**kwargs):calls.append((args,kwargs));return 'prepared'
    monkeypatch.setattr(H,'kwargs',forbidden);monkeypatch.setattr(R,'prepare',prepare)
    assert R.prepare_export(snapshot,rgb,None,byte_budget=256*1024**2)=='prepared'
    np.testing.assert_array_equal(calls[0][0][2],rgb)
    assert calls[0][1]['creative_source']==owned and 'hair_source_path' not in calls[0][1]
    with pytest.raises(ValueError):R.prepare_export(snapshot,rgb.astype(np.uint8),None,byte_budget=256*1024**2)
    with pytest.raises(ValueError):R.prepare_export(snapshot,rgb,rgb.copy(),byte_budget=256*1024**2)


def test_mirror_isolated_before_rebound_guard_without_losing_graph(monkeypatch):
    from lumaretouch_engine.people_export import isolated_snapshot
    from lumaretouch_engine.creative_document_base import require_rebound_snapshot
    engine,state,context,owned,_=fixture(monkeypatch)
    state=S.set_override(state,'face',context['target']['target_id'],A.ENHANCE,'/sclera',.4)
    people={'state':state,'asset_sha256':owned['sha256'],'creative_source':owned,'support_assets':{}}
    snapshot={'creative_base':engine._creative_base,'people':people,
        'deform':{'amounts':{'slim_face':.2}},'enhance':{'amounts':{'sclera':.4}},
        'lip_makeup':{**A.specifications()[A.LIP][0],'brightness':.2}}
    before=deepcopy(snapshot)
    with pytest.raises(ValueError):require_rebound_snapshot(snapshot)
    isolated=isolated_snapshot(snapshot,for_document=True)
    require_rebound_snapshot(isolated)
    assert isolated['people']==people and isolated['deform']['amounts']=={} and isolated['enhance']['amounts']=={}
    assert snapshot==before


def test_derived_mirror_tracks_graph_without_installing_legacy_effects(monkeypatch):
    from lumaretouch_engine.people_host import PeopleHostMixin
    engine,state,context,owned,_=fixture(monkeypatch);key=context['target']['target_id']
    state=S.set_override(state,'face',key,A.ENHANCE,'/sclera',.4)
    state=S.set_override(state,'face',key,A.DEFORM,'/slim_face',.15)
    engine._people_owner=lambda:SimpleNamespace(snapshot=lambda:deepcopy(state))
    engine._people_cursors={owned['sha256']:key};engine._people_analyses={owned['sha256']:{}}
    engine._vram=SimpleNamespace(people_prepared=None,people_suspended=None)
    PeopleHostMixin._people_mirror(engine)
    assert engine._enhance['amounts']['sclera']==.4
    assert engine._deform['amounts']['slim_face']==.15
    assert engine._vram.people_prepared is None
    assert not hasattr(engine._vram,'deform_units') and not hasattr(engine._vram,'enhance_gpu')
    assert engine._creative_base['id'][7:]==owned['sha256']


def test_source_only_runtime_does_not_invoke_unadapted_hair_consumer(monkeypatch):
    from lumaretouch_engine import people_render_runtime as R, hair_colour_runtime as H
    _,_,_,owned,_=fixture(monkeypatch)
    def forbidden(*args,**kwargs):raise AssertionError('Unadapted hair consumer ran')
    monkeypatch.setattr(H,'prepare_bank',forbidden)
    prepared=R.prepare(S.empty(),owned['sha256'],np.full((4,4,3),.5,np.float32),{},
        byte_budget=256*1024**2,creative_source=owned)
    assert prepared.effects==() and prepared.body_fields==()
    with pytest.raises(ValueError,match='original-file'):
        R.prepare(S.empty(),owned['sha256'],np.full((4,4,3),.5,np.float32),{},
            byte_budget=256*1024**2,creative_source=owned,hair_source_path='/original.jpg')


def test_source_only_enhancement_consumer_receives_owned_pixels(monkeypatch):
    from lumaretouch_engine import people_effects as E, blush_makeup_layer as B, lipstick_layer as L
    _,state,context,_,_=fixture(monkeypatch)
    recipes={operation:deepcopy(neutral) for operation,(neutral,_) in A.specifications().items()}
    recipes[A.ENHANCE]['sclera']=.4
    rgb=np.full((4,4,3),np.float32(.500013),np.float32);calls=[]
    def forbidden(*args,**kwargs):raise AssertionError('Unadapted makeup consumer ran')
    def field(landmarks,height,width,source):
        assert source is rgb;calls.append(source)
        return (0,0,4,4),np.ones((3,4,4),np.float32),{},{}
    monkeypatch.setattr(B,'prepare_record',forbidden);monkeypatch.setattr(L,'prepare_record',forbidden)
    monkeypatch.setattr(E.H,'build_field',field)
    effects=E.prepare(context['target']['face_ref'],np.zeros((478,3),np.float32),recipes,rgb,
        excluded=None,skin=None,backend='mediapipe',semantic_sha=None,source_only=True)
    assert len(calls)==1 and len(effects)==1 and effects[0].stage=='enhance'
    assert effects[0].amounts['sclera']==.4 and not effects[0].weights.flags.writeable
