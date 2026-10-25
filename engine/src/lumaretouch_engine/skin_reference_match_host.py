# SPDX-License-Identifier: GPL-3.0-or-later
"""Current-photo selected-reference review through the canonical people owner.

AUTHORED / UNRUN. Source display and complete mixed before/after images are
session-only reductions. No copied pixels, fit, masks, donor identity or review
token enter portable recipes. No separate root command, ledger or graph owner.
"""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import base64
import io
import json
import re
import time
import uuid

from . import people_state as P, creative_derived_source as SOURCE
from . import skin_reference_match_state as S, skin_reference_match_support as SUPPORT
from . import skin_reference_match_project as PROJECT
from .portrait_review_render import image as render_image, snapshot_key, preview_size, MAX_PNG_BYTES
from .optics_candidate_identity import fingerprint

READS = frozenset(('skin_reference_match_catalog', 'skin_reference_match_preview', 'skin_reference_match_image'))
ACTIONS = READS | {'skin_reference_match_confirm', 'skin_reference_match_clear'}
MAX_REVIEWS = 4
MAX_FACES = 64
TTL = 1800


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                            ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def read_only(message):
    # Malformed read requests must not accidentally route through recovery writes.
    return (type(message) is dict and message.get('cmd') == 'people'
            and type(message.get('action')) is str and message['action'] in READS)


def check_action(action, payload, target):
    if (action not in ACTIONS or type(payload) is not dict or type(target) is not dict
            or set(target) != {'scope', 'target_id', 'face_ref'}
            or target['scope'] != 'all_people' or target['face_ref'] is not None):
        raise ValueError('Skin-reference review needs the explicit current photograph, not the editing cursor')
    asset = P.digest(target['target_id'])
    if action in ('skin_reference_match_catalog', 'skin_reference_match_clear'):
        if payload:
            raise ValueError('Skin-reference catalog/clear accepts no implicit donor or target')
    elif action == 'skin_reference_match_preview':
        if (set(payload) != {'version', 'reference_face_ref', 'target_face_refs', 'amount',
                            'source_review_sha256', 'ownership_confirmed'}
                or type(payload['version']) is not int or payload['version'] != 1
                or payload['ownership_confirmed'] is not True):
            raise ValueError('Confirm the exact source overlay and explicit reference/target ownership first')
        P.digest(payload['source_review_sha256'])
        reference = P.check_ref(payload['reference_face_ref'])
        refs = payload['target_face_refs']
        if type(refs) is not list or not 1 <= len(refs) <= MAX_FACES - 1:
            raise ValueError('Select a bounded nonempty complete target-face set')
        refs = [P.check_ref(ref) for ref in refs]
        ids = [ref['face_instance_id'] for ref in refs]
        if (len(set(ids)) != len(ids) or reference['face_instance_id'] in ids
                or reference['asset_sha256'] != asset
                or any(ref['asset_sha256'] != asset for ref in refs)):
            raise ValueError('Reference and unique targets must be distinct faces from this exact photograph')
        if not S.active(S.check({'version': 1, 'amount': payload['amount']})):
            raise ValueError('Use clear for neutral matching; preview needs a positive amount')
    else:
        if type(payload.get('token')) is not str or re.fullmatch('[0-9a-f]{32}', payload['token']) is None:
            raise ValueError('Skin-reference review needs its exact unexpired session token')
        if action == 'skin_reference_match_image':
            if set(payload) != {'token', 'side', 'sha256', 'review_sha256'} or payload['side'] not in ('before', 'after'):
                raise ValueError('Load the exact skin-reference image side and proof')
            P.digest(payload['sha256']); P.digest(payload['review_sha256'])
        else:
            ack = payload.get('ack')
            if (set(payload) != {'token', 'ack'} or type(ack) is not dict
                    or set(ack) != {'review_sha256', 'before_sha256', 'after_sha256'}):
                raise ValueError('Acknowledge this exact fully loaded before/after image pair')
            for value in ack.values():
                P.digest(value)


def _store(engine):
    store = engine.__dict__.get('_skin_reference_match_reviews')
    if store is None:
        # Reuse only immutable blob I/O. This operation owns every proof/token.
        from .collarbone_visual_store import _Images
        store = {'pending': OrderedDict(), 'sources': OrderedDict(),
                 'images': _Images(records=lambda plan: plan.records)}
        engine._skin_reference_match_reviews = store
    now = time.monotonic()
    for collection in ('pending', 'sources'):
        for token, entry in list(store[collection].items()):
            if now >= entry['expires']:
                del store[collection][token]
    store['images'].prune({token: entry for token, entry in store['pending'].items() if not entry['claimed']})
    return store


