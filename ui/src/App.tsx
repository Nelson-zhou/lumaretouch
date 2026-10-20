import { useCallback, useEffect, useRef, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import Viewer, { type Hud } from "./components/Viewer";
import RegistryPanel from "./components/RegistryPanel";
import StudioPanel from "./components/StudioPanel";
import { REGISTRY, keyOf, sectionTitleOf, type SectionId } from "./p0";
import { clickRle } from "./brush";
import { t, type MsgKey } from "./i18n";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import {
  benchStart, benchStats, engineStatus, loadImage, m0Env, parseFrameHead, peekFrame,
  faceStateOf, enhanceStateOf,
  quit, report, runDeform, runEnhance, runFace,
  fetchFilmstrip, runExport, runGrade, runHistory, runInpaint, runLight, runLut, runPick, runSession, runBackground,
  runBatch, runCrop, runExposure, runPreset, runPrecompute, runProject, runTask,
  setCompare, setStrength, shutdownEngine, startEngine,
  type BenchOptions, type DeformInfo, type DocState, type EngineRuntime, type EngineStatus, type EnhanceInfo, type ExportDone,
  type ExportProgress, type HistoryReport, type HistoryState, type ImageReady,
  type InpaintInfo, type SessionState,
  type GradeInfo, type LightInfo,
  type LutInfo, type BackgroundInfo,
  type PickRun, type Precompute, type SessionDoc, type Stats, type ProjectState,
  type TaskState,
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
  const [comparing, setComparing] = useState(false);   // 按住看原图中（不改会话强度）
  const comparingRef = useRef(false);
  const [mirrorOn, setMirrorOn] = useState(true);
  const [glVisible, setGlVisible] = useState(false);   // 对照实验：把 GL 画布放回可见位
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
  const [brushMode, setBrushMode] = useState<"heal" | "dodge" | "burn" | "color">("heal");
  // 框选补脸那一档（LNX-PORTRAIT-006）：它是一次性的编辑意图，不是文档状态——文档状态
  // 是引擎那份 `_face_manual`，这里只记"视口下一拖该画框还是该平移"
  const [pickFace, setPickFace] = useState(false);
  // 修容档数上限：0.6 档是探针在真图上定的产品默认（再大就开始烧穿高光）
  const [lightExposure, setLightExposure] = useState(0.6);
  const [lastLight, setLastLight] = useState<LightInfo | null>(null);
  // 形变三滑块（M2-b）。存一个对象而不是三个数：送进引擎的就是一份 amounts，
  // 拆成三个 state 会让“只改一个但三个都得送”这种不一致没法说清。
  // 默认值只是"引擎还没说话之前显示 0"，不是名单：名单一律来自 ready 的 deform_kinds
  const [deformAmounts, setDeformAmounts] = useState<Record<string, number>>({
    slim_face: 0, big_eye: 0, small_chin: 0, smile: 0,
  });
  const [lastDeform, setLastDeform] = useState<DeformInfo | null>(null);
  // 引擎把形变层整条清除时说的那句话（为什么滑块自己回零了）：不写这一句，
  // 用户看到的就只是“拖了一下的滑块弹回零”，像出了 bug
  const [deformNote, setDeformNote] = useState("");
  // 眼牙三格（LNX-PORTRAIT-009）。名单一律来自 ready 的 enhance_subs：这四个初值只是
  // "引擎还没说话之前显示 0"，不是名单（与形变那几个数同一条纪律）。
  const [enhanceAmounts, setEnhanceAmounts] = useState<Record<string, number>>({
    sclera: 0, iris: 0, teeth: 0,
  });
  const [lastEnhance, setLastEnhance] = useState<EnhanceInfo | null>(null);
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
  // 16-bit 母档直通（M9-e）：默认关。开它就是要求"其它都别动"；只有把它单独成一个勾，
  // "这一件没经过图层"才说得出口。
  const [exportBits16, setExportBits16] = useState(false);
  // 形变作用层（LNX-PORTRAIT-004）：这一格选的是"正在改哪一层"，值本身不进口径——
  // 每一层的数值与"这张被覆盖了哪几格"都由引擎随 doc_state 报（面板读它，不读这里）
  const [deformScope, setDeformScope] = useState<"all" | "person">("all");
  // 导出侧 P0 的四格（注册表 lnx.export.v1 / lnx.batch.v1）。中性位按冻结的注册表：
  // gps 默认关、冲突默认 skip_and_report、色彩档默认 srgb；tiff 压缩的 16-bit 例外
  // 由引擎拒（那条报错会说出来），前端不预先猜
  const [exportProfile, setExportProfile] = useState("srgb");
  const [exportTiffComp, setExportTiffComp] = useState("deflate");
  const [exportGps, setExportGps] = useState(false);
  const [exportConflict, setExportConflict] = useState("skip_and_report");
  // 底片条多选集（LNX-P0-BATCH / 图库批量化）：按 path 记，不按 index 记——
  // 重扫一次目录 index 会换而 path 不会
  const [sel, setSel] = useState<Set<string>>(new Set());
  const selAnchor = useRef<number | null>(null);
  const [batchTag, setBatchTag] = useState("");
  // 预设与批量同步（LNX-P0-PRESET / LNX-P0-BATCH）：清单、台账与上一笔的事实全部从
  // status.session 里读（引擎随 session_state 报），这里只记“界面上选中了哪一个”与
  // “要存的新预设叫什么”。前端不扫目录、不记 batch_id：那是两个会漂的地方。
  const [presetName, setPresetName] = useState("");
  const [presetSel, setPresetSel] = useState("");
  const [appliedPreset, setAppliedPreset] = useState("");
  const [syncScopeLabel, setSyncScopeLabel] = useState("");
  // 视口平移/缩放（只属于显示：导出写的仍是引擎那一份像素）
  const [view, setView] = useState({ zoom: 1, x: 0, y: 0 });
  // 工程与任务面（读只读引擎报的那两份，前端不记“存过了”）
  const [projName, setProjName] = useState("");
  const [projErr, setProjErr] = useState("");
  const [exportErr, setExportErr] = useState("");
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
  // 挑图（LNX-PICK-001）：四组敏感度（档名由引擎 ready 报，这里只存用户挑的那一个）
  const [pickSens, setPickSens] = useState<Record<string, string>>({});
  const [pickNote, setPickNote] = useState("");
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
    setDeformAmounts({ slim_face: 0, big_eye: 0, small_chin: 0, smile: 0, ...ds.deform.amounts });
    setEnhanceAmounts({ sclera: 0, iris: 0, teeth: 0, ...(ds.enhance?.amounts ?? {}) });
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
      if (st.enhance) {
        setLastEnhance(st.enhance);
        // defer/invalidate 那两条不能把滑块弹回零：那两句说的是"引擎现在认不认得人"，
        // 而"用户改过什么"是另一件事（PORTRAIT-004 定下的分层，形变那边同一课）
        if (st.enhance.action === "invalidate") {
          setEnhanceAmounts({ sclera: 0, iris: 0, teeth: 0, ...(st.enhance.dropped_amounts ?? {}) });
        } else {
          setEnhanceAmounts({ sclera: 0, iris: 0, teeth: 0, ...st.enhance.amounts });
        }
      }
      if (st.deform) {
        setLastDeform(st.deform);
        // 引擎把整层清了（关键点后端换成不能按脸形取点的那个、或重建失败）：滑块必须
        // 跟着归零。不接这一句就是“界面上写着 0.6 而画面一动不动”，而事件里已说清了
        // 原因——字段与实际错开正是本仓反复付学费的那一类
        if (st.deform.action === "defer") {
          // 重开工程 / 迁会话那一条：层还在而关键点还没回来。滑块值保持引擎报的那一份
          // （deferred_amounts）——归零就是“把用户的作品按引擎内部事件抹掉”，而那句
          // 「已清除」是 invalidate 才说的。值没丢而画面暂未生效，由面板那行提示讲清。
          setDeformAmounts({ slim_face: 0, big_eye: 0, small_chin: 0, smile: 0,
                             ...(st.deform.deferred_amounts ?? st.deform.amounts ?? {}) });
          setDeformNote(st.deform.reason ?? "");
        } else if (st.deform.action === "invalidate") {
          setDeformAmounts({ slim_face: 0, big_eye: 0, small_chin: 0, smile: 0 });
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
  // 按住空格 = 看原图（DoD 的"对拍"快捷键）。三条守卫都是必要的：
  // ① 焦点在输入框/文本域里时空格是打字，不许被抢走；
  // ② preventDefault 挡掉"空格顺手点击当前聚焦的按钮"（不然一按撤销就没了）；
  // ③ 与按钮那条按住路径共用 comparingRef：两条路都能起,但只能有一个在放。
  useEffect(() => {
    const isText = (el: HTMLElement | null) =>
      !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
    const down = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat || isText(e.target as HTMLElement)) return;
      e.preventDefault();
      if (!pid || comparingRef.current) return;
      comparingRef.current = true;
      setComparing(true);
      void setCompare(true).catch((err) => setDragNote(String(err)));
    };
    const up = (e: KeyboardEvent) => {
      if (e.code !== "Space" || isText(e.target as HTMLElement)) return;
      if (!comparingRef.current) return;
      comparingRef.current = false;
      setComparing(false);
      void setCompare(false).catch((err) => setDragNote(String(err)));
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); };
  }, [pid]);

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
      let importBtn: { found: boolean; text: string } = { found: false, text: "" };
      if (env.load_image) {
        if (/^manual/.test(env.viewport_probe)) {
          // 手动臂：只把路径填进输入框，然后真的去点「导入」那一个按钮。这一条走的是
          // onImport 全链（trim 校验、setBusy、loadImage、waitImportOutcome、就地红字），
          // 而不是探针直调 loadImage——用户报的那次黑屏发生在按钮这条路上，自动臂的
          // 读数替它不作证：两条路的差别正好可能是缺陷所在。
          setImgPath(env.load_image);
          await sleep(150);                       // 让 React 把 imgPath 提交进去
          const b = Array.from(document.querySelectorAll("button"))
            .find((x) => (x.textContent ?? "").trim() === t("retouch.import"));
          importBtn = { found: !!b, text: (b?.textContent ?? "").trim() };
          b?.click();
        } else {
          await loadImage(env.load_image, { maxPx: env.max_px ?? undefined, strength: 0, precompute: "auto" })
            .catch((e) => report(`M0_ERROR 视口探针导入失败: ${e}`));
        }
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
      const cv = document.querySelector<HTMLCanvasElement>(".viewer .gl-src");
      const mir = document.querySelector<HTMLCanvasElement>("body > .mirror");
      const gl = cv?.getContext("webgl2");
      const rect = cv?.getBoundingClientRect();
      const hud = document.querySelector(".hud")?.getBoundingClientRect();
      const back: Record<string, number | number[] | string> = {};
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
      // 一刀两断的实验：给 canvas 元素本身刷一个刺眼的 CSS 背景再截图。截图抓不到 GL
      // 后备缓冲（M2-a2 已证），但 CSS 背景是 DOM 绘制、走页面合成那条路。
      //   截图这块变绿 → 页面合成能上屏、GL 内容上不了屏：黑屏是真的，缺陷在 GL→屏幕；
      //   截图仍是黑 → 截图对这个区域完全无效，"截图里黑"不能作为任何主张的证据。
      //
      // 实测落在第二种：绿色 CSS 背景没进截图（WebGL 后备缓冲盖住了元素背景），但
      // canvas 的 8px 品红 outline 进了——同一张图里"DOM 有效、GL 无效"同时成立，于是
      // 用户报的那次黑屏被判定为**截图伪影**，不是缺陷；下面那个 toDataURL→<img> 才是
      // 正面证据：照片清晰、方向正确地显示在页面上。这一臂留着，以后"黑屏"主张一律先
      // 走它，别再拿 readPixels 当"上屏"的证据——那是后备缓冲，它有没有内容和屏幕上
      // 看不看得到是两段路。
      if (/lime/.test(env.viewport_probe) && cv) {
        cv.style.background = "#00ff00";
        cv.style.outline = "8px solid #ff00ff";
        // 最后一击：把 GL 后备缓冲转成 <img> 贴进 DOM。img 走页面合成，截图一定能反映——
        // 于是"屏幕上到底有没有这张照片"就不再依赖任何推断（preserveDrawingBuffer:true
        // 正是为了让 toDataURL 拿得到内容，而不是拿到一张空图）。
        let dump = "";
        try {
          const url = cv.toDataURL("image/png");
          const el = document.createElement("img");
          el.src = url;
          Object.assign(el.style, { position: "fixed", left: "540px", top: "40px", width: "300px", border: "4px solid #ffffff", zIndex: "9999" });
          document.body.appendChild(el);
          dump = url.slice(0, 22) + `…len=${url.length}`;
        } catch (e) { dump = `toDataURL 失败: ${String(e)}`; }
        await report(`M0_LIME ${JSON.stringify({cssBg: getComputedStyle(cv).backgroundColor, rect: [cv.getBoundingClientRect().width, cv.getBoundingClientRect().height], dump})}`);
      }
      // 通路选型实验：2D canvas 的 putImageData 在这台机器上能不能被看见（判据用
      // "X 抓图抓不抓得到"，因为抓得到就等于它进了页面合成，屏幕必然也有）。
      // 抓得到 → 视口可以从 WebGL 换成 2D 通路；抓不到 → 只能退到 <img>。
      if (/twod/.test(env.viewport_probe) && cv && gl) {
        // 不另开一条取帧路（Viewer 的回路会把 pullFrame 那帧抢走），直接把 GL 画布
        // drawImage 镜像到一张 2D 画布——这也正是候选修法本身：每帧一次 drawImage。
        try {
          const c2 = document.createElement("canvas");
          c2.width = cv.width; c2.height = cv.height;
          Object.assign(c2.style, { position: "fixed", left: "540px", top: "60px", width: "300px",
                                    border: "4px solid #ffffff", zIndex: "9999", background: "#000" });
          c2.getContext("2d")!.drawImage(cv, 0, 0);
          document.body.appendChild(c2);
          const t = document.createElement("img");
          t.src = cv.toDataURL("image/png");
          Object.assign(t.style, { position: "fixed", left: "880px", top: "60px", width: "300px", border: "4px solid #ff00ff" });
          document.body.appendChild(t);
          await report(`M0_TWOD ${JSON.stringify({ mirrored: [cv.width, cv.height] })}`);
        } catch (e) { await report(`M0_TWOD_FAIL ${String(e)}`); }
      }
      // 显示层自己的读数：拿 2D getImageData 从 mirror 画布上读，这是"用户实际看到的
      // 那张画布"的内容，与 GL 后备缓冲分开的第二条证据。
      if (mir) {
        const m2 = mir.getContext("2d");
        if (m2 && mir.width > 0) {
          const d = m2.getImageData(0, 0, mir.width, mir.height).data;
          let ms = 0, mn = 0;
          for (let i = 0; i < mir.width * mir.height; i++) {
            const l = (d[i * 4] + d[i * 4 + 1] + d[i * 4 + 2]) / 3;
            ms += l; if (l > 4) mn++;
          }
          const mr = mir.getBoundingClientRect();
          back.mirrorDims = [mir.width, mir.height];
          back.mirrorCss = [+mr.width.toFixed(1), +mr.height.toFixed(1)];
          back.mirrorMean = +(ms / (mir.width * mir.height)).toFixed(2);
          back.mirrorNonBlack = +(mn / (mir.width * mir.height)).toFixed(4);
        } else {
          back.mirrorFail = "no 2d ctx";
        }
      }
      // 对比按钮的真窗口自证：把强度拉到最大（半径也拉大，让差异看得见），然后真的对
      // 那个按钮派发 pointerdown/pointerup——走的是 cmpOn/cmpOff 同一条 React 处理链，
      // 不是另开一条测试通路。外部在 HELD 与 RELEASED 两段各截一张图，比对视口像素：
      // 两张一样就说明按钮没作用，这里必须让它红。
      if (/cmp/.test(env.viewport_probe)) {
        const btn = Array.from(document.querySelectorAll("button"))
          .find((b) => (b.textContent ?? "").trim() === t("retouch.compare")) as HTMLButtonElement | undefined;
        await report(`M0_CMP_ARMED ${JSON.stringify({ found: !!btn, disabled: !!btn?.disabled })}`);
        if (btn) {
          await setStrength(1.0, { radius: 40 }).catch(() => undefined);
          await sleep(600);
          btn.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, pointerId: 7, isPrimary: true }));
          await report("M0_CMP_HELD");            // 外部：这一拍截"原图"
          await sleep(3200);
          btn.dispatchEvent(new PointerEvent("pointerup", { bubbles: true, pointerId: 7, isPrimary: true }));
          await report("M0_CMP_RELEASED");        // 外部：这一拍截"修好的图"
          await sleep(1600);
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
        tag: env.viewport_probe, hasCanvas: !!cv, hasGL: !!gl, importBtn,
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
      if (!env) return;
      // 渲染/显示配置与"跑不跑靶"无关，必须先读、再管 spec。原来这整段挂在
      // `if (!env || !spec) return` 之后，于是静态探针臂里 LRT_NO_CTX / LRT_NO_MIRROR /
      // LRT_GL_VISIBLE **全是死的**：我拿"两臂读数完全一致"当成 desynchronized 假设被
      // 证伪，而实际上那两臂根本没换过配置。开关不生效比开关不存在更危险——它会产出
      // 一份看起来像对照实验、其实什么都没有做的结论。
      const known = ["raw", "bitmap", "pingpong"] as const;
      if ((known as readonly string[]).includes(env.upload)) {
        setUpload(env.upload as (typeof known)[number]);
      }
      // ctx 属性无可复现收益（两轮背靠背：1/5 vs 3/5 vs 3/5 撞帧，均在 ±3fps 噪声内），
      // 故默认关；保留 LRT_NO_CTX / 开关只做后续对照实验用。
      setCtxOpt(env.no_ctx === "0");
      setMirrorOn(env.no_mirror !== "1");
      setGlVisible(env.gl_visible === "1");
      setChunks(env.chunks > 1 ? env.chunks : 1);
      const spec = env.auto_bench;
      if (!spec) {
        // 门还是那道门（起靶必须先于任何臂），但**过不了门要自己报**。1.6.0 那一轮
        // 第 7 臂就是撞在这里：脚本忘传 LRT_AUTO_BENCH，整条自动序列一声不响地
        // return，外面只能等满 900 s 拿到一句"没跑完"——静默的失败比失败更坏。
        const wanted = (["auto_pick", "auto_filmstrip", "auto_face", "auto_history",
          "auto_export", "auto_background", "auto_local_color", "auto_grade",
          "auto_manual"] as const)
          .filter((k) => !!(env as unknown as Record<string, string>)[k]);
        if (wanted.length) {
          await report("M0_ERROR 自动序列没起跑：这些臂挂了，但整段序列要求 LRT_AUTO_BENCH "
            + "先过门（缺它=静默 return）：" + wanted.join(","));
        }
        return;
      }
      // WebKit 会节流不可见/未聚焦窗口的 rAF，跑靶前必须把窗口拉到前台
      await getCurrentWindow().setFocus().catch(() => undefined);
      const skipPixels = env.skip_pixels === "1";
      // tier0 连像素都不传，上传/绘制自然没得做
      setSkipDraw(env.skip_draw === "1" || skipPixels);
      setTierLabel(skipPixels ? "tier0" : env.skip_draw === "1" ? "tier1" : "tier2");
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
            // COLOR-004：作用域与区域格数也进这一行——真窗口那一臂要能看见“落笔之后
            // 引擎自己把 scope 切成了 brush”，而不是只看见画面动了。
            scope: got.grade_scope, scopes: got.grade_scopes, maskPx: got.mask_px,
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
      // 局部调色（COLOR-004）自动通道（$LRT_AUTO_LOCAL_COLOR="fx:fy:r:dh:ds:dv"）。
      // 真窗口这一臂要同时证三件事：runGrade 的 mask/set 两个新 action 在 Tauri 签名上
      // 递得到（错一个名字会被静默丢掉，屏不动而一个错也不报）；引擎落笔就把作用域切成
      // brush；而**区域外那一圈逐字节没动**。最后一条只能拿用户看见的那一帧量——屏上
      // 没有第二块画布可比，而“局部调色静默变成全图调色”恰恰是画面在变、人分不出来的那种错。
      if (env.auto_local_color) {
        const nums = env.auto_local_color.split(":").map(Number);
        if (nums.length !== 6 || !nums.every(Number.isFinite)) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_LOCAL_COLOR=${env.auto_local_color}（要 fx:fy:r:dh:ds:dv）`);
        } else if (!image) {
          await report("M0_ERROR LRT_AUTO_LOCAL_COLOR 需要 LRT_LOAD_IMAGE（不知道代理帧尺寸）");
        } else {
          const [fx, fy, r, dh, ds, dv] = nums;
          const pw = image.w;
          const ph = image.h;
          const waitGrade = async (pred: (v: GradeInfo) => boolean) => {
            // 轮询预算 12 s：与修容那臂同一条理由——被拒时长时间空轮询会冻住 UI 线程，
            // 把“脚本写错参数”变成一个看着像产品退化的 fps 数字
            for (let i = 0; i < 120; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.grade && pred(st.grade)) return st.grade;
            }
            return null;
          };
          const before = await peek();
          let bad = "";
          let lit: GradeInfo | null = null;
          try {
            await runGrade("mask", { rle: clickRle(pw, ph, fx * pw, fy * ph, r),
                                     feather: 2, mode: "replace" });
            lit = await waitGrade((v) => v.grade_scope === "brush" && v.mask_px > 0);
            if (!lit) bad = "落笔后 12s 内没等到作用域为 brush 的 grade_done";
            if (!bad) {
              await runGrade("set", { dh, ds, dv, amount: 1 });
              lit = await waitGrade((v) => v.grade_lit === true) ?? lit;
            }
          } catch (e) { bad = String(e); }
          const after = await peek();
          // 两份快照得是同一块完整画布才能逐格比：脏矩形只送顶部几行，拿它比字节
          // 比出来的是“没送到”而不是“没变”（上一轮切文档那一臂就报过 -1）
          const full = (f: typeof before) => !!f && f.rows === f.h && f.pixelLen === f.w * f.h * 4;
          let insideChanged = -1;
          let outsideChanged = -1;
          if (!bad && before && after && full(before) && full(after)
            && before.w === after.w && before.h === after.h) {
            const cx = Math.round(fx * after.w);
            const cy = Math.round(fy * after.h);
            const band = Math.round(r) + 6;   // 笔迹半径 + 羽化支撑 + 插值余量
            insideChanged = 0; outsideChanged = 0;
            for (let y = 0; y < after.h; y++) {
              for (let x = 0; x < after.w; x++) {
                const i = (y * after.w + x) * 4;
                if (after.pixels[i] === before.pixels[i]
                  && after.pixels[i + 1] === before.pixels[i + 1]
                  && after.pixels[i + 2] === before.pixels[i + 2]) continue;
                if (Math.abs(x - cx) <= band && Math.abs(y - cy) <= band) insideChanged++;
                else outsideChanged++;
              }
            }
          } else if (!bad) {
            bad = "两份快照不是同一块完整画布（脏矩形或尺寸变了），区域外逐字节那条没法量";
          }
          await report(`M0_LOCAL_COLOR ${JSON.stringify(bad ? { bad, maskPx: lit?.mask_px ?? 0 } : {
            scope: lit?.grade_scope ?? "", scopes: lit?.grade_scopes ?? [],
            maskPx: lit?.mask_px ?? 0, lit: lit?.grade_lit ?? null,
            bytesGrade: lit?.bytes_grade ?? 0, gradeMs: lit?.grade_ms ?? 0,
            canvas: `${after?.w ?? 0}x${after?.h ?? 0}`,
            insideChanged, outsideChanged,
          })}`);
        }
      }
      // 眼牙增强（LNX-PORTRAIT-009）自动通道（$LRT_AUTO_ENHANCE="sclera:iris:teeth"）。
      // 真窗口这一臂证四件事，缺一条就不叫"开箱即用"：①runEnhance → Rust enhance →
      // 引擎 enhance_done 四层签名对得上（错一个字段名会被静默丢掉，屏不动而一个错也不报，
      // 第 7 臂 auto_pick 那一记就是这么漏的）；②点火后画面按掩膜动（insideChanged>0，
      // 不是假滑块）；③**窗口外那一圈逐字节没动**（outsideChanged=0——"局部增强悄悄变成
      // 全图提亮"正是画面在变而人分不出来的那种错）；④clear 之后回到 before 逐字节
      // （backHomeBytes=0，且引擎报 bytes_enhance=0：常驻场真的放掉了，不是留着没人看）。
      if (env.auto_enhance) {
        const nums = env.auto_enhance.split(":").map(Number);
        if (nums.length !== 3 || !nums.every((n) => Number.isFinite(n) && n >= 0 && n <= 1)) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_ENHANCE=${env.auto_enhance}`
            + "（要 sclera:iris:teeth，每个 [0,1]）");
        } else if (!image) {
          await report("M0_ERROR LRT_AUTO_ENHANCE 需要 LRT_LOAD_IMAGE（不知道代理帧尺寸）");
        } else {
          const [sclera, iris, teeth] = nums;
          const waitEnh = async (pred: (v: EnhanceInfo) => boolean) => {
            // 12 s 预算与局部调色那臂同一条理由：被拒时长空轮询会冻住 UI 线程，
            // 把"脚本少传一个参数"变成一个看着像产品退化的 fps 数字
            for (let i = 0; i < 120; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.enhance && pred(st.enhance)) return st.enhance;
            }
            return null;
          };
          const before = await peek();
          const homePix = before?.pixels ?? null;
          let bad = "";
          let lit: EnhanceInfo | null = null;
          try {
            await runEnhance("set", { sclera, iris, teeth });
            lit = await waitEnh((v) => v.lit === true);
            if (!lit) bad = "点火后 12s 内没等到 lit=true 的 enhance_done";
            else {
              // 命中事件那一格可能正好在两次渲染之间（`enhance_ms` 量的是"最近一次渲染里
              // 这一层的耗时"，读到 0 不等于"不要钱"，等于没量到）。等一小段再取一次，
              // 拿到的才是用户在拖滑块时真付的那一份代价。
              await sleep(250);
              const st2 = await engineStatus().catch(() => null);
              if (st2?.enhance?.lit === true) lit = st2.enhance;
            }
          } catch (e) { bad = String(e); }
          const after = await peek();
          // 两份快照得是同一块完整画布才能逐格比：脏矩形只送顶部几行
          const full = (f: typeof before) => !!f && f.rows === f.h && f.pixelLen === f.w * f.h * 4;
          let insideChanged = -1;
          let outsideChanged = -1;
          if (!bad && before && after && full(before) && full(after)
            && before.w === after.w && before.h === after.h) {
            // 窗口取引擎报的那一片画布坐标 (y0,x0,fh,fw)，不是脚本自己按脸盒估的框：
            // "这一层只在自己那只窗口里逐点乘加"这条承诺的实现就是这个数
            const win = lit?.enhance_window ?? null;
            if (!win) {
              bad = "enhance_window 为 null：场没挂上，窗口内外两条没法量";
            } else {
              const wy = Math.round(win[0]), wx = Math.round(win[1]);
              const wh = Math.round(win[2]), ww = Math.round(win[3]);
              insideChanged = 0; outsideChanged = 0;
              for (let y = 0; y < after.h; y++) {
                for (let x = 0; x < after.w; x++) {
                  const i = (y * after.w + x) * 4;
                  if (after.pixels[i] === before.pixels[i]
                    && after.pixels[i + 1] === before.pixels[i + 1]
                    && after.pixels[i + 2] === before.pixels[i + 2]) continue;
                  if (y >= wy && y < wy + wh && x >= wx && x < wx + ww) insideChanged++;
                  else outsideChanged++;
                }
              }
            }
          } else if (!bad) {
            bad = "两份快照不是同一块完整画布（脏矩形或尺寸变了），窗口外逐字节那条没法量";
          }
          // 关掉那层：回到 before 逐字节。这一条只在①②③都量完之后才跑，因为它会把
          // 场放掉——先取完账再放，反过来就只能拿到一份空账
          let backHomeBytes = -2;
          if (!bad) {
            try {
              await runEnhance("clear");
              const off = await waitEnh((v) => v.lit === false && v.bytes_enhance === 0);
              if (!off) {
                bad = "clear 后 12s 内没等到「enhance_lit=false 且 bytes_enhance=0」那一格";
              } else {
                const home2 = await peek();
                backHomeBytes = (home2 && full(home2) && home2.w === before!.w && home2.h === before!.h)
                  ? diffBytes(homePix, home2.pixels) : -1;
              }
            } catch (e) { bad = `clear 那一臂炸了：${e}`; }
          }
          await report(`M0_ENHANCE ${JSON.stringify(bad ? {
            bad, gatedPx: lit?.gated_px ?? {}, window: lit?.enhance_window ?? null,
          } : {
            amounts: lit?.amounts ?? {}, lit: lit?.lit ?? null,
            gatedPx: lit?.gated_px ?? {}, geomPx: lit?.enhance_geom_px ?? {},
            reason: lit?.enhance_reason ?? {}, window: lit?.enhance_window ?? [],
            device: lit?.device ?? "", bytesEnhance: lit?.bytes_enhance ?? 0,
            enhanceMs: lit?.enhance_ms ?? 0, buildMs: lit?.enhance_build_ms ?? 0,
            mouthOpenness: (lit?.enhance_mouth ?? {}).openness ?? null,
            canvas: `${after?.w ?? 0}x${after?.h ?? 0}`,
            insideChanged, outsideChanged, backHomeBytes,
          })}`);
        }
      }
      // 人工纠正优先（LNX-PORTRAIT-006）自动通道（$LRT_AUTO_MANUAL=<要关掉的 index>）。
      // 库里那 20 条与端到端那两条连的是裸引擎；这一臂证的是同一份账走完
      // 视口 → Rust `face` → 引擎 → 宿主 `status.face` 这四层之后**仍是那一条账**，
      // 并且"关掉的那一位在重检测后的那一帧上不得重新出现"能在用户看见的那一帧上量出来
      // ——屏幕上没有第二块画布可比，这一条只能真窗口量。
      if (env.auto_manual) {
        const want = Number(env.auto_manual);
        if (!Number.isInteger(want) || want < 0) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_MANUAL=${env.auto_manual}（要一个非负整数 index）`);
        } else if (!image) {
          await report("M0_ERROR LRT_AUTO_MANUAL 需要 LRT_LOAD_IMAGE + LRT_PRECOMPUTE"
            + "（多人夹具：名单只能来自真实分析）");
        } else {
          const pw = image.w;
          const ph = image.h;
          const full = (f: any) => !!f && f.rows === f.h && f.pixelLen === f.w * f.h * 4;
          const waitFace = async (pred: (v: NonNullable<ReturnType<typeof faceStateOf>>) => boolean) => {
            // 12 s 预算与眼牙那一臂同一条理由：长空轮询会冻住 UI 线程，把"脚本少传一个
            // 参数"变成一个看着像产品退化的 fps 数字
            for (let i = 0; i < 120; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              const v = faceStateOf(st, st?.doc_report?.doc_state ?? null);
              if (v && pred(v)) return v;
            }
            return null;
          };
          /** 那一圈脸盒内芯（缩 25%）里有多少格被改动：逐字节判据的计数方式与端到端同源 */
          const changedIn = (a: Uint8Array | null, b: Uint8Array | null, box: number[] | null) => {
            if (!a || !b || !box || a.length !== b.length) return -1;
            const [x0, y0, x1, y1] = box;
            const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
            const hx = (x1 - x0) / 2 * 0.75, hy = (y1 - y0) / 2 * 0.75;
            let n = 0;
            for (let y = 0; y < ph; y++) {
              for (let x = 0; x < pw; x++) {
                if (Math.abs(x / pw - cx) > hx || Math.abs(y / ph - cy) > hy) continue;
                const i = (y * pw + x) * 4;
                if (a[i] !== b[i] || a[i + 1] !== b[i + 1] || a[i + 2] !== b[i + 2]) n++;
              }
            }
            return n;
          };
          let bad = "";
          let f1: ReturnType<typeof faceStateOf> = null;
          let f2: ReturnType<typeof faceStateOf> = null;
          let f3: ReturnType<typeof faceStateOf> = null;
          let roster0 = 0, other = -1, dfLit: boolean | null = null;
          let keptCore = -1, redetectCore = -1, errRefused = "";
          let rectTakenByEngine = false, rectErrText = "";
          try {
            const st0 = await engineStatus().catch(() => null);
            const f0 = faceStateOf(st0, st0?.doc_report?.doc_state ?? null);
            roster0 = f0?.faces.length ?? 0;
            other = f0?.faces.find((x) => x.index !== want)?.index ?? -1;
            if (!f0 || roster0 <= want || other < 0) {
              bad = `名单里只有 ${roster0} 个人：这一臂要的是多人夹具（要能关掉一位、留下另一位）`;
            }
            if (!bad) {
              await runFace("select", other);
              if (!(await waitFace((v) => v.explicit === true && v.index === other))) {
                bad = `选定人物 ${other} 之后 12s 内没等到 explicit 的 face 状态`;
              }
            }
            if (!bad) {
              await runDeform("set", { slim_face: 0.6 });
              for (let i = 0; i < 90; i++) {
                await sleep(100);
                const st = await engineStatus().catch(() => null);
                if (st?.deform?.lit === true) { dfLit = true; break; }
                dfLit = st?.deform?.lit ?? null;
              }
              if (!dfLit) bad = "推了留下那一位的形变而 9s 内没等到 lit=true";
            }
            if (!bad) {
              const errBefore = (await engineStatus().catch(() => null))?.last_error ?? "";
              const before = await peek();
              await runFace("disable", want);
              f1 = await waitFace((v) => (v.manual?.disabled?.length ?? 0) >= 1);
              if (!f1) bad = "关掉那一只之后 12s 内没等到带人工禁用账的 face 状态";
              else {
                const flags = f1.faces.filter((x) => x.index === want).map((x) => !!x.disabled);
                if (!flags.length || !flags[0]) bad = `被关那一只没标 disabled：${JSON.stringify(f1.faces)}`;
                if (f1.enabled?.includes(want)) bad = "被关那一只仍出现在可编辑名单里";
                // 人工账不许把"这一轮分析是多人图"这个原始事实抹掉（SCOPE-001 的 P0 判据读它）
                if (f1.scope_block !== "multi_face") bad = `禁用抹掉了多人事实：${f1.scope_block}`;
                const after = await peek();
                if (before && after && full(before) && full(after)) {
                  const box = f1.faces.find((x) => x.index === want)?.box ?? null;
                  keptCore = changedIn(before.pixels, after.pixels, box);
                  if (keptCore !== 0) bad = `关掉那一只改动了画面（${keptCore} 格）：选人与账不该动像素`;
                } else bad = "关掉前后不是同一块完整画布，逐格判据没法量";
              }
              // 明拒那一条：被禁的那一只不许再被选定，而拒绝必须走得到宿主（error 事件）
              await runFace("select", want);
              for (let i = 0; i < 40 && !errRefused; i++) {
                await sleep(100);
                const st = await engineStatus().catch(() => null);
                const e = st?.last_error ?? "";
                if (e && e !== errBefore && e.includes("已被人工禁用")) errRefused = e;
              }
              if (!errRefused) bad = bad || "选定被禁那一只没等到『已被人工禁用』的拒绝到达宿主";
              // 后台重检测：账要在、画面里那一圈不许出现他的东西
              const preRedetect = await peek();
              await runPrecompute({ backend: "mediapipe" });
              f2 = await waitFace((v) => (v.manual?.disabled?.length ?? 0) >= 1
                && v.faces.some((x) => x.index === want && x.disabled));
              if (!f2) bad = bad || "重检测后没等到「那一只仍是关着的」那份状态：静默恢复";
              const postRedetect = await peek();
              if (f2 && preRedetect && postRedetect && full(preRedetect) && full(postRedetect)) {
                const box = f2.faces.find((x) => x.index === want)?.box ?? null;
                redetectCore = changedIn(preRedetect.pixels, postRedetect.pixels, box);
                if (redetectCore !== 0) {
                  bad = `重检测后被禁那一只的内芯动了 ${redetectCore} 格：那层的几何悄悄活了回来`;
                }
              } else if (f2) bad = bad || "重检测前后不是同一块完整画布：逐格判据落不了地";
              // 恢复：账清空才算"人工判断可以被人推翻"
              await runFace("enable", want);
              f3 = await waitFace((v) => (v.manual?.disabled?.length ?? 0) === 0);
              if (!f3) bad = bad || "恢复那一只之后 12s 内账没清空";
              // rect 这一格必须在装机壳里也走得通：视口 → Rust `face`(rect) → 引擎。上一轮
              // auto_pick 就是漏在桥那一格（TS 发了，Rust 的签名里没这一项，引擎收到的永远是
              // 空的）。判据用**两条拒绝文案的差别**，不必再造一张漏检夹具：rect 被桥丢了，引擎
              // 说的是「face add 要给归一化矩形」；rect 到了而框里已有人，说的是「这一框里已经
              // 有脸了」。差一句话，正好把丢参数这件事量出来。
              const errBeforeAdd = (await engineStatus().catch(() => null))?.last_error ?? "";
              const boxProbe = f3?.faces.find((x) => x.index === other)?.box ?? null;
              if (!boxProbe) {
                bad = bad || "补框那一臂没拿到可发的 rect（名单里没有留下那一位的脸盒）";
              } else {
                await runFace("add", undefined, boxProbe);
                for (let i = 0; i < 40 && !rectTakenByEngine; i++) {
                  await sleep(100);
                  const e = (await engineStatus().catch(() => null))?.last_error ?? "";
                  if (e && e !== errBeforeAdd) {
                    rectErrText = e.slice(0, 140);
                    rectTakenByEngine = e.includes("已经有脸了");
                  }
                }
                if (!rectTakenByEngine) {
                  bad = bad || `face add 的 rect 没走到引擎（宿主收到的是「${rectErrText}」）`;
                }
              }
            }
          } catch (e) { bad = `臂内异常：${e}`; }
          await report(`M0_MANUAL ${JSON.stringify(bad ? {
            bad, roster: roster0, keptCore, redetectCore, errRefused: !!errRefused,
            rectReachedEngine: rectTakenByEngine, rectErr: rectErrText,
            disabledLedger: f1?.manual?.disabled?.length ?? -1,
          } : {
            roster: roster0, kept: other, refused: want,
            disabledLedger: f3?.manual?.disabled?.length ?? -1,
            enabledAfterEnable: f3?.enabled?.length ?? -1,
            scopeBlock: f1?.scope_block ?? null, preview: f1?.manual?.preview ?? "",
            keptCore, redetectCore, refusedReachedHost: !!errRefused,
            rectReachedEngine: rectTakenByEngine, rectErr: rectErrText,
            deformLit: dfLit, canvas: `${pw}x${ph}`,
          })}`);
        }
      }
      // 分人编辑（LNX-PORTRAIT-003）自动通道（$LRT_AUTO_FACE=<要选的 index>）。
      // 库里那九段判据连的是裸引擎，中间隔着 Rust 的 face 命令与宿主的状态搬运——那两层
      // 只有真窗口能证明。这一臂量四件事：①未选定就推形变，引擎整条拒（SCOPE-001）而画面
      // 一格没动（不许留半截状态）；②runFace → face_selected → status.face 落回宿主；
      // ③选定本身不改画面（选人不等于调图）；④推完形变之后**没被选中的那一圈逐字节没动**。
      // 第④条只能拿用户看见的那一帧量：屏幕上没有第二块画布可比。
      if (env.auto_face) {
        const want = Number(env.auto_face);
        if (!Number.isInteger(want) || want < 0) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_FACE=${env.auto_face}（要一个非负整数 index）`);
        } else if (!image) {
          await report("M0_ERROR LRT_AUTO_FACE 需要 LRT_LOAD_IMAGE + LRT_PRECOMPUTE"
            + "（多人夹具：先解图再分析，名单只能来自真实分析）");
        } else {
          const pw = image.w;
          const ph = image.h;
          const full = (f: any) => !!f && f.rows === f.h && f.pixelLen === f.w * f.h * 4;
          let bad = "";
          let numFaces = 0;
          let blockedBefore: boolean | null = null;
          let pickSource = "";
          let changedBySelect = -1;
          let insideChanged = -1;
          let outsideChanged = -1;
          let df: DeformInfo | null = null;
          const st0 = await engineStatus().catch(() => null);
          const f0 = faceStateOf(st0, st0?.doc_report?.doc_state ?? null);
          numFaces = f0?.faces.length ?? 0;
          blockedBefore = f0?.blocked ?? null;
          const errBefore = st0?.last_error ?? "";
          const base = await peek();
          // ① 未选定就推形变：期待一条引擎的拒绝，而画面一格不许动
          try {
            await runDeform("set", { slim_face: 0.6, big_eye: 0.3, small_chin: 0 });
          } catch (e) { bad = `runDeform 抛错（未选定那一臂）: ${e}`; }
          let errAfter = "";
          for (let i = 0; i < 120 && !bad; i++) {
            await sleep(100);
            const st = await engineStatus().catch(() => null);
            const e = st?.last_error ?? "";
            if (e && e !== errBefore) { errAfter = e; break; }
          }
          if (!bad && !errAfter) bad = "12s 内没等到引擎拒绝未选定时的形变（SCOPE-001 那条没落）";
          if (!bad && !errAfter.includes("face select")) {
            bad = `拒绝没给出路（文案里该有 face select）：${errAfter.slice(0, 120)}`;
          }
          const afterReject = await peek();
          const rejectDiff = (base && afterReject && full(base) && full(afterReject)
            && base.w === afterReject.w && base.h === afterReject.h)
            ? diffBytes(base.pixels, afterReject.pixels) : -1;
          if (!bad && rejectDiff !== 0) {
            bad = `被拒之后画面还动了 ${rejectDiff} 字节（或快照不可比）：拒绝不许留半截状态`;
          }
          // ② 用户点选那一张：答复要落进宿主那一个槽位
          if (!bad) {
            try {
              await runFace("select", want);
            } catch (e) { bad = `runFace 抛错: ${e}`; }
            for (let i = 0; i < 200 && !bad; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.face?.source === "face_selected" && st.face.face.explicit
                && st.face.face.index === want) { pickSource = st.face.source; break; }
            }
            if (!bad && !pickSource) bad = `20s 内 face_selected 没落进宿主的 status.face（want=${want}）`;
          }
          // ③ 选定不改画面：选人是「换个服务对象」，不是「调了一次图」
          const afterSelect = bad ? null : await peek();
          if (!bad) {
            changedBySelect = (afterReject && afterSelect && full(afterReject) && full(afterSelect))
              ? diffBytes(afterReject.pixels, afterSelect.pixels) : -1;
            if (changedBySelect !== 0) {
              bad = `点选人物就改了画面 ${changedBySelect} 字节：选人不等于调图`;
            }
          }
          // ④ 选定之后再推同样的三个数：这一回要建层、要出帧
          if (!bad) {
            try {
              await runDeform("set", { slim_face: 0.6, big_eye: 0.3, small_chin: 0 });
            } catch (e) { bad = `runDeform 抛错（已选定那一臂）: ${e}`; }
            for (let i = 0; i < 200 && !bad; i++) {
              await sleep(100);
              const st = await engineStatus().catch(() => null);
              if (st?.deform && st.deform.lit && st.deform.action === "set") { df = st.deform; break; }
            }
            if (!bad && !df) bad = "选定后 20s 内没等到点火的 deform_done";
          }
          const after = bad ? null : await peek();
          const stF = await engineStatus().catch(() => null);
          const fF = faceStateOf(stF, null);
          const box = fF?.faces.find((x) => x.index === want)?.box ?? null;
          if (!bad && after && afterReject && full(after) && full(afterReject)
            && after.w === afterReject.w && after.h === afterReject.h && box && box.length === 4) {
            // 与 ADR-0009 同一个口径：TPS 是紧支撑窗，实测最远变化落在 1.58× 脸半对角，
            // 所以「没被选中的那一圈」取 1.6R 之外——那里必须一格不动。
            const cx = ((box[0] + box[2]) / 2) * after.w;
            const cy = ((box[1] + box[3]) / 2) * after.h;
            const r = 0.5 * Math.hypot((box[2] - box[0]) * after.w, (box[3] - box[1]) * after.h);
            const lim = 1.6 * r;
            insideChanged = 0; outsideChanged = 0;
            for (let y = 0; y < after.h; y++) {
              for (let x = 0; x < after.w; x++) {
                const i = (y * after.w + x) * 4;
                if (after.pixels[i] === afterReject.pixels[i]
                  && after.pixels[i + 1] === afterReject.pixels[i + 1]
                  && after.pixels[i + 2] === afterReject.pixels[i + 2]) continue;
                if (Math.hypot(x - cx, y - cy) <= lim) insideChanged++; else outsideChanged++;
              }
            }
          } else if (!bad) {
            bad = "两份快照不是同一块完整画布或缺脸盒：另一张脸那一圈没法量";
          }
          await report(`M0_FACE ${JSON.stringify(bad ? { bad, numFaces, want } : {
            numFaces, want, blockedBefore, pickSource, changedBySelect,
            canvas: `${after?.w ?? 0}x${after?.h ?? 0}`, proxy: `${pw}x${ph}`,
            backend: df?.landmark_backend ?? "", built: df?.built ?? null,
            bytesDeform: df?.bytes_deform ?? 0, deformMs: df?.deform_ms ?? 0,
            supportShare: df?.support_share ?? 0, insideChanged, outsideChanged,
          })}`);
        }
      }
      // 层级覆盖与继承（LNX-PORTRAIT-004）自动通道：跟着 LRT_AUTO_FACE 一起点火。
      // 库里那八段判据连的是裸引擎；这一段证的是 runDeform(…, scope) → Rust deform
      // 的第三个参数 → 引擎 deform_done 的 scope/overrides 那几格 → 宿主轮询状态 →
      // 用户看见的那一帧。中间每一层都只有真窗口能证明。
      // 前置：上面那一臂已在这张多人图上选定 want 号，并把全人物默认落成 {0.6, 0.3, 0}。
      if (env.auto_face) {
        const wantL = Number(env.auto_face);
        const fullL = (f: any) => !!f && f.rows === f.h && f.pixelLen === f.w * f.h * 4;
        let lbad = "";
        let personDone: DeformInfo | null = null;
        let defaultDone: DeformInfo | null = null;
        let inheritDone: DeformInfo | null = null;
        let insideChangedL = -1;
        let otherChangedL = -1;
        let sameLayerBytes = -1;
        // 等一条符合判据的 deform_done：不能只看 action，"覆盖了没"只有层级那几格说得出
        const waitDeform = async (ok: (d: DeformInfo | null) => boolean, why: string) => {
          for (let i = 0; i < 200; i++) {
            await sleep(100);
            const st = await engineStatus().catch(() => null);
            if (st && ok(st.deform ?? null)) return st.deform;
          }
          lbad = `20s 内没等到${why}`;
          return null;
        };
        // ① a) 先把默认改成 slim 0.2（此时还没有任何覆盖）→ 这一幅就是"纯默认"的参照
        if (!lbad) {
          try { await runDeform("set", { slim_face: 0.2 }, "all"); }
          catch (e) { lbad = `runDeform(scope=all) 抛错: ${e}`; }
        }
        const fDefault = lbad ? null : await waitDeform(
          (d) => !!d && d.action === "set" && d.scope === "all"
            && Math.abs((d.amounts?.slim_face ?? 9) - 0.2) < 1e-6,
          "到 scope=all 的默认变更");
        const base = lbad ? null : await peek();
        // ① b) 只给这一张挂覆盖（big_eye 0.9）：引擎必须报出 scope=person 与那一格名单
        if (!lbad) {
          try { await runDeform("set", { big_eye: 0.9 }, "person"); }
          catch (e) { lbad = `runDeform(scope=person) 抛错: ${e}`; }
        }
        if (!lbad) {
          personDone = await waitDeform(
            (d) => !!d && d.action === "set" && d.scope === "person"
              && (d.overridden_kinds ?? []).includes("big_eye") && d.inherited === false,
            "scope=person 的覆盖账（overridden_kinds/inherited）");
        }
        const litL = lbad ? null : await peek();
        if (!lbad && !personDone) lbad = lbad || "没等到 scope=person 那一笔的帧";
        // ② 挂覆盖只许动被选中那一张：与 ADR-0009 同一个口径（1.6× 脸半对角之外必须不动）
        if (!lbad && base && litL && fullL(base) && fullL(litL)
          && base.w === litL.w && base.h === litL.h) {
          const stF = await engineStatus().catch(() => null);
          const fF = faceStateOf(stF, null);
          const box = fF?.faces.find((x) => x.index === wantL)?.box ?? null;
          if (box && box.length === 4) {
            const cx = ((box[0] + box[2]) / 2) * litL.w;
            const cy = ((box[1] + box[3]) / 2) * litL.h;
            const r = 0.5 * Math.hypot((box[2] - box[0]) * litL.w, (box[3] - box[1]) * litL.h);
            const lim = 1.6 * r;
            insideChangedL = 0; otherChangedL = 0;
            for (let y = 0; y < litL.h; y++) {
              for (let x = 0; x < litL.w; x++) {
                const i = (y * litL.w + x) * 4;
                if (litL.pixels[i] === base.pixels[i] && litL.pixels[i + 1] === base.pixels[i + 1]
                  && litL.pixels[i + 2] === base.pixels[i + 2]) continue;
                if (Math.hypot(x - cx, y - cy) <= lim) insideChangedL++; else otherChangedL++;
              }
            }
          } else {
            lbad = `选定那一张没有脸盒（index=${wantL}）：作用面没法量`;
          }
        }
        // ③ 再改默认（slim 0.2→0.6）：覆盖那一格必须继续是 0.9，未覆盖那格跟到 0.6
        if (!lbad) {
          try { await runDeform("set", { slim_face: 0.6 }, "all"); }
          catch (e) { lbad = `runDeform(改默认) 抛错: ${e}`; }
        }
        if (!lbad) {
          defaultDone = await waitDeform(
            (d) => !!d && d.action === "set" && d.scope === "all"
              && Math.abs((d.amounts?.big_eye ?? 9) - 0.9) < 1e-6
              && Math.abs((d.amounts?.slim_face ?? 9) - 0.6) < 1e-6,
            "覆盖项继续生效而默认那格跟随（big_eye 0.9 / slim 0.6）");
        }
        // ④ 恢复继承：合成必须落回默认，且画面逐字节等于"两条路径走到同一个层级状态"的另一幅
        if (!lbad) {
          try { await runDeform("inherit"); }
          catch (e) { lbad = `runDeform(inherit) 抛错: ${e}`; }
        }
        if (!lbad) {
          inheritDone = await waitDeform(
            (d) => !!d && d.action === "inherit" && (d.overridden_kinds ?? []).length === 0
              && d.inherited === true && Math.abs((d.amounts?.big_eye ?? 9) - 0.3) < 1e-6,
            "恢复继承后全按层级合成（覆盖名单空、big_eye 回到默认 0.3）");
        }
        const fInherit = lbad ? null : await peek();
        // 另一条路径回到同一个层级状态：再挂一次覆盖（同值）然后再次 inherit。
        // 同一组默认 + 同一份"没有覆盖" → 像素必须逐字节相同，否则合成不是单一出处
        if (!lbad) {
          try { await runDeform("set", { big_eye: 0.95 }, "person"); }
          catch (e) { lbad = `runDeform(第二次覆盖) 抛错: ${e}`; }
        }
        if (!lbad) {
          const again = await waitDeform(
            (d) => !!d && d.scope === "person" && (d.overridden_kinds ?? []).includes("big_eye"),
            "第二次覆盖的账");
          if (again) {
            try { await runDeform("inherit"); }
            catch (e) { lbad = `runDeform(第二次 inherit) 抛错: ${e}`; }
          }
        }
        if (!lbad) {
          await waitDeform((d) => !!d && d.action === "inherit" && d.inherited === true,
            "第二次恢复继承");
        }
        const fAgain = lbad ? null : await peek();
        if (!lbad && fInherit && fAgain && fullL(fInherit) && fullL(fAgain)
          && fInherit.w === fAgain.w && fInherit.h === fAgain.h) {
          sameLayerBytes = diffBytes(fInherit.pixels, fAgain.pixels);
        }
        await report(`M0_LAYER ${JSON.stringify(lbad ? { bad: lbad, want: wantL } : {
          want: wantL,
          defaultFirst: fDefault?.amounts ?? {},
          personScope: personDone?.scope ?? "",
          overriddenKinds: personDone?.overridden_kinds ?? [],
          inheritedBeforeOverride: personDone?.inherited ?? null,
          defaultAmounts: personDone?.default ?? {},
          overrideAmounts: personDone?.amounts ?? {},
          keptAfterDefaultChange: defaultDone?.amounts ?? {},
          inheritAmounts: inheritDone?.amounts ?? {},
          inheritOverrideCount: (inheritDone?.overrides ?? []).length,
          insideChanged: insideChangedL, otherChanged: otherChangedL,
          sameLayerBytes,
        })}`);
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
      // 挑图建议（LNX-PICK-001）自动通道：LRT_AUTO_PICK="<重复>/<清晰>/<曝光>/<眼睛>"。
      // 引擎那半的判据已由 test_pick + 端到端用例逐条钉住；这一条要证的是宿主这四层签名
      // （runPick → Rust pick → 引擎 pick_* → status.pick），再加上只有真窗口能给的最后一层：
      // 徽章确实出现在用户看得见的 DOM 里、原因里带着数值与阈值、并且没有一处写着"删"。
      if (env.auto_pick) {
        const arms = env.auto_pick.split("/");
        if (arms.length !== 4) {
          await report(`M0_ERROR 无法解析 LRT_AUTO_PICK=${env.auto_pick}`
            + "（要 重复/清晰/曝光/眼睛 四档名）");
        } else {
          const sens = { duplicate: arms[0], blur: arms[1], exposure: arms[2], eyes: arms[3] };
          const names0 = ((await fetchFilmstrip().catch(() => null))?.session?.docs ?? [])
            .map((d) => d.name).sort();
          await runPick("analyze", { ...sens, force: true });
          let run: PickRun | null = null;
          let err: string | null = null;
          for (let i = 0; i < 900; i++) {
            await sleep(200);
            const st = await engineStatus().catch(() => null);
            if (st?.last_error) { err = st.last_error; break; }
            if (st?.pick && (st.pick.event === "pick_done" || st.pick.event === "pick_state")) {
              run = st.pick;
              break;
            }
          }
          await sleep(300);
          const st2 = await engineStatus().catch(() => null);
          const fs = await fetchFilmstrip().catch(() => null);
          const docs = fs?.session?.docs ?? [];
          const withPick = docs.filter((d) => d.pick);
          const labelCount: Record<string, number> = {};
          for (const d of withPick) {
            for (const l of d.pick?.labels ?? []) labelCount[l] = (labelCount[l] ?? 0) + 1;
          }
          const badges = Array.from(document.querySelectorAll(".strip .cell .badge.pk"))
            .map((el) => (el.textContent ?? "").trim());
          await report(`M0_PICK_RESULT ${JSON.stringify({
            sens, event: run?.event ?? null, err,
            targets: run?.targets ?? null, measured: run?.measured ?? null,
            failed: run?.failed ?? null, stopped: run?.stopped ?? null,
            groupSizes: (run?.groups ?? []).map((g) => g.size),
            fingerprint: run?.fingerprint ?? null, algo: run?.algo ?? null,
            // 两条独立通道来自装机引擎自己：握手 ready 里那份判据指纹与这次事件里那份。
            // 不相等就是"跑靶读到的判据不是壳握手时承诺的那一版"（发布自证要的就是这一句）
            readyFingerprint: st2?.ready_caps?.pick_fingerprint ?? null,
            readyAlgo: st2?.ready_caps?.pick_algo ?? null,
            readyArms: st2?.ready_caps?.pick_sensitivities ?? null,
            eyesBackend: run?.eyes_backend ?? null, eyesError: run?.eyes_error ?? null,
            batchMedian: run?.batch_median_ratio ?? null, edge: run?.edge ?? null,
            measureMs: run?.measure_ms ?? null, totalMs: run?.total_ms ?? null,
            pickItems: st2?.pick_items ?? -1, cells: docs.length, withPick: withPick.length,
            names0, namesNow: docs.map((d) => d.name).sort(), labels: labelCount,
            badges,
            // 冻结件那两句在宿主这一层的形状：可覆盖 / 不自动删除（引擎恒假，UI 不许改写）
            overridableAll: withPick.every((d) => d.pick?.overridable === true),
            autoDeleteAny: withPick.some((d) => d.pick?.auto_deleted === true
              || d.pick?.auto_trashed === true),
            overridden: withPick.filter((d) => d.pick?.overridden_by_user === true).length,
            reasonsArmed: withPick.every((d) => (d.pick?.reasons ?? []).length === 0
              || (d.pick?.reasons ?? []).every((r) => !!r.method
                && r.value !== undefined && r.threshold !== undefined)),
            deleteWord: withPick.some((d) => (d.pick?.reasons ?? [])
              .some((r) => (r.text ?? "").includes("删"))),
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
    // 每个后缀给大小写两份模式。GTK 的过滤器模式在 Unix 上**大小写敏感**：实测
    // GLib.pattern_match_simple("*.cr2", "IMG.cr2") = True，而 "IMG.CR2" = False。
    // 相机产出的后缀全是大写（佳能 .CR2 / 尼康 .NEF / 索尼 .ARW），于是这一栏过去
    // 把 RAW 整个藏起来——而引擎那边是 ext.lower() 判断，路径给得到就收：
    // 唯一挡路的正是这个框。字符类写法 *.[Cc][Rr]2 在这条匹配器上不通，别试。
    const patterns = exts
      ? Array.from(new Set(exts.flatMap((e) => [e.replace(/^\./, ""), e.replace(/^\./, "").toUpperCase()])))
      : undefined;
    let sel: string | null;
    try {
      sel = await openDialog({ multiple: false, directory: dir,
        ...(patterns ? { filters: [{ name: dir ? "目录" : "图片 / RAW", extensions: patterns }] } : {}) });
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

  /** 对比：按住=临时出一帧原图，松开=回到修好的那一版。
   *  走引擎的 compare 而不是 set_strength(0)：会话强度不动、撤销栈不占步，
   *  松手后滑块位置与画面都还是用户离开时那一版。 */
  async function cmpOn(e: React.PointerEvent<HTMLButtonElement>) {
    if (!pid || comparingRef.current) return;
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* 拿不到捕获不影响对比 */ }
    comparingRef.current = true;
    setComparing(true);
    await setCompare(true).catch((err) => { setDragNote(String(err)); });
  }
  async function cmpOff() {
    if (!comparingRef.current) return;
    comparingRef.current = false;
    setComparing(false);
    await setCompare(false).catch((err) => { setDragNote(String(err)); });
  }
  // 指针在窗口外松开、或按住时切走窗口：pointerup 可能永远不来，那样画面会停在原图。
  // 所以这三条兜底不是装饰——"松开没回来"比没有对比按钮更糟。
  useEffect(() => {
    const off = () => { void cmpOff(); };
    window.addEventListener("blur", off);
    window.addEventListener("pointerup", off);
    window.addEventListener("pointercancel", off);
    return () => {
      window.removeEventListener("blur", off);
      window.removeEventListener("pointerup", off);
      window.removeEventListener("pointercancel", off);
    };
  }, [pid]);

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

  // 框选补脸：视口那一拖交出归一化框，引擎在这一框上**再跑一次真检测**（不拟合占位点位）。
  // 拒绝走 error 事件、成功走名单，两边都不在 invoke 的返回值里，所以这里等一小段再取状态：
  // 否则用户框完只看到"点了没反应"（DoD §3 明确禁止的那件事）
  const onPickFaceRect = useCallback(async (rect: number[]) => {
    setPickFace(false);
    setDragNote(t("face.adding"));
    const errBefore = (await engineStatus().catch(() => null))?.last_error ?? null;
    try {
      await runFace("add", undefined, rect);
    } catch (e) {
      setDragNote(String(e));
      return;
    }
    for (let i = 0; i < 40; i++) {
      await new Promise((r) => setTimeout(r, 250));
      const st = await engineStatus().catch(() => null);
      const err = st?.last_error ?? null;
      if (err && err !== errBefore) { setDragNote(err); return; }
      if ((st?.face?.face?.manual?.added?.length ?? 0) > 0) break;
    }
    await refreshStatus();
  }, [refreshStatus]);

  const onStroke = useCallback(
    (rle: number[][], pixels: number) => {
      if (brushMode === "heal") {
        setDragNote(t("retouch.repairing", { pixels }));
        runInpaint("add", { rle, feather })
          .then(() => refreshStatus())
          .catch((e) => setDragNote(String(e)));
        return;
      }
      if (brushMode === "color") {
        // COLOR-004 局部调色：笔迹不是一条 light/inpaint，而是给肤色定向层递一份区域。
        // 引擎那边“落笔即生效”（自己把 scope 切到 brush 并随事件报回来），所以这里不能
        // 自己记一份作用域，也不能等用户再去点一下才能看见变化。
        setDragNote(t("retouch.coloring", { pixels }));
        runGrade("mask", { rle, feather, mode: "add" })
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

  function onEnhanceChange(sub: string, value: number) {
    // 拖动期间逐事件发：这一层每帧只在自己那只窗口里逐点乘加（实测亚毫秒），
    // 不发就是"滑块拖了、画面不动"。部分提交交给引擎（没给的子功能沿用当前值）。
    setEnhanceAmounts((prev) => ({ ...prev, [sub]: value }));
    void runEnhance("set", { [sub]: value } as Record<string, number>).then(() => {});
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
    setExportErr("");
    // 直通的拒绝是引擎在开跑前发的一条 error：runExport 那条 promise 只到"发出去了"
    // 为止（宿主回的是 requested:true），所以成败要看状态位，不能等 catch。
    // 先拿一份 last_error 作基线：上一张图的错还挂在那儿的时候，不能把它读成"这次也失败了"。
    engineStatus()
      .then((st0) => {
        const before = st0?.last_error ?? null;
        return runExport(exportDir, {
          format: exportFormat,
          quality: exportQuality,
          tile,
          scale: exportScale !== 1 ? exportScale : undefined,
          sharpen: exportSharpen > 0 ? exportSharpen : undefined,
          bitDepth: exportBits16 ? 16 : undefined,
          // 底片条多选集就是本批的清单；没选就只导当前这一张（引擎按 images 逐条记账）
          images: exportTargets.length ? exportTargets : undefined,
          // 导出侧 P0 的四格：中性位由引擎定，这里传用户显式选过的值
          outputProfile: exportProfile,
          tiffCompression: exportTiffComp,
          metadataIncludeGps: exportGps,
          conflictPolicy: exportConflict,
        })
          .then(() => refreshStatus())
          .then(() => watchExportOutcome(before));
      })
      .catch((e) => setDragNote(String(e)));
  }

  /** 拒绝是立刻到的（开跑前），成功是慢慢到的（一批图）：这里只等"引擎开口说错"，
   *  最多 6 秒；导出本身的终态一直由 export_progress / export_done 那条线报。 */
  async function watchExportOutcome(before: string | null) {
    const t0 = performance.now();
    while (performance.now() - t0 < 6_000) {
      const st = await engineStatus().catch(() => null);
      const err = st?.last_error ?? null;
      if (err && err !== before) { setExportErr(err); return; }
      await sleep(250);
    }
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

  /** 一格的点击语义（图库的多选口径）：
   *  普通点=打开那一张；Ctrl/Cmd+点=加减选；Shift+点=从上一次锚点到这一格的连续段。
   *  打开一张不清空多选集：批量导出时"选中的还是那几张"这件事不能被一次浏览打乱。 */
  function onCellClick(e: React.MouseEvent, index: number, path: string) {
    if (e.metaKey || e.ctrlKey) {
      setSel((prev) => { const n = new Set(prev); n.has(path) ? n.delete(path) : n.add(path); return n; });
      selAnchor.current = index;
      return;
    }
    if (e.shiftKey && selAnchor.current !== null) {
      const docs = strip?.docs ?? [];
      const a = Math.min(selAnchor.current, index), b = Math.max(selAnchor.current, index);
      setSel((prev) => { const n = new Set(prev);
        docs.filter((d) => d.index >= a && d.index <= b).forEach((d) => n.add(d.path)); return n; });
      return;
    }
    selAnchor.current = index;
    onPickDoc(index);
  }

  /** 批量打标签：逐张发给引擎（tag 是整份替换语义，所以这里把已有标签并进去而不是覆盖）。 */
  async function onBatchTag() {
    const tag = batchTag.trim();
    if (!tag || !selPaths.length) return;
    for (const path of selPaths) {
      const row = strip?.docs.find((d) => d.path === path);
      const tags = Array.from(new Set([...(row?.tags ?? []), tag]));
      await runProject("tag", { path, tags }).catch((e) => setDragNote(String(e)));
    }
    await refreshStatus();
  }

  /** 批量进/出回收站：置的是工程记录里的标志位，源文件一个字节也不动（CORE-007）。 */
  async function onBatchTrash(toTrash: boolean) {
    for (const path of selPaths) {
      await runProject("trash", { path, trashed: toTrash }).catch((e) => setDragNote(String(e)));
    }
    await refreshStatus();
  }

  /** 挑图的四组敏感度：用户没挑的就留空，让引擎的默认档（standard）由引擎说。 */
  const PICK_KEYS = ["duplicate", "blur", "exposure", "eyes"] as const;
  const pickArms: Record<string, string> = {};
  for (const k of PICK_KEYS) if (pickSens[k]) pickArms[k] = pickSens[k];
  const pickSensList = (status?.ready_caps?.pick_sensitivities ?? null) as
    Record<string, string[]> | null;
  const pickRun = status?.pick ?? null;
  // 在不在跑只看引擎那一份（session_state.picks_running），前端不自己按 pick_item 条数猜
  const pickRunning = !!strip?.picks_running || pickRun?.event === "pick_start";

  /** 挑图那一行的话：进度、结果、与「一行建议都没有」这一种也得说清楚。
   *  读数全部来自引擎报的那格（status.pick / session.docs[].pick），前端一个数也不自己算。 */
  function pickSummary() {
    const docs = strip?.docs ?? [];
    const n = docs.filter((d) => d.pick).length;
    if (!docs.length) return "";
    if (pickRunning) {
      const done = pickRun?.event === "pick_progress" ? pickRun?.done : status?.pick_items;
      const total = pickRun?.total ?? pickRun?.targets ?? docs.length;
      return `${t("pick.running").trim()}${done != null ? ` ${done}/${total}` : ""}`;
    }
    if (pickRun?.event === "pick_done") {
      const groups = (pickRun.groups ?? []).length;
      return n ? t("pick.done", { n, total: docs.length, groups,
                                  ms: Math.round(pickRun.total_ms ?? 0) }) : t("pick.none");
    }
    return n ? t("pick.done", { n, total: docs.length,
                                groups: (pickRun?.groups ?? []).length, ms: 0 }) : t("pick.idle");
  }

  /** 一格建议的 tooltip 全文：表头（判据指纹 + 档位）、逐条原因（带数值与阈值）、
   *  最后固定一句"建议不删原片"。原因本体是引擎写的句子，这里只排版。 */
  function pickTip(d: SessionDoc): string {
    const p = d.pick;
    if (!p) return d.pick_error ? t("pick.failed", { why: d.pick_error }) : "";
    const head = t("pick.tipHeader", {
      name: d.name, fp: p.fingerprint ?? "?",
      sens: Object.entries(p.sensitivities ?? {}).map(([k, v]) => `${k}=${v}`).join("/"),
    });
    const lines = [head];
    if (p.overridden_by_user) lines.push(`· ${t("pick.overridden")}`);
    lines.push(...(p.reasons.length
      ? p.reasons.map((r) => `· ${r.text}〔${r.method}〕`)
      : [`· ${t("pick.empty")}`]));
    if (p.measures.eye_open === null) {
      lines.push(`· ${t("pick.eyesUnknown", { why: p.measures.eye_note || `${p.measures.faces} 张脸` })}`);
    }
    if (p.measures.decoded_from === "camera_preview") {
      lines.push(`· ${t("strip.previewTip")}`);
    }
    lines.push(`· ${t("pick.noDelete")}`);
    return lines.join("\n");
  }

  /** 挑图建议（LNX-PICK-001）：把手。范围是"选中的那几张"，没选中就是整条底片条；
   *  默认跳过已量过的格子，`全部重算`才带 force（判据换版时新旧读数不可比，那时才值
   *  再付一次解码）。度量、分组、建议全在引擎里，这里不算法也不数格子。 */
  async function onPickAnalyze(force = false) {
    setPickNote("");
    if (!strip?.count) { setPickNote(t("strip.needDir")); return; }
    const targets = selPaths.length ? selPaths : undefined;
    try {
      await runPick("analyze", { ...(targets ? { paths: targets } : {}), force, ...pickArms });
      await refreshStatus();
    } catch (e) { setPickNote(String(e)); }
  }

  /** 撤销/重做（M5-b）：把手。步数、能不能撤、撤完画面是什么，全由引擎答复。 */
  function onHistory(action: "undo" | "redo" | "clear") {
    runHistory(action)
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)));
  }

  // ------------------------------------------------------------ 产品态面板（d4：注册表驱动）
  //
  // 面板上每一格的读数只从引擎最近说的那一份 doc_state 来：前端记一份“我以为是多少”
  // 就会出现“滑块在 0.9 而画面是 0.2”那种双向错配（M5-b 那一课的同形）。
  const doc: DocState | null = status?.doc_report?.doc_state ?? null;
  const project: ProjectState | null = status?.project ?? null;
  const tasks: TaskState[] = status?.tasks ?? [];
  const caps = status?.ready_caps ?? null;
  const pc: Precompute | null = status?.precompute ?? null;
  const hasImage = !!status?.image;
  const exporting = !!status?.export_progress;
  const projSuffix = caps?.project_suffix ?? ".lrproject.json";
  /** 底片条上被选中的那几张（没选就只导当前这张） */
  const selPaths = Array.from(sel);
  const exportTargets = selPaths.length ? selPaths : (hasImage && status?.image?.doc ? [status.image.doc] : []);
  /** 分人编辑那一份（LNX-PORTRAIT-003）：名单与「在改哪一张」全部来自引擎。
   *  先后次序在 native.ts 的 faceStateOf 里定，这里不写第二份。 */
  const faceSt = faceStateOf(status, doc);
  const faceCount = faceSt?.num_faces ?? pc?.num_faces ?? 1;
  /** D-P0-02 的单脸口径（注册表 scope_single_face 逐字）：mediapipe + 478 点 + 无几何警告，
   *  作用面要么恰好一张脸，要么多人而用户已显式点选了那一张。人数只从引擎报的读：前端数不来，
   *  也不该自己编一个“看起来只有一张”的判据。synthetic 的网格占位不算可用人脸——引擎在
   *  deform 里就拒它，界面不许装作能点。
   *  `blocked` 是引擎那一侧的放行判据（多人而未选定），这里只读不拼：拼第二份就会出现
   *  「面板说能点而引擎整条拒」那个 DoD 明确禁止的无响应控件。 */
  const faceOk = !!pc && pc.backend === "mediapipe" && pc.num_landmarks === 478
    && !deformGeomWarn
    // 三条一起才放行：①还剩可编辑的人（关掉唯一那一只之后一个也不剩），②人数与选定那一条
    // （多人而未选定要挡），③引擎手上真有"那一个人"的脸盒（`faceSt.box`）。只查②会出现
    // 面板亮着而引擎整条拒——DoD §3 明确禁止的那一形，而它正是人工账新造出来的形状
    && (faceSt?.enabled?.length ?? faceCount) >= 1
    && (faceCount === 1 || (faceCount > 1 && !!faceSt && faceSt.explicit && !faceSt.blocked))
    && !!faceSt && faceSt.box !== null;
  // 可编辑的人数从引擎那份 `enabled` 读（人工禁用之后它就变了）。这里只读不拼：拼第二份
  // 就会出现「面板说还要选人而引擎早就放行了」那个双向错配
  const editable = faceSt?.enabled?.length ?? faceCount;
  const faceWhy = hasImage
    ? ((faceSt?.enabled?.length ?? faceCount) === 0
        // 人工把名单里的人都关掉了：这不是"没分析"，而是用户说过"这些都不是脸"。
        // 面板要说的是这一句，而不是退回一句空洞的"需要先跑分析"
        ? `名单上 ${faceCount} 个人已全部被人工禁用：单脸作用域的面部重塑与眼牙层不再对任何人服务。`
          + "在上方人物格里点 ↺ 恢复那一只（LNX-PORTRAIT-006）；全图调色、曝光/白平衡、裁剪与磨皮仍可用。"
        : faceCount > 1 && faceSt?.blocked
        ? `名单上 ${faceCount} 个人、可编辑的有 ${editable} 个`
          + `${(faceSt?.disabled_count ?? 0) > 0 ? `（已人工关掉 ${faceSt?.disabled_count} 只）` : ""}：`
          + "本版本不在多人照片里替你选哪一张（SCOPE-001）。先在上方点选要编辑的人物，"
          + "选好之后这三个滑块就可用（LNX-PORTRAIT-003）；认出那是误检就点 ✕ 关掉它"
          + "（LNX-PORTRAIT-006）；全图调色、曝光/白平衡、裁剪与磨皮仍可用。"
        : faceCount > 1
          ? `画面里探到 ${faceCount} 张脸：面部重塑只服务你选定的那一张（人物 ${(faceSt?.index ?? 0) + 1}）。`
          : `需要且仅需要一张可用人脸（当前 backend=${pc?.backend ?? "未跑分析"}、点数=${pc?.num_landmarks ?? 0}`
            + `${deformGeomWarn ? "，且引擎报了几何警告" : ""}）。多人照片上替别人改脸是本产品明确不做的事。`)
    : "还没导入图片：这一格要作用于一张打开的图。";
  const liveTask = tasks.length ? tasks[tasks.length - 1] : null;
  // 注册表上的格式名（jpeg/tiff）与引擎落盘用的后缀名（jpg/tif）不是一回事：
  // 映射只在这一处，两个名单都不在面板里重复刻
  const fmtOut: Record<string, string> = { jpeg: "jpg", tiff: "tif", png: "png", webp: "webp" };
  const fmtIn: Record<string, string> = { jpg: "jpeg", jpeg: "jpeg", tif: "tiff", tiff: "tiff", png: "png", webp: "webp" };

  function p0value(key: string): number | boolean | string | number[] | null | undefined {
    switch (key) {
      case "lnx.skin.v1.enabled": return (doc?.strength ?? 0) > 0;
      case "lnx.skin.v1.strength": return doc?.strength;
      case "lnx.blemish.v1.enabled": return brushOn;
      case "lnx.mask.v1.analysis_enabled": return !!pc;
      case "lnx.mask.v1.feather": return feather;
      case "lnx.exposure.v1.ev": return doc?.exposure.ev;
      case "lnx.white_balance.v1.temperature_shift": return doc?.exposure.temperature_shift;
      case "lnx.white_balance.v1.tint_shift": return doc?.exposure.tint_shift;
      case "lnx.crop.v1.rect_normalized": return doc?.crop.rect;
      case "lnx.crop.v1.rotation_degrees": return doc?.crop.rotation_degrees;
      case "lnx.export.v1.format": return fmtIn[exportFormat] ?? exportFormat;
      case "lnx.export.v1.jpeg_quality": return exportQuality;
      case "lnx.export.v1.tiff_compression": return exportTiffComp;
      case "lnx.export.v1.output_profile": return exportProfile;
      case "lnx.export.v1.metadata_include_gps": return exportGps;
      case "lnx.batch.v1.conflict_policy": return exportConflict;
      // 预设下拉读的两个都来自引擎：`last_applied` 是“套完而没被手改”那一个（参数比过
      // 才算），而不是前端记的“上次点了哪个按钮”。
      case "lnx.preset.v1.apply": {
        const la = presetState?.last_applied
        const p = la ? presetList.find((x) => x.id === la.id) : null
        return p ? presetLabel(p) : ""
      }
      case "lnx.batch.v1.module_scope":
        return syncScopeLabel || syncScopes[0]?.label || "";
      default: return undefined;
    }
  }

  /** 枚举格的候选：有些由引擎报（预设名、能落的格式），不能在前端抄一份会漂的名单。 */
  function p0options(key: string): string[] | null {
    switch (key) {
      // 注册表的预设格现在接的是**模块预设**（人像/色彩/裁剪那一族，走 cmd_preset）。
      // LUT 面板上那一排表预设按钮不从这里走：它读的是 ready 报的 `presets`（另一件事：
      // 调色表 + 肤色定向那两层）。
      case "lnx.preset.v1.apply":
        return presetList.map(presetLabel);
      case "lnx.batch.v1.module_scope":
        return syncScopes.map((s) => s.label);
      case "lnx.export.v1.format":
        // 引擎报的落盘后缀翻回注册表的格式名：名单出处仍是 ready.export_formats
        return (caps?.export_formats ?? ["jpg", "tif", "png"]).map((x) => fmtIn[x] ?? x);
      case "lnx.export.v1.output_profile":
        // 内置只有两条真能落的：其它两个枚举值需要用户递一个真实 .icc（面板上说明了原因）
        return ["srgb", "source"];
      case "lnx.export.v1.tiff_compression": return ["none", "deflate", "lzw"];
      case "lnx.batch.v1.conflict_policy": return ["skip_and_report", "recheck"];
      default: return null;
    }
  }

  /** 这一刻为什么不能点。理由必须可复查（说的是引擎报出来的事实），不许写“暂不可用”。 */
  function p0enabled(key: string): string | null {
    if (key.startsWith("lnx.task.v1.")) {
      if (!tasks.length) return "队列里还没有批次：先点「开始批量导出」。";
      const st = liveTask?.state ?? "?";
      if (key.endsWith(".pause")) return st === "running" || st === "queued" ? null : `这一条现在是 ${st}：暂停只对正在跑或排队的批次说得上话（转移表在引擎 tasks.py）。`;
      if (key.endsWith(".resume")) return st === "paused" ? null : `这一条现在是 ${st}：只有 paused 能继续。`;
      if (key.endsWith(".cancel")) return ["succeeded", "failed", "cancelled"].includes(st) ? `这一条已经是 ${st}：取消是对还没停下的东西说的话。` : null;
      if (key.endsWith(".retry")) return ["paused", "failed", "cancelled", "succeeded"].includes(st) ? null : `这一条现在是 ${st}：等它停下再重试。`;
      return null;
    }
    if (key.startsWith("lnx.batch.v1.") || key.startsWith("lnx.export.v1.")) {
      if (key === "lnx.export.v1.start") {
      if (!pid || !engineAlive) return "引擎没在跑：先启动引擎。";
      if (exporting) return "已经有一批在跑：一批只许一个（两条 worker 会同抢一块卡）。";
        return exportTargets.length ? null : "底片条上没选图，也没有打开的文档：导出需要至少一张。";
      }
      return hasImage || selPaths.length ? null : "还没导入图片也没选中图：这一格现在没有可作用的对象。";
    }
    if (key.startsWith("lnx.project.v1.") || key.startsWith("lnx.import.v1.")) {
      return !pid || !engineAlive ? "引擎没在跑：先启动引擎。" : null;
    }
    if (key.startsWith("lnx.history.v1.")) {
      if (!pid || !engineAlive) return "引擎没在跑：先启动引擎。";
      if (!hasImage) return "还没导入图片：没有可撤销的会话。";
      return null;
    }
    // 逐点层与人脸相关：没图 / 没可用人脸就显式禁用并说清哪一条判据没过
    const faceScoped = key.startsWith("lnx.skin.v1.") || key.startsWith("lnx.blemish.v1.")
      || key.startsWith("lnx.mask.v1.");
    if (faceScoped && !faceOk) return faceWhy;
    if (key.startsWith("lnx.exposure.") || key.startsWith("lnx.white_balance.")
        || key.startsWith("lnx.crop.")) {
      return hasImage ? null : "还没导入图片：这一层要作用于一张打开的图。";
    }
    return null;
  }

  function p0slider(key: string, v: number) {
    if (key === "lnx.exposure.v1.ev") void runExposure("set", { ev: v }).then(refreshStatus).catch((e) => setDragNote(String(e)));
    else if (key === "lnx.white_balance.v1.temperature_shift") void runExposure("set", { temperature_shift: v }).then(refreshStatus).catch((e) => setDragNote(String(e)));
    else if (key === "lnx.white_balance.v1.tint_shift") void runExposure("set", { tint_shift: v }).then(refreshStatus).catch((e) => setDragNote(String(e)));
    else if (key === "lnx.crop.v1.rotation_degrees") void runCrop("set", undefined, v).then(refreshStatus).catch((e) => setDragNote(String(e)));
    else if (key === "lnx.skin.v1.strength") onStrength(v);
  }

  function p0toggle(key: string, v: boolean) {
    if (key === "lnx.blemish.v1.enabled") { setBrushOn(v); return; }
    if (key === "lnx.export.v1.metadata_include_gps") { setExportGps(v); return; }
    if (key === "lnx.skin.v1.enabled") { onStrength(v ? (strength <= 0 ? 0.5 : strength) : 0); return; }
    if (key === "lnx.mask.v1.analysis_enabled") {
      // 分析只能跑，不能“关”：掩膜是会话级常驻，关掉就是让面部微调当场失效。
      // 不假装能关：只在没跑过的时候按下去重跑一次。
      if (!v) { setDragNote("面部分析不提供“关掉”：掩膜常驻在本次会话里，要清空请重新导入这张图。"); return; }
      void runPrecompute().then(refreshStatus).catch((e) => setDragNote(String(e)));
    }
  }

  function p0enum(key: string, v: string) {
    if (key === "lnx.export.v1.format") { setExportFormat(fmtOut[v] ?? v); return; }
    if (key === "lnx.export.v1.tiff_compression") { setExportTiffComp(v); return; }
    if (key === "lnx.export.v1.output_profile") { setExportProfile(v); return; }
    if (key === "lnx.batch.v1.conflict_policy") { setExportConflict(v); return; }
    if (key === "lnx.preset.v1.apply") { void onPresetApplyByName(v); return; }
    if (key === "lnx.batch.v1.module_scope") { setSyncScopeLabel(v); return; }
  }

  function p0rect(_key: string, rect: number[]) {
    void runCrop("set", rect).then(refreshStatus).catch((e) => setDragNote(String(e)));
  }

  /** 面板按钮那一批：名字到命令的映射只在这一处（每个键对应注册表的一条）。 */
  async function p0action(key: string) {
    try {
      if (key === "lnx.export.v1.start") { onExport(); return; }
      if (key === "lnx.preset.v1.save") { await onPresetSave(); return; }
      if (key === "lnx.history.v1.undo") { onHistory("undo"); return; }
      if (key === "lnx.history.v1.redo") { onHistory("redo"); return; }
      if (key === "lnx.import.v1.choose_files") { await onPickPath(false); return; }
      if (key === "lnx.import.v1.choose_folder") { await onPickPath(true); return; }
      if (key === "lnx.project.v1.create") {
        const dir = await openDialog({ directory: true, title: "工程放哪个目录" });
        if (typeof dir !== "string" || !dir) return;
        const name = projName.trim() || (dir.split("/").pop() || "未命名项目");
        await runProject("create", { name, directory: dir });
        await refreshStatus();
        return;
      }
      if (key === "lnx.project.v1.open") {
        const f = await openDialog({ title: "打开工程文件",
          filters: [{ name: "LumaRetouch 工程", extensions: ["json"] }] });
        if (typeof f !== "string" || !f) return;
        await runProject("open", { path: f });
        await refreshStatus();
        return;
      }
      if (key === "lnx.project.v1.save") { await runProject("save"); await refreshStatus(); return; }
      if (key.startsWith("lnx.task.v1.")) {
        const action = key.split(".").pop() as "pause" | "resume" | "cancel" | "retry";
        await runTask(action, liveTask?.task_id);
        await refreshStatus();
        return;
      }
    } catch (e) {
      setProjErr(String(e));
      setDragNote(String(e));
    }
  }

  // ── 预设与批量同步（LNX-P0-PRESET / LNX-P0-BATCH）─────────────────────
  // 两份事实都从 status.session 读（引擎随 session_state 报）：预设清单/错误/“现在等于
  // 哪个预设”，与同步台账/上一笔的结果。这里不扫目录、不记 batch_id、不自己数张数。
  const presetState = status?.session?.presets ?? null;
  const syncState = status?.session?.sync ?? null;
  const presetList = presetState?.list ?? [];
  /** 名字重名时才拼 id：下拉的每一项必须能唯一映回一个预设，否则“应用哪一个”会变成猜。 */
  const dupNames = new Set(presetList.map((p) => p.name)
    .filter((n, i, arr) => arr.indexOf(n) !== i));
  const presetLabel = (p: { name: string; id: string }) =>
    (dupNames.has(p.name) ? `${p.name} · ${p.id}` : p.name);
  /** 作用域候选只从引擎报的 transferable 模块里拼：注册表说不通的那格不进候选。 */
  const syncScopes: { label: string; ops: string[] }[] = (() => {
    const mods = presetState?.modules ?? [];
    const okOf = (op: string) => mods.find((m) => m.operation_id === op)?.transferable === true;
    const global = ["lnx.exposure.v1", "lnx.white_balance.v1", "lnx.crop.v1"].filter(okOf);
    const skin = ["lnx.skin.v1", "lnx.blemish.v1"].filter(okOf);
    const out: { label: string; ops: string[] }[] = [];
    if (global.length) out.push({ label: "全图配方（曝光·白平衡·裁剪）", ops: global });
    if (global.length && skin.length)
      out.push({ label: "全图配方 + 磨皮（逐张须单脸）", ops: [...global, ...skin] });
    return out;
  })();
  const syncScopeOps = (syncScopes.find((s) => s.label === syncScopeLabel) ?? syncScopes[0])?.ops ?? [];
  /** 上一笔同步的实话（句子里的每一个数字都来自引擎报的那一份） */
  const syncNote = (() => {
    const r = syncState?.last_result;
    if (!r) return "还没有同步记录。"
    if (r.kind === "commit") {
      const n = r.applied?.length ?? 0
      const sk = r.skipped ?? []
      return sk.length
        ? `同步了 ${n} 张，${sk.length} 张没动：${sk.map((x) => `${x.path.split("/").pop()}（${x.reason}）`).join("；")}`
        : `同步了 ${n} 张（“撤销同步”可以退回去）`
    }
    const n = r.restored?.length ?? 0
    const cf = r.conflicts ?? []
    return cf.length
      ? `撤销了 ${n} 张，${cf.length} 张有冲突没动：${cf.map((x) => `${x.path.split("/").pop()}（${x.reason}）`).join("；")}`
      : `撤销了 ${n} 张`
  })();

  /** 发完一条不开新会话的命令后让引擎重报一次状态；轮询也会拿到，这里只是不等。 */
  async function refreshFromEngine() {
    await runSession("state")
    await refreshStatus()
  }

  async function onPresetApplyByName(label: string) {
    const p = presetList.find((x) => presetLabel(x) === label)
    if (!p) return
    setPresetSel(p.id)
    await runPreset("apply", { id: p.id })
    await refreshFromEngine()
  }

  async function onPresetSave() {
    if (!presetName.trim()) {
      setDragNote("预设名字是空的：存下来也认不出那是哪一个")
      return
    }
    // id 用时间戳而不拿名字拼：名字可以是中文/带空格，拿它当文件名就是一次路径穿越的入口
    const id = `user-${Date.now().toString(36)}`
    await runPreset("save", { id, name: presetName.trim(), kind: "custom" })
    setPresetSel(id)
    setPresetName("")
    await refreshFromEngine()
  }

  async function onPresetImport() {
    const f = await openDialog({ title: "导入预设（.json）",
      filters: [{ name: "LumaRetouch 预设", extensions: ["json"] }] })
    if (typeof f !== "string" || !f) return
    await runPreset("import", { path: f })
    // 成不成都不在这里下结论：清单与 errors 随 session_state 上来，坏掉的那个会带着原因列出来
    await refreshFromEngine()
  }

  async function onPresetDelete() {
    if (!presetSel) return
    await runPreset("delete", { id: presetSel })
    setPresetSel("")
    await refreshFromEngine()
  }

  async function onBatchSync() {
    if (!selPaths.length || !syncScopeOps.length) return
    await runBatch("commit", { docs: selPaths, moduleScope: syncScopeOps, conflictPolicy: exportConflict })
    await refreshFromEngine()
  }

  async function onBatchUndo() {
    const id = syncState?.last
    if (!id) return
    await runBatch("undo", { batchId: id })
    await refreshFromEngine()
  }

  const verdict = gate(stats, w);

  // 引擎进程此刻在不在（M5-c）。报回缺失（新壳配旧宿主）时退回"看 pid"的旧行为，
  // 而不是当成"没在跑"——那会把刚起好的引擎显示成已死。
  const engineAlive = status?.engine_alive ?? !!pid;

  return (
    <div className="app">
      <header className="topbar">
        <span className="name">{t("app.title")}</span>
        <span className="tag">{project?.open ? (project.name ?? "工程") : "未打开工程"}</span>
        {project?.open && (
          <span className={project.dirty ? "tag dirty" : "tag saved"}>
            {project.dirty ? "未保存" : "已保存"}
          </span>
        )}
        {!!selPaths.length && <span className="tag">选中 {selPaths.length} 张</span>}
        {exporting && <span className="tag run">
          导出 {status?.export_progress?.index ?? 0}/{status?.export_progress?.total ?? 0}</span>}
        {!!tasks.length && <span className="tag">队列 {tasks.length}</span>}
        <span className="mut" style={{ marginLeft: "auto" }}>
          {doc ? (doc.crop.lit ? `裁剪 ${JSON.stringify(doc.crop.out_full ?? [])}` : "") : ""}
          {status?.engine_version ? ` · 引擎 ${status.engine_version}` : ""}
        </span>
      </header>
      <aside className="side">
        <StudioPanel status={status} doc={doc} tasks={tasks} project={project}
                     hasImage={hasImage} exporting={exporting} faceOk={faceOk} faceWhy={faceWhy}
                     pickFace={pickFace} setPickFace={setPickFace}
                     faceActions={status?.ready_caps?.face_actions ?? []}
                     note={setDragNote} onDone={refreshStatus}
                     brush={{ on: brushOn, radius: brushRadius, feather, mode: brushMode,
                               onChange: (q) => {
                                 if (q.on !== undefined) setBrushOn(q.on);
                                 if (q.radius !== undefined) setBrushRadius(q.radius);
                                 if (q.feather !== undefined) setFeather(q.feather);
                                 if (q.mode !== undefined) setBrushMode(q.mode);
                               } }}
                     deformKinds={status?.ready_caps?.deform_kinds ?? []}
                     deformRange={status?.ready_caps?.deform_range}
                     exportDir={exportDir} setExportDir={setExportDir}
                     exportBits16={exportBits16} setExportBits16={setExportBits16}
                     deformScope={deformScope} setDeformScope={setDeformScope}
                     selCount={selPaths.length} projName={projName} setProjName={setProjName}
                     preset={{
                       name: presetName, setName: setPresetName,
                       selectedId: presetSel, setSelectedId: setPresetSel,
                       builtin: presetList.find((x) => x.id === presetSel)?.builtin ?? false,
                       count: presetList.length, errors: presetState?.errors ?? [],
                       onImport: () => { void onPresetImport() },
                       onDelete: () => { void onPresetDelete() },
                     }}
                     sync={{
                       selected: selPaths.length, canUndo: !!syncState?.last && hasImage,
                       note: syncNote,
                       onSync: () => { void onBatchSync() }, onUndo: () => { void onBatchUndo() },
                     }}
                     p0={{ value: p0value, optionsFor: p0options, enabled: p0enabled,
                           slider: p0slider, toggle: p0toggle, enum: p0enum,
                           action: p0action, rect: p0rect }} />
        {/* 旧工作台整块折起来：它不是产品面，但那些控件与跑靶都是真在用的证据链，
            删掉就等于把已经验过的能力从这台机器上拿掉。 */}
        <details className="grp harness">
        <summary>旧工作台 · 引擎与跑靶（诊断）</summary>
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
        {/* 厂商后缀单独一行，且必须自带"未经实机样张认证"这句话（M9-h）：免责写在引擎
            报的数据里，前端只是把它显示出来——不是前端自己补的一句漂亮话。 */}
        {!!status?.raw_backends?.vendor_suffixes?.length && (
          <div className="mut">
            {t("engine.rawVendor", {
              s: status.raw_backends.vendor_suffixes.join("/"),
              ok: status.raw_backends.plugin_installed
                ? t("engine.rawVendorDecodes") : t("engine.rawVendorMissing"),
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
        <button className={comparing ? "cmp on" : "cmp"}
                onPointerDown={(e) => { void cmpOn(e); }}
                onPointerUp={() => { void cmpOff(); }}
                onLostPointerCapture={() => { void cmpOff(); }}
                disabled={!pid || !status?.image}
                aria-pressed={comparing}
                title={t("retouch.compareOn")}>
          {comparing ? t("retouch.compareOn") : t("retouch.compare")}
        </button>
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
          <button className={brushMode === "color" ? "primary" : ""} onClick={() => setBrushMode("color")}
                  disabled={!status?.image}>{t("retouch.modeColor")}</button>
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
        {/* 眼牙增强（LNX-PORTRAIT-009）：三条滑块各自独立启停。名单与值域都来自引擎
            （ready 的 enhance_subs / enhance_range）——引擎没说就不画这一排，而不是前端
            刻一份名字去撞一条会被整条拒的命令。每格的"为什么现在不会动"直接引用引擎
            报的那句话（enhance.reason），面板不自己推断。 */}
        {(status?.ready_caps?.enhance_subs ?? []).map((sub) => {
          const en = enhanceStateOf(status, doc);
          const range = status?.ready_caps?.enhance_range ?? [0, 1];
          const px = en?.gated_px?.[sub] ?? 0;
          const why = en?.reason?.[sub] ?? null;
          const unusable = !status?.image
            || (en?.defer ?? false)
            || (faceSt?.blocked ?? false)
            || (en != null && !en.built && px <= 0 && why == null);
          const disabled = unusable || why != null;
          return (
            <div key={sub}>
              <label className="k">{t(`retouch.${sub}` as MsgKey)}
                {' '}{(enhanceAmounts[sub] ?? 0).toFixed(2)}</label>
              <input type="range" min={range[0]} max={range[1] ?? 1} step={0.01}
                     value={enhanceAmounts[sub] ?? 0} disabled={disabled}
                     onChange={(e) => onEnhanceChange(sub, +e.target.value)}
                     style={{ width: "100%" }} />
              {why != null && (
                <div className="mut">{t("retouch.enhOff", { why })}</div>
              )}
              {en?.defer && (
                <div className="mut">{t("retouch.enhDefer")}</div>
              )}
              {faceSt?.blocked && !en?.defer && (
                <div className="warn">{t("retouch.enhBlocked")}</div>
              )}
              {why == null && !disabled && (
                <div className="mut">{t("retouch.enhGate", {
                  px, ms: (lastEnhance?.enhance_ms ?? 0).toFixed(2),
                })}</div>
              )}
            </div>
          );
        })}
        <div className="row">
          <button onClick={() => { void runEnhance("clear").then(() => refreshStatus()); }}
                  disabled={!status?.image ||
                             !Object.values(enhanceAmounts).some((v) => Math.abs(v) > 0)}>
            {t("retouch.enhClear")}
          </button>
        </div>
        <div className="mut">{t("retouch.enhHow")}</div>
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
            {/* 16-bit 母档直通（M9-e）：可选位深名单由引擎的 ready.export_bits 说。
                引擎没报这一句、或当前格式不在 16 的名单里，就不画这个勾——把"能选"
                画出来再让用户去撞一条注定空的请求，是 M6 抠图那个后端踩过的坑。 */}
            {!!status.export_bits?.["16"]?.some((f) => f === exportFormat) && (
              <>
                <label className="row" title={t("export.master16Tip")}>
                  <input type="checkbox" checked={exportBits16}
                         onChange={(e) => setExportBits16(e.target.checked)} />
                  <span className="mut">{t("export.master16")}</span>
                </label>
                {exportBits16 && status.export?.bit_depth === 16
                  && status.export.images?.[0]?.readback_max_diff === 0 && (
                  <div className="mut">{t("export.master16Ran", {
                    src: String(status.export.images[0].source ?? "?"),
                    diff: status.export.images[0].readback_max_diff,
                    lv: (status.export.images[0].levels_per_channel ?? []).join("/"),
                  })}</div>
                )}
              </>
            )}
            {!!exportErr && <div className="err">{exportErr}</div>}
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
        </details>
      </aside>

      <main className="stage">
        <Viewer
          view={view} onView={setView}
          paintLocked={view.zoom !== 1 || view.x !== 0 || view.y !== 0}
          active={!!pid}
          skipDraw={skipDraw}
          upload={upload}
          ctxOpt={ctxOpt}
          mirrorOn={mirrorOn}
          glVisible={glVisible}
          chunks={chunks}
          brush={{ on: brushOn && !!status?.image, radius: brushRadius, onStroke }}
          pick={{ on: pickFace && !!status?.image && !brushOn, onRect: onPickFaceRect }}
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
        <section className="gallery">
          <div className="bar">
            <span>{strip ? t("strip.summary", { n: strip.count,
              th: strip.docs.filter((d) => d.thumb).length }) : t("strip.empty")}</span>
            {strip?.thumbs_running && <span>{t("strip.running")}</span>}
            {strip?.picks_running && <span>{t("pick.running")}</span>}
            <input value={batchTag} placeholder="批量标签" style={{ width: 110 }}
                   onChange={(e) => setBatchTag(e.target.value)} />
            <button disabled={!selPaths.length} onClick={onBatchTag}>打标签</button>
            <button disabled={!selPaths.length} onClick={() => onBatchTrash(true)}>移入回收站</button>
            <button disabled={!selPaths.length} onClick={() => onBatchTrash(false)}>还原</button>
            <button disabled={!selPaths.length} onClick={() => setSel(new Set())}>清除选择</button>
            <input value={stripDir} placeholder={t("strip.dirPlaceholder")}
                   style={{ flex: 1, minWidth: 90 }}
                   onChange={(e) => { setStripDir(e.target.value); setStripErr(""); }} />
            <button onClick={() => onPickPath(true)} title={t("retouch.browseTip")}>{t("retouch.browse")}</button>
            <button onClick={onScanStrip}>{t("strip.scan")}</button>
          </div>
          {/* 挑图（LNX-PICK-001）：档位名单来自引擎 ready；引擎没报就把按钮禁用并说明原因，
              不留一个按了没反应的控件，也不在前端补一份档名。 */}
          <div className="bar" title={t("pick.desc")}>
            <span className="k">{t("pick.title")}</span>
            {pickSensList && PICK_KEYS.map((key) => (
              <label key={key} className="k">{t(`pick.sens.${key}`)}
                <select value={pickSens[key] ?? "standard"}
                        onChange={(e) => setPickSens({ ...pickSens, [key]: e.target.value })}>
                  {(pickSensList[key] ?? ["weak", "standard", "strong"]).map((v) => (
                    <option key={v} value={v}>{t(`pick.arm.${v}` as MsgKey)}</option>
                  ))}
                </select>
              </label>
            ))}
            <button onClick={() => onPickAnalyze(false)}
                    disabled={!strip?.count || pickRunning || !pickSensList}
                    title={pickSensList ? t("pick.runTip") : t("pick.tip.arm")}>
              {t("pick.run")}
            </button>
            <button onClick={() => onPickAnalyze(true)}
                    disabled={!strip?.count || pickRunning || !pickSensList}
                    title={pickSensList ? t("pick.forceTip") : t("pick.tip.arm")}>
              {t("pick.force")}
            </button>
            <span>{pickSummary()}{selPaths.length ? t("pick.scope", { n: selPaths.length }) : ""}</span>
            {pickNote && <span className="err">{pickNote}</span>}
          </div>
          {stripErr && <div className="err">{stripErr}</div>}
          {strip && strip.count > 0 && (
            <div className="strip">
              {strip.docs.map((d) => {
                const edited = d.edits.repair > 0 || d.edits.light > 0 || d.edits.deform
                  || d.edits.lut || d.edits.grade;
                return (
                  <button key={d.path}
                          className={"cell" + (d.loaded ? " on" : "")
                            + (sel.has(d.path) ? " sel" : "") + (d.trashed ? " trashed" : "")}
                          title={`${d.path}${d.thumb_error ? ` · ${d.thumb_error}` : ""}`}
                          onClick={(e) => onCellClick(e, d.index, d.path)}>
                    {d.thumb && thumbs[d.path] ? (
                      <img alt={d.name} width={d.thumb.w} height={d.thumb.h}
                           src={`data:image/jpeg;base64,${thumbs[d.path]}`} />
                    ) : (
                      <span className="ph">{d.thumb_error ? t("strip.failed") : "…"}</span>
                    )}
                    <span className="nm">{d.name}</span>
                    {edited && <span className="badge">{t("strip.edited")}</span>}
                    {/* RAW 那一格画的是相机内嵌预览，不是我们渲的那一帧：不标就是理亏 */}
                    {d.thumb?.preview && (
                      <span className="badge pv" title={t("strip.previewTip")}>
                        {t("strip.preview")}{d.thumb.format ? ` · ${d.thumb.format}` : ""}
                      </span>
                    )}
                    {!!d.tags?.length && <span className="badge tag" title={d.tags.join(" ")}>
                      {d.tags[0]}{d.tags.length > 1 ? ` +${d.tags.length - 1}` : ""}</span>}
                    {/* 挑图那一格（PICK-001）：标签来自引擎，逐条原因在 tooltip 里带着
                        数值与阈值。已有用户标记时换成灰底（人先于机器），但建议本体不藏。 */}
                    {d.pick?.labels?.length ? (
                      <span className={"badge pk" + (d.pick.overridden_by_user ? " ov" : "")}
                            title={pickTip(d)}>
                        {d.pick.labels.map((l) => t(`pick.label.${l}` as MsgKey)).join(" · ")}
                      </span>
                    ) : null}
                    {d.pick && !d.pick.labels.length && (
                      <span className="badge pk ok" title={pickTip(d)}>OK</span>
                    )}
                    {d.pick_error && (
                      <span className="badge pk ov" title={pickTip(d)}>?</span>
                    )}
                    {d.trashed && <span className="badge st">回收站</span>}
                    {!d.trashed && d.opened && !edited && <span className="badge st">已开</span>}
                  </button>
                );
              })}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
