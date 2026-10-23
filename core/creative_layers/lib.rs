// SPDX-License-Identifier: GPL-3.0-or-later
//! Original Lumaretouch image-layer compositor. Authored; local QA is UNRUN.
//! Float32 linear-sRGB D65, premultiplied RGBA. Working compositing never clips.
//! Explicit input, strict export, and display-only bridges have distinct ports.
//! Geometry and intermediate products are widened to f64; storage is always f32.
//! See ABI.md for caller ownership, bounds, sampling, and error-atomicity rules.

use std::{mem, ptr, slice};

pub const MAX_SOURCE_PIXELS: usize = 100_000_000;
pub const MAX_TILE_PIXELS: usize = 65_536;
pub const HDR_STRAIGHT_LIMIT: f64 = 65_504.0;
const MAX_EXACT_CANVAS_COORD: f64 = 1_125_899_906_842_624.0; // 2^50
const ABI_ERROR: i32 = 1;
const SETTINGS_ERROR: i32 = 2;
const PIXEL_ERROR: i32 = 3;
const ALLOCATION_ERROR: i32 = 4;
const RESULT_ERROR: i32 = 5;
const PANIC_ERROR: i32 = 6;

#[no_mangle]
pub extern "C" fn lrt_creative_layers_abi() -> u32 { 1 }

fn count(width: usize, height: usize, maximum: usize) -> Option<usize> {
    width.checked_mul(height).filter(|n| width > 0 && height > 0 && *n <= maximum)
}

fn region<T>(address: *const T, length: usize) -> Option<(usize, usize)> {
    let start = address as usize;
    let bytes = length.checked_mul(mem::size_of::<T>())?;
    if address.is_null() || start % mem::align_of::<T>() != 0 || bytes > isize::MAX as usize {
        return None;
    }
    Some((start, start.checked_add(bytes)?))
}

fn overlaps(a: (usize, usize), b: (usize, usize)) -> bool {
    a.0 < b.1 && b.0 < a.1
}

fn valid_pixel(pixel: &[f32]) -> bool {
    pixel.iter().all(|v| v.is_finite()) && (0.0..=1.0).contains(&pixel[3])
        && (pixel[3] != 0.0 || pixel[..3].iter().all(|v| *v == 0.0))
}

/// Validate a complete immutable imported RGBA image once, without allocation.
/// # Safety
/// Input must be readable/aligned for `length` floats and remain immutable.
#[no_mangle]
pub unsafe extern "C" fn lrt_creative_validate_rgba(
    input: *const f32, length: usize, width: usize, height: usize,
) -> i32 {
    let n = match count(width, height, MAX_SOURCE_PIXELS) { Some(n) => n, None => return ABI_ERROR };
    if length != n * 4 || region(input, length).is_none() { return ABI_ERROR; }
    if slice::from_raw_parts(input, length).chunks_exact(4).all(valid_pixel) { 0 } else { PIXEL_ERROR }
}

/// Validate a complete source-local scalar coverage mask, without allocation.
/// # Safety
/// Input must be readable/aligned for `length` floats and remain immutable.
#[no_mangle]
pub unsafe extern "C" fn lrt_creative_validate_mask(
    input: *const f32, length: usize, width: usize, height: usize,
) -> i32 {
    let n = match count(width, height, MAX_SOURCE_PIXELS) { Some(n) => n, None => return ABI_ERROR };
    if length != n || region(input, length).is_none() { return ABI_ERROR; }
    if slice::from_raw_parts(input, length).iter().all(|v| v.is_finite() && (0.0..=1.0).contains(v)) {
        0
    } else { PIXEL_ERROR }
}

