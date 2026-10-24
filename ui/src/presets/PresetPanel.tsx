import {EYE_BAG_PRESET_OP,neutralEyeBagPreset} from '../eyeBagPreserve/presetModel';
import {EyeBagPresetReview} from '../eyeBagPreserve/EyeBagPresetReview';
import {COLLARBONE_PRESET_OP} from '../collarbone/presetModel';
import {CollarbonePresetReview} from '../collarbone/CollarbonePresetReview';
import {SHADOW_TRANSFER_OP} from '../originalShadow/transferModel';
import {TORSO_TRANSFER_OP} from '../torsoLength/transferModel';
import {TorsoTransferReview} from '../torsoLength/TorsoTransferReview';
import {WAIST_TRANSFER_OP} from '../waistLength/transferModel';
import {HEAD_TRANSFER_OP} from '../headSize/transferModel';
import {WaistTransferReview} from '../waistLength/WaistTransferReview';
import {HeadTransferReview} from '../headSize/HeadTransferReview';
import {CROP_OP} from '../cropTransfer/model';
import {CropTransferReview} from '../cropTransfer/CropTransferReview';
import {SPILL_TRANSFER_OP} from '../spillRemoval/transferModel';
import {SpillTransferReview} from '../spillRemoval/SpillTransferReview';
import {ShadowTransferReview} from '../originalShadow/ShadowTransferReview';
import {PresetOrganisationPanel} from '../presetOrganisation/PresetOrganisationPanel';
import {ReferenceColorReview} from '../referenceColor/ReferenceColorReview';
import {AutomaticTransferReview} from '../optics/AutomaticTransferReview';
import {OPTICS_AUTO_OP} from '../optics/transferReviewModel';
import {LOCAL_GRADE_OP,MaskTransferControls,MaskTransferEvidenceView,transferGroupsFromParams} from '../localMasks/transfer';
import type {PresetWorkflowBinding} from './usePresetWorkflow';
import {moduleLabel,presetLabel,unavailableScope} from './presetModel';
import './presets.css';
import {XmpCompatibilityDialog,XmpSummaryView} from '../xmpImport/XmpCompatibility';
import {XmpPixelReview} from '../xmpImport/XmpPixelReview';
import {validXmpSummary} from '../xmpImport/model';
export function PresetPanel({workflow:w}:{workflow:PresetWorkflowBinding}){
  const list=w.catalog?.list??[],modules=w.catalog?.modules??[],chosen=w.form.scope;
  const unavailable=unavailableScope(chosen,modules),selectedOps=Object.keys(w.selected?.modules??{});
  const eyeBagActive=selectedOps.includes(EYE_BAG_PRESET_OP)&&!neutralEyeBagPreset(w.selected?.modules[EYE_BAG_PRESET_OP]);
  const xmpUnsupported=w.selected?.xmp_import!==undefined&&w.catalog?.xmp_import_protocol!==1;
  const faceBlocked=!w.face.ok&&modules.some(m=>selectedOps.includes(m.operation_id)&&m.single_face);
  const rows=[...modules,...chosen.filter(op=>!modules.some(m=>m.operation_id===op))
    .map(operation_id=>({operation_id,params:[],transferable:false,single_face:false,dedicated_transport:undefined,reason:'当前引擎不再提供这个模块'}))];
  const verbs={list:'刷新列表',preflight:'预检目标预设',apply:'应用预设',save:'保存预设',import:'导入预设',delete:'移入预设回收站',xmp_inspect:'检查 XMP 兼容性'};
  const oldDocument=!!w.ui.submitted?.options.documentId&&w.ui.submitted.options.documentId!==w.context.documentId;
  const nameLength=Array.from(w.form.name.trim()).length;
  return <section className="modulePresets" aria-label="模块预设">
    <h4>模块预设</h4>
    <PresetOrganisationPanel enabled={w.context.enabled&&(w.catalog as {organisation_protocol?:number}|null)?.organisation_protocol===1}
      externalBusy={w.busy} sourceVersion={w.catalog} onChanged={w.refresh} onSelect={w.select}/>
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
      {w.selected.xmp_import!==undefined&&(validXmpSummary(w.selected.xmp_import,selectedOps)?<XmpSummaryView value={w.selected.xmp_import}/>:<p role="alert">XMP 来源摘要不完整，禁止应用。</p>)}
      {xmpUnsupported&&<p role="alert">当前引擎未声明 XMP 逐图审核协议，该预设不能应用。</p>}
      {faceBlocked&&<p>{w.face.why||'部分模块应用时需要可用单脸'}</p>}
      {unavailableScope(selectedOps,modules).length>0&&<p>包含当前不可用模块，不能应用。</p>}
    </div>}
    {eyeBagActive&&<label>目标旧版去眼袋策略<select value={w.eyeBagReplaceLegacy===null?'':String(w.eyeBagReplaceLegacy)} disabled={w.busy} onChange={e=>w.setEyeBagReplaceLegacy(e.target.value===''?null:e.target.value==='true')}>
      <option value="">请明确选择</option><option value="false">不替换旧版，冲突时拒绝</option><option value="true">明确替换旧版去眼袋，其他眼部效果保留</option></select>
      <small>目标须先在去眼袋 v2 面板独立绘制并审核可见逐眼保护。供图的保护、恢复笔迹或分析不复制；未审核眼保持不处理。</small></label>}
    <div className="presetButtons">
      <button disabled={!w.context.enabled||!w.context.editable||w.busy||!w.selected||faceBlocked||xmpUnsupported||unavailableScope(selectedOps,modules).length>0} onClick={()=>void w.apply()}>{eyeBagActive||w.selected?.xmp_import||selectedOps.some(op=>[LOCAL_GRADE_OP,OPTICS_AUTO_OP,"lnx.reference_color.v1",CROP_OP,SPILL_TRANSFER_OP,SHADOW_TRANSFER_OP,TORSO_TRANSFER_OP,WAIST_TRANSFER_OP,HEAD_TRANSFER_OP,COLLARBONE_PRESET_OP].includes(op))?'预检所选预设':'应用所选'}</button>
      <button disabled={!w.context.enabled||w.busy} onClick={()=>void w.refresh()}>刷新列表</button>
      <button disabled={!w.context.enabled||w.busy||!w.selected||w.selected.builtin} onClick={()=>void w.remove()}>移入回收站</button>
    </div>
    {selectedOps.includes(LOCAL_GRADE_OP)&&<MaskTransferControls groups={transferGroupsFromParams(w.selected?.modules[LOCAL_GRADE_OP])} value={w.localMaskTransfer} onChange={w.setLocalMaskTransfer} disabled={w.busy}/>}
    {w.review&&<div className="presetDetail"><strong>冻结的目标预检，尚未应用</strong>{w.review.local_mask_transfer&&<MaskTransferEvidenceView value={w.review.local_mask_transfer}/>} {w.review.reference_color&&<ReferenceColorReview value={w.review.reference_color}/>} {w.review.optical_transfer&&<AutomaticTransferReview report={w.review.optical_transfer}/>}{w.review.crop_transfer&&<CropTransferReview key={w.cropKey} value={w.review.crop_transfer} reviewKey={w.cropKey} onReady={(key,ready)=>w.setCropImage({key,ready})}/>}
      {w.review.xmp_transfer&&<XmpPixelReview key={w.xmpKey} value={w.review.xmp_transfer} reviewKey={w.xmpKey} onReady={(key,ready)=>w.setXmpImage({key,ready})}/>}
      {w.review.spill_transfer&&<SpillTransferReview value={w.review.spill_transfer} reviewKey={w.spillKey} disabled={w.busy} onReady={(key,ready)=>w.setSpillImage({key,ready})}/>}
      {w.review.shadow_transfer&&<ShadowTransferReview value={w.review.shadow_transfer} reviewKey={w.shadowKey} disabled={w.busy} onReady={(key,ready)=>w.setShadowImage({key,ready})}/>}
      {w.review.torso_transfer&&<TorsoTransferReview value={w.review.torso_transfer} reviewKey={w.torsoKey} disabled={w.busy} onReady={(key,ready)=>w.setTorsoImage({key,ready})}/>}
      {w.review.waist_transfer&&<WaistTransferReview value={w.review.waist_transfer} reviewKey={w.waistKey} disabled={w.busy} onReady={(key,ready)=>w.setWaistImage({key,ready})}/>}
      {w.review.head_transfer&&<HeadTransferReview value={w.review.head_transfer} reviewKey={w.headKey} disabled={w.busy} onReady={(key,ready)=>w.setHeadImage({key,ready})}/>}
      {w.review.collarbone_preset&&w.review.id&&w.review.preflight_token&&<CollarbonePresetReview value={w.review.collarbone_preset} id={w.review.id} token={w.review.preflight_token} reviewKey={w.collarboneKey} disabled={w.busy} onReady={(key,ready)=>w.setCollarboneImage({key,ready})}/>}
      {w.review.eye_bag_preset&&w.review.id&&w.review.preflight_token&&<EyeBagPresetReview value={w.review.eye_bag_preset} id={w.review.id} token={w.review.preflight_token} reviewKey={w.eyeBagKey} disabled={w.busy} onReady={(key,ready)=>w.setEyeBagImage({key,ready})}/>}
      {!w.eyeBagReady&&<p role="status">请逐张读取并确认全部受影响成员的逐眼保护、明确替换策略及完整混合前后效果。</p>}
      {!w.collarboneReady&&<p role="status">请读取并确认本照片完整混合预设的真实前后效果。</p>}
      {!w.spillReady&&<p role="status">请查看并勾选确认本目标的祛反光前后效果。</p>}
      {!w.shadowReady&&<p role="status">请查看并勾选确认本目标的原图阴影前后效果。</p>}
      {!w.torsoReady&&<p role="status">请查看并勾选确认本目标身体及本人面部的上身长度前后效果。</p>}
      {!w.waistReady&&<p role="status">请查看并勾选确认本目标身体及本人面部的腰长前后效果。</p>}
      {!w.headReady&&<p role="status">请查看并勾选确认本目标身体及本人面部的小头前后效果。</p>}
      <button disabled={w.busy||!w.context.editable||!w.eyeBagReady||!w.cropReady||!w.xmpReady||!w.spillReady||!w.shadowReady||!w.torsoReady||!w.waistReady||!w.headReady||!w.collarboneReady} onClick={()=>void w.confirmLocal()}>{w.review.eye_bag_preset?.version===2?'确认全部成员并应用此混合预设':'确认本次目标预设并应用'}</button>
      <button disabled={w.busy} onClick={w.dismissReview}>关闭本次审核</button></div>}
    <fieldset><legend>保存当前照片的模块参数</legend>
      <label>预设名称<input aria-label="预设名称" value={w.form.name} maxLength={160} placeholder="例如：室外婚纱暖调" onChange={e=>w.setName(e.target.value)}/><small>{nameLength}/80 字符</small></label>
      {nameLength>80&&<p role="alert">名称过长，请缩短到 80 个字符以内。</p>}
      <div className="presetButtons"><button disabled={w.busy} onClick={()=>w.setScope(modules.filter(m=>m.transferable&&!m.dedicated_transport&&![TORSO_TRANSFER_OP,WAIST_TRANSFER_OP,HEAD_TRANSFER_OP].includes(m.operation_id)).map(m=>m.operation_id))}>全选可组合模块</button>
        <button disabled={w.busy} onClick={()=>w.setScope([])}>清空选择</button></div>
      <div className="presetScopes">{rows.map(m=><label key={m.operation_id} title={m.reason??''}>
        <input type="checkbox" checked={chosen.includes(m.operation_id)} disabled={w.busy||((!m.transferable||!!m.dedicated_transport)&&!chosen.includes(m.operation_id))}
          onChange={e=>w.setScope(e.target.checked?[...chosen,m.operation_id]:chosen.filter(op=>op!==m.operation_id))}/>
        <span>{moduleLabel(m.operation_id)}{m.single_face&&<small>应用时须单脸</small>}{(!m.transferable||!!m.dedicated_transport)&&<small>{m.reason||'暂不可用'}</small>}</span>
      </label>)}</div>
      {chosen.includes(LOCAL_GRADE_OP)&&<MaskTransferControls saveOnly groups={w.context.sourceGroups} value={w.saveMaskTransfer} onChange={w.setSaveMaskTransfer} disabled={w.busy}/>}
      {unavailable.length>0&&<p role="alert">请取消已不可用模块：{unavailable.map(moduleLabel).join('、')}</p>}
      {chosen.includes(TORSO_TRANSFER_OP)&&<p role={chosen.length===1?'status':'alert'}>上身长度须单独保存与审核。{chosen.length>1?'请取消其他模块。':'不保存身体归属、关键点、支持范围或审核。'}</p>}
      {chosen.includes(WAIST_TRANSFER_OP)&&<p role={chosen.length===1?'status':'alert'}>腰长须单独保存与审核。{chosen.length>1?'请取消其他模块。':'仅保存版本与长度标量，不保存身体、腰部标记、本人面部归属、支持或审核。'}</p>}
      {chosen.includes(HEAD_TRANSFER_OP)&&<p role={chosen.length===1?'status':'alert'}>小头须单独保存与审核。{chosen.length>1?'请取消其他模块。':'仅保存版本与缩小标量，不保存身体、头部几何、本人面部归属、支持或审核。'}</p>}
      {!chosen.length&&<p>请明确选择要保存的模块，不会自动保存全部调整。</p>}
      {!w.context.editable&&<p>保存和应用需要可编辑照片；导入、删除和浏览不需要打开照片。</p>}
      <button disabled={!w.context.enabled||!w.context.editable||w.busy||!w.form.name.trim()||nameLength>80||!chosen.length||!!unavailable.length||(chosen.some(op=>[TORSO_TRANSFER_OP,WAIST_TRANSFER_OP,HEAD_TRANSFER_OP].includes(op))&&chosen.length!==1)} onClick={()=>void w.save()}>保存为新预设</button>
    </fieldset>
    <div className="presetButtons"><button disabled={!w.context.enabled||w.busy} onClick={()=>void w.importFile()}>导入 JSON</button>
      <button disabled={!w.context.enabled||w.busy} onClick={()=>void w.importFile(true)}>导入 JSON 为新副本</button>
      <button data-feature-id="LNX-REF-WF-158978-398fbf9da9" disabled={!w.context.enabled||w.catalog?.xmp_import_protocol!==1||w.busy} onClick={()=>void w.importFile(false,true)}>导入 XMP（兼容检查）</button>
      <button disabled={!w.context.enabled||w.catalog?.xmp_import_protocol!==1||w.busy} onClick={()=>void w.importFile(true,true)}>XMP 导入为新副本</button></div>
    {w.xmpImport&&<XmpCompatibilityDialog key={w.xmpImport.report.report_sha256} report={w.xmpImport.report}
      busy={w.ui.phase==='working'||w.ui.phase==='uncertain'} onCancel={w.cancelXmpImport} onImport={ack=>void w.confirmXmpImport(ack)}/>}
    <small>默认不覆盖同 ID 文件。遇到冲突可导入为新副本；内置预设不能删除。</small>
    <div role="status" aria-live="polite">
      {w.ui.phase==='working'&&<p>正在{w.ui.action?verbs[w.ui.action]:'处理'}，尚未确认完成…</p>}
      {w.ui.phase==='done'&&<p>{w.ui.action?verbs[w.ui.action]:'操作'}已确认成功{w.ui.result?.id?`：${w.ui.result.name??w.ui.result.preset?.name??w.ui.result.id}`:''}。</p>}
      {w.ui.result?.success&&w.ui.result.eye_bag_preset_alias_review&&<p>已确认全部 {w.ui.result.eye_bag_preset_alias_review.member_count} 张成员，批次 {w.ui.result.batch_id}。只有原当前照片接收所选色彩、裁剪等配方，其他成员保留自己的当前编辑。请在去眼袋 v2 面板的“混合预设共享来源全成员历史”统一撤销或重做；不使用当前照片本地撤销。</p>}
      {w.ui.message&&<p>{w.ui.message}</p>}{w.note&&<p>{w.note}</p>}
      {oldDocument&&<p>这笔操作属于之前的照片，不会用旧回执覆盖当前照片的控制项。</p>}
      {w.ui.result?.requires_reload&&<p>应用失败且未能恢复图像，请重新打开照片。</p>}
    </div>
    {w.ui.phase==='uncertain'&&<div className="presetUncertain"><p>{w.ui.action==='preflight'||w.ui.action==='xmp_inspect'?'只读检查仍未确认完成，尚未导入或应用；可以查询同一笔任务，不会重复提交。':'结果尚未确认。不会自动重试，也不能据此认定没有保存或应用。'}</p>
      {w.ui.result?.batch_id&&<p>待核对批次 ID：{w.ui.result.batch_id}。此标识不是请求成功终态，也不会单独授权撤销或重做。</p>}
      {w.ui.submitted?.options.eyeBagPresetAck!==undefined&&<p>本次去眼袋预设应用只可查询原请求，冻结令牌和逐成员图像确认不会释放后重发。原生已记录的未知回执可能保持不变，重复查询不保证解锁。若仍未知，请先核对已保存的项目，再手动重新打开项目并检查全部成员；不要重复应用。普通换照片、关面板或刷新状态不能解除旧工作区等待。</p>}
      {w.ui.submitted?.options.headReviewAck!==undefined&&<p>本次小头应用只可查询原请求，冻结令牌及逐图确认不会被释放后重新提交。原生回执读取的既有限制仍可能阻止结果确认；当前状态刷新不等于这笔操作的终态证明。</p>}
      <button onClick={()=>void w.query()}>查询同一笔结果</button><button onClick={()=>void w.inspect()}>请求当前状态供核对</button>
      {w.ui.submitted?.options.waistReviewAck===undefined&&w.ui.submitted?.options.headReviewAck===undefined&&w.ui.submitted?.options.collarbonePresetAck===undefined&&w.ui.submitted?.options.eyeBagPresetAck===undefined&&<button onClick={w.acknowledgeInspection}>我已核对，结束本次等待</button>}
    </div>}
    {!!w.catalog?.errors.length&&<details><summary>预设目录问题（{w.catalog.errors.length}）</summary>
      {w.catalog.errors.map((e,i)=><p key={`${e.file}-${i}`}>{e.file}：{e.error}</p>)}</details>}
  </section>;
}
