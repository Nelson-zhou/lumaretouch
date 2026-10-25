// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useRef, useState, useSyncExternalStore} from 'react';
import {createPortal} from 'react-dom';
import {CONTROL_IDS, OPERATION, REGION_KEYS, activeRegions, checkSourceGeometry, isNeutral, previewPayload, type Draft, type Recipe, type RegionKey} from './model';
import type {HairVolumePort} from './nativePort';
import {HairVolumeSupportEditor} from './HairVolumeSupportEditor';
import {ReviewImages} from './ReviewImages';
import {HairVolumeRecovery} from './HairVolumeRecovery';
import './hairVolume.css';

const NAMES: Record<RegionKey, string> = {crown: '颅顶', left: '画面左侧', right: '画面右侧'};
export function HairVolumePanel({port, engineAlive, onStartEngine, busy = false, available = false}: {
  port: HairVolumePort; engineAlive: boolean; onStartEngine: () => Promise<void>; busy?: boolean; available?: boolean;
}) {
  const state = useSyncExternalStore(port.subscribe, port.snapshot, port.snapshot);
  const [measuring, setMeasuring] = useState(false);
  const dialog = useRef<HTMLDivElement>(null), returnFocus = useRef<HTMLElement | null>(null);
  const workspace = state.workspace, draft = workspace?.draft, reference = workspace?.reference, review = workspace?.review;
  const locked = busy || state.pending || state.checking || state.preparing || state.refreshing;
  const current = !state.stale && !!workspace, editable = available && !locked && current && state.binding.measured;
  const canConfirm = editable && state.sourceReady && !measuring;
  let previewError = '';
  if (draft && reference) try {checkSourceGeometry(previewPayload(draft).regions, reference.source);}
  catch (error) {previewError = error instanceof Error ? error.message : '独立轮廓尚未完整确认。';}
  useEffect(() => {
    if (!state.open) return;
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.current?.querySelector<HTMLButtonElement>('button')?.focus();
    return () => {setMeasuring(false); if (returnFocus.current?.isConnected) returnFocus.current.focus();};
  }, [state.open]);
  useEffect(() => {
    if (!state.open) return;
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {event.preventDefault(); event.stopImmediatePropagation(); port.close(); return;}
      if ((event.ctrlKey || event.metaKey) && ['z', 'y'].includes(event.key.toLowerCase())) {
        // Local geometry is not the photograph's canonical edit history.
        event.preventDefault(); event.stopImmediatePropagation();
      }
    };
    window.addEventListener('keydown', keydown, true); return () => window.removeEventListener('keydown', keydown, true);
  }, [state.open, port]);
  function editRecipe(recipe: Recipe) {if (draft) port.edit({...draft, recipe});}
  function amount(region: RegionKey, value: number) {
    if (!draft) return;
    const recipe = draft.recipe;
    if (region === 'crown') editRecipe({...recipe, crown: {version: 1, amount: value}});
    else editRecipe({...recipe, sides: {...recipe.sides, [region]: value, ...(recipe.sides.linked ? {left: value, right: value} : {})}});
  }
  function slider(region: RegionKey) {
    if (!draft) return null;
    const value = region === 'crown' ? draft.recipe.crown.amount : draft.recipe.sides[region];
    return <label className="hair-volume-slider" key={region}>
      <span>{NAMES[region]}{region === 'crown' ? '高度' : '发量轮廓'} <output>{Math.round(value * 100)}</output></span>
      <input type="range" min={-100} max={100} step={1} value={Math.round(value * 100)} disabled={!editable || measuring}
        aria-label={`${NAMES[region]}${region === 'crown' ? '高度' : '发量轮廓'}`}
        aria-valuetext={`${Math.round(value * 100)}，${value === 0 ? '中性' : region === 'crown' ? value < 0 ? '降低颅顶' : '抬高颅顶' : value < 0 ? '减少侧面发量轮廓' : '增加侧面发量轮廓'}`}
        onChange={event => amount(region, Number(event.target.value) / 100)}/>
      <span>{region === 'crown' ? '向左降低 ← 0 中性 → 向右抬高' : '向左减少 ← 0 中性 → 向右增加'}</span>
    </label>;
  }
  const query = state.pending && <button type="button" disabled={state.checking || state.preparing} onClick={() => void port.recover()}>
    {state.checking ? '正在查询原请求…' : '查询原请求，不重发'}</button>;
  const retire = state.workspaceReopened && <button type="button" disabled={!port.canDismissReopened()} onClick={() => port.dismissReopened()}>
    已确认工程重开，保留未知回执并结束旧会话锁</button>;
  const message = state.message && <p role={state.uncertain || state.phase === 'failure' ? 'alert' : 'status'}>{state.message}</p>;
  return <>
    <section className="hair-volume-panel" data-hair-volume-workflow data-readonly-scopes data-operation-id={OPERATION} data-tool-anchor="颅顶 / 两侧发量" aria-label="颅顶与两侧发量 · 当前照片手动辅助轮廓">
      <h4>颅顶 / 两侧发量</h4>
      <p>颅顶向左降低、向右抬高；两侧向左减少、向右增加，可链接或分别调整画面左 / 右。只改变现有头发外轮廓，不生成或增加发丝密度。</p>
      <div className="hair-volume-toolbar"><button type="button" disabled={!available || busy || !state.binding.targetReady || state.open || (locked && !workspace)} onClick={() => port.open()}>
        {workspace ? '继续独立轮廓与完整效果审核' : '打开独立轮廓与完整效果审核'}</button>
        <button type="button" disabled={!available || locked || !state.binding.targetReady || state.stale} onClick={() => void port.clear()}>仅将颅顶与两侧发量恢复中性</button>{query}{retire}</div>
      {!available && <p role="status">当前版本未接入独立发量协议；不会回退到小头、发色控制或直接写图。</p>}
      {state.binding.reason && <p role="status">{state.binding.reason}</p>}
      {!state.open && message}
      {!state.open && state.uncertain && <HairVolumeRecovery engineAlive={engineAlive} onStartEngine={onStartEngine}/>}
      <p>仅当前照片所选人物的独立人工辅助 2D 源码实现；不支持预设、关联、分组、批量或跨图轮廓迁移。实机与自然度验收未运行。</p>
    </section>
    {state.open && createPortal(<div className="hair-volume-backdrop" data-hair-volume-workflow data-readonly-scopes>
      <div className="hair-volume-workspace" role="dialog" aria-modal="true" aria-labelledby="hair-volume-title" tabIndex={-1} ref={dialog}
        onKeyUp={event => event.stopPropagation()} onKeyDown={event => {
          event.stopPropagation(); if (event.key !== 'Tab') return;
          const controls = dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), summary, [tabindex="0"]');
          if (!controls?.length) {event.preventDefault(); dialog.current?.focus(); return;}
          const first = controls[0], last = controls[controls.length - 1];
          if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) {event.preventDefault(); last.focus();}
          else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first.focus();}
        }}>
        <header><div><strong id="hair-volume-title">颅顶与两侧发量 · 当前照片独立轮廓审核</strong>
          <p>滑块与测量只修改本地草稿，完整审核并确认后才应用。不是小头、染发、发根发尾统一或生成式补发。</p></div>
          <button type="button" onClick={() => port.close()}>{state.pending ? '关闭，保留原请求和已采用草稿' : '关闭并保留已采用草稿'}</button></header>
        {draft && reference && <>
          <div className="hair-volume-controls">
            <fieldset data-control-id={CONTROL_IDS.crown} data-requirement-id="PC-32472:2"><legend>独立颅顶高度</legend>
              {slider('crown')}<button type="button" disabled={!editable || measuring} onClick={() => amount('crown', 0)}>仅将颅顶草稿归零</button></fieldset>
            <fieldset data-control-id={CONTROL_IDS.sides} data-requirement-id="PC-32472:3"><legend>两侧发量轮廓</legend>
              <button type="button" disabled={!editable || measuring} aria-pressed={draft.recipe.sides.linked} onClick={() => editRecipe({...draft.recipe,
                sides: {...draft.recipe.sides, linked: !draft.recipe.sides.linked, ...(!draft.recipe.sides.linked ? {right: draft.recipe.sides.left} : {})}})}>
                {draft.recipe.sides.linked ? '已链接，点击改为左右独立' : '独立调整中，点击链接并采用画面左侧值'}</button>
              {slider('left')}{!draft.recipe.sides.linked && slider('right')}
              {draft.recipe.sides.linked && <p>链接时同一滑块同步写入画面左右数值，仍须分别测量和确认两侧实际轮廓。</p>}
              <button type="button" disabled={!editable || measuring} onClick={() => editRecipe({...draft.recipe, sides: {...draft.recipe.sides, left: 0, right: 0}})}>仅将两侧草稿归零</button>
            </fieldset>
          </div>
          <p>本实现量程为 −100 到 +100，对应原创规范参数 −1 到 +1，0 为中性。位移幅度由本次边界的保守限制约束，不是商业参考产品披露范围。它移动现有像素及周围清晰背景，不合成发丝。</p>
          {!reference.native_available && <p role="alert">当前缺少本项数值形变核心，非零候选不可用；中性恢复仍由原有来源及保留效果校验决定。</p>}
          {!reference.semantic_evidence_sha256 && <p role="alert">缺少当前源图的真实头发语义证据。手工轮廓和勾选不能代替真实头发测量，也不能借用其他照片或其他人物的蒙版。</p>}
          <details open={!review} className="hair-volume-source-details"><summary>本次来源图 · 轮廓、背景与保护区域</summary>
            <HairVolumeSupportEditor key={workspace.binding.key} reference={reference} draft={draft} disabled={!editable}
              onChange={value => port.edit(value)} onError={error => port.failed(error)}
              onSourceReady={ready => port.sourceReady(reference.source.sha256, ready)}
              onPending={pending => {setMeasuring(pending); if (pending && review) port.reviewed(review.preview_id, false);}}/>
            <p>{reference.notice}</p>
          </details>
          <fieldset disabled={!canConfirm} className="hair-volume-consent"><legend>当前来源与本项独立授权</legend>
            {REGION_KEYS.map(region => <label key={region}><input type="checkbox" checked={draft[`${region}_confirmed`]} disabled={!canConfirm || !activeRegions(draft.recipe).includes(region)}
              onChange={event => port.edit({...draft, [`${region}_confirmed`]: event.target.checked} as Draft)}/>
              我独立复核了{NAMES[region]}的可见轮廓、本人头发与清晰背景探针，以及固定{region === 'crown' ? '下界' : '内界'}和背景过渡；没有裁切、遮挡或与受保护区域接触。</label>)}
            <label><input type="checkbox" checked={draft.protection.visible_anatomy_reviewed} onChange={event => port.edit({...draft,
              protection: {...draft.protection, visible_anatomy_reviewed: event.target.checked}})}/>
              我已标记实际可见的耳部、颈部及其他人物保护框；未臆测隐藏解剖，也未省略接触区域来绕过限制。</label>
            <label><input type="checkbox" checked={draft.protection.whole_source_reviewed} onChange={event => port.edit({...draft,
              protection: {...draft.protection, whole_source_reviewed: event.target.checked}})}/>
              我检查了整张当前源图，所有轮廓只属于所选人物，周边为可安全过渡的清晰背景；合并头发语义不是人物实例分割。</label>
          </fieldset>
          {previewError && !isNeutral(draft.recipe) && <p role="status">{previewError}</p>}
          <div className="hair-volume-toolbar"><button type="button" disabled={!canConfirm || !!previewError || !reference.native_available || !reference.semantic_evidence_sha256}
            onClick={() => void port.preview()}>生成实际完整混合前后对照</button>
            <button type="button" disabled={!available || locked || !current || measuring} onClick={() => void port.clear()}>仅将已保存颅顶与两侧发量恢复中性</button></div>
          {review && <>
            <ReviewImages review={review} port={port}/>
            <label className="hair-volume-confirm"><input type="checkbox" checked={state.reviewed} disabled={locked || !current || !state.imagesReady || measuring}
              onChange={event => port.reviewed(review.preview_id, event.target.checked)}/>
              我检查了这份实际完整混合前后照片及独立范围图，确认所选人物轮廓和背景自然，脸、耳、颈及其他人物没有被改动，愿意应用这份候选。</label>
            <div className="hair-volume-toolbar"><button type="button" disabled={locked || !current || !state.imagesReady || !state.reviewed || state.presented || measuring}
              onClick={() => void port.acknowledge()}>{state.presented ? '本份图片确认已核对' : '核对本份图片的精确显示确认'}</button>
              <button type="button" disabled={!available || locked || !current || !state.imagesReady || !state.reviewed || !state.presented || measuring}
                onClick={() => void port.commit()}>应用这份已审核颅顶 / 两侧发量</button></div>
          </>}
        </>}
        {!workspace && !state.pending && <button type="button" disabled={!available || busy || !state.binding.targetReady} onClick={() => port.open()}>载入当前人物来源图</button>}
        <footer>{state.uncertain && <HairVolumeRecovery engineAlive={engineAlive} onStartEngine={onStartEngine}/>}{message}
          {state.stale && <p role="alert">保留草稿不再匹配当前照片、人物或修复/编辑状态。不能提交或借新照片证明旧操作成功。</p>}
          <div className="hair-volume-toolbar">{query}{retire}{workspace && <button type="button" disabled={locked || measuring} onClick={() => port.discard()}>丢弃未应用草稿</button>}</div>
          <p>应用只写入当前照片规范人物状态与统一历史。不生成新的历史分支或绕过现有撤销。关闭不撤回已经发送的请求；未知结果只查询原编号，不重复应用。已采用草稿保留于本次应用会话，不承诺重启恢复；未采用坐标与第一角会取消。</p>
          <p>这是边界受限的手工辅助 2D 外轮廓形变，不等于头发密度合成、自动颅顶检测、耳部定位、三维头型重建或商业软件像素级复刻。完整缩小图用于本次授权，不代替原尺寸实机画质验收；后者尚未运行。</p>
        </footer>
      </div>
    </div>, document.body)}
  </>;
}
