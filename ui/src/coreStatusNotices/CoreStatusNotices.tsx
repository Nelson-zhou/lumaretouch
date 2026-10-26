import type {CoreStatusView} from './model';

/** Always mounted in the production stage, not behind development controls. */
export function CoreStatusNotices({facts}: {facts: CoreStatusView | null}) {
  if (!facts) return null;
  return <section aria-label="当前图像的引擎与色彩说明" style={{flex: '0 0 auto', maxHeight: 180, overflow: 'auto', padding: '6px 12px', fontSize: 13, lineHeight: 1.5, overflowWrap: 'anywhere'}}>
    <div>当前图像载入设备：{facts.device ?? '引擎未报告'}
      {facts.device === 'cpu' && !facts.fallback && '（CPU；仅凭此项不能判定发生了回退）'}</div>
    {facts.fallback && <p role="status" style={{margin: '4px 0'}}>设备回退：{facts.fallback}</p>}
    {!facts.fallbackReported && <div>本次载入的设备回退原因未报告。</div>}
    {facts.notes.length > 0 && <div aria-label="当前图像解码说明">
      {facts.notes.map((note, index) => <div key={`${facts.loadId}:${index}`}>{note}</div>)}
    </div>}
    {facts.resources.length > 0 && <details>
      <summary>载入时资源快照（不是实时内存或可用额度）</summary>
      <ul style={{margin: '4px 0', paddingLeft: 20}}>{facts.resources.map(item =>
        <li key={item.label}>{item.label}：{item.bytes.toLocaleString('zh-CN')} 字节</li>)}</ul>
      <div>仅列引擎已报告的项目；不相加为总内存，也不据此承诺性能或质量。</div>
    </details>}
  </section>;
}
