# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: original-brow enhancement in the canonical people path.

All observations and images are explicitly synthetic fixtures, not detector
output or photographic acceptance. Only brow_enhance_native.available/apply
are doubled. Source admission, anatomical/semantic support, graph ownership,
staging, history, snapshots, preparation and the common sampler remain real.
The native double below checks routing only; it does NOT implement or validate
the Rust source-contrast algorithm. No import, test collection, execution,
inference, build or typecheck ran while authoring this file.

The bounded slice uses source-derived conservative support and the user's
parameter/preview decision. It neither creates a persisted manual review mask
nor borrows brow-material review as enhancement consent. Source-target gain
invariants are distinct from later additive upstream headroom composition.
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

from test_brow_enhance_support_unrun import synthetic_observation

from lumaretouch_engine import brow_enhance_state as S, brow_enhance_native as N
from lumaretouch_engine import brow_enhance_layer as LAYER
from lumaretouch_engine import brow_shape_state as SHAPE, brow_makeup_state as MATERIAL
from lumaretouch_engine import people_algorithms as A, people_state as P
from lumaretouch_engine import people_resolver as RESOLVE, people_associations as LINKS
from lumaretouch_engine import people_cross_owner as CROSS, people_project as PROJECT
from lumaretouch_engine import people_snapshot as SNAP, people_export as EXPORT
from lumaretouch_engine import people_engine_runtime as ENGINE, people_render_runtime as RENDER
from lumaretouch_engine import people_effects as EFFECTS, people_pipeline as PIPE
from lumaretouch_engine import people_edit as EDIT, people_host_commands as HOST
from lumaretouch_engine import people_document_history as HISTORY
from lumaretouch_engine.people_host import PeopleHostMixin
from lumaretouch_engine.people_graph_owner import PeopleGraphOwner, affected_assets
from lumaretouch_engine.people_geometry import CombinedGeometry, FaceGeometry
from lumaretouch_engine import creative_derived_effects as DERIVED
from lumaretouch_engine import creative_derived_repairs as REPAIRS
from lumaretouch_engine import creative_derived_repair_runtime as REPLAY

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = 'synthetic-brow-enhancement-document'
BUDGET = 512 * 1024**2
ACTIVE = {'version': 1, 'linked': True, 'left': .45, 'right': .45}
UNLINKED = {'version': 1, 'linked': False, 'left': -.35, 'right': .55}
LEAVES = {'/linked', '/left', '/right'}

# Read-only byte observations, not runtime/native parity evidence.
LEGACY_SHA256 = {
    'core/brow_shape/lib.rs': '04cf2c546a7c039ca3a88a64a704e71f9579a56afb802496223985d79ea65441',
    'core/brow_makeup/brow_makeup.rs': '2d2cce43adcd7251114ae0c5493790f3f5e4cf9597d0269a74853f1e484dfd15',
    'engine/src/lumaretouch_engine/brow_shape_field.py': 'c1437ab499c12d0f9ab5f3e308776103f2332d66e06caaf21cc33b1742ff86ae',
    'engine/src/lumaretouch_engine/brow_makeup_geometry.py': 'eac237ad7f11d030c05a6deba65016f0c11495c1b153c2cf335a09769e2838b4',
    'engine/src/lumaretouch_engine/ops/deform.py': '5e0800bffa8f87f9f8e4f6cf8caa1ea782bee20d099a2232c869e0e9d53247fd',
}


@pytest.fixture(autouse=True)
def named_native_availability_double():
    """Native capability seam only; never claims the real library was loaded."""
    with patch.object(N, 'available', return_value=True):
        yield


def fixture(*, recipe=ACTIVE, asset='a'*64, size=256, tone=0.):
    """Each call creates independent synthetic observations and a real owner."""
    _, analysis, source = synthetic_observation(size=size)
    analysis = deepcopy(analysis)
    source = np.array(source, dtype=np.float32, copy=True)
    if tone:
        source = source + np.float32(tone)
    assert np.isfinite(source).all() and np.all((source >= 0) & (source <= 1))
    evidence = deepcopy(analysis['evidence'])
    # This fixture declares its own full canonical source, unlike the support
    # worker's separate durable-1024/current-grid observation exercise.
    evidence.update(source_width=size, source_height=size)
    analysis['evidence'] = deepcopy(evidence)
    face = P.new_face(asset, [.05, .03, .95, .97], evidence)
    state = P.empty()
    state['faces'][face['face_instance_id']] = face
    ref = P.face_ref(face)
    analysis['face_ref'] = deepcopy(ref)
    analysis['face_skin_observation']['source_sha256'] = asset
    if recipe is not None:
        state = set_recipe(state, ref, recipe)
    original = np.rint(source.astype(np.float64)*65535.).astype(np.uint16)
    return state, ref, analysis, {'sha256': asset, 'width': size, 'height': size}, original


def set_recipe(state, ref, recipe, operation=None):
    for path, value in A.leaves(recipe).items():
        state = P.set_override(state, 'face', ref['face_instance_id'], operation or S.OP, path, value)
    return state


def resolved(state, ref):
    return A.recipes(RESOLVE.resolve(state, ref['face_instance_id'], A.defaults()))


