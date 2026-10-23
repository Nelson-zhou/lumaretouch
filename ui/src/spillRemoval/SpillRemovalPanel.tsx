import {useEffect,useRef,useState} from 'react';
import type {LocalMaskReport} from '../localMasks/model';
import {MASK_LABELS} from '../localMasks/model';
import type {Report} from '../idBackground/model';
import {control} from '../idBackground/model';
import {manualSpillObject,spillApplyFields,spillReviewKey,validSpillPreviewFields,type SpillReview,type SpillParameters} from './model';
import {SpillPixelReview} from './SpillPixelReview';
import './spillRemoval.css';

type Props={documentId:string;report:Report|null;review:SpillReview|null;masks?:LocalMaskReport;disabled:boolean;request:(action:string,fields?:Record<string,unknown>)=>Promise<void>;invalidate:()=>void};
export function SpillRemovalPanel({documentId,report,review,masks,disabled,request,invalidate}:Props){
 const stored=report?.recipe.version===2?report.recipe.spill:null;
 const [parameters,setParameters]=useState<SpillParameters>({enabled:stored?.enabled??false,strength:stored?.strength??50});
 const [coverage,setCoverage]=useState<'retain'|'automatic'|'manual'>('retain'),[ids,setIds]=useState<string[]>([]),[coverageReviewed,setCoverageReviewed]=useState(false),[readyKey,setReadyKey]=useState<string|null>(null);
 const fenceKey=JSON.stringify([documentId,report?.recipe_document_id,report?.recipe_revision]),fenceRef=useRef(fenceKey);fenceRef.current=fenceKey;
 const masksKey=JSON.stringify(masks?.recipe??null),priorMasks=useRef(masksKey);
 useEffect(()=>{setParameters({enabled:stored?.enabled??false,strength:stored?.strength??50});setCoverage('retain');setIds([]);setCoverageReviewed(false);setReadyKey(null);},[fenceKey]);
 useEffect(()=>{if(priorMasks.current!==masksKey){priorMasks.current=masksKey;setIds([]);setCoverageReviewed(false);setReadyKey(null);invalidate();}},[masksKey]);
 const supported=report?.spill_protocol===1&&report.spill_available===true;
 const active=!!report?.recipe.enabled&&report.recipe.opacity>0&&report.recipe.background.kind!=='none'&&!!report.recipe.support[report.recipe.selected_support]&&report.available;
 const locked=disabled||!supported,choices=masks?.suspended?[]:masks?.recipe.objects.filter(manualSpillObject)??[];
 const key=review?spillReviewKey(review):null;
 const invalidateDraft=()=>{setReadyKey(null);invalidate();};
 const edit=(patch:Partial<SpillParameters>)=>{invalidateDraft();setParameters(previous=>({...previous,...patch}));};
 const fields={parameters,coverage_ids:coverage==='retain'?null:coverage==='automatic'?[]:ids,coverage_reviewed:coverage==='manual'&&coverageReviewed};
 const valid=validSpillPreviewFields(fields)&&(coverage!=='manual'||ids.length>0&&ids.every(id=>choices.some(choice=>choice.id===id)));
 return <section className="spillRemovalPanel" aria-label="背景反光祛染" data-control-id={control('e999ab085a')}>
  <h4>背景反光祛染</h4><p>独立调节背景颜色污染的抑制程度。当前原图或创意回流图都使用自己的来源与审核范围，不借用另一张照片的蒙版。</p>
  {!supported&&<p role="status">当前引擎未提供经审核的祛染处理。若处理库缺失且旧祛染已启用，无法生成可信前后图；可先清除背景选择以停用整条背景处理，或恢复处理库后再审核。</p>}
  <fieldset disabled={locked}><legend>独立祛染草稿</legend>
   <label><input type="checkbox" checked={parameters.enabled} disabled={!active&&!parameters.enabled} onChange={event=>edit({enabled:event.target.checked})}/>启用背景反光祛染</label>
   {!active&&<small>启用前请先应用不透明度大于零的背景替换，并审核当前选中的主体保留范围。</small>}
   <label>祛染程度<input type="range" min={0} max={100} step={1} value={parameters.strength} onChange={event=>edit({strength:Number(event.target.value)})}/><input type="number" aria-label="祛染程度数值" min={0} max={100} step={1} value={parameters.strength} onChange={event=>{const n=event.target.valueAsNumber;if(Number.isFinite(n)&&n>=0&&n<=100)edit({strength:n});}}/></label>
   <fieldset data-control-id={control('4bc238dfa1')}><legend>手工覆盖范围</legend>
    <label><input type="radio" name={`spill-coverage-${documentId}`} checked={coverage==='retain'} onChange={()=>{invalidateDraft();setCoverage('retain');setCoverageReviewed(false);}}/>保留当前范围 · {stored?.coverage?'已审核手工快照':'自动候选范围'}</label>
    <label><input type="radio" name={`spill-coverage-${documentId}`} checked={coverage==='automatic'} onChange={()=>{invalidateDraft();setCoverage('automatic');setCoverageReviewed(false);}}/>使用自动候选范围，清除已保存的手工覆盖</label>
    <label><input type="radio" name={`spill-coverage-${documentId}`} checked={coverage==='manual'} onChange={()=>{invalidateDraft();setCoverage('manual');setCoverageReviewed(false);}}/>选择当前源图中已绘制的手工蒙版</label>
    {coverage==='manual'&&<><p>先在现有局部蒙版源图编辑器绘制并检查画笔、线性或径向对象，再选择全部需要的对象。此处保存独立快照，不传入其他照片、AI 提示或颜色范围选区。</p>
     {choices.length?choices.map(mask=><label key={mask.id}><input type="checkbox" checked={ids.includes(mask.id)} onChange={event=>{invalidateDraft();setIds(previous=>event.target.checked?[...previous,mask.id]:previous.filter(id=>id!==mask.id));setCoverageReviewed(false);}}/>{mask.name} · {MASK_LABELS[mask.kind]}</label>):<p>尚无可用的源图手工对象，请先在局部蒙版编辑器绘制。</p>}
     <label><input type="checkbox" checked={coverageReviewed} disabled={!ids.length} onChange={event=>{invalidateDraft();setCoverageReviewed(event.target.checked);}}/>我已在当前源图中审核这些对象的祛染覆盖范围</label>
    </>}
   </fieldset>
   <button type="button" disabled={!valid||parameters.enabled&&!active} onClick={()=>{invalidateDraft();void request('id_spill_preview',fields);}}>生成真实前后审核（不应用）</button>
  </fieldset>
  {review&&key&&<><SpillPixelReview key={key} value={review} reviewKey={key} onReady={(reviewKey,ready)=>setReadyKey(previous=>ready?reviewKey:previous===reviewKey?null:previous)}/>
   <button type="button" disabled={locked||readyKey!==key} onClick={()=>{if(readyKey!==key||fenceRef.current!==fenceKey)return;setReadyKey(null);void request('id_spill_apply',spillApplyFields(review));}}>应用这次已审核的祛染结果</button>
  </>}
  <small>祛染是有界的颜色污染估计，不保证修复所有反光，也不恢复已经丢失的原始颜色。关闭或改变程度同样先审核再提交。</small>
 </section>;
}
