// SPDX-License-Identifier: GPL-3.0-or-later
//! Local finite-support structure tensor; no global signal prefix/carry.
use crate::contract::{allocate, poll, Cancel, Plan, Result, NUMERICS};

#[derive(Clone, Copy, Default)]
pub(crate) struct Direction { pub x: f32, pub y: f32, pub coherence: f32 }

pub(crate) fn linear(value: f64) -> f64 {
    if value <= 0.04045 { value / 12.92 } else { ((value + 0.055) / 1.055).powf(2.4) }
}

pub(crate) fn log_luminance(rgb: &[f32], plan: Plan, cancel: Cancel, context: *mut std::ffi::c_void) -> Result<Vec<f32>> {
    let mut out = allocate(plan.pixels, 0.0_f32)?;
    for y in 0..plan.height {
        poll(cancel, context)?;
        for x in 0..plan.width {
            let i = y * plan.width + x;
            let l = 0.2126 * linear(rgb[3*i] as f64) + 0.7152 * linear(rgb[3*i+1] as f64) + 0.0722 * linear(rgb[3*i+2] as f64);
            let value = l.max(1.0e-8).ln();
            if !value.is_finite() { return Err(NUMERICS); }
            out[i] = value as f32;
        }
    }
    Ok(out)
}

/// Every nonzero gradient uses its exact own center and +/-1 source taps.
/// Tensor rows/columns are direct finite sums, not signal integral differences:
/// outside-owned source values cannot leak through accumulated roundoff.
pub(crate) fn measure(log_y: &[f32], support: &[bool], plan: Plan, cancel: Cancel,
    context: *mut std::ffi::c_void) -> Result<Vec<Direction>> {
    let (w, h, radius) = (plan.width, plan.height, plan.tensor_radius);
    let mut products = allocate(plan.pixels, [0.0_f32; 3])?;
    if w >= 3 && h >= 3 {
        for y in 1..h-1 {
            poll(cancel, context)?;
            for x in 1..w-1 {
                let i = y*w+x;
                if ![i, i-1, i+1, i-w, i+w].iter().all(|&j| support[j]) { continue; }
                let gx = 0.5 * (log_y[i+1] as f64 - log_y[i-1] as f64);
                let gy = 0.5 * (log_y[i+w] as f64 - log_y[i-w] as f64);
                products[i] = [(gx*gx) as f32, (gy*gy) as f32, (gx*gy) as f32];
            }
        }
    }
    let mut horizontal = allocate(plan.pixels, [0.0_f64; 3])?;
    if w > 2*radius {
        for y in 0..h {
            poll(cancel, context)?;
            for x in radius..w-radius {
                let mut sum = [0.0; 3];
                for dx in x-radius..=x+radius {
                    let p = products[y*w+dx];
                    for c in 0..3 { sum[c] += p[c] as f64; }
                }
                horizontal[y*w+x] = sum;
            }
        }
    }
    drop(products);
    let mut output = allocate(plan.pixels, Direction::default())?;
    if w <= 2*radius || h <= 2*radius { return Ok(output); }
    let area = ((2*radius+1)*(2*radius+1)) as f64;
    for y in radius..h-radius {
        poll(cancel, context)?;
        for x in radius..w-radius {
            let mut sum = [0.0_f64; 3];
            for dy in y-radius..=y+radius {
                let p = horizontal[dy*w+x];
                for c in 0..3 { sum[c] += p[c]; }
            }
            let (xx, yy, xy) = (sum[0]/area, sum[1]/area, sum[2]/area);
            let energy = xx+yy;
            if !energy.is_finite() || !xy.is_finite() { return Err(NUMERICS); }
            // Low energy is a truthful absent direction, not invented hair.
            // Very strong source transitions are an engineering veto.
            if !(1.0e-6..=0.25).contains(&energy) { continue; }
            let anisotropy = ((xx-yy)*(xx-yy)+4.0*xy*xy).sqrt();
            let coherence = (anisotropy / (energy+1.0e-12)).clamp(0.0, 1.0);
            let normal_angle = 0.5 * (2.0*xy).atan2(xx-yy);
            output[y*w+x] = Direction { x: -normal_angle.sin() as f32, y: normal_angle.cos() as f32,
                coherence: coherence as f32 };
        }
    }
    Ok(output)
}
