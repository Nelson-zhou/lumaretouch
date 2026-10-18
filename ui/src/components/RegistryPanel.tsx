/**
 * 右侧精修面板里"注册表驱动"的那一层。
 *
 * 遍历的是《P0参数注册表.json》那 36 条本身（`cellsFor`），绑定表只提供展示名与
 * 控件形态。这样做的唯一理由是可复查：注册表新增一格而宿主没登记时，界面上会出现
 * 一格"未登记 + 已禁用"，而不是那一格从此不存在。
 *
 * 三种"不能点"必须分开，界面上各有各的话：
 * ① 永久未接通（binding.blocked + why_not）——缺哪条通路，为什么不做假的；
 * ② 这一刻不能点（enabled 回调）——没开图、没有可用人脸（D-P0-02 的单脸口径）、
 *    导出正在跑；
 * ③ 能点。
 * 任何一格都不许"看着能点而点了什么都不动"（DoD 第三条明写的"绝不留无响应控件"）。
 */
import { cellsFor, rangeOf, sectionTitleOf, type Cell, type SectionId } from "../p0";
import { lang } from "../i18n";

/** 双语取一句话：跟着应用的语言走，不跟 navigator 走（语言是用户在这个应用里选的）。 */
const say = (p: [string, string]) => (lang() === "en" ? p[1] : p[0]);

export interface PanelProps {
  section: SectionId;
  /** 当前值一律由调用方从引擎状态里读（面板不记一份"我以为是多少"） */
  value: (key: string) => number | boolean | string | number[] | null | undefined;
  onSlider: (key: string, v: number) => void;
  onToggle: (key: string, v: boolean) => void;
  onEnum: (key: string, v: string) => void;
  onAction: (key: string) => void;
  /** 枚举候选由调用方给的那些格（预设名、引擎报的格式名单）：注册表只能列语义枚举，
   *  “这一版引擎真带哪些资产”得由引擎说 */
  optionsFor?: (key: string) => string[] | null;
  /** 裁剪框那一格：四个数作为一个整体交出去（引擎也是整组校、整组提） */
  onRect: (key: string, v: number[]) => void;
  /** 这一刻为什么不能点（null = 能点）。内容由调用方给：它才知道引擎报的单脸判据 */
  enabled: (key: string) => string | null;
  /** 已经由专用控件承载的格（比如磨皮强度那根滑块本来就在面板上），避免一格里两个把手 */
  skip?: string[];
}

function readout(v: number | boolean | string | number[] | null | undefined): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "开" : "关";
  if (Array.isArray(v)) return v.map((x) => x.toFixed(3)).join(", ");
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return v;
}

export default function RegistryPanel({
  section, value, onSlider, onToggle, onEnum, onAction, onRect, enabled, skip = [], optionsFor,
}: PanelProps) {
  const cells = cellsFor(section).filter((c) => !skip.includes(c.key));
  if (!cells.length) return null;
  return (
    <>
      {cells.map((c) => (
        <RegistryCell key={c.key} cell={c} value={value} enabled={enabled}
                      onSlider={onSlider} onToggle={onToggle} onEnum={onEnum}
                      onAction={onAction} onRect={onRect} optionsFor={optionsFor} />
      ))}
    </>
  );
}

export function RegistryCell({ cell: c, value, enabled, onSlider, onToggle, onEnum,
                               onAction, onRect, optionsFor }: {
  cell: Cell;
  value: PanelProps["value"];
  enabled: PanelProps["enabled"];
  onSlider: PanelProps["onSlider"];
  onToggle: PanelProps["onToggle"];
  onEnum: PanelProps["onEnum"];
  onAction: PanelProps["onAction"];
  onRect: PanelProps["onRect"];
  optionsFor?: PanelProps["optionsFor"];
}) {
  const v = value(c.key);
  const opts = optionsFor?.(c.key) ?? c.entry.enum ?? [];
  const why = c.binding.blocked
    ? (c.binding.why_not ? say(c.binding.why_not) : "未接通")
    : enabled(c.key);
  const off = !!why;
  const rg = rangeOf(c);
  const type = c.binding.kind;

  return (
    <div className={"p0cell" + (off ? " off" : "")}>
      <div className="p0head">
        <span className="p0label">{c.label}</span>
        <span className="p0val">{type === "action" ? "" : readout(v)}</span>
        <span className="p0req" title={c.entry.requirement_id + " · " + c.entry.operation_id
          + "." + c.entry.parameter_key + (c.entry.unit ? " · " + c.entry.unit : "")}>P0</span>
      </div>

      {type === "slider" && rg && (
        <input type="range" min={rg.min} max={rg.max} step={rg.step}
               value={typeof v === "number" ? v : (c.entry.neutral as number)}
               disabled={off}
               onChange={(e) => onSlider(c.key, +e.target.value)}
               onMouseUp={(e) => onSlider(c.key, +(e.target as HTMLInputElement).value)} />
      )}

      {type === "toggle" && (
        <label className="p0toggle">
          <input type="checkbox" checked={!!v} disabled={off}
                 onChange={(e) => onToggle(c.key, e.target.checked)} />
          <span className="mut">{v ? "已启用" : "中性位：" + JSON.stringify(c.entry.neutral)}</span>
        </label>
      )}

      {(type === "enum" || type === "asset") && (
        <select value={typeof v === "string" ? v : String(c.entry.neutral ?? "")}
                disabled={off || !opts.length}
                onChange={(e) => onEnum(c.key, e.target.value)}>
          {opts.map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
          {!opts.length && <option value="">（没有可选项：这一格要的资产本版本不带）</option>}
        </select>
      )}

      {type === "rect" && (() => {
        const cur = (Array.isArray(v) ? v : (c.entry.neutral as number[])) ?? [0, 0, 1, 1];
        return (
          <div className="p0rect">
            {cur.map((x, i) => (
              <input key={i} type="number" step={0.01} min={0} max={1}
                     value={Number(x.toFixed(3))} disabled={off}
                     onChange={(e) => {
                       const next = cur.slice();
                       next[i] = +e.target.value;
                       onRect(c.key, next);
                     }} />
            ))}
            <div className="mut">四个数依次为左 / 上 / 右 / 下（归一化 0~1），整组提交</div>
          </div>
        );
      })()}

      {type === "action" && (
        <button disabled={off} onClick={() => onAction(c.key)}>{c.label}</button>
      )}

      {off && <div className="p0why" role="note">{why}</div>}
    </div>
  );
}

/** 分栏标题（面板与折叠头共用，保证两处说的是同一个名字）。 */
export const sectionLabel = sectionTitleOf;
