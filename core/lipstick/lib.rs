// SPDX-License-Identifier: GPL-3.0-or-later
// Original analytic lip coverage and source-texture material response. No assets.
use std::slice;
#[no_mangle] pub extern "C" fn lrt_lipstick_abi()->u32 {1}
fn coverage(id:u32,u:f32,v:f32,d:f32)->f32 {
 let x=u.abs().min(1.);let y=v.clamp(-1.,1.);let d=d.clamp(0.,1.);
 match id {
  0=>1.,
  1=>0.15+0.85*(1.-d).powi(2), // cavity-side bloom
  2=>(1.-d*d).max(0.1), // soft outer border
  3=>0.15+0.85*d.powi(3), // perimeter definition
  4=>0.2+0.8*(-5.*u*u).exp(), // central column
  5=>0.25+0.75*((1.-y)*0.5), // upper-biased
  6=>0.25+0.75*((1.+y)*0.5), // lower-biased
  7=>0.2+0.8*(-30.*(x-0.3).powi(2)).exp()*((1.-y)*0.5), // twin cupid peaks
  8=>(1.-x.powi(4)).max(0.05), // corners fade
  9=>0.2+0.8*(y*0.5+0.5).powi(2), // nonlinear vertical ombre
  10=>0.2+0.8*(u.clamp(-1.,1.)*0.5+0.5), // horizontal ombre
  11=>0.2+0.8*(2.*d-1.).powi(2), // two rims, reduced middle
  12=>0.25+0.75*((1.-x*x)*(0.5+0.5*(3.*u).cos())*(1.-0.4*y*y)).max(0.),
  _=>0.
 }
}
/// SAFETY: caller supplies valid aligned immutable input buffers (count*3 RGB/uv,
/// count support/base-luma), and a separate writable count*3 output buffer.
/// All inputs are validated before any write; count bounded against overflow.
#[no_mangle]
pub unsafe extern "C" fn lrt_lipstick_delta(src:*const f32,uv:*const f32,support:*const f32,base:*const f32,
 count:usize,pattern:u32,texture:u32,strength:f32,red:f32,green:f32,blue:f32,out:*mut f32)->i32 {
 if count==0||count>32_000_000||pattern>12||texture>4||src.is_null()||uv.is_null()||support.is_null()||base.is_null()||out.is_null()
  ||[strength,red,green,blue].iter().any(|v|!v.is_finite()||!(0.0..=1.0).contains(v)){return 1;}
 let src=slice::from_raw_parts(src,count*3);let uv=slice::from_raw_parts(uv,count*3);
 let mask=slice::from_raw_parts(support,count);let base=slice::from_raw_parts(base,count);
 if src.iter().chain(mask).chain(base).any(|v|!v.is_finite()||!(0.0..=1.0).contains(v))||uv.iter().any(|v|!v.is_finite()){return 2;}
 let out=slice::from_raw_parts_mut(out,count*3);let tint=[red,green,blue];
 for i in 0..count {
  let a=strength*mask[i]*coverage(pattern,uv[i*3],uv[i*3+1],uv[i*3+2]);
  if a==0. {out[i*3..i*3+3].fill(0.);continue;}
  let y=0.2126*src[i*3]+0.7152*src[i*3+1]+0.0722*src[i*3+2];
  // Highlights respond ONLY to existing positive luminance structure; no noise,
  // painted anatomy or template highlight. Fine source detail remains present.
  let detail=y-base[i];let highlight=(detail*3.).max(0.).min(0.22);
  let (opacity,detail_gain,sheen)=match texture {
   0=>(0.67,0.90,highlight*0.35), // satin
   1=>(0.82,0.80,-highlight*0.35), // matte: attenuate existing sheen
   2=>(0.78,0.60,highlight*0.15), // cream: softer microcontrast
   3=>(0.64,1.00,highlight*0.8),  // pearl: existing fine ridges only
   _=>(0.50,1.05,highlight*1.3)   // water gloss: existing bright detail only
  };
  for c in 0..3 {
   let target=(tint[c]*(0.6+0.4*base[i])+detail*detail_gain+sheen).clamp(0.,1.);
   out[i*3+c]=(target-src[i*3+c])*a*opacity;
  }
 }
 0
}
#[cfg(test)] mod tests {
 use super::*;
 // Authored only; UNRUN under source-only authorization.
 #[test] fn patterns_are_spatially_distinct(){
  for a in 0..13 {for b in a+1..13 {
   assert!((-8..=8).any(|x|(-8..=8).any(|y|(1..9).any(|d|
    (coverage(a,x as f32/8.,y as f32/8.,d as f32/10.)-coverage(b,x as f32/8.,y as f32/8.,d as f32/10.)).abs()>0.01))));
  }}
 }
 #[test] fn zero_strength_exact(){let s=[0.1,0.2,0.3];let uv=[0.,0.,0.5];let m=[1.];let base=[0.2];let mut out=[9.;3];
 unsafe{assert_eq!(lrt_lipstick_delta(s.as_ptr(),uv.as_ptr(),m.as_ptr(),base.as_ptr(),1,0,0,0.,0.1,0.2,0.3,out.as_mut_ptr()),0);} assert_eq!(out,[0.;3]);}
}
