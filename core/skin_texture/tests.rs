// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. These source fixtures do not establish numeric/photo acceptance.
use super::*;

const SIDE: usize = 97;
const RADIUS: usize = 8;
fn scene() -> (Vec<f32>, Vec<f32>) {
    let mut source = Vec::new();
    for y in 0..SIDE {
        for x in 0..SIDE {
            let modulation = (0.035*(std::f64::consts::TAU*x as f64/6.0).sin()
                + 0.060*(std::f64::consts::TAU*y as f64/20.0).sin()).exp();
            source.extend([0.28, 0.16, 0.09].map(|v| encode(v*modulation)));
        }
    }
    (source, vec![1.0; SIDE*SIDE])
}
fn render(current: &[f32], reference: &[f32], coverage: &[f32], texture: f32, clarity: f32) -> Vec<f32> {
    let mut output = vec![f32::NAN; current.len()];
    apply_into(current, reference, coverage, SIDE, SIDE, texture, clarity, RADIUS,
        &mut output, || false).unwrap();
    output
}
fn bits(a: &[f32], b: &[f32]) -> bool {
    a.len() == b.len() && a.iter().zip(b).all(|(x,y)| x.to_bits() == y.to_bits())
}
fn log_change(current: &[f32], result: &[f32], i: usize) -> f64 {
    (luminance(result, i) / luminance(current, i)).ln()
}

#[test]
fn neutral_zero_support_and_current_endpoints_are_bit_exact() {
    let (mut source, mask) = scene();
    source[0] = -0.0;
    for texture in [0.0, -0.0] {
        for clarity in [0.0, -0.0] { assert!(bits(&source, &render(&source, &source, &mask, texture, clarity))); }
    }
    for (texture, clarity) in [(-1.0, 0.0), (1.0, 1.0)] {
        assert!(bits(&source, &render(&source, &source, &vec![0.0; SIDE*SIDE], texture, clarity)));
        for endpoint in [[0.0, -0.0, 0.0], [1.0; 3]] {
            let current: Vec<_> = (0..SIDE*SIDE).flat_map(|_| endpoint).collect();
            assert!(bits(&current, &render(&current, &source, &mask, texture, clarity)));
        }
    }
}

#[test]
fn flat_original_is_exact_copy_even_when_current_has_structure() {
    let (current, mask) = scene();
    for colour in [[0.30, 0.30, 0.30], [0.28, 0.16, 0.09]] {
        let reference: Vec<_> = (0..SIDE*SIDE).flat_map(|_| colour.map(encode)).collect();
        assert!(bits(&current, &render(&current, &reference, &mask, -1.0, 1.0)));
        assert!(bits(&current, &render(&current, &reference, &mask, 1.0, 1.0)));
    }
}

#[test]
fn signed_texture_and_positive_fine_sharpening_are_distinct_source_bands() {
    let (source, mask) = scene();
    let low = render(&source, &source, &mask, -1.0, 0.0);
    let high = render(&source, &source, &mask, 1.0, 0.0);
    let sharp = render(&source, &source, &mask, 0.0, 1.0);
    assert!(!bits(&source, &low) && !bits(&source, &high) && !bits(&source, &sharp));
    assert!(!bits(&high, &sharp));
    let log_y: Vec<_> = (0..SIDE*SIDE).map(|i| luminance(&source, i).ln()).collect();
    let fine = guided_base(&log_y, &mask, SIDE, SIDE, RADIUS/4, 0.04_f64.powi(2), &mut || false).unwrap();
    let coarse = guided_base(&log_y, &mask, SIDE, SIDE, RADIUS, 0.11_f64.powi(2), &mut || false).unwrap();
    let mut texture_correlation = 0.0;
    let mut sharp_correlation = 0.0;
    for i in 0..SIDE*SIDE {
        if fine[i].is_finite() && coarse[i].is_finite() {
            texture_correlation += log_change(&source, &high, i) * (fine[i] - coarse[i]);
            sharp_correlation += log_change(&source, &sharp, i) * (log_y[i] - fine[i]);
        }
        assert!((log_change(&source, &high, i) + log_change(&source, &low, i)).abs() < 2e-6);
        for result in [&low, &high, &sharp] { assert!(result[3*i..3*i+3].iter().copied().all(unit)); }
    }
    assert!(texture_correlation > 0.0 && sharp_correlation > 0.0);
}

