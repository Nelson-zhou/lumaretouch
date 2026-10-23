// SPDX-License-Identifier: GPL-3.0-or-later
//! Original supported-rank eye-white purification. AUTHORED / UNRUN.
//! Encoded working-sRGB SDR RGB, ONE source-owned eye ROI and real coverage.
//! Not a sclera detector, global brightener, vein-removal alias or AI model.

use std::{ffi::c_void, mem, panic, slice};

pub const MAX_PIXELS: usize = 64_000_000;
pub const MAX_DIMENSION: usize = 65_536;
pub const MAX_RADIUS: usize = 32;
pub const DONOR_COVERAGE: f32 = 0.75;
pub const MAX_NEIGHBOUR_VISITS: usize = 64_000_000;
pub const POLL_PIXELS: usize = 4096;
const MAX_WINDOW: usize = (2 * MAX_RADIUS + 1) * (2 * MAX_RADIUS + 1);
pub const ABI_ERROR: i32 = 1;
pub const SETTINGS_ERROR: i32 = 2;
pub const PIXEL_ERROR: i32 = 3;
pub const CANCELLED: i32 = 4;
pub const RESOURCE_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;
pub type Cancel = Option<extern "C" fn(*mut c_void) -> i32>;

fn unit(value: f32) -> bool {
    value.is_finite() && (0.0..=1.0).contains(&value)
}

fn admit(width: usize, height: usize, radius: usize) -> Result<usize, i32> {
    if width == 0 || height == 0 || width > MAX_DIMENSION || height > MAX_DIMENSION {
        return Err(ABI_ERROR);
    }
    if !(1..=MAX_RADIUS).contains(&radius) { return Err(SETTINGS_ERROR); }
    let pixels = width.checked_mul(height).ok_or(RESOURCE_ERROR)?;
    let side = radius * 2 + 1;
    let visits = pixels.checked_mul(side * side).ok_or(RESOURCE_ERROR)?;
    if pixels > MAX_PIXELS || visits > MAX_NEIGHBOUR_VISITS {
        return Err(RESOURCE_ERROR);
    }
    Ok(pixels)
}

fn decode(value: f64) -> f64 {
    if value <= 0.04045 { value / 12.92 }
    else { ((value + 0.055) / 1.055).powf(2.4) }
}

fn encode(value: f64) -> f32 {
    if value <= 0.0031308 { (12.92 * value) as f32 }
    else { (1.055 * value.powf(1.0 / 2.4) - 0.055) as f32 }
}

fn luminance(rgb: [f64; 3]) -> f64 {
    // Standard relative linear-sRGB Y. Coefficients sum to one.
    0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
}

