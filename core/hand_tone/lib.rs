// SPDX-License-Identifier: GPL-3.0-or-later
//! Original manual hand mid-frequency luminance correction. AUTHORED / UNRUN.
//! No external numerical code, weights, automatic detection or retained pointers.
use std::ffi::c_void;
use std::mem::{align_of, size_of};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::slice;

const MAX_PIXELS: usize = 32_000_000;
const MAX_GAIN: f64 = 0.0769610411361284; // ln(1.08), common RGB gain only
const FLOOR: f64 = 1e-5;
const SAMPLE_CEILING: f64 = 0.995;
type Cancel = Option<unsafe extern "C" fn(*mut c_void) -> i32>;
type Result<T> = std::result::Result<T, i32>;

#[no_mangle]
pub extern "C" fn lrt_hand_tone_abi() -> u32 { 1 }
#[no_mangle]
pub extern "C" fn lrt_hand_tone_algorithm() -> u32 { 1 }

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

// Five rolling moments: weighted log Y, weighted log Y squared, weight,
// hard protection count and excluded sample count. All on the actual source grid.
fn box_moments(rgb: &[f32], limb: &[f32], protect: &[u8], w: usize, h: usize,
               radius: usize, cb: Cancel, ctx: *mut c_void) -> Result<Vec<f64>> {
    let n=w*h;
    let mut horizontal=alloc(n*5,0.0f64)?;
    let donor=|i:usize| -> [f64;5] {
        if protect[i]!=0 { return [0.0,0.0,0.0,1.0,1.0]; }
        let p=&rgb[3*i..3*i+3];
        if limb[i]<=0.0 || p.iter().any(|&v|v as f64<=FLOOR || v as f64>=SAMPLE_CEILING) {
            return [0.0,0.0,0.0,0.0,1.0];
        }
        let log_y=luminance(p).ln(); let g=limb[i] as f64;
        [g*log_y,g*log_y*log_y,g,0.0,0.0]
    };
    for y in 0..h {
        cancelled(cb,ctx)?;
        let mut sum=[0.0;5];
        for x in 0..=radius.min(w-1) {let d=donor(y*w+x);for c in 0..5{sum[c]+=d[c];}}
        for x in 0..w {
            horizontal[5*(y*w+x)..5*(y*w+x)+5].copy_from_slice(&sum);
            if x>=radius {let d=donor(y*w+x-radius);for c in 0..5{sum[c]-=d[c];}}
            if x+radius+1<w {let d=donor(y*w+x+radius+1);for c in 0..5{sum[c]+=d[c];}}
        }
    }
    let mut output=alloc(n*5,0.0f64)?;
    for x in 0..w {
        cancelled(cb,ctx)?;
        let mut sum=[0.0;5];
        for y in 0..=radius.min(h-1) {for c in 0..5{sum[c]+=horizontal[5*(y*w+x)+c];}}
        for y in 0..h {
            output[5*(y*w+x)..5*(y*w+x)+5].copy_from_slice(&sum);
            if y>=radius {for c in 0..5{sum[c]-=horizontal[5*((y-radius)*w+x)+c];}}
            if y+radius+1<h {for c in 0..5{sum[c]+=horizontal[5*((y+radius+1)*w+x)+c];}}
        }
    }
    Ok(output)
}
fn luminance(p: &[f32]) -> f64 {0.2126*p[0] as f64+0.7152*p[1] as f64+0.0722*p[2] as f64}
// C1 taper: suppress high-contrast regions; this is not semantic edge detection.
fn taper(value:f64, full:f64, reject:f64)->f64 {
    let t=((value-full)/(reject-full)).clamp(0.0,1.0);
    1.0-t*t*(3.0-2.0*t)
}
fn measure(rgb: &[f32], limb: &[f32], target: &[f32], protect: &[u8],
           w: usize, h: usize, radius: usize, cb: Cancel, ctx: *mut c_void) -> Result<Measured> {
    valid_rgb(rgb,cb,ctx)?;
    let n=w*h;
    let mut target_count=0u64;
    for i in 0..n {
        if i%32768==0 {cancelled(cb,ctx)?;}
        let (g,t)=(limb[i],target[i]);
        if !g.is_finite() || !t.is_finite()
            || !(0.0..=1.0).contains(&g) || !(0.0..=1.0).contains(&t)
            || t>g
            || protect[i]>1 {return Err(2);}
        if protect[i]==0 && t>0.0 {target_count+=1;}
    }
    let mut result=Measured{field:alloc(n*3,0.0)?,eligible:alloc(n,0)?,counts:[target_count,0,0,0],metrics:[0.0,0.0,0.0,1.0]};
    if target_count==0 {return Ok(result);}
    let small_radius=(radius/4).max(1);
    // Peak temporary memory: 3*40*N moments + 13*N result = 133*N;
    // native budget reserves 160*N plus 8 MiB. No source downsampling.
    let coarse=box_moments(rgb,limb,protect,w,h,radius,cb,ctx)?;
    let fine=box_moments(rgb,limb,protect,w,h,small_radius,cb,ctx)?;
    let coarse_area=((2*radius+1)*(2*radius+1)) as f64;
    let small_area=((2*small_radius+1)*(2*small_radius+1)) as f64;
    for y in 0..h {
        cancelled(cb,ctx)?;
        for x in 0..w {
            let i=y*w+x;
            if target[i]<=0.0 || protect[i]!=0 {continue;}
            let c=&coarse[5*i..5*i+5];let f=&fine[5*i..5*i+5];
            let fraction=(c[2]/coarse_area).clamp(0.0,1.0);
            result.metrics[3]=result.metrics[3].min(fraction);
            let p=&rgb[3*i..3*i+3];
            // Protect erodes eligibility by the entire coarse radius. Source
            // edges, incomplete hand support and black/clipped observations
            // cannot manufacture context from reflection or protected pixels.
            if x<radius || y<radius || x+radius>=w || y+radius>=h
                || fraction<0.95 || f[2]/small_area<0.95 || c[3]>0.0 || c[4]>0.0
                || p.iter().any(|&v|v as f64<=FLOOR || v as f64>=SAMPLE_CEILING) {
                result.counts[2]+=1;continue;
            }
            let base=c[0]/c[2];let detail=f[0]/f[2];
            let sigma=(c[1]/c[2]-base*base).max(0.0).sqrt();
            result.metrics[0]=result.metrics[0].max((base-detail).abs());
            result.metrics[1]=result.metrics[1].max(sigma);
            let safety=taper(sigma,0.08,0.18);
            if safety<=0.0 {result.counts[2]+=1;continue;}
            let correction=(base-detail).clamp(-MAX_GAIN,MAX_GAIN)*safety*target[i] as f64;
            if !correction.is_finite() {return Err(7);}
            let v=if correction.abs()<1e-7 {0.0} else {correction as f32};
            result.field[3*i..3*i+3].fill(v);
            result.eligible[i]=1;result.counts[1]+=1;
            if v!=0.0 {result.counts[3]+=1;}
            result.metrics[2]=result.metrics[2].max((v as f64).abs());
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
        // A common luminance-only gain, never a chroma or geometry edit.
        if gain[0]!=gain[1] || gain[0]!=gain[2] {return Err(2);}
        let effective=[gain[0] as f64*amount;3];
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
pub unsafe extern "C" fn lrt_hand_tone_measure_v1(
 rgb:*const f32,rgb_len:usize,limb:*const f32,limb_len:usize,
 target:*const f32,target_len:usize,
 protect:*const u8,protect_len:usize,w:usize,h:usize,radius:usize,byte_budget:u64,
 field:*mut f32,field_len:usize,eligible:*mut u8,eligible_len:usize,
 counts:*mut u64,counts_len:usize,metrics:*mut f64,metrics_len:usize,
 cb:Cancel,ctx:*mut c_void)->i32 {
    match catch_unwind(AssertUnwindSafe(||->Result<()> {
        let n=dims(w,h)?;
        if rgb_len!=3*n || limb_len!=n || target_len!=n || protect_len!=n
            || field_len!=3*n || eligible_len!=n || counts_len!=4 || metrics_len!=4 {return Err(1);}
        if !(2..=128).contains(&radius) {return Err(3);}
        budget(n,160,8*1024*1024,byte_budget)?;
        let inputs=[range(rgb,rgb_len)?,range(limb,limb_len)?,range(target,target_len)?,range(protect,protect_len)?];
        let outputs=[range(field,field_len)?,range(eligible,eligible_len)?,range(counts,counts_len)?,range(metrics,metrics_len)?];
        disjoint(&inputs,&outputs)?;
        let r=measure(slice::from_raw_parts(rgb,rgb_len),slice::from_raw_parts(limb,n),slice::from_raw_parts(target,n),
                      slice::from_raw_parts(protect,n),w,h,radius,cb,ctx)?;
        cancelled(cb,ctx)?;
        std::ptr::copy_nonoverlapping(r.field.as_ptr(),field,field_len);
        std::ptr::copy_nonoverlapping(r.eligible.as_ptr(),eligible,n);
        std::ptr::copy_nonoverlapping(r.counts.as_ptr(),counts,4);
        std::ptr::copy_nonoverlapping(r.metrics.as_ptr(),metrics,4); Ok(())
    })) {Ok(Ok(()))=>0,Ok(Err(code))=>code,Err(_)=>8}
}

#[no_mangle]
pub unsafe extern "C" fn lrt_hand_tone_apply_v1(
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
