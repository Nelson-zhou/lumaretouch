// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Fixtures are not proof of runtime or photographic quality.
use super::*;

const PARAMS: [f64; 11] = [50.0, 60.0, 1.0, 0.0, 0.0, -1.0,
                           40.0, 60.0, 1.0, 2.0, 0.94];

fn call(points: &[f64], params: &[f64; 11], output: &mut [f64]) -> i32 {
    unsafe {
        lrt_face_size_evaluate_v1(points.as_ptr(), points.len(), params.as_ptr(), 11,
                                 points.len() / 2, output.as_mut_ptr(), output.len())
    }
}

fn run(points: &[f64], params: &[f64; 11]) -> Vec<f64> {
    let mut output = vec![77.0; points.len()];
    assert_eq!(call(points, params, &mut output), 0);
    output
}

fn close(actual: f64, expected: f64) {
    assert!((actual - expected).abs() <= 1.0e-11 * expected.abs().max(1.0),
            "actual={actual}, expected={expected}");
}

#[test]
fn abi_and_positive_shrink_negative_enlarge_use_inverse_not_forward_delta() {
    assert_eq!(lrt_face_size_abi(), 1);
    let points = [70.0, 45.0, 30.0, 75.0, 50.0, 60.0];
    for scale in [0.94, 1.06] {
        let mut params = PARAMS;
        params[10] = scale;
        let output = run(&points, &params);
        for (point, delta) in points.chunks_exact(2).zip(output.chunks_exact(2)) {
            for axis in 0..2 {
                close(delta[axis], (1.0 - 1.0 / scale) * (point[axis] - params[axis]));
                close(point[axis] - delta[axis],
                      params[axis] + (point[axis] - params[axis]) / scale);
            }
        }
        assert_eq!(output[4].to_bits(), 0);
        assert_eq!(output[5].to_bits(), 0);
        assert_eq!(output[0].is_sign_negative(), scale < 1.0);
    }
}

#[test]
fn whole_core_is_uniform_in_both_axes_without_eye_nose_or_mouth_pins() {
    let points = [35.0, 40.0, 65.0, 40.0, 50.0, 55.0, 50.0, 80.0,
                  90.0, 60.0, 50.0, 0.0];
    let output = run(&points, &PARAMS);
    for (point, delta) in points.chunks_exact(2).zip(output.chunks_exact(2)) {
        assert!(delta.iter().any(|v| *v != 0.0));
        close(delta[0], (1.0 - 1.0 / PARAMS[10]) * (point[0] - PARAMS[0]));
        close(delta[1], (1.0 - 1.0 / PARAMS[10]) * (point[1] - PARAMS[1]));
    }
}

#[test]
fn neutral_and_at_or_beyond_outer_are_exact_positive_zero() {
    let outside = [130.0, 60.0, -30.0, 60.0, 50.0, -60.0,
                   50.0, 180.0, 5000.0, -6000.0];
    assert!(run(&outside, &PARAMS).iter().all(|v| v.to_bits() == 0));
    let mut params = PARAMS;
    params[10] = 1.0;
    let all = [50.0, 60.0, 60.0, 70.0, 5000.0, -6000.0, -0.0, -0.0];
    assert!(run(&all, &params).iter().all(|v| v.to_bits() == 0));
    // Neutral support remains valid for extremely small positive radii.
    params[8] = f64::MIN_POSITIVE;
    params[9] = f64::MIN_POSITIVE * 2.0;
    assert!(run(&all, &params).iter().all(|v| v.to_bits() == 0));
}

#[test]
fn quintic_transition_has_correct_midpoint_and_edges_without_strength_clamping() {
    let points = [90.0, 60.0, 100.0, 60.0, 110.0, 60.0,
                  120.0, 60.0, 130.0, 60.0];
    let output = run(&points, &PARAMS);
    for (i, weight) in [1.0, 0.896484375, 0.5, 0.103515625, 0.0].iter().enumerate() {
        close(output[2 * i], (1.0 - 1.0 / PARAMS[10]) * weight * (points[2 * i] - 50.0));
        assert_eq!(output[2 * i + 1].to_bits(), 0);
    }
}

