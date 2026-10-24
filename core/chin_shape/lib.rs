// SPDX-License-Identifier: GPL-3.0-or-later
//! Original bilateral horizontal chin taper and true inverse. AUTHORED / UNRUN.
//! No RGB sampling, landmark inference, imported algorithm or model weights.
use std::{mem, panic, ptr, slice};

pub const MAX_POINTS: usize = 65_536;
pub const PARAMS_LEN: usize = 11;
pub const GAIN: f64 = 0.08;
pub const TAIL: f64 = 0.5;
pub const FRAME_TOLERANCE: f64 = 1.0e-10;
pub const MIN_FORWARD_DERIVATIVE: f64 = 0.7;
pub const MAX_FORWARD_DERIVATIVE: f64 = 1.3;
pub const ABI_ERROR: i32 = 1;
pub const VALUE_ERROR: i32 = 2;
pub const FRAME_ERROR: i32 = 3;
pub const BOUND_ERROR: i32 = 4;
pub const ALLOCATION_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;
const SOLVER_STEPS: usize = 96;
const SUBNORMAL_FLOOR: f64 = f64::from_bits(8);

#[derive(Clone, Copy)]
struct Geometry {
    ox: f64, oy: f64, rx: f64, ry: f64, dx: f64, dy: f64,
    height: f64, inner: f64, outer: f64, left: f64, right: f64,
}

fn span(pointer: *const f64, length: usize) -> Result<(usize, usize), i32> {
    let start = pointer as usize;
    let bytes = length.checked_mul(mem::size_of::<f64>()).ok_or(ABI_ERROR)?;
    if pointer.is_null() || start % mem::align_of::<f64>() != 0
        || bytes > isize::MAX as usize { return Err(ABI_ERROR); }
    Ok((start, start.checked_add(bytes).ok_or(ABI_ERROR)?))
}
fn overlaps(a: (usize, usize), b: (usize, usize)) -> bool {
    a.0 < b.1 && b.0 < a.1
}
fn validate(points: &[f64], p: &[f64]) -> Result<Geometry, i32> {
    if points.iter().chain(p).any(|v| !v.is_finite())
        || !(-1.0..=1.0).contains(&p[9]) || !(-1.0..=1.0).contains(&p[10]) {
        return Err(VALUE_ERROR);
    }
    let rn = p[2].hypot(p[3]);
    let dn = p[4].hypot(p[5]);
    let dot = p[2] * p[4] + p[3] * p[5];
    if !rn.is_finite() || !dn.is_finite() || !dot.is_finite()
        || (rn - 1.0).abs() > FRAME_TOLERANCE
        || (dn - 1.0).abs() > FRAME_TOLERANCE || dot.abs() > FRAME_TOLERANCE
        || p[6] <= 0.0 { return Err(FRAME_ERROR); }
    // The exact 2:1 ratio is part of the derivative proof, not a suggestion.
    if p[7] <= 0.0 || p[8] <= p[7] || p[8] != 2.0 * p[7] {
        return Err(BOUND_ERROR);
    }
    let rx = p[2] / rn;
    let ry = p[3] / rn;
    let (dx, dy) = if p[2] * p[5] - p[3] * p[4] > 0.0 {
        (-ry, rx)
    } else { (ry, -rx) };
    Ok(Geometry { ox: p[0], oy: p[1], rx, ry, dx, dy, height: p[6],
                  inner: p[7], outer: p[8], left: p[9], right: p[10] })
}
fn polynomial(z: f64) -> f64 { z * z * z * (10.0 + z * (6.0 * z - 15.0)) }
fn smoothstep(z: f64) -> f64 {
    if z <= 0.0 { 0.0 } else if z >= 1.0 { 1.0 }
    else if z <= 0.5 { polynomial(z) } else { 1.0 - polynomial(1.0 - z) }
}
fn smoothstep_derivative(z: f64) -> f64 {
    let a = z * (1.0 - z);
    30.0 * a * a
}
fn vertical(t: f64) -> f64 {
    if t <= 0.0 || t >= 1.0 + TAIL { 0.0 }
    else if t < 1.0 { smoothstep(t) }
    else { smoothstep((1.0 + TAIL - t) / TAIL) }
}
// Return L(r) and B(r)=L(r)+r*L'(r), without forming 1/inner: that
// reciprocal could overflow although r/inner is bounded by two in the feather.
fn lateral(radius: f64, g: &Geometry) -> (f64, f64) {
    if radius <= g.inner { (1.0, 1.0) }
    else if radius >= g.outer { (0.0, 0.0) }
    else {
        let z = (g.outer - radius) / g.inner;
        let weight = smoothstep(z);
        (weight, weight - (radius / g.inner) * smoothstep_derivative(z))
    }
}
fn tolerance(a: f64, b: f64) -> f64 {
    (64.0 * f64::EPSILON * a.abs().max(b.abs())).max(SUBNORMAL_FLOOR)
}
fn radial_motion(radius: f64, amount: f64, weight: f64, g: &Geometry) -> f64 {
    // Multiply coordinate before amount, retaining tiny amounts when a large
    // physical coordinate makes the displacement representable.
    -(((GAIN * radius) * amount) * weight) * lateral(radius, g).0
}

