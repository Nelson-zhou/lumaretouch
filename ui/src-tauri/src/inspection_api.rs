//! Internal native API. The Viewer does not consume these patches yet.
use std::io::Read;
use std::path::PathBuf;
use std::sync::Arc;
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,inspection_host as host};
use host::{Action,wire::refinement::{Roi,Ticket}};

pub fn fresh_epoch()->Result<[u8;16],String>{
    let mut out=[0u8;16];std::fs::File::open("/dev/urandom").and_then(|mut f|f.read_exact(&mut out)).map_err(|e|e.to_string())?;
    if out==[0;16]{return Err("inspection entropy unavailable".into());}Ok(out)
}
fn hex(epoch:[u8;16])->String{epoch.iter().map(|b|format!("{b:02x}")).collect()}
fn number(text:&str)->Result<u64,String>{
    let n=text.parse::<u64>().map_err(|_|"invalid inspection identity")?;
    if n.to_string()!=text{return Err("noncanonical inspection identity".into());}Ok(n)
}
fn epoch(text:&str)->Result<[u8;16],String>{
    if text.len()!=32 || !text.bytes().all(|b|b.is_ascii_digit() || (b'a'..=b'f').contains(&b)){
        return Err("invalid inspection epoch".into());
    }
    let mut out=[0;16];for (i,pair) in text.as_bytes().chunks_exact(2).enumerate(){
        out[i]=u8::from_str_radix(std::str::from_utf8(pair).unwrap(),16).map_err(|_|"invalid epoch")?;
    }if out==[0;16]{return Err("empty inspection epoch".into());}Ok(out)
}
fn ticket(value:&Value)->Result<Ticket,String>{
    let parts=value.as_array().ok_or("missing inspection ticket")?;
    if parts.len()!=5{return Err("invalid inspection ticket length".into());}
    let mut n=[0;5];for (i,v) in parts.iter().enumerate(){n[i]=number(v.as_str().ok_or("inspection identities must be strings")?)?;}
    Ok(Ticket{id:n[0],document:n[1],source_generation:n[2],recipe:n[3],viewport:n[4]})
}
fn command(action:&Action,epoch:[u8;16])->Value{
    match action{
        Action::Start(r)=>json!({"cmd":"inspection_snapshot","action":"start","request_id":r.ticket.id.to_string(),
            "max_asset_bytes":host::ASSET_BYTES,"render":{"epoch":hex(epoch),
            "ticket":[r.ticket.id.to_string(),r.ticket.document.to_string(),r.ticket.source_generation.to_string(),r.ticket.recipe.to_string(),r.ticket.viewport.to_string()],
            "source_size":[r.source_width,r.source_height],"canvas_size":[r.canvas_width,r.canvas_height],
            "roi":[r.roi.x,r.roi.y,r.roi.width,r.roi.height],"max_source_pixels":host::SOURCE_PIXELS,
            "max_display_pixels":host::PATCH_PIXELS,"max_address_bytes":host::ADDRESS_BYTES,"timeout_seconds":120}}),
        Action::Cancel(id)=>json!({"cmd":"inspection_snapshot","action":"cancel","request_id":id.to_string()}),
        Action::Release(id)=>json!({"cmd":"inspection_snapshot","action":"release","request_id":id.to_string()}),
    }
}
impl AppState{
    fn dispatch_inspection_locked(&self,h:&mut host::Host,epoch:[u8;16],actions:Vec<Action>)->Result<(),String>{
        let engine=self.engine.lock().map_err(|_|"engine lock poisoned")?;
        for action in actions{
            // Same lock order as ordinary editing: inspection then Engine handle.
            // Hold through enqueue so an engine reset cannot relabel an old action.
            if h.epoch!=epoch{return Err("inspection engine changed before dispatch".into());}
            let result=engine.as_ref()
                .ok_or_else(||"engine unavailable".to_string()).and_then(|e|e.send(command(&action,epoch)));
            if let Err(reason)=result{h.send_failed(&action,reason.clone());return Err(reason);}
        }Ok(())
    }
    pub fn on_inspection_event(&self,engine_epoch:[u8;16],v:&Value){
        let result=(||->Result<(),String>{
            let e=epoch(v["epoch"].as_str().ok_or("inspection event lacks epoch")?)?;
            if e!=engine_epoch{return Ok(());}
            let t=ticket(&v["ticket"])?;
            if v["request_id"].as_str()!=Some(t.id.to_string().as_str()){
                return Err("inspection event request identity mismatch".into());
            }
            let path=v["result_path"].as_str().map(PathBuf::from);
            let mut h=self.inspection.lock().map_err(|_|"inspection lock poisoned")?;
            let actions=h.event(e,t,
                v["state"].as_str().ok_or("inspection event lacks state")?,path,
                v["error"].as_str().map(str::to_owned))?;
            self.dispatch_inspection_locked(&mut h,e,actions)
        })();
        if let Err(e)=result{
            self.push_log(e.clone());
            if let Ok(mut h)=self.inspection.lock(){
                if h.epoch==engine_epoch{
                    let actions=h.protocol_failure(e);
                    let _=self.dispatch_inspection_locked(&mut h,engine_epoch,actions);
                }
            }
        }
    }
    pub fn on_inspection_engine_end(&self,epoch:[u8;16]){
        self.inspection.lock().unwrap().engine_ended(epoch);
    }
}

