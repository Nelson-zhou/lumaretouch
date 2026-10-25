// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. These are executable fixtures, not passed acceptance claims.
use super::*;
fn settings()->Settings{Settings{abi_version:2,struct_size:mem::size_of::<Settings>() as u32,
    aperture:0,max_radius_px:6.0,focus_near:0.4,focus_far:0.6,depth_falloff:0.4,
    occlusion_tolerance:0.0,rotation_radians:0.0,manual_depth:0.9,manual_depth_ack:1}}
fn budget()->Budget{Budget{abi_version:2,struct_size:mem::size_of::<Budget>() as u32,
    max_fft_butterflies:24_000_000_000,max_kernel_quadrature_evals:8_000_000_000,
    max_classification_pixels:4_000_000_000,max_support_probes:800_000_000,
    max_direct_pairs:250_000_000,reserved_repair_pairs:10_000_000,
    max_scratch_bytes:256_000_000,max_sink_bytes:1_600_000_000}}
fn source(w:usize,h:usize)->Vec<f32>{
    (0..w*h).flat_map(|i|[(i%19) as f32/18.0,((i*7+3)%23) as f32/22.0,
        ((i*11+2)%31) as f32/30.0,1.0]).collect()
}
fn run(src:&[f32],q:Option<&[f32]>,w:usize,h:usize,s:Settings)->Vec<f32>{
    let mut job=Job::create(src,q,w,h,s,budget(),||false).unwrap();
    let mut all=vec![f32::NAN;src.len()];
    for index in 0..job.plan.tile_count{
        let (x,y,tw,th)=job.tile_rect(index).unwrap();let mut out=vec![-9.0;tw*th*4];
        job.render_next(index,&mut out,||false).unwrap();
        for ry in 0..th{all[((y+ry)*w+x)*4..((y+ry)*w+x+tw)*4]
            .copy_from_slice(&out[ry*tw*4..(ry+1)*tw*4]);}
    }
    job.finish().unwrap();all
}
// Independent original reference: no FFT, cohort cache or renderer kernel call.
// The equation is the documented v1 4x4 sampled aperture with manual constant z.
fn reference_radius(q:f32,s:Settings)->f64{
    let d=(f64::from(s.focus_near)-f64::from(s.manual_depth))
        .max(f64::from(s.manual_depth)-f64::from(s.focus_far)).max(0.0);
    let b=(d/f64::from(s.depth_falloff)).min(1.0);let q=f64::from(q);
    f64::from(s.max_radius_px)*if q>=0.0{b+(1.0-b)*q}else{b*(1.0+q)}
}
fn reference_weight(dx:f64,dy:f64,r:f64,s:Settings)->f64{
    if r<=0.5{return if dx==0.0&&dy==0.0{1.0}else{0.0};}
    if dx.abs()>r+0.5||dy.abs()>r+0.5{return 0.0;}
    let pi=std::f64::consts::PI;let sides=match s.aperture{2=>5,3=>8,_=>0};
    let mass=match s.aperture{0=>pi,1=>0.625*pi,2|3=>0.5*sides as f64*(2.0*pi/sides as f64).sin(),
        4=>2.0*0.35_f64.acos()-0.7*(1.0-0.35_f64.powi(2)).sqrt(),_=>panic!()};
    let (sn,cs)=f64::from(s.rotation_radians).sin_cos();let mut total=0.0;
    for sy in 0..4{for sx in 0..4{
        let xx=(dx+(sx as f64+0.5)/4.0-0.5)/r;let yy=(dy+(sy as f64+0.5)/4.0-0.5)/r;
        let u=cs*xx+sn*yy;let v=-sn*xx+cs*yy;let rr=u*u+v*v;
        if rr>1.0{continue;}
        total+=match s.aperture{
            0=>1.0,1=>0.25+0.75*rr,
            2|3=>if (0..sides).all(|k|{let a=2.0*pi*k as f64/sides as f64;
                u*a.cos()+v*a.sin()<=(pi/sides as f64).cos()}){1.0}else{0.0},
            4=>if (u-0.35).powi(2)+v*v<=1.0&&(u+0.35).powi(2)+v*v<=1.0{1.0}else{0.0},
            _=>panic!(),
        };
    }}total/(16.0*mass*r*r)
}
fn reference(src:&[f32],q:Option<&[f32]>,w:usize,h:usize,s:Settings)->Vec<f32>{
    let mut out=vec![0.0;src.len()];
    for p in 0..w*h{
        let qp=q.map_or(0.0,|q|q[p]);let clear=f64::from((-qp).max(0.0));
        let mut sum=[0.0;5];let mut contributors=0;let mut sole=usize::MAX;
        for i in 0..w*h{
            let r=reference_radius(q.map_or(0.0,|q|q[i]),s);
            let weight=reference_weight((p%w) as f64-(i%w) as f64,(p/w) as f64-(i/w) as f64,r,s);
            if weight==0.0{continue;}contributors+=1;sole=i;
            for c in 0..4{sum[c]+=weight*f64::from(src[4*i+c]);}sum[4]+=weight;
        }
        if qp== -1.0||(contributors==1&&sole==p){out[4*p..4*p+4].copy_from_slice(&src[4*p..4*p+4]);}
        else{for c in 0..4{out[4*p+c]=((1.0-clear)*(sum[c]/sum[4])+clear*f64::from(src[4*p+c])) as f32;}}
    }out
}
fn near(a:&[f32],b:&[f32]){assert_eq!(a.len(),b.len());
    for (i,(x,y)) in a.iter().zip(b).enumerate(){assert!((x-y).abs()<=2.0e-6,"{i}: {x} != {y}");}}
