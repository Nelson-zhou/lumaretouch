// SPDX-License-Identifier: LGPL-3.0-or-later
// GEGL warp algorithm adaptation: Copyright 2011 Michael Muré.
// Rust bounded replay, affine brush domains, protection and timing: LumaRetouch contributors.
// See README.md for exact upstream references, changes and license obligations.
use crate::wire::{Request, Stroke};
pub const MAX_WORK: u64 = 16_000_000_000;
pub const MAX_DABS: usize = 32768;
#[derive(Clone, Copy, Default)]
pub struct Pixel { pub dx: f32, pub dy: f32, pub freeze: f32 }

fn force(radius: f64, density: f64) -> f64 {
    if radius >= 1.0 { return 0.0; }
    if density >= 1.0 - 0.0000004 { return 1.0; }
    // GEGL's compact, piecewise-quadratic Gaussian approximation, evaluated
    // directly in normalized elliptical coordinates rather than a pixel LUT.
    let x = radius.powf(0.4 / (1.0-density));
    if x < 0.5 { 1.0-2.0*x*x } else { 2.0*(1.0-x).powi(2) }
}
fn sample(field: &[Pixel], w: usize, h: usize, x: f64, y: f64) -> [f64;2] {
    let x=x.clamp(0.0,(w-1) as f64); let y=y.clamp(0.0,(h-1) as f64);
    let a=x.floor() as usize; let b=y.floor() as usize;
    let c=(a+1).min(w-1); let d=(b+1).min(h-1);
    let u=x-a as f64; let v=y-b as f64;
    let p=[field[b*w+a],field[b*w+c],field[d*w+a],field[d*w+c]];
    let mut out=[0.0;2];
    for (k,result) in out.iter_mut().enumerate() {
        let q=p.map(|p| if k==0 {p.dx as f64} else {p.dy as f64});
        *result=(q[0]*(1.0-u)+q[1]*u)*(1.0-v)+(q[2]*(1.0-u)+q[3]*u)*v;
    }
    out
}
fn dab(field: &mut [Pixel], r: &Request, s: &Stroke, center:[f64;2], motion:[f64;2], pressure:f64, dt:f64, work:&mut u64) -> Result<(), &'static str> {
    let (w,h)=(r.w,r.h); let (wf,hf)=(w as f64,h as f64);
    let [a,b,c,d]=s.axes; let det=a*d-b*c;
    let rx=a.hypot(c); let ry=b.hypot(d);
    let x0=((center[0]-rx)*wf-0.5).ceil().clamp(0.0,wf) as usize;
    let y0=((center[1]-ry)*hf-0.5).ceil().clamp(0.0,hf) as usize;
    let x1=(((center[0]+rx)*wf-0.5).floor()+1.0).clamp(0.0,wf) as usize;
    let y1=(((center[1]+ry)*hf-0.5).floor()+1.0).clamp(0.0,hf) as usize;
    if x1<=x0 || y1<=y0 {return Ok(());}
    let n=(x1-x0)*(y1-y0);
    *work=work.checked_add(n as u64*24).ok_or("liquify work overflow")?;
    if *work>MAX_WORK {return Err("liquify replay exceeds bounded work budget; reduce strokes or brush size");}
    let weight=|x:usize,y:usize| {
        let px=(x as f64+0.5)/wf-center[0];let py=(y as f64+0.5)/hf-center[1];
        let u=(d*px-c*py)/det;let v=(-b*px+a*py)/det;
        force(u.hypot(v),s.density)
    };
    let timed=1.0-(-6.0*s.rate*s.pressure*pressure*dt/1000.0).exp();
    let mut mean=[0.0;2];let mut total=0.0;
    if s.mode==2 {
        for y in y0..y1 {for x in x0..x1 {
            let p=field[y*w+x];let q=weight(x,y)*(1.0-p.freeze as f64);
            mean[0]+=q*p.dx as f64;mean[1]+=q*p.dy as f64;total+=q;
        }}
        if total>0.0 {mean[0]/=total;mean[1]/=total;}
    }
    // All reads see the previous field, not a scan-order-dependent half update.
    let mut patch=Vec::with_capacity(n);
    for y in y0..y1 {for x in x0..x1 {
        let old=field[y*w+x];let f=weight(x,y);
        let mut new=old;
        if s.mode==7 {new.freeze=(old.freeze as f64+timed*f).clamp(0.0,1.0) as f32;}
        else if s.mode==8 {new.freeze=(old.freeze as f64-timed*f).clamp(0.0,1.0) as f32;}
        else if f>0.0 && old.freeze<1.0 {
            let edge=if s.fixed {
                let band=(wf.min(hf)*0.02).max(1.0);
                let t=(x.min(w-1-x).min(y.min(h-1-y)) as f64/band).clamp(0.0,1.0);
                t*t*(3.0-2.0*t)
            } else {1.0};
            let influence=f*(1.0-old.freeze as f64)*edge;
            let mix=timed*influence;
            let px=(x as f64+0.5)/wf-center[0];let py=(y as f64+0.5)/hf-center[1];
            let delta=if s.mode==1 {[old.dx as f64*(1.0-mix),old.dy as f64*(1.0-mix)]}
            else if s.mode==2 {[old.dx as f64+mix*(mean[0]-old.dx as f64),old.dy as f64+mix*(mean[1]-old.dy as f64)]}
            else {
                let v=match s.mode {
                    0=>[-motion[0]*s.pressure*pressure*s.rate*influence,-motion[1]*s.pressure*pressure*s.rate*influence],
                    3=>{let u=(d*px-c*py)/det;let v=(-b*px+a*py)/det;
                        let theta=-mix*std::f64::consts::FRAC_PI_4*s.direction;
                        let (sn,cs)=theta.sin_cos();let nu=cs*u-sn*v-u;let nv=sn*u+cs*v-v;
                        [a*nu+c*nv,b*nu+d*nv]},
                    4=>[px*mix*0.25,py*mix*0.25],
                    5=>[-px*mix*0.25,-py*mix*0.25],
                    // Reference defines horizontal left, in the gesture's displayed orientation.
                    6=>[a*mix*0.25,b*mix*0.25],
                    _=>return Err("invalid liquify mode"),
                };
                let v=[v[0]*wf,v[1]*hf];let sampled=sample(field,w,h,x as f64+v[0],y as f64+v[1]);
                [sampled[0]+v[0],sampled[1]+v[1]]
            };
            if delta.iter().any(|n|!n.is_finite()||n.abs()>65536.0) {return Err("liquify displacement overflow");}
            new.dx=delta[0] as f32;new.dy=delta[1] as f32;
        }
        patch.push(new);
    }}
    let mut i=0;for y in y0..y1 {for x in x0..x1 {field[y*w+x]=patch[i];i+=1;}}
    Ok(())
}

