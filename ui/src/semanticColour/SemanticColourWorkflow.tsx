import {useCallback,useEffect,useRef,useState} from 'react';
import './workflow.css';
import {open,save} from '@tauri-apps/plugin-dialog';
import {message,PARAMETER_LABELS} from './model';
import {CLASS_NAMES,type ExportReceipt,type ImportReceipt,type Intent,type Plan,type Progress,type TargetPreview,type WorkflowProps} from './workflowModel';

function IntentDetails({intent}:{intent:Intent}){
 return <details><summary>携带的类别、模式和手动差量</summary><p>{intent.mode==='harmonious'?'和谐':'极致'}；总/明暗/颜色程度：{intent.strengths.join(' / ')}；{intent.enabled?'启用':'保持关闭'}。</p>
  {intent.groups.map(group=><details key={group.id}><summary>{CLASS_NAMES[group.id]??group.id}：{group.enabled?'启用':'关闭'}；{group.offsets.filter(v=>v!==0).length} 项手动差量</summary>
   <ul>{group.offsets.map((v,i)=>v!==0?<li key={i}>{PARAMETER_LABELS[i]}：{v>0?'+':''}{v.toPrecision(5)}</li>:null)}</ul></details>)}
  <p>每张目标重新拟合后才加这些差量。不携带来源的拟合增益、基线或目标蒙版；缺少请求类别或差量越界将明确拒绝该目标。</p></details>;
}

