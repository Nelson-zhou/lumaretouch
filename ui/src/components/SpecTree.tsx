/**
 * 规格树的通用渲染件：不碰引擎，只按 `精修功能规格.json` 的 path 递归画。
 *
 * 两个状态在这里分开：
 *   · 已接通的叶子由调用方传 renderLeaf，画真控件（滑块/按钮）；
 *   · 没接通的叶子一律走 P1Row：完整陈列、置灰、Tooltip 带规格 ID。
 * 组件本身不做“这一族要不要画”的判断——功能清单的唯一出处是 JSON。
 */
import { countLeaves, type SpecNode, type SpecSubcontrol } from "../spec";

/** 未接通：保留控件形状与位置，置灰，并写清阶段与规格 ID。 */
export function P1Row({ name, specId, hint }: {
  name: string;
  specId: string;
  hint?: string;
}) {
  return (
    <div className="specRow off" data-spec-id={specId}
         title={`P1 规划中 · [${specId}]：当前版本未接通后端算法${hint ? `（${hint}）` : ""}`}>
      <span className="specName">{name}</span>
      <span className="specP1">P1 规划中</span>
    </div>
  );
}

/** 说明性条目（概述/常见问题）：不是控件，不冒充 P1 滑杆。 */
export function SpecInfo({ text }: { text: string }) {
  return <div className="specInfo"><span>{text}</span></div>;
}

export interface SpecTreeProps {
  nodes: SpecNode[];
  specId: string;
  depth?: number;
  /** 需要默认展开的完整路径（已接通的那几条的祖先链）。 */
  openPaths?: Set<string>;
  renderLeaf: (leaf: SpecSubcontrol, name: string) => React.ReactNode;
  /** 某个节点在子项之前额外画一块（例如“脸型预设”的卡片）。 */
  renderExtra?: (node: SpecNode) => React.ReactNode;
}

export function SpecNodes({
  nodes, specId, depth = 0, openPaths, renderLeaf, renderExtra,
}: SpecTreeProps) {
  return (
    <>
      {nodes.map((node) => {
        const n = countLeaves([node]);
        const extra = renderExtra?.(node);
        if (!node.children.length) {
          return (
            <div className="specNode" key={node.full}>
              {extra}
              {node.leaf ? renderLeaf(node.leaf, node.name) : null}
            </div>
          );
        }
        // 只展开“已接通那条叶子的祖先链”：39 族 × 805 项全展开会把面板拉成
        // 一条几十屏的长卷，专业工作台也不是那么用的。其余族照常陈列、可点开。
        const open = !!openPaths?.has(node.full);
        return (
          <div className="specNode" key={node.full}>
            <details className="specSub" open={open}>
              <summary title={`${node.full} · ${n} 项`}>
                <span>{node.name}</span>
                <em>{n}</em>
              </summary>
              <div className="specKids">
                {extra}
                {node.leaf ? renderLeaf(node.leaf, node.name) : null}
                <SpecNodes nodes={node.children} specId={specId}
                           depth={depth + 1} openPaths={openPaths}
                           renderLeaf={renderLeaf} renderExtra={renderExtra} />
              </div>
            </details>
          </div>
        );
      })}
    </>
  );
}
