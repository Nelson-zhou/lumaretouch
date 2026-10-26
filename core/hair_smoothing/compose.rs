// SPDX-License-Identifier: GPL-3.0-or-later
//! CURRENT linear RGB only: one common gain preserves chromatic ratios.
use crate::contract::{allocate, poll, Cancel, Plan, Result, INPUT, MAX_LOG_GAIN, NUMERICS};

pub(crate) fn run(rgb: &[f32], field: &[f32], amount: f64, plan: Plan, cancel: Cancel,
    context: *mut std::ffi::c_void) -> Result<Vec<f32>> {
    if !amount.is_finite() || !(0.0..=1.0).contains(&amount) { return Err(INPUT); }
    let mut output=allocate(rgb.len(),0.0_f32)?;
    for y in 0..plan.height {
        poll(cancel,context)?;
        for x in 0..plan.width {
            let i=y*plan.width+x; let current=&rgb[3*i..3*i+3]; let value=field[i] as f64;
            if !current.iter().all(|v| v.is_finite() && (0.0..=1.0).contains(v))
                || !value.is_finite() || value.abs()>MAX_LOG_GAIN { return Err(INPUT); }
            if amount==0.0 || value==0.0 {
                output[3*i..3*i+3].copy_from_slice(current); continue;
            }
            let peak=current.iter().fold(0.0_f64,|a,&b| a.max(b as f64));
            if peak==0.0 { output[3*i..3*i+3].copy_from_slice(current); continue; }
            let gain=(amount*value).exp().min(1.0/peak);
            if !gain.is_finite() || gain<=0.0 { return Err(NUMERICS); }
            if gain==1.0 { output[3*i..3*i+3].copy_from_slice(current); continue; }
            for channel in 0..3 {
                let value=(current[channel] as f64*gain) as f32;
                if !value.is_finite() || !(0.0..=1.0).contains(&value) { return Err(NUMERICS); }
                // No channel-specific clamp, no source RGB or chroma donor.
                output[3*i+channel]=value;
            }
        }
    }
    poll(cancel,context)?; Ok(output)
}
