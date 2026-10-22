import type {LiquifyImage,LiquifyMutation,LiquifyRequest,LiquifyStroke} from './model';
export interface LiquifyContext {enabled:boolean;canStart?:boolean;documentId:string;contextKey:string;reason?:string}
export interface LiquifyTransport {
  preview:(action:'preview'|'presented'|'cancel',preview:string,session:string,document:string,mutation?:LiquifyMutation)=>Promise<unknown>;
  status:(preview:string)=>Promise<unknown>;submit:(request:LiquifyRequest)=>Promise<unknown>;result:(request:string)=>Promise<unknown>;
}
type Phase='idle'|'previewing'|'drawing'|'sending'|'waiting'|'success'|'failure'|'uncertain';
export interface LiquifyState {phase:Phase;open:boolean;image:LiquifyImage|null;previewId:string|null;message:string;strokeActive:boolean;ending:boolean;request:LiquifyRequest|null}
interface Session {id:string;document:string;context:string;opticsSignature?:string}
interface Candidate {id:string;mutation:LiquifyMutation;final:boolean;sequence:number}
const initial=():LiquifyState=>({phase:'idle',open:false,image:null,previewId:null,message:'',strokeActive:false,ending:false,request:null});
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
function image(v:unknown):LiquifyImage {
  const dimensions=(r:Record<string,unknown>)=>[r.width,r.height].every(n=>Number.isSafeInteger(n)&&Number(n)>0&&Number(n)<=800);
  const png=(s:unknown)=>typeof s==='string'&&s.startsWith('data:image/png;base64,')&&s.length<=4*1024*1024;
  if(!object(v)||v.domain!=='post-effects-pre-crop-normalized'||v.quality!=='proxy-render-srgb8'||
    v.drawing_space!=='pre-optics'||typeof v.optics_active!=='boolean'||typeof v.optics_signature!=='string'||
    !/^[0-9a-f]{64}$/.test(v.optics_signature)||!dimensions(v))throw Error('液化绘制域或光学版本不兼容');
  const final=v.final_review;
  if(!object(final)||final.domain!=='final-optical-output'||final.quality!=='proxy-render-srgb8'||final.read_only!==true||
    final.optics_signature!==v.optics_signature||!dimensions(final))throw Error('缺少同一版本的只读最终光学预览');
  const pictures=[v.before,v.after,v.protection,final.after];
  if(!pictures.every(png)||pictures.reduce<number>((n,p)=>n+(typeof p==='string'?p.length:0),0)>12*1024*1024)
    throw Error('液化双视图不是有效的有界真实输出');
  return v as unknown as LiquifyImage;
}
function bounded<T>(p:Promise<T>,ms:number):Promise<T>{let timer:ReturnType<typeof setTimeout>|undefined;
  return Promise.race([p,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('等待超时')),Math.max(1,ms));})]).finally(()=>{if(timer!==undefined)clearTimeout(timer);});}

/** Replaces pending previews while dragging; each exact rendered final candidate
 * is acknowledged once, then submitted once. A failed send is queried, not retried. */
