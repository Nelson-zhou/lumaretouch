// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Original bounded same-photo statistical reference match.
//! This is NOT an automatic brightest-face selector or a person/body segmenter.
//! Host-authenticated reference/target source support is a mandatory precondition.
//! Encoded working-sRGB-D65 SDR enters/exits; all correction is in linear RGB.
use std::{ffi::c_void, mem, panic, ptr, slice};

pub const ABI_VERSION: u32 = 1;
pub const TRANSFORM_LEN: usize = 4;
pub const DIAGNOSTICS_LEN: usize = 24;
pub const MAX_DIMENSION: usize = 65_536;
pub const MAX_FIT_PIXELS: usize = 32_000_000;
pub const MAX_APPLY_PIXELS: usize = 1_048_576;
pub const MAX_FIT_BYTES: usize = 2 * 1024 * 1024 * 1024;
pub const MAX_APPLY_BYTES: usize = 64 * 1024 * 1024;
pub const FIT_FIXED_SCRATCH_BYTES: usize = 256 * 1024;
pub const HISTOGRAM_BINS: usize = 2048;
pub const HISTOGRAM_LEVELS: usize = 2;
pub const FIT_SOURCE_PASSES: usize = 9;
pub const MAX_LOG_LUMINANCE: f64 = std::f64::consts::LN_2;
pub const MAX_LOG_CHROMA: f64 = 0.35;
pub const MIN_EFFECTIVE_SAMPLES: f64 = 64.0;
pub const MAX_LUMINANCE_MAD: f64 = 0.50;
pub const MAX_CHROMA_MAD: f64 = 0.30;
pub const NEUTRAL_TOLERANCE: f64 = 1e-7;
pub const POLL_PIXELS: usize = 256;
pub const ABI_ERROR: i32 = 1;
pub const SETTINGS_ERROR: i32 = 2;
pub const PIXEL_ERROR: i32 = 3;
pub const CANCELLED: i32 = 4;
pub const RESOURCE_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;
pub const REFERENCE_ERROR: i32 = 7;
pub const TARGET_ERROR: i32 = 8;
pub const DISPERSION_ERROR: i32 = 9;
pub const TRANSFORM_ERROR: i32 = 10;
pub type Cancel = Option<extern "C" fn(*mut c_void) -> i32>;

#[derive(Clone, Debug)]
pub struct Fit {
    transform: [f64; TRANSFORM_LEN],
    diagnostics: [f64; DIAGNOSTICS_LEN],
}
impl Fit {
    pub fn transform(&self) -> &[f64; TRANSFORM_LEN] { &self.transform }
    pub fn diagnostics(&self) -> &[f64; DIAGNOSTICS_LEN] { &self.diagnostics }
}
#[derive(Clone, Copy)]
struct Sample { value: [f64; 3], weight: f64 }
#[derive(Clone, Copy)]
struct Bin { weight: f64, low: f64, high: f64 }
impl Bin {
    fn empty() -> Self { Self { weight: 0.0, low: f64::INFINITY, high: f64::NEG_INFINITY } }
    fn add(&mut self, value: f64, weight: f64) {
        self.weight += weight; self.low = self.low.min(value); self.high = self.high.max(value);
    }
}
#[derive(Clone, Copy)]
struct RobustModel { centre: [f64; 3], scale: [f64; 3] }
struct Statistics {
    centre: [f64; 3], mad: [f64; 3], count: usize,
    weight: f64, effective: f64, retained: f64,
}

