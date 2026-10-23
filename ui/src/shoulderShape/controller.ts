// SPDX-License-Identifier: GPL-3.0-or-later
import {check,neutral,request,viewKey,type Action,type Request,type Result,type ShoulderRecipe,type ShoulderView,type Transport} from './model';
export type State={phase:'idle'|'working'|'uncertain';recipe:ShoulderRecipe;message:string;view:ShoulderView|null};
/** App-lifetime, one inflight + latest unsent intent. No retry after uncertainty. */
export class ShoulderController {
  private value:State={phase:'idle',recipe:neutral(),message:'',view:null};
  private listeners=new Set<()=>void>();private inflight:Request|null=null;
  private pending:{recipe:ShoulderRecipe;gesture:string}|null=null;private context='';
  constructor(private transport:Transport){}
  snapshot=():State=>this.value;
  subscribe=(fn:()=>void)=>{this.listeners.add(fn);return ()=>{this.listeners.delete(fn);};};
  private emit(patch:Partial<State>){this.value={...this.value,...patch};for(const fn of this.listeners)fn();}
  clear(){this.context='';this.pending=null;this.emit({view:null,recipe:neutral(),phase:this.inflight?this.value.phase:'idle',message:this.inflight?'旧照片的请求仍待核对，不会重发。':''});}
  update(view:ShoulderView){
    const key=viewKey(view);const changed=key!==this.context;
    if(!changed&&this.value.view&&view.state_revision<this.value.view.state_revision)return;
    if(!changed&&this.value.view&&(view.association_revision!==this.value.view.association_revision||view.people_association_revision!==this.value.view.people_association_revision))this.pending=null;
    this.context=key;
    if(changed){this.pending=null;this.emit({view,recipe:check(view.recipe),message:this.inflight?'旧目标的请求仍在核对，未发送的拖动已取消。':'',phase:this.inflight?this.value.phase:'idle'});}
    else this.emit({view,...(!this.inflight&&!this.pending?{recipe:check(view.recipe)}:{})});
  }
  edit(change:(value:ShoulderRecipe)=>ShoulderRecipe,gesture:string){
    if(this.value.phase==='uncertain'||!this.value.view)throw Error('请先核对待定结果');
    if(this.inflight&&this.key(this.inflight)!==this.context)throw Error('旧目标的请求尚未核对');
    const recipe=check(change(this.value.recipe));this.pending={recipe,gesture};this.emit({recipe,message:''});void this.flush();
  }
  private key(p:Request){return `${p.document_epoch}:${p.document_id}:${p.body_ref.asset_sha256}:${p.body_ref.body_instance_id}:${p.body_ref.analysis_revision}`;}
  private async flush(){
    if(this.inflight||!this.pending||!this.value.view)return;
    const next=this.pending;this.pending=null;
    const p=request(this.value.view,'recipe',{recipe:next.recipe,base:check(this.value.view.recipe)},next.gesture);
    await this.send(p);
  }
  async action(action:Exclude<Action,'recipe'>,payload:Record<string,unknown>){
    if(this.inflight||this.pending||!this.value.view)throw Error('请先等待当前调整完成');
    return this.send(request(this.value.view,action,payload,crypto.randomUUID()));
  }
  private bounded<T>(promise:Promise<T>):Promise<T>{return new Promise<T>((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('等待超时，请查询原请求，不会重发调整。')),30000);promise.then(value=>{clearTimeout(timer);resolve(value);},error=>{clearTimeout(timer);reject(error);});});}
  private async send(p:Request){
    this.inflight=p;this.emit({phase:'working',message:''});
    try{this.accept(await this.bounded(this.transport.send(p)));}
    catch(error){this.pending=null;this.emit({phase:'uncertain',message:error instanceof Error?error.message:'调整结果暂不明确，请查询，不会自动重发。'});}
  }
  private accept(result:Result){
    const p=this.inflight;if(!p||result.request_id!==p.request_id){this.emit({phase:'uncertain',message:'返回结果与当前请求不一致，请查询。'});return;}
    if(result.phase!=='done'||result.outcome_unknown){this.pending=null;this.emit({phase:'uncertain',message:result.error??result.reason??'结果尚未确定，请查询本次请求。'});return;}
    this.inflight=null;
    if(this.key(p)!==this.context){this.pending=null;this.emit({phase:'idle',message:'旧目标的请求已核对，未改变当前选择。'});return;}
    if(!result.success||!result.view){this.pending=null;this.emit({phase:'idle',recipe:this.value.view?check(this.value.view.recipe):neutral(),message:result.error??'调整未应用。'});return;}
    if(viewKey(result.view)!==this.context){this.pending=null;this.emit({phase:'idle',message:'目标已变化，请刷新当前身体状态。'});return;}
    this.emit({phase:'idle',view:result.view,recipe:this.pending?.recipe??check(result.view.recipe),message:result.rendered===false?`参数已保留但尚未应用：${result.unapplied_reason??'请完成定位确认。'}`:''});
    void this.flush();
  }
  async reconcile(){if(!this.inflight)return;try{this.accept(await this.bounded(this.transport.status(this.inflight.request_id)));}catch(error){this.emit({phase:'uncertain',message:error instanceof Error?error.message:'仍无法确认本次结果。'});}}
}
