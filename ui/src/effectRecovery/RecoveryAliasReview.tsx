// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect,useRef,useState} from 'react';
import type {SpillImage} from '../spillRemoval/model';
import {recoveryAliasMemberKey,type RecoveryAliasReview as Review} from './aliasModel';
import type {EffectRecoveryOwner} from './useEffectRecoveryWorkflow';

/** One member's pixels at a time. Prior exact member ACKs survive page navigation, never review replacement. */
export function RecoveryAliasReview({owner,review,preview}:{owner:EffectRecoveryOwner;review:Review;preview:string}){
  return <ReviewPages key={`${preview}:${review.review_sha256}`} owner={owner} review={review} preview={preview}/>;
}
function ReviewPages({owner,review,preview}:{owner:EffectRecoveryOwner;review:Review;preview:string}){
  const [page,setPage]=useState(0),[checked,setChecked]=useState<Record<string,boolean>>({});
  const {workflow}=owner,member=review.members[page],key=recoveryAliasMemberKey(preview,review,member);
  const live=useRef(true);
  useLayoutEffect(()=>{live.current=true;return()=>{live.current=false;for(const member of review.members)workflow.aliasMemberReviewed(preview,recoveryAliasMemberKey(preview,review,member),false);};},[preview,review,workflow]);
  function reviewed(memberKey:string,ready:boolean){if(!live.current)return;
    setChecked(old=>old[memberKey]===ready?old:{...old,[memberKey]:ready});workflow.aliasMemberReviewed(preview,memberKey,ready);}
  return <section aria-label="去眼袋效果恢复共享来源逐图审核">
    <strong>全部 {review.members.length} 张共享来源成员，尚未应用恢复</strong>
    <p>仅共享这位人物、此源图的去眼袋 v2 恢复向量。不是复制其他照片的蒙版、卧蚕保护、裁剪或形变。每张按自己的修补和完整编辑链分别计算，当前照片不能代替其他成员审核。</p>
    <nav aria-label="恢复审核成员分页">{review.members.map((item,index)=>{const itemKey=recoveryAliasMemberKey(preview,review,item);return <button type="button" key={itemKey}
      disabled={owner.pending} aria-current={index===page?'page':undefined} onClick={()=>setPage(index)}>{index+1}{checked[itemKey]?' · 已确认':''}</button>;})}</nav>
    <ReviewPage key={key} owner={owner} review={review} preview={preview} index={page} memberKey={key} checked={checked[key]===true} onReviewed={reviewed}/>
    <p role="status">已独立确认 {review.members.filter(item=>checked[recoveryAliasMemberKey(preview,review,item)]===true).length}/{review.members.length} 张。{owner.state.ending?'全部确认后仍须按底部保存按钮，才发布一笔完整成员批次。':'这是绘制前的只读效果，不会发布任何恢复修改。'}</p>
  </section>;
}
function ReviewPage({owner,review,preview,index,memberKey,checked,onReviewed}:{owner:EffectRecoveryOwner;review:Review;preview:string;index:number;memberKey:string;checked:boolean;onReviewed:(key:string,ready:boolean)=>void}){
  const [pair,setPair]=useState<{before:SpillImage;after:SpillImage}|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState('');
  const [loaded,setLoaded]=useState({before:false,after:false}),[presented,setPresented]=useState(false),[zoom,setZoom]=useState(false);
  const current=useRef(pair),live=useRef(true),generation=useRef(0);current.current=pair;
  const member=review.members[index],visual=member.visual;
  useLayoutEffect(()=>{live.current=true;return()=>{live.current=false;current.current=null;++generation.current;};},[]);
  useLayoutEffect(()=>{setPresented(false);if(!pair||!loaded.before||!loaded.after||error)return;
    const expected=pair;let second=0;const first=requestAnimationFrame(()=>{second=requestAnimationFrame(()=>{if(live.current&&current.current===expected)setPresented(true);});});
    return()=>{cancelAnimationFrame(first);cancelAnimationFrame(second);};
  },[pair,loaded,error]);
  async function load(){if(owner.pending||loading)return;const attempt=++generation.current;current.current=null;setPair(null);setLoading(true);setError('');setLoaded({before:false,after:false});setPresented(false);onReviewed(memberKey,false);
    const valid=()=>live.current&&generation.current===attempt;
    try{const before=await owner.workflow.readAliasImage(preview,review,index,'before',valid),after=await owner.workflow.readAliasImage(preview,review,index,'after',valid);
      if(valid()){const next={before,after};current.current=next;setPair(next);}}
    catch(cause){if(valid())setError(String(cause));}finally{if(valid())setLoading(false);}
  }
  async function decoded(side:'before'|'after',image:HTMLImageElement){const expected=pair;if(!expected||current.current!==expected||!live.current)return;
    try{await image.decode();if(!live.current||current.current!==expected)return;
      if(image.naturalWidth!==visual[side].width||image.naturalHeight!==visual[side].height)throw Error('审核图像实际显示尺寸不符');
      setLoaded(old=>({...old,[side]:true}));
    }catch(cause){if(live.current&&current.current===expected){setError(String(cause));setPresented(false);onReviewed(memberKey,false);}}
  }
  return <section aria-label={`恢复审核成员 ${index+1}`}>
    <h4>{index+1}. {index===0?'当前照片':'共享来源别名'}</h4><p>{member.path}</p>
    <p><small>文档 {visual.document_id} · 冻结版本 {visual.revision} · 自身裁剪、手工修补及其他配方不改变。</small></p>
    <button type="button" disabled={owner.pending||loading} onClick={()=>void load()}>{loading?'正在读取本成员…':pair?'重新读取本成员冻结图像':'读取本成员真实完整前后图像'}</button>
    {checked&&!pair&&<p>此冻结成员已独立确认。返回此页不会撤销确认；重新读取会先撤回确认。</p>}
    {!!error&&<p role="alert">{error} 可重试只读读取；若审核已失效，请结束画笔后重新审核。不会重复应用笔迹。</p>}
    <label><input type="checkbox" checked={zoom} onChange={event=>setZoom(event.target.checked)}/>按审核图像尺寸查看</label>
    {pair&&<div className="recoveryAliasPair">{(['before','after'] as const).map(side=><figure key={side}><figcaption>{side==='before'?'本笔之前':'此恢复候选之后'} · 输出 {visual[side==='before'?'before_output_size':'after_output_size'].join(' × ')}</figcaption>
      <img src={`data:image/png;base64,${pair[side].base64}`} width={visual[side].width} height={visual[side].height} style={{maxWidth:zoom?'none':'100%',height:'auto'}}
        alt={`成员 ${index+1} ${side==='before'?'本笔前完整编辑效果':'本恢复候选完整编辑效果'}`} onLoad={event=>void decoded(side,event.currentTarget)}
        onError={()=>{if(live.current&&current.current===pair){setError('本成员审核图像无法显示');setPresented(false);onReviewed(memberKey,false);}}}/></figure>)}</div>}
    <p><small>这是本成员完整源图计算后缩小的 RGB8 审核图，不是眼部原生像素裁剪，也不替代全分辨率验收。不会混合回原图或清除其他效果。</small></p>
    <label><input type="checkbox" checked={checked} disabled={owner.pending||!checked&&!presented||!!error}
      onChange={event=>onReviewed(memberKey,event.target.checked&&presented)}/>我已比较这张成员的完整前后效果，确认只恢复这位人物的去眼袋 v2 贡献。</label>
  </section>;
}
