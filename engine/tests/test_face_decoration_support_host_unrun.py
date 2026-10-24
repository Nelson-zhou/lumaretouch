# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: canonical support and receipt fixtures.

Synthetic identities and mocked source decoding/publication are unit contracts,
not real portraits, native execution, visual acceptance or a passing test run.
"""
from base64 import b64encode
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from lumaretouch_engine import people_state as P, people_support_assets as BANK
from lumaretouch_engine import face_decoration_support as V, face_decoration_host as H
from lumaretouch_engine import face_decoration_state as D, people_host_commands as COMMANDS

ASSET = 'a'*64


def graph():
    value = P.empty()
    evidence = {'backend':'mediapipe','detector_model_sha256':'b'*64,'semantic_model_sha256':'c'*64,
        'landmark_digest':'d'*64,'status':'verified','source_width':100,'source_height':100,
        'orientation':'exif_normalized_once'}
    face = P.new_face(ASSET,[.1,.1,.9,.9],evidence)
    value['faces'][face['face_instance_id']] = face
    return value,P.face_ref(face)


def region():
    return {'visible':True,'unoccluded':True,'ownership_confirmed':True,
        'recipe':{'version':1,'domain':'source-normalized','objects':[{
            'id':'nose-and-cheek','name':'visible skin','enabled':True,'operation':'add','kind':'brush',
            'opacity':1.,'feather':20.,'points':[[.3,.5],[.5,.5],[.7,.5]],'axes':[[.05,0],[0,.05]]}]}}


def test_independent_single_region_immutable_and_exact_source_binding():
    state,ref = graph(); before = deepcopy(state)
    candidate,bank = V.retain(state,{},ref,region()); BANK.check_store(bank)
    record,key = V.resolve(candidate,bank,ref)
    assert state == before and candidate['revision'] == state['revision']+1
    assert set(record['row']) == {'target','landmark_digest','region'}
    assert record['row']['target'] == 'face_decoration_visibility'
    assert record['source'] == {'sha256':ASSET,'width':100,'height':100}
    assert key == BANK.content_digest(record)
    assert 'blush_makeup_visibility' not in candidate['faces'][ref['face_instance_id']]['local_assets']
    with pytest.raises(ValueError): V.resolve(candidate,bank,{**ref,'analysis_revision':1})
    stale = deepcopy(candidate); stale['faces'][ref['face_instance_id']]['evidence']['landmark_digest'] = 'e'*64
    with pytest.raises(ValueError): V.resolve(stale,bank,ref)
    with pytest.raises(ValueError): V.validate_project({'people_graph':candidate,'people_support_assets':{}})
    V.validate_project({'people_support_assets':bank,'history':{'undo':[{'people_graph':candidate}]}})


@pytest.mark.parametrize('field',['visible','unoccluded','ownership_confirmed'])
def test_separate_consent_cannot_be_inferred(field):
    state,ref = graph(); painted = region(); painted[field] = False
    with pytest.raises(ValueError): V.retain(state,{},ref,painted)
    with pytest.raises(ValueError): V.retain(state,{},ref,{'cheeks':{'left':region(),'right':region()}})


def test_corrupt_vectors_and_cross_operation_assets_are_rejected():
    state,ref = graph(); candidate,bank = V.retain(state,{},ref,region())
    key = next(iter(bank)); corrupted = deepcopy(bank)
    corrupted[key]['row']['region']['recipe']['objects'][0]['points'] = [[.1,.1]]
    with pytest.raises(ValueError): BANK.check_store(corrupted)
    borrowed = deepcopy(bank[key]); borrowed['row']['target'] = 'blush_makeup_visibility'
    with pytest.raises(ValueError): V.check_record(borrowed)
    other = deepcopy(candidate); other['faces'][ref['face_instance_id']]['local_assets'][V.KIND]['owner']['analysis_revision'] += 1
    with pytest.raises(ValueError): V.resolve(other,bank,ref)


@pytest.fixture
def host(monkeypatch):
    from lumaretouch_engine import body_pose_commands as BODY, face_decoration_native as N
    from lumaretouch_engine import creative_derived_source as SOURCE
    state,ref = graph(); key = ref['face_instance_id']
    target = {'scope':'face','target_id':key,'face_ref':ref}
    row = {'document_id':'doc-decoration','path':'fixture.png','state':{},'revision':4}
    owner = SimpleNamespace(value=state,fence=0); owner.snapshot=lambda:deepcopy(owner.value)
    engine = SimpleNamespace(_docs=[row],_doc_index=0,_people_scope_row=row,_people_graph_owner=owner,
        _people_active_context={'owner':owner},_people_support={},_people_analyses={},
        _people_targets={ASSET:deepcopy(target)},_people_cursors={ASSET:key},
        _vram=SimpleNamespace(people_prepared=None,people_suspended=None),
        _guard_editable=lambda _:None,_people_bind=Mock(side_effect=AssertionError('Read must not initialize/migrate')))
    source = {'sha256':ASSET,'width':100,'height':100}
    engine._people_owner=lambda:owner; engine._people_source=lambda:deepcopy(source)
    engine._people_binding=lambda:{'document_id':row['document_id'],'document_epoch':'epoch',
                                  'document_revision':row['revision'],'asset_sha256':ASSET}
    engine.doc_state=lambda:{'people':{'revision':owner.value['revision'],'association_revision':owner.value['association_revision'],
        'binding':engine._people_binding(),'editing_target':deepcopy(target),'selected_face_id':key,
        'face_decoration':H.report(engine,owner.snapshot(),source,key)}}
    engine._people_prepare_graph=Mock()
    def publish(candidate,assets):
        owner.value=deepcopy(candidate); owner.fence+=1; row['revision']+=1
        return {'event':'frame','doc_state':engine.doc_state()}
    engine._people_publish_graph=publish
    monkeypatch.setattr(SOURCE,'row_asset',lambda _:ASSET)
    monkeypatch.setattr(N,'available',lambda:False)
    # This mocked decoder boundary is not a valid-PNG or photographic fixture.
    raw=b'AUTHORED SOURCE-DECODER MOCK, NOT PHOTO ACCEPTANCE'
    monkeypatch.setattr(BODY,'source_preview',lambda _:{'mime':'image/png','base64':b64encode(raw).decode(),
        'width':100,'height':100,'source_sha256':ASSET,'source_width':100,'source_height':100,
        'decoded_width':100,'decoded_height':100,'mapping':'normalized_full_frame','orientation':'exif_normalized_once'})
    def command(action,payload,request):
        return {'cmd':'people',**{k:v for k,v in engine._people_binding().items() if k!='asset_sha256'},
            'state_revision':owner.value['revision'],'association_revision':owner.value['association_revision'],
            'target':deepcopy(target),'action':action,'payload':deepcopy(payload),'request_id':request}
    return engine,owner,target,command,raw


def test_reference_read_then_review_share_canonical_receipts_and_no_duplicate_png(host):
    engine,owner,target,command,raw = host; events=[]
    read=command('face_decoration_reference',{},'reference-1')
    assert COMMANDS.face_decoration_read_only(read)
    COMMANDS.apply(engine,read,events.append); COMMANDS.finish(engine,read,None,events.append)
    receipt=events[-1]; body=receipt['payload']; report=receipt['doc_state']['people']['face_decoration']
    assert receipt['success'] and not receipt['outcome_unknown']
    assert set(body)=={'kind','reference_proof'} and report['source_preview']['sha256']==sha256(raw).hexdigest()
    assert body['reference_proof']==report['reference_proof']
    assert owner.value['revision']==0 and engine._docs[0]['revision']==4
    assert receipt['face_decoration_request']=={k:v for k,v in read.items() if k not in ('cmd','request_id')}
    engine._people_bind.assert_not_called(); engine._people_prepare_graph.assert_not_called()
    review=command('face_decoration_review',{'reference_proof':body['reference_proof'],'region':region()},'review-1')
    assert not COMMANDS.face_decoration_read_only(review)
    COMMANDS.apply(engine,review,events.append); COMMANDS.finish(engine,review,None,events.append)
    result=events[-1]; final=result['doc_state']['people']['face_decoration']
    assert result['success'] and owner.value['revision']==1 and engine._docs[0]['revision']==5
    assert final['reviewed'] and final['support_sha256']==result['payload']['support_sha256']
    assert final['support_available'] is False  # Missing analysis does not erase retained consent.
    assert final['source_preview'] is None and final['reference_proof'] is None
    engine._people_prepare_graph.assert_called_once()


@pytest.mark.parametrize('fault',['document','graph','association','hash','reference-request','target'])
def test_stale_reference_cannot_authorize_support(host,fault):
    engine,owner,target,command,_=host
    body=H.reference(engine,owner.snapshot(),target,{},request_id='reference-1')
    payload={'region':region(),'reference_proof':body['reference_proof']}
    if fault=='document':engine._docs[0]['revision']+=1
    elif fault=='graph':owner.value['revision']+=1
    elif fault=='association':owner.value['association_revision']+=1
    elif fault=='hash':payload['reference_proof']['preview_sha256']='f'*64
    elif fault=='reference-request':payload['reference_proof']['reference_request_id']='foreign'
    else:engine._people_targets[ASSET]={'scope':'all_people','target_id':ASSET,'face_ref':None}
    with pytest.raises(ValueError):H.stage_review(engine,owner.snapshot(),target,payload)
    assert engine._people_support=={}


def test_review_missing_source_reference_and_aliases_refuse_without_publication(host):
    engine,owner,target,command,_=host
    proof={'source':engine._people_source(),'face_ref':target['face_ref'],'landmark_digest':'d'*64,
           'preview_sha256':'e'*64,'reference_request_id':'invented'}
    with pytest.raises(ValueError):H.stage_review(engine,owner.snapshot(),target,{'region':region(),'reference_proof':proof})
    body=H.reference(engine,owner.snapshot(),target,{},request_id='ref')
    engine._docs.append({'document_id':'alias','path':'same.png','state':{}})
    with pytest.raises(ValueError):H.stage_review(engine,owner.snapshot(),target,{'region':region(),'reference_proof':body['reference_proof']})
    assert owner.value['revision']==0 and engine._people_support=={}


def test_old_read_images_are_bounded_without_changing_mutation_outcomes(host):
    engine,owner,target,command,_=host; events=[]
    for index in range(4):
        read=command('face_decoration_reference',{},'reference-'+str(index))
        COMMANDS.apply(engine,read,events.append); COMMANDS.finish(engine,read,None,events.append)
    results=[row['result'] for row in engine._people_receipts.values()]
    assert sum('doc_state' in row for row in results)==1
    for result in results[:-1]:
        assert result['success'] is True and result['outcome_unknown'] is False
        assert result['payload_released'] is True and 'payload' not in result and 'doc_state' not in result
        assert result['face_decoration_request']['action']=='face_decoration_reference'
    # A non-decoration mutation receipt can have a duplicate display view, but
    # pruning must retain its original terminal outcome and unrelated state.
    latest=deepcopy(results[-1]);latest.update(action='patch',request_id='mutation',success=False,
                                               outcome_unknown=True,error='fixture unknown')
    engine._people_receipts['mutation']={'digest':'unchanged','result':latest}
    H.bound_receipt_images(engine._people_receipts)
    assert latest['success'] is False and latest['outcome_unknown'] is True and latest['error']=='fixture unknown'
    assert latest['doc_state']['people']['face_decoration']['source_preview'] is None
    assert engine._people_receipts['mutation']['digest']=='unchanged'
