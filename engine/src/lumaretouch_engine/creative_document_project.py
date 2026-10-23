"""Strict creative records on the existing snapshot/project byte codec.

Live state, named versions, undo/redo, recovery and portable packages all retain
the same immutable records. There is no second history owner; raw chunk sidecars
are only a lossless transport for the canonical byte fields.
Encoded bytes are resolved here, not through project.decode: that generic codec
is deliberately best-effort for unrelated assets, and calling it from its own
creative preflight would recurse. Missing/corrupt creative bytes must never drop.
"""
import base64
import hashlib
from copy import deepcopy
from . import creative_document_assets as A, creative_document_state as S
from .creative_document_assets import AssetStore
from . import creative_document_storage as B

KEY = '_creative_document'
ASSETS_KEY = '_creative_asset_records'
BASE_KEY = '_creative_base'
KEYS = frozenset((KEY, ASSETS_KEY, BASE_KEY))
_RECORD_KEYS = frozenset(('id', 'kind', 'width', 'height', 'encoding', 'alpha',
                          'source_hash', 'icc_hash', 'content', 'original', 'icc'))
_BYTE_LIMITS = {'content': A.MAX_ASSET_BYTES, 'original': A.MAX_ORIGINAL_BYTES,
                'icc': A.MAX_ICC_BYTES}
_UNCHANGED = object()


