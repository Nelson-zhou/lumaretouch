# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded offline CPU child for setup probe and genuine whole-frame inference.
AUTHORED / UNRUN. No photo collection, GPU, download, fallback or model cache.
"""
from dataclasses import asdict
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource


def run(root, output, request_directory=None):
    from .cpu_memory_budget import available_estimate
    if available_estimate()<4*1024**3:
        raise ValueError('Depth CPU worker needs at least 4 GiB visible available memory')
    from .lens_depth_setup import activate_runtime, runtime_identity, PROBE, _read
    before=activate_runtime(root)
    import torch
    torch.set_num_threads(1); torch.set_num_interop_threads(1)
    from .lens_depth_adapter import (DepthSourceV1,DepthOwnerV1,DepthRequestV1,
        _estimate_depth_in_process)
    if request_directory is None:
        width,height=64,48
        proxy=bytes(component for y in range(height) for x in range(width)
                    for component in ((x*4)%256,(y*5)%256,((x+y)*3)%256))
        source=DepthSourceV1(hashlib.sha256(b'generated-depth-probe-source-v1').hexdigest(),width,height)
        request=DepthRequestV1(DepthOwnerV1('depth_probe','depth_probe_epoch','0',source),
            width,height,proxy,hashlib.sha256(b'generated-opaque-srgb-fixture-v1').hexdigest())
    else:
        meta=json.loads(_read(request_directory/'request.json',65536))
        owner=meta['owner']; source=DepthSourceV1(**owner.pop('source'))
        proxy=_read(request_directory/'proxy.rgb8',1024*1024*3)
        request=DepthRequestV1(DepthOwnerV1(source=source,**owner),meta['proxy_width'],meta['proxy_height'],
            proxy,meta['analysis_transform_sha256'])
        if request.identity!=meta['request_identity'] or request.proxy_sha256!=meta['proxy_sha256']:
            raise ValueError('Depth worker analysis request identity mismatch')
    result=_estimate_depth_in_process(request,model_root=root/'model')
    if runtime_identity(root)!=before:
        raise ValueError('Depth optional runtime changed during inference')
    if request_directory is None:
        payload={'probe':PROBE,'runtime':before}
    else:
        with (request_directory/'depth.f32').open('xb') as stream:stream.write(result.depth_le_f32)
        payload={key:value for key,value in asdict(result).items() if key!='depth_le_f32'}
    with output.open('x',encoding='utf-8') as stream:json.dump(payload,stream,sort_keys=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--parent-pid',required=True,type=int)
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--probe',action='store_true');choice.add_argument('--request')
    args=parser.parse_args()
    from .inspection_worker import bind_parent
    bind_parent(args.parent_pid)
    from .privacy import install_offline_policy
    install_offline_policy()  # Also required for installer probes not spawned by engine.
    for key,limit in ((resource.RLIMIT_AS,8*1024**3),(resource.RLIMIT_CPU,100),(resource.RLIMIT_FSIZE,400_000_000)):
        _,hard=resource.getrlimit(key)
        resource.setrlimit(key,(limit if hard==resource.RLIM_INFINITY else min(limit,hard),hard))
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[name]='1'
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    run(Path(args.root),Path(args.output),Path(args.request) if args.request else None)

if __name__=='__main__':main()