fn unit(x: f32) -> bool { x.is_finite() && (0.0..=1.0).contains(&x) }
fn poll<F: FnMut() -> bool>(cancel: &mut F) -> Result<(), i32> {
    if cancel() { Err(CANCELLED) } else { Ok(()) }
}
fn dimensions(width: usize, height: usize) -> Result<usize, i32> {
    if width == 0 || height == 0 || width > MAX_DIMENSION || height > MAX_DIMENSION {
        return Err(ABI_ERROR);
    }
    width.checked_mul(height).ok_or(RESOURCE_ERROR)
}
/// Includes caller RGB/coverage inputs and constant streaming histogram scratch.
pub fn fit_memory_bytes(rw: usize, rh: usize, tw: usize, th: usize) -> Result<usize, i32> {
    let r = dimensions(rw, rh)?;
    let t = dimensions(tw, th)?;
    let n = r.checked_add(t).ok_or(RESOURCE_ERROR)?;
    let bytes = n.checked_mul(16).and_then(|v| v.checked_add(FIT_FIXED_SCRATCH_BYTES))
        .ok_or(RESOURCE_ERROR)?;
    if n > MAX_FIT_PIXELS || bytes > MAX_FIT_BYTES { return Err(RESOURCE_ERROR); }
    Ok(bytes)
}
/// Includes caller current/coverage/output and native transactional RGB stage.
pub fn apply_memory_bytes(width: usize, height: usize) -> Result<usize, i32> {
    let n = dimensions(width, height)?;
    let bytes = n.checked_mul(40).and_then(|v| v.checked_add(4096)).ok_or(RESOURCE_ERROR)?;
    if n > MAX_APPLY_PIXELS || bytes > MAX_APPLY_BYTES { return Err(RESOURCE_ERROR); }
    Ok(bytes)
}
fn limits_valid(limits: [f64; 2]) -> bool {
    limits[0].is_finite() && limits[1].is_finite()
        && (0.0..=MAX_LOG_LUMINANCE).contains(&limits[0])
        && (0.0..=MAX_LOG_CHROMA).contains(&limits[1])
}
fn transform_valid(t: &[f64]) -> bool {
    t.len() == TRANSFORM_LEN && t.iter().all(|v| v.is_finite()) && t[0] == 1.0
        && t[1].abs() <= MAX_LOG_LUMINANCE + 1e-12
        && t[2].hypot(t[3]) <= MAX_LOG_CHROMA + 1e-12
}
fn validate_pixels<F: FnMut() -> bool>(rgb: &[f32], coverage: Option<&[f32]>,
    n: usize, cancel: &mut F) -> Result<(), i32> {
    if rgb.len() != 3*n || coverage.map_or(false, |v| v.len() != n) { return Err(ABI_ERROR); }
    for i in 0..n {
        if i % POLL_PIXELS == 0 { poll(cancel)?; }
        if !unit(rgb[3*i]) || !unit(rgb[3*i+1]) || !unit(rgb[3*i+2])
            || coverage.map_or(false, |v| !unit(v[i])) { return Err(PIXEL_ERROR); }
    }
    Ok(())
}
fn decode(v: f32) -> f64 {
    let v = f64::from(v);
    if v <= 0.04045 { v / 12.92 } else { ((v + 0.055) / 1.055).powf(2.4) }
}
fn encode(v: f64) -> f32 {
    if v <= 0.0031308 { (12.92*v) as f32 }
    else { (1.055*v.powf(1.0/2.4)-0.055) as f32 }
}
fn luminance(rgb: [f64; 3]) -> f64 { 0.2126*rgb[0] + 0.7152*rgb[1] + 0.0722*rgb[2] }
fn smooth(low: f64, high: f64, value: f64) -> f64 {
    let t = ((value-low)/(high-low)).clamp(0.0, 1.0);
    t*t*(3.0-2.0*t)
}
fn reliability(encoded: [f32; 3], linear: [f64; 3]) -> f64 {
    let y = luminance(linear);
    let low = linear[0].min(linear[1]).min(linear[2]);
    let peak = f64::from(encoded[0].max(encoded[1]).max(encoded[2]));
    smooth(0.01, 0.04, y) * (1.0-smooth(0.70, 0.90, y))
        * smooth(0.002, 0.008, low) * (1.0-smooth(0.95, 0.995, peak))
}
fn observation(rgb: &[f32], coverage: &[f32], i: usize) -> Option<Sample> {
    if coverage[i] == 0.0 { return None; }
    let encoded = [rgb[3*i], rgb[3*i+1], rgb[3*i+2]];
    let linear = encoded.map(decode);
    let weight = f64::from(coverage[i])*reliability(encoded, linear);
    if weight <= 0.0 { return None; }
    // The reliability gate proves positive channels. No epsilon pseudo-samples.
    Some(Sample { value: [luminance(linear).ln(), (linear[0]/linear[1]).ln(),
                         (linear[2]/linear[1]).ln()], weight })
}
fn robust_weight(sample: Sample, model: Option<RobustModel>) -> f64 {
    let Some(model) = model else { return sample.weight; };
    let mut weight = sample.weight;
    for axis in 0..3 {
        let r = (sample.value[axis]-model.centre[axis]).abs()/(4.685*model.scale[axis]);
        weight *= if r < 1.0 { (1.0-r*r).powi(2) } else { 0.0 };
    }
    weight
}
/// Full-population approximate weighted medians, all axes in the same scan.
/// Actual per-bin extrema shrink intervals without inventing missing samples.
/// Two levels bound median error by half the final measured interval width;
/// the conservative initial-span/(2*2048^2) bound excludes f64 rounding error.
fn median3<F: FnMut() -> bool>(rgb: &[f32], coverage: &[f32], total: f64,
    mut low: [f64; 3], mut high: [f64; 3], deviation: Option<[f64; 3]>,
    model: Option<RobustModel>, cancel: &mut F) -> Result<[f64; 3], i32> {
    let count = 3*HISTOGRAM_BINS;
    let mut histogram = Vec::new();
    histogram.try_reserve_exact(count).map_err(|_| RESOURCE_ERROR)?;
    for i in 0..count {
        if i % POLL_PIXELS == 0 { poll(cancel)?; }
        histogram.push(Bin::empty());
    }
    let mut rank = [0.5*total; 3];
    for _ in 0..HISTOGRAM_LEVELS {
        for (i, bin) in histogram.iter_mut().enumerate() {
            if i % POLL_PIXELS == 0 { poll(cancel)?; }
            *bin = Bin::empty();
        }
        for i in 0..coverage.len() {
            if i % POLL_PIXELS == 0 { poll(cancel)?; }
            if let Some(sample) = observation(rgb, coverage, i) {
                let weight = robust_weight(sample, model);
                if weight == 0.0 { continue; }
                for axis in 0..3 {
                    let value = deviation.map_or(sample.value[axis], |m| (sample.value[axis]-m[axis]).abs());
                    if value < low[axis] || value > high[axis] { continue; }
                    let bin = if high[axis] == low[axis] { 0 } else {
                        (((value-low[axis])/(high[axis]-low[axis])*HISTOGRAM_BINS as f64) as usize)
                            .min(HISTOGRAM_BINS-1)
                    };
                    histogram[axis*HISTOGRAM_BINS+bin].add(value, weight);
                }
            }
        }
        for axis in 0..3 {
            let mut cumulative = 0.0;
            let mut chosen = None;
            for index in 0..HISTOGRAM_BINS {
                if index % POLL_PIXELS == 0 { poll(cancel)?; }
                let bin = histogram[axis*HISTOGRAM_BINS+index];
                if bin.weight == 0.0 { continue; }
                // Retain a last-bin fallback for roundoff in weighted sums.
                chosen = Some((bin, cumulative));
                if cumulative+bin.weight >= rank[axis] { break; }
                cumulative += bin.weight;
            }
            let (bin, below) = chosen.ok_or(PIXEL_ERROR)?;
            low[axis] = bin.low; high[axis] = bin.high;
            rank[axis] = (rank[axis]-below).max(0.0);
        }
    }
    Ok([low[0]+0.5*(high[0]-low[0]), low[1]+0.5*(high[1]-low[1]),
        low[2]+0.5*(high[2]-low[2])])
}
fn require_evidence(count: usize, weight: f64, squared: f64, error: i32) -> Result<f64, i32> {
    let effective = if squared > 0.0 { weight*weight/squared } else { 0.0 };
    if count < MIN_EFFECTIVE_SAMPLES as usize || weight < MIN_EFFECTIVE_SAMPLES
        || effective < MIN_EFFECTIVE_SAMPLES { Err(error) } else { Ok(effective) }
}
fn statistics<F: FnMut() -> bool>(rgb: &[f32], coverage: &[f32], error: i32,
    cancel: &mut F) -> Result<Statistics, i32> {
    let (mut count, mut weight, mut squared) = (0usize, 0.0, 0.0);
    let (mut low, mut high) = ([f64::INFINITY; 3], [f64::NEG_INFINITY; 3]);
    for i in 0..coverage.len() {
        if i % POLL_PIXELS == 0 { poll(cancel)?; }
        if let Some(s) = observation(rgb, coverage, i) {
            count += 1; weight += s.weight; squared += s.weight*s.weight;
            for axis in 0..3 { low[axis] = low[axis].min(s.value[axis]); high[axis] = high[axis].max(s.value[axis]); }
        }
    }
    require_evidence(count, weight, squared, error)?;
    let mut centre = median3(rgb, coverage, weight, low, high, None, None, cancel)?;
    let mut deviation_high = [0.0; 3];
    for axis in 0..3 { deviation_high[axis] = (low[axis]-centre[axis]).abs().max((high[axis]-centre[axis]).abs()); }
    let mad = median3(rgb, coverage, weight, [0.0; 3], deviation_high, Some(centre), None, cancel)?;
    if mad[0] > MAX_LUMINANCE_MAD || mad[1].hypot(mad[2]) > MAX_CHROMA_MAD {
        return Err(DISPERSION_ERROR);
    }
    // One bounded joint redescending reweight, then three final weighted medians.
    // Floors stabilize truly uniform support; no variance/contrast transfer.
    let model = RobustModel { centre, scale: [(1.4826*mad[0]).max(0.04),
        (1.4826*mad[1]).max(0.025), (1.4826*mad[2]).max(0.025)] };
    let initial_weight = weight;
    weight = 0.0; squared = 0.0; count = 0;
    for i in 0..coverage.len() {
        if i % POLL_PIXELS == 0 { poll(cancel)?; }
        if let Some(sample) = observation(rgb, coverage, i) {
            let w = robust_weight(sample, Some(model));
            if w > 0.0 { count += 1; }
            weight += w; squared += w*w;
        }
    }
    let effective = require_evidence(count, weight, squared, error)?;
    let retained = weight/initial_weight;
    if retained < 0.5 { return Err(DISPERSION_ERROR); }
    centre = median3(rgb, coverage, weight, low, high, None, Some(model), cancel)?;
    Ok(Statistics { centre, mad, count, weight, effective, retained })
}

