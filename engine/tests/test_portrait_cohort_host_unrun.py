# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: persistent full-portrait host, claims and replay contracts.

Synthetic endpoint/render digests only; no photo acceptance or runtime claim.
No imports, test collection, execution, build, typecheck or inference was run
while authoring. Actual full-source rendering and rollback still need execution.
"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lumaretouch_engine import batch_preflight as B
from lumaretouch_engine import face_style_batch_review as STYLE
from lumaretouch_engine import people_cross_owner as CROSS
from lumaretouch_engine import portrait_cohort_review as REVIEW
from lumaretouch_engine import project_recovery_runtime as RECOVERY
from lumaretouch_engine import history_policy as HISTORY
from lumaretouch_engine.batch_preflight_controller import FrozenBatchController
from lumaretouch_engine.creative_document_host import guard_command
from lumaretouch_engine.creative_transfer_host import (
    portrait_cohort_image_read_only, portrait_cohort_preflight_read_only, require_route)

ENGINE=Path(__file__).parents[1]/'src/lumaretouch_engine'
RECIPE={'version':1,'style':'classic','amount':.5}


def fixture(count=2,*,named=True,operation='create',collarbone=False):
    endpoints=[];refs=[];members=[]
    for index in range(count):
        document=f'{index+1:032x}';asset=f'{index+1:064x}'
        proof={'document':{'document_id':document,'epoch':'workspace','revision':3},
            'people_scope':document,'state_revision':1,'association_revision':1,'graph_sha256':'a'*64,
            'source_proof':{'original_sha256':asset,'asset_sha256':asset,'creative_source':None}}
        ref={'asset_sha256':asset,'face_instance_id':'face-'+str(index),'analysis_revision':1}
        endpoints.append(proof);refs.append(ref)
        members.append({'document_id':document,'scope_id':document,'original_sha256':asset,'ref':ref})
    selected={'target_policy':'persistent_association','operation':operation,'association_id':'association',
        'source_ref':refs[0],'source':endpoints[0],
        'selection':STYLE.selection(RECIPE) if named else ({} if operation=='unlink' else {'lnx.face_size.v1':['/amount']}),
        'targets':[{'target':proof,'target_refs':[ref]} for proof,ref in zip(endpoints[1:],refs[1:])]}
    if named:selected['face_style']=deepcopy(RECIPE)
    intent=[{'op':leaf['operation_id'],'path':leaf['parameter_path'],'value':leaf['value']}
            for leaf in STYLE.parameters(RECIPE)]
    capsule=CROSS.descriptor('association',endpoints[0]['document']['document_id'],members,intent)
    review={key:value for key,value in capsule.items() if key!='local_document_id'}|{'operation':operation}
    digest=REVIEW.digest(selected,review);targets=[];records=[];collarbone_ack=[]
    for index,(proof,ref) in enumerate(zip(endpoints,refs)):
        document=proof['document']['document_id']
        record={'version':1,'document_id':document,'revision':'3','source_proof':proof['source_proof'],
            'before_state_sha256':'b'*64,'candidate_state_sha256':'b'*64,
            'before_people_sha256':'c'*64,'candidate_people_sha256':'d'*64,
            'source_size':[1,1],'before_output_size':[1,1],'after_output_size':[1,1],
            'before':{'mime':'image/png','width':1,'height':1,'sha256':'e'*64},
            'after':{'mime':'image/png','width':1,'height':1,'sha256':'f'*64},'cohort_sha256':digest}
        snapshots={side:{key:'9'*64 for key in ('render_sha256','context_sha256','graph_sha256')}
                   for side in ('before','after')}
        payload={'ref':ref,'person_id':'association','candidate_sha256':'d'*64,
                 'portrait_visual':record,'portrait_snapshots':snapshots,
                 'eye_bag_cohort_state':{side:{'version':2,'amount':0,'preserve':1} for side in ('before','after')}}
        if collarbone:
            payload['collarbone_visual']={key:value for key,value in record.items() if key!='cohort_sha256'}|{'coverage_sha256':'8'*64}
            collarbone_ack.append({'document_id':document,'revision':'3','before_sha256':'e'*64,
                                  'after_sha256':'f'*64,'coverage_sha256':'8'*64})
        records.append(record)
        targets.append(B.FrozenTarget(document,3,index,'/photo-'+str(index),None,
                                      B.canonical(proof),people_json=B.canonical(payload)))
    params={'_people_transfer':{'mode':'persistent_association','options':selected,'review':review,
            'portrait_cohort_required':True,'collarbone_visual_required':collarbone,'eye_bag_cohort_required':False}}
    store=B.PreflightStore(lambda:1)
    plan=store.create('workspace',targets[0].document_id,3,targets[0].path,
                      list(selected['selection']),params,'recheck',targets,[])
    ack=[{'document_id':r['document_id'],'revision':r['revision'],'before_sha256':r['before']['sha256'],
          'after_sha256':r['after']['sha256'],'cohort_sha256':r['cohort_sha256']} for r in records]
    return store,plan,ack,collarbone_ack


