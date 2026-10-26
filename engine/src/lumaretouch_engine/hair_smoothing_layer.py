# SPDX-License-Identifier: GPL-3.0-or-later
"""One original-resolution directional measurement, frozen before composition.

Only an authenticated original/repair source resolver can produce measurement
pixels. Display grids receive conservative projections of solved canonical fields;
export/full candidate grids never estimate texture from a proxy. AUTHORED / UNRUN.
"""
from copy import deepcopy
from dataclasses import dataclass
import math
import numpy as np
from . import hair_smoothing_state as S, hair_smoothing_support as C
from . import people_state as P


@dataclass(frozen=True)
class HairSmoothingReviewEvidence:
    admitted_weight: object
    hard_protect: object
    eligible_mask: object
    window_yxhw: tuple
    source_shape_hw: tuple
    measurement_key: str
    source_proof: dict
    facts: dict


def _poll(cancelled):
    if cancelled is not None and cancelled():
        raise InterruptedError('Hair smoothing cancelled before publication')


def plan(ref, analysis, recipe, *, people_state, assets, hair_assets, render_shape=None):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return {'active': False, 'required_work_bytes': 0, 'retained_bytes': 0}
    ref = P.check_ref(ref)
    if type(analysis) is not dict or analysis.get('face_ref') != ref:
        raise ValueError('Hair smoothing requires the exact retained original face analysis')
    resolved = C.resolve(people_state, assets, ref, hair_assets)
    if resolved is None:
        raise ValueError('Hair smoothing has no independently reviewed owned visible target/context')
    record, key = resolved; source = record['source']; shape = (source['height'], source['width'])
    application = shape if render_shape is None else tuple(render_shape)
    from .body_pose_evidence import whole_source_shape, ORIENTATION
    whole_source_shape({**source, 'orientation': ORIENTATION}, application)
    review = C.check_review(record['row']['review'], source=source)
    scale = review['texture_scale'] * min(shape)
    raster = C.raster_plan(people_state, assets, ref, hair_assets, shape)
    from .hair_smoothing_measure import plan as native_plan
    numerical = native_plan(shape, scale)
    for name in ('required_work_bytes', 'retained_bytes'):
        if type(numerical.get(name)) is not int or numerical[name] < 0:
            raise ValueError('Hair smoothing native plan omitted checked resident costs')
    projection = 8 * shape[0] * shape[1] + 24 * application[0] * application[1] + 8 * 1024**2 if shape != application else 0
    # Conservative additive admission intentionally keeps caller-owned source and
    # raster buffers charged even if the numerical ABI also accounts for them.
    return {'active': True, 'source': deepcopy(source), 'source_shape_hw': shape,
            'application_shape_hw': application, 'texture_scale_px': scale,
            'support_sha256': key, 'raster': raster, 'native': numerical,
            'required_work_bytes': raster['required_work_bytes'] + numerical['required_work_bytes'] + projection,
            'retained_bytes': numerical['retained_bytes'] + (5 * application[0] * application[1] if projection else 0)}