#[test]
fn queries_immediately_inside_transition_edges_do_not_spuriously_refuse() {
    let mut params = PARAMS;
    params[0] = 0.0;
    params[1] = 0.0;
    params[6] = 1.0;
    params[7] = 1.0;
    let just_above_inner = f64::from_bits(1.0f64.to_bits() + 1);
    let just_below_outer = f64::from_bits(2.0f64.to_bits() - 1);
    let points = [just_above_inner, 0.0, just_below_outer, 0.0];
    let output = run(&points, &params);
    assert!(output[0] < 0.0);
    assert!(output[2] <= 0.0);
    for i in [0, 2] {
        assert!(output[i].abs() <= ((params[10] - 1.0) / params[10]).abs() * points[i]);
    }
}

#[test]
fn adjacent_representable_nonneutral_scales_keep_their_tiny_motion() {
    let points = [70.0, 45.0, 30.0, 75.0];
    for scale in [f64::from_bits(1.0f64.to_bits() - 1),
                  f64::from_bits(1.0f64.to_bits() + 1)] {
        let mut params = PARAMS;
        params[10] = scale;
        let output = run(&points, &params);
        let coefficient = (scale - 1.0) / scale;
        for i in 0..points.len() {
            let expected = coefficient * (points[i] - params[i % 2]);
            assert_ne!(output[i], 0.0);
            assert!((output[i] - expected).abs() <= expected.abs() * 1.0e-14);
        }
    }
}

#[test]
fn elliptic_support_roll_translation_and_uniform_image_scaling_are_covariant() {
    let points = [70.0, 45.0, 110.0, 60.0, 50.0, 150.0];
    let reference = run(&points, &PARAMS);
    let mut params = PARAMS;
    params[0] = 300.0;
    params[1] = 400.0;
    params[2..6].copy_from_slice(&[0.6, 0.8, 0.8, -0.6]);
    params[6] *= 3.0;
    params[7] *= 3.0;
    let mut transformed = [0.0; 6];
    for (point, target) in points.chunks_exact(2).zip(transformed.chunks_exact_mut(2)) {
        let x = point[0] - PARAMS[0];
        let y = point[1] - PARAMS[1];
        target[0] = params[0] + 3.0 * (0.6 * x - 0.8 * y);
        target[1] = params[1] + 3.0 * (0.8 * x + 0.6 * y);
    }
    let output = run(&transformed, &params);
    for (delta, rotated) in reference.chunks_exact(2).zip(output.chunks_exact(2)) {
        close(rotated[0], 3.0 * (0.6 * delta[0] - 0.8 * delta[1]));
        close(rotated[1], 3.0 * (0.8 * delta[0] + 0.6 * delta[1]));
    }
}

#[test]
fn invalid_values_everywhere_leave_output_untouched_even_when_neutral() {
    let points = [70.0, 45.0, 30.0, 75.0];
    for index in 0..11 {
        for invalid in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let mut params = PARAMS;
            params[10] = 1.0;
            params[index] = invalid;
            let mut output = [77.0; 4];
            assert_eq!(call(&points, &params, &mut output), VALUE_ERROR);
            assert_eq!(output, [77.0; 4]);
        }
    }
    for index in 0..4 {
        for invalid in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let mut bad = points;
            bad[index] = invalid;
            let mut params = PARAMS;
            params[10] = 1.0;
            let mut output = [77.0; 4];
            assert_eq!(call(&bad, &params, &mut output), VALUE_ERROR);
            assert_eq!(output, [77.0; 4]);
        }
    }
}

