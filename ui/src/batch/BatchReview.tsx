import {portraitCohortTargets,portraitCohortReviewKey,portraitCohortImagesReady,portraitCohortAck,type PortraitCohortAck} from '../portraitCohort/model';
import {PortraitCohortReview} from '../portraitCohort/PortraitCohortReview';
import {collarbonePlanTargets} from '../collarbone/cohortModel';
import {COLLARBONE_TRANSFER_OP,collarboneReviewKey,collarboneImagesReady,collarboneAck,type CollarboneAck} from '../collarbone/transferModel';
import {CollarboneTransferReview} from '../collarbone/CollarboneTransferReview';
import {validFaceStyleRecipe, FACE_STYLE_LABELS} from '../faceStyle/model';
import {faceStyleBatchReviewKey, faceStyleBatchImagesReady, faceStyleBatchAck, type FaceStyleBatchAck} from '../faceStyle/batchModel';
import {FaceStyleBatchReview} from '../faceStyle/FaceStyleBatchReview';
import {CROP_OP,cropReviewKey,cropImagesReady} from '../cropTransfer/model';
import {CropTransferReview} from '../cropTransfer/CropTransferReview';
import {SPILL_TRANSFER_OP,spillTransferReviewKey,spillTransferImagesReady,spillTransferAck,type SpillTransferAck} from '../spillRemoval/transferModel';
import {SpillTransferReview} from '../spillRemoval/SpillTransferReview';
import {SHADOW_TRANSFER_OP,shadowTransferReviewKey,shadowTransferImagesReady,shadowTransferAck,type ShadowTransferAck} from '../originalShadow/transferModel';
import {ShadowTransferReview} from '../originalShadow/ShadowTransferReview';
import {TORSO_TRANSFER_OP,torsoTransferReviewKey,torsoTransferImagesReady,torsoTransferAck,type TorsoTransferAck} from '../torsoLength/transferModel';
import {TorsoTransferReview} from '../torsoLength/TorsoTransferReview';
import {WAIST_TRANSFER_OP,waistTransferReviewKey,waistTransferImagesReady,waistTransferAck,type WaistTransferAck} from '../waistLength/transferModel';
import {HEAD_TRANSFER_OP,headTransferReviewKey,headTransferImagesReady,headTransferAck,type HeadTransferAck} from '../headSize/transferModel';
import {WaistTransferReview} from '../waistLength/WaistTransferReview';
import {HeadTransferReview} from '../headSize/HeadTransferReview';
import {AssociationEvidence} from '../people/AssociationEvidence';
import {PeopleTransferEvidence} from '../people/transferReview';
import {ReferenceColorReview} from '../referenceColor/ReferenceColorReview';
import {AutomaticTransferReview} from '../optics/AutomaticTransferReview';
import {MaskTransferEvidenceView} from '../localMasks/transfer';
import {useEffect,useRef,useState,type ReactNode} from 'react';
import type {BatchUi,BatchTarget} from './batchWorkflow';
import './batchReview.css';
const file=(path:string)=>path.split('/').pop()||path;
function reason(text:string|null|undefined){
  if(!text)return '可同步';
  const known:Record<string,string>={
    'target is in the project trash':'照片已移入项目回收站',
    'target was removed or replaced':'照片已移除或被替换',
    'target was edited after preflight; preflight again':'预检后已编辑，已保护，需重新预检',
    'target parameters changed outside the reviewed snapshot':'参数与预检快照不同，已保护',
  };return known[text]??text;
}
export function BatchReview({state,onCommit,onReview,onQuery,onAcknowledge,onClose,peoplePreview,commitBlockedReason}:{state:BatchUi;onCommit:(spillReviewAck?:SpillTransferAck[],shadowReviewAck?:ShadowTransferAck[],torsoReviewAck?:TorsoTransferAck[],waistReviewAck?:WaistTransferAck[],headReviewAck?:HeadTransferAck[],collarboneReviewAck?:CollarboneAck[],faceStyleReviewAck?:FaceStyleBatchAck[],portraitCohortReviewAck?:PortraitCohortAck[])=>unknown;
  onReview:()=>unknown;onQuery:()=>unknown;onAcknowledge:()=>void;onClose:()=>void;peoplePreview?:ReactNode;commitBlockedReason?:string}){
  const [cropImages,setCropImages]=useState<Record<string,boolean>>({});
  const [spillImages,setSpillImages]=useState<Record<string,boolean>>({});
  const [shadowImages,setShadowImages]=useState<Record<string,boolean>>({});
  const [torsoImages,setTorsoImages]=useState<Record<string,boolean>>({});
  const [waistImages,setWaistImages]=useState<Record<string,boolean>>({});
  const [collarboneImages,setCollarboneImages]=useState<Record<string,boolean>>({});
  const [headImages,setHeadImages]=useState<Record<string,boolean>>({});
  const [faceStyleImages,setFaceStyleImages]=useState<Record<string,boolean>>({});
  const [portraitImages,setPortraitImages]=useState<Record<string,boolean>>({});
  const dialog=useRef<HTMLElement>(null),close=useRef(onClose);close.current=onClose;
  useEffect(()=>setCropImages({}),[state.plan?.preflight_token]);
  const open=state.phase!=='closed'&&!state.hidden,busy=state.phase==='committing';
  useEffect(()=>{setSpillImages({});setShadowImages({});setTorsoImages({});setWaistImages({});setHeadImages({});setCollarboneImages({});setFaceStyleImages({});setPortraitImages({});},[state.plan?.preflight_token,state.plan?.request_id,open]);
  useEffect(()=>{
    if(!open)return;
    const previous=document.activeElement as HTMLElement|null;dialog.current?.focus();
    const key=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();close.current();}
      if(event.key==='Tab'){
        const items=Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),summary,[tabindex="0"]')??[]);
        if(!items.length){event.preventDefault();return;}
        const first=items[0],last=items[items.length-1];
        if(event.shiftKey&&(document.activeElement===first||document.activeElement===dialog.current)){event.preventDefault();last.focus();}
        else if(!event.shiftKey&&(document.activeElement===last||document.activeElement===dialog.current)){event.preventDefault();first.focus();}
      }
    };
    window.addEventListener('keydown',key,true);
    return()=>{window.removeEventListener('keydown',key,true);previous?.focus();};
  },[open]);
  if(!open)return state.phase==='uncertain'?<button className="batchPending tb" onClick={onReview}>查看未确认的批量任务</button>:null;
  const plan=state.plan,result=state.result;
  const targets:BatchTarget[]=result?.target_outcomes??plan?.targets??[];
  const cropTargets=plan?.module_scope.includes(CROP_OP)?plan.targets.filter(t=>!t.blocked):[];
  const cropReady=cropImagesReady(plan?.preflight_token??'',cropTargets.map(t=>t.crop_transfer),cropImages);
  const spillTargets=plan?.module_scope.includes(SPILL_TRANSFER_OP)?plan.targets.filter(t=>!t.blocked):[];
  const spillReady=spillTransferImagesReady(plan?.preflight_token??'',spillTargets.map(t=>t.spill_transfer),spillImages);
  const shadowTargets=plan?.module_scope.includes(SHADOW_TRANSFER_OP)?plan.targets.filter(t=>!t.blocked):[];
  const shadowReady=shadowTransferImagesReady(plan?.preflight_token??'',shadowTargets.map(t=>t.shadow_transfer),shadowImages);
  const torsoTargets=plan?.module_scope.includes(TORSO_TRANSFER_OP)?plan.targets.filter(t=>!t.blocked):[];
  const torsoReady=torsoTransferImagesReady(plan?.preflight_token??'',torsoTargets.map(t=>t.torso_transfer),torsoImages);
  const waistTargets=plan?.module_scope.includes(WAIST_TRANSFER_OP)?plan.targets.filter(t=>!t.blocked):[];
  const waistToken=`${plan?.preflight_token??''}:${plan?.request_id??''}`;
  const waistReady=waistTransferImagesReady(waistToken,waistTargets.map(t=>t.waist_transfer),waistImages);
  const headTargets=plan?.module_scope.includes(HEAD_TRANSFER_OP)?plan.targets.filter(t=>!t.blocked):[];
  const headToken=`${plan?.preflight_token??''}:${plan?.request_id??''}`;
  const headReady=headTransferImagesReady(headToken,headTargets.map(t=>t.head_transfer),headImages);
  const collarboneSelected=!!plan&&(plan.collarbone_cohort===true||plan.module_scope.includes(COLLARBONE_TRANSFER_OP));
  const collarboneTargets=plan?collarbonePlanTargets(plan):[];
  const collarboneToken=`${plan?.preflight_token??''}:${plan?.request_id??''}`;
  const collarboneReady=collarboneImagesReady(collarboneToken,collarboneTargets.map(t=>t.visual),collarboneImages);
  const candidateFaceStyle=plan?.applies.face_style;
  const namedRecipe=validFaceStyleRecipe(candidateFaceStyle)?candidateFaceStyle:undefined;
  const faceStyleRecipe=plan?.applies.target_policy==='explicit_face_map'?namedRecipe:undefined;
  const portraitSelected=plan?.portrait_cohort===true,portraitTargets=plan?portraitCohortTargets(plan):[];
  const portraitToken=`${plan?.preflight_token??''}:${plan?.request_id??''}`;
  const portraitReady=!portraitSelected||portraitCohortImagesReady(portraitToken,portraitTargets.map(target=>target.visual),portraitImages);
  const faceStyleTargets=faceStyleRecipe?plan!.targets.filter(target=>!target.blocked):[];
  const faceStyleToken=`${plan?.preflight_token??''}:${plan?.request_id??''}`;
  const faceStyleReady=faceStyleBatchImagesReady(faceStyleToken,faceStyleTargets.map(target=>target.people_transfer?.face_style_visual),faceStyleImages);
  const blockedReason=commitBlockedReason||(!portraitReady?'请读取并逐张查看、勾选源成员及所有目标的真实前后效果。':!cropReady?'请等待每张目标的实际裁剪预览通过显示校验，再确认同步。':!spillReady?'请逐张查看并勾选所有可同步目标的祛反光前后效果。':!shadowReady?'请逐张查看并勾选所有可同步目标的原图阴影前后效果。':!torsoReady?'请逐张查看并勾选所有可同步目标身体及本人面部的上身长度前后效果。':!waistReady?'请逐张查看并勾选所有可同步目标身体及本人面部的腰长前后效果。':!headReady?'请逐张查看并勾选所有可同步目标完整头发、头部及本人面部的小头前后效果。':!collarboneReady?'请逐张查看并勾选所有可同步目标的锁骨真实前后效果。':!faceStyleReady?'请逐张查看并勾选所有可应用目标的新版脸型真实前后效果，包括 0 程度。':undefined);
  const title=state.operation==='redo'?'重做批量同步':state.operation==='undo'?'撤销批量同步':'批量同步预检';
  return <div className="batchReviewBackdrop">
    <section ref={dialog} tabIndex={-1} className="batchReview" role="dialog" aria-modal="true" aria-labelledby="batchReviewTitle">
      <header><h2 id="batchReviewTitle">{title}</h2><button className="tb" disabled={busy} onClick={onClose}>{state.phase==='uncertain'?'暂时收起':'关闭'}</button></header>
      <div aria-live="polite">
        {state.phase==='preflighting'&&<p>正在冻结源图配方并检查目标照片，尚未修改任何照片。</p>}
        {busy&&<p>正在等待引擎的实际结果，请勿重复提交。入队不代表已经完成。</p>}
        {state.message&&<p className="batchWarning">{state.message}</p>}
        {(state.phase==='uncertain'||result?.outcome_unknown)&&<p className="batchWarning">{state.operation==='preflight'?'只读预检尚未确认完成，尚未修改照片；收起后保留同一任务，请继续查询，不会重复解算。':state.queryOnly||plan?.module_scope.some(op=>[WAIST_TRANSFER_OP,HEAD_TRANSFER_OP].includes(op))?'部分改动可能已经生效，只能查询原请求。收起仍保留本次请求身份与冻结审核，不会释放后重复提交；回执读取失败不表示没有写入。':'部分改动可能已经生效。关闭此窗口不会撤销已发送的任务，收起后仍保留本次任务；请再次查询，或检查照片后明确结束跟踪，勿盲目重复同步。'}</p>}
        {result?.success&&<p>{['undo','redo'].includes(state.operation)?`已恢复 ${result.restored?.length??0} 张，冲突 ${result.conflicts?.length??0} 张。`:faceStyleRecipe&&result.batch_id===null?'可应用目标已是本次配方，没有产生新改动或新的撤销批次。':
          `已同步 ${result.target_outcomes?.filter(t=>t.outcome==='applied').length??0} 张，跳过 ${result.target_outcomes?.filter(t=>t.outcome==='skipped').length??0} 张。`}</p>}
      </div>
      {plan&&<>
        <p title={plan.source_snapshot.path}>{faceStyleRecipe?'上下文照片（不提供配方数值）':'源图'}：{file(plan.source_snapshot.path)} · 预检版本 {plan.source_snapshot.revision}</p>
        <p>{state.scopeLabel} · {plan.module_scope.length} 个模块</p>
        {portraitSelected&&namedRecipe&&<p>本次选择 {FACE_STYLE_LABELS[namedRecipe.style]} · v{namedRecipe.version} · 共同程度 {Number((namedRecipe.amount*100).toFixed(6))}。配方由本地引擎生成，源成员不捐赠数值；共同层替换完整 30 项，人脸显式参数仍优先。关联只保存规范参数意图，不保存风格名称；相同共同意图会在写入前明确拒绝，而不是添加空历史。</p>}
        {faceStyleRecipe&&<p>明确选择的新版脸型：{FACE_STYLE_LABELS[faceStyleRecipe.style]} · v{faceStyleRecipe.version} · 所有目标统一程度 {Number((faceStyleRecipe.amount*100).toFixed(6))}。只使用本地固定配方，不比较或复制上下文人脸的外貌与参数；不建立人物关联。每次替换全部 30 个管理参数，0 也是中性替换，不恢复以前的调整。</p>}
        {plan.module_scope.includes(TORSO_TRANSFER_OP)&&<p>仅传递上身长度标量。每张图必须有唯一启用身体和独立审核的支持及本人面部归属；多个启用身体、归属模糊或缺少审核会拒绝，不复制支持范围，也不自动关联人物。</p>}
        {plan.module_scope.includes(WAIST_TRANSFER_OP)&&<p>仅传递腰长标量。每张图必须有唯一启用身体、当前四个腰部标记和独立审核的腰长支持及本人面部归属。缺少或过期则拒绝，不从源图或上身长度复制审核。</p>}
        {plan.module_scope.includes(HEAD_TRANSFER_OP)&&<p>仅传递小头标量。每张图必须有唯一启用身体、当前完整头发/头部框、缩小中心、外围过渡框和独立审核的小头支持及本人面部归属。缺少或过期则拒绝，不从源图或上身长度复制审核。</p>}
        <p>{faceStyleRecipe?'只向本次手动指定的目标人脸应用所选新版配方。上下文照片、目标、人物状态或关联改变后必须重新预检。':plan.persistent_association?'持久关联操作包括源成员，所有独立成员同时审核与提交；只继承共同标量参数，不共享蒙版、关键点或局部素材。':plan.people_transfer?(plan.applies.target_policy==='explicit_face_map'?'只向本次手动指定的人脸同步勾选参数；不建立持久人物关联。源图、目标、人物状态或关联改变后必须重新预检。':'只向明确确认的同一人物同步勾选参数；源图、目标或关联改变后必须重新预检。'):plan.module_scope.includes('lnx.reference_color.v1')?'参考或目标在预检后修改则拒绝，必须重新审核。样片保持不变，整组撤销/重做保留其他手动编辑。':'固定使用预检时的配方；目标照片若在预检后修改，不会被覆盖。'}</p>
        <p>预检可同步 {plan.ok} 张 · 受阻 {plan.blocked} 张 · 无效选择 {plan.rejected_docs?.length??0} 张</p>
        <p>冲突处理：{plan.policy==='recheck'?'任一目标变化则整批不写入，重新预检':'跳过有变化的目标，并逐张报告'}</p>
        {result?.source_changed_since_preflight&&!faceStyleRecipe&&<p>源图在预检后已变化，本次仍使用已确认的旧版本配方。</p>}
        <details><summary>查看冻结的模块与参数</summary><pre>{JSON.stringify(plan.applies,null,2)}</pre></details>
        {plan.persistent_association&&<AssociationEvidence value={plan.persistent_association} source={plan.association_source} sourceOutcome={result?.source_outcome}/>}
        {peoplePreview}
      </>}
      {plan&&collarboneSelected&&<section aria-label="逐成员锁骨真实图像审核">
        {plan.collarbone_cohort&&<p>本次是原子持久关联，源成员也可能改变。必须按下列顺序逐张审核源成员与所有目标，不能只确认目标或沿用另一个成员的范围。已有显式参数可能使部分图像保持不变，仍须确认。</p>}
        {collarboneTargets.map(target=><div key={target.document_id}>
          <h3>{target.source?'源成员':'目标成员'}：{file(target.path)}</h3>
          <CollarboneTransferReview preflightToken={plan.preflight_token} value={target.visual} coverage={target.coverage}
            reviewKey={collarboneReviewKey(collarboneToken,target.visual)} disabled={busy||state.phase!=='review'}
            onReady={(key,ready)=>setCollarboneImages(old=>old[key]===ready?old:{...old,[key]:ready})}/>
        </div>)}
      </section>}
      {plan&&portraitSelected&&<section aria-label="持久人物关联全部成员真实图像审核">
        <p>源成员与所有目标共同提交。更高优先级的人脸显式参数可能使图像保持不变，仍必须逐张读取并勾选。此审核也适用于后续普通参数更新和整体解除，不会根据数值推断或保存命名风格标签。</p>
        {portraitTargets.map((target,index)=><div key={target.document_id}>
          <h3>{target.source?'源成员':'目标成员'} {index+1} / {portraitTargets.length}：{file(target.path)}</h3>
          <PortraitCohortReview preflightToken={plan.preflight_token} value={target.visual} recipe={namedRecipe}
            reviewKey={portraitCohortReviewKey(portraitToken,target.visual)} disabled={busy||state.phase!=='review'}
            onReady={(key,ready)=>setPortraitImages(old=>old[key]===ready?old:{...old,[key]:ready})}/>
        </div>)}
      </section>}
      {plan&&faceStyleRecipe&&<section aria-label="逐目标新版脸型真实图像审核">
        {faceStyleTargets.map((target,index)=>target.people_transfer?.face_style_visual&&<div key={target.document_id}>
          <h3>目标 {index+1} / {faceStyleTargets.length}：{file(target.path)}</h3>
          <FaceStyleBatchReview preflightToken={plan.preflight_token} value={target.people_transfer.face_style_visual} recipe={faceStyleRecipe}
            reviewKey={faceStyleBatchReviewKey(faceStyleToken,target.people_transfer.face_style_visual)} disabled={busy||state.phase!=='review'}
            onReady={(key,ready)=>setFaceStyleImages(old=>old[key]===ready?old:{...old,[key]:ready})}/>
        </div>)}
      </section>}
      {!!targets.length&&<ul className="batchTargets">{targets.map(t=><li key={t.document_id} title={t.path}>
        <span>{file(t.path)}</span><span>{t.outcome==='applied'?'已同步':t.outcome==='unknown'?'结果未确认':t.outcome==='not_applied'?'未执行':reason(t.blocked)}</span>
        {plan?.module_scope.includes(CROP_OP)&&!t.blocked&&t.crop_transfer&&<CropTransferReview key={cropReviewKey(plan.preflight_token,t.crop_transfer)} value={t.crop_transfer} reviewKey={cropReviewKey(plan.preflight_token,t.crop_transfer)} onReady={(key,ready)=>setCropImages(old=>old[key]===ready?old:{...old,[key]:ready})}/>}
        {plan?.module_scope.includes(SPILL_TRANSFER_OP)&&!t.blocked&&t.spill_transfer&&<SpillTransferReview key={`${plan.request_id}:${spillTransferReviewKey(plan.preflight_token,t.spill_transfer)}`} value={t.spill_transfer} reviewKey={spillTransferReviewKey(plan.preflight_token,t.spill_transfer)} disabled={busy||state.phase!=='review'} onReady={(key,ready)=>setSpillImages(old=>old[key]===ready?old:{...old,[key]:ready})}/>}
        {plan?.module_scope.includes(SHADOW_TRANSFER_OP)&&!t.blocked&&t.shadow_transfer&&<ShadowTransferReview key={`${plan.request_id}:${shadowTransferReviewKey(plan.preflight_token,t.shadow_transfer)}`} value={t.shadow_transfer} reviewKey={shadowTransferReviewKey(plan.preflight_token,t.shadow_transfer)} disabled={busy||state.phase!=='review'} onReady={(key,ready)=>setShadowImages(old=>old[key]===ready?old:{...old,[key]:ready})}/>}
        {plan?.module_scope.includes(TORSO_TRANSFER_OP)&&!t.blocked&&t.torso_transfer&&<TorsoTransferReview key={`${plan.request_id}:${torsoTransferReviewKey(plan.preflight_token,t.torso_transfer)}`} value={t.torso_transfer} reviewKey={torsoTransferReviewKey(plan.preflight_token,t.torso_transfer)} disabled={busy||state.phase!=='review'} onReady={(key,ready)=>setTorsoImages(old=>old[key]===ready?old:{...old,[key]:ready})}/>}
        {plan?.module_scope.includes(WAIST_TRANSFER_OP)&&!t.blocked&&t.waist_transfer&&<WaistTransferReview value={t.waist_transfer} reviewKey={waistTransferReviewKey(waistToken,t.waist_transfer)} disabled={busy||state.phase!=='review'} onReady={(key,ready)=>setWaistImages(old=>old[key]===ready?old:{...old,[key]:ready})}/>}
        {plan?.module_scope.includes(HEAD_TRANSFER_OP)&&!t.blocked&&t.head_transfer&&<HeadTransferReview value={t.head_transfer} reviewKey={headTransferReviewKey(headToken,t.head_transfer)} disabled={busy||state.phase!=='review'} onReady={(key,ready)=>setHeadImages(old=>old[key]===ready?old:{...old,[key]:ready})}/>}
        {t.people_transfer&&<PeopleTransferEvidence value={t.people_transfer}/>}
        {t.local_mask_transfer&&<MaskTransferEvidenceView value={t.local_mask_transfer}/>}
        {t.reference_color&&<ReferenceColorReview value={t.reference_color}/>}
        {t.optical_transfer&&<AutomaticTransferReview report={t.optical_transfer}/>}
      </li>)}</ul>}
      {!!plan?.rejected_docs?.length&&<ul>{plan.rejected_docs.map((r,i)=><li key={i}>{String(r.doc)}：{r.error}</li>)}</ul>}
      {!!result?.conflicts?.length&&<ul>{result.conflicts.map((r,i)=><li key={i}>{file(r.path)}：{r.reason}</li>)}</ul>}
      <footer>
        {state.phase==='review'&&blockedReason&&<p role="status">{blockedReason}</p>}
        {state.phase==='review'&&<button className="tb primary" disabled={!!blockedReason||!plan?.ok||(plan.policy==='recheck'&&plan.blocked>0)} onClick={()=>{if(!blockedReason)onCommit(plan?.module_scope.includes(SPILL_TRANSFER_OP)?spillTransferAck(spillTargets.map(t=>t.spill_transfer!)):undefined,plan?.module_scope.includes(SHADOW_TRANSFER_OP)?shadowTransferAck(shadowTargets.map(t=>t.shadow_transfer!)):undefined,plan?.module_scope.includes(TORSO_TRANSFER_OP)?torsoTransferAck(torsoTargets.map(t=>t.torso_transfer!)):undefined,plan?.module_scope.includes(WAIST_TRANSFER_OP)?waistTransferAck(waistTargets.map(t=>t.waist_transfer!)):undefined,plan?.module_scope.includes(HEAD_TRANSFER_OP)?headTransferAck(headTargets.map(t=>t.head_transfer!)):undefined,collarboneSelected?collarboneAck(collarboneTargets.map(t=>t.visual)):undefined,faceStyleRecipe?faceStyleBatchAck(faceStyleTargets.map(t=>t.people_transfer!.face_style_visual!)):undefined,portraitSelected?portraitCohortAck(portraitTargets.map(t=>t.visual)):undefined);}}>{faceStyleRecipe?'确认所选新版脸型并仅应用到指定目标':plan?.persistent_association?'确认全部成员与持久关联操作':plan?.applies.target_policy==='explicit_face_map'?'仅确认本次人脸配对与参数并同步':'确认本次配方并同步'}</button>}
        {['review','error','done'].includes(state.phase)&&!['undo','redo'].includes(state.operation)&&<button className="tb" onClick={onReview}>重新预检</button>}
        {state.phase==='uncertain'&&<>{!state.queryOnly&&!faceStyleRecipe&&!portraitSelected&&!collarboneSelected&&!plan?.module_scope.includes(WAIST_TRANSFER_OP)&&!plan?.module_scope.includes(HEAD_TRANSFER_OP)&&<button className="tb" onClick={onAcknowledge}>我已检查照片，结束本次跟踪</button>}<button className="tb primary" onClick={onQuery}>再次查询这次任务</button></>}
      </footer>
    </section>
  </div>;
}
