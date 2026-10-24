"""AUTHORED / UNRUN: explicit slim-face v2 state and contour-boundary contracts.

All image/landmark observations below are synthetic routing fixtures, not real
detector evidence or photographic acceptance. The contour field builder is an
explicit double; ownership checks and composed-footprint guards remain real.
No product import, test collection, test execution, native build or inference
was performed while authoring these fixtures. Static AST inspection only.
"""
import ast
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from lumaretouch_engine import slim_face_state as S, slim_face_people as PORT
from lumaretouch_engine import face_contour_state as C, face_contour_people as CONTOUR
from lumaretouch_engine import face_contour_runtime as CORE, people_state as PEOPLE
from lumaretouch_engine import skin_colour_support as SUPPORT
from lumaretouch_engine.people_geometry import FaceGeometry

ROOT = Path(__file__).resolve().parents[2]
ACTIVE = {'version': 2, 'linked': True, 'left': .4, 'right': .4}


def fixture(*, prior=(0., 0.), change=(0., 0.)):
    """Narrow synthetic owner contract; no anatomical validity is asserted."""
    shape = (101, 101)
    source = np.full((*shape, 3), .4, np.float32)
    landmarks = np.full((478, 3), .5, np.float32)
    evidence = {'backend': 'mediapipe', 'status': 'verified',
        'detector_model_sha256': 'b'*64, 'semantic_model_sha256': 'c'*64,
        'landmark_digest': hashlib.sha256(landmarks.tobytes()).hexdigest(),
        'source_width': shape[1], 'source_height': shape[0],
        'orientation': 'exif_normalized_once'}
    face = PEOPLE.new_face('a'*64, [.3, .2, .7, .8], evidence)
    state = {'faces': {face['face_instance_id']: face}}
    ref = PEOPLE.face_ref(face)
    analysis = {'face_ref': deepcopy(ref), 'evidence': deepcopy(evidence),
        'landmarks': landmarks, 'excluded': np.zeros(shape, np.float32),
        'skin': np.ones(shape, np.float32), 'face_skin': np.ones(shape, np.float32),
        'face_skin_observation': {'contract': SUPPORT.CONTRACT,
            'source_sha256': ref['asset_sha256'], 'semantic_model_sha256': 'c'*64,
            'producer_width': shape[1], 'producer_height': shape[0]}}
    automatic = SimpleNamespace(
        evaluate=lambda points: np.tile(prior, (len(points), 1)), resident_bytes=lambda: 0)
    field = FaceGeometry(ref['face_instance_id'], shape, automatic, (None,)*4)
    control_facts = {f'{key}/{side}': {'requested': True, 'applied': True, 'reason': None}
                     for key in C.KEYS for side in C.SIDES}
    contour = SimpleNamespace(state={'synthetic_field_double': True}, facts=control_facts,
        evaluate=lambda points: np.tile(change, (len(points), 1)), resident_bytes=lambda: 64)
    return field, state, ref, analysis, source, contour


def test_new_version_and_portable_neutral_are_not_legacy_aliases():
    assert S.OP == 'lnx.slim_face.v2'
    assert S.CONTROL_ID == 'LNX-REF-PC-32466-C-da1d54e292'
    assert S.VERSION == 2 and S.KEYS == ('linked', 'left', 'right')
    assert S.neutral() == {'version': 2, 'linked': True, 'left': 0., 'right': 0.}
    assert S.check(None) == S.neutral() and not S.active(None)
    assert S.neutral() is not S.neutral()
    value = {'version': 2, 'linked': False, 'left': -1, 'right': 1}
    checked = S.check(value)
    assert checked == value and checked is not value
    assert type(checked['left']) is type(checked['right']) is float
    assert S.preset(value) == checked


@pytest.mark.parametrize('value', [
    {}, [], False, {'version': 1, 'linked': True, 'left': 0., 'right': 0.},
    {'version': True, 'linked': True, 'left': 0., 'right': 0.},
    {'version': 2., 'linked': True, 'left': 0., 'right': 0.},
    {'version': 2, 'amount': .4}, {'slim_face': .4},
    {**ACTIVE, 'source': 'a'*64}, {**ACTIVE, 'mask': []},
    {**ACTIVE, 'linked': 1}, {**ACTIVE, 'linked': 'true'},
])
def test_only_explicit_bilateral_v2_shape_is_accepted(value):
    with pytest.raises(ValueError):
        S.check(value)


