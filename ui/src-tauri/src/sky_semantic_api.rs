//! Read-only semantic proposals. Only the existing sky-output receipt can apply an edit.
use std::{collections::{BTreeMap, BTreeSet}, sync::Arc};
use serde_json::{json, Value};
use tauri::State;
use crate::{AppState, color_capture_host::{id16, token}};

#[derive(Default)]
pub(crate) struct SemanticHost {
    epoch: [u8;16],
    binding: Option<(String,String,String)>,
    requests: BTreeMap<String,(String,Value)>,
    proposal: Option<Value>,
    proposal_id: Option<String>,
    delivered: bool,
    shown: BTreeSet<String>,
}
impl SemanticHost {
    pub fn reset(&mut self, epoch:[u8;16]) { self.invalidate(); self.epoch=epoch; }
    pub fn invalidate(&mut self) {
        self.binding=None;
        self.requests.clear();
        self.proposal=None;
        self.proposal_id=None;
        self.delivered=false;
        self.shown.clear();
    }
    pub fn ended(&mut self, epoch:[u8;16]) { if self.epoch==epoch { self.reset([0;16]); } }
    fn matches(&self, epoch:[u8;16], document:&str, session:&str, run:&str)->bool {
        epoch!=[0;16] && epoch==self.epoch && self.binding.as_ref().is_some_and(|b| b.0==document && b.1==session && b.2==run)
    }
    pub fn receive(&mut self, epoch:[u8;16], value:&Value) {
        let Some((document,session,run))=self.binding.as_ref() else { return };
        if !self.matches(epoch,document,session,run) || value["protocol"]!=1
            || value["document_id"]!=document.as_str() || value["session_id"]!=session.as_str() || value["run_id"]!=run.as_str() { return; }
        if value["event"]=="sky_semantic_result" {
            let Some(id)=value["request_id"].as_str() else { return };
            let Some((action,record))=self.requests.get_mut(id) else { return };
            if !value["success"].is_boolean() || value["draft_only"]!=true || value.to_string().len()>16384 { return; }
            if value["success"]==true {
                if action=="start" {
                    let Some(proposal)=value["proposal_id"].as_str().filter(|s| id16(s).is_ok()) else { return };
                    self.proposal_id=Some(proposal.into());
                } else if action=="shown" {
                    if let Some(region)=record["region"].as_str() { self.shown.insert(region.into()); }
                } else if action=="accept" && (!value["semantic"].is_object() || value["requires_sky_output_review"]!=true) { return; }
            }
            *record=value.clone();
        } else if value["event"]=="sky_semantic_proposal" {
            if !self.proposal_id.as_ref().is_some_and(|id| value["proposal_id"]==id.as_str()) { return; }
            let valid=match value["state"].as_str() {
                Some("ready")=> value["proposal_only"]==true && value["review_required"]==true && value["horizon_automatic"]==false
                    && value["source_image"].as_str().is_some_and(|s| s.starts_with("data:image/png;base64,") && s.len()<=4*1024*1024)
                    && ["sky","person","water"].iter().all(|key| value["counts"][*key].as_u64().is_some_and(|n| n<=1024*1024)
                        && value["candidate_overlays"][*key].as_str().is_some_and(|s| s.starts_with("data:image/png;base64,") && s.len()<=2*1024*1024)),
                Some("failed"|"cancelled")=>value["error"].is_string(),
                _=>false,
            };
            self.delivered=false;
            self.shown.clear();
            self.proposal=Some(if valid && value.to_string().len()<=8*1024*1024 { value.clone() }
                else { json!({"event":"sky_semantic_proposal","protocol":1,"proposal_id":self.proposal_id,
                    "state":"failed","error":"invalid or oversized semantic proposal"}) });
        }
    }
}

