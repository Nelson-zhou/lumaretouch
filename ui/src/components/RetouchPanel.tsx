import {EyeMakeupEnhanceControl} from '../eyeMakeupEnhance/EyeMakeupEnhanceControl';
import {FacialSculptPanel} from '../facialSculpt/FacialSculptPanel';
import {FringeRepairPanel} from '../fringeRepair/FringeRepairPanel';
import type {FringeRepairOwner} from '../fringeRepair/useFringeRepairWorkflow';
import {ConnectedPhotoGrainPanel} from '../photoGrain/ConnectedPhotoGrainPanel';
import {CommonBackgroundPanel} from '../commonBackground/CommonBackgroundPanel';
import type {CommonBackgroundOwner} from '../commonBackground/useCommonBackgroundWorkflow';
import {ConnectedPrimaryCalibrationPanel} from "../primaryCalibration/ConnectedPrimaryCalibrationPanel";
import {ConnectedColourEditorPanel} from "../colourEditor/ConnectedColourEditorPanel";
import {ConnectedSelectiveColourPanel} from "../selectiveColour/ConnectedSelectiveColourPanel";
import {ConnectedColourGradingPanel} from "../colourGrading/ConnectedColourGradingPanel";
import {ConnectedPhotoDetailPanel} from "../photoDetail/ConnectedPhotoDetailPanel";
import {ConnectedExtendedTonePanel} from "../extendedTone/ConnectedExtendedTonePanel";
import {ConnectedCustomLutPanel} from "../customLut/ConnectedCustomLutPanel";
import {FaceDecorationPanel} from '../faceDecoration/FaceDecorationPanel';
import {PeoplePanel} from '../people/PeoplePanel';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {peopleContext, type ParameterPatch} from '../people/model';
import {portraitRequestsBusy} from '../people/portraitAccess';
import {HairColourPanel} from '../hairColour/HairColourPanel';
import type {HairPort} from '../hairColour/model';
import {MouthShapeControls} from "../mouthShape/MouthShapeControls";
import {neutral as neutralMouth} from "../mouthShape/model";
import {EyeBagPreservePanel} from '../eyeBagPreserve/EyeBagPreservePanel';
import {EyeLightPanel} from '../eyeLight/EyeLightPanel';
import {EyeSymmetryControl} from '../eyeSymmetry/EyeSymmetryControl';
import {EyeShapeControls} from "../eyeShape/EyeShapeControls";
import {neutral as neutralEyes} from "../eyeShape/model";
import {withoutCoveredLeaves} from "../toolRouting/coverage";
import {SemanticColourWorkflowLaunch} from '../semanticColour/workflowLaunch';
import {revealTool,type ToolLocation} from "../toolRouting/RetouchToolActivity";
import {NoseShapeControls} from "../noseShape/NoseShapeControls";
import {neutral as neutralNose} from "../noseShape/model";
import {BrowShapeControls} from "../browShape/BrowShapeControls";
import {neutral as neutralBrows} from "../browShape/model";
import {LipMakeupControls} from "../lipMakeup/LipMakeupControls";
import {neutral as neutralLips} from "../lipMakeup/model";
import { FacialWrinkleControl } from "../facialWrinkles/FacialWrinkleControl";
import type { Region as WrinkleRegion } from "../facialWrinkles/model";
import { EyeHighlightsControl } from "./EyeHighlightsControl";
import {teethColourReadiness, TEETH_CONTROL_IDS} from '../teethColour/model';
import {redEyeReadiness, RED_EYE_CONTROL_ID} from '../redEye/model';
import {ScleraPurifyControl} from '../scleraPurify/ScleraPurifyControl';
import {SkinColourControl} from '../skinColour/SkinColourControl';
import {SkinFinishControl} from '../skinFinish/SkinFinishControl';
import {SkinGlossControl} from '../skinGloss/SkinGlossControl';
import {SkinTextureControl} from '../skinTexture/SkinTextureControl';
import {LipTextureControl} from '../lipTexture/LipTextureControl';
import {SkinEvennessControl} from '../skinEvenness/SkinEvennessControl';
import {BodySkinEvennessControl} from '../bodySkinEvenness/BodySkinEvennessControl';
import {CollarboneControl} from '../collarbone/CollarboneControl';
import {BodyFaceMatchControl} from '../bodyFaceMatch/BodyFaceMatchControl';
import {FaceContourControl} from '../faceContour/FaceContourControl';
import {FaceStylePanel} from '../faceStyle/FaceStylePanel';
import {SlimFaceControl} from '../slimFace/SlimFaceControl';
import {FaceSizeControl} from '../faceSize/FaceSizeControl';
import {MidFaceControl} from '../midFace/MidFaceControl';
import {PhiltrumControl} from '../philtrum/PhiltrumControl';
import {LowerFaceControl} from '../lowerFace/LowerFaceControl';
import {ChinLengthControl, LegacySmallChinControl} from '../chinLength/ChinLengthControl';
import {ChinShapeControl} from '../chinShape/ChinShapeControl';
import {BrowEnhanceControl} from '../browEnhance/BrowEnhanceControl';
import {ColorActionLaunch,type ColorActionControlsProps} from '../colorActions/ColorActionControls';
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
import { createContext, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  runLipMakeup, runCrop, runDeform, runEnhance, runExposure, runGrade,
  runHistory, runHsl, runLut, setStrength,
  type DocState, type EngineStatus,
} from "../native";
import {
  FEATURES, SPEC_COUNTS, buildTree, type SpecFeature, type SpecNode,
  type SpecSubcontrol,
} from "../spec";
import { DisabledRow, SpecNodes } from "./SpecTree";
import { skinLimits, skinSliderBounds100 } from "../gradeLimits";

export type BrushMode = "heal" | "dodge" | "burn" | "color";

export interface RetouchProps {
  toolLocation?: ToolLocation | null;
  effectRecoveryPanel?: React.ReactNode; manualLiquifyPanel?: React.ReactNode;
  studioBackgroundPanel?: React.ReactNode; skyReplacementPanel?: React.ReactNode; opticsPanel?: React.ReactNode;
  commonBackgroundOwner?: CommonBackgroundOwner;
  fringeRepairOwner?: FringeRepairOwner;
  presetPanel?: React.ReactNode;
  sampleLibraryPanel?: React.ReactNode;
  shoulderPanel?: React.ReactNode;
  expressionPanel?: React.ReactNode;
  hairUnificationPanel?: React.ReactNode;
  hairVolumePanel?: React.ReactNode;
  hairWorkflowBusy?: boolean;
  skinReferencePanel?: React.ReactNode;
  skinReferenceBodyPanel?: React.ReactNode;
  neckWrinklePanel?: React.ReactNode;
  hairPort: HairPort;
  hairBusy: boolean;
  refreshHair: () => Promise<void>;
  whiteBalancePanel?: React.ReactNode;
  whiteBalanceBusy?: boolean;
  colorSamplePanel?: React.ReactNode;
  blushMakeupPanel?: React.ReactNode;
  eyelinerPanel?: React.ReactNode;
  eyelashPanel?: React.ReactNode;
  irisMakeupPanel?: React.ReactNode;
  browMakeupPanel?: React.ReactNode;
  lipstickPanel?: React.ReactNode;
  colorActions?: ColorActionControlsProps;
  healBrushPanel?: React.ReactNode;sourcePatchPanel?: React.ReactNode;cloneStampPanel?: React.ReactNode;localMasksPanel?: React.ReactNode;
  status: EngineStatus | null;
  doc: DocState | null;
  hasImage: boolean;
  faceOk: boolean;
  faceWhy: string;
  note: (s: string) => void;
  onDone: () => void;
  /** 当前文档缩略图（JPEG base64）：人脸 chip 与 LUT 卡片的真实预览 */
  thumb?: string;
  people: PeopleOwner;
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

const PortraitRevision = createContext<string>('');

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
  const authoritativeRevision = useContext(PortraitRevision);
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
  }, [props.value, authoritativeRevision]);

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
        onPointerUp={() => { dragging.current = false; if(authoritativeRevision){setLocal(props.value);setText(fmt(props.value));} }}
        onPointerCancel={() => { dragging.current = false; setLocal(props.value);setText(fmt(props.value)); }}
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
  slim_face: "旧版瘦脸（历史错误拓扑）",
  big_eye: "大眼",
  small_chin: "小下巴",
  smile: "微笑",
};

