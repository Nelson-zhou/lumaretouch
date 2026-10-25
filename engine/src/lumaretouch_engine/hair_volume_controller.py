# SPDX-License-Identifier: GPL-3.0-or-later
"""Current-photo hair-volume context/review/publication protocol. AUTHORED / UNRUN.

No colour-tool consent, second solver, live preview mutation or alternate undo.
All active source fields flow through the shared full mixed candidate renderer.
"""
from collections import OrderedDict
from copy import deepcopy
import re
import time
from . import people_state as P, hair_volume_state as S, hair_volume_support as A
from . import hair_volume_project as PROJECT, hair_volume_native as N, hair_volume_review as REVIEW
from . import hair_colour_evidence as EVIDENCE, creative_derived_source as SOURCE
from .hair_colour_assets import verify_face

ACTIONS = frozenset(('context', 'preview', 'presented', 'commit', 'clear', 'status'))
MUTATIONS = frozenset(('commit', 'clear'))
READS = ACTIONS - MUTATIONS
CONTEXT_FIELDS = {'document_id', 'document_epoch', 'document_revision', 'state_revision', 'association_revision', 'target'}
MAX_REVIEWS = 4
MAX_RECEIPTS = 1024
MAX_READ_IMAGE_BYTES = 32 * 1024 * 1024
TTL = 1800


def check_request(request):
    fields = {'cmd', 'protocol', 'operation_id', 'request_id', 'action', 'people_context', 'payload'}
    if (type(request) is not dict or set(request) != fields or request['cmd'] != 'hair_volume'
            or type(request['protocol']) is not int or request['protocol'] != 1
            or request['operation_id'] != S.OPERATION_ID or type(request['action']) is not str
            or request['action'] not in ACTIONS or type(request['people_context']) is not dict
            or set(request['people_context']) != CONTEXT_FIELDS or type(request['payload']) is not dict):
        raise ValueError('Invalid hair-volume command envelope')
    P.token(request['request_id']); context = request['people_context']
    for name in ('document_id', 'document_epoch'):
        P.token(context[name])
    for name in ('document_revision', 'state_revision', 'association_revision'):
        P.revision(context[name])
    target = context['target']
    if (type(target) is not dict or set(target) != {'scope', 'target_id', 'face_ref'}
            or target['scope'] != 'face' or P.check_ref(target['face_ref'])['face_instance_id'] != target['target_id']):
        raise ValueError('Hair volume requires one exact individually selected current-source FaceRef')
    action, payload = request['action'], request['payload']
    if action in ('context', 'clear'):
        if payload:
            raise ValueError('Hair-volume context and clear have no payload')
    elif action == 'preview':
        expected = {'recipe', 'regions', 'protection', 'confirmed', 'crown_confirmed', 'left_confirmed', 'right_confirmed'}
        if (set(payload) != expected or payload['confirmed'] is not True
                or any(type(payload[name + '_confirmed']) is not bool for name in S.REGIONS)):
            raise ValueError('Hair volume requires independent per-region contour/owner/background consent')
        recipe = S.check(payload['recipe'])
        if not S.active(recipe):
            raise ValueError('Use clear for a native-independent neutral reset')
        A.protection(payload['protection'])
        if type(payload['regions']) is not dict or set(payload['regions']) != set(S.REGIONS):
            raise ValueError('Independent crown/image-left/image-right measured regions are required')
        for name, amount in zip(S.REGIONS, S.amounts(recipe)):
            if amount != 0 and (payload['regions'][name] is None or payload[name + '_confirmed'] is not True):
                raise ValueError('Every nonzero crown/side needs its own observed contour and ownership consent')
            if amount == 0 and payload['regions'][name] is not None:
                raise ValueError('Inactive draft contours must remain local, not enter reviewed source support')
    elif action == 'status':
        if set(payload) != {'original_request_id'}:
            raise ValueError('Hair-volume status needs the original immutable request ID')
        P.token(payload['original_request_id'])
    else:
        expected = {'preview_id', 'review_token'} | ({'confirmed'} if action == 'commit'
            else {'before_sha256', 'after_sha256', 'support_sha256'})
        if (set(payload) != expected or type(payload['preview_id']) is not str
                or re.fullmatch('[0-9a-f]{32}', payload['preview_id']) is None):
            raise ValueError('Hair-volume image acknowledgement differs from the exact review')
        P.digest(payload['review_token'])
        if action == 'commit':
            if payload['confirmed'] is not True:
                raise ValueError('Confirm the exact complete before/after and source diagnostic images')
        else:
            for name in ('before_sha256', 'after_sha256', 'support_sha256'):
                P.digest(payload[name])
    return request


def read_only(request):
    try:
        return check_request(request)['action'] in READS
    except (ValueError, TypeError, KeyError):
        return False


