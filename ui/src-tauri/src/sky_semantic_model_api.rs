//! Explicit optional-model acquisition outside the seccomp image engine.
//! Local migration is a separate helper action and never implies download consent.
use std::{io::{BufRead, BufReader, Read}, process::{Child, Command, Stdio}, sync::{Arc, Mutex}, thread, time::{Duration, Instant}};
use serde_json::{json, Value};
use tauri::State;
use crate::AppState;

pub(crate) struct ModelHost {
    child: Option<Child>, serial: u64, action: String, result: Value,
    error: Option<String>, cancelled: Option<Instant>,
}
impl Default for ModelHost {
    fn default() -> Self { Self { child: None, serial: 0, action: "idle".into(),
        result: json!({"state":"unknown","model_id":"shi-labs/oneformer_ade20k_swin_tiny","weight_bytes":203389501,
            "license":"MIT","source":"https://huggingface.co/shi-labs/oneformer_ade20k_swin_tiny/blob/05f2812b1eccf9909b3897777450f8d68148cafc/README.md",
            "runtime_download_separate":true}), error: None, cancelled: None } }
}
impl ModelHost {
    fn status(&self) -> Value { json!({"running":self.child.is_some(),"action":self.action,"result":self.result,"error":self.error}) }
    fn cancel(&mut self) {
        if self.cancelled.is_none() { if let Some(child) = &mut self.child {
            // Give the Python owner time to remove staging without publishing an incomplete installation.
            #[cfg(unix)] unsafe { libc::kill(child.id() as libc::pid_t, libc::SIGTERM); }
            #[cfg(not(unix))] { let _ = child.kill(); }
            self.cancelled = Some(Instant::now());
        } }
    }
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
pub(crate) fn sky_semantic_model(state: State<'_, Arc<AppState>>, action: String) -> Result<Value, String> {
    if !matches!(action.as_str(), "status"|"install"|"migrate"|"cancel") { return Err("invalid optional model action".into()); }
    let shared = state.sky_semantic_model.clone();
    let mut host = shared.lock().map_err(|_| "optional model lock poisoned")?;
    if action == "cancel" { host.cancel(); return Ok(host.status()); }
    if host.child.is_some() { return if action == "status" { Ok(host.status()) } else { Err("optional model operation already running".into()) }; }
    let engine = state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().filter(|h| h.is_alive()).ok_or("start the selected engine runtime first")?;
    let runtime = state.engine_runtime.lock().map_err(|_| "runtime lock poisoned")?.clone();
    let py = runtime["python"].as_str().filter(|p| !p.is_empty()).ok_or("selected Python is unavailable")?;
    let src = runtime["engine_src"].as_str().filter(|p| !p.is_empty()).ok_or("selected engine source is unavailable")?;
    if !std::path::Path::new(src).join("lumaretouch_engine/sky_semantic/install.py").is_file() {
        return Err("selected engine has no optional-model installer".into());
    }
    let mut command = Command::new(py);
    let operation = match action.as_str() {
        "install" => "--install",
        "migrate" => "--migrate",
        _ => "--status",
    };
    command.args(["-m", "lumaretouch_engine.sky_semantic.install", operation])
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
            if started.elapsed() > Duration::from_secs(7200) { h.error = Some("Optional model operation timed out".into()); h.cancel(); }
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
                Ok(true) if matches!(h.result["state"].as_str(), Some("ready"|"unavailable")) => {},
                _ => { if !matches!(h.result["state"].as_str(), Some("failed"|"cancelled")) {
                    h.result = json!({"state":if h.cancelled.is_some(){"cancelled"}else{"error"},"error":h.error.clone().unwrap_or_else(|| "Optional model helper failed".into())});
                } }
            }
        } }
    });
    Ok(status)
}
#[tauri::command]
pub(crate) fn sky_semantic_model_status(state: State<'_, Arc<AppState>>) -> Result<Value, String> {
    Ok(state.sky_semantic_model.lock().map_err(|_| "optional model lock poisoned")?.status())
}
pub(crate) fn shutdown(state: &AppState) {
    if let Ok(mut host) = state.sky_semantic_model.lock() { host.cancel(); }
    // Do not orphan installer on normal app exit. The owner performs cleanup.
    loop {
        let running = state.sky_semantic_model.lock().map(|h| h.child.is_some()).unwrap_or(false);
        if !running { break; } thread::sleep(Duration::from_millis(100));
    }
}
