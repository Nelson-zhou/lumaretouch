// SPDX-License-Identifier: GPL-3.0-or-later
//! Original two-scale, source-measured skin texture/fine sharpening. AUTHORED / UNRUN.
//! Not skin detection, AI reconstruction, blemish removal or physical reflectance recovery.
//! Encoded working-sRGB-D65 SDR boundary; linear-light/log-luminance processing.

use std::{ffi::c_void, mem, panic, slice};

pub const MAX_PIXELS: usize = 32_000_000;
pub const MAX_DIMENSION: usize = 65_536;
pub const MIN_RADIUS: usize = 4;
pub const MAX_RADIUS: usize = 256;
pub const NATIVE_SCRATCH_BYTES_PER_PIXEL: usize = 72;
pub const NATIVE_TOTAL_BYTES_PER_PIXEL: usize = 112;
pub const MAX_WORKING_BYTES: usize = 4 * 1024 * 1024 * 1024;
pub const POLL_PIXELS: usize = 256;
pub const TEXTURE_GAIN: f64 = 0.75;
pub const CLARITY_GAIN: f64 = 0.55;
pub const TEXTURE_BAND_LIMIT: f64 = 0.08;
pub const FINE_BAND_LIMIT: f64 = 0.025;
pub const ABI_ERROR: i32 = 1;
pub const SETTINGS_ERROR: i32 = 2;
pub const PIXEL_ERROR: i32 = 3;
pub const CANCELLED: i32 = 4;
pub const RESOURCE_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;
pub type Cancel = Option<extern "C" fn(*mut c_void) -> i32>;

