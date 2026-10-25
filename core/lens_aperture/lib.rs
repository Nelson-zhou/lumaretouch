// SPDX-License-Identifier: GPL-3.0-or-later
//! Independently authored finite-aperture, source-radius depth blur. AUTHORED / UNRUN.
//! Linear-sRGB D65 premultiplied float32 RGBA; no Gaussian, RGB clipping, model,
//! focal-length interpretation, hidden depth inference or copied GEGL code.
//! See README.md for the deliberately limited 2.5D visibility approximation.

use std::{ffi::c_void, mem, panic, slice};

pub const MAX_SOURCE_PIXELS: usize = 100_000_000;
pub const MAX_TILE_PIXELS: usize = 65_536;
pub const MAX_RADIUS_PX: f32 = 128.0;
pub const MAX_CANDIDATE_TAPS: usize = 8_388_608;
pub const SUBPIXEL_AXIS: usize = 4;
pub const POLL_TAPS: usize = 256;
pub const HDR_STRAIGHT_LIMIT: f64 = 65_504.0;
pub const ABI_ERROR: i32 = 1;
pub const SETTINGS_ERROR: i32 = 2;
pub const PIXEL_ERROR: i32 = 3;
pub const CANCELLED: i32 = 4;
pub const RESOURCE_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;
pub const RESULT_ERROR: i32 = 7;
pub type Cancel = Option<extern "C" fn(*mut c_void) -> i32>;

/// Stable ABI layout. All floats finite. Aperture IDs are OUR mathematical
/// kernels, not undocumented commercial implementations or physical lens models.
#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct Settings {
    pub aperture: u32,
    pub max_radius_px: f32,
    pub focus_near: f32,
    pub focus_far: f32,
    pub depth_falloff: f32,
    pub occlusion_tolerance: f32,
    pub rotation_radians: f32,
}

impl Settings {
    pub fn validate(self) -> Result<(), i32> {
        if self.aperture > 4 || !self.max_radius_px.is_finite()
            || !(0.0..=MAX_RADIUS_PX).contains(&self.max_radius_px)
            || !unit(self.focus_near) || !unit(self.focus_far)
            || self.focus_near > self.focus_far
            || !self.depth_falloff.is_finite()
            || !(0.000_001..=1.0).contains(&self.depth_falloff)
            || !unit(self.occlusion_tolerance)
            || !self.rotation_radians.is_finite()
            || !(-std::f32::consts::PI..=std::f32::consts::PI).contains(&self.rotation_radians)
        { return Err(SETTINGS_ERROR); }
        Ok(())
    }
}

fn unit(v: f32) -> bool { v.is_finite() && (0.0..=1.0).contains(&v) }
fn signed_unit(v: f32) -> bool { v.is_finite() && (-1.0..=1.0).contains(&v) }
fn poll<F: FnMut() -> bool>(cancel: &mut F) -> Result<(), i32> {
    if cancel() { Err(CANCELLED) } else { Ok(()) }
}
fn count(width: usize, height: usize, maximum: usize) -> Result<usize, i32> {
    if width == 0 || height == 0 { return Err(ABI_ERROR); }
    width.checked_mul(height).filter(|n| *n <= maximum).ok_or(RESOURCE_ERROR)
}
fn valid_pixel(pixel: &[f32]) -> bool {
    let alpha = pixel[3];
    unit(alpha) && pixel[..3].iter().all(|v| v.is_finite()
        && f64::from(v.abs()) <= HDR_STRAIGHT_LIMIT * f64::from(alpha))
}
fn refinement_at(refinement: Option<&[f32]>, i: usize) -> f32 {
    refinement.map_or(0.0, |plane| plane[i])
}
fn check_pixel(source: &[f32], depth: &[f32], refinement: Option<&[f32]>, i: usize)
    -> Result<(), i32>
{
    if !valid_pixel(&source[4*i..4*i+4]) || !unit(depth[i])
        || !signed_unit(refinement_at(refinement, i)) { return Err(PIXEL_ERROR); }
    Ok(())
}
fn lengths(source: &[f32], depth: &[f32], refinement: Option<&[f32]>, n: usize)
    -> Result<(), i32>
{
    if source.len() != n.checked_mul(4).ok_or(RESOURCE_ERROR)? || depth.len() != n
        || refinement.map_or(false, |p| p.len() != n) { return Err(ABI_ERROR); }
    Ok(())
}

