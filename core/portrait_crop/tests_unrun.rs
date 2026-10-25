// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Coordinates are not model or photographic evidence.
use super::*;
const A: [f64; 6] = [500.0, 100.0, 500.0, 700.0, 500.0, 400.0];
const R: [f64; 4] = [1.0, 0.1, 0.6, 0.5];

#[test]
fn version_and_full_frame_neutral() {
    assert_eq!(lrt_portrait_crop_abi(), 1);
    assert_eq!(lrt_portrait_crop_capabilities(), 15);
    assert_eq!(lrt_portrait_crop_result_len(), 20);
    let p = solve(1000, 1000, &A, &R).unwrap();
    assert_eq!(&p[0..4], &[0.0, 0.0, 1000.0, 1000.0]);
    assert_eq!(&p[4..8], &[0.0, 0.0, 1.0, 1.0]);
    assert_eq!(&p[12..20], &[1.0, 0.1, 0.6, 0.5, 0.4, 600.0, 1000.0, 1000.0]);
}

#[test]
fn portrait_landscape_and_singleton_source_boundaries() {
    let p = solve(1200, 1600, &[600.0, 400.0, 600.0, 1000.0, 600.0, 700.0], &[0.75, 0.1, 0.6, 0.5]).unwrap();
    assert_eq!(&p[8..12], &[225.0, 300.0, 975.0, 1300.0]);
    assert_eq!(&p[18..20], &[750.0, 1000.0]);
    let p = solve(1600, 1400, &[800.0, 300.0, 800.0, 700.0, 800.0, 500.0], &[1.5, 0.1, 0.5, 0.5]).unwrap();
    assert_eq!(&p[8..12], &[200.0, 220.0, 1400.0, 1020.0]);
    let p = solve(1, 1, &[0.5, 0.0, 0.5, 1.0, 0.5, 0.5], &[1.0, 0.0, 1.0, 0.5]).unwrap();
    assert_eq!(&p[4..8], &[0.0, 0.0, 1.0, 1.0]);
}

#[test]
fn ties_even_both_parities_and_achieved_aspect() {
    let p = solve(128, 128, &[40.0, 28.5, 40.0, 60.5, 42.5, 44.5], &[1.0, 0.125, 0.5, 0.5]).unwrap();
    assert_eq!(&p[0..4], &[10.5, 20.5, 74.5, 84.5]);
    assert_eq!(&p[8..12], &[10.0, 20.0, 74.0, 84.0]);
    assert_eq!(p[13], 8.5 / 64.0);
    let p = solve(128, 128, &[40.0, 29.5, 40.0, 61.5, 43.5, 45.5], &[1.0, 0.125, 0.5, 0.5]).unwrap();
    assert_eq!(&p[8..12], &[12.0, 22.0, 76.0, 86.0]);
    let p = solve(128, 128, &[40.0, 28.5, 40.0, 60.5, 43.0, 44.5], &[65.0 / 64.0, 0.125, 0.5, 0.5]).unwrap();
    assert_eq!(&p[8..12], &[10.0, 20.0, 76.0, 84.0]);
    assert_eq!(p[12], 66.0 / 64.0);
    assert_ne!(p[12], 65.0 / 64.0);
}

#[test]
fn no_forced_one_pixel_crop_or_rounding_away_the_crown() {
    assert_eq!(solve(100, 100, &[20.25, 20.125, 20.25, 20.375, 20.25, 20.25], &[1.0, 0.0, 1.0, 0.5]), Err(PIXEL_ROUNDING));
    assert_eq!(solve(128, 128, &[64.0, 20.75, 64.0, 52.75, 64.0, 36.75], &[1.0, 0.0, 0.5, 0.5]), Err(PIXEL_ROUNDING));
}

#[test]
fn invalid_and_infeasible_are_distinct() {
    for width in [0, MAX_DIMENSION + 1] { assert_eq!(solve(width, 1000, &A, &R), Err(GEOMETRY_ERROR)); }
    for index in 0..6 {
        let mut a = A; a[index] = f64::NAN;
        assert_eq!(solve(1000, 1000, &a, &R), Err(GEOMETRY_ERROR));
    }
    for index in 0..4 {
        let mut r = R; r[index] = f64::INFINITY;
        assert_eq!(solve(1000, 1000, &A, &r), Err(GEOMETRY_ERROR));
    }
    assert_eq!(solve(1000, 1000, &[500.0, 700.0, 500.0, 100.0, 500.0, 400.0], &R), Err(GEOMETRY_ERROR));
    for r in [[2.0, 0.1, 0.6, 0.5], [1.0, 0.5, 0.6, 0.5], [1.0, 0.1, f64::from_bits(1), 0.5], [1.0, 0.1, 0.6, 0.0]] {
        assert_eq!(solve(1000, 1000, &A, &r), Err(INFEASIBLE));
    }
}

#[test]
fn errors_are_transactional_and_output_cannot_alias_input() {
    let sentinel = [79.25; RESULT_LEN];
    let mut output = sentinel;
    let r = [2.0, 0.1, 0.6, 0.5];
    unsafe {
        assert_eq!(lrt_portrait_crop_plan_v1(1000, 1000, A.as_ptr(), 6, r.as_ptr(), 4, output.as_mut_ptr(), RESULT_LEN), INFEASIBLE);
        assert_eq!(output, sentinel);
        assert_eq!(lrt_portrait_crop_plan_v1(1000, 1000, ptr::null(), 6, R.as_ptr(), 4, output.as_mut_ptr(), RESULT_LEN), ABI_ERROR);
        assert_eq!(lrt_portrait_crop_plan_v1(1000, 1000, A.as_ptr(), 5, R.as_ptr(), 4, output.as_mut_ptr(), RESULT_LEN), ABI_ERROR);
        let p = output.as_mut_ptr();
        assert_eq!(lrt_portrait_crop_plan_v1(1000, 1000, p, 6, R.as_ptr(), 4, p, RESULT_LEN), ABI_ERROR);
    }
    assert_eq!(output, sentinel);
}

#[test]
fn admitted_grid_reencodes_exact_edges_and_preserves_anchors() {
    let a = [256.0, 128.0, 256.0, 256.0, 256.0, 192.0];
    for aspect in [0.5, 0.75, 1.0, 1.5, 2.0] {
        for fraction in [0.25, 0.5, 0.75, 1.0] {
            for headroom in [0.0, 0.125, 0.25] {
                for horizontal in [0.25, 0.5, 0.75] {
                    match solve(512, 512, &a, &[aspect, headroom, fraction, horizontal]) {
                        Ok(p) => {
                            let bounds = [p[8], p[9], p[10], p[11]];
                            for index in 0..4 { assert_eq!(pixel_round(512.0 * p[4 + index]), p[8 + index]); }
                            assert!(a.chunks_exact(2).all(|point| inside(point[0], point[1], &bounds)));
                        }
                        Err(code) => assert!(code == INFEASIBLE || code == PIXEL_ROUNDING),
                    }
                }
            }
        }
    }
}
