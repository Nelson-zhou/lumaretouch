// SPDX-License-Identifier: GPL-3.0-or-later
// Original bounded head-local 2D nose geometry; no commercial solver copied.
use std::slice;
#[no_mangle]
pub extern "C" fn lrt_nose_shape_abi() -> u32 { 1 }
/// points = n*2; roles = n*3 (bridge, wing, tip weights in [0,1]);
/// frame = [right_x,right_y,up_x,up_y,center_x,center_y,tip_x,tip_y,width,height];
/// values = [size,vertical_position,horizontal_position,bridge,wing,tip].
/// Positive horizontal means viewer-right in the unrolled head frame.
/// Forward displacement only; caller solves pullback TPS at points+delta.
/// Caller owns valid, nonoverlapping arrays; n is bounded before dereferencing.
#[no_mangle]
pub unsafe extern "C" fn lrt_nose_shape_controls(
    points:*const f64, roles:*const f64, count:usize, frame:*const f64,
    values:*const f64, output:*mut f64,
)->i32 {
    if count==0||count>256||points.is_null()||roles.is_null()||frame.is_null()||values.is_null()||output.is_null(){return 1;}
    let p=slice::from_raw_parts(points,count*2);let r=slice::from_raw_parts(roles,count*3);
    let f=slice::from_raw_parts(frame,10);let v=slice::from_raw_parts(values,6);
    if p.iter().chain(r).chain(f).chain(v).any(|x|!x.is_finite())
        ||r.iter().any(|x|*x<0.||*x>1.)||v.iter().any(|x|x.abs()>1.){return 2;}
    if (f[0]*f[0]+f[1]*f[1]-1.).abs()>1e-6||(f[2]*f[2]+f[3]*f[3]-1.).abs()>1e-6
        ||(f[0]*f[2]+f[1]*f[3]).abs()>1e-6||f[8]<1.||f[9]<1.{return 3;}
    let mut out=vec![0.;count*2];
    for j in 0..count {
        let rx=p[2*j]-f[4];let ry=p[2*j+1]-f[5];
        let x=rx*f[0]+ry*f[1];let y=rx*f[2]+ry*f[3];
        let tx=p[2*j]-f[6];let ty=p[2*j+1]-f[7];
        let dx=0.12*v[0]*x + 0.08*f[8]*v[2] + 0.18*v[3]*r[3*j]*x + 0.15*v[4]*r[3*j+1]*x
            + 0.15*v[5]*r[3*j+2]*(tx*f[0]+ty*f[1]);
        let dy=0.12*v[0]*y + 0.08*f[9]*v[1] + 0.15*v[5]*r[3*j+2]*(tx*f[2]+ty*f[3]);
        if dx.hypot(dy)>0.28*f[8].max(f[9]) {return 4;}
        out[2*j]=dx*f[0]+dy*f[2];out[2*j+1]=dx*f[1]+dy*f[3];
    }
    if out.iter().any(|x|!x.is_finite()){return 5;}
    slice::from_raw_parts_mut(output,count*2).copy_from_slice(&out);0
}
#[cfg(test)]
mod tests {
    use super::*;
    fn run(v:[f64;6],frame:[f64;10])->[f64;4]{
        let mut out=[0.;4];unsafe{assert_eq!(lrt_nose_shape_controls([8.,8.,12.,12.].as_ptr(),[1.,0.,0.,0.,1.,0.].as_ptr(),2,frame.as_ptr(),v.as_ptr(),out.as_mut_ptr()),0);}out
    }
    fn frame()->[f64;10]{[1.,0.,0.,-1.,10.,10.,10.,12.,20.,30.]}
    #[test]fn zero_is_exact(){assert_eq!(run([0.;6],frame()),[0.;4]);}
    #[test]fn height_is_translation_not_scale(){assert_eq!(run([0.,1.,0.,0.,0.,0.],frame()),[0.,-2.4,0.,-2.4]);}
    #[test]fn horizontal_is_translation(){assert_eq!(run([0.,0.,1.,0.,0.,0.],frame()),[1.6,0.,1.6,0.]);}
    #[test]fn rejects_without_writing(){let mut out=[7.;4];unsafe{assert_ne!(lrt_nose_shape_controls([0.;4].as_ptr(),[0.;6].as_ptr(),2,frame().as_ptr(),[f64::NAN;6].as_ptr(),out.as_mut_ptr()),0);}assert_eq!(out,[7.;4]);}
}
