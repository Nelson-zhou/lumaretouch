# SPDX-License-Identifier: GPL-3.0-or-later
"""Measured same-photo reference proposal, never review consent. AUTHORED / UNRUN.

The existing Rust fitter measures each face against ITSELF with zero correction
limits. Its robust source ln(Y) centre supplies brightness, not segmentation
confidence, demographic labels or an invented proprietary metric. This module
does not apply pixels, retain support, edit recipes or approve any reference.

Capture FullSource through portrait_fit_source before repairs/portrait effects.
The host must fence the source, graph and analysis generation around this call
and still require the operation's source-overlay and before/after review.
"""
from copy import deepcopy
import math

import numpy as np

from . import face_scope as FACE, people_state as P
from . import skin_reference_match_native as N
from . import skin_reference_match_runtime as R
from . import skin_reference_match_state as S
from . import skin_reference_match_support as A
from .cpu_memory_budget import available_estimate

VERSION = 1
MAX_FACES = 64
METHOD = 'rust-self-fit-robust-log-linear-srgb-y-v1'
# A local conservative tie band, NOT a perceptual threshold, calibrated
# confidence interval, or a statement about the external product's metric.
MIN_LOG_GAP = math.log(1.02)
FIXED_BYTES = 128 * 1024**2
RECORD_BYTES = 64 * 1024


def _cancellation_probe(cancelled):
    if not callable(cancelled):
        raise TypeError('cancelled must be callable')
    def probe():
        try:
            return cancelled()
        except InterruptedError:
            raise
        except Exception as error:
            # A callback ValueError is not a candidate-specific evidence refusal.
            raise RuntimeError('Reference-choice cancellation callback failed') from error
    return probe


def _admit(required, byte_budget):
    if type(byte_budget) is not int or byte_budget < 0:
        raise ValueError('Reference choice needs an explicit total working byte budget')
    if required > byte_budget or required > available_estimate():
        raise MemoryError('Measured reference choice exceeds memory admission; no proxy fallback')


def _analysis_bytes(analyses, faces):
    if type(analyses) is not dict or len(analyses) > MAX_FACES:
        raise ValueError('Reference choice needs a bounded same-source analysis bank')
    total = 0
    for key, row in analyses.items():
        P.token(key)
        if key not in faces or type(row) is not dict or len(row) > 32:
            raise ValueError('Reference choice analysis has a foreign/stale owner or unbounded row')
        # Charge all supplied ndarray backing storage, including unused semantic
        # channels and aliases. A tiny view cannot hide its large backing array.
        total += sum(R.array_bytes(value) for value in row.values())
    return total


def _snapshot(face, raw, source, cancelled):
    """Copy only independently authenticated fields; never synthesize a mask."""
    R._poll(cancelled)
    landmarks = raw.get('landmarks')
    if (type(landmarks) is not np.ndarray or landmarks.dtype != np.float32
            or landmarks.shape != (478, 3)):
        raise ValueError('Reference choice requires the actual bounded float32 478-point observation')
    landmarks, observation = A._analysis(face, raw)
    evidence = raw['evidence']
    if (evidence['source_width'], evidence['source_height']) != (source['width'], source['height']):
        raise ValueError('Reference-choice anatomy belongs to different canonical source dimensions')
    row = {'face_ref': P.face_ref(face), 'evidence': deepcopy(evidence),
           'landmarks': landmarks, 'face_skin_observation': observation}
    for name in ('face_skin', 'excluded'):
        R._poll(cancelled)
        row[name] = np.array(raw[name], dtype=np.float32, order='C', copy=True)
        row[name].setflags(write=False)
    row['landmarks'].setflags(write=False)
    # The copy must still agree with the retained exact evidence; live input
    # mutation cannot substitute a different landmark generation mid-copy.
    A._analysis(face, row)
    return row


def _coverage(state, face, analysis, anatomy, shape, cancelled):
    """Same face-skin/feature/footprint/occluder exclusions as reviewed support.

    Other faces' independently validated ovals and all retained same-source
    boxes are VETOES ONLY, including disabled faces. They never supply this
    face's anatomy, skin, luminance samples or affirmative ownership.
    """
    R._poll(cancelled)
    ref = P.face_ref(face)
    landmarks, _ = A._analysis(face, analysis, shape)
    oval, extent = A._extent(landmarks, shape)
    others = tuple(value for key, value in anatomy.items() if key != ref['face_instance_id'])
    boxes = [other['box'] for other in state['faces'].values()
             if other['asset_sha256'] == ref['asset_sha256'] and P.face_ref(other) != ref]
    coverage = FACE.selected_face_skin(analysis['face_skin'], landmarks, other_landmarks=others)
    coverage[analysis['excluded'] > .1] = 0
    A._protect(coverage, oval, extent, boxes, cancelled)
    window = A._window(coverage)
    coverage.setflags(write=False)
    R._poll(cancelled)
    return coverage, window, len(boxes), len(others)


