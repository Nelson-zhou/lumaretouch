// SPDX-License-Identifier: GPL-3.0-or-later
// Original Lumaretouch source-pixel area integrated decorative micro-marks.
// No copied reference artwork, stochastic samples, skin repair or blur kernel.
use std::f64::consts::TAU;
use std::mem::{align_of, size_of};
use std::slice;

const MAX_PIXELS: usize = 4_000_000;
const MAX_MARKS: usize = 64;
const MAX_CLIP_CANDIDATES: usize = 32_000_000;
const SECTORS: usize = 12;

#[derive(Clone, Copy, Default)]
struct Vertex { x: f64, y: f64, a: f64 }

impl Vertex {
    fn interpolate(self, other: Self, t: f64) -> Self {
        Self { x: self.x + (other.x-self.x)*t,
               y: self.y + (other.y-self.y)*t,
               a: self.a + (other.a-self.a)*t }
    }
}

#[derive(Clone, Copy)]
struct Triangle { points: [Vertex; 3], bounds: [usize; 4] }

fn coordinate(v: Vertex, axis: usize) -> f64 { if axis == 0 { v.x } else { v.y } }

/// Clip a convex triangle to the actual source pixel square. Alpha is affine
/// within each triangle, so its integral is area times mean vertex alpha after
/// triangulation. This integrates arbitrarily subpixel marks without sample
/// misses or a hidden minimum dot size. Geometry uses f64 for stable clipping;
/// source, support, coverage and returned working-sRGB contribution are f32.
fn pixel_integral(triangle: &[Vertex; 3], x: usize, y: usize) -> f64 {
    let mut a = [Vertex::default(); 12];
    let mut b = [Vertex::default(); 12];
    let mut n = 3;
    for (dst, src) in a.iter_mut().zip(triangle) {
        *dst = Vertex { x: src.x-x as f64, y: src.y-y as f64, a: src.a };
    }
    for (axis, boundary, greater) in [(0,0.0,true),(0,1.0,false),(1,0.0,true),(1,1.0,false)] {
        if n < 3 { return 0.0; }
        let mut count = 0;
        let mut previous = a[n-1];
        let mut previous_in = if greater { coordinate(previous,axis)>=boundary } else { coordinate(previous,axis)<=boundary };
        for current in a[..n].iter().copied() {
            let current_in = if greater { coordinate(current,axis)>=boundary } else { coordinate(current,axis)<=boundary };
            if current_in != previous_in {
                let t = (boundary-coordinate(previous,axis)) / (coordinate(current,axis)-coordinate(previous,axis));
                b[count] = previous.interpolate(current,t.clamp(0.0,1.0));
                count += 1;
            }
            if current_in { b[count]=current; count+=1; }
            previous=current; previous_in=current_in;
        }
        std::mem::swap(&mut a,&mut b); n=count;
    }
    let mut integral = 0.0;
    for i in 1..n.saturating_sub(1) {
        let p=a[0]; let q=a[i]; let r=a[i+1];
        let area=((q.x-p.x)*(r.y-p.y)-(q.y-p.y)*(r.x-p.x)).abs()*0.5;
        integral += area*(p.a+q.a+r.a)/3.0;
    }
    integral.clamp(0.0,1.0)
}

fn push_triangle(triangles: &mut Vec<Triangle>, points: [Vertex;3], width: usize,
                 height: usize, work: &mut usize) -> Result<(),i32> {
    let xmin=points.iter().map(|p|p.x).fold(f64::INFINITY,f64::min);
    let xmax=points.iter().map(|p|p.x).fold(f64::NEG_INFINITY,f64::max);
    let ymin=points.iter().map(|p|p.y).fold(f64::INFINITY,f64::min);
    let ymax=points.iter().map(|p|p.y).fold(f64::NEG_INFINITY,f64::max);
    let x0=xmin.floor().clamp(0.0,width as f64) as usize;
    let x1=xmax.ceil().clamp(0.0,width as f64) as usize;
    let y0=ymin.floor().clamp(0.0,height as f64) as usize;
    let y1=ymax.ceil().clamp(0.0,height as f64) as usize;
    *work=work.checked_add((x1-x0)*(y1-y0)).ok_or(3)?;
    if *work>MAX_CLIP_CANDIDATES { return Err(3); }
    if x0<x1 && y0<y1 { triangles.push(Triangle{points,bounds:[x0,y0,x1,y1]}); }
    Ok(())
}

