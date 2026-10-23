import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {defaultDraft, hex, parseHex, type Mutation} from './model';
import type {CommonBackgroundOwner} from './useCommonBackgroundWorkflow';
import './commonBackground.css';

export function CommonBackgroundPanel({owner, disabled = false, mode = 'all'}: {
  owner?: CommonBackgroundOwner; disabled?: boolean; mode?: 'all' | 'launcher' | 'workspace';
}) {
  const [loaded, setLoaded] = useState<string[]>([]);
  const draft = owner?.draft ?? defaultDraft();
  const dialog = useRef<HTMLDivElement>(null), lastFocus = useRef<HTMLElement | null>(null);
  const state = owner?.state, workflow = owner?.workflow;
  const opened = mode !== 'launcher' && !!state?.open;
  useEffect(() => {
    if (!opened) return;
    lastFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const first = dialog.current?.querySelector<HTMLButtonElement>('button'); first?.focus();
    return () => {if (lastFocus.current?.isConnected) lastFocus.current.focus();};
  }, [opened]);
  useLayoutEffect(() => {setLoaded([]);}, [state?.previewId]);
  useLayoutEffect(() => {
    if (!opened || !workflow || !state?.open || state.phase !== 'ready' || !state.previewId || !state.image ||
        !['before', 'after'].every(side => loaded.includes(`${state.previewId}:${side}`))) return;
    const preview = state.previewId;
    let live = true, second = 0;
    const first = requestAnimationFrame(() => {second = requestAnimationFrame(() => {if (live) void workflow.presented(preview);});});
    return () => {live = false; cancelAnimationFrame(first); cancelAnimationFrame(second);};
  }, [opened, workflow, state?.open, state?.phase, state?.previewId, state?.image, loaded]);
  const locked = owner?.pending || state?.phase === 'preparing' || state?.phase === 'loading';
  const startDisabled = disabled || !!locked || !owner || !owner.context.enabled || owner.context.canStart === false || owner.pending || owner.active;
  function edit(next: Extract<Mutation, {action: 'set'}>) {owner?.setDraft(next); workflow?.dirty();}
  function preview(mutation: Mutation) {
    if (!workflow || locked) return;
    if (state?.phase === 'ready') void workflow.render(mutation);
    else void workflow.start(mutation);
  }
  return <>
    {mode !== 'workspace' && <section className="commonBackgroundPanel specBlock" aria-label="纯色换底前后审核">
    <div className="specBlockTitle">纯色换底 · 前后审核</div>
    <p>色键适用于颜色较均匀、与人物有明显色差的背景，不是智能人物分割。原照片和不透明 SDR 创意回流图都从各自的当前源图计算。</p>
    <div className="specSeg">
      <button type="button" disabled={startDisabled} onClick={() => preview(draft)}>预览纯色换底</button>
      <button type="button" disabled={startDisabled} onClick={() => preview({action: 'clear'})}>预览还原换底</button>
    </div>
    {!owner && <p role="status">当前工作台未接入换底审核，请使用配套版本。不会回退为直接应用。</p>}
    {owner && !owner.context.enabled && <p role="status">{owner.context.reason || '请在可编辑的单张照片中打开纯色换底审核。'}</p>}
    {!state?.open && state?.message && <p role="status">{state.message}</p>}
    {state?.phase === 'preparing' && <button type="button" onClick={() => workflow?.cancel()}>取消等待</button>}
    {!state?.open && owner?.pending && <button type="button" onClick={() => void workflow?.check()}>查询原操作结果，不重复提交</button>}
    <details><summary>算法与旧路径说明</summary>
      <p>当前审核只使用确定性色键。复杂背景、与底色相近的衣物、半透明发丝仍可能误选，请检查前后对照，不满意就取消。</p>
      <p>旧神经抠图与历史代理蒙版路径仍保留在诊断工具中，权重缺失不会自动回退；代理蒙版不等于原尺寸精修，不能据此宣称神经抠图、透明图或 HDR 已完成验收。</p>
      <p>此处展示实际成片管线的 sRGB 8 位代理图，不是最终导出文件，也不是原尺寸边缘或色彩精度验收结果。</p>
    </details>
    </section>}
    {mode === 'workspace' && !opened && owner?.pending && <aside className="commonBackgroundPanel commonBackgroundReceipt" aria-label="待确认的换底操作">
      <p role="status">{state?.message}</p><button type="button" onClick={() => void workflow?.check()}>查询原操作结果，不重复提交</button>
    </aside>}
    {opened && state && workflow && createPortal(<div className="commonBackgroundBackdrop">
      <div className="commonBackgroundWorkspace" ref={dialog} role="dialog" aria-modal="true" aria-label="纯色换底前后审核"
        onKeyDown={event => {
          if (event.key !== 'Tab') return;
          const items = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), summary, [tabindex="0"]');
          if (!items?.length) return;
          const first = items[0], last = items[items.length - 1];
          if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) {event.preventDefault(); last.focus();}
          else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first.focus();}
        }}>
        <header><div><strong>{state.mutation?.action === 'clear' ? '还原换底前后审核' : '纯色换底前后审核'}</strong>
          <p>预览不会写入照片。只有明确确定并收到完整回执后，才会报告已保存。</p></div>
          <button type="button" onClick={() => workflow.cancel()}>{owner?.pending ? '关闭窗口，保留原操作查询' : '取消 / Esc'}</button></header>
        <fieldset disabled={!!locked} className="commonBackgroundControls"><legend>调整草稿（不是当前保存参数）</legend>
          <label>新背景颜色<input type="color" aria-label="新背景颜色" value={hex(draft.bg)} onChange={event => edit({...draft, bg: parseHex(event.target.value)})}/></label>
          <label>背景色差容差<input type="range" min={0} max={1} step={.001} value={draft.tol} onChange={event => edit({...draft, tol: Number(event.target.value)})}/><output>{draft.tol.toFixed(3)}</output></label>
          <label>边缘过渡宽度<input type="range" min={.001} max={1} step={.001} value={draft.softness} onChange={event => edit({...draft, softness: Number(event.target.value)})}/><output>{draft.softness.toFixed(3)}</output></label>
          <button type="button" onClick={() => preview(draft)}>更新换底对照</button>
          <button type="button" onClick={() => preview({action: 'clear'})}>查看还原对照</button>
        </fieldset>
        {state.image && <div className="commonBackgroundPictures">{(['before', 'after'] as const).map(side => <figure key={`${state.previewId}:${side}`}>
          <figcaption>{side === 'before' ? '本次调整前（包含已有编辑）' : state.mutation?.action === 'clear' ? '还原换底后（尚未保存）' : '本次换底后（尚未保存）'}</figcaption>
          <img src={state.image![side]} alt={side === 'before' ? '本次调整前的真实照片' : '本次调整后的真实照片'}
            onLoad={event => {
              const preview = state.previewId, image = state.image;
              if (!preview || !image || event.currentTarget.naturalWidth !== image.width || event.currentTarget.naturalHeight !== image.height) {
                workflow.failed('换底预览图像尺寸不符，不能确定', preview ?? undefined); return;
              }
              setLoaded(old => old.includes(`${preview}:${side}`) ? old : [...old, `${preview}:${side}`]);
            }} onError={() => workflow.failed('换底照片预览无法完整显示，不能确定', state.previewId ?? undefined)}/>
        </figure>)}</div>}
        <footer><p role={state.phase === 'failure' || state.phase === 'uncertain' ? 'alert' : 'status'}>{state.message}</p>
          {state.image && <p><small>{state.image.note}</small></p>}
          {state.phase === 'ready' && !state.presented && <p role="status">正在确认两张真实预览均已显示，暂不能确定。</p>}
          <p><small>请重点检查发丝、衣物和边缘。不透明 SDR 回流图按自身源图处理，不借用原照片的蒙版；透明/HDR 不在此审核路径的支持范围内。</small></p>
          <div className="specSeg"><button type="button" className="on" disabled={!!locked || state.phase !== 'ready' || !state.presented || !state.committable || owner?.context.canStart === false}
            onClick={() => void workflow.confirm()}>{state.mutation?.action === 'clear' ? '确定还原换底' : '确定应用换底'}</button>
            {owner?.pending && <button type="button" onClick={() => void workflow.check()}>查询原操作，不重复提交</button>}
            {state.phase === 'failure' && <button type="button" onClick={() => preview(state.mutation ?? draft)}>重新生成对照</button>}</div>
        </footer>
      </div>
    </div>, document.body)}
  </>;
}
