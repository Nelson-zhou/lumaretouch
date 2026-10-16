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

/** 滑块动一下：引擎只重算系数。channel 指到常驻掩膜通道也不产生任何推理或上传。 */
export const setStrength = (value: number, channel?: string) =>
  invoke<{ value: number }>("set_strength", { value, channel });

/** 对当前已导入的图跑一次导入期预计算；结果靠 engineStatus().precompute 轮询。 */
export const runPrecompute = (opts?: { backend?: string; channel?: string; modelDir?: string }) =>
  invoke<{ requested: boolean }>("precompute", {
    backend: opts?.backend,
    channel: opts?.channel,
    modelDir: opts?.modelDir,
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
  dirty_frac: number;
  /** 非空则跑靶前先导入这张图（M1-3a 真图通路）。 */
  load_image: string;
  max_px: number | null;
  /** 非空且不为 "0" 则导入后跑一次预计算，值就是后端名（M1-3b）。 */
  precompute: string;
  precompute_channel: string;
}
export const m0Env = () => invoke<M0Env>("m0_env");
export const report = (line: string) => invoke("report", { line });
export const quit = () => invoke("quit");
