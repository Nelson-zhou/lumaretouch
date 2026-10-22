// SPDX-License-Identifier: GPL-3.0-or-later
mod wire;mod field;
use std::io::{self,Read,Write};
fn run()->Result<(),String>{
    let mut input=io::stdin().lock();let mut len=[0;4];input.read_exact(&mut len).map_err(|e|e.to_string())?;
    let len=u32::from_le_bytes(len) as usize;if len>1024*1024{return Err("liquify packet exceeds 1 MiB".into());}
    let mut bytes=vec![0;len];input.read_exact(&mut bytes).map_err(|e|e.to_string())?;
    let req=wire::decode(&bytes).map_err(str::to_owned)?;
    let pixels=field::replay(&req).map_err(str::to_owned)?;
    let mut out=io::BufWriter::new(io::stdout().lock());
    out.write_all(b"LQF1").map_err(|e|e.to_string())?;
    out.write_all(&((pixels.len()*12) as u64).to_le_bytes()).map_err(|e|e.to_string())?;
    for p in pixels {for v in [p.dx,p.dy,p.freeze]{out.write_all(&v.to_le_bytes()).map_err(|e|e.to_string())?;}}
    out.flush().map_err(|e|e.to_string())?;Ok(())
}
fn main(){if let Err(e)=run(){eprintln!("{e}");std::process::exit(2);}}
