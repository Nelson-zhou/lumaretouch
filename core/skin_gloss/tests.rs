// SPDX-License-Identifier: GPL-3.0-or-later
//! Authored source-only acceptance fixtures. ALL UNRUN, including these helpers.
use super::*;

const SIDE: usize = 41;
const RADIUS: usize = 7;
fn scene() -> (Vec<f32>, Vec<f32>) {
    let mut image = Vec::new();
    for y in 0..SIDE {
        for x in 0..SIDE {
            let extra = if (16..25).contains(&x) && (16..25).contains(&y) { 0.15 } else { 0.0 };
            image.extend([0.32 + extra, 0.18 + extra, 0.10 + extra].map(encode));
        }
    }
    (image, vec![1.0; SIDE * SIDE])
}
fn apply(current: &[f32], reference: &[f32], coverage: &[f32], amount: f32) -> Vec<f32> {
    let mut out = vec![f32::NAN; current.len()];
    apply_into(current, reference, coverage, SIDE, SIDE, amount, RADIUS, &mut out, || false).unwrap();
    out
}
fn bits(a: &[f32], b: &[f32]) -> bool {
    a.iter().zip(b).all(|(x, y)| x.to_bits() == y.to_bits()) && a.len() == b.len()
}

#[test]
fn signed_neutral_and_zero_coverage_are_bit_exact() {
    let (mut source, coverage) = scene();
    source[0] = -0.0;
    for amount in [0.0, -0.0] { assert!(bits(&source, &apply(&source, &source, &coverage, amount))); }
    for amount in [-1.0, 1.0] {
        assert!(bits(&source, &apply(&source, &source, &vec![0.0; SIDE * SIDE], amount)));
    }
}

#[test]
fn broad_neutral_additive_lobe_is_selective_and_signed() {
    let (source, coverage) = scene();
    let low = apply(&source, &source, &coverage, -1.0);
    let high = apply(&source, &source, &coverage, 1.0);
    let center = 3 * (20 * SIDE + 20);
    assert!(low[center] < source[center] && high[center] > source[center]);
    for i in 0..SIDE * SIDE {
        let x = i % SIDE;
        let y = i / SIDE;
        for c in 0..3 {
            let j = 3 * i + c;
            assert!(unit(low[j]) && unit(high[j]));
            assert!(low[j] <= source[j] && high[j] >= source[j]);
            if !(16..25).contains(&x) || !(16..25).contains(&y) {
                assert_eq!(source[j].to_bits(), low[j].to_bits());
                assert_eq!(source[j].to_bits(), high[j].to_bits());
            }
        }
    }
}

#[test]
fn achromatic_and_flat_chromatic_fields_refuse_highlights() {
    for colour in [[0.30, 0.30, 0.30], [0.32, 0.18, 0.10]] {
        let source: Vec<_> = (0..SIDE * SIDE).flat_map(|_| colour.map(encode)).collect();
        let coverage = vec![1.0; SIDE * SIDE];
        for amount in [-1.0, 1.0] { assert!(bits(&source, &apply(&source, &source, &coverage, amount))); }
    }
}

#[test]
fn brightness_only_diffuse_shading_does_not_become_gloss() {
    let mut source = Vec::new();
    for _y in 0..SIDE {
        for x in 0..SIDE {
            let scale = if x < 21 { 1.0 } else { 1.6 };
            source.extend([0.32 * scale, 0.18 * scale, 0.10 * scale].map(encode));
        }
    }
    let coverage = vec![1.0; SIDE * SIDE];
    for amount in [-1.0, 1.0] { assert!(bits(&source, &apply(&source, &source, &coverage, amount))); }
}

#[test]
fn isolated_bright_pore_and_inconsistent_coloured_patch_are_refused() {
    let coverage = vec![1.0; SIDE * SIDE];
    for coloured in [false, true] {
        let mut source = Vec::new();
        for y in 0..SIDE {
            for x in 0..SIDE {
                let added = if coloured && (16..25).contains(&x) && (16..25).contains(&y) {
                    [0.02, 0.13, 0.30]
                } else if !coloured && x == 20 && y == 20 { [0.15; 3] } else { [0.0; 3] };
                source.extend(std::array::from_fn::<_, 3, _>(|c| encode([0.32, 0.18, 0.10][c] + added[c])));
            }
        }
        for amount in [-1.0, 1.0] { assert!(bits(&source, &apply(&source, &source, &coverage, amount))); }
    }
}

