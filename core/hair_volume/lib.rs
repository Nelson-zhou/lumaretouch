// SPDX-License-Identifier: GPL-3.0-or-later
//! Original dependency-free crown/side strip geometry. AUTHORED / UNRUN.
//! No pixels, ML, anatomical landmarks, dense weights, inferred contours or RGB
//! resampling. Numeric geometry cannot attest source ownership: the host must.
use std::slice;

const RECIPE_LEN: usize = 4;
const SUPPORT_LEN: usize = 24;
const STATE_LEN: usize = 30;
const FACTS_LEN: usize = 19;
const MAX_POINTS: usize = 1_048_576;
const GAIN: f64 = 0.10; // Original gain: fraction of the narrowest transition.
const MAX_GRADIENT: f64 = 0.45;
const MAX_DISPLACEMENT: f64 = 128.0;
const RESIDUAL: f64 = 1e-7;
const STEP: f64 = 1e-9;
const ITERATIONS: usize = 64;

#[derive(Clone, Copy, Debug)]
struct State([f64; STATE_LEN]);

fn smooth(t: f64) -> (f64, f64) {
    if t <= 0.0 { return (0.0, 0.0); }
    if t >= 1.0 { return (1.0, 0.0); }
    let u = if t <= 0.5 { t } else { 1.0 - t };
    let v = u * u * u * (10.0 + u * (-15.0 + 6.0 * u));
    (if t <= 0.5 { v } else { 1.0 - v }, 30.0 * t * t * (1.0-t) * (1.0-t))
}

fn window(t: f64, p: &[f64]) -> (f64, f64) {
    if t <= p[0] || t >= p[3] { return (0.0, 0.0); }
    if t < p[1] {
        let (v, d) = smooth((t-p[0])/(p[1]-p[0]));
        return (v, d/(p[1]-p[0]));
    }
    if t > p[2] {
        let (v, d) = smooth((p[3]-t)/(p[3]-p[2]));
        return (v, -d/(p[3]-p[2]));
    }
    (1.0, 0.0)
}

impl State {
    fn profile(&self, i: usize) -> &[f64] { &self.0[6+i*8..14+i*8] }

    fn amplitude(&self, i: usize) -> f64 {
        if self.0[3+i] == 0.0 { return 0.0; }
        let p = self.profile(i);
        let margin = (p[1]-p[0]).min(p[3]-p[2]).min(p[5]-p[4]).min(p[7]-p[6]);
        self.0[3+i] * GAIN * margin * if i == 2 { 1.0 } else { -1.0 }
    }

    fn derivative_bound(&self, i: usize) -> f64 {
        let a = self.amplitude(i).abs();
        if a == 0.0 { return 0.0; }
        let p = self.profile(i);
        a * 1.875 * (1.0/(p[1]-p[0]).min(p[3]-p[2]))
            .hypot(1.0/(p[5]-p[4]).min(p[7]-p[6]))
    }

    fn gradient_bound(&self) -> f64 {
        // Side supports are strictly disjoint in x. At a given point only one
        // side row can be nonzero. Frobenius dominates the spectral norm.
        self.derivative_bound(0).hypot(self.derivative_bound(1).max(self.derivative_bound(2)))
    }

    fn displacement_bound(&self) -> f64 {
        self.amplitude(0).abs().hypot(self.amplitude(1).abs().max(self.amplitude(2).abs()))
    }

    fn validate(&self) -> Result<(), i32> {
        let s = self.0;
        if s.iter().any(|v| !v.is_finite()) || s[0] != 1.0
            || !(2.0..=65536.0).contains(&s[1]) || !(2.0..=65536.0).contains(&s[2])
            || s[1].fract() != 0.0 || s[2].fract() != 0.0
            || s[1]*s[2] > 64_000_000.0 { return Err(1); }
        if s[3..6].iter().any(|v| !(-1.0..=1.0).contains(v)) { return Err(2); }
        for i in 0..3 {
            let p = self.profile(i);
            if s[3+i] == 0.0 {
                if p.iter().any(|v| *v != 0.0) { return Err(1); }
                continue;
            }
            for axis in 0..2 {
                let q = &p[axis*4..axis*4+4];
                if !(q[0] < q[1] && q[1] < q[2] && q[2] < q[3])
                    || q[1]-q[0] < 4.0-1e-8 || q[3]-q[2] < 4.0-1e-8 || q[2]-q[1] < 2.0-1e-8 {
                    return Err(6);
                }
                if q[0] < 1.0-1e-8 || q[3] > s[1+axis]-2.0+1e-8 { return Err(8); }
            }
        }
        if s[4] != 0.0 && s[5] != 0.0 && self.profile(1)[3] >= self.profile(2)[0] {
            return Err(6);
        }
        let k = self.gradient_bound();
        if !k.is_finite() || k > MAX_GRADIENT || self.displacement_bound() > MAX_DISPLACEMENT {
            return Err(6);
        }
        Ok(())
    }

