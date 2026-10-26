# SPDX-License-Identifier: GPL-3.0-or-later
"""Operation-owned manual visible hair/context/protection; no person census.

Retained hair-class weights are editing weights, not probabilities or matting.
Disabled claims remain ownership claims. No prompt/model inference is permitted
at replay: this bounded first slice requires retained manual hair ownership.
AUTHORED / UNRUN; no occlusion classifier or photographic acceptance is claimed.
"""
from copy import deepcopy
import hashlib
import math
import numpy as np
from . import people_state as P, local_mask_recipe as M
from . import hair_colour_assets as H, hair_colour_analysis as A, hair_colour_evidence as E
from . import hair_smoothing_state as S
from .people_support_assets import content_digest

FAMILY = 'hair_smoothing'
KIND = S.KIND
MIN_TEXTURE_SCALE_PX = 1.0
MAX_TEXTURE_SCALE_PX = 8.0
MAX_PIXELS = 32_000_000


def _manual(value, *, protect=False):
    value = M.check_stack(value)
    if any(obj['kind'] != 'brush' or obj['operation'] not in ('add', 'subtract') for obj in value['objects']):
        raise ValueError('Hair smoothing needs independent source-normalized manual brush vectors')
    if protect:
        if any(obj['operation'] != 'add' or not obj['enabled'] or obj['opacity'] != 1 or obj['feather'] != 0
               for obj in value['objects']):
            raise ValueError('Hard protection is enabled opaque unfeathered add paint; delete a stroke to revise')
    elif not any(obj['enabled'] and obj['operation'] == 'add' and obj['opacity'] > 0 for obj in value['objects']):
        raise ValueError('Paint visible owned hair target and its complete nearby directional context')
    return value


def check_review(value, *, source=None):
    required = {'version', 'domain', 'target_recipe', 'context_recipe', 'protect_recipe', 'texture_scale',
                'visible_hair_reviewed', 'protections_reviewed', 'ownership_confirmed'}
    if (type(value) is not dict or set(value) != required or type(value['version']) is not int
            or value['version'] != 1 or value['domain'] != 'source-normalized'
            or any(value[k] is not True for k in ('visible_hair_reviewed', 'protections_reviewed', 'ownership_confirmed'))):
        raise ValueError('Independently review visible hair and hard protection of skin/scalp/ears/accessories/other people/ambiguous contacts')
    scale = value['texture_scale']
    if type(scale) not in (int, float) or not 0 < scale <= 1 or not math.isfinite(scale):
        raise ValueError('Observed hair texture scale must be a finite positive source-short-side fraction')
    result = {**deepcopy(value), 'texture_scale': float(scale),
              'target_recipe': _manual(value['target_recipe']), 'context_recipe': _manual(value['context_recipe']),
              'protect_recipe': _manual(value['protect_recipe'], protect=True)}
    if sum(len(obj['points']) for key in ('target_recipe', 'context_recipe', 'protect_recipe')
           for obj in result[key]['objects']) > 4096:
        raise ValueError('Hair smoothing strokes exceed the combined point budget')
    if source is not None:
        source = H.source(source)
        if source['width'] * source['height'] > MAX_PIXELS:
            raise ValueError('Hair smoothing supports authentic original sources up to 32 MP only')
        if not MIN_TEXTURE_SCALE_PX <= scale * min(source['width'], source['height']) <= MAX_TEXTURE_SCALE_PX:
            raise ValueError('Observed texture scale must be 1..8 native source pixels; never silently clamped')
    return result


def check_source_proof(value, source):
    required = {'version', 'source', 'source_proof', 'input_sha256', 'repair_sha256', 'encoding',
                'source_bits', 'orientation', 'stage'}
    if (type(value) is not dict or set(value) != required or type(value['version']) is not int or value['version'] != 1
            or value['source'] != source or value['encoding'] != 'encoded-srgb-f32-v1'
            or value['source_bits'] not in (8, 16) or type(value['source_bits']) is not int
            or value['orientation'] != 'exif_normalized_once'
            or value['stage'] not in ('immutable-source', 'verified-repair-base')):
        raise ValueError('Hair smoothing needs authenticated full native original/repair pixels, not a proxy')
    from .creative_derived_source import check_row_proof
    proof = check_row_proof(value['source_proof'])
    if proof['creative_source'] is not None or proof['asset_sha256'] != source['sha256'] or proof['original_sha256'] != source['sha256']:
        raise ValueError('Hair smoothing does not admit derived composites; original pixels are never relabelled derived')
    P.digest(value['input_sha256']); P.digest(value['repair_sha256'])
    return deepcopy(value)


