import {type MaskTransferOptions,type MaskTransferType,type MaskTransferEvidence,type TransferGroupChoice} from './transferModel';
export * from './transferModel';
const labels:Record<MaskTransferType,string>={subject:'主体类别（整图人像类别）',background:'人像背景',custom:'自定义（不含画笔/AI 提示选区）'};
export function MaskTransferControls({value,onChange,disabled=false,saveOnly=false,groups=[]}:{value:MaskTransferOptions;onChange:(v:MaskTransferOptions)=>void;disabled?:boolean;saveOnly?:boolean;groups?:TransferGroupChoice[]}){
  return <fieldset disabled={disabled} className="maskTransferOptions"><legend>局部调色组范围</legend>
    {!saveOnly&&<label>目标局部组<select value={value.mode} onChange={e=>onChange({...value,mode:e.target.value as MaskTransferOptions['mode']})}><option value="append">追加：保留现有组并在其后调色</option><option value="replace">替换：仅替换所选类型的完整组</option></select></label>}
    {(Object.keys(labels) as MaskTransferType[]).map(type=><label key={type}><input type="checkbox" checked={value.types.includes(type)} onChange={e=>onChange({...value,types:(Object.keys(labels) as MaskTransferType[]).filter(t=>t===type?e.target.checked:value.types.includes(t))})}/>{labels[type]}</label>)}
    {!value.types.length&&<p role="alert">至少选择一种完整类型。</p>}
    <fieldset><legend>源图完整组（默认全部，不自动跳过不便迁移的组）</legend>
      {groups.map(group=><label key={group.id}><input type="checkbox" checked={value.groups===null||value.groups.includes(group.id)} onChange={e=>{
        const selected=value.groups??groups.map(g=>g.id);onChange({...value,groups:e.target.checked?[...selected.filter(id=>id!==group.id),group.id]:selected.filter(id=>id!==group.id)});
      }}/><span>{group.name} · {group.types.map(t=>labels[t as MaskTransferType]??t).join(' + ')}{group.reason&&<small>不可迁移：{group.reason}。请显式取消本组，或先修改源图；不会自动忽略。</small>}{!group.types.every(t=>value.types.includes(t as MaskTransferType))&&<small>类型未完整选中；混合组须完整选择类型或显式取消本组。</small>}</span></label>)}
      {!groups.length&&<small>当前没有可选择的源组。</small>}
      {value.groups?.some(id=>!groups.some(g=>g.id===id))&&<p role="alert">已选组不在当前源图，请重新选择。</p>}
      <button type="button" onClick={()=>onChange({...value,groups:null})}>重新选择全部源组</button>
    </fieldset>
    {!saveOnly&&<label><input type="checkbox" checked={value.rebase} onChange={e=>onChange({...value,rebase:e.target.checked})}/>允许线性/径向按目标原图的相对位置与轴向重映射，不做人物或物体对齐</label>}
    <small>颜色/亮度范围在每张目标的原始像素重新计算；语义类别用匹配模型逐图重算，覆盖整图所有该类区域，不匹配同一个人，也不是通用主体分割。</small>
    <small>画笔不参与批量或预设；AI 提示选区绑定原照片，必须在目标重新选。含这些对象的组整组拒绝，不删掉减去/交集对象。跨多个类型的组必须完整选择。</small>
  </fieldset>;
}
export function MaskTransferEvidenceView({value}:{value:MaskTransferEvidence}){
  return <div className="maskTransferEvidence">
    <p>{value.policy.mode==='append'?'追加':'所选类型替换'}：新增 {value.added.length} 组；移除 {value.removed.length} 组；源图未选类型 {value.excluded.length} 组。</p>
    {!!value.removed.length&&<p>将移除：{value.removed.join('、')}</p>}
    {!!value.excluded.length&&<p>未传递：{value.excluded.join('、')}</p>}
    {value.legacy_preserved&&<p>目标旧对象调色槽及其 LUT 联动保持原样，追加组在旧槽之后执行。</p>}
    {value.legacy_removed&&<p>所选类型命中目标旧对象调色槽，将清零该槽并解除 LUT 强度联动，LUT 数据与强度不变。可撤销。</p>}
    {value.preview_jpeg?<img width="180" alt="目标原始源图与重算组合范围，青色仅为覆盖诊断，不是最终调色" src={`data:image/jpeg;base64,${value.preview_jpeg}`}/>:<small>本目标已重算范围；批量仅前 12 张提供缩略图。</small>}
    <small>源图覆盖诊断（8 位代理），不是最终形变/调色预览。最终应用后请查看照片，必要时撤销。全尺寸：{value.full_dimensions.join(' × ')}。</small>
    {value.groups.some(g=>g.covered_proxy_pixels===0)&&<p>注意：有启用组在代理上覆盖为零，不会扩大到全图；请核对类型与目标内容。</p>}
  </div>;
}
