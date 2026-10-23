//! Original deterministic 2D ID-background compositor. No model or 3D claims.
//! ABI 1 requires entire source-domain planes, linear-sRGB-D65 RGB and float alpha.
//! All incoming pointers are non-overlapping, valid for their declared lengths.
use std::collections::VecDeque;
use std::slice;
const MAX_PIXELS: usize = 32_000_000;
type Cancel = Option<extern "C" fn() -> i32>;
fn stopped(c: Cancel) -> bool { c.map_or(false, |f| f() != 0) }
fn alloc(n: usize) -> Result<Vec<f32>, i32> {
    let mut v = Vec::new(); v.try_reserve_exact(n).map_err(|_| 4)?;
    v.resize(n, 0.0); Ok(v)
}
// Separable square dilation/erosion, outside coverage is zero, O(pixels).
fn morph(src: &[f32], dst: &mut [f32], w: usize, h: usize, r: usize,
         expand: bool, vertical: bool, cancel: Cancel) -> Result<(), i32> {
    let (lines,len)=if vertical {(w,h)} else {(h,w)};
    for line in 0..lines {
        if stopped(cancel) { return Err(3); }
        let idx=|p: usize| if vertical {p*w+line} else {line*w+p};
        let mut q: VecDeque<(isize,f32)>=VecDeque::with_capacity(2*r+1);
        for pos in -(r as isize)..len as isize+r as isize {
            let v=if pos<0 || pos>=len as isize {0.0} else {src[idx(pos as usize)]};
            while q.back().map_or(false, |&(_,b)| if expand {b<=v} else {b>=v}) {q.pop_back();}
            q.push_back((pos,v));
            let center=pos-r as isize;
            while q.front().map_or(false, |&(p,_)| p<center-r as isize) {q.pop_front();}
            if center>=0 && center<len as isize { dst[idx(center as usize)]=q.front().unwrap().1; }
        }
    }
    Ok(())
}
// Finite-support zero-padded box convolution, double accumulator, O(pixels).
fn blur(src: &[f32], dst: &mut [f32], w: usize, h: usize, r: usize,
        vertical: bool, cancel: Cancel) -> Result<(), i32> {
    let (lines,len)=if vertical {(w,h)} else {(h,w)};
    for line in 0..lines {
        if stopped(cancel) { return Err(3); }
        let idx=|p: usize| if vertical {p*w+line} else {line*w+p};
        let mut sum=0f64;
        for p in 0..r.min(len) {sum+=src[idx(p)] as f64;}
        for p in 0..len {
            if p+r<len {sum+=src[idx(p+r)] as f64;}
            if p>r {sum-=src[idx(p-r-1)] as f64;}
            dst[idx(p)]=(sum/(2*r+1) as f64).clamp(0.0,1.0) as f32;
        }
    }
    Ok(())
}
fn sample(a: &[f32], w: usize,h: usize,x: f32,y: f32)->f32 {
    let ix=x.floor() as isize;let iy=y.floor() as isize;
    let tx=x-x.floor();let ty=y-y.floor();let mut v=0.0;
    for (dy,wy) in [(0,1.0-ty),(1,ty)] {for (dx,wx) in [(0,1.0-tx),(1,tx)] {
        let px=ix+dx;let py=iy+dy;
        if px>=0&&py>=0&&px<w as isize&&py<h as isize {v+=a[py as usize*w+px as usize]*wx*wy;}
    }}v
}
fn blend(b:f32,s:f32,mode:u32)->f32 {
    match mode {
        0=>s,
        1=>b*s,
        _=>{let d=if b<=0.25 {((16.0*b-12.0)*b+4.0)*b} else {b.sqrt()};
            if s<=0.5 {b-(1.0-2.0*s)*b*(1.0-b)} else {b+(2.0*s-1.0)*(d-b)}}
    }
}
#[no_mangle]
pub extern "C" fn lrt_id_background_abi()->u32 {1}
// params: edge, background opacity, shadow opacity, blur radius, gradient,
// x,y,distance,angle degrees, shadow linear R,G,B. kind: 0 off,1 soft,2 hard,3 silhouette.
#[no_mangle]
pub unsafe extern "C" fn lrt_id_background_prepare(
    background:*const f32,alpha:*const f32,out:*mut f32,weight:*mut f32,
    w:usize,h:usize,params:*const f32,kind:u32,mode:u32,cancel:Cancel)->i32 {
    if weight.is_null()||background.is_null()||alpha.is_null()||out.is_null()||params.is_null(){return 1;}
    let n=match w.checked_mul(h){Some(n) if n>0&&n<=MAX_PIXELS&&w<=65536&&h<=65536=>n,_=>return 1};
    let p=slice::from_raw_parts(params,12);
    if p.iter().any(|x|!x.is_finite())||p[0].abs()>20.0||
       !(0.0..=1.0).contains(&p[1])||!(0.0..=1.0).contains(&p[2])||
       !(0.0..=256.0).contains(&p[3])||!(0.0..=1.0).contains(&p[4])||
       p[5].abs()>65536.0||p[6].abs()>65536.0||!(0.0..=65536.0).contains(&p[7])||
       p[8].abs()>360.0||p[9..12].iter().any(|x|!(0.0..=1.0).contains(x))||kind>3||mode>2 {return 1;}
    let bg=slice::from_raw_parts(background,n*3);
    let a=slice::from_raw_parts(alpha,n);let dst=slice::from_raw_parts_mut(out,n*3);let weights=slice::from_raw_parts_mut(weight,n);
    // Validate a row at a time for cancellation and bounded latency, before writing output.
    for y in 0..h {
        if stopped(cancel){return 3;}
        if bg[y*w*3..(y+1)*w*3].iter().any(|v|!v.is_finite()||!(0.0..=1.0).contains(v))||
            a[y*w..(y+1)*w].iter().any(|v|!v.is_finite()||!(0.0..=1.0).contains(v)){return 2;}
    }
    if p[1]==0.0 {dst.copy_from_slice(bg);weights.fill(1.0);return 0;}
    let result=(||->Result<(),i32>{
        let radius=if kind>0 && p[2]>0.0 {p[3].round() as usize} else {0};
        let sw=w+2*radius;let sh=h+2*radius;
        let support=sw.checked_mul(sh).ok_or(1)?;
        // Includes caller inputs, possible contiguous copies, output fields,
        // edge and two halo planes; reject before allocating any large field.
        let estimated=52usize.checked_mul(n).and_then(|v|support.checked_mul(8).and_then(|q|v.checked_add(q))).ok_or(1)?;
        if support>64_000_000 || estimated>2_147_483_648 {return Err(4);}
        let mut edge=alloc(n)?;
        let mut shadow=alloc(support)?;
        if p[0]==0.0 {edge.copy_from_slice(a);} else {
            let mut tmp=alloc(n)?;
            morph(a,&mut tmp,w,h,p[0].abs().round() as usize,p[0]>0.0,false,cancel)?;
            morph(&tmp,&mut edge,w,h,p[0].abs().round() as usize,p[0]>0.0,true,cancel)?;
        }
        if kind>0 && p[2]>0.0 {
            let theta=p[8].to_radians();let dx=p[5]+p[7]*theta.cos();let dy=p[6]+p[7]*theta.sin();
            for y in 0..sh {
                if stopped(cancel){return Err(3);}
                for x in 0..sw {
                    // Projection is evaluated outside the visible canvas too;
                    // its blur halo can contribute back into visible pixels.
                    let px=x as f32-radius as f32;let py=y as f32-radius as f32;
                    let sy=if kind==3 {(py-dy-(h-1) as f32)/0.35+(h-1) as f32} else {py-dy};
                    let v=sample(&edge,w,h,px-dx,sy);
                    let v=if kind==2 {if v>=0.5 {1.0}else{0.0}}else{v};
                    // Source-height fade, translated with the projected silhouette.
                    shadow[y*sw+x]=v*(1.0-p[4]*(1.0-sy/(h.saturating_sub(1).max(1) as f32)).clamp(0.0,1.0));
                }
            }
            if radius>0 {
                let mut tmp=alloc(support)?;
                blur(&shadow,&mut tmp,sw,sh,radius,false,cancel)?;
                blur(&tmp,&mut shadow,sw,sh,radius,true,cancel)?;
            }
        }
        for y in 0..h {
            if stopped(cancel){return Err(3);}
            for x in 0..w {let i=y*w+x;let coverage=shadow[(y+radius)*sw+x+radius]*p[2];
                weights[i]=1.0-(1.0-edge[i])*p[1];
                for c in 0..3 {let j=3*i+c;
                    let shaded=bg[j]+coverage*(blend(bg[j],p[9+c],mode)-bg[j]);
                    dst[j]=shaded;
                }
            }
        }
        Ok(())
    })();
    match result {Ok(())=>0,Err(code)=>code}
}

