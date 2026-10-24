# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared target-owned scalar-body review and fixed family routing. AUTHORED / UNRUN.

No candidate installation, live row swap or apply/undo simulation. Only compact
proofs enter histories; PNGs are display reductions of complete float renders.
"""
from copy import deepcopy
from hashlib import sha256
import base64
import io
import re
from dataclasses import dataclass
from types import ModuleType

MAX_TARGETS = 8
PREVIEW_EDGE = 256
MAX_PNG_BYTES = 150000
MAX_BASE64 = 200000
FIELDS = {'version', 'document_id', 'revision', 'source_proof', 'before_sha256',
          'candidate_sha256', 'before_people_sha256', 'candidate_people_sha256',
          'source_size', 'before_output_size', 'after_output_size', 'parameters', 'before', 'after',
          'body_ref', 'associated_face', 'body_support_sha256', 'body_review_sha256',
          'before_bank_sha256', 'candidate_bank_sha256'}
IDENTITY_FIELDS = {'document_id', 'revision', 'source_proof', 'candidate_sha256', 'people_sha256'}


class BodyScalarReview:
    """One complete-render implementation, with explicit family-owned policies.

    The module port keeps the existing torso helper/limit patch points live.
    Runtime providers are fixed source functions, never project import names.
    """
    def __init__(self, *, scope, state, runtime, api, name, label):
        self.scope, self.state, self.runtime, self.api = scope, state, runtime, api
        self.name, self.label = name, label

    def message(self, value):
        return value.replace('Torso-length', self.name.capitalize()).replace(
            'torso-length', self.name).replace('上半身长短', self.label)

    def _hash(self, value):
        if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
            raise ValueError(self.message('Torso-length review requires a SHA-256 identity'))


    def _size(self, value):
        if type(value) is not list or len(value) != 2 or any(type(n) is not int or not 1 <= n <= 2**32-1 for n in value):
            raise ValueError(self.message('Torso-length review requires exact full-source/output dimensions'))


    def _context(self, document, revision):
        if type(document) is not str or not 1 <= len(document) <= 128:
            raise ValueError(self.message('Invalid torso-length review target identity'))
        if (type(revision) is not str or re.fullmatch('(0|[1-9][0-9]{0,19})', revision) is None
                or int(revision) > 2**64-1):
            raise ValueError(self.message('Invalid torso-length review target revision'))


    def _image(self, value, output):
        if type(value) is not dict or set(value) != {'mime', 'width', 'height', 'sha256'} or value['mime'] != 'image/png':
            raise ValueError(self.message('Private torso-length proof must not retain display pixels'))
        w, h = value['width'], value['height']
        if any(type(n) is not int or not 1 <= n <= self.api.PREVIEW_EDGE for n in (w, h)):
            raise ValueError(self.message('Torso-length display exceeds its bounded extent'))
        if w > output[0] or h > output[1] or abs(w*output[1]-h*output[0]) > max(output):
            raise ValueError(self.message('Torso-length display does not match its completed target geometry'))
        self.api._hash(value['sha256'])


    def checked(self, record):
        from .creative_derived_source import check_row_proof
        check_portable = self.scope.check_params
        if type(record) is not dict or set(record) != self.api.FIELDS or type(record['version']) is not int or record['version'] != 1:
            raise ValueError(self.message('Missing exact target torso-length visual review'))
        self.api._context(record['document_id'], record['revision'])
        source = check_row_proof(record['source_proof'])['creative_source']
        for key in ('before_sha256', 'candidate_sha256', 'before_people_sha256', 'candidate_people_sha256',
                    'body_support_sha256', 'body_review_sha256', 'before_bank_sha256', 'candidate_bank_sha256'):
            self.api._hash(record[key])
        if check_portable(record['parameters']) != record['parameters']:
            raise ValueError(self.message('Noncanonical torso-length review parameters'))
        for key in ('source_size', 'before_output_size', 'after_output_size'): self.api._size(record[key])
        if source is not None and [source['width'], source['height']] != record['source_size']:
            raise ValueError(self.message('Torso-length proof belongs to a different derived canvas'))
        self.api._target_proof(record, check_row_proof(record['source_proof'])['asset_sha256'])
        self.api._image(record['before'], record['before_output_size'])
        self.api._image(record['after'], record['after_output_size'])
        return deepcopy(record)


    def rollback_record(self, record, before, revision):
        """Frozen expectation, never a newly observed/rebased people identity."""
        params_of = self.scope.params_of
        value = self.api.checked(record)
        value.update(revision=str(revision), candidate_sha256=value['before_sha256'],
                     candidate_people_sha256=value['before_people_sha256'],
                     candidate_bank_sha256=value['before_bank_sha256'],
                     after_output_size=value['before_output_size'][:],
                     after=deepcopy(value['before']), parameters=params_of(before))
        return self.api.checked(value)


    def acknowledgments(self, raw, records):
        """Exact ordered image acknowledgments, not a generic approve-all boolean."""
        records = [self.api.checked(record) for record in records]
        expected = [{'document_id': r['document_id'], 'revision': r['revision'],
                     'before_sha256': r['before']['sha256'], 'after_sha256': r['after']['sha256']} for r in records]
        if (type(raw) is not list or len(raw) != len(expected) or len(raw) > self.api.MAX_TARGETS
                or len({r['document_id'] for r in records}) != len(records)):
            raise ValueError(self.message('Review every eligible target torso-length image pair before applying'))
        for item, wanted in zip(raw, expected):
            if type(item) is not dict or set(item) != set(wanted) or item != wanted:
                raise ValueError(self.message('Torso-length acknowledgment does not match the frozen target image pair'))
        return deepcopy(expected)


    def _require_retained_people_candidate(self, before, candidate, graph, asset):
        """Legacy preset face overrides are installed only by replay, not this view.

        Refuse that unadapted mixed operation before displaying the wrong candidate.
        A separately committed portrait edit remains part of both full target views.
        """
        if not any(face.get('asset_sha256') == asset for face in graph.get('faces', {}).values()):
            return
        from .optics_candidate_identity import fingerprint
        from . import facial_wrinkle_state as wrinkles
        for state in (before, candidate):
            defaults = state.get('_deform_default') or {}
            amounts = (state.get('_deform') or {}).get('amounts') or {}
            if (not any(abs(float(v)) > 0 for v in defaults.values())
                    and not state.get('_deform_overrides') and any(abs(float(v)) > 0 for v in amounts.values())):
                raise ValueError(self.message('人物形变镜像仍会触发旧默认值迁移，尚不能冻结可靠上半身长短重放；未显示候选或修改照片'))
        fields = ('_brow_shape', '_nose_shape', '_eye_shape', '_mouth_shape', '_lip_makeup',
                  '_eye_light_preset', '_blush_makeup_preset', '_lipstick_preset',
                  '_eyeliner_preset', '_eyelash_preset', '_brow_makeup_preset', '_iris_makeup_preset')
        changed = any(fingerprint(before.get(key)) != fingerprint(candidate.get(key)) for key in fields)
        left = wrinkles.check((before.get('_enhance') or {}).get('amounts', {}))
        right = wrinkles.check((candidate.get('_enhance') or {}).get('amounts', {}))
        if changed or left != right:
            raise ValueError(self.message('受管理人物参数与上半身长短的混合预设尚无候选人物图审核；请先单独应用人物参数，再逐图审核上半身长短，不会显示旧人物图冒充候选'))


    def _require_stable_live_people(self, engine, row, graph, asset):
        """Do not let scalar publication become the first people migration/binding.

        Read only; _people_bind itself is intentionally never called by preflight.
        Parked rows are not activated here. Unexpected external drift is detected,
        not overwritten under the guise of rolling back an unrelated scalar edit.
        """
        from .virtual_copy_people import current_row
        if current_row(engine) is not row or getattr(engine, '_vram', None) is None:
            return
        pc = getattr(engine, '_precompute', None)
        owner = engine.__dict__.get('_people_graph_owner')
        if pc is not None:
            if owner is None or engine.__dict__.get('_people_analysis_key') != (asset, id(pc), owner.fence):
                raise ValueError(self.message('当前人物分析尚未稳定绑定；请完成打开/分析后重新审核上半身长短，不会在应用阶段迁移人物数据'))
        elif owner is not None and not any(item.get('legacy_key') == '_migration_complete'
                and item.get('asset_sha256') == asset for item in graph.get('unresolved_legacy', [])):
            raise ValueError(self.message('当前人物历史尚未完成来源迁移；请先完成打开流程，再审核上半身长短'))


    def _target_proof(self, record, asset):
        from . import body_pose_evidence as E, people_state as P
        FACE_BINDING_KEYS = self.state.FACE_BINDING_KEYS
        ref = E.ref(record['body_ref'])
        binding = record['associated_face']
        if type(binding) is not dict or set(binding) != set(FACE_BINDING_KEYS):
            raise ValueError(self.message('Torso-length review needs the exact current associated-face binding'))
        face = P.check_ref(binding['associated_face_ref'])
        box = binding['associated_face_box']
        import math
        if (type(box) is not list or len(box) != 4
                or any(type(n) not in (int, float) or not 0 < n < 1 or not math.isfinite(n) for n in box)
                or not box[0] < box[2] or not box[1] < box[3]):
            raise ValueError(self.message('Torso-length associated face box must be exact normalized source geometry'))
        self.api._hash(binding['associated_face_evidence_sha256'])
        if ref['asset_sha256'] != asset or face['asset_sha256'] != asset:
            raise ValueError(self.message('Torso-length target body and associated face must own this effective source'))


    def _target_identity(self, state, graph, proof, size):
        """Validate real target support against the actual full-render people graph."""
        from . import body_pose_evidence as E
        T = self.scope
        runtime = self.runtime()
        validate_face_review, face_binding = runtime.validate_face_review, runtime.face_binding
        bank, row, item, support = T.target(state)
        expected = E.source({'sha256': proof['asset_sha256'], 'width': size[0],
                             'height': size[1], 'orientation': E.ORIENTATION})
        if row['record']['source'] != expected:
            raise ValueError(self.message('Torso-length body review differs from actual full target source dimensions or identity'))
        if proof['creative_source'] is not None:
            from .creative_derived_body import validate
            validate(bank, proof['creative_source'])
        face = validate_face_review(support['data'], row, graph)
        return {'body_ref': deepcopy(row['record']['body_ref']),
                'associated_face': face_binding(face),
                'body_support_sha256': item['support_sha256'],
                'body_review_sha256': E.content_digest(item['review']),
                'bank_sha256': E.content_digest(bank)}


    def history_identity(self, engine, row, state, document, revision):
        """Read-only history fence, including current factual associated-face consent."""
        from .full_candidate_render import identity
        self.api._context(document, revision)
        proof, graph, _ = identity(engine, row, state, document, revision)
        if set(proof) != self.api.IDENTITY_FIELDS:
            raise ValueError(self.message('Incomplete full-target torso-length history identity'))
        self.api._require_stable_live_people(engine, row, graph, proof['source_proof']['asset_sha256'])
        self.api._require_retained_people_candidate(state, state, graph, proof['source_proof']['asset_sha256'])
        size, _ = self.api._geometry(row, state, proof['source_proof'])
        self.api._target_identity(state, graph, proof['source_proof'], size)
        return proof


    def _identities(self, engine, row, before, candidate, document, revision):
        from .full_candidate_render import identity
        self.api._context(document, revision)
        left, graph, _ = identity(engine, row, before, document, revision)
        self.api._require_stable_live_people(engine, row, graph, left['source_proof']['asset_sha256'])
        self.api._require_retained_people_candidate(before, candidate, graph, left['source_proof']['asset_sha256'])
        right, candidate_graph, _ = identity(engine, row, candidate, document, revision)
        if set(left) != self.api.IDENTITY_FIELDS or set(right) != self.api.IDENTITY_FIELDS:
            raise ValueError(self.message('Incomplete full-target torso-length identities'))
        if any(left[k] != right[k] for k in ('document_id', 'revision', 'source_proof')):
            raise ValueError(self.message('Torso-length views must share one immutable target source'))
        source, _ = self.api._geometry(row, before, left['source_proof'])
        other, _ = self.api._geometry(row, candidate, right['source_proof'])
        a = self.api._target_identity(before, graph, left['source_proof'], source)
        b = self.api._target_identity(candidate, candidate_graph, right['source_proof'], other)
        if source != other or any(a[k] != b[k] for k in a if k != 'bank_sha256'):
            raise ValueError(self.message('Torso-length transfer cannot replace target body, face association or reviewed support'))
        # Only the selected scalar may change inside the body bank. Full unrelated
        # image edits may be present, but cannot smuggle another body edit through.
        T = self.scope
        from .optics_candidate_identity import fingerprint
        expected = deepcopy(before)
        T.install(expected, T.params_of(candidate))
        if fingerprint(expected.get('_body_pose_bank')) != fingerprint(candidate.get('_body_pose_bank')):
            raise ValueError(self.message('Torso-length transfer changed another body operation or target-owned dependency'))
        target = {k: deepcopy(v) for k, v in b.items() if k != 'bank_sha256'}
        target.update(before_bank_sha256=a['bank_sha256'], candidate_bank_sha256=b['bank_sha256'])
        return left, right, target


    def _geometry(self, row, state, proof):
        from .ops.geometry import out_size
        source = proof['creative_source']
        size = [source['width'], source['height']] if source is not None else [row.get('src_w'), row.get('src_h')]
        self.api._size(size)
        output = list(out_size(*size, state['_crop_rect'], state['_crop_rotation']))
        self.api._size(output)
        return size, output


    def verify(self, engine, row, before, candidate, document, revision, record):
        params_of = self.scope.params_of
        record = self.api.checked(record)
        left, right, target = self.api._identities(engine, row, before, candidate, document, revision)
        actual = {'document_id': document, 'revision': revision, 'source_proof': left['source_proof'],
                  'before_sha256': left['candidate_sha256'], 'candidate_sha256': right['candidate_sha256'],
                  'before_people_sha256': left['people_sha256'], 'candidate_people_sha256': right['people_sha256'],
                  'parameters': params_of(candidate), **target}
        if any(record[k] != value for k, value in actual.items()):
            raise ValueError(self.message('Torso-length target source, edits, people or parameters changed after review'))
        source, prior_size = self.api._geometry(row, before, left['source_proof'])
        other, after_size = self.api._geometry(row, candidate, right['source_proof'])
        if source != other or record['source_size'] != source or record['before_output_size'] != prior_size or record['after_output_size'] != after_size:
            raise ValueError(self.message('Torso-length target geometry changed after review'))
        return record


    def _view(self, engine, row, state, document, revision, expected):
        from .full_candidate_render import render
        from PIL import Image
        import numpy as np
        rgb, proof = render(engine, row, state, document, revision)
        source, output = self.api._geometry(row, state, expected['source_proof'])
        if (type(proof) is not dict or set(proof) != self.api.IDENTITY_FIELDS | {'source_size', 'output_size'}
                or any(proof.get(k) != v for k, v in expected.items())
                or proof['source_size'] != source or proof['output_size'] != output
                or not isinstance(rgb, np.ndarray) or rgb.shape != (output[1], output[0], 3)
                or not np.issubdtype(rgb.dtype, np.floating) or not np.isfinite(rgb).all()):
            raise ValueError(self.message('Torso-length view requires the actual complete finite target render'))
        scale = min(1., self.api.PREVIEW_EDGE / max(output))
        size = tuple(max(1, round(n*scale)) for n in output)
        channels = []
        for channel in range(3):
            with Image.fromarray(rgb[:, :, channel].astype(np.float32)) as plane:
                with plane.resize(size, Image.Resampling.LANCZOS) as small:
                    channels.append(np.asarray(small).copy())
        # This clipping/quantization is presentation only, after full-source edits.
        display = Image.fromarray(np.rint(np.clip(np.stack(channels, axis=2), 0, 1)*255).astype(np.uint8), 'RGB')
        try:
            while True:
                stream = io.BytesIO(); display.save(stream, format='PNG'); raw = stream.getvalue()
                if len(raw) <= self.api.MAX_PNG_BYTES: break
                edge = max(display.size) - 16
                if edge < 1: raise ValueError(self.message('Torso-length display exceeds transport budget; no target omitted'))
                scale = min(1., edge/max(output))
                smaller = display.resize(tuple(max(1, round(n*scale)) for n in output), Image.Resampling.LANCZOS)
                display.close(); display = smaller
            size = display.size
        finally:
            display.close()
        compact = {'mime': 'image/png', 'width': size[0], 'height': size[1], 'sha256': sha256(raw).hexdigest()}
        return compact, {**compact, 'base64': base64.b64encode(raw).decode('ascii')}, source, output


    def prepare(self, engine, row, before, candidate, document, revision):
        params_of = self.scope.params_of
        left, right, target = self.api._identities(engine, row, before, candidate, document, revision)
        a, public_a, source, size_a = self.api._view(engine, row, before, document, revision, left)
        b, public_b, other, size_b = self.api._view(engine, row, candidate, document, revision, right)
        if source != other: raise ValueError(self.message('Torso-length target source changed between views'))
        record = self.api.checked({'version': 1, 'document_id': document, 'revision': revision,
            'source_proof': left['source_proof'], 'before_sha256': left['candidate_sha256'],
            'candidate_sha256': right['candidate_sha256'], 'before_people_sha256': left['people_sha256'],
            'candidate_people_sha256': right['people_sha256'], 'source_size': source,
            'before_output_size': size_a, 'after_output_size': size_b, 'parameters': params_of(candidate),
            'before': a, 'after': b, **target})
        self.api.verify(engine, row, before, candidate, document, revision, record)
        return record, {**deepcopy(record), 'before': public_a, 'after': public_b}


@dataclass(frozen=True)
class Family:
    """Exact established ledger/protocol keys, not a portable family payload."""
    name: str
    operation_id: str
    scope: ModuleType
    review: ModuleType
    wire_key: str
    ack_key: str
    private_key: str
    frozen_key: str
    prepared_key: str
    port_name: str
    preset_key: str


def select(modules):
    """Select one exclusive scalar route from a checked operation collection.

    Accept mapping keys and existing sequence/set callers, never a bare string.
    Ordinary scopes return None. No body scalar family may compose with another
    operation until a real combined target review protocol exists.
    """
    if type(modules) not in (dict, list, tuple, set, frozenset):
        raise ValueError('Body scalar review needs an explicit operation collection')
    ops = tuple(modules)
    if any(type(op) is not str for op in ops) or len(set(ops)) != len(ops):
        raise ValueError('Body scalar review operation IDs must be unique strings')
    # Fixed identities are deliberately visible here; no external data controls
    # an import, attribute lookup, family fallback or state-policy replacement.
    selected = set(ops).intersection(('lnx.torso_length.v1', 'lnx.waist_length.v1', 'lnx.head_size.v1'))
    if not selected:
        return None
    if len(ops) != 1:
        raise ValueError('Body scalar transfers require one exclusive reviewed operation')
    if ops[0] == 'lnx.torso_length.v1':
        from . import torso_length_scope as scope, torso_length_transfer_review as review
        return Family('torso_length', scope.OP, scope, review, 'torso_transfer',
                      'torso_review_ack', 'torso_review', 'torso_json',
                      '_torso_prepared', 'torso', 'torso')
    if ops[0] == 'lnx.waist_length.v1':
        from . import waist_length_scope as scope, waist_length_transfer_review as review
        return Family('waist_length', scope.OP, scope, review, 'waist_transfer',
                      'waist_review_ack', 'waist_review', 'waist_json',
                      '_waist_prepared', 'waist', 'waist_review')
    from . import head_size_scope as scope, head_size_transfer_review as review
    return Family('head_size', scope.OP, scope, review, 'head_transfer',
                  'head_review_ack', 'head_review', 'head_json',
                  '_head_prepared', 'head', 'head_review')
