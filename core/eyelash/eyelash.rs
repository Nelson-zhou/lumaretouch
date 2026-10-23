// SPDX-License-Identifier: GPL-3.0-or-later
// Original tapered procedural lash-fibre rasterization; not eyeliner coverage.
use std::slice;
#[no_mangle]
pub extern "C" fn lrt_eyelash_abi()->u32{1}
/// Caller owns aligned, valid, nonoverlapping buffers throughout this call.
/// Segments: ax, ay, bx, by, root radius, tip radius. All prevalidated before write.
#[no_mangle]
pub unsafe extern "C" fn lrt_eyelash_delta(src:*const f32,support:*const f32,w:usize,h:usize,
 segments:*const f32,n:usize,strength:f32,r:f32,g:f32,b:f32,out:*mut f32)->i32{
 if w==0||h==0||w>32000||h>32000||w.checked_mul(h).map_or(true,|v|v>4_000_000)
 ||n==0||n>1024||src.is_null()||support.is_null()||segments.is_null()||out.is_null()
 ||[strength,r,g,b].iter().any(|x|!x.is_finite()||!(0.0..=1.0).contains(x)){return 1;}
 let count=w*h;let src=slice::from_raw_parts(src,count*3);let support=slice::from_raw_parts(support,count);
 let segments=slice::from_raw_parts(segments,n*6);
 if src.iter().chain(support.iter()).any(|x|!x.is_finite()||!(0.0..=1.0).contains(x))
 ||segments.iter().any(|x|!x.is_finite())||segments.chunks_exact(6).any(|s|
 s[..4].iter().any(|v|v.abs()>64000.0)||s[4]<0.0||s[5]<0.0||s[4]>1024.0||s[5]>1024.0
 ||(s[2]-s[0]).powi(2)+(s[3]-s[1]).powi(2)<0.000001){return 2;}
 let out=slice::from_raw_parts_mut(out,count*3);let colour=[r,g,b];
 for i in 0..count{
  let x=(i%w) as f32+0.5;let y=(i/w) as f32+0.5;let mut coverage=0.0_f32;
  for s in segments.chunks_exact(6){
   let dx=s[2]-s[0];let dy=s[3]-s[1];let t=(((x-s[0])*dx+(y-s[1])*dy)/(dx*dx+dy*dy)).clamp(0.0,1.0);
   let distance=((x-s[0]-t*dx).powi(2)+(y-s[1]-t*dy).powi(2)).sqrt();let radius=s[4]*(1.0-t)+s[5]*t;
   let edge=(radius+0.5-distance).clamp(0.0,1.0);coverage=coverage.max(edge*edge*(3.0-2.0*edge));
  }
  let alpha=coverage*support[i]*strength*0.92;
  for c in 0..3{out[3*i+c]=if alpha==0.0{0.0}else{alpha*(colour[c]-src[3*i+c])};}
 }
 0
}
#[cfg(test)]mod tests{
 use super::*;
 // Authored UNRUN. Qoder local acceptance owns build and execution.
 #[test]fn neutral_exact(){let src=[0.5;3];let mask=[1.];let seg=[0.,0.,1.,1.,1.,0.];let mut out=[9.;3];unsafe{assert_eq!(lrt_eyelash_delta(src.as_ptr(),mask.as_ptr(),1,1,seg.as_ptr(),1,0.,0.,0.,0.,out.as_mut_ptr()),0);}assert_eq!(out,[0.;3]);}
 #[test]fn invalid_atomic(){let src=[f32::NAN;3];let mask=[1.];let seg=[0.,0.,1.,1.,1.,0.];let mut out=[9.;3];unsafe{assert_eq!(lrt_eyelash_delta(src.as_ptr(),mask.as_ptr(),1,1,seg.as_ptr(),1,1.,0.,0.,0.,out.as_mut_ptr()),2);}assert_eq!(out,[9.;3]);}
}
