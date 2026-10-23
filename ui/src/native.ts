import type {PeopleTransferRequest} from './people/transferReview';
import type {PeopleAction, PeopleContext, PeopleMailbox, PeopleView} from './people/model';
import { transportPatch as wrinkleTransport, type WrinkleKey, type RegionFact } from "./facialWrinkles/model";
import type {MaskTransferOptions} from './localMasks/transfer';
import type {WatermarkSettings} from "./watermark/model";
import {curveBarrierRequired,settleCurveEdit,isCurveEditBusy} from './curveEditBarrier';
import type {PresetReply} from './presets/presetWorkflow';
import type {BatchReply} from './batch/batchWorkflow';
import type {CaptureTransport,CaptureStatus} from "./colorCaptureController";
import type {ScopeResult,ScopeStage} from "./colorScopesModel";
/** 与 Rust 命令的唯一出入口。所有跨语言类型集中在这里，避免各组件各自猜字段。 */
import type {LevelsSpec} from "./levelsModel";
import { invoke as tauriInvoke } from "@tauri-apps/api/core";

export const INSPECTION_EDIT_INTENT='lumaretouch-inspection-edit-intent';
export function notifyInspectionEditIntent(){
  if(typeof window!=='undefined')window.dispatchEvent(new Event(INSPECTION_EDIT_INTENT));
}
const inspectionMutations=new Set(['colour_grading_request','extended_tone_request','start_engine','shutdown_engine','load_image','set_strength','precompute',
  'inpaint','light','deform','lut','grade','enhance','lip_makeup','brow_shape','nose_shape','eye_shape','mouth_shape','background','exposure','hsl','curves','levels','fabric','crop','compare',
  'shoulder_shape','leg_shape','waist_shape','leg_length','neck_shape','arm_shape','people','session','history','project','preset','batch','face','pick','export','task','bench_start','bench_stop']);
function invoke<T>(command:string,args?:Parameters<typeof tauriInvoke>[1],options?:Parameters<typeof tauriInvoke>[2]):Promise<T>{
  const send=()=>{if(inspectionMutations.has(command))notifyInspectionEditIntent();return tauriInvoke<T>(command,args,options);};
  if(isCurveEditBusy()&&curveBarrierRequired(command,(args as Record<string,unknown>|undefined)?.action,inspectionMutations.has(command))){
    return settleCurveEdit().then(send);
  }
  return send();
}

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
  load_id?: string;
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
  device_prepare_ms?: number;
  /** 初始化常驻张量：冷进程含 GPU 上下文建立，与图尺寸无关 */
  attach_ms: number;
  first_frame_ms: number;
  import_ms: number;
  /** M5-a 底片条：这一张在列表里的位置、是不是"切回来的"、以及它的完整文档状态。
   *  doc_state 是宿主重摆滑块的唯一出处：切文档时那几条 *_done 快照会被清掉
   *  （它们属于上一条命令而不是这张文档），只有这一份跟着文档走。 */
  session_index: number;
  session_count?: number;
  doc: string;
  switched: boolean;
  layers: SessionEdits;
  doc_state: DocState;
}

/** 一格底片条上"这张调了什么"（引擎按图层数与开关报，不靠前端自己看像素）。 */
export interface SessionEdits {
  colour_grading?: boolean;
  extended_tone?: boolean;
  effect_recovery?: number;
  manual_liquify?: number;
  optics?: boolean;
  sky_replacement?: boolean;
  studio_background?: boolean;
  curves?: boolean;
  levels?: boolean;
  repair: number;
  light: number;
  deform: boolean;
  lut: boolean;
  lut_preset: string | null;
  grade: boolean;
  /** 眼牙层有没有活（三个子功能里至少一个非零）。可选：老引擎没报这一格 */
  enhance?: boolean;
  fabric?: boolean;
  channel: string | null;
}

/** 当前文档的完整编辑状态（引擎是唯一出处）。 */
export type CurveChannel = "master" | "red" | "green" | "blue" | "luminance";
export type ParametricSpec = {
  version:1; algorithm:'lrt-rt512-parametric-splitgrid-lut-v1';space:'srgb-display';
  grid:'split-aligned-4x16384';boundary:'identity-outside-unit';enabled:boolean;
  shadows:number;darks:number;lights:number;highlights:number;splits:[number,number,number];
};
export type CurveSpec = {
  version: 1 | 2 | 3; space: "srgb-display"; interpolation: "pchip"; boundary: "linear";
  enabled: boolean; master: [number,number][]; red: [number,number][];
  green: [number,number][]; blue: [number,number][];
  luminance_space?: "linear-srgb-y-ratio"; luminance?: [number,number][];parametric?:ParametricSpec;
};
export const neutralCurves = (): CurveSpec => ({version:1,space:"srgb-display",interpolation:"pchip",boundary:"linear",enabled:true,
  master:[[0,0],[1,1]],red:[[0,0],[1,1]],green:[[0,0],[1,1]],blue:[[0,0],[1,1]]});
export const runCurves = (action:"set"|"clear", spec?:CurveSpec, gestureId?:string, interactive=false, requestId?:string, documentId?:string) =>
  invoke<{requested:boolean}>("curves",{action,spec,gestureId,interactive,requestId,documentId});
export const colorCaptureApi:CaptureTransport={
  arm:(captureId,documentId)=>invoke<{ticket:string;revision:number}>("capture_arm",{captureId,documentId}),
  status:(captureId,ticket)=>invoke<CaptureStatus>("capture_status",{captureId,ticket}),
  frame:(captureId,ticket)=>invoke<ArrayBuffer>("capture_frame",{captureId,ticket}),
  presented:(captureId,ticket)=>invoke<{eligible:boolean}>("capture_presented",{captureId,ticket}),
  sample:(captureId,ticket,requestId,point)=>invoke<{request_ticket:string}>("capture_sample",{captureId,ticket,requestId,...point}),
  cancel:(captureId,ticket)=>invoke("capture_cancel",{captureId,ticket}),
};
export const requestColorScopes=(documentId:string,requestId:string,stage:ScopeStage)=>
  invoke<{requested:boolean}>("color_scopes",{documentId,requestId,stage});
export type CurvePreview=Partial<Record<CurveChannel,number[]>>&{parametric?:number[];parametric_handles?:[number,number][]};
export const dragParametricCurve=(spec:CurveSpec,region:number,target:number)=>invoke<{spec:CurveSpec;y:number}>("curve_parametric_drag",{spec,region,target});
export const previewCurves = (spec:CurveSpec) => invoke<CurvePreview>("curve_preview",{spec});

export interface DocState {
  colour_grading?: {recipe:import('./colourGrading/model').Recipe;algorithm:string;note:string};
  extended_tone?: {spec:import('./extendedTone/model').Spec;active:boolean;monochrome:boolean;available:boolean};
  people?: PeopleView;
  shoulder_shape?: import('./shoulderShape/model').ShoulderView;
  leg_shape?: import('./legShape/model').LegView;
  waist_shape?: import('./waistShape/model').WaistView;
  neck_shape?: import('./neckShape/model').NeckView;
  leg_length?: import('./legLength/model').LegLengthView;
  arm_shape?: import('./armShape/model').ArmView;
  brow_shape?: {version:1;revision:number;selected_face_id:string;recipe:import("./browShape/model").BrowShape;sides:Partial<Record<import("./browShape/model").BrowSide,import("./browShape/model").BrowFact>>;suspended:string|null;bytes_fields:number};
  nose_shape?: {version:1;revision:number;selected_face_id:string;recipe:import("./noseShape/model").NoseShape;controls:Partial<Record<import("./noseShape/model").NoseKey,import("./noseShape/model").NoseFact>>;suspended:string|null;bytes_fields:number};
  eye_shape?: {version:1;revision:number;selected_face_id:string;recipe:import("./eyeShape/model").EyeShape;controls:Partial<Record<string,import("./eyeShape/model").EyeFact>>;suspended:string|null;bytes_fields:number;legacy_big_eye:number;native_available:boolean};
  mouth_shape?: {version:1;revision:number;selected_face_id:string;recipe:import("./mouthShape/model").MouthShape;controls:Partial<Record<string,import("./mouthShape/model").MouthFact>>;suspended:string|null;bytes_fields:number;legacy_smile:number;native_available:boolean};
  lip_makeup?: {version:1;recipe:import("./lipMakeup/model").LipMakeup;facts:import("./lipMakeup/model").LipFact;suspended:string|null;bytes_fields:number};
  effect_recovery?: import("./effectRecovery/model").RecoveryReport;
  optics?: import("./optics/model").OpticsReport;
  sky_replacement?: import("./skyReplacement/model").SkyReport;
  studio_background?: import("./studioBackground/model").Report;
  manual_liquify?: import("./manualLiquify/model").LiquifyReport;
  local_masks?: import("./localMasks/model").LocalMaskReport;
  fabric?: import("./fabric/FabricPanel").FabricState;
  document_id?: string;
  levels?: LevelsSpec;
  curves?: CurveSpec;
  strength: number;
  params: Record<string, number>;
  channel: string | null;
  light: { exposure: number; radius: number };
  counts: { repair: number; light: number; repair_redo: number; light_redo: number };
  deform: { amounts: Record<string, number>; built: boolean;
            /** 作用层（LNX-PORTRAIT-004）：面板要说“这一张已被单独覆盖 / 完全跟随默认”，
             *  只能从引擎这一格读。前端自己记一份“我刚才改的是哪一层”就会出现
             *  “面板显示默认而渲染用的是覆盖”那种双向错配。可选：老引擎没有这四格。 */
            scope?: "all" | "person";
            default?: Record<string, number>;
            overrides?: { box: number[]; amounts: Record<string, number> }[];
            overridden_kinds?: string[];
            inherited?: boolean;
            /** 「层在而关键点还没回来」（CORE-001 重开 / 迁会话）：滑块值不许弹回 0，
             *  面板要显示「等重新分析」，因为引擎已经答应自动补一次分析 */
            defer?: boolean };
  /** 多人图的分人编辑状态（PORTRAIT-003）。可选：老引擎的 doc_state 里没这一格，
   *  把它声明成必存就会在 JSON 边界上炸一个 TypeError 把整棵树拆掉。 */
  face?: FaceState;
  lut: { lit: boolean; amount: number; preset: string | null; asset_id?: string | null };
  grade: { dh: number; ds: number; dv: number; amount: number; lit: boolean;
           /** COLOR-004 局部调色：作用域、引擎报的可选名单、区域盖了多少格。
            *  下拉框的选中值只能从这里读：换图、重开工程、撤销都会改它，前端自己
            *  记一份就是在替引擎说谎（“当前值必须来自引擎”这条纪律没有例外）。 */
           scope?: string; scopes?: string[]; mask_px?: number };
  /** 眼牙局部增强（LNX-PORTRAIT-009）。整块可选：老引擎的 doc_state 里没这一格，
   *  声明成必存就会在 JSON 边界上炸掉整棵树。`reason` 是"那一格为什么没接通"的唯一
   *  出处——面板那句禁用说明只能引用它，不许前端自己推断（推断的那一句在换图之后
   *  就是说谎：闭嘴样本的牙齿那一格、侧脸被几何校验拒掉的那两只眼各有各的原因）。 */
  enhance?: EnhanceDoc;
  /** 曝光/白平衡（P0 lnx.exposure / lnx.white_balance）。`reference_k` 为 null 是
   *  “没指定参考光源”，不是 0：“中性=null 不能解成零”写在注册表的 null_semantics 里。 */
  exposure: { ev: number; temperature_shift: number; tint_shift: number;
              /** 影调四项（原创扩展，与 EV 同一层）：-100…100，0 = 关 */
              contrast?: number; highlights?: number; shadows?: number;
              saturation?: number;
              options?: {version:1;algorithm:"legacy-xyz-ratio-v1"|"linear-srgb-d-white-ratio-v1";picked_gains:[number,number,number]};
              reference_k: number | null; lit: boolean };
  /** 八色 HSL（原创扩展，与曝光层同一条链）：`bands` 是 8 段 × (色相/饱和度/明亮度)
   *  展平后的 24 个数；段名与色相中心也从引擎来（前端不抄一份色相表，那里迟早分叉）。
   *  整块可选：老引擎的 doc_state 里没这一格。 */
  hsl?: { bands: number[]; names: string[]; centers: number[];
          limits: { hue: number; sat: number; lum: number }; lit: boolean };
  /** 裁剪/旋转（P0 lnx.crop.v1）。rect 是归一化 [左,上,右,下]；`crop_out` 是代理档上
   *  剪后的尺寸，`out_full` 才是导出会写的真实像素数——两个数都得看得见，否则 UI 会
   *  把“预览里那一小块”讲成“文件的尺寸”。 */
  crop: { rect: number[]; rotation_degrees: number; neutral: boolean; lit: boolean;
          limits?: { min: number; max: number } | null;
          crop_out?: [number, number] | null; out_full?: [number, number] | null };
  /** 这一张文档自己的撤销/重做账（M5-b）。随文档走：切到底片条另一格时拿到的是
   *  那一格的栈深，不是全进程一个数。 */
  history: HistoryReport;
}

