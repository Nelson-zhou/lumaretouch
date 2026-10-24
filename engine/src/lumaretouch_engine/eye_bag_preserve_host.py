# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent, single-document eye-bag preservation image review.

AUTHORED / UNRUN. Manual source-space support is not anatomical detection.
Only the established people graph, receipt and document history publish edits.
Full mixed-portrait before/after images are display reductions of the real
canonical renderer; their PNG hashes are not compared with export pixel hashes.
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

from . import people_state as P, people_algorithms as A
from . import creative_derived_source as SOURCE, eye_bag_preserve_state as S
from .portrait_review_render import image as render_image, snapshot_key

READS = frozenset(('eye_bag_reference', 'eye_bag_preview', 'eye_bag_image', 'eye_bag_source_image'))
ACTIONS = READS | {'eye_bag_confirm'}
MAX_REVIEWS = 8
TTL = 1800
MAX_SAFE_REVISION = 9007199254740991


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def check_action(action, payload, target):
    if (action not in ACTIONS or type(payload) is not dict or type(target) is not dict
            or set(target) != {'scope', 'target_id', 'face_ref'} or target['scope'] != 'face'):
        raise ValueError('Eye-bag review requires one explicitly selected current face')
    ref = P.check_ref(target['face_ref'])
    if target['target_id'] != ref['face_instance_id']:
        raise ValueError('Eye-bag target and FaceRef differ')
    if action == 'eye_bag_reference':
        if payload: raise ValueError('Eye-bag source reference accepts no mutation')
    elif action == 'eye_bag_preview':
        if (set(payload) != {'recipe', 'eyes', 'replace_legacy'}
                or type(payload['replace_legacy']) is not bool):
            raise ValueError('Eye-bag preview needs explicit recipe, eyes and legacy replacement choice')
        if not S.active(payload['recipe']):
            raise ValueError('Reset amount to zero directly; dormant reset requires no support or native renderer')
        eyes = payload['eyes']
        if type(eyes) is not dict or not eyes or set(eyes) - {'left', 'right'}:
            raise ValueError('Paint and review at least one explicit eye; no eye is inferred')
        # Validate bounded portable vectors before server read-route admission.
        from . import local_mask_recipe as M
        for eye in eyes.values():
            if (type(eye) is not dict or set(eye) != {'recipe', 'visible', 'unoccluded', 'ownership_confirmed'}
                    or any(eye[key] is not True for key in ('visible', 'unoccluded', 'ownership_confirmed'))):
                raise ValueError('Confirm each painted ridge is visible, unoccluded and belongs to this face')
            stack = M.check_stack(eye['recipe'])
            if (not stack['objects'] or any(obj['kind'] != 'brush' or obj['operation'] not in ('add', 'subtract')
                                          for obj in stack['objects'])
                    or not any(obj['enabled'] and obj['opacity'] > 0 and obj['operation'] == 'add'
                               for obj in stack['objects'])):
                raise ValueError('Eye-bag support needs independently painted add/subtract brush coverage')
    else:
        fields = {'token', 'side', 'sha256'} if action in ('eye_bag_image', 'eye_bag_source_image') else {'token', 'ack'}
        if (set(payload) != fields or type(payload['token']) is not str
                or re.fullmatch('[0-9a-f]{32}', payload['token']) is None):
            raise ValueError('Eye-bag review requires its exact session token')
        if action in ('eye_bag_image', 'eye_bag_source_image'):
            sides = ('left', 'right') if action == 'eye_bag_source_image' else ('before', 'after', 'support')
            if payload['side'] not in sides or not _hash(payload['sha256']):
                raise ValueError('Invalid eye-bag image identity')
        else:
            ack = payload['ack']
            if (type(ack) is not dict or set(ack) != {
                    'review_sha256', 'before_sha256', 'after_sha256', 'support_overlay_sha256'}
                    or not all(_hash(value) for value in ack.values())):
                raise ValueError('Confirm the exact loaded before, after and authoritative support images')