def _manual_owner(record):
    record = H.check(record)
    if any(obj['enabled'] and obj['kind'] == 'prompted' for obj in record['support']['objects']):
        raise ValueError('Hair smoothing requires immutable manual hair ownership; prompted intent would need model replay and is not admitted')
    return record


def retained_faces_digest(state, asset, hair_assets):
    """All retained source faces, including disabled/manual/unresolved, not detections.

    Hair review keys represent ownership. Colour/recovery-only content changes do
    not invalidate that identity; smoothing's own pointer cannot self-invalidate.
    """
    state = P.check(state); P.digest(asset)
    rows = []
    for face in sorted(state['faces'].values(), key=lambda row: row['face_instance_id']):
        if face['asset_sha256'] != asset:
            continue
        owner = None
        if H.KIND in face['local_assets']:
            hair = H.resolve(state, hair_assets, P.face_ref(face))
            owner = {'review_key': hair['review']['review_key'], 'source': hair['source'],
                     'semantic_evidence_sha256': hair['semantic_evidence_sha256']}
        rows.append({key: deepcopy(face[key]) for key in ('face_instance_id', 'asset_sha256',
            'analysis_revision', 'box', 'evidence', 'manual', 'enabled', 'labels')} | {'hair_ownership': owner})
    return content_digest(rows)


def check_record(record):
    if (type(record) is not dict or set(record) != {'version', 'face_ref', 'source', 'row'}
            or type(record['version']) is not int or record['version'] != 1):
        raise ValueError('Invalid hair smoothing support envelope')
    ref = P.check_ref(record['face_ref']); source = H.source(record['source']); row = record['row']
    fields = {'target', 'family', 'operation_id', 'hair_colour_asset_sha256', 'ownership_review_key',
              'semantic_model_sha256', 'semantic_evidence_sha256', 'retained_faces_sha256',
              'source_packet_proof', 'review', 'review_key'}
    if (ref['asset_sha256'] != source['sha256'] or type(row) is not dict or set(row) != fields
            or row['target'] != KIND or row['family'] != FAMILY or row['operation_id'] != S.OP
            or row['semantic_model_sha256'] != H.MODEL_SHA256):
        raise ValueError('Hair smoothing support belongs to another family, source or model')
    for key in ('hair_colour_asset_sha256', 'ownership_review_key', 'semantic_model_sha256',
                'semantic_evidence_sha256', 'retained_faces_sha256', 'review_key'):
        P.digest(row[key])
    check_review(row['review'], source=source); check_source_proof(row['source_packet_proof'], source)
    content = {**record, 'row': {k: v for k, v in row.items() if k != 'review_key'}}
    if content_digest(content) != row['review_key']:
        raise ValueError('Hair smoothing consent is not bound to these exact source, ownership and independent strokes')
    return deepcopy(record)


def retained_support(record, hair_assets, evidence_bank=None):
    """Historical immutable bytes only; never bind a detached fragment to live census."""
    record = check_record(record); row = record['row']
    retained = hair_assets.get(row['hair_colour_asset_sha256'])
    if retained is None:
        raise ValueError('Exact retained hair ownership asset is missing')
    retained = _manual_owner(retained)
    if (H.digest(retained) != row['hair_colour_asset_sha256'] or retained['face_ref'] != record['face_ref']
            or retained['source'] != record['source'] or retained['review']['review_key'] != row['ownership_review_key']
            or retained['semantic_model_sha256'] != row['semantic_model_sha256']
            or retained['semantic_evidence_sha256'] != row['semantic_evidence_sha256']):
        raise ValueError('Historical hair smoothing consent differs from its exact retained ownership/semantic asset')
    if evidence_bank is not None:
        saved = evidence_bank.get(row['semantic_evidence_sha256'])
        if saved is None:
            raise ValueError('Hair smoothing history lost its actual retained semantic evidence')
        evidence = E.decode(saved)
        if (E.identity(evidence) != row['semantic_evidence_sha256'] or evidence['source'] != record['source']
                or evidence['model_sha256'] != row['semantic_model_sha256']):
            raise ValueError('Hair smoothing history semantic evidence belongs to another source or model')
    return retained


