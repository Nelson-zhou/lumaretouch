"""AUTHORED_UNRUN: independently owned measured eye-symmetry integration.

Synthetic meshes, RGB, observations and named prior-field doubles are fixtures,
not detector output, real photographs or acceptance results. Only the EXISTING
eye_shape_native.native loader and controls boundaries are patched. The strict native adapter,
anatomical admission, EyeField/TPS, wrapper, graph owner, snapshot preparation,
repair proof and common sampler remain real. The native double demonstrates
Python routing and inverse-map contracts, NOT a successful native execution.

No product import, collection, test, build, type check, inference or download
ran while authoring. Every case is AUTHORED_UNRUN. Recorded byte hashes are
future source-parity guards, not pixel parity or proof of algorithm quality.
Minimal host IO below does not claim disk-project, dispatcher or UI acceptance.
"""
import ast
from copy import deepcopy
import hashlib
from itertools import product
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from test_eye_symmetry_geometry_unrun import _fixture as measured_eye_fixture

from lumaretouch_engine import eye_symmetry_state as S
from lumaretouch_engine import eye_symmetry_people as PORT
from lumaretouch_engine import eye_symmetry_runtime as CORE
from lumaretouch_engine import eye_shape_native as SHARED
from lumaretouch_engine import eye_shape_state as MANUAL
from lumaretouch_engine import people_algorithms as A, people_state as P
from lumaretouch_engine import people_binding as BIND, people_associations as LINKS
from lumaretouch_engine import people_cross_owner as CROSS
from lumaretouch_engine import people_resolver as RESOLVE, people_project as PROJECT
from lumaretouch_engine import people_snapshot as SNAP, people_export as EXPORT
from lumaretouch_engine import people_render_runtime as RENDER, people_engine_runtime as ENGINE
from lumaretouch_engine import people_edit as EDIT, people_host_commands as HOST
from lumaretouch_engine import people_document_history as HISTORY
from lumaretouch_engine.people_host import PeopleHostMixin
from lumaretouch_engine.people_graph_owner import PeopleGraphOwner, affected_assets
from lumaretouch_engine import creative_derived_effects as DERIVED
from lumaretouch_engine import creative_derived_repairs as REPAIRS
from lumaretouch_engine import creative_derived_repair_runtime as REPLAY
from lumaretouch_engine import skin_colour_support as SKIN
from lumaretouch_engine.people_geometry import AutomaticField, FaceGeometry, CombinedGeometry
from lumaretouch_engine.ops import deform as D

ROOT = Path(__file__).resolve().parents[2]
BUDGET = 512 * 1024**2
DOCUMENT = 'synthetic-eye-symmetry-document'
ACTIVE = {'version': 1, 'horizontal': .35, 'size': .4, 'reference': 'auto'}
RECIPES = tuple({'version': 1, 'horizontal': h, 'size': s, 'reference': ref}
                for h, s in ((.35, 0.), (0., .4), (.35, .4))
                for ref in ('auto', 'left', 'right'))

# sha256sum of current immutable legacy files, observed read-only 2026-10-24.
# No commit provenance or runtime equality is inferred from these byte guards.
PRIOR_SOURCE_SHA256 = {
    'core/eye_shape/lib.rs': '3817392fc8f44974b1fa7215c067e3fe966e813f76a2299bbc66afe142eb0a65',
    'engine/src/lumaretouch_engine/ops/deform.py': '5e0800bffa8f87f9f8e4f6cf8caa1ea782bee20d099a2232c869e0e9d53247fd',
    'engine/src/lumaretouch_engine/brow_shape_field.py': 'c1437ab499c12d0f9ab5f3e308776103f2332d66e06caaf21cc33b1742ff86ae',
    'engine/src/lumaretouch_engine/eye_shape_field.py': '0dec74c9a8f91b5d0dd10c101864964ac4c1701e28d797a37e699f22697c87d7',
}


@pytest.fixture(autouse=True)
def synthetic_native_loader_boundary():
    """Explicit FFI admission double; never claim the real ABI was loaded."""
    with patch.object(SHARED, 'native', return_value=object()):
        yield


def fixture(*, recipe=ACTIVE, asset='a'*64, size=512, larger='left', symmetric=False, tone=0.):
    """Independent synthetic target observations, not rebound donor analyses."""
    left_scale = 1.04 if larger == 'left' and not symmetric else 1.
    right_scale = 1.04 if larger == 'right' and not symmetric else 1.
    landmarks, rgb, excluded = measured_eye_fixture(shape=(size, size),
        left_scale=left_scale, right_scale=right_scale,
        height_difference=0. if symmetric else 2., roll=0.)
    landmarks = np.array(landmarks, dtype=np.float32, copy=True)
    original = np.rint((rgb.astype(np.float64)+tone)*65535.).astype(np.uint16)
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b'*64,
        'semantic_model_sha256': 'c'*64, 'landmark_digest': BIND.landmark_digest(landmarks),
        'status': 'verified', 'source_width': size, 'source_height': size,
        'orientation': 'exif_normalized_once'}
    face = P.new_face(asset, [.1, .05, .9, .95], evidence)
    state = P.empty()
    state['faces'][face['face_instance_id']] = face
    ref = P.face_ref(face)
    analysis = {'face_ref': deepcopy(ref), 'evidence': deepcopy(evidence), 'landmarks': landmarks,
        'excluded': np.array(excluded, dtype=np.float32, copy=True),
        'skin': np.ones((size, size), np.float32), 'face_skin': np.ones((size, size), np.float32),
        'face_skin_observation': {'contract': SKIN.CONTRACT, 'source_sha256': asset,
            'semantic_model_sha256': 'c'*64, 'producer_width': size, 'producer_height': size}}
    if recipe is not None:
        state = set_recipe(state, ref, recipe)
    return state, ref, analysis, {'sha256': asset, 'width': size, 'height': size}, original


