import {useEffect,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
interface ModelStatus {running:boolean;action?:string;error?:string;result?:{state?:string;phase?:string;installed?:boolean;downloaded_bytes?:number;total_bytes?:number;error?:string}}
/** Status reads never install. Only the explicit install button starts downloads. */
export function PromptedModelSetup(){
  const [status,setStatus]=useState<ModelStatus|null>(null),[error,setError]=useState('');
  const alive=useRef(true),serial=useRef(0);
  async function run(action:'status'|'install'|'cancel'){
    const token=++serial.current;setError('');setStatus(previous=>({...previous,running:true,action}));
    try{
      let next=await invoke<ModelStatus>('prompted_model',{action});
      while(alive.current&&token===serial.current){
        setStatus(next);if(!next.running)return;
        await new Promise(resolve=>setTimeout(resolve,500));if(!alive.current||token!==serial.current)return;
        next=await invoke<ModelStatus>('prompted_model_status');
      }
    }catch(reason){if(alive.current&&token===serial.current){setError(String(reason));setStatus(previous=>({...previous,running:false}));}}
  }
  useEffect(()=>{alive.current=true;void run('status');return()=>{alive.current=false;++serial.current;};},[]);
  const result=status?.result,total=result?.total_bytes??156008466,done=result?.downloaded_bytes;
  return <details className="promptedModel"><summary>模型与运行环境 · {status?.running?'处理中':result?.installed?'已安装':'检查 / 安装'}</summary>
    <p>官方 SAM 2.1 Tiny，Apache-2.0。模型权重 156,008,466 字节（约 149 MiB），可能还需下载可选推理运行组件。所有选区推理在本机进行，照片不会上传。</p>
    <p>请先在应用的引擎设置安装并启动 Python 运行环境。仅点击“安装”才会联网下载；未安装时其他基础蒙版仍可使用，缺失模型的已启用 AI 蒙版保持暂停，不会扩大到全图。</p>
    <div className="promptedToolbar"><button disabled={!!status?.running} onClick={()=>void run('status')}>检查状态</button><button disabled={!!status?.running||result?.installed===true} onClick={()=>void run('install')}>安装 / 重试安装 SAM 2.1 Tiny</button>{status?.running&&status.action==='install'&&<button onClick={()=>void run('cancel')}>取消安装</button>}</div>
    {typeof done==='number'&&<label>下载进度 <progress max={Math.max(1,total)} value={done}/>{done.toLocaleString()} / {total.toLocaleString()} 字节</label>}
    <p role="status">{error||status?.error||result?.error||[result?.phase,result?.state].filter(Boolean).join(' · ')||'正在检查模型状态…'}</p>
    <small>取消选区对话框不会卸载模型或撤销已下载文件。安装失败后可检查网络和运行环境，再手动重试。</small>
  </details>;
}
