// SPDX-License-Identifier: GPL-3.0-or-later
//! Original support-normalized two-scale facial structure enhancement.
//! AUTHORED / UNRUN. Not bilateral relighting, specular decomposition or 3D.
use std::{ffi::c_void, mem, panic, slice};
pub const MAX_PIXELS: usize = 4_000_000;
pub const MAX_DIMENSION: usize = 8192;
pub const MAX_LOG_GAIN: f64 = 0.24;
pub const DEADZONE: f64 = 0.025;
pub const MAX_RESIDUAL: f64 = 0.8;
pub type Cancel = Option<extern "C" fn(*mut c_void) -> i32>;
// Error codes: 1 ABI, 2 settings, 3 pixels, 4 cancelled, 5 resources, 6 panic.
fn poll<F: FnMut() -> bool>(cancel: &mut F) -> Result<(), i32> {
    if cancel() { Err(4) } else { Ok(()) }
}
fn unit(v: f32) -> bool { v.is_finite() && (0.0..=1.0).contains(&v) }
fn decode(v: f64) -> f64 { if v <= 0.04045 { v / 12.92 } else { ((v + 0.055) / 1.055).powf(2.4) } }
fn allocate<T: Clone>(n: usize, value: T) -> Result<Vec<T>, i32> {
    let mut out = Vec::new();
    out.try_reserve_exact(n).map_err(|_| 5)?;
    out.resize(n, value);
    Ok(out)
}

/// Integral sums contain only actual admitted source samples: weight, w*logY.
/// No replicated pixels, synthetic boundary or image resizing is introduced.
fn integral<F: FnMut() -> bool>(source: &[f32], support: &[f32], w: usize, h: usize,
                              cancel: &mut F) -> Result<Vec<[f64; 2]>, i32> {
    let stride = w + 1;
    let mut sums = allocate(stride.checked_mul(h + 1).ok_or(5)?, [0.0; 2])?;
    for y in 0..h {
        poll(cancel)?;
        let mut row = [0.0; 2];
        for x in 0..w {
            if x % 256 == 0 { poll(cancel)?; }
            let i = y * w + x;
            let rgb = &source[3*i..3*i+3];
            let lum = 0.2126*decode(rgb[0] as f64) + 0.7152*decode(rgb[1] as f64)
                + 0.0722*decode(rgb[2] as f64);
            // Deep black / clipped channels are not reliable structure samples.
            let admitted = lum > 0.015 && lum < 0.95 && rgb.iter().all(|v| *v < 0.985);
            let mass = if admitted { support[i] as f64 } else { 0.0 };
            row[0] += mass;
            row[1] += if mass > 0.0 { mass * lum.ln() } else { 0.0 };
            let previous = sums[y * stride + x + 1];
            sums[(y + 1) * stride + x + 1] = [row[0] + previous[0], row[1] + previous[1]];
        }
    }
    Ok(sums)
}
fn mean(sums: &[[f64; 2]], w: usize, h: usize, x: usize, y: usize, r: usize,
        fraction: f64) -> Option<f64> {
    // Require a complete geometric window; never extrapolate boundary samples.
    if x < r || y < r || x + r >= w || y + r >= h { return None; }
    let (x0, x1, y0, y1) = (x-r, x+r+1, y-r, y+r+1);
    let stride = w + 1;
    let a = sums[y1*stride+x1]; let b = sums[y0*stride+x1];
    let c = sums[y1*stride+x0]; let d = sums[y0*stride+x0];
    let mass = a[0]-b[0]-c[0]+d[0];
    if mass < 12.0 || mass < ((2*r+1)*(2*r+1)) as f64 * fraction { return None; }
    let value = (a[1]-b[1]-c[1]+d[1])/mass;
    if value.is_finite() { Some(value) } else { None }
}

