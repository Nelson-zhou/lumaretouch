import {associationRequest,sourceAssociation} from './associationRequest';
import type {AssociationRequest} from './associationProof';
import {useEffect, useState} from 'react';
import {useBatchWorkflow} from '../batch/useBatchWorkflow';
import {BatchReview} from '../batch/BatchReview';
import {operationLabel, type FaceRef} from './model';
import type {PeopleOwner} from './usePeopleWorkflow';
import {sameFace, samePeopleRequest, type PeopleTransferRequest, type PeopleTransferProof, type ExplicitPeopleRequest} from './transferReview';
import {explicitRequest, isAvailableEntry, PEOPLE_TRANSFER_LIMITS, type FaceChoices, type PeopleInventoryResult} from './transferInventory';
import {useTransferInventory} from './useTransferInventory';
import {TransferFacePreview} from './TransferFacePreview';

type FrozenVisual = {id: string; inventory: PeopleInventoryResult; request: ExplicitPeopleRequest | AssociationRequest};
/** Existing batch owner still owns confirmation, commit, uncertainty and undo. */
export function ConfirmedPeopleTransfer({owner, targets, currentPath, enabled, onComplete}: {
  owner: PeopleOwner; targets: string[]; currentPath: string; enabled: boolean; onComplete: () => void;
}) {
  const view = owner.value;
  const source = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  const key = JSON.stringify([view?.binding, view?.revision, view?.association_revision, source?.face_ref]);
  const [choice, setChoice] = useState<{key: string; leaves: string[]}>({key: '', leaves: []});
  const [targetPolicy, setTargetPolicy] = useState<'confirmed_person_only' | 'explicit_face_map' | 'persistent_association'>('confirmed_person_only');
  const [associationOperation,setAssociationOperation]=useState<AssociationRequest['operation']>('create');
  const [associationId,setAssociationId]=useState(()=>crypto.randomUUID().replace(/-/g,''));
  const persistent=targetPolicy==='persistent_association';
  const manual=targetPolicy!=='confirmed_person_only';
  const targetLimit=persistent?15:PEOPLE_TRANSFER_LIMITS.targets;
  const [policy, setPolicy] = useState<'recheck' | 'skip_and_report'>('recheck');
  const [last, setLast] = useState<{id: string; epoch: string} | null>(null);
  const [undone, setUndone] = useState(false);
  const [faceChoices, setFaceChoices] = useState<{requestId: string; choices: FaceChoices}>({requestId: '', choices: {}});
  const [images, setImages] = useState<{requestId: string; ready: Record<string, boolean>}>({requestId: '', ready: {}});
  const [frozen, setFrozen] = useState<FrozenVisual | null>(null);
  const [frozenImages, setFrozenImages] = useState<{requestId: string; ready: Record<string, boolean>}>({requestId: '', ready: {}});
  const chosen = choice.key === key ? choice.leaves : [];
  const links = view?.links.filter(link => link.face_instance_id === source?.face_ref.face_instance_id && link.state === 'confirmed') ?? [];
  const resolved = view?.resolved;
  const matches = !!source && !!resolved && sameFace(resolved.face_ref, source.face_ref)
    && resolved.state_revision === view?.revision && resolved.association_revision === view?.association_revision;
  const operations = matches && resolved ? Object.entries(resolved.operations) : [];
  const selection: Record<string, string[]> = {};
  const available = operations.flatMap(([operation, values]) => Object.entries(values).map(([path, record]) => ({
    operation, path, value: record.value, key: JSON.stringify([operation, path]),
    conflict: resolved!.conflicts.some(item => item.operation_id === operation && item.parameter_path === path),
  })));
  for (const leaf of available) if (!leaf.conflict && chosen.includes(leaf.key)) (selection[leaf.operation] ??= []).push(leaf.path);
  const selected = [...new Set(targets)].filter(identity => identity !== view?.binding.document_id);
  const sourceReady = enabled && owner.enabled && !owner.state.pending && !owner.state.uncertain && !!source?.enabled
    && source.analysis_status === 'verified' && matches;
  const inventoryKey = JSON.stringify([key, selected, currentPath, targetPolicy]);
  const inventory = useTransferInventory({key: inventoryKey, enabled: sourceReady && manual, docs: selected,
    source: view && source ? {binding: view.binding, state_revision: view.revision,
      association_revision: view.association_revision, face_ref: source.face_ref} : undefined});
  const listing = inventory.ui.contextKey === inventoryKey && inventory.ui.phase === 'ready' ? inventory.ui.result : null;
  const choices = listing && faceChoices.requestId === listing.request_id ? faceChoices.choices : {};
  const allImagesReady = !!listing && images.requestId === listing.request_id
    && [listing.source, ...listing.targets.filter(isAvailableEntry)].every(entry => images.ready[entry.document.document_id] === true);
  const explicit = explicitRequest(listing, selected, source?.face_ref, selection, choices);
  const association=associationRequest(listing,selected,source?.face_ref,selection,choices,associationOperation,associationId);
  const existingAssociation=sourceAssociation(listing,source?.face_ref);
  const request: PeopleTransferRequest | undefined = persistent ? association : targetPolicy === 'explicit_face_map' ? explicit
    : source && Object.keys(selection).length ? {source_ref: source.face_ref, selection, target_policy: 'confirmed_person_only'} : undefined;
  const proof: PeopleTransferProof | undefined = manual ? (persistent?association?.source:explicit?.source)
    : view && links.length === 1 ? {...view.binding, state_revision: view.revision,
      association_revision: view.association_revision, person_id: links[0].person_id} : undefined;
  const ready = sourceReady && !!proof && !!request && (!manual || allImagesReady);
  const flow = useBatchWorkflow({docs: selected, moduleScope: persistent&&associationOperation==='unlink'?[]:Object.keys(selection), conflictPolicy: persistent?'recheck':policy,
    sourceDocumentId: view?.binding.document_id ?? '', referencePath: currentPath, enabled: ready,
    label: persistent?'持久人物关联：所有成员共同审核，逐人脸显式参数仍优先':targetPolicy === 'explicit_face_map' ? '仅本次手动指定的人脸配对，不建立持久人物关联' : '仅向用户已确认的同一人物同步明确勾选的参数',
    peopleTransfer: request, peopleProof: proof}, onComplete);
  const busy = ['preflighting', 'committing', 'uncertain'].includes(flow.ui.phase);
  const disabled = !enabled || !owner.enabled || owner.state.pending || owner.state.uncertain || busy;
  const inventoryBusy = inventory.ui.contextKey === inventoryKey && ['loading', 'uncertain'].includes(inventory.ui.phase);
  useEffect(() => {
    const result = flow.ui.result;
    if (!result?.success) return;
    if (flow.ui.operation === 'commit' && result.batch_id) {
      const evidence = flow.ui.plan?.targets.find(target => target.people_transfer)?.people_transfer;
      if(flow.ui.plan?.persistent_association&&flow.ui.plan.association_source?.association){setLast({id:result.batch_id,epoch:flow.ui.plan.association_source.association.owner.document.epoch});setUndone(false);setAssociationId(crypto.randomUUID().replace(/-/g,''));}
      else if (evidence) { setLast({id: result.batch_id, epoch: evidence.source_document.epoch}); setUndone(false); }
    } else if (flow.ui.operation === 'undo') setUndone(true);
    else if (flow.ui.operation === 'redo') setUndone(false);
  }, [flow.ui.result, flow.ui.operation, flow.ui.plan]);
  const setLeaves = (leaves: string[]) => setChoice({key, leaves: [...new Set(leaves)]});
  function chooseFaces(documentId: string, refs: FaceRef[]) {
    if (!listing || disabled) return;
    setFaceChoices({requestId: listing.request_id, choices: {...choices, [documentId]: persistent?refs.slice(-1):refs}});
  }
  function start() {
    if (flow.ui.phase === 'uncertain') {void flow.start(); return;}
    if (!ready || busy) return;
    // Capture the exact visual evidence used by this request, never live newer choices.
    const visualId = crypto.randomUUID();
    const visualRequest=persistent?association:explicit;
    setFrozen(visualRequest && listing ? {id: visualId, inventory: listing, request: visualRequest} : null);
    setFrozenImages({requestId: visualId, ready: {}});
    void flow.start();
  }
  const visibleFrozen = frozen && flow.ui.plan && samePeopleRequest(flow.ui.plan.applies, frozen.request) ? frozen : null;
  const frozenReady = !!visibleFrozen && frozenImages.requestId === visibleFrozen.id
    && [visibleFrozen.inventory.source.document.document_id, ...visibleFrozen.request.targets.map(row => row.target.document.document_id)]
      .every(id => frozenImages.ready[id] === true);
  const needsFrozen = ['explicit_face_map','persistent_association'].includes(String(flow.ui.plan?.applies?.target_policy));
  const previewStatus = (requestId: string, id: string, value: boolean) => setImages(old => ({requestId,
    ready: {...(old.requestId === requestId ? old.ready : {}), [id]: value}}));
  const frozenStatus = (requestId: string, id: string, value: boolean) => setFrozenImages(old => old.requestId === requestId
    ? {requestId, ready: {...old.ready, [id]: value}} : old);
  if (!view && flow.ui.phase === 'closed') return null;
  return <section className="peopleTransfer" aria-label="跨照片人物参数同步">
    <details><summary>跨照片同步人物参数</summary>
      <p>在胶片栏选目标照片，再选择关联策略和参数。只同步勾选的标量参数，不复制恢复蒙版、关键点或局部素材。持久关联必须单独选择并逐成员确认。</p>
      <fieldset disabled={disabled}><legend>选择目标方式</legend>
        <label><input type="radio" name="peopleTransferPolicy" checked={targetPolicy === 'confirmed_person_only'}
          onChange={() => setTargetPolicy('confirmed_person_only')}/>仅已有的已确认人物关联</label>
        <label><input type="radio" name="peopleTransferPolicy" checked={targetPolicy === 'explicit_face_map'}
          onChange={() => setTargetPolicy('explicit_face_map')}/>逐张手动指定，仅本次配对</label>
        <label><input type="radio" name="peopleTransferPolicy" checked={persistent} onChange={()=>setTargetPolicy('persistent_association')}/>明确建立或维护持久人物关联</label>
      </fieldset>
      {persistent&&<fieldset disabled={disabled}><legend>持久关联操作</legend>
        <select value={associationOperation} onChange={event=>setAssociationOperation(event.currentTarget.value as AssociationRequest['operation'])}>
          <option value="create">新建已审核的匿名人物关联</option><option value="patch">更新共同继承的所选参数</option><option value="unlink">解除整个关联，保留每张显式编辑与历史</option>
        </select>
        <p>每张照片只选择一张人脸，最多 16 个独立文档成员（含源图）。所有成员同时提交；人脸显式参数优先于共享人物参数。不会自动识别或扩充成员。</p>
        <p>成员源图或可用状态改变后暂停共享编辑；保留上次已接受的本地投影。关联期间不允许直接重新分析成员，需先完整解除关联。当前仅支持成员齐全时更新或整体解除。</p>
        {existingAssociation&&<p>已存关联 {existingAssociation.association_id} · 内容版本 {existingAssociation.generation}。请在胶片栏选择其余全部成员，并重新逐张确认。</p>}
      </fieldset>}
      {targetPolicy === 'confirmed_person_only' && links.length !== 1 && <p role="status">所选人脸必须有且只有一个已确认的匿名人物关联；独立副本可改用“仅本次配对”。</p>}
      {manual && <>
        <p>最多逐张审核 {targetLimit} 张目标照片。每张{persistent?'只':'至少'}手动勾选一张已启用且分析已验证的人脸，不会按外貌、编号或相同像素自动配对。</p>
        <p>缩略图显示实际未编辑源图及其人脸坐标，不是最终修图效果。{persistent?'持久操作将包括源成员，所有成员需再次审核。':'确认不建立或更改持久人物关联。'}</p>
        <button type="button" disabled={!sourceReady || !selected.length || selected.length > targetLimit || busy || inventoryBusy}
          onClick={() => void inventory.start()}>{listing ? '重新读取并清空本次配对' : `读取所选 ${selected.length} 张照片的人脸`}</button>
        {selected.length > targetLimit && <p role="status">请将目标减少至 {targetLimit} 张以内；没有偷偷截断目标名单。</p>}
        {!sourceReady && <p role="status">请先选择已启用、分析已验证且参数已解析的源人脸。</p>}
        {inventory.ui.contextKey === inventoryKey && <>
          {inventory.ui.phase === 'loading' && <p role="status">只读获取实际源图和人脸，不进行分析或修改照片…</p>}
          {inventory.ui.message && <p role="status">{inventory.ui.message}</p>}
          {inventory.ui.phase === 'uncertain' && <button type="button" disabled={busy} onClick={() => void inventory.query()}>查询同一次读取</button>}
          {inventoryBusy && <button type="button" disabled={busy} onClick={inventory.cancel}>取消本次只读读取</button>}
        </>}
        {listing && <>
          <div className="transferFaceGrid">
            <TransferFacePreview key={`${listing.request_id}:source`} entry={listing.source} selected={source ? [source.face_ref] : []}
              label={`源人脸 · ${currentPath.split('/').pop() || '当前照片'}`} readOnly
              onPreviewStatus={(id, value) => previewStatus(listing.request_id, id, value)}/>
            {listing.targets.map((entry, index) => isAvailableEntry(entry) ? <TransferFacePreview key={`${listing.request_id}:${entry.document.document_id}`}
              entry={entry} selected={choices[entry.document.document_id] ?? []} label={`目标照片 ${index + 1}`} disabled={disabled}
              onChange={refs => chooseFaces(entry.document.document_id, refs)} onPreviewStatus={(id, value) => previewStatus(listing.request_id, id, value)}/>
              : <p className="transferFaceBlocked" key={entry.document.document_id}>目标 {entry.document.document_id} 受阻：{entry.blocked}。请打开并处理该照片，或从胶片栏目标选择中移除。</p>)}
          </div>
          {listing.rejected_docs.map(row => <p className="transferFaceBlocked" key={row.doc}>未采用目标 {row.doc}：{row.error}</p>)}
          <p role="status">已手动指定 {selected.filter(id => choices[id]?.length).length} / {selected.length} 张目标照片。{!(persistent?association:explicit) ? (persistent?'需要每张精确成员及其全部关联共同版本；新建或更新还需选择参数，不能跳过受阻成员。':'每张目标都需要有效选择，且至少勾选一项参数，才能预检。') : '下一步将冻结配对与所选参数，仍需在审核窗口最终确认。'}</p>
        </>}
      </>}
      <fieldset disabled={disabled}><legend>逐模块选择参数</legend>
        {operations.map(([operation]) => {
          const leaves = available.filter(leaf => leaf.operation === operation);
          return <details key={operation}><summary>{operationLabel(operation)}</summary>
            <button type="button" onClick={() => setLeaves([...chosen, ...leaves.filter(leaf => !leaf.conflict).map(leaf => leaf.key)])}>勾选本模块可迁移参数</button>
            <button type="button" onClick={() => setLeaves(chosen.filter(id => !leaves.some(leaf => leaf.key === id)))}>取消本模块</button>
            {leaves.map(leaf => <label key={leaf.key} style={{display: 'block'}}>
              <input type="checkbox" checked={chosen.includes(leaf.key)} disabled={leaf.conflict}
                onChange={event => setLeaves(event.currentTarget.checked ? [...chosen, leaf.key] : chosen.filter(id => id !== leaf.key))}/>
              {leaf.path}：{String(leaf.value)}{leaf.conflict ? '（来源有分组冲突）' : ''}
            </label>)}
          </details>;
        })}
        <label>冲突处理<select disabled={persistent} value={persistent?'recheck':policy} onChange={event => setPolicy(event.currentTarget.value as typeof policy)}>
          <option value="recheck">任一目标受阻则不提交整组</option><option value="skip_and_report">跳过受阻目标并逐张报告</option>
        </select></label>
      </fieldset>
      <button type="button" disabled={!ready || !selected.length || busy} onClick={start}>预检所选 {selected.length} 张照片的人物参数</button>
      <button type="button" disabled={!last || busy || !enabled || !owner.enabled || owner.state.pending || owner.state.uncertain || last.epoch !== view?.binding.document_epoch}
        onClick={() => last && (undone ? flow.redo(last.id) : flow.undo(last.id))}>{undone ? '重做本次人物同步' : '撤销本次人物同步'}</button>
      <p>源图、人脸分析、独立人物状态、目标或关联改变后必须重新预检。没有逐张明确指定或已有确认关联的目标不会被猜测补齐。</p>
    </details>
    <BatchReview state={flow.ui} onClose={flow.close} onCommit={() => (!needsFrozen || frozenReady) && flow.commit()} onReview={start}
      onQuery={flow.query} onAcknowledge={flow.acknowledgeInspection}
      commitBlockedReason={needsFrozen && !frozenReady ? '冻结配对的实际源图尚未全部验证显示，不能提交；若预览失败，请关闭并重新读取。' : undefined}
      peoplePreview={visibleFrozen ? <div>
        <p>请逐张核对下面冻结的人脸框。{visibleFrozen.request.target_policy==='persistent_association'?'最终确认授权列出的持久成员及共享参数，源成员也会改变。':'最终确认只授权本次配对与列出的参数，不建立持久人物关联。'}</p>
        <div className="transferFaceGrid">
          <TransferFacePreview key={`frozen:${visibleFrozen.id}:source`} entry={visibleFrozen.inventory.source}
            selected={[visibleFrozen.request.source_ref]} label="冻结源人脸" readOnly
            onPreviewStatus={(id, value) => frozenStatus(visibleFrozen.id, id, value)}/>
          {visibleFrozen.request.targets.map((row, index) => {
            const entry = visibleFrozen.inventory.targets.find(item => item.document.document_id === row.target.document.document_id);
            return entry && isAvailableEntry(entry) ? <TransferFacePreview key={`frozen:${visibleFrozen.id}:${row.target.document.document_id}`}
              entry={entry} selected={row.target_refs} label={`冻结目标 ${index + 1}`} readOnly
              onPreviewStatus={(id, value) => frozenStatus(visibleFrozen.id, id, value)}/> : null;
          })}
        </div>
      </div> : undefined}/>
  </section>;
}
