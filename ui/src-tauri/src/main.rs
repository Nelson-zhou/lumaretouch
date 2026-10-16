//! M0 宿主：起窗口、拉起引擎、从共享内存取帧交给 WebView、跨进程打点。

mod engine;
mod shm;

use std::sync::{Arc, Mutex};

use serde::Serialize;
use serde_json::{json, Value};
use tauri::State;

use shm::ShmReader;

/// 原生单调时钟纳秒：与引擎侧 CLOCK_MONOTONIC 同基，跨进程可直接相减。
pub fn now_ns() -> u64 {
    let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut ts) };
    (ts.tv_sec as u64) * 1_000_000_000 + (ts.tv_nsec as u64)
}

#[derive(Serialize, Clone)]
pub struct Sample {
    pub seq: u64,
    /// 引擎「帧可读」→ 宿主取完字节
    pub emit_to_pull_us: f64,
    /// 宿主自身取帧耗时（共享内存拷贝 + 组装响应），纯原生时钟
    pub pull_dur_us: f64,
    /// 引擎「帧可读」→ 前端确认该帧已发出 draw 命令
    pub emit_to_ack_us: f64,
    /// 宿主取帧 → 前端确认已 draw：IPC 传输 + 等下一个 rAF + 上传 + draw 提交
    pub pull_to_ack_us: f64,
    /// 引擎「帧可读」→ 该帧真正过了一个合成周期（两次 rAF 之后）；未收到为 None
    pub emit_to_present_us: Option<f64>,
    /// 前端自测值，仅作形状参考（WebKitGTK 把它钳到 1 ms 粒度）
    pub js_draw_us: f64,
    pub t_ack_ns: u64,
}

/// 在途帧：ack 与 present 分两次到达，收齐才落成 Sample。
struct Pending {
    seq: u64,
    t_emit: u64,
    t_pull: u64,
    pull_dur: f64,
    js_draw_us: f64,
    t_ack: Option<u64>,
    t_present: Option<u64>,
}

struct Frames {
    shm: Option<ShmReader>,
    shm_name: String,
    emitted: u64,
    delivered: u64,
    /// 在途帧队列：前端每帧都拉，ack 允许滞后，所以不能只留一个。
    pending: std::collections::VecDeque<Pending>,
    samples: Vec<Sample>,
    bench_total: u64,
    bench_done: bool,
}

/// 对照组开关：把「地板成本」与「真实上传绘制成本」拆开。
/// tier0 连像素都不跨进程传，用来量 IPC/rAF 自身有多贵。
struct Tiers {
    skip_draw: bool,
    skip_pixels: bool,
    /// 只把顶部这个比例的行走跨进程+上传，其余字节不碰：脏矩形上传的上限模拟。
    /// 引擎依旧写整帧（M1 实况如此），所以这个量只证「上传+传输能省多少」，
    /// 不证端到端受益——全局调色类操作永远不会是脏矩形。
    dirty_frac: f64,
}

fn tiers() -> &'static Tiers {
    use std::sync::OnceLock;
    static T: OnceLock<Tiers> = OnceLock::new();
    T.get_or_init(|| Tiers {
        skip_draw: std::env::var("LRT_SKIP_DRAW").map(|v| v == "1").unwrap_or(false),
        skip_pixels: std::env::var("LRT_SKIP_PIXELS").map(|v| v == "1").unwrap_or(false),
        dirty_frac: std::env::var("LRT_DIRTY_FRAC")
            .ok()
            .and_then(|v| v.parse::<f64>().ok())
            .filter(|v| (0.01..=1.0).contains(v))
            .unwrap_or(1.0),
    })
}

pub struct AppState {
    frames: Mutex<Frames>,
    logs: Mutex<Vec<String>>,
    engine: Mutex<Option<Arc<engine::EngineHandle>>>,
    /// 引擎最近一次 image_ready 的原文（代理档尺寸、解码耗时等）。前端靠它轮询
    /// 「图已就绪」并拿到该用哪个尺寸起跑靶，不需要另开一条同步等待通路。
    image: Mutex<Option<Value>>,
}

