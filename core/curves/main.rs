//! Headless adapter for recipe restore/batch processing: no GUI or Python compiler.
mod curve;
#[path="../levels/levels.rs"]
mod levels;
use std::io::{self, Read};
fn main() {
    if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}
}
fn run()->Result<(),String>{
    let mut input=String::new();
    io::stdin().take(16385).read_to_string(&mut input).map_err(|e|e.to_string())?;
    if input.len()>16384 {return Err("curve request exceeds 16 KiB".into());}
    let mut tokens=input.split_whitespace();
    let first=tokens.next().ok_or("missing point count")?;
    if first=="levels" {return levels_reference(&mut tokens);}
    let luminance=first=="luminance";
    let count=if luminance {tokens.next().ok_or("missing point count")?} else {first};
    let n:usize=count.parse().map_err(|_|"invalid point count")?;
    if !(2..=curve::MAX_POINTS).contains(&n) {return Err("invalid point count".into());}
    let mut points=Vec::with_capacity(n);
    for _ in 0..n {
        let x:f64=tokens.next().ok_or("missing x")?.parse().map_err(|_|"invalid x")?;
        let y:f64=tokens.next().ok_or("missing y")?.parse().map_err(|_|"invalid y")?;
        points.push(curve::Point{x,y});
    }
    let c=curve::compile(&points).map_err(str::to_owned)?;
    if luminance {
        let mut rows=Vec::new();
        while let Some(first)=tokens.next() {
            if rows.len()>=64 {return Err("reference vector exceeds 64 pixels".into());}
            let mut rgb=[0.;3];rgb[0]=first.parse::<f64>().map_err(|_|"invalid R")?;
            for channel in &mut rgb[1..] {*channel=tokens.next().ok_or("missing RGB channel")?.parse::<f64>().map_err(|_|"invalid channel")?;}
            if !rgb.iter().all(|x|x.is_finite()) {return Err("nonfinite RGB".into());}
            let out=curve::apply_luminance(rgb,&c);
            if !out.iter().all(|x|x.is_finite()) {return Err("reference result overflow".into());}
            rows.push(format!("[{},{},{}]",out[0],out[1],out[2]));
        }
        println!("[{}]",rows.join(","));return Ok(());
    }
    if tokens.next().is_some(){return Err("unexpected trailing input".into());}
    let segments=c.segments.iter().map(|s|format!("[{}, {}, {}, {}, {}, {}]",s.x,s.width,
        s.coefficients[0],s.coefficients[1],s.coefficients[2],s.coefficients[3])).collect::<Vec<_>>().join(",");
    println!("{{\"version\":1,\"identity\":{},\"lower\":[{},{}],\"upper\":[{},{}],\"segments\":[{}]}}",
        c.identity,c.lower[0],c.lower[1],c.upper[0],c.upper[1],segments);
    Ok(())
}

fn levels_reference(tokens:&mut std::str::SplitWhitespace<'_>)->Result<(),String>{
    let enabled=match tokens.next(){Some("1")=>true,Some("0")=>false,_=>return Err("levels enabled must be 0/1".into())};
    let neutral=levels::Channel::new([0.,1.,1.,0.,1.]).unwrap();
    let mut channels=[neutral;4];
    for channel in &mut channels {
        let mut values=[0.;5];
        for value in &mut values {*value=tokens.next().ok_or("missing levels parameter")?.parse::<f64>().map_err(|_|"invalid levels parameter")?;}
        *channel=levels::Channel::new(values).map_err(str::to_owned)?;
    }
    let mut rows=Vec::new();
    while let Some(first)=tokens.next(){
        if rows.len()>=64 {return Err("reference vector exceeds 64 pixels".into());}
        let mut rgb=[0.;3];rgb[0]=first.parse::<f64>().map_err(|_|"invalid R")?;
        for value in &mut rgb[1..] {*value=tokens.next().ok_or("missing RGB channel")?.parse::<f64>().map_err(|_|"invalid channel")?;}
        if !rgb.iter().all(|v|v.is_finite()){return Err("nonfinite RGB".into());}
        let out=levels::apply_rgb(rgb,&channels,enabled);
        rows.push(format!("[{},{},{}]",out[0],out[1],out[2]));
    }
    println!("[{}]",rows.join(","));Ok(())
}
