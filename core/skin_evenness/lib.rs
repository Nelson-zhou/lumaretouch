// SPDX-License-Identifier: GPL-3.0-or-later
//! Original same-face source-owned chromatic evenness. AUTHORED / UNRUN.
//! Preparation measures immutable source; application preserves actual CURRENT
//! linear luminance. No detector, learned target, intrinsic decomposition or blur
//! of the current photograph. No external implementation is incorporated.
use std::{ffi::c_void, mem, panic, slice};

pub const MAX_PIXELS: usize = 32_000_000;
pub const MAX_DIMENSION: usize = 65_536;
pub const MIN_RADIUS: usize = 4;
pub const MAX_RADIUS: usize = 256;
pub const MIN_REFERENCE_SAMPLES: usize = 64;
pub const NATIVE_PREPARE_SCRATCH_BYTES_PER_PIXEL: usize = 88;
pub const NATIVE_PREPARE_TOTAL_BYTES_PER_PIXEL: usize = 112;
pub const NATIVE_APPLY_TOTAL_BYTES_PER_PIXEL: usize = 44;
pub const MAX_WORKING_BYTES: usize = 4 * 1024 * 1024 * 1024;
pub const POLL_PIXELS: usize = 256;
pub const CHROMA_LIMIT: f64 = 0.20;
pub const CORRECTION_GAIN: f64 = 0.45;
pub const MAX_SHIFT: f64 = 0.09;
pub const SHIFT_TOLERANCE: f64 = 1e-7;
pub const GUIDANCE_EPSILON: f64 = 0.03 * 0.03;
pub const ABI_ERROR: i32 = 1;
pub const SETTINGS_ERROR: i32 = 2;
pub const PIXEL_ERROR: i32 = 3;
pub const CANCELLED: i32 = 4;
pub const RESOURCE_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;
pub const REFERENCE_ERROR: i32 = 7;
pub const CONTEXT_ERROR: i32 = 8;
pub type Cancel = Option<extern "C" fn(*mut c_void) -> i32>;

