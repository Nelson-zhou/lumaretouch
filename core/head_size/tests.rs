// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. These are isolated synthetic numeric fixtures, not real
//! anatomy, product defaults, visual acceptance or evidence of a passing build.
use super::*;

fn state(amount: f64) -> State {
    State([20.0, 470.0, 670.0, 1120.0, 20.0, 470.0, 670.0, 1120.0,
           570.0, 570.0, amount * GAIN, 1201.0, 1601.0])
}

fn observed_fixture() -> ([f64; POINTS_LEN], [f64; SUPPORT_LEN]) {
    let mut points = [0.0; POINTS_LEN];
    for i in 0..33 {
        points[i * 5] = (540.0 + (i % 4) as f64 * 20.0) / 1200.0;
        points[i * 5 + 1] = (530.0 + (i % 5) as f64 * 15.0) / 1600.0;
        points[i * 5 + 3] = 1.0;
        points[i * 5 + 4] = 1.0;
    }
    points[11 * 5] = 440.0 / 1200.0;
    points[12 * 5] = 700.0 / 1200.0;
    points[11 * 5 + 1] = 1200.0 / 1600.0;
    points[12 * 5 + 1] = 1200.0 / 1600.0;
    let support = [470.0 / 1200.0, 470.0 / 1600.0, 670.0 / 1200.0, 670.0 / 1600.0,
                   20.0 / 1200.0, 20.0 / 1600.0, 1120.0 / 1200.0, 1120.0 / 1600.0,
                   570.0 / 1200.0, 570.0 / 1600.0];
    (points, support)
}

fn close(actual: f64, expected: f64, tolerance: f64) {
    assert!((actual - expected).abs() <= tolerance,
            "actual={actual}, expected={expected}, tolerance={tolerance}");
}

fn evaluate(s: &State, input: &[f64], output: &mut [f64], jac: &mut [f64]) -> i32 {
    unsafe {
        lrt_head_size_evaluate(s.0.as_ptr(), STATE_LEN, input.as_ptr(), input.len(),
                              input.len() / 2, output.as_mut_ptr(), output.len(),
                              jac.as_mut_ptr(), jac.len())
    }
}

#[test]
fn exact_abi_recipe_support_state_and_facts_layout() {
    assert_eq!(lrt_head_size_abi(), 1);
    let (points, support) = observed_fixture();
    let prepared = prepare(&points, &[1.0, 1.0], &support, 1201.0, 1601.0).unwrap();
    for i in 0..STATE_LEN { close(prepared.0[i], state(1.0).0[i], 1e-12); }
    let f = prepared.facts();
    assert_eq!(f[..4], [20.0, 20.0, 1120.0, 1120.0]);
    assert_eq!(f[4..8], [470.0, 470.0, 670.0, 670.0]);
    assert_eq!(f[8..10], [570.0, 570.0]);
    close(f[10], 0.92, 1e-15);
    close(f[11], GAIN * 550.0_f64.hypot(550.0), 1e-12);
    close(f[12], 0.44666666666666666, 1e-14);
    close(f[13], (1.0 - f[12]) * (1.0 - f[12]), 1e-14);
    assert_eq!(&f[14..], &[RESIDUAL_TOLERANCE, 64.0]);
}

#[test]
fn complete_plateau_including_hair_has_one_uniform_scale_and_explicit_pivot() {
    for amount in [0.0, 0.125, 0.5, 1.0] {
        let s = state(amount);
        s.validate().unwrap();
        // Corners/upper edge stand for independently reviewed hair coverage,
        // not hair points hallucinated from the 11 Body33 facial observations.
        for (x, y) in [(470.0, 470.0), (670.0, 470.0), (570.0, 480.0),
                       (480.0, 660.0), (660.0, 660.0), (570.0, 570.0)] {
            let (d, determinant) = s.forward(x, y);
            close(d[0], -GAIN * amount * (x - 570.0), 1e-12);
            close(d[1], -GAIN * amount * (y - 570.0), 1e-12);
            close(determinant, (1.0 - amount * GAIN).powi(2), 1e-12);
            let (inverse_delta, inverse_det) = s.inverse(x + d[0], y + d[1]).unwrap();
            close(x + d[0] - inverse_delta[0], x, RESIDUAL_TOLERANCE);
            close(y + d[1] - inverse_delta[1], y, RESIDUAL_TOLERANCE);
            close(inverse_det, 1.0 / determinant, 1e-9);
        }
    }
    let mut marked = state(1.0);
    marked.0[8] = 590.0;
    marked.0[9] = 550.0;
    // The conservative bound can veto a displaced pivot at full strength.
    marked.0[10] = 0.04;
    marked.validate().unwrap();
    assert_eq!(marked.forward(590.0, 550.0).0, [0.0, 0.0]);
    assert_ne!(marked.forward(570.0, 570.0).0, [0.0, 0.0]);
}

