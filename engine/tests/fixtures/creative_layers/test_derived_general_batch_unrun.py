"""AUTHORED / UNRUN: exact-source global parameter batch and history contracts.

These ports exercise transaction ownership without decoding, inference or native
rendering. They do not establish functional, performance or visual acceptance.
"""
from copy import deepcopy
from dataclasses import replace
import json
import struct

import pytest

from lumaretouch_engine import creative_derived_source as SOURCE, scope as SC
from lumaretouch_engine.batch_preflight import FrozenTarget, PreflightStore, canonical
from lumaretouch_engine.batch_sync import BatchDocuments, BatchEditor, BatchSyncController
from lumaretouch_engine.creative_document_assets import make_asset


def base(value=.5):
    return make_asset('rgba',2,1,struct.pack('<ffff',value,.25,.125,1.)*2)


def fixture(tmp_path, *, source_derived=True, target_derived=True):
    rows=[]
    for index in range(3):
        path=tmp_path/f'provenance-{index}.bin'
        path.write_bytes(f'Original provenance only, not decoded: {index}'.encode())
        derived=source_derived if index==0 else target_derived if index==1 else False
        rows.append({'path':str(path),'src_w':2,'src_h':1,'undo':[],'redo':[],
                     'state':{'_exposure':(1. if index==0 else 0.,0.,0.,0.,0.,0.,0.),
                              '_creative_base':base(.4+index*.1) if derived else None,
                              '_strength':.5 if index==0 else 0.,'untouched':{'target':index}}})
    current=[0];events=[];replays=[];dirty=[]
    def replay(state,**options):
        rows[current[0]]['state']=deepcopy(state);replays.append(options)
        return {'event':'frame','render_ms':1}
    controller=BatchSyncController(
        BatchDocuments(lambda:rows,lambda:current[0],lambda:None,
                       lambda path:next((i for i,row in enumerate(rows) if row['path']==path),-1)),
        BatchEditor(lambda _label:None,lambda:deepcopy(rows[current[0]]['state']),replay,
                    lambda _row,**_options:('ok',''),lambda:{'fixture':'status'},
                    mark_dirty=lambda:dirty.append(True)),
        events.append,lambda:1.,lambda:2,64)
    for row in rows:controller.versions.version(row)
    return controller,rows,current,events,replays,dirty


def request(controller,events,action,**options):
    controller.handle_command({'cmd':'batch','action':action,'request_id':action+'-fixture',**options})
    return events[-1]


def review(controller,events,docs=(1,2),**options):
    result=request(controller,events,'preflight',docs=list(docs),module_scope=[SC.OP_EXPOSURE],**options)
    assert result['success']
    return result['preflight_token']


def test_review_captures_compact_source_and_each_target_without_writes(tmp_path):
    controller,rows,_,events,replays,dirty=fixture(tmp_path)
    before=deepcopy(rows);token=review(controller,events)
    plan=controller.preflight.store.get(token,controller.versions.workspace)
    assert json.loads(plan.source_proof_json)==SOURCE.row_proof(rows[0])
    assert [json.loads(target.source_proof_json) for target in plan.targets]==[SOURCE.row_proof(row) for row in rows[1:]]
    assert 'content' not in plan.source_proof_json
    assert all('content' not in target.source_proof_json for target in plan.targets)
    assert rows==before and not replays and not dirty and controller.ledger=={}


@pytest.mark.parametrize('source_derived,target_derived',[(True,False),(False,True),(True,True)])
def test_frozen_global_transfer_preserves_target_sources_and_support(tmp_path,source_derived,target_derived):
    controller,rows,_,events,_,_=fixture(tmp_path,source_derived=source_derived,target_derived=target_derived)
    before=deepcopy(rows);token=review(controller,events)
    result=request(controller,events,'commit',preflight_token=token)
    assert result['success'] and result['targets']==[1,2]
    for index in (1,2):
        assert rows[index]['state']['_exposure'][0]==1.
        assert rows[index]['state']['_creative_base']==before[index]['state']['_creative_base']
        assert rows[index]['state']['untouched']==before[index]['state']['untouched']
        assert rows[index]['state']['_strength']==before[index]['state']['_strength']
        receipt=controller.ledger[result['batch_id']]['targets'][str(index)]
        assert receipt['source_proof']==SOURCE.row_proof(rows[index])


def test_frozen_source_pixel_change_is_reported_but_does_not_replace_reviewed_values(tmp_path):
    controller,rows,_,events,_,_=fixture(tmp_path)
    token=review(controller,events)
    rows[0]['state']['_creative_base']=base(.7)
    rows[0]['state']['_exposure']=(4.,0.,0.,0.,0.,0.,0.)
    result=request(controller,events,'commit',preflight_token=token)
    assert result['success'] and result['source_changed_since_preflight']
    assert all(row['state']['_exposure'][0]==1. for row in rows[1:])


