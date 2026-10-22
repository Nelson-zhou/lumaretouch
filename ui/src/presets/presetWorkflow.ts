/** Completion-only receipts. Never install a historical receipt's doc_state into controls. */
import type {PresetInfo, PresetState} from '../native';
export type PresetAction = 'list'|'apply'|'save'|'import'|'delete';
export type PresetOptions = {id?:string;name?:string;path?:string;kind?:string;note?:string;force?:boolean;
  moduleScope?:string[];requestId?:string;documentId?:string};
export type PresetReply = {protocol:number;request_id:string;action:PresetAction;success:boolean;outcome_unknown:boolean;
  document_id?:string|null;name?:string;id?:string;path?:string;module_scope?:string[];preset?:PresetInfo;catalog?:PresetState;
  before?:Record<string,unknown>;after?:Record<string,unknown>;doc_state?:Record<string,unknown>;
  error?:string;requires_reload?:boolean;rolled_back?:boolean;operation_committed?:boolean|null};
export type PresetContext = {enabled:boolean;editable:boolean;documentId:string};
export type PresetUi = {phase:'idle'|'working'|'uncertain'|'done'|'error';action:PresetAction|null;
  result:PresetReply|null;message:string;submitted:{action:PresetAction;options:PresetOptions;requestId:string}|null};
export type PresetTransport = {request:(action:PresetAction,options:PresetOptions)=>Promise<{requested:boolean}>;
  read:(id:string)=>Promise<{phase:string;request_id:string;result?:PresetReply;error?:string}>};