def _live(engine, incoming, *, neutral=False):
    from .people_host_commands import checked
    from .virtual_copy_people import current_row
    state, _, target = checked(engine, {**incoming, 'request_id': 'hair-volume-context'})
    source = A.source(engine._people_source()); ref = P.check_ref(target.get('face_ref'))
    if (target['scope'] != 'face' or target != engine._people_targets.get(source['sha256'])
            or engine._people_cursors.get(source['sha256']) != target['target_id']
            or ref['asset_sha256'] != source['sha256']):
        raise ValueError('发量只支持当前照片中明确选中的独立人物，不能借用原片或其他人物身份')
    face = state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref:
        raise ValueError('Hair-volume selected source face changed')
    if not neutral:
        face = verify_face(state, ref, source)
        if not face['enabled'] or face['manual']:
            raise ValueError('先启用真实分析的人物；发量不从手工人脸框猜测头发或头部归属')
    row = current_row(engine)
    if row is None:
        raise ValueError('Hair-volume current document owner is unavailable')
    current = engine._people_preset_capture(); owner = engine._people_owner()
    version = engine._document_versions().version(row)
    proof = SOURCE.row_proof({**row, 'state': current})
    if proof['asset_sha256'] != source['sha256']:
        raise ValueError('Hair-volume effective source differs from the actual document source')
    SOURCE.verify(source, engine)
    if SOURCE.record(current) is not None:
        SOURCE.verify(source, current)
    captured = {'people_context': deepcopy(incoming), 'source': source, 'face_ref': deepcopy(ref),
        'source_proof': proof, 'owner_identity': id(owner), 'row_identity': id(row), 'graph_fence': owner.fence,
        'document_id': version.document_id, 'document_revision': version.revision,
        'load_id': engine._load_id, 'epoch': engine._document_versions().workspace}
    return captured, state, row, current


def _assert(engine, entry):
    captured, state, row, current = _live(engine, entry['captured']['people_context'])
    if (captured != entry['captured'] or state != entry['before']
            or REVIEW.snapshot_key(engine, row, current, state) != entry['before_key']):
        raise ValueError('照片、人物、分析、源图、保护范围或完整配方已变，请重新预览发量')
    return state, row, current


def context(engine, incoming):
    captured, state, row, current = _live(engine, incoming)
    source = captured['source']
    # Reads retained actual producer output; never installs or runs a model.
    evidence = EVIDENCE.current(engine, source)
    image = REVIEW.source_image(engine, source)
    entry = {'captured': captured, 'before': state, 'before_key': REVIEW.snapshot_key(engine, row, current, state),
        'expires': time.monotonic()+TTL, 'source_image_sha256': image['sha256'],
        'semantic_evidence_sha256': EVIDENCE.identity(evidence)}
    _assert(engine, entry); engine._hair_volume_reference = entry
    return {'kind': 'context', 'source': source, 'face_ref': captured['face_ref'],
        'recipe': PROJECT.recipe(state, captured['face_ref']['face_instance_id']),
        'source_kind': 'derived' if SOURCE.record(current) is not None else 'original',
        'semantic_evidence_sha256': entry['semantic_evidence_sha256'],
        'source_png': image['png'], 'source_png_sha256': image['sha256'],
        'source_width': source['width'], 'source_height': source['height'],
        'source_preview_width': image['width'], 'source_preview_height': image['height'],
        'native_available': N.available(),
        'notice': '颅顶与左右两侧分别测量并确认本人头发、清晰背景及可见耳颈/其他人物保护。整张源图诊断不是人物分割；最终裁切比例不同时按比例留边。不会沿用头发调色同意，也不会推断隐藏解剖结构。'}


def _reference(engine, incoming):
    entry = engine.__dict__.get('_hair_volume_reference')
    if (entry is None or time.monotonic() >= entry['expires']
            or entry['captured']['people_context'] != incoming):
        raise ValueError('先加载当前源图，再分别测量颅顶和所需侧边的轮廓')
    return entry, _assert(engine, entry)


def _reviews(engine):
    entries = engine.__dict__.setdefault('_hair_volume_reviews', OrderedDict())
    for key, entry in list(entries.items()):
        if time.monotonic() >= entry['expires'] and not entry['claimed']:
            entries.pop(key)
    return entries


