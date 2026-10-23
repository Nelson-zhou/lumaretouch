// SPDX-License-Identifier: GPL-3.0-or-later
//! Original flash red-eye colour correction. AUTHORED / UNRUN.
//! Encoded working-sRGB SDR float32 RGB and target-owned inner-iris candidates.
//! No detection, segmentation, replacement iris or invention of missing pixels.
//! Source/target/revision ownership is the host's responsibility. See README.md.

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

/// A conservative colour test, NOT an anatomical or flash-artifact detector.
/// Comparison with max(G,B) requires dominance over BOTH other channels.
/// Natural red/brown iris pixels can still pass. Constants are uncalibrated.
fn red_weight(rgb: [f64; 3]) -> f64 {
    let other = rgb[1].max(rgb[2]);
    let excess = rgb[0] - other;
    // Absolute gating prevents near-black noise having an enormous ratio.
    // The denominator floor only stabilizes the ratio; it does not add pixels.
    smoothstep(1.5, 2.5, rgb[0] / other.max(1e-6))
        * smoothstep(0.08, 0.25, excess)
}

fn pixel(source: [f32; 3], coverage: f32, amount: f32) -> [f32; 3] {
    if coverage == 0.0 || amount == 0.0 { return source; }
    let rgb = source.map(f64::from);
    let gate = red_weight(rgb);
    if gate == 0.0 { return source; }
    let alpha = f64::from(coverage) * f64::from(amount) * gate;
    let destination_red = (rgb[1] + rgb[2]) * 0.5;
    // Only lower existing excess red. G/B are copied directly, bit-for-bit.
    // No spatial sampling, clipping, contrast lift or replacement by black.
    let corrected_red = rgb[0] + alpha * (destination_red - rgb[0]);
    [corrected_red as f32, source[1], source[2]]
}

/// Safe, allocation-free slice entrypoint. Validate ALL input before writing.
/// Cancellation can leave partially written output; discard it on ANY error.
pub fn apply_into(
    source: &[f32], coverage: &[f32], width: usize, height: usize,
    amount: f32, output: &mut [f32], mut cancelled: impl FnMut() -> bool,
) -> Result<(), i32> {
    let pixels = count(width, height)?;
    let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
    if source.len() != channels || coverage.len() != pixels || output.len() != channels {
        return Err(ABI_ERROR);
    }
    if !unit(amount) { return Err(SETTINGS_ERROR); }
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
        let adjusted = pixel(original, coverage[i], amount);
        if !adjusted.iter().copied().all(unit) { return Err(PIXEL_ERROR); }
        output[3*i..3*i+3].copy_from_slice(&adjusted);
    }
    if cancelled() { return Err(CANCELLED); }
    Ok(())
}

// These checks cannot prove that a pointer denotes a valid, live allocation.
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
pub extern "C" fn lrt_red_eye_abi() -> u32 { 1 }

/// ABI-1 lengths count float32 ELEMENTS, not bytes; RGB is interleaved HWC.
/// Returns 0 on success or one of the status constants declared above.
///
/// # Safety
/// Inputs must be live, aligned, readable allocations with the stated lengths
/// and immutable throughout this call, including callbacks. Output must be a
/// live, exclusively writable allocation, not overlapping either input. The
/// two read-only inputs may overlap. Pointer checks cannot prove ownership.
/// Callback/context stay valid; the callback never unwinds, mutates buffers or
/// reenters this call. Discard all output on EVERY nonzero status, even if the
/// last pixel was written before cancellation. Catching Rust panics does not
/// make invalid foreign pointers, foreign exceptions or data races safe.
#[no_mangle]
pub unsafe extern "C" fn lrt_red_eye_apply_v1(
    source: *const f32, source_len: usize,
    coverage: *const f32, coverage_len: usize,
    width: usize, height: usize, amount: f32,
    output: *mut f32, output_len: usize, cancel: Cancel, context: *mut c_void,
) -> i32 {
    let result = panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(), i32> {
        let pixels = count(width, height)?;
        let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
        if source_len != channels || coverage_len != pixels || output_len != channels {
            return Err(ABI_ERROR);
        }
        if !unit(amount) { return Err(SETTINGS_ERROR); }
        let rgb_span = span(source, source_len)?;
        let weight_span = span(coverage, coverage_len)?;
        let output_span = span(output, output_len)?;
        if overlaps(rgb_span, output_span) || overlaps(weight_span, output_span) {
            return Err(ABI_ERROR);
        }
        let rgb = slice::from_raw_parts(source, source_len);
        let weight = slice::from_raw_parts(coverage, coverage_len);
        let out = slice::from_raw_parts_mut(output, output_len);
        apply_into(rgb, weight, width, height, amount, out,
            || cancel.map_or(false, |function| function(context) != 0))
    }));
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

