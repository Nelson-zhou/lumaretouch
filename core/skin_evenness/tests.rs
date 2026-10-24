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

// Optional body-to-own-face extension. All new fixtures are AUTHORED / UNRUN.
const FW: usize = 17;
const FH: usize = 13;
fn flat_chroma(width: usize, height: usize, luminance: f64, u: f64, v: f64) -> Vec<f32> {
    (0..width*height).flat_map(|i| pixel(luminance+0.01*(i as f64).sin(), u, v)).collect()
}
fn body_match(body: &[f32], body_mask: &[f32], face: &[f32], face_mask: &[f32], amount: f32) -> Vec<f32> {
    let mut field = vec![f32::NAN; 2*W*H];
    body_face_prepare_into(body, body_mask, W, H, face, face_mask, FW, FH,
        amount, R, &mut field, || false).unwrap();
    field
}

#[test]
fn optional_face_target_is_not_body_self_median_or_face_brightness_match() {
    let body = flat_chroma(W, H, 0.18, 0.45, -0.5);
    let body_mask = vec![1.0; W*H];
    let face_mask = vec![1.0; FW*FH];
    let face = flat_chroma(FW, FH, 0.12, 0.15, -0.25);
    let brighter_face = flat_chroma(FW, FH, 0.32, 0.15, -0.25);
    assert!(prepare(&body, &body_mask, 1.0).iter().all(|&v| v == 0.0));
    let field = body_match(&body, &body_mask, &face, &face_mask, 1.0);
    let bright = body_match(&body, &body_mask, &brighter_face, &face_mask, 1.0);
    for i in 0..W*H {
        assert!(field[2*i] < -0.005 && field[2*i+1] > 0.005);
        assert!(shift_valid(field[2*i], field[2*i+1]));
        assert!((field[2*i]-bright[2*i]).abs() < 2e-6);
        assert!((field[2*i+1]-bright[2*i+1]).abs() < 2e-6);
    }
    // Prepared source differs from the actual stage in both luminance and tone.
    let current = flat_chroma(W, H, 0.27, 0.30, -0.10);
    let output = apply(&current, &field);
    for i in 0..W*H { assert!((y(rgb(&output, i))-y(rgb(&current, i))).abs() <= 2e-7); }
}

#[test]
fn optional_face_reference_is_robust_and_corrects_body_patch_toward_own_face() {
    let (body, body_mask) = scene(0.45, -0.5);
    let face = flat_chroma(FW, FH, 0.20, 0.15, -0.25);
    let face_mask = vec![1.0; FW*FH];
    let field = body_match(&body, &body_mask, &face, &face_mask, 1.0);
    let mut outliers = face.clone();
    for i in 0..20 { outliers[3*i..3*i+3].copy_from_slice(&pixel(0.20, -0.4, 0.2)); }
    let robust = body_match(&body, &body_mask, &outliers, &face_mask, 1.0);
    for (a, b) in field.iter().zip(&robust) { assert!((a-b).abs() < 2e-6); }
    let changed = apply(&body, &field);
    for at in [(H/2)*W+W/2, (H/2)*W+W-8] {
        let before = rgb(&body, at); let after = rgb(&changed, at);
        let old_distance = ((before[0]/before[1]).ln()-0.15).hypot((before[2]/before[1]).ln()+0.25);
        let new_distance = ((after[0]/after[1]).ln()-0.15).hypot((after[2]/after[1]).ln()+0.25);
        assert!(new_distance < old_distance);
    }
    let half = body_match(&body, &body_mask, &face, &face_mask, 0.5);
    for (a, b) in half.iter().zip(&field) { assert!((2.0*a-b).abs() < 1e-7); }
}

#[test]
fn optional_own_face_equal_body_and_amount_zero_are_true_neutral() {
    let body = flat_chroma(W, H, 0.18, 0.45, -0.5);
    let face = flat_chroma(FW, FH, 0.25, 0.45, -0.5);
    let body_mask = vec![1.0; W*H]; let face_mask = vec![1.0; FW*FH];
    let equal = body_match(&body, &body_mask, &face, &face_mask, 1.0);
    assert!(equal.iter().all(|&v| v == 0.0));
    let neutral = body_match(&body, &vec![0.0; W*H], &face, &vec![0.0; FW*FH], -0.0);
    assert!(neutral.iter().all(|v| v.to_bits() == 0));
    assert!(bits(&body, &apply(&body, &neutral)));
}

