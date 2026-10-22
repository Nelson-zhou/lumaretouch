import { useCallback, useEffect, useRef, useState } from 'react';
import type { CaptureContext, RequestOptions, SampleLibraryPort } from './adapter';
import {
  PAGE_SIZE, SampleLibraryError, errorMessage, isAbort, normalizedName, UNGROUPED_ID,
  type LibraryView, type SampleLibraryCommand, type LibrarySample,
  type SampleLibrarySnapshot, type SampleLibraryPage, type SampleOutcome, type SelectedSampleReference,
} from './model';

type Work = { controller: AbortController; epoch: number; label: string; mutating: boolean; promise?: Promise<void> };
type Query = { view: LibraryView; search: string };
export function useSampleLibrary({ port, open, mode, captureContext, referenceTargetKey, onReferenceSelected }: {
  port: SampleLibraryPort; open: boolean; mode: 'manage' | 'reference'; captureContext?: CaptureContext; referenceTargetKey?: string;
  onReferenceSelected?: (reference: SelectedSampleReference) => void | Promise<void>;
}) {
  const [snapshot, setSnapshot] = useState<SampleLibrarySnapshot | null>(null);
  const [page, setPage] = useState<SampleLibraryPage | null>(null), [pageIndex, setPageIndex] = useState(0);
  const [view, setView] = useState<LibraryView>('all'), [search, setSearch] = useState('');
  // Only deliberately selected metadata survives paging; not a hidden full-catalog cache.
  const [selection, setSelection] = useState<Map<string, LibrarySample>>(() => new Map());
  const [busy, setBusy] = useState<string | null>(null), [ready, setReady] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [outcomes, setOutcomes] = useState<SampleOutcome[]>([]);
  const [uncertain, setUncertain] = useState(false), [reviewedSnapshot, setReviewedSnapshot] = useState(false);
  const session = useRef({ open, port, epoch: 0, mounted: false });
  const latest = useRef({ open, port, mode, captureContext, referenceTargetKey, onReferenceSelected });
  latest.current = { open, port, mode, captureContext, referenceTargetKey, onReferenceSelected };
  const head = useRef<SampleLibrarySnapshot | null>(null), currentPage = useRef<SampleLibraryPage | null>(null);
  const query = useRef<Query>({ view: 'all', search: '' });
  const cursors = useRef<Array<string | null>>([null]), index = useRef(0);
  const work = useRef<Work | null>(null), uncertainty = useRef(false), isReady = useRef(false);

  const run = useCallback((label: string, mutating: boolean,
    task: (options: RequestOptions, current: () => boolean) => Promise<string | void>): Promise<void> => {
    if (!session.current.open || !latest.current.open || session.current.port !== latest.current.port || work.current || (mutating && uncertainty.current)) return Promise.resolve();
    const job: Work = { controller: new AbortController(), epoch: session.current.epoch, label, mutating };
    const jobPort = session.current.port;
    work.current = job; setBusy(label); setError(''); setNotice('');
    const current = () => session.current.mounted && session.current.open && latest.current.open &&
      session.current.epoch === job.epoch && session.current.port === jobPort && latest.current.port === jobPort;
    job.promise = (async () => {
      try {
        const message = await task({ signal: job.controller.signal }, current);
        if (current() && message) setNotice(message);
      } catch (cause) {
        const unknown = job.mutating && !(cause instanceof SampleLibraryError && cause.mutationState === 'not-applied');
        if (unknown && session.current.port === jobPort) {
          uncertainty.current = true;
          if (session.current.mounted) { setUncertain(true); setReviewedSnapshot(false); }
        }
        if (current()) {
          if (cause instanceof SampleLibraryError && ['stale', 'stale_page', 'stale_snapshot'].includes(cause.code)) { isReady.current = false; setReady(false); }
          if ((isAbort(cause) || (cause instanceof SampleLibraryError && cause.code === 'cancelled')) && !unknown) setNotice('已取消本次操作。');
          else setError(errorMessage(cause));
        }
      } finally {
        if (work.current === job) { work.current = null; if (session.current.mounted) setBusy(null); }
      }
    })();
    return job.promise;
  }, []);

  const invalidate = useCallback(() => { isReady.current = false; setReady(false); }, []);
  const installPage = useCallback((next: SampleLibraryPage, nextHead: SampleLibrarySnapshot, cursor: string | null, pageNumber: number) => {
    const allowed = new Set(nextHead.order_ids), groups = new Set(nextHead.groups.map(group => group.id));
    if (next.revision !== nextHead.revision || next.samples.some(sample =>
      !groups.has(sample.group_id ?? UNGROUPED_ID) || (sample.deleted_at === null && !allowed.has(sample.id)))) {
      throw new SampleLibraryError('分页内容与目录版本或稳定身份不同，请刷新目录。', 'stale_page');
    }
    if (next.offset !== pageNumber * PAGE_SIZE || next.limit !== PAGE_SIZE || pageNumber * PAGE_SIZE + next.samples.length > next.total ||
      (next.next_cursor === null && pageNumber * PAGE_SIZE + next.samples.length !== next.total)) {
      throw new SampleLibraryError('分页总数或结束位置不一致，未截断内容。', 'invalid_reply');
    }
    const activeView = query.current.view;
    const viewCount = activeView === 'all' ? nextHead.counts.active : activeView === 'trash' ? nextHead.counts.trash :
      nextHead.group_counts[activeView === 'ungrouped' ? UNGROUPED_ID : activeView.group]?.active ?? 0;
    if (next.total > viewCount || (!query.current.search && next.total !== viewCount)) {
      throw new SampleLibraryError('分页匹配总数与目录计数不同，请刷新目录。', 'invalid_reply');
    }
    head.current = nextHead; currentPage.current = next; index.current = pageNumber;
    cursors.current = cursors.current.slice(0, pageNumber + 1); cursors.current[pageNumber] = cursor;
    setSnapshot(nextHead); setPage(next); setPageIndex(pageNumber);
    setSelection(previous => {
      const updated = new Map(previous);
      for (const row of next.samples) if (updated.has(row.id)) updated.set(row.id, row);
      return updated;
    });
    isReady.current = true; setReady(true);
  }, []);

  const readFresh = useCallback(async (options: RequestOptions, current: () => boolean, minimumRevision = 0) => {
    const next = await port.snapshot(options);
    if (!current()) return;
    if (next.revision < Math.max(minimumRevision, head.current?.revision ?? 0)) throw new SampleLibraryError('目录版本落后于已确认操作，请重新刷新。', 'stale_snapshot');
    let target = query.current;
    if (typeof target.view === 'object' && !next.groups.some(group => group.id === (target.view as { group: string }).group)) {
      target = { ...target, view: 'ungrouped' }; query.current = target; setView('ungrouped');
    }
    const first = await port.page({ ...target, limit: PAGE_SIZE, cursor: null }, next.revision, options);
    if (!current()) return;
    cursors.current = [null]; installPage(first, next, null, 0);
    if (uncertainty.current) setReviewedSnapshot(true);
  }, [port, installPage]);
  const refresh = useCallback(() => run('读取样片目录', false, async (options, current) => {
    invalidate(); await readFresh(options, current); return '目录及第一页已刷新。';
  }), [run, invalidate, readFresh]);

  useEffect(() => {
    const previousPort = session.current.port;
    session.current = { open, port, epoch: session.current.epoch + 1, mounted: true };
    const epoch = session.current.epoch;
    if (previousPort !== port) {
      head.current = null; currentPage.current = null; cursors.current = [null]; index.current = 0;
      query.current = { view: 'all', search: '' }; setView('all'); setSearch('');
      setSnapshot(null); setPage(null); setPageIndex(0); setSelection(new Map()); setOutcomes([]); setError('');
      uncertainty.current = false; setUncertain(false); setReviewedSnapshot(false); invalidate();
    }
    if (open) {
      // A terminal write may become uncertain while the panel is closed.
      // Restore the visible gate and require a fresh read before acknowledgment.
      setUncertain(uncertainty.current); setReviewedSnapshot(false);
      void (async () => {
        await work.current?.promise;
        if (session.current.open && session.current.epoch === epoch) {
          setUncertain(uncertainty.current);
          await refresh();
        }
      })();
    }
    return () => { session.current.open = false; session.current.mounted = false; session.current.epoch++; work.current?.controller.abort(); };
  }, [port, open, refresh, invalidate]);
  useEffect(() => {
    if (work.current?.label === '保存当前成片') {
      work.current.controller.abort(); setNotice('当前照片或编辑版本已变化，正在取消旧版本保存；以最终回执为准。');
    }
  }, [captureContext?.key, captureContext?.available]);
  useEffect(() => {
    setSelection(new Map()); if (work.current?.label === '验证参考样片') work.current.controller.abort();
  }, [mode]);

  function loadPage(cursor: string | null, pageNumber: number, target = query.current): Promise<void> {
    if (!head.current || work.current) return Promise.resolve();
    const pinnedHead = head.current;
    return run('读取样片分页', false, async (options, current) => {
      invalidate();
      const next = await port.page({ ...target, limit: PAGE_SIZE, cursor }, pinnedHead.revision, options);
      if (current()) installPage(next, pinnedHead, cursor, pageNumber);
      return `已读取第 ${pageNumber + 1} 页。`;
    });
  }
  function changeQuery(next: Query) {
    if (work.current) return;
    const prior = query.current;
    const sameView = typeof prior.view === 'object' && typeof next.view === 'object' ? prior.view.group === next.view.group : prior.view === next.view;
    if (sameView && prior.search === next.search) return;
    query.current = next; setView(next.view); setSearch(next.search); setSelection(new Map());
    currentPage.current = null; setPage(null); index.current = 0; setPageIndex(0); cursors.current = [null];
    if (isReady.current) void loadPage(null, 0, next);
    else { invalidate(); setNotice('请刷新目录，以读取新的分组或搜索结果。'); }
  }
  async function afterCommit(receipt: { revision: number; outcomes?: SampleOutcome[] }, message: string, options: RequestOptions, current: () => boolean, clear = true) {
    // Persistence is confirmed before any follow-up read, so a read failure is not an uncertain write.
    if (work.current) work.current.mutating = false;
    if (clear && session.current.mounted && session.current.port === port) setSelection(new Map());
    if (!current()) return;
    invalidate(); setOutcomes(receipt.outcomes ?? []); setNotice(message);
    try {
      await readFresh(options, current, receipt.revision);
      if (current() && isReady.current) setNotice(`${message} 目录已刷新至第一页。`);
    }
    catch (cause) { if (current()) setError(`${message} 但目录刷新未完成：${errorMessage(cause)} 请刷新目录，勿重复提交。`); }
  }
  function mutate(command: SampleLibraryCommand, label: string): Promise<void> {
    if (!head.current || !isReady.current) return Promise.resolve();
    const expectedRevision = head.current.revision;
    return run(label, true, async (options, current) => {
      const receipt = await port.command(command, expectedRevision, options);
      await afterCommit(receipt, `${label}已确认。`, options, current);
    });
  }
  function importPaths(kind: 'images' | 'folder', groupId: string): Promise<void> {
    if (!head.current || !isReady.current || uncertainty.current) return Promise.resolve();
    const before = head.current;
    return run(kind === 'images' ? '导入图片' : '导入文件夹', false, async (options, current) => {
      const paths = await port.chooseImportPaths(kind, options);
      if (!current() || !paths?.length) return '未选择文件，目录未改变。';
      if (paths.length > before.capacity.per_import) throw new SampleLibraryError(`单次最多 ${before.capacity.per_import} 张，请分批导入。`, 'import_limit');
      if (work.current) work.current.mutating = true;
      const receipt = await port.command({ op: 'import_paths', payload: { paths, group_id: groupId } }, before.revision, options);
      await afterCommit(receipt, '导入请求已处理，请查看逐文件结果。', options, current);
    });
  }
  function capture(name: string, groupId: string): Promise<void> {
    const context = latest.current.captureContext;
    if (!head.current || !isReady.current || !context?.available || !port.captureCurrentResult) return Promise.resolve();
    let cleanName: string;
    try { cleanName = normalizedName(name); } catch (cause) { setError(errorMessage(cause)); return Promise.resolve(); }
    const revision = head.current.revision, captureCurrentResult = port.captureCurrentResult;
    return run('保存当前成片', true, async (options, current) => {
      const result = await captureCurrentResult({ name: cleanName, group_id: groupId,
        expected_context: { document_id: context.document_id, revision: context.revision } }, revision, options);
      const message = result.duplicate ? result.archived === true ? '该冻结结果已在回收站，未新增；可恢复已有样片。' : '该冻结结果已存在，没有重复保存；可在列表或回收站查看。'
        : options.signal.aborted ? '取消前成片已经保存；已保留真实结果，没有自动删除。' : '原尺寸冻结成片已保存到本地样片库。';
      await afterCommit(result, message, options, current);
    });
  }
  function chooseReference(): Promise<void> {
    const row = selection.size === 1 ? [...selection.values()][0] : undefined;
    if (latest.current.mode !== 'reference' || !head.current || !isReady.current || !row || row.deleted_at !== null || row.reference_supported === false || !latest.current.onReferenceSelected || uncertainty.current) return Promise.resolve();
    const revision = head.current.revision, targetContext = latest.current.captureContext?.key, targetDocument = latest.current.referenceTargetKey;
    return run('验证参考样片', true, async (options, current) => {
      const result = await port.select(row.id, revision, options);
      if (result.reference.source.sha256 !== row.original_sha256 || (row.reference && row.reference.asset_id !== result.reference.asset_id)) {
        throw new SampleLibraryError('参考回执与选中样片的稳定来源不同，请核对目录。', 'invalid_reply', 'unknown');
      }
      await afterCommit(result, '参考资源已校验，目录正在刷新。', options, current, false);
      if (!current() || options.signal.aborted || latest.current.mode !== 'reference') return '已取消本次参考选择；未自动应用调色。';
      if (targetDocument !== latest.current.referenceTargetKey || targetContext !== latest.current.captureContext?.key) return '当前照片或版本已变化，未应用旧的参考选择。';
      await latest.current.onReferenceSelected?.({ ...result.reference, sample_id: result.sample_id });
      return '已选择经过校验的参考样片；未自动应用调色。';
    });
  }
  function toggle(sample: LibrarySample, checked: boolean) {
    if (work.current || !isReady.current) return;
    setSelection(previous => { const next = mode === 'reference' ? new Map<string, LibrarySample>() : new Map(previous);
      if (checked) next.set(sample.id, sample); else next.delete(sample.id); return next; });
  }
  function acknowledge() {
    if (!reviewedSnapshot || !isReady.current || work.current) return;
    uncertainty.current = false; setUncertain(false); setReviewedSnapshot(false); setNotice('已核对当前目录，可以继续。未自动重试写入。');
  }
  function cancel() {
    if (!work.current) return; work.current.controller.abort();
    setNotice(work.current.label === '导入图片' || work.current.label === '导入文件夹'
      ? '已请求停止后续导入；已完成的文件会保留，等待逐文件结果，不会整批回滚。'
      : work.current.mutating ? '已请求取消，正在等待最终回执。取消前已保存的真实结果会保留。' : '已请求取消，正在等待操作结束。');
  }
  return {
    snapshot, page, pageIndex, view, search, ready, selected: [...selection.keys()], selectedRows: [...selection.values()],
    busy, error, notice, outcomes, uncertain, reviewedSnapshot, refresh, mutate, importPaths, capture, chooseReference, toggle, acknowledge, cancel,
    changeView: (next: LibraryView) => changeQuery({ ...query.current, view: next }),
    changeSearch: (next: string) => changeQuery({ ...query.current, search: next.trim() }),
    previousPage: () => index.current > 0 && isReady.current ? loadPage(cursors.current[index.current - 1] ?? null, index.current - 1) : Promise.resolve(),
    nextPage: () => currentPage.current?.next_cursor && isReady.current ? loadPage(currentPage.current.next_cursor, index.current + 1) : Promise.resolve(),
    selectMany: (rows: LibrarySample[]) => { if (!work.current && isReady.current && mode === 'manage') setSelection(previous => {
      const next = new Map(previous); for (const row of rows) next.set(row.id, row); return next;
    }); },
    clearSelection: () => { if (!work.current) setSelection(new Map()); }, clearOutcomes: () => setOutcomes([]),
    defaultGroup: typeof view === 'object' ? view.group : UNGROUPED_ID,
  };
}
