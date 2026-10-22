// SPDX-License-Identifier: GPL-3.0-or-later
// Original projected 2D controls, no tissue synthesis and no third-party solver.
use std::slice;
#[no_mangle]
pub extern "C" fn lrt_eye_shape_abi() -> u32 { 1 }
/// Forward offsets for inverse TPS interpolation at target = source + offset.
/// frame: outward(2), up(2), eye-center(2), iris-center(2), width, opening-height.
/// roles: iris membership, lower-lid weight; values follow eye_shape_state.KEYS.
/// Caller guarantees valid nonoverlapping array extents. Output is atomic.
#[no_mangle]
pub unsafe extern "C" fn lrt_eye_shape_controls(
    points: *const f64, roles: *const f64, count: usize, frame: *const f64,
    values: *const f64, output: *mut f64,
) -> i32 {
    if count == 0 || count > 256 || points.is_null() || roles.is_null()
        || frame.is_null() || values.is_null() || output.is_null() { return 1; }
    let p = slice::from_raw_parts(points, count * 2);
    let r = slice::from_raw_parts(roles, count * 2);
    let f = slice::from_raw_parts(frame, 10);
    let v = slice::from_raw_parts(values, 10);
    if p.iter().chain(r).chain(f).chain(v).any(|x| !x.is_finite())
        || r.iter().any(|x| *x < 0. || *x > 1.) || v.iter().any(|x| x.abs() > 1.) { return 2; }
    if (f[0]*f[0]+f[1]*f[1]-1.).abs()>1e-6 || (f[2]*f[2]+f[3]*f[3]-1.).abs()>1e-6
        || (f[0]*f[2]+f[1]*f[3]).abs()>1e-6 || f[8]<1. || f[9]<1. { return 3; }
    let mut out = vec![0.; count * 2];
    for j in 0..count {
        let x = (p[2*j]-f[4])*f[0] + (p[2*j+1]-f[5])*f[1];
        let y = (p[2*j]-f[4])*f[2] + (p[2*j+1]-f[5])*f[3];
        let ix = (p[2*j]-f[6])*f[0] + (p[2*j+1]-f[7])*f[1];
        let iy = (p[2*j]-f[6])*f[2] + (p[2*j+1]-f[7])*f[3];
        let inner = (-2.*x/f[8]).clamp(0.,1.).powi(3) * (1.-r[2*j]);
        let outer = (2.*x/f[8]).clamp(0.,1.).powi(3) * (1.-r[2*j]);
        // Size and width/height are intentionally different; height is aperture,
        // position is rigid translation. Positive tilt raises the outer corner.
        let dx = 0.12*v[0]*x + 0.15*v[1]*r[2*j]*ix + 0.16*v[3]*x
            + 0.07*f[8]*v[4] - 0.08*f[8]*v[5]*inner + 0.08*f[8]*v[6]*outer;
        let dy = 0.12*v[0]*y + 0.15*v[1]*r[2*j]*iy + 0.20*v[2]*y
            - 0.16*f[9]*v[7]*r[2*j+1] + 0.12*v[8]*x + 0.08*f[8]*v[9];
        if dx.hypot(dy) > 0.30*f[8] { return 4; }
        out[2*j] = dx*f[0] + dy*f[2];
        out[2*j+1] = dx*f[1] + dy*f[3];
    }
    if out.iter().any(|x| !x.is_finite()) { return 5; }
    slice::from_raw_parts_mut(output, count*2).copy_from_slice(&out);
    0
}

#[cfg(test)]
mod tests {
    use super::*;
    fn controls(v: [f64;10]) -> [f64;12] {
        // Inner/outer corners, lower/upper lid, iris centre and iris rim.
        let points=[-20.,0.,20.,0.,0.,-6.,0.,6.,0.,0.,3.,0.];
        let roles=[0.,0.,0.,0.,0.,1.,0.,0.,1.,0.,1.,0.];
        let frame=[1.,0.,0.,1.,0.,0.,0.,0.,40.,12.];
        let mut out=[0.;12];
        unsafe { assert_eq!(lrt_eye_shape_controls(points.as_ptr(),roles.as_ptr(),6,frame.as_ptr(),v.as_ptr(),out.as_mut_ptr()),0); }
        out
    }
    fn one(key: usize) -> [f64;12] {
        let mut v=[0.;10];v[key]=1.;controls(v)
    }
    #[test] fn neutral_is_exact() { assert_eq!(controls([0.;10]),[0.;12]); }
    #[test] fn every_control_has_distinct_geometry() {
        let outputs:Vec<_>=(0..10).map(one).collect();
        for (i,a) in outputs.iter().enumerate() {
            assert!(a.iter().any(|x| x.abs()>0.));
            for b in &outputs[i+1..] { assert_ne!(a,b); }
        }
    }
    #[test] fn height_is_not_position() {
        let h=one(2);let p=one(9);
        assert!(h[5]<0. && h[7]>0.);
        assert_eq!(h[1],0.);assert_eq!(h[3],0.);
        assert!(p.chunks_exact(2).all(|xy| xy[0]==0. && xy[1]>0.));
    }
    #[test] fn iris_does_not_scale_lids_or_translate_center() {
        let i=one(1);assert_eq!(&i[..10],&[0.;10]);assert!(i[10]>0.);
    }
    #[test] fn tilt_lifts_tail_and_lowers_inner_corner() {
        let i=one(8);assert!(i[1]<0. && i[3]>0.);
    }
    #[test] fn lower_lid_only_goes_down_for_positive() {
        let i=one(7);assert!(i[5]<0.);assert_eq!(i[7],0.);
        assert_eq!(i[1],0.);assert_eq!(i[3],0.);
    }
    #[test] fn rejection_does_not_write() {
        let mut out=[9.;2];let p=[0.;2];let r=[0.;2];
        let frame=[1.,0.,0.,1.,0.,0.,0.,0.,40.,12.];
        unsafe { assert_ne!(lrt_eye_shape_controls(p.as_ptr(),r.as_ptr(),1,frame.as_ptr(),[f64::NAN;10].as_ptr(),out.as_mut_ptr()),0); }
        assert_eq!(out,[9.;2]);
    }
}
