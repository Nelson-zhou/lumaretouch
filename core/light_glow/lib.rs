// SPDX-License-Identifier: GPL-3.0-or-later
//! Original Lumaretouch deterministic SDR light diffusion. AUTHORED / UNRUN.
//! No neural analysis, optical equivalence, scene HDR clipping or foreign code.
//! Exact finite-support source-addressed tiles; see ABI.md and NUMERICS.md.

use std::{ffi::c_void, mem, panic, ptr, slice};

pub const ABI_VERSION: u32 = 1;
pub const MATH_IDENTITY: u32 = 0x0001_0001;
pub const MAX_SOURCE_PIXELS: u64 = 100_000_000;
pub const MAX_EDGE: u32 = 12_000;
pub const MAX_TILE_PIXELS: u64 = 65_536;
pub const MAX_TILE_EDGE: u32 = 512;
pub const MAX_WORK_BYTES: u64 = 512 * 1024 * 1024;
const CHANNELS: usize = 9;
const FIXED_RESERVE: u64 = 8192;
pub const ABI_ERROR: i32 = 1;
pub const SETTINGS_ERROR: i32 = 2;
pub const GEOMETRY_ERROR: i32 = 3;
pub const PIXEL_ERROR: i32 = 4;
pub const BUDGET_ERROR: i32 = 5;
pub const CANCELLED: i32 = 6;
pub const ALLOCATION_ERROR: i32 = 7;
pub const NUMERIC_ERROR: i32 = 8;
pub const PANIC_ERROR: i32 = 9;
pub type Cancel = Option<extern "C" fn(*mut c_void) -> i32>;

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Settings {
    pub struct_bytes: u32,
    pub abi_version: u32,
    pub math_identity: u32,
    pub mode: u32,
    pub radius_px: u32,
    pub reserved: u32,
    pub strength: f32,
    pub threshold: f32,
    pub exposure_ev: f32,
    pub scattering: f32,
    pub hue_deg: f32,
    pub saturation: f32,
    pub lightness: f32,
    pub reserved_f32: f32,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            struct_bytes: mem::size_of::<Self>() as u32,
            abi_version: ABI_VERSION, math_identity: MATH_IDENTITY,
            mode: 0, radius_px: 24, reserved: 0,
            strength: 0.30, threshold: 0.65, exposure_ev: 0.0,
            scattering: 0.0, hue_deg: 0.0, saturation: 0.0,
            lightness: 0.0, reserved_f32: 0.0,
        }
    }
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct Geometry {
    pub struct_bytes: u32,
    pub full_width: u32,
    pub full_height: u32,
    pub tile_x: u32,
    pub tile_y: u32,
    pub tile_width: u32,
    pub tile_height: u32,
    pub reserved: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Plan {
    pub struct_bytes: u32,
    pub region_x: u32,
    pub region_y: u32,
    pub region_width: u32,
    pub region_height: u32,
    pub halo_px: u32,
    pub channels: u32,
    pub reserved: u32,
    pub input_floats: u64,
    pub output_floats: u64,
    pub coverage_floats: u64,
    pub scratch_bytes: u64,
    pub required_bytes: u64,
}

pub struct Rendered {
    pub rgba: Vec<f32>,
    pub coverage: Vec<f32>,
}

fn unit(v: f32) -> bool { v.is_finite() && (0.0..=1.0).contains(&v) }

fn validate_settings(s: &Settings) -> Result<(), i32> {
    if s.struct_bytes != mem::size_of::<Settings>() as u32
        || s.abi_version != ABI_VERSION || s.math_identity != MATH_IDENTITY
        || s.reserved != 0 || s.reserved_f32 != 0.0 {
        return Err(ABI_ERROR);
    }
    if s.mode > 2 || s.radius_px > 512 || !unit(s.strength) || !unit(s.threshold)
        || !unit(s.scattering) || !s.exposure_ev.is_finite()
        || !(-4.0..=4.0).contains(&s.exposure_ev)
        || !s.hue_deg.is_finite() || !(-180.0..=180.0).contains(&s.hue_deg)
        || !s.saturation.is_finite() || !(-1.0..=1.0).contains(&s.saturation)
        || !s.lightness.is_finite() || !(-1.0..=1.0).contains(&s.lightness) {
        return Err(SETTINGS_ERROR);
    }
    Ok(())
}

fn radii(s: &Settings) -> [usize; 3] {
    let r = s.radius_px as f64;
    let dispersion = 0.25 * s.scattering as f64;
    [(r * (1.0 + dispersion)).ceil() as usize,
     s.radius_px as usize,
     (r * (1.0 - dispersion)).ceil() as usize]
}

/// No allocation, pixel access or externally visible mutation.
pub fn plan(s: &Settings, g: &Geometry, max_work_bytes: u64) -> Result<Plan, i32> {
    validate_settings(s)?;
    if g.struct_bytes != mem::size_of::<Geometry>() as u32 || g.reserved != 0 {
        return Err(ABI_ERROR);
    }
    let tile_n = u64::from(g.tile_width) * u64::from(g.tile_height);
    if g.full_width == 0 || g.full_height == 0 || g.full_width > MAX_EDGE
        || g.full_height > MAX_EDGE
        || u64::from(g.full_width) * u64::from(g.full_height) > MAX_SOURCE_PIXELS
        || g.tile_width == 0 || g.tile_height == 0
        || g.tile_width > MAX_TILE_EDGE || g.tile_height > MAX_TILE_EDGE
        || tile_n > MAX_TILE_PIXELS
        || g.tile_x >= g.full_width || g.tile_y >= g.full_height
        || u64::from(g.tile_x) + u64::from(g.tile_width) > u64::from(g.full_width)
        || u64::from(g.tile_y) + u64::from(g.tile_height) > u64::from(g.full_height) {
        return Err(GEOMETRY_ERROR);
    }
    let halo = if s.strength == 0.0 { 0 } else { radii(s)[0] as u32 };
    let x = g.tile_x.saturating_sub(halo);
    let y = g.tile_y.saturating_sub(halo);
    let right = (g.tile_x + g.tile_width + halo).min(g.full_width);
    let bottom = (g.tile_y + g.tile_height + halo).min(g.full_height);
    let w = right - x;
    let h = bottom - y;
    let region_n = u64::from(w) * u64::from(h);
    let scratch = if s.strength == 0.0 { 0 } else { region_n * CHANNELS as u64 * 8 };
    // Source-region input, two scratch vectors, private result and fixed reserve.
    // Caller-owned destination buffers and retained full assets are host charges.
    let required = region_n * 16 + scratch + tile_n * 20 + FIXED_RESERVE;
    if max_work_bytes == 0 || max_work_bytes > MAX_WORK_BYTES || required > max_work_bytes {
        return Err(BUDGET_ERROR);
    }
    Ok(Plan {
        struct_bytes: mem::size_of::<Plan>() as u32,
        region_x: x, region_y: y, region_width: w, region_height: h,
        halo_px: halo, channels: CHANNELS as u32, reserved: 0,
        input_floats: region_n * 4, output_floats: tile_n * 4,
        coverage_floats: tile_n, scratch_bytes: scratch, required_bytes: required,
    })
}

fn zeroed(n: usize) -> Result<Vec<f32>, i32> {
    let mut v = Vec::new();
    v.try_reserve_exact(n).map_err(|_| ALLOCATION_ERROR)?;
    v.resize(n, 0.0);
    Ok(v)
}

fn poll(cancelled: &mut impl FnMut() -> bool) -> Result<(), i32> {
    if cancelled() { Err(CANCELLED) } else { Ok(()) }
}

fn validate_pixels(src: &[f32], width: usize, cancelled: &mut impl FnMut() -> bool) -> Result<(), i32> {
    for row in src.chunks_exact(width * 4) {
        poll(cancelled)?;
        for p in row.chunks_exact(4) {
            if !unit(p[3]) || p[..3].iter().any(|v| !v.is_finite() || *v < 0.0 || *v > p[3]) {
                return Err(PIXEL_ERROR);
            }
        }
    }
    Ok(())
}

fn selection(c: [f64; 3], threshold: f32) -> f64 {
    let y = (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]).clamp(0.0, 1.0);
    let t = threshold as f64;
    if t == 1.0 { return if y == 1.0 { 1.0 } else { 0.0 }; }
    let q = ((y - t) / (1.0 - t).min(0.10)).clamp(0.0, 1.0);
    q * q * (3.0 - 2.0 * q)
}

