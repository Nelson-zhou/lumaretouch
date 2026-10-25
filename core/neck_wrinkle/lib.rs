// SPDX-License-Identifier: AGPL-3.0-only
// Copyright Chris Cork. Adapted for LumaRetouch, 2026-10-25. See NOTICE and LICENSE.
//! Pinned RapidRetouch line/depth method translated to bounded source-grid Rust.
//! AUTHORED / UNRUN. Not neck detection, a photographic acceptance or GPL relicensing.
use std::{ffi::c_void, mem, panic, slice};

pub const ABI: u32 = 1;
pub const ALGORITHM: u32 = 1;
pub const MAX_PIXELS: usize = 32_000_000;
pub const MAX_DIMENSION: usize = 65_536;
pub const MAX_BYTES: u64 = 4 * 1024 * 1024 * 1024;
pub const ALLOWANCE: u64 = 8 * 1024 * 1024;
pub const ABI_ERROR: i32 = 1;
pub const INPUT_ERROR: i32 = 2;
pub const SCALE_ERROR: i32 = 3;
pub const CONTEXT_ERROR: i32 = 4;
pub const BUDGET_ERROR: i32 = 5;
pub const CANCELLED: i32 = 6;
pub const NUMERICAL_ERROR: i32 = 7;
pub const PANIC_ERROR: i32 = 8;
pub type Cancel = Option<extern "C" fn(*mut c_void) -> i32>;
#[derive(Clone, Copy, Debug)]
pub struct Rect { pub y: usize, pub x: usize, pub h: usize, pub w: usize }
#[derive(Clone, Copy, Debug)]
pub struct Policy { pub sigma: [f64; 3], pub close: usize, pub filled: usize,
    pub pore: usize, pub spread: usize, pub fold: usize, pub smooth: usize,
    pub radius: usize }

