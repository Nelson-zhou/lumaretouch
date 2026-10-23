"""AUTHORED / UNRUN: exact ID admission and owned source/export routes.

These isolated contracts are not visual, SAM-model, GPU, or full-project QA.
No implementation or fixture was executed while authoring this file.
"""
from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine import creative_id_background_host as H
from lumaretouch_engine import creative_derived_id_background as C
from lumaretouch_engine import creative_derived_source as D
from lumaretouch_engine import creative_derived_prompted as Q
from lumaretouch_engine import id_background_runtime as R
from lumaretouch_engine import id_background_support as U
from lumaretouch_engine import id_background_state as S
from lumaretouch_engine import local_mask_state as M


SOURCE={'sha256':'a'*64,'width':12,'height':8}
STAMP=(1,2,3,4,5)


def value(*,enabled=True):
    mask=M.check({'source':deepcopy(SOURCE),'semantic_owner':None,
        'recipe':{'version':1,'domain':'source-normalized','objects':[
            {'id':'reviewed-subject','name':'Reviewed source subject','kind':'radial',
             'enabled':True,'operation':'add','opacity':1.,'feather':0.,
             'center':[.5,.5],'axes':[[.3,0.],[0.,.4]]}]}})
    support=U.check_binding({'version':1,'category':'subject','reviewed':True,
                             'mask':mask,'recipe_sha256':U.digest(mask)},'subject')
    result=S.empty();result['source']=deepcopy(SOURCE)
    result['support']['subject']=support;result['enabled']=enabled
    return S.check(result)


def mutation(action='id_clear'):
    return {'cmd':'background','action':action,'request_id':'transaction',
            'document_id':'11','recipe_document_id':'document-version','recipe_revision':'2'}


def prepared():
    return {'alpha':np.ones((8,12),np.float32),'background':np.full((8,12,3),.4,np.float32),
            'encoding':'linear-srgb-d65','render_scale':1.}


def spec():
    return SimpleNamespace(creative_base=object(),id_background=value(),id_background_bundle=None,
        id_background_path='/provenance/original.png',id_background_stamp=list(STAMP),
        creative_id_background_context={'metadata':'fixture only'})


def test_guard_routes_only_id_commands_not_a_generic_background_exemption():
    engine=SimpleNamespace()
    assert H.is_command(engine,'background',mutation())
    assert not H.is_command(engine,'background',{'action':'replace'})
    assert not H.is_command(engine,'background',{'action':'id_set_unreviewed'})
    assert not H.is_command(engine,'grade',mutation())
    assert H.is_command(engine,'color_picker_capture',{'picker_action':'id_background_subject'})
    assert not H.is_command(engine,'color_picker_capture',{'picker_action':'exposure'})


def test_unknown_fields_are_rejected_before_source_proof(monkeypatch):
    calls=[]
    monkeypatch.setattr(C,'validate_state',lambda engine:calls.append('state'))
    monkeypatch.setattr(C,'preview',lambda *args:calls.append('source'))
    with pytest.raises(ValueError):H.require_command(SimpleNamespace(),'background',{**mutation(),'preview_id':'fabricated'})
    assert calls==[]


def test_mutation_admission_checks_current_source_with_neutral_effect(monkeypatch):
    engine=SimpleNamespace();calls=[]
    monkeypatch.setattr(C,'validate_state',lambda owner:calls.append(('state',owner)))
    monkeypatch.setattr(C,'preview',lambda owner,intent:calls.append(('source',owner,intent)))
    H.require_command(engine,'background',mutation())
    assert calls==[('state',engine),('source',engine,S.empty())]


def test_terminal_receipt_replay_precedes_changed_document_or_model(monkeypatch):
    request=mutation();digest=sha256(json.dumps(request,sort_keys=True,allow_nan=False).encode()).hexdigest()
    engine=SimpleNamespace(_id_background_owner=SimpleNamespace(cache={'transaction':(digest,{'success':True})}))
    def deny(*args):raise AssertionError('Terminal replay must not rerun source/model checks')
    monkeypatch.setattr(C,'validate_state',deny);monkeypatch.setattr(C,'preview',deny)
    H.require_command(engine,'background',request)
    with pytest.raises(ValueError):H.require_command(engine,'background',{**request,'document_id':'12'})


