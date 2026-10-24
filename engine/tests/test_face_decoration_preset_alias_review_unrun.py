# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: complete mixed decoration aliases, not image acceptance.

No collection, imports, execution, rendering, inference or numeric validation
was run. Stubs describe exact coordinator boundaries only.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from lumaretouch_engine import face_decoration_preset_review as R
from lumaretouch_engine import face_decoration_preset_alias_review as A
from lumaretouch_engine import face_decoration_preset_store as STORE


def wrapper():
    source={'asset_sha256':'a'*64,'creative_source':None,'original_sha256':'a'*64}
    face={'asset_sha256':'a'*64,'face_instance_id':'face-one','analysis_revision':1}
    second={**face,'face_instance_id':'face-two'}
    image={'mime':'image/png','width':80,'height':60,'sha256':'1'*64}
    coverage={'version':1,'support_transfer':'none','targets':[
        {'face_ref':ref,'scope':'target-reviewed-visible-skin','visibility_sha256':'2'*64,
         'recipe_sha256':'3'*64} for ref in (face,second)]}
    visual={'version':1,'document_id':'doc','revision':'2','source_proof':source,
        **{key:'4'*64 for key in ('before_state_sha256','candidate_state_sha256','before_people_sha256','candidate_people_sha256')},
        'source_size':[80,60],'before_output_size':[80,60],'after_output_size':[80,60],
        'coverage_sha256':R.digest(coverage),'before':deepcopy(image),'after':deepcopy(image)}
    sibling=deepcopy(visual); sibling.update(document_id='sibling',revision='11',before_output_size=[40,60],after_output_size=[40,60])
    sibling['before']['width']=sibling['after']['width']=40
    owner={'document':{'document_id':'doc','epoch':'workspace','revision':2},'people_scope':'project',
        'state_revision':0,'association_revision':0,'graph_sha256':'d'*64,'source_proof':deepcopy(source)}
    return resign({'version':2,'preset_sha256':'5'*64,'applies_sha256':'6'*64,'before_bank_sha256':'7'*64,
        'load_id':'load','owner':owner,'face_ref':face,'coverage':coverage,'visual':deepcopy(visual),
        'members':[{'path':'same.png','role':'active','visual':deepcopy(visual)},
                   {'path':'same.png','role':'sibling','visual':sibling}]})


def resign(value):
    value['review_sha256']=R.digest({key:item for key,item in value.items() if key!='review_sha256'})
    return value


def ack(value):
    return {**{key:value[key] for key in ('review_sha256','preset_sha256','applies_sha256')},
        'members':[{'document_id':v['document_id'],'revision':v['revision'],
            'before_sha256':v['before']['sha256'],'after_sha256':v['after']['sha256'],
            'coverage_sha256':v['coverage_sha256']} for v in (m['visual'] for m in value['members'])]}


def test_exact_v2_has_all_face_coverage_and_each_siblings_own_crop():
    value=wrapper()
    assert R.checked(value)==value and R.checked_ack(ack(value))==ack(value)
    assert R.acknowledgment(ack(value),value)==ack(value)
    assert len(value['coverage']['targets'])==2
    assert value['members'][0]['path']==value['members'][1]['path']
    assert value['members'][0]['visual']['after_output_size']!=value['members'][1]['visual']['after_output_size']


def test_same_derived_asset_distinct_original_provenance_is_preserved():
    value=wrapper(); derived={'sha256':'a'*64,'width':80,'height':60}
    value['owner']['source_proof'].update(creative_source=derived,original_sha256='b'*64)
    value['visual']['source_proof']=deepcopy(value['owner']['source_proof'])
    value['members'][0]['visual']=deepcopy(value['visual'])
    value['members'][1]['visual']['source_proof'].update(creative_source=deepcopy(derived),original_sha256='c'*64)
    assert R.checked(resign(value))==value
    assert value['members'][0]['visual']['source_proof']!=value['members'][1]['visual']['source_proof']


@pytest.mark.parametrize('mutation',['missing','duplicate','role','graph','source','coverage','sibling-recipe',
                                    'sibling-crop','active-pair','revision','unknown','bank','unhashed-bank'])
