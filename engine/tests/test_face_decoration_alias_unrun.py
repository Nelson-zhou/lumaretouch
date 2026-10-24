# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN scalar alias contracts; no image quality acceptance."""
from copy import deepcopy
from pathlib import Path
import pytest
from lumaretouch_engine import people_state as S, face_decoration_state as D
from lumaretouch_engine import face_decoration_alias_history as H
from lumaretouch_engine import face_decoration_alias_review as R


@pytest.fixture
def graph():
    state=S.empty()
    face=S.new_face('a'*64,[.2,.1,.8,.9],{
        'backend':'synthetic','detector_model_sha256':None,'semantic_model_sha256':None,
        'landmark_digest':None,'status':'synthetic','source_width':128,'source_height':160,
        'orientation':'exif_normalized_once'})
    state['faces'][face['face_instance_id']]=face
    return state,S.face_ref(face)


def target(ref):
    return {'scope':'face','target_id':ref['face_instance_id'],'face_ref':ref}


def changed(state,ref,recipe):
    for patch in D.patches(recipe):
        state=S.set_override(state,'face',ref['face_instance_id'],D.OP,
                             patch['parameter_path'],patch['value'])
    return state


def test_only_explicit_scalar_recipe_enters_review(graph):
    state,ref=graph
    R.check_action('face_decoration_alias_preview',{'recipe':D.neutral()},target(ref))
    for payload in ({'recipe':None},{'recipe':D.neutral(),'support':{}},
                    {'recipe':{**D.neutral(),'visibility':[]}}):
        with pytest.raises(ValueError):
            R.check_action('face_decoration_alias_preview',payload,target(ref))
    with pytest.raises(ValueError):
        R.check_action('face_decoration_alias_preview',{'recipe':D.neutral()},
                       {'scope':'all_people','target_id':ref['asset_sha256']})


def test_neutral_is_real_intent_but_exact_noop_has_no_authority(graph):
    before,ref=graph
    active=changed(before,ref,{**D.neutral(),'strength':.6})
    neutral=changed(active,ref,D.neutral())
    assert H.scalar_changes(active,neutral,[ref])
    assert H.scalar_changes(neutral,active,[ref])
    # Undo may remove the original explicit scalar override, not support bytes.
    assert H.scalar_changes(active,before,[ref])
    with pytest.raises(ValueError):H.scalar_changes(active,active,[ref])


def test_pattern_is_a_string_leaf_not_an_eye_amount(graph):
    before,ref=graph
    candidate=changed(before,ref,{**D.neutral(),'pattern':'mole_pair','strength':.7})
    changes=H.scalar_changes(before,candidate,[ref])
    assert len(changes)==2
    assert any(c['key'][-1]=='/pattern' and c['after']['value']=='mole_pair' for c in changes)


def test_scalar_authority_rejects_identity_support_and_foreign_effect(graph):
    before,ref=graph
    candidate=changed(before,ref,D.neutral())
    bad=deepcopy(candidate);bad['association_revision']+=1
    with pytest.raises(ValueError):H.scalar_changes(before,bad,[ref])
    bad=deepcopy(candidate);bad['faces'][ref['face_instance_id']]['enabled']=False
    with pytest.raises(ValueError):H.scalar_changes(before,bad,[ref])
    bad=deepcopy(candidate);bad['overrides'][0]['operation_id']='lnx.eye_bag_preserve.v2'
    with pytest.raises(ValueError):H.scalar_changes(before,bad,[ref])
    with pytest.raises(ValueError):H.scalar_changes(before,candidate,[{**ref,'face_instance_id':'foreign-face'}])


def test_exact_image_address_and_ack_order(graph):
    _,ref=graph
    payload={'token':'a'*32,'document_id':'document-a','side':'after','sha256':'b'*64}
    R.check_action('face_decoration_alias_image',payload,target(ref))
    for addition in ({'pixels':[]},{'revision':'1'},{'side':'support'}):
        with pytest.raises(ValueError):
            R.check_action('face_decoration_alias_image',{**payload,**addition},target(ref))
    review={'token':'a'*32,'review_sha256':'b'*64,'recipe':D.neutral(),
            'candidate_state_revision':4,'members':[{'visual':{'document_id':d,'revision':'2',
            'before':{'sha256':'c'*64},'after':{'sha256':'d'*64}}} for d in ('one','two')]}
    proof=R._proof(review)
    assert proof['history_review_sha256']==R.digest(proof['ack'])
    assert proof['history_review_sha256']!=review['review_sha256']
    assert [m['document_id'] for m in proof['alias_members']]==['one','two']
    assert all(m['result_revision']=='3' for m in proof['alias_members'])


def test_source_hooks_keep_old_defaults_and_exact_uncertainty_claim():
    root=Path(__file__).parents[1]/'src'/'lumaretouch_engine'
    review=(root/'face_decoration_alias_review.py').read_text()
    ledger=(root/'people_batch_ledger.py').read_text()
    persistence=(root/'people_history_persistence.py').read_text()
    assert "engine._batch_controller() is not entry['batch']" in review
    assert "mark_started();entry['claimed']=True" in review
    assert "SOURCE.verify_row({**other,'state':own},source_proof)" in review
    assert "extra={'decoration_authority':authority} if authority is not None else {}" in ledger
    assert 'face_decoration_alias_history' in ledger and 'verify_da(engine,batch,plans,targets)' in ledger
    assert persistence.count('from .face_decoration_alias_history import check as check_da')==2
    # Scalar alias is never a support asset staging authority.
    assert 'stage_review' not in review and 'append_support' not in review
