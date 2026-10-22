//! Bounded source-normalized brush coverage. Float coverage, real flow, per-stroke
//! opacity ceiling, feathered elliptical dabs, ordered add/subtract. No RGB.
use std::io::{self,Read,Write};
const MAX_PIXELS:usize=64_000_000;
struct Reader {bytes:Vec<u8>,pos:usize}
impl Reader {
 fn take<const N:usize>(&mut self)->Result<[u8;N],String>{let end=self.pos.checked_add(N).ok_or("overflow")?;let a=self.bytes.get(self.pos..end).ok_or("truncated")?.try_into().unwrap();self.pos=end;Ok(a)}
 fn u32(&mut self)->Result<usize,String>{Ok(u32::from_le_bytes(self.take()?) as usize)}
 fn f64(&mut self)->Result<f64,String>{let n=f64::from_le_bytes(self.take()?);if !n.is_finite(){return Err("nonfinite parameter".into())}Ok(n)}
 fn unit(&mut self)->Result<f64,String>{let v=self.f64()?;if !(0.0..=1.0).contains(&v){return Err("unit parameter".into())}Ok(v)}
}
fn main(){if let Err(e)=run(){eprintln!("studio-background: {e}");std::process::exit(1)}}
fn run()->Result<(),String>{
 let mut input=io::stdin().lock();let mut head=[0;4];input.read_exact(&mut head).map_err(|e|e.to_string())?;
 let len=u32::from_le_bytes(head) as usize;if len>1024*1024{return Err("request budget".into())}
 let mut bytes=vec![0;len];input.read_exact(&mut bytes).map_err(|e|e.to_string())?;
 let mut extra=[0;1];if input.read(&mut extra).map_err(|e|e.to_string())?!=0{return Err("trailing input".into())}
 let mut r=Reader{bytes,pos:0};if r.take::<4>()?!=*b"SBM1"{return Err("protocol".into())}
 let w=r.u32()?;let h=r.u32()?;let count=r.u32()?;
 let pixels=w.checked_mul(h).ok_or("size overflow")?;
 if w==0||h==0||w>65536||h>65536||pixels>MAX_PIXELS||count>128{return Err("shape/stroke budget".into())}
 let mut bias=vec![0f32;pixels];let mut gain=vec![1f32;pixels];let mut total_points=0;let mut total_dabs=0usize;let mut work=0usize;
 for _ in 0..count {
  let op=r.take::<1>()?[0];if op>1{return Err("operation".into())}
  let feather=r.unit()?;let flow=r.unit()?;let opacity=r.unit()?;
  let a=r.f64()?;let b=r.f64()?;let c=r.f64()?;let d=r.f64()?;let det=a*d-b*c;
  if [a,b,c,d].iter().any(|v|v.abs()>4.)||det.abs()<1e-12{return Err("axes".into())}
  let n=r.u32()?;total_points+=n;if n==0||n>2048||total_points>8192{return Err("points".into())}
  let mut points=Vec::with_capacity(n);for _ in 0..n {points.push([r.unit()?,r.unit()?,r.unit()?]);}
  let ex=(a*a+c*c).sqrt()*w as f64;let ey=(b*b+d*d).sqrt()*h as f64;
  let mut stroke=vec![0f32;pixels];
  let mut dab=|p:[f64;3]|->Result<(),String>{
   total_dabs+=1;if total_dabs>65536{return Err("dab budget".into())}
   let cx=p[0]*w as f64-0.5;let cy=p[1]*h as f64-0.5;
   let x0=((cx-ex).floor().max(0.) as usize).min(w);let x1=((cx+ex).ceil().max(0.) as usize+1).min(w);
   let y0=((cy-ey).floor().max(0.) as usize).min(h);let y1=((cy+ey).ceil().max(0.) as usize+1).min(h);
   work=work.checked_add((x1-x0)*(y1-y0)).ok_or("work overflow")?;if work>2_000_000_000{return Err("work budget".into())}
   for y in y0..y1 {for x in x0..x1 {
    let dx=(x as f64-cx)/w as f64;let dy=(y as f64-cy)/h as f64;
    let radius=(((d*dx-c*dy)/det).powi(2)+((-b*dx+a*dy)/det).powi(2)).sqrt();
    if radius>=1.{continue}
    let t=if feather==0.{1.}else{((1.-radius)/feather).clamp(0.,1.)};let soft=t*t*(3.-2.*t);
    let coverage=(soft*flow*p[2]) as f32;let i=y*w+x;
    stroke[i]+= (1.-stroke[i])*coverage;
   }}Ok(())
  };
  dab(points[0])?;
  for pair in points.windows(2) {let p=pair[0];let q=pair[1];let dx=q[0]-p[0];let dy=q[1]-p[1];
   let distance=(((d*dx-c*dy)/det).powi(2)+((-b*dx+a*dy)/det).powi(2)).sqrt();
   let steps=(distance/0.15).ceil().max(1.) as usize;
   if steps>65536{return Err("segment budget".into())}
   for j in 1..=steps {let t=j as f64/steps as f64;dab([p[0]+dx*t,p[1]+dy*t,p[2]+(q[2]-p[2])*t])?;}
  }
  for i in 0..pixels {let alpha=stroke[i]*opacity as f32;gain[i]*=1.-alpha;
   if op==0 {bias[i]+=(1.-bias[i])*alpha;}else{bias[i]*=1.-alpha;}}
 }
 if r.pos!=r.bytes.len(){return Err("trailing request".into())}
 let mut out=io::BufWriter::new(io::stdout().lock());out.write_all(b"SBF1").map_err(|e|e.to_string())?;
 out.write_all(&((pixels*8) as u64).to_le_bytes()).map_err(|e|e.to_string())?;
 for field in [&bias,&gain] {for v in field {out.write_all(&v.to_le_bytes()).map_err(|e|e.to_string())?;}}
 out.flush().map_err(|e|e.to_string())
}