def controller(store):
    events=[]
    owner=FrozenBatchController(SimpleNamespace(people_transfer=Mock()),
                               SimpleNamespace(workspace='workspace'),events.append,lambda:1)
    owner.store=store
    return owner,events


def commit_request(plan,ack,**extra):
    return {'cmd':'batch','action':'commit','request_id':'commit','preflight_token':plan.token,
            'module_scope':list(plan.modules),'portrait_cohort_ack':deepcopy(ack),**extra}


def preflight_request():
    _,plan,_,_=fixture();selected=plan.params()['_people_transfer']['options']
    return {'cmd':'batch','action':'preflight','request_id':'review','module_scope':list(plan.modules),
            'conflict_policy':'recheck','docs':[item['target']['document']['document_id'] for item in selected['targets']],
            'people_transfer':selected}


def image_request():
    return {'cmd':'batch','action':'portrait_cohort_visual','request_id':'read','preflight_token':'a'*32,
            'document_id':'1'*32,'revision':'3','side':'before','sha256':'e'*64}


def mutate_payload(plan,index,change):
    targets=list(plan.targets);payload=json.loads(targets[index].people_json);change(payload)
    targets[index]=replace(targets[index],people_json=B.canonical(payload))
    return replace(plan,targets=tuple(targets))


@pytest.mark.parametrize('count',[2,16])
def test_actual_full_cohort_requires_every_member_source_first(count):
    _,plan,ack,_=fixture(count)
    records=B.portrait_cohort_records(plan)
    assert len(records)==count and records[0]['document_id']==plan.source_id
    assert REVIEW.acknowledgments(ack,records)==ack
    assert B.face_style_records(plan) is None  # A persistent recipe is not a target-only copy.


@pytest.mark.parametrize('operation',['patch','unlink'])
def test_generic_lifecycle_keeps_complete_review_without_inventing_named_recipe(operation):
    store,plan,ack,_=fixture(named=False,operation=operation)
    assert 'face_style' not in plan.params()['_people_transfer']['options']
    assert len(B.portrait_cohort_records(plan))==2
    store.claim(plan,portrait_cohort_ack=ack,request_id='commit')
    receipt=store.completed(plan.token,'workspace')
    assert receipt['portrait_cohort'] is True and receipt['portrait_cohort_ack']==ack
    assert receipt['module_scope']==([] if operation=='unlink' else ['lnx.face_size.v1'])


@pytest.mark.parametrize('fault',['missing','false','integer','string','wrong-mode','missing-review','partial-intent'])
def test_marker_cannot_replace_actual_complete_intent_or_persistent_ownership(fault):
    _,plan,_,_=fixture();params=plan.params();marker=params['_people_transfer']
    if fault=='missing':marker.pop('portrait_cohort_required')
    elif fault=='false':marker['portrait_cohort_required']=False
    elif fault=='integer':marker['portrait_cohort_required']=1
    elif fault=='string':marker['portrait_cohort_required']='true'
    elif fault=='wrong-mode':marker['mode']='explicit_face_map'
    elif fault=='missing-review':marker.pop('review')
    else:marker['review']['intent'].pop()
    with pytest.raises(ValueError):B.portrait_cohort_records(replace(plan,params_json=B.canonical(params)))


def test_named_request_cannot_hide_partial_intent_with_a_false_cohort_marker():
    _,plan,_,_=fixture();params=plan.params();marker=params['_people_transfer']
    marker['portrait_cohort_required']=False;marker['review']['intent'].pop()
    with pytest.raises(ValueError):B.portrait_cohort_records(replace(plan,params_json=B.canonical(params)))


