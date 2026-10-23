# SPDX-License-Identifier: GPL-3.0-or-later
"""Disposable offline batch evidence worker; same model and Rust colour evaluator."""
import argparse
import json
import os
from pathlib import Path
import resource
import sys
MAX_BYTES=24*1024*1024


def run(root):
    import numpy as np
    from . import semantic_colour_batch_fit as F
    path=root/'request.json'
    if path.stat().st_size>2*1024*1024:raise ValueError('批量追色请求超过元数据预算')
    request=json.loads(path.read_bytes());kind=request.pop('kind',None)
    expected={'reference','binding'} if kind=='reference' else {'intent','reference_analysis','binding'} if kind=='target' else set()
    if not expected or set(request)!=expected:raise ValueError('批量追色工作请求字段无效')
    arrays=[]
    for name in ('image','rgb'):
        path=root/(name+'.npy')
        if path.stat().st_size>4*1024*1024:raise ValueError('批量追色冻结视图超限')
        with path.open('rb') as stream:
            version=np.lib.format.read_magic(stream)
            if version==(1,0):shape,order,dtype=np.lib.format.read_array_header_1_0(stream)
            elif version==(2,0):shape,order,dtype=np.lib.format.read_array_header_2_0(stream)
            else:raise ValueError('批量追色视图 NPY 版本不受支持')
            if (len(shape)!=3 or shape[-1]!=3 or any(type(n) is not int or n<1 for n in shape)
                    or shape[0]*shape[1]>262144 or order or dtype!=np.dtype(np.uint8 if name=='image' else np.float32)
                    or stream.tell()+shape[0]*shape[1]*3*dtype.itemsize!=path.stat().st_size):
                raise ValueError('批量追色冻结视图头或内存预算无效')
        a=np.load(path,allow_pickle=False)
        if not np.isfinite(a).all():raise ValueError('批量追色冻结视图包含非有限值')
        arrays.append(a)
    if arrays[0].shape!=arrays[1].shape:raise ValueError('批量追色分析/采样网格不同')
    result=getattr(F,kind)(request,*arrays)
    raw=json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
    if len(raw)>MAX_BYTES:raise ValueError('批量追色结果超过私有工作预算')
    with (root/'result.json').open('xb') as out:out.write(raw)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True);parser.add_argument('--parent-pid',type=int,required=True);args=parser.parse_args()
    root=Path(args.directory)
    try:
        from .inspection_worker import bind_parent
        bind_parent(args.parent_pid)
        for key,n in ((resource.RLIMIT_CPU,240),(resource.RLIMIT_FSIZE,MAX_BYTES)):
            _,hard=resource.getrlimit(key);n=n if hard==resource.RLIM_INFINITY else min(n,hard);resource.setrlimit(key,(n,n))
        for key,value in {'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2','DO_NOT_TRACK':'1','HF_HUB_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1'}.items():os.environ[key]=value
        sys.dont_write_bytecode=True
        from .privacy import install_offline_policy
        install_offline_policy();run(root)
    except Exception as error:
        (root/'error.json').write_text(json.dumps({'error':str(error)[:2000]},ensure_ascii=False));raise SystemExit(1)
if __name__=='__main__':main()
