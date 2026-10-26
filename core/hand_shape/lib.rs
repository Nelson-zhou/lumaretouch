// SPDX-License-Identifier: GPL-3.0-or-later
//! Original compact hand-width geometry. AUTHORED / UNRUN.
//! Reviewed palm, phalanx and knuckle regions use the same numerical primitive;
//! their anatomical labels, provenance and protection belong to the host.
//! No pixels, model, inferred anatomy, allocation, compiler or image sampler.
use std::{mem, slice};

const STRIDE: usize = 7;
const MAX_PRIMITIVES: usize = 32;
const MAX_POINTS: usize = 1_048_576;
const MAX_DISPLACEMENT: f64 = 128.0;

#[derive(Clone, Copy)]
struct Primitive { cx:f64, cy:f64, ux:f64, uy:f64, a:f64, b:f64, k:f64 }
impl Primitive {
    const EMPTY:Self=Self{cx:0.,cy:0.,ux:1.,uy:0.,a:2.,b:2.,k:0.};
    fn read(s:&[f64], width:u32, height:u32)->Result<Self,i32> {
        if s.iter().any(|v| !v.is_finite()) { return Err(2); }
        let p=Self{cx:s[0],cy:s[1],ux:s[2],uy:s[3],a:s[4],b:s[5],k:s[6]};
        if (p.ux.hypot(p.uy)-1.).abs()>1e-10 || p.a<2. || p.b<2.
            || !(0.2..=5.).contains(&(p.a/p.b)) || p.k.abs()>0.12 { return Err(2); }
        // Normalize accepted roundoff once; determinant formula assumes unit axes.
        let norm=p.ux.hypot(p.uy);
        let p=Self{ux:p.ux/norm,uy:p.uy/norm,..p};
        let rx=(p.a*p.ux).hypot(p.b*p.uy);
        let ry=(p.a*p.uy).hypot(p.b*p.ux);
        if p.cx-rx<1. || p.cy-ry<1. || p.cx+rx>width as f64-2.
            || p.cy+ry>height as f64-2. { return Err(3); }
        Ok(p)
    }
    fn inverse(self,q:[f64;2])->([f64;2],f64) {
        if self.k==0. { return (q,1.); }
        let dx=q[0]-self.cx; let dy=q[1]-self.cy;
        let u=dx*self.ux+dy*self.uy; let v=-dx*self.uy+dy*self.ux;
        let vv=(v/self.b).powi(2); let r=(u/self.a).powi(2)+vv;
        if r>=1. { return (q,1.); }
        let t=1.-r; let shift=self.k*v*t*t*t;
        let det=1.+self.k*(t*t*t-6.*vv*t*t);
        ([q[0]-self.uy*shift,q[1]+self.ux*shift],det)
    }
}

fn evaluate(primitives:&[Primitive],q:[f64;2],width:u32,height:u32,budget:f64)->Result<([f64;2],f64),i32> {
    if q.iter().any(|v| !v.is_finite()) || q[0]<0. || q[1]<0.
        || q[0]>width as f64-1. || q[1]>height as f64-1. { return Err(3); }
    let mut p=q; let mut determinant=1.;
    for primitive in primitives {
        let (next,j)=primitive.inverse(p); p=next; determinant*=j;
        if p.iter().any(|v| !v.is_finite()) || !determinant.is_finite()
            || determinant<=0. { return Err(5); }
    }
    let delta=[q[0]-p[0],q[1]-p[1]];
    if !(0.25..=4.).contains(&determinant)
        || delta[0].hypot(delta[1])>budget+1e-9
        || p[0]<0. || p[1]<0. || p[0]>width as f64-1. || p[1]>height as f64-1. { return Err(5); }
    Ok((delta,determinant))
}