def native_double(calls):
    """Named size/position-only FFI double; no anatomy or production bypass."""
    def controls(points, roles, frame, values):
        assert points.dtype == frame.dtype == values.dtype == np.float64
        assert roles.shape == points.shape and not np.any(roles)
        assert not np.any(values[1:9]) and np.all(np.abs(values) <= 1.)
        assert not points.flags.writeable and not frame.flags.writeable
        assert not roles.flags.writeable and not values.flags.writeable
        calls.append({'points': points.copy(), 'frame': frame.copy(), 'values': values.copy()})
        # This is the explicit synthetic native seam, not a replacement solver.
        return np.asarray(.12*values[0]*(points-frame[4:6])
                          + .08*frame[8]*values[9]*frame[2:4], dtype=np.float64)
    return controls


def set_recipe(state, ref, recipe):
    for path, value in A.leaves(recipe).items():
        state = P.set_override(state, 'face', ref['face_instance_id'], S.OP, path, value)
    return state


def resolved(state, ref):
    return A.recipes(RESOLVE.resolve(state, ref['face_instance_id'], A.defaults()))


def command(state, ref, recipe, *, unset=False):
    patches = [{'operation_id': S.OP, 'parameter_path': path, 'unset': unset,
                **({} if unset else {'value': value})}
               for path, value in A.leaves(recipe).items()]
    return {'document_id': DOCUMENT, 'document_epoch': 'synthetic-epoch', 'document_revision': 7,
            'state_revision': state['revision'], 'association_revision': state['association_revision'],
            'request_id': 'synthetic-symmetry-atomic-request', 'action': 'patch',
            'target': {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': deepcopy(ref)},
            'payload': {'patches': patches}}


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


@pytest.mark.parametrize('path,expected', list(PRIOR_SOURCE_SHA256.items()))
def test_legacy_native_controls_tps_and_eye_field_bytes_remain_unchanged(path, expected):
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == expected


def test_registry_and_derived_transport_keep_three_new_leaves_out_of_manual_eye_recipe():
    assert S.OP == 'lnx.eye_symmetry.v1' and S.OP not in A.GEOMETRY
    assert A.defaults()[S.OP] == {'/horizontal': 0., '/size': 0., '/reference': 'auto'}
    assert S.OP in DERIVED.OPERATIONS and '/version' not in A.defaults()[S.OP]
    assert set(MANUAL.neutral()) == {'version', *MANUAL.KEYS}
    assert 'reference' not in MANUAL.KEYS and 'horizontal' not in MANUAL.KEYS
    for path, value in A.leaves(ACTIVE).items():
        DERIVED._leaf(S.OP, path, value)
    for reference in ('auto', 'left', 'right'):
        DERIVED._leaf(S.OP, '/reference', reference)
    state, ref, _, _, _ = fixture()
    reset = command(state, ref, S.neutral())
    DERIVED._patches(reset['payload'])
    assert len(reset['payload']['patches']) == 3


@pytest.mark.parametrize('path,value', [('/horizontal', True), ('/horizontal', -.01),
    ('/size', 1.01), ('/size', '0.3'), ('/size', float('nan')), ('/size', float('inf')),
    ('/reference', 'larger'), ('/reference', False), ('/version', 1),
    ('/reference_area', 200.), ('/landmarks', []), ('/source_sha256', 'a'*64), ('/pixels', [])])
def test_derived_transport_refuses_source_payloads_and_coercion(path, value):
    with pytest.raises(ValueError):
        DERIVED._leaf(S.OP, path, value)


@pytest.mark.parametrize('reference', ['auto', 'left', 'right'])
def test_neutral_reference_only_append_preserves_exact_prefix_without_source_or_native(reference):
    original = object()
    recipe = {**S.neutral(), 'reference': reference}
    with patch.object(SHARED, 'controls', side_effect=AssertionError('neutral reached native')) as native:
        assert PORT.append(original, None, None, None, None, recipe) == (original, None)
    native.assert_not_called()


def test_real_edit_history_undo_redo_reset_and_inherit_preserve_manual_recipe():
    state, ref, analysis, binding, _ = fixture(recipe=S.neutral())
    manual = MANUAL.link(MANUAL.neutral(), 'position', False)
    manual = MANUAL.adjust(manual, 'position', 'left', .11)
    for path, value in A.leaves(manual).items():
        state = P.set_override(state, 'face', ref['face_instance_id'], A.GEOMETRY[2], path, value)
    before, owner = deepcopy(state), PeopleGraphOwner(state)
    asset = ref['asset_sha256']
    chosen = {**ACTIVE, 'reference': 'right'}
    previous = {'_people_history': owner.capture_document(asset)}
    staged = stage(command(state, ref, chosen), state, ref)['state']
    assert resolved(staged, ref)[S.OP] == chosen
    assert resolved(staged, ref)[A.GEOMETRY[2]] == manual
    A.validate_compatibility(resolved(staged, ref))
    owner.commit(staged, expected_fence=0)
    following = {'_people_history': owner.capture_document(asset)}
    transition = HISTORY.decorate(previous, following)[HISTORY.KEY]
    assert {tuple(change['key'][-2:]) for change in transition['changes']} == {
        (S.OP, '/horizontal'), (S.OP, '/size'), (S.OP, '/reference')}
    undone = HISTORY.restore(owner, transition, asset)
    assert resolved(undone, ref)[S.OP] == S.neutral()
    owner.commit(undone, expected_fence=1)
    reverse = HISTORY.decorate(following, {'_people_history': owner.capture_document(asset)})[HISTORY.KEY]
    redone = HISTORY.restore(owner, reverse, asset)
    assert resolved(redone, ref)[S.OP] == chosen
    owner.commit(redone, expected_fence=2)
    reset = stage(command(owner.snapshot(), ref, S.neutral()), owner.snapshot(), ref)['state']
    assert resolved(reset, ref)[S.OP] == S.neutral()
    assert resolved(reset, ref)[A.GEOMETRY[2]] == manual
    inherited = P.set_override(reset, 'all_people', asset, S.OP, '/size', .2)
    inherited = stage(command(inherited, ref, S.neutral(), unset=True), inherited, ref)['state']
    assert resolved(inherited, ref)[S.OP]['size'] == .2
    assert resolved(inherited, ref)[A.GEOMETRY[2]] == manual
    assert state == before and owner.fence == 3


def test_project_and_frozen_snapshot_keep_portable_intent_without_donor_measurements():
    state, ref, analysis, binding, _ = fixture()
    payload = {'people_graph': state, 'undo': [{'_people_state': set_recipe(state, ref, S.neutral())}]}
    restored = json.loads(json.dumps(payload, sort_keys=True, allow_nan=False))
    PROJECT.validate_records(restored)
    assert restored == payload and resolved(restored['people_graph'], ref)[S.OP] == ACTIVE
    assert set(A.leaves(S.preset(ACTIVE))) == {'/horizontal', '/size', '/reference'}
    DERIVED.require_graph(state, binding, document_id=None)
    frozen = snapshot(state, ref, analysis, binding)
    saved_landmarks = frozen['analyses'][ref['face_instance_id']]['landmarks'].copy()
    analysis['landmarks'][0, 0] += np.float32(.001)
    state['overrides'].clear()
    assert resolved(frozen['state'], ref)[S.OP] == ACTIVE
    np.testing.assert_array_equal(frozen['analyses'][ref['face_instance_id']]['landmarks'], saved_landmarks)
    for name in ('landmarks', 'excluded', 'skin', 'face_skin'):
        retained = frozen['analyses'][ref['face_instance_id']][name]
        assert not retained.flags.writeable and not np.shares_memory(retained, analysis[name])


def assert_prepared(prepared, ref, shape, *, moving=True):
    key = ref['face_instance_id']
    assert type(prepared.geometry) is CombinedGeometry
    assert prepared.geometry.delta.shape == (1, *shape, 2)
    assert prepared.geometry.owner.shape == shape and prepared.geometry.face_ids == (key,)
    assert not prepared.geometry.delta.flags.writeable and not prepared.geometry.owner.flags.writeable
    assert len(prepared.face_fields) == 1 and prepared.effects == ()
    face = prepared.face_fields[0]
    assert isinstance(face, FaceGeometry) and type(face.prefix) is FaceGeometry
    assert face.fields[:4] == (None,)*4 and len(face.fields) == 5
    assert face.prefix.fields == (None,)*4 and not face.automatic.units
    assert prepared.facts[key]['eye_symmetry'] is face.fields[-1].facts
    assert prepared.plan['sample_policy'] == 'one_original_source_sample_after_composed_field'
    if moving:
        assert prepared.geometry.peak > 0 and np.any(prepared.geometry.owner == 0)
    return face.fields[-1]


@pytest.mark.parametrize('recipe', RECIPES)
def test_rgb16_original_and_owned_float_export_use_same_real_field_and_one_sampler(recipe):
    state, ref, analysis, binding, original = fixture(recipe=recipe)
    before, source_before = deepcopy(state), original.copy()
    working = original.astype(np.float32)/65535.
    frozen = snapshot(state, ref, analysis, binding)
    derived = {**frozen, 'creative_source': binding}
    calls = []
    with patch.object(SHARED, 'controls', side_effect=native_double(calls)):
        old, new = export(frozen, original), export(derived, working)
    first = assert_prepared(old, ref, original.shape[:2])
    second = assert_prepared(new, ref, original.shape[:2])
    assert calls and first is not second
    np.testing.assert_array_equal(old.geometry.delta, new.geometry.delta)
    np.testing.assert_array_equal(old.geometry.owner, new.geometry.owner)
    old_output, new_output = old.geometry.warp_original(original), new.geometry.warp(working)
    assert old_output.dtype == np.uint16 and np.any(original % 257 != 0)
    assert np.any(old_output != original) and np.any(new_output != working)
    np.testing.assert_allclose(old_output.astype(np.float64)/65535., new_output, rtol=0, atol=1.1/65535.)
    np.testing.assert_array_equal(original, source_before)
    assert state == before and frozen['state'] == before


@pytest.mark.parametrize('reference', ['auto', 'left', 'right'])
def test_neutral_reference_only_export_needs_no_analysis_and_preserves_original_rgb16(reference):
    recipe = {**S.neutral(), 'reference': reference}
    state, ref, _, _, original = fixture(recipe=recipe)
    frozen = SNAP.capture(state, ref['asset_sha256'], {})
    frozen.update(document_id=DOCUMENT, support_assets={})
    with patch.object(SHARED, 'controls', side_effect=AssertionError('neutral reached native')) as native:
        prepared = export(frozen, original)
    native.assert_not_called()
    assert prepared.face_fields == () and prepared.effects == () and prepared.facts == {}
    assert not prepared.plan['entries'][0]['requires_analysis']
    np.testing.assert_array_equal(prepared.geometry.warp_original(original), original)


@pytest.mark.parametrize('reference', ['auto', 'left', 'right'])
def test_empty_photo_reference_only_policy_never_invents_a_face_or_needs_analysis(reference):
    _, _, _, binding, original = fixture(recipe=None)
    state = P.set_override(P.empty(), 'all_people', binding['sha256'], S.OP, '/reference', reference)
    frozen = SNAP.capture(state, binding['sha256'], {})
    frozen.update(document_id=DOCUMENT, support_assets={})
    with patch.object(SHARED, 'controls', side_effect=AssertionError('empty neutral photo reached native')) as native:
        prepared = export(frozen, original)
    native.assert_not_called()
    assert prepared.face_fields == () and prepared.plan['entries'] == []
    assert prepared.geometry.face_ids == () and not state['faces']
    np.testing.assert_array_equal(prepared.geometry.warp_original(original), original)


@pytest.mark.parametrize('path,value', [('/horizontal', .1), ('/size', .1),
                                     ('/reference', 'donor'), ('/reference', 1)])
def test_empty_photo_nonzero_or_malformed_request_still_refuses(path, value):
    _, _, _, binding, original = fixture(recipe=None)
    state = P.set_override(P.empty(), 'all_people', binding['sha256'], S.OP, path, value)
    frozen = SNAP.capture(state, binding['sha256'], {})
    frozen.update(document_id=DOCUMENT, support_assets={})
    with patch.object(SHARED, 'controls', side_effect=AssertionError('empty active photo reached native')) as native:
        with pytest.raises(ValueError):
            export(frozen, original)
    native.assert_not_called()


@pytest.mark.parametrize('kind', ['legacy_big_eye', 'manual_size', 'manual_position'])
def test_symmetry_staging_adds_no_mutual_exclusion_or_manual_recipe_rewrite(kind):
    state, ref, _, _, _ = fixture(recipe=S.neutral())
    if kind == 'legacy_big_eye':
        state = P.set_override(state, 'face', ref['face_instance_id'], A.DEFORM, '/big_eye', .2)
    else:
        key = 'size' if kind == 'manual_size' else 'position'
        manual = MANUAL.adjust(MANUAL.neutral(), key, 'left', .2)
        for path, value in A.leaves(manual).items():
            state = P.set_override(state, 'face', ref['face_instance_id'], A.GEOMETRY[2], path, value)
    before = deepcopy(state)
    changed = stage(command(state, ref, ACTIVE), state, ref)['state']
    values = resolved(changed, ref)
    A.validate_compatibility(values)
    assert values[S.OP] == ACTIVE
    assert [row for row in changed['overrides'] if row['operation_id'] != S.OP] == [
        row for row in before['overrides'] if row['operation_id'] != S.OP]
    assert state == before


@pytest.mark.parametrize('reference', ['auto', 'left', 'right'])
def test_requested_already_symmetric_eyes_are_valid_measured_identity(reference):
    recipe = {'version': 1, 'horizontal': .8, 'size': .8, 'reference': reference}
    state, ref, analysis, binding, original = fixture(recipe=recipe, symmetric=True)
    calls = []
    with patch.object(SHARED, 'controls', side_effect=native_double(calls)):
        prepared = export(snapshot(state, ref, analysis, binding), original)
    assert_prepared(prepared, ref, original.shape[:2], moving=False)
    # Admission must retain measured active intent even if no pixel needs moving.
    assert prepared.plan['entries'][0]['requires_analysis']
    assert resolved(state, ref)[S.OP] == recipe
    np.testing.assert_array_equal(prepared.geometry.delta, np.zeros_like(prepared.geometry.delta))
    np.testing.assert_array_equal(prepared.geometry.warp_original(original), original)


@pytest.mark.parametrize('fault', ['missing', 'landmark_digest', 'foreign_face', 'occluded'])
def test_active_source_anatomy_failures_never_publish_partial_geometry(fault):
    state, ref, analysis, binding, original = fixture()
    before, pixels_before = deepcopy(state), original.copy()
    if fault == 'landmark_digest':
        analysis['landmarks'][0, 0] += np.float32(.001)
    elif fault == 'foreign_face':
        analysis['face_ref'] = {**analysis['face_ref'], 'asset_sha256': 'f'*64}
    elif fault == 'occluded':
        analysis['excluded'][:] = 1.
    with patch.object(SHARED, 'controls', side_effect=AssertionError('unadmitted source reached native')) as native:
        with pytest.raises(ValueError):
            frozen = SNAP.capture(state, ref['asset_sha256'], {} if fault == 'missing' else {ref['face_instance_id']: analysis})
            frozen.update(document_id=DOCUMENT, support_assets={})
            export(frozen, original)
    native.assert_not_called()
    assert state == before
    np.testing.assert_array_equal(original, pixels_before)


@pytest.mark.parametrize('fault', ['document', 'derived_source', 'budget', 'wrong_original_dtype', 'wrong_derived_dtype'])
def test_canonical_source_and_budget_refusal_never_substitute_proxy_or_another_owner(fault):
    state, ref, analysis, binding, original = fixture()
    frozen = snapshot(state, ref, analysis, binding)
    source, budget = original, BUDGET
    if fault == 'document': frozen['document_id'] = 'another-document'
    elif fault == 'derived_source':
        frozen['creative_source'] = {**binding, 'sha256': 'f'*64}
        source = original.astype(np.float32)/65535.
    elif fault == 'budget': budget = 1
    elif fault == 'wrong_original_dtype': source = original.astype(np.float32)/65535.
    else: frozen['creative_source'] = binding
    with patch.object(SHARED, 'controls', side_effect=AssertionError('invalid source reached native')) as native:
        with pytest.raises(ValueError):
            ENGINE.prepare_export(frozen, source, None, byte_budget=budget, document_id=DOCUMENT)
    native.assert_not_called()


@pytest.mark.parametrize('canonical_size', [512, 768])
def test_original_and_derived_preview_share_real_map_and_verified_repair_identity(canonical_size):
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding, original = fixture(size=canonical_size)
    before = deepcopy(state)
    # Explicit synthetic source-derived nearest proxy, not a second inference.
    indices = np.floor(np.arange(512)*canonical_size/512).astype(int)
    proxy = (original[indices[:, None], indices[None, :]]//257).astype(np.uint8)
    for name in ('excluded', 'skin', 'face_skin'):
        analysis[name] = np.full((512, 512), 0. if name == 'excluded' else 1., np.float32)
    analysis['face_skin_observation'].update(producer_width=512, producer_height=512)
    working = proxy.astype(np.float32)/255.
    pipe = SimpleNamespace(src_f32=torch.from_numpy(working.copy()).permute(2, 0, 1)[None],
                           repair_base=None, repair_ops=[], redo_ops=[])
    proof = REPLAY.make_evidence(binding, working, None, REPAIRS.digest_ops([], [], binding))
    pipe._creative_repair_source = deepcopy(binding)
    pipe._creative_repair_input = deepcopy(proof['input'])
    pipe._creative_repair_evidence = proof
    calls = []
    with patch.object(SHARED, 'controls', side_effect=native_double(calls)):
        old = ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                                     byte_budget=BUDGET, document_id=DOCUMENT)
        new = ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                                     byte_budget=BUDGET, document_id=DOCUMENT,
                                     creative_source=binding, creative_proxy=proxy)
    original_field = assert_prepared(old, ref, working.shape[:2])
    derived_field = assert_prepared(new, ref, working.shape[:2])
    np.testing.assert_array_equal(old.geometry.delta, new.geometry.delta)
    np.testing.assert_array_equal(old.geometry.warp(working), new.geometry.warp(working))
    assert calls and REPLAY.verify_pipeline(pipe, binding) == proof and state == before
    assert original_field.shape == derived_field.shape == (512, 512)
    assert analysis['evidence']['source_width'] == binding['width'] == canonical_size
    expected = CORE.pixels(analysis['landmarks'], (512, 512))
    np.testing.assert_array_equal(derived_field.source_eyes, np.stack([
        expected[list(CORE.EYES[side]+CORE.IRIS[side])] for side in ('left', 'right')]))
    np.testing.assert_array_equal(pipe.src_f32[0].permute(1, 2, 0).numpy(), working)


