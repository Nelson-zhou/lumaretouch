// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. No compilation, execution or real-photo acceptance claimed.
use super::*;

const W: usize = 97;
const H: usize = 65;
const R: usize = 6;
fn pixel(luminance: f64, u: f64, v: f64) -> [f32; 3] {
    let g = luminance/(0.2126*u.exp()+0.7152+0.0722*v.exp());
    [g*u.exp(), g, g*v.exp()].map(encode)
}
fn scene(tone_u: f64, tone_v: f64) -> (Vec<f32>, Vec<f32>) {
    let mut source = Vec::new();
    for yy in 0..H {
        for x in 0..W {
            let patch = x > 3*W/4;
            let luminance = 0.18+0.025*(std::f64::consts::TAU*x as f64/5.0).sin()
                + 0.02*(std::f64::consts::TAU*yy as f64/17.0).sin();
            source.extend(pixel(luminance, tone_u+if patch { 0.25 } else { 0.0 },
                                          tone_v-if patch { 0.12 } else { 0.0 }));
        }
    }
    (source, vec![1.0; W*H])
}
fn prepare(source: &[f32], coverage: &[f32], amount: f32) -> Vec<f32> {
    let mut shift = vec![f32::NAN; 2*W*H];
    prepare_into(source, coverage, W, H, amount, R, &mut shift, || false).unwrap();
    shift
}
fn apply(current: &[f32], shift: &[f32]) -> Vec<f32> {
    let mut output = vec![f32::NAN; 3*W*H];
    apply_into(current, shift, W, H, &mut output, || false).unwrap();
    output
}
fn bits(a: &[f32], b: &[f32]) -> bool {
    a.len() == b.len() && a.iter().zip(b).all(|(x,y)| x.to_bits() == y.to_bits())
}
fn rgb(image: &[f32], i: usize) -> [f64; 3] {
    linear([image[3*i], image[3*i+1], image[3*i+2]])
}

#[test]
fn exact_median_selection_odd_even_duplicates_and_cancellation() {
    let mut odd = vec![9.0, -7.0, 1.0, 4.0, 2.0];
    assert_eq!(median(&mut odd, &mut || false), Ok(2.0));
    let mut even: Vec<_> = (0..1000).rev().map(|v| v as f64).collect();
    assert_eq!(median(&mut even, &mut || false), Ok(499.5));
    let mut duplicate = vec![0.25; 4097];
    assert_eq!(median(&mut duplicate, &mut || false), Ok(0.25));
    let mut visits = 0;
    assert_eq!(median(&mut even, &mut || { visits += 1; visits > 10 }), Err(CANCELLED));
}

#[test]
fn neutral_shift_and_current_endpoints_are_bit_exact() {
    let (mut source, mask) = scene(0.45, -0.5);
    source[0] = -0.0;
    let shift = prepare(&source, &mask, -0.0);
    assert!(shift.iter().all(|v| v.to_bits() == 0));
    assert!(bits(&source, &apply(&source, &shift)));
    let nonzero: Vec<_> = (0..W*H).flat_map(|_| [0.04, -0.03]).collect();
    for endpoint in [[0.0, -0.0, 0.0], [1.0; 3]] {
        let current: Vec<_> = (0..W*H).flat_map(|_| endpoint).collect();
        assert!(bits(&current, &apply(&current, &nonzero)));
    }
    let mut bad = source.clone();
    bad[0] = f32::NAN;
    let mut sentinel = vec![13.0; 2*W*H];
    assert_eq!(prepare_into(&bad, &mask, W, H, 0.0, R, &mut sentinel, || false), Err(PIXEL_ERROR));
    assert!(sentinel.iter().all(|&v| v == 13.0));
}

#[test]
fn already_even_chroma_remains_exact_zero_despite_luminance_texture() {
    let mut source = Vec::new();
    for i in 0..W*H {
        source.extend(pixel(0.18+0.025*(i as f64).sin(), 0.45, -0.5));
    }
    let shift = prepare(&source, &vec![1.0; W*H], 1.0);
    assert!(shift.iter().all(|&v| v == 0.0));
    assert!(bits(&source, &apply(&source, &shift)));
}