/// Validate an immutable complete source/depth/refinement snapshot once before
/// use. This does not prove colour-space labels, depth direction or source identity.
pub fn validate_inputs<F: FnMut() -> bool>(
    source: &[f32], depth: &[f32], refinement: Option<&[f32]>,
    width: usize, height: usize, mut cancelled: F,
) -> Result<(), i32> {
    let n = count(width, height, MAX_SOURCE_PIXELS)?;
    lengths(source, depth, refinement, n)?;
    for i in 0..n {
        if i % POLL_TAPS == 0 { poll(&mut cancelled)?; }
        check_pixel(source, depth, refinement, i)?;
    }
    poll(&mut cancelled)
}

/// Radius belongs to the EMITTING source pixel, never only the receiving pixel.
/// Depth is normalized relative distance: 0 near, 1 far, no metres or disparity.
fn source_radius(depth: f32, refinement: f32, settings: Settings) -> f64 {
    let z = f64::from(depth);
    let distance = (f64::from(settings.focus_near) - z)
        .max(z - f64::from(settings.focus_far)).max(0.0);
    let base = (distance / f64::from(settings.depth_falloff)).min(1.0);
    let q = f64::from(refinement);
    let refined = if q >= 0.0 { base + (1.0 - base) * q } else { base * (1.0 + q) };
    f64::from(settings.max_radius_px) * refined
}

/// One-way conservative depth visibility, applied BEFORE normalizing colour.
/// A farther emitter cannot bleed into an opaque nearer receiver. Partial alpha
/// attenuates it by the receiver's uncovered fraction. Closer/same-depth emitters
/// can spread outward. This is NOT multilayer visibility or hidden-surface recovery.
fn visibility(emitter_depth: f32, receiver_depth: f32, receiver_alpha: f32,
              tolerance: f32) -> f64 {
    if f64::from(emitter_depth) > f64::from(receiver_depth) + f64::from(tolerance) {
        1.0 - f64::from(receiver_alpha)
    } else { 1.0 }
}