@pytest.mark.parametrize('fault',['empty','only-source','omit-source','reverse','duplicate','blocked','empty-blocked',
    'source-id','source-revision','source-path','policy','rejected','too-many'])
def test_atomic_cohort_cannot_omit_skip_reorder_or_rebase_any_member(fault):
    _,plan,_,_=fixture();changes={}
    if fault=='empty':changes['targets']=()
    elif fault=='only-source':changes['targets']=plan.targets[:1]
    elif fault=='omit-source':changes['targets']=plan.targets[1:]
    elif fault=='reverse':changes['targets']=tuple(reversed(plan.targets))
    elif fault=='duplicate':changes['targets']=(plan.targets[0],plan.targets[0])
    elif fault in ('blocked','empty-blocked'):
        changes['targets']=(plan.targets[0],replace(plan.targets[1],blocked='' if fault=='empty-blocked' else 'missing'))
    elif fault=='source-id':changes['source_id']='other'
    elif fault=='source-revision':changes['source_revision']=4
    elif fault=='source-path':changes['source_path']='/other'
    elif fault=='policy':changes['policy']='skip_and_report'
    elif fault=='rejected':changes['rejected_json']='[{"doc":"omitted"}]'
    else:changes['targets']=plan.targets*9
    with pytest.raises(ValueError):B.portrait_cohort_records(replace(plan,**changes))


@pytest.mark.parametrize('field,value',[('document_id','other'),('revision','4'),('cohort_sha256','0'*64),
    ('source_proof',{'original_sha256':'0'*64,'asset_sha256':'0'*64,'creative_source':None}),
    ('recipe_sha256','0'*64)])
def test_each_visual_must_match_exact_frozen_document_source_and_cohort(field,value):
    _,plan,_,_=fixture()
    bad=mutate_payload(plan,0,lambda payload:payload['portrait_visual'].update({field:value}))
    with pytest.raises(ValueError):B.portrait_cohort_records(bad)


@pytest.mark.parametrize('fault',['missing-visual','missing-snapshots','missing-side','extra-side','missing-hash',
    'extra-hash','invalid-hash','wrong-ref'])
def test_private_member_snapshot_proof_is_complete_and_separate_from_public_visual(fault):
    _,plan,_,_=fixture()
    def change(payload):
        if fault=='missing-visual':payload.pop('portrait_visual')
        elif fault=='missing-snapshots':payload.pop('portrait_snapshots')
        elif fault=='missing-side':payload['portrait_snapshots'].pop('after')
        elif fault=='extra-side':payload['portrait_snapshots']['third']={}
        elif fault=='missing-hash':payload['portrait_snapshots']['before'].pop('render_sha256')
        elif fault=='extra-hash':payload['portrait_snapshots']['before']['pixels']='not-proof'
        elif fault=='invalid-hash':payload['portrait_snapshots']['after']['context_sha256']='bad'
        else:payload['ref']['analysis_revision']=2
    with pytest.raises(ValueError):B.portrait_cohort_records(mutate_payload(plan,1,change))


def test_before_json_retains_original_full_endpoint_not_augmented_snapshot_fields():
    _,plan,_,_=fixture();target=plan.targets[0];before=json.loads(target.before_json)
    before['portrait_snapshots']={}
    with pytest.raises(ValueError):
        B.portrait_cohort_records(replace(plan,targets=(replace(target,before_json=B.canonical(before)),plan.targets[1])))


def test_named_scalar_intent_must_equal_locally_generated_typed_recipe_even_with_valid_generation():
    _,plan,_,_=fixture();params=plan.params();marker=params['_people_transfer'];review=marker['review']
    leaf=next(leaf for leaf in review['intent'] if type(leaf['value']) is float)
    leaf['value']=.123
    capsule=CROSS.descriptor(review['association_id'],plan.source_id,review['members'],review['intent'])
    review['generation']=capsule['generation']
    with pytest.raises(ValueError):B.portrait_cohort_records(replace(plan,params_json=B.canonical(params)))