pub fn replay(r:&Request) -> Result<Vec<Pixel>, &'static str> {
    let mut field=vec![Pixel::default();r.w*r.h];let mut work=0;let mut dabs=0;
    for s in &r.strokes {
        let [a,b,c,d]=s.axes;let det=a*d-b*c;
        let first=s.points[0];
        // A click is one 16 ms dab; timestamps then integrate real held duration.
        dab(&mut field,r,s,[first[0],first[1]],[0.0,0.0],first[2],16.0,&mut work)?;
        dabs+=1;
        for pair in s.points.windows(2) {
            let p=pair[0];let q=pair[1];let dx=q[0]-p[0];let dy=q[1]-p[1];
            let distance=((d*dx-c*dy)/det).hypot((-b*dx+a*dy)/det);
            let dt=q[3]-p[3];
            let steps=((distance/0.10).ceil().max((dt/16.0).ceil()).max(1.0)) as usize;
            dabs=dabs.checked_add(steps).ok_or("liquify dab budget overflow")?;
            if dabs>MAX_DABS {return Err("liquify replay exceeds 32768 dabs");}
            for i in 1..=steps {
                let t=i as f64/steps as f64;
                dab(&mut field,r,s,[p[0]+dx*t,p[1]+dy*t],[dx/steps as f64,dy/steps as f64],p[2]+(q[2]-p[2])*t,dt/steps as f64,&mut work)?;
            }
        }
    }
    Ok(field)
}