export function SemanticColourWorkflow({port,context,documentKey,targets,disabled,mutationBlocked,portableReason,onBusyChange,onChanged}:WorkflowProps){
 const [cancellable,setCancellable]=useState(false),[uncertainSave,setUncertainSave]=useState<string|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[progress,setProgress]=useState<Progress|null>(null);
 const [plan,setPlan]=useState<Plan|null>(null),[preview,setPreview]=useState<TargetPreview|null>(null),[selected,setSelected]=useState(''),[reviewed,setReviewed]=useState(false);
 const [policy,setPolicy]=useState<'recheck'|'skip_and_report'>('recheck'),[includeReference,setIncludeReference]=useState(false),[overwrite,setOverwrite]=useState(false);
 const [imported,setImported]=useState<ImportReceipt|null>(null),[prepared,setPrepared]=useState<ExportReceipt|null>(null),[lastBatch,setLastBatch]=useState<{id:string;undone:boolean}|null>(null);
 const alive=useRef(true),generation=useRef(0),session=useRef<string|null>(null),previewTicket=useRef(0),importRef=useRef<string|null>(null),exportRef=useRef<string|null>(null);
 const active=useRef<string|null>(null),uncertainSaveRef=useRef<string|null>(null),previousContext=useRef('');
 const busyCallback=useRef(onBusyChange);busyCallback.current=onBusyChange;
 const begin=(kind='operation')=>{if(active.current)return null;active.current=kind;setCancellable(false);setBusy(true);busyCallback.current(true);setError('');setNotice('');return ++generation.current;};
 const finish=(ticket:number)=>{if(ticket===generation.current){active.current=null;if(alive.current){setBusy(false);setCancellable(false);busyCallback.current(false);}}};
 const valid=(ticket:number)=>alive.current&&ticket===generation.current;
 const clearReview=()=>{previewTicket.current++;setPlan(null);setPreview(null);setSelected('');setReviewed(false);setProgress(null);};
 const cancel=useCallback(async()=>{
  if(active.current&&active.current!=='prepare')return;
  const id=session.current;const ticket=++generation.current;active.current='cancel';previewTicket.current++;
  setBusy(true);busyCallback.current(true);setCancellable(false);setPlan(null);setPreview(null);setSelected('');setReviewed(false);setProgress(null);setError('');
  try{if(id)await port.request('workflow_cancel',{session_id:id});if(alive.current&&ticket===generation.current){session.current=null;setNotice('待处理审核已关闭。已提交的配方不受影响。');}}
  catch(e){if(alive.current&&ticket===generation.current)setError('取消结果待核对，不能认定工作已停止：'+message(e));}
  finally{if(ticket===generation.current){active.current=null;if(alive.current){setBusy(false);busyCallback.current(false);}}}
 },[port]);
 useEffect(()=>{alive.current=true;const recovery=port.pendingExport?.();if(recovery){exportRef.current=recovery.receipt.export_id;setPrepared(recovery.receipt);uncertainSaveRef.current=recovery.path;setUncertainSave(recovery.path);}
  return()=>{alive.current=false;generation.current++;busyCallback.current(false);
  if(session.current)void port.request('workflow_cancel',{session_id:session.current}).catch(()=>{});
  if(importRef.current)void port.request('preset_forget',{import_id:importRef.current}).catch(()=>{});
  // Staged exports are intentionally not released on navigation/unmount: an
  // in-flight or uncertain file write still needs exact immutable readback.
 };},[port]);
 useEffect(()=>{
  const key=`${documentKey}:${context?.revision??''}`;
  if(previousContext.current&&previousContext.current!==key){
   if(!active.current||active.current==='prepare')void cancel();
   else{previewTicket.current++;setPlan(null);setPreview(null);setSelected('');setReviewed(false);}
  }
  previousContext.current=key;
 },[documentKey,context?.revision,cancel]);
 useEffect(()=>{if(mutationBlocked){previewTicket.current++;setPlan(null);setPreview(null);setReviewed(false);setLastBatch(null);}},[mutationBlocked]);
 useEffect(()=>port.subscribeProgress?.((id,value)=>{if(alive.current&&session.current===id)setProgress(value);}),[port]);
 const prepare=async(kind:'batch'|'preset')=>{
  if(!context||disabled||mutationBlocked||(kind==='batch'&&(!!portableReason||targets.length<1||targets.length>128))||(kind==='preset'&&!imported))return;const ticket=begin('prepare');if(ticket===null)return;setCancellable(true);clearReview();const id=crypto.randomUUID().replaceAll('-','');session.current=id;
  try{
   const result=await port.request(kind==='batch'?'batch_prepare':'preset_prepare',kind==='batch'?{context,session_id:id,targets,policy}:{context,session_id:id,import_id:imported?.import_id}) as Plan;
   if(valid(ticket)){setPlan(result);setNotice('逐目标拟合已冻结。请查看前后图、覆盖和诊断，再明确应用。');}
  }catch(e){if(valid(ticket))setError(message(e));}finally{finish(ticket);}
 };
 const showTarget=async(id:string)=>{if(!plan||active.current||disabled)return;const ticket=++previewTicket.current;setSelected(id);setPreview(null);setError('');
  try{const result=await port.request('batch_preview',{preflight_token:plan.preflight_token,document_id:id}) as {preview:TargetPreview};if(alive.current&&ticket===previewTicket.current)setPreview(result.preview);}
  catch(e){if(alive.current&&ticket===previewTicket.current)setError(message(e));}
 };
 const apply=async()=>{if(!context||!plan||!reviewed||disabled||mutationBlocked)return;const ticket=begin('apply');if(ticket===null)return;
  try{const result=await port.request('batch_apply',{context,preflight_token:plan.preflight_token,reviewed:true}) as {success:boolean;outcome_unknown?:boolean;error?:string;batch_id?:string};
   if(!result.success||result.outcome_unknown)throw new Error(result.error??'提交结果需核对，不能重复应用');
   if(valid(ticket)){if(result.batch_id)setLastBatch({id:result.batch_id,undone:false});clearReview();setNotice('已应用逐目标新拟合；每张照片保留自己的精确编辑参数和蒙版。');onChanged();}
  }catch(e){if(valid(ticket)){clearReview();setError('请先核对当前照片和批次历史，不要重发旧应用：'+message(e));onChanged();}}finally{finish(ticket);}
 };
 const restore=async()=>{if(!context||!lastBatch||disabled||mutationBlocked)return;const ticket=begin('restore');if(ticket===null)return;
  try{await port.request('batch_restore',{context,batch_id:lastBatch.id,redo:lastBatch.undone});if(valid(ticket)){setLastBatch({...lastBatch,undone:!lastBatch.undone});onChanged();}}
  catch(e){if(valid(ticket)){setLastBatch(null);setError('恢复结果请检查实际批次历史，不能重发：'+message(e));onChanged();}}finally{finish(ticket);}
 };
 const prepareExport=async()=>{if(!context||!includeReference||disabled||mutationBlocked||portableReason||prepared||uncertainSaveRef.current)return;const ticket=begin('export_prepare');if(ticket===null)return;
  try{const result=await port.request('preset_export_prepare',{context,include_reference:true}) as ExportReceipt;
   if(!valid(ticket)){void port.request('preset_export_release',{export_id:result.export_id}).catch(()=>{});return;}
   if(exportRef.current)await port.request('preset_export_release',{export_id:exportRef.current});exportRef.current=result.export_id;setPrepared(result);
  }catch(e){if(valid(ticket))setError(message(e));}finally{finish(ticket);}
 };
 const writeExport=async()=>{if(!prepared||uncertainSaveRef.current||disabled||mutationBlocked)return;const ticket=begin('export_write');if(ticket===null)return;
  try{const path=await save({filters:[{name:'AI 语义追色便携预设',extensions:['lrtcolour']}],defaultPath:'追色预设.lrtcolour'});if(!path||!valid(ticket))return;
   uncertainSaveRef.current=path;setUncertainSave(path);await port.request('preset_export_write',{export_id:prepared.export_id,path,overwrite});if(!valid(ticket))return;
   void port.request('preset_export_release',{export_id:prepared.export_id}).catch(()=>{});exportRef.current=null;uncertainSaveRef.current=null;setUncertainSave(null);
   if(valid(ticket)){setPrepared(null);setNotice('便携预设已保存，文件含完整样片照片，请谨慎分享。');}
  }catch(e){if(valid(ticket))setError('保存结果请核对所选路径：'+message(e));}finally{finish(ticket);}
 };
 const inspectExport=async()=>{if(!prepared||!uncertainSave)return;const ticket=begin('export_inspect');if(ticket===null)return;
  try{const result=await port.request('preset_export_status',{export_id:prepared.export_id,path:uncertainSave,expected:{file_bytes:prepared.file_bytes,file_sha256:prepared.file_sha256}}) as {state:string};
   if(valid(ticket)){if(result.state==='matching'){await port.request('preset_export_release',{export_id:prepared.export_id});exportRef.current=null;setPrepared(null);setNotice('已按完整文件 SHA-256 核对，保存文件与准备内容一致。');}
    else setNotice(result.state==='missing'?'当前所选文件不存在。尚未重发保存，可重新选择位置。':'当前所选文件内容与预设不同。尚未覆盖或重发保存，请检查目标位置。');uncertainSaveRef.current=null;setUncertainSave(null);}
  }catch(e){if(valid(ticket))setError('文件核对未完成：'+message(e));}finally{finish(ticket);}
 };
 const recoverExport=async()=>{const ticket=begin('export_recover');if(ticket===null)return;
  try{await port.request('state',{});const recovery=port.pendingExport?.();if(valid(ticket)){
   if(recovery){exportRef.current=recovery.receipt.export_id;setPrepared(recovery.receipt);uncertainSaveRef.current=recovery.path;setUncertainSave(recovery.path);setNotice('已找回原始文件回执。若曾开始保存，请先核对目标文件，不会重发保存。');}
   else setNotice('当前没有保留的待保存文件回执。未据此认定任何旧文件写入成功或失败。');
  }}catch(e){if(valid(ticket))setError('回执核对尚未完成：'+message(e));}finally{finish(ticket);}
 };
 const importPreset=async()=>{if(disabled)return;const ticket=begin('import');if(ticket===null)return;
  try{const path=await open({multiple:false,filters:[{name:'AI 语义追色便携预设',extensions:['lrtcolour']}]});if(typeof path!=='string'||!valid(ticket))return;
   const result=await port.request('preset_import',{path}) as ImportReceipt;
   if(!valid(ticket)){void port.request('preset_forget',{import_id:result.import_id}).catch(()=>{});return;}
   if(importRef.current)await port.request('preset_forget',{import_id:importRef.current});importRef.current=result.import_id;setImported(result);setNotice(result.notice);
  }catch(e){if(valid(ticket))setError(message(e));}finally{finish(ticket);}
 };
 const releaseResources=async()=>{if(disabled||uncertainSaveRef.current)return;const ticket=begin('release');if(ticket===null)return;
  try{await port.request('workflow_release',{});if(valid(ticket)){clearReview();session.current=null;setImported(null);setPrepared(null);uncertainSaveRef.current=null;setUncertainSave(null);importRef.current=null;exportRef.current=null;setNotice('待处理预设和审核资源已释放；已应用追色及保存文件保持不变。');}}
  catch(e){if(valid(ticket))setError(message(e));}finally{finish(ticket);}
 };
 const row=plan?.targets.find(v=>v.document_id===selected),lock=busy||disabled;
 return <details className="semantic-workflow" data-control-id="PC-32452-C-e92914a50b"><summary>批量重新拟合 / 便携预设</summary>
  <p>仅全图模式可携带。局部双图选区、画笔和渐变等来源标记不能迁移。参考只复用分析；所有目标都重新渲染、分割、拟合并冻结审核。</p>
  {disabled&&<p className="semantic-warning">请先关闭单张照片的待处理冻结/审核，再使用批量或预设。</p>}
  {mutationBlocked&&<p role="alert" className="semantic-warning">写入结果待核对。请先使用上方“核对当前结果”，审核实际状态后再建立新方案。</p>}
  {targets.length>128&&<p role="alert">本次选择超过 128 张，请明确重新选择较小的一组；没有自动丢弃任何目标。</p>}
  {portableReason&&<p className="semantic-warning">当前配方不能导出/同步：{portableReason}</p>}
  <label>遇到目标冲突 <select disabled={lock} value={policy} onChange={e=>setPolicy(e.target.value as 'recheck'|'skip_and_report')}><option value="recheck">整组暂停，重新审核</option><option value="skip_and_report">明确跳过并报告</option></select></label>
  <button disabled={lock||mutationBlocked||!context||!!portableReason||!targets.length||targets.length>128} onClick={()=>void prepare('batch')}>为底片条所选 {targets.length} 张重新拟合</button>
  <button disabled={busy?!cancellable:!plan&&!session.current} onClick={()=>void cancel()}>取消 / 释放未应用审核</button>
  {progress&&<p role="status">{progress.stage==='reference_analysis'?'分析拥有的完整样片':`逐目标重新拟合 ${progress.position??0} / ${progress.targets}`} {progress.path??''}</p>}
  {busy&&<p role="status">{cancellable?'逐目标准备中，可请求停止；单个工作进程有 240 秒预算，总等待按明确目标数计算。':'操作进行中。写入开始后请等待回执；结果未知时必须核对，不能把取消当作撤销。'}</p>}
  {plan&&<section><p>已冻结 {plan.ok} 张；明确阻止 {plan.blocked} 张。源码接入不是运行或画质验收。</p><IntentDetails intent={plan.applies}/>
   <select aria-label="查看逐目标拟合" value={selected} disabled={lock} onChange={e=>void showTarget(e.target.value)}><option value="">选择目标检查前后图</option>{plan.targets.map(t=><option key={t.document_id} value={t.document_id} disabled={!!t.blocked}>{t.path}{t.blocked?'（已阻止）':''}</option>)}</select>
   {plan.targets.filter(t=>t.blocked).map(t=><p key={t.document_id} className="semantic-warning">{t.path}：{t.blocked}</p>)}
   {preview&&<div className="semantic-preview"><figure><img src={preview.before} alt="目标拟合前"/><figcaption>前</figcaption></figure><figure><img src={preview.after} alt="目标独立拟合与手动差量后"/><figcaption>后</figcaption></figure><p>{preview.notice}</p></div>}
   {row?.semantic_colour&&<details open><summary>该目标覆盖和初始拟合诊断</summary><ul>{row.semantic_colour.coverage.target.map(c=><li key={c.class}>{CLASS_NAMES[c.class]??c.class}：{c.usable_pixels} 可用分析点，权重覆盖 {(c.weighted_coverage*100).toFixed(2)}%</li>)}</ul>
    <p>诊断属于手动差量之前的初始拟合，不是修改后残差，也不是摄影质量概率。</p><ul>{row.semantic_colour.diagnostics.map((d,i)=><li key={i}>{CLASS_NAMES[['global','background','hair','body_skin','face_skin','clothes','others'][i]]}：{d[9]===1?`留出残差 ${d[0].toFixed(4)} → ${d[1].toFixed(4)}，采样越界 ${(d[4]*100).toFixed(2)}%`:'共同支持不足，未拟合该类别'}</li>)}</ul>{row.semantic_colour.warnings.map(w=><p key={w}>{w}</p>)}</details>}
   <label><input type="checkbox" checked={reviewed} disabled={lock||mutationBlocked} onChange={e=>setReviewed(e.target.checked)}/>已检查逐目标结果、阻止项和警告，同意仅应用合格的冻结结果</label>
   <button disabled={lock||mutationBlocked||!reviewed||plan.ok===0||(plan.policy==='recheck'&&plan.blocked>0)} onClick={()=>void apply()}>应用已审核结果</button></section>}
  {lastBatch&&<button disabled={lock||mutationBlocked||!context} onClick={()=>void restore()}>{lastBatch.undone?'重做':'撤销'}此追色批次（保留其它后续编辑）</button>}
  <hr/><label><input type="checkbox" checked={includeReference} disabled={lock} onChange={e=>setIncludeReference(e.target.checked)}/>我同意导出的预设包含这张完整样片照片，分享文件也会分享照片</label>
  <button disabled={lock||mutationBlocked||!!prepared||!!uncertainSave||!includeReference||!!portableReason||!context} onClick={()=>void prepareExport()}>准备便携预设</button>
  {prepared&&<section><p>将包含完整样片 {(prepared.reference_bytes/1048576).toFixed(2)} MiB；文件 {(prepared.file_bytes/1048576).toFixed(2)} MiB。</p><small>样片 SHA-256：{prepared.reference_sha256}</small>
   <label><input type="checkbox" checked={overwrite} disabled={lock} onChange={e=>setOverwrite(e.target.checked)}/>允许替换我随后选择的同名文件</label><button disabled={lock||mutationBlocked||!!uncertainSave} onClick={()=>void writeExport()}>选择位置并保存</button>{uncertainSave&&<button disabled={busy} onClick={()=>void inspectExport()}>先核对未确认的保存文件</button>}</section>}
  <button disabled={lock} onClick={()=>void importPreset()}>导入拥有样片的便携预设</button>
  {imported&&<section><p>已导入 {(imported.reference_bytes/1048576).toFixed(2)} MiB 完整样片，尚未修改当前照片。</p><IntentDetails intent={imported.intent}/><button disabled={lock||mutationBlocked||!context} onClick={()=>void prepare('preset')}>为当前照片重新拟合并审核</button></section>}
  <button disabled={lock||!!uncertainSave} onClick={()=>void releaseResources()}>释放待处理预设与审核资源</button>
  <button disabled={busy} onClick={()=>void recoverExport()}>找回待保存文件及回执</button>
  {notice&&<p role="status">{notice}</p>}{error&&<p className="semantic-warning" role="alert">{error}</p>}
 </details>;
}
