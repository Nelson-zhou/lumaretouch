import type {CurveSpec} from './native';
export type CurveSolver=(spec:CurveSpec,region:number,target:number)=>Promise<{spec:CurveSpec;y:number}>;
type Ports={send:(spec:CurveSpec,id:string,interactive:boolean)=>void|Promise<void>;busy:(value:boolean)=>void;error:(text:string)=>void};
type Active={id:string;before:CurveSpec;last:CurveSpec;sequence:number;closing:boolean;cancelled:boolean;hasInput:boolean;pending:Promise<CurveSpec>|null};
export function boundedCurveSolve<T>(promise:Promise<T>,milliseconds=3000):Promise<T>{
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error('曲线计算超时，保留上次有效值')),milliseconds);
    promise.then(v=>{clearTimeout(timer);resolve(v);},e=>{clearTimeout(timer);reject(e);});
  });
}
/** One gesture owns one history ID. Final dispatch waits for its newest native
 * inverse solve; cancellation/unmount invalidate late replies, never reapply them. */
export class ParametricGesture {
  private active:Active|null=null;
  private finishing:Promise<void>=Promise.resolve();
  private ports:Ports;private solver:CurveSolver;private bound:<T>(p:Promise<T>)=>Promise<T>;
  constructor(ports:Ports,solver:CurveSolver,bound:<T>(p:Promise<T>)=>Promise<T>=boundedCurveSolve){
    this.ports=ports;this.solver=solver;this.bound=bound;
  }
  get busy(){return this.active!==null;}
  get closing(){return this.active?.closing??false;}
  begin(spec:CurveSpec,id=crypto.randomUUID()):boolean{
    if(this.active)return false;
    this.active={id,before:structuredClone(spec),last:structuredClone(spec),sequence:0,closing:false,cancelled:false,hasInput:false,pending:null};
    this.finishing=Promise.resolve();this.ports.busy(true);return true;
  }
  apply(spec:CurveSpec):void{
    const a=this.active;if(!a||a.closing)return;
    a.hasInput=true;++a.sequence;a.pending=null;a.last=structuredClone(spec);this.ports.send(a.last,a.id,true);
  }
  solve(region:number,target:number):void{
    const a=this.active;if(!a||a.closing)return;a.hasInput=true;const sequence=++a.sequence;
    // Resolve failures into the last valid recipe, so no abandoned rejection can
    // escape when another pointer move supersedes this request.
    a.pending=this.bound(Promise.resolve().then(()=>this.solver(structuredClone(a.last),region,target)))
      .then(result=>{
        if(this.active===a&&a.sequence===sequence&&!a.closing){a.last=structuredClone(result.spec);this.ports.send(a.last,a.id,true);}
        return result.spec;
      },error=>{
        if(this.active===a&&a.sequence===sequence)this.ports.error(String(error));
        return a.last;
      });
  }
  finish(cancel=false):Promise<void>{
    const a=this.active;if(!a)return this.finishing;
    if(!a.hasInput){this.active=null;this.ports.busy(false);return Promise.resolve();}
    if(a.cancelled||(!cancel&&a.closing))return this.finishing;
    a.closing=true;if(cancel)a.cancelled=true;
    this.finishing=(async()=>{
      try{
        const spec=cancel?a.before:a.pending?await a.pending:a.last;
        if(this.active!==a||(!cancel&&a.cancelled))return;
        await this.ports.send(spec,a.id,false);
      }finally{
        if(this.active===a&&(cancel||!a.cancelled)){this.active=null;this.ports.busy(false);}
      }
    })();
    return this.finishing;
  }
  async settle():Promise<void>{
    await this.finish();
    // Esc may replace an already-awaited finish with a cancellation barrier.
    let latest:Promise<void>;
    do{latest=this.finishing;await latest;}while(latest!==this.finishing);
  }
  abort():void{this.active=null;this.ports.busy(false);}
}

export function beginCurvePointer(event:{button:number;preventDefault:()=>void;stopPropagation:()=>void},
  busy:boolean,focus:()=>void,begin:()=>boolean):boolean{
  if(event.button!==0)return false;
  if(busy){event.preventDefault();event.stopPropagation();return false;}
  focus();return begin();
}
