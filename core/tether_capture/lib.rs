// SPDX-License-Identifier: GPL-3.0-or-later
//! Device-only boundary for handbook 47251. No background work starts on import.
//! All authored fixtures are UNRUN. See docs/tether-capture/DEVICE.md.
use std::{fmt, path::PathBuf, sync::{Arc, atomic::{AtomicBool, Ordering}}, time::Duration};

#[cfg(target_os = "linux")]
mod ffi;
#[cfg(target_os = "linux")]
mod linux;
#[cfg(target_os = "linux")]
mod transfer;
#[cfg(target_os = "linux")]
pub use linux::LinuxGphotoDevice;

pub const CONTRACT_VERSION: u32 = 1;
pub const MAX_ORIGINAL_BYTES: u64 = 512 * 1024 * 1024;
pub const MAX_PREVIEW_BYTES: u64 = 16 * 1024 * 1024;
/// Linux filename component bound, measured in UTF-8 bytes, not characters.
pub const MAX_LOCAL_NAME_BYTES: usize = 255;
pub const MAX_WAIT: Duration = Duration::from_millis(1000);

#[derive(Clone, Debug, Default)]
pub struct CancellationToken(Arc<AtomicBool>);
impl CancellationToken {
    pub fn cancel(&self) { self.0.store(true, Ordering::Release); }
    pub fn is_cancelled(&self) -> bool { self.0.load(Ordering::Acquire) }
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct DeviceId { pub model: String, pub port: String }

/// Evidence for one operation, not a claim that every camera mode supports it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Support { Unknown, DriverAdvertised, Verified, Unsupported }
impl Support {
    pub fn can_request(self) -> bool {
        matches!(self, Self::DriverAdvertised | Self::Verified)
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeviceCapabilities {
    /// A successful timeout verifies only event polling, not a physical shutter.
    pub events: Support,
    pub settings: Support,
    pub remote_capture: Support,
    /// Asynchronous shutter trigger, distinct from capture returning a file path.
    pub remote_trigger: Support,
    pub preview: Support,
    pub original_download: Support,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CameraObject { pub folder: String, pub name: String }
impl CameraObject {
    pub(crate) fn validate(&self) -> Result<()> {
        if self.folder.is_empty() || !self.folder.starts_with('/') || self.folder.len() >= 1024
            || self.folder.as_bytes().contains(&0) || self.name.is_empty() || self.name.len() >= 128
            || self.name.as_bytes().contains(&0) || self.name.contains('/') || self.name.contains('\\')
            || self.name == "." || self.name == ".." {
            return Err(Error::new(ErrorKind::InvalidInput, "camera_object", "Invalid camera object path"));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DeviceEvent {
    Timeout,
    FileAdded(CameraObject),
    FileChanged(CameraObject),
    FolderAdded { folder: String, name: String },
    CaptureComplete,
    Unknown { description: Option<String> },
}

#[derive(Clone, Debug, PartialEq)]
pub enum SettingValue { Text(String), Number(f32), Toggle(bool), Timestamp(i32) }
#[derive(Clone, Debug, PartialEq)]
pub struct CameraSetting {
    pub key: String,
    pub label: String,
    pub value: SettingValue,
    /// Camera's metadata only. This adapter never offers a setter.
    pub camera_read_only: bool,
}

/// Host supplies a PRIVATE existing directory (owned by this uid, mode 0700).
/// `local_name` must be an independently chosen safe UTF-8 component, not a
/// camera path. Preserve its exact bytes: no transliteration or silent stripping.
#[derive(Clone, Debug)]
pub struct StagingRequest {
    pub directory: PathBuf,
    pub local_name: String,
    pub max_bytes: u64,
    /// Cooperative, not a hard deadline on a blocked native driver.
    pub timeout: Duration,
}

#[derive(Clone, Debug)]
pub struct DownloadReceipt {
    /// Complete staging file only; not proof of document import or user promotion.
    pub path: PathBuf,
    pub local_name: String,
    pub bytes: u64,
    pub sha256_hex: String,
    pub mime_type: Option<String>,
    pub camera_object: CameraObject,
}

#[derive(Clone, Debug)]
pub struct PreviewFrame {
    pub bytes: Vec<u8>,
    pub mime_type: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ErrorKind {
    Unavailable, Unsupported, InvalidInput, Closed, AlreadyOpen, StaleSelection,
    Cancelled, Timeout, Busy, Permission, Disconnected, Native, Io, SizeLimit, Protocol,
}
#[derive(Clone, Debug)]
pub struct Error {
    pub kind: ErrorKind,
    pub operation: &'static str,
    pub native_code: Option<i32>,
    pub message: String,
    /// In particular: failed remote shutter may already have fired. Do not retry.
    pub outcome_unknown: bool,
}
impl Error {
    pub(crate) fn new(kind: ErrorKind, operation: &'static str, message: impl Into<String>) -> Self {
        Self { kind, operation, native_code: None, message: message.into(), outcome_unknown: false }
    }
    pub(crate) fn io(operation: &'static str, error: std::io::Error) -> Self {
        Self::new(ErrorKind::Io, operation, error.to_string())
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { write!(f, "{}: {}", self.operation, self.message) }
}
impl std::error::Error for Error {}
pub type Result<T> = std::result::Result<T, Error>;

/// Construct and use on ONE dedicated owner thread. This trait deliberately has
/// no Send/Sync bound. The Linux implementation is explicitly !Send and !Sync.
/// A host command queue owns session/occurrence ids, fencing, retries and imports.
pub trait TetherDevicePort {
    fn enumerate(&mut self, cancel: &CancellationToken) -> Result<Vec<DeviceId>>;
    fn open_selected(&mut self, selected: &DeviceId, cancel: &CancellationToken) -> Result<DeviceCapabilities>;
    fn capabilities(&self) -> Result<DeviceCapabilities>;
    fn read_settings(&mut self, cancel: &CancellationToken) -> Result<Vec<CameraSetting>>;
    fn wait_event(&mut self, timeout: Duration, cancel: &CancellationToken) -> Result<DeviceEvent>;
    fn download_to_staging(&mut self, object: &CameraObject, request: &StagingRequest,
        cancel: &CancellationToken) -> Result<DownloadReceipt>;
    /// Explicit optional operation. Never invoked by connect/poll/download.
    fn request_capture(&mut self, cancel: &CancellationToken) -> Result<CameraObject>;
    /// Explicit asynchronous shutter command. Success is only dispatch success,
    /// not a file/import receipt: wait for actual FileAdded events. No retry of
    /// uncertain dispatch and no fallback to request_capture.
    fn trigger_capture(&mut self, cancel: &CancellationToken) -> Result<()>;
    /// One preview only, not an autonomous live-view stream. Never changes config.
    fn capture_preview(&mut self, max_bytes: u64, cancel: &CancellationToken) -> Result<PreviewFrame>;
    /// Idempotent local close; no file delete, format, upload, or config writes.
    fn close(&mut self) -> Result<()>;
}

#[cfg(test)]
mod tests;
