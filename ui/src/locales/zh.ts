/**
 * 中文语言包（主语言）。
 *
 * 约定：组件内一律走 t("key")，禁止硬编码字面量——这样 M1 加英文/其它语言时
 * 不需要改任何组件，也不会像某些上游项目那样把文案焊死在 JSX 里。
 */
const zh = {
  "app.title": "LumaRetouch 精修",
  "app.subtitle": "M0 通路骨架 · 共享内存裸帧",

  "side.engine": "引擎",
  "side.bench": "跑靶参数",
  "side.gate": "M0 判据",

  "engine.python": "Python 解释器（留空取 $LRT_ENGINE_PY）",
  "engine.src": "引擎源码目录（留空取 ../engine/src）",
  "engine.start": "启动引擎",
  "engine.stop": "停止引擎",
  "engine.running": "运行中 · PID {pid}",
  "engine.stopped": "未启动",
  "engine.device": "计算设备",
  "engine.shm": "共享内存",

  "bench.size": "帧尺寸",
  "bench.frames": "帧数",
  "bench.interval": "帧间隔 (ms)",
  "bench.mode": "模式",
  "bench.mode.copy": "纯拷贝（通路极限）",
  "bench.mode.pipeline": "挂导向滤波管线（旧名，等于对照组）",
  "bench.mode.pipeline_copyin": "管线·逐帧搬运（对照组）",
  "bench.mode.pipeline_resident": "管线·张量常驻显存（M1-2）",
  "bench.run": "开始跑靶",
  "bench.running": "跑靶中…",
  "bench.done": "跑靶结束",

  "stats.n": "已确认帧",
  "stats.emitted": "引擎发帧",
  "stats.delivered": "已取走",
  "stats.dropped": "丢帧",
  "stats.dropPct": "丢帧率",
  "stats.fps": "有效帧率",
  "stats.emitToPull": "引擎可读 → 宿主取帧",
  "stats.pullDur": "宿主取帧耗时（拷像素+组装）",
  "stats.emitToAck": "引擎可读 → 绘制回执",
  "stats.emitToPresent": "引擎可读 → 真上屏",
  "stats.pullToAck": "取帧 → 绘制回执（原生计时）",
  "stats.jsDraw": "前端上传+绘制",
  "stats.mean": "均值",
  "stats.p50": "p50",
  "stats.p95": "p95",
  "stats.p99": "p99",
  "stats.max": "最大",
  "stats.none": "暂无样本",

  "gate.desc": "主指标：代理档 sustained 帧率 ≥ 55 fps 且丢帧 ≤ 5%（60Hz）；精帧档按按需出帧算，≥ 20 fps 即可。",
  "gate.fps": "可持续帧率（≥ 55 fps 代理档）",
  "gate.drop": "丢帧率（≤ 5%）",
  "gate.pull": "宿主取帧 p95（拷像素+组装）",
  "gate.latency": "取帧 → 绘制回执（按帧周期计）",
  "gate.pass": "通路 A 成立（Tauri + shm + texSubImage2D）",
  "gate.fail": "超标 → 转路径 B（GTK Overlay + DMA-BUF）",
  "gate.pending": "待实测",

  "hud.frame": "当前帧",
  "hud.seq": "序号",
  "hud.res": "分辨率",
  "hud.origin": "左上角应为红色块（验证纹理未上下翻转）",

  "log.title": "引擎日志",
  "log.empty": "（无）",
} as const;

export type MsgKey = keyof typeof zh;
export default zh;
