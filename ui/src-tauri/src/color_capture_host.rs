//! One identified capture, independently owned from frame transport and editor state.
use serde_json::{json,Value};
use crate::capture_wire::Identity;

pub fn token(value:&str)->Result<u64,String>{
    let n=value.parse::<u64>().map_err(|_|"invalid capture integer identity")?;
    if n==0||n.to_string()!=value{return Err("noncanonical capture integer identity".into());}Ok(n)
}
pub fn id16(value:&str)->Result<[u8;16],String>{
    if value.len()!=32||!value.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)) {
        return Err("invalid capture hex identity".into());
    }
    let mut id=[0;16];for i in 0..16{id[i]=u8::from_str_radix(&value[i*2..i*2+2],16).map_err(|_|"invalid capture hex identity")?;}
    if id==[0;16]{return Err("zero capture identity".into());}Ok(id)
}
#[derive(Clone)]
struct Pending {capture:String,document:String,ticket:u64,revision:usize}
#[derive(Clone,Copy,PartialEq,Eq)]
enum Phase {Ready,Copied,Eligible}
#[derive(Clone)]
struct Ready {identity:Identity,descriptor:Value,phase:Phase}
struct SamplePending {request:String,ticket:u64,region:[u32;4]}
#[derive(Default)]
pub struct CaptureHost {
    epoch:[u8;16],counter:u64,pending:Option<Pending>,ready:Option<Ready>,
    sample_pending:Option<SamplePending>,sample:Option<Value>,error:Option<(String,String,String)>,
}
impl CaptureHost {
    pub fn reset(&mut self,epoch:[u8;16]){self.invalidate();self.epoch=epoch;}
    pub fn invalidate(&mut self){self.pending=None;self.ready=None;self.sample_pending=None;self.sample=None;self.error=None;}
    pub fn engine_ended(&mut self,epoch:[u8;16]){if epoch==self.epoch{self.invalidate();self.epoch=[0;16];}}
    fn next(&mut self)->Result<u64,String>{self.counter=self.counter.checked_add(1).ok_or("capture ticket exhausted")?;Ok(self.counter)}
    pub fn begin(&mut self,capture:String,document:String,revision:usize)->Result<String,String>{
        id16(&capture)?;token(&document)?;
        if self.epoch==[0;16]{return Err("capture engine is unavailable".into());}
        let ticket=self.next()?;self.invalidate();
        self.pending=Some(Pending{capture,document,ticket,revision});Ok(ticket.to_string())
    }
    pub fn armed_event(&mut self,epoch:[u8;16],event:&Value,revision:usize){
        if epoch!=self.epoch||event["action"]!="arm"{return;}
        let Some(p)=self.pending.clone() else{return};
        if event["capture_id"]!=p.capture||event["ticket"]!=p.ticket.to_string(){return;}
        self.pending=None;
        let result=(||->Result<Ready,String>{
            if event["success"]!=true{return Err(event["error"].as_str().unwrap_or("capture failed").chars().take(2000).collect());}
            if revision!=p.revision{return Err("document changed while arming capture; retry".into());}
            let d=&event["descriptor"];
            if d["version"]!=1||d["capture_id"]!=p.capture||d["ticket"]!=p.ticket.to_string()||d["document_id"]!=p.document||
                d["domain"]!="proxy-output"||d["quality"]!="proxy-float-output"||d["profile"]!="working-srgb" {
                return Err("capture descriptor contract mismatch".into());
            }
            let scalar=|key:&str|token(d[key].as_str().ok_or("missing capture integer")?);
            let dimension=|key:&str|->Result<u32,String>{u32::try_from(d[key].as_u64().ok_or("missing capture dimension")?).map_err(|_|"capture dimension overflow".into())};
            let identity=Identity{epoch,instance:id16(d["shm_instance"].as_str().ok_or("missing mapping identity")?)?,
                capture:id16(&p.capture)?,seq:scalar("seq")?,generation:scalar("generation")?,document:token(&p.document)?,ticket:p.ticket,
                width:dimension("width")?,height:dimension("height")?,presentation_width:dimension("presentation_width")?,presentation_height:dimension("presentation_height")?};
            identity.payload_len().map_err(str::to_owned)?;
            let mut descriptor=d.clone();descriptor["epoch"]=json!(crate::frame_identity::hex(epoch));
            Ok(Ready{identity,descriptor,phase:Phase::Ready})
        })();
        match result {Ok(ready)=>{self.ready=Some(ready);self.error=None;},Err(error)=>{self.ready=None;self.error=Some((p.capture,p.ticket.to_string(),error));}}
    }
    fn matching(&self,capture:&str,ticket:&str)->Result<&Ready,String>{
        let ready=self.ready.as_ref().ok_or("capture is not ready")?;
        if ready.identity.capture!=id16(capture)?||ready.identity.ticket!=token(ticket)? {
            return Err("capture identity changed".into());
        }Ok(ready)
    }
    pub fn frame(&self,capture:&str,ticket:&str)->Result<Identity,String>{
        let ready=self.matching(capture,ticket)?;
        if ready.phase==Phase::Eligible{return Err("capture was already delivered".into());}
        Ok(ready.identity.clone())
    }
    pub fn copied(&mut self,identity:&Identity)->Result<(),String>{
        let ready=self.ready.as_mut().ok_or("capture invalidated during copy")?;
        if &ready.identity!=identity||ready.phase==Phase::Eligible{return Err("capture invalidated during copy".into());}
        ready.phase=Phase::Copied;Ok(())
    }
    pub fn eligible(&mut self,capture:&str,ticket:&str)->Result<(),String>{
        if self.matching(capture,ticket)?.phase==Phase::Ready{return Err("capture pixels have not been delivered".into());}
        self.ready.as_mut().unwrap().phase=Phase::Eligible;Ok(())
    }
    pub fn cancel(&mut self,capture:&str,ticket:&str)->Option<String>{
        let document=self.pending.as_ref().filter(|p|p.capture==capture&&p.ticket.to_string()==ticket)
            .map(|p|p.document.clone()).or_else(||self.matching(capture,ticket).ok().map(|r|r.identity.document.to_string()));
        if document.is_some(){self.invalidate();}document
    }
    pub fn abandon_sample(&mut self,ticket:&str){
        if self.sample_pending.as_ref().map(|p|p.ticket.to_string()==ticket).unwrap_or(false){self.sample_pending=None;}
    }
    pub fn begin_sample(&mut self,capture:&str,ticket:&str,request:String,x:u32,y:u32,size:u32)->Result<(Identity,String),String>{
        let ready=self.matching(capture,ticket)?;
        if ready.phase!=Phase::Eligible{return Err("capture is not eligible for sampling".into());}
        if request.is_empty()||request.len()>128{return Err("invalid sample request identity".into());}
        let identity=ready.identity.clone();
        if x>=identity.width||y>=identity.height||![1,3,5,11].contains(&size){return Err("invalid capture sample point".into());}
        let radius=size/2;let x0=x.saturating_sub(radius);let y0=y.saturating_sub(radius);
        let region=[x0,y0,x.saturating_add(radius+1).min(identity.width)-x0,y.saturating_add(radius+1).min(identity.height)-y0];
        let nonce=self.next()?;
        self.sample_pending=Some(SamplePending{request,ticket:nonce,region});self.sample=None;
        Ok((identity,nonce.to_string()))
    }
    pub fn sample_event(&mut self,epoch:[u8;16],event:&Value){
        if epoch!=self.epoch{return;}
        let (Some(ready),Some(p))=(self.ready.as_ref(),self.sample_pending.as_ref())else{return};
        if ready.phase!=Phase::Eligible||event["capture_id"]!=crate::frame_identity::hex(ready.identity.capture)||
            event["ticket"]!=ready.identity.ticket.to_string()||event["request_id"]!=p.request||event["request_ticket"]!=p.ticket.to_string(){return;}
        let mut value=event.clone();
        if event["success"]==true {
            let d=&event["descriptor"];
            if d["generation"]!=ready.identity.generation.to_string()||d["document_id"]!=ready.identity.document.to_string()||
                d["shm_instance"]!=crate::frame_identity::hex(ready.identity.instance)||d["seq"]!=ready.identity.seq.to_string(){
                value["success"]=json!(false);value["error"]=json!("sample descriptor changed");
                value.as_object_mut().unwrap().remove("analysis");
            }else{
                let a=&event["analysis"];let n=p.region[2] as u64*p.region[3] as u64;
                let valid_region=["x","y","width","height"].iter().enumerate()
                    .all(|(i,key)|event["region"][*key].as_u64()==Some(p.region[i] as u64));
                let finite=a["finite_samples"].as_u64();let bad=a["nonfinite_samples"].as_u64();
                let means=["mean_srgb","mean_lab_d65"].iter().all(|key|{
                    if finite==Some(0){a[*key].is_null()}else{
                        a[*key].as_array().map(|v|v.len()==3&&v.iter().all(|x|x.as_f64().map(f64::is_finite).unwrap_or(false))).unwrap_or(false)
                    }
                });
                if !valid_region||a["samples"].as_u64()!=Some(n)||finite.zip(bad).and_then(|(f,b)|f.checked_add(b))!=Some(n)||!means {
                    value["success"]=json!(false);value["error"]=json!("invalid sampled region or colour statistics");
                    value.as_object_mut().unwrap().remove("analysis");
                }else{
                    value["descriptor"]=ready.descriptor.clone();
                    value["analysis"]=json!({"samples":n,"finite_samples":finite,"nonfinite_samples":bad,
                        "mean_srgb":a["mean_srgb"],"mean_lab_d65":a["mean_lab_d65"]});
                }
            }
        }
        self.sample=Some(value);self.sample_pending=None;
    }
    pub fn snapshot(&self)->Value{
        let phase=if self.pending.is_some(){"arming"}else if let Some(r)=&self.ready{
            match r.phase{Phase::Ready=>"ready",Phase::Copied=>"copied",Phase::Eligible=>"eligible"}
        }else if self.error.is_some(){"error"}else{"idle"};
        let owner=self.pending.as_ref().map(|p|(p.capture.clone(),p.ticket.to_string()))
            .or_else(||self.ready.as_ref().map(|r|(crate::frame_identity::hex(r.identity.capture),r.identity.ticket.to_string())))
            .or_else(||self.error.as_ref().map(|(capture,ticket,_)|(capture.clone(),ticket.clone())));
        json!({"phase":phase,"capture_id":owner.as_ref().map(|p|&p.0),"ticket":owner.as_ref().map(|p|&p.1),
            "descriptor":self.ready.as_ref().map(|r|&r.descriptor),"error":self.error.as_ref().map(|p|&p.2),"sample":self.sample})
    }
    pub fn status_for(&self,capture:&str,ticket:&str)->Value{
        let status=self.snapshot();
        if status["phase"]=="idle"{return status;}
        if status["capture_id"]!=capture||status["ticket"]!=ticket {
            return json!({"phase":"stale","error":"capture identity changed"});
        }status
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const CAP:&str="0123456789abcdef0123456789abcdef";
    fn event(ticket:&str)->Value{json!({"event":"color_capture","action":"arm","capture_id":CAP,"ticket":ticket,"success":true,
        "descriptor":{"version":1,"capture_id":CAP,"ticket":ticket,"document_id":"123","generation":"7","seq":"9007199254740993",
        "shm_instance":"11111111111111111111111111111111","width":2,"height":2,"presentation_width":1,"presentation_height":1,
        "domain":"proxy-output","quality":"proxy-float-output","profile":"working-srgb"}})}
    fn host()->CaptureHost{let mut h=CaptureHost::default();h.reset([1;16]);h}
    #[test] fn old_epoch_repeated_id_and_cancelled_ticket_do_not_reappear(){
        let mut h=host();let old=h.begin(CAP.into(),"123".into(),4).unwrap();
        h.invalidate();let fresh=h.begin(CAP.into(),"123".into(),4).unwrap();
        h.armed_event([1;16],&event(&old),4);assert_eq!(h.snapshot()["phase"],"arming");
        h.armed_event([2;16],&event(&fresh),4);assert_eq!(h.snapshot()["phase"],"arming");
        h.armed_event([1;16],&event(&fresh),4);assert_eq!(h.snapshot()["phase"],"ready");
        assert!(h.cancel(CAP,&old).is_none());assert_eq!(h.snapshot()["phase"],"ready");
    }
    #[test] fn copy_and_ack_are_required_and_late_ack_cannot_rearm(){
        let mut h=host();let t=h.begin(CAP.into(),"123".into(),4).unwrap();h.armed_event([1;16],&event(&t),4);
        assert!(h.eligible(CAP,&t).is_err());assert!(h.begin_sample(CAP,&t,"r".into(),0,0,1).is_err());
        let identity=h.frame(CAP,&t).unwrap();h.copied(&identity).unwrap();h.eligible(CAP,&t).unwrap();
        h.eligible(CAP,&t).unwrap();assert!(h.begin_sample(CAP,&t,"r".into(),0,0,1).is_ok());
        h.invalidate();assert!(h.eligible(CAP,&t).is_err());assert!(h.copied(&identity).is_err());
    }
    #[test] fn mismatched_revision_and_geometry_fail_before_any_pixel_copy(){
        let mut h=host();let t=h.begin(CAP.into(),"123".into(),4).unwrap();h.armed_event([1;16],&event(&t),5);
        assert_eq!(h.snapshot()["phase"],"error");assert!(h.frame(CAP,&t).is_err());
        let t=h.begin(CAP.into(),"123".into(),5).unwrap();let mut bad=event(&t);bad["descriptor"]["width"]=json!(0);
        h.armed_event([1;16],&bad,5);assert_eq!(h.snapshot()["phase"],"error");
    }
    #[test] fn another_consumers_status_never_returns_this_descriptor(){
        let mut h=host();let t=h.begin(CAP.into(),"123".into(),4).unwrap();h.armed_event([1;16],&event(&t),4);
        assert_eq!(h.status_for(CAP,"999")["phase"],"stale");assert!(h.status_for(CAP,"999").get("descriptor").is_none());
    }
    #[test] fn latest_sample_ticket_and_exact_region_are_required(){
        let mut h=host();let t=h.begin(CAP.into(),"123".into(),4).unwrap();h.armed_event([1;16],&event(&t),4);
        let identity=h.frame(CAP,&t).unwrap();h.copied(&identity).unwrap();h.eligible(CAP,&t).unwrap();
        let (_,old)=h.begin_sample(CAP,&t,"old".into(),0,0,1).unwrap();
        let (_,fresh)=h.begin_sample(CAP,&t,"fresh".into(),0,0,3).unwrap();
        let mut sample=json!({"capture_id":CAP,"ticket":t,"request_id":"old","request_ticket":old,"success":true,
            "descriptor":event(&t)["descriptor"],"region":{"x":0,"y":0,"width":2,"height":2},
            "analysis":{"samples":4,"finite_samples":4,"nonfinite_samples":0,"mean_srgb":[0.1,0.2,0.3],"mean_lab_d65":[1,2,3]}});
        h.sample_event([1;16],&sample);assert!(h.snapshot()["sample"].is_null());
        sample["request_id"]=json!("fresh");sample["request_ticket"]=json!(fresh);
        h.sample_event([2;16],&sample);assert!(h.snapshot()["sample"].is_null());
        h.sample_event([1;16],&sample);assert_eq!(h.snapshot()["sample"]["success"],true);
        let (_,bad)=h.begin_sample(CAP,&t,"bad".into(),0,0,1).unwrap();
        sample["request_id"]=json!("bad");sample["request_ticket"]=json!(bad);
        h.sample_event([1;16],&sample);assert_eq!(h.snapshot()["sample"]["success"],false);
        assert!(h.snapshot()["sample"].get("analysis").is_none());
    }

}
