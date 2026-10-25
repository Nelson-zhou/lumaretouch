// SPDX-License-Identifier: GPL-3.0-or-later
//! Linux/Unix immutable, checksummed event journal. No eviction/compaction and
//! no claim of exactly-once execution: owners must retain idempotent receipts.
use serde::{Deserialize, Serialize};
use std::{fs::{self, File, OpenOptions}, io::{Read, Write}, path::{Path, PathBuf}};
use crate::{ports::{Command, InputOccurrence, Receipt}, scheduler::{Event, Scheduler},
    schema::{checked_directory, fingerprint, require, Graph, Result, ValidatedGraph, WorkflowError, SCHEMA_VERSION}};

pub const MAX_JOURNAL_RECORDS: usize = 4096;
pub const MAX_RECORD_BYTES: usize = 2 * 1024 * 1024;
pub const MAX_JOURNAL_BYTES: u64 = 64 * 1024 * 1024;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "record", rename_all = "snake_case", deny_unknown_fields)]
enum JournalEvent { Genesis { graph: Graph, run_id: String }, Transition { value: Event } }
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Body { schema_version: u32, sequence: usize, previous_sha256: String, event: JournalEvent }
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Envelope { body: Body, sha256: String }

struct Journal {
    root: PathBuf,
    _lock: File,
    next: usize,
    bytes: u64,
    previous: String,
    poisoned: bool,
}
impl Journal {
    fn acquire(root: &Path) -> Result<Self> {
        let root = checked_directory(root)?;
        let lock = writer_lock(&root.join("writer.lock"))?;
        Ok(Self { root, _lock: lock, next: 0, bytes: 0, previous: "0".repeat(64), poisoned: false })
    }
    fn load(&mut self) -> Result<Vec<JournalEvent>> {
        let mut paths = Vec::new();
        let mut total_entries = 0;
        for entry in fs::read_dir(&self.root)? {
            total_entries += 1;
            require(total_entries <= MAX_JOURNAL_RECORDS * 2 + 1, "journal directory entry bound exceeded")?;
            let entry = entry?;
            let name = entry.file_name().into_string().map_err(|_| WorkflowError("non-UTF-8 journal filename".into()))?;
            require(entry.file_type()?.is_file(), "journal contains nonregular/symlink entry")?;
            if name == "writer.lock" { continue; }
            let metadata = entry.metadata()?;
            self.bytes = self.bytes.checked_add(metadata.len()).ok_or_else(|| WorkflowError("journal size overflow".into()))?;
            require(self.bytes <= MAX_JOURNAL_BYTES, "journal byte capacity reached")?;
            if name.ends_with(".partial") {
                // An interrupted private staging file is never dispatched or
                // promoted by recovery, but it still consumes bounded space.
                require(name.len() == 16 && name.as_bytes()[..8].iter().all(|b| b.is_ascii_digit()), "unexpected journal partial filename")?;
                continue;
            }
            require(name.len() == 13 && name.ends_with(".json") && name.as_bytes()[..8].iter().all(|b| b.is_ascii_digit()), "unexpected file in journal directory")?;
            require(metadata.len() <= MAX_RECORD_BYTES as u64, "oversized journal record")?;
            paths.push(entry.path());
            require(paths.len() <= MAX_JOURNAL_RECORDS, "journal record capacity reached")?;
        }
        paths.sort();
        let mut events = Vec::new();
        for (sequence,path) in paths.iter().enumerate() {
            let expected_name = format!("{sequence:08}.json");
            require(path.file_name().and_then(|n| n.to_str()) == Some(expected_name.as_str()), "journal sequence has a gap")?;
            let mut file = open_read_nofollow(path)?;
            let mut bytes = Vec::new();
            (&mut file).take(MAX_RECORD_BYTES as u64 + 1).read_to_end(&mut bytes)?;
            require(bytes.len() <= MAX_RECORD_BYTES, "journal record grew beyond bound")?;
            let envelope: Envelope = serde_json::from_slice(&bytes)?;
            require(envelope.body.schema_version == SCHEMA_VERSION && envelope.body.sequence == sequence
                && envelope.body.previous_sha256 == self.previous
                && envelope.sha256 == fingerprint(&envelope.body)?, "journal identity/checksum chain is invalid")?;
            self.previous = envelope.sha256;
            self.next += 1;
            events.push(envelope.body.event);
        }
        Ok(events)
    }
    fn append(&mut self, event: JournalEvent) -> Result<()> {
        require(!self.poisoned, "journal write outcome is uncertain; close and reopen/read back before continuing")?;
        require(self.next < MAX_JOURNAL_RECORDS, "journal record capacity reached; no receipt eviction is allowed")?;
        let body = Body { schema_version: SCHEMA_VERSION, sequence: self.next, previous_sha256: self.previous.clone(), event };
        let envelope = Envelope { sha256: fingerprint(&body)?, body };
        let bytes = serde_json::to_vec(&envelope)?;
        require(bytes.len() <= MAX_RECORD_BYTES, "journal record exceeds size bound")?;
        require(self.bytes.saturating_add(bytes.len() as u64 * 2) <= MAX_JOURNAL_BYTES, "journal byte capacity reached")?;
        let partial = self.root.join(format!("{:08}.partial", self.next));
        let published = self.root.join(format!("{:08}.json", self.next));
        // Any error after creating staging data fences this runner. A final
        // record may exist, so a failed append must NEVER expose its command.
        self.poisoned = true;
        let mut file = OpenOptions::new().write(true).create_new(true).open(&partial)?;
        file.write_all(&bytes)?;
        file.sync_all()?;
        drop(file);
        // Exclusive publication; never replace an existing receipt/intent.
        // Unsupported hardlinks fail closed, without a rename-overwrite fallback.
        fs::hard_link(&partial, &published)?;
        File::open(&self.root)?.sync_all()?;
        fs::remove_file(&partial)?;
        File::open(&self.root)?.sync_all()?;
        self.bytes += bytes.len() as u64;
        self.next += 1;
        self.previous = envelope.sha256;
        self.poisoned = false;
        Ok(())
    }
}

