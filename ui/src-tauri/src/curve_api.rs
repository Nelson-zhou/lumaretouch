//! Curve recipe boundary and Rust-derived previews, separate from transport.
use serde_json::{json,Value};
use crate::{point_curve,parametric_core};

fn keys(value:&Value,expected:&[&str])->Result<(),String>{
    let object=value.as_object().ok_or("curve recipe must be an object")?;
    if object.len()!=expected.len()||object.keys().any(|k|!expected.contains(&k.as_str())){
        return Err("curve recipe has missing/unknown fields".into());
    }Ok(())
}
pub(crate) fn parametric(value:&Value)->Result<parametric_core::Curve,String>{
    keys(value,&["version","algorithm","space","grid","boundary","enabled","shadows","darks","lights","highlights","splits"])?;
    if value["version"].as_u64()!=Some(1)||value["algorithm"]!=parametric_core::ALGORITHM
        ||value["space"]!="srgb-display"||value["grid"]!="split-aligned-4x16384"
        ||value["boundary"]!="identity-outside-unit"{return Err("unsupported parametric curve schema/domain".into());}
    let enabled=value["enabled"].as_bool().ok_or("parametric enabled must be boolean")?;
    let mut values=[0.;4];
    for (i,name) in ["shadows","darks","lights","highlights"].iter().enumerate(){values[i]=value[*name].as_f64().ok_or("invalid parametric value")?;}
    let parts=value["splits"].as_array().filter(|a|a.len()==3).ok_or("three parametric splits required")?;
    let mut splits=[0.;3];for i in 0..3{splits[i]=parts[i].as_f64().ok_or("invalid parametric split")?;}
    parametric_core::Curve::new(parametric_core::Spec{enabled,values,splits}).map_err(str::to_owned)
}
pub(crate) fn preview(spec:&Value)->Result<Value,String>{
    let version=spec["version"].as_u64().ok_or("invalid curve version")?;
    let mut expected=vec!["version","space","interpolation","boundary","enabled","master","red","green","blue"];
    if version>=2{expected.extend(["luminance","luminance_space"]);}
    if version==3{expected.push("parametric");}keys(spec,&expected)?;
    if ![1,2,3].contains(&version)||(version>=2&&spec["luminance_space"]!="linear-srgb-y-ratio")
        ||spec["space"]!="srgb-display"||spec["interpolation"]!="pchip"||spec["boundary"]!="linear"||!spec["enabled"].is_boolean(){
        return Err("unsupported curve schema/colour space".into());
    }
    let mut samples=serde_json::Map::new();let mut channels=vec!["master","red","green","blue"];
    if version>=2{channels.push("luminance");}
    for channel in channels{
        let rows=spec[channel].as_array().ok_or("curve points must be an array")?;
        if !(2..=point_curve::MAX_POINTS).contains(&rows.len()){return Err("curve point count out of range".into());}
        let mut points=Vec::with_capacity(rows.len());
        for row in rows{let pair=row.as_array().filter(|p|p.len()==2).ok_or("curve point needs x/y")?;
            points.push(point_curve::Point{x:pair[0].as_f64().ok_or("invalid curve x")?,y:pair[1].as_f64().ok_or("invalid curve y")?});}
        let compiled=point_curve::compile(&points).map_err(str::to_owned)?;
        samples.insert(channel.into(),json!((0..=256).map(|i|compiled.evaluate(i as f64/256.)).collect::<Vec<_>>()));
    }
    if version==3{
        let curve=parametric(&spec["parametric"])?;let [s,c,h]=curve.spec().splits;let bounds=[0.,s,c,h,1.];
        samples.insert("parametric".into(),json!((0..=256).map(|i|curve.sampled(i as f64/256.)).collect::<Vec<_>>()));
        samples.insert("parametric_handles".into(),json!((0..4).map(|i|{let x=(bounds[i]+bounds[i+1])*0.5;[x,curve.sampled(x)]}).collect::<Vec<_>>()));
    }
    Ok(Value::Object(samples))
}
pub(crate) fn drag(mut spec:Value,region:usize,target:f64)->Result<Value,String>{
    preview(&spec)?;
    if spec["version"]!=3||spec["enabled"]!=true||spec["parametric"]["enabled"]!=true{
        return Err("enable the parametric curve before dragging".into());
    }
    let curve=parametric(&spec["parametric"])?;let (value,actual)=curve.solve(region,target).map_err(str::to_owned)?;
    spec["parametric"][["shadows","darks","lights","highlights"][region]]=json!(value);
    Ok(json!({"spec":spec,"y":actual}))
}
#[tauri::command]
pub(crate) fn curve_parametric_drag(spec:Value,region:usize,target:f64)->Result<Value,String>{drag(spec,region,target)}

#[cfg(test)]
mod tests{
    use super::*;
    fn recipe()->Value{json!({"version":3,"space":"srgb-display","interpolation":"pchip","boundary":"linear","enabled":true,
        "master":[[0,0],[1,1]],"red":[[0,0],[1,1]],"green":[[0,0],[1,1]],"blue":[[0,0],[1,1]],
        "luminance_space":"linear-srgb-y-ratio","luminance":[[0,0],[1,1]],
        "parametric":{"version":1,"algorithm":parametric_core::ALGORITHM,"space":"srgb-display","grid":"split-aligned-4x16384","boundary":"identity-outside-unit",
        "enabled":true,"shadows":0,"darks":0,"lights":0,"highlights":0,"splits":[0.25,0.5,0.75]}})}
    #[test]fn v3_preview_preserves_point_channels_and_uses_core_for_parameters(){
        let mut spec=recipe();spec["parametric"]["shadows"]=json!(100);let result=preview(&spec).unwrap();
        assert_eq!(result["master"][128],0.5);assert_eq!(result["parametric"].as_array().unwrap().len(),257);
        let expected=parametric(&spec["parametric"]).unwrap().sampled(0.25);
        assert_eq!(result["parametric"][64],expected);assert_eq!(result["parametric_handles"].as_array().unwrap().len(),4);
    }
    #[test]fn strict_v3_schema_rejects_unknown_missing_and_invalid_parameters(){
        for (key,value) in [("algorithm",json!("other")),("grid",json!("uniform")),("shadows",json!(101)),("enabled",json!(1)),("splits",json!([0.2,0.2,0.8]))]{
            let mut spec=recipe();spec["parametric"][key]=value;assert!(preview(&spec).is_err());}
        let mut spec=recipe();spec["parametric"].as_object_mut().unwrap().remove("grid");assert!(preview(&spec).is_err());
        let mut spec=recipe();spec["parametric"]["lut"]=json!([]);assert!(preview(&spec).is_err());
    }
    #[test]fn drag_reuses_complete_recipe_and_only_changes_one_value(){
        let mut spec=recipe();spec["red"]=json!([[0,0.1],[1,0.9]]);let out=drag(spec.clone(),0,0.2).unwrap();
        assert_eq!(out["spec"]["red"],spec["red"]);assert_eq!(out["spec"]["parametric"]["lights"],0);
        assert!(out["spec"]["parametric"]["shadows"].as_f64().unwrap()>0.);
        assert!(drag(spec,4,0.5).is_err());
    }
}