def test_frozen_source_removal_does_not_substitute_current_source(tmp_path):
    controller,rows,current,events,_,_=fixture(tmp_path)
    token=review(controller,events,docs=(1,))
    target=rows[1];rows.pop(0);current[0]=1
    rows[1]['state']['_exposure']=(3.,0.,0.,0.,0.,0.,0.)
    result=request(controller,events,'commit',preflight_token=token)
    assert result['success'] and result['source_missing']
    assert target['state']['_exposure'][0]==1.


@pytest.mark.parametrize('change',['base','clear_base','provenance'])
def test_same_revision_target_source_changes_reject_before_any_write(tmp_path,change):
    controller,rows,_,events,replays,dirty=fixture(tmp_path)
    token=review(controller,events,conflict_policy='recheck')
    if change=='base':rows[1]['state']['_creative_base']=base(.9)
    elif change=='clear_base':rows[1]['state']['_creative_base']=None
    else:(tmp_path/'provenance-1.bin').write_bytes(b'Externally replaced original provenance')
    before=deepcopy(rows)
    result=request(controller,events,'commit',preflight_token=token)
    assert not result['success'] and not result['outcome_unknown']
    assert rows==before and not replays and not dirty and controller.ledger=={}


def test_original_only_review_cannot_authorize_new_derived_target(tmp_path):
    controller,rows,_,events,replays,dirty=fixture(tmp_path,source_derived=False,target_derived=False)
    token=review(controller,events,docs=(1,))
    assert controller.preflight.store.get(token,controller.versions.workspace).source_proof_json is None
    rows[1]['state']['_creative_base']=base(.9);before=deepcopy(rows)
    result=request(controller,events,'commit',preflight_token=token)
    assert not result['success'] and rows==before and not replays and not dirty


def test_shared_original_path_is_not_effective_target_identity(tmp_path):
    controller,rows,_,events,_,_=fixture(tmp_path)
    rows[1]['path']=rows[0]['path'];token=review(controller,events,docs=(1,))
    rows[1]['state']['_creative_base']=rows[0]['state']['_creative_base'];before=deepcopy(rows)
    result=request(controller,events,'commit',preflight_token=token)
    assert not result['success'] and rows==before


def test_unsupported_modules_stay_blocked_even_for_parked_derived_target(tmp_path):
    controller,rows,_,events,_,_=fixture(tmp_path,source_derived=False,target_derived=True)
    result=request(controller,events,'preflight',docs=[1,2],module_scope=[SC.OP_SKIN])
    assert result['success'] and result['targets'][0]['blocked'] and result['targets'][1]['blocked'] is None
    committed=request(controller,events,'commit',preflight_token=result['preflight_token'])
    assert committed['success'] and committed['targets']==[2]
    assert rows[1]['state']['_strength']==0. and rows[2]['state']['_strength']==.5


def test_derived_source_cannot_transfer_unsupported_modules_to_original_targets(tmp_path):
    controller,rows,_,events,replays,dirty=fixture(tmp_path,target_derived=False)
    before=deepcopy(rows)
    result=request(controller,events,'preflight',docs=[1],module_scope=[SC.OP_SKIN])
    assert not result['success'] and rows==before and not replays and not dirty


def test_local_colour_editor_recipe_is_not_a_global_module_escape(tmp_path):
    from lumaretouch_engine import colour_editor_state as CE
    controller,rows,_,events,_,_=fixture(tmp_path)
    rows[0]['state'][CE.KEY]={**CE.neutral(),'scope':'local'}
    result=request(controller,events,'preflight',docs=[1],module_scope=[SC.COLOUR_EDITOR.OP])
    assert not result['success'] and controller.ledger=={}


def test_completed_receipt_is_replayed_without_source_or_guard_revalidation(tmp_path):
    controller,rows,_,events,_,_=fixture(tmp_path)
    token=review(controller,events,docs=(1,))
    first=request(controller,events,'commit',preflight_token=token)
    assert first['success'];before=deepcopy(rows)
    controller.editor=replace(controller.editor,guard=lambda _label:'busy')
    (tmp_path/'provenance-1.bin').unlink()
    repeated=request(controller,events,'commit',preflight_token=token)
    assert repeated['success'] and repeated['replayed']
    assert repeated['batch_id']==first['batch_id'] and rows==before


def test_derived_undo_redo_preserves_unrelated_later_edits(tmp_path):
    controller,rows,_,events,_,_=fixture(tmp_path)
    token=review(controller,events,docs=(1,))
    first=request(controller,events,'commit',preflight_token=token);bid=first['batch_id']
    rows[1]['state']['untouched']={'later':'kept'}
    undone=request(controller,events,'undo',batch_id=bid)
    assert undone['success'] and rows[1]['state']['_exposure'][0]==0.
    redone=request(controller,events,'redo',batch_id=bid)
    assert redone['success'] and rows[1]['state']['_exposure'][0]==1.
    assert rows[1]['state']['untouched']=={'later':'kept'}


