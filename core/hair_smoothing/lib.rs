// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Original dependency-free visible-hair texture kernel.
mod contract;
mod direction;
mod measure;
mod compose;
use contract::{buffer, contained, disjoint, poll, Cancel, Plan, ABI, BUDGET};
use std::ffi::c_void;

#[no_mangle]
pub extern "C" fn lrt_hair_smoothing_abi() -> u32 { 1 }
#[no_mangle]
pub extern "C" fn lrt_hair_smoothing_algorithm() -> u32 { 1 }

/// Allocation-free checked plan: [total-accounted-bytes, retained-bytes, halo].
#[no_mangle]
pub unsafe extern "C" fn lrt_hair_smoothing_plan_v1(width: usize,height: usize,scale: f64,
    values: *mut u64,values_len: usize) -> i32 {
    contained(|| {
        let plan=Plan::new(width,height,scale)?;
        buffer(values,values_len,3)?;
        let result=[plan.required,plan.retained,plan.halo as u64];
        std::ptr::copy_nonoverlapping(result.as_ptr(),values,3); Ok(())
    })
}

#[no_mangle]
pub unsafe extern "C" fn lrt_hair_smoothing_measure_v1(
    rgb: *const f32,rgb_len: usize,target: *const f32,target_len: usize,
    context_weight: *const f32,context_len: usize,protect: *const u8,protect_len: usize,
    width: usize,height: usize,scale: f64,byte_budget: u64,
    output: *mut f32,output_len: usize,eligible: *mut u8,eligible_len: usize,
    counts: *mut u64,counts_len: usize,metrics: *mut f64,metrics_len: usize,
    cancel: Cancel,context: *mut c_void) -> i32 {
    contained(|| {
        let plan=Plan::new(width,height,scale)?; let n=plan.pixels;
        let regions=[buffer(rgb,rgb_len,n.checked_mul(3).ok_or(ABI)?)?,buffer(target,target_len,n)?,
            buffer(context_weight,context_len,n)?,buffer(protect,protect_len,n)?,buffer(output,output_len,n)?,
            buffer(eligible,eligible_len,n)?,buffer(counts,counts_len,4)?,buffer(metrics,metrics_len,2)?];
        disjoint(&regions)?;
        if byte_budget<plan.required { return Err(BUDGET); }
        poll(cancel,context)?;
        let measured=measure::run(std::slice::from_raw_parts(rgb,rgb_len),std::slice::from_raw_parts(target,target_len),
            std::slice::from_raw_parts(context_weight,context_len),std::slice::from_raw_parts(protect,protect_len),scale,plan,cancel,context)?;
        poll(cancel,context)?;
        // All failures and cancellation leave every caller output untouched.
        std::ptr::copy_nonoverlapping(measured.gain.as_ptr(),output,n);
        std::ptr::copy_nonoverlapping(measured.eligible.as_ptr(),eligible,n);
        std::ptr::copy_nonoverlapping(measured.counts.as_ptr(),counts,4);
        std::ptr::copy_nonoverlapping(measured.metrics.as_ptr(),metrics,2); Ok(())
    })
}

#[no_mangle]
pub unsafe extern "C" fn lrt_hair_smoothing_compose_v1(
    current_linear_rgb: *const f32,rgb_len: usize,field: *const f32,field_len: usize,
    width: usize,height: usize,amount: f64,byte_budget: u64,
    output: *mut f32,output_len: usize,cancel: Cancel,context: *mut c_void) -> i32 {
    contained(|| {
        let plan=Plan::new(width,height,1.0)?; let n=plan.pixels;
        let regions=[buffer(current_linear_rgb,rgb_len,n.checked_mul(3).ok_or(ABI)?)?,
            buffer(field,field_len,n)?,buffer(output,output_len,rgb_len)?];
        disjoint(&regions)?;
        // Caller residents, wrapper snapshots, private result, freezing scratch.
        let required=(n as u64).checked_mul(80).and_then(|v| v.checked_add(8*1024*1024)).ok_or(ABI)?;
        if byte_budget<required { return Err(BUDGET); }
        poll(cancel,context)?;
        let pixels=compose::run(std::slice::from_raw_parts(current_linear_rgb,rgb_len),
            std::slice::from_raw_parts(field,field_len),amount,plan,cancel,context)?;
        poll(cancel,context)?;
        std::ptr::copy_nonoverlapping(pixels.as_ptr(),output,rgb_len); Ok(())
    })
}
