// SPDX-License-Identifier: GPL-3.0-or-later
//! Original longitudinal forward field and certified contraction inverse.
//! Source-only, UNRUN. RGB and masks are sampled only by the common host chain.
use std::slice;
const N:usize=26;
const GAIN:f64=0.08;
#[derive(Clone,Copy,Debug)]
struct V{x:f64,y:f64}
impl V{fn new(x:f64,y:f64)->Self{Self{x,y}} fn add(self,b:Self)->Self{Self::new(self.x+b.x,self.y+b.y)} fn sub(self,b:Self)->Self{Self::new(self.x-b.x,self.y-b.y)} fn mul(self,a:f64)->Self{Self::new(self.x*a,self.y*a)} fn len(self)->f64{self.x.hypot(self.y)}}
fn smooth(t:f64)->(f64,f64){let t=t.clamp(0.,1.);(t*t*t*(10.+t*(-15.+6.*t)),30.*t*t*(1.-t)*(1.-t))}
#[derive(Clone,Copy)]
struct Leg{s:[f64;13]}
impl Leg{
 fn d(self)->(V,V){(V::new(self.s[9],self.s[10]),V::new(self.s[11],self.s[12]))}
 fn bound(self)->f64{let(a,b)=self.d();a.len().max(a.add(b).len())}
 fn validate(self)->Result<(),i32>{
  let s=self.s;if s.iter().any(|x|!x.is_finite())||!(s[0]<s[1]&&s[1]<s[2]&&s[2]<s[3]&&s[4]<s[5]&&s[5]<s[6]&&s[6]<s[7]&&s[7]<s[8]){return Err(1)}
  let(a,b)=self.d();let axial=(a.len()/(s[5]-s[4])).max(b.len()/(s[6]-s[5])).max(a.add(b).len()/(s[8]-s[7]));
  // Global operator-norm upper bound via triangle inequality. It proves
  // injectivity and fixed-point convergence, not photographic naturalness.
  let lipschitz=1.875*(axial+self.bound()/(s[1]-s[0]).min(s[3]-s[2]));
  if lipschitz>0.45||self.bound()>128.{return Err(6)}Ok(())
 }
 fn forward_delta(self,p:V)->(V,[f64;4]){
  let s=self.s;if p.x<=s[0]||p.x>=s[3]||p.y<=s[4]||p.y>=s[8]{return(V::new(0.,0.),[0.;4])}
  let(wx,dx)=if p.x<s[1]{let(v,d)=smooth((p.x-s[0])/(s[1]-s[0]));(v,d/(s[1]-s[0]))}else if p.x>s[2]{let(v,d)=smooth((s[3]-p.x)/(s[3]-s[2]));(v,-d/(s[3]-s[2]))}else{(1.,0.)};
  let(a,b)=self.d();let sum=a.add(b);
  let(base,change,lo,hi)=if p.y<s[5]{(V::new(0.,0.),a,s[4],s[5])}else if p.y<s[6]{(a,b,s[5],s[6])}else if p.y<s[7]{(sum,V::new(0.,0.),s[6],s[7])}else{(sum,sum.mul(-1.),s[7],s[8])};
  let(v,d)=smooth((p.y-lo)/(hi-lo));let axial=base.add(change.mul(v));let dy=change.mul(d/(hi-lo));
  (axial.mul(wx),[axial.x*dx,dy.x*wx,axial.y*dx,dy.y*wx])
 }
 fn inverse(self,q:V)->Result<(V,f64),i32>{
  if self.bound()==0.{return Ok((q,1.))}
  let mut p=q;let mut converged=false;
  for _ in 0..64{let(d,_)=self.forward_delta(p);let next=q.sub(d);if next.sub(p).len()<1e-9{p=next;converged=true;break}p=next;}
  let(d,j)=self.forward_delta(p);if !converged||p.add(d).sub(q).len()>1e-7{return Err(9)}
  let determinant=(1.+j[0])*(1.+j[3])-j[1]*j[2];
  if !determinant.is_finite()||!(0.30..=2.11).contains(&determinant)||q.sub(p).len()>self.bound()+1e-7{return Err(9)}
  Ok((p,1./determinant))
 }
}
fn read_state(raw:&[f64])->Result<[Leg;2],i32>{
 if raw.len()!=N{return Err(1)}let mut legs=[Leg{s:[0.;13]};2];
 for(i,leg)in legs.iter_mut().enumerate(){leg.s.copy_from_slice(&raw[i*13..i*13+13]);leg.validate()?;}
 if !(legs[0].s[3]<legs[1].s[0]||legs[1].s[3]<legs[0].s[0]){return Err(7)}Ok(legs)
}
fn prepare(points:&[f64],amount:&[f64],support:&[f64],w:f64,h:f64)->Result<[f64;N],i32>{
 if points.len()!=165||amount.len()!=2||support.len()!=12||points.iter().chain(amount).chain(support).any(|v|!v.is_finite())||!w.is_finite()||!h.is_finite()||w<2.||h<2.||w>1_000_000.||h>1_000_000.{return Err(1)}
 if amount.iter().any(|a|!(0.0..=1.0).contains(a)){return Err(2)}
 let p=|i:usize|V::new(points[i*5]*(w-1.),points[i*5+1]*(h-1.));
 for i in 23..33{let q=&points[i*5..i*5+5];if q[0]<=0.||q[0]>=1.||q[1]<=0.||q[1]>=1.||!(0.8..=1.0).contains(&q[3])||!(0.8..=1.0).contains(&q[4]){return Err(4)}}
 let mut out=[0.;N];
 for side in 0..2{let hip=23+side;let knee=25+side;let ankle=27+side;let raw=&support[side*6..side*6+6];
  let mut s=[0.;13];for i in 0..4{s[i]=raw[i]*(w-1.);}s[4]=p(hip).y;s[5]=p(knee).y;s[6]=p(ankle).y;s[7]=raw[4]*(h-1.);s[8]=raw[5]*(h-1.);
  if s[0]<1.||s[3]>w-2.||s[4]<1.||s[8]>h-2.{return Err(8)}
  for i in [hip,knee,ankle,29+side,31+side]{let q=p(i);if q.x<=s[1]||q.x>=s[2]{return Err(6)}}
  for i in [29+side,31+side]{if p(i).y<s[6]||p(i).y>=s[7]{return Err(5)}}
  for (j,(a,b)) in [(hip,knee),(knee,ankle)].into_iter().enumerate(){let d=p(b).sub(p(a));if d.y<32.||d.x.abs()>d.y*0.35||(points[b*5+2]-points[a*5+2]).abs()*(w-1.)>d.y*0.35{return Err(5)}s[9+j*2]=d.x*GAIN*amount[j];s[10+j*2]=d.y*GAIN*amount[j];}
  out[side*13..side*13+13].copy_from_slice(&s);
 }
 read_state(&out)?;Ok(out)
}
fn evaluate(legs:[Leg;2],q:V)->Result<(V,f64),i32>{let mut p=q;let mut jac=1.;for leg in legs{let(next,j)=leg.inverse(p)?;p=next;jac*=j;}Ok((q.sub(p),jac))}
#[no_mangle]pub extern "C" fn lrt_leg_length_abi()->u32{1}
#[no_mangle]pub unsafe extern "C" fn lrt_leg_length_prepare(p:*const f64,a:*const f64,s:*const f64,w:f64,h:f64,out:*mut f64)->i32{
 if p.is_null()||a.is_null()||s.is_null()||out.is_null(){return 1}match prepare(slice::from_raw_parts(p,165),slice::from_raw_parts(a,2),slice::from_raw_parts(s,12),w,h){Ok(v)=>{slice::from_raw_parts_mut(out,N).copy_from_slice(&v);0},Err(c)=>c}}
