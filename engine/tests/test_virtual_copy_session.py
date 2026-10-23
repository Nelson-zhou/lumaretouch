"""Authored acceptance tests; UNRUN in the restricted implementation pass."""
import threading
from types import SimpleNamespace
import pytest
from lumaretouch_engine.virtual_copy_session import index_of, rows_from
from lumaretouch_engine.virtual_copy_host import affected


def row(identity, root, number, path='/source.jpg'):
    return {'document_id':identity,'root_document_id':root,'source_asset_id':root,
            'copy_number':number,'path':path,'trashed':False}


def test_selection_never_collapses_same_path_recipes():
    rows=[row('a','a',0),row('b','a',1)]
    assert index_of(rows,'/source.jpg','b')==1
    with pytest.raises(ValueError):index_of(rows,'/source.jpg')


def test_unsaved_rescan_retains_copy_family_and_current_object():
    original,copy,other=row('a','a',0),row('b','a',1),row('c','c',0,'/other.jpg')
    engine=SimpleNamespace(_docs=[original,copy,other],_doc_index=2,_project=None,_doclock=threading.RLock(),
                           _new_row=lambda path:row('new','new',0,path))
    result=rows_from(engine,['/new.jpg'])
    assert all(any(candidate is old for candidate in result) for old in (original,copy,other))
    assert engine._docs[engine._doc_index] is other


def test_add_same_path_retains_every_explicit_document_once():
    rows=[row('a','a',0),row('b','a',1)]
    engine=SimpleNamespace(_docs=rows,_doc_index=1,_project=None,_doclock=threading.RLock(),
                           _new_row=lambda _:pytest.fail('must not reimport'))
    assert rows_from(engine,['/source.jpg','/source.jpg'])==rows
    assert engine._doc_index==1


def test_review_closure_matches_linked_semantics():
    rows=[row('a','a',0),row('b','a',1),row('c','a',2)]
    assert [r['document_id'] for r in affected(rows,['a'],'trash')]==['a','b','c']
    assert [r['document_id'] for r in affected(rows,['b'],'trash')]==['b']
    assert [r['document_id'] for r in affected(rows,['b'],'restore')]==['a','b']
    assert [r['document_id'] for r in affected(rows,['a'],'restore')]==['a']