#[test]
fn optional_protected_body_and_reference_pixels_do_not_enter_statistics() {
    let (mut body, mut body_mask) = scene(0.45, -0.5);
    let mut face = flat_chroma(FW, FH, 0.20, 0.15, -0.25);
    let mut face_mask = vec![1.0; FW*FH];
    face_mask[..40].fill(0.0);
    for yy in 0..H { for x in 0..W/4 { body_mask[yy*W+x] = 0.0; } }
    let field = body_match(&body, &body_mask, &face, &face_mask, 1.0);
    for i in 0..W*H {
        if body_mask[i] == 0.0 {
            body[3*i..3*i+3].copy_from_slice(&[0.95, 0.05, 0.98]);
            assert_eq!(&field[2*i..2*i+2], &[0.0, 0.0]);
        }
    }
    for i in 0..40 { face[3*i..3*i+3].copy_from_slice(&[0.98, 0.02, 0.96]); }
    let other = body_match(&body, &body_mask, &face, &face_mask, 1.0);
    assert!(bits(&field, &other));
}

#[test]
fn optional_body_face_reference_and_context_shortages_are_atomic_refusals() {
    let (body, body_mask) = scene(0.45, -0.5);
    let face = flat_chroma(FW, FH, 0.20, 0.15, -0.25);
    let face_mask = vec![1.0; FW*FH];
    let mut output = vec![42.0; W*H*2];
    let mut sparse_body = vec![0.0; W*H]; sparse_body[..63].fill(1.0);
    let mut sparse_face = vec![0.0; FW*FH]; sparse_face[..63].fill(1.0);
    for (bm, fm) in [(&sparse_body, &face_mask), (&body_mask, &sparse_face)] {
        assert_eq!(body_face_prepare_into(&body, bm, W, H, &face, fm, FW, FH,
            1.0, R, &mut output, || false), Err(REFERENCE_ERROR));
        assert!(output.iter().all(|&v| v == 42.0));
    }
    sparse_face[63] = 1.0;
    body_face_prepare_into(&body, &body_mask, W, H, &face, &sparse_face, FW, FH,
        1.0, R, &mut output, || false).unwrap(); // Exactly64 face samples, no face guided-context requirement.
    output.fill(42.0);
    sparse_body.fill(0.0);
    for yy in (2..H).step_by(8) { for x in (2..W).step_by(8) { sparse_body[yy*W+x] = 1.0; } }
    assert!(sparse_body.iter().filter(|&&v| v == 1.0).count() >= 64);
    assert_eq!(body_face_prepare_into(&body, &sparse_body, W, H, &face, &face_mask, FW, FH,
        1.0, 4, &mut output, || false), Err(CONTEXT_ERROR));
    assert!(output.iter().all(|&v| v == 42.0));
    let dark_face = vec![0.001; FW*FH*3];
    assert_eq!(body_face_prepare_into(&body, &body_mask, W, H, &dark_face, &face_mask, FW, FH,
        1.0, R, &mut output, || false), Err(REFERENCE_ERROR));
    assert!(output.iter().all(|&v| v == 42.0));
}

#[test]
fn optional_both_grids_validate_when_neutral_and_cancellation_never_publishes() {
    let (body, body_mask) = scene(0.45, -0.5);
    let face = flat_chroma(FW, FH, 0.20, 0.15, -0.25);
    let face_mask = vec![1.0; FW*FH];
    let mut output = vec![42.0; W*H*2];
    let mut total_polls = 0;
    body_face_prepare_into(&body, &body_mask, W, H, &face, &face_mask, FW, FH,
        1.0, R, &mut output, || { total_polls += 1; false }).unwrap();
    for stop in [1, 10, 100, 500, total_polls] {
        output.fill(42.0); let mut polls = 0;
        assert_eq!(body_face_prepare_into(&body, &body_mask, W, H, &face, &face_mask, FW, FH,
            1.0, R, &mut output, || { polls += 1; polls >= stop }), Err(CANCELLED));
        assert!(output.iter().all(|&v| v == 42.0));
    }
    for invalid in [f32::NAN, f32::INFINITY, -0.01, 1.01] {
        for which in 0..4 {
            let (mut b, mut bm, mut f, mut fm) = (body.clone(), body_mask.clone(), face.clone(), face_mask.clone());
            match which { 0 => b[0] = invalid, 1 => bm[0] = invalid,
                          2 => f[0] = invalid, _ => fm[0] = invalid }
            assert_eq!(body_face_prepare_into(&b, &bm, W, H, &f, &fm, FW, FH,
                0.0, R, &mut output, || false), Err(PIXEL_ERROR));
            assert!(output.iter().all(|&v| v == 42.0));
        }
    }
}

