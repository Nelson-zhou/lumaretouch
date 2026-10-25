"""AUTHORED / UNRUN. Specifications, not numerical/memory acceptance evidence.

This source-only task did not import or run this file. Runtime authorization is
required before executing these fixtures or the actual product pipeline.
"""
from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest

from lumaretouch_engine import creative_edited_capture_admission as A
from lumaretouch_engine.creative_document_import_bounded import ImportMemoryPlan
from lumaretouch_engine.export import ExportSpec
from lumaretouch_engine.export_recipe import build_export_spec
from lumaretouch_engine.ops import curves, levels, parametric_curves
from lumaretouch_engine.ops.lut import CubeLut
from lumaretouch_engine import colour_grading_state as CG, selective_colour_state as SC
from lumaretouch_engine import primary_calibration_state as PC, white_balance_recipe as WB


def snapshot():
    return dict(strength=0., params=dict(radius=12, eps=6e-4, texture_radius=4,
        broad_gain=0., mid_gain=0., detail_gain=1.), grade=(0., 0., 0., 1.),
        grade_scope='all', exposure=(.3, 0., 0., 0., 0., 0., 0.),
        exposure_ref_k=None, wb_options=WB.default_options(), hsl=(0.,) * 24,
        curves=curves.default_curves(), levels=levels.default_levels(),
        lut=None, lut_amount=0., light={'exposure': .6, 'radius': 24},
        light_ops=[], repair_ops=[], deform={'amounts': {}, 'built': False},
        enhance={'amounts': {}, 'built': False, 'box': None}, channel=None, precompute=None,
        crop_rect=(0., 0., 1., 1.), crop_rotation=0., device='cpu', scale=1,
        upscale_backend='lanczos3', sharpen=0., _bg={})


def metadata(width=1600, height=1200, bits=8, original=1234, icc=b''):
    plan = ImportMemoryPlan('PNG', width, height, bits, original, len(icc),
        width * height * (6 if bits == 16 else 3), 32 * 1024 * 1024,
        0, 0, (('header', 2 * original),), A.MAX_WORK_BYTES)
    return dict(format='PNG', width=width, height=height, bits=bits, original_bytes=original,
                icc=icc, orientation=1, working_orientation=1, import_plan=plan)


def build(value):
    spec, skipped = build_export_spec(value, 1200, 1600, for_document=True)
    assert skipped == []
    return spec


def test_combined_supported_colours_keep_the_original_recipe():
    value = snapshot()
    value.update(exposure=(.5, 120., .05, 7., -5., 8., 3.),
        hsl=(2., 3., -4.) + (0.,) * 21, grade=(.01, .02, .03, .5),
        crop_rect=(.1, .2, .9, .8), crop_rotation=89.9,
        colour_grading=CG.neutral(), selective_colour=SC.neutral(), primary_calibration=PC.neutral())
    value['wb_options']['picked_gains'] = [1.1, .95, 1.]
    value['curves']['master'] = [[0., 0.], [.4, .45], [1., 1.]]
    value['colour_grading']['shadows']['saturation'] = 7.
    value['selective_colour']['ranges']['reds']['cyan'] = 8.
    value['primary_calibration']['red']['hue'] = 4.
    before = deepcopy(value)
    result = A.classify_snapshot(value)
    assert result.eligible, result.reasons
    assert {'native-full-colour', 'primary-calibration'} <= set(result.features)
    assert value == before
    assert A.validate_spec(build(value), value).eligible
    assert value == before


def test_v3_curves_remain_recipes_and_never_require_compilation_for_admission(monkeypatch):
    value = snapshot()
    value['curves'].update(version=3, luminance=[[0., 0.], [.5, .6], [1., 1.]],
        luminance_space=curves.LUMINANCE_SPACE, parametric=parametric_curves.default_parametric())
    value['curves']['parametric']['highlights'] = 10.
    def forbidden(*_args, **_kwargs):
        raise AssertionError('No helper process during admission')
    monkeypatch.setattr(curves.subprocess, 'run', forbidden)
    assert A.classify_snapshot(value).eligible


