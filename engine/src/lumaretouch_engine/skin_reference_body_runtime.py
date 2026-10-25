# SPDX-License-Identifier: GPL-3.0-or-later
"""Reviewed BODY to explicitly selected same-photo FACE preparation. UNRUN.

This is a separate scalar/consent path using the existing skin-reference Rust
solver, not the old own-face chroma-only operator and not a new algorithm. It
fits immutable full-native-precision source pixels, then retains only measured
parameters and independently reviewed body coverage. The host owns source and
revision fencing, the complete face/body bank, and one final publication.
"""
from dataclasses import dataclass

import numpy as np

from . import people_state as P, people_resolver as R, body_pose_evidence as E
from . import skin_reference_body_state as S, skin_reference_body_support as A
from . import skin_reference_match_runtime as F, skin_reference_match_native as N
from .cpu_memory_budget import available_estimate
from .people_effects import LocalEffect

STAGE = 'skin_reference_body_match'
FIXED_BYTES = 160 * 1024**2
RECORD_BYTES = F.RECORD_BYTES
BLOCK_PIXELS = F.BLOCK_PIXELS
array_bytes = F.array_bytes
coverage_digest = F.coverage_digest
_poll, _shape, _window, _identity = F._poll, F._shape, F._window, F._identity


class SkinReferenceBodyRefused(ValueError):
    def __init__(self, reason, *, face_ref=None, body_ref=None):
        self.reason, self.face_ref, self.body_ref = reason, face_ref, body_ref
        super().__init__('身体匹配同图指定人脸肤色及亮度未应用：' + reason)


def _body_identity(ref):
    ref = E.ref(ref)
    return (ref['asset_sha256'], ref['body_instance_id'], ref['analysis_revision'])


@dataclass(frozen=True)
class Parameters:
    """In-process source fit with distinct body owner/reference identities."""
    amount: float
    measured_fit: N.MeasuredFit
    source_sha256: str
    source_pixels_sha256: str
    source_shape: tuple
    application_shape: tuple
    owner_identity: tuple
    body_identity: tuple
    reference_identity: tuple
    support_sha256: str
    target_source_window: tuple
    reference_source_window: tuple
    application_window: tuple
    coverage_sha256: str

    @property
    def recipe(self):
        return S.check({'version': S.VERSION, 'amount': self.amount})

    @property
    def body_ref(self):
        return dict(zip(('asset_sha256', 'body_instance_id', 'analysis_revision'), self.body_identity))

    def resident_bytes(self):
        return RECORD_BYTES

    def checked(self):
        self.recipe
        for digest in (self.source_sha256, self.source_pixels_sha256,
                       self.support_sha256, self.coverage_sha256):
            P.digest(digest)
        _shape(self.source_shape); _shape(self.application_shape)
        E.whole_source_shape({'sha256': self.source_sha256, 'width': self.source_shape[1],
            'height': self.source_shape[0], 'orientation': E.ORIENTATION}, self.application_shape)
        for identity in (self.owner_identity, self.reference_identity):
            if type(identity) is not tuple or len(identity) != 3:
                raise ValueError('Body-reference parameters need exact immutable face identities')
            _identity(dict(zip(('asset_sha256', 'face_instance_id', 'analysis_revision'), identity)))
            if identity[0] != self.source_sha256:
                raise ValueError('Body-reference fit cannot cross source owners')
        if type(self.body_identity) is not tuple or len(self.body_identity) != 3:
            raise ValueError('Body-reference parameters need a distinct immutable BodyRef')
        if _body_identity(self.body_ref)[0] != self.source_sha256:
            raise ValueError('Body-reference body belongs to another source')
        # The chosen face may be this body's owner. It is never painted here.
        _window(self.target_source_window, self.source_shape)
        _window(self.reference_source_window, self.source_shape)
        _window(self.application_window, self.application_shape)
        if type(self.measured_fit) is not N.MeasuredFit:
            raise ValueError('Body-reference parameters require the original measured native fit')
        self.measured_fit.checked()
        if (self.measured_fit.target_shape != self.target_source_window[2:]
                or self.measured_fit.reference_shape != self.reference_source_window[2:]):
            raise ValueError('Body-reference fit differs from its independent original-source ROIs')
        return self