/** 历史账（M5-b）：引擎是唯一数步数的人，前端只照它报的摆按钮。 */
export interface HistoryReport {
  can_undo: boolean;
  can_redo: boolean;
  undo_steps: number;
  redo_steps: number;
  history_max: number;
}

/** 最近一条 history_state（M5-b）。doc_state 是撤销之后引擎认定的文档状态——
 *  宿主重摆滑块的唯一出处（同图撤销时 docKey 不变，走不到 image_ready 那条路）。 */
export interface HistoryState extends HistoryReport {
  action: "undo" | "redo" | "state" | "clear";
  doc_state: DocState;
  /** 退无可退时引擎发 noop 而不是 error：快捷键按多了是常态。 */
  noop?: boolean;
  /** 只有真撤销/真重做才带：这一次的历史耗时与出帧耗时。 */
  history_ms?: number;
  render_ms?: number;
}

/** session_state.docs 的一项。缩略图不在这里：像素由 filmstrip 单独取。 */
export interface SessionDoc {
  index: number;
  path: string;
  name: string;
  bytes_on_disk: number;
  w: number | null;
  h: number | null;
  src_w: number | null;
  src_h: number | null;
  loaded: boolean;
  opened: boolean;
  edits: SessionEdits;
  /** 工程层的三个字段随底片条上报（状态徽章与多选批量都要在格子上直接可读）：
   *  标签/标记/回收站都是工程记录，不是对原图动手。 */
  tags: string[];
  label?: string | null;
  trashed: boolean;
  /** 这一格算过源文件指纹没有（项目保存/打开时才算） */
  hashed?: boolean;
  /** `preview` 为真时这一格画的是**相机内嵌预览**（RAW 那一族），不是引擎渲的那一帧；
   *  `format` 是解码报的格式名（DNG/CR2/JPEG…）。两个都不能缺：缺了就分不出
   *  “jpg 的真图”与“DNG 的相机预览”，而底片条上后者看起来跟前者一模一样。 */
  thumb: { w: number; h: number; bytes: number; quality: number;
           preview?: boolean; format?: string | null } | null;
  thumb_error: string | null;
  /** 挑图建议（LNX-PICK-001）：本地确定性度量折出来的一格旁注。null/缺 = 这一格还没量。
   *  徽章与原因只从这一份读：前端自己按缩略图亮度判"这张糊不糊"就是第二个不可复算的出处。 */
  pick?: PickSuggestion | null;
  pick_error?: string | null;
}

/** 预设面（LNX-P0-PRESET）：清单与“哪些模块能作用”全部由引擎报，前端不扫目录。 */
export interface PresetInfo {
  schema: string;
  id: string;
  name: string;
  kind: string;
  builtin: boolean;
  modules: Record<string, Record<string, unknown>>;
  author?: string;
  note?: string;
}

/** `lnx.batch.v1.module_scope` 那一份契约的运行时报信：transferable=false 的格子
 *  带着“为什么没接通”，UI 直接拿它写禁用理由（不在前端刻第二份理由）。 */
export interface ScopeModule {
  dedicated_transport?: string;
  operation_id: string;
  params: string[];
  transferable: boolean;
  single_face: boolean;
  unmodeled?: Record<string, string>;
  reason?: string | null;
}

export interface PresetState {
  available?: boolean;
  list: PresetInfo[];
  errors: { file: string; error: string }[];
  modules: ScopeModule[];
  dir: string;
  schema: string;
  /** “这一张现在等于哪个预设”由引擎判（套完又被手改就不算），前端不记这一份。 */
  last_applied?: { id: string; name: string } | null;
}

/** 批量同步台账（LNX-P0-BATCH / BATCH-004）：撤销要拿引擎报的那个 id。 */
export interface SyncState {
  batches: { batch_id: string; module_scope: string[]; targets: number; undone: boolean }[];
  undoable: string[];
  last: string | null;
  /** 上一笔 commit/undo 的事实：UI 那句“同步了几张、跳过几张为什么”只能读这里。 */
  last_result?: {
    kind: string; batch_id: string;
    applied?: number[]; skipped?: { index: number; path: string; reason: string }[];
    restored?: number[]; conflicts?: { index: number; path: string; reason: string }[];
  } | null;
}

/** 挑图建议的一条原因（LNX-PICK-001）：method / 数值 / 阈值 三件齐全。
 *
 *  为什么这三件必须一起到 UI：这条功能的承诺是"任何人都能复算"，缺一个就退化成
 *  "引擎说了算"。文案（text）里已经把数值与阈值写进句子，但名单化的 value/threshold
 *  才是可以被机器对账的那一份。
 */
export interface PickReason {
  kind: string;
  method: string;
  value: number | null;
  threshold: number | null;
  text: string;
  group_size?: number;
  rank?: number;
  scope?: { analyzed?: number; pooled?: number };
  ratio?: number;
  ratio_threshold?: number;
  batch_median?: number;
}

/** 一张图的全部读数：没有一个字段是结论（结论在 labels/suggest 里，由引擎折）。 */
export interface PickMeasures {
  dhash: string;
  sharpness: number;
  clarity_ratio: number;
  contrast: number;
  under: number;
  over: number;
  /** null = 没量到（没探到脸/没装后端）。UI 不许把它渲染成"睁眼"。 */
  eye_open: number | null;
  eye_note?: string;
  faces: number;
  /** "pixels" / "camera_preview"：RAW 那一族的读数来自相机内嵌预览时必须看得见 */
  decoded_from?: string;
  decode_size?: number[];
  measure_edge: number;
  algo: string;
  ms?: Record<string, number>;
}

export interface PickSuggestion {
  schema: string;
  path: string;
  labels: string[];
  suggest: string;
  overridable: boolean;
  overridden_by_user: boolean;
  /** 这两格恒为假：挑图这一层没有删除能力（手册 §AI挑图 与冻结件的同一条 then） */
  auto_deleted: boolean;
  auto_trashed: boolean;
  sensitivities?: Record<string, string>;
  reasons: PickReason[];
  measures: PickMeasures;
  notes?: string[];
  fingerprint?: string;
  edge?: number;
  batch_median_ratio?: number;
  group_leader?: string | null;
  decoded_from?: string;
  analyzed_at_ns?: number;
}

/** pick_start / pick_progress / pick_done / pick_state 共用的一格播报（按事件名分形）。 */
export interface PickRun {
  event: string;
  targets?: number;
  done?: number;
  total?: number;
  count?: number;
  measured?: number;
  failed?: number;
  pooled?: number;
  reused_hashes?: number;
  stopped?: boolean;
  groups?: { size: number; leader: string; members: string[] }[];
  sensitivities?: Record<string, string>;
  thresholds?: Record<string, unknown>;
  schema?: string;
  algo?: string;
  fingerprint?: string;
  edge?: number;
  batch_median_ratio?: number;
  eyes_backend?: string | null;
  eyes_error?: string | null;
  measure_ms?: number;
  total_ms?: number;
  reason?: string;
  rows?: number;
  analyzed?: number;
  labels?: string[];
}

/** 最近一条 session_state（底片条全貌 + 当前文档状态）。 */
export interface SessionState {
  index: number;
  count: number;
  current: string | null;
  thumbs_running: boolean;
  /** 挑图后台任务在不在跑（引擎报的，前端不自己数 pick_item）。 */
  picks_running?: boolean;
  docs: SessionDoc[];
  doc_state: DocState | null;
  /** 预设清单与同步台账：随同一条 session_state 上来，UI 不在前端记第二份。 */
  presets?: PresetState | null;
  sync?: SyncState | null;
  /** select 命中当前那一格时引擎会补发一条 noop=true 的状态：它没开新会话。 */
  noop?: boolean;
}

/** filmstrip 命令的返回：格子元信息 + path→缩略图 base64（JPEG）。 */
export interface Filmstrip {
  session: SessionState | null;
  thumbs: Record<string, string>;
}

/** 导入期一次预计算的回报：M1-3c 拖滑块只消费这里的通道名与常驻设备。 */
export interface Precompute {
  backend: string;
  num_landmarks: number;
  landmark_shape: number[];
  mask_channels: string[];
  mask_nonzero_pixels?: Record<string, number>;
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
  /** 几何看上去像不像一张脸（判据只写在引擎的 face.geometry_warning 里） */
  geometry_warning: boolean;
  /** 这一轮探到了几张脸（SCOPE-001）。面部重塑只在“恰好 1 张”时可用：
   *  引擎不拿其中某一张冒充“那张脸”，前端也不拿“有一个关键点集”当可用判据。 */
  num_faces: number;
  /** 超范围时引擎给的理由名（目前只有 "multi_face"）；前端不自己编第二个名字 */
  scope_block: string | null;
  /** 检测器上限探几张（不是“画上一共几张”：探到这一数就停） */
  max_faces_probed: number;
  notes: string[];
  /** 只有因换设备而重挂时才有：区分“真算了一次”与“只是重挂旧产物” */
  replayed_for?: string;
}

/** 一次消除笔事件的回报（引擎侧 inpaint_done）。事件驱动：只在松手时算一次。 */
export interface InpaintInfo {
  action: "add" | "undo" | "redo" | "clear";
  ops: number;
  applied: number;
  redo_pending: number;
  painted_px: number;
  boxes: number[][];
  repair_ms: number;
  filter_ms: number;
  render_ms: number;
  total_ms: number;
  bytes_base: number;
  /** 这一帧是否命中了滤波缓存（由执行路径给出，不是声明） */
  filter_cached: boolean;
  /** 本层是否真的重算了。与 filter_cached 不是一回事：两个名字共一个键时，
   *  引擎侧字典后写的会静默吃掉先写的，其中一条永远送不出来 */
  layer_recomputed: boolean;
  op_id?: number;
  decode_ms?: number;
  backend?: string;
  feather?: number;
  rle_runs?: number;
  params?: Record<string, number>;
  device: string;
  strength: number;
}