#[test]
fn optional_same_input_reference_matches_legacy_shared_solve_bit_for_bit() {
    let (source, mask) = scene(0.45, -0.5);
    let expected = prepare(&source, &mask, 1.0);
    let mut actual = vec![42.0; W*H*2];
    // Numerical-only same-input fixture, NOT host permission for face-as-body.
    body_face_prepare_into(&source, &mask, W, H, &source, &mask, W, H,
        1.0, R, &mut actual, || false).unwrap();
    assert!(bits(&actual, &expected));
}

#[test]
fn optional_complete_body_halo_crop_preserves_separate_whole_face_reference() {
    let (body, mut body_mask) = scene(0.45, -0.5);
    let face = flat_chroma(FW, FH, 0.20, 0.15, -0.25);
    let face_mask = vec![1.0; FW*FH];
    for yy in 0..H {
        for xx in 0..W {
            if xx < 20 || xx >= 80 || yy < 18 || yy >= 48 { body_mask[yy*W+xx] = 0.0; }
        }
    }
    let full = body_match(&body, &body_mask, &face, &face_mask, 1.0);
    let (left, top, right, bottom) = (7, 5, 93, 61); // Complete body support and real2r+1 halo.
    let (width, height) = (right-left, bottom-top);
    let mut cropped = Vec::new(); let mut coverage = Vec::new();
    for yy in top..bottom {
        cropped.extend_from_slice(&body[(yy*W+left)*3..(yy*W+right)*3]);
        coverage.extend_from_slice(&body_mask[yy*W+left..yy*W+right]);
    }
    let mut result = vec![42.0; width*height*2];
    body_face_prepare_into(&cropped, &coverage, width, height,
        &face, &face_mask, FW, FH, 1.0, R, &mut result, || false).unwrap();
    for yy in 18..48 {
        for xx in 20..80 {
            let a = (yy*W+xx)*2; let b = ((yy-top)*width+xx-left)*2;
            assert!((full[a]-result[b]).abs() < 1e-6);
            assert!((full[a+1]-result[b+1]).abs() < 1e-6);
        }
    }
}

#[test]
fn optional_abi_checks_every_input_span_before_slicing_and_keeps_abi_one() {
    let (body, body_mask) = scene(0.45, -0.5);
    let face = flat_chroma(FW, FH, 0.20, 0.15, -0.25);
    let face_mask = vec![1.0; FW*FH];
    let expected = body_match(&body, &body_mask, &face, &face_mask, 1.0);
    let mut output = vec![42.0; W*H*2];
    unsafe {
        assert_eq!(lrt_skin_evenness_abi(), 1);
        assert_eq!(lrt_body_face_match_prepare_v1(body.as_ptr(), body.len(), body_mask.as_ptr(), body_mask.len(),
            W, H, face.as_ptr(), face.len(), face_mask.as_ptr(), face_mask.len(), FW, FH,
            1.0, R, output.as_mut_ptr(), output.len(), None, std::ptr::null_mut()), 0);
        assert!(bits(&output, &expected));
        for which in 0..4 {
            let mut pointers = [body.as_ptr(), body_mask.as_ptr(), face.as_ptr(), face_mask.as_ptr()];
            for invalid in [std::ptr::null(), (pointers[which] as *const u8).add(1) as *const f32] {
                pointers[which] = invalid; output.fill(42.0);
                assert_eq!(lrt_body_face_match_prepare_v1(pointers[0], body.len(), pointers[1], body_mask.len(),
                    W, H, pointers[2], face.len(), pointers[3], face_mask.len(), FW, FH,
                    1.0, R, output.as_mut_ptr(), output.len(), None, std::ptr::null_mut()), ABI_ERROR);
                assert!(output.iter().all(|&v| v == 42.0));
            }
            // Alias failures are tested before any output slice is created. The
            // source allocation need not hold output_len because it is refused.
            let originals = [body.as_ptr(), body_mask.as_ptr(), face.as_ptr(), face_mask.as_ptr()];
            assert_eq!(lrt_body_face_match_prepare_v1(body.as_ptr(), body.len(), body_mask.as_ptr(), body_mask.len(),
                W, H, face.as_ptr(), face.len(), face_mask.as_ptr(), face_mask.len(), FW, FH,
                1.0, R, originals[which] as *mut f32, output.len(), None, std::ptr::null_mut()), ABI_ERROR);
        }
        assert_eq!(lrt_body_face_match_prepare_v1(body.as_ptr(), body.len(), body_mask.as_ptr(), body_mask.len(),
            W, H, face.as_ptr(), face.len()-1, face_mask.as_ptr(), face_mask.len(), FW, FH,
            1.0, R, output.as_mut_ptr(), output.len(), None, std::ptr::null_mut()), ABI_ERROR);
    }
    assert_eq!(admit_body_face(8000, 4000, 1, 1), Err(RESOURCE_ERROR));
    assert_eq!(admit_body_face(8000, 2000, 8000, 2000), Ok((16_000_000, 16_000_000)));
    assert_eq!(admit_body_face(0, H, FW, FH), Err(ABI_ERROR));
    assert_eq!(admit_body_face(W, H, 65_537, 1), Err(ABI_ERROR));
}

