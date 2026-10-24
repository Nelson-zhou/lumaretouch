// SPDX-License-Identifier: GPL-3.0-or-later
//! Authored numerical/ABI fixtures. Entire file UNRUN; no quality validation.
use super::*;

const SIDE: usize = 41;
const BASE: Rgb = [0.34, 0.11, 0.07];
fn scene<F: Fn(usize, usize) -> Rgb>(pixel: F) -> Vec<f32> {
    let mut image = Vec::new();
    for y in 0..SIDE {
        for x in 0..SIDE { image.extend(pixel(x, y).map(encode)); }
    }
    image
}
fn furrow() -> Vec<f32> {
    scene(|x, _| BASE.map(|v| if x == 20 { v * 0.82 } else { v }))
}
fn execute(source: &[f32], mask: &[f32], amount: f32, axis: [f32; 2], radius: usize) -> Vec<f32> {
    let mut out = vec![f32::NAN; source.len()];
    apply_into(source, mask, SIDE, SIDE, amount, axis, radius, &mut out, || false).unwrap();
    out
}
fn apply(source: &[f32], mask: &[f32], amount: f32) -> Vec<f32> {
    execute(source, mask, amount, [1.0, 0.0], 1)
}
fn bits(a: &[f32], b: &[f32]) -> bool {
    a.len() == b.len() && a.iter().zip(b).all(|(x, y)| x.to_bits() == y.to_bits())
}
fn pixel(source: &[f32], x: usize, y: usize) -> Rgb {
    let i = 3 * (y * SIDE + x);
    [source[i], source[i+1], source[i+2]]
}

#[test]
fn exact_neutral_zero_support_endpoints_and_low_bits() {
    let mut source = furrow();
    source[0] = -0.0;
    source[1] = 12345.0 / 65535.0;
    source[2] = 12346.0 / 65535.0;
    for amount in [0.0, -0.0] {
        assert!(bits(&source, &apply(&source, &vec![1.0; SIDE*SIDE], amount)));
    }
    assert!(bits(&source, &apply(&source, &vec![0.0; SIDE*SIDE], 1.0)));
    for colour in [[0.0, -0.0, 0.0], [1.0; 3]] {
        let image: Vec<_> = (0..SIDE*SIDE).flat_map(|_| colour).collect();
        assert!(bits(&image, &apply(&image, &vec![1.0; SIDE*SIDE], 1.0)));
    }
}

#[test]
fn chromatic_common_gain_furrow_is_lifted_but_not_replaced() {
    let source = furrow();
    let result = apply(&source, &vec![1.0; SIDE*SIDE], 1.0);
    let before = pixel(&source, 20, 20).map(decode);
    let after = pixel(&result, 20, 20).map(decode);
    let residual = luminance(BASE) - luminance(before);
    let lift = luminance(after) - luminance(before);
    assert!(lift > 0.0 && lift <= MAX_LIFT_FRACTION * residual + 5e-7);
    assert!(luminance(BASE) - luminance(after) >= 0.65 * residual - 5e-7);
    assert!(max_difference(chromaticity(before), chromaticity(after)) < 2e-6);
    for c in 0..3 { assert!((after[c] / before[c] - after[0] / before[0]).abs() < 3e-6); }
    for y in 0..SIDE {
        for x in 0..SIDE {
            if x != 20 || y < 3 || y + 3 >= SIDE {
                assert!(bits(&pixel(&source, x, y), &pixel(&result, x, y)));
            }
        }
    }
}

#[test]
fn amount_scales_luminance_lift_without_feedback_and_axis_sign_is_irrelevant() {
    let source = furrow();
    let mask = vec![1.0; SIDE*SIDE];
    let full = apply(&source, &mask, 1.0);
    let base_y = luminance(pixel(&source, 20, 20).map(decode));
    let full_lift = luminance(pixel(&full, 20, 20).map(decode)) - base_y;
    for amount in [0.25, 0.5, 0.75] {
        let result = apply(&source, &mask, amount);
        let lift = luminance(pixel(&result, 20, 20).map(decode)) - base_y;
        assert!((lift - amount * full_lift).abs() < 4e-7);
        assert!(bits(&result, &apply(&source, &mask, amount)));
    }
    assert!(bits(&full, &execute(&source, &mask, 1.0, [-1.0, 0.0], 1)));
}

