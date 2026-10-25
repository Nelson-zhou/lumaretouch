# SPDX-License-Identifier: GPL-3.0-or-later
"""Session-only full-image scalar preset review, never an application owner.

The caller owns the workflow journal, the loaded document lease and serialized
normal PresetController dispatch. This owner only retains genuine image evidence
and consumes one exact user approval. Runtime/numerical acceptance is UNRUN.
"""
from base64 import b64decode, b64encode
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
import json
import math
import re
import struct
from threading import RLock
import time
import uuid

SCHEMA = 'lrt.workflow-preset-review.v1'
APPROVAL_SCHEMA = 'lrt.workflow-preset-approval.v1'
SUPPORTED_MODULES = frozenset(('lnx.exposure.v1', 'lnx.white_balance.v1', 'lnx.skin.v1'))
TTL = 15 * 60
MAX_REVIEWS = 64
MAX_ACTIVE_REVIEWS = 8
MAX_CACHE_BYTES = 32 * 1024 * 1024
MAX_PNG_BYTES = 4 * 1024 * 1024
PAGE_BYTES = 64 * 1024
TARGET_FIELDS = {'document_id', 'load_id', 'revision'}
ACK_FIELDS = {'review_id', 'review_sha256', 'target', 'preset_id', 'preset_sha256',
              'before_sha256', 'after_sha256', 'accepted'}


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def _hash(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('Review content requires an exact lowercase SHA-256')
    return value


def _token(value):
    if type(value) is not str or re.fullmatch('[A-Za-z0-9._:-]{1,128}', value) is None:
        raise ValueError('Review requires a bounded exact identity')
    return value


def check_target(value):
    if type(value) is not dict or set(value) != TARGET_FIELDS:
        raise ValueError('Review target must contain stable document ID, load ID and revision')
    _token(value['document_id']); _token(value['load_id'])
    revision = value['revision']
    if (type(revision) is not str or re.fullmatch('(0|[1-9][0-9]{0,19})', revision) is None
            or int(revision) > 2**64 - 1):
        raise ValueError('Review requires the current canonical document revision')
    return dict(value)


def support_reason(preset):
    """Stateless recipe admission only; never claims target or image readiness."""
    if type(preset) is not dict or type(preset.get('modules')) is not dict or not preset['modules']:
        return 'invalid_preset_modules'
    if 'xmp_import' in preset:
        return 'xmp_requires_dedicated_review'
    # Recipe admission is not target readiness. Skin must pass the explicit
    # retained-target preparation and canonical people-plan proof before review.
    if set(preset['modules']) - SUPPORTED_MODULES:
        return 'unsupported_workflow_preset_module'
    return None


def _preset(preset_id, preset_sha256):
    from .workflow_preset_catalogue import resolve
    _token(preset_id); _hash(preset_sha256)
    preset = resolve(preset_id, preset_sha256)
    reason = support_reason(preset)
    if reason is not None:
        raise ValueError(reason + ': the complete saved preset is rejected; no module was omitted')
    return preset


def _require_portrait_target(engine, row, before, preset):
    """Read the already prepared canonical owner; never infer inside review."""
    if 'lnx.skin.v1' not in preset['modules']:
        return
    from .workflow_preset_retained_skin import require_target
    require_target(engine, row, before)


def _candidate(before, preset):
    from . import face_decoration_preset_admission as admission, scope
    from .creative_derived_transfer import _same
    from .preset_portrait_review import select
    if select(preset['modules'], state=before) is not None:
        raise ValueError('Retained portrait effects need their dedicated complete preset review owner')
    # Use the identical candidate owner as PresetController, not display math.
    after = admission.candidate(before, preset['modules'])
    admission.require_candidate(before, after, preset['modules'])
    if not _same(scope.apply_modules(before, preset['modules']), after):
        raise ValueError('Scalar review cannot replace unrelated target data, masks, graphs or analysis')
    return after


def _loaded(engine, target):
    """Refuse to establish/activate identities during a supposedly read-only review."""
    from .document_versions import KEY
    from .local_mask_state import file_stamp
    from .virtual_copy_people import current_row
    from .people_preset_plan import require_active_owner
    target = check_target(target)
    row = current_row(engine)
    owner = engine.__dict__.get('_document_version_owner')
    if (type(row) is not dict or row.get('trashed') or owner is None
            or row.get('document_id') != target['document_id']
            or getattr(engine, '_load_id', None) != target['load_id']
            or getattr(engine, '_doc_path', None) != row.get('path')):
        raise ValueError('Open the exact retained target before preset review; no automatic selection occurs')
    value = row.get(KEY)
    if (type(value) is not dict or value.get('owner') != owner.owner or value.get('object') != id(row)
            or value.get('id') != target['document_id'] or type(value.get('revision')) is not int
            or str(value['revision']) != target['revision']
            or type(row.get('document_revision')) is not int or row['document_revision'] != value['revision']):
        raise ValueError('Target identity is missing, replaced or stale; review cannot initialise its fence')
    if row.get('_local_source_stamp') != file_stamp(row['path']):
        raise ValueError('Target source changed after its actual load; reopen it before reviewing')
    reason = engine._guard_editable('workflow preset image review')
    if reason:
        raise ValueError(reason)
    people_owner = require_active_owner(engine)
    return row, owner, people_owner, engine.__dict__['_people_active_context']


def _proof(engine, row, state, target):
    from . import full_candidate_render as full, creative_derived_source as source
    from .creative_derived_repairs import stack_digest
    from .optics_candidate_identity import fingerprint
    from .people_export import isolated_snapshot, verify_source
    source.verify_precompute(state, state.get('_precompute'))
    repairs = stack_digest(state)
    proof, graph, context = full.identity(engine, row, state, target['document_id'], target['revision'])
    snapshot = engine._state_to_export_snap(state, device='cpu', scale=1, upscale_backend='lanczos3',
        sharpen=0., source_path=row['path'], people_graph=graph, people_context=context,
        people_document_id=target['document_id'])
    verify_source(snapshot, row['path'])
    snapshot = isolated_snapshot(snapshot, for_document=True)
    # No requirement that a plain photo invent a nonempty portrait graph. The
    # full context is nevertheless hashed, and existing portrait data may not vanish.
    asset = proof['source_proof']['asset_sha256']
    retained_people = (any(face['asset_sha256'] == asset for face in graph['faces'].values())
        or any(item['asset_sha256'] == asset and item['status'] == 'unresolved' for item in graph['unresolved_legacy'])
        or any(item['scope'] == 'all_people' and item['target_id'] == asset for item in graph['overrides']))
    people = snapshot.get('people')
    if (people is None and retained_people) or (people is not None and people['state'] != graph):
        raise ValueError('Complete scalar snapshot changed its retained target people graph')
    return {'render': proof, 'repair_sha256': repairs, 'snapshot_sha256': fingerprint(snapshot),
            'people_present': people is not None}, graph


def _dimensions(value):
    if (type(value) is not list or len(value) != 2
            or any(type(x) is not int or not 1 <= x <= 2**32 - 1 for x in value)
            or value[0] * value[1] > 32_000_000):
        raise ValueError('Full preset review dimensions exceed their genuine render budget')
    return value


def _image(engine, row, state, graph, target, expected, cancelled):
    from .portrait_review_render import image, preview_size
    # A graph-free derived photo must not invent portrait data merely because
    # the shared renderer accepts an optional candidate graph argument.
    selected_graph = graph if expected['people_present'] else None
    compact, display, proof = image(engine, row, state, selected_graph, target['document_id'],
                                    target['revision'], cancelled=cancelled)
    if (type(proof) is not dict or set(proof) != set(expected['render']) | {'source_size', 'output_size'}
            or {key: proof[key] for key in expected['render']} != expected['render']):
        raise ValueError('Rendered pixels do not belong to the exact full target state')
    _dimensions(proof['source_size']); _dimensions(proof['output_size'])
    if (type(compact) is not dict or set(compact) != {'mime', 'width', 'height', 'sha256'}
            or compact['mime'] != 'image/png' or type(compact['width']) is not int
            or type(compact['height']) is not int
            or (compact['width'], compact['height']) != preview_size(proof['output_size'])
            or type(display) is not dict or set(display) != set(compact) | {'base64'}
            or any(display[key] != value for key, value in compact.items())
            or type(display['base64']) is not str
            or len(display['base64']) > 4 * ((MAX_PNG_BYTES + 2) // 3)):
        raise ValueError('Full-render display evidence is missing or exceeds its transport bound')
    _hash(compact['sha256'])
    raw = b64decode(display['base64'], validate=True)
    if (not 33 <= len(raw) <= MAX_PNG_BYTES or b64encode(raw).decode('ascii') != display['base64']
            or sha256(raw).hexdigest() != compact['sha256'] or raw[:8] != b'\x89PNG\r\n\x1a\n'
            or raw[8:16] != b'\x00\x00\x00\rIHDR'
            or struct.unpack('>II', raw[16:24]) != (compact['width'], compact['height'])
            or raw[24:29] != b'\x08\x02\x00\x00\x00'):
        raise ValueError('Retained PNG bytes differ from their exact full-render display proof')
    return {**compact, 'byte_length': len(raw), 'page_count': (len(raw) + PAGE_BYTES - 1) // PAGE_BYTES}, raw, proof


class WorkflowPresetReviews:
    """No state replay, graph publication, mutation fence, history or persistence."""
    def __init__(self, engine, *, clock=time.monotonic):
        self.engine = engine
        self.clock = clock
        self._reviews = OrderedDict()
        self._bytes = 0
        self._lock = RLock()

    def _now(self):
        now = self.clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError('Review expiry clock is unavailable')
        return now

    def _release_images(self, record):
        self._bytes -= sum(len(raw) for raw in record['images'].values())
        record['images'] = {}

    def _prune(self):
        now = self._now()
        for key, record in list(self._reviews.items()):
            if now >= record['expires']:
                self._release_images(record)
                del self._reviews[key]

    def _entry(self, review_id, review_sha256):
        _token(review_id); _hash(review_sha256)
        self._prune()
        record = self._reviews.get(review_id)
        if record is None or record['review']['review_sha256'] != review_sha256:
            raise ValueError('Exact preset review is missing or expired; restart never restores approval')
        return record

    def _inputs(self, target, preset):
        row, versions, people_owner, context = _loaded(self.engine, target)
        from .optics_candidate_identity import fingerprint
        def ownership():
            return {'workspace': versions.workspace, 'people_fence': people_owner.fence,
                'row_sha256': fingerprint({key: row.get(key) for key in (
                    'document_id', 'document_revision', 'source_asset_id', 'root_document_id', 'copy_number',
                    'recipe_version_id', 'path', 'src_w', 'src_h', 'fingerprint', 'managed_import',
                    'import_origin', '_local_source_stamp')})}
        owned = ownership()
        before = self.engine._people_preset_capture()
        _require_portrait_target(self.engine, row, before, preset)
        after = _candidate(before, preset)
        if 'lnx.skin.v1' in preset['modules']:
            from .workflow_preset_retained_skin import require_candidate
            require_candidate(self.engine, row, before, after)
        left, graph = _proof(self.engine, row, before, target)
        right, candidate_graph = _proof(self.engine, row, after, target)
        if (left['render']['source_proof'] != right['render']['source_proof']
                or left['render']['people_sha256'] != right['render']['people_sha256']
                or left['repair_sha256'] != right['repair_sha256'] or graph != candidate_graph):
            raise ValueError('Scalar candidate changed target source, repairs or retained people')
        latest = _loaded(self.engine, target)
        if (any(old is not new for old, new in zip((row, versions, people_owner, context), latest))
                or owned != ownership()
                or fingerprint(self.engine._people_preset_capture()) != left['render']['candidate_sha256']):
            raise ValueError('Target changed while checking complete preset review inputs')
        return {'row': row, 'versions': versions, 'people_owner': people_owner, 'context': context,
                'ownership': owned, 'before': left, 'after': right}, before, after, graph

    @staticmethod
    def _same_inputs(left, right):
        return (all(left[key] is right[key] for key in ('row', 'versions', 'people_owner', 'context'))
                and all(left[key] == right[key] for key in ('ownership', 'before', 'after')))

    def _current(self, record, target):
        target = check_target(target)
        review = record['review']
        if target != review['target']:
            raise ValueError('Review does not own this exact stable target, load and revision')
        preset = _preset(review['preset_id'], review['preset_sha256'])
        current, _, _, _ = self._inputs(target, preset)
        if not self._same_inputs(record['inputs'], current):
            raise ValueError('Reviewed state, source, repair, people ownership or complete render inputs changed')
        if self._now() >= record['expires']:
            self._prune()
            raise ValueError('Preset review expired while checking the current target')
        return current

    def prepare(self, preset_id, preset_sha256, target, *, cancelled=lambda: False):
        with self._lock:
            self._prune()
            if (len(self._reviews) >= MAX_REVIEWS
                    or sum(bool(record['images']) for record in self._reviews.values()) >= MAX_ACTIVE_REVIEWS):
                raise ValueError('Preset review session is full; pending evidence is not silently evicted')
            target = check_target(target)
            preset = _preset(preset_id, preset_sha256)
            if cancelled():
                raise InterruptedError('Preset review cancelled before full rendering')
            inputs, before, after, graph = self._inputs(target, preset)
            row = inputs['row']
            a, image_a, left = _image(self.engine, row, before, graph, target, inputs['before'], cancelled)
            if cancelled():
                raise InterruptedError('Preset review cancelled between full renders')
            b, image_b, right = _image(self.engine, row, after, graph, target, inputs['after'], cancelled)
            if left['source_size'] != right['source_size'] or left['output_size'] != right['output_size']:
                raise ValueError('Scalar preset image pair changed source or output geometry')
            fresh = _preset(preset_id, preset_sha256)
            current, _, _, _ = self._inputs(target, fresh)
            if cancelled() or not self._same_inputs(inputs, current):
                raise ValueError('Preset target changed or review was cancelled during complete rendering')
            if self._bytes + len(image_a) + len(image_b) > MAX_CACHE_BYTES:
                raise ValueError('Review image cache is full; no resolution or image detail was reduced')
            review_id = uuid.uuid4().hex
            review = {'schema': SCHEMA, 'review_id': review_id, 'target': target,
                'preset_id': preset_id, 'preset_sha256': preset_sha256,
                'module_ids': sorted(preset['modules']), 'before': a, 'after': b,
                'source_proof': deepcopy(left['source_proof']), 'source_size': left['source_size'],
                'output_size': left['output_size'], 'before_state_sha256': left['candidate_sha256'],
                'candidate_state_sha256': right['candidate_sha256'], 'people_sha256': left['people_sha256'],
                'repair_sha256': inputs['before']['repair_sha256'],
                'before_render_sha256': inputs['before']['snapshot_sha256'],
                'candidate_render_sha256': inputs['after']['snapshot_sha256'],
                'page_bytes': PAGE_BYTES, 'ttl_seconds': TTL, 'approval_only': True, 'runtime_verified': False}
            review['review_sha256'] = _digest(review)
            self._reviews[review_id] = {'review': review, 'inputs': inputs, 'expires': self._now() + TTL,
                'images': {'before': image_a, 'after': image_b}, 'served': {'before': set(), 'after': set()},
                'approval': None, 'consumed': False}
            self._bytes += len(image_a) + len(image_b)
            return deepcopy(review)

    def retrieve(self, review_id, review_sha256, target, side, sha256, page):
        with self._lock:
            record = self._entry(review_id, review_sha256)
            self._current(record, target)
            if record['consumed'] or type(side) is not str or side not in ('before', 'after'):
                raise ValueError('Review image is consumed or has an invalid side')
            metadata = record['review'][side]
            if (_hash(sha256) != metadata['sha256'] or type(page) is not int
                    or not 0 <= page < metadata['page_count']):
                raise ValueError('Image page differs from the exact reviewed pair, side or byte range')
            raw = record['images'].get(side)
            if raw is None or len(raw) != metadata['byte_length'] or _bytes_hash(raw) != sha256:
                raise ValueError('Immutable reviewed image bytes are unavailable')
            start = page * PAGE_BYTES
            chunk = raw[start:start + PAGE_BYTES]
            self._current(record, target)
            record['served'][side].add(page)
            return {'review_id': review_id, 'review_sha256': review_sha256, 'target': dict(target),
                'side': side, **deepcopy(metadata), 'page': page, 'page_bytes': PAGE_BYTES,
                'offset': start, 'page_byte_length': len(chunk), 'page_sha256': _bytes_hash(chunk),
                'base64': b64encode(chunk).decode('ascii')}

    def acknowledge(self, ack):
        with self._lock:
            if type(ack) is not dict or set(ack) != ACK_FIELDS or ack['accepted'] is not True:
                raise ValueError('Explicit user acknowledgment of this exact complete image pair is required')
            record = self._entry(ack['review_id'], ack['review_sha256'])
            review = record['review']
            self._current(record, ack['target'])
            expected = {key: review[key] for key in ('review_id', 'review_sha256', 'target', 'preset_id', 'preset_sha256')}
            expected.update(before_sha256=review['before']['sha256'], after_sha256=review['after']['sha256'], accepted=True)
            if ack != expected or record['consumed']:
                raise ValueError('Acknowledgment is not the exact unconsumed target and saved-preset image pair')
            self._images_available(record, require_served=True)
            if record['approval'] is None:
                receipt = {'schema': APPROVAL_SCHEMA, 'approval_id': uuid.uuid4().hex,
                    **deepcopy(expected), 'approval_only': True, 'runtime_verified': False}
                receipt['approval_sha256'] = _digest(receipt)
                record['approval'] = receipt
            # Duplicate exact ACK reads the retained receipt, never creates more authority.
            return deepcopy(record['approval'])

    @staticmethod
    def _images_available(record, *, require_served):
        for side in ('before', 'after'):
            metadata = record['review'][side]
            raw = record['images'].get(side)
            if raw is None or len(raw) != metadata['byte_length'] or _bytes_hash(raw) != metadata['sha256']:
                raise ValueError('Reviewed image evidence was lost or changed')
            if require_served and record['served'][side] != set(range(metadata['page_count'])):
                raise ValueError('Read every page of both exact before/after images before acknowledging them')

    def consume(self, approval_receipt, target, preset_id, preset_sha256):
        """One-shot authority; caller holds catalogue lock through normal dispatch.

        Call only after the core has journaled ApplyPreset, on the serialized
        command lane. A consumed/missing authority is never permission to retry.
        """
        with self._lock:
            if type(approval_receipt) is not dict:
                raise ValueError('A genuine retained approval receipt is required')
            record = self._entry(approval_receipt.get('review_id'), approval_receipt.get('review_sha256'))
            if record['consumed'] or record['approval'] is None or approval_receipt != record['approval']:
                raise ValueError('Approval is missing, forged or already consumed; query the original operation')
            review = record['review']
            if preset_id != review['preset_id'] or preset_sha256 != review['preset_sha256']:
                raise ValueError('Approval cannot authorize another saved preset or version')
            self._current(record, target)
            self._images_available(record, require_served=True)
            authority = {'approval': deepcopy(record['approval']), 'target': dict(review['target']),
                'preset_id': preset_id, 'preset_sha256': preset_sha256,
                'before_state_sha256': review['before_state_sha256'],
                'candidate_state_sha256': review['candidate_state_sha256'],
                'source_proof': deepcopy(review['source_proof']),
                'preset_command': {'cmd': 'preset', 'action': 'apply', 'id': preset_id,
                                   'document_id': review['target']['load_id']}}
            record['consumed'] = True
            self._release_images(record)
            return authority

    def discard(self, review_id, review_sha256):
        """Release only this session's image evidence; never changes a document."""
        with self._lock:
            record = self._entry(review_id, review_sha256)
            self._release_images(record)
            del self._reviews[review_id]


def _bytes_hash(raw):
    return sha256(raw).hexdigest()