#[test]
fn clipped_source_and_unsupported_pixels_are_unchanged() {
    let (mut source, mut coverage) = scene();
    let center = 20 * SIDE + 20;
    source[3 * center] = 1.0;
    coverage[20 * SIDE + 19] = 0.0;
    for amount in [-1.0, 1.0] {
        let out = apply(&source, &source, &coverage, amount);
        for i in [center, 20 * SIDE + 19] {
            assert!(bits(&source[3*i..3*i+3], &out[3*i..3*i+3]));
        }
    }
}

#[test]
fn other_person_or_background_outside_support_cannot_change_evidence() {
    let (source, mut coverage) = scene();
    let mut changed = source.clone();
    for y in 0..SIDE {
        for x in 0..SIDE {
            if x < 10 || x >= 31 || y < 10 || y >= 31 {
                let i = y * SIDE + x;
                coverage[i] = 0.0;
                changed[3*i..3*i+3].copy_from_slice(&[0.99, 0.01, 0.75]);
            }
        }
    }
    // Keep current fixed, change only out-of-coverage ORIGINAL reference.
    assert!(bits(&apply(&source, &source, &coverage, 1.0), &apply(&source, &changed, &coverage, 1.0)));
}

#[test]
fn source_evidence_does_not_depend_on_current_colour_or_amount_sign() {
    let (reference, coverage) = scene();
    let a: Vec<_> = (0..SIDE * SIDE).flat_map(|_| [0.50, 0.40, 0.30].map(encode)).collect();
    let b: Vec<_> = (0..SIDE * SIDE).flat_map(|_| [0.52, 0.43, 0.35].map(encode)).collect();
    let plus_a = apply(&a, &reference, &coverage, 0.25);
    let plus_b = apply(&b, &reference, &coverage, 0.25);
    let minus_a = apply(&a, &reference, &coverage, -0.25);
    for i in 0..a.len() {
        let delta_a = decode(plus_a[i] as f64) - decode(a[i] as f64);
        let delta_b = decode(plus_b[i] as f64) - decode(b[i] as f64);
        let delta_minus = decode(minus_a[i] as f64) - decode(a[i] as f64);
        assert!((delta_a - delta_b).abs() < 2e-7);
        assert!((delta_a + delta_minus).abs() < 2e-7);
    }
    let center = 3 * (20 * SIDE + 20);
    assert!(plus_a[center] > a[center]);
}

#[test]
fn neutral_delta_preserves_opponent_detail_and_bounds_saturation_growth() {
    let current = [0.80, 0.20, 0.01].map(encode);
    let out = adjusted(current, -1.0).unwrap();
    let before = current.map(|v| decode(v as f64));
    let after = out.map(|v| decode(v as f64));
    for c in 0..3 {
        assert!(after[c] >= before[c] * 0.75 - 2e-7);
        assert!(((after[c] - after[0]) - (before[c] - before[0])).abs() < 2e-7);
    }
    assert!(norm(opponent(after)) / mean(after) <= 1.25 * norm(opponent(before)) / mean(before) + 2e-6);
    for value in [[0.0, -0.0, 0.0], [1.0; 3]] {
        assert!(bits(&value, &adjusted(value, 1.0).unwrap()));
        assert!(bits(&value, &adjusted(value, -1.0).unwrap()));
    }
}

#[test]
fn current_black_white_endpoints_survive_nonclipped_highlight_reference() {
    let (reference, coverage) = scene();
    for value in [[0.0, -0.0, 0.0], [1.0; 3]] {
        let current: Vec<_> = (0..SIDE * SIDE).flat_map(|_| value).collect();
        for amount in [-1.0, 1.0] {
            assert!(bits(&current, &apply(&current, &reference, &coverage, amount)));
        }
    }
}

