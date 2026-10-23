import {operationLabel} from './model';
import type {AssociationReview} from './associationProof';
import type {BatchTarget} from '../batch/batchWorkflow';
export function AssociationEvidence({value,source,sourceOutcome}:{value:AssociationReview;source?:BatchTarget;sourceOutcome?:BatchTarget}){
  return <section aria-label="持久人物关联审核">
    <h3>{value.operation==='create'?'新建持久人物关联':value.operation==='patch'?'更新共同继承参数':'解除完整人物关联'}</h3>
    <p>匿名关联 {value.association_id} · 内容版本 {value.generation}</p>
    <p>源成员 {source?.document_id} 同样会修改。{sourceOutcome?.outcome==='applied'?'源成员已提交。':''}</p>
    <p>{value.operation==='unlink'?'移除下列共同继承参数；每张人脸的显式编辑、支持素材及历史保留。':'下列参数在人物层继承；已有更高优先级的人脸显式参数不会被覆盖，所以部分画面可能保持原样。'}</p>
    <ul>{value.members.map(m=><li key={m.document_id}>文档 {m.document_id} · 人脸 {m.ref.face_instance_id} · 分析版本 {m.ref.analysis_revision}</li>)}</ul>
    <ul>{value.intent.map(leaf=><li key={JSON.stringify([leaf.op,leaf.path])}>{operationLabel(leaf.op)} · {leaf.path}：{String(leaf.value)}</li>)}</ul>
    <p>成员不可用或源图切换会暂停共享编辑；重新分析前需先解除关联，不能自动补齐或按相同像素复用身份。撤销沿用受保护的整组历史。</p>
  </section>;
}
