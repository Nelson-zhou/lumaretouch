// SPDX-License-Identifier: AGPL-3.0-only
// Copyright Chris Cork. Adapted for LumaRetouch, 2026-10-25. See NOTICE/LICENSE.
//! AUTHORED / UNRUN synthetic numerical fixtures; not photographic acceptance.
use super::*;
fn full(n: usize) -> Rect { Rect { y:0,x:0,h:n,w:n } }
fn run(rgb: &[f32], n: usize, weight: &[f32], protect: &[u8]) -> Measurement {
    measure_inner(rgb,weight,protect,n,n,full(n),2.0,MAX_BYTES,&mut || false).unwrap()
}
fn valley(n: usize) -> Vec<f32> {
    let mut rgb=vec![0.0;3*n*n];
    for y in 0..n { for x in 0..n {
        let d=y as f64-(n/2) as f64;
        let value=(0.58-0.11*(-d*d/(2.0*2.0_f64.powi(2))).exp()) as f32;
        for c in 0..3 { rgb[3*(y*n+x)+c]=value; }
    }} rgb
}
#[test]
fn dependency_is_composed_not_largest_filter() {
    let p=policy(2.0).unwrap();
    assert_eq!(p.radius,27);
    assert!(p.radius>p.smooth && p.radius>2*p.close);
    assert!(policy(1.39).is_err()); assert!(policy(f64::NAN).is_err());
}
#[test]
fn flat_is_success_with_context_but_no_signal() {
    let n=128; let m=run(&vec![0.5;3*n*n],n,&vec![1.0;n*n],&vec![0;n*n]);
    assert!(m.counts[0]>0); assert_eq!(m.counts[2],0); assert_eq!(m.counts[3],0);
    assert!(m.field.iter().all(|v| v.to_bits()==0));
    assert_eq!(m.eligible.iter().filter(|v| **v!=0).count(),m.counts[0] as usize);
}
#[test]
fn thin_valley_has_bounded_nonzero_proposal() {
    let n=128; let m=run(&valley(n),n,&vec![1.0;n*n],&vec![0;n*n]);
    assert!(m.counts[3]>0); assert!(m.counts[0]>m.counts[3]);
    assert!(m.metrics[0]<=6.0); assert!(m.metrics[1]<=1.25_f64.ln()+1e-8);
}
#[test]
fn protected_adversarial_pixels_cannot_change_evidence() {
    let n=192; let original=valley(n); let mut altered=original.clone();
    let mut protect=vec![0;n*n]; let weight=vec![1.0;n*n];
    for y in 80..112 { for x in 80..112 {
        let i=y*n+x; protect[i]=1;
        altered[3*i]=(x%2) as f32; altered[3*i+1]=(y%2) as f32; altered[3*i+2]=1.0;
    }}
    let a=run(&original,n,&weight,&protect); let b=run(&altered,n,&weight,&protect);
    assert_eq!(a.field,b.field); assert_eq!(a.eligible,b.eligible); assert_eq!(a.counts,b.counts);
    for y in 80..112 { for x in 80..112 { assert_eq!(a.field[y*n+x],0.0); } }
}
#[test]
fn narrow_context_refuses_instead_of_reporting_no_lines() {
    let n=128; let mut weight=vec![0.0;n*n];
    for y in 60..68 { for x in 30..98 { weight[y*n+x]=1.0; } }
    let result=measure_inner(&valley(n),&weight,&vec![0;n*n],n,n,full(n),2.0,MAX_BYTES,&mut || false);
    assert_eq!(result.err(),Some(CONTEXT_ERROR));
}
#[test]
fn gain_preserves_ratios_and_neutral_signed_zero() {
    let rgb=[0.4,0.2,0.1,1.0,0.25,-0.0,0.0,-0.0,0.0];
    let field=[1.25_f32.ln();3];
    let out=apply_inner(&rgb,&field,1.0,&mut || false).unwrap();
    assert!((out[0]/out[1]-2.0).abs()<1e-6);
    for i in 3..9 { assert_eq!(out[i].to_bits(),rgb[i].to_bits()); }
    let zero=apply_inner(&rgb,&field,0.0,&mut || false).unwrap();
    for i in 0..rgb.len() { assert_eq!(zero[i].to_bits(),rgb[i].to_bits()); }
}
#[test]
fn current_headroom_uses_one_gain_not_channel_clipping() {
    let rgb=[0.99,0.4,0.2]; let field=[1.25_f32.ln()];
    let out=apply_inner(&rgb,&field,1.0,&mut || false).unwrap();
    assert!(out[0]<=1.0);
    assert!((out[1]/rgb[1]-out[2]/rgb[2]).abs()<1e-6);
    assert!((out[0]/rgb[0]-out[1]/rgb[1]).abs()<1e-6);
}
#[test]
fn budget_cancellation_hdr_and_aliasing_refuse() {
    let n=128; let rgb=vec![0.5;3*n*n]; let weight=vec![1.0;n*n]; let protect=vec![0;n*n];
    assert_eq!(measure_inner(&rgb,&weight,&protect,n,n,full(n),2.0,0,&mut || false).err(),Some(BUDGET_ERROR));
    assert_eq!(measure_inner(&rgb,&weight,&protect,n,n,full(n),2.0,MAX_BYTES,&mut || true).err(),Some(CANCELLED));
    let mut hdr=rgb.clone(); hdr[0]=1.01;
    assert_eq!(measure_inner(&hdr,&weight,&protect,n,n,full(n),2.0,MAX_BYTES,&mut || false).err(),Some(INPUT_ERROR));
    assert_eq!(separate(&[(100,120),(119,140)]).err(),Some(ABI_ERROR));
}
#[test]
fn ffi_failure_keeps_all_output_buffers_untouched() {
    let n=128; let rgb=vec![0.5;3*n*n]; let weight=vec![1.0;n*n]; let protect=vec![0;n*n];
    let mut field=vec![-12.0;n*n]; let mut eligible=vec![9;n*n]; let mut counts=[99;4]; let mut metrics=[-9.0;2];
    let code=unsafe { lrt_neck_wrinkle_measure_v1(rgb.as_ptr(),rgb.len(),weight.as_ptr(),weight.len(),
        protect.as_ptr(),protect.len(),n,n,0,0,n,n,2.0,0,field.as_mut_ptr(),field.len(),
        eligible.as_mut_ptr(),eligible.len(),counts.as_mut_ptr(),counts.len(),metrics.as_mut_ptr(),metrics.len(),None,std::ptr::null_mut()) };
    assert_eq!(code,BUDGET_ERROR); assert!(field.iter().all(|v| *v == -12.0));
    assert!(eligible.iter().all(|v| *v==9)); assert_eq!(counts,[99;4]); assert_eq!(metrics,[-9.0;2]);
}