def _live(engine, state, target, *, strict=True):
    from .people_preset_plan import require_active_owner
    from .virtual_copy_people import current_row, scope_rows
    owner = require_active_owner(engine); row = current_row(engine)
    if owner.snapshot() != state:
        raise ValueError('Skin-reference graph changed')
    PROJECT.validate_graph(state)
    current = engine._people_preset_capture()
    proof = SOURCE.row_proof({**row, 'state': current})
    source = SOURCE.binding(current, row['path'], (row['src_w'], row['src_h']))
    if target != {'scope': 'all_people', 'target_id': proof['asset_sha256'], 'face_ref': None} or source['sha256'] != proof['asset_sha256']:
        raise ValueError('Skin-reference selection belongs to another effective source')
    if strict:
        aliases = [other for other in scope_rows(engine, row)
                   if SOURCE.row_asset({**other, 'state': current} if other is row else other) == source['sha256']]
        if len(aliases) != 1 or aliases[0] is not row:
            raise ValueError('Skin-reference current-photo review cannot authorize unseen source-identical documents')
        from .face_style_alias_review import verify_dormant
        verify_dormant(engine, row, {source['sha256']})
    SOURCE.verify_row({**row, 'state': current}, proof)
    return owner, row, current, proof, source, engine._document_versions().version(row)


def _analysis(engine, state, ref):
    ref, face = SUPPORT._face(state, ref)
    analysis = engine.__dict__.get('_people_analyses', {}).get(ref['asset_sha256'], {}).get(ref['face_instance_id'])
    SUPPORT._analysis(face, analysis)
    return analysis


def _analysis_key(engine, state, refs):
    rows = []
    for ref in refs:
        analysis = _analysis(engine, state, ref)
        rows.append({key: analysis[key] for key in
            ('face_ref', 'evidence', 'landmarks', 'face_skin', 'face_skin_observation', 'excluded')})
    return fingerprint(rows)


def report(engine, state=None):
    if state is None:
        from .people_preset_plan import require_active_owner
        state = require_active_owner(engine).snapshot()
    asset = engine._people_source()['sha256']; refs = PROJECT.active_refs(state, asset)
    bank = engine.__dict__.get('_people_support', {})
    reference = SUPPORT.validate_active(state, bank, refs)
    return {'version': 1, 'operation_id': S.OP, 'bank_sha256': digest(bank),
        'reference_face_ref': reference, 'target_face_refs': deepcopy(refs),
        'amounts': [{'face_ref': deepcopy(ref), 'amount': PROJECT.recipe(state, ref['face_instance_id'])['amount'],
                     'support_sha256': state['faces'][ref['face_instance_id']]['local_assets'][SUPPORT.KIND]['content_sha256']}
                    for ref in refs]}


def _source_display(engine, source):
    """Real full immutable source, reduced once for selection UI only."""
    from .portrait_fit_source import capture
    from .cpu_memory_budget import available_estimate
    from PIL import Image
    import numpy as np
    captured = capture(engine, expected_source=source, byte_budget=max(0, available_estimate() - 64 * 1024**2))
    size = preview_size([source['width'], source['height']]); channels = []
    pixels = captured.pixels
    for channel in range(3):
        with Image.fromarray(pixels[:, :, channel]) as plane:
            with plane.resize(size, Image.Resampling.LANCZOS) as small:
                channels.append(np.asarray(small).copy())
    with Image.fromarray(np.rint(np.clip(np.stack(channels, axis=2), 0, 1)*255).astype(np.uint8), 'RGB') as display:
        output = io.BytesIO(); display.save(output, format='PNG'); raw = output.getvalue()
    if len(raw) > MAX_PNG_BYTES:
        raise ValueError('Skin-reference source display exceeds its bounded transport; no hidden face omission')
    return {'mime': 'image/png', 'width': size[0], 'height': size[1],
            'sha256': sha256(raw).hexdigest(), 'base64': base64.b64encode(raw).decode('ascii')}, captured.input_sha256


