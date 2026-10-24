// SPDX-License-Identifier: GPL-3.0-or-later
//! Original existing-brow source-local contrast edit. AUTHORED / UNRUN.
//! Encoded working-sRGB-D65 float32 SDR boundary, f64 linear-light calculation.
//! No added strokes, synthesis, reconstruction, source resampling or exposure alias.
use std::{ffi::c_void, mem, panic, slice};

pub const MAX_PIXELS: usize = 32_000_000;
pub const MAX_DIMENSION: usize = 65_536;
pub const MIN_RADIUS: usize = 2;
pub const MAX_RADIUS: usize = 128;
pub const NATIVE_SCRATCH_BYTES_PER_PIXEL: usize = 44;
pub const NATIVE_TOTAL_BYTES_PER_PIXEL: usize = 76;
pub const MAX_WORKING_BYTES: usize = 3 * 1024 * 1024 * 1024;
pub const POLL_PIXELS: usize = 256;
pub const MAX_GAIN: f64 = 0.40;
pub const DARK_DEADZONE_LOG: f64 = 0.04;
pub const MAX_RESIDUAL_LOG: f64 = 1.3862943611198906; // ln(4), original restraint.
pub const MIN_REFERENCE_MASS: f64 = 4.0;
pub const MIN_EFFECTIVE_REFERENCE: f64 = 4.0;
pub const MAX_REFERENCE_CV: f64 = 0.25;
pub const ABI_ERROR: i32 = 1;
pub const SETTINGS_ERROR: i32 = 2;
pub const PIXEL_ERROR: i32 = 3;
pub const CANCELLED: i32 = 4;
pub const RESOURCE_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;
pub const REFERENCE_ERROR: i32 = 7;
pub type Cancel = Option<extern "C" fn(*mut c_void) -> i32>;
type Stats = [f64; 4]; // actual w, w², wY, wY²; no fabricated samples.

fn unit(value: f32) -> bool { value.is_finite() && (0.0..=1.0).contains(&value) }
fn control(value: f32) -> bool { value.is_finite() && (-1.0..=1.0).contains(&value) }
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
fn decode(value: f64) -> f64 {
    if value <= 0.04045 { value / 12.92 }
    else { ((value + 0.055) / 1.055).powf(2.4) }
}
fn encode(value: f64) -> f32 {
    if value <= 0.0031308 { (12.92 * value) as f32 }
    else { (1.055 * value.powf(1.0 / 2.4) - 0.055) as f32 }
}
fn linear(source: &[f32], i: usize) -> [f64; 3] {
    std::array::from_fn(|c| decode(f64::from(source[3 * i + c])))
}
fn luminance(rgb: [f64; 3]) -> f64 { 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2] }
fn sample(source: &[f32], reference: &[f32], i: usize) -> Stats {
    let weight = f64::from(reference[i]);
    if weight == 0.0 { return [0.0; 4]; }
    let y = luminance(linear(source, i));
    [weight, weight * weight, weight * y, weight * y * y]
}

/// O(N) separable rolling sums. Actual in-domain reference pixels only.
/// f64 storage avoids f32 precision loss in small-mass local admission checks.
fn horizontal<F: FnMut() -> bool>(
    source: &[f32], reference: &[f32], width: usize, height: usize, radius: usize,
    cancelled: &mut F,
) -> Result<Vec<Stats>, i32> {
    poll(cancelled)?;
    let count = width * height;
    let mut rows = Vec::new();
    rows.try_reserve_exact(count).map_err(|_| RESOURCE_ERROR)?;
    for i in 0..count {
        if i % POLL_PIXELS == 0 { poll(cancelled)?; }
        rows.push([0.0; 4]);
    }
    for y in 0..height {
        poll(cancelled)?;
        let mut sum = [0.0_f64; 4];
        for x in 0..=radius.min(width - 1) {
            let value = sample(source, reference, y * width + x);
            for c in 0..4 { sum[c] += value[c]; }
        }
        for x in 0..width {
            if x % POLL_PIXELS == 0 { poll(cancelled)?; }
            rows[y * width + x] = sum;
            if x >= radius {
                let value = sample(source, reference, y * width + x - radius);
                for c in 0..4 { sum[c] -= value[c]; }
            }
            if x + radius + 1 < width {
                let value = sample(source, reference, y * width + x + radius + 1);
                for c in 0..4 { sum[c] += value[c]; }
            }
        }
    }
    Ok(rows)
}

