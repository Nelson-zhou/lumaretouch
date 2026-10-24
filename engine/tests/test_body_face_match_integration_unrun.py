# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: partial separately reviewed body-to-own-face chromatic matching.

LNX-REF-PC-32465-C-d8b09012a9 remains partial. Synthetic source pixels, pose,
face landmarks and model hashes are contract fixtures, not inference evidence,
photographic acceptance, learned AI or measured parity evidence.
No product import, test collection/run, native process, build, typecheck,
inference or download ran while authoring this file.

Positive fixtures use the real face/body/person owners, source analysis checks,
operation-specific support, mask recipe validation/budget/packet/tiling,
snapshots, original/derived adapters, common map and CPU/tensor composition.
Only native boundaries are doubled: body_face_match_native, the shared
skin_evenness_native pointwise apply/legacy prepare, and the local-mask
worker process. Its packet-aware brush double supplies binary capsule interiors
for these zero-feather fixtures; it is NOT Rust raster edge/filter acceptance.
The source-dependent HWC2 and independent pointwise-Y doubles are routing
fixtures, not the native robust-reference/neighbourhood solver. No ownership,
support, render, receipt, replay-evidence or project guard is replaced.
"""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from lumaretouch_engine import body_face_match_state as S
from lumaretouch_engine import body_face_match_layer as LAYER
from lumaretouch_engine import body_face_match_native as N
from lumaretouch_engine import skin_evenness_native as CHROMA, local_mask_recipe as M
from lumaretouch_engine import skin_colour_body_support as REVIEW
from lumaretouch_engine import body_skin_semantics as SEM, body_pose_evidence as EVIDENCE
from lumaretouch_engine import body_pose_state as BODY, arm_shape_project as BODY_PROJECT
from lumaretouch_engine import people_algorithms as A, people_state as P
from lumaretouch_engine import people_associations as LINKS, people_binding as BIND
from lumaretouch_engine import people_resolver as RESOLVE, people_project as PROJECT
from lumaretouch_engine import people_snapshot as SNAP, people_export as EXPORT
from lumaretouch_engine import people_engine_runtime as ENGINE, people_render_runtime as RENDER
from lumaretouch_engine import people_render_plan as PLAN
from lumaretouch_engine import people_pipeline as PIPE, people_effects as EFFECTS
from lumaretouch_engine import people_edit as EDIT, people_document_history as HISTORY
from lumaretouch_engine import people_cross_owner as CROSS
from lumaretouch_engine.people_graph_owner import PeopleGraphOwner, affected_assets
from lumaretouch_engine import face_scope as FACE, skin_colour_support as FACE_SUPPORT
from lumaretouch_engine.ops import enhance as ENHANCE
from lumaretouch_engine import creative_derived_effects as DERIVED
from lumaretouch_engine import creative_derived_repairs as REPAIRS
from lumaretouch_engine import creative_derived_repair_runtime as REPLAY
from test_skin_evenness_integration_unrun import native_prepare_double as legacy_prepare_double
from test_skin_evenness_integration_unrun import native_apply_double, luminance

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = 'synthetic-body-face-match-document'
BUDGET = 512 * 1024**2
ACTIVE = {'version': 1, 'amount': .65}
REQUIREMENT = 'LNX-REF-PC-32465-C-d8b09012a9'
FAMILY = {'family': 'body_face_match', 'operation_id': S.OP}


class ManualWorkerDouble:
    """Native-process seam only; validate the real emitted LMR2 brush packet.

    This limited double handles zero-feather diagonal-axis brush capsules only.
    It deliberately rejects other native functionality rather than pretending
    to implement it. Real Python recipe checks, budgeting, packet construction,
    tile assembly and body ownership/semantic checks remain in the path.
    """
    calls = []

    def transact(self, packet, count):
        assert packet[:4] == b'LMR2'
        sw, sh, x, y, w, h, cx, cy, cw, ch, objects, rgb, channels = struct.unpack_from('<13I', packet, 4)
        assert count == cw*ch and rgb == channels == 0
        assert 0 <= x < sw and 0 <= y < sh and x+w <= sw and y+h <= sh
        yy, xx = np.mgrid[y+cy:y+cy+ch, x+cx:x+cx+cw]
        xx, yy = (xx+.5)/sw, (yy+.5)/sh
        result = np.zeros((ch, cw), np.float64)
        offset = 56
        for _ in range(objects):
            kind, operation, opacity, feather = struct.unpack_from('<BBdI', packet, offset)
            offset += 14
            assert kind == M.KINDS.index('brush') and feather == 0
            assert operation in (M.OPERATIONS.index('add'), M.OPERATIONS.index('subtract'))
            length, = struct.unpack_from('<I', packet, offset)
            offset += 4
            data = np.array(struct.unpack_from('<'+'d'*(length*2+4), packet, offset), np.float64)
            offset += (length*2+4)*8
            points, axes = data[:-4].reshape(length, 2), data[-4:].reshape(2, 2)
            assert axes[0, 1] == axes[1, 0] == 0 and axes[0, 0] > 0 and axes[1, 1] > 0
            scale = np.array([axes[0, 0], axes[1, 1]])
            field = np.zeros((ch, cw), bool)
            pairs = zip(points, points[1:]) if length > 1 else [(points[0], points[0])]
            for start, end in pairs:
                a, b = start/scale, end/scale
                dx, dy = xx/scale[0]-a[0], yy/scale[1]-a[1]
                vector = b-a
                norm = float(vector @ vector)
                t = np.clip((dx*vector[0]+dy*vector[1])/norm, 0, 1) if norm else np.zeros_like(dx)
                field |= (dx-t*vector[0])**2+(dy-t*vector[1])**2 <= 1
            weight = field.astype(np.float64)*opacity
            result = np.maximum(result, weight) if operation == M.OPERATIONS.index('add') else result*(1-weight)
        assert offset == len(packet)
        self.calls.append({'source_shape': (sh, sw), 'tile': (y, x, h, w), 'count': count})
        return np.rint(result*255).astype(np.uint8).tobytes()

    def close(self, success=False):
        assert type(success) is bool


@pytest.fixture(autouse=True)
def native_boundaries_only():
    ManualWorkerDouble.calls = []
    with patch.object(N, 'available', return_value=True), \
            patch.object(CHROMA, 'available', return_value=True), patch.object(M, '_Worker', ManualWorkerDouble):
        yield


def native_match_prepare_double(calls, *, zero=False):
    """Split own-source routing marks, NOT native robust-reference acceptance.

    The distinct body and face crops must remain immutable and each coverage
    must match its actual RGB grid. A small face-colour-dependent mark proves
    the own-face reference reaches the native seam, never a serialized donor.
    """
    def prepare(body_rgb, body_coverage, face_rgb, face_coverage, amount, *, radius, cancelled=None):
        for rgb, coverage in ((body_rgb, body_coverage), (face_rgb, face_coverage)):
            assert rgb.dtype == coverage.dtype == np.float32
            assert rgb.shape == (*coverage.shape, 3)
            assert not rgb.flags.writeable and not coverage.flags.writeable
            assert np.isfinite(rgb).all() and np.all((rgb >= 0) & (rgb <= 1))
            assert np.any(coverage > 0) and np.all((coverage >= 0) & (coverage <= 1))
        assert type(radius) is int and 4 <= radius <= 256
        assert type(amount) in (int, float) and 0 < amount <= 1
        if cancelled is not None and cancelled():
            raise InterruptedError('Synthetic native body/own-face preparation cancellation')
        calls.append({'source': body_rgb.copy(), 'coverage': body_coverage.copy(),
                      'face_source': face_rgb.copy(), 'face_coverage': face_coverage.copy(),
                      'amount': amount, 'radius': radius})
        face = np.mean(face_rgb[face_coverage > 0], axis=0, dtype=np.float64)
        body = np.mean(body_rgb[body_coverage > 0], axis=0, dtype=np.float64)
        # Absolute source dependence distinguishes rebuilt repaired-source
        # references too, without claiming to approximate the native estimator.
        marker = np.array([.018+.032*face[0]-.010*body[0],
                           -.014-.028*face[2]+.008*body[2]], np.float32)
        shift = body_coverage[..., None]*np.float32(amount)*marker
        if zero:
            shift.fill(0)
        shift.setflags(write=False)
        return shift
    return prepare


def set_recipe(state, ref, recipe, operation=None):
    for path, value in A.leaves(recipe).items():
        state = P.set_override(state, 'face', ref['face_instance_id'], operation or S.OP, path, value)
    return state


def fixture(*, recipe=ACTIVE, retained=True, linked=True, asset='a'*64, size=256,
            producer_size=None, tone=0., pose_fault=None):
    """Independent synthetic whole-source evidence, never an ownership mock."""
    producer = size if producer_size is None else producer_size
    frame = {'sha256': asset, 'width': size, 'height': size, 'orientation': EVIDENCE.ORIENTATION}
    landmarks = np.full((478, 3), .5, np.float32)
    def ellipse(indices, cx, cy, rx, ry):
        for i, index in enumerate(indices):
            angle = 2*np.pi*i/len(indices)
            landmarks[index, :2] = [cx+rx*np.cos(angle), cy+ry*np.sin(angle)]
    ellipse(FACE.FACE_OVAL, .5, .17, .15, .13)
    ellipse(ENHANCE.EYE_RING_LEFT, .45, .14, .025, .012)
    ellipse(ENHANCE.EYE_RING_RIGHT, .55, .14, .025, .012)
    ellipse(FACE.BROW_LEFT, .55, .11, .03, .01)
    ellipse(FACE.BROW_RIGHT, .45, .11, .03, .01)
    ellipse(FACE.LIPS, .5, .23, .03, .015)
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b'*64,
        'semantic_model_sha256': 'c'*64, 'landmark_digest': BIND.landmark_digest(landmarks),
        'status': 'verified', 'source_width': size, 'source_height': size, 'orientation': EVIDENCE.ORIENTATION}
    state = P.empty()
    face = P.new_face(asset, [.33, .02, .67, .31], evidence)
    state['faces'][face['face_instance_id']] = face
    ref = P.face_ref(face)
    person = None
    if linked:
        state, person = LINKS.create_person(state)
        state = LINKS.set_link(state, ref['face_instance_id'], person, 'confirmed', user_confirmed=True)
    points = [{'index': i, 'x': .5, 'y': .5, 'z': 0., 'visibility': 0., 'presence': 0.} for i in range(33)]
    for index, x, y in ((11, .3, .35), (12, .7, .35), (23, .35, .75), (24, .65, .75)):
        points[index].update(x=x, y=y, visibility=.95, presence=.95)
    if pose_fault == 'confidence': points[11]['visibility'] = .49
    elif pose_fault == 'outside': points[11]['x'] = -0.01
    elif pose_fault == 'collapsed': points[12].update(x=.3, y=.35)
    measured = EVIDENCE.create(source_frame=frame, values=points, backend_version='fixture-only',
        backend_code_sha256='d'*64, model_id='synthetic-contract-fixture', model_sha256='e'*64,
        input_rgb_sha256='f'*64, input_dimensions=(producer, producer))
    bank = BODY.add_run(BODY.empty(), {'source': frame, 'records': [measured],
        'detector_limit': 4, 'limit_reached': False, 'census_complete': False})
    if linked:
        bank = BODY.associate(bank, measured['body_ref'], person, state, user_confirmed=True)
    yy, xx = np.mgrid[:producer, :producer]
    skin = np.full((producer, producer), .95, np.float32)
    body_skin = np.where((yy+.5)/producer >= .36, skin, 0).astype(np.float32)
    analysis = {'face_ref': deepcopy(ref), 'evidence': deepcopy(evidence), 'landmarks': landmarks,
        'excluded': np.zeros_like(skin), 'skin': skin.copy(), 'face_skin': skin.copy(), 'body_skin': body_skin,
        'face_skin_observation': {'contract': FACE_SUPPORT.CONTRACT, 'source_sha256': asset,
            'semantic_model_sha256': 'c'*64, 'producer_width': producer, 'producer_height': producer},
        'body_skin_observation': {'contract': SEM.CONTRACT, 'source_sha256': asset,
            'semantic_model_sha256': 'c'*64, 'detector_model_sha256': 'b'*64,
            'producer_width': producer, 'producer_height': producer}}
    review = {'body_ref': measured['body_ref'], 'points_sha256': measured['points_sha256'],
        'visible': True, 'unoccluded': True, 'ownership_confirmed': True,
        'recipe': {'version': 1, 'domain': 'source-normalized', 'objects': [{
            'id': 'reviewed-own-body', 'name': 'Synthetic own-body contract fixture', 'kind': 'brush',
            'enabled': True, 'operation': 'add', 'opacity': 1., 'feather': 0.,
            'points': [[.5, .52], [.5, .76]], 'axes': [[.2, 0.], [0., .2]]}]}}
    assets = {}
    if retained:
        state, assets = REVIEW.retain(state, assets, ref, bank, analysis, review, **FAMILY)
    if recipe is not None:
        state = set_recipe(state, ref, recipe)
    yy, xx = np.mgrid[:size, :size]
    rgb = np.empty((size, size, 3), np.float32)
    rgb[..., 0] = .46+.025*np.sin(xx/size*5)+tone
    rgb[..., 1] = .37+.018*np.cos(yy/size*4)+tone
    rgb[..., 2] = .29+.02*np.sin((xx+yy)/size*3)+tone
    original = np.rint(rgb.astype(np.float64)*65535).astype(np.uint16)
    binding = {key: frame[key] for key in ('sha256', 'width', 'height')}
    return SimpleNamespace(state=state, assets=assets, ref=ref, bank=bank, analysis=analysis,
                           review=review, original=original, binding=binding, frame=frame)


def resolved(value):
    return A.recipes(RESOLVE.resolve(value.state, value.ref['face_instance_id'], A.defaults()))


def frozen(value, *, derived=False, document=DOCUMENT):
    snap = SNAP.capture(value.state, value.binding['sha256'], {value.ref['face_instance_id']: value.analysis})
    snap.update(document_id=document, support_assets=deepcopy(value.assets))
    if derived:
        snap['creative_source'] = deepcopy(value.binding)
    return snap


def export(value, *, derived=False, repaired=None, proof=None, document=DOCUMENT):
    source = value.original.astype(np.float32)/65535. if derived else value.original
    return ENGINE.prepare_export(frozen(value, derived=derived, document=document), source, repaired,
        byte_budget=BUDGET, document_id=document, body_pose=BODY_PROJECT.snapshot(value.bank, value.frame),
        creative_repair_evidence=proof)


def command(value, recipe, *, unset=False):
    return {'document_id': DOCUMENT, 'document_epoch': 'synthetic-epoch', 'document_revision': 7,
        'state_revision': value.state['revision'], 'association_revision': value.state['association_revision'],
        'request_id': 'synthetic-body-face-match-request', 'action': 'patch',
        'target': {'scope': 'face', 'target_id': value.ref['face_instance_id'], 'face_ref': deepcopy(value.ref)},
        'payload': {'patches': [{'operation_id': S.OP, 'parameter_path': path, 'unset': unset,
            **({} if unset else {'value': leaf})} for path, leaf in A.leaves(recipe).items()]}}


def stage(value, request):
    return EDIT.stage(request, value.state, document_id=DOCUMENT, document_epoch='synthetic-epoch',
        document_revision=7, asset_sha256=value.binding['sha256'],
        source_dimensions=(value.binding['width'], value.binding['height']))


def record(prepared, value):
    assert prepared.geometry.delta.shape == (1, *value.original.shape[:2], 2)
    assert not prepared.geometry.delta.flags.writeable and not np.any(prepared.geometry.delta)
    assert len(prepared.effects) == 1
    effect = prepared.effects[0]
    assert effect.stage == 'body_face_match' and effect.face_ref == value.ref
    assert effect.delta is None and effect.weights is None and effect.amounts is None
    assert effect.chroma_shift.shape == (*effect.window[2:], 2)
    assert effect.chroma_shift.dtype == np.float32 and not effect.chroma_shift.flags.writeable
    assert np.isfinite(effect.chroma_shift).all() and np.any(effect.chroma_shift != 0)
    assert effect.facts['reference_support']['face_ref'] == value.ref
    assert effect.facts['reference_support']['source'] == value.binding
    assert effect.facts['face_reference_samples'] >= 64
    assert effect.facts['body_reference_samples'] >= 64
    assert effect.facts['reference_method'] == 'original-source-own-face-robust-log-chroma'
    assert effect.facts['reference_is_later_corrected_face'] is False
    assert effect.facts['body_to_face_matching'] is True
    assert effect.facts['runtime_quality_accepted'] is False
    return effect


def expanded(effect, shape):
    field = np.zeros((*shape, 2), np.float32)
    y, x, h, w = effect.window
    field[y:y+h, x:x+w] = effect.chroma_shift
    return field


def assert_source_crops(call, effect, source):
    """Both true RGB ROIs, not a donor/reference token or body-size placeholder."""
    y, x, h, w = effect.window
    fy, fx, fh, fw = effect.facts['reference_support']['source_window']
    np.testing.assert_array_equal(call['source'], source[y:y+h, x:x+w])
    np.testing.assert_array_equal(call['face_source'], source[fy:fy+fh, fx:fx+fw])
    assert call['face_source'].shape != call['source'].shape
    assert not np.shares_memory(call['face_source'], call['source'])
    # The native seam receives actual own-face pixels separately; only body
    # HWC2 is retained and reference pixels never enter a portable scalar leaf.
    assert effect.facts['reference_support']['scope'] == 'selected-own-face-original-source-reference'


def test_operation_maps_exact_partial_requirement_and_only_its_amount():
    assert S.OP == 'lnx.body_face_match.v1' and S.OP in DERIVED.OPERATIONS
    assert S.VERSION == 1 and S.CONTROL_ID == REQUIREMENT and S.KEYS == ('amount',)
    assert A.defaults()[S.OP] == {'/amount': 0.} and S.OP not in A.GEOMETRY
    assert A.defaults()['lnx.skin_evenness.v1'] == {'/amount': 0.}
    assert A.defaults()['lnx.skin_colour.v1'] == {'/temperature': 0., '/tint': 0.}
    assert A.defaults()['lnx.skin_finish.v1'] == {'/whitening': 0., '/rosiness': 0.}
    assert REVIEW.family_spec(**FAMILY) == ('body_face_match_visibility', S.OP)
    value = fixture(recipe=None)
    DERIVED._patches(command(value, ACTIVE)['payload'])
    registry = json.loads((ROOT/'docs/p0/registry-extensions.json').read_text())
    row = next(item for item in registry['entries'] if item['operation_id'] == S.OP)
    assert row['neutral'] == S.neutral() and row['source_requirement'] == 'PC-32465-C-d8b09012a9'


@pytest.mark.parametrize('path,value', [('/amount', False), ('/amount', True), ('/amount', '0'),
    ('/amount', -.01), ('/amount', 1.01), ('/amount', float('nan')), ('/amount', float('inf')),
    ('/version', 1), ('/reference_rgb', []), ('/face_ref', {}), ('/body_ref', {}),
    ('/coverage', []), ('/chroma_shift', []), ('/reference', .5), ('/skin_texture', .5), ('/brightness', .5)])
def test_scalar_transport_refuses_coercion_donor_pixels_support_and_reference_transport(path, value):
    with pytest.raises(ValueError):
        DERIVED._leaf(S.OP, path, value)


@pytest.mark.parametrize('family', ['skin_colour', 'skin_finish', 'body_skin_evenness'])
def test_other_family_review_cannot_authorize_active_body_face_matching(family):
    value = fixture(retained=False)
    value.state, value.assets = REVIEW.retain(value.state, {}, value.ref, value.bank,
                                             value.analysis, value.review, family=family)
    saved = deepcopy(value.state)
    with patch.object(N, 'prepare', side_effect=AssertionError('Borrowed another family review')) as solve:
        with pytest.raises(ValueError):
            export(value)
    solve.assert_not_called()
    assert value.state == saved and ManualWorkerDouble.calls == []


def test_missing_optional_match_extension_cannot_fall_back_to_body_evenness():
    value = fixture()
    with patch.object(N, 'available', return_value=False), \
            patch.object(N, 'prepare', side_effect=AssertionError('Unavailable matching prepared')) as match, \
            patch.object(CHROMA, 'prepare', side_effect=AssertionError('Body-evenness fallback used')) as legacy:
        with pytest.raises((ValueError, RuntimeError)):
            export(value)
    match.assert_not_called()
    legacy.assert_not_called()


@pytest.mark.parametrize('flag', REVIEW.FLAGS)
def test_each_body_ownership_visibility_flag_is_required_before_support_creation(flag):
    value = fixture(retained=False)
    value.review[flag] = False
    before = deepcopy(value.state)
    with pytest.raises(ValueError):
        REVIEW.retain(value.state, value.assets, value.ref, value.bank, value.analysis, value.review, **FAMILY)
    assert value.state == before and value.assets == {} and ManualWorkerDouble.calls == []


@pytest.mark.parametrize('fault', ['missing-descriptor', 'missing-body-bank', 'unlinked-body',
    'disabled-body', 'body-points', 'people-revision', 'foreign-face', 'landmarks',
    'body-observation', 'body-semantics', 'face-observation', 'face-semantics',
    'foreign-reference-model', 'empty-face-reference', 'excluded-missing', 'occluded', 'black-source'])
def test_active_owner_or_source_failure_refuses_before_native_solver(fault):
    value = fixture()
    if fault == 'missing-descriptor': value.state = REVIEW.detach(value.state, value.ref, **FAMILY)
    elif fault == 'missing-body-bank': value.bank = BODY.empty()
    elif fault == 'unlinked-body': value.bank = BODY.unlink(value.bank, value.review['body_ref'])
    elif fault == 'disabled-body': BODY.target(value.bank, value.review['body_ref'])['enabled'] = False
    elif fault == 'body-points': BODY.target(value.bank, value.review['body_ref'])['record']['points'][11]['x'] += .01
    elif fault == 'people-revision': value.state['association_revision'] += 1
    elif fault == 'foreign-face': value.analysis['face_ref']['asset_sha256'] = '9'*64
    elif fault == 'landmarks': value.analysis['landmarks'][0, 0] += np.float32(.01)
    elif fault == 'body-observation': value.analysis['body_skin_observation']['source_sha256'] = '9'*64
    elif fault == 'body-semantics': value.analysis['body_skin'] = value.analysis['body_skin_observation'] = None
    elif fault == 'face-observation': value.analysis['face_skin_observation']['source_sha256'] = '9'*64
    elif fault == 'face-semantics': value.analysis['face_skin'] = value.analysis['face_skin_observation'] = None
    elif fault == 'foreign-reference-model': value.analysis['face_skin_observation']['semantic_model_sha256'] = '9'*64
    elif fault == 'empty-face-reference': value.analysis['face_skin'][:] = 0
    elif fault == 'excluded-missing': value.analysis['excluded'] = None
    elif fault == 'occluded': value.analysis['excluded'][:] = 1
    else: value.original[:] = 0
    saved = value.original.copy()
    with patch.object(N, 'prepare', side_effect=AssertionError('Unadmitted body source reached solver')) as solve:
        with pytest.raises(ValueError):
            export(value)
    solve.assert_not_called()
    np.testing.assert_array_equal(value.original, saved)


@pytest.mark.parametrize('fault', ['confidence', 'outside', 'collapsed'])
def test_source_scale_requires_actual_retained_pose_not_face_box_or_mask_extent(fault):
    value = fixture(pose_fault=fault)
    with patch.object(N, 'prepare', side_effect=AssertionError('Unmeasured scale reached solver')) as solve:
        with pytest.raises(ValueError):
            export(value)
    solve.assert_not_called()


@pytest.mark.parametrize('retained', [False, True])
def test_exact_zero_ignores_only_dormant_body_review_without_analysis_or_native_and_preserves_rgb16(retained):
    value = fixture(recipe=S.neutral(), retained=retained)
    # Only an exactly neutral body-only descriptor may be dormant. Its scalar
    # stays validated, the export still enters the checked path when attached,
    # and other assets or malformed/active intent keep their analysis guards.
    snap = SNAP.capture(value.state, value.binding['sha256'], {})
    snap.update(document_id=DOCUMENT, support_assets=deepcopy(value.assets))
    with patch.object(N, 'available', side_effect=AssertionError('Neutral queried native')) as ready, \
            patch.object(N, 'prepare', side_effect=AssertionError('Neutral prepared')) as solve, \
            patch.object(CHROMA, 'apply', side_effect=AssertionError('Neutral applied')) as apply:
        prepared = ENGINE.prepare_export(snap, value.original, None, byte_budget=BUDGET, document_id=DOCUMENT)
        assert LAYER.prepare(None, None, None, S.neutral(), people_state=None,
                             body_assets=None, body_bank=None, byte_budget=0) == []
        source = value.original.astype(np.float32)/65535.
        actual, facts = prepared.apply_source_stage('body_face_match', source)
        assert actual is source and facts['changed_pixels'] == 0
    for boundary in (ready, solve, apply):
        boundary.assert_not_called()
    assert not prepared.effects and not prepared.face_fields
    assert not any(entry['requires_analysis'] for entry in prepared.plan['entries'])
    assert ManualWorkerDouble.calls == [] and EXPORT.fastpath_blocker(snap) is retained
    np.testing.assert_array_equal(prepared.geometry.warp_original(value.original), value.original)


@pytest.mark.parametrize('fault', ['active', 'bool', 'string', 'unknown-leaf', 'conflict', 'other-asset', 'other-operation'])
def test_dormant_body_descriptor_exception_never_hides_active_invalid_conflicted_or_other_owned_intent(fault):
    value = fixture(recipe=None)
    if fault == 'active': value.state = set_recipe(value.state, value.ref, ACTIVE)
    elif fault == 'bool': value.state = set_recipe(value.state, value.ref, {'version': 1, 'amount': False})
    elif fault == 'string': value.state = set_recipe(value.state, value.ref, {'version': 1, 'amount': '0'})
    elif fault == 'unknown-leaf':
        value.state = P.set_override(value.state, 'face', value.ref['face_instance_id'], S.OP, '/reference', .2)
    elif fault == 'conflict':
        for group, amount in (('body-face-match-group-a', .2), ('body-face-match-group-b', .4)):
            value.state = LINKS.set_group(value.state, group, label=group, priority=1, face_ids=[value.ref['face_instance_id']])
            value.state = P.set_override(value.state, 'group', group, S.OP, '/amount', amount)
    elif fault == 'other-asset':
        value.state, value.assets = REVIEW.retain(value.state, value.assets, value.ref, value.bank,
                                                 value.analysis, value.review, family='skin_colour')
    else:
        value.state = set_recipe(value.state, value.ref, ACTIVE, 'lnx.skin_evenness.v1')
    snap = SNAP.capture(value.state, value.binding['sha256'], {})
    snap.update(document_id=DOCUMENT, support_assets=deepcopy(value.assets))
    plan = PLAN.build(value.state, value.binding['sha256'], A.defaults(), max_faces=32,
        per_face_cost=1, total_budget=32, available_evidence={}, operation_check=lambda face, resolved: [])
    assert plan['entries'][0]['requires_analysis'] is True
    assert 'frozen_source_analysis_missing_or_stale' in plan['entries'][0]['reasons']
    with patch.object(N, 'prepare', side_effect=AssertionError('Missing analysis reached native')) as solve:
        with pytest.raises(ValueError):
            ENGINE.prepare_export(snap, value.original, None, byte_budget=BUDGET, document_id=DOCUMENT)
    solve.assert_not_called()
    assert ManualWorkerDouble.calls == []


def test_neutral_wrong_kind_keeps_analysis_requirement_and_fails_operation_owned_project_validation():
    value = fixture(recipe=S.neutral())
    value.state['faces'][value.ref['face_instance_id']]['local_assets'][REVIEW.FACE_MATCH_KIND]['kind'] = REVIEW.KIND
    # The generic owner checks structural descriptor ownership, not this
    # operation's key/kind relation. The real planner must not mark it dormant;
    # the operation-owned project validator then rejects the mismatched kind.
    owner = PeopleGraphOwner(value.state)
    plan = PLAN.build(owner.snapshot(), value.binding['sha256'], A.defaults(), max_faces=32,
        per_face_cost=1, total_budget=32, available_evidence={}, operation_check=lambda face, resolved: [])
    assert plan['entries'][0]['requires_analysis'] is True
    assert 'frozen_source_analysis_missing_or_stale' in plan['entries'][0]['reasons']
    with pytest.raises(ValueError):
        REVIEW.validate_project({'people_graph': owner.snapshot(), 'people_support_assets': value.assets}, **FAMILY)
    assert ManualWorkerDouble.calls == []


@pytest.mark.parametrize('active_operation', [None, S.OP, 'lnx.body_skin_evenness.v1'])
def test_two_dormant_body_descriptors_require_both_exact_recipes_neutral(active_operation):
    value = fixture(recipe=S.neutral())
    value.state, value.assets = REVIEW.retain(value.state, value.assets, value.ref, value.bank,
        value.analysis, value.review, family='body_skin_evenness', operation_id='lnx.body_skin_evenness.v1')
    value.state = set_recipe(value.state, value.ref, S.neutral(), 'lnx.body_skin_evenness.v1')
    if active_operation is not None:
        value.state = set_recipe(value.state, value.ref, ACTIVE, active_operation)
    snap = SNAP.capture(value.state, value.binding['sha256'], {})
    snap.update(document_id=DOCUMENT, support_assets=deepcopy(value.assets))
    plan = PLAN.build(value.state, value.binding['sha256'], A.defaults(), max_faces=32,
        per_face_cost=1, total_budget=32, available_evidence={}, operation_check=lambda face, resolved: [])
    assert plan['entries'][0]['requires_analysis'] is (active_operation is not None)
    with patch.object(N, 'available', side_effect=AssertionError('Missing-analysis match queried native')), \
            patch.object(N, 'prepare', side_effect=AssertionError('Missing-analysis match prepared')), \
            patch.object(CHROMA, 'available', side_effect=AssertionError('Missing-analysis evenness queried native')), \
            patch.object(CHROMA, 'prepare', side_effect=AssertionError('Missing-analysis evenness prepared')):
        if active_operation is None:
            prepared = ENGINE.prepare_export(snap, value.original, None, byte_budget=BUDGET, document_id=DOCUMENT)
            assert not prepared.effects and not prepared.face_fields
            np.testing.assert_array_equal(prepared.geometry.warp_original(value.original), value.original)
        else:
            with pytest.raises(ValueError):
                ENGINE.prepare_export(snap, value.original, None, byte_budget=BUDGET, document_id=DOCUMENT)
    assert ManualWorkerDouble.calls == []


@pytest.mark.parametrize('amount', [.2, .65, 1.])
def test_original_rgb16_and_derived_float_rebuild_identical_owned_body_field(amount):
    value = fixture(recipe={'version': 1, 'amount': amount})
    before, assets, bank = deepcopy(value.state), deepcopy(value.assets), deepcopy(value.bank)
    source = value.original.astype(np.float32)/65535.
    solves, applies = [], []
    with patch.object(N, 'prepare', side_effect=native_match_prepare_double(solves)), \
            patch.object(CHROMA, 'apply', side_effect=native_apply_double(applies)):
        original, derived = export(value), export(value, derived=True)
        a, b = record(original, value), record(derived, value)
        assert a.window == b.window and not np.shares_memory(a.chroma_shift, b.chroma_shift)
        np.testing.assert_array_equal(a.chroma_shift, b.chroma_shift)
        np.testing.assert_array_equal(solves[0]['source'], solves[1]['source'])
        np.testing.assert_array_equal(solves[0]['face_source'], solves[1]['face_source'])
        assert_source_crops(solves[0], a, source)
        assert_source_crops(solves[1], b, source)
        output, facts = original.apply_source_stage('body_face_match', source)
        other, _ = derived.apply_source_stage('body_face_match', source)
    assert len(solves) == len(applies) == 2 and len(ManualWorkerDouble.calls) >= 2
    np.testing.assert_array_equal(output, other)
    protected = ~np.any(expanded(a, source.shape[:2]) != 0, axis=2)
    np.testing.assert_array_equal(output[protected], source[protected])
    np.testing.assert_array_equal(output[:80], source[:80])
    np.testing.assert_allclose(luminance(output), luminance(source), rtol=0, atol=2e-7)
    assert facts['changed_pixels'] > 0 and np.any(output != source)
    assert value.state == before and value.assets == assets and value.bank == bank
    expected = (sum(field.resident_bytes() for field in (*original.face_fields, *original.body_fields))
                + original.geometry.delta.nbytes + original.geometry.owner.nbytes + a.chroma_shift.nbytes)
    assert RENDER.retained_bytes(original) == expected


def test_actual_own_face_colour_change_rebuilds_body_field_but_never_edits_face_pixels():
    value = fixture()
    source = value.original.astype(np.float32)/65535.
    repaired = source.copy()
    repaired[:80, :, 0] += np.float32(.06)
    repaired[:80, :, 2] -= np.float32(.025)
    proof = REPLAY.make_evidence(value.binding, source, repaired, REPAIRS.digest_ops([], [], value.binding))
    calls, applications = [], []
    with patch.object(N, 'prepare', side_effect=native_match_prepare_double(calls)), \
            patch.object(CHROMA, 'apply', side_effect=native_apply_double(applications)):
        original = export(value, derived=True)
        changed = export(value, derived=True, repaired=repaired, proof=proof)
        before, after = record(original, value), record(changed, value)
        assert_source_crops(calls[0], before, source)
        assert_source_crops(calls[1], after, repaired)
        assert before.window == after.window
        np.testing.assert_array_equal(calls[0]['coverage'], calls[1]['coverage'])
        np.testing.assert_array_equal(calls[0]['face_coverage'], calls[1]['face_coverage'])
        own_body = calls[0]['coverage'] > 0
        np.testing.assert_array_equal(calls[0]['source'][own_body], calls[1]['source'][own_body])
        assert not np.array_equal(calls[0]['face_source'], calls[1]['face_source'])
        assert not np.array_equal(before.chroma_shift, after.chroma_shift)
        output, facts = changed.apply_source_stage('body_face_match', repaired)
    assert len(calls) == 2 and len(applications) == 1 and facts['changed_pixels'] > 0
    np.testing.assert_array_equal(output[:80], repaired[:80])
    assert np.any(output[90:] != repaired[90:])
    np.testing.assert_allclose(luminance(output), luminance(repaired), rtol=0, atol=2e-7)
    np.testing.assert_array_equal(value.original.astype(np.float32)/65535., source)


def test_own_face_matching_and_face_evenness_keep_separate_fields_and_stage_consumers():
    value = fixture()
    value.state = set_recipe(value.state, value.ref, {'version': 1, 'amount': .4}, 'lnx.skin_evenness.v1')
    source = value.original.astype(np.float32)/65535.
    calls, legacy_calls, applications = [], [], []
    with patch.object(N, 'prepare', side_effect=native_match_prepare_double(calls)), \
            patch.object(CHROMA, 'prepare', side_effect=legacy_prepare_double(legacy_calls)), \
            patch.object(CHROMA, 'apply', side_effect=native_apply_double(applications)):
        prepared = export(value)
        assert len(calls) == len(legacy_calls) == 1 and len(prepared.effects) == 2
        fields = {effect.stage: expanded(effect, source.shape[:2]) for effect in prepared.effects}
        assert set(fields) == {'skin_evenness', 'body_face_match'}
        face = np.any(fields['skin_evenness'] != 0, axis=2)
        body = np.any(fields['body_face_match'] != 0, axis=2)
        assert np.any(face) and np.any(body) and not np.any(face & body)
        assert not np.any(body[:80]) and not np.any(face[90:])
        body_output, _ = prepared.apply_source_stage('body_face_match', source)
        face_output, _ = prepared.apply_source_stage('skin_evenness', source)
        both, _ = prepared.apply_source_stage('skin_evenness', body_output)
        np.testing.assert_array_equal(body_output[~body], source[~body])
        np.testing.assert_array_equal(face_output[~face], source[~face])
        np.testing.assert_array_equal(both[body], body_output[body])
        np.testing.assert_array_equal(both[face], face_output[face])
        np.testing.assert_allclose(luminance(both), luminance(source), rtol=0, atol=2e-7)
    body_effect = next(effect for effect in prepared.effects if effect.stage == 'body_face_match')
    assert body_effect.facts['body_to_face_matching'] is True
    assert body_effect.facts['body_ref'] == value.review['body_ref']
    assert body_effect.facts['body_support']['support_sha256'] in value.assets
    assert not np.any(prepared.geometry.delta) and len(applications) == 3


def test_body_matching_and_within_body_evenness_need_independent_reviews_and_fields():
    value = fixture()
    value.state, value.assets = REVIEW.retain(value.state, value.assets, value.ref, value.bank,
        value.analysis, value.review, family='body_skin_evenness', operation_id='lnx.body_skin_evenness.v1')
    value.state = set_recipe(value.state, value.ref, {'version': 1, 'amount': .4}, 'lnx.body_skin_evenness.v1')
    source = value.original.astype(np.float32)/65535.
    matches, evenness = [], []
    with patch.object(N, 'prepare', side_effect=native_match_prepare_double(matches)), \
            patch.object(CHROMA, 'prepare', side_effect=legacy_prepare_double(evenness)):
        prepared = export(value)
    fields = {effect.stage: effect for effect in prepared.effects}
    assert set(fields) == {'body_face_match', 'body_skin_evenness'}
    assert len(matches) == len(evenness) == 1
    assert_source_crops(matches[0], fields['body_face_match'], source)
    np.testing.assert_array_equal(matches[0]['source'], evenness[0]['source'])
    np.testing.assert_array_equal(matches[0]['coverage'], evenness[0]['coverage'])
    assert not np.array_equal(fields['body_face_match'].chroma_shift, fields['body_skin_evenness'].chroma_shift)
    assert not np.shares_memory(fields['body_face_match'].chroma_shift, fields['body_skin_evenness'].chroma_shift)
    assert fields['body_face_match'].facts['body_to_face_matching'] is True
    assert fields['body_skin_evenness'].facts['body_to_face_matching'] is False
    assert (fields['body_face_match'].facts['body_support']['support_sha256'] !=
            fields['body_skin_evenness'].facts['body_support']['support_sha256'])
    assert not np.any(prepared.geometry.delta)


def test_neutral_matching_does_not_load_optional_extension_or_break_existing_body_evenness():
    value = fixture(recipe=S.neutral())
    value.state, value.assets = REVIEW.retain(value.state, value.assets, value.ref, value.bank,
        value.analysis, value.review, family='body_skin_evenness', operation_id='lnx.body_skin_evenness.v1')
    value.state = set_recipe(value.state, value.ref, ACTIVE, 'lnx.body_skin_evenness.v1')
    with patch.object(N, 'available', side_effect=AssertionError('Neutral match queried optional symbol')) as ready, \
            patch.object(N, 'prepare', side_effect=AssertionError('Neutral match solved reference')) as match, \
            patch.object(CHROMA, 'prepare', side_effect=legacy_prepare_double(calls := [])):
        prepared = export(value)
    ready.assert_not_called()
    match.assert_not_called()
    assert len(calls) == 1 and len(prepared.effects) == 1
    assert prepared.effects[0].stage == 'body_skin_evenness'
    assert prepared.effects[0].facts['body_to_face_matching'] is False


@pytest.mark.parametrize('with_face', [False, True])
@pytest.mark.parametrize('leaf', [False, True, '0', -.01, 1.01, .25])
def test_invalid_or_active_missing_analysis_cannot_hide_in_original_export_fastpath(with_face, leaf):
    value = fixture(recipe=None, retained=False)
    state = value.state if with_face else P.empty()
    state = P.set_override(state, 'all_people', value.binding['sha256'], S.OP, '/amount', leaf)
    snap = SNAP.capture(state, value.binding['sha256'], {})
    snap.update(document_id=DOCUMENT, support_assets={})
    assert EXPORT.fastpath_blocker(snap)
    with patch.object(N, 'prepare', side_effect=AssertionError('Unadmitted photo reached solver')) as solve:
        with pytest.raises(ValueError):
            ENGINE.prepare_export(snap, value.original, None, byte_budget=BUDGET, document_id=DOCUMENT)
    solve.assert_not_called()
    assert ManualWorkerDouble.calls == []


@pytest.mark.parametrize('derived', [False, True])
@pytest.mark.parametrize('fault', ['document', 'dtype', 'alpha', 'body-source', 'budget'])
def test_export_document_precision_body_source_and_memory_fences_precede_solver(derived, fault):
    value = fixture()
    snap = frozen(value, derived=derived)
    source = value.original.astype(np.float32)/65535. if derived else value.original
    body = BODY_PROJECT.snapshot(value.bank, value.frame)
    budget = BUDGET
    if fault == 'document': snap['document_id'] = 'different-document'
    elif fault == 'dtype': source = value.original if derived else value.original.astype(np.float32)/65535.
    elif fault == 'alpha': source = np.concatenate((source, np.ones_like(source[..., :1])), axis=2)
    elif fault == 'body-source': body['source']['sha256'] = '9'*64
    else: budget = 1
    with patch.object(N, 'prepare', side_effect=AssertionError('Invalid export reached solver')) as solve:
        with pytest.raises(ValueError):
            ENGINE.prepare_export(snap, source, None, byte_budget=budget,
                                  document_id=DOCUMENT, body_pose=body)
    solve.assert_not_called()


def test_body_support_excludes_all_retained_face_boxes_and_unreviewed_or_nonbody_pixels():
    value = fixture()
    box = [.39, .58, .48, .68]
    evidence = {'backend': 'manual_region', 'detector_model_sha256': None, 'semantic_model_sha256': None,
        'landmark_digest': None, 'status': 'unresolved', 'source_width': 256, 'source_height': 256,
        'orientation': EVIDENCE.ORIENTATION}
    other = P.new_face(value.binding['sha256'], box, evidence, manual=True)
    other['enabled'] = False
    value.state['faces'][other['face_instance_id']] = other
    value.analysis['excluded'][170:180, 130:140] = 1
    value.analysis['body_skin'][145:155, 120:130] = 0
    with patch.object(N, 'prepare', side_effect=native_match_prepare_double([])):
        prepared = export(value)
    field = expanded(record(prepared, value), value.original.shape[:2])
    yy, xx = np.mgrid[:256, :256]
    forbidden = ((xx+1 >= box[0]*256) & (xx <= box[2]*256)
                 & (yy+1 >= box[1]*256) & (yy <= box[3]*256))
    assert not np.any(field[forbidden]) and not np.any(field[:80]) and not np.any(field[:, :50])
    assert not np.any(field[170:180, 130:140]) and not np.any(field[145:155, 120:130])
    assert np.any(field != 0)


@pytest.mark.parametrize('derived', [False, True])
def test_full_resolution_rebuild_keeps_producer_observation_and_rerasterizes_manual_vectors(derived):
    pytest.importorskip('cv2')
    value = fixture(size=320, producer_size=160)
    snap = frozen(value, derived=derived)
    with patch.object(N, 'prepare', side_effect=native_match_prepare_double(calls := [])):
        prepared = export(value, derived=derived)
    effect = record(prepared, value)
    assert_source_crops(calls[0], effect, value.original.astype(np.float32)/65535.)
    assert len(calls) == 1 and calls[0]['radius'] == 11
    assert max(calls[0]['source'].shape[:2]) > 160
    assert all(call['source_shape'] == (320, 320) for call in ManualWorkerDouble.calls)
    retained = snap['analyses'][value.ref['face_instance_id']]
    assert retained['body_skin'].shape == (160, 160) and not retained['body_skin'].flags.writeable
    assert retained['body_skin_observation']['producer_width'] == 160
    assert retained['face_skin'].shape == (160, 160) and not retained['face_skin'].flags.writeable
    assert retained['face_skin_observation']['producer_width'] == 160
    assert retained['evidence']['source_width'] == 320


def test_original_and_derived_preview_use_actual_immutable_rgb_and_frozen_body_owner():
    pytest.importorskip('torch')
    from lumaretouch_engine.vram import PreviewPipeline
    value = fixture()
    proxy = (value.original//257).astype(np.uint8)
    source = proxy.astype(np.float32)/255.
    pipe = PreviewPipeline('cpu', 256, 256)
    pipe.load_rgb_u8(proxy)
    proof = REPLAY.make_evidence(value.binding, source, None, REPAIRS.digest_ops([], [], value.binding))
    pipe._creative_repair_source = deepcopy(value.binding)
    pipe._creative_repair_input = deepcopy(proof['input'])
    pipe._creative_repair_evidence = proof
    kwargs = dict(byte_budget=BUDGET, document_id=DOCUMENT, body_bank=value.bank,
                  body_source=value.binding, body_face_match_assets=value.assets)
    with patch.object(N, 'prepare', side_effect=native_match_prepare_double(calls := [])):
        original = ENGINE.prepare_preview(pipe, value.state, value.binding['sha256'],
            {value.ref['face_instance_id']: value.analysis}, **kwargs)
        derived = ENGINE.prepare_preview(pipe, value.state, value.binding['sha256'],
            {value.ref['face_instance_id']: value.analysis}, **kwargs,
            creative_source=value.binding, creative_proxy=proxy)
    a, b = record(original, value), record(derived, value)
    assert len(calls) == 2 and a.window == b.window
    np.testing.assert_array_equal(a.chroma_shift, b.chroma_shift)
    assert_source_crops(calls[0], a, source)
    assert_source_crops(calls[1], b, source)
    np.testing.assert_array_equal(pipe.src_f32[0].permute(1, 2, 0).numpy(), source)
    assert REPLAY.verify_pipeline(pipe, value.binding) == proof


def test_repaired_derived_source_rebuilds_both_actual_rois_only_after_replay_evidence():
    value = fixture()
    source = value.original.astype(np.float32)/65535.
    repaired = source*np.float32(.97)
    proof = REPLAY.make_evidence(value.binding, source, repaired, REPAIRS.digest_ops([], [], value.binding))
    with patch.object(N, 'prepare', side_effect=native_match_prepare_double(calls := [])):
        before = export(value, derived=True)
        after = export(value, derived=True, repaired=repaired, proof=proof)
    a, b = record(before, value), record(after, value)
    assert len(calls) == 2 and a.window == b.window
    assert not np.array_equal(a.chroma_shift, b.chroma_shift)
    assert_source_crops(calls[0], a, source)
    assert_source_crops(calls[1], b, repaired)
    np.testing.assert_allclose(calls[1]['source'], calls[0]['source']*.97, rtol=0, atol=1e-7)
    np.testing.assert_allclose(calls[1]['face_source'], calls[0]['face_source']*.97, rtol=0, atol=1e-7)
    invalid = deepcopy(proof)
    invalid['input']['sha256'] = '9'*64
    with patch.object(N, 'prepare', side_effect=AssertionError('Invalid replay reached native')) as solve:
        with pytest.raises(ValueError):
            export(value, derived=True, repaired=repaired, proof=invalid)
    solve.assert_not_called()


@pytest.mark.parametrize('strength', [0., .4])
def test_real_legacy_light_and_smoothing_pipeline_preserves_current_stage_y(strength):
    pytest.importorskip('torch')
    from lumaretouch_engine.vram import PreviewPipeline, LightOp
    value = fixture()
    source = value.original.astype(np.float32)/65535.
    solves, applications = [], []
    with patch.object(N, 'prepare', side_effect=native_match_prepare_double(solves)), \
            patch.object(CHROMA, 'apply', side_effect=native_apply_double(applications)):
        prepared = export(value)
        effect = record(prepared, value)
        pipes = []
        for _ in range(2):
            pipe = PreviewPipeline('cpu', 256, 256)
            pipe.load_rgb_f32(source.copy())
            pipe.set_light_params(.35, 4)
            pipe.set_light_ops([LightOp(1, np.full((256, 256), 180, np.uint8), sign=-1)])
            pipes.append(pipe)
        settings = {'radius': 6, 'texture_radius': 2, 'broad_gain': .55, 'mid_gain': .7, 'detail_gain': .85}
        baseline = pipes[0].retouch(strength, **settings)[0].permute(1, 2, 0).numpy()
        assert np.any(np.abs(luminance(baseline)-luminance(source)) > 1e-4)
        cpu, facts = prepared.apply_source_stage('body_face_match', baseline)
        PIPE.install(pipes[1], prepared)
        actual = pipes[1].retouch(strength, **settings)[0].permute(1, 2, 0).numpy()
        np.testing.assert_allclose(actual, cpu, rtol=0, atol=3e-6)
        np.testing.assert_allclose(luminance(actual), luminance(baseline), rtol=0, atol=3e-6)
        assert facts['changed_pixels'] > 0 and np.any(actual != baseline)
        source_result, _ = prepared.apply_source_stage('body_face_match', source)
        frozen_rgb_delta = baseline+(source_result-source)
        active = np.any(expanded(effect, source.shape[:2]) != 0, axis=2)
        assert np.max(np.abs(luminance(frozen_rgb_delta)[active]-luminance(baseline)[active])) > 2e-7
    assert len(solves) == 1 and len(applications) == 2
    for pipe in pipes:
        np.testing.assert_array_equal(pipe.src_f32[0].permute(1, 2, 0).numpy(), source)


def test_tensor_full_source_and_two_dimensional_tiles_share_one_body_field():
    torch = pytest.importorskip('torch')
    value = fixture(size=512)
    upstream = value.original.astype(np.float32)/65535.*np.float32(.86)
    solves, applies = [], []
    with patch.object(N, 'prepare', side_effect=native_match_prepare_double(solves)), \
            patch.object(CHROMA, 'apply', side_effect=native_apply_double(applies)):
        prepared = export(value)
        record(prepared, value)
        pixels = torch.from_numpy(upstream.copy()).permute(2, 0, 1)[None]
        full = SimpleNamespace(h=512, w=512, device='cpu', high_precision_warp=False)
        PIPE.install(full, prepared)
        expected = PIPE.source_effect(full, 'body_face_match', pixels)
        actual = torch.empty_like(expected)
        for y0, y1 in ((0, 173), (173, 512)):
            for x0, x1 in ((0, 217), (217, 512)):
                tile = SimpleNamespace(h=y1-y0, w=x1-x0, device='cpu', high_precision_warp=False)
                PIPE.install(tile, prepared, origin=(y0, x0))
                actual[:, :, y0:y1, x0:x1] = PIPE.source_effect(tile, 'body_face_match', pixels[:, :, y0:y1, x0:x1])
                assert tile.people_prepared is prepared
        assert torch.equal(actual, expected)
        cpu, _ = prepared.apply_source_stage('body_face_match', upstream)
        np.testing.assert_allclose(expected[0].permute(1, 2, 0).numpy(), cpu, rtol=0, atol=3e-7)
    assert len(solves) == len(applies) == 1


def test_zero_native_shift_keeps_cpu_tensor_identity_and_signed_zero_bits():
    torch = pytest.importorskip('torch')
    value = fixture()
    with patch.object(N, 'prepare', side_effect=native_match_prepare_double(calls := [], zero=True)), \
            patch.object(CHROMA, 'apply', side_effect=AssertionError('Zero shift applied')) as apply:
        prepared = export(value)
        source = value.original.astype(np.float32)/65535.
        source[0, 0, 0] = -0.
        result, facts = prepared.apply_source_stage('body_face_match', source)
        assert result is source and facts['changed_pixels'] == 0
        np.testing.assert_array_equal(result.view(np.uint32), source.view(np.uint32))
        pipe = SimpleNamespace(h=256, w=256, device='cpu', high_precision_warp=False)
        PIPE.install(pipe, prepared)
        pixels = torch.from_numpy(source.copy()).permute(2, 0, 1)[None]
        assert PIPE.source_effect(pipe, 'body_face_match', pixels) is pixels
    assert len(calls) == 1
    apply.assert_not_called()


def test_history_undo_redo_reset_inherit_and_project_roundtrip_preserve_independent_review():
    from lumaretouch_engine import project as PROJECT_FILE
    value = fixture(recipe=S.neutral())
    value.state = set_recipe(value.state, value.ref, {'version': 1, 'amount': .2}, 'lnx.skin_evenness.v1')
    owner = PeopleGraphOwner(value.state)
    before = {'_people_history': owner.capture_document(value.binding['sha256'])}
    candidate = stage(value, command(value, ACTIVE))['state']
    owner.commit(candidate, expected_fence=0)
    after = {'_people_history': owner.capture_document(value.binding['sha256'])}
    transition = HISTORY.decorate(before, after)[HISTORY.KEY]
    assert {tuple(row['key'][-2:]) for row in transition['changes']} == {(S.OP, '/amount')}
    value.state = HISTORY.restore(owner, transition, value.binding['sha256'])
    assert resolved(value)[S.OP] == S.neutral()
    owner.commit(value.state, expected_fence=1)
    reverse = HISTORY.decorate(after, {'_people_history': owner.capture_document(value.binding['sha256'])})[HISTORY.KEY]
    value.state = HISTORY.restore(owner, reverse, value.binding['sha256'])
    assert resolved(value)[S.OP] == ACTIVE
    assert REVIEW.resolve(value.state, value.assets, value.ref, value.bank, value.analysis, **FAMILY)
    value.state = stage(value, command(value, S.neutral()))['state']
    assert resolved(value)['lnx.skin_evenness.v1'] == {'version': 1, 'amount': .2}
    value.state = P.set_override(value.state, 'all_people', value.binding['sha256'], S.OP, '/amount', .25)
    value.state = stage(value, command(value, S.neutral(), unset=True))['state']
    assert resolved(value)[S.OP] == {'version': 1, 'amount': .25}
    payload = {'people_graph': value.state, 'people_support_assets': value.assets,
               'undo': [{'_people_state': deepcopy(candidate)}], '_params': {'broad_gain': .55}}
    assets, dropped = {}, []
    encoded = PROJECT_FILE.encode(payload, assets, dropped, 'recipe')
    saved = json.loads(json.dumps({'recipe': encoded, 'assets': assets}, allow_nan=False))
    restored = PROJECT_FILE.decode(saved['recipe'], saved['assets'], dropped, 'recipe', {})
    PROJECT.validate_records(restored)
    REVIEW.validate_project(restored, **FAMILY)
    assert restored == payload and dropped == []
    assert all(set(row) == {'scope', 'target_id', 'operation_id', 'parameter_path', 'value'}
               and row['parameter_path'] == '/amount' for row in value.state['overrides'] if row['operation_id'] == S.OP)


def test_reset_recovers_exact_neutral_without_discarding_review_or_requesting_source_analysis():
    value = fixture()
    original_assets = deepcopy(value.assets)
    original_descriptors = deepcopy(value.state['faces'][value.ref['face_instance_id']]['local_assets'])
    value.state = stage(value, command(value, S.neutral()))['state']
    snap = SNAP.capture(value.state, value.binding['sha256'], {})
    snap.update(document_id=DOCUMENT, support_assets=deepcopy(value.assets))
    with patch.object(N, 'available', side_effect=AssertionError('Reset queried native')), \
            patch.object(N, 'prepare', side_effect=AssertionError('Reset solved a reference')), \
            patch.object(CHROMA, 'apply', side_effect=AssertionError('Reset applied chroma')):
        prepared = ENGINE.prepare_export(snap, value.original, None, byte_budget=BUDGET, document_id=DOCUMENT)
    assert resolved(value)[S.OP] == S.neutral() and not prepared.effects
    assert value.assets == original_assets
    assert value.state['faces'][value.ref['face_instance_id']]['local_assets'] == original_descriptors
    assert not prepared.plan['entries'][0]['requires_analysis']
    np.testing.assert_array_equal(prepared.geometry.warp_original(value.original), value.original)
    assert ManualWorkerDouble.calls == []


@pytest.mark.parametrize('location', ['active', 'undo', 'redo', 'nested'])
@pytest.mark.parametrize('with_face', [False, True])
@pytest.mark.parametrize('path,leaf', [('/amount', False), ('/amount', '0'), ('/amount', -.1),
                                     ('/amount', 1.1), ('/reference_rgb', .4), ('/coverage', .3)])
def test_every_saved_depth_and_empty_photo_rejects_invalid_body_intent(location, with_face, path, leaf):
    value = fixture(recipe=None)
    state = value.state if with_face else P.empty()
    state = P.set_override(state, 'all_people', value.binding['sha256'], S.OP, path, leaf)
    payload = ({'people_graph': state} if location == 'active' else
               {location: [{'_people_state': state}]} if location in ('undo', 'redo') else
               {'children': [{'undo': [{'saved': {'_people_state': state}}]}]})
    before = deepcopy(payload)
    with pytest.raises(ValueError):
        PROJECT.validate_records(payload)
    assert payload == before


def test_private_support_bank_cannot_borrow_parent_bytes_or_another_family_descriptor():
    value = fixture()
    payload = {'people_support_assets': value.assets,
               'people_context': {'people_graph': value.state, 'people_support_assets': {}}}
    with pytest.raises(ValueError):
        REVIEW.validate_project(payload, **FAMILY)
    value.state, value.assets = REVIEW.retain(value.state, value.assets, value.ref, value.bank,
                                             value.analysis, value.review, family='skin_colour')
    corrupted = deepcopy(value.state)
    local = corrupted['faces'][value.ref['face_instance_id']]['local_assets']
    local[REVIEW.FACE_MATCH_KIND]['content_sha256'] = local[REVIEW.KIND]['content_sha256']
    with pytest.raises(ValueError):
        REVIEW.validate_project({'people_graph': corrupted, 'people_support_assets': value.assets}, **FAMILY)


def test_shared_person_transfers_only_amount_then_rebuilds_each_independently_reviewed_body():
    values = [fixture(recipe=None, retained=False, asset='a'*64),
              fixture(recipe=None, retained=False, asset='8'*64, size=320, tone=.025)]
    state = P.empty()
    for value in values:
        state['faces'].update(deepcopy(value.state['faces']))
    state, person = LINKS.create_person(state)
    for value in values:
        state = LINKS.set_link(state, value.ref['face_instance_id'], person, 'confirmed', user_confirmed=True)
    assets = {}
    for value in values:
        value.bank = BODY.associate(value.bank, value.review['body_ref'], person, state, user_confirmed=True)
        state, assets = REVIEW.retain(state, assets, value.ref, value.bank, value.analysis, value.review, **FAMILY)
    values[0].state = state
    request = command(values[0], ACTIVE)
    request['target'] = {'scope': 'person', 'target_id': person, 'face_ref': None}
    candidate = stage(values[0], request)['state']
    assert affected_assets(state, candidate) == {'a'*64, '8'*64}
    rows = [row for row in candidate['overrides'] if row['operation_id'] == S.OP]
    assert len(rows) == 1 and rows[0]['scope'] == 'person' and rows[0]['parameter_path'] == '/amount'
    solves, fields = [], []
    for value in values:
        value.state, value.assets = candidate, assets
        with patch.object(N, 'prepare', side_effect=native_match_prepare_double(solves)):
            fields.append(record(export(value), value))
        assert_source_crops(solves[-1], fields[-1], value.original.astype(np.float32)/65535.)
        assert resolved(value)[S.OP] == ACTIVE
    assert len(solves) == 2 and solves[0]['source'].shape != solves[1]['source'].shape
    assert solves[0]['face_source'].shape != solves[1]['face_source'].shape
    assert not np.shares_memory(fields[0].chroma_shift, fields[1].chroma_shift)
    assert fields[0].face_ref != fields[1].face_ref
    # Scalar transport does not authorize an unreviewed target body.
    target = values[1]
    target.state = REVIEW.detach(target.state, target.ref, **FAMILY)
    with patch.object(N, 'prepare', side_effect=AssertionError('Unreviewed target borrowed source review')) as solve:
        with pytest.raises(ValueError):
            export(target)
    solve.assert_not_called()


def test_reviewed_derived_replicas_retain_local_body_reviews_not_donor_reference_fields():
    values = [fixture(recipe=None, retained=False, linked=False, asset='a'*64),
              fixture(recipe=None, retained=False, linked=False, asset='8'*64, tone=.025)]
    documents = ('synthetic-body-derived-a', 'synthetic-body-derived-b')
    members = [{'document_id': document, 'scope_id': document, 'original_sha256': str(index+1)*64,
                'ref': deepcopy(value.ref)} for index, (document, value) in enumerate(zip(documents, values))]
    intent = [{'op': S.OP, 'path': '/amount', 'value': ACTIVE['amount']}]
    fields, capsules = [], []
    for document, value in zip(documents, values):
        capsule = CROSS.descriptor('synthetic-reviewed-body-face-match', document, members, intent)
        value.state = CROSS.create(value.state, 'reviewed-body-person', capsule)
        value.bank = BODY.associate(value.bank, value.review['body_ref'], 'reviewed-body-person',
                                    value.state, user_confirmed=True)
        value.state, value.assets = REVIEW.retain(value.state, {}, value.ref, value.bank,
                                                 value.analysis, value.review, **FAMILY)
        DERIVED.require_graph(value.state, value.binding, document_id=document)
        with patch.object(N, 'prepare', side_effect=native_match_prepare_double([])):
            fields.append(record(export(value, derived=True, document=document), value))
        capsules.append(capsule)
        assert capsule['intent'] == intent and len(value.assets) == 1
        only = next(iter(value.assets.values()))
        assert only['source']['sha256'] == value.binding['sha256']
        assert only['row']['review']['body_ref'] == value.review['body_ref']
        assert only['row']['face_skin_observation'] == value.analysis['face_skin_observation']
        assert not {'reference_rgb', 'coverage', 'chroma_shift', 'donor_ref'} & set(only['row'])
    assert capsules[0]['generation'] == capsules[1]['generation']
    assert not np.array_equal(fields[0].chroma_shift, fields[1].chroma_shift)
    assert not np.shares_memory(fields[0].chroma_shift, fields[1].chroma_shift)


def file_backed_engine(tmp_path):
    """Real host/snapshot/decoder/export owner, with synthetic model observations.

    This fixture does not call an inference backend or create an installed
    production session. It installs named synthetic observations into their
    actual typed owners and renders a genuine temporary PNG through the full
    candidate path. No method on Engine or its source/receipt guards is replaced.
    """
    pytest.importorskip('torch')
    cv2 = pytest.importorskip('cv2')
    from lumaretouch_engine.server import Engine
    from lumaretouch_engine.face import FacePrecompute
    from lumaretouch_engine.vram import PreviewPipeline
    from lumaretouch_engine import local_mask_state as SOURCE
    from lumaretouch_engine import people_retained_analysis as RETAINED
    from lumaretouch_engine import cpu_memory_budget as MEMORY
    # A resource refusal is not replaced with invented budget evidence. This
    # optional full-host fixture requires the real supported Linux budget view.
    try:
        available = MEMORY.available_estimate()
    except ValueError as error:
        pytest.skip('Full real-host fixture needs readable cgroup memory evidence: '+str(error))
    if available < 2*1024**3:
        pytest.skip('Full real-host fixture needs at least 2 GiB admitted memory')
    original = fixture(recipe=None, retained=False).original
    pixels = (original//257).astype(np.uint8)
    path = tmp_path/'synthetic-body-face-match-rgb16.png'
    assert cv2.imwrite(str(path), original[..., ::-1])
    header = path.read_bytes()[:33]
    assert header[:8] == b'\x89PNG\r\n\x1a\n' and header[24:26] == bytes((16, 2))
    value = fixture(recipe=S.neutral(), retained=False, asset=hashlib.sha256(path.read_bytes()).hexdigest())
    engine = Engine(str(tmp_path/'synthetic-body-session'))
    engine._src_rgb = pixels.copy()
    engine._doc_path = str(path)
    engine._image_loaded = True
    engine._load_id = DOCUMENT
    engine._strength = 0.
    engine._params.update(radius=6, texture_radius=2, broad_gain=.55, mid_gain=.7, detail_gain=.85)
    engine._vram = PreviewPipeline('cpu', 256, 256)
    engine._vram.load_rgb_u8(pixels)
    masks = {key: value.analysis[key].copy() for key in ('skin', 'face_skin', 'body_skin')}
    masks.update({key: np.zeros((256, 256), np.float32) for key in ('hair', 'clothes', 'background')})
    points = value.analysis['landmarks'].copy()
    engine._precompute = FacePrecompute(points, masks, 'mediapipe', 0., 0.,
        face_box=tuple(value.state['faces'][value.ref['face_instance_id']]['box']),
        all_landmarks=[points], semantic_model_sha256='c'*64, detector_model_sha256='b'*64)
    engine._precompute_backend = 'mediapipe'
    engine._face_box = engine._precompute.face_box
    engine._face_explicit = True
    target = {'scope': 'face', 'target_id': value.ref['face_instance_id'], 'face_ref': deepcopy(value.ref)}
    owner = PeopleGraphOwner(value.state)
    engine._people_graph_owner = owner
    engine._people_support = {}
    engine._people_targets = {value.binding['sha256']: target}
    engine._people_cursors = {value.binding['sha256']: value.ref['face_instance_id']}
    _, analyses, refusals = BIND.bind(value.state, value.binding['sha256'], engine._precompute,
                                     source_dimensions=(256, 256))
    assert refusals == []
    value.analysis = analyses[value.ref['face_instance_id']]
    engine._people_analyses = {value.binding['sha256']: analyses}
    engine._people_landmarks = RETAINED.retain({}, analyses)
    engine._hair_colour_assets = engine._hair_colour_evidence = {}
    engine._body_pose_bank = BODY_PROJECT.pack(value.bank)
    row = {'path': str(path), 'src_w': 256, 'src_h': 256, 'document_id': DOCUMENT,
           'document_revision': 7, '_local_source_stamp': SOURCE.file_stamp(str(path))}
    engine._docs, engine._doc_index = [row], 0
    assert engine._people_owner() is owner
    engine._people_analysis_key = (value.binding['sha256'], id(engine._precompute), owner.fence)
    row['state'] = engine._capture_state()
    assert engine._people_source() == value.binding
    return engine, value, target, row


def test_real_first_use_full_candidate_review_is_private_until_fenced_confirmation(tmp_path):
    """Real candidate rendering and confirm guard, not UI/frame-history acceptance."""
    from lumaretouch_engine import skin_colour_body_host as HOST_REVIEW
    from lumaretouch_engine import optics_candidate_identity as IDENTITY
    engine, value, target, row = file_backed_engine(tmp_path)
    owner = engine._people_owner()
    before = owner.snapshot()
    before_history = {'_people_history': owner.capture_document(value.binding['sha256'])}
    state_digest = IDENTITY.fingerprint(engine._capture_state())
    version = engine._document_versions().version(row)
    source_bytes = Path(row['path']).read_bytes()
    solves, applies = [], []
    with patch.object(N, 'prepare', side_effect=native_match_prepare_double(solves)), \
            patch.object(CHROMA, 'apply', side_effect=native_apply_double(applies)):
        reference = HOST_REVIEW.reference(engine, before, target, {}, **FAMILY)
        assert reference['attached'] is False and reference['bodies'][0]['body_ref'] == value.review['body_ref']
        assert reference['reference_support']['face_ref'] == value.ref
        assert reference['reference_overlay']['mapping'] == 'normalized_full_frame'
        shown = HOST_REVIEW.preview(engine, before, target,
                                    {'review': value.review, 'amount': ACTIVE['amount']}, **FAMILY)
        assert shown['amount'] == ACTIVE['amount'] and shown['runtime_quality_accepted'] is False
        assert shown['before']['base64'] != shown['after']['base64']
        assert shown['overlay']['mapping'] == 'normalized_full_frame'
        assert shown['family'] == FAMILY['family'] and shown['operation_id'] == S.OP
        assert shown['own_face_reference'] == reference['own_face_reference']
        pending = engine._body_face_match_preview
        assert pending['after_proof']['source_size'] == pending['after_proof']['output_size'] == [256, 256]
        assert pending['after_proof']['source_proof']['asset_sha256'] == value.binding['sha256']
        assert owner.snapshot() == before and owner.fence == 0 and engine._people_support == {}
        assert engine._document_versions().version(row) == version
        assert IDENTITY.fingerprint(engine._capture_state()) == state_digest
        # Incorrect receipt IDs are rejected by the real private-preview guard.
        with pytest.raises(ValueError):
            HOST_REVIEW.confirm(engine, before, target, {'preview_id': 'wrong-preview', 'reviewed': True}, **FAMILY)
        assert owner.snapshot() == before and engine._people_support == {}
        marks = []
        candidate, reply = HOST_REVIEW.confirm(engine, before, target,
            {'preview_id': shown['preview_id'], 'reviewed': True}, **FAMILY,
            mark_started=lambda: marks.append((owner.fence, deepcopy(engine._people_support))))
        assert marks == [(0, {})] and reply == {'kind': 'confirmed', 'attached': True, **FAMILY}
        assert owner.snapshot() == before  # Confirmation returns a candidate, not a second graph owner.
        assert A.recipes(RESOLVE.resolve(candidate, value.ref['face_instance_id'], A.defaults()))[S.OP] == ACTIVE
        assert REVIEW.resolve(candidate, engine._people_support, value.ref, value.bank, value.analysis, **FAMILY)
        prepared = ENGINE.prepare_preview(engine._vram, candidate, value.binding['sha256'],
            {value.ref['face_instance_id']: value.analysis}, byte_budget=BUDGET, document_id=DOCUMENT,
            body_bank=value.bank, body_source=value.binding, body_face_match_assets=engine._people_support)
        effect = record(prepared, value)
        assert_source_crops(solves[0], effect, value.original.astype(np.float32)/65535.)
        # The full comparison was decoded from genuine RGB16, not the RGB8
        # analysis/display proxy used by the separate live preview call.
        assert not np.array_equal(solves[0]['source'], solves[-1]['source'])
        assert not np.array_equal(solves[0]['face_source'], solves[-1]['face_source'])
        # Exercise the actual graph owner after successful complete preparation;
        # this is not a claim of the separate SHM frame-publication transaction.
        owner.commit(candidate, expected_fence=0)
        assert owner.fence == 1 and owner.snapshot() == candidate
        after_history = {'_people_history': owner.capture_document(value.binding['sha256'])}
        transition = HISTORY.decorate(before_history, after_history)[HISTORY.KEY]
        assert {change['collection'] for change in transition['changes']} == {'faces', 'overrides'}
        undo = HISTORY.restore(owner, transition, value.binding['sha256'])
        assert A.recipes(RESOLVE.resolve(undo, value.ref['face_instance_id'], A.defaults()))[S.OP] == S.neutral()
        assert REVIEW.FACE_MATCH_KIND not in undo['faces'][value.ref['face_instance_id']]['local_assets']
        with pytest.raises(ValueError):
            HOST_REVIEW.confirm(engine, candidate, target,
                {'preview_id': shown['preview_id'], 'reviewed': True}, **FAMILY)
    assert len(solves) >= 2 and engine._body_face_match_preview is None
    assert engine._body_face_match_reference is None
    assert Path(row['path']).read_bytes() == source_bytes


def test_real_full_candidate_native_failure_keeps_first_use_private_and_recoverable(tmp_path):
    from lumaretouch_engine import skin_colour_body_host as HOST_REVIEW
    from lumaretouch_engine import optics_candidate_identity as IDENTITY
    engine, value, target, row = file_backed_engine(tmp_path)
    owner = engine._people_owner()
    before = owner.snapshot()
    digest = IDENTITY.fingerprint(engine._capture_state())
    version = engine._document_versions().version(row)
    original = Path(row['path']).read_bytes()
    HOST_REVIEW.reference(engine, before, target, {}, **FAMILY)
    with patch.object(N, 'prepare', side_effect=RuntimeError('Synthetic native preparation refusal')) as solve:
        with pytest.raises((ValueError, RuntimeError), match='Synthetic native preparation refusal'):
            HOST_REVIEW.preview(engine, before, target, {'review': value.review, 'amount': ACTIVE['amount']}, **FAMILY)
    assert solve.called and owner.snapshot() == before and owner.fence == 0
    assert engine._people_support == {} and engine._body_face_match_preview is None
    assert engine._document_versions().version(row) == version
    assert IDENTITY.fingerprint(engine._capture_state()) == digest
    assert Path(row['path']).read_bytes() == original
    # Recovery is a new real comparison; no rollback rewinds owner fences and
    # no stale, partially rendered result can be confirmed as a success.
    with patch.object(N, 'prepare', side_effect=native_match_prepare_double([])), \
            patch.object(CHROMA, 'apply', side_effect=native_apply_double([])):
        shown = HOST_REVIEW.preview(engine, before, target, {'review': value.review, 'amount': ACTIVE['amount']}, **FAMILY)
    assert shown['before']['base64'] != shown['after']['base64']
    assert owner.snapshot() == before and engine._people_support == {}


@pytest.mark.parametrize('changed_stage', ['source', 'repair'])
def test_real_first_use_confirmation_refuses_changed_effective_reference_pixels(tmp_path, changed_stage):
    from lumaretouch_engine import skin_colour_body_host as HOST_REVIEW
    engine, value, target, row = file_backed_engine(tmp_path)
    owner = engine._people_owner()
    before = owner.snapshot()
    version = engine._document_versions().version(row)
    original = Path(row['path']).read_bytes()
    with patch.object(N, 'prepare', side_effect=native_match_prepare_double([])), \
            patch.object(CHROMA, 'apply', side_effect=native_apply_double([])):
        HOST_REVIEW.reference(engine, before, target, {}, **FAMILY)
        shown = HOST_REVIEW.preview(engine, before, target,
            {'review': value.review, 'amount': ACTIVE['amount']}, **FAMILY)
    # Change only the real retained tensor. File/graph/association/recipe IDs
    # stay equal, so the source-stage pixel fence itself must reject the receipt.
    if changed_stage == 'source':
        engine._vram.src_f32 = engine._vram.src_f32 * .97
    else:
        engine._vram.repair_base = engine._vram.src_f32 * .97
    with patch.object(N, 'prepare', side_effect=AssertionError('Stale review prepared')) as solve:
        with pytest.raises(ValueError):
            HOST_REVIEW.confirm(engine, before, target,
                {'preview_id': shown['preview_id'], 'reviewed': True}, **FAMILY)
    solve.assert_not_called()
    assert owner.snapshot() == before and owner.fence == 0 and engine._people_support == {}
    assert engine._document_versions().version(row) == version
    assert Path(row['path']).read_bytes() == original


def test_source_stage_order_and_unchanged_legacy_guided_python_operator():
    tree = ast.parse((ROOT/'engine/src/lumaretouch_engine/vram.py').read_text())
    positions = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == 'PEOPLE_PIPE'
                and node.func.attr == 'source_effect' and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)):
            positions.setdefault(node.args[1].value, []).append(node.lineno)
    order = ('body_face_match', 'body_skin_evenness', 'skin_evenness', 'skin_colour')
    for name in order:
        assert len(positions[name]) == 1
    assert [positions[name][0] for name in order] == sorted(positions[name][0] for name in order)
    assert [EFFECTS.STAGES.index(name) for name in order] == sorted(EFFECTS.STAGES.index(name) for name in order)
    assert hashlib.sha256((ROOT/'engine/src/lumaretouch_engine/ops/guided.py').read_bytes()).hexdigest() == \
        '9abade12a57958d7f73aacdc89da50734fbe81af4f15173af8fec44ac2c9b111'
    assert hashlib.sha256((ROOT/'engine/src/lumaretouch_engine/people_geometry.py').read_bytes()).hexdigest() == \
        '554e4ea056f8c675be3b1fb859a2ca3101ca437dc1db52967e4151524955580b'
    # Deliberately no hash of the entire Rust core: its extracted shared solve
    # is covered by separately authored native legacy numerical parity tests.


def test_doubles_are_only_named_native_process_and_chroma_boundaries():
    tree = ast.parse(Path(__file__).read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
             and node.func.value.id == 'patch']
    assert calls
    for call in calls:
        assert call.func.attr == 'object' and isinstance(call.args[0], ast.Name)
        assert isinstance(call.args[1], ast.Constant)
        assert ((call.args[0].id == 'N' and call.args[1].value in ('available', 'prepare'))
                or (call.args[0].id == 'CHROMA' and call.args[1].value in ('available', 'prepare', 'apply'))
                or (call.args[0].id == 'M' and call.args[1].value == '_Worker'))
