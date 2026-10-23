//! Original colour-selection operator. No spatial filtering; no eight-band HSL.
//! RGB is extended encoded sRGB; selection uses bounded normalized HSL while
//! reconstruction preserves the input's black offset and super-white headroom.
use std::f32::consts::TAU;
const N:usize=16;
fn unit(x:f32)->f32{x.clamp(0.,1.)}
fn wrap(x:f32)->f32{x.rem_euclid(1.)}
fn distance(a:f32,b:f32)->f32{(a-b+0.5).rem_euclid(1.)-0.5}
fn smooth(x:f32)->f32{let t=unit(x);t*t*(3.-2.*t)}
fn band(x:f32,lo:f32,hi:f32,soft:f32)->f32{
 if x>=lo&&x<=hi {1.} else if soft==0. {0.} else if x<lo {smooth(1.-(lo-x)/soft)} else {smooth(1.-(x-hi)/soft)}
}
fn hsl(rgb:[f32;3])->([f32;3],f32,f32){
 let black=rgb.iter().copied().fold(0.,f32::min);
 let scale=(rgb.iter().copied().fold(1.,f32::max)-black).max(1.);
 let [r,g,b]=rgb.map(|x|(x-black)/scale);
 let mx=r.max(g).max(b);let mn=r.min(g).min(b);let d=mx-mn;let l=(mx+mn)*0.5;
 if d<1e-7{return ([0.,0.,l],black,scale)}
 let s=d/(1.-(2.*l-1.).abs()).max(1e-7);
 let h=if mx==r{(g-b)/d}else if mx==g{(b-r)/d+2.}else{(r-g)/d+4.};
 ([wrap(h/6.),unit(s),unit(l)],black,scale)
}
fn rgb(v:[f32;3])->[f32;3]{
 let [h,s,l]=v;let c=(1.-(2.*l-1.).abs())*s;let k=wrap(h)*6.;let x=c*(1.-(k.rem_euclid(2.)-1.).abs());
 let b=match k as u32{0=>[c,x,0.],1=>[x,c,0.],2=>[0.,c,x],3=>[0.,x,c],4=>[x,0.,c],_=>[c,0.,x]};b.map(|v|v+l-c*0.5)
}
fn weight(v:[f32;3],p:&[f32],mask:f32)->f32{
 let hue=if p[1]>=0.5{1.}else{band(distance(v[0],p[0]).abs(),0.,p[1],p[6]*0.5)};
 // Achromatic samples have no meaningful hue, and are selected via S/L bounds.
 let hue=if v[1]<1e-7 {if p[2]==0.{1.}else{0.}}else{hue};
 let raw=hue*band(v[1],p[2],p[3],p[6])*band(v[2],p[4],p[5],p[7]);
 (if p[14]==1.{1.-raw}else{raw})*unit(mask)
}
fn valid(p:&[f32])->bool{
 p.len()==N&&p.iter().all(|x|x.is_finite())&&(0.0..=1.0).contains(&p[0])&&(0.0..=0.5).contains(&p[1])&&
 (2..8).all(|i|(0.0..=1.0).contains(&p[i]))&&p[2]<=p[3]&&p[4]<=p[5]&&
 (8..14).all(|i|(-1.0..=1.0).contains(&p[i]))&&(p[14]==0.||p[14]==1.)&&p[15]==1.
}
#[no_mangle] pub extern "C" fn lrt_colour_editor_abi()->u32{1}
/// Stats [weight, hue_cos, hue_sin, saturation, lightness], sequential f64 sum.
/// Caller resets once per full operator input, then visits canonical raster order.
#[no_mangle] pub unsafe extern "C" fn lrt_colour_editor_stats(src:*const f32,mask:*const f32,n:usize,params:*const f32,stats:*mut f64)->i32{
 if src.is_null()||params.is_null()||stats.is_null()||n>65536{return 1}
 let p=std::slice::from_raw_parts(params,N);if !valid(p){return 2}
 let a=std::slice::from_raw_parts(src,n*3);let sums=std::slice::from_raw_parts_mut(stats,5);
 for i in 0..n{let q=[a[i*3],a[i*3+1],a[i*3+2]];if q.iter().any(|v|!v.is_finite()||v.abs()>128.){return 3}
 let m=if mask.is_null(){1.}else{*mask.add(i)};if !m.is_finite()||!(0.0..=1.0).contains(&m){return 4}
 let(v,_,_)=hsl(q);let w=weight(v,p,m) as f64;sums[0]+=w;sums[1]+=w*(v[0]*TAU).cos() as f64*v[1] as f64;sums[2]+=w*(v[0]*TAU).sin() as f64*v[1] as f64;sums[3]+=w*v[1] as f64;sums[4]+=w*v[2] as f64;
 }0
}
#[no_mangle] pub unsafe extern "C" fn lrt_colour_editor_apply(src:*const f32,mask:*const f32,dst:*mut f32,n:usize,params:*const f32,stats:*const f64,view:u32)->i32{
 if src.is_null()||dst.is_null()||params.is_null()||stats.is_null()||n>65536||view>1{return 1}
 let p=std::slice::from_raw_parts(params,N);if !valid(p){return 2}
 let a=std::slice::from_raw_parts(src,n*3);let out=std::slice::from_raw_parts_mut(dst,n*3);let sums=std::slice::from_raw_parts(stats,5);
 if sums.iter().any(|x|!x.is_finite())||sums[0]<0.{return 5}
 let target=if sums[0]>0.{[if sums[1].hypot(sums[2])<1e-12{p[0]}else{wrap(sums[2].atan2(sums[1]) as f32/TAU)},(sums[3]/sums[0]) as f32,(sums[4]/sums[0]) as f32]}else{[p[0],0.,0.]};
 for i in 0..n {let q=[a[i*3],a[i*3+1],a[i*3+2]];if q.iter().any(|v|!v.is_finite()||v.abs()>128.){return 3}
 let m=if mask.is_null(){1.}else{*mask.add(i)};if !m.is_finite()||!(0.0..=1.0).contains(&m){return 4}
 let(v,black,scale)=hsl(q);let w=weight(v,p,m);
 let result=if view==1{let gray=0.2126*q[0]+0.7152*q[1]+0.0722*q[2];q.map(|x|gray+(x-gray)*w)}
 else if w==0.||(8..14).all(|j|p[j]==0.){q}
 else{let mut t=v;t[0]=wrap(v[0]+distance(target[0],v[0])*p[11]+p[8]*0.5);t[1]=unit(v[1]+(target[1]-v[1])*p[12]+p[9]);t[2]=unit(v[2]+(target[2]-v[2])*p[13]+p[10]);let r=rgb(t);[0,1,2].map(|j|q[j]+(black+r[j]*scale-q[j])*w)};
 out[i*3..i*3+3].copy_from_slice(&result);
 }0
}

