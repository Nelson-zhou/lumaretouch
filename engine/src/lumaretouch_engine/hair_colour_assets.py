"""Append-only face/source-owned reviewed support and effect-only recovery vectors.

One content reference lives in the canonical people graph. This store contains no
person associations, parameter inheritance, undo stack or detector-index identity.
Explicit source-view review is required even if exactly one face was detected.
"""
from copy import deepcopy
import hashlib
import json
from . import people_state as P, local_mask_recipe as M

VERSION = 1
KIND = 'hair_colour'
MODEL_SHA256 = 'c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0'
MAX_ASSETS = 4096
MAX_STORE_BYTES = 16*1024*1024


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def empty_mask(): return {'version': M.VERSION, 'domain': M.DOMAIN, 'objects': []}


def source(value):
    if type(value) is not dict or set(value) != {'sha256', 'width', 'height'}:
        raise ValueError('Hair support needs canonical source identity and dimensions')
    P.digest(value['sha256'])
    for key in ('width', 'height'):
        if type(value[key]) is not int or not 1 <= value[key] <= 65536: raise ValueError('Invalid hair source size')
    if value['width']*value['height'] > M.MAX_PIXELS: raise ValueError('Hair source exceeds 64 MP')
    return deepcopy(value)


def mask(value, *, recovery=False):
    out = M.check_stack(value)
    allowed = ('brush', 'radial') if recovery else ('brush', 'radial', 'prompted')
    if any(o['kind'] not in allowed for o in out['objects']):
        raise ValueError('Hair ownership must be explicit spatial/manual or reviewed prompted support, not a full/semantic/colour shortcut')
    if any(o['operation'] == 'intersect' for o in out['objects']):
        raise ValueError('Hair correction uses explicit add/subtract objects; hair confidence intersection is applied separately')
    if not recovery and not any(o['enabled'] and o['operation'] == 'add' and o['opacity'] > 0 for o in out['objects']):
        raise ValueError('请在源图上标出所选人物的头发范围；选择人脸不是头发实例分割')
    return out


def review_key(face_ref, binding, support, semantic_sha, evidence_sha):
    return digest({'face_ref': P.check_ref(face_ref), 'source': source(binding),
                   'support': mask(support), 'semantic_model_sha256': P.digest(semantic_sha),
                   'semantic_evidence_sha256': P.digest(evidence_sha)})


def check(value):
    fields = {'version', 'face_ref', 'source', 'semantic_model_sha256', 'semantic_evidence_sha256', 'support', 'recovery', 'review'}
    if type(value) is not dict or set(value) != fields or type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('Invalid hair support asset')
    ref = P.check_ref(value['face_ref']); binding = source(value['source'])
    if binding['sha256'] != ref['asset_sha256']: raise ValueError('Hair support belongs to another photograph')
    sha = P.digest(value['semantic_model_sha256'])
    if sha != MODEL_SHA256: raise ValueError('Hair support requires the admitted pinned six-class model')
    evidence_sha = P.digest(value['semantic_evidence_sha256'])
    support = mask(value['support']); recovery = mask(value['recovery'], recovery=True)
    expected = {'method': 'explicit_source_review', 'review_key': review_key(ref, binding, support, sha, evidence_sha), 'confirmed': True}
    if type(value['review']) is not dict or type(value['review'].get('confirmed')) is not bool or value['review'] != expected: raise ValueError('Hair support needs explicit review of this exact source, face and support')
    return {'version': VERSION, 'face_ref': ref, 'source': binding, 'semantic_model_sha256': sha,
            'semantic_evidence_sha256': evidence_sha, 'support': support, 'recovery': recovery, 'review': expected}


def reviewed(face_ref, binding, support, semantic_sha, *, evidence_sha, confirmed, recovery=None):
    if confirmed is not True: raise ValueError('请先确认选区仅包含所选人物的头发')
    return check({'version': VERSION, 'face_ref': face_ref, 'source': binding, 'semantic_model_sha256': semantic_sha,
        'semantic_evidence_sha256': evidence_sha, 'support': support, 'recovery': empty_mask() if recovery is None else recovery,
        'review': {'method': 'explicit_source_review', 'review_key': review_key(face_ref, binding, support, semantic_sha, evidence_sha), 'confirmed': True}})


def verify_face(state, ref, binding=None):
    ref = P.check_ref(ref); face = state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref: raise ValueError('Hair target face/source/analysis changed')
    ev = face['evidence']
    if ev['status'] != 'verified' or ev['backend'] != 'mediapipe' or ev['semantic_model_sha256'] != MODEL_SHA256:
        raise ValueError('Hair editing needs verified retained source/model evidence')
    if binding is not None and (binding['sha256'] != ref['asset_sha256'] or
            (binding['width'], binding['height']) != (ev['source_width'], ev['source_height'])):
        raise ValueError('Hair source dimensions differ from retained analysis')
    return face


def retain(state, assets, record):
    out = P.check(state); record = check(record); face = verify_face(out, record['face_ref'], record['source'])
    store = check_store(assets); key = digest(record)
    if key in store and store[key] != record: raise ValueError('Hair asset digest collision')
    store[key] = record; check_store(store)
    descriptor = {'owner': record['face_ref'], 'kind': KIND, 'content_sha256': key}
    if face['local_assets'].get(KIND) != descriptor:
        face['local_assets'][KIND] = descriptor; out['revision'] += 1
    return P.check(out), store


def resolve(state, assets, face_ref):
    face = verify_face(state, face_ref)
    descriptor = face['local_assets'].get(KIND)
    if descriptor is None: return None
    key = descriptor['content_sha256']; raw = assets.get(key)
    if raw is None: raise ValueError('Retained hair support/recovery asset is missing; not ignored')
    record = check(raw)
    if digest(record) != key or descriptor != {'owner': face_ref, 'kind': KIND, 'content_sha256': key} or record['face_ref'] != face_ref:
        raise ValueError('Hair support asset is changed or belongs to another face')
    verify_face(state, face_ref, record['source'])
    return record


def detach(state, face_ref):
    out = P.check(state); face = verify_face(out, face_ref)
    if KIND in face['local_assets']:
        del face['local_assets'][KIND]; out['revision'] += 1
    return P.check(out)  # Append-only store is deliberately untouched for undo.


def check_store(assets):
    if type(assets) is not dict or len(assets) > MAX_ASSETS or len(json.dumps(assets, allow_nan=False).encode()) > MAX_STORE_BYTES:
        raise ValueError('Hair asset store exceeds the retained-vector budget')
    for key, raw in assets.items():
        P.digest(key)
        if digest(check(raw)) != key: raise ValueError('Hair asset store hash mismatch')
    return deepcopy(assets)


def verify_graph(state, assets):
    state = P.check(state); store = check_store(assets)
    for face in state['faces'].values():
        if KIND in face['local_assets']: resolve(state, store, P.face_ref(face))
    return store
