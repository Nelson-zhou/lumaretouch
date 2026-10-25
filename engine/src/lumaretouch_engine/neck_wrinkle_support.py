# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent neck consent over the canonical people/body support owner.

Only manually reviewed visible neck skin and its context are positive support.
Face/pose evidence identifies and vetoes; it never creates a neck boundary.
Protection is a separate hard union, never an opacity decrease in positive paint.
No demographic, collarbone, neck-shape or facial-wrinkle consent is borrowed.
AUTHORED / UNRUN; no segmentation or photo-quality acceptance is claimed.
"""
from copy import deepcopy
import hashlib
import math
import numpy as np

from . import neck_wrinkle_state as STATE
from . import local_mask_recipe as M
from . import people_state as P
from . import skin_colour_body_support as OWNER
from .people_support_assets import content_digest

FAMILY = 'neck_wrinkle'
KIND = 'neck_wrinkle_visibility'
MIN_LINE_HALF_WIDTH_PX = 1.4
MAX_LINE_HALF_WIDTH_PX = 12.0
_OPTIONS = {'family': FAMILY, 'operation_id': STATE.OP}
_RASTER_FIXED_BYTES = 64 * 1024**2
_RASTER_BYTES_PER_PIXEL = 40


def _manual(value, *, protection):
    recipe = M.check_stack(value)
    if any(obj['kind'] != 'brush' or obj['operation'] not in ('add', 'subtract')
           for obj in recipe['objects']):
        raise ValueError('Neck review accepts only source-normalized manual brush vectors')
    if protection:
        if any(obj['operation'] != 'add' or not obj['enabled'] or obj['opacity'] != 1
               or obj['feather'] != 0 for obj in recipe['objects']):
            raise ValueError('Neck protections must be enabled opaque unfeathered add brushes; delete a stroke to revise it')
    elif not any(obj['enabled'] and obj['operation'] == 'add' and obj['opacity'] > 0
                 for obj in recipe['objects']):
        raise ValueError('Draw actual visible neck skin and admissible nearby context')
    return recipe


def check_neck_review(value, *, source=None):
    """Validate just the mandatory independent ``review.neck`` extension."""
    keys = {'version', 'domain', 'line_half_width', 'protect_recipe',
            'protections_reviewed', 'visible_neck_skin_reviewed'}
    if (type(value) is not dict or set(value) != keys
            or type(value['version']) is not int or value['version'] != 1
            or value['domain'] != 'source-normalized'):
        raise ValueError('Neck review needs its exact independent source-normalized schema')
    if value['protections_reviewed'] is not True or value['visible_neck_skin_reviewed'] is not True:
        raise ValueError('Independently review visible neck skin and all structural/occluder protections')
    width = value['line_half_width']
    if type(width) not in (int, float) or not 0 < width <= 1 or not math.isfinite(width):
        raise ValueError('Observed fine-line half-width must be a positive finite source-short-side fraction')
    protection = _manual(value['protect_recipe'], protection=True)
    if source is not None:
        if (type(source) is not dict or any(type(source.get(k)) is not int
                or not 2 <= source[k] <= 65536 for k in ('width', 'height'))):
            raise ValueError('Neck scale requires exact canonical source dimensions')
        pixels = width * min(source['width'], source['height'])
        if not MIN_LINE_HALF_WIDTH_PX <= pixels <= MAX_LINE_HALF_WIDTH_PX:
            raise ValueError('Observed neck fine-line half-width must be 1.4..12 canonical pixels; no clamp')
    return {**deepcopy(value), 'line_half_width': float(width), 'protect_recipe': protection}


def check_review(value, *, source=None):
    """Exact transport schema; retains the existing BodyRef and association owner."""
    keys = {'body_ref', 'points_sha256', 'recipe', 'visible', 'unoccluded',
            'ownership_confirmed', 'neck'}
    if type(value) is not dict or set(value) != keys:
        raise ValueError('Neck review requires its own body, region, protection and observed scale')
    from . import body_pose_evidence as B
    B.ref(value['body_ref']); B.digest(value['points_sha256'])
    if any(value[key] is not True for key in ('visible', 'unoccluded', 'ownership_confirmed')):
        raise ValueError('Confirm actual visible unoccluded neck skin owned by this exact person/body')
    return {**deepcopy(value), 'recipe': _manual(value['recipe'], protection=False),
            'neck': check_neck_review(value['neck'], source=source)}


def resolve(state, assets, face_ref, body_bank, analysis):
    return OWNER.resolve(state, assets, face_ref, body_bank, analysis, **_OPTIONS)


def retain(state, assets, face_ref, body_bank, analysis, review):
    return OWNER.retain(state, assets, face_ref, body_bank, analysis,
                        check_review(review), **_OPTIONS)


def detach(state, face_ref):
    # The existing owner deliberately permits stale-source cleanup.
    return OWNER.detach(state, face_ref, **_OPTIONS)


def _shape(shape):
    if (type(shape) not in (tuple, list) or len(shape) != 2
            or any(type(n) is not int or not 2 <= n <= 65536 for n in shape)):
        raise ValueError('Neck support requires the exact full canonical source extent')
    return tuple(shape)


def raster_plan(state, assets, face_ref, body_bank, analysis, shape):
    """Admission before allocation, including every competing retained owner."""
    shape = _shape(shape)
    resolved = resolve(state, assets, face_ref, body_bank, analysis)
    if resolved is None:
        raise ValueError('Active neck fine-line correction needs its own reviewed body-skin support')
    record, key = resolved
    if shape != (record['source']['height'], record['source']['width']):
        raise ValueError('Neck support cannot be measured on a proxy or resized source')
    review = check_review(record['row']['review'], source=record['source'])
    recipes = [review['recipe'], review['neck']['protect_recipe']]
    checked = P.check(state)
    from .skin_reference_body_support import _attached as reference_attached
    for face in checked['faces'].values():
        ref = P.face_ref(face)
        if ref == record['face_ref'] or ref['asset_sha256'] != record['source']['sha256']:
            continue
        for family in OWNER.FAMILIES:
            other = OWNER._attached(checked, assets, ref, family=family)
            if other is not None:
                recipes.append(other[0]['row']['review']['recipe'])
        other = reference_attached(checked, assets, ref)
        if other is not None:
            recipes.append(other[0]['row']['review']['recipe'])
    work = sum(M.validate_budget(recipe, shape)['work'] for recipe in recipes)
    if work > M.MAX_WORK:
        raise ValueError('All neck, protection and competing body rasters exceed aggregate work budget')
    return {'required_work_bytes': shape[0]*shape[1]*_RASTER_BYTES_PER_PIXEL + _RASTER_FIXED_BYTES,
            'retained_bytes': shape[0]*shape[1]*5, 'work': work, 'support_sha256': key}


def _plane_digest(value):
    digest = hashlib.sha256()
    # Bounded row transport; no giant hash-only contiguous plane copy.
    for start in range(0, value.shape[0], 64):
        digest.update(np.ascontiguousarray(value[start:start+64]).tobytes(order='C'))
    return digest.hexdigest()


def raster(state, assets, face_ref, body_bank, analysis, shape, *, byte_budget, cancelled=None):
    """Return (readonly admitted f32, readonly hard bool, facts) at full source.

    Existing canonical owner checks every retained face and every other person's
    reviewed body region, even when disabled. A competing positive region refuses
    rather than being stolen by sort order. Pose never supplies positive pixels.
    """
    shape = _shape(shape)
    plan = raster_plan(state, assets, face_ref, body_bank, analysis, shape)
    if type(byte_budget) is not int or byte_budget < plan['required_work_bytes']:
        raise MemoryError('Neck full-source support exceeds memory budget before raster allocation')
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be callable')
    def poll():
        if cancelled is not None and cancelled():
            raise InterruptedError('Neck support cancelled; no partial field published')
    poll()
    record, key = resolve(state, assets, face_ref, body_bank, analysis)
    excluded = analysis.get('excluded')
    if (type(excluded) is not np.ndarray or excluded.dtype != np.float32
            or excluded.shape != shape or not np.isfinite(excluded).all()
            or np.any((excluded < 0) | (excluded > 1))):
        raise ValueError('Neck review requires the actual known-occluder plane at canonical extent')
    coverage, facts = OWNER.raster(state, assets, face_ref, body_bank, analysis, shape,
                                  byte_budget=byte_budget, **_OPTIONS)
    if coverage is None or not facts.get('enabled') or facts.get('support_sha256') != key:
        raise ValueError('Neck support changed during canonical coverage preparation')
    poll()
    protection = M.raster(check_neck_review(record['row']['review']['neck'],
                            source=record['source'])['protect_recipe'], shape)
    if type(protection) is not np.ndarray or protection.dtype != np.uint8 or protection.shape != shape:
        raise ValueError('Neck protection must be the existing Rust source-grid brush raster')
    # Any painted protection or known exclusion is a hard veto. The independent
    # mask is applied last and cannot be undone by a positive region add stroke.
    # Unpainted/background/face-box areas already have zero admission. Do not
    # label the entire unpainted photograph as a manually reviewed protection
    # in the comparison overlay; both zero admission and hard veto deny sampling.
    hard = (protection != 0) | (excluded > 0)
    admitted = np.array(coverage, dtype=np.float32, order='C', copy=True)
    admitted[hard] = 0
    if not np.any(admitted > 0):
        raise ValueError('No visible owned neck skin remains outside hard protections')
    poll()
    admitted.setflags(write=False); hard.setflags(write=False)
    facts = {**facts, 'hard_protected_pixels': int(np.count_nonzero(hard)),
             'manual_protected_pixels': int(np.count_nonzero(protection)),
             'support_pixels': int(np.count_nonzero(admitted > 0)),
             'body_skin_plane_sha256': _plane_digest(analysis['body_skin']),
             'known_occluder_plane_sha256': _plane_digest(excluded),
             'admitted_plane_sha256': _plane_digest(admitted),
             'hard_protect_plane_sha256': _plane_digest(hard),
             'review_sha256': content_digest(record['row']['review']),
             'protection_policy': 'independent-add-only-hard-veto-after-positive-paint',
             'scope': 'manual-visible-neck-skin-and-context-not-pose-inference',
             'runtime_quality_accepted': False}
    poll()
    return admitted, hard, facts


def measurement_key(record, support_facts, source_proof, algorithm_version):
    """Amount deliberately excluded; every source/repair/owner/scale input pinned."""
    if type(algorithm_version) is not str or not algorithm_version:
        raise ValueError('Neck measurement requires the exact native algorithm version')
    return content_digest({'operation_id': STATE.OP, 'record': record,
        'source_proof': source_proof, 'body_skin_plane_sha256': support_facts['body_skin_plane_sha256'],
        'known_occluder_plane_sha256': support_facts['known_occluder_plane_sha256'],
        'admitted_plane_sha256': support_facts['admitted_plane_sha256'],
        'hard_protect_plane_sha256': support_facts['hard_protect_plane_sha256'],
        'algorithm_version': algorithm_version})