fn unit(v: f32) -> bool { v.is_finite() && (0.0..=1.0).contains(&v) }
fn poll<F: FnMut() -> bool>(cancelled: &mut F) -> Result<(), i32> {
    if cancelled() { Err(CANCELLED) } else { Ok(()) }
}
fn admit(width: usize, height: usize, bytes_per_pixel: usize) -> Result<usize, i32> {
    if width == 0 || height == 0 || width > MAX_DIMENSION || height > MAX_DIMENSION {
        return Err(ABI_ERROR);
    }
    let n = width.checked_mul(height).ok_or(RESOURCE_ERROR)?;
    let bytes = n.checked_mul(bytes_per_pixel).ok_or(RESOURCE_ERROR)?;
    if n > MAX_PIXELS || bytes > MAX_WORKING_BYTES { return Err(RESOURCE_ERROR); }
    Ok(n)
}
fn decode(v: f64) -> f64 {
    if v <= 0.04045 { v / 12.92 } else { ((v + 0.055) / 1.055).powf(2.4) }
}
fn encode(v: f64) -> f32 {
    if v <= 0.0031308 { (12.92 * v) as f32 }
    else { (1.055 * v.powf(1.0 / 2.4) - 0.055) as f32 }
}
fn linear(pixel: [f32; 3]) -> [f64; 3] { pixel.map(|v| decode(f64::from(v))) }
fn y(rgb: [f64; 3]) -> f64 { 0.2126*rgb[0] + 0.7152*rgb[1] + 0.0722*rgb[2] }
fn smooth(lo: f64, hi: f64, value: f64) -> f64 {
    // Bounding an evidence gate is not clipping image channels.
    let t = ((value - lo) / (hi - lo)).clamp(0.0, 1.0);
    t*t*(3.0 - 2.0*t)
}
fn source_sample(source: &[f32], coverage: &[f32], i: usize) -> [f64; 4] {
    if coverage[i] == 0.0 { return [0.0; 4]; }
    let encoded = [source[3*i], source[3*i+1], source[3*i+2]];
    let rgb = linear(encoded);
    let guide = y(rgb);
    let minimum = rgb.into_iter().fold(f64::INFINITY, f64::min);
    let peak = encoded.into_iter().fold(0.0_f32, f32::max);
    let reliability = smooth(0.01, 0.04, guide) * (1.0-smooth(0.70, 0.90, guide))
        * smooth(0.002, 0.008, minimum) * (1.0-smooth(0.95, 0.995, f64::from(peak)));
    let weight = f64::from(coverage[i]) * reliability;
    if weight == 0.0 { return [0.0; 4]; }
    // No epsilon pseudo-observation: strictly positive reliable actual channels.
    [guide, (rgb[0]/rgb[1]).ln(), (rgb[2]/rgb[1]).ln(), weight]
}
fn filled<T: Clone, F: FnMut() -> bool>(count: usize, value: T, cancelled: &mut F)
    -> Result<Vec<T>, i32> {
    poll(cancelled)?;
    let mut result = Vec::new();
    result.try_reserve_exact(count).map_err(|_| RESOURCE_ERROR)?;
    for i in 0..count {
        if i % POLL_PIXELS == 0 { poll(cancelled)?; }
        result.push(value.clone());
    }
    Ok(result)
}
fn insertion<F: FnMut() -> bool>(values: &mut [f64], cancelled: &mut F) -> Result<(), i32> {
    poll(cancelled)?;
    for i in 1..values.len() {
        let mut j = i;
        while j > 0 && values[j] < values[j-1] { values.swap(j, j-1); j -= 1; }
    }
    Ok(())
}
/// Exact deterministic median-of-medians selection; no quantized histogram,
/// random pivot, uninterruptible sort or external implementation. Groups of five
/// bound recursive pivot work and worst-case total work linearly in sample count.
fn select<F: FnMut() -> bool>(mut values: &mut [f64], mut rank: usize, cancelled: &mut F)
    -> Result<f64, i32> {
    loop {
        poll(cancelled)?;
        if values.len() <= 32 {
            insertion(values, cancelled)?;
            return Ok(values[rank]);
        }
        let mut groups = 0;
        for start in (0..values.len()).step_by(5) {
            if groups % POLL_PIXELS == 0 { poll(cancelled)?; }
            let end = (start+5).min(values.len());
            insertion(&mut values[start..end], cancelled)?;
            values.swap(groups, start+(end-start)/2);
            groups += 1;
        }
        let pivot = select(&mut values[..groups], groups/2, cancelled)?;
        let (mut low, mut scan, mut high) = (0, 0, values.len());
        let mut visits = 0;
        while scan < high {
            if visits % POLL_PIXELS == 0 { poll(cancelled)?; }
            visits += 1;
            if values[scan] < pivot { values.swap(scan, low); low += 1; scan += 1; }
            else if values[scan] > pivot { high -= 1; values.swap(scan, high); }
            else { scan += 1; }
        }
        if rank < low { values = &mut values[..low]; }
        else if rank >= high { rank -= high; values = &mut values[high..]; }
        else { return Ok(pivot); }
    }
}
fn median<F: FnMut() -> bool>(values: &mut [f64], cancelled: &mut F) -> Result<f64, i32> {
    let middle = values.len()/2;
    let upper = select(values, middle, cancelled)?;
    if values.len() % 2 != 0 { return Ok(upper); }
    let mut lower = f64::NEG_INFINITY;
    for (i, &v) in values[..middle].iter().enumerate() {
        if i % POLL_PIXELS == 0 { poll(cancelled)?; }
        lower = lower.max(v);
    }
    Ok(0.5*(lower+upper))
}
fn reference<F: FnMut() -> bool>(source: &[f32], coverage: &[f32], cancelled: &mut F)
    -> Result<[f64; 2], i32> {
    let mut count = 0;
    for i in 0..coverage.len() {
        if i % POLL_PIXELS == 0 { poll(cancelled)?; }
        if source_sample(source, coverage, i)[3] >= 0.75 { count += 1; }
    }
    if count < MIN_REFERENCE_SAMPLES { return Err(REFERENCE_ERROR); }
    let mut values = filled(count, 0.0_f64, cancelled)?;
    let mut answer = [0.0; 2];
    for component in 0..2 {
        let mut at = 0;
        for i in 0..coverage.len() {
            if i % POLL_PIXELS == 0 { poll(cancelled)?; }
            let sample = source_sample(source, coverage, i);
            if sample[3] >= 0.75 { values[at] = sample[component+1]; at += 1; }
        }
        answer[component] = median(&mut values, cancelled)?;
    }
    Ok(answer)
}
/// Truncated real-domain box sums. No fabricated border or unsupported samples.
fn horizontal<const K: usize, F: FnMut() -> bool, S: Fn(usize) -> [f64; K]>(
    width: usize, height: usize, radius: usize, sample_at: S, cancelled: &mut F,
) -> Result<Vec<[f64; K]>, i32> {
    let mut rows = filled(width*height, [0.0; K], cancelled)?;
    for yy in 0..height {
        poll(cancelled)?;
        let mut sum = [0.0; K];
        for xx in 0..=radius.min(width-1) {
            if xx % POLL_PIXELS == 0 { poll(cancelled)?; }
            let value = sample_at(yy*width+xx);
            for c in 0..K { sum[c] += value[c]; }
        }
        for xx in 0..width {
            if xx % POLL_PIXELS == 0 { poll(cancelled)?; }
            rows[yy*width+xx] = sum;
            if xx >= radius {
                let value = sample_at(yy*width+xx-radius);
                for c in 0..K { sum[c] -= value[c]; }
            }
            if xx+radius+1 < width {
                let value = sample_at(yy*width+xx+radius+1);
                for c in 0..K { sum[c] += value[c]; }
            }
        }
    }
    Ok(rows)
}
fn vertical<const K: usize, F: FnMut() -> bool, V: FnMut(usize, [f64; K]) -> Result<(), i32>>(
    rows: &[[f64; K]], width: usize, height: usize, radius: usize,
    mut visit: V, cancelled: &mut F,
) -> Result<(), i32> {
    for xx in 0..width {
        poll(cancelled)?;
        let mut sum = [0.0; K];
        for yy in 0..=radius.min(height-1) {
            if yy % POLL_PIXELS == 0 { poll(cancelled)?; }
            for c in 0..K { sum[c] += rows[yy*width+xx][c]; }
        }
        for yy in 0..height {
            if yy % POLL_PIXELS == 0 { poll(cancelled)?; }
            visit(yy*width+xx, sum)?;
            if yy >= radius {
                for c in 0..K { sum[c] -= rows[(yy-radius)*width+xx][c]; }
            }
            if yy+radius+1 < height {
                for c in 0..K { sum[c] += rows[(yy+radius+1)*width+xx][c]; }
            }
        }
    }
    Ok(())
}
fn area(i: usize, width: usize, height: usize, radius: usize) -> f64 {
    let x = i%width;
    let yy = i/width;
    ((x+radius).min(width-1)-x.saturating_sub(radius)+1) as f64
        * ((yy+radius).min(height-1)-yy.saturating_sub(radius)+1) as f64
}
fn shift_valid(u: f32, v: f32) -> bool {
    u.is_finite() && v.is_finite()
        && f64::from(u).hypot(f64::from(v)) <= MAX_SHIFT+SHIFT_TOLERANCE
}

