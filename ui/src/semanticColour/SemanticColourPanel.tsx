import {useEffect,useRef,useState} from 'react';
import type {SelectedSampleReference} from '../sampleLibrary/model';
import {CanvasMaskEditor} from './CanvasMaskEditor';
import {useSemanticColour} from './useSemanticColour';
import {BAND_NAMES,KNOTS,PARAMETER_LABELS,bounds,type CanvasMask,type Group,type Mode,type Port} from './model';
import './semanticColour.css';

function PreciseGroup({group,busy,onSave,onReset}:{group:Group;busy:boolean;onSave:(parameters:number[])=>void;onReset:()=>void}){
 const [values,setValues]=useState(group.parameters),[channel,setChannel]=useState(0);
 useEffect(()=>setValues([...group.parameters]),[group.id,group.parameters]);
 const set=(i:number,v:number)=>setValues(p=>p.map((old,j)=>i===j?v:old));
 const input=(i:number)=>{const [min,max,step]=bounds(i);return <label key={i}>{PARAMETER_LABELS[i]}<input type="number" min={min} max={max} step={step} disabled={busy} value={values[i]} onChange={e=>set(i,Number(e.target.value))}/></label>;};
 return <div className="semantic-precise"><div className="semantic-values">{[0,1,2,3,4,5].map(input)}</div>
  <details open><summary>真实 PCHIP 曲线</summary><select aria-label="追色曲线通道" value={channel} onChange={e=>setChannel(Number(e.target.value))}>{['总曲线','红','绿','蓝'].map((v,i)=><option value={i} key={v}>{v}</option>)}</select>
   <svg className="semantic-curve" viewBox="0 0 240 160" role="img" aria-label="曲线控制点示意，实际输出使用 PCHIP 插值"><path d="M10 150L230 10" stroke="currentColor" opacity=".25"/>
    <polyline points={KNOTS.map((x,i)=>`${10+x*220},${150-values[6+channel*5+i]*140}`).join(' ')} fill="none" stroke="var(--semantic-accent)" strokeDasharray="4 3"/>
    {KNOTS.map((x,i)=><circle key={i} cx={10+x*220} cy={150-values[6+channel*5+i]*140} r="4" fill="var(--semantic-accent)"/>)}</svg>
   <div className="semantic-values">{KNOTS.map((_,i)=>input(6+channel*5+i))}</div><small>点线仅标示五个控制点；渲染复用产品的 PCHIP 数学。自动估计保持单调，手动可有意调整为非单调。</small>
  </details>
  <details><summary>八色分段（兼容 HSV）</summary><p>非中性沿用原有 SDR HSV 分段与 0–1 夹域，不是 HDR HSL。</p>{BAND_NAMES.map((name,i)=><div className="semantic-band" key={name}><strong>{name}</strong>{[26+i*3,27+i*3,28+i*3].map(input)}</div>)}</details>
  <button disabled={busy||values.some((v,i)=>!Number.isFinite(v)||v<bounds(i)[0]||v>bounds(i)[1])} onClick={()=>onSave(values)}>应用此组编辑</button>
  <button disabled={busy} onClick={onReset}>还原此组 AI 估计</button><small>只编辑 AI 追色自有组；不会覆盖已有手动曝光、白平衡、曲线或 HSL。</small>
 </div>;
}

