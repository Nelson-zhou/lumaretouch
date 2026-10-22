# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded cancellable offline job; live editor never lends mutable pixels."""
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
import numpy as np
from . import semantic_colour_state as S

class SemanticColourJob:
    def __init__(self,reference,target,*,reference_asset,mode='harmonious',strengths=(100,100,100),reference_selection=None,target_selection=None):
        from .semantic_colour_canvas import validate
        from .semantic_colour_analysis import view
        from .cpu_memory_budget import available_estimate
        validate(reference);validate(target)
        if available_estimate()<256*1024*1024:raise ValueError('AI 追色有界分析和优化内存不足')
        if (reference_selection is None)!=(target_selection is None):raise ValueError('局部追色必须给两张图各自的选区')
        self.directory=tempfile.TemporaryDirectory(prefix='lumaretouch-semantic-colour-');self.root=Path(self.directory.name)
        self.process=None;self.state='running';self.result=None;self.error=None;self.started=time.monotonic()
        self.request={'reference':deepcopy(reference_asset),'reference_binding':reference.binding,'target_binding':target.binding,
            'mode':mode,'strengths':list(strengths),'local_only':target_selection is not None,
            'reference_selection':deepcopy(reference_selection),'target_selection':deepcopy(target_selection)}
        try:
            for prefix,frame in (('reference',reference),('target',target)):
                image,rgb=view(frame)
                for suffix,a in (('image',image),('rgb',rgb)):np.save(self.root/(prefix+'_'+suffix+'.npy'),a,allow_pickle=False)
            raw=json.dumps(self.request,ensure_ascii=False,allow_nan=False)
            if len(raw.encode())>12*1024*1024:raise ValueError('AI 追色请求过大')
            (self.root/'request.json').write_text(raw)
            self.process=subprocess.Popen([sys.executable,'-m','lumaretouch_engine.semantic_colour_worker','--directory',str(self.root),'--parent-pid',str(os.getpid())],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True,start_new_session=True,
                env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        except BaseException:self.directory.cleanup();raise

    def poll(self):
        if self.state!='running':return self.state
        if self.process.poll() is None:
            if time.monotonic()-self.started>240:
                self.cancel();self.state='failed';self.error='AI 追色超过 240 秒预算；没有应用部分结果'
            return self.state
        try:
            if self.process.returncode:
                path=self.root/'error.json';detail=json.loads(path.read_bytes()[:8192]).get('error') if path.is_file() else None
                raise ValueError(detail or 'AI 追色工作进程退出：'+str(self.process.returncode))
            path=self.root/'result.json';info=path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size>24*1024*1024:raise ValueError('AI 追色结果文件异常')
            value=json.loads(path.read_bytes())
            from .semantic_colour_review import verify
            verify(value,target_binding=self.request['target_binding'],reference=self.request['reference'])
            self.result=value;self.state='ready'
        except Exception as error:self.error=str(error)[:2000];self.state='failed'
        self.directory.cleanup();return self.state

    def cancel(self):
        if self.process is not None and self.process.poll() is None:
            try:os.killpg(self.process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            self.process.wait()
        self.result=None;self.state='cancelled';self.directory.cleanup()
