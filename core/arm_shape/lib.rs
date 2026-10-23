// SPDX-License-Identifier: GPL-3.0-or-later
//! Original contour-conditioned compact C2 inverse field, one visible segment.
//! This crate owns no RGB sampler, pose inference, mask inference or model.
//! Joint endpoints stay fixed with zero first/second displacement derivatives.
use std::slice;
const N:usize=9;
const STATE:usize=25;
const GAIN:f64=0.22; // Local implementation choice, NOT a commercial slider value.
#[derive(Clone,Copy)]
struct V {x:f64,y:f64}
impl V {
 fn new(x:f64,y:f64)->Self {Self{x,y}}
 fn add(self,b:Self)->Self {Self::new(self.x+b.x,self.y+b.y)}
 fn sub(self,b:Self)->Self {Self::new(self.x-b.x,self.y-b.y)}
 fn mul(self,v:f64)->Self {Self::new(self.x*v,self.y*v)}
 fn dot(self,b:Self)->f64 {self.x*b.x+self.y*b.y}
 fn len(self)->f64 {self.dot(self).sqrt()}
}
struct Segment {a:V,u:V,length:f64,amount:f64,factor:f64,negative:[f64;N],positive:[f64;N]}
fn smooth(t:f64)->f64 {t*t*t*(10.+t*(-15.+6.*t))}
fn profile(values:&[f64;N],t:f64)->f64 {
 if t<=0.1 {return values[0];} if t>=0.9 {return values[8];}
 let p=(t-0.1)*10.;let i=(p.floor() as usize).min(7);
 values[i]+(values[i+1]-values[i])*smooth((p-i as f64).clamp(0.,1.))
}
fn read(s:&[f64])->Result<Segment,i32> {
 if s.len()!=STATE||s.iter().any(|v|!v.is_finite()) {return Err(1);}
 let mut negative=[0.;N];let mut positive=[0.;N];negative.copy_from_slice(&s[7..16]);positive.copy_from_slice(&s[16..25]);
 let seg=Segment{a:V::new(s[0],s[1]),u:V::new(s[2],s[3]),length:s[4],amount:s[5],factor:s[6],negative,positive};
 if (seg.u.len()-1.).abs()>1e-8||seg.length<4.||!(0.0..=1.0).contains(&seg.amount)||!(1.4..=1.8).contains(&seg.factor)||seg.negative.iter().chain(seg.positive.iter()).any(|v|*v<=0.||*v*seg.factor>seg.length*0.46) {return Err(2);}
 Ok(seg)
}
impl Segment {
 fn inverse(&self,q:V)->Result<(V,f64),i32> {
  let n=V::new(-self.u.y,self.u.x);let d=q.sub(self.a);let t=d.dot(self.u)/self.length;let v=d.dot(n);
  if self.amount==0.||t<=0.||t>=1. {return Ok((q,1.));}
  let radius=self.factor*profile(if v<0.{&self.negative}else{&self.positive},t);
  if v.abs()>=radius {return Ok((q,1.));}
  let z=v/radius;let edge=1.-z*z;let k=GAIN*self.amount*64.*t.powi(3)*(1.-t).powi(3);
  // Axial coordinate is unchanged: radius'(t) contributes shear but not det.
  let p=q.add(n.mul(k*v*edge.powi(3)));
  let jac=1.+k*edge.powi(2)*(1.-7.*z*z);
  if !p.x.is_finite()||!p.y.is_finite()||!jac.is_finite()||jac<0.77||jac>1.23 {return Err(3);}
  Ok((p,jac))
 }
}
#[no_mangle]
pub extern "C" fn lrt_arm_shape_abi()->u32 {1}
/// State [ax,ay,ux,uy,length,amount,factor,negative widths*9,positive widths*9].
/// All widths here are actual render-pixel sizes, never anatomical defaults.
#[no_mangle]
pub unsafe extern "C" fn lrt_arm_shape_evaluate(state:*const f64,xy:*const f64,count:usize,out:*mut f64,jac:*mut f64)->i32 {
 if state.is_null()||xy.is_null()||out.is_null()||jac.is_null()||count>1_048_576 {return 1;}
 let seg=match read(slice::from_raw_parts(state,STATE)){Ok(s)=>s,Err(e)=>return e};
 let input=slice::from_raw_parts(xy,count*2);if input.iter().any(|n|!n.is_finite()){return 1;}
 let output=slice::from_raw_parts_mut(out,count*2);let determinants=slice::from_raw_parts_mut(jac,count);
 for i in 0..count {let q=V::new(input[i*2],input[i*2+1]);match seg.inverse(q){Ok((p,j))=>{let d=q.sub(p);output[i*2]=d.x;output[i*2+1]=d.y;determinants[i]=j;},Err(e)=>return e}}
 0
}
#[cfg(test)]
mod tests {
 use super::*;
 fn fixture(amount:f64)->Segment {let mut s=[12.;25];s[..7].copy_from_slice(&[100.,100.,0.,1.,200.,amount,1.4]);read(&s).unwrap()}
 #[test] fn identity_joints_and_outside(){for s in [fixture(0.),fixture(1.)]{for q in [V::new(100.,100.),V::new(100.,300.),V::new(200.,180.)]{let(p,j)=s.inverse(q).unwrap();assert_eq!((p.x,p.y,j),(q.x,q.y,1.));}}}
 #[test] fn positive_means_thinner(){let q=V::new(108.,200.);let(p,j)=fixture(1.).inverse(q).unwrap();assert!(p.x>q.x&&j>0.);}
 #[test] fn measured_profile_matters(){let a=fixture(1.);let mut b=fixture(1.);b.positive[4]=20.;b.negative[4]=20.;let q=V::new(108.,200.);assert!((a.inverse(q).unwrap().0.x-b.inverse(q).unwrap().0.x).abs()>0.01);}
 #[test] fn analytic_jacobian_with_varying_contour(){let mut s=fixture(0.9);s.negative[3]=20.;s.positive[3]=18.;let q=V::new(108.3,181.7);let e=1e-4;let(p,j)=s.inverse(q).unwrap();let(x,_)=s.inverse(q.add(V::new(e,0.))).unwrap();let(y,_)=s.inverse(q.add(V::new(0.,e))).unwrap();let a=x.sub(p);let b=y.sub(p);assert!(((a.x*b.y-a.y*b.x)/(e*e)-j).abs()<1e-4);}
}
