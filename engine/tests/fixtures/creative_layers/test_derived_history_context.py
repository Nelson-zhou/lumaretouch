"""UNRUN source-context fixtures; no inference or runtime verification claimed."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from lumaretouch_engine import people_state as S
from lumaretouch_engine import local_mask_state as SOURCE
from lumaretouch_engine.people_graph_owner import PeopleGraphOwner
from lumaretouch_engine.people_host import PeopleHostMixin
from lumaretouch_engine.people_source_context import digest

ORIGINAL='a'*64
DERIVED='b'*64


def graph():
    state=S.empty()
    evidence={'backend':'authored_fixture','detector_model_sha256':None,
              'semantic_model_sha256':None,'landmark_digest':None,
              'status':'synthetic','source_width':640,'source_height':480,
              'orientation':'exif_normalized_once'}
    for asset,key in ((ORIGINAL,'original-face'),(DERIVED,'derived-face')):
        face=S.new_face(asset,(.1,.1,.8,.8),evidence)
        face['face_instance_id']=key
        state['faces'][key]=face
    state['persons']={'original-person':{'anonymous':True},'other-person':{'anonymous':True}}
    state['links']=[{'face_instance_id':'original-face','person_id':'original-person',
                     'state':'confirmed','confirmation_revision':0}]
    state['groups']={'original-group':{'label':'Original','priority':0,'face_ids':['original-face']}}
    return S.check(state)


def test_unrelated_global_revisions_and_other_source_edits_keep_context():
    before=graph();after=deepcopy(before)
    after['revision']=10;after['association_revision']=7
    after['faces']['derived-face']['enabled']=False
    after['groups']['other-group']={'label':'Other','priority':9,'face_ids':['derived-face']}
    after['links'].append({'face_instance_id':'derived-face','person_id':'other-person',
                          'state':'confirmed','confirmation_revision':7})
    after=S.set_override(after,'face','derived-face','fixture.operation','/amount',.8)
    assert digest(before,ORIGINAL)==digest(after,ORIGINAL)
    assert digest(before,DERIVED)!=digest(after,DERIVED)


@pytest.mark.parametrize('change',['link','group','person_override','group_override','local_recipe'])
def test_relevant_associations_and_effective_recipes_change_context(change):
    before=graph();after=deepcopy(before)
    if change=='link':
        after['links'][0]['state']='unresolved'
    elif change=='group':
        after['groups']['original-group']['priority']=5
    elif change=='person_override':
        after=S.set_override(after,'person','original-person','fixture.operation','/amount',.5)
    elif change=='group_override':
        after=S.set_override(after,'group','original-group','fixture.operation','/amount',.5)
    else:
        after=S.set_override(after,'face','original-face','fixture.operation','/amount',.5)
    assert digest(before,ORIGINAL)!=digest(after,ORIGINAL)


def source_switch_fixture(monkeypatch,*,change_context=False,legacy=False):
    original=graph();capture=PeopleGraphOwner(original).capture_document(ORIGINAL)
    if not legacy:capture['source_context_sha256']=digest(original,ORIGINAL)
    current=deepcopy(original);current['association_revision']=3;current['revision']=4
    if change_context:current['links'][0]['state']='unresolved'
    owner=PeopleGraphOwner(current)
    engine=SimpleNamespace(_doc_path='authored-original.png',_people_analysis_key='stale',
                           _people_owner=lambda:owner,
                           _people_source=lambda:{'sha256':DERIVED,'width':640,'height':480})
    monkeypatch.setattr(SOURCE,'source_digest',lambda path:ORIGINAL)
    return engine,owner,capture


def test_proven_original_source_switch_tolerates_unrelated_association_counter(monkeypatch):
    engine,owner,capture=source_switch_fixture(monkeypatch)
    before=owner.snapshot();fence=owner.fence
    PeopleHostMixin._people_history_apply(engine,capture,source_state={})
    assert owner.snapshot()==before
    assert owner.fence==fence
    assert engine._people_analysis_key is None


def test_source_switch_refuses_altered_relevant_shared_context(monkeypatch):
    engine,owner,capture=source_switch_fixture(monkeypatch,change_context=True)
    before=owner.snapshot()
    with pytest.raises(ValueError,match='associations or effective recipe changed'):
        PeopleHostMixin._people_history_apply(engine,capture,source_state={})
    assert owner.snapshot()==before


def test_legacy_source_switch_without_proof_still_fails_closed(monkeypatch):
    engine,owner,capture=source_switch_fixture(monkeypatch,legacy=True)
    before=owner.snapshot()
    with pytest.raises(ValueError,match='Retained source portrait recipe changed'):
        PeopleHostMixin._people_history_apply(engine,capture,source_state={})
    assert owner.snapshot()==before
