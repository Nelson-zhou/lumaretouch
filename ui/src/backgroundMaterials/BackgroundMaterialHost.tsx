import { useEffect, useId, useRef, useState } from 'react';
import type { BackgroundMaterialPort } from './adapter';
import type { BackgroundMaterialOwner } from './useBackgroundMaterialHost';
import { UNGROUPED, errorText, formatBytes, normalizedName, reorderedIds, type Material, type MaterialCommand } from './model';
import './backgroundMaterials.css';

function Thumbnail({ row, revision, open, port }: { row: Material; revision: number; open: boolean; port: BackgroundMaterialPort }) {
  const region = useRef<HTMLDivElement>(null), [data, setData] = useState(''), [error, setError] = useState('');
  useEffect(() => {
    setData(''); setError(''); if (!open) return;
    const abort = new AbortController(); let live = true, started = false;
    const load = () => {
      if (started || !live) return; started = true;
      void port.thumbnail(row.id, revision, { signal: abort.signal }).then(value => { if (live) setData(value); })
        .catch(cause => { if (live) setError(errorText(cause)); });
    };
    const observer = typeof IntersectionObserver === 'undefined' ? null : new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { observer?.disconnect(); load(); }
    }, { rootMargin: '120px' });
    if (observer && region.current) observer.observe(region.current); else load();
    return () => { live = false; observer?.disconnect(); abort.abort(); };
  }, [open, port, revision, row.id]);
  return <div ref={region} className="backgroundMaterialThumbnail">
    {data ? <img src={data} alt={`${row.name}的显示用缩略图`} loading="lazy" /> : <span>{error ? '缩略图不可用' : '等待显示用缩略图'}</span>}
    {error && <details><summary>原因</summary><small>{error}</small></details>}
  </div>;
}
type Editor = { op: 'group_create' } | { op: 'group_rename' | 'material_rename'; id: string };
type Confirm = { command: MaterialCommand; label: string; text: string };

export function BackgroundMaterialLaunch({ owner }: { owner: BackgroundMaterialOwner }) {
  return <div className="backgroundMaterialLaunch" data-readonly-scopes>
    <button type="button" disabled={!owner.enabled} onClick={() => owner.show()}>管理本地背景素材</button>
    {!owner.enabled && <small>当前引擎未声明背景素材库协议；启动配套引擎后可用。</small>}
    <small>只管理你有权使用的本地文件，不含商业素材包或 AI 场景生成。</small>
  </div>;
}

