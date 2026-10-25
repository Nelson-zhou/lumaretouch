import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createNativeBackgroundMaterialLibrary } from './nativePort';
import type { BackgroundMaterialPort, RequestOptions } from './adapter';
import { MaterialError, PAGE_SIZE, UNGROUPED, errorText, parseSelection, type ImportOutcome, type Material,
  type MaterialCommand, type MaterialPage, type MaterialQuery, type MaterialSelection, type MaterialSnapshot } from './model';

export type MaterialCaller = { targetKey: string; onChoose: (selection: MaterialSelection) => void | Promise<void> };
type Job = { label: string; write: boolean; controller: AbortController; session: number };
const initialQuery = (): MaterialQuery => ({ group_id: null, text: '', trash: false, sort: 'manual', offset: 0, limit: PAGE_SIZE });

/** Mount once in App, not in the conditional ID panel. Close hides the view only.
 * Pending writes and their readback ownership survive every panel/navigation switch. */
export function useBackgroundMaterialHost({ enabled, targetKey, port: suppliedPort }: {
  enabled: boolean; targetKey: string; port?: BackgroundMaterialPort;
}) {
  const [open, setOpen] = useState(false), [choosing, setChoosing] = useState(false);
  const [head, setHead] = useState<MaterialSnapshot | null>(null), [page, setPage] = useState<MaterialPage | null>(null);
  const [query, setQuery] = useState<MaterialQuery>(initialQuery), [selected, setSelected] = useState<Map<string, Material>>(() => new Map());
  const [busy, setBusy] = useState(''), [ready, setReady] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [uncertain, setUncertain] = useState(false), [reviewed, setReviewed] = useState(false), [outcomes, setOutcomes] = useState<ImportOutcome[]>([]);
  const latest = useRef({ enabled, targetKey }); latest.current = { enabled, targetKey };
  const native = useMemo(() => createNativeBackgroundMaterialLibrary(() => latest.current.enabled), []);
  // Changing the port while a request owns a receipt is unsupported; App supplies
  // one stable port for its lifetime. Native is the production default.
  const port = useRef(suppliedPort ?? native.port).current;
  const state = useRef({ open: false, session: 0, mounted: false, job: null as Job | null,
    head: null as MaterialSnapshot | null, query: initialQuery(), ready: false, uncertain: false, reviewed: false,
    caller: null as MaterialCaller | null, selected: new Map<string, Material>() });
  const publishReady = (value: boolean) => { state.current.ready = value; setReady(value); };
  const clearSelection = useCallback(() => { state.current.selected = new Map(); setSelected(new Map()); }, []);

  const run = useCallback(async (label: string, write: boolean,
    task: (options: RequestOptions, current: () => boolean) => Promise<void>): Promise<void> => {
    const s = state.current;
    if (!latest.current.enabled || !s.open || s.job || (write && (s.uncertain || !s.ready))) return;
    const job: Job = { label, write, controller: new AbortController(), session: s.session };
    s.job = job; setBusy(label); setError('');
    const current = () => state.current.mounted && state.current.open && state.current.session === job.session;
    try { await task({ signal: job.controller.signal }, current); }
    catch (cause) {
      // Even a hidden, cancelled, or old caller must retain a possible write.
      const unknown = write && !(cause instanceof MaterialError && cause.outcome === 'not-applied');
      if (unknown) {
        s.uncertain = true; s.reviewed = false; s.ready = false;
        if (s.mounted) { setUncertain(true); setReviewed(false); setReady(false); }
      }
      if (current()) {
        if (cause instanceof MaterialError && /stale/.test(cause.code)) publishReady(false);
        if (cause instanceof MaterialError && cause.code === 'cancelled' && !unknown) setNotice('已停止等待；已确认的保存不会撤销。');
        else setError(errorText(cause));
      }
    } finally { if (s.job === job) { s.job = null; if (s.mounted) setBusy(''); } }
  }, []);

  const fresh = useCallback(async (options: RequestOptions, current: () => boolean, minimumRevision = 0): Promise<void> => {
    const next = await port.snapshot(options); if (!current()) return;
    const old = state.current.head;
    if (old && next.library_id !== old.library_id) throw new MaterialError('背景素材库身份已变化，请重启工作区后核对。', 'library_changed');
    if (next.revision < Math.max(old?.revision ?? 0, minimumRevision)) throw new MaterialError('目录版本落后于已确认写入，请重新核对。', 'stale_snapshot');
    let q = { ...state.current.query, offset: 0 };
    if (q.group_id !== null && !next.groups.some(g => g.id === q.group_id)) q.group_id = UNGROUPED;
    const nextPage = await port.page(q, next, options); if (!current()) return;
    state.current.head = next; state.current.query = q; state.current.ready = true;
    setHead(next); setQuery(q); setPage(nextPage); setReady(true);
    // Refresh invalidates old selected metadata. Never silently change a bulk target.
    clearSelection();
    if (state.current.uncertain) { state.current.reviewed = true; setReviewed(true); }
  }, [port, clearSelection]);
  const refresh = useCallback(() => run('刷新目录', false, async (options, current) => {
    publishReady(false); await fresh(options, current);
  }), [fresh, run]);

  const changeQuery = useCallback((patch: Partial<MaterialQuery>) => run('读取分页', false, async (options, current) => {
    const snapshot = state.current.head; if (!snapshot || !state.current.ready) return;
    const q = { ...state.current.query, ...patch, limit: PAGE_SIZE };
    const changingFilter = ['group_id', 'text', 'trash', 'sort'].some(key => q[key as keyof MaterialQuery] !== state.current.query[key as keyof MaterialQuery]);
    if (changingFilter) q.offset = 0;
    publishReady(false); const next = await port.page(q, snapshot, options); if (!current()) return;
    state.current.query = q; setQuery(q); setPage(next); publishReady(true);
    if (changingFilter) clearSelection();
  }), [port, run, clearSelection]);

  const mutate = useCallback((command: MaterialCommand, label: string) => run(label, true, async (options, current) => {
    const snapshot = state.current.head; if (!snapshot) return;
    const result = await port.command(command, snapshot, options);
    state.current.ready = false;
    if (state.current.mounted) {
      setReady(false); setOutcomes(result.outcomes ?? []);
      setNotice(result.changed ? `${label}已由目录确认。` : `${label}已核对，目录未变化。`);
    }
    clearSelection();
    // Readback failure after an acknowledged command is not a failed command.
    if (current() && !options.signal.aborted) {
      try { await fresh(options, current, result.revision); }
      catch (cause) { if (current()) setError(`操作已确认；后续目录读取未完成：${errorText(cause)} 请刷新，不要重复操作。`); }
    }
  }), [port, run, fresh, clearSelection]);

  const importPaths = useCallback((kind: 'images' | 'folder') => run(kind === 'images' ? '导入图片' : '导入文件夹', true, async (options, current) => {
    const snapshot = state.current.head; if (!snapshot) return;
    const paths = await port.chooseImportPaths(kind, options); if (!paths?.length || !current()) return;
    const result = await port.command({ op: 'import_paths', payload: { paths, group_id: state.current.query.group_id ?? UNGROUPED } }, snapshot, options);
    state.current.ready = false;
    if (state.current.mounted) { setReady(false); setOutcomes(result.outcomes ?? []); setNotice('本次导入已收到最终回执；各文件结果见下方，已完成文件不会因停止而回滚。'); }
    clearSelection();
    if (current() && !options.signal.aborted) {
      try { await fresh(options, current, result.revision); }
      catch (cause) { if (current()) setError(`导入已有回执；目录刷新未完成：${errorText(cause)} 请先刷新核对。`); }
    }
  }), [port, run, fresh, clearSelection]);

  const choose = useCallback(() => run('校验所选背景', false, async (options, current) => {
    const s = state.current, caller = s.caller, snapshot = s.head;
    if (!caller || !snapshot || s.uncertain || !s.ready || s.selected.size !== 1 || caller.targetKey !== latest.current.targetKey) return;
    const row = [...s.selected.values()][0]!; if (row.deleted_at !== null) return;
    const selection = parseSelection(await port.select(row.id, snapshot, options));
    if (!current() || options.signal.aborted || state.current.caller !== caller || !latest.current.enabled || caller.targetKey !== latest.current.targetKey) return;
    if (selection.sha256 !== row.sha256) throw new MaterialError('所选素材校验值与当前目录不一致。', 'stale_selection');
    // Clear the captured capability before invoking it, so repeated clicks or
    // synchronous rerenders cannot deliver the same choice a second time.
    state.current.caller = null; setChoosing(false);
    await caller.onChoose(selection);
    if (current()) { state.current.open = false; state.current.session++; setOpen(false); }
  }), [port, run]);

  const close = useCallback(() => {
    const s = state.current; s.open = false; s.session++; s.caller = null;
    s.job?.controller.abort(); setOpen(false); setChoosing(false);
  }, []);
  const show = useCallback((caller?: MaterialCaller) => {
    if (!latest.current.enabled || (caller && caller.targetKey !== latest.current.targetKey)) return;
    const s = state.current; s.job?.controller.abort(); s.session++; s.open = true; s.caller = caller ?? null;
    s.ready = false; s.reviewed = false; setReady(false); setReviewed(false); clearSelection();
    setOpen(true); setChoosing(Boolean(caller));
    // Do not discard an earlier request. Its completion releases job ownership;
    // the UI explicitly offers Refresh if reopening while it is still pending.
    if (!s.job) void refresh();
  }, [refresh, clearSelection]);
  const toggle = useCallback((material: Material, checked: boolean) => {
    if (state.current.job || !state.current.ready || state.current.uncertain) return;
    const map = new Map(state.current.caller ? [] : state.current.selected);
    if (checked) map.set(material.id, material); else map.delete(material.id);
    state.current.selected = map; setSelected(map);
  }, []);
  const selectPage = useCallback(() => {
    if (state.current.job || !state.current.ready || state.current.uncertain || state.current.caller || !page) return;
    const map = new Map(state.current.selected); for (const row of page.items) map.set(row.id, row);
    state.current.selected = map; setSelected(map);
  }, [page]);
  const acknowledge = useCallback(() => {
    const s = state.current; if (s.job || !s.reviewed || !s.ready) return;
    s.uncertain = false; s.reviewed = false; setUncertain(false); setReviewed(false); setError('');
    setNotice('已核对当前目录。没有重试上次操作。');
  }, []);
  useEffect(() => { state.current.mounted = true; return () => { state.current.mounted = false; state.current.job?.controller.abort(); state.current.caller = null; }; }, []);
  useEffect(() => {
    if (!enabled) close();
    else if (state.current.caller && state.current.caller.targetKey !== targetKey) {
      state.current.caller = null; state.current.session++; state.current.job?.controller.abort();
      setChoosing(false); setNotice('当前照片或编辑版本已变化，旧背景选择已失效。请从当前照片重新打开选择。'); clearSelection();
    }
  }, [enabled, targetKey, close, clearSelection]);
  return { enabled, open, choosing, head, page, query, selected, busy, ready, error, notice, uncertain, reviewed, outcomes, port,
    show, close, refresh, changeQuery, mutate, importPaths, choose, toggle, selectPage, clearSelection, acknowledge,
    cancel: () => state.current.job?.controller.abort(), clearOutcomes: () => setOutcomes([]) };
}
export type BackgroundMaterialOwner = ReturnType<typeof useBackgroundMaterialHost>;