@pytest.mark.parametrize('side', S.SIDES)
@pytest.mark.parametrize('amount', [True, False, None, '0', [], {},
    float('nan'), float('inf'), -float('inf'), -1.00001, 1.00001, 10**1000])
def test_each_side_requires_strict_finite_signed_amount(side, amount):
    with pytest.raises(ValueError):
        S.check({**ACTIVE, side: amount})


def test_linking_preserves_unequal_intent_until_explicit_linked_adjustment():
    original = {'version': 2, 'linked': False, 'left': -.2, 'right': .7}
    changed = S.adjust(original, 'left', -.6)
    assert changed == {**original, 'left': -.6} and original['left'] == -.2
    relinked = S.link(changed, True)
    assert relinked == {**changed, 'linked': True}
    assert S.adjust(relinked, 'right', .3) == {
        'version': 2, 'linked': True, 'left': .3, 'right': .3}
    assert S.link(relinked, False) == {**relinked, 'linked': False}
    with pytest.raises(ValueError): S.adjust(original, 'viewer-left', .2)
    with pytest.raises(ValueError): S.adjust(original, 'left', True)
    with pytest.raises(ValueError): S.link(original, 1)


@pytest.mark.parametrize('recipe', [None, S.neutral(),
    {'version': 2, 'linked': False, 'left': -0., 'right': 0.}])
def test_neutral_has_no_dependency_or_anatomy_or_other_intent_requirement(recipe):
    original = object()
    # Any import attempted from the neutral path is a dependency regression.
    # Deliberately unusable source/analysis/legacy/contour inputs stay untouched.
    with patch('builtins.__import__', side_effect=AssertionError('neutral dependency')):
        assert S.check_coexistence(recipe, object(), object()) == S.check(recipe)
        assert PORT.append(original, None, None, None, None, recipe,
                           object(), object()) == (original, None)


@pytest.mark.parametrize('left,right,linked', [
    (1., 1., True), (-1., -1., True), (.2, -.7, False), (0., .4, False), (.3, .6, True)])
def test_exact_six_contour_signs_and_subject_sides(left, right, linked):
    recipe = {'version': 2, 'linked': linked, 'left': left, 'right': right}
    before = deepcopy(recipe)
    result = S.contour_recipe(recipe)
    assert result == {'version': 1,
        'temple': {'linked': linked, 'left': -left, 'right': -right},
        'cheekbone': {'linked': linked, 'left': left, 'right': right},
        'jaw': {'linked': linked, 'left': -left, 'right': -right}}
    assert recipe == before
    assert len({id(result[key]) for key in C.KEYS}) == 3


@pytest.mark.parametrize('legacy_amount', [-1., -.01, .01, 1., '.4'])
def test_active_legacy_slim_is_refused_not_converted_or_cleared(legacy_amount):
    recipe = deepcopy(ACTIVE); contour = C.neutral()
    before = deepcopy((recipe, contour))
    with patch.object(CONTOUR, 'append') as append:
        with pytest.raises(ValueError, match='legacy lnx.deform.v1/slim_face'):
            PORT.append(None, None, None, None, None, recipe, legacy_amount, contour)
    append.assert_not_called()
    assert (recipe, contour) == before


@pytest.mark.parametrize('key', C.KEYS)
@pytest.mark.parametrize('side', C.SIDES)
def test_any_active_standalone_contour_is_refused_before_append(key, side):
    contour = C.neutral(); contour[key].update(linked=False)
    contour[key][side] = -.1
    before = deepcopy(contour)
    with patch.object(CONTOUR, 'append') as append:
        with pytest.raises(ValueError, match='active lnx.face_contour.v1'):
            PORT.append(None, None, None, None, None, ACTIVE, 0., contour)
    append.assert_not_called()
    assert contour == before


def test_coexistence_uses_existing_checkers_and_never_rewrites_recipe():
    from lumaretouch_engine.ops import deform as D
    recipe = {'version': 2, 'linked': False, 'left': 0., 'right': -.4}
    contour = C.neutral(); contour['temple']['linked'] = False
    with patch.object(D, 'check_amounts', wraps=D.check_amounts) as legacy_check, \
            patch.object(C, 'check', wraps=C.check) as contour_check:
        checked = S.check_coexistence(recipe, '0', contour)
    legacy_check.assert_called_once_with({'slim_face': '0'})
    assert contour_check.call_args_list[0].args[0] is contour
    assert checked == recipe and checked is not recipe
    assert contour['temple']['linked'] is False
    for legacy in (float('nan'), float('inf'), 1.1, 'bad'):
        with pytest.raises(ValueError): S.check_coexistence(recipe, legacy, contour)
    with pytest.raises(ValueError): S.check_coexistence(recipe, 0., {'version': 1})


