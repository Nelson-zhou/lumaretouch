import {operationLabel} from './model';
import type {PeopleTransferReview} from './transferProof';
export * from './transferProof';

export function PeopleTransferEvidence({value}: {value: PeopleTransferReview}) {
  const explicit = value.target_policy === 'explicit_face_map';
  return <details open={explicit || !!value.skin_colour_coverage || !!value.skin_finish_coverage}><summary>{explicit ? '仅本次指定配对' : '已确认关联'}：{value.target_refs.length} 张人脸 · {value.parameters.length} 项参数</summary>
    <p>只替换明确勾选的参数；不复制蒙版、关键点、局部素材或人物关联。</p>
    {value.target_policy === 'explicit_face_map' ? <>
      <p>确认仅授权本次同步，不建立持久人物关联，也不代表系统识别为同一人。</p>
      <p>目标独立人物版本 {value.target_owner.state_revision} · 关联版本 {value.target_owner.association_revision}。</p>
    </> : <p>匿名人物：{value.confirmed_person_id}。关联版本：{value.target_association_revision}。</p>}
    <ul>{value.target_refs.map(ref => <li key={ref.face_instance_id}>目标人脸 {ref.face_instance_id} · 分析版本 {ref.analysis_revision}</li>)}</ul>
    {value.skin_colour_coverage && <section aria-label="目标肤色覆盖范围">
      <p>肤色只同步色温与色调数值。身体审核不随源图或预设复制；下面范围来自各目标自己的已有审核，不是新建身体关联。</p>
      <ul>{value.skin_colour_coverage.targets.map(row => <li key={row.face_ref.face_instance_id}>
        人脸 {row.face_ref.face_instance_id}：{row.scope === 'face-and-reviewed-body'
          ? '面部 + 该目标已审核的身体皮肤区域（不是自动全身分割）'
          : row.scope === 'face-only' ? '仅面部；该目标没有附加身体审核，不会继承源图的身体范围'
          : '色温与色调均为零，不产生肤色效果；不据此声明身体审核有效'}
      </li>)}</ul>
    </section>}
    {value.skin_finish_coverage && <section aria-label="目标美白红润覆盖范围">
      <p>美白红润只同步独立的美白与红润数值，不改色温或色调。身体审核不随源图或预设复制；旧肤色色温/色调审核不能授权美白红润。</p>
      <ul>{value.skin_finish_coverage.targets.map(row => <li key={row.face_ref.face_instance_id}>
        人脸 {row.face_ref.face_instance_id}：{row.scope === 'face-and-reviewed-body'
          ? '面部 + 该目标为美白红润单独审核的身体皮肤区域（不是自动全身分割）'
          : row.scope === 'face-only' ? '仅面部；该目标没有美白红润身体审核，不会继承源图或色温/色调的身体范围'
          : '美白与红润均为零，不产生美白红润效果；不据此声明身体审核有效'}
      </li>)}</ul>
    </section>}
    <ul>{value.parameters.map(leaf => <li key={`${leaf.operation_id}:${leaf.parameter_path}`}>
      {operationLabel(leaf.operation_id)} · {leaf.parameter_path}：{String(leaf.value)}</li>)}</ul>
  </details>;
}