fn unit(value: f32) -> bool { value.is_finite() && (0.0..=1.0).contains(&value) }
fn controls(texture: f32, clarity: f32) -> bool {
    texture.is_finite() && (-1.0..=1.0).contains(&texture) && unit(clarity)
}
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
fn luminance(reference: &[f32], i: usize) -> f64 {
    0.2126 * decode(f64::from(reference[3*i]))
        + 0.7152 * decode(f64::from(reference[3*i+1]))
        + 0.0722 * decode(f64::from(reference[3*i+2]))
}
fn smooth(low: f64, high: f64, value: f64) -> f64 {
    // This clamps a permission/evidence gate, not RGB output.
    let t = ((value - low) / (high - low)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}
fn source_reliability(reference: &[f32], i: usize) -> f64 {
    let peak = reference[3*i..3*i+3].iter().copied().fold(0.0_f32, f32::max);
    smooth(0.005, 0.03, luminance(reference, i))
        * (1.0 - smooth(0.94, 0.995, f64::from(peak)))
}
fn filled<T: Clone, F: FnMut() -> bool>(
    count: usize, value: T, cancelled: &mut F,
) -> Result<Vec<T>, i32> {
    poll(cancelled)?;
    let mut values = Vec::new();
    values.try_reserve_exact(count).map_err(|_| RESOURCE_ERROR)?;
    for i in 0..count {
        if i % POLL_PIXELS == 0 { poll(cancelled)?; }
        values.push(value.clone());
    }
    Ok(values)
}

/// Real, truncated-in-domain box sums, with no padding or edge replication.
/// f64 rows avoid cancellation of small log-luminance variances in f32 moments.
fn horizontal<const K: usize, F: FnMut() -> bool, S: Fn(usize) -> [f64; K]>(
    width: usize, height: usize, radius: usize, sample_at: S, cancelled: &mut F,
) -> Result<Vec<[f64; K]>, i32> {
    let mut rows = filled(width * height, [0.0; K], cancelled)?;
    for y in 0..height {
        poll(cancelled)?;
        let mut sum = [0.0; K];
        for x in 0..=radius.min(width - 1) {
            if x % POLL_PIXELS == 0 { poll(cancelled)?; }
            let value = sample_at(y * width + x);
            for c in 0..K { sum[c] += value[c]; }
        }
        for x in 0..width {
            if x % POLL_PIXELS == 0 { poll(cancelled)?; }
            rows[y * width + x] = sum;
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
    Ok(rows)
}
fn window_size(position: usize, length: usize, radius: usize) -> usize {
    (position + radius).min(length - 1) - position.saturating_sub(radius) + 1
}
fn area(i: usize, width: usize, height: usize, radius: usize) -> usize {
    window_size(i % width, width, radius) * window_size(i / width, height, radius)
}
fn vertical<const K: usize, F: FnMut() -> bool, V: FnMut(usize, [f64; K]) -> Result<(), i32>>(
    rows: &[[f64; K]], width: usize, height: usize, radius: usize,
    mut visit: V, cancelled: &mut F,
) -> Result<(), i32> {
    for x in 0..width {
        poll(cancelled)?;
        let mut sum = [0.0; K];
        for y in 0..=radius.min(height - 1) {
            if y % POLL_PIXELS == 0 { poll(cancelled)?; }
            for c in 0..K { sum[c] += rows[y * width + x][c]; }
        }
        for y in 0..height {
            if y % POLL_PIXELS == 0 { poll(cancelled)?; }
            visit(y * width + x, sum)?;
            if y >= radius {
                for c in 0..K { sum[c] -= rows[(y - radius) * width + x][c]; }
            }
            if y + radius + 1 < height {
                for c in 0..K { sum[c] += rows[(y + radius + 1) * width + x][c]; }
            }
        }
    }
    Ok(())
}

/// Independent parallel scale, NOT a second filter on the first scale's output.
/// Invalid coefficients have ZERO coefficient-domain support. Never average
/// their zero-filled a/b values as observations or let them influence q.
/// A NaN base sentinel denotes unavailable evidence and is never rendered.
fn guided_base<F: FnMut() -> bool>(
    log_y: &[f64], coverage: &[f32], width: usize, height: usize,
    radius: usize, epsilon: f64, cancelled: &mut F,
) -> Result<Vec<f64>, i32> {
    let pixels = width * height;
    let rows = horizontal(width, height, radius, |i| {
        let w = f64::from(coverage[i]);
        if w == 0.0 { return [0.0; 4]; }
        [w, w*w, w*log_y[i], w*log_y[i]*log_y[i]]
    }, cancelled)?;
    // Weighted a, weighted b, effective coefficient-domain support.
    let mut coefficients = filled(pixels, [0.0; 3], cancelled)?;
    vertical(&rows, width, height, radius, |i, sum| {
        let w = f64::from(coverage[i]);
        if w == 0.0 || sum[0] < 1.0 || sum[1] <= 0.0
            || sum[0]*sum[0] / sum[1] < 4.0
            || sum[0] / (area(i, width, height, radius) as f64) < 0.20 {
            return Ok(());
        }
        let mean = sum[2] / sum[0];
        // Rounding may make constant-signal variance just below zero.
        let variance = (sum[3] / sum[0] - mean*mean).max(0.0);
        let a = variance / (variance + epsilon);
        let b = (1.0 - a) * mean;
        if !a.is_finite() || !b.is_finite() { return Err(PIXEL_ERROR); }
        coefficients[i] = [w*a, w*b, w];
        Ok(())
    }, cancelled)?;
    drop(rows); // Required by the documented 72 B/pixel peak scratch bound.
    let rows = horizontal(width, height, radius, |i| coefficients[i], cancelled)?;
    let mut base = filled(pixels, f64::NAN, cancelled)?;
    vertical(&rows, width, height, radius, |i, sum| {
        if coefficients[i][2] == 0.0 || sum[2] < 1.0
            || sum[2] / (area(i, width, height, radius) as f64) < 0.20 {
            return Ok(());
        }
        let value = (sum[0]*log_y[i] + sum[1]) / sum[2];
        if !value.is_finite() { return Err(PIXEL_ERROR); }
        base[i] = value;
        Ok(())
    }, cancelled)?;
    Ok(base)
}

fn cross(i: usize, width: usize, height: usize) -> Option<[usize; 4]> {
    let x = i % width;
    let y = i / width;
    if x == 0 || x + 1 >= width || y == 0 || y + 1 >= height { return None; }
    Some([i-1, i+1, i-width, i+width])
}
/// A conservative high-frequency noise proxy, not a camera noise calibration.
/// Requiring real supported axial neighbors avoids substituting mask/background
/// zeros. Genuine Nyquist texture can be rejected along with noise.
fn noise_sample(log_y: &[f64], fine: &[f64], coverage: &[f32], i: usize,
                width: usize, height: usize) -> [f64; 5] {
    if coverage[i] == 0.0 || !fine[i].is_finite() { return [0.0; 5]; }
    let neighbors = match cross(i, width, height) { Some(value) => value, None => return [0.0; 5] };
    let mut w = f64::from(coverage[i]);
    for j in neighbors { w = w.min(f64::from(coverage[j])); }
    if w == 0.0 { return [0.0; 5]; }
    let laplacian = 4.0*log_y[i] - neighbors.iter().map(|&j| log_y[j]).sum::<f64>();
    let residual = log_y[i] - fine[i];
    [w, w*w, w*residual, w*residual*residual, w*laplacian*laplacian/20.0]
}
fn edge_gate(log_y: &[f64], coverage: &[f32], i: usize, width: usize, height: usize) -> f64 {
    let neighbors = match cross(i, width, height) { Some(value) => value, None => return 0.0 };
    let mut gradient = 0.0_f64;
    // No unsupported intensity is consulted, even for a conservative edge gate.
    for j in neighbors {
        if coverage[j] == 0.0 { return 0.0; }
        gradient = gradient.max((log_y[i] - log_y[j]).abs());
    }
    1.0 - smooth(0.10, 0.35, gradient)
}
fn band(value: f64, limit: f64) -> f64 {
    // Explicit deadzone makes a constant field an exact no-op despite moments'
    // roundoff. This is not output blur, per-channel clipping or a global curve.
    if value.abs() <= 1e-10 { 0.0 } else { limit * (value / limit).tanh() }
}
fn adjusted(current: [f32; 3], delta: f64) -> Result<[f32; 3], i32> {
    if delta == 0.0 || current.iter().all(|&v| v == 0.0)
        || current.iter().all(|&v| v == 1.0) { return Ok(current); }
    let rgb = current.map(|v| decode(f64::from(v)));
    let peak = rgb.into_iter().fold(0.0_f64, f64::max);
    if peak == 0.0 { return Ok(current); }
    // One common feasible gain preserves linear-RGB channel ratios. Upper-gamut
    // restraint can reduce positive detail; it never clips separate channels.
    let gain = if delta > 0.0 {
        delta.exp().min(1.0 + (1.0 / peak - 1.0).max(0.0) * (1.0 - 1e-12))
    } else { delta.exp() };
    if gain == 1.0 { return Ok(current); }
    let target = rgb.map(|v| v * gain);
    if !target.iter().all(|v| v.is_finite() && (0.0..=1.0).contains(v)) { return Err(PIXEL_ERROR); }
    let encoded = target.map(encode);
    if !encoded.iter().copied().all(unit) { return Err(PIXEL_ERROR); }
    Ok(encoded)
}

/// All source/current/mask values are validated, even on neutral paths.
/// Only the current pixel is corrected; all scale/evidence fields use reference.
/// Output must be discarded after ANY error; safe/FFI callers own publication.
pub fn apply_into<F: FnMut() -> bool>(
    current: &[f32], reference: &[f32], coverage: &[f32], width: usize, height: usize,
    texture: f32, clarity: f32, radius: usize, output: &mut [f32], mut cancelled: F,
) -> Result<(), i32> {
    let pixels = admit(width, height)?;
    let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
    if current.len() != channels || reference.len() != channels
        || coverage.len() != pixels || output.len() != channels { return Err(ABI_ERROR); }
    if !controls(texture, clarity) || !(MIN_RADIUS..=MAX_RADIUS).contains(&radius) { return Err(SETTINGS_ERROR); }
    let mut any_support = false;
    for i in 0..pixels {
        if i % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
        if !unit(coverage[i]) || !current[3*i..3*i+3].iter().copied().all(unit)
            || !reference[3*i..3*i+3].iter().copied().all(unit) { return Err(PIXEL_ERROR); }
        any_support |= coverage[i] > 0.0;
    }
    for i in 0..pixels {
        if i % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
        output[3*i..3*i+3].copy_from_slice(&current[3*i..3*i+3]);
    }
    if (texture == 0.0 && clarity == 0.0) || !any_support { return poll(&mut cancelled); }
    let mut log_y = filled(pixels, 0.0_f64, &mut cancelled)?;
    for i in 0..pixels {
        if i % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
        if coverage[i] > 0.0 { log_y[i] = luminance(reference, i).max(1e-6).ln(); }
    }
    let fine_radius = (radius / 4).max(1);
    let fine = guided_base(&log_y, coverage, width, height, fine_radius, 0.04_f64.powi(2), &mut cancelled)?;
    let coarse = guided_base(&log_y, coverage, width, height, radius, 0.11_f64.powi(2), &mut cancelled)?;
    let rows = horizontal(width, height, fine_radius,
        |i| noise_sample(&log_y, &fine, coverage, i, width, height), &mut cancelled)?;
    vertical(&rows, width, height, fine_radius, |i, sum| {
        if coverage[i] == 0.0 || !fine[i].is_finite() || !coarse[i].is_finite() { return Ok(()); }
        let evidence = source_reliability(reference, i) * edge_gate(&log_y, coverage, i, width, height);
        if evidence == 0.0 { return Ok(()); }
        let mut fine_gate = 0.0;
        if sum[0] >= 1.0 && sum[1] > 0.0 && sum[0]*sum[0]/sum[1] >= 4.0
            && sum[0] / (area(i, width, height, fine_radius) as f64) >= 0.20 {
            let residual_mean = sum[2] / sum[0];
            let energy = (sum[3] / sum[0] - residual_mean*residual_mean).max(0.0);
            let noise = (sum[4] / sum[0]).max(0.0);
            fine_gate = ((energy - 1.25*noise).max(0.0) / (energy + 0.002_f64.powi(2))).min(1.0);
        }
        let medium = band(fine[i] - coarse[i], TEXTURE_BAND_LIMIT);
        let detail = band(log_y[i] - fine[i], FINE_BAND_LIMIT);
        let delta = f64::from(coverage[i]) * evidence
            * (f64::from(texture)*TEXTURE_GAIN*medium
                + f64::from(clarity)*CLARITY_GAIN*fine_gate*detail);
        if !delta.is_finite() { return Err(PIXEL_ERROR); }
        let pixel = [current[3*i], current[3*i+1], current[3*i+2]];
        output[3*i..3*i+3].copy_from_slice(&adjusted(pixel, delta)?);
        Ok(())
    }, &mut cancelled)?;
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
pub extern "C" fn lrt_skin_texture_abi() -> u32 { 1 }

/// # Safety
/// All spans must be live aligned allocations of the stated element lengths.
/// Inputs stay immutable; output is exclusively writable and overlaps no input.
/// Inputs may overlap one another. Callback/context remain valid; callback must
/// not unwind, reenter or mutate buffers. Discard output after nonzero status.
/// Panic containment cannot protect invalid pointers, foreign faults or aborts.
#[no_mangle]
pub unsafe extern "C" fn lrt_skin_texture_apply_v1(
    current: *const f32, current_len: usize, reference: *const f32, reference_len: usize,
    coverage: *const f32, coverage_len: usize, width: usize, height: usize,
    texture: f32, clarity: f32, radius: usize, output: *mut f32, output_len: usize,
    cancel: Cancel, context: *mut c_void,
) -> i32 {
    let result = panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(), i32> {
        let pixels = admit(width, height)?;
        let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
        if current_len != channels || reference_len != channels
            || coverage_len != pixels || output_len != channels { return Err(ABI_ERROR); }
        if !controls(texture, clarity) || !(MIN_RADIUS..=MAX_RADIUS).contains(&radius) { return Err(SETTINGS_ERROR); }
        let output_span = span(output, output_len)?;
        for input in [span(current, current_len)?, span(reference, reference_len)?, span(coverage, coverage_len)?] {
            if overlaps(input, output_span) { return Err(ABI_ERROR); }
        }
        apply_into(slice::from_raw_parts(current, current_len),
            slice::from_raw_parts(reference, reference_len), slice::from_raw_parts(coverage, coverage_len),
            width, height, texture, clarity, radius, slice::from_raw_parts_mut(output, output_len),
            || cancel.map_or(false, |function| function(context) != 0))
    }));
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

#[cfg(test)]
mod tests;
