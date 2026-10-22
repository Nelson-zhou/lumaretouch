// SPDX-License-Identifier: GPL-3.0-or-later
pub struct Stroke {pub mode:u8,pub fixed:bool,pub density:f64,pub pressure:f64,pub rate:f64,pub direction:f64,pub axes:[f64;4],pub points:Vec<[f64;4]>}
pub struct Request {pub w:usize,pub h:usize,pub strokes:Vec<Stroke>}
struct Reader<'a>{b:&'a [u8],i:usize}
impl<'a> Reader<'a> {
    fn take<const N:usize>(&mut self)->Result<[u8;N],&'static str>{
        let end=self.i.checked_add(N).ok_or("packet overflow")?;
        let out=self.b.get(self.i..end).ok_or("truncated packet")?.try_into().map_err(|_|"truncated packet")?;
        self.i=end;Ok(out)
    }
    fn byte(&mut self)->Result<u8,&'static str>{Ok(self.take::<1>()?[0])}
    fn uint(&mut self)->Result<usize,&'static str>{Ok(u32::from_le_bytes(self.take()?) as usize)}
    fn num(&mut self,low:f64,high:f64)->Result<f64,&'static str>{let n=f64::from_le_bytes(self.take()?);if !n.is_finite()||n<low||n>high{Err("nonfinite or out-of-range number")}else{Ok(n)}}
}
pub fn decode(bytes:&[u8])->Result<Request,&'static str>{
    let mut r=Reader{b:bytes,i:0};if r.take::<4>()?!=*b"LQL1"{return Err("incompatible liquify worker protocol");}
    let w=r.uint()?;let h=r.uint()?;let count=r.uint()?;
    if w<1||h<1||w>65536||h>65536||w.checked_mul(h).ok_or("size overflow")?>64_000_000||count>128{return Err("liquify image or stroke budget exceeded");}
    let mut strokes=Vec::with_capacity(count);let mut total=0;
    for _ in 0..count {
        let mode=r.byte()?;let fixed=r.byte()?;if mode>8||fixed>1{return Err("invalid mode or edge lock");}
        let density=r.num(0.0,1.0)?;let pressure=r.num(0.0,1.0)?;let rate=r.num(0.0,1.0)?;let direction=r.num(-1.0,1.0)?;
        if direction!=1.0&&direction!= -1.0{return Err("invalid rotation direction");}
        let axes=[r.num(-4.0,4.0)?,r.num(-4.0,4.0)?,r.num(-4.0,4.0)?,r.num(-4.0,4.0)?];
        if (axes[0]*axes[3]-axes[1]*axes[2]).abs()<1e-12{return Err("degenerate brush axes");}
        let n=r.uint()?;total+=n;if n<1||n>2048||total>8192{return Err("liquify point budget exceeded");}
        let mut points=Vec::with_capacity(n);let mut previous=0.0;
        for j in 0..n {
            let point=[r.num(0.0,1.0)?,r.num(0.0,1.0)?,r.num(0.0,1.0)?,r.num(0.0,60000.0)?];
            if (j==0&&point[3]!=0.0)||(j>0&&(point[3]<previous||point[3]-previous>1000.0)){return Err("invalid gesture timeline");}
            previous=point[3];points.push(point);
        }
        strokes.push(Stroke{mode,fixed:fixed==1,density,pressure,rate,direction,axes,points});
    }
    if r.i!=bytes.len(){return Err("trailing liquify input");}Ok(Request{w,h,strokes})
}