/** 一次修容笔事件的回报（引擎侧 light_done，M2-a2）。与消除笔同为事件驱动。 */
export interface LightInfo {
  action: "add" | "undo" | "redo" | "clear" | "params";
  ops: number;
  redo_pending: number;
  painted_px: number;
  /** 累加后的带符号场绝对峰值（≤1：档数上限钉在 exposure 上，不随笔数漂） */
  field_peak: number;
  /** 这层现在到底有没有生效（空场或 exposure=0 时为 false） */
  lit: boolean;
  exposure: number;
  radius: number;
  /** 建层成本（一次性）：重算场 + 上显存。与每帧的 light_ms 不是一个量 */
  light_build_ms: number;
  /** 本帧实际跑 db 的毫秒：拖磨皮滑块时应当为 0 */
  light_ms: number;
  filter_ms: number;
  bands_ms: number;
  render_ms: number;
  total_ms: number;
  bytes_light: number;
  /** 这一帧的磨皮滤波是否命中缓存（与下面两条分开：三个数说的是三件事） */
  filter_cached: boolean;
  /** 本条事件是否真的重算了修容场：改参数（params）不重算 */
  layer_recomputed: boolean;
  op_id?: number;
  sign?: number;
  decode_ms?: number;
  feather?: number;
  rle_runs?: number;
  params?: Record<string, number>;
  device: string;
  strength: number;
}

/** 一次形变事件的回报（引擎侧 deform_done，M2-b）。三个滑块一条。 */
/** 多人图里「这张图上有谁、正在改谁」（LNX-PORTRAIT-003）。
 *
 * 每一个字段都来自引擎的 `_face_state()`：名单是那一次真实分析算出来的，前端数不来
 * 也不许猜。`blocked` 是唯一的放行判据——它是「多人而用户还没点选」，那时面部重塑
 * 整条被拒（SCOPE-001），面板必须显式禁用并写明原因，而不是留一个点了没反应的滑块。 */
export interface FacePerson {
  index: number;
  /** 归一化脸盒 [左,上,右,下]；认不回那一张时为 null */
  box: number[] | null;
  /** 脸盒占画幅的比例（0–1），只用来给 chip 排个序、显示大小 */
  area: number;
  /** 这一张的点位出自**用户框的区域**（不是这一轮检测自动找到的）——chip 要标"人工" */
  manual?: boolean;
  /** 用户说过"这不是脸"（LNX-PORTRAIT-006）。被标上的那一张不再被任何单脸作用域操作服务 */
  disabled?: boolean;
}
/** 人脸名单上的人工账（引擎 `_face_state().manual` 同一份）。 */
export interface FaceManual {
  /** 用户关掉的那些脸（归一化盒）。认不回也留账——丢掉就是一次静默恢复 */
  disabled: number[][];
  /** 用户框出来补上的那些区域（归一化框） */
  added: number[][];
  /** 账上有、这一轮名单里认不回的禁用条目（面板要说明，不能装作还在生效） */
  stale: number[][];
  /** 账上有、这一轮没找回的人工框 */
  lost: number[][];
  /** 这一轮名单里没有任何人工记录的脸 = 这次检测新增的候选 */
  new_faces?: number[];
  /** 引擎算好的一句话（"保留 1 处禁用，1 处人工框未找回"） */
  preview?: string;
}
export interface FaceState {
  index: number;
  /** 这一张是不是用户显式点选的（引擎区分「默认 0 号」与「用户选了 0 号」） */
  explicit: boolean;
  box: number[] | null;
  num_faces: number;
  faces: FacePerson[];
  /** 还没被人关掉的那些人的 index。`blocked` 按这一格算，不按 `num_faces` 算 */
  enabled?: number[];
  disabled_count?: number;
  /** 人工账（PORTRAIT-006）：关掉的与补上的都在这一格里 */
  manual?: FaceManual;
  blocked: boolean;
  /** 人像模块作用面受限的原因码（multi_face）；null = 不受限 */
  scope_block: string | null;
  max_faces_probed: number;
}

/** 眼牙局部增强在引擎里的那一格账（doc_state.enhance 与 enhance_done 同一个组装点）。 */
export interface EnhanceDoc {
  facial_wrinkles?: Record<string, RegionFact>;
  /** 三个子功能当前的滑块值，[0,1]；0 就是这一格没开 */
  amounts: Record<string, number>;
  /** 子功能名单：面板画几条滑块由引擎这一格决定，前端不刻第二份 */
  subs?: string[];
  /** 值域 [0, limit]（ready 里也报一份） */
  limit?: number[];
  /** 挂过场没有（第一次非零 set 时从关键点重画） */
  built: boolean;
  /** 这一层现在真的有力吗：`built` 而 `lit=false` 是常态——闭嘴样本的牙齿那一格 */
  lit: boolean;
  /** 场还没重画（重开工程 / 迁会话 / 换后端）：参数已存住，等下一次分析自动接回 */
  defer?: boolean;
  /** 这一层挂在谁的脸上（归一化脸盒）；认不回时为 null。SCOPE-001 的落点 */
  box?: number[] | null;
  /** 每个子功能过了内容门的格数（0 就是那一格这一张上不会动） */
  gated_px?: Record<string, number>;
  /** 每个子功能没接通时引擎说的那句话；null = 接通了 */
  reason?: Record<string, string | null>;
}

/** 一次眼牙增强事件的回报（引擎侧 enhance_done，LNX-PORTRAIT-009）。 */
export interface EnhanceInfo extends Omit<EnhanceDoc, "reason"> {
  /** set/clear 是用户发的；rebuild 是关键点回来后重画掩膜；invalidate 是整层被放下
   *  （换成 synthetic / 认不回那一张脸 / 重画失败）；defer 是"参数存住等分析" */
  action: "set" | "clear" | "rebuild" | "invalidate" | "defer";
  person_box?: number[] | null;
  render_ms: number;
  total_ms: number;
  /** 下面这些是宿主槽位里那份嵌套账（与 `_enhance_payload` 同名） */
  enhance_facial_wrinkles?: Record<string, RegionFact>;
  enhance_subs?: string[];
  enhance_limit?: number;
  enhance_geom_px?: Record<string, number>;
  enhance_mouth?: Record<string, unknown>;
  enhance_eyes?: Record<string, unknown>[];
  enhance_window?: number[] | null;
  bytes_enhance?: number;
  enhance_ms?: number;
  enhance_build_ms?: number;
  device?: string;
  layer_recomputed?: boolean;
  /** invalidate/defer 那两条给出的整层级说明 */
  note?: string;
  /** 事件这一份的 `reason` 是**整层**一句话（defer/invalidate 才有），与 doc_state
   *  那份逐子功能映射同名不同形。归一在 enhanceStateOf 里做。 */
  reason?: string | null;
  /** 逐子功能的原因（面板那句"这一格现在不会动"引用的就是它；与 doc_state.enhance.reason
   *  同一个来源 enhance_facts，所以两份必然同一句话） */
  enhance_reason?: Record<string, string | null>;
  /** 事件里那份嵌套的 amounts（宿主槽位读它；面板读平铺） */
  enhance_amounts?: Record<string, number>;
  enhance_lit?: boolean;
  dropped_amounts?: Record<string, number>;
}

export interface DeformInfo {
  /** set/clear 是用户发的；rebuild 是关键点更新后引擎重解单位场；
   *  invalidate 是层被整条清除（后端换成不能按脸形取点的 synthetic）——那一条
   *  必须把滑块归零，否则界面上写着 0.6 而画面一动不动 */
  action: "set" | "clear" | "inherit" | "rebuild" | "invalidate" | "defer";
  /** 作用层与层级那一份账（LNX-PORTRAIT-004，deform_done 与 doc_state 同一个组装点） */
  scope?: "all" | "person";
  default?: Record<string, number>;
  overrides?: { box: number[]; amounts: Record<string, number> }[];
  overridden_kinds?: string[];
  inherited?: boolean;
  /** 三种形变当前的滑块值，[-1,1]。0 就是不动。 */
  amounts: Record<string, number>;
  /** 单位场建过没有（第一次非零 set 时建） */
  built: boolean;
  /** 这层现在到底有没有生效：全零滑块就是 false */
  lit: boolean;
  /** 本帧形变段（组装 + grid_sample）的毫秒。拖滑块期间它就是这层的全部代价 */
  deform_ms: number;
  /** 三个单位场 + 恒等网格的常驻字节 */
  bytes_deform: number;
  render_ms: number;
  total_ms: number;
  /** 关键点出自哪个后端。template 是模板拟合、贴合度不验收，UI 得能显示这一句 */
  landmark_backend: string | null;
  /** 三种形变里最宽的一种会动到画幅的比例（0–1）。“瘦脸不许拖走背景”这句产品
   *  承诺在当前这张图上成不成立，只有这个数说得清：窗口参数只给圆心与半径，
   *  关键点落错地方时同一个公式会盖住整幅（真人照片上量到 0.99）。 */
  support_share: number;
  /** 引擎认为这套关键点不像一张脸（肤色包围盒贴到整幅边界）。判据在引擎里，
   *  前端不去 parse landmark_notes 的中文——改一个字界面就静悄悄不再警告。 */
  geometry_warning: boolean;
  /** 后端对这份几何的意见（模板拟合的自述 + 不像脸时的说明） */
  landmark_notes: string[];
  /** 只有真正建层的那一条才有：一次性解算成本与 kinds 明细 */
  build?: {
    deform_build_ms: number;
    deform_builds: number;
    bytes_deform: number;
    device: string;
    kinds: Record<string, { peak_px: number; merged: number; controls: number;
                            support_px: number; support_share: number }>;
  };
  /** invalidate 那一条说清为什么清（后端换了 / 重建失败），UI 要能直接给用户看 */
  reason?: string;
  /** invalidate 那一条带上刚才的滑块值：只报 lit=false 的话，滑块弹回零像出了 bug */
  dropped_amounts?: Record<string, number>;
  /** 这一层只是「等关键点回来」（重开工程 / 迁会话）：值还在，单位场还没解出来。
   *  与 invalidate 的区别要说清：invalidate 是层没了，defer 是层在等人。 */
  defer?: boolean;
  /** defer 那一条带着用户那一层的值（`amounts` 报的是会话当前真在渲染什么） */
  deferred_amounts?: Record<string, number> | null;
  device: string;
  strength: number;
}

/** 一次调色事件的回报（引擎侧 lut_done，M3-a2）。set/amount/clear 三条臂键集完全相同：
 * 引擎侧只有一个组装点，前端也可以直接按必存字段读。 */
export interface LutInfo {
  action: "set" | "amount" | "clear";
  /** 有没有挂上一张表。恒等表也是 true：“载入了一张表”与“生效了”是两件事 */
  lut_set: boolean;
  /** 这层现在到底有没有生效：恒等表或强度 0 就是 false */
  lut_lit: boolean;
  lut_kind: string | null;
  lut_size: number;
  lut_title: string;
  /** 这张表从哪来（文件名 / "text" / "preset:xxx"）。两张同名表时它是唯一的区分 */
  lut_source: string;
  /** 表是恒等的（且域为 0–1）：短路回去，一个字节也不改 */
  lut_neutral: boolean;
  /** 超出 [0,1] 被夹到端点的表值个数（静默吞掉一个参数比拒绝难查十倍） */
  lut_clipped: number;
  /** 库层对这张表的意见（粗表精度不足等），协议层不许把它吞掉 */
  lut_notes: string[];
  lut_domain_min: number[];
  lut_domain_max: number[];
  /** 混合系数 [0,1]：0 就是逐字节回到未调色那一帧 */
  lut_amount: number;
  /** 本帧跑 3D 查表的毫秒（产品档实测 0.35 ms） */
  lut_ms: number;
  /** 一次性上显存的成本：只有 set 那一条不为 0 */
  lut_mount_ms: number;
  /** 体积 + CPU 原件的常驻字节（只报一份就是藏账） */
  bytes_lut: number;
  lut_grid_bytes: number;
  filter_ms: number;
  bands_ms: number;
  /** 补的那一帧仍命中磨皮缓存：调色在链尾，它不该作废任何上游缓存 */
  filter_cached: boolean;
  deform_ms: number;
  render_ms: number;
  total_ms: number;
  /** 本条事件是否真的重挂了体积（只有 set 是 true） */
  layer_recomputed: boolean;
  device: string;
  strength: number;
  /** 本帧跑肤色定向的毫秒（M3-b：预设一条命令动两层，lut_done 必须能把两层都说出） */
  grade_ms: number;
  /** 定向层现状：与 grade_done 同一出处（都取自引擎里的常驻层），不是第二口径 */
  grade_state: GradeState;
  /** 当前生效的内置预设名；走 path/text 载表或手动改肤色时为 null */
  lut_preset: string | null;
  /** 这一条 clear 有没有连带把预设写进肤色定向的那一份一起拿掉。
   *  预设是两层（表 + 定向），`lut set preset=…` 自己写着“要么两层都上，要么
   *  都不上”，clear 不跟着对称就是半个撤销。 */
  preset_grade_cleared: boolean;
}