/// Decode bounded straight encoded-sRGB RGBA into premultiplied linear RGBA.
/// Input must already be colour-managed into encoded sRGB D65, all channels in
/// [0,1]. Alpha is coverage, not transfer-encoded. It is preserved unmodified.
/// # Safety
/// Aligned, readable input and disjoint writable output each have `length`
/// floats. At most MAX_TILE_PIXELS pixels. Every rejection leaves output intact.
#[no_mangle]
pub unsafe extern "C" fn lrt_creative_linearize_rgba(
    input: *const f32, output: *mut f32, length: usize,
) -> i32 {
    if length == 0 || length % 4 != 0 || length / 4 > MAX_TILE_PIXELS { return ABI_ERROR; }
    let (src_region, out_region) = match (region(input, length), region(output as *const f32, length)) {
        (Some(a), Some(b)) => (a, b), _ => return ABI_ERROR,
    };
    if overlaps(src_region, out_region) { return ABI_ERROR; }
    let source = slice::from_raw_parts(input, length);
    if source.iter().any(|v| !v.is_finite() || !(0.0..=1.0).contains(v)) { return PIXEL_ERROR; }
    let mut staged = Vec::new();
    if staged.try_reserve_exact(length).is_err() { return ALLOCATION_ERROR; }
    for pixel in source.chunks_exact(4) {
        let alpha = pixel[3] as f64;
        for value in &pixel[..3] {
            let encoded = *value as f64;
            let linear = if encoded <= 0.04045 {
                encoded / 12.92
            } else {
                ((encoded + 0.055) / 1.055).powf(2.4)
            };
            staged.push((linear * alpha) as f32);
        }
        staged.push(pixel[3]);
    }
    ptr::copy_nonoverlapping(staged.as_ptr(), output, length);
    0
}

/// Explicit signed extended-sRGB capture bridge, distinct from SDR file import.
/// RGB uses an odd-sign inverse transfer; alpha remains coverage in [0,1].
/// Decoded straight RGB and the stored premultiplied result obey ±65504 bounds.
/// # Safety
/// Valid aligned disjoint input/output each contain `length` float32 values.
/// At most MAX_TILE_PIXELS RGBA pixels; any rejection leaves output unchanged.
#[no_mangle]
pub unsafe extern "C" fn lrt_creative_linearize_extended_rgba(
    input: *const f32, output: *mut f32, length: usize,
) -> i32 {
    if length == 0 || length % 4 != 0 || length / 4 > MAX_TILE_PIXELS { return ABI_ERROR; }
    let (src_region, out_region) = match (region(input, length), region(output as *const f32, length)) {
        (Some(a), Some(b)) => (a,b), _ => return ABI_ERROR,
    };
    if overlaps(src_region, out_region) { return ABI_ERROR; }
    let source = slice::from_raw_parts(input, length);
    if source.chunks_exact(4).any(|p| p.iter().any(|v| !v.is_finite()) || !(0.0..=1.0).contains(&p[3])) {
        return PIXEL_ERROR;
    }
    let mut staged = Vec::new();
    if staged.try_reserve_exact(length).is_err() { return ALLOCATION_ERROR; }
    for pixel in source.chunks_exact(4) {
        let alpha = pixel[3] as f64;
        for value in &pixel[..3] {
            let encoded = *value as f64;
            let magnitude = encoded.abs();
            let decoded = if magnitude <= 0.04045 { encoded / 12.92 }
                else { encoded.signum() * ((magnitude + 0.055) / 1.055).powf(2.4) };
            if !decoded.is_finite() || decoded.abs() > HDR_STRAIGHT_LIMIT { return PIXEL_ERROR; }
            let premultiplied = (decoded * alpha) as f32;
            // Validate the actual rounded stored value, not only ideal arithmetic.
            if !premultiplied.is_finite() || (premultiplied as f64).abs() > HDR_STRAIGHT_LIMIT * alpha {
                return RESULT_ERROR;
            }
            staged.push(premultiplied);
        }
        staged.push(pixel[3]);
    }
    ptr::copy_nonoverlapping(staged.as_ptr(), output, length);
    0
}

fn narrow(value: f64) -> Result<f32, i32> {
    let result = value as f32;
    if result.is_finite() { Ok(result) } else { Err(RESULT_ERROR) }
}

fn encode_srgb(linear: f64) -> f64 {
    if linear <= 0.0031308 { linear * 12.92 }
    else { 1.055 * linear.powf(1.0 / 2.4) - 0.055 }
}