#[test]
fn flat_fields_bright_flakes_edges_blobs_broad_and_deep_features_are_unchanged() {
    let mask = vec![1.0; SIDE*SIDE];
    let images = [
        scene(|_, _| BASE),
        scene(|x, _| BASE.map(|v| if x == 20 { v * 1.15 } else { v })),
        scene(|x, _| BASE.map(|v| if x >= 20 { v * 0.82 } else { v })),
        scene(|x, y| BASE.map(|v| if x == 20 && y == 20 { v * 0.82 } else { v })),
        scene(|x, _| BASE.map(|v| if (17..24).contains(&x) { v * 0.82 } else { v })),
        scene(|x, _| BASE.map(|v| if x == 20 { v * 0.40 } else { v })),
        scene(|x, _| BASE.map(|v| if x == 20 { v * 0.03 } else { v })),
    ];
    for image in images { assert!(bits(&image, &apply(&image, &mask, 1.0))); }
}

#[test]
fn pigment_difference_and_asymmetric_flanks_do_not_become_furrows() {
    let mask = vec![1.0; SIDE*SIDE];
    let pigment = scene(|x, _| if x == 20 { [0.20, 0.11, 0.07] } else { BASE });
    assert!(bits(&pigment, &apply(&pigment, &mask, 1.0)));
    let asymmetric = scene(|x, _| BASE.map(|v| v * if x == 20 { 0.82 } else if x < 20 { 0.98 } else { 1.12 }));
    assert!(bits(&asymmetric, &apply(&asymmetric, &mask, 1.0)));
}

#[test]
fn grayscale_and_rotated_chromatic_furrows_have_no_fixed_hue_assumption() {
    let mask = vec![1.0; SIDE*SIDE];
    let gray = scene(|x, _| [if x == 20 { 0.25 } else { 0.30 }; 3]);
    assert!(pixel(&apply(&gray, &mask, 1.0), 20, 20)[0] > pixel(&gray, 20, 20)[0]);
    let rotated = scene(|x, y| {
        let distance = (x as f32 - 20.0) * 0.866_025_4 + (y as f32 - 20.0) * 0.5;
        let gain = 1.0 - 0.18 * (-(distance * distance) / (2.0 * 0.65 * 0.65)).exp();
        BASE.map(|v| v * gain)
    });
    let result = execute(&rotated, &mask, 1.0, [1.0, 0.0], 2);
    assert!(pixel(&result, 20, 20)[0] > pixel(&rotated, 20, 20)[0]);
    let transposed = scene(|_, y| BASE.map(|v| if y == 20 { v * 0.82 } else { v }));
    assert!(pixel(&execute(&transposed, &mask, 1.0, [0.0, 1.0], 1), 20, 20)[0]
        > pixel(&transposed, 20, 20)[0]);
    assert!(bits(&furrow(), &execute(&furrow(), &mask, 1.0, [0.0, 1.0], 1)));
}

#[test]
fn every_intermediate_support_pixel_matters_not_only_sample_endpoints() {
    let source = furrow();
    let full = vec![1.0; SIDE*SIDE];
    assert!(pixel(&apply(&source, &full, 1.0), 20, 20)[0] > pixel(&source, 20, 20)[0]);
    for hole in [0.0, 0.5, 0.998] {
        let mut mask = full.clone();
        mask[23 * SIDE + 23] = hole; // Square corner, not a central profile tap.
        let result = apply(&source, &mask, 1.0);
        assert!(bits(&pixel(&source, 20, 20), &pixel(&result, 20, 20)));
    }
    let mut seam = full;
    for x in 0..SIDE { seam[21*SIDE+x] = 0.0; }
    assert!(bits(&pixel(&source, 20, 20), &pixel(&apply(&source, &seam, 1.0), 20, 20)));
}