class _Validation:
    """One bounded, temporary staging store for the complete owned subtree."""
    def __init__(self, assets, max_bytes, blob_cache=None):
        if assets is not None and type(assets) is not dict:
            raise ValueError('Invalid canonical project asset table')
        self.assets = assets
        self.store = AssetStore(max_bytes)
        self.records = {}
        self.blobs = {} if blob_cache is None else blob_cache

    def blob(self, value, limit):
        if type(value) is bytes:
            if len(value) > limit:
                raise ValueError('Creative asset byte budget exceeded')
            return value
        if type(value) is dict and B.MARKER in value:
            return B.decode_bytes(value, self.assets, limit=limit, cache=self.blobs)
        if (self.assets is None or type(value) is not dict
                or set(value) not in ({'__asset__'}, {'__asset__', 'at'})
                or ('at' in value and type(value['at']) is not str)):
            raise ValueError('Creative bytes require a canonical immutable asset')
        identity = value.get('__asset__')
        if (type(identity) is not str or len(identity) != 71
                or not identity.startswith('sha256:')
                or any(c not in '0123456789abcdef' for c in identity[7:])):
            raise ValueError('Invalid creative canonical asset identity')
        row = self.assets.get(identity)
        if (type(row) is not dict
                or set(row) != {'kind', 'shape', 'dtype', 'bytes', 'b64'}
                or row['kind'] != 'bytes' or row['shape'] is not None
                or row['dtype'] is not None):
            raise ValueError('Missing or non-byte creative canonical asset')
        size = row['bytes']
        if (type(size) is not int or not 0 <= size <= limit
                or type(row['b64']) is not str
                or len(row['b64']) != 4 * ((size + 2) // 3)):
            raise ValueError('Creative canonical asset byte budget/length mismatch')
        if identity not in self.blobs:
            raw = base64.b64decode(row['b64'], validate=True)
            if len(raw) != size or hashlib.sha256(raw).hexdigest() != identity[7:]:
                raise ValueError('Creative canonical asset byte digest mismatch')
            self.blobs[identity] = raw
        return self.blobs[identity]

    def record(self, value):
        if type(value) is not dict or set(value) != _RECORD_KEYS:
            raise ValueError('Malformed creative project asset record')
        # Reject malformed headers before decoding potentially large byte fields.
        w, h = A.dimension(value['width']), A.dimension(value['height'])
        if w * h > A.MAX_PIXELS or value['kind'] not in ('rgba', 'mask'):
            raise ValueError('Creative project asset pixel budget/kind mismatch')
        if any(type(value[key]) is not str for key in
               ('id', 'kind', 'encoding', 'alpha', 'source_hash', 'icc_hash')):
            raise ValueError('Invalid creative project asset header')
        record = dict(value)
        expected = w * h * (4 if value['kind'] == 'rgba' else 1) * 4
        for key, limit in _BYTE_LIMITS.items():
            record[key] = self.blob(value[key], min(limit, expected) if key == 'content' else limit)
        identity = record['id']
        previous = self.records.get(identity)
        if previous is None:
            # Validates exact byte length, hashes, ICC/source bytes, finite linear
            # pixels, premultiplied alpha and the complete immutable record ID.
            self.store.intern(record)
            self.records[identity] = record
        elif previous != record:
            raise ValueError('Conflicting creative project asset identity')
        return record


class _FrameAssets:
    """A document may reference only its frame, not another frame's assets."""
    def __init__(self, records):
        self.records = records

    def get(self, identity, kind=None):
        if type(identity) is not str or identity not in self.records:
            raise ValueError('Missing creative content-addressed frame asset')
        record = self.records[identity]
        if kind is not None and record['kind'] != kind:
            raise ValueError('Creative frame asset kind mismatch')
        return deepcopy(record)


def _stage(snapshot, validation):
    if type(snapshot) is not dict:
        raise ValueError('Invalid creative history frame')
    if KEYS.intersection(snapshot) and {'__asset__', '__dc__', '__custom_cube__', B.MARKER}.intersection(snapshot):
        raise ValueError('Creative snapshot cannot also be a codec marker')
    document = snapshot.get(KEY)
    records = snapshot.get(ASSETS_KEY, {})
    if type(records) is not dict or len(records) > 2 * S.MAX_LAYERS + 1:
        raise ValueError('Missing or excessive creative project asset records')
    if document is None:
        if records:
            raise ValueError('Orphan creative project assets')
    elif (type(document) is not dict or set(document) != S.ROOT_KEYS
          or type(document.get('schema')) is not int or document['schema'] != 1
          or ASSETS_KEY not in snapshot):
        raise ValueError('Malformed or unsupported creative project document')
    decoded = {}
    for identity, record in records.items():
        if type(identity) is not str or type(record) is not dict or record.get('id') != identity:
            raise ValueError('Creative project asset key mismatch')
        decoded[identity] = validation.record(record)
    if document is not None:
        S.validate(document, _FrameAssets(decoded))
        if set(decoded) != S.references(document):
            raise ValueError('Creative project has unreferenced or missing assets')
    base = snapshot.get(BASE_KEY)
    if base is not None:
        base = validation.record(base)
        if base['kind'] != 'rgba':
            raise ValueError('Creative base must be a standalone RGBA asset')
        from .creative_derived_global_recovery import validate_state
        validate_state({**snapshot, BASE_KEY: base})
    return document


def capture_into(snapshot, document, assets, *, base=_UNCHANGED):
    """Capture on the host's unified history; preserve any already returned base."""
    if type(snapshot) is not dict:
        raise ValueError('Invalid creative snapshot')
    out = dict(snapshot)
    if document is None:
        out.pop(KEY, None)
        out.pop(ASSETS_KEY, None)
    else:
        S.validate(document, assets)
        out[KEY] = deepcopy(document)
        out[ASSETS_KEY] = assets.records(S.references(document))
    if base is not _UNCHANGED:
        out[BASE_KEY] = deepcopy(base)
    elif BASE_KEY in out:
        out[BASE_KEY] = deepcopy(out[BASE_KEY])
    restore_from(out)
    return out


def encode_record(record, assets):
    """Chunk canonical bytes without altering source pixels, headers or IDs."""
    if type(record) is not dict or set(record) != _RECORD_KEYS:
        raise ValueError('Malformed creative project asset record')
    return {key: B.encode_bytes(value, assets) if key in _BYTE_LIMITS else value
            for key, value in record.items()}


def restore_from(snapshot, *, max_bytes=A.MAX_STORE_BYTES):
    """Validate decoded state before publishing; absent fields stay neutral.

    The returned store includes an optional standalone base even when the layer
    document is absent. The host still owns the snapshot and all undo/redo lists.
    """
    validation = _Validation(None, max_bytes)
    document = _stage(snapshot, validation)
    return deepcopy(document), validation.store


def validate_records(value, *, assets=None, allowed=True, max_bytes=A.MAX_STORE_BYTES,
                     blob_cache=None):
    """Check all active/inactive/nested records, decoding canonical refs first.

    No migration, dropped assets, mutation, image decoder or native renderer.
    Assets are deduplicated across frames under one byte budget, but each frame
    must independently own every document reference. Legacy missing fields need
    no migration; present creative fields require the current project schema.
    """
    validation = _Validation(assets, max_bytes, blob_cache)
    pending = [(value, 0)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if depth > 128 or nodes > 2_000_000:
            raise ValueError('Creative project nesting/node budget exceeded')
        if isinstance(current, dict):
            if B.MARKER in current:
                raise ValueError('Creative byte chunks must belong to a validated creative record')
            if KEYS.intersection(current):
                if not allowed:
                    raise ValueError('Creative records require project v23; schema downgrade is not allowed')
                _stage(current, validation)
            pending.extend((child, depth + 1) for key, child in current.items()
                           if key not in KEYS and isinstance(child, (dict, list, tuple)))
        elif isinstance(current, (list, tuple)):
            pending.extend((child, depth + 1) for child in current
                           if isinstance(child, (dict, list, tuple)))
    return validation.store


def validate_history_frames(frames, *, max_bytes=A.MAX_STORE_BYTES):
    """Validate decoded live plus up to 64 undo and 64 redo frames together."""
    if type(frames) is not list or len(frames) > 129 or any(type(frame) is not dict for frame in frames):
        raise ValueError('Creative history frame budget/shape exceeded')
    return validate_records(frames, max_bytes=max_bytes)
