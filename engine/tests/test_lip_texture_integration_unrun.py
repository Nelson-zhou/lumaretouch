# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: partial original-lip dark-furrow people integration.

LNX-REF-PC-32464-C-b6315c40ca is NOT full dry-flake/crack reconstruction.
All images, landmarks and model identities are explicitly synthetic fixtures,
not inference, photographic acceptance or native-kernel correctness evidence.
Only lip_texture_native.available/apply are doubled. Positive source admission,
anatomical/semantic support, owner, history, preparation and composition are real.
No local import, product execution, test collection/run, build, typecheck,
inference or download was performed while authoring this file.

The native double leaves a source-dependent routing mark inside admitted
coverage. It deliberately does not reimplement the Rust furrow classifier.
Every canonical full source below has the dimensions declared by its evidence;
smaller semantic/preview grids never masquerade as full-resolution sources.
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

from test_lip_texture_support_unrun import synthetic_observation

from lumaretouch_engine import lip_texture_state as S, lip_texture_native as N
from lumaretouch_engine import lip_texture_layer as LAYER, lip_texture_project as GATE
from lumaretouch_engine import lip_makeup_state as MAKEUP, mouth_shape_state as MOUTH
from lumaretouch_engine import people_algorithms as A, people_state as P
from lumaretouch_engine import people_resolver as RESOLVE, people_associations as LINKS
from lumaretouch_engine import people_cross_owner as CROSS, people_project as PROJECT
from lumaretouch_engine import people_snapshot as SNAP, people_export as EXPORT
from lumaretouch_engine import people_engine_runtime as ENGINE, people_pipeline as PIPE
from lumaretouch_engine import people_effects as EFFECTS, people_edit as EDIT
from lumaretouch_engine import people_host_commands as HOST, people_document_history as HISTORY
from lumaretouch_engine.people_host import PeopleHostMixin
from lumaretouch_engine.people_graph_owner import PeopleGraphOwner, affected_assets
from lumaretouch_engine.people_geometry import CombinedGeometry, FaceGeometry
from lumaretouch_engine import creative_derived_effects as DERIVED
from lumaretouch_engine import creative_derived_repairs as REPAIRS
from lumaretouch_engine import creative_derived_repair_runtime as REPLAY

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = 'synthetic-lip-furrow-document'
BUDGET = 512 * 1024**2
ACTIVE = {'version': 1, 'amount': .65}
LEAVES = {'/amount'}


@pytest.fixture(autouse=True)
def named_native_availability_double():
    """Capability seam only; this does not claim a real shared library loaded."""
    with patch.object(N, 'available', return_value=True):
        yield


def set_recipe(state, ref, recipe, operation=None):
    for path, value in A.leaves(recipe).items():
        state = P.set_override(state, 'face', ref['face_instance_id'], operation or S.OP, path, value)
    return state


def fixture(*, recipe=ACTIVE, asset='a'*64, size=256, tone=0.):
    """Create one full-source fixture and independently owned durable FaceRef."""
    _, analysis, source = synthetic_observation(size=size)
    analysis = deepcopy(analysis)
    source = np.array(source, dtype=np.float32, copy=True)
    if tone:
        source += np.float32(tone)
    assert np.isfinite(source).all() and np.all((source >= 0) & (source <= 1))
    assert source.shape == (size, size, 3)
    evidence = deepcopy(analysis['evidence'])
    evidence.update(source_width=size, source_height=size)
    analysis['evidence'] = deepcopy(evidence)
    face = P.new_face(asset, [.03, .03, .97, .97], evidence)
    state = P.empty()
    state['faces'][face['face_instance_id']] = face
    ref = P.face_ref(face)
    analysis['face_ref'] = deepcopy(ref)
    for key in ('face_skin_observation', 'body_skin_observation'):
        if analysis.get(key) is not None:
            analysis[key]['source_sha256'] = asset
    if recipe is not None:
        state = set_recipe(state, ref, recipe)
    original = np.rint(source.astype(np.float64)*65535.).astype(np.uint16)
    return state, ref, analysis, {'sha256': asset, 'width': size, 'height': size}, original


def resolved(state, ref):
    return A.recipes(RESOLVE.resolve(state, ref['face_instance_id'], A.defaults()))