#[cfg(test)]
mod tests {
    // AUTHORED / UNRUN. Neither compilation nor acceptance is established.
    use super::*;

    fn render(source: &[f32], support: &[f32], amount: f32) -> Vec<f32> {
        let mut output = vec![-1.0; source.len()];
        apply_into(source, support, support.len(), 1, amount, &mut output, || false).unwrap();
        output
    }
    fn bits(values: &[f32]) -> Vec<u32> { values.iter().map(|v| v.to_bits()).collect() }

    #[test]
    fn neutral_amount_and_zero_support_are_bit_exact() {
        let source = [-0.0, 0.0, 0.5, 0.9, 0.1, 0.2];
        assert_eq!(bits(&source), bits(&render(&source, &[1.0, 0.25], 0.0)));
        assert_eq!(bits(&source), bits(&render(&source, &[0.0, -0.0], 1.0)));
    }

    #[test]
    fn strong_red_moves_to_green_blue_mean_without_changing_those_channels() {
        let source = [0.9, 0.1, 0.2, 1.0, -0.0, 0.0];
        let output = render(&source, &[1.0, 1.0], 1.0);
        assert!((output[0] - 0.15).abs() < 1e-7);
        assert_eq!(output[3], 0.0);
        for channel in [1, 2, 4, 5] {
            assert_eq!(output[channel].to_bits(), source[channel].to_bits());
        }
    }

    #[test]
    fn dominance_over_only_one_other_channel_is_not_enough() {
        let source = [0.9, 0.7, 0.1, 0.9, 0.1, 0.7, 0.4, 0.8, 0.1];
        assert_eq!(bits(&source), bits(&render(&source, &[1.0; 3], 1.0)));
    }

    #[test]
    fn neutral_black_and_near_neutral_catchlights_are_unchanged() {
        let source = [-0.0, 0.0, 0.0, 0.5, 0.5, 0.5,
                      1.0, 1.0, 1.0, 1.0, 0.9, 0.8, 0.07, 0.0, 0.0];
        assert_eq!(bits(&source), bits(&render(&source, &[1.0; 5], 1.0)));
    }

    #[test]
    fn ratio_and_absolute_gates_are_smooth_with_exact_zero_ends() {
        assert_eq!(red_weight([0.3, 0.2, 0.1]), 0.0);
        assert_eq!(red_weight([0.08, 0.0, 0.0]), 0.0);
        assert_eq!(red_weight([0.75, 0.3, 0.1]), 1.0);
        assert!((red_weight([0.6, 0.3, 0.1]) - 0.5).abs() < 1e-12);
        assert!((red_weight([0.165, 0.0, 0.0]) - 0.5).abs() < 1e-12);
        assert!(red_weight([0.450001, 0.3, 0.1]) < 1e-9);
        assert!((1.0 - red_weight([0.749999, 0.3, 0.1])).abs() < 1e-9);
        assert!(red_weight([0.080001, 0.0, 0.0]) < 1e-9);
        assert!((1.0 - red_weight([0.249999, 0.0, 0.0])).abs() < 1e-9);
    }

    #[test]
    fn amount_and_support_scale_the_correction_without_overshoot() {
        let source = [0.8, 0.1, 0.2];
        let full = render(&source, &[1.0], 1.0);
        let half_amount = render(&source, &[1.0], 0.5);
        let half_support = render(&source, &[0.5], 1.0);
        assert_eq!(bits(&half_amount), bits(&half_support));
        assert!((half_amount[0] - (source[0] + full[0])*0.5).abs() < 1e-7);
        let mut previous = source[0];
        for amount in [0.0, 0.1, 0.25, 0.5, 0.75, 1.0] {
            let red = render(&source, &[0.75], amount)[0];
            assert!(red <= previous && red >= (source[1] + source[2])*0.5);
            previous = red;
        }
    }

    #[test]
    fn natural_dark_red_can_still_change_and_is_not_claimed_as_detected_flash() {
        // Deliberate limitation fixture: colour alone cannot separate a real
        // brown/red iris from flash. Correct source-owned support is necessary
        // but insufficient to establish that every covered red pixel is flash.
        let source = [0.3, 0.04, 0.03];
        assert!(render(&source, &[1.0], 1.0)[0] < source[0]);
    }