def _live(engine, state, target):
    from .people_preset_plan import require_active_owner
    from .virtual_copy_people import current_row, scope_rows
    from .face_style_alias_review import verify_dormant
    owner = require_active_owner(engine); row = current_row(engine)
    if owner.snapshot() != state: raise ValueError('Eye-bag graph changed')
    ref = P.check_ref(target['face_ref']); face = state['faces'].get(target['target_id'])
    if (face is None or not face['enabled'] or P.face_ref(face) != ref
            or face['evidence']['status'] != 'verified'):
        raise ValueError('Eye-bag review needs this enabled face and its current verified analysis')
    current = engine._people_preset_capture()
    source = SOURCE.row_proof({**row, 'state': current})
    if (ref['asset_sha256'] != source['asset_sha256']
            or engine._people_cursors.get(source['asset_sha256']) != target['target_id']
            or engine._people_targets.get(source['asset_sha256']) != target):
        raise ValueError('Eye-bag review requires the explicitly selected face of the actual effective source')
    # This v1 protocol does not authorize invisible source-identical siblings,
    # including unavailable saved rows, source-switch history and named versions.
    aliases = [other for other in scope_rows(engine)
        if SOURCE.row_asset({**other, 'state': current} if other is row else other) == source['asset_sha256']]
    if len(aliases) != 1 or aliases[0] is not row:
        raise ValueError('Eye-bag review cannot change source-identical shared documents without reviewing them all')
    verify_dormant(engine, row, {source['asset_sha256']})
    version = engine._document_versions().version(row)
    return owner, row, current, source, version


def _values(state, target):
    from .people_resolver import resolve
    resolved = resolve(state, target['target_id'], A.defaults())
    if resolved['conflicts']: raise ValueError('Resolve existing portrait parameter conflicts before eye-bag review')
    values = A.recipes(resolved)
    return S.check(values[S.OP]), values[A.ENHANCE]['eye_bags']


def reference(engine, state, target, payload):
    check_action('eye_bag_reference', payload, target)
    owner, row, current, source, version = _live(engine, state, target)
    before = snapshot_key(engine, row, current, state); fence = owner.fence
    from .body_pose_commands import source_preview
    from . import eye_bag_preserve_support as SUPPORT
    # Discard superseded source crops before allocating the next full decode.
    engine._eye_bag_reference = None
    shown = source_preview(engine); recipe, legacy = _values(state, target)
    from .eye_bag_preserve_crop import prepare as prepare_crops
    crops = prepare_crops(engine, state, target, current, engine._people_source(), digest(before))
    token = uuid.uuid4().hex
    crop_images = {side: base64.b64decode(record['image']['base64'], validate=True)
        for side, record in crops['eyes'].items()}
    crops = {**crops, 'token': token, 'eyes': {side: {'rect': record['rect'],
        'image': {k: v for k, v in record['image'].items() if k != 'base64'}}
        for side, record in crops['eyes'].items()}}
    eyes = {}
    if S.KIND in state['faces'][target['target_id']]['local_assets']:
        try:
            record, _ = SUPPORT.resolve(state, engine._people_support, target['face_ref'])
            eyes = deepcopy(record['row']['eyes'])
        except ValueError:
            # Never reuse unverified vectors. The complete snapshot's existing
            # project-integrity checks remain strict and may require recovery;
            # this display branch cannot authenticate a corrupted asset bank.
            eyes = {}
    live = _live(engine, state, target)
    if (live[0] is not owner or live[1] is not row or owner.fence != fence
            or live[3] != source or live[4].document_id != version.document_id
            or live[4].revision != version.revision
            or snapshot_key(engine, row, live[2], state) != before):
        raise ValueError('Eye-bag source, repair, analysis or support changed while preparing reference')
    engine._eye_bag_reference = {'owner': owner, 'row': row, 'path': row['path'],
        'load_id': engine._load_id, 'fence': fence, 'target': deepcopy(target),
        'source': deepcopy(source), 'before_key': before, 'document_id': version.document_id,
        'revision': version.revision, 'epoch': engine._document_versions().workspace, 'source_preview': shown,
        'source_crops': crops, 'crop_images': crop_images, 'crop_served': set(), 'expires': time.monotonic() + TTL}
    response = {'kind': 'eye_bag_reference', 'source': deepcopy(engine._people_source()),
        'face_ref': deepcopy(target['face_ref']), 'source_preview': shown,
        'legacy_amount': legacy, 'recipe': recipe, 'eyes': eyes, 'source_crops': crops}
    # The legacy locator is nonauthoritative; refuse oversize transport rather
    # than silently downsampling the native crop pages. Leave receipt headroom.
    if len(json.dumps(response, ensure_ascii=False).encode()) > 6 * 1024**2:
        engine._eye_bag_reference = None
        raise ValueError('Source locator exceeds bounded reference transport; native crops were not reduced')
    return response


