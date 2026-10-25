// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED ONLY: not executed, compiled or accepted.
use super::*;
use std::ptr;

#[test]
fn neutral_preserves_signed_zero_and_does_not_need_field() {
    let rgb=[-0.0f32,0.2,1.0];
    let got=apply(&rgb,&[],0.0,None,ptr::null_mut()).unwrap();
    assert_eq!(got.iter().map(|v|v.to_bits()).collect::<Vec<_>>(),rgb.iter().map(|v|v.to_bits()).collect::<Vec<_>>());
}
#[test]
fn same_plain_fabric_has_no_proposal() {
    let n=16*16;
    let rgb=vec![0.25;n*3]; let g=vec![1.0;n];
    let mut target=vec![0.0;n]; let mut reference=vec![0.0;n];
    for y in 0..16 {for x in 0..16 {if x<4 {reference[y*16+x]=1.0;} else if x>=8 {target[y*16+x]=1.0;}}}
    let m=measure(&rgb,&g,&target,&reference,&vec![0;n],16,16,2,None,ptr::null_mut()).unwrap();
    assert!(m.field.iter().all(|v|*v==0.0)); assert_eq!(m.counts[3],0);
}
#[test]
fn dark_target_gets_bounded_proposal_only_on_target() {
    let (w,h)=(32,16); let n=w*h;
    let mut rgb=vec![0.4;n*3]; let g=vec![1.0;n];
    let mut target=vec![0.0;n]; let mut reference=vec![0.0;n];
    let mut protect=vec![0;n];
    for y in 0..h {for x in 0..w {let i=y*w+x;
        if x<8 {reference[i]=1.0;}
        if x>=16 {target[i]=1.0;rgb[3*i..3*i+3].fill(0.2);}
    }}
    protect[10*w+20]=1;
    let m=measure(&rgb,&g,&target,&reference,&protect,w,h,2,None,ptr::null_mut()).unwrap();
    for i in 0..n {if target[i]==0.0 || protect[i]!=0 {assert_eq!(&m.field[3*i..3*i+3],&[0.0;3]);}}
    assert!(m.field.iter().any(|v|*v>0.0));
    let out=apply(&rgb,&m.field,1.0,None,ptr::null_mut()).unwrap();
    assert!(out.iter().all(|v|v.is_finite() && *v>=0.0 && *v<=1.0));
    assert_eq!(&out[3*(10*w+20)..3*(10*w+20)+3],&rgb[3*(10*w+20)..3*(10*w+20)+3]);
}
#[test]
fn common_headroom_scale_prevents_channel_clip() {
    let out=apply(&[1.0,0.3,0.2],&[0.3,-0.1,0.1],1.0,None,ptr::null_mut()).unwrap();
    assert_eq!(out,vec![1.0,0.3,0.2]);
}
#[test]
fn rejects_overlapping_reference_target() {
    let n=64;let rgb=vec![0.2;n*3];let mask=vec![1.0;n];
    assert_eq!(measure(&rgb,&mask,&mask,&mask,&vec![0;n],8,8,2,None,ptr::null_mut()).err(),Some(2));
}
#[test]
fn ffi_budget_failure_does_not_touch_output() {
    let rgb=[0.2f32;3]; let mut output=[0.7f32;3];
    let status=unsafe{lrt_fabric_sweat_apply_v1(rgb.as_ptr(),3,ptr::null(),0,1,1,0.0,0,output.as_mut_ptr(),3,None,ptr::null_mut())};
    assert_eq!(status,5);assert_eq!(output,[0.7;3]);
}
#[test]
fn ffi_rejects_output_alias_without_touching_input() {
    let mut rgb=[0.2f32;3];
    let status=unsafe{lrt_fabric_sweat_apply_v1(rgb.as_ptr(),3,ptr::null(),0,1,1,0.0,u64::MAX,rgb.as_mut_ptr(),3,None,ptr::null_mut())};
    assert_eq!(status,1); assert_eq!(rgb,[0.2;3]);
}
unsafe extern "C" fn stop(_: *mut c_void)->i32 {1}
#[test]
fn cancelled_work_does_not_publish() {
    let rgb=[0.2f32;3];let mut output=[0.9f32;3];
    let status=unsafe{lrt_fabric_sweat_apply_v1(rgb.as_ptr(),3,ptr::null(),0,1,1,0.0,u64::MAX,output.as_mut_ptr(),3,Some(stop),ptr::null_mut())};
    assert_eq!(status,6);assert_eq!(output,[0.9;3]);
}
