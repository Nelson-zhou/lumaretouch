/**
 * 规格树的通用渲染件：不碰引擎，只按 `精修功能规格.json` 的 path 递归画。
 *
 * 两个状态在这里分开：
 *   · 已接通的叶子由调用方传 renderLeaf，画真控件（滑块/按钮）；
 *   · 没接通的叶子走 DisabledRow：照常陈列、静默置灰，只在原生 Tooltip 里
 *     说明“后续版本提供”。界面上不打印规格 ID、阶段标签或项数。
 * 组件本身不做“这一族要不要画”的判断——功能清单的唯一出处是 JSON。
 */
import { type SpecNode, type SpecSubcontrol } from "../spec";

/** 未接通：保留控件位置，文字淡灰；不在界面上贴任何阶段标签。 */
export function DisabledRow({ name, hint }: { name: string; hint?: string }) {
  return (
    <div className="specRow off" aria-disabled="true"
         title={hint ?? "该功能将在后续版本提供"}>
      <span className="specName">{name}</span>
    </div>
  );
}

export interface SpecTreeProps {
  nodes: SpecNode[];
  depth?: number;
  /** 需要默认展开的完整路径（已接通的那几条的祖先链）。 */
  openPaths?: Set<string>;
  renderLeaf: (leaf: SpecSubcontrol, name: string) => React.ReactNode;
  /** 某个节点在子项之前额外画一块（例如“脸型预设”的卡片）。 */
  renderExtra?: (node: SpecNode) => React.ReactNode;
}

export function SpecNodes({
  nodes, depth = 0, openPaths, renderLeaf, renderExtra,
}: SpecTreeProps) {
  return (
    <>
      {nodes.map((node) => {
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
              <summary title={node.name}>
                <span>{node.name}</span>
              </summary>
              <div className="specKids">
                {extra}
                {node.leaf ? renderLeaf(node.leaf, node.name) : null}
                <SpecNodes nodes={node.children}
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
