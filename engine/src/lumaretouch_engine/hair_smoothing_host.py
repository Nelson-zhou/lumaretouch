# SPDX-License-Identifier: GPL-3.0-or-later
"""Current-photo full-pixel hair smoothing review under the existing people transaction.

This adapter does not publish a graph, own receipts/history, replay a source,
segment a hair smoothing, or substitute a proxy. Private records retain JSON identities,
not full float images. AUTHORED / UNRUN; photo/runtime acceptance remains open.
"""
from copy import deepcopy
from contextlib import contextmanager
from dataclasses import dataclass
import uuid
from .hair_colour_assets import digest as hair_digest
from . import people_state as P
from . import hair_smoothing_state as S
from .hair_smoothing_actions import FAMILY, OP, check_action, check_rect
from . import hair_smoothing_review as IMAGES

REFERENCE_KEY = '_hair_smoothing_reference'
PREVIEW_KEY = '_hair_smoothing_preview'
KIND = 'hair_smoothing_visibility'
_PERMIT = '_hair_smoothing_publication_permit'
_ADMISSION = '_hair_smoothing_publication_admission'


def _tags():
    return {'family': FAMILY, 'operation_id': OP}


def _fingerprint(value):
    from .optics_candidate_identity import fingerprint
    return fingerprint(value)


def selected(engine, state, target):
    source = engine._people_source()
    if (target != engine._people_targets.get(source['sha256']) or target.get('scope') != 'face'
            or engine._people_cursors.get(source['sha256']) != target.get('target_id')):
        raise ValueError('Hair smoothing review requires the explicitly selected current-photo face')
    ref = P.check_ref(target['face_ref']); face = state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref or ref['asset_sha256'] != source['sha256']:
        raise ValueError('Hair smoothing review belongs to another selected face or effective source')
    return deepcopy(source), ref


def _single_document(engine, source, row, snapshot):
    from .virtual_copy_people import scope_rows
    from .creative_derived_source import row_asset
    from .face_style_alias_review import verify_dormant
    aliases = [other for other in scope_rows(engine)
               if row_asset({**other, 'state': snapshot} if other is row else other) == source['sha256']]
    if len(aliases) != 1 or aliases[0] is not row:
        raise ValueError('Hair smoothing review is current-photo only; source-identical shared documents need independent ownership')
    verify_dormant(engine, row, {source['sha256']})


def require_geometry(snapshot, state, source):
    """Bounded review mapping: source and output rectangles must be identical.

    This is a new-review gate, NOT a restriction on replaying an already frozen
    source-domain field under the existing common geometry owner. Every known
    geometry family is explicitly audited; a newly registered family fails closed.
    """
    from .ops.geometry import check as crop_check
    from . import final_canvas_flip_state as FLIP, manual_liquify_state as MANUAL
    from . import optics_state as OPTICS, hand_shape_state as HAND, body_pose_render as BODY
    from . import people_algorithms as A, people_resolver as R
    if crop_check(snapshot.get('_crop_rect', (0, 0, 1, 1)), snapshot.get('_crop_rotation', 0)) != (0., 0., 1., 1., 0.):
        raise ValueError('Hair smoothing native crop review requires neutral crop/rotation until exact mapping is available')
    if (FLIP.active(FLIP.from_state(snapshot)) or MANUAL.check(snapshot.get('_manual_liquify'))['strokes']
            or OPTICS.active(snapshot.get('_optics')) or HAND.active(snapshot.get('_hand_shape'))
            or BODY.geometry_record(snapshot) is not None):
        raise ValueError('Hair smoothing review currently requires neutral flip, manual/body/hand geometry and optics')
    geometry = {op: module for op, module in zip(A.GEOMETRY, (A.B, A.N, A.E, A.M))}
    for module in (A.SLIM_FACE, A.FACE_CONTOUR, A.FACE_SIZE, A.LOWER_FACE, A.MID_FACE,
                   A.CHIN_SHAPE, A.CHIN_LENGTH, A.PHILTRUM, A.EYE_SYMMETRY, A.HAIR_VOLUME):
        geometry[module.OP] = module
    audited_texture = (A.BODY_FACE_MATCH, A.BODY_SKIN_EVENNESS, A.COLLARBONE, A.NECK_WRINKLE,
        A.SKIN_EVENNESS, A.EYE_BAG_PRESERVE, A.LIP_TEXTURE, A.BROW_ENHANCE, A.FACIAL_SCULPT,
        A.EYE_MAKEUP_ENHANCE, A.SKIN_TEXTURE, A.SKIN_GLOSS, A.SKIN_FINISH, A.SKIN_COLOUR,
        A.HAIR, A.HAIR_UNIFICATION, A.SKIN_REFERENCE_MATCH, A.SKIN_REFERENCE_BODY,
        A.EYE_LIGHT, A.FACE_DECORATION, A.BLUSH, A.LIPSTICK, A.EYELINER, A.EYELASH, A.IRIS, A.BROW_MAKEUP)
    non_geometry = {S.OP, A.ENHANCE, A.WRINKLES, A.LIP}
    for module in audited_texture:
        operation = getattr(module, 'OP', getattr(module, 'OPERATION', None))
        if not isinstance(operation, str):
            raise ValueError('Hair smoothing review geometry audit has an unclassified operation')
        non_geometry.add(operation)
    if set(A.specifications()) != set(geometry) | {A.DEFORM} | non_geometry:
        raise ValueError('Hair smoothing review requires a new geometry audit for the changed operation registry')
    for key, face in state['faces'].items():
        if face['asset_sha256'] != source['sha256'] or not face['enabled']:
            continue
        resolved = R.resolve(state, key, A.defaults())
        if resolved['conflicts']:
            raise ValueError('Hair smoothing review cannot prove mapping while person intent is ambiguous')
        values = A.recipes(resolved)
        if any(A.D.check_amounts(values[A.DEFORM]).values()) or any(module.active(values[op]) for op, module in geometry.items()):
            raise ValueError('Hair smoothing native crop review needs neutral geometry on every enabled source person')


