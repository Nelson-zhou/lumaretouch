# SPDX-License-Identifier: GPL-3.0-or-later
"""Small current-photo review adapter; the existing document owner publishes.

Private reference/preview metadata is disposable, not history or a receipt bank.
Ports must capture canonical repaired-source pixels and render the COMPLETE
candidate through the normal pipeline. No default or preview-only renderer exists.
Source authored; build/runtime/photo acceptance UNRUN.
"""
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable
import uuid
import json
import numpy as np
from . import hand_tone_state as S
from .hand_tone_support import check_review
from .optics_candidate_identity import fingerprint


@dataclass(frozen=True)
class Capture:
    source: dict
    input_sha256: str
    repair_sha256: str
    fence: str
    encoded_rgb: np.ndarray
    recipe: object


@dataclass(frozen=True)
class Rendered:
    encoded_rgb: np.ndarray
    source: dict
    input_sha256: str
    repair_sha256: str
    candidate_sha256: str


@dataclass(frozen=True)
class Ports:
    # Internal functions only; never constructed from JSON supplied by the UI.
    capture: Callable[[], Capture]
    render: Callable[[object], Rendered]
    budget: Callable[[], int]


@dataclass(frozen=True)
class ConfirmedEdit:
    """Publication intent for the existing atomic document/receipt owner."""
    fence: str
    recipe: object
    candidate_sha256: str
    payload: dict


def _poll(cancelled):
    if cancelled and cancelled():
        raise InterruptedError('Hand tone review cancelled')


def _tag():
    return {'protocol': 1, 'family': S.FAMILY}


def _image(rgb):
    from .hand_tone_review import display_image
    return display_image(rgb)


def _capture(ports):
    value = ports.capture()
    if not isinstance(value, Capture):
        raise ValueError('Hand tone capture port returned no canonical source')
    source = S.source(value.source)
    for key in ('input_sha256', 'repair_sha256', 'fence'):
        S.digest(getattr(value, key))
    pixels = value.encoded_rgb
    if (type(pixels) is not np.ndarray or pixels.dtype != np.float32 or pixels.flags.writeable
            or pixels.shape != (source['height'], source['width'], 3)):
        raise ValueError('Hand tone needs immutable full-resolution working-sRGB source pixels')
    # No image-wide boolean temporary; source provenance remains the port's duty.
    for first in range(0, source['height'], 32):
        stripe = pixels[first:first + 32]
        if not np.isfinite(stripe).all() or np.any((stripe < 0) | (stripe > 1)):
            raise ValueError('Hand tone rejects HDR/nonfinite source instead of clipping')
    S.check(value.recipe)
    return value


def _identity(value):
    return {'source': S.source(value.source), 'input_sha256': value.input_sha256,
            'repair_sha256': value.repair_sha256, 'fence': value.fence}


def _candidate(capture, payload):
    return S.check({'version': 1, 'source': capture.source,
        'input_sha256': capture.input_sha256, 'repair_sha256': capture.repair_sha256,
        'amount': payload['amount'], 'radius_px': payload['radius_px'], 'review': payload['review']})


def _render(ports, capture, candidate):
    value = ports.render(deepcopy(candidate))
    if (not isinstance(value, Rendered) or value.source != capture.source
            or value.input_sha256 != capture.input_sha256 or value.repair_sha256 != capture.repair_sha256
            or value.candidate_sha256 != fingerprint(candidate)):
        raise ValueError('Hand tone renderer returned a different full candidate/source identity')
    # Full renderer may crop/rotate output; actual output dimensions are transported.
    return _image(value.encoded_rgb), fingerprint(value.encoded_rgb)


