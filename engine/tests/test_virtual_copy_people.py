"""Authored virtual-copy portrait regressions. UNRUN: Qoder runtime verification required."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from lumaretouch_engine import people_state as S, virtual_copy_people as V
from lumaretouch_engine.people_graph_owner import PeopleGraphOwner
from lumaretouch_engine.document_versions import DocumentVersions

ASSET='a'*64
OP='test.portrait'


def graph():
    state=S.empty()
    evidence={'backend':'authored_fixture','detector_model_sha256':None,'semantic_model_sha256':None,
              'landmark_digest':None,'status':'synthetic','source_width':640,'source_height':480,
              'orientation':'exif_normalized_once'}
    face=S.new_face(ASSET,(.1,.1,.8,.8),evidence)
    state['faces'][face['face_instance_id']]=face
    state['persons']['confirmed-person']={'anonymous':True}
    state['links']=[{'face_instance_id':face['face_instance_id'],'person_id':'confirmed-person',
                     'state':'confirmed','confirmation_revision':0}]
    return S.check(state),face['face_instance_id']


def fixture():
    state,face_id=graph()
    original={'document_id':'original','copy_number':0,'path':'same.jpg','state':{},
              'undo':[],'redo':[],'fingerprint':{'sha256':ASSET}}
    engine=SimpleNamespace(_docs=[original],_doc_index=0,_doc_path='same.jpg',
                           _people_graph_owner=PeopleGraphOwner(state),_project=None)
    V.activate(engine,original)
    copies=[]
    for number in (1,2):
        row={**deepcopy(original),'document_id':'copy-'+str(number),'copy_number':number}
        V.inherit(engine,original,row);engine._docs.append(row);copies.append(row)
    return engine,original,copies,face_id


def edit(engine,row,face,value):
    owner=V.row_owner(engine,row)
    candidate=S.set_override(owner.snapshot(),'face',face,OP,'/strength',value)
    return owner.commit(candidate,expected_fence=owner.fence)


def test_copy_graphs_isolate_edits_and_keep_confirmed_source_evidence():
    engine,original,(first,second),face=fixture()
    before=V.row_snapshot(engine,original)
    edit(engine,first,face,.7)
    assert V.row_snapshot(engine,original)==before
    assert V.row_snapshot(engine,second)==before
    changed=V.row_snapshot(engine,first)
    assert changed['faces']==before['faces']
    assert changed['links']==before['links']
    assert changed['persons']==before['persons']
    assert S.face_ref(changed['faces'][face])==S.face_ref(before['faces'][face])
    assert changed['faces'][face]['asset_sha256']==ASSET
    assert first['undo']==first['redo']==[]


def test_switch_restores_private_graph_and_cursor_without_replacing_original():
    engine,original,(first,second),face=fixture()
    root_owner=V.row_owner(engine,original)
    engine._doc_index=1;V.activate(engine,first)
    engine._people_cursors[ASSET]=face
    edit(engine,first,face,.4);V.remember(engine)
    engine._doc_index=2;V.activate(engine,second)
    assert engine._people_cursors.get(ASSET) is None
    assert engine._people_graph_owner.snapshot()['overrides']==[]
    engine._doc_index=0;V.activate(engine,original)
    assert engine._people_graph_owner is root_owner
    assert engine._people_graph_owner.snapshot()['overrides']==[]
    engine._doc_index=1;V.activate(engine,first)
    assert engine._people_cursors[ASSET]==face
    assert engine._people_graph_owner.snapshot()['overrides'][0]['value']==.4


def test_copy_roundtrip_keeps_private_recipe_and_detaches_returned_data():
    engine,original,(first,_),face=fixture()
    edit(engine,first,face,.6)
    encoded=V.encode(first)
    restored={'document_id':'copy-1','copy_number':1,'path':'same.jpg'}
    V.decode(restored,{V.KEY:encoded})
    encoded['people_graph']['overrides'][0]['value']=.1
    assert V.row_snapshot(engine,restored)['overrides'][0]['value']==.6
    assert V.encode(original) is None
    with pytest.raises(ValueError):V.decode({'copy_number':1},{})
    isolated_root={'document_id':'independent-root','copy_number':0}
    V.decode(isolated_root,{V.KEY:V.encode(first)})
    assert V.is_private(isolated_root)


def test_save_while_copy_active_keeps_original_graph_at_project_root():
    engine,original,(first,_),face=fixture()
    before=V.row_snapshot(engine,original)
    engine._doc_index=1;V.activate(engine,first);edit(engine,first,face,.5)
    project={'docs':[{V.KEY:V.encode(first)}]}
    V.save_project(engine,project)
    assert project['people_graph']==before
    assert project['docs'][0][V.KEY]['people_graph']['overrides'][0]['value']==.5


def test_exact_row_state_selects_parked_copy_context_even_with_shared_path():
    engine,original,(first,second),face=fixture()
    edit(engine,first,face,.2);edit(engine,second,face,.8)
    assert V.export_context(engine,first['state'],'same.jpg')['people_graph']['overrides'][0]['value']==.2
    assert V.export_context(engine,second['state'],'same.jpg')['people_graph']['overrides'][0]['value']==.8
    assert V.export_context(engine,original['state'],'same.jpg')['people_graph']['overrides']==[]


def test_same_sha_histories_roundtrip_by_document_id():
    from lumaretouch_engine import people_history_persistence as H
    engine,original,copies,face=fixture()
    for index,row in enumerate(engine._docs):
        row['undo']=[{'_people_history':V.row_owner(engine,row).capture_document(ASSET),'authored_marker':index}]
    project={'assets':{}}
    H.save(engine,project)
    assert set(project['people_document_history'])=={'document:original','document:copy-1','document:copy-2'}
    staged,_=H.prepare(project,engine._docs,64)
    assert [staged[i]['undo'][0]['authored_marker'] for i in range(3)]==[0,1,2]
    copies[0]['undo']=[];copies[0]['_history_owned']=True;engine._project=deepcopy(project)
    H.save(engine,project)
    assert set(project['people_document_history'])=={'document:original','document:copy-2'}


def test_legacy_sha_history_matches_original_only_and_unavailable_is_preserved():
    from lumaretouch_engine import people_history_persistence as H
    engine,original,copies,_=fixture()
    project={'assets':{},'people_document_history':{ASSET:{'path':'same.jpg','stacks':{'undo':[],'redo':[]}}}}
    staged,_=H.prepare(project,engine._docs,64)
    assert set(staged)=={0}
    engine._project=deepcopy(project)
    H.save(engine,project)
    assert ASSET in project['people_document_history']
    original['_history_owned']=True
    H.save(engine,project)
    assert not project['people_document_history']


def batch_fixture(monkeypatch):
    from lumaretouch_engine import local_mask_state as SOURCE,people_batch_ledger as L
    engine,original,copies,face=fixture();versions=DocumentVersions()
    for row in engine._docs:versions.version(row)
    monkeypatch.setattr(SOURCE,'source_digest',lambda _path:ASSET)
    monkeypatch.setattr(L,'prepare_scoped',lambda *_args:None)
    engine._people_sync=lambda **_options:None
    engine._write_current_frame=lambda _kind:{}
    engine.doc_state=lambda:{}
    batch=SimpleNamespace(documents=SimpleNamespace(rows=lambda:engine._docs,remember_current=lambda:V.remember(engine)),
                          versions=versions,sequence=0,clock=lambda:1.,monotonic=lambda:1,
                          ledger={},editor=SimpleNamespace(mark_dirty=lambda:None))
    engine._batch_controller=lambda:batch
    return engine,original,copies,face,batch,L


def test_multi_copy_batch_and_protected_undo_never_edit_original(monkeypatch):
    engine,original,copies,face,batch,L=batch_fixture(monkeypatch)
    before=V.row_snapshot(engine,original);plans={}
    for row,value in zip(copies,(.3,.9)):
        state=V.row_snapshot(engine,row)
        plans[V.scope(row)]={'row':row,'before':state,'candidate':S.set_override(state,'face',face,OP,'/strength',value)}
    bid,_=L.commit_scoped(batch,engine,plans,request_id='authored',prepare=False)
    entry=batch.ledger[bid]
    assert {r['document_id'] for r in entry['targets'].values()}=={'copy-1','copy-2'}
    assert V.row_snapshot(engine,original)==before
    L.restore_scoped(engine,entry,False)
    assert all(V.row_snapshot(engine,row)['overrides']==[] for row in copies)
    L.restore_scoped(engine,entry,True)
    assert [V.row_snapshot(engine,row)['overrides'][0]['value'] for row in copies]==[.3,.9]
    edit(engine,copies[0],face,.5)
    with pytest.raises(ValueError,match='protected undo'):
        L.restore_scoped(engine,entry,False)
    assert V.row_snapshot(engine,copies[1])['overrides'][0]['value']==.9
    assert V.row_snapshot(engine,original)==before


def test_confirmed_transfer_accepts_identical_source_sha_in_distinct_documents():
    from lumaretouch_engine.people_confirmed_transfer import prepare_confirmed
    from lumaretouch_engine.people_transfer_adapter import candidate
    engine,original,(first,second),face=fixture()
    source=edit(engine,original,face,.65)
    document=lambda row:{'document_id':row['document_id'],'epoch':'fixture','revision':0}
    for row in (first,second):
        target=V.row_snapshot(engine,row)
        payload=prepare_confirmed(source,target,S.face_ref(source['faces'][face]),ASSET,{OP:['/strength']},
                                  {OP:{'/strength':0.}},source_document=document(original),target_document=document(row))
        result=candidate(payload,source,target,source_document=document(original),target_document=document(row))
        assert result['overrides'][0]['value']==.65
        assert result['faces']==target['faces']
        assert result['links']==target['links']


def test_reviewed_support_records_keep_hashes_and_split_without_rebinding():
    from lumaretouch_engine import eye_light_support as E,people_support_assets as SUPPORT
    engine,original,(first,second),face=fixture()
    root=V.row_owner(engine,original);state=root.snapshot()
    state['faces'][face]['evidence'].update(backend='mediapipe',status='verified',
        detector_model_sha256='b'*64,landmark_digest='c'*64)
    # Authored schema fixture only, not a real reviewed image/model receipt.
    stroke={'version':1,'domain':'source-normalized','objects':[{'id':'fixture-stroke',
        'name':'Authored fixture, not image evidence','enabled':True,'operation':'add','kind':'brush',
        'opacity':1.,'feather':1.,'points':[[.2,.2],[.3,.4]],'axes':[[.03,0],[0,.03]]}]}
    eyes={'left':{'recipe':stroke,'visible':True,'unoccluded':True,'ownership_confirmed':True}}
    state,assets=E.retain(state,{},S.face_ref(state['faces'][face]),eyes)
    root.commit(state,expected_fence=root.fence);engine._people_support=assets
    V.inherit(engine,original,first);V.inherit(engine,original,second)
    original_record=deepcopy(next(iter(assets.values())));original_hash=SUPPORT.content_digest(original_record)
    assert V.row_context(engine,first)['people_support_assets'][original_hash]==original_record
    engine._doc_index=1;V.activate(engine,first)
    copy_graph=V.row_snapshot(engine,first);changed_eyes=deepcopy(eyes)
    changed_eyes['left']['recipe']['objects'][0]['points'][0][0]=.25
    candidate,new_assets=E.retain(copy_graph,engine._people_support,S.face_ref(copy_graph['faces'][face]),changed_eyes)
    copy_owner=V.row_owner(engine,first);copy_owner.commit(candidate,expected_fence=copy_owner.fence)
    engine._people_support=new_assets;V.remember(engine)
    assert V.row_context(engine,original)['people_support_assets']==assets
    assert V.row_context(engine,second)['people_support_assets']==assets
    assert new_assets[original_hash]==original_record
    assert S.face_ref(candidate['faces'][face])==S.face_ref(state['faces'][face])
    project={'docs':[{V.KEY:V.encode(first)},{V.KEY:V.encode(second)}]}
    V.save_project(engine,project)
    assert len(project['people_support_assets'])==2
    assert project['people_graph']['faces'][face]['local_assets']==state['faces'][face]['local_assets']


def test_multi_copy_publish_failure_rolls_back_all_started_scopes(monkeypatch):
    engine,original,copies,face,batch,L=batch_fixture(monkeypatch)
    original_before=V.row_snapshot(engine,original);plans={}
    for row in copies:
        before=V.row_snapshot(engine,row)
        plans[V.scope(row)]={'row':row,'before':before,'candidate':S.set_override(before,'face',face,OP,'/strength',.4)}
    second_owner=V.row_owner(engine,copies[1])
    def refuse(*_args,**_options):raise ValueError('Authored second-owner failure')
    monkeypatch.setattr(second_owner,'commit',refuse)
    with pytest.raises(ValueError,match='second-owner'):
        L.commit_scoped(batch,engine,plans,request_id='failure',prepare=False)
    assert all(V.row_snapshot(engine,row)['overrides']==[] for row in copies)
    assert V.row_snapshot(engine,original)==original_before
    assert not batch.ledger
    assert V.row_owner(engine,copies[0]).fence>0


def test_originals_keep_their_explicit_cross_photo_shared_person_graph():
    engine,original,(first,_),face=fixture()
    root=V.row_owner(engine,original);state=root.snapshot()
    second_face=S.new_face('b'*64,(.1,.1,.8,.8),state['faces'][face]['evidence'])
    state['faces'][second_face['face_instance_id']]=second_face
    state['links'].append({'face_instance_id':second_face['face_instance_id'],'person_id':'confirmed-person',
                           'state':'confirmed','confirmation_revision':0})
    root.commit(state,expected_fence=root.fence)
    other={'document_id':'another-original','copy_number':0,'path':'other.jpg','state':{}}
    engine._docs.append(other);V.inherit(engine,original,first)
    copy_before=V.row_snapshot(engine,first)
    candidate=S.set_override(root.snapshot(),'person','confirmed-person',OP,'/strength',.45)
    root.commit(candidate,expected_fence=root.fence)
    assert V.row_owner(engine,other) is root
    assert V.row_snapshot(engine,other)['links']==state['links']
    assert V.row_snapshot(engine,other)['overrides'][0]['scope']=='person'
    assert V.row_snapshot(engine,first)==copy_before


def test_new_same_bytes_root_is_private_empty_without_cloning_existing_links(monkeypatch):
    from lumaretouch_engine import local_mask_state as SOURCE
    engine,original,_,face=fixture()
    original['source_asset_id']='source-original'
    before=edit(engine,original,face,.8)
    fresh={'document_id':'independent','source_asset_id':'different-logical-source','copy_number':0,
           'path':'identical-at-other-path.jpg','state':{},'_people_new_import':True}
    engine._docs.append(fresh);calls=[]
    monkeypatch.setattr(SOURCE,'source_digest',lambda path:(calls.append(path),ASSET)[1])
    engine._doc_index=len(engine._docs)-1;V.activate(engine,fresh)
    assert calls==['identical-at-other-path.jpg']
    assert V.is_private(fresh)
    assert V.row_snapshot(engine,fresh)==S.empty()
    assert V.row_context(engine,fresh)['people_support_assets']=={}
    assert V.row_snapshot(engine,original)==before
    assert V.scope(fresh)=='independent'
    restored={'document_id':'independent','copy_number':0}
    V.decode(restored,{V.KEY:V.encode(fresh)})
    assert V.row_snapshot(engine,restored)==S.empty()


def test_query_peek_does_not_hash_or_classify_unopened_independent_root(monkeypatch):
    from lumaretouch_engine import local_mask_state as SOURCE
    engine,_,_,_=fixture()
    fresh={'document_id':'fresh','source_asset_id':'fresh-source','copy_number':0,
           'path':'never-read.jpg','state':{},'_people_new_import':True}
    engine._docs.append(fresh)
    def forbidden(_path):raise AssertionError('A library query must not hash any source')
    monkeypatch.setattr(SOURCE,'source_digest',forbidden)
    before=deepcopy(fresh)
    assert V.peek_graph(engine,fresh) is None
    assert fresh==before


def test_save_classifies_fingerprinted_unopened_duplicate_without_source_reads(monkeypatch):
    from lumaretouch_engine import local_mask_state as SOURCE
    engine,original,_,_=fixture();original['source_asset_id']='original-source'
    fresh={'document_id':'fresh','source_asset_id':'fresh-source','copy_number':0,
           'path':'identical.jpg','state':{},'_people_new_import':True,'fingerprint':{'sha256':ASSET}}
    engine._docs.append(fresh)
    def forbidden(_path):raise AssertionError('Save must reuse its already acquired fingerprint')
    monkeypatch.setattr(SOURCE,'source_digest',forbidden)
    project={'docs':[{'document_id':row['document_id']} for row in engine._docs]}
    V.save_project(engine,project)
    stored=next(row for row in project['docs'] if row['document_id']=='fresh')
    assert stored[V.KEY]['people_graph']==S.empty()
    assert not fresh['_people_new_import']
    assert V.is_private(fresh)
