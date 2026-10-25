"""AUTHORED / UNRUN: bounded geometry vs the actual frozen NumPy renderer.

These are small executable synthetic contracts, not real-photo, performance,
native-process or RSS acceptance evidence. No test in this file has been run.
"""
import math
import sys
from unittest.mock import patch

import numpy as np
import pytest

from lumaretouch_engine import creative_capture_geometry as bounded
from lumaretouch_engine.ops import geometry as legacy


FULL = (0.0, 0.0, 1.0, 1.0)
CROP = (0.13, 0.19, 0.86, 0.93)


def sample(height=9, width=13, dtype=np.float32):
    # Original deterministic fixture: negative/HDR values, not clipped imagery.
    grid = np.arange(height * width * 3, dtype=np.float64).reshape(height, width, 3)
    return (np.sin(grid * 0.317) * 3.0 + grid / 17.0 - 4.0).astype(dtype)


def assert_identical(actual, expected):
    assert actual.shape == expected.shape
    assert actual.dtype == expected.dtype
    # Unlike allclose/array_equal, this also observes the sign bit of zero.
    assert actual.tobytes(order='C') == expected.tobytes(order='C')


@pytest.mark.parametrize('dtype', [np.float32, np.float64])
@pytest.mark.parametrize('angle', [0.5, -0.5, 17.25, -37.5, 45.0, 60.0,
                                  89.5, 90.5, -89.5, -90.5, 179.5, -179.5])
@pytest.mark.parametrize('rect', [FULL, CROP, (0.1, 0.1, 0.9, 0.9)])
@pytest.mark.parametrize('block_pixels', [1, 5, 17, 65_536])
def test_arbitrary_angles_match_real_legacy_byte_for_byte(dtype, angle, rect, block_pixels):
    source = sample(dtype=dtype)
    before = source.tobytes()
    expected = legacy.crop_rotate_np(source, rect, angle, uint8=False)
    actual = bounded.crop_rotate_np_bounded(source, rect, angle, block_pixels=block_pixels)
    assert_identical(actual, expected)
    assert actual.dtype == np.float64
    assert actual.flags.c_contiguous
    assert source.tobytes() == before
    assert (actual.shape[1], actual.shape[0]) == legacy.out_size(13, 9, rect, angle)


@pytest.mark.parametrize('dtype', [np.float32, np.float64])
@pytest.mark.parametrize('shape', [(1, 1), (1, 2), (2, 1), (1, 7), (8, 1)])
@pytest.mark.parametrize('angle', [0.5, 17.0, 45.0, 60.0, -37.5])
def test_singleton_cells_use_the_existing_sampler(dtype, shape, angle):
    source = sample(*shape, dtype=dtype)
    expected = legacy.crop_rotate_np(source, FULL, angle, uint8=False)
    actual = bounded.crop_rotate_np_bounded(source, FULL, angle, block_pixels=2)
    assert_identical(actual, expected)


@pytest.mark.parametrize('rect', [(0.25, 0.25, 0.375, 0.875),
                                 (0.25, 0.25, 0.875, 0.375)])
def test_crop_induced_singleton_uses_cut_extent_not_original_extent(rect):
    source = sample(8, 8)
    expected = legacy.crop_rotate_np(source, rect, 60.0, uint8=False)
    actual = bounded.crop_rotate_np_bounded(source, rect, 60.0, block_pixels=3)
    assert_identical(actual, expected)


@pytest.mark.parametrize('shape', [(1, 1), (1, 7), (7, 1)])
def test_gather_adapter_preserves_exact_singleton_half_pixel_membership(shape):
    source = np.full((*shape, 3), 0.3, dtype=np.float32)
    offsets = np.array([[-0.500001, -0.5, 0.0, 0.5, 0.500001]])
    sx = offsets if shape[1] == 1 else np.full_like(offsets, 2.25)
    sy = offsets if shape[0] == 1 else np.full_like(offsets, 2.25)
    expected = legacy._sample_bilinear_np(source.astype(np.float64), sx, sy)
    actual = legacy._sample_bilinear_np(bounded._Float64Gathers(source), sx, sy)
    assert_identical(actual, expected)
    assert np.all(actual[:, [0, 4]] == 0)
    assert np.all(actual[:, 1:4] != 0)


@pytest.mark.parametrize('dtype', [np.float32, np.float64])
@pytest.mark.parametrize('angle', [-180.0, -179.9, -90.1, -90.0, -89.9, -0.1,
                                  0.1, 89.9, 90.0, 90.1, 179.9, 180.0])