def _reference(engine, state, target, live):
    owner, row, current, source, version = live
    shown = getattr(engine, '_eye_bag_reference', None)
    if (not shown or time.monotonic() >= shown['expires'] or shown['owner'] is not owner or shown['row'] is not row
            or shown['path'] != row['path'] or shown['load_id'] != engine._load_id
            or shown['fence'] != owner.fence or shown['target'] != target or shown['source'] != source
            or shown['document_id'] != version.document_id or shown['revision'] != version.revision
            or shown['epoch'] != engine._document_versions().workspace
            or shown['before_key'] != snapshot_key(engine, row, current, state)):
        engine._eye_bag_reference = None  # Release stale native image bytes.
        raise ValueError('Read a fresh source reference after any source, repair, recipe, analysis or support change')
    return shown


def source_image(engine, state, target, payload):
    """Fetch one immutable native crop, never a new decode or mutable proxy."""
    check_action('eye_bag_source_image', payload, target)
    shown = _reference(engine, state, target, _live(engine, state, target))
    crops = shown['source_crops']
    side = payload['side']
    if payload['token'] != crops['token'] or payload['sha256'] != crops['eyes'][side]['image']['sha256']:
        raise ValueError('Native eye image request does not match the current frozen source crop')
    raw = shown['crop_images'][side]
    if sha256(raw).hexdigest() != payload['sha256']:
        engine._eye_bag_reference = None
        raise ValueError('Native eye cached bytes changed')
    shown['crop_served'].add(side)  # Read delivery, not a claim of human inspection.
    return {'kind': 'eye_bag_source_image', 'token': crops['token'], 'side': side,
        'snapshot_sha256': crops['snapshot_sha256'],
        'image': {**crops['eyes'][side]['image'], 'base64': base64.b64encode(raw).decode('ascii')}}


def _store(engine):
    store = engine.__dict__.get('_eye_bag_reviews')
    if store is None:
        # Reuse only bounded immutable blobs, not any other feature's controller.
        from .collarbone_visual_store import _Images
        store = {'pending': OrderedDict(), 'images': _Images(records=lambda plan: plan.records)}
        engine._eye_bag_reviews = store
    now = time.monotonic()
    for token, entry in list(store['pending'].items()):
        if now >= entry['expires']: del store['pending'][token]
    store['images'].prune({token: entry for token, entry in store['pending'].items() if not entry['claimed']})
    return store


def _plan(review):
    visual = review['visual']; overlay = review['support_overlay']
    # Synthetic image coordinates are private cache keys, not document owners.
    support = {'revision': visual['revision'], 'before': overlay, 'after': overlay}
    return SimpleNamespace(token=review['token'], records={visual['document_id']: visual,
        'support:' + visual['document_id']: support})


def _ack(review):
    return {'review_sha256': review['review_sha256'],
        'before_sha256': review['visual']['before']['sha256'],
        'after_sha256': review['visual']['after']['sha256'],
        'support_overlay_sha256': review['support_overlay']['sha256']}


