# SPDX-License-Identifier: GPL-3.0-or-later
"""Catalog-bound measured face proposal inside the existing people owner.

AUTHORED / UNRUN. This isolated port is not a dispatcher, review token, support
relation, body permission or render commit. Source-image load and explicit
ownership/before-after review remain the selected family's UI obligations.
"""
from copy import deepcopy
from dataclasses import fields, is_dataclass
import sys
import time
import math

import numpy as np

from . import people_state as P, skin_reference_choice as CHOICE
from . import skin_reference_match_host as FACE, skin_reference_body_host as BODY
from . import skin_reference_match_runtime as R
from . import portrait_fit_source as SOURCE
from .cpu_memory_budget import available_estimate
from .optics_candidate_identity import fingerprint

ACTION = 'skin_reference_choice'
READS = frozenset((ACTION,))
ACTIONS = READS
VERSION = 1
HOST_FIXED_BYTES = 64 * 1024**2
VERIFY_FIXED_BYTES = 64 * 1024**2
MAX_RESIDENT_NODES = 1_000_000
FAMILIES = {'face': (FACE, '_skin_reference_match_reviews'),
            'body': (BODY, '_skin_reference_body_reviews')}
REPORT_FIELDS = frozenset(('kind', 'version', 'operation_id', 'family', 'target',
    'document_id', 'revision', 'source', 'source_proof', 'source_review_sha256',
    'source_image_sha256', 'source_pixels_sha256', 'graph_sha256', 'document_snapshot_sha256',
    'analysis_sha256', 'body_bank_sha256', 'skin_reference_choice_request',
    'proposal', 'memory', 'read_only_proposal', 'source_image_load_required',
    'review_required', 'grants_consent', 'render_committed', 'portable', 'report_sha256'))
PROPOSAL_FIELDS = frozenset(('version', 'operation_id', 'control_id', 'method',
    'source', 'source_stage', 'source_pixels_sha256', 'source_kind', 'source_bits',
    'source_encoding', 'state_revision', 'association_revision', 'candidate_scope',
    'census_complete', 'detector_limit_reached', 'candidates', 'read_only_proposal',
    'review_required', 'reference_face_exclusion_required', 'body_extension_enabled',
    'fit_retained', 'portable', 'memory_admission_bytes', 'limitations',
    'reference_face_ref', 'selection_mode', 'automatic_status',
    'automatic_reference_face_ref', 'automatic_blockers', 'ranked_face_refs',
    'top_log_luminance_gap', 'minimum_log_luminance_gap', 'ambiguous_face_refs',
    'proposal_sha256'))


def read_only(message):
    # Identify even malformed reads before any generic recovery-write route.
    return (type(message) is dict and message.get('cmd') == 'people'
            and type(message.get('action')) is str and message['action'] == ACTION)


def check_action(action, payload, target):
    if (action != ACTION or type(payload) is not dict or type(target) is not dict
            or set(target) != {'scope', 'target_id', 'face_ref'}
            or target['scope'] != 'all_people' or target['face_ref'] is not None):
        raise ValueError('Reference choice needs the explicit current photograph, not the editing cursor')
    asset = P.digest(target['target_id'])
    if (set(payload) not in ({'family', 'source_review_sha256'},
                            {'family', 'source_review_sha256', 'manual_reference'})
            or type(payload.get('family')) is not str or payload['family'] not in FAMILIES):
        raise ValueError('Reference choice requires one exact family catalog and optional explicit face')
    P.digest(payload['source_review_sha256'])
    if payload.get('manual_reference') is not None:
        ref = P.check_ref(payload['manual_reference'])
        if ref['asset_sha256'] != asset:
            raise ValueError('Manual reference must belong to this exact current photograph')