/// Strict bridge into legacy opaque SDR RGB export. No alpha drop or clipping.
/// `length` counts INPUT RGBA floats; output has length/4*3 float32 values.
/// # Safety
/// Input/output must be valid, aligned, disjoint spans of those lengths.
/// Any rejection leaves all output bytes unchanged. Maximum MAX_TILE_PIXELS.
#[no_mangle]
pub unsafe extern "C" fn lrt_creative_encode_opaque_sdr_rgb(
    input: *const f32, output: *mut f32, length: usize,
) -> i32 {
    if length == 0 || length % 4 != 0 || length / 4 > MAX_TILE_PIXELS { return ABI_ERROR; }
    let output_length = length / 4 * 3;
    let (src_region, out_region) = match (region(input, length), region(output as *const f32, output_length)) {
        (Some(a), Some(b)) => (a,b), _ => return ABI_ERROR,
    };
    if overlaps(src_region, out_region) { return ABI_ERROR; }
    let source = slice::from_raw_parts(input, length);
    if source.chunks_exact(4).any(|p| p[3] != 1.0
        || p.iter().any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))) {
        return PIXEL_ERROR;
    }
    let mut staged = Vec::new();
    if staged.try_reserve_exact(output_length).is_err() { return ALLOCATION_ERROR; }
    for pixel in source.chunks_exact(4) {
        for value in &pixel[..3] { staged.push(encode_srgb(*value as f64) as f32); }
    }
    ptr::copy_nonoverlapping(staged.as_ptr(), output, output_length);
    0
}

/// DISPLAY ONLY: explicit opaque linear-sRGB matte, SDR clipping, then RGB8.
/// This operation must never be substituted for the strict export bridge.
/// `length` counts INPUT RGBA floats; output has length/4*3 uint8 values.
/// # Safety
/// Input/output/matte must be valid aligned spans (matte is three floats).
/// Output is disjoint from input and matte. Maximum MAX_TILE_PIXELS.
/// All output bytes are unchanged on rejection.
#[no_mangle]
pub unsafe extern "C" fn lrt_creative_display_rgb8(
    input: *const f32, output: *mut u8, length: usize, matte: *const f32,
) -> i32 {
    if length == 0 || length % 4 != 0 || length / 4 > MAX_TILE_PIXELS { return ABI_ERROR; }
    let output_length = length / 4 * 3;
    let (src_region, out_region, matte_region) = match (
        region(input, length), region(output as *const u8, output_length), region(matte, 3),
    ) {
        (Some(a), Some(b), Some(c)) => (a,b,c), _ => return ABI_ERROR,
    };
    if overlaps(src_region, out_region) || overlaps(matte_region, out_region) { return ABI_ERROR; }
    let source = slice::from_raw_parts(input, length);
    let background = slice::from_raw_parts(matte, 3);
    if background.iter().any(|v| !v.is_finite() || !(0.0..=1.0).contains(v)) { return SETTINGS_ERROR; }
    if !source.chunks_exact(4).all(valid_pixel) { return PIXEL_ERROR; }
    let mut staged = Vec::new();
    if staged.try_reserve_exact(output_length).is_err() { return ALLOCATION_ERROR; }
    for pixel in source.chunks_exact(4) {
        for channel in 0..3 {
            let over_matte = pixel[channel] as f64 + background[channel] as f64 * (1.0 - pixel[3] as f64);
            // This named display-only clipping is intentionally absent from all
            // source, compositing, persistence and strict export operations.
            let encoded = encode_srgb(over_matte.clamp(0.0, 1.0));
            staged.push((encoded * 255.0).round() as u8);
        }
    }
    ptr::copy_nonoverlapping(staged.as_ptr(), output, output_length);
    0
}