fn poll<F: FnMut() -> bool>(cancel: &mut F) -> Result<(), i32> {
    if cancel() { Err(CANCELLED) } else { Ok(()) }
}
fn allocated<T: Clone, F: FnMut() -> bool>(n: usize, v: T, cancel: &mut F) -> Result<Vec<T>, i32> {
    poll(cancel)?;
    let mut out = Vec::new();
    out.try_reserve_exact(n).map_err(|_| BUDGET_ERROR)?;
    for i in 0..n { if i % 4096 == 0 { poll(cancel)?; } out.push(v.clone()); }
    Ok(out)
}
fn dimensions(w: usize, h: usize) -> Result<usize, i32> {
    if w == 0 || h == 0 || w > MAX_DIMENSION || h > MAX_DIMENSION { return Err(ABI_ERROR); }
    let n = w.checked_mul(h).ok_or(BUDGET_ERROR)?;
    if n > MAX_PIXELS { return Err(BUDGET_ERROR); }
    Ok(n)
}
fn rectangle(r: Rect, w: usize, h: usize) -> Result<usize, i32> {
    let n = dimensions(r.w, r.h)?;
    if r.x.checked_add(r.w).ok_or(ABI_ERROR)? > w
        || r.y.checked_add(r.h).ok_or(ABI_ERROR)? > h { return Err(ABI_ERROR); }
    Ok(n)
}
pub fn policy(s: f64) -> Result<Policy, i32> {
    if !s.is_finite() || !(1.4..=12.0).contains(&s) { return Err(SCALE_ERROR); }
    let close = (2.5*s).ceil() as usize;
    let filled = (3.0*(0.5*s).max(0.5)).ceil() as usize;
    let pore = (3.0*(0.3*s).max(0.5)).ceil() as usize;
    let spread = (1.5*s).ceil() as usize;
    let fold = (3.0*s).ceil() as usize;
    let smooth = (3.0*s).ceil() as usize;
    let depth = 2*close + filled + pore;
    let line = smooth + 2 + spread + smooth;
    let radius = line.max(depth + fold + smooth);
    Ok(Policy { sigma: [0.5*s, 0.75*s, s], close, filled, pore, spread, fold, smooth, radius })
}
fn sample_rect(r: Rect, radius: usize, w: usize, h: usize) -> Rect {
    let x = r.x.saturating_sub(radius); let y = r.y.saturating_sub(radius);
    Rect { x, y, w: (r.x+r.w+radius).min(w)-x, h: (r.y+r.h+radius).min(h)-y }
}
pub fn required_bytes(n: usize, sample: usize, output: usize) -> Result<u64, i32> {
    // Resident caller RGB/weight/protection + private snapshots, native peak,
    // field output/private/immutable retention. Host adds all unrelated residents.
    (n as u64).checked_mul(34).and_then(|a| (sample as u64).checked_mul(80).and_then(|b| a.checked_add(b)))
        .and_then(|a| (output as u64).checked_mul(15).and_then(|b| a.checked_add(b)))
        .and_then(|a| a.checked_add(ALLOWANCE)).ok_or(BUDGET_ERROR)
}
fn admitted(v: f32) -> bool { v.is_finite() && (0.0..=1.0).contains(&v) }
fn smooth(v: f64, low: f64, high: f64) -> f64 {
    let t = ((v-low)/(high-low)).clamp(0.0,1.0); t*t*(3.0-2.0*t)
}
fn decode(v: f64) -> f64 {
    if v <= 0.04045 { v/12.92 } else { ((v+0.055)/1.055).powf(2.4) }
}
fn luminance(rgb: &[f32], i: usize) -> f64 {
    0.2126*decode(rgb[3*i] as f64)+0.7152*decode(rgb[3*i+1] as f64)+0.0722*decode(rgb[3*i+2] as f64)
}
fn line_response(xx: f64, yy: f64, xy: f64, sigma: f64) -> f64 {
    let half=(xx+yy)*0.5; let root=(((xx-yy)*0.5).powi(2)+xy*xy).sqrt();
    let (l1,l2)=(half+root,half-root);
    if l1<=0.0 { return 0.0; }
    sigma*sigma*l1*(1.0-(l2.abs()/l1.max(1e-6)).clamp(0.0,1.0))
}
fn lstar(y: f64) -> f64 {
    if y > 216.0/24389.0 { 116.0*y.cbrt()-16.0 } else { (24389.0/27.0)*y }
}
fn y_from_l(l: f64) -> f64 {
    if l > 8.0 { ((l+16.0)/116.0).powi(3) } else { l/(24389.0/27.0) }
}