def requests(state, asset_sha256):
    """Resolve ALL enabled new-operation amounts, never a selected row subset.

    A nonzero amount without its own body consent fails during preparation.
    Old face-v1 and old body-to-own-face amounts do not activate this path.
    """
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


def _admit(required, byte_budget):
    if type(byte_budget) is not int or byte_budget < 0:
        raise ValueError('Body-reference preparation requires an explicit total working byte budget')
    if required > byte_budget or required > available_estimate():
        raise MemoryError('Body-reference full-source preparation exceeds admission; no proxy fit')


def _project(raw, shape, cancelled, *, body=False):
    """Resample only actual semantic observations; never pixels used for fitting."""
    result = dict(raw)
    for key in (('body_skin', 'excluded') if body else ('face_skin', 'excluded')):
        _poll(cancelled); value = raw.get(key)
        if type(value) is not np.ndarray or value.dtype != np.float32 or value.ndim != 2:
            raise ValueError('Body-reference preparation needs actual named semantic support planes')
        if value.shape != shape:
            import cv2
            value = cv2.resize(value, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
        value = np.array(value, dtype=np.float32, order='C', copy=True)
        value.setflags(write=False); result[key] = value
    return result


def _record(record, shape, cancelled):
    """Validate one matching stage record before any joint composition."""
    params = record.amounts
    expected = Parameters if record.stage == STAGE else F.Parameters
    if type(params) is not expected:
        raise ValueError('Joint reference bank lacks measured source-owned parameters')
    params.checked(); ref = P.check_ref(record.face_ref)
    owner = params.owner_identity if record.stage == STAGE else params.target_identity
    if (_identity(ref) != owner or params.application_shape != shape
            or record.window != params.application_window):
        raise ValueError('Joint reference record belongs to another owner, window or application grid')
    if any(value is not None for value in (record.delta, record.chroma_shift, record.log_gain)):
        raise ValueError('Reference matching cannot replay RGB deltas or borrow another algorithm')
    _, _, h, w = _window(record.window, shape); weights = record.weights
    if (type(weights) is not np.ndarray or weights.dtype != np.float32
            or weights.shape != (h, w) or weights.flags.writeable or not weights.flags.c_contiguous):
        raise ValueError('Reference coverage must be the immutable contiguous reviewed plane')
    for row in weights:
        for left in range(0, w, BLOCK_PIXELS):
            _poll(cancelled); block = row[left:left+BLOCK_PIXELS]
            if not np.isfinite(block).all() or np.any(block < 0) or np.any(block > 1):
                raise ValueError('Reference coverage must be finite in [0,1]')
    if coverage_digest(weights) != params.coverage_sha256:
        raise ValueError('Reference coverage changed after full-source preparation')
    return params, ref


def validate_joint_records(records, *, application_shape, cancelled=lambda: False):
    """Preflight complete face/body bank with bounded row scratch, not blending.

    Call before either stage to guarantee no duplicate contribution. It rejects
    positive-weight overlap even for the same person, duplicate target bodies,
    mixed source captures/references, and painting the chosen reference face.
    Other portrait families are intentionally not claimed by this operation.
    """
    _poll(cancelled); shape = _shape(application_shape)
    selected = tuple(r for r in records if r.stage in (F.STAGE, STAGE))
    if len(selected) > 2*P.MAX_FACES:
        raise ValueError('Joint reference bank exceeds the bounded target count')
    common, owners, bodies, face_targets = None, set(), set(), set()
    checked = []
    for record in selected:
        params, ref = _record(record, shape, cancelled)
        identity = (params.source_sha256, params.source_pixels_sha256,
                    params.source_shape, params.application_shape, params.reference_identity)
        if common is not None and common != identity:
            raise ValueError('Face/body reference bank disagrees on its source or selected reference')
        common = identity
        owner = (record.stage, ref['face_instance_id'])
        if owner in owners:
            raise ValueError('Joint reference bank contains a duplicate target owner')
        owners.add(owner)
        if record.stage == STAGE:
            body_owner = params.body_identity[:2]
            if body_owner in bodies:
                raise ValueError('Joint reference bank contains a duplicate BodyRef')
            bodies.add(body_owner)
        elif params.amount != 0:
            face_targets.add(params.target_identity)
        if params.amount == 0:
            continue
        y, x, h, w = record.window
        for previous in checked:
            py, px, ph, pw = previous.window
            y0, x0, y1, x1 = max(y, py), max(x, px), min(y+h, py+ph), min(x+w, px+pw)
            if y1 <= y0 or x1 <= x0:
                continue
            for top in range(y0, y1):
                for left in range(x0, x1, BLOCK_PIXELS):
                    _poll(cancelled); right = min(left+BLOCK_PIXELS, x1)
                    one = record.weights[top-y, left-x:right-x]
                    other = previous.weights[top-py, left-px:right-px]
                    if np.any((one > 0) & (other > 0)):
                        raise SkinReferenceBodyRefused('人脸与身体或不同身体的审核范围重叠，不会重复叠加或猜测归属')
        checked.append(record)
    if common is not None and common[-1] in face_targets:
        raise ValueError('Selected reference face must remain unchanged by face/body reference matching')
    _poll(cancelled)
    return selected


def prepare_bank(state, asset_sha256, full_source, analyses, *, assets, body_bank,
                 application_shape, byte_budget, face_records=(), cancelled=lambda: False):
    """Return (body LocalEffects, owner-keyed facts), with no partial publication.

    The source must be captured before repair/portrait effects. Supply the full
    prepared face-reference bank (when active) for cross-stage preflight. Apply
    both stages to current pixels before the existing ONE combined geometry
    resampling. Ordinary BodyRef geometry edits do not alter source fit pixels.
    """
    _poll(cancelled); state = P.check(state); selected = requests(state, asset_sha256)
    if not selected:
        return (), {}
    source, source_shape = F._source_binding(full_source, asset_sha256)
    application_shape = _shape(application_shape)
    E.whole_source_shape({**source, 'orientation': E.ORIENTATION}, application_shape)
    analysis_bytes = F._analysis_bytes(analyses)
    face_records = tuple(face_records)
    if any(record.stage != F.STAGE for record in face_records):
        raise ValueError('Supply only the complete face-reference bank beside body preparation')
    retained_face_bytes = sum(array_bytes(record.weights)+RECORD_BYTES for record in face_records)
    f = source_shape[0]*source_shape[1]; a = application_shape[0]*application_shape[1]
    resident = (full_source.owned_bytes + 2*analysis_bytes + FIXED_BYTES + retained_face_bytes
                + f + a + (8*a + RECORD_BYTES)*len(selected))
    # Projected owner body/excluded and reference face/excluded = 16 bytes/N.
    # Support's 48 bytes/N admission includes manual/competing rasters, masks,
    # validation and full-plane veto temporaries. Only one grid is live at once.
    grid_work = {grid: A._FIXED_BYTES + (16 + A._BYTES_PER_PIXEL)*grid[0]*grid[1]
                 for grid in (source_shape, application_shape)}
    _admit(resident + max(grid_work.values()), byte_budget)
    reference_ref = A.validate_active(state, assets, [ref for ref, _ in selected], body_bank, analyses)
    # Polygon scratch depends on measured face ROI, NOT the whole body canvas.
    # Match support admission's +4 guarded extents for owner/reference vetoes.
    for grid in grid_work:
        largest = 0
        for ref in (*[ref for ref, _ in selected], reference_ref):
            raw = analyses[ref['face_instance_id']]
            _, (x0, y0, x1, y1) = A.FACE_SUPPORT._extent(raw['landmarks'], grid)
            largest = max(largest, min(grid[1], x1-x0+4)*min(grid[0], y1-y0+4))
        grid_work[grid] += A._ROI_BYTES_PER_PIXEL*largest
    required = resident + max(grid_work.values())
    _admit(required, byte_budget)
    pixels = F._validate_source(full_source, cancelled)
    fit_owners = np.zeros(source_shape, dtype=bool)
    app_owners = np.zeros(application_shape, dtype=bool)
    effects, facts = [], {}
    for ref, recipe in selected:
        _poll(cancelled)
        target_raw = analyses[ref['face_instance_id']]
        reference_raw = analyses[reference_ref['face_instance_id']]
        pair = (_project(target_raw, source_shape, cancelled, body=True),
                _project(reference_raw, source_shape, cancelled))
        target, reference, full_facts = A.geometry(state, assets, ref, body_bank, *pair, source_shape,
            byte_budget=byte_budget-resident-16*f, cancelled=cancelled)
        if full_facts['source'] != source:
            raise ValueError('Body-reference review and authenticated source dimensions disagree')
        body_ref = E.ref(full_facts['target']['body_ref'])
        if full_facts['reference']['face_ref'] != reference_ref:
            raise ValueError('Body-reference geometry changed its explicitly selected face')
        tw = _window(tuple(full_facts['target']['source_window']), source_shape)
        rw = _window(tuple(full_facts['reference']['source_window']), source_shape)
        F._claim(fit_owners, target, tw, cancelled)
        # Actual independent body/reference windows are now known. Their native
        # snapshots are additional to the source, projected 16N and two masks8N.
        fit_required = resident + 24*f + N.memory_estimate(rw[2:], tw[2:])
        _admit(fit_required, byte_budget); required = max(required, fit_required)
        measured = N.fit(F._roi(pixels, rw), F._roi(reference, rw),
                         F._roi(pixels, tw), F._roi(target, tw),
                         byte_budget=byte_budget-resident-24*f, cancelled=cancelled)
        del target, reference, pair
        pair = (_project(target_raw, application_shape, cancelled, body=True),
                _project(reference_raw, application_shape, cancelled))
        target, reference, app_facts = A.geometry(state, assets, ref, body_bank, *pair, application_shape,
            byte_budget=byte_budget-resident-16*a, cancelled=cancelled)
        if (app_facts['support_sha256'] != full_facts['support_sha256'] or app_facts['source'] != source
                or app_facts['target']['body_ref'] != body_ref
                or app_facts['reference']['face_ref'] != reference_ref):
            raise ValueError('Body-reference ownership changed between source fit and application support')
        window = _window(tuple(app_facts['target']['source_window']), application_shape)
        F._claim(app_owners, target, window, cancelled)
        content = np.ascontiguousarray(F._roi(target, window)).tobytes()
        weights = np.frombuffer(content, dtype=np.float32).reshape(window[2:])
        params = Parameters(recipe['amount'], measured, asset_sha256, full_source.input_sha256,
            source_shape, application_shape, _identity(ref), _body_identity(body_ref),
            _identity(reference_ref), full_facts['support_sha256'], tw, rw, window,
            coverage_digest(weights)).checked()
        fact = {**app_facts, 'requested': True, 'applied': None, 'stage': STAGE,
            'recipe': recipe, 'face_ref': dict(ref), 'body_ref': dict(body_ref),
            'reference_face_ref': dict(reference_ref), 'body_extension': {'enabled': True},
            'fit_source_dimensions': [source_shape[1], source_shape[0]],
            'application_dimensions': [application_shape[1], application_shape[0]],
            'fit_target_window': list(tw), 'fit_reference_window': list(rw),
            'fit_source_pixels_sha256': full_source.input_sha256,
            'fit_effective_reference_samples': measured.diagnostics[5],
            'fit_effective_target_samples': measured.diagnostics[6],
            'fit_count_per_target': 1, 'composition': 'original-rust-current-pixel-colour-and-brightness',
            'fit_portable': False, 'source_rgb_retained': False,
            'reference_face_unchanged_by_this_operation': True,
            'geometry': 'existing-onepass-source-frame-after-colour', 'memory_admission_bytes': required}
        effects.append(LocalEffect(ref, STAGE, window, weights=weights, amounts=params, facts=fact))
        facts[ref['face_instance_id']] = fact
        del target, reference, pair, content, weights
    validate_joint_records((*face_records, *effects), application_shape=application_shape, cancelled=cancelled)
    _poll(cancelled)
    return tuple(effects), facts