def current_support(state, record, hair_assets):
    retained = retained_support(record, hair_assets); row = record['row']
    current = H.resolve(state, hair_assets, record['face_ref'])
    if current is None:
        raise ValueError('Hair smoothing needs this person\'s independently reviewed hair ownership')
    _manual_owner(current)
    if current['review']['review_key'] != row['ownership_review_key']:
        raise ValueError('Hair smoothing ownership changed; colour-only edits cannot rebind different support')
    return retained


def resolve(state, assets, ref, hair_assets):
    state = P.check(state); ref = P.check_ref(ref); face = H.verify_face(state, ref)
    descriptor = face['local_assets'].get(KIND)
    if descriptor is None:
        return None
    record = assets.get(descriptor['content_sha256'])
    if record is None:
        raise ValueError('Retained hair smoothing support is missing; it is not silently skipped')
    record = check_record(record)
    if (record['face_ref'] != ref or content_digest(record) != descriptor['content_sha256']
            or descriptor != {'owner': ref, 'kind': KIND, 'content_sha256': content_digest(record)}):
        raise ValueError('Hair smoothing support is stale or owned by another FaceRef')
    current_support(state, record, hair_assets)
    if retained_faces_digest(state, ref['asset_sha256'], hair_assets) != record['row']['retained_faces_sha256']:
        raise ValueError('Retained source people/claims changed, including disabled or unresolved faces; review again')
    return record, descriptor['content_sha256']


def retain(state, assets, ref, hair_assets, review, source_proof, all_faces_sha256):
    state = P.check(state); ref = P.check_ref(ref); hair = H.resolve(state, hair_assets, ref)
    if hair is None:
        raise ValueError('Review this exact person\'s visible hair ownership before directional smoothing')
    hair = _manual_owner(hair); source = hair['source']; review = check_review(review, source=source)
    source_proof = check_source_proof(source_proof, source); P.digest(all_faces_sha256)
    if all_faces_sha256 != retained_faces_digest(state, ref['asset_sha256'], hair_assets):
        raise ValueError('Hair smoothing retained-face ownership proof changed')
    row = {'target': KIND, 'family': FAMILY, 'operation_id': S.OP,
           'hair_colour_asset_sha256': H.digest(hair), 'ownership_review_key': hair['review']['review_key'],
           'semantic_model_sha256': hair['semantic_model_sha256'],
           'semantic_evidence_sha256': hair['semantic_evidence_sha256'],
           'retained_faces_sha256': all_faces_sha256, 'source_packet_proof': source_proof, 'review': review}
    record = {'version': 1, 'face_ref': ref, 'source': source, 'row': row}
    row['review_key'] = content_digest(record); record = check_record(record); key = content_digest(record)
    from .people_support_assets import check_store
    bank = check_store(assets)
    if key in bank and bank[key] != record:
        raise ValueError('Hair smoothing immutable support content collision')
    bank[key] = record; check_store(bank)
    face = state['faces'][ref['face_instance_id']]
    descriptor = {'owner': ref, 'kind': KIND, 'content_sha256': key}
    if face['local_assets'].get(KIND) != descriptor:
        face['local_assets'][KIND] = descriptor; state['revision'] += 1
    return P.check(state), bank


def detach(state, ref):
    state = P.check(state); ref = P.check_ref(ref); face = state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref:
        raise ValueError('Hair smoothing detach belongs to another exact face')
    if KIND in face['local_assets']:
        del face['local_assets'][KIND]; state['revision'] += 1
    return P.check(state)


def _owners(state, source, hair_assets):
    result = []
    for face in state['faces'].values():
        if face['asset_sha256'] == source['sha256'] and H.KIND in face['local_assets']:
            # A disabled claim cannot disappear; unresolved retained claims fail
            # exact ownership verification rather than being assigned by order.
            record = _manual_owner(H.resolve(state, hair_assets, P.face_ref(face)))
            if record['source'] != source:
                raise ValueError('Retained hair claims disagree about original source dimensions')
            result.append((P.face_ref(face), record))
    return result


def raster_plan(state, assets, ref, hair_assets, shape):
    resolved = resolve(state, assets, ref, hair_assets)
    if resolved is None:
        raise ValueError('Active hair smoothing requires its own independent visible-hair review')
    record, key = resolved; source = record['source']; shape = tuple(shape)
    if shape != (source['height'], source['width']) or shape[0] * shape[1] > MAX_PIXELS:
        raise ValueError('Hair smoothing support needs the exact full original source, at most 32 MP')
    owners = _owners(state, source, hair_assets)
    recipes = [owner['support'] for _, owner in owners] + [record['row']['review'][k]
                for k in ('target_recipe', 'context_recipe', 'protect_recipe')]
    work = sum(M.validate_budget(value, shape)['work'] for value in recipes)
    if work > M.MAX_WORK or len(owners) * shape[0] * shape[1] > 128_000_000:
        raise ValueError('All retained hair ownership and smoothing strokes exceed aggregate raster work budget')
    return {'required_work_bytes': 64 * shape[0] * shape[1] + 64 * 1024**2,
            'retained_bytes': 13 * shape[0] * shape[1], 'work': work, 'support_sha256': key}


