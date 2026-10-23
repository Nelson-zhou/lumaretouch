"""AUTHORED / UNRUN. Source ownership fixtures, not native/visual acceptance.

Synthetic pixels and model evidence below exercise contracts only. No product
imports, tests, inference or native rendering were run while authoring.
"""
import base64
import io
from copy import deepcopy
import numpy as np
import pytest
from test_derived_effects_contract import fixture, patch
from lumaretouch_engine import creative_derived_effects as C, people_state as S
from lumaretouch_engine import eye_light_state as E, eye_light_support as V


@pytest.mark.parametrize('side',['left','right'])
@pytest.mark.parametrize('key,value',[
    ('asset','original-softbox-v1'),('asset','original-window-v1'),
    ('strength',75.),('horizontal',-50.),('vertical',50.),
    ('rotation',-100.),('flip',True),
])
def test_exact_eye_leaf_domains(monkeypatch,side,key,value):
    engine,_,context,_,_=fixture(monkeypatch)
    command=patch(context,E.OPERATION,f'/{side}/{key}',value)
    assert C.is_local_command('people',command)
    C.require_command(engine,'people',command)


@pytest.mark.parametrize('path,value',[
    ('/left/asset','foreign-material'),('/left/strength',True),
    ('/right/rotation',float('nan')),('/left/flip',1),('/linked',0),
])
def test_invalid_material_and_scalar_domains(monkeypatch,path,value):
    _,_,context,_,_=fixture(monkeypatch)
    assert not C.is_local_command('people',patch(context,E.OPERATION,path,value))


def test_linked_pair_is_atomic_not_individually_rejected(monkeypatch):
    from lumaretouch_engine.people_edit import stage
    engine,state,context,owned,_=fixture(monkeypatch)
    command=patch(context,E.OPERATION,'/left/strength',25.)
    command['payload']['patches'].append({**command['payload']['patches'][0],'parameter_path':'/right/strength'})
    C.require_command(engine,'people',command)
    envelope={key:value for key,value in command.items() if key!='cmd'}
    args=dict(document_id='doc',document_epoch='epoch',document_revision=0,
              asset_sha256=owned['sha256'],source_dimensions=(4,4))
    out=stage(envelope,state,**args)['state']
    C.require_graph(out,owned)
    envelope['payload']['patches'].pop()
    with pytest.raises(ValueError):stage(envelope,state,**args)


def test_reference_uses_effective_pixels_not_original_pixels(monkeypatch):
    from PIL import Image
    from lumaretouch_engine.body_pose_commands import source_preview
    engine,_,_,owned,rgb=fixture(monkeypatch)
    engine._src_rgb=np.zeros_like(rgb)
    shown=source_preview(engine)
    decoded=np.asarray(Image.open(io.BytesIO(base64.b64decode(shown['base64']))))
    np.testing.assert_array_equal(decoded,rgb)
    assert shown['source_sha256']==owned['sha256']
    assert np.any(decoded!=engine._src_rgb)


@pytest.mark.parametrize('action,payload',[
    ('eye_light_reference',{}),('eye_light_review',{'eyes':{'left':{}}}),
])
def test_review_routes_require_actual_analysis_even_before_payload_review(monkeypatch,action,payload):
    engine,_,context,_,_=fixture(monkeypatch)
    command={**context,'cmd':'people','request_id':'review','action':action,'payload':payload}
    C.require_command(engine,'people',command)
    engine._precompute.input_source_binding['sha256']='a'*64
    with pytest.raises(ValueError):C.require_command(engine,'people',command)


def reviewed(monkeypatch):
    engine,state,context,owned,_=fixture(monkeypatch)
    eyes={'left':{'visible':True,'unoccluded':True,'ownership_confirmed':True,
        'recipe':{'version':1,'domain':'source-normalized','objects':[
            {'id':'eye','name':'visible','enabled':True,'operation':'add','kind':'brush',
             'opacity':1.,'feather':0.,'points':[[.4,.4]],'axes':[[.1,0.],[0.,.1]]}]}}}
    state,assets=V.retain(state,{},context['target']['face_ref'],eyes)
    engine._people_support=assets
    return engine,state,context,owned,assets


def test_neutral_retained_review_is_still_content_verified(monkeypatch):
    from lumaretouch_engine.people_owned_inputs import preview
    engine,state,context,owned,assets=reviewed(monkeypatch)
    C.require_graph(state,owned)
    forwarded=preview(engine,state)
    assert forwarded['eye_light_assets'] is assets
    key=next(iter(assets));assets[key]['row']['landmark_digest']='f'*64
    with pytest.raises(ValueError):preview(engine,state)