#[test]
fn normalized_support_excludes_all_background_and_other_person_values() {
    let (current, mut mask) = scene();
    let reference = current.clone();
    let mut altered = reference.clone();
    for y in 0..SIDE {
        for x in 0..SIDE {
            if x < 18 || x >= 79 || y < 18 || y >= 79 || (x > 38 && x < 44) {
                let i = y*SIDE+x;
                mask[i] = 0.0;
                altered[3*i..3*i+3].copy_from_slice(&[0.99, 0.01, 0.79]);
            }
        }
    }
    let a = render(&current, &reference, &mask, 1.0, 1.0);
    let b = render(&current, &altered, &mask, 1.0, 1.0);
    assert!(bits(&a, &b));
    for i in 0..SIDE*SIDE {
        if mask[i] == 0.0 { assert!(bits(&current[3*i..3*i+3], &a[3*i..3*i+3])); }
    }
}

#[test]
fn invalid_coefficient_domains_do_not_become_synthetic_observations() {
    let log_y = vec![-1.5; SIDE*SIDE];
    let mut mask = vec![0.0; SIDE*SIDE];
    mask[(SIDE/2)*SIDE+SIDE/2] = 1.0;
    let base = guided_base(&log_y, &mask, SIDE, SIDE, RADIUS, 0.0121, &mut || false).unwrap();
    assert!(base.iter().all(|value| value.is_nan()));
    let (source, _) = scene();
    assert!(bits(&source, &render(&source, &source, &mask, 1.0, 1.0)));
}

#[test]
fn uniform_permission_scales_log_delta_not_neighborhood_brightness() {
    let (source, full_mask) = scene();
    let full = render(&source, &source, &full_mask, 0.7, 0.0);
    let half = render(&source, &source, &vec![0.5; SIDE*SIDE], 0.7, 0.0);
    for i in 0..SIDE*SIDE {
        assert!((log_change(&source, &half, i) - 0.5*log_change(&source, &full, i)).abs() < 2e-6);
    }
}

#[test]
fn source_owned_measurements_apply_same_gain_to_different_current_intermediates() {
    let (reference, mask) = scene();
    let a: Vec<_> = (0..SIDE*SIDE).flat_map(|_| [0.30, 0.18, 0.10].map(encode)).collect();
    let b: Vec<_> = (0..SIDE*SIDE).flat_map(|_| [0.40, 0.25, 0.16].map(encode)).collect();
    let result_a = render(&a, &reference, &mask, 0.6, 0.8);
    let result_b = render(&b, &reference, &mask, 0.6, 0.8);
    assert!(!bits(&a, &result_a));
    for i in 0..SIDE*SIDE {
        assert!((log_change(&a, &result_a, i) - log_change(&b, &result_b, i)).abs() < 2e-6);
    }
    // Altering a remote current pixel cannot alter any other output pixel.
    let mut changed_current = a.clone();
    let center = (SIDE/2)*SIDE+SIDE/2;
    changed_current[3*center..3*center+3].copy_from_slice(&[0.90, 0.60, 0.10]);
    let changed_output = render(&changed_current, &reference, &mask, 0.6, 0.8);
    for i in 0..SIDE*SIDE {
        if i != center { assert!(bits(&result_a[3*i..3*i+3], &changed_output[3*i..3*i+3])); }
    }
}

#[test]
fn high_frequency_checker_and_hard_edges_are_conservatively_gated() {
    let mask = vec![1.0; SIDE*SIDE];
    let mut checker = Vec::new();
    let mut edge = Vec::new();
    for y in 0..SIDE {
        for x in 0..SIDE {
            let factor = if (x+y)%2 == 0 { 0.008_f64.exp() } else { (-0.008_f64).exp() };
            checker.extend([0.28, 0.16, 0.09].map(|v| encode(v*factor)));
            let factor = if x < SIDE/2 { 1.0 } else { 0.5_f64.exp() };
            edge.extend([0.28, 0.16, 0.09].map(|v| encode(v*factor)));
        }
    }
    // This intentionally rejects genuine Nyquist texture too, not only noise.
    assert!(bits(&checker, &render(&checker, &checker, &mask, 0.0, 1.0)));
    let result = render(&edge, &edge, &mask, 1.0, 1.0);
    for y in 1..SIDE-1 {
        for x in [SIDE/2-1, SIDE/2] {
            let i = y*SIDE+x;
            assert!(bits(&edge[3*i..3*i+3], &result[3*i..3*i+3]));
        }
    }
}

#[test]
fn common_gain_preserves_linear_channel_ratios_and_restrains_gamut() {
    for current in [[0.98, 0.30, 0.01].map(encode), [0.30, 0.18, 0.10].map(encode)] {
        for delta in [-0.08, 0.08, 2.0] {
            let result = adjusted(current, delta).unwrap();
            let before = current.map(|v| decode(f64::from(v)));
            let after = result.map(|v| decode(f64::from(v)));
            let gain = after[0] / before[0];
            for c in 0..3 {
                assert!(unit(result[c]));
                assert!((after[c] - gain*before[c]).abs() < 2e-7);
            }
        }
    }
    let saturated = [1.0, 0.35, 0.02];
    assert!(bits(&saturated, &adjusted(saturated, 0.08).unwrap()));
}

