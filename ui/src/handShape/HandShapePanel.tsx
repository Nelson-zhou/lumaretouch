// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useRef,useState} from 'react';
import {HandModelSetup} from './HandModelSetup';
import {HandShapeSupportEditor} from './HandShapeSupportEditor';
import {imageUrl,neutral,validImage,previewMatches,KIND_LABELS,type HandShapePort,type Reference,type Image,type PreviewPayload,type Region,type Kind,type Confirmations} from './model';
const flags={visible_only:'所有标记均在实际可见的手部，不补全隐藏关节或手指',ownership:'所有区域属于当前照片同一只手；不凭左右手分类确认人物',no_contact:'标记没有跨越交叠、接触、强透视压缩或不明确边界',transitions:'已检查完整过渡支持；背景或纹理可能随其移动',protection_reviewed:'已检查指甲、饰品、纹身、接触物与其他手部，必要处画保护框'};
const emptyFlags=()=>({visible_only:false,ownership:false,no_contact:false,transitions:false,protection_reviewed:false});
export function HandShapePanel({port,disabled=false}:{port:HandShapePort;disabled?:boolean}){
 const r=port.snapshot.reference;
 const valid=!!r&&r.protocol===1&&r.family==='hand_shape'&&validImage(r.source_image)&&r.source.width>=2&&r.source.height>=2&&Math.abs(r.source_image.width*r.source.height-r.source_image.height*r.source.width)<=Math.max(r.source.width,r.source.height);
 return <Editor key={`${port.snapshot.bindingKey}:${valid?r.reference_id:'none'}`} port={port} reference={valid?r:null} disabled={disabled}/>;
}
function ProofImage({image,label,onReady}:{image:Image;label:string;onReady:(ready:boolean)=>void}){return <figure style={{margin:0}}><figcaption>{label}</figcaption><img src={imageUrl(image)} alt={label} draggable={false} style={{display:'block',width:'100%',height:'auto'}} onLoad={e=>onReady(e.currentTarget.naturalWidth===image.width&&e.currentTarget.naturalHeight===image.height)} onError={()=>onReady(false)}/></figure>;}
function Editor({port,reference,disabled}:{port:HandShapePort;reference:Reference|null;disabled:boolean}){
 const {snapshot}=port;
 const [regions,setRegions]=useState<Region[]>([]),[protect,setProtect]=useState<[number,number,number,number][]>([]),[amounts,setAmounts]=useState(reference?.current_recipe?.amounts??neutral());
 const [handId]=useState(()=>crypto.randomUUID().replaceAll('-','')),[proposalId,setProposalId]=useState<string|null>(null),[checks,setChecks]=useState(emptyFlags);
 const [sourceReady,setSourceReady]=useState(false),[draftActive,setDraftActive]=useState(false),[reviewed,setReviewed]=useState(false),[loaded,setLoaded]=useState<Record<string,boolean>>({});
 const [localBusy,setLocalBusy]=useState(false),[error,setError]=useState('');const mounted=useRef(true),inFlight=useRef(false);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 const invalidate=()=>{setReviewed(false);setLoaded({});};
 const blocked=disabled||localBusy||snapshot.pending||snapshot.uncertain||snapshot.refreshRequired||!snapshot.bindingKey;
 const suggestions=reference&&snapshot.proposals?.reference_id===reference.reference_id&&snapshot.proposals.fence===reference.fence?snapshot.proposals.proposals:[];
 const proposal=suggestions.find(p=>p.proposal_id===proposalId)??null;
 const confirmed=Object.values(checks).every(Boolean);
 const request:PreviewPayload|null=reference&&confirmed&&sourceReady&&!draftActive&&regions.length>0&&(!proposalId||proposal)
  ?{reference_id:reference.reference_id,amounts,review:{version:1,domain:'source-normalized',hand_id:handId,regions,protect,proposal_id:proposalId,confirmed:checks as Confirmations}}:null;
 const preview=reference&&previewMatches(snapshot.preview,request,reference)?snapshot.preview.value:null;
 const key=preview?`${preview.preview_id}:${preview.candidate_sha256}`:'';
 const proofReady=!!preview&&['before','after','overlay'].every(k=>loaded[`${key}:${k}`]);
 const run=async(action:()=>Promise<void>)=>{if(blocked||inFlight.current)return;inFlight.current=true;setLocalBusy(true);setError('');try{await action();}catch(e){if(mounted.current)setError(String(e));}finally{inFlight.current=false;if(mounted.current)setLocalBusy(false);}};
 return <section aria-label="手部美型：独立可见手部几何" data-operation="lnx.hand_shape.v1" data-control-id="control:PC-46608:3">
  <strong>手部美型 · 可见轮廓辅助</strong>
  <p><small>分别调整手宽、手指和指节宽度，不是中性灰或祛青筋。支持独立手部照片，不要求身体骨架。当前每张照片仅支持一只手；所有形状区域必须手工测量及复核。模型只提供定位建议，缺失时明确使用手动模式。</small></p>
  <HandModelSetup disabled={blocked} onRefresh={()=>void run(port.reference)}/>
  <button type="button" disabled={blocked} onClick={()=>void run(port.reference)}>读取当前照片来源</button>
  {reference&&<>
   <button type="button" disabled={blocked||!sourceReady||!reference.model.available} onClick={()=>{setProposalId(null);setChecks(emptyFlags());invalidate();void run(()=>port.propose(reference.reference_id));}}>请求实际手部定位建议</button>
   {!reference.model.available&&<p role="status">手动支持模式：{reference.model.reason||'可选模型不可用，不伪造 AI 定位。'}</p>}
   {!!suggestions.length&&<label>定位建议（不代表可见或归属）<select value={proposalId??''} disabled={blocked} onChange={event=>{setProposalId(event.target.value||null);setChecks(emptyFlags());invalidate();}}><option value="">不使用定位建议 · 手动支持</option>{suggestions.map((p,i)=><option key={p.proposal_id} value={p.proposal_id}>候选 {i+1}</option>)}</select></label>}
   <HandShapeSupportEditor source={reference.source} image={reference.source_image} regions={regions} protect={protect} proposal={proposal} disabled={blocked} onReady={value=>{setSourceReady(value);if(!value)invalidate();}} onDraftActive={setDraftActive} onDraftStart={()=>{setChecks(emptyFlags());invalidate();}} onChange={(r,p)=>{setRegions(r);setProtect(p);setChecks(emptyFlags());invalidate();}}/>
   {(Object.keys(flags) as (keyof Confirmations)[]).map(k=><label key={k} style={{display:'block'}}><input type="checkbox" checked={checks[k]} disabled={blocked||draftActive||!sourceReady} onChange={e=>{setChecks(v=>({...v,[k]:e.target.checked}));invalidate();}}/>{flags[k]}</label>)}
   {(['palm','finger','joint'] as Kind[]).map(kind=><label key={kind} style={{display:'block'}}>{KIND_LABELS[kind]} <output>{Math.round(amounts[kind]*100)}</output><input type="range" min="-100" max="100" step="1" value={Math.round(amounts[kind]*100)} disabled={blocked||!regions.some(r=>r.kind===kind)} onChange={event=>{setAmounts(v=>({...v,[kind]:Number(event.target.value)/100}));invalidate();}}/></label>)}
   <p><small>负值变宽、0 不变、正值收窄。-100 至 100、1.8 倍过渡和保守约束是原创本地策略，不是手册披露参数。定位点不自动生成手型，不推断隐藏结构或理想形状。</small></p>
   <div className="prow"><button type="button" disabled={blocked||!request||!reference.capability.available} onClick={()=>{if(request){invalidate();void run(()=>port.preview(request));}}}>生成完整效果对比</button><button type="button" disabled={blocked} onClick={()=>{setAmounts(neutral());invalidate();}}>草稿强度归零</button><button type="button" disabled={blocked||!reference.current_recipe} onClick={()=>void run(port.clear)}>清除本照片手部美型</button></div>
   <p><small>定位建议仅在明确安装固定模型、验证完整字节并通过 CPU 能力检查后可用。未配置时使用手动轮廓支持，不称为 AI。</small></p>
   {!reference.capability.available&&<p role="status">{reference.capability.reason||'Rust 手型数值核心不可用，不回退为替代滤镜。'}</p>}
  </>}
  {preview&&<div key={key}><div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:8}}>{(['before','after','overlay'] as const).map(role=><ProofImage key={`${key}:${role}`} image={preview[role]} label={role==='before'?'修改前（完整合成）':role==='after'?'修改后（完整合成）':'实际源坐标几何支持与保护范围'} onReady={ready=>{setLoaded(old=>({...old,[`${key}:${role}`]:ready}));if(!ready)setReviewed(false);}}/>)}</div>
   <label><input type="checkbox" checked={reviewed} disabled={blocked||!proofReady} onChange={e=>setReviewed(e.target.checked)}/>已完整检查前后效果和范围，接受当前可见手部结构及背景过渡</label>
   <button type="button" disabled={blocked||!proofReady||!reviewed} onClick={()=>void run(()=>port.confirm({preview_id:preview.preview_id,reviewed:true,before_sha256:preview.before.sha256,after_sha256:preview.after.sha256,overlay_sha256:preview.overlay.sha256,candidate_sha256:preview.candidate_sha256}))}>确认应用</button>
  </div>}
  {snapshot.uncertain&&<p role="status">原请求结果未知，正在查询原回执；不会自动重发修改。</p>}
  {snapshot.refreshRequired&&<p role="status">正在同步规范文档状态，暂不接受新的修改。</p>}
  {(error||snapshot.message)&&<p role="status">{error||snapshot.message}</p>}
  <p><small>源码已编写；数值、真实照片自然度、性能及本机验收未运行。遮挡、接触或保护区域冲突会拒绝，不声称自动检测这些情况。</small></p>
 </section>;
}
