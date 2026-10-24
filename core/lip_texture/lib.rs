// SPDX-License-Identifier: GPL-3.0-or-later
//! Original paired-flank dark-furrow appearance edit. AUTHORED / UNRUN.
//! Not Steger's algorithm, learned repair, morphology, blur or inpainting.
//! Boundary: encoded working-sRGB-D65 SDR float32 RGB and real lip permission.

use std::{ffi::c_void, mem, panic, slice};

pub const MAX_PIXELS: usize = 32_000_000;
pub const MAX_DIMENSION: usize = 65_536;
pub const MIN_RADIUS: usize = 1;
pub const MAX_RADIUS: usize = 12;
pub const NATIVE_SCRATCH_BYTES_PER_PIXEL: usize = 28;
pub const NATIVE_TOTAL_BYTES_PER_PIXEL: usize = 56;
pub const MAX_WORKING_BYTES: usize = 3 * 1024 * 1024 * 1024;
pub const FIXED_ALLOWANCE: usize = 8 * 1024 * 1024;
pub const POLL_PIXELS: usize = 256;
pub const FULL_SUPPORT: f32 = 0.999;
pub const MAX_LIFT_FRACTION: f32 = 0.35;
pub const ABI_ERROR: i32 = 1;
pub const SETTINGS_ERROR: i32 = 2;
pub const PIXEL_ERROR: i32 = 3;
pub const CANCELLED: i32 = 4;
pub const RESOURCE_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;
pub type Cancel = Option<extern "C" fn(*mut c_void) -> i32>;
type Rgb = [f32; 3];

fn unit(value: f32) -> bool { value.is_finite() && (0.0..=1.0).contains(&value) }
fn poll<F: FnMut() -> bool>(cancelled: &mut F) -> Result<(), i32> {
    if cancelled() { Err(CANCELLED) } else { Ok(()) }
}
fn settings(amount: f32, across: [f32; 2], radius: usize) -> Result<(), i32> {
    if !unit(amount) || !(MIN_RADIUS..=MAX_RADIUS).contains(&radius)
        || !across.iter().all(|v| v.is_finite())
        || (across[0].hypot(across[1]) - 1.0).abs() > 0.0001 {
        return Err(SETTINGS_ERROR);
    }
    Ok(())
}
fn admit(width: usize, height: usize) -> Result<usize, i32> {
    if width == 0 || height == 0 || width > MAX_DIMENSION || height > MAX_DIMENSION {
        return Err(ABI_ERROR);
    }
    let pixels = width.checked_mul(height).ok_or(RESOURCE_ERROR)?;
    let bytes = pixels.checked_mul(NATIVE_TOTAL_BYTES_PER_PIXEL)
        .and_then(|n| n.checked_add(FIXED_ALLOWANCE)).ok_or(RESOURCE_ERROR)?;
    if pixels > MAX_PIXELS || bytes > MAX_WORKING_BYTES { return Err(RESOURCE_ERROR); }
    Ok(pixels)
}
fn decode(value: f32) -> f32 {
    if value <= 0.04045 { value / 12.92 }
    else { ((value + 0.055) / 1.055).powf(2.4) }
}
fn encode(value: f32) -> f32 {
    if value <= 0.0031308 { 12.92 * value }
    else { 1.055 * value.powf(1.0 / 2.4) - 0.055 }
}
fn luminance(rgb: Rgb) -> f32 { 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2] }
fn chromaticity(rgb: Rgb) -> Rgb {
    // All callers already require reliable luminance; no zero denominator.
    let sum = rgb[0] + rgb[1] + rgb[2];
    rgb.map(|v| v / sum)
}
fn max_difference(a: Rgb, b: Rgb) -> f32 {
    (0..3).map(|c| (a[c] - b[c]).abs()).fold(0.0, f32::max)
}
fn reliable(encoded: Rgb, linear: Rgb) -> bool {
    // No chromatic channel clipped at either endpoint; reject very dark and
    // near-saturated samples before interpolation, not after mixing them.
    encoded.iter().all(|v| *v > 0.001 && *v < 0.985)
        && luminance(linear) >= 0.02
}
fn reserve<T>(count: usize) -> Result<Vec<T>, i32> {
    let mut values = Vec::new();
    values.try_reserve_exact(count).map_err(|_| RESOURCE_ERROR)?;
    Ok(values)
}

/// An exact integer count of coverage holes. u32 is sufficient under 32M pixels.
/// The extra row/column is accounted for by FIXED_ALLOWANCE at admitted sizes.
fn bad_support<F: FnMut() -> bool>(
    coverage: &[f32], width: usize, height: usize, cancelled: &mut F,
) -> Result<Vec<u32>, i32> {
    let stride = width + 1;
    let count = stride.checked_mul(height + 1).ok_or(RESOURCE_ERROR)?;
    let mut sums = reserve(count)?;
    for i in 0..stride {
        if i % POLL_PIXELS == 0 { poll(cancelled)?; }
        sums.push(0_u32);
    }
    for y in 0..height {
        poll(cancelled)?;
        sums.push(0);
        let mut row_bad = 0_u32;
        for x in 0..width {
            if x % POLL_PIXELS == 0 { poll(cancelled)?; }
            row_bad += u32::from(coverage[y * width + x] < FULL_SUPPORT);
            sums.push(sums[y * stride + x + 1] + row_bad);
        }
    }
    Ok(sums)
}