def _capture(engine, state, target):
    from .virtual_copy_people import current_row
    from .full_candidate_render import identity
    source, ref = selected(engine, state, target)
    row = current_row(engine)
    if row is None:
        raise ValueError('Hair smoothing review has no current document')
    analysis = engine._people_analyses.get(source['sha256'], {}).get(ref['face_instance_id'])
    if type(analysis) is not dict or analysis.get('face_ref') != ref:
        raise ValueError('Hair smoothing review requires actual current-face source analysis')
    snapshot = engine._capture_state(); version = engine._document_versions().version(row)
    _single_document(engine, source, row, snapshot)
    document_id, revision = version.document_id, str(version.revision)
    proof, graph, context = identity(engine, row, snapshot, document_id, revision)
    if graph != state:
        raise ValueError('Hair smoothing people owner changed during capture')
    from . import hair_colour_assets as HAIR, hair_colour_evidence as EVIDENCE
    from .hair_smoothing_support import retained_faces_digest, _manual_owner
    bank = engine.__dict__.get('_hair_colour_assets', {})
    hair = HAIR.resolve(state, bank, ref)
    if hair is None:
        raise ValueError('Review this exact person\'s manual hair ownership before smoothing')
    _manual_owner(hair)
    evidence = EVIDENCE.for_source(engine.__dict__.get('_hair_colour_evidence', {}), source)
    if evidence is None:
        raise ValueError('Hair smoothing requires retained real semantic evidence; no new inference at replay')
    if EVIDENCE.identity(evidence) != hair['semantic_evidence_sha256']:
        raise ValueError('Hair ownership and actual measured semantic evidence differ')
    from .hair_smoothing_support import _owners
    _owners(state, source, bank)  # Refuse unresolved/prompted competing claims before source acquisition.
    retained_faces = retained_faces_digest(state, source['sha256'], bank)
    require_geometry(snapshot, state, source)
    fence = _fingerprint({**_tags(), 'identity': proof, 'source': source, 'target': target,
        'binding': engine._people_binding(), 'hair_bank': bank, 'analysis': analysis, 'graph': state,
        'hair_evidence': EVIDENCE.identity(evidence), 'retained_faces': retained_faces})
    return {'fence': fence, 'source': source, 'ref': ref, 'row': row, 'snapshot': snapshot,
            'context': context, 'bank': bank, 'hair': hair, 'hair_evidence': evidence,
            'retained_faces_sha256': retained_faces, 'analysis': analysis, 'document_id': document_id,
            'revision': revision, 'identity': proof}


def _same_capture(engine, state, target, capture):
    if _capture(engine, state, target)['fence'] != capture['fence']:
        raise ValueError('Hair smoothing source, document, edits, associations or analysis changed; review again')


def _budget(reserve=0):
    from .cpu_memory_budget import available_estimate
    available = available_estimate()
    if type(available) is not int or available <= reserve:
        raise MemoryError('Hair smoothing canonical review exceeds its actual available memory budget')
    return available - reserve


