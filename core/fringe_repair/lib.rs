// SPDX-License-Identifier: GPL-3.0-or-later
//! Original directional, reference-guided black/white edit-halo repair.
//! AUTHORED UNRUN: no numerical, visual, build, or performance acceptance yet.
//! This is not lens chromatic defringe, morphology, or a generic blur alias.
//! Immutable full-resolution float32 RGB in; bounded RGB tile out, no clipping.
//! Read ../../docs/fringe-repair/KERNEL.md before integrating.

use std::{ffi::c_void, mem, ptr, slice};

pub const MAX_SOURCE_PIXELS: usize = 100_000_000;
pub const MAX_TILE_PIXELS: usize = 65_536;
pub const ABI_ERROR: i32 = 1;
pub const SETTINGS_ERROR: i32 = 2;
pub const PIXEL_ERROR: i32 = 3;
pub const ALLOCATION_ERROR: i32 = 4;
pub const RESULT_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;
pub const CANCELLED: i32 = 7;

#[derive(Clone, Copy, Debug)]
pub struct Settings {
    pub strength: f32,
    /// Radius at original source resolution, before an explicit preview scale.
    pub radius_source: f32,
    /// Processing raster pixels / original source pixels, 1 for native export.
    pub scale: f32,
    /// Minimum residual prominence as a fraction of the local edited edge.
    pub threshold: f32,
}

impl Default for Settings {
    fn default() -> Self {
        Self { strength: 0.5, radius_source: 2.0, scale: 1.0, threshold: 0.02 }
    }
}

impl Settings {
    fn valid(self) -> bool {
        self.strength.is_finite() && (0.0..=1.0).contains(&self.strength)
            && valid_radius(self.radius_source, self.scale)
            && self.threshold.is_finite() && (0.001..=0.25).contains(&self.threshold)
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Tile {
    pub x: usize,
    pub y: usize,
    pub width: usize,
    pub height: usize,
}

fn valid_radius(radius: f32, scale: f32) -> bool {
    radius.is_finite() && (0.5..=32.0).contains(&radius)
        && scale.is_finite() && (0.03125..=8.0).contains(&scale)
}

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

#[no_mangle]
pub extern "C" fn lrt_fringe_repair_abi() -> u32 { 1 }

/// Conservative access radius in PROCESSING raster pixels. 0 means invalid.
/// Profiles reach 3s along the normal, max(1, s/2) along the tangent, plus
/// one bilinear tap. This overbounds each axis without relying on direction.
#[no_mangle]
pub extern "C" fn lrt_fringe_required_halo(radius_source: f32, scale: f32) -> usize {
    if !valid_radius(radius_source, scale) { return 0; }
    let s = (2.0 * radius_source as f64 * scale as f64).max(0.5);
    (3.0 * s + (0.5 * s).max(1.0) + 1.0).ceil() as usize
}

/// Validate a full immutable snapshot once. The renderer rechecks accessed taps.
/// # Safety
/// `input` must point to `length` live readable aligned floats throughout call.
#[no_mangle]
pub unsafe extern "C" fn lrt_fringe_validate_rgb(
    input: *const f32, length: usize, width: usize, height: usize,
) -> i32 {
    let n = match count(width, height, MAX_SOURCE_PIXELS) { Some(n) => n, None => return ABI_ERROR };
    if length != n * 3 || region(input, length).is_none() { return ABI_ERROR; }
    if slice::from_raw_parts(input, length).iter().all(|v| v.is_finite()) { 0 } else { PIXEL_ERROR }
}

/// # Safety
/// `input` must point to `length` live readable aligned floats throughout call.
#[no_mangle]
pub unsafe extern "C" fn lrt_fringe_validate_coverage(
    input: *const f32, length: usize, width: usize, height: usize,
) -> i32 {
    let n = match count(width, height, MAX_SOURCE_PIXELS) { Some(n) => n, None => return ABI_ERROR };
    if length != n || region(input, length).is_none() { return ABI_ERROR; }
    if slice::from_raw_parts(input, length).iter().all(|v| v.is_finite() && (0.0..=1.0).contains(v)) {
        0
    } else { PIXEL_ERROR }
}

type Rgb = [f64; 3];

fn luma(rgb: Rgb) -> f64 {
    // Rec.709-weighted luma proxy. This does not perform transfer conversion.
    0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
}

fn average(a: Rgb, b: Rgb) -> Rgb {
    std::array::from_fn(|c| 0.5 * (a[c] + b[c]))
}

struct Frame<'a> {
    edited: &'a [f32],
    guide: &'a [f32],
    width: usize,
    height: usize,
}

impl Frame<'_> {
    fn pixel(&self, source: &[f32], x: usize, y: usize) -> Result<Rgb, i32> {
        let offset = 3 * (y * self.width + x);
        let p = [source[offset], source[offset + 1], source[offset + 2]];
        if p.iter().any(|v| !v.is_finite()) { return Err(PIXEL_ERROR); }
        Ok(p.map(|v| v as f64))
    }

