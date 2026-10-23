"""AUTHORED / UNRUN: smoothing recovery source/review contracts, not quality QA."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from test_derived_recovery_contract import owned, preview
from test_derived_global_recovery import prepared, recipe
from lumaretouch_engine import creative_derived_recovery as R
from lumaretouch_engine import creative_derived_global_recovery as G
from lumaretouch_engine import creative_derived_smoothing as C
from lumaretouch_engine import creative_derived_source as D
from lumaretouch_engine import effect_recovery_preview as V
from lumaretouch_engine import effect_recovery_state as S
from lumaretouch_engine import effect_recovery_runtime as E
from lumaretouch_engine import people_recovery as P
from lumaretouch_engine import local_mask_state as M


def smoothing(monkeypatch):
    engine,_,_,source,proof,capture=owned(monkeypatch)
    consumer={'version':1,'source':source,'recipe':{'strength':.4,'channel':'skin',
              'params':{'radius':16}},'evidence_key':['actual-source','actual-skin','repair-stack']}
    monkeypatch.setattr(C,'recovery_context',lambda actual:deepcopy(consumer))
    engine._people_cursors={}
    return engine,source,proof,capture,consumer


def reviewed(proof,context):
    return {'id':'2'*32,'target':'skin_smoothing','proof':proof,'value':S.empty(),
            'people_context':None,'global_context':context,'presented':True,'committable':True}


def test_smoothing_review_needs_consumer_not_selected_face(monkeypatch):
    engine,_,proof,_,_=smoothing(monkeypatch)
    monkeypatch.setattr(P,'context',lambda *_:(_ for _ in ()).throw(AssertionError('not a face effect')))
    R.require_command(engine,'effect_recovery_preview',preview(proof,'skin_smoothing'))
    context=R.global_context(engine,'skin_smoothing')
    assert context['consumer']['recipe']['channel']=='skin' and 'face_ref' not in context
    assert 'skin_smoothing' not in R.TARGETS
    R.assert_review(engine,reviewed(proof,context))
    with pytest.raises(ValueError):R.global_context(engine,'background_replace')


@pytest.mark.parametrize('key',['strength','channel','params','evidence_key','source'])
def test_every_smoothing_consumer_change_expires_presented_review(monkeypatch,key):
    engine,_,proof,_,consumer=smoothing(monkeypatch)
    record=reviewed(proof,R.global_context(engine,'skin_smoothing'))
    engine._effect_recovery_preview_owner=SimpleNamespace(record=record)
    request={**proof,'cmd':'effect_recovery','action':'apply','preview_id':record['id'],'request_id':'smooth-recovery'}
    R.require_command(engine,'effect_recovery',request)
    if key=='strength':consumer['recipe'][key]=.8
    elif key=='channel':consumer['recipe'][key]=None
    elif key=='params':consumer['recipe'][key]={'radius':32}
    elif key=='source':consumer[key]={**consumer[key],'sha256':'f'*64}
    else:consumer[key].append('changed-mask-or-replay')
    with pytest.raises(ValueError):R.require_command(engine,'effect_recovery',request)
    owner=V.RecoveryPreview(engine,lambda event:None);owner.record=record
    with pytest.raises(ValueError):owner.prepare(request)


def test_missing_actual_consumer_refuses_before_recovery_mutation(monkeypatch):
    engine,source,_,_,_=smoothing(monkeypatch)
    from lumaretouch_engine import creative_derived_repair_runtime as B
    monkeypatch.setattr(B,'verify_pipeline',lambda *_:None)
    assert G.mutation_binding(engine,'skin_smoothing')==source
    monkeypatch.setattr(C,'recovery_context',lambda *_:(_ for _ in ()).throw(ValueError('stale mask')))
    with pytest.raises(ValueError,match='stale mask'):G.mutation_binding(engine,'skin_smoothing')
    with pytest.raises(ValueError):G.mutation_binding(engine,'background_replace')


def test_disabled_smoothing_vectors_keep_source_without_live_consumer():
    source={'sha256':'a'*64,'width':4,'height':4}
    value=recipe(source,enabled=False);value['targets'][0]['target']='skin_smoothing'
    assert G.validate(value,source)==value and not S.enabled(value)
    with pytest.raises(ValueError):G.validate(value,{**source,'sha256':'b'*64})
    value['targets'][0]['target']='background_replace'
    with pytest.raises(ValueError):G.validate(value,source)


def test_smoothing_export_keeps_full_source_vectors_and_exact_float_proof(monkeypatch):
    spec,pixels,source=prepared(monkeypatch)
    spec.effect_recovery['targets'][0]['target']='skin_smoothing'
    spec.creative_recovery_context=G.capture({'creative_base':spec.creative_base},spec.effect_recovery,'original')
    G.stamp_pixels(spec,pixels);seen=[]
    monkeypatch.setattr(M.R,'raster',lambda vector,shape:seen.append((deepcopy(vector),shape)) or np.full(shape,128,np.uint8))
    E.export_prepare(spec,(4,4),source_pixels=pixels)
    assert seen==[(spec.effect_recovery['targets'][0]['recipe'],(4,4))]
    assert spec.effect_recovery_fields[0]['target']=='skin_smoothing'
    changed=pixels.copy();changed[0,0,0]+=.001
    with pytest.raises(ValueError):E.export_prepare(spec,(4,4),source_pixels=changed)


def test_smoothing_review_still_requires_presented_committable_receipt(monkeypatch):
    engine,_,proof,_,_=smoothing(monkeypatch)
    record=reviewed(proof,R.global_context(engine,'skin_smoothing'))
    engine._effect_recovery_preview_owner=SimpleNamespace(record=record)
    request={**proof,'cmd':'effect_recovery','action':'apply','preview_id':record['id'],'request_id':'receipt'}
    for key in ('presented','committable'):
        record[key]=False
        with pytest.raises(ValueError):R.require_command(engine,'effect_recovery',request)
        record[key]=True


def test_stale_smoothing_proof_reports_reason_without_losing_other_targets(monkeypatch):
    from lumaretouch_engine import fabric_controller as F
    engine=SimpleNamespace(_vram=SimpleNamespace(has_background=lambda:False),
        _retouch_render_args=lambda:(_ for _ in ()).throw(ValueError('current skin proof changed')))
    monkeypatch.setattr(D,'record',lambda actual:object())
    monkeypatch.setattr(F,'status',lambda actual:{'lit':False,'reason':'fabric off'})
    monkeypatch.setattr(E.FACE,'availability',lambda actual:{'active':False,'reason':'face off'})
    monkeypatch.setattr(P,'managed',lambda actual:False)
    result=E.availability(engine)
    assert result['skin_smoothing']=={'active':False,'reason':'current skin proof changed'}
    assert result['fabric_fine']=={'active':False,'reason':'fabric off'}
    assert not result['background_replace']['active']
