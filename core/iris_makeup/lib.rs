// SPDX-License-Identifier: GPL-3.0-or-later
//! Original analytic texture families. No assets, ML weights, warp or pupil guess.
use std::slice;
#[no_mangle] pub extern "C" fn lrt_iris_makeup_abi()->u32 {1}
fn texture(id:u32,r:f32,t:f32)->f32 {
    let v=match id {
        0=>(t*43.0+r*11.0).sin()*(t*9.0-r*7.0).cos(), // fine radial amber rays
        1=>(t*71.0+(r*19.0).sin()*2.0).sin(), // bent dense slate fibres
        2=>((t*19.0).sin()*(r*31.0).sin()).abs()*2.0-1.0, // olive crypt lattice
        3=>((t*53.0+r*79.0).sin()*(t*97.0-r*37.0).cos()).powi(3), // honey speckle
        4=>(r*35.0+(t*7.0).sin()*4.0).sin(), // wave-like ocean arcs
        5=>(t*13.0).cos()*(1.0-r).clamp(0.0,1.0)*2.0-0.3, // copper starburst
        6=>(t*29.0+r*18.0).sin()*(t*31.0-r*23.0).sin(), // moss lace interference
        7=>(t*17.0+r*r*41.0).cos(), // violet curved fans
        8=>(r*57.0).cos()*(0.65+0.35*(t*5.0).sin()), // silver concentric bands
        9=>(t*37.0+(t*11.0+r*27.0).sin()*3.0).sin(), // bifurcating chestnut fibres
        _=>((t*23.0).sin().abs()+(r*27.0).cos().abs()-1.0)*1.3, // teal cellular mosaic
    };v.clamp(-1.0,1.0)
}
const COLOURS:[[f32;3];11]=[[0.61,0.40,0.17],[0.34,0.42,0.49],[0.44,0.48,0.24],[0.65,0.47,0.23],[0.22,0.43,0.57],[0.58,0.30,0.18],[0.29,0.43,0.31],[0.43,0.34,0.51],[0.49,0.51,0.53],[0.39,0.24,0.16],[0.23,0.47,0.45]];
/// Caller owns non-overlapping valid slices; all input is checked before output.
#[no_mangle] pub unsafe extern "C" fn lrt_iris_makeup_delta(src:*const f32,uv:*const f32,mask:*const f32,n:usize,id:u32,strength:f32,out:*mut f32)->i32 {
    if src.is_null()||uv.is_null()||mask.is_null()||out.is_null()||n==0||n>32_000_000||id>10||!strength.is_finite()||!(0.0..=1.0).contains(&strength){return 1;}
    let s=slice::from_raw_parts(src,n*3);let coords=slice::from_raw_parts(uv,n*2);let m=slice::from_raw_parts(mask,n);
    if s.iter().any(|v|!v.is_finite()||!(0.0..=1.0).contains(v))||coords.iter().any(|v|!v.is_finite())||m.iter().any(|v|!v.is_finite()||!(0.0..=1.0).contains(v)){return 2;}
    let d=slice::from_raw_parts_mut(out,n*3);d.fill(0.0);
    for i in 0..n {
        if m[i]==0.0||strength==0.0 {continue;}
        let p=&s[i*3..i*3+3];let lum=p[0]*0.2126+p[1]*0.7152+p[2]*0.0722;
        let c=COLOURS[id as usize];let cl=c[0]*0.2126+c[1]*0.7152+c[2]*0.0722;
        let tex=texture(id,coords[i*2],coords[i*2+1]);let a=m[i]*strength*0.34;
        // Source luminance/detail retained, texture only a small bounded additive
        // tint. No spatial resampling and at least 66% original chroma retained.
        for k in 0..3 {let target=(lum+c[k]-cl+tex*0.045).clamp(0.0,1.0);d[i*3+k]=(target-p[k])*a;}
    }0
}
#[cfg(test)] mod tests {
 use super::*;
 #[test] fn distinct_families(){for a in 0..11 {for b in a+1..11 {assert!((0..100).any(|i| (texture(a,0.25+i as f32*0.006,i as f32*0.13)-texture(b,0.25+i as f32*0.006,i as f32*0.13)).abs()>0.01));}}}
 #[test] fn exact_zero(){let s=[0.3f32;6];let uv=[0.5f32;4];let m=[0.0,0.0];let mut out=[9.0;6];assert_eq!(unsafe{lrt_iris_makeup_delta(s.as_ptr(),uv.as_ptr(),m.as_ptr(),2,0,1.0,out.as_mut_ptr())},0);assert_eq!(out,[0.0;6]);}
}
