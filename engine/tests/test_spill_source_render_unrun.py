"""AUTHORED / UNRUN: spill source precision, field ownership and ID consumers.

These fixtures have not been imported or executed. Native estimation is mocked
where noted; that is routing evidence only, not spill quality or performance QA.
Tensor/native parity, source-resolution timing and visual acceptance remain UNRUN.
"""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
import torch

from lumaretouch_engine import id_background_state as I
from lumaretouch_engine import id_background_support as U
from lumaretouch_engine import id_background_runtime as R
from lumaretouch_engine import spill_removal_render as S
from lumaretouch_engine import spill_removal_state as SS
from lumaretouch_engine import spill_removal_coverage as C
from lumaretouch_engine import local_mask_state as M
from lumaretouch_engine.id_background_stage import IDBackgroundStage
from lumaretouch_engine.effect_recovery_stage import EffectRecoveryStage
from lumaretouch_engine.ops.matting import composite_linear_fields_t


def recipe(shape=(2, 4), *, enabled=True, strength=50):
    h, w = shape
    source = {'sha256': 'a'*64, 'width': w, 'height': h}
    mask = M.empty(); mask['source'] = source
    mask['recipe']['objects'] = [{'id': 'review', 'name': 'Review', 'enabled': True,
        'operation': 'add', 'kind': 'radial', 'opacity': 1., 'feather': 0.,
        'center': [.5, .5], 'axes': [[.4, 0.], [0., .4]]}]
    value = I.empty(); value.update(enabled=True, source=source)
    value['support']['subject'] = U.check_binding({'version': 1, 'category': 'subject',
        'reviewed': True, 'mask': mask, 'recipe_sha256': U.digest(mask)}, 'subject')
    return I.with_spill(value, {**SS.neutral(), 'enabled': enabled, 'strength': strength})


def native_fields(source, alpha, *, strength, render_scale, encoding, cancelled):
    # Deterministic mocked evidence. The real estimator has separate fixtures.
    delta = np.empty_like(source)
    delta[:] = [.06, -.06*.2126/.7152, 0.]
    return {'delta': delta, 'confidence': np.full(alpha.shape, strength, np.float32),
            'encoding': encoding, 'render_scale': render_scale, 'domain_shape': alpha.shape,
            'estimator': 'fixed-alpha-fb-edge-reflection-v1'}


def prepared(shape=(2, 4), *, alpha=1., spill=True):
    value = recipe(shape, enabled=spill)
    source = np.full((*shape, 3), .4, np.float32)
    matte = np.full(shape, alpha, np.float32)
    with patch('lumaretouch_engine.spill_removal_native.prepare', side_effect=native_fields):
        correction = S.prepare(value, source, matte, full_source=True)
    fields = {'alpha': matte.copy(), 'background': np.full_like(source, .1),
              'encoding': 'linear-srgb-d65', 'render_scale': 1., **correction}
    return value, source, fields


def tensor(pixels):
    return torch.from_numpy(pixels.copy()).permute(2, 0, 1)[None]


def test_uint16_and_float32_source_do_not_take_an_rgb8_detour():
    values = np.array([[[256, 257, 258], [32767, 32768, 32769]]], np.uint16)
    linear = S.linear_source(values)
    encoded = values.astype(np.float32)/65535.
    expected = np.where(encoded <= .04045, encoded/12.92, ((encoded+.055)/1.055)**2.4)
    assert np.array_equal(linear, expected)
    assert len(set(linear[0, 0])) == 3
    floats = encoded + np.float32(.000001)
    assert not np.array_equal(S.linear_source(floats), linear)
    assert not linear.flags.writeable


def test_source_hdr_nonfinite_float64_and_proxy_export_fail_without_clipping():
    value = recipe()
    for pixels in (np.full((2, 4, 3), 1.01, np.float32),
                   np.full((2, 4, 3), np.nan, np.float32),
                   np.ones((2, 4, 3), np.float64), np.ones((1, 2, 3), np.float32)):
        with pytest.raises(ValueError):
            S.source_identity(pixels, value['source'], full_source=True)


def test_disabled_and_zero_strength_keep_exact_legacy_four_plane_path():
    for value in (recipe(enabled=False), recipe(strength=0)):
        with patch('lumaretouch_engine.spill_removal_native.prepare', side_effect=AssertionError('No estimator')):
            assert S.prepare(value, None, None) == {}
    _, _, fields = prepared(spill=False)
    stage = IDBackgroundStage('cpu', (2, 4)); stage.install(fields)
    current = torch.rand((1, 3, 2, 4))
    assert stage.fields.shape == (1, 4, 2, 4)
    expected = composite_linear_fields_t(current, stage.fields[:, :1], stage.fields[:, 1:])
    assert torch.equal(stage.apply(current, lambda x: x), expected)


