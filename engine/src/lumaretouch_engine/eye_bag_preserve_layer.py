# SPDX-License-Identifier: GPL-3.0-or-later
"""Whole-source legacy bag solve plus explicit manual ridge protection.

AUTHORED / UNRUN. Reuses the unchanged pinned AGPL RapidRetouch eye-bag
frequency-separated dodge/burn and crease solver. No generic blur substitute,
no anatomical ridge detector and no claim of total removal at preserve zero.
New preservation acts on this operation's delta ONLY, before geometry warps.
"""
import hashlib
from pathlib import Path
import numpy as np

from . import people_state as P, eye_bag_preserve_state as S
from . import eye_bag_preserve_support as SUPPORT

SOLVER_SHA256 = '1f9f953b70c759c94bcc605962c9de5be0ab0e0c2956c86f065b9d74620359da'
_FIXED_BYTES = 64 * 1024**2
_BYTES_PER_PIXEL = 64
_ROI_BYTES_PER_PIXEL = 384
_MAX_PIXELS = 64_000_000


def _poll(cancelled):
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be callable')
    if cancelled is not None and cancelled():
        raise InterruptedError('Eye-bag preservation cancelled; no partial layer published')


def _solver():
    from .third_party.rapidretouch import under_eye as EYES
    if hashlib.sha256(Path(EYES.__file__).read_bytes()).hexdigest() != SOLVER_SHA256:
        raise RuntimeError('Eye-bag solver differs from the reviewed unchanged AGPL source pin')
    if EYES.cv2 is None:
        raise RuntimeError('Eye-bag correction needs existing OpenCV support; no replacement effect generated')
    return EYES


def _source_digest(source, cancelled=None):
    digest = hashlib.sha256()
    digest.update(str(source.shape).encode('ascii'))
    # Bounded row updates avoid another complete-source serialization buffer.
    for row in source:
        _poll(cancelled)
        digest.update(np.ascontiguousarray(row, dtype='<f4').tobytes())
    return digest.hexdigest()


def _validate_result(source, corrected, protected, coverage, preserve):
    if (type(protected) is not np.ndarray or protected.dtype != np.float32
            or protected.shape != source.shape or not np.isfinite(protected).all()
            or np.any((protected < 0) | (protected > 1))):
        raise ValueError('Eye-bag protection needs finite SDR float32 RGB, without extra clipping')
    core = (coverage == 1) if preserve == 1 else np.zeros(coverage.shape, bool)
    # View bits rather than approximate equality: source signed zeros survive.
    if not np.array_equal(protected[core].view(np.uint32), source[core].view(np.uint32)):
        raise ValueError('Full ridge protection failed exact source preservation')
    no_change = np.all(corrected == source, axis=2)
    if not np.array_equal(protected[no_change].view(np.uint32), source[no_change].view(np.uint32)):
        raise ValueError('Eye-bag protection changed untouched source pixels')
    if preserve == 0 and not np.array_equal(protected[~no_change], corrected[~no_change]):
        raise ValueError('Zero preservation changed the admitted legacy solver result')


