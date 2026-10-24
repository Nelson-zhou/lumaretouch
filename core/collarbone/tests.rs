// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. No compilation, execution or numerical/photo acceptance.
use super::*;
const SIDE: usize = 129;
fn full() -> Rect { Rect {x:0,y:0,width:SIDE,height:SIDE} }
fn trace() -> Trace {
    Trace { points:vec![Point{x:28.0,y:64.0},Point{x:64.0,y:64.0},Point{x:100.0,y:64.0}], half_width:8.0 }
}
fn scene() -> (Vec<f32>,Vec<f32>) {
    let mut rgb = Vec::new();
    for y in 0..SIDE { for _ in 0..SIDE {
        let dy = y as f64-64.0;
        let log_modulation = 0.15*(-dy*dy/18.0).exp()-0.13*(-(dy-6.0).powi(2)/8.0).exp();
        rgb.extend([0.30,0.18,0.10].map(|v|encode(v*log_modulation.exp())));
    } }
    (rgb,vec![1.0;SIDE*SIDE])
}
fn bits(a: &[f32],b: &[f32]) -> bool { a.len()==b.len() && a.iter().zip(b).all(|(x,y)|x.to_bits()==y.to_bits()) }
fn prepared(rgb: &[f32],coverage: &[f32]) -> (Vec<f32>,[u64;STATS_LEN]) {
    let mut field = vec![f32::NAN;SIDE*SIDE]; let mut stats = [0;STATS_LEN];
    prepare_into(rgb,coverage,full(),SIDE,SIDE,&[trace()],full(),&mut field,&mut stats,||false).unwrap();
    (field,stats)
}
fn compose(current: &[f32],field: &[f32],amount: f32) -> Vec<f32> {
    let mut result = vec![f32::NAN;current.len()];
    compose_into(current,full(),field,full(),SIDE,SIDE,amount,&mut result,||false).unwrap(); result
}
#[test]
fn original_ridge_and_shadow_have_opposite_signs_and_bounded_band() {
    let (rgb,mask)=scene(); let (field,stats)=prepared(&rgb,&mask);
    assert!(stats[6]>0); assert!(field[64*SIDE+64]>0.0); assert!(field[70*SIDE+64]<0.0);
    for y in 0..SIDE { for x in 0..SIDE {
        let v=field[y*SIDE+x]; assert!(v.is_finite() && f64::from(v).abs()<=MAX_LOG_GAIN+1e-8);
        if !(57..72).contains(&y) || x<=28 || x>=100 { assert_eq!(v,0.0); }
    } }
}
#[test]
fn flat_source_has_no_invented_ridge_even_if_current_is_structured() {
    let (current,mask)=scene();
    let flat:Vec<_>=(0..SIDE*SIDE).flat_map(|_|[0.30,0.18,0.10].map(encode)).collect();
    let (field,stats)=prepared(&flat,&mask); assert_eq!(stats[6],0); assert!(field.iter().all(|&v|v==0.0));
    assert!(bits(&current,&compose(&current,&field,1.0)));
}
#[test]
fn zero_amount_zero_coverage_and_endpoints_are_bit_exact() {
    let (mut rgb,mask)=scene(); rgb[0]=-0.0;
    let (field,_)=prepared(&rgb,&mask);
    assert!(bits(&rgb,&compose(&rgb,&field,-0.0)));
    let (zero,stats)=prepared(&rgb,&vec![0.0;SIDE*SIDE]);
    assert_eq!(stats[1],0); assert!(bits(&rgb,&compose(&rgb,&zero,1.0)));
    for endpoint in [[0.0,-0.0,0.0],[1.0;3]] {
        let current:Vec<_>=(0..SIDE*SIDE).flat_map(|_|endpoint).collect();
        assert!(bits(&current,&compose(&current,&field,1.0)));
    }
}
#[test]
fn unsupported_other_owner_pixels_never_supply_baseline_or_filter_values() {
    let (source,mut coverage)=scene(); let mut altered=source.clone();
    for y in 0..SIDE { for x in 0..SIDE {
        if y<50 || y>78 || (x>55 && x<60) {
            coverage[y*SIDE+x]=0.0; altered[3*(y*SIDE+x)..3*(y*SIDE+x)+3].copy_from_slice(&[0.99,0.01,0.89]);
        }
    } }
    let (a,sa)=prepared(&source,&coverage); let (b,sb)=prepared(&altered,&coverage);
    assert!(bits(&a,&b)); assert_eq!(sa,sb); assert!(sa[3]>0);
    for (v,w) in a.iter().zip(&coverage) { if *w==0.0 { assert_eq!(*v,0.0); } }
}
#[test]
fn admitted_far_baselines_ignore_localized_unowned_filter_holes() {
    let (source,mut coverage)=scene(); let mut altered=source.clone();
    // Holes occupy part of otherwise observed far-sample neighborhoods. Center
    // taps and enough surrounding real owned skin remain; this must not pass
    // merely because every near/far measurement was refused.
    for (x,y) in [(62,47),(63,47),(66,81),(67,81),(42,49),(84,79)] {
        let i=y*SIDE+x; coverage[i]=0.0;
        altered[3*i..3*i+3].copy_from_slice(&[0.01,0.99,0.75]);
    }
    let (a,sa)=prepared(&source,&coverage); let (b,sb)=prepared(&altered,&coverage);
    assert!(sa[6]>0 && a[64*SIDE+64]>0.0);
    assert!(bits(&a,&b)); assert_eq!(sa,sb);
}
#[test]
fn source_border_is_refused_not_reflected() {
    let (rgb,mask)=scene(); let mut edge=trace(); for p in &mut edge.points { p.y=4.0; }
    let mut field=vec![f32::NAN;SIDE*SIDE]; let mut stats=[0;STATS_LEN];
    prepare_into(&rgb,&mask,full(),SIDE,SIDE,&[edge],full(),&mut field,&mut stats,||false).unwrap();
    assert!(stats[1]>0); assert_eq!(stats[2],stats[1]); assert_eq!(stats[6],0);
    assert!(field.iter().all(|&v|v==0.0));
}
#[test]
fn near_black_and_clipped_source_are_not_recovered() {
    for colour in [[0.0;3],[0.01;3],[1.0,0.4,0.3]] {
        let source:Vec<_>=(0..SIDE*SIDE).flat_map(|_|colour).collect();
        let (field,stats)=prepared(&source,&vec![1.0;SIDE*SIDE]);
        assert_eq!(stats[6],0); assert!(field.iter().all(|&v|v==0.0));
    }
}
#[test]
fn current_stage_chroma_gain_and_gamut_are_shared_channel_not_clipped() {
    let (source,mask)=scene(); let (field,_)=prepared(&source,&mask);
    let current:Vec<_>=(0..SIDE*SIDE).flat_map(|_|[0.45,0.20,0.06].map(encode)).collect();
    let rendered=compose(&current,&field,0.7);
    for i in 0..SIDE*SIDE {
        let a=decode(f64::from(rendered[3*i]))/decode(f64::from(current[3*i]));
        for c in 1..3 {
            let b=decode(f64::from(rendered[3*i+c]))/decode(f64::from(current[3*i+c]));
            assert!((a-b).abs()<2e-6);
        }
    }
    let saturated:Vec<_>=(0..SIDE*SIDE).flat_map(|_|[1.0,0.4,0.2]).collect();
    let result=compose(&saturated,&field,1.0);
    for i in 0..SIDE*SIDE {
        assert!(result[3*i..3*i+3].iter().copied().all(unit));
        if field[i]>=0.0 { assert!(bits(&saturated[3*i..3*i+3],&result[3*i..3*i+3])); }
    }
}
#[test]
fn prepare_once_and_compose_tiles_is_bit_identical() {
    let (source,mask)=scene(); let (field,_)=prepared(&source,&mask); let expected=compose(&source,&field,0.8);
    let mut stitched=vec![f32::NAN;source.len()];
    for y in (0..SIDE).step_by(11) {
        let rows=11.min(SIDE-y); let tile=Rect{x:0,y,width:SIDE,height:rows};
        compose_into(&source[3*y*SIDE..3*(y+rows)*SIDE],tile,&field,full(),SIDE,SIDE,0.8,
            &mut stitched[3*y*SIDE..3*(y+rows)*SIDE],||false).unwrap();
    }
    assert!(bits(&expected,&stitched));
}
#[test]
fn genuine_halo_preparation_matches_full_source_not_proxy() {
    let (source,mask)=scene(); let (full_field,_)=prepared(&source,&mask);
    let sample_window=Rect{x:0,y:34,width:SIDE,height:61};
    let output_window=Rect{x:18,y:54,width:93,height:21};
    let mut output=vec![f32::NAN;output_window.width*output_window.height]; let mut stats=[0;STATS_LEN];
    prepare_into(&source[3*34*SIDE..3*95*SIDE],&mask[34*SIDE..95*SIDE],sample_window,SIDE,SIDE,&[trace()],
        output_window,&mut output,&mut stats,||false).unwrap();
    for y in 0..output_window.height {
        assert!(bits(&output[y*93..(y+1)*93],&full_field[(y+54)*SIDE+18..(y+54)*SIDE+111]));
    }
}
#[test]
fn reversal_does_not_change_symmetric_normal_evidence() {
    let (source,mask)=scene(); let (expected,_)=prepared(&source,&mask); let mut reversed=trace(); reversed.points.reverse();
    let mut output=vec![0.0;SIDE*SIDE]; let mut stats=[0;STATS_LEN];
    prepare_into(&source,&mask,full(),SIDE,SIDE,&[reversed],full(),&mut output,&mut stats,||false).unwrap();
    // Floating-point trace projection reversal is permitted at sub-ulp field error.
    for (a,b) in expected.iter().zip(output) { assert!((a-b).abs()<1e-7); }
}
#[test]
fn malformed_controls_geometry_pixels_resources_and_cancellation_refuse() {
    let (source,mask)=scene(); let mut field=vec![0.0;SIDE*SIDE]; let mut stats=[0;STATS_LEN];
    assert_eq!(prepare_into(&source,&mask,full(),SIDE,SIDE,&[trace()],full(),&mut field,&mut stats,||true),Err(CANCELLED));
    let mut degenerate=trace(); degenerate.points[1]=degenerate.points[0];
    assert_eq!(prepare_into(&source,&mask,full(),SIDE,SIDE,&[degenerate],full(),&mut field,&mut stats,||false),Err(SETTINGS_ERROR));
    let mut invalid=source.clone(); invalid[7]=f32::NAN;
    assert_eq!(prepare_into(&invalid,&mask,full(),SIDE,SIDE,&[trace()],full(),&mut field,&mut stats,||false),Err(PIXEL_ERROR));
    let mut result=vec![0.0;source.len()];
    for amount in [-0.1,1.1,f32::NAN] {
        assert_eq!(compose_into(&source,full(),&field,full(),SIDE,SIDE,amount,&mut result,||false),Err(SETTINGS_ERROR));
    }
    assert_eq!(dimensions(65_537,1),Err(ABI_ERROR)); assert_eq!(dimensions(8000,8000),Err(RESOURCE_ERROR));
}
#[test]
fn abi_rejects_aliases_before_creating_conflicting_slices() {
    let (mut source,_)=scene(); let field=vec![0.0;SIDE*SIDE];
    let code=unsafe { lrt_collarbone_compose_v1(source.as_ptr(),source.len(),0,0,SIDE,SIDE,
        field.as_ptr(),field.len(),0,0,SIDE,SIDE,SIDE,SIDE,0.5,source.as_mut_ptr(),source.len(),None,std::ptr::null_mut()) };
    assert_eq!(code,ABI_ERROR);
}
