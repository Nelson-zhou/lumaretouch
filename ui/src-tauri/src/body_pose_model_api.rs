// SPDX-License-Identifier: GPL-3.0-or-later
//! Explicit body-pose byte acquisition outside the image engine; never installs runtimes.
use std::{io::{BufRead, BufReader, Read}, process::{Child, Command, Stdio}, sync::{Arc, Mutex, OnceLock}, thread, time::{Duration, Instant}};
use serde_json::{json, Value};
use tauri::State;
use crate::AppState;

pub(crate) struct ModelHost {
    child: Option<Child>, serial: u64, action: String, result: Value,
    error: Option<String>, cancelled: Option<Instant>, request_id: String, seen: std::collections::HashSet<String>,
}
impl Default for ModelHost {
    fn default() -> Self { Self { child: None, serial: 0, action: "idle".into(),
        result: json!({"state":"unknown","installed":false,"download_bytes":null,"pin_status":"unknown"}), error: None, cancelled: None, request_id: String::new(), seen: Default::default() } }

}
impl ModelHost {
    fn status(&self) -> Value { json!({"request_id":self.request_id,"running":self.child.is_some(),"action":self.action,"result":self.result,"error":self.error}) }
    fn cancel(&mut self) {
        if self.cancelled.is_none() { if let Some(child) = &mut self.child {
            // Give the Python owner time to remove staging without publishing an incomplete installation.
            #[cfg(unix)] unsafe { libc::kill(child.id() as libc::pid_t, libc::SIGTERM); }
            #[cfg(not(unix))] { let _ = child.kill(); }
            self.cancelled = Some(Instant::now());
        } }
    }
}
fn shared_host() -> Arc<Mutex<ModelHost>> {
    static HOST: OnceLock<Arc<Mutex<ModelHost>>> = OnceLock::new();
    HOST.get_or_init(|| Arc::new(Mutex::new(ModelHost::default()))).clone()
}
fn receive(host: &Arc<Mutex<ModelHost>>, serial: u64, value: Value) {
    if let Ok(mut host) = host.lock() { if host.serial == serial && host.child.is_some() { host.result = value; } }
}
fn read_output<R: Read + Send + 'static>(pipe: R, host: Arc<Mutex<ModelHost>>, serial: u64, json_output: bool) -> thread::JoinHandle<()> {
    thread::spawn(move || {
        let mut reader = BufReader::new(pipe);
        let mut total = 0usize;
        loop {
            let mut bytes = Vec::new();
            let read = reader.by_ref().take(65537).read_until(b'\n', &mut bytes);
            let Ok(n) = read else { break }; if n == 0 { break; }
            total += n;
            if n > 65536 || total > 1024*1024 {
                if let Ok(mut h) = host.lock() { if h.serial == serial { h.error = Some("Optional installer output limit exceeded".into()); h.cancel(); } }
                break;
            }
            if json_output {
                match serde_json::from_slice::<Value>(&bytes) {
                    Ok(value) if value.is_object() => receive(&host, serial, value),
                    _ => { if let Ok(mut h) = host.lock() { if h.serial == serial { h.error = Some("Invalid optional installer progress".into()); h.cancel(); } } break; }
                }
            } else if let Ok(mut h) = host.lock() {
                if h.serial == serial { h.error = Some(String::from_utf8_lossy(&bytes).chars().take(2000).collect()); }
            }
        }
    })
}

