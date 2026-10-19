/** 与 Rust 命令的唯一出入口。所有跨语言类型集中在这里，避免各组件各自猜字段。 */
import { invoke } from "@tauri-apps/api/core";

export interface Dist {
  mean: number;
  p50: number;
  p95: number;
  p99: number;
  max: number;
}

export interface Stats {
  n: number;
  emitted: number;
  delivered: number;
  dropped: number;
  drop_pct: number;
  bench_done: boolean;
  measured_fps: number;
  skip_draw: boolean;
  skip_pixels: boolean;
  emit_to_pull: Dist;
  pull_dur: Dist;
  emit_to_ack: Dist;
  pull_to_ack: Dist;
  emit_to_present: Dist;
  present_cover: number;
  js_draw: Dist;
}

/** 引擎导入一张真图后的回报：代理档尺寸与逐项耗时（一次性成本，不计进逐帧预算）。 */
export interface ImageReady {
  src_w: number;
  src_h: number;
  w: number;
  h: number;
  format: string;
  /** 是否真吃到 libjpeg DCT 预缩（不是“调过 draft()”——那个恒为真） */
  draft: boolean;
  draft_size: [number, number] | null;
  open_ms: number;
  decode_ms: number;
  orient_ms: number;
  scale_ms: number;
  total_ms: number;
  bytes_per_frame: number;
  notes: string[];
  device: string;
  strength: number;
  /** 共享内存建档耗时（尺寸变了才重建，多数情况接近 0） */
  shm_ms: number;
  /** 初始化常驻张量：冷进程含 GPU 上下文建立，与图尺寸无关 */
  attach_ms: number;
  first_frame_ms: number;
  import_ms: number;
  /** M5-a 底片条：这一张在列表里的位置、是不是"切回来的"、以及它的完整文档状态。
   *  doc_state 是宿主重摆滑块的唯一出处：切文档时那几条 *_done 快照会被清掉
   *  （它们属于上一条命令而不是这张文档），只有这一份跟着文档走。 */
  session_index: number;
  session_count?: number;
  doc: string;
  switched: boolean;
  layers: SessionEdits;
  doc_state: DocState;
}

/** 一格底片条上"这张调了什么"（引擎按图层数与开关报，不靠前端自己看像素）。 */
export interface SessionEdits {
  repair: number;
  light: number;
  deform: boolean;
  lut: boolean;
  lut_preset: string | null;
  grade: boolean;
  channel: string | null;
}

/** 当前文档的完整编辑状态（引擎是唯一出处）。 */
export interface DocState {
  strength: number;
  params: Record<string, number>;
  channel: string | null;
  light: { exposure: number; radius: number };
  counts: { repair: number; light: number; repair_redo: number; light_redo: number };
  deform: { amounts: Record<string, number>; built: boolean };
  lut: { lit: boolean; amount: number; preset: string | null };
  grade: { dh: number; ds: number; dv: number; amount: number; lit: boolean };
  /** 曝光/白平衡（P0 lnx.exposure / lnx.white_balance）。`reference_k` 为 null 是
   *  “没指定参考光源”，不是 0：“中性=null 不能解成零”写在注册表的 null_semantics 里。 */
  exposure: { ev: number; temperature_shift: number; tint_shift: number;
              reference_k: number | null; lit: boolean };
  /** 裁剪/旋转（P0 lnx.crop.v1）。rect 是归一化 [左,上,右,下]；`crop_out` 是代理档上
   *  剪后的尺寸，`out_full` 才是导出会写的真实像素数——两个数都得看得见，否则 UI 会
   *  把“预览里那一小块”讲成“文件的尺寸”。 */
  crop: { rect: number[]; rotation_degrees: number; neutral: boolean; lit: boolean;
          limits?: { min: number; max: number } | null;
          crop_out?: [number, number] | null; out_full?: [number, number] | null };
  /** 这一张文档自己的撤销/重做账（M5-b）。随文档走：切到底片条另一格时拿到的是
   *  那一格的栈深，不是全进程一个数。 */
  history: HistoryReport;
}

/** 历史账（M5-b）：引擎是唯一数步数的人，前端只照它报的摆按钮。 */
export interface HistoryReport {
  can_undo: boolean;
  can_redo: boolean;
  undo_steps: number;
  redo_steps: number;
  history_max: number;
}

/** 最近一条 history_state（M5-b）。doc_state 是撤销之后引擎认定的文档状态——
 *  宿主重摆滑块的唯一出处（同图撤销时 docKey 不变，走不到 image_ready 那条路）。 */
export interface HistoryState extends HistoryReport {
  action: "undo" | "redo" | "state" | "clear";
  doc_state: DocState;
  /** 退无可退时引擎发 noop 而不是 error：快捷键按多了是常态。 */
  noop?: boolean;
  /** 只有真撤销/真重做才带：这一次的历史耗时与出帧耗时。 */
  history_ms?: number;
  render_ms?: number;
}

/** session_state.docs 的一项。缩略图不在这里：像素由 filmstrip 单独取。 */
export interface SessionDoc {
  index: number;
  path: string;
  name: string;
  bytes_on_disk: number;
  w: number | null;
  h: number | null;
  src_w: number | null;
  src_h: number | null;
  loaded: boolean;
  opened: boolean;
  edits: SessionEdits;
  /** 工程层的三个字段随底片条上报（状态徽章与多选批量都要在格子上直接可读）：
   *  标签/标记/回收站都是工程记录，不是对原图动手。 */
  tags: string[];
  label?: string | null;
  trashed: boolean;
  /** 这一格算过源文件指纹没有（项目保存/打开时才算） */
  hashed?: boolean;
  /** `preview` 为真时这一格画的是**相机内嵌预览**（RAW 那一族），不是引擎渲的那一帧；
   *  `format` 是解码报的格式名（DNG/CR2/JPEG…）。两个都不能缺：缺了就分不出
   *  “jpg 的真图”与“DNG 的相机预览”，而底片条上后者看起来跟前者一模一样。 */
  thumb: { w: number; h: number; bytes: number; quality: number;
           preview?: boolean; format?: string | null } | null;
  thumb_error: string | null;
}

/** 预设面（LNX-P0-PRESET）：清单与“哪些模块能作用”全部由引擎报，前端不扫目录。 */
export interface PresetInfo {
  schema: string;
  id: string;
  name: string;
  kind: string;
  builtin: boolean;
  modules: Record<string, Record<string, unknown>>;
  author?: string;
  note?: string;
}

/** `lnx.batch.v1.module_scope` 那一份契约的运行时报信：transferable=false 的格子
 *  带着“为什么没接通”，UI 直接拿它写禁用理由（不在前端刻第二份理由）。 */