/// Finite square Gaussian; only complete pass windows are evaluated. All other
/// positions stay zero and are excluded by the complete composed target erosion.
fn gaussian<F: FnMut() -> bool>(input: &[f64], w: usize, h: usize, sigma: f64,
    cancel: &mut F) -> Result<Vec<f64>, i32> {
    let r = (3.0*sigma).ceil() as usize;
    let mut kernel = allocated(2*r+1, 0.0, cancel)?;
    let mut sum = 0.0;
    for (k, v) in kernel.iter_mut().enumerate() {
        let x = k as f64-r as f64; *v = (-x*x/(2.0*sigma*sigma)).exp(); sum += *v;
    }
    for v in &mut kernel { *v /= sum; }
    let mut tmp = allocated(w*h,0.0,cancel)?;
    let mut out = allocated(w*h,0.0,cancel)?;
    if w > 2*r && h > 2*r {
        for y in 0..h {
            poll(cancel)?;
            for x in r..w-r {
                if x % 256 == 0 { poll(cancel)?; }
                let mut value = 0.0;
                for k in 0..2*r+1 { value += input[y*w+x+k-r]*kernel[k]; }
                tmp[y*w+x] = value;
            }
        }
        for y in r..h-r {
            poll(cancel)?;
            for x in r..w-r {
                if x % 256 == 0 { poll(cancel)?; }
                let mut value = 0.0;
                for k in 0..2*r+1 { value += tmp[(y+k-r)*w+x]*kernel[k]; }
                out[y*w+x] = value;
            }
        }
    }
    Ok(out)
}
/// Explicit separable square maximum/minimum. A complete footprint is mandatory.
fn extremum<F: FnMut() -> bool>(input: &[f64], w: usize, h: usize, r: usize,
    maximum: bool, cancel: &mut F) -> Result<Vec<f64>, i32> {
    let mut tmp = allocated(w*h,0.0,cancel)?;
    let mut out = allocated(w*h,0.0,cancel)?;
    if w > 2*r && h > 2*r {
        for y in 0..h {
            poll(cancel)?;
            for x in r..w-r {
                if x % 256 == 0 { poll(cancel)?; }
                let mut v = input[y*w+x-r];
                for k in x-r+1..=x+r { v = if maximum { v.max(input[y*w+k]) } else { v.min(input[y*w+k]) }; }
                tmp[y*w+x] = v;
            }
        }
        for y in r..h-r {
            poll(cancel)?;
            for x in r..w-r {
                if x % 256 == 0 { poll(cancel)?; }
                let mut v = tmp[(y-r)*w+x];
                for k in y-r+1..=y+r { v = if maximum { v.max(tmp[k*w+x]) } else { v.min(tmp[k*w+x]) }; }
                out[y*w+x] = v;
            }
        }
    }
    Ok(out)
}
fn context_mask<F: FnMut() -> bool>(weight: &[f32], protect: &[u8], source_w: usize,
    sample: Rect, r: usize, cancel: &mut F) -> Result<Vec<u8>, i32> {
    let (w,h) = (sample.w,sample.h);
    let mut horizontal = allocated(w*h,0_u32,cancel)?;
    let mut out = allocated(w*h,0_u8,cancel)?;
    if w <= 2*r || h <= 2*r { return Ok(out); }
    let bad = |y: usize,x: usize| -> u32 {
        let j = (y+sample.y)*source_w+x+sample.x;
        u32::from(weight[j] <= 0.0 || protect[j] != 0)
    };
    for y in 0..h {
        poll(cancel)?;
        let mut count = 0;
        for x in 0..=2*r { count += bad(y,x); }
        for x in r..w-r {
            if x % 256 == 0 { poll(cancel)?; }
            horizontal[y*w+x] = count;
            if x+r+1 < w { count -= bad(y,x-r); count += bad(y,x+r+1); }
        }
    }
    for x in r..w-r {
        poll(cancel)?;
        let mut count = 0;
        for y in 0..=2*r { count += horizontal[y*w+x]; }
        for y in r..h-r {
            if y % 256 == 0 { poll(cancel)?; }
            out[y*w+x] = u8::from(count == 0);
            if y+r+1 < h { count -= horizontal[(y-r)*w+x]; count += horizontal[(y+r+1)*w+x]; }
        }
    }
    Ok(out)
}