#[test]
fn source_displacement_sign_and_inverse_determinant_are_not_forward_sampling() {
    let s = state(1.0);
    let (delta, jac) = s.inverse(616.0, 524.0).unwrap();
    close(delta[0], -4.0, 1e-8);
    close(delta[1], 4.0, 1e-8);
    close(616.0 - delta[0], 620.0, 1e-8);
    close(524.0 - delta[1], 520.0, 1e-8);
    close(jac, 1.0 / (0.92 * 0.92), 1e-12);
}

#[test]
fn neutral_outside_transition_and_shoulders_are_exact_identity() {
    for amount in [0.0, 1.0] {
        let s = state(amount);
        for (x, y) in [(0.0, 0.0), (1200.0, 1600.0), (20.0, 570.0),
                       (1120.0, 570.0), (570.0, 20.0), (570.0, 1120.0),
                       (440.0, 1200.0), (700.0, 1200.0)] {
            let (delta, jac) = s.inverse(x, y).unwrap();
            assert!(delta.iter().all(|v| v.to_bits() == 0));
            assert_eq!(jac, 1.0);
        }
    }
    for (x, y) in [(570.0, 570.0), (245.2, 351.7), (615.5, 524.3)] {
        let (delta, jac) = state(0.0).inverse(x, y).unwrap();
        assert!(delta.iter().all(|v| v.to_bits() == 0));
        assert_eq!(jac, 1.0);
    }
}

#[test]
fn quintic_windows_have_zero_slope_at_support_and_plateau_edges() {
    assert_eq!(smooth(0.0), (0.0, 0.0));
    assert_eq!(smooth(1.0), (1.0, 0.0));
    assert_eq!(smooth(0.5), (0.5, 1.875));
    for (x, want) in [(20.0, 0.0), (470.0, 1.0), (670.0, 1.0), (1120.0, 0.0)] {
        assert_eq!(window(x, 20.0, 470.0, 670.0, 1120.0), (want, 0.0));
    }
    for t in [1e-9, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0 - 1e-9] {
        let (w, d) = smooth(t);
        let (v, e) = smooth(1.0 - t);
        close(w + v, 1.0, 1e-14);
        close(d, e, 1e-14);
        assert!((0.0..=1.0).contains(&w));
        assert!((0.0..=1.875).contains(&d));
    }
}

#[test]
fn off_grid_inverse_residual_and_analytic_area_agree_with_numeric_differentials() {
    let s = state(1.0);
    for (qx, qy) in [(100.37, 245.21), (452.73, 1050.13), (950.37, 251.81),
                     (570.37, 570.21), (1119.9, 470.1), (20.0001, 570.0)] {
        let (d, inverse_det) = s.inverse(qx, qy).unwrap();
        let px = qx - d[0];
        let py = qy - d[1];
        let (forward, _) = s.forward(px, py);
        assert!((px + forward[0] - qx).hypot(py + forward[1] - qy) <= RESIDUAL_TOLERANCE);
        let eps = 1e-3;
        let (xp, _) = s.inverse(qx + eps, qy).unwrap();
        let (xm, _) = s.inverse(qx - eps, qy).unwrap();
        let (yp, _) = s.inverse(qx, qy + eps).unwrap();
        let (ym, _) = s.inverse(qx, qy - eps).unwrap();
        let a = 1.0 - (xp[0] - xm[0]) / (2.0 * eps);
        let b = -(yp[0] - ym[0]) / (2.0 * eps);
        let c = -(xp[1] - xm[1]) / (2.0 * eps);
        let d = 1.0 - (yp[1] - ym[1]) / (2.0 * eps);
        close(inverse_det, a * d - b * c, 1e-6);
        assert!(inverse_det >= 1.0 / (1.0 + MAX_GRADIENT).powi(2));
        assert!(inverse_det <= 1.0 / (1.0 - MAX_GRADIENT).powi(2));
    }
}