#[cfg(test)]
mod tests {
 use super::*;
 fn params()->[f32;N]{[0.,0.08,0.,1.,0.,1.,0.1,0.1,0.,0.,0.,0.,0.,0.,0.,1.]}
 #[test] fn wrapped_hue_selection(){let mut p=params();p[1]=0.03;p[6]=0.;assert_eq!(weight([0.99,1.,0.5],&p,1.),1.);assert_eq!(weight([0.01,1.,0.5],&p,1.),1.);assert_eq!(weight([0.5,1.,0.5],&p,1.),0.);}
 #[test] fn inversion_never_escapes_mask(){let mut p=params();p[14]=1.;assert_eq!(weight([0.5,1.,0.5],&p,0.),0.);assert_eq!(weight([0.5,1.,0.5],&p,0.25),0.25);}
 #[test] fn neutral_bit_identity(){let p=params();let q=[-0.1,0.4,2.];let mut out=[0.;3];let sums=[0.;5];unsafe{assert_eq!(lrt_colour_editor_apply(q.as_ptr(),std::ptr::null(),out.as_mut_ptr(),1,p.as_ptr(),sums.as_ptr(),0),0);}for i in 0..3{assert_eq!(q[i].to_bits(),out[i].to_bits());}}
 #[test] fn range_view_does_not_export(){let p=params();let q=[0.,0.,1.];let mut out=[0.;3];let sums=[0.;5];unsafe{lrt_colour_editor_apply(q.as_ptr(),std::ptr::null(),out.as_mut_ptr(),1,p.as_ptr(),sums.as_ptr(),1);}assert!((out[0]-out[1]).abs()<1e-6);unsafe{lrt_colour_editor_apply(q.as_ptr(),std::ptr::null(),out.as_mut_ptr(),1,p.as_ptr(),sums.as_ptr(),0);}assert_eq!(q,out);}
 #[test] fn stats_partition_is_canonical(){let mut p=params();p[1]=0.5;let q=[1.,0.,0.,0.,1.,0.,0.,0.,1.];let mut full=[0.;5];let mut split=[0.;5];unsafe{lrt_colour_editor_stats(q.as_ptr(),std::ptr::null(),3,p.as_ptr(),full.as_mut_ptr());for i in 0..3{lrt_colour_editor_stats(q.as_ptr().add(i*3),std::ptr::null(),1,p.as_ptr(),split.as_mut_ptr());}}assert_eq!(full,split);}
 #[test] fn independent_colour_luminance_boundaries(){let mut p=params();p[4]=0.4;p[5]=0.6;p[7]=0.2;p[6]=0.;assert!(weight([0.,1.,0.3],&p,1.)>0.);assert_eq!(weight([0.2,1.,0.5],&p,1.),0.);}
 #[test] fn full_uniformity_and_dispersion(){let mut p=params();p[1]=0.5;let a=rgb([0.,0.3,0.5]);let b=rgb([0.,0.7,0.5]);let q=[a[0],a[1],a[2],b[0],b[1],b[2]];let mut sums=[0.;5];let mut out=[0.;6];unsafe{lrt_colour_editor_stats(q.as_ptr(),std::ptr::null(),2,p.as_ptr(),sums.as_mut_ptr());p[12]=1.;lrt_colour_editor_apply(q.as_ptr(),std::ptr::null(),out.as_mut_ptr(),2,p.as_ptr(),sums.as_ptr(),0);}assert!((out[0]-out[3]).abs()<1e-5);p[12]=-1.;unsafe{lrt_colour_editor_apply(q.as_ptr(),std::ptr::null(),out.as_mut_ptr(),2,p.as_ptr(),sums.as_ptr(),0);}let (v,_,_)=hsl([out[0],out[1],out[2]]);assert!((v[1]-0.1).abs()<1e-5);}
 #[test] fn unsafe_values_rejected(){let p=params();let q=[f32::NAN,0.,0.];let mut out=[0.;3];let sums=[0.;5];unsafe{assert_eq!(lrt_colour_editor_apply(q.as_ptr(),std::ptr::null(),out.as_mut_ptr(),1,p.as_ptr(),sums.as_ptr(),0),3);}}
}
