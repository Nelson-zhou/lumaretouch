// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN synthetic numeric fixtures. No real-photo quality claim.
use super::*;

fn fixture(amounts: [f64; 3]) -> State {
    let mut support = [0.25, 0.35, 0.65, 0.75, 0.05, 0.15, 0.25, 0.35,
                       0.10, 0.15, 0.25, 0.30, 0.25, 0.40, 0.60, 0.75,
                       0.70, 0.75, 0.85, 0.90, 0.25, 0.40, 0.60, 0.75];
    for i in 0..3 {
        if amounts[i] == 0.0 { support[i*8..i*8+8].fill(0.0); }
    }
    prepare(&[1.0, amounts[0], amounts[1], amounts[2]], &support, 1001.0, 1001.0).unwrap()
}

fn close(a: f64, b: f64, eps: f64) { assert!((a-b).abs() <= eps, "{a} != {b}"); }

#[test]
fn directions_are_crown_height_and_independent_lateral_volume() {
    for amount in [-1.0, -0.3, 0.0, 0.4, 1.0] {
        let s = fixture([amount, amount, amount]);
        let (crown, _) = s.forward(500.0, 180.0);
        close(crown[0], 0.0, 1e-12); close(crown[1], -10.0*amount, 1e-12);
        let (left, _) = s.forward(180.0, 500.0);
        close(left[0], -5.0*amount, 1e-12); close(left[1], 0.0, 1e-12);
        let (right, _) = s.forward(820.0, 500.0);
        close(right[0], 5.0*amount, 1e-12); close(right[1], 0.0, 1e-12);
    }
    let separate = fixture([0.0, 1.0, -1.0]);
    assert!(separate.forward(180.0, 500.0).0[0] < 0.0);
    assert!(separate.forward(820.0, 500.0).0[0] < 0.0);
}

#[test]
fn fixed_face_lower_hair_and_inner_regions_are_not_head_scaling() {
    let s = fixture([1.0, 1.0, 1.0]);
    for (x, y) in [(500.0, 600.0), (500.0, 350.0), (300.0, 500.0), (700.0, 500.0),
                   (180.0, 750.0), (820.0, 800.0), (0.0, 0.0), (1000.0, 1000.0)] {
        assert_eq!(s.forward(x, y), ([0.0, 0.0], 1.0));
        assert_eq!(s.inverse(x, y).unwrap(), ([0.0, 0.0], 1.0));
    }
}

#[test]
fn overlapping_crown_and_side_is_bounded_and_exactly_inverted_off_grid() {
    for amounts in [[1.0, 1.0, 1.0], [-1.0, 1.0, -1.0], [0.7, -0.3, 0.8]] {
        let s = fixture(amounts); s.validate().unwrap();
        let k = s.gradient_bound(); assert!(k <= MAX_GRADIENT);
        for (x, y) in [(275.37, 300.13), (725.17, 325.89), (351.11, 100.29),
                       (180.37, 500.13), (820.71, 450.13), (500.12, 180.17)] {
            let (forward, determinant) = s.forward(x, y);
            let (q_x, q_y) = (x+forward[0], y+forward[1]);
            let (delta, inverse_det) = s.inverse(q_x, q_y).unwrap();
            close(q_x-delta[0], x, RESIDUAL); close(q_y-delta[1], y, RESIDUAL);
            close(inverse_det, 1.0/determinant, 1e-8);
            assert!(determinant >= (1.0-k).powi(2)-1e-12);
            assert!(determinant <= (1.0+k).powi(2)+1e-12);
        }
    }
}

#[test]
fn inverse_analytic_determinant_matches_finite_difference_not_reversed_points() {
    let s = fixture([1.0, -1.0, 1.0]);
    for (x, y) in [(275.37, 300.13), (125.25, 330.75), (725.17, 325.89)] {
        let (_, actual) = s.inverse(x, y).unwrap();
        let e = 1e-3;
        let xp = s.inverse(x+e, y).unwrap().0; let xm = s.inverse(x-e, y).unwrap().0;
        let yp = s.inverse(x, y+e).unwrap().0; let ym = s.inverse(x, y-e).unwrap().0;
        let a = 1.0-(xp[0]-xm[0])/(2.0*e); let b = -(yp[0]-ym[0])/(2.0*e);
        let c = -(xp[1]-xm[1])/(2.0*e); let d = 1.0-(yp[1]-ym[1])/(2.0*e);
        close(actual, a*d-b*c, 1e-6);
    }
}

#[test]
fn neutral_is_exact_and_windows_have_zero_boundary_derivative() {
    let s = fixture([0.0, 0.0, 0.0]);
    assert_eq!(lrt_hair_volume_abi(), 1);
    for (x, y) in [(0.0, 0.0), (1000.0, 1000.0), (135.51, 278.27)] {
        assert_eq!(s.inverse(x, y).unwrap(), ([0.0, 0.0], 1.0));
    }
    assert_eq!(smooth(0.5), (0.5, 1.875));
    for (x, value) in [(10.0, 0.0), (30.0, 1.0), (50.0, 1.0), (70.0, 0.0)] {
        assert_eq!(window(x, &[10.0, 30.0, 50.0, 70.0]), (value, 0.0));
    }
}

#[test]
fn forged_profiles_nonfinite_amounts_and_clipping_are_refused() {
    let good = fixture([1.0, 1.0, 1.0]);
    for value in [f64::NAN, f64::INFINITY, 1.01, -1.01] {
        let mut bad = good; bad.0[3] = value; assert!(bad.validate().is_err());
    }
    let mut bad = good; bad.0[6] = 0.0; assert_eq!(bad.validate(), Err(8));
    let mut bad = good; bad.0[7] = bad.0[6]+1.0; assert_eq!(bad.validate(), Err(6));
    let mut bad = good; bad.0[17] = 750.0; assert!(bad.validate().is_err());
    let mut bad = good; bad.0[3] = 0.0; assert_eq!(bad.validate(), Err(1));
    assert_eq!(good.inverse(-0.001, 250.0), Err(8));
    assert_eq!(good.inverse(250.0, 1000.001), Err(8));
}

#[test]
fn refusal_leaves_all_output_sentinels_and_checks_aliases_and_empty_state() {
    let state = fixture([1.0, 1.0, 1.0]);
    let points = [500.0, 180.0, -1.0, 100.0];
    let mut output = [91.0; 4]; let mut jacobian = [92.0; 2];
    let result = unsafe { lrt_hair_volume_evaluate(state.0.as_ptr(), STATE_LEN,
        points.as_ptr(), 4, 2, output.as_mut_ptr(), 4, jacobian.as_mut_ptr(), 2) };
    assert_eq!(result, 8); assert_eq!(output, [91.0; 4]); assert_eq!(jacobian, [92.0; 2]);
    let alias = unsafe { lrt_hair_volume_describe(state.0.as_ptr(), STATE_LEN,
        state.0.as_ptr() as *mut f64, FACTS_LEN) };
    assert_eq!(alias, 1);
    let mut bad = state; bad.0[0] = 9.0;
    let empty = unsafe { lrt_hair_volume_evaluate(bad.0.as_ptr(), STATE_LEN,
        points.as_ptr(), 0, 0, output.as_mut_ptr(), 0, jacobian.as_mut_ptr(), 0) };
    assert_eq!(empty, 1);
}
