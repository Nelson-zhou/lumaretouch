//! Headless adapter for recipe restore/batch processing: no GUI or Python compiler.
mod curve;
use std::io::{self, Read};
fn main() {
    if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}
}
fn run()->Result<(),String>{
    let mut input=String::new();
    io::stdin().take(16385).read_to_string(&mut input).map_err(|e|e.to_string())?;
    if input.len()>16384 {return Err("curve request exceeds 16 KiB".into());}
    let mut tokens=input.split_whitespace();
    let n:usize=tokens.next().ok_or("missing point count")?.parse().map_err(|_|"invalid point count")?;
    if !(2..=curve::MAX_POINTS).contains(&n) {return Err("invalid point count".into());}
    let mut points=Vec::with_capacity(n);
    for _ in 0..n {
        let x:f64=tokens.next().ok_or("missing x")?.parse().map_err(|_|"invalid x")?;
        let y:f64=tokens.next().ok_or("missing y")?.parse().map_err(|_|"invalid y")?;
        points.push(curve::Point{x,y});
    }
    if tokens.next().is_some(){return Err("unexpected trailing input".into());}
    let c=curve::compile(&points).map_err(str::to_owned)?;
    let segments=c.segments.iter().map(|s|format!("[{}, {}, {}, {}, {}, {}]",s.x,s.width,
        s.coefficients[0],s.coefficients[1],s.coefficients[2],s.coefficients[3])).collect::<Vec<_>>().join(",");
    println!("{{\"version\":1,\"identity\":{},\"lower\":[{},{}],\"upper\":[{},{}],\"segments\":[{}]}}",
        c.identity,c.lower[0],c.lower[1],c.upper[0],c.upper[1],segments);
    Ok(())
}