class Review:
    def __init__(self, ports: Ports):
        self.ports = ports
        self._reference = None
        self._preview = None

    def invalidate(self):
        self._reference = self._preview = None

    def _same(self, capture):
        if _identity(_capture(self.ports)) != _identity(capture):
            self.invalidate()
            raise ValueError('Document, source or edits changed; reload hand tone reference')

    def reference(self, payload, *, cancelled=None):
        if payload != {}:
            raise ValueError('Hand tone reference accepts no source override')
        _poll(cancelled)
        capture = _capture(self.ports)
        from .hand_tone_native import capability
        image = _image(capture.encoded_rgb)
        self._same(capture)
        token = uuid.uuid4().hex
        self._reference = {'id': token, 'identity': _identity(capture)}
        self._preview = None
        return {**_tag(), 'reference_id': token, 'fence': capture.fence,
                'source': deepcopy(capture.source), 'source_image': image,
                'current_amount': 0.0 if capture.recipe is None else S.check(capture.recipe)['amount'],
                'capability': capability()}

    def preview(self, payload, *, cancelled=None):
        if type(payload) is not dict or set(payload) != {'reference_id', 'amount', 'radius_px', 'review'}:
            raise ValueError('Hand tone preview requires exact reference, amount, radius and masks')
        S.amount(payload['amount']); S.radius(payload['radius_px']); check_review(payload['review'])
        if payload['amount'] <= 0:
            raise ValueError('Choose a positive correction amount; use clear for removal')
        capture = _capture(self.ports)
        if (self._reference is None or self._reference['id'] != payload['reference_id']
                or self._reference['identity'] != _identity(capture)):
            raise ValueError('Hand tone reference expired; reload the current source')
        candidate = _candidate(capture, payload)
        _poll(cancelled)
        from .hand_tone_measure import prepare
        # The same preparation function must be used by normal render/export.
        prepared = prepare(capture.encoded_rgb, candidate, byte_budget=self.ports.budget(), cancelled=cancelled)
        from .hand_tone_review import mask_image
        mask = mask_image(capture.encoded_rgb, prepared)
        facts = deepcopy(prepared.facts)
        del prepared
        before, before_raster = _render(self.ports, capture, capture.recipe)
        _poll(cancelled)
        after, after_raster = _render(self.ports, capture, candidate)
        _poll(cancelled)
        self._same(capture)
        token = uuid.uuid4().hex
        self._preview = {'id': token, 'identity': _identity(capture), 'candidate': candidate,
            'candidate_sha256': fingerprint(candidate), 'before_sha256': before['sha256'],
            'after_sha256': after['sha256'], 'mask_sha256': mask['sha256'],
            'before_raster': before_raster, 'after_raster': after_raster}
        result = {**_tag(), 'preview_id': token, 'fence': capture.fence, 'before': before,
                'after': after, 'mask': mask, 'facts': facts, 'candidate_sha256': fingerprint(candidate)}
        if len(json.dumps(result, allow_nan=False, separators=(',', ':')).encode()) > 7 * 1024**2:
            self._preview = None
            raise ValueError('Hand tone comparison exceeds its bounded receipt budget')
        return result

    def confirm(self, payload, *, cancelled=None):
        keys = {'preview_id', 'reviewed', 'before_sha256', 'after_sha256', 'mask_sha256', 'candidate_sha256'}
        if type(payload) is not dict or set(payload) != keys or payload['reviewed'] is not True:
            raise ValueError('Explicitly confirm the exact hand tone comparison and mask')
        for key in keys - {'preview_id', 'reviewed'}:
            S.digest(payload[key])
        capture = _capture(self.ports); cached = self._preview
        if cached is None or cached['identity'] != _identity(capture) or cached['id'] != payload['preview_id']:
            raise ValueError('Hand tone preview expired; update the effect again')
        if any(payload[key] != cached[key] for key in keys - {'preview_id', 'reviewed'}):
            raise ValueError('Hand tone confirmation does not match the reviewed images')
        _poll(cancelled)
        # Immutable source and graph fences, not caller hashes, authorize publication.
        self._same(capture)
        candidate = deepcopy(cached['candidate'])
        return ConfirmedEdit(capture.fence, candidate, cached['candidate_sha256'],
            {**_tag(), 'amount': candidate['amount'], 'candidate_sha256': cached['candidate_sha256']})

    def clear(self, payload):
        if payload != {}:
            raise ValueError('Hand tone clear accepts no external recipe')
        capture = _capture(self.ports)
        self._same(capture)
        return ConfirmedEdit(capture.fence, None, fingerprint(None),
                             {**_tag(), 'amount': 0.0, 'candidate_sha256': fingerprint(None)})

    def assert_publishable(self, edit):
        """Call inside the existing owner lock immediately before committing."""
        if not isinstance(edit, ConfirmedEdit) or _capture(self.ports).fence != edit.fence:
            raise ValueError('Hand tone document changed before atomic publication')
        if fingerprint(S.check(edit.recipe)) != edit.candidate_sha256:
            raise ValueError('Hand tone publication intent changed')
        return deepcopy(edit.recipe)