export interface ScopeModule {
  operation_id: string;
  params: string[];
  transferable: boolean;
  single_face: boolean;
  unmodeled?: Record<string, string>;
  reason?: string | null;
}

export interface PresetState {
  list: PresetInfo[];
  errors: { file: string; error: string }[];
  modules: ScopeModule[];
  dir: string;
  schema: string;
  /** “这一张现在等于哪个预设”由引擎判（套完又被手改就不算），前端不记这一份。 */
  last_applied?: { id: string; name: string } | null;
}

/** 批量同步台账（LNX-P0-BATCH / BATCH-004）：撤销要拿引擎报的那个 id。 */
export interface SyncState {
  batches: { batch_id: string; module_scope: string[]; targets: number; undone: boolean }[];
  undoable: string[];
  last: string | null;
  /** 上一笔 commit/undo 的事实：UI 那句“同步了几张、跳过几张为什么”只能读这里。 */
  last_result?: {
    kind: string; batch_id: string;
    applied?: number[]; skipped?: { index: number; path: string; reason: string }[];
    restored?: number[]; conflicts?: { index: number; path: string; reason: string }[];
  } | null;
}

/** 最近一条 session_state（底片条全貌 + 当前文档状态）。 */
export interface SessionState {
  index: number;
  count: number;
  current: string | null;
  thumbs_running: boolean;
  docs: SessionDoc[];
  doc_state: DocState | null;
  /** 预设清单与同步台账：随同一条 session_state 上来，UI 不在前端记第二份。 */
  presets?: PresetState | null;
  sync?: SyncState | null;
  /** select 命中当前那一格时引擎会补发一条 noop=true 的状态：它没开新会话。 */
  noop?: boolean;
}

/** filmstrip 命令的返回：格子元信息 + path→缩略图 base64（JPEG）。 */
export interface Filmstrip {
  session: SessionState | null;
  thumbs: Record<string, string>;
}

/** 导入期一次预计算的回报：M1-3c 拖滑块只消费这里的通道名与常驻设备。 */
export interface Precompute {
  backend: string;
  num_landmarks: number;
  landmark_shape: number[];
  mask_channels: string[];
  mask_shape: number[];
  mask_bytes: number;
  detect_ms: number;
  masks_ms: number;
  build_ms: number;
  infer_ms: number;
  attach_ms: number;
  total_ms: number;
  resident_device: string;
  landmark_bytes: number;
  active_channel: string | null;
  proxy: number[];
  face_box: number[] | null;
  /** 几何看上去像不像一张脸（判据只写在引擎的 face.geometry_warning 里） */
  geometry_warning: boolean;
  /** 这一轮探到了几张脸（SCOPE-001）。面部重塑只在“恰好 1 张”时可用：
   *  引擎不拿其中某一张冒充“那张脸”，前端也不拿“有一个关键点集”当可用判据。 */
  num_faces: number;
  /** 超范围时引擎给的理由名（目前只有 "multi_face"）；前端不自己编第二个名字 */
  scope_block: string | null;
  /** 检测器上限探几张（不是“画上一共几张”：探到这一数就停） */
  max_faces_probed: number;
  notes: string[];
  /** 只有因换设备而重挂时才有：区分“真算了一次”与“只是重挂旧产物” */
  replayed_for?: string;
}

/** 一次消除笔事件的回报（引擎侧 inpaint_done）。事件驱动：只在松手时算一次。 */
export interface InpaintInfo {
  action: "add" | "undo" | "redo" | "clear";
  ops: number;
  applied: number;
  redo_pending: number;
  painted_px: number;
  boxes: number[][];
  repair_ms: number;
  filter_ms: number;
  render_ms: number;
  total_ms: number;
  bytes_base: number;
  /** 这一帧是否命中了滤波缓存（由执行路径给出，不是声明） */
  filter_cached: boolean;
  /** 本层是否真的重算了。与 filter_cached 不是一回事：两个名字共一个键时，
   *  引擎侧字典后写的会静默吃掉先写的，其中一条永远送不出来 */
  layer_recomputed: boolean;
  op_id?: number;
  decode_ms?: number;
  backend?: string;
  feather?: number;
  rle_runs?: number;
  params?: Record<string, number>;
  device: string;
  strength: number;
}

/** 一次修容笔事件的回报（引擎侧 light_done，M2-a2）。与消除笔同为事件驱动。 */
export interface LightInfo {
  action: "add" | "undo" | "redo" | "clear" | "params";
  ops: number;
  redo_pending: number;
  painted_px: number;
  /** 累加后的带符号场绝对峰值（≤1：档数上限钉在 exposure 上，不随笔数漂） */
  field_peak: number;
  /** 这层现在到底有没有生效（空场或 exposure=0 时为 false） */
  lit: boolean;
  exposure: number;
  radius: number;
  /** 建层成本（一次性）：重算场 + 上显存。与每帧的 light_ms 不是一个量 */
  light_build_ms: number;
  /** 本帧实际跑 db 的毫秒：拖磨皮滑块时应当为 0 */
  light_ms: number;
  filter_ms: number;
  bands_ms: number;
  render_ms: number;
  total_ms: number;
  bytes_light: number;
  /** 这一帧的磨皮滤波是否命中缓存（与下面两条分开：三个数说的是三件事） */
  filter_cached: boolean;
  /** 本条事件是否真的重算了修容场：改参数（params）不重算 */
  layer_recomputed: boolean;
  op_id?: number;
  sign?: number;
  decode_ms?: number;
  feather?: number;
  rle_runs?: number;
  params?: Record<string, number>;
  device: string;
  strength: number;
}

