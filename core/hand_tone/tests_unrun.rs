// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN: no compilation, numerical execution or acceptance claim.
use super::*;
fn fixture()->(Vec<f32>,Vec<f32>,Vec<f32>,Vec<u8>) {
    let rgb=vec![0.4f32;25*25*3];let hand=vec![1.0;25*25];
    let mut target=vec![0.0;25*25];target[12*25+12]=1.0;
    (rgb,hand,target,vec![0;25*25])
}
#[test]
fn neutral_and_zero_amount_preserve_bits() {
    let rgb=[-0.0f32,0.25,1.0];
    let out=apply(&rgb,&[],0.0,None,std::ptr::null_mut()).unwrap();
    assert_eq!(out.iter().map(|v|v.to_bits()).collect::<Vec<_>>(),rgb.iter().map(|v|v.to_bits()).collect::<Vec<_>>());
    let (rgb,hand,target,protect)=fixture();
    let out=measure(&rgb,&hand,&target,&protect,25,25,4,None,std::ptr::null_mut()).unwrap();
    assert!(out.field.iter().all(|v|*v==0.0));assert_eq!(out.counts,[1,1,0,0]);
}
#[test]
fn moderate_dark_and_light_bands_get_opposite_common_gains() {
    for (value,sign) in [(0.37f32,1.0f32),(0.43,-1.0)] {
        let (mut rgb,hand,target,protect)=fixture();
        for y in 11..=13 {for x in 11..=13 {rgb[3*(y*25+x)..3*(y*25+x)+3].fill(value);}}
        let out=measure(&rgb,&hand,&target,&protect,25,25,4,None,std::ptr::null_mut()).unwrap();
        let i=12*25+12;assert!(out.field[3*i]*sign>0.0);
        assert_eq!(out.field[3*i],out.field[3*i+1]);assert_eq!(out.field[3*i],out.field[3*i+2]);
        assert!(out.field.iter().all(|v|(*v as f64).abs()<=MAX_GAIN+1e-6));
        assert_eq!(out.counts,[1,1,0,1]);
    }
}
#[test]
fn protection_excludes_entire_coarse_context() {
    let (rgb,hand,target,mut protect)=fixture();protect[12*25+15]=1;
    assert!(matches!(measure(&rgb,&hand,&target,&protect,25,25,4,None,std::ptr::null_mut()),Err(4)));
    protect[12*25+12]=1;
    let out=measure(&rgb,&hand,&target,&protect,25,25,4,None,std::ptr::null_mut()).unwrap();
    assert_eq!(out.counts,[0,0,0,0]);assert!(out.field.iter().all(|v|*v==0.0));
}
#[test]
fn high_contrast_and_source_edges_refuse() {
    let (mut rgb,hand,mut target,protect)=fixture();
    for y in 0..25 {for x in 0..12 {rgb[3*(y*25+x)..3*(y*25+x)+3].fill(0.1);}}
    assert!(matches!(measure(&rgb,&hand,&target,&protect,25,25,4,None,std::ptr::null_mut()),Err(4)));
    target.fill(0.0);target[0]=1.0;
    assert!(matches!(measure(&rgb,&hand,&target,&protect,25,25,4,None,std::ptr::null_mut()),Err(4)));
}
#[test]
fn application_is_common_linear_in_amount_and_headroom_safe() {
    let rgb=[0.2f32,0.3,0.4];let gain=[0.06f32;3];
    let half=apply(&rgb,&gain,0.5,None,std::ptr::null_mut()).unwrap();
    let full=apply(&rgb,&gain,1.0,None,std::ptr::null_mut()).unwrap();
    for c in 0..3 {assert!(rgb[c]<half[c] && half[c]<full[c]);}
    let white=[1.0f32;3];assert_eq!(apply(&white,&gain,1.,None,std::ptr::null_mut()).unwrap(),white);
    assert!(matches!(apply(&rgb,&[0.01,0.02,0.01],1.,None,std::ptr::null_mut()),Err(2)));
}
#[test]
fn callback_cancels_before_work() {
    unsafe extern "C" fn stop(_: *mut c_void)->i32 {1}
    let (rgb,hand,target,protect)=fixture();
    assert!(matches!(measure(&rgb,&hand,&target,&protect,25,25,4,Some(stop),std::ptr::null_mut()),Err(6)));
}
#[test]
fn rejected_abi_keeps_every_output_untouched() {
    let (rgb,hand,target,protect)=fixture();let n=625;
    let mut field=vec![99.0f32;3*n];let mut eligible=vec![9u8;n];
    let mut counts=[99u64;4];let mut metrics=[99.0f64;4];
    let status=unsafe {lrt_hand_tone_measure_v1(
        rgb.as_ptr(),rgb.len(),hand.as_ptr(),n,target.as_ptr(),n,protect.as_ptr(),n,
        25,25,1,u64::MAX,field.as_mut_ptr(),field.len(),eligible.as_mut_ptr(),n,
        counts.as_mut_ptr(),4,metrics.as_mut_ptr(),4,None,std::ptr::null_mut())};
    assert_eq!(status,3);assert!(field.iter().all(|v|*v==99.0));
    assert!(eligible.iter().all(|v|*v==9));assert_eq!(counts,[99;4]);assert_eq!(metrics,[99.0;4]);
}

// ROI is exact source pixels, including full context halo; no padding/resizing.
fn crop<T:Copy>(data:&[T],width:usize,channels:usize,x:usize,y:usize,w:usize,h:usize)->Vec<T> {
    let mut out=Vec::new();
    for row in y..y+h {out.extend_from_slice(&data[channels*(row*width+x)..channels*(row*width+x+w)]);}
    out
}
#[test]
fn exact_halo_roi_matches_full_source_away_from_thresholds() {
    let (mut rgb,hand,target,protect)=fixture();
    for y in 11..=13 {for x in 11..=13 {rgb[3*(y*25+x)..3*(y*25+x)+3].fill(0.37);}}
    let full=measure(&rgb,&hand,&target,&protect,25,25,4,None,std::ptr::null_mut()).unwrap();
    // Single central target bbox plus exactly four source pixels on each side.
    let roi=measure(&crop(&rgb,25,3,8,8,9,9),&crop(&hand,25,1,8,8,9,9),
        &crop(&target,25,1,8,8,9,9),&crop(&protect,25,1,8,8,9,9),
        9,9,4,None,std::ptr::null_mut()).unwrap();
    let full_i=12*25+12;let roi_i=4*9+4;
    assert_eq!(full.eligible[full_i],roi.eligible[roi_i]);
    for c in 0..3 {assert!((full.field[3*full_i+c]-roi.field[3*roi_i+c]).abs()<1e-6);}
    assert_eq!(full.counts,roi.counts);
}
#[test]
fn original_edge_clipped_halo_refuses_without_padding() {
    let (rgb,hand,mut target,protect)=fixture();target.fill(0.0);target[2*25+2]=1.0;
    assert!(matches!(measure(&rgb,&hand,&target,&protect,25,25,4,None,std::ptr::null_mut()),Err(4)));
    // Desired halo extends beyond source origin; clipping yields only real7x7.
    // Source target remains at(2,2), never shifted inward by synthesized pixels.
    assert!(matches!(measure(&crop(&rgb,25,3,0,0,7,7),&crop(&hand,25,1,0,0,7,7),
        &crop(&target,25,1,0,0,7,7),&crop(&protect,25,1,0,0,7,7),
        7,7,4,None,std::ptr::null_mut()),Err(4)));
}
