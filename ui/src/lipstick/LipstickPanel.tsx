// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useState} from 'react';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import type {useLipstickPicker} from './useLipstickPicker';
import {LipstickControls} from './LipstickControls';
import {ColorSamplePanel} from '../components/ColorSamplePanel';
import {contextKey} from './model';
import {LipstickSupportEditor} from './LipstickSupportEditor';
import {previewImage} from '../legShape/sourcePreview';
type Picker=ReturnType<typeof useLipstickPicker>;
export function LipstickPanel({people,picker,blocked,onArm}:{people:PeopleOwner;picker:Picker;blocked:boolean;onArm:()=>Promise<void>}){
  const [error,setError]=useState(''),[review,setReview]=useState(false);const view=people.value,report=view?.lipstick;
  useEffect(()=>{setReview(false);setError('');},[view?.binding.document_id,report?.face_ref?.face_instance_id,report?.face_ref?.analysis_revision]);
  if(!view||!report)return <p role="status">口红需要当前照片的真实人物分析，请在人物栏选中人物。</p>;
  const selected=view.faces.find(f=>f.face_ref.face_instance_id===view.selected_face_id);
  const unavailable=!people.enabled||!selected?.enabled||selected?.analysis_status!=='verified'||!report.native_available;
  const disabled=blocked||unavailable||people.state.uncertain;
  async function library(action:'save'|'remove',colour:string){
    if(!view?.editing_target)throw Error('请选择明确的人物编辑范围');
    await people.submit('lipstick_palette',{action,colour},view.editing_target);
  }
  async function apply(){try{await picker.apply();setError('');}catch(e){setError(String(e));}}
  const image=previewImage(report.source_preview);
  async function requestReview(){try{if(!view?.editing_target||view.editing_target.scope!=='face')throw Error('请切换为当前人物独立编辑，再审核唇部');picker.cancel();await people.submit('lipstick_reference',{},view.editing_target);setReview(true);setError('');}catch(e){setError(String(e));}}
  return <>
    <button type="button" disabled={disabled||people.state.pending} onClick={()=>void requestReview()}>{report.reviewed?'重新审核可见唇部范围':'先审核可见唇部范围'}</button>
    {!report.reviewed&&<p>启用程度前，请在当前人物的原图参考上涂选上下可见唇部；不会把语义蒙版冒充已审核范围。</p>}
    {review&&report.face_ref&&<LipstickSupportEditor faceKey={`${report.face_ref.asset_sha256}:${report.face_ref.face_instance_id}:${report.face_ref.analysis_revision}`} source={{...report.source,orientation:'exif_normalized_once'}} image={image} disabled={disabled||people.state.pending} onReview={async regions=>{if(!view.editing_target||view.editing_target.scope!=='face')throw Error('人物范围已变化');await people.submit('lipstick_review',{regions},view.editing_target);setReview(false);}}/>}
    {review&&<button type="button" onClick={()=>setReview(false)}>关闭唇部审核</button>}
    <LipstickControls key={contextKey(view)} value={report.recipe} saved={report.library.saved_colours}
      disabled={disabled} busy={people.state.pending} reason={(report.suspended??(unavailable?'请启用真实分析人物及完整口红核心。':people.state.message))||undefined}
      fact={report.facts} commit={people.patch} save={c=>library('save',c)} remove={c=>library('remove',c)} pick={onArm}
      pickerUnavailable={disabled?'当前编辑状态不可取色':undefined}/>
    {picker.active&&<><ColorSamplePanel sampler={picker} canArm={!disabled} reason="口红取色：锁定当前代理浮点输出，再点击画面" onArm={()=>void onArm().catch(e=>setError(String(e)))}/>
      <button type="button" disabled={disabled||picker.ui.phase!=='eligible'||!picker.ui.readout?.success} onClick={()=>void apply()}>使用此颜色</button></>}
    {error&&<p role="alert">{error}</p>}
  </>;
}