def test_rehashed_review_cannot_bless_incomplete_or_foreign_members(mutation):
    value=wrapper(); member=value['members'][1]; visual=member['visual']
    if mutation=='missing':value['members'].pop()
    if mutation=='duplicate':visual['document_id']='doc'
    if mutation=='role':member['role']='active'
    if mutation=='graph':visual['candidate_people_sha256']='f'*64
    if mutation=='source':visual['source_proof']['asset_sha256']='f'*64
    if mutation=='coverage':visual['coverage_sha256']='f'*64
    if mutation=='sibling-recipe':visual['candidate_state_sha256']='f'*64
    if mutation=='sibling-crop':visual['after_output_size']=[50,60];visual['after']['width']=50
    if mutation=='active-pair':value['members'][0]['visual']['after']['sha256']='f'*64
    if mutation=='revision':visual['revision']='9007199254740991'
    if mutation=='unknown':member['donor_mask']={}
    if mutation=='bank':value['before_bank_sha256']='bad'
    if mutation=='unhashed-bank':
        value['before_bank_sha256']='f'*64
    else:resign(value)
    with pytest.raises(ValueError):R.checked(value)


@pytest.mark.parametrize('mutation',['omit','reorder','revision','image','coverage','preset','legacy','scalar','support'])
def test_ack_requires_every_ordered_decoded_pair_and_full_preset_identity(mutation):
    value=wrapper(); response=ack(value)
    if mutation=='omit':response['members'].pop()
    if mutation=='reorder':response['members'].reverse()
    if mutation=='revision':response['members'][1]['revision']='12'
    if mutation=='image':response['members'][1]['after_sha256']='f'*64
    if mutation=='coverage':response['members'][1]['coverage_sha256']='f'*64
    if mutation=='preset':response['preset_sha256']='f'*64
    if mutation=='legacy':response['replace_legacy']=False
    if mutation=='scalar':response.pop('applies_sha256')
    if mutation=='support':response['support_overlay_sha256']='f'*64
    with pytest.raises(ValueError):R.acknowledgment(response,value)


def test_all_server_served_sides_required_independent_of_client_ack(monkeypatch):
    value=wrapper(); entry={'served':set()}
    monkeypatch.setattr(R,'_entry',lambda *a,**k:entry)
    R.acknowledgment(ack(value),value)
    with pytest.raises(ValueError,match='Load every'):A.verify_served(value)
    for member in value['members']:
        A.served(value,member['visual']['document_id'],'before')
        with pytest.raises(ValueError):A.verify_served(value)
        A.served(value,member['visual']['document_id'],'after')
    A.verify_served(value)
    with pytest.raises(ValueError):A.served(value,'unknown','after')


def test_v2_cannot_enter_single_document_replay_or_rollback():
    for rollback in (False,True):
        with pytest.raises(ValueError,match='composite batch ledger'):
            R.replay(None,None,None,'load','2',wrapper(),rollback=rollback)
    with pytest.raises(ValueError,match='composite batch ledger'):
        R.verify_applied(None,None,None,'load','2',wrapper())


def test_private_alias_plan_cannot_enter_generic_replay_even_without_graph_changes():
    from lumaretouch_engine.people_preset_plan import snapshot,PresetAliasReviewPlan
    from lumaretouch_engine.people_scope import execute_plan,restore_plan
    plan=snapshot({'exposure':.2},{},review_only=True)
    assert type(plan) is PresetAliasReviewPlan
    with pytest.raises(ValueError,match='composite batch ledger'):execute_plan(None,plan)
    with pytest.raises(ValueError,match='composite batch ledger'):restore_plan(None,plan,{})


def test_graph_noop_closure_preserves_complete_refs_and_every_alias(monkeypatch):
    value=wrapper(); refs=[item['face_ref'] for item in value['coverage']['targets']]
    rows=[{'path':m['path'],'document_id':m['visual']['document_id'],'state':{'own':index}}
          for index,m in enumerate(value['members'])]
    versions=SimpleNamespace(check_advance=lambda row:SimpleNamespace(document_id=row['document_id'],revision=2))
    entry={'row':rows[0],'refs':refs,'plan':SimpleNamespace(target_ref=value['face_ref']),
           'batch':SimpleNamespace(documents=SimpleNamespace(rows=lambda:rows),versions=versions)}
    monkeypatch.setattr(A.V,'scope',lambda row:'project')
    monkeypatch.setattr(A.SOURCE,'row_proof',lambda row:value['visual']['source_proof'])
    result=A._targets(None,entry,{'current':'not-parked'})
    assert {target['document_id'] for target in result.values()}=={'doc','sibling'}
    assert all(target['reviewed_face_refs']==refs for target in result.values())


