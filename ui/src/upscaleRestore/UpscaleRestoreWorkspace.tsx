// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Native dimensions are retained; no sharpening fallback.
import {useEffect, useSyncExternalStore} from 'react';
import {upscaleReviewKey} from './model';
import {upscaleImageUrl} from './imagery';
import type {UpscaleRestoreController} from './controller';
import './upscaleRestore.css';
export function UpscaleRestoreWorkspace({controller, disabled=false}: {controller: UpscaleRestoreController; disabled?: boolean}) {
  const state=useSyncExternalStore(controller.subscribe,controller.snapshot,controller.snapshot);
  const context=state.context, review=state.review, key=review?upscaleReviewKey(review):'';
  useEffect(()=>()=>controller.releasePresentation(),[controller]);
  return <section className="upscaleRestoreWorkspace" aria-label="AI 超清完整前后复核">
    <p>{state.capability.model_id} · 经典超分 · CPU 浮点完整单帧神经计算，再还原为原尺寸。不是导出尺寸放大；不会用锐化或原图冒充 AI 结果。</p>
    <p>首个支持档仅每边 16–1024 像素、总计不超过 1,048,576 像素的完整、不透明 SDR 来源；保留现有修图结果。更大照片明确拒绝，不会缩小原图、使用代理图或切块冒充完整推理。不是盲恢复或人脸重建。模型可能产生错误纹理，必须检查人脸、文字与重复图案。构建、实机画质和性能尚未验收。CPU 处理可能较慢，尚未实测耗时；等待超时仅查询原请求，不重新计算。</p>
    <p role={state.phase==='failed'||state.phase==='unknown'?'alert':'status'}>{state.message}</p>
    {context && state.source_verified && !state.stale && <figure><img src={upscaleImageUrl(context.before)} alt="当前完整修图来源" draggable={false}
      onLoad={e=>controller.sourceLoaded(context.before.sha256,e.currentTarget.naturalWidth,e.currentTarget.naturalHeight,true)}
      onError={()=>controller.sourceLoaded(context.before.sha256,0,0,false)}/><figcaption>{context.owner.source.width} × {context.owner.source.height} · 完整来源，显示 PNG 不参与模型推理</figcaption></figure>}
    <div className="upscaleRestoreActions"><button type="button" disabled={disabled||!controller.canPreview()} onClick={()=>void controller.preview()}>生成真实模型前后对比</button>
      {context&&!['applied','cancelled'].includes(state.phase)&&<button type="button" disabled={disabled||controller.unresolved()||state.phase==='cancelling'||state.terminal_refresh==='refreshing'} onClick={()=>void controller.cancel()}>取消本次恢复</button>}
      {controller.unresolved()&&<button type="button" disabled={state.checking||['applying','cancelling'].includes(state.phase)} onClick={()=>void controller.check()}>查询原提交结果</button>}</div>
    {review&&state.phase==='review'&&<section aria-label="完整前后对比"><div className="upscaleRestorePair">{(['before','after'] as const).map(side=><figure key={`${side}:${key}`}>
      <img src={upscaleImageUrl(review[side])} alt={side==='before'?'恢复前完整照片':'模型恢复后完整照片'} draggable={false}
        onLoad={e=>controller.presented(side,key,e.currentTarget.naturalWidth,e.currentTarget.naturalHeight,true)}
        onError={()=>controller.presented(side,key,0,0,false)}/><figcaption>{side==='before'?'恢复前':'恢复后'} · 完整照片</figcaption></figure>)}</div>
      {review.notes.length>0&&<ul>{review.notes.map((note,i)=><li key={i}>{note}</li>)}</ul>}
      {review.no_change&&<p>真实模型输出与原来源相同；不会声称已改善画质。</p>}
      <label><input type="checkbox" checked={state.reviewed} disabled={disabled||!controller.canPreview()||!state.before_loaded||!state.after_loaded}
        onChange={e=>controller.acknowledge(e.target.checked)}/>我已检查完整前后图，确认创建独立新图，不覆盖原图。</label></section>}
    <footer><p>只创建独立新图。项目保存和图片导出仍使用现有入口，必须另行操作。</p>
      <button type="button" disabled={disabled||!controller.canApply()} onClick={()=>void controller.apply()}>应用为独立新图</button>
      {state.terminal_refresh==='failed'&&<button type="button" onClick={()=>void controller.refreshTerminal()}>仅重试编辑器刷新</button>}</footer>
  </section>;
}