def _entry(engine, token):
    store = _store(engine); entry = store['pending'].get(token)
    if entry is None: raise ValueError('Eye-bag review expired or was released; preview again')
    return store, entry


def _verify(engine, state, target, entry):
    from .virtual_copy_people import scope
    owner, row, current, source, version = _live(engine, state, target)
    review = entry['review']
    if (entry['claimed'] or owner is not entry['owner'] or owner.fence != entry['fence']
            or row is not entry['row'] or row['path'] != entry['path'] or engine._load_id != entry['load_id']
            or version.document_id != review['visual']['document_id']
            or str(version.revision) != review['visual']['revision']
            or engine._document_versions().workspace != review['owner']['document']['epoch']
            or scope(row) != review['owner']['people_scope']
            or target != entry['target'] or source != review['owner']['source_proof']
            or state != entry['before'] or snapshot_key(engine, row, current, state) != entry['before_key']
            or snapshot_key(engine, row, current, entry['candidate']) != entry['after_key']):
        raise ValueError('Eye-bag source, repair, analysis, support or complete recipe changed; preview again')
    SOURCE.verify_row({**row, 'state': current}, source)
    return current


def _overlay(engine, candidate, target, shown, analysis):
    """Exact authoritative source-space raster, not a browser-painted proxy."""
    from PIL import Image
    import numpy as np
    from . import eye_bag_preserve_support as SUPPORT
    from .cpu_memory_budget import available_estimate
    from .portrait_review_render import MAX_PNG_BYTES
    raw_source = np.asarray(SOURCE.analysis_rgb(engine))
    if (raw_source.dtype != np.uint8 or raw_source.ndim != 3 or raw_source.shape[2] != 3
            or raw_source.shape[:2] != analysis['face_skin'].shape
            or shown['source_sha256'] != target['face_ref']['asset_sha256']
            or [shown['source_width'], shown['source_height']] != [
                analysis['evidence']['source_width'], analysis['evidence']['source_height']]):
        raise ValueError('Eye-bag overlay requires the actual source/analysis grid, not a display proxy')
    # Source dimensions remain canonical in the support record. Semantic
    # observation dimensions remain in analysis. Only the FINAL tinted RGB
    # below is reduced to display dimensions; treatment never resizes this PNG.
    h, w = map(int, raw_source.shape[:2])
    # Reserve one uint8 destination plus the possible Pillow RGB copy and
    # bounded thumbnail/block scratch BEFORE either coverage or output allocates.
    # Never allocate full-frame float RGB/tint/alpha intermediates for display.
    budget = available_estimate(); display_bytes = h*w*6 + 16*1024*1024
    if type(budget) is not int or budget <= display_bytes:
        raise ValueError('Eye-bag support display exceeds its explicit memory admission')
    coverage, _ = SUPPORT.raster(candidate, engine._people_support, target['face_ref'],
        (h, w), analysis=analysis, byte_budget=budget-display_bytes)
    if coverage.shape != raw_source.shape[:2]: raise ValueError('Eye-bag support overlay has another source extent')
    mixed = np.empty((h, w, 3), dtype=np.uint8)
    for y in range(h):
        for x in range(0, w, 4096):
            weight = coverage[y, x:x+4096]
            full = weight == np.float32(1); partial = (weight > 0) & ~full
            alpha = np.zeros(weight.shape, dtype=np.float32)
            alpha[full] = np.float32(.7)
            alpha[partial] = np.float32(.3) + np.float32(.4)*weight[partial]
            block = raw_source[y, x:x+4096].astype(np.float32)
            tint = np.zeros_like(block); tint[full] = (0, 214, 214); tint[partial] = (255, 178, 0)
            block *= np.float32(1) - alpha[:, None]
            block += tint*alpha[:, None]
            np.clip(block, 0, 255, out=block); np.rint(block, out=block)
            mixed[y, x:x+4096] = block.astype(np.uint8)
    with Image.fromarray(mixed, 'RGB') as image:
        image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        width, height = image.size
        output = io.BytesIO(); image.save(output, format='PNG'); raw = output.getvalue()
    if len(raw) > MAX_PNG_BYTES: raise ValueError('Eye-bag support overlay exceeds its bounded transport budget')
    compact = {'mime': 'image/png', 'width': width, 'height': height,
        'sha256': sha256(raw).hexdigest()}
    extent = {'source_width': analysis['evidence']['source_width'],
        'source_height': analysis['evidence']['source_height'],
        'decoded_width': int(raw_source.shape[1]), 'decoded_height': int(raw_source.shape[0])}
    return compact, {**compact, 'base64': base64.b64encode(raw).decode('ascii')}, extent


