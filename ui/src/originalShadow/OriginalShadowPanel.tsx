import {useEffect,useRef,useState} from 'react';
import type {LocalMaskReport} from '../localMasks/model';
import {MASK_LABELS} from '../localMasks/model';
import {control,type Report} from '../idBackground/model';
import {originalShadowApplyFields,originalShadowManualObject,originalShadowReviewKey,originalShadowSubjectEligible,validOriginalShadowPreviewFields,type OriginalShadowBinding,type OriginalShadowParameters,type OriginalShadowPreviewFields,type OriginalShadowReview} from './model';
import type {SpillStroke} from '../spillRemoval/model';
import {OriginalShadowSourcePaint} from './OriginalShadowSourcePaint';
import {originalShadowPaintSourceKey} from './model';
import {OriginalShadowPixelReview} from './OriginalShadowPixelReview';
import './originalShadow.css';

type Props={documentId:string;report:Report|null;review:OriginalShadowReview|null;masks?:LocalMaskReport;disabled:boolean;request:(action:string,fields?:Record<string,unknown>)=>Promise<void>;invalidate:()=>void};
type Selection={mode:'retain'|'manual';ids:string[];reviewed:boolean};
const initialSelection=(binding:OriginalShadowBinding|null|undefined):Selection=>({mode:binding?'retain':'manual',ids:[],reviewed:false});
const bindingIds=(binding:OriginalShadowBinding|null|undefined):string[]=>binding?.mask.recipe.objects.map(object=>object.id)??[];

