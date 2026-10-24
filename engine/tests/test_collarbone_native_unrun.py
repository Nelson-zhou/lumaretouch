# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Boundary fixtures use protocol fakes, never photo evidence.

No product import, native compilation, fixture execution or inference was run
while authoring these files. Real Rust numerical fixtures are separate.
"""
import ctypes

import numpy as np
import pytest

from lumaretouch_engine import collarbone_native as collarbone


SIDE = 129
CURVES = [{'id': 'left', 'points': [[28.5/SIDE, 64.5/SIDE],
                                  [64.5/SIDE, 64.5/SIDE],
                                  [100.5/SIDE, 64.5/SIDE]], 'width': 8.0/SIDE}]


class ZeroEvidenceCopyProtocol:
    """Transport fake only. It intentionally implements no photographic method."""
    def lrt_collarbone_prepare_v1(self, reference, reference_len, coverage, coverage_len,
                                  source_width, source_height, sx, sy, sw, sh,
                                  points, points_len, counts, counts_len, widths, widths_len,
                                  ox, oy, ow, oh, field, field_len, stats, stats_len, cancel, context):
        assert reference_len == 3*sw*sh and coverage_len == sw*sh
        assert field_len == ow*oh and stats_len == 8
        assert source_width == source_height == SIDE
        assert points_len == 6 and counts_len == widths_len == 1 and counts[0] == 3
        assert points[0]*SIDE-0.5 == pytest.approx(28.0)
        assert widths[0]*SIDE == pytest.approx(8.0)
        assert sx <= ox and sy <= oy and sx+sw >= ox+ow and sy+sh >= oy+oh
        if cancel(context):
            return 4
        ctypes.memset(field, 0, field_len*ctypes.sizeof(ctypes.c_float))
        for index in range(stats_len):
            stats[index] = 0
        stats[0] = 20
        stats[1] = 20
        stats[5] = 20
        return 0

    def lrt_collarbone_compose_v1(self, current, current_len, x, y, w, h,
                                  field, field_len, fx, fy, fw, fh, sw, sh, amount,
                                  output, output_len, cancel, context):
        assert current_len == output_len == 3*w*h
        assert field_len == fw*fh
        assert x+w <= sw and y+h <= sh and fx+fw <= sw and fy+fh <= sh
        assert ctypes.addressof(current.contents) != ctypes.addressof(output.contents)
        if cancel(context):
            return 4
        ctypes.memmove(output, current, current_len*ctypes.sizeof(ctypes.c_float))
        return 0


@pytest.fixture
def protocol(monkeypatch):
    monkeypatch.setattr(collarbone, '_available_estimate', lambda: 16*1024**3)
    monkeypatch.setattr(collarbone, 'native', lambda: ZeroEvidenceCopyProtocol())


def source():
    return np.full((SIDE, SIDE, 3), 0.4, dtype=np.float32), np.ones((SIDE, SIDE), dtype=np.float32)


def test_roi_normalized_coordinate_and_no_signal_report_contract(protocol):
    rgb, coverage = source()
    prepared = collarbone.prepare(rgb, coverage, CURVES)
    assert type(prepared) is collarbone.PreparedCollarbone
    assert prepared.source_shape == (SIDE, SIDE)
    assert prepared.field.dtype == np.float32 and prepared.field.flags.c_contiguous
    assert prepared.field.flags.owndata and not prepared.field.flags.writeable
    assert prepared.field.size < SIDE*SIDE
    assert prepared.report['status'] == 'no_observed_signal'
    assert prepared.report['supported_pixels'] == prepared.report['admitted_pixels'] == 0
    assert type(prepared.report) is dict
    assert np.array_equal(collarbone.compose(rgb, prepared, 1.0).view(np.uint32), rgb.view(np.uint32))


def test_memory_estimate_uses_true_roi_and_has_no_side_effect(monkeypatch):
    monkeypatch.setattr(collarbone, 'native', lambda: pytest.fail('No native load in estimate'))
    monkeypatch.setattr(collarbone, '_available_estimate', lambda: pytest.fail('No cgroup read in estimate'))
    checked, output, sample = collarbone._layout((SIDE, SIDE), CURVES)
    sn = (sample[2]-sample[0])*(sample[3]-sample[1])
    on = (output[2]-output[0])*(output[3]-output[1])
    assert collarbone.memory_estimate((SIDE, SIDE), checked) == 48*sn+4*on+8*1024**2
    assert collarbone.memory_estimate((SIDE, SIDE), checked) < collarbone.memory_estimate((SIDE, SIDE))
    assert sample[0] <= output[0] and sample[1] <= output[1]
    for bad in [(0, 12), (True, 12), (12, 65_537), (1, 2, 3)]:
        with pytest.raises(ValueError):
            collarbone.memory_estimate(bad)
    with pytest.raises(MemoryError):
        collarbone.memory_estimate((8000, 8000))


def test_strided_current_and_cropped_field_are_independent_neutral_copies(protocol):
    current = np.full((8, 12, 3), 0.3, dtype=np.float32)[:, ::2]
    current[0, 0, 0] = -0.0
    field = np.zeros((8, 12), dtype=np.float32)[:, ::2]
    output = collarbone.compose_field(current, field, -0.0,
        field_origin=(17, 40), source_shape=(SIDE, SIDE), origin=(17, 40))
    assert output.flags.owndata and output.flags.c_contiguous and output.flags.writeable
    assert not np.shares_memory(output, current)
    assert np.array_equal(output.view(np.uint32), current.view(np.uint32))


def test_curve_count_keys_identity_width_and_finite_points_refuse(protocol):
    rgb, coverage = source()
    for bad in [[], CURVES*2,
                [dict(CURVES[0], width=True)], [dict(CURVES[0], width=1e-6)],
                [dict(CURVES[0], width=3.0)], [dict(CURVES[0], id='both')],
                [dict(CURVES[0], points=[[0, 0.5], [0.5, 0.5], [0.9, 0.5]])],
                [dict(CURVES[0], points=[[0.1, 0.5], [float('nan'), 0.5], [0.9, 0.5]])],
                [dict(CURVES[0], points=CURVES[0]['points'][:2])],
                [dict(CURVES[0], generated=True)]]:
        with pytest.raises(ValueError):
            collarbone.prepare(rgb, coverage, bad)


def test_preparation_reads_only_real_roi_and_rejects_invalid_observed_values(protocol):
    rgb, coverage = source()
    # An unused corner is not a synthetic observation and is not snapshotted.
    rgb[0, 0] = np.nan
    collarbone.prepare(rgb, coverage, CURVES)
    rgb[64, 64] = np.nan
    with pytest.raises(ValueError, match='finite SDR'):
        collarbone.prepare(rgb, coverage, CURVES)
    rgb, coverage = source()
    coverage[64, 64] = 1.01
    with pytest.raises(ValueError, match='finite SDR'):
        collarbone.prepare(rgb, coverage, CURVES)


def test_compose_contract_checks_even_neutral(protocol):
    current = np.full((4, 5, 3), 0.3, dtype=np.float32)
    field = np.zeros((4, 5), dtype=np.float32)
    options = {'field_origin': (2, 3), 'source_shape': (SIDE, SIDE), 'origin': (2, 3)}
    for amount in [True, -0.1, 1.1, float('nan'), 10**1000]:
        with pytest.raises(ValueError):
            collarbone.compose_field(current, field, amount, **options)
    for bad in [float('nan'), 0.121, -0.121]:
        invalid = field.copy()
        invalid[0, 0] = bad
        with pytest.raises(ValueError, match='log-gain'):
            collarbone.compose_field(current, invalid, 0, **options)
    for bad_origin in [(-1, 0), (0.5, 0), (True, 0), (128, 128)]:
        with pytest.raises(ValueError):
            collarbone.compose_field(current, field, 0, **dict(options, origin=bad_origin))
    with pytest.raises(ValueError):
        collarbone.compose_field(current.astype(np.float64), field, 0, **options)


def test_cancellation_memory_missing_core_and_callback_errors_never_fallback(monkeypatch):
    rgb, coverage = source()
    monkeypatch.setattr(collarbone, 'native', lambda: pytest.fail('Must refuse before loading'))
    with pytest.raises(InterruptedError):
        collarbone.prepare(rgb, coverage, CURVES, cancelled=lambda: True)
    monkeypatch.setattr(collarbone, '_available_estimate', lambda: 0)
    with pytest.raises(MemoryError):
        collarbone.prepare(rgb, coverage, CURVES)
    def absent():
        raise RuntimeError('Collarbone Rust core is not installed; no fallback was applied')
    monkeypatch.setattr(collarbone, 'native', absent)
    monkeypatch.setattr(collarbone, '_available_estimate', lambda: 16*1024**3)
    assert not collarbone.available()
    with pytest.raises(RuntimeError, match='no fallback'):
        collarbone.prepare(rgb, coverage, CURVES)
    def broken():
        raise LookupError('callback failed')
    callback, errors = collarbone._callback(broken)
    assert callback(None) == 1
    with pytest.raises(LookupError, match='callback failed'):
        collarbone._result(4, lambda: False, errors)
    for code, error in [(1, ValueError), (2, ValueError), (3, ValueError),
                        (4, InterruptedError), (5, MemoryError), (6, RuntimeError)]:
        with pytest.raises(error):
            collarbone._result(code, lambda: False, [])


def test_corrupt_native_field_output_and_zero_field_composition_are_discarded(protocol, monkeypatch):
    class CorruptField(ZeroEvidenceCopyProtocol):
        def lrt_collarbone_prepare_v1(self, *args):
            code = super().lrt_collarbone_prepare_v1(*args)
            args[20][0] = 0.5
            return code
    monkeypatch.setattr(collarbone, 'native', lambda: CorruptField())
    rgb, coverage = source()
    with pytest.raises(RuntimeError, match='evidence'):
        collarbone.prepare(rgb, coverage, CURVES)
    class CorruptComposition(ZeroEvidenceCopyProtocol):
        def lrt_collarbone_compose_v1(self, *args):
            code = super().lrt_collarbone_compose_v1(*args)
            args[15][0] = 0.7
            return code
    monkeypatch.setattr(collarbone, 'native', lambda: CorruptComposition())
    with pytest.raises(RuntimeError, match='protected'):
        collarbone.compose_field(rgb, np.zeros((SIDE, SIDE), dtype=np.float32), 1.0,
                                 field_origin=(0, 0), source_shape=(SIDE, SIDE))