export function createLiquifyWorkflow(api:LiquifyTransport,options:{refresh:()=>Promise<void>;id?:()=>string;timeoutMs?:number}){
  const id=options.id??(()=>crypto.randomUUID().replaceAll('-','')),timeout=options.timeoutMs??120000;
  const sleep=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms));
  let state=initial(),context:LiquifyContext={enabled:false,documentId:'',contextKey:''};
  let session:Session|null=null,active=true,life=0,sequence=0,querying=false,continueDrawing=false,resumeReady=false;
  let submittedContext:string|null=null,candidate:Candidate|null=null,latest:Candidate|null=null,shown:Candidate|null=null,acknowledging:string|null=null,rendering=false;
  let timer:ReturnType<typeof setTimeout>|undefined,lastSent=0;
  const listeners=new Set<(value:LiquifyState)=>void>();
  const publish=(patch:Partial<LiquifyState>)=>{state={...state,...patch};if(active)listeners.forEach(f=>f(state));};
  const pending=()=>!!state.request&&['sending','waiting','uncertain'].includes(state.phase);
  const current=(s:Session,c?:Candidate)=>active&&session===s&&(!c||candidate===c);
  function discard(){
    const old=session,preview=candidate?.id??state.previewId;session=null;candidate=latest=shown=null;acknowledging=null;rendering=false;++life;
    if(timer!==undefined)clearTimeout(timer);timer=undefined;
    if(old&&preview)void api.preview('cancel',preview,old.id,old.document).catch(()=>{});
  }
  function cancel(message='已结束液化，未提交的手势已丢弃'){
    continueDrawing=false;resumeReady=false;
    if(pending()){publish({open:false,message:'本笔已发送，仍需查询回执；不会重复提交'});return;}
    discard();publish({...initial(),message});
  }
  function failed(error:unknown){
    if(pending()){publish({phase:'uncertain',message:`原操作结果待确认：${String(error)}`});return;}
    continueDrawing=false;discard();publish({phase:'failure',strokeActive:false,ending:false,message:String(error)});
  }
  function schedule(mutation:LiquifyMutation,final:boolean,immediate=false){
    if(!session||pending())return;
    const c:Candidate={id:id(),mutation:structuredClone(mutation),final,sequence:++sequence};latest=c;
    publish({phase:state.strokeActive?'drawing':'previewing',ending:final,message:final?'正在显示本笔最终效果，随后保存一次…':'液化实际效果更新中…'});
    if(timer!==undefined)clearTimeout(timer);
    const delay=final||immediate?0:Math.max(0,120-(Date.now()-lastSent));
    timer=setTimeout(()=>{timer=undefined;pump();},delay);
  }
  function pump(){
    if(rendering||!latest||!session||pending())return;
    const c=latest;latest=null;candidate=c;rendering=true;void render(c);
  }
  async function render(c:Candidate){
    const s=session,token=life;if(!s||!current(s,c))return;lastSent=Date.now();
    try{
      await bounded(api.preview('preview',c.id,s.id,s.document,c.mutation),timeout);
      if(!current(s,c))return;
      const deadline=Date.now()+timeout;
      while(current(s,c)){
        const raw=await bounded(api.status(c.id),deadline-Date.now());if(!current(s,c))return;
        if(!object(raw)||raw.protocol!==2||raw.preview_id!==c.id||raw.session_id!==s.id||raw.document_id!==s.document)throw Error('液化预览身份变化');
        if(raw.state==='running'){await bounded(sleep(40),deadline-Date.now());continue;}
        if(raw.state!=='ready'||raw.success!==true)throw Error(typeof raw.error==='string'?raw.error:'液化预览未完成');
        const output=image(raw.result);
        if(raw.optics_signature!==output.optics_signature||(s.opticsSignature&&s.opticsSignature!==output.optics_signature))throw Error('液化会话中的镜头/透视状态已变化');
        s.opticsSignature=output.optics_signature;
        shown=c;publish({image:output,previewId:c.id,phase:state.strokeActive?'drawing':'previewing',message:c.final?'请查看右侧本笔最终光学效果，显示后保存…':'左侧在镜头/透视前绘制，右侧只读查看最终效果'});return;
      }
    }catch(error){if(current(s,c))failed(error);}
    finally{if(token===life){rendering=false;if(latest)pump();}}
  }
  async function start(continuation=false){
    if(!active||session||pending())return;
    if(!context.enabled||context.canStart===false||!context.documentId){failed(context.reason||'请等待照片可编辑');return;}
    session={id:id(),document:context.documentId,context:context.contextKey};continueDrawing=true;resumeReady=false;
    publish({phase:'previewing',open:true,image:continuation?state.image:null,previewId:null,strokeActive:false,ending:false,request:null,message:'正在准备镜头/透视前绘制图与最终光学预览…'});
    schedule({action:'view'},false,true);
  }
  async function presented(preview:string){
    const s=session,c=shown,token=life;
    if(!s||!c||c.id!==preview||!current(s,c)||pending()||latest||rendering||acknowledging===preview)return;
    acknowledging=preview;
    try{
      await bounded(api.preview('presented',c.id,s.id,s.document),timeout);
      const deadline=Date.now()+timeout;
      while(current(s,c)&&token===life&&!latest){
        const raw=await bounded(api.status(c.id),deadline-Date.now());if(!current(s,c)||token!==life||latest)return;
        if(!object(raw)||raw.protocol!==2||raw.preview_id!==c.id||raw.session_id!==s.id||raw.document_id!==s.document||raw.optics_signature!==s.opticsSignature)throw Error('液化双视图显示证明或光学版本失效');
        if(raw.state==='presented'){
          if(c.final&&!state.strokeActive)await apply(s,c);
          else publish({phase:'drawing',message:'左侧绘制 · 右侧最终光学只读预览 · 松手保存一笔 · Esc 结束'});
          return;
        }
        if(raw.state!=='ready')throw Error(typeof raw.error==='string'?raw.error:'液化显示未确认');
        await bounded(sleep(40),deadline-Date.now());
      }
    }catch(error){if(current(s,c)&&token===life)failed(error);}
    finally{if(acknowledging===preview)acknowledging=null;}
  }
  async function query(request:LiquifyRequest){
    if(!active||querying)return;querying=true;const token=life,deadline=Date.now()+timeout;
    publish({phase:'waiting',request,message:'正在确认本笔撤销历史回执…'});
    try{
      while(active&&token===life){
        const raw=await bounded(api.result(request.request_id),deadline-Date.now());if(!active||token!==life)return;
        if(!object(raw)||raw.request_id!==request.request_id)throw Error('液化回执身份无效');
        if(raw.phase==='pending'){await bounded(sleep(80),deadline-Date.now());continue;}
        if(raw.phase!=='done'||!object(raw.result))throw Error('原笔迹回执未找到，不会重发');
        const r=raw.result;
        if(r.protocol!==1||r.action!=='apply'||r.request_id!==request.request_id||r.preview_id!==request.preview_id||r.session_id!==request.session_id||r.document_id!==request.document_id||typeof r.success!=='boolean'||typeof r.outcome_unknown!=='boolean')throw Error('液化回执不完整');
        if(r.outcome_unknown)throw Error(typeof r.error==='string'?r.error:'执行结果未知');
        if(!r.success){discard();publish({phase:'failure',strokeActive:false,ending:false,message:typeof r.error==='string'?r.error:'本笔未完成'});return;}
        if(r.requires_reload!==false||typeof r.no_change!=='boolean'||!object(r.history)||![r.history.undo_steps,r.history.redo_steps].every(n=>Number.isSafeInteger(n)&&Number(n)>=0))throw Error('液化完成缺少历史证据');
        const again=continueDrawing&&context.documentId===request.document_id;
        discard();const completedLife=life;publish({request:null,ending:false});
        let refreshed=true;try{await bounded(options.refresh(),5000);}catch{refreshed=false;}
        if(!active||life!==completedLife)return;
        resumeReady=again&&continueDrawing&&refreshed&&context.documentId===request.document_id;
        if(r.no_change)submittedContext=null;
        publish({phase:'success',message:(r.no_change?'未改变液化配方，未新增历史':'本笔已保存，可撤销')+(refreshed?'':'；刷新失败，已暂停续画')});return;
      }
    }catch(error){if(active&&token===life)publish({phase:'uncertain',ending:false,message:`结果未确认：${String(error)}`});}
    finally{querying=false;}
  }
  async function apply(s:Session,c:Candidate){
    if(!current(s,c)||latest||pending()||!context.enabled||context.documentId!==s.document||context.contextKey!==s.context)return;
    const request:LiquifyRequest={request_id:`liquify-${id()}`,preview_id:c.id,session_id:s.id,document_id:s.document};
    submittedContext=context.contextKey;resumeReady=false;publish({phase:'sending',request,strokeActive:false,message:'正在保存这一笔液化…'});
    try{await bounded(api.submit(request),timeout);}catch{/* Query uncertain sends; never duplicate a gesture. */}
    if(active)await query(request);
  }
  return {snapshot:()=>state,subscribe:(f:(v:LiquifyState)=>void)=>{listeners.add(f);return()=>{listeners.delete(f);};},start,cancel,failed,presented,
    context(next:LiquifyContext){if(context.documentId!==next.documentId){continueDrawing=false;resumeReady=false;}context=next;
      if(session&&!pending()&&(!next.enabled||next.documentId!==session.document||next.contextKey!==session.context))cancel(next.reason||'照片或编辑状态已变化，丢弃未提交笔迹');},
    beginStroke(){if(state.phase!=='drawing'||state.ending||pending()||!state.image)return false;publish({strokeActive:true});return true;},
    stroke(value:LiquifyStroke,final=false){if(!state.strokeActive||pending())return;if(final)publish({strokeActive:false});schedule({action:'stroke',stroke:value},final);},
    mutate(value:LiquifyMutation){if(!session||pending()||state.strokeActive||state.ending)return;schedule(value,true);},
    gestureCancelled(message:string){if(pending())return;
      if(session&&candidate)void api.preview('cancel',candidate.id,session.id,session.document).catch(()=>{});
      ++life;rendering=false;candidate=latest=shown=null;acknowledging=null;
      // A cancellation ends the producer session, so create a fresh view identity.
      if(session)session={...session,id:id()};
      publish({strokeActive:false,ending:false,message});schedule({action:'view'},false,true);},
    canContinue:()=>state.phase==='success'&&resumeReady&&continueDrawing&&context.enabled&&context.canStart!==false&&context.contextKey!==submittedContext,
    resume:()=>start(true),busy:pending,capturing:()=>!!session,
    externalEdit(){continueDrawing=false;resumeReady=false;if(session&&!pending())cancel('照片正在调整，未提交液化已取消');},
    check:async()=>{if(state.request&&!querying&&['waiting','uncertain'].includes(state.phase))await query(state.request);},
    activate(){active=true;},stop(){continueDrawing=false;const uncertain=pending();discard();active=false;querying=false;state=uncertain?{...state,phase:'uncertain',message:'原操作结果待确认，不会重发'}:initial();},
    acknowledgeAfterReload(){if(active&&!querying&&state.phase==='uncertain'&&state.request&&context.enabled&&context.documentId!==state.request.document_id)publish(initial());},
  };
}
