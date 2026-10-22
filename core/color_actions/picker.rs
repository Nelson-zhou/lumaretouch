//! Scalar targeted adjustments. Image sampling/provenance lives in the engine.
//! These are independently written consumers of the existing curve/levels math.
use crate::{curve::{self, Point}, levels};
pub const POLICY: &str = "stage-targeted-srgb-v1";
pub const CENTERS: [f64;8] = [0.,30.,60.,120.,180.,240.,280.,320.];
#[derive(Debug, Clone)]
pub struct Sample { pub rgb: [f64;3], pub hsl: [f64;3], pub hsv: [f64;3], pub weights: [f64;8] }
pub fn sample(rows: &[[f64;4]]) -> Result<Sample, String> {
    if rows.is_empty() || rows.len()>121 {return Err("pick requires 1–121 samples".into());}
    let mut rgb=[0.;3];
    for row in rows {
        if !row.iter().all(|v|v.is_finite()) || (row[3]-1.).abs()>1e-6 {return Err("sample crosses rotation padding or nonfinite input".into());}
        if row[..3].iter().any(|v|!(0.0..=1.0).contains(v)) {return Err("sample is outside the supported display-referred range".into());}
        for i in 0..3 {rgb[i]+=row[i];}
    }
    // Inputs are already range-checked; clamp only arithmetic roundoff in the mean.
    for value in &mut rgb {*value=(*value/rows.len() as f64).clamp(0.,1.);}
    let max=rgb.into_iter().fold(f64::NEG_INFINITY,f64::max);
    let min=rgb.into_iter().fold(f64::INFINITY,f64::min);let chroma=max-min;
    let hue=if chroma==0. {0.} else if max==rgb[0] {60.*((rgb[1]-rgb[2])/chroma).rem_euclid(6.)}
        else if max==rgb[1] {60.*((rgb[2]-rgb[0])/chroma+2.)} else {60.*((rgb[0]-rgb[1])/chroma+4.)};
    let saturation=if max>0. {chroma/max} else {0.};let lightness=(max+min)/2.;
    let hsl_sat=if chroma==0. {0.} else {let denominator=if max+min<=1. {max+min}else{(1.-max)+(1.-min)};(chroma/denominator).clamp(0.,1.)};
    let weights=CENTERS.map(|center|{let d=(hue-center).abs();let d=d.min(360.-d);let t=(1.-d/45.).clamp(0.,1.);t*t*(3.-2.*t)*(saturation/0.06).clamp(0.,1.)});
    Ok(Sample{rgb,hsl:[hue,hsl_sat,lightness],hsv:[hue,saturation,max],weights})
}
pub fn levels_pick(sample:&Sample, channels:[[f64;5];4], white:bool)->Result<[[f64;5];4],String>{
    let mut next=channels;
    for row in channels {levels::Channel::new(row).map_err(str::to_owned)?;}
    let master=levels::Channel::new(channels[0]).map_err(str::to_owned)?;
    for i in 0..3 {
        // The master precedes individual channels in the existing renderer.
        next[i+1][if white {1} else {0}]=master.apply(sample.rgb[i]);
        levels::Channel::new(next[i+1]).map_err(|_|"sample crosses the opposite input endpoint; move that endpoint first".to_owned())?;
    }
    Ok(next)
}
pub fn curve_pick(points:&[Point], x:f64, delta:f64)->Result<(Vec<Point>,usize,f64),String>{
    let compiled=curve::compile(points).map_err(str::to_owned)?;
    if !x.is_finite() || !(0.0..=1.0).contains(&x) || !delta.is_finite() || !(-1.0..=1.0).contains(&delta){return Err("invalid targeted curve coordinate or delta".into());}
    let mut next=points.to_vec();
    let nearby=points.iter().enumerate().filter(|(_,p)|(p.x-x).abs()<curve::MIN_SPACING*2.)
        .min_by(|(_,a),(_,b)|(a.x-x).abs().total_cmp(&(b.x-x).abs())).map(|(i,_)|i);
    let index=if let Some(i)=nearby {i} else {
        if next.len()>=curve::MAX_POINTS {return Err("curve already has 64 points; remove a point before sampling".into());}
        let index=next.partition_point(|p|p.x<x);next.insert(index,Point{x,y:compiled.evaluate(x)});index
    };
    let old=next[index].y;next[index].y=(old+delta).clamp(0.,1.);
    curve::compile(&next).map_err(str::to_owned)?;
    let achieved=next[index].y-old;Ok((next,index,achieved))
}
pub fn hsl_pick(sample:&Sample,bands:[f64;24],delta:f64)->Result<([f64;24],f64),String>{
    if !delta.is_finite() || !(-60.0..=60.0).contains(&delta) {return Err("hue drag must be within ±60 degrees".into());}
    for (i,value) in bands.iter().enumerate(){let limit=if i%3==0 {60.} else {100.};if !value.is_finite()||value.abs()>limit{return Err("invalid existing HSL band".into());}}
    // A neutral click still reports HSL; only an actual hue change needs chroma.
    if delta==0. {return Ok((bands,0.));}
    if sample.hsv[1]<0.06 {return Err("sample is too neutral to select a stable hue".into());}
    let norm=sample.weights.iter().map(|w|w*w).sum::<f64>();if norm<1e-8{return Err("sample has no editable hue band".into());}
    // Minimum-norm change in the existing overlapping, unnormalized band basis.
    // A common scale stops at the first existing band limit, never clips each
    // band independently or changes saturation/value behind the user's back.
    let change=sample.weights.map(|w|delta*w/norm);let mut scale:f64=1.;
    for i in 0..8 {let d=change[i];if d>0. {scale=scale.min((60.-bands[i*3])/d);}else if d<0. {scale=scale.min((-60.-bands[i*3])/d);}}
    let mut next=bands;for i in 0..8 {next[i*3]=(bands[i*3]+scale*change[i]).clamp(-60.,60.);}
    let effective=|v:[f64;24]|sample.weights.iter().enumerate().map(|(i,w)|w*v[i*3]).sum::<f64>().clamp(-60.,60.);
    Ok((next,effective(next)-effective(bands)))
}
fn number(tokens:&mut std::str::SplitWhitespace<'_>)->Result<f64,String>{let value=tokens.next().ok_or("missing scalar")?.parse::<f64>().map_err(|_|"invalid scalar")?;if !value.is_finite(){return Err("nonfinite scalar".into());}Ok(value)}
fn vector(values:&[f64])->String {format!("[{}]",values.iter().map(|v|format!("{v:e}")).collect::<Vec<_>>().join(","))}
pub fn handle(tokens:&mut std::str::SplitWhitespace<'_>)->Result<String,String>{
    let action=tokens.next().ok_or("missing picker action")?;let channel=tokens.next().ok_or("missing picker channel")?;
    if !["levels_black","levels_white","curve","hsl"].contains(&action)||!["master","red","green","blue","luminance"].contains(&channel)||(action!="curve"&&channel!="master"){return Err("unsupported picker action/channel".into());}
    let delta=number(tokens)?;
    let count=tokens.next().ok_or("missing sample count")?.parse::<usize>().map_err(|_|"invalid sample count")?;
    if !(1..=121).contains(&count){return Err("invalid sample count".into());}
    let mut rows=Vec::with_capacity(count);for _ in 0..count {rows.push([number(tokens)?,number(tokens)?,number(tokens)?,number(tokens)?]);}
    let sample=sample(&rows)?;
    let details=match action {
        "levels_black"|"levels_white"=>{
            if delta!=0. {return Err("levels picker does not accept a drag delta".into());}
            let mut channels=[[0.;5];4];for row in &mut channels {for value in row {*value=number(tokens)?;}}
            let next=levels_pick(&sample,channels,action=="levels_white")?;
            format!("\"levels\":[{}]",next.iter().map(|r|vector(r)).collect::<Vec<_>>().join(","))
        },
        "curve"=>{
            let count=tokens.next().ok_or("missing curve count")?.parse::<usize>().map_err(|_|"invalid curve count")?;
            if !(2..=64).contains(&count){return Err("invalid curve count".into());}
            let mut points=Vec::with_capacity(count);for _ in 0..count {points.push(Point{x:number(tokens)?,y:number(tokens)?});}
            let x=match channel {"red"=>sample.rgb[0],"green"=>sample.rgb[1],"blue"=>sample.rgb[2],"luminance"=>sample.rgb.iter().zip(curve::Y_WEIGHTS).map(|(c,w)|curve::srgb_decode(*c)*w).sum(),_=>sample.rgb.into_iter().fold(f64::NEG_INFINITY,f64::max)};
            let (next,index,achieved)=curve_pick(&points,x,delta)?;
            format!("\"points\":[{}],\"point_index\":{index},\"sample_x\":{x:e},\"achieved_delta\":{achieved:e}",next.iter().map(|p|vector(&[p.x,p.y])).collect::<Vec<_>>().join(","))
        },
        _=>{let mut bands=[0.;24];for value in &mut bands {*value=number(tokens)?;}let (next,achieved)=hsl_pick(&sample,bands,delta)?;
            format!("\"bands\":{},\"weights\":{},\"achieved_delta\":{achieved:e}",vector(&next),vector(&sample.weights))},
    };
    if tokens.next().is_some(){return Err("unexpected trailing picker input".into());}
    Ok(format!("{{\"version\":1,\"policy\":\"{POLICY}\",\"action\":\"{action}\",\"channel\":\"{channel}\",\"samples\":{count},\"mean_srgb\":{},\"hsl\":{},{details}}}",vector(&sample.rgb),vector(&sample.hsl)))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn neutral_has_no_hue_action(){let s=sample(&[[0.5,0.5,0.5,1.]]).unwrap();assert!(hsl_pick(&s,[0.;24],10.).is_err());}
    #[test] fn padding_and_hdr_are_rejected(){assert!(sample(&[[0.4,0.2,0.1,0.9]]).is_err());assert!(sample(&[[1.1,0.,0.,1.]]).is_err());}
    #[test] fn curve_preserves_other_points_and_uses_existing_y(){let p=[Point{x:0.,y:0.2},Point{x:1.,y:0.8}];let (next,i,d)=curve_pick(&p,0.5,0.1).unwrap();assert_eq!(i,1);assert!((next[i].y-0.6).abs()<1e-12);assert!((d-0.1).abs()<1e-12);assert_eq!(next[0],p[0]);}
    #[test] fn hue_uses_overlapping_weights_and_leaves_sat_value(){let s=sample(&[[1.,0.25,0.,1.]]).unwrap();let (next,achieved)=hsl_pick(&s,[0.;24],12.).unwrap();assert!((achieved-12.).abs()<1e-12);assert!(next[0]>0.&&next[3]>0.);for i in 0..8 {assert_eq!(next[i*3+1],0.);assert_eq!(next[i*3+2],0.);}}
}