@pytest.mark.parametrize('fault',['missing','reverse','omit-source','duplicate','extra','wrong-digest','wrong-revision','recipe-field'])
def test_bad_ack_never_consumes_the_usable_review(fault):
    store,plan,ack,_=fixture()
    if fault=='missing':ack=None
    elif fault=='reverse':ack.reverse()
    elif fault=='omit-source':ack.pop(0)
    elif fault=='duplicate':ack[1]=deepcopy(ack[0])
    elif fault=='extra':ack.append(deepcopy(ack[-1]))
    elif fault=='wrong-digest':ack[0]['cohort_sha256']='0'*64
    elif fault=='wrong-revision':ack[0]['revision']='4'
    else:ack[0]['recipe_sha256']=ack[0].pop('cohort_sha256')
    with pytest.raises(ValueError):store.claim(plan,portrait_cohort_ack=ack)
    assert store.pending[plan.token] is plan and not store.terminal


@pytest.mark.parametrize('foreign',['face_style_review_ack','spill_review_ack','shadow_review_ack',
                                  'torso_review_ack','waist_review_ack','head_review_ack','collarbone_review_ack'])
def test_plain_portrait_claim_refuses_other_review_families(foreign):
    store,plan,ack,_=fixture()
    with pytest.raises(ValueError):store.claim(plan,portrait_cohort_ack=ack,**{foreign:[]})
    assert store.pending[plan.token] is plan and not store.terminal


@pytest.mark.parametrize('collarbone',[False,True])
def test_claim_and_final_receipt_keep_exact_ack_scope_and_original_request(collarbone):
    store,plan,ack,clavicle=fixture(collarbone=collarbone)
    extras={'collarbone_review_ack':clavicle} if collarbone else {}
    store.claim(plan,portrait_cohort_ack=ack,request_id='original',**extras)
    result=store.finish(plan,{'success':True,'preflight_token':plan.token})
    assert result['portrait_cohort'] is True and result['portrait_cohort_ack']==ack
    assert result['module_scope']==list(plan.modules) and result['request_id']=='original'
    if collarbone:assert result['collarbone_cohort'] is True and result['collarbone_review_ack']==clavicle
    result['portrait_cohort_ack'].clear()
    assert store.completed(plan.token,'workspace')['portrait_cohort_ack']==ack
    assert plan.token not in store.pending


@pytest.mark.parametrize('field',['portrait_cohort_ack','portrait_cohort','module_scope','collarbone_review_ack','collarbone_cohort'])
def test_final_receipt_cannot_change_either_claimed_family_or_exact_scope(field):
    store,plan,ack,clavicle=fixture(collarbone=True)
    store.claim(plan,portrait_cohort_ack=ack,collarbone_review_ack=clavicle,request_id='original')
    retained=store.completed(plan.token,'workspace')
    with pytest.raises(ValueError):store.finish(plan,{'success':True,field:False if field.endswith('cohort') else []})
    assert store.completed(plan.token,'workspace')==retained


@pytest.mark.parametrize('collarbone',[False,True])
def test_overflow_unknown_receipt_retains_every_consent_and_exact_empty_unlink_scope(monkeypatch,collarbone):
    store,plan,ack,clavicle=fixture(named=False,operation='unlink',collarbone=collarbone)
    extras={'collarbone_review_ack':clavicle} if collarbone else {}
    store.claim(plan,portrait_cohort_ack=ack,request_id='original',**extras)
    monkeypatch.setattr(B,'MAX_RESULT_BYTES',1)
    result=store.finish(plan,{'success':True,'huge':object()})
    assert result['success'] is False and result['outcome_unknown'] is True
    assert result['portrait_cohort'] is True and result['portrait_cohort_ack']==ack
    assert result['module_scope']==[] and result['request_id']=='original'
    if collarbone:assert result['collarbone_review_ack']==clavicle and result['collarbone_cohort'] is True