def command(state, ref, recipe, *, unset=False):
    patches = [{'operation_id': S.OP, 'parameter_path': path, 'unset': unset,
                **({} if unset else {'value': value})}
               for path, value in A.leaves(recipe).items()]
    return {'document_id': DOCUMENT, 'document_epoch': 'synthetic-epoch', 'document_revision': 7,
            'state_revision': state['revision'], 'association_revision': state['association_revision'],
            'request_id': 'synthetic-brow-enhancement-request', 'action': 'patch',
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


def native_double(calls):
    """Synthetic bounded gain at the native seam, NOT the production shader."""
    def apply(source, coverage, amount, *, reference_coverage, radius, cancelled=None):
        assert source.dtype == coverage.dtype == reference_coverage.dtype == np.float32
        assert source.shape[:2] == coverage.shape == reference_coverage.shape
        assert not source.flags.writeable and not coverage.flags.writeable
        assert not reference_coverage.flags.writeable
        assert np.any(coverage > 0) and np.any(reference_coverage > 0)
        assert not np.any((coverage > 0) & (reference_coverage > 0))
        if cancelled is not None and cancelled():
            raise RuntimeError('synthetic native cancellation')
        calls.append({'source': source.copy(), 'coverage': coverage.copy(),
                      'reference': reference_coverage.copy(), 'radius': radius, 'amount': amount})
        # Deliberately simple and different from native log-contrast math. Its
        # only purpose is a visible, bounded, reference-dependent routing mark.
        reference_mean = float(np.mean(source[reference_coverage > 0], dtype=np.float64))
        linear = np.where(source <= .04045, source/12.92, ((source+.055)/1.055)**2.4)
        proposed = np.float32(1 - amount*(.025 + .025*reference_mean))*np.ones(coverage.shape, np.float32)
        if amount < 0:
            peak = np.max(linear, axis=2)
            proposed = np.minimum(proposed, 1 + (1/np.maximum(peak, np.float32(.001))-1)*np.float32(.5))
        gain = 1 + coverage*(proposed-1)
        corrected = linear*gain[..., None]
        encoded = np.where(corrected <= .0031308, corrected*12.92, 1.055*corrected**(1/2.4)-.055)
        return np.array(np.where(coverage[..., None] > 0, encoded, source), dtype=np.float32, copy=True)
    return apply


def assert_prepared(prepared, ref, shape):
    assert type(prepared.geometry) is CombinedGeometry
    assert prepared.geometry.delta.shape == (1, *shape, 2)
    assert prepared.geometry.face_ids == (ref['face_instance_id'],)
    assert not prepared.geometry.delta.flags.writeable
    assert not np.any(prepared.geometry.delta)
    assert len(prepared.face_fields) == 1
    face = prepared.face_fields[0]
    assert type(face) is FaceGeometry and face.fields == (None,)*4
    assert not face.automatic.units
    assert prepared.plan['sample_policy'] == 'one_original_source_sample_after_composed_field'
    assert len(prepared.effects) == 1
    record = prepared.effects[0]
    assert record.stage == 'brow_enhance' and record.face_ref == ref
    assert record.delta.dtype == np.float32 and not record.delta.flags.writeable
    assert np.isfinite(record.delta).all() and np.any(record.delta != 0)
    return record


@pytest.mark.parametrize('path,expected', list(LEGACY_SHA256.items()))
def test_existing_brow_material_geometry_and_common_sampler_bytes_are_unchanged(path, expected):
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == expected


def test_distinct_registry_and_derived_scalar_transport_do_not_alias_makeup_or_shape():
    assert S.OP == 'lnx.brow_enhance.v1' and S.OP not in A.GEOMETRY
    assert S.OP != MATERIAL.OP and S.OP in DERIVED.OPERATIONS
    assert A.defaults()[S.OP] == {'/linked': True, '/left': 0., '/right': 0.}
    assert set(A.leaves(ACTIVE)) == LEAVES
    for recipe in (ACTIVE, UNLINKED):
        for path, value in A.leaves(recipe).items():
            DERIVED._leaf(S.OP, path, value)
        state, ref, _, _, _ = fixture(recipe=None)
        DERIVED._patches(command(state, ref, recipe)['payload'])
    registry = json.loads((ROOT/'docs/p0/registry-extensions.json').read_text())
    row = next(item for item in registry['entries'] if item['operation_id'] == S.OP)
    assert row['source_requirement'] == 'PC-32471-C-18765fa8ea'
    assert S.CONTROL_ID == 'LNX-REF-PC-32471-C-18765fa8ea'


@pytest.mark.parametrize('path,value', [('/left', True), ('/right', '0.3'), ('/left', -1.01),
    ('/right', 1.01), ('/right', float('nan')), ('/left', float('inf')), ('/linked', 1),
    ('/linked', 'true'), ('/version', 1), ('/mask', []), ('/forehead', []),
    ('/source_sha256', 'a'*64), ('/reference_luminance', .5), ('/landmarks', [])])
def test_derived_transport_never_copies_source_support_or_coerces_invalid_leaves(path, value):
    with pytest.raises(ValueError):
        DERIVED._leaf(S.OP, path, value)


def test_atomic_equal_linked_patch_accepts_both_sides_but_half_patch_refuses():
    state, ref, _, _, _ = fixture(recipe=S.neutral())
    before = deepcopy(state)
    changed = stage(command(state, ref, ACTIVE), state, ref)['state']
    assert resolved(changed, ref)[S.OP] == ACTIVE
    bad = command(state, ref, ACTIVE)
    bad['payload']['patches'] = [p for p in bad['payload']['patches'] if p['parameter_path'] == '/left']
    with pytest.raises(ValueError):
        stage(bad, state, ref)
    assert state == before


def test_history_undo_redo_reset_and_inherit_do_not_change_material_or_geometry_intent():
    state, ref, _, _, _ = fixture(recipe=S.neutral())
    manual = SHAPE.adjust(SHAPE.neutral(), 'position', 'left', .11)
    material = MATERIAL.neutral()
    material['left']['strength'] = material['right']['strength'] = .2
    state = set_recipe(state, ref, manual, A.GEOMETRY[0])
    state = set_recipe(state, ref, material, MATERIAL.OP)
    before, owner = deepcopy(state), PeopleGraphOwner(state)
    asset = ref['asset_sha256']
    previous = {'_people_history': owner.capture_document(asset)}
    candidate = stage(command(state, ref, UNLINKED), state, ref)['state']
    owner.commit(candidate, expected_fence=0)
    following = {'_people_history': owner.capture_document(asset)}
    transition = HISTORY.decorate(previous, following)[HISTORY.KEY]
    assert {tuple(row['key'][-2:]) for row in transition['changes']} == {(S.OP, path) for path in LEAVES}
    undone = HISTORY.restore(owner, transition, asset)
    assert resolved(undone, ref)[S.OP] == S.neutral()
    owner.commit(undone, expected_fence=1)
    reverse = HISTORY.decorate(following, {'_people_history': owner.capture_document(asset)})[HISTORY.KEY]
    redone = HISTORY.restore(owner, reverse, asset)
    assert resolved(redone, ref)[S.OP] == UNLINKED
    owner.commit(redone, expected_fence=2)
    reset = stage(command(owner.snapshot(), ref, S.neutral()), owner.snapshot(), ref)['state']
    for operation, expected in ((S.OP, S.neutral()), (A.GEOMETRY[0], manual), (MATERIAL.OP, material)):
        assert resolved(reset, ref)[operation] == expected
    inherited = P.set_override(reset, 'all_people', asset, S.OP, '/left', .2)
    inherited = P.set_override(inherited, 'all_people', asset, S.OP, '/right', .2)
    inherited = stage(command(inherited, ref, S.neutral(), unset=True), inherited, ref)['state']
    assert resolved(inherited, ref)[S.OP] == {**ACTIVE, 'left': .2, 'right': .2}
    assert state == before and owner.fence == 3


def test_project_round_trip_and_snapshot_keep_recipe_only_and_own_observation_copies():
    state, ref, analysis, binding, _ = fixture()
    payload = {'people_graph': state, 'undo': [{'_people_state': set_recipe(state, ref, S.neutral())}]}
    restored = json.loads(json.dumps(payload, sort_keys=True, allow_nan=False))
    PROJECT.validate_records(restored)
    assert restored == payload and resolved(restored['people_graph'], ref)[S.OP] == ACTIVE
    assert state['faces'][ref['face_instance_id']]['local_assets'] == {}
    frozen = snapshot(state, ref, analysis, binding)
    assert frozen['support_assets'] == {}
    retained = frozen['analyses'][ref['face_instance_id']]
    for key in ('landmarks', 'excluded', 'skin', 'face_skin'):
        assert not retained[key].flags.writeable and not np.shares_memory(retained[key], analysis[key])
    leaves = [row for row in restored['people_graph']['overrides'] if row['operation_id'] == S.OP]
    assert {row['parameter_path'] for row in leaves} == LEAVES
    assert all(type(row['value']) in (bool, int, float) for row in leaves)
    assert EXPORT.fastpath_blocker(frozen)


def project_tree(state, location):
    if location == 'active':
        return {'people_graph': state}
    if location in ('undo', 'redo'):
        return {location: [{'_people_state': state}]}
    return {'document': {'children': [{'undo': [{'saved': {'_people_state': state}}]}]}}


@pytest.mark.parametrize('location', ['active', 'undo', 'redo', 'nested'])
@pytest.mark.parametrize('fault', ['unknown', 'linked_integer', 'linked_string', 'unequal_resolved'])
def test_project_validation_rejects_bad_new_leaves_and_linked_values_at_every_saved_depth(location, fault):
    state, ref, _, _, _ = fixture(recipe=None)
    asset = ref['asset_sha256']
    # Inheritance matters: no explicit face recipe can hide a broken resolved
    # linked pair behind individually valid scalar project records.
    state = P.set_override(state, 'all_people', asset, S.OP, '/left', .3)
    state = P.set_override(state, 'all_people', asset, S.OP, '/right', .3)
    if fault == 'unknown':
        state = P.set_override(state, 'face', ref['face_instance_id'], S.OP, '/reference_luminance', .5)
    elif fault == 'linked_integer':
        state = P.set_override(state, 'face', ref['face_instance_id'], S.OP, '/linked', 1)
    elif fault == 'linked_string':
        state = P.set_override(state, 'face', ref['face_instance_id'], S.OP, '/linked', 'true')
    else:
        state = P.set_override(state, 'face', ref['face_instance_id'], S.OP, '/right', .1)
    payload = project_tree(state, location)
    before = deepcopy(payload)
    with pytest.raises(ValueError):
        PROJECT.validate_records(payload)
    assert payload == before


def test_unresolved_new_operation_conflicts_remain_recoverable_but_cannot_render():
    state, ref, analysis, binding, original = fixture(recipe=None)
    for group, value in (('synthetic-brows-a', .2), ('synthetic-brows-b', .4)):
        state = LINKS.set_group(state, group, label=group, priority=1, face_ids=[ref['face_instance_id']])
        state = P.set_override(state, 'group', group, S.OP, '/left', value)
    resolution = RESOLVE.resolve(state, ref['face_instance_id'], A.defaults())
    assert any(conflict['operation_id'] == S.OP for conflict in resolution['conflicts'])
    payload = {'people_graph': state, 'undo': [{'_people_state': deepcopy(state)}]}
    before = deepcopy(payload)
    PROJECT.validate_records(payload)
    with patch.object(N, 'apply', side_effect=AssertionError('conflicting source reached native')) as native:
        with pytest.raises(ValueError):
            export(snapshot(state, ref, analysis, binding), original)
    native.assert_not_called()
    assert payload == before


@pytest.mark.parametrize('linked', [False, True])
def test_zero_strength_link_policy_needs_no_analysis_or_native_and_preserves_rgb16(linked):
    neutral = {'version': 1, 'linked': linked, 'left': 0., 'right': 0.}
    state, ref, _, _, original = fixture(recipe=neutral)
    frozen = SNAP.capture(state, ref['asset_sha256'], {})
    frozen.update(document_id=DOCUMENT, support_assets={})
    with patch.object(N, 'apply', side_effect=AssertionError('neutral reached native')) as native:
        prepared = export(frozen, original)
        assert LAYER.prepare(None, None, None, neutral, byte_budget=0) == []
    native.assert_not_called()
    assert prepared.effects == () and prepared.face_fields == ()
    assert not prepared.plan['entries'][0]['requires_analysis']
    np.testing.assert_array_equal(prepared.geometry.warp_original(original), original)


@pytest.mark.parametrize('linked', [False, True])
def test_empty_photo_all_people_link_policy_is_neutral_without_inventing_a_face(linked):
    _, _, _, binding, original = fixture(recipe=None)
    state = P.set_override(P.empty(), 'all_people', binding['sha256'], S.OP, '/linked', linked)
    frozen = SNAP.capture(state, binding['sha256'], {})
    frozen.update(document_id=DOCUMENT, support_assets={})
    with patch.object(N, 'apply', side_effect=AssertionError('empty neutral photograph reached native')) as native:
        prepared = export(frozen, original)
    native.assert_not_called()
    assert prepared.plan['entries'] == [] and prepared.face_fields == () and prepared.effects == ()
    assert prepared.geometry.face_ids == () and not state['faces']
    np.testing.assert_array_equal(prepared.geometry.warp_original(original), original)


@pytest.mark.parametrize('path,value', [('/linked', 1), ('/linked', 0), ('/linked', 'true'),
    ('/left', False), ('/right', True), ('/left', .1), ('/reference', .5)])
def test_empty_photo_rejects_nonzero_or_malformed_new_intent_despite_python_boolean_equality(path, value):
    _, _, _, binding, original = fixture(recipe=None)
    state = P.set_override(P.empty(), 'all_people', binding['sha256'], S.OP, path, value)
    frozen = SNAP.capture(state, binding['sha256'], {})
    frozen.update(document_id=DOCUMENT, support_assets={})
    with patch.object(N, 'apply', side_effect=AssertionError('invalid empty photograph reached native')) as native:
        with pytest.raises(ValueError):
            export(frozen, original)
    native.assert_not_called()
    assert EXPORT.fastpath_blocker(frozen)


@pytest.mark.parametrize('recipe', [ACTIVE, UNLINKED, {'version': 1, 'linked': False, 'left': .3, 'right': 0.}])
def test_rgb16_and_derived_float_export_rebuild_same_source_layer_without_geometry(recipe):
    state, ref, analysis, binding, original = fixture(recipe=recipe)
    before, pixels = deepcopy(state), original.copy()
    working = original.astype(np.float32)/65535.
    frozen = snapshot(state, ref, analysis, binding)
    calls = []
    with patch.object(N, 'apply', side_effect=native_double(calls)):
        old = export(frozen, original)
        new = export({**frozen, 'creative_source': binding}, working)
    first, second = assert_prepared(old, ref, working.shape[:2]), assert_prepared(new, ref, working.shape[:2])
    assert calls and first is not second and not np.shares_memory(first.delta, second.delta)
    assert first.window == second.window
    np.testing.assert_array_equal(first.delta, second.delta)
    np.testing.assert_array_equal(old.geometry.delta, new.geometry.delta)
    old_output, _ = old.apply_source_stage('brow_enhance', working)
    new_output, _ = new.apply_source_stage('brow_enhance', working)
    np.testing.assert_array_equal(old_output, new_output)
    assert np.any(new_output != working)
    np.testing.assert_allclose(new.geometry.warp(new_output), new_output, rtol=0, atol=2e-6)
    assert state == before and frozen['state'] == before
    np.testing.assert_array_equal(original, pixels)


@pytest.mark.parametrize('fault', ['missing', 'landmark_digest', 'foreign_face', 'face_skin',
                                  'observation', 'occluded', 'flat_source', 'black_source'])
def test_invalid_source_support_refuses_before_native_without_publishing_a_partial_face(fault):
    state, ref, analysis, binding, original = fixture()
    before = deepcopy(state)
    if fault == 'landmark_digest': analysis['landmarks'][0, 0] += np.float32(.001)
    elif fault == 'foreign_face': analysis['face_ref']['asset_sha256'] = 'f'*64
    elif fault == 'face_skin': analysis['face_skin'] = analysis['face_skin_observation'] = None
    elif fault == 'observation': analysis['face_skin_observation']['source_sha256'] = 'f'*64
    elif fault == 'occluded': analysis['excluded'][:] = 1
    elif fault == 'flat_source': original[:] = 32000
    elif fault == 'black_source': original[:] = 0
    saved = original.copy()
    with patch.object(N, 'apply', side_effect=AssertionError('unadmitted source reached native')) as native:
        with pytest.raises(ValueError):
            frozen = SNAP.capture(state, ref['asset_sha256'], {} if fault == 'missing' else {ref['face_instance_id']: analysis})
            frozen.update(document_id=DOCUMENT, support_assets={})
            export(frozen, original)
    native.assert_not_called()
    assert state == before
    np.testing.assert_array_equal(original, saved)


@pytest.mark.parametrize('derived', [False, True])
@pytest.mark.parametrize('fault', ['document', 'dtype', 'alpha', 'budget'])
def test_export_owner_rgb_dtype_alpha_and_budget_are_checked_before_native(derived, fault):
    state, ref, analysis, binding, original = fixture()
    frozen = snapshot(state, ref, analysis, binding, derived=derived)
    source = original.astype(np.float32)/65535. if derived else original
    budget = BUDGET
    if fault == 'document': frozen['document_id'] = 'different-owner'
    elif fault == 'dtype': source = original if derived else original.astype(np.float32)/65535.
    elif fault == 'alpha': source = np.concatenate((source, np.ones_like(source[..., :1])), axis=2)
    else: budget = 1
    with patch.object(N, 'apply', side_effect=AssertionError('invalid export reached native')) as native:
        with pytest.raises(ValueError):
            ENGINE.prepare_export(frozen, source, None, byte_budget=budget, document_id=DOCUMENT)
    native.assert_not_called()


def test_original_and_derived_preview_prepare_use_their_current_owned_rgb():
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding, original = fixture()
    proxy = (original//257).astype(np.uint8)
    working = proxy.astype(np.float32)/255.
    pipe = SimpleNamespace(src_f32=torch.from_numpy(working.copy()).permute(2, 0, 1)[None],
                           repair_base=None, repair_ops=[], redo_ops=[])
    proof = REPLAY.make_evidence(binding, working, None, REPAIRS.digest_ops([], [], binding))
    pipe._creative_repair_source = deepcopy(binding)
    pipe._creative_repair_input = deepcopy(proof['input'])
    pipe._creative_repair_evidence = proof
    calls = []
    with patch.object(N, 'apply', side_effect=native_double(calls)):
        old = ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                                     byte_budget=BUDGET, document_id=DOCUMENT)
        new = ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                                     byte_budget=BUDGET, document_id=DOCUMENT,
                                     creative_source=binding, creative_proxy=proxy)
    first, second = assert_prepared(old, ref, working.shape[:2]), assert_prepared(new, ref, working.shape[:2])
    assert first.window == second.window and calls
    np.testing.assert_array_equal(first.delta, second.delta)
    np.testing.assert_array_equal(pipe.src_f32[0].permute(1, 2, 0).numpy(), working)
    assert REPLAY.verify_pipeline(pipe, binding) == proof


