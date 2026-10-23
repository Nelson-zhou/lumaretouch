import {useEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {FringeCoverageCanvas} from './FringeCoverageCanvas';
import {MAX_STROKES, MAX_TOTAL_POINTS, type BrushSettings} from './model';
import type {FringeRepairOwner} from './useFringeRepairWorkflow';
import './fringeRepair.css';

const handbook = 'LNX-REF-PC-AlCcjw85ql-C-';
export function FringeRepairPanel({owner, disabled = false, mode = 'all', onInspect}: {
  owner?: FringeRepairOwner; disabled?: boolean; mode?: 'all' | 'launcher' | 'workspace'; onInspect?: () => void;
}) {
  const state = owner?.state, workflow = owner?.workflow, draft = state?.draft;
  const opened = mode !== 'launcher' && !!state?.open;
  const dialog = useRef<HTMLDivElement>(null), returnFocus = useRef<HTMLElement | null>(null);
  const [settings, setSettings] = useState<BrushSettings>({mode: 'add', size: 8, opacity: 100, feather: 50});
  const [zoom, setZoom] = useState(100), [showCoverage, setShowCoverage] = useState(false);
  useEffect(() => {
    if (!opened) return;
    setZoom(100); setShowCoverage(false);
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.current?.querySelector<HTMLButtonElement>('button')?.focus();
    return () => {if (returnFocus.current?.isConnected) returnFocus.current.focus();};
  }, [opened]);
  const locked = !!owner?.pending || !!state?.strokeActive || ['preparing', 'loading', 'confirming'].includes(state?.phase ?? '');
  const startDisabled = disabled || !owner || !owner.context.enabled || owner.context.canStart === false || locked || !!state?.open;
  const points = draft?.strokes.reduce((count, stroke) => count + stroke.points.length, 0) ?? 0;
  const receiptTools = owner && <>
    {state?.inventory === 'failed' && <button type="button" onClick={() => void workflow?.initialize()}>重新核对原操作登记</button>}
    {state?.request && <button type="button" disabled={state.querying} onClick={() => void workflow?.check()}>
      {state.querying ? '正在查询原操作…' : '查询原操作结果，不重发'}</button>}
    {state?.request && <p><small>结果未知时不能用重复应用或另一张照片的状态证明成功。此记录只保留在本次应用进程，不是磁盘恢复记录。</small></p>}
  </>;
  return <>
    {mode !== 'workspace' && <section className="fringePanel specBlock" aria-label="祛除黑白边">
      <div className="specBlockTitle">祛除黑白边</div>
      <p>先自动计算人物、发丝、衣物和配饰的疑似边缘，再审核真实照片。手绘范围不会直接改图。</p>
      <button type="button" data-feature-id={`${handbook}6d78bc490e`} disabled={startDisabled} onClick={() => void workflow?.start()}>进入祛边 · Ctrl / ⌘ + Shift + M</button>
      {!owner && <p role="status">当前工作台未接入祛边审核，不会回退为直接应用。</p>}
      {owner && !owner.context.enabled && <p role="status">{owner.context.reason || '请打开一张可编辑的照片。'}</p>}
      {state && !state.open && <p role={state.phase === 'uncertain' || state.inventory === 'failed' ? 'alert' : 'status'}>{state.message}</p>}
      {!state?.open && receiptTools}
      {state?.phase === 'preparing' && <button type="button" onClick={() => workflow?.cancel()}>取消等待</button>}
      {state?.phase === 'success' && onInspect && <button type="button" onClick={onInspect}>到主画布做原尺寸检查</button>}
    </section>}
    {mode === 'workspace' && owner && !state?.open && (owner.pending || state?.phase === 'success') && <aside className="fringeReceipt" aria-label="祛边原操作结果">
      <strong>{owner.pending ? '祛边原操作待确认' : '祛边已应用'}</strong><p role="status">{state?.message}</p>{receiptTools}
      {!owner.pending && <div className="fringeButtons">{onInspect && <button type="button" onClick={onInspect}>到主画布做原尺寸检查</button>}
        <button type="button" onClick={() => workflow?.cancel('')}>关闭提示</button></div>}
    </aside>}
    {opened && owner && state && workflow && createPortal(<div className="fringeBackdrop">
      <div ref={dialog} className="fringeWorkspace" role="dialog" aria-modal="true" aria-labelledby="fringe-title" tabIndex={-1}
        onKeyDown={event => {
          if (event.key !== 'Tab') return;
          const items = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), summary, [tabindex="0"]');
          if (!items?.length) {event.preventDefault(); dialog.current?.focus(); return;}
          const first = items[0], last = items[items.length - 1];
          if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) {event.preventDefault(); last.focus();}
          else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first.focus();}
        }}>
        <header><div><strong id="fringe-title">祛除黑白边 · 范围与成片审核</strong>
          <p>进入时默认启用并生成候选。更新范围与确定应用是两个独立步骤。</p></div>
          <button type="button" onClick={() => workflow.cancel()}>{owner.pending ? '关闭，保留原操作查询' : '取消 / Esc'}</button></header>
        {draft && <>
          <fieldset disabled={locked} className="fringeControls"><legend>当前照片草稿</legend>
            <label data-feature-id={`${handbook}f4f0ead111`}><input type="checkbox" checked={draft.enabled}
              onChange={event => workflow.edit({...draft, enabled: event.target.checked})}/>启用祛边</label>
            <label data-feature-id={`${handbook}2173a021fd`}>程度<input type="range" min={0} max={100} step={1} value={draft.strength}
              onChange={event => workflow.edit({...draft, strength: Number(event.target.value)})}/><output>{draft.strength}</output></label>
            <button type="button" disabled={locked || !state.dirty} data-feature-id={`${handbook}eb7a67cd87`}
              onClick={() => {setShowCoverage(false); setZoom(100); void workflow.update();}}>更新效果</button>
            <small>0–100 和初始值 {state.review?.defaults.strength ?? 50} 是本实现的参数，不是官方披露的数值。</small>
          </fieldset>
          <fieldset disabled={locked} className="fringeControls"><legend>编辑祛边范围 · 松手只保留草稿</legend>
            <div className="fringeButtons" role="group" aria-label="范围工具">
              <button type="button" data-feature-id={`${handbook}8dbd34ce2a`} aria-pressed={settings.mode === 'add'}
                onClick={() => {setSettings(value => ({...value, mode: 'add'})); setShowCoverage(true);}}>画笔添加</button>
              <button type="button" data-feature-id={`${handbook}c205301c9f`} aria-pressed={settings.mode === 'subtract'}
                onClick={() => {setSettings(value => ({...value, mode: 'subtract'})); setShowCoverage(true);}}>橡皮擦减去</button>
            </div>
            <label>大小<input type="range" min={.5} max={50} step={.5} value={settings.size}
              onChange={event => setSettings(value => ({...value, size: Number(event.target.value)}))}/><output>{settings.size}% 短边</output></label>
            <label>不透明度<input type="range" min={1} max={100} step={1} value={settings.opacity}
              onChange={event => setSettings(value => ({...value, opacity: Number(event.target.value)}))}/><output>{settings.opacity}%</output></label>
            <label>羽化<input type="range" min={0} max={100} step={1} value={settings.feather}
              onChange={event => setSettings(value => ({...value, feather: Number(event.target.value)}))}/><output>{settings.feather}%</output></label>
            <button type="button" disabled={locked || !draft.strokes.length} onClick={() => workflow.edit({...draft, strokes: draft.strokes.slice(0, -1)})}>撤回最后一笔草稿 · Ctrl / ⌘ + Z</button>
            <button type="button" disabled={locked || (draft.reset_coverage && !draft.strokes.length)}
              onClick={() => workflow.edit({...draft, strokes: [], reset_coverage: true})}>重置为自动范围</button>
          </fieldset>
          <div className="fringeViewControls">
            <label><input type="checkbox" checked={showCoverage} disabled={state.strokeActive} onChange={event => setShowCoverage(event.target.checked)}/>显示范围</label>
            <label>审核图缩放<select value={zoom} disabled={state.strokeActive} onChange={event => setZoom(Number(event.target.value))}>
              {[100, 150, 200, 300, 400].map(value => <option key={value} value={value}>{value === 100 ? '适应视图' : `${value}% 缩小图`}</option>)}</select></label>
            <button type="button" disabled={state.strokeActive} onClick={() => {setZoom(100); setShowCoverage(false);}}>干净前后对照</button>
            <small>本次新增 {draft.strokes.length}/{MAX_STROKES} 笔，{points}/{MAX_TOTAL_POINTS} 点。已有范围仍受总预算约束。</small>
          </div>
          <FringeCoverageCanvas owner={owner} settings={settings} zoom={zoom} showCoverage={showCoverage}/>
          {draft.strokes.length > 0 && <details className="fringeStrokeList"><summary>本次可编辑范围笔迹（{draft.strokes.length}）</summary>
            <ol>{draft.strokes.map((stroke, index) => <li key={stroke.id}>
              <span>{index + 1}. {stroke.mode === 'add' ? '添加' : '减去'} · {stroke.points.length} 点 · 直径 {(stroke.radius * 200).toFixed(1)}% 短边</span>
              <button type="button" disabled={locked} onClick={() => workflow.edit({...draft, strokes: draft.strokes.filter(value => value.id !== stroke.id)})}>删除此笔草稿</button>
            </li>)}</ol></details>}
        </>}
        {!draft && <div className="fringeWaiting" role="status">正在生成默认启用的祛边候选…</div>}
        <footer>
          <p role={state.phase === 'failure' || state.phase === 'uncertain' ? 'alert' : 'status'}>{state.message}</p>
          {state.review && <p><small>{state.review.image.note}</small></p>}
          <div className="fringeButtons"><button type="button" className="on" disabled={locked || state.phase !== 'ready' ||
            !state.presented || state.dirty || showCoverage || zoom !== 100 || owner.context.canStart === false} onClick={() => void workflow.confirm()}>确定应用 · 可撤销</button>
            {state.phase === 'failure' && !owner.pending && <button type="button" onClick={() => {
              if (state.draft) void workflow.update(); else {workflow.cancel(); void workflow.start();}
            }}>重新生成审核图</button>}{receiptTools}</div>
          <details><summary>边缘、原尺寸、预设与批量的边界</summary>
            <p>添加画笔恢复此前排除的自动可修范围，不会强迫修改健康边缘。请检查真实轮廓光、白色衣物、细发丝、首饰与纹理，不能以范围图代替照片质量判断。</p>
            <p>笔迹绑定当前来源与构图，之后只反算裁剪和旋转；不把其他照片的范围复制过来。照片或上游编辑变化时，未应用候选会失效。</p>
            <p>这里是全尺寸计算后缩小的 8 位审核图，放大不是候选原尺寸检查。应用后请在主画布使用 100% 原尺寸查看；不满意可通过照片历史撤销。RGB16 导出与照片质量尚需单独验收。</p>
            <p>预设和批量通过现有入口同步启用与程度，并按每张目标照片重新计算自动范围。同步会重置目标照片已有的手绘祛边范围，不复制来源照片的笔迹；请在批量审核中确认。</p>
          </details>
        </footer>
      </div>
    </div>, document.body)}
  </>;
}
