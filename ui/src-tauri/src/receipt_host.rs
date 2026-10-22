//! Bounded, epoch-bound terminal receipts. Acceptance is not completion.
use std::{collections::VecDeque, marker::PhantomData};
use serde_json::{json, Value};
pub(crate) const MAX_RECORDS: usize = 32;
const MAX_RESULT_BYTES: usize = 8 * 1024 * 1024;
const MAX_BYTES: usize = 16 * 1024 * 1024;
pub(crate) trait ReceiptKind {
    const NAME: &'static str;
    const ACTIONS: &'static [&'static str];
    fn valid(value: &Value, document: Option<&str>) -> bool;
    fn valid_request(_: &str, _: Option<&str>) -> bool { true }
    fn decorate_failure(_: &mut Value, _: Option<&str>) {}
}
struct Receipt { id: String, action: String, document: Option<String>, result: Option<Value>, bytes: usize }
pub(crate) struct ReceiptHost<K: ReceiptKind> {
    epoch: [u8; 16], supported: bool, records: VecDeque<Receipt>, kind: PhantomData<K>,
}
impl<K: ReceiptKind> Default for ReceiptHost<K> {
    fn default() -> Self { Self { epoch: [0; 16], supported: false, records: VecDeque::new(), kind: PhantomData } }
}
impl<K: ReceiptKind> ReceiptHost<K> {
    pub fn reset(&mut self, epoch: [u8; 16]) { self.epoch = epoch; self.supported = false; self.records.clear(); }
    pub fn ready(&mut self, epoch: [u8; 16], supported: bool) { if self.epoch == epoch { self.supported = supported; } }
    pub fn begin(&mut self, epoch: [u8; 16], id: &str, action: &str) -> Result<(), String> {
        self.begin_bound(epoch, id, action, None)
    }
    pub fn begin_bound(&mut self, epoch: [u8; 16], id: &str, action: &str, document: Option<&str>) -> Result<(), String> {
        if epoch == [0; 16] || epoch != self.epoch { return Err(format!("{} engine generation changed", K::NAME)); }
        if !self.supported { return Err(format!("engine has not advertised reviewed {} support", K::NAME)); }
        if id.is_empty() || id.len() > 128 || !K::ACTIONS.contains(&action) || !K::valid_request(action, document) {
            return Err(format!("invalid {} request", K::NAME));
        }
        if self.records.iter().any(|r| r.id == id) { return Err(format!("{} request ID already exists", K::NAME)); }
        while self.records.len() >= MAX_RECORDS {
            let index = self.records.iter().position(|r| r.result.is_some()).ok_or_else(|| format!("too many pending {} requests", K::NAME))?;
            self.records.remove(index);
        }
        self.records.push_back(Receipt { id: id.into(), action: action.into(), document: document.map(str::to_owned), result: None, bytes: 0 });
        Ok(())
    }
    fn unknown(record: &Receipt, error: &str) -> Value {
        let mut value = json!({"request_id": record.id, "action": record.action, "success": false, "outcome_unknown": true, "error": error});
        K::decorate_failure(&mut value, record.document.as_deref()); value
    }
    pub fn receive(&mut self, epoch: [u8; 16], value: &Value) {
        if epoch != self.epoch || epoch == [0; 16] { return; }
        let Some(id) = value["request_id"].as_str() else { return };
        let Some(record) = self.records.iter_mut().find(|r| r.id == id) else { return };
        if record.result.is_some() || value["action"].as_str() != Some(record.action.as_str()) { return; }
        let result = if !K::valid(value, record.document.as_deref()) || value.to_string().len() > MAX_RESULT_BYTES {
            Self::unknown(record, &format!("invalid or oversized {} receipt; inspect actual state", K::NAME))
        } else { value.clone() };
        record.bytes = result.to_string().len(); record.result = Some(result);
        while self.records.iter().map(|r| r.bytes).sum::<usize>() > MAX_BYTES {
            if let Some(index) = self.records.iter().position(|r| r.result.is_some()) { self.records.remove(index); } else { break; }
        }
    }
    pub fn failed(&mut self, id: &str, error: &str) {
        let value = self.records.iter().find(|r| r.id == id).map(|r| Self::unknown(r, error));
        if let Some(value) = value { self.receive(self.epoch, &value); }
    }
    pub fn ended(&mut self, epoch: [u8; 16]) {
        if self.epoch != epoch { return; }
        let ids: Vec<String> = self.records.iter().filter(|r| r.result.is_none()).map(|r| r.id.clone()).collect();
        for id in ids { self.failed(&id, &format!("engine ended before {} completion was confirmed", K::NAME)); }
        self.epoch = [0; 16]; self.supported = false;
    }
    pub fn status(&self, id: &str) -> Value {
        match self.records.iter().find(|r| r.id == id) {
            Some(r) => match &r.result {
                Some(result) => json!({"phase": "done", "request_id": id, "result": result}),
                None => json!({"phase": "pending", "request_id": id}),
            },
            None => json!({"phase": "unavailable", "request_id": id, "error": "receipt missing, evicted or engine restarted"}),
        }
    }
}