fn pass_radius(reach: usize, pass: usize) -> usize { (reach + pass) / 3 }

/// Sliding finite box convolution. Clamp-to-image extension is computed at the
/// supplied region edge. Complete total halo ensures region-internal extension
/// cannot influence the requested tile. There is no image-size resampling.
fn blur_axis(src: &[f32], dst: &mut [f32], w: usize, h: usize,
             reaches: [usize; 3], pass: usize, horizontal: bool,
             cancelled: &mut impl FnMut() -> bool) -> Result<(), i32> {
    let (lines, length) = if horizontal { (h, w) } else { (w, h) };
    for line in 0..lines {
        poll(cancelled)?;
        for channel in 0..CHANNELS {
            let r = pass_radius(reaches[channel % 3], pass);
            let index = |at: usize| {
                let (x, y) = if horizontal { (at, line) } else { (line, at) };
                (y * w + x) * CHANNELS + channel
            };
            if r == 0 {
                for at in 0..length { dst[index(at)] = src[index(at)]; }
                continue;
            }
            let mut sum = 0.0f64;
            let mut positive = 0usize;
            for offset in -(r as isize)..=(r as isize) {
                let at = offset.clamp(0, length as isize - 1) as usize;
                let sample = src[index(at)];
                sum += sample as f64;
                positive += usize::from(sample > 0.0);
            }
            let divisor = (2 * r + 1) as f64;
            for at in 0..length {
                // Tiny rolling-sum residue must not turn an empty support into
                // light, particularly before a nonzero HSL lightness edit.
                if positive == 0 { sum = 0.0; }
                // Only harmless roundoff is bounded. All mathematical inputs
                // are nonnegative and each normalized box is at most one.
                let value = sum / divisor;
                if !value.is_finite() || !(-1e-12..=1.0 + 1e-12).contains(&value) {
                    return Err(NUMERIC_ERROR);
                }
                dst[index(at)] = value.clamp(0.0, 1.0) as f32;
                if at + 1 < length {
                    let remove = (at as isize - r as isize).clamp(0, length as isize - 1) as usize;
                    let add = (at + r + 1).min(length - 1);
                    let old = src[index(remove)];
                    let new = src[index(add)];
                    positive -= usize::from(old > 0.0);
                    positive += usize::from(new > 0.0);
                    sum += new as f64 - old as f64;
                }
            }
        }
    }
    Ok(())
}

