// SPDX-License-Identifier: GPL-3.0-or-later
//! Rules-only catalogue. No image identity, anchors, rectangle, review or planner.
//! Shared source module using the native host's already-declared serde crates.
use serde::{Deserialize, Serialize};
use std::collections::HashSet;

pub const SCHEMA: &str = "lrt.portrait-crop-rule-catalogue.v1";
pub const MAX_ENTRIES: usize = 256;
pub const MAX_BYTES: usize = 256 * 1024;
pub const MAX_REVISION: u64 = 9_007_199_254_740_991;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Rules {
    pub aspect_ratio: f64,
    pub headroom_fraction: f64,
    pub head_fraction: f64,
    pub horizontal_position: f64,
}
impl Rules {
    pub fn validate(&self) -> Result<(), String> {
        if ![self.aspect_ratio, self.headroom_fraction, self.head_fraction, self.horizontal_position].iter().all(|v| v.is_finite())
            || !(0.001..=1000.0).contains(&self.aspect_ratio)
            || !(0.0..=1.0).contains(&self.headroom_fraction)
            || self.head_fraction <= 0.0 || self.head_fraction > 1.0
            || !(0.0..=1.0).contains(&self.horizontal_position)
            || self.headroom_fraction + self.head_fraction > 1.0 {
            return Err("构图规则超出本地范围或留白与头部占比之和超过 1；没有保存".into());
        }
        Ok(())
    }
}
pub fn name(value: &str) -> Result<(), String> {
    if value.is_empty() || value.chars().count() > 64 || value.len() > 192 || value.trim() != value
        || value.chars().any(|c| c.is_control() || (c.is_whitespace() && c != ' ')
            || matches!(c as u32, 0x200b..=0x200f | 0x202a..=0x202e | 0x2060..=0x206f | 0xfeff)) {
        return Err("名称须为 1–64 个可见字符、最多 192 UTF-8 字节，不含首尾空白或控制字符".into());
    }
    Ok(())
}
fn catalogue_id(value: &str) -> bool { value.len() == 32 && value.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)) }
fn entry_revision(value: &str) -> Option<u64> {
    let digits = value.strip_prefix("rule-")?;
    let revision = digits.parse::<u64>().ok()?;
    (revision > 0 && revision <= MAX_REVISION && digits == revision.to_string()).then_some(revision)
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Entry { pub id: String, pub name: String, pub rules: Rules }
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Catalogue {
    pub schema: String,
    pub catalogue_id: String,
    pub revision: u64,
    pub entries: Vec<Entry>,
}
impl Catalogue {
    pub fn empty(id: String) -> Result<Self, String> {
        let result = Self { schema: SCHEMA.into(), catalogue_id: id, revision: 0, entries: Vec::new() };
        result.validate()?; Ok(result)
    }
    pub fn validate(&self) -> Result<(), String> {
        if self.schema != SCHEMA || !catalogue_id(&self.catalogue_id) || self.revision > MAX_REVISION || self.entries.len() > MAX_ENTRIES {
            return Err("构图规则目录版本、身份或容量无效；不会迁移、清空或覆盖".into());
        }
        let mut ids = HashSet::new(); let mut names = HashSet::new();
        for entry in &self.entries {
            if !entry_revision(&entry.id).is_some_and(|revision| revision <= self.revision)
                || !ids.insert(&entry.id) || !names.insert(&entry.name) { return Err("构图规则目录包含重复或无效身份/名称".into()); }
            name(&entry.name)?; entry.rules.validate()?;
        }
        Ok(())
    }
    /// Pure CAS transition. Caller publishes only a successful complete result.
    pub fn change(&self, request: &Request) -> Result<Self, String> {
        self.validate()?;
        let (id, revision) = request.expected().ok_or("列表动作不能修改目录")?;
        if id != self.catalogue_id || revision != self.revision { return Err("目录已变化；本次未修改。请刷新后重新确认，不会自动覆盖".into()); }
        let next_revision = self.revision.checked_add(1).filter(|v| *v <= MAX_REVISION).ok_or("目录修订已达上限")?;
        let mut next = self.clone();
        match request {
            Request::Create { name: new_name, rules, .. } => {
                name(new_name)?; rules.validate()?;
                if next.entries.len() >= MAX_ENTRIES { return Err("最多保存 256 个构图规则预设".into()); }
                if next.entries.iter().any(|entry| &entry.name == new_name) { return Err("同名预设已存在；创建不会覆盖。请明确选择更新或另取名称".into()); }
                next.entries.push(Entry { id: format!("rule-{next_revision}"), name: new_name.clone(), rules: rules.clone() });
            }
            Request::Rename { id, name: new_name, .. } => {
                name(new_name)?;
                if next.entries.iter().any(|entry| entry.id != *id && entry.name == *new_name) { return Err("同名预设已存在；未重命名".into()); }
                let entry = next.entries.iter_mut().find(|entry| &entry.id == id).ok_or("预设已不存在；请刷新")?;
                entry.name = new_name.clone();
            }
            Request::Update { id, rules, .. } => {
                rules.validate()?;
                next.entries.iter_mut().find(|entry| &entry.id == id).ok_or("预设已不存在；请刷新")?.rules = rules.clone();
            }
            Request::Delete { id, .. } => {
                let index = next.entries.iter().position(|entry| &entry.id == id).ok_or("预设已不存在；请刷新")?;
                next.entries.remove(index);
            }
            Request::List => return Err("列表动作不能修改目录".into()),
        }
        // An explicit equal-value update is a confirmed no-op, not a new revision.
        if next.entries == self.entries { return Ok(self.clone()); }
        next.revision = next_revision; next.validate()?; Ok(next)
    }
}
#[derive(Clone, Debug, Deserialize)]
#[serde(tag = "action", rename_all = "snake_case", deny_unknown_fields)]
pub enum Request {
    List,
    Create { catalogue_id: String, expected_revision: u64, name: String, rules: Rules },
    Rename { catalogue_id: String, expected_revision: u64, id: String, name: String },
    Update { catalogue_id: String, expected_revision: u64, id: String, rules: Rules },
    Delete { catalogue_id: String, expected_revision: u64, id: String },
}
impl Request {
    /// Explicit action allowlist also covers the internally tagged unit variant;
    /// never rely on a deserializer discarding extra fields on `list`.
    pub fn parse(bytes: &[u8]) -> Result<Self, String> {
        if bytes.len() > 8192 { return Err("构图预设请求超过 8 KiB".into()); }
        let value: serde_json::Value = serde_json::from_slice(bytes).map_err(|_| "构图预设请求 JSON 无效")?;
        let object = value.as_object().ok_or("构图预设请求必须为对象")?;
        let fields: &[&str] = match object.get("action").and_then(serde_json::Value::as_str) {
            Some("list") => &["action"],
            Some("create") => &["action", "catalogue_id", "expected_revision", "name", "rules"],
            Some("rename") => &["action", "catalogue_id", "expected_revision", "id", "name"],
            Some("update") => &["action", "catalogue_id", "expected_revision", "id", "rules"],
            Some("delete") => &["action", "catalogue_id", "expected_revision", "id"],
            _ => return Err("未知构图预设动作".into()),
        };
        if object.len() != fields.len() || fields.iter().any(|key| !object.contains_key(*key)) { return Err("构图预设请求包含未知字段或缺少必要字段".into()); }
        serde_json::from_value(value).map_err(|_| "构图预设请求字段或数值类型无效".into())
    }
    pub fn expected(&self) -> Option<(&str, u64)> {
        match self {
            Self::List => None,
            Self::Create { catalogue_id, expected_revision, .. } | Self::Rename { catalogue_id, expected_revision, .. }
            | Self::Update { catalogue_id, expected_revision, .. } | Self::Delete { catalogue_id, expected_revision, .. } => Some((catalogue_id, *expected_revision)),
        }
    }
}

#[cfg(test)]
#[path = "tests_unrun.rs"]
mod tests_unrun;
