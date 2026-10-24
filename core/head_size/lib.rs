// SPDX-License-Identifier: GPL-3.0-or-later
//! Original, dependency-free complete-head-and-hair contraction. AUTHORED / UNRUN.
//! No RGB, model inference, hairline inference, sampler, allocation or fallback.
//! The plateau is the independently reviewed complete head AND hair, not a face
//! oval. Body33 observations only veto unsupported input; they do not create it.
use std::slice;

const POINTS_LEN: usize = 33 * 5;
const RECIPE_LEN: usize = 2;
const SUPPORT_LEN: usize = 10;
const STATE_LEN: usize = 13;
const FACTS_LEN: usize = 16;
const MAX_POINTS: usize = 1_048_576;
const GAIN: f64 = 0.08;
const MIN_PLATEAU: f64 = 32.0;
const MIN_MARGIN: f64 = 16.0;
const MAX_DISPLACEMENT: f64 = 128.0;
const MAX_GRADIENT: f64 = 0.45;
const STEP_TOLERANCE: f64 = 1e-9;
const RESIDUAL_TOLERANCE: f64 = 1e-7;
const MAX_ITERATIONS: usize = 64;

// Codes: 1 malformed numeric/state/buffer/version; 2 amount; 4 observations;
// 5 shoulder exclusion; 6 support or safety budget; 8 source domain; 9 inverse.
#[derive(Clone, Copy, Debug)]
struct State([f64; STATE_LEN]);

// Quintic smoothstep, evaluated symmetrically to avoid cancellation near one.
fn smooth(t: f64) -> (f64, f64) {
    if t <= 0.0 { return (0.0, 0.0); }
    if t >= 1.0 { return (1.0, 0.0); }
    let u = if t <= 0.5 { t } else { 1.0 - t };
    let value = u * u * u * (10.0 + u * (-15.0 + 6.0 * u));
    let derivative = 30.0 * t * t * (1.0 - t) * (1.0 - t);
    (if t <= 0.5 { value } else { 1.0 - value }, derivative)
}

fn window(t: f64, a: f64, b: f64, c: f64, d: f64) -> (f64, f64) {
    if t <= a || t >= d { return (0.0, 0.0); }
    if t < b {
        let (value, derivative) = smooth((t - a) / (b - a));
        return (value, derivative / (b - a));
    }
    if t > c {
        let (value, derivative) = smooth((d - t) / (d - c));
        return (value, -derivative / (d - c));
    }
    (1.0, 0.0)
}

impl State {
    fn radius(self) -> f64 {
        let s = self.0;
        let rx = (s[0] - s[8]).abs().max((s[3] - s[8]).abs());
        let ry = (s[4] - s[9]).abs().max((s[7] - s[9]).abs());
        rx.hypot(ry)
    }

    fn gradient_bound(self) -> f64 {
        let s = self.0;
        let mx = (s[1] - s[0]).min(s[3] - s[2]);
        let my = (s[5] - s[4]).min(s[7] - s[6]);
        s[10] * (1.0 + self.radius() * 1.875 * (1.0 / mx).hypot(1.0 / my))
    }

    fn displacement_bound(self) -> f64 { self.0[10] * self.radius() }

    // Always recheck, including user-forged states, neutral and empty queries.
    // Pose/review provenance is deliberately not claimed by these 13 numbers.
    fn validate(self) -> Result<(), i32> {
        let s = self.0;
        if s.iter().any(|v| !v.is_finite())
            || !(2.0..=1_000_000.0).contains(&s[11])
            || !(2.0..=1_000_000.0).contains(&s[12])
            || s[11].fract() != 0.0 || s[12].fract() != 0.0
            || !(s[0] < s[1] && s[1] < s[2] && s[2] < s[3]
                 && s[4] < s[5] && s[5] < s[6] && s[6] < s[7]) {
            return Err(1);
        }
        if s[0] < 1.0 || s[3] > s[11] - 2.0
            || s[4] < 1.0 || s[7] > s[12] - 2.0 { return Err(8); }
        if !(0.0..=GAIN).contains(&s[10])
            || s[2] - s[1] < MIN_PLATEAU || s[6] - s[5] < MIN_PLATEAU
            || s[1] - s[0] < MIN_MARGIN || s[3] - s[2] < MIN_MARGIN
            || s[5] - s[4] < MIN_MARGIN || s[7] - s[6] < MIN_MARGIN
            || !(s[1] < s[8] && s[8] < s[2] && s[5] < s[9] && s[9] < s[6])
            || self.gradient_bound() > MAX_GRADIENT
            || self.displacement_bound() > MAX_DISPLACEMENT { return Err(6); }
        Ok(())
    }

