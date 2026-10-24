# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN bridge contracts. No imports/tests were executed in delivery.

The boundary double returns fixed numeric constants; it does not implement a
Python inverse or sampler. Numerical expectations belong to original Rust tests.
Synthetic coordinates are not actual portrait evidence or production defaults.
"""
import ctypes as C
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from lumaretouch_engine import head_size_native as N


def prepared_fixture():
    return np.array([20., 470., 670., 1120., 20., 470., 670., 1120.,
                     570., 570., .08, 1201., 1601.])


def inputs_fixture():
    points = np.tile([570 / 1200, 570 / 1600, 0., 1., 1.], (33, 1))
    points[11, :2] = [440 / 1200, 1200 / 1600]
    points[12, :2] = [700 / 1200, 1200 / 1600]
    support = np.array([470 / 1200, 470 / 1600, 670 / 1200, 670 / 1600,
                        20 / 1200, 20 / 1600, 1120 / 1200, 1120 / 1600,
                        570 / 1200, 570 / 1600])
    return points, np.array([1., 1.]), support, (1601, 1201)


class RecordingNative:
    """Native-boundary double, fixed data only; never a geometric fallback."""
    def __init__(self, status=0, on_enter=None, delta=None, jac=None):
        self.status = status
        self.on_enter = on_enter
        self.delta = np.array([[-4., 4.], [0., 0.]] if delta is None else delta)
        self.jac = np.array([1.1814744801512287, 1.] if jac is None else jac)
        self.inputs = []
        self.pointers = []
        self.describe_calls = 0
        self.fact_values = np.array([20., 20., 1120., 1120., 470., 470., 670., 670.,
                                     570., 570., .92, 62.22539674441618,
                                     .44666666666666666, .3061777777777778, 1e-7, 64.])

    @staticmethod
    def _write(pointer, values):
        data = np.ascontiguousarray(values, dtype=np.float64)
        C.memmove(pointer, data.ctypes.data, data.nbytes)

    def _record(self, arrays, pointers):
        if self.on_enter:
            self.on_enter()
        self.inputs = [np.ctypeslib.as_array(ptr, shape=(length,)).copy()
                       for ptr, length in arrays]
        self.pointers = [C.cast(ptr, C.c_void_p).value for ptr in pointers]

    def lrt_head_size_prepare(self, p, pn, recipe, rn, support, sn, w, h, out, on):
        assert (pn, rn, sn, w, h, on) == (165, 2, 10, 1201, 1601, 13)
        self._record(((p, pn), (recipe, rn), (support, sn)), (p, recipe, support, out))
        if not self.status:
            self._write(out, prepared_fixture())
        return self.status

    def lrt_head_size_describe(self, state, sn, out, on):
        assert (sn, on) == (13, 16)
        self.describe_calls += 1
        if not self.status:
            self._write(out, self.fact_values)
        return self.status

    def lrt_head_size_evaluate(self, state, sn, p, pn, count, out, on, jac, jn):
        assert sn == 13 and pn == on == 2 * count and jn == count
        self._record(((state, sn), (p, pn)), (state, p, out, jac))
        if not self.status:
            self._write(out, self.delta)
            self._write(jac, self.jac)
        return self.status


class HeadSizeBridgeContracts(TestCase):
    def test_prepare_snapshots_all_inputs_and_freezes_bytes_backed_state(self):
        p, recipe, support, shape = inputs_fixture()
        before = [value.copy() for value in (p, recipe, support)]
        fake = RecordingNative(on_enter=lambda: (p.fill(0.), recipe.fill(0.), support.fill(0.)))
        with patch.object(N, 'native', return_value=fake):
            prepared = N.prepare(p, recipe, support, shape)
        for actual, expected in zip(fake.inputs, before):
            np.testing.assert_array_equal(actual, expected.ravel())
        self.assertEqual(len(set(fake.pointers)), 4)
        self.assertEqual(fake.describe_calls, 1)
        self.assertIsInstance(prepared.base, bytes)
        self.assertFalse(prepared.flags.writeable)
        with self.assertRaises(ValueError):
            prepared.setflags(write=True)

    def test_evaluate_snapshots_returns_native_sign_and_irreversibly_freezes_output(self):
        state = prepared_fixture()
        queries = np.array([[616., 524.], [440., 1200.]])
        before = [state.copy(), queries.copy()]
        fake = RecordingNative(on_enter=lambda: (state.fill(0.), queries.fill(0.)))
        with patch.object(N, 'native', return_value=fake):
            result = N.evaluate(state, queries)
        for actual, expected in zip(fake.inputs, before):
            np.testing.assert_array_equal(actual, expected.ravel())
        np.testing.assert_array_equal(result, [[-4., 4.], [0., 0.]])
        np.testing.assert_array_equal(before[1] - result, [[620., 520.], [440., 1200.]])
        self.assertEqual(len(set(fake.pointers)), 4)
        self.assertFalse(result.flags.writeable)
        with self.assertRaises(ValueError):
            result.setflags(write=True)

    def test_facts_keep_complete_head_pivot_scale_and_unaccepted_status(self):
        with patch.object(N, 'native', return_value=RecordingNative()):
            facts = N.facts(prepared_fixture())
        self.assertEqual(facts['support_box'], [20., 20., 1120., 1120.])
        self.assertEqual(facts['plateau_box'], [470., 470., 670., 670.])
        self.assertEqual(facts['pivot'], [570., 570.])
        self.assertEqual(facts['scale'], .92)
        self.assertEqual(facts['plateau_scale'], .92)
        self.assertEqual(facts['source_dimensions'], [1201, 1601])
        self.assertEqual(facts['inverse_max_iterations'], 64)
        self.assertFalse(facts['runtime_quality_accepted'])

    def test_malformed_shapes_unbounded_inputs_and_nonfinite_values_stop_before_native(self):
        p, recipe, support, shape = inputs_fixture()
        with patch.object(N, 'native', side_effect=AssertionError('must not load')):
            for args in ((p[:32], recipe, support, shape), (p, recipe[:1], support, shape),
                         (p, recipe, support[:9], shape), (p, recipe, support, (1601., 1201)),
                         (p, recipe, support, (True, 1201)), (p, recipe, support, (1601, 1))):
                with self.assertRaises(ValueError):
                    N.prepare(*args)
            for queries in ([1., 2.], [[float('nan'), 0.]], np.zeros((2, 3)),
                            (value for value in [[0., 0.]])):
                with self.assertRaises(ValueError):
                    N.evaluate(prepared_fixture(), queries)
            with self.assertRaises(ValueError):
                N.facts(np.zeros(12))

    def test_oversized_view_is_rejected_before_any_snapshot_allocation(self):
        huge = np.lib.stride_tricks.as_strided(np.zeros((1, 2)),
                                              shape=(N.MAX_POINTS + 1, 2), strides=(0, 8))
        state = prepared_fixture()
        with patch.object(N, '_snapshot', side_effect=AssertionError('must not allocate')):
            with self.assertRaises(ValueError):
                N.evaluate(state, huge)

    def test_native_refusals_never_return_identity_or_publish_uninitialized_outputs(self):
        for status in (1, 2, 4, 5, 6, 8, 9, 127):
            with self.subTest(status=status), patch.object(N, 'native', return_value=RecordingNative(status)):
                with self.assertRaises(ValueError):
                    N.prepare(*inputs_fixture())
                with self.assertRaises(ValueError):
                    N.facts(prepared_fixture())
                with self.assertRaises(ValueError):
                    N.evaluate(prepared_fixture(), [[616., 524.], [440., 1200.]])

    def test_bad_native_displacement_determinant_and_source_domain_are_not_clipped(self):
        bad = [RecordingNative(delta=[[90., 0.], [0., 0.]]),
               RecordingNative(delta=[[float('nan'), 0.], [0., 0.]]),
               RecordingNative(jac=[0., 1.]), RecordingNative(jac=[4., 1.])]
        for fake in bad:
            with patch.object(N, 'native', return_value=fake), self.assertRaises(ValueError):
                N.evaluate(prepared_fixture(), [[616., 524.], [440., 1200.]])
        fake = RecordingNative(delta=[[2., 0.], [0., 0.]])
        with patch.object(N, 'native', return_value=fake), self.assertRaises(ValueError):
            N.evaluate(prepared_fixture(), [[1., 1.], [440., 1200.]])

    def test_bad_native_metadata_is_not_relabelled_as_accepted(self):
        for index, invalid in ((10, .91), (11, 129.), (12, .46), (13, 0.),
                               (14, 1e-6), (15, 65.), (0, float('nan'))):
            fake = RecordingNative()
            fake.fact_values[index] = invalid
            with patch.object(N, 'native', return_value=fake), self.assertRaises(ValueError):
                N.facts(prepared_fixture())

    def test_empty_queries_still_validate_state_and_produce_immutable_empty_field(self):
        fake = RecordingNative(delta=np.empty((0, 2)), jac=np.empty(0))
        with patch.object(N, 'native', return_value=fake):
            result = N.evaluate(prepared_fixture(), [])
        self.assertEqual(fake.describe_calls, 1)
        self.assertEqual(result.shape, (0, 2))
        self.assertFalse(result.flags.writeable)
        with patch.object(N, 'native', return_value=RecordingNative(status=6)):
            with self.assertRaises(ValueError):
                N.evaluate(prepared_fixture(), [])

    def test_available_reports_only_installed_abi_readiness_without_fallback(self):
        for error in (RuntimeError('ABI'), OSError('load'), AttributeError('symbol')):
            with patch.object(N, 'native', side_effect=error):
                self.assertFalse(N.available())
        with patch.object(N, 'native', return_value=RecordingNative()):
            self.assertTrue(N.available())
