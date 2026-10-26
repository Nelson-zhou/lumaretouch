// SPDX-License-Identifier: GPL-3.0-or-later
//! Bounded, explicit polling, not an event-only watcher and not a background
//! service. Stable metadata is only a debounce hint: completed candidates need
//! a full read/hash and unchanged descriptor AND path identity afterward.
use sha2::{Digest, Sha256};
use serde::{Deserialize,Serialize};
use std::{collections::{BTreeMap,BTreeSet}, fs::{self, File, Metadata, OpenOptions},
    io::Read, path::{Path,PathBuf}, time::{Duration,Instant}};
use crate::{ports::{InputOccurrence, SourceCompletion}, schema::{checked_directory, checked_regular_file,
    fingerprint, require, NodeKind, Result, ValidatedGraph, WorkflowError, MAX_FILE_BYTES}};

pub const MAX_SCAN_ENTRIES: usize = 10_000;
pub const MAX_SCAN_DEPTH: usize = 16;
pub const MAX_OBSERVATIONS: usize = 1024;
pub const MAX_CANDIDATES_PER_POLL: usize = 32;
pub const MAX_HASH_BYTES_PER_POLL: u64 = 2 * 1024 * 1024 * 1024;
const MAX_POLL_TIME: Duration = Duration::from_secs(60);

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Observation {
    stat: [String;5], stable_since: u64, eligible: bool, acknowledged: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DirectoryPoller {
    schema_version: u32,
    graph_sha256: String,
    root: PathBuf,
    root_identity: [String;2],
    recursive: bool,
    include_existing: bool,
    /// Old watched checkpoints deserialize unchanged. New automatic jobs freeze
    /// the first bounded path/stat scan; this is not an atomic FS snapshot.
    #[serde(default, skip_serializing_if = "is_false")]
    captured_file_list: bool,
    extensions: BTreeSet<String>,
    settle_ms: u64,
    previous_tick: Option<u64>,
    baseline_initialized: bool,
    observations: BTreeMap<PathBuf,Observation>,
}
fn is_false(value: &bool) -> bool { !*value }

impl DirectoryPoller {
    pub fn captured_count(&self) -> Option<usize> {
        (self.captured_file_list && self.baseline_initialized).then_some(self.observations.len())
    }
    pub fn capture_admitted(&self) -> bool {
        self.captured_count().is_some() && self.observations.values().all(|item| item.acknowledged)
    }
    pub fn graph_digest(&self) -> &str { &self.graph_sha256 }
    pub fn new(graph: &ValidatedGraph) -> Result<Self> {
        graph.preflight_filesystem()?;
        let NodeKind::DirectorySource { root,recursive,include_existing,extensions,settle_ms } = &graph.source().operation else { unreachable!() };
        let root = checked_directory(Path::new(root))?;
        let root_stat = source_stat(&fs::symlink_metadata(&root)?)?;
        Ok(Self { schema_version: 1, graph_sha256: graph.digest().into(), root,
            root_identity: [root_stat[0].clone(),root_stat[1].clone()], recursive: *recursive,
            include_existing: *include_existing, captured_file_list: graph.automatic(), extensions: extensions.iter().cloned().collect(),
            settle_ms: *settle_ms, previous_tick: None, baseline_initialized: false, observations: BTreeMap::new() })
    }
    /// Persist alongside admissions. Monotonic clock samples are deliberately
    /// not durable: restore always requires a new settling interval.
    pub fn checkpoint(&self) -> Result<String> {
        let pinned_root = self.pin_root()?;
        let mut saved = self.clone();
        saved.previous_tick = None;
        for observation in saved.observations.values_mut() { observation.stable_since = 0; }
        let text = serde_json::to_string(&saved)?;
        require(text.len() <= 1024*1024, "poll checkpoint exceeds 1 MiB")?;
        self.verify_root(&pinned_root)?;
        Ok(text)
    }
    pub fn restore(graph: &ValidatedGraph, checkpoint: &str) -> Result<Self> {
        require(checkpoint.len() <= 1024*1024, "poll checkpoint exceeds 1 MiB")?;
        let mut saved: Self = serde_json::from_str(checkpoint)?;
        let fresh = Self::new(graph)?;
        require(saved.schema_version == 1 && saved.graph_sha256 == fresh.graph_sha256 && saved.root == fresh.root
            && saved.root_identity == fresh.root_identity && saved.recursive == fresh.recursive
            && saved.include_existing == fresh.include_existing && saved.captured_file_list == fresh.captured_file_list && saved.extensions == fresh.extensions
            && saved.settle_ms == fresh.settle_ms && saved.observations.len() <= MAX_OBSERVATIONS,
            "poll checkpoint has stale graph/root identity or unsupported configuration")?;
        for (path,observation) in saved.observations.iter_mut() {
            require(path.starts_with(&fresh.root) && path != &fresh.root && path.to_str().map(crate::schema::path_text).unwrap_or(false),
                "poll checkpoint contains an out-of-root source")?;
            require(observation.stat[..3].iter().all(|v| v.parse::<u64>().is_ok())
                && observation.stat[3..].iter().all(|v| v.parse::<i128>().is_ok()), "invalid checkpoint stat")?;
            observation.stable_since = u64::MAX;
        }
        saved.previous_tick = None;
        Ok(saved)
    }
    /// `monotonic_ms` is an elapsed monotonic host time, not wall-clock time.
    /// First observation never emits a file; a later stable scan must settle.
    /// Return candidates must be durably admitted before acknowledge is called.
    pub fn poll(&mut self, monotonic_ms: u64) -> Result<Vec<InputOccurrence>> {
        let mut staged = self.clone();
        let result = staged.poll_inner(monotonic_ms)?;
        *self = staged;
        Ok(result)
    }
    fn poll_inner(&mut self, monotonic_ms: u64) -> Result<Vec<InputOccurrence>> {
        require(self.previous_tick.map(|tick| monotonic_ms > tick).unwrap_or(true), "poll ticks must strictly increase")?;
        // Keep the original directory object open throughout this poll. A
        // path-based scan alone could otherwise hash a replacement tree.
        let pinned_root = self.pin_root()?;
        let started = Instant::now();
        let first_scan = !self.baseline_initialized;
        let files = if self.captured_file_list && !first_scan {
            // Never rescan the tree or adopt a later arrival/replacement. Each
            // queued original retains the first captured full stat identity.
            let mut captured = BTreeMap::new();
            for (path, observation) in &self.observations {
                if observation.acknowledged { continue; }
                require(started.elapsed() < MAX_POLL_TIME, "captured source verification exceeded its time budget")?;
                let current = checked_regular_file(path).and_then(|_| source_stat(&fs::symlink_metadata(path)?))
                    .map_err(|error| WorkflowError(format!("captured source unavailable: {}: {error}", path.display())))?;
                require(current == observation.stat, &format!("captured source changed: {}; no replacement is adopted", path.display()))?;
                captured.insert(path.clone(), current);
            }
            captured
        } else { self.scan(started)? };
        self.verify_root(&pinned_root)?;
        if !self.captured_file_list { self.observations.retain(|path,_| files.contains_key(path)); }
        let mut candidates = Vec::new();
        let mut hash_budget = MAX_HASH_BYTES_PER_POLL;
        for (path,stat) in files {
            require(started.elapsed() < MAX_POLL_TIME, "bounded directory poll exceeded its time budget")?;
            if !self.observations.get(&path).map(|observed| observed.stat == stat).unwrap_or(false) {
                self.observations.insert(path.clone(),Observation { stat, stable_since: monotonic_ms,
                    eligible: !first_scan || self.include_existing, acknowledged: false });
                continue;
            }
            let observed = self.observations.get_mut(&path).expect("observation retained");
            if observed.stable_since == u64::MAX { observed.stable_since = monotonic_ms; continue; }
            if !observed.eligible || observed.acknowledged || monotonic_ms - observed.stable_since < self.settle_ms { continue; }
            if candidates.len() >= MAX_CANDIDATES_PER_POLL { continue; }
            let size = observed.stat[2].parse::<u64>().map_err(|_| WorkflowError("invalid observed size".into()))?;
            if size > hash_budget { continue; }
            let input = complete_read(&self.root,&path,&observed.stat,started)?;
            self.verify_root(&pinned_root)?;
            hash_budget -= size;
            candidates.push(input);
        }
        require(self.observations.len() <= MAX_OBSERVATIONS, "source observation capacity exceeded")?;
        self.verify_root(&pinned_root)?;
        self.previous_tick = Some(monotonic_ms);
        self.baseline_initialized = true;
        Ok(candidates)
    }
    /// Call only after DurableRunner::admit returned success (including an exact
    /// already-retained occurrence). Never acknowledge on send/timeout alone.
    pub fn acknowledge(&mut self, input: &InputOccurrence) -> Result<()> {
        let pinned_root = self.pin_root()?;
        input.validate()?;
        let path = PathBuf::from(&input.source_path);
        require(self.root.join(&input.relative_path) == path, "acknowledgment belongs to a different source root")?;
        let observation = self.observations.get(&path).ok_or_else(|| WorkflowError("source observation is no longer retained".into()))?;
        require(observation.stat == input.source_stat, "source changed before admission acknowledgment")?;
        self.verify_root(&pinned_root)?;
        self.observations.get_mut(&path).expect("observation retained").acknowledged = true;
        Ok(())
    }
    pub(crate) fn pin_root(&self) -> Result<File> {
        require(checked_directory(&self.root)? == self.root, "watched root changed")?;
        let mut options = OpenOptions::new();
        options.read(true);
        #[cfg(unix)] {
            use std::os::unix::fs::OpenOptionsExt;
            options.custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC);
        }
        let file = options.open(&self.root)?;
        self.verify_root(&file)?;
        Ok(file)
    }
    pub(crate) fn verify_root(&self, pinned: &File) -> Result<()> {
        require(checked_directory(&self.root)? == self.root, "watched root path changed during poll")?;
        let descriptor_metadata = pinned.metadata()?;
        let path_metadata = fs::symlink_metadata(&self.root)?;
        require(descriptor_metadata.is_dir() && path_metadata.is_dir(), "watched root is no longer a directory")?;
        let descriptor = source_stat(&descriptor_metadata)?;
        let current = source_stat(&path_metadata)?;
        require(self.root_identity == [descriptor[0].clone(),descriptor[1].clone()]
            && self.root_identity == [current[0].clone(),current[1].clone()],
            "watched root identity changed during poll; re-arm explicitly")
    }
    fn scan(&self, started: Instant) -> Result<BTreeMap<PathBuf,[String;5]>> {
        let mut files = BTreeMap::new();
        let mut directories = vec![(self.root.clone(),0usize)];
        let mut entries = 0;
        while let Some((directory,depth)) = directories.pop() {
            require(started.elapsed() < MAX_POLL_TIME, "bounded directory scan exceeded its time budget")?;
            checked_directory(&directory)?;
            for entry in fs::read_dir(directory)? {
                entries += 1;
                require(entries <= MAX_SCAN_ENTRIES, "directory traversal exceeds 10000 entries")?;
                let entry = entry?;
                let kind = entry.file_type()?;
                require(!kind.is_symlink(), "symlink in watched tree is refused")?;
                if kind.is_dir() {
                    if self.recursive {
                        require(depth < MAX_SCAN_DEPTH, "watched tree exceeds depth 16")?;
                        directories.push((entry.path(),depth+1));
                    }
                    continue;
                }
                let path = entry.path();
                let Some(extension) = path.extension().and_then(|s| s.to_str()).map(str::to_ascii_lowercase) else { continue; };
                if !self.extensions.contains(&extension) { continue; }
                require(kind.is_file(), "image candidate is not a regular file")?;
                require(files.len() < MAX_OBSERVATIONS, "source observation capacity exceeded")?;
                let metadata = fs::symlink_metadata(&path)?;
                require(metadata.is_file() && metadata.len() <= MAX_FILE_BYTES, "source is not a bounded regular file")?;
                // Empty/in-progress files are observed but not offered until
                // they change and then complete a stable full read.
                if metadata.len() == 0 {
                    require(!self.captured_file_list, &format!("captured source is empty/incomplete: {}", path.display()))?;
                    continue;
                }
                files.insert(path,source_stat(&metadata)?);
            }
        }
        Ok(files)
    }
}

