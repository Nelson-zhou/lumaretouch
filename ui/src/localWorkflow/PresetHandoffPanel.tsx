// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect} from 'react';
import type {WorkflowController, WorkflowViewState} from './controller';
import {reviewKey, type ReviewSide} from './presetReview';

const PHASES = {awaiting_open: '等待打开目标照片', reviewing: '等待逐图审核', authorized: '批准已保留，等待核心核对',
  awaiting_save: '预设已应用，等待保存工程', awaiting_return: '等待返回原目标', unknown: '实际结果未知，只读核对'};
export function PresetHandoffPanel({controller, state}: {controller: WorkflowController; state: WorkflowViewState}) {
  const run = state.active_run, handoff = run?.handoff;
  const identity = handoff?.review?.review_sha256;
  useEffect(() => {
    // Read-only fetching is safe on mount; reopening never restores a checkbox
    // or sends an approval. Exact DOM load proof is still required for each side.
    if (run && handoff?.phase === 'reviewing') {
      const key = reviewKey(run.run_id, handoff);
      void controller.loadReviewImages();
      return () => controller.clearReviewPresentation(key);
    }
  }, [controller, run?.run_id, handoff?.operation_id, handoff?.phase, identity]);
  if (!run || !handoff) return null;
  const report = handoff.review, images = state.review_images;
  const ready = !!images && !images.loading && !images.error && images.displayed.before && images.displayed.after;
  const preApply = handoff.phase === 'awaiting_open' || handoff.phase === 'reviewing';
  return <section className="local-workflow-warning local-workflow-handoff" aria-label="预设逐图审核交接">
    <h4>{PHASES[handoff.phase]}</h4>
    <p>{handoff.message}</p>
    <p>照片 {handoff.document_id} · 预设 {handoff.preset_id}</p>
    <small>预设 SHA-256：{handoff.preset_sha256}</small>
    <p>新照片发现已暂停。当前工程租约与原操作持续保留，停止按钮不会释放尚未结清的交接。</p>
    {handoff.phase === 'awaiting_open' && <>
      <p>下一步会明确切换到这张保留的目标照片并准备完整前后对比，不会应用预设。</p>
      <button type="button" disabled={!controller.canReviewStep('open_target')} onClick={() => void controller.reviewStep('open_target')}>打开目标并准备审核</button>
    </>}
    {handoff.phase === 'reviewing' && report && <>
      <p>目标版本 {report.target.revision} · 模块 {report.module_ids.join('、')} · 原图 {report.source_size.join(' × ')} · 完整输出 {report.output_size.join(' × ')}</p>
      <small>以下为完整渲染的查看图，不是已应用结果。所有分页与整图字节都必须完成 SHA-256 核验，且两张图实际加载后才能勾选。</small>
      {images?.loading && <p role="status">正在读取并校验完整前后图像，没有提交批准…</p>}
      {images?.error && <p role="alert">{images.error}</p>}
      {!images?.loading && (!images?.before || !images.after || !!images.error) && <button type="button" onClick={() => void controller.loadReviewImages()}>重新读取审核图像（只读）</button>}
      <div className="local-workflow-review-images">{(['before', 'after'] as ReviewSide[]).map(side => <figure key={side}>
        <figcaption>{side === 'before' ? '应用前' : '候选效果（尚未应用）'}</figcaption>
        {images?.[side] ? <img key={`${images.key}:${side}`} src={images[side]!} alt={side === 'before' ? '目标照片的完整渲染应用前查看图' : '同一目标照片的预设候选完整渲染查看图'}
          onLoad={event => {const image = event.currentTarget; controller.reviewImageDisplayed(images.key, side, image.complete, image.naturalWidth, image.naturalHeight);}}
          onError={() => controller.reviewImageDisplayed(images.key, side, false, 0, 0)}/> : <p>尚无已核验图像</p>}
        <small>{report[side].width} × {report[side].height} · SHA-256：{report[side].sha256}</small>
      </figure>)}</div>
      <label className="local-workflow-review-check"><input type="checkbox" checked={images?.acknowledged ?? false} disabled={!ready || state.busy || state.pending.length > 0}
        onChange={event => {if (images) controller.acknowledgeReview(images.key, event.currentTarget.checked);}}/>我已查看这张照片的完整前后对比，批准此版本预设应用到此目标。</label>
      <button type="button" disabled={!controller.canReviewStep('approve')} onClick={() => void controller.reviewStep('approve')}>批准这张照片的预设</button>
      <small>批准只绑定当前照片、加载身份、版本与两张审核图像。核心会先记录应用意图，再由实际预设 owner 执行；不会自动保存。</small>
    </>}
    {handoff.phase === 'authorized' && <p role="status">正在核对原批准并等待核心记录应用意图。不要重新批准或另行应用预设。</p>}
    {handoff.phase === 'awaiting_save' && <>
      <p>实际预设已应用，但工程尚未完成保存。下面的按钮将保存当前工程，不能把此阶段当作全部完成。</p>
      <button type="button" disabled={!controller.canReviewStep('save_project')} onClick={() => void controller.reviewStep('save_project')}>保存已应用预设的工程</button>
    </>}
    {handoff.phase === 'awaiting_return' && <>
      <p>保存结果已由实际 owner 核对。明确返回原目标后，宿主才会继续结清此预设操作。</p>
      <button type="button" disabled={!controller.canReviewStep('return_target')} onClick={() => void controller.reviewStep('return_target')}>返回原目标并结清交接</button>
    </>}
    {preApply && <button type="button" disabled={!controller.canReviewStep('return_target')} onClick={() => void controller.reviewStep('return_target')}>取消此预设并返回原目标</button>}
    {preApply && <small>取消只在批准前可用。宿主核对返回原目标后，会按当前 stop 策略停止运行，不会应用部分预设。</small>}
    {handoff.phase === 'unknown' && <p role="alert">无法确认原操作的真实结果。仅查询原请求，不会重新打开、批准、保存、返回或释放租约。</p>}
  </section>;
}