def _self_measure(pixels, coverage, window, *, byte_budget, cancelled):
    """No new numerical implementation: real source ROI against the same ROI."""
    rgb, weight = R._roi(pixels, window), R._roi(coverage, window)
    measured = N.fit(rgb, weight, rgb, weight, limits=(0., 0.),
                     byte_budget=byte_budget, cancelled=cancelled)
    if type(measured) is not N.MeasuredFit:
        raise ValueError('Reference choice requires an original native measured result')
    measured.checked()
    d = measured.diagnostics
    if (measured.reference_shape != window[2:] or measured.target_shape != window[2:]
            or measured.limits != (0., 0.) or measured.transform != (1., 0., 0., 0.)
            or any(d[a] != d[b] for a, b in ((1, 2), (3, 4), (5, 6)))
            or d[7:10] != d[10:13] or d[13:16] != d[16:19]
            or d[19:22] != (0., 0., 0.) or d[22] != 0.
            or not math.log(.01) < d[7] < math.log(.90)):
        raise ValueError('Reference choice received inconsistent source-only self-fit diagnostics')
    # Reliability/count/MAD are displayed as evidence facts, never used as a
    # brightness score, tie-breaker, beauty score or statistical confidence.
    return {'log_luminance': float(d[7]), 'linear_luminance': math.exp(d[7]),
            'initial_log_luminance_mad': float(d[13]),
            'robust_sample_count': int(d[1]), 'robust_weight': float(d[3]),
            'effective_samples': float(d[5]), 'retained_weight_fraction': float(d[23])}


def _selection(rows, run, manual_reference):
    enabled = [row for row in rows if row['status'] != 'disabled']
    ranked = sorted((row for row in enabled if row['status'] == 'measured'),
                    key=lambda row: (-row['measurement']['log_luminance'],
                                     row['face_ref']['face_instance_id']))
    reasons = []
    if len(enabled) < 2:
        reasons.append('fewer-than-two-enabled-retained-faces')
    if any(row['status'] != 'measured' for row in enabled):
        reasons.append('enabled-face-measurement-unavailable')
    if run is not None and run['limit_reached']:
        reasons.append('detector-limit-reached')
    gap = None
    ambiguous = []
    if len(ranked) >= 2:
        top = ranked[0]['measurement']['log_luminance']
        gap = top - ranked[1]['measurement']['log_luminance']
        ambiguous = [deepcopy(row['face_ref']) for row in ranked
                     if top - row['measurement']['log_luminance'] <= MIN_LOG_GAP]
        if len(ambiguous) > 1:
            reasons.append('brightest-measurements-too-close')
        else:
            ambiguous = []
    automatic = deepcopy(ranked[0]['face_ref']) if ranked and not reasons else None
    selected = automatic
    mode = 'automatic-proposal' if automatic is not None else 'none'
    if manual_reference is not None:
        if not any(row['face_ref'] == manual_reference for row in ranked):
            raise ValueError('Explicit reference has no reliable current source measurement; no substitute selected')
        selected = deepcopy(manual_reference)
        mode = 'manual-override-proposal'
    return {'reference_face_ref': selected, 'selection_mode': mode,
            'automatic_status': 'proposed' if automatic is not None else 'blocked',
            'automatic_reference_face_ref': automatic,
            'automatic_blockers': reasons,
            'ranked_face_refs': [deepcopy(row['face_ref']) for row in ranked],
            'top_log_luminance_gap': gap, 'minimum_log_luminance_gap': MIN_LOG_GAP,
            'ambiguous_face_refs': ambiguous}