pub struct Measurement { pub field: Vec<f32>, pub eligible: Vec<u8>, pub counts: [u64;4], pub metrics: [f64;2] }
fn measure_inner<F: FnMut() -> bool>(rgb: &[f32], weight: &[f32], protect: &[u8],
    w: usize, h: usize, window: Rect, s: f64, budget: u64, cancel: &mut F) -> Result<Measurement,i32> {
    let n = dimensions(w,h)?; let out_n = rectangle(window,w,h)?;
    let p = policy(s)?; let sample = sample_rect(window,p.radius,w,h);
    let need = required_bytes(n,sample.w*sample.h,out_n)?;
    if need > budget || need > MAX_BYTES { return Err(BUDGET_ERROR); }
    if rgb.len()!=3*n || weight.len()!=n || protect.len()!=n { return Err(ABI_ERROR); }
    for i in 0..n {
        if i % 4096 == 0 { poll(cancel)?; }
        if !weight[i].is_finite() || !admitted(weight[i]) || protect[i]>1
            || !rgb[3*i..3*i+3].iter().copied().all(admitted) { return Err(INPUT_ERROR); }
        // Do not accept a truncated candidate extent that omits positive support.
        if weight[i]>0.0 && protect[i]==0 {
            let (y,x) = (i/w,i%w);
            if y<window.y || x<window.x || y>=window.y+window.h || x>=window.x+window.w { return Err(INPUT_ERROR); }
        }
    }
    let owned = context_mask(weight,protect,w,sample,p.radius,cancel)?;
    let mut counts = [0_u64;4];
    for y in 0..window.h {
        poll(cancel)?;
        for x in 0..window.w {
            let j=(y+window.y)*w+x+window.x;
            let i=(y+window.y-sample.y)*sample.w+x+window.x-sample.x;
            if weight[j]>0.0 && protect[j]==0 {
                if owned[i]!=0 { counts[0]+=1; } else { counts[1]+=1; }
            }
        }
    }
    if counts[0]==0 { return Err(CONTEXT_ERROR); }
    let (sw,sh)=(sample.w,sample.h); let sn=sw*sh;
    let mut light = allocated(sn,0.0,cancel)?;
    for y in 0..sh {
        poll(cancel)?;
        for x in 0..sw {
            if x % 256 == 0 { poll(cancel)?; }
            let j=(y+sample.y)*w+x+sample.x;
            // Invalid samples are never donor observations; complete-footprint
            // erosion ensures these placeholders cannot affect admitted outputs.
            if weight[j]>0.0 && protect[j]==0 { light[y*sw+x]=lstar(luminance(rgb,j)); }
        }
    }
    let mut strength = allocated(sn,0.0_f64,cancel)?;
    for sigma in p.sigma {
        let g=gaussian(&light,sw,sh,sigma,cancel)?;
        if sw>4 && sh>4 {
            for y in 2..sh-2 {
                poll(cancel)?;
                for x in 2..sw-2 {
                    if x % 256 == 0 { poll(cancel)?; }
                    let i=y*sw+x;
                    // Two central finite-difference gradient passes: radius 2.
                    let xx=(g[i+2]-2.0*g[i]+g[i-2])*0.25;
                    let yy=(g[i+2*sw]-2.0*g[i]+g[i-2*sw])*0.25;
                    let xy=(g[i+sw+1]-g[i+sw-1]-g[i-sw+1]+g[i-sw-1])*0.25;
                    strength[i]=strength[i].max(line_response(xx,yy,xy,sigma));
                }
            }
        }
    }
    for (i,v) in strength.iter_mut().enumerate() {
        if i%4096==0 { poll(cancel)?; } *v=smooth(*v,0.4,1.1);
    }
    let spread=extremum(&strength,sw,sh,p.spread,true,cancel)?;
    drop(strength);
    let line=gaussian(&spread,sw,sh,s,cancel)?; drop(spread);
    let dilated=extremum(&light,sw,sh,p.close,true,cancel)?;
    let closed=extremum(&dilated,sw,sh,p.close,false,cancel)?; drop(dilated);
    let mut filled=gaussian(&closed,sw,sh,(0.5*s).max(0.5),cancel)?; drop(closed);
    for i in 0..sn { if i%4096==0 { poll(cancel)?; } filled[i]=(filled[i]-light[i]).max(0.0); }
    let depth=gaussian(&filled,sw,sh,(0.3*s).max(0.5),cancel)?; drop(filled);
    let near_max=extremum(&depth,sw,sh,p.fold,true,cancel)?;
    let near=gaussian(&near_max,sw,sh,s,cancel)?; drop(near_max);
    let mut field=allocated(out_n,0.0_f32,cancel)?;
    let mut eligible=allocated(out_n,0_u8,cancel)?; let mut metrics=[0.0_f64;2];
    for y in 0..window.h {
        poll(cancel)?;
        for x in 0..window.w {
            if x%256==0 { poll(cancel)?; }
            let i=(y+window.y-sample.y)*sw+x+window.x-sample.x;
            if owned[i]==0 { continue; }
            eligible[y*window.w+x]=1;
            let j=(y+window.y)*w+x+window.x;
            if line[i]<=0.0 || depth[i]<=1e-6 { continue; }
            counts[2]+=1;
            let fold=1.0-0.6*smooth(near[i],8.0,18.0);
            let not_hair=1.0-smooth(depth[i],22.0,30.0);
            let lift=(depth[i]*line[i]*fold*not_hair*(weight[j] as f64)).min(6.0);
            metrics[0]=metrics[0].max(lift);
            let old_y=luminance(rgb,j);
            if lift<=1e-6 || old_y<=1e-8 { continue; }
            let gain=(y_from_l((light[i]+lift).min(100.0))/old_y).min(1.25);
            if !gain.is_finite() || gain<1.0 { return Err(NUMERICAL_ERROR); }
            let value=gain.ln() as f32;
            if value>0.0 { field[y*window.w+x]=value; counts[3]+=1; metrics[1]=metrics[1].max(value as f64); }
        }
    }
    poll(cancel)?;
    Ok(Measurement {field,eligible,counts,metrics})
}