struct Aperture {
    id: u32,
    cosine: f64,
    sine: f64,
    normals: [[f64; 2]; 8],
    sides: usize,
    inradius: f64,
    unit_mass: f64,
}
impl Aperture {
    fn new(settings: Settings) -> Self {
        let (sine, cosine) = f64::from(settings.rotation_radians).sin_cos();
        let sides = match settings.aperture { 2 => 5, 3 => 8, _ => 0 };
        let mut normals = [[0.0; 2]; 8];
        let pi = std::f64::consts::PI;
        for (k, normal) in normals.iter_mut().take(sides).enumerate() {
            let angle = 2.0 * pi * k as f64 / sides as f64;
            *normal = [angle.cos(), angle.sin()];
        }
        let inradius = if sides > 0 { (pi / sides as f64).cos() } else { 0.0 };
        let unit_mass = match settings.aperture {
            0 => pi,
            // Original rim-weighted disk T(rho)=.25+.75*rho^2.
            1 => 0.625 * pi,
            2 | 3 => 0.5 * sides as f64 * (2.0 * pi / sides as f64).sin(),
            // Intersection of unit disks centred at (+-.35,0).
            4 => 2.0 * 0.35_f64.acos() - 0.7 * (1.0 - 0.35_f64.powi(2)).sqrt(),
            _ => unreachable!("settings validated before aperture construction"),
        };
        Self { id: settings.aperture, cosine, sine, normals, sides, inradius, unit_mass }
    }
    fn transmission(&self, x: f64, y: f64) -> f64 {
        let u = self.cosine * x + self.sine * y;
        let v = -self.sine * x + self.cosine * y;
        let radius_squared = u*u + v*v;
        if radius_squared > 1.0 { return 0.0; }
        match self.id {
            0 => 1.0,
            1 => 0.25 + 0.75 * radius_squared,
            2 | 3 => {
                if self.normals[..self.sides].iter()
                    .all(|n| u*n[0] + v*n[1] <= self.inradius) { 1.0 } else { 0.0 }
            }
            4 => {
                if (u-0.35).powi(2)+v*v <= 1.0 && (u+0.35).powi(2)+v*v <= 1.0
                    { 1.0 } else { 0.0 }
            }
            _ => 0.0,
        }
    }
    /// Pixel-box integral approximated by a deterministic 4x4 midpoint grid.
    /// Normalized by analytic aperture mass; receiving mass is renormalized
    /// later. No claim of exact aperture integration or global flux conservation.
    fn weight(&self, dx: f64, dy: f64, radius: f64) -> f64 {
        if radius <= 0.5 { return if dx == 0.0 && dy == 0.0 { 1.0 } else { 0.0 }; }
        if dx.abs() > radius + 0.5 || dy.abs() > radius + 0.5 { return 0.0; }
        let mut integral = 0.0;
        for sy in 0..SUBPIXEL_AXIS {
            let y = (dy + (sy as f64 + 0.5) / SUBPIXEL_AXIS as f64 - 0.5) / radius;
            for sx in 0..SUBPIXEL_AXIS {
                let x = (dx + (sx as f64 + 0.5) / SUBPIXEL_AXIS as f64 - 0.5) / radius;
                integral += self.transmission(x, y);
            }
        }
        integral / ((SUBPIXEL_AXIS * SUBPIXEL_AXIS) as f64 * self.unit_mass * radius * radius)
    }
}

/// The enclosing support includes half a destination pixel. Entire source is
/// supplied; real image edges clip support, whereas tile boundaries never do.
pub fn halo_pixels(settings: Settings) -> Result<usize, i32> {
    settings.validate()?;
    Ok(if settings.max_radius_px <= 0.5 { 0 }
       else { (f64::from(settings.max_radius_px) + 0.5).ceil() as usize })
}
pub fn candidate_budget(width: usize, height: usize, tile_pixels: usize, halo: usize)
    -> Result<usize, i32>
{
    let diameter = halo.checked_mul(2).and_then(|v| v.checked_add(1)).ok_or(RESOURCE_ERROR)?;
    let candidates = tile_pixels.checked_mul(width.min(diameter))
        .and_then(|v| v.checked_mul(height.min(diameter))).ok_or(RESOURCE_ERROR)?;
    if candidates > MAX_CANDIDATE_TAPS { return Err(RESOURCE_ERROR); }
    Ok(candidates)
}

