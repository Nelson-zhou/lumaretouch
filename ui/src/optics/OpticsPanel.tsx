import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import type {Guide,LensMetadata,OpticsRecipe,OpticsReport} from './model';
import type {OpticsOwner} from './useOpticsWorkflow';
import {useOutputPresentation} from './useOutputPresentation';
import './optics.css';
const LABELS:Record<string,string>={distortion:'畸变矫正',vignette:'暗角调节',midpoint:'中点',vertical:'垂直透视',horizontal:'水平透视',rotation:'旋转',aspect:'长宽比',scale:'缩放',offset_x:'水平偏移',offset_y:'垂直偏移'};
function GuideCanvas({source,width,height,guides,disabled,onChange,onLoad}:{source:string;width:number;height:number;guides:Guide[];disabled:boolean;onChange:(v:Guide[])=>void;onLoad:()=>void}){
  const [local,setLocal]=useState(guides),[axis,setAxis]=useState<Guide['axis']>('vertical');
  const drag=useRef<{index:number;endpoint:'start'|'end';pointer:number;newLine:boolean}|null>(null);
  useEffect(()=>{if(!drag.current)setLocal(guides);},[guides]);
  function point(e:React.PointerEvent<SVGSVGElement>):[number,number]{const b=e.currentTarget.getBoundingClientRect();return [Math.min(1,Math.max(0,(e.clientX-b.left)/b.width)),Math.min(1,Math.max(0,(e.clientY-b.top)/b.height))];}
  function down(e:React.PointerEvent<SVGSVGElement>){
    if(disabled||e.button!==0||drag.current)return;
    const p=point(e),target=e.target as Element,index=target.getAttribute('data-guide'),endpoint=target.getAttribute('data-end');
    if(index!==null&&(endpoint==='start'||endpoint==='end'))drag.current={index:Number(index),endpoint,pointer:e.pointerId,newLine:false};
    else{if(local.length>=4)return;const line:Guide={id:crypto.randomUUID().replaceAll('-',''),axis,start:p,end:p};drag.current={index:local.length,endpoint:'end',pointer:e.pointerId,newLine:true};setLocal([...local,line]);}
    e.currentTarget.setPointerCapture(e.pointerId);e.preventDefault();
  }
  function move(e:React.PointerEvent<SVGSVGElement>){const d=drag.current;if(!d||d.pointer!==e.pointerId)return;const p=point(e);setLocal(old=>old.map((g,i)=>i===d.index?{...g,[d.endpoint]:p}:g));}
  function end(e:React.PointerEvent<SVGSVGElement>,cancelled=false){const d=drag.current;if(!d||d.pointer!==e.pointerId)return;drag.current=null;
    if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);
    if(cancelled){setLocal(guides);return;}
    const p=point(e),next=local.map((g,i)=>i===d.index?{...g,[d.endpoint]:p}:g);
    const line=next[d.index];if(!line||Math.hypot(line.end[0]-line.start[0],line.end[1]-line.start[1])<.02){setLocal(guides);return;}
    setLocal(next);onChange(next);
  }
  return <div className="opticsGuideEditor"><label>新引导线方向 <select disabled={disabled} value={axis} onChange={e=>setAxis(e.target.value as Guide['axis'])}><option value="vertical">应当垂直</option><option value="horizontal">应当水平</option></select></label>
    <div className="opticsGuideImage" style={{aspectRatio:`${width}/${height}`}}><img src={source} width={width} height={height} alt="镜头校正后、透视与裁剪之前的真实参考画面，在此绘制引导线" onLoad={onLoad}/>
      <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" role="application" aria-label="透视引导线，可拖动端点" onPointerDown={down} onPointerMove={move} onPointerUp={e=>end(e)} onPointerCancel={e=>end(e,true)} onLostPointerCapture={()=>{if(drag.current){drag.current=null;setLocal(guides);}}}>
        {local.map((g,i)=><g key={g.id}><line x1={g.start[0]*1000} y1={g.start[1]*1000} x2={g.end[0]*1000} y2={g.end[1]*1000} stroke={g.axis==='vertical'?'#7ce8ff':'#ffc782'} strokeWidth="3"/>
          {(['start','end'] as const).map(end=><circle key={end} data-guide={i} data-end={end} cx={g[end][0]*1000} cy={g[end][1]*1000} r="10" fill="#fff" stroke="#111" strokeWidth="2"/>)}<text x={g.start[0]*1000+15} y={g.start[1]*1000+20}>{i+1}</text></g>)}
      </svg>
    </div>
    <small>在真实直边上按住拖动。第 2 条线松手即解算，最多 4 条；可拖动端点或删除。此处未应用透视和最终裁剪。</small>
    {local.map((g,i)=><div key={g.id} className="opticsGuideRow"><span>引导线 {i+1}</span><select aria-label={`引导线 ${i+1} 方向`} disabled={disabled} value={g.axis} onChange={e=>onChange(local.map((line,j)=>j===i?{...line,axis:e.target.value as Guide['axis']}:line))}><option value="vertical">垂直</option><option value="horizontal">水平</option></select><button disabled={disabled} onClick={()=>onChange(local.filter((_,j)=>j!==i))}>删除</button></div>)}
  </div>;
}
export function OpticsPanel({owner,report,disabled=false}:{owner:OpticsOwner;report?:OpticsReport;disabled?:boolean}){
  const {state}=owner;const shown=useRef(state);shown.current=state;const [draft,setDraft]=useState<OpticsRecipe|null>(null),[metadata,setMetadata]=useState<LensMetadata>({camera_maker:'',camera_model:'',lens_maker:'',lens_model:'',focal:null,aperture:null,distance:null});
  const [loaded,setLoaded]=useState<{id:string|null;before:string;after:string;input:string}>({id:null,before:'',after:'',input:''});
  const [autoAttempt,setAutoAttempt]=useState(false);
  const resultImage=useRef<HTMLImageElement>(null);
  const close=useRef<HTMLButtonElement>(null);
  useEffect(()=>{if(state.image){setDraft(structuredClone(state.image.recipe));setAutoAttempt(false);}},[state.image]);
  useEffect(()=>{if(!state.open)setAutoAttempt(false);},[state.open]);
  useEffect(()=>{if(report?.metadata)setMetadata(report.metadata);},[report?.metadata]);
  useEffect(()=>{if(!state.open)return;const root=document.getElementById('root'),was=root?.inert,previous=document.activeElement as HTMLElement|null;if(root)root.inert=true;close.current?.focus();return()=>{if(root)root.inert=!!was;previous?.focus();};},[state.open]);
  useEffect(()=>{if(!state.open)return;const handler=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();owner.cancel();}};window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);},[state.open,owner.cancel]);
  const image=state.image,locked=state.phase==='loading'||owner.pending,ready=state.phase==='ready'&&state.presented;
  const autoEnabled=!!draft&&['smart','horizontal','vertical'].includes(draft.perspective.mode);
  // A failed first smart solve must not prevent trying the single-axis modes.
  // This is retry UI only; it does not enable or persist an unproved recipe.
  const autoRetry=state.phase==='failed'&&(autoAttempt||autoEnabled);
  const imagesLoaded=!!image&&loaded.id===state.previewId&&loaded.before===image.before&&loaded.after===image.after&&loaded.input===image.input;
  useOutputPresentation({element:resultImage,previewId:state.previewId,source:image?.after,width:image?.width,height:image?.height,
    ready:state.open&&state.phase==='ready'&&!state.presented&&imagesLoaded,onPresented:owner.presented});
  function didLoad(key:'before'|'after'|'input'){
    if(!image||state.previewId!==shown.current.previewId||shown.current.phase!=='ready'||shown.current.image?.[key]!==image[key])return;
    setLoaded(previous=>({...previous,...(previous.id!==state.previewId?{before:'',after:'',input:''}:{}),id:state.previewId,[key]:image[key]}));
  }
  function setting(section:'lens'|'perspective',key:string,value:number|boolean){void owner.preview({action:'set',section,key,value});}
  function automatic(mode:'off'|'smart'|'horizontal'|'vertical'){
    setAutoAttempt(mode!=='off');void owner.preview({action:'auto',mode});
  }
  function slider(section:'lens'|'perspective',key:string,min=-100,max=100,step=1){if(!draft)return null;const values=draft[section] as unknown as Record<string,unknown>;const value=Number(values[key]);
    const update=(v:number)=>setDraft(p=>p?{...p,[section]:{...p[section],[key]:v}}:p);
    const commit=(v:number)=>{if(Number.isFinite(v))setting(section,key,v);};
    return <label className="opticsSlider" key={key}>{LABELS[key]}<input type="range" min={min} max={max} step={step} value={value} disabled={locked||!state.presented} onChange={e=>update(Number(e.target.value))} onPointerUp={e=>commit(Number(e.currentTarget.value))} onKeyUp={e=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown'].includes(e.key))commit(Number(e.currentTarget.value));}}/>
      <input aria-label={`${LABELS[key]}数值`} type="number" min={min} max={max} step={step} value={value} disabled={locked||!state.presented} onChange={e=>update(Number(e.target.value))} onBlur={e=>{const v=Number(e.target.value);if(v!==Number((image?.recipe[section] as unknown as Record<string,unknown>)?.[key]))commit(v);}}/></label>;
  }
  return <section className="opticsPanel" aria-label="镜头调整与透视矫正"><strong>镜头调整 / 透视矫正</strong>{report?.install_hint&&<details><summary>镜头运行库安装与修复</summary><p>{report.install_hint}</p></details>}<p><small>真实镜头标定、手动畸变与暗角、自动线段分析和可编辑引导线。</small></p>
    <button disabled={disabled||owner.pending} onClick={()=>void owner.start()}>调整镜头与透视</button>
    {report?.note&&<p><small>{report.note}</small></p>}{report?.suspended&&<p role="alert">已暂停：{report.suspended}</p>}
    {!state.open&&state.message&&<p role="status">{state.message}</p>}{!state.open&&state.phase==='uncertain'&&<button onClick={()=>void owner.check()}>查询原操作结果</button>}
    {state.open&&createPortal(<div className="opticsWorkspace" role="dialog" aria-modal="true" aria-label="镜头与透视工作区"><header><strong>镜头调整与透视矫正</strong><span>真实预览 · 应用后可整步撤销</span><button ref={close} onClick={()=>owner.cancel()}>关闭</button></header>
      <main><aside>{draft&&<>
        <h3>镜头调整</h3><label><input type="checkbox" checked={draft.lens.enabled} disabled={locked||!draft.lens.profile||!state.presented} onChange={e=>setting('lens','enabled',e.target.checked)}/>镜头矫正（Lensfun 实际标定）</label>
        <p><small>{draft.lens.profile?`${draft.lens.profile.lens_maker} ${draft.lens.profile.lens_model} · ${draft.lens.profile.flags.join(' / ')}`:'没有可用镜头配置，可继续手动调整；不会猜测镜头或宣称自动成功'}</small></p>
        {slider('lens','distortion')}{slider('lens','vignette')}{slider('lens','midpoint',0,100)}
        <label><input type="checkbox" checked={draft.lens.crop_lock} disabled={locked||!state.presented} onChange={e=>setting('lens','crop_lock',e.target.checked)}/>锁定镜头裁剪，自动等比收边</label>
        <details><summary>选择真实镜头配置 / 拍摄参数</summary>
          {(['camera_maker','camera_model','lens_maker','lens_model'] as const).map((key,i)=><label key={key}>{['相机品牌','相机型号','镜头品牌','镜头型号'][i]}<input value={metadata[key]} disabled={locked} onChange={e=>setMetadata(p=>({...p,[key]:e.target.value}))}/></label>)}
          {(['focal','aperture','distance'] as const).map((key,i)=><label key={key}>{['焦距 mm（必填）','光圈 f（未知留空）','对焦距离 m（未知留空）'][i]}<input type="number" min="0.01" value={metadata[key]??''} disabled={locked} onChange={e=>setMetadata(p=>({...p,[key]:e.target.value===''?null:Number(e.target.value)}))}/></label>)}
          <small>未知光圈/距离不会猜填，相关暗角标定保持未启用。缺失库需要显式安装，不自动下载。</small>
          <label>源文件方向<select disabled={locked} value={metadata.orientation??1} onChange={e=>setMetadata(p=>({...p,orientation:Number(e.target.value)}))}>{Array.from({length:8},(_,i)=><option key={i+1} value={i+1}>{['正常','水平镜像','旋转 180°','垂直镜像','转置','顺时针 90°','反转置','逆时针 90°'][i]}</option>)}</select></label><button disabled={locked||!state.presented} onClick={()=>void owner.preview({action:'find_profile',metadata})}>查找本地镜头库</button>
          {image?.candidates?.length===0&&<p>没有匹配配置，请检查型号或使用手动调整。</p>}
          {image?.candidates?.map((candidate,i)=><button key={`${candidate.lens_model}-${i}`} disabled={locked||!state.presented} onClick={()=>void owner.preview({action:'profile',candidate,metadata:image.profile_metadata??metadata})}>{candidate.camera_model} / {candidate.lens_maker} {candidate.lens_model}</button>)}
        </details>
        <h3>透视矫正</h3>
        <label><input type="checkbox" checked={autoEnabled} disabled={locked||(!state.presented&&!autoRetry)} onChange={e=>automatic(e.target.checked?'smart':'off')}/>自动透视矫正（手册：AI透视矫正）</label>
        <p><small>采用真实线段检测与几何解算，无神经网络依赖；证据不足时保留上一有效结果并提示。</small></p>
        <div className="opticsModes" role="group" aria-label="自动透视生效模式">{(['smart','horizontal','vertical'] as const).map((mode,i)=><button key={mode} aria-pressed={draft.perspective.mode===mode} disabled={(!autoEnabled&&!autoRetry)||locked||(!state.presented&&!autoRetry)} onClick={()=>automatic(mode)}>{['智能','仅水平','仅垂直'][i]}</button>)}</div>
        {autoRetry&&<p role="status">本次自动解算未生效，上一有效设置未改变；可选择其他模式重试，或返回上一有效预览。</p>}
        <p><small>本产品默认关闭，每次开启先用智能模式；关闭只清除自动解算，保留下面的手动微调。智能在两个方向间保守折中，不强行拉直全部线条。</small></p>
        {draft.perspective.mode==='guided'&&<p><small>当前使用引导线解算；开启自动会替换该解算并清除引导线，手动微调保留。</small><br/><button disabled={locked||!state.presented} onClick={()=>void owner.preview({action:'auto',mode:'off'})}>清除引导线解算，保留手动微调</button></p>}
        {draft.perspective.analysis&&<p><small>{draft.perspective.analysis.message}<br/>依据 {draft.perspective.analysis.lines} 条线，{draft.perspective.mode==='guided'?'手动引导线约束':`线段支持评分 ${Math.round(draft.perspective.analysis.confidence*100)}/100（启发式，非成功概率）`}，残差 {draft.perspective.analysis.residual_degrees.toFixed(2)}°</small></p>}
        {['vertical','horizontal','rotation','aspect','scale','offset_x','offset_y'].map(key=>slider('perspective',key,key==='scale'?25:key==='rotation'?-45:-100,key==='scale'?400:key==='rotation'?45:100,key==='rotation'?.1:1))}
        <label><input type="checkbox" checked={draft.perspective.show_guides} disabled={locked||!state.presented} onChange={e=>setting('perspective','show_guides',e.target.checked)}/>显示结果辅助线</label>
        <label><input type="checkbox" checked={draft.perspective.crop_lock} disabled={locked||!state.presented} onChange={e=>setting('perspective','crop_lock',e.target.checked)}/>锁定透视裁剪，保持画面比例</label>
        <button disabled={locked||!state.presented} onClick={()=>void owner.preview({action:'reset_perspective'})}>仅重置透视，保留镜头调整</button>
        <p><small>更换镜头或修改畸变前须先关闭自动/引导透视，再重新分析或放置引导线，避免旧线条被错误解释。</small></p><p><small>当前自动收边缩放：{((image?.crop_zoom??1)*100).toFixed(1)}%。手动数值范围为本产品约定，不冒充官方未披露量程。</small></p>
        <button disabled={locked||!state.presented} onClick={()=>void owner.preview({action:'reset'})}>重置全部镜头与透视（含镜头配置）</button>
      </>}</aside><div className="opticsImages">{image&&state.phase!=='loading'&&<>
        <div className="opticsComparisons"><figure><figcaption>镜头/透视之前（只读）</figcaption><img key={`before-${state.previewId}`} src={image.before} width={image.width} height={image.height} alt="镜头透视之前，已包括原有全部效果和裁剪的真实画面" onLoad={()=>didLoad('before')}/></figure>
          <figure><figcaption>当前镜头/透视结果（只读）</figcaption><div className={draft?.perspective.show_guides?'opticsResult opticsGrid':'opticsResult'}><img key={`after-${state.previewId}`} ref={resultImage} data-optics-preview={state.previewId} src={image.after} width={image.width} height={image.height} alt="实际镜头和透视校正结果，已应用最终裁剪" onLoad={()=>didLoad('after')}/></div></figure></div>
        {state.phase==='ready'&&!state.presented&&<p role="status">请将本次结果图完整滚动到可视区域，并保持窗口焦点；展示确认完成后才能继续编辑或应用。</p>}
        {autoEnabled&&<p><small>绘制引导线会替换当前自动解算；第 2 条线完成后按引导线重新求解，手动微调保留。</small></p>}
        <h3>透视引导线画布</h3><GuideCanvas key={`input-${state.previewId}`} source={image.input} width={image.input_width} height={image.input_height} guides={draft?.perspective.guides??[]} disabled={locked||!state.presented} onLoad={()=>didLoad('input')} onChange={guides=>void owner.preview({action:'guides',guides})}/>
      </>}</div></main><footer><p role="status">{state.message}</p>{state.phase==='failed'&&<><button onClick={()=>void owner.preview({action:'view'})}>返回上一有效预览</button><button onClick={()=>void owner.preview({action:'reset_perspective'})}>仅重置透视并审阅，保留镜头</button><button onClick={()=>void owner.preview({action:'reset'})}>重置全部镜头/透视并审阅</button></>}<small>预览是当前生产链的真实代理反馈，非全尺寸验收。批量/预设可选手动参数或逐目标自动重算；须审阅完整候选，源照片的镜头身份、矩阵和引导线不复制。</small>
        <button disabled={!ready||!state.dirty||locked} onClick={()=>void owner.apply()}>应用本次修改</button>{state.phase==='uncertain'&&<button onClick={()=>void owner.check()}>查询原结果，不重复提交</button>}
      </footer></div>,document.body)}
  </section>;
}
