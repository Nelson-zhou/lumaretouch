//! Original Lumaretouch RGB-family selective process-colour adjustment.
//! GPL-3.0-or-later. Mathematical contract in docs/selective-colour/CONTRACT.md.
use std::slice;
fn encode(x:f32)->f32 {let a=x.abs();x.signum()*if a<=0.0031308 {12.92*a}else{1.055*a.powf(1./2.4)-0.055}}
fn decode(x:f32)->f32 {let a=x.abs();x.signum()*if a<=0.04045 {a/12.92}else{((a+0.055)/1.055).powf(2.4)}}
/// Continuous RGB-derived partition, ordered R Y G C B M W N K; no hue/HSL.
pub fn weights(p:[f32;3])->[f32;9] {
    let [r,g,b]=p.map(|x|x.clamp(0.,1.));
    let lo=r.min(g).min(b);let hi=r.max(g).max(b);
    let achroma=1.-(hi-lo);let light=(hi+lo)*0.5;
    [(r-g.max(b)).max(0.),(r.min(g)-b).max(0.),
     (g-r.max(b)).max(0.),(g.min(b)-r).max(0.),
     (b-r.max(g)).max(0.),(b.min(r)-g).max(0.),
     achroma*light*light,achroma*2.*light*(1.-light),achroma*(1.-light)*(1.-light)]
}
/// Work on an SDR anchor; signed/HDR residual is untouched in encoded space.
/// Relative adds a fraction of existing complementary ink, absolute percentage
/// points. Black adds equally to all three process-ink adjustments. Each range
/// clamps its ink target, then weights combine deltas from the ORIGINAL anchor.
fn pixel(p:[f32;3],recipe:&[f32])->[f32;3] {
    let anchor=p.map(|v|v.clamp(0.,1.));let w=weights(anchor);
    std::array::from_fn(|c| {
        let ink=1.-anchor[c];let scale=if recipe[36]==1. {ink}else{1.};
        let mut delta=0.;
        for i in 0..9 {
            let target=(ink+(recipe[4*i+c]+recipe[4*i+3])*scale).clamp(0.,1.);
            delta+=w[i]*(ink-target);
        }
        if delta==0. {p[c]}else{p[c]+delta}
    })
}
#[no_mangle] pub extern "C" fn lrt_selective_colour_abi()->u32 {1}
/// SAFETY: aligned valid non-overlapping output of n*3 f32; input n*3 and recipe
/// 37 f32 valid throughout call. No ownership transfer. Mode 0 linear, 1 encoded
/// extended sRGB D65. Errors 1 pointers/bounds, 2 recipe, 3 pixels leave output.
#[no_mangle] pub unsafe extern "C" fn lrt_selective_colour_apply(input:*const f32,output:*mut f32,n:usize,recipe:*const f32,mode:u32)->i32 {
    if input.is_null()||output.is_null()||recipe.is_null()||n==0||n>65536||mode>1{return 1;}
    let bytes=n*12;let a=input as usize;let b=output as usize;let c=recipe as usize;
    let overlap=|x:usize,l:usize,y:usize,m:usize|x<y.saturating_add(m)&&y<x.saturating_add(l);
    if a%4!=0||b%4!=0||c%4!=0||overlap(a,bytes,b,bytes)||overlap(c,148,b,bytes){return 1;}
    let r=slice::from_raw_parts(recipe,37);
    if r[..36].iter().any(|v|!v.is_finite()||v.abs()>1.)||!(r[36]==0.||r[36]==1.){return 2;}
    let src=slice::from_raw_parts(input,n*3);let limit=if mode==0{65504.}else{128.};
    if src.iter().any(|v|!v.is_finite()||v.abs()>limit){return 3;}
    let dst=slice::from_raw_parts_mut(output,n*3);
    if r[..36].iter().all(|v|*v==0.){dst.copy_from_slice(src);return 0;}
    for (s,d) in src.chunks_exact(3).zip(dst.chunks_exact_mut(3)) {
        let original=[s[0],s[1],s[2]];let p=if mode==0{original.map(encode)}else{original};
        let q=pixel(p,r);
        let result=std::array::from_fn::<f32,3,_>(|c|if q[c]==p[c]{original[c]}else if mode==0{decode(q[c])}else{q[c]});
        d.copy_from_slice(&result);
    }
    0
}
#[cfg(test)] mod tests {
 use super::*;
 #[test] fn six_pure_families_are_distinct(){for (i,p) in [[1.,0.,0.],[1.,1.,0.],[0.,1.,0.],[0.,1.,1.],[0.,0.,1.],[1.,0.,1.]].iter().enumerate(){let w=weights(*p);for j in 0..9{assert_eq!(w[j],if i==j{1.}else{0.});}}}
 #[test] fn partition(){for r in 0..11{for g in 0..11{for b in 0..11{let w=weights([r as f32/10.,g as f32/10.,b as f32/10.]);assert!((w.iter().sum::<f32>()-1.).abs()<1e-6);assert!(w.iter().all(|v|*v>=0.));}}}}
 #[test] fn relative_and_absolute_differ(){let mut r=[0.;37];r[0]=0.2;r[36]=1.;let p=[0.8,0.2,0.2];let relative=pixel(p,&r);r[36]=0.;let absolute=pixel(p,&r);assert!(absolute[0]<relative[0]);assert!(relative[0]<p[0]);assert_eq!(relative[1],p[1]);}
 #[test] fn hdr_residual_not_clipped(){let mut r=[0.;37];r[6*4]=0.2;let p=[4.,4.,4.];let q=pixel(p,&r);assert!(q[0]>1.);assert_eq!(q[1],4.);}
 #[test] fn neutral_exact(){let src=[-0.0_f32,0.12345678,4.];let mut dst=[0.;3];let r=[0.;37];assert_eq!(unsafe{lrt_selective_colour_apply(src.as_ptr(),dst.as_mut_ptr(),1,r.as_ptr(),0)},0);for i in 0..3{assert_eq!(src[i].to_bits(),dst[i].to_bits());}}
 #[test] fn reject_without_writing(){let src=[f32::NAN,0.,0.];let mut dst=[42.;3];let r=[0.;37];assert_eq!(unsafe{lrt_selective_colour_apply(src.as_ptr(),dst.as_mut_ptr(),1,r.as_ptr(),1)},3);assert_eq!(dst,[42.;3]);}
}
