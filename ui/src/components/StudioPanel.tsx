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
  runCrop, runDeform, runExposure, runGrade, runInpaint, runLight, runLut, runTask,
  setStrength,
  type DocState, type EngineStatus, type ProjectState, type TaskState,
} from "../native";

export interface BrushState {
  on: boolean;
  radius: number;
  feather: number;
  mode: "heal" | "dodge" | "burn";
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
  note: (s: string) => void;
  onDone: () => void;
  brush: BrushState;
  /** 导出目录与位深（这两个还带着 App 里的跑靶联动，先留在上层） */
  exportDir: string;
  setExportDir: (v: string) => void;
  exportBits16: boolean;
  setExportBits16: (v: boolean) => void;
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
        {(["slim_face", "big_eye", "small_chin"] as const).map((kind) => (
          <div key={kind}>
            <label className="k">{t(("retouch." + kind) as MsgKey)} · {(deforms[kind] ?? 0).toFixed(2)}</label>
            <input type="range" min={-1} max={1} step={0.01}
                   disabled={dim || !props.faceOk}
                   value={deforms[kind] ?? 0}
                   onChange={(e) => ok(runDeform("set", { ...deforms, [kind]: +e.target.value }), props)}
                   style={{ width: "100%" }} />
          </div>
        ))}
        <div className="row">
          <button disabled={dim || !props.faceOk} onClick={() => ok(runDeform("clear"), props)}>
            {t("retouch.deformClear")}</button>
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
        {presets.length === 0 && <div className="mut">（引擎没报内置预设：这一版不带就不画按钮）</div>}
      </Group>

      {/* 4) 局部修容与画笔 */}
      <Group id="local">
        <RegistryPanel section="local" value={p0.value} enabled={p0.enabled}
                       optionsFor={p0.optionsFor} onSlider={p0.slider} onToggle={p0.toggle}
                       onEnum={p0.enum} onAction={p0.action} onRect={p0.rect} />
        <div className="row">
          {(["heal", "dodge", "burn"] as const).map((m) => (
            <button key={m} disabled={dim || !props.faceOk}
                    className={props.brush.mode === m ? "primary" : ""}
                    onClick={() => props.brush.onChange({ on: true, mode: m })}>
              {t(("retouch.mode" + (m === "heal" ? "Heal" : m === "dodge" ? "Dodge" : "Burn")) as MsgKey)}
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
