// SPDX-License-Identifier: GPL-3.0-or-later
//! Original D65-referenced CIELAB skin temperature/tint. AUTHORED / UNRUN.
//! Encoded working-sRGB float32 SDR plus source-owned coverage from the host.
//! No detector, blur, invented texture, Kelvin claim or proprietary equivalence.

use std::{ffi::c_void, mem, panic, slice};

pub const MAX_PIXELS: usize = 64_000_000;
pub const MAX_DIMENSION: usize = 65_536;
pub const MAX_BUFFER_BYTES: usize = 2 * 1024 * 1024 * 1024;
pub const GAMUT_STEPS: usize = 24;
pub const MAX_GAMUT_EVALUATIONS: usize = 1_600_000_000;
pub const POLL_PIXELS: usize = 256;
pub const TEMPERATURE_LAB_B: f64 = 8.0;
pub const TINT_LAB_A: f64 = 6.0;
pub const ABI_ERROR: i32 = 1;
pub const SETTINGS_ERROR: i32 = 2;
pub const PIXEL_ERROR: i32 = 3;
pub const CANCELLED: i32 = 4;
pub const RESOURCE_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;
pub type Cancel = Option<extern "C" fn(*mut c_void) -> i32>;

// Standard sRGB primaries, normalized to the D65 xy white (0.3127, 0.3290).
// These are mathematical colourimetry constants, not copied external code.
const RGB_TO_XYZ: [[f64; 3]; 3] = [
    [0.4123907992659595, 0.35758433938387796, 0.1804807884018343],
    [0.21263900587151036, 0.7151686787677559, 0.07219231536073371],
    [0.01933081871559185, 0.11919477979462599, 0.9505321522496607],
];
const XYZ_TO_RGB: [[f64; 3]; 3] = [
    [3.2409699419045226, -1.537383177570094, -0.4986107602930034],
    [-0.9692436362808796, 1.8759675015077202, 0.04155505740717559],
    [0.05563007969699366, -0.20397695888897652, 1.0569715142428786],
];
const WHITE_X: f64 = 0.3127 / 0.3290;
const WHITE_Z: f64 = (1.0 - 0.3127 - 0.3290) / 0.3290;
const DELTA: f64 = 6.0 / 29.0;

fn unit(value: f32) -> bool { value.is_finite() && (0.0..=1.0).contains(&value) }
fn control(value: f32) -> bool { value.is_finite() && (-1.0..=1.0).contains(&value) }
fn in_gamut(rgb: [f64; 3]) -> bool {
    rgb.iter().all(|v| v.is_finite() && (0.0..=1.0).contains(v))
}

