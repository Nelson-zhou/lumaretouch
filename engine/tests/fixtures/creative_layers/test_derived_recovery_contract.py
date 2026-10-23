"""AUTHORED / UNRUN: exact face recovery ownership and review admission.

Synthetic evidence and mocked capture/tensor boundaries are contract fixtures,
not product execution, inference, native rendering or visual acceptance.
"""
from copy import deepcopy
from types import SimpleNamespace
import hashlib
import json
import numpy as np
import pytest
from test_derived_effects_contract import fixture
from lumaretouch_engine import creative_derived_recovery as D,people_recovery as P
from lumaretouch_engine import people_support_assets as A,effect_recovery_state as R
from lumaretouch_engine.source_patch_controller import PROOF_KEYS


class Tensor:
    def __init__(self,array):self.array=array;self.shape=array.shape
    def __getitem__(self,key):return Tensor(self.array[key])
    def permute(self,*axes):return Tensor(self.array.transpose(axes))
    def detach(self):return self
    def cpu(self):return self
    def numpy(self):return self.array


def owned(monkeypatch):
    engine,state,context,source,rgb=fixture(monkeypatch)
    engine._people_cursors={source['sha256']:context['target']['target_id']}
    engine._people_owner=lambda:SimpleNamespace(snapshot=lambda:deepcopy(state),fence=(0,0))
    engine._vram=SimpleNamespace(src_f32=Tensor((rgb.astype(np.float32)/255.).transpose(2,0,1)[None]))
    proof=dict(document_id='1',capture_id='1'*32,ticket='1',generation='1',recipe_document_id='doc',recipe_revision='0')
    capture={'descriptor':{**proof,'domain':'source-input','mask_group_id':None},'eligible':True}
    def matching(request,recipe=False):
        keys=PROOF_KEYS if recipe else ('capture_id','ticket','document_id','generation')
        if any(request.get(k)!=proof[k] for k in keys):raise ValueError('stale capture')
        return capture
    owner=SimpleNamespace(capture=capture,_matching=matching)
    engine._source_patch_controller=lambda:SimpleNamespace(capture=owner)
    return engine,state,context,source,proof,capture


def preview(proof,target='lipstick'):
    return {**proof,'cmd':'effect_recovery_preview','action':'preview','preview_id':'2'*32,
        'mutation':{'action':'view','target':target}}


def test_exact_ungrouped_capture_and_actual_pixels(monkeypatch):
    engine,_,_,_,proof,capture=owned(monkeypatch)
    command={k:proof[k] for k in ('capture_id','ticket','document_id')}
    command.update(cmd='source_patch_capture',action='arm',epoch='3'*32,purpose='local-masks',group_id=None)
    D.require_command(engine,'source_patch_capture',command)
    for change in ({'purpose':'repair'},{'group_id':'some-group'}):
        with pytest.raises(ValueError):D.require_command(engine,'source_patch_capture',{**command,**change})
    engine._vram.src_f32=Tensor(np.zeros((1,3,4,4),np.float32))
    with pytest.raises(ValueError,match='pixels differ'):D.require_command(engine,'source_patch_capture',command)


@pytest.mark.parametrize('target',sorted(D.TARGETS))
def test_all_existing_face_targets_use_exact_presented_capture(monkeypatch,target):
    engine,_,_,_,proof,capture=owned(monkeypatch)
    command=preview(proof,target)
    D.require_command(engine,'effect_recovery_preview',command)
    capture['eligible']=False
    with pytest.raises(ValueError):D.require_command(engine,'effect_recovery_preview',command)
    capture['eligible']=True;capture['descriptor']['domain']='repair-input'
    with pytest.raises(ValueError):D.require_command(engine,'effect_recovery_preview',command)


@pytest.mark.parametrize('target',['skin_smoothing','fabric_fine','background_replace','enhance'])
def test_global_and_unimplemented_operators_stay_fenced(monkeypatch,target):
    engine,_,_,_,proof,_=owned(monkeypatch)
    with pytest.raises(ValueError):D.require_command(engine,'effect_recovery_preview',preview(proof,target))


def test_apply_requires_same_face_context_and_presented_committable_review(monkeypatch):
    engine,_,_,_,proof,_=owned(monkeypatch)
    record={'id':'2'*32,'target':'lipstick','proof':proof,'people_context':P.context(engine),
        'presented':False,'committable':True}
    engine._effect_recovery_preview_owner=SimpleNamespace(record=record)
    command={**proof,'cmd':'effect_recovery','action':'apply','preview_id':'2'*32,'request_id':'apply'}
    with pytest.raises(ValueError):D.require_command(engine,'effect_recovery',command)
    record['presented']=True;D.require_command(engine,'effect_recovery',command)
    record['people_context']['graph_fence']=(1,1)
    with pytest.raises(ValueError):D.require_command(engine,'effect_recovery',command)