/// Outputs a frozen source-owned log-gain field, not new RGB or a portable mask.
/// Stages privately; every refusal/cancellation leaves caller output untouched.
pub fn field_into<F: FnMut() -> bool>(source: &[f32], support: &[f32], target: &[f32],
    w: usize, h: usize, highlight: f32, shadow: f32, radius: usize,
    output: &mut [f32], mut cancelled: F) -> Result<(), i32> {
    let n = w.checked_mul(h).ok_or(5)?;
    if w == 0 || h == 0 || w > MAX_DIMENSION || h > MAX_DIMENSION || n > MAX_PIXELS { return Err(5); }
    if source.len() != n.checked_mul(3).ok_or(5)? || support.len() != n || target.len() != n || output.len() != n { return Err(1); }
    if !unit(highlight) || !unit(shadow) || !(2..=128).contains(&radius) { return Err(2); }
    for i in 0..n {
        if i % 256 == 0 { poll(&mut cancelled)?; }
        if !unit(support[i]) || !unit(target[i]) || target[i] > support[i] + 1e-6
            || !source[3*i..3*i+3].iter().copied().all(unit) { return Err(3); }
    }
    let mut staged = allocate(n, 0.0_f32)?;
    if highlight != 0.0 || shadow != 0.0 {
        let sums = integral(source, support, w, h, &mut cancelled)?;
        for y in 0..h {
            poll(&mut cancelled)?;
            for x in 0..w {
                if x % 256 == 0 { poll(&mut cancelled)?; }
                let i = y*w+x;
                if target[i] == 0.0 { continue; }
                let rgb = &source[3*i..3*i+3];
                let lum = 0.2126*decode(rgb[0] as f64) + 0.7152*decode(rgb[1] as f64) + 0.0722*decode(rgb[2] as f64);
                if lum <= 0.015 || lum >= 0.95 || rgb.iter().any(|v| *v >= 0.985) { continue; }
                let fine = mean(&sums, w, h, x, y, radius, 0.55);
                let broad = mean(&sums, w, h, x, y, radius*4, 0.18);
                if let (Some(fine), Some(broad)) = (fine, broad) {
                    let residual = fine-broad;
                    // Smooth deadzone, bounded original contrast, separate controls.
                    let t = ((residual.abs()-DEADZONE)/(MAX_RESIDUAL-DEADZONE)).clamp(0.0, 1.0);
                    let response = t*t*(3.0-2.0*t);
                    let amount = if residual > 0.0 { highlight as f64 } else { -(shadow as f64) };
                    staged[i] = (MAX_LOG_GAIN * amount * target[i] as f64 * response) as f32;
                }
            }
        }
    }
    poll(&mut cancelled)?;
    output.copy_from_slice(&staged);
    Ok(())
}
fn range(ptr: *const f32, length: usize) -> Option<(usize, usize)> {
    if ptr.is_null() || (ptr as usize) % mem::align_of::<f32>() != 0 { return None; }
    let bytes = length.checked_mul(mem::size_of::<f32>())?;
    if bytes > isize::MAX as usize { return None; }
    Some((ptr as usize, (ptr as usize).checked_add(bytes)?))
}
fn overlaps(a: (usize, usize), b: (usize, usize)) -> bool { a.0 < b.1 && b.0 < a.1 }
#[no_mangle]
pub extern "C" fn lrt_facial_sculpt_abi() -> u32 { 1 }
/// The caller guarantees valid readable/writable buffers and immutability during
/// the call. Address/length checks cannot establish allocation provenance.
#[no_mangle]
pub unsafe extern "C" fn lrt_facial_sculpt_field_v1(
    source: *const f32, source_len: usize, support: *const f32, support_len: usize,
    target: *const f32, target_len: usize, width: usize, height: usize,
    highlight: f32, shadow: f32, radius: usize, output: *mut f32, output_len: usize,
    cancel: Cancel, context: *mut c_void,
) -> i32 {
    let n = match width.checked_mul(height) { Some(n) if n > 0 && n <= MAX_PIXELS => n, _ => return 5 };
    if source_len != n*3 || support_len != n || target_len != n || output_len != n { return 1; }
    let ranges = [range(source, source_len), range(support, support_len), range(target, target_len), range(output, output_len)];
    if ranges.iter().any(Option::is_none) { return 1; }
    let out_range = ranges[3].unwrap();
    if ranges[..3].iter().any(|r| overlaps(r.unwrap(), out_range)) { return 1; }
    match panic::catch_unwind(panic::AssertUnwindSafe(|| {
        field_into(slice::from_raw_parts(source, source_len), slice::from_raw_parts(support, support_len),
            slice::from_raw_parts(target, target_len), width, height, highlight, shadow, radius,
            slice::from_raw_parts_mut(output, output_len), || cancel.map_or(false, |f| f(context) != 0))
    })) { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => 6 }
}
#[cfg(test)]
mod facial_sculpt_tests;
