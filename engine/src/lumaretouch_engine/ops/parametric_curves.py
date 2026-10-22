"""Validated Rust-owned split-grid LUTs; vector evaluation only, no duplicate shape.

Never accept compiled tables from a project/preset. Compile the complete validated
recipe with the packaged helper; cache immutable CPU data separately from PCHIP.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path
import struct
import subprocess
import numpy as np
from ..optional_dependencies import optional_module

torch = optional_module('torch')
NAMES = ('shadows', 'darks', 'lights', 'highlights')
META = dict(version=1, algorithm='lrt-rt512-parametric-splitgrid-lut-v1',
            space='srgb-display', grid='split-aligned-4x16384', boundary='identity-outside-unit')
REGION_INTERVALS = 16384
SAMPLES = 65537
HEADER = struct.Struct('<4sHHII3d')
PAYLOAD_BYTES = HEADER.size + SAMPLES * 4


def default_parametric():
    return dict(**META, enabled=True, **dict.fromkeys(NAMES, 0.), splits=[.25, .5, .75])


def check_parametric(value):
    if not isinstance(value, dict) or set(value) != {*META, 'enabled', *NAMES, 'splits'}:
        raise ValueError('parametric curves: complete recipe required; unknown fields rejected')
    if any(type(value[k]) is not type(v) or value[k] != v for k, v in META.items()):
        raise ValueError('parametric curves: unsupported version, algorithm or colour/grid domain')
    if type(value['enabled']) is not bool:
        raise ValueError('parametric curves: enabled must be boolean')
    values = [value[k] for k in NAMES]
    if any(type(v) not in (int, float) or not math.isfinite(v) or not -100 <= v <= 100 for v in values):
        raise ValueError('parametric curves: finite values in [-100,100] required')
    splits = value['splits']
    if not isinstance(splits, (tuple, list)) or len(splits) != 3 or any(
            type(v) not in (int, float) or not math.isfinite(v) for v in splits):
        raise ValueError('parametric curves: three finite splits required')
    edges = [0., *splits, 1.]
    if any(b-a + 8*math.ulp(1.) < .01 for a, b in zip(edges, edges[1:])):
        raise ValueError('parametric curves: each region must span at least .01')
    return dict(**META, enabled=value['enabled'], **dict(zip(NAMES, map(float, values))), splits=list(map(float, splits)))


def is_identity(spec):
    return not spec['enabled'] or all(spec[k] == 0 for k in NAMES)


@dataclass(frozen=True)
class Bundle:
    table: object
    left: object
    width: object
    splits: tuple[float, float, float]


def _immutable(values):
    # Immutable bytes ownership prevents even setflags(write=True) on cache data.
    return np.frombuffer(np.asarray(values, np.float64).tobytes(), dtype=np.float64)


def decode(raw: bytes, requested_splits):
    """Validate once at the process boundary, never repeatedly per image pixel."""
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise ValueError('invalid parametric compiler buffer')
    raw = bytes(raw)  # snapshot mutable callers before validation/cache exposure
    if len(raw) != PAYLOAD_BYTES:
        raise ValueError('invalid parametric compiler output size')
    header = HEADER.unpack_from(raw)
    if header[:5] != (b'LPC1', 1, 40, SAMPLES, 1) or header[5:] != tuple(requested_splits):
        raise ValueError('invalid parametric compiler header/grid/split correspondence')
    # Independently validate splits even for decoder callers outside compile_recipe.
    check_parametric({**default_parametric(), 'splits': list(header[5:])})
    table = np.frombuffer(raw, dtype='<f4', count=SAMPLES, offset=HEADER.size)
    if not np.isfinite(table).all() or table[0] != 0 or table[-1] != 1 or np.any(table[1:] < table[:-1]):
        raise ValueError('invalid parametric compiler sample range/order')
    edges = (0., *header[5:], 1.)
    return Bundle(table, _immutable(edges[:-1]), _immutable([b-a for a, b in zip(edges, edges[1:])]), header[5:])


@lru_cache(maxsize=16)
def _compile(values, splits, compiler: Path):
    if not compiler.is_file():
        raise RuntimeError('Rust curve compiler missing; rebuild/install the matching engine package')
    request = 'parametric 1 ' + ' '.join(repr(v) for v in (*values, *splits))
    run = subprocess.run([str(compiler)], input=request.encode('ascii'), capture_output=True, timeout=3, check=False)
    if run.returncode:
        raise ValueError('Rust parametric compilation failed: ' + run.stderr[:512].decode('utf-8', 'replace'))
    return decode(run.stdout, splits)


def compile_recipe(value, compiler):
    spec = check_parametric(value)
    if is_identity(spec):
        return None
    return _compile(tuple(spec[k] for k in NAMES), tuple(spec['splits']), Path(compiler))


def evaluate_np(x, bundle):
    if bundle is None:
        return x
    if not np.issubdtype(x.dtype, np.floating):
        raise ValueError('parametric curves require floating pixels')
    dtype = x.dtype if x.dtype.itemsize >= 4 else np.dtype('float32')
    inside = (x > 0) & (x < 1)
    safe = np.where(inside, x, 0).astype(dtype, copy=False)
    region = sum((safe >= split).astype(np.intp) for split in bundle.splits)
    left = np.asarray(bundle.left, dtype=dtype)
    width = np.asarray(bundle.width, dtype=dtype)
    local = ((safe-left[region])/width[region])*REGION_INTERVALS
    lo = np.clip(np.floor(local), 0, REGION_INTERVALS-1).astype(np.intp)
    fraction = np.clip(local-lo.astype(dtype), 0, 1)
    index = region*REGION_INTERVALS+lo
    a = bundle.table[index].astype(dtype, copy=False)
    b = bundle.table[index+1].astype(dtype, copy=False)
    result = (a+(b-a)*fraction).astype(x.dtype, copy=False)
    return np.where(inside, result, x)


def tensor_bundle(bundle, device, dtype):
    if bundle is None:
        return None
    work_dtype = dtype if dtype in (torch.float32, torch.float64) else torch.float32
    return Bundle(*(torch.tensor(a.copy(), device=device, dtype=work_dtype)
                    for a in (bundle.table, bundle.left, bundle.width)), bundle.splits)


def evaluate_t(x, bundle):
    if bundle is None:
        return x
    if not x.is_floating_point():
        raise ValueError('parametric curves require floating pixels')
    inside = (x > 0) & (x < 1)
    safe = torch.where(inside, x, 0.).to(bundle.table.dtype)
    region = sum((safe >= split).to(torch.long) for split in bundle.splits)
    local = ((safe-bundle.left[region])/bundle.width[region])*REGION_INTERVALS
    lo = local.floor().clamp(0, REGION_INTERVALS-1).to(torch.long)
    fraction = (local-lo.to(local.dtype)).clamp(0, 1)
    index = region*REGION_INTERVALS+lo
    a, b = bundle.table[index], bundle.table[index+1]
    result = (a+(b-a)*fraction).to(x.dtype)
    return torch.where(inside, result, x)
