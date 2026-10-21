//! Epoch-bound correlated receipts. Queue acceptance is never a commit result.
use std::collections::VecDeque;
use serde_json::{json,Value};
const MAX_RECORDS:usize=32;
const MAX_RESULT_BYTES:usize=8*1024*1024;
const MAX_BYTES:usize=16*1024*1024;
struct Receipt { id:String, action:String, result:Option<Value>, bytes:usize }
#[derive(Default)]
pub(crate) struct BatchHost { epoch:[u8;16], supported:bool, records:VecDeque<Receipt> }
impl BatchHost {
    pub fn reset(&mut self,epoch:[u8;16]) {self.epoch=epoch;self.supported=false;self.records.clear();}
    pub fn ready(&mut self,epoch:[u8;16],supported:bool){if self.epoch==epoch{self.supported=supported;}}
    pub fn begin(&mut self,epoch:[u8;16],id:&str,action:&str)->Result<(),String>{
        if epoch==[0;16] || epoch!=self.epoch{return Err("batch engine generation changed".into());}
        if !self.supported{return Err("engine has not advertised reviewed batch support".into());}
        if id.is_empty() || id.len()>128 || !["preflight","commit","undo"].contains(&action){return Err("invalid batch request".into());}
        if self.records.iter().any(|r|r.id==id){return Err("batch request ID already exists".into());}
        while self.records.len()>=MAX_RECORDS {
            let index=self.records.iter().position(|r|r.result.is_some()).ok_or("too many pending batch requests")?;
            self.records.remove(index);
        }
        self.records.push_back(Receipt{id:id.into(),action:action.into(),result:None,bytes:0});Ok(())
    }
    pub fn receive(&mut self,epoch:[u8;16],value:&Value){
        if epoch!=self.epoch || epoch==[0;16]{return;}
        let Some(id)=value["request_id"].as_str() else{return};
        let Some(record)=self.records.iter_mut().find(|r|r.id==id) else{return};
        if record.result.is_some() || value["action"].as_str()!=Some(record.action.as_str()){return;}
        let bytes=value.to_string().len();
        let result=if value["success"].as_bool().is_none() || bytes>MAX_RESULT_BYTES {
            json!({"success":false,"outcome_unknown":true,"request_id":id,"action":record.action,
                "error":"invalid or oversized batch receipt; inspect document state"})
        } else {value.clone()};
        record.bytes=result.to_string().len();record.result=Some(result);
        while self.records.iter().map(|r|r.bytes).sum::<usize>()>MAX_BYTES {
            if let Some(index)=self.records.iter().position(|r|r.result.is_some()){self.records.remove(index);}else{break;}
        }
    }
    pub fn failed(&mut self,id:&str,error:&str){
        let action=self.records.iter().find(|r|r.id==id).map(|r|r.action.clone());
        if let Some(action)=action {self.receive(self.epoch,&json!({"request_id":id,"action":action,
            "success":false,"outcome_unknown":true,"error":error}));}
    }
    pub fn ended(&mut self,epoch:[u8;16]){
        if self.epoch!=epoch{return;}
        let ids:Vec<String>=self.records.iter().filter(|r|r.result.is_none()).map(|r|r.id.clone()).collect();
        for id in ids {self.failed(&id,"engine ended before batch completion was confirmed");}
        self.epoch=[0;16];self.supported=false;
    }
    pub fn status(&self,id:&str)->Value{
        match self.records.iter().find(|r|r.id==id) {
            Some(r)=>match &r.result {
                Some(result)=>json!({"phase":"done","request_id":id,"result":result}),
                None=>json!({"phase":"pending","request_id":id}),
            },
            None=>json!({"phase":"unavailable","request_id":id,"error":"receipt missing, evicted or engine restarted"}),
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]fn receipt_requires_epoch_request_and_action_and_first_terminal_wins(){
        let mut h=BatchHost::default();h.reset([1;16]);h.ready([1;16],true);h.begin([1;16],"a","commit").unwrap();
        for (epoch,id,action) in [([2;16],"a","commit"),([1;16],"other","commit"),([1;16],"a","preflight")] {
            h.receive(epoch,&json!({"request_id":id,"action":action,"success":true}));
            assert_eq!(h.status("a")["phase"],"pending");
        }
        h.receive([1;16],&json!({"request_id":"a","action":"commit","success":true}));h.failed("a","late failure");
        assert_eq!(h.status("a")["result"]["success"],true);
    }
    #[test]fn restart_and_exit_do_not_turn_accepted_commands_into_success(){
        let mut h=BatchHost::default();h.reset([1;16]);h.ready([1;16],true);h.begin([1;16],"a","commit").unwrap();h.ended([1;16]);
        assert_eq!(h.status("a")["result"]["outcome_unknown"],true);
        h.reset([2;16]);assert_eq!(h.status("a")["phase"],"unavailable");
        assert!(h.begin([1;16],"b","commit").is_err());h.ended([1;16]);h.ready([2;16],true);assert!(h.begin([2;16],"b","commit").is_ok());
    }
    #[test]fn pending_requests_are_bounded_and_never_silently_evicted(){
        let mut h=BatchHost::default();h.reset([1;16]);h.ready([1;16],true);
        for i in 0..MAX_RECORDS {h.begin([1;16],&i.to_string(),"preflight").unwrap();}
        assert!(h.begin([1;16],"overflow","preflight").is_err());
        h.failed("0","test");h.begin([1;16],"new","preflight").unwrap();
        assert_eq!(h.status("0")["phase"],"unavailable");assert_eq!(h.status("1")["phase"],"pending");
    }
    #[test]fn readiness_belongs_to_current_epoch_and_exit_preserves_drained_success(){
        let mut h=BatchHost::default();h.reset([2;16]);h.ready([1;16],true);
        assert!(h.begin([2;16],"a","commit").is_err());h.ready([2;16],true);h.begin([2;16],"a","commit").unwrap();
        h.receive([2;16],&json!({"request_id":"a","action":"commit","success":true}));h.ended([2;16]);
        assert_eq!(h.status("a")["result"]["success"],true);
    }

    #[test]fn malformed_completion_is_explicitly_unknown_not_success(){
        let mut h=BatchHost::default();h.reset([1;16]);h.ready([1;16],true);h.begin([1;16],"a","commit").unwrap();
        h.receive([1;16],&json!({"request_id":"a","action":"commit","success":"true"}));
        assert_eq!(h.status("a")["result"]["success"],false);
        assert_eq!(h.status("a")["result"]["outcome_unknown"],true);
    }

}
