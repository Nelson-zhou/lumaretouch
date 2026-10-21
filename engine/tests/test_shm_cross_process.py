"""Readers and writers must share one cross-process synchronization contract."""
import fcntl
import multiprocessing as mp
import os
import time
import pytest
from lumaretouch_engine.shm import FrameShm,shm_name


def _writer(name,entered,done):
    peer=FrameShm(name)
    try:
        entered.set();peer.write_frame(bytes([255])*peer.pixel_size);done.set()
    finally:peer.close()


def test_writer_cannot_overwrite_while_another_process_holds_read_lock():
    name=shm_name('lock-test-'+str(os.getpid()));owner=FrameShm(name,32,24,create=True)
    reader=FrameShm(name);ctx=mp.get_context('spawn');entered=ctx.Event();done=ctx.Event()
    process=ctx.Process(target=_writer,args=(name,entered,done))
    try:
        fcntl.flock(reader._fd,fcntl.LOCK_SH)
        process.start();assert entered.wait(10)
        assert not done.wait(.15), 'writer ignored cross-process read lock'
        fcntl.flock(reader._fd,fcntl.LOCK_UN)
        assert done.wait(10);process.join(10);assert process.exitcode==0
        assert owner.read_pixels(0)==bytes([255])*owner.pixel_size
    finally:
        fcntl.flock(reader._fd,fcntl.LOCK_UN)
        if process.is_alive():process.terminate();process.join(5)
        reader.close();owner.close();owner.unlink()


def test_stale_notification_is_not_relabelled_as_newer_pixels():
    name=shm_name('snapshot-test-'+str(os.getpid()));owner=FrameShm(name,8,8,create=True)
    try:
        old,_,slot=owner.write_frame(bytes([1])*owner.pixel_size)
        owner.write_frame(bytes([2])*owner.pixel_size)
        latest,_,_=owner.write_frame(bytes([3])*owner.pixel_size)
        assert owner.read_snapshot(slot,expected_seq=old) is None
        meta,pixels=owner.read_snapshot()
        assert meta[0]==latest and pixels==bytes([3])*owner.pixel_size
    finally:owner.close();owner.unlink()


def test_native_rust_reader_holds_lock_through_pixel_copy():
    import subprocess
    binary=os.environ.get('LRT_SHM_READER_BIN')
    if not binary:pytest.skip('native shared-frame harness not built')
    name=shm_name('native-lock-'+str(os.getpid()));owner=FrameShm(name,32,24,create=True)
    owner.write_frame(bytes([7])*owner.pixel_size)
    ctx=mp.get_context('spawn');entered=ctx.Event();done=ctx.Event()
    writer=ctx.Process(target=_writer,args=(name,entered,done))
    reader=subprocess.Popen([binary,name,'1000'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        assert reader.stdout.readline().strip()=='LOCKED'
        writer.start();assert entered.wait(10)
        assert not done.wait(.15), 'Python writer ignored Rust shared lock'
        out,err=reader.communicate(timeout=10)
        assert reader.returncode==0,(out,err)
        assert out.strip().endswith('32 24 7'),out
        assert done.wait(10);writer.join(10);assert writer.exitcode==0
        got=subprocess.run([binary,name],capture_output=True,text=True,check=True)
        assert got.stdout.strip().endswith('32 24 255')
    finally:
        if reader.poll() is None:reader.kill();reader.wait()
        if writer.is_alive():writer.terminate();writer.join(5)
        owner.close();owner.unlink()


def test_bad_headers_do_not_leak_descriptors():
    from pathlib import Path
    name=shm_name('bad-header-'+str(os.getpid()));owner=FrameShm(name,8,8,create=True)
    try:
        owner._buf[:4]=b'BAD!'
        before=len(list(Path('/proc/self/fd').iterdir()))
        for _ in range(20):
            with pytest.raises(ValueError):FrameShm(name)
        assert len(list(Path('/proc/self/fd').iterdir()))==before
    finally:owner.close();owner.unlink()


def test_old_reader_refuses_resized_mapping_before_accessing_pixels():
    name=shm_name('resize-'+str(os.getpid()));owner=FrameShm(name,32,32,create=True);peer=FrameShm(name)
    try:
        changed=FrameShm(name,8,8,create=True)
        try:
            with pytest.raises(ValueError,match='size changed'):peer.read_snapshot()
        finally:changed.close()
    finally:peer.close();owner.close();owner.unlink()


def test_native_reader_rejects_legacy_protocol_and_corrupt_layout():
    import subprocess,struct
    binary=os.environ.get('LRT_SHM_READER_BIN')
    if not binary:pytest.skip('native shared-frame harness not built')
    name=shm_name('native-bad-'+str(os.getpid()));owner=FrameShm(name,8,8,create=True)
    try:
        struct.pack_into('<I',owner._buf,4,1)
        bad=subprocess.run([binary,name],capture_output=True,text=True)
        assert bad.returncode!=0 and 'requires locking protocol v2' in bad.stderr
        struct.pack_into('<I',owner._buf,4,2)
        struct.pack_into('<I',owner._buf,20,123)
        bad=subprocess.run([binary,name],capture_output=True,text=True)
        assert bad.returncode!=0 and 'inconsistent' in bad.stderr
    finally:owner.close();owner.unlink()
