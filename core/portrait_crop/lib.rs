// SPDX-License-Identifier: GPL-3.0-or-later
//! Original scalar portrait crop planner. AUTHORED / UNRUN.
//! This does not infer anatomy, load models, sample pixels, or grant approval.
use std::{mem, panic, ptr, slice};

pub const ABI: u32 = 1;
pub const CAPABILITIES: u64 = 15;
pub const ANCHORS_LEN: usize = 6;
pub const RULES_LEN: usize = 4;
pub const RESULT_LEN: usize = 20;
pub const MAX_DIMENSION: u32 = i32::MAX as u32;
pub const ABI_ERROR: i32 = 1;
pub const GEOMETRY_ERROR: i32 = 2;
pub const INFEASIBLE: i32 = 3;
pub const PIXEL_ROUNDING: i32 = 4;
pub const PANIC_ERROR: i32 = 5;

fn span(pointer: *const f64, length: usize) -> Result<(usize, usize), i32> {
    let start = pointer as usize;
    let bytes = length.checked_mul(mem::size_of::<f64>()).ok_or(ABI_ERROR)?;
    if pointer.is_null() || start % mem::align_of::<f64>() != 0 || bytes > isize::MAX as usize {
        return Err(ABI_ERROR);
    }
    Ok((start, start.checked_add(bytes).ok_or(ABI_ERROR)?))
}

fn overlaps(a: (usize, usize), b: (usize, usize)) -> bool {
    a.0 < b.1 && b.0 < a.1
}

fn inside(x: f64, y: f64, bounds: &[f64; 4]) -> bool {
    bounds[0] <= x && x <= bounds[2] && bounds[1] <= y && y <= bounds[3]
}

/// Exact ties-to-even for nonnegative finite values in the admitted int32 grid.
/// f64::round rounds halfway away from zero and is deliberately not used.
fn pixel_round(value: f64) -> f64 {
    let lower = value.floor();
    let fraction = value - lower;
    if fraction < 0.5 || (fraction == 0.5 && (lower as u64) % 2 == 0) {
        lower
    } else {
        lower + 1.0
    }
}