/// Fit once against independent immutable real source windows. No geometry or
/// correspondence is assumed. A target is one reviewed face OR body region;
/// mixed owner/face/body pooling is not an ownership resolver.
pub fn fit_reference<F: FnMut() -> bool>(reference: &[f32], reference_coverage: &[f32],
    rw: usize, rh: usize, target: &[f32], target_coverage: &[f32], tw: usize, th: usize,
    limits: [f64; 2], mut cancel: F) -> Result<Fit, i32> {
    fit_memory_bytes(rw, rh, tw, th)?;
    if !limits_valid(limits) { return Err(SETTINGS_ERROR); }
    validate_pixels(reference, Some(reference_coverage), rw*rh, &mut cancel)?;
    validate_pixels(target, Some(target_coverage), tw*th, &mut cancel)?;
    // No stored pixel samples. Each ROI is scanned at native source resolution,
    // and each completed histogram drops before the next is allocated.
    let r = statistics(reference, reference_coverage, REFERENCE_ERROR, &mut cancel)?;
    let t = statistics(target, target_coverage, TARGET_ERROR, &mut cancel)?;
    let raw = [r.centre[0]-t.centre[0], r.centre[1]-t.centre[1], r.centre[2]-t.centre[2]];
    let mut shift = raw;
    let mut flags = 0u32;
    if shift[0].abs() > limits[0] { shift[0] = shift[0].clamp(-limits[0], limits[0]); flags |= 1; }
    let norm = shift[1].hypot(shift[2]);
    if norm > limits[1] {
        let scale = limits[1]/norm;
        shift[1] *= scale; shift[2] *= scale; flags |= 2;
    }
    for value in &mut shift {
        if value.abs() <= NEUTRAL_TOLERANCE {
            if *value != 0.0 { flags |= 4; }
            *value = 0.0;
        }
    }
    let transform = [1.0, shift[0], shift[1], shift[2]];
    if !transform_valid(&transform) { return Err(PIXEL_ERROR); }
    let mut diagnostics = [0.0; DIAGNOSTICS_LEN];
    diagnostics[..7].copy_from_slice(&[1.0, r.count as f64, t.count as f64,
        r.weight, t.weight, r.effective, t.effective]);
    diagnostics[7..10].copy_from_slice(&r.centre);
    diagnostics[10..13].copy_from_slice(&t.centre);
    diagnostics[13..16].copy_from_slice(&r.mad);
    diagnostics[16..19].copy_from_slice(&t.mad);
    diagnostics[19..22].copy_from_slice(&raw);
    diagnostics[22] = f64::from(flags);
    diagnostics[23] = r.retained.min(t.retained);
    poll(&mut cancel)?;
    Ok(Fit { transform, diagnostics })
}