// Test-only verbatim project-owned pre-refactor oracle from e30f53da51dbfa9b3c5c11598ee210eeb79fb387.
// Only function name/visibility changed. Kept for executable legacy parity, not an alternate runtime path.
// Original function text SHA256: 7c39bb8024359465f38a61fc857a028ac23b98c1633d87659481fbb01379df40
fn pre_extension_prepare_into<F: FnMut() -> bool>(source: &[f32], coverage: &[f32],
    width: usize, height: usize, amount: f32, radius: usize,
    output: &mut [f32], mut cancelled: F) -> Result<(), i32> {
    let n = admit(width, height, NATIVE_PREPARE_TOTAL_BYTES_PER_PIXEL)?;
    if source.len() != n*3 || coverage.len() != n || output.len() != n*2 { return Err(ABI_ERROR); }
    if !unit(amount) || !(MIN_RADIUS..=MAX_RADIUS).contains(&radius) { return Err(SETTINGS_ERROR); }
    for i in 0..n {
        if i % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
        if !unit(coverage[i]) || !source[3*i..3*i+3].iter().copied().all(unit) { return Err(PIXEL_ERROR); }
    }
    if amount == 0.0 {
        poll(&mut cancelled)?;
        output.fill(0.0);
        return Ok(());
    }
    let target = reference(source, coverage, &mut cancelled)?;
    // Store local mass/mean/variance first, then overwrite in-place with two
    // weighted slope/intercept pairs and valid coefficient-domain weight.
    let mut coefficients = filled(n, [0.0_f64; 5], &mut cancelled)?;
    let rows = horizontal(width, height, radius, |i| {
        let s = source_sample(source, coverage, i);
        let w = s[3];
        [w, w*w, w*s[0], w*s[0]*s[0], if w > 0.0 { 1.0 } else { 0.0 }]
    }, &mut cancelled)?;
    vertical(&rows, width, height, radius, |i, sum| {
        if source_sample(source, coverage, i)[3] == 0.0 || sum[0] < 4.0 || sum[1] <= 0.0
            || sum[4] < 8.0 || sum[0]*sum[0]/sum[1] < 8.0
            || sum[0]/area(i, width, height, radius) < 0.15 { return Ok(()); }
        let mean = sum[2]/sum[0];
        let variance = (sum[3]/sum[0]-mean*mean).max(0.0);
        coefficients[i] = [sum[0], mean, variance, 1.0, 0.0];
        Ok(())
    }, &mut cancelled)?;
    drop(rows);
    let rows = horizontal(width, height, radius, |i| {
        let s = source_sample(source, coverage, i);
        [s[3]*s[1], s[3]*s[2], s[3]*s[0]*s[1], s[3]*s[0]*s[2]]
    }, &mut cancelled)?;
    vertical(&rows, width, height, radius, |i, sum| {
        let statistics = coefficients[i];
        if statistics[3] == 0.0 { return Ok(()); }
        let s = source_sample(source, coverage, i);
        let mass = statistics[0];
        let mean_i = statistics[1];
        let mean_u = sum[0]/mass;
        let mean_v = sum[1]/mass;
        let a_u = (sum[2]/mass-mean_i*mean_u)/(statistics[2]+GUIDANCE_EPSILON);
        let a_v = (sum[3]/mass-mean_i*mean_v)/(statistics[2]+GUIDANCE_EPSILON);
        coefficients[i] = [s[3]*a_u, s[3]*(mean_u-a_u*mean_i),
                           s[3]*a_v, s[3]*(mean_v-a_v*mean_i), s[3]];
        if !coefficients[i].iter().all(|v| v.is_finite()) { return Err(PIXEL_ERROR); }
        Ok(())
    }, &mut cancelled)?;
    drop(rows);
    let rows = horizontal(width, height, radius, |i| coefficients[i], &mut cancelled)?;
    let mut result = filled(n*2, 0.0_f32, &mut cancelled)?;
    let mut valid_context = 0_usize;
    vertical(&rows, width, height, radius, |i, sum| {
        if coefficients[i][4] == 0.0 || sum[4] < 4.0
            || sum[4]/area(i, width, height, radius) < 0.15 { return Ok(()); }
        valid_context += 1;
        let s = source_sample(source, coverage, i);
        let du = target[0]-(sum[0]*s[0]+sum[1])/sum[4];
        let dv = target[1]-(sum[2]*s[0]+sum[3])/sum[4];
        let norm = du.hypot(dv);
        if !norm.is_finite() { return Err(PIXEL_ERROR); }
        // Deadzone suppresses float32 decode/moment roundoff on constant chroma.
        if norm <= 1e-6 { return Ok(()); }
        let scale = f64::from(amount)*s[3]*CORRECTION_GAIN
            * CHROMA_LIMIT*(norm/CHROMA_LIMIT).tanh()/norm;
        let u = (du*scale) as f32;
        let v = (dv*scale) as f32;
        if !shift_valid(u, v) { return Err(PIXEL_ERROR); }
        result[2*i] = u;
        result[2*i+1] = v;
        Ok(())
    }, &mut cancelled)?;
    if valid_context == 0 { return Err(CONTEXT_ERROR); }
    poll(&mut cancelled)?;
    // Final publication is one non-cancellable copy after all fallible work.
    output.copy_from_slice(&result);
    Ok(())
}