def test_paged_request_requires_paired_member_identity_and_no_support_payload():
    request={'cmd':'preset','action':'face_decoration_visual','request_id':'request','id':'preset',
        'document_id':'load','revision':'2','side':'before','sha256':'1'*64,'preflight_token':'token',
        'member_document_id':'sibling','member_revision':'11'}
    assert STORE.image_read_only(request)
    assert not STORE.image_read_only({key:item for key,item in request.items() if key!='member_revision'})
    assert not STORE.image_read_only({**request,'donor_mask':{}})
    assert not STORE.image_read_only({**request,'side':'support'})


@pytest.mark.parametrize('selected',[True,False])
def test_prepare_uses_actual_mixed_graph_and_sibling_own_recipe_with_retained_review(monkeypatch,selected):
    from collections import OrderedDict
    from lumaretouch_engine import people_scope,people_transfer_inventory,people_graph_owner
    from lumaretouch_engine import face_decoration_preset_alias_authority as AUTHORITY
    value=wrapper(); face=value['face_ref']; source=value['visual']['source_proof']
    before={'crop':'active-before','repairs':['current'],'_face_decoration_preset_retained_active':True}
    candidate={R.SCOPE.TARGET:face,R.SCOPE.FIELD:{**R.SCOPE.S.neutral(),'strength':.3}}
    after={'crop':'active-after','repairs':['current'],'exposure':.3}
    sibling={'crop':'own-crop','repairs':['own-repair'],'exposure':-.2}
    graph_a={'phase':'before'};graph_b={'phase':'mixed-after'}
    owner=SimpleNamespace(fence=7,snapshot=lambda:deepcopy(graph_a))
    plan=SimpleNamespace(managed=True,owner=owner,owner_fence=7,before=graph_a,candidate=graph_b,state=after,target_ref=face)
    rows=[{'path':'active.png','document_id':'doc'},{'path':'sibling.png','document_id':'sibling'}]
    members=[(rows[0],before,source,SimpleNamespace(document_id='doc',revision=2)),
             (rows[1],sibling,source,SimpleNamespace(document_id='sibling',revision=11))]
    engine=SimpleNamespace(_batch_controller=lambda:object(),_document_versions=lambda:SimpleNamespace(workspace='workspace'))
    monkeypatch.setattr(R,'_target',lambda *a,**k:(owner,'doc'))
    monkeypatch.setattr(people_scope,'plan_preset',lambda *a,**k:plan)
    monkeypatch.setattr(people_graph_owner,'affected_assets',lambda *a:{face['asset_sha256']})
    monkeypatch.setattr(A.PLAN,'admit',lambda *a,**k:rows[0])
    monkeypatch.setattr(A.PLAN,'check_scalar_graph',lambda *a:None)
    monkeypatch.setattr(A.PLAN,'coverage',lambda *a,**k:value['coverage'])
    monkeypatch.setattr(A.CLOSURE,'_eligible',lambda *a:members)
    monkeypatch.setattr(A,'_dormant_key',lambda *a:'frozen-closure')
    monkeypatch.setattr(A,'_bank',lambda *a:{})
    monkeypatch.setattr(A,'_targets',lambda *a:{'0':{'document_id':'doc'},'1':{'document_id':'sibling'}})
    monkeypatch.setattr(A,'_verify',lambda *a:None)
    monkeypatch.setattr(AUTHORITY,'mint',lambda *a,**k:object())
    monkeypatch.setattr(people_transfer_inventory,'proof',lambda *a,**k:value['owner'])
    monkeypatch.setattr(R,'_snapshot_key',lambda engine,row,state,graph:R.digest([state,graph]))
    monkeypatch.setattr(R,'_ENTRIES',OrderedDict())
    rendered=[]
    def render(engine,row,state,graph,document,revision):
        rendered.append((row,deepcopy(state),deepcopy(graph)))
        size=[80,60] if row is rows[0] else [40,60]
        image={'mime':'image/png','width':size[0],'height':size[1],'sha256':str(len(rendered))*64}
        return image,{**image,'base64':'authored-stub'},{'source_proof':source,'source_size':[80,60],
            'output_size':size,'candidate_sha256':R.digest(state),'people_sha256':R.digest(graph)}
    monkeypatch.setattr(R,'_image',render)
    modules={R.SCOPE.OP:{'recipe':candidate[R.SCOPE.FIELD]}} if selected else {'lnx.exposure.v1':{}}
    result,duplicate=A.prepare(engine,rows[0],before,candidate,'load','2',{'id':'mixed'},modules)
    assert rendered==[(rows[0],before,graph_a),(rows[0],after,graph_b),
                      (rows[1],sibling,graph_a),(rows[1],sibling,graph_b)]
    assert result==duplicate and result['before_bank_sha256']==R.digest({})
    entry=R._ENTRIES[R.digest(result)]
    assert set(entry['images'])=={'doc','sibling'} and entry['plan'] is plan
    assert entry['refs']==[item['face_ref'] for item in result['coverage']['targets']]