/// Solve d=q_radius-source_radius, not a negative-forward approximation.
/// R(d)=d+.08*(q_radius-d)*amount*V*L(q_radius-d), R' in [.7,1.3].
/// Positive amount contracts (d<0), negative expands (d>0). The root is
/// bracketed by zero and the signed global amplitude bound, clipped to keep
/// source radius in [0,outer]. Each accepted root has a displacement residual.
fn inverse_shift(q: f64, amount: f64, weight: f64, g: &Geometry) -> Result<f64, i32> {
    let bound = (((GAIN * g.outer) * amount.abs()) * weight).abs();
    if !bound.is_finite() || bound == 0.0 { return Err(BOUND_ERROR); }
    let (mut lower, mut upper) = if amount > 0.0 {
        ((-bound).max(q - g.outer), 0.0)
    } else { (0.0, bound.min(q)) };
    let mut shift = radial_motion(q, amount, weight, g);
    if !shift.is_finite() || shift == 0.0 { return Err(BOUND_ERROR); }
    if shift < lower || shift > upper { shift = lower + (upper - lower) * 0.5; }
    for _ in 0..SOLVER_STEPS {
        let radius = q - shift;
        let (l, b) = lateral(radius, g);
        let target = radial_motion(radius, amount, weight, g);
        let residual = shift - target;
        if !radius.is_finite() || radius < 0.0 || radius > g.outer
            || !l.is_finite() || !(0.0..=1.0).contains(&l)
            || !b.is_finite() || !target.is_finite() || !residual.is_finite() {
            return Err(BOUND_ERROR);
        }
        if residual.abs() <= tolerance(shift, target) {
            if shift == 0.0 || target == 0.0 || radius == 0.0
                || (amount > 0.0 && shift >= 0.0)
                || (amount < 0.0 && shift <= 0.0) { return Err(BOUND_ERROR); }
            return Ok(shift);
        }
        if residual < 0.0 { lower = shift; } else { upper = shift; }
        let derivative = 1.0 - ((GAIN * amount) * weight) * b;
        if !derivative.is_finite() || derivative < MIN_FORWARD_DERIVATIVE - 1.0e-14
            || derivative > MAX_FORWARD_DERIVATIVE + 1.0e-14 { return Err(BOUND_ERROR); }
        let newton = shift - residual / derivative;
        let middle = lower + (upper - lower) * 0.5;
        let next = if newton > lower && newton < upper { newton } else { middle };
        if !next.is_finite() || next == shift { return Err(BOUND_ERROR); }
        shift = next;
    }
    Err(BOUND_ERROR)
}

