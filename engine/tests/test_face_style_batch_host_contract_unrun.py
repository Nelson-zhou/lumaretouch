# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: named face-style batch host and terminal retry fences.

Synthetic protocol contracts only, not image-quality acceptance. No imports,
collection, tests, builds, typechecks, inference or downloads ran in authoring.
"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lumaretouch_engine import batch_preflight as B
from lumaretouch_engine import face_style_batch_review as R
from lumaretouch_engine import project_recovery_runtime as RECOVERY
from lumaretouch_engine import history_policy as HISTORY
from lumaretouch_engine.batch_preflight_controller import FrozenBatchController
from lumaretouch_engine.creative_document_host import guard_command
from lumaretouch_engine.creative_transfer_host import face_style_image_read_only, face_style_preflight_read_only, require_route

ENGINE=Path(__file__).parents[1]/'src/lumaretouch_engine'


def fixture(count=2):
    value={'version':1,'style':'classic','amount':.5}
    options={'face_style':value,'target_policy':'explicit_face_map','selection':R.selection(value)}
    proof={'original_sha256':'a'*64,'asset_sha256':'a'*64,'creative_source':None}
    targets=[];records=[]
    for index in range(count):
        document='target-'+str(index)
        record={'version':1,'document_id':document,'revision':'3','source_proof':deepcopy(proof),
            'before_state_sha256':'b'*64,'candidate_state_sha256':'b'*64,
            'before_people_sha256':'c'*64,'candidate_people_sha256':'d'*64,
            'source_size':[1,1],'before_output_size':[1,1],'after_output_size':[1,1],
            'before':{'mime':'image/png','width':1,'height':1,'sha256':'e'*64},
            'after':{'mime':'image/png','width':1,'height':1,'sha256':'f'*64},
            'recipe_sha256':R.recipe_digest(value)}
        records.append(record)
        targets.append(B.FrozenTarget(document,3,index,'/target-'+str(index),None,
            B.canonical({'source_proof':proof}),people_json=B.canonical({'face_style':deepcopy(value),
                'parameters':R.parameters(value),'face_style_visual':record})))
    store=B.PreflightStore(lambda:1)
    plan=store.create('workspace','source',2,'/source',list(options['selection']),
        {'_people_transfer':{'options':options}},'skip_and_report',targets,[])
    ack=[{'document_id':r['document_id'],'revision':r['revision'],
          'before_sha256':r['before']['sha256'],'after_sha256':r['after']['sha256'],
          'recipe_sha256':r['recipe_sha256']} for r in records]
    return store,plan,ack


def image_request():
    return {'cmd':'batch','action':'face_style_visual','request_id':'image-read',
        'preflight_token':'a'*32,'document_id':'target-0','revision':'3','side':'before','sha256':'e'*64}


def preflight_request():
    def proof(document,asset):
        return {'document':{'document_id':document,'epoch':'workspace','revision':3},'people_scope':'project',
            'state_revision':1,'association_revision':1,'graph_sha256':'c'*64,
            'source_proof':{'original_sha256':asset,'asset_sha256':asset,'creative_source':None}}
    def face(asset,identity):
        return {'asset_sha256':asset,'face_instance_id':identity,'analysis_revision':1}
    value={'version':1,'style':'classic','amount':.5};selected=R.selection(value)
    return {'cmd':'batch','action':'preflight','request_id':'named-review','docs':['2'*32],
        'module_scope':list(selected),'people_transfer':{'target_policy':'explicit_face_map',
            'face_style':value,'selection':selected,'source_ref':face('a'*64,'source-face'),
            'source':proof('1'*32,'a'*64),'targets':[{'target':proof('2'*32,'b'*64),
                'target_refs':[face('b'*64,'target-face')]}]}}


def controller(store):
    events=[]
    owner=FrozenBatchController(SimpleNamespace(people_transfer=Mock()),
        SimpleNamespace(workspace='workspace'),events.append,lambda:1)
    owner.store=store
    return owner,events