/** 一次形变事件的回报（引擎侧 deform_done，M2-b）。三个滑块一条。 */
export interface DeformInfo {
  /** set/clear 是用户发的；rebuild 是关键点更新后引擎重解单位场；
   *  invalidate 是层被整条清除（后端换成不能按脸形取点的 synthetic）——那一条
   *  必须把滑块归零，否则界面上写着 0.6 而画面一动不动 */
  action: "set" | "clear" | "rebuild" | "invalidate";
  /** 三种形变当前的滑块值，[-1,1]。0 就是不动。 */
  amounts: Record<string, number>;
  /** 单位场建过没有（第一次非零 set 时建） */
  built: boolean;
  /** 这层现在到底有没有生效：全零滑块就是 false */
  lit: boolean;
  /** 本帧形变段（组装 + grid_sample）的毫秒。拖滑块期间它就是这层的全部代价 */
  deform_ms: number;
  /** 三个单位场 + 恒等网格的常驻字节 */
  bytes_deform: number;
  render_ms: number;
  total_ms: number;
  /** 关键点出自哪个后端。template 是模板拟合、贴合度不验收，UI 得能显示这一句 */
  landmark_backend: string | null;
  /** 三种形变里最宽的一种会动到画幅的比例（0–1）。“瘦脸不许拖走背景”这句产品
   *  承诺在当前这张图上成不成立，只有这个数说得清：窗口参数只给圆心与半径，
   *  关键点落错地方时同一个公式会盖住整幅（真人照片上量到 0.99）。 */
  support_share: number;
  /** 引擎认为这套关键点不像一张脸（肤色包围盒贴到整幅边界）。判据在引擎里，
   *  前端不去 parse landmark_notes 的中文——改一个字界面就静悄悄不再警告。 */
  geometry_warning: boolean;
  /** 后端对这份几何的意见（模板拟合的自述 + 不像脸时的说明） */
  landmark_notes: string[];
  /** 只有真正建层的那一条才有：一次性解算成本与 kinds 明细 */
  build?: {
    deform_build_ms: number;
    deform_builds: number;
    bytes_deform: number;
    device: string;
    kinds: Record<string, { peak_px: number; merged: number; controls: number;
                            support_px: number; support_share: number }>;
  };
  /** invalidate 那一条说清为什么清（后端换了 / 重建失败），UI 要能直接给用户看 */
  reason?: string;
  /** invalidate 那一条带上刚才的滑块值：只报 lit=false 的话，滑块弹回零像出了 bug */
  dropped_amounts?: Record<string, number>;
  device: string;
  strength: number;
}

/** 一次调色事件的回报（引擎侧 lut_done，M3-a2）。set/amount/clear 三条臂键集完全相同：
 * 引擎侧只有一个组装点，前端也可以直接按必存字段读。 */
export interface LutInfo {
  action: "set" | "amount" | "clear";
  /** 有没有挂上一张表。恒等表也是 true：“载入了一张表”与“生效了”是两件事 */
  lut_set: boolean;
  /** 这层现在到底有没有生效：恒等表或强度 0 就是 false */
  lut_lit: boolean;
  lut_kind: string | null;
  lut_size: number;
  lut_title: string;
  /** 这张表从哪来（文件名 / "text" / "preset:xxx"）。两张同名表时它是唯一的区分 */
  lut_source: string;
  /** 表是恒等的（且域为 0–1）：短路回去，一个字节也不改 */
  lut_neutral: boolean;
  /** 超出 [0,1] 被夹到端点的表值个数（静默吞掉一个参数比拒绝难查十倍） */
  lut_clipped: number;
  /** 库层对这张表的意见（粗表精度不足等），协议层不许把它吞掉 */
  lut_notes: string[];
  lut_domain_min: number[];
  lut_domain_max: number[];
  /** 混合系数 [0,1]：0 就是逐字节回到未调色那一帧 */
  lut_amount: number;
  /** 本帧跑 3D 查表的毫秒（产品档实测 0.35 ms） */
  lut_ms: number;
  /** 一次性上显存的成本：只有 set 那一条不为 0 */
  lut_mount_ms: number;
  /** 体积 + CPU 原件的常驻字节（只报一份就是藏账） */
  bytes_lut: number;
  lut_grid_bytes: number;
  filter_ms: number;
  bands_ms: number;
  /** 补的那一帧仍命中磨皮缓存：调色在链尾，它不该作废任何上游缓存 */
  filter_cached: boolean;
  deform_ms: number;
  render_ms: number;
  total_ms: number;
  /** 本条事件是否真的重挂了体积（只有 set 是 true） */
  layer_recomputed: boolean;
  device: string;
  strength: number;
  /** 本帧跑肤色定向的毫秒（M3-b：预设一条命令动两层，lut_done 必须能把两层都说出） */
  grade_ms: number;
  /** 定向层现状：与 grade_done 同一出处（都取自引擎里的常驻层），不是第二口径 */
  grade_state: GradeState;
  /** 当前生效的内置预设名；走 path/text 载表或手动改肤色时为 null */
  lut_preset: string | null;
  /** 这一条 clear 有没有连带把预设写进肤色定向的那一份一起拿掉。
   *  预设是两层（表 + 定向），`lut set preset=…` 自己写着“要么两层都上，要么
   *  都不上”，clear 不跟着对称就是半个撤销。 */
  preset_grade_cleared: boolean;
}

/** 肤色定向层（M3-b）的现状。它不持有任何张量：状态就是三个增量加一个混入比例。 */
export interface GradeState {
  /** 色相移动（占整圈的比例，正=往黄） */
  dh: number;
  /** 饱和相对量（-0.14 = 降 14%） */
  ds: number;
  /** 明度相对量 */
  dv: number;
  /** 混入比例 [0,1] */
  amount: number;
  /** 这层现在真的在服务：有参数且 amount≠0 */
  lit: boolean;
  /** 本层不占显存：报 0 而不缺键，“查过”才是这句话的内容 */
  bytes_grade: number;
}

/** 一次肤色定向事件的回报（引擎侧 grade_done，M3-b）。
 * set/amount/clear 三条臂键集完全相同：引擎侧只有一个组装点。
 *
 * 它**不继承** GradeState：grade_done 是铺平的一份（grade_dh / grade_amount /
 * grade_lit / grade_set），嵌套那份 grade_state 才是 dh / amount / lit。两套名字
 * 混进一个接口，TypeScript 一律当作必存——谎报发生在 JSON 边界上，编译期抓不到，
 * 现场是渲染时一句 TypeError 把整棵 React 树拆掉（画面就此冻结在 0 帧）。
 * M5-b 的真窗口轮第一次撞上：那时宿主才开始发 hello，grade_limits 不再为空，
 * 定向那一排第一次真的被渲染出来。 */
export interface GradeInfo {
  action: "set" | "amount" | "clear";
  /** 铺平的同一份数：payload 与嵌套字段都来自 _grade_payload */
  grade_dh: number;
  grade_ds: number;
  grade_dv: number;
  grade_amount: number;
  grade_lit: boolean;
  /** 有没有非零参数（全零就是关灯，层里没留下任何颜色改动） */
  grade_set: boolean;
  /** 本层不占显存时也报 0 而不缺键："查过"才是这句话的内容 */
  bytes_grade: number;
  grade_ms: number;
  /** [dh, ds, dv] 的硬边界：滑块的夹取范围由引擎说，前端不抄一份数然后两处漂 */
  grade_limits: number[];
  lut_ms: number;
  lut_preset: string | null;
  filter_ms: number;
  bands_ms: number;
  filter_cached: boolean;
  deform_ms: number;
  render_ms: number;
  total_ms: number;
  layer_recomputed: boolean;
  device: string;
  strength: number;
}

