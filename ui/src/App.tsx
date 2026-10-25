import {useGlowWorkspaceBinding} from './lightGlow/useGlowWorkspaceBinding';
import {LightGlowWorkspaceHost} from './lightGlow/LightGlowWorkspaceHost';
import {GLOW_PROTOCOL, validGlowCapability} from './lightGlow/model';
import {guardCreativeWork} from './workspaces/guardCreativeWork';
import {useLensBlur} from './lensBlur/useLensBlur';
import {LensWorkspaceHost} from './lensBlur/LensWorkspaceHost';
import {useExpressionReplacement} from './expressionReplacement/useExpressionReplacement';
import {ExpressionWorkspaceHost} from './expressionReplacement/ExpressionWorkspaceHost';
import {HealBrushPanel,HealBrushStatus} from './healBrush/HealBrushPanel';
import {useCanvasGuides} from './canvasGuides/useCanvasGuides';
import {useGuideModeGuards} from './canvasGuides/useGuideModeGuards';
import {GuideControls} from './canvasGuides/GuideControls';
import {CreativeWorkspace} from './creativeLayers/CreativeWorkspace';
import {useSelectionBinding} from './creativeLayers/useSelectionBinding';
import {useCreativeWorkspace} from './creativeLayers/useCreativeWorkspace';
import {ExportDestinationPanel} from './exportDestination/ExportDestinationPanel';
import {initialDestination, type DestinationPreview} from './exportDestination/model';
import {exportDestinationApi, INSPECTION_EDIT_INTENT} from './native';
import {settleCurveEdit} from './curveEditBarrier';
import {VirtualCopyControls} from './virtualCopies/VirtualCopyControls';
import {FilmstripGallery} from './libraryQuery/Gallery';
import {LibraryWorkspace} from './libraryQuery/LibraryWorkspace';
import {LibraryQueryControls} from './libraryQuery/Controls';
import {useLibraryQuery} from './libraryQuery/useLibraryQuery';
import {ratingOf,flagOf} from './libraryQuery/model';
import {useBackgroundMaterialHost, BackgroundMaterialHost} from './backgroundMaterials';
import {IdBackgroundPanel} from './idBackground/IdBackgroundPanel';
import {ExportColorSpace} from './components/ExportColorSpace';
import {ExportMetadataOptions} from './components/ExportMetadataOptions';
import {useNeckWorkflow} from './neckShape/useNeckWorkflow';
import {useShoulderWorkflow} from './shoulderShape/useShoulderWorkflow';
import {BodyShapeTools} from './legShape/BodyShapeTools';
import {useLegWorkflow} from './legShape/useLegWorkflow';
import {useArmWorkflow} from './armShape/useArmWorkflow';
import {useWaistWorkflow} from './waistShape/useWaistWorkflow';
import {useLegLengthWorkflow} from './legLength/useLegLengthWorkflow';
import {useTorsoLengthWorkflow} from './torsoLength/useTorsoLengthWorkflow';
import {useWaistLengthWorkflow} from './waistLength/useWaistLengthWorkflow';
import {useHeadSizeWorkflow} from './headSize/useHeadSizeWorkflow';
import {useBodySlimWorkflow} from './bodySlim/useBodySlimWorkflow';
import {useHairColourPort} from './hairColour/useHairColourPort';
import {useOriginalCompareKeys} from './components/useOriginalCompareKeys';
import {useSampleLibraryHost} from './sampleLibrary/useSampleLibraryHost';
import {SampleLibraryHost,SampleLibraryLaunch} from './sampleLibrary/SampleLibraryHost';
import {WorkspaceTopbar} from './sampleLibrary/WorkspaceTopbar';
import {ConfirmedPeopleTransfer} from './people/ConfirmedPeopleTransfer';
import {usePeopleWorkflow} from './people/usePeopleWorkflow';
import {portraitAccess} from './people/portraitAccess';
import {peopleContext, peopleAssetContext, type PeopleContext} from './people/model';
import {ColourTransferTools} from './semanticColour/ColourTransferTools';
import {RetouchToolActivity,type ToolLocation} from "./toolRouting/RetouchToolActivity";
import { neutral as neutralWrinkles } from "./facialWrinkles/model";
import {TargetSizeControls} from './exportTargetSize/TargetSizeControls';
import {initialTargetSize, targetSizePolicy} from './exportTargetSize/model';
import {targetSizeArguments} from './exportTargetSize/nativePort';
import {ExportQueuePanel} from './components/ExportQueuePanel';
import {defaultMaskTransfer,LOCAL_GRADE_OP} from './localMasks/transfer';
import {ColorActionStatus} from './colorActions/ColorActionControls';
import {useRetouchCaptureWorkflows} from './localMasks/useRetouchCaptureWorkflows';
import {useCommonBackgroundWorkflow} from './commonBackground/useCommonBackgroundWorkflow';
import {useFringeRepairWorkflow} from './fringeRepair/useFringeRepairWorkflow';
import {FringeRepairPanel} from './fringeRepair/FringeRepairPanel';
import {CommonBackgroundPanel} from './commonBackground/CommonBackgroundPanel';
import {createRetouchToolSlots} from './studioBackground/RetouchToolsPanels';
import {LocalMaskPanel,LocalMaskStatus} from './localMasks/LocalMaskPanel';
import {EffectRecoveryWorkspace} from './effectRecovery/EffectRecoveryPanel';
import {LiveGradeStatus} from './localMasks/LiveGradeControls';
import {WhiteBalancePickerControls,WhiteBalancePickerStatus} from './whiteBalance/WhiteBalancePickerControls';
import {LayoutControls} from "./layout/LayoutControls";
import {useLayoutSettings} from "./layout/model";
import {WatermarkControls} from "./watermark/WatermarkControls";
import {useWatermarkSettings} from "./watermark/model";
import {useWhiteBalanceWorkflow} from "./whiteBalance/useWhiteBalanceWorkflow";
import {WhiteBalanceControls} from "./whiteBalance/WhiteBalanceControls";
import {CloneStampPanel,CloneStampStatus} from './cloneStamp/CloneStampPanel';
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
import {useEyelinerPicker} from './eyeliner/useEyelinerPicker';
import {EyelinerPanel} from './eyeliner/EyelinerPanel';
import {useEyelashPicker} from './eyelash/useEyelashPicker';
import {IrisMakeupPanel} from './irisMakeup/IrisMakeupPanel';
import {EyelashPanel} from './eyelash/EyelashPanel';
import {useBrowMakeupPicker} from './browMakeup/useBrowMakeupPicker';
import {BrowMakeupPanel} from './browMakeup/BrowMakeupPanel';
import {useLipstickPicker} from './lipstick/useLipstickPicker';
import {LipstickPanel} from './lipstick/LipstickPanel';
import {useBlushPicker} from './blushMakeup/useBlushPicker';
import {BlushMakeupPanel} from './blushMakeup/BlushMakeupPanel';
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
import { REGISTRY, keyOf, sectionTitleOf, type SectionId } from "./p0";
import { clickRle } from "./brush";
import { exportGpsForDepth, is16BitExportFormat, reconcileExportCombo, reconcileExportFormat } from "./exportModel";
import { notifyInspectionEditIntent } from "./native";
import type { InspectionUiState } from "./inspectionController";
import { t, type MsgKey } from "./i18n";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import {
  benchStart, benchStats, engineStatus, loadImage, m0Env, parseFrameHead, peekFrame,
  enhanceStateOf,
  report, runDeform, runEnhance, runFace,
  fetchFilmstrip, runExport, runGrade, runHistory, runHsl, runLight, runLut, runPick, runSession, runBackground,
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
  const [glowOpen,setGlowOpen]=useState(false);
  const [lensOpen,setLensOpen]=useState(false);
  const [expressionOpen,setExpressionOpen]=useState(false);
  const armBusyRef=useRef(false);
  const fringeBusyRef=useRef(false);
  const creativeRoute=useRef<{active:boolean;pending:boolean;importPaths:(paths:string[])=>Promise<void>;history:(direction:'undo'|'redo')=>Promise<void>}|null>(null);

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
  const faceAddContext = useRef<PeopleContext | undefined>(undefined);
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
    ...neutralWrinkles(), sclera: 0, iris: 0, teeth: 0, dark_circles: 0, eye_bags: 0, veins: 0, catchlight_left: 0, catchlight_right: 0,
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
  const [destinationPolicy, setDestinationPolicy] = useState(initialDestination);
  const [destinationPreview, setDestinationPreview] = useState<DestinationPreview|null>(null);
  const [destinationBusy, setDestinationBusy] = useState(false);
  const destinationGeneration = useRef(0);
  const destinationSubmitting = useRef(false);
  const destinationPreviewRunning = useRef(false);
  const destinationInput = useRef('');
  const invalidateDestination = useCallback(() => {
    destinationGeneration.current++; setDestinationPreview(null);
  }, []);
  useEffect(() => {
    window.addEventListener(INSPECTION_EDIT_INTENT, invalidateDestination);
    return () => window.removeEventListener(INSPECTION_EDIT_INTENT, invalidateDestination);
  }, [invalidateDestination]);
  const [exportFormat, setExportFormat] = useState("jpg");
  const [idBackgroundBusy,setIdBackgroundBusy]=useState(false);
  const [exportQuality, setExportQuality] = useState(95);
  const [exportTargetSize, setExportTargetSize] = useState({...initialTargetSize});
  // 放大（M7）：倍率与出片锐量。1 / 0.0 就是"不上这一层"——默认必须是原样出片，
  // 而不是一个没人同意的默认美化。
  const [exportScale, setExportScale] = useState(1);
  const [exportSharpen, setExportSharpen] = useState(0);
  // 16-bit PNG/TIFF：保留原生高位深源，并按逐图配方进入浮点编辑；显示代理不作出片源。
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
  const selAnchor = useRef<string | null>(null);
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
  const [toolLocation,setToolLocation] = useState<ToolLocation | null>(null);
  const locateTool = (featureId: string, path?: string) => {setWorkspace("retouch");setToolLocation(previous=>({featureId,path,serial:(previous?.serial??0)+1}));};
  // 裁剪/旋转模态（P0 lnx.crop.v1）
  const [cropOpen, setCropOpen] = useState(false);
  // 图库的「已导出」：只认引擎 export_done 里真的写出去的那几张
  // 对比：单视图 / 并排 / 卷帘；按住空格是单视图里的临时对比
  const [compareMode, setCompareMode] = useState<CompareMode>("single");
  const [swipe, setSwipe] = useState(0.5);
  const [originalFrame, setOriginalFrame] = useState<ParsedFrame | null>(null);
  const [hasOriginal, setHasOriginal] = useState(false);
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
    setEnhanceAmounts({ ...neutralWrinkles(), sclera: 0, iris: 0, teeth: 0, dark_circles: 0, eye_bags: 0, veins: 0, catchlight_left: 0, catchlight_right: 0, ...(ds.enhance?.amounts ?? {}) });
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
          setEnhanceAmounts({ ...neutralWrinkles(), sclera: 0, iris: 0, teeth: 0, dark_circles: 0, eye_bags: 0, veins: 0, catchlight_left: 0, catchlight_right: 0, ...(st.enhance.dropped_amounts ?? {}) });
        } else {
          setEnhanceAmounts({ ...neutralWrinkles(), sclera: 0, iris: 0, teeth: 0, dark_circles: 0, eye_bags: 0, veins: 0, catchlight_left: 0, catchlight_right: 0, ...st.enhance.amounts });
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
          // 换图回到适应窗口；人物目标由当前文档的 canonical people 状态恢复。
          setOneToOne(false);
          setInspectionEnabled(false);
          setView(VIEW_HOME);
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
      if(creativeRoute.current?.active||creativeRoute.current?.pending)return;
      if(armBusyRef.current||fringeBusyRef.current)return;
      if (document.querySelector('.batchReviewBackdrop, .recoveryWorkspace, .liquifyWorkspace, .studioWorkspace, .skyWorkspace, .commonBackgroundWorkspace, .fringeWorkspace, .fringeReceipt')) return;
      if (e.code !== "Space" || e.repeat || isText(e.target as HTMLElement)) return;
      e.preventDefault();
      if (!pid || comparingRef.current || compareMode !== "single") return;
      comparingRef.current = true;
      setComparing(true);
      void setCompare(true).catch((err) => setDragNote(String(err)));
    };
    const up = (e: KeyboardEvent) => {
      if (document.querySelector('.liquifyWorkspace, .studioWorkspace, .skyWorkspace, .commonBackgroundWorkspace, .fringeWorkspace, .fringeReceipt')) return;
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
      if(armBusyRef.current||fringeBusyRef.current)return;
      if (document.querySelector('.batchReviewBackdrop, .recoveryWorkspace, .liquifyWorkspace, .studioWorkspace, .skyWorkspace, .commonBackgroundWorkspace, .fringeWorkspace, .fringeReceipt')) return;
      if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k !== "z" && k !== "y") return;
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      e.preventDefault();
      const redo = k === "y" || e.shiftKey;
      if(creativeRoute.current?.active){void creativeRoute.current.history(redo?'redo':'undo');return;}
      if(creativeRoute.current?.pending)return;
      runHistory(redo ? "redo" : "undo")
        .then(() => refreshStatus())
        .catch((err) => setDragNote(String(err)));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [refreshStatus]);

  const projectFlow=useProjectWorkflow({projectId:status?.project?.project_id??'__recovery__',projectOpen:status?.project?.open===true,refresh:refreshStatus,notify:setDragNote,
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
    if(armBusyRef.current||fringeBusyRef.current){setDragNote('请先核对或等待当前调整请求完成，再切换照片。');return;}
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
    if(creativeRoute.current?.active){await creativeRoute.current.importPaths(raw);return;}
    if(creativeRoute.current?.pending){setDragNote('创意文档操作仍待核对，未切换照片。');return;}
    if(armBusyRef.current||fringeBusyRef.current){setDragNote('调整请求仍待完成，未导入拖入的照片。');return;}
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
    if (fringeBusyRef.current || !pid || comparingRef.current) return;
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
    if(sky.active||sky.pending||optics.active||optics.pending||fringe.active||fringe.pending||commonBackground.active||commonBackground.pending||studio.active||studio.pending||colorPicker.pending||manual.pending||recovery.pending||liveGrade.busy)return;colorPicker.workflow.cancel();recovery.workflow.cancel();manual.workflow.cancel();
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

  const library=useLibraryQuery(strip,refreshStatus,`${status?.doc_rev??0}:${status?.export?.out_dir??''}:${status?.export?.total_ms??''}`);
  const selectionSnapshot=useRef<{session:string;ids:Record<string,string>;trash:Record<string,boolean>}|null>(null);
  useEffect(()=>{
    const result=strip?.library_query;if(!result)return;
    const previous=selectionSnapshot.current;
    const trash=Object.fromEntries(strip.docs.map(d=>[d.document_id,d.trashed]));
    setSel(old=>{const next=new Set([...old].filter(path=>previous?.session===result.session_id
      &&previous.ids[path]===result.source_ids[path]&&!!result.source_ids[path]&&previous.trash[path]===trash[path]));
      return next.size===old.size?old:next;});
    if(previous?.session!==result.session_id||!result.document_ids.includes(selAnchor.current??''))selAnchor.current=null;
    selectionSnapshot.current={session:result.session_id,ids:result.source_ids,trash};
  },[strip]);
  const libraryControls=<LibraryQueryControls query={library.query} onChange={library.change}
    pending={library.pending||!library.supported} error={library.error} total={strip?.count??0}
    visible={library.docs.length} selected={sel.size}
    onSelectVisible={()=>setSel(prev=>new Set([...prev,...library.docs.map(d=>d.document_id)]))}
    onClearSelection={()=>{setSel(new Set());selAnchor.current=null;}}/>;
  async function cyclePick(d:SessionDoc){
    const next=flagOf(d)==='unflagged'?'accepted':flagOf(d)==='accepted'?'rejected':'unflagged';
    const tags=d.tags.filter(t=>!t.startsWith('flag:'));if(next!=='unflagged')tags.push(`flag:${next}`);
    try{await runProject('tag',{documentId:d.document_id,tags,label:d.label??''});await refreshStatus();}catch(e){setDragNote(String(e));}
  }
  /** 底片条的评分/色标：落在工程记录的 tags/label 上（不碰原图）。
   *  评分用保留标签 `rating:N`；色标用 label（红/黄/绿/蓝/紫）。 */
  async function setRating(d: SessionDoc, n: number) {
    const next = ratingOf(d) === n ? 0 : n;
    const tags = (d.tags ?? []).filter((x) => !x.startsWith("rating:"));
    if (next > 0) tags.push(`rating:${next}`);
    try {
      await runProject("tag", { documentId: d.document_id, tags, label: d.label ?? "" });
      await refreshStatus();
    } catch (e) { setDragNote(String(e)); }
  }
  async function cycleFlag(d: SessionDoc) {
    const order = ["", "红", "黄", "绿", "蓝", "紫"];
    const cur = order.indexOf(d.label ?? "");
    const next = order[(cur + 1) % order.length];
    try {
      await runProject("tag", { documentId: d.document_id, tags: d.tags ?? [], label: next });
      await refreshStatus();
    } catch (e) { setDragNote(String(e)); }
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
    const captured = faceAddContext.current; faceAddContext.current = undefined;
    const before = await engineStatus().catch(() => null);
    const errBefore = before?.last_error ?? null;
    const previousAdded = before?.face?.face?.manual?.added?.length ?? 0;
    try {
      await runFace("add", undefined, rect, captured);
    } catch (e) {
      setDragNote(String(e));
      return;
    }
    for (let i = 0; i < 40; i++) {
      await new Promise((r) => setTimeout(r, 250));
      const st = await engineStatus().catch(() => null);
      const err = st?.last_error ?? null;
      if (err && err !== errBefore) { setDragNote(err); return; }
      if (captured && st?.doc_report?.doc_state?.people?.binding.document_id !== captured.document_id) {setDragNote("照片已切换，原补脸结果未确认；未向新照片重发。"); return;}
      if ((st?.face?.face?.manual?.added?.length ?? 0) > previousAdded) {setDragNote("人脸区域已完成分析并加入当前照片。"); break;}
      if (i === 39) setDragNote("补脸结果尚未确认，请查看人物状态；未重发操作。");
    }
    await refreshStatus();
  }, [refreshStatus]);

  const onStroke = useCallback(
    (rle: number[][], pixels: number) => {
      if (brushMode === "heal") {
        setDragNote(t("retouch.repairing", { pixels }));
        setBrushOn(false);setDragNote("请使用审核式修复画笔面板，旧显示帧笔迹不会提交");
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
    runDeform("set", amounts, undefined, peopleContext(status?.doc_report?.doc_state?.people))
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
    void runEnhance("set", { [sub]: value } as Record<string, number>, peopleContext(status?.doc_report?.doc_state?.people)).then(() => {});
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
  function destinationOptions() {
    const combo = reconcileExportCombo(exportBits16, exportFormat, exportTiffComp);
    const target = targetSizePolicy(exportTargetSize, combo.format, exportBits16 ? 16 : 8);
    return {out_dir:exportDir, format:combo.format, ...(target ? {target_size:target} : {quality:exportQuality}),
      ...(exportTile.trim() ? {tile:Number(exportTile)} : {}),
      ...(exportScale !== 1 ? {scale:exportScale} : {}),
      ...(exportSharpen > 0 ? {sharpen:exportSharpen} : {}),
      ...(exportBits16 ? {bit_depth:16} : {}), output_profile:exportProfile,
      ...(combo.tiffCompression ? {tiff_compression:combo.tiffCompression} : {}),
      metadata_include_gps:exportGpsForDepth(exportBits16, exportGps), conflict_policy:exportConflict, watermark, layout:layoutModel.layout};
  }
  async function onPreviewDestination() {
    if (destinationPreviewRunning.current || destinationSubmitting.current) return;
    destinationPreviewRunning.current = true;
    setExportErr(''); setDestinationBusy(true); setDestinationPreview(null);
    try {
      await settleCurveEdit();
      const revision = ++destinationGeneration.current;
      const input = destinationInput.current;
      const result = await exportDestinationApi.preview({...destinationPolicy, chosen_root:exportDir},
        [...exportTargets], revision, destinationOptions());
      if (revision === destinationGeneration.current && input === destinationInput.current) setDestinationPreview(result);
    } catch (error) { setExportErr(String(error)); }
    finally { destinationPreviewRunning.current = false; setDestinationBusy(false); }
  }
  async function onExport() {
    if (destinationSubmitting.current || destinationPreviewRunning.current) return;
    const plan = destinationPreview;
    if (!plan || plan.intent_revision !== destinationGeneration.current) { setExportErr('请先预览导出位置'); return; }
    if (plan.entries.some(e=>e.disposition==='needs_confirmation')) { setExportErr('请选择改名或跳过冲突文件，然后重新预览'); return; }
    destinationSubmitting.current = true; setDestinationBusy(true); setExportErr('');
    try {
      await settleCurveEdit();
      if (plan.intent_revision !== destinationGeneration.current) throw new Error('编辑已变化，请重新预览导出位置');
      const before = (await engineStatus())?.last_error ?? null;
      const combo = reconcileExportCombo(exportBits16, exportFormat, exportTiffComp);
      await runExport(exportDir, {
        format:combo.format, ...targetSizeArguments(targetSizePolicy(exportTargetSize, combo.format, exportBits16 ? 16 : 8), exportQuality),
        tile:exportTile.trim() ? Number(exportTile) : undefined,
        scale:exportScale !== 1 ? exportScale : undefined,
        sharpen:exportSharpen > 0 ? exportSharpen : undefined,
        bitDepth:exportBits16 ? 16 : undefined, documentIds:[...exportTargets],
        outputProfile:exportProfile, tiffCompression:combo.tiffCompression,
        metadataIncludeGps:exportGpsForDepth(exportBits16, exportGps), conflictPolicy:exportConflict,
        watermark, layout:layoutModel.layout,
        destinationPolicy:{...destinationPolicy, chosen_root:exportDir},
        destinationPlanId:plan.plan_id, intentRevision:plan.intent_revision,
      });
      await refreshStatus(); await watchExportOutcome(before);
    } catch (error) { setExportErr(String(error)); }
    finally { destinationSubmitting.current=false; setDestinationBusy(false); invalidateDestination(); }
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
    if(library.pending||library.error)return;
    const target=library.docs.find(d=>d.index===index);if(!target)return;
    runSession("select", { index,selectedPath:target.path,documentId:target.document_id,sessionId:library.result?.session_id })
      .then(() => refreshStatus())
      .catch((e) => setDragNote(String(e)));
  }

  /** 一格的点击语义（图库的多选口径）：
   *  普通点=打开那一张；Ctrl/Cmd+点=加减选；Shift+点=从上一次锚点到这一格的连续段。
   *  打开一张不清空多选集：批量导出时"选中的还是那几张"这件事不能被一次浏览打乱。 */
  function onCellClick(e: React.MouseEvent, index: number, path: string) {
    if(library.pending||library.error)return;
    if (e.metaKey || e.ctrlKey) {
      setSel((prev) => { const n = new Set(prev); n.has(path) ? n.delete(path) : n.add(path); return n; });
      selAnchor.current = path;
      return;
    }
    if (e.shiftKey && selAnchor.current !== null) {
      const docs = library.docs;
      const anchor=docs.findIndex(d=>d.document_id===selAnchor.current), target=docs.findIndex(d=>d.document_id===path);
      if(anchor<0||target<0){selAnchor.current=path;return;}
      const a = Math.min(anchor,target), b = Math.max(anchor,target);
      setSel((prev) => { const n = new Set(prev);
        docs.slice(a,b+1).forEach((d) => n.add(d.document_id)); return n; });
      return;
    }
    selAnchor.current = path;
    onPickDoc(index);
  }

  /** 批量打标签：逐张发给引擎（tag 是整份替换语义，所以这里把已有标签并进去而不是覆盖）。 */
  async function onBatchTag() {
    const tag = batchTag.trim();
    if (!tag || !selPaths.length) return;
    for (const path of selPaths) {
      const row = strip?.docs.find((d) => d.document_id === path);
      const tags = Array.from(new Set([...(row?.tags ?? []), tag]));
      await runProject("tag", { documentId:path, tags }).catch((e) => setDragNote(String(e)));
    }
    await refreshStatus();
  }

  /** 批量进/出回收站：置的是工程记录里的标志位，源文件一个字节也不动（CORE-007）。 */
  async function onBatchTrash(toTrash: boolean) {
    window.dispatchEvent(new CustomEvent('lrt-virtual-copy-context',{detail:{documentIds:selPaths,action:toTrash?'trash':'restore'}}));
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
      await runPick("analyze", { ...(targets ? { indices: (strip?.docs??[]).filter(d=>targets.includes(d.document_id)).map(d=>d.index) } : {}), force, ...pickArms });
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
  const sampleLibrary = useSampleLibraryHost({
    enabled: !!status?.engine_alive && caps?.sample_library_protocol === 1, documentId: doc?.document_id ?? '',
    refreshKey: JSON.stringify([pid, status?.doc_rev, status?.image?.load_id, status?.edit_queue?.pending, status?.edit_queue?.in_flight, !!status?.export_progress]),
  });

  useEmptyStateProbe(hasImage);
  const exporting = !!status?.export_progress;
  const projSuffix = caps?.project_suffix ?? ".lrproject.json";
  /** 底片条上被选中的那几张（没选就只导当前这张） */
  const selPaths = (library.pending||library.error?[]:library.docs).filter(d=>sel.has(d.document_id)).map(d=>d.document_id);
  const exportTargets = sel.size ? selPaths : (hasImage ? (strip?.docs.filter(d=>d.loaded).map(d=>d.document_id)??[]) : []);
  const destinationSignature = JSON.stringify([destinationPolicy, exportDir, exportFormat, exportQuality, exportTargetSize,
    exportScale, exportSharpen, exportBits16, exportTiffComp, exportGps, exportConflict,
    exportProfile, exportTile, watermark, layoutModel.layout, exportTargets, status?.doc_rev, status?.engine_alive, workspace]);
  destinationInput.current = destinationSignature;
  useEffect(() => { invalidateDestination(); }, [destinationSignature, invalidateDestination]);
  const {ok: faceOk, why: faceWhy} = portraitAccess(status, doc, deformGeomWarn);
  const liveTask = tasks.length ? tasks[tasks.length - 1] : null;
  // 注册表上的格式名（jpeg/tiff）与引擎落盘用的后缀名（jpg/tif）不是一回事：
  // 映射只在这一处，两个名单都不在面板里重复刻
  const fmtOut: Record<string, string> = { jpeg: "jpg", tiff: "tif", png: "png", webp: "webp" };
  const fmtIn: Record<string, string> = { jpg: "jpeg", jpeg: "jpeg", tif: "tiff", tiff: "tiff", png: "png", webp: "webp" };

  function p0value(key: string): number | boolean | string | number[] | null | undefined {
    switch (key) {
      case "lnx.skin.v1.enabled": return (doc?.strength ?? 0) > 0;
      case "lnx.skin.v1.strength": return doc?.strength;
      case "lnx.blemish.v1.enabled": return healBrush.active||healBrush.pending;
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
      case "lnx.export.v1.metadata_include_gps": return exportGpsForDepth(exportBits16, exportGps);
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
        return (caps?.export_formats ?? ["jpg", "tif", "png"]).filter(x=>!exportBits16||is16BitExportFormat(x)).map((x) => fmtIn[x] ?? x);
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
    if (key === "lnx.export.v1.jpeg_quality" && exportBits16) return "16-bit PNG / TIFF 使用无损编码，不使用品质值。";
    if (key === "lnx.export.v1.metadata_include_gps" && exportBits16) return "16-bit PNG / TIFF 暂不支持 GPS；保留 8-bit 时的选择。";
    if (key === "lnx.export.v1.tiff_compression" && !["tif", "tiff"].includes(exportFormat)) return "TIFF 压缩只用于 TIFF；PNG 使用独立的无损编码。";
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
    if (key === "lnx.blemish.v1.enabled") {if(v)startReviewedHeal();else healBrush.workflow.cancel();return;}
    if (key === "lnx.export.v1.metadata_include_gps") { if (!exportBits16) setExportGps(v); return; }
    if (key === "lnx.skin.v1.enabled") { onStrength(v ? (strength <= 0 ? 0.5 : strength) : 0); return; }
    if (key === "lnx.mask.v1.analysis_enabled") {
      // 分析只能跑，不能“关”：掩膜是会话级常驻，关掉就是让面部微调当场失效。
      // 不假装能关：只在没跑过的时候按下去重跑一次。
      if (!v) { setDragNote("面部分析不提供“关掉”：掩膜常驻在本次会话里，要清空请重新导入这张图。"); return; }
      void runPrecompute().then(refreshStatus).catch((e) => setDragNote(String(e)));
    }
  }

  function p0enum(key: string, v: string) {
    if (key === "lnx.export.v1.format") { setExportFormat(reconcileExportFormat(exportBits16, fmtOut[v] ?? v)); return; }
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
  const [localMaskTransfer,setLocalMaskTransfer]=useState(defaultMaskTransfer);
  useEffect(()=>setLocalMaskTransfer(v=>({...v,groups:null})),[doc?.document_id]);
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

  const shoulders = useShoulderWorkflow(status, doc, refreshFromEngine);
  const peopleWorkflow = usePeopleWorkflow(status, doc, refreshFromEngine);
  const whiteBalanceWorkflow=useWhiteBalanceWorkflow({documentId:doc?.document_id??'',
    reason:!status?.engine_alive?'引擎尚未就绪':status?.ready_caps?.white_balance_result_protocol!==1?'当前引擎不支持此操作，请更新匹配版本':!hasImage?'请先导入照片':exporting?'导出进行中':status?.edit_queue?.in_flight||status?.edit_queue?.pending?'有编辑操作正在处理':'照片状态正在同步',
    enabled:!!status?.engine_alive&&status?.ready_caps?.white_balance_result_protocol===1&&hasImage&&!exporting
      &&!!doc?.document_id&&status?.image?.load_id===doc.document_id&&!status?.edit_queue?.in_flight&&!status?.edit_queue?.pending},refreshFromEngine);
  const presetWorkflow=usePresetWorkflow({enabled:!!status?.engine_alive&&status?.ready_caps?.preset_result_protocol===1,
    editable:hasImage&&!exporting&&!status?.edit_queue?.in_flight&&!status?.edit_queue?.pending,
    documentId:doc?.document_id??'',reviewContextKey:JSON.stringify([pid,status?.doc_rev,status?.image?.load_id]),sourceGroups:doc?.local_masks?.transfer_groups},presetState,refreshFromEngine,{ok:faceOk,why:faceWhy});
  const onPresetApplyByName=(label:string)=>presetWorkflow.applyByLabel(label);
  const onPresetSave=()=>presetWorkflow.save();

  const batchWorkflow=useBatchWorkflow({docs:selPaths,moduleScope:syncScopeOps,conflictPolicy:batchPolicy,localMaskTransfer,
    sourceDocumentId:doc?.document_id??'',enabled:!!status?.engine_alive&&status?.ready_caps?.batch_preflight_protocol===1,
    label:effectiveScope.label},()=>{void refreshFromEngine().catch(e=>setDragNote(String(e)));});
  const onBatchSync=()=>batchWorkflow.start();
  const onBatchUndo=()=>syncState?.last?batchWorkflow.undo(syncState.last):undefined;

  useOriginalCompareKeys(pid, cmpHold, cmpOff);

  // 引擎进程此刻在不在（M5-c）。报回缺失（新壳配旧宿主）时退回"看 pid"的旧行为，
  // 而不是当成"没在跑"——那会把刚起好的引擎显示成已死。
  const engineAlive = status?.engine_alive ?? !!pid;

  const fringe=useFringeRepairWorkflow({enabled:!!status?.engine_alive&&caps?.fringe_repair_protocol===1&&hasImage&&!busy&&!exporting&&!idBackgroundBusy
    &&!!doc?.document_id&&status.image?.load_id===doc.document_id&&workspace==='retouch'&&compareMode==='single'&&!comparing&&!inspectionEnabled&&!cropOpen&&!whiteBalanceWorkflow.workflow.busy()
    &&(batchWorkflow.ui.phase==='closed'||batchWorkflow.ui.hidden===true),canStart:!status?.edit_queue?.in_flight&&!status?.edit_queue?.pending&&!peopleWorkflow.state.pending&&!peopleWorkflow.state.uncertain,
    documentId:doc?.document_id??'',contextKey:JSON.stringify([pid,status?.doc_rev,status?.image?.load_id,workspace,compareMode,comparing,inspectionEnabled,cropOpen]),reason:'请等待当前编辑完成，再检查黑白边修复'},refreshFromEngine,async()=>{
      if(commonBackground.active||commonBackground.pending||sky.active||sky.pending||studio.active||studio.pending||optics.active||optics.pending||manual.active||manual.pending||recovery.active||recovery.pending||liveGrade.busy||colorPicker.active||colorPicker.pending||localMasks.active||localMasks.pending||healBrush.active||healBrush.pending||cloneStamp.active||cloneStamp.pending||sourcePatch.active||sourcePatch.pending||wbPicker.active||wbPicker.pending||shoulders.busy||legs.busy||arms.busy||waist.busy||length.busy||neck.busy||torso.busy||waistLength.busy||headSize.busy||bodySlim.busy)throw Error('请先关闭或完成当前工具，再检查黑白边修复');
      setBrushOn(false);setPickFace(false);colorSampler.cancel();blushPicker.cancel();lipstickPicker.cancel();eyelinerPicker.cancel();browMakeupPicker.cancel();eyelashPicker.cancel();
    });
  const commonBackground=useCommonBackgroundWorkflow({readbackEnabled:!!status?.engine_alive&&caps?.common_background_readback_protocol===1,engineKey:String(pid??''),enabled:!fringe.active&&!fringe.pending&&!!status?.engine_alive&&caps?.common_background_protocol===1&&hasImage&&!busy&&!exporting&&!idBackgroundBusy
    &&!!doc?.document_id&&status.image?.load_id===doc.document_id&&workspace==='retouch'&&compareMode==='single'&&!comparing&&!inspectionEnabled&&!cropOpen&&!whiteBalanceWorkflow.workflow.busy()
    &&(batchWorkflow.ui.phase==='closed'||batchWorkflow.ui.hidden===true),canStart:!status?.edit_queue?.in_flight&&!status?.edit_queue?.pending&&!peopleWorkflow.state.pending&&!peopleWorkflow.state.uncertain,
    documentId:doc?.document_id??'',contextKey:JSON.stringify([pid,status?.doc_rev,status?.image?.load_id,workspace,compareMode,comparing,inspectionEnabled,cropOpen]),reason:'请等待编辑完成，并返回单视图代理预览'},refreshFromEngine,async()=>{
      if(sky.active||sky.pending||studio.active||studio.pending||optics.active||optics.pending||manual.active||manual.pending||recovery.active||recovery.pending||liveGrade.busy||colorPicker.active||colorPicker.pending||localMasks.active||localMasks.pending||healBrush.active||healBrush.pending||cloneStamp.active||cloneStamp.pending||sourcePatch.active||sourcePatch.pending||wbPicker.active||wbPicker.pending||shoulders.busy||legs.busy||arms.busy||waist.busy||length.busy||neck.busy||torso.busy||waistLength.busy||headSize.busy||bodySlim.busy)throw Error('请先关闭或完成当前工具，再预览普通换底');
      setBrushOn(false);setPickFace(false);colorSampler.cancel();blushPicker.cancel();lipstickPicker.cancel();eyelinerPicker.cancel();browMakeupPicker.cancel();eyelashPicker.cancel();
    });
  const sourcePatchSupported=caps?.source_patch_capture_protocol===1&&caps?.source_patch_result_protocol===1;
  const sourcePatchAllowed=!fringe.active&&!fringe.pending&&!commonBackground.active&&!commonBackground.pending&&!!status?.engine_alive&&sourcePatchSupported&&hasImage&&!busy&&!exporting
    &&!!doc?.document_id&&status.image?.load_id===doc.document_id&&workspace==='retouch'
    &&compareMode==='single'&&!comparing&&!inspectionEnabled&&!cropOpen&&!whiteBalanceWorkflow.workflow.busy()
    &&(batchWorkflow.ui.phase==='closed'||batchWorkflow.ui.hidden===true);
  const sourcePatchCanStart=!status?.edit_queue?.in_flight&&!status?.edit_queue?.pending;
  const recoveryReport=doc?.effect_recovery;
  const {healBrush,sourcePatch,wbPicker,cloneStamp,localMasks,colorPicker,recovery,liveGrade,manual,studio,optics,sky}=useRetouchCaptureWorkflows({enabled:sourcePatchAllowed,canStart:sourcePatchCanStart,documentId:doc?.document_id??'',
    contextKey:JSON.stringify([pid,status?.doc_rev,status?.image?.load_id,workspace,compareMode,comparing,inspectionEnabled,cropOpen]),
    reason:!sourcePatchSupported?'当前引擎不支持源图取样，请更新匹配版本':!sourcePatchCanStart?'正在等待命令队列空闲':'请等待编辑完成，并切回单视图代理预览'},
    caps,JSON.stringify([pid,doc?.document_id,doc?.crop?.rect,doc?.crop?.rotation_degrees,workspace,compareMode,comparing,inspectionEnabled,cropOpen]),refreshFromEngine,brushOn,pickFace,{report:recoveryReport,prepare:()=>{setBrushOn(false);setPickFace(false);colorSampler.cancel();blushPicker.cancel();lipstickPicker.cancel();eyelinerPicker.cancel();browMakeupPicker.cancel();eyelashPicker.cancel();}});
  const captureAllowed=!idBackgroundBusy&&!sky.active&&!sky.pending&&!optics.active&&!optics.pending&&!fringe.active&&!fringe.pending&&!commonBackground.active&&!commonBackground.pending&&!studio.active&&!studio.pending&&!manual.active&&!manual.pending&&!recovery.active&&!recovery.pending&&!liveGrade.busy&&!colorPicker.active&&!colorPicker.pending&&!localMasks.active&&!localMasks.pending&&!healBrush.active&&!healBrush.pending&&!cloneStamp.active&&!cloneStamp.pending&&!!status?.engine_alive && status?.ready_caps?.color_capture_protocol===1&&!sourcePatch.active&&!sourcePatch.pending&&!wbPicker.active&&!wbPicker.pending
    && !!doc?.document_id && status.image?.load_id===doc.document_id && workspace==='retouch'
    && compareMode==='single' && !comparing && !inspectionEnabled && !cropOpen && (batchWorkflow.ui.phase==='closed'||batchWorkflow.ui.hidden===true);
  const captureReason=captureAllowed?'':'请导入图片，并在单视图代理预览中取色';
  const colorSampler=useColorSampler({documentId:doc?.document_id??'',revision:status?.doc_rev??-1,
    allowed:captureAllowed,reason:captureReason},brushOn||pickFace);
  const blushPicker=useBlushPicker(doc?.people??null,status?.doc_rev??-1,
    captureAllowed&&!busy&&!exporting&&!peopleWorkflow.state.pending&&!peopleWorkflow.state.uncertain&&caps?.blush_makeup_protocol===1,
    brushOn||pickFace||colorSampler.active||!captureAllowed,peopleWorkflow.submitCaptured);
  const lipstickPicker=useLipstickPicker(doc?.people??null,status?.doc_rev??-1,
    captureAllowed&&!busy&&!exporting&&!peopleWorkflow.state.pending&&!peopleWorkflow.state.uncertain&&caps?.lipstick_protocol===1,
    brushOn||pickFace||colorSampler.active||blushPicker.active||!captureAllowed,peopleWorkflow.submitCaptured);
  const eyelinerPicker=useEyelinerPicker(doc?.people??null,status?.doc_rev??-1,
    captureAllowed&&!busy&&!exporting&&!peopleWorkflow.state.pending&&!peopleWorkflow.state.uncertain&&caps?.eyeliner_protocol===1,
    brushOn||pickFace||colorSampler.active||blushPicker.active||lipstickPicker.active||!captureAllowed,peopleWorkflow.submitCaptured);
  const browMakeupPicker=useBrowMakeupPicker(doc?.people??null,status?.doc_rev??-1,
    captureAllowed&&!busy&&!exporting&&!peopleWorkflow.state.pending&&!peopleWorkflow.state.uncertain&&caps?.brow_makeup_protocol===1,
    brushOn||pickFace||colorSampler.active||blushPicker.active||lipstickPicker.active||eyelinerPicker.active||!captureAllowed,peopleWorkflow.submitCaptured);
  const eyelashPicker=useEyelashPicker(doc?.people??null,status?.doc_rev??-1,
    captureAllowed&&!busy&&!exporting&&!peopleWorkflow.state.pending&&!peopleWorkflow.state.uncertain&&caps?.eyelash_protocol===1,
    brushOn||pickFace||colorSampler.active||blushPicker.active||lipstickPicker.active||eyelinerPicker.active||browMakeupPicker.active||!captureAllowed,peopleWorkflow.submitCaptured);
  const armEyelashPicker=async()=>{
    if(!captureAllowed||busy||exporting||peopleWorkflow.state.pending||peopleWorkflow.state.uncertain)throw Error('请等待编辑完成后取色');
    colorSampler.cancel();blushPicker.cancel();lipstickPicker.cancel();eyelinerPicker.cancel();browMakeupPicker.cancel();eyelashPicker.cancel();setBrushOn(false);setPickFace(false);await eyelashPicker.arm();
  };
  const armEyelinerPicker=async()=>{
    if(!captureAllowed||busy||exporting||peopleWorkflow.state.pending||peopleWorkflow.state.uncertain)throw Error('请等待编辑完成后取色');
    colorSampler.cancel();blushPicker.cancel();lipstickPicker.cancel();eyelinerPicker.cancel();browMakeupPicker.cancel();eyelashPicker.cancel();setBrushOn(false);setPickFace(false);await eyelinerPicker.arm();
  };
  const armBrowMakeupPicker=async()=>{
    if(!captureAllowed||busy||exporting||peopleWorkflow.state.pending||peopleWorkflow.state.uncertain)throw Error('请等待编辑完成后取色');
    colorSampler.cancel();blushPicker.cancel();lipstickPicker.cancel();eyelinerPicker.cancel();browMakeupPicker.cancel();eyelashPicker.cancel();setBrushOn(false);setPickFace(false);await browMakeupPicker.arm();
  };
  const armLipstickPicker=async()=>{
    if(!captureAllowed||busy||exporting||peopleWorkflow.state.pending||peopleWorkflow.state.uncertain)throw Error('请等待编辑完成后取色');
    colorSampler.cancel();blushPicker.cancel();lipstickPicker.cancel();eyelinerPicker.cancel();browMakeupPicker.cancel();eyelashPicker.cancel();setBrushOn(false);setPickFace(false);await lipstickPicker.arm();
  };
  const armBlushPicker=async()=>{
    if(!captureAllowed||busy||exporting||peopleWorkflow.state.pending||peopleWorkflow.state.uncertain)throw Error('请等待编辑完成后取色');
    colorSampler.cancel();blushPicker.cancel();lipstickPicker.cancel();eyelinerPicker.cancel();browMakeupPicker.cancel();eyelashPicker.cancel();setBrushOn(false);setPickFace(false);await blushPicker.arm();
  };
  const bodyToolsBlocked=eyelashPicker.active||browMakeupPicker.active||eyelinerPicker.active||lipstickPicker.active||blushPicker.active||busy||exporting||peopleWorkflow.state.pending||peopleWorkflow.state.uncertain
    ||brushOn||pickFace||whiteBalanceWorkflow.workflow.busy()
    ||sky.active||sky.pending||optics.active||optics.pending||fringe.active||fringe.pending||commonBackground.active||commonBackground.pending||studio.active||studio.pending||manual.active||manual.pending
    ||recovery.active||recovery.pending||liveGrade.busy||colorPicker.active||colorPicker.pending||localMasks.active||localMasks.pending
    ||healBrush.active||healBrush.pending||cloneStamp.active||cloneStamp.pending||sourcePatch.active||sourcePatch.pending||wbPicker.active||wbPicker.pending
    ||workspace!=='retouch'||compareMode!=='single'||comparing||inspectionEnabled||cropOpen
    ||!(batchWorkflow.ui.phase==='closed'||batchWorkflow.ui.hidden===true);
  const legs=useLegWorkflow(status,doc,refreshFromEngine,bodyToolsBlocked||shoulders.busy||shoulders.acquisition.busy);
  const arms=useArmWorkflow(status,doc,refreshFromEngine,bodyToolsBlocked||shoulders.busy||shoulders.acquisition.busy||legs.busy);
  const waist=useWaistWorkflow(status,doc,refreshFromEngine,bodyToolsBlocked||shoulders.busy||shoulders.acquisition.busy||legs.busy||arms.busy);
  const length=useLegLengthWorkflow(status,doc,refreshFromEngine,bodyToolsBlocked||shoulders.busy||shoulders.acquisition.busy||legs.busy||arms.busy||waist.busy);
  const neck=useNeckWorkflow(status,doc,refreshFromEngine,bodyToolsBlocked||shoulders.busy||shoulders.acquisition.busy||legs.busy||arms.busy||waist.busy||length.busy);
  const torso=useTorsoLengthWorkflow(status,doc,refreshFromEngine,bodyToolsBlocked||shoulders.busy||shoulders.acquisition.busy||legs.busy||arms.busy||waist.busy||length.busy||neck.busy);
  const waistLength=useWaistLengthWorkflow(status,doc,refreshFromEngine,bodyToolsBlocked||shoulders.busy||shoulders.acquisition.busy||legs.busy||arms.busy||waist.busy||length.busy||neck.busy||torso.busy);
  const headSize=useHeadSizeWorkflow(status,doc,refreshFromEngine,bodyToolsBlocked||shoulders.busy||shoulders.acquisition.busy||legs.busy||arms.busy||waist.busy||length.busy||neck.busy||torso.busy||waistLength.busy);
  const bodySlim=useBodySlimWorkflow(status,doc,refreshFromEngine,bodyToolsBlocked||shoulders.busy||shoulders.acquisition.busy||legs.busy||arms.busy||waist.busy||length.busy||neck.busy||torso.busy||waistLength.busy||headSize.busy);
  armBusyRef.current=arms.busy||waist.busy||length.busy||neck.busy||torso.busy||waistLength.busy||headSize.busy||bodySlim.busy;
  fringeBusyRef.current=fringe.active||fringe.pending;
  const imageToolBusy=eyelashPicker.active||browMakeupPicker.active||eyelinerPicker.active||lipstickPicker.active||blushPicker.active||busy||exporting||shoulders.busy||legs.busy||arms.busy||waist.busy||length.busy||neck.busy||torso.busy||waistLength.busy||headSize.busy||bodySlim.busy||peopleWorkflow.state.pending||peopleWorkflow.state.uncertain
    ||brushOn||pickFace||whiteBalanceWorkflow.workflow.busy()
    ||sky.active||sky.pending||optics.active||optics.pending||fringe.active||fringe.pending||commonBackground.active||commonBackground.pending||studio.active||studio.pending||manual.active||manual.pending
    ||recovery.active||recovery.pending||liveGrade.busy||colorPicker.active||colorPicker.pending||localMasks.active||localMasks.pending
    ||healBrush.active||healBrush.pending||cloneStamp.active||cloneStamp.pending||sourcePatch.active||sourcePatch.pending||wbPicker.active||wbPicker.pending
    ||compareMode!=='single'||comparing||inspectionEnabled||cropOpen
    ||!(batchWorkflow.ui.phase==='closed'||batchWorkflow.ui.hidden===true);
  const hairToolBusy=imageToolBusy||workspace!=='retouch';
  const hairBusy=hairToolBusy||!!status?.edit_queue?.in_flight||!!status?.edit_queue?.pending;
  const hair=useHairColourPort(peopleWorkflow.enabled&&status?.ready_caps?.hair_colour_protocol===1&&!hairBusy
    &&!!doc?.document_id&&status.image?.load_id===doc.document_id,refreshFromEngine);
  const guideCategoryOpen=useGuideModeGuards();
  const creative=useCreativeWorkspace({sourceUid:doc?.source_uid??'',loadId:doc?.document_id??'',engineKey:String(pid??''),hostRevision:status?.doc_rev??-1,
    active:workspace==='creative',available:!!status?.engine_alive&&caps?.creative_document_protocol===1&&hasImage&&status.image?.load_id===doc?.document_id,
    busy:busy||exporting||idBackgroundBusy||peopleWorkflow.state.pending||peopleWorkflow.state.uncertain||shoulders.busy||legs.busy||arms.busy||waist.busy||length.busy||neck.busy||torso.busy||waistLength.busy||headSize.busy||bodySlim.busy
      ||sky.pending||optics.pending||commonBackground.pending||studio.pending||manual.pending||recovery.pending||liveGrade.busy||colorPicker.pending||localMasks.pending||healBrush.pending||cloneStamp.pending||sourcePatch.pending||wbPicker.pending
      ||whiteBalanceWorkflow.workflow.busy()||!!status?.edit_queue?.in_flight||!!status?.edit_queue?.pending||!(batchWorkflow.ui.phase==='closed'||batchWorkflow.ui.hidden===true)},refreshFromEngine);
  const materialTargetKey=JSON.stringify([pid,doc?.document_id,status?.doc_rev]);
  const materials=useBackgroundMaterialHost({enabled:!!status?.engine_alive&&caps?.background_material_library_protocol===1,targetKey:materialTargetKey});
  const selection=useSelectionBinding(creative,JSON.stringify([pid,doc?.document_id]),workspace==='creative',caps?.creative_selection_protocol===1&&caps?.creative_selection_capability?.available===true,imageToolBusy||idBackgroundBusy);
  const expression=useExpressionReplacement({sourceUid:doc?.source_uid??'',loadId:doc?.document_id??'',engineKey:String(pid??''),hostRevision:status?.doc_rev??-1,
    available:!!status?.engine_alive&&caps?.expression_replacement_protocol===1&&hasImage&&status.image?.load_id===doc?.document_id,
    busy:hairToolBusy||idBackgroundBusy||creative.pending||colorSampler.active||sampleLibrary.open,queueBusy:!!status?.edit_queue?.in_flight||!!status?.edit_queue?.pending},refreshFromEngine);
  const lens=useLensBlur({sourceUid:doc?.source_uid??'',loadId:doc?.document_id??'',engineKey:String(pid??''),hostRevision:status?.doc_rev??-1,
    active:workspace==='creative',available:!!status?.engine_alive&&caps?.lens_blur_protocol===3&&hasImage&&status.image?.load_id===doc?.document_id,
    externalBusy:imageToolBusy||idBackgroundBusy||creative.pending||expression.busy||expressionOpen||colorSampler.active||sampleLibrary.open,queueBusy:!!status?.edit_queue?.in_flight||!!status?.edit_queue?.pending},refreshFromEngine);
  const glowCapability=caps?.light_glow_capability;
  const glow=useGlowWorkspaceBinding({sourceUid:doc?.source_uid??'',loadId:doc?.document_id??'',engineKey:String(pid??''),hostRevision:status?.doc_rev??-1,active:workspace==='creative',
    available:!!status?.engine_alive&&hasImage&&status.image?.load_id===doc?.document_id&&caps?.light_glow_protocol===GLOW_PROTOCOL&&validGlowCapability(glowCapability)&&glowCapability.status==='available',
    externalBusy:imageToolBusy||idBackgroundBusy||creative.pending||expression.busy||expressionOpen||lens.busy||lensOpen||colorSampler.active||sampleLibrary.open,queueBusy:!!status?.edit_queue?.in_flight||!!status?.edit_queue?.pending},refreshFromEngine);
  armBusyRef.current=armBusyRef.current||expression.busy||lens.busy||glow.busy;
  creativeRoute.current={active:workspace==='creative',pending:creative.pending,importPaths:creative.importPaths,history:creative.history};
  const guides=useCanvasGuides({loadId:doc?.document_id??'',report:doc?.canvas_guides,center:doc?.crop?[(doc.crop.rect[0]+doc.crop.rect[2])/2,(doc.crop.rect[1]+doc.crop.rect[3])/2]:undefined,
    contextKey:JSON.stringify([pid,doc?.document_id,doc?.crop,view,workspace]),modes:{
      available:!!status?.engine_alive&&caps?.canvas_guides_protocol===1&&hasImage&&status.image?.load_id===doc?.document_id&&workspace==='retouch',
      compare:compareMode!=='single'||comparing,reference:sampleLibrary.open,brush:brushOn||recovery.active||recovery.pending,
      mask:localMasks.active||localMasks.pending,category:guideCategoryOpen||peopleWorkflow.state.pending||peopleWorkflow.state.uncertain,crop:cropOpen,
      inspection:inspectionEnabled,picker:pickFace||colorSampler.active||blushPicker.active||lipstickPicker.active||eyelinerPicker.active||browMakeupPicker.active||eyelashPicker.active||colorPicker.active||colorPicker.pending||wbPicker.active||wbPicker.pending||sky.active||sky.pending||fringe.active||fringe.pending||commonBackground.active||commonBackground.pending||studio.active||studio.pending||optics.active||optics.pending,
      manual:manual.active||manual.pending,repair:sourcePatch.active||sourcePatch.pending||healBrush.active||healBrush.pending||cloneStamp.active||cloneStamp.pending,
      busy:busy||exporting||idBackgroundBusy||liveGrade.busy||whiteBalanceWorkflow.workflow.busy()||shoulders.busy||legs.busy||arms.busy||waist.busy||length.busy||neck.busy||torso.busy||waistLength.busy||headSize.busy||bodySlim.busy||!!status?.edit_queue?.in_flight||!!status?.edit_queue?.pending||!(batchWorkflow.ui.phase==='closed'||batchWorkflow.ui.hidden===true)}},refreshFromEngine);
  const startReviewedHeal=()=>{
    if(!healBrush.context.enabled||healBrush.context.canStart===false||healBrush.pending||sourcePatch.active||sourcePatch.pending||cloneStamp.active||cloneStamp.pending||wbPicker.active||wbPicker.pending||localMasks.active||localMasks.pending||colorPicker.active||colorPicker.pending||recovery.active||recovery.pending||manual.active||manual.pending||fringe.active||fringe.pending||commonBackground.active||commonBackground.pending||studio.active||studio.pending||optics.active||optics.pending||sky.active||sky.pending||liveGrade.busy)return;
    setBrushOn(false);setPickFace(false);colorSampler.cancel();blushPicker.cancel();lipstickPicker.cancel();eyelinerPicker.cancel();browMakeupPicker.cancel();eyelashPicker.cancel();
    sourcePatch.workflow.cancel();cloneStamp.workflow.cancel();wbPicker.workflow.cancel();localMasks.workflow.cancel();colorPicker.workflow.cancel();recovery.workflow.cancel();manual.workflow.cancel();
    void healBrush.workflow.start();
  };
  // Keep uncertain arm/waist mutations and proposal cancellation from racing other UI edits.
  // Original-receipt checks, popup Close and the activity locator remain accessible.
  const guardArmWork=(event:import('react').SyntheticEvent)=>guardCreativeWork(event,{glow:glow.busy||glowOpen,lens:lens.busy||lensOpen,expression:expression.busy||expressionOpen,background:fringe.active||fringe.pending||commonBackground.active||commonBackground.pending,heal:healBrush.pending,layers:creative.pending,selection:selection.busy,
    idBackground:idBackgroundBusy,body:arms.busy||waist.busy||length.busy||neck.busy||torso.busy||waistLength.busy||headSize.busy||bodySlim.busy});
  return (
    <div className={"app ws-" + workspace} onClickCapture={guardArmWork} onPointerDownCapture={guardArmWork} onKeyDownCapture={guardArmWork}>
      <WorkspaceTopbar workspace={workspace} onWorkspace={setWorkspace} busy={busy||arms.busy||waist.busy||length.busy||neck.busy||torso.busy||waistLength.busy||headSize.busy||bodySlim.busy||creative.pending} hasImage={hasImage}
        currentPath={strip?.current} onOpenPhoto={() => { setWorkspace("retouch"); void openAndImport(); }}
        libraryEnabled={sampleLibrary.enabled} onLibrary={() => sampleLibrary.show('manage')}/>
      <LightGlowWorkspaceHost owner={glow} unavailableReason={validGlowCapability(glowCapability)?(glowCapability.status==='available'?undefined:glowCapability.reason||'发光原生模块不可用'): '缺少匹配的发光原生模块；不会降级为占位效果或自动安装'} open={glowOpen} onOpen={()=>setGlowOpen(true)} onClose={()=>setGlowOpen(false)}/>
      <LensWorkspaceHost owner={lens} open={lensOpen} onOpen={()=>setLensOpen(true)} onClose={()=>setLensOpen(false)}/>
      <ExpressionWorkspaceHost owner={expression} open={expressionOpen} onOpen={()=>setExpressionOpen(true)} onClose={()=>setExpressionOpen(false)}/>
      <SampleLibraryHost owner={sampleLibrary}/>
      <BackgroundMaterialHost owner={materials}/>


      {doc?.sky_replacement?.suspended&&<div className="skySuspendedNotice" role="alert">换天空已暂停：{doc.sky_replacement.suspended}。当前代理仅显示其他效果，不是完整出片结果。请进入“换天空”重新选择素材或关闭该效果；全质量检查和导出保持阻止。</div>}

      <aside hidden={workspace !== "retouch"} className="side" onInputCapture={(event)=>{
                const target=event.target;
                if(target instanceof Element && target.closest('[data-readonly-scopes]'))return;
                if(target instanceof HTMLSelectElement || (target instanceof HTMLInputElement
                  && ['range','number','color','checkbox'].includes(target.type)))notifyInspectionEditIntent();
              }}>
          <IdBackgroundPanel materials={materials} materialTargetKey={materialTargetKey} pickerDisabled={busy||exporting||peopleWorkflow.state.pending||peopleWorkflow.state.uncertain||!!status?.edit_queue?.in_flight||!!status?.edit_queue?.pending||brushOn||pickFace||whiteBalanceWorkflow.workflow.busy()||sky.active||sky.pending||optics.active||optics.pending||fringe.active||fringe.pending||commonBackground.active||commonBackground.pending||studio.active||studio.pending||manual.active||manual.pending||recovery.active||recovery.pending||liveGrade.busy||colorPicker.active||colorPicker.pending||localMasks.active||localMasks.pending||healBrush.active||healBrush.pending||cloneStamp.active||cloneStamp.pending||sourcePatch.active||sourcePatch.pending||wbPicker.active||wbPicker.pending||shoulders.busy||legs.busy||arms.busy||waist.busy||length.busy||neck.busy||torso.busy||waistLength.busy||headSize.busy||bodySlim.busy||eyelashPicker.active||browMakeupPicker.active||eyelinerPicker.active||lipstickPicker.active||blushPicker.active||workspace!=='retouch'||inspectionEnabled||cropOpen||!(batchWorkflow.ui.phase==='closed'||batchWorkflow.ui.hidden===true)} selectedReference={sampleLibrary.selectedReference} onSelectReference={()=>sampleLibrary.show('reference')} onBusy={setIdBackgroundBusy} documentId={doc?.document_id??''} hostRevision={status?.doc_rev??-1} disabled={hairBusy||!hasImage} available={status?.ready_caps?.id_background_protocol===1} masks={doc?.local_masks} onChanged={()=>{void refreshFromEngine();}}/>
          <RetouchPanel expressionPanel={<button type="button" disabled={!hasImage||hairBusy||creative.pending} onClick={()=>setExpressionOpen(true)}>同场次表情替换 · 获取真实素材并审核</button>} fringeRepairOwner={fringe} commonBackgroundOwner={commonBackground} irisMakeupPanel={<IrisMakeupPanel people={peopleWorkflow} report={doc?.people?.iris_makeup??null} blocked={busy||exporting||!captureAllowed||eyelashPicker.active||browMakeupPicker.active||eyelinerPicker.active||lipstickPicker.active||blushPicker.active||!!status?.edit_queue?.in_flight||!!status?.edit_queue?.pending}/>} eyelashPanel={<EyelashPanel people={peopleWorkflow} picker={eyelashPicker} blocked={busy||exporting||!captureAllowed||!!status?.edit_queue?.in_flight||!!status?.edit_queue?.pending} onArm={armEyelashPicker}/>} browMakeupPanel={<BrowMakeupPanel people={peopleWorkflow} picker={browMakeupPicker} blocked={busy||exporting||!captureAllowed||!!status?.edit_queue?.in_flight||!!status?.edit_queue?.pending} onArm={armBrowMakeupPicker}/>} eyelinerPanel={<EyelinerPanel people={peopleWorkflow} picker={eyelinerPicker} blocked={busy||exporting||!captureAllowed||!!status?.edit_queue?.in_flight||!!status?.edit_queue?.pending} onArm={armEyelinerPicker}/>} lipstickPanel={<LipstickPanel people={peopleWorkflow} picker={lipstickPicker} blocked={busy||exporting||!captureAllowed||!!status?.edit_queue?.in_flight||!!status?.edit_queue?.pending} onArm={armLipstickPicker}/>} blushMakeupPanel={<BlushMakeupPanel people={peopleWorkflow} picker={blushPicker} blocked={busy||exporting||!captureAllowed||!!status?.edit_queue?.in_flight||!!status?.edit_queue?.pending} onArm={armBlushPicker}/>} shoulderPanel={<BodyShapeTools shoulders={shoulders} legs={legs} arms={arms} waist={waist} length={length} neck={neck} torso={torso} waistLength={waistLength} headSize={headSize} bodySlim={bodySlim} blocked={bodyToolsBlocked}/>} sampleLibraryPanel={<SampleLibraryLaunch owner={sampleLibrary}/>} toolLocation={toolLocation} {...createRetouchToolSlots({guides,guideSourceSize:[status?.image?.src_w??0,status?.image?.src_h??0],guideCrop:doc?.crop,sky,skyReport:doc?.sky_replacement,optics,opticsReport:doc?.optics,manual,recovery,studio,manualReport:doc?.manual_liquify,recoveryReport,studioReport:doc?.studio_background,busy:liveGrade.busy})} colorActions={{owner:colorPicker,blocked:sky.active||sky.pending||manual.pending||recovery.pending||liveGrade.busy||sourcePatch.pending||wbPicker.pending||healBrush.pending||cloneStamp.pending||localMasks.pending,onStart:(action,channel)=>{if(sky.active||sky.pending||manual.pending||recovery.pending||liveGrade.busy||sourcePatch.pending||wbPicker.pending||healBrush.pending||cloneStamp.pending||localMasks.pending)return;setBrushOn(false);setPickFace(false);colorSampler.cancel();blushPicker.cancel();lipstickPicker.cancel();eyelinerPicker.cancel();browMakeupPicker.cancel();eyelashPicker.cancel();sourcePatch.workflow.cancel();wbPicker.workflow.cancel();healBrush.workflow.cancel();cloneStamp.workflow.cancel();localMasks.workflow.cancel();recovery.workflow.cancel();manual.workflow.cancel();void colorPicker.workflow.start(action,channel);}}} whiteBalanceBusy={optics.active||optics.pending||fringe.active||fringe.pending||commonBackground.active||commonBackground.pending||studio.active||studio.pending||sourcePatch.active||sourcePatch.pending||healBrush.active||healBrush.pending||cloneStamp.active||cloneStamp.pending||sky.active||sky.pending||manual.active||recovery.active||manual.pending||recovery.pending||liveGrade.busy||colorPicker.active||colorPicker.pending||whiteBalanceWorkflow.workflow.busy()||wbPicker.active||wbPicker.pending||localMasks.active||localMasks.pending} whiteBalancePanel={<WhiteBalanceControls owner={whiteBalanceWorkflow} value={doc?.exposure} pickerBusy={sky.active||sky.pending||manual.active||recovery.active||manual.pending||recovery.pending||liveGrade.busy||colorPicker.active||colorPicker.pending||localMasks.active||localMasks.pending||wbPicker.active||wbPicker.pending||sourcePatch.active||sourcePatch.pending||healBrush.active||healBrush.pending||cloneStamp.active||cloneStamp.pending} picker={<WhiteBalancePickerControls owner={{...wbPicker,context:{...wbPicker.context,canStart:wbPicker.context.canStart!==false&&!manual.active&&!manual.pending&&!colorPicker.pending&&!recovery.pending&&!liveGrade.busy}}} onStart={()=>{if(sky.active||sky.pending||optics.active||optics.pending||fringe.active||fringe.pending||commonBackground.active||commonBackground.pending||studio.active||studio.pending||colorPicker.pending||manual.pending||recovery.pending||liveGrade.busy)return;colorPicker.workflow.cancel();recovery.workflow.cancel();manual.workflow.cancel();setBrushOn(false);setPickFace(false);colorSampler.cancel();blushPicker.cancel();lipstickPicker.cancel();eyelinerPicker.cancel();browMakeupPicker.cancel();eyelashPicker.cancel();localMasks.workflow.cancel();healBrush.workflow.cancel();cloneStamp.workflow.cancel();void wbPicker.workflow.start();}}/>}/>} presetPanel={<PresetPanel workflow={presetWorkflow}/>} status={status} doc={doc} hasImage={hasImage}
                        healBrushPanel={<HealBrushPanel owner={healBrush} onStart={startReviewedHeal} blocked={bodyToolsBlocked&&!healBrush.active&&!healBrush.pending}/>}
                        sourcePatchPanel={<SourcePatchPanel owner={sourcePatch} blocked={sky.active||sky.pending||manual.pending||recovery.pending||liveGrade.busy||colorPicker.pending||localMasks.pending||wbPicker.active||wbPicker.pending||healBrush.pending||cloneStamp.pending} onStart={()=>{if(sky.active||sky.pending||manual.pending||recovery.pending||liveGrade.busy||colorPicker.pending||localMasks.pending||wbPicker.active||wbPicker.pending||healBrush.pending||cloneStamp.pending)return;colorPicker.workflow.cancel();recovery.workflow.cancel();manual.workflow.cancel();localMasks.workflow.cancel();healBrush.workflow.cancel();cloneStamp.workflow.cancel();setBrushOn(false);setPickFace(false);colorSampler.cancel();blushPicker.cancel();lipstickPicker.cancel();eyelinerPicker.cancel();browMakeupPicker.cancel();eyelashPicker.cancel();void sourcePatch.workflow.start();}}/>}
                        cloneStampPanel={<CloneStampPanel owner={cloneStamp} blocked={sky.active||sky.pending||manual.pending||recovery.pending||liveGrade.busy||colorPicker.pending||localMasks.pending||sourcePatch.active||sourcePatch.pending||wbPicker.active||wbPicker.pending} onStart={()=>{if(sky.active||sky.pending||optics.active||optics.pending||fringe.active||fringe.pending||commonBackground.active||commonBackground.pending||studio.active||studio.pending||colorPicker.pending||manual.pending||recovery.pending||liveGrade.busy)return;colorPicker.workflow.cancel();recovery.workflow.cancel();manual.workflow.cancel();setBrushOn(false);setPickFace(false);colorSampler.cancel();blushPicker.cancel();lipstickPicker.cancel();eyelinerPicker.cancel();browMakeupPicker.cancel();eyelashPicker.cancel();localMasks.workflow.cancel();void cloneStamp.workflow.start();}}/>}
                        localMasksPanel={<LocalMaskPanel liveGrade={liveGrade} owner={localMasks} report={doc?.local_masks} blocked={sky.active||sky.pending||optics.active||optics.pending||fringe.active||fringe.pending||commonBackground.active||commonBackground.pending||studio.active||studio.pending||manual.active||manual.pending||recovery.pending||colorPicker.pending||sourcePatch.active||sourcePatch.pending||wbPicker.active||wbPicker.pending||healBrush.active||healBrush.pending||cloneStamp.active||cloneStamp.pending} onStart={(mutation,draw,groupId)=>{if(sky.active||sky.pending||optics.active||optics.pending||fringe.active||fringe.pending||commonBackground.active||commonBackground.pending||studio.active||studio.pending||colorPicker.pending||manual.pending||recovery.pending||liveGrade.busy)return;colorPicker.workflow.cancel();recovery.workflow.cancel();manual.workflow.cancel();setBrushOn(false);setPickFace(false);colorSampler.cancel();blushPicker.cancel();lipstickPicker.cancel();eyelinerPicker.cancel();browMakeupPicker.cancel();eyelashPicker.cancel();healBrush.workflow.cancel();cloneStamp.workflow.cancel();sourcePatch.workflow.cancel();wbPicker.workflow.cancel();void localMasks.workflow.start(mutation,draw,groupId);}}/>}
                        colorSamplePanel={<ColorSamplePanel sampler={colorSampler} reason={captureReason}
                          canArm={captureAllowed&&!status?.edit_queue?.in_flight&&!status?.edit_queue?.pending}
                          onArm={()=>{if(sky.active||sky.pending||optics.active||optics.pending||fringe.active||fringe.pending||commonBackground.active||commonBackground.pending||studio.active||studio.pending||colorPicker.pending||manual.pending||recovery.pending||liveGrade.busy)return;colorPicker.workflow.cancel();recovery.workflow.cancel();manual.workflow.cancel();setBrushOn(false);setPickFace(false);blushPicker.cancel();lipstickPicker.cancel();eyelinerPicker.cancel();browMakeupPicker.cancel();eyelashPicker.cancel();colorSampler.arm();}}/>}
                        faceOk={faceOk} faceWhy={faceWhy}
                        note={setDragNote} onDone={requestPanelRefresh}
                        thumb={strip?.current ? thumbs[strip.current] : undefined}
                        people={peopleWorkflow}
                        hairPort={hair.port} hairBusy={hairBusy} refreshHair={refreshFromEngine}
                        brush={{ on: brushOn, mode: brushMode, radius: brushRadius }}
                        onBrush={(patch) => {
                          if(patch.on&&(patch.mode??brushMode)==="heal"){startReviewedHeal();return;}
                          if(patch.on===false)healBrush.workflow.cancel();
                          if(sky.active||sky.pending||optics.active||optics.pending||fringe.active||fringe.pending||commonBackground.active||commonBackground.pending||studio.active||studio.pending||colorPicker.pending||manual.pending||recovery.pending||liveGrade.busy)return;if(patch.on)colorPicker.workflow.cancel();recovery.workflow.cancel();manual.workflow.cancel();
                          if (patch.on !== undefined) setBrushOn(patch.on);
                          if (patch.mode) setBrushMode(patch.mode);
                          if (patch.radius !== undefined) setBrushRadius(patch.radius);
                        }}
                        onOpenCrop={() => {if(sky.active||sky.pending||optics.active||optics.pending||fringe.active||fringe.pending||commonBackground.active||commonBackground.pending||studio.active||studio.pending||colorPicker.pending||manual.pending||recovery.pending||liveGrade.busy)return;colorPicker.workflow.cancel();recovery.workflow.cancel();manual.workflow.cancel();setCropOpen(true);}}
                        onFaceAdd={() => {
                          if(sky.active||sky.pending||optics.active||optics.pending||fringe.active||fringe.pending||commonBackground.active||commonBackground.pending||studio.active||studio.pending||colorPicker.pending||manual.pending||recovery.pending||liveGrade.busy)return;colorPicker.workflow.cancel();recovery.workflow.cancel();manual.workflow.cancel();faceAddContext.current=peopleAssetContext(doc?.people);setPickFace(true);
                          setDragNote("在画面中框选一张人脸，松手即可添加人物");
                        }}
                        faceAdding={pickFace} />
        </aside>

      {(workspace==='library'||workspace==='retouch')&&<VirtualCopyControls
        projectKey={`${pid}:${library.result?.session_id??''}`} refreshKey={`${status?.doc_rev}:${status?.session_rev}`} activeDocumentId={strip?.docs.find(d=>d.loaded)?.document_id}
        selectedDocumentIds={selPaths} disabled={busy||exporting||!status?.engine_alive}
        onChanged={()=>{void refreshFromEngine().catch(e=>setDragNote(String(e)));}}/>}
      <main className="stage">
        <RetouchToolActivity onLocate={locateTool} items={[
          {name:"AI瘦手臂与瘦手臂",featureId:"PC-32473",path:"AI瘦手臂&瘦手臂",active:false,pending:arms.busy,phase:arms.uncertain||arms.state.phase==='uncertain'?'uncertain':arms.state.phase,message:arms.message||arms.state.message,check:arms.check},
          {name:"瘦腰",featureId:"PC-32473",path:"瘦腰",active:false,pending:waist.busy,phase:waist.uncertain||waist.state.phase==='uncertain'?'uncertain':waist.state.phase,message:waist.message||waist.state.message,check:waist.check},
          {name:"脖子长宽",featureId:"PC-32473",path:"脖子长度",active:false,pending:neck.busy,phase:neck.uncertain||neck.state.phase==='uncertain'?'uncertain':neck.state.phase,message:neck.message||neck.state.message,check:neck.check},
          {name:"长腿",featureId:"PC-32473",path:"长腿",active:false,pending:length.busy,phase:length.uncertain||length.state.phase==='uncertain'?'uncertain':length.state.phase,message:length.message||length.state.message,check:length.check},
          {name:"上身长度",featureId:"PC-32473",path:"上身长度",active:false,pending:torso.busy,phase:torso.uncertain||torso.state.phase==='uncertain'?'uncertain':torso.state.phase,message:torso.message||torso.state.message,check:torso.check},
          {name:"腰部长度",featureId:"PC-32473",path:"腰部长度",active:false,pending:waistLength.busy,phase:waistLength.uncertain||waistLength.state.phase==='uncertain'?'uncertain':waistLength.state.phase,message:waistLength.message||waistLength.state.message,check:waistLength.check},
          {name:"小头",featureId:"PC-32473",path:"小头",active:false,pending:headSize.busy,phase:headSize.uncertain||headSize.state.phase==='uncertain'?'uncertain':headSize.state.phase,message:headSize.message||headSize.state.message,check:headSize.check},
          {name:"发色与光泽",featureId:"PC-32472",path:"发色选择",active:false,pending:hair.state.pending,phase:hair.state.uncertain?'uncertain':'idle',message:hair.state.message,check:hair.check},
          {name:"修复画笔",featureId:"PC-32482",path:"污点修复画笔",active:healBrush.active,pending:healBrush.pending,phase:healBrush.state.phase,message:healBrush.state.message,check:healBrush.workflow.check},
          {name:"效果恢复画笔",featureId:"PC-32481",active:recovery.active,pending:recovery.pending,phase:recovery.state.phase,message:recovery.state.message,check:recovery.workflow.check},
          {name:"手动液化",featureId:"PC-32479",active:manual.active,pending:manual.pending,phase:manual.state.phase,message:manual.state.message,check:manual.workflow.check},
          {name:"黑白边修复",featureId:"PC-AlCcjw85ql",active:fringe.active,pending:fringe.pending,phase:fringe.state.phase,message:fringe.state.message,check:fringe.workflow.check},
          {name:"普通换底",featureId:"PC-32475",active:commonBackground.active,pending:commonBackground.pending,phase:commonBackground.state.phase,message:commonBackground.state.message,check:commonBackground.workflow.check},
          {name:"背景调整",featureId:"PC-32474",active:studio.active,pending:studio.pending,phase:studio.state.phase,message:studio.state.message,check:studio.workflow.check},
          {name:"镜头与透视",featureId:"PC-32455",path:"镜头调整",active:optics.active,pending:optics.pending,phase:optics.state.phase,message:optics.state.message,check:optics.check},
          {name:"换天空",featureId:"PC-32476",active:sky.active,pending:sky.pending,phase:sky.state.phase,message:sky.state.message,check:sky.workflow.check},
        ]}/>
        <EffectRecoveryWorkspace owner={recovery} report={recoveryReport}/><LiveGradeStatus owner={liveGrade}/>
        <HealBrushStatus owner={healBrush}/><ColorActionStatus owner={colorPicker}/><LocalMaskStatus owner={localMasks}/><CloneStampStatus owner={cloneStamp}/><SourcePatchStatus owner={sourcePatch}/><WhiteBalancePickerStatus owner={wbPicker}/>
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
                  <GuideControls owner={guides}/>
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
                  <button disabled={sky.active||sky.pending||colorPicker.pending||manual.pending||recovery.pending||liveGrade.busy} onClick={() => {colorPicker.workflow.cancel();recovery.workflow.cancel();manual.workflow.cancel();setCropOpen(true);}}
                          title="裁剪与旋转">裁剪</button>
                  {compareMode !== "single" && (
                    <span className="vbState">{hasOriginal ? "原图已就绪" : "正在取原图…"}</span>
                  )}
                </div>
              )}
              <Viewer healBrush={healBrush} guides={guides} guideCrop={doc?.crop} guideSourceSize={[status?.image?.src_w??0,status?.image?.src_h??0]} colorPicker={colorPicker} localMasks={localMasks} colorSampler={eyelashPicker.active?eyelashPicker:browMakeupPicker.active?browMakeupPicker:eyelinerPicker.active?eyelinerPicker:lipstickPicker.active?lipstickPicker:blushPicker.active?blushPicker:colorSampler} cloneStamp={cloneStamp} sourcePatch={sourcePatch} whiteBalancePicker={wbPicker}
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
                brush={{ on: brushOn && brushMode!=="heal" && !!status?.image, radius: brushRadius, onStroke }}
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
                  <button className={oneToOne ? "on" : ""} disabled={sky.active||sky.pending||colorPicker.pending||manual.pending||recovery.pending||liveGrade.busy} onClick={zoomOne}
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

            <ConfirmedPeopleTransfer owner={peopleWorkflow} targets={selPaths} currentPath={strip?.current??''} enabled={hasImage&&!exporting&&status?.ready_caps?.people_protocol===1&&status?.ready_caps?.batch_preflight_protocol===1} onComplete={()=>{void refreshFromEngine().catch(e=>setDragNote(String(e)));}}/>
            {strip && strip.count > 0 && (
              <>
                <ColourTransferTools workflowEnabled={status?.ready_caps?.semantic_colour_workflow_protocol===1} selectedSample={sampleLibrary.selectedReference} semanticEnabled={hasImage&&status?.ready_caps?.semantic_colour_protocol===1} refreshKey={String(status?.doc_rev??0)} sourceDocumentId={doc?.document_id??''} currentPath={strip.current??''} targets={selPaths.filter(id=>id!==strip.docs.find(d=>d.loaded)?.document_id)} enabled={hasImage&&status?.ready_caps?.reference_color_protocol===1} onComplete={()=>{void refreshFromEngine().catch(e=>setDragNote(String(e)));}}/>
                <BatchActions count={selPaths.length} scopes={syncScopes} scope={effectiveScope.label}
                  groups={doc?.local_masks?.transfer_groups} localMaskTransfer={syncScopeOps.includes(LOCAL_GRADE_OP)?localMaskTransfer:undefined} onLocalMaskTransfer={setLocalMaskTransfer} policy={batchPolicy} onScope={setSyncScopeLabel} onPolicy={setBatchPolicy} note={syncNote}
                  ready={hasImage&&status?.ready_caps?.batch_preflight_protocol===1} busy={['committing','preflighting'].includes(batchWorkflow.ui.phase)}
                  unresolved={batchWorkflow.ui.phase==='uncertain'} canUndo={!!syncState?.last} onReview={onBatchSync} onUndo={onBatchUndo}/>
              <FilmstripGallery docs={library.docs} total={strip?.count??0} sel={sel} thumbs={thumbs} controls={libraryControls} facts={library.result?.facts} onPickDoc={onPickDoc} onCellClick={onCellClick} openAndImport={openAndImport} onRetouch={()=>setWorkspace("retouch")} setRating={setRating} cycleFlag={cycleFlag} cyclePick={cyclePick}/>
              </>
            )}
          </>
        )}

        {workspace === "projects" && <ProjectWorkspace workflow={projectFlow}
          project={project} projectSuffix={projSuffix} hasImage={hasImage}
          onEnterRetouch={() => setWorkspace("retouch")} />}

        {workspace === "library" && <LibraryWorkspace busy={busy} exporting={exporting} setBusy={setBusy}
          importFolder={folder=>runSession('add',{paths:[folder],thumbs:true})} refresh={refreshStatus} onError={setDragNote}
          docs={library.docs} total={strip?.count??0} sel={sel} thumbs={thumbs} controls={libraryControls} facts={library.result?.facts} onPickDoc={onPickDoc} onCellClick={onCellClick} openAndImport={openAndImport} onRetouch={()=>setWorkspace("retouch")} setRating={setRating} cycleFlag={cycleFlag} cyclePick={cyclePick}/>}

        {workspace === "creative" && <CreativeWorkspace owner={creative} selection={selection} engineAlive={engineAlive} onStartEngine={onStartEngine} selectionUnavailableReason={caps?.creative_selection_capability?.reason??undefined} hasImage={hasImage} onGlow={()=>setGlowOpen(true)} glowBlocked={imageToolBusy||idBackgroundBusy||expression.busy||lens.busy||!!status?.edit_queue?.in_flight||!!status?.edit_queue?.pending} onLens={()=>setLensOpen(true)} lensBlocked={imageToolBusy||idBackgroundBusy||expression.busy||!!status?.edit_queue?.in_flight||!!status?.edit_queue?.pending} available={caps?.creative_document_protocol===1}
          onBack={()=>setWorkspace('retouch')} healBlocked={sky.active||sky.pending||colorPicker.pending||manual.pending||recovery.pending||liveGrade.busy}
          onHeal={()=>{if(healBrush.pending)return;colorPicker.workflow.cancel();recovery.workflow.cancel();manual.workflow.cancel();setBrushOn(false);locateTool('PC-32482','污点修复画笔');setDragNote('已打开审核式修复画笔，请点击开始后在冻结输入画面涂抹');}}/>}

        {workspace === "export" && (
          <section className="exportView">
            <ExportQueuePanel exportTargets={exportTargets} exporting={exporting} status={status} strip={strip} exportBits16={exportBits16} exportFormat={exportFormat}/>

            <div className="exportCard">
              <h2>导出设置</h2>
              <div className="exGrid">
                <label>格式
                  <select value={exportFormat} onChange={(e) => setExportFormat(reconcileExportFormat(exportBits16, e.target.value))}
                          title={exportBits16 ? "16-bit 可选 PNG 或 TIFF；JPEG / WebP 需要先关闭 16-bit" : undefined}>
                    <option value="jpg" disabled={exportBits16}>JPEG</option>
                    <option value="png">PNG</option>
                    <option value="tif">TIFF</option>
                    <option value="webp" disabled={exportBits16}>WebP</option>
                  </select>
                </label>
                {["tif", "tiff"].includes(exportFormat) && <label>TIFF 无损压缩
                  <select value={exportTiffComp}
                          onChange={(e) => setExportTiffComp(e.target.value)}>
                    <option value="none">无压缩</option>
                    <option value="deflate">Deflate（无损）</option>
                    <option value="lzw">LZW（无损）</option>
                  </select>
                </label>}
                <label>{exportFormat === "png" ? "PNG 压缩力度（无损）" : "质量"}
                  <input type="range" min={60} max={100} value={exportQuality} disabled={exportBits16 || exportTargetSize.enabled || exporting || destinationBusy}
                         onChange={(e) => setExportQuality(+e.target.value)} />
                  <em>{exportBits16 ? "16-bit 无损编码，不使用品质值" : exportQuality}</em>
                </label>
                <TargetSizeControls value={exportTargetSize} onChange={setExportTargetSize} format={exportFormat} bitDepth={exportBits16 ? 16 : 8} busy={exporting || destinationBusy}/>
                <label>尺寸
                  <select value={exportScale} onChange={(e) => setExportScale(+e.target.value)}>
                    <option value={1}>1× 原尺寸</option>
                    <option value={2}>2×</option>
                    <option value={3}>3×</option>
                    <option value={4}>4×</option>
                  </select>
                </label>
                <ExportColorSpace value={exportProfile} onChange={setExportProfile}/>
                <ExportMetadataOptions bits16={exportBits16} format={exportFormat} gps={exportGps} onBits16={setExportBits16} onGps={setExportGps} onFormat={setExportFormat}/>
              </div>
              <LayoutControls model={layoutModel} disabled={exporting} selected={exportTargets.length || (hasImage ? 1 : 0)} receipt={status?.export?.layout_result}/>
              <WatermarkControls value={watermark} onChange={setWatermark} disabled={exporting} storageError={watermarkStorageError}/>
              <ExportDestinationPanel policy={{...destinationPolicy, chosen_root:exportDir}}
                preview={destinationPreview} busy={destinationBusy||exporting}
                available={status?.ready_caps?.export_destination_protocol===1}
                onChange={policy=>{invalidateDestination();setDestinationPolicy(policy);setExportDir(policy.chosen_root??'');setExportConflict(policy.conflict==='rename'?'recheck':'skip_and_report');}}
                onPreview={()=>void onPreviewDestination()} error={exportErr}/>
              <div className="exFoot">
                <span>{exportTargets.length > 1
                  ? `本批 ${exportTargets.length} 张 · 按底片条记账`
                  : "单张导出 · 原片只读"}</span>
                <button className="tb primary" onClick={onExport}
                        disabled={!exportTargets.length || exporting || destinationBusy || !destinationPreview || destinationPreview.entries.some(e=>e.disposition==='needs_confirmation')}>
                  {exporting ? "导出中…" : "开始导出"}
                </button>
              </div>
            </div>
          </section>
        )}
      </main>
      <CommonBackgroundPanel mode="workspace" owner={commonBackground}/>
      <FringeRepairPanel mode="workspace" owner={fringe} onInspect={()=>{fringe.workflow.cancel();const dpr=window.devicePixelRatio||1;setInspectionEnabled(true);setInspectionRetry(n=>n+1);setOneToOne(true);setView({zoom:fitScale>0?1/(dpr*fitScale):1,x:0,y:0,fit:false});}}/>
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
