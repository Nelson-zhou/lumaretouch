// SPDX-License-Identifier: GPL-3.0-or-later
// Original measured-brow density compositor. No geometry warp or brow removal.
use std::slice;
#[no_mangle]
pub extern "C" fn lrt_brow_makeup_abi()->u32{1}
/// All buffers must be aligned, valid for declared sizes and nonoverlapping.
/// Profile: 8 half-widths, 8 vertical offsets, density, strand frequency, tilt.
#[no_mangle]
pub unsafe extern "C" fn lrt_brow_makeup_delta(src:*const f32,uv:*const f32,support:*const f32,
 count:usize,profile:*const f32,strength:f32,r:f32,g:f32,b:f32,out:*mut f32)->i32{
 if count==0||count>4_000_000||src.is_null()||uv.is_null()||support.is_null()||profile.is_null()||out.is_null()
 ||[strength,r,g,b].iter().any(|x|!x.is_finite()||!(0.0..=1.0).contains(x)){return 1;}
 let src=slice::from_raw_parts(src,count*3);let uv=slice::from_raw_parts(uv,count*2);
 let mask=slice::from_raw_parts(support,count);let p=slice::from_raw_parts(profile,19);
 if src.iter().chain(mask).any(|x|!x.is_finite()||!(0.0..=1.0).contains(x))||uv.iter().any(|x|!x.is_finite())
 ||p.iter().any(|x|!x.is_finite())||p[..8].iter().any(|x|!(0.0..=1.2).contains(x))
 ||p[8..16].iter().any(|x|x.abs()>0.35)||!(0.0..=1.0).contains(&p[16])||!(1.0..=64.0).contains(&p[17])||p[18].abs()>1.0{return 2;}
 let out=slice::from_raw_parts_mut(out,count*3);let colour=[r,g,b];
 for i in 0..count{
  let u=uv[i*2];let v=uv[i*2+1];let mut alpha=0.0;
  if strength>0.0&&mask[i]>0.0&&(0.0..=1.0).contains(&u)&&v.abs()<=1.35{
   let q=u*7.0;let j=(q.floor() as usize).min(6);let t=q-j as f32;
   let width=p[j]*(1.0-t)+p[j+1]*t;let centre=p[j+8]*(1.0-t)+p[j+9]*t;
   if width>0.0{
    let edge=((width-(v-centre).abs())/0.2).clamp(0.0,1.0);
    let feather=edge*edge*(3.0-2.0*edge);
    let strand=(u*p[17]+v*p[18]).fract().abs();
    let hair=(1.0-((strand-0.5).abs()*4.0)).clamp(0.0,1.0);
    alpha=mask[i]*strength*feather*p[16]*(0.35+0.65*hair)*0.85;
   }
  }
  for c in 0..3{out[3*i+c]=if alpha==0.0{0.0}else{alpha*(colour[c]-src[3*i+c])};}
 }
 0
}
#[cfg(test)]mod tests{
 use super::*;
 // Authored UNRUN. Local Qoder must compile and execute these.
 #[test]fn exact_neutral(){let src=[0.5;3];let uv=[0.5,0.];let mask=[1.];let mut p=[0.;19];p[..8].fill(1.);p[16]=0.7;p[17]=24.;let mut out=[9.;3];unsafe{assert_eq!(lrt_brow_makeup_delta(src.as_ptr(),uv.as_ptr(),mask.as_ptr(),1,p.as_ptr(),0.,0.,0.,0.,out.as_mut_ptr()),0);}assert_eq!(out,[0.;3]);}
 #[test]fn invalid_is_atomic(){let src=[f32::NAN;3];let uv=[0.,0.];let mask=[1.];let p=[0.;19];let mut out=[9.;3];unsafe{assert_eq!(lrt_brow_makeup_delta(src.as_ptr(),uv.as_ptr(),mask.as_ptr(),1,p.as_ptr(),1.,0.,0.,0.,out.as_mut_ptr()),2);}assert_eq!(out,[9.;3]);}
}