@pytest.mark.parametrize('fault', [None, 'missing', 'input_digest', 'output_digest', 'source'])
def test_derived_export_checks_real_repair_proof_and_measures_unrepaired_owner(fault):
    state, ref, analysis, binding, original = fixture()
    frozen = snapshot(state, ref, analysis, binding, derived=True)
    working = original.astype(np.float32)/65535.
    # A flat repair deliberately has no visible eye evidence. The source-owned
    # geometry must still use the original unmodified textured synthetic source.
    repaired = np.full_like(working, .4)
    before = (working.copy(), repaired.copy(), deepcopy(state))
    proof = REPLAY.make_evidence(binding, working, repaired, REPAIRS.digest_ops([], [], binding))
    if fault == 'missing': proof = None
    elif fault == 'input_digest': proof['input']['sha256'] = 'f'*64
    elif fault == 'output_digest': proof['output']['sha256'] = 'f'*64
    elif fault == 'source': proof['source']['sha256'] = 'f'*64
    calls = []
    with patch.object(SHARED, 'controls', side_effect=native_double(calls)) as native:
        if fault is None:
            expected = export(frozen, working)
            prepared = export(frozen, working, repaired, creative_repair_evidence=proof)
            assert_prepared(prepared, ref, working.shape[:2])
            np.testing.assert_array_equal(expected.geometry.delta, prepared.geometry.delta)
            assert REPLAY.verify_evidence(proof, binding, working, repaired) == proof
        else:
            with pytest.raises(ValueError):
                export(frozen, working, repaired, creative_repair_evidence=proof)
            native.assert_not_called()
    np.testing.assert_array_equal(working, before[0])
    np.testing.assert_array_equal(repaired, before[1])
    assert state == before[2]


