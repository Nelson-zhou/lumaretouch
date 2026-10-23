//! Original bounded Adobe CUBE 1.0 reader. No third-party implementation copied.
use std::{ffi::c_void, panic::{catch_unwind, AssertUnwindSafe}, slice};
pub const MAX_BYTES: usize = 32 * 1024 * 1024;
pub const MAX_PIXELS: usize = 262144;
#[derive(Debug)]
pub struct Cube { pub size: usize, pub dimension: usize, pub title: String, pub min: [f64;3], pub max: [f64;3], pub rows: Vec<[f64;3]> }
fn number(s: &str) -> Result<f64,String> {
    if s.is_empty() || !s.bytes().all(|b| b.is_ascii_digit() || b"+-.eE".contains(&b)) { return Err("invalid decimal".into()); }
    let v = s.parse::<f64>().map_err(|_| "invalid decimal")?;
    if !v.is_finite() || v.abs() > 1e37 { return Err("number exceeds CUBE finite range".into()); } Ok(v)
}
fn triple(s: &str) -> Result<[f64;3],String> {
    let a: Vec<_> = s.split_whitespace().collect();
    if a.len()!=3 {return Err("expected exactly three numbers".into());}
    Ok([number(a[0])?,number(a[1])?,number(a[2])?])
}
pub fn parse(bytes: &[u8]) -> Result<Cube,String> {
    if bytes.len()>MAX_BYTES {return Err("CUBE exceeds 32 MiB".into());}
    // CRLF is a documented compatibility extension; bare CR is not accepted.
    let text=std::str::from_utf8(bytes).map_err(|_| "invalid UTF-8")?;
    let mut c=Cube{size:0,dimension:0,title:String::new(),min:[0.;3],max:[1.;3],rows:Vec::new()};
    let mut seen=[false;4]; let mut expected=0;
    for (i,raw) in text.split('\n').enumerate() {
        let raw=raw.strip_suffix('\r').unwrap_or(raw);
        let fail=|s:&str| format!("line {}: {}",i+1,s);
        if raw.len()>250 || raw.bytes().any(|b| !(b==b'\t' || (32..=126).contains(&b))) {return Err(fail("invalid or overlong CUBE line"));}
        let line=raw.trim(); if line.is_empty() || line.starts_with('#') {continue;}
        let (key,rest)=line.split_once(|c:char| c==' ' || c=='\t').unwrap_or((line,""));
        let idx=match key {"TITLE"=>Some(0),"DOMAIN_MIN"=>Some(1),"DOMAIN_MAX"=>Some(2),"LUT_1D_SIZE"|"LUT_3D_SIZE"=>Some(3),_=>None};
        if let Some(k)=idx {
            if !c.rows.is_empty() || seen[k] {return Err(fail("duplicate/mixed/late header"));} seen[k]=true;
            match k {
                0=>{let t=rest.trim(); if t.len()<2 || !t.starts_with('"') || !t.ends_with('"') || t[1..t.len()-1].contains('"') {return Err(fail("TITLE requires a quoted string"));} c.title=t[1..t.len()-1].into();},
                1=>c.min=triple(rest).map_err(|e|fail(&e))?,
                2=>c.max=triple(rest).map_err(|e|fail(&e))?,
                _=>{let s=rest.trim(); if s.is_empty() || !s.bytes().all(|b|b.is_ascii_digit()){return Err(fail("size must be a positive integer"));}
                    c.size=s.parse().map_err(|_|fail("invalid size"))?;c.dimension=if key=="LUT_1D_SIZE"{1}else{3};
                    let max=if c.dimension==1{65536}else{65};
                    if c.size<2 || c.size>max{return Err(fail("supported size: 1D 2..65536; 3D 2..65"));}
                    expected=c.size.pow(c.dimension as u32);c.rows.reserve_exact(expected);
                }
            }
        } else {
            if !seen[3] {return Err(fail("data or unsupported directive before size"));}
            if c.rows.len()>=expected {return Err(fail("excess rows or unsupported directive"));}
            c.rows.push(triple(line).map_err(|e|fail(&e))?);
        }
    }
    if !seen[3] || c.rows.len()!=expected {return Err("missing size or incorrect table row count".into());}
    if (0..3).any(|k|c.min[k]>=c.max[k]) {return Err("DOMAIN_MAX must exceed DOMAIN_MIN per channel".into());}
    Ok(c)
}
impl Cube {
    pub fn sample(&self, rgb:[f64;3], amount:f64)->Result<[f64;3],String> {
        if !amount.is_finite() || !(0.0..=1.0).contains(&amount) || rgb.iter().any(|v|!v.is_finite()) {return Err("nonfinite pixel or invalid amount".into());}
        if amount==0. {return Ok(rgb);}
        let mut lo=[0;3];let mut hi=[0;3];let mut f=[0.;3];
        for k in 0..3 {let x=((rgb[k]-self.min[k])/(self.max[k]-self.min[k])).clamp(0.,1.)*(self.size-1) as f64;lo[k]=x.floor() as usize;hi[k]=(lo[k]+1).min(self.size-1);f[k]=x-lo[k] as f64;}
        let mut out=[0.;3];
        if self.dimension==1 {for k in 0..3 {out[k]=self.rows[lo[k]][k]*(1.-f[k])+self.rows[hi[k]][k]*f[k];}}
        else {for b in 0..2 {for g in 0..2 {for r in 0..2 {let bits=[r,g,b];let mut at=[0;3];let mut w=1.;for k in 0..3 {at[k]=if bits[k]==0{lo[k]}else{hi[k]};w*=if bits[k]==0{1.-f[k]}else{f[k]};}let row=self.rows[at[0]+self.size*(at[1]+self.size*at[2])];for k in 0..3 {out[k]+=w*row[k];}}}}}
        for k in 0..3 {out[k]=rgb[k]*(1.-amount)+out[k]*amount;if !out[k].is_finite(){return Err("nonfinite result".into());}}
        Ok(out)
    }
}
#[no_mangle]
pub extern "C" fn lrt_custom_lut_abi()->u32 {1}
unsafe fn error(dst:*mut u8,cap:usize,s:&str){if !dst.is_null() && cap>0 {let n=s.len().min(cap-1);std::ptr::copy_nonoverlapping(s.as_ptr(),dst,n);*dst.add(n)=0;}}
/// Caller owns bytes during call, and must free returned opaque handle exactly once.
#[no_mangle]
pub unsafe extern "C" fn lrt_custom_lut_parse(p:*const u8,len:usize,err:*mut u8,cap:usize)->*mut c_void {
    if p.is_null() || len>MAX_BYTES {error(err,cap,"invalid/bounded input");return std::ptr::null_mut();}
    match catch_unwind(||parse(slice::from_raw_parts(p,len))) {Ok(Ok(c))=>Box::into_raw(Box::new(c)).cast(),Ok(Err(e))=>{error(err,cap,&e);std::ptr::null_mut()},Err(_)=>{error(err,cap,"parser panic");std::ptr::null_mut()}}
}
#[no_mangle]
pub unsafe extern "C" fn lrt_custom_lut_free(p:*mut c_void){if !p.is_null(){drop(Box::from_raw(p as *mut Cube));}}
/// RGB float64 only, <=262144 pixels, output committed only after all pixels validate.
#[no_mangle]
pub unsafe extern "C" fn lrt_custom_lut_apply(p:*const c_void,src:*const f64,dst:*mut f64,pixels:usize,amount:f64)->i32 {
    if p.is_null() || src.is_null() || dst.is_null() || pixels>MAX_PIXELS{return 1;}
    match catch_unwind(AssertUnwindSafe(|| {
        let c=&*(p as *const Cube);let input=slice::from_raw_parts(src,pixels*3);let mut output=Vec::with_capacity(pixels*3);
        for v in input.chunks_exact(3){output.extend_from_slice(&c.sample([v[0],v[1],v[2]],amount)?);}
        std::ptr::copy_nonoverlapping(output.as_ptr(),dst,output.len());Ok::<_,String>(())
    })) {Ok(Ok(()))=>0,_=>2}
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn one_dimensional_domain_and_hdr(){let c=parse(b"TITLE \"a#b\"\nDOMAIN_MAX 2 2 2\nLUT_1D_SIZE 2\n-1 0 1\n3 4 5\n").unwrap();assert_eq!(c.sample([1.,1.,1.],1.).unwrap(),[1.,2.,3.]);assert_eq!(c.sample([-1.,3.,1.],0.).unwrap(),[-1.,3.,1.]);}
    #[test] fn axis_order(){let c=parse(include_bytes!("identity-2.cube")).unwrap();let x=[0.25,0.5,0.75];assert_eq!(c.sample(x,1.).unwrap(),x);}
    #[test] fn strict_rejection(){for s in ["LUT_1D_SIZE 2\n0 0 0\nTITLE \"late\"\n1 1 1", "LUT_1D_SIZE 2\n0 0 0\nNaN 1 1", "LUT_3D_SIZE 256", "LUT_1D_SIZE 2\nLUT_3D_SIZE 2", "LUT_1D_SIZE 2\nINPUT_MODE 1\n0 0 0\n1 1 1"] {assert!(parse(s.as_bytes()).is_err());}}
}
/// Output 8 doubles: dimension, size, three minima, three maxima.
#[no_mangle]
pub unsafe extern "C" fn lrt_custom_lut_metadata(p:*const c_void,out:*mut f64)->i32 {
    if p.is_null() || out.is_null(){return 1;}
    let c=&*(p as *const Cube);let data=[c.dimension as f64,c.size as f64,c.min[0],c.min[1],c.min[2],c.max[0],c.max[1],c.max[2]];
    std::ptr::copy_nonoverlapping(data.as_ptr(),out,8);0
}
