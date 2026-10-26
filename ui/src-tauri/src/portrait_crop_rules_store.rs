// SPDX-License-Identifier: GPL-3.0-or-later
//! App-local private Linux catalogue; descriptor-relative no-follow IO, flock,
//! same-directory atomic replace, file+directory fsync. UNRUN source contract.
use crate::portrait_crop_rules_core::{Catalogue, Request, MAX_BYTES};
use serde_json::{json, Value};
use std::{ffi::CString, fs::{File, OpenOptions}, io::{Read, Write},
    os::unix::{fs::{MetadataExt, OpenOptionsExt}, io::{AsRawFd, FromRawFd}},
    path::{Component, Path, PathBuf}};

const TARGET: &str = "catalogue.json";
const TEMP: &str = "catalogue.partial";
struct Store { path: PathBuf, directory: File, identity: (u64, u64), _lock: File }
#[derive(Debug)]
struct Failure { message: String, uncertain: bool }
impl From<String> for Failure { fn from(message: String) -> Self { Self { message, uncertain: false } } }
fn io(error: std::io::Error) -> String { error.to_string() }
fn trusted_directory(file: &File) -> Result<(), String> {
    let meta = file.metadata().map_err(io)?;
    let trusted_owner = meta.uid() == 0 || meta.uid() == unsafe { libc::geteuid() };
    // Root-owned sticky ancestors (e.g. /tmp for isolated test fixtures) protect
    // another user's child from rename. Other group/world-writable parents fail.
    let protected_sticky = meta.uid() == 0 && meta.mode() & 0o1000 != 0;
    if !meta.is_dir() || !trusted_owner || (meta.mode() & 0o022 != 0 && !protected_sticky) {
        return Err("预设目录祖先须由当前用户或 root 持有，且不能被其他用户替换子目录".into());
    }
    Ok(())
}
fn open_directory_at(parent: &File, name: &std::ffi::OsStr) -> std::io::Result<File> {
    let name = CString::new(name.as_encoded_bytes()).map_err(|_| std::io::Error::new(std::io::ErrorKind::InvalidInput, "invalid directory component"))?;
    let fd = unsafe { libc::openat(parent.as_raw_fd(), name.as_ptr(), libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC) };
    if fd < 0 { return Err(std::io::Error::last_os_error()); }
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn mkdir_at(parent: &File, name: &std::ffi::OsStr) -> Result<bool, String> {
    trusted_directory(parent)?;
    let name = CString::new(name.as_encoded_bytes()).map_err(|_| "预设目录名称无效")?;
    if unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o700 as libc::mode_t) } != 0 {
        let error = std::io::Error::last_os_error();
        if error.kind() == std::io::ErrorKind::AlreadyExists { return Ok(false); }
        return Err(io(error));
    }
    parent.sync_all().map_err(io)?;
    Ok(true)
}
fn walk_directory(path: &Path, create: bool) -> Result<File, String> {
    if !path.is_absolute() || path.components().any(|part| !matches!(part, Component::RootDir | Component::Normal(_))) {
        return Err("预设目录必须为规范绝对路径".into());
    }
    let mut current = OpenOptions::new().read(true).custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC).open("/").map_err(io)?;
    trusted_directory(&current)?;
    for component in path.components() {
        match component {
            Component::RootDir => (),
            Component::Normal(name) => {
                current = match open_directory_at(&current, name) {
                    Ok(child) => child,
                    Err(error) if create && error.kind() == std::io::ErrorKind::NotFound => {
                        // Never follow a path-based create through unvalidated
                        // ancestors. The same pinned parent owns mkdir and open.
                        mkdir_at(&current, name)?;
                        open_directory_at(&current, name).map_err(io)?
                    }
                    Err(error) => return Err(io(error)),
                };
                trusted_directory(&current)?;
            }
            _ => return Err("预设目录路径未规范化".into()),
        }
    }
    Ok(current)
}
fn directory(path: &Path) -> Result<File, String> { walk_directory(path, false) }
fn open_at(root: &File, name: &str, flags: i32) -> std::io::Result<File> {
    let name = CString::new(name).map_err(|_| std::io::Error::new(std::io::ErrorKind::InvalidInput, "invalid catalogue filename"))?;
    let fd = unsafe { libc::openat(root.as_raw_fd(), name.as_ptr(), flags | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK, 0o600 as libc::mode_t) };
    if fd < 0 { return Err(std::io::Error::last_os_error()); }
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn private_file(file: &File) -> Result<(), String> {
    let meta = file.metadata().map_err(io)?;
    if !meta.is_file() || meta.uid() != unsafe { libc::geteuid() } || meta.mode() & 0o7777 != 0o600 || meta.nlink() != 1 { return Err("预设文件必须为当前用户独占的 0600 普通文件".into()); }
    Ok(())
}
impl Store {
    fn open(app_data: &Path) -> Result<(Self, Catalogue), Failure> {
        let parent = walk_directory(app_data, true)?;
        let parent_meta = parent.metadata().map_err(io)?;
        if parent_meta.uid() != unsafe { libc::geteuid() } || parent_meta.mode() & 0o022 != 0 {
            return Err("应用数据目录必须由当前用户持有且不可由其他用户写入".to_string().into());
        }
        let component = std::ffi::OsStr::new("portrait-crop-rule-catalogue");
        let path = app_data.join(component);
        let fresh = mkdir_at(&parent, component)?;
        let directory = open_directory_at(&parent, component).map_err(io)?;
        let meta = directory.metadata().map_err(io)?;
        if meta.uid() != unsafe { libc::geteuid() } || meta.mode() & 0o7777 != 0o700 { return Err("预设私有目录必须为当前用户持有的 0700 目录".to_string().into()); }
        let lock = open_at(&directory, "writer.lock", libc::O_RDWR | libc::O_CREAT).map_err(io)?;
        private_file(&lock)?;
        if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 { return Err("其他窗口或进程正在访问预设目录；本次未修改，请稍后刷新".to_string().into()); }
        let store = Self { path, directory, identity: (meta.dev(), meta.ino()), _lock: lock };
        store.verify()?;
        if fresh {
            // mkdir success alone is NOT an identity proof: a same-user rename
            // could substitute a different directory before open. Initialization
            // must use exclusive canonical creation, never replacement save.
            // An existing directory missing its target is never treated as empty.
            let mut bytes = [0_u8; 16];
            File::open("/dev/urandom").and_then(|mut file| file.read_exact(&mut bytes)).map_err(io)?;
            let empty = Catalogue::empty(bytes.iter().map(|v| format!("{v:02x}")).collect())?;
            store.initialize(&empty)?;
        }
        let catalogue = store.read()?;
        // A crash before rename leaves only uncommitted scratch. Never promote
        // it, never restore an older backup and never reset a corrupt catalogue.
        store.discard_partial()?;
        store.directory.sync_all().map_err(io)?;
        store.verify()?;
        Ok((store, catalogue))
    }
    fn verify(&self) -> Result<(), String> {
        let meta = directory(&self.path)?.metadata().map_err(io)?;
        if (meta.dev(), meta.ino()) != self.identity { return Err("预设目录在操作期间已被替换；请停止操作并核对本地目录".into()); }
        Ok(())
    }
    fn read(&self) -> Result<Catalogue, String> {
        let mut file = open_at(&self.directory, TARGET, libc::O_RDONLY).map_err(|error| format!("预设目录读取失败；不会创建空目录覆盖已有数据：{error}"))?;
        private_file(&file)?;
        if file.metadata().map_err(io)?.len() > MAX_BYTES as u64 { return Err("预设目录超过 256 KiB 上限".into()); }
        let mut bytes = Vec::new(); (&mut file).take(MAX_BYTES as u64 + 1).read_to_end(&mut bytes).map_err(io)?;
        if bytes.len() > MAX_BYTES { return Err("预设目录读取时超出上限".into()); }
        let catalogue: Catalogue = serde_json::from_slice(&bytes).map_err(|_| "预设目录字段、JSON 或版本无效；不会迁移或清空")?;
        catalogue.validate()?; self.verify()?; Ok(catalogue)
    }
    fn discard_partial(&self) -> Result<(), String> {
        match open_at(&self.directory, TEMP, libc::O_RDONLY) {
            Ok(file) => {
                private_file(&file)?;
                if unsafe { libc::unlinkat(self.directory.as_raw_fd(), b"catalogue.partial\0".as_ptr().cast(), 0) } != 0 { return Err(io(std::io::Error::last_os_error())); }
                Ok(())
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(error) => Err(io(error)),
        }
    }
    fn initialize(&self, catalogue: &Catalogue) -> Result<(), Failure> {
        catalogue.validate()?; self.verify()?;
        let bytes = serde_json::to_vec(catalogue).map_err(|error| error.to_string())?;
        if bytes.len() > MAX_BYTES { return Err("初始预设目录超过容量上限".to_string().into()); }
        // This is the no-reset proof even if the newly mkdir'd directory was
        // replaced before open: an existing canonical file/symlink/directory
        // always yields EEXIST. Never truncate, rename over, or delete it.
        let mut file = open_at(&self.directory, TARGET, libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL).map_err(io)?;
        // The writer lock prevents readers seeing partial initialization. A crash
        // can leave an incomplete first target; the next open refuses it instead
        // of defaulting. Once create succeeded, failures are not no-change.
        file.write_all(&bytes).and_then(|_| file.sync_all()).and_then(|_| self.directory.sync_all())
            .map_err(io).and_then(|_| self.verify()).map_err(|message| Failure { message, uncertain: true })
    }
    fn save(&self, catalogue: &Catalogue) -> Result<(), Failure> {
        catalogue.validate()?; self.verify()?;
        let bytes = serde_json::to_vec(catalogue).map_err(|error| error.to_string())?;
        if bytes.len() > MAX_BYTES { return Err("预设目录超过 256 KiB 上限".to_string().into()); }
        let mut file = open_at(&self.directory, TEMP, libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL).map_err(io)?;
        // Every failure up to rename leaves the authoritative target untouched.
        let prepared = file.write_all(&bytes).and_then(|_| file.sync_all()).map_err(io).and_then(|_| self.verify());
        if let Err(message) = prepared { let _ = self.discard_partial(); return Err(message.into()); }
        drop(file);
        if unsafe { libc::renameat(self.directory.as_raw_fd(), b"catalogue.partial\0".as_ptr().cast(), self.directory.as_raw_fd(), b"catalogue.json\0".as_ptr().cast()) } != 0 {
            let message = io(std::io::Error::last_os_error()); let _ = self.discard_partial(); return Err(message.into());
        }
        // After rename, errors MUST NOT claim no-change. Read-only refresh checks
        // the complete old-or-new target and fsyncs its directory before writes.
        self.directory.sync_all().map_err(io).and_then(|_| self.verify())
            .map_err(|message| Failure { message, uncertain: true })
    }
}

pub(super) fn perform(app_data: &Path, request: Request) -> Value {
    let result = (|| -> Result<Value, Failure> {
        let (store, catalogue) = Store::open(app_data)?;
        if matches!(request, Request::List) { return Ok(json!({"status":"snapshot","catalogue":catalogue})); }
        let next = catalogue.change(&request)?;
        if next == catalogue { return Ok(json!({"status":"no_change","catalogue":catalogue})); }
        store.save(&next)?;
        Ok(json!({"status":"saved","catalogue":next}))
    })();
    match result {
        Ok(value) => value,
        Err(error) if error.uncertain => json!({"status":"uncertain","message":format!("目录保存结果待核对，不能声称未保存；请刷新目录并检查内容，不要重复提交：{}",error.message)}),
        Err(error) => super::rejected(error.message),
    }
}

#[cfg(test)]
#[path = "portrait_crop_rules_store_unrun.rs"]
mod tests_unrun;