def test_claim_ack_is_exact_and_missing_ack_keeps_plan_usable():
    store,plan,ack=fixture()
    with pytest.raises(ValueError):store.claim(plan,request_id='commit')
    assert store.pending[plan.token] is plan and not store.terminal
    store.claim(plan,face_style_review_ack=ack,request_id='commit')
    receipt=store.completed(plan.token,'workspace')
    assert plan.token not in store.pending and receipt['outcome_unknown']
    assert receipt['face_style_review_ack']==ack and receipt['module_scope']==list(plan.modules)
    ack[0]['before_sha256']='0'*64
    assert store.completed(plan.token,'workspace')['face_style_review_ack'][0]['before_sha256']=='e'*64


@pytest.mark.parametrize('field,value',[
    ('document_id','other'),('revision','4'),('before_sha256','0'*64),
    ('after_sha256','0'*64),('recipe_sha256','0'*64),('coverage_sha256','0'*64),
])
def test_each_foreign_ack_field_is_rejected_without_consumption(field,value):
    store,plan,ack=fixture();ack[0][field]=value
    with pytest.raises(ValueError):store.claim(plan,face_style_review_ack=ack)
    assert store.pending[plan.token] is plan and not store.terminal


@pytest.mark.parametrize('fault',['reverse','duplicate','missing','extra','not-list'])
def test_ack_requires_every_eligible_target_once_in_frozen_order(fault):
    store,plan,ack=fixture()
    if fault=='reverse':ack.reverse()
    elif fault=='duplicate':ack[1]=deepcopy(ack[0])
    elif fault=='missing':ack.pop()
    elif fault=='extra':ack.append(deepcopy(ack[-1]))
    else:ack=tuple(ack)
    with pytest.raises(ValueError):store.claim(plan,face_style_review_ack=ack)
    assert store.pending[plan.token] is plan and not store.terminal


@pytest.mark.parametrize('foreign',['spill_review_ack','shadow_review_ack','torso_review_ack',
    'waist_review_ack','head_review_ack','collarbone_review_ack'])
def test_face_style_claim_rejects_other_family_ack(foreign):
    store,plan,ack=fixture()
    with pytest.raises(ValueError):store.claim(plan,face_style_review_ack=ack,**{foreign:[]})
    assert plan.token in store.pending


def test_generic_claim_and_controller_cannot_use_face_style_ack_as_bypass():
    store=B.PreflightStore(lambda:1)
    plan=store.create('workspace','source',1,'/source',['ev'],{'ev':{'value':1}},
        'skip_and_report',[B.FrozenTarget('target',2,0,'/target',None,'{}')],[])
    with pytest.raises(ValueError):store.claim(plan,face_style_review_ack=[])
    owner,events=controller(store)
    owner.handle({'cmd':'batch','action':'commit','request_id':'commit',
                  'preflight_token':plan.token,'face_style_review_ack':[]})
    owner.ports.people_transfer.assert_not_called()
    assert plan.token in store.pending and not store.terminal
    assert events[-1]['success'] is False and events[-1]['outcome_unknown'] is False


def test_finish_and_query_retain_exact_claim_ack_when_terminal_payload_omits_it():
    store,plan,ack=fixture();store.claim(plan,face_style_review_ack=ack,request_id='original')
    result=store.finish(plan,{'success':True,'outcome_unknown':False,'preflight_token':plan.token})
    assert result['face_style_review_ack']==ack and result['module_scope']==list(plan.modules)
    assert result['request_id']=='original'
    queried=store.completed(plan.token,'workspace');queried['face_style_review_ack'].clear()
    assert store.completed(plan.token,'workspace')['face_style_review_ack']==ack


@pytest.mark.parametrize('field',['face_style_review_ack','module_scope'])
def test_finish_refuses_changed_frozen_receipt_fields(field):
    store,plan,ack=fixture();store.claim(plan,face_style_review_ack=ack,request_id='original')
    before=store.completed(plan.token,'workspace')
    with pytest.raises(ValueError):store.finish(plan,{'success':True,field:[]})
    assert store.completed(plan.token,'workspace')==before and plan.token not in store.pending


def test_overflow_unknown_receipt_preserves_recipe_ack_scope_and_original_request(monkeypatch):
    store,plan,ack=fixture();store.claim(plan,face_style_review_ack=ack,request_id='original')
    monkeypatch.setattr(B,'MAX_RESULT_BYTES',1)
    result=store.finish(plan,{'success':True,'huge':object()})
    assert result['success'] is False and result['outcome_unknown'] is True
    assert result['face_style_review_ack']==ack and result['module_scope']==list(plan.modules)
    assert result['request_id']=='original' and plan.token not in store.pending


