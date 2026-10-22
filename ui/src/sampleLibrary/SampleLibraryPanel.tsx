import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { CaptureContext, SampleLibraryPort } from './adapter';
import {
  NAME_LIMIT, PAGE_SIZE, UNGROUPED_ID, formatBytes, normalizedName, outcomeLabel,
  reorderedIds, type LibrarySample, type LibraryView, type SelectedSampleReference,
} from './model';
import { useSampleLibrary } from './useSampleLibrary';
import './sampleLibrary.css';

export interface SampleLibraryPanelProps {
  /** Memoize the port for this library root; changing it starts a new session. */
  port: SampleLibraryPort;
  open?: boolean;
  mode?: 'manage' | 'reference';
  captureContext?: CaptureContext;
  referenceTargetKey?: string;
  onReferenceSelected?: (reference: SelectedSampleReference) => void | Promise<void>;
  onClose?: () => void;
}
type Editor = { kind: 'group_create' } | { kind: 'group_rename' | 'sample_rename'; id: string };
type Confirmation = { kind: 'group_delete'; id: string; name: string; count: number } |
  { kind: 'sample_remove'; ids: string[] };

function sameView(left: LibraryView, right: LibraryView): boolean {
  return typeof left === 'object' && typeof right === 'object' ? left.group === right.group : left === right;
}
function readableTime(value: number): string {
  // Engine timestamps are Unix milliseconds. No invented date when a value is invalid.
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString();
}
function Thumbnail({ sample, port }: { sample: LibrarySample; port: SampleLibraryPort }) {
  const [url, setUrl] = useState(''), [failed, setFailed] = useState(false), [attempt, setAttempt] = useState(0);
  const anchor = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    let live = true, started = false;
    setUrl(''); setFailed(false);
    const load = () => {
      if (started) return;
      started = true;
      void port.thumbnail(sample.id, { signal: controller.signal }).then(value => {
        if (live && !controller.signal.aborted) setUrl(value);
      }).catch(() => { if (live && !controller.signal.aborted) setFailed(true); });
    };
    let observer: IntersectionObserver | undefined;
    if (typeof IntersectionObserver !== 'undefined' && anchor.current) {
      observer = new IntersectionObserver(entries => {
        if (entries.some(entry => entry.isIntersecting)) { observer?.disconnect(); load(); }
      }, { rootMargin: '180px' });
      observer.observe(anchor.current);
    } else load();
    return () => { live = false; controller.abort(); observer?.disconnect(); };
  }, [sample.id, sample.original_sha256, port, attempt]);
  return <div className="sampleLibraryThumbnail" ref={anchor}>
    {url && !failed ? <img src={url} alt={`${sample.name}的缩略图`} loading="lazy" onError={() => setFailed(true)} /> :
      <span>{failed ? '缩略图暂不可用' : '读取缩略图…'}</span>}
    {failed && <button type="button" onClick={() => setAttempt(value => value + 1)} aria-label={`重新读取${sample.name}的缩略图`}>重试缩略图</button>}
  </div>;
}

