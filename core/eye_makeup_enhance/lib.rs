// SPDX-License-Identifier: GPL-3.0-or-later
//! Original reviewed existing-eye-makeup two-scale Oklab operation. UNRUN.
//! Independent source pigment/lightness/structure adjustment, no synthesized
//! cosmetic shape, anatomical warp, face detection, or unseen skin recovery.
//! Oklab equations: Björn Ottosson (2020), public domain / MIT, see THIRD_PARTY.
use std::{ffi::c_void, mem, panic, slice};

pub const MAX_PIXELS: usize = 4_000_000;
pub const MAX_DIMENSION: usize = 65_536;
pub const MAX_RADIUS: usize = 64;
pub const ABI: i32 = 1;
pub const SETTINGS: i32 = 2;
pub const PIXELS: i32 = 3;
pub const CANCELLED: i32 = 4;
pub const RESOURCE: i32 = 5;
pub const PANIC: i32 = 6;
pub const REFERENCE: i32 = 7;
pub const SUPPORT: i32 = 8;
pub type Cancel = Option<extern "C" fn(*mut c_void) -> i32>;
type Lab = [f64; 3];
type Sum = [f64; 5]; // weighted L,a,b, coverage mass, strictly positive footprint count

fn poll<F: FnMut() -> bool>(cancel: &mut F) -> Result<(), i32> {
    if cancel() { Err(CANCELLED) } else { Ok(()) }
}
fn unit(v: f32) -> bool { v.is_finite() && (0.0..=1.0).contains(&v) }
fn decode(v: f64) -> f64 {
    if v <= 0.04045 { v / 12.92 } else { ((v + 0.055) / 1.055).powf(2.4) }
}
fn encode(v: f64) -> f32 {
    (if v <= 0.0031308 { 12.92*v } else { 1.055*v.powf(1.0/2.4)-0.055 }) as f32
}
fn lab(rgb: [f32; 3]) -> Lab {
    let [r,g,b] = rgb.map(|v| decode(f64::from(v)));
    let l = (0.4122214708*r+0.5363325363*g+0.0514459929*b).cbrt();
    let m = (0.2119034982*r+0.6806995451*g+0.1073969566*b).cbrt();
    let s = (0.0883024619*r+0.2817188376*g+0.6299787005*b).cbrt();
    [0.2104542553*l+0.7936177850*m-0.0040720468*s,
     1.9779984951*l-2.4285922050*m+0.4505937099*s,
     0.0259040371*l+0.7827717662*m-0.8086757660*s]
}
fn rgb([l,a,b]: Lab) -> Lab {
    let x = (l+0.3963377774*a+0.2158037573*b).powi(3);
    let y = (l-0.1055613458*a-0.0638541728*b).powi(3);
    let z = (l-0.0894841775*a-1.2914855480*b).powi(3);
    [4.0767416621*x-3.3077115913*y+0.2309699292*z,
     -1.2684380046*x+2.6097574011*y-0.3413193965*z,
     -0.0041960863*x-0.7034186147*y+1.7076147010*z]
}
fn gamut(v: Lab) -> bool { v.iter().all(|x| x.is_finite() && (0.0..=1.0).contains(x)) }
fn owned<T: Clone>(len: usize, value: T) -> Result<Vec<T>, i32> {
    let mut out = Vec::new();
    out.try_reserve_exact(len).map_err(|_| RESOURCE)?;
    out.resize(len, value);
    Ok(out)
}
fn integral<F: FnMut() -> bool>(values: &[Lab], mask: &[f32], w: usize, h: usize, cancel: &mut F) -> Result<Vec<Sum>, i32> {
    let size = (w+1).checked_mul(h+1).ok_or(RESOURCE)?;
    let mut out = owned(size, [0.0;5])?;
    for y in 0..h {
        poll(cancel)?;
        let mut row = [0.0;5];
        for x in 0..w {
            if x % 256 == 0 { poll(cancel)?; }
            let i = y*w+x; let a = f64::from(mask[i]);
            for k in 0..3 { row[k] += a*values[i][k]; }
            row[3] += a; row[4] += if a > 0.0 { 1.0 } else { 0.0 };
            for k in 0..5 { out[(y+1)*(w+1)+x+1][k] = out[y*(w+1)+x+1][k]+row[k]; }
        }
    }
    Ok(out)
}
fn mean(prefix: &[Sum], x: usize, y: usize, r: usize, w: usize, h: usize) -> Option<Lab> {
    if x < r || y < r || x+r >= w || y+r >= h { return None; }
    let left=x-r; let top=y-r; let right=x+r+1; let bottom=y+r+1; let stride=w+1;
    let sum: Sum = std::array::from_fn(|k| prefix[bottom*stride+right][k]-prefix[top*stride+right][k]
        -prefix[bottom*stride+left][k]+prefix[top*stride+left][k]);
    // Every sample must be genuine visible permitted makeup. No reflected,
    // clamped, hidden or protected samples fill a missing footprint.
    let area=((2*r+1)*(2*r+1)) as f64;
    if sum[4] < area-0.25 || sum[3] < 1.0 || !sum.iter().all(|v| v.is_finite()) { return None; }
    Some(std::array::from_fn(|k| sum[k]/sum[3]))
}
fn reference<F: FnMut() -> bool>(values: &[Lab], a: &[f32], b: &[f32], cancel: &mut F) -> Result<Lab,i32> {
    let mut means = [[0.0;3];2];
    for (j, mask) in [a,b].iter().enumerate() {
        let mut mass=0.0; let mut squares=[0.0;3]; let mut n=0;
        for (i,&v) in mask.iter().enumerate() {
            if i % 256 == 0 { poll(cancel)?; }
            if v == 0.0 { continue; }
            let weight=f64::from(v); mass+=weight; n+=1;
            for k in 0..3 { means[j][k]+=weight*values[i][k]; squares[k]+=weight*values[i][k]*values[i][k]; }
        }
        if n < 16 || mass < 12.0 { return Err(REFERENCE); }
        for k in 0..3 {
            means[j][k]/=mass;
            let var=squares[k]/mass-means[j][k]*means[j][k];
            let limit=if k==0 {0.045_f64} else {0.025_f64};
            if !var.is_finite() || var < -1e-10 || var > limit*limit { return Err(REFERENCE); }
        }
        if !(0.2..=0.92).contains(&means[j][0]) { return Err(REFERENCE); }
    }
    if (means[0][0]-means[1][0]).abs() > 0.035
        || ((means[0][1]-means[1][1]).powi(2)+(means[0][2]-means[1][2]).powi(2)).sqrt() > 0.025 {
        return Err(REFERENCE);
    }
    Ok(std::array::from_fn(|k| (means[0][k]+means[1][k])*0.5))
}
fn adjusted(original: [f32;3], value: Lab, delta: Lab) -> Result<[f32;3],i32> {
    if delta.iter().all(|v| *v==0.0) { return Ok(original); }
    let candidate=|gain:f64| rgb(std::array::from_fn(|k| value[k]+gain*delta[k]));
    let requested=candidate(1.0);
    if gamut(requested) { return Ok(requested.map(encode)); }
    // Conservative segment compression in Lab, never component clipping. The
    // original encoded pixel remains exact if even the small step is infeasible.
    let mut lo=0.0; let mut hi=1.0;
    for _ in 0..28 { let mid=(lo+hi)*0.5; if gamut(candidate(mid)) {lo=mid;} else {hi=mid;} }
    if lo < 1e-7 { return Ok(original); }
    let feasible=candidate(lo*(1.0-1e-9));
    if !gamut(feasible) { return Err(PIXELS); }
    Ok(feasible.map(encode))
}

