//! Private staging, exact folder capabilities, and crash-visible intent ledger.
//! A process restart never replays camera or engine mutations from this file.
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{ffi::CString, fs::{self, File, OpenOptions}, io::{Read, Write},
    os::unix::{fs::{DirBuilderExt, MetadataExt, OpenOptionsExt}, io::{AsRawFd, FromRawFd}},
    path::{Component, Path, PathBuf}};
use lrt_tether_capture::DownloadReceipt;

pub fn uuid() -> Result<String, String> {
    let mut bytes = [0_u8; 16];
    File::open("/dev/urandom").and_then(|mut f| f.read_exact(&mut bytes)).map_err(|e| e.to_string())?;
    bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    Ok(uuid_text(&bytes))
}
pub fn uuid_text(bytes: &[u8; 16]) -> String {
    let h: String = bytes.iter().map(|v| format!("{v:02x}")).collect();
    format!("{}-{}-{}-{}-{}", &h[..8], &h[8..12], &h[12..16], &h[16..20], &h[20..])
}
pub fn utc_date() -> Result<String, String> {
    let seconds = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_err(|e| e.to_string())?.as_secs();
    let seconds: libc::time_t = seconds.try_into().map_err(|_| "系统时间超出范围")?;
    let mut tm: libc::tm = unsafe { std::mem::zeroed() };
    if unsafe { libc::gmtime_r(&seconds, &mut tm) }.is_null() { return Err("无法读取 UTC 日期".into()); }
    Ok(format!("{:04}{:02}{:02}", tm.tm_year + 1900, tm.tm_mon + 1, tm.tm_mday))
}

