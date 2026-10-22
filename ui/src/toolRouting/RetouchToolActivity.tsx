import './toolRouting.css';
export interface ToolLocation { featureId: string; path?: string; serial: number }
export interface ToolActivity {
  name: string;
  featureId: string;
  path?: string;
  active: boolean;
  pending: boolean;
  phase: string;
  message: string;
  check: () => unknown;
}
/** App owns this strip and every original workflow. Navigation never starts an edit. */
export function RetouchToolActivity({items,onLocate}:{items:ToolActivity[];onLocate:(featureId:string,path?:string)=>void}) {
  const visible = items.filter(item => item.active || item.pending || item.phase === 'uncertain');
  return <section className="retouchToolActivity" aria-label="进行中的精修工具" hidden={!visible.length}>
    {visible.map(item => <div key={item.featureId} role="status">
      <strong>{item.name}</strong>
      <span>{item.phase === 'uncertain' ? '结果待核对' : item.pending ? '处理中' : '编辑中'}{item.message ? `：${item.message}` : ''}</span>
      <button onClick={()=>onLocate(item.featureId,item.path)}>返回工具分类</button>
      {item.phase === 'uncertain' && <button onClick={()=>void item.check()}>查询原操作结果</button>}
    </div>)}
  </section>;
}
/** Called only after navigation state has made the persistent family visible. */
export function revealTool(root: HTMLElement | null, featureId: string, path?: string) {
  const family = root?.querySelector<HTMLElement>(`[data-spec-family="${featureId}"]`);
  const target = path ? Array.from(family?.querySelectorAll<HTMLElement>('[data-tool-anchor]') ?? []).find(node => node.dataset.toolAnchor === path) ?? family : family;
  if (!target) return;
  let parent: HTMLElement | null = target;
  while (parent && parent !== root) {
    if (parent instanceof HTMLDetailsElement) parent.open = true;
    parent = parent.parentElement;
  }
  target.scrollIntoView({block:'nearest'});
  (target.querySelector<HTMLElement>('summary,button') ?? family?.querySelector<HTMLElement>('summary'))?.focus();
}