def preview(engine, incoming, payload):
    reference, (state, row, current) = _reference(engine, incoming)
    captured = reference['captured']; source = captured['source']; ref = captured['face_ref']
    if not N.available():
        raise RuntimeError('发量原生模块缺失或 ABI 不兼容；不会用人脸缩放或假预览代替')
    evidence = EVIDENCE.current(engine, source)
    if EVIDENCE.identity(evidence) != reference['semantic_evidence_sha256']:
        raise ValueError('Measured source hair evidence changed; reload source and review independently')
    recipe = S.check(payload['recipe'])
    support = A.reviewed(state, ref, source, payload['regions'], payload['protection'],
                         evidence, confirmed=payload['confirmed'])
    candidate, bank = A.retain(state, PROJECT.store(engine), support)
    candidate = PROJECT.set_recipe(candidate, ref['face_instance_id'], recipe)
    PROJECT.require_scope(engine, state, candidate)
    PROJECT.validate_derived(candidate, bank, evidence, source)
    consent = {name: payload[name + '_confirmed'] for name in S.REGIONS}
    output, entry = REVIEW.complete(engine, row, current, state, candidate, bank,
        captured, reference, support, recipe, consent)
    entry['expires'] = time.monotonic()+TTL
    _assert(engine, entry)
    if REVIEW.snapshot_key(engine, row, current, candidate, staged_people_context=entry['staged']) != entry['after_key']:
        raise ValueError('The complete mixed candidate changed during hair-volume review')
    entries = _reviews(engine)
    while len(entries) >= MAX_REVIEWS:
        entries.popitem(last=False)
    entries[output['preview_id']] = entry
    return output


def _review(engine, incoming, payload):
    entry = _reviews(engine).get(payload['preview_id'])
    if (entry is None or entry['claimed'] or entry['review_token'] != payload['review_token']
            or entry['captured']['people_context'] != incoming or time.monotonic() >= entry['expires']):
        raise ValueError('Hair-volume review expired, changed, targets another owner or was already claimed')
    _, row, current = _assert(engine, entry)
    if REVIEW.snapshot_key(engine, row, current, entry['candidate'], staged_people_context=entry['staged']) != entry['after_key']:
        raise ValueError('Complete hair-volume candidate or immutable support bank changed after review')
    return entry


def presented(engine, incoming, payload):
    entry = _review(engine, incoming, payload)
    expected = REVIEW.ack(entry, payload['preview_id'])
    if payload != expected:
        raise ValueError('ACK only the three exact loaded complete before/after/source diagnostic PNGs')
    entry['presented'] = deepcopy(expected)
    return {'kind': 'presented', 'presented': True, **expected}


def _publish(engine, state, candidate, bank, captured, *, review_token=None):
    old = PROJECT.store(engine)
    if any(bank.get(key) != value for key, value in old.items()):
        raise ValueError('Hair-volume publication cannot replace immutable shared support bytes')
    if candidate == state:
        return None
    history_before = engine._history_capture(); engine._people_support = deepcopy(bank)
    try:
        with PROJECT.reviewed_transition(engine, state, candidate, bank, review_token):
            affected = {captured['source']['sha256']}
            engine._people_prepare_graph(candidate, affected)
            latest, graph, _, _ = _live(engine, captured['people_context'], neutral=review_token is None)
            if latest != captured or graph != state:
                raise ValueError('Hair-volume document or selection changed before canonical publication')
            return engine._people_publish_graph(candidate, affected)
    except Exception:
        # Preserve append-only bytes after any uncertain graph/fence/history change.
        owner = engine._people_owner()
        if engine._vram is not None and owner.snapshot() == state and owner.fence == captured['graph_fence']:
            engine._people_support = old
        raise
    finally:
        engine._people_staged = None
        engine._history_record('hair_volume', history_before, coalesce=False)


def commit(engine, incoming, payload):
    entry = _review(engine, incoming, payload)
    if entry['presented'] != REVIEW.ack(entry, payload['preview_id']):
        raise ValueError('Load and ACK all three exact full review images before applying hair volume')
    entry['claimed'] = True
    frame = _publish(engine, entry['before'], entry['candidate'], entry['bank'],
                     entry['captured'], review_token=entry['review_token'])
    if engine._people_owner().snapshot() != entry['candidate']:
        raise RuntimeError('Hair-volume publication did not retain the exact reviewed canonical graph')
    return {'kind': 'confirmed', 'committed': True, 'recipe': entry['recipe'],
            'asset_sha256': entry['metadata']['support_asset_sha256']}, frame


def clear(engine, incoming):
    captured, state, _, _ = _live(engine, incoming, neutral=True)
    ref = captured['face_ref']
    candidate = PROJECT.set_recipe(state, ref['face_instance_id'], S.neutral())
    candidate = A.detach(candidate, ref)
    PROJECT.require_scope(engine, state, candidate)
    frame = _publish(engine, state, candidate, PROJECT.store(engine), captured)
    return {'kind': 'cleared', 'committed': True, 'recipe': S.neutral()}, frame