def command(state, ref, recipe, *, unset=False):
    patches = [{'operation_id': S.OP, 'parameter_path': path, 'unset': unset,
                **({} if unset else {'value': value})}
               for path, value in A.leaves(recipe).items()]
    return {'document_id': DOCUMENT, 'document_epoch': 'synthetic-epoch', 'document_revision': 7,
            'state_revision': state['revision'], 'association_revision': state['association_revision'],
            'request_id': 'synthetic-lip-furrow-request', 'action': 'patch',
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
    """Bounded source-dependent RGB-gain routing double, not furrow detection."""
    def apply(source, coverage, amount, *, across, radius, cancelled=None):
        assert source.dtype == coverage.dtype == np.float32
        assert source.shape[:2] == coverage.shape and source.shape[2] == 3
        assert not source.flags.writeable and not coverage.flags.writeable
        assert np.any(coverage > 0) and np.all((coverage >= 0) & (coverage <= 1))
        axis = np.asarray(across, np.float32)
        assert axis.shape == (2,) and np.isfinite(axis).all()
        np.testing.assert_allclose(np.linalg.norm(axis), 1, rtol=0, atol=1e-5)
        assert type(radius) is int and 1 <= radius <= 128
        assert type(amount) in (int, float) and 0 < amount <= 1
        eligible = LAYER._full_support(coverage, radius)
        assert np.any(eligible)
        if cancelled is not None and cancelled():
            raise RuntimeError('synthetic native cancellation')
        calls.append({'source': source.copy(), 'coverage': coverage.copy(),
                      'across': axis.copy(), 'radius': radius, 'amount': amount})
        linear = np.where(source <= .04045, source/12.92, ((source+.055)/1.055)**2.4)
        mean = np.float32(np.mean(source[coverage > 0], dtype=np.float64))
        gain = 1 + np.float32(amount)*(.06 + .02*mean)*coverage
        corrected = linear*gain[..., None]
        encoded = np.where(corrected <= .0031308, corrected*12.92, 1.055*corrected**(1/2.4)-.055)
        return np.array(np.where(eligible[..., None], encoded, source), dtype=np.float32, copy=True)
    return apply


def assert_prepared(prepared, ref, shape):
    assert type(prepared.geometry) is CombinedGeometry
    assert prepared.geometry.delta.shape == (1, *shape, 2)
    assert prepared.geometry.face_ids == (ref['face_instance_id'],)
    assert not prepared.geometry.delta.flags.writeable and not np.any(prepared.geometry.delta)
    assert len(prepared.face_fields) == 1
    face = prepared.face_fields[0]
    assert type(face) is FaceGeometry and face.fields == (None,)*4
    assert not face.automatic.units
    assert prepared.plan['sample_policy'] == 'one_original_source_sample_after_composed_field'
    assert len(prepared.effects) == 1
    record = prepared.effects[0]
    assert record.stage == 'lip_texture' and record.face_ref == ref
    assert record.delta.dtype == np.float32 and not record.delta.flags.writeable
    assert np.isfinite(record.delta).all() and np.any(record.delta != 0)
    assert record.weights is None and record.amounts is None
    return record


def expanded(record, shape):
    result = np.zeros(shape, np.float32)
    y, x, h, w = record.window
    result[y:y+h, x:x+w] = record.delta
    return result


def test_new_operation_is_scalar_only_independent_and_partial_reference_not_lip_material():
    assert S.OP == 'lnx.lip_texture.v1' and S.OP not in A.GEOMETRY
    assert S.OP != A.LIP and S.OP != A.LIPSTICK.OP and S.OP in DERIVED.OPERATIONS
    assert A.defaults()[S.OP] == {'/amount': 0.}
    assert set(A.leaves(ACTIVE)) == LEAVES
    assert S.CONTROL_ID == 'LNX-REF-PC-32464-C-b6315c40ca'
    DERIVED._leaf(S.OP, '/amount', .65)
    state, ref, _, _, _ = fixture(recipe=None)
    DERIVED._patches(command(state, ref, ACTIVE)['payload'])
    registry = json.loads((ROOT/'docs/p0/registry-extensions.json').read_text())
    row = next(item for item in registry['entries'] if item['operation_id'] == S.OP)
    assert row['source_requirement'] == 'PC-32464-C-b6315c40ca'


@pytest.mark.parametrize('path,value', [('/amount', False), ('/amount', True),
    ('/amount', '0.65'), ('/amount', -.01), ('/amount', 1.01),
    ('/amount', float('nan')), ('/amount', float('inf')), ('/version', 1),
    ('/mask', []), ('/source_sha256', 'a'*64), ('/landmarks', []),
    ('/lipstick_review', {}), ('/cached_rgb', []), ('/flakes', .5)])
def test_derived_transport_refuses_coercion_source_support_and_unimplemented_reconstruction(path, value):
    with pytest.raises(ValueError):
        DERIVED._leaf(S.OP, path, value)
    with pytest.raises(ValueError):
        GATE.validate_leaf(path, value)


def test_history_undo_redo_reset_and_inherit_preserve_independent_lip_and_mouth_intent():
    state, ref, _, _, _ = fixture(recipe=S.neutral())
    makeup = {**MAKEUP.neutral(), 'brightness': .2, 'saturation': -.1}
    mouth = MOUTH.adjust(MOUTH.neutral(), 'width', .1)
    state = set_recipe(state, ref, makeup, A.LIP)
    state = set_recipe(state, ref, mouth, A.GEOMETRY[3])
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
    for operation, expected in ((S.OP, S.neutral()), (A.LIP, makeup), (A.GEOMETRY[3], mouth)):
        assert resolved(reset, ref)[operation] == expected
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
@pytest.mark.parametrize('path,value', [('/amount', False), ('/amount', True),
    ('/amount', '0'), ('/amount', -.01), ('/amount', 1.01),
    ('/version', 1), ('/source_sha256', 'a'*64), ('/crack_fill', .5)])
def test_project_gate_checks_every_saved_depth_even_empty_or_neutral_equal_boolean_intent(location, with_face, path, value):
    state, ref, _, binding, _ = fixture(recipe=None)
    if not with_face:
        state = P.empty()
    state = P.set_override(state, 'all_people', binding['sha256'], S.OP, path, value)
    payload = project_tree(state, location)
    before = deepcopy(payload)
    with pytest.raises(ValueError):
        PROJECT.validate_records(payload)
    assert payload == before


def test_project_round_trip_keeps_only_scalar_intent_and_snapshot_owns_observations():
    state, ref, analysis, binding, _ = fixture()
    payload = {'people_graph': state, 'undo': [{'_people_state': set_recipe(state, ref, S.neutral())}]}
    restored = json.loads(json.dumps(payload, sort_keys=True, allow_nan=False))
    PROJECT.validate_records(restored)
    assert restored == payload and resolved(restored['people_graph'], ref)[S.OP] == ACTIVE
    assert state['faces'][ref['face_instance_id']]['local_assets'] == {}
    leaves = [row for row in restored['people_graph']['overrides'] if row['operation_id'] == S.OP]
    assert len(leaves) == 1 and leaves[0]['parameter_path'] == '/amount'
    assert type(leaves[0]['value']) is float
    frozen = snapshot(state, ref, analysis, binding)
    assert frozen['support_assets'] == {} and EXPORT.fastpath_blocker(frozen)
    retained = frozen['analyses'][ref['face_instance_id']]
    for key in ('landmarks', 'excluded', 'skin', 'face_skin'):
        if analysis.get(key) is not None:
            assert not retained[key].flags.writeable
            assert not np.shares_memory(retained[key], analysis[key])


def test_unresolved_scalar_inheritance_conflicts_remain_recoverable_but_cannot_render():
    state, ref, analysis, binding, original = fixture(recipe=None)
    for group, value in (('synthetic-lips-a', .2), ('synthetic-lips-b', .4)):
        state = LINKS.set_group(state, group, label=group, priority=1, face_ids=[ref['face_instance_id']])
        state = P.set_override(state, 'group', group, S.OP, '/amount', value)
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


@pytest.mark.parametrize('empty_photo', [False, True])
def test_exact_zero_needs_no_analysis_or_native_and_preserves_canonical_rgb16(empty_photo):
    state, ref, _, binding, original = fixture(recipe=S.neutral())
    if empty_photo:
        state = P.set_override(P.empty(), 'all_people', binding['sha256'], S.OP, '/amount', 0.)
    frozen = SNAP.capture(state, binding['sha256'], {})
    frozen.update(document_id=DOCUMENT, support_assets={})
    with patch.object(N, 'available', side_effect=AssertionError('neutral probed native')) as available:
        with patch.object(N, 'apply', side_effect=AssertionError('neutral reached native')) as native:
            prepared = export(frozen, original)
            assert LAYER.prepare(None, None, None, S.neutral(), byte_budget=0) == []
    available.assert_not_called()
    native.assert_not_called()
    assert prepared.effects == () and prepared.face_fields == ()
    assert not any(entry['requires_analysis'] for entry in prepared.plan['entries'])
    assert not EXPORT.fastpath_blocker(frozen)
    if empty_photo:
        assert prepared.plan['entries'] == [] and prepared.geometry.face_ids == ()
    np.testing.assert_array_equal(prepared.geometry.warp_original(original), original)


@pytest.mark.parametrize('with_face', [False, True])
@pytest.mark.parametrize('path,value', [('/amount', False), ('/amount', True),
    ('/amount', '0'), ('/amount', .1), ('/reference', .5)])
def test_invalid_boolean_and_nonzero_intent_cannot_hide_behind_neutral_fastpath_or_absent_analysis(with_face, path, value):
    state, ref, _, binding, original = fixture(recipe=None)
    if not with_face:
        state = P.empty()
    state = P.set_override(state, 'all_people', binding['sha256'], S.OP, path, value)
    frozen = SNAP.capture(state, binding['sha256'], {})
    frozen.update(document_id=DOCUMENT, support_assets={})
    assert EXPORT.fastpath_blocker(frozen)
    with patch.object(N, 'apply', side_effect=AssertionError('invalid source reached native')) as native:
        with pytest.raises(ValueError):
            export(frozen, original)
    native.assert_not_called()


@pytest.mark.parametrize('amount', [.2, .65, 1.])
def test_rgb16_and_derived_float_export_rebuild_identical_current_source_layers(amount):
    state, ref, analysis, binding, original = fixture(recipe={'version': 1, 'amount': amount})
    before, pixels = deepcopy(state), original.copy()
    working = original.astype(np.float32)/65535.
    frozen = snapshot(state, ref, analysis, binding)
    calls = []
    with patch.object(N, 'apply', side_effect=native_double(calls)):
        old = export(frozen, original)
        new = export({**frozen, 'creative_source': binding}, working)
    first = assert_prepared(old, ref, working.shape[:2])
    second = assert_prepared(new, ref, working.shape[:2])
    assert len(calls) == 2 and first is not second
    assert first.window == second.window and not np.shares_memory(first.delta, second.delta)
    np.testing.assert_array_equal(first.delta, second.delta)
    np.testing.assert_array_equal(calls[0]['source'], calls[1]['source'])
    old_output, _ = old.apply_source_stage('lip_texture', working)
    new_output, _ = new.apply_source_stage('lip_texture', working)
    np.testing.assert_array_equal(old_output, new_output)
    assert np.any(new_output != working)
    np.testing.assert_allclose(new.geometry.warp(new_output), new_output, rtol=0, atol=2e-6)
    assert state == before and frozen['state'] == before
    np.testing.assert_array_equal(original, pixels)


@pytest.mark.parametrize('fault', ['missing', 'landmark_digest', 'foreign_ref', 'revision',
                                  'excluded', 'semantic_model', 'occluded', 'black_source'])
def test_invalid_retained_source_support_refuses_before_native_without_partial_publication(fault):
    state, ref, analysis, binding, original = fixture()
    before = deepcopy(state)
    if fault == 'landmark_digest': analysis['landmarks'][0, 0] += np.float32(.001)
    elif fault == 'foreign_ref': analysis['face_ref']['asset_sha256'] = 'f'*64
    elif fault == 'revision': analysis['face_ref']['analysis_revision'] += 1
    elif fault == 'excluded': analysis['excluded'] = None
    elif fault == 'semantic_model': analysis['evidence']['semantic_model_sha256'] = 'e'*64
    elif fault == 'occluded': analysis['excluded'][:] = 1
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
def test_export_owner_dtype_alpha_and_budget_refuse_before_native(derived, fault):
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


@pytest.mark.parametrize('fault', ['source_identity', 'full_source_extent', 'observation_extent'])
def test_derived_canonical_source_binding_cannot_borrow_foreign_owner_or_proxy_extent(fault):
    state, ref, analysis, binding, original = fixture()
    frozen = snapshot(state, ref, analysis, binding, derived=True)
    source = original.astype(np.float32)/65535.
    if fault == 'source_identity': frozen['creative_source']['sha256'] = 'f'*64
    elif fault == 'full_source_extent': source = source[::2, ::2].copy()
    else:
        frozen['state']['faces'][ref['face_instance_id']]['evidence']['source_width'] += 1
    with patch.object(N, 'apply', side_effect=AssertionError('foreign binding reached native')) as native:
        with pytest.raises(ValueError):
            export(frozen, source)
    native.assert_not_called()


def proxy_analysis(analysis, stride):
    """Retain observed normalized landmarks; only copy existing semantic grids."""
    value = deepcopy(analysis)
    for key in ('excluded', 'skin', 'face_skin', 'body_skin'):
        if value.get(key) is not None:
            value[key] = np.array(value[key][::stride, ::stride], dtype=np.float32, copy=True)
    for key in ('face_skin_observation', 'body_skin_observation'):
        if value.get(key) is not None:
            value[key]['producer_width'] = value['excluded'].shape[1]
            value[key]['producer_height'] = value['excluded'].shape[0]
    return value


def preview_pipe(torch, working, binding):
    pipe = SimpleNamespace(src_f32=torch.from_numpy(working.copy()).permute(2, 0, 1)[None],
                           repair_base=None, repair_ops=[], redo_ops=[])
    proof = REPLAY.make_evidence(binding, working, None, REPAIRS.digest_ops([], [], binding))
    pipe._creative_repair_source = deepcopy(binding)
    pipe._creative_repair_input = deepcopy(proof['input'])
    pipe._creative_repair_evidence = proof
    return pipe, proof


def test_original_and_derived_preview_use_the_current_owned_unmodified_rgb():
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding, original = fixture()
    proxy = (original//257).astype(np.uint8)
    working = proxy.astype(np.float32)/255.
    pipe, proof = preview_pipe(torch, working, binding)
    calls = []
    with patch.object(N, 'apply', side_effect=native_double(calls)):
        old = ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                                     byte_budget=BUDGET, document_id=DOCUMENT)
        new = ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                                     byte_budget=BUDGET, document_id=DOCUMENT,
                                     creative_source=binding, creative_proxy=proxy)
    first = assert_prepared(old, ref, working.shape[:2])
    second = assert_prepared(new, ref, working.shape[:2])
    assert first.window == second.window and len(calls) == 2
    np.testing.assert_array_equal(first.delta, second.delta)
    y, x, h, w = first.window
    for call in calls:
        np.testing.assert_array_equal(call['source'], working[y:y+h, x:x+w])
    np.testing.assert_array_equal(pipe.src_f32[0].permute(1, 2, 0).numpy(), working)
    assert REPLAY.verify_pipeline(pipe, binding) == proof