/// anchors: crown x/y, chin x/y, face-center x/y, in source-edge pixels.
/// rules: W/H, headroom/H, (chin_y-crown_y)/H, (center_x-left)/W.
pub fn solve(width: u32, height: u32, a: &[f64; 6], r: &[f64; 4]) -> Result<[f64; RESULT_LEN], i32> {
    if width == 0 || height == 0 || width > MAX_DIMENSION || height > MAX_DIMENSION
        || a.iter().chain(r).any(|v| !v.is_finite())
        || r[0] <= 0.0 || !(0.0..=1.0).contains(&r[1])
        || r[2] <= 0.0 || r[2] > 1.0 || !(0.0..=1.0).contains(&r[3]) {
        return Err(GEOMETRY_ERROR);
    }
    let w = f64::from(width);
    let h = f64::from(height);
    let source = [0.0, 0.0, w, h];
    if a.chunks_exact(2).any(|p| !inside(p[0], p[1], &source))
        || a[3] <= a[1] || a[5] < a[1] || a[5] > a[3] {
        return Err(GEOMETRY_ERROR);
    }
    if r[1] + r[2] > 1.0 { return Err(INFEASIBLE); }
    let head_height = a[3] - a[1];
    let crop_height = head_height / r[2];
    let crop_width = r[0] * crop_height;
    let top = a[1] - r[1] * crop_height;
    let left = a[4] - r[3] * crop_width;
    let continuous = [left, top, left + crop_width, top + crop_height];
    if !crop_width.is_finite() || !crop_height.is_finite()
        || crop_width <= 0.0 || crop_height <= 0.0
        || continuous.iter().any(|v| !v.is_finite())
        || !(0.0 <= continuous[0] && continuous[0] < continuous[2] && continuous[2] <= w)
        || !(0.0 <= continuous[1] && continuous[1] < continuous[3] && continuous[3] <= h)
        || a.chunks_exact(2).any(|p| !inside(p[0], p[1], &continuous)) {
        return Err(INFEASIBLE);
    }
    // Preserve the sampler's normalize -> multiply -> ties-even order, not
    // round(continuous), and do not borrow its clamps or forced one-pixel crop.
    let normalized = [continuous[0] / w, continuous[1] / h,
                      continuous[2] / w, continuous[3] / h];
    let pixel = [pixel_round(w * normalized[0]), pixel_round(h * normalized[1]),
                 pixel_round(w * normalized[2]), pixel_round(h * normalized[3])];
    if !(0.0 <= pixel[0] && pixel[0] < pixel[2] && pixel[2] <= w)
        || !(0.0 <= pixel[1] && pixel[1] < pixel[3] && pixel[3] <= h)
        || a.chunks_exact(2).any(|p| !inside(p[0], p[1], &pixel)) {
        return Err(PIXEL_ROUNDING);
    }
    let cw = pixel[2] - pixel[0];
    let ch = pixel[3] - pixel[1];
    let mut output = [0.0; RESULT_LEN];
    output[0..4].copy_from_slice(&continuous);
    output[4..8].copy_from_slice(&[pixel[0] / w, pixel[1] / h, pixel[2] / w, pixel[3] / h]);
    output[8..12].copy_from_slice(&pixel);
    output[12..20].copy_from_slice(&[
        cw / ch, (a[1] - pixel[1]) / ch, head_height / ch,
        (a[4] - pixel[0]) / cw, (a[5] - pixel[1]) / ch, head_height, cw, ch,
    ]);
    if output.iter().any(|v| !v.is_finite()) { return Err(INFEASIBLE); }
    Ok(output)
}

#[no_mangle]
pub extern "C" fn lrt_portrait_crop_abi() -> u32 { ABI }
#[no_mangle]
pub extern "C" fn lrt_portrait_crop_capabilities() -> u64 { CAPABILITIES }
#[no_mangle]
pub extern "C" fn lrt_portrait_crop_result_len() -> usize { RESULT_LEN }

/// # Safety
/// Caller supplies aligned, valid, live buffers for every declared span.
/// Input spans may alias one another, but output must be disjoint from both.
/// No concurrent writes; every nonzero return preserves all output bytes.
#[no_mangle]
pub unsafe extern "C" fn lrt_portrait_crop_plan_v1(
    width: u32, height: u32,
    anchors: *const f64, anchors_len: usize,
    rules: *const f64, rules_len: usize,
    output: *mut f64, output_len: usize,
) -> i32 {
    if anchors_len != ANCHORS_LEN || rules_len != RULES_LEN || output_len != RESULT_LEN {
        return ABI_ERROR;
    }
    let a_span = match span(anchors, anchors_len) { Ok(v) => v, Err(e) => return e };
    let r_span = match span(rules, rules_len) { Ok(v) => v, Err(e) => return e };
    let o_span = match span(output, output_len) { Ok(v) => v, Err(e) => return e };
    if overlaps(a_span, o_span) || overlaps(r_span, o_span) { return ABI_ERROR; }
    let result = panic::catch_unwind(|| {
        let a: &[f64; 6] = slice::from_raw_parts(anchors, anchors_len).try_into().map_err(|_| ABI_ERROR)?;
        let r: &[f64; 4] = slice::from_raw_parts(rules, rules_len).try_into().map_err(|_| ABI_ERROR)?;
        solve(width, height, a, r)
    });
    match result {
        Ok(Ok(value)) => { ptr::copy_nonoverlapping(value.as_ptr(), output, RESULT_LEN); 0 }
        Ok(Err(code)) => code,
        Err(_) => PANIC_ERROR,
    }
}

#[cfg(test)]
#[path = "tests_unrun.rs"]
mod tests_unrun;