export function SampleLibraryPanel({ port, open = true, mode = 'manage', captureContext, referenceTargetKey, onReferenceSelected, onClose }: SampleLibraryPanelProps) {
  const w = useSampleLibrary({ port, open, mode, captureContext, referenceTargetKey, onReferenceSelected });
  const [search, setSearch] = useState('');
  const [editor, setEditor] = useState<Editor | null>(null), [editName, setEditName] = useState('');
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [moveGroup, setMoveGroup] = useState(UNGROUPED_ID);
  const [captureOpen, setCaptureOpen] = useState(false), [captureName, setCaptureName] = useState('');
  const [formError, setFormError] = useState('');
  const [draggedSample, setDraggedSample] = useState<string | null>(null), [draggedGroup, setDraggedGroup] = useState<string | null>(null);
  const headingId = useId(), searchId = useId(), outcomeId = useId(), captureNameId = useId(), editNameId = useId(), radioName = useId();
  const snapshot = w.snapshot;
  const pageRows = w.page?.samples ?? [];
  const total = w.page?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const selectedIds = useMemo(() => new Set(w.selected), [w.selected]);
  const selectedRows = w.selectedRows;
  const activeSelected = selectedRows.filter(sample => sample.deleted_at === null);
  const trashSelected = selectedRows.filter(sample => sample.deleted_at !== null);
  const trash = w.view === 'trash';
  const locked = Boolean(w.busy) || w.uncertain || !snapshot || !w.ready;
  const slots = snapshot ? Math.max(0, snapshot.capacity.limit - snapshot.capacity.active) : 0;
  const customGroups = snapshot?.groups.filter(group => group.id !== UNGROUPED_ID) ?? [];
  const groupNames = new Map(snapshot?.groups.map(group => [group.id, group.name]) ?? []);
  const groupCounts = snapshot?.group_counts ?? {};
  const selectedReference = activeSelected.length === 1 ? activeSelected[0] : undefined;
  const canCapture = Boolean(port.captureCurrentResult && captureContext?.available && slots > 0);

  useEffect(() => { setSearch(w.search); }, [w.search]);
  useEffect(() => {
    if (snapshot && moveGroup !== UNGROUPED_ID && !snapshot.groups.some(group => group.id === moveGroup)) setMoveGroup(UNGROUPED_ID);
  }, [snapshot, moveGroup]);
  useEffect(() => {
    if (!open) {
      setEditor(null); setConfirmation(null); setCaptureOpen(false); setFormError('');
      setDraggedGroup(null); setDraggedSample(null);
    }
  }, [open]);

  function changeView(view: LibraryView) {
    w.changeView(view); setEditor(null); setConfirmation(null); setFormError('');
  }
  function beginEdit(next: Editor, name = '') {
    setEditor(next); setEditName(name); setConfirmation(null); setFormError('');
  }
  function saveName() {
    if (!editor || locked) return;
    let name: string;
    try { name = normalizedName(editName); } catch (error) { setFormError(error instanceof Error ? error.message : '名称无效。'); return; }
    const command = editor.kind === 'group_create' ? { op: 'group_create' as const, payload: { name } } :
      { op: editor.kind, payload: { id: editor.id, name } };
    void w.mutate(command, editor.kind === 'group_create' ? '新建分组' : '重命名');
    setEditor(null); setFormError('');
  }
  function confirmAction() {
    if (!confirmation || locked) return;
    if (confirmation.kind === 'group_delete') void w.mutate({ op: 'group_delete', payload: { id: confirmation.id } }, '删除分组并保留样片');
    else void w.mutate({ op: 'sample_remove', payload: { ids: confirmation.ids } }, '移入回收站');
    setConfirmation(null);
  }
  function orderSample(from: string, to: string) {
    if (locked || trash || !snapshot || from === to) return;
    const ids = reorderedIds(snapshot.order_ids, pageRows.map(sample => sample.id), from, to);
    if (!pageRows.some(sample => sample.id === from) || !pageRows.some(sample => sample.id === to)) return;
    void w.mutate({ op: 'sample_reorder', payload: { ids } }, '调整样片顺序');
    setDraggedSample(null);
  }
  function orderGroup(from: string, to: string) {
    if (locked || !snapshot || from === to || from === UNGROUPED_ID || to === UNGROUPED_ID) return;
    const all = snapshot.groups.map(group => group.id), custom = customGroups.map(group => group.id);
    if (!custom.includes(from) || !custom.includes(to)) return;
    void w.mutate({ op: 'group_reorder', payload: { ids: reorderedIds(all, custom, from, to) } }, '调整分组顺序');
    setDraggedGroup(null);
  }
  const title = mode === 'reference' ? '选择本地参考样片' : '本地样片库';
  if (!open) return null;
  return <section className="sampleLibrary" aria-labelledby={headingId}>
    <header className="sampleLibraryHeader">
      <div><h3 id={headingId}>{title}</h3><p>管理自己拥有使用权的图片与成片。默认不附带样片，仅保存在本机。</p></div>
      {onClose && <button type="button" onClick={() => { w.cancel(); onClose(); }} aria-label="关闭样片库">关闭</button>}
    </header>
    <p className="sampleLibraryScope">这里只管理和手动选择样片，不会自动应用调色，不包含 AI 追色、AI 推荐或官方云样片库。</p>
    {snapshot && <div className="sampleLibraryCapacity" aria-label="样片容量">
      <span>可用 {snapshot.capacity.active} / {snapshot.capacity.limit} 张</span>
      <span>含回收站共 {snapshot.counts.total} 张</span>
      <span>样片库自有文件 {formatBytes(snapshot.storage.library_bytes)}</span>
      <span>整个共享参考缓存 {formatBytes(snapshot.storage.shared_reference_bytes)}</span>
      <details className="sampleLibraryStorage"><summary>存储计量、入库策略与磁盘剩余空间</summary>
        <dl><dt>自有文件与共享缓存计量合计</dt><dd>{formatBytes(snapshot.storage.bytes)}</dd>
          <dt>本库当前入库策略上限</dt><dd>{formatBytes(snapshot.storage.budget_bytes)}</dd>
          <dt>样片库所在文件系统剩余空间</dt><dd>{formatBytes(snapshot.storage.free_disk_bytes)}</dd>
          <dt>参考缓存所在文件系统剩余空间</dt><dd>{formatBytes(snapshot.storage.shared_free_disk_bytes)}</dd>
        </dl>
        <p>自有文件包括原片、缩略图、暂存文件、目录及恢复元数据。共享参考缓存包括其他项目及未索引资源，不是本库独占占用。</p>
        <p>策略上限只用于本库新增操作的准入检查，不是全局配额或磁盘预留；其他缓存写入者仍可增加占用。剩余空间为读取时值，两个位置可能在同一磁盘，不能相加。</p>
        {snapshot.storage.bytes > snapshot.storage.budget_bytes && <p role="status">当前计量已超过本库入库策略上限。已有样片仍可浏览；新增操作由后端重新检查，不会自动删除资源。</p>}
      </details>
      <small>每次最多 {snapshot.capacity.per_import} 张；回收站不计入可用数量，但仍占用磁盘。</small>
    </div>}
    <div className="sampleLibraryActions">
      <button type="button" disabled={Boolean(w.busy)} onClick={() => void w.refresh()}>刷新目录</button>
      <button type="button" disabled={locked || !slots} onClick={() => void w.importPaths('images', w.defaultGroup)}>导入图片</button>
      <button type="button" disabled={locked || !slots} onClick={() => void w.importPaths('folder', w.defaultGroup)}>导入文件夹</button>
      <button type="button" disabled={locked || !canCapture} onClick={() => {
        setCaptureName(captureContext?.label ? `${captureContext.label} 成片` : '当前成片'); setCaptureOpen(true); setFormError('');
      }}>保存当前成片为样片</button>
    </div>
    {!port.captureCurrentResult && <small>当前宿主尚未接入原尺寸成片保存；不会用屏幕截图代替。</small>}
    {port.captureCurrentResult && !captureContext?.available && <small>{captureContext?.unavailableReason || '打开可编辑照片后可保存当前成片。'}</small>}
    {snapshot && !slots && <p role="status">可用样片已达到上限。可先将不再使用的样片移入回收站，再导入或恢复。</p>}
    <p className="sampleLibraryHint">文件夹由本机程序展开并逐文件校验。停止导入会保留已完成的文件，不会整批回滚。原图保留原有字节与精度；不支持完整精度参考的格式仍可入库，但不能作为参考。</p>

    <div role="status" aria-live="polite" aria-atomic="true" className="sampleLibraryStatus">
      {w.busy && <p>正在{w.busy}，请等待确认…</p>}
      {w.notice && <p>{w.notice}</p>}
    </div>
    {w.busy && <button type="button" onClick={w.cancel}>{w.busy === '导入图片' || w.busy === '导入文件夹' ? '停止后续导入，保留已完成文件' : '取消等待中的操作'}</button>}
    {w.error && <p role="alert" className="sampleLibraryError">{w.error}</p>}
    {w.uncertain && <div className="sampleLibraryWarning" role="alert">
      <p>上次写入结果尚未确认，不能据此认定没有保存。已暂停新的写入与参考选择，不会自动重试。</p>
      <p>先刷新目录，核对实际内容；仍无法判断时请保留现场，不要重复导入或保存。</p>
      <button type="button" disabled={Boolean(w.busy)} onClick={() => void w.refresh()}>读取当前目录以核对</button>
      <button type="button" disabled={Boolean(w.busy) || !w.reviewedSnapshot} onClick={w.acknowledge}>我已核对目录，继续操作</button>
    </div>}
    {!!snapshot?.warnings.length && <details className="sampleLibraryWarning"><summary>目录提示（{snapshot.warnings.length}）</summary>
      <ul>{snapshot.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
    </details>}

    {captureOpen && <form className="sampleLibraryForm" onSubmit={event => {
      event.preventDefault();
      try { normalizedName(captureName); } catch (error) { setFormError(error instanceof Error ? error.message : '名称无效。'); return; }
      if (!locked && canCapture) { void w.capture(captureName, w.defaultGroup); setCaptureOpen(false); setFormError(''); }
    }}>
      <fieldset disabled={locked}><legend>保存当前成片</legend>
        <label htmlFor={captureNameId}>样片名称</label><input id={captureNameId} value={captureName} maxLength={NAME_LIMIT * 2} onChange={event => setCaptureName(event.target.value)} autoFocus />
        <p>将冻结“{captureContext?.label || '当前照片'}”的当前编辑版本，以原图尺寸渲染后入库到“{groupNames.get(w.defaultGroup) || '未分组'}”。不是截屏，也不会覆盖原图。</p>
        <div className="sampleLibraryActions"><button type="submit" disabled={!canCapture}>确认保存冻结成片</button>
          <button type="button" onClick={() => { setCaptureOpen(false); setFormError(''); }}>取消</button></div>
      </fieldset>
    </form>}

    <div className="sampleLibraryLayout">
      <nav className="sampleLibraryGroups" aria-label="样片分组">
        {([{ value: 'all', label: '全部样片', count: snapshot?.capacity.active ?? 0 },
          { value: 'ungrouped', label: '未分组', count: groupCounts[UNGROUPED_ID]?.active ?? 0 },
          { value: 'trash', label: '回收站', count: snapshot?.counts.trash ?? 0 }] as const).map(item =>
          <button type="button" key={item.value} aria-current={sameView(w.view, item.value) ? 'page' : undefined} disabled={Boolean(w.busy)} onClick={() => changeView(item.value)}>
            <span>{item.label}</span><span>{item.count}</span>
          </button>)}
        <div className="sampleLibraryGroupsHeading"><strong>我的分组</strong><button type="button" disabled={locked} onClick={() => beginEdit({ kind: 'group_create' })}>新建</button></div>
        {customGroups.length === 0 && <small>还没有分组，可先新建再导入。</small>}
        <ol className="sampleLibraryGroupList">{customGroups.map((group, index) => <li key={group.id}
          className={draggedGroup === group.id ? 'isDragging' : undefined}
          onDragOver={event => { if (draggedGroup && !locked) event.preventDefault(); }}
          onDrop={event => { if (draggedGroup && !locked) { event.preventDefault(); orderGroup(draggedGroup, group.id); } }}>
          <button type="button" disabled={Boolean(w.busy)} aria-current={sameView(w.view, { group: group.id }) ? 'page' : undefined} onClick={() => changeView({ group: group.id })}>
            <span>{group.name}</span><span>{groupCounts[group.id]?.active ?? 0}</span>
          </button>
          <div className="sampleLibraryGroupTools">
            <button type="button" disabled={locked} draggable={!locked} aria-label={`拖动分组${group.name}排序；也可使用上移下移按钮`} title="拖动排序；也可用旁边的上移、下移按钮"
              onDragStart={event => { setDraggedGroup(group.id); event.dataTransfer.setData('text/plain', `sample-library-group:${group.id}`); event.dataTransfer.effectAllowed = 'move'; }}
              onDragEnd={() => setDraggedGroup(null)}>↕</button>
            <button type="button" disabled={locked || index === 0} aria-label={`上移分组${group.name}`} onClick={() => orderGroup(group.id, customGroups[index - 1]!.id)}>↑</button>
            <button type="button" disabled={locked || index === customGroups.length - 1} aria-label={`下移分组${group.name}`} onClick={() => orderGroup(group.id, customGroups[index + 1]!.id)}>↓</button>
            <button type="button" disabled={locked} aria-label={`重命名分组${group.name}`} onClick={() => beginEdit({ kind: 'group_rename', id: group.id }, group.name)}>改名</button>
            <button type="button" disabled={locked} aria-label={`删除分组${group.name}但保留样片`} onClick={() => {
              setEditor(null); setConfirmation({ kind: 'group_delete', id: group.id, name: group.name,
                count: (groupCounts[group.id]?.active ?? 0) + (groupCounts[group.id]?.trash ?? 0) });
            }}>删除</button>
          </div>
        </li>)}</ol>
      </nav>
      <div className="sampleLibraryContent" aria-busy={Boolean(w.busy)}>
        <form className="sampleLibrarySearch" onSubmit={event => { event.preventDefault(); w.changeSearch(search); }}>
          <label htmlFor={searchId}>搜索当前分组</label>
          <input id={searchId} type="search" value={search} maxLength={240} disabled={Boolean(w.busy)} onChange={event => setSearch(event.target.value)} placeholder="名称、分组、格式、尺寸" />
          <div className="sampleLibraryActions"><button type="submit" disabled={Boolean(w.busy) || !snapshot}>搜索</button>
            {w.search && <button type="button" disabled={Boolean(w.busy)} onClick={() => { setSearch(''); w.changeSearch(''); }}>清空搜索</button>}</div>
        </form>
        {snapshot && !w.ready && !w.busy && <p role="alert" className="sampleLibraryWarning">当前分页尚未与目录版本核对完成。请刷新目录，不会自动重试旧分页或写入。</p>}
        {editor && <form className="sampleLibraryForm" onSubmit={event => { event.preventDefault(); saveName(); }}>
          <fieldset disabled={locked}><legend>{editor.kind === 'group_create' ? '新建分组' : editor.kind === 'group_rename' ? '重命名分组' : '重命名样片'}</legend>
            <label htmlFor={editNameId}>名称</label><input id={editNameId} autoFocus value={editName} maxLength={NAME_LIMIT * 2} onChange={event => setEditName(event.target.value)} />
            <small>{Array.from(editName.trim()).length} / {NAME_LIMIT} 字符；不修改源文件名。</small>
            <div className="sampleLibraryActions"><button type="submit">保存名称</button><button type="button" onClick={() => { setEditor(null); setFormError(''); }}>取消</button></div>
          </fieldset>
        </form>}
        {confirmation && <div className="sampleLibraryConfirm" role="group" aria-label="确认操作">
          <p>{confirmation.kind === 'group_delete'
            ? `删除分组“${confirmation.name}”？其中 ${confirmation.count} 张样片将移至未分组，回收站状态保持不变，不会删除图片。`
            : `将选中的 ${confirmation.ids.length} 张样片移入回收站？稍后可以恢复；原图和参考资源不会被永久删除，也不会因此释放磁盘空间。`}</p>
          <div className="sampleLibraryActions"><button type="button" disabled={locked} onClick={confirmAction}>确认{confirmation.kind === 'group_delete' ? '删除分组' : '移入回收站'}</button>
            <button type="button" disabled={Boolean(w.busy)} onClick={() => setConfirmation(null)}>取消</button></div>
        </div>}
        {formError && <p role="alert" className="sampleLibraryError">{formError}</p>}
        {trash && <p className="sampleLibraryHint">回收站保留图片及其资源，仅支持恢复，不提供永久删除。恢复后回到原分组；已删除的分组归入未分组。</p>}
        {mode === 'manage' && <div className="sampleLibrarySelection" aria-label="批量管理">
          <div className="sampleLibraryActions">
            <button type="button" disabled={locked || pageRows.length === 0} onClick={() => w.selectMany(pageRows)}>选择本页</button>
            <button type="button" disabled={Boolean(w.busy) || w.selected.length === 0} onClick={w.clearSelection}>清空选择</button>
            <span aria-live="polite">已选 {w.selected.length} 张（其中 {w.selected.filter(id => !pageRows.some(row => row.id === id)).length} 张在其他页）</span>
          </div>
          {trash ? <div className="sampleLibraryActions"><button type="button" disabled={locked || !trashSelected.length || trashSelected.length > slots}
            onClick={() => void w.mutate({ op: 'sample_restore', payload: { ids: trashSelected.map(sample => sample.id) } }, '恢复样片')}>恢复所选</button>
            {trashSelected.length > slots && <small>还可恢复 {slots} 张，请减少选择或先移除其他可用样片。</small>}</div> :
            <div className="sampleLibraryActions"><label>移至分组 <select value={moveGroup} disabled={locked || !activeSelected.length} onChange={event => setMoveGroup(event.target.value)}>
              <option value={UNGROUPED_ID}>未分组</option>{customGroups.map(group => <option value={group.id} key={group.id}>{group.name}</option>)}
            </select></label>
              <button type="button" disabled={locked || !activeSelected.length || activeSelected.every(sample => (sample.group_id ?? UNGROUPED_ID) === moveGroup)}
                onClick={() => void w.mutate({ op: 'sample_move', payload: { ids: activeSelected.map(sample => sample.id), group_id: moveGroup } }, '移动样片')}>移动所选</button>
              <button type="button" disabled={locked || !activeSelected.length} onClick={() => { setEditor(null); setConfirmation({ kind: 'sample_remove', ids: activeSelected.map(sample => sample.id) }); }}>移入回收站</button>
            </div>}
        </div>}
        {mode === 'reference' && <div className="sampleLibraryReferenceChoice">
          <p>一次选择一张有效样片。只有明确点击下方按钮后，才会校验并创建完整精度的稳定参考引用。</p>
          <div className="sampleLibraryActions"><button type="button" disabled={locked || !selectedReference || selectedReference.reference_supported === false || !onReferenceSelected}
            onClick={() => void w.chooseReference()}>使用所选参考样片</button>
            <button type="button" disabled={Boolean(w.busy) || !w.selected.length} onClick={w.clearSelection}>清空选择</button></div>
          {!onReferenceSelected && <small>宿主尚未接入参考选择回调，当前仅可浏览。</small>}
          {selectedReference?.reference_supported === false && <small>{selectedReference.reference_reason || '此样片格式暂不支持完整精度参考，不会降精度代用。'}</small>}
          {trash && <small>回收站样片不能作为参考；请先在管理模式中恢复。</small>}
        </div>}
        {!snapshot && <p>{w.busy ? '正在读取本地样片库…' : '尚未取得目录。请刷新目录，已有图片不会被空列表覆盖。'}</p>}
        {snapshot && w.page && total === 0 && <div className="sampleLibraryEmpty">
          <strong>{w.search ? '没有匹配的样片' : trash ? '回收站为空' : snapshot.capacity.active === 0 ? '从你的第一张样片开始' : '这个分组还没有样片'}</strong>
          <p>{w.search ? '尝试更短的关键词或切换分组。' : trash ? '移除的样片会保留在这里，方便恢复。' : '导入自己拥有使用权的图片，或把当前编辑成片保存为原尺寸样片。'}</p>
          {!!w.search && <button type="button" disabled={Boolean(w.busy)} onClick={() => { setSearch(''); w.changeSearch(''); }}>清空搜索</button>}
        </div>}
        <ol className="sampleLibraryGrid" aria-label={trash ? '回收站样片' : '可用样片'}>{pageRows.map((sample, index) => {
          const checked = selectedIds.has(sample.id);
          return <li key={sample.id} className={`sampleLibraryCard${checked ? ' isSelected' : ''}${draggedSample === sample.id ? ' isDragging' : ''}`}
            onDragOver={event => { if (draggedSample && !locked && !trash) event.preventDefault(); }}
            onDrop={event => { if (draggedSample && !locked && !trash) { event.preventDefault(); orderSample(draggedSample, sample.id); } }}>
            <label className="sampleLibraryCardSelection"><input type={mode === 'reference' ? 'radio' : 'checkbox'} name={mode === 'reference' ? radioName : undefined}
              checked={checked} disabled={locked || (mode === 'reference' && (trash || sample.reference_supported === false))}
              onChange={event => w.toggle(sample, event.target.checked)} />
              <strong title={sample.name}>{sample.name}</strong>
            </label>
            <Thumbnail sample={sample} port={port} />
            <div className="sampleLibraryMetadata">
              <span>{sample.width} × {sample.height} · {sample.format.toUpperCase()} · {sample.precision}</span>
              <span>{formatBytes(sample.bytes)} · {sample.kind === 'render' ? '当前成片' : '导入图片'}</span>
              <span>分组：{groupNames.get(sample.group_id ?? UNGROUPED_ID) || '未分组'}</span>
              {sample.reference_supported === false && <span className="sampleLibraryPrecisionWarning">仅管理，暂不能作为完整精度参考</span>}
            </div>
            <details className="sampleLibraryDetails"><summary>样片详情</summary>
              <dl><dt>创建时间</dt><dd>{readableTime(sample.created_at)}</dd>
                {sample.deleted_at !== null && <><dt>移入回收站</dt><dd>{readableTime(sample.deleted_at)}</dd></>}
                <dt>原图内容校验值</dt><dd>{sample.original_sha256}</dd>
                <dt>参考资源</dt><dd>{sample.reference ? '已生成稳定引用' : '尚未生成，选择时再创建'}</dd>
                {sample.reference_reason && <><dt>参考说明</dt><dd>{sample.reference_reason}</dd></>}
              </dl>{sample.notes?.map((note, noteIndex) => <p key={noteIndex}>{note}</p>)}
            </details>
            {!trash && <div className="sampleLibraryCardTools">
              <button type="button" disabled={locked} draggable={!locked} aria-label={`拖动样片${sample.name}排序；也可使用前移后移按钮`} title="拖动排序；也可用前移、后移按钮"
                onDragStart={event => { setDraggedSample(sample.id); event.dataTransfer.setData('text/plain', `sample-library-sample:${sample.id}`); event.dataTransfer.effectAllowed = 'move'; }}
                onDragEnd={() => setDraggedSample(null)}>↕</button>
              <button type="button" disabled={locked || index === 0} aria-label={`前移样片${sample.name}`} onClick={() => orderSample(sample.id, pageRows[index - 1]!.id)}>前移</button>
              <button type="button" disabled={locked || index === pageRows.length - 1} aria-label={`后移样片${sample.name}`} onClick={() => orderSample(sample.id, pageRows[index + 1]!.id)}>后移</button>
              <button type="button" disabled={locked} aria-label={`重命名样片${sample.name}`} onClick={() => beginEdit({ kind: 'sample_rename', id: sample.id }, sample.name)}>改名</button>
            </div>}
          </li>;
        })}</ol>
        {total > 0 && <nav className="sampleLibraryPagination" aria-label="样片分页">
          <button type="button" disabled={Boolean(w.busy) || !w.ready || w.pageIndex === 0} onClick={() => void w.previousPage()}>上一页</button>
          <span>第 {w.pageIndex + 1} / {pageCount} 页 · 匹配 {total} 张 · 本页 {pageRows.length} 张</span>
          <button type="button" disabled={Boolean(w.busy) || !w.ready || !w.page?.next_cursor} onClick={() => void w.nextPage()}>下一页</button>
        </nav>}
        {!trash && pageRows.length > 1 && <small>拖动或使用前移、后移按钮调整当前页内的顺序；所有其他页和隐藏样片的位置保持不变。</small>}

      </div>
    </div>
    {!!w.outcomes.length && <details className="sampleLibraryOutcomes" open><summary id={outcomeId}>逐文件处理结果（{w.outcomes.length}）</summary>
      <ol aria-labelledby={outcomeId}>{w.outcomes.map((result, index) => <li key={`${index}-${result.path ?? result.id ?? ''}`}>
        <strong>{outcomeLabel(result.status)}</strong><span>{result.path || result.name || result.id || `第 ${index + 1} 项`}</span>{result.message && <p>{result.message}</p>}
      </li>)}</ol><button type="button" onClick={w.clearOutcomes}>收起本次结果</button>
    </details>}
  </section>;
}
