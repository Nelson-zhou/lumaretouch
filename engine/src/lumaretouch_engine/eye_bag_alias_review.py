# SPDX-License-Identifier: GPL-3.0-or-later
"""Direct ridge editing on the actual shared owner and effective source.

Each alias renders its own complete repair/crop/mixed portrait input. The one
source-owned geometric support is not borrowed photometry or a donor transfer.
Publication uses the established scoped ledger. AUTHORED / UNRUN.
"""
from copy import deepcopy
from types import SimpleNamespace
import time
import uuid

from . import eye_bag_preserve_state as S
from . import creative_derived_source as SOURCE, virtual_copy_people as V
from . import people_batch_ledger as LEDGER, eye_bag_review_jobs as JOBS
from . import face_style_alias_review as CLOSURE
from .portrait_review_render import image as render_image, snapshot_key

MAX_MEMBERS = CLOSURE.MAX_MEMBERS


def check_ack(ack):
    from .eye_bag_preserve_host import _hash
    if (type(ack) is not dict or set(ack) != {'review_sha256', 'support_overlay_sha256', 'members'}
            or not _hash(ack['support_overlay_sha256'])):
        raise ValueError('Eye-bag aliases require their source support and every complete image pair')
    # Only the common exact-member wire validator is reused, not its recipe,
    # controller or scalar-only history authority.
    CLOSURE.check_ack({key: ack[key] for key in ('review_sha256', 'members')})


def _plan(review):
    records = {member['visual']['document_id']: member['visual'] for member in review['members']}
    current = review['visual']; overlay = review['support_overlay']
    records['support:' + current['document_id']] = {
        'revision': current['revision'], 'before': overlay, 'after': overlay}
    return SimpleNamespace(token=review['token'], records=records)


def _ack(review):
    return {'review_sha256': review['review_sha256'], 'support_overlay_sha256': review['support_overlay']['sha256'],
        'members': [{'document_id': visual['document_id'], 'revision': visual['revision'],
                     'before_sha256': visual['before']['sha256'], 'after_sha256': visual['after']['sha256']}
                    for visual in (member['visual'] for member in review['members'])]}


def _proof(review):
    from .eye_bag_preserve_host import _proof as single_proof
    proof = single_proof(review)
    proof['ack'] = _ack(review)
    proof['alias_members'] = [{'document_id': member['visual']['document_id'],
        'expected_revision': member['visual']['revision'],
        'result_revision': str(int(member['visual']['revision']) + 1)} for member in review['members']]
    return proof


def _required(review):
    return {(member['visual']['document_id'], side) for member in review['members'] for side in ('before', 'after')} | {
        (review['visual']['document_id'], 'support')}


def _available(store, review):
    plan = _plan(review)
    for document, visual in plan.records.items():
        for side in ('before', 'after'):
            store['images'].read(plan, document, visual['revision'], side, visual[side]['sha256'])


def _verify(engine, state, target, entry):
    from . import eye_bag_preserve_host as REVIEW
    owner, row, current, source, _ = REVIEW._live(engine, state, target, strict=False)
    review = entry['review']; batch = engine._batch_controller()
    if (entry['claimed'] or owner is not entry['owner'] or owner.fence != entry['fence']
            or row is not entry['row'] or engine._load_id != entry['load_id']
            or target != entry['target'] or state != entry['before'] or V.scope(row) != entry['scope']
            or batch is not entry['batch'] or engine._document_versions().workspace != entry['workspace']
            or source != review['owner']['source_proof'] or entry['candidate']['revision'] > REVIEW.MAX_SAFE_REVISION):
        raise ValueError('Eye-bag alias owner, source, selected face or complete graph changed; preview again')
    CLOSURE.verify_dormant(engine, row, {target['face_ref']['asset_sha256']})
    members = CLOSURE._eligible(engine, row, current, target['face_ref']['asset_sha256'])
    if len(members) != len(entry['members']):
        raise ValueError('Eye-bag alias membership changed; review every affected document')
    for actual, frozen in zip(members, entry['members']):
        other, recipe, proof, version = actual; visual = frozen['visual']
        if (other is not frozen['row'] or other['path'] != frozen['path']
                or version.document_id != visual['document_id'] or str(version.revision) != visual['revision']
                or proof != visual['source_proof']
                or snapshot_key(engine, other, recipe, state) != frozen['before_key']
                or snapshot_key(engine, other, recipe, entry['candidate']) != frozen['after_key']):
            raise ValueError('Eye-bag alias source, repair, crop, support or complete snapshot changed; preview again')
        SOURCE.verify_row({**other, 'state': recipe}, proof)
    if CLOSURE._targets(engine, batch, CLOSURE._plans(entry), current) != entry['targets']:
        raise ValueError('Eye-bag ledger closure changed or contains an unreviewed alias')
    return current


