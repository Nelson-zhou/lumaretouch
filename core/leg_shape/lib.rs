// SPDX-License-Identifier: GPL-3.0-or-later
//! Original compact C2 transverse inverse maps on reviewed, visible leg axes.
//! No image sampler, synthetic anatomy, demographic inference or model download.
//! Evaluation is off-grid composition in frozen left/right thigh then calf order.
use std::slice;
const ANCHORS: [usize; 6] = [23, 24, 25, 26, 27, 28];
const JOINTS: [(usize, usize); 4] = [(23, 25), (24, 26), (25, 27), (26, 28)];
const GAIN: f64 = 0.25; // Original implementation policy, not a PixCake number.
#[derive(Clone, Copy, Debug)]
struct V { x: f64, y: f64 }
impl V {
 fn new(x:f64,y:f64)->Self { Self{x,y} }
 fn add(self,b:Self)->Self { Self::new(self.x+b.x,self.y+b.y) }
 fn sub(self,b:Self)->Self { Self::new(self.x-b.x,self.y-b.y) }
 fn mul(self,n:f64)->Self { Self::new(self.x*n,self.y*n) }
 fn dot(self,b:Self)->f64 { self.x*b.x+self.y*b.y }
 fn len(self)->f64 { self.dot(self).sqrt() }
}
#[derive(Clone, Copy)]
struct Segment { a:V, u:V, length:f64, radius:f64, amount:f64 }
impl Segment {
 fn n(self)->V { V::new(-self.u.y,self.u.x) }
 fn coordinates(self,p:V)->(f64,f64) { let d=p.sub(self.a); (d.dot(self.u)/self.length,d.dot(self.n())) }
 fn contains(self,p:V)->bool { let (t,v)=self.coordinates(p); t>0. && t<1. && v.abs()<self.radius }
 fn inverse(self,q:V)->Result<(V,f64),i32> {
  let (t,v)=self.coordinates(q);
  if self.amount==0. || t<=0. || t>=1. || v.abs()>=self.radius { return Ok((q,1.)); }
  let s=v/self.radius; let edge=1.-s*s;
  let axial=64.*t.powi(3)*(1.-t).powi(3);
  let coefficient=GAIN*self.amount*axial;
  // p = q + n*k*v*f(t)*g(v). Positive amount pulls visible output inward.
  let p=q.add(self.n().mul(coefficient*v*edge.powi(3)));
  let determinant=1.+coefficient*edge.powi(2)*(1.-7.*s*s);
  if !p.x.is_finite() || !p.y.is_finite() || !determinant.is_finite() || !(0.70..=1.30).contains(&determinant) { return Err(9); }
  Ok((p,determinant))
 }
}
fn read_state(s:&[f64])->Result<[Segment;4],i32> {
 if s.len()!=28 || s.iter().any(|v|!v.is_finite()) { return Err(1); }
 let blank=Segment{a:V::new(0.,0.),u:V::new(1.,0.),length:1.,radius:1.,amount:0.};
 let mut segments=[blank;4];
 for (i,seg) in segments.iter_mut().enumerate() {
  let p=&s[i*7..i*7+7]; *seg=Segment{a:V::new(p[0],p[1]),u:V::new(p[2],p[3]),length:p[4],radius:p[5],amount:p[6]};
  if (seg.u.len()-1.).abs()>1e-8 || seg.length<16. || seg.radius<2. || seg.radius>seg.length*0.5 || seg.amount.abs()>1. { return Err(1); }
 }
 Ok(segments)
}
fn point_segment_distance(p:V,a:V,b:V)->f64 { let v=b.sub(a); let t=(p.sub(a).dot(v)/v.dot(v)).clamp(0.,1.); p.sub(a.add(v.mul(t))).len() }
fn cross(a:V,b:V)->f64 { a.x*b.y-a.y*b.x }
fn segment_distance(a:V,b:V,c:V,d:V)->f64 {
 let ab=b.sub(a); let cd=d.sub(c); let denominator=cross(ab,cd);
 if denominator.abs()>1e-10 { let t=cross(c.sub(a),cd)/denominator; let u=cross(c.sub(a),ab)/denominator; if (0.0..=1.0).contains(&t)&&(0.0..=1.0).contains(&u) {return 0.;} }
 point_segment_distance(a,c,d).min(point_segment_distance(b,c,d)).min(point_segment_distance(c,a,b)).min(point_segment_distance(d,a,b))
}
fn prepare(points:&[f64],values:&[f64],support:&[f64],w:f64,h:f64)->Result<[f64;28],i32> {
 if points.len()!=165 || values.len()!=2 || support.len()!=28 || points.iter().chain(values).chain(support).any(|v|!v.is_finite()) || !w.is_finite() || !h.is_finite() || w<2. || h<2. || w>1_000_000. || h>1_000_000. {return Err(1);}
 if values.iter().any(|v|v.abs()>1.) {return Err(2);}
 let p=|i:usize|V::new(points[i*5]*(w-1.),points[i*5+1]*(h-1.)); let scale=(w-1.).min(h-1.);
 for i in ANCHORS {let q=&points[i*5..i*5+5]; if q[0]<=0. || q[0]>=1. || q[1]<=0. || q[1]>=1. || q[3]<0.8 || q[3]>1. || q[4]<0.8 || q[4]>1. {return Err(4);}}
 let mut out=[0.;28];
 for (i,(a,b)) in JOINTS.into_iter().enumerate() {
  let axis=p(b).sub(p(a)); let length=axis.len();
  if length<32. || length<scale*0.05 {return Err(3);}
  if (points[a*5+2]-points[b*5+2]).abs()*(w-1.)>length*0.7 {return Err(5);}
  let u=axis.mul(1./length); let n=V::new(-u.y,u.x); let raw=&support[i*7..i*7+7];
  let widths:Vec<f64>=raw[..6].iter().map(|v|v*scale).collect(); let radius=raw[6]*scale;
  if widths.iter().any(|v|*v<2. || *v>length*0.4) || radius<2. || radius>length*0.5 {return Err(6);}
  let max_width=widths.into_iter().fold(0.,f64::max);
  if radius+1e-9<1.4*max_width || radius-1e-9>2.5*max_width {return Err(6);}
  for c in [p(a).add(n.mul(radius)),p(a).sub(n.mul(radius)),p(b).add(n.mul(radius)),p(b).sub(n.mul(radius))] {
   if c.x<1. || c.x>w-2. || c.y<1. || c.y>h-2. {return Err(8);}
  }
  out[i*7..i*7+7].copy_from_slice(&[p(a).x,p(a).y,u.x,u.y,length,radius,values[i/2]]);
 }
 let segments=read_state(&out)?;
 for side in 0..2 {
  let thigh=segments[side]; let calf=segments[side+2]; let ratio=thigh.length/calf.length;
  if thigh.u.dot(calf.u)<0.35 || !(0.4..=2.5).contains(&ratio) {return Err(5);}
 }
 // Opposite-leg supports must be spatially separate. Includes neutral segments:
 // leaving an unedited limb outside the requested map is not optional.
 for i in [0,2] {for j in [1,3] {
  let a=segments[i];let b=segments[j];
  if segment_distance(a.a,a.a.add(a.u.mul(a.length)),b.a,b.a.add(b.u.mul(b.length)))<=a.radius+b.radius {return Err(7);}
 }}
 for (i,segment) in segments.iter().enumerate() {for anchor in ANCHORS { if anchor!=JOINTS[i].0 && anchor!=JOINTS[i].1 && segment.contains(p(anchor)) {return Err(5);} }}
 Ok(out)
}
fn evaluate(segments:[Segment;4],q:V)->Result<(V,f64),i32> {
 let mut p=q;let mut determinant=1.;
 for segment in segments {let (next,j)=segment.inverse(p)?;p=next;determinant*=j;}
 if !determinant.is_finite() || determinant<0.15 || determinant>6. {return Err(9);}
 Ok((q.sub(p),determinant))
}
#[no_mangle]
pub extern "C" fn lrt_leg_shape_abi()->u32 {1}
#[no_mangle]
pub unsafe extern "C" fn lrt_leg_shape_prepare(points:*const f64,values:*const f64,support:*const f64,w:f64,h:f64,out:*mut f64)->i32 {
 if points.is_null()||values.is_null()||support.is_null()||out.is_null() {return 1;}
 match prepare(slice::from_raw_parts(points,165),slice::from_raw_parts(values,2),slice::from_raw_parts(support,28),w,h) {Ok(state)=>{slice::from_raw_parts_mut(out,28).copy_from_slice(&state);0},Err(code)=>code}
}
#[no_mangle]
pub unsafe extern "C" fn lrt_leg_shape_evaluate(state:*const f64,xy:*const f64,count:usize,out:*mut f64,jac:*mut f64)->i32 {
 if state.is_null()||xy.is_null()||out.is_null()||jac.is_null()||count>1_048_576 {return 1;}
 let segments=match read_state(slice::from_raw_parts(state,28)){Ok(v)=>v,Err(code)=>return code};
 let input=slice::from_raw_parts(xy,count*2); if input.iter().any(|v|!v.is_finite()) {return 1;}
 let output=slice::from_raw_parts_mut(out,count*2);let determinants=slice::from_raw_parts_mut(jac,count);
 for i in 0..count {match evaluate(segments,V::new(input[i*2],input[i*2+1])) {Ok((d,j))=>{output[i*2]=d.x;output[i*2+1]=d.y;determinants[i]=j;},Err(code)=>return code}}
 0
}
#[cfg(test)]
mod tests {
 use super::*;
 fn segment(amount:f64)->Segment {Segment{a:V::new(100.,100.),u:V::new(0.,1.),length:200.,radius:30.,amount}}
 #[test] fn inverse_sign_neutral_and_endpoints() {
  for amount in [-1.,0.,1.] {let s=segment(amount); for q in [s.a,s.a.add(s.u.mul(s.length)),V::new(200.,200.)] {let (p,j)=s.inverse(q).unwrap();assert_eq!((p.x,p.y,j),(q.x,q.y,1.));}}
  let (p,_) = segment(1.).inverse(V::new(115.,200.)).unwrap();assert!(p.x>115.);
  let (p,_) = segment(-1.).inverse(V::new(115.,200.)).unwrap();assert!(p.x<115.);
 }
 #[test] fn inverse_determinant_matches_finite_difference() {
  let s=segment(1.);let q=V::new(111.37,180.29);let eps=1e-4;let (p,j)=s.inverse(q).unwrap();let (x,_)=s.inverse(q.add(V::new(eps,0.))).unwrap();let (y,_)=s.inverse(q.add(V::new(0.,eps))).unwrap();let numeric=cross(x.sub(p),y.sub(p))/(eps*eps);assert!((j-numeric).abs()<1e-5);
 }
 #[test] fn actual_off_grid_composition_not_sum() {
  let a=segment(0.8);let b=Segment{a:V::new(100.,150.),..segment(-0.6)};let q=V::new(113.,210.);let (pa,_)=a.inverse(q).unwrap();let (expected,_)=b.inverse(pa).unwrap();let identity=segment(0.);let (delta,_)=evaluate([a,b,identity,identity],q).unwrap();assert!((q.sub(delta).sub(expected)).len()<1e-10);
 }
}