#[cfg(test)]
mod tests {
    use super::*;
    // Authored only, UNRUN under the source-only delivery constraint.
    #[test] fn neutral_is_exact() {unsafe {
        let bg=[0.2f32,0.4,0.6];let a=[0.5f32];let mut dst=[0f32;3];let mut weight=[0f32];
        let p=[0.0f32;12];assert_eq!(lrt_id_background_prepare(bg.as_ptr(),a.as_ptr(),dst.as_mut_ptr(),weight.as_mut_ptr(),1,1,p.as_ptr(),0,0,None),0);assert_eq!(bg,dst);assert_eq!(weight,[1.0]);
    }}
    #[test] fn opacity_changes_background_not_foreground() {unsafe {
        let bg=[1.0f32;6];let a=[1.0f32,0.0];let mut dst=[0f32;6];let mut weight=[0f32;2];
        let mut p=[0.0f32;12];p[1]=0.25;
        assert_eq!(lrt_id_background_prepare(bg.as_ptr(),a.as_ptr(),dst.as_mut_ptr(),weight.as_mut_ptr(),2,1,p.as_ptr(),0,0,None),0);assert_eq!(dst,bg);assert_eq!(weight,[1.0,0.75]);
    }}
    #[test] fn translated_shadow_uses_full_source_support() {unsafe {
        let bg=[1.0f32;9];let a=[1.0f32,0.0,0.0];let mut dst=[0f32;9];let mut weight=[0f32;3];
        let mut p=[0.0f32;12];p[1]=1.0;p[2]=1.0;p[5]=1.0;
        assert_eq!(lrt_id_background_prepare(bg.as_ptr(),a.as_ptr(),dst.as_mut_ptr(),weight.as_mut_ptr(),3,1,p.as_ptr(),1,0,None),0);
        assert_eq!(weight,[1.0,0.0,0.0]);assert_eq!(&dst[3..6],&[0.0,0.0,0.0]);
    }}
    extern "C" fn cancelled()->i32 {1}
    #[test] fn cancelled_preparation_does_not_publish_fields() {unsafe {
        let bg=[1.0f32;3];let a=[0.0f32];let mut dst=[-1.0f32;3];let mut weight=[-1.0f32];let p=[0.0f32;12];
        assert_eq!(lrt_id_background_prepare(bg.as_ptr(),a.as_ptr(),dst.as_mut_ptr(),weight.as_mut_ptr(),1,1,p.as_ptr(),0,0,Some(cancelled)),3);
        assert_eq!(dst,[-1.0;3]);assert_eq!(weight,[-1.0]);
    }}
    #[test] fn soft_light_midgrey_is_neutral() {
        assert_eq!(blend(0.2,0.5,2),0.2);assert_eq!(blend(0.8,0.5,2),0.8);
    }

    #[test] fn outside_canvas_shadow_blurs_back_through_halo() {unsafe {
        let bg=[1.0f32;3];let a=[1.0f32];let mut dst=[0f32;3];let mut weight=[0f32];
        let mut p=[0.0f32;12];p[1]=1.0;p[2]=1.0;p[3]=1.0;p[5]=1.0;
        assert_eq!(lrt_id_background_prepare(bg.as_ptr(),a.as_ptr(),dst.as_mut_ptr(),weight.as_mut_ptr(),1,1,p.as_ptr(),1,0,None),0);
        // Alpha centered one pixel outside the canvas contributes 1/9 after
        // separable radius-one box convolution, rather than disappearing.
        assert!((dst[0]-8.0/9.0).abs()<1e-6);
    }}

}
