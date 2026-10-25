// SPDX-License-Identifier: GPL-3.0-or-later
//! Original reference-assisted limb vein correction. AUTHORED / UNRUN.
//! No external numerical code, weights, automatic detection or retained pointers.
use std::ffi::c_void;
use std::mem::{align_of, size_of};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::slice;

const MAX_PIXELS: usize = 32_000_000;
const MAX_GAIN: f64 = 0.303949045610792; // ln(1.12) + 2*ln(1.10)
const BRIGHTNESS: f64 = 0.11332868530700327; // ln(1.12)
const CHROMA: f64 = 0.09531017980432493; // ln(1.10)
const FLOOR: f64 = 1e-5;
const REF_CEILING: f64 = 0.995;
type Cancel = Option<unsafe extern "C" fn(*mut c_void) -> i32>;
type Result<T> = std::result::Result<T, i32>;

#[no_mangle]
pub extern "C" fn lrt_limb_vein_abi() -> u32 { 1 }
#[no_mangle]
pub extern "C" fn lrt_limb_vein_algorithm() -> u32 { 1 }

fn dims(w: usize, h: usize) -> Result<usize> {
    if w == 0 || h == 0 || w > 65536 || h > 65536 { return Err(1); }
    let n = w.checked_mul(h).ok_or(1)?;
    if n > MAX_PIXELS { Err(5) } else { Ok(n) }
}
fn budget(n: usize, per: u64, extra: u64, available: u64) -> Result<()> {
    let required = (n as u64).checked_mul(per).and_then(|v|v.checked_add(extra)).ok_or(5)?;
    if available < required { Err(5) } else { Ok(()) }
}
fn alloc<T: Clone>(n: usize, value: T) -> Result<Vec<T>> {
    let mut v = Vec::new(); v.try_reserve_exact(n).map_err(|_|5)?; v.resize(n,value); Ok(v)
}
fn range<T>(p: *const T, len: usize) -> Result<(usize,usize)> {
    if p.is_null() || (p as usize) % align_of::<T>() != 0 || len == 0 { return Err(1); }
    let bytes = len.checked_mul(size_of::<T>()).ok_or(1)?;
    if bytes > isize::MAX as usize { return Err(1); }
    let a=p as usize; Ok((a,a.checked_add(bytes).ok_or(1)?))
}
fn disjoint(inputs: &[(usize,usize)], outputs: &[(usize,usize)]) -> Result<()> {
    for (i,a) in outputs.iter().enumerate() {
        for b in inputs.iter().chain(outputs[..i].iter()) {
            if a.0 < b.1 && b.0 < a.1 { return Err(1); }
        }
    }
    Ok(())
}
fn cancelled(cb: Cancel, ctx: *mut c_void) -> Result<()> {
    if let Some(f)=cb { if unsafe { f(ctx) } != 0 { return Err(6); } } Ok(())
}
fn valid_rgb(rgb: &[f32], cb: Cancel, ctx: *mut c_void) -> Result<()> {
    for (i,&v) in rgb.iter().enumerate() {
        if i % 65536 == 0 { cancelled(cb,ctx)?; }
        if !v.is_finite() || !(0.0..=1.0).contains(&v) { return Err(2); }
    } Ok(())
}

struct Measured { field: Vec<f32>, eligible: Vec<u8>, counts: [u64;4], metrics: [f64;4] }

