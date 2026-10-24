// SPDX-License-Identifier: GPL-3.0-or-later
//! Authored numerical and ABI acceptance intentions. ALL UNRUN.
use super::*;

const SIDE: usize = 33;
const RADIUS: usize = 9;
fn scene() -> (Vec<f32>, Vec<f32>, Vec<f32>) {
    let base = [0.42, 0.30, 0.19];
    let mut source = Vec::new();
    let mut target = vec![0.0; SIDE * SIDE];
    let mut reference = vec![0.0; SIDE * SIDE];
    for y in 0..SIDE {
        for x in 0..SIDE {
            let i = y * SIDE + x;
            let factor = if (9..24).contains(&x) && (16..19).contains(&y) {
                target[i] = if y == 16 { 0.75 } else { 1.0 };
                0.25 + 0.025 * (x % 4) as f64
            } else { 1.0 };
            if (5..29).contains(&x) && (9..14).contains(&y) { reference[i] = 1.0; }
            source.extend(base.map(|v| encode(v * factor)));
        }
    }
    (source, target, reference)
}
fn apply(source: &[f32], target: &[f32], reference: &[f32], amount: f32) -> Vec<f32> {
    let mut out = vec![f32::NAN; source.len()];
    apply_into(source, target, reference, SIDE, SIDE, amount, RADIUS, &mut out, || false).unwrap();
    out
}
fn bits(a: &[f32], b: &[f32]) -> bool {
    a.len() == b.len() && a.iter().zip(b).all(|(x, y)| x.to_bits() == y.to_bits())
}

#[test]
fn neutral_signed_zero_and_zero_coverage_are_exact() {
    let (mut source, target, reference) = scene();
    source[0] = -0.0;
    for amount in [0.0, -0.0] {
        assert!(bits(&source, &apply(&source, &target, &reference, amount)));
    }
    for amount in [-1.0, 1.0] {
        assert!(bits(&source, &apply(&source, &vec![0.0; SIDE * SIDE], &reference, amount)));
    }
}

#[test]
fn existing_dark_contrast_has_correct_signed_direction_and_protected_pixels_unchanged() {
    let (source, target, reference) = scene();
    let deep = apply(&source, &target, &reference, 1.0);
    let soft = apply(&source, &target, &reference, -1.0);
    let mut changed = 0;
    for i in 0..SIDE * SIDE {
        for c in 0..3 {
            let j = 3 * i + c;
            assert!(unit(deep[j]) && unit(soft[j]));
            assert!(deep[j] <= source[j] && soft[j] >= source[j]);
            if target[i] == 0.0 {
                assert_eq!(deep[j].to_bits(), source[j].to_bits());
                assert_eq!(soft[j].to_bits(), source[j].to_bits());
            } else if deep[j] < source[j] && soft[j] > source[j] { changed += 1; }
        }
    }
    assert!(changed > 100);
}

#[test]
fn black_equal_bright_and_deadzone_source_pixels_are_exact() {
    let (mut source, target, reference) = scene();
    let baseline = [0.42, 0.30, 0.19];
    let positions = [17 * SIDE + 10, 17 * SIDE + 11, 17 * SIDE + 12, 17 * SIDE + 13];
    for (i, rgb) in positions.into_iter().zip([
        [0.0, -0.0, 0.0], baseline.map(encode), [1.0; 3], baseline.map(|v| encode(v * 0.98)),
    ]) { source[3*i..3*i+3].copy_from_slice(&rgb); }
    for amount in [-1.0, 1.0] {
        let out = apply(&source, &target, &reference, amount);
        for i in positions { assert!(bits(&source[3*i..3*i+3], &out[3*i..3*i+3])); }
    }
}

#[test]
fn flat_achromatic_or_chromatic_source_does_not_invent_brows() {
    let (_, target, reference) = scene();
    for colour in [[0.40, 0.40, 0.40], [0.42, 0.30, 0.19]] {
        let source: Vec<_> = (0..SIDE * SIDE).flat_map(|_| colour.map(encode)).collect();
        for amount in [-1.0, 1.0] { assert!(bits(&source, &apply(&source, &target, &reference, amount))); }
    }
}

#[test]
fn achromatic_dark_source_is_measured_without_hue_or_skin_colour_assumption() {
    let (mut source, target, reference) = scene();
    for i in 0..SIDE * SIDE {
        let value = if target[i] > 0.0 { 0.10 } else { 0.40 };
        source[3*i..3*i+3].copy_from_slice(&[encode(value); 3]);
    }
    let out = apply(&source, &target, &reference, 1.0);
    let i = 17 * SIDE + 15;
    assert!(out[3*i] < source[3*i]);
    assert_eq!(out[3*i], out[3*i+1]);
    assert_eq!(out[3*i], out[3*i+2]);
}