def _resolver(engine, state, capture):
    from .hair_smoothing_source import from_engine
    # Base graph only. Proposed support and amount never replace live ownership.
    return from_engine(engine, state=state, source=capture['source'])


def _source(engine, state, capture, *, reserve=IMAGES.DISPLAY_RESERVE_BYTES, cancelled=None):
    from .hair_smoothing_source import resolve
    return resolve(_resolver(engine, state, capture), face_ref=capture['ref'],
                   source=capture['source'], analysis=capture['analysis'],
                   byte_budget=_budget(reserve), cancelled=cancelled)


def _binding(packet, capture):
    from .creative_derived_source import check_row_proof
    proof = packet.proof
    source_proof = check_row_proof(proof['source_proof'])
    if source_proof['creative_source'] is not None or source_proof['original_sha256'] != capture['source']['sha256']:
        raise ValueError('Hair smoothing source is not an authenticated original; derived composites are unsupported')
    if (proof.get('source') != capture['source']
            or source_proof != capture['identity']['source_proof']
            or source_proof['asset_sha256'] != capture['ref']['asset_sha256']):
        raise ValueError('Hair smoothing canonical pixels and effective source provenance differ')
    P.digest(proof['input_sha256']); P.digest(proof['repair_sha256'])
    rgb = packet.rgb
    if (tuple(rgb.shape) != (capture['source']['height'], capture['source']['width'], 3)
            or str(rgb.dtype) != 'float32' or rgb.flags.writeable
            or type(packet.resident_bytes) is not int or packet.resident_bytes < rgb.nbytes):
        raise ValueError('Hair smoothing source resolver did not provide owned full canonical float32 pixels')
    return {'source': deepcopy(capture['source']), 'source_proof': source_proof,
            'input_sha256': proof['input_sha256'], 'repair_sha256': proof['repair_sha256']}


def _record(engine, key, capture, identifier=None):
    record = engine.__dict__.get(key)
    if (type(record) is not dict or record.get('family') != FAMILY or record.get('operation_id') != OP
            or record.get('fence') != capture['fence'] or record.get('face_ref') != capture['ref']
            or (identifier is not None and record.get('id') != identifier)):
        raise ValueError('Hair smoothing reference/comparison is missing or changed; request a fresh reference')
    return record


def _require_binding(record, binding, proof):
    if record['binding'] != binding or record['source_packet_proof'] != proof:
        raise ValueError('Hair smoothing actual source pixels or repair replay changed after review')


def _candidate(engine, state, capture, packet, review, amount):
    from . import hair_smoothing_support as SUPPORT
    from .people_support_assets import check_store
    review = SUPPORT.check_review(review, source=capture['source'])
    candidate, assets = SUPPORT.retain(state, engine._people_support, capture['ref'],
        capture['bank'], review, packet.proof, capture['retained_faces_sha256'])
    candidate = P.set_override(candidate, 'face', capture['ref']['face_instance_id'], OP, '/amount', amount)
    check_store(assets)
    return candidate, assets


def _diagnostic(engine, state, capture, candidate, assets, amount, expected_proof, *, crop_rect, cancelled=None):
    from .hair_smoothing_layer import prepare_review
    # Reserve source-grid display classification scratch before the detector.
    extra = capture['source']['width'] * capture['source']['height'] * 8
    effects, evidence = prepare_review(capture['ref'], capture['analysis'], {'version': 1, 'amount': amount},
        people_state=candidate, assets=assets, hair_assets=capture['bank'], hair_evidence=capture['hair_evidence'],
        full_source=_resolver(engine, state, capture),
        byte_budget=_budget(IMAGES.DISPLAY_RESERVE_BYTES + extra), cancelled=cancelled)
    if evidence is None or not effects or evidence.source_proof != expected_proof:
        raise ValueError('Hair smoothing diagnostic does not describe the exact prepared canonical source')
    import numpy as np
    x, y, w, h = check_rect(crop_rect, (capture['source']['width'], capture['source']['height']))
    if not np.any(evidence.eligible_mask[y:y+h, x:x+w]):
        raise ValueError('The inspected native source crop does not intersect actual fully eligible owned hair; inspect the target first')
    P.digest(evidence.measurement_key)
    measurement_key = evidence.measurement_key
    diagnostics = {key: evidence.facts['native_report'][key] for key in (
        'supported_pixels', 'context_rejected_pixels', 'directional_pixels', 'changed_pixels', 'no_signal_reason')}
    diagnostics.update(texture_scale_px=evidence.facts['texture_scale_px'], runtime_quality_accepted=False)
    del effects  # No unbudgeted full gain field overlaps the next decode/render.
    packet = _source(engine, state, capture, reserve=IMAGES.DISPLAY_RESERVE_BYTES + extra, cancelled=cancelled)
    binding = _binding(packet, capture)
    if packet.proof != expected_proof:
        raise ValueError('Hair smoothing source changed between measurement and support display')
    image = IMAGES.support_image(packet.rgb, evidence.admitted_weight, evidence.hard_protect,
        evidence.eligible_mask, evidence.window_yxhw, cancelled=cancelled)
    del packet, evidence
    return image, measurement_key, binding, diagnostics