fn measure(rgb: &[f32], limb: &[f32], target: &[f32], reference: &[f32], protect: &[u8],
           w: usize, h: usize, radius: usize, cb: Cancel, ctx: *mut c_void) -> Result<Measured> {
    valid_rgb(rgb,cb,ctx)?;
    let n=w*h;
    let mut target_count=0u64;
    let mut mass=0.0;
    let mut mean=[0.0f64;3];
    let mut m2=[0.0f64;3];
    for i in 0..n {
        if i%32768==0 { cancelled(cb,ctx)?; }
        let (g,t,r)=(limb[i],target[i],reference[i]);
        if !g.is_finite() || !t.is_finite() || !r.is_finite()
            || !(0.0..=1.0).contains(&g) || !(0.0..=1.0).contains(&t)
            || !(0.0..=1.0).contains(&r) || t>g || r>g || (t>0.0 && r>0.0)
            || protect[i]>1 { return Err(2); }
        if protect[i]!=0 { continue; }
        if t>0.0 { target_count+=1; }
    }
    let mut result=Measured{field:alloc(n*3,0.0)?,eligible:alloc(n,0)?,counts:[target_count,0,0,0],metrics:[0.0,0.0,0.0,1.0]};
    if target_count==0 { return Ok(result); }
    for i in 0..n {
        if i%32768==0 { cancelled(cb,ctx)?; }
        let r=reference[i];
        if r>0.0 && protect[i]==0 {
            let rw=r as f64; let next=mass+rw;
            for c in 0..3 {
                let v=rgb[3*i+c] as f64;
                if v<=FLOOR || v>=REF_CEILING { return Err(4); }
                let x=v.ln(); let delta=x-mean[c];
                mean[c]+=rw/next*delta;
                m2[c]+=rw*delta*(x-mean[c]);
            }
            mass=next;
        }
    }
    if mass<16.0 { return Err(4); }
    result.metrics[0]=mass;
    let spread=m2.iter().map(|v|(v.max(0.0)/mass).sqrt()).fold(0.0,f64::max);
    if !spread.is_finite() || spread>0.35 { return Err(4); }
    result.metrics[1]=spread;

    // Horizontal then vertical rolling sums of [weight*log R/G/B,weight].
    // Real source pixels only. Protected/zero-support/black/clipped observations
    // have zero donor mass. No reflected context or interpolated proxy samples.
    let mut horizontal=alloc(n*4,0.0f64)?;
    let donor=|i:usize| -> [f64;4] {
        if protect[i]!=0 || limb[i]<=0.0 { return [0.0;4]; }
        let p=&rgb[3*i..3*i+3];
        if p.iter().any(|&v|v as f64<=FLOOR || v as f64>=REF_CEILING) { return [0.0;4]; }
        let g=limb[i] as f64;
        [g*(p[0] as f64).ln(),g*(p[1] as f64).ln(),g*(p[2] as f64).ln(),g]
    };
    for y in 0..h {
        cancelled(cb,ctx)?;
        let mut sum=[0.0;4];
        for x in 0..=radius.min(w-1) { let d=donor(y*w+x); for c in 0..4 {sum[c]+=d[c];} }
        for x in 0..w {
            horizontal[4*(y*w+x)..4*(y*w+x)+4].copy_from_slice(&sum);
            if x>=radius { let d=donor(y*w+x-radius);for c in 0..4{sum[c]-=d[c];} }
            if let Some(add)=x.checked_add(radius+1) { if add<w {let d=donor(y*w+add);for c in 0..4{sum[c]+=d[c];}} }
        }
    }
    for x in 0..w {
        cancelled(cb,ctx)?;
        let mut sum=[0.0;4];
        for y in 0..=radius.min(h-1) { for c in 0..4 {sum[c]+=horizontal[4*(y*w+x)+c];} }
        for y in 0..h {
            let i=y*w+x;
            if target[i]>0.0 && protect[i]==0 {
                let bw=(x+radius+1).min(w)-x.saturating_sub(radius);
                let bh=(y+radius+1).min(h)-y.saturating_sub(radius);
                let fraction=(sum[3]/(bw*bh) as f64).clamp(0.0,1.0);
                result.metrics[3]=result.metrics[3].min(fraction);
                let pixel=&rgb[3*i..3*i+3];
                if fraction<0.75 || sum[3]<=0.0 || pixel.iter().any(|&v|v as f64<=FLOOR || v as f64>=REF_CEILING) {
                    result.counts[2]+=1;
                } else {
                    result.eligible[i]=1; result.counts[1]+=1;
                    let mut delta=[0.0;3];
                    for c in 0..3 { delta[c]=mean[c]-sum[c]/sum[3]; }
                    let common=(delta[0]+delta[1]+delta[2])/3.0;
                    let light=common.clamp(-BRIGHTNESS,BRIGHTNESS);
                    let chroma=[(delta[0]-common).clamp(-CHROMA,CHROMA),
                                (delta[1]-common).clamp(-CHROMA,CHROMA),
                                (delta[2]-common).clamp(-CHROMA,CHROMA)];
                    let chroma_mean=(chroma[0]+chroma[1]+chroma[2])/3.0;
                    let mut changed=false;
                    for c in 0..3 {
                        let correction=(light+chroma[c]-chroma_mean) * target[i] as f64;
                        if !correction.is_finite() || correction.abs()>MAX_GAIN+1e-10 {return Err(7);}
                        let v=if correction.abs()<1e-7 {0.0} else {correction as f32};
                        result.field[3*i+c]=v; changed |= v!=0.0;
                        result.metrics[2]=result.metrics[2].max((v as f64).abs());
                    }
                    if changed {result.counts[3]+=1;}
                }
            }
            if y>=radius {for c in 0..4{sum[c]-=horizontal[4*((y-radius)*w+x)+c];}}
            if let Some(add)=y.checked_add(radius+1) {if add<h {for c in 0..4{sum[c]+=horizontal[4*(add*w+x)+c];}}}
        }
    }
    cancelled(cb,ctx)?;
    if result.counts[1]==0 {return Err(4);}
    Ok(result)
}

