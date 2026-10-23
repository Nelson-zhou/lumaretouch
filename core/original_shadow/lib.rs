// SPDX-License-Identifier: GPL-3.0-or-later
//! Original reviewed uniform-floor photographed-shadow estimator. ABI 1.
//! SOURCE ONLY: authored fixtures are UNRUN. No neural model or AI claim.
//! Straight finite linear-sRGB-D65 SDR input on one immutable source grid.
//! This estimates achromatic attenuation, not foreground alpha or a silhouette.
//! Same-colour dark albedo can be indistinguishable from a photographed shadow.
//! Read README.md for review requirements, bounds and output ownership.

use std::{mem, slice};

pub const MAX_PIXELS: usize = 32_000_000;
pub const MAX_DIMENSION: usize = 65_536;
const MAX_REFERENCED_BYTES: usize = 1_073_741_824;
const POLL_PIXELS: usize = 4096;
const HISTOGRAM_BINS: usize = 1024;
const MIN_EFFECTIVE_SAMPLES: f64 = 64.0;
const MIN_SAMPLE_WEIGHT: f64 = 32.0;
const SAMPLE_ALPHA_MAX: f32 = 0.001;
const LIT_CHANNEL_CEILING: f32 = 0.995;
const SHADOW_ALPHA_LIMIT: f32 = 0.02;
const MIN_FLOOR_LUMINANCE: f64 = 0.025;
const MAX_RELATIVE_LUMA_RMS: f64 = 0.04;
const MAX_RELATIVE_CHROMA_RMS: f64 = 0.03;
const MAX_SAMPLE_TAIL_WEIGHT: f64 = 0.02;
const LUMA: [f64; 3] = [0.2126, 0.7152, 0.0722];

const ABI_ERROR: i32 = 1;
const PIXEL_ERROR: i32 = 2;
const CANCELLED: i32 = 3;
const RESOURCE_ERROR: i32 = 4;
const SUPPORT_ERROR: i32 = 5;
const DARK_FLOOR_ERROR: i32 = 6;
const NONUNIFORM_FLOOR_ERROR: i32 = 7;

type Cancel = Option<extern "C" fn() -> i32>;
type Rgb = [f64; 3];

#[derive(Clone, Copy)]
struct Floor {
    colour: Rgb,
    square_norm: f64,
    relative_luma_rms: f64,
    relative_chroma_rms: f64,
}

fn poll(cancel: Cancel) -> Result<(), i32> {
    if cancel.map_or(false, |f| f() != 0) { Err(CANCELLED) } else { Ok(()) }
}

fn checked_count(w: usize, h: usize) -> Result<usize, i32> {
    if w == 0 || h == 0 || w > MAX_DIMENSION || h > MAX_DIMENSION {
        return Err(ABI_ERROR);
    }
    let n = w.checked_mul(h).ok_or(ABI_ERROR)?;
    // Both entry points reference seven f32 scalars per pixel in total.
    let bytes = n.checked_mul(7).and_then(|v| v.checked_mul(mem::size_of::<f32>()))
        .and_then(|v| v.checked_add(3 * HISTOGRAM_BINS * mem::size_of::<f64>()))
        .ok_or(RESOURCE_ERROR)?;
    if n > MAX_PIXELS || bytes > MAX_REFERENCED_BYTES { return Err(RESOURCE_ERROR); }
    Ok(n)
}

// Checking a span cannot prove that the caller actually allocated that memory.
// The C caller remains responsible for accessible extents and lifetimes.
fn region(pointer: *const f32, length: usize) -> Option<(usize, usize)> {
    let start = pointer as usize;
    let bytes = length.checked_mul(mem::size_of::<f32>())?;
    if pointer.is_null() || start % mem::align_of::<f32>() != 0
        || bytes > isize::MAX as usize {
        return None;
    }
    Some((start, start.checked_add(bytes)?))
}

fn overlaps(a: (usize, usize), b: (usize, usize)) -> bool {
    a.0 < b.1 && b.0 < a.1
}