@pytest.mark.parametrize('collarbone',[False,True])
def test_replay_requires_exact_original_acknowledgments_and_scope_without_writing(collarbone):
    store,plan,ack,clavicle=fixture(collarbone=collarbone);extras={'collarbone_review_ack':clavicle} if collarbone else {}
    store.claim(plan,portrait_cohort_ack=ack,request_id='original',**extras)
    owner,events=controller(store);request=commit_request(plan,ack,**extras)
    assert owner.replay_completed(request)
    owner.ports.people_transfer.assert_not_called()
    assert events[-1]['replayed'] and events[-1]['request_id']=='commit'
    assert store.completed(plan.token,'workspace')['request_id']=='original'
    for field in ('portrait_cohort_ack','module_scope')+ (('collarbone_review_ack',) if collarbone else ()):
        bad=deepcopy(request);bad.pop(field)
        with pytest.raises(ValueError):owner.replay_completed(bad)
    bad=deepcopy(request);bad['module_scope'].reverse()
    with pytest.raises(ValueError):owner.replay_completed(bad)


@pytest.mark.parametrize('fault',['missing-scope','wrong-scope','missing-ack','foreign-ack'])
def test_controller_rejects_bad_fresh_commit_before_people_adapter_or_claim(fault):
    store,plan,ack,_=fixture();owner,events=controller(store);request=commit_request(plan,ack)
    if fault=='missing-scope':request.pop('module_scope')
    elif fault=='wrong-scope':request['module_scope']=[]
    elif fault=='missing-ack':request.pop('portrait_cohort_ack')
    else:request['face_style_review_ack']=[]
    owner.handle(request)
    owner.ports.people_transfer.assert_not_called()
    assert store.pending[plan.token] is plan and not store.terminal
    assert events[-1]['success'] is False and events[-1]['outcome_unknown'] is False


def test_generic_plan_cannot_use_portrait_ack_scope_or_receipt_marker_as_bypass():
    store=B.PreflightStore(lambda:1)
    plan=store.create('workspace','source',1,'/source',['ev'],{'ev':{'value':1}},
                      'recheck',[B.FrozenTarget('target',2,0,'/target',None,'{}')],[])
    with pytest.raises(ValueError):store.claim(plan,portrait_cohort_ack=[])
    with pytest.raises(ValueError):store.finish(plan,{'success':True,'portrait_cohort':True})
    owner,events=controller(store);owner.handle(commit_request(plan,[]))
    owner.ports.people_transfer.assert_not_called()
    assert store.pending[plan.token] is plan and not store.terminal
    assert events[-1]['success'] is False


def test_named_preflight_exemption_reads_only_exact_detached_metadata():
    request=preflight_request();before=deepcopy(request)
    assert portrait_cohort_preflight_read_only(request) and request==before
    require_route('batch',request)
    request.pop('conflict_policy')
    assert portrait_cohort_preflight_read_only(request)


@pytest.mark.parametrize('fault',['generic','unlink','commit','extra','ack','token','policy','scope','scope-order',
    'recipe','selection','source-asset','target-asset','scope-owner','epoch','duplicate-ref','duplicate-doc',
    'missing-doc','wrong-doc','large-revision','large-analysis','long-id','control-id'])
def test_named_read_exemption_does_not_admit_generic_lifecycle_or_arbitrary_mutation(fault):
    request=preflight_request();selected=request['people_transfer'];target=selected['targets'][0]
    if fault=='generic':selected.pop('face_style')
    elif fault=='unlink':selected['operation']='unlink'
    elif fault=='commit':request['action']='commit'
    elif fault=='extra':request['replacement_graph']={}
    elif fault=='ack':request['portrait_cohort_ack']=[]
    elif fault=='token':request['preflight_token']='a'*32
    elif fault=='policy':request['conflict_policy']='skip_and_report'
    elif fault=='scope':request['module_scope'].pop()
    elif fault=='scope-order':request['module_scope'].reverse()
    elif fault=='recipe':selected['face_style']['amount']=True
    elif fault=='selection':selected['selection'].pop(next(iter(selected['selection'])))
    elif fault=='source-asset':selected['source_ref']['asset_sha256']='0'*64
    elif fault=='target-asset':target['target_refs'][0]['asset_sha256']='0'*64
    elif fault=='scope-owner':
        selected['source']['people_scope']='project';target['target']['people_scope']='project'
    elif fault=='epoch':target['target']['document']['epoch']='other'
    elif fault=='duplicate-ref':target['target_refs']*=2
    elif fault=='duplicate-doc':request['docs']*=2
    elif fault=='missing-doc':request['docs']=[]
    elif fault=='wrong-doc':request['docs']=['f'*32]
    elif fault=='large-revision':target['target']['document']['revision']=2**53
    elif fault=='large-analysis':target['target_refs'][0]['analysis_revision']=2**53
    elif fault=='long-id':request['request_id']='女'*64
    else:request['request_id']='review\n'
    assert not portrait_cohort_preflight_read_only(request)


