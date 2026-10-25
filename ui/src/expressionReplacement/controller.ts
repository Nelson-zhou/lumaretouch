// SPDX-License-Identifier: GPL-3.0-or-later
import {CONFIRMATION_KEYS,OPERATION_ID,contextKey,emptyFusion,faceKey,freeze,packet,pairError,parseReceipt,previewCommand,same,validCurrent,validFusion,
  type ApplyCommand,type DonorCommand,type Confirmation,type Confirmations,type Current,type ExpressionPort,type Face,type FaceOwner,type FaceRef,type FusionMask,type Packet,type Photograph,type Preview,type PreviewCommand,type Receipt,type Settings} from './model';

export type Phase='idle'|'choosing'|'preparing'|'preview_pending'|'ready'|'sending'|'apply_pending'|'unknown'|'cancelling'|'committed'|'rejected';
export type State=Readonly<{
  phase:Phase;cancel_requested:boolean;current:Current|null;donor:Photograph|null;target_ref:FaceRef|null;donor_ref:FaceRef|null;
  fusion:FusionMask;settings:Settings;confirmations:Readonly<Partial<Record<Confirmation,boolean>>>;
  target_displayed:boolean;donor_displayed:boolean;reviewed:boolean;preview:Preview|null;
  preview_packet:Packet<PreviewCommand>|null;request:Packet|null;receipt:Receipt|null;message:string;
}>;
const initial=():State=>freeze({phase:'idle',cancel_requested:false,current:null,donor:null,target_ref:null,donor_ref:null,fusion:emptyFusion(),
  settings:{density:1,pyramid_levels:3,colour_match_strength:0},confirmations:{},target_displayed:false,donor_displayed:false,
  reviewed:false,preview:null,preview_packet:null,request:null,receipt:null,message:''} as State);