#[tauri::command]
pub fn inspection_start(state:State<'_,Arc<AppState>>,engine_epoch:String,generation:String,canvas_width:u32,canvas_height:u32,
                        x:u32,y:u32,width:u32,height:u32)->Result<Value,String>{
    // Canvas is a requested layout, not trusted geometry. The shared full-source
    // worker independently verifies it against the captured crop/rotation recipe.
    let (epoch,ticket)={let mut h=state.inspection.lock().map_err(|_|"inspection lock poisoned")?;
        if h.epoch!=epoch(&engine_epoch)? || h.generation()!=number(&generation)?{return Err("inspection source generation changed".into());}
        let guard=state.engine.lock().map_err(|_|"engine lock poisoned")?;
        let stats=guard.as_ref().ok_or("engine unavailable")?.queue_stats();
        if stats["pending"].as_u64()!=Some(0) || stats["in_flight"].as_bool()!=Some(false) || stats["closed"].as_bool()!=Some(false){
            return Err("wait for queued edits before requesting full-source inspection".into());
        }
        let image=state.image.lock().map_err(|_|"image lock poisoned")?.clone().ok_or("no loaded source")?;
        let source=(image["src_w"].as_u64().ok_or("source width unavailable")?,image["src_h"].as_u64().ok_or("source height unavailable")?);
        let report=state.doc_report.lock().map_err(|_|"document lock poisoned")?.clone().ok_or("document geometry unavailable")?;
        let crop=&report["doc_state"]["crop"];
        let full=crop["out_full"].as_array().and_then(|v|if v.len()==2{Some((v[0].as_u64()?,v[1].as_u64()?))}else{None})
            .or_else(||if crop["neutral"].as_bool()==Some(true){Some(source)}else{None})
            .ok_or("full-resolution canvas geometry unavailable")?;
        if full!=(canvas_width as u64,canvas_height as u64){return Err("inspection canvas metadata changed".into());}
        drop(guard);
        let (ticket,actions)=h.submit(source,full,
            Roi{x:x as u64,y:y as u64,width:width as u64,height:height as u64})?;
        let e=h.epoch;state.dispatch_inspection_locked(&mut h,e,actions)?;
        (e,ticket)};
    Ok(json!({"request_id":ticket.id.to_string(),"epoch":hex(epoch),"accepted":true,
        "expectation":{"epoch":hex(epoch),"ticket":{"id":ticket.id.to_string(),"document":ticket.document.to_string(),
            "sourceGeneration":ticket.source_generation.to_string(),"recipe":ticket.recipe.to_string(),"viewport":ticket.viewport.to_string()},
            "canvasWidth":canvas_width,"canvasHeight":canvas_height,"roi":{"x":x,"y":y,"width":width,"height":height},
            "maxPayloadBytes":host::PATCH_PIXELS*4}}))
}
#[tauri::command]
pub fn inspection_status(state:State<'_,Arc<AppState>>)->Value{
    let h=state.inspection.lock().unwrap();
    json!({"epoch":hex(h.epoch),"available":h.available,"state":h.phase,"error":h.error,
        "generation":h.generation().to_string(),
        "request_id":h.desired_id.map(|n|n.to_string()),
        "worker_id":h.active.as_ref().map(|r|r.ticket.id.to_string()),
        "published_epoch":h.published.map(|(e,_)|hex(e)),"published_id":h.published.map(|(_,t)|t.id.to_string())})
}
#[tauri::command]
pub fn inspection_cancel(state:State<'_,Arc<AppState>>,engine_epoch:String,request_id:String)->Result<Value,String>{
    {let mut h=state.inspection.lock().map_err(|_|"inspection lock poisoned")?;
        if h.epoch!=epoch(&engine_epoch)?{return Err("inspection cancellation epoch changed".into());}
        let actions=h.cancel(number(&request_id)?)?;let e=h.epoch;
        state.dispatch_inspection_locked(&mut h,e,actions)?;}
    Ok(json!({"requested":true}))
}
#[tauri::command]
pub fn inspection_release(state:State<'_,Arc<AppState>>,engine_epoch:String,request_id:String)->Result<Value,String>{
    state.inspection.lock().map_err(|_|"inspection lock poisoned")?.release_publication(epoch(&engine_epoch)?,number(&request_id)?)?;
    Ok(json!({"released":true}))
}
#[tauri::command]
pub async fn inspection_pull(state:State<'_,Arc<AppState>>,engine_epoch:String,request_id:String)->Result<tauri::ipc::Response,String>{
    let st=state.inner().clone();
    let root=st.inspection_root.lock().map_err(|_|"inspection root lock poisoned")?.clone().ok_or("inspection root unavailable")?;
    let (epoch,request,path)={let mut h=st.inspection.lock().map_err(|_|"inspection lock poisoned")?;
        if h.epoch!=epoch(&engine_epoch)?{return Err("inspection pull epoch changed".into());}
        h.begin_pull(number(&request_id)?)?};
    let ticket=request.ticket;
    let result=match tauri::async_runtime::spawn_blocking(move||root.read(&path,epoch,&request)).await{
        Ok(value)=>value,Err(e)=>Err(format!("inspection reader failed: {e}"))};
    let accepted={let mut h=st.inspection.lock().map_err(|_|"inspection lock poisoned")?;
        if h.epoch==epoch && h.active.as_ref().map(|r|r.ticket)==Some(ticket){
            if let Err(e)=&result{h.error=Some(e.clone());}
        }
        let (accepted,actions)=h.finish_pull(epoch,ticket,result.is_ok())?;
        if let Err(e)=st.dispatch_inspection_locked(&mut h,epoch,actions){
            if accepted{let _=h.release_publication(epoch,ticket.id);}
            return Err(e);
        }
        accepted};
    if !accepted{return Err(result.err().unwrap_or_else(||"inspection became stale while reading".into()));}
    Ok(tauri::ipc::Response::new(result?))
}

#[cfg(test)]
mod tests{
    use super::*;
    use host::wire::refinement::Request;
    #[test] fn inspection_identity_parsing_rejects_ambiguous_or_unsafe_values(){
        assert_eq!(number("9007199254740993").unwrap(),9007199254740993);
        for value in ["01","-1","18446744073709551616"]{assert!(number(value).is_err());}
        assert!(epoch(&"00".repeat(16)).is_err());assert!(epoch(&"é".repeat(16)).is_err());
        assert!(ticket(&json!([1,"2","3","4","5"])).is_err());
    }
    #[test] fn inspection_command_keeps_all_generation_fields_as_strings(){
        let r=Request{ticket:Ticket{id:9007199254740993,document:2,source_generation:3,recipe:4,viewport:5},
            source_width:10,source_height:10,canvas_width:10,canvas_height:10,
            roi:Roi{x:0,y:0,width:1,height:1},estimated_live_bytes:1000};
        let cmd=command(&Action::Start(r),[7;16]);
        assert_eq!(cmd["request_id"],"9007199254740993");
        assert_eq!(cmd["render"]["ticket"],json!(["9007199254740993","2","3","4","5"]));
    }
}
