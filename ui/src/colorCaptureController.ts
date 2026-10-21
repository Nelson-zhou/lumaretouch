import {parseCaptureFrame,type VerifiedCapture} from './captureFrame.ts';
import type {CaptureDescriptor,CapturePoint,CaptureReadout} from './captureModel';
export interface CaptureStatus {phase:string;capture_id?:string;ticket?:string;descriptor?:CaptureDescriptor|null;error?:string|null;sample?:CaptureReadout|null}
export interface CaptureTransport {
  arm:(captureId:string,documentId:string)=>Promise<{ticket:string;revision:number}>;
  status:(captureId:string,ticket:string)=>Promise<CaptureStatus>;
  frame:(captureId:string,ticket:string)=>Promise<ArrayBuffer>;
  presented:(captureId:string,ticket:string)=>Promise<{eligible:boolean}>;
  sample:(captureId:string,ticket:string,requestId:string,point:CapturePoint)=>Promise<{request_ticket:string}>;
  cancel:(captureId:string,ticket:string)=>Promise<unknown>;
}
export interface CaptureContext {documentId:string;revision:number;allowed:boolean;reason:string}
export interface CaptureUi {
  phase:'off'|'arming'|'painting'|'eligible'|'sampling'|'error';
  frame:VerifiedCapture|null;readout:CaptureReadout|null;point:CapturePoint|null;message:string;
}
const initial=():CaptureUi=>({phase:'off',frame:null,readout:null,point:null,message:''});
interface Owner {
  serial:number;id:string;documentId:string;revision:number;ticket:string|null;
  sampleSerial:number;queued:{serial:number;point:CapturePoint}|null;driving:boolean;
  ack:Promise<boolean>|null;deadline:ReturnType<typeof setTimeout>|null;
}
export function createColorCaptureController(api:CaptureTransport,publish:(state:CaptureUi)=>void,
  options:{uuid?:()=>string;pause?:()=>Promise<void>}={}){
  const uuid=options.uuid??(()=>crypto.randomUUID().replaceAll('-',''));
  const pause=options.pause??(()=>new Promise<void>(resolve=>setTimeout(resolve,150)));
  let context:CaptureContext={documentId:'',revision:-1,allowed:false,reason:'尚未导入图片'};
  let owner:Owner|null=null,serial=0,disposed=false,state=initial();
  const current=(o:Owner)=>!disposed&&owner===o&&o.serial===serial;
  const set=(patch:Partial<CaptureUi>)=>{state={...state,...patch};if(!disposed)publish(state);};
  const clearDeadline=(o:Owner)=>{if(o.deadline!==null){clearTimeout(o.deadline);o.deadline=null;}};
  const release=(o:Owner)=>{if(o.ticket)void api.cancel(o.id,o.ticket).catch(()=>{/* no pixel/file lease is retained by cancellation */});};
  function cancel(message=''){
    const old=owner;owner=null;++serial;if(old){clearDeadline(old);release(old);}
    set({...initial(),message});
  }
  function fail(o:Owner,error:unknown){
    if(!current(o))return;const message=String(error);cancel();set({phase:'error',message});
  }
  function deadline(o:Owner,milliseconds:number,message:string){
    clearDeadline(o);o.deadline=setTimeout(()=>fail(o,message),milliseconds);
  }
  function updateContext(next:CaptureContext){
    context=next;
    if(owner&&(!next.allowed||next.documentId!==owner.documentId||next.revision>owner.revision))
      cancel(next.reason||'图片或参数已变化，请重新锁定取色');
  }
  async function arm(){
    if(disposed)return;
    if(!context.allowed||!context.documentId){set({phase:'error',message:context.reason||'当前视图无法取色'});return;}
    cancel();const o:Owner={serial,id:uuid(),documentId:context.documentId,revision:context.revision,ticket:null,
      sampleSerial:0,queued:null,driving:false,ack:null,deadline:null};owner=o;
    set({phase:'arming',message:'正在锁定当前代理画面…'});deadline(o,30000,'锁定画面超时，请稍后重试');
    try{
      const receipt=await api.arm(o.id,o.documentId);
      o.ticket=receipt.ticket;
      if(!current(o)){release(o);return;}
      if(!Number.isSafeInteger(receipt.revision)||receipt.revision<o.revision)throw new Error('采样状态版本不一致');
      o.revision=receipt.revision;
      while(current(o)){
        const report=await api.status(o.id,o.ticket!);
        if(!current(o))return;
        if(['error','stale','idle'].includes(report.phase))throw new Error(report.error||'采样画面已失效');
        if(report.capture_id!==o.id||report.ticket!==o.ticket)throw new Error('采样回执身份不匹配');
        if(report.phase==='ready'){
          const d=report.descriptor;
          if(!d||d.capture_id!==o.id||d.ticket!==o.ticket||d.document_id!==o.documentId)throw new Error('采样来源不匹配');
          const buffer=await api.frame(o.id,o.ticket!);
          if(!current(o))return;
          const frame=parseCaptureFrame(buffer,d);
          set({phase:'painting',frame,message:'正在准备取色画面…'});
          deadline(o,10000,'取色画面未就绪，请重新锁定');return;
        }
        await pause();
      }
    }catch(error){fail(o,error);}
  }
  function presented(descriptor:CaptureDescriptor):Promise<boolean>{
    const o=owner;
    if(!o||!current(o)||!state.frame||state.frame.descriptor.capture_id!==descriptor.capture_id||
      state.frame.descriptor.ticket!==descriptor.ticket||descriptor.capture_id!==o.id||descriptor.ticket!==o.ticket)return Promise.resolve(false);
    if(state.phase==='eligible'||state.phase==='sampling')return Promise.resolve(true);
    if(state.phase!=='painting')return Promise.resolve(false);
    if(o.ack)return o.ack;
    o.ack=(async()=>{
      try{
        const result=await api.presented(o.id,o.ticket!);
        if(!current(o))return false;
        if(!result.eligible)throw new Error('取色画面确认失败');
        clearDeadline(o);set({phase:'eligible',message:'画面已锁定；点击读取代理浮点颜色'});return true;
      }catch(error){fail(o,error);return false;}
    })();return o.ack;
  }
  function pick(point:CapturePoint){
    const o=owner;
    if(!o||!current(o)||!state.frame||!['eligible','sampling'].includes(state.phase))return;
    const d=state.frame.descriptor;
    if(!Number.isInteger(point.x)||!Number.isInteger(point.y)||point.x<0||point.y<0||point.x>=d.width||point.y>=d.height||![1,3,5,11].includes(point.size))return;
    const intent=++o.sampleSerial;o.queued={serial:intent,point:{...point}};
    set({phase:'sampling',point:{...point},readout:null,message:'正在读取所选像素…'});
    if(!o.driving)void drive(o);
  }
  async function drive(o:Owner){
    o.driving=true;
    try{
      while(current(o)&&o.queued){
        const intent=o.queued;o.queued=null;const requestId=uuid();
        try {
        deadline(o,30000,'取色结果超时，请重新锁定画面');
        const requested=await api.sample(o.id,o.ticket!,requestId,intent.point);
        if(!current(o))return;
        if(intent.serial!==o.sampleSerial)continue;
        while(current(o)&&intent.serial===o.sampleSerial){
          const report=await api.status(o.id,o.ticket!);
          if(!current(o))return;
          if(intent.serial!==o.sampleSerial)break;
          if(report.phase!=='eligible')throw new Error(report.error||'取色画面已失效');
          const result=report.sample;
          if(result&&result.request_id===requestId&&result.request_ticket===requested.request_ticket&&
            result.capture_id===o.id&&result.ticket===o.ticket){
            if(!result.success||!result.analysis||!result.descriptor)throw new Error(result.error||'取色失败');
            if(result.descriptor.generation!==state.frame?.descriptor.generation||result.descriptor.seq!==state.frame?.descriptor.seq)
              throw new Error('取色结果与锁定画面不一致');
            clearDeadline(o);set({phase:'eligible',readout:result,message:'代理浮点读数 · Lab D65'});break;
          }
          await pause();
        }
        }catch(error){
          if(!current(o))return;
          if(intent.serial!==o.sampleSerial)continue;
          throw error;
        }
      }
    }catch(error){fail(o,error);}finally{o.driving=false;}
  }
  function dispose(){if(disposed)return;cancel();disposed=true;}
  return {arm,cancel,presented,pick,updateContext,dispose,failed:(error:unknown)=>{if(owner)fail(owner,error);},snapshot:()=>state};
}
