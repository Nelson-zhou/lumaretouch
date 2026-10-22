# SPDX-License-Identifier: GPL-3.0-or-later
"""Disposable offline inference+fit. Only bounded immutable views cross process."""
import argparse
import json
import os
from pathlib import Path
import resource
import sys
MAX_RESULT=24*1024*1024


def run(root):
    import numpy as np
    from .semantic_colour_review import prepare
    path=root/'request.json'
    if path.stat().st_size>12*1024*1024:raise ValueError('AI 追色请求超过冻结预算')
    request=json.loads(path.read_bytes())
    expected={'reference','reference_binding','target_binding','mode','strengths','local_only','reference_selection','target_selection'}
    if set(request)!=expected:raise ValueError('AI 追色请求字段不完整')
    from . import semantic_colour_state as S
    S.binding(request['reference_binding']);S.binding(request['target_binding'])
    if request['mode'] not in ('extreme','harmonious') or type(request['local_only']) is not bool:raise ValueError('AI 追色模式无效')
    if type(request['strengths']) is not list or len(request['strengths'])!=3:raise ValueError('AI 追色程度无效')
    for x in request['strengths']:S.number(x,0,200)
    arrays=[]
    for name in ('reference_image','reference_rgb','target_image','target_rgb'):
        path=root/(name+'.npy')
        if path.stat().st_size>4*1024*1024:raise ValueError('AI 追色分析视图超限')
        a=np.load(path,allow_pickle=False)
        if type(a) is not np.ndarray or a.ndim!=3 or a.shape[-1]!=3 or a.shape[0]*a.shape[1]>262144 or a.dtype!=(np.uint8 if name.endswith('image') else np.float32) or not np.isfinite(a).all():raise ValueError('AI 追色分析/全精度样本文件无效')
        arrays.append(a)
    result=prepare(request,*arrays)
    raw=json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
    if len(raw)>MAX_RESULT:raise ValueError('AI 追色结果超过有界传输预算')
    with (root/'result.json').open('xb') as out:out.write(raw)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True);parser.add_argument('--parent-pid',type=int,required=True);args=parser.parse_args()
    root=Path(args.directory)
    try:
        from .inspection_worker import bind_parent
        bind_parent(args.parent_pid)
        for key,n in ((resource.RLIMIT_CPU,240),(resource.RLIMIT_FSIZE,MAX_RESULT)):
            _,hard=resource.getrlimit(key);n=n if hard==resource.RLIM_INFINITY else min(n,hard);resource.setrlimit(key,(n,n))
        for key,value in {'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2','DO_NOT_TRACK':'1','HF_HUB_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1'}.items():os.environ[key]=value
        sys.dont_write_bytecode=True
        from .privacy import install_offline_policy
        install_offline_policy();run(root)
    except Exception as error:
        (root/'error.json').write_text(json.dumps({'error':str(error)[:2000]},ensure_ascii=False));raise SystemExit(1)
if __name__=='__main__':main()
