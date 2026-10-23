// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useMemo, useRef, useState, useSyncExternalStore, type ChangeEvent, type DragEvent} from 'react';
import {CreativeLayerClient} from './client';
import {CREATIVE_BLEND_MODES, checkedCreativeDocument, eligibleParents, layerAncestors, layerHidden, layerLocked,
  layerRows, previewMatches, type CreativeAlignment, type CreativeAuthority, type CreativeBlend,
  type CreativeDocument, type CreativeHistory, type CreativeLayer, type CreativePorts, type CreativePreview,
  type CreativeTransform} from './model';
import './creativeLayers.css';

const blendLabels: Record<CreativeBlend, string> = {normal: '正常', multiply: '正片叠底', screen: '滤色', lighten: '变亮', darken: '变暗'};
const alignmentLabels: Record<CreativeAlignment, string> = {
  left: '左对齐', hcenter: '水平居中', right: '右对齐', top: '顶对齐', vcenter: '垂直居中', bottom: '底对齐',
};
export interface CreativeLayersPanelProps {
  /** Immutable authoritative snapshot, not an optimistic UI copy. */
  snapshot: CreativeDocument | null;
  ownershipToken: string | null;
  ports: CreativePorts;
  preview?: CreativePreview | null;
  history?: CreativeHistory | null;
  busy?: boolean;
  unavailableReason?: string;
}

function NumberField({label, value, onChange, min, max, step = 'any'}: {
  label: string; value: string; onChange: (value: string) => void; min?: number; max?: number; step?: number | 'any';
}) {
  return <label className="creative-number"><span>{label}</span><input type="number" value={value}
    min={min} max={max} step={step} onChange={event => onChange(event.currentTarget.value)}/></label>;
}
const parsed = (value: string): number => value.trim() ? Number(value) : NaN;

function CanvasInspector({document, disabled, client}: {document: CreativeDocument; disabled: boolean; client: CreativeLayerClient}) {
  const [width, setWidth] = useState(String(document.canvas.width));
  const [height, setHeight] = useState(String(document.canvas.height));
  const [dpi, setDpi] = useState(String(document.canvas.dpi));
  const w = parsed(width), h = parsed(height), d = parsed(dpi);
  const valid = Number.isSafeInteger(w) && w > 0 && Number.isSafeInteger(h) && h > 0 &&
    w <= 100_000_000 && h <= 100_000_000 && w * h <= 100_000_000 && Number.isFinite(d) && d >= 1e-6 && d <= 1_000_000;
  const changed = w !== document.canvas.width || h !== document.canvas.height || d !== document.canvas.dpi;
  return <section aria-label="画布属性" className="creative-properties">
    <h4>画布属性</h4><p>当前未选中图层。尺寸单位为像素；DPI 为输出分辨率元数据。</p>
    <form onSubmit={event => {event.preventDefault(); if (!disabled && valid && changed)
      void client.execute({action: 'canvas', width: w, height: h, dpi: d}, '更新画布');}}>
      <fieldset disabled={disabled}><legend>画布尺寸与分辨率</legend>
        <NumberField label="宽度（px）" value={width} onChange={setWidth} min={1} max={100_000_000} step={1}/>
        <NumberField label="高度（px）" value={height} onChange={setHeight} min={1} max={100_000_000} step={1}/>
        <NumberField label="DPI" value={dpi} onChange={setDpi} min={1e-6} max={1_000_000}/>
        {!valid && <p role="alert">请输入有效尺寸与 DPI；画布安全上限为 1 亿像素。</p>}
        <button type="submit" disabled={!valid || !changed}>应用画布属性</button>
        {changed && <small>未应用草稿，不代表当前画布已改变。</small>}
      </fieldset>
    </form>
  </section>;
}