fn smoothstep(low: f64, high: f64, value: f64) -> f64 {
    let t = ((value - low) / (high - low)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

#[derive(Clone, Copy)]
struct Sample { y: f64, weight: f64 }

/// Supported samples only: no padding, clamping, dilation or unmasked fallback.
/// The centre is excluded so a blemish cannot provide its own reference.
/// A missing quadrant or thin/weak support makes the whole operation a no-op.
fn reference(
    luma: &[f64], coverage: &[f32], width: usize, height: usize,
    x: usize, y: usize, radius: usize, scratch: &mut [Sample; MAX_WINDOW],
    work_since_poll: &mut usize, cancelled: &mut impl FnMut() -> bool,
) -> Result<Option<(f64, bool)>, i32> {
    let centre = luma[y * width + x];
    let threshold = 0.012 + 0.06 * centre;
    let mut length = 0;
    let mut weight_sum = 0.0;
    let mut quadrant_count = [0_usize; 4];
    let mut quadrant_weight = [0.0_f64; 4];
    let mut quadrant_brighter = [0.0_f64; 4];
    for sy in y.saturating_sub(radius)..=(y + radius).min(height - 1) {
        for sx in x.saturating_sub(radius)..=(x + radius).min(width - 1) {
            *work_since_poll += 1;
            if *work_since_poll >= POLL_PIXELS {
                *work_since_poll = 0;
                if cancelled() { return Err(CANCELLED); }
            }
            if sx == x && sy == y { continue; }
            let index = sy * width + sx;
            let weight = f64::from(coverage[index]);
            if coverage[index] < DONOR_COVERAGE { continue; }
            let sample_y = luma[index];
            scratch[length] = Sample { y: sample_y, weight };
            length += 1;
            weight_sum += weight;
            // Axial samples contribute to the reference, but cannot stand in
            // for missing diagonal support at a boundary or a structural edge.
            if sx != x && sy != y {
                let q = usize::from(sx > x) + 2 * usize::from(sy > y);
                quadrant_count[q] += 1;
                quadrant_weight[q] += weight;
                if sample_y > centre + threshold {
                    quadrant_brighter[q] += weight;
                }
            }
        }
    }
    let minimum_count = (radius * radius + 3) / 4;
    let minimum_weight = 0.125 * (radius * radius) as f64;
    if length < 8 || quadrant_count.iter().any(|&n| n < minimum_count)
        || quadrant_weight.iter().any(|&w| w < minimum_weight) {
        return Ok(None);
    }
    // sort_unstable is in-place. A fixed 4224-sample maximum bounds sorting
    // work between cancellation polls; the image-dependent scan is budgeted.
    scratch[..length].sort_unstable_by(|a, b| a.y.total_cmp(&b.y));
    let mut accumulated = 0.0;
    let mut median = scratch[length - 1].y;
    for sample in &scratch[..length] {
        accumulated += sample.weight;
        if accumulated >= 0.5 * weight_sum {
            median = sample.y;
            break;
        }
    }
    // A broad flat shadow or monotone edge cannot meet this directional gate:
    // at least 75% of supported weight in EVERY quadrant must be brighter.
    // A compact depression can; even then only a capped fraction is corrected.
    let compact = (0..4).all(|q| quadrant_brighter[q] >= 0.75 * quadrant_weight[q]);
    Ok(Some((median, compact)))
}

fn pixel(source: [f32; 3], coverage: f32, amount: f32, median: f64, compact: bool) -> [f32; 3] {
    if coverage == 0.0 || amount == 0.0 { return source; }
    let rgb = source.map(|v| decode(f64::from(v)));
    let y = luminance(rgb);
    if y == 0.0 { return source; }
    let threshold = 0.012 + 0.06 * y;
    let deficit = (median - y).max(0.0);
    let lift = if compact && y > 0.015 && deficit > threshold {
        (0.35 * (deficit - threshold)).min(0.045)
            * smoothstep(threshold, 2.0 * threshold, deficit)
    } else { 0.0 };
    let chroma = rgb[0].max(rgb[1]).max(rgb[2]) - rgb[0].min(rgb[1]).min(rgb[2]);
    if lift == 0.0 && chroma == 0.0 { return source; }
    // Chroma moves toward neutral at the ORIGINAL Y, independently of the
    // spatial lift decision. No spatial averaging of RGB or fine Y texture.
    let reduction = 0.45 * f64::from(amount);
    let neutral: [f64; 3] = rgb.map(|c| c + reduction * (y - c));
    // An equal linear offset adds precisely its size to Y. Gamut headroom is
    // computed BEFORE adding it, never recovered with a destructive RGB clip.
    let headroom = 1.0 - neutral[0].max(neutral[1]).max(neutral[2]);
    let delta = (f64::from(amount) * lift).min(headroom.max(0.0));
    std::array::from_fn(|channel| {
        let adjusted = neutral[channel] + delta;
        encode(rgb[channel] + f64::from(coverage) * (adjusted - rgb[channel]))
    })
}

/// Safe slice entrypoint. Inputs fully validate before output writes. Native
/// scratch is one f64 Y plane plus a fixed sample window. On ANY error the
/// caller discards ALL output; cancellation can leave a partly rendered buffer.
pub fn apply_into(
    source: &[f32], coverage: &[f32], width: usize, height: usize,
    amount: f32, radius: usize, output: &mut [f32],
    mut cancelled: impl FnMut() -> bool,
) -> Result<(), i32> {
    let pixels = admit(width, height, radius)?;
    let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
    if source.len() != channels || coverage.len() != pixels || output.len() != channels {
        return Err(ABI_ERROR);
    }
    if !unit(amount) { return Err(SETTINGS_ERROR); }
    if cancelled() { return Err(CANCELLED); }
    let mut has_coverage = false;
    for i in 0..pixels {
        if i % POLL_PIXELS == 0 && cancelled() { return Err(CANCELLED); }
        if !unit(coverage[i]) || !source[3*i..3*i+3].iter().copied().all(unit) {
            return Err(PIXEL_ERROR);
        }
        has_coverage |= coverage[i] > 0.0;
    }
    if amount == 0.0 || !has_coverage {
        for start in (0..channels).step_by(3 * POLL_PIXELS) {
            if cancelled() { return Err(CANCELLED); }
            let end = (start + 3 * POLL_PIXELS).min(channels);
            output[start..end].copy_from_slice(&source[start..end]);
        }
        if cancelled() { return Err(CANCELLED); }
        return Ok(());
    }
    let mut luma = Vec::new();
    luma.try_reserve_exact(pixels).map_err(|_| RESOURCE_ERROR)?;
    if cancelled() { return Err(CANCELLED); }
    for i in 0..pixels {
        if i % POLL_PIXELS == 0 && cancelled() { return Err(CANCELLED); }
        let value = if coverage[i] == 0.0 { 0.0 } else {
            luminance([decode(f64::from(source[3*i])), decode(f64::from(source[3*i+1])),
                decode(f64::from(source[3*i+2]))])
        };
        luma.push(value);
    }
    let mut scratch = [Sample { y: 0.0, weight: 0.0 }; MAX_WINDOW];
    let mut work_since_poll = 0;
    for i in 0..pixels {
        if i % POLL_PIXELS == 0 && cancelled() { return Err(CANCELLED); }
        let original = [source[3*i], source[3*i+1], source[3*i+2]];
        let adjusted = if coverage[i] == 0.0 { original } else {
            match reference(&luma, coverage, width, height, i % width, i / width,
                radius, &mut scratch, &mut work_since_poll, &mut cancelled)? {
                Some((median, compact)) => pixel(original, coverage[i], amount, median, compact),
                None => original,
            }
        };
        if !adjusted.iter().copied().all(unit) { return Err(PIXEL_ERROR); }
        output[3*i..3*i+3].copy_from_slice(&adjusted);
    }
    if cancelled() { return Err(CANCELLED); }
    Ok(())
}

// Arithmetic/alignment/overlap checks cannot prove allocation ownership.
fn span(pointer: *const f32, length: usize) -> Result<(usize, usize), i32> {
    let start = pointer as usize;
    let bytes = length.checked_mul(mem::size_of::<f32>()).ok_or(ABI_ERROR)?;
    if pointer.is_null() || start % mem::align_of::<f32>() != 0
        || bytes > isize::MAX as usize { return Err(ABI_ERROR); }
    Ok((start, start.checked_add(bytes).ok_or(ABI_ERROR)?))
}

fn overlaps(a: (usize, usize), b: (usize, usize)) -> bool { a.0 < b.1 && b.0 < a.1 }

#[no_mangle]
pub extern "C" fn lrt_sclera_purify_abi() -> u32 { 1 }

/// ABI 1: lengths are float32 elements, RGB is interleaved HWC.
/// # Safety
/// Inputs are live aligned readable allocations, immutable during the call.
/// Output is live exclusively writable and overlaps neither input. Read-only
/// input overlap is allowed. Callback/context remain valid; callback must not
/// unwind, reenter, or mutate buffers. Discard all output on nonzero status.
#[no_mangle]
pub unsafe extern "C" fn lrt_sclera_purify_apply_v1(
    source: *const f32, source_len: usize, coverage: *const f32, coverage_len: usize,
    width: usize, height: usize, amount: f32, radius: usize,
    output: *mut f32, output_len: usize, cancel: Cancel, context: *mut c_void,
) -> i32 {
    let result = panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(), i32> {
        let pixels = admit(width, height, radius)?;
        let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
        if source_len != channels || coverage_len != pixels || output_len != channels {
            return Err(ABI_ERROR);
        }
        if !unit(amount) { return Err(SETTINGS_ERROR); }
        let rgb_span = span(source, source_len)?;
        let mask_span = span(coverage, coverage_len)?;
        let output_span = span(output, output_len)?;
        if overlaps(rgb_span, output_span) || overlaps(mask_span, output_span) {
            return Err(ABI_ERROR);
        }
        let rgb = slice::from_raw_parts(source, source_len);
        let mask = slice::from_raw_parts(coverage, coverage_len);
        let out = slice::from_raw_parts_mut(output, output_len);
        apply_into(rgb, mask, width, height, amount, radius, out,
            || cancel.map_or(false, |function| function(context) != 0))
    }));
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

#[cfg(test)]
mod tests {
    // AUTHORED / UNRUN. These fixtures are not execution or acceptance evidence.
    use super::*;

    fn scene(width: usize, height: usize, colour: [f32; 3]) -> Vec<f32> {
        (0..width * height).flat_map(|_| colour).collect()
    }
    fn render(source: &[f32], mask: &[f32], width: usize, amount: f32, radius: usize) -> Vec<f32> {
        let mut result = vec![-1.0; source.len()];
        apply_into(source, mask, width, mask.len() / width, amount, radius, &mut result,
            || false).unwrap();
        result
    }
    fn bits(values: &[f32]) -> Vec<u32> { values.iter().map(|v| v.to_bits()).collect() }
    fn y_at(values: &[f32], i: usize) -> f64 {
        luminance([decode(f64::from(values[3*i])), decode(f64::from(values[3*i+1])),
            decode(f64::from(values[3*i+2]))])
    }

    #[test]
    fn neutral_and_outside_are_bit_exact_even_signed_zero() {
        let mut source = scene(9, 9, [0.7, 0.6, 0.5]);
        source[0] = -0.0;
        assert_eq!(bits(&source), bits(&render(&source, &[1.0; 81], 9, 0.0, 2)));
        assert_eq!(bits(&source), bits(&render(&source, &[-0.0; 81], 9, 1.0, 2)));
        let mut mask = [1.0; 81];
        mask[40] = 0.0;
        let result = render(&source, &mask, 9, 1.0, 2);
        assert_eq!(bits(&source[120..123]), bits(&result[120..123]));
    }

    #[test]
    fn isolated_dark_speck_is_partly_lifted_not_replaced() {
        let mut source = scene(9, 9, [0.8; 3]);
        source[120..123].copy_from_slice(&[0.55; 3]);
        let result = render(&source, &[1.0; 81], 9, 1.0, 2);
        let before = y_at(&source, 40);
        let after = y_at(&result, 40);
        assert!(after > before && after - before <= 0.045 + 1e-7);
        assert!(after - before < 0.35 * (y_at(&source, 39) - before));
        assert_eq!(bits(&source[117..120]), bits(&result[117..120]));
    }

    #[test]
    fn broad_plateau_step_and_ramp_luminance_are_preserved() {
        for ramp in [false, true] {
            let mut source = scene(17, 11, [0.0; 3]);
            for y in 0..11 { for x in 0..17 {
                let value = if ramp { 0.35 + 0.025 * x as f32 }
                    else if x < 8 { 0.45 } else { 0.8 };
                source[3*(y*17+x)..3*(y*17+x)+3].copy_from_slice(&[value; 3]);
            }}
            assert_eq!(bits(&source), bits(&render(&source, &[1.0; 187], 17, 1.0, 3)));
        }
    }

    #[test]
    fn chroma_reduces_without_changing_local_luminance_texture() {
        let mut source = scene(9, 9, [0.76, 0.68, 0.56]);
        // Fine alternating luminance remains below the dark-outlier gate.
        for i in 0..81 { if i % 2 == 0 {
            for c in 0..3 { source[3*i+c] += 0.003; }
        }}
        let result = render(&source, &[1.0; 81], 9, 1.0, 2);
        assert!(result[120] - result[122] < source[120] - source[122]);
        for i in 0..81 { assert!((y_at(&result, i) - y_at(&source, i)).abs() < 1e-7); }
    }

    #[test]
    fn unsupported_pixels_never_supply_reference_or_fallback() {
        let mut source = scene(9, 9, [1.0; 3]);
        let mut mask = [0.0; 81];
        mask[40] = 1.0;
        source[120..123].copy_from_slice(&[0.5, 0.4, 0.3]);
        assert_eq!(bits(&source), bits(&render(&source, &mask, 9, 1.0, 2)));
        let mut thin = [0.0; 81];
        for x in 0..9 { thin[4*9+x] = 1.0; }
        assert_eq!(bits(&source), bits(&render(&source, &thin, 9, 1.0, 2)));
        let mut full = [1.0; 81];
        full[40] = 0.0;
        let first = render(&source, &full, 9, 1.0, 2);
        let mut changed = source.clone();
        changed[120..123].copy_from_slice(&[0.0; 3]);
        let second = render(&changed, &full, 9, 1.0, 2);
        for i in 0..81 { if full[i] > 0.0 {
            assert_eq!(bits(&first[3*i..3*i+3]), bits(&second[3*i..3*i+3]));
        }}
    }

    #[test]
    fn weak_targets_cannot_supply_donors_but_may_receive_partial_correction() {
        let source = scene(9, 9, [0.76, 0.68, 0.56]);
        assert_eq!(bits(&source), bits(&render(&source, &[0.749; 81], 9, 1.0, 2)));
        let strong = render(&source, &[0.75; 81], 9, 1.0, 2);
        assert_ne!(bits(&source[120..123]), bits(&strong[120..123]));
        let mut speck = scene(9, 9, [0.8; 3]);
        speck[120..123].copy_from_slice(&[0.55; 3]);
        let mut mask = [1.0; 81];
        mask[40] = 0.5;
        let result = render(&speck, &mask, 9, 1.0, 2);
        assert!(result[120] > speck[120]);
        speck[120..123].copy_from_slice(&[0.0; 3]);
        let changed = render(&speck, &mask, 9, 1.0, 2);
        for i in 0..81 { if i != 40 {
            assert_eq!(bits(&result[3*i..3*i+3]), bits(&changed[3*i..3*i+3]));
        }}
    }

    #[test]
    fn coverage_composes_in_linear_light_and_result_is_finite() {
        let source = scene(9, 9, [0.76, 0.68, 0.56]);
        let full = render(&source, &[1.0; 81], 9, 1.0, 2);
        let mut mask = [1.0; 81];
        mask[40] = 0.5;
        let half = render(&source, &mask, 9, 1.0, 2);
        for c in 0..3 {
            let target = 0.5 * (decode(f64::from(source[120+c])) + decode(f64::from(full[120+c])));
            assert!((decode(f64::from(half[120+c])) - target).abs() < 1e-7);
        }
        for colour in [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0; 3], [0.0; 3]] {
            assert!(render(&scene(9, 9, colour), &[1.0; 81], 9, 1.0, 2).iter().copied().all(unit));
        }
    }

    #[test]
    fn malformed_inputs_reject_before_output_including_neutral() {
        for invalid in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, -0.01, 1.01] {
            let mut output = [42.0; 3];
            assert_eq!(apply_into(&[0.5, 0.5, invalid], &[0.0], 1, 1, 0.0, 1,
                &mut output, || false), Err(PIXEL_ERROR));
            assert_eq!(apply_into(&[0.5; 3], &[invalid], 1, 1, 0.0, 1,
                &mut output, || false), Err(PIXEL_ERROR));
            assert_eq!(apply_into(&[0.5; 3], &[1.0], 1, 1, invalid, 1,
                &mut output, || false), Err(SETTINGS_ERROR));
            assert_eq!(output, [42.0; 3]);
        }
    }

    #[test]
    fn dimensions_radius_work_and_lengths_are_bounded() {
        assert_eq!(admit(0, 1, 1), Err(ABI_ERROR));
        assert_eq!(admit(1, 1, 0), Err(SETTINGS_ERROR));
        assert_eq!(admit(1, 1, MAX_RADIUS + 1), Err(SETTINGS_ERROR));
        assert_eq!(admit(1, 1, MAX_RADIUS), Ok(1));
        assert_eq!(admit(1000, 1000, 12), Err(RESOURCE_ERROR));
        assert_eq!(admit(usize::MAX, usize::MAX, 1), Err(ABI_ERROR));
        assert_eq!(apply_into(&[0.5; 3], &[1.0], 1, 1, 0.5, 1,
            &mut [0.0; 2], || false), Err(ABI_ERROR));
    }

    #[test]
    fn cancellation_before_allocation_and_during_neighbour_work() {
        let mut output = [42.0; 3];
        assert_eq!(apply_into(&[0.5; 3], &[1.0], 1, 1, 1.0, 1,
            &mut output, || true), Err(CANCELLED));
        assert_eq!(output, [42.0; 3]);
        let source = scene(33, 33, [0.7, 0.6, 0.5]);
        let mut output = vec![42.0; source.len()];
        let mut polls = 0;
        assert_eq!(apply_into(&source, &[1.0; 1089], 33, 33, 1.0, 2, &mut output,
            || { polls += 1; polls >= 7 }), Err(CANCELLED));
        assert!(output.iter().any(|&v| v != 42.0));
        assert!(output.iter().any(|&v| v == 42.0));
    }

    #[test]
    fn ffi_refuses_null_alignment_alias_lengths_and_uses_callback() {
        let mut source = [0.7, 0.6, 0.5];
        let mut mask_output = [1.0; 3];
        let mut output = [42.0; 3];
        unsafe {
            assert_eq!(lrt_sclera_purify_apply_v1(std::ptr::null(), 3, mask_output.as_ptr(), 1,
                1, 1, 1.0, 1, output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
            let unaligned = (source.as_ptr() as *const u8).add(1) as *const f32;
            assert_eq!(lrt_sclera_purify_apply_v1(unaligned, 3, mask_output.as_ptr(), 1,
                1, 1, 1.0, 1, output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
            assert_eq!(lrt_sclera_purify_apply_v1(source.as_ptr(), 3, mask_output.as_ptr(), 1,
                1, 1, 1.0, 1, source.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
            assert_eq!(lrt_sclera_purify_apply_v1(source.as_ptr(), 3, mask_output.as_ptr(), 1,
                1, 1, 1.0, 1, mask_output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
            assert_eq!(lrt_sclera_purify_apply_v1(source.as_ptr(), 2, mask_output.as_ptr(), 1,
                1, 1, 1.0, 1, output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
        }
        assert_eq!(output, [42.0; 3]);
        assert_eq!(mask_output, [1.0; 3]);
        extern "C" fn cancel(context: *mut c_void) -> i32 {
            unsafe { *(context as *mut usize) += 1; }
            1
        }
        let mut calls = 0_usize;
        let code = unsafe { lrt_sclera_purify_apply_v1(source.as_ptr(), 3, mask_output.as_ptr(), 1,
            1, 1, 1.0, 1, output.as_mut_ptr(), 3, Some(cancel),
            &mut calls as *mut usize as *mut c_void) };
        assert_eq!(code, CANCELLED);
        assert_eq!(calls, 1);
        assert_eq!(output, [42.0; 3]);
    }
}
