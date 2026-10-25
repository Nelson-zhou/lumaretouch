// SPDX-License-Identifier: GPL-3.0-or-later
//! Bounded sink. Native drivers can still buffer internally; see DEVICE.md.
use crate::{ffi, CancellationToken, Error, ErrorKind, Result, StagingRequest, MAX_LOCAL_NAME_BYTES};
use libc::c_void;
use sha2::{Digest, Sha256};
use std::{ffi::CString, fs::{File, OpenOptions}, io::{Read, Seek, SeekFrom, Write},
    os::unix::{fs::{MetadataExt, OpenOptionsExt}, io::{AsRawFd, FromRawFd}},
    panic::{catch_unwind, AssertUnwindSafe}, path::PathBuf, time::{Duration, Instant}};

pub struct Control { pub token: CancellationToken, pub deadline: Option<Instant> }
impl Control {
    pub fn new(token: CancellationToken, timeout: Duration) -> Self {
        Self { token, deadline: Instant::now().checked_add(timeout) }
    }
    pub fn check(&self) -> Result<()> {
        if self.token.is_cancelled() { return Err(Error::new(ErrorKind::Cancelled, "transfer", "Operation cancelled")); }
        if self.deadline.map_or(false, |deadline| Instant::now() >= deadline) {
            return Err(Error::new(ErrorKind::Timeout, "transfer", "Cooperative operation deadline exceeded"));
        }
        Ok(())
    }
}
pub unsafe extern "C" fn cancel_callback(_: *mut ffi::Context, data: *mut c_void) -> i32 {
    if data.is_null() { return 1; }
    // The boxed Control is stable and outlives Context; no user callback runs.
    if (&*(data as *const Control)).check().is_err() { 1 } else { 0 }
}

pub fn validate_local_name(name: &str) -> Result<()> {
    // String already guarantees valid UTF-8. CString/openat preserve those bytes;
    // an ASCII whitelist would unnecessarily reject Chinese/custom shot names.
    if name.is_empty() || name.len() > MAX_LOCAL_NAME_BYTES || name == "." || name == ".."
        || name.contains('/') || name.contains('\\') || name.chars().any(char::is_control) {
        return Err(Error::new(ErrorKind::InvalidInput, "stage", "Staging name must be a safe UTF-8 component of at most 255 bytes, without separators or control characters"));
    }
    Ok(())
}

pub struct Stage {
    file: File,
    directory: File,
    name: CString,
    pub path: PathBuf,
    committed: bool,
}
impl Stage {
    pub fn create(request: &StagingRequest) -> Result<Self> {
        validate_local_name(&request.local_name)?;
        if !request.directory.is_absolute() {
            return Err(Error::new(ErrorKind::InvalidInput, "stage", "Staging directory must be absolute"));
        }
        let directory = OpenOptions::new().read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&request.directory).map_err(|e| Error::io("stage_directory", e))?;
        let metadata = directory.metadata().map_err(|e| Error::io("stage_directory", e))?;
        if metadata.uid() != unsafe { libc::geteuid() } || metadata.mode() & 0o077 != 0 {
            return Err(Error::new(ErrorKind::Permission, "stage_directory", "Use a private staging directory owned by this user with mode 0700"));
        }
        let name = CString::new(request.local_name.as_bytes())
            .map_err(|_| Error::new(ErrorKind::InvalidInput, "stage", "Invalid staging component"))?;
        let fd = unsafe { libc::openat(directory.as_raw_fd(), name.as_ptr(),
            libc::O_CREAT | libc::O_EXCL | libc::O_RDWR | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            0o600 as libc::mode_t) };
        if fd < 0 { return Err(Error::io("stage_create_exclusive", std::io::Error::last_os_error())); }
        Ok(Self { file: unsafe { File::from_raw_fd(fd) }, directory, name,
            path: request.directory.join(&request.local_name), committed: false })
    }
    fn finish(&mut self, bytes: u64) -> Result<()> {
        self.file.sync_all().map_err(|e| Error::io("stage_sync", e))?;
        if self.file.metadata().map_err(|e| Error::io("stage_metadata", e))?.len() != bytes {
            return Err(Error::new(ErrorKind::Protocol, "stage", "Staging byte count changed"));
        }
        self.directory.sync_all().map_err(|e| Error::io("stage_directory_sync", e))?;
        self.committed = true;
        Ok(())
    }
}
impl Drop for Stage {
    fn drop(&mut self) {
        if !self.committed {
            // Only our exclusively-created file, relative to the pinned private
            // directory descriptor. Never camera paths or user import originals.
            unsafe { libc::unlinkat(self.directory.as_raw_fd(), self.name.as_ptr(), 0); }
        }
    }
}