#[tauri::command]
pub(crate) fn body_pose_model(state: State<'_, Arc<AppState>>, action: String, request_id: String) -> Result<Value, String> {
    if !matches!(action.as_str(), "install"|"cancel") { return Err("invalid optional model action".into()); }
    let shared = shared_host();
    let mut host = shared.lock().map_err(|_| "optional model lock poisoned")?;
    if request_id.is_empty() || request_id.len() > 128 { return Err("body model request identity invalid".into()); }
    if action == "cancel" { if host.request_id != request_id { return Err("body model request has changed".into()); } host.cancel(); return Ok(host.status()); }
    if host.seen.contains(&request_id) { return if host.request_id == request_id { Ok(host.status()) } else { Err("body model request already consumed; not repeated".into()) }; }
    if host.seen.len() >= 65_536 { return Err("body model request budget exhausted".into()); }
    if host.child.is_some() { return Err("optional model operation already running".into()); }
    // Preserve a terminal not-started record if runtime checks or spawn fail.
    host.seen.insert(request_id.clone()); host.request_id = request_id.clone();
    host.action = action.clone(); host.result = json!({"state":"failed","installed":false,"reason":"可选模型获取未启动，请核对所选引擎运行环境。"}); host.error = None;

    let engine = state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().filter(|h| h.is_alive()).ok_or("start the selected engine runtime first")?;
    let runtime = state.engine_runtime.lock().map_err(|_| "runtime lock poisoned")?.clone();
    let py = runtime["python"].as_str().filter(|p| !p.is_empty()).ok_or("selected Python is unavailable")?;
    let src = runtime["engine_src"].as_str().filter(|p| !p.is_empty()).ok_or("selected engine source is unavailable")?;
    if !std::path::Path::new(src).join("lumaretouch_engine/body_pose_acquisition.py").is_file() {
        return Err("selected engine has no optional-model installer".into());
    }
    let mut command = Command::new(py);
    command.args(["-m", "lumaretouch_engine.body_pose_acquisition", "--install"])
        .env("PYTHONPATH", src).env("PYTHONUNBUFFERED", "1").env("PYTHONDONTWRITEBYTECODE", "1")
        .stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped());
    #[cfg(target_os = "linux")]
    {
        use std::os::unix::process::CommandExt;
        let parent = std::process::id() as libc::pid_t;
        unsafe { command.pre_exec(move || {
            if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM) != 0 { return Err(std::io::Error::last_os_error()); }
            if libc::getppid() != parent { return Err(std::io::Error::new(std::io::ErrorKind::Interrupted, "parent exited")); }
            Ok(())
        }); }
    }
    // Keep selected runtime proof alive through spawn; never choose a system fallback here.
    if !engine.is_alive() { return Err("selected runtime stopped".into()); }
    let mut child = command.spawn().map_err(|e| format!("optional model helper could not start: {e}"))?;
    let stdout = child.stdout.take().ok_or("installer stdout unavailable")?;
    let stderr = child.stderr.take().ok_or("installer stderr unavailable")?;
    host.serial = host.serial.wrapping_add(1); let serial = host.serial;
    host.child = Some(child); host.action = action; host.error = None; host.cancelled = None;
    host.result = json!({"state":"running","phase":"starting"});
    let status = host.status(); drop(host);
    let output = read_output(stdout, shared.clone(), serial, true);
    let errors = read_output(stderr, shared.clone(), serial, false);
    thread::spawn(move || {
        let started = Instant::now();
        let outcome = loop {
            thread::sleep(Duration::from_millis(100));
            let Ok(mut h) = shared.lock() else { return };
            if h.serial != serial { return; }
            if started.elapsed() > Duration::from_secs(660) { h.error = Some("Optional model operation timed out".into()); h.cancel(); }
            let force = h.cancelled.is_some_and(|t| t.elapsed() > Duration::from_secs(45));
            let Some(child) = h.child.as_mut() else { return };
            if force { let _ = child.kill(); }
            match child.try_wait() { Ok(Some(exit)) => break Ok(exit.success()), Ok(None) => {}, Err(e) => break Err(e.to_string()) }
        };
        // Preserve the final JSON before marking the helper idle.
        let _ = output.join(); let _ = errors.join();
        if let Ok(mut h) = shared.lock() { if h.serial == serial {
            if let Some(mut child) = h.child.take() { let _ = child.wait(); }
            match outcome {
                Ok(true) if matches!(h.result["state"].as_str(), Some("verified-bytes-runtime-unvalidated"|"not-installed"|"invalid"|"pin-pending")) => {},
                _ => { if !matches!(h.result["state"].as_str(), Some("failed"|"cancelled")) {
                    h.result = json!({"state":if h.cancelled.is_some(){"cancelled"}else{"error"},"error":h.error.clone().unwrap_or_else(|| "Optional model helper failed".into())});
                } }
            }
        } }
    });
    Ok(status)
}
#[tauri::command]
pub(crate) fn body_pose_model_status() -> Result<Value, String> {
    let shared = shared_host();
    let host = shared.lock().map_err(|_| "optional model lock poisoned")?;
    Ok(host.status())
}
pub(crate) fn shutdown() {
    let shared = shared_host();
    if let Ok(mut host) = shared.lock() { host.cancel(); }
    // Do not orphan installer on normal app exit. The owner performs cleanup.
    loop {
        let running = shared.lock().map(|h| h.child.is_some()).unwrap_or(false);
        if !running { break; } thread::sleep(Duration::from_millis(100));
    }
}