@pytest.mark.parametrize('derived', [False, True])
def test_full_export_rebuilds_from_canonical_source_not_corrected_preview_or_enlarged_proxy_delta(derived):
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding, original = fixture(size=512)
    small_analysis = proxy_analysis(analysis, 2)
    proxy = (original[::2, ::2]//257).astype(np.uint8)
    working = proxy.astype(np.float32)/255.
    pipe, _ = preview_pipe(torch, working, binding)
    calls = []
    with patch.object(N, 'apply', side_effect=native_double(calls)):
        preview = ENGINE.prepare_preview(pipe, state, ref['asset_sha256'],
            {ref['face_instance_id']: small_analysis}, byte_budget=BUDGET, document_id=DOCUMENT,
            **({'creative_source': binding, 'creative_proxy': proxy} if derived else {}))
        preview_record = assert_prepared(preview, ref, (256, 256))
        corrected, _ = preview.apply_source_stage('lip_texture', working)
        assert np.any(corrected != working)
        frozen = snapshot(state, ref, small_analysis, binding, derived=derived)
        full_source = original.astype(np.float32)/65535. if derived else original
        prepared = export(frozen, full_source)
    record = assert_prepared(prepared, ref, (512, 512))
    assert len(calls) == 2 and record.window[2] > preview_record.window[2]
    assert calls[1]['radius'] > calls[0]['radius']
    y, x, h, w = record.window
    full_float = original.astype(np.float32)/65535.
    np.testing.assert_array_equal(calls[1]['source'], full_float[y:y+h, x:x+w])
    assert record.facts['source_dimensions'] == [512, 512]
    assert record.facts['render_dimensions'] == [512, 512]
    assert frozen['analyses'][ref['face_instance_id']]['excluded'].shape == (256, 256)
    assert not np.shares_memory(record.delta, preview_record.delta)
    assert not np.shares_memory(calls[1]['source'], corrected)
    # Export takes immutable canonical pixels, not pipe preview output/cache.
    np.testing.assert_array_equal(pipe.src_f32[0].permute(1, 2, 0).numpy(), working)


@pytest.mark.parametrize('fault', ['missing', 'input', 'source'])
def test_derived_repaired_source_requires_real_replay_evidence_before_native(fault):
    state, ref, analysis, binding, original = fixture()
    source = original.astype(np.float32)/65535.
    repaired = source*np.float32(.97)
    frozen = snapshot(state, ref, analysis, binding, derived=True)
    proof = REPLAY.make_evidence(binding, source, repaired, REPAIRS.digest_ops([], [], binding))
    if fault == 'missing': proof = None
    elif fault == 'input': proof['input']['sha256'] = 'e'*64
    else: proof['source']['sha256'] = 'e'*64
    with patch.object(N, 'apply', side_effect=AssertionError('unverified repair reached native')) as native:
        with pytest.raises(ValueError):
            export(frozen, source, repaired, creative_repair_evidence=proof)
    native.assert_not_called()


def test_valid_repair_rebuilds_lip_support_and_native_samples_from_repaired_source():
    state, ref, analysis, binding, original = fixture()
    source = original.astype(np.float32)/65535.
    repaired = source*np.float32(.97)
    frozen = snapshot(state, ref, analysis, binding, derived=True)
    proof = REPLAY.make_evidence(binding, source, repaired, REPAIRS.digest_ops([], [], binding))
    calls = []
    with patch.object(N, 'apply', side_effect=native_double(calls)):
        old = export(frozen, source)
        new = export(frozen, source, repaired, creative_repair_evidence=proof)
    first = assert_prepared(old, ref, source.shape[:2])
    second = assert_prepared(new, ref, source.shape[:2])
    assert first.window == second.window and len(calls) == 2
    assert not np.array_equal(first.delta, second.delta)
    np.testing.assert_allclose(calls[1]['source'], calls[0]['source']*.97, rtol=0, atol=1e-7)
    assert REPLAY.verify_evidence(proof, binding, source, repaired) == proof


@pytest.mark.parametrize('enabled', [False, True])
def test_neutral_foreign_face_box_is_protected_even_without_usable_analysis_or_when_disabled(enabled):
    state, ref, analysis, binding, original = fixture()
    evidence = deepcopy(analysis['evidence'])
    evidence.update(status='unresolved', detector_model_sha256=None, landmark_digest=None)
    neighbor = P.new_face(binding['sha256'], [0., 0., 1., 1.], evidence, manual=True)
    neighbor['enabled'] = enabled
    state['faces'][neighbor['face_instance_id']] = neighbor
    before = deepcopy(state)
    with patch.object(N, 'apply', side_effect=AssertionError('foreign face reached native')) as native:
        with pytest.raises(ValueError):
            export(snapshot(state, ref, analysis, binding), original)
    native.assert_not_called()
    assert state == before and neighbor['local_assets'] == {}


def test_other_asset_face_box_cannot_change_this_sources_lip_support_or_owner():
    state, ref, analysis, binding, original = fixture()
    before = snapshot(state, ref, analysis, binding)
    neighbor = P.new_face('f'*64, [0., 0., 1., 1.], analysis['evidence'])
    state['faces'][neighbor['face_instance_id']] = neighbor
    calls = []
    with patch.object(N, 'apply', side_effect=native_double(calls)):
        old = export(before, original)
        new = export(snapshot(state, ref, analysis, binding), original)
    first = assert_prepared(old, ref, original.shape[:2])
    second = assert_prepared(new, ref, original.shape[:2])
    assert len(calls) == 2 and first.window == second.window
    np.testing.assert_array_equal(first.delta, second.delta)
    np.testing.assert_array_equal(calls[0]['coverage'], calls[1]['coverage'])


def test_real_cpu_and_tensor_source_stage_share_one_upstream_headroom_scalar():
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding, original = fixture()
    source = original.astype(np.float32)/65535.
    calls = []
    with patch.object(N, 'apply', side_effect=native_double(calls)):
        prepared = export(snapshot(state, ref, analysis, binding), original)
    record = assert_prepared(prepared, ref, source.shape[:2])
    delta = expanded(record, source.shape)
    active = np.any(delta != 0, axis=2)
    upstream = source.copy()
    upstream[active] = [.999, .4, .2]
    before = upstream.copy()
    cpu, facts = prepared.apply_source_stage('lip_texture', upstream)
    assert facts['overlap_pixels'] == 0 and np.any(cpu != upstream)
    assert np.all((cpu >= 0) & (cpu <= 1))
    assert not np.array_equal(cpu, np.clip(upstream+delta, 0, 1))
    usable = active & np.all(delta != 0, axis=2)
    gains = (cpu[usable]-upstream[usable])/delta[usable]
    # Float32 subtraction/division magnifies rounding; vector direction is a
    # feasibility claim, not physical hue preservation after arbitrary edits.
    np.testing.assert_allclose(gains, np.repeat(gains[:, :1], 3, axis=1), rtol=0, atol=2e-4)
    assert np.any((gains > 0) & (gains < 1))
    pipe = SimpleNamespace(h=source.shape[0], w=source.shape[1], device='cpu', high_precision_warp=False)
    PIPE.install(pipe, prepared)
    pixels = torch.from_numpy(upstream.copy()).permute(2, 0, 1)[None]
    actual = PIPE.source_effect(pipe, 'lip_texture', pixels)
    np.testing.assert_allclose(actual[0].permute(1, 2, 0).numpy(), cpu, rtol=0, atol=1e-7)
    sampled = PIPE.warp(pipe, actual)
    np.testing.assert_allclose(sampled[0].permute(1, 2, 0).numpy(), cpu, rtol=0, atol=2e-6)
    assert len(calls) == 1
    np.testing.assert_array_equal(upstream, before)


def two_face_source():
    """One real two-face preparation input, assembled from authored specimens."""
    state = P.empty()
    refs, analyses, halves = [], {}, []
    asset, size = 'd'*64, 256
    for index in range(2):
        _, _, analysis, _, original = fixture(recipe=None, size=size, tone=.025*index)
        lm = analysis['landmarks']
        lm[:, 0] = (lm[:, 0]+index)/2
        evidence = analysis['evidence']
        evidence.update(source_width=2*size, source_height=size,
                        landmark_digest=hashlib.sha256(np.ascontiguousarray(lm, dtype='<f4').tobytes()).hexdigest())
        analysis['excluded'] = np.zeros((size, 2*size), np.float32)
        face = P.new_face(asset, [index*.5, .03, (index+1)*.5, .97], evidence)
        state['faces'][face['face_instance_id']] = face
        ref = P.face_ref(face)
        analysis['face_ref'] = deepcopy(ref)
        refs.append(ref)
        analyses[ref['face_instance_id']] = analysis
        halves.append(original)
        state = set_recipe(state, ref, {'version': 1, 'amount': .35+.3*index})
    original = np.concatenate(halves, axis=1)
    binding = {'sha256': asset, 'width': 2*size, 'height': size}
    frozen = SNAP.capture(state, asset, analyses)
    frozen.update(document_id=DOCUMENT, support_assets={})
    return refs, frozen, binding, original


@pytest.mark.parametrize('derived', [False, True])
def test_actual_two_face_joint_source_composition_and_four_tiles_use_full_prepared_layers(derived):
    torch = pytest.importorskip('torch')
    refs, frozen, binding, original = two_face_source()
    source = original.astype(np.float32)/65535.
    if derived:
        frozen['creative_source'] = binding
    calls = []
    with patch.object(N, 'apply', side_effect=native_double(calls)):
        prepared = export(frozen, source if derived else original)
    assert type(prepared.geometry) is CombinedGeometry and len(prepared.face_fields) == 2
    assert set(prepared.geometry.face_ids) == {ref['face_instance_id'] for ref in refs}
    assert not np.any(prepared.geometry.delta)
    assert len(prepared.effects) == len(calls) == 2
    assert all(record.stage == 'lip_texture' for record in prepared.effects)
    assert {record.face_ref['face_instance_id'] for record in prepared.effects} == set(prepared.geometry.face_ids)
    # This is real full-source preparation and real stable-instance merge, not
    # manually manufactured LocalEffect records or an identity owner double.
    cpu, facts = prepared.apply_source_stage('lip_texture', source)
    assert facts['overlap_pixels'] == 0 and facts['changed_pixels'] > 0
    for index in range(2):
        assert np.any(cpu[:, index*256:(index+1)*256] != source[:, index*256:(index+1)*256])
    count = len(calls)
    full = SimpleNamespace(h=256, w=512, device='cpu', high_precision_warp=False)
    PIPE.install(full, prepared)
    pixels = torch.from_numpy(source.copy()).permute(2, 0, 1)[None]
    expected = PIPE.source_effect(full, 'lip_texture', pixels)
    np.testing.assert_allclose(expected[0].permute(1, 2, 0).numpy(), cpu, rtol=0, atol=1e-7)
    rows = []
    # The y=153 split crosses the upper-lip interiors on both source faces.
    for y0, y1 in ((0, 153), (153, 256)):
        chunks = []
        for x0, x1 in ((0, 256), (256, 512)):
            tile = SimpleNamespace(h=y1-y0, w=x1-x0, device='cpu', high_precision_warp=False)
            PIPE.install(tile, prepared, origin=(y0, x0))
            chunk = PIPE.source_effect(tile, 'lip_texture', pixels[:, :, y0:y1, x0:x1])
            chunks.append(chunk)
            assert tile.people_prepared is prepared
        rows.append(torch.cat(chunks, dim=3))
    assert torch.equal(torch.cat(rows, dim=2), expected)
    np.testing.assert_allclose(PIPE.warp(full, expected)[0].permute(1, 2, 0).numpy(), cpu, rtol=0, atol=2e-6)
    assert len(calls) == count  # No native work, support rebuilding or per-tile source substitution.


@pytest.mark.parametrize('bad', [-.01, 1.01, float('nan'), float('inf')])
def test_actual_active_source_stage_refuses_invalid_upstream_without_channel_clipping(bad):
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
        prepared.apply_source_stage('lip_texture', upstream)
    pipe = SimpleNamespace(h=source.shape[0], w=source.shape[1], device='cpu', high_precision_warp=False)
    PIPE.install(pipe, prepared)
    with pytest.raises(ValueError):
        PIPE.source_effect(pipe, 'lip_texture', torch.from_numpy(upstream).permute(2, 0, 1)[None])


def test_neutral_cpu_and_tensor_composition_preserve_object_and_signed_zero_bits():
    from lumaretouch_engine import lip_texture_composition as COMPOSE
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


def test_original_shared_person_transports_one_scalar_and_recalculates_each_targets_source_support():
    targets = [fixture(recipe=None, asset='a'*64, size=256),
               fixture(recipe=None, asset='f'*64, size=320, tone=.025)]
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
    assert len(rows) == 1 and rows[0]['scope'] == 'person'
    assert rows[0]['parameter_path'] == '/amount' and rows[0]['value'] == ACTIVE['amount']
    observed, records = [], []
    for _, ref, analysis, binding, original in targets:
        assert resolved(candidate, ref)[S.OP] == ACTIVE
        calls = []
        with patch.object(N, 'apply', side_effect=native_double(calls)):
            prepared = export(snapshot(candidate, ref, analysis, binding), original)
        record = assert_prepared(prepared, ref, original.shape[:2])
        records.append(record)
        observed.append(calls)
        assert len(calls) == 1 and candidate['faces'][ref['face_instance_id']]['local_assets'] == {}
        assert snapshot(candidate, ref, analysis, binding)['support_assets'] == {}
        y, x, h, w = record.window
        np.testing.assert_array_equal(calls[0]['source'], original[y:y+h, x:x+w].astype(np.float32)/65535.)
    assert observed[0][0]['source'].shape != observed[1][0]['source'].shape
    for key in ('source', 'coverage', 'across'):
        assert not np.shares_memory(observed[0][0][key], observed[1][0][key])
    assert not np.shares_memory(records[0].delta, records[1].delta)
    assert state == before


def test_reviewed_derived_replica_capsules_transport_only_amount_and_rebuild_each_current_owner():
    targets = [fixture(recipe=None, asset='a'*64), fixture(recipe=None, asset='f'*64, tone=.025)]
    documents = ('synthetic-derived-lip-a', 'synthetic-derived-lip-b')
    members = [{'document_id': document, 'scope_id': document,
                'original_sha256': ('1' if index == 0 else '2')*64, 'ref': deepcopy(target[1])}
               for index, (document, target) in enumerate(zip(documents, targets))]
    intent = [{'op': S.OP, 'path': '/amount', 'value': ACTIVE['amount']}]
    results, capsules, samples = [], [], []
    for document, (state, ref, analysis, binding, original) in zip(documents, targets):
        capsule = CROSS.descriptor('synthetic-reviewed-lips', document, members, intent)
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
        samples.append(calls[0]['source'])
        assert len(calls) == 1 and candidate['faces'] == state['faces']
        assert capsule['intent'] == intent
        assert candidate['faces'][ref['face_instance_id']]['local_assets'] == {}
        assert frozen['support_assets'] == {}
    assert capsules[0]['generation'] == capsules[1]['generation']
    assert not np.array_equal(samples[0], samples[1])
    assert not np.array_equal(results[0].delta, results[1].delta)
    assert not np.shares_memory(results[0].delta, results[1].delta)


@pytest.mark.parametrize('failure', ['preparation', 'publication'])
def test_real_host_refusal_restores_graph_history_and_existing_owner_fence_semantics(failure):
    """Actual host transaction; minimal host IO does not replace its owner."""
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
            raise ValueError('synthetic lip publication refusal')
    engine._people_prepare_graph = prepare
    engine._people_sync = sync
    engine._people_publish_graph = lambda candidate, assets: PeopleHostMixin._people_publish_graph(engine, candidate, assets)
    action = RuntimeError('synthetic lip native refusal') if failure == 'preparation' else native_double([])
    with patch.object(N, 'apply', side_effect=action), pytest.raises(ValueError, match='synthetic'):
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


def test_second_face_native_failure_cannot_return_a_partially_prepared_joint_render():
    refs, frozen, _, original = two_face_source()
    state_before, pixels = deepcopy(frozen['state']), original.copy()
    calls = []
    first = native_double(calls)
    attempts = []
    def fail_second(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 2:
            raise RuntimeError('synthetic second-face native refusal')
        return first(*args, **kwargs)
    with patch.object(N, 'apply', side_effect=fail_second):
        with pytest.raises(ValueError, match='synthetic second-face'):
            export(frozen, original)
    assert len(refs) == len(attempts) == 2 and len(calls) == 1
    assert frozen['state'] == state_before
    np.testing.assert_array_equal(original, pixels)


def test_source_stage_wiring_precedes_lip_makeup_without_adding_a_geometry_sampler():
    tree = ast.parse((ROOT/'engine/src/lumaretouch_engine/vram.py').read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
             and node.func.value.id == 'PEOPLE_PIPE' and node.func.attr == 'source_effect']
    positions = {}
    for call in calls:
        if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
            positions.setdefault(call.args[1].value, []).append(call.lineno)
    assert len(positions['lip_texture']) == len(positions['lip_makeup']) == 1
    assert positions['lip_texture'][0] < positions['lip_makeup'][0]
    assert EFFECTS.STAGES.index('lip_texture') < EFFECTS.STAGES.index('lip_makeup')
    assert S.OP not in A.GEOMETRY
    renderer = (ROOT/'engine/src/lumaretouch_engine/people_render_runtime.py').read_text()
    assert 'from .lip_texture_layer import prepare as prepare_lip_texture' in renderer
    assert 'protected_boxes=lip_neighbors' in renderer
    assert 'mouth = field.fields[3]' in renderer
    project = (ROOT/'engine/src/lumaretouch_engine/people_project.py').read_text()
    assert 'from .lip_texture_project import validate_graph as validate_lip_texture_graph' in project
    assert 'validate_lip_texture_graph(value[key])' in project


def test_all_mock_patches_remain_only_at_declared_native_available_apply_boundary():
    tree = ast.parse(Path(__file__).read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
             and node.func.value.id == 'patch' and node.func.attr == 'object']
    assert calls
    for call in calls:
        assert isinstance(call.args[0], ast.Name) and call.args[0].id == 'N'
        assert isinstance(call.args[1], ast.Constant) and call.args[1].value in ('available', 'apply')


# Frozen source from e3114fef, used ONLY as syntax, never imported or executed.
# Error message expressions may acquire a label; every computational statement,
# condition, array shape, arithmetic order, safety margin and return must match.
_BASELINE_BROW_ALGEBRA = '''
def apply_np(pixels, delta):
    import numpy as np
    if (type(pixels) is not np.ndarray or type(delta) is not np.ndarray
            or pixels.ndim != 3 or pixels.shape[-1] != 3 or pixels.shape != delta.shape
            or pixels.dtype != np.float32 or delta.dtype != np.float32):
        raise ValueError('Brow composition requires aligned float32 HWC RGB and delta')
    if not np.isfinite(delta).all():
        raise ValueError('Brow source delta is nonfinite')
    active = np.any(delta != 0, axis=-1, keepdims=True)
    if not np.any(active):
        return pixels
    invalid = ~np.isfinite(pixels) | (pixels < 0) | (pixels > 1)
    if np.any(invalid & active):
        raise ValueError('Active brow composition cannot clip HDR or invalid upstream pixels')
    gain = np.ones_like(pixels[..., :1])
    for channel in range(3):
        component = delta[..., channel:channel+1]
        current = pixels[..., channel:channel+1]
        denominator = np.where(component != 0, component, np.float32(1))
        room = np.where(component > 0, 1-current, -current)
        permitted = np.where(component != 0, room/denominator, np.float32(1))
        gain = np.minimum(gain, permitted)
    gain = np.clip(gain, 0, 1)
    gain = np.where(gain < 1, gain*np.float32(1-4*np.finfo(np.float32).eps), gain)
    result = np.where(delta != 0, pixels+gain*delta, pixels)
    if np.any((~np.isfinite(result) | (result < 0) | (result > 1)) & active):
        raise ValueError('Brow vector feasibility failed; no channel-clipping fallback')
    return result

def apply_t(pixels, delta):
    import torch
    if (not isinstance(pixels, torch.Tensor) or not isinstance(delta, torch.Tensor)
            or pixels.ndim != 4 or pixels.shape[1] != 3 or pixels.shape != delta.shape
            or pixels.dtype != torch.float32 or delta.dtype != torch.float32
            or pixels.device != delta.device):
        raise ValueError('Brow composition requires aligned float32 NCHW RGB and delta')
    if not bool(torch.isfinite(delta).all()):
        raise ValueError('Brow source delta is nonfinite')
    active = delta.ne(0).any(dim=1, keepdim=True)
    if not bool(active.any()):
        return pixels
    invalid = ~torch.isfinite(pixels) | pixels.lt(0) | pixels.gt(1)
    if bool((invalid & active).any()):
        raise ValueError('Active brow composition cannot clip HDR or invalid upstream pixels')
    gain = torch.ones_like(pixels[:, :1])
    for channel in range(3):
        component = delta[:, channel:channel+1]
        current = pixels[:, channel:channel+1]
        denominator = torch.where(component.ne(0), component, torch.ones_like(component))
        room = torch.where(component.gt(0), 1-current, -current)
        permitted = torch.where(component.ne(0), room/denominator, torch.ones_like(component))
        gain = torch.minimum(gain, permitted)
    gain = gain.clamp(0, 1)
    gain = torch.where(gain.lt(1), gain*(1-4*torch.finfo(torch.float32).eps), gain)
    result = torch.where(delta.ne(0), pixels+gain*delta, pixels)
    if bool(((~torch.isfinite(result) | result.lt(0) | result.gt(1)) & active).any()):
        raise ValueError('Brow vector feasibility failed; no channel-clipping fallback')
    return result
'''


def test_shared_vector_extraction_preserves_exact_frozen_brow_computational_ast():
    class ErrorMessagesOnly(ast.NodeTransformer):
        def visit_Raise(self, node):
            assert isinstance(node.exc, ast.Call)
            assert isinstance(node.exc.func, ast.Name) and node.exc.func.id == 'ValueError'
            assert len(node.exc.args) == 1 and not node.exc.keywords and node.cause is None
            node.exc.args = [ast.Constant(value='MESSAGE_ONLY')]
            return node
    expected_tree = ast.parse(_BASELINE_BROW_ALGEBRA)
    actual_tree = ast.parse((ROOT/'engine/src/lumaretouch_engine/people_source_vector.py').read_text())
    expected = {node.name: node for node in expected_tree.body if isinstance(node, ast.FunctionDef)}
    actual = {node.name: node for node in actual_tree.body if isinstance(node, ast.FunctionDef)}
    assert set(expected) == set(actual) == {'apply_np', 'apply_t'}
    for name in expected:
        original = ErrorMessagesOnly().visit(deepcopy(expected[name]))
        extracted = ErrorMessagesOnly().visit(deepcopy(actual[name]))
        assert [arg.arg for arg in extracted.args.args] == ['pixels', 'delta']
        assert [arg.arg for arg in extracted.args.kwonlyargs] == ['label']
        assert extracted.args.kw_defaults == [None]
        assert [ast.dump(node, include_attributes=False) for node in extracted.body] == [
            ast.dump(node, include_attributes=False) for node in original.body]
    for module, label in (('brow_enhance_composition.py', 'Brow'),
                          ('lip_texture_composition.py', 'Lip texture')):
        wrapper = ast.parse((ROOT/'engine/src/lumaretouch_engine'/module).read_text())
        functions = [node for node in wrapper.body if isinstance(node, ast.FunctionDef)]
        assert {node.name for node in functions} == {'apply_np', 'apply_t'}
        for function in functions:
            assert len(function.body) == 1 and isinstance(function.body[0], ast.Return)
            call = function.body[0].value
            assert isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            assert isinstance(call.func.value, ast.Name) and call.func.value.id == 'V'
            assert call.func.attr == function.name
            assert [arg.id for arg in call.args] == ['pixels', 'delta']
            assert len(call.keywords) == 1 and call.keywords[0].arg == 'label'
            assert call.keywords[0].value.value == label