def propose(state, asset_sha256, full_source, analyses, *, byte_budget,
            manual_reference=None, cancelled=lambda: False):
    """Return JSON proposal facts only; never install/approve/apply the selection.

    ``full_source`` MUST be obtained from capture/capture_original for this
    source before repairs and portrait operations. Its type/digest checks do
    not turn caller-constructed objects into authenticated capture results.
    ``analyses`` contains independent actual face_skin/478 observations keyed
    by current stable face-instance ID, not a caller-supplied candidate subset.
    Candidates are ALL enabled retained faces for this source, at most 64; every
    disabled face is also disclosed and kept as a geometric protective veto.

    byte_budget includes supplied source, analyses and this call's workspace.
    Subtract unrelated application/renderer allocations first. Inputs must not
    be concurrently mutated; the host owns generation checks before publication.
    A returned selection is only a UI suggestion. Manual choice is allowed even
    when automatic ranking is blocked, but cannot bypass own-source evidence.
    """
    cancelled = _cancellation_probe(cancelled)
    R._poll(cancelled)
    state = P.check(state); P.digest(asset_sha256)
    source, shape = R._source_binding(full_source, asset_sha256)
    faces = {key: face for key, face in sorted(state['faces'].items())
             if face['asset_sha256'] == asset_sha256}
    if len(faces) > MAX_FACES:
        raise ValueError('Reference choice exceeds 64 retained same-source faces; no silent truncation')
    if manual_reference is not None:
        manual_reference, _ = A._face(state, manual_reference)
        if manual_reference['asset_sha256'] != asset_sha256:
            raise ValueError('Explicit reference must belong to this exact source')
    analysis_bytes = _analysis_bytes(analyses, faces)
    count = shape[0] * shape[1]
    # Covers original and snapshotted analysis backing arrays, graph copies and
    # metadata. Workspace covers projected semantics/full-plane validations;
    # each largest anatomical ROI additionally reserves geometry and native
    # self-fit snapshots. Faces are processed serially, not accumulated masks.
    resident = full_source.owned_bytes + 2*analysis_bytes + FIXED_BYTES + len(faces)*RECORD_BYTES
    workspace = 64*count + A._FIXED_BYTES + N.SCRATCH_BYTES + N.FIT_FIXED_SCRATCH_BYTES
    _admit(resident + workspace, byte_budget)
    rows, snapshots, anatomy = [], {}, {}
    for key, face in faces.items():
        R._poll(cancelled)
        row = {'face_ref': P.face_ref(face),
               'status': 'pending' if face['enabled'] else 'disabled'}
        raw = analyses.get(key)
        if raw is None:
            row['reason'] = 'actual-face-analysis-unavailable'
            if face['enabled']:
                row['status'] = 'unavailable'
        else:
            try:
                snapshot = _snapshot(face, raw, source, cancelled)
                snapshots[key] = snapshot
                anatomy[key] = snapshot['landmarks']
            except ValueError as error:
                row['reason'] = 'actual-face-analysis-invalid'
                row['detail'] = str(error)
                if face['enabled']:
                    row['status'] = 'unavailable'
        rows.append(row)
    largest = 0
    for key, landmarks in anatomy.items():
        if not faces[key]['enabled']:
            continue
        try:
            _, (x0, y0, x1, y1) = A._extent(landmarks, shape)
            largest = max(largest, (x1-x0)*(y1-y0))
        except ValueError:
            # Candidate-specific geometry refusal is reported below; it cannot
            # turn into unmeasured brightness or a whole-face rectangle.
            pass
    required = resident + workspace + 288*largest
    _admit(required, byte_budget)
    pixels = R._validate_source(full_source, cancelled)
    for row in rows:
        R._poll(cancelled)
        if row['status'] != 'pending':
            continue
        key = row['face_ref']['face_instance_id']
        projected = coverage = None
        try:
            projected = R._project(snapshots[key], shape, cancelled)
            coverage, window, boxes, ovals = _coverage(state, faces[key], projected,
                                                       anatomy, shape, cancelled)
            measurement = _self_measure(pixels, coverage, window,
                byte_budget=byte_budget-resident-64*count-A._FIXED_BYTES,
                cancelled=cancelled)
            row.update({'status': 'measured', 'measurement': measurement,
                'source_window': list(window),
                'support_sha256': R.coverage_digest(coverage),
                'evidence': deepcopy(snapshots[key]['evidence']),
                'landmark_digest': snapshots[key]['evidence']['landmark_digest'],
                'face_skin_observation': deepcopy(snapshots[key]['face_skin_observation']),
                'protected_face_boxes': boxes, 'protected_actual_face_ovals': ovals})
        except ValueError as error:
            row.update({'status': 'unavailable', 'reason': 'source-measurement-refused',
                        'detail': str(error)})
        finally:
            del coverage, projected
        # Cancellation/resource/native-capability failures intentionally escape:
        # there is no partial-success fallback or alternative brightness solver.
    R._poll(cancelled)
    run = state['analysis_runs'].get(asset_sha256)
    result = {'version': VERSION, 'operation_id': S.OP, 'control_id': S.CONTROL_ID,
        'method': METHOD, 'source': deepcopy(source), 'source_stage': A.SOURCE_STAGE,
        'source_pixels_sha256': full_source.input_sha256,
        'source_kind': full_source.kind, 'source_bits': full_source.source_bits,
        'source_encoding': N.ENCODING,
        'state_revision': state['revision'], 'association_revision': state['association_revision'],
        'candidate_scope': 'all-enabled-retained-same-source-faces',
        'census_complete': False, 'detector_limit_reached': None if run is None else run['limit_reached'],
        'candidates': rows, 'read_only_proposal': True, 'review_required': True,
        'reference_face_exclusion_required': True, 'body_extension_enabled': False,
        'fit_retained': False, 'portable': False, 'memory_admission_bytes': required,
        'limitations': ['not-a-complete-photograph-face-census',
            'observed-source-luminance-not-intrinsic-complexion',
            'confidence-is-not-brightness-and-no-demographic-inference',
            'unknown-occlusion-and-model-errors-require-visual-review',
            'resampled-semantic-observation-is-not-fresh-full-resolution-inference',
            'not-proprietary-metric-parity-or-complete-ai-multi-person-feature'],
        **_selection(rows, run, manual_reference)}
    result['proposal_sha256'] = A.content_digest(result)
    return result
