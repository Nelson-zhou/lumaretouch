/**
 * 规格数据驱动（Spec-Driven UI）的唯一读入口。
 *
 * 这里读的是《AI开发资料包》四份 JSON 的**项目内逐字节副本**（`ui/src/spec/*.json`）：
 *   · 精修功能规格.json → 39 个功能族 / 805 个子控件
 *   · 工作流规格.json   → 34 条工作流（含五大工作区架构）
 *   · 创意工具规格.json → 32 个创意工具
 *   · P0参数注册表.json → 36 条已立项参数契约
 * 副本的 sha256 与条数落在 `manifest.json`，`engine/tests/test_ui_spec.py` 每次回归
 * 都拿它跟原件对账——资料包换了而 UI 没换，测试先红，不靠人记得。
 *
 * 铁律：界面上的功能清单以这份数据为唯一出处。引擎没接通的格子由调用方静默
 * 置灰，只在原生 Tooltip 里说明后续版本提供；不许在组件里私自少画一族。
 */
import refineRaw from "./refine.json";
import workflowsRaw from "./workflows.json";
import creativeRaw from "./creative.json";
import p0Raw from "./p0.json";
import manifestRaw from "./manifest.json";

export interface SpecSubcontrol {
  path: string;
  kind: string;
  left_right_unlock?: string | null;
  range?: number[] | null;
  default?: number | null;
  step?: number | null;
  unit?: string | null;
}

export interface SpecFeature {
  id: string;
  title: string;
  controls: string[];
  subcontrols: SpecSubcontrol[];
  verified_behavior?: string;
  source?: string;
}

export interface SpecWorkflow {
  id: string;
  title: string;
  steps: string[];
  parameters?: string[];
  states_and_exceptions?: string[];
}

export interface SpecTool {
  id: string;
  /** 官方页标题，形如「人像——AI面部重绘」 */
  tool: string;
  /** 破折号前的模块名（人像/消除/修复/场景/光影/创意玩法） */
  category: string;
  name: string;
  input: string;
  interaction: string;
  output: string;
  limits_and_unknowns?: string;
  source_url?: string;
}

export interface P0Entry {
  requirement_id: string;
  operation_id: string;
  parameter_key: string;
  type: string;
  unit?: string | null;
  neutral?: number | boolean | null;
  range?: unknown;
  status?: string;
}

export interface SpecManifest {
  source_dir: string;
  files: Record<string, { source: string; bytes: number; sha256: string }>;
  counts: {
    features: number;
    subcontrols: number;
    workflows: number;
    tools: number;
    p0_entries: number;
  };
}

const refine = refineRaw as unknown as { features: SpecFeature[] };
const workflows = workflowsRaw as unknown as { workflows: SpecWorkflow[] };
const creative = creativeRaw as unknown as {
  tools: Omit<SpecTool, "category" | "name">[];
};
const p0 = p0Raw as unknown as { entries: P0Entry[] };

export const FEATURES: SpecFeature[] = refine.features;
export const WORKFLOWS: SpecWorkflow[] = workflows.workflows;
export const P0: P0Entry[] = p0.entries;
export const SPEC_MANIFEST = manifestRaw as unknown as SpecManifest;

export const TOOLS: SpecTool[] = creative.tools.map((t) => {
  const cut = t.tool.indexOf("——");
  return {
    ...t,
    category: cut > 0 ? t.tool.slice(0, cut) : "其他",
    name: cut > 0 ? t.tool.slice(cut + 2) : t.tool,
  };
});

export const TOOL_CATEGORIES: string[] = Array.from(new Set(TOOLS.map((t) => t.category)));

export const featureById = (id: string): SpecFeature | undefined =>
  FEATURES.find((f) => f.id === id);

/** 工作区架构（47238）里给三块取的那一段原文：面板标题与图库说明都从这里取。 */
export const WORKSPACE_SPEC = WORKFLOWS.find((w) => w.id === "47238");

/** 神数：0 规格遗漏的判据就是这几个数。 */
export const SPEC_COUNTS = SPEC_MANIFEST.counts;

// ------------------------------------------------------------------ 树
export interface SpecNode {
  /** 路径最后一段（显示名） */
  name: string;
  /** 规格里的完整 path；根节点为空串 */
  full: string;
  children: SpecNode[];
  /** 这一层自己也是一个控件（规格里既有 "裁剪" 又有 "裁剪/原始尺寸"） */
  leaf?: SpecSubcontrol;
}

/** 按 `a/b/c` 拆成树。顺序按规格原文，不排序：官方教程的顺序就是面板的顺序。 */
export function buildTree(leaves: SpecSubcontrol[]): SpecNode[] {
  const roots: SpecNode[] = [];
  const index = new Map<string, SpecNode>();
  const ensure = (full: string, name: string, parent: SpecNode | null): SpecNode => {
    const hit = index.get(full);
    if (hit) return hit;
    const node: SpecNode = { name, full, children: [] };
    index.set(full, node);
    (parent ? parent.children : roots).push(node);
    return node;
  };
  for (const leaf of leaves) {
    const parts = leaf.path.split("/").map((s) => s.trim()).filter(Boolean);
    let parent: SpecNode | null = null;
    let full = "";
    parts.forEach((part, i) => {
      full = full ? `${full}/${part}` : part;
      parent = ensure(full, part, parent);
      if (i === parts.length - 1 && parent) parent.leaf = leaf;
    });
  }
  return roots;
}

/** 深搜数一数某棵树有多少叶子（与 feature.subcontrols.length 应当一致）。 */
export function countLeaves(nodes: SpecNode[]): number {
  return nodes.reduce(
    (n, node) => n + (node.leaf ? 1 : 0) + countLeaves(node.children),
    0,
  );
}
