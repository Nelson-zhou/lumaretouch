// SPDX-License-Identifier: GPL-3.0-or-later
import {check,neutralFamily,request,viewKey,type Action,type Request,type Result,type Family,type ArmView,type Transport,type Segment,type Strategy} from './model';
export type ControllerState={phase:'idle'|'working'|'uncertain';recipe:Family;message:string;view:ArmView|null};
/** One app-lifetime controller. Latest unsent slider intent, never mutation retry. */
export class ArmController {
 private value:ControllerState={phase:'idle',recipe:neutralFamily(),message:'',view:null};
 private listeners=new Set<()=>void>();private inflight:Request|null=null;private context='';private querying=false;
 private pending:{recipe:Family;targets:Segment[];linked:boolean;gesture:string}|null=null;
 constructor(private transport:Transport){}
 snapshot=():ControllerState=>this.value;
 subscribe=(fn:()=>void)=>{this.listeners.add(fn);return ()=>{this.listeners.delete(fn);};};
 private emit(patch:Partial<ControllerState>){this.value={...this.value,...patch};for(const fn of this.listeners)fn();}
 update(view:ArmView){const key=viewKey(view),changed=key!==this.context,old=this.value.view;if(!changed&&old&&(view.state_revision<old.state_revision||view.binding.document_revision<old.binding.document_revision))return;
  if(changed||(old&&(view.body_graph_sha256!==old.body_graph_sha256||view.people_graph_sha256!==old.people_graph_sha256||view.binding.document_revision!==old.binding.document_revision)))this.pending=null;
  this.context=key;this.emit({view,...(changed||(!this.inflight&&!this.pending)?{recipe:check(view.recipe)}:{}),...(changed?{phase:this.inflight?this.value.phase:'idle',message:this.inflight?'旧目标的请求仍在核对，未发送调整已取消。':''}:{})});
 }
 clear(){this.pending=null;this.context='';this.emit({view:null,recipe:neutralFamily(),phase:this.inflight?this.value.phase:'idle',message:this.inflight?'原请求仍待核对，未发送调整已取消。':''});}
 private key(p:Request){return `${p.document_epoch}:${p.document_id}:${p.body_ref.asset_sha256}:${p.body_ref.body_instance_id}:${p.body_ref.analysis_revision}`;}
 edit(keys:Segment[],linked:boolean,strategy:Strategy,amount:number,gesture:string){
  if(this.value.phase==='uncertain'||!this.value.view||(this.inflight&&this.key(this.inflight)!==this.context))throw Error('请先核对上一请求。');
  const recipe=check(this.value.recipe);for(const key of keys)recipe[key]={version:1,strategy,amount};
  // Retain all still-unsent affected segments if a second control is touched.
  const affected=[...new Set([...(this.pending?.targets??[]),...keys])];
  this.pending={recipe:check(recipe),targets:affected,linked,gesture};this.emit({recipe,message:''});void this.flush();
 }
 private async flush(){if(this.inflight||!this.pending||!this.value.view)return;const next=this.pending;this.pending=null;await this.send(request(this.value.view,'recipe',{base:check(this.value.view.recipe),recipe:next.recipe,targets:next.targets,linked:next.linked},next.gesture));}
 async action(action:Exclude<Action,'recipe'>,payload:Record<string,unknown>){if(this.inflight||this.pending||!this.value.view)throw Error('先等待当前调整完成。');await this.send(request(this.value.view,action,payload));}
 private bounded<T>(promise:Promise<T>):Promise<T>{return new Promise<T>((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('结果未确认，请查询原请求，不会重发。')),30000);promise.then(v=>{clearTimeout(timer);resolve(v);},e=>{clearTimeout(timer);reject(e);});});}
 private async send(p:Request){this.inflight=p;this.emit({phase:'working',message:''});try{const result=await this.bounded(this.transport.send(p));if(this.inflight===p)this.accept(result);}catch(e){if(this.inflight===p){this.pending=null;this.emit({phase:'uncertain',message:e instanceof Error?e.message:'结果未知，请查询。'});}}}
 private accept(result:Result){const p=this.inflight;if(!p||result.request_id!==p.request_id){this.pending=null;this.emit({phase:'uncertain',message:'返回请求不一致，请查询。'});return;}
  if(result.phase!=='done'||result.outcome_unknown){this.pending=null;this.emit({phase:'uncertain',message:result.error??result.reason??'结果尚未确认。'});return;}
  this.inflight=null;if(this.key(p)!==this.context){this.pending=null;this.emit({phase:'idle',message:'旧目标已核对，未改变当前选择。'});return;}
  const current=this.value.view,v=result.view;
  if(!result.success||!v){this.pending=null;this.emit({phase:'idle',recipe:current?check(current.recipe):neutralFamily(),message:result.error??'手臂调整未应用。'});return;}
  if(viewKey(v)!==this.context||(current&&(v.state_revision<current.state_revision||(v.state_revision===current.state_revision&&v.body_graph_sha256!==current.body_graph_sha256)||v.binding.document_revision<current.binding.document_revision))){this.pending=null;this.emit({phase:'idle',recipe:current?check(current.recipe):neutralFamily(),message:'已保留较新状态，请刷新。'});return;}
  if(current&&current.people_graph_sha256!==v.people_graph_sha256)this.pending=null;
  this.emit({phase:'idle',view:v,recipe:this.pending?.recipe??check(v.recipe),message:result.rendered===false?`复核已保存，效果未应用：${result.unapplied_reason??'请解决不可用原因。'}`:''});void this.flush();
 }
 async reconcile(){if(!this.inflight||this.querying)return;const original=this.inflight;this.querying=true;try{const result=await this.bounded(this.transport.status(original.request_id));if(this.inflight===original)this.accept(result);}catch(e){if(this.inflight===original)this.emit({phase:'uncertain',message:e instanceof Error?e.message:'暂不能确认。'});}finally{this.querying=false;}}
}