/// Safe tile operation. Every failure, cancellation and invalid result leaves
/// output bitwise unchanged. All halo inputs are checked even on neutral paths.
/// Host must first validate the entire snapshot and preserve it immutably.
#[allow(clippy::too_many_arguments)]
pub fn render_tile_into<F: FnMut() -> bool>(
    source: &[f32], depth: &[f32], refinement: Option<&[f32]>,
    width: usize, height: usize, x: usize, y: usize, tile_width: usize, tile_height: usize,
    settings: Settings, output: &mut [f32], mut cancelled: F,
) -> Result<(), i32> {
    let n = count(width, height, MAX_SOURCE_PIXELS)?;
    let tile_n = count(tile_width, tile_height, MAX_TILE_PIXELS)?;
    lengths(source, depth, refinement, n)?;
    if output.len() != tile_n.checked_mul(4).ok_or(RESOURCE_ERROR)?
        || x.checked_add(tile_width).filter(|end| *end <= width).is_none()
        || y.checked_add(tile_height).filter(|end| *end <= height).is_none()
    { return Err(ABI_ERROR); }
    let halo = halo_pixels(settings)?;
    candidate_budget(width, height, tile_n, halo)?;
    poll(&mut cancelled)?;
    let x0 = x.saturating_sub(halo);
    let y0 = y.saturating_sub(halo);
    let x1 = (x + tile_width).saturating_add(halo).min(width);
    let y1 = (y + tile_height).saturating_add(halo).min(height);
    let mut ticks = 0usize;
    for sy in y0..y1 {
        for sx in x0..x1 {
            if ticks % POLL_TAPS == 0 { poll(&mut cancelled)?; }
            ticks += 1;
            check_pixel(source, depth, refinement, sy*width+sx)?;
        }
    }
    let mut staged = Vec::new();
    staged.try_reserve_exact(output.len()).map_err(|_| RESOURCE_ERROR)?;
    let aperture = Aperture::new(settings);
    for dy in y..y+tile_height {
        for dx in x..x+tile_width {
            poll(&mut cancelled)?;
            let destination = dy*width+dx;
            let original = &source[4*destination..4*destination+4];
            let refinement_here = refinement_at(refinement, destination);
            if halo == 0 || refinement_here == -1.0 {
                staged.extend_from_slice(original);
                continue;
            }
            let mut sum = [0.0_f64; 4];
            let mut mass = 0.0;
            let mut contributors = 0usize;
            let mut sole_source = destination;
            for sy in dy.saturating_sub(halo)..=(dy.saturating_add(halo).min(height-1)) {
                for sx in dx.saturating_sub(halo)..=(dx.saturating_add(halo).min(width-1)) {
                    if ticks % POLL_TAPS == 0 { poll(&mut cancelled)?; }
                    ticks += 1;
                    let i = sy*width+sx;
                    let visible = visibility(depth[i], depth[destination], original[3],
                                             settings.occlusion_tolerance);
                    if visible == 0.0 { continue; }
                    let radius = source_radius(depth[i], refinement_at(refinement, i), settings);
                    let weight = visible * aperture.weight(dx as f64 - sx as f64,
                                                          dy as f64 - sy as f64, radius);
                    if weight == 0.0 { continue; }
                    contributors += 1;
                    sole_source = i;
                    mass += weight;
                    for c in 0..4 { sum[c] += weight * f64::from(source[4*i+c]); }
                }
            }
            if contributors == 1 && sole_source == destination {
                staged.extend_from_slice(original);
                continue;
            }
            if !mass.is_finite() || mass <= 0.0 { return Err(RESULT_ERROR); }
            let clear = f64::from((-refinement_here).max(0.0));
            let result: [f32; 4] = std::array::from_fn(|c| {
                ((1.0-clear) * (sum[c]/mass) + clear*f64::from(original[c])) as f32
            });
            // Mathematical convexity preserves bounds in exact arithmetic, but
            // float32 rounding can violate the premultiplication envelope. Reject
            // rather than clip, unpremultiply or hide a rounding violation.
            if !valid_pixel(&result) { return Err(RESULT_ERROR); }
            staged.extend_from_slice(&result);
        }
    }
    poll(&mut cancelled)?;
    output.copy_from_slice(&staged);
    Ok(())
}

