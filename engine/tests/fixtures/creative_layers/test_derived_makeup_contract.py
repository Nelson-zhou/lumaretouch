"""AUTHORED / UNRUN: reviewed makeup ownership, admission and consumer ports.

Synthetic evidence and mocked consumer boundaries are not inference, native,
photographic or numerical acceptance. No product imports/tests were executed
while this file was authored. Real UI/native/undo/reopen QA remains required.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from test_derived_effects_contract import fixture, patch
from lumaretouch_engine import creative_derived_effects as C, creative_derived_makeup as M
from lumaretouch_engine import people_state as S, people_algorithms as A
from lumaretouch_engine import lipstick_state as L, blush_makeup_state as B
from lumaretouch_engine import eyeliner_state as E, eyelash_state as H
from lumaretouch_engine import brow_makeup_state as W, iris_makeup_state as I
from lumaretouch_engine import lipstick_support as LS, blush_makeup_support as BS
from lumaretouch_engine import eyeliner_support as ES, eyelash_support as HS
from lumaretouch_engine import brow_makeup_support as WS, iris_makeup_support as IS

FAMILIES = ((L,LS,'lipstick'),(B,BS,'blush'),(E,ES,'eyeliner'),
            (H,HS,'eyelash'),(W,WS,'brow_makeup'),(I,IS,'iris'))


def brush():
    return {'version':1,'domain':'source-normalized','objects':[
        {'id':'visible','name':'visible','enabled':True,'operation':'add','kind':'brush',
         'opacity':1.,'feather':0.,'points':[[.4,.4]],'axes':[[.1,0.],[0.,.1]]}]}


def regions(prefix):
    basic={'recipe':brush(),'visible':True,'unoccluded':True,'ownership_confirmed':True}
    if prefix=='lipstick':return {side:deepcopy(basic) for side in ('upper','lower')}
    if prefix=='blush':return {side:deepcopy(basic) for side in ('left','right')}
    if prefix=='eyeliner':return {'left':{**basic,'open_eye':True}}
    if prefix=='eyelash':
        return {'left_upper':{'root_recipe':brush(),'extension_recipe':brush(),
            'visible':True,'unoccluded':True,'ownership_confirmed':True,'open_eye':True}}
    if prefix=='brow_makeup':return {'left':{**basic,'forehead_recipe':brush(),'forehead_visible':True}}
    return {side:{'iris':[[.2,.2],[.4,.2],[.3,.4]],
        'pupil':[[.25,.25],[.3,.25],[.28,.3]],'highlights':[],'confirmed':True}
        for side in ('left','right')}


def reviewed(monkeypatch,family):
    module,support,prefix=family
    engine,state,context,owned,rgb=fixture(monkeypatch)
    state,assets=support.retain(state,{},context['target']['face_ref'],regions(prefix))
    engine._people_support=assets
    return engine,state,context,owned,assets


def active(module):
    recipe=module.neutral()
    if module in (E,W):
        for side in ('left','right'):recipe[side]['strength']=.25
    elif module is H:
        for side in H.PARTS:recipe[side]['strength']=.25
    else:recipe['strength']=.25
    return module.check(recipe)


@pytest.mark.parametrize('module,support,prefix',FAMILIES)
def test_every_catalogue_pattern_is_admitted(monkeypatch,module,support,prefix):
    engine,_,context,_,_=fixture(monkeypatch)
    part='left_upper' if module is H else 'left' if module in (E,W) else None
    path='/pattern' if part is None else '/'+part+'/pattern'
    for value in module.PATTERNS:
        command=patch(context,module.OP,path,value)
        assert C.is_local_command('people',command)
        C.require_command(engine,'people',command)
    for value in ('invented-pattern',None,False):
        assert not C.is_local_command('people',patch(context,module.OP,path,value))


@pytest.mark.parametrize('texture',L.TEXTURES)
def test_all_lipstick_textures(monkeypatch,texture):
    _,_,context,_,_=fixture(monkeypatch)
    assert C.is_local_command('people',patch(context,L.OP,'/texture',texture))


@pytest.mark.parametrize('module',[E,H,W])
def test_linked_recipe_is_staged_atomically(monkeypatch,module):
    from lumaretouch_engine.people_edit import stage
    engine,state,context,owned,_=fixture(monkeypatch)
    command={**context,'cmd':'people','request_id':'linked','action':'patch',
        'payload':{'patches':module.patches(active(module))}}
    C.require_command(engine,'people',command)
    envelope={k:v for k,v in command.items() if k!='cmd'}
    kwargs=dict(document_id='doc',document_epoch='epoch',document_revision=0,
        asset_sha256=owned['sha256'],source_dimensions=(4,4))
    result=stage(envelope,state,**kwargs)
    C.require_graph(result['state'],owned)
    bad=deepcopy(envelope)
    first=next(p for p in bad['payload']['patches'] if p['parameter_path'].endswith('/strength'))
    first['value']=.5
    with pytest.raises(ValueError):stage(bad,state,**kwargs)
    assert state['overrides']==[]


@pytest.mark.parametrize('module,support,prefix',FAMILIES)
def test_reference_review_actions_keep_source_and_analysis_fences(monkeypatch,module,support,prefix):
    engine,_,context,_,_=fixture(monkeypatch)
    field,_,_=M.REVIEWS[prefix]
    for suffix,payload in (('_reference',{}),('_review',{field:regions(prefix)})):
        command={**context,'cmd':'people','request_id':'review','action':prefix+suffix,'payload':payload}
        C.require_command(engine,'people',command)
        shared=deepcopy(command);shared['target']={'scope':'person','target_id':'person','face_ref':None}
        assert not C.is_local_command('people',shared)
        bad=deepcopy(command);bad['payload']['source_path']='/original.jpg'
        assert not C.is_local_command('people',bad)
        engine._precompute.input_source_binding['sha256']='f'*64
        with pytest.raises(ValueError):C.require_command(engine,'people',command)
        engine._precompute.input_source_binding['sha256']=context['target']['face_ref']['asset_sha256']


@pytest.mark.parametrize('prefix',sorted(M.PALETTES))
def test_palette_accepts_only_bounded_colour_intent(monkeypatch,prefix):
    engine,_,context,_,_=fixture(monkeypatch)
    command={**context,'cmd':'people','request_id':'colour','action':prefix+'_palette',
        'payload':{'action':'save','colour':'#12ABEF'}}
    C.require_command(engine,'people',command)
    for payload in ({'action':'load','colour':'#12ABEF'}, {'action':'save','colour':'red'},
                    {'action':'save','colour':'#12ABEF','source_path':'/original.jpg'}):
        assert not C.is_local_command('people',{**command,'payload':payload})


@pytest.mark.parametrize('family',FAMILIES)
@pytest.mark.parametrize('change',[
    lambda r:r['source'].update(sha256='f'*64),
    lambda r:r['source'].update(width=8),
    lambda r:r['face_ref'].update(analysis_revision=999),
    lambda r:r['row'].update(landmark_digest='f'*64),
])
def test_each_support_rejects_foreign_source_face_extent_and_landmarks(monkeypatch,family,change):
    _,state,context,owned,assets=reviewed(monkeypatch,family)
    C.require_graph(state,owned);M.validate_supports(state,assets,owned['sha256'])
    changed=deepcopy(assets);change(next(iter(changed.values())))
    with pytest.raises(ValueError):M.validate_supports(state,changed,owned['sha256'])
    with pytest.raises(ValueError):M.validate_supports(state,{},owned['sha256'])


@pytest.mark.parametrize('family',FAMILIES)
def test_preview_forwards_owned_bank_and_checks_neutral_disabled_reviews(monkeypatch,family):
    from lumaretouch_engine.people_owned_inputs import preview
    engine,state,context,owned,assets=reviewed(monkeypatch,family)
    state['faces'][context['target']['target_id']]['enabled']=False
    inputs=preview(engine,state)
    for name in M.input_banks(assets):assert inputs[name] is assets
    next(iter(assets.values()))['row']['landmark_digest']='f'*64
    with pytest.raises(ValueError):preview(engine,state)


@pytest.mark.parametrize('family',FAMILIES)
@pytest.mark.parametrize('refuse',[False,True])
def test_actual_runtime_consumer_receives_owned_source_analysis_and_review(monkeypatch,family,refuse):
    from lumaretouch_engine import people_render_runtime as R, people_effects as PE
    from lumaretouch_engine import lipstick_layer as LL, blush_makeup_layer as BL
    from lumaretouch_engine import eyeliner_people as EP, eyelash_people as HP
    from lumaretouch_engine import brow_makeup_people as WP, iris_makeup_people as IP
    from lumaretouch_engine import hair_colour_runtime as HAIR
    module,support,prefix=family
    engine,state,context,owned,assets=reviewed(monkeypatch,family)
    ref=context['target']['face_ref'];key=ref['face_instance_id']
    # Full recipe values are intentional: every linked part receives same amount.
    for path,value in A.leaves(active(module)).items():state=S.set_override(state,'face',key,module.OP,path,value)
    excluded=np.zeros((4,4),np.float32);skin=np.ones((4,4),np.float32)
    analysis={'face_ref':ref,'evidence':state['faces'][key]['evidence'],
        'landmarks':engine._precompute.landmarks,'excluded':excluded,'skin':skin}
    rgb=np.full((4,4,3),np.float32(.500013),np.float32);calls=[]
    monkeypatch.setattr(R.A,'build_geometry',lambda *a,**k:SimpleNamespace(fields=[None],resident_bytes=lambda:0))
    monkeypatch.setattr(R,'combine',lambda *a,**k:SimpleNamespace())
    def forbidden(*a,**k):raise AssertionError('Unadapted original-path hair consumer')
    monkeypatch.setattr(HAIR,'prepare_bank',forbidden)
    if module in (L,B):
        review=np.full((4,4),.75,np.float32)
        def raster(graph,bank,target,shape):
            assert bank is assets and target==ref and shape==(4,4)
            return review
        monkeypatch.setattr(support,'raster',raster)
        def consume(target,lm,recipe,pixels,**kwargs):
            assert target==ref and pixels is rgb and kwargs['excluded'] is excluded
            assert kwargs['reviewed'] is review and kwargs['semantic_sha']=='2'*64
            if module is B:assert kwargs['skin'] is skin
            calls.append(target)
            if refuse:raise RuntimeError('Requested makeup native solver unavailable')
            return None
        monkeypatch.setattr(LL if module is L else BL,'prepare_record',consume)
    else:
        port={E:EP,H:HP,W:WP,I:IP}[module]
        def consume(graph,bank,target,measured,pixels,recipe,**kwargs):
            assert bank is assets and target==ref and measured is analysis and pixels is rgb
            calls.append(target)
            if refuse:raise RuntimeError('Requested makeup native solver unavailable')
            return []
        monkeypatch.setattr(port,'prepare',consume)
    args=(state,owned['sha256'],rgb,{key:analysis})
    kwargs=dict(byte_budget=256*1024**2,creative_source=owned,**M.input_banks(assets))
    if refuse:
        with pytest.raises(R.PeoplePreparationRefused,match='native solver'):R.prepare(*args,**kwargs)
    else:assert R.prepare(*args,**kwargs).effects==()
    assert calls==[ref]


@pytest.mark.parametrize('module',[L,B])
def test_lip_and_cheek_review_does_not_replace_measured_semantics(monkeypatch,module):
    from lumaretouch_engine import lipstick_layer as LL, blush_makeup_layer as BL
    engine,_,context,_,_=fixture(monkeypatch)
    target=context['target']['face_ref'];pixels=np.full((4,4,3),.5,np.float32)
    port=LL if module is L else BL
    # Isolate the semantic admission check from unrelated geometry validation.
    monkeypatch.setattr(port,'identity',lambda _:None)
    kwargs=dict(excluded=None,backend='mediapipe',semantic_sha='2'*64,
        reviewed=np.ones((4,4),np.float32))
    if module is B:kwargs['skin']=np.ones((4,4),np.float32)
    with pytest.raises(ValueError):port.prepare_record(target,engine._precompute.landmarks,active(module),pixels,**kwargs)
    kwargs['excluded']=np.zeros((4,4),np.float32);kwargs['semantic_sha']=None
    with pytest.raises(ValueError):port.prepare_record(target,engine._precompute.landmarks,active(module),pixels,**kwargs)


@pytest.mark.parametrize('family',[FAMILIES[2],FAMILIES[3],FAMILIES[4],FAMILIES[5]])
def test_other_makeup_review_never_invents_missing_occlusion(monkeypatch,family):
    from lumaretouch_engine import eyeliner_people as EP, eyelash_people as HP
    from lumaretouch_engine import brow_makeup_people as WP, iris_makeup_people as IP
    module,support,_=family
    engine,state,context,_,assets=reviewed(monkeypatch,family)
    ref=context['target']['face_ref'];key=ref['face_instance_id']
    analysis={'face_ref':ref,'evidence':state['faces'][key]['evidence'],
        'landmarks':engine._precompute.landmarks,'excluded':None,'skin':None}
    pixels=np.full((4,4,3),.5,np.float32)
    port={E:EP,H:HP,W:WP,I:IP}[module]
    kwargs={} if module is I else {'source_revision':state['revision']}
    if module is not I:
        # Do not invoke the native vector rasterizer while checking the later
        # independent measured-occlusion requirement.
        monkeypatch.setattr(support,'raster',lambda *a,**k:{})
    with pytest.raises(ValueError,match='遮挡'):
        port.prepare(state,assets,ref,analysis,pixels,active(module),**kwargs)