fn complete_read(root: &Path,path: &Path,expected: &[String;5],started: Instant) -> Result<InputOccurrence> {
    require(checked_regular_file(path)?.starts_with(root), "candidate escaped source root")?;
    let mut file = open_source(path)?;
    let before = source_stat(&file.metadata()?)?;
    require(&before == expected, "source changed before full-byte completion read")?;
    let mut buffer = vec![0u8;1024*1024];
    let mut hash = Sha256::new();
    let mut size = 0u64;
    loop {
        require(started.elapsed() < MAX_POLL_TIME, "full-byte completion read exceeded poll time budget")?;
        let count = file.read(&mut buffer)?;
        if count == 0 { break; }
        size = size.checked_add(count as u64).ok_or_else(|| WorkflowError("source size overflow".into()))?;
        require(size <= MAX_FILE_BYTES, "source exceeds 2 GiB")?;
        hash.update(&buffer[..count]);
    }
    let after = source_stat(&file.metadata()?)?;
    let resolved = checked_regular_file(path)?;
    let current = source_stat(&fs::symlink_metadata(&resolved)?)?;
    require(before == after && before == current && before[2] == size.to_string(), "source changed during full-byte completion read")?;
    let relative_path = path.strip_prefix(root).map_err(|_| WorkflowError("source escaped root".into()))?
        .to_str().ok_or_else(|| WorkflowError("non-UTF-8 source path".into()))?.to_string();
    let source_path = path.to_str().ok_or_else(|| WorkflowError("non-UTF-8 source path".into()))?.to_string();
    let source_sha256: String = hash.finalize().iter().map(|b| format!("{b:02x}")).collect();
    let source_stamp_sha256 = fingerprint(&before)?;
    let occurrence_id = fingerprint(&(&source_path,&relative_path,&before,&source_sha256))?;
    let input = InputOccurrence { occurrence_id,source_path,relative_path,source_sha256,
        size_bytes:size,source_stamp_sha256,source_stat:before,completion:SourceCompletion::StableRead };
    input.validate()?;
    Ok(input)
}
fn open_source(path: &Path) -> Result<File> {
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)] {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK);
    }
    let file = options.open(path)?;
    require(file.metadata()?.is_file(), "source descriptor is not a regular file")?;
    Ok(file)
}
#[cfg(unix)]
fn source_stat(metadata: &Metadata) -> Result<[String;5]> {
    use std::os::unix::fs::MetadataExt;
    Ok([metadata.dev().to_string(),metadata.ino().to_string(),metadata.size().to_string(),
        (metadata.mtime() as i128 * 1_000_000_000 + metadata.mtime_nsec() as i128).to_string(),
        (metadata.ctime() as i128 * 1_000_000_000 + metadata.ctime_nsec() as i128).to_string()])
}
#[cfg(not(unix))]
fn source_stat(_metadata: &Metadata) -> Result<[String;5]> {
    Err(WorkflowError("platform source identity adapter required; v1 managed-import proof uses Unix stat identity".into()))
}
