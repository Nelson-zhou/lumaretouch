// SPDX-License-Identifier: GPL-3.0-or-later
//! Engine-epoch-owned lens mailbox. It retains exact commands, read evidence and
//! immutable write outcomes, not a renderer, document writer or second history.
use std::{collections::{HashMap,VecDeque},sync::{Arc,Mutex,OnceLock},time::{Duration,Instant}};
use serde_json::{json,Value};
use tauri::State;
use crate::{engine::EngineHandle,lens_blur_protocol as wire,AppState};

const STORE_BYTES:usize=128*1024*1024;
const MAX_ROWS:usize=128;
const MAX_IDENTITIES:usize=16_384;
const IDENTITY_BYTES:usize=8*1024*1024;
const SESSION_TTL:Duration=Duration::from_secs(600);
const PREVIEW_TTL:Duration=Duration::from_secs(180);
struct Identity {epoch:[u8;16],signature:String}
struct Row {
    epoch:[u8;16],request:wire::Request,result:Value,terminal:bool,dispatched:bool,
    cancel_requested:bool,ingress_once:bool,redeemed:bool,retired:bool,reserved:usize,request_bytes:usize,
    before:Option<Value>,expires:Option<Instant>,
}
impl Row {
    fn bytes(&self)->usize {self.request_bytes.saturating_add(self.reserved)}
    fn imagery(&self)->bool {self.result["context"].is_object() || self.result["review"].is_object()}
    fn evictable(&self)->bool {self.terminal && (!self.imagery() || self.redeemed || self.retired)}
}
struct Session {epoch:[u8;16],id:Value,owner:Value,before:Value,depth:Option<Value>,expires:Instant}
#[derive(Default)]
struct Mailbox {
    epoch:[u8;16],supported:bool,ended:bool,capability:Value,rows:VecDeque<Row>,
    seen:HashMap<String,Identity>,identity_bytes:usize,session:Option<Session>,
}
fn mailbox()->&'static Mutex<Mailbox> {
    static STORE:OnceLock<Mutex<Mailbox>>=OnceLock::new();
    static REAPER:OnceLock<bool>=OnceLock::new();
    let store=STORE.get_or_init(||Mutex::new(Mailbox::default()));
    // Idle windows must not pin completed image payloads forever. No rendering,
    // IPC or product work occurs on this bounded lease-maintenance thread.
    let running=*REAPER.get_or_init(||std::thread::Builder::new().name("lens-receipt-leases".into()).spawn(move || loop {
        std::thread::sleep(Duration::from_secs(15));
        if let Ok(mut host)=store.lock() {host.expire(Instant::now());}
    }).is_ok());
    if !running {if let Ok(mut host)=store.lock(){host.supported=false;host.ended=true;host.capability=unavailable_capability();}}
    store
}
fn unavailable(id:&str)->Value {json!({"event":wire::EVENT,"request_id":id,"status":"unknown","message":"原请求未保留或身份不存在；不能认定未执行，也不会重新提交"})}
fn unavailable_capability()->Value {json!({"version":1,"operation_id":wire::OPERATION,"status":"unavailable","kernels":[],"reason":"配套引擎尚未声明镜头协议 2 与可用原生光圈；不提供 AI 景深或占位效果"})}
fn reservation(action:&str)->usize {match action {"current"|"prepare_manual_plane"=>wire::CONTEXT_BYTES,"preview"=>wire::RESULT_BYTES,_=>wire::SMALL_BYTES}}
fn image_proof(image:&Value)->Value {json!({"sha256":image["sha256"],"width":image["width"],"height":image["height"]})}
fn depth_proof(depth:&Value)->Value {json!({"token":depth["token"],"sha256":depth["raster"]["sha256"],"provenance":depth["provenance"]})}
fn same_session(session:&Session,request:&wire::Request)->bool {
    session.id==request.inner()["session_id"] && wire::same(&session.owner,&request.inner()["owner"])
}
impl Mailbox {
    fn expire(&mut self,now:Instant) {
        if self.session.as_ref().is_some_and(|s|now>=s.expires) {self.session=None;}
        for row in &mut self.rows {
            if row.terminal && row.imagery() && row.expires.is_some_and(|end|now>=end) {
                // Only large successful read leases expire. A small validated
                // cancelled/rejected/applied terminal is never rewritten here.
                row.result=wire::rejected(&row.request,"只读图像租约已过期；原请求不会重跑。请明确重新读取当前照片或生成新对比");
                row.before=None;row.retired=true;row.expires=None;row.reserved=wire::SMALL_BYTES;
            }
        }
    }
    fn status(&mut self,id:&str)->Value {
        self.expire(Instant::now());
        self.rows.iter().find(|r|r.request.id==id).map(|r|r.result.clone()).unwrap_or_else(||unavailable(id))
    }
    fn replay(&self,req:&wire::Request)->Result<bool,String> {
        match self.seen.get(&req.id) {None=>Ok(false),Some(old) if old.signature==req.signature=>Ok(true),Some(_)=>Err("镜头请求身份已绑定其他完整原始内容，未重新提交".into())}
    }
    fn end(&mut self,epoch:[u8;16]) {
        if self.session.as_ref().is_some_and(|s|s.epoch==epoch) {self.session=None;}
        for row in self.rows.iter_mut().filter(|r|r.epoch==epoch) {
            if row.request.read() && (!row.terminal || row.imagery()) {
                row.result=wire::rejected(&row.request,"原引擎的只读图像租约已失效；没有据此修改照片，也不表示强制停止了计算");
                row.terminal=true;row.retired=true;row.before=None;row.expires=None;row.reserved=wire::SMALL_BYTES;
            } else if !row.terminal {
                row.result=wire::pending(&row.request,"unknown","原引擎结束前未收到确定回执；原写入结果未知，只能核对，不能重发");
                // A genuine late raw terminal from draining stdout may still
                // establish the original outcome. Keep its small reservation.
            }
        }
        if self.epoch==epoch {self.ended=true;self.supported=false;}
    }
    fn make_room(&mut self,additional:usize)->Result<(),String> {
        self.expire(Instant::now());
        while self.rows.len()>=MAX_ROWS || self.rows.iter().map(Row::bytes).sum::<usize>().saturating_add(additional)>STORE_BYTES {
            let Some(index)=self.rows.iter().position(Row::evictable) else{return Err("镜头安全回执容量已满；未提交新操作，请先核对原请求或等待只读租约释放".into());};
            self.rows.remove(index);
        } Ok(())
    }
    fn admission(&self,epoch:[u8;16],req:&wire::Request)->Result<Option<Value>,String> {
        if epoch==[0;16] || self.epoch!=epoch || self.ended || !self.supported {return Err("原引擎不可用或未声明镜头协议 2；未执行".into());}
        if req.action=="receipt" {
            let Some(original)=self.rows.iter().find(|r|r.epoch==epoch && r.request.write() && r.request.id==req.inner()["request_id"]) else {
                return Err("当前引擎未保留该原写入及其完整身份；不会向另一个引擎猜测或重发".into());
            };
            if !wire::same(original.request.inner(),req.inner()) {return Err("查询内容与保留的原写入不完全一致".into());}
            return Ok(None);
        }
        if self.rows.iter().any(|r|r.epoch==epoch && r.request.write() && !r.terminal) {
            return Err("上一镜头写入或取消尚未确认；仅可查询同一原请求，不能再次提交".into());
        }
        if req.read() && self.rows.iter().any(|r|r.epoch==epoch && r.request.read() && !r.terminal) {
            return Err("已有当前照片读取或预览正在运行；请等待原请求终态或请求停止它".into());
        }
        if req.action=="current" {return Ok(None);}
        let session=self.session.as_ref().filter(|s|s.epoch==epoch && same_session(s,req)).ok_or("缺少完全匹配的当前照片、原文档身份及有效会话租约")?;
        if req.action=="preview" {
            if !session.depth.as_ref().is_some_and(|d|wire::same(d,&req.inner()["recipe"]["depth"])) {
                return Err("配方未绑定本会话明确确认的人工散焦基准面；不会使用 AI 或占位景深".into());
            }
            if !self.capability["kernels"].as_array().is_some_and(|ks|ks.contains(&req.inner()["recipe"]["aperture"])) {
                return Err("原生宿主未声明该光圈核，不会替换成另一种效果".into());
            }
        }
        if req.apply() && !self.rows.iter().any(|r|r.epoch==epoch && r.terminal && !r.retired && !r.redeemed
            && r.request.action=="preview" && wire::apply_matches(req,&r.result["review"])) {
            return Err("缺少本引擎未消费且原文档、完整前后图与完整输出哈希全部匹配的真实预览".into());
        }
        if req.write() && req.inner()["action"]=="cancel" && !req.inner()["token"].is_null()
            && !self.rows.iter().any(|r|r.epoch==epoch && r.request.action=="preview" && !r.retired
                && r.result["review"]["token"]==req.inner()["token"] && wire::same(&r.result["review"]["owner"],&session.owner)
                && r.result["review"]["session_id"]==session.id) {
            return Err("取消令牌不属于当前保留会话，未发送猜测性取消".into());
        }
        Ok(Some(session.before.clone()))
    }
    fn begin(&mut self,epoch:[u8;16],req:wire::Request)->Result<bool,String> {
        self.expire(Instant::now());
        if self.replay(&req)? {return Ok(false);}
        let identity_bytes=req.id.len()+req.signature.len()+64;
        if self.seen.len()>=MAX_IDENTITIES || self.identity_bytes.saturating_add(identity_bytes)>IDENTITY_BYTES {
            return Err("镜头防重放身份容量已满；未提交。旧身份不会因释放图像而删除".into());
        }
        let proof=self.admission(epoch,&req);
        let request_bytes=wire::size(&req.envelope,wire::COMMAND_BYTES+4096)?;
        let reserved=if proof.is_ok() {reservation(&req.action)} else {wire::SMALL_BYTES};
        self.make_room(request_bytes+reserved)?;
        // Capacity cleanup may have evicted a redeemed old row, never a live
        // apply candidate. Check again before consuming its one-copy authority.
        if req.apply() && proof.is_ok() {
            let Some(preview)=self.rows.iter_mut().find(|r|r.epoch==epoch && !r.retired && !r.redeemed
                && r.request.action=="preview" && wire::apply_matches(&req,&r.result["review"])) else{return Err("原预览租约已失效，未提交新副本".into());};
            preview.redeemed=true;
        }
        let terminal=proof.is_err(); // Failed query is complete, but its original write remains unknown.
        let result=match &proof {Ok(_)=>wire::pending(&req,"pending","原镜头请求已登记，等待真实宿主回执"),Err(why)=>wire::rejected(&req,why)};
        let dispatch=proof.is_ok();
        // Only one engine current/depth/candidate lease exists. Admission of a
        // new current/plane/preview revokes old local apply authority immediately.
        if dispatch && req.action=="current" {self.session=None;}
        if dispatch && matches!(req.action.as_str(),"current"|"prepare_manual_plane"|"preview") {
            for row in self.rows.iter_mut().filter(|r|r.epoch==epoch && r.request.action=="preview") {row.redeemed=true;}
        }
        self.identity_bytes+=identity_bytes;
        self.seen.insert(req.id.clone(),Identity{epoch,signature:req.signature.clone()});
        self.rows.push_back(Row{epoch,request:req,result,terminal,dispatched:false,cancel_requested:false,ingress_once:false,redeemed:false,retired:false,
            reserved,request_bytes,before:proof.ok().flatten(),expires:None});
        Ok(dispatch)
    }
    fn unknown(&mut self,epoch:[u8;16],id:&str,why:&str) {
        if let Some(row)=self.rows.iter_mut().find(|r|r.epoch==epoch && r.request.id==id && !r.terminal) {row.result=wire::pending(&row.request,"unknown",why);}
    }
    fn ingress(&mut self,epoch:[u8;16],command:&Value)->Result<(),String> {
        let mut admitted_lens=false;
        if command["cmd"]=="lens_blur" {
            let row=self.rows.iter_mut().find(|r|r.epoch==epoch && command["request_id"]==r.request.id)
                .ok_or("镜头原始请求没有经过专用登记，未执行旁路提交")?;
            if !row.dispatched || !row.ingress_once || row.terminal || !wire::same(command,&row.request.envelope) {
                return Err("镜头原请求的单次入口已使用或内容变化，不能从普通或交互入口重发".into());
            }
            row.ingress_once=false;admitted_lens=true;
        }
        if !self.rows.iter().any(|r|r.epoch==epoch && r.request.apply() && !r.terminal) {return Ok(());}
        if admitted_lens || matches!(command["cmd"].as_str(),Some("hello"|"shutdown")) {return Ok(());}
        Err("镜头新副本原请求尚未确认；请查询原请求，暂不允许继续写入、撤销、保存或导出".into())
    }
    fn observe(&mut self,epoch:[u8;16],v:&Value)->Option<Value> {
        self.expire(Instant::now());
        let id=v["request_id"].as_str()?;
        let index=self.rows.iter().position(|r|r.epoch==epoch && r.request.id==id)?;
        let row=&self.rows[index];
        if row.terminal || !row.dispatched {return None;}
        let before=if row.request.action=="prepare_manual_plane" {v.get("context").map(|c|&c["source_image"])}
            else if row.request.action=="preview" {v.get("review").map(|r|&r["before"])} else {None};
        let same_before=before.map_or(true,|image|row.before.as_ref().is_some_and(|proof|wire::same(proof,&image_proof(image))));
        let consistent_terminal=row.request.action!="receipt" || self.rows.iter().find(|r|r.epoch==epoch && r.request.write()
            && r.request.id==row.request.inner()["request_id"] && wire::same(r.request.inner(),row.request.inner()))
            .is_some_and(|original|!original.terminal || wire::same(&original.result["receipt"],&v["receipt"]));
        let bytes=wire::size(v,reservation(&row.request.action));
        if bytes.is_err() || !wire::valid_result(v,&row.request) || !same_before || !consistent_terminal {
            self.unknown(epoch,id,"宿主回执原文、字段、完整图像哈希或保留身份不匹配；不能据此确认写入或取消");return None;
        }
        let terminal=wire::terminal(v);
        if !terminal && v["receipt"]["phase"]=="pending" && self.rows[index].result["receipt"]["phase"]=="unknown" {return None;}
        let action=row.request.action.clone();
        let is_apply=row.request.apply();
        let inner=row.request.inner().clone();
        // Update small session proof only after exact raw receipt validation.
        if terminal && v["context"].is_object() && epoch==self.epoch && !self.ended {
            let context=&v["context"];
            let expires=if action=="prepare_manual_plane" {self.session.as_ref().map(|s|s.expires).unwrap_or(Instant::now())} else {Instant::now()+SESSION_TTL};
            self.session=Some(Session{epoch,id:context["session_id"].clone(),owner:context["owner"].clone(),before:image_proof(&context["source_image"]),
                depth:context["depth"].is_object().then(||depth_proof(&context["depth"])),expires});
        }
        let session_expiry=self.session.as_ref().filter(|s|s.epoch==epoch).map(|s|s.expires);
        let image_expiry=if action=="preview" {Some(session_expiry.map_or(Instant::now(),|end|end.min(Instant::now()+PREVIEW_TTL)))}else{session_expiry};
        let row=&mut self.rows[index];row.result=v.clone();row.terminal=terminal || action=="receipt";
        if row.terminal {row.reserved=bytes.ok()?;row.before=None;row.expires=if row.imagery(){image_expiry}else{None};}
        // Readback has its own transport ID. The exact unmodified receipt is
        // matched to the retained original write before its fence can settle.
        let mut settled=None;
        if action=="receipt" {
            if let Some(original)=self.rows.iter_mut().find(|r|r.epoch==epoch && r.request.write() && r.request.id==inner["request_id"]
                && wire::same(r.request.inner(),&inner) && !r.terminal) {
                let receipt=&v["receipt"];
                if receipt["phase"]!="pending" || original.result["receipt"]["phase"]!="unknown" {
                    original.result=json!({"event":wire::EVENT,"request_id":original.request.id,"status":"ready","receipt":receipt});
                    original.terminal=terminal;
                    if terminal {original.reserved=wire::SMALL_BYTES;original.before=None;}
                }
                if terminal && original.request.apply() {settled=Some(original.request.id.clone());}
            }
        } else if terminal && is_apply {settled=Some(id.to_owned());}
        if terminal && (action=="submit" || action=="receipt") && matches!(v["receipt"]["outcome"].as_str(),Some("applied"|"cancelled")) {
            if self.session.as_ref().is_some_and(|s|s.epoch==epoch && s.id==inner["session_id"] && wire::same(&s.owner,&inner["owner"])) {self.session=None;}
            for r in self.rows.iter_mut().filter(|r|r.epoch==epoch && r.imagery()) {r.expires=Some(Instant::now());}
            self.expire(Instant::now());
        }
        // Internal settlement only. Never replace the UI's exact protocol-2
        // receipt with a fake history entry, document_id alias or success bit.
        settled.map(|original|json!({"event":wire::EVENT,"request_id":original,"phase":"done","outcome_unknown":false}))
    }
}
pub(crate) fn reset(epoch:[u8;16]) {if let Ok(mut host)=mailbox().lock(){let old=host.epoch;host.end(old);host.epoch=epoch;host.supported=false;host.ended=false;host.capability=unavailable_capability();}}
pub(crate) fn ready(epoch:[u8;16],capability:&Value) {
    if let Ok(mut host)=mailbox().lock(){if host.epoch==epoch && !host.ended {
        host.supported=wire::capability(capability) && capability["status"]=="available";
        host.capability=if wire::capability(capability){capability.clone()}else{unavailable_capability()};
    }}
}
pub(crate) fn ended(epoch:[u8;16]) {if let Ok(mut host)=mailbox().lock(){host.end(epoch);}}
/// Engine stdout MUST call this on the original unparsed line before generic
/// recovery settlement. Parsed Value ingress cannot detect duplicate JSON keys.
pub(crate) fn observe_line(epoch:[u8;16],line:&str)->Option<Value> {
    let value=match wire::unique_json(line,wire::RESULT_BYTES) {Ok(v)=>v,Err(_)=>{
        if let Ok(mut host)=mailbox().lock(){for row in host.rows.iter_mut().filter(|r|r.epoch==epoch && r.dispatched && !r.terminal){
            row.result=wire::pending(&row.request,"unknown","宿主原始 JSON 重复、超限或无效；原请求结果仍未知，不会自动重发");
        }} return None;
    }};
    mailbox().lock().ok()?.observe(epoch,&value)
}
pub(crate) fn guards_result(epoch:[u8;16],id:&str)->bool {
    mailbox().lock().map(|h|h.seen.get(id).is_some_and(|s|s.epoch==epoch)).unwrap_or(true)
}
pub(crate) fn read_only(command:&Value)->bool {
    command["cmd"]=="lens_blur" && (matches!(command["action"].as_str(),Some("current"|"prepare_manual_plane"|"preview"|"receipt"))
        || command["action"]=="submit" && command["command"]["action"]=="cancel")
}
/// Consult on ordinary AND interactive ingress, including direct API sends.
/// A timeout, navigation, read cancellation or unverified event never clears it.
pub(crate) fn blocks_mutation(epoch:[u8;16],command:&Value)->Result<(),String> {
    mailbox().lock().map_err(|_|"镜头原请求屏障锁不可用")?.ingress(epoch,command)
}
/// Shared native dispatch calls once; private host_epoch never crosses stdin.
pub(crate) fn enqueue(handle:&EngineHandle,mut command:Value)->Result<(),String> {
    let epoch=command.as_object_mut().ok_or("镜头信封无效")?.remove("host_epoch").ok_or("缺少原镜头引擎身份")?;
    if epoch.as_str()!=Some(crate::frame_identity::hex(handle.epoch()).as_str()) {return Err("引擎已变化，未向新引擎重发原镜头请求".into());}
    let id=command["request_id"].as_str().ok_or("镜头请求身份缺失")?.to_owned();
    {
        let mut host=mailbox().lock().map_err(|_|"镜头回执锁不可用")?;
        if host.epoch!=handle.epoch() || host.ended || !host.supported || !handle.is_alive() {return Err("原镜头引擎已结束或协议不再有效，未重新提交".into());}
        let row=host.rows.iter_mut().find(|r|r.epoch==handle.epoch() && r.request.id==id).ok_or("镜头命令没有原生登记")?;
        if row.terminal || row.dispatched || !wire::same(&command,&row.request.envelope) {return Err("镜头原请求已发送或内容变化，不会重发".into());}
        row.dispatched=true;row.ingress_once=true; // Before queue/write/flush uncertainty.
    }
    let sent=handle.send(command);
    // Even another domain's pre-ingress refusal consumes this attempt. An
    // unknown original must never retain a reusable direct-send capability.
    if let Ok(mut host)=mailbox().lock() {if let Some(row)=host.rows.iter_mut().find(|r|r.epoch==handle.epoch() && r.request.id==id) {row.ingress_once=false;}}
    sent
}
#[tauri::command]
pub(crate) fn lens_blur_capability(state:State<'_,Arc<AppState>>)->Result<Value,String> {
    let engine=state.engine.lock().map_err(|_|"引擎锁不可用")?;
    let host=mailbox().lock().map_err(|_|"镜头回执锁不可用")?;
    let available=engine.as_ref().is_some_and(|h|h.is_alive() && h.epoch()==host.epoch) && !host.ended;
    Ok(if available && wire::capability(&host.capability){host.capability.clone()}else{unavailable_capability()})
}
#[tauri::command]
pub(crate) fn lens_blur_request(state:State<'_,Arc<AppState>>,request:Value)->Result<Value,String> {
    let req=wire::parse_request(&request)?;let id=req.id.clone();let apply=req.apply();
    {let mut host=mailbox().lock().map_err(|_|"镜头回执锁不可用")?;if host.replay(&req)? {return Ok(host.status(&id));}}
    let handle=state.engine.lock().map_err(|_|"引擎锁不可用")?.clone();
    let epoch=handle.as_ref().map(|h|h.epoch()).unwrap_or([0;16]);
    let dispatch=mailbox().lock().map_err(|_|"镜头回执锁不可用")?.begin(epoch,req)?;
    if dispatch {
        let mut envelope=request;envelope["host_epoch"]=json!(crate::frame_identity::hex(epoch));
        let sent=if apply {state.send_to_engine(envelope)} else {handle.as_ref().ok_or_else(||"引擎未运行".to_string()).and_then(|h|enqueue(h,envelope))};
        if let Err(error)=sent {
            let why=format!("原镜头请求发送未获确认：{}；不会自动重发",error.chars().take(512).collect::<String>());
            mailbox().lock().map_err(|_|"镜头回执锁不可用")?.unknown(epoch,&id,&why);
        }
    }
    Ok(mailbox().lock().map_err(|_|"镜头回执锁不可用")?.status(&id))
}
#[tauri::command]
pub(crate) fn lens_blur_status(_state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String> {
    if !wire::token(&json!(request_id)) {return Err("镜头请求身份无效".into());}
    Ok(mailbox().lock().map_err(|_|"镜头回执锁不可用")?.status(&request_id))
}
#[tauri::command]
pub(crate) fn lens_blur_cancel(state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String> {
    if !wire::token(&json!(request_id)) {return Err("镜头取消请求身份无效".into());}
    let engine=state.engine.lock().map_err(|_|"引擎锁不可用")?;
    let handle=engine.as_ref().filter(|h|h.is_alive()).ok_or("原引擎不可用；不能确认读取已停止")?;
    let epoch=handle.epoch();
    let original={
        let mut host=mailbox().lock().map_err(|_|"镜头回执锁不可用")?;
        let row=host.rows.iter_mut().find(|r|r.epoch==epoch && r.request.id==request_id).ok_or("该读取不属于当前引擎，未发送盲目取消")?;
        if !row.request.read() {return Err("此控制只允许停止原读取或预览，不能中断 apply、伪造取消回执或撤销新图".into());}
        if row.terminal {return Ok(json!({"requested":false,"request_id":request_id,"message":"原请求已有终态，请读取原回执"}));}
        if !row.dispatched {return Err("原读取未进入引擎，不能发送脱离原工作的取消".into());}
        if row.cancel_requested {return Ok(json!({"requested":true,"request_id":request_id,"message":"已请求停止原读取，仍须等待原请求终态"}));}
        row.cancel_requested=true;
        row.result=wire::pending(&row.request,"unknown","已请求停止原读取；这不代表已经取消，必须等待原请求实际终态");
        row.request.envelope.clone()
    };
    if let Err(error)=handle.cancel_lens_blur_read(&request_id,&original) {
        mailbox().lock().map_err(|_|"镜头回执锁不可用")?.unknown(epoch,&request_id,"取消控制发送未获确认；仍须等待原读取终态，不会重发取消");return Err(error);
    }
    Ok(json!({"requested":true,"request_id":request_id,"message":"已请求停止原读取，仍须等待原请求终态"}))
}

#[cfg(test)]
mod mailbox_unrun {
    use super::*;
    #[test] fn rejected_terminal_survives_epoch_end_and_replay() {
        let req=wire::parse_request(&json!({"cmd":"lens_blur","action":"current","request_id":"read-one"})).unwrap();
        let mut host=Mailbox::default();assert!(!host.begin([1;16],req.clone()).unwrap());let terminal=host.status("read-one");
        host.end([1;16]);assert_eq!(host.status("read-one"),terminal);assert!(!host.begin([2;16],req).unwrap());assert_eq!(host.status("read-one"),terminal);
    }
    #[test] fn tombstone_survives_eviction_and_cannot_redispatch() {
        let req=wire::parse_request(&json!({"cmd":"lens_blur","action":"current","request_id":"retained-id"})).unwrap();
        let mut host=Mailbox::default();host.begin([1;16],req.clone()).unwrap();host.rows.clear();
        assert!(!host.begin([2;16],req).unwrap());assert_eq!(host.status("retained-id")["status"],"unknown");
    }
    #[test] fn first_valid_cancelled_read_is_immutable_even_after_end() {
        let req=wire::parse_request(&json!({"cmd":"lens_blur","action":"current","request_id":"cancelled-read"})).unwrap();
        let mut host=Mailbox{epoch:[2;16],supported:true,..Mailbox::default()};host.begin([2;16],req).unwrap();host.rows[0].dispatched=true;
        let terminal=json!({"event":wire::EVENT,"request_id":"cancelled-read","status":"cancelled","message":"Actually unwound"});
        host.observe([2;16],&terminal);host.end([2;16]);host.expire(Instant::now()+SESSION_TTL+SESSION_TTL);
        assert_eq!(host.status("cancelled-read"),terminal);
        host.observe([2;16],&json!({"event":wire::EVENT,"request_id":"cancelled-read","status":"rejected","message":"contradiction"}));
        assert_eq!(host.status("cancelled-read"),terminal);
    }

    // These direct mailbox fixtures exercise lifecycle only; they do not prove
    // that an engine rendered a photo or that admission accepted such a row.
    fn apply_request()->wire::Request {
        let sha="a".repeat(64);
        wire::parse_request(&json!({"cmd":"lens_blur","action":"submit","request_id":"apply-fixture","command":{
            "version":2,"action":"apply","request_id":"apply-fixture","session_id":"session-fixture","owner":{
                "document_id":"source-fixture","document_epoch":"document-epoch","document_revision":"12","source":{
                    "sha256":sha,"width":2,"height":2,"orientation":"exif_normalized_once"}},"token":"review-fixture",
            "recipe_sha256":sha,"before_sha256":sha,"after_sha256":sha,"reviewed":true,"return_mode":"new_image","result_source_sha256":"b".repeat(64)}})).unwrap()
    }
    fn row_fixture(epoch:[u8;16],request:wire::Request)->Row {
        Row{epoch,result:wire::pending(&request,"unknown","unknown fixture"),request,terminal:false,dispatched:true,
            cancel_requested:false,ingress_once:false,redeemed:false,retired:false,reserved:wire::SMALL_BYTES,request_bytes:2048,before:None,expires:None}
    }
    fn applied_fixture(req:&wire::Request,outer:&str)->Value {
        let c=req.inner();json!({"event":wire::EVENT,"request_id":outer,"status":"ready","receipt":{
            "version":2,"request_id":c["request_id"],"session_id":c["session_id"],"action":c["action"],"owner":c["owner"],"token":c["token"],
            "phase":"done","outcome_unknown":false,"outcome":"applied","message":"Fixture authoritative return",
            "recipe_sha256":c["recipe_sha256"],"before_sha256":c["before_sha256"],"after_sha256":c["after_sha256"],"return_mode":"new_image",
            "copied_original_document_id":c["owner"]["document_id"],"result_document_id":"distinct-result-fixture","result_revision":"0",
            "result_source_sha256":c["result_source_sha256"],"no_change":false}})
    }
    #[test] fn unknown_write_survives_epoch_end_until_exact_late_terminal() {
        let req=apply_request();let mut host=Mailbox::default();host.rows.push_back(row_fixture([3;16],req.clone()));
        host.end([3;16]);assert!(!host.rows[0].terminal);assert!(!host.rows[0].evictable());
        let mut wrong=applied_fixture(&req,&req.id);wrong["receipt"]["result_source_sha256"]=json!("c".repeat(64));
        assert!(host.observe([3;16],&wrong).is_none());assert!(!host.rows[0].terminal);
        let correct=applied_fixture(&req,&req.id);let settled=host.observe([3;16],&correct).unwrap();
        assert_eq!(settled["request_id"],req.id);assert_eq!(host.rows[0].result,correct);assert!(host.rows[0].terminal);
        host.end([3;16]);assert_eq!(host.rows[0].result,correct);
    }
    #[test] fn receipt_query_settles_exact_original_without_reissuing_it() {
        let req=apply_request();let mut host=Mailbox{epoch:[4;16],supported:true,..Mailbox::default()};host.rows.push_back(row_fixture([4;16],req.clone()));
        let query=wire::parse_request(&json!({"cmd":"lens_blur","action":"receipt","request_id":"query-fixture","command":req.inner()})).unwrap();
        host.begin([4;16],query.clone()).unwrap();host.rows[1].dispatched=true;
        let result=applied_fixture(&req,&query.id);let settled=host.observe([4;16],&result).unwrap();
        assert_eq!(settled["request_id"],req.id);assert_eq!(host.rows[0].result["receipt"],result["receipt"]);
        assert_eq!(host.rows[0].result["request_id"],req.id);assert!(host.rows[0].dispatched && host.rows[0].terminal);
        assert_eq!(host.rows[1].request.envelope,query.envelope);
    }
    #[test] fn completed_unknown_query_is_evictable_but_original_unknown_write_is_not() {
        let req=apply_request();let mut host=Mailbox{epoch:[5;16],supported:true,..Mailbox::default()};host.rows.push_back(row_fixture([5;16],req.clone()));
        let query=wire::parse_request(&json!({"cmd":"lens_blur","action":"receipt","request_id":"query-unknown","command":req.inner()})).unwrap();
        host.begin([5;16],query.clone()).unwrap();host.rows[1].dispatched=true;
        let result=wire::pending(&query,"unknown","No authoritative publication yet");assert!(host.observe([5;16],&result).is_none());
        assert!(host.rows[1].terminal && host.rows[1].evictable());assert!(!host.rows[0].terminal && !host.rows[0].evictable());
    }
    #[test] fn contradictory_query_cannot_override_a_valid_small_terminal() {
        let req=apply_request();let mut host=Mailbox{epoch:[6;16],supported:true,..Mailbox::default()};host.rows.push_back(row_fixture([6;16],req.clone()));
        let genuine=applied_fixture(&req,&req.id);host.observe([6;16],&genuine);
        let query=wire::parse_request(&json!({"cmd":"lens_blur","action":"receipt","request_id":"query-contradictory","command":req.inner()})).unwrap();
        host.begin([6;16],query.clone()).unwrap();host.rows[1].dispatched=true;
        let mut wrong=wire::rejected(&req,"Contradictory rejection");wrong["request_id"]=json!(query.id);
        assert!(host.observe([6;16],&wrong).is_none());assert_eq!(host.rows[0].result,genuine);
        assert_eq!(host.rows[1].result["receipt"]["phase"],"unknown");
    }
    #[test] fn expired_large_read_shrinks_without_rewriting_small_terminal_receipts() {
        let read=wire::parse_request(&json!({"cmd":"lens_blur","action":"current","request_id":"expired-photo"})).unwrap();
        let mut row=row_fixture([7;16],read);row.terminal=true;row.reserved=wire::CONTEXT_BYTES;
        row.result=json!({"event":wire::EVENT,"request_id":"expired-photo","status":"ready","context":{"fixture":"large photo"}});
        row.expires=Some(Instant::now());let mut host=Mailbox::default();host.rows.push_back(row);host.expire(Instant::now());
        assert_eq!(host.rows[0].reserved,wire::SMALL_BYTES);assert!(host.rows[0].retired);assert!(!host.rows[0].imagery());
        let small=host.rows[0].result.clone();host.end([7;16]);host.expire(Instant::now()+SESSION_TTL);assert_eq!(host.rows[0].result,small);
    }

    #[test] fn direct_and_interactive_same_envelope_cannot_replay_once_ingress_was_used() {
        let req=apply_request();let mut host=Mailbox::default();let mut row=row_fixture([8;16],req.clone());row.ingress_once=true;
        host.rows.push_back(row);assert!(host.ingress([8;16],&req.envelope).is_ok());
        assert!(host.ingress([8;16],&req.envelope).is_err());
        host.rows[0].terminal=true;assert!(host.ingress([8;16],&req.envelope).is_err());
    }
    #[test] fn unknown_apply_has_no_generic_state_or_unregistered_read_bypass() {
        let req=apply_request();let mut host=Mailbox::default();host.rows.push_back(row_fixture([9;16],req));
        assert!(host.ingress([9;16],&json!({"cmd":"creative_document","action":"state"})).is_err());
        assert!(host.ingress([9;16],&json!({"cmd":"lens_blur","action":"receipt","request_id":"unregistered"})).is_err());
        assert!(host.ingress([9;16],&json!({"cmd":"shutdown"})).is_ok());
    }
}