def preview(engine, state, target, payload):
    check_action('eye_bag_preview', payload, target)
    live = _live(engine, state, target); shown = _reference(engine, state, target, live)
    owner, row, current, source, version = live; fence = owner.fence
    if (version.revision >= MAX_SAFE_REVISION or state['revision'] > MAX_SAFE_REVISION
            or state['association_revision'] > MAX_SAFE_REVISION):
        raise ValueError('Eye-bag review counters exceed exact client receipt range; no publication attempted')
    if set(payload['eyes']) - shown['crop_served']:
        raise ValueError('Load each painted eye native source crop under the current reference before review')
    recipe = S.check(payload['recipe']); _, legacy = _values(state, target)
    if legacy > 0 and not payload['replace_legacy']:
        raise ValueError('Legacy eye-bag correction is active; explicitly choose replacement or disable it first')
    from . import eye_bag_preserve_support as SUPPORT
    from .people_support_assets import check_store
    from .people_transfer_inventory import proof
    from .cpu_memory_budget import available_estimate
    analysis = engine._people_analyses.get(source['asset_sha256'], {}).get(target['target_id'])
    if analysis is None: raise ValueError('Current eye-bag face analysis is unavailable')
    candidate, bank = SUPPORT.retain(state, engine._people_support, target['face_ref'], payload['eyes'],
        analysis=analysis, byte_budget=available_estimate())
    check_store(bank)
    _reference(engine, state, target, _live(engine, state, target))
    # Only append-only bytes become reachable here. No live graph pointer,
    # history, canonical recipe or current output changes until confirmation.
    if any(bank.get(key) != value for key, value in engine._people_support.items()):
        raise ValueError('Eye-bag preview cannot replace immutable support bytes')
    engine._people_support = bank
    for key in S.KEYS:
        candidate = P.set_override(candidate, 'face', target['target_id'], S.OP, '/' + key, recipe[key])
    if payload['replace_legacy']:
        candidate = P.set_override(candidate, 'face', target['target_id'], A.ENHANCE, '/eye_bags', 0.0)
    if candidate['revision'] > MAX_SAFE_REVISION:
        raise ValueError('Eye-bag candidate revision exceeds exact client receipt range; no publication attempted')
    from .people_resolver import resolve
    A.validate_compatibility(A.recipes(resolve(candidate, target['target_id'], A.defaults())))
    if SOURCE.record(current) is not None:
        from .creative_derived_effects import require_graph
        require_graph(candidate, SOURCE.binding(current), document_id=version.document_id)
    _, support_key = SUPPORT.resolve(candidate, bank, target['face_ref'])
    before_key = snapshot_key(engine, row, current, state)
    # Retaining THIS preview's unused bytes is the sole authorized change to
    # the source-reference snapshot. Recheck above before appending; all other
    # source/repair/analysis/graph fields stay exact. A later recipe adjustment
    # can reuse the source image without accepting unrelated bank mutations.
    shown['before_key'] = before_key
    after_key = snapshot_key(engine, row, current, candidate)
    a, left, proof_a = render_image(engine, row, current, state, version.document_id, version.revision)
    b, right, proof_b = render_image(engine, row, current, candidate, version.document_id, version.revision)
    if (proof_a['source_proof'] != source or proof_b['source_proof'] != source
            or proof_a['source_size'] != proof_b['source_size']):
        raise ValueError('Eye-bag before/after images changed effective source')
    overlay, overlay_image, overlay_source = _overlay(engine, candidate, target, shown['source_preview'], analysis)
    token = uuid.uuid4().hex
    visual = {'version': 1, 'document_id': version.document_id, 'revision': str(version.revision),
        'source_proof': source, 'before_state_sha256': proof_a['candidate_sha256'],
        'candidate_state_sha256': proof_b['candidate_sha256'], 'before_people_sha256': proof_a['people_sha256'],
        'candidate_people_sha256': proof_b['people_sha256'], 'source_size': proof_a['source_size'],
        'before_output_size': proof_a['output_size'], 'after_output_size': proof_b['output_size'], 'before': a, 'after': b}
    review = {'version': 1, 'token': token, 'recipe': recipe, 'candidate_state_revision': candidate['revision'],
        'owner': proof(engine, row, state, source_row={**row, 'state': current}),
        'face_ref': deepcopy(target['face_ref']), 'support_sha256': support_key,
        'replace_legacy': payload['replace_legacy'], 'visual': visual, 'support_overlay': overlay,
        'support_source': overlay_source}
    review['review_sha256'] = digest(review)
    entry = {'owner': owner, 'row': row, 'path': row['path'], 'load_id': engine._load_id, 'fence': fence,
        'target': deepcopy(target), 'before': deepcopy(state), 'candidate': candidate,
        'before_key': before_key, 'after_key': after_key, 'review': review,
        'expires': time.monotonic() + TTL, 'claimed': False}
    _verify(engine, state, target, entry)
    store = _store(engine)
    while len(store['pending']) >= MAX_REVIEWS: store['pending'].popitem(last=False)
    store['images'].prune(store['pending'])
    store['images'].attach(_plan(review), {
        version.document_id: {'revision': visual['revision'], 'before': left, 'after': right},
        'support:' + version.document_id: {'revision': visual['revision'], 'before': overlay_image, 'after': overlay_image}})
    store['pending'][token] = entry
    return {'kind': 'eye_bag_preview', 'review': deepcopy(review)}


