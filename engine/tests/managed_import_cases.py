"""Qoder runtime verification cases. Authored only; NOT EXECUTED in this change."""
import hashlib
import os
import uuid
import pytest
from lumaretouch_engine import managed_import_io as M


def budget(cancel=lambda:False):
    return M.Budget(cancel,lambda _:None)


def test_copy_full_hash_and_original_unchanged(tmp_path):
    original=tmp_path/'source.jpg'; original.write_bytes(b'opaque fixture, not a decoded JPEG')
    root=tmp_path/'managed';root.mkdir(); b=budget()
    item=M.select([str(original)],{'.jpg'},b)[0]
    fd=M.open_directory(str(root))
    try: result=M.prepare(item,fd,str(root),str(uuid.uuid4()),b)
    finally: os.close(fd)
    assert original.read_bytes()==open(result['path'],'rb').read()
    assert result['sha256']==hashlib.sha256(original.read_bytes()).hexdigest()
    assert result['origin']['relative']=='source.jpg'
    assert os.stat(result['path']).st_mode&0o222==0
    assert not list(root.glob('*.partial'))


def test_cancel_never_publishes(tmp_path):
    original=tmp_path/'a.jpg';original.write_bytes(b'a');root=tmp_path/'managed';root.mkdir()
    item=M.select([str(original)],{'.jpg'},budget())[0];fd=M.open_directory(str(root))
    try:
        with pytest.raises(InterruptedError): M.prepare(item,fd,str(root),str(uuid.uuid4()),budget(lambda:True))
    finally: os.close(fd)
    assert list(root.iterdir())==[] and original.read_bytes()==b'a'


def test_existing_target_never_overwritten(tmp_path):
    original=tmp_path/'a.jpg';original.write_bytes(b'a');root=tmp_path/'managed';root.mkdir()
    operation=str(uuid.uuid4());target=root/(str(uuid.uuid5(uuid.UUID(operation),str(original)))+'.jpg');target.write_bytes(b'keep')
    b=budget();item=M.select([str(original)],{'.jpg'},b)[0];fd=M.open_directory(str(root))
    try:
        with pytest.raises(FileExistsError):M.prepare(item,fd,str(root),operation,b)
    finally:os.close(fd)
    assert target.read_bytes()==b'keep' and original.read_bytes()==b'a'


def test_symlink_and_ancestor_rejected(tmp_path):
    original=tmp_path/'a.jpg';original.write_bytes(b'a');link=tmp_path/'link.jpg';link.symlink_to(original)
    with pytest.raises((OSError,ValueError)):M.select([str(link)],{'.jpg'},budget())
    folder=tmp_path/'folder';folder.mkdir();(folder/'a.jpg').write_bytes(b'a');alias=tmp_path/'alias';alias.symlink_to(folder,target_is_directory=True)
    with pytest.raises((OSError,ValueError)):M.select([str(alias/'a.jpg')],{'.jpg'},budget())


def test_distinct_business_copies_not_hash_deduplicated(tmp_path):
    for name in ('a.jpg','b.jpg'):(tmp_path/name).write_bytes(b'same')
    items=M.select([str(tmp_path/'a.jpg'),str(tmp_path/'b.jpg')],{'.jpg'},budget())
    assert len(items)==2


def test_source_change_after_selection_rejected(tmp_path):
    path=tmp_path/'a.jpg';path.write_bytes(b'a');item=M.select([str(path)],{'.jpg'},budget())[0];path.write_bytes(b'changed')
    with pytest.raises(ValueError):M.prepare(item,None,None,str(uuid.uuid4()),budget())
