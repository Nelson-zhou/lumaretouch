/** Testable project workflow policy. Ports own dialogs, native I/O and React state. */
import type {EngineStatus} from '../native';
export interface ProjectActionPorts {
  choose:(kind:'directory'|'file')=>Promise<unknown>;
  command:(action:'create'|'open'|'save',options?:{name?:string;directory?:string;path?:string})=>Promise<unknown>;
  refresh:()=>Promise<EngineStatus|undefined>;
  inspect:()=>Promise<EngineStatus|null>;
  name:()=>string;
  setError:(message:string)=>void;
  notify:(message:string)=>void;
  remember:(path:string,name:string)=>void;
  enterRetouch:()=>void;
}
export function createProjectActions(p:ProjectActionPorts){
  function reportError(reason:unknown){const text=String(reason);p.setError(text);p.notify(text);}
  async function save(){await p.command('save');await p.refresh();}
  async function perform(action:'create'|'open'|'save'){
    try{
      if(action==='create'){
        const dir=await p.choose('directory');
        if(typeof dir!=='string'||!dir)return;
        const name=p.name().trim()||(dir.split('/').pop()||'未命名项目');
        await p.command('create',{name,directory:dir});await p.refresh();return;
      }
      if(action==='open'){
        const file=await p.choose('file');
        if(typeof file!=='string'||!file)return;
        await p.command('open',{path:file});await p.refresh();return;
      }
      await save();
    }catch(reason){reportError(reason);}
  }
  async function afterChange(){
    await p.refresh();
    const status=await p.inspect().catch(()=>null),project=status?.project;
    if(project?.open&&project.path)p.remember(project.path,project.name??'');
  }
  async function openRecent(path:string,name:string){
    try{await p.command('open',{path});await p.refresh();p.remember(path,name);p.enterRetouch();}
    catch(reason){p.setError(String(reason));}
  }
  // Preserve legacy cancellation/error refresh order in this extraction.
  async function createAndRemember(){await perform('create');await afterChange();}
  async function openAndRemember(){await perform('open');await afterChange();}
  return {perform,save,openRecent,reportError,createAndRemember,openAndRemember};
}
