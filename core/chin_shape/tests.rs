// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Fixtures are not evidence of numerical or image acceptance.
use super::*;

const PARAMS: [f64; 11] = [50.0, 60.0, 1.0, 0.0, 0.0, 1.0,
                          40.0, 25.0, 50.0, 1.0, 1.0];
fn call(points: &[f64], params: &[f64; 11], output: &mut [f64]) -> i32 {
    unsafe { lrt_chin_shape_evaluate_v1(points.as_ptr(), points.len(), params.as_ptr(), 11,
                                       points.len() / 2, output.as_mut_ptr(), output.len()) }
}
fn run(points: &[f64], params: &[f64; 11]) -> Vec<f64> {
    let mut output = vec![77.0; points.len()];
    assert_eq!(call(points, params, &mut output), 0);
    output
}
fn close(actual: f64, expected: f64) {
    assert!((actual - expected).abs() <= 2.0e-11 * expected.abs().max(1.0),
            "actual={actual}, expected={expected}");
}
// Independent forward-only fixture oracle, never an application inverse.
fn s(z: f64) -> f64 { z * z * z * (10.0 - 15.0 * z + 6.0 * z * z) }
fn v(t: f64) -> f64 {
    if t <= 0.0 || t >= 1.5 { 0.0 }
    else if t < 1.0 { s(t) } else { s((1.5 - t) / 0.5) }
}
fn forward(u: f64, t: f64, p: &[f64; 11]) -> f64 {
    let r = u.abs();
    let l = if r <= p[7] { 1.0 } else if r >= p[8] { 0.0 }
            else { s((p[8] - r) / (p[8] - p[7])) };
    let amount = if u > 0.0 { p[9] } else { p[10] };
    u - (((GAIN * u) * amount) * v(t)) * l
}

#[test]
fn signed_width_direction_fixed_tip_and_vertical_coordinate() {
    assert_eq!(lrt_chin_shape_abi(), 1);
    for amount in [-1.0, -0.25, 0.25, 1.0] {
        let mut p = PARAMS;
        p[9] = amount;
        p[10] = amount;
        for u in [-20.0, 20.0] {
            for t in [0.5, 1.0, 1.25] {
                let qu = forward(u, t, &p);
                let point = [p[0] + qu, p[1] + t * p[6]];
                let output = run(&point, &p);
                close(output[0], qu - u);
                close(point[0] - output[0], p[0] + u);
                assert_eq!(output[1].to_bits(), 0);
                assert_eq!(qu.is_sign_positive(), u.is_sign_positive());
                assert!((u.abs() - qu.abs()) * amount > 0.0);
            }
        }
        assert!(run(&[p[0], p[1] + p[6]], &p).iter().all(|x| x.to_bits() == 0));
    }
}

#[test]
fn genuine_inverse_not_forward_at_destination_or_negated_forward() {
    for amount in [-1.0, -0.3, 0.3, 1.0] {
        let mut p = PARAMS;
        p[9] = amount;
        p[10] = amount;
        for u in [-37.5, -20.0, 20.0, 37.5] {
            let t = 0.7;
            let q = forward(u, t, &p);
            let output = run(&[p[0] + q, p[1] + p[6] * t], &p);
            let naive = forward(q, t, &p) - q;
            close(output[0], q - u);
            assert!((output[0] - naive).abs() > 1.0e-7);
            assert!((output[0] + naive).abs() > 1.0e-7);
        }
    }
}

#[test]
fn independent_sides_near_center_continuity_cusp_and_no_crossing() {
    let mut p = PARAMS;
    p[0] = 0.0;
    p[1] = 0.0;
    p[9] = 1.0;
    p[10] = -1.0;
    for epsilon in [1.0e-3, 1.0e-6, 1.0e-9, 1.0e-12] {
        let left = forward(epsilon, 1.0, &p);
        let right = forward(-epsilon, 1.0, &p);
        assert!(left > 0.0 && right < 0.0);
        let bound = (1.08 + 16.0 * f64::EPSILON) * epsilon;
        assert!(left.abs() <= bound && right.abs() <= bound);
        close(left / epsilon, 0.92);
        close(right / -epsilon, 1.08);
        assert!((left / epsilon - right / -epsilon).abs() > 0.15);
        let output = run(&[left, p[6], right, p[6]], &p);
        close(left - output[0], epsilon);
        close(right - output[2], -epsilon);
        assert!(left - output[0] > 0.0 && right - output[2] < 0.0);
    }
    assert_eq!(forward(0.0, 1.0, &p), 0.0);
    assert!(run(&[0.0, p[6]], &p).iter().all(|x| x.to_bits() == 0));
    p[9] = 0.0;
    assert!(run(&[20.0, p[6]], &p).iter().all(|x| x.to_bits() == 0));
    assert_ne!(run(&[-20.0, p[6]], &p)[0], 0.0);
}

