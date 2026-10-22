import {LOCAL_GRADE_OP,MaskTransferControls,MaskTransferEvidenceView,transferGroupsFromParams} from '../localMasks/transfer';
import type {PresetWorkflowBinding} from './usePresetWorkflow';
import {moduleLabel,presetLabel,unavailableScope} from './presetModel';
import './presets.css';
export function PresetPanel({workflow:w}:{workflow:PresetWorkflowBinding}){
  const list=w.catalog?.list??[],modules=w.catalog?.modules??[],chosen=w.form.scope;
  const unavailable=unavailableScope(chosen,modules),selectedOps=Object.keys(w.selected?.modules??{});
  const faceBlocked=!w.face.ok&&modules.some(m=>selectedOps.includes(m.operation_id)&&m.single_face);
  const rows=[...modules,...chosen.filter(op=>!modules.some(m=>m.operation_id===op))
    .map(operation_id=>({operation_id,params:[],transferable:false,single_face:false,reason:'当前引擎不再提供这个模块'}))];
  const verbs={list:'刷新列表',preflight:'预检局部预设',apply:'应用预设',save:'保存预设',import:'导入预设',delete:'删除预设'};
  const oldDocument=!!w.ui.submitted?.options.documentId&&w.ui.submitted.options.documentId!==w.context.documentId;
  const nameLength=Array.from(w.form.name.trim()).length;
  return <section className="modulePresets" aria-label="模块预设">
    <h4>模块预设</h4>
    <p>保存曝光、曲线、HSL 等模块的参数组合。下方的 LUT 风格单独保留，不会被混为一类。</p>
    {!w.context.enabled&&<p role="status">需要支持预设回执的配套引擎，当前操作不可用。</p>}
    <label>选择预设<select aria-label="选择模块预设" value={w.form.selectedId} disabled={w.busy} onChange={e=>w.select(e.target.value)}>
      <option value="">请选择</option>
      {w.form.selectedId&&!w.selected&&<option value={w.form.selectedId}>所选预设暂不在当前列表，请刷新</option>}
      {[true,false].map(builtin=><optgroup key={String(builtin)} label={builtin?'内置预设':'自定义预设'}>
        {list.filter(p=>p.builtin===builtin).map(p=><option key={p.id} value={p.id}>{presetLabel(p,list)}</option>)}
      </optgroup>)}
    </select></label>
    {w.selected&&<div className="presetDetail"><strong>{w.selected.name}</strong><small>ID：{w.selected.id}</small>
      <p>仅作用于：{selectedOps.map(moduleLabel).join('、')}</p>{w.selected.note&&<p>{w.selected.note}</p>}
      {faceBlocked&&<p>{w.face.why||'部分模块应用时需要可用单脸'}</p>}
      {unavailableScope(selectedOps,modules).length>0&&<p>包含当前不可用模块，不能应用。</p>}
    </div>}
    <div className="presetButtons">
      <button disabled={!w.context.enabled||!w.context.editable||w.busy||!w.selected||faceBlocked||unavailableScope(selectedOps,modules).length>0} onClick={()=>void w.apply()}>{selectedOps.includes(LOCAL_GRADE_OP)?'预检所选局部预设':'应用所选'}</button>
      <button disabled={!w.context.enabled||w.busy} onClick={()=>void w.refresh()}>刷新列表</button>
      <button disabled={!w.context.enabled||w.busy||!w.selected||w.selected.builtin} onClick={()=>void w.remove()}>删除所选</button>
    </div>
    {selectedOps.includes(LOCAL_GRADE_OP)&&<MaskTransferControls groups={transferGroupsFromParams(w.selected?.modules[LOCAL_GRADE_OP])} value={w.localMaskTransfer} onChange={w.setLocalMaskTransfer} disabled={w.busy}/>}
    {w.review?.local_mask_transfer&&<div className="presetDetail"><strong>冻结的目标预检，尚未应用</strong><MaskTransferEvidenceView value={w.review.local_mask_transfer}/><button disabled={w.busy||!w.context.editable} onClick={()=>void w.confirmLocal()}>确认本次局部预设并应用</button></div>}
    <fieldset><legend>保存当前照片的模块参数</legend>
      <label>预设名称<input aria-label="预设名称" value={w.form.name} maxLength={160} placeholder="例如：室外婚纱暖调" onChange={e=>w.setName(e.target.value)}/><small>{nameLength}/80 字符</small></label>
      {nameLength>80&&<p role="alert">名称过长，请缩短到 80 个字符以内。</p>}
      <div className="presetButtons"><button disabled={w.busy} onClick={()=>w.setScope(modules.filter(m=>m.transferable).map(m=>m.operation_id))}>全选可用模块</button>
        <button disabled={w.busy} onClick={()=>w.setScope([])}>清空选择</button></div>
      <div className="presetScopes">{rows.map(m=><label key={m.operation_id} title={m.reason??''}>
        <input type="checkbox" checked={chosen.includes(m.operation_id)} disabled={w.busy||(!m.transferable&&!chosen.includes(m.operation_id))}
          onChange={e=>w.setScope(e.target.checked?[...chosen,m.operation_id]:chosen.filter(op=>op!==m.operation_id))}/>
        <span>{moduleLabel(m.operation_id)}{m.single_face&&<small>应用时须单脸</small>}{!m.transferable&&<small>{m.reason||'暂不可用'}</small>}</span>
      </label>)}</div>
      {chosen.includes(LOCAL_GRADE_OP)&&<MaskTransferControls saveOnly groups={w.context.sourceGroups} value={w.saveMaskTransfer} onChange={w.setSaveMaskTransfer} disabled={w.busy}/>}
      {unavailable.length>0&&<p role="alert">请取消已不可用模块：{unavailable.map(moduleLabel).join('、')}</p>}
      {!chosen.length&&<p>请明确选择要保存的模块，不会自动保存全部调整。</p>}
      {!w.context.editable&&<p>保存和应用需要可编辑照片；导入、删除和浏览不需要打开照片。</p>}
      <button disabled={!w.context.enabled||!w.context.editable||w.busy||!w.form.name.trim()||nameLength>80||!chosen.length||!!unavailable.length} onClick={()=>void w.save()}>保存为新预设</button>
    </fieldset>
    <div className="presetButtons"><button disabled={!w.context.enabled||w.busy} onClick={()=>void w.importFile()}>导入 JSON</button>
      <button disabled={!w.context.enabled||w.busy} onClick={()=>void w.importFile(true)}>导入为新副本</button></div>
    <small>默认不覆盖同 ID 文件。遇到冲突可导入为新副本；内置预设不能删除。</small>
    <div role="status" aria-live="polite">
      {w.ui.phase==='working'&&<p>正在{w.ui.action?verbs[w.ui.action]:'处理'}，尚未确认完成…</p>}
      {w.ui.phase==='done'&&<p>{w.ui.action?verbs[w.ui.action]:'操作'}已确认成功{w.ui.result?.id?`：${w.ui.result.name??w.ui.result.preset?.name??w.ui.result.id}`:''}。</p>}
      {w.ui.message&&<p>{w.ui.message}</p>}{w.note&&<p>{w.note}</p>}
      {oldDocument&&<p>这笔操作属于之前的照片，不会用旧回执覆盖当前照片的控制项。</p>}
      {w.ui.result?.requires_reload&&<p>应用失败且未能恢复图像，请重新打开照片。</p>}
    </div>
    {w.ui.phase==='uncertain'&&<div className="presetUncertain"><p>结果尚未确认。不会自动重试，也不能据此认定没有保存或应用。</p>
      <button onClick={()=>void w.query()}>查询同一笔结果</button><button onClick={()=>void w.inspect()}>请求当前状态供核对</button>
      <button onClick={w.acknowledgeInspection}>我已核对，结束本次等待</button>
    </div>}
    {!!w.catalog?.errors.length&&<details><summary>预设目录问题（{w.catalog.errors.length}）</summary>
      {w.catalog.errors.map((e,i)=><p key={`${e.file}-${i}`}>{e.file}：{e.error}</p>)}</details>}
  </section>;
}