    // Returns forward displacement and the forward Jacobian determinant.
    fn forward(self, x: f64, y: f64) -> ([f64; 2], f64) {
        let s = self.0;
        if s[10] == 0.0 || x <= s[0] || x >= s[3] || y <= s[4] || y >= s[7] {
            return ([0.0, 0.0], 1.0);
        }
        let (wx, gx) = window(x, s[0], s[1], s[2], s[3]);
        let (wy, gy) = window(y, s[4], s[5], s[6], s[7]);
        let weight = wx * wy;
        let dx = gx * wy;
        let dy = wx * gy;
        let rx = x - s[8];
        let ry = y - s[9];
        let k = s[10];
        let a = 1.0 - k * (weight + rx * dx);
        let b = -k * rx * dy;
        let c = -k * ry * dx;
        let d = 1.0 - k * (weight + ry * dy);
        ([-k * weight * rx, -k * weight * ry], a * d - b * c)
    }

    fn in_domain(self, x: f64, y: f64) -> bool {
        x.is_finite() && y.is_finite() && x >= 0.0 && x <= self.0[11] - 1.0
            && y >= 0.0 && y <= self.0[12] - 1.0
    }

    // q = p + d(p), p_(n+1) = q - d(p_n). Return delta=q-p, not p-q.
    fn inverse(self, qx: f64, qy: f64) -> Result<([f64; 2], f64), i32> {
        if !self.in_domain(qx, qy) { return Err(8); }
        let mut px = qx;
        let mut py = qy;
        let mut converged = false;
        for _ in 0..MAX_ITERATIONS {
            let (d, _) = self.forward(px, py);
            let nx = qx - d[0];
            let ny = qy - d[1];
            if !nx.is_finite() || !ny.is_finite() { return Err(9); }
            let step = (nx - px).hypot(ny - py);
            px = nx;
            py = ny;
            if step <= STEP_TOLERANCE { converged = true; break; }
        }
        let (d, determinant) = self.forward(px, py);
        let bound = self.gradient_bound();
        let residual = (px + d[0] - qx).hypot(py + d[1] - qy);
        let lower = (1.0 - bound) * (1.0 - bound);
        let upper = (1.0 + bound) * (1.0 + bound);
        if !converged || !residual.is_finite() || residual > RESIDUAL_TOLERANCE
            || !determinant.is_finite() || determinant < lower - 1e-12
            || determinant > upper + 1e-12
            || (qx - px).hypot(qy - py) > self.displacement_bound() + RESIDUAL_TOLERANCE {
            return Err(9);
        }
        if !self.in_domain(px, py) { return Err(8); }
        let dx = qx - px;
        let dy = qy - py;
        Ok(([if dx == 0.0 { 0.0 } else { dx }, if dy == 0.0 { 0.0 } else { dy }],
            1.0 / determinant))
    }

    fn facts(self) -> [f64; FACTS_LEN] {
        let s = self.0;
        let bound = self.gradient_bound();
        [s[0], s[4], s[3], s[7], s[1], s[5], s[2], s[6], s[8], s[9],
         1.0 - s[10], self.displacement_bound(), bound, (1.0 - bound) * (1.0 - bound),
         RESIDUAL_TOLERANCE, MAX_ITERATIONS as f64]
    }
}

