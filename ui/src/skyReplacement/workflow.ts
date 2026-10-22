import type {SkyDraft,SkyImage,SkyMutation,SkyRequest,SkyTarget} from './model';
export interface SkyContext {enabled:boolean;canStart?:boolean;documentId:string;contextKey:string;reason?:string}
export interface SkyTransport {
  preview:(action:'preview'|'presented'|'cancel',preview:string,session:string,document:string,mutation?:SkyMutation)=>Promise<unknown>;
  status:(preview:string)=>Promise<unknown>;submit:(request:SkyRequest)=>Promise<unknown>;result:(request:string)=>Promise<unknown>;
}
type Phase='idle'|'previewing'|'editing'|'sending'|'waiting'|'success'|'failure'|'uncertain';
export interface SkyState {phase:Phase;open:boolean;locatorReady:boolean;drawing:boolean;draft:SkyDraft|null;image:SkyImage|null;previewId:string|null;target:SkyTarget;message:string;error:string|null;dirty:boolean;committable:boolean;request:SkyRequest|null;undo:number;redo:number}
interface Session {id:string;document:string;context:string}
interface Candidate {id:string;mutation:SkyMutation;version:number}
const initial=():SkyState=>({phase:'idle',open:false,locatorReady:false,drawing:false,draft:null,image:null,previewId:null,target:'sky',message:'',error:null,dirty:false,committable:false,request:null,undo:0,redo:0});
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
function image(v:unknown):SkyImage {
  if(!object(v)||v.domain!=='source-normalized'||v.output_domain!=='production-output'||v.quality!=='proxy-render-srgb8'||v.automatic_detection!==false||
    ![v.width,v.height,v.source_width,v.source_height].every(n=>Number.isSafeInteger(n)&&Number(n)>0&&Number(n)<=800)||
    ![v.source,v.after,v.overlay].every(s=>typeof s==='string'&&s.startsWith('data:image/png;base64,')&&s.length<=4*1024*1024))throw Error('天空预览不是有效的源图定位与真实输出');
  return v as unknown as SkyImage;
}
function draft(v:unknown):SkyDraft {
  if(!object(v)||typeof v.enabled!=='boolean'||!(v.asset_path===null||typeof v.asset_path==='string')||!object(v.parameters)||!object(v.regions)||!object(v.recovery)||
      !['unmarked','marked','none'].includes(String(v.person_mode)))throw Error('天空编辑配方无效');
  return structuredClone(v) as unknown as SkyDraft;
}
function bounded<T>(p:Promise<T>,ms:number):Promise<T>{let timer:ReturnType<typeof setTimeout>|undefined;
  return Promise.race([p,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('等待超时')),Math.max(1,ms));})]).finally(()=>{if(timer!==undefined)clearTimeout(timer);});}

/** One in-flight preparation and one replaceable latest complete draft. No
 * coordinate deltas accumulate on a stale server draft; Apply redeems only the
 * displayed exact version. An uncertain send is queried, never duplicated. */
