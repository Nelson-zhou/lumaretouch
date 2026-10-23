# SPDX-License-Identifier: GPL-3.0-or-later
"""Owned process-group jobs; cache reference evidence, never target fitted results."""
from copy import deepcopy
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import numpy as np
from .semantic_colour_job import SemanticColourJob


class BatchFitJob(SemanticColourJob):
    def __init__(self,frame,*,reference=None,intent=None,reference_analysis=None):
        from .semantic_colour_analysis import view
        from .semantic_colour_canvas import validate
        from .cpu_memory_budget import available_estimate
        validate(frame)
        if available_estimate()<256*1024*1024:raise ValueError('批量追色分析内存不足')
        if (reference is None)==(intent is None):raise ValueError('工作必须是样片分析或目标拟合之一')
        self.kind='reference' if reference is not None else 'target'
        self.request={'kind':self.kind,'binding':deepcopy(frame.binding)}
        if reference is not None:self.request['reference']=deepcopy(reference)
        else:
            from .semantic_colour_portable import check
            from .semantic_colour_batch_fit import check_reference
            self.request.update(intent=check(intent),reference_analysis=check_reference(reference_analysis))
        self.directory=tempfile.TemporaryDirectory(prefix='lumaretouch-semantic-batch-');self.root=Path(self.directory.name)
        self.process=None;self.state='running';self.result=None;self.error=None;self.started=time.monotonic()
        try:
            image,rgb=view(frame)
            for name,a in (('image',image),('rgb',rgb)):np.save(self.root/(name+'.npy'),a,allow_pickle=False)
            raw=json.dumps(self.request,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
            if len(raw)>2*1024*1024:raise ValueError('批量追色请求超出有界元数据预算')
            (self.root/'request.json').write_bytes(raw)
            self.process=subprocess.Popen([sys.executable,'-m','lumaretouch_engine.semantic_colour_batch_worker','--directory',str(self.root),'--parent-pid',str(os.getpid())],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True,start_new_session=True,
                env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        except BaseException:self.directory.cleanup();raise

    def poll(self):
        if self.state!='running':return self.state
        if self.process.poll() is None:
            if time.monotonic()-self.started>240:
                self.cancel();self.state='failed';self.error='批量追色单图超过 240 秒预算，未应用部分结果'
            return self.state
        try:
            if self.process.returncode:
                path=self.root/'error.json';message=json.loads(path.read_bytes()[:8192]).get('error') if path.is_file() else None
                raise ValueError(message or '批量追色工作退出：'+str(self.process.returncode))
            path=self.root/'result.json';info=path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size>24*1024*1024:raise ValueError('批量追色结果资源异常')
            value=json.loads(path.read_bytes())
            if self.kind=='reference':
                from .semantic_colour_batch_fit import check_reference
                value=check_reference(value)
                if value['reference']!=self.request['reference'] or value['binding']!=self.request['binding']:raise ValueError('工作返回了另一张样片')
            else:
                from .semantic_colour_review import verify
                verify(value,target_binding=self.request['binding'],reference=self.request['intent']['reference'])
                if value.get('portable_intent')!=self.request['intent'] or value.get('reference_analysis_proof')!=self.request['reference_analysis']['proof']:
                    raise ValueError('工作返回的意图/样片分析与冻结请求不同')
            self.result=value;self.state='ready'
        except Exception as error:self.error=str(error)[:2000];self.state='failed'
        self.directory.cleanup();return self.state

    def wait(self,*,cancelled=lambda:False):
        try:
            while self.poll()=='running':
                if cancelled():raise InterruptedError('批量追色已取消，未发布部分结果')
                time.sleep(.05)
            if cancelled():raise InterruptedError('批量追色已取消，未发布部分结果')
            if self.state!='ready':raise ValueError(self.error or '批量追色工作没有完整结果')
            return self.result
        finally:
            if self.state=='running':self.cancel()