/// A single writer, bounded journal and pure reducer. Call step once, deliver
/// the returned exact command, and record its real owner receipt. Another step
/// before a terminal reply always returns a QUERY, never a repeated mutation.
pub struct DurableRunner { journal: Journal, scheduler: Scheduler }
impl DurableRunner {
    /// The caller explicitly creates/selects a private, empty per-run directory.
    /// Source, managed, output and project roots already exist; no copy occurs.
    pub fn create(root: &Path, graph: ValidatedGraph, run_id: String) -> Result<Self> {
        graph.preflight_filesystem()?;
        let selected = checked_directory(root)?;
        for node in graph.ordered_nodes() {
            let managed_tree = match &node.operation {
                crate::schema::NodeKind::DirectorySource { root,.. } => Some(root),
                crate::schema::NodeKind::ManagedImport { managed_root,.. } => Some(managed_root),
                crate::schema::NodeKind::Export { output_root,.. } => Some(output_root),
                _ => None,
            };
            if let Some(path) = managed_tree {
                require(!crate::schema::overlap(&selected,&checked_directory(Path::new(path))?),
                    "private journal directory must be disjoint from source/managed/output trees")?;
            }
        }
        let mut journal = Journal::acquire(root)?;
        require(journal.load()?.is_empty() && journal.bytes == 0, "run journal directory is not empty")?;
        let scheduler = Scheduler::new(graph,run_id)?;
        journal.append(JournalEvent::Genesis { graph: scheduler.graph.graph.clone(), run_id: scheduler.run_id.clone() })?;
        Ok(Self { journal, scheduler })
    }
    /// Recovery never launches effects. If the latest intent has no terminal
    /// receipt, step yields its original-identity query, including preflight.
    pub fn open(root: &Path) -> Result<Self> {
        let mut journal = Journal::acquire(root)?;
        let mut events = journal.load()?.into_iter();
        let (graph,run_id) = match events.next() {
            Some(JournalEvent::Genesis { graph, run_id }) => (graph.validate()?, run_id),
            _ => return Err(WorkflowError("journal has no valid genesis".into())),
        };
        let mut scheduler = Scheduler::new(graph,run_id)?;
        for event in events {
            match event {
                JournalEvent::Transition { value } => scheduler.reduce(&value)?,
                JournalEvent::Genesis { .. } => return Err(WorkflowError("duplicate journal genesis".into())),
            }
        }
        if let Some(command) = scheduler.pending.as_ref().filter(|_| scheduler.pause.is_none()) {
            scheduler.pause = Some(crate::scheduler::PauseReason::UncertainOutcome {
                operation_id: command.identity.operation_id.clone(), detail: "Recovered pending intent: query its original owner before any further effects.".into() });
        }
        Ok(Self { journal, scheduler })
    }
    pub fn state(&self) -> &Scheduler { &self.scheduler }
    /// Sequence of the last known fully persisted journal record (genesis is
    /// zero). A poisoned writer may have an uncertain later record on disk;
    /// callers must still surface that error and perform recovery/readback.
    pub fn durable_sequence(&self) -> u64 { self.journal.next.saturating_sub(1) as u64 }
    /// Scheduler/journal condition only. The host must ALSO confirm actual
    /// owner outcomes and workspace-lease release before UI effects_settled.
    pub fn pending_effects_settled(&self) -> bool {
        !self.journal.poisoned && self.scheduler.pending.is_none()
    }
    /// Reuse the saved baseline on restart, so photos arriving during downtime
    /// are not silently treated as pre-existing files when include_existing=false.
    pub fn source(&self) -> Result<crate::poll::DirectoryPoller> {
        match &self.scheduler.source_checkpoint {
            Some(checkpoint) => crate::poll::DirectoryPoller::restore(&self.scheduler.graph,checkpoint),
            None => crate::poll::DirectoryPoller::new(&self.scheduler.graph),
        }
    }
    /// Complete a bounded scan and persist every admission before acknowledging
    /// it. A failed checkpoint leaves admitted identities queryable; next scan
    /// deduplicates them. No engine effects occur in this method.
    pub fn poll_source(&mut self, source: &mut crate::poll::DirectoryPoller, monotonic_ms: u64) -> Result<usize> {
        self.poll_source_with_limit(source,monotonic_ms,None)
    }
    /// Limit cumulative NEW job admissions to the owner's finite run/lease
    /// budget. Existing jobs (including terminal jobs) keep consuming budget.
    /// Exact duplicates are acknowledged without consuming another slot.
    /// Surplus candidates are neither admitted nor acknowledged: the durable
    /// source checkpoint retains them for explicit subsequent processing.
    /// This does not seal the run, enlarge a lease or authorize a new session.
    pub fn poll_source_bounded(&mut self, source: &mut crate::poll::DirectoryPoller,
        monotonic_ms: u64, maximum_jobs: usize) -> Result<usize> {
        require((1..=crate::schema::MAX_JOBS).contains(&maximum_jobs), "owner job budget must be 1..256")?;
        require(self.scheduler.jobs.len() <= maximum_jobs, "existing admissions exceed this owner job budget")?;
        self.poll_source_with_limit(source,monotonic_ms,Some(maximum_jobs))
    }
    fn poll_source_with_limit(&mut self, source: &mut crate::poll::DirectoryPoller,
        monotonic_ms: u64, maximum_jobs: Option<usize>) -> Result<usize> {
        require(!self.scheduler.sealed && matches!(self.scheduler.status(),crate::scheduler::RunStatus::Running), "run is not accepting source polls")?;
        require(source.graph_digest() == self.scheduler.graph.digest(), "source poller belongs to a different workflow revision")?;
        match self.poll_source_inner(source,monotonic_ms,maximum_jobs) {
            Ok(admitted) => Ok(admitted),
            Err(error) => {
                // Source errors are STOP, never skip/keep, including budget
                // exhaustion. If the stop itself cannot persist, fence memory.
                if let Err(stop_error) = self.stop() {
                    self.journal.poisoned = true;
                    return Err(WorkflowError(format!("{error}; stop persistence unavailable: {stop_error}")));
                }
                Err(error)
            }
        }
    }
    fn poll_source_inner(&mut self, source: &mut crate::poll::DirectoryPoller,
        monotonic_ms: u64, maximum_jobs: Option<usize>) -> Result<usize> {
        let mut staged = source.clone();
        let inputs = staged.poll(monotonic_ms)?;
        let mut admitted = 0;
        for input in inputs {
            if self.scheduler.knows_occurrence(&input)? {
                staged.acknowledge(&input)?;
                continue;
            }
            if maximum_jobs.map(|limit| self.scheduler.jobs.len() >= limit).unwrap_or(false) {
                // Keep eligible + unacknowledged in the persisted checkpoint.
                // Do not silently discard a photo or consume a lease slot.
                continue;
            }
            if self.admit(input.clone())? { admitted += 1; }
            staged.acknowledge(&input)?;
        }
        let checkpoint = staged.checkpoint()?;
        if self.scheduler.source_checkpoint.as_ref() != Some(&checkpoint) {
            self.persist(Event::SourceCheckpoint { checkpoint })?;
        }
        *source = staged;
        Ok(admitted)
    }
    fn persist(&mut self, event: Event) -> Result<()> {
        require(!self.journal.poisoned, "journal is fenced pending outcome readback")?;
        let mut next = self.scheduler.clone();
        next.reduce(&event)?;
        self.journal.append(JournalEvent::Transition { value: event })?;
        self.scheduler = next;
        Ok(())
    }
    pub fn admit(&mut self, input: InputOccurrence) -> Result<bool> {
        if self.scheduler.knows_occurrence(&input)? { return Ok(false); }
        self.persist(Event::Admit { input })?;
        Ok(true)
    }
    pub fn seal(&mut self) -> Result<()> {
        if self.scheduler.sealed { return Ok(()); }
        self.persist(Event::Seal)
    }
    pub fn stop(&mut self) -> Result<()> {
        if self.scheduler.stopped { return Ok(()); }
        self.persist(Event::Stop)
    }
    pub fn resume(&mut self) -> Result<()> { self.persist(Event::Resume) }
    pub fn record(&mut self, receipt: Receipt) -> Result<bool> {
        if self.scheduler.last_reply.as_ref() == Some(&receipt) { return Ok(false); }
        self.persist(Event::Receipt { receipt })?;
        Ok(true)
    }
    pub fn step(&mut self) -> Result<Option<Command>> {
        require(!self.journal.poisoned, "journal is fenced pending outcome readback")?;
        let command = self.scheduler.next_command()?;
        if self.scheduler.pending.is_some() { return Ok(command); }
        if let Some(command) = &command {
            // Re-read path safety immediately before every fresh operation.
            // Real owners still perform nofollow/source/CAS checks at commit.
            self.scheduler.graph.preflight_filesystem()?;
            self.persist(Event::Intent { command: command.clone() })?;
        }
        Ok(command)
    }
}

#[cfg(unix)]
fn writer_lock(path: &Path) -> Result<File> {
    use std::os::unix::{fs::OpenOptionsExt, io::AsRawFd};
    let file = OpenOptions::new().read(true).write(true).create(true).truncate(false)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC).mode(0o600).open(path)?;
    require(file.metadata()?.is_file(), "journal writer lock is not a regular file")?;
    // The descriptor owns the lock; a crash releases it. Never delete a lock
    // file to steal ownership from another process.
    if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err(WorkflowError(format!("journal already owned or lock unavailable: {}",std::io::Error::last_os_error())));
    }
    Ok(file)
}
#[cfg(not(unix))]
fn writer_lock(_path: &Path) -> Result<File> {
    Err(WorkflowError("durable journal requires a platform-specific exclusive lock adapter; v1 implements Unix".into()))
}
fn open_read_nofollow(path: &Path) -> Result<File> {
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)] {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC);
    }
    let file = options.open(path)?;
    require(file.metadata()?.is_file(), "journal record is not regular")?;
    Ok(file)
}
