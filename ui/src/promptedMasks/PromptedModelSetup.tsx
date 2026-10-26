import {useEffect,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {downloadProgress,extensionReady,extensionStatusLabel,type ModelStatus} from './curatedExtension';
import './promptedMasks.css';
type Action='status'|'install'|'cancel'|'check';
/** Only explicit install downloads. Status verifies receipts; check runs a bounded CPU probe. */
export function PromptedModelSetup({onUse,useDisabled=false,useKey='',expanded=false}:{onUse?:()=>void;useDisabled?:boolean;useKey?:string;expanded?:boolean}){
  const [status,setStatus]=useState<ModelStatus|null>(null),[error,setError]=useState('');
  const alive=useRef(true),serial=useRef(0),useContext=useRef({onUse,useDisabled,useKey});
  useContext.current={onUse,useDisabled,useKey};
  async function run(action:Action):Promise<ModelStatus|null>{
    const token=++serial.current;setError('');setStatus(previous=>({...previous,running:true,action,error:undefined}));
    try{
      let next=await invoke<ModelStatus>('prompted_model',{action,extensionId:'id-background-prompted-v1'});
      while(alive.current&&token===serial.current){
        if(next.extension_id!=='id-background-prompted-v1')throw Error('共享安装器当前属于另一扩展；未采用或取消它的状态。');
        setStatus(next);if(!next.running)return next;
        await new Promise(resolve=>setTimeout(resolve,500));if(!alive.current||token!==serial.current)return null;
        next=await invoke<ModelStatus>('prompted_model_status');
      }
    }catch(reason){if(alive.current&&token===serial.current){setError(String(reason));setStatus(previous=>({...previous,running:false,error:String(reason)}));}}
    return null;
  }
  async function use(){
    const captured=useContext.current;
    if(captured.useDisabled||!captured.onUse||!extensionReady(status))return;
    const next=await run('status');
    if(!alive.current)return;
    const current=useContext.current;
    if(current.useDisabled||current.useKey!==captured.useKey){setError('照片或工具状态已变化，请从当前照片重新开始。');return;}
    if(extensionReady(next))current.onUse?.();
    else setError('当前安装未通过准备检查，未打开选区工具。');
  }
  useEffect(()=>{alive.current=true;void run('status');return()=>{alive.current=false;++serial.current;};},[]);
  const result=status?.result,progress=downloadProgress(status);
  const phase:Record<string,string>={checkpoint:'下载权重',verifying:'校验完整权重 SHA-256',runtime:'准备隔离运行组件',readiness:'执行 CPU 准备检查',complete:'安装步骤结束',starting:'启动准备程序'};
  return <details className="promptedModel" open={expanded||undefined}><summary>模型与运行环境 · {extensionStatusLabel(status)}</summary>
    <p>精选固定版本 SAM 2.1 Tiny（Apache-2.0），用于提示式主体候选。权重 156,008,466 字节（约 149 MiB）；可选运行组件另需下载和磁盘空间。不会安装任意社区节点或上传照片。</p>
    <p>前提：已选 Python 引擎及其 Torch / torchvision 等基础依赖可用。基础引擎的自动准备尚未接通，不是任意新机器零环境一键可用。CPU 准备检查不代表 GPU 兼容、实机画质或性能验收。</p>
    <p>当前仅面向已有 Linux Python ≥3.10 与受支持基础引擎。安装磁盘可用空间准入 1 GiB；CPU 准备检查要求可用内存至少 4 GiB，进程地址空间上限 8 GiB。这些是保守准入预算，不是实测最低配置；暂无通过验收的设备清单。运行组件的额外下载总量尚未完整锁定。</p>
    <div className="promptedToolbar"><button disabled={!!status?.running} onClick={()=>void run('status')}>核对安装状态</button><button disabled={!!status?.running||result?.state==='installed'} onClick={()=>void run('install')}>安装 / 继续下载 / 重试</button><button disabled={!!status?.running||result?.installed!==true} onClick={()=>void run('check')}>重新检查 CPU 准备状态</button>{status?.running&&status.action!=='status'&&<button onClick={()=>void run('cancel')}>取消准备</button>}</div>
    {progress&&<label>权重下载 <progress max={progress.total} value={progress.done}/>{progress.done.toLocaleString()} / {progress.total.toLocaleString()} 字节</label>}
    {typeof result?.resume_bytes==='number'&&result.resume_bytes>0&&<p>本次从已保留的 {result.resume_bytes.toLocaleString()} 字节续传；完成后仍须校验完整 SHA-256。</p>}
    <p role="status">{error||status?.error||result?.error||[phase[result?.phase??'']??result?.phase,extensionStatusLabel(status)].filter(Boolean).join(' · ')}</p>
    {onUse&&<button disabled={useDisabled||!extensionReady(status)} onClick={()=>void use()}>使用扩展：创建主体候选</button>}
    <small>“文件已安装”不等于准备好。安装失败可按错误提示处理后重试；关闭面板不会撤销下载或删除共享模型。已保存的缺失模型选区保持暂停，不会扩大为全图。</small>
  </details>;
}