fn reference_at(src:&[f32],q:Option<&[f32]>,w:usize,h:usize,s:Settings,p:usize)->[f32;4]{
    let qp=q.map_or(0.0,|q|q[p]);let clear=f64::from((-qp).max(0.0));
    let mut sum=[0.0;5];let mut contributors=0;let mut sole=usize::MAX;
    for i in 0..w*h{
        let r=reference_radius(q.map_or(0.0,|q|q[i]),s);
        let weight=reference_weight((p%w) as f64-(i%w) as f64,(p/w) as f64-(i/w) as f64,r,s);
        if weight==0.0{continue;}contributors+=1;sole=i;
        for c in 0..4{sum[c]+=weight*f64::from(src[4*i+c]);}sum[4]+=weight;
    }
    if qp== -1.0||(contributors==1&&sole==p){return src[4*p..4*p+4].try_into().unwrap();}
    std::array::from_fn(|c|((1.0-clear)*(sum[c]/sum[4])+clear*f64::from(src[4*p+c])) as f32)
}
#[test]
fn fft_roundtrip_and_signed_impulse_convolution(){
    use fft::{Complex,test_transform};let mut a=vec![Complex::default();32*16];
    a[7*32+9]=Complex{re:0.25,im:0.75};let original=a.clone();
    test_transform(&mut a,32,16,false).unwrap();test_transform(&mut a,32,16,true).unwrap();
    for (x,y) in a.iter().zip(original){assert!((x.re-y.re).abs()<1e-12);assert!((x.im-y.im).abs()<1e-12);}
}
#[test]
fn all_apertures_radii_rotations_match_direct_original_reference(){
    let src=source(13,9);
    for aperture in 0..5{for radius in [0.0,0.5,0.500_001,1.0,3.0,8.0]{for angle in [-0.7,0.0,0.4]{
        let mut s=settings();s.aperture=aperture;s.max_radius_px=radius;s.rotation_radians=angle;
        s.manual_depth=1.0;s.depth_falloff=0.1;
        near(&run(&src,None,13,9,s),&reference(&src,None,13,9,s));
    }}}
}
#[test]
fn mixed_plateaus_and_exact_feather_residual_mass(){
    let (w,h)=(29,11);let src=source(w,h);let mut q=vec![0.0;w*h];
    for y in 0..h{q[y*w+4]=-1.0;q[y*w+5]=-0.37;q[y*w+9]=0.23;q[y*w+10]=1.0;}
    for aperture in 0..5{let mut s=settings();s.aperture=aperture;s.rotation_radians=0.29;
        let job=Job::create(&src,Some(&q),w,h,s,budget(),||false).unwrap();
        assert_eq!(job.plan.non_delta_cohort_count,2);assert_eq!(job.plan.residual_emitters,22);
        assert!(job.plan.residual_candidate_pairs>0);
        near(&run(&src,Some(&q),w,h,s),&reference(&src,Some(&q),w,h,s));
    }
}
#[test]
fn true_edges_and_fixed_core_seam_match_reference(){
    let (w,h)=(259,7);let src=source(w,h);let mut s=settings();s.aperture=2;s.rotation_radians=0.41;
    let out=run(&src,None,w,h,s);let expected=reference(&src,None,w,h,s);near(&out,&expected);
    for y in 0..h{for x in [0,1,252,253,254,255,258]{near(&out[(y*w+x)*4..(y*w+x+1)*4],
        &expected[(y*w+x)*4..(y*w+x+1)*4]);}}
}
#[test]
fn vertical_and_four_core_corner_seams_match_selected_direct_receivers(){
    let (w,h)=(257,257);let src=source(w,h);let mut s=settings();
    s.aperture=2;s.rotation_radians=0.37;s.max_radius_px=3.0;
    let out=run(&src,None,w,h,s);
    // Independent whole-source gather at both sides of vertical/horizontal
    // seams and their four-core intersection, without a quadratic full oracle.
    for y in [0,252,253,254,255,256]{for x in [0,252,253,254,255,256]{
        let p=y*w+x;near(&out[4*p..4*p+4],&reference_at(&src,None,w,h,s,p));
    }}
}
#[test]
fn rendered_radius128_all_apertures_match_direct_reference(){
    let (w,h)=(17,13);let src=source(w,h);
    for aperture in 0..5{
        let mut s=settings();s.aperture=aperture;s.rotation_radians=0.31;
        s.max_radius_px=128.0;s.manual_depth=1.0;s.depth_falloff=0.1;
        near(&run(&src,None,w,h,s),&reference(&src,None,w,h,s));
    }
}
#[test]
fn distant_nonself_contributor_requires_exact_gather_not_neighbor_guess(){
    let (w,h)=(19,19);let mut src=vec![0.0;w*h*4];for p in src.chunks_exact_mut(4){p[3]=1.0;}
    let receiver=9*w+7;let emitter=9*w+11;src[4*emitter]=1.0;
    let mut q=vec![0.0;w*h];q[emitter]=1.0;
    let mut s=settings();s.manual_depth=0.5;s.max_radius_px=6.0;
    let out=run(&src,Some(&q),w,h,s);
    assert!(out[4*receiver]>0.0,"Distant blur must reach a delta receiver");
    near(&out[4*receiver..4*receiver+4],&reference_at(&src,Some(&q),w,h,s,receiver));
}
#[test]
fn odd_polygon_is_convolution_not_correlation(){
    let (w,h)=(31,31);let mut src=vec![0.0;w*h*4];for p in src.chunks_exact_mut(4){p[3]=1.0;}
    let center=15*w+15;src[4*center]=1.0;
    let mut s=settings();s.aperture=2;s.max_radius_px=8.0;s.manual_depth=1.0;s.depth_falloff=0.1;
    let out=run(&src,None,w,h,s);near(&out,&reference(&src,None,w,h,s));
    let mut asymmetric=false;
    for dy in -7isize..=7{for dx in -7isize..=7{
        let a=out[((15+dy) as usize*w+(15+dx) as usize)*4];
        let b=out[((15-dy) as usize*w+(15-dx) as usize)*4];
        if (a-b).abs()>1e-4{asymmetric=true;}
    }}assert!(asymmetric,"Fixture must distinguish a reflected pentagon");
}
#[test]
fn protection_is_byte_exact_and_protected_delta_emitter_remains(){
    let (w,h)=(11,7);let src=source(w,h);let all=vec![-1.0;w*h];
    let out=run(&src,Some(&all),w,h,settings());
    assert!(out.iter().zip(&src).all(|(a,b)|a.to_bits()==b.to_bits()));
    let mut q=vec![0.0;w*h];q[3*w+5]=-1.0;
    let out=run(&src,Some(&q),w,h,settings());near(&out,&reference(&src,Some(&q),w,h,settings()));
    for c in 0..4{assert_eq!(out[4*(3*w+5)+c].to_bits(),src[4*(3*w+5)+c].to_bits());}
}
#[test]
fn radius_zero_receiver_is_not_general_identity(){
    let (w,h)=(9,9);let mut src=source(w,h);let center=4*w+4;src[4*center]=0.0;
    let mut s=settings();s.manual_depth=0.5;let mut q=vec![1.0;w*h];q[center]=0.0;
    let out=run(&src,Some(&q),w,h,s);assert!(out[4*center]>0.0);
    near(&out,&reference(&src,Some(&q),w,h,s));
}
#[test]
fn neutral_and_single_pixel_preserve_source_bits(){
    let mut src=source(17,5);src[0]=-0.0;let mut s=settings();s.max_radius_px=0.0;
    let out=run(&src,None,17,5,s);assert!(out.iter().zip(&src).all(|(a,b)|a.to_bits()==b.to_bits()));
    let single=[-0.0,0.31,0.7,1.0];let out=run(&single,None,1,1,settings());
    assert!(out.iter().zip(single).all(|(a,b)|a.to_bits()==b.to_bits()));
}
#[test]
fn cancellation_during_fft_preserves_output_and_poisoned_job(){
    let src=source(63,39);let mut job=Job::create(&src,None,63,39,settings(),budget(),||false).unwrap();
    let mut out=vec![-7.25;src.len()];let before=out.clone();let mut polls=0;
    //1 initial +39 delta rows +64 fill rows +64 FFT rows =168 polls;
    // poll181 is inside the first FFT's column transforms for this geometry.
    assert_eq!(job.render_next(0,&mut out,||{polls+=1;polls>180}),Err(CANCELLED));
    assert_eq!(out,before);assert_eq!(job.finish(),Err(STATE_ERROR));
    assert_eq!(job.render_next(0,&mut out,||false),Err(STATE_ERROR));
}
#[test]
fn cancelled_later_tile_cannot_finish_a_partial_sink(){
    let src=source(260,3);let mut job=Job::create(&src,None,260,3,settings(),budget(),||false).unwrap();
    let mut first=vec![0.0;254*3*4];job.render_next(0,&mut first,||false).unwrap();
    let mut second=vec![-4.0;6*3*4];let before=second.clone();
    assert_eq!(job.render_next(1,&mut second,||true),Err(CANCELLED));assert_eq!(second,before);
    assert_eq!(job.finish(),Err(STATE_ERROR));
}
#[test]
fn invalid_hdr_alpha_depth_ack_and_direct_budget_reject(){
    let mut src=source(3,3);src[0]=1.01;
    assert!(matches!(Job::create(&src,None,3,3,settings(),budget(),||false),Err(PIXEL_ERROR)));
    src[0]=0.0;src[3]=0.5;
    assert!(matches!(Job::create(&src,None,3,3,settings(),budget(),||false),Err(PIXEL_ERROR)));
    src[3]=1.0;let mut s=settings();s.manual_depth_ack=0;
    assert!(matches!(Job::create(&src,None,3,3,s,budget(),||false),Err(SETTINGS_ERROR)));
    let mut b=budget();b.max_direct_pairs=250_000_001;
    assert!(matches!(Job::create(&src,None,3,3,settings(),b,||false),Err(RESOURCE_ERROR)));
}
#[test]
fn residual_and_repair_share_budget_and_refusal_is_atomic(){
    let src=source(9,9);let q=vec![0.123;81];let mut b=budget();b.max_direct_pairs=10;b.reserved_repair_pairs=10;
    assert!(matches!(Job::create(&src,Some(&q),9,9,settings(),b,||false),Err(RESOURCE_ERROR)));
    let src=source(1,1);let mut b=budget();b.reserved_repair_pairs=0;
    let mut j=Job::create(&src,None,1,1,settings(),b,||false).unwrap();let mut out=vec![-3.0;4];
    assert_eq!(j.render_next(0,&mut out,||false),Err(RESOURCE_ERROR));assert_eq!(out,vec![-3.0;4]);
}
#[test]
fn ffi_create_cancel_and_overlap_are_atomic(){unsafe{
    let src=source(9,9);let mut handle=ptr::null_mut();let mut p=Plan::default();
    extern "C" fn stop(_: *mut c_void)->i32{1}
    assert_eq!(lrt_lens_cohort_create_v2(src.as_ptr(),src.len(),ptr::null(),0,9,9,
        settings(),budget(),&mut handle,&mut p,Some(stop),ptr::null_mut()),CANCELLED);
    assert!(handle.is_null());assert_eq!(p.abi_version,0);
    assert_eq!(lrt_lens_cohort_create_v2(src.as_ptr(),src.len(),ptr::null(),0,9,9,
        settings(),budget(),&mut handle,&mut p,None,ptr::null_mut()),0);
    assert_eq!(lrt_lens_cohort_render_next_v2(handle,0,src.as_ptr() as *mut f32,src.len(),None,ptr::null_mut()),ABI_ERROR);
    assert_eq!(lrt_lens_cohort_finish_v2(handle),STATE_ERROR);lrt_lens_cohort_destroy_v2(handle);
}}
#[test]
fn ffi_invalid_index_poisons_retry_and_finish_without_output_writes(){unsafe{
    let src=source(9,9);let mut handle=ptr::null_mut();let mut p=Plan::default();
    assert_eq!(lrt_lens_cohort_create_v2(src.as_ptr(),src.len(),ptr::null(),0,9,9,
        settings(),budget(),&mut handle,&mut p,None,ptr::null_mut()),0);
    let mut out=vec![-6.0;src.len()];let before=out.clone();
    assert_eq!(lrt_lens_cohort_render_next_v2(handle,p.tile_count,out.as_mut_ptr(),out.len(),None,ptr::null_mut()),STATE_ERROR);
    assert_eq!(out,before);
    assert_eq!(lrt_lens_cohort_render_next_v2(handle,0,out.as_mut_ptr(),out.len(),None,ptr::null_mut()),STATE_ERROR);
    assert_eq!(out,before);assert_eq!(lrt_lens_cohort_finish_v2(handle),STATE_ERROR);
    lrt_lens_cohort_destroy_v2(handle);
}}
#[test]
fn empty_non_delta_halo_certificate_avoids_unrelated_support_repairs(){
    let (w,h)=(800,5);let src=source(w,h);let mut q=vec![0.0;w*h];q[2*w+400]=1.0;
    let mut s=settings();s.manual_depth=0.5;let mut b=budget();b.reserved_repair_pairs=0;
    let mut job=Job::create(&src,Some(&q),w,h,s,b,||false).unwrap();
    let mut first=vec![-1.0;254*h*4];job.render_next(0,&mut first,||false).unwrap();
    for y in 0..h{for x in 0..254{for c in 0..4{
        assert_eq!(first[(y*254+x)*4+c].to_bits(),src[(y*w+x)*4+c].to_bits());
    }}}
}
#[test]
#[ignore="Large source allocation and runtime acceptance require explicit authorization"]
fn full_24mp_plan_is_derived_work_not_a_benchmark(){
    let src=vec![0.5f32;6000*4000*4];let mut src=src;
    for p in src.chunks_exact_mut(4){p[3]=1.0;}
    let mut s=settings();s.max_radius_px=128.0;s.manual_depth=1.0;s.depth_falloff=0.1;
    let job=Job::create(&src,None,6000,4000,s,budget(),||false).unwrap();
    assert_eq!(job.plan.source_pixels,24_000_000);assert_eq!(job.plan.tile_count,384);
    assert_eq!((job.plan.fft_width,job.plan.fft_height),(512,512));
    assert_eq!(job.plan.fft_transform_count,2305); //6*384 plus one cached kernel.
    assert!(job.plan.required_scratch_bytes<16_000_000);
    assert_eq!(job.plan.sink_bytes,384_000_000);
}