def test_replay_is_exact_correlated_readback_and_never_dispatches_people_write():
    store,plan,ack=fixture();store.claim(plan,face_style_review_ack=ack,request_id='original')
    store.finish(plan,{'success':True,'outcome_unknown':False,'preflight_token':plan.token})
    owner,events=controller(store)
    request={'cmd':'batch','action':'commit','request_id':'readback',
             'preflight_token':plan.token,'face_style_review_ack':ack}
    assert owner.replay_completed(request)
    owner.ports.people_transfer.assert_not_called()
    assert events[-1]['replayed'] and events[-1]['request_id']=='readback'
    assert events[-1]['face_style_review_ack']==ack and events[-1]['module_scope']==list(plan.modules)
    assert store.completed(plan.token,'workspace')['request_id']=='original'
    for bad in (None,[],list(reversed(ack))):
        with pytest.raises(ValueError):owner.replay_completed({**request,'face_style_review_ack':bad})


@pytest.mark.parametrize('fault',['policy','selection','scope','scope-order','recipe','missing-visual',
    'wrong-document','wrong-revision','wrong-recipe','wrong-source','duplicate-target','too-many'])
def test_frozen_marker_requires_actual_exact_scope_and_full_target_records(fault):
    _,plan,_=fixture();params=plan.params();targets=list(plan.targets);modules=plan.modules
    options=params['_people_transfer']['options']
    if fault=='policy':options['target_policy']='confirmed_person_only'
    elif fault=='selection':options['selection'].pop(next(iter(options['selection'])))
    elif fault=='scope':modules=modules[:-1]
    elif fault=='scope-order':modules=tuple(reversed(modules))
    elif fault=='recipe':options['face_style']['amount']=True
    elif fault=='duplicate-target':targets[1]=targets[0]
    elif fault=='too-many':targets=targets*9
    else:
        payload=json.loads(targets[0].people_json);visual=payload['face_style_visual']
        if fault=='missing-visual':payload.pop('face_style_visual')
        elif fault=='wrong-document':visual['document_id']='other'
        elif fault=='wrong-revision':visual['revision']='4'
        elif fault=='wrong-recipe':visual['recipe_sha256']='0'*64
        else:visual['source_proof']={'original_sha256':'0'*64,'asset_sha256':'0'*64,'creative_source':None}
        targets[0]=replace(targets[0],people_json=B.canonical(payload))
    bad=replace(plan,params_json=B.canonical(params),modules=modules,targets=tuple(targets))
    with pytest.raises(ValueError):B.face_style_records(bad)


def test_blocked_target_has_no_invented_ack_or_visual():
    store,plan,ack=fixture();targets=list(plan.targets)
    targets[1]=replace(targets[1],blocked='disabled face',people_json=None)
    plan=replace(plan,targets=tuple(targets));store.pending[plan.token]=plan
    store.claim(plan,face_style_review_ack=ack[:1])
    assert store.completed(plan.token,'workspace')['face_style_review_ack']==ack[:1]


@pytest.mark.parametrize('fault',['recipe','missing-recipe','missing-parameters','missing-leaf',
    'duplicate-leaf','changed-value','boolean-type','leaf-order'])
def test_target_recipe_and_typed_parameters_cannot_diverge_from_frozen_style(fault):
    store,plan,ack=fixture();targets=list(plan.targets);payload=json.loads(targets[0].people_json)
    if fault=='recipe':payload['face_style']['style']='bold'
    elif fault=='missing-recipe':payload.pop('face_style')
    elif fault=='missing-parameters':payload.pop('parameters')
    elif fault=='missing-leaf':payload['parameters'].pop()
    elif fault=='duplicate-leaf':payload['parameters'].append(deepcopy(payload['parameters'][0]))
    elif fault=='changed-value':
        next(item for item in payload['parameters'] if type(item['value']) is float)['value']=.9
    elif fault=='boolean-type':
        leaf=next(item for item in payload['parameters'] if type(item['value']) is bool)
        leaf['value']=int(leaf['value'])  # Python equality alone would admit True == 1.
    else:payload['parameters'].reverse()
    targets[0]=replace(targets[0],people_json=B.canonical(payload))
    changed=replace(plan,targets=tuple(targets));store.pending[plan.token]=changed
    with pytest.raises(ValueError):store.claim(changed,face_style_review_ack=ack)
    assert store.pending[plan.token] is changed and not store.terminal


