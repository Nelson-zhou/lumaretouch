# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: isolated portrait source allocation and numeric contracts."""
import numpy as np
import pytest

from lumaretouch_engine import people_source_materialization as M


def legacy(source, divisor):
    return np.array(source.astype(np.float32) / divisor, dtype=np.float32, copy=True)


@pytest.mark.parametrize('dtype,divisor', [(np.uint8, 255), (np.uint16, 65535), (np.float32, 1)])
@pytest.mark.parametrize('layout', ['c', 'fortran', 'reverse', 'transpose', 'subview'])
def test_values_match_literal_legacy_and_never_alias_or_mutate(dtype, divisor, layout):
    base = np.arange(9 * 13 * 3, dtype=np.uint16).reshape(9, 13, 3)
    source = (base % 251).astype(dtype)
    if dtype == np.float32:
        source /= np.float32(255)
        source[0, 0, 0] = np.float32(-0.0)
        source[0, 0, 1] = np.nextafter(np.float32(0), np.float32(1))
    if layout == 'fortran': source = np.asfortranarray(source)
    elif layout == 'reverse': source = source[::-1, ::-1]
    elif layout == 'transpose': source = source.transpose(1, 0, 2)
    elif layout == 'subview': source = source[1:8:2, 1:12:2]
    before, writeable = source.copy(), source.flags.writeable
    expected = legacy(source, divisor)
    plan = M.inspect_export_source(source, divisor)
    actual = M.materialize_export_source(source, divisor, max_bytes=plan.peak_bytes)
    assert actual.tobytes() == expected.tobytes()
    assert actual.dtype == np.float32 and actual.flags.c_contiguous
    assert not actual.flags.writeable and not np.shares_memory(actual, source)
    assert source.tobytes() == before.tobytes() and source.flags.writeable == writeable
    assert plan.version == 1 and plan.runtime_verified is False


def test_every_rgb16_code_uses_legacy_rounding():
    values = np.arange(65536, dtype=np.uint16)
    source = np.repeat(values[:, None], 3, axis=1).reshape(256, 256, 3)
    plan = M.inspect_export_source(source, 65535)
    actual = M.materialize_export_source(source, 65535, max_bytes=plan.peak_bytes)
    assert actual.tobytes() == legacy(source, 65535).tobytes()


@pytest.mark.parametrize('width', [1, 257, M.BLOCK_PIXELS, M.BLOCK_PIXELS + 1, 2 * M.BLOCK_PIXELS + 1])
def test_all_blocks_cover_exact_grid_with_fixed_pixel_bound(width):
    shape = (3, width, 3)
    visited = np.zeros(shape[:2], np.uint8)
    for top, bottom, left, right in M._blocks(shape):
        assert 0 < (bottom - top) * (right - left) <= M.BLOCK_PIXELS
        visited[top:bottom, left:right] += 1
    assert np.all(visited == 1)


def test_view_reserves_complete_owner_not_visible_nbytes():
    root = np.zeros((100, 100, 3), np.uint16)
    source = root[10:12, 10:12]
    plan = M.inspect_export_source(source, 65535)
    assert plan.source_storage_bytes == root.nbytes > source.nbytes
    assert plan.peak_bytes == root.nbytes + source.size * 4 + plan.block_workspace_bytes


@pytest.mark.parametrize('mutable', [False, True])
def test_byte_buffer_owner_includes_unused_prefix_and_suffix(mutable):
    raw = bytes(range(240))
    owner = bytearray(raw) if mutable else raw
    source = np.frombuffer(memoryview(owner)[12:72], np.uint8).reshape(4, 5, 3)
    plan = M.inspect_export_source(source, 255)
    assert plan.source_storage_bytes == len(owner)
    out = M.materialize_export_source(source, 255, max_bytes=plan.peak_bytes)
    assert out.tobytes() == legacy(source, 255).tobytes()
    assert bytes(owner) == raw


def test_budget_refuses_before_private_destination(monkeypatch):
    source = np.zeros((5, 7, 3), np.uint8)
    plan = M.inspect_export_source(source, 255)
    def forbidden(*args, **kwargs):
        raise AssertionError('Destination allocated before admission')
    monkeypatch.setattr(M.np, 'empty', forbidden)
    with pytest.raises(ValueError, match='memory budget before allocation'):
        M.materialize_export_source(source, 255, max_bytes=plan.peak_bytes - 1)


def test_source_view_cannot_hide_large_backing_in_visible_legacy_allowance():
    owner = np.zeros((1000, 1000, 3), np.uint8)
    source = owner[:2, :2]
    visible_legacy_allowance = source.nbytes + 36 * 4
    with pytest.raises(ValueError, match='memory budget before allocation'):
        M.materialize_export_source(source, 255, max_bytes=visible_legacy_allowance)