def test_real_builder_neutral_objects_and_sky_private_nulls_are_admitted():
    value = snapshot()
    spec = build(value)
    assert spec._sky_replacement_immutable_input is None
    assert spec._sky_replacement_replay_key is None
    assert spec._common_recovery_recipe is None
    assert A.validate_spec(spec, value).eligible
    assert A.inspect_storage((value, spec)).retained_bytes == 0


@pytest.mark.parametrize('key,change', [
    ('strength', .1), ('channel', 'skin'), ('grade_scope', 'skin'),
    ('grade_mask', np.ones((2, 3), np.uint8)), ('scale', 2), ('sharpen', .1),
    ('body_pose', {}), ('creative_base', {}), ('export_skipped', ['missing effect']),
    ('crop_rotation', .5), ('crop_rotation', 89.5), ('crop_rotation', -89.5),
    ('device', 'cuda'), ('fabric_amount', .1), ('new_unpriced_effect', 0),
    ('semantic_colour_mask_assets', {'retained': b'asset'}),
    ('semantic_colour_binding', {'source': 'old'}), ('_bg', {'active': True}),
    ('_bg', {'active': False, 'key_recipe': {}}), ('people', {'unexpected': 'graph'}),
    ('lut', np.zeros((2, 2, 2, 3))), ('colour_grading', {}), ('photo_grain', {}),
])
def test_unsupported_family_is_never_rewritten_as_partial_recipe(key, change):
    value = snapshot()
    value[key] = change
    identity = value[key]
    assert not A.classify_snapshot(value).eligible
    assert value[key] is identity


@pytest.mark.parametrize('key', ('photo_detail', 'extended_tone', 'colour_editor', 'photo_grain'))
def test_heavy_recipe_families_decline_before_preparation(key):
    from lumaretouch_engine import photo_detail_state as PD, extended_tone_state as ET
    from lumaretouch_engine import colour_editor_state as CE, photo_grain_state as PG
    value = snapshot()
    if key == 'photo_detail':
        value[key] = dict(PD.default(), sharpen_amount=5.)
    elif key == 'extended_tone':
        value[key] = dict(ET.default(), monochrome=True)
    elif key == 'colour_editor':
        value[key] = dict(CE.neutral(), scope='local')
    else:
        value[key] = dict(PG.neutral(), strength=5.)
    assert not A.classify_snapshot(value).eligible


def test_dormant_id_and_local_source_do_not_pass_as_neutral():
    from lumaretouch_engine import id_background_state as ID, local_mask_state as LM
    for key, empty in (('id_background', ID.empty), ('local_masks', LM.empty)):
        value = snapshot()
        value[key] = empty()
        value[key]['source'] = {'sha256': 'a' * 64, 'width': 1600, 'height': 1200}
        assert not A.classify_snapshot(value).eligible


def test_disabled_unknown_group_still_declines():
    value = snapshot()
    value['local_grade_groups'] = {'version': 1, 'layers': [{'enabled': False}]}
    assert not A.classify_snapshot(value).eligible


def test_postbuild_recipe_drift_and_private_prepass_are_rejected():
    value = snapshot()
    spec = build(value)
    spec.exposure = (2.,) + (0.,) * 6
    with pytest.raises(A.AdmissionError, match='differs'):
        A.validate_spec(spec, value)
    assert spec.exposure[0] == 2.
    spec = build(value)
    spec._tone_prepass_ready = True
    with pytest.raises(A.AdmissionError, match='Unknown'):
        A.validate_spec(spec, value)


