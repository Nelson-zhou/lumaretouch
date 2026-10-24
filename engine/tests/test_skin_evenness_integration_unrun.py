# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: partial same-face source-reference chromatic evenness.

LNX-REF-PC-32465-C-60b7c0e3d1 is only partially covered. Synthetic images,
landmarks and model identities below are transport/routing fixtures, not real
inference, photographic acceptance, learned AI, blemish classification, body
support or cross-person colour matching. No local product import, execution,
test collection/run, typecheck, build, inference or download ran in authoring.

Only skin_evenness_native.available/prepare/apply are doubled. Positive owner,
semantic/anatomical support, graph transactions, snapshots, source admission,
preview/export adapters and the real tensor composition remain undoubled.
The prepare double supplies a bounded source-dependent HWC2 routing mark, NOT
the native reference/neighbourhood algorithm. The apply double expresses the
documented pointwise current-linear-Y contract independently in NumPy. Neither
double is native-kernel or GPU acceptance evidence.
"""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from test_skin_evenness_support_unrun import synthetic_observation

from lumaretouch_engine import skin_evenness_state as S, skin_evenness_native as N
from lumaretouch_engine import skin_evenness_layer as LAYER
from lumaretouch_engine import skin_colour_state as COLOUR, skin_finish_state as FINISH
from lumaretouch_engine import people_algorithms as A, people_state as P
from lumaretouch_engine import people_resolver as RESOLVE, people_associations as LINKS
from lumaretouch_engine import people_cross_owner as CROSS, people_project as PROJECT
from lumaretouch_engine import people_snapshot as SNAP, people_export as EXPORT
from lumaretouch_engine import people_engine_runtime as ENGINE, people_render_runtime as RENDER
from lumaretouch_engine import people_pipeline as PIPE, people_effects as EFFECTS
from lumaretouch_engine import people_edit as EDIT, people_document_history as HISTORY
from lumaretouch_engine import people_host_commands as HOST
from lumaretouch_engine.people_graph_owner import PeopleGraphOwner, affected_assets
from lumaretouch_engine.people_host import PeopleHostMixin
from lumaretouch_engine.people_geometry import CombinedGeometry, FaceGeometry
from lumaretouch_engine import creative_derived_effects as DERIVED
from lumaretouch_engine import creative_derived_repairs as REPAIRS
from lumaretouch_engine import creative_derived_repair_runtime as REPLAY

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = 'synthetic-skin-evenness-document'
BUDGET = 512 * 1024**2
ACTIVE = {'version': 1, 'amount': .65}
REQUIREMENT = 'LNX-REF-PC-32465-C-60b7c0e3d1'
LUMA = np.array([.2126, .7152, .0722], np.float64)


@pytest.fixture(autouse=True)
def named_native_availability_double():
    """Capability seam only; no claim that a shared library was loaded."""
    with patch.object(N, 'available', return_value=True):
        yield


def set_recipe(state, ref, recipe, operation=None):
    for path, value in A.leaves(recipe).items():
        state = P.set_override(state, 'face', ref['face_instance_id'], operation or S.OP, path, value)
    return state


def fixture(*, recipe=ACTIVE, asset='a'*64, size=256, tone=0.):
    """Independent canonical source and real durable owner for every fixture."""
    _, analysis, source = synthetic_observation(size=size, producer_size=size, source_size=size)
    analysis = deepcopy(analysis)
    source = np.array(source, dtype=np.float32, copy=True)
    source += np.float32(tone)
    assert source.shape == (size, size, 3)
    assert np.isfinite(source).all() and np.all((source >= 0) & (source <= 1))
    face = P.new_face(asset, [.03, .03, .97, .97], analysis['evidence'])
    state = P.empty()
    state['faces'][face['face_instance_id']] = face
    ref = P.face_ref(face)
    analysis['face_ref'] = deepcopy(ref)
    analysis['face_skin_observation']['source_sha256'] = asset
    if recipe is not None:
        state = set_recipe(state, ref, recipe)
    original = np.rint(source.astype(np.float64)*65535.).astype(np.uint16)
    return state, ref, analysis, {'sha256': asset, 'width': size, 'height': size}, original


def resolved(state, ref):
    return A.recipes(RESOLVE.resolve(state, ref['face_instance_id'], A.defaults()))


def command(state, ref, recipe, *, unset=False):
    return {'document_id': DOCUMENT, 'document_epoch': 'synthetic-epoch', 'document_revision': 7,
            'state_revision': state['revision'], 'association_revision': state['association_revision'],
            'request_id': 'synthetic-skin-evenness-request', 'action': 'patch',
            'target': {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': deepcopy(ref)},
            'payload': {'patches': [{'operation_id': S.OP, 'parameter_path': path, 'unset': unset,
                **({} if unset else {'value': value})} for path, value in A.leaves(recipe).items()]}}


def stage(value, state, ref, *, prepare=None):
    evidence = state['faces'][ref['face_instance_id']]['evidence']
    return EDIT.stage(value, state, document_id=DOCUMENT, document_epoch='synthetic-epoch',
        document_revision=7, asset_sha256=ref['asset_sha256'],
        source_dimensions=(evidence['source_width'], evidence['source_height']), prepare=prepare)


def snapshot(state, ref, analysis, binding, *, derived=False):
    value = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    value.update(document_id=DOCUMENT, support_assets={})
    if derived:
        value['creative_source'] = deepcopy(binding)
    return value


def export(value, source, repaired=None, **kwargs):
    return ENGINE.prepare_export(value, source, repaired, byte_budget=BUDGET,
                                 document_id=DOCUMENT, **kwargs)


def linear(rgb):
    value = np.asarray(rgb, np.float64)
    return np.where(value <= .04045, value/12.92, ((value+.055)/1.055)**2.4)


def luminance(rgb):
    return linear(rgb) @ LUMA


def native_prepare_double(calls, *, zero=False):
    """A visible bounded routing mark, not the guided chroma estimator."""
    def prepare(source_rgb, coverage, amount, *, radius, cancelled=None):
        assert source_rgb.dtype == coverage.dtype == np.float32
        assert source_rgb.shape == (*coverage.shape, 3)
        assert not source_rgb.flags.writeable and not coverage.flags.writeable
        assert np.any(coverage > 0) and np.all((coverage >= 0) & (coverage <= 1))
        assert type(radius) is int and 4 <= radius <= 256
        assert type(amount) in (int, float) and 0 < amount <= 1
        if cancelled is not None and cancelled():
            raise InterruptedError('synthetic native preparation cancellation')
        calls.append({'source': source_rgb.copy(), 'coverage': coverage.copy(),
                      'amount': amount, 'radius': radius})
        means = np.mean(source_rgb[coverage > 0], axis=0, dtype=np.float64)
        marker = np.array([.035+.012*means[0], -.020-.008*means[2]], np.float32)
        shift = coverage[..., None]*np.float32(amount)*marker
        if zero:
            shift.fill(0)
        shift.setflags(write=False)
        return shift
    return prepare


def native_apply_double(calls):
    """Documented pointwise algebra, NOT native-implementation acceptance."""
    def apply(current_rgb, shift, *, cancelled=None):
        assert current_rgb.dtype == shift.dtype == np.float32
        assert current_rgb.shape == (*shift.shape[:2], 3) and shift.shape[2] == 2
        assert np.isfinite(current_rgb).all() and np.all((current_rgb >= 0) & (current_rgb <= 1))
        assert np.isfinite(shift).all()
        assert np.all(np.linalg.norm(shift.astype(np.float64), axis=2) <= .0900001)
        if cancelled is not None and cancelled():
            raise InterruptedError('synthetic native application cancellation')
        calls.append({'current': current_rgb.copy(), 'shift': shift.copy()})
        result = current_rgb.copy()
        active = np.any(shift != 0, axis=2)
        active &= ~np.all(current_rgb == 0, axis=2) & ~np.all(current_rgb == 1, axis=2)
        rgb = linear(current_rgb[active])
        move = shift[active].astype(np.float64)
        proposal = rgb * np.column_stack((np.exp(move[:, 0]), np.ones(len(move)), np.exp(move[:, 1])))
        proposal *= ((rgb @ LUMA)/(proposal @ LUMA))[:, None]
        delta = proposal-rgb
        permitted = np.ones_like(delta)
        np.divide(1-rgb, delta, out=permitted, where=delta > 0)
        np.divide(-rgb, delta, out=permitted, where=delta < 0)
        gain = np.minimum(1., np.min(permitted, axis=1))
        gain = np.where(gain < 1, gain*(1-1e-12), gain)
        assert np.all(gain >= 0)
        target = rgb+gain[:, None]*delta
        assert np.isfinite(target).all() and np.all((target >= 0) & (target <= 1))
        encoded = np.where(target <= .0031308, 12.92*target, 1.055*target**(1/2.4)-.055)
        changed = gain > 0
        values = current_rgb[active].copy()
        values[changed] = encoded[changed].astype(np.float32)
        result[active] = values
        return result
    return apply


def assert_prepared(prepared, ref, shape):
    assert type(prepared.geometry) is CombinedGeometry
    assert prepared.geometry.delta.shape == (1, *shape, 2)
    assert prepared.geometry.face_ids == (ref['face_instance_id'],)
    assert not prepared.geometry.delta.flags.writeable and not np.any(prepared.geometry.delta)
    assert len(prepared.face_fields) == 1
    face = prepared.face_fields[0]
    assert type(face) is FaceGeometry and face.fields == (None,)*4 and not face.automatic.units
    assert prepared.plan['sample_policy'] == 'one_original_source_sample_after_composed_field'
    assert len(prepared.effects) == 1
    record = prepared.effects[0]
    assert record.stage == 'skin_evenness' and record.face_ref == ref
    assert record.delta is None and record.weights is None and record.amounts is None
    assert record.chroma_shift.shape == (*record.window[2:], 2)
    assert record.chroma_shift.dtype == np.float32 and not record.chroma_shift.flags.writeable
    assert np.isfinite(record.chroma_shift).all() and np.any(record.chroma_shift != 0)
    assert record.facts['body_extension'] == {'enabled': False}
    return record


def expanded(record, shape):
    value = np.zeros((*shape, 2), np.float32)
    y, x, h, w = record.window
    value[y:y+h, x:x+w] = record.chroma_shift
    return value


def test_operation_is_separate_scalar_intent_not_broad_gain_colour_or_finish():
    assert S.OP == 'lnx.skin_evenness.v1' and S.OP in DERIVED.OPERATIONS
    assert S.VERSION == 1 and S.CONTROL_ID == REQUIREMENT
    assert S.OP not in A.GEOMETRY and S.OP not in (COLOUR.OP, FINISH.OP)
    assert A.defaults()[S.OP] == {'/amount': 0.}
    assert A.defaults()[COLOUR.OP] == {'/temperature': 0., '/tint': 0.}
    assert A.defaults()[FINISH.OP] == {'/whitening': 0., '/rosiness': 0.}
    state, ref, _, _, _ = fixture(recipe=None)
    DERIVED._patches(command(state, ref, ACTIVE)['payload'])
    registry = json.loads((ROOT/'docs/p0/registry-extensions.json').read_text())
    row = next(item for item in registry['entries'] if item['operation_id'] == S.OP)
    assert row['neutral'] == S.neutral()
    assert row['source_requirement'] == 'PC-32465-C-60b7c0e3d1'


@pytest.mark.parametrize('path,value', [('/amount', False), ('/amount', True), ('/amount', '0'),
    ('/amount', -.01), ('/amount', 1.01), ('/amount', float('nan')), ('/amount', float('inf')),
    ('/version', 1), ('/reference_rgb', []), ('/face_ref', {}), ('/coverage', []),
    ('/chroma_shift', []), ('/source_sha256', 'a'*64), ('/body', .5), ('/blemishes', .5)])
def test_derived_transport_refuses_coercion_and_donor_source_or_unimplemented_intent(path, value):
    with pytest.raises(ValueError):
        DERIVED._leaf(S.OP, path, value)


def test_history_undo_redo_reset_and_inherit_keep_independent_colour_intent():
    state, ref, _, _, _ = fixture(recipe=S.neutral())
    colour = {**COLOUR.neutral(), 'temperature': .2, 'tint': -.1}
    state = set_recipe(state, ref, colour, COLOUR.OP)
    before, owner = deepcopy(state), PeopleGraphOwner(state)
    asset = ref['asset_sha256']
    previous = {'_people_history': owner.capture_document(asset)}
    candidate = stage(command(state, ref, ACTIVE), state, ref)['state']
    owner.commit(candidate, expected_fence=0)
    following = {'_people_history': owner.capture_document(asset)}
    transition = HISTORY.decorate(previous, following)[HISTORY.KEY]
    assert {tuple(row['key'][-2:]) for row in transition['changes']} == {(S.OP, '/amount')}
    undone = HISTORY.restore(owner, transition, asset)
    assert resolved(undone, ref)[S.OP] == S.neutral()
    owner.commit(undone, expected_fence=1)
    reverse = HISTORY.decorate(following, {'_people_history': owner.capture_document(asset)})[HISTORY.KEY]
    redone = HISTORY.restore(owner, reverse, asset)
    assert resolved(redone, ref)[S.OP] == ACTIVE
    owner.commit(redone, expected_fence=2)
    reset = stage(command(owner.snapshot(), ref, S.neutral()), owner.snapshot(), ref)['state']
    assert resolved(reset, ref)[S.OP] == S.neutral() and resolved(reset, ref)[COLOUR.OP] == colour
    inherited = P.set_override(reset, 'all_people', asset, S.OP, '/amount', .25)
    inherited = stage(command(inherited, ref, S.neutral(), unset=True), inherited, ref)['state']
    assert resolved(inherited, ref)[S.OP] == {'version': 1, 'amount': .25}
    assert state == before and owner.fence == 3


def project_tree(state, location):
    if location == 'active':
        return {'people_graph': state}
    if location in ('undo', 'redo'):
        return {location: [{'_people_state': state}]}
    return {'document': {'children': [{'undo': [{'saved': {'_people_state': state}}]}]}}


@pytest.mark.parametrize('location', ['active', 'undo', 'redo', 'nested'])
@pytest.mark.parametrize('with_face', [False, True])
@pytest.mark.parametrize('path,value', [('/amount', False), ('/amount', True), ('/amount', '0'),
    ('/amount', -.01), ('/amount', 1.01), ('/chroma_shift', .5), ('/reference', .5)])
def test_project_gate_validates_every_saved_depth_and_empty_photo_intent(location, with_face, path, value):
    state, ref, _, _, _ = fixture(recipe=None)
    if not with_face:
        state = P.empty()
    state = P.set_override(state, 'all_people', ref['asset_sha256'], S.OP, path, value)
    payload = project_tree(state, location)
    before = deepcopy(payload)
    with pytest.raises(ValueError):
        PROJECT.validate_records(payload)
    assert payload == before


def test_project_round_trip_keeps_only_amount_and_snapshot_owns_actual_observations():
    from lumaretouch_engine import project as PROJECT_FILE
    state, ref, analysis, binding, _ = fixture()
    payload = {'people_graph': state, 'undo': [{'_people_state': set_recipe(state, ref, S.neutral())}],
               '_strength': .4, '_params': {'broad_gain': .55, 'radius': 6}}
    assets, dropped = {}, []
    encoded = PROJECT_FILE.encode(payload, assets, dropped, 'recipe')
    serialized = json.loads(json.dumps({'recipe': encoded, 'assets': assets}, sort_keys=True, allow_nan=False))
    restored = PROJECT_FILE.decode(serialized['recipe'], serialized['assets'], dropped, 'recipe', {})
    PROJECT.validate_records(restored)
    assert not dropped and restored == payload
    assert restored['_strength'] == .4 and restored['_params']['broad_gain'] == .55
    assert resolved(restored['people_graph'], ref)[S.OP] == ACTIVE
    assert state['faces'][ref['face_instance_id']]['local_assets'] == {}
    rows = [row for row in state['overrides'] if row['operation_id'] == S.OP]
    assert len(rows) == 1 and rows[0]['parameter_path'] == '/amount' and type(rows[0]['value']) is float
    frozen = snapshot(state, ref, analysis, binding)
    assert frozen['support_assets'] == {} and EXPORT.fastpath_blocker(frozen)
    retained = frozen['analyses'][ref['face_instance_id']]
    for key in ('landmarks', 'excluded', 'skin', 'face_skin'):
        if analysis.get(key) is not None:
            assert not retained[key].flags.writeable and not np.shares_memory(retained[key], analysis[key])
    assert retained['face_skin_observation'] == analysis['face_skin_observation']
    assert retained['face_skin_observation'] is not analysis['face_skin_observation']


def test_conflicting_shared_intent_is_project_recoverable_but_never_partially_rendered():
    state, ref, analysis, binding, original = fixture(recipe=None)
    for group, value in (('synthetic-evenness-a', .2), ('synthetic-evenness-b', .4)):
        state = LINKS.set_group(state, group, label=group, priority=1, face_ids=[ref['face_instance_id']])
        state = P.set_override(state, 'group', group, S.OP, '/amount', value)
    resolution = RESOLVE.resolve(state, ref['face_instance_id'], A.defaults())
    assert any(row['operation_id'] == S.OP for row in resolution['conflicts'])
    payload = {'people_graph': state, 'undo': [{'_people_state': deepcopy(state)}]}
    before = deepcopy(payload)
    PROJECT.validate_records(payload)
    with patch.object(N, 'prepare', side_effect=AssertionError('conflicting graph solved')) as solve:
        with pytest.raises(ValueError):
            export(snapshot(state, ref, analysis, binding), original)
    solve.assert_not_called()
    assert payload == before


def test_original_export_source_verifier_checks_actual_file_digest_and_document(tmp_path):
    # This isolates the real file-byte verifier, not an image decoder/encoder.
    original = fixture()[-1]
    source_file = tmp_path/'synthetic-rgb16-source.bin'
    source_file.write_bytes(original.tobytes())
    digest = hashlib.sha256(source_file.read_bytes()).hexdigest()
    state, ref, analysis, binding, _ = fixture(asset=digest)
    frozen = snapshot(state, ref, analysis, binding)
    envelope = {'people': frozen, 'people_document_id': DOCUMENT}
    EXPORT.verify_source(envelope, str(source_file))
    with pytest.raises(ValueError):
        EXPORT.verify_source({**envelope, 'people_document_id': 'wrong-document'}, str(source_file))
    source_file.write_bytes(original.tobytes()+b'changed-source')
    with pytest.raises(ValueError):
        EXPORT.verify_source(envelope, str(source_file))


@pytest.mark.parametrize('empty_photo', [False, True])
def test_exact_zero_needs_no_analysis_or_native_and_preserves_rgb16(empty_photo):
    state, ref, _, binding, original = fixture(recipe=S.neutral())
    if empty_photo:
        state = P.set_override(P.empty(), 'all_people', binding['sha256'], S.OP, '/amount', 0.)
    frozen = SNAP.capture(state, binding['sha256'], {})
    frozen.update(document_id=DOCUMENT, support_assets={})
    with patch.object(N, 'available', side_effect=AssertionError('neutral probed native')) as ready, \
            patch.object(N, 'prepare', side_effect=AssertionError('neutral solved source')) as solve, \
            patch.object(N, 'apply', side_effect=AssertionError('neutral applied source')) as apply:
        prepared = export(frozen, original)
        assert LAYER.prepare(None, None, None, S.neutral(), byte_budget=0) == []
        working = original.astype(np.float32)/65535.
        actual, facts = prepared.apply_source_stage('skin_evenness', working)
        assert actual is working and facts['changed_pixels'] == 0
    for call in (ready, solve, apply):
        call.assert_not_called()
    assert prepared.effects == () and prepared.face_fields == ()
    assert not any(entry['requires_analysis'] for entry in prepared.plan['entries'])
    assert not EXPORT.fastpath_blocker(frozen)
    np.testing.assert_array_equal(prepared.geometry.warp_original(original), original)


@pytest.mark.parametrize('with_face', [False, True])
@pytest.mark.parametrize('path,value', [('/amount', False), ('/amount', True), ('/amount', '0'),
                                     ('/amount', .1), ('/reference', .5)])
def test_invalid_or_nonzero_missing_analysis_intent_cannot_hide_in_fastpath(with_face, path, value):
    state, ref, _, binding, original = fixture(recipe=None)
    if not with_face:
        state = P.empty()
    state = P.set_override(state, 'all_people', binding['sha256'], S.OP, path, value)
    frozen = SNAP.capture(state, binding['sha256'], {})
    frozen.update(document_id=DOCUMENT, support_assets={})
    assert EXPORT.fastpath_blocker(frozen)
    with patch.object(N, 'prepare', side_effect=AssertionError('invalid source solved')) as solve:
        with pytest.raises(ValueError):
            export(frozen, original)
    solve.assert_not_called()


@pytest.mark.parametrize('amount', [.2, .65, 1.])
def test_rgb16_and_derived_float_export_rebuild_same_typed_field_from_owned_source(amount):
    state, ref, analysis, binding, original = fixture(recipe={'version': 1, 'amount': amount})
    before, saved = deepcopy(state), original.copy()
    working = original.astype(np.float32)/65535.
    frozen = snapshot(state, ref, analysis, binding)
    solves, applications = [], []
    with patch.object(N, 'prepare', side_effect=native_prepare_double(solves)), \
            patch.object(N, 'apply', side_effect=native_apply_double(applications)):
        old = export(frozen, original)
        new = export({**frozen, 'creative_source': binding}, working)
        first = assert_prepared(old, ref, working.shape[:2])
        second = assert_prepared(new, ref, working.shape[:2])
        assert len(solves) == 2 and applications == []
        assert first.window == second.window and not np.shares_memory(first.chroma_shift, second.chroma_shift)
        np.testing.assert_array_equal(first.chroma_shift, second.chroma_shift)
        np.testing.assert_array_equal(solves[0]['source'], solves[1]['source'])
        y, x, h, w = first.window
        np.testing.assert_array_equal(solves[0]['source'], working[y:y+h, x:x+w])
        old_output, _ = old.apply_source_stage('skin_evenness', working)
        new_output, _ = new.apply_source_stage('skin_evenness', working)
    np.testing.assert_array_equal(old_output, new_output)
    np.testing.assert_allclose(luminance(old_output), luminance(working), rtol=0, atol=2e-7)
    assert np.any(old_output != working) and len(solves) == len(applications) == 2
    assert state == before and frozen['state'] == before
    np.testing.assert_array_equal(original, saved)
    expected = (sum(field.resident_bytes() for field in (*old.face_fields, *old.body_fields))
                + old.geometry.delta.nbytes + old.geometry.owner.nbytes + first.chroma_shift.nbytes)
    assert RENDER.retained_bytes(old) == expected


@pytest.mark.parametrize('fault', ['missing', 'landmark_digest', 'foreign_face', 'revision',
    'face_skin', 'observation', 'excluded', 'occluded', 'black_source'])
def test_invalid_source_owned_support_refuses_before_native_without_partial_face(fault):
    state, ref, analysis, binding, original = fixture()
    before = deepcopy(state)
    if fault == 'landmark_digest': analysis['landmarks'][0, 0] += np.float32(.001)
    elif fault == 'foreign_face': analysis['face_ref']['asset_sha256'] = 'f'*64
    elif fault == 'revision': analysis['face_ref']['analysis_revision'] += 1
    elif fault == 'face_skin': analysis['face_skin'] = analysis['face_skin_observation'] = None
    elif fault == 'observation': analysis['face_skin_observation']['source_sha256'] = 'f'*64
    elif fault == 'excluded': analysis['excluded'] = None
    elif fault == 'occluded': analysis['excluded'][:] = 1
    elif fault == 'black_source': original[:] = 0
    saved = original.copy()
    with patch.object(N, 'prepare', side_effect=AssertionError('unadmitted source solved')) as solve:
        with pytest.raises(ValueError):
            frozen = SNAP.capture(state, ref['asset_sha256'], {} if fault == 'missing' else {ref['face_instance_id']: analysis})
            frozen.update(document_id=DOCUMENT, support_assets={})
            export(frozen, original)
    solve.assert_not_called()
    assert state == before
    np.testing.assert_array_equal(original, saved)


@pytest.mark.parametrize('derived', [False, True])
@pytest.mark.parametrize('fault', ['document', 'dtype', 'alpha', 'budget'])
def test_export_document_source_shape_dtype_and_budget_fences_precede_native(derived, fault):
    state, ref, analysis, binding, original = fixture()
    frozen = snapshot(state, ref, analysis, binding, derived=derived)
    source = original.astype(np.float32)/65535. if derived else original
    budget = BUDGET
    if fault == 'document': frozen['document_id'] = 'different-owner'
    elif fault == 'dtype': source = original if derived else original.astype(np.float32)/65535.
    elif fault == 'alpha': source = np.concatenate((source, np.ones_like(source[..., :1])), axis=2)
    else: budget = 1
    with patch.object(N, 'prepare', side_effect=AssertionError('invalid export solved')) as solve:
        with pytest.raises(ValueError):
            ENGINE.prepare_export(frozen, source, None, byte_budget=budget, document_id=DOCUMENT)
    solve.assert_not_called()


def test_original_and_derived_preview_rebuild_from_their_actual_immutable_rgb():
    pytest.importorskip('torch')
    from lumaretouch_engine.vram import PreviewPipeline
    state, ref, analysis, binding, original = fixture()
    proxy = (original//257).astype(np.uint8)
    working = proxy.astype(np.float32)/255.
    pipe = PreviewPipeline('cpu', binding['width'], binding['height'])
    pipe.load_rgb_u8(proxy)
    proof = REPLAY.make_evidence(binding, working, None, REPAIRS.digest_ops([], [], binding))
    pipe._creative_repair_source = deepcopy(binding)
    pipe._creative_repair_input = deepcopy(proof['input'])
    pipe._creative_repair_evidence = proof
    solves = []
    with patch.object(N, 'prepare', side_effect=native_prepare_double(solves)):
        old = ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                                     byte_budget=BUDGET, document_id=DOCUMENT)
        new = ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                                     byte_budget=BUDGET, document_id=DOCUMENT,
                                     creative_source=binding, creative_proxy=proxy)
    first, second = assert_prepared(old, ref, working.shape[:2]), assert_prepared(new, ref, working.shape[:2])
    assert len(solves) == 2 and first.window == second.window
    np.testing.assert_array_equal(first.chroma_shift, second.chroma_shift)
    np.testing.assert_array_equal(pipe.src_f32[0].permute(1, 2, 0).numpy(), working)
    assert REPLAY.verify_pipeline(pipe, binding) == proof


@pytest.mark.parametrize('fault', ['missing', 'input', 'source'])
def test_derived_repaired_source_requires_actual_replay_proof_before_preparation(fault):
    state, ref, analysis, binding, original = fixture()
    source = original.astype(np.float32)/65535.
    repaired = source*np.float32(.97)
    frozen = snapshot(state, ref, analysis, binding, derived=True)
    proof = REPLAY.make_evidence(binding, source, repaired, REPAIRS.digest_ops([], [], binding))
    if fault == 'missing': proof = None
    elif fault == 'input': proof['input']['sha256'] = 'e'*64
    else: proof['source']['sha256'] = 'e'*64
    with patch.object(N, 'prepare', side_effect=AssertionError('unverified repair solved')) as solve:
        with pytest.raises(ValueError):
            export(frozen, source, repaired, creative_repair_evidence=proof)
    solve.assert_not_called()


def test_valid_derived_repair_rebuilds_reference_from_repaired_source_not_old_field():
    state, ref, analysis, binding, original = fixture()
    source = original.astype(np.float32)/65535.
    repaired = source*np.float32(.97)
    frozen = snapshot(state, ref, analysis, binding, derived=True)
    proof = REPLAY.make_evidence(binding, source, repaired, REPAIRS.digest_ops([], [], binding))
    solves = []
    with patch.object(N, 'prepare', side_effect=native_prepare_double(solves)):
        old = export(frozen, source)
        new = export(frozen, source, repaired, creative_repair_evidence=proof)
    first, second = assert_prepared(old, ref, source.shape[:2]), assert_prepared(new, ref, source.shape[:2])
    assert len(solves) == 2 and first.window == second.window
    assert not np.array_equal(first.chroma_shift, second.chroma_shift)
    np.testing.assert_allclose(solves[1]['source'], solves[0]['source']*.97, rtol=0, atol=1e-7)
    assert REPLAY.verify_evidence(proof, binding, source, repaired) == proof


@pytest.mark.parametrize('derived', [False, True])
def test_full_resolution_rebuild_uses_retained_producer_observation_not_enlarged_shift(derived):
    pytest.importorskip('cv2')
    state, ref, analysis, binding, original = fixture(size=320)
    for key in ('excluded', 'skin', 'face_skin'):
        if analysis.get(key) is not None:
            analysis[key] = np.array(analysis[key][::2, ::2], np.float32, copy=True)
    analysis['face_skin_observation'].update(producer_width=160, producer_height=160)
    frozen = snapshot(state, ref, analysis, binding, derived=derived)
    source = original.astype(np.float32)/65535. if derived else original
    solves = []
    with patch.object(N, 'prepare', side_effect=native_prepare_double(solves)):
        full = export(frozen, source)
    record = assert_prepared(full, ref, (320, 320))
    assert len(solves) == 1 and max(solves[0]['source'].shape[:2]) > 160
    assert not np.shares_memory(record.chroma_shift, source)
    assert record.facts['render_dimensions'] == [320, 320]
    retained = frozen['analyses'][ref['face_instance_id']]
    assert retained['face_skin'].shape == (160, 160)
    assert retained['face_skin_observation']['producer_width'] == 160
    assert retained['evidence']['source_width'] == 320


@pytest.mark.parametrize('strength', [0., .4])
def test_canonical_pipeline_preserves_actual_linear_y_after_real_light_and_legacy_smoothing(strength):
    """Real PreviewPipeline, guided bands and LightOp, no positive render mock."""
    pytest.importorskip('torch')
    from lumaretouch_engine.vram import PreviewPipeline, LightOp
    state, ref, analysis, binding, original = fixture()
    source = original.astype(np.float32)/65535.
    solves, applications = [], []
    with patch.object(N, 'prepare', side_effect=native_prepare_double(solves)), \
            patch.object(N, 'apply', side_effect=native_apply_double(applications)):
        prepared = export(snapshot(state, ref, analysis, binding), original)
        record = assert_prepared(prepared, ref, source.shape[:2])
        pipes = []
        for _ in range(2):
            pipe = PreviewPipeline('cpu', binding['width'], binding['height'])
            pipe.load_rgb_f32(source.copy())
            weight = np.full(source.shape[:2], 180, np.uint8)
            pipe.set_light_params(.35, 4)
            pipe.set_light_ops([LightOp(1, weight, sign=-1)])
            pipes.append(pipe)
        settings = {'radius': 6, 'texture_radius': 2, 'broad_gain': .55,
                    'mid_gain': .7, 'detail_gain': .85}
        baseline_t = pipes[0].retouch(strength, **settings)
        baseline = baseline_t[0].permute(1, 2, 0).numpy()
        assert np.any(np.abs(luminance(baseline)-luminance(source)) > 1e-4)
        cpu, facts = prepared.apply_source_stage('skin_evenness', baseline)
        assert facts['changed_pixels'] > 0 and facts['overlap_pixels'] == 0
        np.testing.assert_allclose(luminance(cpu), luminance(baseline), rtol=0, atol=2e-7)
        PIPE.install(pipes[1], prepared)
        actual = pipes[1].retouch(strength, **settings)[0].permute(1, 2, 0).numpy()
        np.testing.assert_allclose(actual, cpu, rtol=0, atol=3e-6)
        np.testing.assert_allclose(luminance(actual), luminance(baseline), rtol=0, atol=3e-6)
        assert np.any(actual != baseline) and np.all((actual >= 0) & (actual <= 1))
        # A frozen source RGB delta is specifically not equivalent here.
        source_result, _ = prepared.apply_source_stage('skin_evenness', source)
        fake_rgb_delta = baseline + (source_result-source)
        active = np.any(expanded(record, source.shape[:2]) != 0, axis=2)
        assert np.max(np.abs(luminance(fake_rgb_delta)[active]-luminance(baseline)[active])) > 2e-7
    assert len(solves) == 1 and len(applications) == 2
    for pipe in pipes:
        np.testing.assert_array_equal(pipe.src_f32[0].permute(1, 2, 0).numpy(), source)


def test_tensor_full_source_and_two_dimensional_tiles_share_one_prepared_field():
    torch = pytest.importorskip('torch')
    # 512**2 exceeds the production 131072-pixel pointwise scratch strip.
    state, ref, analysis, binding, original = fixture(size=512)
    source = original.astype(np.float32)/65535.
    solves, applications = [], []
    with patch.object(N, 'prepare', side_effect=native_prepare_double(solves)), \
            patch.object(N, 'apply', side_effect=native_apply_double(applications)):
        prepared = export(snapshot(state, ref, analysis, binding), original)
        assert_prepared(prepared, ref, source.shape[:2])
        height, width = source.shape[:2]
        upstream = source*np.float32(.86)
        pixels = torch.from_numpy(upstream.copy()).permute(2, 0, 1)[None]
        full = SimpleNamespace(h=height, w=width, device='cpu', high_precision_warp=False)
        PIPE.install(full, prepared)
        expected = PIPE.source_effect(full, 'skin_evenness', pixels)
        actual = torch.empty_like(expected)
        for y0, y1 in ((0, 93), (93, height)):
            for x0, x1 in ((0, 117), (117, width)):
                tile = SimpleNamespace(h=y1-y0, w=x1-x0, device='cpu', high_precision_warp=False)
                PIPE.install(tile, prepared, origin=(y0, x0))
                actual[:, :, y0:y1, x0:x1] = PIPE.source_effect(tile, 'skin_evenness', pixels[:, :, y0:y1, x0:x1])
                assert tile.people_prepared is prepared
        assert torch.equal(actual, expected)
        cpu, _ = prepared.apply_source_stage('skin_evenness', upstream)
        np.testing.assert_allclose(expected[0].permute(1, 2, 0).numpy(), cpu, rtol=0, atol=3e-7)
    assert len(solves) == len(applications) == 1  # Tensor/tile path never re-solves or calls CPU apply.


def test_current_gamut_boundaries_and_endpoints_preserve_y_without_channel_clipping():
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding, original = fixture()
    solves, applications = [], []
    with patch.object(N, 'prepare', side_effect=native_prepare_double(solves)), \
            patch.object(N, 'apply', side_effect=native_apply_double(applications)):
        prepared = export(snapshot(state, ref, analysis, binding), original)
        record = assert_prepared(prepared, ref, original.shape[:2])
        palette = np.array([[.999, .35, .08], [1., .4, .2], [0., .4, .8],
                            [-0., 0., 0.], [1., 1., 1.], [.004, .9, .999]], np.float32)
        yy, xx = np.mgrid[:original.shape[0], :original.shape[1]]
        current = palette[(xx+yy) % len(palette)].copy()
        before = current.copy()
        cpu, _ = prepared.apply_source_stage('skin_evenness', current)
        pipe = SimpleNamespace(h=current.shape[0], w=current.shape[1], device='cpu', high_precision_warp=False)
        PIPE.install(pipe, prepared)
        actual = PIPE.source_effect(pipe, 'skin_evenness', torch.from_numpy(current).permute(2, 0, 1)[None])
        np.testing.assert_allclose(actual[0].permute(1, 2, 0).numpy(), cpu, rtol=0, atol=3e-7)
    np.testing.assert_allclose(luminance(cpu), luminance(current), rtol=0, atol=2e-7)
    assert np.isfinite(cpu).all() and np.all((cpu >= 0) & (cpu <= 1))
    assert np.any(cpu != current) and len(solves) == len(applications) == 1
    protected = (~np.any(expanded(record, current.shape[:2]) != 0, axis=2)
                 | np.all(current == 0, axis=2) | np.all(current == 1, axis=2))
    np.testing.assert_array_equal(cpu[protected].view(np.uint32), current[protected].view(np.uint32))
    np.testing.assert_array_equal(current.view(np.uint32), before.view(np.uint32))


@pytest.mark.parametrize('fault', ['current64', 'field64', 'current16', 'field16', 'alpha',
                                  'rgb_field', 'short_field', 'batch', 'device'])
def test_tensor_application_rejects_noncanonical_dtype_shape_batch_and_device(fault):
    torch = pytest.importorskip('torch')
    from lumaretouch_engine import skin_evenness_composition as COMPOSE
    pixels = torch.full((1, 3, 2, 3), .4, dtype=torch.float32)
    field = torch.full((1, 2, 2, 3), .01, dtype=torch.float32)
    if fault == 'current64': pixels = pixels.double()
    elif fault == 'field64': field = field.double()
    elif fault == 'current16': pixels = pixels.half()
    elif fault == 'field16': field = field.half()
    elif fault == 'alpha': pixels = torch.full((1, 4, 2, 3), .4, dtype=torch.float32)
    elif fault == 'rgb_field': field = torch.full((1, 3, 2, 3), .01, dtype=torch.float32)
    elif fault == 'short_field': field = field[:, :, :1]
    elif fault == 'batch': pixels, field = pixels.repeat(2, 1, 1, 1), field.repeat(2, 1, 1, 1)
    else: field = torch.empty(field.shape, device='meta', dtype=torch.float32)
    with pytest.raises(ValueError):
        COMPOSE.apply_t(pixels, field)


def test_zero_prepared_shift_keeps_tensor_and_cpu_objects_and_signed_zero_bits():
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding, original = fixture()
    solves = []
    with patch.object(N, 'prepare', side_effect=native_prepare_double(solves, zero=True)), \
            patch.object(N, 'apply', side_effect=AssertionError('zero field called native apply')) as apply:
        prepared = export(snapshot(state, ref, analysis, binding), original)
        source = original.astype(np.float32)/65535.
        source[0, 0, 0] = -0.
        result, facts = prepared.apply_source_stage('skin_evenness', source)
        assert result is source and facts['changed_pixels'] == 0
        np.testing.assert_array_equal(result.view(np.uint32), source.view(np.uint32))
        pipe = SimpleNamespace(h=source.shape[0], w=source.shape[1], device='cpu', high_precision_warp=False)
        PIPE.install(pipe, prepared)
        pixels = torch.from_numpy(source.copy()).permute(2, 0, 1)[None]
        assert PIPE.source_effect(pipe, 'skin_evenness', pixels) is pixels
    apply.assert_not_called()
    assert len(solves) == 1


@pytest.mark.parametrize('bad', [-.01, 1.01, float('nan'), float('inf')])
def test_active_current_stage_invalid_pixels_refuse_instead_of_being_clipped(bad):
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding, original = fixture()
    with patch.object(N, 'prepare', side_effect=native_prepare_double([])):
        prepared = export(snapshot(state, ref, analysis, binding), original)
    record = assert_prepared(prepared, ref, original.shape[:2])
    source = original.astype(np.float32)/65535.
    y, x, _, _ = record.window
    dy, dx = np.argwhere(np.any(record.chroma_shift != 0, axis=2))[0]
    source[y+dy, x+dx, 0] = bad
    with patch.object(N, 'apply', side_effect=AssertionError('invalid active RGB reached native')) as apply:
        with pytest.raises(ValueError):
            prepared.apply_source_stage('skin_evenness', source)
    apply.assert_not_called()
    pipe = SimpleNamespace(h=source.shape[0], w=source.shape[1], device='cpu', high_precision_warp=False)
    PIPE.install(pipe, prepared)
    with pytest.raises(ValueError):
        PIPE.source_effect(pipe, 'skin_evenness', torch.from_numpy(source).permute(2, 0, 1)[None])


def test_disabled_unresolved_same_source_neighbours_are_protected_without_borrowed_analysis():
    state, ref, analysis, binding, original = fixture()
    box = [.42, .42, .58, .60]
    evidence = {'backend': 'manual_region', 'detector_model_sha256': None, 'semantic_model_sha256': None,
        'landmark_digest': None, 'status': 'unresolved', 'source_width': binding['width'],
        'source_height': binding['height'], 'orientation': 'exif_normalized_once'}
    for asset, enabled in ((binding['sha256'], False), (binding['sha256'], True), ('e'*64, True)):
        foreign = P.new_face(asset, box, evidence, manual=True)
        foreign['enabled'] = enabled
        state['faces'][foreign['face_instance_id']] = foreign
    solves = []
    with patch.object(N, 'prepare', side_effect=native_prepare_double(solves)):
        prepared = export(snapshot(state, ref, analysis, binding), original)
    record = assert_prepared(prepared, ref, original.shape[:2])
    assert len(solves) == 1 and record.facts['protected_face_boxes'] == 2
    field = expanded(record, original.shape[:2])
    h, w = original.shape[:2]
    yy, xx = np.mgrid[:h, :w]
    footprint = (xx+1 >= box[0]*w) & (xx <= box[2]*w) & (yy+1 >= box[1]*h) & (yy <= box[3]*h)
    assert not np.any(field[footprint]) and np.any(field != 0)


def test_original_shared_person_transfers_only_amount_and_rebuilds_each_target_source():
    targets = [fixture(recipe=None, asset='a'*64), fixture(recipe=None, asset='f'*64, size=320, tone=.025)]
    state = P.empty()
    for own, _, _, _, _ in targets:
        state['faces'].update(deepcopy(own['faces']))
    state, person = LINKS.create_person(state)
    for _, ref, _, _, _ in targets:
        state = LINKS.set_link(state, ref['face_instance_id'], person, 'confirmed', user_confirmed=True)
    edit = command(state, targets[0][1], ACTIVE)
    edit['target'] = {'scope': 'person', 'target_id': person, 'face_ref': None}
    before = deepcopy(state)
    candidate = stage(edit, state, targets[0][1])['state']
    assert affected_assets(state, candidate) == {'a'*64, 'f'*64}
    rows = [row for row in candidate['overrides'] if row['operation_id'] == S.OP]
    assert len(rows) == 1 and rows[0]['scope'] == 'person' and rows[0]['parameter_path'] == '/amount'
    observations, records = [], []
    for _, ref, analysis, binding, original in targets:
        assert resolved(candidate, ref)[S.OP] == ACTIVE
        calls = []
        with patch.object(N, 'prepare', side_effect=native_prepare_double(calls)):
            prepared = export(snapshot(candidate, ref, analysis, binding), original)
        records.append(assert_prepared(prepared, ref, original.shape[:2]))
        observations.append(calls[0])
        assert len(calls) == 1 and candidate['faces'][ref['face_instance_id']]['local_assets'] == {}
    assert observations[0]['source'].shape != observations[1]['source'].shape
    for key in ('source', 'coverage'):
        assert not np.shares_memory(observations[0][key], observations[1][key])
    assert not np.shares_memory(records[0].chroma_shift, records[1].chroma_shift)
    assert state == before


def test_reviewed_derived_replicas_transport_amount_not_reference_chroma_or_support():
    targets = [fixture(recipe=None, asset='a'*64), fixture(recipe=None, asset='f'*64, tone=.025)]
    documents = ('synthetic-derived-evenness-a', 'synthetic-derived-evenness-b')
    members = [{'document_id': document, 'scope_id': document,
                'original_sha256': ('1' if index == 0 else '2')*64, 'ref': deepcopy(target[1])}
               for index, (document, target) in enumerate(zip(documents, targets))]
    intent = [{'op': S.OP, 'path': '/amount', 'value': ACTIVE['amount']}]
    results, capsules = [], []
    for document, (state, ref, analysis, binding, original) in zip(documents, targets):
        capsule = CROSS.descriptor('synthetic-reviewed-evenness', document, members, intent)
        candidate = CROSS.create(state, 'synthetic-person', capsule)
        DERIVED.require_graph(candidate, binding, document_id=document)
        frozen = snapshot(candidate, ref, analysis, binding, derived=True)
        frozen['document_id'] = document
        calls = []
        with patch.object(N, 'prepare', side_effect=native_prepare_double(calls)):
            prepared = ENGINE.prepare_export(frozen, original.astype(np.float32)/65535., None,
                                            byte_budget=BUDGET, document_id=document)
        results.append(assert_prepared(prepared, ref, original.shape[:2]))
        capsules.append(capsule)
        assert len(calls) == 1 and capsule['intent'] == intent and candidate['faces'] == state['faces']
    assert capsules[0]['generation'] == capsules[1]['generation']
    assert not np.array_equal(results[0].chroma_shift, results[1].chroma_shift)
    assert not np.shares_memory(results[0].chroma_shift, results[1].chroma_shift)


@pytest.mark.parametrize('failure', ['preparation', 'publication'])
def test_real_host_refusal_restores_graph_history_and_monotonic_fence(failure):
    """Real host transaction with minimal explicit host IO, never a fake owner."""
    state, ref, analysis, binding, original = fixture(recipe=S.neutral())
    before, owner = deepcopy(state), PeopleGraphOwner(state)
    edit = command(state, ref, ACTIVE)
    prepared, syncs, events = [], [], []
    history = {'undo': [owner.capture_document(ref['asset_sha256'])], 'redo': []}
    history_before = deepcopy(history)
    engine = SimpleNamespace(_guard_editable=lambda name: None, _people_bind=lambda: None,
        _people_binding=lambda: {**binding, 'asset_sha256': ref['asset_sha256'], 'document_id': DOCUMENT,
            'document_epoch': 'synthetic-epoch', 'document_revision': 7},
        _people_owner=lambda: owner, _people_source=lambda: binding,
        _docs=[], _doc_index=-1, _vram=object(), history=history)
    def prepare(candidate, assets):
        assert assets == {ref['asset_sha256']}
        prepared.append(export(snapshot(candidate, ref, analysis, binding), original))
    def sync(*, strict):
        assert strict is True
        syncs.append(owner.snapshot())
        if len(syncs) == 1:
            raise ValueError('synthetic evenness publication refusal')
    engine._people_prepare_graph = prepare
    engine._people_sync = sync
    engine._people_publish_graph = lambda candidate, assets: PeopleHostMixin._people_publish_graph(engine, candidate, assets)
    action = RuntimeError('synthetic evenness native refusal') if failure == 'preparation' else native_prepare_double([])
    with patch.object(N, 'prepare', side_effect=action), pytest.raises(ValueError, match='synthetic'):
        HOST.apply(engine, {'cmd': 'people', **edit}, events.append)
    assert not events and state == before and history == history_before
    assert engine._people_receipts[edit['request_id']]['success'] is False
    current = owner.snapshot()
    assert current['overrides'] == before['overrides'] and current['faces'] == before['faces']
    assert resolved(current, ref)[S.OP] == S.neutral()
    if failure == 'preparation':
        assert not prepared and not syncs and owner.fence == 0
    else:
        assert len(prepared) == 1 and len(syncs) == 2 and owner.fence == 2
        assert resolved(syncs[0], ref)[S.OP] == ACTIVE
        assert resolved(syncs[1], ref)[S.OP] == S.neutral() and engine._people_staged is None


def test_guided_legacy_core_bytes_are_unchanged_not_migrated_to_new_colour_operation():
    # Read-only byte observation from the specified baseline, not execution.
    assert hashlib.sha256((ROOT/'engine/src/lumaretouch_engine/ops/guided.py').read_bytes()).hexdigest() == \
        '9abade12a57958d7f73aacdc89da50734fbe81af4f15173af8fec44ac2c9b111'


def test_source_stage_precedes_skin_colour_and_still_uses_one_common_geometry_sampler():
    text = (ROOT/'engine/src/lumaretouch_engine/vram.py').read_text()
    tree = ast.parse(text)
    positions = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == 'PEOPLE_PIPE'
                and node.func.attr == 'source_effect' and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)):
            positions.setdefault(node.args[1].value, []).append(node.lineno)
    assert len(positions['skin_evenness']) == len(positions['skin_colour']) == 1
    assert positions['skin_evenness'][0] < positions['skin_colour'][0]
    assert EFFECTS.STAGES.index('skin_evenness') < EFFECTS.STAGES.index('skin_colour')
    assert S.OP not in A.GEOMETRY


def test_all_patches_remain_at_named_native_boundary_not_positive_support_or_render():
    tree = ast.parse(Path(__file__).read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
             and node.func.value.id == 'patch']
    assert calls
    for call in calls:
        assert call.func.attr == 'object'
        assert isinstance(call.args[0], ast.Name) and call.args[0].id == 'N'
        assert isinstance(call.args[1], ast.Constant) and call.args[1].value in ('available', 'prepare', 'apply')
