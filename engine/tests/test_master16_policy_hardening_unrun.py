"""AUTHORED / UNRUN: explicit PNG16/TIFF16 neutral-classifier contracts.

No test collection, product import, render, decode, inference or build was run
while authoring. These cases do not establish numeric/visual/codec acceptance.
The live helper intentionally does not own people; frozen export owns that gate.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from lumaretouch_engine.master16_policy import Master16PolicyMixin as POLICY
from lumaretouch_engine import colour_grading_state as CG, selective_colour_state as SC
from lumaretouch_engine import primary_calibration_state as PC, extended_tone_state as ET
from lumaretouch_engine import photo_detail_state as PD, id_background_state as ID
from lumaretouch_engine import local_mask_state as MASK, id_background_support as SUPPORT


FAMILIES = ('colour_grading', 'selective_colour', 'primary_calibration',
            'extended_tone', 'photo_detail', 'id_background')
SOURCE = {'sha256': 'a' * 64, 'width': 32, 'height': 24}


def neutral_live():
    # Independent fixture, not the implementation's adaptation/default map.
    return SimpleNamespace(_strength=0., _grade=(0., 0., 0., 1.), _grade_scope='all',
        _lut=None, _lut_amount=0., _repair_ops=[], _light_ops=[], _deform={'amounts': {}},
        _crop_rect=(0., 0., 1., 1.), _crop_rotation=0., _exposure=(0.,) * 7,
        _hsl=(0.,) * 24, _enhance={'amounts': {}}, _fabric_amount=0., _bg={})


def blockers(patch, mode):
    if mode == 'frozen':
        return POLICY._master16_snapshot_blockers(patch)
    owner = neutral_live()
    for key, value in patch.items():
        setattr(owner, key if key.startswith('_') else '_' + key, value)
    return POLICY._master16_blockers(owner, scale=1, sharpen=0.)


def id_recipe():
    mask = MASK.empty(); mask['source'] = deepcopy(SOURCE)
    mask['recipe']['objects'] = [{'id': 'reviewed-subject', 'name': 'Subject',
        'kind': 'brush', 'operation': 'add', 'enabled': True, 'opacity': 1.,
        'feather': 0., 'points': [[.5, .5]], 'axes': [[.1, 0.], [0., .1]]}]
    value = ID.empty(); value.update(enabled=True, source=deepcopy(SOURCE))
    value['support']['subject'] = {'version': 1, 'category': 'subject',
        'reviewed': True, 'mask': mask, 'recipe_sha256': SUPPORT.digest(mask)}
    return ID.check(value)


def recipe(key, *, active):
    if key == 'colour_grading':
        value = CG.neutral()
        value['shadows'].update(hue=135., saturation=7. if active else 0.)
        value.update(blending=80., balance=-30.)  # Neutral without sat/luminance.
    elif key == 'selective_colour':
        value = SC.neutral(); value['method'] = 'absolute'
        value['ranges']['reds']['cyan'] = -8. if active else 0.
    elif key == 'primary_calibration':
        value = PC.neutral(); value['red']['hue'] = 4. if active else 0.
    elif key == 'extended_tone':
        value = ET.default(); value['monochrome'] = active  # No numeric controls.
    elif key == 'photo_detail':
        value = PD.default(); value.update(sharpen_radius=2., luma_detail=80.,
            chroma_smoothness=90., luma_amount=5. if active else 0.)
    else:
        value = id_recipe(); value['opacity'] = .75 if active else 0.
    return value


@pytest.mark.parametrize('mode', ('live', 'frozen'))
@pytest.mark.parametrize('key', FAMILIES)
@pytest.mark.parametrize('active', (False, True))
def test_each_family_uses_actual_pixel_activity_and_preserves_recipe(mode, key, active):
    value = recipe(key, active=active); before = deepcopy(value)
    assert bool(blockers({key: value}, mode)) is active
    assert value == before


@pytest.mark.parametrize('mode', ('live', 'frozen'))
def test_disabled_amounts_and_legacy_omission_remain_neutral(mode):
    assert blockers({}, mode) == []
    assert blockers({'extended_tone': dict(ET.default(), enabled=False, monochrome=True, clarity=20.),
        'photo_detail': dict(PD.default(), enabled=False, sharpen_amount=50.),
        'id_background': dict(id_recipe(), enabled=False)}, mode) == []
    # Only these canonical validators explicitly allow legacy None.
    assert blockers({'extended_tone': None, 'photo_detail': None, 'id_background': None}, mode) == []


@pytest.mark.parametrize('mode', ('live', 'frozen'))
@pytest.mark.parametrize('key', FAMILIES)
def test_present_incomplete_or_unknown_family_recipe_never_becomes_neutral(mode, key):
    for invalid in ({}, {**recipe(key, active=False), 'future_effect': 0}):
        with pytest.raises(ValueError):
            blockers({key: invalid}, mode)


@pytest.mark.parametrize('mode', ('live', 'frozen'))
@pytest.mark.parametrize('key', ('colour_grading', 'selective_colour', 'primary_calibration'))
def test_strict_native_colour_null_is_not_legacy_omission(mode, key):
    with pytest.raises(ValueError):
        blockers({key: None}, mode)


@pytest.mark.parametrize('mode', ('live', 'frozen'))
@pytest.mark.parametrize('key', FAMILIES)
def test_nan_in_zero_or_disabled_family_is_validated_before_activity(mode, key):
    value = recipe(key, active=False)
    if key == 'colour_grading': value['shadows']['hue'] = float('nan')
    elif key == 'selective_colour': value['ranges']['reds']['cyan'] = float('nan')
    elif key == 'primary_calibration': value['red']['hue'] = float('nan')
    elif key == 'extended_tone': value.update(enabled=False, clarity=float('nan'))
    elif key == 'photo_detail': value.update(enabled=False, sharpen_radius=float('nan'))
    else: value['shadow']['opacity'] = float('nan')
    with pytest.raises(ValueError):
        blockers({key: value}, mode)


@pytest.mark.parametrize('mode', ('live', 'frozen'))
def test_id_spill_and_original_shadow_are_validated_even_with_zero_opacity(mode):
    from lumaretouch_engine import spill_removal_state as SP, original_shadow_state as OS
    value = ID.with_original_shadow(ID.with_spill(id_recipe(), SP.neutral()), OS.neutral())
    value['opacity'] = 0.
    assert blockers({'id_background': value}, mode) == []
    for child, leaf in (('spill', 'strength'), ('original_shadow', 'strength')):
        invalid = deepcopy(value); invalid[child][leaf] = float('nan')
        with pytest.raises(ValueError): blockers({'id_background': invalid}, mode)
    invalid = deepcopy(value); invalid['support']['subject']['recipe_sha256'] = 'b' * 64
    with pytest.raises(ValueError): blockers({'id_background': invalid}, mode)


@pytest.mark.parametrize('mode', ('live', 'frozen'))
@pytest.mark.parametrize('patch', [
    {'grade': (float('nan'), 0., 0., 0.)}, {'grade': (0., 0., 0., float('inf'))},
    {'grade': (0., 0., 0.)}, {'grade': None},
    {'exposure': (float('nan'), 0., 0.)}, {'exposure': (0.,) * 3 + (float('nan'),) + (0.,) * 3},
    {'exposure_ref_k': float('nan')}, {'exposure': None}, {'wb_options': None},
    {'hsl': (float('nan'),) + (0.,) * 23}, {'hsl': (0.,) * 23},
    {'deform': {'amounts': {'slim_face': float('nan')}}},
    {'deform': {'amounts': {'future_effect': 0.}}}, {'deform': {'amounts': None}}, {'deform': None},
    {'enhance': {'amounts': {'sclera': float('nan')}}},
    {'enhance': {'amounts': {'future_effect': 0.}}}, {'enhance': {'amounts': None}}, {'enhance': None},
    {'lut_amount': float('nan')}, {'lut_amount': -0.1}, {'lut_amount': float('inf')},
])
def test_malformed_legacy_scalar_state_refuses_instead_of_identity(mode, patch):
    with pytest.raises((ValueError, TypeError)):
        blockers(patch, mode)


@pytest.mark.parametrize('mode', ('live', 'frozen'))
def test_legacy_three_scalar_exposure_and_zero_amount_grade_are_neutral(mode):
    assert blockers({'exposure': (0., 0., 0.), 'grade': (.02, 0., 0., 0.)}, mode) == []


@pytest.mark.parametrize('mode', ('live', 'frozen'))
def test_wrinkle_unlock_is_metadata_but_all_other_valid_enhance_families_block(mode):
    from lumaretouch_engine.ops import enhance as ENH
    from lumaretouch_engine.facial_wrinkle_state import LINK_KEY
    assert blockers({'enhance': {'amounts': {LINK_KEY: 1}}}, mode) == []
    # ENH.is_identity checks only PIXEL_KEYS, which omits real effects here.
    for key in ENH.EFFECT_KEYS:
        assert blockers({'enhance': {'amounts': {LINK_KEY: 1, key: .2}}}, mode), key
    for invalid in (True, .5, float('nan')):
        with pytest.raises(ValueError):
            blockers({'enhance': {'amounts': {LINK_KEY: invalid}}}, mode)


@pytest.mark.parametrize('value', (0, None, {}, False))
def test_unknown_frozen_top_level_key_is_not_a_neutral_extension(value):
    with pytest.raises(ValueError, match='Unknown frozen'):
        POLICY._master16_snapshot_blockers({'future_pixel_effect': value})


@pytest.mark.parametrize('value', ({}, False, [], {'bank': None}))
def test_malformed_present_body_envelope_is_not_omission(value):
    with pytest.raises(ValueError):
        POLICY._master16_snapshot_blockers({'body_pose': value})


def test_body_envelope_validation_does_not_weaken_existing_bank_gate():
    from lumaretouch_engine import body_pose_state as B, arm_shape_project as P
    from lumaretouch_engine.body_pose_evidence import ORIENTATION
    value = P.snapshot(B.empty(), {**SOURCE, 'orientation': ORIENTATION})
    assert POLICY._master16_snapshot_blockers({'body_pose': value}) == []
    for key, replacement in (('body_refs', [{}]), ('body_operation_order', {}), ('source', SOURCE)):
        invalid = deepcopy(value); invalid[key] = replacement
        with pytest.raises(ValueError): POLICY._master16_snapshot_blockers({'body_pose': invalid})


def test_orphan_derived_contexts_and_body_proof_never_pass_through():
    from lumaretouch_engine.export_snapshot_schema import SNAPSHOT_FIELDS
    for key in SNAPSHOT_FIELDS:
        if key.startswith('creative_') and key.endswith('_context'):
            assert POLICY._master16_snapshot_blockers({key: {}}), key
    assert POLICY._master16_snapshot_blockers({'body_pose_source_proof': {}})


@pytest.mark.parametrize('mode', ('live', 'frozen'))
def test_existing_repair_light_and_retained_liquify_remain_conservative(mode):
    from lumaretouch_engine import manual_liquify_state as ML, local_grade_layers as LG
    for field in ('repair_ops', 'light_ops'):
        assert blockers({field: [object()]}, mode)
    value = ML.empty(); value.update(source=deepcopy(SOURCE), strokes=[{
        'id': 'frozen-mask', 'mode': 'freeze', 'axes': [[.1, 0.], [0., .1]],
        'points': [[.5, .5, 1., 0.]], 'density': 0., 'pressure': 0., 'rate': 0.,
        'fixed_edges': False, 'direction': 1}])
    assert blockers({'manual_liquify': value}, mode)  # Zero rate/freeze still retained.
    groups = LG.empty(); groups['layers'] = [{'id': 'neutral-enabled', 'name': 'Retained',
        'enabled': True, 'grade': [0., 0., 0., 1.], 'mask': MASK.empty()}]
    if mode == 'live':
        owner = neutral_live(); owner._local_grade_layers = groups
        assert POLICY._master16_blockers(owner, scale=1, sharpen=0.)
    else: assert blockers({'local_grade_groups': groups}, mode)


def test_frozen_target_never_reads_or_mutates_another_active_document():
    owner = neutral_live(); owner._colour_grading = recipe('colour_grading', active=True)
    neutral = {}; edited = {'photo_detail': recipe('photo_detail', active=True)}
    before = deepcopy(vars(owner)); frozen_before = deepcopy(edited)
    assert POLICY._master16_snapshot_blockers(neutral) == []
    assert POLICY._master16_snapshot_blockers(edited)
    assert vars(owner) == before and edited == frozen_before


@pytest.mark.parametrize('disabled_face', (False, True))
@pytest.mark.parametrize('value,blocked', ((0., False), (.2, True), (False, True)))
def test_no_enabled_faces_validate_all_people_leaves_without_faking_detection(disabled_face, value, blocked):
    from lumaretouch_engine import people_state as S, people_algorithms as A
    from lumaretouch_engine.people_export import fastpath_blocker
    state = S.empty()
    if disabled_face:
        evidence = dict(backend='fixture', detector_model_sha256=None, semantic_model_sha256=None,
            landmark_digest=None, status='synthetic', source_width=32, source_height=24,
            orientation='exif_normalized_once')
        face = S.new_face(SOURCE['sha256'], [.1, .1, .6, .6], evidence); face['enabled'] = False
        state['faces'][face['face_instance_id']] = face
    state['overrides'] = [dict(scope='all_people', target_id=SOURCE['sha256'],
        operation_id=A.LIP, parameter_path='/brightness', value=value)]
    before = deepcopy(state)
    snap = {'state': state, 'asset_sha256': SOURCE['sha256']}
    assert fastpath_blocker(snap) is blocked
    assert bool(POLICY._master16_snapshot_blockers({'people': snap})) is blocked
    assert state == before


@pytest.mark.parametrize('operation,path', (('future.operation', '/value'), ('lnx.lip_makeup.v1', '/unknown')))
def test_no_face_unknown_zero_overrides_do_not_pass_through(operation, path):
    from lumaretouch_engine import people_state as S
    from lumaretouch_engine.people_export import fastpath_blocker
    state = S.empty(); state['overrides'] = [dict(scope='all_people', target_id=SOURCE['sha256'],
        operation_id=operation, parameter_path=path, value=0.)]
    assert fastpath_blocker({'state': state, 'asset_sha256': SOURCE['sha256']})


@pytest.mark.parametrize('codec', ('png', 'tif'))
@pytest.mark.parametrize('key', FAMILIES)
def test_explicit_native16_routes_each_real_edit_without_changing_original_policy(codec, key):
    import ast
    from test_export_original_native16_unrun import native16_route
    guard = compile(ast.Expression(native16_route().test), '<explicit-native16-route>', 'eval')
    snap = {key: recipe(key, active=True)}
    assert eval(guard, {'__builtins__': {}}, {'decision': None, 'watermark': None,
        'self': POLICY, 'snap_i': snap})
    def forbidden(_snapshot): raise AssertionError('Original must not consult classifier')
    assert eval(guard, {'__builtins__': {}}, {'decision': {'codec': codec, 'bits': 16},
        'watermark': None, 'self': SimpleNamespace(_master16_snapshot_blockers=forbidden),
        'snap_i': snap})


def test_body_active_missing_support_and_disabled_malformed_claims_still_refuse():
    from lumaretouch_engine import body_pose_evidence as E, body_pose_state as B
    from lumaretouch_engine import arm_shape_project as P, shoulder_shape_state as S
    # Synthetic zero-confidence schema fixture only; never authorizes a warp.
    source = {**SOURCE, 'orientation': E.ORIENTATION}
    points = [dict(index=i, x=.5, y=.5, z=0., visibility=0., presence=0.) for i in range(33)]
    record = E.create(source_frame=source, values=points, backend_version='synthetic-only',
        backend_code_sha256='b' * 64, model_id='synthetic-only', model_sha256='c' * 64,
        input_rgb_sha256='d' * 64, input_dimensions=(32, 24))
    bank = B.add_run(B.empty(), dict(source=source, records=[record], detector_limit=4,
        limit_reached=False, census_complete=False))
    ref = record['body_ref']
    changed = B.set_recipe(bank, ref, S.adjust(S.neutral(), 'width', 'left', .2))
    assert POLICY._master16_snapshot_blockers({'body_pose': P.snapshot(changed, source)})
    disabled = B.set_operation_enabled(changed, ref, S.OPERATION_ID, False)
    assert POLICY._master16_snapshot_blockers({'body_pose': P.snapshot(disabled, source)}) == []
    invalid = P.snapshot(disabled, source)
    item = invalid['bank']['state']['bodies'][ref['body_instance_id']]['operations'][S.OPERATION_ID]
    item['support_sha256'] = 'e' * 64  # Missing source-owned support, even disabled.
    invalid['bank']['content_sha256'] = E.content_digest(invalid['bank']['state'])
    with pytest.raises(ValueError): POLICY._master16_snapshot_blockers({'body_pose': invalid})


@pytest.mark.parametrize('mode', ('live', 'frozen'))
def test_enabled_recovery_is_not_treated_as_an_empty_pixel_edit(mode):
    from lumaretouch_engine import effect_recovery_state as R
    value = R.empty(); value.update(source=deepcopy(SOURCE), targets=[{
        'target': 'skin_smoothing', 'enabled': True,
        'recipe': id_recipe()['support']['subject']['mask']['recipe']}])
    assert blockers({'effect_recovery': value}, mode)


def test_native16_both_routes_keep_the_existing_destination_owner():
    import ast
    from test_export_original_native16_unrun import native16_route
    route = native16_route()
    for branch in (route.body, route.orelse):
        calls = [node for statement in branch for node in ast.walk(statement)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == 'EDR'
            and node.func.attr == 'run']
        assert len(calls) == 1
        assert [arg.id for arg in calls[0].args[:2]] == ['destination_plan', 'entry_id']
