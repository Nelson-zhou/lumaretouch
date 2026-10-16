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

export interface EngineStatus {
  shm: string;
  has_shm: boolean;
  emitted: number;
  delivered: number;
  logs: string[];
}

export interface BenchOptions {
  w: number;
  h: number;
  frames: number;
  intervalMs: number;
  mode: "copy" | "pipeline";
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
}
export const m0Env = () => invoke<M0Env>("m0_env");
export const report = (line: string) => invoke("report", { line });
export const quit = () => invoke("quit");
