//! Host-owned inspection generations and one-worker/one-pull lifecycle.
//! This module does no I/O. Only the owning host may turn Actions into commands.
#[path = "inspection_wire.rs"]
pub mod wire;
use wire::refinement::{Budget, Gate, Request, Roi, Ticket};
use std::path::PathBuf;

pub const SOURCE_PIXELS:u64 = 64*1024*1024;
pub const PATCH_PIXELS:u64 = 16*1024*1024;
pub const ASSET_BYTES:u64 = 512*1024*1024;
pub const ADDRESS_BYTES:u64 = 8*1024*1024*1024;
pub fn budget()->Budget { Budget{source_pixels:SOURCE_PIXELS,patch_pixels:PATCH_PIXELS,
    // Admission accounts for the worker address-space cap plus known extra host
    // copies, not a claim about total application RSS or physical machine memory.
    live_bytes:10*1024*1024*1024} }

#[derive(Debug)]
pub enum Action { Start(Request), Cancel(u64), Release(u64) }

pub struct Host {
    pub epoch:[u8;16],
    pub available:bool,
    pub phase:&'static str,
    pub error:Option<String>,
    pub active:Option<Request>,
    pub desired_id:Option<u64>,
    serial:u64,
    version:u64,
    gate:Gate,
    path:Option<PathBuf>,
    reading:Option<([u8;16],Ticket)>,
    pub published:Option<([u8;16],Ticket)>,
    ended:bool,
    broken:bool,
}
impl Default for Host {
    fn default()->Self {Self{epoch:[0;16],available:false,phase:"idle",error:None,
        active:None,desired_id:None,serial:0,version:0,gate:Gate::default(),path:None,reading:None,published:None,ended:false,broken:false}}
}
impl Host {
    pub fn generation(&self)->u64{self.version}
    pub fn reset(&mut self,epoch:[u8;16])->Result<(),String>{
        if epoch==[0;16]{return Err("inspection engine epoch is empty".into());}
        let reading=self.reading;let published=self.published;
        *self=Self{epoch,reading,published,..Self::default()};Ok(())
    }
    pub fn invalidate(&mut self){
        self.version=self.version.saturating_add(1);
        self.desired_id=None;self.gate.invalidate();self.path=None;
        self.phase=if self.active.is_some(){"cancelling"}else{"idle"};
    }
    pub fn engine_ended(&mut self,epoch:[u8;16]){
        if epoch!=self.epoch{return;}
        self.invalidate();self.available=false;self.ended=true;
        if let Some(r)=self.active.take(){let _=self.gate.fail(r.ticket);}
        self.path=None;self.phase="failed";
        self.error=Some("inspection engine exited".into());
    }
    pub fn ready(&mut self,epoch:[u8;16],supported:bool){
        if epoch==self.epoch && !self.ended && !self.broken{self.available=supported;}
    }
    fn begin_next(&mut self)->Option<Action>{
        let r=self.gate.start_next()?;
        self.active=Some(r.clone());self.path=None;
        self.phase="copying";self.error=None;
        Some(Action::Start(r))
    }
    pub fn submit(&mut self,source:(u64,u64),canvas:(u64,u64),roi:Roi)->Result<(Ticket,Vec<Action>),String>{
        if !self.available || self.epoch==[0;16]{return Err("engine lacks inspection protocol v1".into());}
        let id=self.serial.checked_add(1).ok_or("inspection request IDs exhausted")?;
        if [source.0,source.1,canvas.0,canvas.1,roi.x,roi.y,roi.width,roi.height].iter().any(|v|*v>u32::MAX as u64){
            return Err("inspection dimensions exceed wire representation".into());
        }
        let payload=roi.width.checked_mul(roi.height).and_then(|n|n.checked_mul(4)).ok_or("inspection pixel overflow")?;
        if payload>PATCH_PIXELS*4{return Err("inspection patch exceeds host admission".into());}
        let ticket=Ticket{id,document:self.version,source_generation:self.version,recipe:self.version,viewport:id};
        let r=Request{ticket,source_width:source.0,source_height:source.1,canvas_width:canvas.0,canvas_height:canvas.1,roi,
            estimated_live_bytes:ADDRESS_BYTES+ASSET_BYTES+payload.checked_mul(3).ok_or("inspection copy overflow")?+32*1024*1024};
        self.gate.submit(r,&budget())?;
        self.serial=id;self.desired_id=Some(id);self.path=None;self.error=None;
        let actions=if let Some(old)=self.active.as_ref(){
            self.phase="cancelling";vec![Action::Cancel(old.ticket.id)]
        }else{self.begin_next().into_iter().collect()};
        Ok((ticket,actions))
    }
    pub fn cancel(&mut self,id:u64)->Result<Vec<Action>,String>{
        if self.desired_id!=Some(id){return Err("inspection cancellation is stale".into());}
        self.invalidate();
        Ok(self.active.as_ref().map(|r|Action::Cancel(r.ticket.id)).into_iter().collect())
    }
    fn retire(&mut self,ticket:Ticket,release:bool)->Result<Vec<Action>,String>{
        self.gate.fail(ticket)?;self.active=None;self.path=None;
        let mut actions=Vec::new();
        if release{actions.push(Action::Release(ticket.id));}
        if let Some(next)=self.begin_next(){actions.push(next);}
        Ok(actions)
    }
    pub fn event(&mut self,epoch:[u8;16],ticket:Ticket,phase:&str,path:Option<PathBuf>,error:Option<String>)->Result<Vec<Action>,String>{
        if epoch!=self.epoch || self.active.as_ref().map(|r|r.ticket)!=Some(ticket){return Ok(Vec::new());}
        match phase {
            "ready"=>{
                if self.gate.cancelled(ticket){return self.retire(ticket,true);}
                self.path=Some(path.ok_or("inspection ready event lacks result path")?);
                self.phase="ready";self.error=None;
            }
            "failed"|"cancelled"|"released"=>{
                self.phase=if self.broken || phase=="failed"{"failed"}else{"cancelled"};
                if !self.broken{self.error=error;}
                return self.retire(ticket,false);
            }
            "copying"|"spooling"|"rendering"|"cancelling"=>{
                if !self.gate.cancelled(ticket){
                    self.phase=match phase{"copying"=>"copying","spooling"=>"spooling","rendering"=>"rendering",_=>"cancelling"};
                }
            }
            _=>return Err("unknown inspection worker phase".into()),
        }
        Ok(Vec::new())
    }
    pub fn begin_pull(&mut self,id:u64)->Result<([u8;16],Request,PathBuf),String>{
        let r=self.active.as_ref().ok_or("no inspection result lease")?;
        if r.ticket.id!=id || self.desired_id!=Some(id) || self.phase!="ready" || self.reading.is_some() || self.published.is_some(){
            return Err("inspection result is stale, unavailable or already being read".into());
        }
        let path=self.path.clone().ok_or("inspection path unavailable")?;
        self.reading=Some((self.epoch,r.ticket));Ok((self.epoch,r.clone(),path))
    }
    pub fn finish_pull(&mut self,epoch:[u8;16],ticket:Ticket,valid:bool)->Result<(bool,Vec<Action>),String>{
        if self.reading!=Some((epoch,ticket)){return Ok((false,Vec::new()));}
        self.reading=None;
        if epoch!=self.epoch || self.active.as_ref().map(|r|r.ticket)!=Some(ticket){return Ok((false,Vec::new()));}
        let r=self.active.as_ref().unwrap();
        let accepted=if valid{self.gate.finish(ticket,r.roi,r.rgba_bytes()?)?}else{self.gate.fail(ticket)?;false};
        self.active=None;self.path=None;
        if accepted{self.published=Some((epoch,ticket));}
        self.phase=if accepted{"delivered"}else{"failed"};
        let mut actions=vec![Action::Release(ticket.id)];
        if let Some(next)=self.begin_next(){actions.push(next);}
        Ok((accepted,actions))
    }
    pub fn release_publication(&mut self,epoch:[u8;16],id:u64)->Result<(),String>{
        if self.published.map(|(e,t)|(e,t.id))!=Some((epoch,id)){return Err("inspection release is stale".into());}
        self.published=None;Ok(())
    }
    pub fn send_failed(&mut self,action:&Action,reason:String){
        self.available=false;self.broken=true;
        self.invalidate();
        if let Action::Start(request)=action{
            if self.active.as_ref().map(|r|r.ticket)==Some(request.ticket){
                let _=self.gate.fail(request.ticket);self.active=None;
            }
        }
        self.phase="failed";self.error=Some(reason);
    }
    pub fn protocol_failure(&mut self,reason:String)->Vec<Action>{
        self.available=false;self.broken=true;self.invalidate();self.phase="failed";self.error=Some(reason);
        self.active.as_ref().map(|r|Action::Cancel(r.ticket.id)).into_iter().collect()
    }
}