@pytest.mark.parametrize('field,value', [
    ('masks', np.zeros((1, 2, 3), np.float32)), ('grade_mask', np.zeros((2, 3), np.uint8)),
    ('landmarks', np.zeros((478, 3), np.float32)),
    ('manual_liquify_field', np.zeros((2, 3, 3), np.float32)),
    ('local_grade_fields', []), ('effect_recovery_fields', []),
    ('sky_replacement_prepared', {}), ('id_background_prepared', {}),
    ('studio_background_prepared', {}), ('bg_ref', (0., 0., 0.)),
    ('provenance_output', True), ('provenance_result', np.zeros((2, 3), np.float32)),
])
def test_postbuild_prepared_owners_are_not_hidden_by_neutral_recipe(field, value):
    recipe = snapshot()
    spec = build(recipe)
    setattr(spec, field, value)
    with pytest.raises(A.AdmissionError):
        A.validate_spec(spec, recipe)


def test_admission_never_calls_mutating_export_check(monkeypatch):
    value = snapshot()
    spec = build(value)
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Common mutable validation belongs downstream')
    monkeypatch.setattr(ExportSpec, 'check', forbidden)
    assert A.validate_spec(spec, value).eligible
    with pytest.raises(A.AdmissionError):
        A.validate_spec(spec, value, skipped=['missing effect'])


def test_private_source_context_is_scalar_only_not_permission_to_omit_effects():
    value = snapshot()
    spec = build(value)
    spec._creative_capture_original_source = dict(path='/original.png', file_stamp=[1, 2, 3, 4, 5],
        asset_sha256='b' * 64, document_id='document-a')
    assert A.validate_spec(spec, value).eligible
    assert A.inspect_storage(spec).retained_bytes == 0
    spec._creative_capture_original_source['pixels'] = np.ones((2, 3, 3), np.uint8)
    with pytest.raises(A.AdmissionError):
        A.inspect_storage(spec)


def test_whole_array_backing_and_distinct_view_copy_accounting():
    source = np.zeros((20, 30, 3), np.float32)
    first, second = source[:1, :1], source[-1:, -1:]
    census = A.inspect_storage({'first': first, 'repeat': first, 'second': second})
    assert census.total_bytes == source.nbytes
    assert census.array_copy_bytes == first.nbytes + second.nbytes
    assert census.array_count == 2
    assert source.flags.writeable and first.flags.writeable


def test_equal_bytes_are_charged_separately_but_views_share_actual_owner():
    a, b = bytes(bytearray(b'payload' * 100)), bytes(bytearray(b'payload' * 100))
    assert a == b and a is not b
    census = A.inspect_storage((a, a, b, np.frombuffer(a, dtype=np.uint8)))
    assert census.total_bytes == len(a) + len(b)
    assert len(census.owner_ids) == 2
    assert census.array_copy_bytes == len(a)


def test_baseline_excludes_only_actual_shared_terminal_owner():
    original = np.arange(120, dtype=np.float32)
    baseline = A.inspect_storage({'view': original[:2]})
    copy = original[:2].copy()
    current = A.inspect_storage((original[3:5], copy), baseline=baseline)
    assert current.retained_bytes == copy.nbytes
    assert current.total_bytes == original.nbytes + copy.nbytes


def test_face_precompute_is_counted_without_touching_flags():
    from lumaretouch_engine.face import FacePrecompute
    landmarks = np.zeros((478, 3), np.float32)
    mask = np.zeros((80, 60), np.float32)
    record = FacePrecompute(landmarks, {'skin': mask}, 'mediapipe', 0., 0., all_landmarks=[landmarks])
    census = A.inspect_storage(record)
    assert census.total_bytes == landmarks.nbytes + mask.nbytes
    assert census.array_copy_bytes == census.total_bytes
    assert census.validation_scratch_bytes >= 4 * mask.size
    assert landmarks.flags.writeable and mask.flags.writeable


def test_precopy_budget_accounts_for_face_count_multiplier_before_allocation():
    source = np.zeros((100, 200), np.float32)
    roots = ({'_precompute': source}, {'first_face': source, 'second_face': source})
    census = A.inspect_storage(roots)
    assert census.array_copy_bytes == source.nbytes
    required = census.total_bytes + 8 * census.array_copy_bytes + 9 * census.container_bytes + A.METADATA_RESERVE + census.validation_scratch_bytes
    assert A.admit_snapshot_copy(roots, max_bytes=required, copies=8) == census
    with pytest.raises(A.CaptureBudgetExceeded):
        A.admit_snapshot_copy(roots, max_bytes=required - 1, copies=8)
    assert source.flags.writeable