#[test]
fn exhaustive_authored_grid_roundtrip_monotonicity_and_horizontal_bound() {
    for left in [-1.0, 0.0, 0.6, 1.0] {
        for right in [-1.0, 0.0, 0.6, 1.0] {
            let mut p = PARAMS;
            p[9] = left;
            p[10] = right;
            let g = validate(&[], &p).unwrap();
            for t in [0.2, 0.7, 1.0, 1.25] {
                let mut points = Vec::new();
                let mut expected = Vec::new();
                let mut previous = f64::NEG_INFINITY;
                for index in 0..=256 {
                    let u = -55.0 + 110.0 * index as f64 / 256.0;
                    let qu = forward(u, t, &p);
                    assert!(qu > previous);
                    previous = qu;
                    if u != 0.0 { assert_eq!(qu > 0.0, u > 0.0); }
                    points.extend_from_slice(&[p[0] + qu, p[1] + t * p[6]]);
                    expected.extend_from_slice(&[qu - u, 0.0]);
                    let b = lateral(u.abs(), &g).1;
                    assert!((-3.75..=1.0).contains(&b));
                    let amount = if u > 0.0 { left } else { right };
                    let derivative = 1.0 - GAIN * amount * v(t) * b;
                    assert!(derivative >= MIN_FORWARD_DERIVATIVE - 1.0e-14);
                    assert!(derivative <= MAX_FORWARD_DERIVATIVE + 1.0e-14);
                }
                for (actual, expected) in run(&points, &p).iter().zip(expected.iter()) {
                    close(*actual, *expected);
                }
            }
        }
    }
}

#[test]
fn exact_positive_zero_neutral_upper_center_lateral_and_neck_edges() {
    let points = [50.0, 100.0, 70.0, 60.0, 70.0, 59.0, 70.0, 120.0,
                  70.0, 121.0, 0.0, 100.0, 100.0, 100.0, 101.0, 100.0];
    assert!(run(&points, &PARAMS).iter().all(|x| x.to_bits() == 0));
    let mut p = PARAMS;
    p[9] = -0.0;
    p[10] = 0.0;
    assert!(run(&[75.0, 90.0, 25.0, 90.0], &p).iter().all(|x| x.to_bits() == 0));
    assert_eq!(vertical(1.0), 1.0);
    for z in [0.0, 1.0] { assert_eq!(smoothstep_derivative(z), 0.0); }
    close(vertical(0.5), 0.5);
    close(vertical(1.25), 0.5);
}

#[test]
fn roll_translation_uniform_scaling_and_both_handednesses() {
    let points = [65.0, 80.0, 85.0, 103.0, 15.0, 103.0];
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
            close(rotated[0], 3.0 * p[2] * delta[0]);
            close(rotated[1], 3.0 * p[3] * delta[0]);
            close(rotated[0] * p[4] + rotated[1] * p[5], 0.0);
        }
    }
}

#[test]
fn frame_roundoff_is_canonicalized_without_repairing_skew() {
    let mut p = PARAMS;
    p[2..6].copy_from_slice(&[1.0 + 1.0e-12, 0.0, 1.0e-12, 1.0 - 1.0e-12]);
    let g = validate(&[], &p).unwrap();
    assert_eq!((g.rx, g.ry, g.dx, g.dy), (1.0, 0.0, -0.0, 1.0));
    assert_eq!(run(&[65.0, 80.0], &p), run(&[65.0, 80.0], &PARAMS));
}

#[test]
fn tiny_amount_retains_physical_delta_without_source_subtraction() {
    let mut p = PARAMS;
    p[0] = 0.0;
    p[1] = 0.0;
    p[7] = 1.0e300;
    p[8] = 2.0 * p[7];
    for amount in [1.0e-20, -1.0e-20, f64::from_bits(1), -f64::from_bits(1)] {
        p[9] = amount;
        let point = [0.5e300, 0.5 * p[6]];
        let result = run(&point, &p);
        let expected = -((GAIN * point[0]) * amount) * 0.5;
        assert_ne!(result[0], 0.0);
        assert!((result[0] - expected).abs() <= expected.abs() * 1.0e-13);
        assert_eq!(point[0] - result[0], point[0]);
    }
}