def test_confidence_has_strength_once_and_manual_coverage_never_changes_alpha():
    value = recipe(strength=40)
    mask = value['support']['subject']['mask']
    coverage = C.check_binding({'version': 1, 'reviewed': True, 'mask': mask,
                                'recipe_sha256': C.digest(mask)})
    value = I.with_spill(value, {**I.spill_of(value), 'coverage': coverage})
    source = np.full((2, 4, 3), .4, np.float32)
    alpha = np.full((2, 4), .7, np.float32); before = alpha.copy()
    with patch('lumaretouch_engine.spill_removal_native.prepare', side_effect=native_fields) as estimator, \
         patch.object(C, 'raster', return_value=np.full((2, 4), .25, np.float32)):
        fields = S.prepare(value, source, alpha, full_source=True)
    assert estimator.call_args.kwargs['strength'] == .4
    assert np.allclose(fields['spill_confidence'], .1)
    assert np.array_equal(alpha, before)
    assert not fields['spill_delta'].flags.writeable and not fields['spill_confidence'].flags.writeable


def test_source_or_reviewed_alpha_mutation_during_estimation_is_rejected():
    for mutate_source in (True, False):
        value = recipe(); source = np.full((2, 4, 3), .4, np.float32)
        alpha = np.full((2, 4), .7, np.float32)
        def mutate(*args, **kwargs):
            result = native_fields(*args, **kwargs)
            if mutate_source: source[0, 0, 0] = .45
            else: alpha[0, 0] = .8
            return result
        with patch('lumaretouch_engine.spill_removal_native.prepare', side_effect=mutate):
            with pytest.raises(ValueError): S.prepare(value, source, alpha, full_source=True)


def test_current_hdr_and_zero_confidence_are_bit_exact_neutral():
    current = torch.tensor([[[[1.2, .2, -.1]], [[.4, .4, .4]], [[.6, .6, .6]]]], dtype=torch.float32)
    delta = torch.full_like(current, .05)
    confidence = torch.tensor([[[[1., 0., 1.]]]], dtype=torch.float32)
    assert torch.equal(S.apply_t(current, delta, confidence), current)
    assert torch.equal(S.apply_t(current, torch.zeros_like(delta), torch.ones_like(confidence)), current)


def test_common_line_limit_preserves_linear_luminance_without_channel_clipping():
    current = torch.tensor([[[[.99]], [[.12]], [[.3]]]], dtype=torch.float32)
    delta = torch.tensor([[[[.4]], [[-.4*.2126/.7152]], [[0.]]]], dtype=torch.float32)
    out = S.apply_t(current, delta, torch.ones((1, 1, 1, 1)))
    before = S.linear_source(current[0].permute(1, 2, 0).numpy())
    after = S.linear_source(out[0].permute(1, 2, 0).numpy())
    luminance = np.array([.2126, .7152, .0722], np.float32)
    assert np.max(np.abs((after-before) @ luminance)) <= 2e-6
    assert torch.all(out >= 0) and torch.all(out <= 1)
    assert float(out[0, 0, 0, 0]) > .99


def test_stage_aligns_all_fields_once_and_applies_to_current_not_cached_source():
    _, source, fields = prepared(alpha=.8)
    stage = IDBackgroundStage('cpu', (2, 4)); stage.install(fields)
    current = tensor(source + .17); calls = []
    def align(field):
        calls.append(field)
        return field.flip(-1)
    actual = stage.apply(current, align)
    packed = stage.fields.flip(-1)
    expected = composite_linear_fields_t(S.apply_t(current, packed[:, 4:7], packed[:, 7:8]),
                                         packed[:, :1], packed[:, 1:4])
    assert len(calls) == 1 and calls[0].shape[1] == 8
    assert torch.equal(actual, expected)
    assert not torch.equal(actual, stage.apply(tensor(source), lambda x: x))


def test_full_source_fields_crop_tiles_without_reestimating_or_seams():
    value, source, fields = prepared(alpha=.8)
    current = tensor(source + .12)
    whole = IDBackgroundStage('cpu', (2, 4)); whole.install(fields)
    spec = SimpleNamespace(id_background=value, id_background_prepared=fields)
    parts = []
    with patch('lumaretouch_engine.spill_removal_native.prepare', side_effect=AssertionError('No tile estimator')):
        for x0, x1 in ((0, 2), (2, 4)):
            pipe = SimpleNamespace(device='cpu', h=2, w=2)
            R.attach_tile(pipe, spec, (0, x0, 2, x1))
            parts.append(pipe.id_background.apply(current[:, :, :, x0:x1], lambda x: x))
    assert torch.equal(torch.cat(parts, dim=3), whole.apply(current, lambda x: x))
    assert R.resident_bytes(spec) == 2*4*8*4


