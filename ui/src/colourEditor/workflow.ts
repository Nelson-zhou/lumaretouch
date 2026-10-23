import {checked,type Recipe} from './model';
export type Context={document:string;revision:number};
export type Reply={event:string;request_id:string;document_id?:string;revision?:number;preview_id?:string;recipe?:Recipe;frame?:unknown;status?:string;requires_reload?:boolean};
export type Ports={abort?:(id:string)=>Promise<void>;send:(p:Record<string,unknown>)=>Promise<Reply>;show:(frame:unknown,isCurrent:()=>boolean)=>Promise<void>;context:()=>Context;message:(s:string)=>void;committed:(r:Recipe,revision:number)=>void};
/** One active preview plus one replaceable queued intent. Apply is explicit.
 * show() MUST check isCurrent immediately before publishing pixels and resolve only after display. */
export class ColourEditorWorkflow {
  private rangeView=false;
  setRangeView(show:boolean){this.rangeView=show;}
  private inflight:string|null=null;
  private epoch=0;private active=false;private queued:Recipe|null=null;
  private displayed:{id:string;epoch:number;context:Context}|null=null;
  private committing=false;private uncertain:string|null=null;private disposed=false;
  private listeners=new Set<()=>void>();
  constructor(private ports:Ports){}
  subscribe(fn:()=>void){this.listeners.add(fn);return ()=>{this.listeners.delete(fn);};}
  private notify(){for(const fn of this.listeners)fn();}
  private id(){return crypto.randomUUID();}
  private base(action:string,id:string,c=this.ports.context()){return {cmd:'colour_editor',action,request_id:id,document_id:c.document,revision:c.revision};}
  get locked(){return this.committing||this.uncertain!==null;}
  get canApply(){return !this.active&&!this.queued&&!this.committing&&!this.uncertain&&this.displayed!==null;}
  private same(c:Context){const n=this.ports.context();return c.document===n.document&&c.revision===n.revision;}
  preview(r:Recipe){if(this.disposed||this.committing||this.uncertain)return;this.queued=checked(r);this.epoch++;if(this.inflight)void this.ports.abort?.(this.inflight).catch(()=>{});this.displayed=null;this.notify();void this.pump();}
  private async pump(){
    if(this.active||!this.queued||this.disposed)return;this.active=true;
    const recipe=this.queued;this.queued=null;const epoch=this.epoch,c=this.ports.context(),id=this.id();this.inflight=id;
    try{
      const reply=await this.ports.send({...this.base('preview',id,c),recipe,show_range:this.rangeView});
      if(this.disposed||epoch!==this.epoch||!this.same(c))return;
      if(reply.event!=='colour_editor_preview'||reply.request_id!==id||reply.document_id!==c.document||reply.revision!==c.revision||reply.preview_id!==id||!reply.frame)throw Error('色彩编辑器预览回执不匹配');
      await this.ports.show(reply.frame,()=>!this.disposed&&epoch===this.epoch&&this.same(c));
      if(!this.disposed&&epoch===this.epoch&&this.same(c)){this.displayed={id,epoch,context:c};this.ports.message('预览已显示；应用后保存为一条历史记录');}
    }catch(error){if(epoch===this.epoch&&!this.disposed)this.ports.message(String(error));}
    finally{this.inflight=null;this.active=false;this.notify();if(this.queued&&!this.disposed)void this.pump();}
  }
  async apply(){
    if(!this.canApply||!this.displayed)return;
    const shown=this.displayed;if(!this.same(shown.context))return this.invalidate();
    this.committing=true;this.notify();const id=this.id();
    try{
      const r=await this.ports.send({...this.base('commit',id,shown.context),preview_id:shown.id});
      if(r.request_id!==id||r.document_id!==shown.context.document||r.status!=='applied'||!r.recipe||r.revision===undefined)throw Error('色彩编辑器提交结果未确认');
      if(this.same(shown.context)){this.ports.committed(checked(r.recipe),r.revision);if(r.frame)await this.ports.show(r.frame,()=>!this.disposed&&this.same({document:shown.context.document,revision:r.revision!}));}
      this.displayed=null;this.ports.message('色彩编辑器已应用');
    }catch(error){this.uncertain=id;this.ports.message(`${String(error)}。不会自动重发，请查询结果或重新打开照片。`);}
    finally{this.committing=false;this.notify();}
  }
  async query(){
    if(!this.uncertain)return;const id=this.uncertain;
    try{const r=await this.ports.send(this.base('status',id));if(r.request_id!==id)throw Error('回执身份不匹配');
      if(r.status==='applied'&&r.recipe&&r.revision!==undefined&&r.document_id===this.ports.context().document){this.ports.committed(checked(r.recipe),r.revision);this.uncertain=null;this.displayed=null;this.ports.message('已确认色彩编辑器应用成功');this.notify();}
      else this.ports.message(r.requires_reload?'状态恢复需要重新打开照片':'结果仍未确认；请重新打开照片');
    }catch(e){this.ports.message(String(e));}
  }
  reconcileAfterReadback(){if(this.committing)return;this.uncertain=null;this.invalidate();this.ports.message("已核对引擎当前状态；旧请求不会重新发送");}
  invalidate(){if(this.inflight)void this.ports.abort?.(this.inflight).catch(()=>{});this.epoch++;this.queued=null;this.displayed=null;this.notify();}
  async cancel(){
    if(this.committing||this.uncertain){this.ports.message('提交结果待确认，不能将取消视为撤销');return;}
    this.invalidate();const epoch=this.epoch,c=this.ports.context();try{const r=await this.ports.send(this.base('cancel',this.id(),c));if(epoch===this.epoch&&this.same(c)&&!this.disposed&&r.frame)await this.ports.show(r.frame,()=>epoch===this.epoch&&this.same(c)&&!this.disposed);this.ports.message('已取消色彩编辑器预览');}catch(e){this.ports.message(String(e));}
  }
  dispose(){this.disposed=true;this.invalidate();}
}
