import {useEffect,useRef,useState,useSyncExternalStore} from 'react';
import {peopleContext,type PeopleView,type ParameterPatch} from '../people/model';
import {HairSourceEditor} from './HairSourceEditor';
import {IDS,STYLES,check,contextKey,emptyMask,neutral,patches,resolvedRecipe,type HairContext,type HairMask,type HairPort,type HairPreview} from './model';
import './hairColour.css';
/** Scalar edits use the one people workflow; masks use source-owned review receipts. */
export function HairColourPanel({people,port,busy,patch,refresh}:{people:PeopleView|null;port:HairPort;busy:boolean;patch:(items:ParameterPatch[])=>Promise<void>;refresh:()=>Promise<void>}){
  const context=peopleContext(people),key=context?contextKey(context):'';
  const receipt=useSyncExternalStore(port.subscribe,port.snapshot,port.snapshot);
  const currentKey=useRef(key),reviewGeneration=useRef(0);currentKey.current=key;
  const [source,setSource]=useState<HairContext|null>(null),[kind,setKind]=useState<'support'|'recovery'>('support');
  const [mask,setMask]=useState<HairMask>(emptyMask),[preview,setPreview]=useState<HairPreview|null>(null),[reviewed,setReviewed]=useState(false);
  const [waiting,setWaiting]=useState(false),[error,setError]=useState('');
  let recipe=neutral(),recipeError='';try{recipe=resolvedRecipe(people);}catch(e){recipeError=String(e);}
  const selected=people?.faces.find(face=>face.face_ref.face_instance_id===people.selected_face_id);
  const canAssets=!!context&&context.target.scope==='face'&&context.target.target_id===people?.selected_face_id&&selected?.enabled&&selected.analysis_status==='verified';
  const locked=busy||waiting||receipt.pending||receipt.checking,canRecipe=!!people?.resolved&&!!context&&selected?.enabled&&selected.analysis_status==='verified';
  function closeReview(){reviewGeneration.current+=1;setSource(null);setPreview(null);setReviewed(false);setMask(emptyMask());setWaiting(false);}
  useEffect(()=>{reviewGeneration.current+=1;setSource(null);setPreview(null);setReviewed(false);setMask(emptyMask());setKind('support');setError('');setWaiting(false);},[key]);
  async function work<T,>(task:()=>Promise<T>,consume:(value:T)=>void){
    const captured=key,generation=reviewGeneration.current;setWaiting(true);setError('');
    const current=()=>currentKey.current===captured&&reviewGeneration.current===generation;
    try{const value=await task();if(current())consume(value);}
    catch(e){if(current())setError(String(e));}
    finally{if(current())setWaiting(false);}
  }
  function load(){if(!context)return;void work(()=>port.call<HairContext>('context',context,{}),value=>{const next=kind==='recovery'&&value.support_reviewed?'recovery':'support';setSource(value);setKind(next);setMask(value[next]);setPreview(null);setReviewed(false);});}
  function edit(next:HairMask){setMask(next);setPreview(null);setReviewed(false);}
  function changeKind(next:'support'|'recovery'){setKind(next);edit(source?.[next]??emptyMask());}
  async function sendRecipe(next:typeof recipe,field?:'style'|'strength'|'gloss'){
    await work(()=>patch(patches(check(next)).filter(item=>!field||item.parameter_path===`/${field}`)),()=>undefined);
  }
  return <section className="hair-colour-panel" aria-label="发色选择与现有高光光泽">
    <p>13 种发色意图，原创配色与 0–100% 强度，并非商业像素复刻。默认均为 0，不自动美化导入照片。</p>
    <label data-tool-anchor="发色选择" data-control-id={IDS.colour}>发色选择 <select value={recipe.style} disabled={locked||!canRecipe} onChange={e=>void sendRecipe({...recipe,style:e.target.value as typeof recipe.style},'style')}>
      {STYLES.map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
    <label data-control-id={IDS.colour}>发色强度 {Math.round(recipe.strength*100)}%<input aria-label="发色强度" type="range" min="0" max="100" step="1" value={Math.round(recipe.strength*100)} disabled={locked||!canRecipe} onChange={e=>void sendRecipe({...recipe,strength:Number(e.target.value)/100},'strength')}/></label>
    <label data-tool-anchor="头发光泽" data-control-id={IDS.gloss}>已有高光光泽 {Math.round(recipe.gloss*100)}%<input aria-label="已有高光光泽" type="range" min="0" max="100" step="1" value={Math.round(recipe.gloss*100)} disabled={locked||!canRecipe} onChange={e=>void sendRecipe({...recipe,gloss:Number(e.target.value)/100},'gloss')}/></label>
    <button type="button" disabled={locked||!canRecipe} onClick={()=>void sendRecipe(neutral())}>重置发色与光泽</button>
    <p>先审核所选人物头发范围，再增加效果。光泽只增强源图已有亮部结构，不做全头发曝光。裁黑、过曝和深黑发染浅存在真实信息限制，不生成发丝、光源或缺失细节。</p>
    {!canAssets&&<p role="status">选区与恢复只属于此照片的单个人物。请在人物栏选择“人物独立覆盖”；人物/分组参数可继承，但蒙版不跨照片复制。</p>}
    <div className="hair-toolbar"><button type="button" disabled={locked||!canAssets} onClick={load}>打开源图并审核头发范围</button>
      <button type="button" disabled={!receipt.pending||waiting||receipt.checking} onClick={()=>void work(()=>port.recover(),()=>{setSource(null);setPreview(null);})}>查询原请求结果</button></div>
    {source&&<div className="hair-review">
      <div className="hair-toolbar"><button type="button" disabled={locked} aria-pressed={kind==='support'} onClick={()=>changeKind('support')}>人物头发范围</button>
        <button type="button" disabled={locked||!source.support_reviewed} aria-pressed={kind==='recovery'} onClick={()=>changeKind('recovery')}>仅恢复本项发色/光泽</button>
        <button type="button" onClick={closeReview}>{receipt.pending?'关闭审核，已发请求仍待确认':'关闭审核，不提交草稿'}</button></div>
      <p>{source.notice}</p>
      <HairSourceEditor source={source.source_png} width={source.source.width} height={source.source.height} value={mask} onChange={edit} disabled={locked}/>
      <button type="button" disabled={locked||!context||(!mask.objects.length&&kind==='support')} onClick={()=>{if(context)void work(()=>port.call<HairPreview>(`preview_${kind}`,context,{mask}),value=>{setPreview(value);setReviewed(false);});}}>生成审核图</button>
      {preview&&<div><img className="hair-overlay" src={preview.overlay_png} alt={kind==='support'?'真实头发证据与人工范围相交的源图审核':'仅本项效果恢复范围审核'}/>
        <p>{preview.notice} 当前范围 {preview.selected_pixels.toLocaleString()} 个预览源像素。</p>
        <label><input type="checkbox" disabled={locked} checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/>{kind==='support'?'我已检查完整源图，青色范围只包含所选人物的头发，没有相邻人物。':'我确认只擦回此人物的发色/光泽，不覆盖其他编辑。'}</label>
        <button type="button" disabled={locked||!reviewed||!context} onClick={()=>{if(context)void work(()=>port.call(`commit_${kind}`,context,{preview_id:preview.preview_id,confirmed:true}),()=>{setSource(null);setPreview(null);});}}>确认并应用</button></div>}
      <button type="button" disabled={locked||!context||kind==='support'&&(recipe.strength>0||recipe.gloss>0)} onClick={()=>{if(context)void work(()=>port.call(`clear_${kind}`,context,{}),()=>{setSource(null);setPreview(null);});}}>{kind==='support'?'移除此人物头发范围（需先重置效果）':'清除本项恢复笔迹'}</button>
      {source.facts&&<p>上次渲染：{source.facts.applied?'已产生像素变化':source.facts.reason??'未应用'}；变化 {source.facts.changed_pixels.toLocaleString()} 像素，已有高光证据 {source.facts.highlight_pixels.toLocaleString()} 像素。{source.facts.limitation}</p>}
    </div>}
    {(error||recipeError)&&<p role="alert">{error||recipeError}</p>}
    {receipt.message&&receipt.message!==error&&<p role="status">{receipt.message}</p>}
    {!receipt.pending&&receipt.message.includes('刷新失败')&&<button type="button" disabled={waiting||busy} onClick={()=>void work(refresh,()=>undefined)}>刷新照片状态，不重发修改</button>}
    <p>本项不包含发色统一、发量/发际线、发缝填充、祛碎发或祛白发。</p>
  </section>;
}
