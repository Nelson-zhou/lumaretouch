"""Effective pixel source identity, distinct from original-file provenance.

A returned composite is an immutable canonical asset, not the file named by the
photo row. Its content ID includes dimensions, working format and exact RGBA
bytes. Original pathname/fingerprint remain unchanged for recovery/relocation.
"""
import hashlib


def record(state_or_engine):
    from .creative_document_base import from_state
    if isinstance(state_or_engine, dict):
        return from_state(state_or_engine)
    return from_state({'_creative_base':getattr(state_or_engine,'_creative_base',None)})


def binding(state_or_engine, path=None, original_size=None):
    value = record(state_or_engine)
    if value is not None:
        return {'sha256':value['id'][7:],'width':value['width'],'height':value['height']}
    from . import local_mask_state as source
    if not isinstance(state_or_engine, dict):
        return source.bind_source(state_or_engine)
    if path is None or original_size is None:
        raise ValueError('Original snapshot binding needs its original path and dimensions')
    width,height = original_size
    if any(type(v) is not int or v < 1 for v in (width,height)):
        raise ValueError('Invalid original source dimensions')
    return {'sha256':source.source_digest(path),'width':width,'height':height}


def verify(expected, state_or_engine, path=None, original_size=None):
    actual = binding(state_or_engine,path,original_size)
    if expected != actual:
        raise ValueError('Analysis belongs to another effective pixel source')
    return actual


def row_asset(row):
    """Effective portrait identity for an exact remembered document row.

    Unopened originals need not invent dimensions. A derived row instead owns
    its validated canonical extent and content, independent of the shared path.
    Callers must remember live state before using a parked-row transaction.
    """
    value = record(row.get('state') or {})
    if value is not None:
        return value['id'][7:]
    from .local_mask_state import source_digest
    return source_digest(row['path'])


def check_row_proof(proof):
    """Validate JSON-safe planner/history evidence without reading a file."""
    from copy import deepcopy
    from .people_state import digest
    if type(proof) is not dict or set(proof) != {'asset_sha256','creative_source','original_sha256'}:
        raise ValueError('Incomplete effective portrait source proof')
    digest(proof['asset_sha256']); digest(proof['original_sha256'])
    source = proof['creative_source']
    if source is None:
        if proof['asset_sha256'] != proof['original_sha256']:
            raise ValueError('Original portrait proof names another source')
    else:
        if type(source) is not dict or set(source) != {'sha256','width','height'}:
            raise ValueError('Incomplete derived portrait source extent')
        digest(source['sha256'])
        if source['sha256'] != proof['asset_sha256'] or any(type(source[key]) is not int or source[key] < 1 for key in ('width','height')):
            raise ValueError('Invalid derived portrait source identity')
    return deepcopy(proof)


def row_proof(row):
    """Keep immutable effective pixels and physical provenance as two proofs."""
    state = row.get('state') or {}
    value = record(state)
    from .local_mask_state import source_digest
    original = source_digest(row['path'])
    source = None if value is None else {'sha256':value['id'][7:],'width':value['width'],'height':value['height']}
    return check_row_proof({'asset_sha256':original if source is None else source['sha256'],
                           'creative_source':source,'original_sha256':original})


def verify_row(row, expected):
    expected = check_row_proof(expected)
    if row_proof(row) != expected:
        raise ValueError('Effective portrait source or original provenance changed')
    return expected


def verify_row_target(row, target):
    """New receipts own both sources; legacy receipts authorize originals only."""
    if target.get('source_proof') is not None:
        proof = verify_row(row,target['source_proof'])
        if proof['asset_sha256'] != target['asset_sha256']:
            raise ValueError('Portrait receipt has conflicting source identities')
        return proof
    if record(row.get('state') or {}) is not None:
        raise ValueError('Legacy portrait receipt lacks derived-source proof')
    if row_asset(row) != target['asset_sha256']:
        raise ValueError('Portrait receipt belongs to another original source')
    return None


def analysis_rgb(engine):
    """Actual source proxy for inference, never original pixels under a new ID.

    Model inference is explicitly uint8 proxy-domain. Full float32 export pixels
    stay canonical and are not replaced by this analysis/display representation.
    """
    value = record(engine)
    if value is None:
        if getattr(engine,'_src_rgb',None) is None:
            raise ValueError('No source pixels are loaded')
        return engine._src_rgb
    from .creative_document_base import proxy_for_state
    from .creative_document_host import memory_budget
    budget = int(getattr(engine,'_proxy_budget',0) or 12_000_000)
    key = (value['id'],budget)
    cache = engine.__dict__.get('_creative_analysis_rgb')
    if cache is not None and cache[0] == key:
        return cache[1]
    rgb = proxy_for_state(None,{'_creative_base':value},max_pixels=budget,max_bytes=memory_budget())
    rgb.setflags(write=False)
    engine._creative_analysis_rgb = (key,rgb)
    return rgb


def stamp_precompute(engine, pc, rgb=None):
    """Called by an inference owner after running its model on exactly rgb."""
    if record(engine) is None:
        pc.input_source_binding = None
        return pc
    if rgb is None: rgb = analysis_rgb(engine)
    proof = binding(engine)
    proof.update(proxy_width=int(rgb.shape[1]),proxy_height=int(rgb.shape[0]),
                 proxy_sha256=hashlib.sha256(memoryview(rgb).cast('B')).hexdigest())
    pc.input_source_binding = proof
    return pc


def verify_precompute(state_or_engine, pc):
    if pc is None: return
    value = record(state_or_engine)
    proof = getattr(pc,'input_source_binding',None)
    if value is None:
        if proof is not None:
            raise ValueError('Derived-source analysis cannot be rebound to the original file')
        return
    keys = {'sha256','width','height','proxy_width','proxy_height','proxy_sha256'}
    if type(proof) is not dict or set(proof) != keys:
        raise ValueError('Composite analysis lacks its exact inference-input binding')
    if {k:proof[k] for k in ('sha256','width','height')} != binding(state_or_engine):
        raise ValueError('Cached analysis belongs to another composite')
    if any(type(proof[k]) is not int or proof[k] < 1 for k in ('proxy_width','proxy_height')):
        raise ValueError('Invalid analysis proxy extent')
    digest = proof['proxy_sha256']
    if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Invalid analysis input digest')
    masks = getattr(pc,'masks',{})
    if any(tuple(mask.shape[:2]) != (proof['proxy_height'],proof['proxy_width']) for mask in masks.values()):
        raise ValueError('Analysis masks do not match their owned input extent')
    # A live owner additionally proves its actual inference input. Frozen
    # snapshots retain the exact proof and immutable source asset for replay.
    if not isinstance(state_or_engine,dict):
        rgb = analysis_rgb(state_or_engine)
        if rgb.shape[:2] != (proof['proxy_height'],proof['proxy_width']) or hashlib.sha256(memoryview(rgb).cast('B')).hexdigest() != digest:
            raise ValueError('Analysis input proxy changed; reanalysis is required')


def restore_history_source(engine):
    """Switch source extent and invalidate mismatched inference before replay."""
    value = record(engine)
    row = engine._docs[engine._doc_index]
    dimensions = ((value['width'],value['height']) if value is not None else
                  getattr(engine,'_creative_original_dimensions',None))
    if dimensions is not None:
        row['src_w'],row['src_h'] = dimensions
    try:
        verify_precompute(engine,engine._precompute)
    except ValueError:
        engine._precompute = None
        engine._people_analysis_key = None
    from .people_open import restore_source
    restore_source(engine)
