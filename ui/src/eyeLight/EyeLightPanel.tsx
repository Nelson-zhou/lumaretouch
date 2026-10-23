import {useEffect,useState} from 'react';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {previewImage} from '../legShape/sourcePreview';
import {EyeLightControls} from './EyeLightControls';
import {EyeLightSupportEditor} from './EyeLightSupportEditor';
import {check,neutral,type EyeLight,type EyeLightReceipt} from './model';
export function EyeLightPanel({people,blocked}:{people:PeopleOwner;blocked:boolean}){
 const view=people.value?.eye_light,target=people.value?.editing_target;
 const [draft,setDraft]=useState<EyeLight>(view?.recipe??neutral()),[review,setReview]=useState(false),[error,setError]=useState('');
 const key=`${people.value?.binding.document_id}:${view?.face_ref.face_instance_id}:${view?.face_ref.analysis_revision}:${JSON.stringify(view?.recipe)}`;
 useEffect(()=>{setDraft(view?.recipe??neutral());setError('');},[key]);
 useEffect(()=>{setReview(false);},[view?.face_ref.face_instance_id,view?.face_ref.analysis_revision,people.value?.binding.document_id]);
 const unavailable=blocked||!people.enabled||people.state.pending||people.state.uncertain||!view||!view.native_available;
 const reason=!view?'请先选择完成真实分析的人物':!view.native_available?'眼神光 Rust 核心未安装，请使用完整打包版本':view.suspended??(!view.reviewed?'请先审核当前人物可见眼球':undefined);
 const receipt:EyeLightReceipt={status:unavailable?'unavailable':view?.reviewed?'ready':'needs-review',personId:view?.face_ref.face_instance_id??'',sourceRevision:people.value?.revision??0,reason,changedPixels:view?.changed_pixels};
 const requestReview=async()=>{try{if(!target||target.scope!=='face')throw Error('请切换为当前人物独立编辑，再审核眼球范围');await people.submit('eye_light_reference',{},target);setReview(true);}catch(e){setError(String(e));}};
 async function apply(){try{if(unavailable||!target)return;const value=check(draft);const leaves=(r:EyeLight):Record<string,string|number|boolean>=>({...Object.fromEntries((['left','right'] as const).flatMap(side=>Object.entries(r[side]).map(([k,v])=>[`/${side}/${k}`,v]))),'/linked':r.linked});const old=leaves(view?.recipe??neutral());const patches=Object.entries(leaves(value)).filter(([k,v])=>v!==old[k]).map(([k,v])=>({operation_id:'lnx.eye_light.v1',parameter_path:k,unset:false as const,value:v}));if(patches.length)await people.submit('patch',{patches},target);setError('');}catch(e){setError(String(e));}}
 const image=previewImage(view?.source_preview??null);
 return <div data-eye-light-workflow>
  <EyeLightControls value={draft} receipt={receipt} onChange={setDraft} onReview={()=>void requestReview()}/>
  <button type="button" disabled={unavailable} onClick={()=>void apply()}>应用眼神光</button>
  {view&&<p>当前人物素材候选变化（恢复与后续处理前）：{view.changed_pixels} 像素。显示与导出使用现有色彩流程，不声称恢复真实光源或完成整条 HDR 工作流。</p>}
  {review&&view&&<EyeLightSupportEditor faceKey={`${view.face_ref.asset_sha256}:${view.face_ref.face_instance_id}:${view.face_ref.analysis_revision}`} source={{...view.source,orientation:'exif_normalized_once'}} image={image} disabled={unavailable} onReview={async eyes=>{if(!target||target.scope!=='face')throw Error('人物范围已改变');await people.submit('eye_light_review',{eyes},target);setReview(false);}}/>}
  {review&&<button type="button" onClick={()=>setReview(false)}>关闭审核</button>}
  {(error||people.state.message)&&<p role="alert">{error||people.state.message}</p>}
 </div>;
}
