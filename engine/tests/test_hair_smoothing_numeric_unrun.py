# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Requires the separately built matching native core.

No test in this file has been executed for this change. These fixtures test the
numerical boundary only; they do not authorize source ownership or photo quality.
"""
import math
import unittest
import numpy as np
from lumaretouch_engine import hair_smoothing_measure as M
from lumaretouch_engine import hair_smoothing_native as N


def frozen(value):
    value = np.ascontiguousarray(value, dtype=np.float32)
    return np.frombuffer(value.tobytes(), dtype=np.float32).reshape(value.shape)


def fixture(side=97):
    yy, xx = np.mgrid[:side, :side]
    value = 0.36 + 0.025*np.sin(xx*2*math.pi/7) + 0.003*np.cos(yy*2*math.pi/3)
    source = frozen(np.repeat(value[..., None], 3, axis=2))
    target = np.zeros((side, side), np.float32); target[24:-24, 24:-24] = 1
    context = np.ones((side, side), np.float32)
    hard = np.zeros((side, side), bool)
    return source, target, context, hard


class NativeHairDirectionalContractUnrun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # An unavailable library is NOT a passed native acceptance suite.
        if not N.available():
            raise unittest.SkipTest('UNRUN native readiness: build/install matching hair core first')

    def solve(self, values=None, **kwargs):
        values = fixture() if values is None else values
        options = {'texture_scale_px': 2.0, 'byte_budget': M.plan(values[0].shape[:2], 2.0)['required_work_bytes']}
        options.update(kwargs)
        return M.measure(*values, **options)

    def test_actual_directional_signed_field_not_global_blur(self):
        measured = self.solve()
        self.assertEqual(measured.source_shape_hw, (97, 97))
        self.assertGreater(measured.facts['directional_pixels'], 0)
        self.assertGreater(measured.facts['changed_pixels'], 0)
        self.assertTrue(np.any(measured.log_gain > 0))
        self.assertTrue(np.any(measured.log_gain < 0))
        self.assertTrue(np.all(np.abs(measured.log_gain.astype(np.float64)) <= M.MAX_LOG_GAIN))
        self.assertTrue(np.all(measured.log_gain[~measured.eligible_mask] == 0))
        with self.assertRaises(ValueError):
            measured.log_gain.setflags(write=True)
        with self.assertRaises(ValueError):
            measured.eligible_mask.setflags(write=True)

    def test_constant_owned_texture_is_honest_no_direction(self):
        source, target, context, hard = fixture()
        measured = self.solve((frozen(np.full(source.shape, .36)), target, context, hard))
        self.assertGreater(measured.facts['supported_pixels'], 0)
        self.assertEqual(measured.facts['changed_pixels'], 0)
        self.assertEqual(measured.facts['no_signal_reason'], 'no_admitted_directional_signal')
        self.assertTrue(np.all(measured.log_gain == 0))

    def test_missing_complete_context_is_refusal(self):
        source, target, context, hard = fixture()
        context.fill(0); target.fill(0); context[48, 48] = target[48, 48] = 1
        with self.assertRaises(N.HairSmoothingContextError):
            self.solve((source, target, context, hard))

    def test_hard_pixel_excludes_entire_dependency_halo(self):
        source, target, context, hard = fixture()
        hard[48, 48] = True
        measured = self.solve((source, target, context, hard))
        radius = M.plan(source.shape[:2], 2)['dependency_radius_px']
        self.assertFalse(np.any(measured.eligible_mask[48-radius:49+radius, 48-radius:49+radius]))
        self.assertTrue(np.all(measured.log_gain[48-radius:49+radius, 48-radius:49+radius] == 0))

    def test_outside_owned_pixels_cannot_influence_complete_taps(self):
        source, target, context, hard = fixture()
        context[:, :8] = 0
        first = self.solve((source, target, context, hard))
        altered = source.copy(); altered[:, :8] = .94
        second = self.solve((frozen(altered), target, context, hard))
        np.testing.assert_array_equal(first.log_gain.view(np.uint32), second.log_gain.view(np.uint32))

    def test_alias_layout_nonfinite_and_scale_rejected(self):
        source, target, context, hard = fixture()
        with self.assertRaises(ValueError):
            self.solve((source, target, target, hard))
        with self.assertRaises(ValueError):
            self.solve((source[:, ::-1], target, context, hard))
        invalid = source.copy(); invalid[30, 30, 0] = np.nan
        with self.assertRaises(ValueError):
            self.solve((frozen(invalid), target, context, hard))
        for scale in (0.999, 8.001, float('nan'), True):
            with self.assertRaises(ValueError):
                M.plan(source.shape[:2], scale)
        with self.assertRaises(MemoryError):
            self.solve(byte_budget=1)

    def test_current_chroma_ratios_and_common_headroom(self):
        current = np.array([[[.1, .3, .6], [.2, .6, 1.0], [.2, .6, 1.0]]], np.float32)
        gain = np.array([[.07, .07, -.07]], np.float32)
        output = M.apply(current, gain, amount=1)
        np.testing.assert_allclose(output[0, 0] / current[0, 0], np.repeat(math.exp(float(gain[0, 0])), 3), rtol=2e-7)
        np.testing.assert_array_equal(output[0, 1].view(np.uint32), current[0, 1].view(np.uint32))
        np.testing.assert_allclose(output[0, 2] / current[0, 2], np.repeat(math.exp(float(gain[0, 2])), 3), rtol=2e-7)
        self.assertTrue(np.all(output <= 1))

    def test_zero_field_and_amount_are_bit_exact(self):
        current = np.array([[[0.0, -0.0, 1.0], [.111, .333, .777]]], np.float32)
        field = np.array([[0.0, .08]], np.float32)
        neutral = M.apply(current, field, amount=0)
        np.testing.assert_array_equal(neutral.view(np.uint32), current.view(np.uint32))
        zeros = M.apply(current, np.zeros((1, 2), np.float32), amount=1)
        np.testing.assert_array_equal(zeros.view(np.uint32), current.view(np.uint32))

    def test_frozen_eligibility_survives_tile_composition_and_overlap_refuses(self):
        from lumaretouch_engine.people_effects import LocalEffect
        from lumaretouch_engine.hair_smoothing_composition import apply_np
        ref = {'asset_sha256': '1'*64, 'face_instance_id': 'face-a', 'analysis_revision': 1}
        shape = (9, 11)
        gain = frozen(np.full((*shape, 1), .025, np.float32))
        eligible = np.frombuffer(bytes([1])*(shape[0]*shape[1]), dtype=np.bool_).reshape(shape)
        facts = {'operation_id': 'lnx.hair_smoothing.v1', 'face_ref': ref,
            'source_proof': {'source': 'fixture-only-no-host-authority'},
            'measurement_key': '2'*64, 'source_shape_hw': list(shape),
            'application_shape_hw': list(shape), 'runtime_quality_accepted': False,
            'review_authority': True, 'display_projection': None}
        record = LocalEffect(ref, 'hair_smoothing', (0, 0, *shape), log_gain=gain,
            eligibility=eligible, amounts={'amount': .5}, facts=facts)
        current = np.full((*shape, 3), .3, np.float32)
        whole, _ = apply_np(current, [record])
        tiled, _ = apply_np(current[2:7, 3:8].copy(), [record], source_shape=shape, origin=(2, 3))
        np.testing.assert_array_equal(whole[2:7, 3:8].view(np.uint32), tiled.view(np.uint32))
        other = {**ref, 'face_instance_id': 'face-b'}
        conflict = LocalEffect(other, 'hair_smoothing', (0, 0, *shape), log_gain=frozen(np.zeros((*shape, 1))),
            eligibility=eligible, amounts={'amount': .5}, facts={**facts, 'face_ref': other})
        with self.assertRaises(ValueError):
            apply_np(current, [record, conflict])
        invalid = LocalEffect(ref, 'hair_smoothing', (0, 0, *shape), log_gain=gain,
            eligibility=None, amounts={'amount': .5}, facts=facts)
        with self.assertRaises(ValueError):
            apply_np(current, [invalid])

    def test_cancel_and_invalid_abi_leave_outputs_untouched(self):
        source, target, context, hard = fixture()
        output = np.full(target.shape, .25, np.float32)
        eligible = np.full(target.shape, 199, np.uint8)
        counts = np.full(4, 999, np.uint64); metrics = np.full(2, 999., np.float64)
        hard = hard.view(np.uint8)
        callback = N.CANCEL(lambda _: 1)
        args = [source.ctypes.data_as(N.P), source.size, target.ctypes.data_as(N.P), target.size,
            context.ctypes.data_as(N.P), context.size, hard.ctypes.data_as(N.BP), hard.size,
            97, 97, 2., M.plan(target.shape, 2)['required_work_bytes'], output.ctypes.data_as(N.P), output.size,
            eligible.ctypes.data_as(N.BP), eligible.size, counts.ctypes.data_as(N.UP), counts.size,
            metrics.ctypes.data_as(N.DP), metrics.size, callback, None]
        self.assertEqual(N.native().lrt_hair_smoothing_measure_v1(*args), 6)
        self.assertTrue(np.all(output == .25)); self.assertTrue(np.all(eligible == 199))
        self.assertTrue(np.all(counts == 999)); self.assertTrue(np.all(metrics == 999))
        args[13] = output.size - 1
        self.assertEqual(N.native().lrt_hair_smoothing_measure_v1(*args), 1)
        self.assertTrue(np.all(output == .25)); self.assertTrue(np.all(counts == 999))


if __name__ == '__main__':
    unittest.main()