def test_strict_snap_preserves_lossless_dtype_and_actual_legacy_pixels(dtype, angle):
    source = sample(dtype=dtype)
    expected = legacy.crop_rotate_np(source, CROP, angle, uint8=False)
    plan = bounded.inspect_crop_rotate_np(source, CROP, angle, block_pixels=3)
    actual = bounded.crop_rotate_np_bounded(source, CROP, angle, block_pixels=3)
    assert plan.path == 'quarter-turn'
    assert plan.quarter_turns == legacy._snapped_quarter_turn(angle)
    assert plan.output_dtype == source.dtype.name
    assert_identical(actual, expected)


@pytest.mark.parametrize('angle', [0.0, -0.0, 0.5e-12, -0.5e-12, 1e-12, -1e-12])
def test_neutral_returns_original_object_and_keeps_readonly_strided_storage(angle):
    owner = sample()
    source = owner[::-1, ::-2, ::-1]
    source.flags.writeable = False
    plan = bounded.inspect_crop_rotate_np(source, FULL, angle)
    assert bounded.crop_rotate_np_bounded(source, FULL, angle) is source
    assert plan.path == 'identity'
    assert plan.source_storage_bytes == owner.nbytes
    assert plan.output_storage_bytes == owner.nbytes
    assert plan.output_allocation_bytes == 0
    assert plan.block_workspace_bytes == 0
    assert not source.flags.writeable


@pytest.mark.parametrize('angle', [0.0, 0.5e-12, 1e-12, 0.1, 90.0, 17.5])
@pytest.mark.parametrize('layout', ['negative', 'transpose', 'fortran', 'channels', 'broadcast'])
def test_strided_sources_match_real_legacy_without_full_source_copy(angle, layout):
    owner = sample(11, 19, dtype=np.float64)
    if layout == 'negative':
        source = owner[::-2, ::-3]
    elif layout == 'transpose':
        source = owner.transpose(1, 0, 2)
    elif layout == 'fortran':
        source = np.asfortranarray(owner)
    elif layout == 'channels':
        source = owner[:, :, ::-1]
    else:
        source = np.broadcast_to(owner[:1, :1], (11, 19, 3))
    expected = legacy.crop_rotate_np(source, CROP, angle, uint8=False)
    actual = bounded.crop_rotate_np_bounded(source, CROP, angle, block_pixels=7)
    assert_identical(actual, expected)


@pytest.mark.parametrize('dtype', [np.float32, np.float64])
@pytest.mark.parametrize('angle', [0.0, 0.1, 90.0, 17.5, -37.5])
def test_signed_zero_and_extended_values_are_not_clipped_or_normalized(dtype, angle):
    values = np.array([-0.0, 0.0, -12.0, 12.0, 1.00001, -0.000001,
                       65_504.0, -65_504.0, 0.25], dtype=dtype)
    source = np.resize(values, (9, 13, 3)).copy()
    expected = legacy.crop_rotate_np(source, FULL, angle, uint8=False)
    actual = bounded.crop_rotate_np_bounded(source, FULL, angle, block_pixels=3)
    assert_identical(actual, expected)
    assert np.min(actual) < 0
    assert np.max(actual) > 1


def test_float32_gathers_promote_before_subtracting_not_after_overflow():
    source = np.resize(np.array([-3e38, 3e38, 1.0], dtype=np.float32), (5, 7, 3)).copy()
    source[1::2, :, :] *= np.float32(-1)
    with np.errstate(over='raise', invalid='raise'):
        expected = legacy.crop_rotate_np(source, FULL, 17.5, uint8=False)
        actual = bounded.crop_rotate_np_bounded(source, FULL, 17.5, block_pixels=2)
    assert_identical(actual, expected)
    assert np.isfinite(actual).all()


def test_coordinates_are_global_f64_and_sampler_calls_stay_bounded():
    source = sample(19, 29)
    angle, cap = 17.5, 7
    plan = bounded.inspect_crop_rotate_np(source, CROP, angle, block_pixels=cap)
    ys, xs = np.mgrid[:plan.height, :plan.width].astype(np.float64)
    dx, dy = xs - (plan.width - 1) / 2.0, ys - (plan.height - 1) / 2.0
    xa, xb, ya, yb = plan.crop_bounds
    a = math.radians(angle)
    ca, sa = math.cos(-a), math.sin(-a)
    sx = ca * dx - sa * dy + (xb - xa - 1) / 2.0
    sy = sa * dx + ca * dy + (yb - ya - 1) / 2.0
    observed_x, observed_y, real_sampler = [], [], legacy._sample_bilinear_np

    def observe(src, x, y):
        assert x.dtype == np.float64 and y.dtype == np.float64
        assert 0 < x.size <= cap
        observed_x.append(x.copy().reshape(-1))
        observed_y.append(y.copy().reshape(-1))
        return real_sampler(src, x, y)

    with patch.object(legacy, '_sample_bilinear_np', side_effect=observe):
        bounded.crop_rotate_np_bounded(source, CROP, angle, block_pixels=cap)
    assert len(observed_x) > 1
    assert_identical(np.concatenate(observed_x), sx.reshape(-1))
    assert_identical(np.concatenate(observed_y), sy.reshape(-1))