fn corrected(encoded: [f32; 3], transform: &[f64], strength: f64) -> Result<[f32; 3], i32> {
    if strength == 0.0 || transform[1..].iter().all(|&v| v == 0.0) { return Ok(encoded); }
    let current = encoded.map(decode);
    let strength = strength*reliability(encoded, current);
    if strength == 0.0 { return Ok(encoded); }
    let y = luminance(current);
    let colored = [current[0]*(strength*transform[2]).exp(), current[1],
                   current[2]*(strength*transform[3]).exp()];
    let gain = y*(strength*transform[1]).exp()/luminance(colored);
    let desired = colored.map(|v| v*gain);
    let delta = [desired[0]-current[0], desired[1]-current[1], desired[2]-current[2]];
    if desired.iter().any(|v| !v.is_finite()) { return Err(PIXEL_ERROR); }
    let mut alpha = 1.0_f64;
    for c in 0..3 {
        if delta[c] > 0.0 { alpha = alpha.min((1.0-current[c])/delta[c]); }
        else if delta[c] < 0.0 { alpha = alpha.min(-current[c]/delta[c]); }
    }
    if !alpha.is_finite() || alpha < 0.0 { return Err(PIXEL_ERROR); }
    if alpha == 0.0 { return Ok(encoded); }
    // A shared inward margin only for constrained corrections avoids numerical
    // excursions at a gamut face. Never clip three channels independently.
    if alpha < 1.0 { alpha *= 1.0-16.0*f64::EPSILON; }
    let mut out = [0.0; 3];
    for c in 0..3 {
        let linear = current[c] + alpha*delta[c];
        if !linear.is_finite() || !(0.0..=1.0).contains(&linear) { return Err(PIXEL_ERROR); }
        out[c] = encode(linear);
        if !unit(out[c]) { return Err(PIXEL_ERROR); }
    }
    Ok(out)
}

