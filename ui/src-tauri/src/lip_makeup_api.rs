// SPDX-License-Identifier: GPL-3.0-or-later
//! Strict bounded recipe transport; no face, source image or recovery transfer.
use serde_json::{json,Value};
pub fn command(recipe:Value,document_id:String,control:String)->Result<Value,String>{
    if document_id.is_empty()||document_id.len()>128{return Err("唇妆照片身份无效".into());}
    let object=recipe.as_object().ok_or("唇妆配方必须是对象")?;
    if object.len()!=4||recipe["version"].as_u64()!=Some(1){return Err("唇妆配方版本或字段无效".into());}
    for key in ["saturation","brightness","dimensionality"] {
        let value=recipe[key].as_f64().ok_or("唇妆数值无效")?;
        if !value.is_finite()||!(-1.0..=1.0).contains(&value){return Err("唇妆数值超出范围".into());}
    }
    if !["all","saturation","brightness","dimensionality"].contains(&control.as_str()){return Err("唇妆控件无效".into());}
    Ok(json!({"cmd":"lip_makeup","recipe":recipe,"document_id":document_id,"control":control}))
}

#[tauri::command]
pub(crate) fn lip_makeup(state:tauri::State<'_,std::sync::Arc<crate::AppState>>,recipe:Value,document_id:String,control:String,people_context:Option<Value>)->Result<Value,String>{
    let mut request = command(recipe,document_id,control)?;
    crate::people_api::add_context(&mut request, people_context)?;
    state.send_to_engine(request)?;
    Ok(json!({"requested":true}))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn exact_recipe_and_control_whitelist() {
        let recipe=json!({"version":1,"saturation":0.2,"brightness":0,"dimensionality":0});
        assert!(command(recipe.clone(),"photo".into(),"saturation".into()).is_ok());
        assert!(command(recipe.clone(),"photo".into(),"lipstick_asset".into()).is_err());
        let mut wrong=recipe.clone(); wrong["brightness"]=json!(true);
        assert!(command(wrong,"photo".into(),"brightness".into()).is_err());
        let mut wrong=recipe; wrong["landmarks"]=json!([]);
        assert!(command(wrong,"photo".into(),"all".into()).is_err());
    }
}