def test_adapter_preserves_exact_inputs_guard_object_and_unedited_build_facts():
    inputs = tuple(object() for _ in range(5))
    guarded = object(); facts = {'temple/left': {'requested': True, 'applied': True}}
    before = deepcopy(facts)
    with patch.object(CONTOUR, 'append', return_value=(guarded, facts)) as append:
        result, report = PORT.append(*inputs, ACTIVE, 0., C.neutral())
    append.assert_called_once()
    assert all(actual is expected for actual, expected in zip(append.call_args.args[:5], inputs))
    assert result is guarded and report['contour_facts'] is facts and facts == before
    assert report['contour_recipe'] is append.call_args.args[5]
    assert report['recipe'] == ACTIVE and report['recipe'] is not ACTIVE
    assert report['operation_id'] == S.OP and report['version'] == 2
    assert report['policy'] == 'corrected-compound-contour-v2'
    assert report['profile'] == {
        'contour_operation_id': C.OP, 'region_gain_of_face_width': .035,
        'legacy_operation_id': 'lnx.deform.v1', 'legacy_peak_of_face_width': .11,
        'legacy_numeric_or_appearance_equivalent': False}


@pytest.mark.parametrize('reason', ['foreign face window', 'occlusion', 'native ABI unavailable',
    'identity anchor conflict', 'control attenuation', 'fold risk', 'source footprint'])
def test_delegate_refusals_and_their_facts_propagate_without_fallback(reason):
    refusal = ValueError(reason); refusal.facts = {'guard': reason}
    with patch.object(CONTOUR, 'append', side_effect=refusal) as append:
        with pytest.raises(ValueError) as caught:
            PORT.append(None, None, None, None, None, ACTIVE, 0., C.neutral())
    assert caught.value is refusal and caught.value.facts == {'guard': reason}
    append.assert_called_once()


def test_real_boundary_forwards_exact_evidence_source_and_all_retained_neighbors():
    field, state, ref, analysis, source, contour = fixture()
    own = state['faces'][ref['face_instance_id']]
    for index, (enabled, manual, status) in enumerate(
            ((False, False, 'verified'), (True, True, 'unresolved'))):
        other = deepcopy(own)
        other.update(face_instance_id=f'neighbor-{index}', enabled=enabled, manual=manual,
                     box=[.05+index*.2, .1, .15+index*.2, .4])
        other['evidence']['status'] = status
        state['faces'][other['face_instance_id']] = other
    foreign = deepcopy(own); foreign.update(face_instance_id='other-source', asset_sha256='f'*64)
    state['faces']['other-source'] = foreign
    before = source.copy()
    with patch.object(CORE, 'build', return_value=contour) as build:
        result, report = PORT.append(field, state, ref, analysis, source, ACTIVE, 0., C.neutral())
    assert type(result) is CONTOUR.ContouredFace
    assert result.prefix is field and result.automatic is field.automatic
    assert result.fields == (*field.fields, contour) and field.fields == (None,)*4
    assert result.face_instance_id == ref['face_instance_id'] and result.shape == source.shape[:2]
    build.assert_called_once()
    assert build.call_args.args[0] is analysis['landmarks']
    assert build.call_args.args[1] == S.contour_recipe(ACTIVE)
    assert build.call_args.args[2] is source
    assert build.call_args.args[3] is analysis['excluded']
    assert build.call_args.kwargs['analysis'] is analysis
    assert build.call_args.kwargs['backend'] == own['evidence']['backend']
    assert build.call_args.kwargs['protected_boxes'] == ((.05, .1, .15, .4), (.25, .1, .35, .4))
    assert result.protected_boxes == build.call_args.kwargs['protected_boxes']
    assert report['contour_facts'] is contour.facts
    np.testing.assert_array_equal(source, before)


@pytest.mark.parametrize('change', ['stale_ref', 'disabled', 'digest', 'foreign_field',
    'repeat', 'grid', 'source_observation', 'backend'])
