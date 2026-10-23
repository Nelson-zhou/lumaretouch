// SPDX-License-Identifier: GPL-3.0-or-later
//! Original continuous source-space deformation, not a sampled displacement LUT.
//! Entire reviewed connected head/hair plateau translates with the neck.
use std::f64::consts::PI;
fn smooth(t:f64)->(f64,f64){if t<=0. {(0.,0.)}else if t>=1. {(1.,0.)}else{(t*t*(3.-2.*t),6.*t*(1.-t))}}
fn ramp(x:f64,a:f64,b:f64)->(f64,f64){let (v,d)=smooth((x-a)/(b-a));(v,d/(b-a))}
fn plateau(x:f64,a:f64,b:f64,c:f64,d:f64)->(f64,f64){let (l,dl)=ramp(x,a,b);let(r,dr)=ramp(x,c,d);(l*(1.-r),dl*(1.-r)-l*dr)}
fn contour(s:&[f64],t:f64)->(f64,f64){let z=t.clamp(0.,1.)*4.;let i=(z.floor() as usize).min(3);let(v,d)=smooth(z-i as f64);(s[i]+(s[i+1]-s[i])*v,(s[i+1]-s[i])*d*4.)}
// Returns forward displacement and its analytic derivative [xx,xy,yx,yy].
fn forward(s:&[f64],x:f64,y:f64)->([f64;2],[f64;4]){
 let h=s[2]-s[1];let (wx,dx)=plateau(x,s[7],s[3],s[5],s[9]);
 let (wy,dy)=plateau(y,s[8],s[4],s[1],s[2]);let amp=-s[21]*h*0.08;
 let mut out=[0.,amp*wx*wy];let mut j=[0.,0.,amp*dx*wy,amp*wx*dy];
 let t=(y-s[1])/h;
 if t>0.&&t<1. {
  let side=if x<s[0]{-1.}else{1.};let k=if side<0.{11}else{16};let amount=if side<0.{s[22]}else{s[23]};
  let (r,rt)=contour(&s[k..k+5],t);let ry=rt/h;let q=(x-s[0]).abs()/r;
  if q<2. {let b=(PI*q*0.5).sin().powi(2);let db=PI*0.5*(PI*q).sin();let a=(PI*t).sin().powi(2);let ay=PI*(2.*PI*t).sin()/h;
   out[0]=-side*amount*0.06*r*b*a;
   j[0]=-amount*0.06*db*a;
   j[1]=-side*amount*0.06*((ry*b-ry*q*db)*a+r*b*ay);
  }
 }
 (out,j)
}
fn valid(s:&[f64])->bool{
 if s.len()!=24||s.iter().any(|x|!x.is_finite())||s[21..].iter().any(|x|x.abs()>1.){return false}
 let h=s[2]-s[1];let mx=(s[3]-s[7]).min(s[9]-s[5]);let my=(s[4]-s[8]).min(h);
 if h<16.||mx<=0.||my<=0.||!(s[8]<s[4]&&s[4]<s[6]&&s[6]<=s[1]&&s[1]<s[2]&&s[2]<s[10]&&s[3]<s[0]&&s[0]<s[5])||s[11..21].iter().any(|x|*x<=0.){return false}
 let r=s[11..21].iter().copied().fold(0.,f64::max);
 if s[0]-2.*r<=s[7]||s[0]+2.*r>=s[9]{return false}
 let slope=s[11..16].windows(2).chain(s[16..21].windows(2)).map(|v|(v[1]-v[0]).abs()*6./h).fold(0.,f64::max);
 // Infinity-norm contraction bound globally, not just grid-point Jacobians.
 let width=s[22].abs().max(s[23].abs())*0.06*(PI*0.5+slope*(1.+PI)+r*PI/h);
 let length=s[21].abs()*h*0.08*1.5*(1./mx+1./my);
 width.max(length)<0.45
}
#[no_mangle]pub extern "C" fn lrt_neck_shape_abi()->u32{1}
/// ABI owns no pointers. Caller supplies 24 finite source-pixel scalars and N xy pairs.
#[no_mangle]pub unsafe extern "C" fn lrt_neck_shape_evaluate(state:*const f64,points:*const f64,n:usize,out:*mut f64,jac:*mut f64)->i32{
 if state.is_null()||points.is_null()||out.is_null()||jac.is_null()||n>1_048_576{return 1}
 let s=std::slice::from_raw_parts(state,24);if !valid(s){return 2}
 let p=std::slice::from_raw_parts(points,n*2);let o=std::slice::from_raw_parts_mut(out,n*2);let js=std::slice::from_raw_parts_mut(jac,n);
 for i in 0..n{let target=[p[2*i],p[2*i+1]];if target.iter().any(|v|!v.is_finite()){return 1}
  let mut q=target;for _ in 0..48{let(d,_)=forward(s,q[0],q[1]);q=[target[0]-d[0],target[1]-d[1]];}
  let(d,j)=forward(s,q[0],q[1]);let det=(1.+j[0])*(1.+j[3])-j[1]*j[2];
  if (q[0]+d[0]-target[0]).abs().max((q[1]+d[1]-target[1]).abs())>1e-7||det<=0.25||det>=2.5{return 3}
  let bound=s[21].abs()*(s[2]-s[1])*0.08+s[22].abs().max(s[23].abs())*0.06*s[11..21].iter().copied().fold(0.,f64::max);
  if d[0].hypot(d[1])>bound+1e-7{return 3}
  o[2*i]=target[0]-q[0];o[2*i+1]=target[1]-q[1];js[i]=1./det;
 }
 0
}
