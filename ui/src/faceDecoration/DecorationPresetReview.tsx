// SPDX-License-Identifier: GPL-3.0-or-later
import {useCallback,useEffect,useRef,useState} from 'react';
import {verifyDecorationPreset,decorationPresetMembers,decorationPresetMemberKey,type DecorationPreset as Review,type DecorationPresetMember} from './transferModel';
import {fetchDecorationImage} from './visualTransport';
import {requestDecorationPresetImage,readDecorationPresetImage} from '../native';
import type {SpillImage} from '../spillRemoval/model';
type Props={value:Review;id:string;token:string;reviewKey:string;onReady:(key:string,ready:boolean)=>void;disabled?:boolean};
export function DecorationPresetReview(props:Props){return <ReviewMembers key={props.reviewKey} {...props}/>;}
function ReviewMembers({value,id,token,reviewKey,onReady,disabled=false}:Props){
 const [ready,setReady]=useState<Record<string,boolean>>({}),notify=useRef(onReady);notify.current=onReady;
 const members=decorationPresetMembers(value),allReady=members.every(member=>ready[decorationPresetMemberKey(reviewKey,member)]===true);
 const memberReady=useCallback((key:string,value:boolean)=>{if(!value)notify.current(reviewKey,false);setReady(old=>old[key]===value?old:{...old,[key]:value});},[reviewKey]);
 useEffect(()=>{notify.current(reviewKey,allReady);},[reviewKey,allReady]);
 useEffect(()=>()=>notify.current(reviewKey,false),[reviewKey]);
 return <section aria-label={value.version===2?'脸部装饰 混合预设共享来源全成员审核':'脸部装饰 完整预设当前人物审核'}>
  <strong>{value.version===2?`全部 ${members.length} 张共享来源成员的完整混合前后效果，尚未应用`:'当前照片的完整混合预设前后效果，尚未应用'}</strong>
  {value.version===2&&<p>所选色彩、裁剪和其他非人像配方只应用到当前照片；共享人像图修改（含脸部装饰和其他所选人像参数）同时影响以下所有来源别名。其他成员保留自己的裁剪、修补和当前配方，不会复制当前照片的完整编辑状态。每张图都按自己的完整编辑链渲染，不能以当前照片代替其他成员审核。</p>}
  <p>脸部装饰仅传递图案和程度。每个人物使用自己的已审核可见皮肤范围；不复制供图的皮肤笔迹、恢复蒙版、坐标或人物分析。未审核的人物不据此获得处理资格。</p>
  {value.coverage.targets.map(row=><p key={row.face_ref.face_instance_id}>目标人物 {row.face_ref.face_instance_id}：{row.scope==='neutral-no-effect'?'候选装饰程度为零；移除已有装饰仍须查看完整前后图。':'仅使用该人物自己已审核的可见皮肤范围。'}</p>)}
  {members.map((member,index)=><ReviewPair key={decorationPresetMemberKey(reviewKey,member)} value={value} id={id} token={token} reviewKey={decorationPresetMemberKey(reviewKey,member)} member={member} index={index} onReady={memberReady} disabled={disabled}/>)}
  {value.version===2&&<p role="status">已逐图确认 {members.filter(member=>ready[decorationPresetMemberKey(reviewKey,member)]===true).length}/{members.length} 张。必须读取、解码并独立确认每张冻结前后图；之后由同一个全成员批次管理撤销/重做，不创建当前照片的第二份撤销记录。</p>}
 </section>;
}
function ReviewPair({value,id,token,reviewKey,onReady,disabled=false,member,index}:Props&{member:DecorationPresetMember;index:number}){
 const [pair,setPair]=useState<{before:SpillImage;after:SpillImage}|null>(null),[attempt,setAttempt]=useState(0),[error,setError]=useState('');
 const [loaded,setLoaded]=useState({before:false,after:false}),[checked,setChecked]=useState(false),[zoom,setZoom]=useState(false);
 const notify=useRef(onReady);notify.current=onReady;const current=useRef(pair);current.current=pair;
 const visual=member.visual;
 useEffect(()=>{notify.current(reviewKey,false);return()=>notify.current(reviewKey,false);},[reviewKey]);
 useEffect(()=>{
  if(!attempt)return;let live=true;setPair(null);setError('');setLoaded({before:false,after:false});setChecked(false);notify.current(reviewKey,false);
  void (async()=>{try{
   if(!await verifyDecorationPreset(value))throw Error('人物可见皮肤支持或完整成员冻结审核摘要不一致');
   const api={request:requestDecorationPresetImage,read:readDecorationPresetImage};
   const fetchSide=(side:'before'|'after')=>fetchDecorationImage(api,{id,documentId:value.load_id,preflightToken:token,revision:value.visual.revision,
    ...(value.version===2?{memberDocumentId:visual.document_id,memberRevision:visual.revision}:{}),side,sha256:visual[side].sha256,requestId:crypto.randomUUID()},visual[side],()=>live);
   const before=await fetchSide('before'),after=await fetchSide('after');if(live)setPair({before,after});
  }catch(e){if(live)setError(String(e));}})();return()=>{live=false;current.current=null;};
 },[attempt,reviewKey,id,token,value,visual]);
 const ready=!!pair&&loaded.before&&loaded.after&&!error;
 useEffect(()=>{notify.current(reviewKey,ready&&checked);},[reviewKey,ready,checked]);
 async function onLoad(side:'before'|'after',image:HTMLImageElement){
  const expected=visual[side],captured=pair;if(!captured||current.current!==captured)return;
  try{
   await image.decode();if(current.current!==captured)return;
   if(image.naturalWidth!==expected.width||image.naturalHeight!==expected.height)throw Error('审核图像显示尺寸不符');
   setLoaded(old=>({...old,[side]:true}));
  }catch(e){if(current.current===captured){setError(String(e));setChecked(false);}}
 }
 function reload(){current.current=null;setChecked(false);setLoaded({before:false,after:false});notify.current(reviewKey,false);setAttempt(n=>n+1);}
 return <section aria-label={`完整预设成员 ${index+1} ${member.role==='active'?'当前照片':'共享来源别名'}`}>
  <h5>{index+1}. {member.role==='active'?'当前照片：完整所选配方 + 共享人像图（含脸部装饰）':'共享来源别名：只更新共享人像图（含脸部装饰）'}</h5>
  {member.path&&<p>{member.path}</p>}
  <p><small>文档 {visual.document_id} · 冻结版本 {visual.revision}。{member.role==='sibling'?'自身裁剪、修补及其他当前编辑保留。':''}</small></p>
  <button type="button" disabled={disabled||!!attempt&&!pair&&!error} onClick={reload}>{pair?'重新读取本成员冻结图像':'读取本成员实际完整前后图像'}</button>
  {!!error&&<p role="alert">{error} 仅重试读取不会重新提交应用。</p>}
  <label><input type="checkbox" checked={zoom} onChange={e=>setZoom(e.target.checked)}/>按审核图原尺寸查看</label>
  {pair&&<div style={{display:'flex',flexWrap:'wrap',gap:12,maxHeight:900,overflow:'auto'}}>{(['before','after'] as const).map(side=><figure key={`${attempt}:${side}`} style={{margin:0}}>
   <figcaption>{side==='before'?'应用前':member.role==='active'?'完整所选预设应用后':'共享图修改后的本成员完整效果'} · 完整输出 {visual[side==='before'?'before_output_size':'after_output_size'].join(' × ')}</figcaption>
   <img src={`data:image/png;base64,${pair[side].base64}`} width={visual[side].width} height={visual[side].height} style={{maxWidth:zoom?'none':'100%',height:'auto'}}
    alt={`成员 ${index+1} ${side==='before'?'完整编辑链应用前':'完整混合候选效果'}`} onLoad={e=>void onLoad(side,e.currentTarget)} onError={()=>{if(current.current===pair){setError('审核图像未显示');setChecked(false);}}}/>
  </figure>)}</div>}
  <p><small>先计算本成员完整源图及全部效果，再生成最长边不超过 1024 像素的 RGB8 审核图；不是面部局部叠加示意图，不代替全分辨率照片验收。目标手绘审核不是自动遮挡分割。</small></p>
  <label><input type="checkbox" disabled={disabled||!ready} checked={ready&&checked} onChange={e=>setChecked(ready&&e.target.checked)}/>我已比较本成员完整前后图、脸部图案、可见皮肤及相邻人物与背景，确认{member.role==='active'?'当前照片完整所选配方':'本成员只更新共享图，保留自己的其他编辑'}</label>
 </section>;
}
