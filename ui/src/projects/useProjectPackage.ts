/** Correlated, non-retrying package workflow. Reload preserves the original operation ID. */
import {useEffect,useRef,useState} from 'react';
import {open,save,confirm} from '@tauri-apps/plugin-dialog';
import {projectPackageRequest,projectPackageReceipt,runProject,engineStatus} from '../native';
export type Dependency={id?:string;type?:string;kind?:string;path?:string;source_path?:string;included?:boolean;include?:boolean;status?:string;reason?:string;licence?:string;license?:string;provenance?:unknown;sha256?:string;sha256_expected?:string;bytes?:number};
export type PackagePreview={preview_id:string;manifest_sha256?:string;dependencies?:Dependency[];embedded_assets?:Dependency[];model_dependencies?:unknown;bytes?:number;warnings?:string[]};
export type PackageResult={request_id?:string;operation_id?:string;status:string;error?:string;preview?:PackagePreview;operation?:PackageResult;progress?:unknown;project_path?:string;destination?:string;manifest_sha256?:string;missing_dependencies?:Dependency[]};
const KEY='lrt.package.pending.v1';
type Recovery={operation_id:string;destination?:string;mode?:string;manifest_sha256?:string};
function readRecovery():Recovery|null{try{const raw=localStorage.getItem(KEY);if(!raw)return null;try{const value=JSON.parse(raw);return typeof value?.operation_id==='string'?value:null;}catch{return {operation_id:raw};}}catch{return null;}}
export function useProjectPackage(onChanged:()=>void){
  const [originals,setOriginals]=useState(false),[references,setReferences]=useState(false);
  const [preview,setPreview]=useState<PackagePreview|null>(null),[mode,setMode]=useState<'create'|'restore'>('create');
  const [result,setResult]=useState<PackageResult|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const recovery=useRef<Recovery|null>(readRecovery());
  const [pending,setPending]=useState<string|null>(()=>recovery.current?.operation_id??null);
  const [unknown,setUnknown]=useState(false),[archive,setArchive]=useState('');
  const mounted=useRef(true),lock=useRef(false),poll=useRef(false),changed=useRef(onChanged);changed.current=onChanged;
  function remember(id:string|null,details:Partial<Recovery>={}){setPending(id);recovery.current=id?{...details,operation_id:id}:null;try{if(recovery.current)localStorage.setItem(KEY,JSON.stringify(recovery.current));else localStorage.removeItem(KEY);}catch{}}
  function accept(value:PackageResult){
    const v=value.operation??value;setResult(v);
    if(v.preview){if(recovery.current?.mode==='preview_restore')setMode('restore');setPreview(v.preview);setUnknown(false);if(v.status==='preview')remember(null);}
    if(v.status==='unknown'){setUnknown(true);return;}
    if(['completed','cancelled','failed'].includes(v.status)){remember(null);setUnknown(false);if(v.error)setError(v.error);}
  }
  async function exchange(action:string,payload:Record<string,unknown>={},write=false){
    const id=crypto.randomUUID();if(write)remember(id,{destination:String(payload.destination??''),mode:action,manifest_sha256:preview?.manifest_sha256});
    await projectPackageRequest({action,request_id:id,...payload});
    // A transport acknowledgement is not completion. Read only this exact receipt.
    const deadline=Date.now()+120000;
    while(mounted.current&&Date.now()<deadline){
      const packet=await projectPackageReceipt<PackageResult>(id);
      if(packet.result)return packet.result;
      if(packet.phase==='unknown')throw new Error('回执未知，请查询原操作；不会自动重试。');
      await new Promise(resolve=>setTimeout(resolve,300));
    }
    throw new Error('等待回执超时，请查询原操作；不会自动重试。');
  }
  async function run(action:string,payload:Record<string,unknown>={},write=false){
    if(lock.current)return;lock.current=true;setBusy(true);setError('');
    try{const value=await exchange(action,payload,write);if(mounted.current)accept(value);}
    catch(e){if(mounted.current){setError(String(e));if(write||action==='cancel'||action==='status')setUnknown(true);}}
    finally{lock.current=false;if(mounted.current)setBusy(false);}
  }
  async function readback(){if(pending)await run('status',{...recovery.current,operation_id:pending});}
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  useEffect(()=>{
    if(!pending||busy||unknown)return;
    const timer=setInterval(()=>{if(!poll.current&&!lock.current){poll.current=true;void run('status',{...recovery.current,operation_id:pending}).finally(()=>{poll.current=false;});}},1000);
    return()=>clearInterval(timer);
  },[pending,busy,unknown]);
  function invalidate(){setPreview(null);setResult(null);}
  async function previewCreate(){if(lock.current||pending)return;setPreview(null);setMode('create');setArchive('');await run('preview_create',{include_originals:originals,include_references:references});}
  async function previewRestore(){
    if(lock.current||pending)return;
    lock.current=true;setBusy(true);
    try{const path=await open({directory:false,multiple:false,title:'选择便携工程包',filters:[{name:'LumaRetouch 便携工程',extensions:['lrpackage','zip']}]});
      if(typeof path!=='string'||!mounted.current)return;setArchive(path);setMode('restore');setPreview(null);
      const value=await exchange('preview_restore',{archive_path:path},true);if(mounted.current)accept(value);
    }catch(e){if(mounted.current)setError(String(e));}finally{lock.current=false;if(mounted.current)setBusy(false);}
  }
  async function commit(){
    if(lock.current||pending||!preview)return;lock.current=true;setBusy(true);setError('');
    try{
      const chosen=mode==='create'?await save({title:'保存便携工程包（必须为新文件）',defaultPath:'project.lrpackage',filters:[{name:'LumaRetouch 便携工程',extensions:['lrpackage']}]}):await open({directory:true,multiple:false,title:'选择恢复位置（在其中新建唯一目录，不覆盖文件）'});
      if(typeof chosen!=='string'||!mounted.current)return;
      const destination=mode==='restore'?`${chosen.replace(/[\\/]$/,'')}/lrt-restored-${crypto.randomUUID()}`:chosen;
      const approved=await confirm(`目标：${destination}\n\n`+(mode==='create'?'按已预览清单创建便携工程包。原图与外部参考原件只按你的选择复制；不会下载模型或转移未知许可的模型权重。目标已存在会拒绝，不会覆盖。继续？':'校验所有内容后恢复到新目录，不覆盖现有文件、不执行包内内容。恢复后需手动打开工程；未包含的依赖仍列为缺失。继续？'),{title:'确认便携工程操作',kind:'warning'});
      if(!approved||!mounted.current)return;
      const value=await exchange(mode,{preview_id:preview.preview_id,destination,archive_path:archive,include_originals:originals,include_references:references,confirmed:true},true);
      if(mounted.current)accept(value);
    }catch(e){if(mounted.current){setError(String(e));setUnknown(true);}}finally{lock.current=false;if(mounted.current)setBusy(false);}
  }
  async function openRestored(){
    const path=result?.project_path;if(!path||lock.current||pending)return;lock.current=true;setBusy(true);setError('');
    try{await runProject('open',{path});const until=Date.now()+10000;
      while(mounted.current&&Date.now()<until){const state=await engineStatus();if(state?.project?.path===path){changed.current();return;}await new Promise(r=>setTimeout(r,250));}
      throw new Error('尚未确认恢复工程已打开。请先保存当前工程，再使用“打开工程”核对；不会强制丢弃修改。');
    }catch(e){if(mounted.current)setError(String(e));}finally{lock.current=false;if(mounted.current)setBusy(false);}
  }
  return {canResetPreview:unknown&&recovery.current?.mode==='preview_restore',resetPreview:()=>{if(!lock.current&&recovery.current?.mode==='preview_restore'){remember(null);setPreview(null);setUnknown(false);setError('');}},originals,references,setOriginals:(v:boolean)=>{setOriginals(v);invalidate();},setReferences:(v:boolean)=>{setReferences(v);invalidate();},preview,mode,result,error,busy,pending,unknown,previewCreate,previewRestore,commit,readback,openRestored,cancel:()=>pending&&run('cancel',{operation_id:pending})};
}