/// 用 `Arc` 起步才能传给引擎读线程；因此额外管理一个持有 Arc 的启动器。
#[derive(Clone)]
pub struct Launcher(pub Arc<AppState>);

impl AppState {
    fn new() -> Self {
        Self {
            frames: Mutex::new(Frames {
                shm: None,
                shm_name: String::new(),
                emitted: 0,
                delivered: 0,
                pending: std::collections::VecDeque::new(),
                samples: Vec::new(),
                bench_total: 0,
                bench_done: false,
            }),
            logs: Mutex::new(Vec::new()),
            engine: Mutex::new(None),
            image: Mutex::new(None),
        }
    }

    pub fn push_log(&self, line: String) {
        let mut v = self.logs.lock().unwrap();
        v.push(line);
        if v.len() > 400 {
            let cut = v.len() - 400;
            v.drain(..cut);
        }
    }

    pub fn attach_shm(&self, reader: ShmReader, name: String) {
        // 每一条 shm_ready 都代表引擎新建了一块缓冲（同尺寸会早退不发事件），而新缓冲的
        // seq 从 1 重计。所以重置必须无条件：拿 pixel_size 当“换档”信号会漏掉
        // 672×848 ↔ 848×672 这种同字节不同构图（同一个代理预算换个 EXIF 方向就是它），
        // 届时新帧被当成“见过的旧 seq”拒掉，frame_acked 还会把回执配到旧条目的 t_emit 上。
        let old = {
            let mut f = self.frames.lock().unwrap();
            let o = f.shm.as_ref().map(|s| (s.pixel_size, f.emitted, f.delivered, f.pending.len()));
            f.pending.clear();
            f.samples.clear();
            f.emitted = 0;
            f.delivered = 0;
            f.shm = Some(reader);
            f.shm_name = name;
            o
        };
        if let Some((from, emitted, delivered, pending)) = old {
            // 日志在帧锁之外交，不嵌套两把锁
            self.push_log(format!(
                "共享内存换档：旧像素区 {from} 字节，计数重置（已发 {emitted}/已送 {delivered}/在途 {pending}）"
            ));
        }
    }

    pub fn on_image_ready(&self, v: &Value) {
        *self.image.lock().unwrap() = Some(v.clone());
    }

    pub fn on_frame_event(&self) {
        self.frames.lock().unwrap().emitted += 1;
    }

    pub fn on_bench_done(&self) {
        self.frames.lock().unwrap().bench_done = true;
    }

    fn send_to_engine(&self, cmd: Value) -> Result<(), String> {
        let guard = self.engine.lock().map_err(|_| "引擎锁中毒".to_string())?;
        guard
            .as_ref()
            .ok_or_else(|| "引擎未启动".to_string())?
            .send(cmd)
    }
}

// ---------------------------------------------------------------- 命令

/// 引擎源码目录解析顺序：显式参数 → `$LRT_ENGINE_SRC` → deb 打包资源 → 仓库开发布局。
/// 装到系统上以后没有 cwd 可猜，必须能从自己的资源目录里找回来。
fn default_engine_src(app: &tauri::AppHandle) -> Result<String, String> {
    use tauri::Manager;
    if let Ok(v) = std::env::var("LRT_ENGINE_SRC") {
        if !v.is_empty() {
            return Ok(v);
        }
    }
    if let Ok(dir) = app.path().resource_dir() {
        let cand = dir.join("engine/src");
        if cand.join("lumaretouch_engine").is_dir() {
            return Ok(cand.to_string_lossy().to_string());
        }
    }
    let dev = std::env::current_dir()
        .map_err(|e| e.to_string())?
        .join("../engine/src");
    if dev.join("lumaretouch_engine").is_dir() {
        return Ok(dev.to_string_lossy().to_string());
    }
    Err("找不到引擎源码目录（已试过：$LRT_ENGINE_SRC / 打包资源目录 / ../engine/src）".into())
}

