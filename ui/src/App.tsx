import { useCallback, useEffect, useRef, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import Viewer, { type Hud } from "./components/Viewer";
import { clickRle } from "./brush";
import { t } from "./i18n";
import {
  benchStart, benchStats, engineStatus, loadImage, m0Env, quit, report, runDeform, runInpaint, runLight, runLut, setStrength,
  shutdownEngine, startEngine,
  type BenchOptions, type DeformInfo, type EngineStatus, type ImageReady, type InpaintInfo, type LightInfo,
  type LutInfo,
  type Precompute, type Stats,
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

/** 强度滑块的最小发送间隔：逐 pointermove 发会把 IPC 排成长队，30 Hz 足够看不见拖影。 */
const DRAG_THROTTLE_MS = 32;

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

  // ---- 精修台（M1-3c/M1-4）：图路径、磨皮参数、通道、画笔 ----
  const [imgPath, setImgPath] = useState("");
  const [maxPx, setMaxPx] = useState(576000);
  const [strength, setStrengthV] = useState(0.5);
  const [radius, setRadius] = useState(12);
  // 这三行初始值必须与引擎侧 DEFAULT_* 逐个对得上（test_drag.py 里有一条用例专看这件事）：
  // 写两份字面量而不对拍，就是 M1-2 那次“默认值改了但调用方还带着旧值”的同构坑。
  const [detailGain, setDetailGain] = useState(1.0);   // 细带（肌理/毛孔）保留度
  const [midGain, setMidGain] = useState(0.0);         // 中带（瑕疵/边缘锐度）保留度
  const [broadGain, setBroadGain] = useState(0.0);     // 低频带（大面积色斑/光影）保留度
  const [channel, setChannel] = useState("");
  const [brushOn, setBrushOn] = useState(false);
  const [brushRadius, setBrushRadius] = useState(8);
  const [feather, setFeather] = useState(2);
  // 画笔模式（M2-a2）：同一支画笔管道，落点时按模式分派到两个图层。
  // 不另开一套坐标采集：修容与消除笔画的都是代理帧上的同一个 RLE，两套代码必漂。
  const [brushMode, setBrushMode] = useState<"heal" | "dodge" | "burn">("heal");
  // 修容档数上限：0.6 档是探针在真图上定的产品默认（再大就开始烧穿高光）
  const [lightExposure, setLightExposure] = useState(0.6);
  const [lastLight, setLastLight] = useState<LightInfo | null>(null);
  // 形变三滑块（M2-b）。存一个对象而不是三个数：送进引擎的就是一份 amounts，
  // 拆成三个 state 会让“只改一个但三个都得送”这种不一致没法说清。
  const [deformAmounts, setDeformAmounts] = useState<Record<string, number>>({
    slim_face: 0, big_eye: 0, small_chin: 0,
  });
  const [lastDeform, setLastDeform] = useState<DeformInfo | null>(null);
  // 引擎把形变层整条清除时说的那句话（为什么滑块自己回零了）：不写这一句，
  // 用户看到的就只是“拖了一下的滑块弹回零”，像出了 bug
  const [deformNote, setDeformNote] = useState("");
  const deformFlight = useRef(false);
  const deformQueued = useRef<Record<string, number> | null>(null);
  const [lastInpaint, setLastInpaint] = useState<InpaintInfo | null>(null);
  // 影楼色彩（M3-a2）：一张 .cube + 一个混合系数。它不逐事件发（与形变不同）：
  // 引擎每帧真跑一次 3D 查表，但每条命令都要重画一帧，拖快了就堆在 stdin 上。
  const [lutPath, setLutPath] = useState("");
  const [lutAmount, setLutAmount] = useState(1);
  const [lastLut, setLastLut] = useState<LutInfo | null>(null);
  const [dragNote, setDragNote] = useState("");
  const lastSend = useRef(0);
  const pending = useRef<number | null>(null);

  const [w, h] = SIZES[sizeKey];

  const refreshStatus = useCallback(async () => {
    try {
      const st = await engineStatus();
      setStatus(st);
      // 消除笔的结果与日志同源：inpaint_done 只发一次，轮询不能错过
      if (st.inpaint) setLastInpaint(st.inpaint);
      if (st.light) setLastLight(st.light);
      if (st.deform) {
        setLastDeform(st.deform);
        // 引擎把整层清了（关键点后端换成不能按脸形取点的那个、或重建失败）：滑块必须
        // 跟着归零。不接这一句就是“界面上写着 0.6 而画面一动不动”，而事件里已说清了
        // 原因——字段与实际错开正是本仓反复付学费的那一类
        if (st.deform.action === "invalidate") {
          setDeformAmounts({ slim_face: 0, big_eye: 0, small_chin: 0 });
          setDeformNote(st.deform.reason ?? "");
        } else {
          // 不拿 deformNote 做条件（refreshStatus 的依赖表是空的，读到的是旧值）：
          // 无条件清空在正常路径上只是一个 no-op，而按旧值判就会把提示卡在那里抹不掉
          setDeformNote("");
        }
      }
      // 调色层也是事件驱动的一次回报（载入/改强度/清除各一条），轮询不能错过
      if (st.lut) setLastLut(st.lut);
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
      let image: ImageReady | null = null;
      let pre: Precompute | null = null;
      if (env.load_image) {
        // 代理档尺寸由引擎决定（按像素预算+长宽比），跑靶得跟着它走，不能拿 spec 里的尺寸硬跑
        const wantPre = !!env.precompute && env.precompute !== "0";
        await loadImage(env.load_image, {
          maxPx: env.max_px ?? undefined,
          strength: 0,
          precompute: wantPre ? env.precompute : undefined,
          channel: env.precompute_channel || undefined,
        });
        // 轮询得同时等预计算：precompute_ready 就在 image_ready 后面几十毫秒，
        // 只盯 image 会在它到达前就 break 掉，报表上变成“导了图但没算掩膜”
        for (let i = 0; i < 300; i++) {
          await sleep(100);
          const st = await engineStatus().catch(() => null);
          image = st?.image ?? null;
          pre = st?.precompute ?? null;
          if (image && (!wantPre || pre)) break;
        }
        if (!image) {
          await report(`M0_ERROR load_image 30s 内未就绪: ${env.load_image}`);
          return;
        }
        if (wantPre && !pre) {
          // 预计算没就绪不能默默当“没这一步”：要么报错要么报缺，绝不给一份假的绿
          await report(`M0_ERROR precompute 30s 内未就绪（backend=${env.precompute}）`);
          return;
        }
        await report(`M0_IMAGE ${JSON.stringify(image)}`);
        if (pre) await report(`M0_PRECOMPUTE ${JSON.stringify(pre)}`);
        bench.w = image.w;
        bench.h = image.h;
      }
      // 消除笔自动通道（$LRT_AUTO_INPAINT="fx:fy:r,…"）：走的是与真人点击完全同一条链
      // ——brush.ts 的 toRle → runInpaint → Rust → 引擎 → inpaint_done。只有真窗口里
      // 跑通，才能说“图层常驻 + 拖拽期零重算”不是只在 pytest 的子进程里成立。
      if (env.auto_inpaint) {
        if (!image) {
          await report("M0_ERROR LRT_AUTO_INPAINT 需要 LRT_LOAD_IMAGE（不知道代理帧尺寸）");
        } else {
          const w = image.w;
          const h = image.h;
          const waitInpaint = async (pred: (v: InpaintInfo) => boolean) => {
            for (let k = 0; k < 300; k++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.inpaint && pred(st.inpaint)) return st.inpaint;
            }
            return null;
          };
          const strokes = env.auto_inpaint.split(",").map((s) => s.trim()).filter(Boolean);
          let bad = "";
          let lastAdd: InpaintInfo | null = null;
          for (let i = 0; i < strokes.length; i++) {
            const [fx, fy, r] = strokes[i].split(":").map(Number);
            if (![fx, fy, r].every(Number.isFinite)) {
              bad = `第 ${i + 1} 段“${strokes[i]}”不是 fx:fy:r`;
              break;
            }
            await runInpaint("add", { rle: clickRle(w, h, fx * w, fy * h, r), feather: 2 });
            lastAdd = await waitInpaint((v) => v.action === "add" && v.ops === i + 1);
            if (!lastAdd) {
              bad = `第 ${i + 1} 笔 30s 内没等到 inpaint_done`;
              break;
            }
          }
          if (bad) {
            await report(`M0_ERROR 消除笔自动通道：${bad}`);
          } else {
            // undo/redo 各走一次：“只存输入”的重放在真窗口里逐笔可回退
            await runInpaint("undo");
            const u = await waitInpaint((v) => v.action === "undo" && v.ops === strokes.length - 1);
            await runInpaint("redo");
            const rd = await waitInpaint((v) => v.action === "redo" && v.ops === strokes.length);
            await report(`M0_INPAINT ${JSON.stringify(lastAdd)}`);
            await report(`M0_INPAINT_STACK ${JSON.stringify({
              strokes: strokes.length, undoOps: u?.ops ?? -1, redoOps: rd?.ops ?? -1,
              // filter_cached 由执行路径给出：重做后那一帧真的重算了滤波。
              // 不叫 cached：引擎侧那两个名字（本层重算/滤波命中）同名会互相覆盖
              filterCached: rd?.filter_cached ?? null,
              layerRecomputed: rd?.layer_recomputed ?? null,
              repairMs: rd?.repair_ms ?? null,
              totalMs: rd?.total_ms ?? null, paintedPx: lastAdd?.painted_px ?? null,
            })}`);
          }
        }
      }
      // 三条带增益自动通道（$LRT_AUTO_SKIN="mid:broad:detail"）：走的是与真人松手完全
      // 同一条链 —— setStrength → Rust set_strength → 引擎 params_set。引擎那条回显由
      // Rust 打到 stdout（M0_ENGINE …），跑靶脚本据此核对参数真的过了宿主这一层：
      // 命令签名改了而 TS 侧名字对不上时，Tauri 会静默丢掉那个参数，一个错也不报。
      if (env.auto_skin) {
        const nums = env.auto_skin.split(":").map(Number);
        if (nums.length !== 3 || !nums.every(Number.isFinite)) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_SKIN=${env.auto_skin}（要 mid:broad:detail）`);
        } else {
          const [midGain, broadGain, detailGain] = nums;
          await setStrength(strengthRef.current, { midGain, broadGain, detailGain })
            .catch((e) => report(`M0_ERROR 带增益提交失败: ${e}`));
          await report(`M0_SKIN ${JSON.stringify({ midGain, broadGain, detailGain,
                                                   strength: strengthRef.current })}`);
          await sleep(600);        // 等引擎的 params_set 回显落进 stdout
        }
      }
      // 修容自动通道（$LRT_AUTO_LIGHT="fx:fy:r:sign,…"）：与自动消除笔同一条链。
      // 只有真窗口能证明 runLight → Rust light → 引擎 light_done 这条命令签名对得上：
      // Tauri 对不上名字时会静默丢参，屏上不动而一个错也不报。
      if (env.auto_light) {
        // 坐标必须落在**代理帧**坐标系里。这里踩过一个坑：外层还有个 `const [w, h] =
        // SIZES[sizeKey]`（合成跑靶档 1024×1280），它和引擎会话 672×848 不是一个系，
        // 拿它算笔印会编出 x=672 这种越界行程码、被引擎整条拒掉。消除笔那一臂一开始就用
        // image.w/h，修容这一臂必须跟着它，不能靠外层那个同名变量。
        if (!image) {
          await report("M0_ERROR LRT_AUTO_LIGHT 需要 LRT_LOAD_IMAGE（不知道代理帧尺寸）");
        } else {
          const pw = image.w;
          const ph = image.h;
          const strokes = env.auto_light.split(",").map((s) => s.trim()).filter(Boolean);
          const waitLight = async (pred: (v: LightInfo) => boolean) => {
            // 轮询预算只给 12 s：命令被引擎整条拒绝时（越界 RLE、参数非法）这一层永远
            // 等不到，长时间空轮询会把 UI 线程冻住，把一次“脚本写错参数”变成
            // 一个看着像产品退化的 fps 数字（实测 45.5 fps / emit_to_pull.max 12.7 s）。
            for (let i = 0; i < 120; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.light && pred(st.light)) return st.light;
            }
            return null;
          };
          let lit: LightInfo | null = null;
          let bad = "";
          for (let i = 0; i < strokes.length; i++) {
            const [fx, fy, r, sign] = strokes[i].split(":").map(Number);
            if (![fx, fy, r, sign].every(Number.isFinite)) { bad = `第 ${i + 1} 条码无法解析`; break; }
            try {
              await runLight("add", { rle: clickRle(pw, ph, fx * pw, fy * ph, r), feather: 2, sign });
            } catch (e) { bad = String(e); break; }
            lit = await waitLight((v) => v.action === "add" && v.ops === i + 1);
            if (!lit) { bad = `第 ${i + 1} 笔 12s 内没等到 light_done（r=${r} 是像素半径，越界会被引擎拒绝）`; break; }
          }
          await report(`M0_LIGHT ${JSON.stringify(bad ? { bad, strokes: strokes.length } : {
            strokes: strokes.length, ops: lit?.ops ?? -1, lit: lit?.lit ?? null,
            exposure: lit?.exposure ?? null, radius: lit?.radius ?? null,
            fieldPeak: lit?.field_peak ?? null, lightMs: lit?.light_ms ?? null,
            bandsMs: lit?.bands_ms ?? null, bytesLight: lit?.bytes_light ?? null,
          })}`);
        }
      }
      // 形变自动通道（$LRT_AUTO_DEFORM="slim:eye:chin"）：与修容同一条理由，只有
      // 真窗口能证明 runDeform → Rust deform → 引擎 deform_done 这条签名对得上。
      if (env.auto_deform) {
        const nums = env.auto_deform.split(":").map((s) => Number(s.trim()));
        if (nums.length !== 3 || !nums.every(Number.isFinite)) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_DEFORM=${env.auto_deform}（要 slim:eye:chin）`);
        } else {
          const amounts = { slim_face: nums[0], big_eye: nums[1], small_chin: nums[2] };
          const waitDeform = async () => {
            // 轮询预算 12 s：被引擎整条拒（没 precompute、synthetic 关键点）时
            // 这一层永远等不到，长时空轮询会冻住 UI 线程、污染 fps。
            for (let i = 0; i < 120; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.deform && st.deform.amounts.slim_face === amounts.slim_face) return st.deform;
            }
            return null;
          };
          let got: DeformInfo | null = null;
          try {
            await runDeform("set", amounts);
            got = await waitDeform();
          } catch (e) {
            await report(`M0_ERROR runDeform 失败: ${e}`);
          }
          await report(`M0_DEFORM ${JSON.stringify(got ? {
            amounts, lit: got.lit, built: got.built, backend: got.landmark_backend,
            deformMs: got.deform_ms, bytesDeform: got.bytes_deform, renderMs: got.render_ms,
            buildMs: got.build?.deform_build_ms ?? null,
            peaks: got.build ? Object.fromEntries(Object.entries(got.build.kinds).map(
              ([k, v]) => [k, v.peak_px])) : null,
            merged: got.build ? Object.fromEntries(Object.entries(got.build.kinds).map(
              ([k, v]) => [k, v.merged])) : null,
          } : { bad: "12s 内没等到 deform_done（没 precompute 或后端被拒）", amounts })}`);
        }
      }
      // 调色自动通道（$LRT_AUTO_LUT="amount@/tmp/x.cube"）：与形变同一条理由，只有
      // 真窗口能证明 runLut → Rust lut → 引擎 lut_done 这条命令签名对得上。
      // 只按**第一个** @ 切分：前半段是个数字，不可能含 @，而路径里什么都可能。
      if (env.auto_lut) {
        const at = env.auto_lut.indexOf("@");
        const amt = Number(at >= 0 ? env.auto_lut.slice(0, at) : "1");
        const src = (at >= 0 ? env.auto_lut.slice(at + 1) : env.auto_lut).trim();
        if (!Number.isFinite(amt) || !src) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_LUT=${env.auto_lut}（要 amount@<路径>）`);
        } else {
          const preset = src.startsWith("preset:") ? src.slice(7) : "";
          const opts = preset ? { preset, amount: amt } : { path: src, amount: amt };
          const waitLut = async () => {
            // 轮询预算 12 s：被引擎整条拒（文件不存在、表非法）时这一层永远等不到，
            // 长时空轮询会冻住 UI 线程、污染 fps。
            for (let i = 0; i < 120; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.lut && st.lut.action === "set" && st.lut.lut_amount === amt) return st.lut;
            }
            return null;
          };
          let got: LutInfo | null = null;
          try {
            await runLut("set", opts);
            got = await waitLut();
          } catch (e) {
            await report(`M0_ERROR runLut 失败: ${e}`);
          }
          await report(`M0_LUT ${JSON.stringify(got ? {
            source: got.lut_source, size: got.lut_size, amount: got.lut_amount,
            lit: got.lut_lit, neutral: got.lut_neutral, clipped: got.lut_clipped,
            notes: got.lut_notes, lutMs: got.lut_ms, mountMs: got.lut_mount_ms,
            bytesLut: got.bytes_lut, filterCached: got.filter_cached, bandsMs: got.bands_ms,
            renderMs: got.render_ms,
          } : { bad: "12s 内没等到 lut_done（文件不存在或表被引擎拒绝）", opts })}`);
        }
      }
      for (let i = 0; i < 100; i++) {
        const st = await engineStatus().catch(() => null);
        if (st?.has_shm) break;
        await sleep(100);
      }
      try {
        await benchStart(bench);
      } catch (e) {
        // 启动被拒就必须收场：继续往下只会空轮询 400×500 ms，最后被 timeout 掐掉，
        // 日志里连“为什么没数据”都不留
        await report(`M0_ERROR bench 启动失败: ${e}`);
        await quit().catch(() => undefined);
        return;
      }
      for (let i = 0; i < 400; i++) {
        await sleep(500);
        const s = await benchStats().catch(() => null);
        if (s?.bench_done) {
          await sleep(1500); // 等在途帧的 ack 收尾
          const final = await benchStats().catch(() => null);
          await report(
            `M0_STATS ${JSON.stringify({ ...final, ...bench, device: env.device, tier: env.skip_pixels === "1" ? 0 : env.skip_draw === "1" ? 1 : 2, upload: env.upload, chunks: env.chunks, ctx: env.no_ctx !== "1", dirtyFrac: env.dirty_frac, hz: +(1000 / bench.intervalMs).toFixed(1), ...(image ? { decodeMs: image.decode_ms, importMs: image.import_ms, scaleMs: image.scale_ms, shmMs: image.shm_ms, attachMs: image.attach_ms, firstFrameMs: image.first_frame_ms, draft: image.draft, draftSize: image.draft_size, pipeDevice: image.device, bytesPerFrame: image.bytes_per_frame, proxy: `${image.w}x${image.h}` } : {}), ...(pre ? { pcBackend: pre.backend, pcInferMs: pre.infer_ms, pcAttachMs: pre.attach_ms, pcTotalMs: pre.total_ms, maskBytes: pre.mask_bytes, channels: pre.mask_channels, residentDevice: pre.resident_device, activeChannel: pre.active_channel } : {}) })}`,
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

  // ------------------------------------------------------------ 精修台
  const strengthRef = useRef(strength);
  strengthRef.current = strength;

  async function onImport() {
    const p = imgPath.trim();
    if (!p) {
      setDragNote(t("retouch.needPath"));
      return;
    }
    setBusy(true);
    setLastInpaint(null);
    setDragNote(t("retouch.importing"));
    try {
      // 设备由 $LRT_DEVICE 定（宿主 load_image 会先把 set_device 发在会话之前）；
      // precompute=auto：有真后端就用真的，没有就用 synthetic 并把原因写进 notes
      await loadImage(p, { maxPx, strength: strengthRef.current, precompute: "auto", channel: channel || undefined });
    } catch (e) {
      setDragNote(String(e));
    } finally {
      setBusy(false);
    }
  }

  /** 强度：零推理通路，可以逐事件发；唯一要卡住的是 IPC 排队频率。 */
  function onStrength(v: number) {
    setStrengthV(v);
    const now = performance.now();
    const send = () => {
      lastSend.current = performance.now();
      setStrength(strengthRef.current, { channel: channel || undefined }).catch((e) => setDragNote(String(e)));
    };
    if (now - lastSend.current >= DRAG_THROTTLE_MS) {
      if (pending.current !== null) {
        window.clearTimeout(pending.current);
        pending.current = null;
      }
      send();
    } else if (pending.current === null) {
      // 拖动的最后一个值必须发出去，否则松手那一下会停在旧强度上
      pending.current = window.setTimeout(() => {
        pending.current = null;
        send();
      }, DRAG_THROTTLE_MS);
    }
  }

  /**
   * 磨皮参数：松手才算。分带（半径/纹理半径/eps）一变要重跑整条 guided（产品档实测 5 ms），
   * 三个增益只重跑重组（~0.5 ms）——两者都逐事件发会把 M1-3c 拿回来的 vsync 余量吐出去。
   */
  function onParamCommit() {
    setStrength(strengthRef.current,
                { radius, detailGain, midGain, broadGain })
      .catch((e) => setDragNote(String(e)));
  }

  function onChannelChange(c: string) {
    setChannel(c);
    setStrength(strengthRef.current, { channel: c || undefined }).catch((e) => setDragNote(String(e)));
  }

  const onStroke = useCallback(
    (rle: number[][], pixels: number) => {
      if (brushMode === "heal") {
        setDragNote(t("retouch.repairing", { pixels }));
        runInpaint("add", { rle, feather })
          .then(() => refreshStatus())
          .catch((e) => setDragNote(String(e)));
        return;
      }
      // 加深/减淡共用一条命令，差别只在符号：场是带符号累加的，所以同处一正一负会抵消
      setDragNote(t("retouch.lighting", { pixels }));
      runLight("add", { rle, feather, sign: brushMode === "dodge" ? 1 : -1 })
        .then(() => refreshStatus())
        .catch((e) => setDragNote(String(e)));
    },
    [feather, brushMode, refreshStatus],
  );

  function onInpaintAction(action: InpaintInfo["action"]) {
    setDragNote(t("retouch.repairing", { pixels: 0 }));
    runInpaint(action)
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)));
  }

  /** 修容层的撤销/重做/清空：与消除笔各自一份栈（M5 再合并成产品级历史） */
  function onLightAction(action: LightInfo["action"]) {
    setDragNote(t("retouch.lighting", { pixels: 0 }));
    runLight(action)
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)));
  }

  /** 修容强度：松手才提交。改一次要重算两份 db（产品档实测 ~4 ms），逐事件发会吐掉 vsync 余量 */
  function onLightExposureCommit() {
    runLight("params", { exposure: lightExposure })
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)));
  }

  /** 形变滑块：拖动期间就要发（引擎侧只缩放已常驻的单位场，产品档每帧 ~1.3 ms）。
   *
   * 但不许排队：一次 IPC 没回来时把后续的合并成“最新那一份”。不这样做的话，
   * 快速拖一下就会在 stdin 上堆几十条命令，而每条都要引擎重画一帧——事件回显
   * 会落到用户早已离开的位置上。宁可丢中间帧，也不让上报与画面错开。
   */
  function sendDeform(amounts: Record<string, number>) {
    if (deformFlight.current) {
      deformQueued.current = amounts;
      return;
    }
    deformFlight.current = true;
    runDeform("set", amounts)
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)))
      .finally(() => {
        deformFlight.current = false;
        const q = deformQueued.current;
        deformQueued.current = null;
        if (q) sendDeform(q);
      });
  }

  function onDeformChange(kind: string, value: number) {
    const next = { ...deformAmounts, [kind]: value };
    setDeformAmounts(next);
    sendDeform(next);
  }

  function onDeformClear() {
    sendDeform({ slim_face: 0, big_eye: 0, small_chin: 0 });
    setDeformAmounts({ slim_face: 0, big_eye: 0, small_chin: 0 });
  }

  /** 载入一张 .cube（M3-a2）。M3-b 会加内置预设按钮，走同一条 runLut 与同一个事件。 */
  function onLutLoad() {
    const p = lutPath.trim();
    if (!p) return;
    runLut("set", { path: p, amount: lutAmount })
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)));
  }

  /** 清除调色层：引擎会回一条 lut_done(action=clear)，面板上那张表得跟着改成未生效 */
  function onLutClear() {
    runLut("clear")
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)));
  }

  /** 调色强度：松手才提交。引擎不重传体积，但每条命令都要重画一帧，
   *  逐事件发会吞掉 vsync 余量（与修容强度同一条理由，与形变滑块相反）。 */
  function onLutAmountCommit() {
    runLut("amount", { amount: lutAmount })
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)));
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

        <h2>{t("side.retouch")}</h2>
        <label className="k">{t("retouch.image")}</label>
        <input value={imgPath} onChange={(e) => setImgPath(e.target.value)} placeholder="/path/to/photo.jpg" style={{ width: "100%" }} />
        <div className="row">
          <input type="number" value={maxPx} step={10000} min={0} onChange={(e) => setMaxPx(+e.target.value)} style={{ width: 110 }} />
          <span className="mut">{t("retouch.maxPx")}</span>
          <button className="primary" onClick={onImport} disabled={!pid || busy || !imgPath.trim()}>{t("retouch.import")}</button>
        </div>
        <label className="k">{t("retouch.strength")} · {strength.toFixed(2)}</label>
        <input type="range" min={0} max={1} step={0.01} value={strength} onChange={(e) => onStrength(+e.target.value)} style={{ width: "100%" }} />
        <label className="k">{t("retouch.radius")} · {radius}</label>
        <input type="range" min={1} max={60} step={1} value={radius} onChange={(e) => setRadius(+e.target.value)}
               onPointerUp={onParamCommit} onKeyUp={onParamCommit} style={{ width: "100%" }} />
        <label className="k">{t("retouch.detail")} · {detailGain.toFixed(2)}</label>
        <input type="range" min={0} max={1.5} step={0.05} value={detailGain} onChange={(e) => setDetailGain(+e.target.value)}
               onPointerUp={onParamCommit} onKeyUp={onParamCommit} style={{ width: "100%" }} />
        <label className="k">{t("retouch.mid")} · {midGain.toFixed(2)}</label>
        <input type="range" min={0} max={1.5} step={0.05} value={midGain} onChange={(e) => setMidGain(+e.target.value)}
               onPointerUp={onParamCommit} onKeyUp={onParamCommit} style={{ width: "100%" }} />
        <label className="k">{t("retouch.broad")} · {broadGain.toFixed(2)}</label>
        <input type="range" min={0} max={1.5} step={0.05} value={broadGain} onChange={(e) => setBroadGain(+e.target.value)}
               onPointerUp={onParamCommit} onKeyUp={onParamCommit} style={{ width: "100%" }} />
        <div className="mut">{t("retouch.commitHint")}</div>
        <label className="k">{t("retouch.channel")}</label>
        <select value={channel} onChange={(e) => onChannelChange(e.target.value)} style={{ width: "100%" }}>
          <option value="">{t("retouch.channelFull")}</option>
          {(status?.precompute?.mask_channels ?? []).map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <div className="row">
          <button className={brushOn ? "primary" : ""} onClick={() => setBrushOn(!brushOn)} disabled={!status?.image}>
            {brushOn ? t("retouch.brushOn") : t("retouch.brushOff")}
          </button>
          <input type="number" min={2} max={64} value={brushRadius} onChange={(e) => setBrushRadius(+e.target.value)} style={{ width: 60 }} />
          <span className="mut">{t("retouch.brushSize")}</span>
          <input type="number" min={0} max={8} value={feather} onChange={(e) => setFeather(+e.target.value)} style={{ width: 52 }} />
          <span className="mut">{t("retouch.feather")}</span>
        </div>
        <div className="row">
          {/* 一支画笔、三个去处（M2-a2）：模式选完再画，与真实修图软件的笔组一致 */}
          <button className={brushMode === "heal" ? "primary" : ""} onClick={() => setBrushMode("heal")}
                  disabled={!status?.image}>{t("retouch.modeHeal")}</button>
          <button className={brushMode === "dodge" ? "primary" : ""} onClick={() => setBrushMode("dodge")}
                  disabled={!status?.image}>{t("retouch.modeDodge")}</button>
          <button className={brushMode === "burn" ? "primary" : ""} onClick={() => setBrushMode("burn")}
                  disabled={!status?.image}>{t("retouch.modeBurn")}</button>
        </div>
        <label className="k">{t("retouch.lightExposure", { stops: lightExposure.toFixed(2) })}</label>
        <input type="range" min={-2} max={2} step={0.05} value={lightExposure}
               onChange={(e) => setLightExposure(+e.target.value)}
               onMouseUp={onLightExposureCommit} onTouchEnd={onLightExposureCommit}
               style={{ width: "100%" }} />
        <div className="row">
          <button onClick={() => onInpaintAction("undo")} disabled={!status?.image}>{t("retouch.undo")}</button>
          <button onClick={() => onInpaintAction("redo")} disabled={!status?.image}>{t("retouch.redo")}</button>
          <button onClick={() => { onInpaintAction("clear"); setLastInpaint(null); }} disabled={!status?.image}>{t("retouch.clear")}</button>
        </div>
        <div className="row">
          <button onClick={() => onLightAction("undo")} disabled={!status?.image}>{t("retouch.lightUndo")}</button>
          <button onClick={() => onLightAction("redo")} disabled={!status?.image}>{t("retouch.lightRedo")}</button>
          <button onClick={() => { onLightAction("clear"); setLastLight(null); }} disabled={!status?.image}>{t("retouch.lightClear")}</button>
        </div>
        {/* 五官微调（M2-b）：三个滑块都是 [-1,1]，负值就是反向（丰颊/小眼/长下巴），
            引擎侧同一套控制点不需要第二份代码。拖动期间逐事件发：它只缩放单位场。 */}
        {(["slim_face", "big_eye", "small_chin"] as const).map((kind) => (
          <div key={kind}>
            <label className="k">{t(`retouch.${kind}`)}
              {' '}{deformAmounts[kind].toFixed(2)}</label>
            <input type="range" min={-1} max={1} step={0.01} value={deformAmounts[kind]}
                   onChange={(e) => onDeformChange(kind, +e.target.value)}
                   style={{ width: "100%" }} />
          </div>
        ))}
        <div className="row">
          <button onClick={onDeformClear} disabled={!status?.image}>{t("retouch.deformClear")}</button>
        </div>
        {deformNote && (
          <div className="mut">{t("retouch.deformInvalidated")}：{deformNote}</div>
        )}
        {lastInpaint && (
          <table>
            <tbody>
              <tr>
                <td>{t("retouch.ops")}</td>
                <td>{lastInpaint.ops} · {t("retouch.redoPending")} {lastInpaint.redo_pending}</td>
              </tr>
              <tr>
                <td>{t("retouch.painted")}</td>
                <td>{lastInpaint.painted_px} px</td>
              </tr>
              <tr>
                <td>{t("retouch.repairMs")}</td>
                <td>{lastInpaint.repair_ms.toFixed(2)} ms</td>
              </tr>
              <tr>
                <td>{t("retouch.totalMs")}</td>
                <td>
                  {lastInpaint.total_ms.toFixed(2)} ms · {t("retouch.cached")}{" "}
                  {lastInpaint.filter_cached ? t("retouch.yes") : t("retouch.no")}
                </td>
              </tr>
              <tr>
                <td>{t("retouch.device")}</td>
                <td>{lastInpaint.device}</td>
              </tr>
            </tbody>
          </table>
        )}
        {dragNote && <div className="mut">{dragNote}</div>}

        {lastLight && (
          <table>
            <tbody>
              <tr>
                <td>{t("retouch.lightOps")}</td>
                <td>{lastLight.ops} · {t("retouch.redoPending")} {lastLight.redo_pending}
                  {' · '}{lastLight.lit ? t("retouch.lightOn") : t("retouch.lightOff")}</td>
              </tr>
              <tr>
                <td>{t("retouch.lightStops")}</td>
                <td>{t("retouch.lightStopsValue", {
                  stops: lastLight.exposure.toFixed(2),
                  peak: lastLight.field_peak.toFixed(2),
                })}</td>
              </tr>
              <tr>
                <td>{t("retouch.lightMs")}</td>
                <td>{t("retouch.lightMsValue", {
                  light: lastLight.light_ms.toFixed(2),
                  total: lastLight.total_ms.toFixed(2),
                })}</td>
              </tr>
              <tr>
                <td>{t("retouch.lightResident")}</td>
                <td>{t("retouch.mib", { v: (lastLight.bytes_light / 1048576).toFixed(2) })}</td>
              </tr>
            </tbody>
          </table>
        )}

        {lastDeform && (
          <table>
            <tbody>
              <tr>
                <td>{t("retouch.deformLayer")}</td>
                <td>{lastDeform.lit ? t("retouch.deformOn") : t("retouch.deformOff")}
                  {' · '}{lastDeform.landmark_backend ?? "-"}</td>
              </tr>
              <tr>
                <td>{t("retouch.deformMs")}</td>
                <td>{t("retouch.deformMsValue", {
                  deform: lastDeform.deform_ms.toFixed(2),
                  total: lastDeform.total_ms.toFixed(2),
                })}</td>
              </tr>
              {lastDeform.build && (
                <tr>
                  <td>{t("retouch.deformBuild")}</td>
                  <td>{t("retouch.deformBuildValue", {
                    ms: lastDeform.build.deform_build_ms.toFixed(1),
                    px: Object.values(lastDeform.build.kinds).map((k) => k.peak_px.toFixed(1)).join(" / "),
                  })}</td>
                </tr>
              )}
              <tr>
                <td>{t("retouch.deformResident")}</td>
                <td>{t("retouch.mib", { v: (lastDeform.bytes_deform / 1048576).toFixed(2) })}</td>
              </tr>
            </tbody>
          </table>
        )}

        <h2>{t("side.color")}</h2>
        {/* 影楼色彩（M3-a2）：一张 .cube + 一个混合系数。引擎侧是逐点输出变换，
            挂在磨皮/修容/形变之后，所以它不作废任何上游缓存（面板上能直接看到
            filter_cached 仍为真）。内置预设（M3-b）会沿同一条 runLut 加进来。 */}
        <label className="k">{t("color.cubePath")}</label>
        <input value={lutPath} onChange={(e) => setLutPath(e.target.value)}
               placeholder="/path/to/grade.cube" style={{ width: "100%" }} />
        <div className="row">
          <button className="primary" onClick={onLutLoad}
                  disabled={!status?.image || !lutPath.trim()}>{t("color.load")}</button>
          <button onClick={onLutClear} disabled={!lastLut?.lut_set}>{t("color.clear")}</button>
        </div>
        <label className="k">{t("color.amount", { v: lutAmount.toFixed(2) })}</label>
        <input type="range" min={0} max={1} step={0.01} value={lutAmount}
               onChange={(e) => setLutAmount(+e.target.value)}
               onPointerUp={onLutAmountCommit} onKeyUp={onLutAmountCommit}
               style={{ width: "100%" }} />
        <div className="mut">{t("color.commitHint")}</div>
        {lastLut && (
          <table>
            <tbody>
              <tr>
                <td>{t("color.layer")}</td>
                <td>{lastLut.lut_lit ? t("color.on") : t("color.off")}
                  {' · '}{lastLut.lut_amount.toFixed(2)}</td>
              </tr>
              <tr>
                <td>{t("color.table")}</td>
                <td>{t("color.tableValue", {
                  size: lastLut.lut_size, source: lastLut.lut_source || "-",
                })}</td>
              </tr>
              {lastLut.lut_neutral && (
                <tr><td colSpan={2}>{t("color.neutral")}</td></tr>
              )}
              {lastLut.lut_clipped > 0 && (
                <tr><td>{t("color.clipped")}</td><td>{lastLut.lut_clipped}</td></tr>
              )}
              {lastLut.lut_notes.length > 0 && (
                <tr><td>{t("color.notes")}</td><td>{lastLut.lut_notes.join(" · ")}</td></tr>
              )}
              <tr>
                <td>{t("color.ms")}</td>
                <td>{t("color.msValue", {
                  lut: lastLut.lut_ms.toFixed(2), total: lastLut.total_ms.toFixed(2),
                  mount: lastLut.lut_mount_ms.toFixed(2),
                })}</td>
              </tr>
              <tr>
                <td>{t("color.resident")}</td>
                <td>{t("retouch.mib", { v: (lastLut.bytes_lut / 1048576).toFixed(2) })}</td>
              </tr>
            </tbody>
          </table>
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
          <option value="image_stream">{t("bench.mode.image_stream")}</option>
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
        <Viewer
          active={!!pid}
          skipDraw={skipDraw}
          upload={upload}
          ctxOpt={ctxOpt}
          chunks={chunks}
          brush={{ on: brushOn && !!status?.image, radius: brushRadius, onStroke }}
          onHud={setHud}
        />
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