def test_id_recovery_attenuates_spill_and_replacement_together():
    _, source, fields = prepared(alpha=.6)
    current = tensor(source + .19)
    stage = IDBackgroundStage('cpu', (2, 4)); stage.install(fields)
    after = stage.apply(current, lambda x: x)
    recovery = EffectRecoveryStage('cpu', (2, 4))
    weight = np.array([[0, 128, 255, 255], [0, 128, 255, 255]], np.uint8)
    recovery.set([{'target': 'id_background', 'weight': weight}])
    out = recovery.apply('id_background', current, after, align=lambda x: x)
    assert torch.equal(out[:, :, :, :1], after[:, :, :, :1])
    assert torch.equal(out[:, :, :, 2:], current[:, :, :, 2:])


def test_stage_and_full_prepared_proofs_cover_spill_arrays_and_actual_source():
    value, source, fields = prepared()
    stage = IDBackgroundStage('cpu', (2, 4)); stage.install(fields)
    before = R._stage_proof(stage)
    stage.fields[:, 7:8].numpy()[0, 0, 0, 0] = .2  # Alias bypasses tensor version.
    assert R._stage_proof(stage) != before
    spec = SimpleNamespace(id_background=value, _spill_source_input=source)
    proof = R._prepared_proof(spec, fields)
    altered = {**fields, 'spill_delta': fields['spill_delta'].copy()}
    altered['spill_delta'][0, 0, 0] += .01
    assert R._prepared_proof(spec, altered) != proof
    changed = deepcopy(fields); changed['spill_source']['linear_sha256'] = 'f'*64
    assert R._prepared_proof(spec, changed) != proof
    source[0, 0, 0] = .5
    with pytest.raises(ValueError): R._prepared_proof(spec, fields)


def test_cancelled_preparation_and_proof_do_not_return_partial_fields():
    value, source, fields = prepared()
    with pytest.raises(InterruptedError):
        S.prepare(value, source, fields['alpha'], cancelled=lambda: True)
    with pytest.raises(InterruptedError):
        R._prepared_proof(SimpleNamespace(id_background=value, _spill_source_input=source,
                                         _id_background_cancelled=lambda: True), fields)


def test_export_prepares_whole_source_once_and_freezes_every_owned_array():
    value, source, fields = prepared()
    spec = SimpleNamespace(id_background=value, id_background_bundle=None,
        id_background_path='/fixture/source.png', id_background_stamp=[1, 2, 3, 4, 5],
        creative_base=None)
    with patch.object(M, 'file_stamp', return_value=(1, 2, 3, 4, 5)), \
         patch.object(M, 'verify_source'), patch.object(R, 'prepare', return_value=fields) as prepare:
        R.export_prepare(spec, source)
    assert prepare.call_count == 1 and prepare.call_args.args[3] is source
    assert prepare.call_args.kwargs['full_source'] is True
    assert spec._spill_source_input is source
    assert all(not array.flags.writeable for array in fields.values() if isinstance(array, np.ndarray))


def test_original_colour_provenance_excludes_spill_foreground_unless_fully_recovered():
    from lumaretouch_engine.reference_color_provenance import source_support
    _, _, fields = prepared((8, 8), alpha=1.)
    identity = IDBackgroundStage('cpu', (8, 8)); identity.install(fields)
    recovery = SimpleNamespace(required=set(), suspended=None, suspended_targets=set(), fields={})
    pipe = SimpleNamespace(device='cpu', id_background=identity,
        studio_background=SimpleNamespace(required=False, fields={}, recovery={}),
        sky_replacement=SimpleNamespace(value={'enabled': False}), effect_recovery=recovery,
        align_source_grade_mask=lambda x: x, has_background=lambda: False,
        manual_liquify=SimpleNamespace(apply=lambda x: x))
    spec = SimpleNamespace(repair=[])
    excluded = source_support(pipe, (0, 0, 8, 8), (8, 8), spec)
    assert np.all(excluded[2:-2, 2:-2] == 0)
    recovery.required = {'id_background'}
    recovery.fields = {'id_background': torch.full((1, 1, 8, 8), 255, dtype=torch.uint8)}
    restored = source_support(pipe, (0, 0, 8, 8), (8, 8), spec)
    assert np.all(restored[2:-2, 2:-2] == 1)
    recovery.fields['id_background'][:] = 128
    partial = source_support(pipe, (0, 0, 8, 8), (8, 8), spec)
    assert np.all(partial[2:-2, 2:-2] == 0)
