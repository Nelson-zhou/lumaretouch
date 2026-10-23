//! Original Lumaretouch xy-primary basis transform. GPL-3.0-or-later.
//! Global linear transform, not HSL, ICC parsing, DCP or camera characterization.
use std::slice;
type M = [[f32;3];3];
const WHITE:[f32;3]=[0.3127/0.3290,1.,(1.-0.3127-0.3290)/0.3290];
const XY:[[f32;2];3]=[[0.64,0.33],[0.30,0.60],[0.15,0.06]];
fn mv(a:M,v:[f32;3])->[f32;3]{std::array::from_fn(|i|a[i][0]*v[0]+a[i][1]*v[1]+a[i][2]*v[2])}
fn mm(a:M,b:M)->M{std::array::from_fn(|i|std::array::from_fn(|j|(0..3).map(|k|a[i][k]*b[k][j]).sum()))}
fn norm(a:M)->f32 {a.iter().map(|r|r.iter().map(|v|v.abs()).sum::<f32>()).fold(0.,f32::max)}
fn inverse(a:M)->Option<M>{
 let d=a[0][0]*(a[1][1]*a[2][2]-a[1][2]*a[2][1])-a[0][1]*(a[1][0]*a[2][2]-a[1][2]*a[2][0])+a[0][2]*(a[1][0]*a[2][1]-a[1][1]*a[2][0]);
 if !d.is_finite()||d<=1e-5{return None;}
 let b=std::array::from_fn(|i|std::array::from_fn(|j|{
  let rows:Vec<usize>=(0..3).filter(|x|*x!=j).collect();let cols:Vec<usize>=(0..3).filter(|x|*x!=i).collect();
  let v=a[rows[0]][cols[0]]*a[rows[1]][cols[1]]-a[rows[0]][cols[1]]*a[rows[1]][cols[0]];
  v*if (i+j)%2==0 {1./d}else{-1./d}
 }));
 if norm(a)*norm(b)>100.||b.iter().flatten().any(|v|!v.is_finite()){None}else{Some(b)}
}
fn basis(xy:[[f32;2];3])->Option<M>{
 if xy.iter().any(|p|!p[0].is_finite()||!p[1].is_finite()||p[0]<=0.||p[1]<=0.||p[0]+p[1]>=1.){return None;}
 let a=std::array::from_fn(|i|std::array::from_fn(|j|match i{0=>xy[j][0]/xy[j][1],1=>1.,_ =>(1.-xy[j][0]-xy[j][1])/xy[j][1]}));
 let weights=mv(inverse(a)?,WHITE);
 if weights.iter().any(|w|!w.is_finite()||*w<0.005||*w>2.){return None;}
 let out=std::array::from_fn(|i|std::array::from_fn(|j|a[i][j]*weights[j]));
 inverse(out)?;Some(out)
}
pub fn matrix(r:&[f32])->Option<M>{
 if r.len()!=6||r.iter().any(|v|!v.is_finite()||v.abs()>100.){return None;}
 if r.iter().all(|v|*v==0.) {return Some([[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]);}
 let adjusted=std::array::from_fn(|i|{
  let x=XY[i][0]-0.3127;let y=XY[i][1]-0.3290;
  // Positive hue rotates red toward yellow, green toward cyan, blue toward magenta.
  let angle=(r[2*i]*0.20).to_radians();let (s,c)=angle.sin_cos();let scale=1.+r[2*i+1]*0.005;
  [0.3127+scale*(x*c-y*s),0.3290+scale*(x*s+y*c)]
 });
 let mut result=mm(inverse(basis(XY)?)?,basis(adjusted)?);
 // Fix floating-point white row sums; exact gray is also bypassed below.
 for row in &mut result {row[2]=1.-row[0]-row[1];}
 inverse(result)?;Some(result)
}
fn decode(x:f32)->f32{let a=x.abs();x.signum()*if a<=0.04045{a/12.92}else{((a+0.055)/1.055).powf(2.4)}}
fn encode(x:f32)->f32{let a=x.abs();x.signum()*if a<=0.0031308{a*12.92}else{1.055*a.powf(1./2.4)-0.055}}
#[no_mangle] pub extern "C" fn lrt_primary_calibration_abi()->u32{1}
/// Six f32 controls, valid/aligned for call. 0 admitted, 1 invalid pointer, 2 invalid basis.
#[no_mangle] pub unsafe extern "C" fn lrt_primary_calibration_admit(recipe:*const f32)->i32{
 if recipe.is_null()||(recipe as usize)%4!=0{return 1;}
 if matrix(slice::from_raw_parts(recipe,6)).is_some(){0}else{2}
}
/// n RGB pixels, <=65536. Disjoint valid input/output and recipe buffers.
/// mode 0 linear sRGB D65, mode 1 signed extended encoded sRGB D65.
/// Error: 1 ABI/bounds, 2 recipe/basis, 3 input. Output untouched on error.
#[no_mangle] pub unsafe extern "C" fn lrt_primary_calibration_apply(input:*const f32,output:*mut f32,n:usize,recipe:*const f32,mode:u32)->i32{
 if input.is_null()||output.is_null()||recipe.is_null()||n==0||n>65536||mode>1{return 1;}
 let a=input as usize;let b=output as usize;let c=recipe as usize;let bytes=n*12;
 let overlap=|x:usize,l:usize,y:usize,k:usize|x<y.saturating_add(k)&&y<x.saturating_add(l);
 if a%4!=0||b%4!=0||c%4!=0||overlap(a,bytes,b,bytes)||overlap(c,24,b,bytes){return 1;}
 let r=slice::from_raw_parts(recipe,6);let Some(m)=matrix(r) else{return 2;};
 let src=slice::from_raw_parts(input,n*3);let bound=if mode==0{65504.}else{128.};
 if src.iter().any(|v|!v.is_finite()||v.abs()>bound){return 3;}
 let dst=slice::from_raw_parts_mut(output,n*3);
 if r.iter().all(|v|*v==0.){dst.copy_from_slice(src);return 0;}
 for (s,d) in src.chunks_exact(3).zip(dst.chunks_exact_mut(3)){
  if s[0]==s[1]&&s[1]==s[2]{d.copy_from_slice(s);continue;}
  let p=[s[0],s[1],s[2]];let p=if mode==1{p.map(decode)}else{p};let q=mv(m,p);
  let q=if mode==1{q.map(encode)}else{q};d.copy_from_slice(&q);
 }
 0
}
#[cfg(test)]mod tests{
 use super::*;
 #[test]fn identity(){assert_eq!(matrix(&[0.;6]).unwrap(),[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]);}
 #[test]fn rejects_nonfinite(){assert!(matrix(&[f32::NAN;6]).is_none());}
 #[test]fn preserves_white(){let m=matrix(&[10.,-10.,-10.,-10.,10.,-10.]).unwrap();for v in mv(m,[1.;3]){assert!((v-1.).abs()<1e-6);}}
 #[test]fn rejects_degenerate(){assert!(inverse([[1.;3];3]).is_none());}
}
