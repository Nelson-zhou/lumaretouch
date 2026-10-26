# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded .lrtcolour snapshot, not the generic text-preset catalogue.

Only small canonical intent/identity metadata crosses the native boundary. The
preflight owner retains the exact archive bytes before Start consent; inference
is deferred until the authorized run. Original paths are never reread as a
substitute for retained bytes. Source authored only; acceptance is UNRUN.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

from . import semantic_colour_preset as E, semantic_colour_portable as P
from . import workflow_owner_protocol as W

FIELDS = ('path', 'file_bytes', 'file_sha256', 'intent_sha256', 'portable_intent_json')


def metadata(value):
    value = W.record(value, FIELDS)
    W.I.path(value['path'])
    if Path(value['path']).suffix.lower() != '.lrtcolour':
        raise ValueError('Automatic semantic colour requires an explicit .lrtcolour archive')
    E._integer(value['file_bytes'], E.MAX_FILE_BYTES)
    W.I.digest(value['file_sha256']); W.I.digest(value['intent_sha256'])
    W.text(value['portable_intent_json'], E.MAX_MANIFEST_BYTES)
    intent = P.check(json.loads(value['portable_intent_json'], object_pairs_hook=E._no_duplicate_keys))
    # Preserve exact numeric JSON bytes through JavaScript/Rust; JSON Number
    # round trips would rewrite integral floats and break the graph identity.
    if W.encoded(intent, sorted_keys=True).decode('utf-8') != value['portable_intent_json']:
        raise ValueError('Portable semantic intent must retain its canonical JSON bytes')
    if W.digest(intent) != value['intent_sha256']:
        raise ValueError('Semantic portable intent digest differs from its complete intent')
    return value


class FrozenArchive:
    def __init__(self, path, expected=None):
        self.path = None
        W.I.path(path)
        if Path(path).suffix.lower() != '.lrtcolour':
            raise ValueError('Select a .lrtcolour archive, not a generic preset')
        from .cpu_memory_budget import available_estimate
        from . import reference_color_assets as A
        if available_estimate() < 2*A.MAX_RAW_BYTES + 2*A.MAX_BYTES + 128*1024*1024:
            raise ValueError('Complete semantic reference archive verification exceeds memory budget')
        self.path = None
        self._cache = None
        self._analysis_started = False
        source, size = E._open_regular(path, E.MAX_FILE_BYTES)
        try:
            with source:
                before = os.fstat(source.fileno())
                fd, self.path = tempfile.mkstemp(prefix='workflow-semantic-', suffix='.lrtcolour')
                digest = sha256(); total = 0
                with os.fdopen(fd, 'wb') as output:
                    while raw := source.read(1024*1024):
                        total += len(raw)
                        if total > E.MAX_FILE_BYTES:
                            raise ValueError('Semantic archive grew beyond its byte budget')
                        digest.update(raw); output.write(raw)
                    output.flush(); os.fsync(output.fileno())
                after = os.fstat(source.fileno())
                if total != size or any(getattr(before, key) != getattr(after, key)
                        for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')):
                    raise ValueError('Semantic archive changed while its exact bytes were captured')
            envelope = E.load_file(self.path)
            intent = P.check(envelope['intent'])
            self.metadata = metadata({'path': path, 'file_bytes': total,
                'file_sha256': digest.hexdigest(), 'intent_sha256': W.digest(intent), 'portable_intent_json': W.encoded(intent, sorted_keys=True).decode('utf-8')})
            if expected is not None and self.metadata != metadata(expected):
                raise ValueError('Selected semantic archive bytes/intent changed; reselect and reconfirm Start')
            # Authentic full float image + provenance, no model or target fit.
            E.hydrate(envelope)
            self.intent = deepcopy(intent)
            self.bundle = envelope['chunks']
            self.assert_current()
        except BaseException:
            self.close()
            raise

    def assert_current(self):
        if (self.path is None or E._file_identity(self.path) !=
                {key: self.metadata[key] for key in ('file_bytes', 'file_sha256')}
                or W.digest(self.intent) != self.metadata['intent_sha256']):
            raise ValueError('Retained semantic archive identity changed; no replacement is allowed')
        # Verification is hash-only, never a repeated decoder/memory admission.
        from . import reference_color_assets as A
        path = A.cache_root() / (self.intent['reference']['asset_id'] + '.npz')
        if path.is_symlink() or not path.is_file() or A._hash(path) != self.intent['reference']['asset_id']:
            raise ValueError('Retained full reference bytes changed; never substitute or rehydrate')

    def reference_analysis(self):
        self.assert_current()
        if self._cache is None:
            if self._analysis_started:
                raise ValueError('Original reference analysis failed or is uncertain; never silently rerun')
            self._analysis_started = True
            from .semantic_colour_batch_target import reference_analysis
            self._cache = reference_analysis(self.intent, self.bundle)
        from .semantic_colour_batch_fit import check_reference
        checked = check_reference(self._cache)
        if checked['reference'] != self.intent['reference']:
            raise ValueError('Reference analysis belongs to another retained archive')
        self.assert_current()
        return checked

    def close(self):
        path, self.path = self.path, None
        if path is not None:
            try: os.unlink(path)
            except FileNotFoundError: pass
        self.bundle = None
        self._cache = None

    def __del__(self):
        try: self.close()
        except OSError: pass


def inspect(path):
    archive = FrozenArchive(path)
    try: return deepcopy(archive.metadata)
    finally: archive.close()