    fn sample(&self, source: &[f32], x: f64, y: f64) -> Result<Option<Rgb>, i32> {
        // Missing full-frame evidence is not clamped into a fictitious plateau.
        if x < 0.0 || y < 0.0 || x > (self.width - 1) as f64 || y > (self.height - 1) as f64 {
            return Ok(None);
        }
        let xa = x.floor() as usize;
        let ya = y.floor() as usize;
        let xb = (xa + 1).min(self.width - 1);
        let yb = (ya + 1).min(self.height - 1);
        let fx = x - xa as f64;
        let fy = y - ya as f64;
        let a = self.pixel(source, xa, ya)?;
        let b = self.pixel(source, xb, ya)?;
        let c = self.pixel(source, xa, yb)?;
        let d = self.pixel(source, xb, yb)?;
        Ok(Some(std::array::from_fn(|i| {
            let top = a[i] * (1.0 - fx) + b[i] * fx;
            let bottom = c[i] * (1.0 - fx) + d[i] * fx;
            top * (1.0 - fy) + bottom * fy
        })))
    }
}

#[derive(Clone, Copy)]
struct Candidate {
    residual: f64,
    bounded: f64,
    confidence: f64,
    score: f64,
    edge_sign: f64,
    direction: (f64, f64),
    step: f64,
}

/// A seven-sample NORMAL profile. The guide contributes only evidence and
/// retained center detail, never a global replacement for the edited raster.
fn candidate(
    frame: &Frame<'_>, x: f64, y: f64, direction: (f64, f64), step: f64, threshold: f64,
) -> Result<Option<Candidate>, i32> {
    let mut g = [[0.0; 3]; 7];
    let mut e = [[0.0; 3]; 7];
    for j in 0..7 {
        let distance = (j as f64 - 3.0) * step;
        let px = x + distance * direction.0;
        let py = y + distance * direction.1;
        g[j] = match frame.sample(frame.guide, px, py)? { Some(p) => p, None => return Ok(None) };
        e[j] = match frame.sample(frame.edited, px, py)? { Some(p) => p, None => return Ok(None) };
    }
    let gy = g.map(luma);
    let ey = e.map(luma);
    let gl = average(g[0], g[1]);
    let gr = average(g[5], g[6]);
    let el = average(e[0], e[1]);
    let er = average(e[5], e[6]);
    let gspan = luma(gr) - luma(gl);
    let espan = luma(er) - luma(el);
    let gm = gspan.abs();
    let em = espan.abs();
    let magnitude = gy.iter().chain(ey.iter()).fold(1.0_f64, |a, b| a.max(b.abs()));
    let floor = 1.0e-6 * magnitude;
    // Very weak/flat edges and contrast reversals cannot support this model.
    if gm < 64.0 * floor || em < 64.0 * floor || gspan.signum() != espan.signum() {
        return Ok(None);
    }
    let gs = gspan.signum();
    let gplateau = (gy[0] - gy[1]).abs().max((gy[5] - gy[6]).abs());
    let eplateau = (ey[0] - ey[1]).abs().max((ey[5] - ey[6]).abs());
    if gplateau > 0.12 * gm + floor || eplateau > 0.15 * em + floor {
        return Ok(None);
    }
    let backtrack: f64 = gy.windows(2).map(|p| (-(p[1] - p[0]) * gs).max(0.0)).sum();
    if backtrack > 0.06 * gm + floor || (gy[4] - gy[2]) * gs < 0.5 * gm {
        return Ok(None);
    }
    let mut residual_rgb = [[0.0; 3]; 3];
    for j in 2..=4 {
        let t = (gy[j] - luma(gl)) / gspan;
        if !(-0.03..=1.03).contains(&t) { return Ok(None); }
        let t = t.clamp(0.0, 1.0);
        // Original texture plus a smoothly varying EDIT DELTA, not blurred RGB.
        for c in 0..3 {
            let expected = g[j][c] + (el[c] - gl[c]) * (1.0 - t) + (er[c] - gr[c]) * t;
            residual_rgb[j - 2][c] = e[j][c] - expected;
        }
    }
    let r = residual_rgb.map(luma);
    let residual = r[1];
    let amplitude = residual.abs();
    let minimum = threshold * em + 4.0 * floor;
    if amplitude <= minimum || amplitude > 1.5 * em { return Ok(None); }
    let sign = residual.signum();
    let prominence = amplitude - 0.5 * ((r[0] * sign).max(0.0) + (r[2] * sign).max(0.0));
    if prominence <= minimum { return Ok(None); }
    // A neutral additive artifact should move all channels together. Large
    // chromatic residuals belong to colour/matting tools, not this operator.
    let chroma_deviation = residual_rgb[1].iter().fold(0.0_f64, |a, v| a.max((v - residual).abs()));
    if chroma_deviation > 0.35 * amplitude + minimum { return Ok(None); }
    let confidence = (prominence / (2.0 * minimum)).min(1.0)
        * (1.0 - backtrack / (0.08 * gm + floor)).clamp(0.0, 1.0);
    Ok(Some(Candidate {
        residual,
        bounded: residual.signum() * amplitude.min(0.35 * em),
        confidence,
        score: confidence * prominence / em,
        edge_sign: gs,
        direction,
        step,
    }))
}

