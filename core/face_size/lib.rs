// SPDX-License-Identifier: GPL-3.0-or-later
//! Original analytic whole-face inverse field. AUTHORED / UNRUN.
//! No contour controls, identity pins, RGB sampling or inference is performed.

use std::{mem, panic, ptr, slice};

pub const MAX_POINTS: usize = 65_536;
pub const PARAMS_LEN: usize = 11;
pub const MIN_SCALE: f64 = 0.94;
pub const MAX_SCALE: f64 = 1.06;
pub const FRAME_TOLERANCE: f64 = 1.0e-6;
pub const MIN_INVERSE_DERIVATIVE: f64 = 0.2;
pub const ABI_ERROR: i32 = 1;
pub const VALUE_ERROR: i32 = 2;
pub const FRAME_ERROR: i32 = 3;
pub const BOUND_ERROR: i32 = 4;
pub const ALLOCATION_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;

fn span(pointer: *const f64, length: usize) -> Result<(usize, usize), i32> {
    let start = pointer as usize;
    let bytes = length.checked_mul(mem::size_of::<f64>()).ok_or(ABI_ERROR)?;
    if pointer.is_null() || start % mem::align_of::<f64>() != 0
        || bytes > isize::MAX as usize
    {
        return Err(ABI_ERROR);
    }
    Ok((start, start.checked_add(bytes).ok_or(ABI_ERROR)?))
}

fn overlaps(a: (usize, usize), b: (usize, usize)) -> bool {
    a.0 < b.1 && b.0 < a.1
}

fn validate(points: &[f64], params: &[f64]) -> Result<(), i32> {
    if points.iter().chain(params).any(|v| !v.is_finite())
        || !(MIN_SCALE..=MAX_SCALE).contains(&params[10])
    {
        return Err(VALUE_ERROR);
    }
    let right_norm = params[2].hypot(params[3]);
    let up_norm = params[4].hypot(params[5]);
    let dot = params[2] * params[4] + params[3] * params[5];
    if !right_norm.is_finite() || !up_norm.is_finite() || !dot.is_finite()
        || (right_norm - 1.0).abs() > FRAME_TOLERANCE
        || (up_norm - 1.0).abs() > FRAME_TOLERANCE
        || dot.abs() > FRAME_TOLERANCE || params[6] <= 0.0 || params[7] <= 0.0
    {
        return Err(FRAME_ERROR);
    }
    let inner = params[8];
    let outer = params[9];
    if inner <= 0.0 || outer <= inner { return Err(BOUND_ERROR); }
    let inverse = 1.0 / params[10];
    let coefficient = (params[10] - 1.0) / params[10];
    // max smoothstep'(t) is 1.875. This conservative radial/tangential
    // inverse-derivative floor rejects too-narrow transition bands, not merely
    // an inverted scale. A neutral map has no transition derivative at all.
    let floor = if coefficient == 0.0 { 1.0 } else {
        inverse.min(1.0) - coefficient.abs() * 1.875 * (outer / (outer - inner))
    };
    if !floor.is_finite() || floor < MIN_INVERSE_DERIVATIVE {
        return Err(BOUND_ERROR);
    }
    Ok(())
}