@pytest.mark.parametrize('fault', ['missing', 'input_digest', 'stack_digest'])
def test_missing_or_tampered_derived_preview_repair_evidence_refuses_before_native(fault):
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding, original = fixture()
    proxy = (original//257).astype(np.uint8)
    working = proxy.astype(np.float32)/255.
    pipe = SimpleNamespace(src_f32=torch.from_numpy(working.copy()).permute(2, 0, 1)[None],
                           repair_base=None, repair_ops=[], redo_ops=[])
    if fault != 'missing':
        proof = REPLAY.make_evidence(binding, working, None, REPAIRS.digest_ops([], [], binding))
        pipe._creative_repair_source = deepcopy(binding)
        pipe._creative_repair_input = deepcopy(proof['input'])
        if fault == 'input_digest': proof['input']['sha256'] = 'f'*64
        else: proof['stack_sha256'] = 'f'*64
        pipe._creative_repair_evidence = proof
    with patch.object(SHARED, 'controls', side_effect=AssertionError('invalid proof reached native')) as native:
        with pytest.raises(ValueError):
            ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                byte_budget=BUDGET, document_id=DOCUMENT, creative_source=binding, creative_proxy=proxy)
    native.assert_not_called()


@pytest.mark.parametrize('reference', ['auto', 'left', 'right'])
def test_original_person_recipe_recomputes_each_target_eyes_without_donor_pixels(reference):
    targets = [fixture(recipe=None, asset='a'*64, larger='left'),
               fixture(recipe=None, asset='f'*64, larger='right', tone=.02)]
    state = P.empty()
    for own, _, _, _, _ in targets:
        state['faces'].update(deepcopy(own['faces']))
    state, person = LINKS.create_person(state)
    for _, ref, _, _, _ in targets:
        state = LINKS.set_link(state, ref['face_instance_id'], person, 'confirmed', user_confirmed=True)
    recipe = {**ACTIVE, 'reference': reference}
    first_ref = targets[0][1]
    edit = command(state, first_ref, recipe)
    edit['target'] = {'scope': 'person', 'target_id': person, 'face_ref': None}
    owner, before = PeopleGraphOwner(state), deepcopy(state)
    candidate = stage(edit, state, first_ref)['state']
    assert affected_assets(state, candidate) == {'a'*64, 'f'*64}
    shared = [row for row in candidate['overrides'] if row['operation_id'] == S.OP]
    assert len(shared) == 3 and all(row['scope'] == 'person' for row in shared)
    assert {row['parameter_path'] for row in shared} == {'/horizontal', '/size', '/reference'}
    fields, prepared_maps, sources = [], [], []
    for _, ref, analysis, binding, original in targets:
        assert resolved(candidate, ref)[S.OP] == recipe
        frozen = snapshot(candidate, ref, analysis, binding)
        source = original
        sources.append(source.copy())
        calls = []
        with patch.object(SHARED, 'controls', side_effect=native_double(calls)):
            prepared = export(frozen, source)
        field = assert_prepared(prepared, ref, source.shape[:2])
        measured = CORE.pixels(analysis['landmarks'], source.shape[:2])
        expected = np.stack([measured[list(CORE.EYES[side]+CORE.IRIS[side])]
                             for side in ('left', 'right')])
        np.testing.assert_array_equal(field.source_eyes, expected)
        fields.append(field)
        prepared_maps.append(prepared.geometry.delta)
        assert calls and owner.snapshot() == before and owner.fence == 0
        np.testing.assert_array_equal(source, sources[-1])
    left, right = (field.facts['size'] for field in fields)
    assert left['left_opening_area_px2'] > left['right_opening_area_px2']
    assert right['right_opening_area_px2'] > right['left_opening_area_px2']
    assert left['resolved_reference'] == ('left' if reference == 'auto' else reference)
    assert right['resolved_reference'] == ('right' if reference == 'auto' else reference)
    assert fields[0] is not fields[1]
    assert not np.array_equal(sources[0], sources[1])
    assert not np.shares_memory(fields[0].source_eyes, fields[1].source_eyes)
    assert not np.shares_memory(prepared_maps[0], prepared_maps[1])
    assert not np.array_equal(prepared_maps[0], prepared_maps[1])
    owner.commit(candidate, expected_fence=0)
    assert state == before and owner.fence == 1
    for _, ref, _, _, _ in targets:
        assert resolved(owner.snapshot(), ref)[S.OP] == recipe


