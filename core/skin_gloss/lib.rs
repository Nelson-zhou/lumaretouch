// SPDX-License-Identifier: GPL-3.0-or-later
//! Original source-measured face-skin highlight appearance edit. AUTHORED / UNRUN.
//! Encoded working-sRGB-D65 float32 SDR at the boundary; linear-light math inside.
//! This is not physical reflectance recovery, a skin detector or highlight synthesis.

use std::{ffi::c_void, mem, panic, slice};

pub const MAX_PIXELS: usize = 32_000_000;
pub const MAX_DIMENSION: usize = 65_536;
pub const MIN_RADIUS: usize = 2;
pub const MAX_RADIUS: usize = 256;
pub const NATIVE_SCRATCH_BYTES_PER_PIXEL: usize = 44;
pub const NATIVE_TOTAL_BYTES_PER_PIXEL: usize = 84;
pub const MAX_WORKING_BYTES: usize = 3 * 1024 * 1024 * 1024;
pub const POLL_PIXELS: usize = 256;
pub const MAX_GAIN: f64 = 0.65;
pub const MAX_SUPPRESSION_MEAN_FRACTION: f64 = 0.20;
pub const MAX_SUPPRESSION_MIN_FRACTION: f64 = 0.25;
pub const ABI_ERROR: i32 = 1;
pub const SETTINGS_ERROR: i32 = 2;
pub const PIXEL_ERROR: i32 = 3;
pub const CANCELLED: i32 = 4;
pub const RESOURCE_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;
pub type Cancel = Option<extern "C" fn(*mut c_void) -> i32>;
type Rgb = [f64; 3];

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
fn linear(source: &[f32], i: usize) -> Rgb {
    std::array::from_fn(|c| decode(f64::from(source[3 * i + c])))
}
fn mean(rgb: Rgb) -> f64 { (rgb[0] + rgb[1] + rgb[2]) / 3.0 }
fn dot(a: Rgb, b: Rgb) -> f64 { a[0] * b[0] + a[1] * b[1] + a[2] * b[2] }
fn norm(value: Rgb) -> f64 { dot(value, value).sqrt() }
fn opponent(rgb: Rgb) -> Rgb {
    let m = mean(rgb);
    rgb.map(|v| v - m)
}
fn luminance(rgb: Rgb) -> f64 { dot(rgb, [0.2126, 0.7152, 0.0722]) }
fn smooth(low: f64, high: f64, value: f64) -> f64 {
    // Only a bounded evidence gate, never RGB clipping.
    let t = ((value - low) / (high - low)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}
fn reliable(source: &[f32], i: usize, rgb: Rgb) -> f64 {
    let peak = source[3 * i..3 * i + 3].iter().copied().fold(0.0_f32, f32::max);
    smooth(0.008, 0.035, luminance(rgb))
        * (1.0 - smooth(0.96, 0.995, f64::from(peak)))
}

/// Weighted local source-only statistics: w, w², w*RGB, w*opponent direction.
/// Ninth lane is reliable source-support mass, independent of chroma weighting.
fn sample(reference: &[f32], coverage: &[f32], i: usize) -> [f64; 9] {
    if coverage[i] == 0.0 { return [0.0; 9]; }
    let rgb = linear(reference, i);
    let reliability = reliable(reference, i, rgb) * f64::from(coverage[i]);
    let chroma = opponent(rgb);
    let magnitude = norm(chroma);
    let average = mean(rgb);
    if reliability == 0.0 || average <= 0.0 || magnitude <= 1e-12 { return [0.0; 9]; }
    let relative = magnitude / average;
    // Measured relative chroma favours local body-colour evidence over neutral
    // additions. No fixed skin hue, ethnicity classifier or proprietary weights.
    let weight = reliability * relative * relative / (relative * relative + 0.16);
    [weight, weight * weight, weight * rgb[0], weight * rgb[1], weight * rgb[2],
     weight * chroma[0] / magnitude, weight * chroma[1] / magnitude,
     weight * chroma[2] / magnitude, reliability]
}

fn zeros<const K: usize, F: FnMut() -> bool>(
    count: usize, cancelled: &mut F,
) -> Result<Vec<[f32; K]>, i32> {
    poll(cancelled)?;
    let mut values = Vec::new();
    values.try_reserve_exact(count).map_err(|_| RESOURCE_ERROR)?;
    for i in 0..count {
        if i % POLL_PIXELS == 0 { poll(cancelled)?; }
        values.push([0.0; K]);
    }
    Ok(values)
}

/// Bounded separable box sum with actual in-domain samples, no edge replication.
/// O(K*N), independent of radius; each sample fetched at most twice per row.
fn horizontal<const K: usize, F: FnMut() -> bool, S: Fn(usize) -> [f64; K]>(
    width: usize, height: usize, radius: usize, sample_at: S, cancelled: &mut F,
) -> Result<Vec<[f32; K]>, i32> {
    let mut result = zeros::<K, F>(width * height, cancelled)?;
    for y in 0..height {
        poll(cancelled)?;
        let mut sum = [0.0_f64; K];
        for x in 0..=radius.min(width - 1) {
            let value = sample_at(y * width + x);
            for c in 0..K { sum[c] += value[c]; }
        }
        for x in 0..width {
            if x % POLL_PIXELS == 0 { poll(cancelled)?; }
            result[y * width + x] = sum.map(|v| v as f32);
            if x >= radius {
                let value = sample_at(y * width + x - radius);
                for c in 0..K { sum[c] -= value[c]; }
            }
            if x + radius + 1 < width {
                let value = sample_at(y * width + x + radius + 1);
                for c in 0..K { sum[c] += value[c]; }
            }
        }
    }
    Ok(result)
}

fn window_size(position: usize, length: usize, radius: usize) -> usize {
    (position + radius).min(length - 1) - position.saturating_sub(radius) + 1
}

/// Independent original bounded evidence, NOT a solved physical albedo layer.
/// Each raw field is [neutral-light excess * evidence, evidence], without amount,
/// current RGB or final coverage mixing. At least 12 effective local observations
/// and coherent non-achromatic body colour are required before fitting.
fn candidate(reference: &[f32], coverage: &[f32], i: usize, stats: [f64; 9], area: usize) -> [f32; 2] {
    if coverage[i] == 0.0 || stats[0] < 4.0 || stats[1] <= 0.0
        || stats[0] * stats[0] / stats[1] < 12.0 || stats[8] / (area as f64) < 0.35 {
        return [0.0; 2];
    }
    let p = linear(reference, i);
    let reliability = reliable(reference, i, p);
    if reliability == 0.0 { return [0.0; 2]; }
    let q = [stats[2] / stats[0], stats[3] / stats[0], stats[4] / stats[0]];
    let p_mean = mean(p);
    let q_mean = mean(q);
    let p_chroma = opponent(p);
    let q_chroma = opponent(q);
    let q_norm = norm(q_chroma);
    let p_norm = norm(p_chroma);
    if q_mean <= 0.0 || p_mean <= 0.0 || q_norm <= 1e-10 { return [0.0; 2]; }
    let q_relative = q_norm / q_mean;
    let p_relative = p_norm / p_mean;
    let coherence = norm([stats[5], stats[6], stats[7]]) / stats[0];
    // Project only onto measured opponent colour; neutral illumination is the
    // stated assumption, not an estimated or silently white-balanced illuminant.
    let diffuse_scale = dot(p_chroma, q_chroma) / (q_norm * q_norm);
    let specular_excess = p_mean - diffuse_scale * q_mean;
    let residual = norm(std::array::from_fn(|c| p_chroma[c] - diffuse_scale * q_chroma[c]))
        / p_norm.max(0.02 * p_mean);
    let q_y = luminance(q);
    let p_y = luminance(p);
    if q_y <= 0.0 || p_y <= 0.0 || specular_excess <= 0.0 { return [0.0; 2]; }
    let evidence = reliability
        * smooth(0.035, 0.12, q_relative)
        * smooth(0.94, 0.985, coherence)
        * smooth(0.03, 0.20, (p_y - q_y) / q_y)
        * smooth(0.035, 0.18, (q_relative - p_relative) / q_relative)
        * smooth(0.015, 0.12, specular_excess / p_y)
        * smooth(0.55, 0.80, diffuse_scale)
        * (1.0 - smooth(1.20, 1.60, diffuse_scale))
        * (1.0 - smooth(0.02, 0.08, residual));
    if !evidence.is_finite() || evidence <= 0.0 { return [0.0; 2]; }
    // A measured positive excess may not remove more than the minimum source
    // linear channel, even before the 0.65 signed appearance-control bound.
    let excess = specular_excess.min(p.into_iter().fold(f64::INFINITY, f64::min));
    [(excess * evidence) as f32, evidence as f32]
}

fn evidence_field<F: FnMut() -> bool>(
    reference: &[f32], coverage: &[f32], width: usize, height: usize, radius: usize,
    cancelled: &mut F,
) -> Result<Vec<[f32; 2]>, i32> {
    let rows = horizontal(width, height, radius, |i| sample(reference, coverage, i), cancelled)?;
    let mut raw = zeros::<2, F>(width * height, cancelled)?;
    for x in 0..width {
        poll(cancelled)?;
        let mut sum = [0.0_f64; 9];
        for y in 0..=radius.min(height - 1) {
            for c in 0..9 { sum[c] += f64::from(rows[y * width + x][c]); }
        }
        for y in 0..height {
            if y % POLL_PIXELS == 0 { poll(cancelled)?; }
            let wx = window_size(x, width, radius);
            let wy = window_size(y, height, radius);
            if wx >= 3 && wy >= 3 {
                raw[y * width + x] = candidate(reference, coverage, y * width + x, sum, wx * wy);
            }
            if y >= radius {
                for c in 0..9 { sum[c] -= f64::from(rows[(y - radius) * width + x][c]); }
            }
            if y + radius + 1 < height {
                for c in 0..9 { sum[c] += f64::from(rows[(y + radius + 1) * width + x][c]); }
            }
        }
    }
    Ok(raw)
}

fn adjusted(current: [f32; 3], delta: f64) -> Result<[f32; 3], i32> {
    if delta == 0.0 || current.iter().all(|&v| v == 0.0)
        || current.iter().all(|&v| v == 1.0) { return Ok(current); }
    let rgb = current.map(|v| decode(f64::from(v)));
    let headroom = if delta > 0.0 {
        rgb.into_iter().map(|v| 1.0 - v).fold(f64::INFINITY, f64::min)
    } else {
        // Prevent aggressive neutral subtraction from magnifying current-stage
        // chroma after colour/finish edits. Mean retention >=80%, darkest
        // channel retention >=75%; relative opponent chroma rises at most25%.
        (MAX_SUPPRESSION_MEAN_FRACTION * mean(rgb)).min(
            MAX_SUPPRESSION_MIN_FRACTION * rgb.into_iter().fold(f64::INFINITY, f64::min))
    };
    if headroom <= 0.0 { return Ok(current); }
    // One common feasible scalar for the neutral vector, not RGB-channel clamp.
    // A small interior factor protects roundoff without changing colour direction.
    let step = delta.signum() * delta.abs().min(headroom * (1.0 - 1e-12));
    if step == 0.0 { return Ok(current); }
    let target = rgb.map(|v| v + step);
    if !target.iter().all(|v| v.is_finite() && (0.0..=1.0).contains(v)) { return Err(PIXEL_ERROR); }
    let encoded = target.map(encode);
    if !encoded.iter().copied().all(unit) { return Err(PIXEL_ERROR); }
    Ok(encoded)
}

/// Safe public slice entry. All inputs validated even when amount/support is zero.
/// No output is valid after an error or cancellation; callers own publication.
pub fn apply_into<F: FnMut() -> bool>(
    current: &[f32], reference: &[f32], coverage: &[f32], width: usize, height: usize,
    amount: f32, radius: usize, output: &mut [f32], mut cancelled: F,
) -> Result<(), i32> {
    let pixels = admit(width, height)?;
    let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
    if current.len() != channels || reference.len() != channels
        || coverage.len() != pixels || output.len() != channels { return Err(ABI_ERROR); }
    if !control(amount) || !(MIN_RADIUS..=MAX_RADIUS).contains(&radius) { return Err(SETTINGS_ERROR); }
    let mut any_support = false;
    for i in 0..pixels {
        if i % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
        if !unit(coverage[i]) || !current[3*i..3*i+3].iter().copied().all(unit)
            || !reference[3*i..3*i+3].iter().copied().all(unit) { return Err(PIXEL_ERROR); }
        any_support |= coverage[i] > 0.0;
    }
    // Bitwise copies avoid transfer-curve round trips on all no-effect paths.
    for i in 0..pixels {
        if i % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
        output[3*i..3*i+3].copy_from_slice(&current[3*i..3*i+3]);
    }
    if amount == 0.0 || !any_support { return poll(&mut cancelled); }
    let raw = evidence_field(reference, coverage, width, height, radius, &mut cancelled)?;
    let rows = horizontal(width, height, radius, |i| raw[i].map(f64::from), &mut cancelled)?;
    for x in 0..width {
        poll(&mut cancelled)?;
        let mut sum = [0.0_f64; 2];
        for y in 0..=radius.min(height - 1) {
            for c in 0..2 { sum[c] += f64::from(rows[y * width + x][c]); }
        }
        for y in 0..height {
            if y % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
            let i = y * width + x;
            if coverage[i] > 0.0 && raw[i][1] > 0.0 && sum[1] >= 3.0 && sum[0] > 0.0 {
                let area = window_size(x, width, radius) * window_size(y, height, radius);
                // Region-scale evidence rejects isolated bright pores/noise. No
                // centre evidence means EXACT copy, even beside a valid highlight.
                let regional = smooth(0.04, 0.16, sum[1] / area as f64);
                let local_excess = f64::from(raw[i][0]) / f64::from(raw[i][1]);
                let smoothed_excess = (sum[0] / sum[1]).min(local_excess);
                let delta = f64::from(amount) * MAX_GAIN * f64::from(coverage[i])
                    * f64::from(raw[i][1]) * regional * smoothed_excess;
                let source = [current[3*i], current[3*i+1], current[3*i+2]];
                output[3*i..3*i+3].copy_from_slice(&adjusted(source, delta)?);
            }
            if y >= radius {
                for c in 0..2 { sum[c] -= f64::from(rows[(y - radius) * width + x][c]); }
            }
            if y + radius + 1 < height {
                for c in 0..2 { sum[c] += f64::from(rows[(y + radius + 1) * width + x][c]); }
            }
        }
    }
    poll(&mut cancelled)
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
pub extern "C" fn lrt_skin_gloss_abi() -> u32 { 1 }

/// ABI 1, encoded working-sRGB-D65 SDR HWC buffers; lengths count f32 elements.
/// # Safety
/// All spans must be live, aligned, readable/writable allocations of stated sizes.
/// Inputs remain immutable and may overlap each other, but output must overlap
/// no input and be exclusively writable. Callback/context stay alive; callback
/// must not unwind, reenter or mutate these buffers. Discard output on failure.
/// Panic containment cannot repair invalid pointers, foreign faults or aborts.
#[no_mangle]
pub unsafe extern "C" fn lrt_skin_gloss_apply_v1(
    current: *const f32, current_len: usize, reference: *const f32, reference_len: usize,
    coverage: *const f32, coverage_len: usize, width: usize, height: usize,
    amount: f32, radius: usize, output: *mut f32, output_len: usize,
    cancel: Cancel, context: *mut c_void,
) -> i32 {
    let result = panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(), i32> {
        let pixels = admit(width, height)?;
        let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
        if current_len != channels || reference_len != channels
            || coverage_len != pixels || output_len != channels { return Err(ABI_ERROR); }
        if !control(amount) || !(MIN_RADIUS..=MAX_RADIUS).contains(&radius) { return Err(SETTINGS_ERROR); }
        let output_span = span(output, output_len)?;
        for input in [span(current, current_len)?, span(reference, reference_len)?, span(coverage, coverage_len)?] {
            if overlaps(input, output_span) { return Err(ABI_ERROR); }
        }
        apply_into(slice::from_raw_parts(current, current_len),
            slice::from_raw_parts(reference, reference_len), slice::from_raw_parts(coverage, coverage_len),
            width, height, amount, radius, slice::from_raw_parts_mut(output, output_len),
            || cancel.map_or(false, |function| function(context) != 0))
    }));
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

#[cfg(test)]
mod tests;