#[test]
fn no_pose_centroid_hairline_or_unused_limb_inference() {
    let (points, support) = observed_fixture();
    let original = prepare(&points, &[1.0, 0.5], &support, 1201.0, 1601.0).unwrap();
    let mut altered = points;
    for i in 0..11 { altered[i * 5] = 600.0 / 1200.0; }
    for i in 13..33 {
        altered[i * 5] = -4.0;
        altered[i * 5 + 3] = 0.0;
        altered[i * 5 + 4] = 0.0;
    }
    let result = prepare(&altered, &[1.0, 0.5], &support, 1201.0, 1601.0).unwrap();
    assert_eq!(result.0, original.0);
    let mut marked = support;
    marked[8] = 580.0 / 1200.0;
    let changed = prepare(&points, &[1.0, 0.5], &marked, 1201.0, 1601.0).unwrap();
    close(changed.0[8], 580.0, 1e-12);
    assert_ne!(changed.0, original.0);
}

#[test]
fn observations_and_shoulders_are_gates_even_for_neutral_recipe() {
    let (points, support) = observed_fixture();
    for i in 0..13 {
        for field in [3, 4] {
            let mut bad = points;
            bad[i * 5 + field] = 0.799;
            assert!(matches!(prepare(&bad, &[1.0, 0.0], &support, 1201.0, 1601.0), Err(4)));
        }
    }
    let mut bad = points;
    bad[0] = support[0];
    assert!(matches!(prepare(&bad, &[1.0, 0.0], &support, 1201.0, 1601.0), Err(6)));
    for (index, value) in [(11 * 5 + 1, support[7]), (12 * 5 + 1, 1300.0 / 1600.0),
                            (12 * 5, 460.0 / 1200.0), (12 * 5 + 2, 0.1)] {
        let mut bad = points;
        bad[index] = value;
        assert!(matches!(prepare(&bad, &[1.0, 0.0], &support, 1201.0, 1601.0), Err(5)));
    }
}

#[test]
fn requested_strength_is_rejected_never_silently_attenuated() {
    let (points, mut support) = observed_fixture();
    support[4] = 420.0 / 1200.0; // Narrow left margin makes full strength unsafe.
    assert!(matches!(prepare(&points, &[1.0, 1.0], &support, 1201.0, 1601.0), Err(6)));
    let low = prepare(&points, &[1.0, 0.01], &support, 1201.0, 1601.0).unwrap();
    assert_eq!(low.0[10], 0.01 * GAIN);
    let mut output = [77.0; STATE_LEN];
    let recipe = [1.0, 1.0];
    let code = unsafe { lrt_head_size_prepare(points.as_ptr(), points.len(), recipe.as_ptr(), 2,
        support.as_ptr(), support.len(), 1201.0, 1601.0, output.as_mut_ptr(), output.len()) };
    assert_eq!(code, 6);
    assert_eq!(output, [77.0; STATE_LEN]);
}

#[test]
fn all_forged_state_components_and_budgets_are_revalidated() {
    for index in 0..STATE_LEN {
        for invalid in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let mut bad = state(0.0);
            bad.0[index] = invalid;
            assert!(read_state(&bad.0).is_err());
        }
    }
    for (index, invalid) in [(0, 0.5), (3, 1200.0), (4, 0.5), (7, 1600.0),
                             (1, 660.0), (5, 660.0), (0, 460.0), (7, 680.0),
                             (8, 470.0), (9, 670.0), (10, -0.001), (10, 0.08001),
                             (11, 1201.5), (12, 1_000_001.0)] {
        let mut bad = state(0.0);
        bad.0[index] = invalid;
        assert!(read_state(&bad.0).is_err(), "forged index={index}, value={invalid}");
    }
    let mut too_large = state(1.0);
    for index in 0..10 { too_large.0[index] *= 10.0; }
    too_large.0[11] *= 10.0;
    too_large.0[12] *= 10.0;
    assert!(too_large.gradient_bound() < MAX_GRADIENT);
    assert!(matches!(too_large.validate(), Err(6))); // D > 128, not L.
}