@pytest.mark.parametrize('reference', ['auto', 'left', 'right'])
def test_reviewed_derived_replicas_transport_only_intent_and_remeasure_owned_source(reference):
    """Real local capsule validation, not a whole cross-document commit claim."""
    targets = [fixture(recipe=None, asset='a'*64, larger='left'),
               fixture(recipe=None, asset='f'*64, larger='right', tone=.02)]
    documents = ('synthetic-derived-a', 'synthetic-derived-b')
    members = [{'document_id': document, 'scope_id': document,
                'original_sha256': ('1' if index == 0 else '2')*64, 'ref': deepcopy(target[1])}
               for index, (document, target) in enumerate(zip(documents, targets))]
    recipe = {**ACTIVE, 'reference': reference}
    intent = [{'op': S.OP, 'path': path, 'value': value} for path, value in A.leaves(recipe).items()]
    fields, capsules = [], []
    for document, (state, ref, analysis, binding, original) in zip(documents, targets):
        capsule = CROSS.descriptor('synthetic-reviewed-eyes', document, members, intent)
        candidate = CROSS.create(state, 'synthetic-person', capsule)
        capsules.append(capsule)
        DERIVED.require_graph(candidate, binding, document_id=document)
        assert resolved(candidate, ref)[S.OP] == recipe
        assert capsule['intent'] == sorted(intent, key=lambda value: (value['op'], value['path']))
        frozen = snapshot(candidate, ref, analysis, binding, derived=True)
        frozen['document_id'] = document
        source, calls = original.astype(np.float32)/65535., []
        with patch.object(SHARED, 'controls', side_effect=native_double(calls)):
            prepared = ENGINE.prepare_export(frozen, source, None, byte_budget=BUDGET, document_id=document)
        field = assert_prepared(prepared, ref, source.shape[:2])
        fields.append(field)
        expected = CORE.pixels(analysis['landmarks'], source.shape[:2])
        np.testing.assert_array_equal(field.source_eyes, np.stack([
            expected[list(CORE.EYES[side]+CORE.IRIS[side])] for side in ('left', 'right')]))
        assert calls and candidate['faces'] == state['faces']
    assert capsules[0]['generation'] == capsules[1]['generation']
    assert fields[0].facts['size']['resolved_reference'] == ('left' if reference == 'auto' else reference)
    assert fields[1].facts['size']['resolved_reference'] == ('right' if reference == 'auto' else reference)
    assert not np.array_equal(fields[0].source_eyes, fields[1].source_eyes)
    assert not np.shares_memory(fields[0].source_eyes, fields[1].source_eyes)