def prepare(face_ref, analysis, source, recipe, *, people_state, support_assets,
            byte_budget, cancelled=None):
    """Return one immutable source delta, solved before preview/export tiling.

    The host authenticates actual effective-source bytes and the committed
    repair/snapshot identity. A source-owned geometric review is not a claim of
    unchanged source photometry; repairs do not reuse cached correction pixels.
    Source RGB is opaque encoded working-sRGB float32 in [0,1]. RGBA, HDR and
    malformed inputs refuse explicitly. A full-resolution caller must provide
    real decoded/repaired full-source bytes, not an enlarged preview raster.
    """
    recipe = S.check(recipe)
    if not S.active(recipe):
        return []  # No support, native library, analysis, source or budget needed.
    _poll(cancelled)
    if (type(source) is not np.ndarray or source.dtype != np.float32 or source.ndim != 3
            or source.shape[2] != 3 or min(source.shape[:2]) < 2):
        raise ValueError('Eye-bag preservation requires opaque current-source float32 working-sRGB RGB')
    h, w = source.shape[:2]
    if (h*w > _MAX_PIXELS or type(byte_budget) is not int
            or byte_budget < _FIXED_BYTES + h*w*_BYTES_PER_PIXEL):
        raise ValueError('Whole-source eye-bag solve exceeds conservative memory admission; no proxy fallback')
    if not np.isfinite(source).all() or np.any((source < 0) | (source > 1)):
        raise ValueError('Eye-bag preservation refuses nonfinite/HDR source instead of silently clipping it')
    state = P.check(people_state)
    ref = P.check_ref(face_ref)
    coverage, eligible, support_facts = SUPPORT.admitted_fields(state, support_assets, ref,
        (h, w), analysis=analysis, byte_budget=byte_budget, cancelled=cancelled)
    EYES = _solver()
    from . import eye_bag_preserve_native as N
    if not N.available():
        raise RuntimeError('Eye-bag preservation Rust core is unavailable; no Python effect fallback')
    from .under_eye_layer import bounds
    # Existing complete-face source ROI and 2-eye-width padding preserve all
    # legacy eye crop/filter/reference context. This is NOT a render tile and
    # is never resized; vector coordinates still refer to the whole source.
    window, landmarks_px = bounds(analysis['landmarks'], h, w)
    y, x, rh, rw = window
    if (_FIXED_BYTES+h*w*_BYTES_PER_PIXEL+rh*rw*_ROI_BYTES_PER_PIXEL
            + N.memory_estimate((rh, rw)) > byte_budget):
        raise ValueError('Complete source-face eye-bag ROI exceeds memory admission; no halo reduction')
    frozen = np.array(source[y:y+rh, x:x+rw], dtype=np.float32, order='C', copy=True)
    frozen.setflags(write=False)
    corrected = frozen.copy()
    points = landmarks_px - np.array([x, y], dtype=np.float32)
    local_eligible = eligible[y:y+rh, x:x+rw]
    local_coverage = np.array(coverage[y:y+rh, x:x+rw], dtype=np.float32, order='C', copy=True)
    local_coverage.setflags(write=False)
    params = EYES.Params(dark_circles=0.0, eye_bags=recipe['amount'])
    # Use the pinned per-eye solver on complete, unscaled effective-source
    # context, with the required full legacy crop/halo explicitly checked.
    # Do not solve unreviewed eyes, and do not attenuate dark circles, veins,
    # highlights, red eye or any other independently prepared correction.
    reviewed = [side for side in EYES.EYES if support_facts['sides'][side]['reviewed']]
    for side in reviewed:
        _poll(cancelled)
        whole_geo = EYES._eye_geometry(landmarks_px, EYES.EYES[side])
        whole_extent = np.concatenate((whole_geo['bag'], whole_geo['contour'], whole_geo['crows_feet']))
        margin = (EYES.SURROUND+.3)*whole_geo['eye_w']
        low = np.maximum(np.floor(whole_extent.min(axis=0)-margin), 0)
        high = np.minimum(np.ceil(whole_extent.max(axis=0)+margin), [w, h])
        if np.any(low < [x, y]) or np.any(high > [x+rw, y+rh]):
            raise ValueError('Complete face ROI would truncate the pinned solver source/reference halo')
        EYES._correct_eye(corrected, EYES._eye_geometry(points, EYES.EYES[side]), params)
        _poll(cancelled)  # Legacy OpenCV call itself has no cancellation hook.
    if not np.isfinite(corrected).all() or np.any((corrected < 0) | (corrected > 1)):
        raise ValueError('Pinned eye-bag solver returned an invalid bounded SDR result')
    corrected[~local_eligible] = frozen[~local_eligible]
    corrected = np.ascontiguousarray(corrected, dtype=np.float32)
    corrected.setflags(write=False)
    _poll(cancelled)
    protected = N.apply(frozen, corrected, local_coverage, recipe['preserve'], cancelled=cancelled)
    _poll(cancelled)
    _validate_result(frozen, corrected, protected, local_coverage, recipe['preserve'])
    delta = np.ascontiguousarray(protected-frozen, dtype=np.float32)
    # Explicitly zero the full-coverage preservation branch. Common staging
    # uses delta!=0, so other stages/current RGB survive without reassignment.
    if recipe['preserve'] == 1:
        delta[local_coverage == 1] = np.float32(0)
    delta[~local_eligible] = np.float32(0)
    if not np.isfinite(delta).all():
        raise ValueError('Eye-bag preservation produced a nonfinite contribution')
    delta.setflags(write=False)
    changed = int(np.count_nonzero(np.any(delta != 0, axis=2)))
    facts = {'operation_id': S.OP, 'control_id': S.CONTROL_ID, 'recipe': recipe,
        'face_ref': ref, 'support': support_facts, 'reviewed_eyes': reviewed,
        'source_dimensions': support_facts['source_dimensions'], 'render_dimensions': [w, h],
        'effective_source_pixel_sha256': _source_digest(source, cancelled),
        'source_contract': 'actual-opaque-effective-source-encoded-working-srgb-sdr',
        'source_window': list(window), 'whole_source_solved_before_tiles': True,
        'source_roi_policy': 'existing-complete-face-bounds-plus-two-eye-width-reference-padding-no-resampling',
        'solver': 'pinned-rapidretouch-under-eye-bag-frequency-and-crease',
        'solver_sha256': SOLVER_SHA256, 'preservation_solver': 'rust-eye-bag-preserve-v1',
        'changed_pixels': changed, 'reason': None if changed else 'no-admitted-source-correction',
        'automatic_ridge_detection': False, 'runtime_quality_accepted': False,
        'limitations': [
            'manual-painted-visible-source-region-not-automatic-anatomical-ridge-detection',
            'unreviewed-eye-unchanged-no-inferred-absence-of-ridge',
            'full-preserve-exact-only-at-weight-one-relative-to-this-pre-geometry-effect',
            'fractional-feather-coverage-retains-only-that-fraction-of-source-correction',
            'preserve-zero-restores-admitted-existing-solver-not-total-eye-bag-or-ridge-removal',
            'semantic-class-support-and-landmarks-are-not-instance-or-unknown-occlusion-proof',
            'legacy-opencv-solver-is-cancellable-only-between-complete-eye-solves',
            'other-effects-and-later-geometry-can-change-final-displayed-pixels',
        ]}
    from .people_effects import LocalEffect
    _poll(cancelled)
    return [LocalEffect(ref, 'eye_bag_preserve', window, delta=delta, facts=facts)]
