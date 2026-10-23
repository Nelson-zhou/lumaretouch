//! Original Lumaretouch tonal-mask colour grading. GPL-3.0-or-later.
//! See docs/colour-grading/CONTRACT.md; no vendor implementation is copied.
use std::slice;
const MAX_PIXELS: usize = 65536;
const Y: [f32;3] = [0.2126,0.7152,0.0722];
fn luminance(p:[f32;3])->f32 { p[0]*Y[0]+p[1]*Y[1]+p[2]*Y[2] }
fn smooth(lo:f32,hi:f32,x:f32)->f32 { let t=((x-lo)/(hi-lo)).clamp(0.,1.); t*t*(3.-2.*t) }
/// Positive balance expands highlights. Width controls real overlapping masks.
/// The midpoint is linear Y=.18, not encoded sRGB=.5. Masks partition unity.
pub fn weights(y:f32,blend:f32,balance:f32)->[f32;3] {
    let y=y.max(0.); let t=(y/(y+0.18)+balance*0.003).clamp(0.,1.);
    let width=0.04+0.36*blend/100.;
    let s=1.-smooth(1./3.-width,1./3.+width,t);
    let h=smooth(2./3.-width,2./3.+width,t);
    let m=(1.-s-h).max(0.); let total=s+m+h;
    [s/total,m/total,h/total]
}
fn decode(x:f32)->f32 {let a=x.abs(); x.signum()*if a<=0.04045 {a/12.92}else{((a+0.055)/1.055).powf(2.4)}}
fn encode(x:f32)->f32 {let a=x.abs(); x.signum()*if a<=0.0031308 {a*12.92}else{1.055*a.powf(1./2.4)-0.055}}
/// Hue 0 red, 120 green, 240 blue, continuous periodic opponent direction.
/// Remove luminance before normalizing: saturation is a tint amount, NOT HSL.
fn tint(h:f32,s:f32)->[f32;3] {
    if s==0. {return [0.;3];}
    let a=h.to_radians(); let raw=[a.cos(),(a-2.*std::f32::consts::PI/3.).cos(),(a+2.*std::f32::consts::PI/3.).cos()];
    let l=luminance(raw);let d=raw.map(|v|v-l);
    let scale=d.iter().fold(0.0_f32,|a,v|a.max(v.abs()));
    d.map(|v|v/scale*s/100.*0.5)
}
fn valid_recipe(r:&[f32])->bool {
    r.len()==14 && r.iter().all(|x|x.is_finite()) && (0..4).all(|i| {
        (0.0..=360.0).contains(&r[i*3]) && (0.0..=100.0).contains(&r[i*3+1]) && r[i*3+2].abs()<=100.
    }) && (0.0..=100.0).contains(&r[12]) && r[13].abs()<=100.
}
fn neutral(r:&[f32])->bool {(0..4).all(|i|r[i*3+1]==0. && r[i*3+2]==0.)}
fn pixel(p:[f32;3],r:&[f32],tints:[[f32;3];4])->[f32;3] {
    let y=luminance(p);let w=weights(y,r[12],r[13]);let amplitude=y.max(0.02);
    let ev=r[11]*0.02+w[0]*r[2]*0.02+w[1]*r[5]*0.02+w[2]*r[8]*0.02;
    let gain=ev.exp2();
    std::array::from_fn(|c|(p[c]+amplitude*(tints[3][c]+w[0]*tints[0][c]+w[1]*tints[1][c]+w[2]*tints[2][c]))*gain)
}
#[no_mangle] pub extern "C" fn lrt_colour_grading_abi()->u32 {1}
/// Caller supplies non-overlapping, aligned input/output buffers, each n*3 f32,
/// and 14 recipe scalars; pointers valid for full call. No ownership transfer.
/// mode 0: linear sRGB D65, mode 1: extended encoded sRGB D65 (not ICC RGB).
/// Errors leave output untouched: 1 bounds/pointers/mode, 2 recipe, 3 pixels.
/// Cancellation is between caller chunks, not through a data-racy C flag.
#[no_mangle] pub unsafe extern "C" fn lrt_colour_grading_apply(input:*const f32,output:*mut f32,n:usize,recipe:*const f32,mode:u32)->i32 {
    if input.is_null()||output.is_null()||recipe.is_null()||n==0||n>MAX_PIXELS||mode>1{return 1;}
    // Addresses must not overlap (including the immutable recipe).
    let bytes=n*3*std::mem::size_of::<f32>();let a=input as usize;let b=output as usize;let c=recipe as usize;
    let overlaps=|x:usize,l:usize,y:usize,m:usize| x<y.saturating_add(m)&&y<x.saturating_add(l);
    if a%4!=0||b%4!=0||c%4!=0||overlaps(a,bytes,b,bytes)||overlaps(c,56,b,bytes){return 1;}
    let r=slice::from_raw_parts(recipe,14);if !valid_recipe(r){return 2;}
    let src=slice::from_raw_parts(input,n*3);
    // Encoded bound prevents decode overflow; linear HDR retains signed headroom.
    let limit=if mode==0 {65504.}else{128.};
    if src.iter().any(|v|!v.is_finite()||v.abs()>limit){return 3;}
    let dst=slice::from_raw_parts_mut(output,n*3);
    if neutral(r){dst.copy_from_slice(src);return 0;}
    let tints=std::array::from_fn(|i|tint(r[i*3],r[i*3+1]));
    for (source,target) in src.chunks_exact(3).zip(dst.chunks_exact_mut(3)) {
        let mut p=[source[0],source[1],source[2]];if mode==1 {p=p.map(decode);}
        let mut q=pixel(p,r,tints);if mode==1 {q=q.map(encode);}
        target.copy_from_slice(&q);
    }
    0
}
#[cfg(test)] mod tests {
    use super::*;
    fn r()->[f32;14] {let mut r=[0.;14];r[12]=50.;r}
    #[test] fn masks_partition_and_balance(){for y in [0.,0.01,0.05,0.18,0.5,1.,4.,100.] {for b in [0.,50.,100.] {let w=weights(y,b,0.);assert!((w.iter().sum::<f32>()-1.).abs()<1e-6);assert!(w.iter().all(|x|*x>=0.));assert!(weights(y,b,100.)[2]>=weights(y,b,-100.)[2]);}}}
    #[test] fn blend_changes_actual_overlap(){assert!(weights(0.09,100.,0.)[2]>weights(0.09,0.,0.)[2]);}
    #[test] fn neutral_bit_exact_signed_hdr(){let input=[-0.0,0.12345678,4.];let mut out=[0.;3];assert_eq!(unsafe{lrt_colour_grading_apply(input.as_ptr(),out.as_mut_ptr(),1,r().as_ptr(),0)},0);for i in 0..3 {assert_eq!(input[i].to_bits(),out[i].to_bits());}}
    #[test] fn global_ignores_masks(){let mut a=r();a[9]=240.;a[10]=40.;let mut b=a;b[12]=0.;b[13]=100.;let t=std::array::from_fn(|i|tint(a[i*3],a[i*3+1]));assert_eq!(pixel([0.18;3],&a,t),pixel([0.18;3],&b,t));}
    #[test] fn brightness_changes_selected_range(){let mut a=r();a[2]=100.;let ts=[[0.;3];4];assert!(pixel([0.01;3],&a,ts)[0]>0.01);assert_eq!(pixel([4.;3],&a,ts),[4.;3]);}
    #[test] fn malformed_rejects_before_output(){let input=[f32::NAN,0.,0.];let mut out=[42.;3];assert_eq!(unsafe{lrt_colour_grading_apply(input.as_ptr(),out.as_mut_ptr(),1,r().as_ptr(),0)},3);assert_eq!(out,[42.;3]);}
}
