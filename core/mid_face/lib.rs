// SPDX-License-Identifier: GPL-3.0-or-later
//! Original monotone mid-face inverse with a retained lower-face plateau. AUTHORED / UNRUN.
//! No RGB sampling, identity pins, inference, external code or model weights.
use std::{mem, panic, ptr, slice};

pub const MAX_POINTS: usize = 65_536;
pub const PARAMS_LEN: usize = 12;
pub const GAIN: f64 = 0.08;
pub const FRAME_TOLERANCE: f64 = 1.0e-10;
pub const MIN_TAIL: f64 = 0.25;
pub const MAX_TAIL: f64 = 4.0;
pub const MIN_PLATEAU_END: f64 = 1.25;
pub const MAX_PLATEAU_END: f64 = 8.0;
pub const MIN_FORWARD_DERIVATIVE: f64 = 0.4;
pub const ABI_ERROR: i32 = 1;
pub const VALUE_ERROR: i32 = 2;
pub const FRAME_ERROR: i32 = 3;
pub const BOUND_ERROR: i32 = 4;
pub const ALLOCATION_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;
const SOLVER_STEPS: usize = 96;
const RESIDUAL_ULPS: f64 = 64.0;
const SUBNORMAL_FLOOR: f64 = f64::from_bits(8);

