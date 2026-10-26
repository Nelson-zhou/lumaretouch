# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline isolated CPU inference process; AUTHORED/UNRUN, never import-launched."""
import argparse
from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import struct


def run(root, output, request_directory=None):
    from . import setup as S
    from .source import CanonicalSource
    from .geometry import plan_native_candidate
    from ..cpu_memory_budget import available_estimate
    if available_estimate() < 4*1024**3:
        raise ValueError('Upscale CPU worker needs at least 4 GiB visible available memory')
    before = S.runtime_identity(root)
    # Exact checked bytes are deserialized once, only inside bounded offline child.
    checkpoint = S.checkpoint_bytes(root)
    import torch
    import numpy as np
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    from .swin2sr_network import build_model
    network = build_model(torch, checkpoint)
    envelope = 'official-hf-safetensors'
    del checkpoint
    if request_directory is None:
        width, height = 18, 16
        pixels = b''.join(struct.pack('<ffff', x/width, y/height, (x+y)/(width+height), 1.)
                          for y in range(height) for x in range(width))
        source = CanonicalSource(width, height, pixels, hashlib.sha256(pixels).hexdigest())
    else:
        meta = json.loads(S._read(request_directory/'request.json', 65536))
        width, height = meta['width'], meta['height']
        if type(width) is not int or type(height) is not int or width < 16 or height < 16 or width > S.MAX_SIDE or height > S.MAX_SIDE or width*height > S.MAX_PIXELS:
            raise ValueError('Upscale source outside bounded CPU profile')
        source = CanonicalSource(width, height, S._read(request_directory/'source.f32', S.MAX_PIXELS*16), meta['source_sha256'])
    plan = plan_native_candidate(source.width, source.height, model_id=S.MODEL_ID, core_size=S.CORE_SIZE, halo=S.HALO)
    if plan.tile_count != 1:
        raise ValueError('First Swin2SR profile requires one complete model frame; border tiling is not admitted')
    from ._stream import _execute_unadmitted_reference
    result = _execute_unadmitted_reference(torch, np, network, source, plan, device='cpu', check_cancelled=lambda: None)
    if S.runtime_identity(root) != before:
        raise ValueError('Upscale model or runtime changed during inference')
    if request_directory is None:
        payload = {'probe': S.PROBE, 'runtime': before}
    else:
        with (request_directory/'result.f32').open('xb') as stream:
            stream.write(result.rgba_f32le)
        payload = {key:value for key,value in asdict(result).items() if key != 'rgba_f32le'}
        payload.update(status='review_required', runtime=before, checkpoint_envelope=envelope,
                       quality_acceptance='UNRUN', performance_acceptance='UNRUN', halo_quality_accepted=False)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, sort_keys=True, allow_nan=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--parent-pid', required=True, type=int)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--probe', action='store_true')
    choice.add_argument('--request')
    args = parser.parse_args()
    from ..inspection_worker import bind_parent
    bind_parent(args.parent_pid)
    from ..privacy import install_offline_policy
    install_offline_policy()
    for key, limit in ((resource.RLIMIT_AS, 8*1024**3), (resource.RLIMIT_CPU, 600),
                       (resource.RLIMIT_FSIZE, 200_000_000)):
        _, hard = resource.getrlimit(key)
        resource.setrlimit(key, (limit if hard == resource.RLIM_INFINITY else min(limit, hard), hard))
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[name] = '1'
    run(Path(args.root), Path(args.output), Path(args.request) if args.request else None)


if __name__ == '__main__': main()