def _render(engine, state, capture, *, candidate=None, assets=None, rect=None,
            measurement_key=None, cancelled=None):
    from .full_candidate_render import render
    options = {'people_graph': state}
    if candidate is not None:
        staged = deepcopy(capture['context']); staged['people_graph'] = candidate
        staged['people_support_assets'] = assets
        options = {'people_graph': candidate, 'staged_people_context': staged}
    rgb, proof = render(engine, capture['row'], capture['snapshot'], capture['document_id'],
                        capture['revision'], cancelled=cancelled or (lambda: False), **options)
    size = [int(rgb.shape[1]), int(rgb.shape[0])]
    canonical_size = [capture['source']['width'], capture['source']['height']]
    if (proof.get('output_size') != size or size != canonical_size or proof.get('source_size') != canonical_size
            or proof.get('source_proof') != capture['identity']['source_proof']):
        raise ValueError('Hair smoothing complete comparison omitted its actual output/source proof')
    from . import people_resolver as RESOLVER
    from .hair_smoothing_state import active, check, neutral
    rendered_graph = P.check(state if candidate is None else candidate)
    expected_faces = set()
    for face in rendered_graph['faces'].values():
        if face['asset_sha256'] != capture['source']['sha256'] or not face['enabled']:
            continue
        resolved = RESOLVER.resolve(rendered_graph, face['face_instance_id'], {OP: {'/amount': 0.}})
        if active(RESOLVER.materialize(resolved, OP, neutral(), check)):
            ref = P.face_ref(face)
            expected_faces.add(tuple(ref[name] for name in ('asset_sha256', 'face_instance_id', 'analysis_revision')))
    # Only an actually inactive rendered graph may omit optional diagnostics.
    # Active before renders and exact candidates must prove every active owner;
    # absent, empty, foreign or stale measurements are never blanket-defaulted.
    if 'hair_smoothing_measurements' not in proof:
        if expected_faces or measurement_key is not None:
            raise ValueError('Hair smoothing active renderer omitted its actual prepared measurement identities')
        measurements = []
    else:
        measurements = proof['hair_smoothing_measurements']
    if type(measurements) is not list or len(measurements) > 4096:
        raise ValueError('Hair smoothing renderer omitted its actual prepared measurement identities')
    seen = set()
    for measured in measurements:
        if type(measured) is not dict or set(measured) != {'face_ref', 'measurement_key'}:
            raise ValueError('Hair smoothing renderer returned invalid measurement provenance')
        checked_ref = P.check_ref(measured['face_ref']); P.digest(measured['measurement_key'])
        key = tuple(checked_ref[name] for name in ('asset_sha256', 'face_instance_id', 'analysis_revision'))
        if key in seen:
            raise ValueError('Hair smoothing renderer returned ambiguous repeated face measurement provenance')
        seen.add(key)
    if seen != expected_faces:
        raise ValueError('Hair smoothing renderer measurement owners do not match the exact active rendered graph')
    if measurement_key is not None and {'face_ref': capture['ref'], 'measurement_key': measurement_key} not in measurements:
        raise ValueError('Hair smoothing actual mixed renderer measured a different source/support/algorithm')
    full_sha = IMAGES.raster_hash(rgb, cancelled=cancelled)
    shown = (IMAGES.full_image(rgb, cancelled=cancelled) if rect is None
             else IMAGES.crop_image(rgb, rect, cancelled=cancelled))
    del rgb
    return shown, {'render': deepcopy(proof), 'raster_sha256': full_sha, 'output_size': size}