export function SemanticColourPanel({port,documentKey,refreshKey,selectedSample,onChanged}:{port:Port;documentKey:string;refreshKey?:string;selectedSample:SelectedSampleReference|null;onChanged:()=>void}){
 const flow=useSemanticColour(port,documentKey,onChanged);
 useEffect(()=>{if(refreshKey!==undefined)void flow.refresh().catch(()=>{});},[refreshKey,flow.refresh]);
 const [mode,setMode]=useState<Mode>('harmonious'),[local,setLocal]=useState(false),[precise,setPrecise]=useState(false),[strengths,setStrengths]=useState([100,100,100]);
 const [referenceMask,setReferenceMask]=useState<CanvasMask|null>(null),[targetMask,setTargetMask]=useState<CanvasMask|null>(null),[reviewed,setReviewed]=useState(false),[maskEdit,setMaskEdit]=useState<string|null>(null),[editingMask,setEditingMask]=useState<CanvasMask|null>(null),[maskOverlay,setMaskOverlay]=useState<string|undefined>(),[maskError,setMaskError]=useState('');
 const overlayTicket=useRef(0);
 const showMask=async(mask:CanvasMask)=>{const ticket=++overlayTicket.current;setMaskOverlay(undefined);setMaskError('');try{const result=await port.request('mask_overlay',{mask_id:mask.id,objects:mask.objects}) as {image:string};if(ticket===overlayTicket.current)setMaskOverlay(result.image);}catch(error){if(ticket===overlayTicket.current)setMaskError(String(error));}};
 const busy=['capturing','running','committing','editing'].includes(flow.phase);
 useEffect(()=>{setReferenceMask(flow.capture?.reference_selection??null);setTargetMask(flow.capture?.target_selection??null);setReviewed(false);},[flow.capture]);
 useEffect(()=>{setReviewed(false);},[flow.review?.proof]);
 useEffect(()=>{if(flow.report?.recipe){setStrengths([...flow.report.recipe.strengths]);setMode(flow.report.recipe.mode);}},[flow.report]);
 useEffect(()=>{overlayTicket.current++;setMaskEdit(null);setEditingMask(null);setMaskOverlay(undefined);return()=>{overlayTicket.current++;};},[documentKey]);
 const reference=selectedSample?{source:selectedSample.source,render_sha256:selectedSample.render_sha256,asset_id:selectedSample.asset_id}:null;
 const previousSample=useRef(selectedSample?.asset_id);
 useEffect(()=>{if(previousSample.current!==selectedSample?.asset_id){previousSample.current=selectedSample?.asset_id;void flow.cancel();}},[selectedSample?.asset_id,flow.cancel]);
 const recipe=flow.report?.recipe;
 return <section className="semantic-colour-panel" data-control-id="PC-32452-C-fbe73f0159" aria-label="AI 语义追色">
  <div className="semantic-title"><strong>AI 语义追色</strong><span>开源分割 + Rust 参数优化</span></div>
  <p>按真实语义类别比较样片与目标颜色，生成可继续修改的全图及局部参数。不会生成纹理或改变构图。</p>
  <p className="semantic-warning">本功能源码已接入不等于画质验收：推理、耗时、全幅导出和真实人像质量仍待本地验证。</p>
  {!selectedSample&&<p>请先在本地样片库选择一张自己的参考样片。</p>}
  <div className="semantic-toolbar"><button disabled={!reference||!flow.context||busy} onClick={()=>reference&&flow.freeze(reference)}>冻结当前双图</button>
   {(flow.capture||busy)&&<button disabled={flow.phase==='committing'} onClick={()=>void flow.cancel()}>关闭 / 取消待处理结果</button>}
   <button data-control-id={precise?"PC-32452-C-6bc7d19de9":"PC-32452-C-a8bb7fedf1"} onClick={()=>setPrecise(v=>!v)} aria-pressed={precise}>{precise?'切到快速视图':'精准视图'}</button></div>
  <div className="semantic-toolbar"><label data-control-id="PC-32452-C-22025a98c5">优化模式 <select disabled={busy} value={mode} onChange={e=>setMode(e.target.value as Mode)}><option data-control-id="PC-32452-C-526ef81feb" value="harmonious">和谐：较强原片保护</option><option data-control-id="PC-32452-C-633b863a30" value="extreme">极致：较强颜色匹配</option></select></label>
   <label data-control-id="PC-32452-C-a6bb17749a"><input type="checkbox" checked={local} disabled={busy} onChange={e=>setLocal(e.target.checked)}/>局部双图选择</label></div>
  <small>两个模式是同一真实后端的正则化策略，不是两个虚构训练模型。改变模式后需重新分析，不会在滑块拖动时自动重跑。</small>
  {['整体','影调','色彩'].map((label,i)=><label className="semantic-strength" data-control-id={`PC-32452-C-${["765234dfde","ba031c1bf1","fc758fb168"][i]}`} key={label}>{label}<input type="range" min="0" max="200" step="1" disabled={busy} value={strengths[i]} onChange={e=>setStrengths(v=>v.map((old,j)=>i===j?Number(e.target.value):old))}/><output>{strengths[i]}</output></label>)}
  {!!recipe?.groups.length&&<button disabled={busy} onClick={()=>flow.edit('strengths',strengths)}>更新三个程度（不重新拟合）</button>}
  {flow.capture&&<><p>{flow.capture.notice}</p>{local&&referenceMask&&targetMask?<div className="semantic-dual">
   <CanvasMaskEditor title="样片自己的选区" image={flow.capture.reference.image} mask={referenceMask} onChange={setReferenceMask} disabled={busy}/>
   <CanvasMaskEditor title="目标自己的选区" image={flow.capture.target.image} mask={targetMask} onChange={setTargetMask} disabled={busy}/>
  </div>:<div className="semantic-dual semantic-images"><figure><img src={flow.capture.reference.image} alt="冻结参考样片"/><figcaption>参考样片</figcaption></figure><figure><img src={flow.capture.target.image} alt="冻结目标，保留现有手动编辑"/><figcaption>目标：保留已有编辑</figcaption></figure></div>}
  {local&&<p>两个选区各自绑定自己的画布。至少提供两图可用支持；局部模式不参加批量和预设。</p>}
  <button disabled={busy||flow.phase==='uncertain'||(local&&(!referenceMask?.objects.length||!targetMask?.objects.length))} onClick={()=>flow.start(mode,strengths,local?referenceMask:null,local?targetMask:null)}>开始语义分析与追色</button></>}
  {flow.phase==='running'&&<p role="status">正在对冻结双图进行真实语义分析和有界优化，可取消。不会修改当前编辑。</p>}
  {flow.phase==='capturing'&&<p role="status">正在冻结完整分辨率双图，未开始拟合。</p>}
  {flow.review&&<section className="semantic-review"><h4>检查后再应用</h4>
   {flow.preview&&<><div className="semantic-dual semantic-images"><figure><img src={flow.preview.before} alt="追色前采样检查图"/><figcaption>之前</figcaption></figure><figure><img src={flow.preview.after} alt="追色后采样检查图"/><figcaption>之后</figcaption></figure></div><small>{flow.preview.notice}</small></>}
   <p>留出颜色残差：{flow.review.diagnostics[0][0].toFixed(4)} → {flow.review.diagnostics[0][1].toFixed(4)}；采样越界占比 {(flow.review.diagnostics[0][4]*100).toFixed(2)}%。这不是摄影质量评分。</p>
   <details><summary>语义覆盖与限制</summary>{flow.review.coverage.target.map((r,i)=><p key={r.class}>{r.class}：目标 {r.usable_pixels}；样片 {flow.review!.coverage.reference[i].usable_pixels} 个支持点</p>)}<ul>{flow.review.warnings.map(w=><li key={w}>{w}</li>)}</ul></details>
   <label><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/>我已检查前后图、语义覆盖和限制</label>
   <button data-control-id="PC-32452-C-20622a1901" disabled={!reviewed||busy||flow.phase==='uncertain'} onClick={()=>void flow.commit()}>应用此冻结结果</button>
  </section>}
  {!flow.review&&recipe?.last_review&&<details><summary>上次 AI 初始估计的保留诊断</summary><p>颜色残差 {recipe.last_review.diagnostics[0][0].toFixed(4)} → {recipe.last_review.diagnostics[0][1].toFixed(4)}。这是已审核初始估计的记录，后续手动参数或蒙版编辑不会伪称重新拟合。</p><ul>{recipe.last_review.warnings.map(w=><li key={w}>{w}</li>)}</ul></details>}
  {flow.report?.suspended&&<p className="semantic-warning" role="alert">{flow.report.suspended}</p>}
  {!!recipe?.groups.length&&<section data-control-id="PC-32452-C-e84df35afd"><div className="semantic-toolbar"><label><input type="checkbox" checked={recipe.enabled} disabled={busy} onChange={e=>flow.edit('enabled',e.target.checked)}/>启用 AI 追色组</label><button data-control-id="PC-32452-C-a6f71ac905" disabled={busy} onClick={()=>flow.edit('reset',null)}>清除本次 AI 追色贡献</button></div>
   {recipe.groups.map(group=><details key={group.id} open={precise&&group.id==='global'}><summary>{group.name} {group.enabled?'':'（关闭）'}</summary>
    <div className="semantic-toolbar"><label><input type="checkbox" checked={group.enabled} disabled={busy} onChange={e=>flow.edit('group_enabled',{id:group.id,enabled:e.target.checked})}/>应用此组</label>
    {group.mask_id&&<><button disabled={busy||!!flow.report?.suspended} onClick={()=>{const mask=recipe.masks.find(m=>m.id===group.mask_id);if(mask){setMaskEdit(group.mask_id);setEditingMask(structuredClone(mask));void showMask(mask);if(!flow.capture&&recipe.reference)void flow.freeze(recipe.reference);}}}>编辑蒙版</button><button disabled={busy} onClick={()=>flow.edit('group_delete',{id:group.id})}>删除此局部组和蒙版</button></>}</div>
    {precise?<PreciseGroup group={group} busy={busy} onSave={parameters=>flow.edit('group_parameters',{id:group.id,parameters})} onReset={()=>flow.edit('group_reset',{id:group.id})}/>:<p>切到精准视图编辑曝光、通道增益、曲线和八色参数。快速/精准视图使用同一配方。</p>}
   </details>)}
  </section>}
  {maskEdit&&editingMask&&flow.capture&&<section><CanvasMaskEditor title={`编辑 ${editingMask.name}`} image={flow.capture.target.image} mask={editingMask} overlay={maskOverlay} onChange={m=>{overlayTicket.current++;setEditingMask(m);setMaskOverlay(undefined);}} disabled={busy}/><p>保留神经模型初选，手工标记在其后按顺序添加或擦除。</p><button disabled={busy} onClick={()=>void showMask(editingMask)}>查看实际合成蒙版</button>{maskError&&<p role="alert">{maskError}</p>}<button disabled={busy} onClick={()=>{void flow.edit('mask_objects',{id:maskEdit,objects:editingMask.objects});setMaskEdit(null);}}>保存蒙版编辑</button><button onClick={()=>{overlayTicket.current++;setMaskEdit(null);}}>放弃编辑</button></section>}
  {flow.error&&<p role="alert" className="semantic-warning">{flow.error}</p>}
  {flow.phase==='uncertain'&&<button onClick={()=>void flow.cancel()}>关闭待处理会话并核对当前结果</button>}
 </section>;
}
