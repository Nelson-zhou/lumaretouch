"""Disposable offline worker, separate from the explicit online installer."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import resource
from . import manifest as M


def png(array):
    from PIL import Image
    output = io.BytesIO()
    Image.fromarray(array).save(output, format='PNG')
    return base64.b64encode(output.getvalue()).decode('ascii')


def overlay_png(labels):
    import numpy as np
    rgba = np.full((*labels.shape, 4), 255, dtype=np.uint8)
    rgba[..., 3] = labels
    return png(rgba)


def run(root):
    from .predict import activate, predict
    from . import immutable_input as I
    from .state import source
    raw = I.read_regular_bytes(root / 'request.json', 65536)
    request = json.loads(raw)
    original = {'path', 'source', 'device'}
    derived = {'immutable_input', 'source', 'device'}
    if type(request) is not dict or set(request) not in (original, derived):
        raise ValueError('自动选区请求字段无效')
    binding = source(request['source'])
    if request['device'] not in ('cpu', 'cuda'):
        raise ValueError('自动选区计算设备无效')
    if set(request) == original:
        if type(request['path']) is not str or not request['path']:
            raise ValueError('自动选区源文件路径无效')
        packet = None
    else:
        packet = I.read_packet(root, request['immutable_input'], binding)
    installation, _receipt = activate()
    if packet is None:
        from ..prompted_mask_source import decode_source
        pixels = decode_source(request['path'], binding, device='cpu')
        result = predict(pixels, request['device'], installation=installation)
    else:
        result = predict(None, request['device'], installation=installation, immutable_input=packet)
    result['source'] = binding
    result['source_image'] = 'data:image/png;base64,' + png(result.pop('pixels'))
    if packet is not None:
        I.validate_result(packet, result)
    fields, supports = result.pop('fields'), result.pop('supports')
    result['fields_sha256'] = {key: hashlib.sha256(fields[key].tobytes() + supports[key].tobytes()).hexdigest()
                               for key in fields}
    result['counts'] = {key: int((field > 0).sum()) for key, field in fields.items()}
    result['_fields'] = {key: {'labels': png(fields[key]), 'support': png(supports[key])} for key in fields}
    result['candidate_overlays'] = {key: 'data:image/png;base64,' + overlay_png(fields[key]) for key in fields}
    result['proposal_only'] = True
    result['review_required'] = True
    result['horizon_automatic'] = False
    data = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
    if len(data) > M.MAX_RESULT_BYTES:
        raise ValueError('自动选区结果超过传输预算')
    with (root / 'result.json').open('xb') as output:
        output.write(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True)
    parser.add_argument('--parent-pid', type=int, required=True)
    args = parser.parse_args()
    root = Path(args.directory)
    try:
        from ..inspection_worker import bind_parent
        bind_parent(args.parent_pid)
        for key, limit in ((resource.RLIMIT_CPU, 180), (resource.RLIMIT_FSIZE, M.MAX_RESULT_BYTES)):
            _, hard = resource.getrlimit(key)
            limit = limit if hard == resource.RLIM_INFINITY else min(hard, limit)
            resource.setrlimit(key, (limit, limit))
        for key, value in {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'DO_NOT_TRACK': '1',
                           'HF_HUB_DISABLE_TELEMETRY': '1', 'OMP_NUM_THREADS': '2',
                           'OPENBLAS_NUM_THREADS': '2', 'PYTHONDONTWRITEBYTECODE': '1'}.items():
            os.environ[key] = value
        sys_dont_write_bytecode()
        from ..privacy import install_offline_policy
        install_offline_policy()
        run(root)
    except Exception as error:
        with (root / 'error.json').open('x') as output:
            json.dump({'error': str(error)[:2000]}, output, ensure_ascii=False)
        raise SystemExit(1)


def sys_dont_write_bytecode():
    import sys
    sys.dont_write_bytecode = True


if __name__ == '__main__':
    main()