@pytest.mark.parametrize('fault', ['missing', 'input', 'source'])
def test_derived_repaired_source_requires_its_real_replay_proof_before_native(fault):
    state, ref, analysis, binding, original = fixture()
    source = original.astype(np.float32)/65535.
    repaired = source*np.float32(.98)
    frozen = snapshot(state, ref, analysis, binding, derived=True)
    proof = REPLAY.make_evidence(binding, source, repaired, REPAIRS.digest_ops([], [], binding))
    if fault == 'missing': proof = None
    elif fault == 'input': proof['input']['sha256'] = 'e'*64
    else: proof['source']['sha256'] = 'e'*64
    with patch.object(N, 'apply', side_effect=AssertionError('unverified repair reached native')) as native:
        with pytest.raises(ValueError):
            export(frozen, source, repaired, creative_repair_evidence=proof)
    native.assert_not_called()


def test_valid_derived_repair_rebuilds_effect_from_repaired_current_source_not_original_delta():
    state, ref, analysis, binding, original = fixture()
    source = original.astype(np.float32)/65535.
    repaired = source*np.float32(.97)
    frozen = snapshot(state, ref, analysis, binding, derived=True)
    proof = REPLAY.make_evidence(binding, source, repaired, REPAIRS.digest_ops([], [], binding))
    calls = []
    with patch.object(N, 'apply', side_effect=native_double(calls)):
        old = export(frozen, source)
        new = export(frozen, source, repaired, creative_repair_evidence=proof)
    old_record = assert_prepared(old, ref, source.shape[:2])
    new_record = assert_prepared(new, ref, source.shape[:2])
    assert old_record.window == new_record.window
    assert not np.array_equal(old_record.delta, new_record.delta)
    assert len(calls) == 4  # Both requested sides independently rebuilt twice.
    for old_call, new_call in zip(calls[:2], calls[2:]):
        np.testing.assert_allclose(new_call['source'], old_call['source']*.97, rtol=0, atol=1e-7)
    assert REPLAY.verify_evidence(proof, binding, source, repaired) == proof


