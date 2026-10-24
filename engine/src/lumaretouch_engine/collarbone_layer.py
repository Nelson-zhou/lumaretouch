# SPDX-License-Identifier: GPL-3.0-or-later
"""Reviewed source-visible clavicle contrast, not generated anatomy. UNRUN.

Only explicit manual traces plus separately reviewed, semantic own-body skin
provide support. The Rust estimator reads the immutable effective source stage
(including canonical repair replay); its log-light field is applied later to
actual current-stage pixels. No shoulder landmarks, face rectangles, cached
preview effect or blanket lightness lift substitute for visible clavicles.
"""
from collections.abc import Mapping
import numpy as np

from . import collarbone_state as S, collarbone_support as C
from . import skin_colour_body_support as SUPPORT
from . import people_state as P

_FIXED_BYTES = 32 * 1024**2
_HOST_BYTES_PER_PIXEL = 24
_RASTER_BYTES_PER_PIXEL = 24
_RASTER_FIXED_BYTES = 32 * 1024**2


def _poll(cancelled):
    if cancelled is not None and cancelled():
        raise InterruptedError('Collarbone preparation cancelled; no partial field published')


def prepare(ref, analysis, source, recipe, *, people_state, body_assets, body_bank,
            byte_budget, cancelled=None):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return []
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be callable')
    _poll(cancelled)
    if (type(source) is not np.ndarray or source.dtype != np.float32 or source.ndim != 3
            or source.shape[2] != 3 or min(source.shape[:2]) < 2):
        raise ValueError('Collarbone needs actual source-stage float32 working-sRGB RGB')
    h, w = source.shape[:2]
    baseline = h*w*_HOST_BYTES_PER_PIXEL + _FIXED_BYTES
    raster_bytes = h*w*_RASTER_BYTES_PER_PIXEL + _RASTER_FIXED_BYTES
    if type(byte_budget) is not int or byte_budget < baseline+raster_bytes:
        raise ValueError('Collarbone source and coverage exceed memory budget before allocation')
    ref = P.check_ref(ref)
    if type(analysis) is not dict or analysis.get('face_ref') != ref:
        raise ValueError('Collarbone needs exact retained source/person analysis')
    resolved = SUPPORT.resolve(people_state, body_assets, ref, body_bank, analysis,
                               family=C.FAMILY, operation_id=S.OP)
    if resolved is None:
        raise ValueError('Active collarbone contrast requires its own body/anatomy review')
    record, key = resolved
    clavicle = C.check(record['row']['review']['clavicle'], source=record['source'])
    from .body_pose_evidence import whole_source_shape, ORIENTATION
    whole_source_shape({**record['source'], 'orientation': ORIENTATION}, (h, w))
    # Width/coordinate admission is repeated on the actual render grid by the
    # native boundary. Source-normalized curves never become preview assets.
    curves = clavicle['curves']
    from . import collarbone_native as N
    native_bytes = N.memory_estimate((h, w), curves)
    if baseline+raster_bytes+native_bytes > byte_budget:
        raise ValueError('Collarbone real source window and halo exceed memory budget before allocation')
    if not np.isfinite(source).all() or np.any((source < 0) | (source > 1)):
        raise ValueError('Collarbone refuses nonfinite or HDR source instead of clipping')
    _poll(cancelled)
    coverage, support_facts = SUPPORT.raster(people_state, body_assets, ref, body_bank,
        analysis, (h, w), byte_budget=byte_budget-baseline-native_bytes,
        family=C.FAMILY, operation_id=S.OP)
    if (coverage is None or not support_facts.get('enabled')
            or support_facts.get('support_sha256') != key
            or support_facts.get('body_ref') != record['row']['review']['body_ref']
            or support_facts.get('points_sha256') != record['row']['review']['points_sha256']
            or support_facts.get('body_record_sha256') != record['row']['body_record_sha256']):
        raise ValueError('Collarbone reviewed source/body support changed during preparation')
    if (type(coverage) is not np.ndarray or coverage.dtype != np.float32
            or coverage.shape != (h, w) or not np.isfinite(coverage).all()
            or np.any((coverage < 0) | (coverage > 1))):
        raise ValueError('Collarbone needs finite actual-grid owned skin coverage')
    _poll(cancelled)
    if not N.available():
        raise RuntimeError('Collarbone Rust kernel is unavailable; no Python effect fallback')
    prepared = N.prepare(source, coverage, curves, cancelled=cancelled or (lambda: False))
    _poll(cancelled)
    field = prepared.field
    if (type(field) is not np.ndarray or field.dtype != np.float32 or field.ndim != 2
            or min(field.shape) < 1 or not field.flags.c_contiguous or field.flags.writeable
            or not np.isfinite(field).all() or np.any(np.abs(field) > N.MAX_LOG_GAIN+1e-8)
            or tuple(prepared.source_shape) != (h, w)):
        raise ValueError('Collarbone native field is not a bounded immutable actual-source log-light ROI')
    origin = prepared.origin
    if (type(origin) not in (tuple, list) or len(origin) != 2
            or any(type(n) is not int or n < 0 for n in origin)):
        raise ValueError('Collarbone native field lost its full-source origin')
    x, y = origin; rh, rw = field.shape
    if y+rh > h or x+rw > w:
        raise ValueError('Collarbone field exceeds its actual source domain')
    changed = field != 0
    report = prepared.report
    if (not isinstance(report, Mapping) or type(report.get('supported_pixels')) is not int
            or not 0 <= report['supported_pixels'] <= rh*rw):
        raise ValueError('Collarbone native diagnostics omitted actual admitted-source evidence')
    if report['supported_pixels'] == 0 or not np.any(changed):
        raise ValueError('No observed source clavicle contrast in the reviewed traces; positive collarbone effect was not published')
    changed_pixels = int(np.count_nonzero(changed))
    if report['supported_pixels'] != changed_pixels:
        raise ValueError('Collarbone native diagnostics differ from the actual supported source field')
    if np.any(changed & (coverage[y:y+rh, x:x+rw] <= 0)):
        raise ValueError('Collarbone native field changed protected source pixels')
    log_gain = field[..., None]
    log_gain.setflags(write=False)
    facts = {'operation_id': S.OP, 'control_id': S.CONTROL_ID, 'recipe': recipe,
        'face_ref': ref, 'body_ref': support_facts['body_ref'], 'body_support': support_facts,
        'source_dimensions': [record['source']['width'], record['source']['height']],
        'render_dimensions': [w, h], 'source_window': [y, x, rh, rw],
        'scope': 'reviewed-source-visible-clavicle-body-skin-only',
        'source_contract': 'immutable-effective-source-stage-working-srgb-sdr',
        'anatomy': 'explicit-manual-source-normalized-polylines-not-shoulder-inference',
        'curve_count': len(curves), 'category': clavicle['category'],
        'category_basis': 'explicit-user-confirmation-not-inferred-demographics',
        'width_convention': 'half-width-fraction-of-source-short-side',
        'field_contract': 'readonly-source-ROI-scalar-log-light-gain',
        'application': 'bounded-neutral-light-on-actual-current-stage-linear-RGB',
        'native_report': dict(report), 'changed_pixels': changed_pixels,
        'native_solver': 'rust-collarbone-v1', 'runtime_quality_accepted': False,
        'limitations': ['manual-assisted-2D-not-3D-AI-or-hidden-clavicle-reconstruction',
            'unknown-occlusion-and-semantic-errors-still-need-human-before-after-review',
            'source-contrast-is-not-a-calibrated-anatomy-or-lighting-decomposition',
            'no-observed-signal-refuses-positive-intent-no-drawn-shadow-or-highlight',
            'resampled-semantic-evidence-is-not-new-full-resolution-inference']}
    from .people_effects import LocalEffect
    return [LocalEffect(ref, 'collarbone', (y, x, rh, rw), log_gain=log_gain,
                        amounts={'amount': recipe['amount']}, facts=facts)]