fn apply(rgb:&[f32], field:&[f32], amount:f64, cb:Cancel, ctx:*mut c_void)->Result<Vec<f32>> {
    valid_rgb(rgb,cb,ctx)?;
    let mut out=alloc(rgb.len(),0.0)?; out.copy_from_slice(rgb);
    if amount==0.0 {return Ok(out);}
    for (i,(pixel,gain)) in rgb.chunks_exact(3).zip(field.chunks_exact(3)).enumerate() {
        if i%32768==0 {cancelled(cb,ctx)?;}
        if gain.iter().any(|v|!v.is_finite() || (*v as f64).abs()>MAX_GAIN+1e-6) {return Err(2);}
        // One progressive control: first soften colour; only the upper half
        // adds bounded shading correction. No geometric flattening or diagnosis.
        let common=(gain[0] as f64+gain[1] as f64+gain[2] as f64)/3.0;
        let colour=(2.0*amount).min(1.0);
        let tone=(2.0*amount-1.0).max(0.0);
        let effective=[common*tone+(gain[0] as f64-common)*colour,
                       common*tone+(gain[1] as f64-common)*colour,
                       common*tone+(gain[2] as f64-common)*colour];
        let mut t=1.0f64;
        for c in 0..3 {
            let (v,g)=(pixel[c] as f64,effective[c]);
            if g>0.0 && v>0.0 {t=t.min((-v.ln()/g).max(0.0)*(1.0-1e-7));}
        }
        if t==0.0 || effective.iter().all(|v|*v==0.0) {continue;}
        for c in 0..3 {
            if pixel[c]==0.0 || effective[c]==0.0 {continue;}
            let v=(pixel[c] as f64*(t*effective[c]).exp()) as f32;
            if !v.is_finite() || !(0.0..=1.0).contains(&v) {return Err(7);}
            out[3*i+c]=v;
        }
    }
    cancelled(cb,ctx)?; Ok(out)
}

#[no_mangle]
pub unsafe extern "C" fn lrt_limb_vein_measure_v1(
 rgb:*const f32,rgb_len:usize,limb:*const f32,limb_len:usize,
 target:*const f32,target_len:usize,reference:*const f32,reference_len:usize,
 protect:*const u8,protect_len:usize,w:usize,h:usize,radius:usize,byte_budget:u64,
 field:*mut f32,field_len:usize,eligible:*mut u8,eligible_len:usize,
 counts:*mut u64,counts_len:usize,metrics:*mut f64,metrics_len:usize,
 cb:Cancel,ctx:*mut c_void)->i32 {
    match catch_unwind(AssertUnwindSafe(||->Result<()> {
        let n=dims(w,h)?;
        if rgb_len!=3*n || limb_len!=n || target_len!=n || reference_len!=n || protect_len!=n
            || field_len!=3*n || eligible_len!=n || counts_len!=4 || metrics_len!=4 {return Err(1);}
        if !(2..=128).contains(&radius) {return Err(3);}
        budget(n,128,8*1024*1024,byte_budget)?;
        let inputs=[range(rgb,rgb_len)?,range(limb,limb_len)?,range(target,target_len)?,range(reference,reference_len)?,range(protect,protect_len)?];
        let outputs=[range(field,field_len)?,range(eligible,eligible_len)?,range(counts,counts_len)?,range(metrics,metrics_len)?];
        disjoint(&inputs,&outputs)?;
        let r=measure(slice::from_raw_parts(rgb,rgb_len),slice::from_raw_parts(limb,n),slice::from_raw_parts(target,n),
                      slice::from_raw_parts(reference,n),slice::from_raw_parts(protect,n),w,h,radius,cb,ctx)?;
        cancelled(cb,ctx)?;
        std::ptr::copy_nonoverlapping(r.field.as_ptr(),field,field_len);
        std::ptr::copy_nonoverlapping(r.eligible.as_ptr(),eligible,n);
        std::ptr::copy_nonoverlapping(r.counts.as_ptr(),counts,4);
        std::ptr::copy_nonoverlapping(r.metrics.as_ptr(),metrics,4); Ok(())
    })) {Ok(Ok(()))=>0,Ok(Err(code))=>code,Err(_)=>8}
}

#[no_mangle]
pub unsafe extern "C" fn lrt_limb_vein_apply_v1(
 current:*const f32,current_len:usize,field:*const f32,field_len:usize,w:usize,h:usize,
 amount:f64,byte_budget:u64,output:*mut f32,output_len:usize,cb:Cancel,ctx:*mut c_void)->i32 {
    match catch_unwind(AssertUnwindSafe(||->Result<()> {
        let n=dims(w,h)?;
        if current_len!=3*n || output_len!=3*n {return Err(1);}
        if !amount.is_finite() || !(0.0..=1.0).contains(&amount) {return Err(3);}
        budget(n,80,1024*1024,byte_budget)?;
        let mut inputs=vec![range(current,current_len)?];
        let gains=if amount==0.0 && field.is_null() && field_len==0 {&[][..]} else {
            if field_len!=3*n {return Err(1);}
            inputs.push(range(field,field_len)?); slice::from_raw_parts(field,field_len)
        };
        disjoint(&inputs,&[range(output,output_len)?])?;
        let r=apply(slice::from_raw_parts(current,current_len),gains,amount,cb,ctx)?;
        cancelled(cb,ctx)?;
        std::ptr::copy_nonoverlapping(r.as_ptr(),output,output_len); Ok(())
    })) {Ok(Ok(()))=>0,Ok(Err(code))=>code,Err(_)=>8}
}

#[cfg(test)]
#[path="tests_unrun.rs"]
mod tests;