fn admit(width: usize, height: usize) -> Result<usize, i32> {
    if width == 0 || height == 0 || width > MAX_DIMENSION || height > MAX_DIMENSION {
        return Err(ABI_ERROR);
    }
    let pixels = width.checked_mul(height).ok_or(RESOURCE_ERROR)?;
    // Source RGB + coverage + output = seven float32 values per pixel.
    let bytes = pixels.checked_mul(7 * mem::size_of::<f32>()).ok_or(RESOURCE_ERROR)?;
    let evaluations = pixels.checked_mul(GAMUT_STEPS + 1).ok_or(RESOURCE_ERROR)?;
    if pixels > MAX_PIXELS || bytes > MAX_BUFFER_BYTES || evaluations > MAX_GAMUT_EVALUATIONS {
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

fn transform(matrix: [[f64; 3]; 3], value: [f64; 3]) -> [f64; 3] {
    matrix.map(|row| row[0] * value[0] + row[1] * value[1] + row[2] * value[2])
}

fn lab_curve(value: f64) -> f64 {
    if value > DELTA * DELTA * DELTA { value.cbrt() }
    else { value / (3.0 * DELTA * DELTA) + 4.0 / 29.0 }
}

fn lab_inverse(value: f64) -> f64 {
    if value > DELTA { value * value * value }
    else { 3.0 * DELTA * DELTA * (value - 4.0 / 29.0) }
}

/// D65-referenced CIELAB, not CSS lab()'s D50-adapted coordinates.
fn to_lab(rgb: [f64; 3]) -> ([f64; 3], f64) {
    let xyz = transform(RGB_TO_XYZ, rgb);
    let fy = lab_curve(xyz[1]);
    ([116.0 * fy - 16.0,
      500.0 * (lab_curve(xyz[0] / WHITE_X) - fy),
      200.0 * (fy - lab_curve(xyz[2] / WHITE_Z))], xyz[1])
}

fn from_lab_at_y(lab: [f64; 3], original_y: f64) -> [f64; 3] {
    let fy = (lab[0] + 16.0) / 116.0;
    // Retain source Y directly rather than round-tripping it through inverse L*.
    transform(XYZ_TO_RGB, [
        WHITE_X * lab_inverse(fy + lab[1] / 500.0),
        original_y,
        WHITE_Z * lab_inverse(fy - lab[2] / 200.0),
    ])
}

/// Scale BOTH opponent channels by the SAME factor; L* is never adjusted.
/// Store only strictly in-gamut candidates. The fixed 24-step search is not
/// CSS local-MINDE and does not clip RGB, even as a floating-point repair.
/// The Lab gamut need not be radially convex: this is a safe feasible result,
/// not a proof of globally maximal chroma or perceptually constant hue.
fn compress_chroma(lab: [f64; 3], original_y: f64) -> [f64; 3] {
    let requested = from_lab_at_y(lab, original_y);
    if in_gamut(requested) { return requested; }
    // The zero-chroma anchor is exact linear neutral at source Y. This avoids
    // inverse-matrix roundoff at the neutral axis; black/white bypass earlier.
    let mut best = [original_y; 3];
    let mut low = 0.0;
    let mut high = 1.0;
    for _ in 0..GAMUT_STEPS {
        let scale = 0.5 * (low + high);
        let candidate = from_lab_at_y([lab[0], scale * lab[1], scale * lab[2]], original_y);
        if in_gamut(candidate) {
            best = candidate;
            low = scale;
        } else {
            high = scale;
        }
    }
    best
}

fn pixel(source: [f32; 3], coverage: f32, temperature: f32, tint: f32) -> [f32; 3] {
    if coverage == 0.0 || (temperature == 0.0 && tint == 0.0)
        || source.iter().all(|&v| v == 0.0) || source.iter().all(|&v| v == 1.0) {
        return source;
    }
    let linear = source.map(|v| decode(f64::from(v)));
    let (mut lab, original_y) = to_lab(linear);
    lab[1] += TINT_LAB_A * f64::from(tint);
    lab[2] += TEMPERATURE_LAB_B * f64::from(temperature);
    let adjusted = compress_chroma(lab, original_y);
    let weight = f64::from(coverage);
    // A convex combination of two feasible linear RGB colours is feasible.
    // This form avoids subtractive cancellation at exactly full coverage.
    std::array::from_fn(|c| encode((1.0 - weight) * linear[c] + weight * adjusted[c]))
}

/// Safe slice entry point. Validate ALL inputs before writing output, including
/// neutral or unsupported pixels. No heap, neighbour reads, hidden downsampling
/// or mutation of source/coverage. Errors may leave private output incomplete;
/// the caller must discard the entire output on every error or cancellation.
pub fn apply_into(
    source: &[f32], coverage: &[f32], width: usize, height: usize,
    temperature: f32, tint: f32, output: &mut [f32],
    mut cancelled: impl FnMut() -> bool,
) -> Result<(), i32> {
    let pixels = admit(width, height)?;
    let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
    if source.len() != channels || coverage.len() != pixels || output.len() != channels {
        return Err(ABI_ERROR);
    }
    if !control(temperature) || !control(tint) { return Err(SETTINGS_ERROR); }
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
        let adjusted = pixel(original, coverage[i], temperature, tint);
        if !adjusted.iter().copied().all(unit) { return Err(PIXEL_ERROR); }
        output[3*i..3*i+3].copy_from_slice(&adjusted);
    }
    if cancelled() { return Err(CANCELLED); }
    Ok(())
}

// Checked integer ranges do not prove allocation ownership or readable memory.
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
pub extern "C" fn lrt_skin_colour_abi() -> u32 { 1 }

/// ABI 1. Lengths count float32 elements, not bytes; source is interleaved HWC.
/// # Safety
/// Caller supplies live, aligned, sufficiently sized allocations. Source and
/// coverage stay immutable; output is exclusively writable and overlaps neither
/// input. Read-only inputs may overlap each other. Callback/context stay alive
/// and callback must not unwind, mutate these buffers or reenter this operation.
/// Discard all output on nonzero status. Panic containment cannot repair invalid
/// pointers, foreign callback faults, process abort or use-after-free.
#[no_mangle]
pub unsafe extern "C" fn lrt_skin_colour_apply_v1(
    source: *const f32, source_len: usize, coverage: *const f32, coverage_len: usize,
    width: usize, height: usize, temperature: f32, tint: f32,
    output: *mut f32, output_len: usize, cancel: Cancel, context: *mut c_void,
) -> i32 {
    let result = panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(), i32> {
        let pixels = admit(width, height)?;
        let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
        if source_len != channels || coverage_len != pixels || output_len != channels {
            return Err(ABI_ERROR);
        }
        if !control(temperature) || !control(tint) { return Err(SETTINGS_ERROR); }
        let rgb_span = span(source, source_len)?;
        let mask_span = span(coverage, coverage_len)?;
        let output_span = span(output, output_len)?;
        if overlaps(rgb_span, output_span) || overlaps(mask_span, output_span) {
            return Err(ABI_ERROR);
        }
        let rgb = slice::from_raw_parts(source, source_len);
        let mask = slice::from_raw_parts(coverage, coverage_len);
        let out = slice::from_raw_parts_mut(output, output_len);
        apply_into(rgb, mask, width, height, temperature, tint, out,
            || cancel.map_or(false, |function| function(context) != 0))
    }));
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

#[cfg(test)]
mod tests;
