#!/usr/bin/env python3
"""Matched warmed-GPU, predecoded synthetic-frame benchmark; NOT RAW/UI timing.

Run unchanged against two exact checkouts in separate sequential processes.
Never flush the allocator cache; retain all samples and verify output before rc0.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import traceback


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--expected-head',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--reference',type=Path)
    args=parser.parse_args()
    if args.output.exists():
        raise RuntimeError('Refusing to overwrite prior benchmark evidence')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    source=args.source.resolve()
    head=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if head!=args.expected_head:raise RuntimeError('Unexpected source commit')
    data={'pid':os.getpid(),'head':head,'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
          'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'scope':'warmed GPU; predecoded synthetic RGB8; excludes RAW decode, IPC, WebView and display',
          'repetitions':5,'hot_samples_per_repetition':5,'width':3320,'height':2488,'samples':[]}
    print(json.dumps({'pid':data['pid'],'head':head,'started_utc':data['started_utc']}),flush=True)
    try:
        sys.path.insert(0,str(source/'engine'/'src'))
        from lumaretouch_engine.privacy import install_offline_policy
        policy=install_offline_policy()
        if not policy.get('enforced'):raise RuntimeError('Offline policy not enforced')
        data['offline_policy']=policy
        import numpy as np
        import torch
        from lumaretouch_engine import vram
        if not Path(vram.__file__).resolve().is_relative_to(source):
            raise RuntimeError('Imported pipeline is not from requested checkout')
        if not torch.cuda.is_available():raise RuntimeError('CUDA/ROCm GPU required; no CPU fallback')
        data.update(source_file=str(Path(vram.__file__).resolve()),torch=torch.__version__,
                    rocm=getattr(torch.version,'hip',None),cuda=getattr(torch.version,'cuda',None),
                    device=torch.cuda.get_device_name(0))
        rgb=np.random.default_rng(1729).integers(0,256,(2488,3320,3),dtype=np.uint8)
        data['fixture_sha256']=hashlib.sha256(rgb.tobytes()).hexdigest()
        data['warmup_ms']=vram.warm_device('cuda')
        torch.cuda.synchronize()

        def measure(fn):
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
            before=int(torch.cuda.memory_allocated())
            start=time.perf_counter_ns()
            value=fn()
            torch.cuda.synchronize()
            elapsed=(time.perf_counter_ns()-start)/1e6
            return value,{'ms':elapsed,'allocated_before_bytes':before,
                          'peak_allocated_bytes':int(torch.cuda.max_memory_allocated()),
                          'allocated_after_bytes':int(torch.cuda.memory_allocated())}

        def open_neutral():
            pipe=vram.PreviewPipeline('cuda',3320,2488)
            pipe.load_rgb_u8(rgb)
            pipe.render(0.)
            return pipe,pipe.read_back()

        edited_hashes=[]
        for repetition in range(5):
            (pipe,frame),neutral=measure(open_neutral)
            if frame.shape!=(2488,3320,4) or not np.array_equal(frame[...,:3],rgb) or not np.all(frame[...,3]==255):
                raise AssertionError('Neutral output differs from input')
            neutral.update(filter_bytes=pipe.filter_resident_bytes(),bands_bytes=pipe.bands_resident_bytes())
            del frame
            def edited():
                pipe.render(.5)
                return pipe.read_back()
            frame,first=measure(edited)
            digest=hashlib.sha256(frame.tobytes()).hexdigest()
            edited_hashes.append(digest)
            first.update(filter_bytes=pipe.filter_resident_bytes(),bands_bytes=pipe.bands_resident_bytes())
            del frame
            hot=[]
            for _ in range(5):
                frame,metric=measure(edited)
                if hashlib.sha256(frame.tobytes()).hexdigest()!=digest:
                    raise AssertionError('Hot output changed without a recipe change')
                hot.append(metric)
                del frame
            data['samples'].append({'repetition':repetition,'neutral':neutral,'first_nonzero':first,
                                    'hot':hot,'edited_sha256':digest})
            del pipe  # No empty_cache, global settings or allocator manipulation.
            torch.cuda.synchronize()
            print(json.dumps({'repetition':repetition,'neutral_ms':neutral['ms'],
                              'first_nonzero_ms':first['ms'],'hot_ms':[m['ms'] for m in hot]}),flush=True)
        if len(set(edited_hashes))!=1:raise AssertionError('Fresh repetitions changed edited pixels')
        if args.reference:
            reference=json.loads(args.reference.read_text())
            for key in ('script_sha256','fixture_sha256','width','height','device','torch','rocm','cuda'):
                if reference.get(key)!=data.get(key):raise AssertionError(f'Mismatched experiment metadata: {key}')
            if reference.get('status')!='ok':raise AssertionError('Reference experiment did not pass')
            if any(s['edited_sha256']!=edited_hashes[0] for s in reference['samples']):
                raise AssertionError('Baseline and current edited pixels differ')
            data['reference_head']=reference['head']
        for stage in ('neutral','first_nonzero','hot'):
            values=([m['ms'] for s in data['samples'] for m in s['hot']] if stage=='hot'
                    else [s[stage]['ms'] for s in data['samples']])
            data.setdefault('summary',{})[stage]={'n':len(values),'min_ms':min(values),
                'median_ms':statistics.median(values),'max_ms':max(values)}
        data['status']='ok'
    except BaseException as error:
        data['status']='failed';data['error']=f'{type(error).__name__}: {error}'
        traceback.print_exc()
    finally:
        data['finished_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    if data['status']!='ok':return 1
    print(json.dumps({'status':'ok','output':str(args.output),'summary':data['summary']}),flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