/** 已接通的控制：键是「功能族 ID|规格 path」，值是面板里的分派名。
 *
 * 这张表只做一件事——把规格里的那一条路径指到引擎的一条真命令上。表里没有的
 * 一律静默置灰；表里有的但引擎拒了（例如没关键点时开瘦脸），错误照样从引擎回来，
 * 面板不提前放行。
 */
const WIRED: Record<string, string> = {
  // 眼睛对称：独立水平、大小及仅用于大小的参考眼。
  "PC-32470|眼睛对称": "eye_symmetry.family",
  "PC-32470|眼睛对称/水平对称": "eye_symmetry.horizontal",
  "PC-32470|眼睛对称/大小对称": "eye_symmetry.size",
  "PC-32470|眼睛对称/参考眼选择": "eye_symmetry.reference",
  "PC-32470|眼神光": "eye_light.family",
  "PC-32470|眼神光/程度": "eye_light.strength",
  "PC-32470|眼神光/垂直位置": "eye_light.vertical",
  "PC-32470|眼神光/水平位置": "eye_light.horizontal",
  "PC-32470|眼神光/旋转": "eye_light.rotation",
  "PC-32470|眼神光/水平翻转": "eye_light.flip",
  "PC-32466|嘴巴": "mouth.family",
  "PC-32466|嘴巴/大小": "mouth.size",
  "PC-32466|嘴巴/嘴宽": "mouth.width",
  "PC-32466|嘴巴/上下": "mouth.vertical",
  "PC-32466|嘴巴/左右": "mouth.horizontal",
  "PC-32466|嘴巴/露龈调整": "mouth.gummy",
  "PC-32466|嘴巴/M唇": "mouth.m_lip",
  "PC-32466|嘴巴/倾斜": "mouth.tilt",
  "PC-32466|嘴巴/丰上唇": "mouth.upper",
  "PC-32466|嘴巴/丰下唇": "mouth.lower",
  "PC-32466|眼睛": "eye.family",
  "PC-32466|眼睛/整体大小": "eye.size",
  "PC-32466|眼睛/眼瞳大小": "eye.iris_size",
  "PC-32466|眼睛/眼高": "eye.height",
  "PC-32466|眼睛/眼宽": "eye.width",
  "PC-32466|眼睛/眼距": "eye.spacing",
  "PC-32466|眼睛/内眼角": "eye.inner_corner",
  "PC-32466|眼睛/外眼角": "eye.outer_corner",
  "PC-32466|眼睛/眼睑下至": "eye.lower_lid",
  "PC-32466|眼睛/倾斜": "eye.tilt",
  "PC-32466|眼睛/位置": "eye.position",
  "PC-32466|鼻子": "nose.family",
  "PC-32466|鼻子/大小": "nose.size",
  "PC-32466|鼻子/鼻高": "nose.height",
  "PC-32466|鼻子/左右": "nose.position",
  "PC-32466|鼻子/鼻梁": "nose.bridge",
  "PC-32466|鼻子/鼻翼": "nose.wing",
  "PC-32466|鼻子/鼻尖": "nose.tip",
  "PC-32466|眉毛": "brow.family",
  "PC-32466|眉毛/粗细": "brow.thickness",
  "PC-32466|眉毛/眉距": "brow.spacing",
  "PC-32466|眉毛/倾斜": "brow.tilt",
  "PC-32466|眉毛/形状": "brow.arch",
  "PC-32466|眉毛/位置": "brow.position",
  "PC-32466|眉毛/眉头长短": "brow.inner_length",
  "PC-32466|眉毛/眉尾长短": "brow.outer_length",

  "PC-32471|局部妆容/眼线": "eyeliner.family",
  "PC-32471|局部妆容/美瞳": "irisMakeup.family",
  "PC-32471|局部妆容/睫毛": "eyelash.family",
  "PC-32471|局部妆容/眼线/推荐颜色": "eyeliner.recommended",
  "PC-32471|局部妆容/睫毛/推荐颜色": "eyelash.recommended",
  "PC-32471|局部妆容/眼线/吸管": "eyeliner.eyedropper",
  "PC-32471|局部妆容/睫毛/吸管": "eyelash.eyedropper",
  "PC-32471|局部妆容/眼线/RGB": "eyeliner.rgb",
  "PC-32471|局部妆容/睫毛/RGB": "eyelash.rgb",
  "PC-32471|局部妆容/眼线/HEX": "eyeliner.hex",
  "PC-32471|局部妆容/睫毛/HEX": "eyelash.hex",
  "PC-32471|局部妆容/眼线/收藏颜色": "eyeliner.saved",
  "PC-32471|局部妆容/睫毛/收藏颜色": "eyelash.saved",
  "PC-32471|局部妆容/眉毛": "browMakeup.family",
  "PC-32471|局部妆容/眉毛/推荐颜色": "browMakeup.recommended",
  "PC-32471|局部妆容/眉毛/吸管": "browMakeup.eyedropper",
  "PC-32471|局部妆容/眉毛/RGB": "browMakeup.rgb",
  "PC-32471|局部妆容/眉毛/HEX": "browMakeup.hex",
  "PC-32471|局部妆容/眉毛/收藏颜色": "browMakeup.saved",
  "PC-32471|局部妆容/口红": "lipstick.family",
  "PC-32471|局部妆容/口红/推荐颜色": "lipstick.recommended",
  "PC-32471|局部妆容/口红/吸管": "lipstick.eyedropper",
  "PC-32471|局部妆容/口红/RGB": "lipstick.rgb",
  "PC-32471|局部妆容/口红/HEX": "lipstick.hex",
  "PC-32471|局部妆容/口红/收藏颜色": "lipstick.saved",
  "PC-32471|局部妆容/口红/缎面": "lipstick.satin",
  "PC-32471|局部妆容/口红/哑光": "lipstick.matte",
  "PC-32471|局部妆容/口红/奶油": "lipstick.cream",
  "PC-32471|局部妆容/口红/珠光": "lipstick.pearl",
  "PC-32471|局部妆容/口红/水光": "lipstick.water_gloss",
  "PC-32471|局部妆容/脸部装饰": "face_decoration.family",
  "PC-32471|局部妆容/腮红": "blush.family",
  "PC-32471|局部妆容/腮红/推荐颜色": "blush.recommended",
  "PC-32471|局部妆容/腮红/吸管": "blush.eyedropper",
  "PC-32471|局部妆容/腮红/RGB": "blush.rgb",
  "PC-32471|局部妆容/腮红/HEX": "blush.hex",
  "PC-32471|局部妆容/腮红/收藏颜色": "blush.saved",
  "PC-32471|唇妆增强": "lip.family",
  "PC-32471|眉毛增强": "brow_enhance.v1",
  "PC-32471|眼妆增强": "eye_makeup_enhance.family",
  "PC-32471|眼妆增强/饱和度": "eye_makeup_enhance.family",
  "PC-32471|眼妆增强/明度": "eye_makeup_enhance.family",
  "PC-32471|眼妆增强/立体度": "eye_makeup_enhance.family",
  "PC-32471|高光立体": "facial_sculpt.highlight",
  "PC-32471|阴影立体": "facial_sculpt.shadow",
  "PC-32471|唇妆增强/饱和度": "lip.saturation",
  "PC-32471|唇妆增强/明度": "lip.brightness",
  "PC-32471|唇妆增强/立体度": "lip.dimensionality",
  "PC-32464|面部祛瑕疵/唇纹修整": "lip_texture.amount",
  "PC-32464|面部祛纹": "wrinkle.family",
  "PC-32464|面部祛纹/祛抬头纹": "wrinkle.forehead",
  "PC-32464|面部祛纹/祛川字纹": "wrinkle.glabellar",
  "PC-32464|面部祛纹/祛眼周纹": "wrinkle.eye_area",
  "PC-32464|面部祛纹/祛鼻背纹": "wrinkle.nose",
  "PC-32464|面部祛纹/祛法令纹": "wrinkle.nasolabial",
  "PC-32464|面部祛纹/祛脸颊纹": "wrinkle.cheek",
  "PC-32464|面部祛纹/祛木偶纹": "wrinkle.marionette",
  "PC-32464|面部祛纹/祛嘴周纹": "wrinkle.mouth_surround",

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
  "PC-32455|色阶/吸管工具": "levels.control",
  "PC-32455|色阶/黑场吸管": "levels.control",
  "PC-32455|色阶/白场吸管": "levels.control",
  "PC-32455|曲线/曲线吸管": "curves.control",
  "PC-32455|HSL/HSL吸管": "color.picker",
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
  "PC-32465|AI肤色统一（脸部）": "skin_evenness.amount",
  "PC-32465|AI肤色统一（身体）": "body_skin_evenness.amount",
  "PC-32465|锁骨增强": "collarbone.amount",
  "PC-32465|肤色统一（身体）": "body_face_match.amount",
  "PC-32465|水润磨皮-脸部/身体": "skin.radius",
  "PC-32465|肤色色温": "skin_colour.temperature",
  "PC-32465|肤色色调": "skin_colour.tint",
  "PC-32465|肤色美白": "skin_finish.whitening",
  "PC-32465|皮肤红润": "skin_finish.rosiness",
  "PC-32465|皮肤质感/光泽度": "skin_gloss.amount",
  "PC-32465|皮肤质感/纹理度": "skin_texture.texture",
  "PC-32465|皮肤质感/清晰度": "skin_texture.clarity",
  // 面部重塑 / 表情
  "PC-32466|脸型/瘦脸": "slim_face.v2",
  "PC-32466|脸型/小脸": "face_size.amount",
  "PC-32466|脸型/中庭": "mid_face.amount",
  "PC-32466|脸型/人中": "philtrum.amount",
  "PC-32466|脸型/下庭": "lower_face.amount",
  "PC-32466|脸型/下巴长短": "chin_length.amount",
  "PC-32466|脸型/尖下巴": "chin_shape.v1",
  "PC-32466|脸型/太阳穴": "face_contour.temple",
  "PC-32466|脸型/颧骨": "face_contour.cheekbone",
  "PC-32466|脸型/下颌": "face_contour.jaw",

  "PC-32466|脸型/收下巴": "deform.small_chin",
  "PC-32466|脸型预设/经典": "deform.preset:经典",
  "PC-32466|脸型预设/幼态": "deform.preset:幼态",
  "PC-32466|脸型预设/英气": "deform.preset:英气",
  "PC-32468|微笑嘴角": "deform.smile",
  "PC-32464|面部祛瑕疵/祛黑眼圈": "enh.dark_circles",
  "PC-32464|面部祛瑕疵/祛眼袋": "eye_bag.family",
  "PC-32464|面部祛瑕疵/祛眼袋/保留卧蚕": "eye_bag.preserve",
  // 五官细节
  "PC-32470|亮眼/眼白": "enh.sclera",
  "PC-32470|亮眼/眼瞳": "enh.iris",
  "PC-32470|祛红血丝": "enh.veins",
  "PC-32470|眼白净化": "enh.sclera_purify",
  "PC-32470|祛红眼": "enh.red_eye",
  "PC-32470|亮眼/眼睛高光": "enh.catchlight",
  "PC-32469|牙齿美白": "enh.teeth",
  // The source specifies two independent child controls, not another alias of
  // the existing combined whitening amount. [0,1] is our local scalar range.
  "PC-32469|牙齿美白/明度": "enh.teeth_brightness",
  "PC-32469|牙齿美白/祛黄": "enh.teeth_yellow_removal",
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
  // 来源区域修补由独立 sourcePatchPanel 接入，不借 brush.heal；仿制图章由独立 cloneStampPanel 接入。
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
  "PC-32482|仿制图章": "仿制图章需要匹配版本的独立取样面板；来源区域修补不是仿制图章。",
};