@pytest.mark.parametrize('action',['undo','redo'])
def test_history_rejects_changed_effective_target_without_rewriting_scope(tmp_path,action):
    controller,rows,_,events,replays,_=fixture(tmp_path)
    first=request(controller,events,'commit',preflight_token=review(controller,events,docs=(1,)))
    bid=first['batch_id']
    if action=='redo':assert request(controller,events,'undo',batch_id=bid)['success']
    rows[1]['state']['_creative_base']=base(.9);before=deepcopy(rows)
    result=request(controller,events,action,batch_id=bid)
    assert not result.get('restored') and rows==before and not replays


@pytest.mark.parametrize('dormant',['before','after'])
def test_legacy_history_cannot_hide_a_dormant_derived_snapshot(tmp_path,dormant):
    controller,rows,_,events,replays,_=fixture(tmp_path,source_derived=False,target_derived=False)
    first=request(controller,events,'commit',docs=[1],module_scope=[SC.OP_EXPOSURE])
    bid=first['batch_id'];receipt=controller.ledger[bid]['targets']['1']
    assert 'source_proof' not in receipt
    receipt[dormant]=deepcopy(receipt[dormant]);receipt[dormant]['_creative_base']=base(.8)
    before=deepcopy(rows)
    result=request(controller,events,'undo',batch_id=bid)
    assert not result.get('restored') and result['conflicts'] and rows==before and not replays


def test_missing_frozen_target_proof_cannot_be_backfilled_at_commit(tmp_path):
    controller,rows,_,events,_,_=fixture(tmp_path)
    token=review(controller,events,docs=(1,));store=controller.preflight.store
    plan=store.get(token,controller.versions.workspace)
    store.pending[token]=replace(plan,targets=(replace(plan.targets[0],source_proof_json=None),))
    before=deepcopy(rows);result=request(controller,events,'commit',preflight_token=token)
    assert not result['success'] and rows==before


def test_candidate_source_injection_is_rejected_before_publication(tmp_path,monkeypatch):
    from lumaretouch_engine import optics_auto_scope as OA
    controller,rows,_,events,replays,dirty=fixture(tmp_path)
    token=review(controller,events,docs=(1,));original=OA.candidate
    def wrong_target(state,modules,**options):
        candidate=original(state,modules,**options)
        candidate['_creative_base']=rows[0]['state']['_creative_base']
        return candidate
    monkeypatch.setattr(OA,'candidate',wrong_target)
    before=deepcopy(rows);result=request(controller,events,'commit',preflight_token=token)
    assert not result['success'] and rows==before and not replays and not dirty


def test_invalid_and_oversized_proofs_are_not_published_in_plan_store(tmp_path):
    controller,rows,_,_,_,_=fixture(tmp_path);proof=SOURCE.row_proof(rows[1])
    for payload in (canonical({**proof,'content':'not a source proof'}),' '*4097):
        store=PreflightStore(lambda:1)
        target=FrozenTarget('target',0,1,rows[1]['path'],None,'{}',source_proof_json=payload)
        with pytest.raises(ValueError):store.create('workspace','source',0,rows[0]['path'],[SC.OP_EXPOSURE],{},'recheck',[target],[],source_proof=proof)
        assert not store.pending


def test_people_target_inventory_dispatches_before_edit_guard(tmp_path):
    controller,rows,_,events,_,dirty=fixture(tmp_path);calls=[]
    controller.editor=replace(controller.editor,guard=lambda _label:pytest.fail('Inventory entered editable guard'))
    def inventory(owner,command,plan):
        calls.append((command,plan));owner.emit_result(command,{'success':True,'targets':[]})
    controller.preflight.ports=replace(controller.preflight.ports,people_transfer=inventory)
    before=deepcopy(rows);result=request(controller,events,'people_targets',docs=[rows[1]['document_id']])
    assert result['success'] and calls[0][1] is None and rows==before and not dirty


@pytest.mark.parametrize('action',['commit','undo','redo'])
def test_parked_provenance_race_during_live_render_rolls_back_before_publication(tmp_path,action):
    controller,rows,current,events,_,_=fixture(tmp_path)
    token=review(controller,events)
    if action!='commit':
        first=request(controller,events,'commit',preflight_token=token);assert first['success']
        bid=first['batch_id']
        if action=='redo':assert request(controller,events,'undo',batch_id=bid)['success']
    current[0]=1
    original=controller.editor.replay
    def racing_render(state,**options):
        frame=original(state,**options)
        if 'rollback' not in options['replayed_for']:
            (tmp_path/'provenance-2.bin').write_bytes(b'Changed during active render')
        return frame
    controller.editor=replace(controller.editor,replay=racing_render)
    before=deepcopy(rows);ledger=deepcopy(controller.ledger)
    options={'preflight_token':token} if action=='commit' else {'batch_id':bid}
    result=request(controller,events,action,**options)
    assert not result['success']
    assert [row['state'] for row in rows]==[row['state'] for row in before]
    assert rows[2]['undo']==before[2]['undo'] and rows[2]['redo']==before[2]['redo']
    assert controller.ledger==ledger