def test_source_contract_has_all_member_mutation_fences_and_no_unreviewed_replay():
    root=Path(__file__).parents[1]/'src'/'lumaretouch_engine'
    review=(root/'face_decoration_preset_alias_review.py').read_text()
    planner=(root/'people_scope.py').read_text()
    assert 'after = plan.state if other is row else state' in review
    assert 'PLAN.coverage(engine,other,plan.candidate,ref,plan.before,state=state)' in review
    assert "REVIEW.digest(_bank(engine)) != wrapper['before_bank_sha256']" in review
    assert "entry['authority'].verify(engine,row,plan.before,plan.candidate)" in review
    assert 'verify_images()' in review and 'ack=ack, verify_before=verify_before' in review
    assert 'review_only=reviewed_face_decoration_aliases' in planner
    assert planner.count('type(plan) is not PresetReplayPlan')==2


@pytest.mark.parametrize('mutation',['bank','source','state','coverage','membership','closure','owner','workspace'])
def test_live_gate_refuses_mutation_before_any_commit(monkeypatch,mutation):
    value=wrapper(); before={'own':'before'}; incoming={R.SCOPE.FIELD:R.SCOPE.S.neutral()}
    graph={'frozen':'graph'}; row={'path':'same.png'}; sibling={'path':'same.png'}
    rows=[row,sibling]; versions=[SimpleNamespace(document_id='doc',revision=2),SimpleNamespace(document_id='sibling',revision=11)]
    own=[before,{'own':'sibling'}]; sources=[deepcopy(m['visual']['source_proof']) for m in value['members']]
    owner=SimpleNamespace(fence=7,snapshot=lambda:graph)
    plan=SimpleNamespace(owner=owner,owner_fence=7,before=graph,candidate=graph,state=before,target_ref=value['face_ref'])
    batch=object(); workspace='workspace'; bank={}; closure='unchanged'; coverage=deepcopy(value['coverage'])
    engine=SimpleNamespace(_batch_controller=lambda:batch,_document_versions=lambda:SimpleNamespace(workspace=workspace))
    entry={'claimed':False,'plan':plan,'row':row,'batch':batch,'workspace':'workspace',
        'before_input_sha256':A.fingerprint(before),'candidate_input_sha256':A.fingerprint(incoming),
        'dormant_key':'unchanged','bank':{},'authority':SimpleNamespace(verify=lambda *a:None),
        'targets':{},'members':[{'row':r,'path':r['path'],'visual':deepcopy(v['visual']),
            'before_key':'snapshot','after_key':'snapshot','state_sha256':A.fingerprint(s)}
            for r,v,s in zip(rows,value['members'],own)]}
    value['before_bank_sha256']=R.digest({})
    if mutation=='bank':bank['foreign']='support'
    if mutation=='source':sources[1]['original_sha256']='f'*64
    if mutation=='state':own[1]['own']='changed'
    if mutation=='coverage':coverage['targets'].pop()
    if mutation=='closure':closure='changed'
    if mutation=='owner':owner.fence+=1
    if mutation=='workspace':workspace='different'
    members=list(zip(rows,own,sources,versions))
    if mutation=='membership':members.pop()
    monkeypatch.setattr(R,'_target',lambda *a,**k:(owner,'doc'))
    monkeypatch.setattr(A.V,'scope',lambda *a:'project')
    monkeypatch.setattr(A,'_bank',lambda *a:bank)
    monkeypatch.setattr(A,'_dormant_key',lambda *a:closure)
    monkeypatch.setattr(A.PLAN,'admit',lambda *a,**k:None)
    monkeypatch.setattr(A.PLAN,'coverage',lambda *a,**k:coverage)
    monkeypatch.setattr(A.CLOSURE,'verify_dormant',lambda *a:None)
    monkeypatch.setattr(A.CLOSURE,'_eligible',lambda *a:members)
    monkeypatch.setattr(R,'_snapshot_key',lambda *a:'snapshot')
    monkeypatch.setattr(A.SOURCE,'verify_row',lambda *a:None)
    monkeypatch.setattr(A,'_targets',lambda *a:{})
    with pytest.raises(ValueError):A._verify(engine,entry,value,before,incoming)
    assert entry['claimed'] is False