def test_state_remains_readable_without_a_renderable_source(monkeypatch):
    def deny(*args):raise AssertionError('Status is not an effect mutation')
    monkeypatch.setattr(C,'preview',deny)
    H.require_command(SimpleNamespace(),'background',{'cmd':'background','action':'id_state',
        'request_id':'status','document_id':'11'})
    with pytest.raises(ValueError):
        H.require_command(SimpleNamespace(),'background',{'cmd':'background','action':'id_state',
            'request_id':'status','document_id':'11','recipe':{}})


def test_sampling_requires_existing_native_capture_owner():
    with pytest.raises(ValueError):
        H.require_command(SimpleNamespace(),'background',{'cmd':'background','action':'id_sample','request_id':'pick'})


def test_original_decode_dimensions_are_provenance_not_derived_extent(monkeypatch):
    snapshot={'creative_base':object(),'id_background':value(),'creative_id_background_context':{'owned':'metadata'}}
    calls=[]
    monkeypatch.setattr(M,'file_stamp',lambda path:STAMP)
    monkeypatch.setattr(C,'verify_snapshot',lambda snap,path=None,shape=None:calls.append((snap,path,shape)))
    R.check_export_decode(snapshot,'/provenance/original.png',STAMP,(300,400))
    assert calls==[(snapshot,'/provenance/original.png',None)]
    assert snapshot['id_background_stamp']==list(STAMP)
    assert snapshot['id_background_path']=='/provenance/original.png'


def test_changed_original_provenance_never_installs_export_path(monkeypatch):
    snapshot={'creative_base':object(),'id_background':value()}
    monkeypatch.setattr(M,'file_stamp',lambda path:(9,2,3,4,5))
    with pytest.raises(ValueError):R.check_export_decode(snapshot,'/original.png',STAMP,(300,400))
    assert 'id_background_path' not in snapshot


def test_configure_export_freezes_metadata_and_forbids_cross_document_reuse(monkeypatch):
    snapshot={'creative_base':object(),'id_background':value(enabled=False),
        'creative_id_background_context':{'source':deepcopy(SOURCE),'recipe':value(enabled=False)},
        'id_background_path':'/original.png','id_background_stamp':list(STAMP)}
    checked=[]
    monkeypatch.setattr(C,'verify_snapshot',lambda snap,path=None,shape=None:checked.append((path,shape)))
    target=SimpleNamespace()
    R.configure_export(target,snapshot,(8,12),for_document=True)
    assert checked==[('/original.png',(8,12))]
    assert target.creative_id_background_context==snapshot['creative_id_background_context']
    assert target.creative_id_background_context is not snapshot['creative_id_background_context']
    snapshot['creative_id_background_context']['source']['sha256']='f'*64
    assert target.creative_id_background_context['source']==SOURCE
    with pytest.raises(ValueError):R.configure_export(SimpleNamespace(),snapshot,(8,12),for_document=False)


def test_manual_live_input_never_calls_original_or_builds_model_packet(monkeypatch):
    rgb=np.full((4,6,3),.4,np.float32);rgb.setflags(write=False)
    engine=SimpleNamespace(_creative_base=object(),_vram=object(),_docs=[{'path':'/must-not-decode.png'}],_doc_index=0)
    monkeypatch.setattr(C,'preview',lambda owner,intent:(None,rgb,('verified-live-source',)))
    monkeypatch.setattr(D,'binding',lambda owner:deepcopy(SOURCE))
    def deny(*args):raise AssertionError('No original path or SAM for manual support')
    monkeypatch.setattr(M,'verify_source',deny);monkeypatch.setattr(Q,'capture',deny)
    key,path,actual,source,packet=R._live_input(engine,value())
    assert key==('verified-live-source',);assert path is None
    assert actual is rgb and not actual.flags.writeable
    assert source==SOURCE and packet is None