#[test]
fn real_two_radius_halo_matches_full_domain_interior_with_tolerance() {
    let (source, coverage) = scene();
    let full = apply(&source, &source, &coverage, 0.7);
    // Core [18,23), halo14 on each side, real crop [4,37), no resampling.
    let start = 4;
    let width = 33;
    let mut crop = Vec::new();
    let mut mask = Vec::new();
    for y in start..start + width {
        crop.extend_from_slice(&source[3*(y*SIDE+start)..3*(y*SIDE+start+width)]);
        mask.extend_from_slice(&coverage[y*SIDE+start..y*SIDE+start+width]);
    }
    let mut result = vec![0.0; crop.len()];
    apply_into(&crop, &crop, &mask, width, width, 0.7, RADIUS, &mut result, || false).unwrap();
    for y in 18..23 {
        for x in 18..23 {
            for c in 0..3 {
                assert!((result[3*((y-start)*width+x-start)+c] - full[3*(y*SIDE+x)+c]).abs() < 2e-6);
            }
        }
    }
}

#[test]
fn strict_invalid_sdr_and_settings_even_when_neutral() {
    let (mut source, coverage) = scene();
    let mut out = vec![0.0; source.len()];
    for bad in [f32::NAN, f32::INFINITY, -0.01, 1.01] {
        source[0] = bad;
        assert_eq!(apply_into(&source, &source, &coverage, SIDE, SIDE, 0.0, RADIUS, &mut out, || false), Err(PIXEL_ERROR));
    }
    source[0] = 0.2;
    for radius in [0, 1, MAX_RADIUS + 1] {
        assert_eq!(apply_into(&source, &source, &coverage, SIDE, SIDE, 0.0, radius, &mut out, || false), Err(SETTINGS_ERROR));
    }
    assert_eq!(apply_into(&source, &source, &coverage, SIDE, SIDE, 1.01, RADIUS, &mut out, || false), Err(SETTINGS_ERROR));
    assert_eq!(apply_into(&source, &source, &coverage, SIDE, SIDE, 1.0, RADIUS, &mut out, || true), Err(CANCELLED));
    assert_eq!(admit(65536, 65536), Err(RESOURCE_ERROR));
}

#[test]
fn ffi_matches_safe_entry_and_refuses_aliases_lengths_and_nulls() {
    let (source, coverage) = scene();
    let safe = apply(&source, &source, &coverage, 0.5);
    let mut ffi = vec![0.0; source.len()];
    unsafe {
        assert_eq!(lrt_skin_gloss_abi(), 1);
        assert_eq!(lrt_skin_gloss_apply_v1(source.as_ptr(), source.len(), source.as_ptr(), source.len(),
            coverage.as_ptr(), coverage.len(), SIDE, SIDE, 0.5, RADIUS, ffi.as_mut_ptr(), ffi.len(), None, std::ptr::null_mut()), 0);
        assert!(bits(&safe, &ffi));
        assert_eq!(lrt_skin_gloss_apply_v1(source.as_ptr(), source.len(), source.as_ptr(), source.len(),
            coverage.as_ptr(), coverage.len(), SIDE, SIDE, 0.5, RADIUS, source.as_ptr() as *mut f32, source.len(), None, std::ptr::null_mut()), ABI_ERROR);
        assert_eq!(lrt_skin_gloss_apply_v1(std::ptr::null(), source.len(), source.as_ptr(), source.len(),
            coverage.as_ptr(), coverage.len(), SIDE, SIDE, 0.5, RADIUS, ffi.as_mut_ptr(), ffi.len(), None, std::ptr::null_mut()), ABI_ERROR);
        assert_eq!(lrt_skin_gloss_apply_v1(source.as_ptr(), source.len() - 1, source.as_ptr(), source.len(),
            coverage.as_ptr(), coverage.len(), SIDE, SIDE, 0.5, RADIUS, ffi.as_mut_ptr(), ffi.len(), None, std::ptr::null_mut()), ABI_ERROR);
    }
}