@pytest.mark.parametrize('derived', [False, True])
def test_original_size_export_rebuilds_support_from_retained_normalized_observations(derived):
    state, ref, analysis, binding, original = fixture(size=320)
    # Retain a smaller actual synthetic producer grid. This resampling fixture
    # does not assert higher-resolution semantic information has been inferred.
    producer = 160
    for key in ('excluded', 'skin', 'face_skin'):
        analysis[key] = np.array(analysis[key][::2, ::2], dtype=np.float32, copy=True)
    analysis['face_skin_observation'].update(producer_width=producer, producer_height=producer)
    frozen = snapshot(state, ref, analysis, binding, derived=derived)
    source = original.astype(np.float32)/65535. if derived else original
    calls = []
    with patch.object(N, 'apply', side_effect=native_double(calls)):
        prepared = export(frozen, source)
    record = assert_prepared(prepared, ref, (320, 320))
    assert calls and max(record.window[2:]) > 0
    retained = frozen['analyses'][ref['face_instance_id']]
    assert retained['face_skin'].shape == (producer, producer)
    assert retained['face_skin_observation']['producer_width'] == producer
    assert analysis['evidence']['source_width'] == 320
    assert not np.shares_memory(record.delta, original)


@pytest.mark.parametrize('amount', [.45, -.45])
def test_real_cpu_and_tensor_stage_use_one_common_upstream_headroom_scalar(amount):
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding, original = fixture(recipe={**ACTIVE, 'left': amount, 'right': amount})
    working = original.astype(np.float32)/65535.
    calls = []
    with patch.object(N, 'apply', side_effect=native_double(calls)):
        prepared = export(snapshot(state, ref, analysis, binding), original)
    record = assert_prepared(prepared, ref, working.shape[:2])
    count = len(calls)
    y, x, h, w = record.window
    full_delta = np.zeros_like(working)
    full_delta[y:y+h, x:x+w] = record.delta
    active = np.any(full_delta != 0, axis=2)
    upstream = working.copy()
    upstream[active] = [.001, .4, .8] if amount > 0 else [.999, .6, .2]
    before = upstream.copy()
    cpu, facts = prepared.apply_source_stage('brow_enhance', upstream)
    assert facts['overlap_pixels'] == 0 and np.any(cpu != upstream)
    assert np.all((cpu >= 0) & (cpu <= 1))
    assert not np.array_equal(cpu, np.clip(upstream+full_delta, 0, 1))
    usable = active & np.all(full_delta != 0, axis=2)
    gains = (cpu[usable]-upstream[usable])/full_delta[usable]
    # Dividing a float32 subtraction by a tiny encoded delta magnifies its
    # rounding. This checks common scalar feasibility, not a bit-exact ratio.
    np.testing.assert_allclose(gains, np.repeat(gains[:, :1], 3, axis=1), rtol=0, atol=2e-4)
    assert np.any((gains > 0) & (gains < 1))
    pipe = SimpleNamespace(h=working.shape[0], w=working.shape[1], device='cpu', high_precision_warp=False)
    PIPE.install(pipe, prepared)
    pixels = torch.from_numpy(upstream.copy()).permute(2, 0, 1)[None]
    actual = PIPE.source_effect(pipe, 'brow_enhance', pixels)
    np.testing.assert_allclose(actual[0].permute(1, 2, 0).numpy(), cpu, rtol=0, atol=1e-7)
    # The common geometry sampler is still one installed unchanged map. This
    # tests source-stage routing, not the complete color/export encode pipeline.
    sampled = PIPE.warp(pipe, actual)
    np.testing.assert_allclose(sampled[0].permute(1, 2, 0).numpy(), cpu, rtol=0, atol=2e-6)
    assert len(calls) == count
    np.testing.assert_array_equal(upstream, before)


