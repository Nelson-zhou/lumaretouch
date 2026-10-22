// SPDX-License-Identifier: GPL-3.0-or-later
//! Strict sparse transport for the eight-region family. This is not a renderer.
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
    let mut command = serde_json::json!({"cmd":"enhance","action":action});
    let keys = ["sclera", "iris", "teeth", "dark_circles", "eye_bags", "veins", "catchlight_left", "catchlight_right"];
    for (key, value) in keys.into_iter().zip(legacy) {
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
