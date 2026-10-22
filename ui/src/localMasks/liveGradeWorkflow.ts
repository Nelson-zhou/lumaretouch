import type {LocalGradeLayer} from './model';

export type GradeValues=LocalGradeLayer['grade'];
export type LiveGradeAction='begin'|'preview'|'commit'|'cancel';
export interface LiveGradeRequest {
  action:LiveGradeAction;request_id:string;document_id:string;session_id:string;group_id:string;grade?:GradeValues;
}
export interface LiveGradeReceipt extends Omit<LiveGradeRequest,'grade'> {
  protocol:1;success:boolean;outcome_unknown:boolean;requires_reload:boolean;grade?:GradeValues;
  history?:{undo_steps:number;redo_steps:number};error?:string;
}
export interface LiveGradeTransport {
  send:(request:LiveGradeRequest)=>Promise<unknown>;
  result:(requestId:string)=>Promise<unknown>;
}
export interface LiveGradeContext {documentId:string;enabled:boolean;canStart?:boolean}
export interface LiveGradeState {
  phase:'idle'|'editing'|'finishing'|'uncertain'|'failure';
  documentId:string;groupId:string;values:GradeValues|null;message:string;
}
interface Gesture {
  documentId:string;groupId:string;sessionId:string;base:GradeValues;last:GradeValues;
  begun:boolean;latest:GradeValues|null;finish:'commit'|'cancel'|null;pending:LiveGradeRequest|null;
}
const initial=():LiveGradeState=>({phase:'idle',documentId:'',groupId:'',values:null,message:''});
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const validGrade=(v:unknown):v is GradeValues=>Array.isArray(v)&&v.length===4&&v.every(n=>typeof n==='number'&&Number.isFinite(n));
const same=(a:GradeValues,b:GradeValues)=>a.every((v,i)=>v===b[i]);
function bounded<T>(p:Promise<T>,ms:number):Promise<T>{
  let timer:ReturnType<typeof setTimeout>|undefined;
  return Promise.race([p,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('等待调色回执超时')),Math.max(1,ms));})])
    .finally(()=>clearTimeout(timer));
}

/** One in-flight command and one replaceable latest numeric candidate.
 * Unknown delivery queries the same request ID, never resends a mutation.
 * Preview receipts do not modify the application's authoritative recipe report.
 */
