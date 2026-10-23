// SPDX-License-Identifier: GPL-3.0-or-later
// Original Lumaretouch compact-support cheek lobe compositor, no copied assets.
use std::slice;
#[no_mangle]
pub extern "C" fn lrt_blush_makeup_abi() -> u32 { 1 }
/// SAFETY: all pointers must address initialized aligned nonoverlapping buffers
/// of the declared lengths, owned by the caller throughout this call. Sources,
/// coordinates and coverage are immutable; output is separate. 6 floats/lobe:
/// center u,v, radii u,v, rotation radians, gain. Coordinates already orient each
/// measured cheek outward, making the same original design bilateral.
#[no_mangle]
pub unsafe extern "C" fn lrt_blush_makeup_delta(
    src: *const f32, uv: *const f32, support: *const f32, count: usize,
    lobes: *const f32, lobe_count: usize, strength: f32,
    red: f32, green: f32, blue: f32, output: *mut f32,
) -> i32 {
    if count==0 || count>32_000_000 || lobe_count==0 || lobe_count>8
        || src.is_null() || uv.is_null() || support.is_null() || lobes.is_null() || output.is_null()
        || !strength.is_finite() || !(0.0..=1.0).contains(&strength)
        || [red,green,blue].iter().any(|v| !v.is_finite() || !(0.0..=1.0).contains(v)) {return 1;}
    let src=slice::from_raw_parts(src,count*3);
    let uv=slice::from_raw_parts(uv,count*2);
    let support=slice::from_raw_parts(support,count);
    let lobes=slice::from_raw_parts(lobes,lobe_count*6);
    if src.iter().chain(support.iter()).any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
        || uv.iter().chain(lobes.iter()).any(|v| !v.is_finite())
        || lobes.chunks_exact(6).any(|l| l[2]<=0.0 || l[3]<=0.0 || l[2]>2.0 || l[3]>2.0 || !(0.0..=1.0).contains(&l[5])) {return 2;}
    let output=slice::from_raw_parts_mut(output,count*3);
    let tint=[red,green,blue];
    let tint_y=0.2126*red+0.7152*green+0.0722*blue;
    for i in 0..count {
        let mut shape=0.0_f32;
        if strength>0.0 && support[i]>0.0 {
            for l in lobes.chunks_exact(6) {
                let x=uv[2*i]-l[0];let y=uv[2*i+1]-l[1];let (s,c)=l[4].sin_cos();
                let r2=((x*c+y*s)/l[2]).powi(2)+((-x*s+y*c)/l[3]).powi(2);
                // Compact smooth falloff, exactly zero outside the original lobe.
                shape=shape.max((1.0-r2).max(0.0).powi(2)*l[5]);
            }
        }
        let amount=shape*support[i]*strength*0.32;
        let source_y=0.2126*src[3*i]+0.7152*src[3*i+1]+0.0722*src[3*i+2];
        for c in 0..3 {
            // Add bounded tint chroma and a gentle encoded-luma tint. Neutral
            // black/grey/white swatches remain real selectable colours. Most
            // source texture stays at gain one (luma gain >=0.92). Gamut
            // bounds constrain ONLY this contribution; untouched HDR input is
            // handled by host working-space admission, never quantized here.
            let d=amount*((tint[c]-tint_y)+0.25*(tint_y-source_y));
            output[3*i+c]=if amount==0.0 {0.0} else {d.clamp(-0.16,0.16).clamp(-src[3*i+c],1.0-src[3*i+c])};
        }
    }
    0
}
#[cfg(test)]
mod tests {
    use super::*;
    // Authored, UNRUN. No test/build was executed during the source-only task.
    #[test] fn neutral_and_no_support_are_exact() {
        let src=[0.12345,0.56789,0.9];let uv=[0.,0.];let support=[1.];let lobes=[0.,0.,1.,1.,0.,1.];let mut out=[9.;3];
        unsafe {assert_eq!(lrt_blush_makeup_delta(src.as_ptr(),uv.as_ptr(),support.as_ptr(),1,lobes.as_ptr(),1,0.,0.8,0.3,0.4,out.as_mut_ptr()),0);}
        assert_eq!(out,[0.;3]);
    }
    #[test] fn invalid_is_atomic() {
        let src=[f32::NAN,0.5,0.5];let uv=[0.,0.];let support=[1.];let lobes=[0.,0.,1.,1.,0.,1.];let mut out=[9.;3];
        unsafe {assert_eq!(lrt_blush_makeup_delta(src.as_ptr(),uv.as_ptr(),support.as_ptr(),1,lobes.as_ptr(),1,1.,0.8,0.3,0.4,out.as_mut_ptr()),2);}
        assert_eq!(out,[9.;3]);
    }
}