def test_arbitrary_path_never_promotes_or_contiguizes_a_full_source_raster():
    source, cap = sample(19, 29), 5
    expected = legacy.crop_rotate_np(source, CROP, 17.5, uint8=False)
    real_asarray = np.asarray

    def bounded_asarray(value, *args, **kwargs):
        if type(value) is np.ndarray and value.size > cap * 3:
            raise AssertionError('Attempted full-raster array conversion')
        return real_asarray(value, *args, **kwargs)

    with patch.object(np, 'asarray', side_effect=bounded_asarray), patch.object(
            np, 'ascontiguousarray', side_effect=AssertionError('Full crop copy')):
        actual = bounded.crop_rotate_np_bounded(source, CROP, 17.5, block_pixels=cap)
    assert_identical(actual, expected)


def test_plan_charges_full_owner_f64_output_and_named_bounded_scratch():
    owner = sample(31, 47, dtype=np.float64)
    source = owner[5:12, 8:19]
    plan = bounded.inspect_crop_rotate_np(source, FULL, 17.5, block_pixels=11)
    assert plan.version == bounded.GEOMETRY_VERSION
    assert plan.source_bytes == source.nbytes
    assert plan.source_storage_bytes == owner.nbytes
    assert plan.output_dtype == 'float64'
    assert plan.output_bytes == plan.height * plan.width * 24
    assert plan.output_allocation_bytes == plan.output_bytes
    assert plan.output_storage_bytes == plan.output_bytes
    assert plan.block_workspace_bytes == 640 * 11
    assert len(dict(plan.scratch_components)) == 7
    assert plan.peak_bytes == (owner.nbytes + plan.output_bytes + 640 * 11
                               + bounded.ARRAY_WORKSPACE_RESERVE + bounded.METADATA_RESERVE)
    assert not plan.runtime_verified


@pytest.mark.parametrize('storage_type', [bytes, bytearray])
def test_known_buffer_backing_charges_unused_bytes_and_memoryview_root(storage_type):
    storage = storage_type(4096)
    source = np.frombuffer(memoryview(storage)[32:512], dtype='=f4', count=18,
                           offset=12).reshape(2, 3, 3)
    plan = bounded.inspect_crop_rotate_np(source, FULL, 17.5)
    assert plan.source_storage_bytes == len(storage)
    assert plan.source_owner_id == id(storage)
    assert plan.source_bytes == 72


def test_broadcast_logical_extent_is_not_mistaken_for_actual_root_storage():
    owner = np.zeros((1, 1, 3), dtype=np.float32)
    source = np.broadcast_to(owner, (7, 11, 3))
    plan = bounded.inspect_crop_rotate_np(source, FULL, 17.5)
    assert plan.source_bytes == 7 * 11 * 12
    assert plan.source_storage_bytes == 12


def test_exact_budget_admits_one_byte_less_rejects_before_output_or_sampling():
    source = sample()
    plan = bounded.inspect_crop_rotate_np(source, FULL, 17.5, block_pixels=7)
    assert bounded.inspect_crop_rotate_np(source, FULL, 17.5, block_pixels=7,
                                          max_bytes=plan.peak_bytes).peak_bytes == plan.peak_bytes
    with patch.object(np, 'empty') as allocate, patch.object(legacy, '_sample_bilinear_np') as sampler:
        with pytest.raises(bounded.GeometryCaptureBudgetExceeded):
            bounded.crop_rotate_np_bounded(source, FULL, 17.5, block_pixels=7,
                                           max_bytes=plan.peak_bytes - 1)
        allocate.assert_not_called()
        sampler.assert_not_called()
    actual = bounded.crop_rotate_np_bounded(source, FULL, 17.5, block_pixels=7,
                                            max_bytes=plan.peak_bytes)
    assert_identical(actual, legacy.crop_rotate_np(source, FULL, 17.5, uint8=False))


def test_alias_crop_is_charged_once_and_noncontiguous_crop_has_one_output():
    source = sample()
    alias = bounded.inspect_crop_rotate_np(source, (0.0, 0.2, 1.0, 0.8), 0.0)
    copied = bounded.inspect_crop_rotate_np(source, CROP, 0.0)
    assert alias.output_storage_kind == 'source-alias'
    assert alias.output_allocation_bytes == 0
    assert alias.output_storage_bytes == source.nbytes
    assert copied.output_allocation_bytes == copied.output_bytes
    assert copied.output_dtype == 'float32'
    assert copied.block_workspace_bytes == copied.block_pixels * 24


