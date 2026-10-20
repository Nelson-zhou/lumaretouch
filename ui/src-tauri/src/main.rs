//! M0 宿主：起窗口、拉起引擎、从共享内存取帧交给 WebView、跨进程打点。

// 状态载荷是一个大 `json!`（一次轮询把二十几格全装进去），每多两键就深一层宏递归：
// PICK-001 加到那一步撞上默认 128 的上限。serde_json 的官方建议就是抬这个上限，而不是
// 把载荷拆成两次 merge——拆了以后"轮询里到底有什么"就变成两处代码，比递归难对账得多。
#![recursion_limit = "256"]

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
    /// 最近一次引擎关于「这张图里有几张脸、正在改哪一张」的说法（PORTRAIT-003）。
    /// 一个槽位、多个来源：precompute_ready / face_selected / face_list，加上任何带
    /// doc_state 的事件（image_ready、history_state）。分成几份存就会出现「面板读着旧的
    /// 而引擎说的是新的」；而这几路说的是同一件事，所以必须汇成一份。
    face: Mutex<Option<Value>>,
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
    /// 最近一次 grade_done（M3-b 肤色定向）。与 lut 分开存：预设一条命令同时动两层，
    /// 但两层的数字、耗时与账单各自一份，合成一份就分不清“表淡了还是肤色淡了”。
    grade: Mutex<Option<Value>>,
    /// 最近一次 enhance_done（PORTRAIT-009 眼牙局部增强）。与 grade 分开存：这一层
    /// 报的是几何掩膜与内容门的账（每子功能盖了多少格、没接通是为什么），生命期同
    /// 形变层——关键点一走它就没有来源，换图/换进程必须清空。
    enhance: Mutex<Option<Value>>,
    /// 最近一次 bg_done（M6 换底）。与 grade 分开存：换底是一次事件驱动的遮罩合成，
    /// 报的是合成耗时与遮罩常驻字节；生命期同图层（换图即清）。
    background: Mutex<Option<Value>>,
    /// 引擎在 ready 里报出的内置预设清单（M3-b）。存名字与标题两份：前端按它渲染按钮，
    /// 不自己抄一份——资产改了名而 UI 还拿旧名提交，得到的是“按钮全灭”而不是报错。
    presets: Mutex<Vec<Value>>,
    /// 肤色定向三个增量的硬边界（也在 ready 里）：滑块行程由引擎说。
    grade_limits: Mutex<Vec<f64>>,
    /// 最近一次 export_done（M4 批量出片）。它不是图层：一次导出是一批文件的结果，
    /// 但与图层同一条生命期——引擎进程换了、图换了，上一批的账单就不能当本图的读。
    export: Mutex<Option<Value>>,
    /// 最近一条 export_progress（第几张 / 共几张）。与 export 分开存：一批二十张时
    /// 只存终态就看不出“卡在第三张”与“根本没开始”的区别。
    export_progress: Mutex<Option<Value>>,
    /// 引擎报出的导出能力（export_formats / export_tile 范围）：目的地选项与 tile
    /// 行程由引擎说，宿主抄一份必漂（与 presets / grade_limits 同一条理由）。
    export_caps: Mutex<Value>,
    /// 引擎在 ready 里自报的 RAW 解码能力（raw_backends：基线能读什么、哪些需插件、
    /// 插件装没装）。「支持 RAW」这种话由引擎说，宿主不刻一份——把没落地的 CR2
    /// 支持写进 UI 就是一条假指标（与 export_caps / presets 同一条理由）。
    raw_backends: Mutex<Value>,
    /// 抠图后端清单（M6，ops/birefnet.matting_backends）：哪个档装机即用、哪个还在等
    /// 权重。与 raw_backends / export_caps 同一条理由：能力由引擎报，宿主不刻一份。
    matting_backends: Mutex<Value>,
    /// 能收哪些后缀（引擎 session.IMAGE_EXTS 报的那一份）：原生选择框的过滤器用它，
    /// 宿主不刻一份——名单漂了，用户就在选择框里选不到，而工程师那边说"支持"。
    image_exts: Mutex<Value>,
    /// 导出位深能力（ready.export_bits，M9-e）：哪些位深对应哪些落盘格式由引擎说。
    /// 前端自己刻一份"16-bit 只能写 TIFF"，就是引擎改口径时漏改的那一处。
    export_bits: Mutex<Value>,
    /// 引擎最近一条 error（M9）：load_image 是"发出去就返回"的，失败只走 error 事件。
    /// 不接住它，宿主就永远看不见"为什么打不开"——用户那边就是点了没反应。
    last_error: Mutex<Option<String>>,
    /// 最近一条 session_state（M5 底片条）：格子列表、当前索引、有没有缩略图。
    /// 这一份里**不带 base64**——控制通道那条“像素不进 JSON”的规矩只在缩略图上开了
    /// 一个一次性的例外，宿主不该把它长期握在轮询载荷里。
    session: Mutex<Option<Value>>,
    /// path → 缩略图 base64。归属看 path 不看 index：中途重扫一次列表，index 会换，
    /// 而“哪张图配哪一格”不会换。
    thumbs: Mutex<std::collections::HashMap<String, String>>,
    /// session_state 每来一条 +1：前端拿它决定“要不要整条重取一次底片条”，
    /// 而不是每秒把两百张缩略图克隆一遍。
    session_rev: Mutex<usize>,
    /// 挑图建议（LNX-PICK-001）：最近一条 pick_start / pick_progress / pick_done /
    /// pick_state。UI 那句「已量 37/200、这次按哪三档判的」只能从这里来——前端自己数
    /// 徽章就是第二个出处。
    pick: Mutex<Option<Value>>,
    /// 已收到多少条 pick_item（按格计，pick_start 归零）。徽章是逐格亮的，进度只认这个数。
    pick_items: Mutex<usize>,
    /// 最近一条 history_state（M5-b）。这一份里的 doc_state 是撤销之后**引擎认定的
    /// 文档状态**：宿主必须按它重摆滑块，因为同一张文档内部撤销时 docKey 不变，
    /// 走不到 image_ready 那条重摆路——不接就是“画面退回去了而滑块还停在 0.9”。
    history: Mutex<Option<Value>>,
    history_rev: Mutex<usize>,
    /// ready 报的"哪些命令算编辑"（M5-b）。名单属于引擎，宿主只照抄：新加一层而
    /// 忘了进名单时，撤销按钮会点着不亮——那正是"第七层没人记得"的老下场。
    history_edit_cmds: Mutex<Vec<String>>,
    /// 最近一条**带着 doc_state** 的事件（image_ready / session_state / history_state
    /// 三条之一），外加"是哪一条"。历史账只能从这三条里来，而谁最后到只有宿主按到达
    /// 次序数得出来：前端各取一份，就会出现"撤销完了又被一条晚到的 session_state 把
    /// 旧栈深顶回来"——按钮在骗人。
    doc_report: Mutex<Option<Value>>,
    doc_rev: Mutex<usize>,
    /// 发过一条编辑命令、还没听到引擎的历史答复。这一段窗口里撤销按钮必须可用，
    /// 否则用户拖完滑块按不动：历史账只在 history_state / image_ready / session_state
    /// 三条里出现，而拖滑块那几条都不在其中。
    history_dirty: Mutex<bool>,
    /// 最近一条项目播报（project_created / opened / saved / edited / state）。
    /// 名单只照抄引擎的 `project_actions`，宿主不自建第二份：徽章上那个“未保存”
    /// 只能来自引擎的 dirty，拿宿主自己数的就会在“刚存完”那一拍说谎。
    project: Mutex<Option<Value>>,
    project_rev: Mutex<usize>,
    /// 批量任务台账（按 task_id 聚合的最新一条 task_state）。
    /// 存整份而不是只存条数：暂停/继续/取消按钮的可用态取决于**那一条现在是什么
    /// 状态**，而转移表在引擎里——宿主只搬运，不自己判“能不能暂停”。
    tasks: Mutex<Vec<Value>>,
    task_rev: Mutex<usize>,
    /// ready 的**整份**能力清单（M9-f）。以前每加一个名单（presets / grade_limits /
    /// export_caps / project_actions / task_actions）就要改一次 Rust：那正是双出处。
    /// 整份搬过去让 UI 直接按引擎报的名单画控件；没报就是 Null，UI 那一排不画。
    ready_caps: Mutex<Value>,
    /// 引擎在 ready 里报的版本（M5-c 发布自证）。宿主不拿自己的常量去填"这是 0.9.0"
    /// ——UI 的版本取自打包配置，引擎的版本取自同步后的 __version__，两者只在
    /// ready 里对得上；装机校验就是比这两份，不一致说明装的引擎不是这个壳配的。
    engine_version: Mutex<Option<String>>,
    /// 引擎运行时的来源（M5-c）：解释器路径、它从哪一档候选里选出来、源码目录、
    /// 以及 ready 里那份 pip 包账单。"引擎起不来"在三台机器上是三个原因，
    /// 把它们打到状态里，用户与发布校验才看得出现在到底缺哪一件。
    engine_runtime: Mutex<Value>,
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
            face: Mutex::new(None),
            inpaint: Mutex::new(None),
            light: Mutex::new(None),
            deform: Mutex::new(None),
            lut: Mutex::new(None),
            grade: Mutex::new(None),
            background: Mutex::new(None),
            enhance: Mutex::new(None),
            presets: Mutex::new(Vec::new()),
            grade_limits: Mutex::new(Vec::new()),
            export: Mutex::new(None),
            export_progress: Mutex::new(None),
            export_caps: Mutex::new(Value::Null),
            raw_backends: Mutex::new(Value::Null),
            matting_backends: Mutex::new(Value::Null),
            image_exts: Mutex::new(Value::Null),
            export_bits: Mutex::new(Value::Null),
            last_error: Mutex::new(None),
            session: Mutex::new(None),
            thumbs: Mutex::new(std::collections::HashMap::new()),
            session_rev: Mutex::new(0),
            pick: Mutex::new(None),
            pick_items: Mutex::new(0),
            history: Mutex::new(None),
            history_rev: Mutex::new(0),
            doc_report: Mutex::new(None),
            doc_rev: Mutex::new(0),
            history_edit_cmds: Mutex::new(Vec::new()),
            history_dirty: Mutex::new(false),
            project: Mutex::new(None),
            project_rev: Mutex::new(0),
            tasks: Mutex::new(Vec::new()),
            task_rev: Mutex::new(0),
            ready_caps: Mutex::new(Value::Null),
            engine_version: Mutex::new(None),
            engine_runtime: Mutex::new(Value::Null),
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

    /// 三条带 doc_state 的事件都进这里落一份"引擎最新说的文档状态 + 它是谁说的"。
    fn note_doc(&self, v: &Value, src: &str) {
        self.note_face(v, src);
        match v.get("doc_state") {
            Some(ds) if !ds.is_null() => {
                *self.doc_report.lock().unwrap() =
                    Some(json!({"source": src, "doc_state": ds}));
                *self.doc_rev.lock().unwrap() += 1;
            }
            _ => *self.doc_report.lock().unwrap() = None,
        }
        *self.history_dirty.lock().unwrap() = false;
    }

    pub fn on_image_ready(&self, v: &Value) {
        *self.image.lock().unwrap() = Some(v.clone());
        // image_ready 带着这一格文档的历史账（doc_state.history），脏标记可以落地
        self.note_doc(v, "image_ready");
    }

    pub fn on_precompute_ready(&self, v: &Value) {
        *self.precompute.lock().unwrap() = Some(v.clone());
        self.note_face(v, "precompute_ready");
    }

    /// 引擎关于「有几个人、在改哪一个」的任何一句陈述都进这里落一份。
    /// 事件自己带 `face`（precompute_ready / face_selected / face_list），带 `doc_state`
    /// 的那些（image_ready / history_state）里也有同一个对象——两个形状取到一个槽位。
    pub fn note_face(&self, v: &Value, src: &str) {
        let cand = v.get("face").cloned()
            .or_else(|| v.get("doc_state").and_then(|d| d.get("face")).cloned());
        match cand {
            Some(f) if f.is_object() => {
                *self.face.lock().unwrap() = Some(json!({"source": src, "face": f}));
            }
            _ => {
                // 没带这一格的事件不改动槽位：选型是文档状态，只有引擎说了才算
            }
        }
    }

    /// 多人图选人（PORTRAIT-003）：把用户那一次点击送进引擎，答复走 face_selected。
    #[allow(dead_code)]
    pub fn on_face(&self, v: &Value, src: &str) {
        self.note_face(v, src);
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

    pub fn on_grade_ready(&self, v: &Value) {
        *self.grade.lock().unwrap() = Some(v.clone());
    }

    pub fn on_enhance_ready(&self, v: &Value) {
        *self.enhance.lock().unwrap() = Some(v.clone());
    }

    pub fn on_bg_ready(&self, v: &Value) {
        *self.background.lock().unwrap() = Some(v.clone());
    }

    pub fn on_export_ready(&self, v: &Value) {
        *self.export.lock().unwrap() = Some(v.clone());
        // export_done 一到就把进度条归位：留着“12/20”跟在一句“共 20 张、失败 1”后面
        // 会被读成“还在跑”，而实际已经结束了
        *self.export_progress.lock().unwrap() = None;
    }

    /// 裁剪/曝光那一类 frame 事件：它们带 doc_state，不进这一格的话面板上的数字
    /// 就停在上一笔（而拖拽帧不带 doc_state，一条也不进）。高频路径上只多一次
    /// `Option` 判断。pub 而 note_doc 不 pub：判定只在 note_doc 一处，这里只多一个入口。
    pub fn on_layer_frame(&self, v: &Value) {
        self.note_doc(v, "frame");
    }

    /// 项目事件：最后一条就是“现在哪个工程、存没存、几张、丢了什么”。
    /// 五个名字进同一格：拆开存就会出“刚 create 完但徽章还写着上一个工程的 dirty”。
    pub fn on_project(&self, v: &Value) {
        *self.project.lock().unwrap() = Some(v.clone());
        *self.project_rev.lock().unwrap() += 1;
    }

    /// 台账：task_state 按 id 覆盖（保留队列插入序），task_list 整份重建，
    /// task_deleted 删一格。三个名字写同一张表，UI 只需读 tasks 一项目。
    pub fn on_task(&self, v: &Value) {
        {
            let mut t = self.tasks.lock().unwrap();
            match v.get("event").and_then(|e| e.as_str()).unwrap_or("") {
                "task_list" => {
                    if let Some(list) = v.get("tasks").and_then(|x| x.as_array()) {
                        *t = list.clone();
                    }
                }
                "task_deleted" => {
                    if let Some(id) = v.get("task_id").and_then(|x| x.as_str()) {
                        t.retain(|x| x.get("task_id").and_then(|i| i.as_str()) != Some(id));
                    }
                }
                _ => {
                    let id = v.get("task_id").and_then(|x| x.as_str()).unwrap_or("").to_string();
                    match t.iter_mut().find(|x| x.get("task_id").and_then(|i| i.as_str())
                                                   == Some(id.as_str())) {
                        Some(slot) => *slot = v.clone(),
                        None => t.push(v.clone()),
                    }
                }
            }
        }
        *self.task_rev.lock().unwrap() += 1;
    }

    pub fn on_session_state(&self, v: &Value) {
        *self.session.lock().unwrap() = Some(v.clone());
        // 同上：切文档那一条的 doc_state 就是新那一张的历史账
        self.note_doc(v, "session_state");
        *self.session_rev.lock().unwrap() += 1;
    }

    /// thumb_ready / thumb_failed 都进这里：一条给像素，一条给“这张解不开”。
    /// 两条都必须让前端重取整条底片条，所以一起 bump revision。
    pub fn on_thumb(&self, v: &Value) {
        if let (Some(p), Some(b)) = (v.get("path").and_then(|x| x.as_str()),
                                     v.get("jpeg_b64").and_then(|x| x.as_str())) {
            self.thumbs.lock().unwrap().insert(p.to_string(), b.to_string());
        }
        *self.session_rev.lock().unwrap() += 1;
    }

    /// 挑图的四种播报进同一格（最后一条就是当前事实），`pick_item` 只数一格并让前端
    /// 重取底片条：建议本体随 session_state 的 docs 走，宿主不另存一份（存两份就会漂）。
    pub fn on_pick(&self, v: &Value) {
        let name = v.get("event").and_then(|e| e.as_str()).unwrap_or("");
        if name == "pick_start" {
            *self.pick_items.lock().unwrap() = 0;
        } else if name == "pick_item" {
            *self.pick_items.lock().unwrap() += 1;
            *self.session_rev.lock().unwrap() += 1;
        } else if name == "pick_failed" {
            *self.session_rev.lock().unwrap() += 1;
        }
        if name != "pick_item" {
            *self.pick.lock().unwrap() = Some(v.clone());
        }
    }

    pub fn on_history(&self, v: &Value) {
        *self.history.lock().unwrap() = Some(v.clone());
        *self.history_rev.lock().unwrap() += 1;
        self.note_doc(v, "history_state");
    }

    pub fn on_export_progress(&self, v: &Value) {
        *self.export_progress.lock().unwrap() = Some(v.clone());
    }

    pub fn on_ready(&self, v: &Value) {
        // 整份能力清单先存下（新名单不用改宿主）：只取 JSON 里真是对象的那一份
        if v.is_object() {
            *self.ready_caps.lock().unwrap() = v.clone();
        }
        // 版本与运行时账单（M5-c）：没报就当这一版引擎不说自己是谁，置 None 而不是留上一份
        *self.engine_version.lock().unwrap() =
            v.get("version").and_then(|x| x.as_str()).map(String::from);
        // 引擎那份包账单挂在 **packages 子键**下，不铺平进宿主这一层：两边都有
        // "python" 这个键（宿主写解释器路径，引擎写解释器版本），铺平就是后到的把
        // 先到的顶掉。M5-c 装机校验那一轮正是这么读到 python="3.12.15" 的——
        // 数据是好的，只是"解释器路径"这一项被同名键吃了。
        match v.get("runtime") {
            Some(r) if r.is_object() => {
                let mut merged = self.engine_runtime.lock().unwrap().clone();
                if !merged.is_object() { merged = json!({}); }
                if let Some(obj) = merged.as_object_mut() {
                    obj.insert("packages".to_string(), r.clone());
                }
                *self.engine_runtime.lock().unwrap() = merged;
            }
            _ => {}
        }
        // 只接数组：缺键或非数组就当这一版引擎还没这一能力，留空而不是留上一份
        match v.get("presets").and_then(|p| p.as_array()) {
            Some(list) => *self.presets.lock().unwrap() = list.clone(),
            None => *self.presets.lock().unwrap() = Vec::new(),
        }
        match v.get("grade_limits").and_then(|p| p.as_array()) {
            Some(list) => *self.grade_limits.lock().unwrap() =
                list.iter().filter_map(|x| x.as_f64()).collect(),
            None => *self.grade_limits.lock().unwrap() = Vec::new(),
        }
        // 哪些命令算编辑（M5-b）：没报就当这一版引擎还没有历史，清空而不是留上一份
        match v.get("history_edit_cmds").and_then(|p| p.as_array()) {
            Some(list) => *self.history_edit_cmds.lock().unwrap() =
                list.iter().filter_map(|x| x.as_str().map(String::from)).collect(),
            None => *self.history_edit_cmds.lock().unwrap() = Vec::new(),
        }
        // 导出能力（M4）：没报就当这一版引擎还不能导出，置 Null 而不是留上一份
        // 放大能力（M7）与导出同屏，挂在同一份 caps 里：它管的也是"这张图能怎么出片"。
        // 同样"没报就置 null"：旧引擎不说倍率，UI 就不画放大那一排，而不是前端刻一份
        // [1,2,3,4] 然后拿一个引擎不认的参数去撞拒绝。
        *self.export_caps.lock().unwrap() = match (v.get("export_formats"), v.get("export_tile")) {
            (Some(f), Some(t)) => json!({"formats": f, "tile": t,
                                         "tile_default": v.get("export_tile_default"),
                                         "scales": v.get("upscale_scales"),
                                         "upscale_backends": v.get("upscale_backends")}),
            _ => Value::Null,
        };
        // RAW 能力清单（raw.py 的 raw_backends）：没报就当这一版引擎不说自己能不能读 RAW，
        // 置 Null 而不是留上一份（换进程/换壳后旧账单不能当本引擎的读）。
        *self.raw_backends.lock().unwrap() = match v.get("raw_backends") {
            Some(r) if r.is_object() => r.clone(),
            _ => Value::Null,
        };
        // 抠图后端（M6）：没报就置 Null（旧引擎不说这一句），不留上一份
        // 可收后缀名单（scan 那份白名单）：没报就置 Null，选择框退化成"什么都不过滤"，
        // 而不是拿一份宿主抄的名单去挡用户
        *self.image_exts.lock().unwrap() = match v.get("image_exts") {
            Some(r) if r.is_array() => r.clone(),
            _ => Value::Null,
        };
        // 位深能力是个字典（{"8":[…],"16":[…]}）：没报就置 Null，老引擎不说这一句时
        // UI 不画 16-bit 那个勾，而不是默认"应该支持"
        *self.export_bits.lock().unwrap() = match v.get("export_bits") {
            Some(r) if r.is_object() => r.clone(),
            _ => Value::Null,
        };
        *self.matting_backends.lock().unwrap() = match v.get("matting_backends") {
            Some(r) if r.is_object() => r.clone(),
            _ => Value::Null,
        };
    }

    pub fn on_frame_event(&self) {
        self.frames.lock().unwrap().emitted += 1;
    }

    pub fn on_bench_done(&self) {
        self.frames.lock().unwrap().bench_done = true;
    }

    fn send_to_engine(&self, cmd: Value) -> Result<(), String> {
        // M5-b：命令名先取出来（cmd 下面会被 send 吃掉）。它只用来标"可能有新的一步"，
        // 宿主不数步数、不自己判哪条命令算编辑——名单由引擎的 ready 报
        let name = cmd.get("cmd").and_then(|c| c.as_str()).unwrap_or("").to_string();
        let edited = self.history_edit_cmds.lock().unwrap().iter().any(|c| c == &name);
        let guard = self.engine.lock().map_err(|_| "引擎锁中毒".to_string())?;
        guard
            .as_ref()
            .ok_or_else(|| "引擎未启动".to_string())?
            .send(cmd)?;
        if edited {
            *self.history_dirty.lock().unwrap() = true;
        }
        Ok(())
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

/// 引擎解释器的候选表（M5-c 开箱即用）。这一张顺序与 `packaging/setup-runtime.sh`
/// 的头注释是同一条约定：脚本把运行时装到哪，宿主就得找到哪——两边分叉时，
/// 用户会遇到“明明装好了却说没装”。
///   1) $LRT_ENGINE_PY      开发/调试覆盖，永远优先
///   2) 用户级运行时      $XDG_DATA_HOME(≈~/.local/share)/LumaRetouch/engine/venv
///   3) 系统级运行时      /usr/lib/LumaRetouch/engine/venv（root 装的）
///   4) python3            兜底：几乎必然缺 torch，缺什么由 ready 的 runtime 账单明说
fn resolve_engine_py() -> (String, &'static str) {
    use std::path::Path;
    if let Ok(v) = std::env::var("LRT_ENGINE_PY") {
        if !v.is_empty() {
            return (v, "env");
        }
    }
    let data_home = match std::env::var("XDG_DATA_HOME") {
        Ok(v) if !v.is_empty() => Some(v),
        _ => std::env::var("HOME").ok().map(|h| format!("{h}/.local/share")),
    };
    let mut cands: Vec<String> = Vec::new();
    if let Some(d) = data_home {
        cands.push(format!("{d}/LumaRetouch/engine/venv/bin/python"));
    }
    cands.push("/usr/lib/LumaRetouch/engine/venv/bin/python".to_string());
    for c in cands {
        if Path::new(&c).exists() {
            return (c, "runtime");
        }
    }
    ("python3".to_string(), "fallback")
}

/// 运行时没就位时给用户的下一句话。装机布局与开发布局的脚本位置不同，
/// 拿错的那一条就是让人去跑一个不存在的路径。
fn runtime_setup_hint() -> String {
    const INSTALLED: &str = "/usr/lib/LumaRetouch/engine/setup-runtime.sh";
    if std::path::Path::new(INSTALLED).exists() {
        return format!("跑一次 {INSTALLED} 按显卡装引擎运行时（需能联网取 GPU 版 torch）");
    }
    "跑一次 packaging/setup-runtime.sh 按显卡装引擎运行时（需能联网取 GPU 版 torch）".to_string()
}

#[tauri::command]
fn start_engine(app: tauri::AppHandle, launcher: State<'_, Launcher>, py: String, src: String) -> Result<Value, String> {
    // 空串＝走候选表（M5-c）：以前这里直接落 "python3"，在没有任何开发环境的机器上
    // 得到的是一个“引擎起了又死了”的窗口——现在先探一次，不行就当场说清缺什么。
    let (py, source) = if py.is_empty() { resolve_engine_py() } else { (py, "explicit") };
    let probe = std::process::Command::new(&py).arg("--version").output();
    let py_version = match probe {
        Ok(o) if o.status.success() => {
            let s = String::from_utf8_lossy(&o.stdout).trim().to_string();
            if s.is_empty() { String::from_utf8_lossy(&o.stderr).trim().to_string() } else { s }
        }
        Ok(o) => {
            return Err(format!("{} 不可用（{}）：{}\n→ {}", py, source,
                              String::from_utf8_lossy(&o.stderr).trim(), runtime_setup_hint()));
        }
        Err(e) => {
            return Err(format!("调不起解释器 {py}（{source}）：{e}\n→ {}", runtime_setup_hint()));
        }
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
    // 运行时的来历**必须在 spawn 之前写进去**：spawn 里的读线程随时可能把 ready
    // 送进来，而 on_ready 是往这一份 object 里**并**包账单。先 spawn 后赋值的话，
    // 引擎比这里快一步（venv 里 import 早已热着时就成立）就会把 numpy/torch 那几条
    // 顶掉——“有时候有、有时候没”的发布账单比没有还坏。
    *st.engine_runtime.lock().unwrap() = json!({
        "python": py.clone(), "python_source": source, "python_version": py_version,
        "engine_src": src.clone(), "hint": runtime_setup_hint(),
    });
    *st.engine_version.lock().unwrap() = None;   // 版本等本进程的 ready 重新报
    let h = engine::spawn(&py, &src, &session, st.clone());
    let pid = h.pid();
    // 新引擎进程 = 空的会话。不清掉上一张图的就绪标记，自动流程会拿陈图的 w/h
    // 去驱一个 _vram=None 的新引擎（量出来就是“没跑但正常”）。
    *st.image.lock().unwrap() = None;
    *st.precompute.lock().unwrap() = None;
    *st.face.lock().unwrap() = None;        // 新进程没分析过任何图，名单是空的
    *st.deform.lock().unwrap() = None;      // 形变层随关键点走，新进程里没有关键点
    *st.lut.lock().unwrap() = None;          // 调色层也随文档走，新进程里一张表也没挂
    *st.grade.lock().unwrap() = None;        // 定向层同理：新进程里肤色参数应当全是零
    *st.inpaint.lock().unwrap() = None;      // 笔迹层随会话走：新进程里一笔也没落
    *st.light.lock().unwrap() = None;        // 增减层与笔迹同生命期
    *st.background.lock().unwrap() = None;   // 换底层同理：新进程里 matte=None
    *st.enhance.lock().unwrap() = None;      // 眼牙层同理：新进程里没有关键点，掩膜画不出
    *st.presets.lock().unwrap() = Vec::new();  // 清单等新进程的 ready 重新填
    *st.grade_limits.lock().unwrap() = Vec::new();
    *st.export.lock().unwrap() = None;         // 新进程还没导出一张，上一批的账单不是本会话的
    *st.export_progress.lock().unwrap() = None;
    *st.export_caps.lock().unwrap() = Value::Null;   // 能力等 ready 重新报
    *st.raw_backends.lock().unwrap() = Value::Null;   // RAW 能力清单等 ready 重新报
    *st.matting_backends.lock().unwrap() = Value::Null; // 抠图后端清单同理（M6）
    *st.image_exts.lock().unwrap() = Value::Null;
    *st.export_bits.lock().unwrap() = Value::Null;   // 后缀名单同理：等新进程报
    *st.last_error.lock().unwrap() = None;                // 新进程没说错过
    // 底片条也是引擎进程的事实：新进程还没扫过目录，留着旧列表就是让用户点一个
    // 这个进程从没见过的 index
    *st.session.lock().unwrap() = None;
    st.thumbs.lock().unwrap().clear();
    st.pick.lock().unwrap().take();
    *st.pick_items.lock().unwrap() = 0;
    *st.session_rev.lock().unwrap() += 1;
    // 历史属于一个引擎进程里的那份会话：新进程连图都没解，栈必须从零开始
    *st.history.lock().unwrap() = None;
    *st.history_rev.lock().unwrap() += 1;
    *st.doc_report.lock().unwrap() = None;
    *st.doc_rev.lock().unwrap() += 1;
    st.history_edit_cmds.lock().unwrap().clear();   // 名单等新进程的 ready 重新填
    *st.history_dirty.lock().unwrap() = false;

    // 握手：引擎的 ready（预设清单、grade 上限、导出能力、session/history 名单）
    // **只在收到 hello 时才发**。M5-b 之前这里从没发过 hello，于是装机件里
    // engine_status 报出来的 presets/grade_limits/export_caps/history_edit_cmds
    // 一路全是空的——UI 把这些能力全判成"这个引擎还没有"，而日志里一个错都不报。
    // 真窗口那一轮第一次把它抓出来：裸引擎的协议用例自己会发 hello，碰不到这一层。
    // 必须在句柄存进 st.engine 之前发出去：那里头没有别的人会替它问候一次。
    let _ = h.send(json!({"cmd": "hello"}));
    *st.engine.lock().map_err(|_| "引擎锁中毒".to_string())? = Some(Arc::new(h));
    Ok(json!({"pid": pid, "python": py, "python_source": source,
              "src": src, "session": session}))
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
    // 设备默认交回引擎去定（"auto"）：装机件里没人设 LRT_DEVICE，这里写死 "cpu" 就会
    // 把整条 GPU 管线绕开（M8 裸环境那一轮实测：卡与 rocm 版 torch 都在，会话却建在 CPU 上）。
    let device = std::env::var("LRT_DEVICE").unwrap_or_else(|_| "auto".into());
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
    // 91 ms/帧的“GPU”数据。默认同样交回引擎定（"auto"）：上一版这里写死 cpu，
    // 而“开箱即用”的那台机器上没人会设 LRT_DEVICE——GPU 版 torch 白装。
    let device = std::env::var("LRT_DEVICE").unwrap_or_else(|_| "auto".into());
    state.send_to_engine(json!({"cmd": "set_device", "device": device}))?;
    // 一次新的导入请求 = 上一张的账作废：错误位与 image 都清掉。不清的话，坏路径被
    // 引擎拒掉时 status.image 里还是上一张的 image_ready，宿主会把它读成"这次也成功了"。
    *state.last_error.lock().unwrap() = None;
    *state.image.lock().unwrap() = None;
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
    // 人脸名单同理：换一张图就是换一摞脸，留着旧名单会让人点到一个不存在的 index
    *state.face.lock().unwrap() = None;
    // 画笔图层也一起清：引擎侧 load_image 会丢旧笔画，宿主留着就是报一个不存在的图层状态
    *state.inpaint.lock().unwrap() = None;
    *state.light.lock().unwrap() = None;
    *state.deform.lock().unwrap() = None;
    // 调色层也是：上一张照片的色调不能静默带到这一张上（引擎侧 load_image 已把它清了）
    *state.lut.lock().unwrap() = None;
    *state.grade.lock().unwrap() = None;     // 上一张图的肤色参数不能静默带到这一张
    // 换底层也是：引擎在 cmd_load_image 里把 _bg 整层清回出厂态（_fresh_doc_state），
    // 宿主留着旧的那一份就会报“换底还开着”而屏幕上根本没有——按钮的灰与不灰、常驻
    // MiB 那一行都读这个槽位（与上面 inpaint/light/lut/grade 同一条理由）。
    *state.background.lock().unwrap() = None;
    // 上一批导出的账单也一样：它说的是另一张图的文件与字节数
    *state.export.lock().unwrap() = None;
    *state.export_progress.lock().unwrap() = None;
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

// 「按住看原图」。引擎侧它不在 EDIT_CMDS 里，所以这一趟只是转发一次出帧请求：
// 会话强度不动、撤销栈不占步。这里刻意不复用 set_strength —— 那样按住再松开会
// 留下一次"查看"作为可撤销步骤，用户下一次 Ctrl+Z 撤掉的就不是编辑而是查看。
#[tauri::command]
fn compare(state: State<'_, Arc<AppState>>, on: bool) -> Result<Value, String> {
    state.send_to_engine(json!({"cmd": "compare", "on": on}))?;
    Ok(json!({"on": on}))
}

/// 换底（M6）：一次“换底”一条命令。backend=color_key（默认、确定性色键）/ birefnet
/// （神经网络，无权重引擎会诚实拒）。bg 是 [r,g,b] 0–255。不返回同步结果：
/// 遮罩合成在引擎侧算，结果靠 engine_status().background 轮询（与 inpaint/light 同路）。
#[tauri::command]
fn background(
    state: State<'_, Arc<AppState>>,
    action: String,
    backend: Option<String>,
    bg: Option<Vec<u64>>,
    tol: Option<f64>,
    softness: Option<f64>,
) -> Result<Value, String> {
    let mut cmd = json!({"cmd": "background", "action": action});
    if let Some(b) = backend.filter(|s| !s.is_empty()) {
        cmd["backend"] = json!(b);
    }
    if let Some(v) = bg {
        cmd["bg"] = json!(v);
    }
    if let Some(v) = tol {
        cmd["tol"] = json!(v);
    }
    if let Some(v) = softness {
        cmd["softness"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
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
    scope: Option<String>,
) -> Result<Value, String> {
    let mut cmd = json!({"cmd": "deform", "action": action});
    // 与 light 同一条规矩：给了才附。宿主写默认值等于替引擎做决定，
    // 生产默认值一改这条通路就会静默漂开。
    if let Some(v) = amounts {
        cmd["amounts"] = v;
    }
    // 作用层（LNX-PORTRAIT-004）：all=改全人物默认 / person=只覆盖当前选定那一张。
    // 同样"给了才附"——引擎那边的默认值才是唯一出处，这里再刻一份就是双出处。
    if let Some(v) = scope {
        cmd["scope"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 多人图选人（PORTRAIT-003）与人脸名单的人工账（PORTRAIT-006）：
/// action list / select / disable / enable / add / remove（前四个要带 index，add 要带 rect）。
///
/// 为什么这条必须由引擎回答而不是前端自己数：SCOPE-001 挡的就是「引擎替你选了一张脸」，
/// 那放行的凭据必须是用户的一次显式点击，而名单只能来自那一次真实分析。前端数出来的
/// chip 与引擎能服务的张数一旦不一致，「点了没反应」就再也没人说得清是谁的错。
///
/// 动作与 rect 都**不在这层白名单**：引擎是唯一出处（ready 报 `face_actions`）。上一版
/// 这里少一条 rect，宿主把"用户框的那一张"整条丢掉，前端收到 requested=true 而引擎从没
/// 见过那条框——桥层静默吞参数是本轮 auto_pick 那次同款事故的形状，所以参数一律转发。
#[tauri::command]
fn face(
    state: State<'_, Arc<AppState>>,
    action: String,
    index: Option<u32>,
    rect: Option<Vec<f64>>,
) -> Result<Value, String> {
    let mut cmd = json!({"cmd": "face", "action": action});
    if let Some(v) = index {
        cmd["index"] = json!(v);
    }
    if let Some(v) = rect {
        cmd["rect"] = json!(v);
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

/// 眼牙局部增强（LNX-PORTRAIT-009）：三个子功能独立启停。
///
/// 一律"给了才附"：部分提交语义靠的就是"没给"与"给了 0"的区别，宿主替引擎填 0.0
/// 就等于把另外两格抹零（与 grade/deform 同一条规矩）。
#[tauri::command]
fn enhance(
    state: State<'_, Arc<AppState>>,
    action: String,
    sclera: Option<f64>,
    iris: Option<f64>,
    teeth: Option<f64>,
) -> Result<Value, String> {
    let mut cmd = json!({"cmd": "enhance", "action": action});
    if let Some(v) = sclera {
        cmd["sclera"] = json!(v);
    }
    if let Some(v) = iris {
        cmd["iris"] = json!(v);
    }
    if let Some(v) = teeth {
        cmd["teeth"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 肤色定向（M3-b）：三个增量 + 一个混入比例。action: set / amount / clear。
///
/// 与 lut 的发送时机相反：这一层是“拖哪个滑块就动哪个”，所以拖动期间逐事件发。
/// 不逐发就是“滑块拖了、画面不动”（引擎侧每帧真跑一次定向内核，产品档实测 1.3 ms）。
/// 这里不夹取也不填默认值：滑块范围由引擎的 grade_limits 说，宿主抄一份必漂。
#[tauri::command]
fn grade(
    state: State<'_, Arc<AppState>>,
    action: String,
    dh: Option<f64>,
    ds: Option<f64>,
    dv: Option<f64>,
    amount: Option<f64>,
    scope: Option<String>,
    rle: Option<Value>,
    feather: Option<u64>,
    mode: Option<String>,
) -> Result<Value, String> {
    let mut cmd = json!({"cmd": "grade", "action": action});
    // 一律“给了才附”：部分提交语义靠的就是“没给”与“给了 0”的区别，
    // 宿主填个默认 0.0 就等于把另外两个滑块抹零。
    if let Some(v) = dh {
        cmd["dh"] = json!(v);
    }
    if let Some(v) = ds {
        cmd["ds"] = json!(v);
    }
    if let Some(v) = dv {
        cmd["dv"] = json!(v);
    }
    if let Some(v) = amount {
        cmd["amount"] = json!(v);
    }
    // COLOR-004 局部调色：作用域与画笔区域同一条命令走（引擎那一侧的 action：
    // scope / mask / mask_clear）。这里也不能替引擎填默认值：“没给”与
    // “给了全图”在引擎里是两种语义（前者不动作用域，后者会把局部改回全图）。
    if let Some(v) = scope {
        cmd["scope"] = json!(v);
    }
    if let Some(v) = rle {
        cmd["rle"] = v;
    }
    if let Some(v) = feather {
        cmd["feather"] = json!(v);
    }
    if let Some(v) = mode {
        cmd["mode"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 全尺寸分块导出（M4）。不带 images 就是导当前这张；带 out_dir 必需。
///
/// 这一条与上面几个图层命令不同：它不在主线程算任何东西，只是把请求递给了
/// 引擎的 worker 线程——满幅一块图就能是几秒，UI 线程不能等。进度与终态从
/// export_progress / export_done 两条事件拿（engine_status 轮询），不靠这里返回。
/// 同样一律“给了才附”：格式与 tile 的默认值属于引擎，宿主填一份就会在引擎改
/// 默认值时静默漂开（export_formats / export_tile 就是为此才由 ready 报的）。
#[tauri::command]
fn export(
    state: State<'_, Arc<AppState>>,
    out_dir: String,
    format: Option<String>,
    quality: Option<i64>,
    tile: Option<i64>,
    images: Option<Vec<String>>,
    // 放大（M7）：倍率与出片锐量。宿主不填默认值——那两个数的出处是引擎的
    // ready（upscale_scales），宿主抄一份就会在引擎改口径时静默漂开。
    scale: Option<i64>,
    sharpen: Option<f64>,
    upscale_backend: Option<String>,
    // 导出位深（M9-e）：宿主不填默认值。不给就让引擎按它自己的 8 走，
    // 宿主把 8 写死在这里就是把引擎的默认值拷进了宿主。（函数参数上不能挂 ///：
    // 那是文档注释，只许贴在条目自己那一级，cargo 会直接拒掉这一份签名）
    bit_depth: Option<i64>,
    // 导出侧 P0 口径的四格（d2c）：名单以引擎为准，宿主不填默认值（填了就是把
    // 引擎的中性位拷进宿主，而中性位属于产品决策，ADR-0003 冻结的就是它）
    output_profile: Option<String>,
    tiff_compression: Option<String>,
    metadata_include_gps: Option<bool>,
    conflict_policy: Option<String>,
) -> Result<Value, String> {
    let mut cmd = json!({"cmd": "export", "action": "start", "out_dir": out_dir});
    if let Some(v) = format {
        cmd["format"] = json!(v);
    }
    if let Some(v) = quality {
        cmd["quality"] = json!(v);
    }
    if let Some(v) = tile {
        cmd["tile"] = json!(v);
    }
    if let Some(v) = images {
        cmd["images"] = json!(v);
    }
    if let Some(v) = scale {
        cmd["scale"] = json!(v);
    }
    if let Some(v) = sharpen {
        cmd["sharpen"] = json!(v);
    }
    if let Some(v) = upscale_backend {
        cmd["upscale_backend"] = json!(v);
    }
    if let Some(v) = bit_depth {
        cmd["bit_depth"] = json!(v);
    }
    for (k, v) in [
        ("output_profile", output_profile.map(Value::from)),
        ("tiff_compression", tiff_compression.map(Value::from)),
        ("metadata_include_gps", metadata_include_gps.map(Value::from)),
        ("conflict_policy", conflict_policy.map(Value::from)),
    ] {
        if let Some(v) = v {
            cmd[k] = v;
        }
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

/// 只读快照：把当前最新一帧的**整帧像素**取回去，不判重、不记账、不碰 pending/samples。
///
/// 为什么要有这一条而复用 `pull_frame`：那条命令是丢帧统计的地基（同 seq 拒发、
/// 在途队列、reap 都挂在它上面），测试路径走它就会被"这帧已经投过了"拒掉，而
/// 前端渲染循环本来就在逐帧拉取——自动通道永远抢不到那一帧。这里要的恰恰是
/// "此刻屏幕上是什么"，与投递计数无关，所以另开一条纯读的口。
/// `LRT_SKIP_PIXELS` 那类宿主对照组也不影响它：这里必须拿到像素，否则对拍是空的。
#[tauri::command]
fn peek_frame(state: State<'_, Arc<AppState>>) -> Result<tauri::ipc::Response, String> {
    let f = state.frames.lock().map_err(|_| "锁中毒".to_string())?;
    let shm = f.shm.as_ref().ok_or("SHM_NOT_READY")?;
    let (meta, slot) = shm.freshest().ok_or("NO_FRAME_YET")?;
    let n = shm.pixel_size;
    let mut buf = vec![0u8; 40 + n];
    shm.copy_span(slot, 0, &mut buf[40..])?;
    buf[0..8].copy_from_slice(&meta.seq.to_le_bytes());
    buf[8..16].copy_from_slice(&meta.t_ns.to_le_bytes());
    buf[16..24].copy_from_slice(&now_ns().to_le_bytes());
    buf[24..28].copy_from_slice(&meta.w.to_le_bytes());
    buf[28..32].copy_from_slice(&meta.h.to_le_bytes());
    buf[32..36].copy_from_slice(&(n as u32).to_le_bytes());
    // y0 恒 0、行数恒 h：这条口的语义就是整帧
    buf[36..40].copy_from_slice(&0u32.to_le_bytes());
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
    let face = state.face.lock().unwrap().clone();
    let inpaint = state.inpaint.lock().unwrap().clone();
    let light = state.light.lock().unwrap().clone();
    let deform = state.deform.lock().unwrap().clone();
    let lut = state.lut.lock().unwrap().clone();
    let grade = state.grade.lock().unwrap().clone();
    let background = state.background.lock().unwrap().clone();
    let enhance = state.enhance.lock().unwrap().clone();
    let export = state.export.lock().unwrap().clone();
    let export_progress = state.export_progress.lock().unwrap().clone();
    let export_caps = state.export_caps.lock().unwrap().clone();
    let raw_backends = state.raw_backends.lock().unwrap().clone();
    let matting_backends = state.matting_backends.lock().unwrap().clone();
    let image_exts = state.image_exts.lock().unwrap().clone();
    let export_bits = state.export_bits.lock().unwrap().clone();
    let last_error = state.last_error.lock().unwrap().clone();
    let session = state.session.lock().unwrap().clone();
    let session_rev = *state.session_rev.lock().unwrap();
    let history = state.history.lock().unwrap().clone();
    let history_rev = *state.history_rev.lock().unwrap();
    let history_dirty = *state.history_dirty.lock().unwrap();
    let doc_report = state.doc_report.lock().unwrap().clone();
    let doc_rev = *state.doc_rev.lock().unwrap();
    let thumbs_ready = state.thumbs.lock().unwrap().len();
    let pick = state.pick.lock().unwrap().clone();
    let pick_items = *state.pick_items.lock().unwrap();
    let presets: Vec<Value> = state.presets.lock().unwrap().clone();
    let grade_limits: Vec<f64> = state.grade_limits.lock().unwrap().clone();
    json!({"shm": shm_name, "has_shm": has_shm, "emitted": emitted,
           "delivered": delivered, "logs": logs, "image": image, "precompute": precompute,
           "face": face,
           "inpaint": inpaint, "light": light, "deform": deform, "lut": lut,
           "grade": grade, "presets": presets, "grade_limits": grade_limits,
           "background": background, "enhance": enhance,
           "export": export, "export_progress": export_progress,
           "export_caps": export_caps,
           "raw_backends": raw_backends,
           // 抠图后端（M6）：UI 的下拉项由这一份决定，不在前端猜"装了 birefnet 就能选"
           "matting_backends": matting_backends,
           "image_exts": image_exts,
           "export_bits": export_bits,
           "last_error": last_error,
           // 底片条的“有没有、几张、当前哪一格”进轮询（小），像素本体不进：
           // 那两百张要由 filmstrip 单独取，且只在 session_rev 变了的时候取
           "session": session, "session_rev": session_rev,
           "thumbs_ready": thumbs_ready,
           // 挑图（PICK-001）：进度与账单。建议本体在 session.docs 的每一格里
           "pick": pick, "pick_items": pick_items,
           // 撤销/重做（M5-b）：上一条结果 + 变更序号。按钮的灰与不灰、滑块的重摆
           // 都只看这两项，前端不许自己数步数
           "history": history, "history_rev": history_rev,
           "history_dirty": history_dirty,
           "doc_report": doc_report, "doc_rev": doc_rev,
           // 项目面与任务台账（LNX-P0-PROJECT / LNX-P0-TASK）：小载荷（没像素），
           // 所以进轮询；UI 的“未保存”徽章与队列按钮全看这几项，不自己数
           "project": state.project.lock().unwrap().clone(),
           "project_rev": *state.project_rev.lock().unwrap(),
           "tasks": state.tasks.lock().unwrap().clone(),
           "task_rev": *state.task_rev.lock().unwrap(),
           "ready_caps": state.ready_caps.lock().unwrap().clone(),
           "history_edit_cmds": state.history_edit_cmds.lock().unwrap().clone(),
           // 发布自证（M5-c）：壳选的是哪个解释器（含它从哪一档候选里来）、引擎报的
           // 版本与包账单、以及进程现在还在不在。"引擎起不来"的三种成因（没运行时 /
           // 运行时缺包 / 跑到一半崩了）在三行上是不同的形状，混在一句"引擎未启动"里
           // 就谁也没法定位。
           "engine_alive": state.engine.lock().unwrap().as_ref()
               .map(|h| h.is_alive()).unwrap_or(false),
           "engine_version": state.engine_version.lock().unwrap().clone(),
           "engine_runtime": state.engine_runtime.lock().unwrap().clone()})
}

#[tauri::command]
fn shutdown_engine(state: State<'_, Arc<AppState>>) -> Value {
    let h = state.engine.lock().unwrap().clone();
    // 引擎停了，它报过的 image_ready / precompute_ready 也随之作废；留着会让下一次
    // 自动流程拿陈尺寸与陈掩膜状态起跑
    *state.image.lock().unwrap() = None;
    *state.precompute.lock().unwrap() = None;
    *state.face.lock().unwrap() = None;
    *state.inpaint.lock().unwrap() = None;
    *state.light.lock().unwrap() = None;
    *state.deform.lock().unwrap() = None;
    *state.lut.lock().unwrap() = None;
    *state.grade.lock().unwrap() = None;
    *state.background.lock().unwrap() = None;   // 换底层也随会话走：进程没了就没有层
    *state.presets.lock().unwrap() = Vec::new();   // 引擎没了，它报过的清单也就没了
    *state.grade_limits.lock().unwrap() = Vec::new();
    *state.export.lock().unwrap() = None;
    *state.export_progress.lock().unwrap() = None;
    *state.export_caps.lock().unwrap() = Value::Null;
    *state.raw_backends.lock().unwrap() = Value::Null;    // 能力是引擎报的，不是永久的
    *state.matting_backends.lock().unwrap() = Value::Null; // 同上（M6）
    *state.image_exts.lock().unwrap() = Value::Null;
    *state.export_bits.lock().unwrap() = Value::Null;  // 同上
    *state.last_error.lock().unwrap() = None;          // 同上
    *state.session.lock().unwrap() = None;
    state.thumbs.lock().unwrap().clear();
    *state.session_rev.lock().unwrap() += 1;
    *state.history.lock().unwrap() = None;
    *state.history_rev.lock().unwrap() += 1;
    *state.doc_report.lock().unwrap() = None;
    *state.doc_rev.lock().unwrap() += 1;
    state.history_edit_cmds.lock().unwrap().clear();
    *state.history_dirty.lock().unwrap() = false;
    match h {
        Some(h) => {
            h.shutdown();
            json!({"shutdown": true})
        }
        None => json!({"shutdown": false, "reason": "引擎未启动"}),
    }
}

/// 底片条（M5-a）：一条命令转发六个动作。参数一律「给了才附」，与 export 同一条
/// 理由——默认值属于引擎，宿主填一份就会在引擎改默认值时静默漂开。
/// 这里的 action 白名单只是把手挡（拼错的动作名不该变成一个引擎事件），
/// 真口径仍以引擎的拒绝为准：名单与它报出来的 session_actions 同源。
#[tauri::command]
fn session(
    state: State<'_, Arc<AppState>>,
    action: String,
    dir: Option<String>,
    paths: Option<Vec<String>>,
    index: Option<i64>,
    edge: Option<i64>,
    quality: Option<i64>,
    limit: Option<i64>,
    thumbs: Option<bool>,
) -> Result<Value, String> {
    const ACTIONS: [&str; 6] = ["scan", "add", "select", "state", "thumbs", "stop_thumbs"];
    if !ACTIONS.contains(&action.as_str()) {
        return Err(format!("session 不认识动作 {action}（可用：{}）", ACTIONS.join("/")));
    }
    let mut cmd = json!({"cmd": "session", "action": action});
    if let Some(v) = dir {
        cmd["dir"] = json!(v);
    }
    if let Some(v) = paths {
        cmd["paths"] = json!(v);
    }
    if let Some(v) = index {
        cmd["index"] = json!(v);
    }
    if let Some(v) = edge {
        cmd["edge"] = json!(v);
    }
    if let Some(v) = quality {
        cmd["quality"] = json!(v);
    }
    if let Some(v) = limit {
        cmd["limit"] = json!(v);
    }
    if let Some(v) = thumbs {
        cmd["thumbs"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 挑图建议（LNX-PICK-001）：一条命令转发 analyze/stop/state。
///
/// 这里**不写动作白名单**（session/history/project 那三处各有一份手抄名单）。理由不是偷懒：
/// 引擎的拒绝文案里已经带着名单（`名单在 ready 的 pick_actions 里`），宿主再抄一份就是
/// 两个答案——加一档时先撞宿主的挡，用户看到的是"不认识动作"而不是引擎那句真话。
/// 参数一律「给了才附」：默认档位属于引擎，宿主填一份就会在引擎改默认时静默漂开。
#[tauri::command]
fn pick(
    state: State<'_, Arc<AppState>>,
    action: String,
    indices: Option<Vec<i64>>,
    paths: Option<Vec<String>>,
    edge: Option<i64>,
    model_dir: Option<String>,
    duplicate: Option<String>,
    blur: Option<String>,
    exposure: Option<String>,
    eyes: Option<String>,
    force: Option<bool>,
) -> Result<Value, String> {
    let mut cmd = json!({"cmd": "pick", "action": action});
    if let Some(v) = indices {
        cmd["indices"] = json!(v);
    }
    if let Some(v) = paths {
        cmd["paths"] = json!(v);
    }
    if let Some(v) = edge {
        cmd["edge"] = json!(v);
    }
    if let Some(v) = model_dir {
        cmd["model_dir"] = json!(v);
    }
    if let Some(v) = duplicate {
        cmd["duplicate"] = json!(v);
    }
    if let Some(v) = blur {
        cmd["blur"] = json!(v);
    }
    if let Some(v) = exposure {
        cmd["exposure"] = json!(v);
    }
    if let Some(v) = eyes {
        cmd["eyes"] = json!(v);
    }
    if let Some(v) = force {
        cmd["force"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 撤销/重做（M5-b）：四个动作一条命令，宿主只做把手。步数上限、手势合并窗口、
/// 哪几层进历史、随文档走的那条栈——全在引擎里；在这里刻一份就会漂一份。
#[tauri::command]
fn history(state: State<'_, Arc<AppState>>, action: String) -> Result<Value, String> {
    const ACTIONS: [&str; 4] = ["undo", "redo", "state", "clear"];
    if !ACTIONS.contains(&action.as_str()) {
        return Err(format!("history 不认识动作 {action}（可用：{}）", ACTIONS.join("/")));
    }
    state.send_to_engine(json!({"cmd": "history", "action": action}))?;
    Ok(json!({"requested": true}))
}

/// 项目（LNX-P0-PROJECT / CORE-001、007、008）：创建/打开/保存/标签/回收站。
/// 原子写、脏标记、资产去重、指纹全在引擎的 project.py；这里只做把手。动作名单
/// 照抄引擎 ready 里的 project_actions，宿主刻一份就有两份答案（session/history 同形）。
#[tauri::command]
fn project(
    state: State<'_, Arc<AppState>>,
    action: String,
    name: Option<String>,
    directory: Option<String>,
    path: Option<String>,
    doc: Option<String>,
    index: Option<i64>,
    tags: Option<Vec<String>>,
    label: Option<String>,
    trashed: Option<bool>,
    force: Option<bool>,
) -> Result<Value, String> {
    const ACTIONS: [&str; 6] = ["create", "open", "save", "state", "tag", "trash"];
    if !ACTIONS.contains(&action.as_str()) {
        return Err(format!("project 不认识动作 {action}（可用：{}）", ACTIONS.join("/")));
    }
    let mut cmd = json!({"cmd": "project", "action": action});
    for (k, v) in [
        ("name", name.map(Value::from)),
        ("directory", directory.map(Value::from)),
        ("path", path.map(Value::from)),
        ("doc", doc.map(Value::from)),
        ("index", index.map(Value::from)),
        ("trashed", trashed.map(Value::from)),
        ("force", force.map(Value::from)),
    ] {
        if let Some(v) = v {
            cmd[k] = v;
        }
    }
    // tags 与 label 只在 tag 动作上有意义，但空数组也是一个意思（“把标签清空”）：
    // 拿 `if let Some` 判就区分不了“没给”与“给了一串空”，而后者是用户的明确动作
    if let Some(v) = tags {
        cmd["tags"] = json!(v);
    }
    if let Some(v) = label {
        cmd["label"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 批量任务队列（LNX-P0-TASK）：暂停/继续/取消/重试/删除/列清单。
/// 转移表只在引擎的 tasks.py：宿主不判“这条能不能暂停”，也不拿“最后一个任务”当默认
/// 目标（那会静默叫停错的那一批），只把 id 递过去。
#[tauri::command]
fn task(
    state: State<'_, Arc<AppState>>,
    action: String,
    task: Option<String>,
) -> Result<Value, String> {
    const ACTIONS: [&str; 6] = ["list", "pause", "resume", "cancel", "retry", "delete"];
    if !ACTIONS.contains(&action.as_str()) {
        return Err(format!("task 不认识动作 {action}（可用：{}）", ACTIONS.join("/")));
    }
    let mut cmd = json!({"cmd": "task", "action": action});
    if let Some(v) = task {
        cmd["task"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 模块预设（LNX-P0-PRESET / PRESET-001、002）：清单/应用/保存/导入/删除一条命令。
/// “哪些参数属于哪个模块”“这个预设文件能不能接”全在引擎的 scope.py + preset_store.py：
/// 宿主抄一份模块名单或量程就是第二个会漂的地方（与 exposure/crop 同一条理由）。
/// 清单随 session_state 的 `presets` 上来，这里不开“拿清单”的口子给前端自己扫目录。
#[tauri::command]
fn preset(
    state: State<'_, Arc<AppState>>,
    action: String,
    id: Option<String>,
    name: Option<String>,
    path: Option<String>,
    kind: Option<String>,
    note: Option<String>,
    force: Option<bool>,
    module_scope: Option<Vec<String>>,
) -> Result<Value, String> {
    const ACTIONS: [&str; 5] = ["list", "apply", "save", "import", "delete"];
    if !ACTIONS.contains(&action.as_str()) {
        return Err(format!("preset 不认识动作 {action}（可用：{}）", ACTIONS.join("/")));
    }
    let mut cmd = json!({"cmd": "preset", "action": action});
    for (k, v) in [
        ("id", id.map(Value::from)),
        ("name", name.map(Value::from)),
        ("path", path.map(Value::from)),
        ("kind", kind.map(Value::from)),
        ("note", note.map(Value::from)),
        ("force", force.map(Value::from)),
    ] {
        if let Some(v) = v {
            cmd[k] = v;
        }
    }
    if let Some(v) = module_scope {
        cmd["module_scope"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 批量同步（LNX-P0-BATCH / BATCH-004）：preflight/commit/undo/state。
/// 目标一律按 path 递：重扫一次目录 index 会换而 path 不会（与底片条多选集同一口径）。
/// 作用域合法性、人脸范围判定、冲突与原子提交全在引擎：宿主不判“这一格能不能同步”，
/// 也不拿“上一个 batch_id”当默认目标之外的事——这里只把 id 递过去。
#[tauri::command]
fn batch(
    state: State<'_, Arc<AppState>>,
    action: String,
    docs: Option<Vec<String>>,
    module_scope: Option<Vec<String>>,
    conflict_policy: Option<String>,
    batch_id: Option<String>,
) -> Result<Value, String> {
    const ACTIONS: [&str; 4] = ["preflight", "commit", "undo", "state"];
    if !ACTIONS.contains(&action.as_str()) {
        return Err(format!("batch 不认识动作 {action}（可用：{}）", ACTIONS.join("/")));
    }
    let mut cmd = json!({"cmd": "batch", "action": action});
    if let Some(v) = docs {
        cmd["docs"] = json!(v);
    }
    if let Some(v) = module_scope {
        cmd["module_scope"] = json!(v);
    }
    if let Some(v) = conflict_policy {
        cmd["conflict_policy"] = json!(v);
    }
    if let Some(v) = batch_id {
        cmd["batch_id"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 曝光/白平衡（P0 注册表 lnx.exposure / lnx.white_balance）。量程不在这里写：
/// 引擎随事件报 exposure_limits，宿主抄一份数就是第二个会漂的地方。
#[tauri::command]
fn exposure(
    state: State<'_, Arc<AppState>>,
    action: String,
    ev: Option<f64>,
    temperature_shift: Option<f64>,
    tint_shift: Option<f64>,
    reference_k: Option<f64>,
) -> Result<Value, String> {
    const ACTIONS: [&str; 2] = ["set", "clear"];
    if !ACTIONS.contains(&action.as_str()) {
        return Err(format!("exposure 不认识动作 {action}（可用：{}）", ACTIONS.join("/")));
    }
    let mut cmd = json!({"cmd": "exposure", "action": action});
    for (k, v) in [
        ("ev", ev.map(Value::from)),
        ("temperature_shift", temperature_shift.map(Value::from)),
        ("tint_shift", tint_shift.map(Value::from)),
        ("reference_k", reference_k.map(Value::from)),
    ] {
        if let Some(v) = v {
            cmd[k] = v;
        }
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 裁剪/旋转（P0 注册表 lnx.crop.v1）。rect 是归一化的 [左,上,右,下]，
/// 正角顺时针——两个口径的出处都在引擎 ops/geometry.py，宿主不另定一套。
#[tauri::command]
fn crop(
    state: State<'_, Arc<AppState>>,
    action: String,
    rect: Option<Vec<f64>>,
    rotation_degrees: Option<f64>,
) -> Result<Value, String> {
    const ACTIONS: [&str; 2] = ["set", "clear"];
    if !ACTIONS.contains(&action.as_str()) {
        return Err(format!("crop 不认识动作 {action}（可用：{}）", ACTIONS.join("/")));
    }
    let mut cmd = json!({"cmd": "crop", "action": action});
    if let Some(v) = rect {
        cmd["rect"] = json!(v);
    }
    if let Some(v) = rotation_degrees {
        cmd["rotation_degrees"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// 整条底片条：格子的元信息来自最近一条 session_state，缩略图按 path 现场配对。
/// 单独一条命令而不是塞进 engine_status 轮询：两百张 base64 有 1.4 MB，
/// 每秒克隆一遍是白给的性能税（前端只在 session_rev 变了时取）。
#[tauri::command]
fn filmstrip(state: State<'_, Arc<AppState>>) -> Value {
    let session = state.session.lock().unwrap().clone();
    let thumbs = state.thumbs.lock().unwrap().clone();
    json!({"session": session, "thumbs": thumbs})
}

/// M0 自动跑靶配置：环境变量传进来，让整条通路可以被脚本驱起来跑。
#[tauri::command]
fn m0_env() -> Value {
    json!({
        "auto_bench": std::env::var("LRT_AUTO_BENCH").unwrap_or_default(),
        "engine_py": std::env::var("LRT_ENGINE_PY").unwrap_or_default(),
        "engine_src": std::env::var("LRT_ENGINE_SRC").unwrap_or_default(),
        // 没设 LRT_DEVICE 时报 "auto"（引擎会把它落实成 cuda/cpu）：这里写死 cpu 就会
        // 让跑靶报表上的设备栏与真用的那个不一致
        "device": std::env::var("LRT_DEVICE").unwrap_or_else(|_| "auto".into()),
        "skip_draw": std::env::var("LRT_SKIP_DRAW").unwrap_or_default(),
        "skip_pixels": std::env::var("LRT_SKIP_PIXELS").unwrap_or_default(),
        "upload": std::env::var("LRT_UPLOAD").unwrap_or_else(|_| "raw".into()),
        "chunks": std::env::var("LRT_CHUNKS").ok()
            .and_then(|v| v.parse::<u32>().ok())
            .filter(|v| (1..=64).contains(v))
            .unwrap_or(1),
        "no_ctx": std::env::var("LRT_NO_CTX").unwrap_or_default(),
        "no_mirror": std::env::var("LRT_NO_MIRROR").unwrap_or_default(),
        "gl_visible": std::env::var("LRT_GL_VISIBLE").unwrap_or_default(),
        // 视口自证探针（M9）：静态图静置后读回画布缓冲并量布局矩形。历轮跑靶的证据取的是
        // shm 那一帧，即“引擎→宿主”那一段；“宿主→屏幕”那一段从没测过，而 WebKitGTK 的
        // GL 表面截图只会抓到纯黑客户区——黑屏与布局撑爆正是从这条缝里漏出去的。
        "viewport_probe": std::env::var("LRT_VIEWPORT_PROBE").unwrap_or_default(),
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
        // M3-b 肤色定向自动通道："dh:ds:dv:amount"。与上面几条同一条理由：只有真窗口
        // 能证明 runGrade → Rust grade → 引擎 grade_done 这条命令签名对得上。
        "auto_grade": std::env::var("LRT_AUTO_GRADE").unwrap_or_default(),
        // 局部调色（COLOR-004）："fx:fy:r:dh:ds:dv"。区域外逐字节不动这一条只能在真窗口量，
        // 所以它与上面几条同一个身份：签名递得到 + 画面真的按作用域在动。
        "auto_local_color": std::env::var("LRT_AUTO_LOCAL_COLOR").unwrap_or_default(),
        // 眼牙增强（LNX-PORTRAIT-009）："sclera:iris:teeth"。与上面几条同一个身份：
        // 只有真窗口能证明 runEnhance → Rust enhance → 引擎 enhance_done 这条签名对得上。
        "auto_enhance": std::env::var("LRT_AUTO_ENHANCE").unwrap_or_default(),
        "auto_face": std::env::var("LRT_AUTO_FACE").unwrap_or_default(),
        // 人工纠正优先（LNX-PORTRAIT-006）那一臂。上一轮 auto_pick 就是漏在这一行没写：
        // 脚本传了 env、App.tsx 有臂，而桥不转发，于是那条臂**从没跑过**而外面只知道
        // "等满了超时"。桥层漏一个键 = 一条臂静静消失，所以这一格必须与 App.tsx 的臂同名
        "auto_manual": std::env::var("LRT_AUTO_MANUAL").unwrap_or_default(),
        "auto_drop": std::env::var("LRT_AUTO_DROP").unwrap_or_default(),
        "auto_empty": std::env::var("LRT_AUTO_EMPTY").unwrap_or_default(),
        // M4 导出自动通道："<目录>@<格式>@<tile>"（tile 与格式可省）。真窗口跑这一条
        // 才能证明 runExport → Rust export → 引擎 export_done 对得上，而且落盘文件
        // 的尺寸是“满幅不是代理档”的唯一直接证据
        "auto_export": std::env::var("LRT_AUTO_EXPORT").unwrap_or_default(),
        // 底片条自动通道："<目录>[@<选中第几张>[@<edge>]]"，给真窗口确认轮用
        "auto_filmstrip": std::env::var("LRT_AUTO_FILMSTRIP").unwrap_or_default(),
        // 撤销/重做自动通道：<强度值>，给真窗口确认轮用。它验的不是引擎（引擎有
        // 协议用例逐字节对拍），而是 runHistory → Rust history → 引擎 history_state
        // 这条命令签名在真窗口里对不对得上——Tauri 参数名不匹配时是静默丢参数。
        // 换底自检（M6）：非空则前端自动走一次色键换底（“rrggbb:tol:softness”）
        "auto_background": std::env::var("LRT_AUTO_BG").unwrap_or_default(),
        "auto_history": std::env::var("LRT_AUTO_HISTORY").unwrap_or_default(),
        // 发布自检（M5-c）：非空则让前端报一条 M0_RELEASE（解释器来历 + 版本 + 能力）
        "auto_release": std::env::var("LRT_AUTO_RELEASE").unwrap_or_default(),
        // 挑图建议（LNX-PICK-001）自动通道："<重复>/<清晰>/<曝光>/<眼睛>"。
        // 这一格上一轮漏过一次：前端 M0Env 声明了 auto_pick，而宿主少返回一个键，
        // TS 编译期看不出来（引擎交回来的是无类型 JSON），表现是「引擎算得对而屏幕上
        // 一次都没点火」。键名单的双向守卫在 engine/tests/test_pick.py 里钉着。
        "auto_pick": std::env::var("LRT_AUTO_PICK").unwrap_or_default(),
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
        // 原生文件/目录选择（M9 裁决3）：路径输入框拿人手填不合法路径，错又只落在
        // 窗口另一头的一行灰色小字上——那是事实上的静默失败。
        .plugin(tauri_plugin_dialog::init())
        .manage(state.clone())
        .manage(Launcher(state.clone()))
        .invoke_handler(tauri::generate_handler![
            start_engine, bench_start, pull_frame, peek_frame, frame_acked, frame_presented, bench_stats,
            engine_status, shutdown_engine, m0_env, load_image, set_strength, compare, precompute,
            inpaint, light, deform, lut, grade, enhance, background, export, session, filmstrip, history,
            project, task, exposure, crop, preset, batch, face, pick,
            report, quit
        ])
        .run(tauri::generate_context!())
        .expect("运行 LumaRetouch 失败");
}
