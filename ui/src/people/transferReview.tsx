import {operationLabel} from './model';
import type {PeopleTransferReview} from './transferProof';
export * from './transferProof';

export function PeopleTransferEvidence({value}: {value: PeopleTransferReview}) {
  const explicit = value.target_policy === 'explicit_face_map';
  return <details open={explicit}><summary>{explicit ? '仅本次指定配对' : '已确认关联'}：{value.target_refs.length} 张人脸 · {value.parameters.length} 项参数</summary>
    <p>只替换明确勾选的参数；不复制蒙版、关键点、局部素材或人物关联。</p>
    {value.target_policy === 'explicit_face_map' ? <>
      <p>确认仅授权本次同步，不建立持久人物关联，也不代表系统识别为同一人。</p>
      <p>目标独立人物版本 {value.target_owner.state_revision} · 关联版本 {value.target_owner.association_revision}。</p>
    </> : <p>匿名人物：{value.confirmed_person_id}。关联版本：{value.target_association_revision}。</p>}
    <ul>{value.target_refs.map(ref => <li key={ref.face_instance_id}>目标人脸 {ref.face_instance_id} · 分析版本 {ref.analysis_revision}</li>)}</ul>
    <ul>{value.parameters.map(leaf => <li key={`${leaf.operation_id}:${leaf.parameter_path}`}>
      {operationLabel(leaf.operation_id)} · {leaf.parameter_path}：{String(leaf.value)}</li>)}</ul>
  </details>;
}