/** 一次换底事件的回报（引擎侧 bg_done，M6）。事件驱动：一次“换底”一条。
 *  clear 臂不带 backend/bg/matte_fill_fg（那些只在 set 时有意义）——按 M5-b 那一课，
 *  引擎不发、这里就不许声明成必存。 */
export interface BackgroundInfo {
  action: "set" | "clear";
  bg_active: boolean;
  /** 遮罩 + 背景的常驻字节：没活时报 0 而不缺键 */
  bytes_bg: number;
  device: string;
  bg_ms: number;
  render_ms: number;
  total_ms: number;
  backend?: string;
  bg?: number[];
  /** 前景占比（alpha>127 的像素比例）：0–1 */
  matte_fill_fg?: number;
}

/** 引擎进程的运行时账单：ready 里的 runtime 与宿主选解释器的那几条合起来一份。
 *  键全部可选：新壳配旧引擎时 ready 里根本没有这一项（宿主也不会凭空造一个）。 */
export interface EngineRuntime {
  python?: string;
  /** env（$LRT_ENGINE_PY）/ explicit（面板里填了）/ runtime（候选表命中）/ fallback（python3）。 */
  python_source?: string;
  python_version?: string;
  engine_src?: string;
  hint?: string;
  /** 引擎 ready 报回来的包账单，单独一层（M5-c）。不铺平进这一层：宿主与引擎两边
   *  都有 `python` 这个键，铺平就是同名互相顶——装机校验读到过 "3.12.15" 当路径。 */
  packages?: {
    python?: string | null;
    engine_version?: string | null;
    numpy?: string | null;
    pillow?: string | null;
    torch?: string | null;
    torchvision?: string | null;
  };
}

export interface EngineStatus {
  /** 引擎运行时的来历与包账单（M5-c 开箱即用）。整块都取可选：ready 里没报就是
   *  这一版引擎不说自己是谁，UI 该什么都不显示——把可选字段声明成必存，谎报发生在
   *  JSON 边界上，编译期抓不到，运行期一个 TypeError 把整棵树拆掉（M5-b 那一课）。 */
  engine_alive?: boolean;
  engine_version?: string | null;
  engine_runtime?: EngineRuntime | null;
  shm: string;
  has_shm: boolean;
  emitted: number;
  delivered: number;
  logs: string[];
  /** 最近一次 image_ready；没导过图为 null。 */
  image: ImageReady | null;
  /** 最近一次 precompute_ready；换图/换引擎进程会清空。 */
  precompute: Precompute | null;
  /** 最近一次 inpaint_done；换图/换设备会清空（图层跟着会话走）。 */
  inpaint: InpaintInfo | null;
  /** 最近一次 light_done；与 inpaint 同生命期，但两份结果各自一份，不串台。 */
  light: LightInfo | null;
  /** 最近一次 deform_done（M2-b）；换图/换引擎进程会清空（关键点不在，层也不在）。 */
  deform: DeformInfo | null;
  /** 最近一次 lut_done（M3-a2）；换图会清空（调色层随文档走，不随引擎进程走）。 */
  lut: LutInfo | null;
  /** 最近一次 grade_done（M3-b）；与 lut 同生命期：肤色定向也随文档走。 */
  grade: GradeInfo | null;
  /** 最近一次 bg_done（M6 换底）；换图/换设备会清空（遮罩随代理档与设备走）。 */
  background: BackgroundInfo | null;
  /** 引擎在 ready 里报出的内置预设清单（M3-b）。空数组 = 这个引擎还没这一能力，
   *  UI 就不画按钮，而不是前端自己抄一份名字去撞一个不存在的资产。 */
  presets: PresetInfo[];
  /** [dh, ds, dv] 的硬边界（ready 里报的）：滑块行程的唯一出处。空数组 = 这个引擎
   *  还没这一能力，定向那一排就不画。 */
  grade_limits: number[];
  /** 最近一次 export_done（M4 批量出片）；换图/换引擎进程会清空。 */
  export: ExportDone | null;
  /** 最近一条 export_progress：第几张 / 共几张。null = 没在跑（或刚跑完）。 */
  export_progress: ExportProgress | null;
  /** 引擎在 ready 里报的导出能力。null = 这个引擎还不能导出，按钮就不画。 */
  export_caps: ExportCaps | null;
  /** 引擎在 ready 里自报的 RAW 解码能力（raw.py 的 raw_backends）。null = 这一版引擎
   *  还没报过这份清单。能读什么由引擎说，前端不刻一份——把没落地的 CR2 支持写进 UI 就是一条假指标。 */
  raw_backends: RawBackends | null;
  /** 引擎 scan 那份白名单（ready 里报的 image_exts）：原生选择框的过滤器用它。
   *  null = 这一版引擎没说，选择框就退化成“什么都不过滤”，不拿宿主抄的名单去挡人。 */
  image_exts: string[] | null;
  /** 导出位深能力（M9-e，引擎单一口径）：每个位深对应哪些落盘格式。
   *  引擎没报（老引擎）就不画 16-bit 那个勾，而不是默认"应该能写"。 */
  export_bits?: { "8"?: string[]; "16"?: string[] } | null;
  /** 引擎最近一条 error（M9）：load_image 发出去就返回，失败只走 error 事件。
   *  不接住它，坏路径就是一次彻底的静默失败。 */
  last_error: string | null;
  /** 引擎在 ready 里自报的抠图后端清单（birefnet.py 的 matting_backends）。null =
   *  这一版引擎还没报过。换底下拉项由这一份决定：权重未放行时 birefnet 在
   *  weights_gated 里，摆一个注定被拒的选项就是邀请用户去撞一个空请求。 */
  matting_backends: MattingBackends | null;
  /** 最近一条 session_state（M5-a 底片条）；换引擎进程会清空。 */
  session: SessionState | null;
  /** session_state / 缩略图每来一条就 +1：前端只在它变了的时候整条重取底片条。 */
  session_rev: number;
  /** 宿主已收到多少张缩略图（按 path 计）。 */
  thumbs_ready: number;
  /** 最近一条 history_state（M5-b）；换引擎进程会清空。 */
  history: HistoryState | null;
  /** history_state 每来一条 +1：宿主只在它变了的时候按引擎那份 doc_state 重摆滑块。 */
  history_rev: number;
  /** 发过编辑命令、还没听到引擎的历史答复：撤销按钮在这段窗口里保持可用。 */
  history_dirty: boolean;
  /** 最近一条带 doc_state 的事件（image_ready / session_state / history_state 之一）。
   *  历史账只从这三条里来，而谁最后到只有宿主按到达次序数得出来。 */
  doc_report: { source: string; doc_state: DocState } | null;
  /** doc_report 每换一次 +1：前端只在它变了的时候取新的栈深。 */
  doc_rev: number;
  /** ready 报的"哪些命令算编辑"。空数组 = 这个引擎还没有历史能力。 */
  history_edit_cmds: string[];
  /** ready 的整份能力清单（宿主不逐字段拄）：面板上的动作名单、工程后缀、导出格式
   *  这些“引擎说什么能力”的清单都从这一份读。老宿主没报时为 undefined——那时那一排
   *  控件按“引擎没说”处理（不画/禁用），而不是前端自己猜一份。 */
  ready_caps?: {
    project_actions?: string[];
    project_suffix?: string;
    task_actions?: string[];
    export_formats?: string[];
    [k: string]: unknown;
  } | null;
  /** 最近一条项目播报（created/opened/saved/edited/state）。整块可选：老引擎不报
   *  就什么都不显示，而不是前端自己记一份"存过了"。 */
  project?: ProjectState | null;
  project_rev?: number;
  /** 批量任务台账（按 task_id 聚合的最新一条）。可用性只从这份读：
   *  转移表在引擎里，前端不自己判"这条能不能暂停"。 */
  tasks?: TaskState[];
  task_rev?: number;
}