def execute(engine, request, emit):
    check_request(request); request_id = request['request_id']; action = request['action']
    receipts = engine.__dict__.setdefault('_hair_volume_receipts', OrderedDict()); digest = A.digest(request)
    if request_id in receipts:
        if receipts[request_id]['digest'] != digest:
            raise ValueError('Hair-volume request ID was reused with different content')
        return
    if len(receipts) >= MAX_RECEIPTS:
        raise ValueError('Hair-volume receipt limit reached; save and reopen the authoritative project')
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
    # The common publisher has written the actual current raster, but its raw
    # frame lacks this operation's receipt identity. Only the exact terminal
    # receipt may notify native consumers and publish authoritative doc_state.
    receipts[request_id].update(success=True, payload=result, frame_emitted=frame is not None)


def finish(engine, request, error, emit):
    request_id = request.get('request_id')
    if type(request_id) is not str:
        return
    receipts = engine.__dict__.setdefault('_hair_volume_receipts', OrderedDict()); old = receipts.get(request_id, {})
    digest = A.digest(request)
    base = {'event': 'hair_volume_result', 'protocol': 1, 'operation_id': S.OPERATION_ID,
        'request_id': request_id, 'action': request.get('action'),
        'document_id': request.get('people_context', {}).get('document_id'),
        'people_context': deepcopy(request.get('people_context')), 'request_payload': deepcopy(request.get('payload'))}
    if not old and len(receipts) >= MAX_RECEIPTS:
        emit({**base, 'success': False, 'outcome_unknown': False, 'payload': None,
              'error': 'Hair-volume receipt limit reached; no new work admitted; save and reopen the authoritative project'})
        return
    if old.get('digest') not in (None, digest):
        emit({**base, 'success': False, 'outcome_unknown': False, 'payload': None,
              'error': 'Hair-volume request ID was reused with different content'})
        return
    if 'result' in old:
        emit(old['result']); return
    changed = bool(old.get('dispatch_unknown') or (error and old.get('mutation')
        and old.get('before_fence') != engine._people_owner().fence))
    success = bool(old.get('success')) and not error
    result = {**base, 'success': success, 'outcome_unknown': bool(engine._vram is None or changed),
        'error': None if success else str(error or 'Hair-volume operation did not complete'),
        'payload': deepcopy(old.get('payload')), 'frame_emitted': bool(old.get('frame_emitted'))}
    if engine._vram is not None and request.get('action') in MUTATIONS:
        try:
            result['doc_state'] = engine.doc_state()
        except Exception as state_error:
            result.update(success=False, outcome_unknown=True, error='Hair-volume result state unavailable: '+str(state_error))
    if result['outcome_unknown'] and request.get('action') in MUTATIONS:
        engine._hair_volume_uncertain = {'request_id': request_id, 'people_context': deepcopy(request.get('people_context'))}
    receipts[request_id] = {'digest': digest, 'result': result}
    REVIEW.bound_read_images(receipts, MAX_READ_IMAGE_BYTES)
    emit(receipts[request_id]['result'])


class HairVolumeHostMixin:
    def cmd_hair_volume(self, request):
        from .server import emit
        return execute(self, request, emit)

    def finish_hair_volume(self, request, error):
        from .server import emit
        return finish(self, request, error, emit)


def capability():
    available = N.available()
    return {'available': available, 'protocol': 1, 'operation_id': S.OPERATION_ID,
            'reason': None if available else 'Hair-volume core is missing or ABI-incompatible'}


def guard_other(engine, name, request):
    if engine.__dict__.get('_hair_volume_uncertain') is None:
        return
    if name in ('hello', 'shutdown'):
        return
    if name == 'hair_volume' and request.get('action') == 'status':
        return
    if name == 'session' and request.get('action') == 'query':
        return
    if name == 'project' and request.get('action') in ('open', 'create', 'new'):
        return
    if name == 'project_recovery' and request.get('action') in ('list', 'inspect', 'status', 'restore'):
        return
    raise ValueError('Hair-volume publication remains unresolved; query its original receipt or reopen the authoritative project')


def invalidate_after_reload(engine):
    """Only after confirmed authoritative reload, never on a transport timeout."""
    for name in ('uncertain', 'reference', 'reviews'):
        engine.__dict__.pop('_hair_volume_' + name, None)


def dispatch_rejected(engine, request, error, started, emit):
    if type(request) is not dict or type(request.get('request_id')) is not str:
        return
    receipts = engine.__dict__.setdefault('_hair_volume_receipts', OrderedDict())
    if request['request_id'] not in receipts and len(receipts) < MAX_RECEIPTS:
        receipts[request['request_id']] = {'digest': A.digest(request), 'success': False,
            'mutation': request.get('action') in MUTATIONS,
            'dispatch_unknown': bool(started and request.get('action') in MUTATIONS),
            'before_fence': engine._people_owner().fence}
    finish(engine, request, str(error), emit)
