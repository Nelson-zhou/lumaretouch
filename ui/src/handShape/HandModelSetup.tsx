// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useRef,useState} from 'react';
import {handModelReady} from './handModelSetup';
import {invoke} from '@tauri-apps/api/core';
import {downloadProgress,type ModelStatus} from '../promptedMasks/curatedExtension';
const EXTENSION='hand-landmarker-v1';
type Action='status'|'install'|'check'|'cancel';
/** Shared native process owner; never supplies a URL, model path or photo. */
export function HandModelSetup({disabled,onRefresh}:{disabled:boolean;onRefresh:()=>void}){
 const [status,setStatus]=useState<ModelStatus|null>(null),[error,setError]=useState('');
 const alive=useRef(true),serial=useRef(0),busy=useRef(false);
 async function run(action:Action){
  if(busy.current&&action!=='cancel')return;
  busy.current=true;const token=++serial.current;setError('');
  setStatus(old=>({...old,running:true,action}));
  try{
   let next=await invoke<ModelStatus>('prompted_model',{action,extensionId:EXTENSION});
   while(alive.current&&token===serial.current){
    if(next.extension_id!==EXTENSION)throw Error('共享安装器正由另一扩展使用；不会采用或取消它的任务。');
    setStatus(next);if(!next.running)break;
    await new Promise(resolve=>setTimeout(resolve,500));
    if(!alive.current||token!==serial.current)return;
    next=await invoke<ModelStatus>('prompted_model_status');
   }
  }catch(reason){if(alive.current&&token===serial.current){setError(String(reason));setStatus(old=>({...old,running:false,error:String(reason)}));}}
  finally{if(token===serial.current)busy.current=false;}
 }
 useEffect(()=>{alive.current=true;void run('status');return()=>{alive.current=false;++serial.current;busy.current=false;};},[]);
 const progress=downloadProgress(status),ready=handModelReady(status);
 return <details><summary>可选手部定位模型 · {ready?'CPU 准备检查通过':status?.running?'处理中':'尚未就绪'}</summary>
  <p>官方 MediaPipe Hand Landmarker float16/1（Apache-2.0），7,819,105 字节。点击安装才从固定官方地址下载；支持断点续传并核对完整 SHA-256。不上传照片，不安装任意模型或修改全局包。</p>
  <p>须先选择已审核的 Linux Python ≥3.10 / MediaPipe 1.1.1 应用环境；缺少时会明确停止，不自动安装基础依赖。模型安装使用 64 MiB 空间准入；生成空白图 CPU 能力检查使用 2 GiB 地址空间及 60 秒 CPU 上限。这不是实测最低配置或照片效果验收。</p>
  <button type="button" disabled={!!status?.running} onClick={()=>void run('status')}>核对状态</button>
  <button type="button" disabled={!!status?.running} onClick={()=>void run('install')}>安装 / 继续下载 / 重试</button>
  <button type="button" disabled={!!status?.running||!status?.result?.installed} onClick={()=>void run('check')}>重新检查 CPU 准备状态</button>
  {status?.running&&<button type="button" onClick={()=>void run('cancel')}>取消准备</button>}
  {progress&&<p><progress value={progress.done} max={progress.total}/>{progress.done.toLocaleString()} / {progress.total.toLocaleString()} 字节</p>}
  <p role="status">{error||status?.error||status?.result?.error||(ready?'准备检查通过；请刷新当前照片来源以启用定位建议。':status?.result?.phase||status?.result?.state||'尚未核对')}</p>
  <button type="button" disabled={disabled||!ready} onClick={onRefresh}>刷新当前来源与定位能力</button>
  <small>关闭面板不会取消共享安装；请明确点击取消。文件存在不等于准备好。手动几何始终独立可用。定位结果仍须逐点复核；本次源码交付的安装、检查及实拍验收均未运行。</small>
 </details>;
}
