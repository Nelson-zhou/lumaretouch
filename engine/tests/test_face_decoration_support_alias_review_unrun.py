# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN support-alias review contracts, never image acceptance.

Synthetic retained identities and mock boundaries are not runtime, export,
native, photographic or visual-quality evidence. Do not mark these passed.
"""
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from lumaretouch_engine import people_state as S, face_decoration_state as D
from lumaretouch_engine import face_decoration_support as SUPPORT
from lumaretouch_engine import face_decoration_support_alias_plan as PLAN
from lumaretouch_engine import face_decoration_support_alias_review as REVIEW
from lumaretouch_engine import face_decoration_alias_history as SCALAR
from lumaretouch_engine import people_host_commands as COMMANDS
from test_face_decoration_support_host_unrun import graph, region


def target(ref):return {'scope':'face','target_id':ref['face_instance_id'],'face_ref':ref}


def reference(ref):
    return {'source':{'sha256':ref['asset_sha256'],'width':100,'height':100},'face_ref':ref,
        'landmark_digest':'d'*64,'preview_sha256':'e'*64,'reference_request_id':'source-reference'}


def active(state,ref):return S.set_override(state,'face',ref['face_instance_id'],D.OP,'/strength',.4)


def review(ref):
    return {'version':1,'token':'a'*32,'target':SUPPORT.KIND,'face_ref':ref,'before_support_sha256':None,
        'support_sha256':'b'*64,'before_bank_sha256':'c'*64,'candidate_bank_sha256':'d'*64,
        'candidate_state_revision':1,'review_sha256':'e'*64,'members':[
            {'visual':{'document_id':doc,'revision':'4','before':{'sha256':'f'*64},'after':{'sha256':'0'*64}}}
            for doc in ('one','two')]}


def test_distinct_request_requires_exact_source_paint_and_review_address():
    _,ref=graph();payload={'region':region(),'reference_proof':reference(ref)}
    REVIEW.check_action('face_decoration_support_alias_preview',payload,target(ref))
    for addition in ({'recipe':D.neutral()},{'assets':{}},{'reference_proof':{**reference(ref),'preview_sha256':'bad'}}):
        with pytest.raises(ValueError):
            REVIEW.check_action('face_decoration_support_alias_preview',{**payload,**addition},target(ref))
    image={'token':'a'*32,'document_id':'one','side':'before','sha256':'b'*64,'review_sha256':'c'*64}
    REVIEW.check_action('face_decoration_support_alias_image',image,target(ref))
    with pytest.raises(ValueError):
        REVIEW.check_action('face_decoration_support_alias_image',{k:v for k,v in image.items() if k!='review_sha256'},target(ref))
    assert REVIEW.read_only({'cmd':'people','action':'face_decoration_support_alias_preview','payload':None})
    assert not REVIEW.read_only({'cmd':'people','action':'face_decoration_support_alias_confirm'})
    assert not REVIEW.read_only({'cmd':'people','action':[]})


def test_initial_neutral_support_is_detached_and_active_missing_before_refuses():
    before,ref=graph();saved=deepcopy(before);candidate,assets=SUPPORT.retain(before,{},ref,region())
    PLAN.narrow(before,candidate,{},assets,ref)
    covered=PLAN.coverage(before,candidate,{},assets,ref)
    assert before==saved and covered['targets'][0]['before_visibility_sha256'] is None
    assert covered['targets'][0]['visibility_sha256']==next(iter(assets))
    broken=active(before,ref);after,bank=SUPPORT.retain(broken,{},ref,region())
    with pytest.raises(ValueError):PLAN.narrow(broken,after,{},bank,ref)
    with pytest.raises(ValueError):PLAN.coverage(broken,after,{},bank,ref)
    with pytest.raises(ValueError):SCALAR.scalar_changes(before,candidate,[ref])


def test_revised_paint_retains_both_records_and_rejects_noop_or_extra_asset():
    empty,ref=graph();before,old=SUPPORT.retain(empty,{},ref,region())
    paint=region();paint['recipe']['objects'][0]['points']=[[.35,.55],[.65,.55]]
    candidate,assets=SUPPORT.retain(before,old,ref,paint)
    PLAN.narrow(before,candidate,old,assets,ref)
    assert len(assets)==2 and all(assets[key]==value for key,value in old.items())
    same,same_bank=SUPPORT.retain(before,old,ref,region())
    with pytest.raises(ValueError):PLAN.narrow(before,same,old,same_bank,ref)
    numeric_same=region();numeric_same['recipe']['objects'][0]['opacity']=1
    same,same_bank=SUPPORT.retain(before,old,ref,numeric_same)
    with pytest.raises(ValueError):PLAN.narrow(before,same,old,same_bank,ref)
    changed=deepcopy(candidate);changed['overrides']=active(before,ref)['overrides']
    with pytest.raises(ValueError):PLAN.narrow(before,changed,old,assets,ref)
    stale=deepcopy(old);stale[next(iter(stale))]['row']['landmark_digest']='0'*64
    with pytest.raises(ValueError):PLAN.narrow(before,candidate,stale,assets,ref)


def test_other_active_faces_keep_their_own_visibility_and_recipe():
    before,ref=graph();other=S.new_face(ref['asset_sha256'],[.2,.2,.6,.7],before['faces'][ref['face_instance_id']]['evidence'])
    other_ref=S.face_ref(other);before['faces'][other_ref['face_instance_id']]=other
    before,bank=SUPPORT.retain(before,{},other_ref,region());before=active(before,other_ref)
    candidate,assets=SUPPORT.retain(before,bank,ref,region())
    PLAN.narrow(before,candidate,bank,assets,ref)
    coverage=PLAN.coverage(before,candidate,bank,assets,ref)
    assert {row['face_ref']['face_instance_id'] for row in coverage['targets']}=={ref['face_instance_id'],other_ref['face_instance_id']}
    row=next(row for row in coverage['targets'] if row['face_ref']==other_ref)
    assert row['before_visibility_sha256']==row['visibility_sha256']
    assert row['before_recipe_sha256']==row['recipe_sha256']
    with pytest.raises(ValueError):PLAN.coverage(before,candidate,{},assets,ref)


def test_complete_coverage_cap_refuses_instead_of_truncating():
    before,ref=graph()
    for index in range(64):
        face=S.new_face(ref['asset_sha256'],[.2,.2,.6,.7],before['faces'][ref['face_instance_id']]['evidence'])
        own=S.face_ref(face);before['faces'][own['face_instance_id']]=face;before=active(before,own)
    candidate,bank=SUPPORT.retain(before,{},ref,region())
    with pytest.raises(ValueError,match='bounded review'):PLAN.coverage(before,candidate,{},bank,ref)


def test_staged_context_never_installs_candidate_bank(monkeypatch):
    from lumaretouch_engine import full_candidate_render as FULL
    before,ref=graph();after,assets=SUPPORT.retain(before,{},ref,region())
    original={'people_graph':before,'people_support_assets':{},'unrelated':{'repair':'own'}}
    engine=SimpleNamespace(_people_support={});row={}
    monkeypatch.setattr(FULL,'people_context',lambda *_:deepcopy(original))
    staged=PLAN.staged_context(engine,row,after,{},assets)
    assert staged['people_graph']==after and staged['people_support_assets']==assets
    assert original['people_graph']==before and engine._people_support=={}
    with pytest.raises(ValueError):PLAN.staged_context(engine,row,after,assets,assets)


def test_actual_all_member_image_reads_and_exact_order_are_required(monkeypatch):
    _,ref=graph();frozen=review(ref);entry={'review':frozen,'candidate':{'revision':1},'served':set()}
    cache=Mock();store={'images':cache};engine=SimpleNamespace()
    monkeypatch.setattr(REVIEW,'_entry',lambda *_:(store,entry));monkeypatch.setattr(REVIEW,'_verify',lambda *_:None)
    with pytest.raises(ValueError):REVIEW.confirm(engine,{},target(ref),{'token':frozen['token'],'ack':REVIEW._ack(frozen)})
    for member in frozen['members']:
        visual=member['visual']
        for side in ('before','after'):
            request={'token':frozen['token'],'document_id':visual['document_id'],'side':side,
                'sha256':visual[side]['sha256'],'review_sha256':frozen['review_sha256']}
            REVIEW.image(engine,{},target(ref),request)
    candidate,proof=REVIEW.confirm(engine,{},target(ref),{'token':frozen['token'],'ack':REVIEW._ack(frozen)})
    assert candidate==entry['candidate'] and proof['history_review_sha256']==REVIEW.digest(proof['ack'])
    wrong=REVIEW._ack(frozen);wrong['members'].reverse()
    with pytest.raises(ValueError):REVIEW.confirm(engine,{},target(ref),{'token':frozen['token'],'ack':wrong})
    request['review_sha256']='1'*64
    with pytest.raises(ValueError):REVIEW.image(engine,{},target(ref),request)


@pytest.mark.parametrize('mode',['prewrite','rollback','unknown'])
def test_failed_support_receipt_never_exposes_attempted_candidate(mode):
    _,ref=graph();frozen=review(ref)
    request={'cmd':'people','action':'face_decoration_support_alias_confirm','request_id':'confirm',
        'document_id':'one','document_epoch':'epoch','document_revision':4,'state_revision':0,'association_revision':0,
        'target':target(ref),'payload':{'token':frozen['token'],'ack':REVIEW._ack(frozen)}}
    old={'before_fence':0,'success':False,'side_effects_started':mode!='prewrite',
        'rolled_back':mode=='rollback','requires_reload':mode=='unknown','payload':REVIEW._proof(frozen)}
    engine=SimpleNamespace(_people_receipts=OrderedDict([('confirm',old)]),_vram=object(),
        _people_graph_owner=SimpleNamespace(fence=int(mode!='prewrite')),
        doc_state=Mock(side_effect=AssertionError('Failed support receipts cannot expose candidate state')))
    emitted=[];COMMANDS.finish(engine,request,'fixture failure',emitted.append);result=emitted[-1]
    assert result['success'] is False and 'payload' not in result and 'doc_state' not in result
    assert result['no_write']==(mode=='prewrite') and result['rolled_back']==(mode=='rollback')
    assert result['outcome_unknown']==(mode=='unknown')


def test_owned_source_hooks_preserve_scalar_and_full_render_defaults():
    root=Path(__file__).parents[1]/'src'/'lumaretouch_engine'
    review_source=(root/'face_decoration_support_alias_review.py').read_text()
    render_source=(root/'portrait_review_render.py').read_text()
    host=(root/'face_decoration_host.py').read_text()
    assert 'staged_people_context=context' in review_source
    assert 'render_image(engine,other,own,state,version.document_id,str(version.revision))' in review_source
    assert "entry['served'].add((payload['document_id'],payload['side']))" in review_source
    assert "entry['batch'].documents.remember_current();verify_before()" in review_source
    assert "mark_started();entry['claimed']=True" in review_source
    commands=(root/'people_host_commands.py').read_text()
    assert commands.index("records[request]['batch_id']=batch_id")<commands.index('decoration_support_alias.verify_after_publish')
    assert 'engine._people_support =' not in review_source and 'engine._people_support=' not in review_source
    assert "options = {} if staged_people_context is None" in render_source
    assert 'def review_reference' in host and 'source, ref, proof = review_reference' in host