def test_canonical_export_is_verified_before_any_prepare_or_original_decode(monkeypatch):
    target=spec();calls=[]
    monkeypatch.setattr(M,'file_stamp',lambda path:STAMP)
    def reject(*args):raise ValueError('canonical source proof mismatch')
    monkeypatch.setattr(C,'verify_export',reject)
    monkeypatch.setattr(R,'prepare',lambda *args,**kwargs:calls.append('prepare'))
    monkeypatch.setattr(M,'verify_source',lambda *args:calls.append('original'))
    with pytest.raises(ValueError,match='canonical'):
        R.export_prepare(target,np.zeros((8,12,3),np.float32))
    assert calls==[] and target.id_background_prepared is None


def test_derived_export_passes_exact_fullfloat_exclusive_path_none(monkeypatch):
    target=spec();rgb=np.full((8,12,3),.4,np.float32)
    rgb[0,0]=[256/65535,257/65535,258/65535]
    calls=[];fields=prepared()
    monkeypatch.setattr(M,'file_stamp',lambda path:STAMP)
    monkeypatch.setattr(C,'verify_export',lambda owner,actual:{'source':deepcopy(SOURCE)})
    monkeypatch.setattr(C,'verify_snapshot',lambda *args,**kwargs:None)
    def record(*args,**kwargs):calls.append((args,kwargs));return fields
    monkeypatch.setattr(R,'prepare',record)
    def deny(*args):raise AssertionError('Derived export cannot verify or decode original as source')
    monkeypatch.setattr(M,'verify_source',deny)
    R.export_prepare(target,rgb)
    args,kwargs=calls[0]
    assert args[2] is None and args[3] is rgb
    assert kwargs['effective_source']==SOURCE and kwargs['source_pixels'] is rgb
    assert kwargs['full_source'] is True
    assert 'source_input' not in kwargs
    assert rgb[0,0,0]!=rgb[0,0,1]
    assert target.id_background_prepared is fields
    assert not fields['alpha'].flags.writeable and not fields['background'].flags.writeable


def test_prepared_export_bytes_are_rechecked_not_just_pointer_identity(monkeypatch):
    target=spec();target.id_background_prepared=prepared()
    target._id_background_prepared_proof=R._prepared_proof(target,target.id_background_prepared)
    monkeypatch.setattr(M,'file_stamp',lambda path:STAMP)
    monkeypatch.setattr(C,'verify_snapshot',lambda *args,**kwargs:None)
    target.id_background_prepared['alpha'][0,0]=.5
    with pytest.raises(ValueError,match='fields changed'):R.finish_export(target)


def test_export_rejects_proxy_grid_or_wrong_working_encoding():
    target=spec()
    for fields in ({**prepared(),'alpha':np.ones((4,6),np.float32)},
                   {**prepared(),'render_scale':.5},
                   {**prepared(),'encoding':'encoded-srgb'},
                   {**prepared(),'background':np.full((8,12,3),np.nan,np.float32)}):
        with pytest.raises(ValueError):R._prepared_proof(target,fields)


def test_live_field_bytes_cannot_change_under_same_tensor_pointer_and_version():
    # Regression contract: NumPy alias writes bypass Torch's version counter.
    # A pointer/version-only stamp is insufficient for actual coverage identity.
    torch=pytest.importorskip('torch')
    field=torch.ones((1,4,2,2),dtype=torch.float32)
    stage=SimpleNamespace(required=True,suspended=None,fields=field,shape=(2,2))
    before=R._stage_proof(stage);version=field._version;pointer=field.data_ptr()
    field.numpy()[0,0,0,0]=.25
    assert field._version==version and field.data_ptr()==pointer
    assert R._stage_proof(stage)!=before