@pytest.mark.parametrize('derived', [False, True])
def test_export_resamples_retained_semantics_but_rebuilds_actual_full_resolution_eye_field(derived):
    state, ref, analysis, binding, original = fixture(size=768)
    producer = 512
    for name in ('excluded', 'skin', 'face_skin'):
        fill = 0. if name == 'excluded' else 1.
        analysis[name] = np.full((producer, producer), fill, np.float32)
    analysis['face_skin_observation'].update(producer_width=producer, producer_height=producer)
    frozen = snapshot(state, ref, analysis, binding, derived=derived)
    source = original.astype(np.float32)/65535. if derived else original
    calls = []
    with patch.object(SHARED, 'controls', side_effect=native_double(calls)):
        prepared = export(frozen, source)
    own = assert_prepared(prepared, ref, (768, 768))
    expected = CORE.pixels(analysis['landmarks'], (768, 768))
    np.testing.assert_array_equal(own.source_eyes, np.stack([
        expected[list(CORE.EYES[side]+CORE.IRIS[side])] for side in ('left', 'right')]))
    assert own.shape == (768, 768) and calls
    retained = frozen['analyses'][ref['face_instance_id']]
    assert retained['excluded'].shape == (512, 512)
    assert retained['face_skin_observation']['producer_width'] == producer
    assert state['faces'][ref['face_instance_id']]['evidence']['source_width'] == 768