/** 已接通格子的产品名：规格 path 的最后一段常常只是“身体/程度”，
 *  直接当滑杆名会让两行都叫“身体”。这里只改显示名，不改规格 path。 */
const WIRE_LABEL: Record<string, string> = {
  "skin.strength": "磨皮强度",
  "skin.detail": "质感保留",
  "skin.broad": "旧版大尺度频率增益（非肤色统一）",
  "skin.radius": "磨皮半径",
  "slim_face.v2": "瘦脸（新版左右独立）",
  "face_size.amount": "小脸（局部整脸大小）",
  "mid_face.amount": "中庭（局部纵向长度）",
  "philtrum.amount": "人中（鼻下至唇上局部间距）",
  "lower_face.amount": "下庭（局部纵向长度）",
  "chin_length.amount": "下巴长短（唇下局部纵向长度）",
  "chin_shape.v1": "尖下巴（局部横向收尖，左右独立）",
  "brow_enhance.v1": "眉毛增强（已有眉毛对比，左右独立）",
  "deform.slim_face": "旧版瘦脸（历史错误拓扑）",
  "deform.big_eye": "大眼",
  "deform.small_chin": "小下巴",
  "deform.smile": "微笑",
  "enh.dark_circles": "祛黑眼圈",
  "enh.eye_bags": "祛眼袋",
  "enh.sclera": "眼白提亮",
  "enh.iris": "眼瞳提亮",
  "enh.veins": "祛红血丝",
  "enh.sclera_purify": "眼白净化",
  "enh.red_eye": "祛红眼",
  "enh.catchlight": "眼睛高光",
  "enh.teeth": "牙齿美白",
  "enh.teeth_brightness": "牙齿明度",
  "enh.teeth_yellow_removal": "牙齿祛黄",
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

/** Historical lnx.deform.v1 recipes, including its known wrong slim-face topology.
 * Never reinterpret these strengths as lnx.slim_face.v2 or silently clear v2. */
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
  "PC-32474": "背景调整",
  "PC-32475": "证件照换底",
  "PC-32476": "换天空",
  "PC-32477": "衣物修饰",
  "PC-32452": "风格调色",
  "PC-32455": "色彩光影",
  "PC-32454": "局部调色",
  "PC-32479": "手动液化",
  "PC-32482": "修复工具",
  "PC-32481": "手动涂抹画笔",
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

export default function RetouchPanel(props: RetouchProps) {
  const { doc, status } = props;
  const dim = !props.hasImage||!!props.hairWorkflowBusy||props.hairPort.pending()||!!props.colorActions?.owner.pending||(props.people.state.pending && props.people.state.pendingAction !== 'patch')||props.people.state.uncertain;
  const capturedPeople = peopleContext(doc?.people);
  const skinReady = skinMaskReady(status?.precompute?.mask_channels, status?.precompute?.mask_nonzero_pixels);
  const skinWhy = skinReady ? "" : "尚无有效皮肤掩膜，请先完成人像分析";
  const params = doc?.params ?? {};
  const amounts = doc?.deform.amounts ?? {};
  const enhAmounts = doc?.enhance?.amounts ?? {};
  const teethCapability = doc?.enhance?.teeth_colour_available === undefined ? status?.enhance : doc?.enhance;
  const teethReady = teethColourReadiness(teethCapability);
  const redEyeCapability = doc?.enhance?.red_eye_available === undefined ? status?.enhance : doc?.enhance;
  const redEyeReady = redEyeReadiness(redEyeCapability);
  const ex = doc?.exposure;
  const grade = doc?.grade;
  // P2-3：肤色定向三条滑杆的量程来自引擎报的 grade_limits（不是前端写死 ±100）。
  // ×100 整数表示：dh→±5、ds/dv→±60，换算回后端单位正好落在 check_params 的有效带。
  const gradeBounds = skinSliderBounds100(skinLimits(status?.grade_limits));
  const presets = status?.presets ?? [];
  const [q, setQ] = useState("");
  const [toolGroup, setToolGroup] = useState<ToolGroup>("color");
  const contentRef = useRef<HTMLDivElement | null>(null);
  const scrollPositions = useRef<Partial<Record<ToolGroup, number>>>({});
  useLayoutEffect(() => {
    if (contentRef.current) contentRef.current.scrollTop = q.trim() ? 0 : (scrollPositions.current[toolGroup] ?? 0);
  }, [toolGroup, q]);
  const [openSeen, setOpenSeen] = useState<Record<string, boolean>>({});
  const [navigationTarget, setNavigationTarget] = useState<ToolLocation | null>(null);
  const navigateTool = (featureId: string, path?: string) => {
    setQ(""); setToolGroup(toolGroupOf(featureId) ?? "color");
    setOpenSeen(previous => ({...previous, [featureId]: true}));
    setNavigationTarget(previous => ({featureId,path,serial:(previous?.serial??0)+1}));
  };
  useLayoutEffect(() => {
    if (navigationTarget) revealTool(contentRef.current, navigationTarget.featureId, navigationTarget.path);
  }, [navigationTarget]);
  useEffect(() => {
    if (props.toolLocation) navigateTool(props.toolLocation.featureId, props.toolLocation.path);
    // A new serial permits locating the same tool twice; no workflow is restarted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.toolLocation]);
  // 八色 HSL 当前选中的色段（0…7）。这是**界面选择**，不是文档状态：切图后同一段
  // 继续被选中，引擎侧那 24 个数才是画面事实。
  const [hslBand, setHslBand] = useState(0);
  const hslNames = doc?.hsl?.names ?? HSL_BANDS;

  const trees = useMemo(
    () => FEATURES.map((f) => ({ f, tree: buildTree(f.subcontrols) })),
    [],
  );

  const commitSkin = (patch: SkinEdit) => {
    if (!doc || dim || props.people.state.pending || props.people.state.uncertain) return;
    if (skinWhy) { props.note(skinWhy); return; }
    ok(setStrength(patch.strength, skinEditOptions(patch)), props);
  };

  const commitPeopleLeaves = (patches: ParameterPatch[]) => {
    try {props.people.patch(patches);} catch (error) {props.note(String(error));}
  };
  const scalarLeaves = (operation: string, values: Record<string, number>): ParameterPatch[] =>
    Object.entries(values).map(([key, value]) => ({operation_id: operation, parameter_path: `/${key}`, unset: false, value}));
  const commitDeform = (patch: Record<string, number>) => {
    if (doc?.people) {commitPeopleLeaves(scalarLeaves('lnx.deform.v1', patch)); return;}
    ok(runDeform("set", patch, undefined, capturedPeople), props);
  };

  const commitEnhance = (patch: Record<string, number>) => {
    if (doc?.people) {
      commitPeopleLeaves(Object.entries(patch).map(([key, value]) => ({operation_id: key.startsWith('wrinkle_')
        ? 'lnx.facial_wrinkles.v1' : 'lnx.enhance.v1', parameter_path: `/${key}`, unset: false, value}))); return;
    }
    ok(runEnhance("set", patch, capturedPeople), props);
  };

  const commitExposure = (patch: Record<string, number>) =>
    ok(runExposure("set", patch, true), props);

  const rotateBy = (delta: number) => {
    const cur = doc?.crop?.rotation_degrees ?? 0;
    let next = cur + delta;
    if (next > 180) next -= 360;
    if (next < -180) next += 360;
    ok(runCrop("set", doc?.crop?.rect ?? [0, 0, 1, 1], next), props);
  };

  const lutOn = !!doc?.lut.lit;
  const lutAmt = doc?.lut.amount ?? 1;
  const gradeScopes = grade?.scopes ?? ["all", "skin"];
  const maskPx = grade?.mask_px ?? 0;

  const brushOn = props.brush.on;
  const brushMode = props.brush.mode;

  /** 已接通叶子的实际控件。`name` 是规格 path 的最后一段。 */
  const renderWired = (leaf: SpecSubcontrol, name: string,
                       kind: string): React.ReactNode => {
    const label = WIRE_LABEL[kind] ?? name;
    if (kind === "mouth.family") return <MouthShapeControls key={leaf.path} value={doc?.mouth_shape?.recipe??neutralMouth()}
      facts={doc?.mouth_shape?.controls} disabled={dim||!props.faceOk||!!props.whiteBalanceBusy||status?.ready_caps?.mouth_shape_protocol!==2}
      why={props.faceOk?(doc?.mouth_shape?.native_available===false?"嘴形 Rust 核心不可用，调整会明确拒绝；仍可重置旧参数。请使用完整打包版本。":doc?.mouth_shape?.suspended??undefined):props.faceWhy}
      legacy={doc?.mouth_shape?.legacy_smile??amounts.smile??0}
      documentId={doc?.document_id??""} faceId={doc?.mouth_shape?.selected_face_id??""} revision={doc?.mouth_shape?.revision??0} peopleContext={capturedPeople}/>;
    if (kind.startsWith("mouth.")) return null;
    if (kind === "eye_bag.family") return <div key={leaf.path}>
      <EyeBagPreservePanel people={props.people} faceOk={props.faceOk}
        coreAvailable={status?.ready_caps?.eye_bags_protocol===2}
        blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy() || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}/>
      <details><summary>旧版祛眼袋（保留原值与原行为，不含新版卧蚕保护）</summary>
        <p>旧配方不会自动迁移。新版生效时不要叠加旧版眼袋处理；切换必须明确审核替换。</p>
        <Slider label="旧版祛眼袋" value={Math.round((enhAmounts.eye_bags ?? 0) * 100)} min={0} max={100}
          disabled={dim || !props.faceOk || props.people.state.pending || props.people.state.uncertain}
          onChange={v => commitEnhance({eye_bags: v / 100})} onReset={() => commitEnhance({eye_bags: 0})}/>
      </details>
    </div>;
    if (kind.startsWith("eye_bag.")) return null;
    if (kind === "eye_light.family") return <EyeLightPanel key={leaf.path} people={props.people} blocked={dim||props.hairBusy||!!props.whiteBalanceBusy||status?.ready_caps?.eye_light_protocol!==1}/>;
    if (kind.startsWith("eye_light.")) return null;
    if (kind === "eye_symmetry.family") {
      if (!doc?.people) return <section key={leaf.path} data-control-id="LNX-REF-PC-32470-C-2745ac86f5" aria-label="眼睛对称暂不可用">
        <p className="muted">此文档尚未提供规范人物状态，眼睛对称暂不可用。不会改用眼形大小、眼球调整、旧版大眼或像素镜像替代。</p>
      </section>;
      return <EyeSymmetryControl key={leaf.path}
        people={props.people} capability={status?.ready_caps}
        blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
          || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
        faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
    }
    if (kind.startsWith("eye_symmetry.")) return null;
    if (kind === "eye.family") return <EyeShapeControls key={leaf.path} value={doc?.eye_shape?.recipe??neutralEyes()}
      facts={doc?.eye_shape?.controls} disabled={dim||!props.faceOk||!!props.whiteBalanceBusy||status?.ready_caps?.eye_shape_protocol!==2}
      why={props.faceOk?(doc?.eye_shape?.native_available===false?"眼形 Rust 核心未安装；调整会明确拒绝，请使用完整打包版本。":doc?.eye_shape?.suspended??undefined):props.faceWhy}
      legacy={doc?.eye_shape?.legacy_big_eye??amounts.big_eye??0} clearLegacy={()=>commitDeform({big_eye:0})}
      documentId={doc?.document_id??""} faceId={doc?.eye_shape?.selected_face_id??""} revision={doc?.eye_shape?.revision??0} peopleContext={capturedPeople}/>;
    if (kind.startsWith("eye.")) return null;
    if (kind === "nose.family") return <NoseShapeControls key={leaf.path} value={doc?.nose_shape?.recipe??neutralNose()}
      facts={doc?.nose_shape?.controls} disabled={dim||!props.faceOk||!!props.whiteBalanceBusy||status?.ready_caps?.nose_shape_protocol!==2}
      why={props.faceOk?(doc?.nose_shape?.suspended??undefined):props.faceWhy}
      documentId={doc?.document_id??""} faceId={doc?.nose_shape?.selected_face_id??""} revision={doc?.nose_shape?.revision??0} peopleContext={capturedPeople}/>;
    if (kind.startsWith("nose.")) return null;
    if (kind === "brow.family") return <BrowShapeControls key={leaf.path} value={doc?.brow_shape?.recipe??neutralBrows()}
      facts={doc?.brow_shape?.sides} disabled={dim||!props.faceOk||!!props.whiteBalanceBusy||status?.ready_caps?.brow_shape_protocol!==2}
      why={props.faceOk?(doc?.brow_shape?.suspended??undefined):props.faceWhy}
      documentId={doc?.document_id??""} faceId={doc?.brow_shape?.selected_face_id??""} revision={doc?.brow_shape?.revision??0} peopleContext={capturedPeople}/>;
    if (kind.startsWith("brow.")) return null;
    if (kind === "eyeliner.family") return <div key={leaf.path}>{props.eyelinerPanel}</div>;
    if (kind === "irisMakeup.family") return <div key={leaf.path}>{props.irisMakeupPanel}</div>;
    if (kind === "eyelash.family") return <div key={leaf.path}>{props.eyelashPanel}</div>;
    if (kind.startsWith("eyeliner.")) return null;
    if (kind.startsWith("eyelash.")) return null;
    if (kind === "browMakeup.family") return <div key={leaf.path}>{props.browMakeupPanel}</div>;
    if (kind.startsWith("browMakeup.")) return null;
    if (kind === "lipstick.family") return <div key={leaf.path}>{props.lipstickPanel}</div>;
    if (kind.startsWith("lipstick.")) return null;
    if (kind === 'eye_makeup_enhance.family') return <EyeMakeupEnhanceControl key={leaf.path}
      people={props.people} capability={status?.ready_caps} faceOk={props.faceOk} faceWhy={props.faceWhy}
      note={props.note} Slider={Slider} blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
        || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}/>;
    if (kind === 'facial_sculpt.highlight' || kind === 'facial_sculpt.shadow') return <FacialSculptPanel key={leaf.path}
      people={props.people} capability={status?.ready_caps} faceOk={props.faceOk} faceWhy={props.faceWhy}
      control={kind==='facial_sculpt.highlight'?'highlight':'shadow'}
      blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
        || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}/>;
    if (kind === "face_decoration.family") return <FaceDecorationPanel key={leaf.path} people={props.people}
      capability={status?.ready_caps} faceOk={props.faceOk} faceWhy={props.faceWhy}
      blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
        || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}/>;
    if (kind === "blush.family") return <div key={leaf.path}>{props.blushMakeupPanel}</div>;
    if (kind.startsWith("blush.")) return null;
    if (kind === "lip.family") return <LipMakeupControls key={leaf.path} value={doc?.lip_makeup?.recipe??neutralLips()}
      fact={doc?.lip_makeup?.facts} disabled={dim||!props.faceOk||!!props.whiteBalanceBusy||status?.ready_caps?.lip_makeup_protocol!==1}
      reason={props.faceOk?(doc?.lip_makeup?.suspended??undefined):props.faceWhy}
      commit={(recipe,control)=>{
        if (doc?.people) {
          const keys = control === undefined ? ['saturation','brightness','dimensionality'] as const : [control];
          commitPeopleLeaves(keys.map(key=>({operation_id:'lnx.lip_makeup.v1',parameter_path:`/${key}`,unset:false,value:recipe[key]})));
        } else if (doc?.document_id) ok(runLipMakeup(recipe,doc.document_id,control,capturedPeople),props);
      }} Slider={Slider}/>;
    if (kind.startsWith("lip.")) return null;
    if (kind === "wrinkle.family") return <p key={leaf.path} className="muted"
      data-control-id="PC-32464-C-d9e8e03577">八个部位独立调节；法令纹可左右联动或解锁。只淡化线状细纹，保留五官与皮肤纹理。</p>;
    if (kind.startsWith("wrinkle.")) return <FacialWrinkleControl key={leaf.path}
      region={kind.slice("wrinkle.".length) as WrinkleRegion} amounts={enhAmounts}
      facts={doc?.enhance?.facial_wrinkles}
      disabled={dim || !props.faceOk} reason={props.faceOk ? undefined : props.faceWhy}
      commit={commitEnhance} Slider={Slider} />;

    if (kind.startsWith("deform.preset:")) {
      const preset = kind.split(":")[1];
      return (
        <details key={leaf.path}><summary>明确打开旧版{name}预设（历史兼容）</summary>
        <button type="button" className="specBtn"
          title={`历史脸型预设：${name}。保留旧版瘦脸、小下巴数值及错误拓扑；与新版瘦脸或新版下巴长短的非零效果冲突时引擎会拒绝整个请求，不会自动替换。`}
          disabled={dim || !props.faceOk}
          onClick={() => {
            setOpenSeen((s) => ({ ...s, [preset]: true }));
            commitDeform(SHAPE_PRESETS[preset] ?? {});
          }}>
          <b>{name}</b><em>历史预设 · 旧版瘦脸</em>
        </button></details>
      );
    }
    switch (kind) {
      case "lip_texture.amount":
        return <LipTextureControl key={leaf.path}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "histogram.control": return null;
      case "levels.control": return null;
      case "color.picker": return null; // real targeted control lives with its tool group
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
      case "skin_evenness.amount": {
        // The former alias had the only broad-gain route. Keep an explicit legacy route,
        // with its original parameters and command, rather than migrating or hiding saved values.
        const legacyDisabled = !doc || dim || !!skinWhy || props.people.state.pending || props.people.state.uncertain;
        return <div key={leaf.path}>
          <SkinEvennessControl
            people={props.people} capability={status?.ready_caps}
            blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
              || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
            faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>
          <details data-legacy-skin-compat="true">
            <summary>旧版磨皮兼容控制（照片级参数，非脸部色度均匀）</summary>
            <p className="muted">以下保留当前照片的旧版磨皮强度与大尺度频率增益，不随人物编辑范围切换；旧流程使用整张照片的皮肤掩膜。它们不是新的脸部色度均匀，也不进行参数迁移、换算或自动清除。</p>
            <Slider label="旧版照片级磨皮强度（皮肤掩膜）"
              value={Math.round((doc?.strength ?? 0) * 100)} min={0} max={100}
              disabled={legacyDisabled} title={skinWhy || '旧版磨皮强度；0 关闭旧磨皮。双击恢复旧版默认值 0。'}
              onChange={value => commitSkin({ strength: value / 100 })}
              onReset={() => commitSkin({ strength: 0 })}/>
            <Slider label="旧版大尺度频率增益（0 至 2，非肤色统一）"
              value={params.broad_gain ?? 0} min={0} max={2} step={0.01} digits={2}
              disabled={legacyDisabled} title={skinWhy || '旧版频率增益；0 是旧默认值，不是中性。双击恢复旧版默认值 0。'}
              onChange={value => commitSkin({ broad: value })}
              onReset={() => commitSkin({ broad: 0 })}/>
            <p className="muted">旧版强度 0 关闭旧磨皮；大尺度增益 0 只是旧默认值，不代表中性或关闭。两项均沿用旧版渲染与保存含义，不受上方新功能归零按钮影响。</p>
            <button type="button" className="specBtn" disabled={legacyDisabled}
              onClick={() => commitSkin({ strength: 0 })}>恢复旧版强度默认值（0，关闭旧磨皮）</button>
            <button type="button" className="specBtn" disabled={legacyDisabled}
              onClick={() => commitSkin({ broad: 0 })}>恢复旧版大尺度增益默认值（0，非中性）</button>
            {skinWhy && <p className="muted" role="status">{skinWhy}</p>}
            <p className="muted">人物修改正在处理或结果尚未确认时，旧版控制也会暂停。旧版命令仍保留自身限制；不支持的衍生来源路径仍会拒绝，不通过新功能绕过。</p>
          </details>
        </div>;
      }
      case "body_skin_evenness.amount":
        return <BodySkinEvennessControl key={leaf.path}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "collarbone.amount":
        return <CollarboneControl key={leaf.path}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "body_face_match.amount":
        return <BodyFaceMatchControl key={leaf.path}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "skin_colour.temperature":
      case "skin_colour.tint":
        return <SkinColourControl key={leaf.path}
          control={kind === 'skin_colour.temperature' ? 'temperature' : 'tint'}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "skin_finish.whitening":
      case "skin_finish.rosiness":
        return <SkinFinishControl key={leaf.path}
          control={kind === 'skin_finish.whitening' ? 'whitening' : 'rosiness'}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "skin_gloss.amount":
        return <SkinGlossControl key={leaf.path}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "skin_texture.texture":
      case "skin_texture.clarity":
        return <SkinTextureControl key={leaf.path}
          control={kind === 'skin_texture.texture' ? 'texture' : 'clarity'}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "face_size.amount":
        if (!doc?.people) return <section key={leaf.path} data-control-id="LNX-REF-PC-32466-C-728fc62cdd" aria-label="小脸暂不可用">
          <p className="muted">此文档尚未提供规范人物状态，小脸暂不可用。不会改用整张图像缩放、旧版瘦脸或五官大小替代。</p>
        </section>;
        return <FaceSizeControl key={leaf.path}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "mid_face.amount":
        if (!doc?.people) return <section key={leaf.path} data-control-id="LNX-REF-PC-32466-C-ea67c9d99f" aria-label="中庭暂不可用">
          <p className="muted">此文档尚未提供规范人物状态，中庭暂不可用。不会改用下庭、小脸、收下巴、下巴长短或短脸替代。</p>
        </section>;
        return <MidFaceControl key={leaf.path}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "lower_face.amount":
        if (!doc?.people) return <section key={leaf.path} data-control-id="LNX-REF-PC-32466-C-1ae8316994" aria-label="下庭暂不可用">
          <p className="muted">此文档尚未提供规范人物状态，下庭暂不可用。不会改用小脸、收下巴、下巴长短或短脸替代。</p>
        </section>;
        return <LowerFaceControl key={leaf.path}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "chin_shape.v1":
        if (!doc?.people) return <section key={leaf.path} data-control-id="LNX-REF-PC-32466-C-ed7837df9a" aria-label="尖下巴暂不可用">
          <p className="muted">此文档尚未提供规范人物状态，尖下巴暂不可用。不会改用旧版小下巴、收下巴、下巴长短、下庭、瘦脸或下颌替代。</p>
        </section>;
        return <ChinShapeControl key={leaf.path}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "brow_enhance.v1":
        if (!doc?.people) return <section key={leaf.path} data-control-id="LNX-REF-PC-32471-C-18765fa8ea" aria-label="眉毛增强暂不可用">
          <p className="muted">此文档尚未提供规范人物状态，眉毛增强暂不可用。不会改用眉妆素材、眉形变形或通用曝光替代。</p>
        </section>;
        return <BrowEnhanceControl key={leaf.path}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "chin_length.amount":
        if (!doc?.people) return <section key={leaf.path} data-control-id="LNX-REF-PC-32466-C-44a42baef4" aria-label="下巴长短暂不可用">
          <p className="muted">此文档尚未提供规范人物状态，下巴长短暂不可用。不会改用旧版小下巴、收下巴、下庭、中庭或尖下巴替代；旧效果保留不变。</p>
        </section>;
        return <ChinLengthControl key={leaf.path}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "philtrum.amount":
        if (!doc?.people) return <section key={leaf.path} data-control-id="LNX-REF-PC-32466-C-2605502c27" aria-label="人中暂不可用">
          <p className="muted">此文档尚未提供规范人物状态，人中暂不可用。不会改用嘴巴上下位置、中庭、下庭、下巴长短或尖下巴替代；其他效果保留不变。</p>
        </section>;
        return <PhiltrumControl key={leaf.path}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "face_contour.temple":
      case "face_contour.cheekbone":
      case "face_contour.jaw":
        return <FaceContourControl key={leaf.path}
          control={kind === 'face_contour.temple' ? 'temple' : kind === 'face_contour.cheekbone' ? 'cheekbone' : 'jaw'}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "slim_face.v2":
        if (!doc?.people) return <section key={leaf.path} aria-label="旧版瘦脸兼容编辑">
          <p className="muted">此文档尚未提供规范人物状态，新版左右独立瘦脸暂不可用。以下仅编辑保存的旧版配方，不会自动升级或换算。</p>
          <p className="muted">旧版右侧控制点列表含非面部椭圆点和嘴唇点，属于历史错误拓扑；这里只为旧作品的外观兼容保留，不代表与新版同等正确。</p>
          {Number.isFinite(amounts.slim_face) && Math.abs(amounts.slim_face) <= 1
            ? <Slider label="旧版瘦脸（历史错误拓扑）" value={amounts.slim_face * 100} min={-100} max={100}
                disabled={dim || !props.faceOk || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
                  || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
                title={props.faceOk ? '保留旧版数值含义，不转换为新版瘦脸。' : props.faceWhy}
                onChange={value => commitDeform({slim_face: value / 100})}
                onReset={() => commitDeform({slim_face: 0})}/>
            : <p className="muted">引擎尚未提供有效的旧版瘦脸读数，不以 0 代替。</p>}
        </section>;
        return <SlimFaceControl key={leaf.path}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
      case "deform.small_chin":
        if (doc?.people) return <LegacySmallChinControl key={leaf.path}
          people={props.people} capability={status?.ready_caps}
          blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
            || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
          faceOk={props.faceOk} faceWhy={props.faceWhy} note={props.note} Slider={Slider}/>;
        return <section key={leaf.path} aria-label="旧版小下巴兼容编辑">
          <p className="muted">这里只编辑保存的旧版小下巴，历史错误拓扑与原数值保留；不会自动换算成新版下巴长短。</p>
          {Number.isFinite(amounts.small_chin) && amounts.small_chin >= 0 && amounts.small_chin <= 1
            ? <Slider label={label} value={amounts.small_chin * 100} min={0} max={100}
                disabled={dim || !props.faceOk || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
                  || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
                title={props.faceOk ? '保留旧版小下巴数值与原行为。' : props.faceWhy}
                onChange={value => commitDeform({small_chin: value / 100})} onReset={() => commitDeform({small_chin: 0})}/>
            : Number.isFinite(amounts.small_chin) && amounts.small_chin >= -1 && amounts.small_chin < 0
              ? <>
                  <p className="muted">已保存的旧版小下巴实际值：{Number((amounts.small_chin * 100).toFixed(6))}。此负值保持原样，不夹到原有 0 至 100 滑杆的范围内，也不换算成新版。</p>
                  <button type="button" className="specBtn"
                    disabled={dim || !props.faceOk || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
                      || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}
                    onClick={() => commitDeform({small_chin: 0})}>仅归零保存的旧版小下巴</button>
                </>
              : <p className="muted">引擎尚未提供有效的旧版小下巴读数，不以 0 代替。</p>}
        </section>;
      case "deform.big_eye":
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
      case "enh.teeth_brightness":
      case "enh.teeth_yellow_removal": {
        const key = kind === 'enh.teeth_brightness' ? 'teeth_brightness' : 'teeth_yellow_removal';
        const reason = !props.faceOk ? props.faceWhy : teethReady.reason
          ?? doc?.enhance?.reason?.[key] ?? status?.enhance?.enhance_reason?.[key] ?? undefined;
        return <div key={leaf.path} data-control-id={TEETH_CONTROL_IDS[key]}>
          <Slider label={label} value={Math.round((enhAmounts[key] ?? 0) * 100)} min={0} max={100}
            disabled={dim || !props.faceOk || !teethReady.available}
            title={reason ?? (key === 'teeth_brightness' ? '调整已有牙齿的明度，保留纹理与高光' : '只降低已有牙齿的黄色偏色，不漂白其它颜色')}
            onChange={(v) => commitEnhance({ [key]: v / 100 })}
            onReset={() => commitEnhance({ [key]: 0 })} />
          {reason && <p className="muted" role="status">{reason}</p>}
          {key === 'teeth_brightness' && !teethReady.available
            && ((enhAmounts.teeth_brightness ?? 0) > 0 || (enhAmounts.teeth_yellow_removal ?? 0) > 0)
            && <button type="button" className="specBtn"
              disabled={dim || props.people.state.pending || (doc?.people ? !capturedPeople : !doc)}
              title="只归零当前编辑范围的明度与祛黄；保留旧版美白及其他参数，无需缺失的调整核心"
              onClick={() => commitEnhance({teeth_brightness: 0, teeth_yellow_removal: 0})}>重置独立牙齿调整</button>}
        </div>;
      }
      case "enh.sclera_purify":
        return <ScleraPurifyControl key={leaf.path} amount={enhAmounts.sclera_purify ?? 0}
          capability={doc?.enhance?.sclera_purify_available === undefined ? status?.enhance : doc?.enhance}
          disabled={dim} faceOk={props.faceOk} faceWhy={props.faceWhy}
          reason={doc?.enhance?.reason?.sclera_purify ?? status?.enhance?.enhance_reason?.sclera_purify}
          resetDisabled={dim || props.people.state.pending || (doc?.people ? !capturedPeople : !doc)}
          commit={commitEnhance} Slider={Slider} />;
      case "enh.red_eye": {
        const reason = !props.faceOk ? props.faceWhy : redEyeReady.reason
          ?? doc?.enhance?.reason?.red_eye ?? status?.enhance?.enhance_reason?.red_eye ?? undefined;
        return <div key={leaf.path} data-control-id={RED_EYE_CONTROL_ID}>
          <p className="muted">仅校正中央虹膜内明显偏红像素，不是瞳孔分割。红棕虹膜、美瞳或彩色反光可能误判，请对比原图；不会重建眼睛。</p>
          <Slider label={label} value={Math.round((enhAmounts.red_eye ?? 0) * 100)} min={0} max={100}
            disabled={dim || !props.faceOk || !redEyeReady.available}
            title={reason ?? '减轻闪光造成的瞳孔红色偏光；与眼白红血丝和眼瞳提亮独立'}
            onChange={(v) => commitEnhance({red_eye: v / 100})}
            onReset={() => commitEnhance({red_eye: 0})} />
          {reason && <p className="muted" role="status">{reason}</p>}
          {(enhAmounts.red_eye ?? 0) > 0 && <button type="button" className="specBtn"
            disabled={dim || props.people.state.pending || (doc?.people ? !capturedPeople : !doc)}
            title="只归零当前编辑范围的祛红眼参数；保留眼白红血丝、眼瞳提亮及其他参数，无需缺失的调整核心"
            onClick={() => commitEnhance({red_eye: 0})}>重置祛红眼</button>}
        </div>;
      }
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
            onChange={(v) => ok(runLut("amount", { amount: v / 100 }), props)}
            onReset={() => ok(runLut("amount", { amount: 0 }), props)} />
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
    if (featureId === "PC-32455" && props.opticsPanel && node.full === "镜头调整")
      return <div data-tool-anchor="镜头调整">{props.opticsPanel}</div>;
    if (featureId === "PC-32455" && props.opticsPanel && node.full === "透视矫正")
      return <div data-tool-anchor="透视矫正" className="toolRouteNote"><button className="toolRouteLink" onClick={()=>navigateTool("PC-32455","镜头调整")}>前往镜头与透视调整</button><p>自动透视启用、智能/水平/垂直模式、手动微调与引导线使用同一个编辑器；自动分析基于真实线段与几何解算。</p></div>;
    if(featureId==="PC-32455"&&node.full==="白平衡")return props.whiteBalancePanel;
    if(featureId==="PC-32455"&&node.full==="直方图")return <HistogramPanel
      key={status?.image?.load_id??"empty"} documentId={status?.image?.load_id??""} snapshotId={doc?.document_id}
      revision={status?.doc_rev??-1} result={status?.color_scopes} disabled={!props.hasImage||status?.ready_caps?.color_scopes_protocol!==1} onDone={props.onDone}/>;
    if (featureId === "PC-32455" && node.full === "色阶") return <LevelsEditor
      key={status?.image?.load_id??"empty"} value={doc?.levels} documentId={status?.image?.load_id??""}
      snapshotId={doc?.document_id} documentRevision={status?.doc_rev??-1}
      disabled={!props.hasImage||!!props.colorActions?.owner.pending} result={status?.levels_result} onDone={props.onDone} note={props.note} picker={props.colorActions}/>;
    if (featureId === "PC-32455" && node.full === "曲线") return <CurveEditor
      key={status?.image?.load_id ?? status?.image?.doc ?? "empty"} value={doc?.curves}
      documentId={status?.image?.load_id??""} snapshotId={doc?.document_id} documentRevision={status?.doc_rev??-1}
      disabled={!props.hasImage||!!props.colorActions?.owner.pending} parametricSupported={status?.ready_caps?.curve_recipe_versions?.includes(3)===true} result={status?.curve_result} error={status?.last_error??null} onDone={props.onDone} note={props.note} picker={props.colorActions}/>;
    if (node.full !== "HSL") return null;
    return (
      <div key="hsl-chips">{props.colorActions&&<div className="colorActionToolbar"><ColorActionLaunch {...props.colorActions} action="hsl"/>
        <small>图像取样后左右拖动定向色相。读数为 HSL，八色渲染仍为 HSV 算子。</small></div>}
      <div className="hslChips" data-hsl-band={hslBand}>
        {HSL_BANDS.map((n, i) => (
          <button key={n} title={`${n}色`}
            className={"hslChip" + (i === hslBand ? " on" : "")}
            style={{ background: HSL_CHIP_COLORS[i] }}
            onClick={() => setHslBand(i)}>{n}</button>
        ))}
        <button className="hslChip reset" title="八段全部归零" disabled={dim}
          onClick={() => ok(runHsl("clear"), props)}>归零</button>
      </div></div>
    );
  };

  /** 已接通祖先链：默认展开，别让真控件埋在折叠里。 */
  const openPathsFor = (f: SpecFeature): Set<string> => {
    const open = new Set<string>();
    if(f.id === "PC-32455") {open.add("曲线");open.add("色阶");if(props.opticsPanel)open.add("镜头调整");if(navigationTarget?.path)open.add(navigationTarget.path);}
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
            onClick={() => ok(runLut("set", { preset: p.name, amount: lutAmt }), props)}>
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

      </div>
    </>
  );

  const gradeBlock = (
    <div className="specBlock">
      <div className="specBlockTitle">局部调色</div>
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
        {(["all", "skin", "brush", "objects"] as const).map((s) => {
          const on = (grade?.scope ?? "all") === s;
          const off = s === "brush" && maskPx === 0;
          return (
            <button key={s} className={on ? "on" : ""}
              disabled={dim || !gradeScopes.includes(s) || off || s === "objects"}
              title={off ? "先用「局部调色笔」在画面里涂抹一块区域"
                : s === "all" ? "整张图" : s === "skin" ? "只作用于肤色" : s === "objects" ? "使用下方保留的组合蒙版" : "只作用于涂抹区域"}
              onClick={() => ok(runGrade("scope", { scope: s }), props)}>
              {s === "all" ? "全图" : s === "skin" ? "肤色" : s === "objects" ? "组合蒙版" : "涂抹区域"}
            </button>
          );
        })}
      </div>
      {props.localMasksPanel}
    </div>
  );

  const bgBlock = <CommonBackgroundPanel mode="launcher" owner={props.commonBackgroundOwner}
    disabled={dim || status?.ready_caps?.common_background_protocol !== 1}/>;

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
        ] as const).filter(([mode])=>mode!=="heal"||!props.healBrushPanel).map(([mode, label]) => (
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
    if (fid === "PC-32468") return props.expressionPanel;
    if (fid === "PC-32473") return props.shoulderPanel;
    if (fid === "PC-32472") return <>
      {props.hairVolumePanel}
      {props.hairUnificationPanel}
      {status?.ready_caps?.hair_colour_protocol!==1&&<p role="status">当前引擎未提供头发范围审核，请使用配套版本。</p>}
      <HairColourPanel people={doc?.people??null} port={props.hairPort}
        busy={dim||props.hairBusy||!props.people.enabled||status?.ready_caps?.hair_colour_protocol!==1||portraitRequestsBusy()}
        patch={async patches=>{props.people.patch(patches);}} refresh={props.refreshHair}/>
      {props.people.state.message&&<p role="status">{props.people.state.message}</p>}
    </>;
    if (fid === "PC-32455") return <>{doc?.document_id && <ConnectedPrimaryCalibrationPanel documentId={doc.document_id} hostRevision={status?.doc_rev ?? 0} disabled={dim} available={status?.ready_caps?.primary_calibration_protocol===1}/>}{doc?.document_id && <ConnectedColourGradingPanel documentId={doc.document_id} hostRevision={status?.doc_rev ?? 0} disabled={dim} available={status?.ready_caps?.colour_grading_protocol===1}/>}{doc?.document_id && <ConnectedSelectiveColourPanel documentId={doc.document_id} hostRevision={status?.doc_rev ?? 0} disabled={dim} available={status?.ready_caps?.selective_colour_protocol===1}/>}{doc?.document_id && <ConnectedExtendedTonePanel documentId={doc.document_id} revision={status?.doc_rev ?? 0} disabled={dim} available={status?.ready_caps?.extended_tone_protocol===1}/>}{doc?.document_id && <ConnectedPhotoDetailPanel documentId={doc.document_id} revision={status?.doc_rev ?? 0} disabled={dim} available={status?.ready_caps?.photo_detail_protocol===1}/>}{doc?.document_id && <ConnectedPhotoGrainPanel documentId={doc.document_id} hostRevision={status?.doc_rev ?? 0} disabled={dim} available={status?.ready_caps?.photo_grain_protocol===1}/>}{doc?.document_id && <ConnectedColourEditorPanel documentId={doc.document_id} hostRevision={status?.doc_rev ?? 0} disabled={dim} available={status?.ready_caps?.colour_editor_protocol===1}/>}{lutBlock}{doc?.document_id && <ConnectedCustomLutPanel documentId={doc.document_id} hostRevision={status?.doc_rev ?? 0} assetId={doc.lut.asset_id ?? null} amount={doc.lut.amount} />}</>;
    if (fid === "PC-32452") return <>{props.sampleLibraryPanel}{props.presetPanel}{lutBlock}</>;
    if (fid === "PC-32454") return gradeBlock;
    if (fid === "PC-32481") return props.effectRecoveryPanel;
    if (fid === "PC-32479") return props.manualLiquifyPanel;
    if (fid === "PC-32474") return props.studioBackgroundPanel;
    if (fid === "PC-32476") return props.skyReplacementPanel;
    if (fid === "PC-32475") return bgBlock;
    if (fid === "PC-AlCcjw85ql") return <FringeRepairPanel mode="launcher" owner={props.fringeRepairOwner} disabled={dim||status?.ready_caps?.fringe_repair_protocol!==1}/>;
    if (fid === "PC-47209") return historyBlock;
    if (fid === "PC-32477") return <FabricPanel value={doc?.fabric} documentId={doc?.document_id} revision={status?.doc_rev??0} disabled={dim} onDone={props.onDone} note={props.note}/>;
    if (fid === "PC-32482") return <>{props.healBrushPanel}{props.sourcePatchPanel}{props.cloneStampPanel}{brushBlock}</>;
    return null;
  };

  return (
    <PortraitRevision.Provider value={doc?.people ? `${doc.people.binding.document_id}:${doc.people.revision}:${JSON.stringify(doc.people.editing_target)}` : ''}>
    <div className="retouch" data-spec-total={SPEC_COUNTS.features}
         data-spec-controls={SPEC_COUNTS.subcontrols}>
      <div className="rtContent" ref={contentRef} onScroll={(e) => {
        if (!q.trim()) scrollPositions.current[toolGroup] = e.currentTarget.scrollTop;
      }}>
      <div className="rtTitle">{q.trim() ? "功能搜索" : TOOL_GROUPS.find(g => g.id === toolGroup)?.label}</div>

      <div data-spec-family="PC-47211" hidden={toolGroup !== "portrait" || !!query}>
        <PeoplePanel owner={props.people} busy={dim || portraitRequestsBusy() || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending}
          thumb={props.thumb} onFaceAdd={props.onFaceAdd} faceAdding={props.faceAdding}/>
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
        const open = !!query || (openSeen[f.id] ?? (f.id === "PC-32465" || f.id === "PC-32455" || (!!custom && ["PC-32481","PC-32479","PC-32474","PC-32476"].includes(f.id))));
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
              {f.id === "PC-32465" && <p className="muted">磨皮使用本照片皮肤蒙版，不随上方人物或分组范围切换。</p>}
              {f.id === "PC-32464" && props.neckWrinklePanel}
              {f.id === "PC-32465" && props.skinReferencePanel}
              {f.id === "PC-32465" && props.skinReferenceBodyPanel}
              {f.id === "PC-32465" && skinWhy && <div className="specEmpty" role="status">{skinWhy}</div>}
              {f.id === "PC-32455" && props.colorSamplePanel}
              {custom}
              {f.id === "PC-32466" && <FaceStylePanel people={props.people} faceOk={props.faceOk}
                blocked={dim || props.hairBusy || !!props.whiteBalanceBusy || portraitRequestsBusy()
                  || !!status?.edit_queue?.in_flight || !!status?.edit_queue?.pending || !!status?.edit_queue?.closed}/>}
              {tree.length > 0 && (
                <SpecNodes nodes={withoutCoveredLeaves(tree, f.id, f.id === "PC-32455" ? !!props.opticsPanel : !!custom)}
                  openPaths={openPathsFor(f)} renderExtra={node=>renderExtra(node,f.id)}
                  renderLeaf={(leaf, name) => {
                    if(f.id==='PC-32464'&&leaf.path==='面部祛瑕疵/祛颈纹'&&props.neckWrinklePanel)return <p className="toolRouteNote">上方提供独立颈部细纹审核；须手绘可见颈部及首饰、衣领等保护区，不是自动颈部识别。</p>;
                    if(f.id==='PC-32468'&&leaf.path==='AI完美表情'&&props.expressionPanel)return <p className="toolRouteNote">上方接通同场次真实素材的手动替换与融合审核；自动识别人选、最佳表情选择仍未提供。</p>;
                    if (f.id === 'PC-32466' && ['脸型预设/少年', '脸型预设/圆脸适用', '脸型预设/长脸适用', '脸型预设/方脸适用', '脸型预设/程度'].includes(leaf.path)) return null; // New versioned chooser above; legacy routes remain untouched.
                    if(f.id==='PC-32455'&&['滤镜/我的/CUBE导入','滤镜/我的','滤镜/推荐'].includes(leaf.path))return null;
                    if(f.id==='PC-32452'&&leaf.path==='AI追色/批量同步&保存预设')return <SemanticColourWorkflowLaunch enabled={props.hasImage&&props.status?.ready_caps?.semantic_colour_workflow_protocol===1}/>;
                    if(f.id==='PC-32472'&&['发色选择','头发光泽'].includes(leaf.path))return null;
                    if(f.id==='PC-32472'&&props.hairVolumePanel&&['颅顶调整&颅顶调整（头顶）','发量调整'].includes(leaf.path))return null;
                    if(f.id==='PC-32472'&&props.hairUnificationPanel&&leaf.path==='发色统一')return null;
                    if (f.id === "PC-32481" && leaf.path === "背景调整涂抹笔" && props.studioBackgroundPanel)
                      return <div className="toolRouteNote"><button className="toolRouteLink" onClick={()=>navigateTool("PC-32474")}>背景调整恢复画笔</button><p>进入背景调整，在编辑范围中选择对应的恢复目标。</p></div>;
                    if (f.id === "PC-32481" && leaf.path === "换天空涂抹笔" && props.skyReplacementPanel)
                      return <div className="toolRouteNote"><button className="toolRouteLink" onClick={()=>navigateTool("PC-32476")}>换天空恢复画笔</button><p>进入换天空，选择“恢复换天空”标记区域。</p></div>;
                    if (f.id === "PC-32481" && props.effectRecoveryPanel && ["祛除瑕疵涂抹笔","衣服祛褶皱涂抹笔"].includes(leaf.path))
                      return <div><DisabledRow name={name}/><p className="toolRouteNote">{leaf.path === "祛除瑕疵涂抹笔" ? "通用祛瑕疵恢复尚未接通；上方磨皮、面部祛纹及唇妆恢复仅处理各自效果。" : "当前仅支持衣物细褶恢复，不代表全部衣服褶皱恢复。"}</p></div>;
                    if(f.id==='PC-32477'&&leaf.path==='衣服祛褶皱/祛细褶皱')return null;
                    if(f.id==='PC-32482'&&((leaf.path==='污点修复画笔'&&props.healBrushPanel)||(leaf.path==='修补工具'&&props.sourcePatchPanel)||(leaf.path==='仿制图章'&&props.cloneStampPanel)))return null;
                    if (f.id === "PC-32452" && props.sampleLibraryPanel && [
                      "AI追色/样片来源/自定义导入样片", "AI追色/导入样片",
                      "AI追色/将当前结果图创建为样片", "AI追色/创建为样片",
                    ].includes(leaf.path)) return null;
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
            title={group.label} onClick={() => { if(props.colorActions?.owner.active)props.colorActions.owner.workflow.cancel('已切换工具，未提交的定向调整已取消');setToolGroup(group.id); setQ(""); }}>
            {group.label}
          </button>
        ))}
      </nav>
    </div>
    </PortraitRevision.Provider>
  );
}