enum Sink { Disk(Stage), Memory(Vec<u8>), Retired }
pub struct Transfer {
    sink: Sink,
    pub bytes: u64,
    limit: u64,
    read_position: u64,
    hash: Sha256,
    pub failure: Option<Error>,
    control: Control,
}
impl Transfer {
    pub fn disk(request: &StagingRequest, cancel: &CancellationToken) -> Result<Self> {
        Ok(Self::new(Sink::Disk(Stage::create(request)?), request.max_bytes, cancel, request.timeout))
    }
    pub fn memory(limit: u64, cancel: &CancellationToken) -> Self {
        Self::new(Sink::Memory(Vec::new()), limit, cancel, Duration::from_secs(15))
    }
    fn new(sink: Sink, limit: u64, cancel: &CancellationToken, timeout: Duration) -> Self {
        Self { sink, bytes: 0, limit, read_position: 0, hash: Sha256::new(), failure: None,
            control: Control::new(cancel.clone(), timeout) }
    }
    fn write(&mut self, input: &[u8]) -> Result<()> {
        self.control.check()?;
        let next = self.bytes.checked_add(input.len() as u64)
            .filter(|v| *v <= self.limit)
            .ok_or_else(|| Error::new(ErrorKind::SizeLimit, "transfer", "Transfer exceeds explicit byte limit"))?;
        match &mut self.sink {
            Sink::Disk(stage) => {
                stage.file.seek(SeekFrom::End(0)).map_err(|e| Error::io("stage_seek", e))?;
                stage.file.write_all(input).map_err(|e| Error::io("stage_write", e))?;
            }
            Sink::Memory(bytes) => {
                bytes.try_reserve(input.len()).map_err(|_| Error::new(ErrorKind::SizeLimit, "preview", "Cannot reserve bounded preview memory"))?;
                bytes.extend_from_slice(input);
            }
            Sink::Retired => return Err(Error::new(ErrorKind::Closed, "transfer", "Transfer callback has been retired")),
        }
        self.hash.update(input);
        self.bytes = next;
        Ok(())
    }
    fn read(&mut self, output: &mut [u8]) -> Result<usize> {
        self.control.check()?;
        let count = (self.bytes.saturating_sub(self.read_position)).min(output.len() as u64) as usize;
        match &mut self.sink {
            Sink::Disk(stage) => {
                stage.file.seek(SeekFrom::Start(self.read_position)).map_err(|e| Error::io("stage_seek", e))?;
                stage.file.read_exact(&mut output[..count]).map_err(|e| Error::io("stage_read", e))?;
            }
            Sink::Memory(bytes) => output[..count].copy_from_slice(&bytes[self.read_position as usize..self.read_position as usize + count]),
            Sink::Retired => return Err(Error::new(ErrorKind::Closed, "transfer", "Transfer callback has been retired")),
        }
        self.read_position += count as u64;
        Ok(count)
    }
    pub fn complete_disk(&mut self) -> Result<(PathBuf, u64, String)> {
        self.control.check()?;
        if let Some(error) = self.failure.take() { return Err(error); }
        if self.bytes == 0 { return Err(Error::new(ErrorKind::Protocol, "transfer", "Empty original was not accepted")); }
        let digest = format!("{:x}", self.hash.clone().finalize());
        match &mut self.sink {
            Sink::Disk(stage) => { stage.finish(self.bytes)?; Ok((stage.path.clone(), self.bytes, digest)) }
            _ => Err(Error::new(ErrorKind::Protocol, "transfer", "Wrong sink type")),
        }
    }
    pub fn complete_memory(&mut self) -> Result<Vec<u8>> {
        self.control.check()?;
        if let Some(error) = self.failure.take() { return Err(error); }
        match std::mem::replace(&mut self.sink, Sink::Retired) {
            Sink::Memory(bytes) if !bytes.is_empty() => Ok(bytes),
            _ => Err(Error::new(ErrorKind::Protocol, "preview", "Empty preview or wrong sink")),
        }
    }
    pub fn retire(&mut self) {
        // A camlib may have retained a CameraFile ref. Keep this tombstone and
        // its handler address alive until camera teardown, but not image bytes.
        self.sink = Sink::Retired;
        self.failure = Some(Error::new(ErrorKind::Closed, "transfer", "Transfer callback has been retired"));
    }
}