export function OriginalShadowPanel({documentId,report,review,masks,disabled,request,invalidate}:Props){
 const stored=report?.recipe.version===3?report.recipe.original_shadow:null;
 const [parameters,setParameters]=useState<OriginalShadowParameters>({enabled:stored?.enabled??false,strength:stored?.strength??100,blend:stored?.blend??'normal'});
 const [lit,setLit]=useState<Selection>(()=>initialSelection(stored?.lit_floor)),[retention,setRetention]=useState<Selection>(()=>initialSelection(stored?.retention));
 const [direct,setDirect]=useState(false),[litStrokes,setLitStrokes]=useState<SpillStroke[]>([]),[retentionStrokes,setRetentionStrokes]=useState<SpillStroke[]>([]),[paintReady,setPaintReady]=useState({lit:false,retention:false}),[paintReviewed,setPaintReviewed]=useState(false),[sourceInvalid,setSourceInvalid]=useState(false);
 const paintSource=report?.shadow_paint_source,sourceKey=paintSource?originalShadowPaintSourceKey(paintSource):null;
 const [uniformFloor,setUniformFloor]=useState(stored?.uniform_floor_confirmed??false),[readyKey,setReadyKey]=useState<string|null>(null);
 const fenceKey=JSON.stringify([documentId,report?.recipe_document_id,report?.recipe_revision]),fenceRef=useRef(fenceKey);fenceRef.current=fenceKey;
 const masksKey=JSON.stringify([masks?.suspended,masks?.recipe??null]),priorMasks=useRef(masksKey);
 useEffect(()=>{
  setParameters({enabled:stored?.enabled??false,strength:stored?.strength??100,blend:stored?.blend??'normal'});
  setDirect(false);setLitStrokes([]);setRetentionStrokes([]);setPaintReady({lit:false,retention:false});setPaintReviewed(false);setSourceInvalid(false);setLit(initialSelection(stored?.lit_floor));setRetention(initialSelection(stored?.retention));setUniformFloor(stored?.uniform_floor_confirmed??false);setReadyKey(null);
 },[fenceKey]);
 useEffect(()=>{setLitStrokes([]);setRetentionStrokes([]);setPaintReady({lit:false,retention:false});setPaintReviewed(false);setSourceInvalid(false);},[sourceKey]);
 useEffect(()=>{if(priorMasks.current!==masksKey){
  setLitStrokes([]);setRetentionStrokes([]);setPaintReady({lit:false,retention:false});setPaintReviewed(false);setSourceInvalid(true);
  priorMasks.current=masksKey;setLit(value=>({...value,ids:[],reviewed:false}));setRetention(value=>({...value,ids:[],reviewed:false}));setReadyKey(null);invalidate();
 }},[masksKey]);
 const supported=report?.original_shadow_protocol===1&&report.original_shadow_available===true;
 // An inactive parent has no original-shadow pixels to render. This narrow escape
 // can disable retained intent without pretending the missing kernel is available.
 const disableOnly=report?.original_shadow_protocol===1&&report.original_shadow_available===false
  &&(!report.recipe.enabled||report.recipe.opacity===0)&&stored!==null;
 const activeBackground=!!report?.recipe.enabled&&report.recipe.opacity>0&&report.recipe.background.kind!=='none'&&!!report.recipe.support[report.recipe.selected_support]&&report.available;
 const subjectSelected=report?.recipe.selected_support==='subject'&&originalShadowSubjectEligible(report.recipe.support.subject);
 const projectedActive=!!report&&report.recipe.shadow.kind!=='none'&&report.recipe.shadow.opacity>0;
 const locked=disabled||!supported&&!disableOnly,choices=masks?.suspended?[]:masks?.recipe.objects.filter(originalShadowManualObject)??[];
 const selectedLit=lit.mode==='retain'?bindingIds(stored?.lit_floor):lit.ids,selectedRetention=retention.mode==='retain'?bindingIds(stored?.retention):retention.ids;
 const overlap=selectedLit.some(id=>selectedRetention.includes(id));
 const invalidObjects=(selection:Selection)=>selection.mode==='manual'&&(!selection.ids.length||!selection.ids.every(id=>choices.some(choice=>choice.id===id)));
 const replacing=lit.mode==='manual'||retention.mode==='manual';
 const fields:OriginalShadowPreviewFields=direct?{parameters,lit_ids:null,retention_ids:null,samples_reviewed:paintReviewed,uniform_floor_confirmed:uniformFloor,...(paintSource?{paint:{token:paintSource.token,lit_strokes:litStrokes,retention_strokes:retentionStrokes}}:{})}:{parameters,lit_ids:lit.mode==='retain'?null:lit.ids,retention_ids:retention.mode==='retain'?null:retention.ids,
  samples_reviewed:replacing&&(lit.mode==='retain'||lit.reviewed)&&(retention.mode==='retain'||retention.reviewed),uniform_floor_confirmed:uniformFloor};
 const valid=validOriginalShadowPreviewFields(fields)&&(direct?!!paintSource&&!sourceInvalid&&paintReady.lit&&paintReady.retention&&paintReviewed&&litStrokes.length+retentionStrokes.length>0:!invalidObjects(lit)&&!invalidObjects(retention)&&!overlap)
  &&(!disableOnly||!parameters.enabled&&parameters.strength===stored?.strength&&parameters.blend===stored?.blend&&lit.mode==='retain'&&retention.mode==='retain'&&uniformFloor===stored?.uniform_floor_confirmed)
  &&(!parameters.enabled||activeBackground&&(direct?!!stored?.lit_floor||litStrokes.some(stroke=>stroke.mode==='restore'):selectedLit.length>0)&&(direct?!!stored?.retention||retentionStrokes.some(stroke=>stroke.mode==='restore'):selectedRetention.length>0))
  &&(!parameters.enabled||parameters.strength===0||subjectSelected&&!projectedActive);
 const key=review?originalShadowReviewKey(review):null;
 const invalidateDraft=()=>{setReadyKey(null);invalidate();};
 const edit=(patch:Partial<OriginalShadowParameters>)=>{invalidateDraft();setParameters(value=>({...value,...patch}));};
 function selectGroup(role:'lit'|'retention',patch:Partial<Selection>){
  invalidateDraft();const update=role==='lit'?setLit:setRetention;update(value=>({...value,...patch}));
 }
 function group(role:'lit'|'retention',selection:Selection,binding:OriginalShadowBinding|null|undefined){
  const opposite=role==='lit'?selectedRetention:selectedLit,title=role==='lit'?'无阴影明亮地面样本':'原图阴影保留范围';
  return <fieldset disabled={disableOnly} data-control-id={role==='retention'?control('0513155f3d'):undefined}><legend>{title}</legend>
   <label><input type="radio" name={`original-shadow-${role}-${documentId}`} checked={selection.mode==='retain'} onChange={()=>selectGroup(role,{mode:'retain',reviewed:false})}/>保留本照片已审核快照 · {binding?`${binding.mask.recipe.objects.length} 个独立对象`:'尚未保存'}</label>
   <label><input type="radio" name={`original-shadow-${role}-${documentId}`} checked={selection.mode==='manual'} onChange={()=>selectGroup(role,{mode:'manual',reviewed:false})}/>选择当前源图局部蒙版编辑器中的手工对象</label>
   {selection.mode==='manual'&&<>
    <p>{role==='lit'?'在现有源图蒙版编辑器，用画笔、线性或径向对象标出同一地面上无阴影、无污渍的明亮样本。不要包含人物、反光或高光。':'在现有源图蒙版编辑器，另画一组对象限制原阴影可保留的位置与边缘。这里选择已保存对象，不是新的直接涂抹工具。'}</p>
    {choices.length?choices.map(mask=><label key={mask.id}><input type="checkbox" checked={selection.ids.includes(mask.id)} disabled={opposite.includes(mask.id)&&!selection.ids.includes(mask.id)}
     onChange={event=>selectGroup(role,{ids:event.target.checked?[...selection.ids,mask.id]:selection.ids.filter(id=>id!==mask.id),reviewed:false})}/>{mask.name} · {MASK_LABELS[mask.kind]}{opposite.includes(mask.id)?'（已用于另一组）':''}</label>):<p>尚无当前源图可用的手工对象。请先在局部蒙版工具绘制、审核并保存。</p>}
    <label><input type="checkbox" disabled={!selection.ids.length||invalidObjects(selection)||overlap} checked={selection.reviewed} onChange={event=>selectGroup(role,{reviewed:event.target.checked})}/>我已在当前源图中查看并审核{title}的这些对象</label>
   </>}
  </fieldset>;
 }
 return <section className="originalShadowPanel" aria-label="原图阴影" data-control-id={control('442ced0175')}>
  <h4>原图阴影</h4>
  <p>手工辅助保留照片已拍到的阴影，独立于“增加二维设计阴影”。当前方法从均匀漫反射地面样本估计标量照明衰减，不复制旧地面 RGB，也不是 AI 阴影分离。</p>
  <label data-control-id={control('ab010073e3')}><input type="checkbox" disabled checked={false} readOnly/>AI 保留阴影：不可用，尚无经核验的模型权重与推理后端</label>
  {!supported&&<p role="status">{disableOnly?'原图阴影处理库不可用，但背景路径已停用。现在仅可审核关闭已保留意图，或审核清除两组样本并重置原图阴影；其他设置冻结。前后图仍须真实渲染、核验并由你确认。':'当前引擎未提供经审核的手工原图阴影处理。若已有原阴影导致无法渲染，可先用“清除背景选择”停用整个背景路径，再核对能否审核关闭保留意图；这里不会自动改写照片或下载模型。'}</p>}
  <fieldset disabled={locked}><legend>手工辅助原图阴影草稿</legend>
   <label><input type="checkbox" checked={parameters.enabled} disabled={(!activeBackground||!subjectSelected)&&!parameters.enabled} onChange={event=>edit({enabled:event.target.checked})}/>启用手工辅助原图阴影</label>
   {!activeBackground&&!disableOnly&&<small>先应用不透明度大于零、具有独立审核主体范围的背景替换，再启用本处理。</small>}
   {!subjectSelected&&<p className="originalShadowWarning">原图阴影需要已应用的“主体”保留类别，且该主体范围全部由源图手工画笔、线性或径向对象构成。提示模型、语义或颜色/亮度范围不能充当本方法的完整源图主体证据。请先在局部蒙版编辑器绘制并独立审核主体；若已有原图阴影，先关闭并审核它，再修改主体范围。</p>}
   {projectedActive&&<p className="originalShadowWarning">当前增加阴影已开启。非零原图阴影与增加阴影互斥，须先将增加阴影关闭并应用背景配方；这里不会替你改动它。</p>}
   <label data-control-id={control('48553e2d03')}>程度<input type="range" disabled={disableOnly} min={0} max={100} step={1} value={parameters.strength} onChange={event=>edit({strength:Number(event.target.value)})}/><input type="number" disabled={disableOnly} aria-label="原图阴影程度数值" min={0} max={100} step={1} value={parameters.strength} onChange={event=>{const strength=event.target.valueAsNumber;if(Number.isFinite(strength)&&strength>=0&&strength<=100)edit({strength});}}/></label>
   <small>程度 0–100、步长 1、初始 100 是本实现的选择，不是官方公开参数，也未作照片质量验收。</small>
   <fieldset disabled={disableOnly}><legend>混合方式</legend>{(['normal','multiply','softlight'] as const).map((blend,index)=><label key={blend} data-control-id={control(['c959928d7a','b1b766d4ce','9e1c732ff8'][index])}>
    <input type="radio" name={`original-shadow-blend-${documentId}`} checked={parameters.blend===blend} onChange={()=>edit({blend})}/>{['正常','正片叠底','柔光（艺术效果）'][index]}</label>)}
    <small>本算法使用黑色照明层，正常与正片叠底结果相同。柔光是艺术混合，不是物理照明恢复。</small>
   </fieldset>
   <label><input type="checkbox" disabled={disableOnly} checked={direct} onChange={event=>{invalidateDraft();setDirect(event.target.checked);setPaintReviewed(false);}}/>直接在完整源图画布上编辑两组范围</label>
   {direct?<>
    <button type="button" onClick={()=>{invalidateDraft();setPaintReviewed(false);setPaintReady({lit:false,retention:false});setSourceInvalid(true);setLitStrokes([]);setRetentionStrokes([]);void request('id_original_shadow_paint_source');}}>{paintSource?'重新读取源图并丢弃两组本次笔画':'读取当前不可变源图与两组范围'}</button>
    {paintSource&&!sourceInvalid&&(['lit','retention'] as const).map(role=><OriginalShadowSourcePaint key={`${sourceKey}-${role}`} title={role==='lit'?'无阴影明亮地面样本':'原图阴影保留范围'}
     source={{version:1,token:paintSource.token,recipe_document_id:paintSource.recipe_document_id,recipe_revision:paintSource.recipe_revision,source:paintSource.source,domain:paintSource.domain,image:paintSource.image,coverage:role==='lit'?paintSource.lit_floor:paintSource.retention}}
     strokes={role==='lit'?litStrokes:retentionStrokes} disabled={locked||disableOnly}
     onChange={strokes=>{invalidateDraft();setPaintReviewed(false);(role==='lit'?setLitStrokes:setRetentionStrokes)(strokes);}}
     onGestureStart={()=>{invalidateDraft();setPaintReviewed(false);}}
     onReady={ready=>{setPaintReady(previous=>previous[role]===ready?previous:{...previous,[role]:ready});if(!ready){setPaintReviewed(false);setReadyKey(null);}}}/>)}
    <label><input type="checkbox" checked={paintReviewed} disabled={sourceInvalid||!paintReady.lit||!paintReady.retention||!litStrokes.length&&!retentionStrokes.length} onChange={event=>{invalidateDraft();setPaintReviewed(event.target.checked);}}/>我已在当前完整源图核对两组范围；明亮地面样本不含人物、反光、高光或阴影</label>
    <small>两组笔画独立保留于此照片。重叠处不会用于明亮地面估计；颜色相似的污渍仍可能无法识别。没有已保存范围时从空白开始。</small>
   </>:<>{group('lit',lit,stored?.lit_floor)}{group('retention',retention,stored?.retention)}</>}
   {!direct&&overlap&&<p role="alert">明亮样本与保留范围必须使用不同对象，不能复用另一组的对象 ID。请修改选择或另画对象。</p>}
   <label><input type="checkbox" disabled={disableOnly} checked={uniformFloor} onChange={event=>{invalidateDraft();setUniformFloor(event.target.checked);}}/>我确认两组选区来自同一均匀、同材质的漫反射地面，并已排除纹理、污渍、反射及变化照明</label>
   <p>同色污渍与纹理无法可靠区分为阴影。深色、反光、花纹地面、多重或彩色光照不适用；不能保证脚部接触与半影都被准确保留。</p>
   <button type="button" disabled={!valid} onClick={()=>{invalidateDraft();void request('id_original_shadow_preview',fields);}}>生成真实原图阴影前后审核（不应用）</button>
  </fieldset>
  <button type="button" disabled={locked} onClick={()=>{invalidateDraft();void request('id_original_shadow_preview',{parameters:{enabled:false,strength:100,blend:'normal'},lit_ids:null,retention_ids:null,samples_reviewed:false,uniform_floor_confirmed:false,clear_samples:true});}}>审核清除两组样本并重置原图阴影（尚不应用）</button>
  <small>清除会将原图阴影关闭、程度恢复为 100、混合恢复正常并移除两组已保存快照；只在核验前后图并应用后写入，可通过统一历史撤销。</small>
  {review&&key&&<><OriginalShadowPixelReview key={key} value={review} reviewKey={key} disabled={locked} onReady={(reviewKey,ready)=>setReadyKey(previous=>ready?reviewKey:previous===reviewKey?null:previous)}/>
   <button type="button" disabled={locked||readyKey!==key} onClick={()=>{if(readyKey!==key||fenceRef.current!==fenceKey)return;setReadyKey(null);void request('id_original_shadow_apply',originalShadowApplyFields(review));}}>应用这次已审核的原图阴影结果</button>
  </>}
  <small>两个范围分别绑定当前不可变源图。原照片与创意回流照片必须各自绘制和审核，不能跨照片复制蒙版。关闭、程度为零与混合变化也须审核后提交；进入此面板不会自动写入。</small>
 </section>;
}