fn supported(sums: &[u32], width: usize, height: usize, x: usize, y: usize, radius: usize) -> bool {
    // Every point of the entire square, not just sparse sample endpoints, must
    // be genuine permission. This also covers every bilinear vertex and every
    // connecting segment; a candidate cannot jump over a seam or tiny hole.
    let guard = 3 * radius;
    if x < guard || y < guard || x + guard >= width || y + guard >= height { return false; }
    let stride = width + 1;
    let (left, top, right, bottom) = (x - guard, y - guard, x + guard + 1, y + guard + 1);
    // Subtract vertical strips first to avoid unsigned underflow.
    sums[bottom * stride + right] - sums[top * stride + right]
        == sums[bottom * stride + left] - sums[top * stride + left]
}

/// Real bilinear footprint only. All four vertices must be allowed/reliable,
/// including zero-weight vertices at integer coordinates. Never clamp/repeat.
fn sample(
    source: &[f32], linear: &[Rgb], coverage: &[f32], width: usize, height: usize,
    x: f32, y: f32,
) -> Option<Rgb> {
    if !x.is_finite() || !y.is_finite() || x < 0.0 || y < 0.0 { return None; }
    let left = x.floor() as usize;
    let top = y.floor() as usize;
    if left + 1 >= width || top + 1 >= height { return None; }
    let ids = [top * width + left, top * width + left + 1,
               (top + 1) * width + left, (top + 1) * width + left + 1];
    for &i in &ids {
        let encoded = [source[3*i], source[3*i+1], source[3*i+2]];
        if coverage[i] < FULL_SUPPORT || !reliable(encoded, linear[i]) { return None; }
    }
    let (fx, fy) = (x - left as f32, y - top as f32);
    let weights = [(1.0-fx)*(1.0-fy), fx*(1.0-fy), (1.0-fx)*fy, fx*fy];
    Some(std::array::from_fn(|c| (0..4).map(|j| weights[j] * linear[ids[j]][c]).sum()))
}

/// Original bounded photometric policy, not an anatomical/disease classifier.
/// Flanks at +/-r and +/-2r must describe the same local colour on both sides.
fn section(center: Rgb, flanks: [Rgb; 4]) -> Option<f32> {
    let yc = luminance(center);
    let ys = flanks.map(luminance);
    let low = ys.iter().copied().fold(f32::INFINITY, f32::min);
    let high = ys.iter().copied().fold(f32::NEG_INFINITY, f32::max);
    let average: Rgb = std::array::from_fn(|c| flanks.iter().map(|v| v[c]).sum::<f32>() * 0.25);
    let ya = luminance(average);
    let residual = low - yc;
    // Both sides must be brighter. Flat fields, edges, deep creases/cavity-like
    // contrasts and broad shading are not eligible. Thresholds are original
    // conservative policy constants, not calibrated clinical/quality claims.
    if yc < 0.02 || residual < 0.0015_f32.max(0.02 * ya)
        || residual > 0.06_f32.min(0.30 * ya)
        || high - low > 0.002_f32.max(0.20 * residual) { return None; }
    let chroma = chromaticity(average);
    if flanks.iter().any(|p| max_difference(chromaticity(*p), chroma) > 0.018)
        || max_difference(chromaticity(center), chroma) > 0.025 { return None; }
    Some(residual)
}

fn oriented_residual(
    source: &[f32], linear: &[Rgb], coverage: &[f32], width: usize, height: usize,
    x: usize, y: usize, across: [f32; 2], radius: usize,
) -> Option<f32> {
    let along = [-across[1], across[0]];
    let r = radius as f32;
    let mut minimum = f32::INFINITY;
    let mut maximum = 0.0_f32;
    // Five cross-sections require persistence in both directions along a furrow.
    // A point/blob or a short discontinuity is not filled in or reconstructed.
    for step in [0.0, -1.0, 1.0, -2.0, 2.0] {
        let px = x as f32 + step * r * along[0];
        let py = y as f32 + step * r * along[1];
        let center = sample(source, linear, coverage, width, height, px, py)?;
        let mut flanks = [[0.0; 3]; 4];
        for (i, side) in [-1.0, 1.0, -2.0, 2.0].iter().enumerate() {
            flanks[i] = sample(source, linear, coverage, width, height,
                px + side * r * across[0], py + side * r * across[1])?;
        }
        let residual = section(center, flanks)?;
        minimum = minimum.min(residual);
        maximum = maximum.max(residual);
    }
    if minimum < 0.50 * maximum { return None; }
    Some(minimum)
}