function TransformInspector({layer, disabled, client}: {layer: CreativeLayer; disabled: boolean; client: CreativeLayerClient}) {
  const [draft, setDraft] = useState(() => ({x: String(layer.transform.x), y: String(layer.transform.y),
    scale_x: String(layer.transform.scale_x), scale_y: String(layer.transform.scale_y), rotation: String(layer.transform.rotation),
    flip_x: layer.transform.flip_x, flip_y: layer.transform.flip_y}));
  const value: CreativeTransform = {x: parsed(draft.x), y: parsed(draft.y), scale_x: parsed(draft.scale_x), scale_y: parsed(draft.scale_y),
    rotation: parsed(draft.rotation), flip_x: draft.flip_x, flip_y: draft.flip_y};
  const valid = Number.isFinite(value.x) && Math.abs(value.x) <= 1e9 && Number.isFinite(value.y) && Math.abs(value.y) <= 1e9 &&
    Number.isFinite(value.scale_x) && value.scale_x >= 1e-6 && value.scale_x <= 1e4 &&
    Number.isFinite(value.scale_y) && value.scale_y >= 1e-6 && value.scale_y <= 1e4 &&
    Number.isFinite(value.rotation) && Math.abs(value.rotation) <= 360000;
  const changed = (Object.keys(value) as (keyof CreativeTransform)[]).some(key => value[key] !== layer.transform[key]);
  return <section aria-label="图片图层变换">
    <form onSubmit={event => {event.preventDefault(); if (!disabled && valid && changed)
      void client.execute({action: 'transform', layer_id: layer.id, transform: value}, '应用图层变换');}}>
      <fieldset disabled={disabled}><legend>图片变换</legend>
        <div className="creative-field-grid">
          <NumberField label="X（px）" value={draft.x} onChange={x => setDraft({...draft, x})} min={-1e9} max={1e9}/>
          <NumberField label="Y（px）" value={draft.y} onChange={y => setDraft({...draft, y})} min={-1e9} max={1e9}/>
          <NumberField label="水平缩放（倍）" value={draft.scale_x} onChange={scale_x => setDraft({...draft, scale_x})} min={1e-6} max={1e4}/>
          <NumberField label="垂直缩放（倍）" value={draft.scale_y} onChange={scale_y => setDraft({...draft, scale_y})} min={1e-6} max={1e4}/>
          <NumberField label="旋转（度）" value={draft.rotation} onChange={rotation => setDraft({...draft, rotation})} min={-360000} max={360000}/>
        </div>
        <div className="creative-actions">
          <label><input type="checkbox" checked={draft.flip_x} onChange={event => setDraft({...draft, flip_x: event.currentTarget.checked})}/>水平翻转</label>
          <label><input type="checkbox" checked={draft.flip_y} onChange={event => setDraft({...draft, flip_y: event.currentTarget.checked})}/>垂直翻转</label>
        </div>
        {!valid && <p role="alert">请输入有限的有效变换值；缩放范围为 0.000001 至 10000 倍。</p>}
        <button type="submit" disabled={!valid || !changed}>应用变换</button>
        {changed && <small>未应用草稿。先应用变换，再执行对齐。</small>}
      </fieldset>
    </form>
    <fieldset disabled={disabled || changed}><legend>相对画布对齐</legend><div className="creative-alignment">
      {(Object.keys(alignmentLabels) as CreativeAlignment[]).map(alignment => <button type="button" key={alignment}
        onClick={() => void client.execute({action: 'align', layer_id: layer.id, alignment}, alignmentLabels[alignment])}>
        {alignmentLabels[alignment]}</button>)}
    </div></fieldset>
  </section>;
}