#[test]
fn own_face_chromatic_patch_corrects_toward_source_not_external_palette() {
    let (source, mask) = scene(0.45, -0.5);
    let shift = prepare(&source, &mask, 1.0);
    let at = (H/2)*W+W-8;
    assert!(shift[2*at] < -0.005 && shift[2*at+1] > 0.002);
    let (different_tone, _) = scene(0.15, -0.25);
    let other = prepare(&different_tone, &mask, 1.0);
    // Same unevenness on another own tone yields the same correction, not a
    // globally prescribed skin color. All fixtures stay inside reliability=1.
    for (a,b) in shift.iter().zip(&other) { assert!((a-b).abs() < 2e-6); }
    let changed = apply(&source, &shift);
    let before = (rgb(&source, at)[0]/rgb(&source, at)[1]).ln();
    let after = (rgb(&changed, at)[0]/rgb(&changed, at)[1]).ln();
    assert!((after-0.45).abs() < (before-0.45).abs());
    assert!(!bits(&source, &changed));
}

#[test]
fn preserves_actual_current_luminance_detail_and_chroma_displacement() {
    let (source, mask) = scene(0.45, -0.5);
    let shift = prepare(&source, &mask, 1.0);
    // Actual stage differs in both color and luminance from prepared source.
    let current: Vec<_> = (0..W*H).flat_map(|i|
        pixel(0.30+0.05*(i as f64/2.0).sin(), 0.20, -0.10)).collect();
    let result = apply(&current, &shift);
    for i in 0..W*H {
        let before = rgb(&current, i);
        let after = rgb(&result, i);
        assert!((y(after)-y(before)).abs() <= 2e-7);
        let du = (after[0]/after[1]).ln()-(before[0]/before[1]).ln();
        let dv = (after[2]/after[1]).ln()-(before[2]/before[1]).ln();
        assert!((du-f64::from(shift[2*i])).abs() <= 2e-6);
        assert!((dv-f64::from(shift[2*i+1])).abs() <= 2e-6);
        if i > 0 {
            let source_detail = y(before)-y(rgb(&current, i-1));
            let result_detail = y(after)-y(rgb(&result, i-1));
            assert!((source_detail-result_detail).abs() <= 4e-7);
        }
    }
}

#[test]
fn zero_coverage_foreign_pixels_and_hidden_low_bits_are_not_quantized() {
    let (mut source, mut mask) = scene(0.45, -0.5);
    for yy in 0..H {
        for x in 0..W/4 { mask[yy*W+x] = 0.0; }
    }
    let original = prepare(&source, &mask, 1.0);
    for i in 0..W*H {
        if mask[i] == 0.0 { source[3*i..3*i+3].copy_from_slice(&[0.95, 0.05, 0.98]); }
    }
    let changed_background = prepare(&source, &mask, 1.0);
    assert!(bits(&original, &changed_background));
    for i in 0..W*H {
        if mask[i] == 0.0 { assert_eq!(&original[2*i..2*i+2], &[0.0, 0.0]); }
    }
    let shift: Vec<_> = (0..W*H).flat_map(|_| [-0.03, 0.02]).collect();
    let mut low_bits = vec![0.501_f32; W*H*3];
    let base = apply(&low_bits, &shift);
    low_bits[0] += 0.00001;
    assert_eq!((0.501_f32*255.0).round(), (low_bits[0]*255.0).round());
    let fine = apply(&low_bits, &shift);
    assert!(!bits(&base, &fine));
    assert!((y(rgb(&fine, 0))-y(rgb(&low_bits, 0))).abs() < 2e-7);
}