fn apply_inner<F: FnMut() -> bool>(rgb: &[f32], field: &[f32], amount: f64,
    cancel: &mut F) -> Result<Vec<f32>,i32> {
    if !amount.is_finite() || !(0.0..=1.0).contains(&amount) { return Err(INPUT_ERROR); }
    if rgb.len()!=3*field.len() || field.len()>MAX_PIXELS { return Err(ABI_ERROR); }
    if 56*(field.len() as u64)+ALLOWANCE>MAX_BYTES { return Err(BUDGET_ERROR); }
    let mut out=allocated(rgb.len(),0.0_f32,cancel)?;
    for i in 0..field.len() {
        if i%256==0 { poll(cancel)?; }
        let src=&rgb[3*i..3*i+3];
        if !src.iter().copied().all(admitted) || !field[i].is_finite()
            || field[i]<0.0 || field[i] as f64>1.25_f64.ln()+1e-8 { return Err(INPUT_ERROR); }
        out[3*i..3*i+3].copy_from_slice(src);
        let peak=src.iter().copied().fold(0.0_f32,f32::max) as f64;
        if amount==0.0 || field[i]==0.0 || peak==0.0 || peak>=1.0 { continue; }
        let gain=((field[i] as f64)*amount).exp().min(1.0+(1.0/peak-1.0)*(1.0-1e-12));
        if gain<=1.0 { continue; }
        for c in 0..3 {
            let v=((src[c] as f64)*gain) as f32;
            if !admitted(v) { return Err(NUMERICAL_ERROR); }
            out[3*i+c]=v;
        }
    }
    poll(cancel)?; Ok(out)
}

