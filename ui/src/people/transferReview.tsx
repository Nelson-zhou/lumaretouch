import {operationLabel} from './model';
import type {PeopleTransferReview} from './transferProof';
export * from './transferProof';

export function PeopleTransferEvidence({value}: {value: PeopleTransferReview}) {
  const explicit = value.target_policy === 'explicit_face_map';
  return <details open={explicit || !!value.skin_colour_coverage || !!value.skin_finish_coverage || !!value.body_skin_evenness_coverage || !!value.body_face_match_coverage || !!value.collarbone_coverage}><summary>{explicit ? '仅本次指定配对' : '已确认关联'}：{value.target_refs.length} 张人脸 · {value.parameters.length} 项参数</summary>
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
    {value.body_skin_evenness_coverage && <section aria-label="目标身体色度均匀覆盖范围">
      <p>身体色度均匀只同步强度，不复制源图身体蒙版、参考色或人物关联。非零目标必须各自拥有本功能独立有效审核；色温、美白红润或脸部审核不能代替，也不能回退为仅面部效果。</p>
      <ul>{value.body_skin_evenness_coverage.targets.map(row => <li key={row.face_ref.face_instance_id}>
        人物 {row.face_ref.face_instance_id}：{row.scope === 'reviewed-body-only'
          ? '仅此目标为身体色度均匀独立审核的身体皮肤，使用其自身来源参考；不调整脸部，不是脸身匹配'
          : '身体强度为零，不产生本项效果；不据此声明已有有效身体审核'}
      </li>)}</ul>
      <p>预检中被拒绝的目标不会因其他人物已有审核而变为可用；请保留并处理原始拒绝原因。</p>
    </section>}
    {value.body_face_match_coverage && <section aria-label="目标身体向本人脸部色度匹配覆盖范围">
      <p>只同步匹配强度，不复制身体蒙版、参考色、脸部观察或人物关联。非零目标必须各自拥有本功能独立审核的身体皮肤和本人的实测来源脸部；身体色度均匀、色温或美白红润审核不能代替。</p>
      <ul>{value.body_face_match_coverage.targets.map(row => <li key={row.face_ref.face_instance_id}>
        人物 {row.face_ref.face_instance_id}：{row.scope === 'reviewed-body-own-face'
          ? `仅该目标独立审核的身体皮肤；参考是目标本人脸部 ${row.own_face_reference!.face_ref.face_instance_id}（分析版本 ${row.own_face_reference!.face_ref.analysis_revision}），来自此目标有效来源在肖像效果之前的冻结阶段，含已验证修复（若有）`
          : '匹配强度为零，不产生本项效果；不据此声明已有身体审核或可用脸部参考'}
      </li>)}</ul>
      <p>保留此处理阶段实际输入的亮度，不匹配亮度，不复制 RGB，不追随后续修饰后的脸。每个参考身份来自该目标自己的观察，不是源预设的参考；元数据也不等于照片质量验收。</p>
      <p>预检中被拒绝的目标不会因其他人物已有审核而变为可用；请保留并处理原始拒绝原因。</p>
    </section>}
    {value.collarbone_coverage && <section aria-label="目标锁骨现有明暗增强覆盖范围">
      <p>只同步独立强度；不复制身体蒙版、锁骨曲线、类别确认或人物关联。每个非零目标必须使用自己的身体审核与手工可见锁骨曲线，在目标来源上重新计算已有明暗支持；其他身体功能不能代替。</p>
      <ul>{value.collarbone_coverage.targets.map(row => <li key={row.face_ref.face_instance_id}>
        人物 {row.face_ref.face_instance_id}：{row.scope === 'reviewed-clavicle-only'
          ? `仅此目标独立审核的可见锁骨；用户确认类别：${row.clavicle_category === 'female' ? '女' : '长辈女'}；手工图像侧：${row.clavicle_sides.map(side => side === 'left' ? '图像左侧' : '图像右侧').join('、')}`
          : '本项强度为零，不产生锁骨增强；不据此声明类别、身体范围或可见锁骨审核有效'}
      </li>)}</ul>
      <p>这份披露是目标审核元数据；上方真实前后对比须逐图查看并确认，不代表照片质量验收。不能从一个目标的审核推及其他人物；不自动分类、检测锁骨、补全另一侧或进行 AI 3D 重建。</p>
      <p>预检拒绝须逐目标处理，不能通过复制源图曲线或借用其他人物审核绕过。</p>
    </section>}
    <ul>{value.parameters.map(leaf => <li key={`${leaf.operation_id}:${leaf.parameter_path}`}>
      {operationLabel(leaf.operation_id)} · {leaf.parameter_path}：{String(leaf.value)}</li>)}</ul>
  </details>;
}