#[test]
fn masked_colour_changes_never_contaminate_a_supported_pixel() {
    let source = furrow();
    let mut changed = source.clone();
    let mut mask = vec![1.0; SIDE*SIDE];
    for y in 0..SIDE {
        for x in 0..SIDE {
            if x < 10 || x > 30 || y < 10 || y > 30 {
                let i = y*SIDE+x;
                mask[i] = 0.0;
                changed[3*i..3*i+3].copy_from_slice(&[0.97, 0.01, 0.80]);
            }
        }
    }
    let a = apply(&source, &mask, 1.0);
    let b = apply(&changed, &mask, 1.0);
    for i in 0..SIDE*SIDE {
        if mask[i] == 1.0 { assert!(bits(&a[3*i..3*i+3], &b[3*i..3*i+3])); }
    }
}

#[test]
fn clipped_vertex_is_rejected_even_when_its_bilinear_weight_is_zero() {
    let mut source = furrow();
    source[3*(23*SIDE+23)] = 1.0;
    let result = apply(&source, &vec![1.0; SIDE*SIDE], 1.0);
    assert!(bits(&pixel(&source, 20, 20), &pixel(&result, 20, 20)));
    for colour in [[0.0; 3], [1.0; 3], [0.99, 0.2, 0.1]] {
        let mut source = furrow();
        source[3*(20*SIDE+20)..3*(20*SIDE+20)+3].copy_from_slice(&colour);
        assert!(bits(&colour, &pixel(&apply(&source, &vec![1.0; SIDE*SIDE], 1.0), 20, 20)));
    }
}

#[test]
fn rgb16_adjacent_codes_are_not_reduced_to_rgb8() {
    let mut a = furrow();
    for value in &mut a { *value = (*value * 65535.0).round() / 65535.0; }
    let mut b = a.clone();
    b[3*(20*SIDE+20)] += 1.0 / 65535.0;
    let mask = vec![1.0; SIDE*SIDE];
    let out_a = apply(&a, &mask, 1.0);
    let out_b = apply(&b, &mask, 1.0);
    assert_ne!(pixel(&out_a, 20, 20)[0].to_bits(), pixel(&out_b, 20, 20)[0].to_bits());
    assert!(pixel(&out_a, 20, 20)[0] > pixel(&a, 20, 20)[0]);
}

#[test]
fn real_halo_matches_full_source_interior_without_repeated_samples() {
    let source = furrow();
    let mask = vec![1.0; SIDE*SIDE];
    let full = apply(&source, &mask, 0.6);
    let start = 10;
    let side = 21;
    let mut crop = Vec::new();
    for y in start..start+side {
        crop.extend_from_slice(&source[3*(y*SIDE+start)..3*(y*SIDE+start+side)]);
    }
    let mut result = vec![0.0; crop.len()];
    apply_into(&crop, &vec![1.0; side*side], side, side, 0.6, [1.0, 0.0], 1, &mut result, || false).unwrap();
    for y in 15..26 {
        for x in 15..26 {
            let local = 3*((y-start)*side+x-start);
            for c in 0..3 { assert!((result[local+c] - full[3*(y*SIDE+x)+c]).abs() < 1e-6); }
        }
    }
}

#[test]
fn errors_and_late_cancellation_never_commit_partial_output() {
    let source = furrow();
    let mask = vec![1.0; SIDE*SIDE];
    let marker = vec![-42.0; source.len()];
    for stop in [1, 10, 80, 150] {
        let mut output = marker.clone();
        let mut polls = 0;
        let result = apply_into(&source, &mask, SIDE, SIDE, 1.0, [1.0, 0.0], 1, &mut output, || {
            polls += 1;
            polls >= stop
        });
        assert_eq!(result, Err(CANCELLED));
        assert!(bits(&marker, &output));
    }
    for bad in [f32::NAN, f32::INFINITY, -0.1, 1.1] {
        let mut invalid = source.clone();
        let last = invalid.len()-1;
        invalid[last] = bad;
        let mut output = marker.clone();
        assert_eq!(apply_into(&invalid, &mask, SIDE, SIDE, 0.0, [1.0, 0.0], 1, &mut output, || false), Err(PIXEL_ERROR));
        assert!(bits(&marker, &output));
    }
}