fn triangles(frame: &[f32], marks: &[f32], width: usize, height: usize) -> Result<Vec<Triangle>,i32> {
    let mut result=Vec::new();
    result.try_reserve_exact((marks.len()/7)*SECTORS*3).map_err(|_|4)?;
    let mut work=0;
    for mark in marks.chunks_exact(7) {
        let (s,c)=(mark[4] as f64).sin_cos();
        let transform=|u:f64,v:f64,alpha:f64|Vertex {
            x:frame[0] as f64+u*frame[2] as f64+v*frame[4] as f64,
            y:frame[1] as f64+u*frame[3] as f64+v*frame[5] as f64,a:alpha };
        let center=transform(mark[0] as f64,mark[1] as f64,mark[5] as f64);
        let mut outer=[Vertex::default();SECTORS];
        let mut inner=[Vertex::default();SECTORS];
        for j in 0..SECTORS {
            let angle=TAU*j as f64/SECTORS as f64;
            let (sn,cs)=angle.sin_cos();
            // An original bounded pebble edge, not a random or sampled texture.
            let radius=1.0+0.07*(3.0*angle+mark[6] as f64).cos();
            let a=mark[2] as f64*cs*radius;
            let b=mark[3] as f64*sn*radius;
            let du=a*c-b*s; let dv=a*s+b*c;
            outer[j]=transform(mark[0] as f64+du,mark[1] as f64+dv,0.0);
            inner[j]=transform(mark[0] as f64+du*0.38,mark[1] as f64+dv*0.38,mark[5] as f64);
        }
        for j in 0..SECTORS {
            let next=(j+1)%SECTORS;
            push_triangle(&mut result,[center,inner[j],inner[next]],width,height,&mut work)?;
            push_triangle(&mut result,[inner[j],outer[j],outer[next]],width,height,&mut work)?;
            push_triangle(&mut result,[inner[j],outer[next],inner[next]],width,height,&mut work)?;
        }
    }
    Ok(result)
}

fn aligned(pointer: *const f32) -> bool { !pointer.is_null() && (pointer as usize)%align_of::<f32>()==0 }

fn disjoint(a: *const f32, an: usize, b: *const f32, bn: usize) -> bool {
    match ((a as usize).checked_add(an*size_of::<f32>()),(b as usize).checked_add(bn*size_of::<f32>())) {
        (Some(a1),Some(b1)) => a1<=b as usize || b1<=a as usize,
        _ => false,
    }
}

#[no_mangle]
pub extern "C" fn lrt_face_decoration_abi() -> u32 { 1 }

