import {useEffect, useId, useRef, useState} from 'react';
import {settleCurveEdit} from '../curveEditBarrier';
import {affectedRows, changedRows, isOutcome, isState, rowLabel, sameOperationProject,
  type PendingVirtualCopy, type VirtualCopyAction, type VirtualCopyEnvelope, type VirtualCopyState} from './model';
import {bounded, clearPending, pendingFor, receipt, request, retainPending, unboundPendingFor} from './nativePort';
import './virtualCopies.css';

export interface VirtualCopyControlsProps {
  /** Changes when the caller opens/replaces a project. Native workspace is the write fence. */
  projectKey: string;
  refreshKey?: string;
  /** Refresh session/project state after a confirmed mutation; the engine marks project dirty. */
  onChanged: () => void;
  activeDocumentId?: string;
  /** Canonical document IDs from gallery selection, never source paths or load IDs. */
  selectedDocumentIds?: string[];
  disabled?: boolean;
}
const POLL_MS = 300;
const DEADLINE_MS = 15000;
const actionLabels: Record<VirtualCopyAction, string> = {create: '创建虚拟副本', trash: '移到回收站', restore: '恢复'};

export function VirtualCopyControls({projectKey, refreshKey, onChanged, activeDocumentId, selectedDocumentIds, disabled = false}: VirtualCopyControlsProps) {
  const id = useId();
  const [state, setState] = useState<VirtualCopyState | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [scope, setScope] = useState<'active' | 'trash' | 'all'>('active');
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<PendingVirtualCopy | null>(null);
  const [review, setReview] = useState<'trash' | 'restore' | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const generation = useRef(0);
  const active = useRef<string | null>(null);
  const mounted = useRef(false);
  const snapshot = useRef(state); snapshot.current = state;
  const changed = useRef(onChanged); changed.current = onChanged;
  const shortcut = useRef<() => void>(() => {});
  const panel = useRef<HTMLElement | null>(null);
  const externalSelectionKey = selectedDocumentIds === undefined ? undefined : JSON.stringify(selectedDocumentIds);

  function showState(value: VirtualCopyState) {
    if (snapshot.current?.workspace !== value.workspace) setSelected([]);
    setState(value); snapshot.current = value;
    setPending(pendingFor(value.workspace, value.project_id));
    setSelected(old => old.filter(documentId => value.rows.some(row => row.document_id === documentId)));
  }

  function markUnknown(operation: PendingVirtualCopy | null, message: string) {
    if (operation) { retainPending(operation); setPending(operation); }
    setNotice(message);
  }

  function accept(envelope: VirtualCopyEnvelope, action: string, operation: PendingVirtualCopy | null): void {
    if (!envelope.success) {
      // A failed readback does not establish the original mutation's outcome.
      if (operation && action !== 'query') {
        clearPending(operation.workspace, operation.request_id); setPending(null);
      }
      setError(envelope.error || '操作未完成');
      return;
    }
    if (action === 'state') {
      if (!isState(envelope.result)) throw new Error('工程清单回执无效，未采用');
      showState(envelope.result);
      setReview(null);
      setNotice(pendingFor(envelope.result.workspace, envelope.result.project_id)
        ? '已读取当前清单，但原操作仍待确认。请查询原操作；清单读取不会重试，也不会自动解除待确认状态。'
        : '已读取当前工程清单。虚拟副本共享原图，编辑记录独立。');
      return;
    }
    if (!operation || !isOutcome(envelope.result) || envelope.result.operation_id !== operation.request_id)
      throw new Error('原操作回执身份或内容不匹配，未采用');
    const outcome = envelope.result;
    if (outcome.state && (!sameOperationProject(operation, outcome.state)
      || (action !== 'query' && outcome.state.workspace !== operation.workspace)))
      throw new Error('工程身份已变化，未采用旧操作回执；原操作仍待确认');
    if (outcome.status === 'pending' || outcome.status === 'unknown') {
      if (outcome.state) showState(outcome.state);
      markUnknown(operation, outcome.status === 'pending'
        ? '原操作仍在处理。稍后可再次查询；不会重新提交修改。'
        : '原操作结果尚未确认。请查询原操作或读取当前清单核对；不会自动重试。');
      return;
    }
    if (outcome.status === 'succeeded' && !outcome.state) throw new Error('成功回执缺少工程清单，请查询原操作');
    clearPending(operation.workspace, operation.request_id); setPending(null);
    if (outcome.state) showState(outcome.state);
    setReview(null);
    if (outcome.status === 'failed') { setError(outcome.error || envelope.error || '原操作失败，未自动重试。请刷新后重新审核。'); return; }
    setSelected([]);
    const count = outcome.changed_document_ids?.length;
    setNotice(action === 'query'
      ? `${actionLabels[operation.action]}的原操作结果已确认。没有重新执行或自动保存；当前是否需要保存，以工程状态为准。`
      : `${actionLabels[operation.action]}已确认${count === undefined ? '' : `，涉及 ${count} 个文档`}。工程有未保存修改，请使用“保存工程”；原图文件未修改。`);
    try { changed.current(); } catch (reason) { setError(`操作已确认，但界面刷新失败：${String(reason)}`); }
  }

  async function run(action: string, payload: Record<string, unknown> = {}, operation: PendingVirtualCopy | null = null) {
    if (active.current) return;
    const requestId = operation && action !== 'query' ? operation.request_id : crypto.randomUUID();
    const epoch = generation.current;
    const current = () => mounted.current && generation.current === epoch;
    active.current = requestId; setBusy(true); setError('');
    let submitted = false;
    try {
      if (operation && action !== 'query') {
        // A timeout while settling an edit must not send a mutation later.
        await bounded(settleCurveEdit(), 6000);
        if (!current()) return;
        retainPending(operation); setPending(operation);
      }
      submitted = true;
      await bounded(request({action, request_id: requestId, ...payload}), 6000);
      if (!current()) return;
      const until = Date.now() + DEADLINE_MS;
      while (current() && Date.now() < until) {
        const value = await bounded(receipt(requestId), Math.max(1, Math.min(4000, until - Date.now())));
        if (!current()) return;
        if (value.result) { accept(value.result, action, operation); return; }
        if (value.phase === 'unknown') {
          markUnknown(operation, '回执当前不可用。请查询原操作或读取当前清单核对；不会自动重试。'); return;
        }
        await new Promise(resolve => setTimeout(resolve, POLL_MS));
      }
      if (current()) markUnknown(operation, '等待已停止，结果仍待确认。请查询原操作；不会自动重发。');
    } catch (reason) {
      if (current()) {
        setError(String(reason));
        if (operation && submitted) markUnknown(operation, '发送或接收结果未确认。原请求已保留，只允许查询，不会自动重试修改。');
      }
    } finally {
      if (current() && active.current === requestId) { active.current = null; setBusy(false); }
    }
  }

  useEffect(() => {
    mounted.current = true; generation.current += 1; active.current = null;
    snapshot.current = null; setState(null); setSelected([]); setPending(null); setReview(null);
    setError(''); setNotice(''); setBusy(false);
    void run('state', {workspace: ''});
    return () => {
      mounted.current = false; generation.current += 1;
      // Never cancel, resend, or forget a mutation when switching gallery/retouch.
    };
  }, [projectKey]);

  useEffect(() => {
    if (!mounted.current || !snapshot.current || active.current || pendingFor(snapshot.current.workspace, snapshot.current.project_id)) return;
    if (review) { setReview(null); setNotice('文档已改变，请重新审核受影响文档。'); }
    void run('state', {workspace: snapshot.current.workspace});
  }, [refreshKey]);

  useEffect(() => {
    if (externalSelectionKey === undefined || !state) return;
    const ids = new Set<string>(JSON.parse(externalSelectionKey) as string[]);
    setSelected(state.rows.filter(row => ids.has(row.document_id)).map(row => row.document_id));
    setReview(null);
  }, [externalSelectionKey, state?.workspace]);

  useEffect(() => {
    const showContext = (event: Event) => {
      const detail = (event as CustomEvent<{documentId?: unknown; documentIds?: unknown; action?: unknown}>).detail;
      const value = snapshot.current;
      const documentIds = typeof detail?.documentId === 'string' ? [detail.documentId]
        : Array.isArray(detail?.documentIds) && detail.documentIds.every(item => typeof item === 'string')
          ? [...new Set(detail.documentIds as string[])] : [];
      if (!value || !documentIds.length) return;
      const rows = value.rows.filter(row => documentIds.includes(row.document_id));
      if (rows.length !== documentIds.length) { setError('部分文档未在当前清单中，请刷新后重新选择。'); return; }
      const action = detail?.action === 'trash' || detail?.action === 'restore' ? detail.action : null;
      setSelected(documentIds); setScope('all'); setReview(null);
      if (action && rows.every(row => action === 'trash' ? !row.trashed : row.trashed)) setReview(action);
      else if (action) setError('正常文档与回收站文档不能混合执行此操作，请分开选择。');
      setNotice(action ? '已打开受影响文档审核。确认前不会修改工程。'
        : '已定位右键文档。请选择创建副本、审核移到回收站或审核恢复；右键本身不会修改工程。');
      panel.current?.scrollIntoView({block: 'nearest'}); panel.current?.focus();
    };
    window.addEventListener('lrt-virtual-copy-context', showContext);
    return () => window.removeEventListener('lrt-virtual-copy-context', showContext);
  }, []);

  const visible = (state?.rows ?? []).filter(row => scope === 'all' || (scope === 'trash' ? row.trashed : !row.trashed));
  const chosen = visible.filter(row => selected.includes(row.document_id));
  const allActive = chosen.length > 0 && chosen.every(row => !row.trashed);
  const allTrashed = chosen.length > 0 && chosen.every(row => row.trashed);
  const locked = disabled || busy || !!pending || !state;
  const affected = state && review ? affectedRows(state, chosen.map(row => row.document_id), review) : [];
  const changing = review ? changedRows(affected, review) : [];
  const cascade = changing.filter(row => !chosen.some(item => item.document_id === row.document_id));
  const unbound = state ? unboundPendingFor(state.workspace) : [];

  function mutate(action: VirtualCopyAction, documentIds = chosen.map(row => row.document_id)) {
    const value = snapshot.current;
    if (!value || disabled || active.current || pendingFor(value.workspace, value.project_id) || !documentIds.length) return;
    const picked = value.rows.filter(row => documentIds.includes(row.document_id));
    if (picked.length !== documentIds.length || picked.some(row => action === 'restore' ? !row.trashed : row.trashed)) {
      setError('选择状态已变化，请刷新清单并重新选择。'); setReview(null); return;
    }
    const rows = affectedRows(value, documentIds, action);
    const requestId = crypto.randomUUID();
    void run(action, {workspace: value.workspace, project_id: value.project_id, document_ids: documentIds,
      expected_revisions: Object.fromEntries(rows.map(row => [row.document_id, row.revision])), operation_id: requestId},
    {request_id: requestId, workspace: value.workspace, project_id: value.project_id, action, document_ids: documentIds});
  }

  shortcut.current = () => {
    if (locked || review) return;
    if (allActive) mutate('create');
    else if (chosen.length === 0 && activeDocumentId && state?.rows.some(row => row.document_id === activeDocumentId && !row.trashed))
      mutate('create', [activeDocumentId]);
  };
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      const target = event.target;
      if (event.defaultPrevented || event.repeat || event.altKey || event.shiftKey || !(event.metaKey || event.ctrlKey)
        || (event.key !== "'" && event.code !== 'Quote')
        || (target instanceof HTMLElement && (target.isContentEditable || !!target.closest('input,textarea,select,[role="textbox"]')))) return;
      event.preventDefault(); shortcut.current();
    };
    window.addEventListener('keydown', keydown);
    return () => window.removeEventListener('keydown', keydown);
  }, []);

  async function queryOriginal() {
    const current = snapshot.current;
    if (!pending || !current || active.current || !sameOperationProject(pending, current)) return;
    // Querying the engine is read-only and names the ORIGINAL operation. The host
    // status endpoint is polled only for this new readback's correlated receipt.
    await run('query', {workspace: current.workspace, project_id: current.project_id,
      original_workspace: pending.workspace, operation_id: pending.request_id}, pending);
  }

  return <section ref={panel} tabIndex={-1} className="virtual-copies" aria-label="虚拟副本" aria-busy={busy}>
    <div className="virtual-copies__header"><strong>虚拟副本</strong><span>同一原图，独立编辑</span></div>
    <p className="virtual-copies__hint">创建时复制所选文档的编辑状态，不复制原图文件。后续编辑互不影响，保存工程后保留。</p>
    <div className="virtual-copies__toolbar">
      <label htmlFor={`${id}-scope`}>显示 <select id={`${id}-scope`} value={scope} disabled={busy}
        onChange={event => { setScope(event.target.value as typeof scope); setReview(null); }}>
        <option value="active">正常文档</option><option value="trash">回收站</option><option value="all">全部文档</option>
      </select></label>
      <button type="button" disabled={locked || !visible.length} onClick={() => { setSelected(visible.map(row => row.document_id)); setReview(null); }}>选择当前可见</button>
      <button type="button" disabled={busy || !selected.length} onClick={() => { setSelected([]); setReview(null); }}>清除选择</button>
      <span>{chosen.length} 个可见文档已选</span>
    </div>
    <div className="virtual-copies__list" role="group" aria-label="按文档身份选择照片">
      {visible.map(row => <label key={row.document_id} className="virtual-copies__row" data-trashed={row.trashed}>
        <input type="checkbox" disabled={locked} checked={selected.includes(row.document_id)}
          onChange={event => { const checked = event.target.checked; setSelected(old => checked ? [...old, row.document_id] : old.filter(value => value !== row.document_id)); setReview(null); }}/>
        <span className="virtual-copies__name" title={`${row.path}\n文档：${row.document_id}`}>
          {rowLabel(row)}{row.trashed && <em>回收站</em>}{row.document_id === activeDocumentId && <em>当前编辑</em>}
        </span>
      </label>)}
      {state && visible.length === 0 && <p>此范围没有文档。</p>}
      {!state && <p role="status">{busy ? '正在读取工程清单…' : '尚未取得工程清单，请刷新。'}</p>}
    </div>
    <div className="virtual-copies__toolbar">
      <button type="button" disabled={locked || !allActive || !!review} aria-keyshortcuts="Control+' Meta+'"
        title="Ctrl / Cmd + '；每个选中文档创建一个独立虚拟副本" onClick={() => mutate('create')}>
        {chosen.length > 1 ? `批量创建 ${chosen.length} 个虚拟副本` : '创建虚拟副本'}
      </button>
      <button type="button" disabled={locked || !allActive} onClick={() => setReview('trash')}>审核移到回收站</button>
      <button type="button" disabled={locked || !allTrashed} onClick={() => setReview('restore')}>审核恢复</button>
    </div>
    <p className="virtual-copies__hint">Ctrl / Cmd + ' 创建副本。只处理当前可见的选择；无选择时快捷键可用于当前编辑文档。</p>
    <p className="virtual-copies__semantics">删除原件：原件及全部关联副本一起进回收站。删除副本：仅该副本。恢复副本：同时恢复其原件，不恢复其他副本。恢复原件：仅原件。以上操作都不删除源文件。</p>
    {review && <div className="virtual-copies__review" role="region" aria-label="审核受影响文档">
      <strong>{actionLabels[review]}：将改变 {changing.length} 个文档{cascade.length ? `，含联动的 ${cascade.length} 个` : ''}</strong>
      <ul>{changing.map(row => <li key={row.document_id}>{rowLabel(row)}{cascade.some(item => item.document_id === row.document_id) ? '（联动）' : ''}</li>)}</ul>
      <p>仅改变工程内的回收站状态，不移动或删除任何原图文件。此次修改尚需保存工程。</p>
      <button type="button" disabled={locked || !changing.length} onClick={() => mutate(review)}>确认{actionLabels[review]}（{changing.length} 个）</button>
      <button type="button" disabled={busy} onClick={() => setReview(null)}>取消</button>
    </div>}
    {pending && <div className="virtual-copies__uncertain" role="status">
      <p>“{actionLabels[pending.action]}”结果待确认。已锁定新修改，避免重复创建或误操作。</p>
      {pending.workspace !== state?.workspace && <p>这是同一已保存工程的旧会话操作。将查询原操作记录，不会在新会话重新执行。</p>}
      <button type="button" disabled={busy || disabled} onClick={() => void queryOriginal()}>查询原操作结果</button>
      <button type="button" disabled={busy || disabled} onClick={() => void run('state', {workspace: state?.workspace ?? '', project_id: state?.project_id ?? null})}>读取当前清单（不重试）</button>
      <small>即使离开此面板，也不会取消或重新发送原操作。</small>
    </div>}
    {unbound.length > 0 && <p className="virtual-copies__uncertain" role="status">
      另有 {unbound.length} 个旧的未保存会话操作仍是未知结果，无法可靠关联到当前工程。它们没有被重试或视为成功，也不会绑定到其他工程。
    </p>}
    {!pending && <button type="button" disabled={busy || disabled} onClick={() => void run('state', {workspace: state?.workspace ?? ''})}>刷新文档清单</button>}
    {notice && <p role="status" aria-live="polite">{notice}</p>}
    {error && <p className="virtual-copies__error" role="alert">{error}</p>}
  </section>;
}
