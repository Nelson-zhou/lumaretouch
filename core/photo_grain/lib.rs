//! Original Lumaretouch deterministic source-anchored photo grain. GPL-3.0-or-later.
//! Seven independent controls; no downloaded texture, PRNG state or image allocation.
use std::slice;
const MAX_PIXELS:usize=65536;
fn mix(mut x:u32)->u32 {x^=x>>16;x=x.wrapping_mul(0x7feb352d);x^=x>>15;x=x.wrapping_mul(0x846ca68b);x^(x>>16)}
fn lattice(x:i32,y:i32,seed:u32,channel:u32)->f32 {
    let h=mix((x as u32).wrapping_mul(0x9e3779b9)^(y as u32).wrapping_mul(0x85ebca6b)^seed^channel.wrapping_mul(0xc2b2ae35));
    ((h>>8) as f32)*(2./16777215.)-1.
}
fn smooth(t:f32)->f32 {t*t*(3.-2.*t)}
fn field(x:f32,y:f32,seed:u32,channel:u32)->f32 {
    let ix=x.floor() as i32;let iy=y.floor() as i32;
    let fx=smooth(x-ix as f32);let fy=smooth(y-iy as f32);
    let a=lattice(ix,iy,seed,channel);let b=lattice(ix+1,iy,seed,channel);
    let c=lattice(ix,iy+1,seed,channel);let d=lattice(ix+1,iy+1,seed,channel);
    (a+(b-a)*fx)*(1.-fy)+(c+(d-c)*fx)*fy
}
fn noise(x:f32,y:f32,r:&[f32],seed:u32,channel:u32)->f32 {
    let rough=r[5]/100.;let a=field(x/r[4],y/r[4],seed,channel);
    // Roughness introduces finer independent structure, not a second strength slider.
    let b=field(x*2./r[4],y*2./r[4],seed^0xa511e9b3,channel);
    a*(1.-0.55*rough)+b*(0.55*rough)
}
fn encode(x:f32)->f32 {let a=x.abs();x.signum()*if a<=0.0031308 {12.92*a}else{1.055*a.powf(1./2.4)-0.055}}
fn decode(x:f32)->f32 {let a=x.abs();x.signum()*if a<=0.04045 {a/12.92}else{((a+0.055)/1.055).powf(2.4)}}
fn weights(y:f32)->[f32;3] {
    let y=y.clamp(0.,1.);let s=1.-smooth((y/0.5).clamp(0.,1.));
    let h=smooth(((y-0.5)/0.5).clamp(0.,1.));[s,1.-s-h,h]
}
fn valid(r:&[f32])->bool {r.iter().all(|v|v.is_finite())&&(0..7).all(|i| if i==4 {(0.5..=16.).contains(&r[i])}else{(0.0..=100.).contains(&r[i])})}
fn pixel(p:[f32;3],x:f32,y:f32,r:&[f32],seed:u32,linear:bool)->[f32;3] {
    let e=if linear {p.map(encode)}else{p};
    let w=weights(0.2126*e[0]+0.7152*e[1]+0.0722*e[2]);
    let amplitude=r[0]*0.001*(w[0]*r[1]+w[1]*r[2]+w[2]*r[3])/100.;
    let nx=x+0.5;let ny=y+0.5;let mono=noise(nx,ny,r,seed,0);
    let colour=r[6]/100.;
    let out=std::array::from_fn(|c|e[c]+amplitude*(mono*(1.-colour)+noise(nx,ny,r,seed,c as u32+1)*colour));
    if linear {out.map(decode)}else{out}
}
#[no_mangle] pub extern "C" fn lrt_photo_grain_abi()->u32 {1}
/// Nonoverlapping aligned arrays: n*3 floats input/output and 7 recipe floats.
/// x,y are SOURCE coordinates of first pixel in a single source row, never proxy.
/// mode 0 linear sRGB D65, 1 extended encoded sRGB D65. No clipping.
/// Return 1 ABI/bounds, 2 recipe, 3 input. Invalid input leaves output untouched.
#[no_mangle] pub unsafe extern "C" fn lrt_photo_grain_apply(input:*const f32,output:*mut f32,n:usize,recipe:*const f32,seed:u32,x:u32,y:u32,mode:u32)->i32 {
    if input.is_null()||output.is_null()||recipe.is_null()||n==0||n>MAX_PIXELS||mode>1||x as usize+n>1000000||y>=1000000{return 1;}
    let a=input as usize;let b=output as usize;let c=recipe as usize;let bytes=n*12;
    let overlaps=|a:usize,n:usize,b:usize,m:usize|a<b.saturating_add(m)&&b<a.saturating_add(n);
    if a%4!=0||b%4!=0||c%4!=0||overlaps(a,bytes,b,bytes)||overlaps(c,28,b,bytes){return 1;}
    let r=slice::from_raw_parts(recipe,7);if !valid(r){return 2;}
    let src=slice::from_raw_parts(input,n*3);let limit=if mode==0 {65504.}else{128.};
    if src.iter().any(|v|!v.is_finite()||v.abs()>limit){return 3;}
    let dst=slice::from_raw_parts_mut(output,n*3);
    if r[0]==0.||(r[1]==0.&&r[2]==0.&&r[3]==0.) {dst.copy_from_slice(src);return 0;}
    for (i,(s,d)) in src.chunks_exact(3).zip(dst.chunks_exact_mut(3)).enumerate(){
        d.copy_from_slice(&pixel([s[0],s[1],s[2]],(x+i as u32) as f32,y as f32,r,seed,mode==0));
    }0
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn source_coordinates_not_tile_origin(){let r=[50.,100.,100.,100.,1.5,50.,30.];let a=pixel([0.4;3],125.,43.,&r,123,true);let b=pixel([0.4;3],125.,43.,&r,123,true);assert_eq!(a,b);}
    #[test] fn monochrome_and_colour_differ(){let mut r=[50.,100.,100.,100.,1.5,50.,0.];let a=pixel([0.5;3],10.,20.,&r,5,false);assert_eq!(a[0],a[1]);r[6]=100.;let b=pixel([0.5;3],10.,20.,&r,5,false);assert_ne!(b[0],b[1]);}
    #[test] fn tonal_partitions(){assert_eq!(weights(0.),[1.,0.,0.]);assert_eq!(weights(0.5),[0.,1.,0.]);assert_eq!(weights(1.),[0.,0.,1.]);}
    #[test] fn preserves_signed_headroom(){let r=[50.,100.,100.,100.,1.5,50.,0.];let p=pixel([-0.5,2.,4.],2.,3.,&r,1,false);assert!(p[0]<0.&&p[1]>1.&&p[2]>1.);}
}