def reference(engine, state, target, payload, *, cancelled=None):
    check_action('hair_smoothing_reference', payload, target)
    capture = _capture(engine, state, target)
    packet = _source(engine, state, capture, cancelled=cancelled)
    binding = _binding(packet, capture)
    image = IMAGES.full_image(packet.rgb, cancelled=cancelled)
    proof = deepcopy(packet.proof); del packet
    _same_capture(engine, state, target, capture)
    reference_id = uuid.uuid4().hex
    setattr(engine, PREVIEW_KEY, None)
    setattr(engine, REFERENCE_KEY, {**_tags(), 'id': reference_id, 'fence': capture['fence'],
        'face_ref': capture['ref'], 'binding': binding, 'source_packet_proof': proof, 'source_crop_rect': None, 'source_crop_sha256': None})
    return {'kind': 'reference', **_tags(), 'reference_id': reference_id, **binding,
        'face_ref': capture['ref'],
        'hair_colour_asset_sha256': hair_digest(capture['hair']),
        'ownership_review_key': capture['hair']['review']['review_key'],
        'semantic_evidence_sha256': capture['hair']['semantic_evidence_sha256'],
        'retained_faces_sha256': capture['retained_faces_sha256'], 'source_image': image,
        'attached': KIND in state['faces'][capture['ref']['face_instance_id']]['local_assets']}


def preview(engine, state, target, payload, *, cancelled=None):
    check_action('hair_smoothing_preview', payload, target)
    capture = _capture(engine, state, target)
    reference_record = _record(engine, REFERENCE_KEY, capture)
    if reference_record.get('source_crop_rect') is None or reference_record.get('source_crop_sha256') is None:
        raise ValueError('Inspect actual 1:1 hair smoothing source pixels before reviewing visible scale and protections')
    setattr(engine, PREVIEW_KEY, None)
    packet = _source(engine, state, capture, cancelled=cancelled); binding = _binding(packet, capture)
    _require_binding(reference_record, binding, packet.proof)
    source_proof = deepcopy(packet.proof)
    candidate, assets = _candidate(engine, state, capture, packet, payload['review'], payload['amount'])
    del packet
    support, measurement_key, checked_binding, diagnostics = _diagnostic(engine, state, capture, candidate, assets,
        payload['amount'], source_proof, crop_rect=reference_record['source_crop_rect'], cancelled=cancelled)
    if binding != checked_binding:
        raise ValueError('Hair smoothing support display source changed')
    # The real mixed export pipeline solves its own field from the SAME frozen
    # source/support. No injected local patch or thumbnail overlay is a preview.
    before, before_proof = _render(engine, state, capture, cancelled=cancelled)
    after, after_proof = _render(engine, state, capture, candidate=candidate, assets=assets,
                                 measurement_key=measurement_key, cancelled=cancelled)
    if before_proof['output_size'] != after_proof['output_size']:
        raise ValueError('Hair smoothing comparison unexpectedly changed full output geometry')
    _same_capture(engine, state, target, capture)
    preview_id = uuid.uuid4().hex
    pending = {**_tags(), 'id': preview_id, 'fence': capture['fence'], 'face_ref': capture['ref'],
        'binding': binding, 'source_packet_proof': source_proof, 'review': deepcopy(payload['review']),
        'amount': payload['amount'], 'candidate_sha256': _fingerprint({'state': candidate, 'assets': assets}),
        'measurement_key': measurement_key, 'diagnostics': diagnostics, 'before_proof': before_proof, 'after_proof': after_proof,
        'image_hashes': {'before_sha256': before['sha256'], 'after_sha256': after['sha256'],
                         'support_sha256': support['sha256']}, 'inspection': None,
        'source_crop_rect': deepcopy(reference_record['source_crop_rect']),
        'source_crop_sha256': reference_record['source_crop_sha256']}
    setattr(engine, PREVIEW_KEY, pending)
    return {'kind': 'preview', **_tags(), 'preview_id': preview_id, **binding, 'face_ref': capture['ref'],
        'review': deepcopy(payload['review']), 'amount': payload['amount'], 'before': before, 'after': after,
        'support': support, 'before_output_size': before_proof['output_size'],
        'after_output_size': after_proof['output_size'], 'diagnostics': diagnostics, 'runtime_quality_accepted': False}