/// Produces an owned, original-source log-chroma displacement field. No writes
/// to caller output occur before success. Active insufficient reference refuses.
pub fn prepare_into<F: FnMut() -> bool>(source: &[f32], coverage: &[f32],
    width: usize, height: usize, amount: f32, radius: usize,
    output: &mut [f32], mut cancelled: F) -> Result<(), i32> {
    let n = admit(width, height, NATIVE_PREPARE_TOTAL_BYTES_PER_PIXEL)?;
    if source.len() != n*3 || coverage.len() != n || output.len() != n*2 { return Err(ABI_ERROR); }
    if !unit(amount) || !(MIN_RADIUS..=MAX_RADIUS).contains(&radius) { return Err(SETTINGS_ERROR); }
    for i in 0..n {
        if i % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
        if !unit(coverage[i]) || !source[3*i..3*i+3].iter().copied().all(unit) { return Err(PIXEL_ERROR); }
    }
    if amount == 0.0 {
        poll(&mut cancelled)?;
        output.fill(0.0);
        return Ok(());
    }
    let target = reference(source, coverage, &mut cancelled)?;
    // Store local mass/mean/variance first, then overwrite in-place with two
    // weighted slope/intercept pairs and valid coefficient-domain weight.
    let mut coefficients = filled(n, [0.0_f64; 5], &mut cancelled)?;
    let rows = horizontal(width, height, radius, |i| {
        let s = source_sample(source, coverage, i);
        let w = s[3];
        [w, w*w, w*s[0], w*s[0]*s[0], if w > 0.0 { 1.0 } else { 0.0 }]
    }, &mut cancelled)?;
    vertical(&rows, width, height, radius, |i, sum| {
        if source_sample(source, coverage, i)[3] == 0.0 || sum[0] < 4.0 || sum[1] <= 0.0
            || sum[4] < 8.0 || sum[0]*sum[0]/sum[1] < 8.0
            || sum[0]/area(i, width, height, radius) < 0.15 { return Ok(()); }
        let mean = sum[2]/sum[0];
        let variance = (sum[3]/sum[0]-mean*mean).max(0.0);
        coefficients[i] = [sum[0], mean, variance, 1.0, 0.0];
        Ok(())
    }, &mut cancelled)?;
    drop(rows);
    let rows = horizontal(width, height, radius, |i| {
        let s = source_sample(source, coverage, i);
        [s[3]*s[1], s[3]*s[2], s[3]*s[0]*s[1], s[3]*s[0]*s[2]]
    }, &mut cancelled)?;
    vertical(&rows, width, height, radius, |i, sum| {
        let statistics = coefficients[i];
        if statistics[3] == 0.0 { return Ok(()); }
        let s = source_sample(source, coverage, i);
        let mass = statistics[0];
        let mean_i = statistics[1];
        let mean_u = sum[0]/mass;
        let mean_v = sum[1]/mass;
        let a_u = (sum[2]/mass-mean_i*mean_u)/(statistics[2]+GUIDANCE_EPSILON);
        let a_v = (sum[3]/mass-mean_i*mean_v)/(statistics[2]+GUIDANCE_EPSILON);
        coefficients[i] = [s[3]*a_u, s[3]*(mean_u-a_u*mean_i),
                           s[3]*a_v, s[3]*(mean_v-a_v*mean_i), s[3]];
        if !coefficients[i].iter().all(|v| v.is_finite()) { return Err(PIXEL_ERROR); }
        Ok(())
    }, &mut cancelled)?;
    drop(rows);
    let rows = horizontal(width, height, radius, |i| coefficients[i], &mut cancelled)?;
    let mut result = filled(n*2, 0.0_f32, &mut cancelled)?;
    let mut valid_context = 0_usize;
    vertical(&rows, width, height, radius, |i, sum| {
        if coefficients[i][4] == 0.0 || sum[4] < 4.0
            || sum[4]/area(i, width, height, radius) < 0.15 { return Ok(()); }
        valid_context += 1;
        let s = source_sample(source, coverage, i);
        let du = target[0]-(sum[0]*s[0]+sum[1])/sum[4];
        let dv = target[1]-(sum[2]*s[0]+sum[3])/sum[4];
        let norm = du.hypot(dv);
        if !norm.is_finite() { return Err(PIXEL_ERROR); }
        // Deadzone suppresses float32 decode/moment roundoff on constant chroma.
        if norm <= 1e-6 { return Ok(()); }
        let scale = f64::from(amount)*s[3]*CORRECTION_GAIN
            * CHROMA_LIMIT*(norm/CHROMA_LIMIT).tanh()/norm;
        let u = (du*scale) as f32;
        let v = (dv*scale) as f32;
        if !shift_valid(u, v) { return Err(PIXEL_ERROR); }
        result[2*i] = u;
        result[2*i+1] = v;
        Ok(())
    }, &mut cancelled)?;
    if valid_context == 0 { return Err(CONTEXT_ERROR); }
    poll(&mut cancelled)?;
    // Final publication is one non-cancellable copy after all fallible work.
    output.copy_from_slice(&result);
    Ok(())
}
fn corrected(current: [f32; 3], shift: [f32; 2]) -> Result<[f32; 3], i32> {
    if shift == [0.0; 2] || current.iter().all(|&v| v == 0.0)
        || current.iter().all(|&v| v == 1.0) { return Ok(current); }
    let rgb = linear(current);
    let luminance = y(rgb);
    // Multiplicative ratios avoid log(0) or synthetic channels at application.
    let proposal = [rgb[0]*f64::from(shift[0]).exp(), rgb[1], rgb[2]*f64::from(shift[1]).exp()];
    let denominator = y(proposal);
    if !denominator.is_finite() || denominator <= 0.0 { return Err(PIXEL_ERROR); }
    let proposal = proposal.map(|v| v*luminance/denominator);
    let mut t = 1.0_f64;
    for c in 0..3 {
        let delta = proposal[c]-rgb[c];
        if delta > 0.0 { t = t.min((1.0-rgb[c])/delta); }
        else if delta < 0.0 { t = t.min(-rgb[c]/delta); }
    }
    if !t.is_finite() || t < 0.0 { return Err(PIXEL_ERROR); }
    if t == 0.0 { return Ok(current); }
    if t < 1.0 { t *= 1.0-1e-12; }
    let target = [0, 1, 2].map(|c| rgb[c]+t*(proposal[c]-rgb[c]));
    if !target.iter().all(|v| v.is_finite() && (0.0..=1.0).contains(v)) { return Err(PIXEL_ERROR); }
    let encoded = target.map(encode);
    if !encoded.iter().copied().all(unit) { return Err(PIXEL_ERROR); }
    Ok(encoded)
}
/// Pointwise current-stage application, no source statistics or previous result
/// feedback. On any error/cancellation caller output remains unchanged.
pub fn apply_into<F: FnMut() -> bool>(current: &[f32], shift: &[f32],
    width: usize, height: usize, output: &mut [f32], mut cancelled: F) -> Result<(), i32> {
    let n = admit(width, height, NATIVE_APPLY_TOTAL_BYTES_PER_PIXEL)?;
    if current.len() != n*3 || shift.len() != n*2 || output.len() != n*3 { return Err(ABI_ERROR); }
    for i in 0..n {
        if i % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
        if !current[3*i..3*i+3].iter().copied().all(unit)
            || !shift_valid(shift[2*i], shift[2*i+1]) { return Err(PIXEL_ERROR); }
    }
    let mut result = filled(n*3, 0.0_f32, &mut cancelled)?;
    for i in 0..n {
        if i % POLL_PIXELS == 0 { poll(&mut cancelled)?; }
        let pixel = corrected([current[3*i], current[3*i+1], current[3*i+2]], [shift[2*i], shift[2*i+1]])?;
        result[3*i..3*i+3].copy_from_slice(&pixel);
    }
    poll(&mut cancelled)?;
    output.copy_from_slice(&result);
    Ok(())
}
fn span(pointer: *const f32, length: usize) -> Result<(usize, usize), i32> {
    let start = pointer as usize;
    let bytes = length.checked_mul(mem::size_of::<f32>()).ok_or(ABI_ERROR)?;
    if pointer.is_null() || start % mem::align_of::<f32>() != 0 || bytes > isize::MAX as usize { return Err(ABI_ERROR); }
    Ok((start, start.checked_add(bytes).ok_or(ABI_ERROR)?))
}
fn overlaps(a: (usize, usize), b: (usize, usize)) -> bool { a.0 < b.1 && b.0 < a.1 }
fn disjoint(output: *mut f32, output_len: usize, a: *const f32, a_len: usize,
    b: *const f32, b_len: usize) -> Result<(), i32> {
    let out = span(output, output_len)?;
    if overlaps(out, span(a, a_len)?) || overlaps(out, span(b, b_len)?) { return Err(ABI_ERROR); }
    Ok(())
}
fn status(result: std::thread::Result<Result<(), i32>>) -> i32 {
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}
#[no_mangle]
pub extern "C" fn lrt_skin_evenness_abi() -> u32 { 1 }
/// # Safety
/// Caller supplies live aligned buffers of the stated float lengths. Inputs are
/// immutable and output exclusively owned/disjoint. Callback/context stay valid;
/// callback must not unwind, reenter or change buffers. Panic containment cannot
/// repair foreign faults, invalid pointers or aborts. A nonzero status writes no
/// output. The final successful copy is not interruptible or synchronization.
#[no_mangle]
pub unsafe extern "C" fn lrt_skin_evenness_prepare_v1(source: *const f32, source_len: usize,
    coverage: *const f32, coverage_len: usize, width: usize, height: usize,
    amount: f32, radius: usize, output: *mut f32, output_len: usize,
    cancel: Cancel, context: *mut c_void) -> i32 {
    status(panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(), i32> {
        let n = admit(width, height, NATIVE_PREPARE_TOTAL_BYTES_PER_PIXEL)?;
        if source_len != n*3 || coverage_len != n || output_len != n*2 { return Err(ABI_ERROR); }
        if !unit(amount) || !(MIN_RADIUS..=MAX_RADIUS).contains(&radius) { return Err(SETTINGS_ERROR); }
        disjoint(output, output_len, source, source_len, coverage, coverage_len)?;
        prepare_into(slice::from_raw_parts(source, source_len), slice::from_raw_parts(coverage, coverage_len),
            width, height, amount, radius, slice::from_raw_parts_mut(output, output_len),
            || cancel.map_or(false, |function| function(context) != 0))
    })))
}
/// # Safety
/// Same allocation, immutability, callback and publication contract as prepare.
#[no_mangle]
pub unsafe extern "C" fn lrt_skin_evenness_apply_v1(current: *const f32, current_len: usize,
    shift: *const f32, shift_len: usize, width: usize, height: usize,
    output: *mut f32, output_len: usize, cancel: Cancel, context: *mut c_void) -> i32 {
    status(panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(), i32> {
        let n = admit(width, height, NATIVE_APPLY_TOTAL_BYTES_PER_PIXEL)?;
        if current_len != n*3 || shift_len != n*2 || output_len != n*3 { return Err(ABI_ERROR); }
        disjoint(output, output_len, current, current_len, shift, shift_len)?;
        apply_into(slice::from_raw_parts(current, current_len), slice::from_raw_parts(shift, shift_len),
            width, height, slice::from_raw_parts_mut(output, output_len),
            || cancel.map_or(false, |function| function(context) != 0))
    })))
}

#[cfg(test)]
mod tests;
