//! Read-only .lrtcolour selection. No editor command, inference or Start consent.
use serde_json::Value;
use lrt_local_workflow::schema::SemanticArchive;

pub fn checked(value: &Value, path: &str) -> Result<Value, String> {
    let archive: SemanticArchive = serde_json::from_value(value.clone()).map_err(|e| e.to_string())?;
    archive.validate().map_err(|e| e.to_string())?;
    if archive.path != path { return Err("追色归档回执路径与本次选择不同".into()); }
    serde_json::to_value(archive).map_err(|e| e.to_string())
}
