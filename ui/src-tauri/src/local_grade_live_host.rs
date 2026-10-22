//! Numeric gestures do not consume source/geometry presentation proofs.
//! Every acknowledgement is bound to engine epoch, photo, group and gesture.
use serde_json::{json, Value};
use crate::receipt_host::{ReceiptHost, ReceiptKind};

pub(crate) struct LiveGradeKind;
pub(crate) type LiveGradeHost = ReceiptHost<LiveGradeKind>;

pub(crate) fn identity(value: &str, limit: usize) -> bool {
    !value.is_empty() && value.len() <= limit
        && value.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'-')
}
pub(crate) fn binding(document: &str, session: &str, group: &str) -> Result<String, String> {
    if !identity(document, 128) || !identity(session, 128) || !identity(group, 64) {
        return Err("invalid live grade photo/group/gesture identity".into());
    }
    Ok(format!("{document}|{session}|{group}"))
}
fn parts(bound: Option<&str>) -> Option<(&str, &str, &str)> {
    let mut p = bound?.split('|');
    let (document, session, group) = (p.next()?, p.next()?, p.next()?);
    if p.next().is_some() || binding(document, session, group).is_err() { return None; }
    Some((document, session, group))
}
impl ReceiptKind for LiveGradeKind {
    const NAME: &'static str = "local_grade_live";
    const ACTIONS: &'static [&'static str] = &["begin", "preview", "commit", "cancel"];
    fn valid_request(_: &str, bound: Option<&str>) -> bool { parts(bound).is_some() }
    fn valid(v: &Value, bound: Option<&str>) -> bool {
        let Some((document, session, group)) = parts(bound) else { return false; };
        let (Some(success), Some(unknown), Some(reload)) =
            (v["success"].as_bool(), v["outcome_unknown"].as_bool(), v["requires_reload"].as_bool()) else { return false; };
        if v["protocol"] != 1 || v["document_id"] != document || v["session_id"] != session
            || v["group_id"] != group || success && (unknown || reload) { return false; }
        if !success { return true; }
        match v["action"].as_str() {
            Some("begin" | "preview" | "commit") => {
                if !v["grade"].as_array().is_some_and(|a| a.len() == 4 && a.iter().all(Value::is_number)) { return false; }
                v["action"] != "commit" || (v["no_change"].is_boolean()
                    && ["undo_steps", "redo_steps"].iter().all(|key| v["history"][*key].as_u64().is_some()))
            }
            Some("cancel") => v["cancelled"] == true,
            _ => false,
        }
    }
    fn decorate_failure(v: &mut Value, bound: Option<&str>) {
        v["protocol"] = json!(1); v["requires_reload"] = json!(true);
        if let Some((document, session, group)) = parts(bound) {
            v["document_id"] = json!(document); v["session_id"] = json!(session); v["group_id"] = json!(group);
        }
    }
}
