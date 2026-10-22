import type {Mutation,Review,Request} from './model';
export interface Context {enabled:boolean;canStart?:boolean;documentId:string;contextKey:string;reason?:string}
export interface Transport {preview:(action:'preview'|'presented'|'cancel',preview:string,session:string,document:string,mutation?:Mutation)=>Promise<unknown>;status:(preview:string)=>Promise<unknown>;submit:(r:Request)=>Promise<unknown>;result:(r:string)=>Promise<unknown>}
export interface State {open:boolean;phase:'idle'|'loading'|'ready'|'sending'|'uncertain'|'failure'|'success';image:Review|null;previewId:string|null;presented:boolean;committable:boolean;message:string;request:Request|null}
const initial=():State=>({open:false,phase:'idle',image:null,previewId:null,presented:false,committable:false,message:'',request:null});
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
function review(v:unknown):Review {
 if(!object(v)||v.domain!=='source-normalized'||v.review_domain!=='production-output'||v.quality!=='proxy-render-srgb8'||
 ![v.width,v.height,v.source_width,v.source_height].every(n=>Number.isSafeInteger(n)&&Number(n)>0&&Number(n)<=800)||
 ![v.before,v.after,v.source,v.mask].every(s=>typeof s==='string'&&s.startsWith('data:image/png;base64,')&&s.length<=4*1024*1024))throw Error('背景预览不是有效的真实照片输出');
 return v as unknown as Review;
}
function bounded<T>(p:Promise<T>,ms:number):Promise<T>{let timer:ReturnType<typeof setTimeout>|undefined;return Promise.race([p,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('等待超时')),Math.max(1,ms));})]).finally(()=>{if(timer!==undefined)clearTimeout(timer);});}
export function createWorkflow(api:Transport,refresh:()=>Promise<void>){
 let state=initial(),context:Context={enabled:false,documentId:'',contextKey:''},session:{id:string;document:string;context:string}|null=null;
 let alive=true,revision=0,querying=false,acknowledging:string|null=null;
 const listeners=new Set<(s:State)=>void>(),id=()=>crypto.randomUUID().replaceAll('-','');
 const publish=(p:Partial<State>)=>{state={...state,...p};if(alive)listeners.forEach(f=>f(state));};
 const busy=()=>state.phase==='sending'||state.phase==='uncertain';
 const sleep=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms));
 function discard(){const old=session,preview=state.previewId;session=null;revision++;acknowledging=null;if(old&&preview)void api.preview('cancel',preview,old.id,old.document).catch(()=>{});}
 function cancel(message='已取消未确定的背景调整'){
   if(busy()){publish({open:false,message:'修改已发送，正在确认原操作结果；不会重发'});return;}
   discard();publish({...initial(),message});
 }
 function failed(error:unknown){if(busy()){publish({phase:'uncertain',message:`原操作结果待确认：${String(error)}`});return;}discard();publish({phase:'failure',committable:false,presented:false,message:String(error)});}
 async function render(mutation:Mutation){
   const s=session;if(!s||busy())return;const token=++revision,preview=id();
   publish({phase:'loading',previewId:preview,presented:false,committable:false,message:'正在计算并显示真实背景效果…'});
   try{
     await bounded(api.preview('preview',preview,s.id,s.document,mutation),120000);
     const deadline=Date.now()+120000;
     while(alive&&session===s&&revision===token){
       const raw=await bounded(api.status(preview),deadline-Date.now());if(!alive||session!==s||revision!==token)return;
       if(!object(raw)||raw.preview_id!==preview||raw.session_id!==s.id||raw.document_id!==s.document)throw Error('背景预览身份变化');
       if(raw.state==='running'){await sleep(100);continue;}
       if(raw.state!=='ready'||raw.success!==true)throw Error(typeof raw.error==='string'?raw.error:'背景预览不可用');
       publish({phase:'ready',image:review(raw.result),committable:mutation.action==='replace',message:mutation.action==='replace'?'请检查真实结果，满意后确定':'先标记范围，再设置强度；所有效果默认为零'});return;
     }
   }catch(error){if(alive&&session===s&&revision===token)failed(error);}
 }
 async function start(){if(!context.enabled||context.canStart===false||busy())return;discard();session={id:id(),document:context.documentId,context:context.contextKey};publish({...initial(),open:true});await render({action:'view',target:'background'});}
 async function presented(preview:string){
   const s=session;if(!s||preview!==state.previewId||state.phase!=='ready'||state.presented||acknowledging===preview)return;
   acknowledging=preview;
   try{
     await bounded(api.preview('presented',preview,s.id,s.document),10000);const deadline=Date.now()+10000;
     while(alive&&session===s&&state.previewId===preview){
       const r=await bounded(api.status(preview),deadline-Date.now());
       if(!object(r)||r.preview_id!==preview||r.session_id!==s.id||r.document_id!==s.document)throw Error('背景显示确认身份失效');
       if(r.state==='presented'){publish({presented:true});return;}
       if(r.state!=='ready')throw Error('背景效果显示确认失败');await sleep(60);
     }
   }catch(error){if(alive&&session===s&&state.previewId===preview)failed(error);}
   finally{if(acknowledging===preview)acknowledging=null;}
 }
 async function query(request:Request){
   if(querying)return;querying=true;
   try{const deadline=Date.now()+120000;
     while(alive&&state.request===request){
       const raw=await bounded(api.result(request.request_id),deadline-Date.now());
       if(!object(raw)||raw.request_id!==request.request_id)throw Error('背景操作回执身份不符');
       if(raw.phase==='pending'){await sleep(100);continue;}
       if(raw.phase!=='done'||!object(raw.result))throw Error('原操作回执尚未找到，不会重复提交');
       const r=raw.result;
       if(r.protocol!==1||r.action!=='apply'||r.request_id!==request.request_id||r.preview_id!==request.preview_id||r.session_id!==request.session_id||r.document_id!==request.document_id||typeof r.success!=='boolean'||typeof r.outcome_unknown!=='boolean')throw Error('背景修改回执不完整');
       if(r.outcome_unknown)throw Error(typeof r.error==='string'?r.error:'结果未知');
       if(!r.success){discard();publish({phase:'failure',request:null,message:typeof r.error==='string'?r.error:'背景修改失败'});return;}
       if(r.requires_reload!==false||typeof r.no_change!=='boolean'||!object(r.history)||![r.history.undo_steps,r.history.redo_steps].every(v=>Number.isSafeInteger(v)&&Number(v)>=0))throw Error('背景修改缺少历史证据');
       discard();publish({phase:'success',open:false,request:null,message:r.no_change?'参数未改变，未新增历史':'背景调整已保存，可撤销'});await bounded(refresh(),5000);return;
     }
   }catch(error){if(alive&&state.request===request)publish({phase:'uncertain',message:`结果待确认：${String(error)}`});}
   finally{querying=false;}
 }
 async function confirm(){
   const s=session;if(!s||state.phase!=='ready'||!state.presented||!state.committable||!state.previewId||!context.enabled||context.contextKey!==s.context)return;
   const request:Request={request_id:`studio-${id()}`,preview_id:state.previewId,session_id:s.id,document_id:s.document};
   publish({phase:'sending',request,committable:false,message:'正在保存本次背景调整…'});
   try{await bounded(api.submit(request),120000);}catch{/* Query the original request, never repeat uncertain submission. */}
   if(alive)await query(request);
 }
 return {snapshot:()=>state,subscribe:(f:(s:State)=>void)=>{listeners.add(f);return()=>{listeners.delete(f);};},start,cancel,failed,presented,confirm,render,busy,
   dirty(){if(!busy())publish({committable:false,message:'有未更新的改动，请先更新效果'});},
   context(next:Context){context=next;if(session&&!busy()&&(!next.enabled||next.documentId!==session.document||next.contextKey!==session.context))cancel(next.reason||'照片或编辑版本变化，未确定内容已取消');},
   check:async()=>{if(state.request)await query(state.request);},externalEdit(){if(session&&!busy())cancel('其他编辑开始，背景草稿已取消');},
   activate(){alive=true;},stop(){const pending=busy();discard();alive=false;state=pending?{...state,phase:'uncertain'}:initial();},
 };
}
