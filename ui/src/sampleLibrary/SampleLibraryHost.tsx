import { useEffect, useRef } from 'react';
import { SampleLibraryPanel } from './SampleLibraryPanel';
import type { SampleLibraryOwner } from './useSampleLibraryHost';

export function SampleLibraryLaunch({ owner }: { owner: SampleLibraryOwner }) {
  return <section className="sampleLibraryLaunch" data-readonly-scopes aria-label="本地样片与参考选择">
    <div><button type="button" disabled={!owner.enabled} onClick={() => owner.show('manage')}>管理本地样片库</button>
      <button type="button" disabled={!owner.enabled} onClick={() => owner.show('reference')}>选择参考样片</button></div>
    {!owner.enabled && <small>启动支持本地样片库的配套引擎后可使用，无需先打开照片。</small>}
    <small>只管理自己拥有使用权的本地样片；选择参考不会自动调色，也不代表 AI 追色已接通。</small>
    {owner.selectedReference && <div className="sampleLibraryReferenceChoice" role="status">
      <strong>已选择本地参考样片</strong>
      <span>原片 {owner.selectedReference.source.width} × {owner.selectedReference.source.height} · 来源与渲染身份已校验</span>
      <details><summary>稳定参考身份</summary><dl>
        <dt>样片</dt><dd>{owner.selectedReference.sample_id}</dd>
        <dt>原片 SHA-256</dt><dd>{owner.selectedReference.source.sha256}</dd>
        <dt>渲染 SHA-256</dt><dd>{owner.selectedReference.render_sha256}</dd>
        <dt>资源</dt><dd>{owner.selectedReference.asset_id}</dd>
      </dl></details>
      <button type="button" onClick={owner.clearSelectedReference}>清除参考选择</button>
    </div>}
  </section>;
}
/** Kept mounted while hidden so closing cannot discard an uncertain write owner. */
export function SampleLibraryHost({ owner }: { owner: SampleLibraryOwner }) {
  const region = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!owner.open) return;
    const previous = document.activeElement;
    region.current?.focus();
    return () => { if (previous instanceof HTMLElement && previous.isConnected) previous.focus(); };
  }, [owner.open]);
  return <div ref={region} hidden={!owner.open} tabIndex={-1} className="sampleLibraryHost" data-readonly-scopes
    role="region" aria-label="本地样片库工作区" onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); owner.close(); } }}>
    {owner.contextPending && <p role="status">正在核对当前照片的原尺寸保存状态…</p>}
    {owner.contextError && <p role="alert">{owner.contextError} <button type="button" onClick={owner.refreshContext}>重新核对当前照片</button></p>}
    <SampleLibraryPanel port={owner.port} open={owner.open} mode={owner.mode} captureContext={owner.captureContext}
      referenceTargetKey={owner.documentId} onReferenceSelected={owner.setSelectedReference} onClose={owner.close}/>
  </div>;
}