#[test]
fn amount_is_bounded_and_reference_not_replaced_by_rare_color_outliers() {
    let (source, mask) = scene(0.45, -0.5);
    let half = prepare(&source, &mask, 0.5);
    let full = prepare(&source, &mask, 1.0);
    for i in 0..W*H {
        assert!(shift_valid(full[2*i], full[2*i+1]));
        assert!((half[2*i]*2.0-full[2*i]).abs() < 1e-7);
        assert!((half[2*i+1]*2.0-full[2*i+1]).abs() < 1e-7);
    }
    let mut outliers = source.clone();
    for i in 0..100 { outliers[3*i..3*i+3].copy_from_slice(&pixel(0.20, -0.4, 0.2)); }
    let reference_before = reference(&source, &mask, &mut || false).unwrap();
    let reference_after = reference(&outliers, &mask, &mut || false).unwrap();
    assert!((reference_before[0]-reference_after[0]).abs() < 1e-6);
    assert!((reference_before[1]-reference_after[1]).abs() < 1e-6);
}

#[test]
fn one_common_gamut_interpolation_preserves_luminance_without_clipping() {
    for current in [[0.995, 0.25, 0.4], [0.001, 0.999, 0.45], [1.0, 0.4, 0.2],
                    [0.9, 0.9, 0.999], [0.0, 0.4, 0.25], [0.00001, 0.00002, 0.00003]] {
        for shift in [[0.08, -0.03], [-0.08, 0.03], [0.01, 0.08]] {
            let result = corrected(current, shift).unwrap();
            assert!(result.iter().copied().all(unit));
            let before = linear(current);
            let after = linear(result);
            assert!((y(after)-y(before)).abs() < 2e-7);
            let raw = [before[0]*f64::from(shift[0]).exp(), before[1], before[2]*f64::from(shift[1]).exp()];
            let proposal = raw.map(|v| v*y(before)/y(raw));
            let mut interpolation = None;
            for c in 0..3 {
                if (proposal[c]-before[c]).abs() > 1e-5 {
                    let t = (after[c]-before[c])/(proposal[c]-before[c]);
                    assert!((-1e-4..=1.0001).contains(&t));
                    if let Some(previous) = interpolation { assert!((t-previous).abs() < 0.003); }
                    interpolation = Some(t);
                }
            }
        }
    }
}

#[test]
fn insufficient_reference_and_context_are_distinct_atomic_refusals() {
    let (source, _) = scene(0.45, -0.5);
    let mut mask = vec![0.0; W*H];
    mask[..63].fill(1.0);
    let mut output = vec![42.0; W*H*2];
    assert_eq!(prepare_into(&source, &mask, W, H, 1.0, R, &mut output, || false), Err(REFERENCE_ERROR));
    assert!(output.iter().all(|&v| v == 42.0));
    mask.fill(0.0);
    for yy in (2..H).step_by(8) {
        for x in (2..W).step_by(8) { mask[yy*W+x] = 1.0; }
    }
    assert!(mask.iter().filter(|&&v| v == 1.0).count() >= 64);
    assert_eq!(prepare_into(&source, &mask, W, H, 1.0, 4, &mut output, || false), Err(CONTEXT_ERROR));
    assert!(output.iter().all(|&v| v == 42.0));
    let dark = vec![0.001; W*H*3];
    assert_eq!(prepare_into(&dark, &vec![1.0; W*H], W, H, 1.0, R, &mut output, || false), Err(REFERENCE_ERROR));
}

#[test]
fn cancellation_and_errors_never_publish_partial_outputs() {
    let (source, mask) = scene(0.45, -0.5);
    for stop in [1, 10, 100, 500] {
        let mut calls = 0;
        let mut output = vec![42.0; W*H*2];
        let status = prepare_into(&source, &mask, W, H, 1.0, R, &mut output,
            || { calls += 1; calls >= stop });
        assert_eq!(status, Err(CANCELLED));
        assert!(output.iter().all(|&v| v == 42.0));
    }
    let shift = vec![0.01; W*H*2];
    for stop in [1, 30, 70] {
        let mut calls = 0;
        let mut output = vec![42.0; W*H*3];
        assert_eq!(apply_into(&source, &shift, W, H, &mut output,
            || { calls += 1; calls >= stop }), Err(CANCELLED));
        assert!(output.iter().all(|&v| v == 42.0));
    }
    let mut invalid = shift;
    invalid[0] = 0.09;
    invalid[1] = 0.09; // Each component bounded, vector not bounded.
    let mut output = vec![42.0; W*H*3];
    assert_eq!(apply_into(&source, &invalid, W, H, &mut output, || false), Err(PIXEL_ERROR));
    assert!(output.iter().all(|&v| v == 42.0));
}

