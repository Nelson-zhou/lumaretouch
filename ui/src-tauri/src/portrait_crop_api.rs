// SPDX-License-Identifier: GPL-3.0-or-later
//! Dedicated engine-epoch-owned portrait crop mailbox. Only the real Python
//! host creates receipts/digests; native never invents a cancellation, render,
//! crop history entry or successful commit. AUTHORED / UNRUN.
use std::{collections::{HashMap, VecDeque}, sync::{Arc, Condvar, Mutex, OnceLock}, time::{Duration, Instant}};
use serde_json::{json, Value};
use tauri::State;
use crate::{engine::EngineHandle, portrait_crop_protocol as wire, AppState};

const STORE_BYTES:usize=128*1024*1024;
const MAX_ROWS:usize=512;
const MAX_WRITES:usize=128;
const MAX_IDENTITIES:usize=16_384;
const IDENTITY_BYTES:usize=8*1024*1024;
const SESSION_TTL:Duration=Duration::from_secs(600);
const PREVIEW_TTL:Duration=Duration::from_secs(180);
const WAIT:Duration=Duration::from_secs(4);
struct Identity {epoch:[u8;16],signature:String}
struct Row {
    epoch:[u8;16],request:wire::Request,result:Option<Value>,digest:Option<String>,error:Option<String>,
    terminal:bool,dispatched:bool,ingress_once:bool,cancel_requested:bool,redeemed:bool,released:bool,workspace_reopened:bool,
    reserved:usize,request_bytes:usize,proof:Option<Value>,proof_bytes:usize,expires:Option<Instant>,sequence:u64,reopen_evidence:Option<Arc<Value>>,
}
impl Row {
    fn imagery(&self)->bool {self.result.as_ref().is_some_and(|r|r["current"].is_object() || r["preview"].is_object())}
    fn bytes(&self)->usize {self.reserved.saturating_add(self.request_bytes).saturating_add(self.proof_bytes)}
    fn recovery(&self)->Option<Value> {
        if self.terminal || !self.workspace_reopened {return None;}
        self.reopen_evidence.as_ref().map(|event|json!({"workspace_reopened":true,"authority":"native_verified_project_reopen_v1",
            "original_request":self.request.envelope,"outcome_unknown":true,"authoritative_event":event.as_ref(),
            "message":"工程已明确重新读取；旧请求的历史结果仍未知，不会重发，也不代表旧修改已撤销"}))
    }
    // Write receipts are immutable and never evicted. The bounded write capacity
    // fails closed rather than forgetting an old commit and accepting a replay.
    fn evictable(&self)->bool {(self.request.read() && self.released) || (self.terminal && !self.request.apply() && (!self.imagery() || self.redeemed || self.released))}
}
struct Session {epoch:[u8;16],proof:Value,expires:Instant}
#[derive(Default)]
struct Mailbox {
    epoch:[u8;16],supported:bool,ended:bool,maintenance:bool,rows:VecDeque<Row>,seen:HashMap<String,Identity>,
    identity_bytes:usize,session:Option<Session>,query_counter:u64,reopen_requested:bool,
}
fn store()->&'static (Mutex<Mailbox>,Condvar) {
    static STORE:OnceLock<(Mutex<Mailbox>,Condvar)>=OnceLock::new();
    static REAPER:OnceLock<bool>=OnceLock::new();
    let store=STORE.get_or_init(||(Mutex::new(Mailbox::default()),Condvar::new()));
    REAPER.get_or_init(|| {
        let running=std::thread::Builder::new().name("portrait-crop-leases".into()).spawn(move||loop {
            std::thread::sleep(Duration::from_secs(15));
            if let Ok(mut host)=store.0.lock() {host.expire(Instant::now());store.1.notify_all();}
        }).is_ok();
        if let Ok(mut host)=store.0.lock(){host.maintenance=running;if !running {host.supported=false;host.ended=true;}}
        running
    });
    store
}
fn reservation(action:&str)->usize {if matches!(action,"current"|"preview"|"status"){wire::RESULT_BYTES}else{wire::SMALL_BYTES}}
fn notify() {store().1.notify_all();}
impl Mailbox {
    fn expire(&mut self,now:Instant) {
        if self.session.as_ref().is_some_and(|s|now>=s.expires){self.session=None;}
        for row in &mut self.rows {
            if row.terminal && row.imagery() && row.expires.is_some_and(|end|now>=end) {
                // Drop image leases without forging/replacing a server terminal.
                // The original ID + local signature + pinned digest survive.
                row.result=None;row.proof=None;row.proof_bytes=0;row.reserved=wire::SMALL_BYTES;
                row.released=true;row.expires=None;row.sequence=row.sequence.saturating_add(1);
                row.error=Some("原只读照片租约已释放；原请求不会重跑，请明确重新捕获当前照片".into());
            }
        }
    }
    fn replay(&self,req:&wire::Request)->Result<bool,String> {
        match self.seen.get(&req.id) {
            None=>Ok(false),Some(old) if old.signature==req.signature=>Ok(true),
            Some(_)=>Err("人像裁剪请求身份已绑定其他原始内容；不能重新提交".into()),
        }
    }
    fn row(&self,req:&wire::Request)->Result<&Row,String> {
        if !self.replay(req)? {return Err("没有保留该完整原请求；缺少回执不代表没有执行，不允许重发".into());}
        self.rows.iter().find(|r|r.request.id==req.id && wire::same(&r.request.envelope,&req.envelope))
            .ok_or_else(||"原请求的防重放身份仍保留，但读取回执已释放；不会重发".into())
    }
    fn make_room(&mut self,additional:usize)->Result<(),String> {
        self.expire(Instant::now());
        while self.rows.len()>=MAX_ROWS || self.rows.iter().map(Row::bytes).sum::<usize>().saturating_add(wire::SMALL_BYTES).saturating_add(additional)>STORE_BYTES {
            let Some(index)=self.rows.iter().position(Row::evictable) else{return Err("人像裁剪回执内存已满；原未知写入不会被遗忘，未提交新操作".into());};
            self.rows.remove(index);
        } Ok(())
    }
    fn admission(&self,epoch:[u8;16],req:&wire::Request)->Result<Option<Value>,String> {
        if epoch==[0;16] || self.epoch!=epoch || self.ended || !self.supported {return Err("原引擎不可用或未声明配套人像裁剪协议；未提交".into());}
        if req.action=="status" {
            let original=self.rows.iter().find(|r|r.epoch==epoch && r.request.id==req.envelope["target_request_id"] && r.request.action!="status")
                .ok_or("查询不属于当前原引擎的保留请求；不会猜测另一引擎的结果")?;
            if !original.dispatched {return Err("原请求未进入专用发送入口；没有服务器回执可查询".into());}
            return Ok(None);
        }
        if self.rows.iter().any(|r|r.epoch==epoch && r.request.apply() && !r.terminal && !r.workspace_reopened) {
            return Err("原人像裁剪应用尚未确认；只能查询同一原请求，不能继续修改或重新应用".into());
        }
        if self.rows.iter().any(|r|r.epoch==epoch && r.request.action!="status" && !r.terminal && !r.workspace_reopened) {
            return Err("已有原人像裁剪请求待确认；请等待、查询或请求停止其只读准备".into());
        }
        if matches!(req.action.as_str(),"current"|"capability") {return Ok(None);}
        let current=&self.session.as_ref().filter(|s|s.epoch==epoch && s.proof["session_id"]==req.envelope["session_id"])
            .ok_or("缺少本引擎的有效当前照片捕获；未提交")?.proof;
        if req.action=="preview" && !wire::preview_request(req,current) {return Err("锚点、人脸或完整来源照片不属于保留的当前捕获".into());}
        if req.apply() && !self.rows.iter().any(|r|r.epoch==epoch && r.terminal && !r.redeemed && !r.released
            && r.request.action=="preview" && r.result.as_ref().is_some_and(|v|wire::apply_matches(req,&v["preview"],current))) {
            return Err("缺少本引擎未消费且完整前后图及候选哈希一致的真实预览；未提交".into());
        }
        Ok(Some(current.clone()))
    }
    fn begin(&mut self,epoch:[u8;16],req:wire::Request)->Result<bool,String> {
        self.expire(Instant::now());
        if self.replay(&req)? {return Ok(false);}
        let identity_bytes=req.id.len()+req.signature.len()+64;
        if self.seen.len()>=MAX_IDENTITIES || self.identity_bytes.saturating_add(identity_bytes)>IDENTITY_BYTES {
            return Err("人像裁剪防重放容量已满；不会删除旧身份以重发新请求".into());
        }
        if req.apply() && self.rows.iter().filter(|r|r.request.apply()).count()>=MAX_WRITES {
            return Err("人像裁剪原生写入回执容量已满；未提交新写入".into());
        }
        let proof=self.admission(epoch,&req)?;
        let proof_bytes=proof.as_ref().map_or(Ok(0),|p|wire::size(p,wire::SMALL_BYTES))?;
        let request_bytes=wire::size(&req.envelope,wire::COMMAND_BYTES)?;
        let reserved=reservation(&req.action);
        self.make_room(request_bytes.saturating_add(reserved).saturating_add(proof_bytes))?;
        if req.apply() {
            let current=proof.as_ref().ok_or("缺少应用捕获身份")?;
            let Some(preview)=self.rows.iter_mut().find(|r|r.epoch==epoch && r.terminal && !r.redeemed && !r.released && r.request.action=="preview"
                && r.result.as_ref().is_some_and(|v|wire::apply_matches(&req,&v["preview"],current))) else{return Err("原预览在容量检查前已失效；未提交".into());};
            preview.redeemed=true; // Before any queue/write/flush uncertainty.
        }
        if matches!(req.action.as_str(),"current"|"preview"|"apply"|"cancel") {
            for row in self.rows.iter_mut().filter(|r|r.epoch==epoch && r.request.action=="preview") {row.redeemed=true;}
        }
        if matches!(req.action.as_str(),"current"|"apply"|"cancel") {self.session=None;}
        self.identity_bytes+=identity_bytes;
        self.seen.insert(req.id.clone(),Identity{epoch,signature:req.signature.clone()});
        self.rows.push_back(Row{epoch,request:req,result:None,digest:None,error:None,terminal:false,dispatched:false,ingress_once:false,
            cancel_requested:false,redeemed:false,released:false,workspace_reopened:false,reserved,request_bytes,proof,proof_bytes,expires:None,sequence:0,reopen_evidence:None});
        Ok(true)
    }
    fn error(&mut self,epoch:[u8;16],id:&str,message:&str) {
        if let Some(row)=self.rows.iter_mut().find(|r|r.epoch==epoch && r.request.id==id && !r.terminal) {
            row.error=Some(message.into());row.sequence=row.sequence.saturating_add(1);
        }
    }
    fn end(&mut self,epoch:[u8;16]) {
        if self.session.as_ref().is_some_and(|s|s.epoch==epoch) {self.session=None;}
        for row in self.rows.iter_mut().filter(|r|r.epoch==epoch) {
            if row.terminal && row.imagery() {row.expires=Some(Instant::now());}
            if !row.terminal {
                row.error=Some(if row.request.apply(){"原引擎结束前未确认应用；原结果未知，不能重发或认定未写入"}
                    else{"原引擎已结束；只读计算/会话取消尚无真实终态，不会假装已取消"}.into());
                // Genuine draining stdout may still establish the original
                // terminal. Do not convert process death into no_write=true.
                if row.request.action=="status" {row.terminal=true;row.reserved=wire::SMALL_BYTES;}
                if row.request.read() {row.released=true;row.reserved=wire::SMALL_BYTES;}
                row.sequence=row.sequence.saturating_add(1);
            }
        }
        self.expire(Instant::now());
        if self.epoch==epoch {self.ended=true;self.supported=false;}
    }
    fn ingress(&mut self,epoch:[u8;16],command:&Value)->Result<(),String> {
        let recovery = (command["cmd"]=="project" && matches!(command["action"].as_str(),Some("open"|"create"|"new")))
            || (command["cmd"]=="project_recovery" && matches!(command["action"].as_str(),Some("list"|"inspect"|"status"|"restore")))
            || (command["cmd"]=="session" && command["action"]=="query");
        if (command["cmd"]=="project" && matches!(command["action"].as_str(),Some("open"|"create"|"new")))
            || (command["cmd"]=="project_recovery" && command["action"]=="restore") {self.reopen_requested=true;}
        let mut owned=false;
        if command["cmd"]=="portrait_crop" {
            let row=self.rows.iter_mut().find(|r|r.epoch==epoch && command["request_id"]==r.request.id)
                .ok_or("人像裁剪命令未经专用原生登记，禁止普通/交互旁路提交")?;
            if !row.dispatched || !row.ingress_once || row.terminal || !wire::same(command,&row.request.envelope) {
                return Err("人像裁剪一次性入口已消费或原文变化，不能重发".into());
            }
            row.ingress_once=false;owned=true;
        }
        // The cancellation control lane is private to the verified native API.
        if command["cmd"]=="portrait_crop_cancel" {return Err("只读取消必须使用保留服务器摘要的专用控制入口".into());}
        if self.rows.iter().any(|r|r.epoch==epoch && r.request.apply() && !r.terminal && !r.workspace_reopened)
            && !(owned || recovery || matches!(command["cmd"].as_str(),Some("hello"|"shutdown"))) {
            return Err("人像裁剪原应用尚未确认；只允许查询原请求，暂不能编辑、撤销、保存或导出".into());
        }
        Ok(())
    }
    fn reopen(&mut self,epoch:[u8;16],value:&Value) {
        if !self.reopen_requested || epoch!=self.epoch || self.ended
            || !matches!(value["event"].as_str(),Some("project_opened"|"project_created"))
            || value["open"]!=true || !value["path"].as_str().is_some_and(|v|!v.is_empty() && v.len()<=8192 && !v.contains('\0'))
            || !wire::token(&value["project_id"]) || !value["docs"].is_u64() || !value["dirty"].is_boolean()
            || value["success"]==false || value["outcome_unknown"]==true || value.get("error").is_some()
            || value["requires_reload"]==true || value["requires_readback"]==true {return;}
        let Ok(evidence_bytes)=wire::size(value,32*1024) else{return;};
        self.reopen_requested=false;self.session=None;
        let evidence=Arc::new(value.clone());
        for row in self.rows.iter_mut().filter(|r|r.epoch==epoch) {
            if row.imagery() {row.expires=Some(Instant::now());}
            if !row.terminal && !row.workspace_reopened {
                row.workspace_reopened=true;row.reopen_evidence=Some(evidence.clone());
                row.proof_bytes=row.proof_bytes.saturating_add(evidence_bytes);
                row.error=Some("工程已明确重新读取；旧操作的历史结果仍未知，不会重发，也不代表原修改已撤销".into());
                if row.request.read() {row.released=true;row.reserved=wire::SMALL_BYTES;}
            }
        }
        self.expire(Instant::now());
    }
    fn accept_original(&mut self,epoch:[u8;16],id:&str,value:&Value)->Result<Option<Value>,String> {
        let index=self.rows.iter().position(|r|r.epoch==epoch && r.request.id==id).ok_or("原请求不存在")?;
        let row=&self.rows[index];
        if row.terminal {
            return if row.result.as_ref().is_some_and(|old|wire::same(old,value)) {Ok(None)}else{Err("迟到或查询回执与首个真实终态冲突".into())};
        }
        if !row.dispatched || !wire::valid_result(value,&row.request,row.digest.as_deref(),row.proof.as_ref()) {
            return Err("回执原请求、服务器摘要、完整照片或裁剪身份不匹配，不能确认应用或取消".into());
        }
        let bytes=wire::size(value,reservation(&row.request.action))?;
        let terminal=wire::terminal(value);let action=row.request.action.clone();let retired_workspace=row.workspace_reopened;
        // A late working acknowledgement cannot downgrade server-declared
        // uncertainty. No local status ever manufactures a server phase.
        if !terminal && wire::phase(value)=="working" && row.result.as_ref().is_some_and(|v|wire::phase(v)=="unknown") {return Ok(None);}
        if terminal && action=="current" && wire::phase(value)=="current_ready" && epoch==self.epoch && !self.ended && !retired_workspace {
            let proof=wire::current_proof(&value["current"]);wire::size(&proof,wire::SMALL_BYTES)?;
            self.session=Some(Session{epoch,proof,expires:Instant::now()+SESSION_TTL});
        }
        let image_expiry=if action=="current" {Some(Instant::now()+SESSION_TTL)} else if action=="preview" {
            Some(self.session.as_ref().filter(|s|s.epoch==epoch).map_or(Instant::now(),|s|s.expires.min(Instant::now()+PREVIEW_TTL)))
        } else {None};
        let row=&mut self.rows[index];
        row.digest=Some(value["command_sha256"].as_str().unwrap().into());row.result=Some(value.clone());row.error=None;
        row.sequence=row.sequence.saturating_add(1);row.terminal=terminal;
        if terminal {row.reserved=bytes;row.expires=if row.imagery(){image_expiry}else{None};}
        if terminal && !row.request.apply() {row.proof=None;row.proof_bytes=0;}
        // Keep compact current proof with write receipts: a query can verify
        // historical publication after navigation without pretending live state.
        if terminal && !retired_workspace && matches!(action.as_str(),"apply"|"cancel") {
            if epoch==self.epoch {self.session=None;}
            for r in self.rows.iter_mut().filter(|r|r.epoch==epoch && r.imagery()) {r.expires=Some(Instant::now());}
        }
        if (self.ended || epoch!=self.epoch || retired_workspace) && terminal && matches!(action.as_str(),"current"|"preview") {
            self.rows[index].expires=Some(Instant::now());
        }
        self.expire(Instant::now());
        Ok((terminal && action=="apply").then(||json!({"event":wire::EVENT,"request_id":id,"phase":"done","outcome_unknown":false})))
    }
    fn observe(&mut self,epoch:[u8;16],value:&Value)->Option<Value> {
        self.expire(Instant::now());
        let id=value["request_id"].as_str()?;
        let index=self.rows.iter().position(|r|r.epoch==epoch && r.request.id==id)?;
        if self.rows[index].terminal || !self.rows[index].dispatched {return None;}
        if self.rows[index].request.action!="status" {
            return match self.accept_original(epoch,id,value) {Ok(marker)=>marker,Err(why)=>{self.error(epoch,id,&why);None}};
        }
        let query=&self.rows[index];
        let target=query.request.envelope["target_request_id"].as_str()?.to_owned();
        if !wire::valid_result(value,&query.request,query.digest.as_deref(),None) {
            self.error(epoch,id,"查询包装与其专用身份不一致");self.error(epoch,&target,"查询包装校验失败；原结果仍未确认");return None;
        }
        let marker=if wire::phase(value)=="status" {
            match self.accept_original(epoch,&target,&value["receipt"]) {
                Ok(marker)=>marker,Err(why)=>{self.error(epoch,&target,&why);None},
            }
        } else {self.error(epoch,&target,"服务器未保留可核实的原结果；缺少回执不代表未执行，不会重发");None};
        let query=&mut self.rows[index];query.terminal=true;query.digest=value["command_sha256"].as_str().map(str::to_owned);
        query.reserved=wire::SMALL_BYTES;query.error=None;query.sequence=query.sequence.saturating_add(1);
        // Do not keep a recursive status wrapper or duplicate large images.
        marker
    }
}