def _entry(engine, family, key):
    """Read an existing family store without creating/pruning consent or images."""
    module, name = FAMILIES[family]
    store = engine.__dict__.get(name)
    entry = None if type(store) is not dict else store.get('sources', {}).get(key)
    if (type(entry) is not dict or type(entry.get('expires')) not in (int, float)
            or not math.isfinite(entry['expires'])
            or not time.monotonic() < entry['expires']):
        raise ValueError('Load this family\'s current source catalog before reference choice')
    review = entry.get('source_review')
    if (type(review) is not dict or review.get('operation_id') != module.S.OP
            or FACE.digest(review) != key):
        raise ValueError('Reference choice cannot borrow another family\'s source receipt')
    return module, store, entry


def _analyses(engine, state, asset):
    bank = engine.__dict__.get('_people_analyses')
    if type(bank) is not dict:
        raise ValueError('Reference choice requires the actual current analysis bank')
    analyses = bank.get(asset, {})
    faces = {key: face for key, face in state['faces'].items() if face['asset_sha256'] == asset}
    if len(faces) > CHOICE.MAX_FACES:
        raise ValueError('Reference choice exceeds the complete retained-face bound; no truncation')
    # Validate all supplied current-source rows, never silently select a subset.
    CHOICE._analysis_bytes(analyses, faces)
    return analyses


