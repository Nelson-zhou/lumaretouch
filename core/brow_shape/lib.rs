// SPDX-License-Identifier: GPL-3.0-or-later
// Original bilateral eyebrow geometry. No third-party algorithm is copied.
use std::slice;
#[no_mangle]
pub extern "C" fn lrt_brow_shape_abi() -> u32 { 1 }
/// Ten input points: upper inner->outer, lower inner->outer. Head-local lateral
/// points toward this person's outer brow, up points toward forehead. Values:
/// thickness, spacing, tilt, arch, position, inner length, outer length.
/// Output is FORWARD content displacement. Caller solves inverse TPS at P+D.
/// All arrays nonoverlapping, lengths exactly 20,2,2,7,20 respectively.
#[no_mangle]
pub unsafe extern "C" fn lrt_brow_shape_controls(
    points: *const f64, outward: *const f64, up: *const f64,
    values: *const f64, output: *mut f64,
) -> i32 {
    if points.is_null() || outward.is_null() || up.is_null() || values.is_null() || output.is_null() { return 1; }
    let p = slice::from_raw_parts(points,20);
    let e = slice::from_raw_parts(outward,2);
    let u = slice::from_raw_parts(up,2);
    let v = slice::from_raw_parts(values,7);
    if p.iter().chain(e.iter()).chain(u.iter()).chain(v.iter()).any(|x| !x.is_finite())
        || v.iter().any(|x| x.abs()>1.) { return 2; }
    let dot = |a: &[f64], b: &[f64]| a[0]*b[0]+a[1]*b[1];
    if (dot(e,e)-1.).abs()>1e-6 || (dot(u,u)-1.).abs()>1e-6 || dot(e,u).abs()>1e-6 { return 3; }
    let mut centers = [[0.;2];5];
    for j in 0..5 { for a in 0..2 { centers[j][a]=(p[2*j+a]+p[2*(j+5)+a])*0.5; } }
    let width = ((centers[4][0]-centers[0][0]).powi(2)+(centers[4][1]-centers[0][1]).powi(2)).sqrt();
    if width<1. { return 4; }
    let center = [centers.iter().map(|c|c[0]).sum::<f64>()/5.,centers.iter().map(|c|c[1]).sum::<f64>()/5.];
    // Positive tilt lowers the outer end, matching the official guide direction.
    let angle = -v[2]*12_f64.to_radians();
    let (sin,cos)=angle.sin_cos();
    let mut result=[0.;20];
    for j in 0..10 {
        let k=j%5; let t=k as f64/4.;
        let relative=[p[2*j]-center[0],p[2*j+1]-center[1]];
        let x=dot(&relative,e); let y=dot(&relative,u);
        let thick=((p[2*j]-centers[k][0])*u[0]+(p[2*j+1]-centers[k][1])*u[1])*0.5*v[0];
        let dx=x*cos-y*sin-x - 0.12*width*v[1]
            - 0.18*width*v[5]*(1.-2.*t).max(0.).powi(3) + 0.18*width*v[6]*(2.*t-1.).max(0.).powi(3);
        let dy=x*sin+y*cos-y + thick + 0.12*width*v[3]*4.*t*(1.-t) + 0.12*width*v[4];
        for a in 0..2 { result[2*j+a]=e[a]*dx+u[a]*dy; }
    }
    slice::from_raw_parts_mut(output,20).copy_from_slice(&result);
    0
}

#[cfg(test)]
mod tests {
    use super::*;
    fn input()->[f64;20] { [0.,2.,10.,3.,20.,4.,30.,3.,40.,2.,0.,-2.,10.,-1.,20.,0.,30.,-1.,40.,-2.] }
    fn run(v:[f64;7])->[f64;20] {
        let p=input();let mut out=[0.;20];
        unsafe { assert_eq!(lrt_brow_shape_controls(p.as_ptr(),[1.,0.].as_ptr(),[0.,1.].as_ptr(),v.as_ptr(),out.as_mut_ptr()),0); }
        out
    }
    #[test] fn zero_is_exact() { assert_eq!(run([0.;7]),[0.;20]); }
    #[test] fn arch_keeps_ends_and_lengths_keep_opposite_half() {
        let mut v=[0.;7];v[3]=1.;let a=run(v);
        for i in [0,4,5,9] {assert_eq!(a[2*i],0.);assert_eq!(a[2*i+1],0.);}
        v=[0.;7];v[5]=1.;let inner=run(v);
        for i in [2,3,4,7,8,9] {assert_eq!(inner[2*i],0.);assert_eq!(inner[2*i+1],0.);}
        assert!(inner[0]<0.);
        v=[0.;7];v[6]=1.;let outer=run(v);
        for i in [0,1,2,5,6,7] {assert_eq!(outer[2*i],0.);assert_eq!(outer[2*i+1],0.);}
        assert!(outer[8]>0.);
    }
    #[test] fn reject_before_any_output_write() {
        let p=input();let v=[f64::NAN;7];let mut out=[7.;20];
        unsafe { assert_ne!(lrt_brow_shape_controls(p.as_ptr(),[1.,0.].as_ptr(),[0.,1.].as_ptr(),v.as_ptr(),out.as_mut_ptr()),0); }
        assert_eq!(out,[7.;20]);
    }
}
