// SPDX-License-Identifier: GPL-3.0-or-later
//! Original manually referenced hair chromatic unification. AUTHORED / UNRUN.
//! Full-source robust reference measurement followed by bounded CURRENT-stage
//! composition. No learned inference, palette selection, blur or additive delta.
//! See docs/hair-unification/{CORE,NUMERICS,ABI,ACCEPTANCE-UNRUN}.md.

use std::{ffi::c_void, mem, panic, ptr, slice};

pub const ABI_VERSION: u32 = 1;
pub const OK: i32 = 0;
pub const ABI_ERROR: i32 = 1;
pub const VALUE_ERROR: i32 = 2;
pub const LIMIT_ERROR: i32 = 3;
pub const CANCELLED: i32 = 4;
pub const ALLOCATION_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;
pub const UNRELIABLE_REFERENCE: i32 = 7;
pub const AMBIGUOUS_REFERENCE: i32 = 8;
pub const RESULT_ERROR: i32 = 9;
const W: [f64; 3] = [0.2126, 0.7152, 0.0722];
const BINS: usize = 512;
const MIN_PIXELS: u64 = 32;
const MIN_EFFECTIVE: f64 = 32.0;
const MIN_WEIGHT: f64 = 16.0;
const MIN_RETAINED: f64 = 0.70;
const MAX_DISPERSION: f64 = 0.06;
const MEASURE_WORKING_BYTES: u64 = 32_768;

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct LimitsV1 {
    pub max_source_pixels: u64,
    pub max_tile_pixels: u64,
    pub max_work_units: u64,
    pub max_working_bytes: u64,
}
impl Default for LimitsV1 {
    fn default() -> Self {
        Self { max_source_pixels: 64_000_000, max_tile_pixels: 262_144,
               max_work_units: 1_000_000_000, max_working_bytes: 8_388_608 }
    }
}
#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct ReferenceV1 {
    pub abi_version: u32,
    pub struct_size: u32,
    pub direction: i32,
    pub reserved: u32,
    pub source_width: u32,
    pub source_height: u32,
    pub selected_pixels: u64,
    pub reliable_pixels: u64,
    pub selected_weight: f64,
    pub reliable_weight: f64,
    pub effective_samples: f64,
    pub retained_fraction: f64,
    pub dispersion: f64,
    pub chroma_ratio: [f64; 3],
}
pub type CancelV1 = Option<unsafe extern "C" fn(*mut c_void) -> u32>;