@pytest.mark.parametrize('fault', ['face_ref', 'observation', 'landmarks'])
def test_target_cannot_borrow_donor_analysis_or_keep_stale_landmark_digest(fault):
    _, donor_ref, donor_analysis, _, _ = fixture(asset='a'*64, larger='left')
    state, ref, analysis, binding, original = fixture(asset='f'*64, larger='right')
    if fault == 'face_ref': analysis['face_ref'] = deepcopy(donor_ref)
    elif fault == 'observation': analysis['face_skin_observation'] = deepcopy(donor_analysis['face_skin_observation'])
    else: analysis['landmarks'] = donor_analysis['landmarks'].copy()
    before = deepcopy(state)
    with patch.object(SHARED, 'controls', side_effect=AssertionError('donor evidence reached native')) as native:
        with pytest.raises(ValueError):
            export(snapshot(state, ref, analysis, binding, derived=True), original.astype(np.float32)/65535.)
    native.assert_not_called()
    assert state == before


def prefix_fixture():
    state, ref, analysis, _, original = fixture()
    source = original.astype(np.float32)/65535.
    shape = source.shape[:2]
    automatic = AutomaticField(analysis['landmarks'], dict.fromkeys(D.KINDS, 0.), shape)
    # Named synthetic prior TPS: only composition, not old anatomical admission.
    points = np.array([[0., 0.], [511., 0.], [0., 511.], [511., 511.], [176., 210.], [336., 214.]])
    deltas = np.array([[0., 0.], [.08, 0.], [0., .06], [.04, -.04], [.14, -.06], [-.04, .1]])
    tps = D.tps_solve(points, deltas, scale=float(max(shape)))
    automatic.units.append((tps, 1., np.array([255.5, 255.5]), 300., 400.))
    automatic.windows.append((np.array([255.5, 255.5]), 300., 400.))
    mouth = SimpleNamespace(state=None, resident_bytes=lambda: 0)
    prefix = FaceGeometry(ref['face_instance_id'], shape, automatic, (None, None, None, mouth))
    return state, ref, analysis, source, prefix


@pytest.mark.parametrize('enabled', list(product((False, True), repeat=7)))
def test_128_contour_wrapper_prefix_topologies_keep_mouth_and_append_symmetry_last(enabled):
    """128 wrapper topologies, not execution of every predecessor recipe family."""
    from lumaretouch_engine.face_contour_people import ContouredFace
    from lumaretouch_engine.face_size_people import SizedFace
    from lumaretouch_engine.lower_face_people import LowerFace
    from lumaretouch_engine.mid_face_people import MidFace
    from lumaretouch_engine.chin_shape_people import ChinShape
    from lumaretouch_engine.chin_length_people import ChinLength
    from lumaretouch_engine.philtrum_people import Philtrum
    state, ref, analysis, source, base = prefix_fixture()
    prefix, previous = base, []
    # Corrected slim delegates the same contour wrapper, but this fixture does
    # not run either predecessor's native admission or distinct recipe policy.
    # It exercises real wrapper composition with named synthetic prior fields.
    wrappers = ((ContouredFace, 'contour'), (SizedFace, 'face_size'),
                (LowerFace, 'lower_face'), (MidFace, 'mid_face'),
                (ChinShape, 'chin_shape'), (ChinLength, 'chin_length'), (Philtrum, 'philtrum'))
    for use, (wrapper, label) in zip(enabled, wrappers):
        if not use: continue
        prior = SimpleNamespace(state={'synthetic_prefix': label},
            evaluate=lambda q: (np.asarray(q, dtype=np.float64)-[255.5, 255.5])*.0001,
            resident_bytes=lambda: 64)
        prefix = wrapper(base.face_instance_id, base.shape, base.automatic, (*prefix.fields, prior), prefix, ())
        previous.append(prior)
    saved_fields, source_before = prefix.fields, source.copy()
    calls = []
    with patch.object(SHARED, 'controls', side_effect=native_double(calls)):
        result, facts = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    assert type(result) is PORT.EyeSymmetry and result.prefix is prefix
    assert result.automatic is base.automatic and 4 <= len(prefix.fields) <= 11
    assert prefix.fields is saved_fields and result.fields[:-1] == saved_fields
    assert result.fields[3] is base.fields[3]
    assert all(result.fields[4+i] is field for i, field in enumerate(previous))
    own = result.fields[-1]
    assert type(own) is CORE.EyeSymmetryField and facts is own.facts
    points = own.target_eyes.reshape(-1, 2)[[0, 4, 16, 21, 25, 37]].copy()
    symmetry = own.evaluate(points)
    expected = symmetry + prefix.evaluate(points-symmetry)
    np.testing.assert_allclose(result.evaluate(points), expected, rtol=0, atol=1e-12)
    assert not np.allclose(expected, prefix.evaluate(points)+symmetry, rtol=0, atol=1e-10)
    assert result.resident_bytes() >= prefix.resident_bytes()+own.resident_bytes()
    np.testing.assert_array_equal(source, source_before)
    assert calls