export const initialPresetUi:PresetUi = {phase:'idle',action:null,result:null,message:'',submitted:null};
const object = (value:unknown):value is Record<string,unknown> => !!value && typeof value==='object' && !Array.isArray(value);
const text = (value:unknown):value is string => typeof value==='string' && value.trim().length>0;
const scope = (value:unknown):value is string[] => Array.isArray(value) && value.length>0 && value.every(text) && new Set(value).size===value.length;
const sameScope = (a:string[],b:string[]) => a.length===b.length && a.every(op=>b.includes(op));
const moduleKeys = (value:unknown,ops:string[]) => object(value) && sameScope(Object.keys(value),ops) && Object.values(value).every(object);
export function validatePresetReply(result:PresetReply,action:PresetAction,opts:PresetOptions,requestId:string,expectedScope?:string[]){
  if(!result || result.protocol!==1 || result.request_id!==requestId || result.action!==action
    || typeof result.success!=='boolean' || typeof result.outcome_unknown!=='boolean' || (result.success&&result.outcome_unknown))throw Error('预设回执身份或状态不完整');
  if(['apply','save'].includes(action)&&result.document_id!==opts.documentId)throw Error('预设结果不属于本次照片');
  if(!result.success)return;
  if(action==='list'){
    if(!result.catalog || result.catalog.available!==true || !Array.isArray(result.catalog.list)
      || !Array.isArray(result.catalog.errors) || !Array.isArray(result.catalog.modules))throw Error('预设目录结果不完整');
    return;
  }
  if(!text(result.id) || (opts.id!==undefined&&result.id!==opts.id))throw Error('预设结果与提交的预设不一致');
  if(action==='delete'){if(!text(result.path))throw Error('缺少实际删除路径');return;}
  if(!scope(result.module_scope))throw Error('缺少实际作用模块');
  const wanted=action==='save'?opts.moduleScope:expectedScope;
  if(wanted&&!sameScope(result.module_scope,wanted))throw Error('实际作用模块与选择不一致');
  if(action==='apply'){
    if(!moduleKeys(result.before,result.module_scope)||!moduleKeys(result.after,result.module_scope)
      || !object(result.doc_state)||result.doc_state.document_id!==opts.documentId)throw Error('缺少实际应用状态');
  }else{
    const preset=result.preset;
    if(!text(result.path)||!preset||preset.schema!=='lrt.preset.v1'||preset.id!==result.id||!text(preset.name)
      ||!text(preset.kind)||!moduleKeys(preset.modules,result.module_scope))throw Error('缺少实际保存的预设内容');
    if(action==='save'&&preset.name!==opts.name)throw Error('保存名称与提交不一致');
  }
}
export function createPresetWorkflow(api:PresetTransport,publish:(state:PresetUi)=>void,
  config:{uuid?:()=>string;now?:()=>number;pause?:(ms:number)=>Promise<void>;timeoutMs?:number}={}){
  const uuid=config.uuid??(()=>crypto.randomUUID()),now=config.now??(()=>performance.now());
  const pause=config.pause??((ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms)));
  let context:PresetContext={enabled:false,editable:false,documentId:''},state={...initialPresetUi},disposed=false,generation=0;
  type Pending={id:string;action:PresetAction;options:PresetOptions;expectedScope?:string[];generation:number};
  let pending:Pending|null=null;
  const active=(g:number)=>!disposed&&generation===g;
  const set=(patch:Partial<PresetUi>)=>{state={...state,...patch};if(!disposed)publish(state);};
  function bounded<T>(promise:Promise<T>,deadline:number):Promise<T>{
    return new Promise<T>((resolve,reject)=>{
      const timer=setTimeout(()=>reject(Error('等待超时，执行结果未确认')),Math.max(1,deadline-now()));
      promise.then(v=>{clearTimeout(timer);resolve(v);},e=>{clearTimeout(timer);reject(e);});
    });
  }
  function uncertain(request:Pending,error:unknown){
    if(!active(request.generation))return;
    if(request.action==='list'){pending=null;set({phase:'error',message:String(error)});}
    else set({phase:'uncertain',message:String(error)});
  }
  async function poll(request:Pending,deadline=now()+(config.timeoutMs??120000)){
    try{
      while(active(request.generation)){
        const response=await bounded(api.read(request.id),deadline);
        if(!active(request.generation))return;
        if(response.request_id!==request.id)throw Error('预设查询身份不匹配');
        if(response.phase==='done'){
          const result=response.result;
          if(!result)throw Error('缺少预设完成结果');
          validatePresetReply(result,request.action,request.options,request.id,request.expectedScope);
          if(result.outcome_unknown){if(request.action==='list')pending=null;set({phase:request.action==='list'?'error':'uncertain',result,message:result.error??'执行结果未确认，请先核对实际状态'});return;}
          pending=null;set({phase:result.success?'done':'error',result,message:result.error??''});return;
        }
        if(response.phase!=='pending')throw Error(response.error??'结果不可查，不代表操作未执行');
        if(now()>=deadline)throw Error('尚未确认执行结果；只能继续查询，不能自动重试');
        await pause(150);
      }
    }catch(error){uncertain(request,error);}
  }
  async function submit(action:PresetAction,options:PresetOptions={},expectedScope?:string[]){
    if(disposed||pending||state.phase==='working'||state.phase==='uncertain')return;
    const editing=action==='apply'||action==='save';
    if(!context.enabled||(editing&&(!context.editable||!context.documentId))){
      set({phase:'error',action,result:null,message:editing?'需要可编辑照片和支持预设回执的配套引擎':'当前引擎不支持预设回执'});return;
    }
    if(action==='save'&&(!options.name?.trim()||!scope(options.moduleScope))){
      set({phase:'error',action,result:null,message:'请填写名称并明确选择保存模块'});return;
    }
    if(action==='save'&&Array.from(options.name??'').length>80){
      set({phase:'error',action,result:null,message:'预设名称最多 80 个字符，请缩短后保存'});return;
    }
    const id=uuid(),g=++generation,deadline=now()+(config.timeoutMs??120000);
    const captured={...options,moduleScope:options.moduleScope?[...options.moduleScope]:undefined,
      ...(editing?{documentId:context.documentId}:{}),requestId:id};
    const request:Pending={id,action,options:captured,expectedScope:expectedScope?[...expectedScope]:undefined,generation:g};pending=request;
    set({phase:'working',action,result:null,message:'',submitted:{action,options:captured,requestId:id}});
    try{
      const accepted=await bounded(api.request(action,captured),deadline);
      if(!active(g))return;
      if(!accepted.requested)throw Error('未确认请求入队，不能据此判断未执行');
      await poll(request,deadline);
    }catch(error){uncertain(request,error);}
  }
  async function query(){if(!pending||state.phase!=='uncertain')return;set({phase:'working',result:null,message:''});await poll(pending);}
  function acknowledgeInspection(){if(state.phase!=='uncertain')return;generation++;pending=null;set({...initialPresetUi});}
  return {submit,query,acknowledgeInspection,updateContext:(next:PresetContext)=>{context={...next};},snapshot:()=>state,
    dispose:()=>{disposed=true;generation++;pending=null;}};
}