#[test]
fn isotropic_curvature_is_not_a_line_and_bright_ridge_is_not_dark_valley() {
    assert_eq!(line_response(2.0,2.0,0.0,2.0),0.0);
    assert_eq!(line_response(-2.0,0.0,0.0,2.0),0.0);
    assert!(line_response(2.0,0.0,0.0,2.0)>0.0);
    // Rotation changes Hessian entries, not the eigenvalue-based valley response.
    assert!((line_response(1.0,1.0,1.0,2.0)-line_response(2.0,0.0,0.0,2.0)).abs()<1e-12);
}
#[test]
fn measured_lightness_ramp_has_no_line_proposal() {
    let n=128; let mut rgb=vec![0.0;3*n*n];
    for y in 0..n { for x in 0..n {
        let l=40.0+20.0*(x as f64)/(n as f64); let linear=y_from_l(l);
        let encoded=if linear<=0.0031308 { 12.92*linear } else { 1.055*linear.powf(1.0/2.4)-0.055 } as f32;
        for c in 0..3 { rgb[3*(y*n+x)+c]=encoded; }
    }}
    let m=run(&rgb,n,&vec![1.0;n*n],&vec![0;n*n]);
    assert_eq!(m.counts[3],0);
}
#[test]
fn fullgrid_preparation_matches_roi_preparation_without_downsampling() {
    let n=192; let rgb=valley(n); let mut weight=vec![0.0;n*n]; let protect=vec![0;n*n];
    for y in 35..157 { for x in 45..147 { weight[y*n+x]=1.0; } }
    let a=run(&rgb,n,&weight,&protect);
    let r=Rect{y:35,x:45,h:122,w:102};
    let b=measure_inner(&rgb,&weight,&protect,n,n,r,2.0,MAX_BYTES,&mut || false).unwrap();
    for y in 0..r.h { for x in 0..r.w {
        assert_eq!(a.field[(y+r.y)*n+x+r.x].to_bits(),b.field[y*r.w+x].to_bits());
        assert_eq!(a.eligible[(y+r.y)*n+x+r.x],b.eligible[y*r.w+x]);
    }}
}