/** 肤色定向层（M3-b）的现状。它不持有任何张量：状态就是三个增量加一个混入比例。 */
export interface GradeState {
  /** 色相移动（占整圈的比例，正=往黄） */
  dh: number;
  /** 饱和相对量（-0.14 = 降 14%） */
  ds: number;
  /** 明度相对量 */
  dv: number;
  /** 混入比例 [0,1] */
  amount: number;
  /** 这层现在真的在服务：有参数且 amount≠0 */
  lit: boolean;
  /** 本层不占显存：报 0 而不缺键，“查过”才是这句话的内容 */
  bytes_grade: number;
}

/** 一次肤色定向事件的回报（引擎侧 grade_done，M3-b）。
 * set/amount/clear 三条臂键集完全相同：引擎侧只有一个组装点。
 *
 * 它**不继承** GradeState：grade_done 是铺平的一份（grade_dh / grade_amount /
 * grade_lit / grade_set），嵌套那份 grade_state 才是 dh / amount / lit。两套名字
 * 混进一个接口，TypeScript 一律当作必存——谎报发生在 JSON 边界上，编译期抓不到，
 * 现场是渲染时一句 TypeError 把整棵 React 树拆掉（画面就此冻结在 0 帧）。
 * M5-b 的真窗口轮第一次撞上：那时宿主才开始发 hello，grade_limits 不再为空，
 * 定向那一排第一次真的被渲染出来。 */
export interface GradeInfo {
  action: "set" | "amount" | "clear" | "scope" | "mask" | "mask_clear";
  /** 铺平的同一份数：payload 与嵌套字段都来自 _grade_payload */
  grade_dh: number;
  grade_ds: number;
  grade_dv: number;
  grade_amount: number;
  grade_lit: boolean;
  /** 有没有非零参数（全零就是关灯，层里没留下任何颜色改动） */
  grade_set: boolean;
  /** 本层不占显存时也报 0 而不缺键："查过"才是这句话的内容 */
  bytes_grade: number;
  grade_ms: number;
  /** [dh, ds, dv] 的硬边界：滑块的夹取范围由引擎说，前端不抄一份数然后两处漂 */
  grade_limits: number[];
  /** COLOR-004：当前生效的作用域与可选名单（同样是引擎说）。scope 只能拿这里
   *  列出的值去试：skin 要人脸掩膜、brush 要画笔区域，拿不到时引擎整条拒而不是
   *  默默退回全图——所以 UI 必须能看到“现在真的调的是哪一片”。 */
  grade_scope: string;
  grade_scopes: string[];
  /** 画笔区域盖了多少格（代理帧坐标）。0 与“没这一格”不同：那是引擎真报了一个 0。 */
  mask_px: number;
  lut_ms: number;
  lut_preset: string | null;
  filter_ms: number;
  bands_ms: number;
  filter_cached: boolean;
  deform_ms: number;
  render_ms: number;
  total_ms: number;
  layer_recomputed: boolean;
  device: string;
  strength: number;
}

/** 一次换底事件的回报（引擎侧 bg_done，M6）。事件驱动：一次“换底”一条。
 *  clear 臂不带 backend/bg/matte_fill_fg（那些只在 set 时有意义）——按 M5-b 那一课，
 *  引擎不发、这里就不许声明成必存。 */
export interface BackgroundInfo {
  action: "set" | "clear";
  bg_active: boolean;
  /** 遮罩 + 背景的常驻字节：没活时报 0 而不缺键 */
  bytes_bg: number;
  device: string;
  bg_ms: number;
  render_ms: number;
  total_ms: number;
  backend?: string;
  bg?: number[];
  /** 前景占比（alpha>127 的像素比例）：0–1 */
  matte_fill_fg?: number;
}

/** 引擎进程的运行时账单：ready 里的 runtime 与宿主选解释器的那几条合起来一份。
 *  键全部可选：新壳配旧引擎时 ready 里根本没有这一项（宿主也不会凭空造一个）。 */
export interface EngineRuntime {
  python?: string;
  /** env（$LRT_ENGINE_PY）/ explicit（面板里填了）/ runtime（候选表命中）/ fallback（python3）。 */
  python_source?: string;
  python_version?: string;
  engine_src?: string;
  hint?: string;
  /** 引擎 ready 报回来的包账单，单独一层（M5-c）。不铺平进这一层：宿主与引擎两边
   *  都有 `python` 这个键，铺平就是同名互相顶——装机校验读到过 "3.12.15" 当路径。 */
  packages?: {
    python?: string | null;
    engine_version?: string | null;
    numpy?: string | null;
    pillow?: string | null;
    torch?: string | null;
    torchvision?: string | null;
  };
}

export interface EngineStatus {
  /** 引擎运行时的来历与包账单（M5-c 开箱即用）。整块都取可选：ready 里没报就是
   *  这一版引擎不说自己是谁，UI 该什么都不显示——把可选字段声明成必存，谎报发生在
   *  JSON 边界上，编译期抓不到，运行期一个 TypeError 把整棵树拆掉（M5-b 那一课）。 */
  engine_alive?: boolean;
  engine_version?: string | null;
  engine_runtime?: EngineRuntime | null;
  shm: string;
  has_shm: boolean;
  emitted: number;
  delivered: number;
  logs: string[];
  /** 最近一次 image_ready；没导过图为 null。 */
  image: ImageReady | null;
  /** 最近一次 precompute_ready；换图/换引擎进程会清空。 */
  precompute: Precompute | null;
  /** 引擎关于「有几个人、在改哪一个」的最新一句陈述（PORTRAIT-003）。
   *  一个槽位、多源汇入：precompute_ready / face_selected / face_list，以及任何带
   *  doc_state 的事件。`source` 说的是哪一条事件说的，出问题时要能指认。 */
  face: { source: string; face: FaceState } | null;
  /** 最近一次 inpaint_done；换图/换设备会清空（图层跟着会话走）。 */
  inpaint: InpaintInfo | null;
  /** 最近一次 light_done；与 inpaint 同生命期，但两份结果各自一份，不串台。 */
  light: LightInfo | null;
  /** 最近一次 deform_done（M2-b）；换图/换引擎进程会清空（关键点不在，层也不在）。 */
  deform: DeformInfo | null;
  /** 最近一次 lut_done（M3-a2）；换图会清空（调色层随文档走，不随引擎进程走）。 */
  lut: LutInfo | null;
  /** 最近一次 grade_done（M3-b）；与 lut 同生命期：肤色定向也随文档走。 */
  grade: GradeInfo | null;
  /** 最近一次 enhance_done（PORTRAIT-009）；换图/换引擎进程会清空（掩膜是从关键点
   *  重画的，没有关键点就没有这一层）。 */
  enhance: EnhanceInfo | null;
  /** 最近一次 bg_done（M6 换底）；换图/换设备会清空（遮罩随代理档与设备走）。 */
  background: BackgroundInfo | null;
  /** 引擎在 ready 里报出的内置预设清单（M3-b）。空数组 = 这个引擎还没这一能力，
   *  UI 就不画按钮，而不是前端自己抄一份名字去撞一个不存在的资产。 */
  presets: LutPresetInfo[];
  /** [dh, ds, dv] 的硬边界（ready 里报的）：滑块行程的唯一出处。空数组 = 这个引擎
   *  还没这一能力，定向那一排就不画。 */
  grade_limits: number[];
  /** 最近一次 export_done（M4 批量出片）；换图/换引擎进程会清空。 */
  export: ExportDone | null;
  /** 最近一条 export_progress：第几张 / 共几张。null = 没在跑（或刚跑完）。 */
  export_progress: ExportProgress | null;
  /** 引擎在 ready 里报的导出能力。null = 这个引擎还不能导出，按钮就不画。 */
  export_caps: ExportCaps | null;
  /** 引擎在 ready 里自报的 RAW 解码能力（raw.py 的 raw_backends）。null = 这一版引擎
   *  还没报过这份清单。能读什么由引擎说，前端不刻一份——把没落地的 CR2 支持写进 UI 就是一条假指标。 */
  raw_backends: RawBackends | null;
  /** 引擎 scan 那份白名单（ready 里报的 image_exts）：原生选择框的过滤器用它。
   *  null = 这一版引擎没说，选择框就退化成“什么都不过滤”，不拿宿主抄的名单去挡人。 */
  image_exts: string[] | null;
  /** 导出位深能力（M9-e，引擎单一口径）：每个位深对应哪些落盘格式。
   *  引擎没报（老引擎）就不画 16-bit 那个勾，而不是默认"应该能写"。 */
  export_bits?: { "8"?: string[]; "16"?: string[] } | null;
  /** 引擎最近一条 error（M9）：load_image 发出去就返回，失败只走 error 事件。
   *  不接住它，坏路径就是一次彻底的静默失败。 */
  last_error: string | null;
  color_scopes?: ScopeResult|null;
  curve_result?: {request_id:string;document_id:string;host_doc_rev:number;success:boolean;spec:CurveSpec}|null;
  levels_result?: {request_id:string;document_id:string;host_doc_rev:number;success:boolean;spec:LevelsSpec;error:string|null}|null;
  /** 引擎在 ready 里自报的抠图后端清单（birefnet.py 的 matting_backends）。null =
   *  这一版引擎还没报过。换底下拉项由这一份决定：权重未放行时 birefnet 在
   *  weights_gated 里，摆一个注定被拒的选项就是邀请用户去撞一个空请求。 */
  matting_backends: MattingBackends | null;
  /** 最近一条 session_state（M5-a 底片条）；换引擎进程会清空。 */
  session: SessionState | null;
  /** session_state / 缩略图每来一条就 +1：前端只在它变了的时候整条重取底片条。 */
  session_rev: number;
  /** 宿主已收到多少张缩略图（按 path 计）。 */
  thumbs_ready: number;
  /** 挑图（LNX-PICK-001）：最近一条 pick_* 账单，与已收到的建议格数。
   *  进度那句话只能读这两项——前端自己数徽章就是把引擎的后台状态改成自己的猜测。 */
  pick?: PickRun | null;
  pick_items?: number;
  /** 最近一条 history_state（M5-b）；换引擎进程会清空。 */
  history: HistoryState | null;
  /** history_state 每来一条 +1：宿主只在它变了的时候按引擎那份 doc_state 重摆滑块。 */
  history_rev: number;
  /** 发过编辑命令、还没听到引擎的历史答复：撤销按钮在这段窗口里保持可用。 */
  history_dirty: boolean;
  edit_queue?: { pending: number; in_flight: boolean; coalesced: number; closed: boolean };
  /** 最近一条带 doc_state 的事件（image_ready / session_state / history_state 之一）。
   *  历史账只从这三条里来，而谁最后到只有宿主按到达次序数得出来。 */
  doc_report: { source: string; doc_state: DocState } | null;
  /** doc_report 每换一次 +1：前端只在它变了的时候取新的栈深。 */
  doc_rev: number;
  /** ready 报的"哪些命令算编辑"。空数组 = 这个引擎还没有历史能力。 */
  history_edit_cmds: string[];
  /** ready 的整份能力清单（宿主不逐字段抄）：面板上的动作名单、工程后缀、导出格式
   *  这些“引擎说什么能力”的清单都从这一份读。老宿主没报时为 undefined——那时那一排
   *  控件按“引擎没说”处理（不画/禁用），而不是前端自己猜一份。 */
  ready_caps?: {
    colour_grading_protocol?: number;
    extended_tone_protocol?: number;
    lip_makeup_protocol?: number;
    eye_light_protocol?: number;
    blush_makeup_protocol?: number;
    lipstick_protocol?: number;
    eyeliner_protocol?: number;
    eyelash_protocol?: number;
    iris_makeup_protocol?: number;
    brow_makeup_protocol?: number;
    brow_shape_protocol?: number;
    nose_shape_protocol?: number;
    eye_shape_protocol?: number;
    mouth_shape_protocol?: number;
    reference_color_protocol?: number;
    shoulder_shape_protocol?: number;
    leg_shape_protocol?: number;
    waist_shape_protocol?: number;
    neck_shape_protocol?: number;
    leg_length_protocol?: number;
    arm_shape_protocol?: number;
    semantic_colour_protocol?: number;
    semantic_colour_workflow_protocol?: number;
    hair_colour_protocol?: number;
    sample_library_protocol?: number;
    effect_recovery_protocol?: number;
    optics_protocol?: number;
    sky_replacement_protocol?: number;
    sky_semantic_protocol?: number;
    manual_liquify_preview_protocol?: number;
    studio_background_protocol?: number;
    manual_liquify_protocol?: number;
    local_grade_live_protocol?: number;
    source_patch_capture_protocol?: number;
    source_patch_result_protocol?: number;
    clone_stamp_protocol?: number;
    local_masks_result_protocol?: number;
    white_balance_result_protocol?: number;
    white_balance_capture_protocol?: number;
    color_picker_capture_protocol?: number;
    color_picker_result_protocol?: number;
    color_capture_protocol?: number;
    batch_preflight_protocol?: number;
    preset_result_protocol?: number;
    curve_recipe_versions?:number[];
    color_scopes_protocol?: number;
    project_actions?: string[];
    /** 挑图（LNX-PICK-001）：动作名单、四组档位的可选值、阈值本体与判据指纹。
     *  面板上的下拉项由这几格决定，前端不刻一份档名（刻了就双出处）。 */
    pick_actions?: string[];
    pick_sensitivities?: Record<string, string[]>;
    pick_thresholds?: Record<string, unknown>;
    pick_fingerprint?: string;
    pick_algo?: string;
    pick_edge?: number[];
    pick_edge_default?: number;
    project_suffix?: string;
    /** 形变名单与值域（LNX-PORTRAIT-012 起）。面板画几格滑块由这一格决定，
     *  前端不再自己刻一份元组——刻了就是第二个出处，加 kind 时必然出现
     *  "引擎有而屏幕上没有"（与 auto_pick 那一格同一类）。 */
    deform_kinds?: string[];
    deform_range?: number[];
    /** 眼牙增强（LNX-PORTRAIT-009）：子功能名单、值域与动作名单。面板画几条滑块
     *  由这几格决定——引擎加了第四个子功能而屏幕上没有，就是双出处的形状。 */
    enhance_facial_wrinkles?: Record<string, RegionFact>;
  enhance_subs?: string[];
    enhance_range?: number[];
    enhance_actions?: string[];
    /** 人脸名单能收哪些动作（LNX-PORTRAIT-006）：面板上 ✕/↺/⌫/「框一位」这几格
     *  画不画由这一格决定，前端不刻第二份名单。 */
    face_actions?: string[];
    people_protocol?: number;
    task_actions?: string[];
    export_formats?: string[];
    [k: string]: unknown;
  } | null;
  /** 最近一条项目播报（created/opened/saved/edited/state）。整块可选：老引擎不报
   *  就什么都不显示，而不是前端自己记一份"存过了"。 */
  project?: ProjectState | null;
  project_rev?: number;
  /** 批量任务台账（按 task_id 聚合的最新一条）。可用性只从这份读：
   *  转移表在引擎里，前端不自己判"这条能不能暂停"。 */
  tasks?: TaskState[];
  task_rev?: number;
}