def catalogue(engine, state, target, payload):
    check_action('skin_reference_match_catalog', payload, target)
    owner, row, current, source_proof, source, version = _live(engine, state, target)
    selected = [(key, face) for key, face in sorted(state['faces'].items()) if face['asset_sha256'] == source['sha256']]
    if len(selected) > MAX_FACES:
        raise ValueError('Skin-reference source overlay exceeds its complete face bound; no face was omitted')
    fence = owner.fence; before_key = snapshot_key(engine, row, current, state)
    faces = []; available = []
    for key, face in selected:
        ref = P.face_ref(face); reason = None
        try:
            if (face['evidence']['source_width'], face['evidence']['source_height']) != (source['width'], source['height']):
                raise ValueError('Skin-reference face evidence belongs to different canonical source dimensions')
            _analysis(engine, state, ref)
        except (ValueError, TypeError, KeyError) as exc:
            reason = str(exc)
        if reason is None:
            available.append(ref)
        faces.append({'face_ref': ref, 'box': deepcopy(face['box']), 'enabled': face['enabled'],
                      'available': reason is None, 'reason': reason, 'amount': PROJECT.recipe(state, key)['amount']})
    analysis_key = _analysis_key(engine, state, available)
    source_image, input_sha256 = _source_display(engine, source)
    compact = {key: value for key, value in source_image.items() if key != 'base64'}
    source_review = {'version': 1, 'operation_id': S.OP, 'document_id': version.document_id,
        'revision': str(version.revision), 'source': source, 'source_proof': source_proof,
        'graph_sha256': digest(state), 'analysis_sha256': analysis_key, 'source_pixels_sha256': input_sha256,
        'source_image': compact, 'faces': faces}
    key = digest(source_review)
    entry = {'owner': owner, 'row': row, 'path': row['path'], 'load_id': engine._load_id, 'fence': fence,
        'target': deepcopy(target), 'before': deepcopy(state), 'before_key': before_key,
        'source_review': source_review, 'available': available, 'expires': time.monotonic() + TTL}
    _verify_source(engine, state, target, entry)
    store = _store(engine)
    while len(store['sources']) >= MAX_REVIEWS:
        store['sources'].popitem(last=False)
    store['sources'][key] = entry
    return {'kind': 'skin_reference_match_catalog', 'version': 1, 'operation_id': S.OP,
        'scope': 'current-photo-face-only', 'source': source, 'source_proof': source_proof,
        'document_id': version.document_id, 'revision': str(version.revision),
        'source_image': source_image, 'source_review_sha256': key, 'faces': faces,
        'current': report(engine, state), 'body_matching': False, 'automatic_reference': False, **S.capability()}


def _verify_source(engine, state, target, entry):
    owner, row, current, proof, source, version = _live(engine, state, target)
    review = entry['source_review']
    if (owner is not entry['owner'] or owner.fence != entry['fence'] or row is not entry['row']
            or row['path'] != entry['path'] or engine._load_id != entry['load_id'] or target != entry['target']
            or state != entry['before'] or source != review['source'] or proof != review['source_proof']
            or version.document_id != review['document_id'] or str(version.revision) != review['revision']
            or snapshot_key(engine, row, current, state) != entry['before_key']
            or _analysis_key(engine, state, entry['available']) != review['analysis_sha256']):
        raise ValueError('Skin-reference source overlay or complete document changed; reload the catalog')
    return current


def _reset(state, asset):
    candidate = PROJECT.validate_graph(state)
    ids = {key for key, face in state['faces'].items() if face['asset_sha256'] == asset}
    touched = {row['target_id'] for row in candidate['overrides']
               if row['operation_id'] == S.OP and row['scope'] == 'face' and row['target_id'] in ids}
    candidate['overrides'] = [row for row in candidate['overrides']
        if not (row['operation_id'] == S.OP and row['scope'] == 'face' and row['target_id'] in ids)]
    for key in ids:
        if SUPPORT.KIND in candidate['faces'][key]['local_assets']:
            touched.add(key); del candidate['faces'][key]['local_assets'][SUPPORT.KIND]
    return candidate, [P.face_ref(state['faces'][key]) for key in sorted(touched)]


def _stage(engine, state, payload, source, bank):
    # Atomically replace the complete prior operation target set, including
    # dormant disabled rows, never leave old targets using a different donor.
    candidate, _ = _reset(state, source['sha256'])
    reference = payload['reference_face_ref']; reference_analysis = _analysis(engine, state, reference)
    staged = deepcopy(bank)
    for ref in payload['target_face_refs']:
        candidate, staged = SUPPORT.retain(candidate, staged, ref, reference,
            _analysis(engine, state, ref), reference_analysis, confirmed=True)
        candidate = P.set_override(candidate, 'face', ref['face_instance_id'], S.OP, '/amount', payload['amount'])
    candidate['revision'] = state['revision'] + 1
    candidate = PROJECT.validate_owned_graph(candidate, staged)
    refs = PROJECT.active_refs(candidate, source['sha256'])
    if {ref['face_instance_id'] for ref in refs} != {ref['face_instance_id'] for ref in payload['target_face_refs']}:
        raise ValueError('Skin-reference candidate omitted or inherited an unreviewed target')
    SUPPORT.validate_active(candidate, staged, refs, engine._people_analyses[source['sha256']])
    return candidate, staged