fn valid_unit(value: f32) -> bool { value.is_finite() && (0.0..=1.0).contains(&value) }
fn rgb(source: &[f32], i: usize) -> Rgb {
    [source[3 * i] as f64, source[3 * i + 1] as f64, source[3 * i + 2] as f64]
}
fn dot(a: Rgb, b: Rgb) -> f64 { a[0] * b[0] + a[1] * b[1] + a[2] * b[2] }
fn norm(a: Rgb) -> f64 { dot(a, a).sqrt() }
fn difference(a: Rgb, b: Rgb) -> Rgb { [a[0] - b[0], a[1] - b[1], a[2] - b[2]] }
fn scale(a: Rgb, s: f64) -> Rgb { [a[0] * s, a[1] * s, a[2] * s] }
fn smoothstep(low: f64, high: f64, value: f64) -> f64 {
    let t = ((value - low) / (high - low)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

fn sample_weight(alpha: f32, coverage: f32, retention: f32, value: Rgb) -> f64 {
    // Even feathered selection overlap is excluded. A selected shadow must not
    // contaminate its own "lit" baseline merely because two paths intersect.
    // Near-saturation is not a reliable radiometric reference. Reject a sample
    // when ANY channel reaches the conservative ceiling, even on coloured floors.
    if alpha <= SAMPLE_ALPHA_MAX && retention == 0.0
        && value.iter().all(|&channel| channel < LIT_CHANNEL_CEILING as f64) {
        coverage as f64 * (1.0 - alpha as f64)
    } else {
        0.0
    }
}

fn supported(sum: f64, square_sum: f64) -> bool {
    sum >= MIN_SAMPLE_WEIGHT && square_sum > 0.0
        && sum * sum / square_sum >= MIN_EFFECTIVE_SAMPLES
}

fn weighted_median(histogram: &[f64; HISTOGRAM_BINS], total: f64) -> f64 {
    let mut cumulative = 0.0;
    for (index, &weight) in histogram.iter().enumerate() {
        cumulative += weight;
        if cumulative >= 0.5 * total {
            return (index as f64 + 0.5) / HISTOGRAM_BINS as f64;
        }
    }
    // Only reached for a rounding-sized accumulation difference at the end.
    (HISTOGRAM_BINS as f64 - 0.5) / HISTOGRAM_BINS as f64
}

fn clear(output: &mut [f32], cancel: Cancel) -> Result<(), i32> {
    for chunk in output.chunks_mut(POLL_PIXELS) {
        poll(cancel)?;
        chunk.fill(0.0);
    }
    poll(cancel)
}

// Robustly refine a histogram-median RGB seed, then test the ORIGINAL selected
// distribution. Robust fitting may not silently trim an unsuitable sample set.
fn fit_floor(source: &[f32], alpha: &[f32], lit: &[f32], retention: &[f32], mut colour: Rgb,
             total_weight: f64, cancel: Cancel) -> Result<Floor, i32> {
    for _ in 0..2 {
        let magnitude = norm(colour).max(MIN_FLOOR_LUMINANCE);
        let mut sum = [0.0; 3];
        let mut weight_sum = 0.0;
        let mut weight_square_sum = 0.0;
        for i in 0..alpha.len() {
            if i % POLL_PIXELS == 0 { poll(cancel)?; }
            let colour_i = rgb(source, i);
            let weight = sample_weight(alpha[i], lit[i], retention[i], colour_i);
            if weight == 0.0 { continue; }
            let relative_distance = norm(difference(colour_i, colour)) / magnitude;
            let robust_weight = weight * if relative_distance <= 0.04 {
                1.0
            } else {
                0.04 / relative_distance
            };
            for channel in 0..3 { sum[channel] += robust_weight * colour_i[channel]; }
            weight_sum += robust_weight;
            weight_square_sum += robust_weight * robust_weight;
        }
        poll(cancel)?;
        if !supported(weight_sum, weight_square_sum) { return Err(SUPPORT_ERROR); }
        for channel in 0..3 { colour[channel] = sum[channel] / weight_sum; }
    }

    let luminance = dot(colour, LUMA);
    if luminance < MIN_FLOOR_LUMINANCE { return Err(DARK_FLOOR_ERROR); }
    let square_norm = dot(colour, colour);
    let magnitude = square_norm.sqrt();
    let mut luma_square = 0.0;
    let mut chroma_square = 0.0;
    let mut tail_weight = 0.0;
    for i in 0..alpha.len() {
        if i % POLL_PIXELS == 0 { poll(cancel)?; }
        let value = rgb(source, i);
        let weight = sample_weight(alpha[i], lit[i], retention[i], value);
        if weight == 0.0 { continue; }
        let relative_luma = (dot(value, LUMA) - luminance).abs() / luminance;
        let projection = dot(value, colour) / square_norm;
        let relative_chroma = norm(difference(value, scale(colour, projection))) / magnitude;
        luma_square += weight * relative_luma * relative_luma;
        chroma_square += weight * relative_chroma * relative_chroma;
        if relative_luma > 0.08 || relative_chroma > 0.05 { tail_weight += weight; }
    }
    poll(cancel)?;
    let relative_luma_rms = (luma_square / total_weight).sqrt();
    let relative_chroma_rms = (chroma_square / total_weight).sqrt();
    if relative_luma_rms > MAX_RELATIVE_LUMA_RMS
        || relative_chroma_rms > MAX_RELATIVE_CHROMA_RMS
        || tail_weight > MAX_SAMPLE_TAIL_WEIGHT * total_weight {
        return Err(NONUNIFORM_FLOOR_ERROR);
    }
    Ok(Floor { colour, square_norm, relative_luma_rms, relative_chroma_rms })
}

fn estimate_pixel(value: Rgb, alpha: f32, retention: f32, floor: Floor) -> f32 {
    if retention == 0.0 || alpha >= SHADOW_ALPHA_LIMIT { return 0.0; }
    // Zero-offset, achromatic least-squares transmittance relative to the actual
    // lit-floor RGB. Not a six-parameter affine model or an albedo decomposition.
    let transmittance = dot(value, floor.colour) / floor.square_norm;
    if transmittance <= 0.08 || transmittance >= 1.0 { return 0.0; }
    let predicted = scale(floor.colour, transmittance);
    let relative_chroma = norm(difference(value, predicted)) / norm(predicted).max(0.02);
    let chroma_full = (2.0 * floor.relative_chroma_rms).max(0.015);
    let chroma_zero = (4.0 * floor.relative_chroma_rms).max(0.04);
    if relative_chroma >= chroma_zero { return 0.0; }
    let attenuation = 1.0 - transmittance;
    let noise_floor = (3.0 * floor.relative_luma_rms).max(0.01);
    if attenuation <= noise_floor { return 0.0; }

    let chroma_gate = 1.0 - smoothstep(chroma_full, chroma_zero, relative_chroma);
    let noise_gate = smoothstep(noise_floor, 2.0 * noise_floor, attenuation);
    // Near-black measurements cannot reliably identify attenuation or material.
    let dark_gate = smoothstep(0.08, 0.15, transmittance);
    // Alpha is an eligibility exclusion above, NOT a second opacity factor.
    // The parent composites the subject over this shaded background once.
    // Contact/edge shadows under excluded mixed coverage are not recovered.
    (attenuation * retention as f64 * chroma_gate * noise_gate * dark_gate) as f32
}

#[no_mangle]
pub extern "C" fn lrt_original_shadow_abi() -> u32 { 1 }

/// Prepare a complete source-owned scalar black-shadow opacity plane.
/// Always prepare the full effective source, including for previews. Only reduce
/// the completed shaded replacement background for display, never estimator inputs.
/// Inputs: RGB length 3*w*h; reviewed alpha, lit samples, retention and output
/// each length w*h. All four inputs must already be on the exact same grid.
/// The caller must authenticate source identity, alpha review, homogeneous-floor
/// suitability and masks. The kernel cannot inspect review receipts.
///
/// # Safety
/// All pointers must be aligned, valid for the declared extents, immutable for
/// inputs and exclusively writable for output throughout the call. Output must
/// be disjoint from every input. Callback must not unwind, reenter this call or
/// mutate/free any referenced buffer. Dimensions do not prove source identity.
/// Any nonzero result invalidates the ENTIRE output; cancellation may leave a
/// partial buffer. Never install/cache/display output until success and a final
/// caller-side cancellation/source-generation check.
#[no_mangle]
pub unsafe extern "C" fn lrt_original_shadow_prepare(
    source: *const f32, source_len: usize,
    alpha: *const f32, alpha_len: usize,
    lit_samples: *const f32, lit_len: usize,
    retention: *const f32, retention_len: usize,
    out: *mut f32, out_len: usize,
    w: usize, h: usize, cancel: Cancel,
) -> i32 {
    let n = match checked_count(w, h) { Ok(n) => n, Err(code) => return code };
    if source_len != 3 * n || alpha_len != n || lit_len != n || retention_len != n || out_len != n {
        return ABI_ERROR;
    }
    let output_region = match region(out as *const f32, out_len) {
        Some(value) => value, None => return ABI_ERROR,
    };
    for (pointer, length) in [(source, source_len), (alpha, alpha_len),
                             (lit_samples, lit_len), (retention, retention_len)] {
        let input_region = match region(pointer, length) { Some(value) => value, None => return ABI_ERROR };
        if overlaps(input_region, output_region) { return ABI_ERROR; }
    }
    let image = slice::from_raw_parts(source, source_len);
    let matte = slice::from_raw_parts(alpha, alpha_len);
    let lit = slice::from_raw_parts(lit_samples, lit_len);
    let keep = slice::from_raw_parts(retention, retention_len);
    let output = slice::from_raw_parts_mut(out, out_len);
    let result = (|| -> Result<(), i32> {
        let mut histograms = [[0.0f64; HISTOGRAM_BINS]; 3];
        let mut weight_sum = 0.0;
        let mut weight_square_sum = 0.0;
        let mut eligible_retention = false;
        // Validate EVERYTHING even when the eventual operation is neutral.
        // Work is polled by pixel count, not potentially huge image rows.
        for i in 0..n {
            if i % POLL_PIXELS == 0 { poll(cancel)?; }
            if !valid_unit(matte[i]) || !valid_unit(lit[i]) || !valid_unit(keep[i])
                || !image[3 * i..3 * i + 3].iter().copied().all(valid_unit) {
                return Err(PIXEL_ERROR);
            }
            eligible_retention |= keep[i] > 0.0 && matte[i] < SHADOW_ALPHA_LIMIT;
            let weight = sample_weight(matte[i], lit[i], keep[i], rgb(image, i));
            if weight == 0.0 { continue; }
            weight_sum += weight;
            weight_square_sum += weight * weight;
            for channel in 0..3 {
                let bin = ((image[3 * i + channel] as f64 * HISTOGRAM_BINS as f64) as usize)
                    .min(HISTOGRAM_BINS - 1);
                histograms[channel][bin] += weight;
            }
        }
        poll(cancel)?;
        // Includes an exactly opaque reviewed matte and empty retention. Do not
        // demand a floor fit when no pixel can receive a shadow in this result.
        if !eligible_retention { return clear(output, cancel); }
        if !supported(weight_sum, weight_square_sum) { return Err(SUPPORT_ERROR); }
        let seed = [weighted_median(&histograms[0], weight_sum),
                    weighted_median(&histograms[1], weight_sum),
                    weighted_median(&histograms[2], weight_sum)];
        if dot(seed, LUMA) < MIN_FLOOR_LUMINANCE { return Err(DARK_FLOOR_ERROR); }
        let floor = fit_floor(image, matte, lit, keep, seed, weight_sum, cancel)?;
        for i in 0..n {
            if i % POLL_PIXELS == 0 { poll(cancel)?; }
            output[i] = estimate_pixel(rgb(image, i), matte[i], keep[i], floor);
        }
        poll(cancel)
    })();
    match result { Ok(()) => 0, Err(code) => code }
}

fn black_blend(backdrop: f64, mode: u32) -> f64 {
    match mode {
        0 => 0.0,                        // Normal: source black.
        1 => backdrop * 0.0,             // Multiply: backdrop * source.
        _ => backdrop - backdrop * (1.0 - backdrop), // Soft Light, source=0.
    }
}

/// Apply the prepared achromatic black layer to a replacement linear background.
/// Modes: 0 Normal, 1 Multiply, 2 Soft Light. Normal and Multiply coincide for a
/// black source; Soft Light is not linear attenuation. No alpha is returned.
/// `opacity` is user strength and is applied exactly once to prepared coverage.
/// Full-source and exact-coordinate cropped tile calls use the same pointwise
/// formula. Never estimate independently on a crop or substitute a preview map.
///
/// # Safety
/// RGB input/output each length 3*w*h, scalar shadow length w*h. Follow the same
/// pointer, callback, disjoint-output and discard-on-nonzero rules as prepare.
/// All inputs, including the replacement background, must be finite SDR [0,1].
/// This ABI rejects unsupported HDR rather than clipping it into this model.
#[no_mangle]
pub unsafe extern "C" fn lrt_original_shadow_apply(
    background: *const f32, background_len: usize,
    shadow: *const f32, shadow_len: usize,
    out: *mut f32, out_len: usize,
    w: usize, h: usize, opacity: f32, mode: u32, cancel: Cancel,
) -> i32 {
    let n = match checked_count(w, h) { Ok(n) => n, Err(code) => return code };
    if background_len != 3 * n || shadow_len != n || out_len != 3 * n
        || !valid_unit(opacity) || mode > 2 { return ABI_ERROR; }
    let output_region = match region(out as *const f32, out_len) {
        Some(value) => value, None => return ABI_ERROR,
    };
    for (pointer, length) in [(background, background_len), (shadow, shadow_len)] {
        let input_region = match region(pointer, length) { Some(value) => value, None => return ABI_ERROR };
        if overlaps(input_region, output_region) { return ABI_ERROR; }
    }
    let image = slice::from_raw_parts(background, background_len);
    let coverage = slice::from_raw_parts(shadow, shadow_len);
    let output = slice::from_raw_parts_mut(out, out_len);
    let result = (|| -> Result<(), i32> {
        for i in 0..n {
            if i % POLL_PIXELS == 0 { poll(cancel)?; }
            if !valid_unit(coverage[i])
                || !image[3 * i..3 * i + 3].iter().copied().all(valid_unit) {
                return Err(PIXEL_ERROR);
            }
        }
        poll(cancel)?;
        for i in 0..n {
            if i % POLL_PIXELS == 0 { poll(cancel)?; }
            let q = coverage[i] as f64 * opacity as f64;
            if q == 0.0 {
                output[3 * i..3 * i + 3].copy_from_slice(&image[3 * i..3 * i + 3]);
                continue;
            }
            for channel in 0..3 {
                let index = 3 * i + channel;
                let backdrop = image[index] as f64;
                output[index] = ((1.0 - q) * backdrop + q * black_blend(backdrop, mode)) as f32;
            }
        }
        poll(cancel)
    })();
    match result { Ok(()) => 0, Err(code) => code }
}

#[cfg(test)]
mod unrun_authored_tests {
    // Authored source fixtures ONLY. No compiler, imports or tests were run.
    use super::*;

    fn scene() -> (Vec<f32>, Vec<f32>, Vec<f32>, Vec<f32>) {
        let mut source = vec![0.8f32; 128 * 3];
        let alpha = vec![0.0f32; 128];
        let mut lit = vec![0.0f32; 128];
        let mut retention = vec![0.0f32; 128];
        lit[..96].fill(1.0);
        retention[96..].fill(1.0);
        source[96 * 3..].fill(0.4);
        (source, alpha, lit, retention)
    }

    fn prepare(source: &[f32], alpha: &[f32], lit: &[f32], retention: &[f32], output: &mut [f32]) -> i32 {
        unsafe { lrt_original_shadow_prepare(source.as_ptr(), source.len(), alpha.as_ptr(), alpha.len(),
            lit.as_ptr(), lit.len(), retention.as_ptr(), retention.len(), output.as_mut_ptr(), output.len(),
            16, 8, None) }
    }

    fn apply(background: &[f32], shadow: &[f32], opacity: f32, mode: u32, output: &mut [f32]) -> i32 {
        unsafe { lrt_original_shadow_apply(background.as_ptr(), background.len(), shadow.as_ptr(), shadow.len(),
            output.as_mut_ptr(), output.len(), shadow.len(), 1, opacity, mode, None) }
    }

    #[test]
    fn exact_uniform_floor_recovers_observed_ratio_without_alpha_changes() {
        let (source, alpha, lit, retention) = scene();
        let before = alpha.clone();
        let mut output = vec![-7.0; 128];
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), 0);
        assert!(output[..96].iter().all(|&v| v == 0.0));
        assert!(output[96..].iter().all(|&v| (v - 0.5).abs() < 1e-6));
        assert_eq!(alpha, before);
    }

    #[test]
    fn coloured_floor_uses_actual_rgb_projection() {
        let (mut source, alpha, lit, retention) = scene();
        for pixel in source[..96 * 3].chunks_exact_mut(3) { pixel.copy_from_slice(&[0.8, 0.6, 0.4]); }
        for pixel in source[96 * 3..].chunks_exact_mut(3) { pixel.copy_from_slice(&[0.4, 0.3, 0.2]); }
        let mut output = vec![0.0; 128];
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), 0);
        assert!((output[100] - 0.5).abs() < 1e-6);
    }

    #[test]
    fn constant_lit_sample_weights_are_respected() {
        let (source, alpha, mut lit, retention) = scene();
        lit[..96].fill(0.5);
        let mut output = vec![0.0; 128];
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), 0);
        assert!((output[100] - 0.5).abs() < 1e-6);
    }

    #[test]
    fn retention_without_observed_darkening_is_exactly_neutral() {
        let (mut source, alpha, lit, retention) = scene();
        source.fill(0.8);
        let mut output = vec![0.7; 128];
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), 0);
        assert!(output.iter().all(|&v| v == 0.0));
    }

    #[test]
    fn saturated_only_lit_references_are_not_a_reliable_baseline() {
        let (mut source, alpha, lit, retention) = scene();
        let mut output = vec![-9.0; 128];
        source[..96 * 3].fill(1.0);
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), SUPPORT_ERROR);
        // One clipped channel is enough to invalidate a coloured reference.
        for pixel in source[..96 * 3].chunks_exact_mut(3) { pixel.copy_from_slice(&[1.0, 0.8, 0.6]); }
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), SUPPORT_ERROR);
        source[..96 * 3].fill(LIT_CHANNEL_CEILING);
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), SUPPORT_ERROR);
        assert!(output.iter().all(|&v| v == -9.0));
    }

    #[test]
    fn saturated_lit_pixels_are_excluded_when_independent_support_remains() {
        let (mut source, alpha, lit, retention) = scene();
        source[..32 * 3].fill(1.0);
        let mut output = vec![0.0; 128];
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), 0);
        assert!((output[100] - 0.5).abs() < 1e-6);
    }

    #[test]
    fn overlapped_shadow_pixels_cannot_contaminate_lit_fit() {
        let (mut source, alpha, lit, mut retention) = scene();
        retention[64..].fill(1.0);
        source[64 * 3..].fill(0.4);
        let mut output = vec![0.0; 128];
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), 0);
        assert!((output[80] - 0.5).abs() < 1e-6);
        assert!((output[100] - 0.5).abs() < 1e-6);
        retention[..96].fill(0.01);
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), SUPPORT_ERROR);
    }

    #[test]
    fn retention_and_foreground_are_gates_not_shadow_sources() {
        let (mut source, mut alpha, lit, mut retention) = scene();
        alpha[98] = 1.0;
        alpha[99] = 0.02;
        alpha[102] = 0.01;
        retention[100] = 0.5;
        source[101 * 3..102 * 3].fill(0.8);
        let mut output = vec![0.0; 128];
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), 0);
        assert_eq!(output[98], 0.0);
        assert_eq!(output[99], 0.0);
        assert!((output[100] - 0.25).abs() < 1e-6);
        assert_eq!(output[101], 0.0);
        // Do not multiply by (1-alpha) again before the parent's source-over.
        assert!((output[102] - 0.5).abs() < 1e-6);
    }

    #[test]
    fn opaque_matte_has_exact_neutral_bypass_without_lit_support() {
        let (source, mut alpha, mut lit, retention) = scene();
        alpha.fill(1.0);
        lit.fill(0.0);
        let mut output = vec![0.7; 128];
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), 0);
        assert!(output.iter().all(|&v| v.to_bits() == 0.0f32.to_bits()));
    }

    #[test]
    fn insufficient_floor_support_does_not_overwrite_output() {
        let (source, alpha, mut lit, retention) = scene();
        lit.fill(0.0);
        lit[..63].fill(1.0);
        let mut output = vec![-9.0; 128];
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), SUPPORT_ERROR);
        assert!(output.iter().all(|&v| v == -9.0));
    }

    #[test]
    fn foreground_samples_do_not_count_as_floor_support() {
        let (source, mut alpha, lit, retention) = scene();
        alpha[..96].fill(0.5);
        let mut output = vec![-9.0; 128];
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), SUPPORT_ERROR);
    }

    #[test]
    fn dark_floor_and_nonuniform_floor_are_refused() {
        let (mut source, alpha, lit, retention) = scene();
        source[..96 * 3].fill(0.01);
        let mut output = vec![-9.0; 128];
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), DARK_FLOOR_ERROR);
        source[..48 * 3].fill(0.75);
        source[48 * 3..96 * 3].fill(0.85);
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), NONUNIFORM_FLOOR_ERROR);
        assert!(output.iter().all(|&v| v == -9.0));
    }

    #[test]
    fn coloured_residual_near_black_and_near_lit_pixels_abstain() {
        let (mut source, alpha, lit, retention) = scene();
        source[96 * 3..97 * 3].copy_from_slice(&[0.4, 0.2, 0.4]);
        source[97 * 3..98 * 3].fill(0.01);
        source[98 * 3..99 * 3].fill(0.796);
        source[99 * 3..100 * 3].fill(0.9);
        let mut output = vec![-1.0; 128];
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), 0);
        assert_eq!(&output[96..100], &[0.0, 0.0, 0.0, 0.0]);
    }

    #[test]
    fn same_colour_dark_albedo_is_not_automatically_disambiguated() {
        // Exactly the same source values can describe a shadow or a dark patch.
        // This intentional limitation requires applicability and result review.
        let (source, alpha, lit, retention) = scene();
        let mut output = vec![0.0; 128];
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), 0);
        assert!(output[100] > 0.0);
    }

    #[test]
    fn hdr_nan_and_bad_lengths_fail_closed_even_for_neutral_calls() {
        let (mut source, mut alpha, lit, retention) = scene();
        alpha.fill(1.0);
        let mut output = vec![-9.0; 128];
        source[0] = 1.01;
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), PIXEL_ERROR);
        source[0] = f32::NAN;
        assert_eq!(prepare(&source, &alpha, &lit, &retention, &mut output), PIXEL_ERROR);
        assert_eq!(prepare(&source[..source.len() - 1], &alpha, &lit, &retention, &mut output), ABI_ERROR);
        assert!(output.iter().all(|&v| v == -9.0));
        let mut rgb_out = [7.0; 3];
        assert_eq!(apply(&[1.1, 0.0, 0.0], &[0.0], 0.0, 0, &mut rgb_out), PIXEL_ERROR);
        assert_eq!(rgb_out, [7.0; 3]);
    }

    #[test]
    fn normal_and_multiply_coincide_while_soft_light_differs() {
        let background = [0.2, 0.5, 0.8];
        let shadow = [0.5];
        let mut normal = [0.0; 3];
        let mut multiply = [0.0; 3];
        let mut soft = [0.0; 3];
        assert_eq!(apply(&background, &shadow, 1.0, 0, &mut normal), 0);
        assert_eq!(apply(&background, &shadow, 1.0, 1, &mut multiply), 0);
        assert_eq!(apply(&background, &shadow, 1.0, 2, &mut soft), 0);
        assert_eq!(normal, multiply);
        for c in 0..3 { assert!((normal[c] - 0.5 * background[c]).abs() < 1e-6); }
        assert!((soft[1] - 0.375).abs() < 1e-6);
        assert_ne!(normal, soft);
    }

    #[test]
    fn zero_strength_and_zero_shadow_are_bit_exact_including_signed_zero() {
        let background = [-0.0f32, 0.12345679, 1.0];
        for mode in 0..=2 {
            let mut output = [7.0; 3];
            assert_eq!(apply(&background, &[0.8], 0.0, mode, &mut output), 0);
            for c in 0..3 { assert_eq!(output[c].to_bits(), background[c].to_bits()); }
            assert_eq!(apply(&background, &[0.0], 1.0, mode, &mut output), 0);
            for c in 0..3 { assert_eq!(output[c].to_bits(), background[c].to_bits()); }
        }
    }

    #[test]
    fn apply_is_pointwise_and_crop_equivalent() {
        let background = [0.2, 0.3, 0.4, 0.7, 0.6, 0.5];
        let shadow = [0.2, 0.7];
        let mut whole = [0.0; 6];
        let mut tile = [0.0; 3];
        assert_eq!(apply(&background, &shadow, 0.6, 2, &mut whole), 0);
        assert_eq!(apply(&background[3..], &shadow[1..], 0.6, 2, &mut tile), 0);
        assert_eq!(&whole[3..], &tile);
    }

    extern "C" fn stop_now() -> i32 { 1 }

    #[test]
    fn cancellation_is_explicit_and_output_is_not_a_result() {
        let (source, alpha, lit, retention) = scene();
        let mut output = vec![-9.0; 128];
        let status = unsafe { lrt_original_shadow_prepare(
            source.as_ptr(), source.len(), alpha.as_ptr(), alpha.len(), lit.as_ptr(), lit.len(),
            retention.as_ptr(), retention.len(), output.as_mut_ptr(), output.len(), 16, 8, Some(stop_now)) };
        assert_eq!(status, CANCELLED);
        assert!(output.iter().all(|&v| v == -9.0));
    }

    static LATE_CANCEL_POLLS: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);

    extern "C" fn stop_after_four_polls() -> i32 {
        (LATE_CANCEL_POLLS.fetch_add(1, std::sync::atomic::Ordering::Relaxed) >= 4) as i32
    }

    #[test]
    fn cancelled_partial_neutral_output_must_be_discarded() {
        let n = 8192;
        let source = vec![0.8f32; 3 * n];
        let alpha = vec![1.0f32; n];
        let lit = vec![0.0f32; n];
        let retention = vec![1.0f32; n];
        let mut output = vec![-9.0f32; n];
        LATE_CANCEL_POLLS.store(0, std::sync::atomic::Ordering::Relaxed);
        // Two validation polls + validation-end + first clear chunk are allowed.
        // The second clear chunk is cancelled: this is deliberately NOT atomic.
        let status = unsafe { lrt_original_shadow_prepare(
            source.as_ptr(), source.len(), alpha.as_ptr(), alpha.len(), lit.as_ptr(), lit.len(),
            retention.as_ptr(), retention.len(), output.as_mut_ptr(), output.len(), n, 1,
            Some(stop_after_four_polls)) };
        assert_eq!(status, CANCELLED);
        assert!(output[..POLL_PIXELS].iter().all(|&v| v == 0.0));
        assert!(output[POLL_PIXELS..].iter().all(|&v| v == -9.0));
    }

    #[test]
    fn null_overlapping_spans_and_resource_excess_are_rejected() {
        let mut background = [0.2, 0.3, 0.4];
        let shadow = [0.5];
        let status = unsafe { lrt_original_shadow_apply(
            background.as_ptr(), 3, shadow.as_ptr(), 1, background.as_mut_ptr(), 3, 1, 1, 1.0, 0, None) };
        assert_eq!(status, ABI_ERROR);
        let status = unsafe { lrt_original_shadow_apply(
            std::ptr::null(), 3, shadow.as_ptr(), 1, background.as_mut_ptr(), 3, 1, 1, 1.0, 0, None) };
        assert_eq!(status, ABI_ERROR);
        assert_eq!(checked_count(0, 1), Err(ABI_ERROR));
        assert_eq!(checked_count(8192, 4096), Err(RESOURCE_ERROR));
        assert_eq!(checked_count(usize::MAX, 2), Err(ABI_ERROR));
    }
}
