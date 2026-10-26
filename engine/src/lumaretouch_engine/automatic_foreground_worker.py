# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline automatic portrait-category proposal; never changes source RGB."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import resource
import sys


def run(root):
    import numpy as np
    import cv2
    from .automatic_foreground import CONTRACT, check_source, check_binding
    from .prompted_mask_source import decode_source
    from .semantic_colour_analysis import infer
    path = root / 'request.json'
    if path.stat().st_size > 65536:
        raise ValueError('自动前景请求超过预算')
    request = json.loads(path.read_bytes())
    if type(request) is not dict or set(request) != {'path','source'}:
        raise ValueError('自动前景请求字段无效')
    source = check_source(request['source'])
    if type(request['path']) is not str or not request['path'] or len(request['path']) > 32768:
        raise ValueError('自动前景需要原照片路径')
    rgb = decode_source(request['path'], source, device='cpu')
    h,w = rgb.shape[:2]
    scale = min(1., 512/max(h,w))
    width,height = max(1, round(w*scale)), max(1, round(h*scale))
    reduced = cv2.resize(rgb, (width,height), interpolation=cv2.INTER_AREA)
    if reduced.dtype == np.uint16:
        image = ((reduced.astype(np.uint32)+128)//257).astype(np.uint8)
    elif reduced.dtype == np.uint8:
        image = np.array(reduced, copy=True, order='C')
    else:
        raise ValueError('自动前景需要真实 RGB8 / RGB16 原图')
    del rgb, reduced
    probabilities, receipt = infer(image)
    # Not inverse-background: other objects/accessories remain unknown. This is
    # a semantic proposal covering every matching person, never a single person.
    alpha = np.rint(np.clip(probabilities[:,:,1:5].sum(axis=-1),0,1)*255).astype(np.uint8)
    raw = alpha.tobytes(order='C')
    binding = check_binding({'origin':'automatic','contract':CONTRACT,
        'model_sha256':receipt['model_sha256'],'runtime':receipt['runtime'],
        'input_sha256':receipt['input_sha256'],'alpha_sha256':hashlib.sha256(raw).hexdigest(),
        'width':width,'height':height,'source':source})
    result = json.dumps({'binding':binding,'alpha_u8':base64.b64encode(raw).decode('ascii')},
                        allow_nan=False, separators=(',',':')).encode()
    if len(result) > 2*1024*1024:
        raise ValueError('自动前景结果超过预算')
    with (root / 'result.json').open('xb') as stream:
        stream.write(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True)
    parser.add_argument('--parent-pid', type=int, required=True)
    args = parser.parse_args()
    root = Path(args.directory)
    try:
        from .inspection_worker import bind_parent
        bind_parent(args.parent_pid)
        for key, bound in ((resource.RLIMIT_CPU,180),(resource.RLIMIT_FSIZE,2*1024*1024)):
            _,hard = resource.getrlimit(key)
            bound = bound if hard == resource.RLIM_INFINITY else min(bound,hard)
            resource.setrlimit(key,(bound,bound))
        for key,value in {'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2',
                          'DO_NOT_TRACK':'1','HF_HUB_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1'}.items():
            os.environ[key] = value
        sys.dont_write_bytecode = True
        from .privacy import install_offline_policy
        install_offline_policy()
        run(root)
    except Exception as error:
        (root / 'error.json').write_text(json.dumps({'error':str(error)[:2000]}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
