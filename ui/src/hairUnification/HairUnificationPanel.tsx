// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useRef, useState, useSyncExternalStore} from 'react';
import {createPortal} from 'react-dom';
import {CONTROL_ID, hasSample, type ReferenceSide} from './model';
import type {HairUnificationPort} from './nativePort';
import {HairSampleEditor} from './HairSampleEditor';
import {ReviewImages} from './ReviewImages';
import {HairRecovery} from './HairRecovery';
import './hairUnification.css';

export function HairUnificationPanel({port, engineAlive, onStartEngine, busy = false, available = false}: {
  port: HairUnificationPort; engineAlive: boolean; onStartEngine: () => Promise<void>; busy?: boolean; available?: boolean;
}) {
  const state = useSyncExternalStore(port.subscribe, port.snapshot, port.snapshot);
  const [side, setSide] = useState<ReferenceSide>('roots'), [stroke, setStroke] = useState(false);
  const dialog = useRef<HTMLDivElement>(null), returnFocus = useRef<HTMLElement | null>(null);
  const workspace = state.workspace, draft = workspace?.draft, reference = workspace?.reference, review = workspace?.review;
  const locked = busy || state.pending || state.checking || state.preparing || state.refreshing;
  const editable = available && !locked && !state.stale && state.binding.measured;
  const current = !state.stale && !!workspace;
  useEffect(() => {
    if (!state.open) return;
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.current?.querySelector<HTMLButtonElement>('button')?.focus();
    return () => {setStroke(false); if (returnFocus.current?.isConnected) returnFocus.current.focus();};
  }, [state.open]);
  useEffect(() => {
    if (!state.open) return;
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {event.preventDefault(); event.stopImmediatePropagation(); port.close(); return;}
      if ((event.ctrlKey || event.metaKey) && ['z', 'y'].includes(event.key.toLowerCase())) {
        event.preventDefault(); event.stopImmediatePropagation();
        // A source sample draft must not invoke the photograph's canonical history behind this modal.
        if (event.key.toLowerCase() === 'z' && !event.shiftKey && !event.repeat && !locked && !stroke && draft) {
          const field = side === 'roots' ? 'root_sample' : 'tip_sample', sample = draft[field];
          if (sample.objects.length) port.edit({...draft, [field]: {...sample, objects: sample.objects.slice(0, -1)}});
        }
      }
    };
    window.addEventListener('keydown', key, true); return () => window.removeEventListener('keydown', key, true);
  }, [state.open, port, locked, stroke, side, draft]);
  const query = state.pending && <button type="button" disabled={state.checking || state.preparing} onClick={() => void port.recover()}>
    {state.checking ? '正在查询原请求…' : '查询原请求，不重发'}</button>;
  const retire = state.workspaceReopened && <button type="button" disabled={!port.canDismissReopened()} onClick={() => port.dismissReopened()}>
    已确认工程重开，保留未知回执并结束旧会话锁</button>;
  const message = <p role={state.uncertain || state.phase === 'failure' ? 'alert' : 'status'}>{state.message}</p>;
  return <>
    <section className="hair-unification-panel" data-hair-unification-workflow aria-label="发色统一 · 本人发根或发尾参考" data-tool-anchor="发色统一" data-control-id={CONTROL_ID}>
      <h4>发色统一</h4>
      <p>负值参考本人发尾，正值参考本人发根，0 为中性。手绘样本并审核完整照片后才应用，不是发色选择或光泽。</p>
      <div className="hair-unification-toolbar">
        <button type="button" disabled={!available || busy || !state.binding.targetReady || state.open || (locked && !workspace)} onClick={() => port.open()}>
          {workspace ? '继续本人样本与效果审核' : '打开本人样本与效果审核'}</button>
        <button type="button" disabled={!available || locked || !state.binding.targetReady || state.stale || stroke} onClick={() => void port.clear()}>仅将发色统一恢复中性</button>
        {query}
        {retire}
      </div>
      {!available && <p role="status">当前版本未接入发色统一的独立协议；不会回退到通用滑块或直接写入。</p>}
      {state.binding.reason && <p role="status">{state.binding.reason}</p>}
      {!state.open && message}
      {!state.open && state.uncertain && <HairRecovery engineAlive={engineAlive} onStartEngine={onStartEngine}/>}
      <p>本版仅当前照片、所选人物的独立审核；关联、分组、预设和批量同步不受支持。未执行画质验收。</p>
    </section>
    {state.open && createPortal(<div className="hair-unification-backdrop" data-hair-unification-workflow>
      <div className="hair-unification-workspace" role="dialog" aria-modal="true" aria-labelledby="hair-unification-title" ref={dialog} tabIndex={-1}
        onKeyUp={event => event.stopPropagation()}
        onKeyDown={event => {
          event.stopPropagation();
          if (event.key !== 'Tab') return;
          const controls = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), summary, [tabindex="0"]');
          if (!controls?.length) {event.preventDefault(); dialog.current?.focus(); return;}
          const first = controls[0], last = controls[controls.length - 1];
          if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) {event.preventDefault(); last.focus();}
          else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first.focus();}
        }}>
        <header><div><strong id="hair-unification-title">发色统一 · 本人源图样本和完整照片审核</strong>
          <p>滑块和笔迹只修改本地草稿，不立即改变照片。</p></div>
          <button type="button" onClick={() => port.close()}>{state.pending ? '关闭，保留原请求和草稿' : '关闭并保留草稿'}</button></header>
        {draft && reference && <>
          <fieldset disabled={!editable || stroke} className="hair-unification-controls"><legend>本次程度草稿</legend>
            <label htmlFor="hair-unification-amount">向发尾 ← 发色统一 → 向发根
              <input id="hair-unification-amount" type="range" min={-100} max={100} step={1} value={Math.round(draft.recipe.amount * 100)}
                aria-valuetext={draft.recipe.amount === 0 ? '0，中性，无发色统一' : `${Math.round(Math.abs(draft.recipe.amount) * 100)}%，参考本人${draft.recipe.amount < 0 ? '发尾' : '发根'}`}
                onChange={event => port.edit({...draft, recipe: {version: 1, amount: Number(event.target.value) / 100}})}/>
              <output>{Math.round(draft.recipe.amount * 100)}%</output></label>
            <button type="button" onClick={() => port.edit({...draft, recipe: {version: 1, amount: 0}})}>将程度草稿归零</button>
          </fieldset>
          <p>参考样本本身受保护；所选人物已审核头发范围中的其余像素向该样本的颜色靠拢。不自动判断哪些像素属于解剖上的发根或发尾，不借用其他人物的样本。</p>
          {!reference.native_available && <p role="alert">当前缺少发色统一数值核心，非零候选已禁用。中性恢复不依赖本项数值核心，但仍须原有来源、人物与其他编辑的必要分析可核对；缺失时会明确拒绝，不伪造分析。</p>}
          {(!reference.support_sha256 || !reference.semantic_evidence_sha256) && <p role="alert">此人物缺少已审核并冻结的实测头发证据。请先在“发色选择”审核头发归属，再重新载入；不能用脸框或手绘笔迹代替实测头发支持。</p>}
          <details open={!review} className="hair-unification-source-details"><summary>手绘本人参考样本 · 未修改照片</summary>
            <div className="hair-unification-toolbar" role="group" aria-label="参考样本类型">
              <button type="button" disabled={!editable || stroke} aria-pressed={side === 'roots'} onClick={() => setSide('roots')}>本人发根样本（正值参考）</button>
              <button type="button" disabled={!editable || stroke} aria-pressed={side === 'tips'} onClick={() => setSide('tips')}>本人发尾样本（负值参考）</button>
            </div>
            <HairSampleEditor key={`${workspace.binding.key}:${side}`} reference={reference} side={side}
              value={side === 'roots' ? draft.root_sample : draft.tip_sample} disabled={!editable} onStroke={setStroke}
              onError={message => port.failed(message)} onChange={sample => port.edit({...draft,
                [side === 'roots' ? 'root_sample' : 'tip_sample']: sample})}/>
            <p>{reference.notice}</p>
          </details>
          <label className="hair-unification-confirm"><input type="checkbox" checked={draft.ownership_confirmed} disabled={!editable || stroke}
            onChange={event => port.edit({...draft, ownership_confirmed: event.target.checked})}/>
            我确认所画发根 / 发尾参考样本可见、未被遮挡，属于当前照片的所选人物，不包含相邻人物。</label>
          <div className="hair-unification-toolbar">
            <button type="button" disabled={!editable || stroke || !reference.native_available || !reference.support_sha256
              || !reference.semantic_evidence_sha256 || !draft.ownership_confirmed || draft.recipe.amount === 0
              || !hasSample(draft.recipe.amount < 0 ? draft.tip_sample : draft.root_sample)} onClick={() => void port.preview()}>生成完整照片前后对照</button>
            <button type="button" disabled={!available || locked || !state.binding.targetReady || state.stale || stroke} onClick={() => void port.clear()}>仅将已保存的发色统一恢复中性</button>
          </div>
          {review && <>
            <ReviewImages review={review} port={port}/>
            <p>参考方向：本人{review.reference_side === 'roots' ? '发根' : '发尾'}。实测头发 {review.sample_counts.hair_pixels.toLocaleString()} 像素，
              发根样本 {review.sample_counts.root_pixels.toLocaleString()}、发尾样本 {review.sample_counts.tip_pixels.toLocaleString()}、本次参考样本 {review.sample_counts.selected_pixels.toLocaleString()} 像素。</p>
            <label className="hair-unification-confirm"><input type="checkbox" checked={state.reviewed} disabled={locked || !current || !state.imagesReady || stroke}
              onChange={event => port.reviewed(review.preview_id, event.target.checked)}/>
              我已检查这份完整前后照片及样本范围，确认参考来自此人物，受影响范围没有相邻人物，愿意应用这一份候选。</label>
            <div className="hair-unification-toolbar">
              <button type="button" disabled={locked || !current || !state.imagesReady || !state.reviewed || state.presented || stroke}
                onClick={() => void port.acknowledge()}>{state.presented ? '本份图片确认已核对' : '核对本份图片的显示确认'}</button>
              <button type="button" disabled={!available || locked || !current || !state.imagesReady || !state.reviewed || !state.presented || stroke}
                onClick={() => void port.commit()}>将这份已审核效果应用到当前人物</button>
            </div>
          </>}
        </>}
        {!workspace && !state.pending && <button type="button" disabled={!available || busy || !state.binding.targetReady} onClick={() => port.open()}>载入当前人物源图</button>}
        <footer>
          {state.uncertain && <HairRecovery engineAlive={engineAlive} onStartEngine={onStartEngine}/>}
          {message}{state.stale && <p role="alert">保留的草稿不再匹配当前照片或人物版本；它不能提交，也不会转移给新人物。</p>}
          <div className="hair-unification-toolbar">{query}{retire}
            {workspace && <button type="button" disabled={locked || stroke} onClick={() => port.discard()}>丢弃未应用草稿</button>}
          </div>
          <p>只匹配当前源图可测得的头发色度，保持已有亮度及纹理，不均衡纯亮度差异，不生成发丝、不重建裁黑或过曝细节。0–100% 是本实现的程度量程，不承诺商业软件像素级复刻。</p>
          <p>应用只写入当前照片的规范人物图与统一历史。关闭窗口不会撤销已经发出的请求；结果未知时保留样本与原编号，只能查询，不能再次应用或借另一张照片证明成功。本次应用内保存草稿，不承诺重启恢复。</p>
        </footer>
      </div>
    </div>, document.body)}
  </>;
}