    #[test]
    fn invalid_pixels_are_rejected_even_when_neutral_or_outside_support() {
        for invalid in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, -0.01, 1.01] {
            let mut output = [42.0; 3];
            assert_eq!(apply_into(&[invalid, 0.1, 0.2], &[0.0], 1, 1,
                0.0, &mut output, || false), Err(PIXEL_ERROR));
            assert_eq!(output, [42.0; 3]);
            assert_eq!(apply_into(&[0.9, 0.1, 0.2], &[invalid], 1, 1,
                0.0, &mut output, || false), Err(PIXEL_ERROR));
            assert_eq!(output, [42.0; 3]);
        }
    }

    #[test]
    fn invalid_last_pixel_cannot_publish_the_first_corrected_pixel() {
        let mut output = [42.0; 6];
        assert_eq!(apply_into(&[0.9, 0.1, 0.2, 0.8, 0.1, f32::NAN],
            &[1.0, 0.0], 2, 1, 1.0, &mut output, || false), Err(PIXEL_ERROR));
        assert_eq!(output, [42.0; 6]);
    }

    #[test]
    fn invalid_amount_dimensions_and_lengths_fail_closed() {
        for invalid in [f32::NAN, f32::INFINITY, -0.01, 1.01] {
            let mut output = [42.0; 3];
            assert_eq!(apply_into(&[0.5; 3], &[1.0], 1, 1,
                invalid, &mut output, || false), Err(SETTINGS_ERROR));
            assert_eq!(output, [42.0; 3]);
        }
        assert_eq!(count(0, 1), Err(ABI_ERROR));
        assert_eq!(count(usize::MAX, usize::MAX), Err(ABI_ERROR));
        assert_eq!(count(8192, 8192), Err(RESOURCE_ERROR));
        assert_eq!(apply_into(&[0.5; 3], &[1.0], 1, 1,
            1.0, &mut [0.0; 2], || false), Err(ABI_ERROR));
    }

    #[test]
    fn cancellation_before_and_during_output_is_reported() {
        let mut untouched = [42.0; 3];
        assert_eq!(apply_into(&[0.9, 0.1, 0.2], &[1.0], 1, 1,
            1.0, &mut untouched, || true), Err(CANCELLED));
        assert_eq!(untouched, [42.0; 3]);
        let source = vec![0.5; 3*POLL_PIXELS*2];
        let support = vec![1.0; POLL_PIXELS*2];
        let mut output = vec![42.0; source.len()];
        let mut calls = 0;
        assert_eq!(apply_into(&source, &support, support.len(), 1, 1.0, &mut output,
            || { calls += 1; calls >= 5 }), Err(CANCELLED));
        assert_ne!(output[0], 42.0);
        assert_eq!(output[3*POLL_PIXELS], 42.0);
    }

    #[test]
    fn ffi_rejects_null_unaligned_alias_and_wrong_lengths_before_writing() {
        let mut source = [0.9, 0.1, 0.2];
        let support = [1.0];
        let mut output = [42.0; 3];
        let mut shared_support_output = [1.0; 3];
        unsafe {
            assert_eq!(lrt_red_eye_apply_v1(std::ptr::null(), 3, support.as_ptr(), 1,
                1, 1, 1.0, output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
            let unaligned = (source.as_ptr() as *const u8).add(1) as *const f32;
            assert_eq!(lrt_red_eye_apply_v1(unaligned, 3, support.as_ptr(), 1,
                1, 1, 1.0, output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
            assert_eq!(lrt_red_eye_apply_v1(source.as_ptr(), 3, support.as_ptr(), 1,
                1, 1, 1.0, source.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
            assert_eq!(lrt_red_eye_apply_v1(source.as_ptr(), 2, support.as_ptr(), 1,
                1, 1, 1.0, output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
            assert_eq!(lrt_red_eye_apply_v1(source.as_ptr(), 3, shared_support_output.as_ptr(), 1,
                1, 1, 1.0, shared_support_output.as_mut_ptr(), 3, None, std::ptr::null_mut()), ABI_ERROR);
        }
        assert_eq!(output, [42.0; 3]);
        assert_eq!(shared_support_output, [1.0; 3]);
    }

    #[test]
    fn ffi_honours_cancellation_context() {
        extern "C" fn cancel(context: *mut c_void) -> i32 {
            // The test owns this live usize exclusively for the callback.
            unsafe { *(context as *mut usize) += 1; }
            1
        }
        let source = [0.9, 0.1, 0.2];
        let support = [1.0];
        let mut output = [42.0; 3];
        let mut calls = 0_usize;
        let code = unsafe {
            lrt_red_eye_apply_v1(source.as_ptr(), 3, support.as_ptr(), 1, 1, 1,
                1.0, output.as_mut_ptr(), 3, Some(cancel),
                &mut calls as *mut usize as *mut c_void)
        };
        assert_eq!(code, CANCELLED);
        assert_eq!(calls, 1);
        assert_eq!(output, [42.0; 3]);
    }
}