def crop(engine, state, target, payload, *, cancelled=None):
    check_action('hair_smoothing_crop', payload, target)
    capture = _capture(engine, state, target); plane = payload['plane']; rect = payload['rect']
    source_crop = plane == 'source'; id_key = 'reference_id' if source_crop else 'preview_id'
    record = _record(engine, REFERENCE_KEY if source_crop else PREVIEW_KEY, capture, payload[id_key])
    size = ([capture['source']['width'], capture['source']['height']] if source_crop
            else record[plane + '_proof']['output_size'])
    check_rect(rect, size)
    if not source_crop and rect != record['source_crop_rect']:
        raise ValueError('Inspect exactly the same native source/output rectangle; geometry must remain identity')
    packet = _source(engine, state, capture, cancelled=cancelled); binding = _binding(packet, capture)
    _require_binding(record, binding, packet.proof)
    if source_crop:
        shown = IMAGES.crop_image(packet.rgb, rect, cancelled=cancelled)
        del packet
    else:
        candidate, assets = _candidate(engine, state, capture, packet, record['review'], record['amount'])
        del packet
        if _fingerprint({'state': candidate, 'assets': assets}) != record['candidate_sha256']:
            raise ValueError('Hair smoothing inspection candidate/support differs from the reviewed rendering')
        options = {'candidate': candidate, 'assets': assets, 'measurement_key': record['measurement_key']} if plane == 'after' else {}
        shown, proof = _render(engine, state, capture, rect=rect, cancelled=cancelled, **options)
        if proof != record[plane + '_proof']:
            raise ValueError('Hair smoothing 1:1 pixels differ from the frozen complete mixed rendering')
    _same_capture(engine, state, target, capture)
    if source_crop:
        record['source_crop_rect'] = list(rect)
        record['source_crop_sha256'] = shown['sha256']
        setattr(engine, PREVIEW_KEY, None)
    else:
        # At most one rectangle and its two PNG hashes. Visiting another rect
        # invalidates the prior pair; no full output buffers are retained.
        inspection = record.get('inspection')
        if type(inspection) is not dict or inspection.get('rect') != rect:
            inspection = {'rect': list(rect)}
        inspection[plane + '_sha256'] = shown['sha256']
        record['inspection'] = inspection
    return {'kind': 'crop', **_tags(), id_key: payload[id_key], 'plane': plane, 'rect': list(rect),
            'domain': 'source' if source_crop else 'rendered_result', **binding, 'image': shown}


def confirm(engine, state, target, payload, *, mark_started=lambda: None, cancelled=None):
    check_action('hair_smoothing_confirm', payload, target)
    capture = _capture(engine, state, target)
    pending = _record(engine, PREVIEW_KEY, capture, payload['preview_id'])
    if any(payload[key] != value for key, value in pending['image_hashes'].items()):
        raise ValueError('Hair smoothing confirmation does not name all three exact full-frame review images')
    if pending.get('inspection') != payload['inspection']:
        raise ValueError('Inspect the same actual 1:1 before/after output rectangle before confirming')
    check_rect(payload['inspection']['rect'], pending['before_proof']['output_size'])
    packet = _source(engine, state, capture, cancelled=cancelled); binding = _binding(packet, capture)
    _require_binding(pending, binding, packet.proof)
    candidate, assets = _candidate(engine, state, capture, packet, pending['review'], pending['amount'])
    del packet
    if _fingerprint({'state': candidate, 'assets': assets}) != pending['candidate_sha256']:
        raise ValueError('Hair smoothing immutable support or face amount differs from the reviewed candidate')
    support, measurement_key, checked_binding, diagnostics = _diagnostic(engine, state, capture, candidate, assets,
        pending['amount'], pending['source_packet_proof'], crop_rect=pending['source_crop_rect'], cancelled=cancelled)
    if (measurement_key != pending['measurement_key'] or checked_binding != binding or diagnostics != pending['diagnostics']
            or support['sha256'] != pending['image_hashes']['support_sha256']):
        raise ValueError('Hair smoothing numerical admission/source changed after the reviewed comparison')
    _same_capture(engine, state, target, capture); IMAGES.poll(cancelled)
    # Append-only immutable assets follow the existing people review seam. The
    # caller ALONE prepares/publishes candidate through the existing people
    # owner/history transaction, and records the outcome in its existing receipt.
    owner = engine._people_owner()
    if owner.snapshot() != state:
        raise ValueError('Hair smoothing graph owner changed before canonical confirmation publication')
    permit = _PublicationPermit(owner, owner.fence, _fingerprint(state), _fingerprint(candidate),
        _fingerprint(assets), deepcopy(target), deepcopy(binding), pending['measurement_key'],
        _fingerprint(capture['snapshot']), _fingerprint(engine._people_binding()),
        _fingerprint(capture['bank']), _fingerprint(capture['analysis']))
    if engine.__dict__.get(_ADMISSION) is not None:
        raise ValueError('Hair smoothing confirmation cannot nest another publication admission')
    mark_started(); engine._people_support = assets
    engine.__dict__[_PERMIT] = permit
    setattr(engine, PREVIEW_KEY, None); setattr(engine, REFERENCE_KEY, None)
    return candidate, {'kind': 'confirmed', **_tags(), 'attached': True, 'amount': pending['amount']}


