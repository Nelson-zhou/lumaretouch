//! Private no-follow, single-writer persistence. A failed publication fences
//! the host; neither a missing response nor a restart authorizes redispatch.
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{fs::{self, File, OpenOptions}, io::{Read, Write}, path::{Component, Path, PathBuf}};

const LIMIT: usize = 16 * 1024 * 1024;
pub fn hash(bytes: &[u8]) -> String { format!("{:x}", Sha256::digest(bytes)) }
pub fn fingerprint<T: serde::Serialize>(value: &T) -> Result<String, String> {
    Ok(hash(&serde_json::to_vec(value).map_err(|e| e.to_string())?))
}
pub fn uuid() -> Result<String, String> {
    let mut bytes = [0_u8; 16];
    File::open("/dev/urandom").and_then(|mut file| file.read_exact(&mut bytes)).map_err(|e| e.to_string())?;
    bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    let text: String = bytes.iter().map(|byte| format!("{byte:02x}")).collect();
    Ok(format!("{}-{}-{}-{}-{}", &text[..8], &text[8..12], &text[12..16], &text[16..20], &text[20..]))
}
pub fn now() -> Result<u64, String> {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|duration| duration.as_secs()).map_err(|e| e.to_string())
}
pub fn timestamp(seconds: u64) -> Result<String, String> {
    let seconds: libc::time_t = seconds.try_into().map_err(|_| "系统时间超出范围")?;
    let mut tm: libc::tm = unsafe { std::mem::zeroed() };
    if unsafe { libc::gmtime_r(&seconds, &mut tm) }.is_null() { return Err("无法读取 UTC 时间".into()); }
    Ok(format!("{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z", tm.tm_year + 1900, tm.tm_mon + 1,
        tm.tm_mday, tm.tm_hour, tm.tm_min, tm.tm_sec))
}
/// Capture an existing directory capability by no-follow traversal. The exact
/// device/inode survives in the preflight token and run, not a fresh send stat.
fn directory_handle(path: &Path) -> Result<File, String> {
    use std::{ffi::CString, os::unix::{fs::OpenOptionsExt, io::{AsRawFd, FromRawFd}}};
    if !path.is_absolute() { return Err("目录能力需要绝对路径".into()); }
    let mut file = OpenOptions::new().read(true).custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open("/").map_err(|e| e.to_string())?;
    for part in path.components() {
        match part {
            Component::RootDir => (),
            Component::Normal(name) => {
                let name = CString::new(name.as_encoded_bytes()).map_err(|_| "目录名称包含空字节")?;
                let fd = unsafe { libc::openat(file.as_raw_fd(), name.as_ptr(), libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC) };
                if fd < 0 { return Err(std::io::Error::last_os_error().to_string()); }
                file = unsafe { File::from_raw_fd(fd) };
            }
            _ => return Err("目录路径不规范".into()),
        }
    }
    Ok(file)
}
pub fn pin_directory(path: &Path) -> Result<[String; 2], String> {
    use std::os::unix::fs::MetadataExt;
    let meta = directory_handle(path)?.metadata().map_err(|e| e.to_string())?;
    Ok([meta.dev().to_string(), meta.ino().to_string()])
}
fn open_at(directory: &File, name: &str, flags: i32, mode: libc::mode_t) -> std::io::Result<File> {
    use std::{ffi::CString, os::unix::io::{AsRawFd, FromRawFd}};
    let name = CString::new(name).map_err(|_| std::io::Error::new(std::io::ErrorKind::InvalidInput, "invalid private filename"))?;
    let fd = unsafe { libc::openat(directory.as_raw_fd(), name.as_ptr(), flags | libc::O_NOFOLLOW | libc::O_CLOEXEC, mode) };
    if fd < 0 { return Err(std::io::Error::last_os_error()); }
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn directory(path: &Path) -> Result<(), String> {
    if !path.is_absolute() { return Err("私有日志路径必须是绝对路径".into()); }
    let mut current = PathBuf::new();
    for part in path.components() {
        if matches!(part, Component::CurDir | Component::ParentDir) { return Err("日志路径未规范化".into()); }
        current.push(part.as_os_str());
        let meta = fs::symlink_metadata(&current).map_err(|e| e.to_string())?;
        if !meta.is_dir() || meta.file_type().is_symlink() { return Err("日志目录包含符号链接或非目录".into()); }
    }
    Ok(())
}

pub struct Store { pub root: PathBuf, directory: File, root_identity: [String; 2], _lock: File, poisoned: bool }
impl Store {
    pub fn open(app_data: &Path) -> Result<(Self, Option<Value>), String> {
        use std::os::unix::{fs::{DirBuilderExt, MetadataExt}, io::AsRawFd};
        // Only application-owned storage may be created here. Input/project,
        // managed originals and output roots are never created by this host.
        fs::create_dir_all(app_data).map_err(|e| e.to_string())?;
        directory(app_data)?;
        // If this is the first launch, directory entries in newly created
        // ancestors must be durable before any later external effect is sent.
        for ancestor in app_data.ancestors() {
            directory_handle(ancestor)?.sync_all().map_err(|e| e.to_string())?;
        }
        let root = app_data.join("local-workflow-private-v1");
        match fs::DirBuilder::new().mode(0o700).create(&root) {
            Ok(()) => (), Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => (),
            Err(e) => return Err(e.to_string()),
        }
        directory_handle(app_data)?.sync_all().map_err(|e| e.to_string())?;
        directory(&root)?;
        let directory = directory_handle(&root)?;
        let meta = directory.metadata().map_err(|e| e.to_string())?;
        let root_identity = [meta.dev().to_string(), meta.ino().to_string()];
        if meta.uid() != unsafe { libc::geteuid() } || meta.mode() & 0o7777 != 0o700 {
            return Err("工作流私有目录必须属于当前用户且权限为 0700".into());
        }
        let lock = open_at(&directory, "writer.lock", libc::O_RDWR | libc::O_CREAT | libc::O_NONBLOCK, 0o600).map_err(|e| e.to_string())?;
        let lock_meta = lock.metadata().map_err(|e| e.to_string())?;
        if !lock_meta.is_file() || lock_meta.uid() != unsafe { libc::geteuid() } || lock_meta.mode() & 0o077 != 0 || lock_meta.nlink() != 1
            || unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err("工作流日志已被其他宿主持有".into());
        }
        let previous = match open_at(&directory, "workspace.json", libc::O_RDONLY | libc::O_NONBLOCK, 0) {
            Ok(mut file) => {
                let meta = file.metadata().map_err(|e| e.to_string())?;
                if !meta.is_file() || meta.len() > LIMIT as u64 || meta.uid() != unsafe { libc::geteuid() }
                    || meta.mode() & 0o077 != 0 || meta.nlink() != 1 { return Err("工作流日志类型、大小或权限无效".into()); }
                let mut bytes = Vec::new(); (&mut file).take(LIMIT as u64 + 1).read_to_end(&mut bytes).map_err(|e| e.to_string())?;
                if bytes.len() > LIMIT { return Err("工作流日志读取时增长".into()); }
                let envelope: Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
                if envelope["sha256"].as_str() != Some(fingerprint(&envelope["value"])?.as_str()) {
                    return Err("工作流日志校验失败；不会重放任何写入".into());
                }
                Some(envelope["value"].clone())
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => None,
            Err(e) => return Err(e.to_string()),
        };
        if pin_directory(&root)? != root_identity { return Err("读取时工作流私有目录已替换".into()); }
        Ok((Self { root, directory, root_identity, _lock: lock, poisoned: false }, previous))
    }
    fn verify(&self) -> Result<(), String> {
        if pin_directory(&self.root)? != self.root_identity { return Err("工作流私有日志目录已替换；已禁止派发".into()); }
        Ok(())
    }
    pub fn save<T: serde::Serialize>(&mut self, value: &T) -> Result<(), String> {
        use std::{ffi::CString, os::unix::io::AsRawFd};
        if self.poisoned { return Err("日志提交结果待核对；已禁止后续写入".into()); }
        self.verify()?;
        let value = serde_json::to_value(value).map_err(|e| e.to_string())?;
        let bytes = serde_json::to_vec(&serde_json::json!({"sha256":fingerprint(&value)?,"value":value})).map_err(|e| e.to_string())?;
        if bytes.len() > LIMIT { return Err("工作流日志已达到容量上限；不会驱逐原始回执".into()); }
        self.poisoned = true;
        let partial = format!("workspace-{}.partial", uuid()?);
        let mut file = open_at(&self.directory, &partial, libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL, 0o600).map_err(|e| e.to_string())?;
        file.write_all(&bytes).and_then(|_| file.sync_all()).map_err(|e| e.to_string())?;
        drop(file);
        let partial = CString::new(partial).map_err(|_| "私有日志名称无效")?;
        if unsafe { libc::renameat(self.directory.as_raw_fd(), partial.as_ptr(), self.directory.as_raw_fd(), b"workspace.json\0".as_ptr().cast()) } != 0 {
            return Err(std::io::Error::last_os_error().to_string());
        }
        self.directory.sync_all().map_err(|e| e.to_string())?;
        self.verify()?;
        self.poisoned = false;
        Ok(())
    }
    pub fn run_directory(&self, id: &str) -> Result<PathBuf, String> {
        use std::{ffi::CString, os::unix::io::AsRawFd};
        if !super::wire::identity(id) { return Err("无效运行身份".into()); }
        self.verify()?;
        let root = self.root.join(format!("run-{id}"));
        let name = CString::new(format!("run-{id}")).map_err(|_| "运行目录名称无效")?;
        if unsafe { libc::mkdirat(self.directory.as_raw_fd(), name.as_ptr(), 0o700) } != 0 { return Err(std::io::Error::last_os_error().to_string()); }
        self.directory.sync_all().map_err(|e| e.to_string())?;
        self.verify()?;
        Ok(root)
    }
}