#[test]
fn linear_chromatic_ratios_are_preserved_with_one_gamut_feasible_scalar() {
    for source in [[0.07, 0.04, 0.02], [0.99, 0.002, 0.001]] {
        let encoded = source.map(encode);
        for amount in [-1.0, 1.0] {
            let out = adjusted(encoded, 0.9, 1.0, amount).unwrap();
            let before = encoded.map(|v| decode(v as f64));
            let after = out.map(|v| decode(v as f64));
            let gain = after[0] / before[0];
            for c in 0..3 {
                assert!(unit(out[c]));
                assert!((after[c] - before[c] * gain).abs() < 2e-7);
            }
        }
    }
    // A clipped channel cannot be lifted without changing chromaticity.
    let saturated = [1.0, encode(0.002), encode(0.001)];
    assert!(bits(&saturated, &adjusted(saturated, 0.9, 1.0, -1.0).unwrap()));
}

#[test]
fn fixed_reference_and_coverage_keep_tonal_order_and_contrast_under_suppression() {
    // This is not a promise across different support/coverage or reference fields.
    for amount in [-1.0, -0.5, 0.5, 1.0] {
        let mut last = 0.0;
        for n in 1..1000 {
            let y = n as f64 / 1000.0;
            let source = [encode(y); 3];
            let out = adjusted(source, 0.75, 0.8, amount).unwrap();
            let next = decode(out[0] as f64);
            assert!(next >= last);
            if amount < 0.0 && y < 0.75 { assert!(next < 0.75 + 2e-7); }
            last = next;
        }
    }
}

#[test]
fn continuous_float_and_rgb16_low_bits_are_not_quantized_to_rgb8() {
    let a = [10_000.0_f32 / 65_535.0; 3];
    let b = [10_001.0_f32 / 65_535.0; 3];
    assert_eq!((a[0] * 255.0) as u8, (b[0] * 255.0) as u8);
    for amount in [-1.0, 1.0] {
        let aa = adjusted(a, 0.4, 1.0, amount).unwrap();
        let bb = adjusted(b, 0.4, 1.0, amount).unwrap();
        assert!(aa[0] < bb[0]);
        assert_ne!(aa[0].to_bits(), bb[0].to_bits());
    }
}

#[test]
fn outside_target_and_reference_rgb_cannot_influence_target_result() {
    let (source, target, reference) = scene();
    let mut changed = source.clone();
    for i in 0..SIDE * SIDE {
        if target[i] == 0.0 && reference[i] == 0.0 {
            changed[3*i..3*i+3].copy_from_slice(&[0.99, 0.01, 0.85]);
        }
    }
    let a = apply(&source, &target, &reference, 0.7);
    let b = apply(&changed, &target, &reference, 0.7);
    for i in 0..SIDE * SIDE {
        if target[i] > 0.0 { assert!(bits(&a[3*i..3*i+3], &b[3*i..3*i+3])); }
    }
}

#[test]
fn true_crop_containing_all_reference_and_target_support_matches_full_grid() {
    let (source, target, reference) = scene();
    let full = apply(&source, &target, &reference, -0.7);
    let (x0, y0, width, height) = (2, 5, 29, 18);
    let mut rgb = Vec::new();
    let mut mask = Vec::new();
    let mut skin = Vec::new();
    for y in y0..y0 + height {
        rgb.extend_from_slice(&source[3*(y*SIDE+x0)..3*(y*SIDE+x0+width)]);
        mask.extend_from_slice(&target[y*SIDE+x0..y*SIDE+x0+width]);
        skin.extend_from_slice(&reference[y*SIDE+x0..y*SIDE+x0+width]);
    }
    let mut out = vec![0.0; rgb.len()];
    apply_into(&rgb, &mask, &skin, width, height, -0.7, RADIUS, &mut out, || false).unwrap();
    for y in 16..19 {
        for x in 9..24 {
            for c in 0..3 {
                assert!((out[3*((y-y0)*width+x-x0)+c] - full[3*(y*SIDE+x)+c]).abs() < 2e-6);
            }
        }
    }
}

#[test]
fn missing_partial_or_heterogeneous_reference_refuses_whole_side_atomically() {
    let (source, target, reference) = scene();
    for mut bad in [vec![0.0; SIDE * SIDE], reference.clone()] {
        if bad.iter().any(|v| *v > 0.0) {
            // A remote target has no local reference even though other targets do.
            bad.fill(0.0);
            for x in 5..8 { bad[10 * SIDE + x] = 1.0; }
        }
        let mut out = vec![0.123; source.len()];
        let before = out.clone();
        assert_eq!(apply_into(&source, &target, &bad, SIDE, SIDE, 1.0, RADIUS, &mut out, || false), Err(REFERENCE_ERROR));
        assert!(bits(&before, &out));
    }
    let mut inconsistent = source.clone();
    for i in 0..SIDE * SIDE {
        if reference[i] > 0.0 {
            inconsistent[3*i..3*i+3].copy_from_slice(&[if i % 2 == 0 { 0.1 } else { 0.95 }; 3]);
        }
    }
    let mut out = vec![0.123; source.len()];
    let before = out.clone();
    assert_eq!(apply_into(&inconsistent, &target, &reference, SIDE, SIDE, 1.0, RADIUS, &mut out, || false), Err(REFERENCE_ERROR));
    assert!(bits(&before, &out));
}

