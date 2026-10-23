// SPDX-License-Identifier: GPL-3.0-or-later
// Original procedural artistic materials. Not recovered physical illumination.
use std::slice;
fn soft(v:f32, half:f32)->f32 { ((half-v.abs())/0.10).clamp(0.0,1.0) }
fn material(kind:u32,x:f32,y:f32)->f32 {
    match kind {
        0 => soft(x,0.72)*soft(y,0.95)*(0.85+0.15*(x+0.72)/1.44),
        1 => soft(x,0.95)*soft(y,0.95)*((x.abs()-0.10)/0.08).clamp(0.0,1.0)
             *((y.abs()-0.10)/0.08).clamp(0.0,1.0)*(0.80+0.20*(x+0.95)/1.90),
        _ => 0.0,
    }
}
fn inside(x:f32,y:f32,p:&[f32])->bool {
    let n=p.len()/2; let mut hit=false; let mut j=n-1;
    for i in 0..n { let (xi,yi,xj,yj)=(p[2*i],p[2*i+1],p[2*j],p[2*j+1]);
        if ((yi>y)!=(yj>y)) && x < (xj-xi)*(y-yi)/(yj-yi)+xi { hit=!hit; } j=i;
    } hit
}
/// Config: center x/y, measured eye-axis unit x/y, visible iris radius,
/// strength 0..100, horizontal/vertical -100..100, rotation -100..100,
/// flip 0/1. Radius and geometry are observed, never synthesized.
/// Produces additive linear RGB delta, not replacement pixels. No clipping HDR.
pub fn render(w:usize,h:usize, visibility:&[f32], recovery:&[f32], polygon:&[f32], cfg:&[f32],kind:u32)->Result<Vec<f32>, &'static str> {
    let n=w.checked_mul(h).ok_or("size")?;
    if n==0 || n>4_000_000 || visibility.len()!=n || recovery.len()!=n || cfg.len()!=10
        || polygon.len()<6 || polygon.len()>64 || polygon.len()%2!=0 || kind>1 {return Err("shape");}
    if cfg.iter().chain(polygon.iter()).chain(visibility.iter()).chain(recovery.iter()).any(|v| !v.is_finite())
        || visibility.iter().chain(recovery.iter()).any(|v| !(0.0..=1.0).contains(v)) { return Err("finite/range"); }
    if cfg[4]<2.0 || cfg[4]>4096.0 || (cfg[2]*cfg[2]+cfg[3]*cfg[3]-1.0).abs()>0.01
        || !(0.0..=100.0).contains(&cfg[5]) || cfg[6..9].iter().any(|v| !(-100.0..=100.0).contains(v))
        || (cfg[9]!=0.0 && cfg[9]!=1.0) { return Err("configuration"); }
    let mut out=vec![0.;n*3]; if cfg[5]==0.0 {return Ok(out);}
    let a=cfg[8]*std::f32::consts::PI/100.0; let (s,c)=a.sin_cos();
    // Local design: position endpoints move by one measured iris radius;
    // material half-size 0.30 iris radii. Positive vertical follows image-down.
    for y in 0..h {for x in 0..w {
        let i=y*w+x; let px=x as f32; let py=y as f32;
        if visibility[i]==0.0 || recovery[i]==1.0 || !inside(px,py,polygon) {continue;}
        let dx=px-cfg[0]; let dy=py-cfg[1];
        // Also clip to the measured visible iris disk, not imagined whole eye.
        if dx*dx+dy*dy>cfg[4]*cfg[4] {continue;}
        let u=(dx*cfg[2]+dy*cfg[3])/cfg[4]-cfg[6]/100.0;
        let v=(-dx*cfg[3]+dy*cfg[2])/cfg[4]-cfg[7]/100.0;
        let mut tx=(c*u+s*v)/0.30; let ty=(-s*u+c*v)/0.30;
        if cfg[9]==1.0 {tx=-tx;}
        let delta=material(kind,tx,ty)*visibility[i]*(1.0-recovery[i])*cfg[5]/100.0*0.65;
        out[i*3..i*3+3].fill(delta);
    }} Ok(out)
}
#[no_mangle] pub extern "C" fn lrt_eye_light_abi()->u32 {1}
/// Caller owns valid, aligned, disjoint buffers for stated lengths.
/// Entire input is checked before output writes. Max ROI is four million px.
#[no_mangle] pub unsafe extern "C" fn lrt_eye_light_delta(w:usize,h:usize,vis:*const f32,rec:*const f32,poly:*const f32,points:usize,cfg:*const f32,kind:u32,out:*mut f32)->i32 {
    let n=match w.checked_mul(h) {Some(v) if v>0 && v<=4_000_000=>v,_=>return 1};
    if vis.is_null()||rec.is_null()||poly.is_null()||cfg.is_null()||out.is_null()||points<3||points>32 {return 1;}
    match render(w,h,slice::from_raw_parts(vis,n),slice::from_raw_parts(rec,n),slice::from_raw_parts(poly,points*2),slice::from_raw_parts(cfg,10),kind) {
        Ok(delta)=>{std::ptr::copy_nonoverlapping(delta.as_ptr(),out,n*3);0}, Err(_)=>2
    }
}
#[cfg(test)] mod tests {
 use super::*;
 #[test] fn neutral_and_recovery_are_exact_zero() {
  let polygon=[0.,0.,16.,0.,16.,16.,0.,16.]; let mut cfg=[8.,8.,1.,0.,6.,0.,0.,0.,0.,0.];
  assert!(render(16,16,&vec![1.;256],&vec![0.;256],&polygon,&cfg,0).unwrap().iter().all(|x| *x==0.));
  cfg[5]=100.; assert!(render(16,16,&vec![1.;256],&vec![1.;256],&polygon,&cfg,1).unwrap().iter().all(|x| *x==0.));
 }
 #[test] fn finite_and_bounds_fail_closed() {
  assert!(render(1,1,&[f32::NAN],&[0.],&[0.,0.,1.,0.,1.,1.],&[0.;10],0).is_err());
 }
 #[test] fn flip_changes_asymmetric_original_material() {assert_ne!(material(0,0.3,0.),material(0,-0.3,0.));}
}
fn decode(v:f32)->f32 { let a=v.abs(); v.signum()*if a<=0.04045 {a/12.92} else {((a+0.055)/1.055).powf(2.4)} }
fn encode(v:f32)->f32 { let a=v.abs(); v.signum()*if a<=0.0031308 {a*12.92} else {1.055*a.powf(1.0/2.4)-0.055} }
/// Extended working-sRGB transfer, no gamut/HDR clipping. mode 0 decodes;
/// mode 1 returns encoded additive delta relative to the frozen source.
#[no_mangle] pub unsafe extern "C" fn lrt_eye_light_colour(src:*const f32,light:*const f32,count:usize,mode:u32,out:*mut f32)->i32 {
 if src.is_null()||light.is_null()||out.is_null()||count==0||count>192_000_000||mode>1{return 1;}
 let s=slice::from_raw_parts(src,count);let d=slice::from_raw_parts(light,count);
 if s.iter().chain(d.iter()).any(|v| !v.is_finite()){return 2;}
 let mut result=Vec::with_capacity(count);
 for i in 0..count {let value=if mode==0 {decode(s[i])} else if d[i]==0.0 {0.0} else {encode(decode(s[i])+d[i])-s[i]};
  if !value.is_finite(){return 2;} result.push(value);
 }
 std::ptr::copy_nonoverlapping(result.as_ptr(),out,count);0
}
#[cfg(test)] mod colour_tests {
 use super::*;
 #[test] fn extended_srgb_preserves_negative_and_hdr() {
  assert!((decode(0.5)-0.21404114).abs()<0.000001);
  for v in [-0.2f32,0.0,0.5,1.0,2.0] {assert!((encode(decode(v))-v).abs()<0.00001);}
 }
}
