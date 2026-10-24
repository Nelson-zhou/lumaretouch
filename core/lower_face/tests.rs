// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Fixtures are not evidence of numerical or image acceptance.
use super::*;

const PARAMS: [f64; 11] = [50.0, 60.0, 1.0, 0.0, 0.0, 1.0,
                          40.0, 25.0, 50.0, 0.5, 1.0];
fn call(points: &[f64], params: &[f64; 11], output: &mut [f64]) -> i32 {
    unsafe { lrt_lower_face_evaluate_v1(points.as_ptr(), points.len(), params.as_ptr(), 11,
                                      points.len() / 2, output.as_mut_ptr(), output.len()) }
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
// Forward-only fixture oracle. This is never an application inverse fallback.
fn s(z: f64) -> f64 { z * z * z * (10.0 - 15.0 * z + 6.0 * z * z) }
fn forward_weight(t: f64, tail: f64) -> f64 {
    if t <= 0.0 || t >= 1.0 + tail { 0.0 }
    else if t <= 1.0 { s(t) } else { 1.0 - s((t - 1.0) / tail) }
}

#[test]
fn abi_chin_target_and_signs_require_true_inverse_not_negated_forward() {
    assert_eq!(lrt_lower_face_abi(), 1);
    for amount in [-1.0, -0.3, 0.3, 1.0] {
        let mut p = PARAMS;
        p[10] = amount;
        let shift = GAIN * p[6] * amount;
        let q = [p[0], p[1] + p[6] + shift];
        let output = run(&q, &p);
        assert_eq!(output[0].to_bits(), 0);
        close(output[1], shift);
        close(q[1] - output[1], p[1] + p[6]);
        assert_eq!(output[1].is_sign_positive(), amount > 0.0);
        let naive = shift * forward_weight((q[1] - p[1]) / p[6], p[9]);
        assert!((output[1] - naive).abs() > 1.0e-7);
    }
}

#[test]
fn monotone_forward_roundtrips_every_signed_tail_and_lateral_region() {
    for amount in [-1.0, -0.25, 0.25, 1.0] {
        for tail in [0.25, 0.5, 1.0] {
            for (u, l) in [(0.0, 1.0), (25.0, 1.0), (37.5, 0.5), (50.0, 0.0)] {
                let mut p = PARAMS;
                p[9] = tail;
                p[10] = amount;
                let mut points = Vec::new();
                let mut expected = Vec::new();
                let mut previous = f64::NEG_INFINITY;
                for i in 0..=512 {
                    let t = (1.0 + tail) * i as f64 / 512.0;
                    let v = t * p[6];
                    let shift = GAIN * amount * p[6] * l * forward_weight(t, tail);
                    let qv = v + shift;
                    assert!(qv > previous);
                    previous = qv;
                    points.extend_from_slice(&[p[0] + u, p[1] + qv]);
                    expected.extend_from_slice(&[0.0, shift]);
                }
                let output = run(&points, &p);
                for (actual, expected) in output.iter().zip(expected.iter()) {
                    close(*actual, *expected);
                }
            }
        }
    }
}

#[test]
fn derivative_lower_bound_and_quintic_join_values_are_explicit() {
    for tail in [0.25, 0.5, 1.0] {
        for amount in [-1.0, 1.0] {
            for i in 0..=1024 {
                let t = (1.0 + tail) * i as f64 / 1024.0;
                let (weight, slope) = vertical(t, tail);
                assert!((0.0..=1.0).contains(&weight));
                assert!(1.0 + GAIN * amount * slope >= MIN_FORWARD_DERIVATIVE - 1.0e-14);
            }
        }
        assert_eq!(vertical(0.0, tail), (0.0, 0.0));
        assert_eq!(vertical(1.0, tail), (1.0, 0.0));
        assert_eq!(vertical(1.0 + tail, tail), (0.0, 0.0));
        close(vertical(0.5, tail).0, 0.5);
        close(vertical(1.0 + tail * 0.5, tail).0, 0.5);
    }
}

#[test]
fn neutral_upper_boundary_and_outside_are_exact_positive_zero() {
    let points = [50.0, 60.0, 50.0, 20.0, 50.0, 120.0, 50.0, 121.0,
                  100.0, 80.0, 0.0, 80.0, 5000.0, -6000.0];
    assert!(run(&points, &PARAMS).iter().all(|v| v.to_bits() == 0));
    let mut p = PARAMS;
    p[10] = -0.0;
    let all = [50.0, 60.0, 60.0, 80.0, -f64::MAX, f64::MAX, -0.0, -0.0];
    assert!(run(&all, &p).iter().all(|v| v.to_bits() == 0));
}

#[test]
fn root_stays_in_signed_amplitude_bracket_and_lateral_coordinate_is_preserved() {
    for amount in [-1.0, 1.0] {
        let mut p = PARAMS;
        p[10] = amount;
        let points = [50.0, 80.0, 85.0, 103.0, 99.0, 119.0];
        let output = run(&points, &p);
        for delta in output.chunks_exact(2) {
            assert_eq!(delta[0].to_bits(), 0);
            assert!(delta[1] * amount > 0.0);
            assert!(delta[1].abs() <= GAIN * p[6]);
        }
    }
}

#[test]
fn roll_translation_uniform_scaling_and_both_frame_handednesses_are_covariant() {
    let points = [55.0, 80.0, 85.0, 103.0, 99.0, 119.0];
    let reference = run(&points, &PARAMS);
    for handedness in [-1.0, 1.0] {
        let mut p = PARAMS;
        p[0] = 300.0;
        p[1] = 400.0;
        p[2..6].copy_from_slice(&[0.6, 0.8, -0.8 * handedness, 0.6 * handedness]);
        for extent in &mut p[6..9] { *extent *= 3.0; }
        let mut transformed = [0.0; 6];
        for (point, target) in points.chunks_exact(2).zip(transformed.chunks_exact_mut(2)) {
            let x = point[0] - PARAMS[0];
            let y = point[1] - PARAMS[1];
            target[0] = p[0] + 3.0 * (p[2] * x + p[4] * y);
            target[1] = p[1] + 3.0 * (p[3] * x + p[5] * y);
        }
        let output = run(&transformed, &p);
        for (delta, rotated) in reference.chunks_exact(2).zip(output.chunks_exact(2)) {
            close(rotated[0], 3.0 * p[4] * delta[1]);
            close(rotated[1], 3.0 * p[5] * delta[1]);
            close(rotated[0] * p[2] + rotated[1] * p[3], 0.0);
        }
    }
}

#[test]
fn accepted_frame_roundoff_is_canonicalized_not_treated_as_geometric_skew() {
    let mut p = PARAMS;
    p[2..6].copy_from_slice(&[1.0 + 1.0e-12, 0.0, 1.0e-12, 1.0 - 1.0e-12]);
    let g = validate(&[], &p).unwrap();
    assert_eq!((g.rx, g.ry, g.dx, g.dy), (1.0, 0.0, -0.0, 1.0));
    let points = [50.0, 80.0, 85.0, 103.0];
    assert_eq!(run(&points, &p), run(&points, &PARAMS));
}

#[test]
fn tiny_amount_preserves_representable_shift_without_source_subtraction() {
    let mut p = PARAMS;
    p[0] = 0.0;
    p[1] = 0.0;
    p[6] = 1.0e300;
    for amount in [1.0e-20, -1.0e-20, f64::from_bits(1), -f64::from_bits(1)] {
        p[10] = amount;
        let points = [0.0, 0.5 * p[6]];
        let result = run(&points, &p);
        let expected = ((GAIN * p[6]) * amount) * 0.5;
        assert_ne!(result[1], 0.0);
        assert!((result[1] - expected).abs() <= expected.abs() * 1.0e-13);
        // Delta may be representable even when coordinate subtraction rounds it
        // away. This is not a promise of effective pixel movement.
        assert_eq!(points[1] - result[1], points[1]);
    }
}

#[test]
fn all_nonfinite_values_and_invalid_geometry_refuse_even_for_neutral() {
    let points = [50.0, 80.0];
    for index in 0..11 {
        for bad in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let mut p = PARAMS;
            p[10] = 0.0;
            p[index] = bad;
            let mut output = [77.0; 2];
            assert_eq!(call(&points, &p, &mut output), VALUE_ERROR);
            assert_eq!(output, [77.0; 2]);
        }
    }
    for index in 0..2 {
        for bad in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let mut point = points;
            point[index] = bad;
            let mut output = [77.0; 2];
            assert_eq!(call(&point, &PARAMS, &mut output), VALUE_ERROR);
            assert_eq!(output, [77.0; 2]);
        }
    }
    for (index, bad, expected) in [(10, -1.01, VALUE_ERROR), (10, 1.01, VALUE_ERROR),
        (2, 0.0, FRAME_ERROR), (2, 1.000001, FRAME_ERROR), (4, 1.0e-8, FRAME_ERROR),
        (6, 0.0, FRAME_ERROR), (6, -1.0, FRAME_ERROR), (7, 0.0, BOUND_ERROR),
        (7, 50.0, BOUND_ERROR), (8, 24.0, BOUND_ERROR), (9, 0.249, BOUND_ERROR),
        (9, 1.001, BOUND_ERROR)] {
        let mut p = PARAMS;
        p[10] = 0.0;
        p[index] = bad;
        let mut output = [77.0; 2];
        assert_eq!(call(&points, &p, &mut output), expected);
        assert_eq!(output, [77.0; 2]);
    }
}

