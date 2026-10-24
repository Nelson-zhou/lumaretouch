// SPDX-License-Identifier: GPL-3.0-or-later
//! Source-owned protection blend for a separately prepared eye-bag correction.
//! AUTHORED / UNRUN. This is not an anatomical detector or a bag-removal solver.
//! Float32 encoded working-sRGB SDR RGB; no transfer function, clamp or resample.
use std::{ffi::c_void, mem, panic, slice};

pub const MAX_PIXELS: usize = 32_000_000;
pub const MAX_DIMENSION: usize = 65_536;
pub const NATIVE_SCRATCH_BYTES_PER_PIXEL: usize = 12;
pub const NATIVE_TOTAL_BYTES_PER_PIXEL: usize = 52;
pub const MAX_WORKING_BYTES: usize = 3 * 1024 * 1024 * 1024;
pub const POLL_PIXELS: usize = 256;
pub const ABI_ERROR: i32 = 1;
pub const SETTINGS_ERROR: i32 = 2;
pub const PIXEL_ERROR: i32 = 3;
pub const CANCELLED: i32 = 4;
pub const RESOURCE_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;
pub type Cancel = Option<extern "C" fn(*mut c_void) -> i32>;

fn unit(value: f32) -> bool { value.is_finite() && (0.0..=1.0).contains(&value) }
fn poll<F: FnMut() -> bool>(cancelled: &mut F) -> Result<(), i32> {
    if cancelled() { Err(CANCELLED) } else { Ok(()) }
}
fn admit(width: usize, height: usize) -> Result<usize, i32> {
    if width == 0 || height == 0 || width > MAX_DIMENSION || height > MAX_DIMENSION {
        return Err(ABI_ERROR);
    }
    let pixels = width.checked_mul(height).ok_or(RESOURCE_ERROR)?;
    let bytes = pixels.checked_mul(NATIVE_TOTAL_BYTES_PER_PIXEL).ok_or(RESOURCE_ERROR)?;
    if pixels > MAX_PIXELS || bytes > MAX_WORKING_BYTES { return Err(RESOURCE_ERROR); }
    Ok(pixels)
}

fn blend(source: f32, corrected: f32, keep: f64) -> Result<f32, i32> {
    // Source equality is deliberately numeric: +0 and -0 are the same zero
    // delta, and the source's original sign bit wins without doing arithmetic.
    if keep == 1.0 || source == corrected { return Ok(source); }
    if keep == 0.0 { return Ok(corrected); }
    let value = (f64::from(source)
        + (f64::from(corrected) - f64::from(source)) * (1.0 - keep)) as f32;
    if !unit(value) { return Err(PIXEL_ERROR); }
    // A sub-f32 correction that rounds to no numerical change is also a no-op.
    Ok(if value == source { source } else { value })
}

/// Blend only this operation's corrected RGB against the exact common source.
/// Every input is validated even if the requested blend is an identity. Output
/// is untouched on returned errors/cancellation. Inputs are never modified.
/// Final publication is one non-interruptible copy after the final poll.
pub fn apply_into<F: FnMut() -> bool>(
    source: &[f32], corrected: &[f32], protection: &[f32],
    width: usize, height: usize, preserve: f32, output: &mut [f32],
    mut cancelled: F,
) -> Result<(), i32> {
    let pixels = admit(width, height)?;
    let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
    if source.len() != channels || corrected.len() != channels
        || protection.len() != pixels || output.len() != channels { return Err(ABI_ERROR); }
    if !unit(preserve) { return Err(SETTINGS_ERROR); }
    let mut may_change = false;
    for i in 0..pixels {
        if i % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
        if !unit(protection[i])
            || !source[3*i..3*i+3].iter().copied().all(unit)
            || !corrected[3*i..3*i+3].iter().copied().all(unit) {
            return Err(PIXEL_ERROR);
        }
        let keep = f64::from(preserve) * f64::from(protection[i]);
        may_change |= keep != 1.0 && (0..3).any(|c| source[3*i+c] != corrected[3*i+c]);
    }
    poll(&mut cancelled)?;
    if !may_change {
        output.copy_from_slice(source);
        return Ok(());
    }
    let mut staged = Vec::new();
    staged.try_reserve_exact(channels).map_err(|_| RESOURCE_ERROR)?;
    for i in 0..pixels {
        if i % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
        let keep = f64::from(preserve) * f64::from(protection[i]);
        for c in 0..3 { staged.push(blend(source[3*i+c], corrected[3*i+c], keep)?); }
    }
    poll(&mut cancelled)?;
    output.copy_from_slice(&staged);
    Ok(())
}

fn span(pointer: *const f32, length: usize) -> Result<(usize, usize), i32> {
    let bytes = length.checked_mul(mem::size_of::<f32>()).ok_or(ABI_ERROR)?;
    let start = pointer as usize;
    if pointer.is_null() || start % mem::align_of::<f32>() != 0 || bytes > isize::MAX as usize {
        return Err(ABI_ERROR);
    }
    Ok((start, start.checked_add(bytes).ok_or(ABI_ERROR)?))
}
fn overlaps(a: (usize, usize), b: (usize, usize)) -> bool { a.0 < b.1 && b.0 < a.1 }

#[no_mangle]
pub extern "C" fn lrt_eye_bag_preserve_abi() -> u32 { 1 }

/// ABI 1. Lengths count floats. Host authenticates the exact source, FaceRef,
/// reviewed protection, dimensions and separately prepared eye-bag correction.
/// This boundary cannot establish anatomy, review completeness or provenance.
/// # Safety
/// All spans must be live aligned allocations of their stated sizes. Read-only
/// inputs remain immutable and may overlap; output is exclusive and may not
/// overlap any input. Callback/context remain live throughout the call. Callback
/// must not unwind, reenter, free allocations or mutate any supplied buffer.
/// Range checks do not prove allocation ownership; panic containment does not
/// contain invalid pointers, foreign faults or process aborts.
#[no_mangle]
pub unsafe extern "C" fn lrt_eye_bag_preserve_apply_v1(
    source: *const f32, source_len: usize,
    corrected: *const f32, corrected_len: usize,
    protection: *const f32, protection_len: usize,
    width: usize, height: usize, preserve: f32,
    output: *mut f32, output_len: usize,
    cancel: Cancel, context: *mut c_void,
) -> i32 {
    let result = panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(), i32> {
        let pixels = admit(width, height)?;
        let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
        if source_len != channels || corrected_len != channels
            || protection_len != pixels || output_len != channels { return Err(ABI_ERROR); }
        if !unit(preserve) { return Err(SETTINGS_ERROR); }
        let output_span = span(output, output_len)?;
        for input in [span(source, source_len)?, span(corrected, corrected_len)?,
                      span(protection, protection_len)?] {
            if overlaps(input, output_span) { return Err(ABI_ERROR); }
        }
        apply_into(slice::from_raw_parts(source, source_len),
            slice::from_raw_parts(corrected, corrected_len),
            slice::from_raw_parts(protection, protection_len), width, height, preserve,
            slice::from_raw_parts_mut(output, output_len),
            || cancel.map_or(false, |function| function(context) != 0))
    }));
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

#[cfg(test)]
mod tests;