#[test]
fn strict_settings_shapes_resources_and_mask_finiteness() {
    let source = furrow();
    let mask = vec![1.0; SIDE*SIDE];
    let mut out = vec![0.0; source.len()];
    for radius in [0, MAX_RADIUS+1] {
        assert_eq!(apply_into(&source, &mask, SIDE, SIDE, 0.0, [1.0, 0.0], radius, &mut out, || false), Err(SETTINGS_ERROR));
    }
    for axis in [[0.0, 0.0], [2.0, 0.0], [f32::NAN, 1.0]] {
        assert_eq!(apply_into(&source, &mask, SIDE, SIDE, 0.0, axis, 1, &mut out, || false), Err(SETTINGS_ERROR));
    }
    for amount in [-0.1, 1.1, f32::NAN] {
        assert_eq!(apply_into(&source, &mask, SIDE, SIDE, amount, [1.0, 0.0], 1, &mut out, || false), Err(SETTINGS_ERROR));
    }
    let mut bad_mask = mask;
    bad_mask[0] = f32::NAN;
    assert_eq!(apply_into(&source, &bad_mask, SIDE, SIDE, 0.0, [1.0, 0.0], 1, &mut out, || false), Err(PIXEL_ERROR));
    assert_eq!(admit(65536, 65536), Err(RESOURCE_ERROR));
    assert_eq!(admit(65537, 1), Err(ABI_ERROR));
    assert_eq!(admit(0, 1), Err(ABI_ERROR));
}

#[test]
fn ffi_parity_and_invalid_spans_are_checked_before_dereference() {
    let source = furrow();
    let mask = vec![1.0; SIDE*SIDE];
    let expected = apply(&source, &mask, 0.4);
    let mut output = vec![-42.0; source.len()];
    unsafe {
        assert_eq!(lrt_lip_texture_abi(), 1);
        assert_eq!(lrt_lip_texture_apply_v1(source.as_ptr(), source.len(), mask.as_ptr(), mask.len(),
            SIDE, SIDE, 0.4, 1.0, 0.0, 1, output.as_mut_ptr(), output.len(), None, std::ptr::null_mut()), 0);
        assert!(bits(&expected, &output));
        assert_eq!(lrt_lip_texture_apply_v1(source.as_ptr(), source.len(), mask.as_ptr(), mask.len(),
            SIDE, SIDE, 0.4, 1.0, 0.0, 1, source.as_ptr() as *mut f32, source.len(), None, std::ptr::null_mut()), ABI_ERROR);
        assert_eq!(lrt_lip_texture_apply_v1(std::ptr::null(), source.len(), mask.as_ptr(), mask.len(),
            SIDE, SIDE, 0.4, 1.0, 0.0, 1, output.as_mut_ptr(), output.len(), None, std::ptr::null_mut()), ABI_ERROR);
        assert_eq!(lrt_lip_texture_apply_v1(source.as_ptr(), source.len()-1, mask.as_ptr(), mask.len(),
            SIDE, SIDE, 0.4, 1.0, 0.0, 1, output.as_mut_ptr(), output.len(), None, std::ptr::null_mut()), ABI_ERROR);
        assert_eq!(lrt_lip_texture_apply_v1(source.as_ptr(), source.len(), mask.as_ptr(), mask.len(),
            SIDE, SIDE, 0.4, 1.0, 0.0, 1, std::ptr::null_mut(), output.len(), None, std::ptr::null_mut()), ABI_ERROR);
    }
}
