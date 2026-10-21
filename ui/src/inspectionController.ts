import {parseInspectionFrame,type InspectionExpectation} from './inspectionFrame.ts';
export type InspectionStatus={epoch:string;generation:string;available:boolean;state:string;error:string|null;
  request_id:string|null;worker_id:string|null;published_epoch:string|null;published_id:string|null};
export type InspectionAccepted={epoch:string;request_id:string;accepted:boolean;expectation:InspectionExpectation};
export type InspectionIntent={key:string;canvasWidth:number;canvasHeight:number;roi:{x:number;y:number;width:number;height:number}};
export type InspectionApi={
  status:()=>Promise<InspectionStatus>;
  start:(intent:InspectionIntent,status:InspectionStatus)=>Promise<InspectionAccepted>;
  pull:(epoch:string,id:string)=>Promise<ArrayBuffer>;
  cancel:(epoch:string,id:string)=>Promise<unknown>;
  release:(epoch:string,id:string)=>Promise<unknown>;
};
export type InspectionUiState={state:'idle'|'loading'|'ready'|'error';message:string;key?:string};
type Frame=ReturnType<typeof parseInspectionFrame>;
export type InspectionCleanupStore={owner:InspectionAccepted|null;serial:number;latest:number};
const sharedCleanup:InspectionCleanupStore={owner:null,serial:0,latest:0};

function validateAccepted(owner:InspectionAccepted,intent:InspectionIntent,status:InspectionStatus){
  const e=owner.expectation;
  if(!owner.accepted||owner.epoch!==status.epoch||e.epoch!==owner.epoch||e.ticket.id!==owner.request_id
     ||e.ticket.recipe!==status.generation||e.canvasWidth!==intent.canvasWidth||e.canvasHeight!==intent.canvasHeight
     ||(['x','y','width','height'] as const).some(k=>e.roi[k]!==intent.roi[k])
     ||!Number.isSafeInteger(e.maxPayloadBytes)||e.maxPayloadBytes<0||e.maxPayloadBytes>64*1024*1024)
    throw new Error('精细预览受理信息与当前视口不一致');
}