@pytest.mark.parametrize('field,value',[
    ('cmd','preset'),('action','commit'),('preflight_token','x'*32),('document_id',''),
    ('request_id',''),('revision','03'),('revision',str(2**64)),('side','mask'),
    ('sha256','F'*64),('face_style_review_ack',[]),('people_transfer',{}),('amount',.5),
])
def test_image_read_exemption_is_exact_and_cannot_admit_mutation(field,value):
    assert face_style_image_read_only(image_request())
    assert not face_style_image_read_only({**image_request(),field:value})


def test_derived_image_read_does_not_reinterpret_any_original_graph():
    request=image_request();prior=deepcopy(request)
    engine=SimpleNamespace(_creative_base={'synthetic':True},_docs=[])
    require_route('batch',request);guard_command(engine,'batch',request)
    assert request==prior
    for extra in ({'module_scope':['lnx.head_size.v1']},{'docs':['other']},{'face_style_review_ack':[]}):
        with pytest.raises(ValueError):require_route('batch',{**request,**extra})


def test_derived_commit_is_not_a_read_exemption_and_accepts_only_one_exact_ack_kind():
    request={'cmd':'batch','action':'commit','request_id':'commit','preflight_token':'a'*32,
             'face_style_review_ack':[]}
    require_route('batch',request)
    assert not face_style_image_read_only(request)
    for extra in ({'head_review_ack':[]},{'collarbone_review_ack':[]},{'module_scope':[]},
                  {'people_transfer':{}},{'amount':.5}):
        with pytest.raises(ValueError):require_route('batch',{**request,**extra})


@pytest.mark.parametrize('failed',[False,True])
@pytest.mark.parametrize('tainted',[False,True])
def test_cached_read_never_advances_recovery_or_clears_existing_taint(failed,tainted):
    runtime=SimpleNamespace(revision=9,tainted=tainted,reason='existing reason')
    engine=SimpleNamespace(_project_recovery_runtime=runtime,EDIT_CMDS={'batch'})
    RECOVERY.finish(engine,{'message':image_request(),'started':True,'returned':not failed,'failed':failed},
                    'synthetic read failure' if failed else None)
    assert vars(runtime)=={'revision':9,'tainted':tainted,'reason':'existing reason'}


def test_face_style_commits_remain_recovery_mutations_and_separate_history_groups():
    request={'cmd':'batch','action':'commit','request_id':'commit-a',
             'preflight_token':'a'*32,'face_style_review_ack':[]}
    runtime=SimpleNamespace(revision=9,tainted=False,reason=None)
    engine=SimpleNamespace(_project_recovery_runtime=runtime,EDIT_CMDS={'batch'})
    RECOVERY.finish(engine,{'message':request,'started':True,'returned':True,'failed':False})
    assert runtime.revision==10 and not runtime.tainted
    assert HISTORY.command_group('batch',request)!=HISTORY.command_group('batch',
        {**request,'preflight_token':'b'*32,'request_id':'commit-b'})


def test_dispatch_preserves_all_guards_before_read_and_all_capture_owners_after_read():
    source=(ENGINE/'server.py').read_text();body=source[source.index('    def _process_line('):]
    for predicate in ('face_style_image_read_only','face_style_preflight_read_only'):
        read=body.index('if '+predicate+'(msg):')
        for guard in ('recovery.host.blocks','managed.blocks','package.blocks','CDH.guard_command','relocation.blocks'):
            assert body.index(guard)<read
        for mutation in ('invalidate_other(self,name,msg)','self._arm_before_command(msg)',
                         'self._cancel_snapshot(', 'before = self._history_capture()'):
            assert read<body.index(mutation)
    sync=(ENGINE/'batch_sync.py').read_text()
    assert sync.index('if action == "face_style_visual":')<sync.index('why = self.editor.guard')
    assert 'from .face_style_batch_store import retrieve' in sync
    assert len(source.splitlines())<=7065