def test_real_owner_and_evidence_guards_are_not_bypassed(change):
    field, state, ref, analysis, source, contour = fixture()
    if change == 'stale_ref': ref = {**ref, 'analysis_revision': ref['analysis_revision']+1}
    elif change == 'disabled': state['faces'][ref['face_instance_id']]['enabled'] = False
    elif change == 'digest': analysis['landmarks'][0, 0] += .001
    elif change == 'foreign_field': field = FaceGeometry('another-face', field.shape, field.automatic, field.fields)
    elif change == 'repeat': field = FaceGeometry(field.face_instance_id, field.shape, field.automatic, (*field.fields, contour))
    elif change == 'grid': field = FaceGeometry(field.face_instance_id, (64, 64), field.automatic, field.fields)
    elif change == 'source_observation': analysis['face_skin_observation']['source_sha256'] = 'f'*64
    else:
        analysis['evidence']['backend'] = 'synthetic'
        state['faces'][ref['face_instance_id']]['evidence']['backend'] = 'synthetic'
    with patch.object(CORE, 'build') as build, pytest.raises(ValueError):
        PORT.append(field, state, ref, analysis, source, ACTIVE, 0., C.neutral())
    build.assert_not_called()


def test_active_missing_face_skin_has_no_landmarks_only_or_merged_skin_fallback():
    field, state, ref, analysis, source, _ = fixture()
    analysis['face_skin'] = analysis['face_skin_observation'] = None
    with patch.object(CORE, 'build_controls') as controls, pytest.raises(ValueError, match='authenticated face_skin'):
        PORT.append(field, state, ref, analysis, source, ACTIVE, 0., C.neutral())
    controls.assert_not_called()


@pytest.mark.parametrize('mode', ['missing', 'no_state', 'refused'])
def test_real_boundary_never_publishes_missing_or_partially_refused_controls(mode):
    field, state, ref, analysis, source, contour = fixture()
    if mode == 'missing': contour = None
    elif mode == 'no_state': contour.state = None
    else: contour.facts['jaw/right'].update(applied=False, reason='occluded')
    with patch.object(CORE, 'build', return_value=contour), pytest.raises(ValueError):
        PORT.append(field, state, ref, analysis, source, ACTIVE, 0., C.neutral())
    assert field.fields == (None,)*4


@pytest.mark.parametrize('stage', ['output', 'before', 'after'])
def test_returned_guard_still_checks_all_composed_foreign_face_footprints(stage):
    prior = {'output': (30., 0.), 'before': (20., 0.), 'after': (25., 0.)}[stage]
    field, state, ref, analysis, source, contour = fixture(prior=prior, change=(-5., 0.))
    other = deepcopy(state['faces'][ref['face_instance_id']])
    other.update(face_instance_id='protected', box=[.49, .49, .51, .51], enabled=False)
    state['faces']['protected'] = other
    with patch.object(CORE, 'build', return_value=contour):
        result, _ = PORT.append(field, state, ref, analysis, source, ACTIVE, 0., C.neutral())
    point = np.array([[50. if stage == 'output' else 70., 50.]])
    with pytest.raises(ValueError, match='another retained face'):
        result.evaluate(point)


def test_returned_guard_refuses_out_of_source_without_border_fill():
    field, state, ref, analysis, source, contour = fixture(change=(3., 0.))
    with patch.object(CORE, 'build', return_value=contour):
        result, _ = PORT.append(field, state, ref, analysis, source, ACTIVE, 0., C.neutral())
    with pytest.raises(ValueError, match='outside the genuine source'):
        result.evaluate(np.array([[1., 50.]]))


def test_legacy_algorithm_source_is_preserved_not_rebound_to_new_profile():
    tree = ast.parse((ROOT/'engine/src/lumaretouch_engine/ops/deform.py').read_text())
    expected = {
        'FACE_OVAL_LEFT': (234, 127, 162, 21, 54, 103, 67, 109),
        'FACE_OVAL_RIGHT': (454, 399, 356, 288, 314, 405, 338, 308),
        'SLIM_PEAK_OF_FACE_W': .11,
    }
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in expected:
                    assert ast.literal_eval(node.value) == expected.pop(target.id)
    assert not expected
    controls = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'controls')
    # Captured from the untouched legacy source, not from a new implementation.
    digest = hashlib.sha256(ast.dump(controls, include_attributes=False).encode()).hexdigest()
    assert digest == 'b00a4f6c888e374afaf232f5e01083525d258ba04be5b3a698d1e5141910d000'
    native = ast.parse((ROOT/'engine/src/lumaretouch_engine/face_contour_native.py').read_text())
    gain = next(ast.literal_eval(node.value) for node in native.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'REGION_GAIN' for target in node.targets))
    assert gain == S.REGION_GAIN_OF_FACE_WIDTH == .035
    assert S.LEGACY_PEAK_OF_FACE_WIDTH == .11 and gain != S.LEGACY_PEAK_OF_FACE_WIDTH