@pytest.mark.parametrize('change',[
    lambda r:r['source'].update(sha256='f'*64),
    lambda r:r['source'].update(width=8),
    lambda r:r['face_ref'].update(analysis_revision=999),
    lambda r:r['row'].update(landmark_digest='f'*64),
])
def test_foreign_or_stale_review_never_rebinds(monkeypatch,change):
    _,state,context,_,assets=reviewed(monkeypatch)
    changed=deepcopy(assets);change(next(iter(changed.values())))
    with pytest.raises(ValueError):V.resolve(state,changed,context['target']['face_ref'])


def test_unadapted_support_and_shared_targets_stay_fenced(monkeypatch):
    _,state,context,owned,assets=reviewed(monkeypatch)
    face=state['faces'][context['target']['target_id']]
    descriptor=face['local_assets'].pop(V.KIND)
    face['local_assets']['repair']={**descriptor,'kind':'enhance'}
    with pytest.raises(ValueError):C.require_graph(state,owned)
    command=patch(context,E.OPERATION,'/linked',False)
    command['target']={'scope':'person','target_id':'person','face_ref':None}
    assert not C.is_local_command('people',command)


@pytest.mark.parametrize('refuse',[False,True])
def test_runtime_calls_only_adapted_eye_consumer_with_owned_inputs(monkeypatch,refuse):
    from types import SimpleNamespace
    from lumaretouch_engine import people_render_runtime as R, eye_light_people as P
    from lumaretouch_engine import hair_colour_runtime as H, eyeliner_people as L
    engine,state,context,owned,assets=reviewed(monkeypatch)
    ref=context['target']['face_ref'];key=ref['face_instance_id']
    state=S.set_override(state,'face',key,E.OPERATION,'/linked',False)
    state=S.set_override(state,'face',key,E.OPERATION,'/left/strength',25.)
    analysis={'face_ref':ref,'evidence':state['faces'][key]['evidence'],
        'landmarks':engine._precompute.landmarks,'excluded':None,'skin':None}
    rgb=np.full((4,4,3),np.float32(.500013),np.float32);calls=[]
    field=SimpleNamespace(fields=[None],resident_bytes=lambda:0)
    monkeypatch.setattr(R.A,'build_geometry',lambda *a,**k:field)
    monkeypatch.setattr(R.E,'prepare',lambda *a,**k:[])
    monkeypatch.setattr(R,'combine',lambda *a,**k:SimpleNamespace())
    def forbidden(*a,**k):raise AssertionError('Unadapted consumer invoked')
    monkeypatch.setattr(H,'prepare_bank',forbidden);monkeypatch.setattr(L,'prepare',forbidden)
    def consume(graph,bank,target,measured,pixels,recipe,**kwargs):
        assert bank is assets and target==ref and measured is analysis and pixels is rgb
        assert recipe['left']['strength']==25. and recipe['right']['strength']==0.
        calls.append(target)
        if refuse:raise RuntimeError('Native eye-light solver unavailable')
        return []
    monkeypatch.setattr(P,'prepare',consume)
    args=(state,owned['sha256'],rgb,{key:analysis})
    kwargs=dict(byte_budget=256*1024**2,creative_source=owned,eye_light_assets=assets)
    if refuse:
        with pytest.raises(R.PeoplePreparationRefused,match='Native eye-light'):R.prepare(*args,**kwargs)
    else:
        prepared=R.prepare(*args,**kwargs)
        assert prepared.effects==()
    assert calls==[ref]


def test_export_forwards_frozen_review_bank_without_quantizing_composite(monkeypatch):
    from lumaretouch_engine import people_engine_runtime as R
    _,state,_,owned,assets=reviewed(monkeypatch);calls=[]
    snapshot={'state':state,'asset_sha256':owned['sha256'],'creative_source':owned,
        'analyses':{},'support_assets':assets}
    rgb=np.full((4,4,3),np.float32(.500013),np.float32)
    def consume(*args,**kwargs):calls.append((args,kwargs));return 'prepared'
    monkeypatch.setattr(R,'prepare',consume)
    assert R.prepare_export(snapshot,rgb,None,byte_budget=256*1024**2)=='prepared'
    np.testing.assert_array_equal(calls[0][0][2],rgb)
    assert calls[0][1]['eye_light_assets'] is assets