fn fill(points: &[f64], params: &[f64], scratch: &mut [f64]) -> Result<(), i32> {
    // Algebraically 1 - 1/scale, without reciprocal-subtraction cancellation
    // for the smallest representable nonneutral scales near one.
    let coefficient = (params[10] - 1.0) / params[10];
    // Inputs and support are still validated for a neutral direct ABI call.
    if coefficient == 0.0 { return Ok(()); }
    for (point, delta) in points.chunks_exact(2).zip(scratch.chunks_exact_mut(2)) {
        let dx = point[0] - params[0];
        let dy = point[1] - params[1];
        if !dx.is_finite() || !dy.is_finite() { return Err(BOUND_ERROR); }
        let local_x = (dx * params[2] + dy * params[3]) / params[6];
        let local_y = (dx * params[4] + dy * params[5]) / params[7];
        let radius = local_x.hypot(local_y);
        // Infinite radius after division by a tiny positive extent is outside
        // every finite support. NaN is never interpreted as background.
        if local_x.is_nan() || local_y.is_nan() || radius.is_nan() {
            return Err(BOUND_ERROR);
        }
        if radius >= params[9] || (dx == 0.0 && dy == 0.0) { continue; }
        let weight = if radius <= params[8] { 1.0 } else {
            let t = (radius - params[8]) / (params[9] - params[8]);
            // 1 - (6t^5 - 15t^4 + 10t^3), using smoothstep symmetry
            // near the outer edge to avoid cancellation. C2 at both edges.
            let smoothstep = |u: f64| u * u * u * (10.0 + u * (6.0 * u - 15.0));
            if t <= 0.5 { 1.0 - smoothstep(t) } else { smoothstep(1.0 - t) }
        };
        let factor = coefficient * weight;
        let x = factor * dx;
        let y = factor * dy;
        if !weight.is_finite() || !(0.0..=1.0).contains(&weight)
            || !x.is_finite() || !y.is_finite()
            || !(point[0] - x).is_finite() || !(point[1] - y).is_finite()
        {
            return Err(BOUND_ERROR);
        }
        // Normalize exact zero components, including negative input zeros.
        delta[0] = if x == 0.0 { 0.0 } else { x };
        delta[1] = if y == 0.0 { 0.0 } else { y };
    }
    Ok(())
}

#[no_mangle]
pub extern "C" fn lrt_face_size_abi() -> u32 { 1 }

/// Private ABI 1: every length counts f64 elements, never bytes.
/// points[N,2] are destination queries; params has exactly 11 elements:
/// [cx,cy,right_x,right_y,up_x,up_y,hx,hy,inner,outer,scale].
/// output[N,2] is q - source(q), NOT forward motion or a source position.
/// N is 1..65536; callers batch larger grids. Any error leaves output untouched.
/// # Safety
/// Caller supplies live aligned allocations covering the exact declared lengths,
/// immutable inputs and exclusively writable output for the entire call. Output
/// overlaps no input; read-only inputs may overlap. Address arithmetic cannot
/// establish actual allocated extents, lifetime, anatomy or provenance. Invalid
/// non-null memory remains a caller violation. Panic containment cannot recover
/// foreign memory faults or process aborts. This is not a hostile-process boundary.
#[no_mangle]
pub unsafe extern "C" fn lrt_face_size_evaluate_v1(
    points: *const f64, points_len: usize,
    params: *const f64, params_len: usize, count: usize,
    output: *mut f64, output_len: usize,
) -> i32 {
    let result = panic::catch_unwind(|| -> Result<(), i32> {
        if count == 0 || count > MAX_POINTS { return Err(ABI_ERROR); }
        let coordinates = count.checked_mul(2).ok_or(ABI_ERROR)?;
        if points_len != coordinates || params_len != PARAMS_LEN || output_len != coordinates {
            return Err(ABI_ERROR);
        }
        let output_span = span(output, output_len)?;
        for (pointer, length) in [(points, points_len), (params, params_len)] {
            if overlaps(span(pointer, length)?, output_span) { return Err(ABI_ERROR); }
        }
        // Pointer/shape/overlap checks precede slice construction. Every input
        // value is validated before neutral bypass or scratch allocation.
        let points = slice::from_raw_parts(points, points_len);
        let params = slice::from_raw_parts(params, params_len);
        validate(points, params)?;
        // At most 1 MiB for 65536 two-dimensional f64 queries. Reserve failure
        // is an ordinary error; resize cannot allocate after this reservation.
        let mut scratch = Vec::new();
        scratch.try_reserve_exact(coordinates).map_err(|_| ALLOCATION_ERROR)?;
        scratch.resize(coordinates, 0.0);
        fill(points, params, &mut scratch)?;
        // The only caller-output write occurs after all computations succeed.
        ptr::copy_nonoverlapping(scratch.as_ptr(), output, output_len);
        Ok(())
    });
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

#[cfg(test)]
mod tests;