def detach(engine, state, target, payload):
    check_action('hair_smoothing_detach', payload, target)
    source, ref = selected(engine, state, target)
    from .virtual_copy_people import current_row
    row = current_row(engine)
    if row is None:
        raise ValueError('Hair smoothing detach has no current document')
    _single_document(engine, source, row, engine._capture_state())
    # Intentionally no hair resolution, source decode, model or native core.
    # Local zero masks any inherited value; never erase old recipes/assets or
    # another family's pointer. The existing owner commits both changes at once.
    from .hair_smoothing_support import detach as detach_support
    candidate = P.set_override(state, 'face', ref['face_instance_id'], OP, '/amount', 0.)
    candidate = detach_support(candidate, ref)
    setattr(engine, PREVIEW_KEY, None); setattr(engine, REFERENCE_KEY, None)
    return candidate, {'kind': 'detached', **_tags(), 'attached': False, 'amount': 0.}


def report(engine, state, source, selected_id):
    face = state['faces'].get(selected_id)
    if face is None or face['asset_sha256'] != source['sha256']:
        return None
    ref = P.face_ref(face); attached = KIND in face['local_assets']
    result = {**_tags(), 'attached': attached, 'face_ref': ref, 'source': deepcopy(source),
              'needs_review': False, 'reason': None}
    if attached:
        try:
            from .hair_smoothing_support import resolve
            resolve(state, engine._people_support, ref, engine.__dict__.get('_hair_colour_assets', {}))
        except (ValueError, KeyError, TypeError) as error:
            result.update(needs_review=True, reason=str(error))
    return result


def bound_receipt_payloads(records):
    """Bound images IN the existing receipt owner, without minting a new ledger."""
    remaining = 2
    for row in reversed(records.values()):
        result = row.get('result', row); payload = result.get('payload')
        if (type(payload) is not dict or payload.get('family') != FAMILY
                or payload.get('operation_id') != OP or payload.get('kind') not in ('reference', 'preview', 'crop')):
            continue
        if remaining:
            remaining -= 1
        else:
            result.pop('payload', None); result['payload_released'] = True


@dataclass(frozen=True)
class _PublicationPermit:
    """One exact confirmed candidate, not a transferable/public bypass flag."""
    owner: object
    fence: object
    before_sha256: str
    candidate_sha256: str
    bank_sha256: str
    target: dict
    binding: dict
    measurement_key: str
    snapshot_sha256: str
    document_binding_sha256: str
    hair_bank_sha256: str
    analysis_sha256: str


def _verify_permit(engine, before, candidate, permit):
    if type(permit) is not _PublicationPermit:
        raise ValueError('Hair smoothing activation requires its exact private confirmed publication permit')
    owner = engine._people_owner()
    if (owner is not permit.owner or owner.fence != permit.fence
            or _fingerprint(before) != permit.before_sha256
            or _fingerprint(owner.snapshot()) != permit.before_sha256
            or _fingerprint(candidate) != permit.candidate_sha256
            or _fingerprint(engine._people_support) != permit.bank_sha256):
        raise ValueError('Hair smoothing confirmed graph, bank or canonical owner changed before publication')
    source, _ = selected(engine, before, permit.target)
    if source != permit.binding['source']:
        raise ValueError('Hair smoothing confirmed effective source changed before publication')
    from .virtual_copy_people import current_row
    row = current_row(engine)
    if row is None:
        raise ValueError('Hair smoothing confirmed document is no longer current')
    snapshot = engine._capture_state()
    analysis = engine._people_analyses.get(source['sha256'], {}).get(permit.target['target_id'])
    if (_fingerprint(snapshot) != permit.snapshot_sha256
            or _fingerprint(engine._people_binding()) != permit.document_binding_sha256
            or _fingerprint(engine.__dict__.get('_hair_colour_assets', {})) != permit.hair_bank_sha256
            or _fingerprint(analysis) != permit.analysis_sha256):
        raise ValueError('Hair smoothing document, repair, hair ownership or measured analysis changed before publication')
    _single_document(engine, source, row, snapshot)
    require_geometry(snapshot, before, source)