def _project(effect, eligible, shape, cancelled):
    """Only solved scalar fields; every interpolation tap must remain eligible."""
    import cv2
    from .people_effects import LocalEffect
    canonical = tuple(effect.facts['source_shape_hw'])
    if shape == canonical:
        return effect
    _poll(cancelled)
    gain = cv2.resize(effect.log_gain[..., 0], (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
    # A strictly positive blocked mixture vetoes the entire projected sample.
    blocked = cv2.resize((~eligible).astype(np.float32), (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
    gain[blocked > 0] = 0
    if (gain.dtype != np.float32 or gain.shape != shape or not np.isfinite(gain).all()
            or np.any(np.abs(gain.astype(np.float64)) > math.log(1.10))):
        raise ValueError('Hair smoothing projection lost its bounded canonical scalar field')
    field = np.frombuffer(gain.tobytes(), dtype=np.float32).reshape((*shape, 1))
    projected_eligibility = np.frombuffer((blocked == 0).tobytes(), dtype=np.bool_).reshape(shape)
    facts = {**deepcopy(effect.facts), 'application_shape_hw': list(shape),
             'render_dimensions': [shape[1], shape[0]], 'review_authority': False,
             'display_projection': {'version': 1, 'kind': 'canonical-field-preview-only',
                 'mapping': 'source-pixel-edge-centres-cv2-linear', 'canonical_shape_hw': list(canonical),
                 'application_shape_hw': list(shape), 'authorizes_review': False, 'authorizes_export': False}}
    _poll(cancelled)
    return LocalEffect(effect.face_ref, S.STAGE, (0, 0, *shape), log_gain=field,
                       amounts=dict(effect.amounts), facts=facts, eligibility=projected_eligibility)


def _prepare(ref, analysis, recipe, *, people_state, assets, hair_assets, hair_evidence,
             full_source, byte_budget, render_shape=None, cancelled=None, include_review=False):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return ([], None) if include_review else []
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be callable')
    _poll(cancelled)
    admission = plan(ref, analysis, recipe, people_state=people_state, assets=assets,
                     hair_assets=hair_assets, render_shape=render_shape)
    shape = admission['source_shape_hw']
    if include_review and admission['application_shape_hw'] != shape:
        raise ValueError('A display projection cannot authorize hair smoothing review')
    if type(byte_budget) is not int or byte_budget <= admission['required_work_bytes']:
        raise MemoryError('Full original hair smoothing support/detector exceeds budget before allocation')
    from .hair_smoothing_source import resolve as resolve_source
    packet = resolve_source(full_source, face_ref=ref, source=admission['source'], analysis=analysis,
        byte_budget=byte_budget-admission['required_work_bytes'], cancelled=cancelled)
    source = packet.rgb
    if (type(source) is not np.ndarray or source.dtype != np.float32 or source.shape != (*shape, 3)
            or not source.flags.c_contiguous or source.flags.writeable or not np.isfinite(source).all()
            or np.any((source < 0) | (source > 1))):
        raise ValueError('Hair smoothing requires immutable authentic native working-sRGB float32')
    if type(packet.resident_bytes) is not int or packet.resident_bytes < source.nbytes:
        raise ValueError('Hair smoothing source did not account for immutable original/repair residents')
    if packet.resident_bytes + admission['required_work_bytes'] > byte_budget:
        raise MemoryError('Source and all directional preparation exceed aggregate memory')
    record, key = C.resolve(people_state, assets, ref, hair_assets)
    if key != admission['support_sha256'] or record['row']['source_packet_proof'] != packet.proof:
        raise ValueError('Hair smoothing source/repair/ownership changed after the independent review')
    target, context, hard, support_facts = C.raster(people_state, assets, ref, hair_assets,
        hair_evidence, shape, byte_budget=admission['raster']['required_work_bytes'], cancelled=cancelled)
    from .hair_smoothing_measure import measure
    measured = measure(source, target, context, hard, texture_scale_px=admission['texture_scale_px'],
        byte_budget=admission['native']['required_work_bytes'], cancelled=cancelled)
    field = measured.log_gain; eligible = measured.eligible_mask; _poll(cancelled)
    if (type(field) is not np.ndarray or field.dtype != np.float32 or field.shape != shape
            or field.flags.writeable or not field.flags.c_contiguous or not np.isfinite(field).all()
            or np.any(np.abs(field.astype(np.float64)) > math.log(1.10))
            or type(eligible) is not np.ndarray or eligible.dtype != np.bool_ or eligible.shape != shape
            or eligible.flags.writeable or not eligible.flags.c_contiguous
            or tuple(measured.source_shape_hw) != shape
            or measured.algorithm_version != admission['native']['algorithm_version']):
        raise ValueError('Hair smoothing native measurement lost exact immutable field/eligibility provenance')
    changed = field != 0
    if np.any(changed & ~eligible) or np.any(eligible & ((target <= 0) | (context <= 0) | hard)):
        raise ValueError('Hair smoothing numerical field escaped owned target/context or hard protection')
    native_facts = dict(measured.facts)
    if native_facts.get('runtime_quality_accepted') is not False:
        raise ValueError('Hair smoothing numerical facts must preserve unaccepted runtime status')
    for name in ('supported_pixels', 'context_rejected_pixels', 'directional_pixels', 'changed_pixels'):
        if type(native_facts.get(name)) is not int or not 0 <= native_facts[name] <= shape[0] * shape[1]:
            raise ValueError('Hair smoothing numerical support/direction/change counts are invalid')
    if (native_facts['supported_pixels'] != int(np.count_nonzero(eligible))
            or native_facts['changed_pixels'] != int(np.count_nonzero(changed))
            or not native_facts['changed_pixels'] <= native_facts['directional_pixels'] <= native_facts['supported_pixels']):
        raise ValueError('Hair smoothing must distinguish context admission, directional signal and proposed change')
    if not native_facts['supported_pixels']:
        raise ValueError('No complete owned directional measurement footprint; do not fabricate context')
    if not native_facts['changed_pixels'] and not native_facts.get('no_signal_reason'):
        raise ValueError('Valid zero hair smoothing signal requires a truthful explicit no-signal reason')
    key = C.measurement_key(record, support_facts, packet.proof, measured.algorithm_version)
    facts = {'operation_id': S.OP, 'control_id': S.CONTROL_ID, 'face_ref': deepcopy(ref),
             'source_proof': deepcopy(packet.proof), 'source_dimensions': [shape[1], shape[0]],
             'source_shape_hw': list(shape), 'application_shape_hw': list(shape),
             'render_dimensions': [shape[1], shape[0]], 'source_window': [0, 0, *shape],
             'texture_scale_px': admission['texture_scale_px'], 'algorithm_version': measured.algorithm_version,
             'measurement_key': key, 'support': support_facts, 'native_report': native_facts,
             'changed_pixels': native_facts['changed_pixels'], 'no_signal_reason': native_facts.get('no_signal_reason'),
             'display_projection': None, 'review_authority': True, 'runtime_quality_accepted': False,
             'scope': 'visible-owned-resolved-hair-texture-only',
             'application': 'current-stage-common-linear-RGB-gain-common-SDR-headroom',
             'limitations': ['not-hidden-hair-reconstruction', 'not-flyaway-removal-or-geometric-straightening',
                 'no-physical-highlight-or-occlusion-classifier', 'manual-only-owned-hair-first-slice',
                 'semantic-editing-weight-not-probability-matting-or-person-census', 'no-cross-image-cohort-or-donor-mask']}
    from .people_effects import LocalEffect
    field = field[..., None]; field.setflags(write=False)
    effect = LocalEffect(ref, S.STAGE, (0, 0, *shape), log_gain=field,
                         amounts={'amount': recipe['amount']}, facts=facts, eligibility=eligible)
    if include_review:
        evidence = HairSmoothingReviewEvidence(target, hard, eligible, (0, 0, *shape), shape,
                                                key, deepcopy(packet.proof), deepcopy(facts))
        return [effect], evidence
    return [_project(effect, eligible, admission['application_shape_hw'], cancelled)]


def prepare(ref, analysis, recipe, *, people_state, assets, hair_assets, hair_evidence,
            full_source, byte_budget, render_shape=None, cancelled=None):
    return _prepare(ref, analysis, recipe, people_state=people_state, assets=assets, hair_assets=hair_assets,
        hair_evidence=hair_evidence, full_source=full_source, byte_budget=byte_budget,
        render_shape=render_shape, cancelled=cancelled)


def prepare_review(ref, analysis, recipe, *, people_state, assets, hair_assets, hair_evidence,
                   full_source, byte_budget, cancelled=None):
    return _prepare(ref, analysis, recipe, people_state=people_state, assets=assets, hair_assets=hair_assets,
        hair_evidence=hair_evidence, full_source=full_source, byte_budget=byte_budget,
        cancelled=cancelled, include_review=True)
