/** Real dialog + correlated receipts. Unknown commit never becomes a new commit. */
import {useEffect,useRef,useState} from 'react';
import {confirm} from '@tauri-apps/plugin-dialog';
import {runProject} from '../native';
import {chooseFiles,chooseFolder,query,request,type Result,type Preview,type State} from './nativePort';
export function SourceRelocationPanel({projectKey,onChanged}:{projectKey:string;onChanged:()=>void}) {
  const [state,setState]=useState<State|null>(null),[preview,setPreview]=useState<Preview|null>(null);
  const [selected,setSelected]=useState<string[]>([]),[choices,setChoices]=useState<Record<string,string>>({});
  const [error,setError]=useState(''),[notice,setNotice]=useState(''),[confirmed,setConfirmed]=useState(false);
  const [busy,setBusy]=useState(false),[uncertain,setUncertain]=useState(false),[recoveryId,setRecoveryId]=useState<string|null>(null);
  const active=useRef<{id:string;action:string}|null>(null),generation=useRef(0),mounted=useRef(true);
  const changed=useRef(onChanged);changed.current=onChanged;
  function accept(value:Result,action:string){
    if(value.status==='pending')return false;
    if(value.status==='unknown') {setUncertain(true);setNotice('结果尚未确认。请查询原操作，不要重新提交。');return true;}
    if(value.state){setState(value.state);if(value.state.recovery_operation_id)setRecoveryId(value.state.recovery_operation_id);if(value.state.requires_readback)setUncertain(true);}
    if(value.preview){setPreview(value.preview);setChoices({});setConfirmed(false);setNotice('逐项选择核验通过的候选；相同内容的多个副本不会自动合并。');}
    if(value.status==='failed'||value.status==='cancelled'){setError(value.error??'操作未完成');setUncertain(false);setRecoveryId(null);}
    if(value.status==='succeeded'){setNotice(`已重定位 ${value.relocated??0} 张。未移动或修改原图，配方和历史保持不变。`);setPreview(null);setUncertain(false);setRecoveryId(null);changed.current();}
    if(action==='query'&&value.operation){
      if(value.operation.status==='pending'){setUncertain(true);setNotice('原操作仍在进行，请稍后查询。');}
      else accept(value.operation,'commit');
    }
    return true;
  }
  async function run(action:string,payload:Record<string,unknown>={}){
    if(active.current)return;
    const id=crypto.randomUUID(),epoch=generation.current;
    active.current={id,action};setBusy(true);setError('');
    if(action==='scan'||action==='commit')setRecoveryId(id);
    try{
      await request({action,request_id:id,...payload});
      const until=Date.now()+135000;
      while(mounted.current&&epoch===generation.current&&Date.now()<until){
        const result=await query(id);
        if(!mounted.current||epoch!==generation.current)return;
        if(accept(result,action))return result;
        await new Promise(resolve=>setTimeout(resolve,250));
      }
      if(mounted.current&&epoch===generation.current){setUncertain(true);setNotice('等待超时，请查询原操作。不会自动重发。');}
    }catch(reason){if(mounted.current&&epoch===generation.current){setError(String(reason));if(action!=='state'){setUncertain(true);setNotice('发送结果未确认；请查询原操作。');}}}
    finally{if(mounted.current&&epoch===generation.current){active.current=null;setBusy(false);}}
  }
  useEffect(()=>{
    mounted.current=true;generation.current+=1;active.current=null;
    setPreview(null);setSelected([]);setChoices({});setConfirmed(false);setUncertain(false);setRecoveryId(null);setState(null);
    void run('state');
    return ()=>{mounted.current=false;generation.current+=1;const op=active.current;
      if(op?.action==='scan')void request({action:'cancel',request_id:crypto.randomUUID(),operation_id:op.id}).catch(()=>{});
      // Never cancel/retry a commit on unmount. Its retained receipt is queried on return.
    };
  },[projectKey]);
  async function scan(directory:boolean){
    if(busy||uncertain||!selected.length)return;
    const epoch=generation.current;
    setBusy(true);setError('');
    try{
      const chosen=await (directory?chooseFolder():chooseFiles());
      if(!mounted.current||epoch!==generation.current||chosen===null)return;
      setPreview(null);setConfirmed(false);setChoices({});
      await run('scan',{document_ids:selected,...(directory?{directory:chosen}:{paths:Array.isArray(chosen)?chosen:[chosen]})});
    }catch(reason){if(mounted.current&&epoch===generation.current)setError(String(reason));}
    finally{if(mounted.current&&epoch===generation.current&&!active.current)setBusy(false);}
  }
  async function recover(){
    if(busy||!uncertain||!state?.project_path)return;
    const path=state.project_path,workspace=state.workspace,epoch=generation.current;
    const approved=await confirm('重新打开磁盘上的工程以核对实际结果。此操作不会恢复旧文件，也不会重试重定位；当前未保存的会话修改将被丢弃。是否继续？',{title:'核对磁盘工程',kind:'warning'});
    if(!approved||!mounted.current||epoch!==generation.current)return;
    try{
      await runProject('open',{path,force:true,doc:'none'});
      const result=await run('state');
      if(!mounted.current||epoch!==generation.current)return;
      if(result?.state&&result.state.workspace!==workspace&&!result.state.requires_readback){
        setUncertain(false);setRecoveryId(null);setPreview(null);setChoices({});setSelected([]);setConfirmed(false);
        setNotice('已重新打开磁盘工程。请核对缺失清单与来源变化提示；没有自动重试重定位。');changed.current();
      }else setError('尚未确认重新打开成功，请保留工程文件并查询原操作。');
    }catch(reason){if(mounted.current&&epoch===generation.current)setError(String(reason));}
  }
  return <section aria-label="缺失原图重定位" className="projCard">
    <h3>找回缺失原图</h3>
    <p>只更新工程引用。完整 SHA-256 不符会标记“源文件变化”，不会把新内容冒充原图，也不会移动、删除或上传文件。</p>
    {!state?.available&&<p role="status">{state?.reason??(state?.busy?'原操作仍在进行，请查询原操作结果':'正在读取重定位状态')}</p>}
    {(state?.rows??[]).map(row=><label key={row.document_id} style={{display:'block'}}>
      <input type="checkbox" disabled={busy||uncertain||!row.eligible} checked={selected.includes(row.document_id)} onChange={e=>{setSelected(old=>e.target.checked?[...old,row.document_id]:old.filter(id=>id!==row.document_id));setPreview(null);setConfirmed(false);}}/>
      {row.old_path}{!row.eligible&&` · ${row.reason}`}
    </label>)}
    {state?.available&&state.rows.length===0&&<p>当前没有缺失原图。</p>}
    <button disabled={!state?.available||busy||uncertain||selected.length===0||selected.length>64} onClick={()=>void scan(false)}>选择原图文件</button>
    <button disabled={!state?.available||busy||uncertain||selected.length===0||selected.length>64} onClick={()=>void scan(true)}>扫描文件夹</button>
    <small>每次最多 64 张；扫描最多 10,000 项、16 层、16 GiB 或 120 秒。符号链接不会跟随。</small>
    {busy&&active.current?.action==='scan'&&<button onClick={()=>{const id=active.current?.id;if(id)void request({action:'cancel',request_id:crypto.randomUUID(),operation_id:id}).then(()=>setNotice('正在安全停止扫描')).catch(reason=>setError(String(reason)));}}>取消扫描</button>}
    {preview&&<div>
      <p>已核验 {preview.files_hashed} 个文件。候选显示前已比较完整内容；提交前再次核验。</p>
      {preview.rows.map(row=><div key={row.document_id}>
        <p>{row.old_path}<br/>原图 SHA-256：{row.sha256}<br/>大小：{row.bytes} 字节；候选通过时以完整字节一致核验格式、尺寸、方向{row.width&&row.height?`（${row.width} × ${row.height}）`: '（旧项目未记录可展示的尺寸）'}</p>
        <select aria-label={`为 ${row.old_path} 选择新路径`} disabled={busy||uncertain} value={choices[row.document_id]??''} onChange={e=>{const path=e.target.value;setChoices(old=>{const next={...old};if(path)next[row.document_id]=path;else delete next[row.document_id];return next;});setConfirmed(false);}}>
          <option value="">{row.candidates.length?'选择候选（可暂不处理）':'未找到完全匹配的原图'}</option>
          {row.candidates.map(candidate=><option key={candidate.path} value={candidate.path}>{candidate.path}</option>)}
        </select>
      </div>)}
      {preview.errors.length>0&&<details><summary>扫描提示（{preview.errors.length}）</summary><ul>{preview.errors.map((item,index)=><li key={index}>{item.path}：{item.reason}</li>)}</ul></details>}
      <label><input type="checkbox" disabled={busy||uncertain} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>我已审核 {Object.keys(choices).length} 个路径对应关系，只更新选定引用</label>
      <button disabled={busy||uncertain||!confirmed||Object.keys(choices).length===0} onClick={()=>void run('commit',{preview_id:preview.preview_id,choices,confirmed:true})}>确认重定位并保存工程</button>
    </div>}
    {(uncertain||recoveryId)&&<button disabled={busy||!recoveryId} onClick={()=>void run('query',{operation_id:recoveryId})}>查询原操作结果</button>}
    {uncertain&&<button disabled={busy||!state?.project_path} onClick={()=>void recover()}>明确重新打开磁盘工程核对</button>}
    <button disabled={busy||uncertain} onClick={()=>void run('state')}>刷新缺失清单</button>
    {notice&&<p role="status">{notice}</p>}{error&&<p role="alert">{error}</p>}
  </section>;
}
