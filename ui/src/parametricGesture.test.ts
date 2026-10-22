import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ParametricGesture,boundedCurveSolve,beginCurvePointer,type CurveSolver} from './parametricGesture.ts';
import {parametricCurveSpec} from './curveModel.ts';
import {registerCurveEditBarrier,settleCurveEdit,curveBarrierRequired,isCurveEditBusy} from './curveEditBarrier.ts';
import type {CurveSpec} from './native';
const base=():CurveSpec=>({version:2,space:'srgb-display',interpolation:'pchip',boundary:'linear',enabled:true,
  master:[[0,0],[1,1]],red:[[0,0],[1,1]],green:[[0,0],[1,1]],blue:[[0,0],[1,1]],
  luminance_space:'linear-srgb-y-ratio',luminance:[[0,0],[1,1]]});
const value=(n:number)=>{const s=parametricCurveSpec(base());s.parametric.shadows=n;return s;};
function deferred<T>(){let resolve!:(value:T)=>void;let reject!:(error:unknown)=>void;
  const promise=new Promise<T>((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
const turn=()=>new Promise<void>(resolve=>setImmediate(resolve));
function setup(solver:CurveSolver,bound=<T>(p:Promise<T>)=>p){
  const sent:{spec:CurveSpec;id:string;interactive:boolean}[]=[];const busy:boolean[]=[];const errors:string[]=[];
  const g=new ParametricGesture({send:(spec,id,interactive)=>sent.push({spec:structuredClone(spec),id,interactive}),
    busy:v=>busy.push(v),error:s=>errors.push(s)},solver,bound);
  return {g,sent,busy,errors};
}
test('final barrier waits for newest native solve and ignores an older late reply',async()=>{
  const a=deferred<{spec:CurveSpec;y:number}>(),b=deferred<{spec:CurveSpec;y:number}>();let n=0;
  const {g,sent}=setup(()=>++n===1?a.promise:b.promise);g.begin(base(),'gesture');g.solve(0,.2);g.solve(0,.3);
  const end=g.finish();await turn();assert.equal(sent.length,0);
  b.resolve({spec:value(30),y:.3});await end;assert.equal(sent.length,1);assert.equal(sent[0].interactive,false);
  assert.equal(sent[0].spec.parametric?.shadows,30);assert.equal(sent[0].id,'gesture');
  a.resolve({spec:value(20),y:.2});await turn();assert.equal(sent.length,1);
});
test('cancel restores complete pre-upgrade recipe and blocks late native application',async()=>{
  const d=deferred<{spec:CurveSpec;y:number}>();const {g,sent,busy}=setup(()=>d.promise);const original=base();original.red[0][1]=.1;
  g.begin(original,'cancel');g.solve(0,.2);await g.finish(true);
  assert.deepEqual(sent[0].spec,original);assert.equal(sent[0].spec.version,2);assert.deepEqual(busy,[true,false]);
  d.resolve({spec:value(99),y:.9});await turn();assert.equal(sent.length,1);
});
test('unmount or authoritative failure aborts without late writes',async()=>{
  const d=deferred<{spec:CurveSpec;y:number}>();const {g,sent}=setup(()=>d.promise);
  g.begin(base());g.solve(0,.2);g.abort();d.resolve({spec:value(99),y:.9});await turn();assert.equal(sent.length,0);
});
test('synchronous sliders share history identity and finish with one final barrier',async()=>{
  const {g,sent}=setup(async()=>({spec:value(0),y:0}));g.begin(base(),'range');g.apply(value(10));g.apply(value(20));await g.finish();await g.finish();
  assert.deepEqual(sent.map(v=>v.interactive),[true,true,false]);assert.ok(sent.every(v=>v.id==='range'));
  assert.equal(sent[2].spec.parametric?.shadows,20);
});
test('native failure retains last valid value and closes with visible error',async()=>{
  const {g,sent,errors}=setup(async()=>{throw new Error('native failure');});g.begin(base(),'failure');g.apply(value(12));g.solve(0,.3);await g.finish();
  assert.equal(sent.at(-1)?.spec.parametric?.shadows,12);assert.equal(sent.at(-1)?.interactive,false);assert.match(errors[0],/native failure/);
});
test('closing rejects more edits and a second gesture until its final request settles',async()=>{
  const d=deferred<{spec:CurveSpec;y:number}>();const {g,sent}=setup(()=>d.promise);g.begin(base());g.solve(0,.2);const end=g.finish();
  assert.equal(g.begin(base()),false);g.apply(value(88));d.resolve({spec:value(20),y:.2});await end;
  assert.equal(sent.length,1);assert.equal(sent[0].spec.parametric?.shadows,20);assert.equal(g.busy,false);
});
test('bounded native timeout settles the gesture and ignores a later success',async()=>{
  const d=deferred<{spec:CurveSpec;y:number}>();const {g,sent,errors}=setup(()=>d.promise,p=>boundedCurveSolve(p,1));
  g.begin(base());g.solve(0,.2);await g.finish();assert.equal(g.busy,false);assert.match(errors[0],/超时/);
  d.resolve({spec:value(99),y:.9});await turn();assert.equal(sent.length,1);assert.deepEqual(sent[0].spec,base());
});

test('selecting a handle without moving does not upgrade or dirty the recipe',async()=>{
  const {g,sent}=setup(async()=>({spec:value(0),y:0}));g.begin(base());await g.finish();assert.equal(sent.length,0);
  g.begin(base());await g.finish(true);assert.equal(sent.length,0);
});

test('cancel after native v3 migration retains a v1 field set exactly',async()=>{
  const original=base();original.version=1;delete original.luminance;delete original.luminance_space;
  const {g,sent}=setup(async()=>({spec:value(25),y:.2}));g.begin(original);g.solve(0,.2);await turn();await g.finish(true);
  assert.deepEqual(sent.at(-1)?.spec,original);assert.equal(sent.at(-1)?.spec.version,1);
});

test('external history waits for newest solve and its final host enqueue acknowledgement',async()=>{
  const solve=deferred<{spec:CurveSpec;y:number}>(),ack=deferred<void>();const order:string[]=[];
  const g=new ParametricGesture({send:async()=>{order.push('curve-sent');await ack.promise;order.push('curve-enqueued');},busy:()=>{},error:()=>{}},()=>solve.promise,p=>p);
  const remove=registerCurveEditBarrier(()=>g.settle());
  try{g.begin(base());g.solve(0,.2);const external=settleCurveEdit().then(()=>order.push('undo-sent'));await turn();assert.deepEqual(order,[]);
    solve.resolve({spec:value(20),y:.2});await turn();assert.deepEqual(order,['curve-sent']);
    ack.resolve();await external;assert.deepEqual(order,['curve-sent','curve-enqueued','undo-sent']);
  }finally{remove();}
});
test('external barrier follows cancellation replacing a pending final solve',async()=>{
  const solve=deferred<{spec:CurveSpec;y:number}>(),ack=deferred<void>();const sent:CurveSpec[]=[];let proceeded=false;
  const g=new ParametricGesture({send:async spec=>{sent.push(spec);await ack.promise;},busy:()=>{},error:()=>{}},()=>solve.promise,p=>p);
  g.begin(base());g.solve(0,.2);const external=g.settle().then(()=>{proceeded=true;});const cancel=g.finish(true);
  solve.resolve({spec:value(99),y:.9});await turn();assert.equal(proceeded,false);assert.deepEqual(sent,[base()]);
  ack.resolve();await cancel;await external;assert.equal(proceeded,true);assert.equal(sent.length,1);
});
test('curve barrier excludes own writes and pure state reads, not undo or preset application',()=>{
  assert.equal(curveBarrierRequired('curves','set',true),false);
  assert.equal(curveBarrierRequired('history','state',true),false);
  assert.equal(curveBarrierRequired('history','undo',true),true);
  assert.equal(curveBarrierRequired('preset','apply',true),true);
  assert.equal(curveBarrierRequired('engine_status',undefined,false),false);
});

test('idle editors keep normal dispatch timing and old cleanup cannot clear a newer barrier',async()=>{
  const old=registerCurveEditBarrier(async()=>{},()=>false);assert.equal(isCurveEditBusy(),false);
  let called=false;const newer=registerCurveEditBarrier(async()=>{called=true;},()=>true);old();
  assert.equal(isCurveEditBusy(),true);await settleCurveEdit();assert.equal(called,true);newer();assert.equal(isCurveEditBusy(),false);
});

test('secondary pointer cannot focus another control or trigger its native default',()=>{
  const order:string[]=[];const event={button:0,preventDefault:()=>order.push('prevent'),stopPropagation:()=>order.push('stop')};
  const accepted=beginCurvePointer(event,true,()=>order.push('focus'),()=>{order.push('begin');return true;});
  assert.equal(accepted,false);assert.deepEqual(order,['prevent','stop']);
});
test('idle pointer focuses the destination before beginning a new history gesture',()=>{
  const order:string[]=[];const event={button:0,preventDefault:()=>order.push('prevent'),stopPropagation:()=>order.push('stop')};
  assert.equal(beginCurvePointer(event,false,()=>order.push('focus'),()=>{order.push('begin');return true;}),true);
  assert.deepEqual(order,['focus','begin']);
});
