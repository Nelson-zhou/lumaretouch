import {useEffect, useRef, useState} from 'react';
import {LABEL, REGIONS, type InstallStatus, type Proposal, type Region, type SemanticDescriptor, type SemanticPorts} from './model';
import './skySemantic.css';

const LICENSE = 'https://huggingface.co/shi-labs/oneformer_ade20k_swin_tiny/blob/05f2812b1eccf9909b3897777450f8d68148cafc/README.md';
const mib = (n: number) => `${(n / 1048576).toFixed(1)} MiB`;

export function SkySemanticPanel({ports, onDraft, onRemove, active, disabled=false}: {
  ports: SemanticPorts; onDraft: (value: SemanticDescriptor) => void; onRemove: () => void; active: boolean; disabled?:boolean;
}) {
  const [install, setInstall] = useState<InstallStatus | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [device, setDevice] = useState<'cpu' | 'cuda'>('cpu');
  const [target, setTarget] = useState<Region>('sky');
  const [selected, setSelected] = useState<Region[]>(['sky']);
  const [seen, setSeen] = useState<Set<Region>>(new Set());
  const [photoReady, setPhotoReady] = useState(false);
  const [maskReady, setMaskReady] = useState(false);
  const [licenseRead, setLicenseRead] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<string | null>(null);
  const early = useRef<Proposal | null>(null);
  const mounted = useRef(true);
  const serial = useRef(0);

  function present(event: Proposal) {
    setProposal(event); setBusy(false); setSeen(new Set()); setPhotoReady(false); setMaskReady(false);
    if (event.state === 'ready') setSelected(event.counts?.sky ? ['sky'] : []);
    if (event.error) setError(event.error);
  }

  useEffect(() => {
    mounted.current = true;
    let off: (() => void) | null = null;
    ports.listen(event => {
      if (!mounted.current) return;
      if (!pending.current) { early.current = event; return; }
      if (event.proposal_id !== pending.current) return;
      present(event);
    }).then(fn => { if (mounted.current) off = fn; else fn(); }).catch(e => setError(String(e)));
    ports.model('status').then(value => { if (mounted.current) setInstall(value); }).catch(e => setError(String(e)));
    return () => { mounted.current = false; serial.current++; off?.(); void ports.cancel().catch(()=>{}); };
  }, [ports]);

  useEffect(() => {
    if (!install?.running) return;
    let stopped = false;
    const timer = window.setInterval(() => {
      void ports.pollModel().then(value => { if (!stopped) setInstall(value); }).catch(e => { if (!stopped) setError(String(e)); });
    }, 500);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [install?.running, ports]);

  useEffect(() => {
    if (!photoReady || !maskReady || proposal?.state !== 'ready' || seen.has(target)) return;
    let stopped = false, inner = 0;
    const outer = requestAnimationFrame(() => { inner = requestAnimationFrame(() => {
      if (stopped) return;
      void ports.shown(proposal.proposal_id, target).then(() => {
        if (!stopped) setSeen(previous => new Set([...previous, target]));
      }).catch(e => { if (!stopped) setError(String(e)); });
    }); });
    return () => { stopped = true; cancelAnimationFrame(outer); cancelAnimationFrame(inner); };
  }, [photoReady, maskReady, proposal, target, seen, ports]);

  async function model(action: 'install' | 'cancel') {
    setError(null);
    try { setInstall(await ports.model(action)); } catch (e) { setError(String(e)); }
  }
  async function start() {
    const attempt = ++serial.current;
    pending.current = null; early.current = null;
    setError(null); setBusy(true); setProposal(null); setSeen(new Set());
    try {
      const result = await ports.start(device);
      if (attempt !== serial.current || !mounted.current) return;
      pending.current = result.proposal_id;
      const arrived = early.current as Proposal | null; // Event callback can run while start awaits native response.
      if (arrived?.proposal_id === result.proposal_id) present(arrived);
      else setProposal({event: 'sky_semantic_proposal', proposal_id: result.proposal_id, state: 'running'});
      early.current = null;
    } catch (e) { if (attempt === serial.current) { setError(String(e)); setBusy(false); } }
  }
  async function accept() {
    if (!proposal || !selected.length || selected.some(region => !seen.has(region))) return;
    setBusy(true); setError(null);
    try {
      const result = await ports.accept(proposal.proposal_id, Object.fromEntries(selected.map(region => [region, 0])));
      if (result.draft_only !== true || result.requires_sky_output_review !== true) throw new Error('自动选区未返回明确的草稿审核要求');
      onDraft(result.semantic);
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  const ready = proposal?.state === 'ready';
  const runtimeError = install?.error || install?.result.error || install?.result.reason;
  return <section className="sky-semantic" aria-label="可选自动天空选区">
    <h4>自动选区（可选，本地运行）</h4>
    <p>真正的天空 / 人物 / 水面类别初选，不是人物蒙版反选。候选可能有误，请检查后用画笔补选或擦除。手工标记始终可用。</p>
    <p className="sky-semantic-warning">初选不等于已应用效果。水面不是自动反射授权：仍需明确地平线；无人照片仍需你明确声明。</p>
    {!install?.result.installed && <details open>
      <summary>获取固定模型和专用运行库</summary>
      <p>OneFormer ADE20K Swin-Tiny，权重 203,389,501 字节。{install?.result.download_bytes ? `含运行库共 ${mib(install.result.download_bytes)}。` : '完整下载量正在计算。'}</p>
      <a href={LICENSE} target="_blank" rel="noreferrer">官方 MIT 模型许可</a>
      <p>采用明确标记的 Apache-2.0 语义专用运行库分支，不替换现有显卡环境，不包含有许可兼容疑义的 regex 依赖。未进行本机质量或性能验收。</p>
      {install?.result.runtime && <details><summary>运行库版本与许可</summary><ul>{install.result.runtime.map(item => <li key={item.name}><a href={item.source} target="_blank" rel="noreferrer">{item.name} {item.version}</a> · {item.license}</li>)}</ul></details>}
      <label><input type="checkbox" checked={licenseRead} onChange={e => setLicenseRead(e.target.checked)} />我已查看许可和下载内容，允许下载并校验这些可选文件</label>
      <button disabled={!licenseRead || install?.running || !install?.result.download_bytes} onClick={() => void model('install')}>下载并校验</button>
    </details>}
    {install?.running && <div role="status"><progress value={install.result.received} max={install.result.total || 1} />{install.result.state}<button onClick={() => void model('cancel')}>取消下载</button></div>}
    {runtimeError && <p role="alert">{runtimeError}</p>}
    <label>计算设备<select value={device} disabled={busy} onChange={e => setDevice(e.target.value as 'cpu' | 'cuda')}><option value="cpu">CPU（明确选择）</option><option value="cuda">当前 GPU / ROCm</option></select></label>
    <button disabled={disabled || !install?.result.installed || busy} onClick={() => void start()}>生成区域候选</button>
    {busy && <button onClick={() => { serial.current++; pending.current = null; void ports.cancel().catch(e=>setError(String(e))).finally(()=>{setBusy(false);setProposal(null);}); }}>取消初选</button>}
    {ready && <>
      <div className="sky-semantic-regions">{REGIONS.map(region => <label key={region}>
        <input type="checkbox" disabled={!proposal.counts?.[region] || busy} checked={selected.includes(region)} onChange={e => setSelected(current => e.target.checked ? [...current, region] : current.filter(item => item !== region))} />
        <button onClick={() => { if (target !== region) { setMaskReady(false); setTarget(region); } }}>{LABEL[region]}{seen.has(region) ? ' · 已查看' : ''}</button>
        {!proposal.counts?.[region] && <small>未找到，请手工标记</small>}
      </label>)}</div>
      <div className="sky-semantic-locator">
        <img src={proposal.source_image} alt="原照片源坐标定位图，不是导出像素" onLoad={() => setPhotoReady(true)} onError={() => setError('原照片定位图显示失败')} />
        <div className={`sky-semantic-overlay ${target}`} style={{maskImage: `url(${proposal.candidate_overlays?.[target]})`, WebkitMaskImage: `url(${proposal.candidate_overlays?.[target]})`}} />
        <img key={`${proposal.proposal_id}-${target}`} className="sky-semantic-mask-load" src={proposal.candidate_overlays?.[target]} alt="" onLoad={() => setMaskReady(true)} onError={() => setError('自动选区叠加显示失败')} />
      </div>
      <p>当前叠加：{LABEL[target]}。每个要接受的区域都必须先查看；接受后进入真实天空效果预览，仍可修正。</p>
      <button disabled={disabled || busy || !selected.length || selected.some(region => !seen.has(region) || !proposal.counts?.[region])} onClick={() => void accept()}>将已查看区域放入草稿</button>
    </>}
    {active && <button disabled={disabled||busy} onClick={onRemove}>移除自动初选，保留手工画笔</button>}
    {error && <p role="alert">{error}。未应用失败的初选，手工标记仍可使用。</p>}
  </section>;
}
