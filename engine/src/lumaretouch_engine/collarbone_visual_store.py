# SPDX-License-Identifier: GPL-3.0-or-later
"""Session-only, bounded immutable display blobs for collarbone batch review.

PNG reductions are never project assets, source pixels, history or effect masks.
Only random private filenames are used. Tokens/documents never become paths.
All runtime/filesystem behavior and fixture acceptance are UNRUN.
"""
from base64 import b64decode, b64encode
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
import uuid

MAX_BYTES = 128 * 1024 * 1024
MAX_IMAGES = 256
REQUEST_FIELDS = {'cmd', 'action', 'request_id', 'preflight_token', 'document_id', 'revision', 'side', 'sha256'}


def _records(plan):
    from .collarbone_transfer_review import checked
    params = plan.params().get('_people_transfer')
    cohort = type(params) is dict and params.get('mode') == 'persistent_association'
    required = (params.get('collarbone_visual_required') is True if cohort
                else 'lnx.collarbone.v1' in plan.modules)
    if type(params) is not dict or not required:
        raise ValueError('Collarbone images require their actual frozen people or complete-cohort review')
    if cohort and (not plan.targets or plan.targets[0].document_id != plan.source_id
                   or any(target.blocked for target in plan.targets)):
        raise ValueError('Collarbone cohort images require the source first and every atomic member')
    if len(plan.targets) > 16:
        raise ValueError('Collarbone image set exceeds its complete reviewed target bound')
    out = {}
    for target in plan.targets:
        if target.blocked: continue
        record = checked(json.loads(target.people_json)['collarbone_visual'])
        if (record['document_id'] != target.document_id or record['revision'] != str(target.revision)
                or target.document_id in out):
            raise ValueError('Frozen collarbone image identity is inconsistent')
        out[target.document_id] = record
    return out