#[no_mangle]pub unsafe extern "C" fn lrt_leg_length_evaluate(s:*const f64,xy:*const f64,count:usize,out:*mut f64,jac:*mut f64)->i32{
 if s.is_null()||xy.is_null()||out.is_null()||jac.is_null()||count>1_048_576{return 1}let legs=match read_state(slice::from_raw_parts(s,N)){Ok(v)=>v,Err(c)=>return c};let input=slice::from_raw_parts(xy,count*2);if input.iter().any(|v|!v.is_finite()){return 1}let output=slice::from_raw_parts_mut(out,count*2);let determinants=slice::from_raw_parts_mut(jac,count);
 for i in 0..count{match evaluate(legs,V::new(input[i*2],input[i*2+1])){Ok((d,j))=>{output[i*2]=d.x;output[i*2+1]=d.y;determinants[i]=j},Err(c)=>return c}}0}
#[cfg(test)]mod tests{use super::*;
 fn leg()->Leg{Leg{s:[0.,100.,200.,300.,100.,300.,500.,550.,750.,0.,8.,0.,8.]}}
 #[test]fn exact_joint_lengths_and_foot_translation(){let l=leg();l.validate().unwrap();for(y,want)in [(100.,0.),(300.,8.),(500.,16.),(525.,16.),(750.,0.)]{let(d,_)=l.forward_delta(V::new(150.,y));assert_eq!(d.y,want);}}
 #[test]fn inverse_off_grid_and_jacobian(){let l=leg();let q=V::new(125.37,356.21);let(p,j)=l.inverse(q).unwrap();let(d,_)=l.forward_delta(p);assert!(p.add(d).sub(q).len()<1e-7);let eps=1e-4;let(x,_)=l.inverse(q.add(V::new(eps,0.))).unwrap();let(y,_)=l.inverse(q.add(V::new(0.,eps))).unwrap();let a=x.sub(p);let b=y.sub(p);assert!((j-(a.x*b.y-a.y*b.x)/(eps*eps)).abs()<1e-5);}
 #[test]fn refuse_fold_budget(){let mut l=leg();l.s[10]=200.;assert!(l.validate().is_err());}
}
