// SPDX-License-Identifier: GPL-3.0-or-later
//! Authored synthetic fixtures only. NO test has been executed.
use super::*;
fn scene(w: usize, h: usize) -> Vec<f32> {
    let mut out = vec![0.0; w*h*3];
    for y in 0..h { for x in 0..w {
        let a = (-(((x as f64-38.0)/7.0).powi(2)+((y as f64-40.0)/10.0).powi(2))/2.0).exp();
        let b = (-(((x as f64-88.0)/7.0).powi(2)+((y as f64-40.0)/10.0).powi(2))/2.0).exp();
        let v = (0.45 + 0.25*a - 0.20*b) as f32;
        out[3*(y*w+x)..3*(y*w+x)+3].fill(v);
    }}
    out
}
#[test]
fn facial_sculpt_neutral_is_exact_zero() {
    let n=81*81; let mut out=vec![9.0;n];
    assert_eq!(field_into(&vec![0.4;n*3],&vec![1.0;n],&vec![1.0;n],81,81,0.0,0.0,3,&mut out,||false),Ok(()));
    assert!(out.iter().all(|v| v.to_bits()==0));
}
#[test]
fn facial_sculpt_flat_source_cannot_invent_structure() {
    let n=81*81; let mut out=vec![9.0;n];
    field_into(&vec![0.4;n*3],&vec![1.0;n],&vec![1.0;n],81,81,1.0,1.0,3,&mut out,||false).unwrap();
    assert!(out.iter().all(|v| *v==0.0));
}
#[test]
fn facial_sculpt_two_independent_source_signs() {
    let (w,h)=(129,81); let n=w*h; let source=scene(w,h); let support=vec![1.0;n];
    let mut hi=vec![0.0;n]; let mut sh=vec![0.0;n];
    field_into(&source,&support,&support,w,h,1.0,0.0,3,&mut hi,||false).unwrap();
    field_into(&source,&support,&support,w,h,0.0,1.0,3,&mut sh,||false).unwrap();
    assert!(hi.iter().any(|v| *v>0.0)); assert!(hi.iter().all(|v| *v>=0.0 && *v<=0.24));
    assert!(sh.iter().any(|v| *v<0.0)); assert!(sh.iter().all(|v| *v<=0.0 && *v>=-0.24));
    assert!(hi[40*w+38]>0.0); assert!(sh[40*w+88]<0.0);
}
#[test]
fn facial_sculpt_protected_pixels_and_bounded_strength() {
    let (w,h)=(129,81); let n=w*h; let source=scene(w,h); let support=vec![1.0;n];
    let mut target=vec![1.0;n]; for x in 30..45 {target[40*w+x]=0.0;}
    let mut half=vec![0.0;n]; let mut full=vec![0.0;n];
    field_into(&source,&support,&target,w,h,0.5,0.5,3,&mut half,||false).unwrap();
    field_into(&source,&support,&target,w,h,1.0,1.0,3,&mut full,||false).unwrap();
    for i in 0..n { if target[i]==0.0 {assert_eq!(full[i],0.0);} assert!((full[i]-2.0*half[i]).abs()<1e-7); }
}
#[test]
fn facial_sculpt_errors_do_not_publish() {
    let n=81*81; let mut source=vec![0.4;n*3]; let mut out=vec![7.0;n]; let support=vec![1.0;n];
    source[100]=f32::NAN;
    assert_eq!(field_into(&source,&support,&support,81,81,1.0,1.0,3,&mut out,||false),Err(3));
    assert!(out.iter().all(|v| *v==7.0)); source[100]=0.4;
    assert_eq!(field_into(&source,&support,&support,81,81,1.0,1.0,3,&mut out,||true),Err(4));
    assert!(out.iter().all(|v| *v==7.0));
}
#[test]
fn facial_sculpt_no_unreviewed_measurement_or_hdr() {
    let n=81*81; let mut out=vec![7.0;n]; let source=vec![0.4;n*3];
    assert_eq!(field_into(&source,&vec![0.0;n],&vec![1.0;n],81,81,1.0,1.0,3,&mut out,||false),Err(3));
    let mut hdr=source; hdr[0]=1.1;
    assert_eq!(field_into(&hdr,&vec![1.0;n],&vec![1.0;n],81,81,0.0,0.0,3,&mut out,||false),Err(3));
    assert!(out.iter().all(|v| *v==7.0));
}
