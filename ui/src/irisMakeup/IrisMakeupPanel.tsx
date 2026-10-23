// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useState} from 'react';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {previewImage} from './sourcePreview';
import {PATTERNS,neutral,patches,contextKey,type IrisView} from './model';
import {IrisMakeupSupportEditor} from './IrisMakeupSupportEditor';
export function IrisMakeupPanel({people,report,blocked}:{people:PeopleOwner;report:IrisView|null;blocked:boolean}){
 const [review,setReview]=useState(false),[error,setError]=useState('');const view=people.value;
 const key=view?contextKey(view):'';
 useEffect(()=>{setReview(false);setError('');},[view?.binding.document_id,report?.face_ref?.face_instance_id,report?.face_ref?.analysis_revision]);
 if(!view||!report)return <p role="status">美瞳需要当前照片的真实人物分析。</p>;
 const selected=view.faces.find(f=>f.face_ref.face_instance_id===view.selected_face_id);
 const disabled=blocked||!people.enabled||!selected?.enabled||selected?.analysis_status!=='verified'||people.state.uncertain||people.state.pending;
 async function open(){try{if(!view?.editing_target||view.editing_target.scope!=='face')throw Error('请切换为当前人物独立编辑');await people.submit('iris_reference',{},view.editing_target);setReview(true);setError('');}catch(e){setError(String(e));}}
 return <section aria-label="美瞳" data-control-id="PC-32471-C-62d685c7ac">
  <p>11 款本地原创程序纹理，保留原有瞳孔、高光和纹理，不改变视线或补全隐藏虹膜。</p>
  <button type="button" disabled={disabled} onClick={()=>void open()}>{report.reviewed?'重新审核双眼':'先审核可见虹膜与实测瞳孔'}</button>
  {review&&report.face_ref&&<IrisMakeupSupportEditor faceKey={JSON.stringify(report.face_ref)} source={{...report.source,orientation:'exif_normalized_once'}} image={previewImage(report.source_preview)} disabled={disabled} onReview={async eyes=>{if(!view.editing_target||view.editing_target.scope!=='face')throw Error('人物范围已变化');await people.submit('iris_review',{eyes},view.editing_target);setReview(false);}}/>}
  {review&&<button type="button" onClick={()=>setReview(false)}>关闭审核</button>}
  <div role="group" aria-label="原创美瞳纹理">{PATTERNS.map(([id,label])=><button key={id} type="button" disabled={disabled} aria-pressed={report.recipe.pattern===id} onClick={()=>people.patch(patches({...report.recipe,pattern:id}))}>{label}</button>)}</div>
  <label>程度（本地 0–100）<output>{Math.round(report.recipe.strength*100)}</output><input key={key} aria-label="美瞳程度" type="range" min={0} max={100} step={1} value={Math.round(report.recipe.strength*100)} disabled={disabled||!report.reviewed||!report.native_available} onChange={e=>people.patch(patches({...report.recipe,strength:Number(e.target.value)/100}))}/></label>
  <button type="button" disabled={disabled} onClick={()=>people.patch(patches(neutral()))}>重置美瞳</button>
  {!report.native_available&&<p role="status">美瞳 Rust 核心尚未安装，无法应用效果。</p>}
  <small>审核放大和轮廓编辑是本地安全工具，不是官网宣称的美瞳大小、左右解锁或自定义颜色控件。过小、闭眼、遮挡、强反光会拒绝整项应用。</small>
  {(error||report.suspended)&&<p role="alert">{error||report.suspended}</p>}{people.state.pending&&<p role="status">等待当前人物编辑回执，尚未确认应用。</p>}
 </section>;
}
