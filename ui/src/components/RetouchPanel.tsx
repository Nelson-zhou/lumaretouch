import { EyeHighlightsControl } from "./EyeHighlightsControl";
import {FabricPanel} from "../fabric/FabricPanel";
import {HistogramPanel} from "./HistogramPanel";
import {LevelsEditor} from "./LevelsEditor";
import { CurveEditor } from "./CurveEditor";
import { skinEditOptions, skinMaskReady, type SkinEdit } from "../skinScope";
import { TOOL_GROUPS, toolGroupOf, type ToolGroup } from "../toolNavigation";
/**
 * 右侧精修面板（Spec-Driven，1.12.0）。
 *
 * 功能清单不在这里手写：所有功能族与子控件从 `ui/src/spec/refine.json`
 * 读出来递归画（`SpecTree`）。本文件只负责三件事：
 *   ① 把已经接通的能力接上真控件（15 项能力 + 画笔/裁剪/换底/肤色定向）；
 *   ② 未开放的格子静默置灰，只在原生 Tooltip 里说明后续版本提供；
 *   ③ 人物栏：所有人 / 每张脸 / 多脸联动 / 添加与移出。
 *
 * 产品界面不打印内部编号、阶段标签、项数统计或后端实现细节。
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  runBackground, runCrop, runDeform, runEnhance, runExposure, runFace, runGrade,
  runHistory, runHsl, runLut, setStrength,
  type DocState, type EngineStatus, type FacePerson,
} from "../native";
import {
  FEATURES, SPEC_COUNTS, buildTree, type SpecFeature, type SpecNode,
  type SpecSubcontrol,
} from "../spec";
import { DisabledRow, SpecNodes } from "./SpecTree";
import { skinLimits, skinSliderBounds100 } from "../gradeLimits";

export type BrushMode = "heal" | "dodge" | "burn" | "color";

export interface RetouchProps {
  presetPanel?: React.ReactNode;
  whiteBalancePanel?: React.ReactNode;
  whiteBalanceBusy?: boolean;
  colorSamplePanel?: React.ReactNode;
  sourcePatchPanel?: React.ReactNode;
  status: EngineStatus | null;
  doc: DocState | null;
  hasImage: boolean;
  faceOk: boolean;
  faceWhy: string;
  note: (s: string) => void;
  onDone: () => void;
  /** 当前文档缩略图（JPEG base64）：人脸 chip 与 LUT 卡片的真实预览 */
  thumb?: string;
  /** 当前编辑范围：所有人（联动）或某一张脸（独立） */
  faceScope: "all" | number;
  onFaceScope: (s: "all" | number) => void;
  /** 视口画笔（引擎同一支管道：消除 / 局部调色 / 减淡 / 加深） */
  brush: { on: boolean; mode: BrushMode; radius: number };
  onBrush: (patch: Partial<{ on: boolean; mode: BrushMode; radius: number }>) => void;
  /** 打开裁剪/旋转模态（P0 lnx.crop.v1） */
  onOpenCrop: () => void;
  /** 框选补脸（PORTRAIT-006）：在画面里拖一个框，引擎再跑一次真检测 */
  onFaceAdd: () => void;
  faceAdding: boolean;
}

const ok = (p: Promise<unknown>, props: RetouchProps) =>
  p.then(props.onDone).catch((e) => props.note(String(e)));

function Slider(props: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  digits?: number;
  disabled?: boolean;
  title?: string;
  onChange: (v: number) => void;
  onReset: () => void;
}) {
  const [local, setLocal] = useState(props.value);
  const [text, setText] = useState(() => fmt(props.value));
  const dragging = useRef(false);
  const typing = useRef(false);
  const step = props.step ?? 1;

  function fmt(v: number) {
    return props.digits === undefined ? String(Math.round(v)) : v.toFixed(props.digits);
  }

  function snap(v: number) {
    const n = Math.min(props.max, Math.max(props.min, v));
    return Math.round(n / step) * step;
  }

  useEffect(() => {
    if (dragging.current || typing.current) return;
    setLocal(props.value);
    setText(fmt(props.value));
    // fmt 只依赖 props.digits；把它列进来会让滑杆每次父级刷新都重置光标。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.value]);

  const commit = () => {
    typing.current = false;
    const raw = Number(text);
    if (!Number.isFinite(raw)) {
      setText(fmt(local));
      return;
    }
    const v = snap(raw);
    setLocal(v);
    setText(fmt(v));
    if (v !== props.value) props.onChange(v);
  };

  const pct = ((local - props.min) / (props.max - props.min)) * 100;
  const zero = props.min < 0 && props.max > 0
    ? ((0 - props.min) / (props.max - props.min)) * 100 : 0;
  const lo = Math.min(pct, zero);
  const hi = Math.max(pct, zero);
  const track = `linear-gradient(to right, #343434 0 ${lo}%, #c79a63 ${lo}% ${hi}%, #343434 ${hi}% 100%)`;

  return (
    <div className={"pslider" + (props.disabled ? " off" : "")}>
      <div className="prow">
        <span className="plabel">{props.label}</span>
        <span className="pfield">
          <input className="pnum" type="text" inputMode="decimal"
            aria-label={`${props.label} 数值`}
            value={text} disabled={props.disabled}
            onChange={(e) => setText(e.target.value)}
            onFocus={(e) => { typing.current = true; e.currentTarget.select(); }}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
              if (e.key === "Escape") {
                typing.current = false;
                setText(fmt(props.value));
                e.currentTarget.blur();
              }
            }} />
          {props.unit && <span className="punit">{props.unit}</span>}
        </span>
      </div>
      <input type="range" min={props.min} max={props.max}
        step={step}
        value={local}
        disabled={props.disabled}
        aria-label={props.label}
        title={props.title ?? "双击归零"}
        style={{ background: track }}
        onPointerDown={() => { dragging.current = true; }}
        onPointerUp={() => { dragging.current = false; }}
        onPointerCancel={() => { dragging.current = false; }}
        onChange={(e) => {
          const v = +e.target.value;
          setLocal(v);
          setText(fmt(v));
          props.onChange(v);
        }}
        onDoubleClick={() => {
          dragging.current = false;
          props.onReset();
        }}
      />
    </div>
  );
}

