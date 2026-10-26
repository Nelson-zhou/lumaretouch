import {useEffect, useRef, useState} from 'react';
import {runPick, type PickRun, type SessionDoc} from '../native';
import './originalFocus.css';

type Props = {docs: SessionDoc[]; selected: Set<string>; sessionId: string;
  blocked: boolean; available: boolean; running: boolean; run: PickRun | null;
  lastError: string | null; refresh: () => Promise<unknown>};
const metric = (value: number | null) => value === null ? '不可解释' : Number.isFinite(value) ? value.toPrecision(5) : '无效';

/** No local photo/result database: every card is the current canonical session row. */
export function OriginalFocusReview({docs, selected, sessionId, blocked, available, running, run, lastError, refresh}: Props) {
  const [x, setX] = useState('0.5'), [y, setY] = useState('0.5');
  const [submitting, setSubmitting] = useState(false), [note, setNote] = useState('');
  const baseline = useRef<{run: string; error: string | null} | null>(null);
  const lock = useRef(false);
  const rows = docs.filter(d => selected.has(d.document_id));
  const validSelection = rows.length >= 1 && rows.length <= 8 && rows.length === selected.size;
  const validPoint = x.trim() !== '' && y.trim() !== '' && [Number(x), Number(y)].every(n => Number.isFinite(n) && n >= 0 && n <= 1);
  const busy = running || submitting;
  const context = JSON.stringify([sessionId, rows.map(d => [d.document_id, d.source_asset_id, d.path, d.index])]);
  // Selection/source changes remove message context; results themselves never survive in local state.
  useEffect(() => {setNote('');}, [context]);
  useEffect(() => {
    if (!baseline.current) return;
    if ((run?.action === 'focus' && JSON.stringify(run) !== baseline.current.run)
      || (run?.event === 'pick_state' && run.running === false && JSON.stringify(run) !== baseline.current.run)
      || (lastError && lastError !== baseline.current.error)) {
      if (lastError && lastError !== baseline.current.error) setNote(lastError);
      lock.current = false; setSubmitting(false); baseline.current = null;
    }
  }, [run, lastError]);
  async function start() {
    if (lock.current || busy || blocked || !available || !validSelection || !validPoint) return;
    lock.current = true; setSubmitting(true); setNote('');
    baseline.current = {run: JSON.stringify(run), error: lastError};
    try {await runPick('focus', {indices: rows.map(d => d.index), focus_documents: rows.map(d => d.document_id), focus_x: Number(x), focus_y: Number(y)}); await refresh();}
    catch (error) {lock.current = false; baseline.current = null; setSubmitting(false); setNote(String(error));}
  }
  async function control(action: 'stop' | 'state') {
    try {await runPick(action); await refresh(); if (action === 'stop') setNote('已请求停止；等待引擎确认，已完成的结果保留。');}
    catch (error) {setNote(String(error));}
  }
  const focusRun = run?.action === 'focus' ? run : null;
  return <section className="original-focus" aria-label="原片焦点复核">
    <h3>原片焦点复核 · 100%</h3>
    <p>只检查显式选中的 1–8 张。Ctrl/Cmd 点击多选；隐藏的已选照片请先清除选择。不会排名、选择最佳照片、删除照片或修改星级与旗标。</p>
    <p>相同归一化原片位置，读取未编辑的原尺寸像素（每张最多 256×256），不是当前编辑画面或相机内嵌预览。RAW 请先打开原片；超过 3200 万像素或内存不足会拒绝，不降采样。</p>
    <fieldset disabled={busy || blocked || !available}>
      <legend>裁块中心（0–1；左上角为 0,0，默认中心 0.5,0.5）</legend>
      <label>X <input type="number" min="0" max="1" step="0.01" value={x} onChange={e => setX(e.target.value)}/></label>
      <label>Y <input type="number" min="0" max="1" step="0.01" value={y} onChange={e => setY(e.target.value)}/></label>
      <button type="button" disabled={!validSelection || !validPoint} onClick={() => void start()}>复核已选 {rows.length} 张原片</button>
    </fieldset>
    {!available && <p role="status">当前引擎未提供原片焦点复核，请使用更新后的引擎。</p>}
    {!validPoint && <p role="alert">X、Y 必须是 0–1 之间的有限数值。</p>}
    {!validSelection && <p role="status">请显式选择 1–8 张当前结果中的照片；不会自动处理整个图库。</p>}
    {busy && <p role="status">{submitting && !running ? '等待引擎确认…' : `正在复核 ${focusRun?.done ?? 0}/${focusRun?.total ?? focusRun?.targets ?? '…'}`}</p>}
    <button type="button" disabled={!busy} onClick={() => void control('stop')}>停止挑图任务</button>
    <button type="button" disabled={!available} onClick={() => void control('state')}>查询任务状态</button>
    {focusRun?.event === 'pick_done' && <p role="status">{focusRun.stopped ? '已停止' : '复核结束'} · 完成 {focusRun.count ?? 0} · 失败 {focusRun.failed ?? 0}</p>}
    {(focusRun?.error || (focusRun?.event === 'pick_failed' && focusRun.reason) || note) && <p role="alert">{focusRun?.error || focusRun?.reason || note}</p>}
    <p>下方为最近一次测量的原片裁块，实际矩形见各卡片；更改坐标后需重新复核。100% = 一源像素对应一 CSS 像素，不保证一物理屏幕像素。低纹理、曝光与噪声都会影响读数；这些不是对焦结论或跨照片排名。</p>
    {!busy && !blocked && validSelection && <div className="original-focus__results">{rows.map(d => {
      const r = d.pick_focus;
      const valid = r?.version === 1 && r.scope === 'original-source-crop' && r.rect.length === 4
        && r.rect.every(Number.isInteger) && r.rect[0] >= 0 && r.rect[1] >= 0
        && r.rect[2] > 0 && r.rect[2] <= 256 && r.rect[3] > 0 && r.rect[3] <= 256
        && r.rect[0] + r.rect[2] <= r.source.width && r.rect[1] + r.rect[3] <= r.source.height
        && r.preview_png.startsWith('data:image/png;base64,');
      return <article key={`${sessionId}:${d.document_id}:${d.source_asset_id}:${r?.source.sha256 ?? ''}`}>
        <h4>{d.name}{d.copy_number ? ` · 副本 ${d.copy_number}（仍检查原片）` : ''}</h4>
        {d.pick_focus_error ? <p role="alert">{d.pick_focus_error}</p> : valid && r ? <>
          <div className="original-focus__pixels"><img src={r.preview_png} alt={`${d.name} 原片 100% 裁块`}
            width={r.rect[2]} height={r.rect[3]} style={{width: r.rect[2], height: r.rect[3], maxWidth: 'none', maxHeight: 'none', objectFit: 'none'}}/></div>
          <p>原片 {r.source.width}×{r.source.height} · {r.source_bits} bit · 中心 {r.point?.join(', ')} · 裁块 [x,y,w,h] = [{r.rect.join(', ')}]</p>
          <details><summary>原片 SHA-256</summary><code>{r.source.sha256}</code></details>
          <dl><dt>局部对比度</dt><dd>{metric(r.contrast)}</dd><dt>梯度能量</dt><dd>{metric(r.gradient_energy)}</dd><dt>拉普拉斯方差</dt><dd>{metric(r.laplacian_variance)}</dd><dt>细节 / 对比度</dt><dd>{metric(r.detail_to_contrast)}</dd></dl>
          {r.low_contrast && <p>低对比度 / 低纹理：细节比不应解释为清晰度结论。</p>}
          {r.notes.map((text, i) => <p key={i}>{text}</p>)}
        </> : <p>{r ? '结果格式不完整，已隐藏。请重新复核。' : '暂无有效原片复核；引擎发现源文件变化后会隐藏旧结果，请重新复核。'}</p>}
      </article>;
    })}</div>}
  </section>;
}
