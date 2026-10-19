/**
 * P0 参数注册表的消费层（《P0参数注册表.json》冻结的那 36 条）。
 *
 * 为什么单独一层，而不是在面板里直接写控件：手册与验收用例判的是"注册表里每一格
 * 都得在 UI 上有对应控件，接不通的必须显式禁用并说明原因"。控件手写清单就会与注册表
 * 漂开——漂的形状是"某一格在界面上根本不存在"，而那正是 DoD 里"绝不留无响应控件"
 * 的反面（不存在比不响应更难发现）。
 *
 * 这一层的三条硬规则：
 * ① 面板遍历的是 **注册表**（WIRING 只是给每一格补上展示名与绑定），不在 WIRING 里
 *    的条目照样渲染，并且落成"未接通 + 未登记"——漏登记当场可见，而不是静默消失；
 * ② `wired: false` 必须带 `why_not`，而且 why 是真话（缺哪条通路/为什么不做），
 *    不写"暂未实现"这种没人能复查的话；
 * ③ 量程、中性值、枚举一律取自注册表那一份，宿主与引擎都不在这里再刻一份。
 */
import raw from "./p0-registry.json";
import { lang } from "./i18n";

export type Scope = "image" | "single_face" | "preview" | "export_job"
  | "selected_assets" | "project_or_selection";

export interface P0Range { min: number | null; max: number | null; step: number | null }

export interface P0Entry {
  requirement_id: string;
  operation_id: string;
  parameter_key: string;
  type: string;
  unit: string | null;
  neutral: unknown;
  range: P0Range | null;
  enum: string[] | null;
  target_scope: Scope[];
  enable_condition: string;
  reason: string;
}

export interface P0Registry {
  schema_version: string;
  derived_from: string;
  source_sha256: string;
  entries: P0Entry[];
  scope_single_face: { decision: string; rule: string; usable_face_criteria: string };
  quality_thresholds: Record<string, unknown>;
}

export const REGISTRY = raw as unknown as P0Registry;
export const ENTRIES = REGISTRY.entries;
export const keyOf = (e: { operation_id: string; parameter_key: string }) =>
  `${e.operation_id}.${e.parameter_key}`;

/** 面板分栏（手册的工作区规划：右侧精修面板按功能分栏）。 */
export type SectionId = "skin" | "face" | "tone" | "local" | "crop" | "output";

export interface Binding {
  /** 展示名（双语，按 i18n 当前语言取） */
  label: [zh: string, en: string];
  section: SectionId;
  /** 控件形态：滑杆 / 开关 / 下拉 / 按钮 / 裁剪框 / 资产选择 */
  kind: "slider" | "toggle" | "enum" | "action" | "rect" | "asset";
  /** 接不通时为 true；必须同时给 why_not（界面上直接显示，不弹窗不隐藏） */
  blocked?: boolean;
  why_not?: [zh: string, en: string];
  /** 值从引擎状态哪一格读（面板不许自己记一份当前值） */
  read?: string;
}

/**
 * 36 条冻结项的绑定表。key 用 `operation_id.parameter_key`。
 * 这里只写"这一格接的是哪条命令、界面上叫什么、读哪一格状态"——
 * 真正的参数校验与默认值全在引擎，这一层不重复判。
 */