def preview(engine, state, target, payload, live, shown):
    from . import eye_bag_preserve_host as REVIEW
    from .people_transfer_inventory import proof
    from .people_graph_patch import between
    from .people_graph_owner import affected_assets
    owner, row, current, source, _ = live; fence = owner.fence
    members = CLOSURE._eligible(engine, row, current, source['asset_sha256'])
    candidate, support_key, _, _, analysis = REVIEW._stage(engine, state, target, payload, live, shown, strict=False)
    if not between(state, candidate):
        raise ValueError('Eye-bag alias review has no canonical change; no review was claimed')
    if affected_assets(state, candidate) != {source['asset_sha256']}:
        raise ValueError('Eye-bag ridge editing cannot change another source or association')
    batch = engine._batch_controller()
    entry = {'owner': owner, 'row': row, 'scope': V.scope(row), 'load_id': engine._load_id, 'fence': fence,
        'workspace': engine._document_versions().workspace, 'batch': batch, 'target': deepcopy(target),
        'before': deepcopy(state), 'candidate': candidate, 'members': [], 'claimed': False, 'served': set()}
    targets = CLOSURE._targets(engine, batch, CLOSURE._plans(entry), current)
    if ({item['document_id'] for item in targets.values()} != {item[3].document_id for item in members}
            or len(targets) != len(members)):
        raise ValueError('Eye-bag ledger includes an unreviewed affected alias')
    entry['targets'] = deepcopy(targets); public = []; displays = {}; common_size = None
    for other, recipe, source_proof, version in members:
        JOBS.checkpoint(engine)
        # Neither the current crop nor its repaired pixels are substituted for
        # another document. Each complete canonical render recomputes treatment.
        before_key = snapshot_key(engine, other, recipe, state)
        after_key = snapshot_key(engine, other, recipe, candidate)
        a, left, proof_a = render_image(engine, other, recipe, state, version.document_id, version.revision,
                                       cancelled=lambda: JOBS.cancelled(engine))
        b, right, proof_b = render_image(engine, other, recipe, candidate, version.document_id, version.revision,
                                        cancelled=lambda: JOBS.cancelled(engine))
        if (proof_a['source_proof'] != source_proof or proof_b['source_proof'] != source_proof
                or proof_a['source_size'] != proof_b['source_size']
                or (common_size is not None and proof_a['source_size'] != common_size)):
            raise ValueError('Eye-bag alias images changed effective source, provenance or canonical extent')
        common_size = proof_a['source_size']
        visual = {'version': 1, 'document_id': version.document_id, 'revision': str(version.revision),
            'source_proof': source_proof, 'before_state_sha256': proof_a['candidate_sha256'],
            'candidate_state_sha256': proof_b['candidate_sha256'], 'before_people_sha256': proof_a['people_sha256'],
            'candidate_people_sha256': proof_b['people_sha256'], 'source_size': proof_a['source_size'],
            'before_output_size': proof_a['output_size'], 'after_output_size': proof_b['output_size'], 'before': a, 'after': b}
        public.append({'path': other['path'], 'visual': visual})
        entry['members'].append({'row': other, 'path': other['path'], 'visual': visual,
                                 'before_key': before_key, 'after_key': after_key})
        displays[version.document_id] = {'revision': visual['revision'], 'before': left, 'after': right}
    overlay, overlay_image, overlay_source = REVIEW._overlay(engine, candidate, target, shown['source_preview'], analysis)
    JOBS.checkpoint(engine)
    token = uuid.uuid4().hex
    review = {'version': 2, 'token': token, 'recipe': S.check(payload['recipe']),
        'candidate_state_revision': candidate['revision'], 'owner': proof(engine, row, state, source_row={**row, 'state': current}),
        'face_ref': deepcopy(target['face_ref']), 'support_sha256': support_key, 'replace_legacy': payload['replace_legacy'],
        'visual': deepcopy(public[0]['visual']), 'members': public, 'support_overlay': overlay, 'support_source': overlay_source}
    review['review_sha256'] = REVIEW.digest(review)
    entry.update(review=review, expires=time.monotonic() + REVIEW.TTL)
    _verify(engine, state, target, entry)
    store = REVIEW._store(engine)
    while len(store['pending']) >= REVIEW.MAX_REVIEWS: store['pending'].popitem(last=False)
    store['images'].prune(store['pending'])
    visual = review['visual']
    displays['support:' + visual['document_id']] = {
        'revision': visual['revision'], 'before': overlay_image, 'after': overlay_image}
    JOBS.checkpoint(engine)
    store['images'].attach(_plan(review), displays)
    try:
        _verify(engine, state, target, entry)
        JOBS.checkpoint(engine)
        store['pending'][token] = entry
        return {'kind': 'eye_bag_preview', 'review': deepcopy(review)}
    except Exception:
        store['images'].discard(token)
        raise