fn fill(points: &[f64], g: &Geometry, scratch: &mut [f64]) -> Result<(), i32> {
    if g.left == 0.0 && g.right == 0.0 { return Ok(()); }
    for (point, delta) in points.chunks_exact(2).zip(scratch.chunks_exact_mut(2)) {
        let x = point[0] - g.ox;
        let y = point[1] - g.oy;
        if !x.is_finite() || !y.is_finite() { return Err(BOUND_ERROR); }
        let u = x * g.rx + y * g.ry;
        let v = x * g.dx + y * g.dy;
        if !u.is_finite() || !v.is_finite() { return Err(BOUND_ERROR); }
        let t = v / g.height;
        if t.is_nan() { return Err(BOUND_ERROR); }
        // Division overflow is beyond finite vertical support. Centerline is
        // fixed exactly, without a positive-width dead zone or side blending.
        if u == 0.0 || u.abs() >= g.outer || v <= 0.0 || t >= 1.0 + TAIL { continue; }
        let amount = if u > 0.0 { g.left } else { g.right };
        if amount == 0.0 { continue; }
        // Positive physical v is not an upper-boundary point merely because
        // division by a huge H underflowed its positive normalized coordinate.
        if t == 0.0 { return Err(BOUND_ERROR); }
        let weight = vertical(t);
        if !weight.is_finite() || weight <= 0.0 || weight > 1.0 { return Err(BOUND_ERROR); }
        let radial_shift = inverse_shift(u.abs(), amount, weight, g)?;
        let shift = if u > 0.0 { radial_shift } else { -radial_shift };
        let ax = g.rx * shift;
        let ay = g.ry * shift;
        let sx = point[0] - ax;
        let sy = point[1] - ay;
        if !ax.is_finite() || !ay.is_finite() || !sx.is_finite() || !sy.is_finite()
            || (ax == 0.0 && ay == 0.0) { return Err(BOUND_ERROR); }
        // Check the representable source, not just the solver's internal root.
        let source_x = sx - g.ox;
        let source_y = sy - g.oy;
        let source_u = source_x * g.rx + source_y * g.ry;
        let source_v = source_x * g.dx + source_y * g.dy;
        let source_t = source_v / g.height;
        let forward_radius = radial_motion(source_u.abs(), amount, vertical(source_t), g);
        let forward_shift = if source_u > 0.0 { forward_radius } else { -forward_radius };
        let scale = point[0].abs().max(point[1].abs()).max(g.ox.abs())
            .max(g.oy.abs()).max(g.height).max(g.outer).max(shift.abs());
        let epsilon = (256.0 * f64::EPSILON * scale).max(SUBNORMAL_FLOOR);
        if !source_x.is_finite() || !source_y.is_finite()
            || !source_u.is_finite() || !source_v.is_finite() || !source_t.is_finite()
            || source_u == 0.0 || (source_u > 0.0) != (u > 0.0)
            || !forward_shift.is_finite() || forward_shift == 0.0
            || (source_v - v).abs() > epsilon
            || (forward_shift - shift).abs() > epsilon
            || ((sx - point[0]) + g.rx * forward_shift).abs() > epsilon
            || ((sy - point[1]) + g.ry * forward_shift).abs() > epsilon {
            return Err(BOUND_ERROR);
        }
        delta[0] = if ax == 0.0 { 0.0 } else { ax };
        delta[1] = if ay == 0.0 { 0.0 } else { ay };
    }
    Ok(())
}

#[no_mangle]
pub extern "C" fn lrt_chin_shape_abi() -> u32 { 1 }

/// Private ABI 1. All lengths are f64 elements. output[N,2]=q-source(q).
/// params=[ox,oy,right_x,right_y,down_x,down_y,H,inner_x,outer_x,left,right].
/// Every error leaves all output untouched. N=1..65536; scratch <=1 MiB payload.
/// # Safety
/// Caller provides live aligned allocations of the declared extents, immutable
/// inputs and exclusively writable output for the full call. Output overlaps
/// neither input. Read-only inputs may overlap. Checked spans do not establish
/// allocation provenance/extent or lifetime; panic containment cannot recover
/// invalid memory, foreign faults, process aborts or allocator termination.
#[no_mangle]
pub unsafe extern "C" fn lrt_chin_shape_evaluate_v1(
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
        let points = slice::from_raw_parts(points, points_len);
        let params = slice::from_raw_parts(params, params_len);
        let geometry = validate(points, params)?;
        let mut scratch = Vec::new();
        scratch.try_reserve_exact(coordinates).map_err(|_| ALLOCATION_ERROR)?;
        scratch.resize(coordinates, 0.0);
        fill(points, &geometry, &mut scratch)?;
        ptr::copy_nonoverlapping(scratch.as_ptr(), output, output_len);
        Ok(())
    });
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

#[cfg(test)]
mod tests;
