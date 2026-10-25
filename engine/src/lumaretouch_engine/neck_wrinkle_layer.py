# SPDX-License-Identifier: GPL-3.0-or-later
"""Frozen full-source neck measurement, independent of amount/current pixels.

The parent-owned source resolver is the ONLY authority for canonical original or
returned creative pixels and exact repair replay. Ordinary pipeline proxies,
arrays plus caller hashes and path-only provenance cannot enter this adapter.
No numerical fallback, cached raster recipe or inferred neck contour. UNRUN.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from copy import deepcopy
import numpy as np

from . import neck_wrinkle_state as S, neck_wrinkle_support as C
from . import people_state as P


@dataclass(frozen=True)
class NeckReviewEvidence:
    """Private disposable full-grid diagnostics; never persisted or portable."""
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
        raise InterruptedError('Neck fine-line preparation cancelled; no partial field published')


def _application_shape(source, render_shape):
    canonical = (source['height'], source['width'])
    if render_shape is None:
        return canonical
    from .body_pose_evidence import whole_source_shape, ORIENTATION
    whole_source_shape({**source, 'orientation': ORIENTATION}, render_shape)
    return tuple(render_shape)


def plan(ref, analysis, recipe, *, people_state, body_assets, body_bank, render_shape=None):
    """Pure admission for the parent to aggregate BEFORE any source/ROI allocation.

    Conservatively plans the full canonical grid, not face bounds. The numerical
    adapter may subsequently use a smaller genuine reviewed-support ROI, never a
    lower-resolution proxy. Parent charges all resident other operators as well.
    """
    recipe = S.check(recipe)
    if not S.active(recipe):
        return {'required_work_bytes': 0, 'retained_bytes': 0, 'active': False}
    ref = P.check_ref(ref)
    if type(analysis) is not dict or analysis.get('face_ref') != ref:
        raise ValueError('Neck fine-line measurement requires exact retained source/face analysis')
    resolved = C.resolve(people_state, body_assets, ref, body_bank, analysis)
    if resolved is None:
        raise ValueError('Active neck fine-line correction requires its own reviewed body-skin support')
    record, key = resolved
    neck = C.check_neck_review(record['row']['review']['neck'], source=record['source'])
    shape = (record['source']['height'], record['source']['width'])
    application_shape = _application_shape(record['source'], render_shape)
    scale = neck['line_half_width'] * min(shape)
    raster = C.raster_plan(people_state, body_assets, ref, body_bank, analysis, shape)
    from . import neck_wrinkle_measure as N
    native = N.plan(shape, scale, (0, 0, *shape))
    for name in ('required_work_bytes', 'retained_bytes'):
        if type(native.get(name)) is not int or native[name] < 0:
            raise ValueError('Neck native memory plan omitted checked aggregate costs')
    # Native total already charges source/weight/protect (17N). Source is
    # charged by packet.resident_bytes; raster allowance covers weight/protect.
    # Other native scratch and retained output are additive to those residents.
    native_extra = native['required_work_bytes'] - 17*shape[0]*shape[1]
    if native_extra < 0:
        raise ValueError('Neck native memory plan omitted its resident inputs')
    # Preview projection is separate from measurement. Reserve padded full-grid
    # gain/eligibility plus cv2 result, immutable output and validation scratch
    # before source resolution or either image-sized allocation.
    projected = application_shape != shape
    projection_bytes = (8*shape[0]*shape[1] + 20*application_shape[0]*application_shape[1]
                        + 8*1024**2) if projected else 0
    return {'active': True, 'source_shape_hw': shape, 'line_half_width_px': scale,
            'application_shape_hw': application_shape, 'projection_bytes': projection_bytes,
            'source': deepcopy(record['source']), 'support_sha256': key,
            'raster': raster, 'native': native,
            'required_work_bytes': raster['required_work_bytes'] + native_extra + projection_bytes,
            'retained_bytes': native['retained_bytes'] + (4*application_shape[0]*application_shape[1] if projected else 0)}


def _project_display(effect, eligible, application_shape, cancelled):
    """Project a SOLVED canonical field, never estimate from preview pixels.

    Matches people_snapshot's cv2.INTER_LINEAR pixel-edge-centre convention:
    canonical sample = (display index + .5) * canonical/display extent - .5.
    This is explicitly an interactive approximation, not a full-output review.
    Any noneligible interpolation tap vetoes the display correction, preventing
    interpolation from weakening hard/complete-context protection at its taps.
    """
    import cv2
    from .people_effects import LocalEffect
    canonical = tuple(effect.facts['source_shape_hw'])
    if canonical == application_shape:
        return effect
    _poll(cancelled)
    y, x, h, w = effect.window
    full = np.zeros(canonical, np.float32)
    full[y:y+h, x:x+w] = effect.log_gain[..., 0]
    gain = cv2.resize(full, (application_shape[1], application_shape[0]), interpolation=cv2.INTER_LINEAR)
    _poll(cancelled)
    full.fill(1)
    full[y:y+h, x:x+w] = ~eligible
    blocked = cv2.resize(full, (application_shape[1], application_shape[0]), interpolation=cv2.INTER_LINEAR)
    del full
    _poll(cancelled)
    gain[blocked > 0] = 0
    from .neck_wrinkle_measure import MAX_LOG_GAIN
    if (gain.dtype != np.float32 or gain.shape != application_shape
            or not np.isfinite(gain).all() or np.any(gain < 0)
            or np.any(gain > MAX_LOG_GAIN + 1e-8)):
        raise ValueError('Neck display projection returned invalid scalar field transport')
    # Bytes-backed output cannot be made writable after publication.
    field = np.frombuffer(gain.tobytes(order='C'), dtype=np.float32).reshape((*application_shape, 1))
    projection = {'version': 1, 'kind': 'canonical-field-preview-only',
        'mapping': 'source-pixel-edge-centres-cv2-linear',
        'canonical_shape_hw': list(canonical), 'application_shape_hw': list(application_shape),
        'authorizes_review': False, 'authorizes_export': False}
    facts = {**deepcopy(effect.facts), 'application_shape_hw': list(application_shape),
             'render_dimensions': [application_shape[1], application_shape[0]],
             'display_projection': projection,
             'application_field_pixels': int(np.count_nonzero(field)),
             'application_quality': 'interactive-approximation-from-canonical-measurement',
             'review_authority': False}
    _poll(cancelled)
    return LocalEffect(effect.face_ref, 'neck_wrinkle', (0, 0, *application_shape),
                       log_gain=field, amounts=dict(effect.amounts), facts=facts)


def _prepare(ref, analysis, recipe, *, people_state, body_assets, body_bank,
             full_source, byte_budget, cancelled=None, include_review=False, render_shape=None):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return ([], None) if include_review else []  # No source/support/native lookup or effect allocation.
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be callable')
    _poll(cancelled)
    admission = plan(ref, analysis, recipe, people_state=people_state,
                     body_assets=body_assets, body_bank=body_bank, render_shape=render_shape)
    if include_review and admission['application_shape_hw'] != admission['source_shape_hw']:
        raise ValueError('Neck review cannot be authorized by a reduced display projection')
    if type(byte_budget) is not int or byte_budget < admission['required_work_bytes']:
        raise MemoryError('Neck full-source support and detector exceed memory budget before allocation')
    from .neck_wrinkle_source import resolve as resolve_full_source
    packet = resolve_full_source(full_source, face_ref=ref, source=admission['source'],
        analysis=analysis, byte_budget=byte_budget-admission['required_work_bytes'], cancelled=cancelled)
    # Provenance is checked by the exact internal resolver, not minted here.
    source = packet.rgb; canonical_analysis = packet.analysis; shape = admission['source_shape_hw']
    if (type(source) is not np.ndarray or source.dtype != np.float32
            or source.shape != (*shape, 3) or not source.flags.c_contiguous or source.flags.writeable
            or not np.isfinite(source).all() or np.any((source < 0) | (source > 1))):
        raise ValueError('Neck resolver must return immutable full canonical SDR working-sRGB RGB')
    if type(packet.resident_bytes) is not int or packet.resident_bytes < source.nbytes:
        raise ValueError('Neck source resolver omitted its resident canonical/repair/analysis allocation')
    if packet.resident_bytes + admission['required_work_bytes'] > byte_budget:
        raise MemoryError('Neck source, all support scratch and native field exceed aggregate budget')
    _poll(cancelled)
    record, key = C.resolve(people_state, body_assets, ref, body_bank, canonical_analysis)
    if key != admission['support_sha256']:
        raise ValueError('Neck review changed during canonical source resolution')
    coverage, hard, support_facts = C.raster(people_state, body_assets, ref, body_bank,
        canonical_analysis, shape, byte_budget=admission['raster']['required_work_bytes'], cancelled=cancelled)
    _poll(cancelled)
    from . import neck_wrinkle_measure as N
    prepared = N.measure(source, coverage, hard, line_half_width_px=admission['line_half_width_px'],
        byte_budget=admission['native']['required_work_bytes'],
        cancelled=cancelled)
    _poll(cancelled)
    window = prepared.window_yxhw
    if (type(window) not in (tuple, list) or len(window) != 4
            or any(type(n) is not int for n in window)):
        raise ValueError('Neck field lost its exact full-source window')
    y, x, h, w = window
    if min(y, x) < 0 or min(h, w) < 1 or y+h > shape[0] or x+w > shape[1]:
        raise ValueError('Neck field exceeds the canonical source extent')
    field = prepared.log_gain
    if (type(field) is not np.ndarray or field.dtype != np.float32
            or field.shape != (h, w) or field.flags.writeable or not field.flags.c_contiguous
            or not np.isfinite(field).all() or np.any(field < 0)
            or np.any(field > N.MAX_LOG_GAIN + 1e-8)
            or tuple(prepared.source_shape_hw) != shape
            or prepared.algorithm_version != admission['native']['algorithm_version']):
        raise ValueError('Neck kernel must return a bounded readonly full-source scalar log-gain field')
    eligible = prepared.eligible_mask
    if (type(eligible) is not np.ndarray or eligible.dtype != np.bool_
            or eligible.shape != (h, w) or eligible.flags.writeable or not eligible.flags.c_contiguous):
        raise ValueError('Neck kernel omitted immutable full-context admission independent of detected lines')
    changed = field != 0
    if np.any(changed & ~eligible):
        raise ValueError('Neck field changed a source center without complete context admission')
    if np.any(changed & ((coverage[y:y+h, x:x+w] <= 0) | hard[y:y+h, x:x+w])):
        raise ValueError('Neck kernel changed hard-protected or unowned pixels')
    report = prepared.facts
    if not isinstance(report, Mapping) or report.get('runtime_quality_accepted') is not False:
        raise ValueError('Neck kernel omitted honest unaccepted-runtime facts')
    for name in ('supported_pixels', 'context_rejected_pixels', 'line_pixels', 'changed_pixels'):
        if type(report.get(name)) is not int or not 0 <= report[name] <= shape[0]*shape[1]:
            raise ValueError('Neck kernel returned invalid support/line/context diagnostics')
    count = int(np.count_nonzero(changed))
    if report['changed_pixels'] != count or not count <= report['line_pixels'] <= report['supported_pixels']:
        raise ValueError('Neck kernel confused admitted support, detected lines or actual proposed changes')
    if report['supported_pixels'] != int(np.count_nonzero(eligible)):
        raise ValueError('Neck reported support differs from the actual numerical eligible mask')
    if report['supported_pixels'] == 0:
        raise ValueError('Neck review has no complete owned source sampling footprint')
    if count == 0:
        expected_reason = ('no_detected_wrinkle_lines' if report['line_pixels'] == 0
                           else 'no_positive_wrinkle_lift')
        if report.get('no_signal_reason') != expected_reason:
            raise ValueError('Successful neutral neck measurement must distinguish absent lines from gated zero lift')
    proof = deepcopy(packet.proof)
    facts = {'operation_id': S.OP, 'control_id': S.CONTROL_ID, 'face_ref': deepcopy(ref),
        'body_ref': deepcopy(support_facts['body_ref']), 'body_support': support_facts,
        'source_proof': proof, 'source_dimensions': [shape[1], shape[0]],
        'render_dimensions': [shape[1], shape[0]], 'source_window': list(window),
        'source_shape_hw': list(shape), 'application_shape_hw': list(shape),
        'display_projection': None, 'review_authority': True,
        'line_half_width_px': admission['line_half_width_px'],
        'algorithm_version': prepared.algorithm_version,
        'measurement_key': C.measurement_key(record, support_facts, proof, prepared.algorithm_version),
        'scope': 'reviewed-visible-neck-skin-and-context-only',
        'field_contract': 'readonly-full-source-ROI-positive-scalar-log-gain',
        'application': 'native-current-stage-common-linear-RGB-gain-with-real-headroom',
        'native_report': dict(report), 'changed_pixels': count,
        'no_signal_reason': report.get('no_signal_reason'), 'runtime_quality_accepted': False,
        'limitations': ['manual-assisted-not-automatic-neck-detection',
            'unknown-occlusion-and-confidently-wrong-semantics-require-human-review',
            'fine-texture-and-perceptual-hue-invariance-not-guaranteed',
            'resampled-semantic-plane-is-not-new-full-resolution-inference',
            'no-cross-image-cohorts-batch-or-generic-face-recovery']}
    log_gain = field[..., None]; log_gain.setflags(write=False)
    from .people_effects import LocalEffect
    _poll(cancelled)
    # Valid no-lines keeps a zero field with honest facts for the comparison;
    # publication must not claim that supported_pixels means a visible change.
    effects = [LocalEffect(ref, 'neck_wrinkle', tuple(window), log_gain=log_gain,
                           amounts={'amount': recipe['amount']}, facts=facts)]
    if include_review:
        evidence = NeckReviewEvidence(coverage, hard, eligible, tuple(window), shape,
            facts['measurement_key'], deepcopy(proof), deepcopy(facts))
        return effects, evidence
    if admission['application_shape_hw'] != shape:
        return [_project_display(effects[0], eligible, admission['application_shape_hw'], cancelled)]
    return effects


def prepare(ref, analysis, recipe, *, people_state, body_assets, body_bank,
            full_source, byte_budget, cancelled=None, render_shape=None):
    """Canonical solve, optionally projected only for the ordinary display grid.

    ``render_shape`` is an application extent, NEVER a measurement extent. Full
    export/review must omit it or pass the canonical shape. Projected records
    retain canonical measurement identity and explicitly deny review/export
    authority; they cannot be reused as full-resolution fields.
    """
    return _prepare(ref, analysis, recipe, people_state=people_state, body_assets=body_assets,
        body_bank=body_bank, full_source=full_source, byte_budget=byte_budget, cancelled=cancelled,
        render_shape=render_shape)


def prepare_review(ref, analysis, recipe, *, people_state, body_assets, body_bank,
                   full_source, byte_budget, cancelled=None):
    """Same solve plus exact cyan/hard/context-rejected diagnostic inputs.

    Host may release these rasters before canonical comparison rendering and
    repeat deterministic measurement against the SAME source/repair/support/key.
    A positive manual brush alone is never the final admission overlay.
    """
    return _prepare(ref, analysis, recipe, people_state=people_state, body_assets=body_assets,
        body_bank=body_bank, full_source=full_source, byte_budget=byte_budget,
        cancelled=cancelled, include_review=True)
