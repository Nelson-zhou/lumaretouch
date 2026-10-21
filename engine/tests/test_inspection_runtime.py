"""Actual protocol → owned spool → limited independent CPU worker → LRIF."""
import json
import os
import struct
from pathlib import Path
import numpy as np
import pytest
from test_protocol import engine
from lumaretouch_engine.inspection_job import validate_config


def config(request_id='1'):
    return dict(epoch='12'*16,ticket=[request_id,'1','1','1','1'],roi=[2,3,8,7],
                source_size=[96,64],canvas_size=[96,64],max_source_pixels=6144,
                max_display_pixels=56,max_address_bytes=4*1024**3,timeout_seconds=60)


@pytest.mark.parametrize('field,value',[
    ('epoch','00'*16),('ticket',['01','1','1','1','1']),
    ('roi',[90,0,8,7]),('max_source_pixels',6143),('max_address_bytes',True),
    ('max_display_pixels',55),('timeout_seconds',121)])
def test_reject_unadmitted_render_config(field,value):
    c=config();c[field]=value
    with pytest.raises(ValueError):validate_config(c)


def test_admission_returns_private_lists():
    c=config();out=validate_config(c);c['ticket'][1]='7'
    assert out['ticket'][1]=='1'


def test_real_protocol_worker_renders_then_release_removes_private_result(engine,tmp_path):
    pytest.importorskip('torch')
    from PIL import Image
    data=np.full((64,96,3),100,np.uint8)
    path=tmp_path/'fixture.png';Image.fromarray(data).save(path)
    engine.send(cmd='load_image',path=str(path),device='cpu',strength=0)
    engine.wait_for('image_ready',timeout=60)
    engine.send(cmd='inspection_snapshot',action='start',request_id='1',max_asset_bytes=1024*1024,
                render=config(),_host_request_id='accepted')
    phases=[];accepted=False
    while True:
        event=engine.next_event(timeout=75)
        if event['event']=='command_done' and event['request_id']=='accepted':accepted=True
        if event['event']!='inspection_snapshot':
            assert event['event']!='error',event
            continue
        phases.append(event['state'])
        assert event['state'] not in ('failed','cancelled','cancelling'),event
        if event['state']=='ready':
            assert accepted and event['preparation_only'] is False
            result=Path(event['result_path']);break
    assert 'spooling' in phases and 'rendering' in phases
    packet=result.read_bytes()
    assert packet[:4]==b'LRIF' and len(packet)==128+8*7*4
    assert packet[8:24]==bytes.fromhex('12'*16)
    assert struct.unpack_from('<5Q',packet,24)==(1,1,1,1,1)
    pixels=np.frombuffer(packet[128:],np.uint8).reshape(7,8,4)
    np.testing.assert_array_equal(pixels[:,:,:3],data[3:10,2:10])
    assert (pixels[:,:,3]==255).all()
    directory=result.parent
    engine.send(cmd='inspection_snapshot',action='release',request_id='1')
    while True:
        event=engine.next_event(timeout=10)
        if event['event']=='inspection_snapshot' and event['state']=='released':break
    assert not directory.exists()


def test_cancel_keeps_worker_lease_until_actual_exit(tmp_path,monkeypatch):
    from lumaretouch_engine import inspection_job as jobs
    from lumaretouch_engine.render_snapshot import own_render_inputs
    class Child:
        pid=123456
        rc=None
        def poll(self):return self.rc
    child=Child();kills=[]
    monkeypatch.setattr(jobs.subprocess,'Popen',lambda *a,**k:child)
    monkeypatch.setattr(jobs.os,'killpg',lambda pid,sig:kills.append((pid,sig)))
    owned=own_render_inputs({},max_asset_bytes=0)
    job=jobs.InspectionJob(owned,str(tmp_path/'source'),[1,2,3,4,5],config(),0)
    directory=Path(job.directory)
    job.tick(1024*1024)
    assert job.state=='rendering' and job.running
    job.cancel()
    assert job.state=='cancelling' and directory.exists() and kills
    with pytest.raises(RuntimeError,match='live'):
        job.cleanup()
    child.rc=-9
    job.tick(1024)
    assert job.state=='cancelled' and not directory.exists()


def test_worker_failure_removes_partial_private_output(tmp_path,monkeypatch):
    from lumaretouch_engine import inspection_job as jobs
    from lumaretouch_engine.render_snapshot import own_render_inputs
    class Child:
        pid=123456
        def poll(self):return 1
    monkeypatch.setattr(jobs.subprocess,'Popen',lambda *a,**k:Child())
    job=jobs.InspectionJob(own_render_inputs({},max_asset_bytes=0),str(tmp_path/'source'),
                           [1,2,3,4,5],config(),0)
    directory=Path(job.directory)
    job.tick(1024*1024)
    assert job.state=='failed' and 'code 1' in job.error and not directory.exists()


def test_missing_source_emits_failed_identity_and_ack(tmp_path,monkeypatch):
    from test_snapshot_scheduler import harness
    from types import SimpleNamespace
    from lumaretouch_engine import server
    e=harness();events=[]
    e._image_loaded=True;e._vram=SimpleNamespace(h=64,w=96)
    e._doc_path=str(tmp_path/'deleted.png');e._export=e.bench=None
    monkeypatch.setattr(server,'emit',events.append)
    e._process_line(json.dumps(dict(cmd='inspection_snapshot',action='start',request_id='1',
                    max_asset_bytes=100,render=config(),_host_request_id='ack')),
                    {'inspection_snapshot':e.cmd_inspection_snapshot})
    assert any(v['event']=='inspection_snapshot' and v['state']=='failed' and v['request_id']=='1' for v in events)
    assert events[-1]=={'event':'command_done','request_id':'ack'}


def test_heavy_work_waits_for_cancelled_worker_without_losing_bench_terminal(monkeypatch):
    from test_snapshot_scheduler import harness
    from lumaretouch_engine import server
    e=harness();events=[];calls=[]
    e.device='cpu';e._cuda=False
    class Job:
        running=True;state='rendering';error=None;asset_bytes=0
        def cancel(self):self.state='cancelling'
    e._inspection_job=Job()
    monkeypatch.setattr(server,'emit',events.append)
    table={name:lambda msg:calls.append(msg['cmd']) for name in ('bench_start','export','task')}
    for i,command in enumerate(({'cmd':'bench_start'},{'cmd':'export'},
                                {'cmd':'task','action':'retry'},{'cmd':'task','action':'list'})):
        e._process_line(json.dumps(dict(command,_host_request_id=str(i))),table)
    assert calls==['task']
    assert any(v['event']=='bench_done' and v['failed'] for v in events)
    assert len([v for v in events if v['event']=='command_done'])==4


def test_cancel_exit_race_explicitly_cleans_before_dropping_job():
    from test_snapshot_scheduler import harness
    e=harness();cleaned=[]
    class Job:
        running=True
        def cancel(self):self.running=False
        def cleanup(self):cleaned.append(True)
    e._inspection_job=Job()
    e._cancel_snapshot(notify=False)
    assert cleaned==[True] and e._inspection_job is None


def test_parent_binding_checks_reparenting(monkeypatch):
    import ctypes
    from lumaretouch_engine import inspection_worker as worker
    class Call:
        def __call__(self,*args):
            assert args==(1,9,0,0,0)
            return 0
    class Lib:
        prctl=Call()
    monkeypatch.setattr(ctypes,'CDLL',lambda *a,**k:Lib())
    monkeypatch.setattr(worker.os,'getppid',lambda:123)
    worker.bind_parent(123)
    with pytest.raises(RuntimeError,match='exited'):
        worker.bind_parent(456)
