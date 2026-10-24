//! AUTHORED / UNRUN. Recovery correlation predicates, not actual engine execution.
use super::*;
use crate::torso_transfer_protocol::{HEAD_OP, read_only_head_preflight};
fn review(kind: &str, id: &str) -> Value {
    let mut value = json!({"cmd":kind,"action":"preflight","request_id":id,"module_scope":[HEAD_OP]});
    if kind == "preset" { value["id"] = json!("head-preset"); value["document_id"] = json!("head-target"); }
    else { value["docs"] = json!(["head-target"]); }
    value
}
#[test]
fn exact_head_preflight_is_read_only_not_a_blanket_preflight_exemption() {
    let epoch = [191;16];
    for (kind, id) in [("preset","head-preset-read"),("batch","head-batch-read")] {
        let value = review(kind, id); assert!(read_only_head_preflight(&value)); issued(epoch, &value).unwrap();
    }
    assert!(proof(epoch).is_ok());
    for (key, replacement) in [("cmd", json!("other")), ("action", json!("commit")),
        ("module_scope", json!([HEAD_OP,"lnx.exposure.v1"])), ("module_scope", json!([crate::waist_transfer_protocol::WAIST_OP])),
        ("module_scope", json!([])), ("head_review_ack", json!([])), ("waist_review_ack", Value::Null),
        ("head_transfer", json!({}))] {
        let mut value = review("batch", "not-a-safe-head-read"); value[key] = replacement;
        assert!(!read_only_head_preflight(&value), "{key}");
    }
    let mut ordinary = review("batch", "legacy-read"); ordinary.as_object_mut().unwrap().remove("module_scope");
    issued(epoch, &ordinary).unwrap(); assert!(proof(epoch).is_err());
    observed(epoch, &json!({"event":"batch_result","action":"preflight","request_id":"legacy-read","success":false,"outcome_unknown":false}));
    assert!(proof(epoch).is_ok());
}
#[test]
fn head_read_exemption_never_replaces_a_pending_mutation_with_same_id() {
    let epoch = [192;16];
    let mutation = json!({"cmd":"batch","action":"commit","request_id":"same","head_review_ack":[],"preflight_token":"f".repeat(32)});
    issued(epoch, &mutation).unwrap(); assert!(issued(epoch, &review("preset", "same")).is_err());
    assert!(proof(epoch).is_err());
    for (event, action) in [("preset_result","preflight"), ("batch_result","preflight"), ("preset_result","apply"), ("arbitrary_done","commit")] {
        observed(epoch, &json!({"event":event,"action":action,"request_id":"same","success":true,"outcome_unknown":false}));
        assert!(proof(epoch).is_err(), "{event}/{action}");
    }
    observed(epoch, &json!({"event":"batch_result","request_id":"same","success":true,"outcome_unknown":false}));
    assert!(proof(epoch).is_err());
    observed(epoch, &json!({"event":"batch_result","action":null,"request_id":"same","success":true,"outcome_unknown":false}));
    assert!(proof(epoch).is_err());
    observed(epoch, &json!({"event":"batch_result","action":"commit","request_id":"same","success":true,"outcome_unknown":true}));
    assert!(proof(epoch).is_err());
    observed(epoch, &json!({"event":"batch_result","action":"commit","request_id":"same","success":true,"outcome_unknown":false}));
    assert!(proof(epoch).is_ok());
}
#[test]
fn late_head_read_cannot_settle_later_mutation_in_either_host_or_other_domain() {
    for (epoch, kind, action) in [([193;16], "preset", "apply"), ([194;16], "batch", "commit"), ([195;16], "people", "commit")] {
        issued(epoch, &review("batch", "reused")).unwrap(); assert!(proof(epoch).is_ok());
        issued(epoch, &json!({"cmd":kind,"action":action,"request_id":"reused"})).unwrap();
        for scope in [Value::Null, json!([HEAD_OP])] {
            observed(epoch, &json!({"event":"batch_result","action":"preflight","request_id":"reused",
                "success":false,"outcome_unknown":false,"module_scope":scope,"error":"Read rejected"}));
            assert!(proof(epoch).is_err());
        }
        observed(epoch, &json!({"event":"project_opened"})); assert!(proof(epoch).is_ok());
    }
}
