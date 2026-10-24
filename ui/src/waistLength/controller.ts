// SPDX-License-Identifier: GPL-3.0-or-later
import {check,neutral,request,viewKey,type Action,type Request,type Result,type WaistLengthRecipe,type WaistLengthView,type Transport} from './model.ts';
import {confirmedPublication} from './receipts.ts';
export type ControllerState={phase:'idle'|'working'|'uncertain';recipe:WaistLengthRecipe;message:string;view:WaistLengthView|null};
/** App-lifetime controller: latest unsent slider intent, never replay uncertainty. */
export class WaistLengthController {
 private value:ControllerState={phase:'idle',recipe:neutral(),message:'',view:null};
 private listeners=new Set<()=>void>();private inflight:Request|null=null;
 private pending:{recipe:WaistLengthRecipe;gesture:string}|null=null;private context='';
 private transport:Transport;private reconciling:Promise<void>|null=null;
 constructor(transport:Transport){this.transport=transport;}
 snapshot=():ControllerState=>this.value;
 subscribe=(fn:()=>void)=>{this.listeners.add(fn);return ()=>{this.listeners.delete(fn);};};
 private emit(patch:Partial<ControllerState>){this.value={...this.value,...patch};for(const fn of this.listeners)fn();}
 clear(){this.context='';this.pending=null;this.emit({view:null,recipe:neutral(),phase:this.inflight?this.value.phase:'idle',message:this.inflight?'旧照片的请求仍待核对，不会重发。':''});}
 update(view:WaistLengthView){
  const key=viewKey(view),changed=key!==this.context,old=this.value.view;
  if(!changed&&old&&(view.state_revision<old.state_revision||view.binding.document_revision<old.binding.document_revision))return;
  if(changed||(old&&(view.body_graph_sha256!==old.body_graph_sha256||view.people_graph_sha256!==old.people_graph_sha256||view.association_revision!==old.association_revision||view.people_association_revision!==old.people_association_revision||view.binding.document_revision!==old.binding.document_revision)))this.pending=null;
  this.context=key;
  if(changed)this.emit({view,recipe:check(view.recipe),message:this.inflight?'旧目标的请求仍在核对，未发送的拖动已取消。':'',phase:this.inflight?this.value.phase:'idle'});
  else this.emit({view,...(!this.inflight&&!this.pending?{recipe:check(view.recipe)}:{})});
 }
 private key(p:Request){return `${p.document_epoch}:${p.document_id}:${p.body_ref.asset_sha256}:${p.body_ref.body_instance_id}:${p.body_ref.analysis_revision}`;}
 edit(change:(recipe:WaistLengthRecipe)=>WaistLengthRecipe,gesture:string){
  if(this.value.phase==='uncertain'||!this.value.view)throw Error('请先核对本次结果。');
  if(this.inflight&&this.key(this.inflight)!==this.context)throw Error('旧目标的请求仍未核对。');
  const recipe=check(change(this.value.recipe));this.pending={recipe,gesture};this.emit({recipe,message:''});void this.flush();
 }
 private async flush(){
  if(this.inflight||!this.pending||!this.value.view)return;
  const next=this.pending;this.pending=null;
  await this.send(request(this.value.view,'recipe',{recipe:next.recipe,base:check(this.value.view.recipe)},next.gesture));
 }
 async action(action:Exclude<Action,'recipe'>,payload:Record<string,unknown>){
  if(this.inflight||this.pending||!this.value.view)throw Error('请先等待当前调整完成。');
  await this.send(request(this.value.view,action,payload,crypto.randomUUID()));
 }
 private bounded<T>(promise:Promise<T>):Promise<T>{return new Promise<T>((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('结果尚未确认，请查询原请求，不会重发。')),30000);promise.then(v=>{clearTimeout(timer);resolve(v);},e=>{clearTimeout(timer);reject(e);});});}
 private async send(p:Request){
  this.inflight=p;this.emit({phase:'working',message:''});
  try{const result=await this.bounded(this.transport.send(p));if(this.inflight===p)this.accept(result);}catch(error){if(this.inflight===p){this.pending=null;this.emit({phase:'uncertain',message:error instanceof Error?error.message:'调整结果暂不明确，请查询。'});}}
 }
 private accept(result:Result){
  const p=this.inflight;
  if(!p)return;
  if(result.request_id!==p.request_id){this.pending=null;this.emit({phase:'uncertain',message:'返回结果与本次请求不一致，请查询。'});return;}
  if(result.phase!=='done'||result.outcome_unknown!==false||typeof result.success!=='boolean'){this.pending=null;this.emit({phase:'uncertain',message:result.error??result.reason??'结果尚未确认。'});return;}
  if(result.success&&!confirmedPublication(result)){this.pending=null;this.emit({phase:'uncertain',message:'成功回执缺少一致的实际发布结果，请查询原请求；不会声称效果已应用。'});return;}
  // Invalid canonical data keeps the original request recoverable rather than
  // clearing inflight and leaving the UI stuck in a working phase.
  const confirmedRecipe=result.success&&result.view?check(result.view.recipe):null;
  this.inflight=null;
  if(this.key(p)!==this.context){this.pending=null;this.emit({phase:'idle',message:'旧目标的请求已核对，未改变当前选择。'});return;}
  if(!result.success||!result.view){this.pending=null;this.emit({phase:'idle',recipe:this.value.view?check(this.value.view.recipe):neutral(),message:result.error??(result.success?'请求已完成，当前状态待刷新；不会重新提交。':'腰部长度调整未应用。')});return;}
  const v=result.view,current=this.value.view;
  if(viewKey(v)!==this.context||(current&&(v.state_revision<current.state_revision||(v.state_revision===current.state_revision&&v.body_graph_sha256!==current.body_graph_sha256)||v.binding.document_revision<current.binding.document_revision))){this.pending=null;this.emit({phase:'idle',recipe:current?check(current.recipe):neutral(),message:'已保留较新的状态，请刷新当前身体结果。'});return;}
  if(current&&(current.people_graph_sha256!==v.people_graph_sha256||p.association_revision!==v.association_revision||p.people_association_revision!==v.people_association_revision))this.pending=null;
  if(result.rendered===false)this.pending=null;
  this.emit({phase:'idle',view:v,recipe:this.pending?.recipe??confirmedRecipe??check(v.recipe),message:result.rendered===false?`参数或复核已保存，但效果尚未应用：${result.unapplied_reason??'请先解决不可用原因。'}`:''});
  void this.flush();
 }
 reconcile():Promise<void>{
  if(this.reconciling)return this.reconciling;const original=this.inflight;if(!original)return Promise.resolve();
  const query=(async()=>{try{const result=await this.bounded(this.transport.status(original.request_id));if(this.inflight===original)this.accept(result);}catch(error){if(this.inflight===original)this.emit({phase:'uncertain',message:error instanceof Error?error.message:'仍无法确认本次结果。'});}})();
  this.reconciling=query;void query.finally(()=>{if(this.reconciling===query)this.reconciling=null;});return query;
 }
}
