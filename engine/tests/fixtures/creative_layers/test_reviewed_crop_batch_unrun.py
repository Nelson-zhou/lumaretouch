"""AUTHORED / UNRUN: crop transaction contracts, not visual acceptance.

The test port below returns synthetic schema evidence without decoding/rendering.
It deliberately tests only receipt/source/transaction ownership. Real canonical
crop pixels, display quality and native UI remain separate local acceptance.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json

import pytest

from lumaretouch_engine import scope as SC, creative_derived_source as SOURCE
from lumaretouch_engine.batch_sync import verify_history_source
from test_derived_general_batch_unrun import fixture, request


def candidate_key(state):
    # Omit immutable binary content only in this synthetic transaction fixture;
    # the production renderer fingerprints the actual entire owned candidate.
    value={key:value for key,value in state.items() if key!='_creative_base'}
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def setup(tmp_path,monkeypatch,*,derived=False):
    controller,rows,current,events,replays,dirty=fixture(tmp_path,source_derived=derived,target_derived=derived)
    for index,row in enumerate(rows):
        row['state'].update(_crop_rect=(.5,0.,1.,1.) if index==0 else (0.,0.,1.,1.),_crop_rotation=0.)
    from lumaretouch_engine import crop_transfer_review as C
    def checked(record):
        assert 'base64' not in record['preview']
        return record
    monkeypatch.setattr(C,'check_record',checked)
    calls=[]
    def prepare(row,candidate,identity,revision):
        proof={'version':1,'document_id':identity,'revision':str(revision),
            'source_proof':SOURCE.row_proof({**row,'state':candidate}),
            'candidate_sha256':candidate_key(candidate),'people_sha256':'a'*64,
            'crop':SC.params_of(candidate,[SC.OP_CROP])[SC.OP_CROP],
            'source_size':[2,1],'output_size':[1,1],
            'preview':{'mime':'image/png','width':1,'height':1,'sha256':'b'*64}}
        public={**deepcopy(proof),'preview':{**proof['preview'],'base64':'SYNTHETIC_NOT_IMAGE'}}
        calls.append(identity)
        return proof,public
    def verify(row,candidate,identity,revision,proof):
        if (proof is None or proof['document_id']!=identity or proof['revision']!=str(revision)
                or proof['candidate_sha256']!=candidate_key(candidate)
                or proof['source_proof']!=SOURCE.row_proof({**row,'state':candidate})):
            raise ValueError('Synthetic reviewed crop proof changed')
    controller.editor=replace(controller.editor,prepare_crop=prepare,verify_crop=verify)
    controller.preflight.ports=replace(controller.preflight.ports,prepare_crop=prepare,verify_crop=verify)
    return controller,rows,current,events,replays,dirty,calls


def preflight(controller,events,docs=(1,)):
    return request(controller,events,'preflight',docs=list(docs),module_scope=[SC.OP_CROP],conflict_policy='recheck')


def test_every_original_crop_target_gets_source_proof_and_private_evidence(tmp_path,monkeypatch):
    c,rows,_,events,replays,dirty,calls=setup(tmp_path,monkeypatch)
    result=preflight(c,events,(1,2));assert result['success'] and result['ok']==2
    assert len(calls)==2 and all(t['crop_transfer'] for t in result['targets'])
    plan=c.preflight.store.get(result['preflight_token'],c.versions.workspace)
    assert plan.source_proof_json is not None
    assert all(t.source_proof_json and t.crop_json and 'SYNTHETIC_NOT_IMAGE' not in t.crop_json for t in plan.targets)
    assert not replays and not dirty and not c.ledger


def test_crop_without_real_adapter_is_reported_blocked_not_admitted(tmp_path,monkeypatch):
    c,rows,_,events,replays,dirty,_=setup(tmp_path,monkeypatch,derived=True)
    c.preflight.ports=replace(c.preflight.ports,prepare_crop=None)
    result=preflight(c,events)
    assert result['success'] and result['ok']==0 and result['targets'][0]['crop_transfer'] is None
    assert not replays and not dirty


def test_tokenless_crop_commit_refuses_even_original_only(tmp_path,monkeypatch):
    c,rows,_,events,replays,dirty,_=setup(tmp_path,monkeypatch)
    before=deepcopy(rows)
    result=request(c,events,'commit',docs=[1],module_scope=[SC.OP_CROP])
    assert not result['success'] and rows==before and not replays and not dirty


@pytest.mark.parametrize('change',['unselected_recipe','source_bytes','missing_proof'])
def test_crop_commit_refuses_stale_full_target_or_missing_review(tmp_path,monkeypatch,change):
    c,rows,_,events,replays,dirty,_=setup(tmp_path,monkeypatch)
    result=preflight(c,events);token=result['preflight_token']
    if change=='unselected_recipe':rows[1]['state']['untouched']['target']=99
    elif change=='source_bytes':(tmp_path/'provenance-1.bin').write_bytes(b'new target source')
    else:
        plan=c.preflight.store.get(token,c.versions.workspace)
        c.preflight.store.pending[token]=replace(plan,targets=tuple(replace(t,crop_json=None) for t in plan.targets))
    before=deepcopy(rows);result=request(c,events,'commit',preflight_token=token)
    assert not result['success'] and rows==before and not replays and not dirty


def test_crop_frozen_source_recipe_survives_source_changes(tmp_path,monkeypatch):
    c,rows,_,events,_,_,_=setup(tmp_path,monkeypatch,derived=True)
    reviewed=preflight(c,events)
    rows[0]['state']['_crop_rect']=(0.,0.,.5,1.)
    c.versions.advance(rows[0])
    result=request(c,events,'commit',preflight_token=reviewed['preflight_token'])
    assert result['success'] and result['source_changed_since_preflight']
    assert rows[1]['state']['_crop_rect']==(.5,0.,1.,1.)
    record=c.ledger[result['batch_id']]['targets']['1']
    assert record['crop_review']['crop']['rect_normalized']==[.5,0.,1.,1.]
    assert 'base64' not in record['crop_review']['preview']


def test_reviewed_crop_group_history_preserves_unrelated_later_edit(tmp_path,monkeypatch):
    c,rows,_,events,_,_,_=setup(tmp_path,monkeypatch,derived=True)
    review=preflight(c,events)
    committed=request(c,events,'commit',preflight_token=review['preflight_token'])
    assert committed['success'];bid=committed['batch_id']
    rows[1]['state']['untouched']['target']=123
    undone=request(c,events,'undo',batch_id=bid)
    assert undone['success'] and rows[1]['state']['_crop_rect']==(0.,0.,1.,1.)
    assert rows[1]['state']['untouched']['target']==123
    redone=request(c,events,'redo',batch_id=bid)
    assert redone['success'] and rows[1]['state']['_crop_rect']==(.5,0.,1.,1.)
    assert rows[1]['state']['untouched']['target']==123


def test_derived_crop_history_without_visual_record_refuses(tmp_path,monkeypatch):
    c,rows,_,events,_,_,_=setup(tmp_path,monkeypatch,derived=True)
    review=preflight(c,events)
    committed=request(c,events,'commit',preflight_token=review['preflight_token'])
    rec=deepcopy(c.ledger[committed['batch_id']]['targets']['1']);rec.pop('crop_review')
    with pytest.raises(ValueError,match='visual proof'):
        verify_history_source(rows[1],rec,[SC.OP_CROP],rec['before'])


def test_visual_target_budget_never_silently_truncates(tmp_path,monkeypatch):
    c,rows,_,events,replays,dirty,calls=setup(tmp_path,monkeypatch)
    c.preflight.ports=replace(c.preflight.ports,targets=lambda docs:(list(range(17)),[]))
    result=preflight(c,events)
    assert not result['success'] and 'sixteen' in result['error']
    assert not calls and not replays and not dirty


def test_active_crop_render_rechecks_known_advance_and_preserves_review_revision(tmp_path,monkeypatch):
    c,rows,_,events,replays,_,_=setup(tmp_path,monkeypatch)
    review=preflight(c,events,(0,1));version=c.versions.version(rows[0]).revision
    committed=request(c,events,'commit',preflight_token=review['preflight_token'])
    assert committed['success'] and replays[0]['strict_local']
    rec=c.ledger[committed['batch_id']]['targets']['0']
    assert rec['crop_review']['revision']==str(version)
    assert c.versions.version(rows[0]).revision==version+1