/** One asynchronous pipeline; changing intent never abandons a pending IPC buffer. */
export function createInspectionController(api:InspectionApi,callbacks:{
  clear:()=>void;paint:(frame:Frame,intent:InspectionIntent)=>void;reveal:(intent:InspectionIntent)=>void;
  state:(state:InspectionUiState)=>void;
},wait:(ms:number)=>Promise<void>=(ms)=>new Promise(r=>setTimeout(r,ms)),now:()=>number=()=>performance.now(),
 cleanup:InspectionCleanupStore=sharedCleanup){
  let revision=0,handled=-1,running=false,disposed=false,wanted:InspectionIntent|null=null;
  let active:InspectionAccepted|null=null,cancellation:Promise<unknown>|null=null;
  const current=(r:number)=>!disposed&&r===revision&&wanted!==null;
  function cancelActive(){
    if(active&&!cancellation)cancellation=api.cancel(active.epoch,active.request_id).catch(()=>undefined);
    return cancellation;
  }
  async function release(owner:InspectionAccepted){
    const stamp=++cleanup.serial;
    try{await api.release(owner.epoch,owner.request_id);}
    catch(error){
      // Reconcile an uncertain reply, never blindly repeat a release.
      try{const status=await api.status();
        if(status.published_epoch===owner.epoch&&status.published_id===owner.request_id)throw error;
      }catch(failure){
        if(stamp>=cleanup.latest){cleanup.latest=stamp;cleanup.owner=owner;}
        throw failure;
      }
    }
    if(stamp>=cleanup.latest){cleanup.latest=stamp;cleanup.owner=null;}
  }
  async function reconcileOwned(){
    const owner=cleanup.owner;if(!owner)return;
    const status=await api.status();
    if(status.published_epoch===owner.epoch&&status.published_id===owner.request_id)await release(owner);
    else if(cleanup.owner===owner)cleanup.owner=null;
  }
  async function pump(){
    if(running||disposed)return;
    running=true;
    try{
      while(!disposed&&wanted&&handled!==revision){
        const r=revision,intent=wanted;
        let pulled=false,owner:InspectionAccepted|null=null;
        try{
          await wait(120);if(!current(r))continue;
          await reconcileOwned();if(!current(r))continue;
          callbacks.state({state:'loading',message:'精细预览加载中',key:intent.key});
          const admissionDeadline=now()+5000;
          while(current(r)){
            const status=await api.status();if(!current(r))break;
            if(!status.available)throw new Error(status.error??'当前引擎不支持全分辨率精修');
            if(status.published_id!==null){
              if(now()>admissionDeadline)throw new Error('上一份精细预览尚未释放');
              await reconcileOwned();
              await wait(80);continue;
            }
            try{owner=await api.start(intent,status);active=owner;validateAccepted(owner,intent,status);break;}
            catch(error){
              if(!/queued edits|generation changed|canvas metadata changed/.test(String(error))||now()>admissionDeadline)throw error;
              await wait(80);
            }
          }
          if(!owner)continue;
          if(!current(r)){await cancelActive();continue;}
          const deadline=now()+125000;
          while(current(r)){
            const status=await api.status();if(!current(r))break;
            if(status.epoch!==owner.epoch||status.request_id!==owner.request_id)
              throw new Error('图像或参数已变化，精细预览已取消');
            if(status.state==='failed'||status.state==='cancelled')throw new Error(status.error??'精细预览未完成');
            if(status.state==='ready')break;
            if(now()>deadline)throw new Error('精细预览超时');
            await wait(80);
          }
          if(!current(r)){await cancelActive();continue;}
          let buffer:ArrayBuffer|null=await api.pull(owner.epoch,owner.request_id);pulled=true;
          try{
            const status=await api.status();
            if(current(r)&&status.available&&status.epoch===owner.epoch&&status.generation===owner.expectation.ticket.recipe
               &&status.request_id===owner.request_id&&status.published_epoch===owner.epoch&&status.published_id===owner.request_id){
              let frame:Frame|null=parseInspectionFrame(buffer,owner.expectation);
              callbacks.paint(frame,intent);frame=null;
            }else throw new Error('精细预览返回时图像已变化');
          }finally{
            // Canvas owns its copied pixels. No ArrayBuffer/typed-array/ImageData
            // reference is retained in React state or across the release await.
            buffer=null;await release(owner);
          }
          const finalStatus=await api.status();
          if(current(r)&&finalStatus.available&&finalStatus.epoch===owner.epoch
             &&finalStatus.generation===owner.expectation.ticket.recipe&&finalStatus.request_id===owner.request_id
             &&finalStatus.published_id===null&&finalStatus.published_epoch===null){
            callbacks.reveal(intent);callbacks.state({state:'ready',message:'原始分辨率精细预览',key:intent.key});
          }else if(current(r))throw new Error('精细预览交付前图像已变化');
        }catch(error){
          if(current(r)){callbacks.clear();callbacks.state({state:'error',message:String(error),key:intent.key});}
          // A rejected pull may have lost only its response. Once it settles and
          // no buffer reached JS, reconcile our exact published lease.
          if(owner&&!pulled){
            const stamp=++cleanup.serial;cleanup.latest=stamp;cleanup.owner=owner;
            try{const status=await api.status();
              if(status.published_epoch===owner.epoch&&status.published_id===owner.request_id)await release(owner);
              else if(cleanup.latest===stamp)cleanup.owner=null;
            }catch{/* Retain exact ownership until a future authoritative read. */}
          }
          await cancelActive();
        }finally{
          if(cancellation)await cancellation;
          active=null;cancellation=null;
          handled=r;
        }
      }
    }finally{running=false;if(!disposed&&wanted&&handled!==revision)void pump();}
  }
  return{
    update(intent:InspectionIntent|null){
      if(wanted===null&&intent===null)return;
      if(wanted&&intent&&wanted.key===intent.key&&wanted.canvasWidth===intent.canvasWidth&&wanted.canvasHeight===intent.canvasHeight
         &&(['x','y','width','height'] as const).every(k=>wanted!.roi[k]===intent.roi[k]))return;
      wanted=intent?{...intent,roi:{...intent.roi}}:null;revision++;callbacks.clear();
      callbacks.state({state:intent?'loading':'idle',message:intent?'精细预览加载中':'代理预览',key:intent?.key});
      void cancelActive();void pump();
    },
    dispose(){disposed=true;wanted=null;revision++;callbacks.clear();void cancelActive();},
  };
}
