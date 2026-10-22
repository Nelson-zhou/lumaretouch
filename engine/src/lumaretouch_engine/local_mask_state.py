"""Retained mask intent, source binding and disposable preview fields.

The grade consumer follows deformation and LUT. Geometry and range selection
refer to immutable working-sRGB source pixels; the real deformation grid warps
the composed mask at the grade mixer, never inferred from displayed pixels.
"""
from copy import deepcopy
import hashlib
import json
import os
import re
import numpy as np
from . import local_mask_recipe as R


def empty():
    return {'recipe': {'version': 1, 'domain': 'source-normalized', 'objects': []},
            'source': None, 'semantic_owner': None}


def check(value):
    if value is None: return empty()
    if type(value) is not dict or set(value) != {'recipe', 'source', 'semantic_owner'}:
        raise ValueError('Invalid retained mask state')
    recipe = R.check_stack(value['recipe'])
    source = value['source']
    if source is not None:
        if (type(source) is not dict or set(source) != {'sha256', 'width', 'height'}
                or type(source['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', source['sha256'])
                or any(type(source[k]) is not int or source[k] < 1 for k in ('width', 'height'))):
            raise ValueError('Invalid mask source binding')
    if recipe['objects'] and source is None: raise ValueError('Mask objects require their source binding')
    owner = value['semantic_owner']
    if owner is not None:
        if (type(owner) is not dict or set(owner) != {'backend', 'contract'}
                or any(type(owner[k]) is not str or not 1 <= len(owner[k]) <= 128 for k in owner)):
            raise ValueError('Invalid semantic mask owner')
    return deepcopy({'recipe': recipe, 'source': source, 'semantic_owner': owner})


def file_stamp(path):
    st = os.stat(path)
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def source_digest(path):
    before = file_stamp(path)
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        while chunk := stream.read(1024 * 1024): h.update(chunk)
    if file_stamp(path) != before: raise ValueError('Source changed while identifying mask input')
    return h.hexdigest()


def verify_source(value, path, shape=None):
    source = value['source']
    if source is None: return
    if shape is not None and (source['height'], source['width']) != tuple(shape):
        raise ValueError('Mask source dimensions changed; retained objects are suspended')
    if source_digest(path) != source['sha256']:
        raise ValueError('Mask source content changed; retained objects are suspended')


SEMANTIC_CONTRACT = 'mediapipe-selfie-multiclass-six-classes-v1'


def semantic_owner(pc, backend):
    digest = getattr(pc, 'semantic_model_sha256', None)
    if type(digest) is not str or not re.fullmatch('[0-9a-f]{64}', digest): return None
    return {'backend': str(backend or 'unknown'), 'contract': SEMANTIC_CONTRACT + ':' + digest}


def current_owner(engine):
    return semantic_owner(engine._precompute, engine._precompute_backend)


def owner_from_state(st):
    return semantic_owner(st.get('_precompute'), st.get('_precompute_backend'))


def bind_source(engine):
    row = engine._docs[engine._doc_index]
    if row.get('_local_source_stamp') != file_stamp(row['path']):
        raise ValueError('Source file changed after decoding; reopen before drawing masks')
    return {'sha256': source_digest(row['path']), 'width': int(row['src_w']), 'height': int(row['src_h'])}


def state(engine):
    value = check(getattr(engine, '_local_masks', None))
    pipe = engine._vram
    from .semantic_sources import SOURCE_LABELS
    from . import local_grade_layers as L
    return {'recipe': value['recipe'], 'bound': engine._grade_scope == 'objects',
            'transfer_groups': L.inventory({'_local_masks':value, '_grade_scope':engine._grade_scope,
                '_grade':engine._grade, '_local_grade_layers':getattr(engine,'_local_grade_layers',None)}),
            'layers': L.report({'_local_grade_layers': getattr(engine, '_local_grade_layers', None)},
                               getattr(getattr(pipe, 'local_grade_layers', None), 'suspended', None)),
            'channel_labels': dict(SOURCE_LABELS), 'semantic_scope': 'whole-photo-category',
            'suspended': getattr(pipe, 'local_mask_suspended', None),
            'channels': sorted((getattr(engine._precompute, 'masks', None) or {}).keys()) if current_owner(engine) else []}


def sync(engine, *, strict=False):
    pipe = engine._vram
    if pipe is None or engine._grade_scope != 'objects': return
    value = check(engine._local_masks)
    row = engine._docs[engine._doc_index] if 0 <= engine._doc_index < len(engine._docs) else {}
    pc = engine._precompute
    key = None
    try:
        stamp = file_stamp(row['path'])
        from . import prompted_mask_resolver as P
        prompted_stamp = P.dependency_stamp() if P.active(value['recipe']) else None
        key = (json.dumps(value, sort_keys=True), stamp, id(pipe.src_f32), id(pc),
               json.dumps(current_owner(engine), sort_keys=True), prompted_stamp)
        if getattr(pipe, '_local_mask_key', None) == key:
            pipe.grade_scope = 'objects'
            if strict and pipe.local_mask_suspended: raise ValueError(pipe.local_mask_suspended)
            return
        if row.get('_local_source_stamp') != stamp:
            raise ValueError('Source file changed after decoding; reopen this photo')
        verify_source(value, row['path'], (row['src_h'], row['src_w']))
        needs_rgb, channels = R.dependencies(value['recipe'])
        if channels and (value['semantic_owner'] is None or value['semantic_owner'] != current_owner(engine)):
            raise ValueError('Analysis backend or semantic contract changed; mask is suspended')
        semantic = dict(getattr(pc, 'masks', None) or {})
        semantic.update(P.fields(value['recipe'], value['source'], row['path'], (pipe.h, pipe.w)))
        rgb = pipe.src_f32[0].permute(1, 2, 0).detach().cpu().numpy() if needs_rgb else None
        weight = R.raster(value['recipe'], (pipe.h, pipe.w), rgb=rgb, semantic=semantic)
        pipe.set_local_mask(weight)
        pipe._local_mask_key = key
    except Exception as error:
        pipe.set_local_mask(np.zeros((pipe.h, pipe.w), np.uint8), reason=str(error))
        pipe._local_mask_key = key
        if strict: raise


def export_prepare(spec, source, *, cancelled=lambda: False):
    if spec.grade_scope != 'objects': return
    if spec.local_masks is None: raise ValueError('Composed grade mask recipe is missing')
    value = check(spec.local_masks)
    h, w = source.shape[:2]
    if value['source'] and (h, w) != (value['source']['height'], value['source']['width']):
        raise ValueError('Export source dimensions differ from retained mask source')
    # RGB stays in this process; the raster bridge sends bounded tiles only.
    from . import prompted_mask_resolver as P
    semantics = dict(spec.local_mask_semantics)
    if P.active(value['recipe']):
        if not spec.local_mask_source_path:
            raise ValueError('Prompted export requires the bound original source path')
        semantics.update(P.fields(value['recipe'], value['source'], spec.local_mask_source_path,
                                  (h, w), force=True, cancelled=cancelled))
    spec.grade_mask = R.raster(value['recipe'], (h, w), rgb=source, semantic=semantics)


def diagnostic(engine):
    """Read-only persisted composition on the original source grid, not a draft."""
    pipe = engine._vram
    try:
        value = check(engine._local_masks)
        row = engine._docs[engine._doc_index]
        if row.get('_local_source_stamp') != file_stamp(row['path']):
            raise ValueError('Source changed since decoding')
        verify_source(value, row['path'], (row['src_h'], row['src_w']))
        needs_rgb, channels = R.dependencies(value['recipe'])
        if channels and (value['semantic_owner'] is None or value['semantic_owner'] != current_owner(engine)):
            raise ValueError('Semantic analysis unavailable or changed')
        rgb = pipe.src_f32[0].permute(1, 2, 0).detach().cpu().numpy() if needs_rgb else None
        masks = dict(getattr(engine._precompute, 'masks', None) or {})
        from .prompted_mask_resolver import fields
        masks.update(fields(value['recipe'], value['source'], row['path'], (pipe.h, pipe.w)))
        return R.raster(value['recipe'], (pipe.h, pipe.w), rgb=rgb, semantic=masks), None
    except Exception as error:
        return np.zeros((pipe.h, pipe.w), np.uint8), str(error)


def check_export_decode(snap, path, before, shape):
    if snap.get('grade_scope') != 'objects': return
    if file_stamp(path) != before:
        raise ValueError('Source changed during full-resolution decoding; export suspended')
    value = check(snap.get('local_masks'))
    source = value['source']
    if source is not None and tuple(shape) != (source['height'], source['width']):
        raise ValueError('Full-resolution source dimensions changed; export suspended')
    # Runtime-only source location. The retained project contains its digest,
    # not a proxy raster or a provider-owned duplicate photograph.
    snap['local_mask_source_path'] = path


def sample_valid_rows(valid):
    """Bounded exact pick validity; coverage alpha cannot stand in for this."""
    if valid.ndim != 2 or valid.shape[0] > 8192: return None
    rows = []
    for row in valid:
        indices = np.flatnonzero(row)
        if not len(indices):
            rows.append([0, 0]); continue
        gaps = np.flatnonzero(np.diff(indices) != 1)
        last = int(gaps[0]) if len(gaps) else len(indices)-1
        rows.append([int(indices[0]), int(indices[last])+1])
    return rows