fn adjusted(v: f64, amount: f64) -> f64 {
    if amount >= 0.0 { v + amount * (1.0 - v) } else { v + amount * v }
}

fn tint(mut c: [f64; 3], s: &Settings) -> [f64; 3] {
    if c.iter().all(|v| *v == 0.0) { return c; }
    if s.exposure_ev != 0.0 {
        let gain = 2.0f64.powf(s.exposure_ev as f64);
        c = c.map(|v| gain * v / (1.0 + (gain - 1.0) * v));
    }
    if s.hue_deg == 0.0 && s.saturation == 0.0 && s.lightness == 0.0 { return c; }
    let high = c[0].max(c[1]).max(c[2]);
    let low = c[0].min(c[1]).min(c[2]);
    let delta = high - low;
    let lightness = (high + low) * 0.5;
    let denominator = 1.0 - (2.0 * lightness - 1.0).abs();
    let saturation = if delta == 0.0 || denominator <= 0.0 { 0.0 } else { delta / denominator };
    let hue = if delta == 0.0 { 0.0 }
        else if high == c[0] { ((c[1] - c[2]) / delta).rem_euclid(6.0) }
        else if high == c[1] { (c[2] - c[0]) / delta + 2.0 }
        else { (c[0] - c[1]) / delta + 4.0 };
    let hue = (hue + s.hue_deg as f64 / 60.0).rem_euclid(6.0);
    let sat = adjusted(saturation.clamp(0.0, 1.0), s.saturation as f64);
    let light = adjusted(lightness, s.lightness as f64);
    let chroma = (1.0 - (2.0 * light - 1.0).abs()) * sat;
    let secondary = chroma * (1.0 - (hue.rem_euclid(2.0) - 1.0).abs());
    let raw = if hue < 1.0 { [chroma, secondary, 0.0] }
        else if hue < 2.0 { [secondary, chroma, 0.0] }
        else if hue < 3.0 { [0.0, chroma, secondary] }
        else if hue < 4.0 { [0.0, secondary, chroma] }
        else if hue < 5.0 { [secondary, 0.0, chroma] }
        else { [chroma, 0.0, secondary] };
    raw.map(|v| v + light - chroma * 0.5)
}

