// SPDX-License-Identifier: GPL-3.0-or-later
// Original head-local mouth control math. No commercial solver or texture model.
use std::slice;
#[no_mangle]
pub extern "C" fn lrt_mouth_shape_abi() -> u32 { 1 }
/// points n*2; roles n*4: upper outer, lower outer, upper inner, corner.
/// frame: right(2), up(2), center(2), width, upper thickness, lower thickness,
/// observed central aperture. values: size,width,down,right,M,tilt,upper,lower,
/// gummy(person-left),gummy(person-right). Gummy values are [0,1], never reverse.
/// Positive tilt is clockwise in the image's head-local right/down plane. The
/// official guide repeats one sign, so this choice is OUR policy, not its claim.
/// Caller owns valid arrays; output is untouched on error. No image synthesis.
#[no_mangle]
pub unsafe extern "C" fn lrt_mouth_shape_controls(
    points: *const f64, roles: *const f64, count: usize, frame: *const f64,
    values: *const f64, output: *mut f64,
) -> i32 {
    if count == 0 || count > 256 || points.is_null() || roles.is_null()
        || frame.is_null() || values.is_null() || output.is_null() { return 1; }
    let p = slice::from_raw_parts(points, count * 2);
    let roles = slice::from_raw_parts(roles, count * 4);
    let f = slice::from_raw_parts(frame, 10);
    let v = slice::from_raw_parts(values, 10);
    if p.iter().chain(roles).chain(f).chain(v).any(|x| !x.is_finite())
        || roles.iter().any(|x| *x < 0. || *x > 1.)
        || v.iter().any(|x| x.abs() > 1.) || v[8] < 0. || v[9] < 0. { return 2; }
    if (f[0]*f[0]+f[1]*f[1]-1.).abs() > 1e-6
        || (f[2]*f[2]+f[3]*f[3]-1.).abs() > 1e-6
        || (f[0]*f[2]+f[1]*f[3]).abs() > 1e-6
        || f[6] < 24. || f[7] <= 0. || f[8] <= 0. || f[9] < 0. { return 3; }
    if (v[8] > 0. || v[9] > 0.) && f[9] < 2. { return 4; }
    let mut out = vec![0.; count * 2];
    let angle = v[5] * 0.10;
    for j in 0..count {
        let rx = p[2*j]-f[4]; let ry = p[2*j+1]-f[5];
        let x = rx*f[0]+ry*f[1]; let y = rx*f[2]+ry*f[3];
        let u = (x/(f[6]*0.5)).clamp(-1.,1.);
        let envelope = (1.-u*u).max(0.);
        let upper = roles[4*j]; let lower = roles[4*j+1];
        let inner_upper = roles[4*j+2]; let corner = roles[4*j+3];
        // Width and whole-mouth size are distinct. Tilt is a rigid rotation.
        let sx = x*(1.+0.12*v[0]+0.16*v[1]);
        let sy = y*(1.+0.12*v[0]);
        let dx = sx*angle.cos()+sy*angle.sin()-x + 0.06*f[6]*v[3];
        let mut dy = -sx*angle.sin()+sy*angle.cos()-y - 0.06*f[6]*v[2];
        // Thickness moves only outer vermilion, retaining the inner aperture.
        dy += envelope*(0.32*f[7]*v[6]*upper-0.32*f[8]*v[7]*lower);
        // M is an upper contour/bead operation, not the old corner-only smile.
        // Left strengthens cupid peaks and bead; right flattens them slightly.
        let peaks = (-((u.abs()-0.27)/0.18).powi(2)).exp();
        let bead = (-(u/0.22).powi(2)).exp();
        dy -= v[4]*(0.20*f[7]*peaks*upper - 0.16*f[7]*bead*inner_upper
                    + 0.012*f[6]*corner);
        // Viewer-right is person-left. Smoothly blend at the philtrum; no seam.
        let left_mix = 0.5+0.5*(u/0.25).clamp(-1.,1.);
        let gummy = v[8]*left_mix+v[9]*(1.-left_mix);
        dy -= gummy*envelope*(0.045*f[6]).min(0.35*f[9])*(upper+inner_upper);
        if dx.hypot(dy) > 0.28*f[6] { return 5; }
        out[2*j] = dx*f[0]+dy*f[2]; out[2*j+1] = dx*f[1]+dy*f[3];
    }
    if out.iter().any(|x| !x.is_finite()) { return 6; }
    slice::from_raw_parts_mut(output, count * 2).copy_from_slice(&out);
    0
}

#[cfg(test)]
mod tests {
    use super::*;
    fn frame() -> [f64;10] { [1.,0.,0.,-1.,50.,50.,60.,6.,8.,12.] }
    fn run(v:[f64;10], point:[f64;2], role:[f64;4]) -> [f64;2] {
        let mut out=[0.;2];
        unsafe { assert_eq!(lrt_mouth_shape_controls(point.as_ptr(),role.as_ptr(),1,
            frame().as_ptr(),v.as_ptr(),out.as_mut_ptr()),0); }
        out
    }
    #[test]
    fn neutral_is_exact() { assert_eq!(run([0.;10],[50.,40.],[1.,0.,0.,0.]),[0.;2]); }
    #[test]
    fn positive_vertical_is_down() {
        let mut v=[0.;10];v[2]=1.;
        let d=run(v,[50.,40.],[1.,0.,0.,0.]);assert_eq!(d[0],0.);assert!((d[1]-3.6).abs()<1e-12);
    }
    #[test]
    fn width_does_not_scale_height() {
        let mut v=[0.;10];v[1]=1.;
        let d=run(v,[60.,40.],[1.,0.,0.,0.]);assert!(d[0]>0.);assert_eq!(d[1],0.);
    }
    #[test]
    fn upper_thickness_does_not_move_inner_or_lower() {
        let mut v=[0.;10];v[6]=1.;
        assert!(run(v,[50.,40.],[1.,0.,0.,0.])[1]<0.);
        assert_eq!(run(v,[50.,46.],[0.,0.,1.,0.]),[0.;2]);
        assert_eq!(run(v,[50.,60.],[0.,1.,0.,0.]),[0.;2]);
    }
    #[test]
    fn gummy_only_lowers_upper_ring() {
        let mut v=[0.;10];v[8]=1.;v[9]=1.;
        assert!(run(v,[50.,40.],[1.,0.,0.,0.])[1]>0.);
        assert!(run(v,[50.,46.],[0.,0.,1.,0.])[1]>0.);
        assert_eq!(run(v,[50.,60.],[0.,1.,0.,0.]),[0.;2]);
    }
    #[test]
    fn left_m_lip_has_bead_and_cupid_not_only_corners() {
        let mut v=[0.;10];v[4]=-1.;
        assert!(run(v,[50.,46.],[0.,0.,1.,0.])[1]>0.);
        assert!(run(v,[58.1,40.],[1.,0.,0.,0.])[1]<0.);
        assert!(run(v,[80.,50.],[0.,0.,0.,1.])[1]<0.);
    }
    #[test]
    fn invalid_gummy_preserves_output() {
        let mut v=[0.;10];v[8]=-0.1;let mut out=[7.;2];
        unsafe { assert_ne!(lrt_mouth_shape_controls([50.,40.].as_ptr(),[1.,0.,0.,0.].as_ptr(),1,
            frame().as_ptr(),v.as_ptr(),out.as_mut_ptr()),0); }
        assert_eq!(out,[7.;2]);
    }
}