export const WIRING: Record<string, Binding> = {
  // ── 质感与磨皮（高低频） ──────────────────────────────────────────────
  "lnx.skin.v1.enabled": {
    label: ["磨皮启用", "Skin retouch on"], section: "skin", kind: "toggle",
    read: "strength>0",
  },
  "lnx.skin.v1.strength": {
    label: ["磨皮强度", "Skin strength"], section: "skin", kind: "slider",
    read: "strength",
  },
  // ── 局部修正（消除笔/修痕） ───────────────────────────────────────────
  "lnx.blemish.v1.enabled": {
    label: ["局部修正画笔", "Blemish brush on"], section: "local", kind: "toggle",
    read: "counts.repair>0",
  },
  "lnx.blemish.v1.strength": {
    label: ["局部修正强度", "Blemish strength"], section: "local", kind: "slider",
    blocked: true,
    why_not: ["本实现的局部修正是「笔迹」：落在你画过的位置，按消除/减淡/加深三种模式作用，"
      + "没有一条会被强度缩放的通道。加一根不作用到像素上的滑杆就是假控件。",
      "This implementation works in strokes (heal / dodge / burn at the painted place); "
      + "there is no strength-scaled path. A slider that touches no pixels would be a fake control."],
  },
  "lnx.blemish.v1.protect_identity_marks": {
    label: ["保护标志性细节（痣/疤）", "Protect identity marks"], section: "local",
    kind: "toggle", blocked: true,
    why_not: ["引擎不自动识别痣与疤痕，因此也没有「保护」这个开关可依：画笔落在哪里由"
      + "你决定，没画过的地方逐字节不动（这条由 P0-BRUSH-BOUNDARY 用例钉着）。"
      + "做一个会自动挑「哪些算痣」的开关，就是本仓禁止的伪装 AI。",
      "The engine does not detect moles or scars, so there is nothing for a protect switch to "
      + "gated on: untouched pixels stay byte-identical (pinned by P0-BRUSH-BOUNDARY). "
      + "An auto «which marks count» toggle would be the disguised-AI this repo forbids."],
  },
  // ── 遮罩（面部分析） ─────────────────────────────────────────────────
  "lnx.mask.v1.analysis_enabled": {
    label: ["面部分析（关键点与掩膜）", "Face analysis"], section: "face", kind: "toggle",
    read: "precompute.ok",
  },
  "lnx.mask.v1.overlay_visible": {
    label: ["遮罩叠加显示", "Show mask overlay"], section: "face", kind: "toggle",
    blocked: true,
    why_not: ["帧通路只送 RGB，没有把掩膜送到显示层的那一条视口通道；做它需要新增一条"
      + "「掩膜伪彩」帧模式。本轮未接，因此这里显式禁用而不是留一个点了没反应的开关。",
      "The frame channel carries RGB only; there is no viewport path for the matte. Enabling it "
      + "needs a new mask-preview frame mode, which this round does not ship."],
  },
  "lnx.mask.v1.feather": {
    label: ["遮罩边缘羽化", "Mask edge feather"], section: "face", kind: "slider",
    blocked: true,
    why_not: ["注册表这一格是语义遮罩（single_face）的边缘羽化，量程 0~256 代理像素；"
      + "本实现的遮罩羽化长在画笔那一层（笔刷羽化 0~8，见“局部修容与画笔”栏），而没有"
      + "“把磨皮遮罩边缘外扩 N 像素”这一层。把它们当同一格会拿 0~256 去撞一个 0~8 的引擎参数。",
      "This cell is the semantic skin mask's edge feather (0~256 px). This build feathers the "
      + "brush matte (0~8) and has no mask-edge dilation layer, so binding them together would "
      + "push a 0~256 value into a 0~8 engine parameter."],
  },
  // ── 曝光与白平衡 ────────────────────────────────────────────────────
  "lnx.exposure.v1.ev": {
    label: ["曝光（EV）", "Exposure (EV)"], section: "tone", kind: "slider",
    read: "exposure.ev",
  },
  "lnx.white_balance.v1.temperature_shift": {
    label: ["色温偏移", "Temperature shift"], section: "tone", kind: "slider",
    read: "exposure.temperature_shift",
  },
  "lnx.white_balance.v1.tint_shift": {
    label: ["色调偏移（绿↔品）", "Tint shift"], section: "tone", kind: "slider",
    read: "exposure.tint_shift",
  },
  // ── 裁剪 / 旋转 ─────────────────────────────────────────────────────
  "lnx.crop.v1.rect_normalized": {
    label: ["裁剪框（左,上,右,下 归一化）", "Crop rect (L,T,R,B normalized)"],
    section: "crop", kind: "rect", read: "crop.rect",
  },
  "lnx.crop.v1.rotation_degrees": {
    label: ["旋转角度（正为顺时针）", "Rotation (positive = clockwise)"],
    section: "crop", kind: "slider", read: "crop.rotation_degrees",
  },
  // ── 导出 ────────────────────────────────────────────────────────────
  "lnx.export.v1.format": {
    label: ["导出格式", "Export format"], section: "output", kind: "enum",
  },
  "lnx.export.v1.jpeg_quality": {
    label: ["JPEG 质量", "JPEG quality"], section: "output", kind: "slider",
  },
  "lnx.export.v1.tiff_compression": {
    label: ["TIFF 压缩", "TIFF compression"], section: "output", kind: "enum",
  },
  "lnx.export.v1.output_profile": {
    label: ["输出色彩档", "Output ICC profile"], section: "output", kind: "asset",
    blocked: true,
    why_not: ["srgb 与 source 两条是通的（已接进导出）；AdobeRGB / Display-P3 需要一个真实的"
      + " .icc 文件路径才能嵌——本版本不烘一份「名字对、内容靠猜」的档，界面上也不给"
      + "一个点了就写错 profile 的下拉项。递路径的入口在导出参数里。",
      "srgb and source are wired. AdobeRGB / Display-P3 need a real .icc file; this build refuses "
      + "to bake a guessed table, so those two enum values stay disabled."],
  },
  "lnx.export.v1.metadata_include_gps": {
    label: ["导出带 GPS（默认不带）", "Include GPS (default off)"],
    section: "output", kind: "toggle",
  },
  "lnx.export.v1.start": {
    label: ["开始批量导出", "Start batch export"], section: "output", kind: "action",
  },
  // ── 批量应用范围与冲突策略 ───────────────────────────────────────────
  // 批量同步的作用域（1.2.0 接通）：候选与合法性都在引擎 scope.py，这里只给两个
  // 真能落的组合。逐点层（消除笔/修容笔笔迹、形变）按定义属于「这一张」的画布坐标与
  // 那一张自己的关键点，所以它们**不在任何一个选项里**——不是没做，是搬过去就是错的。
  "lnx.batch.v1.module_scope": {
    label: ["批量同步哪些层", "Layers to sync in batch"], section: "output",
    kind: "enum",
  },
  "lnx.batch.v1.conflict_policy": {
    label: ["同名冲突策略", "Name conflict policy"], section: "output", kind: "enum",
  },
  "lnx.batch.v1.preflight": {
    label: ["导出前整批体检", "Preflight the whole batch"], section: "output",
    kind: "action", blocked: true,
    why_not: ["现在只有「逐张失败如实上报 + 16-bit 母档的阻塞项点名」这一条：批量导出会把"
      + "每张的解码/写入结局逐条报出来，但没有一次「跑之前先把整批试解一遍」的独立动作。"
      + "做它需要一条只解码不写盘的预演命令，本轮未接。",
      "Per-image failures and 16-bit blockers are reported, but there is no decode-only dry run "
      + "of the whole batch yet."],
  },
  "lnx.batch.v1.commit": {
    label: ["整批提交", "Commit the batch"], section: "output", kind: "action",
    blocked: true,
    why_not: ["原子提交发生在**每张文件自己**那一层（写临时 → fsync → rename → 目录 fsync），"
      + "没有跨条目的「整批一次提交」：批量导出中途断电时，已完成的每张都是完整可读的文件，"
      + "未跑的不会出现半个。界面上放一个「提交」按钮会让人以为不点就还没落盘。",
      "Atomic commit is per file (tmp → fsync → rename → dir fsync); a cross-item «commit» button "
      + "would imply nothing is durable until pressed, which is false."],
  },
  // ── 工程 ────────────────────────────────────────────────────────────
  "lnx.project.v1.create": {
    label: ["新建工程", "New project"], section: "output", kind: "action",
  },
  "lnx.project.v1.open": {
    label: ["打开工程", "Open project"], section: "output", kind: "action",
  },
  "lnx.project.v1.save": {
    label: ["保存工程", "Save project"], section: "output", kind: "action",
  },
  "lnx.import.v1.choose_files": {
    label: ["导入图片…", "Import files…"], section: "output", kind: "action",
  },
  "lnx.import.v1.choose_folder": {
    label: ["导入整个文件夹…", "Import folder…"], section: "output", kind: "action",
  },
  "lnx.history.v1.undo": {
    label: ["撤销", "Undo"], section: "output", kind: "action", read: "history.can_undo",
  },
  "lnx.history.v1.redo": {
    label: ["重做", "Redo"], section: "output", kind: "action", read: "history.can_redo",
  },
  // 预设的两格都接通了（1.2.0）：清单/应用/保存/导入/删除走引擎的 cmd_preset，
  // 落盘格式是 lrt.preset.v1（scope.py 逐条校验参数键与量程）。
  "lnx.preset.v1.save": {
    label: ["保存当前配方为预设", "Save current recipe as preset"], section: "tone",
    kind: "action",
  },
  "lnx.preset.v1.apply": {
    label: ["应用预设", "Apply preset"], section: "tone", kind: "enum",
  },
  // ── 批量任务 ────────────────────────────────────────────────────────
  "lnx.task.v1.pause": {
    label: ["暂停批次", "Pause batch"], section: "output", kind: "action",
  },
  "lnx.task.v1.resume": {
    label: ["继续批次", "Resume batch"], section: "output", kind: "action",
  },
  "lnx.task.v1.cancel": {
    label: ["取消批次", "Cancel batch"], section: "output", kind: "action",
  },
  "lnx.task.v1.retry": {
    label: ["重试未完成", "Retry pending"], section: "output", kind: "action",
  },
};