export function selectedFace(photo:Photograph|null,ref:FaceRef|null):Face|null{return photo?.faces.find(face=>faceKey(face.face_ref)===faceKey(ref))??null;}
export function selection(state:State):{target:FaceOwner;donor:FaceOwner}|null {
  const target=selectedFace(state.current?.photo??null,state.target_ref),donor=selectedFace(state.donor,state.donor_ref);
  return state.current&&state.donor&&target&&donor?{target:{source:state.current.photo.source,face:target},donor:{source:state.donor.source,face:donor}}:null;
}
export function sourceDisplayKey(photo:Photograph|null):string{return photo?`${photo.source.asset_sha256}:${photo.source.retained_asset_id}:${photo.image.sha256}`:'';}
export function previewKey(state:State):string{return state.preview&&state.preview_packet?`${state.preview_packet.command_sha256}:${state.preview.preview_token}:${state.preview.before.sha256}:${state.preview.after.sha256}:${state.preview.fusion_mask_sha256}:${state.preview.fusion_image.sha256}`:'';}
export function locked(state:State):boolean{return !['idle','ready','rejected'].includes(state.phase);}
export function canPreview(state:State):boolean {
  const owners=selection(state);
  return !locked(state)&&!!state.current?.available&&!!owners&&!pairError(owners.target,owners.donor)
    &&state.target_displayed&&state.donor_displayed&&CONFIRMATION_KEYS.every(key=>state.confirmations[key]===true)
    &&validFusion(state.fusion,owners.target.source,owners.target.face)&&state.fusion.strokes.some(stroke=>stroke.mode==='add');
}
function bounded<T>(promise:Promise<T>,milliseconds:number):Promise<T>{
  let timer:ReturnType<typeof setTimeout>|undefined;
  return Promise.race([promise,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('状态等待超时')),milliseconds);})])
    .finally(()=>{if(timer!==undefined)clearTimeout(timer);});
}
/** App lifetime owner: hiding/unmounting a panel must not destroy an apply receipt. */
export class ExpressionController {
  private state:State=initial();
  private readonly listeners=new Set<()=>void>();
  private generation=0;
  private querying=false;
  private cancelling=false;
  constructor(private readonly port:ExpressionPort,private readonly options:{id?:()=>string;timeoutMs?:number;onCommitted?:(receipt:Extract<Receipt,{phase:'committed'}>)=>void}={}){
    if(port.protocol!==1||port.capability.protocol!==1||port.capability.operation_id!==OPERATION_ID)throw Error('表情模块接口版本不匹配，不能创建写入通道。');
  }
  snapshot=():State=>this.state;
  subscribe=(listener:()=>void):(()=>void)=>{this.listeners.add(listener);return()=>{this.listeners.delete(listener);};};
  private publish(patch:Partial<State>):void{this.state=freeze({...this.state,...patch});this.listeners.forEach(listener=>listener());}
  private id():string{return this.options.id?.()??crypto.randomUUID();}
  private wait<T>(promise:Promise<T>):Promise<T>{return bounded(promise,Math.max(100,this.options.timeoutMs??15000));}
  private pendingApply():boolean{return !!this.state.request&&this.state.request.command.action==='apply'&&['sending','apply_pending','unknown'].includes(this.state.phase);}
  private release(preview:Preview|null):void{if(!preview)return;try{void this.port.releasePreview(preview.preview_token).catch(()=>{/* Host expiry retains cleanup authority. */});}catch{/* Cleanup failure never changes document state or permits another write. */}}
  private invalidate():void{
    this.release(this.state.preview);++this.generation;
    this.publish({preview:null,preview_packet:null,request:null,receipt:null,reviewed:false,confirmations:{},cancel_requested:false,phase:'idle',message:''});
  }
  bind(value:Current|null):void {
    if(value&&!validCurrent(value))value=null;
    if(value&&!this.port.capability.available)value={...value,available:false,unavailable_reason:this.port.capability.reason||'表情替换宿主能力不可用。'};
    if(contextKey(value)===contextKey(this.state.current))return;
    ++this.generation;
    if(this.pendingApply()){
      // Keep the old exact command and lease. Never call its apply again.
      this.publish({current:value,target_ref:null,target_displayed:false,donor_displayed:false,reviewed:false,
        message:'照片或编辑上下文已变化；原操作仍待确认，不会重发，也不会当作取消。'});return;
    }
    if(this.state.request){
      this.publish({current:value,target_ref:null,target_displayed:false,donor_displayed:false,reviewed:false});
      this.cancel();return;
    }
    this.release(this.state.preview);
    this.publish({...initial(),current:value,message:value?'请先选择当前照片的人脸，再选取另一张照片中的本人表情。':'当前来源或定位证据无效，不能开始。'});
  }
  private editable():void{if(locked(this.state)||!this.state.current?.available)throw Error('当前上下文不可编辑，或上一次操作尚未确认。');}
  selectTarget(ref:FaceRef):void {
    this.editable();const face=selectedFace(this.state.current!.photo,ref);
    if(!face?.enabled)throw Error('当前人脸无有效来源证据或已停用。');
    this.invalidate();this.publish({target_ref:face.face_ref,fusion:emptyFusion()});
  }
  selectDonor(ref:FaceRef):void {
    this.editable();const face=selectedFace(this.state.donor,ref);
    if(!face?.enabled)throw Error('素材人脸无有效来源证据或已停用。');
    this.invalidate();this.publish({donor_ref:face.face_ref});
  }
  async chooseDonor():Promise<void>{
    this.editable();this.invalidate();const token=this.generation;
    const command:DonorCommand=freeze({version:1,operation_id:OPERATION_ID,action:'choose_donor',request_id:this.id(),binding:this.state.current!.binding});
    this.publish({donor:null,donor_ref:null,donor_displayed:false,phase:'choosing',message:'请选择真实表情素材；选取与分析由这一明确请求持有。'});
    let sent:Packet<DonorCommand>;
    try{sent=await packet(command);}catch{if(token===this.generation)this.publish({phase:'rejected',message:'素材请求摘要未生成，未发送。'});return;}
    if(token!==this.generation)return;
    this.publish({request:sent});
    try{await this.wait(this.port.chooseDonor(sent).then(result=>this.receive(result,sent)));}
    catch{if(this.state.request?.command.request_id===sent.command.request_id)this.publish({phase:'unknown',message:'素材选取或分析仍待确认；可查询或请求取消原请求。'});}
  }
  displayed(which:'target'|'donor',key:string,ready:boolean):void {
    const expected=sourceDisplayKey(which==='target'?this.state.current?.photo??null:this.state.donor);
    if(!key||key!==expected)return;
    if(this.state[`${which}_displayed`]===ready)return;
    if(!ready&&!this.pendingApply()){
      // Also cancel a still-hashing, unsent apply; a sent request retains its lease.
      this.cancel();
      if(!this.state.request)this.publish({message:'来源全图显示中断，未提交候选和旧复核已失效。'});
    }
    this.publish(which==='target'?{target_displayed:ready}:{donor_displayed:ready});
  }
  setFusion(fusion:FusionMask):void {
    this.editable();const target=selectedFace(this.state.current!.photo,this.state.target_ref);
    if(!target||!this.state.target_displayed||!validFusion(fusion,this.state.current!.photo.source,target))throw Error('融合笔迹超出当前面部上下文，或完整来源图尚未显示。');
    this.invalidate();this.publish({fusion});
  }
  setSettings(settings:Settings):void {
    this.editable();if(!Number.isFinite(settings.density)||settings.density<=0||settings.density>1||!Number.isInteger(settings.pyramid_levels)||settings.pyramid_levels<1||settings.pyramid_levels>5||settings.colour_match_strength!==0)throw Error('融合设置不受支持。');
    this.invalidate();this.publish({settings});
  }
  confirm(key:Confirmation,value:boolean):void {
    this.editable();if(!this.state.target_displayed||!this.state.donor_displayed||!selection(this.state))throw Error('请先加载两张完整来源图并选择人脸。');
    if(this.state.preview){this.release(this.state.preview);this.publish({phase:'idle',preview:null,preview_packet:null,reviewed:false});}
    this.publish({confirmations:{...this.state.confirmations,[key]:value}});
  }
  reviewed(key:string,ready:boolean):void {
    if(this.state.phase!=='ready'||key!==previewKey(this.state)||!key)return;
    this.publish({reviewed:ready});
  }
  async preview():Promise<void>{
    if(!canPreview(this.state))throw Error('请先完成两张来源图、人脸、融合范围与逐项确认。');
    const owners=selection(this.state)!;
    const command=previewCommand({version:1,operation_id:OPERATION_ID,action:'preview',request_id:this.id(),binding:this.state.current!.binding,
      ...owners,fusion:this.state.fusion,settings:this.state.settings,confirmations:this.state.confirmations as Confirmations});
    this.release(this.state.preview);const token=++this.generation;
    this.publish({phase:'preparing',preview:null,preview_packet:null,reviewed:false,request:null,receipt:null,message:'正在生成真实全图候选；尚未修改照片。'});
    let sent:Packet<PreviewCommand>;
    try{sent=await packet(command);}catch{if(token===this.generation)this.publish({phase:'rejected',message:'命令摘要未生成，未发送。'});return;}
    if(token!==this.generation)return;
    this.publish({request:sent,preview_packet:sent,phase:'preview_pending'});
    try{await this.wait(this.port.preview(sent).then(result=>this.receive(result,sent)));}
    catch{if(token===this.generation&&this.state.request?.command.request_id===sent.command.request_id)this.publish({phase:'unknown',message:'候选状态未确认；可查询原请求，或丢弃未提交候选。'});}
  }
  async apply():Promise<void>{
    if(this.state.phase!=='ready'||!this.state.reviewed||!this.state.preview||!this.state.preview_packet||!this.state.current?.available||!this.state.target_displayed||!this.state.donor_displayed||CONFIRMATION_KEYS.some(key=>this.state.confirmations[key]!==true))throw Error('请完整查看并确认当前候选后再应用。');
    if(!same(this.state.current.binding,this.state.preview_packet.command.binding))throw Error('候选所属上下文已变化，请重新生成。');
    const p=this.state.preview,origin=this.state.preview_packet;
    const command:ApplyCommand=freeze({version:1,operation_id:OPERATION_ID,action:'apply',request_id:this.id(),binding:origin.command.binding,return_mode:'new_image',
      preview_request_id:origin.command.request_id,preview_command_sha256:origin.command_sha256,preview_token:p.preview_token,
      candidate_sha256:p.candidate_sha256,fusion_mask_sha256:p.fusion_mask_sha256,before_image_sha256:p.before.sha256,after_image_sha256:p.after.sha256,fusion_image_sha256:p.fusion_image.sha256,
      review:'full_before_after_and_fusion_confirmed'});
    const token=this.generation;
    this.publish({phase:'sending',reviewed:false,request:null,message:'正在保存一次独立结果副本；原照片不覆盖，未确认前不会重发。'});
    let sent:Packet<ApplyCommand>;
    try{sent=await packet(command);}catch{if(token===this.generation)this.publish({phase:'ready',message:'命令摘要未生成，未发送；请重新确认预览。'});return;}
    if(token!==this.generation)return;
    // Set the immutable request before invoking the possibly-writing transport.
    this.publish({request:sent});
    try{await this.wait(this.port.apply(sent).then(result=>this.receive(result,sent)));}
    catch{if(this.state.request===sent||this.state.request?.command.request_id===sent.command.request_id)this.publish({phase:'unknown',message:'提交结果未确认；仅查询原请求，不会重发或宣称已取消。'});}
  }
  private receive(value:unknown,sent:Packet):void {
    const receipt=parseReceipt(value,sent),isApply=sent.command.action==='apply';
    if(this.state.request?.command.request_id!==sent.command.request_id){
      if(!isApply&&receipt?.phase==='ready'&&receipt.preview.preview_token!==this.state.preview?.preview_token)this.release(receipt.preview);
      return;
    }
    if(!receipt){this.publish({phase:'unknown',message:'回执缺失、矛盾或身份不匹配，不能宣称已应用；请查询原请求。'});return;}
    if(receipt.phase==='pending'||receipt.phase==='unknown'||receipt.phase==='cancelling'){
      this.publish({receipt,cancel_requested:this.state.cancel_requested||receipt.phase==='cancelling',phase:this.state.cancel_requested?'cancelling':receipt.phase==='unknown'?'unknown':receipt.phase==='cancelling'?'cancelling':isApply?'apply_pending':sent.command.action==='choose_donor'?'choosing':'preview_pending',message:receipt.message||'原请求仍待确认，不会重发。'});return;
    }
    if(receipt.phase==='cancelled'){
      this.release(this.state.preview);this.publish({receipt,phase:'idle',request:null,preview:null,preview_packet:null,reviewed:false,confirmations:{},cancel_requested:false,message:receipt.message||'原只读任务已确认取消，照片未修改。'});return;
    }
    if(!isApply&&this.state.cancel_requested&&(receipt.phase==='ready'||receipt.phase==='donor_ready')){
      // First-terminal-wins native mailboxes cannot rewrite a finished read as cancelled.
      // Exact receipt identity was already verified above. Only discard completed reads.
      if(receipt.phase==='ready')this.release(receipt.preview);
      this.publish({receipt,phase:'idle',request:null,preview:null,preview_packet:null,reviewed:false,confirmations:{},cancel_requested:false,
        message:'原只读任务已完成，晚到结果已丢弃；没有保存副本，也不宣称任务被取消。'});return;
    }
    if(receipt.phase==='donor_ready'){
      if(receipt.photo.source.asset_sha256===sent.command.binding.source.asset_sha256||receipt.photo.source.original_sha256===sent.command.binding.source.original_sha256){
        this.publish({receipt,phase:'rejected',request:null,message:'请选择不同原片的表情素材，当前照片未修改。'});return;
      }
      this.publish({receipt,phase:'idle',request:null,donor:receipt.photo,donor_ref:null,donor_displayed:false,message:'请在素材中明确选择本人；不会按相似度自动关联身份。'});return;
    }
    if(receipt.phase==='rejected'){
      this.release(this.state.preview);this.publish({receipt,phase:'rejected',cancel_requested:false,request:null,preview:null,preview_packet:null,reviewed:false,message:`未写入照片：${receipt.message}`});return;
    }
    if(receipt.phase==='ready'){
      this.publish({receipt,phase:'ready',request:null,preview:receipt.preview,preview_packet:sent as Packet<PreviewCommand>,reviewed:false,message:'候选已就绪；完整查看前后效果并确认后才可应用。'});return;
    }
    if(receipt.phase==='committed'){
      const changed=!this.state.current||!same(this.state.current.binding,sent.command.binding);
      this.publish({receipt,phase:'committed',request:null,preview:null,preview_packet:null,reviewed:false,
        message:`${changed?'先前照片':'当前照片'}的独立结果副本已保存：${receipt.result_document_id}。原照片保持不变${receipt.no_change?'；本次像素未产生变化':''}。`});
      try{this.options.onCommitted?.(receipt);}catch{this.publish({message:'已有匹配副本保存回执，但状态刷新未完成。请刷新，不要重复保存。'});}
    }
  }
  async reconcile():Promise<void>{
    const sent=this.state.request;if(!sent||this.querying)return;
    this.querying=true;
    try{await this.wait(this.port.status(sent.command.request_id,sent.command_sha256).then(result=>this.receive(result,sent)));}
    catch{if(this.state.request?.command.request_id===sent.command.request_id)this.publish({phase:'unknown',message:'原请求状态仍不可用；不会重发，也不会把未知结果作为失败重试。'});}
    finally{this.querying=false;}
  }
  canDetach():boolean{return !this.state.request&&!['sending','choosing','preparing','cancelling'].includes(this.state.phase);}
  dispose():void {
    if(!this.canDetach())throw Error('未终结任务仍由此模块持有，不能卸载或替换控制器。');
    this.cancel();this.listeners.clear();
  }
  cancel():void {
    if(this.pendingApply()){this.publish({reviewed:false,message:'保存已发送，不能当作未提交取消；请查询原操作结果。'});return;}
    const sent=this.state.request;
    if(sent){
      if(this.state.cancel_requested)return;
      ++this.generation;this.publish({phase:'cancelling',cancel_requested:true,reviewed:false,confirmations:{},message:'已请求取消原只读任务；等待任务退出回执，不宣称已强制停止。'});
      void this.requestCancel(sent);return;
    }
    this.invalidate();this.publish({fusion:emptyFusion(),message:'未提交的候选已丢弃，当前照片未修改。'});
  }
  private async requestCancel(sent:Packet):Promise<void>{
    if(sent.command.action==='apply'||this.cancelling)return;
    this.cancelling=true;
    try{await this.wait(this.port.cancel(freeze({version:1,operation_id:OPERATION_ID,request_id:sent.command.request_id,command_sha256:sent.command_sha256})).then(result=>this.receive(result,sent)));}
    catch{if(this.state.request?.command.request_id===sent.command.request_id)this.publish({phase:'cancelling',message:'取消结果尚未确认；仅查询原请求，不会重新选取或生成候选。'});}
    finally{this.cancelling=false;}
  }
}
