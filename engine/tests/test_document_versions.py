from copy import deepcopy
from lumaretouch_engine.document_versions import DocumentVersions,KEY,fences_current_document


def test_reorder_and_reconstructed_records_retain_identity_but_new_imports_do_not():
    versions=DocumentVersions();a={'path':'same'};b={'path':'other'}
    original=versions.version(a);versions.version(b)
    assert versions.find([b,a],original.document_id)==(1,a)
    assert versions.version(deepcopy(a)).document_id==original.document_id  # persisted record, not a create-copy action
    assert versions.version({'path':'same'}).document_id!=original.document_id


def test_fence_does_not_rewind_when_recipe_returns_to_previous_value():
    versions=DocumentVersions();row={'state':{'ev':0}}
    first=versions.version(row)
    row['state']={'ev':1};versions.advance(row)
    row['state']={'ev':0};versions.advance(row)
    assert versions.version(row).revision==first.revision+2
    assert KEY not in row['state']


def test_new_workspace_invalidates_context_without_rewriting_retained_row_identity():
    versions=DocumentVersions();row={};before=versions.version(row);workspace=versions.workspace
    versions.new_workspace()
    assert versions.workspace!=workspace and versions.version(row)==before
    other=DocumentVersions();assert other.version(row).document_id==before.document_id
    assert other.workspace != versions.workspace  # persistent identity, fresh admission epoch


def test_command_fence_excludes_pure_reads_selection_and_batch_owned_writes():
    edits={'exposure','curves','batch','preset'}
    assert fences_current_document('exposure',{'action':'set'},edits)
    assert fences_current_document('history',{'action':'undo'},edits)
    assert fences_current_document('history',{'action':'redo'},edits)
    assert fences_current_document('precompute',{},edits)
    for name,p in [('exposure',{'action':'state'}),('batch',{'action':'commit'}),('preset',{'action':'save'}),
                   ('history',{'action':'state'}),('session',{'action':'select'}),('load_image',{}),('compare',{}),('color_capture',{'action':'sample'})]:
        assert not fences_current_document(name,p,edits)