/** 工程面（LNX-P0-PROJECT）：名字、脏标记、格数与"这一版没存进去的东西"。 */
export interface ProjectState {
  event?: string;
  open?: boolean;
  path?: string | null;
  name?: string | null;
  project_id?: string | null;
  docs?: number;
  dirty?: boolean;
  saved_ns?: number | null;
  /** 台账格数（不是清单）：清单在 project_saved 的 `dropped` 里，两件事不共用一个名字 */
  tasks?: number;
  dropped_count?: number;
  bytes?: number;
  sha256?: string;
  write_ms?: number;
  hash_ms?: number;
  fingerprinted?: number;
  /** project_saved 才有：没存进工程文件的层与原因（逐条，上限 12） */
  dropped?: { path?: string; at: string; reason: string }[];
  /** project_opened 才有：读回来时逐条说了什么 */
  task_restore?: { task_id: string; state: string; blocked: string }[];
  missing?: { path: string; exists: boolean }[];
  missing_count?: number;
  changed?: { path: string; level?: string; head_match?: boolean; bytes_match?: boolean; full_match?: boolean | null }[];
  changed_count?: number;
  auto_opened?: string | null;
  proxy_budget?: number | null;
}

/** 任务台账的一格（引擎 task_state 的宿主搬运，状态机在 tasks.py）。 */
export interface TaskState {
  task_id: string;
  kind: string;
  state: "queued" | "running" | "pause_requested" | "paused" | "resuming"
    | "cancelling" | "cancelled" | "retrying" | "succeeded" | "failed" | string;
  attempt: number;
  counts: { total: number; succeeded: number; failed: number; skipped: number; pending: number };
  batch: { running: number; state: string; counts: Record<string, number> };
  persisted: boolean;
  blocked_reason: string | null;
  out_dir: string | null;
  updated_ns: number;
  note?: string;
}

/** 一次导出的逐图账单（export_done.images[] 的一项，M4）。
 *
 * 失败项只有 path/stage/error：一张坏路径只塌自己那一张，不带倒整批。
 * skipped 是逐图报的：不是当前文档的那些图不会带上笔迹/形变/通道，这句话
 * 必须逐张说清，不能默默少几层。
 */
export interface ExportedImage {
  path: string;
  outputs?: {path: string | null; variant: string; skipped?: boolean}[];
  watermark?: {enabled: boolean; orientation?: string; asset_sha256?: string};
  /** 16-bit 母档读回差值必须为0；档位/低8位是诊断而非纯色图拒绝条件。
   *  冲突跳过时没有读回，三个诊断值为null。 */
  bits?: number;
  source?: string | null;
  readback_max_diff?: number | null;
  levels_per_channel?: number[] | null;
  low8_nonzero_px?: number | null;
  decode_ms?: number;
  readback_ms?: number;
  verification_ms?: number;
  semantic_analysis_ms?: number;
  pipeline?: "passthrough_rgb16" | "float32_rgb16";
  render_stats?: Record<string, unknown>;
  out?: string;
  format?: string;
  bytes?: number;
  write_ms?: number;
  w?: number;
  h?: number;
  px?: number;
  src_mb?: number;
  /** 放大（M7）：源幅与倍率。只报 `w/h` 分不出"2× 真做了"与"导出了原图"。 */
  src_w?: number;
  src_h?: number;
  scale?: number;
  upscale_backend?: string | null;
  upscale_ms?: number;
  sharpen_ms?: number;
  sharpen_amount?: number;
  tile?: number;
  tiles?: number;
  margin_px?: number;
  deform_peak_px?: number;
  total_ms?: number;
  field_ms?: number;
  per_tile_ms?: number;
  seg_ms?: Record<string, number>;
  delta_cpu_mb?: number;
  channel?: string | null;
  repair_ms?: number;
  applied?: number;
  skipped?: string[];
  stage?: string;
  error?: string;
}

/** 一批导出的终态（引擎侧 export_done，M4）。 */
export interface ExportDone {
  layout_result?: import("./layout/model").LayoutReceipt | null;
  total: number;
  failed: number;
  out_dir: string;
  format: string;
  quality: number;
  tile: number;
  /** 这一批用的倍率/后端/锐量（引擎拍一次报一次，不是前端自己记得） */
  scale?: number;
  upscale_backend?: string | null;
  sharpen?: number;
  /** 这一批的位深（引擎报，不是前端自己记得）：16 意味着走的是直通那条不进图层的链 */
  bit_depth?: number;
  total_ms: number;
  images: ExportedImage[];
}

/** 逐图进度（引擎侧 export_progress，M4）。index 从 0 起。 */
export interface ExportProgress {
  index: number;
  total: number;
  path: string;
  ok: boolean;
}

/** 导出能力（ready 报的）：格式名单与 tile 行程由引擎说，前端不抄一份。 */
export interface ExportCaps {
  formats: string[];
  tile: [number, number];
  tile_default: number | null;
  /** 允许的放大倍率（M7）。缺 = 这一版引擎不说倍率，放大那一排就不画。 */
  scales?: number[] | null;
  /** 放大能力清单（upscale.py 的 scale_backends）：哪一档装机即用、哪一档等权重。 */
  upscale_backends?: UpscaleBackends | null;
}

/** 放大后端清单：baseline 与 weights_gated 是两种不同强度的主张，不许混报。 */
export interface UpscaleBackends {
  baseline: string[];
  weights_gated: string[];
}

/** 抠图后端清单（M6）：与放大那一档同一个口径、同一种形状，故复用同一份定义——
 *  两处各自刻一遍就会漂（EXPORT_KEYS 那一课已经付过一次钱）。 */
export type MattingBackends = UpscaleBackends;

/** raw.py 的 raw_backends 形状：基线能读什么、哪些需插件、插件装没装。 */
export interface RawBackends {
  baseline: string[];
  suffixes: string[];
  needs_plugin: string[];
  plugin: string;
  plugin_installed: boolean;
  /** M9-h 定稿口径：已全链路自验的后缀，与依赖系统 LibRaw 但没有实机样张的那一栏。
   *  老引擎没报就是 undefined——那时前端只报 suffixes 那一行，不替引擎编一句"已认证"。 */
  suffixes_verified?: string[];
  verified_full_chain?: string[];
  vendor_suffixes?: string[];
  vendor_status?: string;
  sample_certified?: { [k: string]: boolean };
}

