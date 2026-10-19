/**
 * 右侧精修面板（产品态）。六个分栏按手册的工作区规划与《P0参数注册表.json》组织：
 * 质感磨皮 / 面部重塑 / 曝光白平衡肤色LUT / 局部修容画笔 / 裁剪旋转 / 导出批量工程。
 *
 * 三条硬规矩（都是本仓付过钱的）：
 * ① 每一格的**当前值一律从引擎说的 doc_state 读**（`doc`），组件自己不记一份——
 *    记了就会出现"滑块在 0.9 而画面是 0.2"那种双向错配；
 * ② 注册表里接不通的格子由 `RegistryPanel` 显式禁用并把原因写在格子里，
 *    不留"看着能点而点了什么都不动"的控件；
 * ③ 名单与量程不在这份文件里刻：预设名、能落的格式来自 `ready_caps`，磨皮参数的
 *    边界来自引擎的 doc_state/limits。这里只写"提交哪条命令"。
 */
import RegistryPanel from "./RegistryPanel";
import { sectionTitleOf, type SectionId } from "../p0";
import { t, type MsgKey } from "../i18n";
import {
  faceStateOf, runCrop, runDeform, runExposure, runFace, runGrade, runInpaint, runLight,
  runLut, runTask,
  setStrength,
  type DocState, type EngineStatus, type ProjectState, type TaskState,
} from "../native";

export interface BrushState {
  on: boolean;
  radius: number;
  feather: number;
  mode: "heal" | "dodge" | "burn" | "color";
  onChange: (patch: Partial<BrushState>) => void;
}

export interface StudioProps {
  status: EngineStatus | null;
  doc: DocState | null;
  tasks: TaskState[];
  project: ProjectState | null;
  hasImage: boolean;
  exporting: boolean;
  faceOk: boolean;
  faceWhy: string;
  /** 形变有哪些格：引擎 ready 报的那一份（`deform_kinds`）。空数组 = 这个引擎没报，
   *  面板整栏禁用并写明原因，而不是退回一份前端自己记的名单。 */
  deformKinds: string[];
  /** 值域同样取引擎（`deform_range`）；没报就按 [-1,1]，但那只是缺省，不是副本 */
  deformRange?: number[];
  note: (s: string) => void;
  onDone: () => void;
  brush: BrushState;
  /** 导出目录与位深（这两个还带着 App 里的跑靶联动，先留在上层） */
  exportDir: string;
  setExportDir: (v: string) => void;
  exportBits16: boolean;
  setExportBits16: (v: boolean) => void;
  /** 形变的作用层（LNX-PORTRAIT-004）：这是"正在改哪一层"的编辑意图，不是文档值；
   *  每一层的数值一律从 `doc.deform` 读（引擎是唯一出处）。 */
  deformScope: "all" | "person";
  setDeformScope: (v: "all" | "person") => void;
  /** 选中要批量导出的张数（底片条多选） */
  selCount: number;
  /** 模块预设（LNX-P0-PRESET）：清单来自引擎随 session_state 报的那一份，
   *  前端不扫目录、不记预设名单（那就是两个会漂的地方） */
  preset: {
    /** 名字输入（保存用）：空字符串时按钮不动作并说明为什么 */
    name: string;
    setName: (v: string) => void;
    selectedId: string;
    setSelectedId: (v: string) => void;
    builtin: boolean;
    count: number;
    errors: { file: string; error: string }[];
    onImport: () => void;
    onDelete: () => void;
  };
  /** 批量同步（LNX-P0-BATCH / BATCH-004）：目标就是底片条多选集 */
  sync: {
    selected: number;
    canUndo: boolean;
    note: string;
    onSync: () => void;
    onUndo: () => void;
  };
  /** 新建工程的名字（顶栏与面板共用一份输入，存不存由引擎说） */
  projName: string;
  setProjName: (v: string) => void;
  p0: {
    value: (key: string) => number | boolean | string | number[] | null | undefined;
    optionsFor: (key: string) => string[] | null;
    enabled: (key: string) => string | null;
    slider: (key: string, v: number) => void;
    toggle: (key: string, v: boolean) => void;
    enum: (key: string, v: string) => void;
    action: (key: string) => void;
    rect: (key: string, v: number[]) => void;
  };
}

