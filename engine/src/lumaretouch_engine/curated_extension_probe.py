"""Owned CPU readiness probe for the existing prompted-mask predictor.

Only the installer's explicit install/check command starts this worker. A passing
programmatic fixture proves bounded CPU operation, NOT photo quality, latency,
GPU support, alpha/hair quality or ID-photo regulatory compliance.
"""
import argparse
import json
import os
from pathlib import Path
import resource

PROBE = 'sam2-tiny-cpu-fixture-v1'


def run(root, output):
    from .cpu_memory_budget import available_estimate
    if available_estimate() < 4*1024**3:
        raise ValueError("CPU readiness needs a visible memory budget with at least 4 GiB currently available")
    from .prompted_mask_source import Predictor
    import numpy as np
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    predictor = Predictor('cpu', root=root)
    pixels = np.zeros((32, 32, 3), dtype=np.uint8)
    pixels[8:24, 8:24] = 128
    result = predictor.predict(pixels, {'points':[{'x':.5, 'y':.5, 'label':1}], 'box':None})
    masks = result['masks']
    if masks.shape != (3,32,32) or result['device'] != 'CPU' or not np.isfinite(result['scores']).all():
        raise ValueError('Bounded CPU probe returned an invalid predictor contract')
    from .prompted_model_install import installed_runtime_identity
    with output.open('x', encoding='utf-8') as stream:
        json.dump({'probe':PROBE, 'runtime':installed_runtime_identity(root=root)}, stream, sort_keys=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--parent-pid', required=True, type=int)
    args = parser.parse_args()
    from .inspection_worker import bind_parent
    bind_parent(args.parent_pid)
    # Address space is not an RSS promise. Unsupported builds fail visibly; no
    # fallback to another Python, device, model, or non-AI placeholder.
    for key, limit in ((resource.RLIMIT_AS, 8*1024**3), (resource.RLIMIT_CPU, 180), (resource.RLIMIT_FSIZE, 65536)):
        _, hard = resource.getrlimit(key)
        resource.setrlimit(key, (limit if hard == resource.RLIM_INFINITY else min(limit, hard), hard))
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
        os.environ[name] = '1'
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    run(Path(args.root), Path(args.output))


if __name__ == '__main__':
    main()