#[test]
fn source_window_retains_all_face_reference_and_real_guided_halo() {
    let (source, mut mask) = scene(0.45, -0.5);
    for yy in 0..H {
        for x in 0..W {
            if x < 20 || x >= 80 || yy < 18 || yy >= 48 { mask[yy*W+x] = 0.0; }
        }
    }
    let full = prepare(&source, &mask, 1.0);
    let (left, top, right, bottom) = (7, 5, 93, 61); // Whole own support +2r+1.
    let (width, height) = (right-left, bottom-top);
    let mut cropped = Vec::new();
    let mut permission = Vec::new();
    for yy in top..bottom {
        cropped.extend_from_slice(&source[(yy*W+left)*3..(yy*W+right)*3]);
        permission.extend_from_slice(&mask[yy*W+left..yy*W+right]);
    }
    let mut result = vec![0.0; width*height*2];
    prepare_into(&cropped, &permission, width, height, 1.0, R, &mut result, || false).unwrap();
    for yy in 18..48 {
        for x in 20..80 {
            let a = (yy*W+x)*2;
            let b = ((yy-top)*width+x-left)*2;
            assert!((full[a]-result[b]).abs() < 1e-6);
            assert!((full[a+1]-result[b+1]).abs() < 1e-6);
        }
    }
}

#[test]
fn abi_parity_lengths_null_alignment_alias_and_resource_rejection() {
    let (source, mask) = scene(0.45, -0.5);
    let expected = prepare(&source, &mask, 1.0);
    let mut output = vec![42.0; 2*W*H];
    unsafe {
        assert_eq!(lrt_skin_evenness_abi(), 1);
        assert_eq!(lrt_skin_evenness_prepare_v1(source.as_ptr(), source.len(), mask.as_ptr(), mask.len(),
            W, H, 1.0, R, output.as_mut_ptr(), output.len(), None, std::ptr::null_mut()), 0);
        assert!(bits(&output, &expected));
        assert_eq!(lrt_skin_evenness_prepare_v1(std::ptr::null(), source.len(), mask.as_ptr(), mask.len(),
            W, H, 1.0, R, output.as_mut_ptr(), output.len(), None, std::ptr::null_mut()), ABI_ERROR);
        assert_eq!(lrt_skin_evenness_prepare_v1(source.as_ptr(), source.len()-1, mask.as_ptr(), mask.len(),
            W, H, 1.0, R, output.as_mut_ptr(), output.len(), None, std::ptr::null_mut()), ABI_ERROR);
        assert_eq!(lrt_skin_evenness_prepare_v1(source.as_ptr(), source.len(), mask.as_ptr(), mask.len(),
            W, H, 1.0, R, source.as_ptr() as *mut f32, output.len(), None, std::ptr::null_mut()), ABI_ERROR);
        let unaligned = (source.as_ptr() as *const u8).add(1) as *const f32;
        assert_eq!(lrt_skin_evenness_prepare_v1(unaligned, source.len(), mask.as_ptr(), mask.len(),
            W, H, 1.0, R, output.as_mut_ptr(), output.len(), None, std::ptr::null_mut()), ABI_ERROR);
        let mut rendered = vec![42.0; source.len()];
        assert_eq!(lrt_skin_evenness_apply_v1(source.as_ptr(), source.len(), output.as_ptr(), output.len(),
            W, H, rendered.as_mut_ptr(), rendered.len(), None, std::ptr::null_mut()), 0);
        assert!(bits(&rendered, &apply(&source, &expected)));
    }
    assert_eq!(admit(0, 1, 112), Err(ABI_ERROR));
    assert_eq!(admit(65_537, 1, 112), Err(ABI_ERROR));
    assert_eq!(admit(8000, 4001, 112), Err(RESOURCE_ERROR));
    assert_eq!(admit(8000, 4000, 112), Ok(32_000_000));
}