/// Return codes: 0 success; 1 shape/pointer/scalar; 2 invalid data/geometry;
/// 3 exact-raster work budget exceeded; 4 allocation refused. Rejections do not
/// write any output. No runtime filesystem, model, network, GPU or RNG use.
///
/// # Safety
/// Caller owns initialized aligned readable arrays: src=width*height*3,
/// frame=6 (origin x,y; u-axis x,y; v-axis x,y), support=width*height,
/// marks=mark_count*7 (u,v,ru,rv,rotation,opacity,edge phase); output is separate
/// writable width*height*3. All buffers remain live for this synchronous call.
#[no_mangle]
pub unsafe extern "C" fn lrt_face_decoration_delta(
    src:*const f32, frame:*const f32, support:*const f32, width:usize, height:usize,
    marks:*const f32, mark_count:usize, strength:f32, output:*mut f32,
) -> i32 {
    let count=match width.checked_mul(height) {Some(n) if n>0 && n<=MAX_PIXELS=>n,_=>return 1};
    if mark_count==0 || mark_count>MAX_MARKS || !strength.is_finite() || !(0.0..=1.0).contains(&strength)
        || [src,frame,support,marks,output as *const f32].iter().any(|p|!aligned(*p))
        || [(src,count*3),(frame,6),(support,count),(marks,mark_count*7)].iter()
            .any(|(p,n)|!disjoint(*p,*n,output,count*3)) {return 1;}
    let source=slice::from_raw_parts(src,count*3);
    let frame=slice::from_raw_parts(frame,6);
    let support=slice::from_raw_parts(support,count);
    let marks=slice::from_raw_parts(marks,mark_count*7);
    if source.iter().chain(support.iter()).any(|v|!v.is_finite() || !(0.0..=1.0).contains(v))
        || frame.iter().chain(marks.iter()).any(|v|!v.is_finite())
        || frame.iter().any(|v|v.abs()>1_000_000.0)
        || marks.chunks_exact(7).any(|m| m[0].abs()>2.0 || m[1].abs()>2.0
            || !(0.002..=0.06).contains(&m[2]) || !(0.002..=0.06).contains(&m[3])
            || m[4].abs()>TAU as f32 || m[6].abs()>TAU as f32 || !(0.0..=1.0).contains(&m[5])) {return 2;}
    let ux=frame[2] as f64; let uy=frame[3] as f64;
    let vx=frame[4] as f64; let vy=frame[5] as f64;
    let us=ux.hypot(uy); let vs=vx.hypot(vy);
    if !(1.0..=100_000.0).contains(&us) || !(1.0..=100_000.0).contains(&vs)
        || (ux*vy-uy*vx).abs()<0.25*us*vs {return 2;}
    // Even neutral validates the FFI buffers, but never allocates a raster or
    // changes the source. The host neutral path need not load this library.
    if strength==0.0 || !support.iter().any(|v|*v>0.0) {
        slice::from_raw_parts_mut(output,count*3).fill(0.0); return 0;
    }
    let triangles=match triangles(frame,marks,width,height) {Ok(v)=>v,Err(code)=>return code};
    let mut coverage=Vec::<f32>::new();
    if coverage.try_reserve_exact(count).is_err() {return 4;}
    coverage.resize(count,0.0);
    for triangle in triangles {
        let [x0,y0,x1,y1]=triangle.bounds;
        for y in y0..y1 { for x in x0..x1 {
            let index=y*width+x;
            if support[index]==0.0 {continue;}
            coverage[index]+=(pixel_integral(&triangle.points,x,y) as f32).max(0.0);
        }}
    }
    let output=slice::from_raw_parts_mut(output,count*3);
    let absorption=[0.40_f32,0.57,0.68];
    for i in 0..count {
        let alpha=coverage[i].clamp(0.0,1.0)*support[i]*strength;
        for c in 0..3 {
            // Multiplicative warm-brown pigment preserves original texture and
            // scales across skin luminance. It never lightens or removes spots.
            output[3*i+c]=if alpha==0.0 {0.0} else {-source[3*i+c]*(alpha*absorption[c])};
        }
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;
    // Authored UNRUN. Synthetic numerical fixtures are not portrait acceptance.
    fn render(width:usize,height:usize,frame:[f32;6],mark:[f32;7],strength:f32) -> Vec<f32> {
        let source=vec![0.5;width*height*3]; let support=vec![1.0;width*height];
        let mut out=vec![9.0;source.len()];
        let code=unsafe {lrt_face_decoration_delta(source.as_ptr(),frame.as_ptr(),support.as_ptr(),width,height,
            mark.as_ptr(),1,strength,out.as_mut_ptr())};
        assert_eq!(code,0); assert!(source.iter().all(|v|*v==0.5)); out
    }
    #[test] fn neutral_is_exact() {
        assert!(render(8,8,[4.0,4.0,20.0,0.0,0.0,20.0],[0.0,0.0,0.01,0.01,0.0,0.6,0.0],0.0)
            .iter().all(|v|*v==0.0));
    }
    #[test] fn invalid_is_atomic() {
        let source=[f32::NAN,0.5,0.5]; let frame=[0.5,0.5,20.0,0.0,0.0,20.0];
        let support=[1.0]; let mark=[0.0,0.0,0.01,0.01,0.0,0.6,0.0]; let mut out=[9.0;3];
        let code=unsafe {lrt_face_decoration_delta(source.as_ptr(),frame.as_ptr(),support.as_ptr(),1,1,mark.as_ptr(),1,1.0,out.as_mut_ptr())};
        assert_eq!(code,2); assert_eq!(out,[9.0;3]);
    }
    #[test] fn subpixel_mark_mass_survives_translation() {
        let mark=[0.0,0.0,0.003,0.003,0.31,0.6,1.2];
        let a=render(8,8,[3.2,3.1,20.0,0.0,0.0,20.0],mark,1.0);
        let b=render(8,8,[3.97,3.99,20.0,0.0,0.0,20.0],mark,1.0);
        let sum=|v:Vec<f32>|v.iter().map(|x|*x as f64).sum::<f64>();
        let (sa,sb)=(sum(a),sum(b)); assert!(sa< -0.00001); assert!((sa-sb).abs()<1e-7);
    }
    #[test] fn coarse_and_fine_integrated_mass_agree() {
        let mark=[0.0,0.0,0.011,0.016,0.31,0.6,1.2];
        let a=render(16,16,[8.1,7.9,30.0,0.0,0.0,30.0],mark,1.0);
        let b=render(32,32,[16.2,15.8,60.0,0.0,0.0,60.0],mark,1.0);
        let sa=a.iter().map(|x|*x as f64).sum::<f64>();
        let sb=b.iter().map(|x|*x as f64).sum::<f64>()/4.0;
        assert!((sa-sb).abs()<1e-6);
    }
    #[test] fn pixel_integral_matches_triangle_area() {
        let triangle=[Vertex{x:0.0,y:0.0,a:1.0},Vertex{x:1.0,y:0.0,a:1.0},Vertex{x:0.0,y:1.0,a:1.0}];
        assert!((pixel_integral(&triangle,0,0)-0.5).abs()<1e-12);
    }
    #[test] fn no_support_is_exact_and_source_is_unchanged() {
        let source=[0.123456,0.567891,0.912345]; let before=source;
        let frame=[0.5,0.5,20.0,0.0,0.0,20.0]; let support=[0.0];
        let mark=[0.0,0.0,0.02,0.02,0.0,0.9,0.0]; let mut out=[9.0;3];
        let code=unsafe {lrt_face_decoration_delta(source.as_ptr(),frame.as_ptr(),support.as_ptr(),1,1,mark.as_ptr(),1,1.0,out.as_mut_ptr())};
        assert_eq!(code,0); assert_eq!(source,before);
        assert!(out.iter().all(|v|v.to_bits()==0));
    }
    #[test] fn exact_work_budget_refuses_before_output() {
        let points=[Vertex{x:0.0,y:0.0,a:1.0},Vertex{x:2000.0,y:0.0,a:1.0},Vertex{x:0.0,y:2000.0,a:1.0}];
        let mut triangles=Vec::new(); let mut work=MAX_CLIP_CANDIDATES;
        assert_eq!(push_triangle(&mut triangles,points,2000,2000,&mut work),Err(3));
        assert!(triangles.is_empty());
    }
}