#[test]
fn late_overflow_or_unrepresentable_supported_motion_never_partially_publish() {
    let mut p = PARAMS;
    p[0] = -f64::MAX;
    let points = [-f64::MAX, 80.0, f64::MAX, 80.0];
    let mut output = [77.0; 4];
    assert_eq!(call(&points, &p, &mut output), BOUND_ERROR);
    assert_eq!(output, [77.0; 4]);
    p = PARAMS;
    p[0] = 0.0;
    p[1] = 0.0;
    p[6] = f64::from_bits(1);
    let mut output = [77.0; 2];
    assert_eq!(call(&[0.0, p[6]], &p, &mut output), BOUND_ERROR);
    assert_eq!(output, [77.0; 2]);
}

#[test]
fn lengths_counts_null_unaligned_overflowing_and_overlapping_pointers_refuse() {
    let points = [50.0, 80.0];
    for index in 0..3 {
        for invalid in [0, 1, usize::MAX] {
            let mut lengths = [2, 11, 2];
            lengths[index] = invalid;
            let mut output = [77.0; 2];
            let status = unsafe { lrt_lower_face_evaluate_v1(points.as_ptr(), lengths[0],
                PARAMS.as_ptr(), lengths[1], 1, output.as_mut_ptr(), lengths[2]) };
            assert_eq!(status, ABI_ERROR);
            assert_eq!(output, [77.0; 2]);
        }
    }
    for count in [0, MAX_POINTS + 1, usize::MAX] {
        let mut output = [77.0; 2];
        let status = unsafe { lrt_lower_face_evaluate_v1(points.as_ptr(), 2,
            PARAMS.as_ptr(), 11, count, output.as_mut_ptr(), 2) };
        assert_eq!(status, ABI_ERROR);
        assert_eq!(output, [77.0; 2]);
    }
    for invalid in [ptr::null(), 1usize as *const f64, (usize::MAX - 7) as *const f64] {
        for index in 0..3 {
            let mut output = [77.0; 2];
            let a = if index == 0 { invalid } else { points.as_ptr() };
            let b = if index == 1 { invalid } else { PARAMS.as_ptr() };
            let out = if index == 2 { invalid as *mut f64 } else { output.as_mut_ptr() };
            let status = unsafe { lrt_lower_face_evaluate_v1(a, 2, b, 11, 1, out, 2) };
            assert_eq!(status, ABI_ERROR);
            assert_eq!(output, [77.0; 2]);
        }
    }
    for offset in [0, 1] {
        let mut storage = [77.0; 16];
        let status = unsafe { lrt_lower_face_evaluate_v1(storage.as_ptr(), 2,
            PARAMS.as_ptr(), 11, 1, storage.as_mut_ptr().add(offset), 2) };
        assert_eq!(status, ABI_ERROR);
        assert_eq!(storage, [77.0; 16]);
        let status = unsafe { lrt_lower_face_evaluate_v1(points.as_ptr(), 2,
            storage.as_ptr(), 11, 1, storage.as_mut_ptr().add(offset), 2) };
        assert_eq!(status, ABI_ERROR);
        assert_eq!(storage, [77.0; 16]);
    }
}

#[test]
fn maximum_batch_is_bounded_and_read_only_inputs_may_overlap() {
    let points = vec![1000.0; MAX_POINTS * 2];
    assert!(run(&points, &PARAMS).iter().all(|v| v.to_bits() == 0));
    let mut output = [77.0; 2];
    let status = unsafe { lrt_lower_face_evaluate_v1(PARAMS.as_ptr(), 2,
        PARAMS.as_ptr(), 11, 1, output.as_mut_ptr(), 2) };
    assert_eq!(status, 0);
    assert!(output.iter().all(|v| v.to_bits() == 0));
}