#[derive(Clone, Copy)]
struct Geometry {
    ox: f64, oy: f64, rx: f64, ry: f64, dx: f64, dy: f64,
    height: f64, inner: f64, outer: f64, plateau_end: f64, tail: f64, amount: f64,
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
        || !(-1.0..=1.0).contains(&p[11]) { return Err(VALUE_ERROR); }
    let rn = p[2].hypot(p[3]);
    let dn = p[4].hypot(p[5]);
    let dot = p[2] * p[4] + p[3] * p[5];
    if !rn.is_finite() || !dn.is_finite() || !dot.is_finite()
        || (rn - 1.0).abs() > FRAME_TOLERANCE
        || (dn - 1.0).abs() > FRAME_TOLERANCE || dot.abs() > FRAME_TOLERANCE
        || p[6] <= 0.0 { return Err(FRAME_ERROR); }
    if p[7] <= 0.0 || p[8] <= p[7]
        || !(MIN_PLATEAU_END..=MAX_PLATEAU_END).contains(&p[9])
        || !(MIN_TAIL..=MAX_TAIL).contains(&p[10]) {
        return Err(BOUND_ERROR);
    }
    // Roundoff normalization only, after strict rejection of nonorthonormal
    // input. Both handednesses are valid; do not infer anatomical orientation.
    let rx = p[2] / rn;
    let ry = p[3] / rn;
    let handedness = p[2] * p[5] - p[3] * p[4];
    let (dx, dy) = if handedness > 0.0 { (-ry, rx) } else { (ry, -rx) };
    Ok(Geometry { ox: p[0], oy: p[1], rx, ry, dx, dy, height: p[6],
                  inner: p[7], outer: p[8], plateau_end: p[9], tail: p[10], amount: p[11] })
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
// The flat interval is deliberately NOT lower_face's rise-and-fall envelope.
// Equal-u points from nose t=1 through measured plateau_end translate equally.
// The host must enclose every retained lower-face point plus measured padding
// in the flat vertical plateau, and every claimed target in the lateral core.
// plateau_end includes chin but is not assumed to equal its coordinate.
fn vertical(t: f64, plateau_end: f64, tail: f64) -> (f64, f64) {
    if t <= 0.0 || t >= plateau_end + tail { (0.0, 0.0) }
    else if t < 1.0 { (smoothstep(t), smoothstep_derivative(t)) }
    else if t <= plateau_end { (1.0, 0.0) }
    else {
        // Evaluate neck feather from its zero edge rather than 1-S(z).
        let z = (plateau_end + tail - t) / tail;
        (smoothstep(z), -smoothstep_derivative(z) / tail)
    }
}
fn lateral(u: f64, g: &Geometry) -> f64 {
    let x = u.abs();
    if x <= g.inner { 1.0 } else if x >= g.outer { 0.0 }
    else { smoothstep((g.outer - x) / (g.outer - g.inner)) }
}
fn residual_tolerance(a: f64, b: f64) -> f64 {
    (RESIDUAL_ULPS * f64::EPSILON * a.abs().max(b.abs())).max(SUBNORMAL_FLOOR)
}

/// Solve the inverse shift itself, not source subtraction or negated forward
/// motion. g(d)=d-k*V(tq-d/H) has g' >= 0.4. Its root is bracketed by 0 and k.
/// V is flat from measured nose to chin; its plateau does not change the
/// derivative lower bound 1-.08*abs(amount)*1.875/min(1,tail) >= .4.
/// Computing physical k as (0.08*H)*amount*L also preserves subnormal amounts
/// when multiplying by a large H makes their physical shift representable.
fn inverse_shift(tq: f64, k: f64, g: &Geometry) -> Result<f64, i32> {
    if k == 0.0 { return Err(BOUND_ERROR); }
    let mut lower = k.min(0.0);
    let mut upper = k.max(0.0);
    let mut shift = k * vertical(tq, g.plateau_end, g.tail).0;
    if shift == 0.0 { return Err(BOUND_ERROR); }
    for _ in 0..SOLVER_STEPS {
        let source_t = tq - shift / g.height;
        let (weight, slope) = vertical(source_t, g.plateau_end, g.tail);
        let target = k * weight;
        let residual = shift - target;
        if !source_t.is_finite() || !weight.is_finite() || !residual.is_finite()
            || !(0.0..=1.0).contains(&weight) { return Err(BOUND_ERROR); }
        if residual.abs() <= residual_tolerance(shift, target) {
            // Never silently neutralize a mathematically nonzero supported edit.
            if shift == 0.0 || target == 0.0 { return Err(BOUND_ERROR); }
            return Ok(shift);
        }
        if residual < 0.0 { lower = shift; } else { upper = shift; }
        let derivative = 1.0 + (k / g.height) * slope;
        if !derivative.is_finite() || derivative < MIN_FORWARD_DERIVATIVE - 1.0e-14 {
            return Err(BOUND_ERROR);
        }
        let newton = shift - residual / derivative;
        let middle = lower + (upper - lower) * 0.5;
        let next = if newton > lower && newton < upper { newton } else { middle };
        if !next.is_finite() || next == shift { return Err(BOUND_ERROR); }
        shift = next;
    }
    Err(BOUND_ERROR)
}

fn fill(points: &[f64], g: &Geometry, scratch: &mut [f64]) -> Result<(), i32> {
    if g.amount == 0.0 { return Ok(()); }
    for (point, delta) in points.chunks_exact(2).zip(scratch.chunks_exact_mut(2)) {
        let x = point[0] - g.ox;
        let y = point[1] - g.oy;
        if !x.is_finite() || !y.is_finite() { return Err(BOUND_ERROR); }
        let u = x * g.rx + y * g.ry;
        let v = x * g.dx + y * g.dy;
        if !u.is_finite() || !v.is_finite() { return Err(BOUND_ERROR); }
        let tq = v / g.height;
        // Division overflow from a positive tiny H is outside finite support.
        if tq.is_nan() { return Err(BOUND_ERROR); }
        if u.abs() >= g.outer || tq <= 0.0 || tq >= g.plateau_end + g.tail { continue; }
        let l = lateral(u, g);
        if !l.is_finite() || !(0.0..=1.0).contains(&l) || l == 0.0 {
            return Err(BOUND_ERROR);
        }
        let k = ((GAIN * g.height) * g.amount) * l;
        if !k.is_finite() { return Err(BOUND_ERROR); }
        let shift = inverse_shift(tq, k, g)?;
        let ax = g.dx * shift;
        let ay = g.dy * shift;
        let sx = point[0] - ax;
        let sy = point[1] - ay;
        if !ax.is_finite() || !ay.is_finite() || !sx.is_finite() || !sy.is_finite()
            || (ax == 0.0 && ay == 0.0) { return Err(BOUND_ERROR); }
        // Verify the representable source actually satisfies the forward map.
        // Tolerance is explicitly tied to f64 coordinates, not a quality claim.
        let source_x = sx - g.ox;
        let source_y = sy - g.oy;
        let source_u = source_x * g.rx + source_y * g.ry;
        let source_v = source_x * g.dx + source_y * g.dy;
        let source_t = source_v / g.height;
        let actual_k = ((GAIN * g.height) * g.amount) * lateral(source_u, g);
        let forward_shift = actual_k * vertical(source_t, g.plateau_end, g.tail).0;
        let scale = point[0].abs().max(point[1].abs()).max(g.ox.abs())
            .max(g.oy.abs()).max(g.height).max(shift.abs());
        let tolerance = (256.0 * f64::EPSILON * scale).max(SUBNORMAL_FLOOR);
        if !source_u.is_finite() || !source_v.is_finite() || !source_t.is_finite()
            || !forward_shift.is_finite() || (source_u - u).abs() > tolerance
            || (forward_shift - shift).abs() > tolerance
            || ((sx - point[0]) + g.dx * forward_shift).abs() > tolerance
            || ((sy - point[1]) + g.dy * forward_shift).abs() > tolerance {
            return Err(BOUND_ERROR);
        }
        delta[0] = if ax == 0.0 { 0.0 } else { ax };
        delta[1] = if ay == 0.0 { 0.0 } else { ay };
    }
    Ok(())
}

#[no_mangle]
pub extern "C" fn lrt_mid_face_abi() -> u32 { 1 }

/// Private ABI 1, lengths in f64 elements; output[N,2] = q-source(q).
/// params=[ox,oy,right_x,right_y,down_x,down_y,H,inner_x,outer_x,plateau_end,tail,amount].
/// All failures leave output untouched. N=1..65536. No sampling or fallback.
/// # Safety
/// Caller provides live aligned allocations of the declared extents, immutable
/// inputs and exclusively writable output for the full call. Output overlaps no
/// input; read-only inputs may overlap each other. Checked address arithmetic
/// cannot prove allocation extent, lifetime or provenance. Invalid non-null
/// memory, process aborts and foreign faults cannot be recovered by catch_unwind.
#[no_mangle]
pub unsafe extern "C" fn lrt_mid_face_evaluate_v1(
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
        // At most 1 MiB f64 payload. Reserve failure is a normal bounded error.
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
