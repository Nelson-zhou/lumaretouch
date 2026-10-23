//! Correlated retained receipts bound to an engine epoch. Unknown never resends edits.
use std::{collections::HashMap,sync::{Arc,Mutex,OnceLock}};
use serde_json::{Value,json};
use tauri::State;
use crate::AppState;
struct Row {epoch:[u8;16],request:Value,result:Option<Value>}
fn mailbox()->&'static Mutex<HashMap<String,Row>> {static BOX:OnceLock<Mutex<HashMap<String,Row>>>=OnceLock::new();BOX.get_or_init(||Mutex::new(HashMap::new()))}
pub(crate) fn receive(epoch:[u8;16],value:&Value){
    let Some(id)=value["request_id"].as_str() else{return};
    if let Ok(mut m)=mailbox().lock(){if let Some(row)=m.get_mut(id){if row.epoch==epoch&&row.result.is_none(){let mut v=value.clone();if let Some(o)=v.as_object_mut(){o.remove("doc_state");}if v.to_string().len()<=32768{row.result=Some(v);}}}}
}
#[tauri::command]
pub(crate) fn colour_editor_request(state:State<'_,Arc<AppState>>,request:Value)->Result<Value,String>{
    if request.to_string().len()>8192{return Err("色彩编辑器请求超过 8 KiB".into());}
    let id=request["request_id"].as_str().filter(|x|!x.is_empty()&&x.len()<=128).ok_or("缺少色彩编辑器请求身份")?.to_owned();
    let cmd=request["cmd"].as_str().ok_or("缺少色彩编辑器命令")?;
    if !matches!(cmd,"colour_editor"|"colour_editor_state"|"colour_editor_sample"){return Err("未知色彩编辑器命令".into());}
    if cmd=="colour_editor_sample" {
        let handle=state.engine.lock().map_err(|_|"engine lock")?.clone().ok_or("engine offline")?;
        let capture=state.color_picker_capture.lock().map_err(|_|"capture lock")?;
        let cid=request["capture_id"].as_str().ok_or("missing capture ID")?;
        let ticket=request["ticket"].as_str().ok_or("missing capture ticket")?;
        let proof=capture.eligible_proof(handle.epoch(),cid,ticket)?;
        if proof.descriptor["picker_action"]!="colour_editor"||proof.descriptor["source_stage"]!="colour-editor-input" {return Err("not a colour editor input capture".into());}
        for (key,value) in [("document_id",proof.identity.document.to_string()),("generation",proof.identity.generation.to_string()),("recipe_document_id",proof.recipe_document_id.clone()),("recipe_revision",proof.recipe_revision.clone())] {
            if request[key].as_str()!=Some(value.as_str()){return Err("colour editor proof changed".into());}
        }
        let region:crate::color_picker_capture_api::Region=serde_json::from_value(request["region"].clone()).map_err(|_|"invalid editor sample region")?;
        region.validate()?;
        if u64::from(region.x)+u64::from(region.width)>u64::from(proof.identity.width)||u64::from(region.y)+u64::from(region.height)>u64::from(proof.identity.height){return Err("sample outside presented input".into());}
    }
    let edit=cmd=="colour_editor" && request["action"]=="commit";
    let guard=state.engine.lock().map_err(|_|"引擎锁错误")?;let handle=guard.as_ref().ok_or("引擎未启动")?;let epoch=handle.epoch();
    {let mut m=mailbox().lock().map_err(|_|"色彩编辑器回执锁错误")?;
      if let Some(old)=m.get(&id){if old.epoch==epoch&&old.request==request{return Ok(json!({"requested":true,"request_id":id,"replayed":true}));}return Err("请求身份重复，未发送".into());}
      if edit {
        let preview_id=request["preview_id"].as_str().ok_or("missing preview identity")?;
        let preview=m.get(preview_id).ok_or("preview receipt expired")?;
        let shown=preview.result.as_ref().ok_or("preview not ready")?;
        if preview.epoch!=epoch||preview.request["document_id"]!=request["document_id"]||preview.request["revision"]!=request["revision"]||shown["event"]!="colour_editor_preview" {return Err("preview identity changed".into());}
        let seq=shown["frame"]["seq"].as_u64().ok_or("preview sequence missing")?;
        let slot=shown["frame"]["slot"].as_u64().ok_or("preview slot missing")? as usize;
        let f=state.frames.lock().map_err(|_|"frame lock")?;
        let read=f.shm.as_ref().ok_or("shm unavailable")?.read()?;
        let (meta,current_slot)=read.freshest()?.ok_or("preview frame unavailable")?;
        let presented=f.pending.iter().any(|p|p.seq==seq&&p.t_present.is_some())||f.samples.iter().rev().take(16).any(|p|p.seq==seq&&p.emit_to_present_us.is_some());
        if meta.seq!=seq||current_slot!=slot||!presented{return Err("exact preview not presented or already replaced".into());}
      }
      // Retain commits for reconciliation; preview/readback results are consumable.
      m.retain(|_,row|row.result.is_none()||row.request["action"]=="commit");
      if m.len()>=512{return Err("色彩编辑器回执容量已满；请保存并重启应用".into());}
      m.insert(id.clone(),Row{epoch,request:request.clone(),result:None});}
    drop(guard);
    let sent=if edit {state.send_to_engine(request)}else{let g=state.engine.lock().map_err(|_|"引擎锁错误")?;g.as_ref().ok_or("引擎未启动")?.send(request)};
    if let Err(error)=sent{return Err(format!("发送状态未确认：{}；请查询原操作，勿自动重发",error));}
    Ok(json!({"requested":true,"request_id":id}))
}
#[tauri::command]
pub(crate) fn colour_editor_status(state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String>{
    if request_id.len()>128{return Err("无效色彩编辑器身份".into());}
    let guard=state.engine.lock().map_err(|_|"引擎锁错误")?;let epoch=guard.as_ref().map(|h|h.epoch());
    let mut m=mailbox().lock().map_err(|_|"色彩编辑器回执锁错误")?;
    let Some(row)=m.get(&request_id) else{return Ok(json!({"request_id":request_id,"phase":"unknown","result":null}));};
    if epoch!=Some(row.epoch){return Ok(json!({"request_id":request_id,"phase":"unknown","result":null,"reason":"engine-restarted; explicit-readback-required"}));}
    let result=json!({"request_id":request_id,"phase":if row.result.is_some(){"done"}else{"pending"},"result":row.result});
    let consume=row.request["cmd"]=="colour_editor_state" && row.result.is_some();
    if consume {m.remove(&request_id);}
    Ok(result)
}

/// Confirms the exact correlated frame was copied and compositor-presented,
/// and that its shared-memory slot still denotes the same freshest sequence.
#[tauri::command]
pub(crate) fn colour_editor_frame_status(state:State<'_,Arc<AppState>>,request_id:String,seq:u64,slot:usize)->Result<bool,String>{
    let engine=state.engine.lock().map_err(|_|"engine lock")?;
    let epoch=engine.as_ref().ok_or("engine offline")?.epoch();
    let m=mailbox().lock().map_err(|_|"receipt lock")?;
    let row=m.get(&request_id).ok_or("preview receipt expired")?;
    let r=row.result.as_ref().ok_or("preview not returned")?;
    if row.epoch!=epoch||r["frame"]["seq"].as_u64()!=Some(seq)||r["frame"]["slot"].as_u64()!=Some(slot as u64){return Err("frame receipt mismatch".into());}
    let report=state.doc_report.lock().map_err(|_|"document lock")?;
    if report.as_ref().and_then(|v|v["doc_state"]["document_id"].as_str())!=row.request["document_id"].as_str(){return Err("document changed".into());}
    let f=state.frames.lock().map_err(|_|"frame lock")?;
    let shm=f.shm.as_ref().ok_or("shm unavailable")?;
    let read=shm.read()?;
    let (meta,current_slot)=read.freshest()?.ok_or("frame unavailable")?;
    if meta.seq!=seq||current_slot!=slot{return Err("frame replaced before presentation confirmation".into());}
    Ok(f.pending.iter().any(|p|p.seq==seq&&p.t_present.is_some())||f.samples.iter().rev().take(16).any(|p|p.seq==seq&&p.emit_to_present_us.is_some()))
}

#[tauri::command]
pub(crate) fn colour_editor_abort(state:State<'_,Arc<AppState>>,request_id:String)->Result<(),String>{
    if request_id.is_empty()||request_id.len()>128{return Err("invalid grading request identity".into());}
    let g=state.engine.lock().map_err(|_|"engine lock")?;
    g.as_ref().ok_or("engine offline")?.send(json!({"cmd":"colour_editor_abort","request_id":request_id}))
}
