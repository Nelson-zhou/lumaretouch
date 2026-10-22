// SPDX-License-Identifier: GPL-3.0-or-later
// Original pointwise Lab control math. No third-party lip implementation copied.
use std::slice;
#[no_mangle]
pub extern "C" fn lrt_lip_makeup_abi() -> u32 { 1 }
/// Source Lab and measured low/mid-frequency L shading are immutable. Output
/// is a new Lab proposal. No texture gain, geometry or invented highlights.
/// Inputs/outputs must not alias. Validate the entire call before any write.
#[no_mangle]
pub unsafe extern "C" fn lrt_lip_makeup_propose(
    lab: *const f32, shading: *const f32, count: usize,
    saturation: f32, brightness: f32, dimensionality: f32, output: *mut f32,
) -> i32 {
    if count == 0 || count > 32_000_000 || lab.is_null() || shading.is_null() || output.is_null()
        || [saturation,brightness,dimensionality].iter().any(|x| !x.is_finite() || !(-1.0..=1.0).contains(x)) { return 1; }
    let src = slice::from_raw_parts(lab,count*3);
    let shade = slice::from_raw_parts(shading,count);
    let out = slice::from_raw_parts_mut(output,count*3);
    if src.iter().chain(shade.iter()).any(|x| !x.is_finite()) { return 2; }
    if src.chunks_exact(3).any(|p| !(0.0..=100.0).contains(&p[0])
        || p[1].abs()>200.0 || p[2].abs()>200.0)
        || shade.iter().any(|x| x.abs()>20.0) { return 2; }
    for i in 0..count {
        let p=i*3;
        // Brightness is independent of chroma; dimensionality scales measured
        // broad/mid shading only. High-frequency source L is kept at gain one.
        out[p]=(src[p]+10.0*brightness+(0.65*dimensionality*shade[i]).clamp(-10.0,10.0)).clamp(0.0,100.0);
        out[p+1]=src[p+1]*(1.0+0.6*saturation);
        out[p+2]=src[p+2]*(1.0+0.6*saturation);
    }
    0
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn zero_and_separate_controls() {
        let source=[45.,12.,-8.]; let shading=[3.]; let mut out=[0.;3];
        unsafe { assert_eq!(lrt_lip_makeup_propose(source.as_ptr(),shading.as_ptr(),1,0.,0.,0.,out.as_mut_ptr()),0); }
        assert_eq!(source,out);
        unsafe { lrt_lip_makeup_propose(source.as_ptr(),shading.as_ptr(),1,1.,0.,0.,out.as_mut_ptr()); }
        assert_eq!(source[0],out[0]); assert!(out[1]>source[1]);
    }
    #[test] fn reject_before_write() {
        let source=[45.,12.,-8.]; let shading=[f32::NAN]; let mut out=[7.;3];
        unsafe { assert_eq!(lrt_lip_makeup_propose(source.as_ptr(),shading.as_ptr(),1,0.,0.,0.,out.as_mut_ptr()),2); }
        assert_eq!(out,[7.;3]);
    }
}