/** 工程面（LNX-P0-PROJECT）：名字、脏标记、格数与"这一版没存进去的东西"。 */
export interface ProjectState {
  event?: string;
  open?: boolean;
  path?: string | null;
  name?: string | null;
  project_id?: string | null;
  docs?: number;
  dirty?: boolean;
  saved_ns?: number | null;
  /** 台账格数（不是清单）：清单在 project_saved 的 `dropped` 里，两件事不共用一个名字 */
  tasks?: number;
  dropped_count?: number;
  bytes?: number;
  sha256?: string;
  write_ms?: number;
  hash_ms?: number;
  fingerprinted?: number;
  /** project_saved 才有：没存进工程文件的层与原因（逐条，上限 12） */
  dropped?: { path?: string; at: string; reason: string }[];
  /** project_opened 才有：读回来时逐条说了什么 */
  task_restore?: { task_id: string; state: string; blocked: string }[];
  missing?: { path: string; exists: boolean }[];
  missing_count?: number;
  auto_opened?: string | null;
  proxy_budget?: number | null;
}

/** 任务台账的一格（引擎 task_state 的宿主搬运，状态机在 tasks.py）。 */
export interface TaskState {
  task_id: string;
  kind: string;
  state: "queued" | "running" | "pause_requested" | "paused" | "resuming"
    | "cancelling" | "cancelled" | "retrying" | "succeeded" | "failed" | string;
  attempt: number;
  counts: { total: number; succeeded: number; failed: number; skipped: number; pending: number };
  batch: { running: number; state: string; counts: Record<string, number> };
  persisted: boolean;
  blocked_reason: string | null;
  out_dir: string | null;
  updated_ns: number;
  note?: string;
}

/** 一次导出的逐图账单（export_done.images[] 的一项，M4）。
 *
 * 失败项只有 path/stage/error：一张坏路径只塌自己那一张，不带倒整批。
 * skipped 是逐图报的：不是当前文档的那些图不会带上笔迹/形变/通道，这句话
 * 必须逐张说清，不能默默少几层。
 */
export interface ExportedImage {
  path: string;
  /** 16-bit 母档直通（M9-e）的三个保真读数。缺任何一条都不能算"无损"：
   *  差值必须 0、每通道档位必须远多于 256、低 8 位不许全是零。 */
  bits?: number;
  source?: string | null;
  readback_max_diff?: number;
  levels_per_channel?: number[];
  low8_nonzero_px?: number;
  out?: string;
  format?: string;
  bytes?: number;
  write_ms?: number;
  w?: number;
  h?: number;
  px?: number;
  src_mb?: number;
  /** 放大（M7）：源幅与倍率。只报 `w/h` 分不出"2× 真做了"与"导出了原图"。 */
  src_w?: number;
  src_h?: number;
  scale?: number;
  upscale_backend?: string | null;
  upscale_ms?: number;
  sharpen_ms?: number;
  sharpen_amount?: number;
  tile?: number;
  tiles?: number;
  margin_px?: number;
  deform_peak_px?: number;
  total_ms?: number;
  field_ms?: number;
  per_tile_ms?: number;
  seg_ms?: Record<string, number>;
  delta_cpu_mb?: number;
  channel?: string | null;
  repair_ms?: number;
  applied?: number;
  skipped?: string[];
  stage?: string;
  error?: string;
}

/** 一批导出的终态（引擎侧 export_done，M4）。 */
export interface ExportDone {
  total: number;
  failed: number;
  out_dir: string;
  format: string;
  quality: number;
  tile: number;
  /** 这一批用的倍率/后端/锐量（引擎拍一次报一次，不是前端自己记得） */
  scale?: number;
  upscale_backend?: string | null;
  sharpen?: number;
  /** 这一批的位深（引擎报，不是前端自己记得）：16 意味着走的是直通那条不进图层的链 */
  bit_depth?: number;
  total_ms: number;
  images: ExportedImage[];
}

/** 逐图进度（引擎侧 export_progress，M4）。index 从 0 起。 */
export interface ExportProgress {
  index: number;
  total: number;
  path: string;
  ok: boolean;
}

/** 导出能力（ready 报的）：格式名单与 tile 行程由引擎说，前端不抄一份。 */
export interface ExportCaps {
  formats: string[];
  tile: [number, number];
  tile_default: number | null;
  /** 允许的放大倍率（M7）。缺 = 这一版引擎不说倍率，放大那一排就不画。 */
  scales?: number[] | null;
  /** 放大能力清单（upscale.py 的 scale_backends）：哪一档装机即用、哪一档等权重。 */
  upscale_backends?: UpscaleBackends | null;
}

/** 放大后端清单：baseline 与 weights_gated 是两种不同强度的主张，不许混报。 */
export interface UpscaleBackends {
  baseline: string[];
  weights_gated: string[];
}

/** 抠图后端清单（M6）：与放大那一档同一个口径、同一种形状，故复用同一份定义——
 *  两处各自刻一遍就会漂（EXPORT_KEYS 那一课已经付过一次钱）。 */
export type MattingBackends = UpscaleBackends;

/** raw.py 的 raw_backends 形状：基线能读什么、哪些需插件、插件装没装。 */
export interface RawBackends {
  baseline: string[];
  suffixes: string[];
  needs_plugin: string[];
  plugin: string;
  plugin_installed: boolean;
  /** M9-h 定稿口径：已全链路自验的后缀，与依赖系统 LibRaw 但没有实机样张的那一栏。
   *  老引擎没报就是 undefined——那时前端只报 suffixes 那一行，不替引擎编一句"已认证"。 */
  suffixes_verified?: string[];
  verified_full_chain?: string[];
  vendor_suffixes?: string[];
  vendor_status?: string;
  sample_certified?: { [k: string]: boolean };
}