const ok = (p: Promise<unknown>, props: StudioProps) =>
  p.then(props.onDone).catch((e) => props.note(String(e)));

/** 高低频的分带与增益：一次提交整组参数（引擎 set_strength 就是整组收的）。 */
function commitSkin(props: StudioProps, patch: Record<string, number>) {
  const d = props.doc;
  if (!d) return;
  ok(setStrength(d.strength, {
    channel: d.channel ?? undefined,
    radius: patch.radius ?? d.params.radius,
    detailGain: patch.detailGain ?? d.params.detail_gain,
    midGain: patch.midGain ?? d.params.mid_gain,
    broadGain: patch.broadGain ?? d.params.broad_gain,
    textureRadius: patch.textureRadius ?? d.params.texture_radius,
  }), props);
}

/** 裁剪比例预设：矩形按“居中裁”算，比例来自画面长宽比的常识值。
 *  这不是引擎参数，只是一个把手——真正的口径（整组校验、正角顺时针）在引擎里。 */
function rectForAspect(w: number, h: number, aspect: number): number[] {
  const img = w / h;
  if (aspect >= img) {                       // 目标更宽：上下裁
    const keep = img / aspect;
    const cut = (1 - keep) / 2;
    return [0, cut, 1, 1 - cut];
  }
  const keep = aspect / img;                 // 目标更高：左右裁
  const cut = (1 - keep) / 2;
  return [cut, 0, 1 - cut, 1];
}

/** 画笔模式的展示名（局部调色是 COLOR-004 那第四条：同一支笔、四个去处）。 */
const MODE_MSG: Record<string, MsgKey> = {
  heal: "retouch.modeHeal", dodge: "retouch.modeDodge",
  burn: "retouch.modeBurn", color: "retouch.modeColor",
};

/** 调色作用域的展示名。名单本身从引擎报的 scopes 读（这里只给名字）：
 *  引擎以后加一档时，这里少一行只是一个没翻译的选项（直陈引擎那个词），
 *  而不是拿"全图"去套一个它并不是的东西。 */
const SCOPE_MSG: Record<string, MsgKey> = {
  all: "grade.scopeAll", skin: "grade.scopeSkin", brush: "grade.scopeBrush",
};

function Group(props: { id: SectionId; children: React.ReactNode; open?: boolean }) {
  return (
    <details className="grp" open={props.open ?? true}>
      <summary>{sectionTitleOf(props.id)}</summary>
      <div className="body">{props.children}</div>
    </details>
  );
}