const FACE_LABEL: Record<string, string> = {
  slim_face: "瘦脸",
  big_eye: "大眼",
  small_chin: "小下巴",
  smile: "微笑",
};

/** 人脸 chip 的头像：拿当前文档缩略图按归一化脸盒裁一块，不额外向引擎要图。 */
function FaceAvatar({ face, thumb, all }: {
  face?: FacePerson; thumb?: string; all?: boolean;
}) {
  if (all || !face?.box || !thumb) {
    return <i className={"faceAv ph" + (all ? " all" : "")}>{all ? "全" : "人"}</i>;
  }
  const [x0, y0, x1, y1] = face.box;
  const w = Math.max(0.06, Math.min(1, x1 - x0));
  const h = Math.max(0.06, Math.min(1, y1 - y0));
  const px = w < 0.999 ? Math.max(0, Math.min(100, (x0 / (1 - w)) * 100)) : 50;
  const py = h < 0.999 ? Math.max(0, Math.min(100, (y0 / (1 - h)) * 100)) : 50;
  return (
    <i className="faceAv"
      style={{
        backgroundImage: `url(data:image/jpeg;base64,${thumb})`,
        backgroundSize: `${100 / w}% ${100 / h}%`,
        backgroundPosition: `${px}% ${py}%`,
      }} />
  );
}

/** 已接通的控制：键是「功能族 ID|规格 path」，值是面板里的分派名。
 *
 * 这张表只做一件事——把规格里的那一条路径指到引擎的一条真命令上。表里没有的
 * 一律静默置灰；表里有的但引擎拒了（例如没关键点时开瘦脸），错误照样从引擎回来，
 * 面板不提前放行。
 */
const WIRED: Record<string, string> = {
  "PC-32455|直方图": "histogram.control",
  "PC-32455|色阶/输入黑场": "levels.control",
  "PC-32455|色阶/输入灰场": "levels.control",
  "PC-32455|色阶/输入白场": "levels.control",
  "PC-32455|色阶/输出黑场": "levels.control",
  "PC-32455|色阶/输出白场": "levels.control",
  "PC-32455|色阶/输入色阶": "levels.control",
  "PC-32455|色阶/输出色阶": "levels.control",
  "PC-32455|色阶/通道调整方法": "levels.control",
  "PC-32455|色阶/RGB": "levels.control",
  "PC-32455|色阶/红": "levels.control",
  "PC-32455|色阶/绿": "levels.control",
  "PC-32455|色阶/蓝": "levels.control",
  "PC-32455|曲线/RGB": "curves.control",
  "PC-32455|曲线/红": "curves.control",
  "PC-32455|曲线/绿": "curves.control",
  "PC-32455|曲线/蓝": "curves.control",
  "PC-32455|曲线/亮度": "curves.control",
  "PC-32455|曲线/亮度通道曲线": "curves.control",
  "PC-32455|曲线/添加控制点": "curves.control",
  "PC-32455|曲线/删除控制点": "curves.control",
  "PC-32455|曲线/移动控制点": "curves.control",

  // 皮肤调整
  "PC-32465|高低频磨皮-脸部/身体": "skin.strength",
  "PC-32465|质感磨皮": "skin.detail",
  "PC-32465|AI肤色统一（脸部）": "skin.broad",
  "PC-32465|水润磨皮-脸部/身体": "skin.radius",
  // 面部重塑 / 表情
  "PC-32466|脸型/瘦脸": "deform.slim_face",
  "PC-32466|眼睛/整体大小": "deform.big_eye",
  "PC-32466|脸型/收下巴": "deform.small_chin",
  "PC-32466|脸型预设/经典": "deform.preset:经典",
  "PC-32466|脸型预设/幼态": "deform.preset:幼态",
  "PC-32466|脸型预设/英气": "deform.preset:英气",
  "PC-32468|微笑嘴角": "deform.smile",
  "PC-32464|面部祛瑕疵/祛黑眼圈": "enh.dark_circles",
  "PC-32464|面部祛瑕疵/祛眼袋": "enh.eye_bags",
  // 五官细节
  "PC-32470|亮眼/眼白": "enh.sclera",
  "PC-32470|亮眼/眼瞳": "enh.iris",
  "PC-32470|祛红血丝": "enh.veins",
  "PC-32470|亮眼/眼睛高光": "enh.catchlight",
  "PC-32469|牙齿美白": "enh.teeth",
  // 色彩与光影
  "PC-32455|影调/曝光": "exp.ev",
  "PC-32455|白平衡/色温": "exp.temp",
  "PC-32455|白平衡/色调": "exp.tint",
  "PC-32455|影调/对比度": "tone.contrast",
  "PC-32455|影调/高光": "tone.highlights",
  "PC-32455|影调/阴影": "tone.shadows",
  "PC-32455|影调/饱和度": "tone.saturation",
  // 八色 HSL（原创扩展）：规格里 HSL 那一支只有 色相/饱和度/明亮度 三格，色段
  // 选择器画在父节点（见 hslChips），三格作用的是当前选中的那一段。
  "PC-32455|HSL/色相": "hsl.hue",
  "PC-32455|HSL/饱和度": "hsl.sat",
  "PC-32455|HSL/明亮度": "hsl.lum",
  "PC-32455|滤镜/强度": "lut.amount",
  // 裁剪旋转
  "PC-32478|裁剪": "crop.open",
  "PC-32478|旋转/顺时针": "crop.cw",
  "PC-32478|旋转/逆时针": "crop.ccw",
  "PC-32478|旋转/倾斜角度": "crop.open",
  // 手动修复
  // F13（P2-4）：只有“污点修复画笔”背后是真·heal 笔迹（按落点扩散、无独立采样）。
  // 来源区域修补由独立 sourcePatchPanel 接入，不借 brush.heal；仿制图章仍未接通。
  "PC-32482|污点修复画笔": "brush.heal",
  // 历史
  "PC-47209|撤销": "history.undo",
  "PC-47209|重做": "history.redo",
};