def image(engine, state, target, payload, store, entry):
    if set(payload) != {'token', 'document_id', 'side', 'sha256'}:
        raise ValueError('Eye-bag alias images require the exact reviewed document identity')
    _verify(engine, state, target, entry); review = entry['review']; side = payload['side']
    document = payload['document_id']; records = _plan(review).records
    if side == 'support':
        if document != review['visual']['document_id']:
            raise ValueError('The shared source overlay belongs to the current reviewed source, not another repaired input')
        document = 'support:' + document; side = 'before'
    visual = records.get(document)
    if visual is None or payload['sha256'] != visual[side]['sha256']:
        raise ValueError('Eye-bag image does not belong to this exact reviewed alias')
    pixels = store['images'].read(_plan(review), document, visual['revision'], side, payload['sha256'])
    _verify(engine, state, target, entry); JOBS.checkpoint(engine)
    entry['served'].add((payload['document_id'], payload['side']))
    return {'kind': 'eye_bag_image', **deepcopy(payload), 'review_sha256': review['review_sha256'], 'image': pixels}


def _confirmed(store, entry, payload):
    review = entry['review']
    if payload['ack'] != _ack(review):
        raise ValueError('Confirm every exact eye-bag alias pair in reviewed order and the shared source overlay')
    if not _required(review) <= entry['served']:
        raise ValueError('Load every reviewed alias before/after and the authoritative source support before confirming')
    _available(store, review)


def confirm(engine, state, target, payload, store, entry):
    _verify(engine, state, target, entry)
    _confirmed(store, entry, payload); _verify(engine, state, target, entry)
    return deepcopy(entry['candidate']), _proof(entry['review'])