#[test]
fn refactored_legacy_prepare_matches_pre_extension_oracle_without_arithmetic_changes() {
    for (u, v) in [(0.45, -0.5), (0.15, -0.25)] {
        let (source, mut coverage) = scene(u, v);
        for yy in 0..H { for xx in 0..W/5 { coverage[yy*W+xx] = 0.0; } }
        for amount in [0.0, 0.25, 1.0] {
            let mut old = vec![42.0; W*H*2]; let mut new = old.clone();
            let (mut old_polls, mut new_polls) = (0, 0);
            let before = pre_extension_prepare_into(&source, &coverage, W, H, amount, R, &mut old,
                || { old_polls += 1; false });
            let after = prepare_into(&source, &coverage, W, H, amount, R, &mut new,
                || { new_polls += 1; false });
            assert_eq!(before, Ok(())); assert_eq!(before, after);
            assert!(bits(&old, &new)); assert_eq!(old_polls, new_polls);
            for stop in [1, 10, old_polls] {
                old.fill(42.0); new.fill(42.0);
                let (mut a, mut b) = (0, 0);
                let before = pre_extension_prepare_into(&source, &coverage, W, H, amount, R, &mut old,
                    || { a += 1; a >= stop });
                let after = prepare_into(&source, &coverage, W, H, amount, R, &mut new,
                    || { b += 1; b >= stop });
                assert_eq!(before, Err(CANCELLED)); assert_eq!(before, after);
                assert!(bits(&old, &new)); assert!(new.iter().all(|&v| v == 42.0));
            }
        }
        for sparse in [vec![0.0; W*H], vec![0.01; W*H]] {
            let mut old = vec![42.0; W*H*2]; let mut new = old.clone();
            let before = pre_extension_prepare_into(&source, &sparse, W, H, 1.0, R, &mut old, || false);
            let after = prepare_into(&source, &sparse, W, H, 1.0, R, &mut new, || false);
            assert_eq!(before, Err(REFERENCE_ERROR)); assert_eq!(before, after); assert!(bits(&old, &new));
        }
    }
}