def _resident_bytes(*roots):
    """Read actual backing storage without decode, tensor transfer or inference.

    Include parked document buffers, retained analyses and preview/source/repair
    fields. Count unique array/tensor storage conservatively; tensors on every
    device are charged, not presumed to be free CPU allocations. Opaque loaded
    model/session objects are covered by available_estimate, not traversed.
    """
    seen = set(); storages = set(); nodes = 0
    torch = sys.modules.get('torch')
    tensor_type = None if torch is None else getattr(torch, 'Tensor', None)
    def size(value, depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 64 or nodes > MAX_RESIDENT_NODES:
            raise ValueError('Reference-choice resident inputs exceed accounting bounds')
        if id(value) in seen:
            return 0
        seen.add(id(value))
        if isinstance(value, (bytes, bytearray)):
            return len(value)
        if isinstance(value, memoryview):
            return size(value.obj, depth + 1)
        if isinstance(value, np.ndarray):
            if type(value) is not np.ndarray:
                raise ValueError('Reference-choice resident array subclass cannot hide backing storage')
            # R.array_bytes charges a tiny view's complete original backing.
            base = value
            while isinstance(base.base, np.ndarray):
                base = base.base
            owner = base if base.base is None else base.base
            key = ('array', id(owner))
            if key in storages:
                return 0
            storages.add(key)
            return R.array_bytes(value)
        if tensor_type is not None and isinstance(value, tensor_type):
            storage = value.untyped_storage()
            count = storage.nbytes()
            if type(count) is not int or count < 0:
                raise ValueError('Reference-choice tensor storage has no exact resident byte count')
            key = ('tensor', str(value.device), storage.data_ptr())
            if key in storages:
                return 0
            storages.add(key)
            return count
        if isinstance(value, dict):
            return sum(size(item, depth + 1) for item in value.values())
        if isinstance(value, (tuple, list, set, frozenset)):
            return sum(size(item, depth + 1) for item in value)
        if is_dataclass(value) and not isinstance(value, type):
            return sum(size(getattr(value, field.name), depth + 1) for field in fields(value))
        # Inspect only product-owned retained stage records, never arbitrary
        # properties, sessions or foreign objects that may run hidden work.
        if (type(value).__module__.startswith('lumaretouch_engine.')
                and hasattr(value, '__dict__')):
            return size(vars(value), depth + 1)
        return 0
    return HOST_FIXED_BYTES + sum(size(value) for value in roots)


def _resident_inputs(engine, state, current, entry):
    # Reading __dict__ avoids property-backed allocation. The supplied state,
    # catalog receipt and current capture may own additional detached buffers.
    roots = [state, current, _live_fields(engine), entry['before'], entry['source_review']]
    roots.extend(engine.__dict__.get(key) for key in (
        '_docs', '_src_rgb', '_people_analyses', '_precompute', '_creative_base', '_vram',
        '_people_support', '_people_landmarks', '_people_active_context',
        '_people_project_context', '_body_pose_bank', '_hair_colour_assets',
        '_hair_unification_assets', '_hair_colour_evidence'))
    return _resident_bytes(*roots)


def _live_fields(engine):
    """Read existing fields only: never call capture to decide if capture fits."""
    names = getattr(type(engine), 'DOC_FIELDS', ())
    return {key: engine.__dict__.get(key) for key in names}


def _metadata_bytes(*roots):
    """Conservative copied-container footprint, without copying its contents."""
    seen = set(); nodes = 0
    def size(value, depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 64 or nodes > MAX_RESIDENT_NODES:
            raise ValueError('Reference-choice snapshot metadata exceeds accounting bounds')
        if id(value) in seen:
            return 0
        seen.add(id(value))
        if isinstance(value, np.ndarray):
            return 0  # Array backing/copies are charged separately.
        if isinstance(value, dict):
            return sys.getsizeof(value) + sum(size(item, depth + 1) for item in value.values())
        if isinstance(value, (list, tuple, set, frozenset)):
            return sys.getsizeof(value) + sum(size(item, depth + 1) for item in value)
        if is_dataclass(value) and not isinstance(value, type):
            return sys.getsizeof(value) + sum(size(getattr(value, field.name), depth + 1) for field in fields(value))
        return 0  # deepcopy shares immutable strings/bytes/numbers.
    return sum(size(root) for root in roots)


def _verification_workspace(engine, state, entry):
    """Reserve family snapshot_key's allocations BEFORE entering its verifier.

    B.bind/restore_missing can own four producer planes per retained face;
    people_snapshot.capture then owns four more, without deduplicating shared
    masks. Sixteen additional largest planes cover producer reductions, float
    conversion, validation scratch and the shared initial bind. Two 478-point
    arrays per face cover restored and frozen landmarks. This is admission, not
    an allocation or a claimed measured peak.
    """
    asset = entry['source_review']['source']['sha256']
    faces = [face for face in state['faces'].values() if face['asset_sha256'] == asset]
    if len(faces) > CHOICE.MAX_FACES:
        raise ValueError('Reference-choice verifier exceeds its complete retained-face bound')
    pc = engine.__dict__.get('_precompute')
    masks = None if pc is None else vars(pc).get('masks')
    masks = {} if masks is None else masks
    if not isinstance(masks, dict):
        raise ValueError('Reference-choice verifier needs bounded actual producer masks')
    plane = 0
    for value in masks.values():
        if value is None:
            continue
        if type(value) is not np.ndarray:
            raise ValueError('Reference-choice verifier cannot budget opaque producer masks')
        plane = max(plane, R.array_bytes(value), int(value.size) * 4)
    live = _live_fields(engine)
    # Context/snapshot validation may independently deepcopy active stores and
    # document records several times. Reserve eight complete copies, including
    # arrays/bytes conservatively even when immutable storage is actually shared.
    copies = [state, live, entry['before'], entry['source_review']]
    copies.extend(engine.__dict__.get(name) for name in (
        '_people_support', '_people_landmarks', '_body_pose_bank', '_hair_colour_assets',
        '_hair_unification_assets', '_hair_colour_evidence'))
    copy_bytes = _resident_bytes(*copies) - HOST_FIXED_BYTES + _metadata_bytes(*copies)
    return VERIFY_FIXED_BYTES + 8 * copy_bytes + (8 * len(faces) + 16) * plane + 2 * len(faces) * 478 * 3 * 4


def _admit_verification(engine, state, entry, admission, *, current=None, held_bytes=0):
    """Reserve snapshot transients independently at every expensive boundary."""
    admission['resident'] = max(admission['resident'], _resident_inputs(engine, state, current, entry))
    admission['verification'] = max(admission['verification'], _verification_workspace(engine, state, entry))
    remaining = min(admission['limit'], available_estimate()) - admission['resident'] - admission['verification']
    if remaining <= held_bytes:
        raise MemoryError('Reference-choice resident inputs and verifier snapshots exceed admission before allocation')
    return remaining


def _guard(engine, state, target, request, store, entry, analysis_key, body_key,
           input_identity, admission, pixels, current):
    module, latest_store, latest = _entry(engine, request['family'], request['source_review_sha256'])
    if latest_store is not store or latest is not entry:
        raise ValueError('Reference-choice source catalog was replaced during measurement')
    _admit_verification(engine, state, entry, admission, current=current, held_bytes=pixels.owned_bytes)
    current = module._verify_source(engine, state, target, entry)
    analyses = _analyses(engine, state, target['target_id'])
    if (fingerprint(analyses) != analysis_key
            or FACE.digest(BODY._body_bank(engine)) != body_key
            or fingerprint(current) != input_identity):
        raise ValueError('Reference-choice complete analysis, repair or body bank changed')
    return current


def _candidate(row, face, source):
    if type(row) is not dict or P.check_ref(row.get('face_ref')) != P.face_ref(face):
        raise ValueError('Reference-choice candidate does not identify its exact retained face')
    status = row.get('status')
    if (status not in ('measured', 'unavailable', 'disabled')
            or (status == 'disabled') != (not face['enabled'])):
        raise ValueError('Reference-choice candidate enabled state changed')
    if status != 'measured':
        keys = {'face_ref', 'status'}
        if 'reason' in row:
            keys.add('reason')
            if row['reason'] not in ('actual-face-analysis-unavailable',
                    'actual-face-analysis-invalid', 'source-measurement-refused'):
                raise ValueError('Reference-choice candidate refusal is not explicit')
            if row['reason'] != 'actual-face-analysis-unavailable':
                keys.add('detail')
                if type(row.get('detail')) is not str:
                    raise ValueError('Reference-choice candidate refusal detail is missing')
        if set(row) != keys or status == 'unavailable' and 'reason' not in row:
            raise ValueError('Reference-choice unmeasured candidate schema changed')
        return
    keys = {'face_ref', 'status', 'measurement', 'source_window', 'support_sha256',
            'evidence', 'landmark_digest', 'face_skin_observation',
            'protected_face_boxes', 'protected_actual_face_ovals'}
    if set(row) != keys:
        raise ValueError('Reference-choice measured candidate schema changed')
    measurement = row['measurement']
    fields = {'log_luminance', 'linear_luminance', 'initial_log_luminance_mad',
              'robust_sample_count', 'robust_weight', 'effective_samples', 'retained_weight_fraction'}
    if (type(measurement) is not dict or set(measurement) != fields
            or any(type(value) not in (int, float) or not math.isfinite(value)
                   for value in measurement.values())
            or type(measurement['robust_sample_count']) is not int
            or measurement['robust_sample_count'] < 1):
        raise ValueError('Reference-choice measured diagnostics are not bounded JSON facts')
    window = row['source_window']
    if type(window) is not list:
        raise ValueError('Reference-choice source window must be an explicit JSON list')
    R._window(tuple(window), (source['height'], source['width']))
    P.digest(row['support_sha256']); P.digest(row['landmark_digest'])
    evidence = FACE.SUPPORT._evidence(row['evidence'], source)
    if evidence != face['evidence'] or row['landmark_digest'] != evidence['landmark_digest']:
        raise ValueError('Reference-choice candidate evidence changed')
    FACE.SUPPORT._observation(row['face_skin_observation'], row['face_ref'], evidence)
    if any(type(row[key]) is not int or not 0 <= row[key] < CHOICE.MAX_FACES
           for key in ('protected_face_boxes', 'protected_actual_face_ovals')):
        raise ValueError('Reference-choice candidate protective-veto count changed')


def _proposal(value, state, source, pixels, manual):
    """Fail closed on helper protocol drift before emitting any proposal."""
    if type(value) is not dict or set(value) != PROPOSAL_FIELDS:
        raise ValueError('Reference-choice measured proposal schema changed')
    expected = {'version': CHOICE.VERSION, 'operation_id': FACE.S.OP,
        'control_id': FACE.S.CONTROL_ID, 'method': CHOICE.METHOD, 'source': source,
        'source_pixels_sha256': pixels.input_sha256, 'source_kind': pixels.kind,
        'source_bits': pixels.source_bits, 'source_encoding': R.N.ENCODING,
        'source_stage': FACE.SUPPORT.SOURCE_STAGE, 'state_revision': state['revision'],
        'association_revision': state['association_revision'],
        'candidate_scope': 'all-enabled-retained-same-source-faces',
        'census_complete': False, 'read_only_proposal': True, 'review_required': True,
        'reference_face_exclusion_required': True, 'body_extension_enabled': False,
        'fit_retained': False, 'portable': False}
    if any(value[key] != expected_value or type(value[key]) is not type(expected_value)
           for key, expected_value in expected.items()):
        raise ValueError('Reference-choice measurement changed its exact source or authority boundary')
    unsigned = {key: item for key, item in value.items() if key != 'proposal_sha256'}
    if FACE.digest(unsigned) != P.digest(value['proposal_sha256']):
        raise ValueError('Reference-choice measured proposal digest changed')
    refs = [P.face_ref(face) for _, face in sorted(state['faces'].items())
            if face['asset_sha256'] == source['sha256']]
    if (type(value['candidates']) is not list
            or any(type(row) is not dict for row in value['candidates'])
            or [row.get('face_ref') for row in value['candidates']] != refs):
        raise ValueError('Reference-choice proposal omitted or substituted a retained source face')
    for row in value['candidates']:
        _candidate(row, state['faces'][row['face_ref']['face_instance_id']], source)
    run = state['analysis_runs'].get(source['sha256'])
    selection = CHOICE._selection(value['candidates'], run, manual)
    if any(value[key] != expected or type(value[key]) is not type(expected)
           for key, expected in selection.items()):
        raise ValueError('Reference-choice selection differs from its disclosed measurements')
    limit = None if run is None else run['limit_reached']
    if (value['detector_limit_reached'] is not limit
            or type(value['memory_admission_bytes']) is not int or value['memory_admission_bytes'] < 1
            or type(value['limitations']) is not list
            or not value['limitations'] or any(type(item) is not str for item in value['limitations'])):
        raise ValueError('Reference-choice proposal limits are missing or inconsistent')
    if manual is not None and (value['reference_face_ref'] != manual
            or value['selection_mode'] != 'manual-override-proposal'):
        raise ValueError('Reference-choice manual override was silently substituted')
    return value


def propose(engine, state, target, payload, *, byte_budget=None, cancelled=lambda: False):
    """Return source-bound JSON facts only, using the already loaded family catalog.

    byte_budget is a host-only total working-set limit, never a wire payload
    permission. Live available memory and actual resident buffers are charged
    before capture can inspect/decode pixels. No proxy or alternative solver.
    Caller owns serialized dispatch and rejection of late request IDs in UI.
    """
    check_action(ACTION, payload, target)
    cancelled = CHOICE._cancellation_probe(cancelled)
    R._poll(cancelled)
    if byte_budget is not None and (type(byte_budget) is not int or byte_budget < 1):
        raise ValueError('Reference choice needs a positive host working byte budget')
    live_limit = available_estimate()
    limit = live_limit if byte_budget is None else min(byte_budget, live_limit)
    if limit <= HOST_FIXED_BYTES + VERIFY_FIXED_BYTES:
        raise MemoryError('Reference-choice host and verifier admission refused before any snapshot allocation')
    request = deepcopy(payload); target = deepcopy(target)
    module, store, entry = _entry(engine, request['family'], request['source_review_sha256'])
    admission = {'limit': limit, 'resident': 0, 'verification': 0}
    _admit_verification(engine, state, entry, admission)
    state = P.check(state)
    if request.get('manual_reference') is not None:
        FACE.SUPPORT._face(state, request['manual_reference'])
    current = module._verify_source(engine, state, target, entry)
    source = deepcopy(entry['source_review']['source'])
    analyses = _analyses(engine, state, target['target_id'])
    analysis_key = fingerprint(analyses)
    body_key = FACE.digest(BODY._body_bank(engine))
    input_identity = fingerprint(current)
    capture_budget = _admit_verification(engine, state, entry, admission, current=current)
    pixels = SOURCE.capture(engine, expected_source=source, byte_budget=capture_budget, cancelled=cancelled)
    R._source_binding(pixels, source['sha256'])
    if pixels.source != source or pixels.input_sha256 != entry['source_review']['source_pixels_sha256']:
        raise ValueError('Reference-choice original pixels differ from the loaded family catalog')
    current = _guard(engine, state, target, request, store, entry, analysis_key, body_key,
                     input_identity, admission, pixels, current)
    R._poll(cancelled)
    # Re-admit after decoding too. Helper includes captured source and all of its
    # own analysis/workspace; double-charged shared analysis is conservative.
    remaining = _admit_verification(engine, state, entry, admission,
                                    current=current, held_bytes=pixels.owned_bytes)
    measured = CHOICE.propose(state, source['sha256'], pixels, analyses,
        byte_budget=remaining, manual_reference=request.get('manual_reference'), cancelled=cancelled)
    measured = _proposal(measured, state, source, pixels, request.get('manual_reference'))
    if pixels.peak_bytes > capture_budget or measured['memory_admission_bytes'] > remaining:
        raise MemoryError('Reference-choice measured working set exceeded its exact host admission')
    # Verify original immutable bytes again, independently of the helper's scalar
    # response and of source-file/creative-proof checks in the family verifier.
    R._validate_source(pixels, cancelled)
    _guard(engine, state, target, request, store, entry, analysis_key, body_key,
           input_identity, admission, pixels, current)
    R._poll(cancelled)
    resident = admission['resident']; verification = admission['verification']
    peak = resident + verification + max(pixels.peak_bytes, measured['memory_admission_bytes'])
    if peak > limit:
        raise MemoryError('Reference-choice final verifier exceeded the admitted complete working set')
    review = entry['source_review']
    result = {'kind': ACTION, 'version': VERSION, 'operation_id': module.S.OP,
        'family': request['family'], 'target': target, 'document_id': review['document_id'],
        'revision': review['revision'], 'source': source, 'source_proof': deepcopy(review['source_proof']),
        'source_review_sha256': request['source_review_sha256'],
        'source_image_sha256': review['source_image']['sha256'],
        'source_pixels_sha256': pixels.input_sha256, 'graph_sha256': FACE.digest(state),
        'document_snapshot_sha256': fingerprint(entry['before_key']),
        'analysis_sha256': analysis_key, 'body_bank_sha256': body_key,
        'skin_reference_choice_request': request, 'proposal': measured,
        'memory': {'resident_input_bytes': resident, 'total_byte_budget': limit,
            'verification_workspace_bytes': verification,
            'capture_byte_budget': capture_budget, 'measurement_byte_budget': remaining,
            'estimated_peak_bytes': peak},
        'read_only_proposal': True, 'source_image_load_required': True,
        'review_required': True, 'grants_consent': False, 'render_committed': False, 'portable': False}
    result['report_sha256'] = FACE.digest(result)
    if set(result) != REPORT_FIELDS:
        raise ValueError('Reference-choice host report schema changed')
    return result