export function createSkyWorkflow(api:SkyTransport,options:{refresh:()=>Promise<void>;id?:()=>string;timeoutMs?:number}){
  const id=options.id??(()=>crypto.randomUUID().replaceAll('-','')),timeout=options.timeoutMs??120000;
  const sleep=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms));
  let state=initial(),context:SkyContext={enabled:false,documentId:'',contextKey:''};
  let session:Session|null=null,active=true,life=0,version=0,rendering=false,querying=false;
  let candidate:Candidate|null=null,latest:Candidate|null=null,shown:Candidate|null=null,ack:string|null=null;
  let past:SkyDraft[]=[],future:SkyDraft[]=[],gesture:SkyDraft|null=null;
  let timer:ReturnType<typeof setTimeout>|undefined,lastSent=0;
  const listeners=new Set<(v:SkyState)=>void>();
  const publish=(p:Partial<SkyState>)=>{state={...state,...p};if(active)listeners.forEach(f=>f(state));};
  const pending=()=>!!state.request&&['sending','waiting','uncertain'].includes(state.phase);
  const current=(s:Session,c?:Candidate)=>active&&session===s&&(!c||candidate===c);
  function discard(){
    const old=session,preview=candidate?.id??state.previewId;session=null;candidate=latest=shown=null;ack=null;rendering=false;++life;
    if(timer!==undefined)clearTimeout(timer);timer=undefined;
    if(old&&preview)void api.preview('cancel',preview,old.id,old.document).catch(()=>{});
  }
  function cancel(message='未应用的天空草稿已取消'){
    if(pending()){publish({open:false,message:'原操作已发送，仍需查询结果；不会重复提交'});return;}
    discard();past=[];future=[];gesture=null;publish({...initial(),message});
  }
  function failed(error:unknown){
    if(pending()){publish({phase:'uncertain',message:`原操作结果待确认：${String(error)}`});return;}
    publish({phase:'failure',committable:false,message:String(error),error:String(error)});
  }
  function schedule(mutation:SkyMutation,immediate=false){
    if(!session||pending())return;
    latest={id:id(),mutation:structuredClone(mutation),version:++version};
    publish({phase:'previewing',committable:false,error:null,message:'正在更新真实天空效果…'});
    if(timer!==undefined)clearTimeout(timer);
    timer=setTimeout(()=>{timer=undefined;pump();},immediate?0:Math.max(0,150-(Date.now()-lastSent)));
  }
  function pump(){if(rendering||!latest||!session||pending())return;const c=latest;latest=null;candidate=c;rendering=true;void render(c);}
  async function render(c:Candidate){
    const s=session,token=life;if(!s||!current(s,c))return;lastSent=Date.now();
    try{
      await bounded(api.preview('preview',c.id,s.id,s.document,c.mutation),timeout);
      const deadline=Date.now()+timeout;
      while(current(s,c)){
        const raw=await bounded(api.status(c.id),deadline-Date.now());if(!current(s,c))return;
        if(!object(raw)||raw.preview_id!==c.id||raw.session_id!==s.id||raw.document_id!==s.document)throw Error('天空预览身份变化');
        if(raw.state==='running'){await bounded(sleep(50),deadline-Date.now());continue;}
        if(raw.state!=='ready'||raw.success!==true)throw Error(typeof raw.error==='string'?raw.error:'天空预览未完成');
        if(latest)return;
        const result=image(raw.result),editable=draft(raw.editable);
        if(result.target!==c.mutation.target)throw Error('天空标记叠层与当前目标不一致');
        if(typeof raw.committable!=='boolean'||!(raw.validation_error===null||typeof raw.validation_error==='string'))throw Error('天空预览缺少可提交状态');
        shown=c;publish({image:result,previewId:c.id,draft:state.draft??editable,error:raw.validation_error as string|null,
          message:raw.validation_error?`效果已暂停：${raw.validation_error}。右侧只显示其他已保存效果，请修正后再应用。`:'左侧标记源照片，右侧查看真实效果。所有更改在点击应用前都是草稿。'});
        return;
      }
    }catch(error){if(current(s,c))failed(error);}
    finally{if(token===life){rendering=false;if(latest)pump();}}
  }
  async function start(){
    if(!active||session||pending())return;
    if(!context.enabled||context.canStart===false||!context.documentId){failed(context.reason||'请等待照片可编辑');return;}
    session={id:id(),document:context.documentId,context:context.contextKey};past=[];future=[];gesture=null;
    publish({...initial(),phase:'previewing',open:true,message:'正在准备原照片定位与真实效果…'});
    schedule({action:'view',target:'sky'},true);
  }
  async function presented(preview:string){
    const s=session,c=shown,token=life;
    if(!s||!c||c.id!==preview||!current(s,c)||pending()||latest||rendering||ack===preview)return;
    ack=preview;
    try{
      await bounded(api.preview('presented',c.id,s.id,s.document),timeout);
      const deadline=Date.now()+timeout;
      while(current(s,c)&&token===life&&!latest){
        const raw=await bounded(api.status(c.id),deadline-Date.now());if(!current(s,c)||token!==life||latest)return;
        if(!object(raw)||raw.preview_id!==c.id)throw Error('天空预览显示证明失效');
        if(raw.state==='presented'){publish({phase:'editing',locatorReady:true,committable:raw.committable===true&&!state.error});return;}
        if(raw.state!=='ready')throw Error(typeof raw.error==='string'?raw.error:'天空预览显示未确认');
        await bounded(sleep(50),deadline-Date.now());
      }
    }catch(error){if(current(s,c)&&token===life)failed(error);}
    finally{if(ack===preview)ack=null;}
  }
  function replace(value:SkyDraft,record=true){
    if(!session||pending()||!state.draft||!state.locatorReady)return;
    if(record&&!gesture){past.push(structuredClone(state.draft));if(past.length>32)past.shift();future=[];}
    publish({draft:structuredClone(value),dirty:true,undo:past.length,redo:future.length});
    schedule({action:'replace',target:state.target,draft:value});
  }
  async function query(request:SkyRequest){
    if(!active||querying)return;querying=true;const token=life,deadline=Date.now()+timeout;
    publish({phase:'waiting',request,message:'正在确认换天空与撤销历史回执…'});
    try{
      while(active&&token===life){
        const raw=await bounded(api.result(request.request_id),deadline-Date.now());if(!active||token!==life)return;
        if(!object(raw)||raw.request_id!==request.request_id)throw Error('天空回执身份无效');
        if(raw.phase==='pending'){await bounded(sleep(80),deadline-Date.now());continue;}
        if(raw.phase!=='done'||!object(raw.result))throw Error('原操作回执未找到，不会重发');
        const r=raw.result;
        if(r.protocol!==1||r.action!=='apply'||r.request_id!==request.request_id||r.preview_id!==request.preview_id||r.session_id!==request.session_id||r.document_id!==request.document_id||typeof r.success!=='boolean'||typeof r.outcome_unknown!=='boolean')throw Error('天空回执不完整');
        if(r.outcome_unknown)throw Error(typeof r.error==='string'?r.error:'执行结果未知');
        if(!r.success){publish({phase:'failure',request:null,committable:false,message:typeof r.error==='string'?r.error:'天空修改未完成'});return;}
        if(r.requires_reload!==false||typeof r.no_change!=='boolean'||!object(r.history)||![r.history.undo_steps,r.history.redo_steps].every(n=>Number.isSafeInteger(n)&&Number(n)>=0))throw Error('完成回执缺少历史证据');
        discard();publish({phase:'success',open:false,request:null,dirty:false,committable:false,message:r.no_change?'天空配方没有变化':'换天空已应用，可撤销；保存项目会保留素材链接和区域笔迹'});
        await bounded(options.refresh(),5000).catch(()=>publish({message:'换天空已应用，但刷新失败，请刷新当前照片'}));return;
      }
    }catch(error){if(active&&token===life)publish({phase:'uncertain',message:`结果未确认：${String(error)}`});}
    finally{querying=false;}
  }
  async function apply(){
    const s=session,c=shown;
    if(!s||!c||!current(s,c)||latest||rendering||gesture||pending()||!state.committable||!state.dirty||context.contextKey!==s.context)return;
    const request:SkyRequest={request_id:`sky-${id()}`,preview_id:c.id,session_id:s.id,document_id:s.document};
    publish({phase:'sending',request,committable:false,message:'正在应用换天空…'});
    try{await bounded(api.submit(request),timeout);}catch{/* Query, never duplicate uncertain sends. */}
    if(active)await query(request);
  }
  return {snapshot:()=>state,subscribe:(f:(v:SkyState)=>void)=>{listeners.add(f);return()=>{listeners.delete(f);};},start,cancel,failed,presented,replace,apply,
    context(next:SkyContext){context=next;if(session&&!pending()&&(!next.enabled||next.documentId!==session.document||next.contextKey!==session.context))cancel(next.reason||'照片或编辑状态已变化，未提交天空草稿已取消');},
    target(target:SkyTarget){if(!state.draft||!state.locatorReady||pending()||gesture)return;publish({target});schedule(state.dirty?{action:'replace',target,draft:state.draft}:{action:'view',target},true);},
    beginGesture(drawing=false){if(!state.draft||!state.locatorReady||pending()||gesture)return false;gesture=structuredClone(state.draft);publish({drawing});return true;},
    endGesture(){if(!gesture)return;if(JSON.stringify(gesture)!==JSON.stringify(state.draft)){past.push(gesture);if(past.length>32)past.shift();future=[];}gesture=null;publish({undo:past.length,redo:future.length,drawing:false});},
    cancelGesture(){if(!gesture)return;const old=gesture;gesture=null;publish({drawing:false});replace(old,false);},
    undo(){if(!state.draft||gesture||pending()||!past.length)return;future.push(structuredClone(state.draft));const value=past.pop()!;replace(value,false);publish({undo:past.length,redo:future.length});},
    redo(){if(!state.draft||gesture||pending()||!future.length)return;past.push(structuredClone(state.draft));const value=future.pop()!;replace(value,false);publish({undo:past.length,redo:future.length});},
    busy:pending,capturing:()=>!!session,identity:()=>session?.id??null,externalEdit(){if(session&&!pending())cancel('其他效果正在调整，未提交天空草稿已取消');},
    check:async()=>{if(state.request&&!querying&&['waiting','uncertain'].includes(state.phase))await query(state.request);},
    activate(){active=true;},stop(){const uncertain=pending();discard();active=false;querying=false;state=uncertain?{...state,phase:'uncertain',message:'原操作结果待确认，不会重发'}:initial();},
  };
}
