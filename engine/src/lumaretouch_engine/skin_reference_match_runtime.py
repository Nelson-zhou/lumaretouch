# SPDX-License-Identifier: GPL-3.0-or-later
"""Selected same-photo FACE reference preparation. AUTHORED / UNRUN.

Fit genuine immutable full-source pixels once per target. Project only measured
semantic observations, rebuild anatomical permission on each grid, and retain
no source RGB/delta, geometry, history bank or portable fit. Capture, document
revision fencing and one final publication remain the canonical host's duties.
"""
from dataclasses import dataclass
import hashlib

import numpy as np

from . import people_state as P, people_resolver as R
from . import skin_reference_match_state as S, skin_reference_match_support as A
from . import skin_reference_match_native as N
from .cpu_memory_budget import available_estimate
from .people_effects import LocalEffect
from .portrait_fit_source import FullSource

STAGE = 'skin_reference_match'
FIXED_BYTES = 128 * 1024**2
RECORD_BYTES = 64 * 1024
BLOCK_PIXELS = 4096


class SkinReferenceMatchRefused(ValueError):
    def __init__(self, reason, *, face_ref=None):
        self.reason, self.face_ref = reason, face_ref
        super().__init__('同图指定人脸肤色及亮度匹配未应用：' + reason)


def _poll(cancelled):
    if not callable(cancelled):
        raise TypeError('cancelled must be callable')
    if cancelled():
        raise InterruptedError('Skin-reference preparation cancelled; private bank discarded')


def _identity(ref):
    ref = P.check_ref(ref)
    return (ref['asset_sha256'], ref['face_instance_id'], ref['analysis_revision'])


def _window(value, shape):
    if (type(value) is not tuple or len(value) != 4
            or any(type(v) is not int for v in value)):
        raise ValueError('Skin-reference coverage needs an exact source-grid window')
    y, x, h, w = value
    if min(y, x) < 0 or min(h, w) < 1 or y+h > shape[0] or x+w > shape[1]:
        raise ValueError('Skin-reference window is outside its declared grid')
    return value


def _shape(value):
    if (type(value) is not tuple or len(value) != 2
            or any(type(v) is not int or not 2 <= v <= N.MAX_DIMENSION for v in value)
            or value[0] * value[1] > N.MAX_FRAME_PIXELS):
        raise ValueError('Skin-reference grid must be an exact bounded (height,width) tuple')
    return value


@dataclass(frozen=True)
class Parameters:
    """In-process fit plus immutable ownership, never a serializable approval."""
    amount: float
    measured_fit: N.MeasuredFit
    source_sha256: str
    source_pixels_sha256: str
    source_shape: tuple
    application_shape: tuple
    target_identity: tuple
    reference_identity: tuple
    support_sha256: str
    target_source_window: tuple
    reference_source_window: tuple
    application_window: tuple
    coverage_sha256: str

    @property
    def recipe(self):
        return S.check({'version': S.VERSION, 'amount': self.amount})

    def resident_bytes(self):
        """Conservative complete non-array record/facts allowance; count weights separately."""
        return RECORD_BYTES

    def checked(self):
        self.recipe
        for digest in (self.source_sha256, self.source_pixels_sha256,
                       self.support_sha256, self.coverage_sha256):
            P.digest(digest)
        _shape(self.source_shape); _shape(self.application_shape)
        A._whole_shape({'sha256': self.source_sha256, 'width': self.source_shape[1],
                        'height': self.source_shape[0]}, self.application_shape)
        for identity in (self.target_identity, self.reference_identity):
            if type(identity) is not tuple or len(identity) != 3:
                raise ValueError('Skin-reference parameters require immutable exact face identities')
            _identity(dict(zip(('asset_sha256', 'face_instance_id', 'analysis_revision'), identity)))
            if identity[0] != self.source_sha256:
                raise ValueError('Skin-reference fit cannot cross source owners')
        if self.target_identity[1] == self.reference_identity[1]:
            raise ValueError('Skin-reference selected reference cannot also be a target')
        _window(self.target_source_window, self.source_shape)
        _window(self.reference_source_window, self.source_shape)
        _window(self.application_window, self.application_shape)
        if type(self.measured_fit) is not N.MeasuredFit:
            raise ValueError('Skin-reference parameters require the original measured native fit')
        self.measured_fit.checked()
        if (self.measured_fit.target_shape != self.target_source_window[2:]
                or self.measured_fit.reference_shape != self.reference_source_window[2:]):
            raise ValueError('Skin-reference fit is not bound to its independent source ROIs')
        return self


def requests(state, asset_sha256):
    """Resolve the COMPLETE enabled target set, including every inheritance scope."""
    state = P.check(state); P.digest(asset_sha256)
    selected = []
    for face_id, face in sorted(state['faces'].items()):
        if face['asset_sha256'] != asset_sha256 or not face['enabled']:
            continue
        resolved = R.resolve(state, face_id, {S.OP: {'/amount': 0.0}})
        recipe = R.materialize(resolved, S.OP, S.neutral(), S.check)
        if S.active(recipe):
            selected.append((P.face_ref(face), recipe))
    return tuple(selected)


