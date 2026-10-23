# SPDX-License-Identifier: GPL-3.0-or-later
"""Owned bounded read-only SAM proposal process. No body state mutation.

Atomic bounded result files avoid multiprocessing Queue partial-frame deadlocks.
Only this owner's private process group and temporary directory are cancelled.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
from . import body_pose_evidence as E, arm_shape_state as S
MAX_RESULT=8*1024*1024


def _read_file(path,limit):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size>limit:raise ValueError('Arm worker file is not a bounded regular file')
    with path.open('rb') as stream:data=stream.read(limit+1)
    if len(data)>limit:raise ValueError('Arm worker file exceeded its byte budget')
    return json.loads(data)


def _write_result(root,result):
    data=json.dumps(result,separators=(',',':'),allow_nan=False).encode()
    if len(data)>MAX_RESULT:raise ValueError('Actual SAM result exceeds transport budget')
    with (root/'result.partial').open('xb') as output:output.write(data)
    os.replace(root/'result.partial',root/'result.json')


def _run(directory,parent_pid):
    # Same admitted parent-death and CPU/file limits as existing image workers.
    import resource
    import threading
    from .inspection_worker import bind_parent
    bind_parent(parent_pid)
    for kind,limit in ((resource.RLIMIT_CPU,180),(resource.RLIMIT_FSIZE,MAX_RESULT)):
        _,hard=resource.getrlimit(kind);limit=limit if hard==resource.RLIM_INFINITY else min(hard,limit)
        resource.setrlimit(kind,(limit,limit))
    os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
    timer=threading.Timer(180,lambda:os.kill(os.getpid(),signal.SIGKILL));timer.daemon=True;timer.start()
    root=Path(directory)
    try:
        request=_read_file(root/'request.json',256*1024)
        if type(request) is not dict or set(request)!={'path','record','segment','scope','ownership','device'}:raise ValueError('Invalid arm worker request')
        from .arm_shape_selection import propose
        result={'success':True,'proposal':propose(request['path'],request['record'],request['segment'],request['scope'],request['ownership'],device=request['device'])}
        _write_result(root,result)
    except Exception as error:
        (root/'result.partial').unlink(missing_ok=True)
        _write_result(root,{'success':False,'error':str(error)[:2000],'proposal':None})
    finally:timer.cancel()


class ArmProposalJobs:
    def __init__(self,*,max_jobs=4,max_retained_bytes=12*1024*1024):
        if type(max_jobs) is not int or not 1<=max_jobs<=8 or type(max_retained_bytes) is not int or not 1024*1024<=max_retained_bytes<=32*1024*1024:raise ValueError('Invalid arm proposal job budget')
        self.max_jobs=max_jobs;self.max_retained_bytes=max_retained_bytes;self.jobs={};self.cancelled_ids=set();self.closed=False

    def start(self,job_id,path,record,segment,scope,ownership,device,context):
        E.token(job_id)
        if self.closed or job_id in self.cancelled_ids:
            return {'phase':'done','job_id':job_id,'success':False,'error':'Arm proposal was cancelled or its owner closed before start','proposal':None}
        record=E.check(record);scope=S.region(scope);S.axis(record,segment)
        from .arm_shape_selection import check_ownership
        check_ownership(ownership,record)
        if device not in ('cpu','cuda'):raise ValueError('Choose the actual CPU or CUDA/ROCm device')
        if type(context) is not dict or set(context)!={'document_id','document_epoch','body_graph_sha256','people_graph_sha256'}:raise ValueError('Arm job needs exact document/body/people context')
        E.token(context['document_id']);E.token(context['document_epoch']);E.digest(context['body_graph_sha256']);E.digest(context['people_graph_sha256'])
        request={'path':str(path),'record':record,'segment':segment,'scope':scope,'ownership':ownership,'device':device}
        identity=E.content_digest({**request,'context':context})
        if job_id in self.jobs:
            if self.jobs[job_id]['identity']!=identity:raise ValueError('Arm proposal ID reused with changed inputs')
            return self.status(job_id)
        if len(self.jobs)>=self.max_jobs:raise ValueError('Close retained arm proposals before starting another job')
        if any(row['process'].poll() is None for row in self.jobs.values()):raise ValueError('Another owned arm model job is running; no parallel inference overcommit')
        from .cpu_memory_budget import available_estimate
        pixels=record['source']['width']*record['source']['height']
        if pixels>64_000_000 or available_estimate()<pixels*32+2*1024**3:raise ValueError('Insufficient admitted RAM for source buffers and the existing 2 GiB prompted-model reserve')
        encoded=json.dumps(request,separators=(',',':'),allow_nan=False).encode()
        if len(encoded)>256*1024:raise ValueError('Arm proposal request exceeds budget')
        directory=tempfile.TemporaryDirectory(prefix='lumaretouch-arm-proposal-');root=Path(directory.name)
        try:
            (root/'request.json').write_bytes(encoded)
            process=subprocess.Popen([sys.executable,'-m','lumaretouch_engine.arm_shape_job','--worker-directory',directory.name,'--parent-pid',str(os.getpid())],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True,start_new_session=True)
        except BaseException:directory.cleanup();raise
        row={'identity':identity,'started':time.monotonic(),'process':process,'directory':directory,'root':root,
             'result':{'phase':'pending','job_id':job_id,'context':deepcopy(context),'success':False}}
        self.jobs[job_id]=row
        return deepcopy(row['result'])

    def _retain(self,row,value):
        if type(value) is not dict or type(value.get('success')) is not bool:raise ValueError('Invalid arm worker result')
        size=len(json.dumps(value,separators=(',',':')).encode())
        retained=sum(len(json.dumps(x['result'],separators=(',',':')).encode()) for x in self.jobs.values())
        if size+retained>self.max_retained_bytes:value={'success':False,'error':'Actual SAM result exceeds retained mask budget','proposal':None}
        row['result']={**row['result'],**value,'phase':'done'}
        row['directory'].cleanup()

    def status(self,job_id):
        E.token(job_id);row=self.jobs.get(job_id)
        if row is None:return {'phase':'unavailable','job_id':job_id,'success':False,'error':'Arm proposal no longer retained'}
        if row['result']['phase']=='pending':
            code=row['process'].poll()
            if code is None:
                if time.monotonic()-row['started']>180:
                    self.cancel(job_id);row['result']['error']='SAM arm proposal exceeded its 180-second deadline'
            else:
                try:
                    if code:raise ValueError('SAM worker exited without a completed proposal: '+str(code))
                    self._retain(row,_read_file(row['root']/'result.json',MAX_RESULT))
                except (OSError,ValueError,TypeError) as error:
                    self._retain(row,{'success':False,'error':str(error)[:2000],'proposal':None})
        return deepcopy(row['result'])

    def cancel(self,job_id):
        E.token(job_id)
        if not self.closed and job_id not in self.cancelled_ids:
            if len(self.cancelled_ids)>=4096:self.closed=True  # Closing refuses every delayed start; never evict a tombstone.
            else:self.cancelled_ids.add(job_id)
        row=self.jobs.get(job_id)
        if row is None:return {'phase':'done','job_id':job_id,'success':False,'error':'Arm proposal cancelled before admission','proposal':None}
        if row['process'].poll() is None:
            try:os.killpg(row['process'].pid,signal.SIGKILL)
            except ProcessLookupError:pass
            try:row['process'].wait(timeout=2)
            except subprocess.TimeoutExpired as error:raise RuntimeError('Owned SAM worker has not exited after cancellation; retain its job until confirmed') from error
        if row['result']['phase']=='pending':
            row['result']={**row['result'],'phase':'done','success':False,'error':'Arm proposal cancelled; no body edit applied','proposal':None}
        row['directory'].cleanup()
        return deepcopy(row['result'])

    def release(self,job_id):
        self.cancel(job_id);self.jobs.pop(job_id,None)

    def close(self):
        self.closed=True
        for job_id in list(self.jobs):self.release(job_id)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--worker-directory',required=True);parser.add_argument('--parent-pid',required=True,type=int)
    args=parser.parse_args();_run(args.worker_directory,args.parent_pid)
