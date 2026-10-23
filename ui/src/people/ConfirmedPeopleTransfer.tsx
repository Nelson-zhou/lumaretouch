import {useEffect, useState} from 'react';
import {useBatchWorkflow} from '../batch/useBatchWorkflow';
import {BatchReview} from '../batch/BatchReview';
import {operationLabel} from './model';
import type {PeopleOwner} from './usePeopleWorkflow';
import type {PeopleTransferRequest, PeopleTransferProof} from './transferReview';

/** One existing batch owner handles review/commit/uncertainty/undo. No copied face assets. */
export function ConfirmedPeopleTransfer({owner, targets, currentPath, enabled, onComplete}: {
  owner: PeopleOwner; targets: string[]; currentPath: string; enabled: boolean; onComplete: () => void;
}) {
  const view = owner.value;
  const source = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  const key = JSON.stringify([view?.binding.document_epoch, view?.binding.document_id, source?.face_ref]);
  const [choice, setChoice] = useState<{key: string; leaves: string[]}>({key: '', leaves: []});
  const [policy, setPolicy] = useState<'recheck' | 'skip_and_report'>('recheck');
  const [last, setLast] = useState<{id: string; epoch: string} | null>(null);
  const [undone, setUndone] = useState(false);
  const chosen = choice.key === key ? choice.leaves : [];
  const links = view?.links.filter(link => link.face_instance_id === source?.face_ref.face_instance_id && link.state === 'confirmed') ?? [];
  const resolved = view?.resolved;
  const matches = !!source && resolved?.face_ref.face_instance_id === source.face_ref.face_instance_id
    && resolved.face_ref.asset_sha256 === source.face_ref.asset_sha256 && resolved.face_ref.analysis_revision === source.face_ref.analysis_revision;
  const operations = matches && resolved ? Object.entries(resolved.operations) : [];
  const selection: Record<string, string[]> = {};
  const available = operations.flatMap(([operation, values]) => Object.entries(values).map(([path, record]) => ({
    operation, path, value: record.value, key: JSON.stringify([operation, path]),
    conflict: resolved!.conflicts.some(item => item.operation_id === operation && item.parameter_path === path),
  })));
  for (const leaf of available) if (!leaf.conflict && chosen.includes(leaf.key)) (selection[leaf.operation] ??= []).push(leaf.path);
  const request: PeopleTransferRequest | undefined = source && Object.keys(selection).length ? {
    source_ref: source.face_ref, selection, target_policy: 'confirmed_person_only',
  } : undefined;
  const proof: PeopleTransferProof | undefined = view && links.length === 1 ? {
    ...view.binding, state_revision: view.revision, association_revision: view.association_revision, person_id: links[0].person_id,
  } : undefined;
  const selected = [...new Set(targets)].filter(identity => identity !== view?.binding.document_id);
  const ready = enabled && owner.enabled && !owner.state.pending && !owner.state.uncertain && !!source?.enabled
    && source.analysis_status === 'verified' && matches && !!proof && !!request;
  const flow = useBatchWorkflow({docs: selected, moduleScope: Object.keys(selection), conflictPolicy: policy,
    sourceDocumentId: view?.binding.document_id ?? '', referencePath: currentPath, enabled: ready,
    label: '仅向用户已确认的同一人物同步明确勾选的参数', peopleTransfer: request, peopleProof: proof}, onComplete);
  const busy = ['preflighting', 'committing', 'uncertain'].includes(flow.ui.phase);
  useEffect(() => {
    const result = flow.ui.result;
    if (!result?.success) return;
    if (flow.ui.operation === 'commit' && result.batch_id) {
      const evidence = flow.ui.plan?.targets.find(target => target.people_transfer)?.people_transfer;
      if (evidence) { setLast({id: result.batch_id, epoch: evidence.source_document.epoch}); setUndone(false); }
    } else if (flow.ui.operation === 'undo') setUndone(true);
    else if (flow.ui.operation === 'redo') setUndone(false);
  }, [flow.ui.result, flow.ui.operation, flow.ui.plan]);
  const setLeaves = (leaves: string[]) => setChoice({key, leaves: [...new Set(leaves)]});
  if (!view && flow.ui.phase === 'closed') return null;
  return <section className="peopleTransfer" aria-label="跨照片已确认人物同步">
    <details><summary>跨照片同步已确认人物</summary>
      <p>先在人物面板明确确认跨照片关联，再在胶片栏选目标照片。这里只同步勾选参数，不复制恢复蒙版、关键点或关联。</p>
      {links.length !== 1 && <p role="status">所选人脸必须有且只有一个已确认的匿名人物关联。</p>}
      <fieldset disabled={!enabled || !owner.enabled || owner.state.pending || owner.state.uncertain || busy}>
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
        <label>冲突处理<select value={policy} onChange={event => setPolicy(event.currentTarget.value as typeof policy)}>
          <option value="recheck">任一目标受阻则不提交整组</option><option value="skip_and_report">跳过受阻目标并逐张报告</option>
        </select></label>
      </fieldset>
      <button type="button" disabled={!ready || !selected.length || busy} onClick={flow.start}>预检所选 {selected.length} 张照片的人物参数</button>
      <button type="button" disabled={!last || busy || !enabled || !owner.enabled || owner.state.pending || owner.state.uncertain || last.epoch !== view?.binding.document_epoch}
        onClick={() => last && (undone ? flow.redo(last.id) : flow.undo(last.id))}>{undone ? '重做本次人物同步' : '撤销本次人物同步'}</button>
      <p>未明确确认的照片会报告受阻，不会根据外貌猜测人物。预检会展示实际目标人脸和冻结参数。</p>
    </details>
    <BatchReview state={flow.ui} onClose={flow.close} onCommit={flow.commit} onReview={flow.start}
      onQuery={flow.query} onAcknowledge={flow.acknowledgeInspection}/>
  </section>;
}