/// Source-only, complete-window evaluation. Controls: amount/saturation/lightness/structure.
/// No output publication on failure; caller-provided output untouched until final poll.
pub fn apply_into<F: FnMut() -> bool>(source: &[f32], coverage: &[f32], reference_a: &[f32], reference_b: &[f32],
    width: usize, height: usize, controls: [f32;4], radius: usize, output: &mut [f32], mut cancel: F) -> Result<(),i32> {
    if width==0 || height==0 || width>MAX_DIMENSION || height>MAX_DIMENSION { return Err(ABI); }
    let n=width.checked_mul(height).ok_or(RESOURCE)?; let rgbn=n.checked_mul(3).ok_or(RESOURCE)?;
    if n>MAX_PIXELS { return Err(RESOURCE); }
    if source.len()!=rgbn || output.len()!=rgbn || coverage.len()!=n || reference_a.len()!=n || reference_b.len()!=n {return Err(ABI);}
    if radius==0 || radius>MAX_RADIUS || !controls.iter().all(|v| v.is_finite() && (-1.0..=1.0).contains(v)) {return Err(SETTINGS);}
    poll(&mut cancel)?;
    for i in 0..n {
        if i%256==0 {poll(&mut cancel)?;}
        if !source[3*i..3*i+3].iter().copied().all(unit) || !unit(coverage[i]) || !unit(reference_a[i]) || !unit(reference_b[i]) {return Err(PIXELS);}
        if (coverage[i]>0.0 && (reference_a[i]>0.0 || reference_b[i]>0.0)) || (reference_a[i]>0.0 && reference_b[i]>0.0) {return Err(REFERENCE);}
    }
    if controls.iter().all(|v| *v==0.0) {poll(&mut cancel)?;output.copy_from_slice(source);return Ok(());}
    let mut values=owned(n,[0.0;3])?;
    for i in 0..n {if i%256==0 {poll(&mut cancel)?;} values[i]=lab([source[3*i],source[3*i+1],source[3*i+2]]);}
    let clean=if controls[0]!=0.0 {reference(&values,reference_a,reference_b,&mut cancel)?} else {[0.0;3]};
    let prefix=integral(&values,coverage,width,height,&mut cancel)?;
    let mut result=owned(rgbn,0.0_f32)?;result.copy_from_slice(source);
    let mut admitted=0; let mut amount_admitted=0; let mut structure_admitted=0;
    for y in 0..height {
        poll(&mut cancel)?;
        for x in 0..width {
            if x%256==0 {poll(&mut cancel)?;}
            let i=y*width+x; let weight=f64::from(coverage[i]); if weight==0.0 {continue;}
            // Glints, clipped colour and deep shadow have no dependable visible-pigment evidence.
            if source[3*i..3*i+3].iter().any(|v| *v<=0.005 || *v>=0.985) {continue;}
            let base=match mean(&prefix,x,y,radius,width,height) {Some(v)=>v,None=>continue};
            let broad=if controls[3]!=0.0 {match mean(&prefix,x,y,radius*3,width,height) {Some(v)=>v,None=>continue}} else {base};
            admitted+=1;
            let residual:Lab=std::array::from_fn(|k| base[k]-clean[k]);
            let contrast=(residual[0]*residual[0]+residual[1]*residual[1]+residual[2]*residual[2]).sqrt();
            let mut delta=[0.0;3];
            if controls[0]!=0.0 && contrast>=0.015 && contrast<=0.25 {
                // Both signs scale ONLY measured low-frequency makeup/reference difference.
                // Negative is bounded appearance attenuation, never a bare-skin reconstruction.
                amount_admitted+=1;
                for k in 0..3 {delta[k]+=0.45*f64::from(controls[0])*residual[k];}
            }
            delta[1]+=0.40*f64::from(controls[1])*base[1];
            delta[2]+=0.40*f64::from(controls[1])*base[2];
            delta[0]+=0.075*f64::from(controls[2]);
            let structure=base[0]-broad[0];
            if controls[3]!=0.0 && structure.abs()>0.0002 {structure_admitted+=1;}
            delta[0]+=0.65*f64::from(controls[3])*structure;
            for d in &mut delta {*d*=weight;}
            if !delta.iter().all(|v| v.is_finite()) {return Err(PIXELS);}
            let pixel=adjusted([source[3*i],source[3*i+1],source[3*i+2]],values[i],delta)?;
            if !pixel.iter().copied().all(unit) {return Err(PIXELS);}
            result[3*i..3*i+3].copy_from_slice(&pixel);
        }
    }
    if admitted<16 {return Err(SUPPORT);}
    if controls[0]!=0.0 && amount_admitted<16 {return Err(REFERENCE);}
    if controls[3]!=0.0 && structure_admitted<8 {return Err(SUPPORT);}
    poll(&mut cancel)?;output.copy_from_slice(&result);Ok(())
}
fn range(ptr: *const f32, len:usize) -> Option<(usize,usize)> {
    let start=ptr as usize; let bytes=len.checked_mul(mem::size_of::<f32>())?;
    if ptr.is_null() || start%mem::align_of::<f32>()!=0 || bytes>isize::MAX as usize {return None;}
    Some((start,start.checked_add(bytes)?))
}
fn overlap(a:(usize,usize),b:(usize,usize))->bool {a.0<b.1 && b.0<a.1}
#[no_mangle]
pub extern "C" fn lrt_eye_makeup_enhance_abi()->u32 {1}
/// # Safety
/// Every pointer must denote a valid live allocation for its explicit count;
/// output must not overlap ANY input. Host holds all allocations immutably until return.
#[no_mangle]
pub unsafe extern "C" fn lrt_eye_makeup_enhance_apply_v1(source:*const f32, source_len:usize,
    coverage:*const f32, coverage_len:usize, reference_a:*const f32, reference_a_len:usize,
    reference_b:*const f32, reference_b_len:usize, width:usize, height:usize,
    amount:f32,saturation:f32,brightness:f32,structure:f32,radius:usize,
    output:*mut f32,output_len:usize,cancel:Cancel,context:*mut c_void)->i32 {
    let result=panic::catch_unwind(panic::AssertUnwindSafe(|| {
        if width==0 || height==0 || width>MAX_DIMENSION || height>MAX_DIMENSION {return Err(ABI);}
        let n=width.checked_mul(height).ok_or(RESOURCE)?;
        if n>MAX_PIXELS || n.checked_mul(3)!=Some(source_len) || output_len!=source_len
            || coverage_len!=n || reference_a_len!=n || reference_b_len!=n {return Err(ABI);}
        let out=range(output,output_len).ok_or(ABI)?;
        for (ptr,len) in [(source,source_len),(coverage,coverage_len),(reference_a,reference_a_len),(reference_b,reference_b_len)] {
            if overlap(out,range(ptr,len).ok_or(ABI)?) {return Err(ABI);}
        }
        apply_into(slice::from_raw_parts(source,source_len),slice::from_raw_parts(coverage,coverage_len),
            slice::from_raw_parts(reference_a,reference_a_len),slice::from_raw_parts(reference_b,reference_b_len),
            width,height,[amount,saturation,brightness,structure],radius,slice::from_raw_parts_mut(output,output_len),
            ||cancel.map_or(false,|f|f(context)!=0))
    }));
    match result {Ok(Ok(()))=>0,Ok(Err(code))=>code,Err(_)=>PANIC}
}
#[cfg(test)] mod tests;
