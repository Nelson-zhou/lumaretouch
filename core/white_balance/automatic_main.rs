//! Separate fixed binary ABI. Does not widen curve-compiler's 16 KiB contract.
mod white_balance;
mod automatic;
use std::io::{self,Read};
const MAGIC: &[u8;8]=b"LRTAWB01";
const BYTES:usize=40+automatic::SAMPLES*40;
fn main() {if let Err(error)=run(){eprintln!("{error}");std::process::exit(2);}}
fn run()->Result<(),String>{
    let args:Vec<String>=std::env::args().skip(1).collect();
    if args.len()==1 && args[0]=="--protocol" {println!("white-balance-auto-v1:{}",automatic::POLICY);return Ok(());}
    if !args.is_empty(){return Err("unexpected auto-WB arguments".into());}
    let mut bytes=Vec::with_capacity(BYTES+1);
    io::stdin().take((BYTES+1) as u64).read_to_end(&mut bytes).map_err(|e|e.to_string())?;
    if bytes.len()!=BYTES || &bytes[..8]!=MAGIC {return Err("invalid fixed auto-WB message".into());}
    let count=u32::from_le_bytes(bytes[8..12].try_into().unwrap());
    if count!=automatic::SAMPLES as u32 || bytes[12..16]!=[0;4] {return Err("unsupported auto-WB count/flags".into());}
    let number=|offset:usize|f64::from_le_bytes(bytes[offset..offset+8].try_into().unwrap());
    let manual=[number(16),number(24),number(32)];
    let rows:Vec<automatic::Sample>=(0..automatic::SAMPLES).map(|i| {
        let p=40+i*40;automatic::Sample {rgb:[number(p),number(p+8),number(p+16)],coverage:number(p+24),risk:number(p+32)}
    }).collect();
    let r=automatic::estimate(&rows,manual).map_err(|e|format!("auto white balance rejected: {e:?}"))?;
    println!("{{\"version\":1,\"policy\":\"{}\",\"samples\":{},\"accepted\":{},\"stable_tiles\":{},\"spread\":{:e},\"illuminant\":[{:e},{:e},{:e}],\"gains\":[{:e},{:e},{:e}]}}",automatic::POLICY,automatic::SAMPLES,r.accepted,r.stable_tiles,r.spread,r.illuminant[0],r.illuminant[1],r.illuminant[2],r.gains[0],r.gains[1],r.gains[2]);
    Ok(())
}