#[test]
fn scale_frame_extents_support_and_fold_risk_are_rejected_not_repaired() {
    let points = [70.0, 45.0];
    for (index, invalid, expected) in [
        (10, 0.939, VALUE_ERROR), (10, 1.061, VALUE_ERROR),
        (2, 0.0, FRAME_ERROR), (2, 1.00001, FRAME_ERROR),
        (4, 0.1, FRAME_ERROR), (6, 0.0, FRAME_ERROR), (7, -1.0, FRAME_ERROR),
        (8, 0.0, BOUND_ERROR), (8, 2.0, BOUND_ERROR), (9, 0.9, BOUND_ERROR),
        (9, 1.01, BOUND_ERROR),
    ] {
        let mut params = PARAMS;
        params[index] = invalid;
        let mut output = [77.0; 2];
        assert_eq!(call(&points, &params, &mut output), expected);
        assert_eq!(output, [77.0; 2]);
    }
    // Both scale directions must satisfy the stated conservative derivative bound.
    for scale in [MIN_SCALE, MAX_SCALE] {
        let mut params = PARAMS;
        params[9] = 1.01;
        params[10] = scale;
        let mut output = [77.0; 2];
        assert_eq!(call(&points, &params, &mut output), BOUND_ERROR);
        assert_eq!(output, [77.0; 2]);
    }
}

#[test]
fn numeric_error_after_an_earlier_valid_query_does_not_partially_publish() {
    let mut params = PARAMS;
    params[0] = -f64::MAX;
    let points = [-f64::MAX, 60.0, f64::MAX, 60.0];
    let mut output = [77.0; 4];
    assert_eq!(call(&points, &params, &mut output), BOUND_ERROR);
    assert_eq!(output, [77.0; 4]);
}

#[test]
fn all_exact_lengths_and_query_count_are_checked_before_dereference() {
    let points = [70.0, 45.0];
    for index in 0..3 {
        for invalid in [0, 1, usize::MAX] {
            let mut lengths = [2, 11, 2];
            lengths[index] = invalid;
            let mut output = [77.0; 2];
            let code = unsafe {
                lrt_face_size_evaluate_v1(points.as_ptr(), lengths[0], PARAMS.as_ptr(),
                    lengths[1], 1, output.as_mut_ptr(), lengths[2])
            };
            assert_eq!(code, ABI_ERROR);
            assert_eq!(output, [77.0; 2]);
        }
    }
    for count in [0, MAX_POINTS + 1, usize::MAX] {
        let mut output = [77.0; 2];
        let code = unsafe {
            lrt_face_size_evaluate_v1(points.as_ptr(), 2, PARAMS.as_ptr(), 11,
                                     count, output.as_mut_ptr(), 2)
        };
        assert_eq!(code, ABI_ERROR);
        assert_eq!(output, [77.0; 2]);
    }
}

#[test]
fn null_unaligned_overflowing_and_overlapping_pointers_are_rejected() {
    let points = [70.0, 45.0];
    for invalid in [ptr::null(), 1usize as *const f64, (usize::MAX - 7) as *const f64] {
        for index in 0..3 {
            let mut output = [77.0; 2];
            let p = if index == 0 { invalid } else { points.as_ptr() };
            let f = if index == 1 { invalid } else { PARAMS.as_ptr() };
            let out = if index == 2 { invalid as *mut f64 } else { output.as_mut_ptr() };
            let code = unsafe { lrt_face_size_evaluate_v1(p, 2, f, 11, 1, out, 2) };
            assert_eq!(code, ABI_ERROR);
            assert_eq!(output, [77.0; 2]);
        }
    }
    for offset in [0, 1] {
        let mut storage = [77.0; 16];
        let code = unsafe {
            lrt_face_size_evaluate_v1(storage.as_ptr(), 2, PARAMS.as_ptr(), 11, 1,
                                     storage.as_mut_ptr().add(offset), 2)
        };
        assert_eq!(code, ABI_ERROR);
        assert_eq!(storage, [77.0; 16]);
        let code = unsafe {
            lrt_face_size_evaluate_v1(points.as_ptr(), 2, storage.as_ptr(), 11, 1,
                                     storage.as_mut_ptr().add(offset), 2)
        };
        assert_eq!(code, ABI_ERROR);
        assert_eq!(storage, [77.0; 16]);
    }
}

#[test]
fn maximum_batch_is_bounded_and_support_zero_is_positive_zero() {
    let points = vec![1000.0; MAX_POINTS * 2];
    let output = run(&points, &PARAMS);
    assert_eq!(output.len(), MAX_POINTS * 2);
    assert!(output.iter().all(|value| value.to_bits() == 0));
}