/// Algebraically premultiplied forms of source-over plus separable blending.
/// No straight-alpha division, including at zero/very small alpha.
fn blend(backdrop: &[f32], source: [f32; 4], mode: u32) -> Result<[f32; 4], i32> {
    if !valid_pixel(backdrop) || !valid_pixel(&source) { return Err(PIXEL_ERROR); }
    if source[3] == 0.0 { return Ok([backdrop[0], backdrop[1], backdrop[2], backdrop[3]]); }
    if backdrop[3] == 0.0 { return Ok(source); }
    let (ab, as_) = (backdrop[3] as f64, source[3] as f64);
    let mut result = [0.0; 4];
    for channel in 0..3 {
        let (b, s) = (backdrop[channel] as f64, source[channel] as f64);
        let value = match mode {
            0 => s + b * (1.0 - as_),
            1 => s * (1.0 - ab) + b * (1.0 - as_) + s * b,
            2 => s + b - s * b,
            3 => s * (1.0 - ab) + b * (1.0 - as_) + (b * as_).max(s * ab),
            4 => s * (1.0 - ab) + b * (1.0 - as_) + (b * as_).min(s * ab),
            _ => return Err(SETTINGS_ERROR),
        };
        result[channel] = narrow(value)?;
    }
    result[3] = narrow(as_ + ab * (1.0 - as_))?;
    Ok(result)
}

struct Image<'a> {
    pixels: &'a [f32],
    width: usize,
    height: usize,
    mask: Option<&'a [f32]>,
}

impl Image<'_> {
    fn tap(&self, x: i64, y: i64) -> Result<[f64; 4], i32> {
        if x < 0 || y < 0 || x >= self.width as i64 || y >= self.height as i64 {
            return Ok([0.0; 4]);
        }
        let index = y as usize * self.width + x as usize;
        let pixel = &self.pixels[index * 4..index * 4 + 4];
        if !valid_pixel(pixel) { return Err(PIXEL_ERROR); }
        let coverage = if let Some(mask) = self.mask {
            let value = mask[index];
            if !value.is_finite() || !(0.0..=1.0).contains(&value) { return Err(PIXEL_ERROR); }
            value as f64
        } else { 1.0 };
        Ok(std::array::from_fn(|channel| pixel[channel] as f64 * coverage))
    }

    fn sample(&self, x: f64, y: f64, opacity: f32) -> Result<[f32; 4], i32> {
        if !x.is_finite() || !y.is_finite() { return Err(SETTINGS_ERROR); }
        // Pixel centers are n+0.5. The exterior is transparent, NOT edge-clamped.
        // Rejecting the full-support exterior before integer conversion avoids
        // float-to-integer saturation for huge, but finite, off-canvas transforms.
        let (u, v) = (x - 0.5, y - 0.5);
        if u <= -1.0 || v <= -1.0 || u >= self.width as f64 || v >= self.height as f64 {
            return Ok([0.0; 4]);
        }
        let (left, top) = (u.floor() as i64, v.floor() as i64);
        let (fx, fy) = (u - left as f64, v - top as f64);
        let taps = [self.tap(left, top)?, self.tap(left + 1, top)?,
                    self.tap(left, top + 1)?, self.tap(left + 1, top + 1)?];
        let mut sampled = [0.0; 4];
        for channel in 0..4 {
            let upper = taps[0][channel] * (1.0 - fx) + taps[1][channel] * fx;
            let lower = taps[2][channel] * (1.0 - fx) + taps[3][channel] * fx;
            sampled[channel] = narrow((upper * (1.0 - fy) + lower * fy) * opacity as f64)?;
        }
        // A rounded-to-zero alpha with representable RGB cannot be expressed
        // canonically. Reject instead of silently clipping HDR energy or leaving
        // hidden RGB that could leak into a later transformed edge.
        if sampled[3] == 0.0 && sampled[..3].iter().any(|v| *v != 0.0) {
            return Err(RESULT_ERROR);
        }
        Ok(sampled)
    }
}