class _Images:
    def __init__(self, records=None):
        self.records = _records if records is None else records
        self.directory = tempfile.TemporaryDirectory(prefix='lumaretouch-collarbone-review-')
        self.plans = {}
        self.bytes = 0
        self.count = 0

    def discard(self, token):
        rows = self.plans.get(token, {})
        for document, row in list(rows.items()):
            for side, entry in list(row.items()):
                try: entry['path'].unlink(missing_ok=True)
                except OSError: continue  # Retain reservation and retry on next prune.
                self.bytes -= entry['bytes']; self.count -= 1
                del row[side]
            if not row: del rows[document]
        if not rows: self.plans.pop(token, None)

    def prune(self, pending):
        for token in list(self.plans):
            if token not in pending: self.discard(token)

    def attach(self, plan, display_map):
        from .collarbone_transfer_review import MAX_PNG_BYTES
        records = self.records(plan)
        if type(display_map) is not dict or set(display_map) != set(records):
            raise ValueError('Every eligible collarbone target requires both immutable review images')
        if plan.token in self.plans:
            raise ValueError('Collarbone visual token already owns immutable images')
        staged = {}
        try:
            for document, record in records.items():
                display = display_map[document]
                if type(display) is not dict or set(display) != {'revision', 'before', 'after'} or display['revision'] != record['revision']:
                    raise ValueError('Collarbone display map has a different target revision')
                staged[document] = {}
                for side in ('before', 'after'):
                    image = display[side]; compact = record[side]
                    if (type(image) is not dict or set(image) != set(compact) | {'base64'}
                            or any(image[key] != value for key, value in compact.items())
                            or type(image['base64']) is not str):
                        raise ValueError('Collarbone display pixels do not match the frozen image metadata')
                    encoded = image['base64']
                    if len(encoded) > 4 * ((MAX_PNG_BYTES + 2) // 3):
                        raise ValueError('Collarbone review image exceeds its individual transport budget')
                    raw = b64decode(encoded, validate=True)
                    if (not raw or len(raw) > MAX_PNG_BYTES or b64encode(raw).decode('ascii') != encoded
                            or sha256(raw).hexdigest() != compact['sha256']):
                        raise ValueError('Collarbone review image bytes failed immutable content verification')
                    if (self.bytes + len(raw) > MAX_BYTES or self.count + 1 > MAX_IMAGES):
                        raise ValueError('Collarbone session image budget is full; finish or expire older reviews, no target detail was reduced')
                    path = Path(self.directory.name) / (uuid.uuid4().hex + '.png')
                    # Reserve even if the write/cleanup fails; never undercount
                    # abandoned bytes after a filesystem error.
                    staged[document][side] = {'path': path, 'bytes': len(raw), 'metadata': dict(compact), 'revision': record['revision']}
                    self.bytes += len(raw); self.count += 1
                    # Exclusive creation, fixed private directory, no caller filename.
                    with path.open('xb') as stream:
                        stream.write(raw)
            self.plans[plan.token] = staged
        except Exception:
            self.plans[plan.token] = staged
            self.discard(plan.token)
            raise

    def read(self, plan, document, revision, side, digest):
        record = self.records(plan).get(document)
        row = self.plans.get(plan.token, {}).get(document)
        if (record is None or row is None or side not in ('before', 'after')
                or revision != record['revision'] or digest != record[side]['sha256']):
            raise ValueError('Collarbone image does not belong to this pending token, target, revision and side')
        entry = row.get(side)
        if (entry is None or entry['revision'] != revision or entry['metadata'] != record[side]
                or not entry['path'].is_file() or entry['path'].is_symlink()):
            raise ValueError('Collarbone review image is unavailable; create a fresh review')
        with entry['path'].open('rb') as stream:
            raw = stream.read(entry['bytes'] + 1)
        if len(raw) != entry['bytes'] or sha256(raw).hexdigest() != digest:
            raise ValueError('Collarbone cached image changed; create a fresh review')
        return {**entry['metadata'], 'base64': b64encode(raw).decode('ascii')}


def prune(store):
    cache = getattr(store, '_collarbone_visual_images', None)
    if cache is not None: cache.prune(store.pending)


def attach(store, plan, display_map):
    store._prune(store.clock()); prune(store)
    if store.pending.get(plan.token) is not plan:
        raise ValueError('Collarbone visual attachment requires its actual live frozen plan')
    from .cohort_image_cache import cache as shared_cache
    _records(plan)  # This wrapper retains collarbone proof authority.
    cache = shared_cache(store)
    cache.attach(plan, display_map)


def verify_available(store, plan):
    store._prune(store.clock()); prune(store)
    if store.pending.get(plan.token) is not plan:
        raise ValueError('Collarbone visual plan expired or was consumed')
    cache = getattr(store, '_collarbone_visual_images', None)
    if cache is None: raise ValueError('Collarbone visual cache is unavailable')
    for document, record in _records(plan).items():
        for side in ('before', 'after'):
            cache.read(plan, document, record['revision'], side, record[side]['sha256'])


def retrieve(controller, request):
    if (type(request) is not dict or set(request) != REQUEST_FIELDS or request.get('cmd') != 'batch'
            or request.get('action') != 'collarbone_visual' or request.get('side') not in ('before', 'after')
            or type(request.get('request_id')) is not str or not 1 <= len(request['request_id']) <= 128
            or type(request.get('document_id')) is not str or not 1 <= len(request['document_id']) <= 128
            or type(request.get('revision')) is not str or re.fullmatch('(0|[1-9][0-9]{0,19})', request['revision']) is None
            or int(request['revision']) > 2**64 - 1 or type(request.get('sha256')) is not str
            or re.fullmatch('[a-f0-9]{64}', request['sha256']) is None):
        raise ValueError('Collarbone image reads require exact token, document, revision, side, digest and request identity')
    try:
        plan = controller.store.get(request['preflight_token'], controller.versions.workspace)
    finally:
        # get() expires pending entries before raising: release their blobs in
        # this same failed read, not only after a later successful request.
        prune(controller.store)
    cache = getattr(controller.store, '_collarbone_visual_images', None)
    if cache is None: raise ValueError('Collarbone review images are no longer retained')
    _records(plan)  # Shared pixels never authorize a different proof family.
    image = cache.read(plan, request['document_id'], request['revision'], request['side'], request['sha256'])
    return {'event': 'batch_result', 'action': 'collarbone_visual', 'success': True,
            **{key: request[key] for key in ('request_id', 'preflight_token', 'document_id', 'revision', 'side', 'sha256')},
            'image': image}
