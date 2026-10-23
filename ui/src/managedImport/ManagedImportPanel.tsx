import {useEffect,useRef,useState} from 'react';
import {chooseFiles,chooseFolder,chooseRoot,query,request,type Result,type Progress,type State} from './nativePort';

/** Default remains reference; copy requires a separately chosen local root. */
export function ManagedImportPanel({projectKey,onChanged}:{projectKey:string;onChanged:()=>void}) {
  const [mode,setMode]=useState<'reference'|'copy'>('reference');
  const [paths,setPaths]=useState<string[]>([]),[root,setRoot]=useState('');
  const [busy,setBusy]=useState(false),[uncertain,setUncertain]=useState(false),[operation,setOperation]=useState<string|null>(null);
  const [state,setState]=useState<State|null>(null),[progress,setProgress]=useState<Progress|null>(null);
  const [notice,setNotice]=useState(''),[error,setError]=useState('');
  const alive=useRef(true),epoch=useRef(0),active=useRef<string|null>(null),change=useRef(onChanged);
  change.current=onChanged;
  const storageKey=`lrt-managed-import:${projectKey}`;
  function retain(id:string|null){try{if(id)sessionStorage.setItem(storageKey,id);else sessionStorage.removeItem(storageKey);}catch{/* In-memory outcome remains queryable if session storage is unavailable. */}}
  function accept(result:Result) {
    if(result.progress)setProgress(result.progress);
    if(result.state){setState(result.state);if(result.state.recovery_operation_id)setOperation(result.state.recovery_operation_id);if(result.state.requires_readback||result.state.busy)setUncertain(true);}
    if(result.operation){
      if(result.operation.status==='pending'){setUncertain(true);setNotice('原导入仍在进行，请稍后再次查询。');return true;}
      return acceptOperation(result.operation);
    }
    return acceptOperation(result);
  }
  function acceptOperation(result:Result):boolean {
    if(result.status==='pending')return false;
    if(result.status==='unknown'){setUncertain(true);setNotice('结果未确认。查询原操作，不要重复导入；重启后请先打开原工程核对。');}
    if(result.status==='succeeded'){setUncertain(false);setOperation(null);retain(null);setPaths([]);setNotice(`已导入 ${result.imported??0} 张。原图没有被移动、删除或覆盖。`);change.current();}
    if(result.status==='failed'||result.status==='cancelled'){
      setUncertain(false);setOperation(null);retain(null);setError(result.error??'导入未完成');setNotice(result.notice??'原图保持不变。');
      if(result.verified_copies?.length)setNotice((result.notice??'')+` 已核验但未登记的复制文件：${result.verified_copies.join('；')}`);
    }
    return true;
  }
  async function run(action:string,payload:Record<string,unknown>={}){
    if(active.current)return;
    const id=crypto.randomUUID(),generation=epoch.current;
    active.current=id;setBusy(true);setError('');
    if(action==='start'){setOperation(id);retain(id);setProgress(null);}
    try{
      await request({action,request_id:id,...payload});
      const until=Date.now()+330000;
      while(alive.current&&generation===epoch.current&&Date.now()<until){
        const result=await query(id);
        if(!alive.current||generation!==epoch.current)return;
        if(accept(result))return;
        await new Promise(resolve=>setTimeout(resolve,300));
      }
      if(alive.current&&generation===epoch.current){setUncertain(true);setNotice('等待超时，不能判断是否已登记。请查询原操作。');}
    }catch(reason){if(alive.current&&generation===epoch.current){setError(String(reason));if(action!=='state')setUncertain(true);}}
    finally{if(alive.current&&generation===epoch.current){active.current=null;setBusy(false);}}
  }
  useEffect(()=>{
    alive.current=true;epoch.current+=1;active.current=null;
    setPaths([]);setRoot('');setMode('reference');setUncertain(false);setOperation(null);setState(null);setProgress(null);
    try{const retained=sessionStorage.getItem(storageKey);if(retained){setOperation(retained);setUncertain(true);}}catch{/* No implicit retry. */}
    void run('state');
    return()=>{alive.current=false;epoch.current+=1;}; // Never retry/cancel an uncertain commit on unmount.
  },[projectKey]);
  async function pick(kind:'files'|'folder'|'root'){
    if(busy||uncertain)return;
    const generation=epoch.current;setBusy(true);
    try{
      const value=await (kind==='root'?chooseRoot():kind==='folder'?chooseFolder():chooseFiles());
      if(!alive.current||generation!==epoch.current||value===null)return;
      const selected=Array.isArray(value)?value:[value];
      if(kind==='root')setRoot(selected[0]??'');else setPaths(selected);
    }catch(reason){if(alive.current&&generation===epoch.current)setError(String(reason));}
    finally{if(alive.current&&generation===epoch.current)setBusy(false);}
  }
  return <section className="projCard" aria-label="原图导入方式">
    <h3>导入原图</h3>
    <label><input type="radio" name="managed-import-mode" disabled={busy||uncertain} checked={mode==='reference'} onChange={()=>setMode('reference')}/>引用原位置（默认，不复制）</label>
    <label><input type="radio" name="managed-import-mode" disabled={busy||uncertain} checked={mode==='copy'} onChange={()=>setMode('copy')}/>复制到托管目录</label>
    <p>{mode==='reference'?'保持原来的引用导入方式；原图移动或改变后需要核对来源。':'先复制到临时文件，完整 SHA-256 核验后才登记到已保存工程。不会按相同内容静默合并业务副本。'}</p>
    <button disabled={busy||uncertain} onClick={()=>void pick('files')}>选择文件</button>
    <button disabled={busy||uncertain} onClick={()=>void pick('folder')}>选择目录</button>
    {paths.length>0&&<p>已选 {paths.length} 项：{paths.join('；')}</p>}
    {mode==='copy'&&<><button disabled={busy||uncertain} onClick={()=>void pick('root')}>选择托管目录</button><p>{root||'尚未选择托管目录'}</p>
      {!state?.available&&<p role="status">{state?.reason??'正在读取工程状态'}</p>}
      <small>最多 512 张、16 GiB、单文件 2 GiB、300 秒；不跟随符号链接。失败时完整但未登记的副本保留供核对，不冒充成功。</small></>}
    <button disabled={busy||uncertain||paths.length===0||(mode==='copy'&&(!root||!state?.available))} onClick={()=>void run('start',{mode,paths,...(mode==='copy'?{root}:{})})}>{mode==='copy'?'核验复制并保存工程':'引用导入'}</button>
    {busy&&operation&&<button onClick={()=>void request({action:'cancel',request_id:crypto.randomUUID(),operation_id:operation}).then(()=>setNotice('已请求取消，正在等待安全边界；已开始的原子提交可能完成。')).catch(reason=>setError(String(reason)))}>取消导入</button>}
    {progress&&<p role="status">{progress.phase==='copying'?'正在复制':progress.phase==='verifying'?'正在核验':'正在准备'} · 已处理 {(progress.bytes/1048576).toFixed(1)} MiB（包含核验读取） · 原图 {(progress.total/1048576).toFixed(1)} MiB</p>}
    {uncertain&&operation&&<button disabled={busy} onClick={()=>void run('query',{operation_id:operation})}>查询原导入结果</button>}
    <button disabled={busy||uncertain} onClick={()=>void run('state')}>刷新导入状态</button>
    {notice&&<p role="status">{notice}</p>}{error&&<p role="alert">{error}</p>}
  </section>;
}