fn directions(across: [f32; 2]) -> [[f32; 2]; 3] {
    let c = 0.866_025_4_f32;
    [across,
     [c*across[0] - 0.5*across[1], 0.5*across[0] + c*across[1]],
     [c*across[0] + 0.5*across[1], -0.5*across[0] + c*across[1]]]
}

/// Safe entry: output remains untouched on every error, including cancellation.
/// All inputs are validated even for amount zero or absent support. Computation
/// reads only original immutable source, never previously corrected pixels.
pub fn apply_into<F: FnMut() -> bool>(
    source: &[f32], coverage: &[f32], width: usize, height: usize,
    amount: f32, across: [f32; 2], radius: usize, output: &mut [f32], mut cancelled: F,
) -> Result<(), i32> {
    let pixels = admit(width, height)?;
    let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
    if source.len() != channels || coverage.len() != pixels || output.len() != channels {
        return Err(ABI_ERROR);
    }
    settings(amount, across, radius)?;
    let mut any_support = false;
    for i in 0..pixels {
        if i % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
        if !unit(coverage[i]) || !source[3*i..3*i+3].iter().copied().all(unit) { return Err(PIXEL_ERROR); }
        any_support |= coverage[i] >= FULL_SUPPORT;
    }
    if amount == 0.0 || !any_support {
        poll(&mut cancelled)?;
        output.copy_from_slice(source);
        return Ok(());
    }
    let mut linear = reserve(pixels)?;
    let mut private = reserve(channels)?;
    for i in 0..pixels {
        if i % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
        let encoded = [source[3*i], source[3*i+1], source[3*i+2]];
        linear.push(encoded.map(decode));
        private.extend_from_slice(&encoded);
    }
    let support = bad_support(coverage, width, height, &mut cancelled)?;
    let axes = directions(across);
    for y in 0..height {
        poll(&mut cancelled)?;
        for x in 0..width {
            if x % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
            let i = y * width + x;
            if !supported(&support, width, height, x, y, radius) { continue; }
            let mut residual = 0.0_f32;
            for axis in axes {
                if let Some(value) = oriented_residual(source, &linear, coverage, width, height, x, y, axis, radius) {
                    residual = residual.max(value);
                }
            }
            if residual == 0.0 { continue; }
            let p = linear[i];
            let lift = amount * MAX_LIFT_FRACTION * coverage[i] * residual;
            let peak = p.iter().copied().fold(0.0, f32::max);
            let gain = (1.0 + lift / luminance(p)).min((1.0 - f32::EPSILON) / peak);
            if gain <= 1.0 { continue; }
            // One common multiplicative linear-RGB gain preserves the source
            // channel ratios, limited jointly by the most constrained channel.
            // No per-channel clamp or replacement by an average flank colour.
            let encoded = p.map(|v| encode(v * gain));
            if !encoded.iter().copied().all(unit) { return Err(PIXEL_ERROR); }
            // Extremely small amounts can be below f32 transfer roundoff; do
            // not introduce a backwards correction merely by re-encoding.
            if (0..3).any(|c| encoded[c] < source[3*i+c]) { continue; }
            private[3*i..3*i+3].copy_from_slice(&encoded);
        }
    }
    poll(&mut cancelled)?;
    // No fallible work or cancellation callback after this final commit point.
    // This is all-or-nothing at call return, not concurrent memory publication.
    output.copy_from_slice(&private);
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
pub extern "C" fn lrt_lip_texture_abi() -> u32 { 1 }

/// # Safety
/// Caller provides live aligned allocations of stated sizes, immutable input
/// spans and exclusively writable output overlapping no input. Input spans may
/// overlap each other. Callback/context remain live, may not unwind/reenter or
/// mutate buffers. Pointer validity cannot be established by length checks.
/// Panic containment cannot catch foreign faults, invalid pointers or aborts.
#[no_mangle]
pub unsafe extern "C" fn lrt_lip_texture_apply_v1(
    source: *const f32, source_len: usize, coverage: *const f32, coverage_len: usize,
    width: usize, height: usize, amount: f32, across_x: f32, across_y: f32, radius: usize,
    output: *mut f32, output_len: usize, cancel: Cancel, context: *mut c_void,
) -> i32 {
    let result = panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(), i32> {
        let pixels = admit(width, height)?;
        let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
        if source_len != channels || coverage_len != pixels || output_len != channels { return Err(ABI_ERROR); }
        settings(amount, [across_x, across_y], radius)?;
        let out = span(output, output_len)?;
        if overlaps(out, span(source, source_len)?) || overlaps(out, span(coverage, coverage_len)?) { return Err(ABI_ERROR); }
        apply_into(slice::from_raw_parts(source, source_len), slice::from_raw_parts(coverage, coverage_len),
            width, height, amount, [across_x, across_y], radius, slice::from_raw_parts_mut(output, output_len),
            || cancel.map_or(false, |function| function(context) != 0))
    }));
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

#[cfg(test)]
mod tests;
