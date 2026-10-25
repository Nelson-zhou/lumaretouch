"""AUTHORED / UNRUN. Census contract fixtures, not inference or photo acceptance.

Model hashes, landmarks, masks and file bytes here are synthetic schema fixtures.
The private source context does not claim these bytes were decoded by the real
image decoder. Owner-level numerical/memory/source-race acceptance is separate.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from lumaretouch_engine import creative_capture_people as C
from lumaretouch_engine import people_state as S
from lumaretouch_engine.local_mask_state import file_stamp


@pytest.fixture
def census(tmp_path):
    path = tmp_path / 'source.fixture'
    path.write_bytes(b'not an image: immutable unit-test source bytes')
    asset = sha256(path.read_bytes()).hexdigest()
    source = np.arange(8 * 12 * 3, dtype=np.uint16).reshape(8, 12, 3)
    source.setflags(write=False)
    points = np.zeros((478, 3), dtype='<f4')
    points.setflags(write=False)
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'd' * 64,
        'semantic_model_sha256': 'e' * 64, 'landmark_digest': sha256(points.tobytes()).hexdigest(),
        'status': 'verified', 'source_width': 12, 'source_height': 8,
        'orientation': 'exif_normalized_once'}
    face = {'face_instance_id': 'face-a', 'asset_sha256': asset, 'analysis_revision': 4,
        'box': [.1, .1, .6, .8], 'evidence': deepcopy(evidence), 'manual': False,
        'enabled': True, 'labels': {}, 'local_assets': {}}
    state = S.empty()
    state['faces']['face-a'] = face
    plane = np.full((2, 3), .25, np.float32)
    plane.setflags(write=False)
    raw = {'face_ref': S.face_ref(face), 'evidence': deepcopy(evidence),
        'landmarks': points, 'excluded': plane, 'skin': plane}
    people = {'state': state, 'asset_sha256': asset, 'document_id': 'doc-a',
        'analyses': {'face-a': raw}, 'support_assets': {}, 'hair_colour_assets': {},
        'hair_colour_evidence': None, 'hair_colour_source_path': str(path),
        'hair_colour_source_stamp': None}
    context = {'path': str(path), 'file_stamp': file_stamp(str(path)),
        'asset_sha256': asset, 'document_id': 'doc-a'}
    return SimpleNamespace(people=people, people_document_id='doc-a', creative_base=None,
                           _creative_capture_original_source=context), source, path


def row(census):
    return census[0].people['analyses']['face-a']


def face(census):
    return census[0].people['state']['faces']['face-a']


def override(census, op='lnx.deform.v1', path='/slim_face', value=0., scope='face', target='face-a'):
    census[0].people['state']['overrides'].append({'scope': scope, 'target_id': target,
        'operation_id': op, 'parameter_path': path, 'value': value})


def brush_recipe():
    return {'version': 1, 'domain': 'source-normalized', 'objects': [
        {'id': 'stroke-a', 'name': 'Fixture stroke', 'enabled': True, 'operation': 'add',
         'kind': 'brush', 'opacity': 1., 'feather': 0., 'points': [[.4, .4]],
         'axes': [[.03, 0.], [0., .03]]}]}


@pytest.mark.parametrize('dtype', [np.uint8, np.uint16])
def test_neutral_rgb8_rgb16_keeps_exact_snapshot_and_array_identity(census, dtype):
    spec, source, _ = census
    source = source.astype(dtype)
    source.setflags(write=False)
    people, before_state = spec.people, deepcopy(spec.people['state'])
    original = source.tobytes()
    arrays = {key: value for key, value in row(census).items() if isinstance(value, np.ndarray)}
    originals = {key: value.tobytes() for key, value in arrays.items()}
    assert C.neutral_census_candidate(people) is True
    assert C.neutral_original_census(spec, source) is True
    assert spec.people is people and people['state'] == before_state
    assert source.tobytes() == original and not source.flags.writeable
    for key, value in arrays.items():
        assert row(census)[key] is value and value.tobytes() == originals[key]
        assert not value.flags.writeable


def test_no_full_preparation_raster_resample_or_geometry(census):
    spec, source, _ = census
    forbidden = AssertionError('Census must not allocate target-grid preparation')
    with patch('lumaretouch_engine.people_snapshot.at_dimensions', side_effect=forbidden), \
         patch('lumaretouch_engine.people_support_assets.raster', side_effect=forbidden), \
         patch('lumaretouch_engine.people_engine_runtime.prepare_export', side_effect=forbidden), \
         patch('lumaretouch_engine.people_algorithms.build_geometry', side_effect=forbidden):
        assert C.neutral_original_census(spec, source) is True


def test_actual_producer_grid_reaches_existing_analysis_validator(census):
    from lumaretouch_engine.people_render_runtime import verify_analysis
    spec, source, _ = census
    with patch('lumaretouch_engine.people_render_runtime.verify_analysis', wraps=verify_analysis) as verify:
        assert C.neutral_original_census(spec, source) is True
    assert [call.args[2] for call in verify.call_args_list] == [(2, 3)]


def test_maskless_real_schema_analysis_requires_no_invented_mask(census):
    spec, source, _ = census
    row(census)['skin'] = row(census)['excluded'] = None
    face(census)['evidence']['semantic_model_sha256'] = None
    row(census)['evidence']['semantic_model_sha256'] = None
    assert C.neutral_census_candidate(spec.people) is True
    assert C.neutral_original_census(spec, source) is True
    assert row(census)['skin'] is None and row(census)['excluded'] is None


def test_candidate_does_not_authorize_skip_without_source_context(census):
    spec, source, _ = census
    assert C.neutral_census_candidate(spec.people) is True
    del spec._creative_capture_original_source
    assert C.neutral_original_census(spec, source) is False


@pytest.mark.parametrize('change', ['unknown_key', 'missing_key', 'boolean_stamp', 'wrong_document'])
def test_malformed_or_wrong_private_context_refuses(census, change):
    spec, source, _ = census
    context = spec._creative_capture_original_source
    if change == 'unknown_key': context['trusted'] = True
    if change == 'missing_key': context.pop('path')
    if change == 'boolean_stamp': context['file_stamp'] = [False] * 5
    if change == 'wrong_document': context['document_id'] = 'same-byte-copy'
    with pytest.raises(ValueError): C.neutral_original_census(spec, source)


def test_same_source_bytes_do_not_replace_independent_document_owner(census):
    spec, source, _ = census
    spec.people['document_id'] = 'same-byte-copy'
    with pytest.raises(ValueError): C.neutral_original_census(spec, source)


def test_changed_source_stamp_refuses(census):
    spec, source, path = census
    path.write_bytes(b'different source bytes')
    with pytest.raises(ValueError): C.neutral_original_census(spec, source)


def test_digest_is_checked_even_with_current_stamp(census):
    spec, source, path = census
    path.write_bytes(b'different source bytes')
    spec._creative_capture_original_source['file_stamp'] = file_stamp(str(path))
    with pytest.raises(ValueError): C.neutral_original_census(spec, source)


def test_source_is_rechecked_after_analysis_validation(census, monkeypatch):
    spec, source, _ = census
    old = tuple(spec._creative_capture_original_source['file_stamp'])
    changed, calls = (*old[:-1], old[-1] + 1), []
    def stamp(_path):
        calls.append(None)
        return old if len(calls) <= 2 else changed
    monkeypatch.setattr('lumaretouch_engine.local_mask_state.file_stamp', stamp)
    monkeypatch.setattr('lumaretouch_engine.local_mask_state.source_digest', lambda _path: spec.people['asset_sha256'])
    with pytest.raises(ValueError): C.neutral_original_census(spec, source)
    assert len(calls) == 3


def test_derived_float_and_alpha_are_not_original_census(census):
    spec, source, _ = census
    assert C.neutral_original_census(spec, source.astype(np.float32)) is False
    spec.creative_base = {'not': 'original'}
    assert C.neutral_original_census(spec, source) is False
    spec.creative_base = None
    with pytest.raises(ValueError): C.neutral_original_census(spec, np.zeros((8, 12, 4), np.uint8))
    spec.people['creative_source'] = {'sha256': spec.people['asset_sha256'], 'width': 12, 'height': 8}
    assert C.neutral_census_candidate(spec.people) is False
    assert C.neutral_original_census(spec, source) is False


@pytest.mark.parametrize('enabled', [True, False])
def test_active_face_is_not_neutral_even_when_disabled(census, enabled):
    spec, source, _ = census
    face(census)['enabled'] = enabled
    override(census, value=.2)
    assert C.neutral_census_candidate(spec.people) is False
    assert C.neutral_original_census(spec, source) is False


def test_shadowed_nondefault_photograph_intent_is_not_discarded(census):
    spec, source, _ = census
    override(census, value=.2, scope='all_people', target=spec.people['asset_sha256'])
    override(census, value=0.)
    assert C.neutral_original_census(spec, source) is False


def test_dormant_nondefault_mode_still_declines(census):
    spec, source, _ = census
    override(census, op='lnx.brow_enhance.v1', path='/linked', value=False)
    assert C.neutral_census_candidate(spec.people) is False
    assert C.neutral_original_census(spec, source) is False


@pytest.mark.parametrize('op,path,value', [
    ('lnx.deform.v1', '/slim_face', False), ('lnx.brow_enhance.v1', '/linked', 1),
    ('unknown.operation', '/amount', 0.), ('lnx.deform.v1', '/unknown', 0.),
])
def test_scalar_aliases_and_unknown_parameters_refuse(census, op, path, value):
    spec, source, _ = census
    override(census, op=op, path=path, value=value)
    with pytest.raises(ValueError): C.neutral_original_census(spec, source)


def test_zero_faces_cannot_hide_unknown_all_people_operation(census):
    spec, source, _ = census
    spec.people['state']['faces'], spec.people['analyses'] = {}, {}
    override(census, op='unknown.operation', path='/strength', scope='all_people', target=spec.people['asset_sha256'])
    with pytest.raises(ValueError): C.neutral_census_candidate(spec.people)
    with pytest.raises(ValueError): C.neutral_original_census(spec, source)


def test_zero_faces_with_valid_defaults_needs_no_invented_faceref(census):
    spec, source, _ = census
    spec.people['state']['faces'], spec.people['analyses'] = {}, {}
    override(census, scope='all_people', target=spec.people['asset_sha256'])
    with patch('lumaretouch_engine.people_state.new_face', side_effect=AssertionError('No invented face')):
        assert C.neutral_original_census(spec, source) is True
    assert spec.people['state']['faces'] == {}


@pytest.mark.parametrize('change', ['face_ref', 'evidence', 'landmarks', 'unknown_field', 'foreign_key'])
def test_invalid_analysis_refuses_even_for_disabled_face(census, change):
    spec, source, _ = census
    face(census)['enabled'] = False
    raw = row(census)
    if change == 'face_ref': raw['face_ref']['analysis_revision'] += 1
    if change == 'evidence': raw['evidence']['landmark_digest'] = 'f' * 64
    if change == 'landmarks': raw['landmarks'] = np.ones((478, 3), np.float32)
    if change == 'unknown_field': raw['proxy_effect'] = np.zeros((2, 3, 3), np.float32)
    if change == 'foreign_key': spec.people['analyses']['not-retained'] = raw
    with pytest.raises(ValueError): C.neutral_original_census(spec, source)


@pytest.mark.parametrize('hidden', ['active_recipe', 'unknown_snapshot', 'disabled_local_asset'])
def test_invalid_actual_analysis_raises_even_when_other_inputs_already_decline(census, hidden):
    spec, source, _ = census
    if hidden == 'active_recipe': override(census, value=.2)
    if hidden == 'unknown_snapshot': spec.people['future_owned_effect'] = {'enabled': False}
    if hidden == 'disabled_local_asset':
        face(census)['enabled'] = False
        face(census)['local_assets']['face_decoration_visibility'] = {
            'owner': S.face_ref(face(census)), 'kind': 'face_decoration_visibility', 'content_sha256': 'f' * 64}
    row(census)['landmarks'] = np.ones((478, 3), np.float32)
    with pytest.raises(ValueError): C.neutral_original_census(spec, source)
    with pytest.raises(ValueError): C.neutral_census_candidate(spec.people)


def test_original_extent_is_independent_of_proxy_grid(census):
    spec, source, _ = census
    face(census)['evidence']['source_width'] = row(census)['evidence']['source_width'] = 13
    with pytest.raises(ValueError): C.neutral_original_census(spec, source)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -.01, 1.01])
def test_corrupt_mask_values_are_not_ignored(census, value):
    spec, source, _ = census
    row(census)['skin'] = np.full((2, 3), value, np.float32)
    with pytest.raises(ValueError): C.neutral_original_census(spec, source)


def test_semantics_without_loaded_model_evidence_refuse(census):
    spec, source, _ = census
    face(census)['evidence']['semantic_model_sha256'] = row(census)['evidence']['semantic_model_sha256'] = None
    with pytest.raises(ValueError): C.neutral_original_census(spec, source)


def test_mixed_legacy_grids_decline_without_resizing(census):
    spec, source, _ = census
    row(census)['skin'] = np.full((3, 4), .5, np.float32)
    assert C.neutral_census_candidate(spec.people) is False
    assert C.neutral_original_census(spec, source) is False
    assert row(census)['skin'].shape == (3, 4)


@pytest.mark.parametrize('name', ['face_skin', 'body_skin'])
def test_named_semantics_require_actual_recorded_producer_extent(census, name):
    from lumaretouch_engine import skin_colour_support as F, body_skin_semantics as B
    spec, source, _ = census
    raw = row(census)
    raw[name] = raw['skin']
    observation = {'contract': (F if name == 'face_skin' else B).CONTRACT,
        'source_sha256': spec.people['asset_sha256'], 'semantic_model_sha256': 'e' * 64,
        'producer_width': 3, 'producer_height': 2}
    if name == 'body_skin': observation['detector_model_sha256'] = 'd' * 64
    raw[name + '_observation'] = observation
    assert C.neutral_original_census(spec, source) is True
    observation['producer_width'] = 4
    assert C.neutral_original_census(spec, source) is False
    observation['source_sha256'] = 'f' * 64
    with pytest.raises(ValueError): C.neutral_original_census(spec, source)


def test_each_face_keeps_its_producer_grid_and_shared_arrays(census):
    spec, source, _ = census
    second = deepcopy(face(census))
    second['face_instance_id'], second['enabled'] = 'face-b', False
    spec.people['state']['faces']['face-b'] = second
    second_row = {**row(census), 'face_ref': S.face_ref(second),
                  'skin': np.full((3, 5), .5, np.float32), 'excluded': None}
    spec.people['analyses']['face-b'] = second_row
    assert C.neutral_original_census(spec, source) is True
    assert second_row['landmarks'] is row(census)['landmarks']
    assert row(census)['excluded'] is row(census)['skin']


def test_missing_manual_and_unresolved_evidence_is_not_synthesized(census):
    spec, source, _ = census
    spec.people['analyses'] = {}
    assert C.neutral_original_census(spec, source) is False
    face(census)['manual'], face(census)['evidence']['status'] = True, 'unresolved'
    assert C.neutral_census_candidate(spec.people) is False
    assert C.neutral_original_census(spec, source) is False


def test_foreign_graph_faces_and_detection_runs_decline(census):
    spec, source, _ = census
    other = deepcopy(face(census))
    other['face_instance_id'], other['asset_sha256'] = 'other-source-face', 'f' * 64
    spec.people['state']['faces'][other['face_instance_id']] = other
    assert C.neutral_original_census(spec, source) is False
    spec.people['analyses'][other['face_instance_id']] = {**row(census), 'face_ref': S.face_ref(other)}
    with pytest.raises(ValueError): C.neutral_original_census(spec, source)
    del spec.people['state']['faces'][other['face_instance_id']]
    del spec.people['analyses'][other['face_instance_id']]
    spec.people['state']['analysis_runs']['f' * 64] = {
        'detector_limit': 32, 'limit_reached': False, 'census_complete': False, 'notice': 'Fixture only'}
    assert C.neutral_original_census(spec, source) is False


def test_legacy_archive_and_unlinked_person_are_not_ignored(census):
    spec, source, _ = census
    state = spec.people['state']
    state['unresolved_legacy'] = [{'id': 'legacy-a', 'legacy_key': 'deform',
        'asset_sha256': spec.people['asset_sha256'], 'intent': {'slim_face': .2},
        'owner_evidence': None, 'history_ref': None, 'status': 'unresolved', 'binding': None}]
    assert C.neutral_original_census(spec, source) is False
    state['unresolved_legacy'] = []
    state['persons']['unlinked-person'] = {'anonymous': True}
    assert C.neutral_original_census(spec, source) is False


def test_neutral_cross_owner_capsule_never_authorizes_skip(census):
    from lumaretouch_engine import people_cross_owner as X
    spec, source, _ = census
    members = [
        {'document_id': 'doc-a', 'scope_id': 'doc-a', 'original_sha256': spec.people['asset_sha256'], 'ref': S.face_ref(face(census))},
        {'document_id': 'doc-b', 'scope_id': 'doc-b', 'original_sha256': 'f' * 64,
         'ref': {'asset_sha256': 'f' * 64, 'face_instance_id': 'foreign-face', 'analysis_revision': 0}},
    ]
    capsule = X.descriptor('association', 'doc-a', members,
        [{'op': 'lnx.deform.v1', 'path': '/slim_face', 'value': 0.}])
    spec.people['state'] = X.create(spec.people['state'], 'reviewed-person', capsule)
    assert C.neutral_census_candidate(spec.people) is False
    assert C.neutral_original_census(spec, source) is False
    spec.people_document_id = spec.people['document_id'] = 'same-byte-copy'
    spec._creative_capture_original_source['document_id'] = 'same-byte-copy'
    with pytest.raises(ValueError): C.neutral_original_census(spec, source)


def test_disabled_local_pointer_is_not_silently_dropped(census):
    spec, source, _ = census
    face(census)['enabled'] = False
    face(census)['local_assets']['face_decoration_visibility'] = {
        'owner': S.face_ref(face(census)), 'kind': 'face_decoration_visibility', 'content_sha256': 'f' * 64}
    assert C.neutral_original_census(spec, source) is False


def test_corrupt_support_store_refuses(census):
    spec, source, _ = census
    spec.people['support_assets'] = {'f' * 64: {}}
    with pytest.raises(ValueError): C.neutral_original_census(spec, source)


def test_detached_recovery_store_and_disabled_recovery_are_not_discarded(census):
    from lumaretouch_engine import people_support_assets as V, effect_recovery_state as E
    spec, source, _ = census
    binding = {'sha256': spec.people['asset_sha256'], 'width': 12, 'height': 8}
    target = {'target': 'facial_wrinkles', 'enabled': False, 'recipe': brush_recipe(),
        'owner': {'version': 1, 'source_sha256': binding['sha256'],
                  'landmarks_sha256': face(census)['evidence']['landmark_digest'], 'backend': 'mediapipe'}}
    checked = E.check({'version': 1, 'source': binding, 'targets': [target]})
    record = {'version': 1, 'face_ref': S.face_ref(face(census)), 'source': checked['source'], 'row': checked['targets'][0]}
    spec.people['support_assets'] = {V.content_digest(record): record}
    assert face(census)['local_assets'] == {}
    assert C.neutral_original_census(spec, source) is False
    spec.people['support_assets'], spec.effect_recovery = {}, checked
    assert C.neutral_original_census(spec, source) is False


def test_detached_hair_store_is_not_neutral(census):
    from lumaretouch_engine import hair_colour_assets as H
    spec, source, _ = census
    binding = {'sha256': spec.people['asset_sha256'], 'width': 12, 'height': 8}
    record = H.reviewed(S.face_ref(face(census)), binding, brush_recipe(), H.MODEL_SHA256,
                        evidence_sha='f' * 64, confirmed=True)
    spec.people['hair_colour_assets'] = {H.digest(record): record}
    assert C.neutral_census_candidate(spec.people) is False
    assert C.neutral_original_census(spec, source) is False


@pytest.mark.parametrize('field,value', [
    ('body_pose', {}), ('body_pose_source_path', 'some-body-source'),
    ('body_pose_source_proof', {}), ('effect_recovery_fields', [object()]),
    ('effect_recovery_fields', ()),
    ('effect_recovery_path', 'some-recovery-source'), ('repair', [object()]),
])
def test_owned_body_recovery_and_repair_inputs_never_skip(census, field, value):
    spec, source, _ = census
    setattr(spec, field, value)
    assert C.neutral_original_census(spec, source) is False


def test_unknown_retained_snapshot_input_is_not_assumed_harmless(census):
    spec, source, _ = census
    spec.people['future_owned_effect'] = {'enabled': False}
    assert C.neutral_census_candidate(spec.people) is False
    assert C.neutral_original_census(spec, source) is False


def test_planner_refusal_or_analysis_requirement_cannot_be_bypassed(census):
    from lumaretouch_engine import people_render_plan as P
    spec, source, _ = census
    original = P.build
    for field, value in (('status', 'refused'), ('requires_analysis', True)):
        def changed(*args, **kwargs):
            plan = original(*args, **kwargs)
            plan['entries'][0][field] = value
            return plan
        with patch.object(P, 'build', side_effect=changed):
            assert C.neutral_original_census(spec, source) is False


def test_real_neutral_recovery_preparation_does_not_block_census(census):
    from lumaretouch_engine.effect_recovery_runtime import export_prepare
    spec, source, _ = census
    spec.effect_recovery = None
    export_prepare(spec, source.shape[:2], source_pixels=source)
    assert type(spec.effect_recovery_fields) is list and spec.effect_recovery_fields == []
    assert C.neutral_original_census(spec, source) is True


def test_private_people_prepare_skips_allocation_but_keeps_bank(census):
    from lumaretouch_engine.people_export import prepare
    spec, source, _ = census
    people = spec.people
    forbidden = AssertionError('Private neutral preparation must not enter generic allocation')
    with patch('lumaretouch_engine.people_support_assets.raster', side_effect=forbidden), \
         patch('lumaretouch_engine.people_engine_runtime.prepare_export', side_effect=forbidden):
        assert prepare(spec, source, None) is None
    assert spec.people is people


def test_failed_private_proof_refuses_without_unadmitted_generic_fallthrough(census):
    from lumaretouch_engine.people_export import prepare
    spec, source, _ = census
    people = spec.people
    forbidden = AssertionError('Failed private proof cannot fall through')
    with patch.object(C, 'neutral_original_census', return_value=False), \
         patch('lumaretouch_engine.people_support_assets.raster', side_effect=forbidden), \
         patch('lumaretouch_engine.people_engine_runtime.prepare_export', side_effect=forbidden):
        with pytest.raises(ValueError, match='fully verified neutral original people census'):
            prepare(spec, source, None)
    assert spec.people is people


def test_repaired_source_never_enters_private_census_skip(census):
    from lumaretouch_engine.people_export import prepare
    spec, source, _ = census
    with patch.object(C, 'neutral_original_census', side_effect=AssertionError('Refuse before proof')):
        with pytest.raises(ValueError, match='fully verified neutral original people census'):
            prepare(spec, source, np.zeros(source.shape, np.float32))


def test_generic_people_prepare_without_marker_stays_on_existing_path(census):
    from lumaretouch_engine.people_export import prepare
    spec, source, _ = census
    del spec._creative_capture_original_source
    people, prepared = spec.people, object()
    with patch.object(C, 'neutral_original_census', side_effect=AssertionError('Generic path is unchanged')), \
         patch('lumaretouch_engine.people_support_assets.raster', return_value={}) as raster, \
         patch('lumaretouch_engine.people_engine_runtime.prepare_export', return_value=prepared) as full, \
         patch('lumaretouch_engine.cpu_memory_budget.available_estimate', return_value=123):
        assert prepare(spec, source, None) is prepared
    raster.assert_called_once()
    assert full.call_args.args == (people, source, None)
    assert full.call_args.kwargs['document_id'] == 'doc-a'
    assert spec.people is people
