"""Authored regression cases, UNRUN by the implementation agent. Qoder executes."""
from dataclasses import replace
from pathlib import Path
import json
import os
import pytest
from lumaretouch_engine.export_destination_policy import Source, Policy, freeze, restore, DestinationError
from lumaretouch_engine.export_destination_commit import commit_encoded_bytes, CommitFailure
from lumaretouch_engine.export_destination_import import origin, expand
from lumaretouch_engine import export_destination_runtime as runtime


def source(tmp_path, *, item='document:one', folder='source', name='photo.jpg'):
    root = tmp_path/folder
    root.mkdir(parents=True,exist_ok=True)
    path = root/name
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists(): path.write_bytes(b'untouched-original')
    return Source(item,str(path),str(root),'frozen-frame-'+item,Path(name).name)


def policy(tmp_path, **kwargs):
    return Policy(chosen_root=str(tmp_path/'delivery'),create_missing=True,**kwargs)


def test_relative_hierarchy_and_roundtrip(tmp_path):
    row = source(tmp_path,name='nested/photo.jpg')
    plan = freeze([row],policy(tmp_path,retain_hierarchy=True),{'bit_depth':16,'metadata_include_gps':False},7)
    assert plan.entries[0].target == str(tmp_path/'delivery/source/nested/photo.jpg')
    assert restore(json.loads(json.dumps(plan.payload()))) == plan
    assert not (tmp_path/'delivery').exists()  # preview never mkdir


def test_source_folder_never_overwrites_original(tmp_path):
    row = source(tmp_path)
    plan = freeze([row],Policy(mode='source_folder',source_subfolder='none',conflict='rename'),{},1)
    assert plan.entries[0].target.endswith('photo-0001.jpg')
    assert Path(row.source_path).read_bytes() == b'untouched-original'


def test_same_leaf_roots_remain_distinct_and_deterministic(tmp_path):
    a = source(tmp_path,item='a',folder='a/session')
    b = source(tmp_path,item='b',folder='b/session')
    p = policy(tmp_path,retain_hierarchy=True)
    first = freeze([a,b],p,{},1); second = freeze([b,a],p,{},1)
    assert first == second
    assert len({e.target for e in first.entries}) == 2
    assert all('/session-' in e.target for e in first.entries)


def test_virtual_copies_have_independent_targets(tmp_path):
    a = source(tmp_path,item='original')
    b = replace(a,item_id='copy',frame_receipt='other-frozen-frame')
    plan = freeze([a,b],policy(tmp_path),{},1)
    assert len({e.target for e in plan.entries}) == 2
    assert {e.frame_receipt for e in plan.entries} == {a.frame_receipt,b.frame_receipt}


def test_ask_collision_is_not_a_write(tmp_path):
    row = source(tmp_path)
    Path(tmp_path/'delivery').mkdir()
    Path(tmp_path/'delivery/photo.jpg').write_bytes(b'old')
    plan = freeze([row],policy(tmp_path,conflict='ask'),{},1)
    assert plan.entries[0].disposition == 'needs_confirmation'


def test_missing_requires_explicit_creation_choice(tmp_path):
    row = source(tmp_path)
    with pytest.raises(DestinationError,match='destination_missing'):
        freeze([row],Policy(chosen_root=str(tmp_path/'missing')),{},1)


@pytest.mark.parametrize('name',['../outside.jpg','/outside.jpg','bad\\name.jpg','\0.jpg'])
def test_target_name_traversal_rejected(tmp_path,name):
    row = replace(source(tmp_path),target_filename=name)
    with pytest.raises(DestinationError): freeze([row],policy(tmp_path),{},1)


def test_symlink_destination_rejected(tmp_path):
    row=source(tmp_path)
    (tmp_path/'real').mkdir(); (tmp_path/'delivery').symlink_to(tmp_path/'real',target_is_directory=True)
    with pytest.raises(DestinationError): freeze([row],policy(tmp_path),{},1)


def test_relocation_preserves_logical_import_tree(tmp_path):
    old=source(tmp_path,name='nested/photo.jpg')
    provenance=origin(old.source_path,old.import_root,kind='directory')
    relocated=tmp_path/'relocated.jpg'; Path(old.source_path).rename(relocated)
    row=replace(old,source_path=str(relocated),import_relative=provenance['relative'])
    plan=freeze([row],policy(tmp_path,retain_hierarchy=True),{},1)
    assert plan.entries[0].target == str(tmp_path/'delivery/source/nested/photo.jpg')


def test_publish_no_clobber_and_cancel(tmp_path):
    target=tmp_path/'output.jpg'; target.write_bytes(b'original')
    with pytest.raises(CommitFailure) as failure: commit_encoded_bytes(str(target),b'new')
    assert failure.value.committed is False
    assert target.read_bytes() == b'original'
    cancelled=commit_encoded_bytes(str(tmp_path/'cancelled.jpg'),b'new',cancelled=lambda:True)
    assert cancelled['cancelled'] and not cancelled['committed']
    assert not (tmp_path/'cancelled.jpg').exists()


def test_publication_creates_only_authorized_missing_directories(tmp_path):
    target=tmp_path/'missing/output.jpg'
    with pytest.raises(CommitFailure): commit_encoded_bytes(str(target),b'data')
    result=commit_encoded_bytes(str(target),b'data',create_missing=True)
    assert result['committed'] and target.read_bytes()==b'data'


def test_retry_preserves_target_and_refuses_existing_output(tmp_path):
    row=source(tmp_path)
    plan=freeze([row],policy(tmp_path),{},1)
    target=plan.entries[0].target
    def write():
        resolved=runtime.resolve(target)
        assert resolved == (target,None)
        return commit_encoded_bytes(target,b'output',create_missing=runtime.create_missing())
    runtime.run(plan.payload(),row.item_id,write)
    with pytest.raises(DestinationError,match='冻结输出已存在'):
        runtime.run(plan.payload(),row.item_id,write)
    assert Path(target).read_bytes()==b'output'
    assert not Path(target).with_name('photo-0001.jpg').exists()


def test_folder_import_records_explicit_root(tmp_path):
    row=source(tmp_path,name='nested/photo.jpg')
    files,provenance=expand([row.import_root],{'.jpg'},100)
    assert files==[row.source_path]
    assert provenance[row.source_path]['relative']=='nested/photo.jpg'