def _plane_digest(value):
    digest = hashlib.sha256()
    for y in range(0, value.shape[0], 64):
        digest.update(np.ascontiguousarray(value[y:y+64]).tobytes())
    return digest.hexdigest()


def raster(state, assets, ref, hair_assets, hair_evidence, shape, *, byte_budget, cancelled=None):
    admission = raster_plan(state, assets, ref, hair_assets, shape)
    if type(byte_budget) is not int or byte_budget < admission['required_work_bytes']:
        raise MemoryError('Hair smoothing ownership/context raster exceeds admitted memory')
    def poll():
        if cancelled is not None and cancelled():
            raise InterruptedError('Hair smoothing ownership preparation cancelled')
    poll(); record, key = resolve(state, assets, ref, hair_assets); source = record['source']
    hair = A.at_dimensions(hair_evidence, source, tuple(shape)); evidence_sha = E.identity(hair_evidence)
    if evidence_sha != record['row']['semantic_evidence_sha256']:
        raise ValueError('Hair smoothing uses different actual measured class evidence')
    occupied = np.zeros(shape, np.bool_); own = None; owner_proofs = []
    for other_ref, other in _owners(state, source, hair_assets):
        poll()
        if other['semantic_evidence_sha256'] != evidence_sha:
            raise ValueError('Retained hair claims disagree about actual semantic evidence')
        weight = np.ascontiguousarray(M.raster(other['support'], shape), dtype=np.float32) / 255.
        weight *= hair; visible = weight > 0
        if np.any(occupied & visible):
            raise ValueError('Retained hair ownership overlaps, including disabled people; no face-order settlement')
        occupied |= visible
        owner_proofs.append({'face_ref': other_ref, 'ownership_review_key': other['review']['review_key'],
                             'weight_sha256': _plane_digest(weight)})
        if other_ref == ref:
            own = weight
    if own is None:
        raise ValueError('No independently owned visible hair belongs to this exact face')
    review = record['row']['review']; poll()
    context = np.minimum(own, np.ascontiguousarray(M.raster(review['context_recipe'], shape), dtype=np.float32) / 255.)
    target = np.minimum(np.minimum(own, context), np.ascontiguousarray(M.raster(review['target_recipe'], shape), dtype=np.float32) / 255.)
    hard = np.ascontiguousarray(M.raster(review['protect_recipe'], shape) > 0, dtype=np.bool_)
    target[hard] = 0; context[hard] = 0
    if not np.any(target > 0) or not np.any(context > 0):
        raise ValueError('Reviewed visible target/context has no actual owned hair evidence outside hard protection')
    facts = {'support_sha256': key, 'hair_colour_asset_sha256': record['row']['hair_colour_asset_sha256'],
             'ownership_review_key': record['row']['ownership_review_key'],
             'semantic_evidence_sha256': evidence_sha, 'retained_faces_sha256': record['row']['retained_faces_sha256'],
             'conflicting_owner_proof_sha256': content_digest(sorted(owner_proofs, key=lambda r: r['face_ref']['face_instance_id'])),
             'target_sha256': _plane_digest(target), 'context_sha256': _plane_digest(context), 'hard_protect_sha256': _plane_digest(hard),
             'target_pixels': int(np.count_nonzero(target)), 'context_pixels': int(np.count_nonzero(context)),
             'hard_protected_pixels': int(np.count_nonzero(hard)), 'semantic_kind': 'confidence-gated-editing-weight-not-probability-or-matting',
             'occlusion_classification': 'none-explicit-independent-human-hard-protection-required'}
    poll()
    return target, context, hard, facts


def measurement_key(record, facts, source_proof, algorithm_version):
    check_record(record); check_source_proof(source_proof, record['source'])
    if source_proof != record['row']['source_packet_proof']:
        raise ValueError('Original/repair pixels changed since hair smoothing review')
    return content_digest({'operation_id': S.OP, 'support': content_digest(record), 'facts': facts,
                           'source_proof': source_proof, 'algorithm_version': algorithm_version})
