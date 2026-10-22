import {SkySemanticPanel} from '../skySemantic/SkySemanticPanel';
import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {open} from '@tauri-apps/plugin-dialog';
import {CONTROLS,emptyMask,maskOf,TARGET_LABELS,withMask,type SkyControl,type SkyReport,type SkyTarget} from './model';
import type {SkyReplacementOwner} from './useSkyReplacementWorkflow';
import {SkyCanvas} from './SkyCanvas';
import './skyReplacement.css';
export function SkyReplacementPanel({owner,report,disabled=false}:{owner:SkyReplacementOwner;report?:SkyReport;disabled?:boolean}){
  const {state,workflow}=owner,draft=state.draft;
  const [size,setSize]=useState(12),[opacity,setOpacity]=useState(100),[erase,setErase]=useState(false),[showMask,setShowMask]=useState(true),[zoom,setZoom]=useState(100);
  const close=useRef<HTMLButtonElement|null>(null);
  const workspace=useRef<HTMLDivElement|null>(null),launcher=useRef<HTMLButtonElement|null>(null);
  useEffect(()=>{if(!state.open)return;close.current?.focus();return()=>{if(launcher.current?.isConnected)launcher.current.focus();};},[state.open]);
  const blocked=owner.pending||!draft||!state.locatorReady||state.drawing;
  async function choose(){
    if(!draft||owner.pending)return;
    const identity=workflow.identity();
    try{
      const path=await open({multiple:false,directory:false,title:'选择自有天空素材',filters:[{name:'天空照片',extensions:['jpg','jpeg','png','bmp','tif','tiff']}]});
      if(typeof path==='string'&&identity===workflow.identity()&&workflow.capturing()&&!workflow.snapshot().drawing)workflow.replace({...workflow.snapshot().draft!,asset_path:path,asset_choice:crypto.randomUUID().replaceAll('-','')});
    }catch(error){if(identity===workflow.identity())workflow.failed(error);}
  }
  function slider(control:SkyControl){
    if(!draft)return null;
    const unavailable=(control.key==='person'&&draft.person_mode!=='marked')||
      (['reflection','reflection_blur'].includes(control.key)&&((!draft.regions.water.objects.length&&draft.semantic?.regions.water===undefined)||draft.horizon===null));
    return <label key={control.key} className="skySlider" data-control-id={`PC-32476-C-${control.id}`}>{control.label}
      <input type="range" min={control.min} max={control.max} step={control.step} value={draft.parameters[control.key]} disabled={blocked||unavailable}
        onPointerDown={()=>workflow.beginGesture()} onPointerUp={()=>workflow.endGesture()} onPointerCancel={()=>workflow.cancelGesture()}
        onKeyDown={e=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown'].includes(e.key))workflow.beginGesture();}}
        onKeyUp={()=>workflow.endGesture()} onBlur={()=>workflow.endGesture()}
        onChange={e=>workflow.replace({...draft,parameters:{...draft.parameters,[control.key]:Number(e.target.value)}})}/>
      <output>{draft.parameters[control.key]}{control.unit??''}</output>
    </label>;
  }
  return <section className="skyReplacementPanel" aria-label="换天空" data-feature-id="PC-32476">
    <strong>换天空</strong><p><small>自有素材 · 可选语义初选 + 手动画笔 · 浮点融合</small></p>
    <button ref={launcher} disabled={disabled||owner.pending||!owner.context.enabled||owner.context.canStart===false} onClick={()=>void workflow.start()}>编辑天空{report?.enabled?' · 已启用':''}</button>
    {report?.suspended&&<p role="alert">换天空已暂停：{report.suspended}。修正前不能忽略本效果出片。</p>}
    {!state.open&&state.message&&<p role="status">{state.message}</p>}
    {state.phase==='uncertain'&&!state.open&&<button onClick={()=>void workflow.check()}>查询原操作结果</button>}
    {state.open&&createPortal(<div ref={workspace} className="skyWorkspace" data-readonly-scopes role="dialog" aria-modal="true" aria-label="换天空工作区" onKeyDown={event=>{
      if(event.key!=='Tab')return;
      const elements=Array.from(workspace.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),summary,[tabindex="0"]')??[]).filter(el=>el.getClientRects().length>0);
      const first=elements[0],last=elements.at(-1);if(!first||!last)return;
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
    }}>
      <header><strong>换天空</strong><span>自动初选必须审核，可用左侧画笔修正。右侧查看真实效果。</span><button ref={close} onClick={()=>workflow.cancel()}>取消 / Esc</button></header>
      <div className="skyWorkspaceBody"><aside>
        <section data-control-id="PC-32476-C-1f5b94eaeb"><h3>天空素材与区域</h3>
          <button disabled={blocked} onClick={()=>void choose()}>选择自己的天空照片</button>
          {draft?.asset_path&&<><p className="skyAssetPath" title={draft.asset_path}>{draft.asset_path.split(/[\\/]/).at(-1)}</p><button disabled={blocked} onClick={()=>workflow.replace({...draft,enabled:false,asset_path:null,asset_choice:null})}>移除素材</button></>}
          <p><small>JPG/PNG/BMP/RGB TIFF ≤64 MiB；RGB16 TIFF 保留精度。无内置授权图库，素材必须可合法使用。</small></p>
          <div className="skyTargets" role="group" aria-label="标记区域">{(Object.keys(TARGET_LABELS) as SkyTarget[]).map(target=><button key={target} disabled={blocked} aria-pressed={state.target===target}
            data-control-id={target==='recovery'?'PC-32476-C-c68a287a5a':undefined} onClick={()=>workflow.target(target)}>{TARGET_LABELS[target]}</button>)}</div>
          <label><input type="checkbox" checked={erase} disabled={blocked} onChange={e=>setErase(e.target.checked)}/>擦除标记{state.target==='recovery'?'（重新显示天空效果）':''}</label>
          <label>画笔大小 <input type="range" min={.5} max={80} step={.5} value={size} disabled={blocked} onChange={e=>setSize(Number(e.target.value))}/><output>{size}% 短边</output></label>
          <label>笔刷强度 <input type="range" min={1} max={100} value={opacity} disabled={blocked} onChange={e=>setOpacity(Number(e.target.value))}/><output>{opacity}%</output></label>
          <label><input type="checkbox" checked={showMask} disabled={state.drawing} onChange={e=>setShowMask(e.target.checked)}/>显示标记叠层</label>
          <label>定位缩放 <select value={zoom} disabled={state.drawing} onChange={e=>setZoom(Number(e.target.value))}>{[100,150,200,300,400].map(value=><option key={value} value={value}>{value}%</option>)}</select></label>
          <button disabled={blocked||!draft||!maskOf(draft,state.target).objects.length} onClick={()=>draft&&workflow.replace(withMask(draft,state.target,emptyMask()))}>清空当前区域</button>
          <label><input type="checkbox" checked={draft?.person_mode==='none'} disabled={blocked||!!draft?.regions.person.objects.length||draft?.semantic?.regions.person!==undefined}
            onChange={e=>draft&&workflow.replace({...draft,person_mode:e.target.checked?'none':'unmarked'})}/>照片中没有人物</label>
          <p><small>有人物时请完整涂抹人物或审核人物自动初选，防止把人物当景物染色。恢复画笔只还原本次换天空的贡献，不恢复整张原图。</small></p>
          <label><input type="checkbox" checked={draft?.enabled??false} disabled={blocked} onChange={e=>draft&&workflow.replace({...draft,enabled:e.target.checked})}/>启用天空替换</label>
        </section>
        <SkySemanticPanel ports={owner.semantic} disabled={blocked} active={!!draft?.semantic}
          onDraft={semantic=>{
            const current=workflow.snapshot().draft;
            if(!current||owner.pending)return;
            workflow.replace({...current,semantic,person_mode:semantic.regions.person!==undefined?'marked':current.person_mode});
          }} onRemove={()=>{
            const current=workflow.snapshot().draft;
            if(!current||owner.pending)return;
            workflow.replace({...current,semantic:null,
              person_mode:current.person_mode==='marked'&&!current.regions.person.objects.length?'unmarked':current.person_mode,
              enabled:current.enabled&&!!current.regions.sky.objects.length&&
                (current.person_mode==='none'||!!current.regions.person.objects.length)});
          }}/>
        {state.image?.semantic_suspended&&<p role="alert">自动选区未显示：{state.image.semantic_suspended}。当前仅显示手工笔迹；请获取模型或移除自动初选。</p>}
        <details open><summary>天空调整</summary>
          <label data-control-id="PC-32476-C-62a11b207d"><input type="checkbox" checked={draft?.parameters.flip??false} disabled={blocked}
            onChange={e=>draft&&workflow.replace({...draft,parameters:{...draft.parameters,flip:e.target.checked}})}/>水平翻转天空</label>
          {CONTROLS.slice(0,12).map(slider)}
        </details>
        <details open data-control-id="PC-32476-C-2db62a27f5"><summary>人景调整</summary>{CONTROLS.slice(12,14).map(slider)}
          <small>-100 保持换天空前色彩；0 有基础氛围映射；正向增强。上限与强度映射为本项目尺度，不宣称复刻未公开算法。</small>
        </details>
        <details open data-control-id="PC-32476-C-47bf45fbb5"><summary>水面调整</summary>
          <label>地平线（源图自上而下）<input type="range" min={1} max={99} step={.5} value={(draft?.horizon??.5)*100} disabled={blocked}
            onPointerDown={()=>workflow.beginGesture()} onPointerUp={()=>workflow.endGesture()} onPointerCancel={()=>workflow.cancelGesture()}
            onKeyDown={e=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown'].includes(e.key))workflow.beginGesture();}} onKeyUp={()=>workflow.endGesture()} onBlur={()=>workflow.endGesture()}
            onChange={e=>draft&&workflow.replace({...draft,horizon:Number(e.target.value)/100})}/><output>{draft?.horizon===null?'未设置':`${Math.round((draft?.horizon??0)*1000)/10}%`}</output></label>
          <button disabled={blocked} onClick={()=>draft&&workflow.replace({...draft,horizon:.5})}>明确使用中线作为地平线</button>
          {CONTROLS.slice(14).map(slider)}<small>必须先标记真实水面并设置地平线，只在其下方反射。没有水面时保持反射为 0。</small>
        </details>
      </aside><main><SkyCanvas owner={owner} size={size} erase={erase} opacity={opacity} showMask={showMask} zoom={zoom}/>
        <div className="skyDraftHistory"><button disabled={blocked||!state.undo} onClick={()=>workflow.undo()}>撤销草稿</button><button disabled={blocked||!state.redo} onClick={()=>workflow.redo()}>重做草稿</button></div>
        <p role={state.error?'alert':'status'}>{state.message}</p>{report?.boundaries.map(line=><p key={line}><small>{line}</small></p>)}
      </main></div>
      <footer><small>当前为代理反馈。应用一次记入一次历史，项目保留区域笔迹、自动初选来源和素材身份，全尺寸 RGB8/RGB16 共用浮点效果。</small>
        {state.phase==='uncertain'&&<button onClick={()=>void workflow.check()}>查询原操作，不重复提交</button>}
        <button disabled={blocked||!state.dirty||!state.committable||state.phase!=='editing'} onClick={()=>void workflow.apply()}>应用天空修改</button>
      </footer>
    </div>,document.body)}
  </section>;
}
