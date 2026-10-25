// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useLayoutEffect,useRef,useState,useSyncExternalStore} from 'react';
import {CONFIRMATIONS,CONFIRMATION_KEYS,OPERATION_ID,REQUIREMENT_ID,contextKey,faceKey,pairError,type Current,type Face,type Photograph} from './model';
import {ExpressionController,canPreview,locked,previewKey,selectedFace,selection,sourceDisplayKey,type State} from './controller';
import {FusionMaskEditor} from './FusionMaskEditor';
import {VerifiedImage} from './VerifiedImage';
import './expressionReplacement.css';

function FaceChoices({photo,selected,onSelect,disabled,label}:{photo:Photograph;selected:string;onSelect:(face:Face)=>void;disabled:boolean;label:string}){
  return <fieldset disabled={disabled} className="expression-face-choices"><legend>{label}</legend>
    {!photo.faces.length&&<p>没有符合保守条件的真实人脸，请先完成本图分析；不会自动补造定位。</p>}
    {photo.faces.map((face,index)=><button type="button" key={faceKey(face.face_ref)} disabled={!face.enabled} aria-pressed={selected===faceKey(face.face_ref)} onClick={()=>onSelect(face)}>
      人脸 {index+1} · {face.face_ref.face_instance_id}{!face.enabled?' · 已停用':''}
    </button>)}
  </fieldset>;
}
function FaceOverlay({photo,face}:{photo:Photograph;face:Face|null}){
  if(!face)return null;const c=face.crop;
  return <svg className="expression-face-overlay" viewBox={`-.5 -.5 ${photo.source.width} ${photo.source.height}`} preserveAspectRatio="none" aria-hidden="true">
    <rect x={c.left-.5} y={c.top-.5} width={c.width} height={c.height} fill="none" stroke="#f3c66d" strokeWidth={Math.max(1,photo.source.width/700)}/>
  </svg>;
}
function CandidateReview({state,controller}:{state:State;controller:ExpressionController}){
  const preview=state.preview!,source=state.preview_packet!.command.target.source,key=previewKey(state);
  const [before,setBefore]=useState(false),[after,setAfter]=useState(false),[mask,setMask]=useState(false),[checked,setChecked]=useState(false);
  const notify=useRef(controller);notify.current=controller;
  const ready=before&&after&&mask,confirmed=ready&&checked;
  useEffect(()=>{notify.current.reviewed(key,confirmed);return()=>notify.current.reviewed(key,false);},[key,confirmed]);
  return <section className="expression-review" aria-label="当前候选完整前后图审核">
    <h4>完整当前照片：应用前 / 候选后</h4>
    <p>这是完整照片的真实渲染缩略图，不是人脸裁切、效果示意或最终输出像素。原始画幅 {preview.output_width} × {preview.output_height}；融合前后均保留全图。</p>
    <div className="expression-image-pair">
      <VerifiedImage image={preview.before} source={source} label="应用前 · 完整当前照片" onReady={value=>{setBefore(value);if(!value)setChecked(false);}}/>
      <VerifiedImage image={preview.after} source={source} label="候选后 · 完整当前照片，尚未应用" onReady={value=>{setAfter(value);if(!value)setChecked(false);}}/>
    </div>
    <VerifiedImage image={preview.fusion_image} source={source} label="实际融合蒙版 · 白色参与，黑色保留当前照片，灰色为过渡" onReady={value=>{setMask(value);if(!value)setChecked(false);}}/>
    <label><input type="checkbox" checked={confirmed} disabled={!ready||state.phase!=='ready'} onChange={event=>setChecked(event.currentTarget.checked)}/>
      我已对照完整前后图，检查本人表情、融合边缘、眼口、他人和背景，接受将本次候选保存为独立副本</label>
  </section>;
}
/** Standalone module. Host owns one controller across navigation and native history. */
export function ExpressionReplacementPanel({current,controller,onClose}:{current:Current|null;controller:ExpressionController;onClose?:()=>void}){
  useLayoutEffect(()=>controller.bind(current),[current,controller]);
  const state=useSyncExternalStore(controller.subscribe,controller.snapshot,controller.snapshot),[error,setError]=useState('');
  const currentMatches=contextKey(current)===contextKey(state.current);
  const disabled=!currentMatches||locked(state)||!state.current?.available,target=selectedFace(state.current?.photo??null,state.target_ref),donorFace=selectedFace(state.donor,state.donor_ref),owners=selection(state);
  const problem=owners?pairError(owners.target,owners.donor):null;
  function action(run:()=>void|Promise<void>){setError('');try{void Promise.resolve(run()).catch(e=>setError(e instanceof Error?e.message:'操作未完成。'));}catch(e){setError(e instanceof Error?e.message:'操作未完成。');}}
  return <section className="expression-replacement" aria-label="当前照片的手动本人表情替换" data-operation={OPERATION_ID} data-requirement-id={REQUIREMENT_ID}>
    <header><h3>表情替换 · 手动本人素材</h3>{onClose&&<button type="button" onClick={onClose}>收起面板</button>}</header>
    <p>选择当前人脸和同场次另一张照片中的本人表情。使用实测定位做保守二维对齐与多频融合，不自动识别身份，也不生成表情或补出遮挡内容。</p>
    {!state.current?.available&&<p role="status">{state.current?.unavailable_reason||'真实来源、分析或宿主模块不可用。已有历史配方保持不变，不以空白效果冒充成功。'}</p>}
    {state.current&&<>
      <FaceChoices photo={state.current.photo} selected={faceKey(state.target_ref)} label="1. 当前照片中要替换的人脸" disabled={disabled} onSelect={face=>action(()=>controller.selectTarget(face.face_ref))}/>
      {target?<FusionMaskEditor source={state.current.photo.source} image={state.current.photo.image} label={`当前来源全图：${state.current.photo.label}`} onReady={ready=>controller.displayed('target',sourceDisplayKey(state.current!.photo),ready)}
        face={target} value={state.fusion} disabled={disabled||!state.target_displayed} onChange={value=>action(()=>controller.setFusion(value))}/>
        :<VerifiedImage image={state.current.photo.image} source={state.current.photo.source} label={`当前来源全图：${state.current.photo.label}`} onReady={ready=>controller.displayed('target',sourceDisplayKey(state.current!.photo),ready)}/>}
    </>}
    <button type="button" disabled={disabled} onClick={()=>action(()=>controller.chooseDonor())}>2. 选择另一张真实表情素材照片</button>
    {state.donor&&<>
      <FaceChoices photo={state.donor} selected={faceKey(state.donor_ref)} label="3. 明确选择素材中的本人" disabled={disabled} onSelect={face=>action(()=>controller.selectDonor(face.face_ref))}/>
      <VerifiedImage image={state.donor.image} source={state.donor.source} label={`素材来源全图：${state.donor.label}`} onReady={ready=>controller.displayed('donor',sourceDisplayKey(state.donor),ready)}><FaceOverlay photo={state.donor} face={donorFace}/></VerifiedImage>
    </>}
    {owners&&<p>当前人脸：{owners.target.face.face_ref.face_instance_id} / 分析 {owners.target.face.face_ref.analysis_revision}；素材人脸：{owners.donor.face.face_ref.face_instance_id} / 分析 {owners.donor.face.face_ref.analysis_revision}。两者来源和定位分别绑定，不复制定位或归属。</p>}
    {problem&&<p role="alert">{problem}</p>}
    <fieldset disabled={disabled||!owners||!state.target_displayed||!state.donor_displayed}><legend>4. 独立检查来源、本人和融合</legend>
      {CONFIRMATION_KEYS.map(key=><label key={key}><input type="checkbox" checked={state.confirmations[key]===true} onChange={event=>action(()=>controller.confirm(key,event.currentTarget.checked))}/>{CONFIRMATIONS[key]}</label>)}
    </fieldset>
    <fieldset disabled={disabled}><legend>融合设置</legend>
      <label>密度 <output>{Math.round(state.settings.density*100)}%</output><input type="range" min={1} max={100} step={1} value={Math.round(state.settings.density*100)} onChange={event=>action(()=>controller.setSettings({...state.settings,density:Number(event.currentTarget.value)/100}))}/></label>
      <label>金字塔层数<select value={state.settings.pyramid_levels} onChange={event=>action(()=>controller.setSettings({...state.settings,pyramid_levels:Number(event.currentTarget.value) as 1|2|3|4|5}))}>{[1,2,3,4,5].map(n=><option key={n} value={n}>{n}</option>)}</select></label>
      <p>本版不启用肤色匹配。范围、默认值和保守限制为本产品原创策略，并非官方公开参数。设置变化会撤销旧复核。</p>
    </fieldset>
    <button type="button" disabled={!currentMatches||!canPreview(state)} onClick={()=>action(()=>controller.preview())}>生成真实全图候选，不写入照片</button>
    {state.phase==='ready'&&state.preview&&state.preview_packet&&<CandidateReview key={previewKey(state)} state={state} controller={controller}/>}
    <div className="expression-actions">
      <button type="button" disabled={!currentMatches||state.phase!=='ready'||!state.reviewed} onClick={()=>action(()=>controller.apply())}>确认并保存独立结果副本</button>
      <button type="button" onClick={()=>action(()=>controller.cancel())}>{state.request?.command.action==='apply'?'保留待确认操作，不重复提交':state.request?'请求取消原只读任务':'丢弃未提交候选'}</button>
      {state.request&&<button type="button" onClick={()=>action(()=>controller.reconcile())}>查询原请求结果，不重发</button>}
    </div>
    {state.message&&<p role="status">{state.message}</p>}{error&&<p role="alert">{error}</p>}
    <p className="expression-policy">只处理当前照片中的一个明确人脸。当前照片及素材原件均不覆盖；没有批量替换、自动挑选最佳表情或 .tsq 兼容承诺。候选或申请待确认时，关闭面板不等于撤销。此独立模块尚未代表主程序接线、实机或自然度验收完成。</p>
  </section>;
}
