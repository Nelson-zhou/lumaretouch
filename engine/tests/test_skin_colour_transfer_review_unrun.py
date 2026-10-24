"""AUTHORED / UNRUN: target coverage disclosure and scalar-only preset fixtures.

Synthetic contracts and mocked resolution/snapshot boundaries are not model,
pixel-quality, native execution, actual full-render or product acceptance.
No product imports or fixture/test execution occurred while authoring.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import json
import numpy as np
import pytest
from lumaretouch_engine import people_state as P, skin_colour_state as S
from lumaretouch_engine import skin_colour_transfer_review as R, skin_colour_scope as C
from lumaretouch_engine import skin_colour_body_support as BODY, skin_colour_support as FACE

ASSET='a'*64
SUPPORT='d'*64


def fixture(*, attached=False, temperature=.2, tint=0.):
    landmarks=np.full((478,3),.5,np.float32)
    evidence={'backend':'mediapipe','detector_model_sha256':'b'*64,'semantic_model_sha256':'c'*64,
        'landmark_digest':sha256(landmarks.tobytes()).hexdigest(),'status':'verified',
        'source_width':640,'source_height':480,'orientation':'exif_normalized_once'}
    face=P.new_face(ASSET,[.1,.2,.6,.8],evidence);face['face_instance_id']='target-face'
    ref=P.face_ref(face);graph=P.empty();graph['faces'][ref['face_instance_id']]=face
    if attached:face['local_assets'][BODY.KIND]={'owner':ref,'kind':BODY.KIND,'content_sha256':SUPPORT}
    graph=P.set_override(graph,'face',ref['face_instance_id'],S.OP,'/temperature',temperature)
    graph=P.set_override(graph,'face',ref['face_instance_id'],S.OP,'/tint',tint)
    analysis={'face_ref':ref,'evidence':evidence,'landmarks':landmarks,
        'skin':np.ones((8,10),np.float32),'excluded':np.zeros((8,10),np.float32),
        'face_skin':np.ones((8,10),np.float32),'face_skin_observation':{
            'contract':FACE.CONTRACT,'source_sha256':ASSET,'semantic_model_sha256':'c'*64,
            'producer_width':10,'producer_height':8}}
    payload={'target_document':{'document_id':'target-document','epoch':'workspace','revision':2},
        'target_refs':[ref],'parameters':[{'operation_id':S.OP,'parameter_path':'/temperature','value':temperature}]}
    recipe={'version':1,'temperature':temperature,'tint':tint}
    return graph,ref,analysis,payload,recipe


def test_absent_descriptor_means_target_face_only_without_copying_source_review(monkeypatch):
    graph,ref,_,_,recipe=fixture()
    monkeypatch.setattr(BODY,'resolve',lambda *a:pytest.fail('Absent body descriptor must not resolve another bank'))
    result=R.describe(graph,{'unrelated-donor-support':object()},ref,None,None,recipe)
    assert result=={'face_ref':ref,'scope':'face-only','body_review_sha256':None}
    assert result['face_ref'] is not ref


def test_attached_target_calls_actual_resolver_with_exact_target_inputs(monkeypatch):
    graph,ref,analysis,_,recipe=fixture(attached=True)
    assets={'target-only':object()};bank={'target-body-bank':object()};calls=[]
    def resolve(*args):
        calls.append(args);return {'fixture':'already resolved, not a support record'},SUPPORT
    monkeypatch.setattr(BODY,'resolve',resolve)
    result=R.describe(graph,assets,ref,bank,analysis,recipe)
    assert result=={'face_ref':ref,'scope':'face-and-reviewed-body','body_review_sha256':SUPPORT}
    assert calls[0][0] is graph and calls[0][1] is assets and calls[0][3] is bank and calls[0][4] is analysis
    assert set(result)=={'face_ref','scope','body_review_sha256'}


@pytest.mark.parametrize('missing',[False,True])
def test_stale_or_omitted_attached_support_never_degrades_to_face_only(monkeypatch,missing):
    graph,ref,analysis,_,recipe=fixture(attached=True)
    def resolve(*_):
        if missing:return None
        raise ValueError('Stale target BodyRef/person/model evidence')
    monkeypatch.setattr(BODY,'resolve',resolve)
    with pytest.raises(ValueError):R.describe(graph,{},ref,{},analysis,recipe)


def test_neutral_reset_claims_no_effect_without_certifying_stale_body(monkeypatch):
    graph,ref,analysis,payload,recipe=fixture(attached=True,temperature=0.)
    monkeypatch.setattr(BODY,'resolve',lambda *a:pytest.fail('Neutral reset must not need stale body evidence'))
    assert R.describe(graph,{},ref,None,analysis,recipe)=={
        'face_ref':ref,'scope':'neutral-no-effect','body_review_sha256':None}
    engine=SimpleNamespace(_people_export_snapshot=lambda *a,**k:pytest.fail('Neutral reset needs no body snapshot'))
    result=R.for_target(engine,{'state':{}},graph,payload)
    assert result['targets'][0]['scope']=='neutral-no-effect'


def test_target_partial_scalar_transfer_keeps_its_other_nonzero_leaf_active():
    graph,ref,_,payload,_=fixture(temperature=0.,tint=.4)
    result=R.for_target(SimpleNamespace(),{'state':{}},graph,payload)
    assert result=={'version':1,'support_transfer':'none','targets':[
        {'face_ref':ref,'scope':'face-only','body_review_sha256':None}]}
    assert payload['parameters']==[{'operation_id':S.OP,'parameter_path':'/temperature','value':0.}]


def target_snapshot(monkeypatch, *, bad=None):
    graph,ref,analysis,payload,_=fixture(attached=True)
    row={'path':'/target-owned.png','state':{'target-state':'not the current live state'}}
    context={'people_support_assets':{'target-bank':'owned'}};bank={'target-body':'owned'};calls=[]
    from lumaretouch_engine import full_candidate_render as FULL, body_pose_project as PROJECT
    monkeypatch.setattr(FULL,'people_context',lambda engine,actual_row:context if actual_row is row else pytest.fail('Wrong target row'))
    monkeypatch.setattr(PROJECT,'bank',lambda state:bank if state is row['state'] else pytest.fail('Wrong target body state'))
    def snapshot(state,path,candidate,*,context,document_id):
        calls.append((state,path,candidate,context,document_id))
        value={'state':candidate,'asset_sha256':ASSET,'document_id':document_id,
            'support_assets':context['people_support_assets'],'analyses':{ref['face_instance_id']:analysis}}
        if bad is not None:value[bad]='not-this-target'
        return value
    def resolve(actual_graph,assets,actual_ref,actual_bank,actual_analysis):
        assert actual_graph==graph and assets is context['people_support_assets']
        assert actual_ref==ref and actual_bank is bank and actual_analysis is analysis
        return {},SUPPORT
    monkeypatch.setattr(BODY,'resolve',resolve)
    engine=SimpleNamespace(_people_export_snapshot=snapshot,
        _body_bank=lambda:pytest.fail('Parked target must never borrow current live body bank'))
    return engine,row,graph,payload,calls


def test_batch_coverage_uses_target_snapshot_and_document_body_bank(monkeypatch):
    engine,row,graph,payload,calls=target_snapshot(monkeypatch)
    before=deepcopy(payload);report=R.for_target(engine,row,graph,payload)
    assert report['targets'][0]['scope']=='face-and-reviewed-body'
    assert report['targets'][0]['body_review_sha256']==SUPPORT and report['support_transfer']=='none'
    assert payload==before and len(calls)==1
    assert calls[0][0] is row['state'] and calls[0][1]=='/target-owned.png'
    assert calls[0][-1]=='target-document'
    assert 'recipe' not in json.dumps(report) and 'landmarks' not in json.dumps(report)


@pytest.mark.parametrize('bad',['state','asset_sha256','document_id'])
def test_batch_disclosure_rejects_another_snapshot_owner(monkeypatch,bad):
    engine,row,graph,payload,_=target_snapshot(monkeypatch,bad=bad)
    with pytest.raises(ValueError,match='differs from the reviewed target'):
        R.for_target(engine,row,graph,payload)


def test_unrelated_parameter_transfer_adds_no_skin_disclosure():
    graph,_,_,payload,_=fixture(attached=True)
    payload['parameters']=[{'operation_id':'lnx.deform.v1','parameter_path':'/face_slim','value':.2}]
    assert R.for_target(None,None,graph,payload) is None


def capture_engine(monkeypatch, *, attached=True, temperature=.2):
    graph,ref,analysis,_,_=fixture(attached=attached,temperature=temperature)
    owner=SimpleNamespace(snapshot=lambda:deepcopy(graph));bank={'live-body':'owned'};assets={'live-support':'owned'}
    from lumaretouch_engine import skin_colour_native as N
    monkeypatch.setattr(N,'available',lambda:True)
    engine=SimpleNamespace(_people_managed=lambda:True,_people_owner=lambda:owner,
        _people_source=lambda:{'sha256':ASSET,'width':640,'height':480},
        _people_cursors={ASSET:ref['face_instance_id']},
        _people_targets={ASSET:{'scope':'face','target_id':ref['face_instance_id'],'face_ref':ref}},
        _people_analyses={ASSET:{ref['face_instance_id']:analysis}},_people_support=assets,
        _body_bank=lambda:bank,_capture_state=lambda:{})
    return engine,bank,assets


def test_scalar_capture_discloses_own_body_extent_without_serializing_it(monkeypatch):
    engine,bank,assets=capture_engine(monkeypatch)
    def resolve(graph,actual_assets,ref,actual_bank,analysis):
        assert actual_assets is assets and actual_bank is bank
        return {},SUPPORT
    monkeypatch.setattr(BODY,'resolve',resolve)
    capture=C.capture(engine)
    assert capture[C.COVERAGE]['scope']=='face-and-reviewed-body'
    assert capture['_skin_colour_supported'] is True
    assert C.params_of(capture)=={'recipe':{'version':1,'temperature':.2,'tint':0.}}
    assert C.FIELDS==(C.FIELD,)
    assert SUPPORT not in json.dumps(C.params_of(capture))
    for name in ('coverage','body_ref','body_skin','body_review_sha256'):
        with pytest.raises(ValueError):C.check_params({**C.params_of(capture),name:capture[C.COVERAGE]})


def test_active_stale_preset_capture_refuses_but_zero_stays_available(monkeypatch):
    engine,_,_=capture_engine(monkeypatch)
    def resolve(*_):raise ValueError('Target body review is stale')
    monkeypatch.setattr(BODY,'resolve',resolve)
    capture=C.capture(engine)
    assert capture[C.COVERAGE] is None and capture['_skin_colour_supported'] is False
    assert 'body review is stale' in capture['_skin_colour_refusal']
    with pytest.raises(ValueError):C.params_of(capture)
    C.install(capture,{'recipe':S.neutral()})
    assert capture[C.FIELD]==S.neutral()


def test_real_batch_hook_follows_actual_renderer_and_does_not_change_commit():
    root=Path(__file__).resolve().parents[2]/'engine/src/lumaretouch_engine'
    text=(root/'people_batch_transfer.py').read_text()
    start=text.index('            validate(engine,row,staged)')
    coverage=text.index('coverage=skin_coverage(engine,row,staged,payload)',start)
    verify=text.index('SOURCE.verify_row(row,target_proof)',coverage)
    assert start<coverage<verify
    assert 'skin_colour_coverage' not in text[text.index('def commit('):]
    # Generic preset replay still demands the canonical strict renderer and
    # retains rollback. Captured scope is not substituted for renderer success.
    replay=(root/'people_scope.py').read_text()
    assert "if SKIN_COLOUR.S.active(skin_recipe):kwargs['strict_local']=True" in replay
    assert "return engine._replay_state(state,**kwargs)" in replay