/** 一个内置预设的可显示信：提交只靠 name，文字只靠 title。 */
export interface PresetInfo {
  name: string;
  title: string;
}

export interface BenchOptions {
  w: number;
  h: number;
  frames: number;
  intervalMs: number;
  /** pipeline = pipeline_copyin 的历史别名，引擎侧两者同义。image_stream 需先 load_image。 */
  mode: "copy" | "pipeline" | "pipeline_copyin" | "pipeline_resident" | "image_stream";
}

export const startEngine = (py: string, src: string) =>
  invoke<{ pid: number; python: string; src: string; session: string }>("start_engine", { py, src });

export const benchStart = (o: BenchOptions) =>
  invoke("bench_start", {
    w: o.w,
    h: o.h,
    frames: o.frames,
    intervalMs: o.intervalMs,
    mode: o.mode,
  });

/** 取最新帧：40B 头 + RGBA 裸像素。无新帧时以 "NO_NEW_FRAME" 拒绝。 */
export const pullFrame = () => invoke<ArrayBuffer>("pull_frame");

/** 只读快照：拿"此刻屏幕上是什么"，与投递计数无关（见 main.rs 的 peek_frame）。
 *  自动通道量像素用这条，不能用 pullFrame——那条会因"这帧已经投过了"拒发，
 *  而渲染循环本来就在逐帧拉取，测试路径永远抢不到。 */
export const peekFrame = () => invoke<ArrayBuffer>("peek_frame");

export const frameAcked = (seq: number, jsDrawUs: number) =>
  // 不能传 BigInt：invoke 的负载走 JSON 序列化，BigInt 会直接抛 TypeError
  invoke("frame_acked", { seq, jsDrawUs });

/** 告知宿主：该帧之后又跑了两个 rAF，已被合成器拿去画过一整屏。 */
export const framePresented = (seq: number) => invoke("frame_presented", { seq });

export const benchStats = () => invoke<Stats>("bench_stats");
export const engineStatus = () => invoke<EngineStatus>("engine_status");
export const shutdownEngine = () => invoke("shutdown_engine");

/** 导入真图。异步语义：引擎要几百毫秒到几秒，靠 engineStatus().image 轮询就绪。
 * precompute 给“auto/mediapipe/synthetic”就是导完图算一次，给空则只解码不算。 */
export const loadImage = (
  path: string,
  opts?: { maxPx?: number; strength?: number; precompute?: string; channel?: string },
) =>
  invoke<{ requested: boolean }>("load_image", {
    path,
    maxPx: opts?.maxPx,
    strength: opts?.strength,
    precompute: opts?.precompute,
    channel: opts?.channel,
  });

/**
 * 滑块动一下：引擎只重算系数。channel 指到常驻掩膜通道也不产生任何推理或上传。
 * radius/eps/textureRadius 变的是**分带**（实测产品档 5 ms），detailGain/midGain/broadGain
 * 变的只是**重组**（~0.5 ms），strength 两者都不动（~0.1 ms）。
 * 两层都是“松手才提交”：逐事件发会把 M1-3c 拿回来的 vsync 余量又吐出去。
 */
/** 按住看原图：on=true 临时出一帧原图，on=false 回到修好的那一版。不改会话强度。 */
export const setCompare = (on: boolean) => invoke<{ on: number }>("compare", { on });

export const setStrength = (
  value: number,
  opts?: { channel?: string; radius?: number; eps?: number; detailGain?: number;
           midGain?: number; broadGain?: number; textureRadius?: number },
) =>
  invoke<{ value: number }>("set_strength", {
    value,
    channel: opts?.channel,
    radius: opts?.radius,
    eps: opts?.eps,
    detailGain: opts?.detailGain,
    midGain: opts?.midGain,
    broadGain: opts?.broadGain,
    textureRadius: opts?.textureRadius,
  });

/** 对当前已导入的图跑一次导入期预计算；结果靠 engineStatus().precompute 轮询。 */
export const runPrecompute = (opts?: { backend?: string; channel?: string; modelDir?: string }) =>
  invoke<{ requested: boolean }>("precompute", {
    backend: opts?.backend,
    channel: opts?.channel,
    modelDir: opts?.modelDir,
  });

/**
 * 消除笔：action=add 带行程编码；undo/redo/clear 不带画。异步语义同 loadImage：
 * 结果靠 engineStatus().inpaint 轮询。不把它做成同步调用——一次修补要几十毫秒，
 * 而“松手就能看见结果”靠的是不等回答、下一帧自然上屏。
 */
export const runInpaint = (
  action: InpaintInfo["action"],
  opts?: { rle?: number[][]; feather?: number; backend?: string; refineIters?: number },
) =>
  invoke<{ requested: boolean }>("inpaint", {
    action,
    rle: opts?.rle,
    feather: opts?.feather,
    backend: opts?.backend,
    refineIters: opts?.refineIters,
  });

/** 修容笔（M2-a2）：与消除笔同一套事件调度，一次松手一条。
 *
 * sign 是方向而不是强度：+1 减淡、-1 加深，强度由这层的 exposure（档数）给出。
 * 这样“多画几笔”只是让场更接近上限，不会像逐笔乘那样把脸烧穿。
 */
export const runLight = (
  action: LightInfo["action"],
  opts?: { rle?: number[][]; feather?: number; sign?: number; exposure?: number; radius?: number },
) =>
  invoke<{ requested: boolean }>("light", {
    action,
    rle: opts?.rle,
    feather: opts?.feather,
    sign: opts?.sign,
    exposure: opts?.exposure,
    radius: opts?.radius,
  });

/** 五官微调（M2-b）：送三个滑块的值。
 *
 * 与修容笔不同，这条在拖动期间也要发：引擎侧只把已常驻的单位场按新系数缩放，
 * 一次 TPS 也不重解（拖 600 帧 deform_builds 不增，见 m2-face-bench）。
 * 不发就等于“滑块拖了、画面不动”。
 */
export const runDeform = (action: DeformInfo["action"], amounts?: Record<string, number>) =>
  invoke<{ requested: boolean }>("deform", { action, amounts });

/** 影楼色彩（M3-a2）：送一张 .cube，或只改混合系数。
 *
 * path 与 text 二选一（同时给会被引擎整条拒：拿到哪张都是“对的那张的错版本”）。
 * 强度滑块松手才发：它不重挂体积，但每条命令都要引擎重画一帧，逐事件发会吞掉
 * vsync 余量（与修容强度同一条理由）。而形变那一条相反：它必须拖动期间逐事件发。
 */
