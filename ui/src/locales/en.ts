/** 英文语言包（fallback 用；缺 key 自动回落到中文，不会白屏）。 */
import type { MsgKey } from "./zh";

export const en: Partial<Record<MsgKey, string>> = {
  "app.subtitle": "M0 pipeline skeleton · raw frames over shared memory",
  "side.engine": "Engine",
  "side.bench": "Bench",
  "engine.start": "Start engine",
  "engine.stop": "Stop engine",
  "bench.mode.copy": "Copy only (path ceiling)",
  "bench.mode.pipeline": "With guided-filter pipeline (legacy alias)",
  "bench.mode.pipeline_copyin": "Pipeline · per-frame copy-in (control)",
  "bench.mode.pipeline_resident": "Pipeline · tensors resident in VRAM (M1-2)",
  "bench.run": "Run bench",
  "stats.p95": "p95",
  "gate.pending": "not measured",
};
