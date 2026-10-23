// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useState} from 'react';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import type {useBrowMakeupPicker} from './useBrowMakeupPicker';
import {BrowMakeupBrowControls} from './BrowMakeupBrowControls';
import {edit,patches} from './model';
import {ColorSamplePanel} from '../components/ColorSamplePanel';
import {contextKey} from './model';
import {BrowMakeupSupportEditor} from './BrowMakeupSupportEditor';
import {previewImage} from '../legShape/sourcePreview';
type Picker=ReturnType<typeof useBrowMakeupPicker>;
export function BrowMakeupPanel({people,picker,blocked,onArm}:{people:PeopleOwner;picker:Picker;blocked:boolean;onArm:()=>Promise<void>}){
  const [error,setError]=useState(''),[review,setReview]=useState(false);const view=people.value,report=view?.brow_makeup;
  useEffect(()=>{setReview(false);setError('');},[view?.binding.document_id,report?.face_ref?.face_instance_id,report?.face_ref?.analysis_revision]);
  if(!view||!report)return <p role="status">眉妆需要当前照片的真实人物分析，请在人物栏选中人物。</p>;
  const selected=view.faces.find(f=>f.face_ref.face_instance_id===view.selected_face_id);
  const unavailable=!people.enabled||!selected?.enabled||selected?.analysis_status!=='verified'||!report.native_available;
  const disabled=blocked||unavailable||people.state.uncertain;
  async function library(action:'save'|'remove',colour:string){
    if(!view?.editing_target)throw Error('请选择明确的人物编辑范围');
    await people.submit('brow_makeup_palette',{action,colour},view.editing_target);
  }
  async function apply(){try{await picker.apply();setError('');}catch(e){setError(String(e));}}
  const image=previewImage(report.source_preview);
  async function requestReview(){try{if(!view?.editing_target||view.editing_target.scope!=='face')throw Error('请切换为当前人物独立编辑，再审核眉毛及邻近额头');picker.cancel();await people.submit('brow_makeup_reference',{},view.editing_target);setReview(true);setError('');}catch(e){setError(String(e));}}
  return <>
    <button type="button" disabled={disabled||people.state.pending} onClick={()=>void requestReview()}>{report.reviewed?'重新审核可见眉毛及邻近额头范围':'先审核可见眉毛及邻近额头范围'}</button>
    {!report.reviewed&&<p>启用程度前，请在当前人物的原图参考上涂选需要启用的每一侧眉毛与邻近额头；其他眼部审核不授权眉妆；遮挡时先解除联动，将该眉程度归零。</p>}
    {report.reviewed&&<p>已审核：{report.reviewed_sides.map(s=>s==='left'?'人物左眉':'人物右眉').join('、')}。未审核的一侧需保持程度为 0。</p>}
    {review&&report.face_ref&&<BrowMakeupSupportEditor faceKey={`${report.face_ref.asset_sha256}:${report.face_ref.face_instance_id}:${report.face_ref.analysis_revision}`} source={{...report.source,orientation:'exif_normalized_once'}} image={image} disabled={disabled||people.state.pending} onReview={async brows=>{if(!view.editing_target||view.editing_target.scope!=='face')throw Error('人物范围已变化');await people.submit('brow_makeup_review',{brows},view.editing_target);setReview(false);}}/>}
    {review&&<button type="button" onClick={()=>setReview(false)}>关闭眉毛及邻近额头审核</button>}
    <label><input type="checkbox" disabled={disabled||people.state.pending} checked={report.recipe.linked} onChange={e=>people.patch(patches({...report.recipe,linked:e.target.checked,...(e.target.checked?{left:report.recipe[picker.side],right:report.recipe[picker.side]}:{})}))}/>左右联动（重新联动采用当前眉参数）</label>
    <label>编辑眉侧<select value={picker.side} disabled={disabled||people.state.pending||picker.active} onChange={e=>picker.setSide(e.target.value as 'left'|'right')}><option value="left">人物左眉</option><option value="right">人物右眉</option></select></label>
    <BrowMakeupBrowControls key={contextKey(view)+picker.side} value={report.recipe[picker.side]} saved={report.library.saved_colours}
      disabled={disabled} busy={people.state.pending} reason={(report.suspended??(unavailable?'请启用真实分析人物及完整眉妆核心。':people.state.message))||undefined}
      fact={{changed_pixels:report.changed_pixels,reason:report.reason??undefined}} commit={eye=>people.patch(patches(edit(report.recipe,picker.side,eye)))} save={c=>library('save',c)} remove={c=>library('remove',c)} pick={onArm}
      pickerUnavailable={disabled?'当前编辑状态不可取色':undefined}/>
    {picker.active&&<><ColorSamplePanel sampler={picker} canArm={!disabled} reason="眉妆取色：锁定当前代理浮点输出，再点击画面" onArm={()=>void onArm().catch(e=>setError(String(e)))}/>
      <button type="button" disabled={disabled||picker.ui.phase!=='eligible'||!picker.ui.readout?.success} onClick={()=>void apply()}>使用此颜色</button></>}
    {error&&<p role="alert">{error}</p>}
  </>;
}