export const runLut = (
  action: LutInfo["action"],
  opts?: { path?: string; text?: string; preset?: string; amount?: number },
) =>
  invoke<{ requested: boolean }>("lut", {
    action,
    path: opts?.path,
    text: opts?.text,
    preset: opts?.preset,
    amount: opts?.amount,
  });

/** 肤色定向（M3-b）：三个增量 + 一个混入比例。
 *
 * set 是部分提交：没给的增量沿用当前值（拖一个滑块不该把另外两个抹零）。
 * 拖动期间逐事件发：这一层每帧真跑内核（产品档实测 1.3 ms/帧），不发就是
 * “滑块拖了、画面不动”。越界值整条拒，拒完状态干净，UI 不必先夹再发。
 */
export const runGrade = (
  action: GradeInfo["action"],
  opts?: { dh?: number; ds?: number; dv?: number; amount?: number },
) =>
  invoke<{ requested: boolean }>("grade", {
    action,
    dh: opts?.dh,
    ds: opts?.ds,
    dv: opts?.dv,
    amount: opts?.amount,
  });

/** 换底（M6）：一次“换底”一条命令。action=set 需 bg（[r,g,b] 0–255）；clear 关掉整层。
 *  backend 默认 color_key（确定性色键）；birefnet 需权重，无权重引擎会诚实拒。返回只是
 *  “请求递出去了”，真正的合成结果从 engine_status().background 轮询（与 inpaint/light 同路）。 */
export const runBackground = (
  action: BackgroundInfo["action"],
  opts?: { backend?: string; bg?: number[]; tol?: number; softness?: number },
) =>
  invoke<{ requested: boolean }>("background", {
    action,
    backend: opts?.backend,
    bg: opts?.bg,
    tol: opts?.tol,
    softness: opts?.softness,
  });

/** 全尺寸分块导出（M4）。不传 images 就是导当前这张。
 *
 * 这里的返回只是“请求递出去了”：满幅一块图就能是几秒，真正的结果从
 * export_progress / export_done 两条事件拿（engine_status 轮询）。
 * format/tile 不抄默认值：那两个数的出处是引擎的 ready（export_formats /
 * export_tile），宿主填一份就会在引擎改口径时静默漂开。
 *
 * scale/sharpen 同理（M7）：不给就是不上这一层。后端只能从 ready 报的 baseline 里选，
 * 拿 weights_gated 那一个去提交会被引擎整条拒（这是设计，不是降级）。
 */
export const runExport = (
  outDir: string,
  opts?: { format?: string; quality?: number; tile?: number; images?: string[];
           scale?: number; sharpen?: number; upscaleBackend?: string;
           bitDepth?: number; outputProfile?: string; tiffCompression?: string;
           metadataIncludeGps?: boolean; conflictPolicy?: string },
) =>
  invoke<{ requested: boolean }>("export", {
    outDir,
    format: opts?.format,
    quality: opts?.quality,
    tile: opts?.tile,
    images: opts?.images,
    scale: opts?.scale,
    sharpen: opts?.sharpen,
    upscaleBackend: opts?.upscaleBackend,
    bit_depth: opts?.bitDepth,
    // 导出侧 P0 的四格：中性位由引擎定（ADR-0003），这里只在用户显式改过才传
    output_profile: opts?.outputProfile,
    tiff_compression: opts?.tiffCompression,
    metadata_include_gps: opts?.metadataIncludeGps,
    conflict_policy: opts?.conflictPolicy,
  });

/** 帧头解析（小端，与 main.rs 的 pull_frame 注释逐字段对应）。 */
export interface ParsedFrame {
  seq: number;
  tEmitNs: number;
  tPullNs: number;
  w: number;
  h: number;
  /** 0 = 宿主对照组（LRT_SKIP_PIXELS），像素根本没跨进程 */
  pixelLen: number;
  /** 脏矩形起始行（占用头部的保留位） */
  y0: number;
  /** 本次送来的行数：整帧时等于 h，脏矩形时小于 h */
  rows: number;
  pixels: Uint8Array;
  /** upload=bitmap 策略下泵里解好的原生位图；用完必须 close() */
  bitmap?: ImageBitmap;
}

export function parseFrameHead(buf: ArrayBuffer): ParsedFrame {
  const dv = new DataView(buf);
  const w = dv.getUint32(24, true);
  const h = dv.getUint32(28, true);
  const pixelLen = dv.getUint32(32, true);
  return {
    seq: Number(dv.getBigUint64(0, true)),
    tEmitNs: Number(dv.getBigUint64(8, true)),
    tPullNs: Number(dv.getBigUint64(16, true)),
    w,
    h,
    pixelLen,
    y0: dv.getUint32(36, true),
    // 行数从字节数反推：宿主只送顶部几行时，上传尺寸得按实际拿到的算
    rows: pixelLen > 0 && w > 0 ? pixelLen / (w * 4) : 0,
    pixels: new Uint8Array(buf, 40),
  };
}

export const isNoFrame = (e: unknown) => {
  const s = String(e);
  return s.includes("NO_NEW_FRAME") || s.includes("NO_FRAME_YET") || s.includes("SHM_NOT_READY");
};

