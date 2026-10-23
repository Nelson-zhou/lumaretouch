// AUTHORED / UNRUN. Sparse native protocol fixtures, not renderer acceptance.
use super::{enhance_command, enhance_command_with_teeth};
use serde_json::json;

#[test]
fn legacy_envelope_does_not_introduce_new_amounts() {
    let command = enhance_command("set", [None, None, Some(0.4), None, None, None, None, None], None).unwrap();
    assert_eq!(command, json!({"cmd":"enhance", "action":"set", "teeth":0.4}));
}

#[test]
fn each_new_leaf_is_sparse_and_explicit_zero_is_kept() {
    let command = enhance_command_with_teeth("set", [None; 8], [Some(0.0), None], None).unwrap();
    assert_eq!(command, json!({"cmd":"enhance", "action":"set", "teeth_brightness":0.0}));
    let command = enhance_command_with_teeth("set", [None; 8], [None, Some(0.7)], None).unwrap();
    assert_eq!(command, json!({"cmd":"enhance", "action":"set", "teeth_yellow_removal":0.7}));
}

#[test]
fn combined_legacy_wrinkles_and_independent_tooth_parameters_stay_distinct() {
    let command = enhance_command_with_teeth("set", [Some(0.2), None, Some(0.3), None, None, None, None, None],
        [Some(0.6), Some(0.8)], Some(json!({"wrinkle_forehead":0.4}))).unwrap();
    assert_eq!(command, json!({"cmd":"enhance", "action":"set", "sclera":0.2, "teeth":0.3,
        "teeth_brightness":0.6, "teeth_yellow_removal":0.8, "wrinkle_forehead":0.4}));
}

#[test]
fn nonfinite_and_out_of_range_new_values_are_rejected() {
    for invalid in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY, -0.01, 1.01] {
        assert!(enhance_command_with_teeth("set", [None; 8], [Some(invalid), None], None).is_err());
        assert!(enhance_command_with_teeth("set", [None; 8], [None, Some(invalid)], None).is_err());
    }
    assert!(enhance_command_with_teeth("set", [None; 8], [Some(0.5), None],
        Some(json!({"teeth_yellow_removal":0.5}))).is_err());
    assert!(enhance_command_with_teeth("set", [None; 8], [Some(0.5), None],
        Some(json!({"wrinkle_forehead":true}))).is_err());
}
