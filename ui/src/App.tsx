import {useWhiteBalancePickerWorkflow} from './whiteBalance/useWhiteBalancePicker';
import {WhiteBalancePickerControls,WhiteBalancePickerStatus} from './whiteBalance/WhiteBalancePickerControls';
import {LayoutControls} from "./layout/LayoutControls";
import {useLayoutSettings} from "./layout/model";
import {WatermarkControls, WatermarkReceipt} from "./watermark/WatermarkControls";
import {useWatermarkSettings} from "./watermark/model";
import {useWhiteBalanceWorkflow} from "./whiteBalance/useWhiteBalanceWorkflow";
import {WhiteBalanceControls} from "./whiteBalance/WhiteBalanceControls";
import {useSourcePatchWorkflow} from './sourcePatch/useSourcePatchWorkflow';
import {SourcePatchPanel,SourcePatchStatus} from './sourcePatch/SourcePatchPanel';
import {createStatusFence} from "./statusFence";
import {usePresetWorkflow} from "./presets/usePresetWorkflow";
import {PresetPanel} from "./presets/PresetPanel";
import {presetLabel as modulePresetLabel} from "./presets/presetModel";
import {batchScopeOptions, resolveBatchScope} from "./batch/batchScopeOptions";
import {BatchActions} from './batch/BatchActions';
import {useBatchWorkflow} from './batch/useBatchWorkflow';
import {BatchReview} from './batch/BatchReview';
import {useColorSampler} from './useColorSampler';
import {ColorSamplePanel} from './components/ColorSamplePanel';
import {useProjectWorkflow} from './projects/useProjectWorkflow';
import {ProjectWorkspace} from './projects/ProjectWorkspace';
import {useViewportProbe} from './diagnostics/useViewportProbe';
import {useBenchmarkAutomation} from './diagnostics/useBenchmarkAutomation';
import {useEmptyStateProbe} from './diagnostics/useEmptyStateProbe';
import { createRefreshPump } from "./refreshPump";
import { captureOriginal, compareImageKey } from "./compareCapture";
import { skinStrengthOptions, skinMaskUnavailable } from "./skinScope";
import { useCallback, useEffect, useRef, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import Viewer, { VIEW_HOME, type CompareMode, type Hud, type View } from "./components/Viewer";
import RegistryPanel from "./components/RegistryPanel";
import RetouchPanel from "./components/RetouchPanel";
import CropModal from "./components/CropModal";
import { TOOLS, TOOL_CATEGORIES } from "./spec";
import { REGISTRY, keyOf, sectionTitleOf, type SectionId } from "./p0";
import { clickRle } from "./brush";
import { reconcileExportCombo } from "./exportModel";
import { notifyInspectionEditIntent } from "./native";
import type { InspectionUiState } from "./inspectionController";
import { t, type MsgKey } from "./i18n";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import {
  benchStart, benchStats, engineStatus, loadImage, m0Env, parseFrameHead, peekFrame,
  faceStateOf, enhanceStateOf,
  report, runDeform, runEnhance, runFace,
  fetchFilmstrip, runExport, runGrade, runHistory, runHsl, runInpaint, runLight, runLut, runPick, runSession, runBackground,
  runCrop, runExposure, runPrecompute, runProject, runTask,
  setCompare, compareStatus, setStrength, shutdownEngine, startEngine,
  type BenchOptions, type DeformInfo, type DocState, type EngineStatus, type EnhanceInfo, type ExportDone,
  type ExportProgress, type HistoryReport, type HistoryState,
  type InpaintInfo, type SessionState,
  type GradeInfo, type LightInfo,
  type LutInfo, type BackgroundInfo,
  type Precompute, type SessionDoc, type Stats, type ProjectState,
  type TaskState, type ParsedFrame,
} from "./native";

/** 拖进来的文件能不能开：判据只有一份，出处是引擎 ready 报的 image_exts
 *  （session.IMAGE_EXTS 那一份）。拆成纯函数是因为装机真窗口要能**直接问它**——
 *  否则"拖拽接上了吗"这件事只能靠人坐在机器前拖一次，而那一条没法进发布门禁。 */
export function splitDroppable(paths: string[], exts: string[] | null | undefined) {
  const extOf = (p: string) => {
    const i = p.lastIndexOf(".");
    return i < 0 ? "" : p.slice(i).toLowerCase();
  };
  const ok: string[] = [], skipped: string[] = [];
  for (const p of paths) {
    if (!p) continue;
    (exts && exts.length && !exts.includes(extOf(p)) ? skipped : ok).push(p);
  }
  ok.sort();                       // 同一批重拖得到同一张：顺序不能靠操作系统给
  return { ok, skipped };
}

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

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

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
  const [dropHint, setDropHint] = useState(false);
  // 路径错误就地显示在输入框下方。原来它只落到 dragNote——那行灰字在窗口另一头，
  // 用户点了「导入」什么也没发生也不知道为什么，那就是事实上的静默失败。
  const [pathErr, setPathErr] = useState("");
  // 产品档代理：8294400 px（约 4K 视口档）。此前默认 576000 是跑靶预算，
  // 在大屏上会把 24MP 的原片缩成 960×600 再放大，观感就是一层马赛克。
  const [maxPx] = useState(8_294_400);
  const [strength, setStrengthV] = useState(0.0);
  const strengthRef = useRef(strength);
  strengthRef.current = strength;
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
    sclera: 0, iris: 0, teeth: 0, dark_circles: 0, eye_bags: 0, veins: 0, catchlight_left: 0, catchlight_right: 0,
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
  const {watermark, setWatermark, storageError: watermarkStorageError} = useWatermarkSettings();
  const layoutModel = useLayoutSettings();
  const [exportDir, setExportDir] = useState("/tmp/luma-export");
  const [exportFormat, setExportFormat] = useState("jpg");
  const [exportQuality, setExportQuality] = useState(95);
  // 放大（M7）：倍率与出片锐量。1 / 0.0 就是"不上这一层"——默认必须是原样出片，
  // 而不是一个没人同意的默认美化。
  const [exportScale, setExportScale] = useState(1);
  const [exportSharpen, setExportSharpen] = useState(0);
  // 16-bit TIFF：保留原生高位深源，并按逐图配方进入浮点编辑；显示代理不作出片源。
  const [exportBits16, setExportBits16] = useState(false);
  // 形变作用层（LNX-PORTRAIT-004）：这一格选的是"正在改哪一层"，值本身不进口径——
  // 每一层的数值与"这张被覆盖了哪几格"都由引擎随 doc_state 报（面板读它，不读这里）
  const [deformScope, setDeformScope] = useState<"all" | "person">("all");
  // 导出侧 P0 的四格（注册表 lnx.export.v1 / lnx.batch.v1）。中性位按冻结的注册表：
  // GPS默认关，冲突默认skip_and_report，色彩档默认sRGB；两种位深均支持无损TIFF压缩。
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
  const [appliedPreset, setAppliedPreset] = useState("");
  const [syncScopeLabel, setSyncScopeLabel] = useState("");
  const [batchPolicy,setBatchPolicy]=useState("skip_and_report");
  // 视口平移/缩放（只属于显示：导出写的仍是引擎那一份像素）
  const [view, setView] = useState<View>({ ...VIEW_HOME });
  /** Fit 倍率由视口算（它才知道画布与帧尺寸）；100% = 1/(dpr*fitScale) */
  const [fitScale, setFitScale] = useState(1);
  /** 当前是不是「1:1 物理像素」档：它必须随 fitScale 重算，否则改窗口大小就会
   *  从 100% 漂成 119%（4K 验收时量到过）。自由缩放/滚轮一进来就退出这一档。 */
  const [oneToOne, setOneToOne] = useState(false);
  const [inspectionEnabled,setInspectionEnabled]=useState(false);
  const [inspectionRetry,setInspectionRetry]=useState(0);
  const [inspectionState,setInspectionState]=useState<InspectionUiState>({state:'idle',message:'代理预览'});
  // 工作区：项目管理 / 图库 / 精修（默认）/ 创意 / 批量导出。
  // 五档对应《工作流规格.json》47238「工作区信息架构」：主页管理项目，项目内切换
  // 图库、精修、创意，默认精修；导出列表是全局入口。
  const [workspace, setWorkspace] = useState<
    "projects" | "library" | "retouch" | "creative" | "export"
  >("retouch");
  // 裁剪/旋转模态（P0 lnx.crop.v1）
  const [cropOpen, setCropOpen] = useState(false);
  // 图库的「已导出」：只认引擎 export_done 里真的写出去的那几张
  const [exported, setExported] = useState<Set<string>>(new Set());
  // 对比：单视图 / 并排 / 卷帘；按住空格是单视图里的临时对比
  const [compareMode, setCompareMode] = useState<CompareMode>("single");
  const [swipe, setSwipe] = useState(0.5);
  const [originalFrame, setOriginalFrame] = useState<ParsedFrame | null>(null);
  const [hasOriginal, setHasOriginal] = useState(false);
  // 人物属性栏：所有人（联动）或某一张脸（独立）。索引来自引擎的 face.index。
  const [faceScope, setFaceScope] = useState<"all" | number>("all");
  // 工程与任务面（读只读引擎报的那两份，前端不记“存过了”）
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
    setEnhanceAmounts({ sclera: 0, iris: 0, teeth: 0, dark_circles: 0, eye_bags: 0, veins: 0, catchlight_left: 0, catchlight_right: 0, ...(ds.enhance?.amounts ?? {}) });
    setLutAmount(ds.lut.amount);
    setGradeAmounts({ dh: ds.grade.dh, ds: ds.grade.ds, dv: ds.grade.dv });
    setGradeMix(ds.grade.amount);
    applied.current = { strength: ds.strength, from };
  }, []);

  const statusFence = useRef(createStatusFence());
  const refreshStatusWithErrors = useCallback(async (propagateError = false) => {
    const ticket = statusFence.current.issue();
    try {
      const st = await engineStatus();
      if (!statusFence.current.accept(ticket, st.doc_rev)) return;
      setStatus(st);
      // 消除笔的结果与日志同源：inpaint_done 只发一次，轮询不能错过
      if (st.inpaint) setLastInpaint(st.inpaint);
      if (st.light) setLastLight(st.light);
      if (st.enhance) {
        setLastEnhance(st.enhance);
        // defer/invalidate 那两条不能把滑块弹回零：那两句说的是"引擎现在认不认得人"，
        // 而"用户改过什么"是另一件事（PORTRAIT-004 定下的分层，形变那边同一课）
        if (st.enhance.action === "invalidate") {
          setEnhanceAmounts({ sclera: 0, iris: 0, teeth: 0, dark_circles: 0, eye_bags: 0, veins: 0, catchlight_left: 0, catchlight_right: 0, ...(st.enhance.dropped_amounts ?? {}) });
        } else {
          setEnhanceAmounts({ sclera: 0, iris: 0, teeth: 0, dark_circles: 0, eye_bags: 0, veins: 0, catchlight_left: 0, catchlight_right: 0, ...st.enhance.amounts });
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
        const fs = await fetchFilmstrip();
        if (!statusFence.current.current(ticket, st.doc_rev)) return;
        stripRev.current = st.session_rev;
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
          // 换图 = 回到适应窗口、回到所有人；对比的原图快照作废重取
          setOneToOne(false);
          setInspectionEnabled(false);
          setView(VIEW_HOME);
          setFaceScope("all");
          setHasOriginal(false);
        }
      } else {
        setHistRep(null);
        applied.current = null;
      }
      return st;
    } catch (error) {
      if (propagateError) throw error;
      /* Background polling is quiet; explicit workflows surface refresh errors. */
    }
  }, [applyDocState]);
  const refreshStatus = useCallback(() => refreshStatusWithErrors(), [refreshStatusWithErrors]);

  const panelRefreshRef = useRef<ReturnType<typeof createRefreshPump> | null>(null);
  useEffect(() => {
    const pump = createRefreshPump(async () => {
      const st = await refreshStatus();
      return !!(st?.edit_queue?.in_flight || st?.edit_queue?.pending);
    }, run => window.setTimeout(run, 80), id => window.clearTimeout(id));
    panelRefreshRef.current = pump;
    return () => {
      pump.dispose();
      if (panelRefreshRef.current === pump) panelRefreshRef.current = null;
    };
  }, [refreshStatus]);
  const requestPanelRefresh = useCallback(() => panelRefreshRef.current?.trigger(), []);

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
      if (document.querySelector('.batchReviewBackdrop')) return;
      if (e.code !== "Space" || e.repeat || isText(e.target as HTMLElement)) return;
      e.preventDefault();
      if (!pid || comparingRef.current || compareMode !== "single") return;
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
  }, [pid, compareMode]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (document.querySelector('.batchReviewBackdrop')) return;
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

  const projectFlow=useProjectWorkflow({refresh:refreshStatus,notify:setDragNote,
    enterRetouch:()=>setWorkspace("retouch")});

  useViewportProbe(setImgPath);

  useBenchmarkAutomation({setUpload,setCtxOpt,setMirrorOn,setGlVisible,setChunks,setSkipDraw,setTierLabel,setPid,setOneToOne,setView,strengthRef,refreshStatus,applied,hudRef});

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

  /** 原生选择框：路径不该靠手打。dir=true 选目录（底片条），false 选图片文件。
   *  过滤器用引擎报的那份名单（ready.image_exts）；引擎没说就什么都不过滤，而不是
   *  拿宿主抄的一份去挡用户。取消选择是正常路径（返回 null），不报错也不改现值。 */
  /** 图片后缀模式：只从引擎 ready 报的 `image_exts` 来（唯一出处）。
   *
   *  每个后缀给大小写两份。GTK 的过滤器模式在 Unix 上**大小写敏感**：实测
   *  GLib.pattern_match_simple("*.cr2", "IMG.cr2") = True，而 "IMG.CR2" = False。
   *  相机产出的后缀全是大写（佳能 .CR2 / 尼康 .NEF / 索尼 .ARW），于是这一栏过去
   *  把 RAW 整个藏起来——而引擎那边是 ext.lower() 判断，路径给得到就收：
   *  唯一挡路的正是这个框。字符类写法 *.[Cc][Rr]2 在这条匹配器上不通，别试。
   *  引擎还没报名单时返回 undefined：把过滤交给系统，而不是拿宿主抄的名单挡人。 */
  async function imagePatterns(): Promise<string[] | undefined> {
    const exts = (await engineStatus().catch(() => null))?.image_exts ?? null;
    return exts
      ? Array.from(new Set(exts.flatMap((e) => [e.replace(/^\./, ""), e.replace(/^\./, "").toUpperCase()])))
      : undefined;
  }

  async function onPickPath(dir: boolean) {
    const patterns = dir ? undefined : await imagePatterns();
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

  /** 拖进来与点进来走同一条路：选择框、路径框、系统 DND 都汇到 importPath，
   *  行为只有一份（两份导入就会有一份不报错）。 */
  async function onImport() { await importPath(imgPath); }

  /** 一次点击就开图：空状态卡片与顶栏「打开照片」共用这一条路。
   *
   *  与 `onPickPath(false)` 的唯一差别是选完立刻导入——C 端入口不该要两次点击，
   *  而"选完还得再按一下导入"正是最容易让人以为按钮坏了的形状（DoD §3）。
   *  过滤器、取消路径、报错文案全部复用同一份，免得出现"拖进来能开、点进来开不了"。
   *  取消是正常路径（返回 null），不报错也不改现值。 */
  async function openAndImport() {
    if (busy) return;
    const patterns = await imagePatterns();
    let sel: string | null;
    try {
      sel = await openDialog({ multiple: false, directory: false,
        ...(patterns ? { filters: [{ name: "图片 / RAW", extensions: patterns }] } : {}) });
    } catch (e) {
      setPathErr(`${t("retouch.pickFailed")}：${String(e)}`);
      return;
    }
    if (typeof sel !== "string" || !sel) return;
    setPathErr("");
    setImgPath(sel);
    await importPath(sel);
  }

  async function importPath(raw: string) {
    const p = raw.trim();
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
      await loadImage(p, { maxPx, precompute: "auto" });
      const out = await waitImportOutcome(p);
      if (out.kind !== "ok") {
        setPathErr(out.why); setDragNote(out.why);
      } else {
        setDragNote("");      // “导入中…”不许留在屏上：那一行现在说的是过去
        // 打开一张图就把同目录扫进底片条（商业软件的行为：底片条是这个文件夹，
        // 不是一根空带子）。缩略图由引擎生成；扫不动不影响这张图本身。
        const dir = p.slice(0, Math.max(0, p.lastIndexOf("/")));
        if (dir) {
          setStripDir(dir);
          runSession("scan", { dir, thumbs: true }).catch(() => undefined);
        }
      }
    } catch (e) {
      const why = String(e);
      setPathErr(why);                 // 就在输入框下面说，不只丢给窗口另一头那行灰字
      setDragNote(why);
    } finally {
      setBusy(false);
    }
  }

  /** 系统文件拖入（DoD §5「任意拖入真机人像或 DNG 照片」）。
   *
   *  为什么走 Tauri 的 drag-drop 事件而不是 HTML5 的 onDrop：装机壳里 v2 默认
   *  `dragDropEnabled: true`，WebKitGTK 把桌面环境的 DND 拦成 `tauri://drag-drop` 并
   *  只在这里交出**真实文件路径**；HTML5 的 dataTransfer 在壳里拿不到路径（浏览器 dev
   *  里能拿到）。挂错的地方就表现为"拖进来什么都不发生、屏上一个字也不说"。
   *  可开后缀以引擎报的 `image_exts`（session.IMAGE_EXTS 那一份）为准：拷一份名单到
   *  前端就是给自己埋雷。多张的接法按现有能力说实话：底片条是按目录扫的，所以同一目录
   *  先 scan 再打开第一张，不同目录就明说只打开了第一张（不许静默丢文件）。 */
  async function onDropPaths(raw: string[]) {
    setDropHint(false);
    if (!raw.length) return;
    const exts = (await engineStatus().catch(() => null))?.image_exts ?? null;
    const { ok, skipped } = splitDroppable(raw, exts);
    if (!ok.length) {
      setPathErr(t("retouch.drop.unsupported", { n: String(skipped.length), exts: (exts ?? []).join(" ") }));
      return;
    }
    ok.sort();                       // 同一批重拖得到同一张：顺序不能靠操作系统给
    const first = ok[0];
    const dirs = new Set(ok.map((p) => p.slice(0, p.lastIndexOf("/"))));
    setImgPath(first);
    setPathErr("");
    if (ok.length > 1 && dirs.size === 1) {
      const dir = Array.from(dirs)[0];
      setStripDir(dir);
      runSession("scan", { dir, thumbs: true }).catch(() => undefined);
      setDragNote(t("retouch.drop.scanned", { n: String(ok.length) }));
    } else if (ok.length > 1) {
      setDragNote(t("retouch.drop.onlyFirst", { n: String(ok.length - 1) }));
    }
    await importPath(first);
  }

  useEffect(() => {
    let dead = false;
    let unlisten: (() => void) | undefined;
    // 宿主 API 可能**同步**抛错：普通浏览器里没有 __TAURI_INTERNALS__，
    // `getCurrentWindow()` 读 `.metadata` 直接 TypeError；而 useEffect 里逃出来的
    // 同步异常会把整棵 React 树打崩（浏览器预览因此只剩空 body）。系统拖拽是可选
    // 能力：起不来就跳过这一路，界面照常——DoD §3 要的是"没有起不来的界面"。
    let attaching: Promise<() => void>;
    try {
      attaching = getCurrentWindow().onDragDropEvent((ev) => {
        const p = ev.payload as { type: string; paths?: string[] };
        if (p.type === "enter" || p.type === "over") { setDropHint(true); return; }
        if (p.type === "leave") { setDropHint(false); return; }
        if (p.type === "drop") void onDropPaths(p.paths ?? []);
      });
    } catch {
      return;
    }
    attaching.then(async (fn) => {
      if (dead) fn(); else unlisten = fn;
      // env 只能问宿主（异步）：这一臂是可选的，读不到就当没开，不许拖垮监听本身
      if ((await m0Env().catch(() => null))?.auto_drop) {
        // 装机壳里量两件事：①监听器挂上了（权限或 API 没通就是这里 reject，
        // 走不到这一行）；②那份"能不能开"的判断在**装好的这一件**里跑的是引擎报的
        // 名单（可开后缀为空 = 引擎还没说话，臂自己报红，不猜）
        void (async () => {
          // ready 可能还没到（引擎 spawn 是并行的）：轮一小段等引擎说话。等不到就带着
          // 空名单报出去——那一格在门禁里就是红的，臂不许猜一份后缀名单顶上去。
          let exts: string[] | null = null;
          for (let i = 0; i < 100 && !exts?.length; i++) {
            exts = (await engineStatus().catch(() => null))?.image_exts ?? null;
            if (!exts?.length) await sleep(100);
          }
          const got = splitDroppable(["/x/照片.jpg", "/x/照片.DNG", "/x/说明.txt", ""], exts);
          await report(`M0_DROP ${JSON.stringify({
            attached: true, exts: exts ?? [],
            accepted: got.ok.map((p) => p.split("/").pop()),
            rejected: got.skipped.map((p) => p.split("/").pop()),
            dragDropEnabledDefault: true,
          })}`);
        })();
      }
    }).catch(async (e) => {
      setDropHint(false);
      if ((await m0Env().catch(() => null))?.auto_drop) {
        await report(`M0_DROP ${JSON.stringify({ attached: false, error: String(e) })}`);
      }
    });
    return () => { dead = true; unlisten?.(); };
    // 只挂一次：处理函数读的是 ref 与 setState，放进依赖会让监听器每帧重挂
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** 对比：按住=临时出一帧原图，松开=回到修好的那一版。
   *  走引擎的 compare 而不是 set_strength(0)：会话强度不动、撤销栈不占步，
   *  松手后滑块位置与画面都还是用户离开时那一版。 */
  /** 按住看原图（顶栏按钮与空格键共用这一条）。 */
  async function cmpHold() {
    if (!pid || comparingRef.current) return;
    comparingRef.current = true;
    setComparing(true);
    await setCompare(true).catch((err) => { setDragNote(String(err)); });
  }

  async function cmpOn(e: React.PointerEvent<HTMLButtonElement>) {
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* 拿不到捕获不影响对比 */ }
    await cmpHold();
  }
  async function cmpOff() {
    if (!comparingRef.current) return;
    comparingRef.current = false;
    setComparing(false);
    await setCompare(false).catch((err) => { setDragNote(String(err)); });
  }

  // Polling allocates fresh objects, but does not import a new photograph.
  const compareKey = compareImageKey(status?.image);
  const compareDoc = status?.image?.doc ?? "";
  const needsOriginal = compareMode !== "single";
  useEffect(() => {
    setHasOriginal(false);
    setOriginalFrame(null);
    if (workspace !== "retouch" || !needsOriginal || !compareDoc || !pid) return;
    let dead = false;
    const id = crypto.randomUUID();
    void (async () => {
      try {
        const frame = await captureOriginal({
          id, doc: compareDoc, documentId:status?.image?.load_id, cancelled: () => dead,
          request: (requestId) => setCompare(true, requestId), receipt: compareStatus,
          pixels: async () => parseFrameHead(await peekFrame()),
          wait: () => sleep(25), now: () => performance.now(),
        });
        if (!dead && frame) { setOriginalFrame(frame); setHasOriginal(true); }
      } catch (err) {
        if (!dead) { setDragNote(String(err)); setCompareMode("single"); }
      } finally {
        if (!dead) void setCompare(false).catch((err) => setDragNote(String(err)));
      }
    })();
    return () => { dead = true; void setCompare(false).catch(() => undefined); };
  }, [needsOriginal, workspace, compareKey, compareDoc, pid]);

  /** 视口/顶栏的缩放：Fit 与真正的 100%（1 图像像素 = 1 屏幕像素）。 */
  function zoomFit() { setInspectionEnabled(false); setOneToOne(false); setView({ ...VIEW_HOME }); }
  function zoomOne() {
    const dpr = window.devicePixelRatio || 1;
    setInspectionEnabled(true);setInspectionRetry(n=>n+1);
    setOneToOne(true);
    setView({ zoom: fitScale>0?1/(dpr*fitScale):1, x: 0, y: 0, fit: false });
  }
  // Fit 倍率随画布尺寸变；「100%」是把 zoom 存成相对 Fit 的倍率，所以窗口一改
  // 大小就得重算。只算一次的话，4K 上把窗口拉大后徽标会写 119%（图不是 1:1 了）。
  useEffect(() => {
    if (!oneToOne) return;
    if (fitScale<=0) return;
    const dpr = window.devicePixelRatio || 1;
    setView((v) => ({ ...v, zoom: 1 / Math.max(1e-6, dpr * fitScale) }));
  }, [oneToOne, fitScale]);
  // 没有图时不渲染缩放条；有图但视口还没量出 fitScale 时用 100% 占位，
  // 绝不让顶栏出现 0%。
  const zoomPct = !status?.image ? ""
    : fitScale > 0
      ? `${Math.round((view.fit ? fitScale
        : view.zoom * fitScale * (window.devicePixelRatio || 1)) * 100)}%`
      : "100%";

  const inspectionCrop=status?.doc_report?.doc_state?.crop;
  const inspectionSize=inspectionCrop?.out_full ?? (inspectionCrop?.neutral
    ? [status?.image?.src_w??0,status?.image?.src_h??0] : [0,0]);
  const inspectionKey=JSON.stringify([compareKey,status?.doc_rev,pid,inspectionRetry]);

  /** 底片条的评分/色标：落在工程记录的 tags/label 上（不碰原图）。
   *  评分用保留标签 `rating:N`；色标用 label（红/黄/绿/蓝/紫）。 */
  const ratingOf = (d: SessionDoc) => {
    const hit = (d.tags ?? []).find((x) => /^rating:[0-5]$/.test(x));
    return hit ? Number(hit.slice(7)) : 0;
  };
  async function setRating(d: SessionDoc, n: number) {
    const next = ratingOf(d) === n ? 0 : n;
    const tags = (d.tags ?? []).filter((x) => !x.startsWith("rating:"));
    if (next > 0) tags.push(`rating:${next}`);
    try {
      await runProject("tag", { doc: d.path, tags, label: d.label ?? "" });
      await refreshStatus();
    } catch (e) { setDragNote(String(e)); }
  }
  async function cycleFlag(d: SessionDoc) {
    const order = ["", "红", "黄", "绿", "蓝", "紫"];
    const cur = order.indexOf(d.label ?? "");
    const next = order[(cur + 1) % order.length];
    try {
      await runProject("tag", { doc: d.path, tags: d.tags ?? [], label: next });
      await refreshStatus();
    } catch (e) { setDragNote(String(e)); }
  }
  const FLAG_COLOR: Record<string, string> = {
    "红": "#e06c6c", "黄": "#e3c176", "绿": "#7bbf8a", "蓝": "#6f9fd8", "紫": "#b48ad8",
  };
  /** 图库三种标识都必须是真事实：RAW 看源后缀或相机预览，已编辑看工程里那几层，
   *  已导出看 export_done 的 out 字段。前端不按“看起来像”猜。 */
  const RAW_RE = /\.(dng|cr2|cr3|nef|arw|raf|orf|rw2|pef|srw|3fr|x3f|rwl|iiq)$/i;
  const isRawDoc = (d: SessionDoc) => RAW_RE.test(d.path) || !!d.thumb?.preview;
  const isEditedDoc = (d: SessionDoc) => {
    const e = d.edits;
    return e.repair > 0 || e.light > 0 || e.deform || e.lut || e.grade
      || !!e.enhance || !!e.channel || !!e.curves || !!e.levels;
  };
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
    setChannel("skin");
    setStrengthV(v);
    const now = performance.now();
    const send = () => {
      lastSend.current = performance.now();
      setStrength(strengthRef.current, skinStrengthOptions()).catch((e) => setDragNote(String(e)));
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
        // P2-2：勾了 16-bit 就按TIFF容器，保留用户的无损压缩选择发，
        // 不把JPEG容器冒充16-bit，也不向非TIFF格式递交旧TIFF压缩参数。
        const combo = reconcileExportCombo(exportBits16, exportFormat, exportTiffComp);
        return runExport(exportDir, {
          format: combo.format,
          quality: exportQuality,
          tile,
          scale: exportScale !== 1 ? exportScale : undefined,
          sharpen: exportSharpen > 0 ? exportSharpen : undefined,
          bitDepth: exportBits16 ? 16 : undefined,
          // 底片条多选集就是本批的清单；没选就只导当前这一张（引擎按 images 逐条记账）
          images: exportTargets.length ? exportTargets : undefined,
          // 导出侧 P0 的四格：中性位由引擎定，这里传用户显式选过的值
          outputProfile: exportProfile,
          tiffCompression: combo.tiffCompression,
          metadataIncludeGps: exportGps,
          conflictPolicy: exportConflict,
          watermark, layout: layoutModel.layout,
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

  useEmptyStateProbe(hasImage);
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
  const faceWhy = hasImage
    ? ((faceSt?.enabled?.length ?? faceCount) === 0
        // 人物被全部排除：告诉用户从哪里恢复，不复述内部状态字段。
        ? "画面中的人物已全部排除。请在上方人物栏重新选中需要调整的人物。"
          + "全图调色、曝光、白平衡、裁剪与磨皮仍可使用。"
        : faceCount > 1 && faceSt?.blocked
        ? `画面中有 ${faceCount} 个人物，请先在人物栏选择要调整的人物。`
          + `${(faceSt?.disabled_count ?? 0) > 0 ? `（已排除 ${faceSt?.disabled_count} 人）` : ""}`
          + "选定后即可单独调整面部与眼牙。"
        : faceCount > 1
          ? `当前仅对选中的人物 ${(faceSt?.index ?? 0) + 1} 生效。`
          : "未检测到可编辑的人脸。请换一张正面人像，或在人物栏中添加人物。")
    : "打开照片后即可使用。";
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
      case "lnx.batch.v1.conflict_policy": return batchPolicy;
      // 预设下拉读的两个都来自引擎：`last_applied` 是“套完而没被手改”那一个（参数比过
      // 才算），而不是前端记的“上次点了哪个按钮”。
      case "lnx.preset.v1.apply": {
        const la = presetState?.last_applied
        const p = la ? presetList.find((x) => x.id === la.id) : null
        return p ? presetLabel(p) : ""
      }
      case "lnx.batch.v1.module_scope":
        return effectiveScope.label;
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
      if (key.startsWith("lnx.batch.v1.") && (!hasImage || status?.ready_caps?.batch_preflight_protocol!==1)) return "需要已打开照片及支持预检的配套引擎。";
      if (key === "lnx.export.v1.start") {
      if (!pid || !engineAlive) return "图像处理服务未就绪，请稍候重试。";
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
    if (key.startsWith("lnx.skin.v1.") && skinMaskUnavailable(pc?.mask_nonzero_pixels)
        && !(key === "lnx.skin.v1.enabled" && (doc?.strength ?? 0) > 0))
      return "未找到置信度足够的皮肤区域，本次不会自动磨皮。可重新分析；不要把空蒙版当成已修好。";
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
    if (key === "lnx.batch.v1.conflict_policy") { setBatchPolicy(v); return; }
    if (key === "lnx.preset.v1.apply") { void onPresetApplyByName(v); return; }
    if (key === "lnx.batch.v1.module_scope") { setSyncScopeLabel(v); return; }
  }

  function p0rect(_key: string, rect: number[]) {
    void runCrop("set", rect).then(refreshStatus).catch((e) => setDragNote(String(e)));
  }

  /** 面板按钮那一批：名字到命令的映射只在这一处（每个键对应注册表的一条）。 */
  async function p0action(key: string) {
    try {
      if (key === "lnx.batch.v1.preflight" || key === "lnx.batch.v1.commit") {await onBatchSync();return;}
      if (key === "lnx.export.v1.start") { onExport(); return; }
      if (key === "lnx.preset.v1.save") { await onPresetSave(); return; }
      if (key === "lnx.history.v1.undo") { onHistory("undo"); return; }
      if (key === "lnx.history.v1.redo") { onHistory("redo"); return; }
      if (key === "lnx.import.v1.choose_files") { await onPickPath(false); return; }
      if (key === "lnx.import.v1.choose_folder") { await onPickPath(true); return; }
      if (key === "lnx.project.v1.create") { await projectFlow.perform("create"); return; }
      if (key === "lnx.project.v1.open") { await projectFlow.perform("open"); return; }
      if (key === "lnx.project.v1.save") { await projectFlow.perform("save"); return; }
      if (key.startsWith("lnx.task.v1.")) {
        const action = key.split(".").pop() as "pause" | "resume" | "cancel" | "retry";
        await runTask(action, liveTask?.task_id);
        await refreshStatus();
        return;
      }
    } catch (e) {
      projectFlow.reportError(e);
    }
  }

  // ── 预设与批量同步（LNX-P0-PRESET / LNX-P0-BATCH）─────────────────────
  // 两份事实都从 status.session 读（引擎随 session_state 报）：预设清单/错误/“现在等于
  // 哪个预设”，与同步台账/上一笔的结果。这里不扫目录、不记 batch_id、不自己数张数。
  const presetState = status?.session?.presets ?? null;
  const syncState = status?.session?.sync ?? null;
  const presetList = presetState?.list ?? [];
  const presetLabel = (p: (typeof presetList)[number]) => modulePresetLabel(p, presetList);
  /** 作用域候选只从引擎报的 transferable 模块里拼：注册表说不通的那格不进候选。 */
  const scopeChoices = batchScopeOptions(presetState?.modules ?? []);
  const effectiveScope = resolveBatchScope(scopeChoices, syncScopeLabel);
  const syncScopes = effectiveScope.ops.length ? scopeChoices : [effectiveScope, ...scopeChoices];
  const syncScopeOps = effectiveScope.ops;
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
    await refreshStatusWithErrors(true)
  }

  const whiteBalanceWorkflow=useWhiteBalanceWorkflow({documentId:doc?.document_id??'',
    reason:!status?.engine_alive?'引擎尚未就绪':status?.ready_caps?.white_balance_result_protocol!==1?'当前引擎不支持此操作，请更新匹配版本':!hasImage?'请先导入照片':exporting?'导出进行中':status?.edit_queue?.in_flight||status?.edit_queue?.pending?'有编辑操作正在处理':'照片状态正在同步',
    enabled:!!status?.engine_alive&&status?.ready_caps?.white_balance_result_protocol===1&&hasImage&&!exporting
      &&!!doc?.document_id&&status?.image?.load_id===doc.document_id&&!status?.edit_queue?.in_flight&&!status?.edit_queue?.pending},refreshFromEngine);
  const presetWorkflow=usePresetWorkflow({enabled:!!status?.engine_alive&&status?.ready_caps?.preset_result_protocol===1,
    editable:hasImage&&!exporting&&!status?.edit_queue?.in_flight&&!status?.edit_queue?.pending,
    documentId:doc?.document_id??''},presetState,refreshFromEngine,{ok:faceOk,why:faceWhy});
  const onPresetApplyByName=(label:string)=>presetWorkflow.applyByLabel(label);
  const onPresetSave=()=>presetWorkflow.save();

  const batchWorkflow=useBatchWorkflow({docs:selPaths,moduleScope:syncScopeOps,conflictPolicy:batchPolicy,
    sourceDocumentId:doc?.document_id??'',enabled:!!status?.engine_alive&&status?.ready_caps?.batch_preflight_protocol===1,
    label:effectiveScope.label},()=>{void refreshFromEngine().catch(e=>setDragNote(String(e)));});
  const onBatchSync=()=>batchWorkflow.start();
  const onBatchUndo=()=>syncState?.last?batchWorkflow.undo(syncState.last):undefined;

  // 空格按住出原图、松开回修好的那版（DoD §3 的“按住空格实时对拍”）。
  // 光标在输入框里或按钮上时不抢：那是用户在打字/激活控件。
  useEffect(() => {
    const busyTarget = (el: EventTarget | null) => {
      const n = el as HTMLElement | null;
      return !!n && (n.tagName === "INPUT" || n.tagName === "TEXTAREA"
        || n.tagName === "SELECT" || n.tagName === "BUTTON" || n.isContentEditable);
    };
    const down = (e: KeyboardEvent) => {
      if (document.querySelector('.batchReviewBackdrop')) return;
      if (e.code !== "Space" || e.repeat || busyTarget(e.target)) return;
      e.preventDefault();
      void cmpHold();
    };
    const up = (e: KeyboardEvent) => {
      if (e.code !== "Space" || busyTarget(e.target)) return;
      e.preventDefault();
      void cmpOff();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  // 引擎进程此刻在不在（M5-c）。报回缺失（新壳配旧宿主）时退回"看 pid"的旧行为，
  // 而不是当成"没在跑"——那会把刚起好的引擎显示成已死。
  const engineAlive = status?.engine_alive ?? !!pid;

  /** 图库的「已导出」：只认 export_done 里 out 真写出来的那些源图。 */
  useEffect(() => {
    const done = status?.export;
    if (!done?.images?.length) return;
    setExported((prev) => {
      let changed = false;
      const next = new Set(prev);
      for (const img of done.images) {
        if (img.path && img.out && !img.error && !next.has(img.path)) {
          next.add(img.path);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [status?.export]);

  const sourcePatchSupported=caps?.source_patch_capture_protocol===1&&caps?.source_patch_result_protocol===1;
  const sourcePatchAllowed=!!status?.engine_alive&&sourcePatchSupported&&hasImage&&!busy&&!exporting
    &&!!doc?.document_id&&status.image?.load_id===doc.document_id&&workspace==='retouch'
    &&compareMode==='single'&&!comparing&&!inspectionEnabled&&!cropOpen&&!whiteBalanceWorkflow.workflow.busy()
    &&(batchWorkflow.ui.phase==='closed'||batchWorkflow.ui.hidden===true);
  const sourcePatchCanStart=!status?.edit_queue?.in_flight&&!status?.edit_queue?.pending;
  const sourcePatch=useSourcePatchWorkflow({enabled:sourcePatchAllowed,canStart:sourcePatchCanStart,documentId:doc?.document_id??'',
    contextKey:JSON.stringify([pid,status?.doc_rev,status?.image?.load_id,workspace,compareMode,comparing,inspectionEnabled,cropOpen]),
    reason:!sourcePatchSupported?'当前引擎不支持来源区域修补，请更新匹配版本':!sourcePatchCanStart?'正在等待命令队列空闲':'请等待编辑完成，并切回单视图代理预览'},refreshFromEngine);
  useEffect(()=>{if((brushOn||pickFace)&&sourcePatch.workflow.capturing()&&!sourcePatch.workflow.busy())sourcePatch.workflow.cancel('已切换工具，未提交的修补选区已取消');},[brushOn,pickFace,sourcePatch.workflow]);
  const wbPicker=useWhiteBalancePickerWorkflow({enabled:sourcePatchAllowed&&!sourcePatch.active&&!sourcePatch.pending&&caps?.white_balance_capture_protocol===1,
    canStart:sourcePatchCanStart,documentId:doc?.document_id??'',contextKey:JSON.stringify([pid,status?.doc_rev,status?.image?.load_id,workspace,compareMode,comparing,inspectionEnabled,cropOpen]),
    reason:caps?.white_balance_capture_protocol!==1?'当前引擎不支持白平衡输入取样，请更新匹配版本':'请结束其他操作，并切回单视图代理预览'},refreshFromEngine);
  useEffect(()=>{if((brushOn||pickFace)&&wbPicker.workflow.capturing()&&!wbPicker.workflow.busy())wbPicker.workflow.cancel('已切换工具，未提交的白平衡取样已取消');},[brushOn,pickFace,wbPicker.workflow]);
  const captureAllowed=!!status?.engine_alive && status?.ready_caps?.color_capture_protocol===1&&!sourcePatch.active&&!sourcePatch.pending&&!wbPicker.active&&!wbPicker.pending
    && !!doc?.document_id && status.image?.load_id===doc.document_id && workspace==='retouch'
    && compareMode==='single' && !comparing && !inspectionEnabled && !cropOpen && (batchWorkflow.ui.phase==='closed'||batchWorkflow.ui.hidden===true);
  const captureReason=captureAllowed?'':'请导入图片，并在单视图代理预览中取色';
  const colorSampler=useColorSampler({documentId:doc?.document_id??'',revision:status?.doc_rev??-1,
    allowed:captureAllowed,reason:captureReason},brushOn||pickFace);
  return (
    <div className={"app ws-" + workspace}>
      <header className="topbar">
        <span className="brand">LumaRetouch</span>
        <button className="tb openPhoto"
                onClick={() => { setWorkspace("retouch"); void openAndImport(); }}
                disabled={busy}>
          打开照片
        </button>
        <nav className="wsTabs" aria-label="工作区">
          <button className={workspace === "projects" ? "on" : ""}
                  onClick={() => setWorkspace("projects")}>项目管理</button>
          <button className={workspace === "library" ? "on" : ""}
                  onClick={() => setWorkspace("library")}>图库</button>
          <button className={workspace === "retouch" ? "on" : ""}
                  onClick={() => setWorkspace("retouch")}>精修</button>
          <button className={workspace === "creative" ? "on" : ""}
                  onClick={() => setWorkspace("creative")}>创意</button>
          <button className={workspace === "export" ? "on" : ""}
                  onClick={() => setWorkspace("export")}>批量导出</button>
        </nav>
        <span className="topHint">
          {hasImage ? (strip?.current?.split("/").pop() ?? "当前照片") : "本地 · 离线"}
        </span>
        <button className="tb primary exportBtn"
                onClick={() => setWorkspace("export")}
                disabled={!hasImage}>
          导出照片
        </button>
      </header>

      {workspace === "retouch" && (
        <aside className="side" onInputCapture={(event)=>{
                const target=event.target;
                if(target instanceof Element && target.closest('[data-readonly-scopes]'))return;
                if(target instanceof HTMLSelectElement || (target instanceof HTMLInputElement
                  && ['range','number','color','checkbox'].includes(target.type)))notifyInspectionEditIntent();
              }}>
          <RetouchPanel whiteBalanceBusy={whiteBalanceWorkflow.workflow.busy()||wbPicker.active||wbPicker.pending} whiteBalancePanel={<WhiteBalanceControls owner={whiteBalanceWorkflow} value={doc?.exposure} pickerBusy={wbPicker.active||wbPicker.pending||sourcePatch.active||sourcePatch.pending} picker={<WhiteBalancePickerControls owner={wbPicker} onStart={()=>{setBrushOn(false);setPickFace(false);colorSampler.cancel();void wbPicker.workflow.start();}}/>}/>} presetPanel={<PresetPanel workflow={presetWorkflow}/>} status={status} doc={doc} hasImage={hasImage}
                        sourcePatchPanel={<SourcePatchPanel owner={sourcePatch} blocked={wbPicker.active||wbPicker.pending} onStart={()=>{if(wbPicker.active||wbPicker.pending)return;setBrushOn(false);setPickFace(false);colorSampler.cancel();void sourcePatch.workflow.start();}}/>}
                        colorSamplePanel={<ColorSamplePanel sampler={colorSampler} reason={captureReason}
                          canArm={captureAllowed&&!status?.edit_queue?.in_flight&&!status?.edit_queue?.pending}
                          onArm={()=>{setBrushOn(false);setPickFace(false);colorSampler.arm();}}/>}
                        faceOk={faceOk} faceWhy={faceWhy}
                        note={setDragNote} onDone={requestPanelRefresh}
                        thumb={strip?.current ? thumbs[strip.current] : undefined}
                        faceScope={faceScope} onFaceScope={setFaceScope}
                        brush={{ on: brushOn, mode: brushMode, radius: brushRadius }}
                        onBrush={(patch) => {
                          if (patch.on !== undefined) setBrushOn(patch.on);
                          if (patch.mode) setBrushMode(patch.mode);
                          if (patch.radius !== undefined) setBrushRadius(patch.radius);
                        }}
                        onOpenCrop={() => setCropOpen(true)}
                        onFaceAdd={() => {
                          setPickFace(true);
                          setDragNote("在画面中框选一张人脸，松手即可添加人物");
                        }}
                        faceAdding={pickFace} />
        </aside>
      )}

      <main className="stage">
        <SourcePatchStatus owner={sourcePatch}/><WhiteBalancePickerStatus owner={wbPicker}/>
        {!!((project?.changed_count ?? 0) + (project?.missing_count ?? 0)) && (
          <section className="projectSourceWarning" role="alert" aria-label="工程原片校验提醒">
            <strong>工程原片需要核对</strong>
            <p>打开工程时发现 {project?.changed_count ?? 0} 张原片内容已改变，
              {project?.missing_count ?? 0} 张原片缺失。旧编辑参数可能不再适用，导出前请核对原片与修图效果。
              保存工程不会自动消除此提醒；恢复正确原片后重新打开工程可再次校验。</p>
            <details><summary>查看原片路径（最多显示各 12 项）</summary>
              <ul>{project?.changed?.map((item) => <li key={"changed:" + item.path}>内容改变：{item.path}</li>)}
                {project?.missing?.map((item) => <li key={"missing:" + item.path}>原片缺失：{item.path}</li>)}</ul>
            </details>
          </section>
        )}
        {workspace === "retouch" && (
          <>
            <div className="stageBody">
              {hasImage && (
                <div className="viewBar" role="toolbar" aria-label="视图模式">
                  <button className={compareMode === "single" ? "on" : ""}
                          onClick={() => setCompareMode("single")}>单视图</button>
                  <button className={compareMode === "split" ? "on" : ""}
                          onClick={() => setCompareMode("split")}>并排对比</button>
                  <button className={compareMode === "swipe" ? "on" : ""}
                          onClick={() => setCompareMode("swipe")}>卷帘分屏</button>
                  <span className="vbSep" />
                  <button className={comparing ? "on" : ""}
                          onPointerDown={(e) => { void cmpOn(e); }}
                          onPointerUp={() => { void cmpOff(); }}
                          onLostPointerCapture={() => { void cmpOff(); }}
                          disabled={compareMode !== "single"}
                          title="按住查看原图（也可以按住空格）">按住看原图</button>
                  <button onClick={() => setCropOpen(true)}
                          title="裁剪与旋转">裁剪</button>
                  {compareMode !== "single" && (
                    <span className="vbState">{hasOriginal ? "原图已就绪" : "正在取原图…"}</span>
                  )}
                </div>
              )}
              <Viewer colorSampler={colorSampler} sourcePatch={sourcePatch} whiteBalancePicker={wbPicker}
                view={view} onView={(v) => {
                  // 滚轮/捏合改了倍率就退出 1:1；平移不算，仍是同一像素密度
                  if (v.fit) setInspectionEnabled(false);
                  if (v.fit || v.zoom !== view.zoom) setOneToOne(false);
                  setView(v);
                }}
                paintLocked={!view.fit || view.zoom !== 1 || view.x !== 0 || view.y !== 0}
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
                compareMode={compareMode}
                swipe={swipe}
                onSwipe={setSwipe}
                originalFrame={originalFrame}
                onFitScale={setFitScale}
                inspection={{enabled:inspectionEnabled,oneToOne,comparing,key:inspectionKey,width:inspectionSize[0],height:inspectionSize[1]}}
                onInspectionState={setInspectionState}
              />
              {hasImage && (
                <div className="zoomBar" role="group" aria-label="缩放">
                  <button className={view.fit ? "on" : ""} onClick={zoomFit}
                          title="适应窗口">适合</button>
                  <button className={oneToOne ? "on" : ""} onClick={zoomOne}
                          title="按原始图像尺寸查看 1:1，停下操作后加载当前视口的精细像素；再次点击可重试">100%</button>
                  {inspectionEnabled && (
                    <span className="zoomProxyTag" role="status" title={inspectionState.message}>
                      {compareMode!=='single'||comparing?'代理对比':inspectionState.state==='ready'?'原图精细':inspectionState.state==='loading'?'精细预览加载中':'代理预览'}
                    </span>
                  )}
                  <span className={"zoomRead" + (view.fit || oneToOne ? " srOnly" : "")}>
                    {zoomPct}
                  </span>
                </div>
              )}
              {!hasImage && (
                <div className="emptyStage" role="button" tabIndex={0} aria-busy={busy}
                     aria-label={t("empty.open")}
                     onClick={() => void openAndImport()}
                     onKeyDown={(e) => {
                       if (e.key === "Enter" || e.key === " ") { e.preventDefault(); void openAndImport(); }
                     }}>
                  <div className="emptyCard">
                    <div className="emptyGlyph" aria-hidden="true">＋</div>
                    <div className="emptyTitle">{busy ? "正在打开…" : t("empty.open")}</div>
                    <div className="emptyHint">{t("empty.hint")}</div>
                  </div>
                </div>
              )}
              {(pathErr || exportErr || dragNote) && (
                <div className="toast">{exportErr || pathErr || dragNote}</div>
              )}
            </div>

            {strip && strip.count > 0 && (
              <>
                <BatchActions count={selPaths.length} scopes={syncScopes} scope={effectiveScope.label}
                  policy={batchPolicy} onScope={setSyncScopeLabel} onPolicy={setBatchPolicy} note={syncNote}
                  ready={hasImage&&status?.ready_caps?.batch_preflight_protocol===1} busy={['committing','preflighting'].includes(batchWorkflow.ui.phase)}
                  unresolved={batchWorkflow.ui.phase==='uncertain'} canUndo={!!syncState?.last} onReview={onBatchSync} onUndo={onBatchUndo}/>
              <section className="gallery">
                <div className="strip">
                  {strip.docs.map((d) => {
                    const rate = ratingOf(d);
                    const flag = d.label ?? "";
                    return (
                      <div key={d.path}
                           className={"cell" + (d.loaded ? " on" : "")
                             + (sel.has(d.path) ? " sel" : "") + (d.trashed ? " trashed" : "")}
                           role="button" tabIndex={0}
                           title={d.name}
                           onClick={(e) => onCellClick(e as unknown as React.MouseEvent, d.index, d.path)}
                           onKeyDown={(e) => {
                             if (e.key === "Enter") onPickDoc(d.index);
                           }}>
                        {d.thumb && thumbs[d.path] ? (
                          <img alt={d.name} width={d.thumb.w} height={d.thumb.h}
                               src={`data:image/jpeg;base64,${thumbs[d.path]}`} />
                        ) : (
                          <span className="ph">…</span>
                        )}
                        <span className="cellFlag"
                              style={flag && FLAG_COLOR[flag] ? { background: FLAG_COLOR[flag] } : undefined}
                              title={flag ? `色标：${flag}（点击更换）` : "色标（点击设置）"}
                              onClick={(e) => { e.stopPropagation(); void cycleFlag(d); }} />
                        <span className="cellStars" onClick={(e) => e.stopPropagation()}>
                          {[1, 2, 3, 4, 5].map((n) => (
                            <button key={n} className={n <= rate ? "on" : ""}
                                    title={`${n} 星（再点一次清零）`}
                                    onClick={() => void setRating(d, n)}>★</button>
                          ))}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </section>
              </>
            )}
          </>
        )}

        {workspace === "projects" && <ProjectWorkspace workflow={projectFlow}
          project={project} projectSuffix={projSuffix} hasImage={hasImage}
          onEnterRetouch={() => setWorkspace("retouch")} />}

        {workspace === "library" && (
          <section className="library">
            <div className="libHead">
              <div>
                <h2>图库</h2>
                <span>{strip?.count ?? 0} 张照片{sel.size ? ` · 已选 ${sel.size}` : ""}</span>
              </div>
              <button className="chip" onClick={() => void openAndImport()}>
                打开照片
              </button>
            </div>
            {strip && strip.docs.length > 0 ? (
              <div className="libGrid">
                {strip.docs.map((d) => (
                  <button key={d.path}
                          className={"libCard" + (d.loaded ? " cur" : "")}
                          onClick={() => { onPickDoc(d.index); setWorkspace("retouch"); }}>
                    <span className="libThumb">
                      {d.thumb && thumbs[d.path]
                        ? <img alt={d.name} src={`data:image/jpeg;base64,${thumbs[d.path]}`} />
                        : <span className="ph">…</span>}
                    </span>
                    <span className="libMeta">
                      <span className="libName">{d.name}</span>
                      <span className="libTags">
                        {isRawDoc(d) && <em className="tag raw">RAW</em>}
                        {isEditedDoc(d) && <em className="tag edited">已编辑</em>}
                        {exported.has(d.path) && <em className="tag done">已导出</em>}
                      </span>
                      <span className="libStars">
                        {"★".repeat(ratingOf(d))}{"☆".repeat(5 - ratingOf(d))}
                      </span>
                    </span>
                    {d.label && FLAG_COLOR[d.label] && (
                      <i className="libFlag" style={{ background: FLAG_COLOR[d.label] }} />
                    )}
                  </button>
                ))}
              </div>
            ) : (
              <div className="libEmpty" role="button" tabIndex={0}
                   onClick={() => void openAndImport()}
                   onKeyDown={(e) => { if (e.key === "Enter") void openAndImport(); }}>
                <b>打开照片，开始第一批精修</b>
                <span>支持 JPEG / PNG / TIFF / WebP / DNG；原片只读，编辑写工程记录</span>
              </div>
            )}
          </section>
        )}

        {workspace === "creative" && (
          <section className="creativeView">
            <div className="creativeHead">
              <div>
                <h2>创意</h2>
                <span>让照片拥有更多表达</span>
              </div>
              <button className="chip" disabled={!hasImage}
                onClick={() => setWorkspace("retouch")}>回到画布</button>
            </div>
            <div className="creativeBody">
              <div className="creativeCards">
                {TOOL_CATEGORIES.map((cat) => (
                  <div className="cGroup" key={cat}>
                    <h3>{cat}</h3>
                    <div className="cCards">
                      {TOOLS.filter((t) => t.category === cat).map((tool) => {
                        const wired = tool.name.includes("智能消除");
                        return (
                          <button key={tool.id}
                            className={"cCard" + (wired ? " on" : " off")}
                            disabled={!wired || !hasImage}
                            title={wired
                              ? "在画布上使用消除笔"
                              : "该工具将在后续版本提供"}
                            onClick={() => {
                              if (!wired) return;
                              setWorkspace("retouch");
                              setBrushMode("heal");
                              setBrushOn(true);
                            }}>
                            <b>{tool.name}</b>
                            <span>{(tool.interaction || tool.output || "").slice(0, 46)}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
              <aside className="layerPanel">
                <h3>图层与历史</h3>
                <ul>
                  <li><span>基础图</span><em>只读</em></li>
                  <li><span>高低频磨皮</span><em>{doc?.strength ? "已启用" : "未启用"}</em></li>
                  <li><span>面部重塑</span><em>{Object.values(doc?.deform.amounts ?? {}).some((v) => v)
                    ? "已启用" : "未启用"}</em></li>
                  <li><span>色彩与风格</span><em>{doc?.lut.lit ? "LUT 已启用" : "未启用"}</em></li>
                  <li><span>眼牙增强</span><em>{doc?.enhance?.built ? "已启用" : "未启用"}</em></li>
                  <li><span>裁剪与旋转</span><em>{doc?.crop?.lit ? "已启用" : "未启用"}</em></li>
                </ul>
                <div className="layerHist">
                  撤销 {doc?.history.undo_steps ?? 0} 步 · 重做 {doc?.history.redo_steps ?? 0} 步
                </div>
                <div className="layerHist">
                  {strip?.docs.length ?? 0} 张在底片条 · 选中 {sel.size} 张
                </div>
              </aside>
            </div>
          </section>
        )}

        {workspace === "export" && (
          <section className="exportView">
            <div className="exportQueue">
              <div className="qHead">
                <h2>批量导出</h2>
                <span>{exportTargets.length} 张 · {exporting
                  ? `导出中 ${(status?.export_progress?.index ?? 0) + 1}/${status?.export_progress?.total ?? 0}`
                  : status?.export
                    ? `上一批 ${status.export.total} 张 · 失败 ${status.export.failed}`
                    : "空闲"}</span>
              </div>
              {exporting && (
                <div className="qBar"><i style={{ width: `${Math.round(
                  ((status?.export_progress?.index ?? 0) + 1)
                  / Math.max(1, status?.export_progress?.total ?? 1) * 100)}%` }} /></div>
              )}
              <div className="qList">
                {exportTargets.length ? exportTargets.map((p) => {
                  const d = strip?.docs.find((x) => x.path === p);
                  const done = status?.export?.images?.find((i) => i.path === p);
                  const now = status?.export_progress?.path === p;
                  const state = done ? (done.error ? "失败" : "已完成")
                    : now ? "导出中" : "待导出";
                  return (
                    <div className={"qRow" + (done ? (done.error ? " bad" : " ok") : "")}
                         key={p} title={done?.error}>
                      <span className="qName">{d?.name ?? p.split("/").pop() ?? p}</span>
                      <span className="qFmt">{exportBits16 ? "16-bit TIFF"
                        : exportFormat.toUpperCase()}</span>
                      <em>{state}</em>
                      <WatermarkReceipt outputs={done?.outputs}/>
                    </div>
                  );
                }) : <div className="qEmpty">先在底片条或图库选择要导出的照片</div>}
              </div>
            </div>

            <div className="exportCard">
              <h2>导出设置</h2>
              <div className="exGrid">
                <label>格式
                  <select value={exportFormat} onChange={(e) => setExportFormat(e.target.value)}
                          disabled={exportBits16}
                          title={exportBits16 ? "16-bit 输出使用 TIFF，支持无损压缩，格式已锁定" : undefined}>
                    <option value="jpg">JPEG</option>
                    <option value="png">PNG</option>
                    <option value="tif">TIFF</option>
                    <option value="webp">WebP</option>
                  </select>
                </label>
                <label>TIFF 无损压缩
                  <select value={exportTiffComp}
                          disabled={!exportBits16 && !["tif", "tiff"].includes(exportFormat)}
                          onChange={(e) => setExportTiffComp(e.target.value)}>
                    <option value="none">无压缩</option>
                    <option value="deflate">Deflate（无损）</option>
                    <option value="lzw">LZW（无损）</option>
                  </select>
                </label>
                <label>质量
                  <input type="range" min={60} max={100} value={exportQuality}
                         onChange={(e) => setExportQuality(+e.target.value)} />
                  <em>{exportQuality}</em>
                </label>
                <label>尺寸
                  <select value={exportScale} onChange={(e) => setExportScale(+e.target.value)}>
                    <option value={1}>1× 原尺寸</option>
                    <option value={2}>2×</option>
                    <option value={3}>3×</option>
                    <option value={4}>4×</option>
                  </select>
                </label>
                <label>色彩空间 ICC
                  <select value={exportProfile} onChange={(e) => setExportProfile(e.target.value)}>
                    <option value="srgb">sRGB（嵌入 ICC）</option>
                    <option value="source">跟随源文件 ICC</option>
                    <option value="adobergb" disabled>AdobeRGB</option>
                    <option value="display_p3" disabled>Display P3</option>
                  </select>
                </label>
                <label>同名冲突
                  <select value={exportConflict} onChange={(e) => setExportConflict(e.target.value)}>
                    <option value="skip_and_report">跳过并报告</option>
                    <option value="recheck">重新检查</option>
                  </select>
                </label>
                <label className="exCheck">
                  <input type="checkbox" checked={exportBits16}
                         onChange={(e) => {
                           setExportBits16(e.target.checked);
                           // 切 16-bit 同时把面板格式收到 TIFF，不让控件停在会被后端拒的 jpg
                           if (e.target.checked) setExportFormat("tif");
                         }} />
                  16-bit TIFF
                </label>
                <label className="exCheck">
                  <input type="checkbox" checked={exportGps}
                         onChange={(e) => setExportGps(e.target.checked)} />
                  写入 GPS
                </label>
              </div>
              <LayoutControls model={layoutModel} disabled={exporting} selected={exportTargets.length || (hasImage ? 1 : 0)} receipt={status?.export?.layout_result}/>
              <WatermarkControls value={watermark} onChange={setWatermark} disabled={exporting} storageError={watermarkStorageError}/>
              <label className="exDir">输出目录
                <input value={exportDir} onChange={(e) => setExportDir(e.target.value)} />
              </label>
              <div className="exFoot">
                <span>{exportTargets.length > 1
                  ? `本批 ${exportTargets.length} 张 · 按底片条记账`
                  : "单张导出 · 原片只读"}</span>
                <button className="tb primary" onClick={onExport}
                        disabled={!hasImage || exporting}>
                  {exporting ? "导出中…" : "开始导出"}
                </button>
              </div>
            </div>
          </section>
        )}
      </main>
      <BatchReview state={batchWorkflow.ui} onCommit={batchWorkflow.commit} onReview={batchWorkflow.start} onQuery={batchWorkflow.query} onAcknowledge={batchWorkflow.acknowledgeInspection} onClose={batchWorkflow.close}/>
      <CropModal open={cropOpen}
        imgW={status?.image?.w ?? 0} imgH={status?.image?.h ?? 0}
        crop={doc?.crop ?? null}
        onClose={() => setCropOpen(false)}
        onApply={(rect, rot) => {
          runCrop("set", rect, rot)
            .then(() => { void refreshStatus(); setCropOpen(false); })
            .catch((e) => setDragNote(String(e)));
        }}
        onClear={() => {
          runCrop("clear")
            .then(() => { void refreshStatus(); setCropOpen(false); })
            .catch((e) => setDragNote(String(e)));
        }} />
    </div>
  );
}