#[test]
fn true_two_radius_halo_matches_full_domain_without_padding() {
    let (source, mask) = scene();
    let full = render(&source, &source, &mask, -0.6, 0.8);
    let start = 29;
    let size = 39; // Core45..52 has a real16-pixel halo on every side.
    let mut crop = Vec::new();
    let mut crop_mask = Vec::new();
    for y in start..start+size {
        crop.extend_from_slice(&source[3*(y*SIDE+start)..3*(y*SIDE+start+size)]);
        crop_mask.extend_from_slice(&mask[y*SIDE+start..y*SIDE+start+size]);
    }
    let mut output = vec![0.0; crop.len()];
    apply_into(&crop, &crop, &crop_mask, size, size, -0.6, 0.8, RADIUS, &mut output, || false).unwrap();
    for y in 45..52 {
        for x in 45..52 {
            for c in 0..3 {
                assert!((output[3*((y-start)*size+x-start)+c] - full[3*(y*SIDE+x)+c]).abs() < 2e-6);
            }
        }
    }
}

#[test]
fn invalid_inputs_controls_resources_and_staged_cancellation_refuse() {
    let (mut source, mask) = scene();
    let mut output = vec![0.0; source.len()];
    for invalid in [f32::NAN, f32::INFINITY, -0.01, 1.01] {
        source[0] = invalid;
        assert_eq!(apply_into(&source, &source, &mask, SIDE, SIDE, 0.0, 0.0, RADIUS,
            &mut output, || false), Err(PIXEL_ERROR));
    }
    source[0] = 0.3;
    for (texture, clarity, radius) in [(1.01, 0.0, 4), (-1.01, 0.0, 4), (0.0, -0.01, 4),
        (0.0, 1.01, 4), (f32::NAN, 0.0, 4), (0.0, f32::INFINITY, 4), (0.0, 0.0, 3), (0.0, 0.0, 257)] {
        assert_eq!(apply_into(&source, &source, &mask, SIDE, SIDE, texture, clarity, radius,
            &mut output, || false), Err(SETTINGS_ERROR));
    }
    for cutoff in [0, 50, 500, 2000] {
        let mut polls = 0;
        assert_eq!(apply_into(&source, &source, &mask, SIDE, SIDE, 1.0, 1.0, RADIUS,
            &mut output, || { polls += 1; polls > cutoff }), Err(CANCELLED));
    }
    assert_eq!(admit(0, 1), Err(ABI_ERROR));
    assert_eq!(admit(65536, 65536), Err(RESOURCE_ERROR));
    assert_eq!(NATIVE_SCRATCH_BYTES_PER_PIXEL, 8+8+32+24);
}

extern "C" fn cancel_now(_: *mut c_void) -> i32 { 1 }
#[test]
fn ffi_matches_safe_entry_and_rejects_alias_null_misalignment_and_short_spans() {
    let (source, mask) = scene();
    let safe = render(&source, &source, &mask, 0.5, 0.8);
    let mut output = vec![0.0; source.len()];
    let output_len = output.len();
    unsafe {
        let invoke = |source_ptr, source_len, output_ptr, cancel| lrt_skin_texture_apply_v1(
            source_ptr, source_len, source.as_ptr(), source.len(), mask.as_ptr(), mask.len(),
            SIDE, SIDE, 0.5, 0.8, RADIUS, output_ptr, output_len, cancel, std::ptr::null_mut());
        assert_eq!(lrt_skin_texture_abi(), 1);
        assert_eq!(invoke(source.as_ptr(), source.len(), output.as_mut_ptr(), None), 0);
        assert!(bits(&safe, &output));
        assert_eq!(invoke(source.as_ptr(), source.len(), source.as_ptr() as *mut f32, None), ABI_ERROR);
        assert_eq!(invoke(std::ptr::null(), source.len(), output.as_mut_ptr(), None), ABI_ERROR);
        assert_eq!(invoke(source.as_ptr(), source.len()-1, output.as_mut_ptr(), None), ABI_ERROR);
        let misaligned = (source.as_ptr() as *const u8).add(1) as *const f32;
        assert_eq!(invoke(misaligned, source.len(), output.as_mut_ptr(), None), ABI_ERROR);
        assert_eq!(invoke(source.as_ptr(), source.len(), output.as_mut_ptr(), Some(cancel_now)), CANCELLED);
    }
}