def _context(engine, row, candidate, bank, expected_bank):
    from .full_candidate_render import people_context
    context = people_context(engine, row)
    if context['people_support_assets'] != expected_bank:
        raise ValueError('Skin-reference canonical support bank changed')
    context['people_graph'] = deepcopy(candidate); context['people_support_assets'] = deepcopy(bank)
    return context


def _plan(review):
    visual = review['visual']
    return SimpleNamespace(token=review['token'], records={visual['document_id']: visual})


def _ack(review):
    return {'review_sha256': review['review_sha256'], 'before_sha256': review['visual']['before']['sha256'],
            'after_sha256': review['visual']['after']['sha256']}


def _proof(review):
    return {'kind': 'skin_reference_match_confirm', **{key: deepcopy(review[key]) for key in
        ('token', 'review_sha256', 'reference_face_ref', 'target_face_refs', 'amount',
         'candidate_state_revision', 'support_sha256', 'candidate_bank_sha256')}, 'ack': _ack(review)}


def _entry(engine, token):
    store = _store(engine); entry = store['pending'].get(token)
    if entry is None:
        raise ValueError('Skin-reference review expired or was replaced; preview again')
    return store, entry


def _verify(engine, state, target, entry, *, installed=False):
    owner, row, current, source_proof, source, version = _live(engine, state, target)
    review = entry['review']; visual = review['visual']; expected = entry['assets'] if installed else entry['before_assets']
    if (entry['claimed'] or owner is not entry['owner'] or owner.fence != entry['fence']
            or row is not entry['row'] or row['path'] != entry['path'] or engine._load_id != entry['load_id']
            or state != entry['before'] or target != entry['target'] or source != review['source']
            or source_proof != visual['source_proof'] or version.document_id != visual['document_id']
            or str(version.revision) != visual['revision'] or engine._people_support != expected
            or fingerprint(current) != entry['recipe_sha256']
            or _analysis_key(engine, state, [review['reference_face_ref'], *review['target_face_refs']]) != entry['analysis_sha256']
            or review['review_sha256'] != digest({key: value for key, value in review.items() if key != 'review_sha256'})):
        raise ValueError('Skin-reference source, repair, ownership, support or complete recipe changed; preview again')
    if not installed and snapshot_key(engine, row, current, state) != entry['before_key']:
        raise ValueError('Skin-reference before recipe/context changed')
    context = _context(engine, row, entry['candidate'], entry['assets'], expected)
    if snapshot_key(engine, row, current, entry['candidate'], staged_people_context=context) != entry['after_key']:
        raise ValueError('Skin-reference complete candidate context changed')
    PROJECT.validate_owned_graph(entry['candidate'], entry['assets'])
    return current