export function createLiveGradeWorkflow(api:LiveGradeTransport,ports:{refresh:()=>Promise<void>;id?:()=>string;timeoutMs?:number}){
  const id=ports.id??(()=>crypto.randomUUID().replaceAll('-',''));
  const timeout=ports.timeoutMs??15000;
  let state=initial(),gesture:Gesture|null=null,running=false;
  let context:LiveGradeContext={documentId:'',enabled:false};
  const listeners=new Set<(s:LiveGradeState)=>void>();
  const publish=(patch:Partial<LiveGradeState>)=>{state={...state,...patch};listeners.forEach(f=>f(state));};
  const request=(g:Gesture,action:LiveGradeAction,grade?:GradeValues):LiveGradeRequest=>({
    action,request_id:id(),document_id:g.documentId,session_id:g.sessionId,group_id:g.groupId,...(grade?{grade:[...grade] as GradeValues}:{})});
  async function receipt(p:LiveGradeRequest):Promise<LiveGradeReceipt>{
    const deadline=Date.now()+timeout;
    while(Date.now()<deadline){
      const packet=await bounded(api.result(p.request_id),deadline-Date.now());
      if(!object(packet)||packet.request_id!==p.request_id)throw Error('调色回执身份不匹配');
      if(packet.phase==='pending'){
        await new Promise<void>(resolve=>setTimeout(resolve,20));continue;
      }
      if(packet.phase!=='done'||!object(packet.result))throw Error('原调色结果暂不可用，不会重新发送');
      const r=packet.result;
      if(r.protocol!==1||['request_id','action','document_id','session_id','group_id'].some(key=>r[key]!==p[key as keyof LiveGradeRequest])
        ||typeof r.success!=='boolean'||typeof r.outcome_unknown!=='boolean'||typeof r.requires_reload!=='boolean')
        throw Error('调色回执内容无效');
      if(r.outcome_unknown||r.requires_reload)throw Error(String(r.error||'原调色结果未确认'));
      if(r.success&&p.action!=='cancel'&&!validGrade(r.grade))throw Error('调色回执缺少有效参数');
      const history=r.history;
      if(r.success&&p.action==='commit'&&(!object(history)||!['undo_steps','redo_steps'].every(k=>Number.isSafeInteger(history[k])&&Number(history[k])>=0)))
        throw Error('调色提交回执缺少历史结果');
      return r as unknown as LiveGradeReceipt;
    }
    throw Error('等待原调色结果超时，不会重新发送');
  }
  async function consume(g:Gesture,p:LiveGradeRequest,r:LiveGradeReceipt){
    g.pending=null;
    if(!r.success){
      // The engine cancels and restores an unsuccessful numeric gesture. No
      // optimistic recipe value is retained after a known rejection.
      gesture=null;
      publish({...initial(),phase:'failure',message:r.error||'本次调色未应用'});
      await ports.refresh();return;
    }
    if(p.action==='begin')g.begun=true;
    if(p.action==='preview')g.last=[...r.grade!] as GradeValues;
    if(p.action==='commit'||p.action==='cancel'){
      gesture=null;
      const previousPhoto=context.documentId!==g.documentId;
      publish({...initial(),message:p.action==='commit'?(previousPhoto?'上一张照片的本次调色已保留，可一步撤销':'本次调色已保留，可一步撤销'):
        (previousPhoto?'上一张照片的未提交调色已取消':'已取消，照片恢复调整前效果')});
      await ports.refresh();
    }
  }
  async function pump(){
    const g=gesture;if(!g||running||state.phase==='uncertain')return;
    running=true;
    try{
      while(gesture===g){
        let p:LiveGradeRequest;
        if(g.pending){p=g.pending;}
        else if(!g.begun){p=request(g,'begin',g.base);}
        else if(g.finish==='cancel'){g.latest=null;p=request(g,'cancel');}
        else if(g.latest){const values=g.latest;g.latest=null;if(same(values,g.last))continue;p=request(g,'preview',values);}
        else if(g.finish==='commit'){p=request(g,'commit');}
        else break;
        const previouslySent=!!g.pending;
        g.pending=p;
        if(!previouslySent){
          // A native timeout/rejection can follow actual enqueue. Always ask
          // the receipt host, never send the same or replacement request.
          try{await bounded(api.send(p),timeout);}catch{/* Reconcile below. */}
        }
        const r=await receipt(p);
        if(gesture!==g)return;
        await consume(g,p,r);
      }
    }catch(error){
      if(gesture===g)publish({phase:'uncertain',message:`${String(error)}；请查询原操作结果，不会重复提交`});
    }finally{running=false;}
  }
  function cancel(message='手势已取消，正在恢复照片…'){
    const g=gesture;if(!g)return;
    // Once commit was sent, its outcome must be established before any new
    // mutation. A later blur cannot turn an accepted commit into a cancel.
    if(g.pending?.action==='commit')return;
    g.latest=null;g.finish='cancel';
    publish({values:[...g.base] as GradeValues,message,...(state.phase==='uncertain'?{}:{phase:'finishing'})});
    void pump();
  }
  return {
    snapshot:()=>state,subscribe:(f:(s:LiveGradeState)=>void)=>{listeners.add(f);return()=>{listeners.delete(f);};},
    busy:()=>gesture!==null,
    context(next:LiveGradeContext){
      const changedPhoto=context.documentId!==next.documentId;
      context=next;
      if(gesture&&(next.documentId!==gesture.documentId||!next.enabled))cancel('照片或工具状态变化，未提交的调色已取消');
      else if(changedPhoto&&!gesture)publish(initial());
    },
    begin(groupId:string,base:GradeValues){
      if(gesture||!context.enabled||context.canStart===false||!context.documentId||!validGrade(base))return false;
      gesture={documentId:context.documentId,groupId,sessionId:id(),base:[...base],last:[...base],begun:false,latest:null,finish:null,pending:null};
      publish({phase:'editing',documentId:context.documentId,groupId,values:[...base],message:'主画布显示真实效果预览；松开后保留，Esc 取消'});
      void pump();return true;
    },
    change(values:GradeValues){
      const g=gesture;if(!g||g.finish||!validGrade(values)||state.phase!=='editing')return;
      g.latest=[...values];publish({values:[...values]});void pump();
    },
    finish(){
      const g=gesture;if(!g||g.finish||state.phase==='uncertain')return;
      g.finish='commit';publish({phase:'finishing',message:'正在保留本次调色…'});void pump();
    },
    cancel,
    check(){
      if(!gesture||running||state.phase!=='uncertain')return;
      publish({phase:gesture.finish?'finishing':'editing',message:'正在查询原调色结果…'});void pump();
    },
    acknowledgeReload(){
      if(state.phase!=='uncertain'||!gesture||context.documentId===gesture.documentId)return;
      gesture=null;publish(initial());
    },
  };
}
export type LiveGradeWorkflow=ReturnType<typeof createLiveGradeWorkflow>;
