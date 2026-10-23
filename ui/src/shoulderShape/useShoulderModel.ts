// SPDX-License-Identifier: GPL-3.0-or-later
import {useCallback,useEffect,useRef,useState} from 'react';
import {bodyPoseModelStatus,runBodyPoseModel} from '../native';
import type {ModelStatus} from './nativePort';
export type ModelTask={request_id:string;running:boolean;action:string;result:Partial<ModelStatus>&{phase?:string;downloaded_bytes?:number;total_bytes?:number};error?:string|null};
/** App lifetime owns acquisition. Polls only the existing native child, never starts one on mount. */
export function useShoulderModel(onCompleted:()=>void){
 const [task,setTask]=useState<ModelTask|null>(null),[uncertain,setUncertain]=useState(false),[message,setMessage]=useState('');
 const pending=useRef<string|null>(null),done=useRef(onCompleted);done.current=onCompleted;
 const adopt=useCallback((value:ModelTask)=>{
  if(pending.current&&value.request_id!==pending.current){setUncertain(true);setMessage('模型获取请求尚未匹配，不能认定没有启动。');return;}
  setTask(value);
  if(!value.running&&value.request_id){pending.current=null;setUncertain(false);setMessage(value.error??value.result.reason??'');done.current();}
 },[]);
 const check=useCallback(async()=>{try{adopt(await bodyPoseModelStatus());}catch(error){setUncertain(true);setMessage(String(error));}},[adopt]);
 useEffect(()=>{if(!task?.running&&!uncertain)return;const timer=setInterval(()=>void check(),1000);return()=>clearInterval(timer);},[task?.running,uncertain,check]);
 const install=useCallback(async()=>{
  if(pending.current||task?.running)throw Error('模型获取仍在进行，请先查询或取消。');
  const id=`body-model-${crypto.randomUUID()}`;pending.current=id;setMessage('');setUncertain(false);setTask({request_id:id,running:true,action:'install',result:{state:'starting'}});
  try{adopt(await runBodyPoseModel('install',id));}catch(error){setUncertain(true);setMessage(`模型获取结果待核对：${String(error)}`);}
 },[task?.running,adopt]);
 const cancel=useCallback(async()=>{const id=pending.current??task?.request_id;if(!id)return;try{adopt(await runBodyPoseModel('cancel',id));}catch(error){setUncertain(true);setMessage(String(error));}},[task?.request_id,adopt]);
 return {task,busy:!!task?.running||uncertain,uncertain,message,install,cancel,check};
}