def test_full_frame_and_tile_source_composition_share_the_same_prepared_layer():
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding, original = fixture(recipe=UNLINKED)
    working = original.astype(np.float32)/65535.
    calls = []
    with patch.object(N, 'apply', side_effect=native_double(calls)):
        prepared = export(snapshot(state, ref, analysis, binding), original)
    assert_prepared(prepared, ref, working.shape[:2])
    count = len(calls)
    height, width = working.shape[:2]
    pixels = torch.from_numpy(working.copy()).permute(2, 0, 1)[None]
    full = SimpleNamespace(h=height, w=width, device='cpu', high_precision_warp=False)
    PIPE.install(full, prepared)
    expected = PIPE.source_effect(full, 'brow_enhance', pixels)
    chunks = []
    for y0, y1 in ((0, height//2), (height//2, height)):
        tile = SimpleNamespace(h=y1-y0, w=width, device='cpu', high_precision_warp=False)
        PIPE.install(tile, prepared, origin=(y0, 0))
        chunks.append(PIPE.source_effect(tile, 'brow_enhance', pixels[:, :, y0:y1]))
        assert tile.people_prepared is prepared
    assert torch.equal(torch.cat(chunks, dim=2), expected)
    assert len(calls) == count  # No anatomy/contrast is rerun for an export tile.


@pytest.mark.parametrize('bad', [-.01, 1.01, float('nan'), float('inf')])
def test_actual_active_source_stage_rejects_hdr_or_invalid_upstream_without_clipping(bad):
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding, original = fixture()
    source = original.astype(np.float32)/65535.
    with patch.object(N, 'apply', side_effect=native_double([])):
        prepared = export(snapshot(state, ref, analysis, binding), original)
    record = assert_prepared(prepared, ref, source.shape[:2])
    y, x, _, _ = record.window
    dy, dx = np.argwhere(np.any(record.delta != 0, axis=2))[0]
    upstream = source.copy()
    upstream[y+dy, x+dx, 0] = bad
    with pytest.raises(ValueError):
        prepared.apply_source_stage('brow_enhance', upstream)
    pipe = SimpleNamespace(h=source.shape[0], w=source.shape[1], device='cpu', high_precision_warp=False)
    PIPE.install(pipe, prepared)
    with pytest.raises(ValueError):
        PIPE.source_effect(pipe, 'brow_enhance', torch.from_numpy(upstream).permute(2, 0, 1)[None])


def test_composition_exact_zero_preserves_object_and_bits_without_claiming_physical_hue():
    from lumaretouch_engine import brow_enhance_composition as COMPOSE
    source = np.array([[[-0., .4, 1.]]], dtype=np.float32)
    assert COMPOSE.apply_np(source, np.zeros_like(source)) is source
    np.testing.assert_array_equal(COMPOSE.apply_np(source, np.zeros_like(source)).view(np.uint32), source.view(np.uint32))
    with pytest.raises(ValueError):
        COMPOSE.apply_np(np.ones((1, 1, 4), np.float32), np.zeros((1, 1, 4), np.float32))
    with pytest.raises(ValueError):
        COMPOSE.apply_np(source.astype(np.float64), np.zeros_like(source, dtype=np.float64))
    torch = pytest.importorskip('torch')
    pixels = torch.from_numpy(source).permute(2, 0, 1)[None]
    assert COMPOSE.apply_t(pixels, torch.zeros_like(pixels)) is pixels


def test_original_shared_person_rebuilds_each_targets_own_support_and_source_samples():
    targets = [fixture(recipe=None, asset='a'*64, size=256),
               fixture(recipe=None, asset='f'*64, size=320, tone=.025)]
    state = P.empty()
    for own, _, _, _, _ in targets:
        state['faces'].update(deepcopy(own['faces']))
    state, person = LINKS.create_person(state)
    for _, ref, _, _, _ in targets:
        state = LINKS.set_link(state, ref['face_instance_id'], person, 'confirmed', user_confirmed=True)
    edit = command(state, targets[0][1], UNLINKED)
    edit['target'] = {'scope': 'person', 'target_id': person, 'face_ref': None}
    before = deepcopy(state)
    candidate = stage(edit, state, targets[0][1])['state']
    assert affected_assets(state, candidate) == {'a'*64, 'f'*64}
    rows = [row for row in candidate['overrides'] if row['operation_id'] == S.OP]
    assert len(rows) == 3 and all(row['scope'] == 'person' for row in rows)
    assert {row['parameter_path'] for row in rows} == LEAVES
    observed, records = [], []
    for _, ref, analysis, binding, original in targets:
        assert resolved(candidate, ref)[S.OP] == UNLINKED
        calls = []
        with patch.object(N, 'apply', side_effect=native_double(calls)):
            prepared = export(snapshot(candidate, ref, analysis, binding), original)
        records.append(assert_prepared(prepared, ref, original.shape[:2]))
        observed.append(calls)
        assert calls and candidate['faces'][ref['face_instance_id']]['local_assets'] == {}
        assert snapshot(candidate, ref, analysis, binding)['support_assets'] == {}
    assert observed[0][0]['source'].shape != observed[1][0]['source'].shape
    for first in observed[0]:
        for second in observed[1]:
            for key in ('source', 'coverage', 'reference'):
                assert not np.shares_memory(first[key], second[key])
    assert not np.shares_memory(records[0].delta, records[1].delta)
    assert state == before


def test_reviewed_derived_replica_capsules_transport_only_three_scalar_leaves():
    targets = [fixture(recipe=None, asset='a'*64), fixture(recipe=None, asset='f'*64, tone=.025)]
    documents = ('synthetic-derived-brow-a', 'synthetic-derived-brow-b')
    members = [{'document_id': document, 'scope_id': document,
                'original_sha256': ('1' if index == 0 else '2')*64, 'ref': deepcopy(target[1])}
               for index, (document, target) in enumerate(zip(documents, targets))]
    intent = [{'op': S.OP, 'path': path, 'value': value} for path, value in A.leaves(UNLINKED).items()]
    results, capsules = [], []
    for document, (state, ref, analysis, binding, original) in zip(documents, targets):
        capsule = CROSS.descriptor('synthetic-reviewed-brows', document, members, intent)
        candidate = CROSS.create(state, 'synthetic-person', capsule)
        DERIVED.require_graph(candidate, binding, document_id=document)
        frozen = snapshot(candidate, ref, analysis, binding, derived=True)
        frozen['document_id'] = document
        calls = []
        with patch.object(N, 'apply', side_effect=native_double(calls)):
            prepared = ENGINE.prepare_export(frozen, original.astype(np.float32)/65535., None,
                                            byte_budget=BUDGET, document_id=document)
        results.append(assert_prepared(prepared, ref, original.shape[:2]))
        capsules.append(capsule)
        assert calls and candidate['faces'] == state['faces']
        assert capsule['intent'] == sorted(intent, key=lambda row: (row['op'], row['path']))
    assert capsules[0]['generation'] == capsules[1]['generation']
    assert not np.array_equal(results[0].delta, results[1].delta)
    assert not np.shares_memory(results[0].delta, results[1].delta)


@pytest.mark.parametrize('failure', ['preparation', 'second_side_native', 'publication'])
def test_real_host_failure_restores_graph_and_history_without_rewinding_owner_fence(failure):
    """Real host stage/publication with explicit minimal non-product host IO."""
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
            raise ValueError('synthetic brow publication refusal')
    engine._people_prepare_graph = prepare
    engine._people_sync = sync
    engine._people_publish_graph = lambda candidate, assets: PeopleHostMixin._people_publish_graph(engine, candidate, assets)
    action = RuntimeError('synthetic brow native refusal') if failure == 'preparation' else native_double([])
    if failure == 'second_side_native':
        first_side = native_double([])
        side_calls = []
        def second_side_refusal(*args, **kwargs):
            side_calls.append(1)
            if len(side_calls) == 2:
                raise RuntimeError('synthetic second-side native refusal')
            return first_side(*args, **kwargs)
        action = second_side_refusal
    with patch.object(N, 'apply', side_effect=action), pytest.raises(ValueError, match='synthetic'):
        HOST.apply(engine, {'cmd': 'people', **edit}, events.append)
    assert not events and state == before and history == history_before
    assert engine._people_receipts[edit['request_id']]['success'] is False
    current = owner.snapshot()
    assert current['overrides'] == before['overrides'] and current['faces'] == before['faces']
    assert resolved(current, ref)[S.OP] == S.neutral()
    if failure in ('preparation', 'second_side_native'):
        assert not prepared and not syncs and owner.fence == 0
        if failure == 'second_side_native':
            assert len(side_calls) == 2
    else:
        assert len(prepared) == 1 and len(syncs) == 2 and owner.fence == 2
        assert resolved(syncs[0], ref)[S.OP] == ACTIVE
        assert resolved(syncs[1], ref)[S.OP] == S.neutral() and engine._people_staged is None


def test_all_mock_patches_stay_at_the_declared_native_boundary():
    tree = ast.parse(Path(__file__).read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
             and node.func.value.id == 'patch' and node.func.attr == 'object']
    assert calls
    for call in calls:
        assert isinstance(call.args[0], ast.Name) and call.args[0].id == 'N'
        assert isinstance(call.args[1], ast.Constant) and call.args[1].value in ('available', 'apply')


def test_source_wiring_is_before_added_brow_material_and_does_not_add_geometry_sampler():
    source = (ROOT/'engine/src/lumaretouch_engine/vram.py').read_text()
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
             and node.func.value.id == 'PEOPLE_PIPE' and node.func.attr == 'source_effect']
    positions = {}
    for call in calls:
        if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
            positions.setdefault(call.args[1].value, []).append(call.lineno)
    assert len(positions['brow_enhance']) == len(positions['brow_makeup']) == 1
    assert positions['brow_enhance'][0] < positions['brow_makeup'][0]
    assert S.OP not in A.GEOMETRY
    renderer = (ROOT/'engine/src/lumaretouch_engine/people_render_runtime.py').read_text()
    assert 'from .brow_enhance_layer import prepare as prepare_brow_enhance' in renderer
    assert "mouth = field.fields[3]" in renderer
    assert EFFECTS.STAGES.index('brow_enhance') < EFFECTS.STAGES.index('brow_makeup')
