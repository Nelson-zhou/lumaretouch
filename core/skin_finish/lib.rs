// SPDX-License-Identifier: GPL-3.0-or-later
//! Original D65-CIELAB skin whitening and rosiness. AUTHORED / UNRUN.
//! Encoded working-sRGB float32 SDR plus source-owned coverage from the host.
//! No detector, blur, invented texture, exposure/tint alias or proprietary equivalence.

use std::{ffi::c_void, mem, panic, slice};

pub const MAX_PIXELS: usize = 64_000_000;
pub const MAX_DIMENSION: usize = 65_536;
pub const MAX_BUFFER_BYTES: usize = 2 * 1024 * 1024 * 1024;
pub const GAMUT_STEPS: usize = 24;
pub const MAX_GAMUT_EVALUATIONS: usize = 1_600_000_000;
pub const POLL_PIXELS: usize = 256;
pub const WHITENING_LIFT: f64 = 0.18;
pub const WHITENING_CHROMA_REDUCTION: f64 = 0.12;
pub const WHITENING_COOL_LAB_B: f64 = 1.5;
pub const ROSINESS_LAB_A: f64 = 5.0;
pub const ROSINESS_LAB_B_RATIO: f64 = 0.25;
pub const ROSINESS_RED_RESTRAINT: f64 = 20.0;
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
fn control(value: f32) -> bool { unit(value) }
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
    // Algebraically identical low-light CIELAB branch without cancellation.
    let lightness = if xyz[1] <= DELTA * DELTA * DELTA {
        xyz[1] * (116.0 / (3.0 * DELTA * DELTA))
    } else { 116.0 * fy - 16.0 };
    ([lightness,
      500.0 * (lab_curve(xyz[0] / WHITE_X) - fy),
      200.0 * (fy - lab_curve(xyz[2] / WHITE_Z))], xyz[1])
}

fn from_lab_at_y(lab: [f64; 3], target_y: f64) -> [f64; 3] {
    let fy = (lab[0] + 16.0) / 116.0;
    // Preserve the requested Y through gamut mapping, not a rounded Lab round-trip.
    transform(XYZ_TO_RGB, [
        WHITE_X * lab_inverse(fy + lab[1] / 500.0),
        target_y,
        WHITE_Z * lab_inverse(fy - lab[2] / 200.0),
    ])
}

/// Scale BOTH requested opponent channels together; requested L*/Y stays fixed.
/// Store only strictly in-gamut candidates. The fixed 24-step search is not
/// CSS local-MINDE and does not clip RGB, even as a floating-point repair.
/// The Lab gamut need not be radially convex: this is a safe feasible result,
/// not a proof of globally maximal chroma or perceptually constant hue.
fn compress_chroma(lab: [f64; 3], target_y: f64) -> [f64; 3] {
    let requested = from_lab_at_y(lab, target_y);
    if in_gamut(requested) { return requested; }
    // The zero-chroma anchor is exact linear neutral at requested Y. This avoids
    // inverse-matrix roundoff at the neutral axis; black/white bypass earlier.
    let mut best = [target_y; 3];
    let mut low = 0.0;
    let mut high = 1.0;
    for _ in 0..GAMUT_STEPS {
        let scale = 0.5 * (low + high);
        let candidate = from_lab_at_y([lab[0], scale * lab[1], scale * lab[2]], target_y);
        if in_gamut(candidate) {
            best = candidate;
            low = scale;
        } else {
            high = scale;
        }
    }
    best
}

/// Inverse L* with the low-light branch expressed without subtractive loss.
fn y_from_lightness(lightness: f64) -> f64 {
    if lightness <= 8.0 { lightness * (3.0 * DELTA * DELTA / 116.0) }
    else { ((lightness + 16.0) / 116.0).powi(3) }
}

/// Original, bounded product controls; no recovered commercial coefficients.
/// l' = l + .18*w*l*(1-l), whose slope is in [.82,1.18] and whose maximum
/// increase is 4.5 L*. Chroma gates vanish at the mathematical black/white ends.
/// Rosiness is a small warm-red vector, restrained on already-red colours, not
/// a uniform +a* tint. Existing temperature/tint ABI and meaning stay unchanged.
fn finish_lab(mut lab: [f64; 3], whitening: f32, rosiness: f32) -> [f64; 3] {
    let l = lab[0] / 100.0;
    let gate = 4.0 * l * (1.0 - l);
    let white = f64::from(whitening);
    let white_gate = white * gate;
    let retained_chroma = 1.0 - WHITENING_CHROMA_REDUCTION * white_gate;
    lab[0] = 100.0 * (l + WHITENING_LIFT * white * l * (1.0 - l));
    lab[1] *= retained_chroma;
    lab[2] = lab[2] * retained_chroma - WHITENING_COOL_LAB_B * white_gate;
    let existing_red = lab[1].max(0.0) / ROSINESS_RED_RESTRAINT;
    let redness = ROSINESS_LAB_A * f64::from(rosiness) * gate
        / (1.0 + existing_red * existing_red);
    lab[1] += redness;
    lab[2] += ROSINESS_LAB_B_RATIO * redness;
    lab
}

