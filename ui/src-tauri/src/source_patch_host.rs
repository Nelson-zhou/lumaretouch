//! One bounded terminal receipt per apply; queue acceptance is not completion.
use serde_json::{json, Value};
use crate::{color_capture_host::{id16, token}, receipt_host::{ReceiptHost, ReceiptKind}};

pub(crate) struct SourcePatchKind;
pub(crate) type SourcePatchHost = ReceiptHost<SourcePatchKind>;

// ReceiptHost's opaque bound context keeps all three identities together without
// adding another receipt table. All components exclude the separator.
pub(crate) fn binding(document: &str, capture: &str, ticket: &str) -> Result<String, String> {
    token(document)?;
    id16(capture)?;
    token(ticket)?;
    Ok(format!("{document}|{capture}|{ticket}"))
}
fn parts(bound: Option<&str>) -> Option<(&str, &str, &str)> {
    let mut values = bound?.split('|');
    let (document, capture, ticket) = (values.next()?, values.next()?, values.next()?);
    if values.next().is_some() || binding(document, capture, ticket).is_err() { return None; }
    Some((document, capture, ticket))
}
impl ReceiptKind for SourcePatchKind {
    const NAME: &'static str = "source_patch";
    const ACTIONS: &'static [&'static str] = &["apply"];
    fn valid_request(_: &str, bound: Option<&str>) -> bool { parts(bound).is_some() }
    fn valid(v: &Value, bound: Option<&str>) -> bool {
        let Some((document, capture, ticket)) = parts(bound) else { return false };
        let (Some(success), Some(unknown), Some(reload)) =
            (v["success"].as_bool(), v["outcome_unknown"].as_bool(), v["requires_reload"].as_bool())
            else { return false };
        if v["protocol"] != 1 || v["action"] != "apply"
            || v["document_id"].as_str() != Some(document)
            || v["capture_id"].as_str() != Some(capture)
            || v["ticket"].as_str() != Some(ticket) || (success && unknown) { return false; }
        if !success { return true; }
        let (Some(no_change), Some(before), Some(after)) =
            (v["no_change"].as_bool(), v["before_count"].as_u64(), v["after_count"].as_u64())
            else { return false };
        if reload || !["undo_steps", "redo_steps"].iter().all(|k| v["history"][*k].as_u64().is_some()) { return false; }
        if no_change {
            before == after && v.get("op_id").is_some_and(Value::is_null)
        } else {
            before.checked_add(1) == Some(after) && v["op_id"].as_u64().is_some()
        }
    }
    fn decorate_failure(v: &mut Value, bound: Option<&str>) {
        v["protocol"] = json!(1);
        v["requires_reload"] = json!(true);
        if let Some((document, capture, ticket)) = parts(bound) {
            v["document_id"] = json!(document);
            v["capture_id"] = json!(capture);
            v["ticket"] = json!(ticket);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const CAP: &str = "0123456789abcdef0123456789abcdef";
    fn receipt() -> Value { json!({"protocol":1,"action":"apply","request_id":"r","document_id":"123",
        "capture_id":CAP,"ticket":"7","success":true,"outcome_unknown":false,"requires_reload":false,
        "no_change":false,"before_count":3,"after_count":4,"op_id":12,"history":{"undo_steps":4,"redo_steps":0}}) }
    fn bound() -> String { binding("123", CAP, "7").unwrap() }
    #[test] fn successful_receipt_requires_exact_identity_and_one_operation() {
        let v = receipt();
        assert!(SourcePatchKind::valid(&v, Some(&bound())));
        for key in ["document_id", "capture_id", "ticket"] {
            let mut bad = v.clone(); bad[key] = json!("wrong");
            assert!(!SourcePatchKind::valid(&bad, Some(&bound())));
        }
        let mut bad = v; bad["after_count"] = json!(5);
        assert!(!SourcePatchKind::valid(&bad, Some(&bound())));
        bad["after_count"] = json!(4); bad["op_id"] = json!(1.5);
        assert!(!SourcePatchKind::valid(&bad, Some(&bound())));
    }
    #[test] fn no_change_is_explicit_and_never_claims_an_operation() {
        let mut v = receipt(); v["no_change"] = json!(true); v["after_count"] = json!(3); v["op_id"] = Value::Null;
        assert!(SourcePatchKind::valid(&v, Some(&bound())));
        v["op_id"] = json!(12); assert!(!SourcePatchKind::valid(&v, Some(&bound())));
        v["op_id"] = Value::Null; v["outcome_unknown"] = json!(true);
        assert!(!SourcePatchKind::valid(&v, Some(&bound())));
    }
    #[test] fn wrong_epoch_and_duplicates_do_not_replace_terminal_receipt() {
        let mut h = SourcePatchHost::default(); h.reset([1;16]); h.ready([1;16], true);
        h.begin_bound([1;16], "r", "apply", Some(&bound())).unwrap();
        h.receive([2;16], &receipt()); assert_eq!(h.status("r")["phase"], "pending");
        h.receive([1;16], &receipt()); h.ended([1;16]);
        assert_eq!(h.status("r")["result"]["success"], true);
        assert!(h.begin_bound([1;16], "r", "apply", Some(&bound())).is_err());
    }
    #[test] fn malformed_or_lost_result_is_unknown_and_keeps_capture_binding() {
        let mut h = SourcePatchHost::default(); h.reset([1;16]); h.ready([1;16], true);
        h.begin_bound([1;16], "r", "apply", Some(&bound())).unwrap();
        let mut bad = receipt(); bad["ticket"] = json!("9"); h.receive([1;16], &bad);
        let status = h.status("r");
        assert_eq!(status["result"]["outcome_unknown"], true);
        assert_eq!(status["result"]["requires_reload"], true);
        assert_eq!(status["result"]["capture_id"], CAP);
        assert_eq!(status["result"]["ticket"], "7");
    }
}