fn reference_y(stats: Stats) -> Result<f64, i32> {
    let [mass, squared, weighted_y, weighted_y_squared] = stats;
    if !stats.iter().all(|v| v.is_finite()) || mass < MIN_REFERENCE_MASS
        || squared <= 0.0 || mass * mass / squared < MIN_EFFECTIVE_REFERENCE {
        return Err(REFERENCE_ERROR);
    }
    let mean = weighted_y / mass;
    if !mean.is_finite() || mean <= 0.0 || mean > 1.0 { return Err(REFERENCE_ERROR); }
    let second = weighted_y_squared / mass;
    let raw_variance = second - mean * mean;
    // Tiny negative roundoff in a second moment is not an invented RGB sample.
    // A larger inconsistency is refused, not repaired by widening the threshold.
    if !raw_variance.is_finite() || raw_variance < -1e-12 { return Err(REFERENCE_ERROR); }
    let variance = raw_variance.max(0.0);
    if variance > MAX_REFERENCE_CV * MAX_REFERENCE_CV * mean * mean {
        return Err(REFERENCE_ERROR);
    }
    Ok(mean)
}

fn adjusted(source: [f32; 3], reference_y: f64, coverage: f32, amount: f32) -> Result<[f32; 3], i32> {
    if coverage == 0.0 || amount == 0.0 { return Ok(source); }
    let rgb = source.map(|v| decode(f64::from(v)));
    let y = luminance(rgb);
    // Exact black is not lifted, and bright/equal pixels never become dark hairs.
    if y == 0.0 || y >= reference_y { return Ok(source); }
    let residual = ((reference_y / y).ln() - DARK_DEADZONE_LOG).max(0.0).min(MAX_RESIDUAL_LOG);
    if residual == 0.0 { return Ok(source); }
    let requested = (-f64::from(amount) * MAX_GAIN * f64::from(coverage) * residual).exp();
    if !requested.is_finite() || requested <= 0.0 { return Err(PIXEL_ERROR); }
    let peak = rgb.into_iter().fold(0.0_f64, f64::max);
    // One common scalar preserves linear RGB ratios. No per-channel clipping.
    let feasible = if requested > 1.0 {
        requested.min(1.0 / peak)
    } else { requested };
    if feasible == 1.0 { return Ok(source); }
    // Interior rounding protection applies only when gamut actually limits lift.
    let gain = if feasible < requested { feasible * (1.0 - 1e-12) } else { feasible };
    let result = rgb.map(|v| v * gain);
    if !result.iter().all(|v| v.is_finite() && (0.0..=1.0).contains(v)) { return Err(PIXEL_ERROR); }
    let encoded = result.map(encode);
    if !encoded.iter().copied().all(unit) { return Err(PIXEL_ERROR); }
    Ok(encoded)
}

