// SPDX-License-Identifier: GPL-3.0-or-later
import {ReferenceColorReview} from '../referenceColor/ReferenceColorReview';
import {useEffect,useRef,useState} from 'react';
import {requestPortraitPresetGroup,readPortraitPresetGroup} from '../native';
import {acknowledgments,catalogue,checkedPlan,imageData,scopeLabel,type Plan,type Preset,type Reply} from './model';
type Pending={id:string;plan:Plan;deliveryContextKey:string};
type Preparation={id:string;docs:string[];preset:Preset;engineKey:string};
let retainedPreparation:Preparation|null=null;
// A dismissal/remount never grants permission to repeat an uncertain write.
let retainedCommit:Pending|null=null;
async function bounded<T>(task:Promise<T>):Promise<T>{return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('原请求响应超时，尚未确认结果。')),120000);task.then(value=>{clearTimeout(timer);resolve(value);},error=>{clearTimeout(timer);reject(error);});});}
const requestId=()=>`portrait-group-${crypto.randomUUID()}`;
async function poll(id:string,action:string,current:()=>boolean):Promise<Reply>{
  const deadline=Date.now()+120000;
  while(current()){
    const r=await bounded(readPortraitPresetGroup(id));
    if(r.request_id!==id)throw Error('回执请求身份不匹配。');
    if(r.phase==='done'){
      const result=r.result;
      if(!result||result.request_id!==id||result.action!==action)throw Error('回执动作身份不匹配。');
      return result;
    }
    if(r.phase!=='pending'||Date.now()>deadline)throw Error(r.error||'尚不能确认结果；请查询原请求，不重复提交。');
    await new Promise(resolve=>setTimeout(resolve,150));
  }
  throw Error('请求展示已失效。');
}
async function request(action:string,options:Record<string,unknown>,current:()=>boolean,id=requestId()){
  const queued=await bounded(requestPortraitPresetGroup(action,{...options,requestId:id}));
  if(!queued.requested)throw Error('请求未确认入队。');
  const result=await poll(id,action,current);
  if(result.success!==true||result.outcome_unknown===true)throw Error(String(result.error||'整组操作未完成。'));
  return result;
}
export function PortraitPresetGroupPanel({docs,currentDocument,enabled,preparationEnabled,contextKey,engineKey,deliveryContextKey,onPreparationLock,onComplete,onApplied}:{docs:string[];currentDocument:string;enabled:boolean;preparationEnabled:boolean;contextKey:string;engineKey:string;deliveryContextKey:string;onPreparationLock:(locked:boolean)=>void;onComplete:()=>void;onApplied:(receipt:Reply)=>void}){
  const [preparing,setPreparing]=useState<Preparation|null>(retainedPreparation);
  const latest=useRef({identity:'',docs,selected:'',engineKey,deliveryContextKey});
  const [presets,setPresets]=useState<Preset[]>([]),[selected,setSelected]=useState('');
  const [plan,setPlan]=useState<Plan|null>(retainedCommit?.plan??null),[pending,setPending]=useState<Pending|null>(retainedCommit);
  const [images,setImages]=useState<Record<string,string>>({}),[displayed,setDisplayed]=useState<Record<string,boolean>>({});
  const [accepted,setAccepted]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const generation=useRef(0),mounted=useRef(true),planIdentity=useRef('');
  const identity=JSON.stringify([contextKey,docs,selected]);
  latest.current={identity,docs,selected,engineKey,deliveryContextKey};
  useEffect(()=>{onPreparationLock(!!preparing);},[!!preparing,onPreparationLock]);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;generation.current++;};},[]);
  useEffect(()=>{if(!retainedPreparation)generation.current++;setImages({});setDisplayed({});setAccepted(false);if(!retainedCommit)setPlan(null);},[identity]);
  const live=(n:number)=>mounted.current&&generation.current===n;
  async function refresh(){
    if(busy||pending||preparing||!enabled)return;const n=++generation.current;setBusy(true);setPlan(null);setAccepted(false);
    try{const r=await request('portrait_preset_catalogue',{},()=>live(n));if(live(n)){setPresets(catalogue(r.catalogue));setMessage('请选择完整兼容预设；不支持的混合模块不会被截去后应用。');}}
    catch(e){if(live(n))setMessage(String(e));}finally{if(mounted.current)setBusy(false);}
  }
  async function loadImages(p:Plan,n:number){
    setImages({});setDisplayed({});setAccepted(false);
    for(const target of p.targets)for(const side of ['before','after'] as const){
      const data=await imageData(p,target,side,page=>request('portrait_preset_image',{preflightToken:p.preflight_token,documentId:target.document_id,side,page},()=>live(n)),()=>live(n));
      if(!live(n))return;setImages(old=>({...old,[`${target.document_id}:${side}`]:data}));
    }
  }
  async function prepare(){
    const preset=presets.find(p=>p.id===selected);
    if(busy||pending||preparing||!enabled||!preset||!docs.length||docs.length>8||docs.includes(currentDocument))return;
    const n=++generation.current,frozenDocs=[...docs];setBusy(true);setPlan(null);setMessage('正在冻结整组候选；不运行新的分析，也不应用预设。');
    try{const r=await request('portrait_preset_preflight',{docs:frozenDocs,presetId:preset.id,presetSha256:preset.preset_sha256},()=>live(n));
      const p=checkedPlan(r,frozenDocs,preset);if(!live(n))return;planIdentity.current=identity;setPlan(p);await loadImages(p,n);if(live(n))setMessage('所有候选已读取；请查看各图后一次确认整组。');}
    catch(e){if(live(n))setMessage(String(e));}finally{if(mounted.current)setBusy(false);}
  }
  async function settlePreparation(p:Preparation,dispatch:boolean){
    setBusy(true);setPlan(null);setImages({});setDisplayed({});setAccepted(false);
    setMessage('正在逐张执行真实加载与各照片自己的人脸分析；全部准备并恢复编辑器后才冻结整组。未知结果只查询原请求。');
    try{
      if(dispatch){const queued=await bounded(requestPortraitPresetGroup('portrait_preset_prepare',{requestId:p.id,docs:p.docs,presetId:p.preset.id,presetSha256:p.preset.preset_sha256}));if(!queued.requested)throw Error('准备入队结果未确认。');}
      const r=await poll(p.id,'portrait_preset_prepare',()=>mounted.current);
      if(r.portrait_preset!==true||r.preset_id!==p.preset.id||r.preset_sha256!==p.preset.preset_sha256||JSON.stringify(r.portrait_preset_docs)!==JSON.stringify(p.docs)||r.outcome_unknown!==false)throw Error(String(r.error||'准备回执身份或结果未确认。'));
      if(r.success===false&&r.no_write===true){retainedPreparation=null;setPreparing(null);setMessage(String(r.error||'准备未启动。'));return;}
      const rows=r.preparation_results;
      if(r.preparation!==true||r.editor_restored!==true||!Array.isArray(rows)||rows.length!==p.docs.length||rows.some((row,i)=>!row||typeof row!=='object'||row.document_id!==p.docs[i]||!['prepared','failed','not_started'].includes(row.status)))throw Error('准备结果或编辑器恢复未确认；保留原请求，禁止重新分析。');
      const summary=rows.map(row=>`${row.document_id}: ${row.status==='prepared'?'已准备':row.status==='failed'?'失败':'未开始'}${row.error?`（${String(row.error)}）`:''}`).join('；');
      if(r.success!==true){retainedPreparation=null;setPreparing(null);setMessage(`${summary}。${String(r.error||'整组未冻结，未应用预设。')} 已准备照片可另选后只读预检；不要把部分完成当作整组成功。`);onComplete();return;}
      if(rows.some(row=>row.status!=='prepared'))throw Error('成功回执含未完成目标。');
      const plan=checkedPlan(r,p.docs,p.preset);
      retainedPreparation=null;setPreparing(null);
      const now=latest.current;
      if(now.engineKey!==p.engineKey||JSON.stringify(now.docs)!==JSON.stringify(p.docs)||now.selected!==p.preset.id){setMessage(`${summary}。选择、预设或引擎已变化，不沿用本次审核；请重新只读预检。`);return;}
      const n=++generation.current;planIdentity.current=now.identity;setPlan(plan);await loadImages(plan,n);
      if(live(n))setMessage(`${summary}。编辑器已恢复；查看完整前后图后一次批准整组。`);
    }catch(e){if(mounted.current)setMessage(`${String(e)} ${retainedPreparation?'仅查询原准备结果，不重新发送。':'准备已确认；候选图可只读重载。'}`);}finally{if(mounted.current)setBusy(false);}
  }
  function startPreparation(){
    const preset=presets.find(p=>p.id===selected);
    if(!preset||presets.find(p=>p.id===selected)?.portrait_group_support?.mode==='reference_color'||!enabled||!preparationEnabled||busy||pending||preparing||!docs.length||docs.length>8||docs.includes(currentDocument))return;
    const p={id:requestId(),docs:[...docs],preset:structuredClone(preset),engineKey};
    retainedPreparation=p;setPreparing(p);generation.current++;void settlePreparation(p,true);
  }
  async function retryImages(){if(!plan||busy||pending||preparing)return;const n=++generation.current;setBusy(true);try{await loadImages(plan,n);}catch(e){if(live(n))setMessage(String(e));}finally{if(mounted.current)setBusy(false);}}
  const ready=planIdentity.current===identity&&!!plan&&plan.targets.every(t=>['before','after'].every(side=>displayed[`${t.document_id}:${side}`]===true));
  async function settle(p:Pending,dispatch:boolean){
    setBusy(true);setMessage('正在核对原组提交回执；不会重复应用。');
    try{
      if(dispatch){const q=await bounded(requestPortraitPresetGroup('portrait_preset_commit',{requestId:p.id,preflightToken:p.plan.preflight_token,portraitPresetAck:acknowledgments(p.plan),accepted:true}));if(!q.requested)throw Error('提交入队结果未确认。');}
      const r=await poll(p.id,'portrait_preset_commit',()=>mounted.current);
      if(r.success===false&&r.no_write===true&&r.outcome_unknown!==true){retainedCommit=null;setPending(null);setAccepted(false);setMessage(String(r.error||'整组未写入，请重新预检。'));setPlan(null);return;}
      if(r.success!==true||r.outcome_unknown!==false||r.portrait_preset!==true||r.accepted!==true||r.preset_id!==p.plan.preset_id||r.preset_sha256!==p.plan.preset_sha256
        ||(!Array.isArray(r.portrait_preset_ack)||r.portrait_preset_ack.length!==p.plan.targets.length||acknowledgments(p.plan).some((ack,i)=>Object.entries(ack).some(([key,value])=>(r.portrait_preset_ack as Reply[])[i]?.[key]!==value)))||typeof r.batch_id!=='string'||!r.batch_id||r.preflight_token!==p.plan.preflight_token
        ||JSON.stringify(r.approved_document_ids)!==JSON.stringify(p.plan.targets.map(t=>t.document_id)))throw Error(String(r.error||'提交回执未证明完整冻结组，保留未知状态。'));
      retainedCommit=null;setPending(null);setPlan(null);setImages({});setDisplayed({});setAccepted(false);setMessage('整组已应用到现有批量历史；工程保存与输出尚未完成，画质与性能尚未验收。');onComplete();
      try{if(p.deliveryContextKey!==latest.current.deliveryContextKey)throw Error('引擎或工程已变化，请核对原组；旧回执不会接到当前工程');onApplied(r);}catch(e){setMessage(`整组应用已确认；交付未接通：${String(e)}。不会重复应用。`);}
    }catch(e){if(mounted.current)setMessage(`${String(e)} 仅查询原提交，不重新批准。`);}finally{if(mounted.current)setBusy(false);}
  }
  function commit(){if(!plan||!ready||!accepted||busy||pending||preparing||!enabled)return;const p={id:requestId(),plan:structuredClone(plan),deliveryContextKey};retainedCommit=p;setPending(p);void settle(p,true);}
  return <section className="batchActions" data-portrait-preparation-owner="true" aria-label="预设与参考色彩整组审核">
    <h4>预设与参考色彩 · 整组审核</h4>
    <p>皮肤预设：选择 1–8 张未编辑原图。多人美白／红润及质感／清晰度预设逐张分析并作用于该图检测到的全部 1–8 张已验证人脸；兼容混合预设中的曝光／白平衡作用于整张照片，不局限于皮肤；不是自动逐图校色。旧版磨皮预设仍只支持单脸，不与这些逐脸模块混用，算法不会互换。已有分析可只读预检；当前打开图不能在组内。不识别跨图身份、不复制其他照片的脸或蒙版。未触及检测上限也不保证没有漏检，请逐图检查漏脸。模糊、检测截断或不支持目标拒绝整组，不静默跳过。</p>
    <small>8 张照片及每图最多 8 张脸是资源与界面的范围限制，不是已验证的性能指标。显式准备会串行切图分析并恢复原编辑器；不代表自动批准、保存或导出。</small>
    <div><button disabled={!enabled||busy||!!pending||!!preparing} onClick={()=>void refresh()}>读取兼容预设</button>
    <select aria-label="整组预设" value={selected} disabled={busy||!!pending||!!preparing} onChange={e=>setSelected(e.target.value)}><option value="">请选择</option>{presets.map(p=><option key={p.id} value={p.id}>{p.name} · {p.portrait_group_support?.mode!=='legacy_scalar'?scopeLabel(p.module_ids):'旧版单脸'} · {p.id}</option>)}</select>
    <button disabled={!enabled||busy||!!pending||!!preparing||!selected||docs.length<1||docs.length>8||docs.includes(currentDocument)} onClick={()=>void prepare()}>只读预检所选 {docs.length} 张</button>
    <button disabled={presets.find(p=>p.id===selected)?.portrait_group_support?.mode==='reference_color'||!enabled||!preparationEnabled||busy||!!pending||!!preparing||!selected||docs.length<1||docs.length>8||docs.includes(currentDocument)} onClick={startPreparation}>开始准备所选新原图并整组审核</button></div>
    {!preparing&&docs.includes(currentDocument)&&<p>请取消选择当前打开照片；不会自动从组里删掉它。</p>}
    {message&&<p role="status">{message}</p>}
    <p>参考色彩预设仅包含参考意图：逐图自动寻找场景对应并拟合，不复制滑杆或人脸。无需人脸准备；样片必须已保存在本机。场景不相似、对应不足或来源不明时整组拒绝。须逐张看完整画面，不代表画质已验收。</p>
    {plan&&<div>{plan.mode==='retained_people'&&<p>本次完整作用域：{scopeLabel(plan.module_scope)}。预设包含全图调色时，与各图自己的逐脸效果一起审核；不会只应用其中一部分。</p>}{plan.targets.map(t=><section key={`${plan.preflight_token}:${t.document_id}`}><h5>{t.path} · 版本 {t.revision}{plan.mode==='retained_people'?` · 本图全部 ${t.face_count} 张已验证人脸`:''}</h5>{plan.mode==='reference_color'&&t.reference_color&&<ReferenceColorReview value={t.reference_color}/>}<div className="local-workflow-review-images">{(['before','after'] as const).map(side=>{
      const key=`${t.document_id}:${side}`,url=images[key],meta=t[side],n=generation.current;
      return <figure key={side}><figcaption>{side==='before'?'应用前':'冻结候选（未应用）'}</figcaption>{url?<img src={url} alt={`${t.path} ${side==='before'?'应用前':'候选效果'}`} onLoad={e=>{if(live(n)){const i=e.currentTarget;setDisplayed(old=>({...old,[key]:i.complete&&i.naturalWidth===meta.width&&i.naturalHeight===meta.height}));}}} onError={()=>{if(live(n)){setDisplayed(old=>({...old,[key]:false}));setAccepted(false);}}}/>:<p>尚未完整读取并校验</p>}</figure>;
    })}</div></section>)}
    {!pending&&<><button disabled={busy} onClick={()=>void retryImages()}>重新读取前后图（只读）</button><label><input type="checkbox" disabled={!ready||busy||!enabled} checked={accepted} onChange={e=>setAccepted(e.target.checked)}/>我已查看组内每张照片的完整前后图{plan.mode==='retained_people'?'，确认所列全图调色及各图全部已验证人脸的逐脸效果（不匹配跨图身份）':''}，批准此冻结组。</label><button disabled={!ready||!accepted||busy||!enabled} onClick={commit}>一次批准并应用整组</button><button disabled={busy} onClick={()=>{generation.current++;setPlan(null);setImages({});setDisplayed({});setAccepted(false);}}>关闭审核（不应用）</button></>}
    </div>}
    {preparing&&<button disabled={busy} onClick={()=>void settlePreparation(preparing,false)}>查询原组准备结果（不重发）</button>}
    {pending&&<button disabled={busy} onClick={()=>void settle(pending,false)}>查询原组提交结果（不重发）</button>}
  </section>;
}