/** 一格里要显示的东西（注册表的数 + 绑定表的展示名 + 接不通的原因）。 */
export interface Cell {
  entry: P0Entry;
  key: string;
  label: string;
  binding: Binding;
  /** 未登记（注册表新增项忘了补绑定）也要显式说出来，不能静默消失 */
  unlisted: boolean;
}

const pick = (p: [string, string]) => (lang() === "en" ? p[1] : p[0]);

/** 按分栏取这一栏该显示的格子：遍历的是注册表本体，绑定表只是补充。 */
export function cellsFor(section: SectionId): Cell[] {
  const out: Cell[] = [];
  for (const entry of ENTRIES) {
    const key = keyOf(entry);
    const binding = WIRING[key];
    if (!binding) {
      // 漏登记：照样渲染成"未接通"，并把"没登记"这件事本身说出来
      out.push({
        entry, key, label: key, unlisted: true,
        binding: {
          label: [key, key], section, kind: "action", blocked: true,
          why_not: ["注册表里有这一格，而宿主没有登记它的绑定：它必须是禁用并可见的，"
            + "不能不出现在界面上。",
            "The registry has this parameter but the shell has no binding for it: it must show up "
            + "disabled rather than not at all."],
        },
      });
      continue;
    }
    if (binding.section !== section) continue;
    out.push({ entry, key, label: pick(binding.label), binding, unlisted: false });
  }
  return out;
}

/** 数值格的量程：一律从注册表读（引擎也会随事件再报一遍硬上限，两边不一致时引擎赢）。 */
export function rangeOf(c: Cell): { min: number; max: number; step: number } | null {
  const r = c.entry.range;
  if (!r || r.min === null || r.max === null || r.step === null) return null;
  return { min: r.min, max: r.max, step: r.step };
}

/** 分栏标题（面板上的分组名）。 */
export const SECTION_TITLES: Record<SectionId, [string, string]> = {
  skin: ["质感与磨皮（高低频）", "Skin & frequency separation"],
  face: ["面部重塑与遮罩", "Face reshaping & mask"],
  tone: ["曝光 · 白平衡 · 肤色 · LUT", "Exposure · white balance · skin tone · LUT"],
  local: ["局部修容与画笔", "Local corrections & brush"],
  crop: ["裁剪与旋转", "Crop & rotation"],
  output: ["导出 · 批量 · 工程", "Export · batch · project"],
};

export const sectionTitleOf = (id: SectionId): string =>
  lang() === "en" ? SECTION_TITLES[id][1] : SECTION_TITLES[id][0];