    fn forward(&self, x: f64, y: f64) -> ([f64; 2], f64) {
        let mut d = [0.0, 0.0];
        let mut j = [[1.0, 0.0], [0.0, 1.0]];
        for i in 0..3 {
            let a = self.amplitude(i);
            if a == 0.0 { continue; }
            let p = self.profile(i);
            let (wx, gx) = window(x, &p[0..4]);
            let (wy, gy) = window(y, &p[4..8]);
            let axis = if i == 0 { 1 } else { 0 };
            d[axis] += a*wx*wy;
            j[axis][0] += a*gx*wy;
            j[axis][1] += a*wx*gy;
        }
        (d, j[0][0]*j[1][1]-j[0][1]*j[1][0])
    }

    fn in_domain(&self, x: f64, y: f64) -> bool {
        x.is_finite() && y.is_finite() && x >= 0.0 && y >= 0.0
            && x <= self.0[1]-1.0 && y <= self.0[2]-1.0
    }

    fn inverse(&self, qx: f64, qy: f64) -> Result<([f64; 2], f64), i32> {
        if !self.in_domain(qx, qy) { return Err(8); }
        let (mut x, mut y) = (qx, qy);
        let mut converged = false;
        for _ in 0..ITERATIONS {
            let (d, _) = self.forward(x, y);
            let (nx, ny) = (qx-d[0], qy-d[1]);
            if !nx.is_finite() || !ny.is_finite() { return Err(9); }
            let step = (nx-x).hypot(ny-y);
            x = nx; y = ny;
            if step <= STEP { converged = true; break; }
        }
        let (d, det) = self.forward(x, y);
        let residual = (x+d[0]-qx).hypot(y+d[1]-qy);
        let k = self.gradient_bound();
        if !converged || !residual.is_finite() || residual > RESIDUAL || !det.is_finite()
            || det < (1.0-k).powi(2)-1e-12 || det > (1.0+k).powi(2)+1e-12
            || (qx-x).hypot(qy-y) > self.displacement_bound()+RESIDUAL { return Err(9); }
        if !self.in_domain(x, y) { return Err(8); }
        let clean = |v: f64| if v == 0.0 { 0.0 } else { v };
        Ok(([clean(qx-x), clean(qy-y)], 1.0/det))
    }

    fn facts(&self) -> [f64; FACTS_LEN] {
        let mut result = [0.0; FACTS_LEN];
        for i in 0..3 {
            let p = self.profile(i);
            result[i*4..i*4+4].copy_from_slice(&[p[0], p[4], p[3], p[7]]);
        }
        let k = self.gradient_bound();
        result[12..].copy_from_slice(&[self.displacement_bound(), k, (1.0-k).powi(2),
            RESIDUAL, ITERATIONS as f64, self.0[1], self.0[2]]);
        result
    }
}

fn read_state(raw: &[f64]) -> Result<State, i32> {
    if raw.len() != STATE_LEN { return Err(1); }
    let mut out = [0.0; STATE_LEN]; out.copy_from_slice(raw);
    let result = State(out); result.validate()?; Ok(result)
}

fn prepare(recipe: &[f64], support: &[f64], width: f64, height: f64) -> Result<State, i32> {
    if recipe.len() != RECIPE_LEN || support.len() != SUPPORT_LEN || recipe[0] != 1.0
        || recipe.iter().chain(support).any(|v| !v.is_finite()) { return Err(1); }
    let mut out = [0.0; STATE_LEN];
    out[0..3].copy_from_slice(&[1.0, width, height]); out[3..6].copy_from_slice(&recipe[1..]);
    for i in 0..3 {
        for j in 0..8 {
            let value = support[i*8+j];
            if recipe[1+i] == 0.0 {
                if value != 0.0 { return Err(1); }
            } else if !(0.0..1.0).contains(&value) { return Err(6); }
            out[6+i*8+j] = value * if j < 4 { width-1.0 } else { height-1.0 };
        }
    }
    let result = State(out); result.validate()?; Ok(result)
}