pub struct Directory { pub path: PathBuf, pub file: File, device: u64, inode: u64 }
impl Directory {
    pub fn identity(&self) -> [String; 2] { [self.device.to_string(), self.inode.to_string()] }
    /// No symlink at any ancestor. This mirrors the engine's root traversal.
    pub fn open(path: &Path) -> Result<Self, String> {
        let text = path.to_str().ok_or("目录必须是 UTF-8 本地路径")?;
        if !path.is_absolute() || text.len() > 4096 || text.contains('\0')
            || text != "/" && text.split('/').skip(1).any(|v| matches!(v, "" | "." | "..")) {
            return Err("需要规范绝对目录路径".into());
        }
        let mut file = OpenOptions::new().read(true).custom_flags(libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open("/").map_err(|e| e.to_string())?;
        for component in path.components() {
            let Component::Normal(name) = component else { continue };
            let name = CString::new(name.as_encoded_bytes()).map_err(|_| "无效目录分量")?;
            let fd = unsafe { libc::openat(file.as_raw_fd(), name.as_ptr(), libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW) };
            if fd < 0 { return Err(std::io::Error::last_os_error().to_string()); }
            file = unsafe { File::from_raw_fd(fd) };
        }
        let meta = file.metadata().map_err(|e| e.to_string())?;
        Ok(Self { path: path.to_owned(), file, device: meta.dev(), inode: meta.ino() })
    }
    pub fn verify(&self) -> Result<(), String> {
        let current = Self::open(&self.path)?;
        if current.device != self.device || current.inode != self.inode { return Err("所选目录已被替换，请重新选择".into()); }
        Ok(())
    }
    pub fn private(&self) -> Result<(), String> {
        let meta = self.file.metadata().map_err(|e| e.to_string())?;
        if meta.uid() != unsafe { libc::geteuid() } || meta.mode() & 0o7777 != 0o700 {
            return Err("联机私有目录须由当前用户持有且权限为 0700".into());
        }
        Ok(())
    }
    pub fn child(&self, name: &str) -> Result<Self, String> {
        super::wire::component(name)?;
        self.verify()?;
        let name_c = CString::new(name).map_err(|_| "无效目录名称")?;
        if unsafe { libc::mkdirat(self.file.as_raw_fd(), name_c.as_ptr(), 0o700) } != 0 {
            return Err(std::io::Error::last_os_error().to_string());
        }
        self.file.sync_all().map_err(|e| e.to_string())?;
        let child = Self::open(&self.path.join(name))?; child.private()?; Ok(child)
    }
    pub fn writable(&self) -> Result<(), String> {
        self.verify()?;
        // access(2) can lie about a later write; the engine still rechecks and
        // uses exclusive files. This does not create a probe file in user data.
        if unsafe { libc::faccessat(self.file.as_raw_fd(), b".\0".as_ptr().cast(), libc::W_OK, libc::AT_EACCESS) } != 0 {
            return Err("所选目录当前不可写".into());
        }
        Ok(())
    }
}

pub struct Ledger { pub directory: Directory, pub previous: Option<Value> }
impl Ledger {
    pub fn open(app_data: &Path) -> Result<Self, String> {
        fs::create_dir_all(app_data).map_err(|e| e.to_string())?;
        let base = app_data.canonicalize().map_err(|e| e.to_string())?;
        let path = base.join("tether-capture-private");
        match fs::DirBuilder::new().mode(0o700).create(&path) {
            Ok(()) => (), Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => (),
            Err(error) => return Err(error.to_string()),
        }
        let directory = Directory::open(&path)?; directory.private()?;
        let name = CString::new("ledger.json").unwrap();
        let fd = unsafe { libc::openat(directory.file.as_raw_fd(), name.as_ptr(), libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK) };
        let previous = if fd < 0 {
            let error = std::io::Error::last_os_error();
            if error.kind() != std::io::ErrorKind::NotFound { return Err(error.to_string()); }
            None
        } else {
            let mut file = unsafe { File::from_raw_fd(fd) };
            let meta = file.metadata().map_err(|e| e.to_string())?;
            if !meta.is_file() || meta.len() > 4 * 1024 * 1024 || meta.uid() != unsafe { libc::geteuid() }
                || meta.mode() & 0o077 != 0 || meta.nlink() != 1 { return Err("原联机日志类型、权限或长度无效，未开始新会话".into()); }
            let mut bytes = Vec::new(); file.take(4 * 1024 * 1024 + 1).read_to_end(&mut bytes).map_err(|e| e.to_string())?;
            Some(serde_json::from_slice(&bytes).map_err(|_| "原联机日志不能完整读取，未开始新会话")?)
        };
        Ok(Self { directory, previous })
    }
    pub fn save(&self, value: &Value) -> Result<(), String> {
        self.directory.verify()?;
        let bytes = serde_json::to_vec(value).map_err(|e| e.to_string())?;
        if bytes.len() > 4 * 1024 * 1024 { return Err("联机持久化回执容量已满；不会丢弃旧回执".into()); }
        let name = CString::new(format!("ledger-{}.tmp", uuid()?)).map_err(|e| e.to_string())?;
        let fd = unsafe { libc::openat(self.directory.file.as_raw_fd(), name.as_ptr(),
            libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL | libc::O_NOFOLLOW | libc::O_CLOEXEC, 0o600 as libc::mode_t) };
        if fd < 0 { return Err(std::io::Error::last_os_error().to_string()); }
        let mut file = unsafe { File::from_raw_fd(fd) };
        file.write_all(&bytes).and_then(|_| file.sync_all()).map_err(|e| e.to_string())?;
        let target = CString::new("ledger.json").unwrap();
        if unsafe { libc::renameat(self.directory.file.as_raw_fd(), name.as_ptr(), self.directory.file.as_raw_fd(), target.as_ptr()) } != 0 {
            return Err(std::io::Error::last_os_error().to_string());
        }
        self.directory.file.sync_all().map_err(|e| e.to_string())
    }
    pub fn recovery_needed(&self) -> bool {
        self.previous.as_ref().map_or(false, |old| {
            old["schema"] != 1 || old["pending_requests"].as_array().map_or(true, |v| !v.is_empty())
                || !old["session"].is_null() && old["session"]["phase"] != "stopped"
                || old["engine_pending"] != Value::Null
        })
    }
    pub fn archive_completed(&self) -> Result<(), String> {
        let Some(previous) = self.previous.as_ref() else { return Ok(()) };
        if self.recovery_needed() { return Err("原联机会话尚未核验结束，不能归档或替换".into()); }
        let count = fs::read_dir(&self.directory.path).map_err(|e| e.to_string())?
            .filter_map(Result::ok).filter(|entry| entry.file_name().to_string_lossy().starts_with("history-")).count();
        if count >= 32 { return Err("已保留 32 份会话日志；需明确整理后再启动，不会自动删除历史回执".into()); }
        let name = CString::new(format!("history-{}.json", uuid()?)).map_err(|e| e.to_string())?;
        let fd = unsafe { libc::openat(self.directory.file.as_raw_fd(), name.as_ptr(),
            libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL | libc::O_CLOEXEC | libc::O_NOFOLLOW, 0o600 as libc::mode_t) };
        if fd < 0 { return Err(std::io::Error::last_os_error().to_string()); }
        let mut file = unsafe { File::from_raw_fd(fd) };
        let bytes = serde_json::to_vec(previous).map_err(|e| e.to_string())?;
        file.write_all(&bytes).and_then(|_| file.sync_all()).map_err(|e| e.to_string())?;
        self.directory.file.sync_all().map_err(|e| e.to_string())
    }
}

fn stamp(meta: &fs::Metadata) -> Result<Vec<String>, String> {
    let ns = |seconds: i64, sub: i64| -> Result<String, String> {
        let value = i128::from(seconds) * 1_000_000_000 + i128::from(sub);
        if value < 0 || value > u64::MAX as i128 { return Err("来源时间戳不能精确表示".into()); }
        Ok(value.to_string())
    };
    Ok(vec![meta.dev().to_string(), meta.ino().to_string(), meta.len().to_string(),
        ns(meta.mtime(), meta.mtime_nsec())?, ns(meta.ctime(), meta.ctime_nsec())?])
}
/// Re-read the entire exclusively staged file. The driver's digest is necessary
/// but not sufficient: verify metadata stability, actual bytes and container.
pub fn completed_source(directory: &Directory, receipt: &DownloadReceipt, occurrence: &str) -> Result<Value, String> {
    directory.verify()?; directory.private()?;
    if receipt.path != directory.path.join(&receipt.local_name) || receipt.bytes == 0
        || receipt.bytes > lrt_tether_capture::MAX_ORIGINAL_BYTES { return Err("原片完成回执路径或大小不匹配".into()); }
    super::wire::component(&receipt.local_name)?;
    let name = CString::new(receipt.local_name.as_str()).map_err(|_| "无效原片名称")?;
    let fd = unsafe { libc::openat(directory.file.as_raw_fd(), name.as_ptr(), libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK) };
    if fd < 0 { return Err(std::io::Error::last_os_error().to_string()); }
    let mut file = unsafe { File::from_raw_fd(fd) };
    let before = file.metadata().map_err(|e| e.to_string())?;
    if !before.is_file() || before.len() != receipt.bytes || before.nlink() != 1
        || before.uid() != unsafe { libc::geteuid() } || before.mode() & 0o077 != 0 { return Err("暂存原片类型、所有者、权限或大小不符".into()); }
    let mut hash = Sha256::new(); let mut count = 0_u64; let mut buffer = [0_u8; 64 * 1024]; let mut header = Vec::new();
    loop {
        let got = file.read(&mut buffer).map_err(|e| e.to_string())?;
        if got == 0 { break; }
        count = count.checked_add(got as u64).filter(|v| *v <= receipt.bytes).ok_or("暂存原片读取时增长")?;
        if header.is_empty() { header.extend_from_slice(&buffer[..got.min(64)]); }
        hash.update(&buffer[..got]);
    }
    let after = file.metadata().map_err(|e| e.to_string())?;
    let sha = format!("{:x}", hash.finalize());
    if stamp(&before)? != stamp(&after)? || count != receipt.bytes || sha != receipt.sha256_hex
        || before.mode() != after.mode() || after.nlink() != 1 { return Err("暂存原片完整校验不一致；未提交导入".into()); }
    let kind = super::wire::format(&receipt.local_name);
    let tiff = header.starts_with(b"II*\0") || header.starts_with(b"MM\0*")
        || header.starts_with(b"IIRO") || header.starts_with(b"IIRS") || header.starts_with(b"IIU\0");
    let raf = header.starts_with(b"FUJIFILMCCD-RAW ");
    let cr3 = header.len() >= 12 && &header[4..8] == b"ftyp" && header[8..].chunks(4).any(|v| v == b"crx ");
    if !(kind == "jpeg" && header.starts_with(&[0xff, 0xd8, 0xff]) || kind == "raw" && (tiff || raf || cr3)) {
        return Err("原片扩展名与已支持 RAW/JPEG 容器不匹配；未导入未知类型".into());
    }
    let path = receipt.path.to_str().ok_or("来源路径不是 UTF-8")?;
    Ok(json!({"path":path,"sha256":sha,"size":count,"stat":stamp(&after)?,
        "occurrence_id":occurrence,"completion":"completed_transfer"}))
}
