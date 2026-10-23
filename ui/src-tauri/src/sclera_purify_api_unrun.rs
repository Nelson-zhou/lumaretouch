// AUTHORED / UNRUN. Sparse transport fixtures, not renderer/photo acceptance.
use super::{append, append_sclera_purify, enhance_command,
    enhance_command_with_teeth, enhance_command_with_red_eye};
use serde_json::json;

#[test]
fn prior_wrappers_do_not_invent_purification_intent() {
    let commands = [
        enhance_command("set", [None; 8], None).unwrap(),
        enhance_command_with_teeth("set", [None; 8], [Some(0.3), None], None).unwrap(),
        enhance_command_with_red_eye("set", [None; 8], Some(0.4), [None; 2], None).unwrap(),
    ];
    for mut command in commands {
        assert!(command.get("sclera_purify").is_none());
        let before = command.clone();
        append_sclera_purify(&mut command, None).unwrap();
        assert_eq!(command, before);
    }
}

#[test]
fn purification_zero_and_nonzero_remain_explicit_sparse_leaves() {
    for amount in [0.0, 0.4, 1.0] {
        let mut command = enhance_command("set", [None; 8], None).unwrap();
        append_sclera_purify(&mut command, Some(amount)).unwrap();
        assert_eq!(command, json!({"cmd":"enhance","action":"set","sclera_purify":amount}));
    }
}

#[test]
fn purification_does_not_replace_other_enhancement_or_wrinkle_leaves() {
    let mut command = enhance_command_with_red_eye("set",
        [Some(0.1), Some(0.2), Some(0.3), Some(0.4), Some(0.5), Some(0.6), Some(0.7), Some(0.8)],
        Some(0.9), [Some(0.15), Some(0.25)], Some(json!({"wrinkle_forehead":0.35}))).unwrap();
    let before = command.clone();
    append_sclera_purify(&mut command, Some(0.45)).unwrap();
    assert_eq!(command["sclera_purify"], json!(0.45));
    command.as_object_mut().unwrap().remove("sclera_purify");
    assert_eq!(command, before);
}

#[test]
fn rejected_purification_never_mutates_the_envelope() {
    for amount in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY, -0.01, 1.01] {
        let mut command = json!({"cmd":"enhance","action":"set","sclera":0.2});
        let before = command.clone();
        assert!(append_sclera_purify(&mut command, Some(amount)).is_err());
        assert_eq!(command, before);
    }
    let mut command = json!([]);
    assert!(append_sclera_purify(&mut command, Some(0.5)).is_err());
    assert_eq!(command, json!([]));
}

#[test]
fn wrinkle_metadata_cannot_smuggle_a_purification_leaf() {
    let mut command = enhance_command("set", [None; 8], None).unwrap();
    let before = command.clone();
    assert!(append(&mut command, Some(json!({"sclera_purify":0.8}))).is_err());
    assert_eq!(command, before);
}
