//! A single latest colour-analysis request. Late replies cannot resurrect invalidated data.
use serde_json::{json,Value};
#[derive(Default)]
pub struct ScopeHost {
    generation:u64,
    pending:Option<Pending>,
    result:Option<Value>,
}
struct Pending {ticket:String,request:String,document:String,stage:String,revision:usize}
impl ScopeHost {
    pub fn invalidate(&mut self) {self.pending=None;self.result=None;}
    pub fn begin(&mut self,request:String,document:String,stage:String,revision:usize)->Result<String,String> {
        self.generation=self.generation.checked_add(1).ok_or("scope generation exhausted")?;
        let ticket=self.generation.to_string();
        self.pending=Some(Pending{ticket:ticket.clone(),request,document,stage,revision});
        self.result=None;Ok(ticket)
    }
    pub fn complete(&mut self,event:&Value,revision:usize) {
        let Some(p)=self.pending.as_ref() else{return};
        if event["ticket"]!=p.ticket || event["request_id"]!=p.request || event["stage"]!=p.stage {return;}
        let mut result=event.clone();
        if event["document_id"]!=p.document || revision!=p.revision {
            result=json!({"event":"color_scopes","request_id":p.request,"ticket":p.ticket,
                "document_id":p.document,"stage":p.stage,"success":false,
                "error":"Document changed while sampling; refresh colour scopes"});
        }
        result["host_doc_rev"]=json!(p.revision);
        self.result=Some(result);self.pending=None;
    }
    pub fn snapshot(&self)->Option<Value>{self.result.clone()}
}
#[cfg(test)]
mod tests {
    use super::*;
    fn event(ticket:&str)->Value{json!({"request_id":"r","document_id":"doc","stage":"output","ticket":ticket,"success":true})}
    #[test] fn invalidated_or_replaced_reply_cannot_reappear(){
        let mut h=ScopeHost::default();let old=h.begin("r".into(),"doc".into(),"output".into(),3).unwrap();
        h.invalidate();h.complete(&event(&old),3);assert!(h.snapshot().is_none());
        let new=h.begin("r".into(),"doc".into(),"output".into(),3).unwrap();
        h.complete(&event(&old),3);assert!(h.snapshot().is_none());
        h.complete(&event(&new),3);assert_eq!(h.snapshot().unwrap()["success"],true);
    }
    #[test] fn changed_revision_is_an_explicit_stale_result(){
        let mut h=ScopeHost::default();let t=h.begin("r".into(),"doc".into(),"output".into(),3).unwrap();
        h.complete(&event(&t),4);assert_eq!(h.snapshot().unwrap()["success"],false);
    }
}
