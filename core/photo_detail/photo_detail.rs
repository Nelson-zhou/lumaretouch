//! Original non-AI display-RGB detail operators. Whole-frame, f32, ABI 1.
//! No model, texture aliases, per-tile boundaries, implicit resizing or output clipping.
use std::slice;
const MAX_PIXELS: usize = 100_000_000;
fn buffer(n:usize)->Result<Vec<f32>, &'static str>{let mut v=Vec::new();v.try_reserve_exact(n).map_err(|_|"allocation refused")?;v.resize(n,0.);Ok(v)}
fn clone_checked(v:&[f32])->Result<Vec<f32>, &'static str>{let mut o=buffer(v.len())?;o.copy_from_slice(v);Ok(o)}
// Two separable passes with a fixed original guide, clamp-to-frame boundaries.
// sigma=0 gives a Gaussian low pass; otherwise range weights preserve guide edges.
fn filter(src:&[f32],guide:&[f32],w:usize,h:usize,radius:f32,sigma:f32,cancel:&dyn Fn()->bool)->Result<Vec<f32>, &'static str>{
    let support=(3.*radius).ceil().max(1.) as isize;
    let mut tmp=buffer(src.len())?;let mut out=buffer(src.len())?;
    for axis in 0..2 {
        let input=if axis==0{src}else{&tmp};let mut dst=buffer(src.len())?;
        for y in 0..h {if cancel(){return Err("cancelled");}for x in 0..w {
            if x%128==0 && cancel(){return Err("cancelled");}
            let i=y*w+x;let mut sum=0.;let mut weights=0.;
            for d in -support..=support {
                let xx=if axis==0{(x as isize+d).clamp(0,w as isize-1) as usize}else{x};
                let yy=if axis==1{(y as isize+d).clamp(0,h as isize-1) as usize}else{y};let j=yy*w+xx;
                let spatial=d as f32/radius.max(0.01);
                let range=if sigma>0.{(guide[j]-guide[i])/sigma}else{0.};
                let weight=(-0.5*(spatial*spatial+range*range)).exp();sum+=weight*input[j];weights+=weight;
            }dst[i]=sum/weights;
        }}if axis==0{tmp=dst;}else{out=dst;}
    }Ok(out)
}
/// p = sharpen amount/radius/detail; luma amount/detail/contrast; chroma amount/detail/smoothness.
/// Radius is full-source pixels. Scale is explicit processing/source ratio; 1 for native-size export/inspection, up to 8 for enlarged export.
pub fn render(src:&[f32],w:usize,h:usize,p:[f32;9],scale:f32,cancel:&dyn Fn()->bool)->Result<Vec<f32>, &'static str>{
    let n=w.checked_mul(h).ok_or("dimensions")?;
    if n==0||n>MAX_PIXELS||src.len()!=n*3||!scale.is_finite()||scale<=0.||scale>8.||!p.iter().all(|v|v.is_finite())||!src.iter().all(|v|v.is_finite()&&v.abs()<=65504.){return Err("invalid input");}
    for i in 0..9{if i==1{if !(0.1..=3.).contains(&p[i]){return Err("radius");}}else if !(0.0..=100.).contains(&p[i]){return Err("control");}}
    if cancel(){return Err("cancelled");}
    if p[0]==0.&&p[3]==0.&&p[6]==0.{return clone_checked(src);}
    let a=p.map(|v|v/100.);let mut y=buffer(n)?;let mut u=buffer(n)?;let mut v=buffer(n)?;
    for i in 0..n {if i%4096==0&&cancel(){return Err("cancelled");}y[i]=0.2126*src[3*i]+0.7152*src[3*i+1]+0.0722*src[3*i+2];u[i]=src[3*i]-y[i];v[i]=src[3*i+2]-y[i];}
    if a[6]>0. {
        // More chroma detail narrows range threshold; smoothness widens spatial support.
        // Luma guide avoids color bleeding across strong luminance edges.
        let radius=(0.65+2.35*a[8])*scale;let sigma=0.16-0.145*a[7];
        for channel in [&mut u,&mut v] {
            let smooth=filter(channel,&y,w,h,radius,0.055,cancel)?;
            for i in 0..n {if i%4096==0&&cancel(){return Err("cancelled");}
                let residual=channel[i]-smooth[i];let retain=(residual.abs()/sigma).powi(2);
                // Bounded influence suppresses small chroma errors, retaining large color edges.
                channel[i]-=a[6]*residual/(1.+retain);
            }
        }
    }
    if a[3]>0. {
        // PixCake direction: higher luma detail means MORE denoising, not Adobe's inverse.
        let smooth=filter(&y,&y,w,h,1.15*scale,0.012+0.12*a[4],cancel)?;
        for i in 0..n {if i%4096==0&&cancel(){return Err("cancelled");}
            let residual=y[i]-smooth[i];
            // Contrast controls residual integration near the local mean, never global contrast.
            let integration=0.55+0.45*a[5]/(1.+(residual/0.06).powi(2));
            y[i]-=a[3]*integration*residual;
        }
    }
    if a[0]>0. {
        let blur=filter(&y,&y,w,h,p[1]*scale,0.,cancel)?;
        for i in 0..n {if i%4096==0&&cancel(){return Err("cancelled");}
            let residual=y[i]-blur[i];let threshold=0.025*(1.-a[2]);
            let fine_gate=if threshold==0.{1.}else{residual.abs()/(residual.abs()+threshold)};
            y[i]+=1.5*a[0]*residual*fine_gate;
        }
    }
    let mut out=buffer(src.len())?;
    for i in 0..n {if i%4096==0&&cancel(){return Err("cancelled");}
        out[3*i]=y[i]+u[i];out[3*i+2]=y[i]+v[i];out[3*i+1]=y[i]-(0.2126*u[i]+0.0722*v[i])/0.7152;
    }
    if !out.iter().all(|v|v.is_finite()){return Err("overflow");}Ok(out)
}
#[no_mangle]pub extern "C" fn lrt_photo_detail_abi()->u32{1}
/// Caller supplies valid aligned disjoint buffers. Output is untouched on error/cancel.
#[no_mangle]pub unsafe extern "C" fn lrt_photo_detail_render(input:*const f32,w:usize,h:usize,p:*const f32,scale:f32,output:*mut f32,cancel:Option<extern "C" fn()->i32>)->i32{
    if input.is_null()||p.is_null()||output.is_null(){return 1;}
    let n=match w.checked_mul(h){Some(n)if n>0&&n<=MAX_PIXELS=>n,_=>return 1};
    let result=std::panic::catch_unwind(||render(slice::from_raw_parts(input,n*3),w,h,std::array::from_fn(|i|*p.add(i)),scale,&||cancel.map_or(false,|f|f()!=0)));
    match result{Ok(Ok(data))=>{if cancel.map_or(false,|f|f()!=0){return 4;}std::ptr::copy_nonoverlapping(data.as_ptr(),output,n*3);0},Ok(Err("cancelled"))=>4,Ok(Err(_))=>2,Err(_)=>3}
}
// AUTHORED UNRUN: rustc/test execution deliberately left to authorized local QA.
#[cfg(test)]mod tests{
    use super::*;
    fn neutral()->[f32;9]{[0.,1.,50.,0.,50.,50.,0.,50.,50.]}
    #[test]fn neutral_exact(){let s=[-0.,-1.,2.];let o=render(&s,1,1,neutral(),1.,&||false).unwrap();assert_eq!(s.map(f32::to_bits),[o[0].to_bits(),o[1].to_bits(),o[2].to_bits()]);}
    #[test]fn constant_stays_constant(){let s=vec![0.4;3*49];let mut p=neutral();p[0]=100.;p[3]=100.;p[6]=100.;let o=render(&s,7,7,p,1.,&||false).unwrap();assert!(o.iter().all(|v|(*v-0.4).abs()<1e-5));}
    #[test]fn cancel_refuses(){assert_eq!(render(&[0.;3],1,1,neutral(),1.,&||true).unwrap_err(),"cancelled");}
    #[test]fn invalid_scale(){assert!(render(&[0.;3],1,1,neutral(),0.,&||false).is_err());}

    fn noisy()->Vec<f32>{(0..81).flat_map(|i|{let t=0.4+if i%2==0{0.02}else{-0.02};[t,t,t]}).collect()}
    fn energy(s:&[f32])->f32{s.chunks_exact(3).map(|p|(p[0]-0.4).powi(2)).sum()}
    #[test]fn luma_detail_direction(){let s=noisy();let mut p=neutral();p[3]=100.;p[4]=0.;let low=render(&s,9,9,p,1.,&||false).unwrap();p[4]=100.;let high=render(&s,9,9,p,1.,&||false).unwrap();assert!(energy(&high)<energy(&low));}
    #[test]fn sharpen_detail_direction(){let s=noisy();let mut p=neutral();p[0]=100.;p[2]=0.;let low=render(&s,9,9,p,1.,&||false).unwrap();p[2]=100.;let high=render(&s,9,9,p,1.,&||false).unwrap();assert!(energy(&high)>energy(&low));}
    #[test]fn luma_does_not_invent_chroma(){let s=noisy();let mut p=neutral();p[3]=100.;for rgb in render(&s,9,9,p,1.,&||false).unwrap().chunks_exact(3){assert!((rgb[0]-rgb[1]).abs()<1e-6);assert!((rgb[1]-rgb[2]).abs()<1e-6);}}
}