@pytest.mark.parametrize('fault', ['identity', 'disabled', 'digest', 'grid', 'owner', 'few_slots', 'many_slots'])
def test_prefix_foreign_identity_or_invalid_shape_refuses_before_native(fault):
    state, ref, analysis, source, prefix = prefix_fixture()
    if fault == 'identity': ref = {**ref, 'analysis_revision': ref['analysis_revision']+1}
    elif fault == 'disabled': state['faces'][ref['face_instance_id']]['enabled'] = False
    elif fault == 'digest': analysis['landmarks'][0, 0] += np.float32(.001)
    elif fault == 'grid': prefix = FaceGeometry(prefix.face_instance_id, (64, 64), prefix.automatic, prefix.fields)
    elif fault == 'owner': prefix = FaceGeometry('other-face', prefix.shape, prefix.automatic, prefix.fields)
    else: prefix = FaceGeometry(prefix.face_instance_id, prefix.shape, prefix.automatic, (None,)*(3 if fault == 'few_slots' else 12))
    with patch.object(SHARED, 'controls', side_effect=AssertionError('invalid prefix reached native')) as native:
        with pytest.raises(ValueError):
            PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    native.assert_not_called()


def test_repeated_append_never_acquires_second_symmetry_owner():
    state, ref, analysis, source, prefix = prefix_fixture()
    calls = []
    with patch.object(SHARED, 'controls', side_effect=native_double(calls)):
        wrapped, _ = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
        count = len(calls)
        with pytest.raises(ValueError):
            PORT.append(wrapped, state, ref, analysis, source, ACTIVE)
    assert len(calls) == count and len(prefix.fields) == 4


@pytest.mark.parametrize('failure', ['preparation', 'publication'])
def test_real_host_failure_rolls_back_recipe_and_history_without_rewinding_fence(failure):
    """Real stage/export/publish/owner; minimal host IO is deliberately explicit."""
    state, ref, analysis, binding, original = fixture(recipe=S.neutral())
    before, owner = deepcopy(state), PeopleGraphOwner(state)
    edit = command(state, ref, ACTIVE)
    pixels_before, prepared, syncs, events = original.copy(), [], [], []
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
            raise ValueError('synthetic host publication refusal')
    engine._people_prepare_graph = prepare
    engine._people_sync = sync
    engine._people_publish_graph = lambda candidate, assets: PeopleHostMixin._people_publish_graph(engine, candidate, assets)
    calls = []
    native_action = (RuntimeError('synthetic native preparation refusal') if failure == 'preparation'
                     else native_double(calls))
    with patch.object(SHARED, 'controls', side_effect=native_action), pytest.raises(ValueError, match='synthetic'):
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
        assert current['revision'] > before['revision']
    np.testing.assert_array_equal(original, pixels_before)


def test_source_routing_appends_after_philtrum_without_moving_mouth_slot_or_copying_recipe():
    source = (ROOT/'engine/src/lumaretouch_engine/people_render_runtime.py').read_text()
    tree = ast.parse(source)
    prepare = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'prepare')
    calls = [node for node in ast.walk(prepare) if isinstance(node, ast.Call)]
    names = ('build_geometry', 'append_slim', 'append_contour', 'append_size', 'append_lower',
             'append_mid', 'append_chin', 'append_chin_length', 'append_philtrum', 'append_eye_symmetry')
    ordered = []
    for name in names:
        found = [node for node in calls if (isinstance(node.func, ast.Name) and node.func.id == name)
                 or (isinstance(node.func, ast.Attribute) and node.func.attr == name)]
        assert len(found) == 1
        ordered.append(found[0].lineno)
        if name == 'append_eye_symmetry':
            assert len(found[0].args) == 6 and found[0].keywords == []
    assert ordered == sorted(ordered)
    assert 'mouth = field.fields[3]' in source and 'mouth = field.fields[-1]' not in source
    assert "facts[key]['eye_symmetry'] = eye_symmetry_facts" in source
    # Source-only ownership check: slim currently delegates ContouredFace and
    # returns that exact object, not a separate SlimmedFace implementation.
    # This assertion is not a positive slim recipe/native execution fixture.
    slim_tree = ast.parse((ROOT/'engine/src/lumaretouch_engine/slim_face_people.py').read_text())
    slim = next(node for node in slim_tree.body if isinstance(node, ast.FunctionDef) and node.name == 'append')
    delegates = [node for node in ast.walk(slim) if isinstance(node, ast.Assign)
                 and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                 and isinstance(node.value.func.value, ast.Name)
                 and node.value.func.value.id == 'C' and node.value.func.attr == 'append']
    assert len(delegates) == 1 and len(delegates[0].targets) == 1
    target = delegates[0].targets[0]
    assert isinstance(target, ast.Tuple) and isinstance(target.elts[0], ast.Name)
    returned = [node for node in ast.walk(slim) if isinstance(node, ast.Return)
                and isinstance(node.value, ast.Tuple) and isinstance(node.value.elts[0], ast.Name)
                and node.value.elts[0].id == target.elts[0].id]
    assert len(returned) == 1


def test_all_integration_patches_remain_at_existing_native_loader_or_controls_boundary():
    tree = ast.parse(Path(__file__).read_text())
    patches = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
               and node.func.value.id == 'patch' and node.func.attr == 'object']
    assert patches
    for call in patches:
        assert isinstance(call.args[0], ast.Name) and call.args[0].id == 'SHARED'
        assert isinstance(call.args[1], ast.Constant) and call.args[1].value in ('native', 'controls')