fn span(pointer:usize,len:usize)->Result<(usize,usize),i32> {
    if len==0 { return Ok((0,0)); }
    if pointer==0 || pointer%mem::align_of::<f64>()!=0 { return Err(1); }
    let bytes=len.checked_mul(mem::size_of::<f64>()).ok_or(1)?;
    if bytes>isize::MAX as usize { return Err(1); }
    Ok((pointer,pointer.checked_add(bytes).ok_or(1)?))
}
fn overlaps(a:(usize,usize),b:(usize,usize))->bool { a.0<a.1 && b.0<b.1 && a.0<b.1 && b.0<a.1 }

#[no_mangle]
pub extern "C" fn lrt_hand_shape_abi()->u32 { 1 }

/// Rows: center xy, unit longitudinal axis xy, longitudinal/transverse radii, k.
/// Positive k narrows displayed width; output is q-source(q), not source(q).
/// Composition is the supplied row order, evaluated off-grid, never summed LUTs.
/// Error: 1 buffer/schema, 2 primitive, 3 source domain, 4 budget, 5 map safety.
/// All failure paths preserve BOTH output arrays. Zero queries still check state.
///
/// # Safety
/// Caller supplies correctly allocated readable/writable f64 arrays of the exact
/// lengths below, kept alive and unmodified throughout this call. Numeric pointer
/// validation cannot establish allocation ownership or prevent concurrent writes.
#[no_mangle]
pub unsafe extern "C" fn lrt_hand_shape_evaluate(
    primitives:*const f64,primitives_len:usize,count:usize,width:u32,height:u32,
    max_displacement:f64,points:*const f64,points_len:usize,n:usize,
    out:*mut f64,out_len:usize,jac:*mut f64,jac_len:usize,
)->i32 {
    if count>MAX_PRIMITIVES || n>MAX_POINTS || primitives_len!=count*STRIDE
        || points_len!=n*2 || out_len!=n*2 || jac_len!=n
        || !(4..=1_000_000).contains(&width) || !(4..=1_000_000).contains(&height) { return 1; }
    if !max_displacement.is_finite() || !(0.0..=MAX_DISPLACEMENT).contains(&max_displacement) { return 4; }
    let spans=[span(primitives as usize,primitives_len),span(points as usize,points_len),
        span(out as usize,out_len),span(jac as usize,jac_len)];
    let mut ranges=[(0,0);4];
    for (i,result) in spans.into_iter().enumerate() {
        match result { Ok(value)=>ranges[i]=value,Err(code)=>return code }
    }
    for output in 2..4 { for other in 0..output {
        if overlaps(ranges[output],ranges[other]) { return 1; }
    }}
    let raw=if count==0 { &[][..] } else { slice::from_raw_parts(primitives,primitives_len) };
    let mut parsed=[Primitive::EMPTY;MAX_PRIMITIVES]; let mut bound=0.;
    for i in 0..count {
        match Primitive::read(&raw[i*STRIDE..(i+1)*STRIDE],width,height) {
            Ok(p)=>{parsed[i]=p;bound+=p.k.abs()*p.b;},Err(code)=>return code
        }
    }
    // Conservative, source-space triangle bound; no strength silently reduced.
    if !bound.is_finite() || bound>max_displacement+1e-12 { return 4; }
    let input=if n==0 { &[][..] } else { slice::from_raw_parts(points,points_len) };
    // No allocation or partial output: complete deterministic dry run first.
    for q in input.chunks_exact(2) {
        if let Err(code)=evaluate(&parsed[..count],[q[0],q[1]],width,height,max_displacement) { return code; }
    }
    if n==0 { return 0; }
    let output=slice::from_raw_parts_mut(out,out_len);
    let determinants=slice::from_raw_parts_mut(jac,jac_len);
    for (i,q) in input.chunks_exact(2).enumerate() {
        // Immutable validated state makes this the identical arithmetic as dry run.
        // Do not return after writing; the dry run has already admitted every row.
        let mut p=[q[0],q[1]]; let mut determinant=1.;
        for primitive in &parsed[..count] { let (next,j)=primitive.inverse(p);p=next;determinant*=j; }
        output[2*i]=q[0]-p[0];output[2*i+1]=q[1]-p[1];determinants[i]=determinant;
    }
    0
}

#[cfg(test)]
#[path="tests.rs"]
mod tests;