fn read_state(raw: &[f64]) -> Result<State, i32> {
    if raw.len() != STATE_LEN { return Err(1); }
    let mut values = [0.0; STATE_LEN];
    values.copy_from_slice(raw);
    let state = State(values);
    state.validate()?;
    Ok(state)
}

// These checks prove bounded arithmetic/alignment/disjointness, NOT that an
// arbitrary pointer owns a live allocation. Valid memory and no concurrent
// mutation throughout the call remain the unsafe C caller's obligations.
fn disjoint_buffers(buffers: &[(usize, usize)]) -> bool {
    for (i, &(address, length)) in buffers.iter().enumerate() {
        if address == 0 || address % std::mem::align_of::<f64>() != 0 { return false; }
        let bytes = match length.checked_mul(std::mem::size_of::<f64>()) {
            Some(value) => value, None => return false,
        };
        if bytes > isize::MAX as usize { return false; }
        let end = match address.checked_add(bytes) { Some(value) => value, None => return false };
        for &(other_address, other_length) in &buffers[..i] {
            let other_bytes = match other_length.checked_mul(std::mem::size_of::<f64>()) {
                Some(value) => value, None => return false,
            };
            let other_end = match other_address.checked_add(other_bytes) {
                Some(value) => value, None => return false,
            };
            if bytes != 0 && other_bytes != 0 && address < other_end && other_address < end {
                return false;
            }
        }
    }
    true
}

fn prepare(points: &[f64], recipe: &[f64], support: &[f64], w: f64, h: f64) -> Result<State, i32> {
    if points.len() != POINTS_LEN || recipe.len() != RECIPE_LEN || support.len() != SUPPORT_LEN
        || points.iter().chain(support).any(|v| !v.is_finite())
        || recipe[0] != 1.0 || !w.is_finite() || !h.is_finite()
        || !(2.0..=1_000_000.0).contains(&w) || !(2.0..=1_000_000.0).contains(&h)
        || w.fract() != 0.0 || h.fract() != 0.0 { return Err(1); }
    if !recipe[1].is_finite() || !(0.0..=1.0).contains(&recipe[1]) { return Err(2); }
    if support.iter().any(|v| *v <= 0.0 || *v >= 1.0) { return Err(6); }
    // All head landmarks 0..10 and both real shoulders 11,12 must be observed.
    // Low-confidence unused limbs never become synthetic head evidence.
    for i in 0..13 {
        let p = &points[i * 5..i * 5 + 5];
        if p[0] <= 0.0 || p[0] >= 1.0 || p[1] <= 0.0 || p[1] >= 1.0
            || !(0.8..=1.0).contains(&p[3]) || !(0.8..=1.0).contains(&p[4]) {
            return Err(4);
        }
    }
    let s = State([
        support[4] * (w - 1.0), support[0] * (w - 1.0),
        support[2] * (w - 1.0), support[6] * (w - 1.0),
        support[5] * (h - 1.0), support[1] * (h - 1.0),
        support[3] * (h - 1.0), support[7] * (h - 1.0),
        support[8] * (w - 1.0), support[9] * (h - 1.0), recipe[1] * GAIN, w, h,
    ]);
    s.validate()?;
    let shoulder_dx = (points[11 * 5] - points[12 * 5]).abs() * (w - 1.0);
    let shoulder_dy = (points[11 * 5 + 1] - points[12 * 5 + 1]).abs() * (h - 1.0);
    let shoulder_dz = (points[11 * 5 + 2] - points[12 * 5 + 2]).abs() * (w - 1.0);
    if shoulder_dx < 32.0 || shoulder_dy > 0.25 * shoulder_dx
        || shoulder_dz > 0.35 * shoulder_dx { return Err(5); }
    if s.0[7] >= points[11 * 5 + 1] * (h - 1.0)
        || s.0[7] >= points[12 * 5 + 1] * (h - 1.0) { return Err(5); }
    for i in 0..11 {
        let x = points[i * 5] * (w - 1.0);
        let y = points[i * 5 + 1] * (h - 1.0);
        if x <= s.0[1] || x >= s.0[2] || y <= s.0[5] || y >= s.0[6] { return Err(6); }
    }
    Ok(s)
}