def array_bytes(value):
    """Charge backing ndarray storage, not merely a possibly tiny strided view."""
    if type(value) is not np.ndarray:
        return 0
    base = value
    while isinstance(base.base, np.ndarray):
        base = base.base
    owner = base.base
    backing = owner.nbytes if isinstance(owner, memoryview) else len(owner) if isinstance(owner, (bytes, bytearray)) else 0
    return max(int(value.nbytes), int(base.nbytes), int(backing))


def _analysis_bytes(analyses):
    if type(analyses) is not dict or len(analyses) > P.MAX_FACES:
        raise ValueError('Skin-reference analysis bank must use bounded stable face-instance keys')
    total = 0
    for key, row in analyses.items():
        P.token(key)
        if type(row) is not dict or len(row) > 32:
            raise ValueError('Skin-reference analysis row is not bounded')
        # Repeated references are deliberately charged repeatedly. Include all
        # supplied semantic arrays, even ones this operation does not consume.
        total += sum(array_bytes(value) for value in row.values())
    return total


def _admit(required, byte_budget):
    if type(byte_budget) is not int or byte_budget < 0:
        raise ValueError('Skin-reference runtime needs an explicit total working byte budget')
    if required > byte_budget or required > available_estimate():
        raise MemoryError('Skin-reference full-source and application work exceeds memory admission; no proxy fit')


def _source_binding(full_source, asset_sha256):
    if type(full_source) is not FullSource:
        raise SkinReferenceMatchRefused('需要已认证的完整原始精度源图，不能使用显示代理或调用方验证标记')
    source = full_source.binding
    P.digest(full_source.input_sha256)
    shape = _shape((source['height'], source['width']))
    if (source['sha256'] != asset_sha256 or type(full_source._content) is not bytes
            or full_source.owned_bytes != shape[0] * shape[1] * 12
            or (full_source.kind, full_source.source_bits) not in
            (('original', 8), ('original', 16), ('creative', 32))):
        raise ValueError('Skin-reference captured source binding/precision is inconsistent')
    return source, shape


def _validate_source(full_source, cancelled):
    pixels = full_source.pixels
    if pixels.dtype != np.float32 or pixels.flags.writeable or not pixels.flags.c_contiguous:
        raise ValueError('Skin-reference source must be immutable native float32 working-sRGB')
    digest = hashlib.sha256(); view = memoryview(full_source._content)
    for start in range(0, len(view), 1024 * 1024):
        _poll(cancelled); digest.update(view[start:start + 1024 * 1024])
    if digest.hexdigest() != full_source.input_sha256:
        raise ValueError('Skin-reference captured pixels differ from their authenticated input digest')
    for row in pixels:
        for left in range(0, row.shape[0], BLOCK_PIXELS):
            _poll(cancelled); block = row[left:left + BLOCK_PIXELS]
            if not np.isfinite(block).all() or np.any(block < 0) or np.any(block > 1):
                raise ValueError('Skin-reference source is not finite encoded SDR; clipping is forbidden')
    return pixels