/// Strict safe entry. Requested pixels all require real reference evidence.
/// Output is untouched on every returned error/cancellation. Final publication
/// is a single non-cancellable copy after the last cancellation poll.
pub fn apply_into<F: FnMut() -> bool>(
    source: &[f32], target: &[f32], reference: &[f32], width: usize, height: usize,
    amount: f32, radius: usize, output: &mut [f32], mut cancelled: F,
) -> Result<(), i32> {
    let pixels = admit(width, height)?;
    let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
    if source.len() != channels || target.len() != pixels || reference.len() != pixels
        || output.len() != channels { return Err(ABI_ERROR); }
    if !control(amount) || !(MIN_RADIUS..=MAX_RADIUS).contains(&radius) { return Err(SETTINGS_ERROR); }
    let mut requested = false;
    for i in 0..pixels {
        if i % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
        if !unit(target[i]) || !unit(reference[i])
            || !source[3*i..3*i+3].iter().copied().all(unit)
            || (target[i] > 0.0 && reference[i] > 0.0) { return Err(PIXEL_ERROR); }
        requested |= target[i] > 0.0;
    }
    if amount == 0.0 || !requested {
        poll(&mut cancelled)?;
        output.copy_from_slice(source);
        return Ok(());
    }
    let rows = horizontal(source, reference, width, height, radius, &mut cancelled)?;
    let mut staged = Vec::new();
    staged.try_reserve_exact(channels).map_err(|_| RESOURCE_ERROR)?;
    for i in 0..pixels {
        if i % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
        staged.extend_from_slice(&source[3*i..3*i+3]);
    }
    for x in 0..width {
        poll(&mut cancelled)?;
        let mut sum = [0.0_f64; 4];
        for y in 0..=radius.min(height - 1) {
            for c in 0..4 { sum[c] += rows[y * width + x][c]; }
        }
        for y in 0..height {
            if y % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
            let i = y * width + x;
            if target[i] > 0.0 {
                // Validate each requested pixel, including black/bright pixels;
                // unsupported source is never disguised as a successful edit.
                let baseline = reference_y(sum)?;
                let pixel = [source[3*i], source[3*i+1], source[3*i+2]];
                staged[3*i..3*i+3].copy_from_slice(&adjusted(pixel, baseline, target[i], amount)?);
            }
            if y >= radius {
                for c in 0..4 { sum[c] -= rows[(y - radius) * width + x][c]; }
            }
            if y + radius + 1 < height {
                for c in 0..4 { sum[c] += rows[(y + radius + 1) * width + x][c]; }
            }
        }
    }
    poll(&mut cancelled)?;
    output.copy_from_slice(&staged);
    Ok(())
}

fn span(pointer: *const f32, length: usize) -> Result<(usize, usize), i32> {
    let start = pointer as usize;
    let bytes = length.checked_mul(mem::size_of::<f32>()).ok_or(ABI_ERROR)?;
    if pointer.is_null() || start % mem::align_of::<f32>() != 0 || bytes > isize::MAX as usize {
        return Err(ABI_ERROR);
    }
    Ok((start, start.checked_add(bytes).ok_or(ABI_ERROR)?))
}
fn overlaps(a: (usize, usize), b: (usize, usize)) -> bool { a.0 < b.1 && b.0 < a.1 }

#[no_mangle]
pub extern "C" fn lrt_brow_enhance_abi() -> u32 { 1 }

/// ABI 1. Lengths count floats. Source is ORIGINAL effective source, not a prior
/// brow enhancement. Host authenticates face, original source, grid and anatomy.
/// # Safety
/// All spans must be live aligned allocations of stated sizes. Read-only inputs
/// remain immutable and may overlap; output is exclusive and overlaps no input.
/// Callback/context remain live; callback must not unwind, reenter or mutate.
/// Range checks cannot prove allocation ownership. Panic containment does not
/// contain invalid pointers, foreign faults or process aborts.
#[no_mangle]
pub unsafe extern "C" fn lrt_brow_enhance_apply_v1(
    source: *const f32, source_len: usize, target: *const f32, target_len: usize,
    reference: *const f32, reference_len: usize, width: usize, height: usize,
    amount: f32, radius: usize, output: *mut f32, output_len: usize,
    cancel: Cancel, context: *mut c_void,
) -> i32 {
    let result = panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(), i32> {
        let pixels = admit(width, height)?;
        let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
        if source_len != channels || target_len != pixels || reference_len != pixels
            || output_len != channels { return Err(ABI_ERROR); }
        if !control(amount) || !(MIN_RADIUS..=MAX_RADIUS).contains(&radius) { return Err(SETTINGS_ERROR); }
        let output_span = span(output, output_len)?;
        for input in [span(source, source_len)?, span(target, target_len)?, span(reference, reference_len)?] {
            if overlaps(input, output_span) { return Err(ABI_ERROR); }
        }
        apply_into(slice::from_raw_parts(source, source_len), slice::from_raw_parts(target, target_len),
            slice::from_raw_parts(reference, reference_len), width, height, amount, radius,
            slice::from_raw_parts_mut(output, output_len),
            || cancel.map_or(false, |function| function(context) != 0))
    }));
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

#[cfg(test)]
mod tests;
