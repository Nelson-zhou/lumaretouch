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
  const [modelPending, setModelPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<string | null>(null);
  const early = useRef<Proposal | null>(null);
  const mounted = useRef(true);
  const serial = useRef(0);
  const modelRequest = useRef(false);

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

  async function model(action: 'status' | 'install' | 'migrate' | 'cancel') {
    if (modelRequest.current) return;
    if (action !== 'cancel' && (install?.running || busy)) return;
    if (action === 'install' && (!licenseRead || !install?.result.download_bytes)) return;
    if (action === 'migrate' && !install?.result.migration_available) return;
    modelRequest.current = true; setModelPending(true); setError(null);
    try {
      const value = await ports.model(action);
      if (!mounted.current) return;
      setInstall(value);
      if (action === 'migrate') {
        // A copied payload is not permission to carry a previous candidate review forward.
        serial.current++; pending.current = null; early.current = null;
        setProposal(null); setSeen(new Set()); setPhotoReady(false); setMaskReady(false);
      }
    } catch (e) { if (mounted.current) setError(String(e)); }
    finally { modelRequest.current = false; if (mounted.current) setModelPending(false); }
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
  const modelWorking = modelPending || !!install?.running;
  const migrating = install?.running && install.action === 'migrate';
  const operationLabel = install?.action === 'migrate' ? '本地迁移' : install?.action === 'install' ? '下载' : '本地检查';
  return <section className="sky-semantic" aria-label="可选自动天空选区">
    <h4>自动选区（可选，本地运行）</h4>
    <p>真正的天空 / 人物 / 水面类别初选，不是人物蒙版反选。候选可能有误，请检查后用画笔补选或擦除。手工标记始终可用。</p>
    <p className="sky-semantic-warning">初选不等于已应用效果。水面不是自动反射授权：仍需明确地平线；无人照片仍需你明确声明。</p>
    {!install?.result.installed && install?.result.migration_available && <details open>
      <summary>迁移已校验的本地模型（不联网）</summary>
      <p>已找到可复用的模型和专用运行库。仅复制并校验本机现有文件，保留已有许可；不下载、不执行模型推理，也不会修改照片。</p>
      <p>本地复制量：{typeof install.result.migration_bytes === 'number' ? mib(install.result.migration_bytes) : '尚未确认'}。原有安装会保留，迁移完整校验后才启用新位置。</p>
      {install.result.migration_source_identity && <details><summary>已校验的迁移来源身份</summary><ul>{Object.entries(install.result.migration_source_identity).map(([name, value]) => <li key={name} style={{overflowWrap: 'anywhere'}}>{name}：{value}</li>)}</ul></details>}
      <p>继续沿用已有的<a href={LICENSE} target="_blank" rel="noreferrer">模型 MIT 许可</a>和专用运行库许可。本按钮不授权任何联网下载。</p>
      <p className="sky-semantic-warning">旧的已审核候选不能自动沿用。迁移后必须重新生成候选、逐区域查看，再放入草稿并审核天空效果。</p>
      <button disabled={modelWorking || busy || !install.result.migration_bytes || !install.result.migration_source_identity} onClick={() => void model('migrate')}>复制并校验已有文件（离线迁移）</button>
    </details>}
    {!install?.result.installed && install?.result.migration_reason && <p>本地迁移暂不可用：{install.result.migration_reason}。不会自动转为下载。</p>}
    {!install?.result.installed && !migrating && <details open={!install?.result.migration_available}>
      <summary>联网下载固定模型和专用运行库（单独授权）</summary>
      <p>OneFormer ADE20K Swin-Tiny，权重 203,389,501 字节。{install?.result.download_bytes ? `含运行库共 ${mib(install.result.download_bytes)}。` : '完整下载量正在计算。'}</p>
      <a href={LICENSE} target="_blank" rel="noreferrer">官方 MIT 模型许可</a>
      <p>采用明确标记的 Apache-2.0 语义专用运行库分支，不替换现有显卡环境，不包含有许可兼容疑义的 regex 依赖。未进行本机质量或性能验收。</p>
      {install?.result.runtime && <details><summary>运行库版本与许可</summary><ul>{install.result.runtime.map(item => <li key={item.name}><a href={item.source} target="_blank" rel="noreferrer">{item.name} {item.version}</a> · {item.license}</li>)}</ul></details>}
      <label><input type="checkbox" checked={licenseRead} disabled={modelWorking} onChange={e => setLicenseRead(e.target.checked)} />我已查看许可和下载内容，允许下载并校验这些可选文件</label>
      <button disabled={!licenseRead || modelWorking || busy || !install?.result.download_bytes} onClick={() => void model('install')}>联网下载并校验</button>
    </details>}
    {migrating && <p>正在离线复制并校验已有文件，不下载、不运行模型。原有安装会保留；新位置完整校验后才启用，旧候选仍需重新生成和审核。</p>}
    {install?.running && <div role="status"><progress aria-label={operationLabel} value={install.result.received} max={install.result.total || 1} />正在{operationLabel}：{install.result.state}<button disabled={modelPending} onClick={() => void model('cancel')}>取消{operationLabel}</button></div>}
    {install?.result.migrated && install.result.installed && <p role="status">{install.result.publication_warning ? '已发布通过校验的本地安装，但收尾出现警告。' : '离线迁移已完成，模型和运行库已通过校验。'}未下载、未运行推理，也未应用照片修改。</p>}
    {install?.result.publication_warning && <p className="sky-semantic-warning" role="alert">{install.result.publication_warning}。已发布的安装没有回滚，请勿把本次操作视为已取消。</p>}
    {install?.result.installed && install.result.requires_descriptor_review && <p className="sky-semantic-warning">旧模型身份下的候选审核不再有效；请重新生成候选并逐区域查看，不能直接复用旧的已审核选区。</p>}
    {runtimeError && <p role="alert">{runtimeError}</p>}
    {!install?.running && <button disabled={modelPending || busy} onClick={() => void model('status')}>重新检查本地文件（不下载）</button>}
    <label>计算设备<select value={device} disabled={busy} onChange={e => setDevice(e.target.value as 'cpu' | 'cuda')}><option value="cpu">CPU（明确选择）</option><option value="cuda">当前 GPU / ROCm</option></select></label>
    <button disabled={disabled || !install?.result.installed || busy || modelWorking} onClick={() => void start()}>生成区域候选</button>
    {busy && <button onClick={() => { serial.current++; pending.current = null; void ports.cancel().catch(e=>setError(String(e))).finally(()=>{setBusy(false);setProposal(null);}); }}>取消初选</button>}
    {ready && <>
      <div className="sky-semantic-regions">{REGIONS.map(region => <label key={region}>
        <input type="checkbox" disabled={!proposal.counts?.[region] || busy} checked={selected.includes(region)} onChange={e => setSelected(current => e.target.checked ? [...current, region] : current.filter(item => item !== region))} />
        <button onClick={() => { if (target !== region) { setMaskReady(false); setTarget(region); } }}>{LABEL[region]}{seen.has(region) ? ' · 已查看' : ''}</button>
        {!proposal.counts?.[region] && <small>未找到，请手工标记</small>}
      </label>)}</div>
      <div className="sky-semantic-locator">
        <img src={proposal.source_image} alt="当前源图坐标定位图，不是导出像素" onLoad={() => setPhotoReady(true)} onError={() => setError('当前源图定位图显示失败')} />
        <div className={`sky-semantic-overlay ${target}`} style={{maskImage: `url(${proposal.candidate_overlays?.[target]})`, WebkitMaskImage: `url(${proposal.candidate_overlays?.[target]})`}} />
        <img key={`${proposal.proposal_id}-${target}`} className="sky-semantic-mask-load" src={proposal.candidate_overlays?.[target]} alt="" onLoad={() => setMaskReady(true)} onError={() => setError('自动选区叠加显示失败')} />
      </div>
      <p>当前叠加：{LABEL[target]}。每个要接受的区域都必须先查看；接受后进入真实天空效果预览，仍可修正。</p>
      <button disabled={disabled || busy || modelWorking || !selected.length || selected.some(region => !seen.has(region) || !proposal.counts?.[region])} onClick={() => void accept()}>将已查看区域放入草稿</button>
    </>}
    {active && <button disabled={disabled||busy} onClick={onRemove}>移除自动初选，保留手工画笔</button>}
    {error && <p role="alert">{error}。未应用失败的初选，手工标记仍可使用。</p>}
  </section>;
}
