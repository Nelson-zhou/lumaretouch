# SPDX-License-Identifier: GPL-3.0-or-later
"""Immutable operation-owned manual sample vectors, not a second people graph."""
from copy import deepcopy
import json
from . import people_state as P, local_mask_recipe as M
from . import hair_colour_assets as HAIR, hair_colour_evidence as EVIDENCE
from . import hair_unification_state as S

VERSION = 1
KIND = S.KIND
MAX_ASSETS = 4096
MAX_BYTES = 16 * 1024 * 1024
digest = HAIR.digest
source = HAIR.source
empty_mask = HAIR.empty_mask


def sample(value):
    value = M.check_stack(value)
    if any(obj['kind'] not in ('brush', 'radial') or obj['operation'] not in ('add', 'subtract')
           for obj in value['objects']):
        raise ValueError('Mark roots/tips manually in the actual source; no face box, inferred or transferred sample')
    return value


def check(value):
    fields = {'version', 'operation_id', 'face_ref', 'source', 'semantic_model_sha256',
              'semantic_evidence_sha256', 'support_sha256', 'hair_colour_asset_sha256',
              'root_sample', 'tip_sample', 'review'}
    if (type(value) is not dict or set(value) != fields or type(value['version']) is not int
            or value['version'] != VERSION or value['operation_id'] != S.OP):
        raise ValueError('Invalid hair-unification sample asset')
    ref = P.check_ref(value['face_ref']); binding = source(value['source'])
    if ref['asset_sha256'] != binding['sha256']:
        raise ValueError('Hair-unification samples belong to another photograph')
    for key in ('semantic_model_sha256', 'semantic_evidence_sha256', 'support_sha256', 'hair_colour_asset_sha256'):
        P.digest(value[key])
    if value['semantic_model_sha256'] != HAIR.MODEL_SHA256:
        raise ValueError('Hair unification requires the retained admitted real hair class')
    out = {**deepcopy(value), 'face_ref': ref, 'source': binding,
           'root_sample': sample(value['root_sample']), 'tip_sample': sample(value['tip_sample'])}
    content = {key: val for key, val in out.items() if key != 'review'}
    expected = {'method': 'explicit_source_root_tip_review', 'confirmed': True, 'review_key': digest(content)}
    if type(value['review']) is not dict or value['review'] != expected or type(value['review'].get('confirmed')) is not bool:
        raise ValueError('Root/tip review does not match these exact owned source vectors')
    return out


def reviewed(hair_record, root_sample, tip_sample, *, confirmed):
    hair = HAIR.check(hair_record)
    if confirmed is not True:
        raise ValueError('Confirm manually painted reference samples belong to this person')
    value = {'version': VERSION, 'operation_id': S.OP, 'face_ref': hair['face_ref'], 'source': hair['source'],
             'semantic_model_sha256': hair['semantic_model_sha256'],
             'semantic_evidence_sha256': hair['semantic_evidence_sha256'],
             'support_sha256': hair['review']['review_key'], 'hair_colour_asset_sha256': digest(hair),
             'root_sample': sample(root_sample), 'tip_sample': sample(tip_sample)}
    value['review'] = {'method': 'explicit_source_root_tip_review', 'confirmed': True, 'review_key': digest(value)}
    return check(value)


def check_store(bank):
    if (type(bank) is not dict or len(bank) > MAX_ASSETS
            or len(json.dumps(bank, allow_nan=False).encode()) > MAX_BYTES):
        raise ValueError('Hair-unification sample bank exceeds its retained-vector budget')
    for key, value in bank.items():
        P.digest(key)
        if digest(check(value)) != key:
            raise ValueError('Hair-unification immutable sample hash mismatch')
    return deepcopy(bank)


def verify_record(value, hair_assets, evidence_bank=None):
    value = check(value)
    hair = hair_assets.get(value['hair_colour_asset_sha256'])
    if hair is None:
        raise ValueError('Referenced reviewed hair support is missing')
    hair = HAIR.check(hair)
    if (digest(hair) != value['hair_colour_asset_sha256'] or hair['face_ref'] != value['face_ref']
            or hair['source'] != value['source'] or hair['review']['review_key'] != value['support_sha256']
            or any(hair[key] != value[key] for key in ('semantic_model_sha256', 'semantic_evidence_sha256'))):
        raise ValueError('Root/tip samples do not match exact source, face, semantics and reviewed hair support')
    if evidence_bank is not None:
        saved = evidence_bank.get(value['semantic_evidence_sha256'])
        if saved is None or EVIDENCE.identity(EVIDENCE.decode(saved)) != value['semantic_evidence_sha256']:
            raise ValueError('Hair-unification measured semantic evidence is missing or corrupt')
        if saved['source'] != value['source'] or saved['model_sha256'] != value['semantic_model_sha256']:
            raise ValueError('Hair-unification semantic evidence belongs to another source')
    return hair


def resolve(state, bank, face_ref, hair_assets):
    face = HAIR.verify_face(state, face_ref)
    descriptor = face['local_assets'].get(KIND)
    if descriptor is None:
        return None
    key = descriptor['content_sha256']; raw = bank.get(key)
    if raw is None:
        raise ValueError('Retained hair-unification samples are missing; not silently ignored')
    value = check(raw)
    if (digest(value) != key or value['face_ref'] != face_ref
            or descriptor != {'owner': face_ref, 'kind': KIND, 'content_sha256': key}):
        raise ValueError('Hair-unification sample reference changed or belongs to another target')
    verify_record(value, hair_assets)
    HAIR.verify_face(state, face_ref, value['source'])
    return value


def current_support(state, value, hair_assets):
    """Changing tint/recovery alone does not invalidate the same reviewed support."""
    retained = verify_record(value, hair_assets)
    current = HAIR.resolve(state, hair_assets, value['face_ref'])
    if current is None or current['review']['review_key'] != value['support_sha256']:
        raise ValueError('Reviewed hair ownership changed; repaint/review root and tip samples')
    return retained


def retain(state, bank, value, hair_assets):
    out = P.check(state); value = check(value); face = HAIR.verify_face(out, value['face_ref'], value['source'])
    current_support(out, value, hair_assets)
    bank = check_store(bank); key = digest(value)
    if key in bank and bank[key] != value:
        raise ValueError('Hair-unification sample content collision')
    bank[key] = value; bank = check_store(bank)
    descriptor = {'owner': value['face_ref'], 'kind': KIND, 'content_sha256': key}
    if face['local_assets'].get(KIND) != descriptor:
        face['local_assets'][KIND] = descriptor; out['revision'] += 1
    return P.check(out), bank


def verify_graph(state, bank, hair_assets, evidence_bank=None):
    state = P.check(state); bank = check_store(bank)
    for value in bank.values():
        verify_record(value, hair_assets, evidence_bank)
    for face in state['faces'].values():
        if KIND in face['local_assets']:
            resolve(state, bank, P.face_ref(face), hair_assets)
    return bank