pub(crate) fn reset(epoch:[u8;16]) {
    if let Ok(mut host)=store().0.lock(){let old=host.epoch;host.end(old);host.epoch=epoch;host.supported=false;host.ended=false;host.reopen_requested=false;}
    notify();
}
pub(crate) fn ready(epoch:[u8;16],capability:&Value) {
    if let Ok(mut host)=store().0.lock(){if host.epoch==epoch && !host.ended {host.supported=host.maintenance && wire::capability(capability);}}
    notify();
}
pub(crate) fn ended(epoch:[u8;16]) {if let Ok(mut host)=store().0.lock(){host.end(epoch);}notify();}
/// Must run on the original stdout line before ordinary JSON parsing/recovery.
pub(crate) fn observe_line(epoch:[u8;16],line:&str)->Option<Value> {
    if !line.contains(wire::EVENT) {
        if line.contains("project_opened") || line.contains("project_created") {
            if let Ok(value)=wire::unique_json(line,wire::SMALL_BYTES) {
                if let Ok(mut host)=store().0.lock(){host.reopen(epoch,&value);}notify();
            }
        }
        return None;
    }
    let value=match wire::unique_json(line,wire::RESULT_BYTES) {
        Ok(value)=>value,Err(_)=>{
            if let Ok(mut host)=store().0.lock(){for row in host.rows.iter_mut().filter(|r|r.epoch==epoch && r.dispatched && !r.terminal) {
                row.error=Some("人像裁剪原始回执含重复字段、超限或非法 JSON；不能确认结果".into());row.sequence=row.sequence.saturating_add(1);
            }} notify();return None;
        }
    };
    let marker=store().0.lock().ok()?.observe(epoch,&value);notify();marker
}
/// Integration hook deliberately does not trust already-parsed event content.
/// The required raw observe_line hook performs duplicate-key-safe reopening.
pub(crate) fn project_reopened(_epoch:[u8;16],_value:&Value) {notify();}
pub(crate) fn guards_result(epoch:[u8;16],id:&str)->bool {
    store().0.lock().map(|h|h.seen.get(id).is_some_and(|s|s.epoch==epoch)).unwrap_or(true)
}
pub(crate) fn read_only(command:&Value)->bool {
    command["cmd"]=="portrait_crop" && matches!(command["action"].as_str(),Some("capability"|"current"|"preview"|"status"|"cancel"))
}
pub(crate) fn blocks_mutation(epoch:[u8;16],command:&Value)->Result<(),String> {
    store().0.lock().map_err(|_|"人像裁剪原请求屏障锁不可用")?.ingress(epoch,command)
}
/// AppState routes apply here after normal edit-intent guards. The epoch tag is
/// native-only; stdin receives exactly the retained original_request envelope.
pub(crate) fn enqueue(handle:&EngineHandle,mut command:Value)->Result<(),String> {
    let epoch=command.as_object_mut().ok_or("人像裁剪信封无效")?.remove("host_epoch").ok_or("缺少原人像裁剪引擎身份")?;
    if epoch.as_str()!=Some(crate::frame_identity::hex(handle.epoch()).as_str()) {return Err("引擎已变化；未向新引擎重发原人像裁剪请求".into());}
    let id=command["request_id"].as_str().ok_or("人像裁剪请求身份缺失")?.to_owned();
    {
        let mut host=store().0.lock().map_err(|_|"人像裁剪回执锁不可用")?;
        if host.epoch!=handle.epoch() || host.ended || !host.supported || !handle.is_alive(){return Err("原人像裁剪引擎不可用；未重新提交".into());}
        let row=host.rows.iter_mut().find(|r|r.epoch==handle.epoch() && r.request.id==id).ok_or("人像裁剪命令没有专用原生登记")?;
        if row.terminal || row.dispatched || !wire::same(&command,&row.request.envelope) {return Err("原人像裁剪请求已消费或内容变化，不会重发".into());}
        row.dispatched=true;row.ingress_once=true;
    }
    let result=handle.send(command);
    // Every attempt consumes ingress, including a cross-domain guard refusal.
    if let Ok(mut host)=store().0.lock(){if let Some(row)=host.rows.iter_mut().find(|r|r.epoch==handle.epoch() && r.request.id==id){row.ingress_once=false;}}
    result
}
fn wait_receipt(original:&wire::Request,after:Option<u64>)->Result<Value,String> {
    let deadline=Instant::now()+WAIT;
    let (lock,changed)=store();let mut host=lock.lock().map_err(|_|"人像裁剪回执锁不可用")?;
    loop {
        host.expire(Instant::now());
        let row=host.row(original)?;
        if let Some(recovery)=row.recovery(){return Ok(recovery);}
        if let Some(why)=&row.error {return Err(why.clone());}
        if let Some(result)=&row.result {
            if row.terminal || after.map_or(true,|sequence|row.sequence>sequence) || Instant::now()>=deadline {return Ok(result.clone());}
        }
        if Instant::now()>=deadline {return Err("尚未收到含服务器摘要的真实原请求回执；结果未确认，只能查询，不能重发".into());}
        let remaining=deadline.saturating_duration_since(Instant::now());
        host=changed.wait_timeout(host,remaining).map_err(|_|"人像裁剪等待锁不可用")?.0;
    }
}
fn send(state:&Arc<AppState>,request:Value)->Result<Value,String> {
    let req=wire::parse_request(&request)?;
    if req.action=="status" {return Err("查询必须使用 portrait_crop_status 并提供完整原请求，不能任意查询身份".into());}
    {let host=store().0.lock().map_err(|_|"人像裁剪回执锁不可用")?;if host.replay(&req)? {drop(host);return wait_receipt(&req,None);}}
    let handle=state.engine.lock().map_err(|_|"引擎锁不可用")?.clone().ok_or("引擎未运行；未提交")?;
    let epoch=handle.epoch();
    let dispatch=store().0.lock().map_err(|_|"人像裁剪回执锁不可用")?.begin(epoch,req.clone())?;
    if dispatch {
        let mut envelope=request;envelope["host_epoch"]=json!(crate::frame_identity::hex(epoch));
        let sent=if req.apply(){state.send_to_engine(envelope)}else{enqueue(&handle,envelope)};
        if let Err(error)=sent {
            let why=format!("原人像裁剪发送未获确认：{}；不会自动重发",error.chars().take(512).collect::<String>());
            store().0.lock().map_err(|_|"人像裁剪回执锁不可用")?.error(epoch,&req.id,&why);notify();
        }
    }
    wait_receipt(&req,None)
}
fn status(state:&Arc<AppState>,original:Value)->Result<Value,String> {
    let req=wire::parse_request(&original)?;
    if req.action=="status" {return Err("只能查询实际原请求，不能递归查询包装".into());}
    let (epoch,sequence)={
        let mut host=store().0.lock().map_err(|_|"人像裁剪回执锁不可用")?;host.expire(Instant::now());
        let row=host.row(&req)?;
        if let Some(recovery)=row.recovery(){return Ok(recovery);}
        if row.terminal {if let Some(result)=&row.result{return Ok(result.clone());}return Err(row.error.clone().unwrap_or_else(||"原只读回执已释放，不能重发".into()));}
        (row.epoch,row.sequence)
    };
    let handle=state.engine.lock().map_err(|_|"引擎锁不可用")?.clone().filter(|h|h.is_alive() && h.epoch()==epoch)
        .ok_or("原引擎已结束或变化；不能向其他引擎猜测结果或重发原请求")?;
    let query={
        let mut host=store().0.lock().map_err(|_|"人像裁剪回执锁不可用")?;
        // Re-check after acquiring engine ownership. A concurrent terminal wins.
        if host.row(&req)?.terminal {drop(host);return wait_receipt(&req,None);}
        if host.rows.iter().any(|r|r.epoch==epoch && r.request.action=="status" && !r.terminal && r.request.envelope["target_request_id"]==req.id) {None}
        else {
            host.query_counter=host.query_counter.checked_add(1).ok_or("人像裁剪查询身份计数已满")?;
            let id=format!("portrait-crop-status:{}:{}",crate::frame_identity::hex(epoch),host.query_counter);
            let value=json!({"cmd":"portrait_crop","action":"status","request_id":id,"target_request_id":req.id});
            let query=wire::parse_request(&value)?;host.begin(epoch,query)?;
            // A fresh query may recover a prior transport/validation error. This
            // clears only a local notice, never a genuine server outcome.
            if let Some(row)=host.rows.iter_mut().find(|r|r.epoch==epoch && r.request.id==req.id) {row.error=None;}
            Some(value)
        }
    };
    if let Some(mut query)=query {
        let query_id=query["request_id"].as_str().unwrap().to_owned();query["host_epoch"]=json!(crate::frame_identity::hex(epoch));
        if let Err(error)=enqueue(&handle,query) {
            let why=format!("原请求查询发送未获确认：{}；原应用没有被重发",error.chars().take(512).collect::<String>());
            let mut host=store().0.lock().map_err(|_|"人像裁剪回执锁不可用")?;host.error(epoch,&query_id,&why);host.error(epoch,&req.id,&why);notify();
        }
    }
    wait_receipt(&req,Some(sequence))
}
#[tauri::command]
pub(crate) async fn portrait_crop(state:State<'_,Arc<AppState>>,request:Value)->Result<Value,String> {
    let state=state.inner().clone();tauri::async_runtime::spawn_blocking(move||send(&state,request)).await.map_err(|e|e.to_string())?
}
#[tauri::command]
pub(crate) async fn portrait_crop_status(state:State<'_,Arc<AppState>>,original:Value)->Result<Value,String> {
    let state=state.inner().clone();tauri::async_runtime::spawn_blocking(move||status(&state,original)).await.map_err(|e|e.to_string())?
}
#[tauri::command(rename_all = "snake_case")]
pub(crate) fn portrait_crop_cancel_read(state:State<'_,Arc<AppState>>,original:Value,command_sha256:String)->Result<Value,String> {
    let req=wire::parse_request(&original)?;
    if !req.read() || !wire::hash(&json!(command_sha256)) {return Err("取消只支持真实 current/preview 读取及其服务器摘要，不能取消 apply".into());}
    let handle=state.engine.lock().map_err(|_|"引擎锁不可用")?.clone().filter(|h|h.is_alive()).ok_or("原引擎不可用，不能确认读取已停止")?;
    let epoch=handle.epoch();
    {
        let mut host=store().0.lock().map_err(|_|"人像裁剪回执锁不可用")?;
        let retained=host.row(&req)?;
        if retained.epoch!=epoch || retained.digest.as_deref()!=Some(command_sha256.as_str()) {return Err("读取不属于原引擎或取消摘要不是原服务器回执摘要".into());}
        if retained.terminal {return Ok(json!({"requested":false,"request_id":req.id,"message":"原请求已有终态，请查询原回执"}));}
        if !retained.dispatched {return Err("原读取尚未进入专用发送入口，未发送脱离原工作的取消".into());}
        if retained.cancel_requested {return Ok(json!({"requested":true,"request_id":req.id,"message":"已请求停止原读取，仍须等待原请求真实终态"}));}
        let row=host.rows.iter_mut().find(|r|r.epoch==epoch && r.request.id==req.id).ok_or("原读取不存在")?;
        row.cancel_requested=true; // Before uncertain control-line write/flush.
    }
    if let Err(error)=handle.cancel_portrait_crop_read(&req.id,&command_sha256) {
        store().0.lock().map_err(|_|"人像裁剪回执锁不可用")?.error(epoch,&req.id,"只读取消发送未获确认；不能假装已经取消，也不会重发取消");notify();return Err(error);
    }
    Ok(json!({"requested":true,"request_id":req.id,"message":"已请求停止原读取，必须等待原请求实际取消或其他终态"}))
}

