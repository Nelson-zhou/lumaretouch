//! Repository-owned bounded histogram worker. No model, network or GUI dependencies.
mod scopes;
mod wire;
use std::io::{self,Read};
use scopes::{Histogram,Scopes};
fn histogram(value:&Histogram)->String {
    format!("{{\"bins\":[{}],\"underflow\":{},\"overflow\":{}}}",
        value.bins.iter().map(u64::to_string).collect::<Vec<_>>().join(","),value.underflow,value.overflow)
}
fn triplet(value:Option<[f64;3]>)->String {
    value.map(|v|format!("[{},{},{}]",v[0],v[1],v[2])).unwrap_or_else(||"null".into())
}
fn output(value:Scopes)->String {
    let mean=value.mean_rgb();
    format!("{{\"version\":1,\"bins\":256,\"samples\":{},\"finite_samples\":{},\"nonfinite_samples\":{},\"rgb\":[{},{},{}],\"linear_y\":{},\"mean_srgb\":{},\"mean_lab_d65\":{}}}",
        value.samples,value.finite_samples,value.nonfinite_samples,
        histogram(&value.rgb[0]),histogram(&value.rgb[1]),histogram(&value.rgb[2]),
        histogram(&value.linear_y),triplet(mean),triplet(mean.map(scopes::srgb_to_lab_d65)))
}
fn run()->Result<(),String> {
    let mut bytes=Vec::new();
    io::stdin().take((wire::MAX_BYTES+1) as u64).read_to_end(&mut bytes).map_err(|e|e.to_string())?;
    if bytes.len()>wire::MAX_BYTES {return Err("colour-scope request exceeds budget".into());}
    let result=wire::decode(&bytes).map_err(str::to_owned)?;
    println!("{}",output(result)); Ok(())
}
fn main(){if let Err(error)=run(){eprintln!("{error}");std::process::exit(2);}}