def preview(engine, state, target, payload):
    from .people_transfer_inventory import proof
    check_action('skin_reference_match_preview', payload, target)
    store = _store(engine); source_entry = store['sources'].get(payload['source_review_sha256'])
    if source_entry is None or digest(source_entry['source_review']) != payload['source_review_sha256']:
        raise ValueError('Load this operation\'s exact source overlay before selecting faces')
    _verify_source(engine, state, target, source_entry)
    if any(ref not in source_entry['available'] for ref in [payload['reference_face_ref'], *payload['target_face_refs']]):
        raise ValueError('Select only faces verified as available in this exact source overlay')
    owner, row, current, source_proof, source, version = _live(engine, state, target)
    before_assets = deepcopy(engine._people_support)
    # Strict before validation/render occurs independently from staged consent.
    PROJECT.validate_owned_graph(state, before_assets)
    candidate, assets = _stage(engine, state, payload, source, before_assets)
    PROJECT.require_scope(engine, state, candidate)
    context = _context(engine, row, candidate, assets, before_assets)
    before_key = snapshot_key(engine, row, current, state)
    after_key = snapshot_key(engine, row, current, candidate, staged_people_context=context)
    a, left, pa = render_image(engine, row, current, state, version.document_id, version.revision)
    b, right, pb = render_image(engine, row, current, candidate, version.document_id, version.revision, staged_people_context=context)
    if (pa['source_proof'] != source_proof or pb['source_proof'] != source_proof
            or pa['source_size'] != [source['width'], source['height']] or pa['source_size'] != pb['source_size']
            or pa['output_size'] != pb['output_size']):
        raise ValueError('Skin-reference complete before/after changed source or output geometry')
    token = uuid.uuid4().hex
    visual = {'version': 1, 'document_id': version.document_id, 'revision': str(version.revision), 'source_proof': source_proof,
        'source_size': pa['source_size'], 'before_output_size': pa['output_size'], 'after_output_size': pb['output_size'],
        'before_state_sha256': pa['candidate_sha256'], 'candidate_state_sha256': pb['candidate_sha256'],
        'before_people_sha256': pa['people_sha256'], 'candidate_people_sha256': pb['people_sha256'], 'before': a, 'after': b}
    refs = deepcopy(payload['target_face_refs'])
    review = {'version': 1, 'token': token, 'operation_id': S.OP,
        'owner': proof(engine, row, state, source_row={**row, 'state': current}), 'source': source,
        'reference_face_ref': deepcopy(payload['reference_face_ref']), 'target_face_refs': refs,
        'amount': S.check({'version': 1, 'amount': payload['amount']})['amount'],
        'source_review_sha256': payload['source_review_sha256'],
        'before_target_face_refs': PROJECT.active_refs(state, source['sha256']),
        'candidate_state_revision': candidate['revision'], 'before_bank_sha256': digest(before_assets),
        'candidate_bank_sha256': digest(assets), 'support_sha256': {ref['face_instance_id']:
            candidate['faces'][ref['face_instance_id']]['local_assets'][SUPPORT.KIND]['content_sha256'] for ref in refs},
        'visual': visual}
    review['review_sha256'] = digest(review)
    entry = {'owner': owner, 'row': row, 'path': row['path'], 'load_id': engine._load_id, 'fence': owner.fence,
        'target': deepcopy(target), 'before': deepcopy(state), 'candidate': candidate,
        'before_assets': before_assets, 'assets': assets, 'before_key': before_key, 'after_key': after_key,
        'recipe_sha256': fingerprint(current), 'analysis_sha256': _analysis_key(engine, state, [payload['reference_face_ref'], *refs]),
        'review': review, 'expires': time.monotonic() + TTL, 'claimed': False, 'served': set()}
    _verify_source(engine, state, target, source_entry); _verify(engine, state, target, entry)
    while len(store['pending']) >= MAX_REVIEWS:
        store['pending'].popitem(last=False)
    store['images'].prune(store['pending'])
    store['images'].attach(_plan(review), {version.document_id: {'revision': str(version.revision), 'before': left, 'after': right}})
    store['pending'][token] = entry
    return {'kind': 'skin_reference_match_preview', 'review': deepcopy(review)}


def image(engine, state, target, payload):
    check_action('skin_reference_match_image', payload, target)
    store, entry = _entry(engine, payload['token']); _verify(engine, state, target, entry)
    review = entry['review']; visual = review['visual']; side = payload['side']
    if payload['review_sha256'] != review['review_sha256'] or payload['sha256'] != visual[side]['sha256']:
        raise ValueError('Skin-reference image differs from the exact frozen review')
    pixels = store['images'].read(_plan(review), visual['document_id'], visual['revision'], side, payload['sha256'])
    _verify(engine, state, target, entry); entry['served'].add(side)
    return {'kind': 'skin_reference_match_image', **deepcopy(payload), 'image': pixels}


def _available(store, entry):
    if entry['served'] != {'before', 'after'}:
        raise ValueError('Load both exact skin-reference before/after images before confirming')
    review = entry['review']; visual = review['visual']
    for side in ('before', 'after'):
        store['images'].read(_plan(review), visual['document_id'], visual['revision'], side, visual[side]['sha256'])


def confirm(engine, state, target, payload):
    check_action('skin_reference_match_confirm', payload, target)
    store, entry = _entry(engine, payload['token']); _verify(engine, state, target, entry)
    if payload['ack'] != _ack(entry['review']):
        raise ValueError('Confirm the exact loaded skin-reference full-image pair')
    _available(store, entry); _verify(engine, state, target, entry)
    return deepcopy(entry['candidate']), _proof(entry['review'])