/** 独立来源区域修补不冒充 heal 或仿制图章；缺少独立面板时保留明确说明。 */
const LEAF_NOTE: Record<string, string> = {
  "PC-32470|眼神光": "可放置眼神光素材尚未实现；亮眼中的眼睛高光仅增强原片已有高光。",
  "PC-32470|眼神光/程度": "素材眼神光尚未接通，不用现有高光增强替代。",
  "PC-32482|修补工具": "来源区域修补需要独立取样视图与匹配版本的引擎；不会使用消除笔替代。",
  "PC-32482|仿制图章": "仿制图章尚未实现持续采样点与逐笔来源偏移；来源区域修补不是仿制图章。",
};

/** 已接通格子的产品名：规格 path 的最后一段常常只是“身体/程度”，
 *  直接当滑杆名会让两行都叫“身体”。这里只改显示名，不改规格 path。 */
const WIRE_LABEL: Record<string, string> = {
  "skin.strength": "磨皮强度",
  "skin.detail": "质感保留",
  "skin.broad": "肤色匀净",
  "skin.radius": "磨皮半径",
  "deform.slim_face": "瘦脸",
  "deform.big_eye": "大眼",
  "deform.small_chin": "小下巴",
  "deform.smile": "微笑",
  "enh.dark_circles": "祛黑眼圈",
  "enh.eye_bags": "祛眼袋",
  "enh.sclera": "眼白提亮",
  "enh.iris": "眼瞳提亮",
  "enh.veins": "祛红血丝",
  "enh.catchlight": "眼睛高光",
  "enh.teeth": "牙齿美白",
  "exp.ev": "曝光",
  "exp.temp": "色温",
  "exp.tint": "色调",
  "tone.contrast": "对比度",
  "tone.highlights": "高光",
  "tone.shadows": "阴影",
  "tone.saturation": "饱和度",
  "hsl.hue": "色相",
  "hsl.sat": "饱和度",
  "hsl.lum": "明亮度",
  "lut.amount": "风格强度",
  "crop.open": "裁剪",
  "crop.cw": "顺时针 90°",
  "crop.ccw": "逆时针 90°",
  "brush.heal": "修复画笔",
  "history.undo": "撤销",
  "history.redo": "重做",
};

/** 八色 HSL 的色段：与 ops/hsl.py 的 BAND_NAMES 同序。名字与量程以引擎上报为准，
 *  这一份只做首帧（doc 还没回来时）的占位与色块底色。 */
const HSL_BANDS = ["红", "橙", "黄", "绿", "青", "蓝", "紫", "洋红"];
const HSL_CHIP_COLORS = ["#e2534b", "#ef8b3a", "#e3c443", "#5fae57",
                         "#49b3b0", "#4b7bd0", "#8a63c9", "#cf5fa8"];

const SHAPE_PRESETS: Record<string, Record<string, number>> = {
  经典: { slim_face: 0.22, big_eye: 0.04, small_chin: 0.14, smile: 0 },
  幼态: { slim_face: 0.12, big_eye: 0.10, small_chin: 0.10, smile: 0.05 },
  英气: { slim_face: 0.30, big_eye: 0.02, small_chin: 0.18, smile: 0 },
};

/** 面板上用产品语言呈现的分组名：只改显示，不动规格原文。 */
const PANEL_TITLE: Record<string, string> = {
  "PC-32464": "瑕疵修复",
  "PC-32465": "皮肤质感",
  "PC-32466": "面部重塑",
  "PC-32468": "表情微调",
  "PC-32469": "牙齿美化",
  "PC-32470": "眼部精修",
  "PC-32471": "妆容调整",
  "PC-32472": "发型调整",
  "PC-46608": "手部美化",
  "PC-9XYcMCvHXW": "足部美化",
  "PC-32473": "全身塑形",
  "PC-32474": "背景处理",
  "PC-32475": "证件照换底",
  "PC-32476": "天空替换",
  "PC-32477": "衣物修饰",
  "PC-32452": "风格调色",
  "PC-32455": "色彩光影",
  "PC-32454": "局部调色",
  "PC-32479": "手动液化",
  "PC-32482": "修复工具",
  "PC-32481": "局部画笔",
  "PC-32480": "批量同步",
  "PC-4WvzDIBakP": "宠物修复",
  "PC-DaMvAbwxp4": "眼部调整",
  "PC-32478": "裁剪与旋转",
  "PC-AlCcjw85ql": "去除黑白边",
  "PC-165385": "构图参考线",
  "PC-47209": "历史记录",
};

/** 说明书式的概述与常见问答不占工作台版面；数据仍在 DOM 与规格 JSON 里。 */
const ARCHIVE_IDS = new Set([
  "PC-47248", "PC-47246", "PC-230985",
  "PC-32558", "PC-64490", "PC-149774", "PC-32550",
  "PC-121089", "PC-124704", "PC-32552",
]);