// libgphoto2 retains pointers to BOTH handler and private data until gp_file_unref.
// The caller boxes them and keeps tombstones until camera teardown, because an
// additional camera filesystem/cache reference can outlive its own unref call.
pub fn handler() -> Box<ffi::CameraFileHandler> {
    Box::new(ffi::CameraFileHandler { size: Some(size_callback), read: Some(read_callback), write: Some(write_callback) })
}
unsafe extern "C" fn size_callback(data: *mut c_void, size: *mut u64) -> i32 {
    if data.is_null() || size.is_null() { return ffi::BAD_PARAMETERS; }
    let transfer = &mut *(data as *mut Transfer);
    if transfer.failure.is_some() { *size = 0; return ffi::IO_WRITE; }
    // gp_file_get_data_and_size calls size then read for a fresh complete copy;
    // do not return EOF/uninitialized native output on its second invocation.
    transfer.read_position = 0;
    *size = transfer.bytes;
    0
}
unsafe extern "C" fn write_callback(data: *mut c_void, bytes: *mut u8, length: *mut u64) -> i32 {
    io_callback(data, bytes, length, true)
}
unsafe extern "C" fn read_callback(data: *mut c_void, bytes: *mut u8, length: *mut u64) -> i32 {
    io_callback(data, bytes, length, false)
}
unsafe fn io_callback(data: *mut c_void, bytes: *mut u8, length: *mut u64, write: bool) -> i32 {
    if data.is_null() || length.is_null() { return ffi::BAD_PARAMETERS; }
    let transfer = &mut *(data as *mut Transfer);
    let requested = *length;
    *length = 0;
    if transfer.failure.is_some() { return ffi::IO_WRITE; }
    // Check count BEFORE constructing a native slice, including addressable size.
    if requested > isize::MAX as u64 || requested > transfer.limit || (requested != 0 && bytes.is_null()) {
        transfer.failure = Some(Error::new(ErrorKind::SizeLimit, "transfer", "Invalid or oversized native chunk"));
        return ffi::IO_WRITE;
    }
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<u64> {
        if requested == 0 { transfer.control.check()?; return Ok(0); }
        if write {
            transfer.write(std::slice::from_raw_parts(bytes, requested as usize))?;
            Ok(requested)
        } else {
            Ok(transfer.read(std::slice::from_raw_parts_mut(bytes, requested as usize))? as u64)
        }
    }));
    match result {
        Ok(Ok(count)) => { *length = count; 0 }
        Ok(Err(error)) => { let code = if error.kind == ErrorKind::Cancelled { ffi::CANCEL } else { ffi::IO_WRITE }; transfer.failure = Some(error); code }
        Err(_) => { transfer.failure = Some(Error::new(ErrorKind::Protocol, "transfer", "Transfer callback panic contained")); ffi::IO_WRITE }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    // Authored fixtures only: UNRUN, do not connect a camera or load a library.
    #[test]
    fn callback_bounds_before_mutation() {
        let mut transfer = Transfer::memory(3, &CancellationToken::default());
        transfer.write(b"abc").unwrap();
        assert_eq!(transfer.write(b"d").unwrap_err().kind, ErrorKind::SizeLimit);
        assert_eq!(transfer.bytes, 3);
    }
    #[test]
    fn stream_hash_known_vector() {
        let mut transfer = Transfer::memory(3, &CancellationToken::default());
        transfer.write(b"a").unwrap(); transfer.write(b"bc").unwrap();
        assert_eq!(format!("{:x}", transfer.hash.finalize()), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    }
    #[test]
    fn cancellation_rejects_before_bytes() {
        let token = CancellationToken::default(); token.cancel();
        let mut transfer = Transfer::memory(3, &token);
        assert_eq!(transfer.write(b"abc").unwrap_err().kind, ErrorKind::Cancelled);
        assert_eq!(transfer.bytes, 0);
    }
    #[test]
    fn retained_callback_tombstone_rejects_late_access() {
        let mut transfer = Transfer::memory(3, &CancellationToken::default());
        transfer.write(b"abc").unwrap();
        transfer.retire();
        let mut bytes = [0_u8; 3];
        let mut len = 3_u64;
        let code = unsafe { read_callback((&mut transfer as *mut Transfer).cast(), bytes.as_mut_ptr(), &mut len) };
        assert_ne!(code, 0);
        assert_eq!(len, 0);
        assert_eq!(bytes, [0; 3]);
    }
    #[test]
    fn repeated_native_size_read_starts_a_fresh_copy() {
        let mut transfer = Transfer::memory(3, &CancellationToken::default());
        transfer.write(b"abc").unwrap();
        for _ in 0..2 {
            let mut size = 0;
            let mut output = [0_u8; 3];
            let pointer = (&mut transfer as *mut Transfer).cast();
            assert_eq!(unsafe { size_callback(pointer, &mut size) }, 0);
            assert_eq!(unsafe { read_callback(pointer, output.as_mut_ptr(), &mut size) }, 0);
            assert_eq!(&output, b"abc");
        }
    }
    #[test]
    fn oversized_native_callback_never_reads_foreign_bytes() {
        let mut transfer = Transfer::memory(3, &CancellationToken::default());
        let mut size = 4;
        let code = unsafe { write_callback((&mut transfer as *mut Transfer).cast(), std::ptr::null_mut(), &mut size) };
        assert_ne!(code, 0);
        assert_eq!(size, 0);
        assert_eq!(transfer.bytes, 0);
    }
}
