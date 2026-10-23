// SPDX-License-Identifier: GPL-3.0-or-later
//! Original, non-generative tooth colour adjustment. AUTHORED / UNRUN.
//! Encoded working-sRGB SDR float32 RGB and caller-owned teeth coverage only.
//! This kernel cannot detect teeth or authenticate a face/source/mask identity.
//! See README.md for method, provenance, safety and acceptance limitations.

use std::{ffi::c_void, mem, panic, slice};

pub const MAX_PIXELS: usize = 64_000_000;
pub const MAX_DIMENSION: usize = 65_536;
pub const POLL_PIXELS: usize = 4096;
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

fn count(width: usize, height: usize) -> Result<usize, i32> {
    if width == 0 || height == 0 || width > MAX_DIMENSION || height > MAX_DIMENSION {
        return Err(ABI_ERROR);
    }
    let pixels = width.checked_mul(height).ok_or(RESOURCE_ERROR)?;
    if pixels > MAX_PIXELS { return Err(RESOURCE_ERROR); }
    Ok(pixels)
}

fn smoothstep(low: f64, high: f64, value: f64) -> f64 {
    let t = ((value - low) / (high - low)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

/// A colour range, not a tooth detector. Plateau 45..75 degrees, smooth
/// falloff to exactly zero at 25 and 95 degrees. Red/pink/blue are excluded.
fn yellow_weight(rgb: [f64; 3], value: f64, minimum: f64) -> f64 {
    let chroma = value - minimum;
    if chroma == 0.0 { return 0.0; }
    let hue = if value == rgb[0] {
        ((rgb[1] - rgb[2]) / chroma).rem_euclid(6.0) * 60.0
    } else if value == rgb[1] {
        ((rgb[2] - rgb[0]) / chroma + 2.0) * 60.0
    } else {
        ((rgb[0] - rgb[1]) / chroma + 4.0) * 60.0
    };
    1.0 - smoothstep(15.0, 35.0, (hue - 60.0).abs())
}

fn pixel(source: [f32; 3], coverage: f32, brightness: f32, yellow: f32) -> [f32; 3] {
    if coverage == 0.0 || (brightness == 0.0 && yellow == 0.0) { return source; }
    let rgb = source.map(f64::from);
    let value = rgb[0].max(rgb[1]).max(rgb[2]);
    let minimum = rgb[0].min(rgb[1]).min(rgb[2]);
    // Black is never lifted into invented tooth detail.
    if value == 0.0 { return source; }
    let reduction = if yellow == 0.0 { 0.0 }
        else { f64::from(yellow) * yellow_weight(rgb, value, minimum) };
    // Multiplicative gain with a monotone shoulder, not replacement by white.
    // V' < .965 for V < .965; already brighter values are never darkened.
    // Unlike hard clipping this retains ordering of distinct highlight values.
    let headroom = (0.965_f64 - value).max(0.0);
    let gain = 0.35 * f64::from(brightness) * value;
    let lift = if gain == 0.0 || headroom == 0.0 { 0.0 }
        else { gain * headroom / (gain + headroom) };
    if lift == 0.0 && reduction == 0.0 { return source; }
    let scale = (value + lift) / value;
    let alpha = f64::from(coverage);
    std::array::from_fn(|channel| {
        // Moving toward the original V lowers HSV S, without changing H or V.
        // The separate common RGB scale changes V without changing H or S.
        let adjusted = (rgb[channel] + reduction * (value - rgb[channel])) * scale;
        (rgb[channel] + alpha * (adjusted - rgb[channel])) as f32
    })
}

/// Safe slice entrypoint. No allocations, resizing, spatial filtering or AI.
/// Inputs are fully validated BEFORE any output writes. Cancellation may leave
/// a partial output: the caller MUST discard it on every nonzero result.
pub fn apply_into(
    source: &[f32], coverage: &[f32], width: usize, height: usize,
    brightness: f32, yellow: f32, output: &mut [f32],
    mut cancelled: impl FnMut() -> bool,
) -> Result<(), i32> {
    let pixels = count(width, height)?;
    let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
    if source.len() != channels || coverage.len() != pixels || output.len() != channels {
        return Err(ABI_ERROR);
    }
    if !unit(brightness) || !unit(yellow) { return Err(SETTINGS_ERROR); }
    if cancelled() { return Err(CANCELLED); }
    for i in 0..pixels {
        if i % POLL_PIXELS == 0 && cancelled() { return Err(CANCELLED); }
        if !unit(coverage[i]) || !source[3*i..3*i+3].iter().copied().all(unit) {
            return Err(PIXEL_ERROR);
        }
    }
    for i in 0..pixels {
        if i % POLL_PIXELS == 0 && cancelled() { return Err(CANCELLED); }
        let original = [source[3*i], source[3*i+1], source[3*i+2]];
        let adjusted = pixel(original, coverage[i], brightness, yellow);
        if !adjusted.iter().copied().all(unit) { return Err(PIXEL_ERROR); }
        output[3*i..3*i+3].copy_from_slice(&adjusted);
    }
    if cancelled() { return Err(CANCELLED); }
    Ok(())
}

// Checks pointer arithmetic, alignment and overlap, NOT allocation validity.
fn span(pointer: *const f32, length: usize) -> Result<(usize, usize), i32> {
    let start = pointer as usize;
    let bytes = length.checked_mul(mem::size_of::<f32>()).ok_or(ABI_ERROR)?;
    if pointer.is_null() || start % mem::align_of::<f32>() != 0
        || bytes > isize::MAX as usize { return Err(ABI_ERROR); }
    Ok((start, start.checked_add(bytes).ok_or(ABI_ERROR)?))
}

fn overlaps(a: (usize, usize), b: (usize, usize)) -> bool {
    a.0 < b.1 && b.0 < a.1
}

#[no_mangle]
pub extern "C" fn lrt_teeth_colour_abi() -> u32 { 1 }

/// ABI-1 lengths count float32 ELEMENTS, not bytes. Interleaved HWC RGB.
/// Return 0 only on success; status values are public constants above.
///
/// # Safety
/// Caller supplies valid live, aligned readable allocations for both inputs and
/// an exclusively writable output allocation with exactly the stated lengths.
/// Inputs stay immutable for the entire call, including during callbacks.
/// Output must not overlap either input; read-only input overlap is permitted.
/// The callback/context stay valid, never unwind, never mutate these buffers,
/// and never reenter this call. A pointer range check cannot prove ownership.
/// Discard ALL output on nonzero status, including cancellation after rendering.
#[no_mangle]
pub unsafe extern "C" fn lrt_teeth_colour_apply_v1(
    source: *const f32, source_len: usize,
    coverage: *const f32, coverage_len: usize,
    width: usize, height: usize, brightness: f32, yellow: f32,
    output: *mut f32, output_len: usize, cancel: Cancel, context: *mut c_void,
) -> i32 {
    let result = panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(), i32> {
        let pixels = count(width, height)?;
        let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
        if source_len != channels || coverage_len != pixels || output_len != channels {
            return Err(ABI_ERROR);
        }
        if !unit(brightness) || !unit(yellow) { return Err(SETTINGS_ERROR); }
        let rgb_span = span(source, source_len)?;
        let weight_span = span(coverage, coverage_len)?;
        let output_span = span(output, output_len)?;
        if overlaps(rgb_span, output_span) || overlaps(weight_span, output_span) {
            return Err(ABI_ERROR);
        }
        let rgb = slice::from_raw_parts(source, source_len);
        let weight = slice::from_raw_parts(coverage, coverage_len);
        let out = slice::from_raw_parts_mut(output, output_len);
        apply_into(rgb, weight, width, height, brightness, yellow, out,
            || cancel.map_or(false, |function| function(context) != 0))
    }));
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

#[cfg(test)]
mod tests {
    // AUTHORED / UNRUN. These fixtures are not build or acceptance evidence.
    use super::*;

    fn render(source: &[f32], coverage: &[f32], brightness: f32, yellow: f32) -> Vec<f32> {
        let mut output = vec![-1.0; source.len()];
        apply_into(source, coverage, coverage.len(), 1, brightness, yellow,
            &mut output, || false).unwrap();
        output
    }
    fn bits(values: &[f32]) -> Vec<u32> { values.iter().map(|v| v.to_bits()).collect() }
    fn saturation(rgb: &[f32]) -> f32 {
        let high = rgb.iter().copied().fold(0.0_f32, f32::max);
        let low = rgb.iter().copied().fold(1.0_f32, f32::min);
        if high == 0.0 { 0.0 } else { (high - low) / high }
    }

    #[test]
    fn neutral_and_zero_coverage_are_bit_exact() {
        let source = [-0.0, 0.0, 0.5, 0.7, 0.65, 0.4];
        assert_eq!(bits(&source), bits(&render(&source, &[1.0, 0.25], 0.0, 0.0)));
        assert_eq!(bits(&source), bits(&render(&source, &[0.0, -0.0], 1.0, 1.0)));
    }

    #[test]
    fn brightness_and_yellow_are_independent() {
        let source = [0.8, 0.75, 0.5];
        let bright = render(&source, &[1.0], 1.0, 0.0);
        assert!(bright[0] > source[0] && bright[0] < 0.965);
        assert!((saturation(&bright) - saturation(&source)).abs() < 1e-6);
        assert!((bright[0] / source[0] - bright[2] / source[2]).abs() < 1e-6);
        let less_yellow = render(&source, &[1.0], 0.0, 0.5);
        assert_eq!(less_yellow[0].to_bits(), source[0].to_bits());
        assert!(saturation(&less_yellow) < saturation(&source));
        assert!(((less_yellow[0] - less_yellow[1]) / (less_yellow[0] - less_yellow[2])
            - (source[0] - source[1]) / (source[0] - source[2])).abs() < 1e-6);
    }

    #[test]
    fn yellow_does_not_blanket_desaturate_gums_blue_green_or_neutral() {
        let source = [0.8, 0.4, 0.5, 0.2, 0.4, 0.8, 0.3, 0.8, 0.4, 0.5, 0.5, 0.5];
        assert_eq!(bits(&source), bits(&render(&source, &[1.0; 4], 0.0, 1.0)));
    }

    #[test]
    fn yellow_band_is_smooth_and_bounded() {
        let colour = |h: f64| [1.0, h / 60.0, 0.0];
        assert_eq!(yellow_weight(colour(25.0), 1.0, 0.0), 0.0);
        assert_eq!(yellow_weight(colour(45.0), 1.0, 0.0), 1.0);
        let middle = yellow_weight(colour(35.0), 1.0, 0.0);
        assert!((middle - 0.5).abs() < 1e-12);
        assert!((yellow_weight(colour(25.001), 1.0, 0.0)).abs() < 1e-7);
        assert!((1.0 - yellow_weight(colour(44.999), 1.0, 0.0)).abs() < 1e-7);
    }

    #[test]
    fn feathering_blends_only_with_own_source_pixel() {
        let source = [0.75, 0.7, 0.5];
        let full = render(&source, &[1.0], 0.7, 0.6);
        let half = render(&source, &[0.5], 0.7, 0.6);
        for channel in 0..3 {
            assert!((half[channel] - 0.5*(source[channel] + full[channel])).abs() < 1e-6);
        }
    }

    #[test]
    fn black_and_existing_highlights_are_not_synthesized_or_darkened() {
        assert_eq!(bits(&render(&[-0.0, 0.0, 0.0], &[1.0], 1.0, 1.0)),
            bits(&[-0.0, 0.0, 0.0]));
        let source = [0.98, 0.96, 0.8, 1.0, 1.0, 1.0];
        assert_eq!(bits(&source), bits(&render(&source, &[1.0, 1.0], 1.0, 0.0)));
    }

    #[test]
    fn shoulder_retains_ordered_highlight_texture() {
        let mut previous = 0.0;
        for value in [0.6_f32, 0.8, 0.9, 0.94, 0.95, 0.96] {
            let output = pixel([value, value, value], 1.0, 1.0, 0.0)[0];
            assert!(output > value && output < 0.965 && output > previous);
            previous = output;
        }
    }

    #[test]
    fn invalid_source_is_rejected_even_when_neutral_or_uncovered() {
        for invalid in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, -0.01, 1.01] {
            let mut output = [42.0; 3];
            assert_eq!(apply_into(&[invalid, 0.5, 0.4], &[0.0], 1, 1,
                0.0, 0.0, &mut output, || false), Err(PIXEL_ERROR));
            assert_eq!(output, [42.0; 3]);
        }
    }

    #[test]
    fn invalid_last_pixel_never_partially_publishes_valid_first_pixel() {
        let source = [0.8, 0.75, 0.5, 0.8, 0.7, f32::NAN];
        let mut output = [42.0; 6];
        assert_eq!(apply_into(&source, &[1.0, 0.0], 2, 1,
            1.0, 1.0, &mut output, || false), Err(PIXEL_ERROR));
        assert_eq!(output, [42.0; 6]);
    }

    #[test]
    fn settings_and_coverage_fail_closed() {
        for invalid in [f32::NAN, f32::INFINITY, -0.01, 1.01] {
            let mut output = [42.0; 3];
            assert_eq!(apply_into(&[0.5; 3], &[1.0], 1, 1, invalid,
                0.0, &mut output, || false), Err(SETTINGS_ERROR));
            assert_eq!(apply_into(&[0.5; 3], &[1.0], 1, 1, 0.0,
                invalid, &mut output, || false), Err(SETTINGS_ERROR));
            assert_eq!(apply_into(&[0.5; 3], &[invalid], 1, 1, 0.5,
                0.5, &mut output, || false), Err(PIXEL_ERROR));
            assert_eq!(output, [42.0; 3]);
        }
    }

    #[test]
    fn dimensions_and_lengths_are_bounded() {
        assert_eq!(count(0, 1), Err(ABI_ERROR));
        assert_eq!(count(usize::MAX, usize::MAX), Err(ABI_ERROR));
        assert_eq!(count(8192, 8192), Err(RESOURCE_ERROR));
        assert_eq!(apply_into(&[0.5; 3], &[1.0], 1, 1, 0.5, 0.5,
            &mut [0.0; 2], || false), Err(ABI_ERROR));
    }

    #[test]
    fn cancellation_before_and_during_output_is_reported() {
        let mut untouched = [42.0; 3];
        assert_eq!(apply_into(&[0.5; 3], &[1.0], 1, 1, 0.5, 0.5,
            &mut untouched, || true), Err(CANCELLED));
        assert_eq!(untouched, [42.0; 3]);
        let source = vec![0.5; 3*POLL_PIXELS*2];
        let mask = vec![1.0; POLL_PIXELS*2];
        let mut output = vec![42.0; source.len()];
        let mut calls = 0;
        assert_eq!(apply_into(&source, &mask, mask.len(), 1, 0.5, 0.0, &mut output,
            || { calls += 1; calls >= 5 }), Err(CANCELLED));
        // A nonzero return is never publishable, even if some values changed.
        assert_ne!(output[0], 42.0);
        assert_eq!(output[3*POLL_PIXELS], 42.0);
    }

    #[test]
    fn ffi_rejects_null_unaligned_alias_and_wrong_lengths() {
        let mut source = [0.7, 0.6, 0.4];
        let mask = [1.0];
        let mut output = [42.0; 3];
        let mut shared_mask_output = [1.0; 3];
        unsafe {
            assert_eq!(lrt_teeth_colour_apply_v1(std::ptr::null(), 3, mask.as_ptr(), 1,
                1, 1, 0.5, 0.5, output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
            let unaligned = (source.as_ptr() as *const u8).add(1) as *const f32;
            assert_eq!(lrt_teeth_colour_apply_v1(unaligned, 3, mask.as_ptr(), 1,
                1, 1, 0.5, 0.5, output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
            assert_eq!(lrt_teeth_colour_apply_v1(source.as_ptr(), 3, mask.as_ptr(), 1,
                1, 1, 0.5, 0.5, source.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
            assert_eq!(lrt_teeth_colour_apply_v1(source.as_ptr(), 2, mask.as_ptr(), 1,
                1, 1, 0.5, 0.5, output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
            assert_eq!(lrt_teeth_colour_apply_v1(source.as_ptr(), 3, shared_mask_output.as_ptr(), 1,
                1, 1, 0.5, 0.5, shared_mask_output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
        }
        assert_eq!(output, [42.0; 3]);
        assert_eq!(shared_mask_output, [1.0; 3]);
    }

    #[test]
    fn ffi_honours_cancellation_context() {
        extern "C" fn cancel(context: *mut c_void) -> i32 {
            // The fixture supplies one live usize, exclusively for this callback.
            unsafe { *(context as *mut usize) += 1; }
            1
        }
        let source = [0.8, 0.75, 0.5];
        let mask = [1.0];
        let mut output = [42.0; 3];
        let mut calls = 0_usize;
        let code = unsafe {
            lrt_teeth_colour_apply_v1(source.as_ptr(), 3, mask.as_ptr(), 1, 1, 1,
                0.5, 0.5, output.as_mut_ptr(), 3, Some(cancel),
                &mut calls as *mut usize as *mut c_void)
        };
        assert_eq!(code, CANCELLED);
        assert_eq!(calls, 1);
        assert_eq!(output, [42.0; 3]);
    }
}
