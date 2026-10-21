import { test } from 'node:test';
import assert from 'node:assert/strict';
import { captureOriginal, compareImageKey, comparisonFrameSize } from './compareCapture.ts';
const frame = {seq:7,w:2,h:1,pixelLen:8,pixels:new Uint8Array(8),y0:0,rows:1};
const receipt = {capture_id:'new',doc:'/a',seq:7,view:'original'};
function setup() {
  let clock=0;
  return {id:'new',doc:'/a',cancelled:()=>false,request:async (_id:string)=>{},
    receipt:async()=>receipt,pixels:async()=>frame,now:()=>clock,
    wait:async()=>{clock+=100;},timeoutMs:500};
}
test('polling object identity does not restart capture; reload does',()=>{
  const image={doc:'/a',load_id:'1',w:2,h:1,src_w:20,src_h:10};
  assert.equal(compareImageKey(image),compareImageKey({...image}));
  assert.notEqual(compareImageKey(image),compareImageKey({...image,load_id:'2'}));
  assert.notEqual(compareImageKey(image),compareImageKey({...image,doc:'/b'}));
});
test('accept exact request and complete nonempty frame',async()=>{
  assert.equal(await captureOriginal(setup()),frame);
});
for(const patch of [{capture_id:'old'},{doc:'/b'},{view:'edited'},{seq:6}]) {
  test(`reject stale receipt ${JSON.stringify(patch)}`,async()=>{
    const o=setup();o.receipt=async()=>({...receipt,...patch});
    await assert.rejects(captureOriginal(o),/超时/);
  });
}
test('empty/partial buffers are not originals',async()=>{
  const o=setup();o.pixels=async()=>({...frame,pixelLen:0,pixels:new Uint8Array()});
  await assert.rejects(captureOriginal(o),/超时/);
});
test('cancel in-flight pixels rejects stale result',async()=>{
  const o=setup();let cancelled=false;o.cancelled=()=>cancelled;
  o.pixels=async()=>{cancelled=true;return frame;};
  assert.equal(await captureOriginal(o),null);
});
test('slow receipt succeeds beyond old 180ms assumption',async()=>{
  const o=setup();o.timeoutMs=2000;let calls=0;
  o.receipt=async()=>++calls<8?{...receipt,capture_id:'old'}:receipt;
  assert.equal(await captureOriginal(o),frame);assert.equal(calls,8);
});

test('side-by-side preserves two complete equal-scale frames',()=>{
  assert.deepEqual(comparisonFrameSize(220,275,'split'),{w:440,h:275});
  assert.deepEqual(comparisonFrameSize(600,400,'split'),{w:1200,h:400});
  assert.deepEqual(comparisonFrameSize(220,275,'swipe'),{w:220,h:275});
  assert.deepEqual(comparisonFrameSize(220,275,'single'),{w:220,h:275});
});

test('identified comparison refuses reused sequence from another mapping or document',async()=>{
 const base=setup();
 const goodFrame={...frame,seqId:'7',instance:'a',presentation:{documentId:'123',kind:2}};
 const goodReceipt={...receipt,seq_id:'7',shm_instance:'a',document_id:'123'};
 const o={...base,documentId:'123',pixels:async()=>goodFrame,receipt:async()=>goodReceipt};
 assert.equal(await captureOriginal(o),goodFrame);
 o.pixels=async()=>({...goodFrame,instance:'b'});await assert.rejects(captureOriginal(o),/超时/);
});