fn buffer<T>(p: *const T, len: usize) -> Result<(usize,usize),i32> {
    if p.is_null() || (p as usize)%mem::align_of::<T>()!=0 || len==0 { return Err(ABI_ERROR); }
    let bytes=len.checked_mul(mem::size_of::<T>()).ok_or(ABI_ERROR)?;
    if bytes>isize::MAX as usize { return Err(ABI_ERROR); }
    let start=p as usize; Ok((start,start.checked_add(bytes).ok_or(ABI_ERROR)?))
}
fn separate(ranges: &[(usize,usize)]) -> Result<(),i32> {
    for (i,a) in ranges.iter().enumerate() { for b in &ranges[i+1..] {
        if a.0<b.1 && b.0<a.1 { return Err(ABI_ERROR); }
    }} Ok(())
}
#[no_mangle]
pub extern "C" fn lrt_neck_wrinkle_abi() -> u32 { ABI }
#[no_mangle]
pub extern "C" fn lrt_neck_wrinkle_algorithm() -> u32 { ALGORITHM }
/// Safety: pointers are live, aligned allocations of the stated length. Inputs
/// are immutable for the call; outputs exclusive. The callback cannot unwind,
/// mutate/reenter the core or release buffers. Foreign faults are not catchable.
#[no_mangle]
pub unsafe extern "C" fn lrt_neck_wrinkle_measure_v1(
    rgb: *const f32, rgb_len: usize, weight: *const f32, weight_len: usize,
    protect: *const u8, protect_len: usize, w: usize, h: usize,
    wy: usize, wx: usize, wh: usize, ww: usize, half_width: f64, budget: u64,
    output: *mut f32, output_len: usize, eligible: *mut u8, eligible_len: usize,
    counts: *mut u64, counts_len: usize,
    metrics: *mut f64, metrics_len: usize, callback: Cancel, context: *mut c_void) -> i32 {
    let run=|| -> Result<(),i32> {
        let n=dimensions(w,h)?; let window=Rect{y:wy,x:wx,h:wh,w:ww};
        let out_n=rectangle(window,w,h)?;
        if rgb_len!=n.checked_mul(3).ok_or(ABI_ERROR)? || weight_len!=n || protect_len!=n
            || output_len!=out_n || eligible_len!=out_n || counts_len!=4 || metrics_len!=2 { return Err(ABI_ERROR); }
        separate(&[buffer(rgb,rgb_len)?,buffer(weight,weight_len)?,buffer(protect,protect_len)?,
            buffer(output,output_len)?,buffer(eligible,eligible_len)?,buffer(counts,counts_len)?,buffer(metrics,metrics_len)?])?;
        let mut cancel=|| callback.map(|f| f(context)!=0).unwrap_or(false);
        poll(&mut cancel)?;
        let result=measure_inner(slice::from_raw_parts(rgb,rgb_len),slice::from_raw_parts(weight,weight_len),
            slice::from_raw_parts(protect,protect_len),w,h,window,half_width,budget,&mut cancel)?;
        // Commit point: no polls/fallible work after this check. Error paths leave
        // caller output and statistics untouched, never a partially solved field.
        poll(&mut cancel)?;
        std::ptr::copy_nonoverlapping(result.field.as_ptr(),output,output_len);
        std::ptr::copy_nonoverlapping(result.eligible.as_ptr(),eligible,eligible_len);
        std::ptr::copy_nonoverlapping(result.counts.as_ptr(),counts,4);
        std::ptr::copy_nonoverlapping(result.metrics.as_ptr(),metrics,2);
        Ok(())
    };
    match panic::catch_unwind(panic::AssertUnwindSafe(run)) { Ok(Ok(()))=>0,Ok(Err(e))=>e,Err(_)=>PANIC_ERROR }
}
#[no_mangle]
pub unsafe extern "C" fn lrt_neck_wrinkle_apply_v1(rgb: *const f32, rgb_len: usize,
    field: *const f32, field_len: usize, w: usize, h: usize, amount: f64,
    output: *mut f32, output_len: usize, callback: Cancel, context: *mut c_void) -> i32 {
    let run=|| -> Result<(),i32> {
        let n=dimensions(w,h)?;
        if field_len!=n || rgb_len!=3*n || output_len!=rgb_len { return Err(ABI_ERROR); }
        separate(&[buffer(rgb,rgb_len)?,buffer(field,field_len)?,buffer(output,output_len)?])?;
        let mut cancel=|| callback.map(|f| f(context)!=0).unwrap_or(false);
        let result=apply_inner(slice::from_raw_parts(rgb,rgb_len),slice::from_raw_parts(field,field_len),amount,&mut cancel)?;
        poll(&mut cancel)?;
        std::ptr::copy_nonoverlapping(result.as_ptr(),output,output_len);
        Ok(())
    };
    match panic::catch_unwind(panic::AssertUnwindSafe(run)) { Ok(Ok(()))=>0,Ok(Err(e))=>e,Err(_)=>PANIC_ERROR }
}
#[cfg(test)]
mod tests;
