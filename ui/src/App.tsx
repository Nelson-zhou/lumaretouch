import { useCallback, useEffect, useRef, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import Viewer, { type Hud } from "./components/Viewer";
import { t } from "./i18n";
import {
  benchStart, benchStats, engineStatus, m0Env, quit, report, shutdownEngine, startEngine,
  type BenchOptions, type EngineStatus, type Stats,
} from "./native";

const SIZES: Record<string, [number, number]> = {
  "640 × 400": [640, 400],
  "1280 × 800（代理档）": [1280, 800],
  "2048 × 1280（精帧档）": [2048, 1280],
};

/**
 * M0 判据：主指标是可持续帧率与丢帧，不是「引擎→上屏」的绝对延迟。
 * 后者最少包含一个垂直同步周期（60Hz 下 16.7 ms），任何按 vsync 出帧的设计
 * 物理上都进不了 10 ms，拿它当门限只会量到调度不是成本。
 */
function gate(s: Stats | null, w: number): "pass" | "fail" | "pending" {
  if (!s || s.n < 10) return "pending";
  return w <= 1280
    ? s.measured_fps >= 55 && s.drop_pct <= 5
      ? "pass"
      : "fail"
    : s.measured_fps >= 20
      ? "pass"
      : "fail";
}

const fmt = (us: number) => (us > 0 ? `${(us / 1000).toFixed(2)} ms` : "—");

/** 解析 "1280x800:600:16.7:copy"。 */
function parseAutoBench(spec: string) {
  const [dims, frames, interval, mode] = spec.split(":");
  const [w, h] = dims.split("x").map(Number);
  if (!w || !h || !frames) return null;
  return { w, h, frames: +frames, intervalMs: +(interval || 16.7), mode: (mode || "copy") as BenchOptions["mode"] };
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
let m0Started = false;   // React StrictMode 下 effect 会执行两次，这里只允许起靶一次

export default function App() {
  const [py, setPy] = useState("");
  const [src, setSrc] = useState("");
  const [pid, setPid] = useState<number | null>(null);
  const [sizeKey, setSizeKey] = useState("1280 × 800（代理档）");
  const [frames, setFrames] = useState(600);
  const [interval, setInterval_] = useState(16.7);
  const [mode, setMode] = useState<BenchOptions["mode"]>("copy");
  const [stats, setStats] = useState<Stats | null>(null);
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [hud, setHudState] = useState<Hud>({ seq: 0, w: 0, h: 0, fps: 0, lastError: "" });
  const hudRef = useRef<Hud>(hud);
  const setHud = useCallback((v: Hud) => {
    hudRef.current = v;
    setHudState(v);
  }, []);
  const [busy, setBusy] = useState(false);
  const [skipDraw, setSkipDraw] = useState(false);
  const [upload, setUpload] = useState<"raw" | "bitmap" | "pingpong">("raw");
  const [ctxOpt, setCtxOpt] = useState(false);
  const [chunks, setChunks] = useState(1);
  const [tierLabel, setTierLabel] = useState("tier2");
  const poll = useRef<number | null>(null);

  const [w, h] = SIZES[sizeKey];

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await engineStatus());
    } catch {
      /* 引擎未起，忽略 */
    }
  }, []);

  // M0 自动跑靶通道
  useEffect(() => {
    if (m0Started) return;
    m0Started = true;
    (async () => {
      const env = await m0Env().catch(() => null);
      const spec = env?.auto_bench;
      if (!env || !spec) return;
      // WebKit 会节流不可见/未聚焦窗口的 rAF，跑靶前必须把窗口拉到前台
      await getCurrentWindow().setFocus().catch(() => undefined);
      const skipPixels = env.skip_pixels === "1";
      // tier0 连像素都不传，上传/绘制自然没得做
      setSkipDraw(env.skip_draw === "1" || skipPixels);
      setTierLabel(skipPixels ? "tier0" : env.skip_draw === "1" ? "tier1" : "tier2");
      const known = ["raw", "bitmap", "pingpong"] as const;
      if ((known as readonly string[]).includes(env.upload)) {
        setUpload(env.upload as (typeof known)[number]);
      }
      // ctx 属性无可复现收益（两轮背靠背：1/5 vs 3/5 vs 3/5 撞帧，均在 ±3fps 噪声内），
      // 故默认关；保留 LRT_NO_CTX / 开关只做后续对照实验用。
      setCtxOpt(env.no_ctx === "0");
      setChunks(env.chunks > 1 ? env.chunks : 1);
      const bench = parseAutoBench(spec);
      if (!bench) {
        await report(`M0_ERROR 无法解析 LRT_AUTO_BENCH=${spec}`);
        return;
      }
      try {
        const r = await startEngine(env.engine_py, env.engine_src);
        setPid(r.pid);
      } catch (e) {
        await report(`M0_ERROR 引擎启动失败: ${e}`);
        return;
      }
      for (let i = 0; i < 100; i++) {
        const st = await engineStatus().catch(() => null);
        if (st?.has_shm) break;
        await sleep(100);
      }
      await benchStart(bench).catch(async (e) => report(`M0_ERROR bench 启动失败: ${e}`));
      for (let i = 0; i < 400; i++) {
        await sleep(500);
        const s = await benchStats().catch(() => null);
        if (s?.bench_done) {
          await sleep(1500); // 等在途帧的 ack 收尾
          const final = await benchStats().catch(() => null);
          await report(
            `M0_STATS ${JSON.stringify({ ...final, ...bench, device: env.device, tier: env.skip_pixels === "1" ? 0 : env.skip_draw === "1" ? 1 : 2, upload: env.upload, chunks: env.chunks, ctx: env.no_ctx !== "1", dirtyFrac: env.dirty_frac, hz: +(1000 / bench.intervalMs).toFixed(1) })}`,
          );
          break;
        }
      }
      await report(`M0_HUD ${JSON.stringify({ ...hudRef.current, active: true })}`);
      await sleep(300);
      await quit().catch(() => undefined);
    })();
  }, []);

  useEffect(() => {
    if (!pid) return;
    const id = window.setInterval(refreshStatus, 1000);
    return () => window.clearInterval(id);
  }, [pid, refreshStatus]);

  useEffect(() => {
    return () => {
      if (poll.current) window.clearInterval(poll.current);
    };
  }, []);

  async function onStartEngine() {
    setBusy(true);
    try {
      const r = await startEngine(py, src);
      setPid(r.pid);
    } catch (e) {
      setHud({ ...hudRef.current, lastError: String(e) });
    } finally {
      setBusy(false);
    }
  }

  async function onRun() {
    setBusy(true);
    setStats(null);
    try {
      await benchStart({ w, h, frames, intervalMs: interval, mode });
      if (poll.current) window.clearInterval(poll.current);
      poll.current = window.setInterval(async () => {
        try {
          const s = await benchStats();
          setStats(s);
          if (s.bench_done && s.delivered >= s.emitted) {
            if (poll.current) window.clearInterval(poll.current);
            poll.current = null;
            setBusy(false);
          }
        } catch {
          /* 忽略单次轮询失败 */
        }
      }, 600);
    } catch (e) {
      setHud({ ...hudRef.current, lastError: String(e) });
      setBusy(false);
    }
  }

  async function onStopEngine() {
    await shutdownEngine().catch(() => undefined);
    setPid(null);
    setStats(null);
  }

  const verdict = gate(stats, w);

  return (
    <div className="app">
      <aside className="side">
        <h1>{t("app.title")}</h1>
        <div className="mut">{t("app.subtitle")}</div>

        <h2>{t("side.engine")}</h2>
        <label className="k">{t("engine.python")}</label>
        <input value={py} onChange={(e) => setPy(e.target.value)} placeholder="python3 / 虚拟环境解释器绝对路径" style={{ width: "100%" }} />
        <label className="k">{t("engine.src")}</label>
        <input value={src} onChange={(e) => setSrc(e.target.value)} placeholder="../engine/src" style={{ width: "100%" }} />
        <div className="row">
          <button className="primary" onClick={onStartEngine} disabled={!!pid || busy}>
            {t("engine.start")}
          </button>
          <button onClick={onStopEngine} disabled={!pid}>
            {t("engine.stop")}
          </button>
        </div>
        <div className={pid ? "ok" : "mut"}>
          {pid ? t("engine.running", { pid }) : t("engine.stopped")}
        </div>
        {status?.has_shm && (
          <div className="mut">
            {t("engine.shm")}: {status.shm} · {status.emitted}/{status.delivered}
          </div>
        )}

        <h2>{t("side.bench")}</h2>
        <label className="k">{t("bench.size")}</label>
        <select value={sizeKey} onChange={(e) => setSizeKey(e.target.value)} style={{ width: "100%" }}>
          {Object.keys(SIZES).map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <label className="k">{t("bench.frames")}</label>
        <input type="number" value={frames} min={1} max={5000} onChange={(e) => setFrames(+e.target.value)} style={{ width: "100%" }} />
        <label className="k">{t("bench.interval")}</label>
        <input type="number" value={interval} step={0.1} onChange={(e) => setInterval_(+e.target.value)} style={{ width: "100%" }} />
        <label className="k">{t("bench.mode")}</label>
        <select value={mode} onChange={(e) => setMode(e.target.value as BenchOptions["mode"])} style={{ width: "100%" }}>
          <option value="copy">{t("bench.mode.copy")}</option>
          <option value="pipeline">{t("bench.mode.pipeline")}</option>
          <option value="pipeline_copyin">{t("bench.mode.pipeline_copyin")}</option>
          <option value="pipeline_resident">{t("bench.mode.pipeline_resident")}</option>
        </select>
        <div className="row">
          <button className="primary" onClick={onRun} disabled={!pid || busy}>
            {busy ? t("bench.running") : t("bench.run")}
          </button>
        </div>

        <h2>{t("side.gate")}</h2>
        <div className="mut">{t("gate.desc")}</div>
        {tierLabel !== "tier2" && <div className="warn">{tierLabel}</div>}
        <div className="row">
          <span className={verdict === "pass" ? "ok" : verdict === "fail" ? "warn" : "mut"}>
            {verdict === "pass" ? t("gate.pass") : verdict === "fail" ? t("gate.fail") : t("gate.pending")}
          </span>
        </div>
        <table>
          <tbody>
            <tr>
              <td>{t("gate.fps")}</td>
              <td>{stats ? `${stats.measured_fps.toFixed(1)} fps` : "—"}</td>
            </tr>
            <tr>
              <td>{t("gate.drop")}</td>
              <td>{stats ? `${stats.drop_pct.toFixed(1)} %` : "—"}</td>
            </tr>
            <tr>
              <td>{t("gate.pull")}</td>
              <td>{stats ? fmt(stats.pull_dur.p95) : "—"}</td>
            </tr>
            <tr>
              <td>{t("gate.latency")}</td>
              <td>{stats ? `${(stats.pull_to_ack.p50 / 1000 / 16.7).toFixed(2)} × 帧周期` : "—"}</td>
            </tr>
          </tbody>
        </table>

        <h2>{t("log.title")}</h2>
        <pre className="log">{status?.logs?.length ? status.logs.join("\n") : t("log.empty")}</pre>
      </aside>

      <main className="stage">
        <Viewer active={!!pid} skipDraw={skipDraw} upload={upload} ctxOpt={ctxOpt} chunks={chunks} onHud={setHud} />
        <div className="hud">
          <div>
            <div className="k">{t("hud.frame")}</div>
            <div>
              {t("hud.seq")} {hud.seq} · {t("hud.res")} {hud.w}×{hud.h}
            </div>
            {hud.lastError && <div className="warn">{hud.lastError}</div>}
          </div>
          <div>
            <div className="k">{t("stats.fps")}</div>
            <div>{hud.fps.toFixed(1)} fps</div>
            <div className="mut">{t("hud.origin")}</div>
          </div>
          <div>
            <div className="k">{t("stats.emitToAck")} p95</div>
            <div>{fmt(stats?.emit_to_ack.p95 ?? 0)}</div>
            <div className="mut">
              {t("stats.jsDraw")} {fmt(stats?.js_draw.p95 ?? 0)} p95
            </div>
          </div>
        </div>
        {stats && (
          <table style={{ padding: "0 14px 12px" }}>
            <tbody>
              {([
                [t("stats.emitToPull"), stats.emit_to_pull],
                [t("stats.pullDur"), stats.pull_dur],
                [t("stats.emitToAck"), stats.emit_to_ack],
                [t("stats.pullToAck"), stats.pull_to_ack],
                [t("stats.emitToPresent"), stats.emit_to_present],
                [t("stats.jsDraw"), stats.js_draw],
              ] as const).map(([label, d]) => (
                <tr key={label}>
                  <td>{label}</td>
                  <td>
                    {fmt(d.mean)} / {fmt(d.p50)} / <b>{fmt(d.p95)}</b> / {fmt(d.p99)} / {fmt(d.max)}
                  </td>
                </tr>
              ))}
              <tr>
                <td>{t("stats.emitted")}/{t("stats.delivered")}/{t("stats.dropped")}</td>
                <td>
                  {stats.emitted}/{stats.delivered}/{stats.dropped}（{stats.drop_pct.toFixed(1)}%）
                </td>
              </tr>
            </tbody>
          </table>
        )}
      </main>
    </div>
  );
}