/// Apply one immutable fit to CURRENT full-resolution pixels, with no halo and
/// no source replay. At amount zero absent support/transform is legitimate.
/// Output is untouched on all errors and cancellation; final copy cannot cancel.
pub fn apply_into<F: FnMut() -> bool>(current: &[f32], coverage: Option<&[f32]>,
    width: usize, height: usize, transform: Option<&[f64]>, amount: f32,
    output: &mut [f32], mut cancel: F) -> Result<(), i32> {
    apply_memory_bytes(width, height)?;
    let n = width*height;
    if output.len() != 3*n { return Err(ABI_ERROR); }
    if !unit(amount) { return Err(SETTINGS_ERROR); }
    if transform.map_or(false, |v| !transform_valid(v)) { return Err(TRANSFORM_ERROR); }
    if amount != 0.0 && (coverage.is_none() || transform.is_none()) { return Err(ABI_ERROR); }
    validate_pixels(current, coverage, n, &mut cancel)?;
    poll(&mut cancel)?;
    if amount == 0.0 {
        output.copy_from_slice(current);
        return Ok(());
    }
    let support = coverage.ok_or(ABI_ERROR)?;
    let transform = transform.ok_or(ABI_ERROR)?;
    let mut stage = Vec::new();
    stage.try_reserve_exact(3*n).map_err(|_| RESOURCE_ERROR)?;
    for i in 0..n {
        if i % POLL_PIXELS == 0 { poll(&mut cancel)?; }
        let pixel = [current[3*i], current[3*i+1], current[3*i+2]];
        let result = corrected(pixel, transform, f64::from(amount)*f64::from(support[i]))?;
        stage.extend_from_slice(&result);
    }
    poll(&mut cancel)?;
    output.copy_from_slice(&stage);
    Ok(())
}

