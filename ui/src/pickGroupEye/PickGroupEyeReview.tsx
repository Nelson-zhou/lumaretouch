import {useEffect, useRef, useState} from 'react';
import {runPick, type PickGroupEyeCapability, type PickRun, type SessionDoc} from '../native';
import {eyeStatus, pickFailure, ruleCapability} from './model';
import '../originalFocus/originalFocus.css';

type Props = {docs: SessionDoc[]; selected: Set<string>; sessionId: string; blocked: boolean;
  capability?: PickGroupEyeCapability; running: boolean; run: PickRun | null;
  lastError: string | null; refresh: () => Promise<unknown>};

/** Backend session rows own all evidence/results; editing the draft does not apply it. */
export function PickGroupEyeReview({docs, selected, sessionId, blocked, capability, running, run, lastError, refresh}: Props) {
  const [enabled, setEnabled] = useState(false), [threshold, setThreshold] = useState('3');
  const [submitting, setSubmitting] = useState(false), [note, setNote] = useState('');
  const lock = useRef(false), baseline = useRef<{sequence: number; error: string | null} | null>(null);
  const available = ruleCapability(capability);
  const rows = docs.filter(d => selected.has(d.document_id));
  const validSelection = rows.length >= 1 && rows.length <= 8 && rows.length === selected.size;
  const n = Number(threshold);
  const validRule = !enabled || (threshold.trim() !== '' && Number.isInteger(n)
    && n >= (capability?.min ?? 1) && n <= (capability?.max ?? 0));
  const busy = running || submitting;
  const context = JSON.stringify([sessionId, rows.map(d => [d.document_id, d.source_asset_id, d.path, d.index])]);
  useEffect(() => {setNote('');}, [context]);
  useEffect(() => {
    if (!baseline.current) return;
    if ((run?.host_sequence ?? 0) !== baseline.current.sequence || (lastError && lastError !== baseline.current.error)) {
      if (lastError && lastError !== baseline.current.error) setNote(lastError);
      baseline.current = null; lock.current = false; setSubmitting(false);
    }
  }, [run, lastError]);
  async function request(action: 'analyze' | 'group_rule') {
    if (lock.current || busy || blocked || !available || !validSelection || (action === 'group_rule' && !validRule)) return;
    lock.current = true; setSubmitting(true); setNote('');
    baseline.current = {sequence: run?.host_sequence ?? 0, error: lastError};
    try {
      await runPick(action, {indices: rows.map(d => d.index), pick_documents: rows.map(d => d.document_id),
        ...(action === 'analyze' ? {force: true} : {group_eye_rule: {version: 1, more_than: enabled ? n : null}})});
      await refresh();
    } catch (error) {baseline.current = null; lock.current = false; setSubmitting(false); setNote(String(error));}
  }
  async function control(action: 'stop' | 'state') {
    try {await runPick(action); await refresh(); if (action === 'stop') setNote('已请求停止，等待引擎确认。');}
    catch (error) {setNote(String(error));}
  }
  return <section className="original-focus" aria-label="闭眼提示的多人例外">
    <h3>闭眼提示 · 可选多人例外</h3>
    <p>默认关闭。仅当同一次真实检测的脸数严格多于 N 时，按你的规则省略闭眼提示。检测最多 {capability?.detection_limit ?? 32} 张脸，不是完整人数统计；不识别大笑、不判断某张脸清晰，也不自动选片或修改星级、旗标、回收站。</p>
    <fieldset disabled={busy || blocked || !available}>
      <legend>规则草稿（改动后需显式应用）</legend>
      <label><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)}/>启用检测脸数例外</label>
      <label>严格多于 N = <input type="number" min={capability?.min} max={capability?.max} step="1" disabled={!enabled} value={threshold} onChange={e => setThreshold(e.target.value)}/></label>
      <button type="button" disabled={!validSelection || !validRule} onClick={() => void request('group_rule')}>仅重算已选缓存（不检测）</button>
      <button type="button" disabled={!validSelection} onClick={() => void request('analyze')}>重新测量已选 {rows.length} 张（例外关闭）</button>
    </fieldset>
    <p>规则应用不运行模型；缺失或过期缓存保持未知。重新测量会运行现有 FaceMesh 和代理读数，使用默认敏感度并关闭本次所选照片的例外；不是新增 AI 分类器。读数来自解码代理，可能是相机内嵌预览；不是原片质量结论。共享源路径的虚拟副本请在该来源的首个文档上测量；缓存规则仅作用于明确选择的文档。</p>
    {!available && <p role="status">引擎未提供版本1规则接口；不能应用例外。</p>}
    {!validSelection && <p role="status">请显式选择当前可见结果中的1–8张；隐藏的选择请先清除。不会自动处理全图库。</p>}
    {!validRule && <p role="alert">N 必须是 {capability?.min}–{capability?.max} 的整数。</p>}
    <button type="button" disabled={!busy} onClick={() => void control('stop')}>停止挑图任务</button>
    <button type="button" disabled={!available} onClick={() => void control('state')}>查询任务状态</button>
    {busy && <p role="status">{submitting && !running ? '等待引擎确认…' : '挑图任务运行中；当前规则结果待确认。'}</p>}
    {run?.action === 'group_rule' && run.event === 'pick_done' && <p role="status">缓存规则处理结束 · 更新 {run.count ?? 0} · 未完成 {run.failed ?? 0} · 没有重新检测</p>}
    {(note || pickFailure(run)) && <p role="alert">{note || pickFailure(run)}</p>}
    {!busy && !blocked && validSelection && <div className="original-focus__results">{rows.map(d => {
      const p = d.pick, detection = p?.measures.face_detection;
      return <article key={`${sessionId}:${d.document_id}:${d.source_asset_id}`}>
        <h4>{d.name}</h4><p>{eyeStatus(p)}</p>
        {d.pick_error && <p role="alert">{d.pick_error}</p>}
        {p && <>
          <p>此缓存的已应用规则：{p.group_eye_rule?.more_than == null ? '关闭' : `检测脸数严格多于 ${p.group_eye_rule.more_than}`} · 状态 {p.group_eye_rule_state ?? '旧版本未知'}</p>
          {detection?.status === 'verified' ? <p>同次检测 {detection.count} 张脸 / 上限 {detection.limit}{detection.limit_reached ? '（达到上限，可能漏检）' : '（仍可能漏检）'} · 解码尺寸 {detection.decode_size.join('×')}</p> : <p>无可用于例外的当前检测脸数；不从旧元数据猜测。</p>}
          {p.reasons.filter(r => r.kind.startsWith('eyes_')).map((r, i) => <p key={i}>{r.text}</p>)}
          {p.overridden_by_user && <p>已有人工标记优先；规则未修改你的决定。</p>}
          {detection?.status === 'verified' && <details><summary>检测证据身份（不是完整人数统计）</summary>
            <p>{detection.backend} · {detection.schema}</p><code>{detection.detector_sha256}</code>
            <p>模型：{detection.model_path}</p><p>来源：{detection.source_path}</p>
            <p>文件变更戳：{detection.source_stamp.join(', ')}</p>
          </details>}
        </>}
      </article>;
    })}</div>}
  </section>;
}