#[cfg(test)]
mod mailbox_unrun {
    //! AUTHORED / UNRUN. Lifecycle fixtures bypass admission deliberately and
    //! cannot prove renderer, photographic review, detector or history success.
    use super::*;
    fn req(action:&str)->wire::Request {
        if action=="apply" {
            wire::parse_request(&json!({"cmd":"portrait_crop","action":"apply","request_id":"apply-fixture",
                "session_id":"session-fixture","capture_sha256":"a".repeat(64),"preview_request_id":"preview-fixture",
                "preview_token":"preview-token","candidate_sha256":"b".repeat(64),"before_image_sha256":"c".repeat(64),
                "after_image_sha256":"d".repeat(64),"review":"full_before_after_confirmed"})).unwrap()
        } else {wire::parse_request(&json!({"cmd":"portrait_crop","action":action,"request_id":format!("{action}-fixture")})).unwrap()}
    }
    fn fixture_row(request:wire::Request)->Row {
        Row{epoch:[1;16],request,result:None,digest:None,error:None,terminal:false,dispatched:true,ingress_once:false,
            cancel_requested:false,redeemed:false,released:false,workspace_reopened:false,reserved:wire::SMALL_BYTES,request_bytes:2048,
            proof:Some(json!({"binding":{"document_id":"document-fixture","revision":"12","state_sha256":"e".repeat(64)}})),
            proof_bytes:256,expires:None,sequence:0,reopen_evidence:None}
    }
    fn receipt(req:&wire::Request,phase:&str)->Value {
        json!({"event":wire::EVENT,"version":1,"request_id":req.id,"action":req.action,"command_sha256":"f".repeat(64),
            "original_request":req.envelope,"phase":phase})
    }
    fn committed(req:&wire::Request)->Value {
        let mut v=receipt(req,"committed");v["result"]=json!({"status":"applied","document_id":"document-fixture","revision":"13"});
        v["preview_token"]=req.envelope["preview_token"].clone();v["candidate_sha256"]=req.envelope["candidate_sha256"].clone();
        v["original_request_id"]=json!(req.id);v["recovered"]=json!(false);v
    }
    fn host(request:wire::Request)->Mailbox {
        let mut host=Mailbox{epoch:[1;16],supported:true,..Mailbox::default()};
        host.seen.insert(request.id.clone(),Identity{epoch:[1;16],signature:request.signature.clone()});
        host.rows.push_back(fixture_row(request));host
    }
    #[test] fn one_shot_ingress_has_no_generic_or_interactive_replay() {
        let request=req("apply");let mut host=host(request.clone());host.rows[0].ingress_once=true;
        assert!(host.ingress([1;16],&request.envelope).is_ok());assert!(host.ingress([1;16],&request.envelope).is_err());
        assert!(host.ingress([1;16],&json!({"cmd":"history","action":"undo"})).is_err());
        assert!(host.ingress([1;16],&json!({"cmd":"portrait_crop_cancel","request_id":request.id,"command_sha256":"f".repeat(64)})).is_err());
    }
    #[test] fn unknown_apply_survives_epoch_end_and_only_exact_late_terminal_settles() {
        let request=req("apply");let mut host=host(request.clone());host.end([1;16]);
        assert!(!host.rows[0].terminal);assert!(!host.rows[0].evictable());assert!(host.rows[0].result.is_none());
        let mut wrong=committed(&request);wrong["result"]["revision"]=json!("12");assert!(host.observe([1;16],&wrong).is_none());assert!(!host.rows[0].terminal);
        let correct=committed(&request);assert!(host.observe([1;16],&correct).is_some());assert_eq!(host.rows[0].result,Some(correct.clone()));
        let mut contradiction=receipt(&request,"rejected");contradiction["no_write"]=json!(true);host.observe([1;16],&contradiction);
        assert_eq!(host.rows[0].result,Some(correct));
    }
    #[test] fn server_digest_pins_cancellation_identity_not_local_json_signature() {
        let request=req("current");let mut host=host(request.clone());let mut working=receipt(&request,"working");working["no_write"]=json!(true);
        host.observe([1;16],&working);assert_eq!(host.rows[0].digest,Some("f".repeat(64)));assert_ne!(host.rows[0].digest,Some(request.signature.clone()));
        let mut terminal=receipt(&request,"cancelled");terminal["no_write"]=json!(true);terminal["command_sha256"]=json!("a".repeat(64));
        host.observe([1;16],&terminal);assert!(!host.rows[0].terminal);
        terminal["command_sha256"]=json!("f".repeat(64));host.observe([1;16],&terminal);assert!(host.rows[0].terminal);
        host.end([1;16]);assert_eq!(host.rows[0].result,Some(terminal));
    }
    #[test] fn exact_status_wrapper_settles_original_without_resubmitting_apply() {
        let original=req("apply");let mut host=host(original.clone());
        let query=wire::parse_request(&json!({"cmd":"portrait_crop","action":"status","request_id":"status-fixture","target_request_id":original.id})).unwrap();
        host.begin([1;16],query.clone()).unwrap();host.rows[1].dispatched=true;
        let mut response=receipt(&query,"status");response["receipt"]=committed(&original);
        let marker=host.observe([1;16],&response).unwrap();assert_eq!(marker["request_id"],original.id);
        assert!(host.rows[0].terminal && host.rows[1].terminal);assert!(host.rows[1].result.is_none());assert_eq!(host.rows[0].request.envelope,original.envelope);
    }
    #[test] fn tombstones_survive_released_read_eviction() {
        let original=req("current");let mut host=host(original.clone());host.end([1;16]);assert!(host.rows[0].evictable());host.rows.clear();
        assert!(host.replay(&original).unwrap());assert!(!host.begin([2;16],original.clone()).unwrap());assert!(host.row(&original).is_err());
        let mut conflict=original.envelope;conflict["action"]=json!("capability");assert!(host.replay(&wire::parse_request(&conflict).unwrap()).is_err());
    }
    #[test] fn authoritative_reopen_retires_only_workspace_fence_not_historical_outcome() {
        let original=req("apply");let mut host=host(original.clone());
        let opened=json!({"event":"project_opened","open":true,"path":"/fixture/project.lrt","project_id":"project-fixture","docs":1,"dirty":false});
        host.reopen([1;16],&opened);assert!(!host.rows[0].workspace_reopened);
        host.ingress([1;16],&json!({"cmd":"project","action":"open","path":"/fixture/project.lrt"})).unwrap();
        let mut malformed=opened.clone();malformed["requires_reload"]=json!(true);host.reopen([1;16],&malformed);assert!(!host.rows[0].workspace_reopened);
        host.reopen([2;16],&opened);assert!(!host.rows[0].workspace_reopened);
        host.reopen([1;16],&opened);assert!(!host.rows[0].terminal);let recovery=host.rows[0].recovery().unwrap();
        assert_eq!(recovery["original_request"],original.envelope);assert_eq!(recovery["authoritative_event"],opened);assert_eq!(recovery["outcome_unknown"],true);
        assert!(recovery.get("phase").is_none());assert!(recovery.get("command_sha256").is_none());
        assert!(host.ingress([1;16],&json!({"cmd":"history","action":"undo"})).is_ok());assert!(host.replay(&original).unwrap());
        host.session=Some(Session{epoch:[1;16],proof:json!({"session_id":"new-workspace-session"}),expires:Instant::now()+SESSION_TTL});
        assert!(host.observe([1;16],&committed(&original)).is_some());assert!(host.rows[0].recovery().is_none());
        assert_eq!(host.session.as_ref().unwrap().proof["session_id"],"new-workspace-session");
    }
}