function LayerInspector({document, layer, disabled, client, ports, canDelete, onMask}: {
  document: CreativeDocument; layer: CreativeLayer; disabled: boolean; client: CreativeLayerClient;
  ports: CreativePorts; canDelete: boolean; onMask: (file: File) => void;
}) {
  const [name, setName] = useState(layer.name), [opacity, setOpacity] = useState(String(layer.opacity * 100));
  const maskInput = useRef<HTMLInputElement>(null);
  const locked = layerLocked(document, layer), editingDisabled = disabled || locked;
  const percentage = parsed(opacity), validOpacity = Number.isFinite(percentage) && percentage >= 0 && percentage <= 100;
  const siblings = document.layers.filter(item => item.parent_id === layer.parent_id), index = siblings.findIndex(item => item.id === layer.id);
  const move = (parent_id: string | null, nextIndex: number) => void client.execute({action: 'move', layer_id: layer.id, parent_id, index: nextIndex}, '移动图层');
  const parents = eligibleParents(document, layer);
  return <section className="creative-properties" aria-label="所选图层属性">
    <h4>{layer.kind === 'group' ? '图层组' : '图片图层'}属性</h4>
    {locked && <p role="status">{layer.locked ? '当前图层已锁定。' : '上级图层组已锁定。'}解锁后才能修改。</p>}
    {layerHidden(document, layer) && <p>此图层当前不可见，可能由自身或上级组隐藏。</p>}
    <form onSubmit={event => {event.preventDefault(); if (!editingDisabled && name.trim() && name !== layer.name)
      void client.execute({action: 'rename', layer_id: layer.id, name: name.trim()}, '重命名图层');}}>
      <fieldset disabled={editingDisabled}><legend>名称</legend><label>图层名称<input value={name} onChange={event => setName(event.currentTarget.value)}/></label>
        <button type="submit" disabled={!name.trim() || name.trim() === layer.name}>保存名称</button></fieldset>
    </form>
    <fieldset disabled={editingDisabled}><legend>合成</legend>
      <label>混合模式<select value={layer.blend} onChange={event => void client.execute({action: 'blend', layer_id: layer.id,
        blend: event.currentTarget.value as CreativeBlend}, '更新混合模式')}>
        {CREATIVE_BLEND_MODES.map(mode => <option value={mode} key={mode}>{blendLabels[mode]}</option>)}
      </select></label>
      <form onSubmit={event => {event.preventDefault(); if (!editingDisabled && validOpacity && percentage / 100 !== layer.opacity)
        void client.execute({action: 'opacity', layer_id: layer.id, opacity: percentage / 100}, '更新不透明度');}}>
        <NumberField label="不透明度（%）" value={opacity} onChange={setOpacity} min={0} max={100}/>
        <input type="range" aria-label="不透明度草稿" min={0} max={100} step={0.1}
          value={validOpacity ? percentage : layer.opacity * 100} onChange={event => setOpacity(event.currentTarget.value)}/>
        <button type="submit" disabled={!validOpacity || percentage / 100 === layer.opacity}>应用不透明度</button>
        {percentage / 100 !== layer.opacity && <small>未应用草稿</small>}
      </form>
    </fieldset>
    <fieldset disabled={editingDisabled}><legend>层级与顺序</legend>
      <label>所属图层组<select value={layer.parent_id ?? ''} onChange={event => {
        const parent_id = event.currentTarget.value || null;
        move(parent_id, document.layers.filter(item => item.parent_id === parent_id && item.id !== layer.id).length);
      }}><option value="">画布根层级</option>{parents.map(group => <option value={group.id} key={group.id}>{group.name}</option>)}</select></label>
      <div className="creative-actions"><button type="button" disabled={index >= siblings.length - 1} onClick={() => move(layer.parent_id, index + 1)}>上移一层</button>
        <button type="button" disabled={index <= 0} onClick={() => move(layer.parent_id, index - 1)}>下移一层</button>
        {layer.kind === 'group' && <button type="button" onClick={() => void client.execute({action: 'ungroup', layer_id: layer.id}, '解散图层组')}>解散组并保留子图层</button>}
      </div>
    </fieldset>
    {layer.kind === 'image' ? <TransformInspector layer={layer} disabled={editingDisabled} client={client}/> :
      <p>组保留真实子图层。组变换尚未提供，不会假装已作用到子图层。</p>}
    <fieldset disabled={editingDisabled}><legend>栅格蒙版</legend>
      <p>{layer.mask_id ? '已附加真实栅格蒙版。' : '当前没有蒙版。'}{layer.kind === 'group' ? '组蒙版使用画布坐标。' : ''}</p>
      <input ref={maskInput} className="creative-file" type="file" accept="image/*" aria-label="选择栅格蒙版文件"
        disabled={editingDisabled || !ports.attachMask} onChange={event => {
          const file = event.currentTarget.files?.[0]; event.currentTarget.value = ''; if (file) onMask(file);
        }}/>
      <div className="creative-actions"><button type="button" disabled={!ports.attachMask} onClick={() => maskInput.current?.click()}>
        {layer.mask_id ? '替换栅格蒙版…' : '导入栅格蒙版…'}</button>
        <button type="button" disabled={!layer.mask_id || !ports.removeMask} onClick={() => void client.removeMask(layer.id)}>移除蒙版</button></div>
      {!ports.attachMask && <small>蒙版文件解码接口未接入，无法附加或替换蒙版。</small>}
      {layer.mask_id && !ports.removeMask && <small>蒙版移除接口未接入。</small>}
    </fieldset>
    <div className="creative-actions"><button type="button" disabled={editingDisabled}
      onClick={() => void client.execute({action: 'duplicate', layer_id: layer.id}, '复制图层')}>复制图层</button>
      <button type="button" disabled={editingDisabled || !canDelete} onClick={() => void client.execute({action: 'delete', layer_id: layer.id}, '删除图层')}>删除（可撤销）</button></div>
    {!canDelete && <small>宿主尚未确认可恢复的删除历史，删除暂不可用。</small>}
  </section>;
}

