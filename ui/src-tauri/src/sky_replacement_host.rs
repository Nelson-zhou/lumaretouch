//! Exact-output presentation proof and one-shot sky replacement receipts.
use serde_json::{json,Value};
use crate::receipt_host::{ReceiptHost,ReceiptKind};
use crate::color_capture_host::{id16,token};
pub(crate) struct SkyReplacementKind;
pub(crate) type SkyReplacementHost=ReceiptHost<SkyReplacementKind>;
pub(crate) fn binding(document:&str,session:&str,preview:&str)->Result<String,String>{
    token(document)?;id16(session)?;id16(preview)?;Ok(format!("{document}|{session}|{preview}"))
}
fn parts(bound:Option<&str>)->Option<[&str;3]>{
    let p:Vec<_>=bound?.split('|').collect();let p:[&str;3]=p.try_into().ok()?;
    binding(p[0],p[1],p[2]).ok()?;Some(p)
}
impl ReceiptKind for SkyReplacementKind {
    const NAME:&'static str="sky_replacement";
    const ACTIONS:&'static [&'static str]=&["apply"];
    fn valid_request(_:&str,bound:Option<&str>)->bool{parts(bound).is_some()}
    fn valid(v:&Value,bound:Option<&str>)->bool{
        let Some([document,session,preview])=parts(bound) else{return false};
        let (Some(success),Some(unknown),Some(reload))=(v["success"].as_bool(),v["outcome_unknown"].as_bool(),v["requires_reload"].as_bool()) else{return false};
        v["protocol"]==1&&v["action"]=="apply"&&v["document_id"]==document&&v["session_id"]==session&&v["preview_id"]==preview
            &&!(success&&unknown)&&(!success||(!reload&&v["no_change"].is_boolean()
                &&["undo_steps","redo_steps"].iter().all(|k|v["history"][*k].as_u64().is_some())))
    }
    fn decorate_failure(v:&mut Value,bound:Option<&str>){
        v["protocol"]=json!(1);v["requires_reload"]=json!(true);
        if let Some(p)=parts(bound){for(k,vv)in ["document_id","session_id","preview_id"].iter().zip(p){v[*k]=json!(vv);}}
    }
}
#[derive(Default)]
pub(crate) struct SkyReplacementPreviewHost {
    epoch:[u8;16],bound:Option<(String,String,String)>,value:Option<Value>,delivered:bool,presentation_requested:bool,shown:bool,redeemed:bool,
}
impl SkyReplacementPreviewHost {
    pub fn source_session(&self, epoch:[u8;16], document:&str, session:&str, shown:bool)->bool {
        epoch != [0;16] && epoch == self.epoch && !self.redeemed
            && self.bound.as_ref().is_some_and(|b| b.0 == document && b.1 == session)
            && (!shown || self.shown)
    }
    pub fn invalidate(&mut self){self.bound=None;self.value=None;self.delivered=false;self.presentation_requested=false;self.shown=false;self.redeemed=false;}
    pub fn reset(&mut self,epoch:[u8;16]){self.invalidate();self.epoch=epoch;}
    pub fn ended(&mut self,epoch:[u8;16]){if self.epoch==epoch{self.reset([0;16]);}}
    pub fn begin(&mut self,epoch:[u8;16],document:&str,session:&str,preview:&str)->Result<(),String>{
        binding(document,session,preview)?;
        if epoch==[0;16]||epoch!=self.epoch{return Err("sky replacement engine changed".into());}
        if self.bound.as_ref().is_some_and(|b|b.2==preview){return Err("use a fresh sky preview ID".into());}
        self.invalidate();self.bound=Some((document.into(),session.into(),preview.into()));
        self.value=Some(json!({"protocol":1,"state":"running","success":true,"document_id":document,"session_id":session,"preview_id":preview}));Ok(())
    }
    pub fn matches(&self,epoch:[u8;16],document:&str,session:&str,preview:&str)->bool{
        epoch!=[0;16]&&epoch==self.epoch&&self.bound.as_ref().is_some_and(|b|b.0==document&&b.1==session&&b.2==preview)
    }
    pub fn receive(&mut self,epoch:[u8;16],v:&Value){
        let Some((document,session,preview))=self.bound.as_ref()else{return};
        if epoch!=self.epoch||v["document_id"]!=document.as_str()||v["session_id"]!=session.as_str()||v["preview_id"]!=preview.as_str()||self.redeemed{return;}
        let image=||{let r=&v["result"];
            r["domain"]=="source-normalized"&&r["quality"]=="proxy-render-srgb8"&&r["output_domain"]=="production-output"&&r["automatic_detection"].is_boolean()
            &&matches!(r["target"].as_str(),Some("sky"|"person"|"water"|"recovery"))
            &&["source_width","source_height"].iter().all(|k|r[*k].as_u64().is_some_and(|n|(1..=800).contains(&n)))
            &&v["committable"].is_boolean()&&v["editable"].is_object()&&(v["validation_error"].is_null()||v["validation_error"].is_string())
            &&["width","height"].iter().all(|k|r[*k].as_u64().is_some_and(|n|(1..=800).contains(&n)))
            &&["source","after","overlay"].iter().all(|k|r[*k].as_str().is_some_and(|s|s.starts_with("data:image/png;base64,")&&s.len()<=4*1024*1024))
            &&v["recipe_document_id"].as_str().is_some_and(|s|id16(s).is_ok())
            &&v["recipe_revision"].as_str().is_some_and(|s|s.parse::<u64>().is_ok())};
        let valid=v["protocol"]==1&&v.to_string().len()<=6*1024*1024+256*1024&&match v["state"].as_str(){
            Some("ready")=>v["success"]==true&&image(),
            Some("presented")=>v["success"]==true&&self.delivered&&self.presentation_requested,
            Some("failed")=>v["success"]==false,
            Some("cancelled")=>v["success"]==true,
            _=>false,
        };
        if !valid{
            self.shown=false;self.value=Some(json!({"protocol":1,"state":"failed","success":false,"document_id":document,"session_id":session,"preview_id":preview,"error":"invalid sky replacement preview"}));
        }else if v["state"]=="presented"{
            self.shown=true;if let Some(value)=self.value.as_mut(){value["state"]=json!("presented");}
        }else{self.delivered=false;self.shown=false;self.presentation_requested=false;self.value=Some(v.clone());}
    }
    pub fn status(&mut self,epoch:[u8;16],preview:&str)->Value{
        if epoch!=self.epoch||!self.bound.as_ref().is_some_and(|b|b.2==preview)||self.redeemed{return json!({"state":"stale","preview_id":preview});}
        if self.value.as_ref().is_some_and(|v|v["state"]=="ready"){self.delivered=true;}
        self.value.clone().unwrap_or_else(||json!({"state":"stale","preview_id":preview}))
    }
    pub fn presentation_requested(&mut self)->Result<(),String>{
        if !self.delivered||self.redeemed||!self.value.as_ref().is_some_and(|v|v["state"]=="ready"||v["state"]=="presented"){
            return Err("sky replacement output has not been delivered".into());
        }
        self.presentation_requested=true;Ok(())
    }
    pub fn redeem(&mut self)->Result<(),String>{
        if !self.shown||self.redeemed||!self.value.as_ref().is_some_and(|v|v["committable"]==true&&v["validation_error"].is_null()){return Err("final sky replacement output was not presented or was already submitted".into());}
        self.redeemed=true;Ok(())
    }
}