@pytest.mark.parametrize('value', [True, 0, -1, 1.0, 65_537])
def test_invalid_block_bound_rejects_before_any_raster_allocation(value):
    with patch.object(np, 'empty') as allocate:
        with pytest.raises(bounded.GeometryCaptureError, match='block'):
            bounded.crop_rotate_np_bounded(sample(), FULL, 17.5, block_pixels=value)
        allocate.assert_not_called()


@pytest.mark.parametrize('value', [True, 0, -1, 1.0, 4_000_000_001])
def test_invalid_budget_rejects(value):
    with pytest.raises(bounded.GeometryCaptureError, match='budget'):
        bounded.crop_rotate_np_bounded(sample(), FULL, 17.5, max_bytes=value)


def test_invalid_sources_and_unknown_owners_fail_closed():
    swapped = '>f4' if sys.byteorder == 'little' else '<f4'
    invalid = [None, np.zeros((2, 3)), np.zeros((2, 3, 4), dtype=np.float32),
               np.zeros((0, 3, 3), dtype=np.float32), np.zeros((2, 0, 3), dtype=np.float32),
               np.zeros((2, 3, 3), dtype=swapped)]
    invalid.extend(np.zeros((2, 3, 3), dtype=dtype)
                   for dtype in (np.uint8, np.uint16, np.float16, np.int32, np.bool_))
    source = sample()
    invalid.append(np.lib.stride_tricks.as_strided(source, shape=source.shape, strides=source.strides))

    class Subclass(np.ndarray):
        pass

    invalid.append(source.view(Subclass))
    for item in invalid:
        with pytest.raises(bounded.GeometryCaptureError):
            bounded.inspect_crop_rotate_np(item, FULL, 17.5)


def test_source_and_rotated_output_pixel_caps_reject_shape_only_fixtures():
    # No large raster is allocated: both are read-only virtual broadcast views.
    owner = np.zeros((1, 1, 3), dtype=np.float32)
    too_large = np.broadcast_to(owner, (bounded.MAX_SOURCE_PIXELS + 1, 1, 3))
    with pytest.raises(bounded.GeometryCaptureError, match='source'):
        bounded.inspect_crop_rotate_np(too_large, FULL, 0.0)
    very_tall = np.broadcast_to(owner, (bounded.MAX_SOURCE_PIXELS, 1, 3))
    with pytest.raises(bounded.GeometryCaptureError, match='output'):
        bounded.inspect_crop_rotate_np(very_tall, FULL, 45.0)


def test_precancel_does_not_examine_source_or_allocate():
    with patch.object(np, 'empty') as allocate, patch.object(legacy, '_sample_bilinear_np') as sampler:
        with pytest.raises(InterruptedError):
            bounded.crop_rotate_np_bounded(object(), FULL, 17.5, cancelled=lambda: True)
        allocate.assert_not_called()
        sampler.assert_not_called()


def test_cancel_after_output_allocation_prevents_first_sampler_call():
    source = sample()
    state, real_empty = {'cancelled': False}, np.empty

    def allocate(*args, **kwargs):
        result = real_empty(*args, **kwargs)
        state['cancelled'] = True
        return result

    with patch.object(np, 'empty', side_effect=allocate), patch.object(legacy, '_sample_bilinear_np') as sampler:
        with pytest.raises(InterruptedError):
            bounded.crop_rotate_np_bounded(source, FULL, 17.5,
                                           cancelled=lambda: state['cancelled'])
        sampler.assert_not_called()


def test_cancel_after_one_real_block_returns_no_partial_and_preserves_source():
    source = sample()
    before, real_sampler = source.tobytes(), legacy._sample_bilinear_np
    state = {'calls': 0}

    def sample_then_cancel(*args):
        result = real_sampler(*args)
        state['calls'] += 1
        return result

    with patch.object(legacy, '_sample_bilinear_np', side_effect=sample_then_cancel):
        with pytest.raises(InterruptedError):
            bounded.crop_rotate_np_bounded(source, FULL, 17.5, block_pixels=2,
                                           cancelled=lambda: state['calls'] > 0)
    assert state['calls'] == 1
    assert source.tobytes() == before


def test_snapshot_plan_cannot_be_mutated_or_advertise_runtime_verification():
    from dataclasses import FrozenInstanceError
    plan = bounded.inspect_crop_rotate_np(sample(), FULL, 17.5)
    with pytest.raises(FrozenInstanceError):
        plan.output_dtype = 'float32'
    assert plan.runtime_verified is False
