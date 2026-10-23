//! Call from main.rs export command after accepting target_size: Option<Value>.
//! Engine remains authoritative. Never drop unsupported configuration silently.
use serde_json::Value;

pub fn attach_target_size(command: &mut Value, target_size: Option<Value>) -> Result<(), String> {
    if let Some(policy) = target_size {
        if !policy.is_object() {
            return Err("target_size must be an object".into());
        }
        if command.get("quality").is_some() {
            return Err("quality and target_size are mutually exclusive".into());
        }
        command["target_size"] = policy;
    }
    Ok(())
}