def verify_before_publish(engine, before, candidate):
    """Existing transaction's final fence, after preparation but before commit."""
    permit = engine.__dict__.get(_ADMISSION)
    if permit is not engine.__dict__.get(_PERMIT):
        raise ValueError('Hair smoothing publication is outside its exact confirmation context')
    _verify_permit(engine, before, candidate, permit)


@contextmanager
def reviewed_transition(engine, before, candidate):
    """Activate only confirm's exact permit around existing canonical publish.

    Parent must wrap its existing publish call in this context manager and call
    require_transition from _people_prepare_graph. No new graph/history owner.
    """
    if engine.__dict__.get(_ADMISSION) is not None:
        raise ValueError('Hair smoothing reviewed publication cannot nest another admission')
    permit = engine.__dict__.get(_PERMIT)
    try:
        _verify_permit(engine, before, candidate, permit)
        engine.__dict__[_ADMISSION] = permit
        yield
    finally:
        engine.__dict__.pop(_ADMISSION, None)
        engine.__dict__.pop(_PERMIT, None)


def discard_publication(engine):
    """Existing failed-request/reset cleanup, not a receipt or rollback owner."""
    engine.__dict__.pop(_ADMISSION, None)
    engine.__dict__.pop(_PERMIT, None)


def _hair_smoothing_signature(graph):
    """Only hair smoothing intent/support and its actual active ownership, never other ops."""
    from .hair_smoothing_project import validate_leaf, require_face_scope
    from .people_resolver import resolve
    rows = {}
    for row in graph['overrides']:
        if row['operation_id'] != OP:
            continue
        require_face_scope(row['scope']); validate_leaf(row['parameter_path'], row['value'])
        rows.setdefault(row['target_id'], []).append(deepcopy(row))
    result = {}
    for identity, face in graph['faces'].items():
        local_rows = rows.get(identity, [])
        support = face['local_assets'].get(KIND)
        if not local_rows and support is None:
            continue
        resolved = resolve(graph, identity, {OP: {'/amount': 0.}})
        if any(row['operation_id'] == OP for row in resolved['conflicts']):
            raise ValueError('Hair smoothing ownership transition cannot hide an unresolved amount conflict')
        amount = resolved['operations'][OP]['/amount']['value']
        active_owner = None
        if amount > 0:
            links = [deepcopy(link) for link in graph['links']
                     if link['face_instance_id'] == identity and link['state'] == 'confirmed']
            links.sort(key=lambda link: link['person_id'])
            active_owner = {'enabled': face['enabled'], 'association_revision': graph['association_revision'],
                'links': links, 'persons': {link['person_id']: deepcopy(graph['persons'][link['person_id']])
                                          for link in links}}
        result[identity] = {'face_ref': P.face_ref(face), 'evidence': deepcopy(face['evidence']),
            'support': deepcopy(support), 'rows': sorted(local_rows, key=lambda row: row['parameter_path']),
            'amount': amount, 'active_owner': active_owner}
    return result


def require_transition(engine, before, candidate):
    """Reject bypass activation/rebinding while preserving unrelated graph edits.

    Outside an exact confirmation admission only an explicit current-face zero
    (with optional own pointer removal) is allowed. It needs no model/core.
    Canonical history restoration must keep its existing separate restore owner;
    this function does not manufacture a generic undo/preset/import authority.
    """
    left, right = _hair_smoothing_signature(before), _hair_smoothing_signature(candidate)
    if left == right:
        return candidate
    permit = engine.__dict__.get(_ADMISSION)
    if permit is not None:
        if permit is not engine.__dict__.get(_PERMIT):
            raise ValueError('Hair smoothing publication admission lost its exact confirmation identity')
        _verify_permit(engine, before, candidate, permit)
        return candidate
    source = engine._people_source(); target = engine._people_targets.get(source['sha256'])
    if type(target) is not dict:
        raise ValueError('Hair smoothing neutral recovery requires the exact selected current face')
    source, ref = selected(engine, before, target)
    from .virtual_copy_people import current_row
    row = current_row(engine)
    if row is None:
        raise ValueError('Hair smoothing neutral recovery requires the current document')
    _single_document(engine, source, row, engine._capture_state())
    neutral = P.set_override(before, 'face', ref['face_instance_id'], OP, '/amount', 0.)
    from .hair_smoothing_support import detach as detach_support
    detached = detach_support(neutral, ref)
    if right not in (_hair_smoothing_signature(neutral), _hair_smoothing_signature(detached)):
        raise ValueError('Hair smoothing activation, support or ownership changes require their own reviewed confirmation; only explicit local zero is direct')
    return candidate