/// Render privately. Input is exactly the region returned by `plan`, read only.
/// The caller, not the core, proves immutable source owner/revision and manages
/// full-image staging. Every error drops private results without publication.
pub fn render(s: &Settings, g: &Geometry, input: &[f32], max_work_bytes: u64,
              cancelled: &mut impl FnMut() -> bool) -> Result<Rendered, i32> {
    let p = plan(s, g, max_work_bytes)?;
    if input.len() as u64 != p.input_floats { return Err(ABI_ERROR); }
    let w = p.region_width as usize;
    let h = p.region_height as usize;
    validate_pixels(input, w, cancelled)?;
    poll(cancelled)?;
    let mut rgba = zeroed(p.output_floats as usize)?;
    let mut coverage = zeroed(p.coverage_floats as usize)?;
    if s.strength == 0.0 {
        rgba.copy_from_slice(input);
        poll(cancelled)?;
        return Ok(Rendered { rgba, coverage });
    }
    let mut a = zeroed(w * h * CHANNELS)?;
    let mut b = zeroed(w * h * CHANNELS)?;
    for y in 0..h {
        poll(cancelled)?;
        for x in 0..w {
            let offset = y * w + x;
            let src = &input[offset * 4..offset * 4 + 4];
            let alpha = src[3] as f64;
            let c = if alpha == 0.0 { [0.0; 3] } else {
                [src[0] as f64 / alpha, src[1] as f64 / alpha, src[2] as f64 / alpha]
            };
            let m = selection(c, s.threshold);
            for channel in 0..3 {
                a[offset * CHANNELS + channel] = (m * src[channel] as f64) as f32;
                a[offset * CHANNELS + channel + 3] = src[channel];
                a[offset * CHANNELS + channel + 6] = src[3];
            }
        }
    }
    let reaches = radii(s);
    for pass in 0..3 {
        blur_axis(&a, &mut b, w, h, reaches, pass, true, cancelled)?;
        blur_axis(&b, &mut a, w, h, reaches, pass, false, cancelled)?;
    }
    let origin_x = (g.tile_x - p.region_x) as usize;
    let origin_y = (g.tile_y - p.region_y) as usize;
    for y in 0..g.tile_height as usize {
        poll(cancelled)?;
        for x in 0..g.tile_width as usize {
            let from = (y + origin_y) * w + x + origin_x;
            let to = y * g.tile_width as usize + x;
            let src = &input[from * 4..from * 4 + 4];
            let alpha = src[3] as f64;
            if alpha == 0.0 {
                rgba[to * 4..to * 4 + 4].copy_from_slice(src);
                continue;
            }
            let c = [src[0] as f64 / alpha, src[1] as f64 / alpha, src[2] as f64 / alpha];
            let m = selection(c, s.threshold);
            let mut halo = [0.0; 3];
            let mut base = [0.0; 3];
            for channel in 0..3 {
                let denominator = a[from * CHANNELS + channel + 6] as f64;
                if denominator > 0.0 {
                    halo[channel] = (a[from * CHANNELS + channel] as f64 / denominator).clamp(0.0, 1.0);
                    base[channel] = (a[from * CHANNELS + channel + 3] as f64 / denominator).clamp(0.0, 1.0);
                } else { base[channel] = c[channel]; }
            }
            let glow = tint(halo, s);
            let veil = glow[0].max(glow[1]).max(glow[2]);
            let k = s.strength as f64;
            for channel in 0..3 {
                let v = c[channel];
                let value = match s.mode {
                    0 => {
                        let delta = glow[channel] - m * v;
                        v + k * delta * if delta >= 0.0 { 1.0 - v } else { v }
                    }
                    1 => {
                        let weight = k * veil;
                        let softened = v + 0.35 * weight * (base[channel] - v);
                        (1.0 - weight) * softened + k * glow[channel]
                    }
                    _ => v + k * glow[channel] * (1.0 - v),
                };
                if !value.is_finite() || !(-1e-12..=1.0 + 1e-12).contains(&value) {
                    return Err(NUMERIC_ERROR);
                }
                let out = (value.clamp(0.0, 1.0) * alpha) as f32;
                rgba[to * 4 + channel] = out;
                coverage[to] = coverage[to].max((out - src[channel]).abs());
            }
            rgba[to * 4 + 3] = src[3];
        }
    }
    poll(cancelled)?;
    Ok(Rendered { rgba, coverage })
}