function hexToRgb(hex: string): number[] {
  const h = hex.replace("#", "");
  const n = h.length === 3
    ? h.split("").map((c) => parseInt(c + c, 16))
    : [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  return n.map((v) => (Number.isFinite(v) ? Math.max(0, Math.min(255, v)) : 255));
}

export default function RetouchPanel(props: RetouchProps) {
  const { doc, status } = props;
  const dim = !props.hasImage;
  const skinReady = skinMaskReady(status?.precompute?.mask_channels, status?.precompute?.mask_nonzero_pixels);
  const skinWhy = props.faceScope !== "all" ? "单人物磨皮尚未接通，请选择所有人"
    : skinReady ? "" : "尚无有效皮肤掩膜，请先完成人像分析";
  const params = doc?.params ?? {};
  const amounts = doc?.deform.amounts ?? {};
  const enhAmounts = doc?.enhance?.amounts ?? {};
  const ex = doc?.exposure;
  const grade = doc?.grade;
  // P2-3：肤色定向三条滑杆的量程来自引擎报的 grade_limits（不是前端写死 ±100）。
  // ×100 整数表示：dh→±5、ds/dv→±60，换算回后端单位正好落在 check_params 的有效带。
  const gradeBounds = skinSliderBounds100(skinLimits(status?.grade_limits));
  const presets = status?.presets ?? [];
  const faces = doc?.face?.faces ?? [];
  const faceIdx = typeof props.faceScope === "number" ? props.faceScope : null;
  const scope: "all" | "person" = props.faceScope === "all" ? "all" : "person";
  const [q, setQ] = useState("");
  const [toolGroup, setToolGroup] = useState<ToolGroup>("color");
  const contentRef = useRef<HTMLDivElement | null>(null);
  const scrollPositions = useRef<Partial<Record<ToolGroup, number>>>({});
  useLayoutEffect(() => {
    if (contentRef.current) contentRef.current.scrollTop = q.trim() ? 0 : (scrollPositions.current[toolGroup] ?? 0);
  }, [toolGroup, q]);
  const [bgHex, setBgHex] = useState("#ffffff");
  const [openSeen, setOpenSeen] = useState<Record<string, boolean>>({});
  // 八色 HSL 当前选中的色段（0…7）。这是**界面选择**，不是文档状态：切图后同一段
  // 继续被选中，引擎侧那 24 个数才是画面事实。
  const [hslBand, setHslBand] = useState(0);
  const hslNames = doc?.hsl?.names ?? HSL_BANDS;

  const trees = useMemo(
    () => FEATURES.map((f) => ({ f, tree: buildTree(f.subcontrols) })),
    [],
  );

  const commitSkin = (patch: SkinEdit) => {
    if (!doc || dim) return;
    if (skinWhy) { props.note(skinWhy); return; }
    ok(setStrength(patch.strength, skinEditOptions(patch)), props);
  };

  const commitDeform = (patch: Record<string, number>) => {
    const p = faceIdx === null ? Promise.resolve() : runFace("select", faceIdx);
    ok(p.then(() => runDeform("set", patch, scope)), props);
  };

  const commitEnhance = (patch: Record<string, number>) =>
    ok(runEnhance("set", patch), props);

  const commitExposure = (patch: Record<string, number>) =>
    ok(runExposure("set", patch, true), props);

  const rotateBy = (delta: number) => {
    const cur = doc?.crop?.rotation_degrees ?? 0;
    let next = cur + delta;
    if (next > 180) next -= 360;
    if (next < -180) next += 360;
    ok(runCrop("set", doc?.crop?.rect ?? [0, 0, 1, 1], next), props);
  };

  const applyBg = () => {
    const backend = status?.matting_backends?.baseline?.[0] ?? "color_key";
    ok(runBackground("set", { backend, bg: hexToRgb(bgHex) }), props);
  };

  const lutOn = !!doc?.lut.preset;
  const lutAmt = doc?.lut.amount ?? 1;
  const gradeScopes = grade?.scopes ?? ["all", "skin"];
  const maskPx = grade?.mask_px ?? 0;

  const brushOn = props.brush.on;
  const brushMode = props.brush.mode;

  /** 已接通叶子的实际控件。`name` 是规格 path 的最后一段。 */
  const renderWired = (leaf: SpecSubcontrol, name: string,
                       kind: string): React.ReactNode => {
    const label = WIRE_LABEL[kind] ?? name;
    if (kind.startsWith("deform.preset:")) {
      const preset = kind.split(":")[1];
      return (
        <button key={leaf.path} className="specBtn" title={`脸型预设：${name}`}
          disabled={dim || !props.faceOk}
          onClick={() => {
            setOpenSeen((s) => ({ ...s, [preset]: true }));
            commitDeform(SHAPE_PRESETS[preset] ?? {});
          }}>
          <b>{name}</b><em>预设</em>
        </button>
      );
    }
    switch (kind) {
      case "histogram.control": return null;
      case "levels.control": return null;
      case "curves.control": return null; // implemented together in CurveEditor
      case "skin.strength":
        return (
          <Slider key={leaf.path} label={label}
            value={Math.round((doc?.strength ?? 0) * 100)} min={0} max={100}
            disabled={dim || !!skinWhy} title={skinWhy || undefined} onChange={(v) => commitSkin({ strength: v / 100 })}
            onReset={() => commitSkin({ strength: 0 })} />
        );
      case "skin.detail":
        return (
          <Slider key={leaf.path} label={label}
            value={Math.round(((params.detail_gain ?? 0) / 2) * 100)} min={0} max={100}
            disabled={dim || !!skinWhy} title={skinWhy || undefined} onChange={(v) => commitSkin({ detail: (v / 100) * 2 })}
            onReset={() => commitSkin({ detail: 0 })} />
        );
      case "skin.broad":
        return (
          <Slider key={leaf.path} label={label}
            value={Math.round(((params.broad_gain ?? 0) / 2) * 100)} min={0} max={100}
            disabled={dim || !!skinWhy} title={skinWhy || undefined} onChange={(v) => commitSkin({ broad: (v / 100) * 2 })}
            onReset={() => commitSkin({ broad: 0 })} />
        );
      case "skin.radius":
        return (
          <Slider key={leaf.path} label={label}
            value={Math.round(params.radius ?? 12)} min={2} max={24}
            disabled={dim || !!skinWhy} title={skinWhy || undefined} onChange={(v) => commitSkin({ radius: v })}
            onReset={() => commitSkin({ radius: 12 })} />
        );
      case "deform.slim_face":
      case "deform.big_eye":
      case "deform.small_chin":
      case "deform.smile": {
        const key = kind.slice("deform.".length);
        return (
          <Slider key={leaf.path} label={label}
            value={Math.round((amounts[key] ?? 0) * 100)} min={0} max={100}
            disabled={dim || !props.faceOk}
            title={props.faceOk ? "拖动调整" : props.faceWhy}
            onChange={(v) => commitDeform({ [key]: v / 100 })}
            onReset={() => commitDeform({ [key]: 0 })} />
        );
      }
      case "enh.catchlight":
        return <EyeHighlightsControl key={leaf.path} amounts={enhAmounts}
          disabled={dim || !props.faceOk} reason={props.faceOk ? undefined : props.faceWhy}
          commit={commitEnhance} Slider={Slider} />;
      case "enh.veins":
      case "enh.dark_circles":
      case "enh.eye_bags":
      case "enh.sclera":
      case "enh.iris":
      case "enh.teeth": {
        const key = kind.slice("enh.".length);
        return (
          <Slider key={leaf.path} label={label}
            value={Math.round((enhAmounts[key] ?? 0) * 100)} min={0} max={100}
            disabled={dim || !props.faceOk}
            title={props.faceOk ? "拖动调整" : props.faceWhy}
            onChange={(v) => commitEnhance({ [key]: v / 100 })}
            onReset={() => commitEnhance({ [key]: 0 })} />
        );
      }
      case "exp.ev":
        return (
          <Slider key={leaf.path} label={label}
            value={ex?.ev ?? 0} min={-5} max={5} step={0.05}
            unit="EV" digits={2} disabled={dim}
            onChange={(v) => commitExposure({ ev: v })}
            onReset={() => commitExposure({ ev: 0 })} />
        );
      case "exp.temp":
        return (
          <Slider key={leaf.path} label={label}
            value={Math.round(ex?.temperature_shift ?? 0)} min={-2000} max={2000} step={20}
            unit="K" disabled={dim||props.whiteBalanceBusy}
            onChange={(v) => commitExposure({ temperature_shift: v })}
            onReset={() => commitExposure({ temperature_shift: 0 })} />
        );
      case "exp.tint":
        return (
          <Slider key={leaf.path} label={label}
            value={Math.round((ex?.tint_shift ?? 0) * 100)} min={-100} max={100}
            disabled={dim||props.whiteBalanceBusy}
            onChange={(v) => commitExposure({ tint_shift: v / 100 })}
            onReset={() => commitExposure({ tint_shift: 0 })} />
        );
      case "hsl.hue":
      case "hsl.sat":
      case "hsl.lum": {
        const i = kind === "hsl.hue" ? 0 : kind === "hsl.sat" ? 1 : 2;
        const cur = doc?.hsl?.bands?.[hslBand * 3 + i] ?? 0;
        const lim = i === 0 ? (doc?.hsl?.limits?.hue ?? 60)
          : i === 1 ? (doc?.hsl?.limits?.sat ?? 100)
            : (doc?.hsl?.limits?.lum ?? 100);
        const key = (["dh", "ds", "dl"] as const)[i];
        return (
          <Slider key={leaf.path}
            label={`${hslNames[hslBand] ?? HSL_BANDS[hslBand]} · ${label}`}
            value={Math.round(cur)} min={-lim} max={lim}
            disabled={dim}
            onChange={(v) => ok(runHsl("set", hslBand, { [key]: v }, true), props)}
            onReset={() => ok(runHsl("set", hslBand, { [key]: 0 }, true), props)} />
        );
      }
      case "tone.contrast":
      case "tone.highlights":
      case "tone.shadows":
      case "tone.saturation": {
        const key = kind.slice("tone.".length) as
          "contrast" | "highlights" | "shadows" | "saturation";
        return (
          <Slider key={leaf.path} label={label}
            value={Math.round((ex?.[key] ?? 0) as number)} min={-100} max={100}
            disabled={dim}
            onChange={(v) => commitExposure({ [key]: v })}
            onReset={() => commitExposure({ [key]: 0 })} />
        );
      }
      case "lut.amount":
        return (
          <Slider key={leaf.path} label={label}
            value={Math.round(lutAmt * 100)} min={0} max={100}
            unit="%" disabled={dim || !lutOn}
            title={lutOn ? "拖动调整" : "先选择一个风格"}
            onChange={(v) => ok(runLut("set", {
              preset: doc?.lut.preset ?? undefined, amount: v / 100,
            }), props)}
            onReset={() => ok(runLut("set", {
              preset: doc?.lut.preset ?? undefined, amount: 0,
            }), props)} />
        );
      case "crop.open":
        return (
          <button key={leaf.path} className="specBtn" title="裁剪与旋转" disabled={dim}
            onClick={() => props.onOpenCrop()}>
            <b>{label}</b><em>打开</em>
          </button>
        );
      case "crop.cw":
      case "crop.ccw":
        return (
          <button key={leaf.path} className="specBtn"
            title={kind === "crop.cw" ? "顺时针旋转 90°" : "逆时针旋转 90°"} disabled={dim}
            onClick={() => rotateBy(kind === "crop.cw" ? 90 : -90)}>
            <b>{label}</b><em>旋转</em>
          </button>
        );
      case "brush.heal":
        return (
          <button key={leaf.path} className="specBtn" title="修复画笔" disabled={dim}
            onClick={() => props.onBrush({ mode: "heal", on: true })}>
            <b>{label}</b><em>画笔</em>
          </button>
        );
      case "history.undo":
      case "history.redo":
        return (
          <button key={leaf.path} className="specBtn"
            title={kind === "history.undo" ? "撤销上一步" : "重做"}
            disabled={dim || (kind === "history.undo" ? !doc?.history.can_undo
              : !doc?.history.can_redo)}
            onClick={() => ok(runHistory(kind === "history.undo" ? "undo" : "redo"), props)}>
            <b>{label}</b><em>历史</em>
          </button>
        );
      default:
        return <DisabledRow key={leaf.path} name={name} />;
    }
  };

  /** 规格树里需要额外画一块的节点：目前只有 HSL 的八色色段选择器。
   *  三格滑杆仍是规格里的叶子（HSL/色相…），这里只决定“改哪一段”。 */
  const renderExtra = (node: SpecNode, featureId?:string): React.ReactNode => {
    if(featureId==="PC-32455"&&node.full==="白平衡")return props.whiteBalancePanel;
    if(featureId==="PC-32455"&&node.full==="直方图")return <HistogramPanel
      key={status?.image?.load_id??"empty"} documentId={status?.image?.load_id??""} snapshotId={doc?.document_id}
      revision={status?.doc_rev??-1} result={status?.color_scopes} disabled={!props.hasImage||status?.ready_caps?.color_scopes_protocol!==1} onDone={props.onDone}/>;
    if (featureId === "PC-32455" && node.full === "色阶") return <LevelsEditor
      key={status?.image?.load_id??"empty"} value={doc?.levels} documentId={status?.image?.load_id??""}
      snapshotId={doc?.document_id} documentRevision={status?.doc_rev??-1}
      disabled={!props.hasImage} result={status?.levels_result} onDone={props.onDone} note={props.note}/>;
    if (featureId === "PC-32455" && node.full === "曲线") return <CurveEditor
      key={status?.image?.load_id ?? status?.image?.doc ?? "empty"} value={doc?.curves}
      documentId={status?.image?.load_id??""} snapshotId={doc?.document_id} documentRevision={status?.doc_rev??-1}
      disabled={!props.hasImage} parametricSupported={status?.ready_caps?.curve_recipe_versions?.includes(3)===true} result={status?.curve_result} error={status?.last_error??null} onDone={props.onDone} note={props.note}/>;
    if (node.full !== "HSL") return null;
    return (
      <div className="hslChips" key="hsl-chips" data-hsl-band={hslBand}>
        {HSL_BANDS.map((n, i) => (
          <button key={n} title={`${n}色`}
            className={"hslChip" + (i === hslBand ? " on" : "")}
            style={{ background: HSL_CHIP_COLORS[i] }}
            onClick={() => setHslBand(i)}>{n}</button>
        ))}
        <button className="hslChip reset" title="八段全部归零"
          onClick={() => ok(runHsl("clear"), props)}>归零</button>
      </div>
    );
  };

  /** 已接通祖先链：默认展开，别让真控件埋在折叠里。 */
  const openPathsFor = (f: SpecFeature): Set<string> => {
    const open = new Set<string>();
    if(f.id === "PC-32455") {open.add("曲线");open.add("色阶");}
    for (const leaf of f.subcontrols) {
      if (!WIRED[`${f.id}|${leaf.path}`]) continue;
      const parts = leaf.path.split("/");
      let full = "";
      for (let i = 0; i < parts.length - 1; i++) {
        full = full ? `${full}/${parts[i]}` : parts[i];
        open.add(full);
      }
      // 叶子所在的那一层也要开：像 `高低频磨皮-脸部/身体` 这种路径，
      // “身体”自己还有子项，是一个 <details>——不把 full 加进来，真滑杆就
      // 被折叠在“身体”里，用户只看见一个计数。
      open.add(leaf.path);
    }
    return open;
  };

  const visibleTrees = trees.filter(({ f }) =>
    f.id !== "PC-47211" && !ARCHIVE_IDS.has(f.id));
  const archived = FEATURES.filter((f) =>
    f.id !== "PC-47211" && ARCHIVE_IDS.has(f.id));

  const query = q.trim().toLowerCase();
  const hit = (f: SpecFeature) => {
    if (!query) return true;
    const title = PANEL_TITLE[f.id] ?? f.title;
    return title.toLowerCase().includes(query)
      || f.title.toLowerCase().includes(query)
      || f.subcontrols.some((s) => s.path.toLowerCase().includes(query));
  };

  const lutBlock = (
    <>
      <div className="lutGrid">
        <button className={"lutCard" + (!lutOn ? " on" : "")} disabled={dim}
          onClick={() => ok(runLut("clear"), props)}>
          <span className="lutThumb none">原</span>
          <span className="lutName">原片</span>
        </button>
        {presets.map((p) => (
          <button key={p.name}
            className={"lutCard" + (doc?.lut.preset === p.name ? " on" : "")}
            disabled={dim}
            onClick={() => ok(runLut("set", { preset: p.name, amount: lutAmt || 1 }), props)}>
            <span className="lutThumb"
              style={props.thumb ? {
                backgroundImage: `url(data:image/jpeg;base64,${props.thumb})`,
                filter: p.name === "creamy"
                  ? "sepia(.16) saturate(1.06) brightness(1.04) contrast(.98)"
                  : "saturate(.9) brightness(1.03) contrast(1.04) hue-rotate(-6deg)",
              } : undefined} />
            <span className="lutName">{p.title}</span>
          </button>
        ))}
        <button className="lutCard off" disabled title="自定义 LUT 导入将在后续版本提供">
          <span className="lutThumb none dashed">+</span>
          <span className="lutName">导入 LUT</span>
        </button>
      </div>
    </>
  );

  const gradeBlock = (
    <div className="specBlock">
      <div className="specBlockTitle">肤色定向</div>
      <Slider label="色相偏移" value={Math.round((grade?.dh ?? 0) * 100)}
        min={gradeBounds[0].min} max={gradeBounds[0].max} disabled={dim}
        onChange={(v) => ok(runGrade("set", { dh: v / 100 }), props)}
        onReset={() => ok(runGrade("set", { dh: 0 }), props)} />
      <Slider label="饱和偏移" value={Math.round((grade?.ds ?? 0) * 100)}
        min={gradeBounds[1].min} max={gradeBounds[1].max} disabled={dim}
        onChange={(v) => ok(runGrade("set", { ds: v / 100 }), props)}
        onReset={() => ok(runGrade("set", { ds: 0 }), props)} />
      <Slider label="明度偏移" value={Math.round((grade?.dv ?? 0) * 100)}
        min={gradeBounds[2].min} max={gradeBounds[2].max} disabled={dim}
        onChange={(v) => ok(runGrade("set", { dv: v / 100 }), props)}
        onReset={() => ok(runGrade("set", { dv: 0 }), props)} />
      <Slider label="混入比例" value={Math.round((grade?.amount ?? 1) * 100)}
        min={0} max={100} disabled={dim}
        onChange={(v) => ok(runGrade("amount", { amount: v / 100 }), props)}
        onReset={() => ok(runGrade("amount", { amount: 0 }), props)} />
      <div className="specSeg">
        <span>作用范围</span>
        {(["all", "skin", "brush"] as const).map((s) => {
          const on = (grade?.scope ?? "all") === s;
          const off = s === "brush" && maskPx === 0;
          return (
            <button key={s} className={on ? "on" : ""}
              disabled={dim || !gradeScopes.includes(s) || off}
              title={off ? "先用「局部调色笔」在画面里涂抹一块区域"
                : s === "all" ? "整张图" : s === "skin" ? "只作用于肤色" : "只作用于涂抹区域"}
              onClick={() => ok(runGrade("scope", { scope: s }), props)}>
              {s === "all" ? "全图" : s === "skin" ? "肤色" : "涂抹区域"}
            </button>
          );
        })}
      </div>
    </div>
  );

  const bgBlock = (
    <div className="specBlock">
      <div className="specBlockTitle">证件照换底</div>
      <div className="specSeg">
        <span>底色</span>
        <input type="color" value={bgHex} disabled={dim}
          onChange={(e) => setBgHex(e.target.value)} title="选择纯色背景" />
        <button className="on" disabled={dim} onClick={applyBg}>应用换底</button>
        <button disabled={dim || !status?.background?.bg_active}
          onClick={() => ok(runBackground("clear"), props)}>还原</button>
      </div>
    </div>
  );

  const historyBlock = (
    <div className="specSeg">
      <span>历史</span>
      <button disabled={dim || !doc?.history.can_undo}
        onClick={() => ok(runHistory("undo"), props)}>
        撤销（{doc?.history.undo_steps ?? 0}）
      </button>
      <button disabled={dim || !doc?.history.can_redo}
        onClick={() => ok(runHistory("redo"), props)}>
        重做（{doc?.history.redo_steps ?? 0}）
      </button>
    </div>
  );

  const brushBlock = (
    <div className="specBlock">
      <div className="specBlockTitle">局部画笔</div>
      <div className="specSeg">
        {([
          ["heal", "消除笔"],
          ["color", "局部调色笔"],
          ["dodge", "减淡"],
          ["burn", "加深"],
        ] as const).map(([mode, label]) => (
          <button key={mode} className={brushOn && brushMode === mode ? "on" : ""}
            disabled={dim}
            onClick={() => props.onBrush({ mode, on: true })}>{label}</button>
        ))}
        <button className={!brushOn ? "on" : ""} disabled={dim}
          onClick={() => props.onBrush({ on: false })}>关闭</button>
      </div>
      <Slider label="画笔大小" value={props.brush.radius} min={2} max={40}
        disabled={dim}
        onChange={(v) => props.onBrush({ radius: v })}
        onReset={() => props.onBrush({ radius: 8 })} />
    </div>
  );

  const blockFor = (fid: string): React.ReactNode => {
    if (fid === "PC-32452") return <>{props.presetPanel}{lutBlock}</>;
    if (fid === "PC-32454") return gradeBlock;
    if (fid === "PC-32475") return bgBlock;
    if (fid === "PC-47209") return historyBlock;
    if (fid === "PC-32477") return <FabricPanel value={doc?.fabric} documentId={doc?.document_id} revision={status?.doc_rev??0} disabled={dim} onDone={props.onDone} note={props.note}/>;
    if (fid === "PC-32482") return <>{props.sourcePatchPanel}{brushBlock}</>;
    return null;
  };

  return (
    <div className="retouch" data-spec-total={SPEC_COUNTS.features}
         data-spec-controls={SPEC_COUNTS.subcontrols}>
      <div className="rtContent" ref={contentRef} onScroll={(e) => {
        if (!q.trim()) scrollPositions.current[toolGroup] = e.currentTarget.scrollTop;
      }}>
      <div className="rtTitle">{q.trim() ? "功能搜索" : TOOL_GROUPS.find(g => g.id === toolGroup)?.label}</div>

      {/* ① 人物栏：所有人 / 每张脸 / 多脸联动 / 添加与移出 */}
      <div className="faceBar" data-spec-family="PC-47211" hidden={toolGroup !== "portrait" || !!query}>
        <div className="faceHead">
          <span>人物</span>
          <em>{faces.length ? `${faces.length} 人` : "未检测到人脸"}</em>
        </div>
        <div className="faceChips">
          <button className={"faceChip" + (props.faceScope === "all" ? " on" : "")}
            disabled={dim} onClick={() => props.onFaceScope("all")}
            title="所有人联动：一次调整应用到画面里的每一张脸">
            <FaceAvatar all />
            <span>所有人</span>
          </button>
          {faces.map((f) => (
            <button key={f.index}
              className={"faceChip" + (faceIdx === f.index ? " on" : "")}
              disabled={dim || !!f.disabled || doc?.face?.blocked}
              title={f.disabled ? "已标记为非脸" : `单独编辑第 ${f.index + 1} 人`}
              onClick={() => {
                props.onFaceScope(f.index);
                ok(runFace("select", f.index), props);
              }}>
              <FaceAvatar face={f} thumb={props.thumb} />
              <span>人物 {f.index + 1}</span>
            </button>
          ))}
          {!faces.length && dim && <span className="faceEmpty">打开照片后自动识别人物</span>}
        </div>
        <div className="faceState">
          <button className={"faceLock" + (props.faceScope === "all" ? " on" : "")}
            disabled={dim || !faces.length}
            title="在多脸同步与单脸调整之间切换"
            onClick={() => props.onFaceScope(props.faceScope === "all"
              ? (faces[0]?.index ?? "all") : "all")}>
            {props.faceScope === "all" ? "多脸联动" : "单脸调整"}
          </button>
          <span>{props.faceScope === "all"
            ? "所有人物同步调整"
            : `仅调整人物 ${(faceIdx ?? 0) + 1}`}</span>
        </div>
        <div className="faceActs">
          <button className="specBtn slim" disabled={dim || props.faceAdding}
            title="在画面中框选一张脸，追加为人物"
            onClick={() => props.onFaceAdd()}>
            <b>{props.faceAdding ? "在画面中框选…" : "＋ 添加人物"}</b>
          </button>
          <button className="specBtn slim" disabled={dim || faceIdx === null}
            title="将当前人物从编辑范围中排除"
            onClick={() => {
              if (faceIdx === null) return;
              ok(runFace("disable", faceIdx), props);
            }}>
            <b>排除人物</b>
          </button>
          <span className="faceAttr" title="年龄与性别识别将在后续版本提供">
            男女长幼
          </span>
        </div>
      </div>

      <div className="specSearchBar">
        <svg className="searchIcon" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="11" cy="11" r="6.5" />
          <path d="m16 16 4 4" />
        </svg>
        <input className="specSearch" value={q} placeholder="搜索全部功能，如 曝光、磨皮"
          onChange={(e) => setQ(e.target.value)} />
      </div>

      {query && !visibleTrees.some(({ f }) => hit(f)) && (
        <div className="specEmpty">未找到相关功能</div>
      )}

      {/* ② 其余功能族：按规格顺序递归渲染；未开放的项只置灰，不贴任何标签 */}
      {visibleTrees.map(({ f, tree }) => {
        const custom = blockFor(f.id);
        const open = !!query || (openSeen[f.id] ?? (f.id === "PC-32465" || f.id === "PC-32455"));
        const title = PANEL_TITLE[f.id] ?? f.title;
        return (
          <details className="pg sfam" key={f.id} open={open}
            data-spec-family={f.id}
            hidden={query ? !hit(f) : toolGroupOf(f.id) !== toolGroup}
            onToggle={(e) => {
              const el = e.currentTarget as HTMLDetailsElement;
              if (!query) { const next = el.open; setOpenSeen((s) => s[f.id] === next ? s : { ...s, [f.id]: next }); }
            }}>
            <summary title={title}>
              <span>{title}</span>
            </summary>
            <div className="pgBody">
              {f.id === "PC-32465" && skinWhy && <div className="specEmpty" role="status">{skinWhy}</div>}
              {f.id === "PC-32455" && props.colorSamplePanel}
              {custom}
              {tree.length > 0 && (
                <SpecNodes nodes={tree}
                  openPaths={openPathsFor(f)} renderExtra={node=>renderExtra(node,f.id)}
                  renderLeaf={(leaf, name) => {
                    if(f.id==='PC-32477'&&leaf.path==='衣服祛褶皱/祛细褶皱')return null;
                    if(f.id==='PC-32482'&&leaf.path==='修补工具'&&props.sourcePatchPanel)return null;
                    const kind = WIRED[`${f.id}|${leaf.path}`];
                    return kind ? renderWired(leaf, name, kind)
                      : <DisabledRow key={leaf.path} name={name}
                          hint={LEAF_NOTE[`${f.id}|${leaf.path}`]} />;
                  }} />
              )}
            </div>
          </details>
        );
      })}

      {/* 概述与常见问答不占工作台版面；保留隐藏节点是为了完整数据契约与白盒审计。 */}
      <div className="specArchive" hidden aria-hidden="true">
        {archived.map((f) => <div key={f.id} data-spec-family={f.id} />)}
      </div>
      </div>
      <nav className="rtToolNav" aria-label="精修工具分类">
        {TOOL_GROUPS.map(group => (
          <button key={group.id} type="button" aria-pressed={!query && toolGroup === group.id}
            title={group.label} onClick={() => { setToolGroup(group.id); setQ(""); }}>
            {group.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
