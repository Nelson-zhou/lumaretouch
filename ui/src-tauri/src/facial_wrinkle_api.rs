// SPDX-License-Identifier: GPL-3.0-or-later
//! Strict sparse enhancement transport. This is not a renderer.
use serde_json::Value;

pub const KEYS: [&str; 10] = [
    "wrinkle_forehead", "wrinkle_glabellar", "wrinkle_eye_area", "wrinkle_nose",
    "wrinkle_nasolabial_left", "wrinkle_nasolabial_right", "wrinkle_cheek",
    "wrinkle_marionette", "wrinkle_mouth_surround", "wrinkle_nasolabial_unlocked",
];

pub fn append(command: &mut Value, patch: Option<Value>) -> Result<(), String> {
    let Some(value) = patch else { return Ok(()); };
    let object = value.as_object().ok_or("面部祛纹参数必须是对象")?;
    if object.len() > KEYS.len() { return Err("面部祛纹参数数量无效".into()); }
    for (key, value) in object {
        if !KEYS.contains(&key.as_str()) { return Err(format!("未知面部祛纹参数：{key}")); }
        let amount = value.as_f64().ok_or("面部祛纹强度必须是有限数值")?;
        if !amount.is_finite() || !(0.0..=1.0).contains(&amount) {
            return Err(format!("面部祛纹强度超出范围：{key}"));
        }
        if key == "wrinkle_nasolabial_unlocked" && amount != 0.0 && amount != 1.0 {
            return Err("法令纹解锁标志只能为 0 或 1".into());
        }
    }
    // Validate all entries before mutating the command envelope.
    for (key, value) in object { command[key.as_str()] = value.clone(); }
    Ok(())
}

/// Build the complete enhance protocol envelope. Existing eye/teeth options
/// remain sparse and independent from the wrinkle-family metadata envelope.
pub fn enhance_command(action: &str, legacy: [Option<f64>; 8], wrinkles: Option<Value>) -> Result<Value, String> {
    enhance_command_with_teeth(action, legacy, [None, None], wrinkles)
}

/// Independent PC-32469 brightness/yellow-removal leaves. Missing values must
/// stay missing: the old combined `teeth` amount is never copied or reset here.
/// The finite [0,1] range is a Linux implementation choice, not a source default.
pub fn enhance_command_with_teeth(action: &str, legacy: [Option<f64>; 8], teeth_colour: [Option<f64>; 2], wrinkles: Option<Value>) -> Result<Value, String> {
    enhance_command_with_red_eye(action, legacy, None, teeth_colour, wrinkles)
}

/// Flash red-eye is independent from sclera veins and iris brightness. Optional
/// omission is not a reset; only an explicit finite zero clears this scalar.
pub fn enhance_command_with_red_eye(action: &str, legacy: [Option<f64>; 8], red_eye: Option<f64>, teeth_colour: [Option<f64>; 2], wrinkles: Option<Value>) -> Result<Value, String> {
    let mut command = serde_json::json!({"cmd":"enhance","action":action});
    let legacy_keys = ["sclera", "iris", "teeth", "dark_circles", "eye_bags", "veins", "catchlight_left", "catchlight_right"];
    let teeth_keys = ["teeth_brightness", "teeth_yellow_removal"];
    for (key, value) in legacy_keys.into_iter().zip(legacy)
        .chain(teeth_keys.into_iter().zip(teeth_colour)).chain([("red_eye", red_eye)]) {
        if let Some(amount) = value {
            if !amount.is_finite() || !(0.0..=1.0).contains(&amount) {
                return Err(format!("人物增强参数超出范围：{key}"));
            }
            command[key] = serde_json::json!(amount);
        }
    }
    append(&mut command, wrinkles)?;
    Ok(command)
}

#[cfg(test)]
#[path = "teeth_colour_api_unrun.rs"]
mod teeth_colour_tests;

#[cfg(test)]
#[path = "red_eye_api_unrun.rs"]
mod red_eye_tests;