#[cfg(test)]
mod tests{
    use super::*;
    fn host()->Host{let mut h=Host::default();h.reset([7;16]).unwrap();h.available=true;h}
    fn roi()->Roi{Roi{x:0,y:0,width:10,height:10}}
    fn submit(h:&mut Host)->u64{h.submit((100,100),(100,100),roi()).unwrap().0.id}
    fn ready(h:&mut Host){let r=h.active.as_ref().unwrap().clone();h.event(h.epoch,r.ticket,"ready",Some("/private/result.lrif".into()),None).unwrap();}
    #[test] fn only_latest_pending_starts_after_old_worker_terminal(){
        let mut h=host();let a=submit(&mut h);let old=h.active.as_ref().unwrap().ticket;
        submit(&mut h);let c=submit(&mut h);assert_eq!(h.active.as_ref().unwrap().ticket.id,a);
        let actions=h.event(h.epoch,old,"cancelled",None,None).unwrap();
        assert!(matches!(&actions[..],[Action::Start(r)] if r.ticket.id==c));
        assert_eq!(h.active.as_ref().unwrap().ticket.id,c);
    }
    #[test] fn edit_invalidates_an_inflight_pull(){
        let mut h=host();let id=submit(&mut h);ready(&mut h);
        let (epoch,r,_)=h.begin_pull(id).unwrap();h.invalidate();
        assert!(!h.finish_pull(epoch,r.ticket,true).unwrap().0);
    }
    #[test] fn repeated_pull_cannot_duplicate_payload_lease(){
        let mut h=host();let id=submit(&mut h);ready(&mut h);
        let (epoch,r,_)=h.begin_pull(id).unwrap();assert!(h.begin_pull(id).is_err());
        assert!(h.finish_pull(epoch,r.ticket,true).unwrap().0);assert!(h.begin_pull(id).is_err());
    }
    #[test] fn old_epoch_eof_cannot_clear_new_engine(){
        let mut h=host();h.reset([8;16]).unwrap();h.available=true;submit(&mut h);
        h.engine_ended([7;16]);assert!(h.active.is_some() && h.available);
    }
    #[test] fn stale_ready_does_not_replace_new_request(){
        let mut h=host();submit(&mut h);let old=h.active.as_ref().unwrap().ticket;
        let id=submit(&mut h);let actions=h.event(h.epoch,old,"ready",Some("/private/old".into()),None).unwrap();
        assert!(matches!(&actions[..],[Action::Release(_),Action::Start(r)] if r.ticket.id==id));
        assert!(h.begin_pull(id).is_err());
    }
    #[test] fn read_completion_after_cancelled_worker_does_not_free_new_worker(){
        let mut h=host();let a=submit(&mut h);ready(&mut h);let (epoch,r,_)=h.begin_pull(a).unwrap();
        let b=submit(&mut h);h.event(epoch,r.ticket,"cancelled",None,None).unwrap();
        assert!(!h.finish_pull(epoch,r.ticket,true).unwrap().0);
        assert_eq!(h.active.as_ref().unwrap().ticket.id,b);
    }
    #[test] fn cancelled_read_keeps_single_global_read_lease(){
        let mut h=host();let a=submit(&mut h);ready(&mut h);let (epoch,r,_)=h.begin_pull(a).unwrap();
        let b=submit(&mut h);h.event(epoch,r.ticket,"cancelled",None,None).unwrap();ready(&mut h);
        assert!(h.begin_pull(b).is_err());h.finish_pull(epoch,r.ticket,true).unwrap();
        assert!(h.begin_pull(b).is_ok());
    }
    #[test] fn publication_requires_explicit_ack_before_another_pull(){
        let mut h=host();let a=submit(&mut h);ready(&mut h);let (epoch,r,_)=h.begin_pull(a).unwrap();
        h.finish_pull(epoch,r.ticket,true).unwrap();let b=submit(&mut h);ready(&mut h);
        assert!(h.begin_pull(b).is_err());h.release_publication(epoch,a).unwrap();assert!(h.begin_pull(b).is_ok());
    }
    #[test] fn cancel_send_failure_does_not_free_running_worker(){
        let mut h=host();let a=submit(&mut h);h.send_failed(&Action::Cancel(a),"closed".into());
        assert_eq!(h.active.as_ref().unwrap().ticket.id,a);assert!(!h.available);
    }
    #[test] fn huge_dimensions_fail_without_arithmetic_panic(){
        let mut h=host();assert!(h.submit((100,100),(u64::MAX,100),Roi{x:0,y:0,width:u64::MAX/16,height:1}).is_err());
    }
    #[test] fn malformed_ready_cancels_without_losing_worker_lease(){
        let mut h=host();let a=submit(&mut h);let t=h.active.as_ref().unwrap().ticket;
        assert!(h.event(h.epoch,t,"ready",None,None).is_err());
        assert!(matches!(&h.protocol_failure("bad packet".into())[..],[Action::Cancel(id)] if *id==a));
        assert!(h.active.is_some());h.event(h.epoch,t,"cancelled",None,None).unwrap();
        assert!(h.active.is_none());assert_eq!(h.error.as_deref(),Some("bad packet"));
        h.ready(h.epoch,true);assert!(!h.available);
    }
}