export default function StudioPanel(props: StudioProps) {
  const { doc, status, p0, note, onDone } = props;
  const dim = !props.hasImage;
  const chans = status?.precompute?.mask_channels ?? [];
  const deforms = doc?.deform.amounts ?? {};
  // 层级那三份（PORTRAIT-004）：默认那一层的三个数、当前这张被单独覆盖了哪几格、
  // 是不是完全跟随默认。全部取自引擎报的那一份，前端不数、不猜、不自己记
  const layerDefault = doc?.deform.default ?? {};
  const overridden = doc?.deform.overridden_kinds ?? [];
  // 画哪几格：引擎 ready 那份名单优先；还没握手时退回**这份文档的 amounts 键**
  // （引擎按 KINDS 全量建账，键集合就是名单，仍然是引擎说的）。两个来源都不是前端刻的。
  const kinds = props.deformKinds.length ? props.deformKinds : Object.keys(deforms);
  const [kLo, kHi] = (props.deformRange && props.deformRange.length === 2)
    ? [props.deformRange[0], props.deformRange[1]] : [-1, 1];
  const inherited = doc?.deform.inherited ?? true;
  const scope = props.deformScope;
  /** 多人图那一份名单与选型（LNX-PORTRAIT-003）：chip 数、能不能放行，全从引擎报的读。
   *  前端自己数脸（数不出来的那种“看着像两个人”）与前端自己记“我点了第几个人”都是第二份
   *  出处，漂的时候会以「面板能点而引擎整条拒」的形态出现。 */
  const faceSt = faceStateOf(props.status, doc);
  const multi = !!faceSt && faceSt.faces.length > 1;
  const presets = status?.presets ?? [];
  const gl = (status?.grade_limits ?? []) as number[];
  const gmax = gl.length === 3 ? gl[0] : 100;

  const taskBtn = (label: string, action: "pause" | "resume" | "cancel" | "retry" | "delete",
                   x: TaskState, enabled: boolean) => (
    <button key={action} disabled={!enabled}
            title={x.blocked_reason ?? undefined}
            onClick={() => ok(runTask(action, x.task_id), props)}>{label}</button>
  );
  const LIVE = ["queued", "running", "pause_requested", "paused", "resuming", "retrying"];
  const RETRYABLE = ["paused", "failed", "cancelled", "succeeded"];

  return (
    <div className="studio">
      {/* 1) 质感与磨皮（高低频） */}
      <Group id="skin">
        <RegistryPanel section="skin" value={p0.value} enabled={p0.enabled}
                       optionsFor={p0.optionsFor} onSlider={p0.slider} onToggle={p0.toggle}
                       onEnum={p0.enum} onAction={p0.action} onRect={p0.rect}
                       skip={["lnx.skin.v1.enabled"]} />
        <label className="k">{t("retouch.radius")} · {doc?.params.radius ?? "—"}</label>
        <input type="range" min={1} max={60} step={1} disabled={dim}
               value={doc?.params.radius ?? 12}
               onChange={(e) => commitSkin(props, { radius: +e.target.value })}
               style={{ width: "100%" }} />
        {([["detailGain", "retouch.detail"], ["midGain", "retouch.mid"],
           ["broadGain", "retouch.broad"]] as const).map(([k, msg]) => (
          <div key={k}>
            <label className="k">{t(msg)} · {(doc?.params[k === "detailGain" ? "detail_gain"
              : k === "midGain" ? "mid_gain" : "broad_gain"] ?? 0).toFixed(2)}</label>
            <input type="range" min={0} max={1.5} step={0.05} disabled={dim}
                   value={doc?.params[k === "detailGain" ? "detail_gain"
                     : k === "midGain" ? "mid_gain" : "broad_gain"] ?? 0}
                   onChange={(e) => commitSkin(props, { [k]: +e.target.value })}
                   style={{ width: "100%" }} />
          </div>
        ))}
        <label className="k">{t("retouch.channel")}</label>
        <select disabled={dim || !chans.length} value={doc?.channel ?? ""}
                onChange={(e) => ok(setStrength(doc?.strength ?? 0, {
                  channel: e.target.value || undefined, radius: doc?.params.radius,
                }), props)} style={{ width: "100%" }}>
          <option value="">{chans.length ? t("retouch.channelFull") : "（未跑面部分析）"}</option>
          {chans.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </Group>

      {/* 2) 面部重塑与遮罩 */}
      <Group id="face">
        {multi && (
          <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
            {faceSt!.faces.map((f) => (
              <button key={f.index} disabled={dim}
                      className={faceSt!.explicit && faceSt!.index === f.index ? "primary" : ""}
                      title={`脸盒 ${f.box ? f.box.map((x) => x.toFixed(3)).join(", ") : "无"}`
                              + `·占画幅 ${(f.area * 100).toFixed(2)}%`}
                      onClick={() => ok(runFace("select", f.index), props)}>
                {t("face.person")} {f.index + 1}
              </button>
            ))}
          </div>
        )}
        {multi && faceSt!.explicit && !faceSt!.blocked && (
          <div className="mut">{t("face.editing", { n: faceSt!.index + 1 })}</div>
        )}
        {!!doc?.deform.defer && <div className="p0why">{t("face.deferWait")}</div>}
        {/* 作用层（LNX-PORTRAIT-004）：改「全人物默认」还是「只这一张脸」。
         *  滑块的位置永远是**生效值**（引擎正在渲染的那一组），标签里再带上层级账：
         *  只按默认的那一格写着"跟随默认 x.xx"，被单独覆盖的那一格由下面一行点名。
         *  「只这一张」在引擎认不出脸盒时（多人没选定 / 没分析）整条被拒，按钮当场禁用
         *  并把原因放进 title——绝不留一个点了不动的控件。 */}
        <div className="row" style={{ gap: 6 }}>
          <button className={scope === "all" ? "primary" : ""} disabled={dim}
                  title={t("retouch.scopeAllWhy")}
                  onClick={() => props.setDeformScope("all")}>{t("retouch.scopeAll")}</button>
          <button className={scope === "person" ? "primary" : ""}
                  disabled={dim || !props.faceOk}
                  title={props.faceOk ? t("retouch.scopePersonWhy") : props.faceWhy}
                  onClick={() => props.setDeformScope("person")}>{t("retouch.scopePerson")}</button>
        </div>
        <div className="mut">{scope === "all"
          ? t("retouch.editingDefault") : t("retouch.editingOverride")}</div>
        <div className="mut">{inherited
          ? t("retouch.inheritAll")
          : t("retouch.overriddenNote",
              { kinds: overridden.map((k) => t(("retouch." + k) as MsgKey)).join("、") })}</div>
        {!kinds.length && (
          <div className="p0why">{t("retouch.noKinds")}</div>
        )}
        {kinds.map((kind) => (
          <div key={kind}>
            <label className="k">{t(("retouch." + kind) as MsgKey)} · {(deforms[kind] ?? 0).toFixed(2)}
              {scope === "person" && !overridden.includes(kind)
                ? `（${t("retouch.followDefault")} ${(layerDefault[kind] ?? 0).toFixed(2)}）` : ""}
            </label>
            <input type="range" min={kLo} max={kHi} step={0.01}
                   disabled={dim || !props.faceOk}
                   value={deforms[kind] ?? 0}
                   // 只发改变的那一格：整组回发会把「生效值」写进所选那一层，于是改一次
                   // 默认就把这个人单独覆盖过的别的格子抹平（PORTRAIT-004 的"覆盖项继续生效"）
                   onChange={(e) => ok(runDeform("set", { [kind]: +e.target.value }, scope), props)}
                   style={{ width: "100%" }} />
          </div>
        ))}
        <div className="row">
          <button disabled={dim || !props.faceOk} title={t("retouch.deformClearWhy")}
                  onClick={() => ok(runDeform("clear", undefined, "all"), props)}>
            {t("retouch.deformClear")}</button>
          <button disabled={dim || !props.faceOk || !overridden.length}
                  title={overridden.length ? t("retouch.inheritWhy") : t("retouch.inheritIdle")}
                  onClick={() => ok(runDeform("inherit"), props)}>{t("retouch.inherit")}</button>
        </div>
        {!props.faceOk && <div className="p0why">{props.faceWhy}</div>}
        <RegistryPanel section="face" value={p0.value} enabled={p0.enabled}
                       optionsFor={p0.optionsFor} onSlider={p0.slider} onToggle={p0.toggle}
                       onEnum={p0.enum} onAction={p0.action} onRect={p0.rect} />
      </Group>

      {/* 3) 曝光 · 白平衡 · 肤色 · LUT */}
      <Group id="tone">
        <RegistryPanel section="tone" value={p0.value} enabled={p0.enabled}
                       optionsFor={p0.optionsFor} onSlider={p0.slider} onToggle={p0.toggle}
                       onEnum={p0.enum} onAction={p0.action} onRect={p0.rect} />
        {/* 预设面（LNX-P0-PRESET）：名单与“能不能删”全部读引擎报的那一份。
            内置预设不删（它随包分发）；坏掉的那一个带原因列在下面，不静默少一个。 */}
        <div className="row">
          <input value={props.preset.name} placeholder="新预设名字（保存用）"
                 onChange={(e) => props.preset.setName(e.target.value)}
                 style={{ flex: 1, minWidth: 0 }} />
          <button disabled={dim} onClick={() => { void p0.action("lnx.preset.v1.save") }}>
            存为预设</button>
          <button onClick={props.preset.onImport}>导入预设…</button>
          <button disabled={!props.preset.selectedId || props.preset.builtin}
                  onClick={props.preset.onDelete}>删除所选</button>
        </div>
        {!!props.preset.errors.length && (
          <div className="p0why">
            {props.preset.errors.map((e) => `读不了 ${e.file}：${e.error}`).join("；")}
          </div>
        )}
        <div className="row">
          <button disabled={dim} onClick={() => ok(runExposure("clear"), props)}>
            {t("studio.exposureClear")}</button>
          <button disabled={dim || !doc?.lut.lit} onClick={() => ok(runLut("clear"), props)}>清 LUT</button>
          <button disabled={dim || !doc?.grade.lit} onClick={() => ok(runGrade("clear"), props)}>
            {t("grade.clear")}</button>
        </div>
        <label className="k">{t("color.amount", { v: (doc?.lut.amount ?? 0).toFixed(2) })}</label>
        <input type="range" min={0} max={1} step={0.01} disabled={dim || !doc?.lut.lit}
               value={doc?.lut.amount ?? 1}
               onChange={(e) => ok(runLut("amount", { amount: +e.target.value }), props)}
               style={{ width: "100%" }} />
        {(["dh", "ds", "dv"] as const).map((k) => (
          <div key={k}>
            <label className="k">{t(k === "dh" ? "grade.hue" : k === "ds" ? "grade.sat"
              : "grade.val", { v: (doc?.grade[k] ?? 0).toFixed(1) })}</label>
            <input type="range" min={-gmax} max={gmax} step={1} disabled={dim}
                   value={doc?.grade[k] ?? 0}
                   onChange={(e) => ok(runGrade("set", { [k]: +e.target.value }), props)}
                   style={{ width: "100%" }} />
          </div>
        ))}
        <label className="k">{t("grade.mix", { v: (doc?.grade.amount ?? 1).toFixed(2) })}</label>
        <input type="range" min={0} max={1} step={0.01} disabled={dim}
               value={doc?.grade.amount ?? 1}
               onChange={(e) => ok(runGrade("amount", { amount: +e.target.value }), props)}
               style={{ width: "100%" }} />
        {/* COLOR-004 局部调色：作用域 + 画笔区域。选项与选中值都读引擎报的那一份
            （scopes / scope / mask_px）：前端抄一份名单，下一轮引擎加一档这里就少一档；
            而自己记一份“现在只调皮肤”，换图/重开/撤销后就会替引擎说谎。 */}
        <label className="k">{t("grade.scope")}</label>
        <select disabled={dim} style={{ width: "100%" }}
                value={doc?.grade.scope ?? "all"}
                onChange={(e) => ok(runGrade("scope", { scope: e.target.value }), props)}>
          {(doc?.grade.scopes ?? ["all"]).map((s) => {
            // 拿不到底衬的那一档显式禁用并写清原因（引擎那一侧是整条拒），
            // 不留“能选而选了什么都不动”的控件
            const why = s === "skin" && !props.faceOk ? props.faceWhy
              : s === "brush" && !(doc?.grade.mask_px ?? 0) ? t("grade.regionEmpty") : "";
            return (
              <option key={s} value={s} disabled={!!why}>
                {SCOPE_MSG[s] ? t(SCOPE_MSG[s]) : s}{why ? `（${why}）` : ""}
              </option>);
          })}
        </select>
        <div className="row">
          <button disabled={dim || !(doc?.grade.mask_px ?? 0)}
                  onClick={() => ok(runGrade("mask_clear"), props)}>{t("grade.clearRegion")}</button>
          <span className="mut">{(doc?.grade.mask_px ?? 0)
            ? t("grade.region", { n: doc?.grade.mask_px ?? 0 }) : t("grade.regionEmpty")}</span>
        </div>
        {presets.length === 0 && <div className="mut">（引擎没报内置预设：这一版不带就不画按钮）</div>}
      </Group>

      {/* 4) 局部修容与画笔 */}
      <Group id="local">
        <RegistryPanel section="local" value={p0.value} enabled={p0.enabled}
                       optionsFor={p0.optionsFor} onSlider={p0.slider} onToggle={p0.toggle}
                       onEnum={p0.enum} onAction={p0.action} onRect={p0.rect} />
        <div className="row">
          {(["heal", "dodge", "burn", "color"] as const).map((m) => (
            // “局部调色”不靠关键点（它要的是用户涂的那一片），所以不该被“没跑面部分析”
            // 连带禁用：已接通的功被错禁，与“没接通却看着能点”是同一类错
            <button key={m} disabled={dim || (m !== "color" && !props.faceOk)}
                    className={props.brush.mode === m ? "primary" : ""}
                    onClick={() => props.brush.onChange({ on: true, mode: m })}>
              {t(MODE_MSG[m])}
            </button>
          ))}
        </div>
        <div className="row">
          <label className="k" style={{ margin: 0 }}>{t("retouch.brushSize")}</label>
          <input type="number" min={2} max={64} disabled={dim} value={props.brush.radius}
                 onChange={(e) => props.brush.onChange({ radius: +e.target.value })}
                 style={{ width: 60 }} />
          <label className="k" style={{ margin: 0 }}>{t("retouch.feather")}</label>
          <input type="number" min={0} max={8} disabled={dim} value={props.brush.feather}
                 onChange={(e) => props.brush.onChange({ feather: +e.target.value })}
                 style={{ width: 52 }} />
        </div>
        <label className="k">{t("retouch.lightExposure", {
          stops: (doc?.light.exposure ?? 0).toFixed(2) })}</label>
        <input type="range" min={-2} max={2} step={0.05} disabled={dim}
               value={doc?.light.exposure ?? 0}
               onChange={(e) => ok(runLight("params", { exposure: +e.target.value }), props)}
               style={{ width: "100%" }} />
        <div className="row">
          <button disabled={dim} onClick={() => ok(runInpaint("undo"), props)}>{t("retouch.undo")}</button>
          <button disabled={dim} onClick={() => ok(runInpaint("redo"), props)}>{t("retouch.redo")}</button>
          <button disabled={dim} onClick={() => ok(runInpaint("clear"), props)}>{t("retouch.clear")}</button>
          <button disabled={dim} onClick={() => ok(runLight("clear"), props)}>{t("retouch.lightClear")}</button>
        </div>
        <div className="mut">
          笔迹只作用于**当前这一张**：批量导出时不会搬到别的脸上（这条在引擎的导出快照里判，
          不在这里猜）。
        </div>
      </Group>

      {/* 5) 裁剪与旋转 */}
      <Group id="crop">
        <RegistryPanel section="crop" value={p0.value} enabled={p0.enabled}
                       optionsFor={p0.optionsFor} onSlider={p0.slider} onToggle={p0.toggle}
                       onEnum={p0.enum} onAction={p0.action} onRect={p0.rect} />
        <div className="row">
          {[[1, 1], [4, 5], [3, 2], [16, 9]].map(([a, b]) => (
            <button key={`${a}:${b}`} disabled={dim}
                    onClick={() => {
                      const d = status?.image;
                      if (!d?.w || !d?.h) { note("没有可裁的画布：先导入一张图。"); return; }
                      ok(runCrop("set", rectForAspect(d.w, d.h, a / b)), props);
                    }}>{a}:{b}</button>
          ))}
          <button disabled={dim || !doc?.crop.lit} onClick={() => ok(runCrop("clear"), props)}>
            {t("retouch.clear")}</button>
        </div>
        {doc?.crop.lit && (
          <div className="mut">
            预览 {JSON.stringify(doc.crop.crop_out ?? [])} · 导出写 {JSON.stringify(doc.crop.out_full ?? [])}
            （单位 px）
          </div>
        )}
      </Group>

      {/* 6) 导出 · 批量 · 工程 */}
      <Group id="output" open={false}>
        <label className="k">{t("studio.outDir")}</label>
        <input value={props.exportDir} disabled={!props.hasImage}
               onChange={(e) => props.setExportDir(e.target.value)} style={{ width: "100%" }} />
        <label className="p0toggle">
          <input type="checkbox" checked={props.exportBits16}
                 onChange={(e) => props.setExportBits16(e.target.checked)} />
          <span className="mut">16-bit 母档直通（要求其余图层都在中性位，否则引擎逐条点名拒绝）</span>
        </label>
        <div className="mut">
          {props.selCount ? t("studio.targetsSel", { n: props.selCount })
            : props.hasImage ? t("studio.targetsOne") : t("studio.targetsNone")}
        </div>
        <RegistryPanel section="output" value={p0.value} enabled={p0.enabled}
                       optionsFor={p0.optionsFor} onSlider={p0.slider} onToggle={p0.toggle}
                       onEnum={p0.enum} onAction={p0.action} onRect={p0.rect} />
        {/* 批量同步（LNX-P0-BATCH / BATCH-004）：目标 = 底片条多选集，作用域 = 上面那一格。
            撤销只拿引擎报的 batch_id（前端不记“上一个批次”），有冲突就报冲突不抹后续修改。 */}
        <div className="row">
          <button disabled={!props.sync.selected || !props.hasImage} onClick={props.sync.onSync}>
            同步到所选（{props.sync.selected}）</button>
          <button disabled={!props.sync.canUndo} onClick={props.sync.onUndo}>撤销同步</button>
        </div>
        {props.sync.note && <div className="mut">{props.sync.note}</div>}
        <div className="row">
          <input value={props.projName} placeholder="工程名"
                 onChange={(e) => props.setProjName(e.target.value)}
                 style={{ flex: 1, minWidth: 0 }} />
        </div>
        <h2>{t("studio.tasks")}</h2>
        {!props.tasks.length && <div className="mut">队列里还没有批次。</div>}
        {props.tasks.map((x) => (
          <div className="taskrow" key={x.task_id}>
            <span className="id" title={x.task_id}>{x.task_id} · {x.state}
              {x.attempt ? ` (第 ${x.attempt + 1} 次)` : ""}</span>
            <span className="mut" title={x.blocked_reason ?? ""}>
              {x.counts.succeeded}/{x.counts.total}
              {x.counts.failed ? ` · 失败 ${x.counts.failed}` : ""}
              {x.counts.skipped ? ` · 跳过 ${x.counts.skipped}` : ""}
            </span>
            <span className="btns">
              {taskBtn("暂停", "pause", x, x.state === "running" || x.state === "queued")}
              {taskBtn("继续", "resume", x, x.state === "paused")}
              {taskBtn("取消", "cancel", x, LIVE.includes(x.state))}
              {taskBtn("重试", "retry", x, RETRYABLE.includes(x.state))}
              {taskBtn("删除记录", "delete", x, true)}
            </span>
            {x.blocked_reason && <span className="p0why">{x.blocked_reason}</span>}
          </div>
        ))}
        <h2>{t("studio.project")}</h2>
        <div className="mut">
          {props.project?.open
            ? `${props.project.name ?? "?"} · ${props.project.docs ?? 0} 张 · `
              + `${props.project.dirty ? "未保存" : "已保存"}`
            : "未打开工程（导出的配方与标签只活在本次会话）"}
        </div>
        {props.project?.dropped_count
          ? <div className="p0why">{`保存时丢开 ${props.project.dropped_count} 项（模型产物不随工程文件走，重开按后端重推理）`}</div>
          : null}
      </Group>
    </div>
  );
}