#[test]
fn all_invalid_values_geometry_and_late_failures_leave_all_output_untouched() {
    for index in 0..11 {
        for bad in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let mut p = PARAMS;
            p[9] = 0.0;
            p[10] = 0.0;
            p[index] = bad;
            let mut output = [77.0; 2];
            assert_eq!(call(&[65.0, 80.0], &p, &mut output), VALUE_ERROR);
            assert_eq!(output, [77.0; 2]);
        }
    }
    for (index, bad, status) in [(9, -1.01, VALUE_ERROR), (10, 1.01, VALUE_ERROR),
        (2, 0.0, FRAME_ERROR), (2, 1.000001, FRAME_ERROR), (4, 1.0e-8, FRAME_ERROR),
        (6, 0.0, FRAME_ERROR), (6, -1.0, FRAME_ERROR), (7, 0.0, BOUND_ERROR),
        (7, 50.0, BOUND_ERROR), (8, 24.0, BOUND_ERROR), (8, 50.0001, BOUND_ERROR)] {
        let mut p = PARAMS;
        p[index] = bad;
        let mut output = [77.0; 2];
        assert_eq!(call(&[65.0, 80.0], &p, &mut output), status);
        assert_eq!(output, [77.0; 2]);
    }
    for point in [[f64::NAN, 80.0], [65.0, f64::INFINITY], [65.0, f64::NEG_INFINITY]] {
        let mut output = [77.0; 2];
        assert_eq!(call(&point, &PARAMS, &mut output), VALUE_ERROR);
        assert_eq!(output, [77.0; 2]);
    }
    let mut p = PARAMS;
    p[0] = -f64::MAX;
    let mut output = [77.0; 4];
    assert_eq!(call(&[-f64::MAX, 80.0, f64::MAX, 80.0], &p, &mut output), BOUND_ERROR);
    assert_eq!(output, [77.0; 4]);
    p = PARAMS;
    p[9] = f64::from_bits(1);
    assert_eq!(call(&[50.0, 80.0, 51.0, 80.0], &p, &mut output), BOUND_ERROR);
    assert_eq!(output, [77.0; 4]);
}

#[test]
fn tiny_supported_weights_are_nonzero_or_explicit_atomic_refusals() {
    let mut p = PARAMS;
    p[0] = 0.0;
    p[1] = 0.0;
    p[6] = 1.0;
    // Tiny positive V is representable, and remains an edit despite losing
    // effective movement when subtracting the returned delta from q.
    let point = [1.0, 1.0e-50];
    let output = run(&point, &p);
    assert!(output[0] < 0.0 && output[0].is_finite());
    assert_eq!(point[0] - output[0], point[0]);
    // V itself underflows although t is positive: refuse, never neutralize.
    let mut destination = [77.0; 4];
    assert_eq!(call(&[0.0, 1.0, 1.0, 1.0e-200], &p, &mut destination), BOUND_ERROR);
    assert_eq!(destination, [77.0; 4]);
    // t underflows before evaluating V: still refuse supported nonzero intent.
    p[6] = 1.0e300;
    assert_eq!(call(&[0.0, 1.0, 1.0, 1.0e-100], &p, &mut destination), BOUND_ERROR);
    assert_eq!(destination, [77.0; 4]);
    // Just inside the lateral edge must not be rounded/clamped to zero L.
    p[6] = 1.0;
    let u = f64::from_bits(p[8].to_bits() - 1);
    let edge = run(&[u, 1.0], &p);
    assert!(edge[0] < 0.0);
    assert_eq!(u - edge[0], u);
    assert!(run(&[p[8], 1.0], &p).iter().all(|x| x.to_bits() == 0));
}

#[test]
fn abi_lengths_counts_pointers_and_alias_refuse_before_writing() {
    let points = [65.0, 80.0];
    for index in 0..3 {
        for bad in [0, 1, usize::MAX] {
            let mut lengths = [2, 11, 2];
            lengths[index] = bad;
            let mut output = [77.0; 2];
            let status = unsafe { lrt_chin_shape_evaluate_v1(points.as_ptr(), lengths[0],
                PARAMS.as_ptr(), lengths[1], 1, output.as_mut_ptr(), lengths[2]) };
            assert_eq!(status, ABI_ERROR);
            assert_eq!(output, [77.0; 2]);
        }
    }
    for count in [0, MAX_POINTS + 1, usize::MAX] {
        let mut output = [77.0; 2];
        let status = unsafe { lrt_chin_shape_evaluate_v1(points.as_ptr(), 2,
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
            let status = unsafe { lrt_chin_shape_evaluate_v1(a, 2, b, 11, 1, out, 2) };
            assert_eq!(status, ABI_ERROR);
            assert_eq!(output, [77.0; 2]);
        }
    }
    for offset in [0, 1] {
        let mut storage = [77.0; 16];
        let status = unsafe { lrt_chin_shape_evaluate_v1(storage.as_ptr(), 2,
            PARAMS.as_ptr(), 11, 1, storage.as_mut_ptr().add(offset), 2) };
        assert_eq!(status, ABI_ERROR);
        assert_eq!(storage, [77.0; 16]);
        let status = unsafe { lrt_chin_shape_evaluate_v1(points.as_ptr(), 2,
            storage.as_ptr(), 11, 1, storage.as_mut_ptr().add(offset), 2) };
        assert_eq!(status, ABI_ERROR);
        assert_eq!(storage, [77.0; 16]);
    }
}

#[test]
fn bounded_maximum_batch_and_readonly_input_overlap() {
    let points = vec![1000.0; MAX_POINTS * 2];
    assert!(run(&points, &PARAMS).iter().all(|v| v.to_bits() == 0));
    let mut output = [77.0; 2];
    let status = unsafe { lrt_chin_shape_evaluate_v1(PARAMS.as_ptr(), 2,
        PARAMS.as_ptr(), 11, 1, output.as_mut_ptr(), 2) };
    assert_eq!(status, 0);
    assert!(output.iter().all(|v| v.to_bits() == 0));
}