/// Mapped source coordinate triples (sx,sy,valid) for one output row band.
/// Coordinate storage is caller-owned, bounded to n triples; no raster noise map.
#[no_mangle] pub unsafe extern "C" fn lrt_photo_grain_apply_mapped(input:*const f32,output:*mut f32,n:usize,recipe:*const f32,seed:u32,coords:*const f32,mode:u32)->i32 {
    if input.is_null()||output.is_null()||recipe.is_null()||coords.is_null()||n==0||n>MAX_PIXELS||mode>1{return 1;}
    let a=input as usize;let b=output as usize;let c=recipe as usize;let d=coords as usize;let bytes=n*12;
    let overlap=|a:usize,n:usize,b:usize,m:usize|a<b.saturating_add(m)&&b<a.saturating_add(n);
    if a%4!=0||b%4!=0||c%4!=0||d%4!=0||overlap(a,bytes,b,bytes)||overlap(c,28,b,bytes)||overlap(d,bytes,b,bytes){return 1;}
    let r=slice::from_raw_parts(recipe,7);if !valid(r){return 2;}
    let src=slice::from_raw_parts(input,n*3);let xy=slice::from_raw_parts(coords,n*3);
    let limit=if mode==0{65504.}else{128.};
    if src.iter().any(|v|!v.is_finite()||v.abs()>limit)||xy.chunks_exact(3).any(|v|!v.iter().all(|a|a.is_finite())||v[0].abs()>1000000.||v[1].abs()>1000000.||!(v[2]==0.||v[2]==1.)){return 3;}
    let dst=slice::from_raw_parts_mut(output,n*3);
    for ((s,d),c) in src.chunks_exact(3).zip(dst.chunks_exact_mut(3)).zip(xy.chunks_exact(3)) {
        if c[2]==0.||r[0]==0.||(r[1]==0.&&r[2]==0.&&r[3]==0.) {d.copy_from_slice(s);}else{d.copy_from_slice(&pixel([s[0],s[1],s[2]],c[0],c[1],r,seed,mode==0));}
    }0
}