def clear(engine, state, target, payload):
    check_action('skin_reference_match_clear', payload, target)
    _, _, _, _, source, _ = _live(engine, state, target)
    candidate, cleared = _reset(state, source['sha256'])
    if not cleared:
        raise ValueError('This photograph has no skin-reference matching to clear')
    candidate['revision'] = state['revision'] + 1
    PROJECT.require_unreviewed_transition(state, candidate)
    return candidate, {'kind': 'skin_reference_match_clear', 'candidate_state_revision': candidate['revision'], 'cleared_face_refs': cleared}


def publish(engine, state, target, payload, candidate, proof, request_id, mark_started=lambda: None):
    """Wrap existing people publication, never duplicate its rollback/history owner."""
    from .people_host_commands import publish as people_publish
    if proof.get('kind') == 'skin_reference_match_clear':
        owner, row, current, source_proof, _, version = _live(engine, state, target)
        expected, expected_proof = clear(engine, state, target, payload)
        if candidate != expected or proof != expected_proof:
            raise ValueError('Skin-reference clear differs from the exact current-photo reset')
        fence = owner.fence; revision = version.revision; before_key = snapshot_key(engine, row, current, state)
        def reset_before():
            live = _live(engine, state, target)
            if live[0] is not owner or owner.fence != fence or live[1] is not row or snapshot_key(engine, row, live[2], state) != before_key:
                raise ValueError('Skin-reference reset changed source or complete recipe before publication')
            mark_started()
        result = people_publish(engine, state, candidate, request_id, shared=False, before_publish=reset_before)
        if owner.snapshot() != candidate or owner.fence != fence + 1 or engine._document_versions().version(row).revision != revision + 1:
            raise ValueError('Skin-reference reset outcome differs from the canonical publication; inspect the existing request')
        SOURCE.verify_row({**row, 'state': engine._people_preset_capture()}, source_proof)
        return result
    store, entry = _entry(engine, payload['token']); _verify(engine, state, target, entry)
    if candidate != entry['candidate'] or proof != _proof(entry['review']) or payload['ack'] != _ack(entry['review']):
        raise ValueError('Skin-reference publication differs from the exact reviewed candidate and acknowledgment')
    _available(store, entry)
    # Append-only immutable metadata may remain unused after failed preparation;
    # it is never a successful graph/history edit and is needed by old receipts.
    engine._people_support = deepcopy(entry['assets'])
    def before_publish():
        _verify(engine, state, target, entry, installed=True); _available(store, entry)
        mark_started(); entry['claimed'] = True
    with PROJECT.reviewed_transition(engine, state, candidate, entry['assets'], proof['review_sha256']):
        result = people_publish(engine, state, candidate, request_id, shared=False, before_publish=before_publish)
    verify_after_publish(engine, candidate, proof)
    return result


def verify_after_publish(engine, candidate, proof):
    from .people_preset_plan import require_active_owner
    from .virtual_copy_people import current_row
    owner = require_active_owner(engine)
    if proof.get('kind') == 'skin_reference_match_clear':
        if owner.snapshot() != candidate:
            raise ValueError('Skin-reference reset does not match the canonical graph')
        return
    _, entry = _entry(engine, proof['token']); review = entry['review']; row = current_row(engine)
    version = engine._document_versions().version(row); current = engine._people_preset_capture()
    if (not entry['claimed'] or owner is not entry['owner'] or owner.fence != entry['fence'] + 1
            or row is not entry['row'] or row['path'] != entry['path'] or engine._load_id != entry['load_id']
            or version.document_id != review['visual']['document_id'] or version.revision != int(review['visual']['revision']) + 1
            or candidate != entry['candidate'] or owner.snapshot() != candidate or proof != _proof(review)
            or engine._people_support != entry['assets'] or snapshot_key(engine, row, current, candidate) != entry['after_key']):
        raise ValueError('Skin-reference outcome differs from its full reviewed source/graph; inspect the existing request')
    SOURCE.verify_row({**row, 'state': current}, review['visual']['source_proof'])


def bound_receipt_images(records):
    """Bound display receipts while preserving their original request identities."""
    remaining = {'skin_reference_match_image': 2, 'skin_reference_match_catalog': 1}
    for row in reversed(records.values()):
        saved = row.get('result', row); body = saved.get('payload')
        kind = body.get('kind') if type(body) is dict else None
        if kind in remaining:
            if remaining[kind]:
                remaining[kind] -= 1
            else:
                saved.pop('payload', None); saved['payload_released'] = True
