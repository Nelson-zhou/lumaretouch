# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact full-image review and canonical graph publication. AUTHORED / UNRUN.

Preview keeps its candidate bank private. Only a bound presented-image ACK can
publish. The existing document owner remains the sole graph/history authority.
"""
from collections import OrderedDict
from copy import deepcopy
import base64
import hashlib
import io
import time
import uuid
import numpy as np
from . import people_state as P, hair_unification_state as S, hair_unification_assets as A
from . import hair_unification_project as PROJECT, hair_unification_native as N
from . import hair_colour_assets as HAIR, hair_colour_evidence as EVIDENCE, hair_colour_analysis as ANALYSIS
from . import creative_derived_source as SOURCE
from .portrait_review_render import snapshot_key, image as render_image

ACTIONS = frozenset(('context', 'preview', 'presented', 'commit', 'clear', 'status'))
READS = ACTIONS - {'commit', 'clear'}
MUTATIONS = frozenset(('commit', 'clear'))
CONTEXT_FIELDS = {'document_id', 'document_epoch', 'document_revision', 'state_revision', 'association_revision', 'target'}
MAX_REVIEWS = 4
MAX_READ_IMAGE_BYTES = 32 * 1024 * 1024
MAX_RECEIPTS = 1024
TTL = 1800


def check_request(request):
    if (type(request) is not dict or set(request) != {'cmd', 'protocol', 'operation_id', 'request_id', 'action', 'people_context', 'payload'}
            or request['cmd'] != 'hair_unification' or type(request['protocol']) is not int or request['protocol'] != 1
            or request['operation_id'] != S.OP or request['action'] not in ACTIONS
            or type(request['people_context']) is not dict or set(request['people_context']) != CONTEXT_FIELDS
            or type(request['payload']) is not dict):
        raise ValueError('Invalid hair-unification command envelope')
    P.token(request['request_id'])
    action, payload = request['action'], request['payload']
    if action in ('context', 'clear'):
        if payload: raise ValueError('Hair-unification context/clear takes no payload')
    elif action == 'preview':
        if set(payload) != {'recipe', 'root_sample', 'tip_sample', 'ownership_confirmed'} or payload['ownership_confirmed'] is not True:
            raise ValueError('Confirm source-owned manually painted root/tip sample vectors')
        if not S.active(payload['recipe']): raise ValueError('Use clear for a native-independent neutral reset')
        A.sample(payload['root_sample']); A.sample(payload['tip_sample'])
    elif action == 'status':
        if set(payload) != {'original_request_id'}: raise ValueError('Status needs the original immutable request ID')
        P.token(payload['original_request_id'])
    else:
        fields = {'preview_id', 'review_token'} | ({'confirmed'} if action == 'commit'
            else {'before_sha256', 'after_sha256', 'support_sha256'})
        if set(payload) != fields: raise ValueError('Hair-unification ACK fields differ from exact review')
        if type(payload['preview_id']) is not str or len(payload['preview_id']) != 32:
            raise ValueError('Invalid hair-unification preview token')
        P.token(payload['preview_id']); P.digest(payload['review_token'])
        if action == 'commit':
            if payload['confirmed'] is not True: raise ValueError('Explicit image review confirmation is required')
        else:
            for key in ('before_sha256', 'after_sha256', 'support_sha256'): P.digest(payload[key])
    return request


def read_only(request):
    try: return check_request(request)['action'] in READS
    except (ValueError, TypeError, KeyError): return False


def _live(engine, incoming, *, neutral=False):
    from .people_host_commands import checked
    from .virtual_copy_people import current_row
    state, binding, target = checked(engine, {**incoming, 'request_id': 'hair-unification-context'})
    source = A.source(engine._people_source()); ref = target.get('face_ref')
    if (target['scope'] != 'face' or target != engine._people_targets.get(source['sha256'])
            or engine._people_cursors.get(source['sha256']) != target['target_id']):
        raise ValueError('头发统一仅支持当前照片中明确选定的独立人物')
    ref = P.check_ref(ref); face = state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref or ref['asset_sha256'] != source['sha256']:
        raise ValueError('Hair-unification target no longer belongs to this exact source')
    if not neutral:
        face = HAIR.verify_face(state, ref, source)
        if not face['enabled']: raise ValueError('先启用所选人物，再审核头发统一')
    row = current_row(engine)
    if row is None: raise ValueError('Current document owner is unavailable')
    current = engine._people_preset_capture(); owner = engine._people_owner()
    version = engine._document_versions().version(row)
    source_proof = SOURCE.row_proof({**row, 'state': current})
    if source_proof['asset_sha256'] != source['sha256']:
        raise ValueError('Displayed hair-unification source differs from actual document source')
    if SOURCE.record(current) is not None: SOURCE.verify(source, current)
    captured = {'people_context': deepcopy(incoming), 'source': source, 'face_ref': deepcopy(ref),
        'owner_identity': id(owner), 'row_identity': id(row), 'graph_fence': owner.fence,
        'source_proof': source_proof, 'document_id': version.document_id, 'document_revision': version.revision,
        'load_id': engine._load_id, 'epoch': engine._document_versions().workspace}
    return captured, state, row, current


def _key(engine, captured, state, row, current):
    return snapshot_key(engine, row, current, state)


def _png(rgb):
    from PIL import Image
    if rgb.dtype == np.uint8: shown = rgb
    else:
        if not np.isfinite(rgb).all(): raise ValueError('Source review contains nonfinite pixels')
        shown = np.rint(np.clip(rgb, 0, 1)*255).astype(np.uint8)
    with Image.fromarray(shown, 'RGB') as image:
        image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        width, height = image.size; stream = io.BytesIO(); image.save(stream, format='PNG')
    raw = stream.getvalue()
    if len(raw) > 4*1024*1024: raise ValueError('Hair-unification review image exceeds bounded transport')
    return {'png': 'data:image/png;base64,' + base64.b64encode(raw).decode('ascii'),
            'sha256': hashlib.sha256(raw).hexdigest(), 'width': width, 'height': height}


def _raw_source(engine, source):
    rgb = SOURCE.analysis_rgb(engine)
    if type(rgb) is not np.ndarray or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('Actual source-view pixels are unavailable; no fabricated painting canvas')
    if SOURCE.record(engine) is not None:
        SOURCE.verify(source, engine); SOURCE.verify_precompute(engine, engine._precompute)
    return rgb


def _assert(engine, entry):
    captured, state, row, current = _live(engine, entry['captured']['people_context'])
    if (captured != entry['captured'] or state != entry['before']
            or _key(engine, captured, state, row, current) != entry['before_key']):
        raise ValueError('照片、人物、分析、选区或完整配方已改变，请重新预览头发统一')
    return state, row, current


def context(engine, incoming):
    captured, state, row, current = _live(engine, incoming)
    source = captured['source']; ref = captured['face_ref']; hair_bank = engine.__dict__.get('_hair_colour_assets', {})
    hair = HAIR.resolve(state, hair_bank, ref)
    evidence = EVIDENCE.current(engine, source) if hair is not None else None
    if hair is not None and hair['semantic_evidence_sha256'] != EVIDENCE.identity(evidence):
        raise ValueError('Reviewed hair support differs from retained real semantic evidence')
    pixels = _raw_source(engine, source); image = _png(pixels)
    samples = A.resolve(state, PROJECT.store(engine), ref, hair_bank)
    if samples is not None and (hair is None or samples['support_sha256'] != hair['review']['review_key']): samples = None
    entry = {'captured': captured, 'before': state, 'before_key': _key(engine, captured, state, row, current),
             'expires': time.monotonic()+TTL, 'source_image_sha256': image['sha256']}
    _assert(engine, entry); engine._hair_unification_reference = entry
    return {'kind': 'context', 'source': source, 'face_ref': ref, 'recipe': PROJECT.recipe(state, ref['face_instance_id']),
        'root_sample': A.empty_mask() if samples is None else samples['root_sample'],
        'tip_sample': A.empty_mask() if samples is None else samples['tip_sample'],
        'support_sha256': None if hair is None else hair['review']['review_key'],
        'semantic_evidence_sha256': None if hair is None else hair['semantic_evidence_sha256'],
        'source_png': image['png'], 'source_width': source['width'], 'source_height': source['height'],
        'source_preview_width': image['width'], 'source_preview_height': image['height'], 'native_available': N.available(),
        'notice': '负值取手工发梢样本，正值取手工发根样本。取样非零范围保持不变，其余已审核本人头发为目标；仅统一颜色，不均衡亮度或重建细节。'}


def _reference(engine, incoming):
    entry = engine.__dict__.get('_hair_unification_reference')
    if entry is None or time.monotonic() >= entry['expires'] or entry['captured']['people_context'] != incoming:
        raise ValueError('先加载当前源图，再手工标记并审核发根/发梢')
    return entry, _assert(engine, entry)


def _store(engine):
    entries = engine.__dict__.setdefault('_hair_unification_reviews', OrderedDict())
    for key, value in list(entries.items()):
        if time.monotonic() >= value['expires'] and not value['claimed']: entries.pop(key)
    return entries


def _staged_context(engine, row, candidate, bank):
    from .full_candidate_render import people_context
    result = people_context(engine, row)
    result['people_graph'] = candidate; result[PROJECT.KEY] = bank
    return result


def _overlay(engine, source, samples, hair_record, recipe, evidence):
    from .hair_unification_runtime import fields, target_coverage
    from .cpu_memory_budget import available_estimate
    rgb = _raw_source(engine, source); shape = tuple(rgb.shape[:2])
    if available_estimate() < rgb.shape[0]*rgb.shape[1]*64+32*1024*1024:
        raise MemoryError('Source sample overlay exceeds memory admission')
    hair = ANALYSIS.at_dimensions(evidence, source, shape)
    support, roots, tips = fields(samples, hair_record, shape, hair,
        source_path=None if SOURCE.record(engine) is not None else engine._doc_path)
    target = target_coverage(support, roots, tips, recipe)
    selected = tips if S.reference_side(recipe) == 'tips' else roots
    if np.count_nonzero(selected) < 32:
        raise ValueError('当前源图视图中可审核的可信取样太少，请扩大样本或使用更清晰的照片')
    shown = rgb.astype(np.float32)/255.
    alpha = np.minimum(target, 1)[..., None]*.4
    shown = shown*(1-alpha)+np.array((.1, .85, .85), dtype=np.float32)*alpha
    for coverage, colour in ((roots, (.95, .35, .15)), (tips, (.45, .35, 1.0))):
        alpha = (coverage > 0)[..., None].astype(np.float32)*.6
        shown = shown*(1-alpha)+np.array(colour, dtype=np.float32)*alpha
    return _png(shown), {'hair_pixels': int(np.count_nonzero(support)), 'root_pixels': int(np.count_nonzero(roots)),
                         'tip_pixels': int(np.count_nonzero(tips)), 'selected_pixels': int(np.count_nonzero(selected))}


def preview(engine, incoming, payload):
    reference, (state, row, current) = _reference(engine, incoming)
    captured = reference['captured']; ref = captured['face_ref']; source = captured['source']
    if not N.available(): raise RuntimeError('头发统一原生模块不可用；不会把染发、空白图或假预览当作成功')
    hair_bank = engine.__dict__.get('_hair_colour_assets', {})
    hair = HAIR.resolve(state, hair_bank, ref)
    if hair is None: raise ValueError('先在头发调色中审核本人物完整头发范围；人脸框不是头发归属')
    evidence = EVIDENCE.current(engine, source)
    if EVIDENCE.identity(evidence) != hair['semantic_evidence_sha256']: raise ValueError('Hair class evidence changed')
    samples = A.reviewed(hair, payload['root_sample'], payload['tip_sample'], confirmed=payload['ownership_confirmed'])
    candidate, bank = A.retain(state, PROJECT.store(engine), samples, hair_bank)
    recipe = S.check(payload['recipe'])
    candidate = P.set_override(candidate, 'face', ref['face_instance_id'], S.OP, '/amount', recipe['amount'])
    PROJECT.require_scope(engine, state, candidate)
    if SOURCE.record(current) is not None:
        PROJECT.validate_derived(candidate, bank, hair_bank, evidence, source)
    staged = _staged_context(engine, row, candidate, bank)
    before_key = reference['before_key']; after_key = snapshot_key(engine, row, current, candidate, staged_people_context=staged)
    a, before_image, proof_a = render_image(engine, row, current, state, captured['document_id'], captured['document_revision'])
    b, after_image, proof_b = render_image(engine, row, current, candidate, captured['document_id'], captured['document_revision'], staged_people_context=staged)
    if (proof_a['source_proof'] != captured['source_proof'] or proof_b['source_proof'] != captured['source_proof']
            or proof_a['source_size'] != proof_b['source_size'] or proof_a['output_size'] != proof_b['output_size']):
        raise ValueError('Complete hair-unification review changed its source or output geometry')
    overlay, counts = _overlay(engine, source, samples, hair, recipe, evidence)
    token = uuid.uuid4().hex
    metadata = {'version': 1, 'operation_id': S.OP, 'preview_id': token, 'source': source, 'face_ref': ref,
        'recipe': recipe, 'sample_asset_sha256': A.digest(samples), 'source_image_sha256': reference['source_image_sha256'],
        'before_key': before_key, 'after_key': after_key, 'before_proof': proof_a, 'after_proof': proof_b,
        'before_sha256': a['sha256'], 'after_sha256': b['sha256'], 'support_sha256': overlay['sha256']}
    review_token = A.digest(metadata)
    entry = {'captured': captured, 'before': state, 'candidate': candidate, 'bank': bank, 'staged': staged,
        'before_key': before_key, 'after_key': after_key, 'metadata': metadata, 'review_token': review_token,
        'recipe': recipe, 'presented': None, 'claimed': False, 'expires': time.monotonic()+TTL}
    _assert(engine, entry)
    if snapshot_key(engine, row, current, candidate, staged_people_context=staged) != after_key:
        raise ValueError('Candidate changed during complete before/after review')
    entries = _store(engine)
    while len(entries) >= MAX_REVIEWS: entries.popitem(last=False)
    entries[token] = entry
    return {'kind': 'preview', 'preview_id': token, 'review_token': review_token, 'preview_sha256': review_token,
        'sample_asset_sha256': metadata['sample_asset_sha256'], 'source': source, 'face_ref': ref, 'recipe': recipe, 'root_sample': samples['root_sample'], 'tip_sample': samples['tip_sample'],
        'before_png': 'data:image/png;base64,'+before_image['base64'], 'after_png': 'data:image/png;base64,'+after_image['base64'],
        'support_png': overlay['png'], 'before_sha256': a['sha256'], 'after_sha256': b['sha256'], 'support_sha256': overlay['sha256'],
        'before_width': a['width'], 'before_height': a['height'], 'after_width': b['width'], 'after_height': b['height'],
        'support_width': overlay['width'], 'support_height': overlay['height'], 'source_width': source['width'], 'source_height': source['height'],
        'reference_side': S.reference_side(recipe), 'sample_counts': counts}


def _review(engine, incoming, payload):
    entry = _store(engine).get(payload['preview_id'])
    if (entry is None or entry['claimed'] or entry['review_token'] != payload['review_token']
            or entry['captured']['people_context'] != incoming or time.monotonic() >= entry['expires']):
        raise ValueError('Hair-unification review expired, changed, belongs to another target or was already claimed')
    state, row, current = _assert(engine, entry)
    if snapshot_key(engine, row, current, entry['candidate'], staged_people_context=entry['staged']) != entry['after_key']:
        raise ValueError('Complete candidate or owned sample bank changed since review')
    return entry


def presented(engine, incoming, payload):
    entry = _review(engine, incoming, payload)
    expected = {'preview_id': payload['preview_id'], 'review_token': entry['review_token'],
                **{key: entry['metadata'][key] for key in ('before_sha256', 'after_sha256', 'support_sha256')}}
    if payload != expected: raise ValueError('Only ACK the exact loaded complete before, after and source sample PNGs')
    entry['presented'] = deepcopy(expected)
    return {'kind': 'presented', 'presented': True, **expected}


def _publish(engine, state, candidate, bank, captured, *, review_token=None):
    old = PROJECT.store(engine)
    history_before = engine._history_capture()
    if any(bank.get(key) != value for key, value in old.items()):
        raise ValueError('Hair-unification publication cannot replace immutable sample bytes')
    if candidate == state: return None
    engine._hair_unification_assets = bank
    try:
        with PROJECT.reviewed_transition(engine, state, candidate, bank, review_token):
            affected = {captured['source']['sha256']}
            engine._people_prepare_graph(candidate, affected)
            # Full preparation cannot authorize a stale document/target.
            latest, latest_state, _, _ = _live(engine, captured['people_context'], neutral=review_token is None)
            if latest != captured or latest_state != state:
                raise ValueError('Hair-unification document changed before atomic publication')
            return engine._people_publish_graph(candidate, affected)
    except Exception:
        # Append-only bytes stay retained if commit/rollback is uncertain. They
        # are inert without pointers, but must remain available to undo history.
        if engine._vram is not None and engine._people_owner().snapshot() == state:
            engine._hair_unification_assets = old
        raise
    finally:
        engine._people_staged = None
        engine._history_record("hair_unification", history_before, coalesce=False)


def commit(engine, incoming, payload):
    entry = _review(engine, incoming, payload)
    expected = {'preview_id': payload['preview_id'], 'review_token': entry['review_token'],
                **{key: entry['metadata'][key] for key in ('before_sha256', 'after_sha256', 'support_sha256')}}
    if entry['presented'] != expected: raise ValueError('Load and ACK all three exact review images before committing')
    entry['claimed'] = True
    frame = _publish(engine, entry['before'], entry['candidate'], entry['bank'], entry['captured'], review_token=entry['review_token'])
    if engine._people_owner().snapshot() != entry['candidate']:
        raise RuntimeError('Hair-unification publication did not retain the exact reviewed graph')
    return {'kind': 'confirmed', 'committed': True, 'recipe': entry['recipe'],
            'asset_sha256': entry['metadata']['sample_asset_sha256']}, frame


def clear(engine, incoming):
    captured, state, _, _ = _live(engine, incoming, neutral=True)
    candidate = P.set_override(state, 'face', captured['face_ref']['face_instance_id'], S.OP, '/amount', 0.0)
    PROJECT.require_scope(engine, state, candidate)
    frame = _publish(engine, state, candidate, PROJECT.store(engine), captured)
    return {'kind': 'cleared', 'committed': True, 'recipe': S.neutral()}, frame


def execute(engine, request, emit):
    check_request(request); request_id = request['request_id']; action = request['action']
    receipts = engine.__dict__.setdefault('_hair_unification_receipts', OrderedDict()); digest = A.digest(request)
    if request_id in receipts:
        if receipts[request_id]['digest'] != digest: raise ValueError('Hair-unification request ID reused with different content')
        return
    if len(receipts) >= MAX_RECEIPTS:
        raise ValueError('Hair-unification receipt capacity reached; save and reopen the authoritative project before new requests')
    receipts[request_id] = {'digest': digest, 'success': False, 'mutation': action in MUTATIONS,
                            'before_fence': engine._people_owner().fence}
    incoming, payload = request['people_context'], request['payload']; frame = None
    if action == 'status':
        original = receipts.get(payload['original_request_id'])
        result = {'kind': 'status', 'original_request_id': payload['original_request_id'],
                  'found': bool(original and 'result' in original), 'result': deepcopy(original.get('result')) if original else None}
    elif action == 'context': result = context(engine, incoming)
    elif action == 'preview': result = preview(engine, incoming, payload)
    elif action == 'presented': result = presented(engine, incoming, payload)
    elif action == 'commit': result, frame = commit(engine, incoming, payload)
    else: result, frame = clear(engine, incoming)
    if frame is not None: emit(frame)
    receipts[request_id].update(success=True, payload=result, frame_emitted=frame is not None)


def finish(engine, request, error, emit):
    request_id = request.get('request_id')
    if type(request_id) is not str: return
    receipts = engine.__dict__.setdefault('_hair_unification_receipts', OrderedDict()); old = receipts.get(request_id, {})
    digest = A.digest(request)
    base = {'event': 'hair_unification_result', 'protocol': 1, 'operation_id': S.OP, 'request_id': request_id,
            'action': request.get('action'), 'document_id': request.get('people_context', {}).get('document_id'),
            'people_context': deepcopy(request.get('people_context')), 'request_payload': deepcopy(request.get('payload'))}
    if not old and len(receipts) >= MAX_RECEIPTS:
        emit({**base, 'success': False, 'outcome_unknown': False,
              'error': 'Hair-unification receipt capacity reached; no new work admitted; save and reopen the authoritative project'})
        return
    if old.get('digest') not in (None, digest):
        emit({**base, 'success': False, 'outcome_unknown': False, 'error': 'Request ID reused with different content'}); return
    if 'result' in old: emit(old['result']); return
    changed = bool(old.get("dispatch_unknown") or (error and old.get("mutation") and old.get("before_fence") != engine._people_owner().fence))
    success = bool(old.get('success')) and not error
    result = {**base, 'success': success, 'outcome_unknown': bool(engine._vram is None or changed),
              'error': None if success else str(error or 'Hair-unification operation did not complete'),
              'payload': deepcopy(old.get('payload')), 'frame_emitted': bool(old.get('frame_emitted'))}
    if engine._vram is not None and request.get('action') in MUTATIONS:
        try: result['doc_state'] = engine.doc_state()
        except Exception as state_error:
            result.update(success=False, outcome_unknown=True, error='Hair-unification result state unavailable: '+str(state_error))
    if result["outcome_unknown"] and request.get("action") in MUTATIONS:
        engine._hair_unification_uncertain = {"request_id": request_id, "people_context": deepcopy(request.get("people_context"))}
    receipts[request_id] = {'digest': digest, 'result': result}
    _bound_read_images(receipts)
    emit(receipts[request_id]['result'])


class HairUnificationHostMixin:
    def cmd_hair_unification(self, request):
        from .server import emit
        return execute(self, request, emit)

    def finish_hair_unification(self, request, error):
        from .server import emit
        return finish(self, request, error, emit)


def capability():
    """Symbol/ABI probe at runtime only, not an image-acceptance claim."""
    ok = N.available()
    return {'available': ok, 'reason': None if ok else 'Hair-unification core is disabled, missing or ABI-incompatible',
            'protocol': 1, 'operation_id': S.OP}


def guard_other(engine, name, request):
    if engine.__dict__.get('_hair_unification_uncertain') is None: return
    if name in ('hello', 'shutdown'): return
    if name == 'hair_unification' and request.get('action') == 'status': return
    if name == 'session' and request.get('action') == 'query': return
    if name == 'project' and request.get('action') in ('open', 'create', 'new'): return
    if name == 'project_recovery' and request.get('action') in ('list', 'inspect', 'status', 'restore'): return
    raise ValueError('Hair-unification commit is unresolved; query its original receipt or reopen the authoritative project before editing')


def invalidate_after_reload(engine):
    """Only after confirmed authoritative project reload, never on a timeout."""
    engine.__dict__.pop('_hair_unification_uncertain', None)
    engine.__dict__.pop('_hair_unification_reference', None)
    engine.__dict__.pop('_hair_unification_reviews', None)


def dispatch_rejected(engine, request, error, started, emit):
    if type(request) is not dict or type(request.get('request_id')) is not str: return
    receipts = engine.__dict__.setdefault('_hair_unification_receipts', OrderedDict())
    old = receipts.get(request['request_id'])
    if old is None and len(receipts) < MAX_RECEIPTS:
        receipts[request['request_id']] = {'digest': A.digest(request), 'success': False,
            'mutation': request.get('action') in MUTATIONS, 'dispatch_unknown': bool(started and request.get('action') in MUTATIONS),
            'before_fence': engine._people_owner().fence}
    finish(engine, request, str(error), emit)


def _image_bytes(value):
    """Count retained encoded image strings without decoding or copying them."""
    if type(value) is str:
        return len(value) if value.startswith('data:image/') else 0
    if type(value) is dict:
        return sum(len(child) if key == 'base64' and type(child) is str else _image_bytes(child)
                   for key, child in value.items())
    if type(value) in (list, tuple):
        return sum(_image_bytes(child) for child in value)
    return 0


def _bound_read_images(receipts):
    """Release old read PNGs, retaining exact request identities as tombstones.

    Mutation and presented ACK receipts are never modified. An expired read's
    identity still exists, so execute cannot rerender or recapture under that ID.
    The independent metadata/request limit refuses new work rather than evicting
    an identity and making duplicate effects or fresh images possible.
    """
    rows = []
    total = 0
    for request_id, record in receipts.items():
        result = record.get('result')
        if result is None or result.get('action') not in ('context', 'preview', 'status'):
            continue
        size = _image_bytes(result)
        if size:
            rows.append((request_id, size)); total += size
    for request_id, size in rows:
        if total <= MAX_READ_IMAGE_BYTES: break
        record = receipts[request_id]; result = record['result']
        # Keep exact correlation, raw request payload and immutable original
        # digest, but never imply an evicted image can still be acknowledged.
        tombstone = {key: value for key, value in result.items() if key not in ('payload', 'doc_state')}
        tombstone.update(success=False, outcome_unknown=False, payload=None,
            payload_released=True, no_write=True, frame_emitted=False,
            error='Read-only hair-unification images were released; request a fresh context/preview with a new request ID')
        receipts[request_id] = {**record, 'result': tombstone}
        total -= size