fn pixel(source: [f32; 3], coverage: f32, whitening: f32, rosiness: f32) -> [f32; 3] {
    if coverage == 0.0 || (whitening == 0.0 && rosiness == 0.0)
        || source.iter().all(|&v| v == 0.0) || source.iter().all(|&v| v == 1.0) {
        return source;
    }
    let linear = source.map(|v| decode(f64::from(v)));
    let (lab, original_y) = to_lab(linear);
    let requested = finish_lab(lab, whitening, rosiness);
    // Rosiness alone preserves original luminance exactly in f64; whitening
    // changes it only via the monotone endpoint-preserving L* curve.
    let target_y = if whitening == 0.0 { original_y }
        else { y_from_lightness(requested[0]) };
    let adjusted = compress_chroma(requested, target_y);
    let weight = f64::from(coverage);
    // Convex in linear light. For fixed coverage and controls, requested Y is
    // monotone in source Y independently of chroma/gamut reduction. Different
    // coverage or controls across pixels cannot promise global tone ordering.
    std::array::from_fn(|c| encode((1.0 - weight) * linear[c] + weight * adjusted[c]))
}

/// Safe slice entry point. Validate ALL inputs before writing output, including
/// neutral or unsupported pixels. No heap, neighbour reads, hidden downsampling
/// or mutation of source/coverage. Errors may leave private output incomplete;
/// the caller must discard the entire output on every error or cancellation.
pub fn apply_into(
    source: &[f32], coverage: &[f32], width: usize, height: usize,
    whitening: f32, rosiness: f32, output: &mut [f32],
    mut cancelled: impl FnMut() -> bool,
) -> Result<(), i32> {
    let pixels = admit(width, height)?;
    let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
    if source.len() != channels || coverage.len() != pixels || output.len() != channels {
        return Err(ABI_ERROR);
    }
    if !control(whitening) || !control(rosiness) { return Err(SETTINGS_ERROR); }
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
        let adjusted = pixel(original, coverage[i], whitening, rosiness);
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
pub extern "C" fn lrt_skin_finish_abi() -> u32 { 1 }

/// ABI 1. Lengths count float32 elements, not bytes; source is interleaved HWC.
/// # Safety
/// Caller supplies live, aligned, sufficiently sized allocations. Source and
/// coverage stay immutable; output is exclusively writable and overlaps neither
/// input. Read-only inputs may overlap each other. Callback/context stay alive
/// and callback must not unwind, mutate these buffers or reenter this operation.
/// Discard all output on nonzero status. Panic containment cannot repair invalid
/// pointers, foreign callback faults, process abort or use-after-free.
#[no_mangle]
pub unsafe extern "C" fn lrt_skin_finish_apply_v1(
    source: *const f32, source_len: usize, coverage: *const f32, coverage_len: usize,
    width: usize, height: usize, whitening: f32, rosiness: f32,
    output: *mut f32, output_len: usize, cancel: Cancel, context: *mut c_void,
) -> i32 {
    let result = panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(), i32> {
        let pixels = admit(width, height)?;
        let channels = pixels.checked_mul(3).ok_or(RESOURCE_ERROR)?;
        if source_len != channels || coverage_len != pixels || output_len != channels {
            return Err(ABI_ERROR);
        }
        if !control(whitening) || !control(rosiness) { return Err(SETTINGS_ERROR); }
        let rgb_span = span(source, source_len)?;
        let mask_span = span(coverage, coverage_len)?;
        let output_span = span(output, output_len)?;
        if overlaps(rgb_span, output_span) || overlaps(mask_span, output_span) {
            return Err(ABI_ERROR);
        }
        let rgb = slice::from_raw_parts(source, source_len);
        let mask = slice::from_raw_parts(coverage, coverage_len);
        let out = slice::from_raw_parts_mut(output, output_len);
        apply_into(rgb, mask, width, height, whitening, rosiness, out,
            || cancel.map_or(false, |function| function(context) != 0))
    }));
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

#[cfg(test)]
mod tests;