def test_inspection_does_not_allocate_pixel_destination_or_change_flags(monkeypatch):
    source = np.zeros((5, 7, 3), np.uint16)
    def forbidden(*args, **kwargs):
        raise AssertionError('Inspection allocated pixel storage')
    monkeypatch.setattr(M.np, 'empty', forbidden)
    monkeypatch.setattr(M.np, 'array', forbidden)
    assert M.can_materialize_export_source(source, 65535)
    assert source.flags.writeable


@pytest.mark.parametrize('source,divisor', [
    (np.zeros((2, 3, 4), np.uint8), 255),
    (np.zeros((0, 3, 3), np.uint8), 255),
    (np.zeros((2, 3, 3), np.float64), 1),
    (np.zeros((2, 3, 3), np.uint16), 255),
    (np.zeros((2, 3, 3), np.float32), True),
])
def test_malformed_metadata_is_not_legacy_eligibility(source, divisor):
    with pytest.raises(ValueError): M.can_materialize_export_source(source, divisor)


def test_opaque_strided_wrapper_is_explicit_legacy_only():
    root = np.zeros((3, 4, 3), np.uint8)
    source = np.lib.stride_tricks.as_strided(root, shape=root.shape, strides=root.strides)
    assert not M.can_materialize_export_source(source, 255)
    with pytest.raises(M.UnsupportedSourceLayout):
        M.materialize_export_source(source, 255, max_bytes=10**9)
    assert np.all(root == 0)


def test_out_of_owner_span_is_malformed_not_legacy_eligibility(monkeypatch):
    source = np.zeros((3, 4, 3), np.uint8)
    # Simulate the inspector observing malformed addresses, without ever
    # constructing or reading an actual out-of-bounds NumPy view.
    monkeypatch.setattr(M, '_span', lambda array: (-1, -1))
    with pytest.raises(ValueError, match='exceeds its recognized') as failure:
        M.can_materialize_export_source(source, 255)
    assert not isinstance(failure.value, M.UnsupportedSourceLayout)


def test_non_native_precision_does_not_enter_optional_or_legacy_fallback():
    dtype = np.dtype(np.uint16).newbyteorder('S')
    source = np.zeros((3, 4, 3), dtype=dtype)
    with pytest.raises(ValueError): M.can_materialize_export_source(source, 65535)


@pytest.mark.parametrize('bad', [np.nan, np.inf, -np.inf, -0.01, 1.01])
def test_nonfinite_or_hdr_does_not_fallback_clip_or_mutate(bad):
    source = np.zeros((3, 5, 3), np.float32)
    source[-1, -1, -1] = bad
    before = source.tobytes()
    plan = M.inspect_export_source(source, 1)
    with pytest.raises(ValueError, match='finite SDR'):
        M.materialize_export_source(source, 1, max_bytes=plan.peak_bytes)
    assert source.tobytes() == before and source.flags.writeable


@pytest.mark.parametrize('cancel_at', [1, 2, 3, 4])
def test_cancellation_never_publishes_or_mutates(cancel_at):
    source = np.zeros((1, M.BLOCK_PIXELS + 1, 3), np.uint8)
    before = source.tobytes()
    plan = M.inspect_export_source(source, 255)
    calls = 0
    def cancelled():
        nonlocal calls
        calls += 1
        return calls == cancel_at
    with pytest.raises(InterruptedError, match='cancelled'):
        M.materialize_export_source(source, 255, max_bytes=plan.peak_bytes, cancelled=cancelled)
    assert source.tobytes() == before and source.flags.writeable


def test_initial_cancellation_precedes_destination_allocation(monkeypatch):
    source = np.zeros((3, 5, 3), np.uint8)
    plan = M.inspect_export_source(source, 255)
    def forbidden(*args, **kwargs):
        raise AssertionError('Cancelled source allocated destination')
    monkeypatch.setattr(M.np, 'empty', forbidden)
    with pytest.raises(InterruptedError):
        M.materialize_export_source(source, 255, max_bytes=plan.peak_bytes, cancelled=lambda: True)


def test_retained_failure_traceback_does_not_keep_private_pixel_allocations():
    source = np.zeros((1, M.BLOCK_PIXELS + 1, 3), np.float32)
    source[0, -1, -1] = np.nan
    plan = M.inspect_export_source(source, 1)
    with pytest.raises(ValueError, match='finite SDR') as failure:
        M.materialize_export_source(source, 1, max_bytes=plan.peak_bytes)
    trace = failure.value.__traceback__
    found = False
    while trace is not None:
        if trace.tb_frame.f_code is M.materialize_export_source.__code__:
            found = True
            assert trace.tb_frame.f_locals['output'] is None
            assert trace.tb_frame.f_locals['block'] is None
            assert trace.tb_frame.f_locals['normalized'] is None
        trace = trace.tb_next
    assert found


@pytest.mark.parametrize('budget', [-1, True, 1.0, None])
def test_invalid_budgets_fail_closed(budget):
    with pytest.raises(ValueError, match='byte budget'):
        M.materialize_export_source(np.zeros((1, 1, 3), np.uint8), 255, max_bytes=budget)
