"""Display-referred sRGB curves; Rust compiles, NumPy/Torch evaluate coefficients.

Recipes store control points only, never trust a file's alleged compiled bundle.
The compiler is a packaged, dependency-free Rust executable, not a Python spline.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import json
import math
import subprocess
import numpy as np
from ..optional_dependencies import optional_module

torch = optional_module('torch')
CHANNELS = ('master', 'red', 'green', 'blue')
HEADER = dict(version=1, space='srgb-display', interpolation='pchip', boundary='linear')


def default_curves():
    return dict(**HEADER, enabled=True, **{c: [[0., 0.], [1., 1.]] for c in CHANNELS})


def check_curves(value):
    if value is None:
        return default_curves()
    if not isinstance(value, dict) or set(value) != set(HEADER) | {'enabled', *CHANNELS}:
        raise ValueError('curves: expected complete versioned RGB/master recipe')
    if any(value[k] != v or type(value[k]) is not type(v) for k, v in HEADER.items()):
        raise ValueError('curves: unsupported schema, colour space or interpolation')
    if type(value['enabled']) is not bool:
        raise ValueError('curves: enabled must be boolean')
    result = dict(**HEADER, enabled=value['enabled'])
    for channel in CHANNELS:
        points = value[channel]
        if not isinstance(points, (list, tuple)) or not 2 <= len(points) <= 64:
            raise ValueError('curves: each channel needs 2..64 points')
        clean = []
        for point in points:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError('curves: points are x/y pairs')
            if any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in point):
                raise ValueError('curves: finite x/y in [0,1] required')
            x, y = map(float, point)
            if clean and x - clean[-1][0] < 1e-5:
                raise ValueError('curves: x values must strictly increase with spacing >= 1e-5')
            clean.append([x, y])
        if clean[0][0] != 0 or clean[-1][0] != 1:
            raise ValueError('curves: endpoint x values must be 0 and 1')
        result[channel] = clean
    return result


def is_identity(value):
    spec = check_curves(value)
    return not spec['enabled'] or all(x == y for c in CHANNELS for x, y in spec[c])


def _compiler_path():
    return Path(__file__).resolve().parent.parent / 'bin' / 'curve-compiler'


@lru_cache(maxsize=256)
def _compile_channel(points):
    if all(x == y for x, y in points):
        return None
    compiler = _compiler_path()
    if not compiler.is_file():
        raise RuntimeError('Rust curve compiler missing; rebuild/install the matching engine package')
    request = str(len(points)) + ' ' + ' '.join(repr(v) for p in points for v in p)
    run = subprocess.run([str(compiler)], input=request, text=True, capture_output=True,
                         timeout=3, check=False)
    if run.returncode:
        raise ValueError('Rust curve compilation failed: ' + run.stderr[:512])
    if len(run.stdout) > 32768:
        raise ValueError('invalid curve compiler output size')
    data = json.loads(run.stdout)
    if data.get('version') != 1 or data.get('identity') is not False:
        raise ValueError('invalid curve compiler result')
    rows = np.asarray(data['segments'], dtype=np.float64)
    lower = np.asarray(data['lower'], dtype=np.float64)
    upper = np.asarray(data['upper'], dtype=np.float64)
    if rows.shape != (len(points)-1, 6) or lower.shape != (2,) or upper.shape != (2,):
        raise ValueError('invalid curve compiler coefficient shape')
    if not all(np.isfinite(v).all() for v in (rows, lower, upper)) or not (rows[:, 1] > 0).all():
        raise ValueError('nonfinite curve coefficients')
    # These arrays are immutable shared cache entries; never update them in place.
    for arr in (rows, lower, upper):
        arr.flags.writeable = False
    return rows, lower, upper


def compile_curves(value):
    spec = check_curves(value)
    if not spec['enabled']:
        return (None,) * 4
    return tuple(_compile_channel(tuple(map(tuple, spec[c]))) for c in CHANNELS)


def _eval_np(x, bundle):
    if bundle is None:
        return x
    rows, lower, upper = bundle
    idx = np.searchsorted(rows[1:, 0], x, side='right')
    # Gather one coefficient at a time; never allocate image_size x 6 rows.
    t = (x-rows[:, 0][idx])/rows[:, 1][idx]
    result = rows[:, 2][idx] + t*(rows[:, 3][idx] + t*(rows[:, 4][idx] + t*rows[:, 5][idx]))
    result = np.where(x < 0, lower[0]+x*lower[1], result)
    result = np.where(x > 1, upper[0]+(x-1)*upper[1], result)
    return result.astype(x.dtype, copy=False)


def curves_np(rgb, spec):
    bundles = compile_curves(spec)
    if all(b is None for b in bundles):
        return rgb
    if rgb.ndim < 1 or rgb.shape[-1] != 3 or not np.issubdtype(rgb.dtype, np.floating):
        raise ValueError('curves_np expects floating RGB with last dimension 3')
    return np.stack([_eval_np(_eval_np(rgb[..., i], bundles[0]), bundles[i+1])
                     for i in range(3)], axis=-1)


def tensor_bundles(spec, device, dtype):
    """Called when recipe/device changes, not once per rendered frame."""
    return tuple(None if bundle is None else tuple(torch.tensor(a.copy(), device=device, dtype=dtype)
                 for a in bundle) for bundle in compile_curves(spec))


def _eval_t(x, bundle):
    if bundle is None:
        return x
    rows, lower, upper = bundle
    idx = torch.bucketize(x.contiguous(), rows[1:, 0].contiguous(), right=True)
    # Gather one coefficient at a time; never allocate image_size x 6 rows.
    t = (x-rows[:, 0][idx])/rows[:, 1][idx]
    result = rows[:, 2][idx] + t*(rows[:, 3][idx] + t*(rows[:, 4][idx] + t*rows[:, 5][idx]))
    result = torch.where(x < 0, lower[0]+x*lower[1], result)
    return torch.where(x > 1, upper[0]+(x-1)*upper[1], result)


def curves_t(rgb, bundles):
    if all(b is None for b in bundles):
        return rgb
    if rgb.ndim != 4 or rgb.shape[1] != 3:
        raise ValueError('curves_t expects NCHW RGB')
    return torch.stack([_eval_t(_eval_t(rgb[:, i], bundles[0]), bundles[i+1])
                        for i in range(3)], dim=1)