def _project(raw, shape, cancelled):
    """Same interpolation as people_snapshot, without unrelated semantic banks."""
    result = dict(raw)
    for key in ('face_skin', 'excluded'):
        _poll(cancelled); value = raw[key]
        if value.shape != shape:
            import cv2
            value = cv2.resize(value, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
        value = np.array(value, dtype=np.float32, order='C', copy=True)
        value.setflags(write=False); result[key] = value
    # Producer observation and normalized landmarks are preserved, not promoted
    # to a claim that fresh full-resolution inference took place.
    return result


def _claim(occupied, coverage, window, cancelled):
    y, x, h, w = window
    for row in range(y, y+h):
        for left in range(x, x+w, BLOCK_PIXELS):
            _poll(cancelled); right = min(left + BLOCK_PIXELS, x+w)
            visible = coverage[row, left:right] > 0
            used = occupied[row, left:right]
            if np.any(visible & used):
                raise SkinReferenceMatchRefused('已审核的不同目标人脸范围重叠，不会按顺序覆盖或猜测归属')
            used |= visible


def coverage_digest(weights):
    """Hash an already admitted contiguous plane without an extra plane copy."""
    digest = hashlib.sha256(); view = memoryview(weights).cast('B')
    for start in range(0, len(view), 1024 * 1024):
        digest.update(view[start:start + 1024 * 1024])
    return digest.hexdigest()


def _roi(value, window):
    y, x, h, w = window
    return value[y:y+h, x:x+w]


def prepare_bank(state, asset_sha256, full_source, analyses, *, assets,
                 application_shape, byte_budget, cancelled=lambda: False):
    """Return (LocalEffect tuple, per-target facts), or publish nothing on failure.

    full_source MUST come from portrait_fit_source.capture/capture_original for
    this fenced source, before repairs/portrait edits. Its class and dimensions
    are structural checks, not a substitute for that authentication. byte_budget
    is the total allowance for supplied source/analyses and this operation;
    callers must subtract every unrelated renderer allocation first.
    """
    _poll(cancelled)
    state = P.check(state); selected = requests(state, asset_sha256)
    if not selected:
        return (), {}  # No source, analysis, support, native capability or raster needed.
    source, source_shape = _source_binding(full_source, asset_sha256)
    application_shape = _shape(application_shape)
    A._whole_shape(source, application_shape)
    analysis_bytes = _analysis_bytes(analyses)
    f = source_shape[0] * source_shape[1]
    a = application_shape[0] * application_shape[1]
    # Charge already resident inputs, both ownership canvases, worst retained
    # immutable weights AND their freeze copies, graph/validation allowance.
    resident = (full_source.owned_bytes + 2*analysis_bytes + FIXED_BYTES + f + a
                + (8*a + RECORD_BYTES)*len(selected))
    grid_work = 64*f + 64*a
    _admit(resident + grid_work, byte_budget)
    reference_ref = A.validate_active(state, assets, [ref for ref, _ in selected], analyses)
    relevant = [analyses[ref['face_instance_id']] for ref, _ in selected]
    relevant.append(analyses[reference_ref['face_instance_id']])
    largest_roi = 0
    for raw in relevant:
        for grid in (source_shape, application_shape):
            _, (x0, y0, x1, y1) = A._extent(raw['landmarks'], grid)
            largest_roi = max(largest_roi, (x1-x0)*(y1-y0))
    # Geometry's largest ROI scratch and both independent native ROI snapshots
    # are charged together, conservatively, although not live simultaneously.
    required = (resident + grid_work + 288*largest_roi + A._FIXED_BYTES
                + N.SCRATCH_BYTES + N.FIT_FIXED_SCRATCH_BYTES)
    _admit(required, byte_budget)
    pixels = _validate_source(full_source, cancelled)
    fit_owners = np.zeros(source_shape, dtype=bool)
    app_owners = np.zeros(application_shape, dtype=bool)
    effects, facts = [], {}
    for ref, recipe in selected:
        _poll(cancelled)
        target_raw = analyses[ref['face_instance_id']]
        reference_raw = analyses[reference_ref['face_instance_id']]
        pair = (_project(target_raw, source_shape, cancelled), _project(reference_raw, source_shape, cancelled))
        target, reference, full_facts = A.geometry(state, assets, ref, *pair, source_shape,
            byte_budget=byte_budget-resident-16*f, cancelled=cancelled)
        if full_facts['source'] != source:
            raise ValueError('Skin-reference review and authenticated canonical source dimensions disagree')
        tw = tuple(full_facts['target']['source_window'])
        rw = tuple(full_facts['reference']['source_window'])
        _window(tw, source_shape); _window(rw, source_shape)
        _claim(fit_owners, target, tw, cancelled)
        # Own independent full support windows, never common-size crops, paired
        # source pixels, resampled source RGB or tile-local repeated fitting.
        measured = N.fit(_roi(pixels, rw), _roi(reference, rw),
                        _roi(pixels, tw), _roi(target, tw),
                        byte_budget=byte_budget-resident-24*f, cancelled=cancelled)
        del target, reference, pair
        pair = (_project(target_raw, application_shape, cancelled),
                _project(reference_raw, application_shape, cancelled))
        target, reference, app_facts = A.geometry(state, assets, ref, *pair, application_shape,
            byte_budget=byte_budget-resident-16*a, cancelled=cancelled)
        if app_facts['support_sha256'] != full_facts['support_sha256'] or app_facts['source'] != source:
            raise ValueError('Skin-reference relation changed between fit and application support')
        window = tuple(app_facts['target']['source_window']); _window(window, application_shape)
        _claim(app_owners, target, window, cancelled)
        # Immutable bytes storage cannot be made writeable again with setflags.
        content = np.ascontiguousarray(_roi(target, window)).tobytes()
        weights = np.frombuffer(content, dtype=np.float32).reshape(window[2:])
        parameters = Parameters(recipe['amount'], measured, asset_sha256, full_source.input_sha256,
            source_shape, application_shape, _identity(ref), _identity(reference_ref),
            full_facts['support_sha256'], tw, rw, window, coverage_digest(weights)).checked()
        fact = {**app_facts, 'requested': True, 'applied': None, 'stage': STAGE,
            'recipe': recipe, 'face_ref': dict(ref), 'reference_face_ref': dict(reference_ref),
            'fit_source_dimensions': [source_shape[1], source_shape[0]],
            'application_dimensions': [application_shape[1], application_shape[0]],
            'fit_target_window': list(tw), 'fit_reference_window': list(rw),
            'fit_source_pixels_sha256': full_source.input_sha256,
            'fit_effective_reference_samples': measured.diagnostics[5],
            'fit_effective_target_samples': measured.diagnostics[6],
            'fit_count_per_target': 1, 'composition': 'original-rust-current-pixel-colour-and-brightness',
            'fit_portable': False, 'source_rgb_retained': False, 'memory_admission_bytes': required}
        effects.append(LocalEffect(ref, STAGE, window, weights=weights, amounts=parameters, facts=fact))
        facts[ref['face_instance_id']] = fact
        del target, reference, pair, content, weights
    _poll(cancelled)
    return tuple(effects), facts