#[test]
fn recipe_dimensions_and_all_input_nonfinites_are_rejected() {
    let (points, support) = observed_fixture();
    for recipe in [[0.0, 0.0], [2.0, 0.0], [f64::NAN, 0.0], [1.0, -0.1],
                   [1.0, 1.01], [1.0, f64::NAN], [1.0, f64::INFINITY]] {
        assert!(prepare(&points, &recipe, &support, 1201.0, 1601.0).is_err());
    }
    for (w, h) in [(1201.5, 1601.0), (1201.0, f64::INFINITY), (1.0, 1601.0)] {
        assert!(prepare(&points, &[1.0, 0.0], &support, w, h).is_err());
    }
    for index in 0..POINTS_LEN {
        let mut bad = points;
        bad[index] = f64::NAN;
        assert!(prepare(&bad, &[1.0, 0.0], &support, 1201.0, 1601.0).is_err());
    }
    for index in 0..SUPPORT_LEN {
        let mut bad = support;
        bad[index] = f64::INFINITY;
        assert!(prepare(&points, &[1.0, 0.0], &bad, 1201.0, 1601.0).is_err());
    }
}

#[test]
fn evaluate_failures_after_valid_queries_leave_both_outputs_untouched() {
    for (last, code) in [([f64::NAN, 570.0], 1), ([-0.001, 570.0], 8),
                          ([1200.001, 570.0], 8), ([570.0, 1600.001], 8)] {
        let points = [616.0, 524.0, last[0], last[1]];
        let mut output = [77.0; 4];
        let mut jac = [88.0; 2];
        assert_eq!(evaluate(&state(1.0), &points, &mut output, &mut jac), code);
        assert_eq!(output, [77.0; 4]);
        assert_eq!(jac, [88.0; 2]);
    }
    let points = [616.0, 524.0];
    let mut output = [77.0; 2];
    let mut jac = [88.0; 1];
    assert_eq!(evaluate(&state(1.0), &points, &mut output, &mut jac), 0);
    close(output[0], -4.0, 1e-8);
    close(output[1], 4.0, 1e-8);
    close(jac[0], 1.0 / (0.92 * 0.92), 1e-12);
}

#[test]
fn buffer_lengths_null_alignment_aliases_and_arithmetic_are_checked_before_access() {
    let s = state(1.0);
    let mut buffer = [77.0; 32];
    assert_eq!(unsafe { lrt_head_size_describe(s.0.as_ptr(), STATE_LEN - 1,
        buffer.as_mut_ptr(), FACTS_LEN) }, 1);
    assert_eq!(unsafe { lrt_head_size_describe(std::ptr::null(), STATE_LEN,
        buffer.as_mut_ptr(), FACTS_LEN) }, 1);
    assert_eq!(unsafe { lrt_head_size_describe(1usize as *const f64, STATE_LEN,
        buffer.as_mut_ptr(), FACTS_LEN) }, 1);
    assert_eq!(unsafe { lrt_head_size_describe(buffer.as_ptr(), STATE_LEN,
        buffer.as_mut_ptr(), FACTS_LEN) }, 1);
    assert_eq!(buffer, [77.0; 32]);
    assert!(!disjoint_buffers(&[(8, usize::MAX)]));
    assert!(!disjoint_buffers(&[(usize::MAX - 7, 2)]));
    let mut output = [77.0; 2];
    let mut jac = [88.0; 1];
    let xy = [616.0, 524.0];
    assert_eq!(unsafe { lrt_head_size_evaluate(s.0.as_ptr(), STATE_LEN, xy.as_ptr(), 2,
        usize::MAX, output.as_mut_ptr(), 2, jac.as_mut_ptr(), 1) }, 1);
    assert_eq!(unsafe { lrt_head_size_evaluate(s.0.as_ptr(), STATE_LEN, xy.as_ptr(), 2,
        1, output.as_mut_ptr(), 2, output.as_mut_ptr(), 1) }, 1);
    assert_eq!(output, [77.0; 2]);
    assert_eq!(jac, [88.0; 1]);
}

#[test]
fn empty_bands_are_allowed_but_do_not_bypass_state_validation() {
    let mut output = [];
    let mut jac = [];
    assert_eq!(evaluate(&state(1.0), &[], &mut output, &mut jac), 0);
    let mut bad = state(0.0);
    bad.0[8] = bad.0[1];
    assert_eq!(evaluate(&bad, &[], &mut output, &mut jac), 6);
}
