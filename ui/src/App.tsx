import { useCallback, useEffect, useRef, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import Viewer, { type Hud } from "./components/Viewer";
import { clickRle } from "./brush";
import { t, type MsgKey } from "./i18n";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import {
  benchStart, benchStats, engineStatus, loadImage, m0Env, parseFrameHead, peekFrame,
  quit, report, runDeform,
  fetchFilmstrip, runExport, runGrade, runHistory, runInpaint, runLight, runLut, runSession, runBackground,
  setStrength, shutdownEngine, startEngine,
  type BenchOptions, type DeformInfo, type DocState, type EngineRuntime, type EngineStatus, type ExportDone,
  type ExportProgress, type HistoryReport, type HistoryState, type ImageReady,
  type InpaintInfo, type SessionState,
  type GradeInfo, type LightInfo,
  type LutInfo, type BackgroundInfo,
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

/** 开发态标志（Vite 构建期常量）：跑靶面板、解释器路径这些**开发工具**只在开发态出现。
 *  发布包里它们不是“美化掉”的东西：一张修图软件的主面板上摆着“python3 / 虚拟环境
 *  解释器绝对路径”与“帧数/帧间隔”，用户会以为产品坏了。产品面板、状态行、日志面板全都
 *  保留——只拆掉那些不是产品的那几个。 */
const IS_DEV = import.meta.env.DEV;

/** 换底后端的显示名（M6）：名单本身由引擎的 matting_backends 给，这里只负责把
 *  它报回来的名字翻成文案。引擎日后多报一个没见过的名字就直接显示原名——名字
 *  是事实，怎么叫它才是文案，前端不许拿名单当自己可枚举的集合。 */
const BG_LABEL: Record<string, MsgKey> = { color_key: "bg.key", birefnet: "bg.ai" };

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
let viewportProbeStarted = false;   // 同上：StrictMode 下 effect 会跑两次

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
  // 路径错误就地显示在输入框下方。原来它只落到 dragNote——那行灰字在窗口另一头，
  // 用户点了「导入」什么也没发生也不知道为什么，那就是事实上的静默失败。
  const [pathErr, setPathErr] = useState("");
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
  // 几何可信度两个读数：基本量（share）与开关（warn）。存基本量而不是对象：
  // refreshStatus 是轮询，每轮 new 一个对象就是每轮一次重渲染（HUD 那边学过）。
  const [deformGeomShare, setDeformGeomShare] = useState(0);
  const [deformGeomWarn, setDeformGeomWarn] = useState(false);
  const deformFlight = useRef(false);
  const deformQueued = useRef<Record<string, number> | null>(null);
  const [lastInpaint, setLastInpaint] = useState<InpaintInfo | null>(null);
  // 影楼色彩（M3-a2）：一张 .cube + 一个混合系数。它不逐事件发（与形变不同）：
  // 引擎每帧真跑一次 3D 查表，但每条命令都要重画一帧，拖快了就堆在 stdin 上。
  const [lutPath, setLutPath] = useState("");
  const [lutAmount, setLutAmount] = useState(1);
  const [lastLut, setLastLut] = useState<LutInfo | null>(null);
  // 肤色定向（M3-b）：三个增量 + 一个混入比例。这一层与形变同侧：拖哪个滑块就动哪个，
  // 所以拖动期间逐事件发（但与形变一样不许排队：一次 IPC 没回来就把后续合并成最新一份）。
  const [gradeAmounts, setGradeAmounts] = useState({ dh: 0, ds: 0, dv: 0 });
  const [gradeMix, setGradeMix] = useState(1);
  const [lastGrade, setLastGrade] = useState<GradeInfo | null>(null);
  // 换底（M6）：最近一次 bg_done。与其它层同生命期（事件驱动、轮询取回）。
  const [lastBg, setLastBg] = useState<BackgroundInfo | null>(null);
  const gradeFlight = useRef(false);
  const gradeQueued = useRef<{ dh?: number; ds?: number; dv?: number } | null>(null);
  // 批量出片（M4）：满幅导出跑在引擎的 worker 线程里，UI 只能从事件拿进度与终态。
  // tile 不预先填一个数：行程与默认值都来自 ready 报的 export_caps，前端抄一份就会在
  // 引擎改口径时把"能导"变成"导错"。
  const [exportDir, setExportDir] = useState("/tmp/luma-export");
  const [exportFormat, setExportFormat] = useState("jpg");
  const [exportQuality, setExportQuality] = useState(95);
  // 放大（M7）：倍率与出片锐量。1 / 0.0 就是"不上这一层"——默认必须是原样出片，
  // 而不是一个没人同意的默认美化。
  const [exportScale, setExportScale] = useState(1);
  const [exportSharpen, setExportSharpen] = useState(0);
  const [exportTile, setExportTile] = useState("");
  // 换底（M6）：背景色 + 色键容差/软边 + 后端。默认走确定性色键；birefnet 需权重，
  // 无权重时引擎会诚实拒（与消除笔的 lama 同一条能力口径）。
  const [bgColor, setBgColor] = useState("#ffffff");
  const [bgTol, setBgTol] = useState(0.12);
  const [bgSoft, setBgSoft] = useState(0.1);
  const [bgBackend, setBgBackend] = useState("color_key");
  const [lastExport, setLastExport] = useState<ExportDone | null>(null);
  const [exportProgress, setExportProgress] = useState<ExportProgress | null>(null);
  // 底片条（M5-a）：格子列表与缩略图分开存。列表每条 session_state 全量替换，
  // 缩略图按 path 累积——引擎重扫过一次列表时 index 会换而 path 不会，
  // 拿 index 配像素就会把上一轮的图塞进不相干的那一格。
  const [strip, setStrip] = useState<SessionState | null>(null);
  const [thumbs, setThumbs] = useState<Record<string, string>>({});
  // 默认留空，不拿一个目录当预置值：上一版预置的是 /tmp/luma-strip，而这台机器的
  // /tmp 是 tmpfs——重启就清，底片条每次开机都是空的，看着像“扫描坏了”。
  const [stripDir, setStripDir] = useState("");
  // 底片条那个目录框同理：扫不进去要当场说，不能只把错误丢给窗口另一头那行灰字
  const [stripErr, setStripErr] = useState("");
  const stripRev = useRef(-1);
  // 当前是哪一张文档：变了才按引擎那份 doc_state 重摆滑块（同图轮询不重摆，
  // 否则会把用户正在拖的手势按回引擎上一帧的值）
  const docKey = useRef("");
  // 撤销/重做（M5-b）。histRep 只信引擎报的那份；histRev 变了才按 history_state
  // 里的 doc_state 重摆滑块（同图撤销时 docKey 不变，走不到 image_ready 那条路）。
  // applied 是"宿主真的把引擎那份状态摆上去了"的直接证据，自动通道要读它。
  const [histRep, setHistRep] = useState<HistoryReport | null>(null);
  const [histDirty, setHistDirty] = useState(false);
  const [lastHistory, setLastHistory] = useState<HistoryState | null>(null);
  const histRev = useRef(-1);
  const docRev = useRef(-1);
  const applied = useRef<{ strength: number; from: string } | null>(null);
  const [dragNote, setDragNote] = useState("");
  const lastSend = useRef(0);
  const pending = useRef<number | null>(null);

  const [w, h] = SIZES[sizeKey];

  /** 引擎那份文档状态 → 界面滑块。两条路共用它：切文档（image_ready）与
   *  撤销/重做（history_state）。各写一遍就是 M5-a 之前那种漂移的源头。 */
  const applyDocState = useCallback((ds: DocState | null | undefined, from: string) => {
    if (!ds) return;
    setStrengthV(ds.strength);
    setRadius(ds.params.radius ?? 12);
    setDetailGain(ds.params.detail_gain ?? 1.0);
    setMidGain(ds.params.mid_gain ?? 0.0);
    setBroadGain(ds.params.broad_gain ?? 0.0);
    setChannel(ds.channel ?? "");
    setLightExposure(ds.light.exposure);
    setDeformAmounts({ slim_face: 0, big_eye: 0, small_chin: 0, ...ds.deform.amounts });
    setLutAmount(ds.lut.amount);
    setGradeAmounts({ dh: ds.grade.dh, ds: ds.grade.ds, dv: ds.grade.dv });
    setGradeMix(ds.grade.amount);
    applied.current = { strength: ds.strength, from };
  }, []);

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
          setDeformGeomWarn(false);
        } else {
          // 不拿 deformNote 做条件（refreshStatus 的依赖表是空的，读到的是旧值）：
          // 无条件清空在正常路径上只是一个 no-op，而按旧值判就会把提示卡在那里抹不掉
          setDeformNote("");
          // 几何不像脸时当场说出来。真图试验量到：肤色盒模板在一张有红发、
          // 脖子与一只手的照片上被撑到整幅，slim_face=0.9 改了 98.6% 的画幅、
          // 其中 57.6% 落在脸外——“瘦脸不许拖走背景”这句承诺当场不成立，而画面上
          // 只是“动得多了点”，看不出错。警告只拿引擎的 geometry_warning 开：作用面
          // 占比（share）随“脸在画面里多大”变，拿它卡固定阈值就是许愿，所以它只当
          // 读数显示。层没点亮时不噪。
          setDeformGeomShare(st.deform.support_share);
          setDeformGeomWarn(st.deform.lit && st.deform.geometry_warning);
        }
      }
      // 调色层也是事件驱动的一次回报（载入/改强度/清除各一条），轮询不能错过
      if (st.lut) setLastLut(st.lut);
      if (st.lut && (st.lut.lut_preset !== null || st.lut.preset_grade_cleared)) {
        // 预设一条命令动两层（表 + 肤色定向），所以定向滑块必须跟着引擎那一层走。
        // 不跟就是“画面已经变了而滑块一动不动”：真图试验量到 clear 之后画面
        // 还带着预设的肤色。只在引擎自己说它动了定向的那两条臂上同步：用户自己
        // 载表时，清调色不许伸进他的肤色里。
        const gs = st.lut.grade_state;
        setGradeAmounts({ dh: gs.dh, ds: gs.ds, dv: gs.dv });
        setGradeMix(gs.amount);
      }
      if (st.grade) setLastGrade(st.grade);
      if (st.background) setLastBg(st.background);
      // 导出这两条无条件跟状态走：Rust 侧在换图/换进程时会清空，这里不跟着清就会
      // 把上一批的字节数当本批读（与图层那几条同一个病，只是这边是账单不是参数）
      setLastExport(st.export ?? null);
      setExportProgress(st.export_progress ?? null);
      // 底片条：小载荷（格子与状态）跟着轮询走，像素只在 session_rev 变了时整条取一次
      setStrip(st.session ?? null);
      if (st.session_rev !== stripRev.current) {
        stripRev.current = st.session_rev;
        const fs = await fetchFilmstrip();
        setThumbs(fs.thumbs);
        if (fs.session) setStrip(fs.session);
      }
      // 历史账（M5-b）。栈深只从宿主记的那一份 doc_report 取：三条带 doc_state 的
      // 事件谁最后到由 Rust 按到达次序数，前端各自取一份就会出现"撤销完了又被一条
      // 晚到的 session_state 把旧栈深顶回来"——按钮在骗人。
      setHistDirty(st.history_dirty);
      if (st.doc_rev !== docRev.current) {
        docRev.current = st.doc_rev;
        setHistRep(st.doc_report?.doc_state?.history ?? null);
      }
      // 重摆滑块的两个触发点。history_state 里只有 undo/redo 真的动了编辑，
      // state 与 clear 是"问一句"，跟着重摆会把用户正在拖的手势按回引擎的值
      if (st.history_rev !== histRev.current) {
        histRev.current = st.history_rev;
        const hs = st.history;
        if (hs) {
          setLastHistory(hs);
          if (hs.action === "undo" || hs.action === "redo") applyDocState(hs.doc_state, hs.action);
        }
      }
      if (st.image) {
        const key = `${st.image.doc ?? ""}#${st.image.session_index ?? -1}`;
        if (key !== docKey.current) {
          docKey.current = key;
          applyDocState(st.image.doc_state, "image_ready");
        }
      } else {
        setHistRep(null);
        applied.current = null;
      }
    } catch {
      /* 引擎未起，忽略 */
    }
  }, [applyDocState]);

  // Ctrl+Z / Ctrl+Shift+Z（macOS 上跟着 Cmd）：撤销是全局动作，不该要求某个按钮被聚焦。
  // 两处放行：① 焦点在文本框里（目录输入框那种编辑不能被全局撤销吃掉）；② 按住 Alt
  // 不动它（留给窗口管理器的组合键）。被拒/空栈由引擎回 noop，按钮自己会灰下去。
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k !== "z" && k !== "y") return;
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      e.preventDefault();
      const redo = k === "y" || e.shiftKey;
      runHistory(redo ? "redo" : "undo")
        .then(() => refreshStatus())
        .catch((err) => setDragNote(String(err)));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [refreshStatus]);

  // 视口自证（M9 裁决3 的取证臂）：静态图导入后静置，读回画布缓冲并量布局矩形。
  // 单独一个 effect，不挂在 M0 跑靶那条链上：那条链的入口是 LRT_AUTO_BENCH，而这里要的
  // 恰恰是"不跑帧流"的静态状态——流在跑时每一帧都在重画，preserveDrawingBuffer 的后果
  // 根本显不出来。历轮跑靶就是这么漏掉黑屏的：帧一直在动，屏上就"看着有东西"。
  useEffect(() => {
    if (viewportProbeStarted) return;
    viewportProbeStarted = true;
    (async () => {
      const env = await m0Env().catch(() => null);
      if (!env?.viewport_probe) return;
      await getCurrentWindow().setFocus().catch(() => undefined);
      // 静态臂不跑 LRT_AUTO_BENCH，所以入图这步得自己做：用的就是用户那条导入命令
      // （onImport 里同一个 loadImage → Rust → 引擎 cmd_load_image），而不是另开一套
      // 测试专用通路——否则这一臂量的就不是用户那一条路。
      if (env.load_image) {
        await loadImage(env.load_image, { maxPx: env.max_px ?? undefined, strength: 0, precompute: "auto" })
          .catch((e) => report(`M0_ERROR 视口探针导入失败: ${e}`));
      }
      // 必须先等到真有一帧送达。探针在首帧之前跑会读到空缓冲，那种"黑"是这个缺陷的
      // 假阳性，量出来会把自己骗过去
      let st: EngineStatus | null = null;
      for (let i = 0; i < 200; i++) {
        st = await engineStatus().catch(() => null);
        if (st?.image) break;
        await sleep(250);
      }
      if (!st?.image) {
        await report("M0_ERROR 视口探针等不到 image（图没导进来，这一读不作数）");
        return;
      }
      const frameDims: [number, number] = [st.image.w, st.image.h];
      await sleep(800);                       // 静置：给合成器几个 vsync 的机会
      const cv = document.querySelector<HTMLCanvasElement>(".viewer > canvas");
      const gl = cv?.getContext("webgl2");
      const rect = cv?.getBoundingClientRect();
      const hud = document.querySelector(".hud")?.getBoundingClientRect();
      const back: Record<string, number> = {};
      if (cv && gl && gl.drawingBufferWidth > 0) {
        const w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
        const px = new Uint8Array(w * h * 4);
        gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
        let sum = 0, sq = 0, nb = 0;
        for (let i = 0; i < w * h; i++) {
          const l = (px[i * 4] + px[i * 4 + 1] + px[i * 4 + 2]) / 3;
          sum += l; sq += l * l; if (l > 4) nb++;
        }
        const mean = sum / (w * h);
        back.readMean = +mean.toFixed(2);
        back.readStd = +Math.sqrt(Math.max(0, sq / (w * h) - mean * mean)).toFixed(2);
        back.readNonBlack = +(nb / (w * h)).toFixed(4);
        // 与 shm 里那一帧逐字节比。不能拿原生顺序直接比：`readPixels` 的原点在
        // **左下**，而 shm 帧从左上起，不翻转就会把“整张垂直倒了”读成“字节对不上”；
        // alpha 也比不了（通路里 alpha 不参与显示）。两个读数都报：不比的是伪证据，
        // 只报一个则看不出差是几何来的还是内容来的。
        back.readDiffVsShm = -1;
        let f = null;
        try { f = parseFrameHead(await peekFrame()); } catch (e) { f = null; }
        if (f && f.w === w && f.h === h && f.pixels.length >= w * h * 4) {
          let raw = 0, flip = 0, row = w * 4;
          for (let r = 0; r < h; r++) {
            const top = r * row;                       // shm：第 r 行从顶上数
            const bot = (h - 1 - r) * row;             // readPixels：原点在左下
            for (let x = 0; x < w; x++) {
              const i = x * 4;
              for (let c = 0; c < 3; c++) {
                if (px[top + i + c] !== f.pixels[top + i + c]) raw++;
                if (px[bot + i + c] !== f.pixels[top + i + c]) flip++;
              }
            }
          }
          back.readDiffVsShm = raw;                    // 不翻转（只当参考）
          back.readDiffFlipRgb = flip;                 // 翻转后的 RGB 差异：这一条该为 0
        }
      }
      const scrollH = document.documentElement.scrollHeight;
      // 反向门（裁决3）：写一个不存在的路径再点「导入」，输入框下方必须出现红字。
      // 这条不是装饰：“错了但不说”就是这次缺陷的本体，门不会关就等于没修。
      let negErrText = "";
      const browseBtns = Array.from(document.querySelectorAll("button"))
        .filter((b) => (b.textContent ?? "").includes("浏览") || (b.textContent ?? "").includes("Browse")).length;
      try {
        setImgPath("/definitely-not-here.jpg");
        await sleep(80);
        const btn = Array.from(document.querySelectorAll("button"))
          .find((b) => (b.textContent ?? "").trim() === t("retouch.import"));
        btn?.click();
        for (let i = 0; i < 40 && !negErrText; i++) {
          await sleep(100);
          negErrText = (document.querySelector(".err")?.textContent ?? "").trim();
        }
        setImgPath("");
      } catch (e) {
        negErrText = `反向门自身异常: ${String(e)}`;   // 异常也要报出来，不许静默吞掉
      }
      await report(`M0_VIEWPORT ${JSON.stringify({
        tag: env.viewport_probe, hasCanvas: !!cv, hasGL: !!gl,
        drawingBuffer: [gl?.drawingBufferWidth ?? 0, gl?.drawingBufferHeight ?? 0],
        frameDims, canvasCss: rect ? [Math.round(rect.width), Math.round(rect.height), Math.round(rect.bottom)] : null,
        canvasBottom: rect ? Math.round(rect.bottom) : -1,
        hudBottom: hud ? Math.round(hud.bottom) : -1,
        innerW: window.innerWidth, innerH: window.innerHeight,
        scrollH, overflowing: scrollH > window.innerHeight,
        browseBtns, negErrText,
        ...back,
      })}`);
    })();
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
      // 发布自检（M5-c 开箱即用）自动通道：LRT_AUTO_RELEASE=1。
      // 装机件在**没有任何开发 env** 的机器上，必须能一句话说清："引擎跑在哪个
      // 解释器、它是从候选表哪一档来的、版本与包账单对不对、hello 报的能力到没到"。
      // 这几件事错了都不崩，只是让"开箱即用"实际变成"在这台开发机上碰巧能跑"。
      // 位置要紧：这一条紧跟 startEngine、在导任何图**之前**。运行时缺包时引擎
      // 当场就死，后面那句 "load_image 未就绪" 会整段 return——把自检放在那之后，
      // 最需要它报账的那一种情形就永远不报，剩下的只有"没跑完"这种模糊读数。
      if (env.auto_release) {
        let st = await engineStatus().catch(() => null);
        for (let i = 0; i < 50; i++) {
          const rt0 = st?.engine_runtime ?? {};
          // ready 到了才会有包账单（packages 一层）里的 torch 键；引擎已经死了也立刻收工
          if (rt0.packages?.torch !== undefined || st?.engine_alive === false) break;
          await sleep(100);
          st = await engineStatus().catch(() => null);
        }
        const rt: EngineRuntime = st?.engine_runtime ?? {};
        await report(`M0_RELEASE ${JSON.stringify({
          engineVersion: st?.engine_version ?? null,
          alive: st?.engine_alive ?? null,
          python: rt.python ?? null,
          // runtime = 候选表命中了装好的运行时；env/explicit = 开发覆盖；
          // fallback = 连候选表都没中，落到了 python3（几乎必然缺 torch）
          pythonSource: rt.python_source ?? null,
          pythonVersion: rt.python_version ?? null,
          engineSrc: rt.engine_src ?? null,
          pkgs: { numpy: rt.packages?.numpy ?? null, pillow: rt.packages?.pillow ?? null,
                  torch: rt.packages?.torch ?? null,
                  torchvision: rt.packages?.torchvision ?? null },
          caps: { presets: st?.presets?.length ?? -1,
                  gradeLimits: st?.grade_limits?.length ?? -1,
                  exportCaps: st?.export_caps ? 1 : 0,
                  editCmds: st?.history_edit_cmds?.length ?? -1,
                  // 能力上报的一致性（M8）：换底/放大两档后端清单必须由引擎自己报，
                  // 缺一项就是“装机件里 UI 在猜能力”——裸环境跑这一臂才能区分。
                  mattingCaps: st?.matting_backends ? 1 : 0,
                  mattingBaseline: st?.matting_backends?.baseline?.length ?? -1,
                  upscaleBackends: st?.export_caps?.upscale_backends ? 1 : 0 },
          hasShm: !!st?.has_shm,
        })}`);
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
      // 肤色定向自动通道（$LRT_AUTO_GRADE="dh:ds:dv:amount"）：与上面几条同一条理由——
      // 只有真窗口能证明 runGrade → Rust grade → 引擎 grade_done 这条命令签名对得上。
      if (env.auto_grade) {
        const parts = env.auto_grade.split(":").map((x) => Number(x));
        if (parts.length !== 4 || parts.some((x) => !Number.isFinite(x))) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_GRADE=${env.auto_grade}（要 dh:ds:dv:amount）`);
        } else {
          const [dh, ds, dv, amount] = parts;
          const waitGrade = async () => {
            // 与调色同一条 12 s 轮询预算：被引擎整条拒（越界、跑靶中）时永远等不到
            for (let i = 0; i < 120; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.grade && st.grade.action === "set" && st.grade.grade_dh === dh) return st.grade;
            }
            return null;
          };
          let got: GradeInfo | null = null;
          try {
            await runGrade("set", { dh, ds, dv, amount });
            got = await waitGrade();
          } catch (e) {
            await report(`M0_ERROR runGrade 失败: ${e}`);
          }
          await report(`M0_GRADE ${JSON.stringify(got ? {
            dh: got.grade_dh, ds: got.grade_ds, dv: got.grade_dv, amount: got.grade_amount,
            lit: got.grade_lit, gradeMs: got.grade_ms, lutMs: got.lut_ms,
            bytesGrade: got.bytes_grade, filterCached: got.filter_cached,
            limits: got.grade_limits, renderMs: got.render_ms,
          } : { bad: "12s 内没等到 grade_done（参数越界或跑靶进行中）", dh, ds, dv, amount })}`);
        }
      }
      // 帧快照与字节差：底片条（M5-a）与撤销/重做（M5-b）两条自动通道共用。
      // 比的是"用户看见的那一帧"，不是引擎上报的那个数字。
      const peek = async () => {
        try {
          return parseFrameHead(await peekFrame());
        } catch (e) {
          await report(`M0_ERROR peekFrame 失败: ${e}`);
          return null;
        }
      };
      // 返回 -1 表示"两份快照不是一块画布"（尺寸不同）。这不等于"画面没变"：
      // 切到不同幅面那张时代理档就从 400×504 变成 552×368，画布都换了，
      // 拿字节数比是比不出东西的——上一版就是在这里把它判成"没变"，一条
      // 假红灯把 mixed 那一档整条带崩
      const diffBytes = (a: Uint8Array | null, b: Uint8Array | null) => {
        if (!a || !b) return -2;
        if (a.length !== b.length) return -1;
        let n = 0;
        for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) n++;
        return n;
      };
      // 换底自动通道（$LRT_AUTO_BG="rrggbb:tol:softness[:backend]"）。
      // 真窗口要证的不是合成本身（test_matting 已钉数值保真），而是三层签名对得上、
      // 且画面真的随之而动：runBackground → Rust background → 引擎 cmd_background →
      // bg_done → engine_status。Tauri 参数名错一个，命令会被静默丢掉（屏上不动而
      // 一个错也不报）——只有真窗口抓得到这一类。
      //
      // 三臂一次跑完，因为它们是同一个里程碑的三半边：
      //   set   → frameChanged > 0（合成写进了用户看见的那一帧）
      //   clear → frameChanged = 0（关掉整层要逐字节回出厂帧，"能开不能关"是缺陷）
      //   birefnet 无权重 → 引擎整条拒、画面不动、宿主还活着（静默降级是最坏答案）
      if (env.auto_background) {
        const parts = env.auto_background.split(":");
        const hex = (parts[0] || "").replace("#", "");
        const tol = Number(parts[1] ?? 0.12), soft = Number(parts[2] ?? 0.10);
        const backend = parts[3] || "color_key";
        if (hex.length !== 6 || !Number.isFinite(tol) || !Number.isFinite(soft)) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_BG=${env.auto_background}（要 rrggbb:tol:softness[:backend]）`);
        } else {
          const bg = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
          // 角落像素直采：frameChanged > 0 只说"动了"，不说"动成了什么"。底色是纯色，
          // 左上角 8×8 均值就该是那个色（±1 量化）——这一条比字节差硬。
          // 字节序是 RGBA（取证：给纯红 ff0000 时 p[0]=255、p[2]=0，而画布用的 ImageData
          // 本就是 RGBA；当成 BGRA 读会得到反的三元组，上一轮 m6bg 真窗口就报过 [0,0,255]）。
          const cornerRgb = (p: Uint8Array | null, w: number) => {
            if (!p || w <= 0) return null;
            let b = 0, g = 0, r = 0, n = 0;
            for (let y = 0; y < 8; y++) {
              for (let x = 0; x < 8; x++) {
                const i = (y * w + x) * 4;
                if (i + 3 >= p.length) return null;
                r += p[i]; g += p[i + 1]; b += p[i + 2]; n++;
              }
            }
            return [Math.round(r / n), Math.round(g / n), Math.round(b / n)];
          };
          const before = await peek();
          const homePix = before?.pixels ?? null;
          // 轮询等一条 bg_done：等 action 而不是等"有 background"，clear 与 set 共用
          // 同一个槽位，不分辨就会把上一条的余温当成这一条的答复
          const waitBg = async (want: "set" | "clear", ms = 12000) => {
            for (let i = 0; i < ms / 100; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.background && st.background.action === want &&
                  (want !== "set" || st.background.bg_active)) return st.background;
            }
            return null;
          };
          let got: BackgroundInfo | null = null;
          try {
            await runBackground("set", { backend, bg, tol, softness: soft });
            got = await waitBg("set");
          } catch (e) {
            await report(`M0_ERROR runBackground 失败: ${e}`);
          }
          const after = await peek();
          const diff = diffBytes(homePix, after?.pixels ?? null);
          await report(`M0_BG ${JSON.stringify(got ? {
            active: got.bg_active, backend: got.backend, fill: got.matte_fill_fg,
            bytesBg: got.bytes_bg, bgMs: got.bg_ms, frameChanged: diff, device: got.device,
            wantBg: bg, cornerBefore: cornerRgb(homePix, before?.w ?? 0),
            cornerAfter: cornerRgb(after?.pixels ?? null, after?.w ?? 0),
          } : { bad: "12s 内没等到 bg_done", bg, tol, soft, backend, frameChanged: diff })}`);

          if (got) {
            // 关掉整层：这一臂的判据是"逐字节回到出厂帧"，不是"变了另一个样"
            let cleared: BackgroundInfo | null = null;
            try {
              await runBackground("clear");
              cleared = await waitBg("clear");
            } catch (e) {
              await report(`M0_ERROR runBackground(clear) 失败: ${e}`);
            }
            const back = await peek();
            await report(`M0_BG_CLEAR ${JSON.stringify(cleared ? {
              active: cleared.bg_active, bytesBg: cleared.bytes_bg,
              frameRestoredDiff: diffBytes(homePix, back?.pixels ?? null),
              cornerRestored: cornerRgb(back?.pixels ?? null, back?.w ?? 0),
              bgMs: cleared.bg_ms,
            } : { bad: "12s 内没等到 clear 的 bg_done" })}`);
          } else {
            // 主臂就没成，后面两臂没有判的余地——但 birefnet 那一臂仍然要试：
            // 它本来就不该成，主臂塌了它该照塌（引擎没被主臂的失败搞死）
            await report("M0_BG_SKIP 主臂未就绪，跳过 clear 臂");
          }

          // birefnet 无权重臂：色键臂能成就说明引擎活着，这一臂要的正是"整条拒 +
          // 画面一个字不动 + 引擎还能应答"。拒的话 bg_done 永不到，这里不等它，
          // 等的是宿主轮询还能拿到状态 + 日志里那条诚实的拒绝。
          if (backend !== "birefnet") {
            const pixBeforeReject = (await peek())?.pixels ?? null;
            let rejectNote = "";
            try {
              await runBackground("set", { backend: "birefnet", bg, tol, softness: soft });
              for (let i = 0; i < 60 && !rejectNote; i++) {
                await sleep(100);
                const st = await engineStatus().catch(() => null);
                const hit = (st?.logs ?? []).find((l) => /birefnet|BiRefNet|权重/.test(l));
                if (hit) rejectNote = hit.slice(0, 220);
              }
            } catch (e) {
              rejectNote = `invoke 抛错: ${e}`;
            }
            const stAfter = await engineStatus().catch(() => null);
            const pixAfterReject = (await peek())?.pixels ?? null;
            await report(`M0_BG_REJECT ${JSON.stringify({
              sawError: !!rejectNote, note: rejectNote,
              frameMoved: diffBytes(pixBeforeReject, pixAfterReject),
              engineAlive: !!stAfter?.engine_alive,
              bgStillActive: stAfter?.background?.bg_active ?? null,
            })}`);

            // 换图即清臂（M8 补的缺陷）：引擎在 cmd_load_image 里把 _bg 整层清回
            // 出厂态（_fresh_doc_state），宿主那一侧的 background 槽位若不跟着清，
            // 就会报“换底还开着”而屏幕上根本没有——同一行还驱动着“关掉换底”按钮的
            // 灰与不灰、常驻 MiB 的读数。裸引擎的协议用例碰不到宿主这一侧，只有真窗
            // 口拿得到这一条。
            if (env.load_image) {
              const pixBeforeReload = (await peek())?.pixels ?? null;
              try {
                await loadImage(env.load_image, { maxPx: env.max_px ?? undefined, strength: 0 });
              } catch (e) {
                await report(`M0_ERROR loadImage（重导）失败: ${e}`);
              }
              let rst: EngineStatus | null = null;
              for (let i = 0; i < 300; i++) {
                await sleep(100);
                rst = await engineStatus().catch(() => null);
                if (rst?.image) break;
              }
              const rl = await peek();
              await report(`M0_BG_RELOAD ${JSON.stringify({
                hostBgCleared: rst?.background == null,
                engineBgActive: rst?.background?.bg_active ?? null,
                // 重导同一张图（同一 maxPx）逐字节等于出厂帧：解码确定、代理档同幅。
                // 不为 0 就是“旧图层没清干净”或“代理档跳了”，两者都不是换底该有的行为。
                frameIsHome: diffBytes(homePix, rl?.pixels ?? null),
                frameMovedVsBefore: diffBytes(pixBeforeReload, rl?.pixels ?? null),
                corner: cornerRgb(rl?.pixels ?? null, rl?.w ?? 0),
                proxy: rst?.image ? `${rst.image.w}x${rst.image.h}` : "-",
                proxySame: !!rst?.image && !!before && `${rst.image.w}x${rst.image.h}` === `${before.w}x${before.h}`,
              })}`);
              // 后面的臂跟着新的代理档走（旧 w/h 驱一个刚重建的会话只会量到陈尺寸）
              if (rst?.image) image = rst.image;
            } else {
              // 不能默默当这一臂过了：没得验就报没得验
              await report("M0_BG_SKIP 无 LRT_LOAD_IMAGE，跳过换图即清臂");
            }

            // 重挂臂：把底色再开回去，并且**开着进接下来的跑靶**。两个理由：
            //   • 换底不是一次性动作——同一会话里第二次 set 也得成（第一次把状态
            //     写坏、第二次静默不动是这类分层最容易犯的错）；
            //   • 后面的 bench 就在"链尾挂着一层常驻合成"的真实状态下量帧通路，
            //     而不是把层关掉再测一个好看的数。
            // M8 起这一臂还多一层意思：它跑在**重导之后**，所以量的是“会话重建后
            // 再开一次”而不只是“同一会话里连着按”。
            await runBackground("set", { backend, bg, tol, softness: soft });
            const again = await waitBg("set");
            const re = await peek();
            await report(`M0_BG_REAPPLY ${JSON.stringify(again ? {
              active: again.bg_active, backend: again.backend, bytesBg: again.bytes_bg,
              corner: cornerRgb(re?.pixels ?? null, re?.w ?? 0),
              frameChangedVsHome: diffBytes(homePix, re?.pixels ?? null),
            } : { bad: "第二次 set 没等到 bg_done" })}`);
          }
        }
      }
      // 等宿主把下一条 history_state 搬进轮询状态：撤销的答复是异步的，
      // 而它的 doc_state 就是"引擎认为现在该摆哪些滑块"的唯一出处
      const waitHistory = async (rev: number, ms = 20000) => {
        for (let i = 0; i < ms / 100; i++) {
          await sleep(100);
          const st = await engineStatus().catch(() => null);
          if (st && st.history_rev !== rev && st.history) return st.history;
        }
        return null;
      };
      // 批量出片（M4）自动通道："<目录>[@<格式>[@<tile>[@<scale>[@<锐量>]]]]"。
      // 这一条与上面几条同一个身份：只有真窗口能证明 runExport → Rust export →
      // 引擎 export_done 对得上；而且落盘尺寸是"导出的是满幅不是代理档"的唯一直接
      // 证据，所以它与 image_ready 的代理档尺寸一起报出去（proxy vs out）。
      // M7 在它后面接上 scale/锐量：同一个口子，证的还是"参数一路递到了落盘那一帧"。
      if (env.auto_export) {
        const [dir, fmt, tileStr, scaleStr, sharpStr] = env.auto_export.split("@");
        if (!dir) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_EXPORT=${env.auto_export}（要 目录[@格式[@tile[@倍率[@锐量]]]]）`);
        } else {
          const proxy = image ? `${image.w}x${image.h}` : "-";
          const scale = scaleStr ? Number(scaleStr) : undefined;
          const sharpen = sharpStr ? Number(sharpStr) : undefined;
          try {
            await runExport(dir, {
              format: fmt || undefined,
              tile: tileStr ? Number(tileStr) : undefined,
              scale: scale && Number.isFinite(scale) && scale > 1 ? scale : undefined,
              sharpen: sharpen && Number.isFinite(sharpen) && sharpen > 0 ? sharpen : undefined,
            });
          } catch (e) {
            await report(`M0_ERROR runExport 失败: ${e}`);
          }
          let got: ExportDone | null = null;
          for (let i = 0; i < 600 && !got; i++) {
            await sleep(200);
            const st = await engineStatus().catch(() => null);
            if (st?.export) got = st.export;
          }
          await report(`M0_EXPORT ${JSON.stringify(got ? {
            dir, proxy, full: got.images.map((x) => (x.error ? `ERR:${x.stage}` : `${x.w}x${x.h}`)),
            tiles: got.images.map((x) => x.tiles ?? 0),
            margin: got.images.map((x) => x.margin_px ?? 0),
            bytes: got.images.map((x) => x.bytes ?? 0),
            failed: got.failed, total: got.total, totalMs: got.total_ms,
            seg: got.images.map((x) => x.seg_ms ?? {}),
            skipped: got.images.map((x) => x.skipped ?? []),
            // 放大（M7）要的直接证据：请求的倍率 vs 引擎报回的倍率 vs 落盘尺寸/源尺寸。
            // 只看"w×h 变大了"分不出"真做了 2×"与"源图本来就大"，所以 ratio 单独算。
            wantScale: scale ?? 1, gotScale: got.scale ?? 1,
            backend: got.upscale_backend ?? null, sharpen: got.sharpen ?? 0,
            srcs: got.images.map((x) => `${x.src_w ?? 0}x${x.src_h ?? 0}`),
            ratios: got.images.map((x) => (x.src_w ? +(x.w! / x.src_w).toFixed(3) : 0)),
            upscaleMs: got.images.map((x) => x.upscale_ms ?? 0),
            sharpenMs: got.images.map((x) => x.sharpen_ms ?? 0),
          } : { bad: "120s 内没等到 export_done", dir, proxy })}`);
        }
      }
      // 底片条（M5-a）自动通道："<目录>[@<切到第几张>[@<长边>]]"。
      // 这一条要证的是签名与数字：TS runSession → Rust session → 引擎 session_state
      // 对得上，而且切走再切回来时引擎报回来的 doc_state 与走时是同一份。
      // 画面像素这里也量（peek_frame 取三次快照比字节）：先前打算只让协议用例
      // （test_switching_documents_returns_the_exact_same_frame）逐字节钉画面，理由是
      // "装机件里那条路是同一份引擎代码"。但那份用例连的是裸引擎，中间隔着 Rust 的
      // session/filmstrip 两条命令与宿主的状态搬运——那两层恰恰只有真窗口能证明。
      // 所以这里量的是"用户看见的那一帧"，不是"引擎算出来的那一帧"。
      if (env.auto_filmstrip) {
        const [dir, pickStr, edgeStr] = env.auto_filmstrip.split("@");
        if (!dir) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_FILMSTRIP=${env.auto_filmstrip}（要 目录[@第几张[@长边]]）`);
        } else {
          const pick = Number(pickStr ?? "1");
          const edge = Number(edgeStr ?? "0");
          const st0 = await engineStatus().catch(() => null);
          const home = st0?.image?.doc ?? null;
          const homeIdx0 = st0?.image?.session_index ?? -1;
          try {
            await runSession("scan", { dir, thumbs: true, ...(edge >= 32 ? { edge } : {}) });
          } catch (e) {
            await report(`M0_ERROR runSession(scan) 失败: ${e}`);
          }
          let sess: SessionState | null = null;
          for (let i = 0; i < 300; i++) {
            await sleep(200);
            const st = await engineStatus().catch(() => null);
            if (st?.session) sess = st.session;
            if (sess && !sess.thumbs_running && sess.count > 0
              && sess.docs.every((d) => d.thumb || d.thumb_error)) break;
          }
          // 基线现取一次：上一条 session_state 可能是开图那一刻发的，中间那几档
          // 自动调参（lut/grade/deform）都不在它里面
          await runSession("state").catch(() => undefined);
          await sleep(400);
          const stB = await engineStatus().catch(() => null);
          sess = stB?.session ?? sess;
          const before = sess?.doc_state ?? null;
          const docs = sess?.docs ?? [];
          // 当前那一格的 index 必须在扫描之后重取：扫进来的那一批会整条替换底片条，
          // 原来那张被挪到列表末尾（引擎只保证"当前那张不会被放下"）。拿扫描前的 0
          // 去"切回"，切到的其实是新列表的第 0 格——引擎完全照办，日志上一个错都
          // 看不出来，而这条通道想证的"绕回原样"当场就变成假的。所以这里以引擎报的
          // index 为准，并且核对 current 还是不是那张
          const homeIdx = sess?.index ?? -1;
          if (sess && home && sess.current !== home) {
            await report(`M0_ERROR 扫描后当前文档换了：${sess.current} ≠ ${home}（不能拿它当基线）`);
          }
          let away: DocState | null = null;
          let back: DocState | null = null;
          let awayPath = "";
          let backPath = "";
          let switchMs = -1;
          const idx = pick >= 0 && pick < docs.length ? pick : -1;
          let pixHome = "", pixAway = "", pixBack = "";
          let seqHome = -1, seqAway = -1, seqBack = -1;
          let diffAway = -1, diffBack = -1;
          // 引擎在 image_ready 里报的代理档尺寸：拿它核对"这次快照取的到底是哪张的帧"。
          // 换到不同幅面的那张时 shm 会整块重建（seq 从 1 重来），只看 seq 递增就会
          // 在那一档判错，而只看字节又证明不了取到的是新帧不是陈旧帧
          let awayReady = "", backReady = "";
          if (idx >= 0 && homeIdx >= 0) {
            const f0 = await peek();
            pixHome = f0 ? `${f0.w}x${f0.h}` : "";
            seqHome = f0?.seq ?? -1;
            const homePix = f0?.pixels ?? null;
            await runSession("select", { index: idx }).catch((e) => report(`M0_ERROR select 失败: ${e}`));
            for (let i = 0; i < 200; i++) {
              await sleep(150);
              const st = await engineStatus().catch(() => null);
              if (st?.image && st.image.doc !== home) {
                away = st.image.doc_state; awayPath = st.image.doc; switchMs = st.image.import_ms;
                awayReady = `${st.image.w}x${st.image.h}`; break;
              }
            }
            {
              const f1 = await peek();
              pixAway = f1 ? `${f1.w}x${f1.h}` : "";
              seqAway = f1?.seq ?? -1;
              diffAway = diffBytes(homePix, f1?.pixels ?? null);
            }
            await runSession("select", { index: homeIdx }).catch((e) => report(`M0_ERROR 切回失败: ${e}`));
            for (let i = 0; i < 200; i++) {
              await sleep(150);
              const st = await engineStatus().catch(() => null);
              if (st?.image && st.image.switched && st.image.doc === home) {
                back = st.image.doc_state; backPath = st.image.doc;
                backReady = `${st.image.w}x${st.image.h}`; break;
              }
            }
            const f2 = await peek();
            pixBack = f2 ? `${f2.w}x${f2.h}` : "";
            seqBack = f2?.seq ?? -1;
            diffBack = diffBytes(homePix, f2?.pixels ?? null);
          }
          // DOM 证据（M9-d）：GL 表面抓不到图，但底片条是 DOM——角标在不在、写的
          // 是什么，可以直接问 DOM。“引擎报了 preview”与“用户看得见这件事”是两层，
          // 差的恰恰是这一层，只看引擎上报抓不到它丢没丢。
          await sleep(150);
          const pvBadges = Array.from(document.querySelectorAll(".strip .cell .badge.pv"))
            .map((el) => (el.textContent ?? "").trim());
          await report(`M0_FILMSTRIP ${JSON.stringify({
            dir, count: sess?.count ?? 0, index: sess?.index ?? -1, home, homeIdx, homeIdx0,
            names: docs.map((d) => d.name),
            thumbCount: docs.filter((d) => d.thumb).length,
            thumbBytes: docs.reduce((a, d) => a + (d.thumb?.bytes ?? 0), 0),
            // RAW 格与“来路是相机内嵌预览”的格分开报：底片条能不能把 DNG 画出来是一回事，
            // 有没有如实告诉用户画的是预览是另一回事。后者只能从这里看得到。
            previewCells: docs.filter((d) => d.thumb?.preview).length,
            pvBadges,
            formats: Array.from(new Set(docs.map((d) => d.thumb?.format).filter(Boolean))),
            longestEdge: Math.max(0, ...docs.map((d) => (d.thumb ? Math.max(d.thumb.w, d.thumb.h) : 0))),
            failed: docs.filter((d) => d.thumb_error).map((d) => `${d.name}:${d.thumb_error}`),
            awayPath, backPath, switchMs,
            before, away, back,
            kept: !!before && !!back && JSON.stringify(before) === JSON.stringify(back),
            // 切过去那张必须干干净净：home 的笔迹漏进新文档，就是"上一张的工刷到
            // 这一张上"。先前这条写的是 away.counts.repair > 0（把漏了当成通过），
            // 方向反了——名字也跟着反，所以一并改成 awayClean
            awayClean: !!away && away.counts.repair === 0 && away.counts.light === 0
              && away.counts.repair_redo === 0 && away.counts.light_redo === 0,
            // 画面这一对才是"切回来还是不是那张"的直接证据：绕回必须 0 字节不同，
            // 而切走那一步必须**有**不同（否则这一对判据是空的——两张图长得一样时
            // "0 字节不同"说明不了任何事）
            frames: `${pixHome}/${pixAway}/${pixBack}`,
            seqs: [seqHome, seqAway, seqBack],
            readyDims: [awayReady, backReady],
            diffAwayBytes: diffAway,
            diffBackBytes: diffBack,
            pixelKept: diffBack === 0,
            // "切走了"的直接证据有两个：画布换了（不同幅面那张）或同一块画布上的
            // 字节真的不同（同幅面那张）。两个都不成立才是没换
            pixelLeft: pixAway !== pixHome || diffAway > 0,
            canvasChanged: pixAway !== pixHome,
          })}`);
        }
      }
      // 撤销/重做（M5-b）自动通道：LRT_AUTO_HISTORY=<强度值>。
      // 引擎那条链已有协议用例逐字节对拍（test_undo_walks_back_through_every_layer），
      // 而那份用例连的是裸引擎。这一条要证的是宿主这四层：
      //   ① runHistory → Rust history → 引擎 history_state 的签名对得上；
      //   ② 画面真的逐字节退回去/回来（peek_frame 从装机件的 shm 里取）；
      //   ③ 宿主按引擎那份 doc_state 重摆了滑块（applied 是唯一直接证据——滑块没跟着
      //      退而画面退了，用户在 UI 上看到的还是 0.9）；
      //   ④ 引擎在 ready 里报的能力名单真的送到了宿主（historyEditCmds）：这一条
      //      上一轮报的是 0，抓出的正是"宿主从没发过 hello"那个缺陷。
      // 基线一律现问引擎（askHistory("state")），不许拿轮询里那份 doc_report：
      // 编辑命令不带 doc_state，拿它就是拿开图那一刻的账来比现在的动作。
      if (env.auto_history) {
        const v = Number(env.auto_history);
        if (!Number.isFinite(v) || v < 0 || v > 1) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_HISTORY=${env.auto_history}（要一个 0–1 的强度值）`);
        } else {
          const askHistory = async (action: "undo" | "redo" | "state" | "clear") => {
            const before = (await engineStatus().catch(() => null))?.history_rev ?? -1;
            await runHistory(action).catch((e) => report(`M0_ERROR runHistory(${action}) 失败: ${e}`));
            const got = await waitHistory(before);
            if (!got) await report(`M0_ERROR 没等到 history ${action} 的答复`);
            return got;
          };
          const st0 = await engineStatus().catch(() => null);
          const editCmds = st0?.history_edit_cmds?.length ?? -1;
          const q0 = await askHistory("state");
          const steps0 = q0?.undo_steps ?? -1;
          const strength0 = q0?.doc_state?.strength ?? -1;
          const base = await peek();
          const homePix = base?.pixels ?? null;
          // 一次手势：两条 set_strength 都只带 value → 同组、窗口内 → 应当只占一步。
          // 第二跳的落点按"离基线强度足够远"来选（不是 v*0.6 那种固定比例）：
          // 挂满图层那一臂的基线强度本来就是 0.5，v=0.85 的 0.6 倍正好 0.51，画面
          // 只差 5515 字节——"撤回去 0 字节"在这种薄鉴别力下几乎不构成证据。
          const target = (q0?.doc_state?.strength ?? 0) <= 0.5 ? 0.95 : 0.05;
          await setStrength(v).catch((e) => report(`M0_ERROR setStrength 失败: ${e}`));
          await sleep(200);
          await setStrength(target).catch((e) => report(`M0_ERROR setStrength 失败: ${e}`));
          await sleep(500);
          const strong = await peek();
          const q1 = await askHistory("state");
          const steps1 = q1?.undo_steps ?? -1;
          const strengthEdit = q1?.doc_state?.strength ?? -1;
          const appliedBefore = applied.current;
          // 撤销：像素必须逐字节等于基线，滑块的 echo 必须回到基线那一刻的值
          const u = await askHistory("undo");
          await refreshStatus();
          const appliedUndo = applied.current;
          const afterUndo = await peek();
          // 重做：必须回到强版本
          const r = await askHistory("redo");
          await refreshStatus();
          const appliedRedo = applied.current;
          const afterRedo = await peek();
          await report(`M0_HISTORY ${JSON.stringify({
            value: v, editCmds, steps0, steps1,
            undoSteps: u?.undo_steps ?? -1, redoSteps: u?.redo_steps ?? -1,
            undoSteps2: r?.undo_steps ?? -1, redoSteps2: r?.redo_steps ?? -1,
            undoMs: u?.history_ms ?? -1, redoMs: r?.history_ms ?? -1,
            renderMs: u?.render_ms ?? -1,
            strength0, strengthEdit,
            strengthUndo: u?.doc_state?.strength ?? -1,
            strengthRedo: r?.doc_state?.strength ?? -1,
            seqs: [base?.seq ?? -1, strong?.seq ?? -1, afterUndo?.seq ?? -1, afterRedo?.seq ?? -1],
            // 鉴别力：上了强度画面必须变（否则下面那两条"相等"是空的）
            changed: diffBytes(homePix, strong?.pixels ?? null),
            // 保真：撤销 == 基线帧、重做 == 撤销前，都是逐字节
            undoDiff: diffBytes(homePix, afterUndo?.pixels ?? null),
            redoDiff: diffBytes(strong?.pixels ?? null, afterRedo?.pixels ?? null),
            // 宿主重摆：applied 由 applyDocState 写，from 说的是哪一条事件摆的
            applied: [appliedBefore?.from ?? "", appliedUndo?.from ?? "", appliedRedo?.from ?? ""],
            appliedStrength: [appliedBefore?.strength ?? -1, appliedUndo?.strength ?? -1,
                              appliedRedo?.strength ?? -1],
            stepsMerged: steps0 >= 0 && steps1 === steps0 + 1,
          })}`);
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
      // 换底层在整个跑靶（几百帧）之后还在不在：这一条是"常驻合成不是只能
      // 一次性点亮"的直接证据。只看 M0_BG_REAPPLY 不够——那是 bench **开始前**的
      // 状态；300 帧里被谁摸了一下、重连时 _attach_pipeline 没重挂上，只有此处能发现。
      if (env.auto_background) {
        const stLive = await engineStatus().catch(() => null);
        await report(`M0_BG_LIVE ${JSON.stringify({
          active: stLive?.background?.bg_active ?? false,
          action: stLive?.background?.action ?? null,
          bytesBg: stLive?.background?.bytes_bg ?? 0,
          emitted: stLive?.emitted ?? 0, delivered: stLive?.delivered ?? 0,
        })}`);
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

  // 开箱即用（M8 发布态）：装机件双击开起来就该是“能用的软件”，而不是“先点一下
  // 启动引擎”。空串 py/src 就是“拿宿主的候选表找运行时”（裸环境那一轮实测
  // python_source=runtime），与手动按钮走同一条路；这里只多一个“不必点”。
  // 跑靶那一条不抢：带 LRT_AUTO_BENCH 时它自己拿 env 的 py/src 起引擎，两边都起
  // 则第二个会被“引擎已在运行”拒掉——那条错不该顶在用户脸上。
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const env = await m0Env().catch(() => null);
      if (cancelled || env?.auto_bench) return;
      try {
        const r = await startEngine("", "");
        if (!cancelled) setPid(r.pid);
      } catch {
        // 起不来不弹错：engine_status 里那一行“没运行/已退出”与运行时账单就是现场证据，
        // 面板上的候选路径提示也在 engine_runtime.hint 里跟着走
      }
    })();
    return () => { cancelled = true; };
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

  /** 原生选择框：路径不该靠手打。dir=true 选目录（底片条），false 选图片文件。
   *  过滤器用引擎报的那份名单（ready.image_exts）；引擎没说就什么都不过滤，而不是
   *  拿宿主抄的一份去挡用户。取消选择是正常路径（返回 null），不报错也不改现值。 */
  async function onPickPath(dir: boolean) {
    let exts: string[] | null = null;
    if (!dir) exts = (await engineStatus().catch(() => null))?.image_exts ?? null;
    const stripped = exts ? exts.map((e) => e.replace(/^\./, "")) : undefined;
    let sel: string | null;
    try {
      sel = await openDialog({ multiple: false, directory: dir,
        ...(stripped ? { filters: [{ name: dir ? "目录" : "图片 / RAW", extensions: stripped }] } : {}) });
    } catch (e) {
      // 选择框本身起不来也要说出来：这里静默返回，用户会以为按钮坏了
      setPathErr(`${t("retouch.pickFailed")}：${String(e)}`);
      return;
    }
    if (typeof sel !== "string" || !sel) return;
    setPathErr("");
    if (dir) { setStripDir(sel); setStripErr(""); } else { setImgPath(sel); }
  }

  /** 导入的成败要从状态里读回来。`load_image` 是“发出去就返回”的（Rust 只回
   *  requested:true），引擎拒一张图走的是 error 事件——不在那个 promise 的拒绝里。
   *  所以下面这三件事必须同时盯：错误位有话、image.doc 变成了这张、或者到点没回话。
   *  少了这一步，坏路径就是一次彻底的静默失败（上一版就是这样）。 */
  async function waitImportOutcome(p: string, ms = 40_000):
    Promise<{ kind: "ok" | "error" | "timeout"; why: string }> {
    const t0 = performance.now();
    while (performance.now() - t0 < ms) {
      const st = await engineStatus().catch(() => null);
      if (st?.last_error) return { kind: "error", why: st.last_error };
      if (st?.image && st.image.doc === p) return { kind: "ok", why: "" };
      await sleep(150);
    }
    return { kind: "timeout", why: t("retouch.loadTimeout") };
  }

  async function onImport() {
    const p = imgPath.trim();
    if (!p) {
      setPathErr(t("retouch.needPath"));
      return;
    }
    setPathErr("");
    setBusy(true);
    setLastInpaint(null);
    setDragNote(t("retouch.importing"));
    try {
      // 设备由 $LRT_DEVICE 定（宿主 load_image 会先把 set_device 发在会话之前）；
      // precompute=auto：有真后端就用真的，没有就用 synthetic 并把原因写进 notes
      await loadImage(p, { maxPx, strength: strengthRef.current, precompute: "auto", channel: channel || undefined });
      const out = await waitImportOutcome(p);
      if (out.kind !== "ok") {
        setPathErr(out.why); setDragNote(out.why);
      } else {
        setDragNote("");      // “导入中…”不许留在屏上：那一行现在说的是过去
      }
    } catch (e) {
      const why = String(e);
      setPathErr(why);                 // 就在输入框下面说，不只丢给窗口另一头那行灰字
      setDragNote(why);
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

  /** 一键预设（M3-b）：一条 `lut set preset=<名>` 同时上表与肤色定向。
   *  强度沿用面板上那个值：预设的“50%”应当是整预设 50%，不是表 50% + 肤色 100%。 */
  function onPreset(name: string) {
    runLut("set", { preset: name, amount: lutAmount })
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)));
  }

  /** 肤色滑块：单飞 + 只留最新一份（与 sendDeform 同一条理由：宁可丢中间帧，
   *  也不让上报与画面错开）。部分提交：只发动过的那一个，另两个沿用当前值。 */
  function sendGrade(opts: { dh?: number; ds?: number; dv?: number }) {
    if (gradeFlight.current) {
      gradeQueued.current = opts;
      return;
    }
    gradeFlight.current = true;
    runGrade("set", opts)
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)))
      .finally(() => {
        gradeFlight.current = false;
        const q = gradeQueued.current;
        gradeQueued.current = null;
        if (q) sendGrade(q);
      });
  }

  function onGradeChange(which: "dh" | "ds" | "dv", value: number) {
    setGradeAmounts({ ...gradeAmounts, [which]: value });
    sendGrade({ [which]: value });
  }

  /** 定向混入比例：也逐事件发（它与其他三个增量一样只改一个数，不重建任何东西） */
  function onGradeMixChange(value: number) {
    setGradeMix(value);
    runGrade("amount", { amount: value })
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)));
  }

  function onGradeClear() {
    runGrade("clear")
      .then(() => refreshStatus())
      .then(() => setGradeAmounts({ dh: 0, ds: 0, dv: 0 }))
      .catch((e) => setDragNote(String(e)));
  }

  /** 换底（M6）：一次事件一条。hex → [r,g,b]；不猜默认 tol/softness（那两数的
   *  语义由色键定，前端写死就会与引擎那一档漂）。 */
  // 可选后端名单由引擎 ready 报的 matting_backends 决定（M8 与放大同一口径）：
  // 没报就只留 color_key——那是唯一零依赖、装机即用的档，前端不许自己扩名单。
  const bgBaseline = status?.matting_backends?.baseline?.length
    ? status.matting_backends.baseline : ["color_key"];
  const bgGated = status?.matting_backends?.weights_gated ?? [];
  // 选中的后端可能在新的引擎进程里已经不在名单中（换进程 = 换能力）：提交前按名单
  // 回落，而不是把注定被整条拒的那一个递上去。
  const bgBackendSafe = bgBaseline.includes(bgBackend) ? bgBackend : bgBaseline[0];
  function onApplyBg() {
    const hex = bgColor.replace("#", "");
    if (hex.length !== 6) { setDragNote("背景色需 #rrggbb"); return; }
    const bg = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
    runBackground("set", { backend: bgBackendSafe, bg, tol: bgTol, softness: bgSoft })
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)));
  }

  function onClearBg() {
    runBackground("clear")
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)));
  }

  /** 导出一张：tile 空串就是“不给”（让引擎用自己的 DEFAULT_TILE），而不是前端猜一个。
   *  倍率/锐量为 1/0 时也不给：那两个值就是“这一层没开”，递上去与递默认值是两回事。 */
  function onExport() {
    const tile = exportTile.trim() === "" ? undefined : Number(exportTile);
    runExport(exportDir, {
      format: exportFormat,
      quality: exportQuality,
      tile,
      scale: exportScale !== 1 ? exportScale : undefined,
      sharpen: exportSharpen > 0 ? exportSharpen : undefined,
    })
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)));
  }

  /** 扫一个目录进底片图：edge 不给就用引擎的默认长边（前端不抄一份数字）。 */
  function onScanStrip() {
    const dir = stripDir.trim();
    if (!dir) { setStripErr(t("strip.needDir")); return; }
    setStripErr("");
    runSession("scan", { dir, thumbs: true })
      .then(() => refreshStatus())
      .catch((e) => { setStripErr(String(e)); setDragNote(String(e)); });
  }

  /** 点一格就换文档。引擎那边走的是 load_image 同一条路（守卫、状态存回、重挂同源），
   *  所以这里被拒（跑靶中/导出中）是正常路径，不是错误分支。 */
  function onPickDoc(index: number) {
    runSession("select", { index })
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)));
  }

  /** 撤销/重做（M5-b）：把手。步数、能不能撤、撤完画面是什么，全由引擎答复。 */
  function onHistory(action: "undo" | "redo" | "clear") {
    runHistory(action)
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)));
  }

  const verdict = gate(stats, w);

  // 引擎进程此刻在不在（M5-c）。报回缺失（新壳配旧宿主）时退回"看 pid"的旧行为，
  // 而不是当成"没在跑"——那会把刚起好的引擎显示成已死。
  const engineAlive = status?.engine_alive ?? !!pid;

  return (
    <div className="app">
      <aside className="side">
        <h1>{t("app.title")}</h1>
        <div className="mut">{t("app.subtitle")}</div>

        <h2>{t("side.engine")}</h2>
        {/* 解释器与引擎源目录只属于开发态：发布包里这两个框填不上也不能让用户去猜
            “该往这里填什么”——候选表的事由宿主定，账单在下面的运行状态那一行说。 */}
        {IS_DEV && (
          <>
            <label className="k">{t("engine.python")}</label>
            <input value={py} onChange={(e) => setPy(e.target.value)} placeholder="python3 / 虚拟环境解释器绝对路径" style={{ width: "100%" }} />
            <label className="k">{t("engine.src")}</label>
            <input value={src} onChange={(e) => setSrc(e.target.value)} placeholder="../engine/src" style={{ width: "100%" }} />
          </>
        )}
        <div className="row">
          <button className="primary" onClick={onStartEngine} disabled={(!!pid && engineAlive) || busy}>
            {t("engine.start")}
          </button>
          <button onClick={onStopEngine} disabled={!pid || !engineAlive}>
            {t("engine.stop")}
          </button>
        </div>
        {/* 运行状态看 engine_alive，不看 pid（M5-c）。pid 只说明“我们起过一个”：
            运行时缺包时引擎立刻死掉，拿 pid 判就会写成“运行中 · PID 1234”，并把
            启动按钮永久禁掉——那时用户唯一能做的事只剩重启整个应用。 */}
        <div className={pid ? (engineAlive ? "ok" : "warn") : "mut"}>
          {pid ? (engineAlive ? t("engine.running", { pid }) : t("engine.died", { pid })) : t("engine.stopped")}
        </div>
        {!!status?.engine_version && (
          <div className="mut">
            {t("engine.version", { v: status.engine_version, py: status.engine_runtime?.python ?? "" })}
          </div>
        )}
        {/* RAW 能力由引擎的 raw_backends 自报（raw.py）：只说基线能读的后缀与插件装没装，
            不拿“支持 RAW”这种笼统话骗人——厂商容器（CR2/NEF）要 libraw 插件才成立。 */}
        {!!status?.raw_backends && (
          <div className="mut">
            {t("engine.raw", {
              s: status.raw_backends.suffixes.join("/"),
              p: status.raw_backends.plugin_installed ? t("engine.rawInstalled") : t("engine.rawMissing"),
            })}
          </div>
        )}
        {/* 缺包告警只在包账单**已到**而 torch 为空时报。拿 `torch == null` 单独判会
            在 ready 还没到的那几百毫秒里就对一个健康引擎闪一次“没有 torch”——
            假告警与假指标同罪。 */}
        {!!status?.engine_runtime?.packages && "torch" in status.engine_runtime.packages
          && status.engine_runtime.packages.torch == null && (!!status.engine_runtime.hint) && (
          <>
            <div className="warn">{t("engine.noTorch", { py: status.engine_runtime.python ?? "" })}</div>
            <div className="mut">{status.engine_runtime.hint}</div>
          </>
        )}
        {status?.has_shm && (
          <div className="mut">
            {t("engine.shm")}: {status.shm} · {status.emitted}/{status.delivered}
          </div>
        )}

        <h2>{t("side.retouch")}</h2>
        <label className="k">{t("retouch.image")}</label>
        <div className="row">
          <input value={imgPath} onChange={(e) => { setImgPath(e.target.value); setPathErr(""); }}
                 placeholder="/path/to/photo.jpg" style={{ flex: 1, minWidth: 0 }} />
          <button onClick={() => onPickPath(false)} title={t("retouch.browseTip")}>{t("retouch.browse")}</button>
        </div>
        {pathErr && <div className="err">{pathErr}</div>}
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
        {deformGeomWarn && (
          <div className="warn">{t("retouch.geomWarn", {
            share: (deformGeomShare * 100).toFixed(0),
            backend: status?.deform?.landmark_backend ?? "-",
          })}</div>
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

        {/* 内置预设（M3-b）：清单与按钮文字全部来自引擎的 ready，前端不抄一份名字。
            一键 = 一张色彩观表 + 三个肤色数，强度滑块同时管两层（那条语义由引擎侧卡）。 */}
        {(status?.presets ?? []).length > 0 && (
          <div className="row">
            {status!.presets.map((p) => (
              <button key={p.name} onClick={() => onPreset(p.name)} disabled={!status?.image}
                      className={lastLut?.lut_preset === p.name ? "primary" : ""}>
                {p.title}
              </button>
            ))}
          </div>
        )}
        {/* 肤色定向（M3-b）：只在肤色窗口里动的三个增量。滑块行程来自 ready 报的
            grade_limits——引擎没说就整排不画，而不是前端先猜一份然后两处漂。 */}
        {(status?.grade_limits ?? []).length === 3 && (
          <>
            <label className="k">{t("grade.hue", { v: gradeAmounts.dh.toFixed(3) })}</label>
            <input type="range" min={-status!.grade_limits[0]} max={status!.grade_limits[0]}
                   step={0.001} value={gradeAmounts.dh}
                   onChange={(e) => onGradeChange("dh", +e.target.value)}
                   style={{ width: "100%" }} />
            <label className="k">{t("grade.sat", { v: gradeAmounts.ds.toFixed(3) })}</label>
            <input type="range" min={-status!.grade_limits[1]} max={status!.grade_limits[1]}
                   step={0.01} value={gradeAmounts.ds}
                   onChange={(e) => onGradeChange("ds", +e.target.value)}
                   style={{ width: "100%" }} />
            <label className="k">{t("grade.val", { v: gradeAmounts.dv.toFixed(3) })}</label>
            <input type="range" min={-status!.grade_limits[2]} max={status!.grade_limits[2]}
                   step={0.01} value={gradeAmounts.dv}
                   onChange={(e) => onGradeChange("dv", +e.target.value)}
                   style={{ width: "100%" }} />
            <label className="k">{t("grade.mix", { v: gradeMix.toFixed(2) })}</label>
            <input type="range" min={0} max={1} step={0.01} value={gradeMix}
                   onChange={(e) => onGradeMixChange(+e.target.value)}
                   style={{ width: "100%" }} />
            <div className="row">
              <button onClick={onGradeClear} disabled={!lastGrade?.grade_set}>
                {t("grade.clear")}
              </button>
            </div>
            <div className="mut">{t("grade.window")}</div>
            {lastGrade && (
              <table>
                <tbody>
                  <tr>
                    <td>{t("grade.layer")}</td>
                    <td>{lastGrade.grade_lit ? t("color.on") : t("color.off")}
                      {' · '}{lastGrade.grade_amount.toFixed(2)}</td>
                  </tr>
                  <tr>
                    <td>{t("grade.params")}</td>
                    <td>{`Δh ${lastGrade.grade_dh.toFixed(4)} · Δs ${lastGrade.grade_ds.toFixed(3)} · Δv ${lastGrade.grade_dv.toFixed(3)}`}</td>
                  </tr>
                  <tr>
                    <td>{t("grade.ms")}</td>
                    <td>{t("grade.msValue", {
                      grade: lastGrade.grade_ms.toFixed(2), lut: lastGrade.lut_ms.toFixed(2),
                      total: lastGrade.total_ms.toFixed(2),
                    })}</td>
                  </tr>
                  {lastGrade.filter_cached && (
                    <tr><td colSpan={2}>{t("grade.cacheKept")}</td></tr>
                  )}
                </tbody>
              </table>
            )}
          </>
        )}

        {/* 换底（M6）：确定性色键把纯色/蓝箱底抠掉换新背景；自动抠图（birefnet）需
            权重，权重未放行前它只在下面的告知行里出现，不做选项——UI 不许邀请用户
            去发一个引擎注定整条拒的请求（静默降级与假可用性是同一种病的两面）。 */}
        <h2>{t("side.background")}</h2>
        <div className="mut">{t("bg.desc")}</div>
        <div className="row">
          <input type="color" value={bgColor} onChange={(e) => setBgColor(e.target.value)}
                 style={{ width: 48 }} />
          <select value={bgBackendSafe} onChange={(e) => setBgBackend(e.target.value)} style={{ width: 132 }}>
            {bgBaseline.map((b) => (
              <option key={b} value={b}>{BG_LABEL[b] ? t(BG_LABEL[b]) : b}</option>
            ))}
          </select>
        </div>
        {!!bgGated.length && (
          <div className="mut">{t("bg.gated", { b: bgGated.join("/"), ok: bgBaseline.join("/") })}</div>
        )}
        <label className="k">{t("bg.tol", { v: bgTol.toFixed(2) })}</label>
        <input type="range" min={0} max={1} step={0.01} value={bgTol}
               onChange={(e) => setBgTol(+e.target.value)} style={{ width: "100%" }} />
        <label className="k">{t("bg.soft", { v: bgSoft.toFixed(2) })}</label>
        <input type="range" min={0.01} max={1} step={0.01} value={bgSoft}
               onChange={(e) => setBgSoft(+e.target.value)} style={{ width: "100%" }} />
        <div className="row">
          <button className="primary" onClick={onApplyBg} disabled={!status?.image}>{t("bg.apply")}</button>
          <button onClick={onClearBg} disabled={!lastBg?.bg_active}>{t("bg.clear")}</button>
        </div>
        {lastBg && (
          <table>
            <tbody>
              <tr><td>{t("bg.state")}</td>
                <td>{lastBg.bg_active ? t("color.on") : t("color.off")}</td></tr>
              {lastBg.action === "set" && (
                <tr><td>{t("bg.fill")}</td>
                  <td>{((lastBg.matte_fill_fg ?? 0) * 100).toFixed(1)}%</td></tr>
              )}
              <tr><td>{t("bg.cost")}</td>
                <td>{t("bg.msValue", { bg: lastBg.bg_ms.toFixed(2), total: lastBg.total_ms.toFixed(2) })}</td></tr>
              <tr><td>{t("bg.resident")}</td>
                <td>{t("retouch.mib", { v: (lastBg.bytes_bg / 1048576).toFixed(2) })}</td></tr>
            </tbody>
          </table>
        )}

        {/* 批量出片（M4）：满幅分块导出。能力清单（格式与 tile 行程）由引擎在 ready 里
            报：export_caps 为空就是这一版引擎还不能导，这里不画按钮也不填一份默认值。 */}
        <h2>{t("side.export")}</h2>
        {status?.export_caps ? (
          <>
            <div className="mut">{t("export.desc")}</div>
            <input value={exportDir} onChange={(e) => setExportDir(e.target.value)}
                   style={{ width: "100%" }} />
            <div className="row">
              <select value={exportFormat}
                      onChange={(e) => setExportFormat(e.target.value)} style={{ width: 84 }}>
                {status.export_caps.formats.map((f) => (
                  <option key={f} value={f}>{f}</option>
                ))}
              </select>
              <input type="number" min={1} max={100} value={exportQuality}
                     onChange={(e) => setExportQuality(+e.target.value)} style={{ width: 58 }} />
              <span className="mut">{t("export.quality")}</span>
              <input type="text" value={exportTile}
                     placeholder={String(status.export_caps.tile_default ?? "")}
                     onChange={(e) => setExportTile(e.target.value)} style={{ width: 72 }} />
              <span className="mut">
                {t("export.tile", { lo: status.export_caps.tile[0], hi: status.export_caps.tile[1] })}
              </span>
            </div>
            {/* 放大（M7）：倍率名单与可用后端全部从 ready 拿。旧引擎不说 scales 就不画
                这一排；weights_gated 那一个后端只当"等权重"告知，不当选项——递上去会被
                引擎整条拒，把它的名字做成下拉就是邀请用户去撞一个注定失败的请求。 */}
            {!!(status.export_caps.scales?.length) && (
              <>
                <div className="row">
                  <label className="k">{t("export.scale")}</label>
                  {(status.export_caps.scales ?? []).map((s) => (
                    <button key={s} className={exportScale === s ? "primary" : ""}
                            onClick={() => setExportScale(s)}>
                      {t("export.scaleValue", { s })}
                    </button>
                  ))}
                </div>
                <div className="row">
                  <input type="number" min={0} max={2} step={0.05} value={exportSharpen}
                         onChange={(e) => setExportSharpen(+e.target.value)} style={{ width: 62 }} />
                  <span className="mut">{t("export.sharpen")}</span>
                </div>
                {!!status.export_caps.upscale_backends?.weights_gated?.length && (
                  <div className="mut">{t("export.upscaleGated", {
                    b: status.export_caps.upscale_backends.weights_gated.join("/"),
                    ok: status.export_caps.upscale_backends.baseline.join("/"),
                  })}</div>
                )}
                {exportScale > 1 && status?.image && (
                  <div className="mut">{t("export.scalePreview", {
                    src: `${status.image.src_w}x${status.image.src_h}`,
                    out: `${status.image.src_w * exportScale}x${status.image.src_h * exportScale}`,
                    mp: ((status.image.src_w * exportScale) * (status.image.src_h * exportScale) / 1e6).toFixed(1),
                  })}</div>
                )}
              </>
            )}
            <div className="row">
              <button className="primary" onClick={onExport}
                      disabled={!status?.image || exportProgress !== null}>
                {exportProgress ? t("export.running") : t("export.run")}
              </button>
            </div>
            {exportProgress && (
              <div className="mut">
                {t("export.progress", { i: exportProgress.index + 1, n: exportProgress.total })}
              </div>
            )}
            {lastExport && (
              <>
                <table>
                  <tbody>
                    <tr>
                      <td>{t("export.files")}</td>
                      <td>{t("export.filesValue", { ok: lastExport.total - lastExport.failed, total: lastExport.total })}</td>
                    </tr>
                    <tr>
                      <td>{t("export.settings")}</td>
                      <td>{t("export.settingsValue", {
                        format: lastExport.format, quality: lastExport.quality, tile: lastExport.tile,
                      })}</td>
                    </tr>
                    {/* 放大那一行只在引擎真报过倍率时画：没报就是这一批没开放大，
                        拿前端的 exportScale 去填会把"我选了 2×"写成"引擎做了 2×" */}
                    {!!lastExport.scale && lastExport.scale > 1 && (
                      <tr>
                        <td>{t("export.scale")}</td>
                        <td>{t("export.scaleRan", {
                          s: lastExport.scale, b: lastExport.upscale_backend ?? "",
                          sh: lastExport.sharpen ?? 0,
                        })}</td>
                      </tr>
                    )}
                    <tr>
                      <td>{t("export.ms")}</td>
                      <td>{`${lastExport.total_ms.toFixed(1)} ms · ${lastExport.out_dir}`}</td>
                    </tr>
                  </tbody>
                </table>
                {lastExport.images.map((x) => (
                  <div key={x.path} className="mut">
                    {x.error
                      ? t("export.failedRow", { stage: x.stage ?? "?", why: x.error })
                      : t("export.row", {
                        name: (x.out ?? "").split("/").pop() ?? "?",
                        size: `${x.w}×${x.h}`, tiles: x.tiles ?? 0,
                        margin: x.margin_px ?? 0, kb: ((x.bytes ?? 0) / 1024).toFixed(0),
                        ms: (x.total_ms ?? 0).toFixed(0),
                      })}
                    {(x.skipped ?? []).length > 0 && (
                      <div>{t("export.skipped", { items: (x.skipped ?? []).join(" · ") })}</div>
                    )}
                  </div>
                ))}
              </>
            )}
          </>
        ) : (
          <div className="mut">{t("export.unavailable")}</div>
        )}

        {/* 底片条（M5-a）：一格一图，点它就切换文档。缩略图按 path 配对（引擎重扫一次
            列表，index 会换而 path 不会）；"已调"徽章来自引擎报的图层数，前端不猜。 */}
        <h2>{t("side.strip")}</h2>
        <div className="mut">{t("strip.desc")}</div>
        <div className="row">
          <input value={stripDir} onChange={(e) => { setStripDir(e.target.value); setStripErr(""); }}
                 placeholder={t("strip.dirPlaceholder")}
                 style={{ flex: 1, minWidth: 0 }} />
          <button onClick={() => onPickPath(true)} title={t("retouch.browseTip")}>{t("retouch.browse")}</button>
          <button onClick={onScanStrip}>{t("strip.scan")}</button>
        </div>
        {stripErr && <div className="err">{stripErr}</div>}
        {strip && strip.count > 0 ? (
          <>
            <div className="mut">
              {t("strip.summary", { n: strip.count, th: strip.docs.filter((d) => d.thumb).length })}
              {strip.thumbs_running ? t("strip.running") : ""}
            </div>
            <div className="strip">
              {strip.docs.map((d) => {
                const edited = d.edits.repair > 0 || d.edits.light > 0 || d.edits.deform
                  || d.edits.lut || d.edits.grade;
                return (
                  <button key={d.path} className={d.loaded ? "cell on" : "cell"}
                          title={d.thumb_error ?? d.path}
                          onClick={() => onPickDoc(d.index)}>
                    {d.thumb && thumbs[d.path] ? (
                      <img alt={d.name} width={d.thumb.w} height={d.thumb.h}
                           src={`data:image/jpeg;base64,${thumbs[d.path]}`} />
                    ) : (
                      <span className="ph">{d.thumb_error ? t("strip.failed") : "…"}</span>
                    )}
                    <span className="nm">{d.name}</span>
                    {edited && <span className="badge">{t("strip.edited")}</span>}
                    {/* RAW 那一格画的是相机内嵌预览。不标就是理亏：用户会以为那一格
                        就是我们解出来的质量，而它其实来自相机——这件事必须上屏。 */}
                    {d.thumb?.preview && (
                      <span className="badge pv" title={t("strip.previewTip")}>
                        {t("strip.preview")}{d.thumb.format ? ` · ${d.thumb.format}` : ""}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </>
        ) : (
          <div className="mut">{t("strip.empty")}</div>
        )}

        {/* 撤销/重做（M5-b）：一条跨层的历史，按一次退一次手势。按钮的灰与不灰只看
            引擎报的那份账；刚发过编辑而答复还没回来时（history_dirty）保持可用，
            否则用户拖完滑块那一下按不动。 */}
        <h2>{t("side.history")}</h2>
        <div className="mut">{t("history.desc")}</div>
        <div className="row">
          <button onClick={() => onHistory("undo")}
                  disabled={!(histRep?.can_undo || histDirty)}>{t("history.undo")}</button>
          <button onClick={() => onHistory("redo")}
                  disabled={!histRep?.can_redo}>{t("history.redo")}</button>
          <button onClick={() => onHistory("clear")}
                  disabled={!histRep?.can_undo}>{t("history.clear")}</button>
        </div>
        <div className="mut">
          {histRep
            ? t("history.count", { u: histRep.undo_steps, r: histRep.redo_steps, max: histRep.history_max })
            : t("history.unknown")}
        </div>
        {lastHistory && (lastHistory.action === "undo" || lastHistory.action === "redo") ? (
          <div className="mut">
            {t("history.last", { act: lastHistory.action, ms: lastHistory.history_ms ?? 0 })}
            {lastHistory.noop ? t("history.noop") : ""}
          </div>
        ) : null}

        {IS_DEV && (
          <>
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
          </>
        )}

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