def test_unknown_property_hooks_never_execute():
    class Trap:
        @property
        def __dict__(self):
            raise AssertionError('Must not inspect arbitrary properties')
    with pytest.raises(A.AdmissionError, match='Unsupported'):
        A.inspect_storage(Trap())


def test_cycles_subclasses_object_arrays_and_unknown_backing_fail_closed():
    cycle = []; cycle.append(cycle)
    for value in (cycle, np.zeros(3, dtype=object),
                  np.zeros(3).view(type('ArraySubclass', (np.ndarray,), {})),
                  np.lib.stride_tricks.as_strided(np.zeros(3), shape=(10,), strides=(0,))):
        with pytest.raises(A.AdmissionError):
            A.inspect_storage(value)


def test_cube_cpu_storage_and_torch_upload_both_count():
    recipe = snapshot()
    grid = np.zeros((2, 2, 2, 3), np.float64)
    cube = CubeLut('3d', 2, grid)
    recipe.update(lut=cube, lut_amount=.5)
    assert A.classify_snapshot(recipe).eligible
    assert A.inspect_storage(recipe).total_bytes == grid.nbytes
    plan = A.plan_capture(metadata(), recipe, max_bytes=A.MAX_WORK_BYTES)
    assert dict(dict(plan.owners)['common-tile-render'])['lut-upload-copies'] == grid.size * 8
    assert grid.flags.writeable
    recipe['lut'] = replace(cube, kind='1d')
    assert not A.classify_snapshot(recipe).eligible


def test_actual_radius_halo_remains_when_strength_is_zero():
    recipe = snapshot()
    plan = A.plan_capture(metadata(), recipe, max_bytes=A.MAX_WORK_BYTES)
    assert plan.margin == 80
    assert plan.tile_pixels == min(1200, 1184) * min(1600, 1184)
    assert dict(dict(plan.owners)['common-tile-render'])['halo-colour-workspace'] == 512 * plan.tile_pixels
    recipe['params']['radius'] = 80
    larger = A.plan_capture(metadata(), recipe, max_bytes=A.MAX_WORK_BYTES)
    assert larger.tile_pixels > plan.tile_pixels
    with pytest.raises(A.AdmissionError):
        A.plan_capture(metadata(), recipe, max_bytes=A.MAX_WORK_BYTES, tile=512)


def test_named_phase_sums_and_exact_budget_boundary():
    recipe = snapshot()
    plan = A.plan_capture(metadata(), recipe, max_bytes=A.MAX_WORK_BYTES, retained_bytes=17_000_000)
    for phase, total in plan.phases:
        assert total == sum(amount for _, amount in dict(plan.owners)[phase])
    assert A.plan_capture(metadata(), recipe, max_bytes=plan.peak_bytes, retained_bytes=17_000_000).peak_bytes == plan.peak_bytes
    with pytest.raises(A.CaptureBudgetExceeded):
        A.plan_capture(metadata(), recipe, max_bytes=plan.peak_bytes - 1, retained_bytes=17_000_000)
    assert plan.runtime_verified is False


def test_native_finishing_and_transfer_keep_large_crop_backing():
    recipe = snapshot()
    recipe['colour_grading'] = CG.neutral()
    recipe['colour_grading']['global']['saturation'] = 10.
    recipe['crop_rect'] = (0., 0., 1., .1)
    plan = A.plan_capture(metadata(), recipe, max_bytes=A.MAX_WORK_BYTES)
    n, m = 1600 * 1200, plan.output_width * plan.output_height
    parts = dict(dict(plan.owners)['native-colour-finishing'])
    assert parts['retained-stitch-backing'] == 12 * n
    assert parts['native-input-output'] == 24 * m
    assert parts['validation-contiguous-return-reserve'] == 36 * m
    assert dict(dict(plan.owners)['rgb-to-canonical'])['output-rgb-backing'] == 12 * n
    assert dict(dict(plan.owners)['immutable-freeze'])['mutable-and-immutable-rgba'] == 32 * m