fn render(
    image: &Image<'_>, backdrop: &[f32], width: usize, height: usize,
    inverse: &[f64], origin: (f64, f64), opacity: f32, mode: u32,
) -> Result<Vec<f32>, i32> {
    if mode > 4 || !opacity.is_finite() || !(0.0..=1.0).contains(&opacity)
        || inverse.len() != 6 || inverse.iter().any(|v| !v.is_finite())
        || !origin.0.is_finite() || !origin.1.is_finite()
        || origin.0.abs() > MAX_EXACT_CANVAS_COORD || origin.1.abs() > MAX_EXACT_CANVAS_COORD
        || origin.0.fract() != 0.0 || origin.1.fract() != 0.0 {
        return Err(SETTINGS_ERROR);
    }
    let determinant = inverse[0] * inverse[4] - inverse[1] * inverse[3];
    if !determinant.is_finite() || determinant == 0.0 { return Err(SETTINGS_ERROR); }
    let mut output = Vec::new();
    output.try_reserve_exact(backdrop.len()).map_err(|_| ALLOCATION_ERROR)?;
    for y in 0..height {
        for x in 0..width {
            let at = (y * width + x) * 4;
            let base = &backdrop[at..at + 4];
            if !valid_pixel(base) { return Err(PIXEL_ERROR); }
            if opacity == 0.0 {
                output.extend_from_slice(base);
                continue;
            }
            let (cx, cy) = (origin.0 + x as f64 + 0.5, origin.1 + y as f64 + 0.5);
            let sx = inverse[0] * cx + inverse[1] * cy + inverse[2];
            let sy = inverse[3] * cx + inverse[4] * cy + inverse[5];
            let source = image.sample(sx, sy, opacity)?;
            output.extend_from_slice(&blend(base, source, mode)?);
        }
    }
    Ok(output)
}

/// Render one full-resolution canvas tile, with a full immutable source image.
/// Mode IDs: 0 normal, 1 multiply, 2 screen, 3 lighten, 4 darken.
/// Matrix order: sx=a*cx+b*cy+c; sy=d*cx+e*cy+f, cx/ cy pixel centers.
/// A null mask and zero mask_length mean no mask; otherwise it matches source.
/// Returns zero only after committing ALL output. Any rejection leaves it intact.
/// # Safety
/// All supplied spans must be valid/aligned for their exact lengths, and all
/// reads immutable during this call. Output must be writable and disjoint from
/// every input. The ABI checks sizes/overlap but cannot verify pointer provenance.
#[no_mangle]
pub unsafe extern "C" fn lrt_creative_composite_tile(
    source: *const f32, source_length: usize, source_width: usize, source_height: usize,
    backdrop: *const f32, output: *mut f32, tile_length: usize, tile_width: usize, tile_height: usize,
    inverse: *const f64, canvas_x: f64, canvas_y: f64, opacity: f32, mode: u32,
    mask: *const f32, mask_length: usize,
) -> i32 {
    let source_count = match count(source_width, source_height, MAX_SOURCE_PIXELS) {
        Some(n) => n, None => return ABI_ERROR,
    };
    let tile_count = match count(tile_width, tile_height, MAX_TILE_PIXELS) {
        Some(n) => n, None => return ABI_ERROR,
    };
    if source_length != source_count * 4 || tile_length != tile_count * 4 { return ABI_ERROR; }
    let (sr, br, out, matrix) = match (
        region(source, source_length), region(backdrop, tile_length),
        region(output as *const f32, tile_length), region(inverse, 6),
    ) {
        (Some(sr), Some(br), Some(out), Some(matrix)) => (sr, br, out, matrix),
        _ => return ABI_ERROR,
    };
    if [sr, br, matrix].iter().any(|span| overlaps(out, *span)) { return ABI_ERROR; }
    let mask_slice = if mask.is_null() {
        if mask_length != 0 { return ABI_ERROR; }
        None
    } else {
        if mask_length != source_count { return ABI_ERROR; }
        let mask_region = match region(mask, mask_length) { Some(r) => r, None => return ABI_ERROR };
        if overlaps(out, mask_region) { return ABI_ERROR; }
        Some(slice::from_raw_parts(mask, mask_length))
    };
    let image = Image {
        pixels: slice::from_raw_parts(source, source_length),
        width: source_width, height: source_height, mask: mask_slice,
    };
    let base = slice::from_raw_parts(backdrop, tile_length);
    let transform = slice::from_raw_parts(inverse, 6);
    // A Rust panic is contained at the foreign boundary. No output references
    // exist until successful staging, so even a contained panic is error-atomic.
    match std::panic::catch_unwind(|| render(
        &image, base, tile_width, tile_height, transform, (canvas_x, canvas_y), opacity, mode,
    )) {
        Ok(Ok(staged)) => { ptr::copy_nonoverlapping(staged.as_ptr(), output, tile_length); 0 }
        Ok(Err(code)) => code,
        Err(_) => PANIC_ERROR,
    }
}

#[cfg(test)]
mod tests;
