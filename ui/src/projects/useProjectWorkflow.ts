/** Owns project forms, dialogs and recent-project persistence, not photo editing. */
import {useState} from 'react';
import {useProjectRecovery} from '../projectRecovery/useProjectRecovery';
import {createProjectActions} from './projectActions';
import {open as openDialog} from '@tauri-apps/plugin-dialog';
import {runProject,engineStatus,type EngineStatus} from '../native';
export type RecentProject={path:string;name:string;at:number};
export interface ProjectPorts {
  projectId:string;
  projectOpen:boolean;
  refresh:()=>Promise<EngineStatus|undefined>;
  notify:(message:string)=>void;
  enterRetouch:()=>void;
}
export function useProjectWorkflow({refresh,notify,enterRetouch,projectId,projectOpen}:ProjectPorts){
  const recovery=useProjectRecovery(projectId,projectOpen);
  const [name,setName]=useState('');
  const [error,setError]=useState('');
  const [recent,setRecent]=useState<RecentProject[]>(()=>{
    try{const raw=localStorage.getItem('lrt.recentProjects');return raw?JSON.parse(raw):[];}
    catch{return [];}
  });
  function remember(path:string,name:string){
    setRecent(prev=>{
      const next=[{path,name,at:Date.now()},...prev.filter(p=>p.path!==path)].slice(0,8);
      try{localStorage.setItem('lrt.recentProjects',JSON.stringify(next));}catch{}
      return next;
    });
  }
  const actions=createProjectActions({
    choose:(kind)=>kind==='directory'
      ? openDialog({directory:true,title:'工程放哪个目录'})
      : openDialog({title:'打开工程文件',filters:[{name:'LumaRetouch 工程',extensions:['json']}]}),
    command:runProject,refresh,inspect:engineStatus,name:()=>name,
    setError,notify,remember,enterRetouch,
  });
  return {name,setName,error,recent,refresh,recovery,...actions};
}
export type ProjectWorkflow=ReturnType<typeof useProjectWorkflow>;