// Arithmetic/alignment/disjointness checks cannot prove allocation ownership.
// The C caller still owns valid live memory and exclusion of concurrent writes.
fn buffers_ok(buffers: &[(usize, usize)]) -> bool {
    for (i, &(address, length)) in buffers.iter().enumerate() {
        if address == 0 || address % std::mem::align_of::<f64>() != 0 { return false; }
        let bytes = match length.checked_mul(8) { Some(n) => n, None => return false };
        if bytes > isize::MAX as usize { return false; }
        let end = match address.checked_add(bytes) { Some(n) => n, None => return false };
        for &(other, size) in &buffers[..i] {
            let size = match size.checked_mul(8) { Some(n) => n, None => return false };
            let other_end = match other.checked_add(size) { Some(n) => n, None => return false };
            if bytes != 0 && size != 0 && address < other_end && other < end { return false; }
        }
    }
    true
}

#[no_mangle]
pub extern "C" fn lrt_hair_volume_abi() -> u32 { 1 }

/// # Safety
/// Live, aligned, mutually disjoint length-matched buffers; no concurrent writes.
#[no_mangle]
pub unsafe extern "C" fn lrt_hair_volume_prepare(
    recipe: *const f64, recipe_len: usize, support: *const f64, support_len: usize,
    width: f64, height: f64, out: *mut f64, out_len: usize,
) -> i32 {
    if recipe_len != RECIPE_LEN || support_len != SUPPORT_LEN || out_len != STATE_LEN
        || !buffers_ok(&[(recipe as usize, recipe_len), (support as usize, support_len), (out as usize, out_len)]) { return 1; }
    match prepare(slice::from_raw_parts(recipe, recipe_len), slice::from_raw_parts(support, support_len), width, height) {
        Ok(state) => { slice::from_raw_parts_mut(out, out_len).copy_from_slice(&state.0); 0 },
        Err(code) => code,
    }
}

/// # Safety
/// Live, aligned, mutually disjoint length-matched buffers; no concurrent writes.
#[no_mangle]
pub unsafe extern "C" fn lrt_hair_volume_describe(state: *const f64, state_len: usize, out: *mut f64, out_len: usize) -> i32 {
    if state_len != STATE_LEN || out_len != FACTS_LEN
        || !buffers_ok(&[(state as usize, state_len), (out as usize, out_len)]) { return 1; }
    match read_state(slice::from_raw_parts(state, state_len)) {
        Ok(value) => { slice::from_raw_parts_mut(out, out_len).copy_from_slice(&value.facts()); 0 },
        Err(code) => code,
    }
}

/// # Safety
/// Live, aligned, mutually disjoint buffers, including nonnull empty pointers.
/// All numeric queries are admitted before either output is written.
#[no_mangle]
pub unsafe extern "C" fn lrt_hair_volume_evaluate(
    state: *const f64, state_len: usize, xy: *const f64, xy_len: usize, count: usize,
    out: *mut f64, out_len: usize, jac: *mut f64, jac_len: usize,
) -> i32 {
    if state_len != STATE_LEN || count > MAX_POINTS || xy_len != count*2
        || out_len != count*2 || jac_len != count
        || !buffers_ok(&[(state as usize, state_len), (xy as usize, xy_len), (out as usize, out_len), (jac as usize, jac_len)]) { return 1; }
    let state = match read_state(slice::from_raw_parts(state, state_len)) { Ok(s) => s, Err(c) => return c };
    let points = slice::from_raw_parts(xy, xy_len);
    if points.iter().any(|v| !v.is_finite()) { return 1; }
    for i in 0..count {
        if let Err(c) = state.inverse(points[2*i], points[2*i+1]) { return c; }
    }
    let output = slice::from_raw_parts_mut(out, out_len);
    let jacobian = slice::from_raw_parts_mut(jac, jac_len);
    for i in 0..count {
        match state.inverse(points[2*i], points[2*i+1]) {
            Ok((d, j)) => { output[2*i] = d[0]; output[2*i+1] = d[1]; jacobian[i] = j; },
            Err(c) => return c,
        }
    }
    0
}

#[cfg(test)]
mod tests;