#[tauri::command]
pub(crate) fn sky_semantic(state:State<'_,Arc<AppState>>, request_id:String, document_id:String,
    session_id:String, run_id:String, action:String, device:Option<String>, proposal_id:Option<String>, region:Option<String>, regions:Option<Value>)->Result<Value,String> {
    id16(&request_id)?;
    id16(&session_id)?;
    id16(&run_id)?;
    token(&document_id)?;
    if !matches!(action.as_str(),"start"|"cancel"|"shown"|"accept") { return Err("invalid semantic action".into()); }
    if (action=="start")!=device.is_some() || (matches!(action.as_str(),"shown"|"accept"))!=proposal_id.is_some()
        || (action=="shown")!=region.is_some() || (action=="accept")!=regions.is_some() { return Err("unexpected semantic arguments".into()); }
    if state.ready_caps.lock().map_err(|_|"capability lock poisoned")?["sky_semantic_protocol"]!=1 {
        return Err("current engine has no optional semantic proposal protocol".into());
    }
    let handle=state.engine.lock().map_err(|_|"engine lock poisoned")?.clone().filter(|h|h.is_alive()).ok_or("engine is not running")?;
    if action!="cancel" && !state.sky_preview.lock().map_err(|_|"sky preview lock poisoned")?
        .source_session(handle.epoch(),&document_id,&session_id,action=="start") { return Err("shown sky source session expired".into()); }
    let mut host=state.sky_semantic.lock().map_err(|_|"semantic lock poisoned")?;
    if action=="start" {
        if !matches!(device.as_deref(),Some("cpu"|"cuda")) { return Err("choose CPU or CUDA explicitly".into()); }
        if host.epoch!=handle.epoch() { return Err("semantic engine changed".into()); }
        if request_id!=run_id { return Err("semantic run identity mismatch".into()); }
        host.invalidate();
        host.binding=Some((document_id.clone(),session_id.clone(),run_id.clone()));
    } else if !host.matches(handle.epoch(),&document_id,&session_id,&run_id) { return Err("semantic source session expired".into()); }
    if host.requests.contains_key(&request_id) || host.requests.len()>=32 { return Err("semantic request ID reused or budget exceeded".into()); }
    let mut command=json!({"cmd":"sky_semantic","request_id":request_id,"action":action,"document_id":document_id,"session_id":session_id,"run_id":run_id});
    if let Some(device)=device { command["device"]=json!(device); }
    if let Some(proposal)=proposal_id {
        id16(&proposal)?;
        if host.proposal_id.as_ref()!=Some(&proposal) || !host.delivered || !host.proposal.as_ref().is_some_and(|v|v["state"]=="ready") {
            return Err("semantic proposal has not been delivered or changed".into());
        }
        command["proposal_id"]=json!(proposal);
    }
    if let Some(region)=region {
        if !matches!(region.as_str(),"sky"|"person"|"water") { return Err("invalid semantic region".into()); }
        command["region"]=json!(region);
    }
    if let Some(regions)=regions {
        let object=regions.as_object().filter(|v|!v.is_empty()&&v.len()<=3).ok_or("select reviewed semantic regions")?;
        if !object.iter().all(|(key,value)| host.shown.contains(key) && value.as_f64().is_some_and(|x|x.is_finite()&&(0.0..=1.0).contains(&x))) {
            return Err("every selected semantic region must be displayed first".into());
        }
        command["regions"]=regions;
    }
    host.requests.insert(request_id.clone(),(action,json!({"state":"running","request_id":request_id,"region":command["region"]})));
    if let Err(error)=handle.send(command) {
        host.requests.remove(&request_id);
        return Err(error);
    }
    Ok(json!({"requested":true}))
}

#[tauri::command]
pub(crate) fn sky_semantic_result(state:State<'_,Arc<AppState>>, request_id:String)->Result<Value,String> {
    id16(&request_id)?;
    let host=state.sky_semantic.lock().map_err(|_|"semantic lock poisoned")?;
    Ok(host.requests.get(&request_id).map(|(_,value)|value.clone()).unwrap_or_else(||json!({"state":"stale","request_id":request_id})))
}

#[tauri::command]
pub(crate) fn sky_semantic_proposal_status(state:State<'_,Arc<AppState>>, document_id:String, session_id:String, run_id:String, proposal_id:String)->Result<Value,String> {
    id16(&session_id)?;
    id16(&run_id)?;
    id16(&proposal_id)?;
    token(&document_id)?;
    let handle=state.engine.lock().map_err(|_|"engine lock poisoned")?.clone().filter(|h|h.is_alive()).ok_or("engine is not running")?;
    let source=state.sky_preview.lock().map_err(|_|"sky preview lock poisoned")?.source_session(handle.epoch(),&document_id,&session_id,false);
    let mut host=state.sky_semantic.lock().map_err(|_|"semantic lock poisoned")?;
    if !source || !host.matches(handle.epoch(),&document_id,&session_id,&run_id) || host.proposal_id.as_ref()!=Some(&proposal_id) {
        return Ok(json!({"state":"stale","proposal_id":proposal_id}));
    }
    if host.proposal.as_ref().is_some_and(|v|v["state"]=="ready") { host.delivered=true; }
    Ok(host.proposal.clone().unwrap_or_else(||json!({"state":"running","proposal_id":proposal_id})))
}
