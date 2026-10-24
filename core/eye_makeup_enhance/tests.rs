// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Synthetic contracts, never photographic acceptance.
use super::*;
fn fixture() -> (Vec<f32>,Vec<f32>,Vec<f32>,Vec<f32>) {
    let n=64*64;let mut src=vec![0.0;n*3];let mut mask=vec![0.0;n];let mut a=vec![0.0;n];let mut b=vec![0.0;n];
    for y in 0..64 {for x in 0..64 {let i=y*64+x;let in_target=(20..44).contains(&x)&&(20..44).contains(&y);
        src[3*i..3*i+3].copy_from_slice(if in_target {&[0.4,0.25,0.35]} else {&[0.6,0.5,0.45]});
        if in_target {mask[i]=1.0;}
        if (4..12).contains(&x)&&(20..44).contains(&y) {a[i]=1.0;}
        if (52..60).contains(&x)&&(20..44).contains(&y) {b[i]=1.0;}
    }}
    (src,mask,a,b)
}
#[test]
fn neutral_exact_even_signed_zero() {
    let (mut src,mask,a,b)=fixture();src[0]=-0.0;
    let mut out=vec![9.0;src.len()];
    assert_eq!(apply_into(&src,&mask,&a,&b,64,64,[0.0;4],1,&mut out,||false),Ok(()));
    assert!(out.iter().zip(src).all(|(a,b)|a.to_bits()==b.to_bits()));
}
#[test]
fn independent_brightness_and_saturation_preserve_protected() {
    let(src,mask,a,b)=fixture();let centre=(32*64+32)*3;
    for controls in [[0.0,0.0,0.5,0.0],[0.0,0.5,0.0,0.0],[0.0,-0.5,0.0,0.0]] {
        let mut out=vec![9.0;src.len()];assert_eq!(apply_into(&src,&mask,&a,&b,64,64,controls,1,&mut out,||false),Ok(()));
        for i in 0..mask.len() {if mask[i]==0.0 {assert_eq!(&out[i*3..i*3+3],&src[i*3..i*3+3]);}}
        let before=lab([src[centre],src[centre+1],src[centre+2]]);let after=lab([out[centre],out[centre+1],out[centre+2]]);
        if controls[2]>0.0 {assert!(after[0]>before[0]);}
        if controls[1]>0.0 {assert!(after[1].hypot(after[2])>before[1].hypot(before[2]));}
        if controls[1]<0.0 {assert!(after[1].hypot(after[2])<before[1].hypot(before[2]));}
    }
}
#[test]
fn fade_and_enhance_measured_residual_not_replacement() {
    let(src,mask,a,b)=fixture();let c=(32*64+32)*3;
    let clean=lab([0.6,0.5,0.45]);let distance=|p:Lab|((p[0]-clean[0]).powi(2)+(p[1]-clean[1]).powi(2)+(p[2]-clean[2]).powi(2)).sqrt();
    let before=distance(lab([src[c],src[c+1],src[c+2]]));
    for amount in [-1.0,1.0] {let mut out=vec![9.0;src.len()];
        assert_eq!(apply_into(&src,&mask,&a,&b,64,64,[amount,0.0,0.0,0.0],1,&mut out,||false),Ok(()));
        let after=distance(lab([out[c],out[c+1],out[c+2]]));
        if amount<0.0 {assert!(after<before&&after>0.0);}else{assert!(after>before);}
    }
}
#[test]
fn ambiguous_reference_and_missing_reference_are_atomic_refusals() {
    let(mut src,mask,a,b)=fixture();for i in 0..b.len(){if b[i]>0.0{src[3*i..3*i+3].copy_from_slice(&[0.8,0.4,0.3]);}}
    let mut out=vec![9.0;src.len()];assert_eq!(apply_into(&src,&mask,&a,&b,64,64,[1.0,0.0,0.0,0.0],1,&mut out,||false),Err(REFERENCE));
    assert!(out.iter().all(|v|*v==9.0));
    let zeros=vec![0.0;mask.len()];assert_eq!(apply_into(&src,&mask,&zeros,&zeros,64,64,[-1.0,0.0,0.0,0.0],1,&mut out,||false),Err(REFERENCE));
}
#[test]
fn uniform_makeup_cannot_claim_structure() {
    let(src,mask,a,b)=fixture();let mut out=vec![9.0;src.len()];
    assert_eq!(apply_into(&src,&mask,&a,&b,64,64,[0.0,0.0,0.0,1.0],1,&mut out,||false),Err(SUPPORT));
    assert!(out.iter().all(|v|*v==9.0));
}
#[test]
fn cancellation_hdr_and_overlap_never_publish() {
    let(mut src,mask,a,b)=fixture();let mut out=vec![9.0;src.len()];
    assert_eq!(apply_into(&src,&mask,&a,&b,64,64,[0.0,0.0,0.5,0.0],1,&mut out,||true),Err(CANCELLED));
    assert!(out.iter().all(|v|*v==9.0));
    src[0]=1.01;assert_eq!(apply_into(&src,&mask,&a,&b,64,64,[0.0;4],1,&mut out,||false),Err(PIXELS));
    src[0]=0.6;assert_eq!(apply_into(&src,&mask,&mask,&b,64,64,[0.0,0.0,0.5,0.0],1,&mut out,||false),Err(REFERENCE));
    assert!(out.iter().all(|v|*v==9.0));
}
#[test]
fn ffi_rejects_output_alias_before_mutation() {
    let(mut src,mask,a,b)=fixture();let before=src.clone();let pointer=src.as_mut_ptr();
    let code=unsafe{lrt_eye_makeup_enhance_apply_v1(pointer,src.len(),mask.as_ptr(),mask.len(),a.as_ptr(),a.len(),b.as_ptr(),b.len(),
        64,64,0.0,0.0,0.5,0.0,1,pointer,src.len(),None,std::ptr::null_mut())};
    assert_eq!(code,ABI);assert_eq!(src,before);
}