/** 一个内置预设的可显示信：提交只靠 name，文字只靠 title。 */
export interface LutPresetInfo {
  name: string;
  title: string;
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

/** 取最新帧：LRF1 128B 头 + RGBA 裸像素。无新帧时以 "NO_NEW_FRAME" 拒绝。 */
export const pullFrame = () => invoke<ArrayBuffer>("pull_frame");

/** 只读快照：拿"此刻屏幕上是什么"，与投递计数无关（见 main.rs 的 peek_frame）。
 *  自动通道量像素用这条，不能用 pullFrame——那条会因"这帧已经投过了"拒发，
 *  而渲染循环本来就在逐帧拉取，测试路径永远抢不到。 */
export const peekFrame = (respectTiers=false) => invoke<ArrayBuffer>("peek_frame",{respectTiers});

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

/**
 * 滑块动一下：引擎只重算系数。channel 指到常驻掩膜通道也不产生任何推理或上传。
 * radius/eps/textureRadius 变的是**分带**（实测产品档 5 ms），detailGain/midGain/broadGain
 * 变的只是**重组**（~0.5 ms），strength 两者都不动（~0.1 ms）。
 * 两层都是“松手才提交”：逐事件发会把 M1-3c 拿回来的 vsync 余量又吐出去。
 */
/** 按住看原图：on=true 临时出一帧原图，on=false 回到修好的那一版。不改会话强度。 */
export const setCompare = (on: boolean, captureId?: string) => invoke<{ on: boolean }>("compare", { on, captureId });
export const compareStatus = () => invoke<import("./compareCapture").CompareReceipt | null>("compare_status");

export const setStrength = (
  value: number | undefined,
  opts?: { channel?: string; radius?: number; eps?: number; detailGain?: number;
           midGain?: number; broadGain?: number; textureRadius?: number; interactionKey?: string },
) =>
  invoke<{ value: number | null }>("set_strength", {
    value,
    channel: opts?.channel,
    radius: opts?.radius,
    eps: opts?.eps,
    detailGain: opts?.detailGain,
    midGain: opts?.midGain,
    broadGain: opts?.broadGain,
    textureRadius: opts?.textureRadius,
    interactionKey: opts?.interactionKey,
  });

/** 对当前已导入的图跑一次导入期预计算；结果靠 engineStatus().precompute 轮询。 */
export const runPrecompute = (opts?: { backend?: string; channel?: string; modelDir?: string }) =>
  invoke<{ requested: boolean }>("precompute", {
    backend: opts?.backend,
    channel: opts?.channel,
    modelDir: opts?.modelDir,
  });

/**
 * 消除笔：action=add 带行程编码；undo/redo/clear 不带画。异步语义同 loadImage：
 * 结果靠 engineStatus().inpaint 轮询。不把它做成同步调用——一次修补要几十毫秒，
 * 而“松手就能看见结果”靠的是不等回答、下一帧自然上屏。
 */
export const runInpaint = (
  action: InpaintInfo["action"],
  opts?: { rle?: number[][]; feather?: number; backend?: string; refineIters?: number },
) =>
  invoke<{ requested: boolean }>("inpaint", {
    action,
    rle: opts?.rle,
    feather: opts?.feather,
    backend: opts?.backend,
    refineIters: opts?.refineIters,
  });

/** 修容笔（M2-a2）：与消除笔同一套事件调度，一次松手一条。
 *
 * sign 是方向而不是强度：+1 减淡、-1 加深，强度由这层的 exposure（档数）给出。
 * 这样“多画几笔”只是让场更接近上限，不会像逐笔乘那样把脸烧穿。
 */
export const runLight = (
  action: LightInfo["action"],
  opts?: { rle?: number[][]; feather?: number; sign?: number; exposure?: number; radius?: number },
) =>
  invoke<{ requested: boolean }>("light", {
    action,
    rle: opts?.rle,
    feather: opts?.feather,
    sign: opts?.sign,
    exposure: opts?.exposure,
    radius: opts?.radius,
  });

/** 五官微调（M2-b）：送三个滑块的值。
 *
 * 与修容笔不同，这条在拖动期间也要发：引擎侧只把已常驻的单位场按新系数缩放，
 * 一次 TPS 也不重解（拖 600 帧 deform_builds 不增，见 m2-face-bench）。
 * 不发就等于“滑块拖了、画面不动”。
 */
export const runDeform = (action: DeformInfo["action"], amounts?: Record<string, number>,
                           scope?: "all" | "person", peopleContext?: PeopleContext) =>
  // scope 给了才附（与 amounts 同一条规矩）：宿主写默认值等于替引擎做决定，而
  // `inherit` 这一臂根本没有 amounts——两个都要能缺省，名单只在引擎的 ready 里
  invoke<{ requested: boolean }>("deform", { action, amounts, scope, peopleContext });

/** 多人图选人（LNX-PORTRAIT-003）：list 问名单，select 点定「这次改哪一张」。
 *
 * 为什么必须走引擎而不是前端自己记住「我点了第几个人」：SCOPE-001 挡的就是「引擎替你
 * 选了一张脸」，放行的凭据必须是用户的一次显式点击，而这份点击要进文档状态、进撤销栈、
 * 进出片口径。前端只画 chip 与发 index。答复走 face_selected（轮询 status.face 取）。 */
/** 引擎关于「这张图上有几个人、正在改哪一个」的最新一份。
 *
 *  先后次序只在这一处定：事件槽位（precompute_ready / face_selected）比 doc_state 新——
 *  重开工程那一刻 image_ready 先带着「还没分析」的 face 出来，几百毫秒后自动补的那次
 *  分析才把名单与选型报回来。写两份就会有一份漂。 */
export const faceStateOf = (st: EngineStatus | null, doc: DocState | null): FaceState | null =>
  st?.face?.face ?? doc?.face ?? null;

/** 人脸名单的命令（LNX-PORTRAIT-003 选定 / LNX-PORTRAIT-006 人工账）。
 *
 * 动作名单由引擎 ready 报（`face_actions`）：这里写联合类型只是为了编译期挡住拼错，
 * 运行时能不能收仍以引擎为准——面板上一格按钮在引擎没有对应动作时必须显式禁用，
 * 不许发一条指望引擎"大概能懂"的命令。
 * rect 只在 `add` 上有意义：那是用户框出来的归一化区域，引擎在这一框上**再跑一次真检测**
 * 拿 478 点（不拿框拟合一套占位点位，那是 DoD §2 严禁的假 AI）。 */
export type FaceAction = "list" | "select" | "disable" | "enable" | "add" | "remove";

export const runFace = (action: FaceAction, index?: number, rect?: number[], peopleContext?: PeopleContext) =>
  invoke<{ requested: boolean }>("face", { action, index, rect, peopleContext });

/** 影楼色彩（M3-a2）：送一张 .cube，或只改混合系数。
 *
 * path 与 text 二选一（同时给会被引擎整条拒：拿到哪张都是“对的那张的错版本”）。
 * 强度滑块松手才发：它不重挂体积，但每条命令都要引擎重画一帧，逐事件发会吞掉
 * vsync 余量（与修容强度同一条理由）。而形变那一条相反：它必须拖动期间逐事件发。
 */
export const runLut = (
  action: LutInfo["action"],
  opts?: { path?: string; text?: string; preset?: string; amount?: number },
) =>
  invoke<{ requested: boolean }>("lut", {
    action,
    path: opts?.path,
    text: opts?.text,
    preset: opts?.preset,
    amount: opts?.amount,
  });

/** 眼牙局部增强（LNX-PORTRAIT-009）：三个子功能各自独立启停。
 *
 * set 是部分提交：只给一个子功能时另两个沿用当前值（拖一个滑块不该把另外两个抹零，
 * 与定向层同一条语义）。拖动期间逐事件发：这一层每帧只在自己那只窗口里逐点乘加
 * （实测 enhance_ms 在产品档上是零点几毫秒），不发就是"滑块拖了、画面不动"。
 * 越界与不认识的子功能整条拒，拒完状态干净——UI 不必先夹再发。
 */
export const runEnhance = (
  action: EnhanceInfo["action"],
  opts?: { sclera?: number; iris?: number; teeth?: number; dark_circles?: number; eye_bags?: number; veins?: number; catchlight_left?: number; catchlight_right?: number } & Partial<Record<WrinkleKey, number>>,
  peopleContext?: PeopleContext,
) =>
  invoke<{ requested: boolean }>("enhance", {
    action,
    darkCircles: opts?.dark_circles,
    eyeBags: opts?.eye_bags,
    veins: opts?.veins,
    catchlightLeft: opts?.catchlight_left,
    catchlightRight: opts?.catchlight_right,
    wrinkles: wrinkleTransport(opts),
    peopleContext,
    sclera: opts?.sclera,
    iris: opts?.iris,
    teeth: opts?.teeth,
  });

/** 眼牙层现状：与 faceStateOf 同一类"两个来源汇成一份"（重开工程那一刻 image_ready
 *  先带着"还没分析"的账出来，几百毫秒后自动补的那次分析才把场重画回来）。 */
export const enhanceStateOf = (
  st: EngineStatus | null, doc: DocState | null,
): EnhanceDoc | null => {
  const ev = st?.enhance;
  if (ev) {
    // 事件那份的平铺 reason 是整层一句话，面板要的逐格原因在 enhance_reason 里：
    // 不在这里换下来，`reason[sub]` 就是在字符串上取下标，恒 undefined——于是
    // "闭嘴样本的牙齿那一格为什么不动"这句在屏幕上永远显示不出来（而 DoD §3 要的
    // 正是"禁用必须带原因"）。其余字段两形同名同值，直接摊平用。
    return { ...ev, reason: ev.enhance_reason ?? undefined, facial_wrinkles: ev.enhance_facial_wrinkles };
  }
  return doc?.enhance ?? null;
};

/** 肤色定向（M3-b）：三个增量 + 一个混入比例。
 *
 * set 是部分提交：没给的增量沿用当前值（拖一个滑块不该把另外两个抹零）。
 * 拖动期间逐事件发：这一层每帧真跑内核（产品档实测 1.3 ms/帧），不发就是
 * “滑块拖了、画面不动”。越界值整条拒，拒完状态干净，UI 不必先夹再发。
 */
export const runGrade = (
  action: GradeInfo["action"],
  opts?: { dh?: number; ds?: number; dv?: number; amount?: number;
           scope?: string; rle?: number[][]; feather?: number; mode?: string },
) =>
  invoke<{ requested: boolean }>("grade", {
    action,
    dh: opts?.dh,
    ds: opts?.ds,
    dv: opts?.dv,
    amount: opts?.amount,
    // COLOR-004：作用域与区域走同一条命令。“给了才附”在 Rust 那一侧把关，
    // 这里不替引擎填默认值（写了 scope: "all" 就等于把用户刚选的局部作用域抹掉）。
    scope: opts?.scope,
    rle: opts?.rle,
    feather: opts?.feather,
    mode: opts?.mode,
  });

/** 换底（M6）：一次“换底”一条命令。action=set 需 bg（[r,g,b] 0–255）；clear 关掉整层。
 *  backend 默认 color_key（确定性色键）；birefnet 需权重，无权重引擎会诚实拒。返回只是
 *  “请求递出去了”，真正的合成结果从 engine_status().background 轮询（与 inpaint/light 同路）。 */
export const runBackground = (
  action: BackgroundInfo["action"],
  opts?: { backend?: string; bg?: number[]; tol?: number; softness?: number },
) =>
  invoke<{ requested: boolean }>("background", {
    action,
    backend: opts?.backend,
    bg: opts?.bg,
    tol: opts?.tol,
    softness: opts?.softness,
  });

/** 全尺寸分块导出（M4）。不传 images 就是导当前这张。
 *
 * 这里的返回只是“请求递出去了”：满幅一块图就能是几秒，真正的结果从
 * export_progress / export_done 两条事件拿（engine_status 轮询）。
 * format/tile 不抄默认值：那两个数的出处是引擎的 ready（export_formats /
 * export_tile），宿主填一份就会在引擎改口径时静默漂开。
 *
 * scale/sharpen 同理（M7）：不给就是不上这一层。后端只能从 ready 报的 baseline 里选，
 * 拿 weights_gated 那一个去提交会被引擎整条拒（这是设计，不是降级）。
 */
export const runExport = (
  outDir: string,
  opts?: { format?: string; quality?: number; tile?: number; images?: string[];
           scale?: number; sharpen?: number; upscaleBackend?: string;
           bitDepth?: number; outputProfile?: string; tiffCompression?: string;
           metadataIncludeGps?: boolean; conflictPolicy?: string; watermark?: WatermarkSettings; layout?: import("./layout/model").LayoutSpec },
) =>
  invoke<{ requested: boolean }>("export", {
    outDir,
    format: opts?.format,
    quality: opts?.quality,
    tile: opts?.tile,
    images: opts?.images,
    scale: opts?.scale,
    sharpen: opts?.sharpen,
    upscaleBackend: opts?.upscaleBackend,
    bitDepth: opts?.bitDepth,
    // 导出侧 P0 的四格：中性位由引擎定（ADR-0003），这里只在用户显式改过才传。
    // 键同样必须是 camelCase：写成 snake_case 就是“勾了 16-bit TIFF / 关了 GPS /
    // 选了不覆盖，而引擎全按默认跑”——落盘的文件看起来完全正常。
    outputProfile: opts?.outputProfile,
    tiffCompression: opts?.tiffCompression,
    metadataIncludeGps: opts?.metadataIncludeGps,
    conflictPolicy: opts?.conflictPolicy,
    watermark: opts?.watermark,
    layout: opts?.layout,
  });

export {parseFrameHead,type ParsedFrame} from './previewFrame';

export const isNoFrame = (e: unknown) => {
  const s = String(e);
  return s.includes("NO_NEW_FRAME") || s.includes("NO_FRAME_YET") || s.includes("SHM_NOT_READY") || s.includes("SHM_CHANGED");
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
  no_mirror: string;
  gl_visible: string;
  /** 视口自证探针（M9）：非空时在静置后读回画布缓冲并量布局矩形，报 M0_VIEWPORT。 */
  viewport_probe: string;
  dirty_frac: number;
  /** 非空则跑靶前先导入这张图（M1-3a 真图通路）。 */
  load_image: string;
  max_px: number | null;
  /** 非空且不为 "0" 则导入后跑一次预计算，值就是后端名（M1-3b）。 */
  precompute: string;
  precompute_channel: string;
  /** 非空则导入后自动打几笔消除笔（M1-4）："fx:fy:r,…"。fx/fy 是代理帧归一化坐标，
   *  r 是**像素**半径（clickRle 直接吃它）——上一版注释只说"坐标归一化"，我按 0.15
   *  传过比例，结果只盖了 25 像素、第三笔 RLE 越界被引擎拒绝，白跑一轮确认。 */
  auto_inpaint: string;
  /** 非空则导入后提交一次三条带增益（M2-a）："mid:broad:detail"。 */
  auto_skin: string;
  /** 非空则导入后画几笔修容（M2-a2）："fx:fy:r:sign,…"，fx/fy 归一化、r 是**像素**、sign 取 1/-1。 */
  auto_light: string;
  /** 非空则导入后提交一次形变（M2-b）："slim:eye:chin"，三个都是 [-1,1] 的滑块值。
   *  需要 LRT_PRECOMPUTE 给出关键点（synthetic 后端会被引擎整条拒）。 */
  auto_deform: string;
  /** 非空则导入后载入一张表（M3-a2）："amount@<路径>"，也支持 "amount@preset:<名>"
   *  （M3-b：预设一条命令同时上表与肤色定向，所以这一条能把两层都验到）。路径里出现 @
   *  不冲突：只按**第一个** @ 切分，因为前半段是个数字。 */
  auto_lut: string;
  /** 非空则导入后提交一次肤色定向（M3-b）："dh:ds:dv:amount"，四个数用 : 分隔。
   *  与 lut 的 @ 分法各走一份，两条自动臂可以同时挂。 */
  auto_grade: string;
  /** 局部调色（COLOR-004）自动通道（$LRT_AUTO_LOCAL_COLOR）："fx:fy:r:dh:ds:dv"。
   *  fx/fy 是代理帧归一化坐标、r 是像素半径（与修容同一套坐标口径），后三个是定向增量。
   *  这一条要证的是三层签名对得上 + 区域外逐字节不动（后者只能拿用户看见那一帧量）。 */
  auto_local_color: string;
  /** 分人编辑（LNX-PORTRAIT-003）自动通道（$LRT_AUTO_FACE）：<要选的 index>。真窗口要证的
   *  是 runFace → Rust face → 引擎 face_selected → status.face 这四层签名，外加两句话：
   *  未选定时整条拒而画面一格没动、选定之后没被选中的那一圈逐字节没动。 */
  /** 眼牙增强（LNX-PORTRAIT-009）自动通道（$LRT_AUTO_ENHANCE）："sclera:iris:teeth"，
   *  三个 [0,1]。这一条要证的是四层签名 + 窗口外逐字节不动 + clear 后回出厂帧——后两条
   *  只能拿用户看见的那一帧量，屏上没有第二块画布可比。 */
  auto_enhance: string;
  auto_face: string;
  /** 人工纠正优先（$LRT_AUTO_MANUAL=<要关掉的 index>）：见 App.tsx 第 9 臂 */
  auto_manual: string;
  /** 1.12 规格工作台（$LRT_AUTO_SPEC=<JSON>）：100% 视口 + 曝光/影调 + 八色 HSL +
   *  磨皮 + 瘦脸 + 裁剪旋转。它与上面几条同一条纪律：只有真窗口能证明宿主桥把参数
   *  原样递到了引擎，而屏幕真的按它动了。 */
  auto_spec: string;
  /** 取证臂：跑完自动序列后不退出，留给截图（默认空=照旧退出）。 */
  keep_open: string;
  /** 系统文件拖入（$LRT_AUTO_DROP=1）：见 App.tsx 第 10 臂——监听挂上了吗，
   *  以及"能不能开"那份判断在装机壳里用的是不是引擎报的名单 */
  auto_drop: string;
  /** 空状态自证（1.10.0）：没有图时跑一臂，报卡片与顶栏入口。 */
  auto_empty: string;
  /** M6 换底自动通道（$LRT_AUTO_BG）："rrggbb:tol:softness"。真窗口要证的不是
   *  合成对不对（test_matting 已钉），而是 TS runBackground → Rust background →
   *  引擎 bg_done 这条命令签名在真窗口里对得上，且画面真的变了（peek 字节差）。 */
  auto_background: string;
  /** M4 导出自动通道："<目录>[@<格式>][@<tile>]"。 */
  auto_export: string;
  /** M5-a 底片条自动通道："<目录>[@<切到第几张>[@<长边>]]"。
   *  这一条要证的不是引擎能扫描（那是 test_session 的事），而是
   *  TS runSession → Rust session → 引擎 session_state 这条签名在真窗口里对得上，
   *  以及切走再切回来时 doc_state 与画面是否还是同一份。 */
  auto_filmstrip: string;
  /** M5-b 撤销/重做自动通道：<强度值>。引擎那条链已有协议用例逐字节对拍，这一条要证
   *  的是宿主三层：runHistory → Rust history → history_state 的签名对不对得上，
   *  以及宿主有没有真按引擎那份 doc_state 重摆滑块（applied 里那一份是唯一直接证据）。 */
  auto_history: string;
  /** 发布自检（M5-c 开箱即用）：非空（一般给 1）则报一条 M0_RELEASE，把“引擎跑在
   *  哪个解释器、从哪一档候选里来、版本与包账单、能力到没到”一次打全。这些信息
   *  平时分散在侧栏的四行小字里，脚本读不到而人也不会一行一行去比对。 */
  auto_release: string;
  /** 挑图建议（LNX-PICK-001）自动通道（$LRT_AUTO_PICK）："<重复>/<清晰>/<曝光>/<眼睛>"
   *  四档名，例如 standard/standard/standard/strong。引擎那半已有端到端用例逐条钉判据，
   *  这一条要证的是宿主四层签名（runPick → Rust pick → 引擎 pick_* → status.pick）再加上
   *  用户看得见的那一层：徽章真在 DOM 里、原因里带着数值与阈值、没有一处说"删"。 */
  auto_pick: string;
}
export const m0Env = () => invoke<M0Env>("m0_env");

/** 底片条（M5-a）：一条转发六个动作的命令。参数一律"给了才附"，让引擎的默认值
 *  由引擎说（与 runExport 同一条理由）。 */
export const runSession = (
  action: "scan" | "add" | "select" | "state" | "thumbs" | "stop_thumbs",
  opts: { dir?: string; paths?: string[]; index?: number; edge?: number;
          quality?: number; limit?: number; thumbs?: boolean } = {},
) => invoke<{ requested: boolean }>("session", { action, ...opts });

/** 挑图建议（LNX-PICK-001）：一条命令转发 analyze/stop/state。
 *  动作与档位名单来自引擎 ready（`pick_actions` / `pick_sensitivities`），宿主与前端
 *  都不抄一份：抄了就是双出处，加一档时先漂的那一处永远是抄的那一份。
 *  参数一律"给了才附"，默认档位由引擎说。 */
export const runPick = (
  action: "analyze" | "stop" | "state",
  opts: { indices?: number[]; paths?: string[]; edge?: number; model_dir?: string;
          duplicate?: string; blur?: string; exposure?: string; eyes?: string;
          force?: boolean } = {},
) => invoke<{ requested: boolean }>("pick", { action, ...opts });

/** 撤销/重做（M5-b）：四个动作一条命令，宿主只做把手。步数上限、手势合并窗口、
 *  哪几层进历史全在引擎里——在这里刻一份就会漂一份。 */
export const runHistory = (action: "undo" | "redo" | "state" | "clear") =>
  invoke<{ requested: boolean }>("history", { action });

/** 整条底片条：格子元信息 + 缩略图。只在 session_rev 变了的时候取。 */
export const fetchFilmstrip = () => invoke<Filmstrip>("filmstrip");

/** 工程（LNX-P0-PROJECT）：六个动作一条命令。原子写、脏标记、资产去重全在引擎。 */
export const runProject = (
  action: "create" | "open" | "save" | "state" | "tag" | "trash",
  opts: { name?: string; directory?: string; path?: string; doc?: string; index?: number;
          tags?: string[]; label?: string; trashed?: boolean; force?: boolean } = {},
) => invoke<{ requested: boolean }>("project", { action, ...opts });

/** 批量任务队列（LNX-P0-TASK）：转移表在引擎里，这里只把 id 递过去。 */
export const runTask = (
  action: "list" | "pause" | "resume" | "cancel" | "retry" | "delete",
  taskId?: string,
) => invoke<{ requested: boolean }>("task", { action, task: taskId });

/** 模块预设（LNX-P0-PRESET / PRESET-001、002）：作用域与合法性全在引擎的 scope.py，
 *  这里既不列模块名单也不写量程（与 exposure/crop 同一条理由：抄一份就漂一份）。 */
export const runPreset = (
  action: "list" | "preflight" | "apply" | "save" | "import" | "delete",
  opts: { id?: string; name?: string; path?: string; kind?: string; note?: string;
          force?: boolean; moduleScope?: string[]; requestId?: string; documentId?: string;localMaskTransfer?:MaskTransferOptions;referenceColor?:{strength:number};preflightToken?:string } = {},
) => invoke<{ requested: boolean }>("preset", {
  action, id: opts.id, name: opts.name, path: opts.path, kind: opts.kind, note: opts.note,
  force: opts.force, moduleScope: opts.moduleScope, requestId: opts.requestId, documentId: opts.documentId,localMaskTransfer:opts.localMaskTransfer,referenceColor:opts.referenceColor,preflightToken:opts.preflightToken,
});
export const readPresetResult=(requestId:string)=>invoke<{phase:string;request_id:string;result?:PresetReply;error?:string}>("preset_result",{requestId});

/** 批量同步（LNX-P0-BATCH / BATCH-004）：目标按 path 递（多选集就是按 path 记的），
 *  preflight/commit/undo 的判定与原子性全在引擎。 */
export const runBatch = (
  action: "preflight" | "commit" | "undo" | "redo" | "state",
  opts: { docs?: string[]; moduleScope?: string[]; conflictPolicy?: string;
          batchId?: string; preflightToken?:string;requestId?:string;localMaskTransfer?:MaskTransferOptions;referenceColor?:{strength:number};peopleTransfer?:PeopleTransferRequest } = {},
) => invoke<{ requested: boolean }>("batch", {
  action, docs: opts.docs, moduleScope: opts.moduleScope,
  conflictPolicy: opts.conflictPolicy, batchId: opts.batchId,preflightToken:opts.preflightToken,requestId:opts.requestId,localMaskTransfer:opts.localMaskTransfer,referenceColor:opts.referenceColor,peopleTransfer:opts.peopleTransfer,
});
export const readBatchResult=(requestId:string)=>invoke<{phase:string;request_id:string;result?:BatchReply;error?:string}>("batch_result",{requestId});

/** 曝光/白平衡（P0）：量程由引擎随事件报 exposure_limits，这里不抄一份。 */
export const runExposure = (
  action: "set" | "clear",
  v: { ev?: number; temperature_shift?: number; tint_shift?: number;
       reference_k?: number; contrast?: number; highlights?: number;
       shadows?: number; saturation?: number } = {},
  interactive = false,
) =>
  // Tauri 的命令参数在 JS 侧是 **camelCase**（Rust 的 temperature_shift 对应
  // temperatureShift）。上一版这里原样展开了 snake_case 的键：Tauri 把不认识的键
  // 当“没给”，于是色温/色调/参考白/四项影调全是“拖了滑块而引擎一个数没收到”，
  // 而回执一切正常。这条不是风格问题，是七个参数里四个静默丢失。
  invoke<{ requested: boolean }>("exposure", {
    action,
    ev: v.ev,
    temperatureShift: v.temperature_shift,
    tintShift: v.tint_shift,
    referenceK: v.reference_k,
    contrast: v.contrast,
    highlights: v.highlights,
    shadows: v.shadows,
    saturation: v.saturation,
    interactive,
  });

/** 八色 HSL：band 0…7（红/橙/黄/绿/青/蓝/紫/洋红），dh/ds/dl 为这一段的三个量。
 *  `clear` 整层归零；部分提交语义在引擎（拖一个滑块不抹掉同段另外两个）。 */
export const runHsl = (
  action: "set" | "clear",
  band?: number,
  v: { dh?: number; ds?: number; dl?: number } = {},
  interactive = false,
) => invoke<{ requested: boolean }>("hsl", { action, band, ...v, interactive });

/** 裁剪/旋转（P0 lnx.crop.v1）：rect 归一化，正角顺时针——口径在引擎 ops/geometry.py。 */
export const runCrop = (
  action: "set" | "clear", rect?: number[], rotationDegrees?: number,
) => invoke<{ requested: boolean }>("crop", {
  action, rect, rotationDegrees,
});
export const report = (line: string) => invoke("report", { line });
export const quit = () => invoke("quit");

/** Full-source patches use their own identity-bearing transport, never proxy SHM. */
export const inspectionStatus = () => invoke<import('./inspectionController').InspectionStatus>('inspection_status');
export const inspectionStart = (intent:import('./inspectionController').InspectionIntent,status:import('./inspectionController').InspectionStatus) =>
  invoke<import('./inspectionController').InspectionAccepted>('inspection_start',{
    engineEpoch:status.epoch,generation:status.generation,canvasWidth:intent.canvasWidth,canvasHeight:intent.canvasHeight,...intent.roi,
  });
export const inspectionPull = (engineEpoch:string,requestId:string) => invoke<ArrayBuffer>('inspection_pull',{engineEpoch,requestId});
export const inspectionCancel = (engineEpoch:string,requestId:string) => invoke<{requested:boolean}>('inspection_cancel',{engineEpoch,requestId});
export const inspectionRelease = (engineEpoch:string,requestId:string) => invoke<{released:boolean}>('inspection_release',{engineEpoch,requestId});
export const inspectionApi = {status:inspectionStatus,start:inspectionStart,pull:inspectionPull,cancel:inspectionCancel,release:inspectionRelease};

export const runLevels=(action:'set'|'clear',spec:LevelsSpec|undefined,documentId:string,
  gestureId?:string,interactive=false,requestId?:string)=>invoke<{requested:boolean}>('levels',
    {action,spec,documentId,gestureId,interactive,requestId});

/** Enqueue only; authoritative fabric value arrives through document state. */
export const runFabric=(amount:number,documentId:string)=>invoke<{requested:boolean}>("fabric",{action:amount===0?"clear":"set",amount,documentId});

/** Accepted edits update doc_state only after the engine rendered the recipe. */
export const runLipMakeup=(recipe:import("./lipMakeup/model").LipMakeup,documentId:string,control:import("./lipMakeup/model").LipKey|"all"="all",peopleContext?:PeopleContext)=>
  invoke<{requested:boolean}>("lip_makeup",{recipe,documentId,control,peopleContext});

type BrowRequest={people_context?:PeopleContext;action:'edit';request_id:string;gesture_id:string;document_id:string;face_id:string;control:string;recipe:import('./browShape/model').BrowShape;base:import('./browShape/model').BrowShape};
export function runBrowShapeRequest(request:{action:'status';request_id:string}):Promise<import('./browShape/latestIntent').Mailbox<import('./browShape/model').BrowShape>>;
export function runBrowShapeRequest(request:BrowRequest):Promise<{requested:boolean}>;
export function runBrowShapeRequest(request:BrowRequest|{action:'status';request_id:string}){
  // Receipt lookups are read-only and must not invalidate editing captures.
  return request.action==='status'?tauriInvoke<import('./browShape/latestIntent').Mailbox<import('./browShape/model').BrowShape>>("brow_shape",{request}):invoke<{requested:boolean}>("brow_shape",{request});
}

type NoseRequest={people_context?:PeopleContext;action:'edit';request_id:string;gesture_id:string;document_id:string;face_id:string;control:string;recipe:import('./noseShape/model').NoseShape;base:import('./noseShape/model').NoseShape};
export function runNoseShapeRequest(request:{action:'status';request_id:string}):Promise<import('./browShape/latestIntent').Mailbox<import('./noseShape/model').NoseShape>>;
export function runNoseShapeRequest(request:NoseRequest):Promise<{requested:boolean}>;
export function runNoseShapeRequest(request:NoseRequest|{action:'status';request_id:string}){
  // Receipt lookups are read-only and must not invalidate editing captures.
  return request.action==='status'?tauriInvoke<import('./browShape/latestIntent').Mailbox<import('./noseShape/model').NoseShape>>("nose_shape",{request}):invoke<{requested:boolean}>("nose_shape",{request});
}

type EyeRequest={people_context?:PeopleContext;action:'edit';request_id:string;gesture_id:string;document_id:string;face_id:string;control:string;recipe:import('./eyeShape/model').EyeShape;base:import('./eyeShape/model').EyeShape};
export function runEyeShapeRequest(request:{action:'status';request_id:string}):Promise<import('./browShape/latestIntent').Mailbox<import('./eyeShape/model').EyeShape>>;
export function runEyeShapeRequest(request:EyeRequest):Promise<{requested:boolean}>;
export function runEyeShapeRequest(request:EyeRequest|{action:'status';request_id:string}){
  // Receipt lookups are read-only and must not invalidate editing captures.
  return request.action==='status'?tauriInvoke<import('./browShape/latestIntent').Mailbox<import('./eyeShape/model').EyeShape>>("eye_shape",{request}):invoke<{requested:boolean}>("eye_shape",{request});
}

type MouthRequest={people_context?:PeopleContext;action:'edit';request_id:string;gesture_id:string;document_id:string;face_id:string;control:string;recipe:import('./mouthShape/model').MouthShape;base:import('./mouthShape/model').MouthShape};
export function runMouthShapeRequest(request:{action:'status';request_id:string}):Promise<import('./browShape/latestIntent').Mailbox<import('./mouthShape/model').MouthShape>>;
export function runMouthShapeRequest(request:MouthRequest):Promise<{requested:boolean}>;
export function runMouthShapeRequest(request:MouthRequest|{action:'status';request_id:string}){
  // Receipt lookups are read-only and must not invalidate editing captures.
  return request.action==='status'?tauriInvoke<import('./browShape/latestIntent').Mailbox<import('./mouthShape/model').MouthShape>>("mouth_shape",{request}):invoke<{requested:boolean}>("mouth_shape",{request});
}

/** Commands carry exact engine binding; status lookups never mutate captures. */
export function runPeopleRequest(request: {action: 'status'; request_id: string}): Promise<PeopleMailbox>;
export function runPeopleRequest(request: PeopleAction): Promise<{requested: boolean}>;
export function runPeopleRequest(request: PeopleAction | {action: 'status'; request_id: string}) {
  return request.action === 'status' ? tauriInvoke<PeopleMailbox>('people', {request})
    : invoke<{requested: boolean}>('people', {request});
}

/** Shoulder control and model receipts are read-only; edits retain normal capture fences. */
export function runShoulderShape(request:import('./shoulderShape/nativePort').Command|{action:'mailbox_status'|'release';request_id:string}):Promise<import('./shoulderShape/nativePort').Mailbox>{
  return ['view','install','status','mailbox_status','release'].includes(request.action)
    ? tauriInvoke<import('./shoulderShape/nativePort').Mailbox>('shoulder_shape',{request}) : invoke<import('./shoulderShape/nativePort').Mailbox>('shoulder_shape',{request});
}

export const runBodyPoseModel=(action:'install'|'cancel',requestId:string)=>tauriInvoke<import('./shoulderShape/useShoulderModel').ModelTask>('body_pose_model',{action,requestId});
export const bodyPoseModelStatus=()=>tauriInvoke<import('./shoulderShape/useShoulderModel').ModelTask>('body_pose_model_status');

/** Read-only leg receipts bypass edit/capture fences; mutations never do. */
export function runLegShape(request:import('./legShape/nativeTransport').Command|{action:'mailbox_status'|'release';request_id:string}):Promise<import('./legShape/nativeTransport').Mailbox>{
  return ['view','status','mailbox_status','release'].includes(request.action)
    ? tauriInvoke<import('./legShape/nativeTransport').Mailbox>('leg_shape',{request}) : invoke<import('./legShape/nativeTransport').Mailbox>('leg_shape',{request});
}

export function runWaistShape(request:import('./waistShape/nativeTransport').Command|{action:'mailbox_status'|'release';request_id:string}):Promise<import('./waistShape/nativeTransport').Mailbox>{
  return ['view','status','mailbox_status','release'].includes(request.action)
    ? tauriInvoke<import('./waistShape/nativeTransport').Mailbox>('waist_shape',{request}) : invoke<import('./waistShape/nativeTransport').Mailbox>('waist_shape',{request});
}

/** One arm mailbox; reads and proposal receipts never invalidate editing captures. */
export function runArmShape(request:import('./armShape/nativeTransport').Command|{action:'mailbox_status'|'release';request_id:string}):Promise<import('./armShape/nativeTransport').Mailbox>{
  return ['view','status','proposal_start','proposal_status','proposal_cancel','mailbox_status','release'].includes(request.action)
    ? tauriInvoke<import('./armShape/nativeTransport').Mailbox>('arm_shape',{request}) : invoke<import('./armShape/nativeTransport').Mailbox>('arm_shape',{request});
}

export function runLegLength(request:import('./legLength/nativeTransport').Command|{action:'mailbox_status'|'release';request_id:string}):Promise<import('./legLength/nativeTransport').Mailbox>{
  return ['view','status','mailbox_status','release'].includes(request.action)
    ? tauriInvoke<import('./legLength/nativeTransport').Mailbox>('leg_length',{request}) : invoke<import('./legLength/nativeTransport').Mailbox>('leg_length',{request});
}

export function runNeckShape(request:import('./neckShape/nativeTransport').Command|{action:'mailbox_status'|'release';request_id:string}):Promise<import('./neckShape/nativeTransport').Mailbox>{
  return ['view','status','mailbox_status','release'].includes(request.action)
    ? tauriInvoke<import('./neckShape/nativeTransport').Mailbox>('neck_shape',{request}) : invoke<import('./neckShape/nativeTransport').Mailbox>('neck_shape',{request});
}