@pytest.mark.parametrize('field,value',[('cmd','preset'),('action','commit'),('preflight_token','x'*32),
    ('revision','03'),('revision',str(2**64)),('side','mask'),('sha256','F'*64),
    ('module_scope',[]),('portrait_cohort_ack',[]),('people_transfer',{})])
def test_image_read_is_exact_and_never_an_edit_exemption(field,value):
    assert portrait_cohort_image_read_only(image_request())
    assert not portrait_cohort_image_read_only({**image_request(),field:value})


def test_derived_routes_admit_exact_cohort_image_and_commit_but_no_mixed_families():
    request=image_request();engine=SimpleNamespace(_creative_base={'synthetic':True},_docs=[])
    require_route('batch',request);guard_command(engine,'batch',request)
    _,plan,ack,_=fixture();request=commit_request(plan,ack)
    require_route('batch',request);require_route('batch',{**request,'collarbone_review_ack':[]})
    for extra in ({'face_style_review_ack':[]},{'head_review_ack':[]},{'people_transfer':{}},{'docs':[]}):
        with pytest.raises(ValueError):require_route('batch',{**request,**extra})
    for field in ('portrait_cohort_ack','module_scope'):
        bad=dict(request);bad.pop(field)
        with pytest.raises(ValueError):require_route('batch',bad)


@pytest.mark.parametrize('request_factory',[image_request,preflight_request])
@pytest.mark.parametrize('failed',[False,True])
@pytest.mark.parametrize('tainted',[False,True])
def test_exact_read_keeps_recovery_revision_and_preexisting_taint(request_factory,failed,tainted):
    runtime=SimpleNamespace(revision=9,tainted=tainted,reason='existing')
    engine=SimpleNamespace(_project_recovery_runtime=runtime,EDIT_CMDS={'batch'})
    RECOVERY.finish(engine,{'message':request_factory(),'started':True,'returned':not failed,'failed':failed},
                    'read failed' if failed else None)
    assert vars(runtime)=={'revision':9,'tainted':tainted,'reason':'existing'}


def test_generic_preflight_failure_stays_guarded_and_commit_stays_a_distinct_history_mutation():
    request=preflight_request();request['people_transfer'].pop('face_style')
    runtime=SimpleNamespace(revision=9,tainted=False,reason=None)
    engine=SimpleNamespace(_project_recovery_runtime=runtime,EDIT_CMDS={'batch'})
    RECOVERY.finish(engine,{'message':request,'started':True,'returned':False,'failed':True},'failure')
    assert runtime.tainted and runtime.revision==9
    _,plan,ack,_=fixture();request=commit_request(plan,ack)
    RECOVERY.finish(engine,{'message':request,'started':True,'returned':True,'failed':False})
    assert runtime.tainted and runtime.revision==10
    assert HISTORY.command_group('batch',request)!=HISTORY.command_group('batch',{**request,'preflight_token':'b'*32})


def test_dispatch_keeps_earlier_guards_and_no_capture_invalidation_for_reads():
    source=(ENGINE/'server.py').read_text();body=source[source.index('    def _process_line('):]
    read=body.index('if portrait_cohort_image_read_only(msg) or portrait_cohort_preflight_read_only(msg):')
    for guard in ('recovery.host.blocks','managed.blocks','package.blocks','CDH.guard_command','relocation.blocks'):
        assert body.index(guard)<read
    for mutation in ('invalidate_other(self,name,msg)','self._arm_before_command(msg)',
                     'self._cancel_snapshot(', 'before = self._history_capture()'):
        assert read<body.index(mutation)
    sync=(ENGINE/'batch_sync.py').read_text()
    assert sync.index('if action == "portrait_cohort_visual":')<sync.index('why = self.editor.guard')
    assert len(source.splitlines())<=7065
    for name in ('batch_preflight.py','batch_preflight_controller.py'):
        assert 'from .portrait_cohort_store import prune as prune_portrait_cohort' in (ENGINE/name).read_text()
