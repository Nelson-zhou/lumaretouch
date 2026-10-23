"""Lossless, bounded retained source-class evidence. Replay requires no ML weights.

Only actual producer output enters retain(). Project data is integrity-checked,
not relabelled as a new inference. Source identity + shape + model + content hash
pin each bank record; no crop, resampling, quantization or model download here.
"""
import base64
from copy import deepcopy
import hashlib
import json
import zlib
import numpy as np
from . import hair_colour_analysis as E, hair_colour_assets as A

KEY = 'hair_colour_evidence'
MAX_RAW_BYTES = 64*1024*1024
MAX_COMPRESSED_BYTES = 32*1024*1024
MAX_STORE_BYTES = 128*1024*1024
_MISSING = object()


def identity(value):
    E.check(value, value['source'])
    metadata = {key: item for key, item in value.items() if key != 'weight'}
    metadata['shape'] = list(value['weight'].shape)
    return A.digest(metadata)


def encode(value):
    E.check(value, value['source']); weight = np.ascontiguousarray(value['weight'], dtype='<f4')
    if weight.nbytes > MAX_RAW_BYTES: raise ValueError('Retained measured hair field exceeds the lossless asset budget; no downsampling was substituted')
    compressed = zlib.compress(weight.tobytes(), level=6)
    if len(compressed) > MAX_COMPRESSED_BYTES: raise ValueError('Retained hair evidence exceeds compressed asset budget')
    result = {key: deepcopy(item) for key, item in value.items() if key != 'weight'}
    result.update(shape=list(weight.shape), encoding='zlib-le-f32-v1', data=base64.b64encode(compressed).decode())
    return result


def decode(record):
    fields = {'domain','source','model_sha256','producer','weight_sha256','shape','encoding','data'}
    if type(record) is not dict or set(record) != fields or record['encoding'] != 'zlib-le-f32-v1':
        raise ValueError('Invalid retained hair evidence format')
    shape = record['shape']
    if type(shape) is not list or len(shape) != 2 or any(type(n) is not int or not 1 <= n <= 65536 for n in shape):
        raise ValueError('Invalid retained hair evidence dimensions')
    size = shape[0]*shape[1]*4
    if size > MAX_RAW_BYTES or type(record['data']) is not str or len(record['data']) > ((MAX_COMPRESSED_BYTES+2)//3)*4:
        raise ValueError('Retained hair evidence exceeds bounded decode budget')
    try:
        compressed = base64.b64decode(record['data'], validate=True)
        if len(compressed) > MAX_COMPRESSED_BYTES: raise ValueError('Compressed hair evidence exceeds budget')
        decoder = zlib.decompressobj(); raw = decoder.decompress(compressed, size+1)
        if len(raw) != size or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError('Retained hair evidence size/stream mismatch')
    except (ValueError, zlib.error) as error:
        raise ValueError('Retained hair evidence is corrupt or exceeds its declared length') from error
    if hashlib.sha256(raw).hexdigest() != record['weight_sha256']: raise ValueError('Retained hair field checksum mismatch')
    weight = np.frombuffer(raw, dtype='<f4').reshape(shape).copy(); weight.setflags(write=False)
    value = {key: deepcopy(item) for key, item in record.items() if key not in ('shape','encoding','data')}
    value['weight'] = weight; E.check(value, value['source'])
    return value


def check_store(store):
    if type(store) is not dict or len(store) > 4096 or len(json.dumps(store,allow_nan=False).encode()) > MAX_STORE_BYTES:
        raise ValueError('Retained hair semantic bank exceeds project budget')
    sources = set()
    for key, record in store.items():
        A.P.digest(key); value = decode(record)
        if identity(value) != key: raise ValueError('Hair semantic bank identity mismatch')
        source_key = value['source']['sha256']
        if source_key in sources: raise ValueError('A source has ambiguous retained hair evidence')
        sources.add(source_key)
    return deepcopy(store)


def retain(store, value):
    out = check_store(store); key = identity(value)
    for saved_key, record in out.items():
        if record['source']['sha256'] == value['source']['sha256'] and saved_key != key:
            raise ValueError('Frozen hair evidence cannot be silently replaced by a new analysis')
    out[key] = encode(value); check_store(out)
    return out, key


def for_source(store, binding):
    binding = A.source(binding)
    matches = [(key, record) for key, record in store.items() if record['source']['sha256'] == binding['sha256']]
    if not matches: return None
    if len(matches) != 1 or matches[0][1]['source'] != binding: raise ValueError('Retained hair evidence source/dimensions are ambiguous')
    key, record = matches[0]; value = decode(record)
    if identity(value) != key: raise ValueError('Retained hair evidence identity mismatch')
    return value


def current(engine, binding, precompute=_MISSING):
    bank = engine.__dict__.setdefault('_hair_colour_evidence', {})
    saved = for_source(bank, binding)
    if saved is not None: return saved  # No model installation/load/inference.
    value = E.capture(engine._precompute if precompute is _MISSING else precompute, binding)
    engine._hair_colour_evidence, _ = retain(bank, value)
    return value


def verify_assets(assets, bank):
    bank = check_store(bank)
    for record in A.check_store(assets).values():
        key = record['semantic_evidence_sha256']; saved = bank.get(key)
        if saved is None or saved['source'] != record['source'] or saved['model_sha256'] != record['semantic_model_sha256']:
            raise ValueError('Hair support references missing/foreign retained semantic evidence')
    return bank