fn correction(frame: &Frame<'_>, x: f64, y: f64, settings: Settings) -> Result<f64, i32> {
    const Q: f64 = std::f64::consts::FRAC_1_SQRT_2;
    const DIRECTIONS: [(f64, f64); 4] = [(1.0, 0.0), (Q, Q), (0.0, 1.0), (-Q, Q)];
    let mut candidates: [Option<Candidate>; 12] = [None; 12];
    let mut best: Option<Candidate> = None;
    for (si, factor) in [0.5, 1.0, 2.0].iter().enumerate() {
        let step = (settings.radius_source as f64 * settings.scale as f64 * factor).max(0.5);
        for (di, direction) in DIRECTIONS.iter().enumerate() {
            let found = candidate(frame, x, y, *direction, step, settings.threshold as f64)?;
            candidates[si * 4 + di] = found;
            if let Some(c) = found {
                if best.map_or(true, |b| c.score > b.score) { best = Some(c); }
            }
        }
    }
    let chosen = match best { Some(c) => c, None => return Ok(0.0) };
    // Strong opposite-polarity evidence across scales/directions is ambiguous.
    if candidates.iter().flatten().any(|c| c.residual.signum() != chosen.residual.signum()
        && c.score >= 0.5 * chosen.score) { return Ok(0.0); }
    let tangent = (-chosen.direction.1, chosen.direction.0);
    let distance = (0.5 * chosen.step).max(1.0);
    let mut confidence = chosen.confidence;
    for sign in [-1.0, 1.0] {
        let side = candidate(frame, x + tangent.0 * distance * sign,
            y + tangent.1 * distance * sign, chosen.direction, chosen.step, settings.threshold as f64)?;
        let side = match side { Some(c) => c, None => return Ok(0.0) };
        if side.residual.signum() != chosen.residual.signum() || side.edge_sign != chosen.edge_sign {
            return Ok(0.0);
        }
        let ratio = side.residual.abs() / chosen.residual.abs();
        if !(0.35..=3.0).contains(&ratio) { return Ok(0.0); }
        confidence = confidence.min(side.confidence);
    }
    Ok(chosen.bounded * confidence)
}

