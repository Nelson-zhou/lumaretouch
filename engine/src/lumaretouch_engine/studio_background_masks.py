"""Rust-only float coverage bridge; no proxy mask is persisted or enlarged."""
import os
import select
import struct
import subprocess
import time
from pathlib import Path
import numpy as np
from . import studio_background_state as S


def transform(value, target, shape, *, cancelled=lambda: False):
    value = S.check(value); S.validate_budget(value, shape)
    rows = [s for s in value['strokes'] if s['target'] == target]
    if target not in S.TARGETS: raise ValueError('未知背景蒙版目标')
    if not rows: return None
    h,w = shape
    packet = bytearray(b'SBM1')+struct.pack('<III',w,h,len(rows))
    for row in rows:
        packet += struct.pack('<B7dI',int(row['operation']=='subtract'),row['feather'],row['flow'],row['opacity'],*row['axes'][0],*row['axes'][1],len(row['points']))
        for point in row['points']: packet += struct.pack('<3d',*point)
    if len(packet)>1024*1024: raise ValueError('背景蒙版传输超过 1 MiB')
    path=Path(__file__).resolve().parent/'bin'/'studio-background'
    if not path.is_file(): raise RuntimeError('匹配的 Rust studio-background 蒙版程序未安装')
    proc=subprocess.Popen([str(path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    for stream in (proc.stdin,proc.stdout,proc.stderr): os.set_blocking(stream.fileno(),False)
    deadline=time.monotonic()+120
    def wait(stream,write=False):
        while True:
            if cancelled(): raise InterruptedError('背景蒙版重放已取消')
            left=deadline-time.monotonic()
            if left<=0: raise TimeoutError('背景蒙版重放超时；不会替代为代理蒙版')
            ready=select.select([] if write else [stream],[stream] if write else [],[],min(.1,left))
            if ready[0] or ready[1]: return
    def read(size):
        result=bytearray()
        while len(result)<size:
            wait(proc.stdout)
            try: part=os.read(proc.stdout.fileno(),min(65536,size-len(result)))
            except BlockingIOError: continue
            if not part:
                try: reason=os.read(proc.stderr.fileno(),2048).decode(errors='replace')
                except BlockingIOError: reason=''
                raise ValueError('背景蒙版重放失败或输出截断：'+reason)
            result.extend(part)
        return result
    try:
        data=memoryview(struct.pack('<I',len(packet))+packet)
        while data:
            wait(proc.stdin,True)
            try: n=os.write(proc.stdin.fileno(),data[:65536])
            except BlockingIOError: continue
            if n<1: raise ValueError('背景蒙版输入中断')
            data=data[n:]
        proc.stdin.close();header=read(12)
        if header[:4]!=b'SBF1' or struct.unpack_from('<Q',header,4)[0]!=h*w*8:
            raise ValueError('背景蒙版版本或尺寸不兼容')
        fields=[]
        for _ in range(2):
            out=np.empty((h,w),np.float32);rows=max(1,1048576//(w*4))
            for y in range(0,h,rows):
                count=min(rows,h-y);out[y:y+count]=np.frombuffer(read(count*w*4),'<f4').reshape(count,w)
            if not np.isfinite(out).all() or np.any((out<0)|(out>1)): raise ValueError('背景覆盖度无效')
            fields.append(out)
        while proc.poll() is None:
            if cancelled(): raise InterruptedError('背景蒙版重放已取消')
            if time.monotonic()>=deadline: raise TimeoutError('背景蒙版程序未正常结束')
            time.sleep(.01)
        if proc.returncode or os.read(proc.stdout.fileno(),1): raise ValueError('背景蒙版退出失败或有多余输出')
        return fields
    finally:
        if proc.poll() is None: proc.kill();proc.wait()
        for stream in (proc.stdin,proc.stdout,proc.stderr):
            if not stream.closed: stream.close()


def raster(value,target,shape,base=None,*,cancelled=lambda:False):
    fields=transform(value,target,shape,cancelled=cancelled)
    if base is None: return np.zeros(shape,np.float32) if fields is None else fields[0]
    base=np.asarray(base,dtype=np.float32)
    if base.shape!=tuple(shape) or not np.isfinite(base).all() or np.any((base<0)|(base>1)):
        raise ValueError('背景蒙版基底无效')
    return base.copy() if fields is None else base*fields[1]+fields[0]
