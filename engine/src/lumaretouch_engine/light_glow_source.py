# SPDX-License-Identifier: GPL-3.0-or-later
"""Owned current full-edited capture for glow. AUTHORED / UNRUN.

Uses the existing complete photo export capture, immutable canonical assets,
source fencing and display-only PNG producer. No proxy becomes output pixels.
"""
from dataclasses import dataclass
import json
import uuid

from . import lens_blur_stage as shared
from .lens_blur_host import _Fence

OPERATION = 'lnx.light_glow.v1'


@dataclass(frozen=True, slots=True)
class Fence:
    base: object
    repair_stack_sha256: str

    def stale(self, engine):
        return self.base.stale(engine)

    def verify(self, engine, cancelled=lambda: False, *, cold=True):
        self.base.verify(engine, cancelled, cold=cold)
        if cold:
            from .creative_derived_repairs import stack_digest
            if stack_digest(engine) != self.repair_stack_sha256:
                raise ValueError('Glow ordered repair evidence changed after full-source capture')
        if cancelled() or self.stale(engine):
            raise InterruptedError('Glow source ownership expired')


@dataclass(frozen=True, slots=True)
class Source:
    pixels: shared.CapturedSource
    evidence_json: bytes

    @property
    def owner(self):
        return self.pixels.owner

    @property
    def evidence(self):
        return json.loads(self.evidence_json)

    @property
    def retained_bytes(self):
        return self.pixels.retained_bytes + len(self.evidence_json)


def capture_current(engine, *, budget, cancelled=lambda: False):
    """Retain current recipe, geometry and repair output, not original RGB.

    Full-source capture owns replay admission, including original and derived
    repair stacks. The stack hash proves intent/order, not a new AI measurement.
    The existing cold fence proves the file, canonical document and people owner.
    """
    from .creative_document_assets import AssetStore
    from .creative_document_base import capture_current_asset
    from .creative_document_host import require_photo_return
    from .creative_derived_repairs import stack_digest
    base = _Fence.capture(engine, cancelled)
    fence = Fence(base, stack_digest(engine))
    stopped = lambda: cancelled() or fence.stale(engine)
    state = engine._capture_state()
    if stack_digest(state) != fence.repair_stack_sha256:
        raise ValueError('Glow capture state does not own the current ordered repair stack')
    assets = AssetStore(max_bytes=min(2_000_000_000, budget.max_bytes))
    asset = capture_current_asset(engine, base.row, state, assets,
        max_bytes=budget.max_bytes, cancelled=stopped,
        neutral_import_version=1, allow_legacy_import_budget_fallback=False,
        edited_capture_version=3)
    del assets, state
    require_photo_return(asset)  # No alpha flattening, HDR clipping or tone-map.
    owner = {'document_id': base.version.document_id, 'document_epoch': base.epoch,
             'document_revision': str(base.version.revision),
             'source': {'sha256': asset['id'][7:], 'width': asset['width'],
                        'height': asset['height'], 'orientation': shared.ORIENTATION}}
    pixels = shared.capture_source(asset, owner, budget=budget, cancelled=stopped)
    evidence = {'kind': 'current_full_edited_source', 'capture_version': 3,
                'original_sha256': base.file_sha256,
                'people_graph_sha256': base.graph_sha256,
                'repair_stack_sha256': fence.repair_stack_sha256,
                'document_revision': owner['document_revision'],
                'load_id': str(base.load_id), 'capture_token': uuid.uuid4().hex}
    fence.verify(engine, cancelled)
    return Source(pixels, shared._json(evidence)), fence


def require(source):
    if type(source) is not Source:
        raise ValueError('Glow requires its retained full edited-source lease')
    shared._require_source(source.pixels)
    evidence = source.evidence
    keys = {'kind', 'capture_version', 'original_sha256', 'people_graph_sha256',
            'repair_stack_sha256', 'document_revision', 'load_id', 'capture_token'}
    if (set(evidence) != keys or evidence['kind'] != 'current_full_edited_source'
            or evidence['capture_version'] != 3
            or evidence['document_revision'] != source.owner['document_revision']
            or not all(shared._sha(evidence[k]) for k in
                       ('original_sha256', 'people_graph_sha256', 'repair_stack_sha256'))
            or not shared._token(evidence['capture_token']) or type(evidence['load_id']) is not str):
        raise ValueError('Glow retained capture evidence is malformed')
    return source