#[no_mangle]
pub extern "C" fn lrt_head_size_abi() -> u32 { 1 }

/// # Safety
/// Pointers must be live, aligned, length-matched, mutually disjoint allocations.
/// No input or output may be concurrently mutated throughout this call.
#[no_mangle]
pub unsafe extern "C" fn lrt_head_size_prepare(
    points: *const f64, points_len: usize, recipe: *const f64, recipe_len: usize,
    support: *const f64, support_len: usize, w: f64, h: f64,
    out: *mut f64, out_len: usize,
) -> i32 {
    if points_len != POINTS_LEN || recipe_len != RECIPE_LEN
        || support_len != SUPPORT_LEN || out_len != STATE_LEN
        || !disjoint_buffers(&[(points as usize, points_len), (recipe as usize, recipe_len),
            (support as usize, support_len), (out as usize, out_len)]) { return 1; }
    match prepare(slice::from_raw_parts(points, points_len), slice::from_raw_parts(recipe, recipe_len),
                  slice::from_raw_parts(support, support_len), w, h) {
        Ok(state) => { slice::from_raw_parts_mut(out, out_len).copy_from_slice(&state.0); 0 },
        Err(code) => code,
    }
}

/// # Safety
/// The same live, disjoint, aligned and non-concurrent buffer rules apply.
#[no_mangle]
pub unsafe extern "C" fn lrt_head_size_describe(
    state: *const f64, state_len: usize, out: *mut f64, out_len: usize,
) -> i32 {
    if state_len != STATE_LEN || out_len != FACTS_LEN
        || !disjoint_buffers(&[(state as usize, state_len), (out as usize, out_len)]) { return 1; }
    match read_state(slice::from_raw_parts(state, state_len)) {
        Ok(state) => { slice::from_raw_parts_mut(out, out_len).copy_from_slice(&state.facts()); 0 },
        Err(code) => code,
    }
}

/// # Safety
/// All four buffers must be live, aligned, length-matched and disjoint; inputs
/// must remain unchanged until return. Empty buffers still need aligned nonnull
/// pointers. On refusal, neither output buffer is written under this contract.
#[no_mangle]
pub unsafe extern "C" fn lrt_head_size_evaluate(
    state: *const f64, state_len: usize, xy: *const f64, xy_len: usize, count: usize,
    out: *mut f64, out_len: usize, jac: *mut f64, jac_len: usize,
) -> i32 {
    if state_len != STATE_LEN || count > MAX_POINTS || xy_len != count * 2
        || out_len != count * 2 || jac_len != count
        || !disjoint_buffers(&[(state as usize, state_len), (xy as usize, xy_len),
            (out as usize, out_len), (jac as usize, jac_len)]) { return 1; }
    let state = match read_state(slice::from_raw_parts(state, state_len)) {
        Ok(value) => value, Err(code) => return code,
    };
    let input = slice::from_raw_parts(xy, xy_len);
    if input.iter().any(|v| !v.is_finite()) { return 1; }
    // Deterministic, allocation-free admission pass precedes all output writes.
    for i in 0..count {
        if let Err(code) = state.inverse(input[i * 2], input[i * 2 + 1]) { return code; }
    }
    let output = slice::from_raw_parts_mut(out, out_len);
    let determinants = slice::from_raw_parts_mut(jac, jac_len);
    for i in 0..count {
        match state.inverse(input[i * 2], input[i * 2 + 1]) {
            Ok((delta, determinant)) => {
                output[i * 2] = delta[0];
                output[i * 2 + 1] = delta[1];
                determinants[i] = determinant;
            },
            Err(code) => return code,
        }
    }
    0
}

#[cfg(test)]
mod tests;