#[test]
fn target_reference_overlap_is_rejected_even_neutral() {
    let (source, target, mut reference) = scene();
    reference[17 * SIDE + 10] = 0.01;
    let mut out = vec![0.123; source.len()];
    let before = out.clone();
    assert_eq!(apply_into(&source, &target, &reference, SIDE, SIDE, 0.0, RADIUS, &mut out, || false), Err(PIXEL_ERROR));
    assert!(bits(&before, &out));
}

#[test]
fn finite_inputs_settings_lengths_and_resource_caps_are_strict() {
    let (source, target, reference) = scene();
    for bad in [f32::NAN, f32::INFINITY, -0.01, 1.01] {
        let mut corrupted = source.clone();
        corrupted[0] = bad;
        let mut out = vec![0.123; source.len()];
        let before = out.clone();
        assert_eq!(apply_into(&corrupted, &target, &reference, SIDE, SIDE, 0.0, RADIUS, &mut out, || false), Err(PIXEL_ERROR));
        assert!(bits(&before, &out));
    }
    let mut out = vec![0.123; source.len()];
    for radius in [0, 1, MAX_RADIUS + 1] {
        assert_eq!(apply_into(&source, &target, &reference, SIDE, SIDE, 0.0, radius, &mut out, || false), Err(SETTINGS_ERROR));
    }
    for amount in [f32::NAN, f32::INFINITY, -1.01, 1.01] {
        assert_eq!(apply_into(&source, &target, &reference, SIDE, SIDE, amount, RADIUS, &mut out, || false), Err(SETTINGS_ERROR));
    }
    assert_eq!(apply_into(&source[..source.len()-1], &target, &reference, SIDE, SIDE, 0.0, RADIUS, &mut out, || false), Err(ABI_ERROR));
    assert_eq!(admit(0, 3), Err(ABI_ERROR));
    assert_eq!(admit(65_536, 65_536), Err(RESOURCE_ERROR));
    assert_eq!(admit(6000, 6000), Err(RESOURCE_ERROR));
}

#[test]
fn early_and_midwork_cancellation_never_publish_partial_output() {
    let (source, target, reference) = scene();
    for limit in [0, 10, 50, 100] {
        let mut polls = 0;
        let mut out = vec![0.123; source.len()];
        let before = out.clone();
        let result = apply_into(&source, &target, &reference, SIDE, SIDE, 1.0, RADIUS, &mut out, || {
            polls += 1;
            polls > limit
        });
        assert_eq!(result, Err(CANCELLED));
        assert!(bits(&before, &out));
    }
}

#[test]
fn ffi_matches_safe_entry_and_rejects_output_alias_null_and_length() {
    let (source, target, reference) = scene();
    let safe = apply(&source, &target, &reference, 0.6);
    let mut output = vec![0.123; source.len()];
    unsafe {
        assert_eq!(lrt_brow_enhance_abi(), 1);
        assert_eq!(lrt_brow_enhance_apply_v1(source.as_ptr(), source.len(), target.as_ptr(), target.len(),
            reference.as_ptr(), reference.len(), SIDE, SIDE, 0.6, RADIUS, output.as_mut_ptr(), output.len(), None, std::ptr::null_mut()), 0);
        assert!(bits(&safe, &output));
        assert_eq!(lrt_brow_enhance_apply_v1(source.as_ptr(), source.len(), target.as_ptr(), target.len(),
            reference.as_ptr(), reference.len(), SIDE, SIDE, 0.6, RADIUS, source.as_ptr() as *mut f32, source.len(), None, std::ptr::null_mut()), ABI_ERROR);
        assert_eq!(lrt_brow_enhance_apply_v1(std::ptr::null(), source.len(), target.as_ptr(), target.len(),
            reference.as_ptr(), reference.len(), SIDE, SIDE, 0.6, RADIUS, output.as_mut_ptr(), output.len(), None, std::ptr::null_mut()), ABI_ERROR);
        assert_eq!(lrt_brow_enhance_apply_v1(source.as_ptr(), source.len(), target.as_ptr(), target.len()-1,
            reference.as_ptr(), reference.len(), SIDE, SIDE, 0.6, RADIUS, output.as_mut_ptr(), output.len(), None, std::ptr::null_mut()), ABI_ERROR);
    }
}