fn region<T>(address: *const T, length: u64) -> Option<(usize, usize)> {
    let start = address as usize;
    let n = usize::try_from(length).ok()?;
    let bytes = n.checked_mul(mem::size_of::<T>())?;
    if address.is_null() || start % mem::align_of::<T>() != 0 || bytes > isize::MAX as usize {
        return None;
    }
    Some((start, start.checked_add(bytes)?))
}
fn overlap(a: (usize, usize), b: (usize, usize)) -> bool { a.0 < b.1 && b.0 < a.1 }

#[no_mangle]
pub extern "C" fn lrt_light_glow_abi() -> u32 { ABI_VERSION }
#[no_mangle]
pub extern "C" fn lrt_light_glow_math() -> u32 { MATH_IDENTITY }
#[no_mangle]
pub extern "C" fn lrt_light_glow_settings_size() -> u32 { mem::size_of::<Settings>() as u32 }
#[no_mangle]
pub extern "C" fn lrt_light_glow_geometry_size() -> u32 { mem::size_of::<Geometry>() as u32 }
#[no_mangle]
pub extern "C" fn lrt_light_glow_plan_size() -> u32 { mem::size_of::<Plan>() as u32 }

/// # Safety
/// Settings/geometry are readable and stable; output is writable/aligned and
/// disjoint. No pointer, callback or buffer may be freed/mutated concurrently.
#[no_mangle]
pub unsafe extern "C" fn lrt_light_glow_plan(
    settings: *const Settings, geometry: *const Geometry,
    max_work_bytes: u64, output: *mut Plan,
) -> i32 {
    let (Some(s), Some(g), Some(o)) = (region(settings, 1), region(geometry, 1), region(output, 1)) else {
        return ABI_ERROR;
    };
    if overlap(s, g) || overlap(s, o) || overlap(g, o) { return ABI_ERROR; }
    match panic::catch_unwind(|| plan(&*settings, &*geometry, max_work_bytes)) {
        Ok(Ok(value)) => { ptr::write(output, value); 0 },
        Ok(Err(code)) => code,
        Err(_) => PANIC_ERROR,
    }
}

/// # Safety
/// All buffers are valid/aligned for exact supplied lengths and pairwise
/// disjoint (including settings/geometry). Input stays immutable. Callback is
/// synchronous, cannot unwind, reenter or mutate buffers, and its user pointer
/// stays live. Successful output publication consists only of final infallible
/// copies after all validation, allocation, numerical work and cancellation.
#[no_mangle]
pub unsafe extern "C" fn lrt_light_glow_render(
    settings: *const Settings, geometry: *const Geometry,
    input: *const f32, input_floats: u64,
    output: *mut f32, output_floats: u64,
    coverage: *mut f32, coverage_floats: u64,
    max_work_bytes: u64, cancel: Cancel, cancel_user: *mut c_void,
) -> i32 {
    let bounds = [region(settings, 1), region(geometry, 1), region(input, input_floats),
                  region(output, output_floats), region(coverage, coverage_floats)];
    if bounds.iter().any(Option::is_none) { return ABI_ERROR; }
    for i in 0..bounds.len() {
        for j in i + 1..bounds.len() {
            if overlap(bounds[i].unwrap(), bounds[j].unwrap()) { return ABI_ERROR; }
        }
    }
    let result = panic::catch_unwind(panic::AssertUnwindSafe(|| {
        let p = plan(&*settings, &*geometry, max_work_bytes)?;
        if input_floats != p.input_floats || output_floats != p.output_floats
            || coverage_floats != p.coverage_floats { return Err(ABI_ERROR); }
        let src = slice::from_raw_parts(input, input_floats as usize);
        render(&*settings, &*geometry, src, max_work_bytes,
               &mut || cancel.map(|f| f(cancel_user) != 0).unwrap_or(false))
    }));
    match result {
        Ok(Ok(value)) => {
            ptr::copy_nonoverlapping(value.rgba.as_ptr(), output, value.rgba.len());
            ptr::copy_nonoverlapping(value.coverage.as_ptr(), coverage, value.coverage.len());
            0
        }
        Ok(Err(code)) => code,
        Err(_) => PANIC_ERROR,
    }
}

#[cfg(test)]
mod tests;