#[tauri::command]
fn start_engine(app: tauri::AppHandle, launcher: State<'_, Launcher>, py: String, src: String) -> Result<Value, String> {
    // 空串＝用环境变量或默认布局，方便 dev 一键起引擎
    let py = if py.is_empty() {
        std::env::var("LRT_ENGINE_PY").unwrap_or_else(|_| "python3".into())
    } else {
        py
    };
    let src = if src.is_empty() { default_engine_src(&app)? } else { src };
    let st = launcher.0.clone();
    {
        let guard = st.engine.lock().map_err(|_| "引擎锁中毒".to_string())?;
        if let Some(h) = guard.as_ref() {
            if h.is_alive() {
                return Err("引擎已在运行".into());
            }
        }
    }
    let session = format!("ui-{}", std::process::id());
    let h = engine::spawn(&py, &src, &session, st.clone());
    let pid = h.pid();
    // 新引擎进程 = 空的会话。不清掉上一张图的就绪标记，自动流程会拿陈图的 w/h
    // 去驱一个 _vram=None 的新引擎（量出来的是“没跑但正常”）。
    *st.image.lock().unwrap() = None;
    *st.engine.lock().map_err(|_| "引擎锁中毒".to_string())? = Some(Arc::new(h));
    Ok(json!({"pid": pid, "python": py, "src": src, "session": session}))
}

#[tauri::command]
fn bench_start(
    state: State<'_, Arc<AppState>>,
    w: u32,
    h: u32,
    frames: u32,
    interval_ms: f64,
    mode: String,
) -> Result<Value, String> {
    {
        let mut f = state.frames.lock().map_err(|_| "锁中毒".to_string())?;
        f.emitted = 0;
        f.delivered = 0;
        f.pending.clear();
        f.samples.clear();
        f.bench_total = frames as u64;
        f.bench_done = false;
    }
    let device = std::env::var("LRT_DEVICE").unwrap_or_else(|_| "cpu".into());
    state.send_to_engine(json!({"cmd": "set_device", "device": device}))?;
    state.send_to_engine(json!({
        "cmd": "bench_start", "w": w, "h": h,
        "frames": frames, "interval_ms": interval_ms, "mode": mode
    }))?;
    Ok(json!({"started": true, "device": device, "mode": mode}))
}