export function CreativeLayersPanel({snapshot, ownershipToken, ports, preview, history, busy = false, unavailableReason}: CreativeLayersPanelProps) {
  const validated = useMemo(() => {
    if (!snapshot) return {document: null, error: ''};
    try {return {document: checkedCreativeDocument(snapshot), error: ''};}
    catch (error) {return {document: null, error: error instanceof Error ? error.message : String(error)};}
  }, [snapshot]);
  const document = validated.document;
  const authority: CreativeAuthority | null = document && ownershipToken ? {document, ownership_token: ownershipToken, busy} : null;
  const context = useRef({authority, ports}); context.current = {authority, ports};
  const [client] = useState(() => new CreativeLayerClient(() => context.current.authority, () => context.current.ports));
  const state = useSyncExternalStore(client.subscribe, client.getState, client.getState);
  useEffect(() => {client.synchronize();}, [client, document?.document_id, document?.source_uid, document?.revision, ownershipToken]);
  // Subscriptions detach on unmount. Pending work belongs to the host, not this view.
  const [fileError, setFileError] = useState('');
  const [groupName, setGroupName] = useState('图层组');
  const imageInput = useRef<HTMLInputElement>(null);
  const [loadedPreview, setLoadedPreview] = useState(''), [failedPreview, setFailedPreview] = useState('');
  const previewCurrent = !!authority && previewMatches(preview, authority);
  const previewKey = previewCurrent ? JSON.stringify([preview.document_id, preview.source_uid, preview.ownership_token, preview.revision, preview.render_id, preview.url]) : '';
  const previewLoaded = !!previewKey && loadedPreview === previewKey && failedPreview !== previewKey;
  const pending = state.phase !== 'idle', disabled = !authority || busy || pending;
  const commandsDisabled = disabled || !ports.command;
  const selected = document?.layers.find(layer => layer.id === document.selected_id);
  const canDelete = !!history?.recoverable_delete && !!ports.undo;
  useEffect(() => {setFileError(''); setGroupName('图层组');}, [document?.document_id, document?.source_uid, ownershipToken]);
  const importFiles = (files: FileList | null) => {
    if (disabled || !ports.importImage) return;
    setFileError('');
    if (!files || files.length !== 1) {setFileError('请一次导入一个图片文件，等待确认后再导入下一张。'); return;}
    void client.importImage(files[0]);
  };
  const onDrop = (event: DragEvent<HTMLElement>) => {event.preventDefault(); importFiles(event.dataTransfer.files);};
  const onFile = (event: ChangeEvent<HTMLInputElement>) => {importFiles(event.currentTarget.files); event.currentTarget.value = '';};
  const selectedLocked = !!(document && selected && layerLocked(document, selected));
  const formKey = JSON.stringify([document?.document_id, document?.source_uid, ownershipToken, document?.revision, document?.selected_id]);
  return <section className="creative-layers" aria-label="创意图层文档" aria-busy={busy || pending}>
    <header className="creative-header"><div><h3>创意图层</h3><p>独立图层、真实合成，保留原始素材。</p></div>
      {document && <span className="creative-revision">修订 {document.revision} · {document.canvas.width} × {document.canvas.height}</span>}
    </header>
    {!authority ? <p role="status">{validated.error || unavailableReason || '尚未连接可编辑的图层文档及所有权令牌。'}</p> : <>
      {!ports.command && <p role="status">图层命令接口未接入。以下仅显示宿主确认的文档状态。</p>}
      <div className="creative-toolbar" aria-label="文档操作">
        <button type="button" disabled={disabled || !ports.undo || !history?.can_undo} onClick={() => void client.undo()}>撤销</button>
        <button type="button" disabled={disabled || !ports.redo || !history?.can_redo} onClick={() => void client.redo()}>重做</button>
        <span>历史由宿主管理</span>
        <button type="button" disabled={commandsDisabled} aria-pressed={document!.selected_id === null}
          onClick={() => void client.execute({action: 'select', layer_id: null}, '选择画布')}>编辑画布</button>
      </div>
      <div className="creative-workspace">
        <div className="creative-stage" onDragOver={event => {event.preventDefault(); event.dataTransfer.dropEffect = disabled || !ports.importImage ? 'none' : 'copy';}} onDrop={onDrop}>
          <figure className="creative-preview">
            {previewCurrent ? <>
              {failedPreview !== previewKey && <img key={previewKey} src={preview.url} alt="当前图层文档的真实合成预览" draggable={false}
                onLoad={() => {setLoadedPreview(previewKey); setFailedPreview('');}} onError={() => setFailedPreview(previewKey)}/>}
              <figcaption>{failedPreview === previewKey ? '真实渲染预览加载失败，返回功能已暂停。' :
                previewLoaded ? `已载入宿主合成预览 · 修订 ${preview.revision}` : '正在载入宿主合成预览…'}</figcaption>
            </> : <p role="status">尚未收到当前修订的真实渲染预览，不使用示意图或过期图片代替。</p>}
          </figure>
          <div className="creative-import">
            <input ref={imageInput} className="creative-file" type="file" accept="image/*" aria-label="选择图片图层文件"
              disabled={disabled || !ports.importImage} onChange={onFile}/>
            <button type="button" disabled={disabled || !ports.importImage} onClick={() => imageInput.current?.click()}>导入图片图层…</button>
            <p>{ports.importImage ? '将一个图片文件拖到预览区，或点击导入。解码成功并由引擎确认后才添加图层。' : '图片文件导入接口未接入。'}</p>
            {fileError && <p role="alert">{fileError}</p>}
          </div>
        </div>
        <aside className="creative-sidebar" aria-label="图层列表和属性">
          <section className="creative-stack"><h4>图层 <span>{document!.layers.length}</span></h4><p>从上到下显示，列表上方覆盖下方。</p>
            <ul className="creative-layer-list" aria-label="图层堆叠顺序">
              {layerRows(document!).map(({layer, depth}) => {
                const ancestorLocked = layerAncestors(document!, layer).some(parent => parent.locked);
                return <li key={layer.id} className={`creative-layer-row${layer.id === document!.selected_id ? ' is-selected' : ''}`}
                  style={{paddingInlineStart: `${Math.min(depth, 10) * 12 + 6}px`}}>
                  <button type="button" className="creative-layer-choice" disabled={commandsDisabled}
                    aria-pressed={layer.id === document!.selected_id} title={layer.name}
                    onClick={() => void client.execute({action: 'select', layer_id: layer.id}, '选择图层')}>
                    <span className="creative-kind">{layer.kind === 'group' ? '组' : '图'}</span><span>{layer.name}
                      <small>{layer.mask_id ? '含蒙版 · ' : ''}{layerHidden(document!, layer) ? '不可见' : blendLabels[layer.blend]}</small></span>
                  </button>
                  <button type="button" className="creative-row-toggle" disabled={commandsDisabled || layerLocked(document!, layer)}
                    aria-label={`${layer.visible ? '隐藏' : '显示'} ${layer.name}`} aria-pressed={layer.visible}
                    onClick={() => void client.execute({action: 'visibility', layer_id: layer.id, visible: !layer.visible}, layer.visible ? '隐藏图层' : '显示图层')}>
                    {layer.visible ? '显示' : '隐藏'}</button>
                  <button type="button" className="creative-row-toggle" disabled={commandsDisabled || ancestorLocked}
                    aria-label={`${layer.locked ? '解锁' : '锁定'} ${layer.name}`} aria-pressed={layer.locked}
                    onClick={() => void client.execute({action: 'lock', layer_id: layer.id, locked: !layer.locked}, layer.locked ? '解锁图层' : '锁定图层')}>
                    {layer.locked ? '已锁' : '未锁'}</button>
                </li>;
              })}
            </ul>
            {document!.layers.length === 0 && <p>尚无图层。请导入真实图片素材。</p>}
            <fieldset disabled={commandsDisabled}><legend>图层组</legend><label>新组名称<input value={groupName} onChange={event => setGroupName(event.currentTarget.value)}/></label>
              <div className="creative-actions"><button type="button" disabled={!groupName.trim()}
                onClick={() => void client.execute({action: 'group', name: groupName.trim(), layer_ids: []}, '创建空图层组')}>新建空组</button>
                <button type="button" disabled={!selected || selectedLocked || !groupName.trim()}
                  onClick={() => selected && void client.execute({action: 'group', name: groupName.trim(), layer_ids: [selected.id]}, '将所选图层编组')}>将所选图层编组</button></div>
            </fieldset>
          </section>
          {selected ? <LayerInspector key={formKey} document={document!} layer={selected} disabled={commandsDisabled} client={client}
            ports={ports} canDelete={canDelete} onMask={file => {if (!disabled && !selectedLocked) void client.attachMask(selected.id, file);}}/> :
            <CanvasInspector key={formKey} document={document!} disabled={commandsDisabled} client={client}/>}
        </aside>
      </div>
      <footer className="creative-return"><div><strong>返回修图流程</strong><p>仅返回当前修订已载入的真实合成结果。</p></div>
        <button type="button" disabled={disabled || !ports.returnNew || !previewLoaded}
          onClick={() => previewCurrent && previewLoaded && void client.returnImage('new', preview)}>作为新图片返回</button>
        <button type="button" disabled={disabled || !ports.updateOriginal || !previewLoaded}
          onClick={() => previewCurrent && previewLoaded && void client.returnImage('update', preview)}>更新原图片</button>
        {(!ports.returnNew || !ports.updateOriginal) && <small>
          {!ports.returnNew ? '新图片返回接口未接入。' : ''}{!ports.updateOriginal ? '更新原图片接口未接入。' : ''}</small>}
      </footer>
    </>}
    {state.message && <p className="creative-status" role={state.phase === 'uncertain' || state.phase === 'stale' ? 'alert' : 'status'}>{state.message}</p>}
    {(state.phase === 'sending' || state.phase === 'uncertain' || state.phase === 'awaiting_snapshot') && <div className="creative-actions">
      <button type="button" disabled={!ports.reconcile} onClick={() => void client.reconcile()}>核对原操作结果</button>
      {!ports.reconcile && <small>回执查询接口未接入，需要宿主核对结果；不会重新提交。</small>}
    </div>}
  </section>;
}
