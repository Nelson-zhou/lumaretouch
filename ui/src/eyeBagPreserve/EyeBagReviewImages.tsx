// SPDX-License-Identifier: GPL-3.0-or-later
import {imageKey, memberKey, members, type EyeBagReview, type EyeBagSide} from './model';
import {pairReady, type EyeBagAccepted, type EyeBagImages, type EyeBagLoaded} from './reviewState';
/** Only the selected logical document's full-mixed pair is paged in. Geometry stays source-owned. */
export function EyeBagReviewImages({review, page, onPage, images, loaded, accepted, supportAccepted, busy,
  onAccepted, onSupportAccepted, onLoaded, onError}: {
  review: EyeBagReview; page: number; onPage: (page: number) => void; images: EyeBagImages; loaded: EyeBagLoaded;
  accepted: EyeBagAccepted; supportAccepted: boolean; busy: boolean;
  onAccepted: (key: string, value: boolean) => void; onSupportAccepted: (value: boolean) => void;
  onLoaded: (side: EyeBagSide, documentId: string, element: HTMLImageElement) => void;
  onError: (side: EyeBagSide, documentId: string) => void;
}) {
  const all = members(review), member = all[page];
  if (!member) return null;
  const supportKey = imageKey(review, 'support'), key = memberKey(review, member.visual);
  const supportReady = !!images[supportKey] && loaded[supportKey] === true;
  const ready = pairReady(review, member, images, loaded) && supportReady;
  const figure = (side: EyeBagSide, documentId: string) => {
    const key = imageKey(review, side, documentId), image = images[key];
    const caption = side === 'support' ? '共享来源保护几何：青色满覆盖 1，琥珀色部分覆盖，无色 0；底图是未修补的来源参考，不代表任一成员的修补结果'
      : `${review.version === 2 ? `成员 ${page + 1}：` : ''}${side === 'before' ? '修改前完整混合人像实际渲染' : '候选修改后完整混合人像实际渲染（尚未应用）'}`;
    return <figure key={key}>
      <figcaption>{caption}</figcaption>
      {image ? <img src={`data:image/png;base64,${image.base64}`} alt={caption} style={{maxWidth: '100%', height: 'auto'}}
        onLoad={event => onLoaded(side, documentId, event.currentTarget)} onError={() => onError(side, documentId)}/>
        : <p role="status">正在读取审核图…</p>}
    </figure>;
  };
  return <>
    <p>来源 {review.support_source.source_width} × {review.support_source.source_height}；本次实际解码保护网格 {review.support_source.decoded_width} × {review.support_source.decoded_height}，下方仅显示缩略图。</p>
    <p>候选尚未应用。请检查保护范围、此脸、邻近人物和背景；这些是真实渲染的缩略图，不是原尺寸质量验收。</p>
    {figure('support', review.visual.document_id)}
    {review.version === 2 && <>
      <label><input type="checkbox" checked={supportAccepted} disabled={busy || !supportReady} onChange={event => onSupportAccepted(event.target.checked)}/>
        我已查看这份源图几何保护范围；它不是每张成员的已修补眼部检查图</label>
      <div role="group" aria-label="全部共享来源祛眼袋成员审核">
        <p role="status">此脸和卧蚕保护属于同一来源，将整体影响全部 {all.length} 张逻辑照片。当前照片列第一；每张分别使用自己的像素、已提交修补、裁剪与混合渲染，不复制当前成员的修补结果，也不向不同来源迁移保护。</p>
        <ol>{all.map((item, index) => <li key={memberKey(review, item.visual)}>
          <button type="button" disabled={busy} aria-current={index === page ? 'step' : undefined} onClick={() => onPage(index)}>
            {index + 1}. {item.path}{index === 0 ? '（当前）' : ''} · {accepted[memberKey(review, item.visual)] ? '已逐张确认' : '待审核'}
          </button><span> 文档 {item.visual.document_id} · 版本 {item.visual.revision}</span>
        </li>)}</ol>
        <p>正在审核第 {page + 1} / {all.length} 张：{member.path}</p>
      </div>
    </>}
    {figure('before', member.visual.document_id)}{figure('after', member.visual.document_id)}
    <label><input type="checkbox" checked={accepted[key] === true} disabled={busy || !ready}
      onChange={event => onAccepted(key, event.target.checked)}/>
      {review.version === 2 ? `我已查看第 ${page + 1} 张真实完整前后图，接受此成员随全部共享成员一起修改`
        : '我已查看真实保护范围和完整修改前后图，接受此脸当前候选'}{review.replace_legacy ? '，并明确替换旧版眼袋程度' : ''}</label>
    {review.version === 2 && <p role="status">已确认 {all.filter(item => accepted[memberKey(review, item.visual)]).length} / {all.length} 张。
      <button type="button" disabled={busy || page === 0} onClick={() => onPage(page - 1)}>上一张</button>
      <button type="button" disabled={busy || page === all.length - 1} onClick={() => onPage(page + 1)}>下一张</button>
    </p>}
  </>;
}
