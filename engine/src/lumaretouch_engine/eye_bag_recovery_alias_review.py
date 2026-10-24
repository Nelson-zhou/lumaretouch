# SPDX-License-Identifier: GPL-3.0-or-later
"""Complete, paged recovery review on one existing shared source owner.

Only the selected face's immutable eye_bag_preserve recovery pointer changes.
Each member keeps its own complete document recipe, repair and crop. Candidate
vectors are staged in isolated full renders, never installed for a preview.
AUTHORED / UNRUN.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import base64
import json
import time
import uuid

from . import face_style_alias_review as CLOSURE, virtual_copy_people as V
from . import creative_derived_source as SOURCE, people_support_assets as BANK
from . import eye_bag_effect_recovery as EYE

TARGET = EYE.TARGET
TTL = 600
_SEAL = object()
TRANSACTION_FIELDS = ('context', 'before', 'candidate', 'assets', 'target', 'no_change')


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class _Admission:
    """A private source/owner capability, not a client flag or generic bypass."""
    def __init__(self, engine, live, context):
        self.seal = _SEAL
        self.engine = engine
        self.owner, self.row, _, self.source, _ = live
        self.fence = self.owner.fence
        self.context = deepcopy(context)
        self.before = self.owner.snapshot()
        self.workspace = engine._document_versions().workspace
        self.load_id = engine._load_id


def _live(engine):
    from . import people_recovery as PEOPLE
    from .eye_bag_preserve_host import _live as eye_live
    source, graph, _, ref = PEOPLE.selection(engine, editing=True)
    target = {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': ref}
    live = eye_live(engine, graph, target, strict=False)
    if source['sha256'] != live[3]['asset_sha256']:
        raise ValueError('Eye-bag recovery alias source identity changed')
    return live, PEOPLE.context(engine)


def availability(engine):
    """Availability probes cannot mint publication or candidate authority."""
    live, _ = _live(engine)
    if CLOSURE.has_aliases(engine, live):
        CLOSURE._eligible(engine, live[1], live[2], live[3]['asset_sha256'])


def admission(engine):
    live, context = _live(engine)
    if not CLOSURE.has_aliases(engine, live):
        return None
    CLOSURE._eligible(engine, live[1], live[2], live[3]['asset_sha256'])
    return _Admission(engine, live, context)


def validate_admission(engine, value, graph, face_ref):
    if (type(value) is not _Admission or value.seal is not _SEAL or value.engine is not engine
            or value.before != graph or value.context['face_ref'] != face_ref):
        raise ValueError('Shared eye-bag recovery requires its private exact-source admission')
    live, context = _live(engine)
    if (live[0] is not value.owner or live[1] is not value.row or live[0].fence != value.fence
            or context != value.context or live[3] != value.source
            or engine._document_versions().workspace != value.workspace or engine._load_id != value.load_id
            or not CLOSURE.has_aliases(engine, live)):
        raise ValueError('Shared eye-bag recovery admission changed owner, source, face or workspace')
    return live


def _dormant_key(engine, row):
    from .optics_candidate_identity import fingerprint
    project = getattr(engine, '_project', None) or {}
    return fingerprint({'saved_docs': project.get('docs', []),
        'retained_histories': project.get('people_document_history', {}),
        'source_assets': project.get('source_assets', {}),
        'rows': [{'document_id': other.get('document_id'), 'path': other.get('path'),
            'scope': V.scope(other), 'trashed': other.get('trashed'),
            'new_import': other.get('_people_new_import'),
            'undo': getattr(engine, '_undo', []) if other is row else other.get('undo', []),
            'redo': getattr(engine, '_redo', []) if other is row else other.get('redo', [])}
            for other in CLOSURE._scope_rows(engine, row)]})


def _retained(transaction):
    return deepcopy({key: transaction[key] for key in TRANSACTION_FIELDS})


def _narrow(transaction, before_assets):
    from .people_graph_patch import between
    from .people_graph_owner import affected_assets
    if transaction['target'] != TARGET:
        raise ValueError('Shared recovery admission cannot edit another effect')
    ref = transaction['context']['face_ref']; before = transaction['before']; after = transaction['candidate']
    BANK.check_store(before_assets); BANK.check_store(transaction['assets'])
    if any(transaction['assets'].get(key) != value for key, value in before_assets.items()):
        raise ValueError('Recovery cannot replace immutable history vectors')
    for graph, bank in ((before, before_assets), (after, transaction['assets'])):
        BANK.resolve(graph, bank, ref, TARGET)
    expected = deepcopy(before)
    expected['revision'] = after['revision']
    face = ref['face_instance_id']; descriptor = after['faces'][face]['local_assets'].get(TARGET)
    if descriptor is None: expected['faces'][face]['local_assets'].pop(TARGET, None)
    else: expected['faces'][face]['local_assets'][TARGET] = deepcopy(descriptor)
    changes = between(before, after)
    if (after != expected or after['revision'] != before['revision'] + bool(changes)
            or after['revision'] > CLOSURE.MAX_REVISION
            or affected_assets(before, after) - {ref['asset_sha256']}
            or transaction['no_change'] != (not changes)):
        raise ValueError('Recovery may change only this face eye-bag contribution pointer')
    added = set(transaction['assets']) - set(before_assets)
    expected_added = set() if descriptor is None else {descriptor['content_sha256']} - set(before_assets)
    if added != expected_added:
        raise ValueError('Recovery candidate contains an unreviewed extra immutable asset')


def _plans(entry):
    transaction = entry['transaction']
    return {V.PROJECT: {'row': entry['admission'].row, 'before': transaction['before'],
        'candidate': transaction['candidate'],
        'reviewed_face_refs': [deepcopy(transaction['context']['face_ref'])]}}


def _targets(engine, entry, current):
    # Read-only viewing also has a complete closure even though its graph is a
    # no-op. A mutation additionally checks the actual ledger enumerator below.
    ref = entry['transaction']['context']['face_ref']; result = {}
    for index, row in enumerate(entry['batch'].documents.rows()):
        if V.scope(row) != V.PROJECT: continue
        source = SOURCE.row_proof({**row, 'state': current} if row is entry['admission'].row else row)
        if source['asset_sha256'] != ref['asset_sha256']: continue
        version = entry['batch'].versions.check_advance(row)
        result[str(index)] = {'path': row['path'], 'document_id': version.document_id,
            'revision': version.revision, 'asset_sha256': ref['asset_sha256'],
            'people_scope': V.PROJECT, 'source_proof': source, 'reviewed_face_refs': [deepcopy(ref)]}
    if not entry['transaction']['no_change']:
        if result != CLOSURE._targets(engine, entry['batch'], _plans(entry), current):
            raise ValueError('Recovery review differs from the complete scoped ledger closure')
    return result


def _identity(engine, row, recipe, version, transaction):
    from .full_candidate_render import identity
    from .local_mask_state import file_stamp
    staged = EYE._context(engine, row, transaction)
    args = (engine, row, recipe, version.document_id, str(version.revision))
    before, _, _ = identity(*args, people_graph=transaction['before'])
    after, _, _ = identity(*args, people_graph=transaction['candidate'], staged_people_context=staged)
    return {'before': before, 'after': after, 'path_stamp': list(file_stamp(row['path']))}, staged


def _display(rgb, proof):
    from .portrait_review_render import preview_size
    data, size = EYE._display(rgb, proof, _size=preview_size(proof['output_size']))
    encoded = data.removeprefix('data:image/png;base64,'); raw = base64.b64decode(encoded, validate=True)
    from .portrait_review_render import MAX_PNG_BYTES
    if len(raw) > MAX_PNG_BYTES:
        raise ValueError('Eye-bag recovery image exceeds bounded transport; no member was omitted')
    metadata = {'mime': 'image/png', 'width': size[0], 'height': size[1], 'sha256': sha256(raw).hexdigest()}
    return metadata, {**metadata, 'base64': encoded}


def _cache(engine):
    value = engine.__dict__.get('_eye_bag_recovery_alias_images')
    if value is None:
        from .collarbone_visual_store import _Images
        value = engine._eye_bag_recovery_alias_images = _Images(records=lambda plan: plan.records)
    return value


def _plan(entry):
    review = entry['review']
    return SimpleNamespace(token=review['token'], records={member['visual']['document_id']: member['visual']
        for member in review['members']})


def discard(engine, entry):
    if type(entry) is dict and entry.get('seal') is _SEAL:
        entry['cancelled'] = True
        _cache(engine).discard(entry['review']['token'])


def verify(engine, entry, transaction=None):
    if (type(entry) is not dict or entry.get('seal') is not _SEAL or entry.get('cancelled')
            or entry.get('claimed') or time.monotonic() >= entry['expires']):
        raise ValueError('Shared recovery review is expired, canceled or already claimed')
    retained = entry['transaction']
    if transaction is not None and _retained(transaction) != retained:
        raise ValueError('Recovery candidate differs from every displayed alias')
    live = validate_admission(engine, entry['admission'], retained['before'], retained['context']['face_ref'])
    if (engine._batch_controller() is not entry['batch'] or engine._people_support != entry['before_assets']
            or _dormant_key(engine, live[1]) != entry['dormant_key']):
        raise ValueError('Shared recovery context or retained source closure changed')
    _narrow(retained, entry['before_assets'])
    members = CLOSURE._eligible(engine, live[1], live[2], live[3]['asset_sha256'])
    if len(members) != len(entry['members']):
        raise ValueError('Shared recovery requires every exact affected member')
    for actual, frozen in zip(members, entry['members']):
        row, recipe, proof, version = actual; visual = frozen['visual']
        if (row is not frozen['row'] or row['path'] != frozen['path']
                or version.document_id != visual['document_id'] or str(version.revision) != visual['revision']
                or proof != visual['source_proof']
                or _identity(engine, row, recipe, version, retained)[0] != frozen['identity']):
            raise ValueError('Shared recovery source, repair, crop, support or member revision changed')
        SOURCE.verify_row({**row, 'state': recipe}, proof)
    if _targets(engine, entry, live[2]) != entry['targets']:
        raise ValueError('Shared recovery ledger target set changed')
    if digest({key: value for key, value in entry['review'].items() if key != 'review_sha256'}) != entry['review']['review_sha256']:
        raise ValueError('Shared recovery review digest changed')
    return live


def preview(engine, transaction, permit, *, viewing=False):
    from .full_candidate_render import render
    before_assets = deepcopy(engine._people_support)
    _narrow(transaction, before_assets)
    if transaction['no_change'] and not viewing:
        raise ValueError('This recovery gesture has no canonical change; no alias revision was claimed')
    live = validate_admission(engine, permit, transaction['before'], transaction['context']['face_ref'])
    members = CLOSURE._eligible(engine, live[1], live[2], live[3]['asset_sha256'])
    entry = {'seal': _SEAL, 'admission': permit, 'transaction': _retained(transaction),
        'before_assets': before_assets, 'batch': engine._batch_controller(), 'members': [],
        'dormant_key': _dormant_key(engine, live[1]), 'served': set(), 'claimed': False,
        'cancelled': False, 'expires': time.monotonic() + TTL}
    entry['targets'] = _targets(engine, entry, live[2])
    if ({target['document_id'] for target in entry['targets'].values()} != {item[3].document_id for item in members}
            or len(entry['targets']) != len(members)):
        raise ValueError('Recovery ledger includes an unavailable or unreviewed alias')
    public = []; displays = {}; common_source = None
    for row, recipe, source, version in members:
        frozen, staged = _identity(engine, row, recipe, version, transaction)
        args = (engine, row, recipe, version.document_id, str(version.revision))
        rgb, left_proof = render(*args, people_graph=transaction['before'])
        left, left_image = _display(rgb, left_proof); del rgb
        rgb, right_proof = render(*args, people_graph=transaction['candidate'], staged_people_context=staged)
        right, right_image = _display(rgb, right_proof); del rgb
        if (left_proof['source_proof'] != source or right_proof['source_proof'] != source
                or left_proof['source_size'] != right_proof['source_size']
                or left_proof['output_size'] != right_proof['output_size']
                or (common_source is not None and common_source != left_proof['source_size'])
                or _identity(engine, row, recipe, version, transaction)[0] != frozen):
            raise ValueError('Recovery alias full render changed its actual member source or geometry')
        for side, rendered in (('before', left_proof), ('after', right_proof)):
            if {key: rendered[key] for key in frozen[side]} != frozen[side]:
                raise ValueError('Recovery alias full render differs from its immutable candidate proof')
        common_source = left_proof['source_size']
        visual = {'version': 1, 'document_id': version.document_id, 'revision': str(version.revision),
            'source_proof': source, 'before_state_sha256': left_proof['candidate_sha256'],
            'candidate_state_sha256': right_proof['candidate_sha256'],
            'before_people_sha256': left_proof['people_sha256'], 'candidate_people_sha256': right_proof['people_sha256'],
            'source_size': common_source, 'before_output_size': left_proof['output_size'],
            'after_output_size': right_proof['output_size'], 'before': left, 'after': right}
        public.append({'path': row['path'], 'visual': visual})
        entry['members'].append({'row': row, 'path': row['path'], 'visual': visual, 'identity': frozen})
        displays[version.document_id] = {'revision': visual['revision'], 'before': left_image, 'after': right_image}
    ref = transaction['context']['face_ref']; face = ref['face_instance_id']
    def recovery_key(graph):
        return (graph['faces'][face]['local_assets'].get(TARGET) or {}).get('content_sha256')
    review = {'version': 2, 'token': uuid.uuid4().hex, 'target': TARGET, 'face_ref': deepcopy(ref),
        'before_recovery_sha256': recovery_key(transaction['before']),
        'recovery_sha256': recovery_key(transaction['candidate']), 'visual': deepcopy(public[0]['visual']), 'members': public}
    review['review_sha256'] = digest(review); entry['review'] = review
    verify(engine, entry)
    cache = _cache(engine); cache.prune({}); cache.attach(_plan(entry), displays)
    try:
        verify(engine, entry)
        return {'domain': 'production-output', 'quality': 'full-source-render-srgb8',
            'note': '每张受影响照片均使用自己的完整配方、修复和裁剪渲染；仅恢复眼袋 v2 贡献。RGB8 缩小显示，非原生像素验收。',
            'review': deepcopy(review)}, entry
    except Exception:
        discard(engine, entry)
        raise


def acknowledgment(entry):
    return CLOSURE._ack(entry['review'])


def check_ack(value):
    CLOSURE.check_ack(value)


def confirm(engine, entry, ack, transaction=None):
    check_ack(ack); verify(engine, entry, transaction)
    if ack != acknowledgment(entry):
        raise ValueError('Confirm every exact recovery alias image pair in the frozen order')
    required = {(member['visual']['document_id'], side) for member in entry['members'] for side in ('before', 'after')}
    if entry['served'] != required:
        raise ValueError('Load every affected recovery alias before/after before confirming')
    cache = _cache(engine); plan = _plan(entry)
    for document, visual in plan.records.items():
        for side in ('before', 'after'):
            cache.read(plan, document, visual['revision'], side, visual[side]['sha256'])
    verify(engine, entry, transaction)


def image(engine, entry, request):
    verify(engine, entry)
    review = entry['review']; document = request['member_document_id']; side = request['side']
    if request['review_sha256'] != review['review_sha256']:
        raise ValueError('Recovery image belongs to another complete review')
    visual = _plan(entry).records.get(document)
    if (visual is None or request['member_revision'] != visual['revision']
            or request['sha256'] != visual[side]['sha256']):
        raise ValueError('Recovery image does not belong to the exact member revision')
    pixels = _cache(engine).read(_plan(entry), document, visual['revision'], side, request['sha256'])
    verify(engine, entry); entry['served'].add((document, side))
    return pixels
