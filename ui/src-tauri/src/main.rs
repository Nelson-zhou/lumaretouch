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
    /// 最近一次 precompute_ready（478 点 / 掩膜通道 / 常驻设备）。
    /// 与 image 分开存：换图不重跑预计算时，陈的掩膜状态绝不能当成还在。
    precompute: Mutex<Option<Value>>,
    /// 最近一次 inpaint_done（消除笔的事件驱动结果）。与图层同生命期：
    /// 换图/换引擎进程必须清空，否则前端会拿上一张图的修补指标当本图的。
    inpaint: Mutex<Option<Value>>,
    /// 最近一次 light_done（M2-a2 修容笔）。与 inpaint 分开存：两个图层各自
    /// 一次事件一条结果，合成一份就会让“消除笔的 repair_ms”被读成修容的耗时。
    light: Mutex<Option<Value>>,
    /// 最近一次 deform_done（M2-b 五官微调）。与修容分开存的理由与上面同一条：
    /// 它报的是形变段与常驻字节，与 db 的账不是一个量。
    deform: Mutex<Option<Value>>,
    /// 最近一次 lut_done（M3-a2 影楼色彩）。与形变分开存：调色是逐点输出变换，
    /// 它不依赖关键点也不依赖笔迹，生命期也只随文档走（换图即清）。
    lut: Mutex<Option<Value>>,
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
            precompute: Mutex::new(None),
            inpaint: Mutex::new(None),
            light: Mutex::new(None),
            deform: Mutex::new(None),
            lut: Mutex::new(None),
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

    pub fn on_precompute_ready(&self, v: &Value) {
        *self.precompute.lock().unwrap() = Some(v.clone());
    }

    pub fn on_inpaint_ready(&self, v: &Value) {
        *self.inpaint.lock().unwrap() = Some(v.clone());
    }

    pub fn on_light_ready(&self, v: &Value) {
        *self.light.lock().unwrap() = Some(v.clone());
    }

    pub fn on_deform_ready(&self, v: &Value) {
        *self.deform.lock().unwrap() = Some(v.clone());
    }

    pub fn on_lut_ready(&self, v: &Value) {
        *self.lut.lock().unwrap() = Some(v.clone());
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
    // 去驱一个 _vram=None 的新引擎（量出来就是“没跑但正常”）。
    *st.image.lock().unwrap() = None;
    *st.precompute.lock().unwrap() = None;
    *st.deform.lock().unwrap() = None;      // 形变层随关键点走，新进程里没有关键点
    *st.lut.lock().unwrap() = None;          // 调色层也随文档走，新进程里一张表也没挂
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
    precompute: Option<String>,
    channel: Option<String>,
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
    // 导入期预计算：“auto/mediapipe/synthetic” 传下去就是导完图算一次；
    // 空串/None 那么只解码不算，两条路都得能跑，否则通路验收分不开。
    match precompute.as_deref().filter(|s| !s.is_empty() && *s != "0") {
        Some(b) => {
            cmd["precompute"] = json!(true);
            cmd["backend"] = json!(b);
            if let Some(c) = channel.as_deref().filter(|s| !s.is_empty()) {
                cmd["channel"] = json!(c);
            }
        }
        None => {}
    }
    *state.image.lock().unwrap() = None;      // 清掉上一张的就绪标记，否则前端会读到陈数据
    *state.precompute.lock().unwrap() = None;
    // 画笔图层也一起清：引擎侧 load_image 会丢旧笔画，宿主留着就是报一个不存在的图层状态
    *state.inpaint.lock().unwrap() = None;
    *state.light.lock().unwrap() = None;
    *state.deform.lock().unwrap() = None;
    // 调色层也是：上一张照片的色调不能静默带到这一张上（引擎侧 load_image 已把它清了）
    *state.lut.lock().unwrap() = None;
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 滑块动一下：只重算系数，不重解码也不重上传。channel 指向某个常驻掩膜通道。
/// radius/eps/detail_gain 是磨皮参数：它们变了引擎会重算一次滤波，所以前端只在松手时带。
#[tauri::command]
fn set_strength(
    state: State<'_, Arc<AppState>>,
    value: f64,
    channel: Option<String>,
    radius: Option<u64>,
    eps: Option<f64>,
    detail_gain: Option<f64>,
    mid_gain: Option<f64>,
    broad_gain: Option<f64>,
    texture_radius: Option<u64>,
) -> Result<Value, String> {
    let mut cmd = json!({"cmd": "set_strength", "value": value});
    if let Some(c) = channel.filter(|s| !s.is_empty()) {
        cmd["channel"] = json!(c);
    }
    // 只在显式给了值时才附字段：缺字段就是“不改这个参数”，与引擎侧的
    // `p.get(k) is None → continue` 一一对应。把默认值写在这里就等于宿主替引擎
    // 做决定，生产默认值一改这条通路就会静默漂开。
    if let Some(v) = radius {
        cmd["radius"] = json!(v);
    }
    if let Some(v) = eps {
        cmd["eps"] = json!(v);
    }
    if let Some(v) = detail_gain {
        cmd["detail_gain"] = json!(v);
    }
    // M2-a 四条带：mid=瑕疵/边缘锐度，broad=大面积色斑/光影，texture_radius=细带取多宽
    if let Some(v) = mid_gain {
        cmd["mid_gain"] = json!(v);
    }
    if let Some(v) = broad_gain {
        cmd["broad_gain"] = json!(v);
    }
    if let Some(v) = texture_radius {
        cmd["texture_radius"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"value": value}))
}

