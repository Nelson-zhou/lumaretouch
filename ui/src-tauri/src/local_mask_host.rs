//! Local-mask history receipts are distinct from repair operation counts.
use serde_json::{json, Value};
use crate::receipt_host::{ReceiptHost, ReceiptKind};
pub(crate) struct LocalMaskKind;
pub(crate) type LocalMaskHost = ReceiptHost<LocalMaskKind>;
pub(crate) use crate::source_patch_host::binding;
fn parts(bound: Option<&str>) -> Option<(&str, &str, &str)> {
    let mut values = bound?.split('|');
    let (document, capture, ticket) = (values.next()?, values.next()?, values.next()?);
    if values.next().is_some() || binding(document, capture, ticket).is_err() { return None; }
    Some((document, capture, ticket))
}
impl ReceiptKind for LocalMaskKind {
    const NAME: &'static str = "local_masks";
    const ACTIONS: &'static [&'static str] = &["apply"];
    fn valid_request(_: &str, bound: Option<&str>) -> bool { parts(bound).is_some() }
    fn valid(v: &Value, bound: Option<&str>) -> bool {
        let Some((document, capture, ticket)) = parts(bound) else { return false };
        let (Some(success), Some(unknown), Some(reload)) =
            (v["success"].as_bool(), v["outcome_unknown"].as_bool(), v["requires_reload"].as_bool()) else { return false };
        if v["protocol"] != 1 || v["action"] != "apply"
            || v["document_id"].as_str() != Some(document)
            || v["capture_id"].as_str() != Some(capture) || v["ticket"].as_str() != Some(ticket)
            || (success && unknown) { return false; }
        !success || (!reload && v["no_change"].is_boolean()
            && ["undo_steps", "redo_steps"].iter().all(|key| v["history"][*key].as_u64().is_some()))
    }
    fn decorate_failure(v: &mut Value, bound: Option<&str>) {
        v["protocol"] = json!(1); v["requires_reload"] = json!(true);
        if let Some((document, capture, ticket)) = parts(bound) {
            v["document_id"] = json!(document); v["capture_id"] = json!(capture); v["ticket"] = json!(ticket);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const CAP: &str = "0123456789abcdef0123456789abcdef";
    fn bound() -> String { binding("123", CAP, "7").unwrap() }
    fn receipt() -> Value { json!({"protocol":1,"action":"apply","request_id":"r","document_id":"123",
        "capture_id":CAP,"ticket":"7","success":true,"outcome_unknown":false,"requires_reload":false,
        "no_change":false,"history":{"undo_steps":4,"redo_steps":0}}) }
    #[test] fn local_mask_receipt_is_bound_to_displayed_source_and_history() {
        let v = receipt(); assert!(LocalMaskKind::valid(&v, Some(&bound())));
        for key in ["document_id", "capture_id", "ticket", "protocol", "no_change", "history"] {
            let mut bad = v.clone(); bad[key] = Value::Null;
            assert!(!LocalMaskKind::valid(&bad, Some(&bound())));
        }
        let mut bad = v; bad["outcome_unknown"] = json!(true);
        assert!(!LocalMaskKind::valid(&bad, Some(&bound())));
    }
    #[test] fn duplicate_wrong_epoch_and_lost_result_never_claim_success() {
        let mut host = LocalMaskHost::default(); host.reset([1;16]); host.ready([1;16], true);
        host.begin_bound([1;16], "r", "apply", Some(&bound())).unwrap();
        host.receive([2;16], &receipt()); assert_eq!(host.status("r")["phase"], "pending");
        assert!(host.begin_bound([1;16], "r", "apply", Some(&bound())).is_err());
        host.ended([1;16]); let result = &host.status("r")["result"];
        assert_eq!(result["outcome_unknown"], true); assert_eq!(result["capture_id"], CAP);
        assert_eq!(result["requires_reload"], true);
    }
}
