"""Authored development handoff; not executed in this implementation session."""
from copy import deepcopy
import pytest
from lumaretouch_engine import local_grade_layers as L, local_mask_state as M, scope as SC
from lumaretouch_engine.local_grade_preset_review import PresetReviews


SOURCE = {'sha256':'a'*64, 'width':100, 'height':80}
TARGET = {'sha256':'b'*64, 'width':180, 'height':120}


def layer(ident='source', kind='linear', operation='add'):
    obj = {'id':'mask', 'name':'mask', 'kind':kind, 'enabled':True,
           'operation':operation, 'opacity':.8, 'feather':3}
    if kind == 'linear': obj.update(start=[.1,.2], end=[.8,.7], cross=[-.5,.7])
    elif kind == 'brush': obj.update(points=[[.3,.4]], axes=[[.02,0],[0,.02]])
    elif kind == 'semantic': obj.update(channel='skin')
    elif kind == 'color_range': obj.update(color=[.5,.3,.2], tolerance=.2, invert=True)
    mask = {'recipe':{'version':1,'domain':'source-normalized','objects':[obj]},
            'source':dict(SOURCE),'semantic_owner':None}
    if kind == 'semantic': mask['semantic_owner']={'backend':'mediapipe','contract':M.SEMANTIC_CONTRACT+':'+'c'*64}
    return {'id':ident,'name':ident,'enabled':True,'grade':[.01,.15,-.1,.7],'mask':mask}


def state(layers=()):
    return {'_local_grade_layers':{'version':1,'layers':deepcopy(list(layers))},
            '_grade_scope':'all','_grade':L.NEUTRAL,'_local_masks':M.empty(),
            '_grade_mask':None,'_lut_preset':None,'_lut':None,'_lut_amount':.6,
            '_exposure':(1.,0,0,0,0,0,0)}


def options(**kw):
    return {'mode':'append','types':list(L.TYPES),'rebase':True,'groups':None,**kw}


def test_append_keeps_existing_group_order_and_entire_legacy_slot():
    target = state([layer('old')]); target.update(_grade_scope='objects',_grade=(.02,.2,.1,.6),
        _local_masks=layer('legacy')['mask'],_lut_preset='creamy')
    before = deepcopy(target)
    prepared, facts = L.transfer(L.params_of(state([layer()])),target,TARGET,options())
    after = SC.apply_modules(target,{L.OP:prepared},local_replace_legacy=facts['legacy_removed'])
    assert target == before and facts['legacy_preserved'] and not facts['legacy_removed']
    assert after['_local_grade_layers']['layers'][0] == before['_local_grade_layers']['layers'][0]
    assert after['_local_grade_layers']['layers'][1]['mask']['source'] == TARGET
    for key in L.FIELDS[1:]: assert after[key] == before[key]
    assert after['_exposure'] == before['_exposure']


def test_replace_only_selected_type_and_restore_exact_legacy_link():
    target = state([layer('portrait','semantic'),layer('custom')])
    target.update(_grade_scope='objects',_grade=(.02,.1,.1,.5),
                  _local_masks=layer('legacy')['mask'],_lut_preset='creamy')
    prepared, facts = L.transfer(L.params_of(state([layer()])),target,TARGET,options(mode='replace',types=['custom']))
    assert facts['legacy_removed'] and facts['removed']==['custom','当前编辑器局部调色']
    after=SC.apply_modules(target,{L.OP:prepared},local_replace_legacy=True)
    assert after['_grade']==L.NEUTRAL and after['_lut_preset'] is None
    assert after['_lut_amount']==target['_lut_amount'] and after['_local_grade_layers']['layers'][0]['id']=='portrait'
    after['_exposure']=(2.,0,0,0,0,0,0)
    restored=SC.restore_modules(after,target,[L.OP])
    for key in L.FIELDS: assert restored[key]==target[key]
    assert restored['_exposure'][0]==2


def test_explicit_whole_group_exclusion_is_required_for_brush():
    source=L.params_of(state([layer('gradient'),layer('brush','brush')]))
    with pytest.raises(ValueError,match='画笔'):L.transfer(source,state(),TARGET,options())
    prepared,facts=L.transfer(source,state(),TARGET,options(groups=['gradient']))
    assert facts['selected_group_ids']==['gradient'] and facts['excluded']==['brush']
    assert len(prepared['groups']['layers'])==1
    with pytest.raises(ValueError,match='已变化'):L.transfer(source,state(),TARGET,options(groups=['deleted']))


def test_mixed_semantics_cannot_lose_a_subtract_operand_or_require_silent_rebase():
    mixed=layer(); subtract=layer('portrait','semantic','subtract')['mask']['recipe']['objects'][0]
    subtract['id']='minus'; mixed['mask']['recipe']['objects'].append(subtract)
    mixed['mask']['semantic_owner']=layer('portrait','semantic')['mask']['semantic_owner']
    with pytest.raises(ValueError,match='混合'):L.transfer(L.params_of(state([mixed])),state(),TARGET,options(types=['custom']))
    with pytest.raises(ValueError,match='重映射'):L.transfer(L.params_of(state([layer()])),state(),TARGET,options(rebase=False))
    ranges,_=L.transfer(L.params_of(state([layer(kind='color_range')])),state(),TARGET,options(rebase=False))
    assert ranges['groups']['layers'][0]['mask']['recipe']['objects'][0]['invert'] is True


def test_frozen_preset_review_is_revision_bound_and_one_use(monkeypatch):
    from lumaretouch_engine import local_grade_preset_review as Review
    original=state(); modules={L.OP:L.params_of(state([layer()]))}
    prepared,facts=L.transfer(modules[L.OP],original,TARGET,options())
    monkeypatch.setattr(Review.LR,'prepare_modules',lambda *a,**kw:({L.OP:deepcopy(prepared)},deepcopy(facts)))
    monkeypatch.setattr(Review.LR,'verify_modules',lambda *a:None)
    reviews=PresetReviews(); preset={'id':'p','name':'preset','modules':modules}; row={'path':'/target','state':original}
    plan=reviews.prepare(preset,original,row,'doc','7',options())
    preset['name']='changed after review'
    with pytest.raises(ValueError,match='版本'):reviews.claim(plan['preflight_token'],'p',original,row,'doc','8')
    record=reviews.claim(plan['preflight_token'],'p',original,row,'doc','7')
    assert record['preset']['name']=='preset'
    with pytest.raises(ValueError,match='失效'):reviews.claim(plan['preflight_token'],'p',original,row,'doc','7')


def test_group_only_snapshot_never_uses_neutral_rgb16_passthrough():
    from lumaretouch_engine.server import Engine
    assert Engine._master16_snapshot_blockers({'local_grade_groups':{'version':1,'layers':[layer()]}})


def test_undo_identity_fences_legacy_edits_without_fencing_unrelated_exposure():
    before=state([layer()]); key=L.undo_key(before)
    before['_exposure']=(2.,0,0,0,0,0,0)
    assert L.undo_key(before)==key
    before['_grade']=(.01,0,0,1)
    assert L.undo_key(before)!=key
