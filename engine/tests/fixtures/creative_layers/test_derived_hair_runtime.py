"""AUTHORED / UNRUN: pathless derived hair consumer/export integration.

Synthetic model evidence and mocked solvers are ownership fixtures only.
No product imports, inference, tests or rendering were run while authoring.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from test_derived_hair_controller import setup,stroke,prompted
from test_derived_effects_contract import patch
from lumaretouch_engine import creative_derived_hair as D, creative_derived_effects as C
from lumaretouch_engine import hair_colour_assets as A, hair_colour_evidence as V
from lumaretouch_engine import hair_colour_state as H, people_state as S


def reviewed(monkeypatch):
    engine,state,context,source,rgb=setup(monkeypatch)
    evidence=V.current(engine,source)
    record=A.reviewed(context['target']['face_ref'],source,stroke(),A.MODEL_SHA256,
        evidence_sha=V.identity(evidence),confirmed=True)
    state,assets=A.retain(state,{},record);engine._hair_colour_assets=assets
    return engine,state,context,source,evidence,assets


@pytest.mark.parametrize('style',H.STYLE_IDS)
def test_all_existing_hair_styles_have_exact_leaf_admission(monkeypatch,style):
    engine,_,context,_,_=setup(monkeypatch)
    command=patch(context,H.OPERATION,'/style',style)
    assert C.is_local_command('people',command)
    C.require_command(engine,'people',command)
    assert not C.is_local_command('people',patch(context,H.OPERATION,'/style','invented'))


@pytest.mark.parametrize('action,payload',[
    ('context',{}),('preview_support',{'mask':stroke()}),
    ('preview_recovery',{'mask':stroke()}),('clear_support',{}),('clear_recovery',{}),
    ('commit_support',{'preview_id':'review','confirmed':True}),
    ('commit_recovery',{'preview_id':'review','confirmed':True}),
])
def test_hair_controller_envelopes_remain_local_and_complete(monkeypatch,action,payload):
    engine,_,context,_,_=setup(monkeypatch)
    command={'cmd':'hair_colour','request_id':'request','people_context':context,'action':action,'payload':payload}
    C.require_command(engine,'hair_colour',command)
    bad=deepcopy(command);bad['people_context']['target']={'scope':'person','target_id':'person','face_ref':None}
    assert not C.is_local_command('hair_colour',bad)
    bad=deepcopy(command);bad['payload']['source_path']='/original.jpg'
    assert not C.is_local_command('hair_colour',bad)


@pytest.mark.parametrize('enabled',[False,True])
def test_persisted_prompted_operand_never_gets_original_file_fallback(monkeypatch,enabled):
    engine,state,context,source,evidence,_=reviewed(monkeypatch)
    record=A.reviewed(context['target']['face_ref'],source,prompted(enabled),A.MODEL_SHA256,
        evidence_sha=V.identity(evidence),confirmed=True)
    state,assets=A.retain(state,{},record)
    with pytest.raises(ValueError,match='prompted'):D.validate(state,assets,evidence,source)


def test_preview_and_frozen_export_forward_owned_evidence_without_paths(monkeypatch):
    engine,state,_,source,evidence,assets=reviewed(monkeypatch)
    inputs=D.preview_inputs(engine,state,source)
    assert set(inputs)=={'hair_assets','hair_evidence'}
    assert inputs['hair_evidence']['weight_sha256']==evidence['weight_sha256']
    snapshot={'state':state,'asset_sha256':source['sha256'],'creative_source':source}
    D.capture(engine,{'_creative_base':engine._creative_base},snapshot,engine._precompute,source)
    output=D.export_inputs(snapshot)
    assert output['hair_assets']==assets and 'hair_source_path' not in output
    assert output['hair_evidence']['source']==source
    snapshot['hair_colour_source_path']='/original.jpg'
    with pytest.raises(ValueError):D.export_inputs(snapshot)


def test_stale_or_missing_evidence_never_labels_original_analysis(monkeypatch):
    engine,state,_,source,evidence,assets=reviewed(monkeypatch)
    with pytest.raises(ValueError):D.validate(state,assets,None,source)
    changed=dict(evidence,source={**source,'sha256':'f'*64})
    with pytest.raises(ValueError):D.validate(state,assets,changed,source)
    engine._precompute.input_source_binding['sha256']='f'*64
    with pytest.raises(ValueError):D.capture(engine,{'_creative_base':engine._creative_base},
        {'state':state},engine._precompute,source)


@pytest.mark.parametrize('refuse',[False,True])
def test_real_runtime_port_receives_unquantized_pixels_and_owned_bank(monkeypatch,refuse):
    from lumaretouch_engine import people_render_runtime as R,hair_colour_runtime as HAIR
    engine,state,context,source,evidence,assets=reviewed(monkeypatch)
    ref=context['target']['face_ref'];key=ref['face_instance_id']
    state=S.set_override(state,'face',key,H.OPERATION,'/strength',.4)
    analysis={'face_ref':ref,'evidence':state['faces'][key]['evidence'],
        'landmarks':engine._precompute.landmarks,'excluded':None,'skin':None}
    rgb=np.full((4,4,3),np.float32(.500013),np.float32);calls=[]
    monkeypatch.setattr(R.A,'build_geometry',lambda *a,**k:SimpleNamespace(fields=[None],resident_bytes=lambda:0))
    monkeypatch.setattr(R,'combine',lambda *a,**k:SimpleNamespace(delta=np.zeros((4,4,2),np.float32),owner=np.zeros((4,4),np.int32)))
    def consume(graph,asset,pixels,plan,**kwargs):
        assert asset==source['sha256'] and pixels is rgb
        assert kwargs['assets'] is assets and kwargs['evidence'] is evidence and kwargs['source_path'] is None
        calls.append(asset)
        if refuse:raise HAIR.HairColourRefused('fixture explicit native refusal')
        return (),{}
    monkeypatch.setattr(HAIR,'prepare_bank',consume)
    args=(state,source['sha256'],rgb,{key:analysis})
    kwargs=dict(byte_budget=256*1024**2,creative_source=source,hair_assets=assets,hair_evidence=evidence)
    if refuse:
        with pytest.raises(HAIR.HairColourRefused):R.prepare(*args,**kwargs)
    else:assert R.prepare(*args,**kwargs).effects==()
    assert calls==[source['sha256']]