def _pixels(store, review, side):
    visual = review['visual']; support = side == 'support'
    document = ('support:' if support else '') + visual['document_id']
    descriptor = review['support_overlay'] if support else visual[side]
    return store['images'].read(_plan(review), document, visual['revision'],
        'before' if support else side, descriptor['sha256'])


def image(engine, state, target, payload):
    check_action('eye_bag_image', payload, target); store, entry = _entry(engine, payload['token'])
    _verify(engine, state, target, entry); review = entry['review']; side = payload['side']
    descriptor = review['support_overlay'] if side == 'support' else review['visual'][side]
    if payload['sha256'] != descriptor['sha256']: raise ValueError('Eye-bag image hash differs from this review')
    pixels = _pixels(store, review, side); _verify(engine, state, target, entry)
    return {'kind': 'eye_bag_image', **deepcopy(payload), 'review_sha256': review['review_sha256'], 'image': pixels}


def _proof(review):
    return {'kind': 'eye_bag_confirm', 'token': review['token'], 'review_sha256': review['review_sha256'],
        'ack': _ack(review), 'recipe': deepcopy(review['recipe']), 'support_sha256': review['support_sha256'],
        'replace_legacy': review['replace_legacy'], 'candidate_state_revision': review['candidate_state_revision']}


def confirm(engine, state, target, payload):
    check_action('eye_bag_confirm', payload, target); store, entry = _entry(engine, payload['token'])
    _verify(engine, state, target, entry); review = entry['review']
    if payload['ack'] != _ack(review): raise ValueError('Confirm this exact complete eye-bag image review')
    for side in ('before', 'after', 'support'): _pixels(store, review, side)
    _verify(engine, state, target, entry)
    return deepcopy(entry['candidate']), _proof(review)