/** Stable App owner remains mounted; the visual region may be hidden safely. */
export function BackgroundMaterialHost({ owner: w }: { owner: BackgroundMaterialOwner }) {
  const focus = useRef<HTMLDivElement>(null), titleId = useId(), searchId = useId(), nameId = useId(), radioId = useId();
  const [search, setSearch] = useState(''), [moveGroup, setMoveGroup] = useState(UNGROUPED);
  const [editor, setEditor] = useState<Editor | null>(null), [name, setName] = useState(''), [formError, setFormError] = useState('');
  const [confirm, setConfirm] = useState<Confirm | null>(null), [dragged, setDragged] = useState<string | null>(null);
  const [draggedGroup, setDraggedGroup] = useState<string | null>(null);
  const locked = !!w.busy || !w.enabled || !w.ready || w.uncertain, rows = w.page?.items ?? [], head = w.head;
  const selected = [...w.selected.values()], customGroups = head?.groups.filter(g => g.id !== UNGROUPED) ?? [];
  const canOrder = !locked && !w.query.trash && w.query.sort === 'manual';
  useEffect(() => {
    if (!w.open) return; const prior = document.activeElement; focus.current?.focus();
    return () => { if (prior instanceof HTMLElement && prior.isConnected) prior.focus(); };
  }, [w.open]);
  useEffect(() => { setEditor(null); setConfirm(null); setFormError(''); setDragged(null); setDraggedGroup(null); }, [w.open, head?.revision, head?.library_id]);
  useEffect(() => { setSearch(w.query.text); }, [w.query.text]);
  useEffect(() => { if (head && !head.groups.some(g => g.id === moveGroup)) setMoveGroup(UNGROUPED); }, [head, moveGroup]);
  const beginEdit = (next: Editor, initial = '') => { setEditor(next); setName(initial); setFormError(''); setConfirm(null); };
  const saveName = () => {
    if (!editor || locked) return;
    try {
      const value = normalizedName(name), command: MaterialCommand = editor.op === 'group_create'
        ? { op: 'group_create', payload: { name: value } } : { op: editor.op, payload: { id: editor.id, name: value } };
      setEditor(null); void w.mutate(command, editor.op === 'group_create' ? '新建分组' : '重命名');
    } catch (cause) { setFormError(errorText(cause)); }
  };
  const orderMaterial = (from: string, to: string) => {
    if (!head || !canOrder) return; setDragged(null);
    void w.mutate({ op: 'material_reorder', payload: { ids: reorderedIds(head.order_ids, rows.map(r => r.id), from, to) } }, '调整素材顺序');
  };
  const orderGroup = (from: string, to: string) => {
    if (!head || locked) return; setDraggedGroup(null);
    void w.mutate({ op: 'group_reorder', payload: { ids: reorderedIds(head.groups.map(g => g.id), customGroups.map(g => g.id), from, to) } }, '调整分组顺序');
  };
  const remove = () => setConfirm({ command: { op: 'material_remove', payload: { ids: selected.map(r => r.id) } }, label: '移入回收站',
    text: `将选中的 ${selected.length} 张背景素材移入回收站？只修改目录记录，可恢复；不删除原文件或库内原始字节，也不会释放磁盘空间。` });
  const outcomeLabels: Record<string, string> = { imported: '已导入', duplicate: '已存在', trashed_duplicate: '已在回收站', error: '未导入', cancelled: '已停止' };
  return <div hidden={!w.open} ref={focus} tabIndex={-1} role="region" aria-labelledby={titleId}
    className="backgroundMaterialHost" data-readonly-scopes onKeyDown={event => {
      if (event.key === 'Escape') { event.stopPropagation(); w.close(); }
    }}>
    <header className="backgroundMaterialHeader"><div><h2 id={titleId}>{w.choosing ? '选择本地背景素材' : '本地背景素材库'}</h2>
      <p>从自己的图片或文件夹导入。分类、改名和移除只修改素材目录，不改写源文件。</p></div>
      <button type="button" onClick={w.close} aria-label="关闭背景素材库">关闭</button></header>
    {!w.enabled && <p role="alert">当前引擎不支持背景素材库协议，现有目录未被替换。</p>}
    <div className="backgroundMaterialActions">
      <button type="button" disabled={!!w.busy || !w.enabled} onClick={() => void w.refresh()}>刷新目录</button>
      <button type="button" disabled={locked || !head || head.counts.active >= head.limits.max_active} onClick={() => void w.importPaths('images')}>导入图片</button>
      <button type="button" disabled={locked || !head || head.counts.active >= head.limits.max_active} onClick={() => void w.importPaths('folder')}>导入文件夹</button>
      {w.busy && <button type="button" onClick={w.cancel}>请求停止，保留已完成文件</button>}
    </div>
    <p className="backgroundMaterialHint">JPEG、PNG、TIFF、BMP。原始字节单独保存；缩略图仅供浏览，不会当作修图或导出输入。没有联网下载、商业素材包或 AI 布景生成。</p>
    {head && <div className="backgroundMaterialSummary">
      <span>可用 {head.counts.active} / {head.limits.max_active} · 回收站 {head.counts.trash} · 每次最多 {head.limits.max_import} 个文件</span>
      <span>库内占用 {formatBytes(head.storage.bytes)} · 新增准入预算 {formatBytes(head.storage.budget_bytes)}</span>
      <small>单个原文件 ≤ {formatBytes(head.limits.max_object_bytes)}，≤ {(head.limits.max_pixels / 1e6).toFixed(0)} 百万像素。预算不是磁盘预留；回收站仍占用空间。</small>
    </div>}
    <div role="status" aria-live="polite">{w.busy && <p>正在{w.busy}，等待真实回执…</p>}{w.notice && <p>{w.notice}</p>}</div>
    {w.error && <p role="alert" className="backgroundMaterialError">{w.error}</p>}
    {w.uncertain && <div className="backgroundMaterialWarning" role="alert">
      <p>上次写入结果尚未确认，已暂停新写入和背景选择。不会自动重试，也不能把关闭或停止理解为撤销。</p>
      <button type="button" disabled={!!w.busy || !w.enabled} onClick={() => void w.refresh()}>读取回执与当前目录以核对</button>
      <button type="button" disabled={!!w.busy || !w.reviewed || !w.ready} onClick={w.acknowledge}>我已核对目录，继续</button>
    </div>}
    {head && !w.ready && !w.busy && <p role="status">当前目录或分页尚待核对。请刷新后再修改或选择，不会自动重放旧操作。</p>}
    {!!head?.warnings.length && <details><summary>目录提示（{head.warnings.length}）</summary><ul>{head.warnings.map((value, i) => <li key={i}>{value}</li>)}</ul></details>}
    <div className="backgroundMaterialLayout">
      <nav className="backgroundMaterialGroups" aria-label="背景素材分组">
        <button type="button" disabled={!!w.busy || !w.ready} aria-current={!w.query.trash && w.query.group_id === null ? 'page' : undefined}
          onClick={() => void w.changeQuery({ group_id: null, trash: false })}>全部素材（{head?.counts.active ?? 0}）</button>
        <button type="button" disabled={!!w.busy || !w.ready} aria-current={!w.query.trash && w.query.group_id === UNGROUPED ? 'page' : undefined}
          onClick={() => void w.changeQuery({ group_id: UNGROUPED, trash: false })}>未分组</button>
        <button type="button" disabled={!!w.busy || !w.ready} aria-current={w.query.trash ? 'page' : undefined}
          onClick={() => void w.changeQuery({ group_id: null, trash: true })}>回收站（{head?.counts.trash ?? 0}）</button>
        <div className="backgroundMaterialActions"><strong>我的分组</strong><button type="button" disabled={locked || !head || head.groups.length >= head.limits.max_groups} onClick={() => beginEdit({ op: 'group_create' })}>新建</button></div>
        <ol>{customGroups.map((group, i) => <li key={group.id} onDragOver={event => { if (draggedGroup && !locked) event.preventDefault(); }}
          onDrop={event => { if (draggedGroup && !locked) { event.preventDefault(); orderGroup(draggedGroup, group.id); } }}>
          <button type="button" disabled={!!w.busy || !w.ready} aria-current={!w.query.trash && w.query.group_id === group.id ? 'page' : undefined}
            onClick={() => void w.changeQuery({ group_id: group.id, trash: false })}>{group.name}</button>
          <div className="backgroundMaterialActions">
            <button type="button" disabled={locked} draggable={!locked} aria-label={`拖动分组${group.name}排序`} onDragStart={event => {
              setDraggedGroup(group.id); event.dataTransfer.setData('text/plain', `background-material-group:${group.id}`); event.dataTransfer.effectAllowed = 'move';
            }} onDragEnd={() => setDraggedGroup(null)}>↕</button>
            <button type="button" disabled={locked || i === 0} aria-label={`上移分组${group.name}`} onClick={() => orderGroup(group.id, customGroups[i - 1]!.id)}>↑</button>
            <button type="button" disabled={locked || i === customGroups.length - 1} aria-label={`下移分组${group.name}`} onClick={() => orderGroup(group.id, customGroups[i + 1]!.id)}>↓</button>
            <button type="button" disabled={locked} onClick={() => beginEdit({ op: 'group_rename', id: group.id }, group.name)}>改名</button>
            <button type="button" disabled={locked} onClick={() => setConfirm({ command: { op: 'group_delete', payload: { id: group.id } }, label: '删除分组',
              text: `删除分组“${group.name}”？其中素材归入未分组，回收站状态不变，不删除任何原文件。` })}>删除</button>
          </div>
        </li>)}</ol>
      </nav>
      <main className="backgroundMaterialContent" aria-busy={!!w.busy}>
        <form className="backgroundMaterialSearch" onSubmit={event => { event.preventDefault(); void w.changeQuery({ text: search }); }}>
          <label htmlFor={searchId}>搜索当前分组</label><input id={searchId} type="search" maxLength={240} value={search} disabled={!!w.busy}
            onChange={event => setSearch(Array.from(event.target.value).slice(0, 120).join(''))} placeholder="按素材名称搜索" />
          <button type="submit" disabled={!!w.busy || !w.ready}>搜索</button>
          {w.query.text && <button type="button" disabled={!!w.busy || !w.ready} onClick={() => void w.changeQuery({ text: '' })}>清空</button>}
          <label>排序 <select value={w.query.sort} disabled={!!w.busy || !w.ready} onChange={event => void w.changeQuery({ sort: event.target.value as typeof w.query.sort })}>
            <option value="manual">手动顺序</option><option value="name_asc">名称升序</option><option value="name_desc">名称降序</option>
            <option value="newest">最新导入</option><option value="oldest">最早导入</option>
          </select></label>
        </form>
        {editor && <form className="backgroundMaterialForm" onSubmit={event => { event.preventDefault(); saveName(); }}>
          <fieldset disabled={locked}><legend>{editor.op === 'group_create' ? '新建分组' : '修改显示名称'}</legend>
            <label htmlFor={nameId}>名称</label><input id={nameId} value={name} autoFocus onChange={event => setName(event.target.value)} maxLength={240} />
            <small>1–120 个字符；不会重命名源文件。</small>
            <div className="backgroundMaterialActions"><button type="submit">保存</button><button type="button" onClick={() => setEditor(null)}>取消</button></div>
          </fieldset>
        </form>}
        {formError && <p role="alert" className="backgroundMaterialError">{formError}</p>}
        {confirm && <div className="backgroundMaterialWarning" role="group" aria-label="确认目录操作"><p>{confirm.text}</p>
          <button type="button" disabled={locked} onClick={() => { const action = confirm; setConfirm(null); void w.mutate(action.command, action.label); }}>确认{confirm.label}</button>
          <button type="button" disabled={!!w.busy} onClick={() => setConfirm(null)}>取消</button>
        </div>}
        {w.choosing ? <div className="backgroundMaterialActions"><button type="button" disabled={locked || selected.length !== 1 || w.query.trash}
          onClick={() => void w.choose()}>使用所选背景</button><span>只有点击后才向当前照片传递稳定身份；图片校验和应用由证件照背景工具处理。</span></div> :
          <div className="backgroundMaterialBulk">
            <div className="backgroundMaterialActions"><button type="button" disabled={locked || !rows.length} onClick={w.selectPage}>选择本页</button>
              <button type="button" disabled={!!w.busy || !selected.length} onClick={w.clearSelection}>清空选择</button>
              <span>已选 {selected.length} 张（含其他页 {selected.filter(row => !rows.some(item => item.id === row.id)).length} 张）</span></div>
            {w.query.trash ? <button type="button" disabled={locked || !selected.length || !head || selected.length > head.limits.max_active - head.counts.active}
              onClick={() => void w.mutate({ op: 'material_restore', payload: { ids: selected.map(r => r.id) } }, '恢复素材')}>恢复所选</button> :
              <div className="backgroundMaterialActions"><label>移至分组 <select value={moveGroup} disabled={locked || !selected.length} onChange={event => setMoveGroup(event.target.value)}>
                {head?.groups.map(group => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label>
                <button type="button" disabled={locked || !selected.length} onClick={() => void w.mutate({ op: 'material_move', payload: { ids: selected.map(r => r.id), group_id: moveGroup } }, '移动素材')}>移动所选</button>
                <button type="button" disabled={locked || !selected.length} onClick={remove}>移入回收站</button>
              </div>}
          </div>}
        {w.query.trash && <p className="backgroundMaterialHint">回收站只支持恢复，不提供永久删除。恢复不修改源文件；已删除的分组归入未分组。</p>}
        {!head && <p>{w.busy ? '正在读取本地素材目录…' : '尚未取得目录。请刷新；不会把读取失败当作空目录。'}</p>}
        {head && w.page && !w.page.total && <div className="backgroundMaterialEmpty"><strong>{w.query.text ? '没有匹配的背景素材' : w.query.trash ? '回收站为空' : '这里还没有背景素材'}</strong>
          <p>导入你自己有权使用的本地图片，或切换分组和搜索条件。</p></div>}
        <ol className="backgroundMaterialGrid">{rows.map((row, i) => <li key={`${head?.library_id}-${head?.revision}-${row.id}`} className={w.selected.has(row.id) ? 'isSelected' : ''}
          onDragOver={event => { if (dragged && canOrder) event.preventDefault(); }} onDrop={event => { if (dragged && canOrder) { event.preventDefault(); orderMaterial(dragged, row.id); } }}>
          <label className="backgroundMaterialCardLabel"><input type={w.choosing ? 'radio' : 'checkbox'} name={w.choosing ? radioId : undefined} checked={w.selected.has(row.id)}
            disabled={locked || (w.choosing && w.query.trash)} onChange={event => w.toggle(row, event.target.checked)} /><strong title={row.name}>{row.name}</strong></label>
          <Thumbnail row={row} revision={head!.revision} open={w.open && w.ready} port={w.port} />
          <small>{row.width} × {row.height} · {row.format.toUpperCase()} · {row.bits} bit{row.has_alpha ? ' · 含透明度' : ''}</small>
          <small>{formatBytes(row.bytes)} · {head?.groups.find(g => g.id === row.group_id)?.name ?? '未分组'}</small>
          <details><summary>素材身份</summary><dl><dt>内容 SHA-256</dt><dd>{row.sha256}</dd><dt>导入时间</dt><dd>{new Date(row.created_at).toLocaleString()}</dd>
            {row.deleted_at !== null && <><dt>移除时间</dt><dd>{new Date(row.deleted_at).toLocaleString()}</dd></>}</dl></details>
          {!w.query.trash && <div className="backgroundMaterialActions">
            <button type="button" disabled={!canOrder} draggable={canOrder} aria-label={`拖动素材${row.name}排序`} onDragStart={event => {
              setDragged(row.id); event.dataTransfer.setData('text/plain', `background-material:${row.id}`); event.dataTransfer.effectAllowed = 'move';
            }} onDragEnd={() => setDragged(null)}>↕</button>
            <button type="button" disabled={!canOrder || i === 0} aria-label={`前移素材${row.name}`} onClick={() => orderMaterial(row.id, rows[i - 1]!.id)}>前移</button>
            <button type="button" disabled={!canOrder || i === rows.length - 1} aria-label={`后移素材${row.name}`} onClick={() => orderMaterial(row.id, rows[i + 1]!.id)}>后移</button>
            <button type="button" disabled={locked} onClick={() => beginEdit({ op: 'material_rename', id: row.id }, row.name)}>改名</button>
          </div>}
        </li>)}</ol>
        {w.page && w.page.total > 0 && <nav className="backgroundMaterialActions" aria-label="背景素材分页">
          <button type="button" disabled={!!w.busy || !w.ready || w.query.offset === 0} onClick={() => void w.changeQuery({ offset: Math.max(0, w.query.offset - w.query.limit) })}>上一页</button>
          <span>第 {Math.floor(w.query.offset / w.query.limit) + 1} / {Math.ceil(w.page.total / w.query.limit)} 页 · 匹配 {w.page.total} 张</span>
          <button type="button" disabled={!!w.busy || !w.ready || w.page.next_offset === null} onClick={() => { if (w.page?.next_offset !== null && w.page) void w.changeQuery({ offset: w.page.next_offset }); }}>下一页</button>
        </nav>}
        {w.query.sort === 'manual' && !w.query.trash && <small>拖动或前移、后移只调整当前页可见素材的相对位置；其他页和隐藏素材的位置不变。</small>}
      </main>
    </div>
    {!!w.outcomes.length && <details className="backgroundMaterialOutcomes" open><summary>逐文件导入结果（{w.outcomes.length}）</summary>
      <ol>{w.outcomes.map((result, i) => <li key={`${i}-${result.index}`}><strong>{outcomeLabels[result.status] ?? result.status}</strong> {result.name || `第 ${result.index + 1} 项`}<p>{result.message}</p></li>)}</ol>
      <button type="button" onClick={w.clearOutcomes}>收起本次结果</button>
    </details>}
  </div>;
}