/// 消除笔（M1-4）：一次事件（松手）一条命令。rle 是代理帧坐标下的行程编码。
/// 不返回同步结果：修补要几十毫秒，结果靠 engine_status().inpaint 轮询。
#[tauri::command]
fn inpaint(
    state: State<'_, Arc<AppState>>,
    action: String,
    rle: Option<Value>,
    feather: Option<u64>,
    backend: Option<String>,
    refine_iters: Option<u64>,
    smooth_iters: Option<u64>,
) -> Result<Value, String> {
    let mut cmd = json!({"cmd": "inpaint", "action": action});
    if let Some(v) = rle {
        cmd["rle"] = v;
    }
    if let Some(v) = feather {
        cmd["feather"] = json!(v);
    }
    if let Some(b) = backend.filter(|s| !s.is_empty()) {
        cmd["backend"] = json!(b);
    }
    if let Some(v) = refine_iters {
        cmd["refine_iters"] = json!(v);
    }
    if let Some(v) = smooth_iters {
        cmd["smooth_iters"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 修容笔（M2-a2）：加深/减淡一次事件一条命令，与消除笔同一套事件调度。
/// sign=+1 减淡、-1 加深；action=params 时只改这层的档数与带限半径。
/// 不返回同步结果：db 要几毫秒，结果靠 engine_status().light 轮询。
#[tauri::command]
fn light(
    state: State<'_, Arc<AppState>>,
    action: String,
    rle: Option<Value>,
    feather: Option<u64>,
    sign: Option<i64>,
    exposure: Option<f64>,
    radius: Option<u64>,
) -> Result<Value, String> {
    let mut cmd = json!({"cmd": "light", "action": action});
    // 一律“给了才附”：缺字段在引擎侧是“不改这个参数”，宿主写默认值就等于
    // 替引擎做决定，生产默认值一改这条通路就会静默漂开（与 set_strength 同一条规矩）
    if let Some(v) = rle {
        cmd["rle"] = v;
    }
    if let Some(v) = feather {
        cmd["feather"] = json!(v);
    }
    if let Some(v) = sign {
        cmd["sign"] = json!(v);
    }
    if let Some(v) = exposure {
        cmd["exposure"] = json!(v);
    }
    if let Some(v) = radius {
        cmd["radius"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 五官微调（M2-b）：三个滑块的值送进引擎。action: set / clear。
///
/// 与修容笔不同，它不是逐笔事件而是参数层：滑块拖动期间每帧都要送（引擎侧只缩放
/// 已常驻的单位场，一次 TPS 也不解）。所以这里不能像 light 那样只在松手时发。
#[tauri::command]
fn deform(
    state: State<'_, Arc<AppState>>,
    action: String,
    amounts: Option<Value>,
) -> Result<Value, String> {
    let mut cmd = json!({"cmd": "deform", "action": action});
    // 与 light 同一条规矩：给了才附。宿主写默认值等于替引擎做决定，
    // 生产默认值一改这条通路就会静默漂开。
    if let Some(v) = amounts {
        cmd["amounts"] = v;
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 影楼色彩（M3-a2）：把一张 .cube 或混合系数送进引擎。action: set / amount / clear。
///
/// 与 deform 同为“参数层”（不是逐笔图层），但发送时机相反：强度只在松手时发。
/// 引擎侧只把表乘一个新系数重画一帧（不重传体积），逐事件发只会吞掉 vsync 余量。
#[tauri::command]
fn lut(
    state: State<'_, Arc<AppState>>,
    action: String,
    path: Option<String>,
    text: Option<String>,
    preset: Option<String>,
    amount: Option<f64>,
) -> Result<Value, String> {
    let mut cmd = json!({"cmd": "lut", "action": action});
    // 一律“给了才附”（与 light/deform 同规）：宿主写默认值就是替引擎做决定，
    // 生产默认值一改这条通路就会静默漂开。
    if let Some(v) = path {
        cmd["path"] = json!(v);
    }
    if let Some(v) = text {
        cmd["text"] = json!(v);
    }
    if let Some(v) = preset {
        cmd["preset"] = json!(v);
    }
    if let Some(v) = amount {
        cmd["amount"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 对当前已导入的图跑一次导入期预计算（478 点 + 语义掩膜，算完常驻显存）。
#[tauri::command]
fn precompute(
    state: State<'_, Arc<AppState>>,
    backend: Option<String>,
    channel: Option<String>,
    model_dir: Option<String>,
) -> Result<Value, String> {
    let mut cmd = json!({"cmd": "precompute", "backend": backend.unwrap_or_else(|| "auto".into())});
    if let Some(c) = channel.filter(|s| !s.is_empty()) {
        cmd["channel"] = json!(c);
    }
    if let Some(d) = model_dir.filter(|s| !s.is_empty()) {
        cmd["model_dir"] = json!(d);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
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
    let precompute = state.precompute.lock().unwrap().clone();
    let inpaint = state.inpaint.lock().unwrap().clone();
    let light = state.light.lock().unwrap().clone();
    let deform = state.deform.lock().unwrap().clone();
    let lut = state.lut.lock().unwrap().clone();
    json!({"shm": shm_name, "has_shm": has_shm, "emitted": emitted,
           "delivered": delivered, "logs": logs, "image": image, "precompute": precompute,
           "inpaint": inpaint, "light": light, "deform": deform, "lut": lut})
}

#[tauri::command]
fn shutdown_engine(state: State<'_, Arc<AppState>>) -> Value {
    let h = state.engine.lock().unwrap().clone();
    // 引擎停了，它报过的 image_ready / precompute_ready 也随之作废；留着会让下一次
    // 自动流程拿陈尺寸与陈掩膜状态起跑
    *state.image.lock().unwrap() = None;
    *state.precompute.lock().unwrap() = None;
    *state.inpaint.lock().unwrap() = None;
    *state.light.lock().unwrap() = None;
    *state.deform.lock().unwrap() = None;
    *state.lut.lock().unwrap() = None;
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
        "precompute": std::env::var("LRT_PRECOMPUTE").unwrap_or_default(),
        "precompute_channel": std::env::var("LRT_PRECOMPUTE_CHANNEL").unwrap_or_default(),
        // 消除笔自动通道："fx:fy:r,…"（坐标按代理帧归一化），跑的是与真人点击同一条链
        "auto_inpaint": std::env::var("LRT_AUTO_INPAINT").unwrap_or_default(),
        // M2-a 三条带增益的自动通道：“mid:broad:detail”。xdotool 的合成点击进不了 WebKit，
        // 所以“滑块能不能过 Rust”这件事只能靠 env 钩子在真窗口里验：命令签名改了而 TS 侧
        // 名字对不上时，Tauri 会静默丢掉那个参数，屏上不动而一个错也不报。
        "auto_skin": std::env::var("LRT_AUTO_SKIN").unwrap_or_default(),
        // M2-a2 修容自动通道：“fx:fy:r:sign,…”（坐标按代理帧归一化，sign 取 +1/-1），
        // 跟自动消除笔同一条链：只有真窗口能证明“TS → Rust → 引擎”这条命令签名对得上。
        "auto_light": std::env::var("LRT_AUTO_LIGHT").unwrap_or_default(),
        "auto_deform": std::env::var("LRT_AUTO_DEFORM").unwrap_or_default(),
        // M3-a2 调色自动通道："amount@<路径>"。与上面几条同一条理由：只有真窗口
        // 能证明 runLut → Rust lut → 引擎 lut_done 这条命令签名对得上。
        "auto_lut": std::env::var("LRT_AUTO_LUT").unwrap_or_default(),
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
            engine_status, shutdown_engine, m0_env, load_image, set_strength, precompute,
            inpaint, light, deform, lut, report, quit
        ])
        .run(tauri::generate_context!())
        .expect("运行 LumaRetouch 失败");
}