def verify_before_publish(engine, state, target, payload, candidate, proof):
    store, entry = _entry(engine, payload['token']); _verify(engine, state, target, entry)
    review = entry['review']
    if candidate != entry['candidate'] or proof != _proof(review) or payload['ack'] != _ack(review):
        raise ValueError('Eye-bag publication differs from the exact reviewed graph or acknowledgement')
    for side in ('before', 'after', 'support'): _pixels(store, review, side)
    _verify(engine, state, target, entry)
    # One-way claim. A failure after this boundary must retain an uncertain
    # original request, not invite blind publication under a new identity.
    entry['claimed'] = True


def claimed(engine, token):
    entry = engine.__dict__.get('_eye_bag_reviews', {}).get('pending', {}).get(token)
    return bool(entry and entry['claimed'])


def verify_after_publish(engine, candidate, proof):
    from .virtual_copy_people import scope
    _, entry = _entry(engine, proof['token']); review = entry['review']
    owner, row, current, source, version = _live(engine, candidate, entry['target'])
    if (not entry['claimed'] or owner is not entry['owner'] or owner.fence != entry['fence'] + 1
            or row is not entry['row'] or row['path'] != entry['path'] or engine._load_id != entry['load_id']
            or version.document_id != review['visual']['document_id']
            or version.revision != int(review['visual']['revision']) + 1
            or engine._document_versions().workspace != review['owner']['document']['epoch']
            or scope(row) != review['owner']['people_scope'] or source != review['owner']['source_proof']
            or candidate != entry['candidate'] or owner.snapshot() != candidate or proof != _proof(review)
            or snapshot_key(engine, row, current, owner.snapshot()) != entry['after_key']):
        raise ValueError('Eye-bag publication differs from the reviewed graph/source; inspect the existing request')
    SOURCE.verify_row({**row, 'state': current}, review['owner']['source_proof'])


def report(engine, state, source, selected_id):
    from .people_resolver import resolve as resolve_values, materialize
    face = state['faces'].get(selected_id)
    if face is None: return None
    target = {'scope': 'face', 'target_id': selected_id, 'face_ref': P.face_ref(face)}
    resolved = resolve_values(state, selected_id, A.defaults())
    conflicts = [row for row in resolved['conflicts'] if row['operation_id'] == S.OP]
    recipe = None if conflicts else materialize(resolved, S.OP, S.neutral(), S.check)
    legacy_row = resolved['operations'].get(A.ENHANCE, {}).get('/eye_bags')
    legacy = None if legacy_row is None else legacy_row['value']
    descriptor = face['local_assets'].get(S.KIND)
    eyes = []; support_error = None; support_key = None
    if descriptor is not None:
        from .eye_bag_preserve_support import resolve
        try:
            record, support_key = resolve(state, engine._people_support, target['face_ref'])
            eyes = sorted(record['row']['eyes'])
        except ValueError as error:
            support_error = str(error)
    elif recipe is not None and S.active(recipe):
        support_error = 'Active eye-bag preservation has no reviewed support'
    prepared = getattr(engine._vram, 'people_prepared', None)
    records = [record for record in prepared.effects
        if record.stage == 'eye_bag_preserve' and record.face_ref == target['face_ref']] if prepared else []
    return {'recipe': recipe, 'source': deepcopy(source), 'face_ref': target['face_ref'],
        'legacy_amount': legacy, 'reviewed': support_key is not None, 'reviewed_eyes': eyes,
        'support_sha256': support_key, 'support_error': support_error, 'conflicts': deepcopy(conflicts),
        'changed_pixels': sum(int((record.facts or {}).get('changed_pixels', 0)) for record in records),
        'suspended': getattr(engine._vram, 'people_suspended', None)}
