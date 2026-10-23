//! Original extended-display-sRGB tone operators. No exposure aliases or image normalization.
//! ABI 2: packed RGB f32, optional [0,1] mask, seven [-100,100] controls, preview scale, cooperative cancellation callback.
use std::slice;
const MAX_PIXELS: usize = 100_000_000;
fn smooth(a:f64,b:f64,x:f64)->f64 {let t=((x-a)/(b-a)).clamp(0.,1.);t*t*(3.-2.*t)}
fn linear(x:f64)->f64 {let a=x.abs();x.signum()*if a<=0.04045 {a/12.92} else {((a+0.055)/1.055).powf(2.4)}}
fn encoded(x:f64)->f64 {let a=x.abs();x.signum()*if a<=0.0031308 {a*12.92} else {1.055*a.powf(1./2.4)-0.055}}
fn luma(p:&[f64])->f64 {0.2126*p[0]+0.7152*p[1]+0.0722*p[2]}
// Separable edge-aware local mean: fixed support, never a global Gaussian/detail substitute.
fn bilateral(src:&[f64],w:usize,h:usize,r:usize,sigma:f64,cancel:&dyn Fn()->bool)->Result<Vec<f64>,&'static str>{
    let mut tmp=vec![0.;src.len()];let mut out=vec![0.;src.len()];
    for axis in 0..2 {let input=if axis==0 {src} else {&tmp};let mut dst=vec![0.;src.len()];
        for y in 0..h {if cancel(){return Err("cancelled");}for x in 0..w {if x%256==0&&cancel(){return Err("cancelled");}let i=y*w+x;let mut sum=0.;let mut weights=0.;
            for d in -(r as isize)..=r as isize {let xx=if axis==0 {(x as isize+d).clamp(0,w as isize-1) as usize} else{x};let yy=if axis==1 {(y as isize+d).clamp(0,h as isize-1) as usize} else{y};
                let v=input[yy*w+xx];let delta=(v-input[i])/sigma;let distance=d as f64/r.max(1) as f64;
                let weight=(-0.5*delta*delta-2.*distance*distance).exp();sum+=weight*v;weights+=weight;
            }dst[i]=sum/weights;
        }}if axis==0 {tmp=dst;} else {out=dst;}
    }Ok(out)
}
// Fractional source-space radii preserve distinct frequency bands on small proxies.
// Below one pixel interpolate identity and radius-one, rather than collapsing both bands.
fn scaled_bilateral(src:&[f64],w:usize,h:usize,radius:f64,sigma:f64,cancel:&dyn Fn()->bool)->Result<Vec<f64>,&'static str>{
    let lo=radius.floor() as usize;let hi=radius.ceil().max(1.) as usize;let t=radius-lo as f64;
    let low=if lo==0 {src.to_vec()} else {bilateral(src,w,h,lo,sigma,cancel)?};
    if lo==hi {return Ok(low);}
    let high=bilateral(src,w,h,hi,sigma,cancel)?;
    Ok(low.iter().zip(high).map(|(a,b)|a+(b-a)*t).collect())
}
fn local_min(src:&[f64],w:usize,h:usize,r:usize,cancel:&dyn Fn()->bool)->Result<Vec<f64>,&'static str>{
    let mut tmp=vec![0.;src.len()];let mut out=vec![0.;src.len()];
    for y in 0..h {if cancel(){return Err("cancelled");}for x in 0..w {if x%256==0&&cancel(){return Err("cancelled");}let mut m=f64::INFINITY;for xx in x.saturating_sub(r)..=(x+r).min(w-1){m=m.min(src[y*w+xx]);}tmp[y*w+x]=m;}}
    for y in 0..h {if cancel(){return Err("cancelled");}for x in 0..w {if x%256==0&&cancel(){return Err("cancelled");}let mut m=f64::INFINITY;for yy in y.saturating_sub(r)..=(y+r).min(h-1){m=m.min(tmp[yy*w+x]);}out[y*w+x]=m;}}Ok(out)
}
// Deterministic bounded histogram, fixed log domain (not per-image rescaling).
fn airlight(rgb:&[f64],cancel:&dyn Fn()->bool)->Result<f64,&'static str> {
    let mut bins=[0usize;2048];let mut sums=[0.;2048];
    for (i,p) in rgb.chunks_exact(3).enumerate() {if i%4096==0&&cancel(){return Err("cancelled");}let y=luma(p).max(0.);let b=((1.+y).ln()/17.*2047.).floor().clamp(0.,2047.) as usize;bins[b]+=1;sums[b]+=y;}
    let target=((rgb.len()/3) as f64*0.001).ceil().max(1.) as usize;let mut n=0;let mut s=0.;
    for i in (0..2048).rev(){n+=bins[i];s+=sums[i];if n>=target{break;}}Ok((s/n.max(1) as f64).max(0.05))
}
pub fn render(src:&[f32],w:usize,h:usize,mask:Option<&[f32]>,p:[f64;7],scale:f64)->Result<Vec<f32>,&'static str>{
    render_cancellable(src,w,h,mask,p,scale,&||false)
}
pub fn render_cancellable(src:&[f32],w:usize,h:usize,mask:Option<&[f32]>,p:[f64;7],scale:f64,cancel:&dyn Fn()->bool)->Result<Vec<f32>,&'static str>{
    if cancel(){return Err("cancelled");}
    let n=w.checked_mul(h).ok_or("dimension overflow")?;
    if n==0 || n>MAX_PIXELS || src.len()!=n*3 || !src.iter().all(|v|v.is_finite()) || !p.iter().all(|v|v.is_finite()&&(-100.0..=100.0).contains(v)) || !scale.is_finite() || !(0.<scale&&scale<=1.) {return Err("invalid input");}
    if let Some(m)=mask {if m.len()!=n || !m.iter().all(|v|v.is_finite()&&(0.0..=1.0).contains(v)){return Err("invalid mask");}}
    if p.iter().all(|v|*v==0.) || mask.map_or(false,|m|m.iter().all(|v|*v==0.)){return Ok(src.to_vec());}
    let a=p.map(|v|v/100.);let mut rgb:Vec<f64>=src.iter().map(|v|*v as f64).collect();
    // Scene-linear atmospheric scattering inversion, independent from brightness and contrast.
    if a[5]!=0. {
        let mut lin:Vec<f64>=rgb.iter().map(|v|linear(*v)).collect();let air=airlight(&lin,cancel)?;
        let dark:Vec<f64>=lin.chunks_exact(3).map(|v|v[0].min(v[1]).min(v[2]).max(0.)).collect();
        let r=(12.*scale).round().max(1.) as usize;let dark=local_min(&dark,w,h,r,cancel)?;
        for (i,pixel) in lin.chunks_exact_mut(3).enumerate(){if i%4096==0&&cancel(){return Err("cancelled");}let haze=(dark[i]/air).clamp(0.,0.9);let t=(1.-0.8*a[5].abs()*haze).max(0.28);
            for v in pixel { *v=if a[5]>0. {(*v-air)/t+air} else {*v*t+air*(1.-t)}; }
        }rgb=lin.into_iter().map(encoded).collect();
    }
    // Endpoint controls and a smooth compact midtone bump. Preserve extended HDR, no clipping.
    for (i,pixel) in rgb.chunks_exact_mut(3).enumerate() {if i%4096==0&&cancel(){return Err("cancelled");}let y=luma(pixel);let t=y.clamp(0.,1.);let bump=if (0.0..=1.0).contains(&y){4.*t*t*(1.-t)*(1.-t)}else{0.};
        let delta=a[0]*bump+0.35*a[1]*smooth(0.6,1.,y)+0.15*a[2]*(1.-smooth(0.,0.35,y));
        for v in pixel {*v+=delta;}
    }
    if a[3]!=0. || a[4]!=0. {
        let y:Vec<f64>=rgb.chunks_exact(3).map(luma).collect();
        let guide:Vec<f64>=y.iter().map(|v|v.max(0.).ln_1p()).collect();
        let fine=scaled_bilateral(&guide,w,h,scale,0.12,cancel)?;let mid=scaled_bilateral(&guide,w,h,3.*scale,0.12,cancel)?;
        let coarse=if a[4]!=0. {scaled_bilateral(&guide,w,h,12.*scale,0.22,cancel)?} else {mid.clone()};
        for (i,pixel) in rgb.chunks_exact_mut(3).enumerate(){
            if i%4096==0&&cancel(){return Err("cancelled");}
            let band=fine[i]-mid[i];let noise_gate=smooth(0.001,0.006,band.abs());
            let texture=0.75*a[3]*band*noise_gate;let clarity=0.65*a[4]*(mid[i]-coarse[i]);
            let delta=(texture+clarity).clamp(-0.12,0.12);let target=(guide[i]+delta).exp_m1();
            let dy=if y[i]>=0. {target-y[i]} else{0.};for v in pixel {*v+=dy;}
        }
    }
    if a[6]!=0. {for (i,pixel) in rgb.chunks_exact_mut(3).enumerate(){if i%4096==0&&cancel(){return Err("cancelled");}let y=luma(pixel);let hi=pixel.iter().copied().fold(f64::NEG_INFINITY,f64::max);let lo=pixel.iter().copied().fold(f64::INFINITY,f64::min);let chroma=hi-lo;
        let saturation=(chroma/hi.abs().max(lo.abs()).max(0.001)).clamp(0.,1.);
        let gain=1.+0.8*a[6]*(1.-saturation).powi(2);
        for v in pixel {*v=y+(*v-y)*gain;}
    }}
    let mut out=src.to_vec();for i in 0..n{if i%4096==0&&cancel(){return Err("cancelled");}let amount=mask.map_or(1.,|m|m[i] as f64);if amount==0.{continue;}for c in 0..3{let j=3*i+c;let v=src[j] as f64+amount*(rgb[j]-src[j] as f64);if !v.is_finite()||v.abs()>f32::MAX as f64{return Err("output overflow");}out[j]=v as f32;}}Ok(out)
}
#[no_mangle]pub extern "C" fn lrt_extended_tone_abi()->u32{2}
/// Pointers must be valid, aligned and nonoverlapping. Output unchanged on numerical failure.
#[no_mangle]pub unsafe extern "C" fn lrt_extended_tone_render(input:*const f32,w:usize,h:usize,mask:*const f32,controls:*const f64,scale:f64,output:*mut f32,cancel:Option<extern "C" fn()->i32>)->i32{
    if input.is_null()||controls.is_null()||output.is_null(){return 1;}
    let n=match w.checked_mul(h){Some(v) if v>0&&v<=MAX_PIXELS=>v,_=>return 1};
    let result=std::panic::catch_unwind(|| {let src=slice::from_raw_parts(input,n*3);let params=slice::from_raw_parts(controls,7);let p=std::array::from_fn(|i|params[i]);let m=if mask.is_null(){None}else{Some(slice::from_raw_parts(mask,n))};render_cancellable(src,w,h,m,p,scale,&||cancel.map_or(false,|f|f()!=0))});
    match result {Ok(Ok(data))=>{std::ptr::copy_nonoverlapping(data.as_ptr(),output,n*3);0},Ok(Err("cancelled"))=>4,Ok(Err(_))=>2,Err(_)=>3}
}
#[cfg(test)]mod tests{
    use super::*;
    #[test]fn neutral_is_bit_exact(){let x=[-0.,-1.,2.,0.2,0.2,0.2];assert_eq!(render(&x,2,1,None,[0.;7],1.).unwrap().iter().map(|x|x.to_bits()).collect::<Vec<_>>(),x.iter().map(|x|x.to_bits()).collect::<Vec<_>>());}
    #[test]fn zero_mask_exact(){let x=[-0.,-1.,2.];let y=render(&x,1,1,Some(&[0.]),[50.;7],1.).unwrap();assert_eq!(x.map(f32::to_bits),[y[0].to_bits(),y[1].to_bits(),y[2].to_bits()]);}
    #[test]fn constant_texture_clarity_are_identity(){let x=vec![0.4;27];for slot in [3,4]{let mut p=[0.;7];p[slot]=100.;let y=render(&x,3,3,None,p,1.).unwrap();for (a,b) in x.iter().zip(y){assert!((*a-b).abs()<1e-6);}}}
    #[test]fn neutral_colors_remain_neutral(){let x=vec![0.4;27];let y=render(&x,3,3,None,[25.;7],1.).unwrap();for p in y.chunks(3){assert_eq!(p[0],p[1]);assert_eq!(p[1],p[2]);}}
    #[test]fn brightness_is_not_exposure(){let x=[0.,0.,0.,0.5,0.5,0.5,1.,1.,1.];let y=render(&x,3,1,None,[100.,0.,0.,0.,0.,0.,0.],1.).unwrap();assert_eq!(y[0],0.);assert_eq!(y[6],1.);assert!(y[3]>0.5);}
    #[test]fn rejects_bad_inputs(){assert!(render(&[0.;3],1,1,None,[101.;7],1.).is_err());assert!(render(&[0.;3],1,1,Some(&[1.1]),[0.;7],1.).is_err());}
}

/// Original grayscale output mode, after all color effects. No profile impersonation.
#[no_mangle]pub unsafe extern "C" fn lrt_extended_tone_monochrome(input:*const f32,n:usize,output:*mut f32,cancel:Option<extern "C" fn()->i32>)->i32{
    if input.is_null()||output.is_null()||n==0||n>MAX_PIXELS{return 1;}
    let src=slice::from_raw_parts(input,n*3);
    if !src.iter().all(|v|v.is_finite()){return 2;}
    for i in 0..n {
        if i%4096==0&&cancel.map_or(false,|f|f()!=0){return 4;}
        let y=(src[3*i] as f64*0.2126+src[3*i+1] as f64*0.7152+src[3*i+2] as f64*0.0722) as f32;
        for c in 0..3{*output.add(3*i+c)=y;}
    }0
}
