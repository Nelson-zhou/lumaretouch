// AUTHORED / UNRUN. Sparse transport fixtures, not renderer/photo acceptance.
use super::{enhance_command, enhance_command_with_teeth, enhance_command_with_red_eye};
use serde_json::json;

#[test]
fn old_callers_do_not_invent_red_eye_intent() {
    assert_eq!(enhance_command("set", [None; 8], None).unwrap(),
        json!({"cmd":"enhance","action":"set"}));
    assert_eq!(enhance_command_with_teeth("set", [None; 8], [Some(0.3), None], None).unwrap(),
        json!({"cmd":"enhance","action":"set","teeth_brightness":0.3}));
    assert_eq!(enhance_command_with_red_eye("set", [None; 8], None, [None; 2], None).unwrap(),
        json!({"cmd":"enhance","action":"set"}));
}

#[test]
fn red_eye_zero_and_nonzero_are_sparse_explicit_leaves() {
    for value in [0.0, 0.4, 1.0] {
        assert_eq!(enhance_command_with_red_eye("set", [None; 8], Some(value), [None; 2], None).unwrap(),
            json!({"cmd":"enhance","action":"set","red_eye":value}));
    }
}

#[test]
fn red_eye_keeps_sclera_iris_veins_teeth_and_wrinkles_independent() {
    let command = enhance_command_with_red_eye("set",
        [Some(0.1), Some(0.2), Some(0.3), None, None, Some(0.4), Some(0.5), Some(0.6)],
        Some(0.7), [Some(0.8), Some(0.9)], Some(json!({"wrinkle_forehead":0.25}))).unwrap();
    assert_eq!(command, json!({"cmd":"enhance","action":"set","sclera":0.1,"iris":0.2,
        "teeth":0.3,"veins":0.4,"catchlight_left":0.5,"catchlight_right":0.6,"red_eye":0.7,
        "teeth_brightness":0.8,"teeth_yellow_removal":0.9,"wrinkle_forehead":0.25}));
}

#[test]
fn invalid_red_eye_scalars_are_rejected() {
    for invalid in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY, -0.01, 1.01] {
        assert!(enhance_command_with_red_eye("set", [None; 8], Some(invalid), [None; 2], None).is_err());
    }
}

#[test]
fn wrinkle_envelope_cannot_smuggle_or_overwrite_red_eye() {
    for invalid in [json!({"red_eye":0.9}), json!({"wrinkle_forehead":true}), json!([])] {
        assert!(enhance_command_with_red_eye("set", [None; 8], Some(0.4), [None; 2], Some(invalid)).is_err());
    }
}