def test_cleanup_uses_separate_face_style_image_namespace_for_claim_and_expiry():
    for name in ('batch_preflight.py','batch_preflight_controller.py'):
        source=(ENGINE/name).read_text()
        assert 'from .face_style_batch_store import prune as prune_face_style' in source
    source=(ENGINE/'batch_preflight_controller.py').read_text()
    handle=source.split('    def handle(self,p):',1)[1]
    assert handle.index("acknowledgments(p.get('face_style_review_ack'),face_records)")<handle.index("self.ports.people_transfer(self,p,reviewed)")


def test_named_preflight_predicate_only_reads_exact_detached_metadata():
    request=preflight_request();before=deepcopy(request)
    assert face_style_preflight_read_only(request) and request==before
    require_route('batch',request)
    assert face_style_preflight_read_only({**request,'conflict_policy':'recheck'})
    assert not face_style_image_read_only(request)


@pytest.mark.parametrize('fault',['generic','commit','token','ack','extra','empty-id','long-id',
    'scope','scope-order','recipe','selection','source-proof','source-face','target-proof',
    'epoch','face-source','duplicate-face','duplicate-doc','missing-doc','other-doc','unsafe-revision'])
def test_named_preflight_exemption_does_not_admit_generic_or_malformed_requests(fault):
    request=preflight_request();people=request['people_transfer'];target=people['targets'][0]
    if fault=='generic':people.pop('face_style')
    elif fault=='commit':request['action']='commit'
    elif fault=='token':request['preflight_token']='a'*32
    elif fault=='ack':request['face_style_review_ack']=[]
    elif fault=='extra':request['replacement_graph']={}
    elif fault=='empty-id':request['request_id']=''
    elif fault=='long-id':request['request_id']='女'*64
    elif fault=='scope':request['module_scope'].pop()
    elif fault=='scope-order':request['module_scope'].reverse()
    elif fault=='recipe':people['face_style']['amount']=True
    elif fault=='selection':people['selection'].pop(next(iter(people['selection'])))
    elif fault=='source-proof':people['source']['graph_sha256']='not-a-digest'
    elif fault=='source-face':people['source_ref']['asset_sha256']='0'*64
    elif fault=='target-proof':target['target']['document']['document_id']='1'*32
    elif fault=='epoch':target['target']['document']['epoch']='another-workspace'
    elif fault=='face-source':target['target_refs'][0]['asset_sha256']='a'*64
    elif fault=='duplicate-face':target['target_refs'].append(deepcopy(target['target_refs'][0]))
    elif fault=='duplicate-doc':request['docs'].append(request['docs'][0])
    elif fault=='missing-doc':request['docs']=[]
    elif fault=='other-doc':request['docs']=['3'*32]
    else:target['target']['document']['revision']=2**53
    assert not face_style_preflight_read_only(request)


@pytest.mark.parametrize('failed',[False,True])
@pytest.mark.parametrize('tainted',[False,True])
def test_exact_named_review_keeps_recovery_revision_and_existing_taint(failed,tainted):
    runtime=SimpleNamespace(revision=9,tainted=tainted,reason='existing reason')
    engine=SimpleNamespace(_project_recovery_runtime=runtime,EDIT_CMDS={'batch'})
    RECOVERY.finish(engine,{'message':preflight_request(),'started':True,'returned':not failed,'failed':failed},
                    'synthetic review failure' if failed else None)
    assert vars(runtime)=={'revision':9,'tainted':tainted,'reason':'existing reason'}


def test_generic_people_preflight_failure_is_not_reclassified_as_safe_named_review():
    request=preflight_request();request['people_transfer'].pop('face_style')
    runtime=SimpleNamespace(revision=9,tainted=False,reason=None)
    engine=SimpleNamespace(_project_recovery_runtime=runtime,EDIT_CMDS={'batch'})
    RECOVERY.finish(engine,{'message':request,'started':True,'returned':False,'failed':True},'failure')
    assert runtime.tainted and runtime.revision==9