/** M0 自动化跑靶：由环境变量驱动，结果打到宿主 stdout，便于脚本采集。 */
export interface M0Env {
  auto_bench: string;
  engine_py: string;
  engine_src: string;
  device: string;
  skip_draw: string;
  skip_pixels: string;
  upload: string;
  /** 单次上传的横向分块数（验 4 MiB 命令缓冲假设） */
  chunks: number;
  no_ctx: string;
  no_mirror: string;
  gl_visible: string;
  /** 视口自证探针（M9）：非空时在静置后读回画布缓冲并量布局矩形，报 M0_VIEWPORT。 */
  viewport_probe: string;
  dirty_frac: number;
  /** 非空则跑靶前先导入这张图（M1-3a 真图通路）。 */
  load_image: string;
  max_px: number | null;
  /** 非空且不为 "0" 则导入后跑一次预计算，值就是后端名（M1-3b）。 */
  precompute: string;
  precompute_channel: string;
  /** 非空则导入后自动打几笔消除笔（M1-4）："fx:fy:r,…"。fx/fy 是代理帧归一化坐标，
   *  r 是**像素**半径（clickRle 直接吃它）——上一版注释只说"坐标归一化"，我按 0.15
   *  传过比例，结果只盖了 25 像素、第三笔 RLE 越界被引擎拒绝，白跑一轮确认。 */
  auto_inpaint: string;
  /** 非空则导入后提交一次三条带增益（M2-a）："mid:broad:detail"。 */
  auto_skin: string;
  /** 非空则导入后画几笔修容（M2-a2）："fx:fy:r:sign,…"，fx/fy 归一化、r 是**像素**、sign 取 1/-1。 */
  auto_light: string;
  /** 非空则导入后提交一次形变（M2-b）："slim:eye:chin"，三个都是 [-1,1] 的滑块值。
   *  需要 LRT_PRECOMPUTE 给出关键点（synthetic 后端会被引擎整条拒）。 */
  auto_deform: string;
  /** 非空则导入后载入一张表（M3-a2）："amount@<路径>"，也支持 "amount@preset:<名>"
   *  （M3-b：预设一条命令同时上表与肤色定向，所以这一条能把两层都验到）。路径里出现 @
   *  不冲突：只按**第一个** @ 切分，因为前半段是个数字。 */
  auto_lut: string;
  /** 非空则导入后提交一次肤色定向（M3-b）："dh:ds:dv:amount"，四个数用 : 分隔。
   *  与 lut 的 @ 分法各走一份，两条自动臂可以同时挂。 */
  auto_grade: string;
  /** M6 换底自动通道（$LRT_AUTO_BG）："rrggbb:tol:softness"。真窗口要证的不是
   *  合成对不对（test_matting 已钉），而是 TS runBackground → Rust background →
   *  引擎 bg_done 这条命令签名在真窗口里对得上，且画面真的变了（peek 字节差）。 */
  auto_background: string;
  /** M4 导出自动通道："<目录>[@<格式>][@<tile>]"。 */
  auto_export: string;
  /** M5-a 底片条自动通道："<目录>[@<切到第几张>[@<长边>]]"。
   *  这一条要证的不是引擎能扫描（那是 test_session 的事），而是
   *  TS runSession → Rust session → 引擎 session_state 这条签名在真窗口里对得上，
   *  以及切走再切回来时 doc_state 与画面是否还是同一份。 */
  auto_filmstrip: string;
  /** M5-b 撤销/重做自动通道：<强度值>。引擎那条链已有协议用例逐字节对拍，这一条要证
   *  的是宿主三层：runHistory → Rust history → history_state 的签名对不对得上，
   *  以及宿主有没有真按引擎那份 doc_state 重摆滑块（applied 里那一份是唯一直接证据）。 */
  auto_history: string;
  /** 发布自检（M5-c 开箱即用）：非空（一般给 1）则报一条 M0_RELEASE，把“引擎跑在
   *  哪个解释器、从哪一档候选里来、版本与包账单、能力到没到”一次打全。这些信息
   *  平时分散在侧栏的四行小字里，脚本读不到而人也不会一行一行去比对。 */
  auto_release: string;
}
export const m0Env = () => invoke<M0Env>("m0_env");

/** 底片条（M5-a）：一条转发六个动作的命令。参数一律"给了才附"，让引擎的默认值
 *  由引擎说（与 runExport 同一条理由）。 */
export const runSession = (
  action: "scan" | "add" | "select" | "state" | "thumbs" | "stop_thumbs",
  opts: { dir?: string; paths?: string[]; index?: number; edge?: number;
          quality?: number; limit?: number; thumbs?: boolean } = {},
) => invoke<{ requested: boolean }>("session", { action, ...opts });

/** 撤销/重做（M5-b）：四个动作一条命令，宿主只做把手。步数上限、手势合并窗口、
 *  哪几层进历史全在引擎里——在这里刻一份就会漂一份。 */
export const runHistory = (action: "undo" | "redo" | "state" | "clear") =>
  invoke<{ requested: boolean }>("history", { action });

/** 整条底片条：格子元信息 + 缩略图。只在 session_rev 变了的时候取。 */
export const fetchFilmstrip = () => invoke<Filmstrip>("filmstrip");

/** 工程（LNX-P0-PROJECT）：六个动作一条命令。原子写、脏标记、资产去重全在引擎。 */
export const runProject = (
  action: "create" | "open" | "save" | "state" | "tag" | "trash",
  opts: { name?: string; directory?: string; path?: string; doc?: string; index?: number;
          tags?: string[]; label?: string; trashed?: boolean; force?: boolean } = {},
) => invoke<{ requested: boolean }>("project", { action, ...opts });

/** 批量任务队列（LNX-P0-TASK）：转移表在引擎里，这里只把 id 递过去。 */
export const runTask = (
  action: "list" | "pause" | "resume" | "cancel" | "retry" | "delete",
  taskId?: string,
) => invoke<{ requested: boolean }>("task", { action, task: taskId });

/** 模块预设（LNX-P0-PRESET / PRESET-001、002）：作用域与合法性全在引擎的 scope.py，
 *  这里既不列模块名单也不写量程（与 exposure/crop 同一条理由：抄一份就漂一份）。 */
export const runPreset = (
  action: "list" | "apply" | "save" | "import" | "delete",
  opts: { id?: string; name?: string; path?: string; kind?: string; note?: string;
          force?: boolean; moduleScope?: string[] } = {},
) => invoke<{ requested: boolean }>("preset", {
  action, id: opts.id, name: opts.name, path: opts.path, kind: opts.kind, note: opts.note,
  force: opts.force, module_scope: opts.moduleScope,
});

/** 批量同步（LNX-P0-BATCH / BATCH-004）：目标按 path 递（多选集就是按 path 记的），
 *  preflight/commit/undo 的判定与原子性全在引擎。 */
export const runBatch = (
  action: "preflight" | "commit" | "undo" | "state",
  opts: { docs?: string[]; moduleScope?: string[]; conflictPolicy?: string;
          batchId?: string } = {},
) => invoke<{ requested: boolean }>("batch", {
  action, docs: opts.docs, module_scope: opts.moduleScope,
  conflict_policy: opts.conflictPolicy, batch_id: opts.batchId,
});

/** 曝光/白平衡（P0）：量程由引擎随事件报 exposure_limits，这里不拄一份。 */
export const runExposure = (
  action: "set" | "clear",
  v: { ev?: number; temperature_shift?: number; tint_shift?: number; reference_k?: number } = {},
) => invoke<{ requested: boolean }>("exposure", { action, ...v });

/** 裁剪/旋转（P0 lnx.crop.v1）：rect 归一化，正角顺时针——口径在引擎 ops/geometry.py。 */
export const runCrop = (
  action: "set" | "clear", rect?: number[], rotationDegrees?: number,
) => invoke<{ requested: boolean }>("crop", {
  action, rect, rotation_degrees: rotationDegrees,
});
export const report = (line: string) => invoke("report", { line });
export const quit = () => invoke("quit");
