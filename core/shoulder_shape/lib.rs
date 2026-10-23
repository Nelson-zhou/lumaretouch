// SPDX-License-Identifier: GPL-3.0-or-later
//! Original 2D visible-shoulder deformation, no generated pixels or body mesh.
//! Forward map is two disjoint compact C2 radial translations. Its analytical
//! derivative is bounded below the contraction budget; inverse is solved at the
//! actual requested coordinates, never a resampled displacement grid.
use std::slice;
const ABI:u32=1;
const POINTS:usize=33;
const ANCHORS:[usize;9]=[0,7,8,11,12,13,14,23,24];
const FIXED:[usize;7]=[0,7,8,13,14,23,24];
const GRAD_MAX:f64=1.718;
const LIPSCHITZ_MAX:f64=0.65;
#[derive(Clone,Copy,Debug)]
struct V {x:f64,y:f64}
impl V {
 fn new(x:f64,y:f64)->Self{Self{x,y}}
 fn add(self,b:Self)->Self{Self::new(self.x+b.x,self.y+b.y)}
 fn sub(self,b:Self)->Self{Self::new(self.x-b.x,self.y-b.y)}
 fn mul(self,s:f64)->Self{Self::new(self.x*s,self.y*s)}
 fn dot(self,b:Self)->f64{self.x*b.x+self.y*b.y}
 fn len(self)->f64{self.dot(self).sqrt()}
 fn unit(self)->Result<Self,i32>{let n=self.len();if !n.is_finite()||n<1e-9{Err(3)}else{Ok(self.mul(1./n))}}
}
#[derive(Clone,Copy)]
struct Lobe {c:V,r:f64,d:V}
fn read_lobe(s:&[f64])->Lobe{Lobe{c:V::new(s[0],s[1]),r:s[2],d:V::new(s[3],s[4])}}
fn phi(p:V,l:Lobe)->f64{let t=p.sub(l.c).dot(p.sub(l.c))/(l.r*l.r);if t>=1.{0.}else{(1.-t).powi(3)}}
fn gradient(p:V,l:Lobe)->V{let v=p.sub(l.c);let t=v.dot(v)/(l.r*l.r);if t>=1.{V::new(0.,0.)}else{v.mul(-6.*(1.-t).powi(2)/(l.r*l.r))}}
fn valid_lobes(s:&[f64])->Result<[Lobe;2],i32>{
 if s.len()!=10||s.iter().any(|v|!v.is_finite()){return Err(1)}
 let ls=[read_lobe(&s[..5]),read_lobe(&s[5..])];
 for l in ls {if l.r<1.||GRAD_MAX*l.d.len()/l.r>LIPSCHITZ_MAX{return Err(6)}}
 if ls[0].c.sub(ls[1].c).len()<=ls[0].r+ls[1].r{return Err(7)}
 Ok(ls)
}
fn prepare(points:&[f64],values:&[f64],w:f64,h:f64)->Result<[f64;10],i32>{
 if points.len()!=POINTS*5||values.len()!=4||points.iter().chain(values).any(|v|!v.is_finite())||!w.is_finite()||!h.is_finite()||w<2.||h<2.{return Err(1)}
 if values[0]<0.||values[0]>1.||values[1]<0.||values[1]>1.||values[2].abs()>1.||values[3].abs()>1.{return Err(2)}
 let p=|i:usize|V::new(points[i*5]*(w-1.),points[i*5+1]*(h-1.));
 for i in ANCHORS {if points[i*5+3]<0.8||points[i*5+4]<0.8||points[i*5+3]>1.||points[i*5+4]>1.||points[i*5]<=0.||points[i*5]>=1.||points[i*5+1]<=0.||points[i*5+1]>=1.{return Err(4)}}
 let left=p(11);let right=p(12);let width=left.sub(right).len();
 if width<24.||width<w.min(h)*0.06{return Err(3)}
 prepare_supported(points,values,w,h)
}
fn prepare_supported(points:&[f64],values:&[f64],w:f64,h:f64)->Result<[f64;10],i32>{
 let p=|i:usize|V::new(points[i*5]*(w-1.),points[i*5+1]*(h-1.));
 let left=p(11);let right=p(12);let center=left.add(right).mul(0.5);let width=left.sub(right).len();
 let torso=p(23).add(p(24)).mul(0.5).sub(center);let down=torso.unit()?;
 let raw_axis=left.sub(right).unit()?;
 if torso.len()<width*0.55||torso.len()>width*3.8||raw_axis.dot(down).abs()>0.35{return Err(5)}
 let mut axis=V::new(down.y,-down.x);if axis.dot(raw_axis)<0.{axis=axis.mul(-1.)}
 // z is approximate and only a rejection clue, never reconstructed geometry.
 if (points[11*5+2]-points[12*5+2]).abs()*(w-1.)>width*0.55{return Err(5)}
 for (s,e) in [(11,13),(12,14)] {if p(e).sub(p(s)).dot(down)<width*0.1{return Err(5)}}
 if p(0).sub(center).dot(down)>-width*0.15{return Err(5)}
 let mut out=[0.;10];
 for side in 0..2 {
  let c=if side==0{left}else{right};
  let mut radius=width*0.44;
  for i in FIXED {radius=radius.min(c.sub(p(i)).len()*0.65)}
  let d=axis.mul(values[2+side]*width*0.08*if side==0{1.}else{-1.}).sub(down.mul(values[side]*width*0.06));
  if radius<8.||c.x-radius<1.||c.y-radius<1.||c.x+radius>w-2.||c.y+radius>h-2.{return Err(8)}
  let start=side*5;out[start..start+5].copy_from_slice(&[c.x,c.y,radius,d.x,d.y]);
 }
 valid_lobes(&out)?;Ok(out)
}
fn inverse(q:V,lobes:[Lobe;2])->Result<(V,f64),i32>{
 let mut p=q;
 let mut active=None;
 for l in lobes {if q.sub(l.c).len()<l.r{active=Some(l);break}}
 let Some(l)=active else{return Ok((V::new(0.,0.),1.))};
 if l.d.x==0.&&l.d.y==0.{return Ok((V::new(0.,0.),1.))}
 for _ in 0..96 {
  let next=q.sub(l.d.mul(phi(p,l)));
  let error=next.sub(p).len();p=next;
  if error<=1e-9 {
   let residual=p.add(l.d.mul(phi(p,l))).sub(q).len();
   let det=1.+l.d.dot(gradient(p,l));
   if residual>1e-7||!det.is_finite()||det<1.-LIPSCHITZ_MAX{return Err(9)}
   return Ok((q.sub(p),1./det))
  }
 }
 Err(9)
}
#[no_mangle]
pub extern "C" fn lrt_shoulder_shape_abi()->u32{ABI}
/// Status: 1 schema, 2 range, 3 scale, 4 visibility, 5 extreme pose,
/// 6 deformation budget, 7 overlap, 8 cropped support, 9 inverse/fold failure.
#[no_mangle]
pub unsafe extern "C" fn lrt_shoulder_shape_prepare(points:*const f64,values:*const f64,w:f64,h:f64,out:*mut f64)->i32{
 if points.is_null()||values.is_null()||out.is_null(){return 1}
 match prepare(slice::from_raw_parts(points,165),slice::from_raw_parts(values,4),w,h){Ok(v)=>{slice::from_raw_parts_mut(out,10).copy_from_slice(&v);0},Err(e)=>e}
}
#[no_mangle]
pub unsafe extern "C" fn lrt_shoulder_shape_evaluate(state:*const f64,xy:*const f64,count:usize,out:*mut f64,jac:*mut f64)->i32{
 if state.is_null()||xy.is_null()||out.is_null()||jac.is_null()||count>1_048_576{return 1}
 let lobes=match valid_lobes(slice::from_raw_parts(state,10)){Ok(v)=>v,Err(e)=>return e};
 let input=slice::from_raw_parts(xy,count*2);let output=slice::from_raw_parts_mut(out,count*2);let determinants=slice::from_raw_parts_mut(jac,count);
 if input.iter().any(|v|!v.is_finite()){return 1}
 for i in 0..count {match inverse(V::new(input[i*2],input[i*2+1]),lobes){Ok((v,j))=>{output[i*2]=v.x;output[i*2+1]=v.y;determinants[i]=j},Err(e)=>return e}}
 0
}
#[cfg(test)]
mod tests {
 use super::*;
 #[test] fn exact_identity_and_outside(){let s=[100.,100.,30.,0.,0.,200.,100.,30.,0.,0.];let l=valid_lobes(&s).unwrap();for q in [V::new(101.23,99.8),V::new(0.,0.)]{let (d,j)=inverse(q,l).unwrap();assert_eq!((d.x,d.y,j),(0.,0.,1.));}}
 #[test] fn maps_actual_moved_shoulder_back(){let s=[100.,100.,40.,4.,-3.,200.,100.,40.,0.,0.];let l=valid_lobes(&s).unwrap();let (d,j)=inverse(V::new(104.,97.),l).unwrap();assert!((d.x-4.).abs()<1e-7&&(d.y+3.).abs()<1e-7&&j>0.);}
 #[test] fn refusal_not_strength_clamp(){assert!(valid_lobes(&[100.,100.,10.,9.,0.,200.,100.,10.,0.,0.]).is_err());assert!(valid_lobes(&[100.,100.,60.,1.,0.,200.,100.,60.,0.,0.]).is_err());}
}