def publish(engine, state, target, payload, candidate, proof, request_id):
    from . import eye_bag_preserve_host as REVIEW
    from .eye_bag_alias_history import prepare
    store, entry = REVIEW._entry(engine, payload['token'])
    if entry['review']['version'] != 2:
        raise ValueError('Shared eye-bag publication requires its complete version-2 alias review')
    _verify(engine, state, target, entry)
    if candidate != entry['candidate'] or proof != _proof(entry['review']):
        raise ValueError('Eye-bag alias publication differs from its reviewed graph or acknowledgement')
    batch = entry['batch']; plans = CLOSURE._plans(entry); targets = deepcopy(entry['targets'])
    try:
        batch.documents.remember_current()
        if LEDGER._targets(batch, engine, plans) != targets:
            raise ValueError('Eye-bag alias ledger closure changed before preparation')
        history = prepare(engine, entry['review'], plans, targets)
        LEDGER.prepare_scoped(engine, plans, targets)
        LEDGER._verify(batch, engine, plans, targets)
        _verify(engine, state, target, entry); _confirmed(store, entry, payload)
        _verify(engine, state, target, entry)
        if LEDGER._targets(batch, engine, plans) != targets:
            raise ValueError('Eye-bag alias ledger closure changed before claim')
        # Never release this one-way claim after an exception. The host marks
        # it before publication so an unchanged graph fence is not a false proof
        # of no write when a claimed operation failed or lost its response.
        entry['claimed'] = True
        engine._people_receipts[request_id]['side_effects_started'] = True
        result = LEDGER.commit_scoped(batch, engine, plans, request_id=request_id,
            prepare=False, prepared_targets=targets, eye_bag_alias_history=history)
        if result is None: raise ValueError('Reviewed eye-bag alias publication unexpectedly became a no-op')
        bid, frame = result; entry['batch_id'] = bid
        # Preserve known ledger identity even if later post-publication status
        # verification fails. This is still outcome-unknown, never a new edit.
        engine._people_receipts[request_id]['batch_id'] = bid
        return bid, frame
    finally:
        engine._people_staged = None


def verify_after_publish(engine, candidate, proof, entry):
    from .people_preset_plan import require_active_owner
    from .eye_bag_alias_history import check
    owner = require_active_owner(engine); row = V.current_row(engine); review = entry['review']
    current = engine._people_preset_capture(); batch = engine._batch_controller()
    if (not entry['claimed'] or owner is not entry['owner'] or owner.fence != entry['fence'] + 1
            or row is not entry['row'] or V.scope(row) != entry['scope'] or engine._load_id != entry['load_id']
            or engine._document_versions().workspace != entry['workspace'] or batch is not entry['batch']
            or candidate != entry['candidate'] or owner.snapshot() != candidate or proof != _proof(review)):
        raise ValueError('Eye-bag alias publication graph/fence changed; inspect the existing request')
    CLOSURE.verify_dormant(engine, row, {entry['target']['face_ref']['asset_sha256']})
    members = CLOSURE._eligible(engine, row, current, entry['target']['face_ref']['asset_sha256'], advance=False)
    if len(members) != len(entry['members']):
        raise ValueError('Published eye-bag alias membership changed; inspect the existing request')
    for actual, frozen in zip(members, entry['members']):
        other, recipe, source, version = actual; visual = frozen['visual']
        if (other is not frozen['row'] or other['path'] != frozen['path']
                or version.document_id != visual['document_id'] or version.revision != int(visual['revision']) + 1
                or source != visual['source_proof']
                or snapshot_key(engine, other, recipe, owner.snapshot()) != frozen['after_key']):
            raise ValueError('Published eye-bag alias source, revision or snapshot differs; inspect the existing request')
        SOURCE.verify_row({**other, 'state': recipe}, source)
    expected = deepcopy(entry['targets'])
    for target in expected.values(): target['revision'] += 1
    receipt = batch.ledger.get(entry.get('batch_id'), {}); marker = check(receipt)
    if (CLOSURE._targets(engine, batch, CLOSURE._plans(entry), current) != expected
            or receipt.get('targets') != entry['targets'] or marker is None
            or marker['review_sha256'] != review['review_sha256']
            or marker['document_ids'] != sorted(member['visual']['document_id'] for member in review['members'])):
        raise ValueError('Published eye-bag ledger closure differs from review; inspect the existing request')