fn region<T>(pointer: *const T, len: usize) -> Result<(usize, usize), i32> {
    if pointer.is_null() || len == 0 || (pointer as usize) % mem::align_of::<T>() != 0 {
        return Err(ABI_ERROR);
    }
    let bytes = len.checked_mul(mem::size_of::<T>()).ok_or(ABI_ERROR)?;
    if bytes > isize::MAX as usize { return Err(ABI_ERROR); }
    let begin = pointer as usize;
    Ok((begin, begin.checked_add(bytes).ok_or(ABI_ERROR)?))
}
fn overlaps(a: (usize, usize), b: (usize, usize)) -> bool { a.0 < b.1 && b.0 < a.1 }
fn ffi_result<F: FnOnce() -> Result<(), i32> + panic::UnwindSafe>(f: F) -> i32 {
    match panic::catch_unwind(f) { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}
#[no_mangle]
pub extern "C" fn lrt_skin_reference_match_abi() -> u32 { ABI_VERSION }

/// # Safety
/// Pointers must name live, appropriately aligned allocations of stated lengths.
/// Inputs remain immutable, outputs are exclusive, and callbacks do not unwind,
/// reenter, or change/free any buffer. Range validation cannot prove allocation.
#[no_mangle]
pub unsafe extern "C" fn lrt_skin_reference_match_fit_v1(
    reference: *const f32, reference_len: usize, reference_coverage: *const f32,
    reference_coverage_len: usize, rw: usize, rh: usize,
    target: *const f32, target_len: usize, target_coverage: *const f32,
    target_coverage_len: usize, tw: usize, th: usize,
    limits: *const f64, limits_len: usize,
    transform_out: *mut f64, transform_len: usize,
    diagnostics_out: *mut f64, diagnostics_len: usize, cancel: Cancel, context: *mut c_void,
) -> i32 {
    ffi_result(|| {
        fit_memory_bytes(rw, rh, tw, th)?;
        if reference_len != 3*rw*rh || reference_coverage_len != rw*rh
            || target_len != 3*tw*th || target_coverage_len != tw*th
            || limits_len != 2 || transform_len != TRANSFORM_LEN || diagnostics_len != DIAGNOSTICS_LEN {
            return Err(ABI_ERROR);
        }
        let inputs = [region(reference, reference_len)?, region(reference_coverage, reference_coverage_len)?,
            region(target, target_len)?, region(target_coverage, target_coverage_len)?, region(limits, limits_len)?];
        let a = region(transform_out, transform_len)?;
        let b = region(diagnostics_out, diagnostics_len)?;
        if overlaps(a, b) || inputs.iter().any(|&input| overlaps(input, a) || overlaps(input, b)) {
            return Err(ABI_ERROR);
        }
        let fit = fit_reference(slice::from_raw_parts(reference, reference_len),
            slice::from_raw_parts(reference_coverage, reference_coverage_len), rw, rh,
            slice::from_raw_parts(target, target_len), slice::from_raw_parts(target_coverage, target_coverage_len),
            tw, th, [*limits, *limits.add(1)], || cancel.map_or(false, |callback| callback(context) != 0))?;
        // Final publication has no callbacks/fallible steps between these copies.
        // This is error atomicity, not concurrent-reader synchronization.
        ptr::copy_nonoverlapping(fit.transform.as_ptr(), transform_out, TRANSFORM_LEN);
        ptr::copy_nonoverlapping(fit.diagnostics.as_ptr(), diagnostics_out, DIAGNOSTICS_LEN);
        Ok(())
    })
}

/// # Safety
/// Same allocation/lifetime/callback contract as fit. Output cannot overlap any
/// supplied input. At neutral only, missing coverage/transform uses (NULL, 0).
#[no_mangle]
pub unsafe extern "C" fn lrt_skin_reference_match_apply_v1(
    current: *const f32, current_len: usize, coverage: *const f32, coverage_len: usize,
    width: usize, height: usize, transform: *const f64, transform_len: usize, amount: f32,
    output: *mut f32, output_len: usize, cancel: Cancel, context: *mut c_void,
) -> i32 {
    ffi_result(|| {
        apply_memory_bytes(width, height)?;
        let n = width*height;
        if current_len != 3*n || output_len != 3*n { return Err(ABI_ERROR); }
        if !unit(amount) { return Err(SETTINGS_ERROR); }
        let source_region = region(current, current_len)?;
        let output_region = region(output, output_len)?;
        if overlaps(source_region, output_region) { return Err(ABI_ERROR); }
        let support = if coverage.is_null() && coverage_len == 0 && amount == 0.0 { None }
        else {
            if coverage_len != n { return Err(ABI_ERROR); }
            if overlaps(region(coverage, coverage_len)?, output_region) { return Err(ABI_ERROR); }
            Some(slice::from_raw_parts(coverage, coverage_len))
        };
        let transform = if transform.is_null() && transform_len == 0 && amount == 0.0 { None }
        else {
            if transform_len != TRANSFORM_LEN { return Err(ABI_ERROR); }
            if overlaps(region(transform, transform_len)?, output_region) { return Err(ABI_ERROR); }
            Some(slice::from_raw_parts(transform, transform_len))
        };
        apply_into(slice::from_raw_parts(current, current_len), support, width, height,
            transform, amount, slice::from_raw_parts_mut(output, output_len),
            || cancel.map_or(false, |callback| callback(context) != 0))
    })
}

#[cfg(test)]
mod tests;