def test_png16_keeps_third_encoded_owner_and_full_precision_integer_storage():
    info = metadata(bits=16, original=123456)
    plan = A.plan_capture(info, snapshot(), max_bytes=A.MAX_WORK_BYTES)
    phases = dict(plan.owners)
    assert dict(phases['decode-icc'])['three-encoded-source-owners'] == 3 * info['original_bytes']
    assert dict(phases['decode-icc'])['decode-working-overlap'] == 64 * info['width'] * info['height']
    assert dict(phases['common-tile-render'])['integer-working-source'] == 6 * info['width'] * info['height']


@pytest.mark.parametrize('bits', (1, 2, 4, 8))
def test_lowbit_png_metadata_unchanged_while_working_storage_is_rgb8(bits):
    info = metadata(bits=bits)
    plan = A.plan_capture(info, snapshot(), max_bytes=A.MAX_WORK_BYTES)
    assert info['bits'] == bits and plan.bits == 8
    assert dict(dict(plan.owners)['common-tile-render'])['integer-working-source'] == 3 * info['width'] * info['height']


def test_orientation_disagreement_rejects_even_when_square():
    info = metadata(width=100, height=100)
    info['working_orientation'] = 2
    with pytest.raises(A.AdmissionError, match='orientation'):
        A.plan_capture(info, snapshot(), max_bytes=A.MAX_WORK_BYTES)


def test_persistent_state_is_in_each_tail_not_double_charged_during_render():
    recipe, info = snapshot(), metadata()
    common = dict(max_bytes=A.MAX_WORK_BYTES, retained_bytes=30_000_000)
    before = A.plan_capture(info, recipe, **common)
    after = A.plan_capture(info, recipe, persistent_retained_bytes=20_000_000, **common)
    for phase in ('rgb-to-canonical', 'immutable-freeze', 'validate-intern'):
        assert dict(after.phases)[phase] == dict(before.phases)[phase] + 20_000_000
    assert dict(after.phases)['common-tile-render'] == dict(before.phases)['common-tile-render']
    with pytest.raises(A.AdmissionError):
        A.plan_capture(info, recipe, persistent_retained_bytes=40_000_000, **common)


def test_custom_cube_storage_is_counted_without_constructing_or_parsing(monkeypatch):
    from lumaretouch_engine.custom_lut_asset import CustomCube
    from lumaretouch_engine import custom_lut_asset
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Storage inspection must not parse a LUT')
    monkeypatch.setattr(custom_lut_asset, 'ParsedCube', forbidden)
    # Deliberately non-renderable record: the storage inspector is not an asset
    # validator, and optimization must decline its class even at zero amount.
    cube = object.__new__(CustomCube)
    payload = bytes(bytearray(b'opaque-retained-custom-lut'))
    for key, value in {'content': payload, 'asset_id': 'a' * 64, 'title': 'Retained',
                       'metadata': (3, 2, 0., 0., 0., 1., 1., 1.)}.items():
        object.__setattr__(cube, key, value)
    assert A.inspect_storage((cube, payload)).total_bytes == len(payload)
    recipe = snapshot()
    recipe['lut'] = cube
    assert not A.classify_snapshot(recipe).eligible


def test_dormant_semantic_mask_declines_before_embedded_payload_unpack(monkeypatch):
    from lumaretouch_engine import semantic_colour_state as SEM, semantic_colour_masks as MASKS
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Unsupported mask payload must not be unpacked')
    monkeypatch.setattr(MASKS, 'unpack', forbidden)
    recipe = snapshot()
    recipe['semantic_colour'] = SEM.empty()
    recipe['semantic_colour']['masks'] = [{'base': {'encoding': 'legacy-embedded'}}]
    assert not A.classify_snapshot(recipe).eligible
    assert recipe['semantic_colour']['masks']
