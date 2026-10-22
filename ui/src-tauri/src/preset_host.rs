//! Preset-specific protocol and document binding atop the shared mailbox.
use serde_json::{json, Value};
use crate::receipt_host::{ReceiptHost, ReceiptKind};
pub(crate) struct PresetKind;
fn text(value: &Value) -> bool { value.as_str().is_some_and(|s| !s.trim().is_empty()) }
fn scope(value: &Value) -> bool {
    value.as_array().is_some_and(|a| !a.is_empty() && a.iter().all(text)
        && a.iter().filter_map(Value::as_str).collect::<std::collections::BTreeSet<_>>().len() == a.len())
}
fn modules(value: &Value, ops: &Value) -> bool {
    let (Some(map), Some(ops)) = (value.as_object(), ops.as_array()) else { return false };
    map.len() == ops.len() && ops.iter().all(|op| op.as_str().is_some_and(|op| map.get(op).is_some_and(Value::is_object)))
}
fn preset(value: &Value) -> bool {
    value["schema"] == "lrt.preset.v1" && text(&value["id"]) && text(&value["name"])
        && text(&value["kind"]) && value["builtin"].is_boolean() && value["modules"].as_object().is_some_and(|m| !m.is_empty() && m.values().all(Value::is_object))
}
impl ReceiptKind for PresetKind {
    const NAME: &'static str = "preset";
    const ACTIONS: &'static [&'static str] = &["list", "apply", "save", "import", "delete"];
    fn valid_request(action: &str, document: Option<&str>) -> bool {
        if ["apply", "save"].contains(&action) {
            document.is_some_and(|d| !d.is_empty() && d.len() <= 128 && d.chars().count() <= 64)
        } else { document.is_none() }
    }
    fn valid(value: &Value, document: Option<&str>) -> bool {
        let Some(success) = value["success"].as_bool() else { return false };
        let Some(unknown) = value["outcome_unknown"].as_bool() else { return false };
        if value["protocol"].as_u64() != Some(1) || (success && unknown) { return false; }
        if document.is_some() && value["document_id"].as_str() != document { return false; }
        if !success { return true; }
        match value["action"].as_str() {
            Some("list") => value["catalog"]["available"] == true && value["catalog"]["list"].as_array().is_some_and(|items| items.iter().all(preset))
                && value["catalog"]["errors"].is_array() && value["catalog"]["modules"].is_array(),
            Some("apply") => text(&value["id"]) && scope(&value["module_scope"]) && modules(&value["before"], &value["module_scope"])
                && modules(&value["after"], &value["module_scope"]) && value["doc_state"].is_object()
                && value["doc_state"]["document_id"].as_str() == document,
            Some("save" | "import") => text(&value["id"]) && text(&value["path"]) && scope(&value["module_scope"])
                && preset(&value["preset"]) && value["preset"]["id"] == value["id"] && modules(&value["preset"]["modules"], &value["module_scope"]),
            Some("delete") => text(&value["id"]) && text(&value["path"]),
            _ => false,
        }
    }
    fn decorate_failure(value: &mut Value, document: Option<&str>) {
        value["protocol"] = json!(1);
        if let Some(document) = document { value["document_id"] = json!(document); }
    }
}
pub(crate) type PresetHost = ReceiptHost<PresetKind>;
#[cfg(test)]
mod tests {
    use super::*;
    fn host() -> PresetHost { let mut h = PresetHost::default(); h.reset([1; 16]); h.ready([1; 16], true); h }
    #[test] fn editing_actions_require_document_identity_but_catalog_does_not() {
        let mut h = host(); assert!(h.begin([1; 16], "a", "apply").is_err());
        assert!(h.begin_bound([1; 16], "a", "save", Some("doc")).is_ok());
        assert!(h.begin([1; 16], "b", "list").is_ok());
        assert!(h.begin_bound([1; 16], "c", "import", Some("doc")).is_err());
    }
    #[test] fn mismatched_document_and_missing_evidence_never_become_success() {
        let mut h = host(); h.begin_bound([1; 16], "a", "apply", Some("doc")).unwrap();
        h.receive([1; 16], &json!({"protocol":1,"request_id":"a","action":"apply","success":true,"outcome_unknown":false,"document_id":"other"}));
        assert_eq!(h.status("a")["result"]["outcome_unknown"], true);
        assert_eq!(h.status("a")["result"]["document_id"], "doc");
        h.begin_bound([1; 16], "b", "save", Some("doc")).unwrap();
        h.receive([1; 16], &json!({"protocol":1,"request_id":"b","action":"save","success":true,"outcome_unknown":false,"document_id":"doc"}));
        assert_eq!(h.status("b")["result"]["success"], false);
    }
    #[test] fn shutdown_and_send_failure_keep_protocol_identity_and_first_terminal() {
        let mut h = host(); h.begin_bound([1; 16], "a", "save", Some("doc")).unwrap(); h.failed("a", "send failed");
        assert_eq!(h.status("a")["result"]["protocol"], 1);
        assert_eq!(h.status("a")["result"]["document_id"], "doc");
        h.begin([1; 16], "b", "delete").unwrap();
        h.receive([1; 16], &json!({"protocol":1,"request_id":"b","action":"delete","success":true,"outcome_unknown":false,"id":"p","path":"/p.json"}));
        h.ended([1; 16]); assert_eq!(h.status("b")["result"]["success"], true);
        h.reset([2; 16]); assert_eq!(h.status("a")["phase"], "unavailable");
    }
    #[test] fn complete_receipts_are_accepted_for_all_actions() {
        let p = json!({"schema":"lrt.preset.v1","id":"p","name":"name","kind":"custom","builtin":false,"modules":{"hsl":{"recipe":{}}}});
        for action in ["list", "apply", "save", "import", "delete"] {
            let document = if ["apply", "save"].contains(&action) { Some("doc") } else { None };
            let value = json!({"protocol":1,"request_id":"r","action":action,"success":true,"outcome_unknown":false,
                "document_id":"doc","id":"p","path":"/p.json","module_scope":["hsl"],"preset":p,
                "before":{"hsl":{}},"after":{"hsl":{}},"doc_state":{"document_id":"doc"},
                "catalog":{"available":true,"list":[p],"errors":[],"modules":[]}});
            assert!(PresetKind::valid(&value, document), "{action}");
        }
    }
    #[test] fn duplicate_scope_and_incomplete_module_evidence_are_rejected() {
        let mut v = json!({"protocol":1,"request_id":"r","action":"save","success":true,"outcome_unknown":false,
            "document_id":"doc","id":"p","path":"/p.json","module_scope":["hsl"],
            "preset":{"schema":"lrt.preset.v1","id":"p","name":"name","kind":"custom","builtin":false,"modules":{"hsl":{}}}});
        assert!(PresetKind::valid(&v, Some("doc")));
        v["module_scope"] = json!(["hsl","hsl"]); assert!(!PresetKind::valid(&v, Some("doc")));
        v["module_scope"] = json!(["hsl"]); v["preset"]["modules"] = json!({}); assert!(!PresetKind::valid(&v, Some("doc")));
        v["action"] = json!("apply"); v["before"] = json!({}); v["after"] = json!({});
        v["doc_state"] = json!({"document_id":"doc"}); assert!(!PresetKind::valid(&v, Some("doc")));
    }

}