/// Render one immutable-snapshot tile. No output allocation exceeds 768 KiB.
/// Whole-frame validation should be cached by the caller per immutable source;
/// this function validates every actually accessed pixel, including halo taps.
pub fn render_tile(
    edited: &[f32], guide: &[f32], width: usize, height: usize,
    coverage: Option<&[f32]>, tile: Tile, settings: Settings, cancel: &dyn Fn() -> bool,
) -> Result<Vec<f32>, i32> {
    let n = count(width, height, MAX_SOURCE_PIXELS).ok_or(ABI_ERROR)?;
    let tn = count(tile.width, tile.height, MAX_TILE_PIXELS).ok_or(ABI_ERROR)?;
    if edited.len() != n * 3 || guide.len() != n * 3
        || coverage.map_or(false, |m| m.len() != n)
        || tile.x.checked_add(tile.width).map_or(true, |x| x > width)
        || tile.y.checked_add(tile.height).map_or(true, |y| y > height) { return Err(ABI_ERROR); }
    if !settings.valid() { return Err(SETTINGS_ERROR); }
    if cancel() { return Err(CANCELLED); }
    let frame = Frame { edited, guide, width, height };
    let mut output = Vec::new();
    output.try_reserve_exact(tn * 3).map_err(|_| ALLOCATION_ERROR)?;
    for row in 0..tile.height {
        if cancel() { return Err(CANCELLED); }
        for col in 0..tile.width {
            if col % 16 == 0 && cancel() { return Err(CANCELLED); }
            let x = tile.x + col;
            let y = tile.y + row;
            let i = y * width + x;
            let pixel = frame.pixel(edited, x, y)?;
            let amount = coverage.map_or(1.0, |m| m[i]);
            if !amount.is_finite() || !(0.0..=1.0).contains(&amount) { return Err(PIXEL_ERROR); }
            if settings.strength == 0.0 || amount == 0.0 {
                // Copy actual storage bits, including negative zero. No guide
                // read or reconstruction on explicitly neutral/bypassed pixels.
                output.extend_from_slice(&edited[3 * i..3 * i + 3]);
                continue;
            }
            let delta = correction(&frame, x as f64, y as f64, settings)?
                * settings.strength as f64 * amount as f64;
            if delta == 0.0 {
                output.extend_from_slice(&edited[3 * i..3 * i + 3]);
                continue;
            }
            for channel in pixel {
                let repaired = (channel - delta) as f32;
                if !repaired.is_finite() { return Err(RESULT_ERROR); }
                output.push(repaired);
            }
        }
    }
    if cancel() { return Err(CANCELLED); }
    Ok(output)
}

/// # Safety
/// Valid aligned immutable full-raster edited/guide/coverage spans and writable
/// disjoint bounded output are required. Lengths count floats. Pointers must
/// remain valid until return; detected numeric overlap is rejected. The callback
/// must not unwind, invalidate buffers, or mutate any input. Nonzero return is
/// transactional: all caller output bytes remain unchanged.
#[no_mangle]
pub unsafe extern "C" fn lrt_fringe_repair_tile(
    edited: *const f32, edited_length: usize,
    guide: *const f32, guide_length: usize, width: usize, height: usize,
    coverage: *const f32, coverage_length: usize,
    tile_x: usize, tile_y: usize, tile_width: usize, tile_height: usize,
    strength: f32, radius_source: f32, scale: f32, threshold: f32,
    output: *mut f32, output_length: usize,
    cancel: Option<extern "C" fn(*mut c_void) -> i32>, cancel_context: *mut c_void,
) -> i32 {
    let n = match count(width, height, MAX_SOURCE_PIXELS) { Some(n) => n, None => return ABI_ERROR };
    let tn = match count(tile_width, tile_height, MAX_TILE_PIXELS) { Some(n) => n, None => return ABI_ERROR };
    if edited_length != n * 3 || guide_length != n * 3 || output_length != tn * 3
        || tile_x.checked_add(tile_width).map_or(true, |x| x > width)
        || tile_y.checked_add(tile_height).map_or(true, |y| y > height) { return ABI_ERROR; }
    let (er, gr, out) = match (region(edited, edited_length), region(guide, guide_length),
        region(output as *const f32, output_length)) {
        (Some(e), Some(g), Some(o)) => (e, g, o), _ => return ABI_ERROR,
    };
    if overlaps(er, out) || overlaps(gr, out) { return ABI_ERROR; }
    let mask = if coverage.is_null() {
        if coverage_length != 0 { return ABI_ERROR; }
        None
    } else {
        if coverage_length != n { return ABI_ERROR; }
        let mr = match region(coverage, coverage_length) { Some(r) => r, None => return ABI_ERROR };
        if overlaps(mr, out) { return ABI_ERROR; }
        Some(slice::from_raw_parts(coverage, coverage_length))
    };
    let settings = Settings { strength, radius_source, scale, threshold };
    if !settings.valid() { return SETTINGS_ERROR; }
    let tile = Tile { x: tile_x, y: tile_y, width: tile_width, height: tile_height };
    let result = std::panic::catch_unwind(|| render_tile(
        slice::from_raw_parts(edited, edited_length), slice::from_raw_parts(guide, guide_length),
        width, height, mask, tile, settings, &|| cancel.map_or(false, |f| f(cancel_context) != 0),
    ));
    match result {
        Ok(Ok(data)) => {
            if cancel.map_or(false, |f| f(cancel_context) != 0) { return CANCELLED; }
            ptr::copy_nonoverlapping(data.as_ptr(), output, output_length);
            0
        }
        Ok(Err(code)) => code,
        Err(_) => PANIC_ERROR,
    }
}

#[cfg(test)]
mod tests;
