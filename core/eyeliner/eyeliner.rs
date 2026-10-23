// SPDX-License-Identifier: GPL-3.0-or-later
// Original observed-lid curves. No downloaded material, hidden geometry or inference.
use std::slice;
#[no_mangle]
pub extern "C" fn lrt_eyeliner_abi()->u32{1}
/// Caller owns aligned, nonoverlapping buffers of declared lengths throughout call.
/// Segments: ax,ay,bx,by,outward nx,ny,widthA,widthB. No extension past endpoints.
#[no_mangle]
pub unsafe extern "C" fn lrt_eyeliner_delta(src:*const f32,support:*const f32,w:usize,h:usize,
    segments:*const f32,n:usize,strength:f32,r:f32,g:f32,b:f32,out:*mut f32)->i32{
    if w==0||h==0||w>32000||h>32000||w.checked_mul(h).map_or(true,|v|v>4_000_000)
        ||n==0||n>32||src.is_null()||support.is_null()||segments.is_null()||out.is_null()
        ||[strength,r,g,b].iter().any(|x|!x.is_finite()||!(0.0..=1.0).contains(x)){return 1;}
    let count=w*h;let src=slice::from_raw_parts(src,count*3);let support=slice::from_raw_parts(support,count);
    let segments=slice::from_raw_parts(segments,n*8);
    if src.iter().chain(support.iter()).any(|x|!x.is_finite()||!(0.0..=1.0).contains(x))
        ||segments.iter().any(|x|!x.is_finite())||segments.chunks_exact(8).any(|s|
            s[6]<0.0||s[7]<0.0||s[6]>4096.0||s[7]>4096.0
            ||((s[4]*s[4]+s[5]*s[5])-1.0).abs()>0.01
            ||(s[2]-s[0]).powi(2)+(s[3]-s[1]).powi(2)<0.0625){return 2;}
    let out=slice::from_raw_parts_mut(out,count*3);let colour=[r,g,b];
    for i in 0..count{
        let x=(i%w) as f32+0.5;let y=(i/w) as f32+0.5;let mut coverage=0.0_f32;
        for s in segments.chunks_exact(8){
            let dx=s[2]-s[0];let dy=s[3]-s[1];let t=((x-s[0])*dx+(y-s[1])*dy)/(dx*dx+dy*dy);
            if !(0.0..=1.0).contains(&t){continue;}
            let distance=(x-s[0]-t*dx)*s[4]+(y-s[1]-t*dy)*s[5];let width=s[6]*(1.0-t)+s[7]*t;
            // Exterior skin only, never paint the observed eyeball interior.
            if width>0.0&&distance>=0.0&&distance<=width{
                let edge=(width-distance).min(1.0).max(0.0);
                coverage=coverage.max(edge*edge*(3.0-2.0*edge));
            }
        }
        let alpha=coverage*support[i]*strength*0.85;
        for c in 0..3{out[3*i+c]=if alpha==0.0{0.0}else{alpha*(colour[c]-src[3*i+c])};}
    }
    0
}
#[cfg(test)]mod tests{
 use super::*;
 // Authored UNRUN: build and execution belong to local Qoder acceptance.
 #[test]fn neutral_exact(){let src=[0.5;3];let mask=[1.];let seg=[0.,0.,1.,0.,0.,1.,1.,1.];let mut out=[9.;3];unsafe{assert_eq!(lrt_eyeliner_delta(src.as_ptr(),mask.as_ptr(),1,1,seg.as_ptr(),1,0.,0.,0.,0.,out.as_mut_ptr()),0);}assert_eq!(out,[0.;3]);}
 #[test]fn invalid_atomic(){let src=[f32::NAN;3];let mask=[1.];let seg=[0.,0.,1.,0.,0.,1.,1.,1.];let mut out=[9.;3];unsafe{assert_eq!(lrt_eyeliner_delta(src.as_ptr(),mask.as_ptr(),1,1,seg.as_ptr(),1,1.,0.,0.,0.,out.as_mut_ptr()),2);}assert_eq!(out,[9.;3]);}
}