def test_exact_terminal_receipt_replay_does_not_reopen_capture(monkeypatch):
    engine,_,_,_,proof,_=owned(monkeypatch)
    command={**proof,'cmd':'effect_recovery','action':'apply','preview_id':'2'*32,'request_id':'apply'}
    digest=hashlib.sha256(json.dumps(command,sort_keys=True,allow_nan=False).encode()).hexdigest()
    engine._effect_recovery_owner=SimpleNamespace(cache={'apply':(digest,{'success':True})})
    engine._precompute=None
    D.require_command(engine,'effect_recovery',command)
    with pytest.raises(ValueError):D.require_command(engine,'effect_recovery',{**command,'ticket':'2'})


def retained(monkeypatch):
    engine,state,context,source,_,_=owned(monkeypatch)
    ref=context['target']['face_ref']
    row={'target':'lipstick','enabled':True,'owner':{'version':1,'source_sha256':source['sha256'],
        'landmarks_sha256':state['faces'][ref['face_instance_id']]['evidence']['landmark_digest'],'backend':'mediapipe'},
        'recipe':{'version':1,'domain':'source-normalized','objects':[
            {'id':'brush','name':'restore','enabled':True,'operation':'add','kind':'brush','opacity':1.,
             'feather':0.,'points':[[.5,.5]],'axes':[[.1,0.],[0.,.1]]}]}}
    candidate,assets=A.retain(state,{},ref,source,row)
    weight=np.ones((4,4),np.uint8)
    field={'face_ref':ref,'stage':'lipstick','weight':weight,
        'content_sha256':hashlib.sha256(weight.tobytes()).hexdigest(),
        'recipe_sha256':candidate['faces'][ref['face_instance_id']]['local_assets']['lipstick']['content_sha256']}
    return engine,candidate,source,assets,{(ref['face_instance_id'],'lipstick'):field}


def test_vectors_and_raster_must_both_match_exact_source_face_and_hash(monkeypatch):
    _,state,source,assets,fields=retained(monkeypatch)
    D.validate_supports(state,assets,source);D.validate_fields(state,source,fields,(4,4))
    with pytest.raises(ValueError):D.validate_fields(state,source,{},(4,4))
    bad=deepcopy(fields);next(iter(bad.values()))['weight'][0,0]=2
    with pytest.raises(ValueError):D.validate_fields(state,source,bad,(4,4))
    bad=deepcopy(fields);next(iter(bad.values()))['recipe_sha256']='f'*64
    with pytest.raises(ValueError):D.validate_fields(state,source,bad,(4,4))
    bad=deepcopy(assets);next(iter(bad.values()))['source']['width']=8
    with pytest.raises(ValueError):D.validate_supports(state,bad,source)


def test_recovery_source_requires_real_current_derived_precompute(monkeypatch):
    engine,_,_,source,_,_=owned(monkeypatch)
    assert D.source_binding(engine)==source
    engine._precompute.input_source_binding['sha256']='f'*64
    with pytest.raises(ValueError):D.source_binding(engine)


def test_empty_global_recovery_remains_empty(monkeypatch):
    from lumaretouch_engine.people_state import face_ref
    engine,state,source,assets,_=retained(monkeypatch)
    face=next(iter(state['faces'].values()))
    value=A.resolve(state,assets,face_ref(face),'lipstick')
    assert P.global_value(engine,value)==R.empty()


def test_stage_key_keeps_provenance_and_effective_source_independent(monkeypatch):
    from lumaretouch_engine import effect_recovery_runtime as runtime,creative_derived_source as source
    engine,_,_,owned_source,_,_=owned(monkeypatch)
    engine._doc_index=0;engine._docs[0]['path']='/physical/original'
    stamp=(1,2,3,4,5)
    first=runtime.stage_key(engine,R.empty(),source_stamp=stamp)
    monkeypatch.setattr(source,'binding',lambda _: {**owned_source,'sha256':'f'*64})
    second=runtime.stage_key(engine,R.empty(),source_stamp=stamp)
    assert first!=second and first[1]==second[1]==stamp


def test_candidate_assets_are_forwarded_before_publication(monkeypatch):
    from lumaretouch_engine import people_owned_inputs as inputs,people_engine_runtime as runtime
    engine,state,source,assets,_=retained(monkeypatch)
    face=next(iter(state['faces'].values()))
    from lumaretouch_engine.people_state import face_ref
    recovery=A.resolve(state,assets,face_ref(face),'lipstick')
    engine._people_sync=lambda **kwargs:None
    engine._people_analyses={source['sha256']:{}}
    engine._vram.h=engine._vram.w=4
    seen=[]
    monkeypatch.setattr(A,'raster',lambda *args,**kwargs:{})
    def forwarding(actual,candidate,**kwargs):
        assert actual is engine and kwargs['support_bank']!=engine._people_support
        assert A.resolve(candidate,kwargs['support_bank'],face_ref(face),'lipstick')==recovery
        seen.append(kwargs['support_bank']);return {}
    monkeypatch.setattr(inputs,'preview',forwarding)
    monkeypatch.setattr(runtime,'prepare_preview',lambda *args,**kwargs:'prepared')
    staged=P.prepare(engine,recovery,'lipstick')
    assert staged['prepared']=='prepared' and seen and engine._people_support=={}