/// 导入真图（M1-3a）：解码、代理档、常驻显存全在引擎侧，这里只转发与后续查状态。
/// 不返回同步结果：引擎要几百毫秒到几秒，把它变成一次同步调用会把 UI 卡住。
#[tauri::command]
fn load_image(
    state: State<'_, Arc<AppState>>,
    path: String,
    max_px: Option<u64>,
    strength: Option<f64>,
) -> Result<Value, String> {
    let mut cmd = json!({"cmd": "load_image", "path": path});
    // 设备必须在建会话之前就定好。F 轮翻车就是因为它：只有 bench_start 发 set_device，
    // 导入时引擎还是默认的 cpu，常驻会话整个建在 CPU 上，跑靶再切 cuda 也追不回来。
    // 引擎侧现在也会跟着迁移旧会话，但正确顺序仍然要在这里保证——没人想看一张
    // 91 ms/帧的“GPU”数据。
    let device = std::env::var("LRT_DEVICE").unwrap_or_else(|_| "cpu".into());
    state.send_to_engine(json!({"cmd": "set_device", "device": device}))?;
    if let Some(v) = max_px {
        cmd["max_px"] = json!(v);
    }
    if let Some(v) = strength {
        cmd["strength"] = json!(v);
    }
    *state.image.lock().unwrap() = None;      // 清掉上一张的就绪标记，否则前端会读到陈数据
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 滑块动一下：只重算系数，不重解码也不重上传。
#[tauri::command]
fn set_strength(state: State<'_, Arc<AppState>>, value: f64) -> Result<Value, String> {
    state.send_to_engine(json!({"cmd": "set_strength", "value": value}))?;
    Ok(json!({"value": value}))
}

/// 取最新一帧。原生二进制响应 = 40B 头 + RGBA 像素：
/// seq u64 | t_emit_ns u64 | t_pull_ns u64 | w u32 | h u32 | pixel_len u32 | reserved u32
/// `LRT_SKIP_PIXELS=1` 时 pixel_len 置 0 并不拷像素，前端据此跳过上传，得到纯 IPC 对照组。
#[tauri::command]
fn pull_frame(state: State<'_, Arc<AppState>>) -> Result<tauri::ipc::Response, String> {
    // 判重、取元数据、拷像素、记在途全部挤在同一个帧锁里。分几次取锁的话，引擎导入真图
    // 就可能在两次取锁之间把整块 shm 换掉：“按旧 pixel_size 分配缓冲、往新缓冲里读”
    // 越界（panic 或 UB）；而判重与 push 之间的窗口会让同一个 seq 被投两次，
    // 丢帧统计同时失真。拷贝本来就是 µs 级，锁里做完不亏。
    let mut f = state.frames.lock().map_err(|_| "锁中毒".to_string())?;
    let shm = f.shm.as_ref().ok_or("SHM_NOT_READY")?;
    let (meta, slot) = shm.freshest().ok_or("NO_FRAME_YET")?;
    let (seq, t_emit, fw, fh) = (meta.seq, meta.t_ns, meta.w, meta.h);
    // 同一帧重复拉取（无新帧）时直接拒，避免重复计数
    if f.pending.iter().any(|p| p.seq == seq)
        || f.samples.last().map(|x| x.seq) == Some(seq)
    {
        return Err("NO_NEW_FRAME".into());
    }
    let t_pull = now_ns();
    let (y0, rows) = dirty_window(fw, fh);
    let want = if tiers().skip_pixels {
        0
    } else {
        (y0 as usize + rows as usize) * fw as usize * 4
    };
    let payload = want.min(shm.pixel_size);
    let mut buf = vec![0u8; 40 + payload];
    if payload > 0 {
        shm.copy_span(slot, y0 as usize * fw as usize * 4, &mut buf[40..])?;
    }
    buf[0..8].copy_from_slice(&seq.to_le_bytes());
    buf[8..16].copy_from_slice(&t_emit.to_le_bytes());
    buf[16..24].copy_from_slice(&t_pull.to_le_bytes());
    buf[24..28].copy_from_slice(&fw.to_le_bytes());
    buf[28..32].copy_from_slice(&fh.to_le_bytes());
    buf[32..36].copy_from_slice(&(payload as u32).to_le_bytes());
    // 保留位放 y0：前端用 pixel_len 就能推出行数，起始行得宿主告知
    buf[36..40].copy_from_slice(&y0.to_le_bytes());
    let pull_dur = now_ns().saturating_sub(t_pull) as f64 / 1000.0;
    f.delivered += 1;
    f.pending.push_back(Pending {
        seq,
        t_emit,
        t_pull,
        pull_dur,
        js_draw_us: 0.0,
        t_ack: None,
        t_present: None,
    });
    while f.pending.len() > 24 {
        // 前端跟不上的旧帧：丢弃并计入丢帧
        f.pending.pop_front();
    }
    reap(&mut f);
    Ok(tauri::ipc::Response::new(buf))
}

/// 脏矩形窗口：取顶部 dirty_frac 比例的行（行 0 起）。
/// 测帧的序号色块就落在顶部区域内，所以「帧在换」这个证据依然成立。
fn dirty_window(w: u32, h: u32) -> (u32, u32) {
    if tiers().dirty_frac >= 1.0 || w == 0 || h == 0 {
        return (0, h);
    }
    (0, ((h as f64) * tiers().dirty_frac).ceil().clamp(1.0, h as f64) as u32)
}

/// 把 ack/present 都已收齐的在途帧落成样本。ack 与 present 到达顺序不固定，
/// 所以两个入口都调这个。
fn reap(f: &mut Frames) {
    let mut i = 0;
    while i < f.pending.len() {
        let (ta, tp) = match &f.pending[i] {
            p if p.t_ack.is_some() && p.t_present.is_some() => (p.t_ack.unwrap(), p.t_present.unwrap()),
            _ => { i += 1; continue; }
        };
        let p = f.pending.remove(i).unwrap();
        f.samples.push(Sample {
            seq: p.seq,
            emit_to_pull_us: p.t_pull.saturating_sub(p.t_emit) as f64 / 1000.0,
            pull_dur_us: p.pull_dur,
            emit_to_ack_us: ta.saturating_sub(p.t_emit) as f64 / 1000.0,
            pull_to_ack_us: ta.saturating_sub(p.t_pull) as f64 / 1000.0,
            emit_to_present_us: Some(tp.saturating_sub(p.t_emit) as f64 / 1000.0),
            js_draw_us: p.js_draw_us,
            t_ack_ns: ta,
        });
    }
}

#[tauri::command]
fn frame_acked(state: State<'_, Arc<AppState>>, seq: u64, js_draw_us: f64) -> Result<(), String> {
    let t_ack = now_ns();
    let mut f = state.frames.lock().map_err(|_| "锁中毒".to_string())?;
    let p = f
        .pending
        .iter_mut()
        .find(|p| p.seq == seq)
        .ok_or_else(|| format!("ack 的 seq={seq} 不在在途队列里"))?;
    p.t_ack = Some(t_ack);
    p.js_draw_us = js_draw_us;
    reap(&mut f);
    Ok(())
}

/// 前端在该帧之后又跑了两个 rAF：此时它已被合成器拿去画过一轮。
#[tauri::command]
fn frame_presented(state: State<'_, Arc<AppState>>, seq: u64) -> Result<(), String> {
    let t = now_ns();
    let mut f = state.frames.lock().map_err(|_| "锁中毒".to_string())?;
    let p = f
        .pending
        .iter_mut()
        .find(|p| p.seq == seq)
        .ok_or_else(|| format!("present 的 seq={seq} 不在在途队列里"))?;
    p.t_present = Some(t);
    reap(&mut f);
    Ok(())
}

#[derive(Serialize)]
pub struct Dist {
    pub mean: f64,
    pub p50: f64,
    pub p95: f64,
    pub p99: f64,
    pub max: f64,
}

fn dist(mut v: Vec<f64>) -> Dist {
    if v.is_empty() {
        return Dist { mean: 0.0, p50: 0.0, p95: 0.0, p99: 0.0, max: 0.0 };
    }
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let n = v.len();
    let pick = |q: f64| v[((n as f64 - 1.0) * q).round() as usize];
    Dist { mean: v.iter().sum::<f64>() / n as f64, p50: pick(0.50), p95: pick(0.95), p99: pick(0.99), max: v[n - 1] }
}

#[derive(Serialize)]
pub struct Stats {
    pub n: usize,
    pub emitted: u64,
    pub delivered: u64,
    pub dropped: u64,
    pub drop_pct: f64,
    pub bench_done: bool,
    pub measured_fps: f64,
    pub skip_draw: bool,
    pub skip_pixels: bool,
    pub emit_to_pull: Dist,
    pub pull_dur: Dist,
    pub emit_to_ack: Dist,
    pub pull_to_ack: Dist,
    pub emit_to_present: Dist,
    pub present_cover: usize,
    pub js_draw: Dist,
}

#[tauri::command]
fn bench_stats(state: State<'_, Arc<AppState>>) -> Result<Stats, String> {
    let f = state.frames.lock().map_err(|_| "锁中毒".to_string())?;
    let s = &f.samples;
    // 有效帧率：用首末帧「上屏确认」的原生时间戳之差推算，不依赖前端时钟
    let fps = if s.len() >= 2 {
        let span_us = (s.last().unwrap().t_ack_ns.saturating_sub(s[0].t_ack_ns)) as f64 / 1000.0;
        if span_us > 0.0 { (s.len() - 1) as f64 * 1_000_000.0 / span_us } else { 0.0 }
    } else {
        0.0
    };
    let dropped = f.emitted.saturating_sub(f.delivered);
    let present: Vec<f64> = s.iter().filter_map(|x| x.emit_to_present_us).collect();
    let present_cover = present.len();
    Ok(Stats {
        n: s.len(),
        emitted: f.emitted,
        delivered: f.delivered,
        dropped,
        drop_pct: if f.emitted > 0 { dropped as f64 * 100.0 / f.emitted as f64 } else { 0.0 },
        bench_done: f.bench_done,
        measured_fps: fps,
        skip_draw: tiers().skip_draw,
        skip_pixels: tiers().skip_pixels,
        emit_to_pull: dist(s.iter().map(|x| x.emit_to_pull_us).collect()),
        pull_dur: dist(s.iter().map(|x| x.pull_dur_us).collect()),
        emit_to_ack: dist(s.iter().map(|x| x.emit_to_ack_us).collect()),
        pull_to_ack: dist(s.iter().map(|x| x.pull_to_ack_us).collect()),
        emit_to_present: dist(present),
        present_cover,
        js_draw: dist(s.iter().map(|x| x.js_draw_us).collect()),
    })
}

#[tauri::command]
fn engine_status(state: State<'_, Arc<AppState>>) -> Value {
    let (shm_name, emitted, delivered, has_shm) = {
        let f = state.frames.lock().unwrap();
        (f.shm_name.clone(), f.emitted, f.delivered, f.shm.is_some())
    };
    let logs: Vec<String> = state.logs.lock().unwrap().iter().rev().take(25).cloned().collect();
    let image = state.image.lock().unwrap().clone();
    json!({"shm": shm_name, "has_shm": has_shm, "emitted": emitted,
           "delivered": delivered, "logs": logs, "image": image})
}

#[tauri::command]
fn shutdown_engine(state: State<'_, Arc<AppState>>) -> Value {
    let h = state.engine.lock().unwrap().clone();
    // 引擎停了，它报过的 image_ready 也随之作废；留着会让下一次自动流程拿陈尺寸起跑
    *state.image.lock().unwrap() = None;
    match h {
        Some(h) => {
            h.shutdown();
            json!({"shutdown": true})
        }
        None => json!({"shutdown": false, "reason": "引擎未启动"}),
    }
}

/// M0 自动跑靶配置：环境变量传进来，让整条通路可以被脚本驱起来跑。
#[tauri::command]
fn m0_env() -> Value {
    json!({
        "auto_bench": std::env::var("LRT_AUTO_BENCH").unwrap_or_default(),
        "engine_py": std::env::var("LRT_ENGINE_PY").unwrap_or_default(),
        "engine_src": std::env::var("LRT_ENGINE_SRC").unwrap_or_default(),
        "device": std::env::var("LRT_DEVICE").unwrap_or_else(|_| "cpu".into()),
        "skip_draw": std::env::var("LRT_SKIP_DRAW").unwrap_or_default(),
        "skip_pixels": std::env::var("LRT_SKIP_PIXELS").unwrap_or_default(),
        "upload": std::env::var("LRT_UPLOAD").unwrap_or_else(|_| "raw".into()),
        "chunks": std::env::var("LRT_CHUNKS").ok()
            .and_then(|v| v.parse::<u32>().ok())
            .filter(|v| (1..=64).contains(v))
            .unwrap_or(1),
        "no_ctx": std::env::var("LRT_NO_CTX").unwrap_or_default(),
        "dirty_frac": tiers().dirty_frac,
        "load_image": std::env::var("LRT_LOAD_IMAGE").unwrap_or_default(),
        "max_px": std::env::var("LRT_MAX_PX").ok().and_then(|v| v.parse::<u64>().ok()),
    })
}

/// 把结果回显到 `tauri dev` 的标准输出，便于跑靶脚本直接采集。
#[tauri::command]
fn report(line: String) {
    println!("{line}");
}

#[tauri::command]
fn quit() {
    std::process::exit(0);
}

fn main() {
    let state = Arc::new(AppState::new());
    tauri::Builder::default()
        .manage(state.clone())
        .manage(Launcher(state.clone()))
        .invoke_handler(tauri::generate_handler![
            start_engine, bench_start, pull_frame, frame_acked, frame_presented, bench_stats,
            engine_status, shutdown_engine, m0_env, load_image, set_strength, report, quit
        ])
        .run(tauri::generate_context!())
        .expect("运行 LumaRetouch 失败");
}