#[derive(Clone, Copy)]
struct Span { start: usize, end: usize }
fn span<T>(p: *const T, len: usize) -> Result<Span, i32> {
    let start = p as usize;
    let bytes = len.checked_mul(mem::size_of::<T>()).ok_or(ABI_ERROR)?;
    if p.is_null() || start % mem::align_of::<T>() != 0 || bytes > isize::MAX as usize {
        return Err(ABI_ERROR);
    }
    Ok(Span { start, end: start.checked_add(bytes).ok_or(ABI_ERROR)? })
}
fn disjoint(output: Span, input: Span) -> Result<(), i32> {
    if output.start < input.end && input.start < output.end { Err(ABI_ERROR) } else { Ok(()) }
}
fn count(width: u32, height: u32, cap: u64) -> Result<usize, i32> {
    let n = (width as u64).checked_mul(height as u64).ok_or(LIMIT_ERROR)?;
    if width == 0 || height == 0 { return Err(ABI_ERROR); }
    if n > cap { return Err(LIMIT_ERROR); }
    usize::try_from(n).map_err(|_| LIMIT_ERROR)
}
fn exact_len(got: u64, expected: usize) -> Result<(), i32> {
    if got == expected as u64 { Ok(()) } else { Err(ABI_ERROR) }
}
fn amount_direction(amount: f32) -> Result<i32, i32> {
    if !amount.is_finite() || !(-1.0..=1.0).contains(&amount) { return Err(VALUE_ERROR); }
    Ok(if amount < 0.0 { -1 } else if amount > 0.0 { 1 } else { 0 })
}
unsafe fn get_limits(p: *const LimitsV1) -> Result<LimitsV1, i32> {
    let hard = LimitsV1::default();
    let v = if p.is_null() { hard } else { span(p, 1)?; ptr::read(p) };
    if v.max_source_pixels == 0 || v.max_source_pixels > hard.max_source_pixels
        || v.max_tile_pixels == 0 || v.max_tile_pixels > hard.max_tile_pixels
        || v.max_work_units == 0 || v.max_work_units > hard.max_work_units
        || v.max_working_bytes == 0 || v.max_working_bytes > hard.max_working_bytes {
        return Err(LIMIT_ERROR);
    }
    Ok(v)
}
struct Budget { used: u64, limit: u64, last_poll: u64, callback: CancelV1, context: *mut c_void }
impl Budget {
    fn new(limits: LimitsV1, callback: CancelV1, context: *mut c_void) -> Self {
        Self { used: 0, limit: limits.max_work_units, last_poll: 0, callback, context }
    }
    fn poll(&mut self) -> Result<(), i32> {
        self.last_poll = self.used;
        if let Some(f) = self.callback {
            // The caller guarantees non-throwing, non-mutating callback behavior.
            if unsafe { f(self.context) } != 0 { return Err(CANCELLED); }
        }
        Ok(())
    }
    fn charge(&mut self, work: u64) -> Result<(), i32> {
        self.used = self.used.checked_add(work).ok_or(LIMIT_ERROR)?;
        if self.used > self.limit { return Err(LIMIT_ERROR); }
        if self.used - self.last_poll >= 4096 { self.poll()?; }
        Ok(())
    }
}
fn decode(v: f64) -> f64 {
    if v <= 0.04045 { v / 12.92 } else { ((v + 0.055) / 1.055).powf(2.4) }
}
fn encode(v: f64) -> f64 {
    if v <= 0.0031308 { 12.92 * v } else { 1.055 * v.powf(1.0 / 2.4) - 0.055 }
}
fn luminance(p: [f64; 3]) -> f64 { W[0] * p[0] + W[1] * p[1] + W[2] * p[2] }
fn smooth(lo: f64, hi: f64, v: f64) -> f64 {
    let t = ((v - lo) / (hi - lo)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}
fn evidence_gate(rgb: [f64; 3]) -> f64 {
    let y = luminance(rgb);
    let peak = rgb[0].max(rgb[1]).max(rgb[2]);
    // Source/current near-black and near-white evidence is intentionally weak.
    smooth(0.008, 0.04, y) * (1.0 - smooth(0.55, 0.90, y))
        * (1.0 - smooth(0.85, 0.99, peak))
}
fn linear_pixel(rgb: &[f32], i: usize) -> [f64; 3] {
    [decode(rgb[3 * i] as f64), decode(rgb[3 * i + 1] as f64), decode(rgb[3 * i + 2] as f64)]
}
fn valid_pixel(rgb: &[f32], i: usize) -> bool {
    rgb[3 * i..3 * i + 3].iter().all(|v| v.is_finite() && (0.0..=1.0).contains(v))
}
fn valid_mask(v: f32) -> bool { v.is_finite() && (0.0..=1.0).contains(&v) }
fn candidate(rgb: &[f32], mask: &[f32], i: usize) -> Option<([f64; 3], f64)> {
    if mask[i] == 0.0 { return None; }
    let p = linear_pixel(rgb, i);
    let weight = mask[i] as f64 * evidence_gate(p);
    if weight <= 0.0 { return None; }
    let sum = p[0] + p[1] + p[2];
    if sum <= 0.0 { return None; }
    Some((p.map(|v| v / sum), weight))
}
fn bin(v: f64) -> usize { ((v * BINS as f64).floor() as usize).min(BINS - 1) }
fn weighted_median(hist: &[f64; BINS], weight: f64, budget: &mut Budget) -> Result<f64, i32> {
    let mut total = 0.0;
    for (i, w) in hist.iter().enumerate() {
        budget.charge(1)?;
        total += w;
        if total >= weight * 0.5 { return Ok((i as f64 + 0.5) / BINS as f64); }
    }
    Err(RESULT_ERROR)
}
fn distance(a: [f64; 3], b: [f64; 3]) -> f64 {
    (a[0] - b[0]).abs().max((a[1] - b[1]).abs()).max((a[2] - b[2]).abs())
}
fn neutral_reference(width: u32, height: u32) -> ReferenceV1 {
    ReferenceV1 { abi_version: ABI_VERSION, struct_size: mem::size_of::<ReferenceV1>() as u32,
        source_width: width, source_height: height, ..ReferenceV1::default() }
}
fn measure(
    rgb: &[f32], hair: &[f32], roots: &[f32], tips: &[f32],
    width: u32, height: u32, direction: i32, budget: &mut Budget,
) -> Result<ReferenceV1, i32> {
    let selected = if direction < 0 { tips } else { roots };
    let mut hist = [[0.0; BINS]; 3];
    let mut selected_pixels = 0_u64;
    let mut selected_weight = 0.0;
    let mut eligible_weight = 0.0;
    // First pass validates EVERY provided sample, even where coverage is zero.
    for i in 0..hair.len() {
        budget.charge(1)?;
        if !valid_pixel(rgb, i) || !valid_mask(hair[i]) || !valid_mask(roots[i]) || !valid_mask(tips[i]) {
            return Err(VALUE_ERROR);
        }
        if roots[i] > hair[i] || tips[i] > hair[i] { return Err(VALUE_ERROR); }
        if roots[i] > 0.0 && tips[i] > 0.0 { return Err(AMBIGUOUS_REFERENCE); }
        if selected[i] > 0.0 { selected_pixels += 1; selected_weight += selected[i] as f64; }
        if let Some((p, w)) = candidate(rgb, selected, i) {
            eligible_weight += w;
            for c in 0..3 { hist[c][bin(p[c])] += w; }
        }
    }
    if selected_pixels < MIN_PIXELS || selected_weight < MIN_WEIGHT || eligible_weight < MIN_WEIGHT {
        return Err(UNRELIABLE_REFERENCE);
    }
    let mut median = [0.0; 3];
    for c in 0..3 { median[c] = weighted_median(&hist[c], eligible_weight, budget)?; }
    // A bounded weighted MAD in normalized linear-RGB chromaticity space.
    let mut distances = [0.0; BINS];
    for i in 0..hair.len() {
        budget.charge(1)?;
        if let Some((p, w)) = candidate(rgb, selected, i) { distances[bin(distance(p, median))] += w; }
    }
    let mad = weighted_median(&distances, eligible_weight, budget)?;
    if mad > 0.05 { return Err(UNRELIABLE_REFERENCE); }
    let radius = (3.0 * mad).max(0.02).min(0.12);
    let mut weight = 0.0;
    let mut weight_squared = 0.0;
    let mut sum = [0.0; 3];
    let mut sum_squared = 0.0;
    let mut reliable_pixels = 0_u64;
    for i in 0..hair.len() {
        budget.charge(1)?;
        if let Some((p, w)) = candidate(rgb, selected, i) {
            if distance(p, median) > radius { continue; }
            reliable_pixels += 1;
            weight += w;
            weight_squared += w * w;
            for c in 0..3 { sum[c] += p[c] * w; sum_squared += p[c] * p[c] * w; }
        }
    }
    // Cauchy bounds effective support by retained count. Limit only positive
    // summation roundoff in this diagnostic, never image channels or evidence.
    let effective = if weight_squared > 0.0 {
        (weight * weight / weight_squared).min(reliable_pixels as f64)
    } else { 0.0 };
    let retained = weight / eligible_weight;
    if reliable_pixels < MIN_PIXELS || effective + 1.0e-9 < MIN_EFFECTIVE || weight < MIN_WEIGHT
        || retained < MIN_RETAINED || weight / selected_weight < 0.25 { return Err(UNRELIABLE_REFERENCE); }
    let chromaticity = sum.map(|v| v / weight);
    let mean_square: f64 = chromaticity.iter().map(|v| v * v).sum();
    let dispersion = (sum_squared / weight - mean_square).max(0.0).sqrt();
    if !dispersion.is_finite() || dispersion > MAX_DISPERSION { return Err(UNRELIABLE_REFERENCE); }
    let reference_y = luminance(chromaticity);
    let ratio = chromaticity.map(|v| v / reference_y - 1.0);
    Ok(ReferenceV1 { direction, selected_pixels, reliable_pixels, selected_weight,
        reliable_weight: weight, effective_samples: effective, retained_fraction: retained,
        dispersion, chroma_ratio: ratio, ..neutral_reference(width, height) })
}
fn validate_reference(r: &ReferenceV1, direction: i32, limits: LimitsV1) -> Result<(), i32> {
    if r.abi_version != ABI_VERSION || r.struct_size as usize != mem::size_of::<ReferenceV1>()
        || r.reserved != 0 || r.direction != direction || direction == 0 { return Err(ABI_ERROR); }
    let n = count(r.source_width, r.source_height, limits.max_source_pixels)? as u64;
    let values = [r.selected_weight, r.reliable_weight, r.effective_samples,
                  r.retained_fraction, r.dispersion];
    if values.iter().any(|v| !v.is_finite()) || r.selected_pixels > n
        || r.reliable_pixels < MIN_PIXELS || r.reliable_pixels > r.selected_pixels
        || r.selected_weight < MIN_WEIGHT || r.selected_weight > r.selected_pixels as f64 + 1.0e-8
        || r.reliable_weight < MIN_WEIGHT || r.reliable_weight > r.selected_weight + 1.0e-8
        || r.reliable_weight / r.selected_weight < 0.25
        || r.effective_samples + 1.0e-9 < MIN_EFFECTIVE
        || r.effective_samples > r.reliable_pixels as f64 + 1.0e-7
        || !(MIN_RETAINED..=1.0 + 1.0e-12).contains(&r.retained_fraction)
        || !(0.0..=MAX_DISPERSION).contains(&r.dispersion) { return Err(UNRELIABLE_REFERENCE); }
    for (c, q) in r.chroma_ratio.iter().enumerate() {
        if !q.is_finite() || *q < -1.0 - 1.0e-12 || *q > 1.0 / W[c] - 1.0 + 1.0e-12 {
            return Err(VALUE_ERROR);
        }
    }
    if luminance(r.chroma_ratio).abs() > 1.0e-8 { return Err(VALUE_ERROR); }
    Ok(())
}
fn gamut_target(y: f64, q: [f64; 3]) -> Result<[f64; 3], i32> {
    let chroma = q.map(|v| y * v);
    let mut scale = 1.0_f64;
    for v in chroma {
        if v > 0.0 { scale = scale.min((1.0 - y) / v); }
        else if v < 0.0 { scale = scale.min(-y / v); }
    }
    if !scale.is_finite() || scale < 0.0 { return Err(RESULT_ERROR); }
    // Common inward contraction avoids per-channel clamps, including boundary
    // roundoff. It perturbs chroma only, never the neutral-axis luminance.
    scale *= 1.0 - 4.0e-12;
    let target = chroma.map(|v| y + scale * v);
    if target.iter().any(|v| !v.is_finite() || !(0.0..=1.0).contains(v)) { return Err(RESULT_ERROR); }
    Ok(target)
}
fn compose(rgb: &[f32], hair: &[f32], amount: f32, reference: &ReferenceV1,
           budget: &mut Budget) -> Result<Vec<f32>, i32> {
    let mut output = Vec::new();
    output.try_reserve_exact(rgb.len()).map_err(|_| ALLOCATION_ERROR)?;
    output.resize(rgb.len(), 0.0);
    for i in 0..hair.len() {
        budget.charge(1)?;
        if !valid_pixel(rgb, i) || !valid_mask(hair[i]) { return Err(VALUE_ERROR); }
        let p = linear_pixel(rgb, i);
        let alpha = amount.abs() as f64 * hair[i] as f64 * evidence_gate(p);
        if alpha == 0.0 {
            output[3 * i..3 * i + 3].copy_from_slice(&rgb[3 * i..3 * i + 3]);
            continue;
        }
        let target = gamut_target(luminance(p), reference.chroma_ratio)?;
        for c in 0..3 {
            let linear = p[c] * (1.0 - alpha) + target[c] * alpha;
            let encoded = encode(linear);
            if !encoded.is_finite() || !(0.0..=1.0).contains(&encoded) { return Err(RESULT_ERROR); }
            output[3 * i + c] = encoded as f32;
        }
    }
    Ok(output)
}

#[no_mangle]
pub extern "C" fn lrt_hair_unification_abi() -> u32 { ABI_VERSION }

/// # Safety
/// All non-null accessed pointers must address their declared live, aligned
/// immutable spans; the output must be disjoint. See the C header and ABI.md.
#[no_mangle]
pub unsafe extern "C" fn lrt_hair_unification_measure_v1(
    source_rgb: *const f32, source_rgb_len: u64, hair: *const f32, hair_len: u64,
    roots: *const f32, roots_len: u64, tips: *const f32, tips_len: u64,
    source_width: u32, source_height: u32, signed_amount: f32,
    limits: *const LimitsV1, reference_out: *mut ReferenceV1,
    cancel: CancelV1, cancel_context: *mut c_void,
) -> i32 {
    let result = panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(), i32> {
        let direction = amount_direction(signed_amount)?;
        let limit = get_limits(limits)?;
        let n = count(source_width, source_height, limit.max_source_pixels)?;
        let output_span = span(reference_out, 1)?;
        if !limits.is_null() { disjoint(output_span, span(limits, 1)?)?; }
        let mut budget = Budget::new(limit, cancel, cancel_context);
        budget.poll()?;
        let reference = if direction == 0 {
            neutral_reference(source_width, source_height)
        } else {
            if limit.max_working_bytes < MEASURE_WORKING_BYTES { return Err(LIMIT_ERROR); }
            let rgb_len = n.checked_mul(3).ok_or(ABI_ERROR)?;
            exact_len(source_rgb_len, rgb_len)?;
            exact_len(hair_len, n)?; exact_len(roots_len, n)?; exact_len(tips_len, n)?;
            for input in [span(source_rgb, rgb_len)?, span(hair, n)?, span(roots, n)?, span(tips, n)?] {
                disjoint(output_span, input)?;
            }
            measure(slice::from_raw_parts(source_rgb, rgb_len), slice::from_raw_parts(hair, n),
                slice::from_raw_parts(roots, n), slice::from_raw_parts(tips, n),
                source_width, source_height, direction, &mut budget)?
        };
        budget.poll()?;
        ptr::write(reference_out, reference);
        Ok(())
    }));
    match result { Ok(Ok(())) => OK, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

/// # Safety
/// The inputs are tightly packed CURRENT-stage tile pixels, not the immutable
/// measurement frame. Caller binds target coverage and tile to the source ID.
#[no_mangle]
pub unsafe extern "C" fn lrt_hair_unification_compose_v1(
    current_rgb: *const f32, current_rgb_len: u64, hair: *const f32, hair_len: u64,
    tile_x: u32, tile_y: u32, tile_width: u32, tile_height: u32,
    signed_amount: f32, reference: *const ReferenceV1, limits: *const LimitsV1,
    output_rgb: *mut f32, output_rgb_len: u64, cancel: CancelV1, cancel_context: *mut c_void,
) -> i32 {
    let result = panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(), i32> {
        let direction = amount_direction(signed_amount)?;
        let limit = get_limits(limits)?;
        let n = count(tile_width, tile_height, limit.max_tile_pixels)?;
        tile_x.checked_add(tile_width).ok_or(ABI_ERROR)?;
        tile_y.checked_add(tile_height).ok_or(ABI_ERROR)?;
        let rgb_len = n.checked_mul(3).ok_or(ABI_ERROR)?;
        exact_len(current_rgb_len, rgb_len)?; exact_len(output_rgb_len, rgb_len)?;
        let output_span = span(output_rgb, rgb_len)?;
        disjoint(output_span, span(current_rgb, rgb_len)?)?;
        if !limits.is_null() { disjoint(output_span, span(limits, 1)?)?; }
        let mut budget = Budget::new(limit, cancel, cancel_context);
        budget.poll()?;
        if direction == 0 {
            // No RGB-value validation, masks, reference, allocation or conversion.
            budget.charge(n as u64)?;
            budget.poll()?;
            ptr::copy_nonoverlapping(current_rgb, output_rgb, rgb_len);
            return Ok(());
        }
        exact_len(hair_len, n)?;
        disjoint(output_span, span(hair, n)?)?;
        disjoint(output_span, span(reference, 1)?)?;
        let r = ptr::read(reference);
        validate_reference(&r, direction, limit)?;
        if tile_x + tile_width > r.source_width || tile_y + tile_height > r.source_height { return Err(ABI_ERROR); }
        let scratch = (rgb_len as u64).checked_mul(mem::size_of::<f32>() as u64)
            .and_then(|v| v.checked_add(4096)).ok_or(LIMIT_ERROR)?;
        if scratch > limit.max_working_bytes { return Err(LIMIT_ERROR); }
        let candidate = compose(slice::from_raw_parts(current_rgb, rgb_len),
            slice::from_raw_parts(hair, n), signed_amount, &r, &mut budget)?;
        // The only output write is an infallible bounded commit after final poll.
        budget.poll()?;
        ptr::copy_nonoverlapping(candidate.as_ptr(), output_rgb, rgb_len);
        Ok(())
    }));
    match result { Ok(Ok(())) => OK, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

fn validate_grid_projection(grid_width: u32, grid_height: u32, reference: &ReferenceV1) -> Result<(), i32> {
    if grid_width == 0 || grid_height == 0 || grid_width > reference.source_width
        || grid_height > reference.source_height { return Err(ABI_ERROR); }
    if grid_width == reference.source_width && grid_height == reference.source_height { return Ok(()); }
    // decode.proxy_size aligns EACH reduced axis to 8, with an 8-pixel minimum.
    // Exact full grids need no alignment. An exceptional tiny-axis decoder
    // upscale is deliberately refused by the non-upscaling check above.
    if grid_width % 8 != 0 || grid_height % 8 != 0 { return Err(ABI_ERROR); }
    // Same strict common-scale interval as body_pose_evidence.whole_source_shape:
    // [grid_width/source_width, (grid_width+8)/source_width) must overlap the
    // height interval. Upper ends are OPEN because proxy_size rounds downward.
    // The host still authenticates exact proxy_size output and budget. Tiny-axis
    // floor/fallback results outside this interval are deliberately unsupported.
    let a = (grid_width as u64).checked_mul(reference.source_height as u64).ok_or(ABI_ERROR)?;
    let b = (grid_height as u64).checked_mul(reference.source_width as u64).ok_or(ABI_ERROR)?;
    let upper_y = (grid_height as u64).checked_add(8)
        .and_then(|v| v.checked_mul(reference.source_width as u64)).ok_or(ABI_ERROR)?;
    let upper_x = (grid_width as u64).checked_add(8)
        .and_then(|v| v.checked_mul(reference.source_height as u64)).ok_or(ABI_ERROR)?;
    if a >= upper_y || b >= upper_x { return Err(ABI_ERROR); }
    Ok(())
}

/// Explicit processing-grid composition with a genuine full-source reference.
/// The older compose_v1 implementation and its source-grid-only ABI are unchanged.
/// # Safety
/// Buffers follow compose_v1's live/aligned/disjoint rules. The caller additionally
/// guarantees the current grid and target coverage were projected from the same
/// source/person/transform in working-sRGB, without falsifying reference metadata.
#[no_mangle]
pub unsafe extern "C" fn lrt_hair_unification_compose_grid_v1(
    current_rgb: *const f32, current_rgb_len: u64, hair: *const f32, hair_len: u64,
    grid_width: u32, grid_height: u32,
    tile_x: u32, tile_y: u32, tile_width: u32, tile_height: u32,
    signed_amount: f32, reference: *const ReferenceV1, limits: *const LimitsV1,
    output_rgb: *mut f32, output_rgb_len: u64, cancel: CancelV1, cancel_context: *mut c_void,
) -> i32 {
    let result = panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(), i32> {
        let direction = amount_direction(signed_amount)?;
        let limit = get_limits(limits)?;
        count(grid_width, grid_height, limit.max_source_pixels)?;
        let n = count(tile_width, tile_height, limit.max_tile_pixels)?;
        let end_x = tile_x.checked_add(tile_width).ok_or(ABI_ERROR)?;
        let end_y = tile_y.checked_add(tile_height).ok_or(ABI_ERROR)?;
        if end_x > grid_width || end_y > grid_height { return Err(ABI_ERROR); }
        let rgb_len = n.checked_mul(3).ok_or(ABI_ERROR)?;
        exact_len(current_rgb_len, rgb_len)?; exact_len(output_rgb_len, rgb_len)?;
        let output_span = span(output_rgb, rgb_len)?;
        disjoint(output_span, span(current_rgb, rgb_len)?)?;
        if !limits.is_null() { disjoint(output_span, span(limits, 1)?)?; }
        let mut budget = Budget::new(limit, cancel, cancel_context);
        budget.poll()?;
        if direction == 0 {
            // Explicit grid bounds remain meaningful without evidence. The RGB
            // bits, mask and reference otherwise follow the legacy neutral path.
            budget.charge(n as u64)?;
            budget.poll()?;
            ptr::copy_nonoverlapping(current_rgb, output_rgb, rgb_len);
            return Ok(());
        }
        exact_len(hair_len, n)?;
        disjoint(output_span, span(hair, n)?)?;
        disjoint(output_span, span(reference, 1)?)?;
        let r = ptr::read(reference);
        validate_reference(&r, direction, limit)?;
        validate_grid_projection(grid_width, grid_height, &r)?;
        let scratch = (rgb_len as u64).checked_mul(mem::size_of::<f32>() as u64)
            .and_then(|v| v.checked_add(4096)).ok_or(LIMIT_ERROR)?;
        if scratch > limit.max_working_bytes { return Err(LIMIT_ERROR); }
        let candidate = compose(slice::from_raw_parts(current_rgb, rgb_len),
            slice::from_raw_parts(hair, n), signed_amount, &r, &mut budget)?;
        budget.poll()?;
        ptr::copy_nonoverlapping(candidate.as_ptr(), output_rgb, rgb_len);
        Ok(())
    }));
    match result { Ok(Ok(())) => OK, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

#[cfg(test)]
mod tests;
