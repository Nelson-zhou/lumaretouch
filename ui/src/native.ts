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
  cached: boolean;
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
  cached: boolean;
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
  action: "set" | "clear";
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
  /** 只有真正建层的那一条才有：一次性解算成本与 kinds 明细 */
  build?: {
    deform_build_ms: number;
    deform_builds: number;
    bytes_deform: number;
    device: string;
    kinds: Record<string, { peak_px: number; merged: number; controls: number }>;
  };
  device: string;
  strength: number;
}

export interface EngineStatus {
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
}
export const m0Env = () => invoke<M0Env>("m0_env");
export const report = (line: string) => invoke("report", { line });
export const quit = () => invoke("quit");
