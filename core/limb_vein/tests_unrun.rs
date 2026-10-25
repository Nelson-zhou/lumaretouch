// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. No execution claim.
use super::*;
#[test]
fn zero_amount_preserves_bits() {
    let rgb=[-0.0f32,0.25,1.0];
    let out=apply(&rgb,&[],0.0,None,std::ptr::null_mut()).unwrap();
    assert_eq!(out.iter().map(|v|v.to_bits()).collect::<Vec<_>>(),rgb.iter().map(|v|v.to_bits()).collect::<Vec<_>>());
}
#[test]
fn common_shading_is_inactive_in_lower_half() {
    let rgb=[0.3f32,0.4,0.5]; let gain=[0.08f32;3];
    assert_eq!(apply(&rgb,&gain,0.5,None,std::ptr::null_mut()).unwrap(),rgb);
    let out=apply(&rgb,&gain,1.0,None,std::ptr::null_mut()).unwrap();
    assert!(out.iter().zip(rgb).all(|(a,b)|*a>b));
}
#[test]
fn zero_field_and_highlight_are_identity() {
    let rgb=[0.2f32,0.3,0.4];
    assert_eq!(apply(&rgb,&[0.;3],1.,None,std::ptr::null_mut()).unwrap(),rgb);
    let white=[1.0f32;3];
    assert_eq!(apply(&white,&[0.1;3],1.,None,std::ptr::null_mut()).unwrap(),white);
}
#[test]
fn protected_target_has_no_field() {
    let rgb=vec![0.4f32;9*9*3];let limb=vec![1.0;81];
    let mut target=vec![0.0;81];target[40]=1.0;
    let reference=vec![0.0;81];let mut protect=vec![0u8;81];protect[40]=1;
    let out=measure(&rgb,&limb,&target,&reference,&protect,9,9,2,None,std::ptr::null_mut()).unwrap();
    assert!(out.field.iter().all(|v|*v==0.));assert!(out.eligible.iter().all(|v|*v==0));
}
