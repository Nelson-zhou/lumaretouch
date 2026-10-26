// SPDX-License-Identifier: GPL-3.0-or-later
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{collections::{BTreeMap, BTreeSet}, fmt, fs, path::{Component, Path, PathBuf}};

pub const SCHEMA_VERSION: u32 = 1;
pub const MAX_GRAPH_BYTES: usize = 256 * 1024;
pub const MAX_JOBS: usize = 256;
pub const MAX_FILE_BYTES: u64 = 2 * 1024 * 1024 * 1024;
pub const MAX_LABELS: usize = 64;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct WorkflowError(pub String);
impl fmt::Display for WorkflowError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { write!(f,"{}",self.0) }
}
impl std::error::Error for WorkflowError {}
impl From<std::io::Error> for WorkflowError {
    fn from(error: std::io::Error) -> Self { Self(error.to_string()) }
}
impl From<serde_json::Error> for WorkflowError {
    fn from(error: serde_json::Error) -> Self { Self(error.to_string()) }
}
pub type Result<T> = std::result::Result<T, WorkflowError>;
pub(crate) fn require(condition: bool, message: &str) -> Result<()> {
    if condition { Ok(()) } else { Err(WorkflowError(message.into())) }
}
pub(crate) fn bounded(value: &str, maximum: usize) -> bool {
    !value.is_empty() && value.len() <= maximum && !value.chars().any(char::is_control)
}
pub(crate) fn id(value: &str) -> bool {
    bounded(value, 128) && value.bytes().all(|b| b.is_ascii_alphanumeric() || b"._:-".contains(&b))
}
pub(crate) fn digest(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
pub(crate) fn sha256(value: &[u8]) -> String {
    let bytes = Sha256::digest(value);
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
pub(crate) fn fingerprint<T: Serialize>(value: &T) -> Result<String> {
    Ok(sha256(&serde_json::to_vec(value)?))
}
pub(crate) fn path_text(value: &str) -> bool {
    bounded(value, 4096) && Path::new(value).is_absolute()
        && !Path::new(value).components().any(|c| matches!(c, Component::ParentDir | Component::CurDir))
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorPolicy { Stop, Skip, KeepContinue }

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LabelTarget { Filename, RelativePath }

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LabelRule { pub target: LabelTarget, pub contains: String, pub label: String }

/// Frozen execution intent, NOT a fresh user start acknowledgment.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AutomaticBatchIntent {
    pub schema: String, pub mode: String, pub scope: String, pub source_mode: String, pub originals: String,
    pub save: String, pub collision: String, pub unattended: bool,
    #[serde(default, skip_serializing_if = "Option::is_none", deserialize_with = "explicit_portrait_scope")]
    pub portrait_scope: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none", deserialize_with = "explicit_portrait_scope")]
    pub reference_scope: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none", deserialize_with = "explicit_portrait_scope")]
    pub reference_source_policy: Option<String>,
}
// Missing is legacy scalar scope; explicit null is not an opt-in declaration.
fn explicit_portrait_scope<'de, D: serde::Deserializer<'de>>(deserializer: D) -> std::result::Result<Option<String>, D::Error> {
    String::deserialize(deserializer).map(Some)
}
impl AutomaticBatchIntent {
    pub fn validate(&self) -> Result<()> {
        require(self.schema == "lrt.automatic-batch-intent.v1" && self.mode == "automatic"
            && self.scope == "directory_originals" && self.source_mode == "captured_file_list" && self.originals == "managed_copy_only"
            && self.save == "target_recipe" && self.collision == "fail_no_overwrite" && self.unattended
            && self.portrait_scope.as_deref().map_or(true, |scope| scope == "all_verified_detected_faces")
            && match (self.reference_scope.as_deref(), self.reference_source_policy.as_deref()) {
                (None, None) => true,
                (Some("stored_reference_per_target_fit"), Some("reject_same_source")) => self.portrait_scope.is_none(),
                _ => false,
            },
            "unsupported automatic batch intent; no implicit scope, save or overwrite authority")
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum NodeKind {
    DirectorySource {
        root: String, recursive: bool, include_existing: bool,
        extensions: Vec<String>, settle_ms: u64,
    },
    ManagedImport { project_id: String, project_path: String, managed_root: String },
    PathLabels { rules: Vec<LabelRule> },
    CompatiblePreset { preset_id: String, preset_sha256: String, when_all_labels: Vec<String> },
    AutomaticPreset { preset_id: String, preset_sha256: String, when_all_labels: Vec<String>, intent: AutomaticBatchIntent },
    Export { output_root: String, recipe_sha256: String },
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Node { pub id: String, pub error_policy: ErrorPolicy, pub operation: NodeKind }

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Edge { pub from: String, pub to: String }

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Graph {
    pub schema_version: u32,
    pub workflow_id: String,
    pub revision: u64,
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
}

/// Only Graph::validate constructs this; graph content is immutable for a run.
#[derive(Clone, Debug)]
pub struct ValidatedGraph {
    pub(crate) graph: Graph,
    pub(crate) ordered: Vec<Node>,
    pub(crate) sha256: String,
}
impl Graph {
    pub fn from_json(bytes: &[u8]) -> Result<ValidatedGraph> {
        require(bytes.len() <= MAX_GRAPH_BYTES, "workflow definition exceeds 256 KiB")?;
        serde_json::from_slice::<Graph>(bytes)?.validate()
    }
    pub fn validate(self) -> Result<ValidatedGraph> {
        require(self.schema_version == SCHEMA_VERSION, "unsupported workflow schema version")?;
        require(id(&self.workflow_id) && self.revision > 0 && self.revision <= 9_007_199_254_740_991,
            "invalid workflow identity/revision (must fit a JavaScript-safe positive integer)")?;
        require((3..=5).contains(&self.nodes.len()), "v1 requires source, import, optional labels/preset, export")?;
        require(self.edges.len() == self.nodes.len() - 1, "v1 requires one complete linear chain")?;
        let mut nodes = BTreeMap::new();
        let mut labels = BTreeSet::new();
        for node in &self.nodes {
            require(id(&node.id) && nodes.insert(node.id.clone(), node).is_none(), "invalid or duplicate node id")?;
            require(node.error_policy != ErrorPolicy::KeepContinue || matches!(node.operation, NodeKind::CompatiblePreset { .. }),
                "keep_continue is only implemented for a preset with a verified retained document")?;
            match &node.operation {
                NodeKind::DirectorySource { root, extensions, settle_ms, .. } => {
                    require(path_text(root), "source root must be an absolute normalized path")?;
                    require(node.error_policy == ErrorPolicy::Stop, "source discovery failures must stop, not silently lose input")?;
                    require((250..=300_000).contains(settle_ms), "settle_ms must be 250..300000")?;
                    require(!extensions.is_empty() && extensions.len() <= 32, "choose 1..32 explicit image extensions")?;
                    let mut unique = BTreeSet::new();
                    for extension in extensions {
                        require(extension.len() <= 10 && !extension.is_empty()
                            && extension.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit())
                            && unique.insert(extension), "extensions must be unique lowercase names without dots")?;
                    }
                }
                NodeKind::ManagedImport { project_id, project_path, managed_root } => {
                    require(id(project_id) && path_text(project_path) && path_text(managed_root), "invalid managed import project/paths")?;
                }
                NodeKind::PathLabels { rules } => {
                    require(!rules.is_empty() && rules.len() <= MAX_LABELS, "choose 1..64 filename/path label rules")?;
                    for rule in rules {
                        require(bounded(&rule.contains, 256) && bounded(&rule.label, 128), "invalid label match/value")?;
                        labels.insert(rule.label.clone());
                    }
                }
                NodeKind::CompatiblePreset { preset_id, preset_sha256, when_all_labels }
                | NodeKind::AutomaticPreset { preset_id, preset_sha256, when_all_labels, .. } => {
                    if let NodeKind::AutomaticPreset { intent, .. } = &node.operation { intent.validate()?; }
                    require(id(preset_id) && digest(preset_sha256) && when_all_labels.len() <= MAX_LABELS,
                        "preset must pin its identity and content SHA-256")?;
                    let unique: BTreeSet<_> = when_all_labels.iter().collect();
                    require(unique.len() == when_all_labels.len() && when_all_labels.iter().all(|s| bounded(s,128)), "invalid/repeated preset label conditions")?;
                }
                NodeKind::Export { output_root, recipe_sha256 } => {
                    require(path_text(output_root) && digest(recipe_sha256), "export requires an absolute destination and pinned recipe SHA-256")?;
                }
            }
        }
        let mut incoming: BTreeMap<String, usize> = nodes.keys().map(|s| (s.clone(), 0)).collect();
        let mut outgoing = BTreeMap::new();
        for edge in &self.edges {
            require(nodes.contains_key(&edge.from) && nodes.contains_key(&edge.to) && edge.from != edge.to, "invalid edge endpoints/self-cycle")?;
            require(!matches!(nodes[&edge.from].operation, NodeKind::Export { .. }), "export is terminal and has no output")?;
            require(!matches!(nodes[&edge.to].operation, NodeKind::DirectorySource { .. }), "source has no input")?;
            require(outgoing.insert(edge.from.clone(), edge.to.clone()).is_none(), "branching is not implemented in v1")?;
            let count = incoming.get_mut(&edge.to).expect("validated endpoint");
            *count += 1;
            require(*count <= 1, "fan-in is not implemented in v1")?;
        }
        let starts: Vec<_> = incoming.iter().filter(|(_,n)| **n == 0).map(|(s,_)| s.clone()).collect();
        require(starts.len() == 1, "graph is disconnected or cyclic")?;
        let mut ordered = Vec::new();
        let mut seen = BTreeSet::new();
        let mut cursor = starts[0].clone();
        loop {
            require(seen.insert(cursor.clone()), "graph contains a cycle")?;
            ordered.push((*nodes[&cursor]).clone());
            match outgoing.get(&cursor) { Some(next) => cursor = next.clone(), None => break }
        }
        require(ordered.len() == nodes.len(), "graph is disconnected or cyclic")?;
        require(matches!(ordered[0].operation, NodeKind::DirectorySource { .. })
            && matches!(ordered[1].operation, NodeKind::ManagedImport { .. })
            && matches!(ordered[ordered.len()-1].operation, NodeKind::Export { .. })
            && match &ordered[2..ordered.len()-1] {
                [] => true,
                [node] => matches!(node.operation, NodeKind::PathLabels { .. } | NodeKind::CompatiblePreset { .. } | NodeKind::AutomaticPreset { .. }),
                [labels, preset] => matches!(labels.operation, NodeKind::PathLabels { .. })
                    && matches!(preset.operation, NodeKind::CompatiblePreset { .. } | NodeKind::AutomaticPreset { .. }),
                _ => false,
            },
            "unsupported v1 node order")?;
        if ordered.iter().any(|node| matches!(node.operation, NodeKind::AutomaticPreset { .. })) {
            require(matches!(ordered[0].operation, NodeKind::DirectorySource { include_existing: true, .. }),
                "automatic captured-file jobs require include_existing; future-file watching is a different mode")?;
        }
        for node in &ordered {
            if let NodeKind::CompatiblePreset { when_all_labels, .. } | NodeKind::AutomaticPreset { when_all_labels, .. } = &node.operation {
                require(when_all_labels.iter().all(|s| labels.contains(s)), "preset condition refers to a label no rule can produce")?;
            }
        }
        require(serde_json::to_vec(&self)?.len() <= MAX_GRAPH_BYTES, "workflow definition exceeds 256 KiB")?;
        let sha256 = fingerprint(&self)?;
        Ok(ValidatedGraph { graph: self, ordered, sha256 })
    }
}

impl ValidatedGraph {
    pub fn graph(&self) -> &Graph { &self.graph }
    pub fn digest(&self) -> &str { &self.sha256 }
    pub fn ordered_nodes(&self) -> &[Node] { &self.ordered }
    pub fn source(&self) -> &Node { &self.ordered[0] }
    pub fn import(&self) -> &Node { &self.ordered[1] }
    pub fn preset(&self) -> Option<&Node> {
        self.ordered.iter().find(|node| matches!(node.operation, NodeKind::CompatiblePreset { .. } | NodeKind::AutomaticPreset { .. }))
    }
    pub fn automatic(&self) -> bool { self.preset().is_some_and(|node| matches!(node.operation, NodeKind::AutomaticPreset { .. })) }
    pub fn export(&self) -> &Node { self.ordered.last().expect("validated chain") }
    pub fn project_id(&self) -> &str {
        match &self.import().operation { NodeKind::ManagedImport { project_id, .. } => project_id, _ => unreachable!() }
    }
    pub fn labels_for(&self, relative: &str) -> Vec<String> {
        let filename = Path::new(relative).file_name().and_then(|v| v.to_str()).unwrap_or("");
        let mut labels = BTreeSet::new();
        for node in &self.ordered {
            if let NodeKind::PathLabels { rules } = &node.operation {
                for rule in rules {
                    let subject = match rule.target { LabelTarget::Filename => filename, LabelTarget::RelativePath => relative };
                    if subject.contains(&rule.contains) { labels.insert(rule.label.clone()); }
                }
            }
        }
        labels.into_iter().collect()
    }
    /// Read-only, current filesystem check. Adapters must recheck at mutation.
    /// All roots must already exist; no implicit directory creation is performed.
    pub fn preflight_filesystem(&self) -> Result<()> {
        let source = match &self.source().operation { NodeKind::DirectorySource { root, .. } => checked_directory(Path::new(root))?, _ => unreachable!() };
        let (project, managed) = match &self.import().operation {
            NodeKind::ManagedImport { project_path, managed_root, .. } =>
                (checked_regular_file(Path::new(project_path))?, checked_directory(Path::new(managed_root))?),
            _ => unreachable!(),
        };
        let output = match &self.export().operation { NodeKind::Export { output_root, .. } => checked_directory(Path::new(output_root))?, _ => unreachable!() };
        require(!overlap(&source,&output), "source/export roots overlap; exported photos would be re-ingested")?;
        require(!overlap(&source,&managed), "source/managed roots overlap; managed copies would be re-ingested")?;
        require(!overlap(&managed,&output), "managed originals and export destinations must be disjoint")?;
        require(!project.starts_with(&source) && !project.starts_with(&managed) && !project.starts_with(&output),
            "saved project must not reside inside watched, managed or output roots")
    }
}
pub(crate) fn overlap(a: &Path, b: &Path) -> bool { a.starts_with(b) || b.starts_with(a) }

/// Refuse symlink ancestors and non-normalized names. This is preflight, not an
/// openat security lease; mutation owners still enforce their own nofollow/CAS.
pub(crate) fn checked_path(path: &Path) -> Result<PathBuf> {
    let text = path.to_str().ok_or_else(|| WorkflowError("non-UTF-8 paths are unsupported in v1".into()))?;
    require(path_text(text), "path must be absolute, normalized and UTF-8")?;
    let mut current = PathBuf::new();
    for part in path.components() {
        current.push(part.as_os_str());
        require(!fs::symlink_metadata(&current)?.file_type().is_symlink(), "symlink path components are refused")?;
    }
    Ok(fs::canonicalize(path)?)
}
pub(crate) fn checked_directory(path: &Path) -> Result<PathBuf> {
    let path = checked_path(path)?;
    require(fs::symlink_metadata(&path)?.is_dir(), "configured root is not a directory")?;
    Ok(path)
}
pub(crate) fn checked_regular_file(path: &Path) -> Result<PathBuf> {
    let path = checked_path(path)?;
    require(fs::symlink_metadata(&path)?.is_file(), "path is not a regular file")?;
    Ok(path)
}