fn span(pointer: *const f32, length: usize) -> Result<(usize, usize), i32> {
    let start = pointer as usize;
    let bytes = length.checked_mul(mem::size_of::<f32>()).ok_or(ABI_ERROR)?;
    if pointer.is_null() || start % mem::align_of::<f32>() != 0 || bytes > isize::MAX as usize {
        return Err(ABI_ERROR);
    }
    Ok((start, start.checked_add(bytes).ok_or(ABI_ERROR)?))
}
fn overlap(a: (usize, usize), b: (usize, usize)) -> bool { a.0 < b.1 && b.0 < a.1 }
unsafe fn optional_plane<'a>(p: *const f32, length: usize, expected: usize)
    -> Result<Option<&'a [f32]>, i32>
{
    if p.is_null() { return if length == 0 { Ok(None) } else { Err(ABI_ERROR) }; }
    if length != expected { return Err(ABI_ERROR); }
    span(p, length)?;
    Ok(Some(slice::from_raw_parts(p, length)))
}
fn caught(result: Result<Result<(), i32>, Box<dyn std::any::Any + Send>>) -> i32 {
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}

#[no_mangle]
pub extern "C" fn lrt_lens_aperture_abi() -> u32 { 1 }

/// Bit k means original aperture k is implemented, not quality/acceptance passed.
#[no_mangle]
pub extern "C" fn lrt_lens_aperture_kernel_mask_v1() -> u32 { 0b1_1111 }

/// # Safety
/// Valid, aligned, live immutable input allocations of stated lengths. Callback
/// must not unwind, reenter, mutate/free inputs or invalidate its own context.
#[no_mangle]
pub unsafe extern "C" fn lrt_lens_aperture_validate_v1(
    source: *const f32, source_len: usize, depth: *const f32, depth_len: usize,
    refinement: *const f32, refinement_len: usize, width: usize, height: usize,
    cancel: Cancel, context: *mut c_void,
) -> i32 {
    caught(panic::catch_unwind(panic::AssertUnwindSafe(|| {
        let n = count(width, height, MAX_SOURCE_PIXELS)?;
        if source_len != n*4 || depth_len != n { return Err(ABI_ERROR); }
        span(source, source_len)?;
        span(depth, depth_len)?;
        let plane = optional_plane(refinement, refinement_len, n)?;
        validate_inputs(slice::from_raw_parts(source, source_len),
                        slice::from_raw_parts(depth, depth_len), plane, width, height,
                        || cancel.map_or(false, |function| function(context) != 0))
    })))
}

/// # Safety
/// As validation above; output must be a live aligned exclusively writable
/// allocation disjoint from every input. Settings are passed by value. Every
/// nonzero return preserves output. Panic containment cannot fix invalid memory,
/// foreign callback faults, process aborts or external concurrent mutation.
#[no_mangle]
pub unsafe extern "C" fn lrt_lens_aperture_render_tile_v1(
    source: *const f32, source_len: usize, depth: *const f32, depth_len: usize,
    refinement: *const f32, refinement_len: usize, width: usize, height: usize,
    x: usize, y: usize, tile_width: usize, tile_height: usize, settings: Settings,
    output: *mut f32, output_len: usize, cancel: Cancel, context: *mut c_void,
) -> i32 {
    caught(panic::catch_unwind(panic::AssertUnwindSafe(|| {
        let n = count(width, height, MAX_SOURCE_PIXELS)?;
        let tile_n = count(tile_width, tile_height, MAX_TILE_PIXELS)?;
        if source_len != n*4 || depth_len != n || output_len != tile_n*4 { return Err(ABI_ERROR); }
        let out = span(output, output_len)?;
        for input in [span(source, source_len)?, span(depth, depth_len)?] {
            if overlap(input, out) { return Err(ABI_ERROR); }
        }
        if !refinement.is_null() && overlap(span(refinement, refinement_len)?, out) {
            return Err(ABI_ERROR);
        }
        let plane = optional_plane(refinement, refinement_len, n)?;
        render_tile_into(slice::from_raw_parts(source, source_len),
                         slice::from_raw_parts(depth, depth_len), plane, width, height,
                         x, y, tile_width, tile_height, settings,
                         slice::from_raw_parts_mut(output, output_len),
                         || cancel.map_or(false, |function| function(context) != 0))
    })))
}

#[cfg(test)]
mod tests;
