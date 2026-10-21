import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {parseInspectionFrame} from './inspectionFrame.ts';

function golden():ArrayBuffer {
  const hex=readFileSync(new URL('../../core/inspection/packet-v1.hex',import.meta.url),'utf8').trim();
  const bytes=Uint8Array.from(hex.match(/../g)!,x=>parseInt(x,16));
  return bytes.buffer as ArrayBuffer;
}
function expected(){return {epoch:'07'.repeat(16),
  ticket:{id:'9007199254740993',document:'2',sourceGeneration:'3',recipe:'4',viewport:'5'},
  canvasWidth:10,canvasHeight:10,roi:{x:1,y:2,width:2,height:1},maxPayloadBytes:8};}

test('shared Python/Rust/JS vector preserves identity through JSON ack',()=>{
  const buffer=golden(),frame=parseInspectionFrame(buffer,expected());
  assert.equal(frame.ticket.id,'9007199254740993');
  assert.equal(JSON.parse(JSON.stringify({ticket:frame.ticket})).ticket.id,'9007199254740993');
  assert.equal(frame.pixels.buffer,buffer);
  assert.deepEqual(Array.from(frame.pixels),[1,2,3,255,4,5,6,255]);
});
test('u64 maximum identity never rounds through Number',()=>{
  const buffer=golden(),e=expected();e.ticket.id='18446744073709551615';
  new DataView(buffer).setBigUint64(24,18446744073709551615n,true);
  assert.equal(parseInspectionFrame(buffer,e).ticket.id,e.ticket.id);
});
test('rejects truncated, trailing, stale and unknown envelope bytes',()=>{
  for(const size of [0,127,128,135])assert.throws(()=>parseInspectionFrame(golden().slice(0,size),expected()));
  const extra=new Uint8Array(137);extra.set(new Uint8Array(golden()));
  assert.throws(()=>parseInspectionFrame(extra.buffer,expected()));
  for(const offset of [0,4,6,8,24,32,40,48,56,64,68,72,76,80,84,88,96,100,102,104,108,127,131]){
    const buffer=golden();new Uint8Array(buffer)[offset]^=2;
    assert.throws(()=>parseInspectionFrame(buffer,expected()),`offset ${offset}`);
  }
});
test('budget and expected identity representation are strict',()=>{
  const e=expected();e.maxPayloadBytes=7;assert.throws(()=>parseInspectionFrame(golden(),e));
  for(const bad of ['09007199254740993','-1','1e3','18446744073709551616']){
    const e=expected();e.ticket.id=bad;assert.throws(()=>parseInspectionFrame(golden(),e));
  }
  const bad=expected();bad.ticket.id=9007199254740992 as unknown as string;
  assert.throws(()=>parseInspectionFrame(golden(),bad));
});

test('shared mutable memory is not an accepted IPC packet',()=>{
  const shared=new SharedArrayBuffer(136);
  new Uint8Array(shared).set(new Uint8Array(golden()));
  assert.throws(()=>parseInspectionFrame(shared as unknown as ArrayBuffer,expected()));
});

test('resizable packet buffers are rejected',()=>{
  const buffer=new ArrayBuffer(136,{maxByteLength:256});
  new Uint8Array(buffer).set(new Uint8Array(golden()));
  assert.throws(()=>parseInspectionFrame(buffer,expected()));
});
test('rejects unsafe budgets and precision metadata',()=>{
  for(const n of [NaN,Infinity,-1,.5,Number.MAX_SAFE_INTEGER+1]){
    const e=expected();e.maxPayloadBytes=n;assert.throws(()=>parseInspectionFrame(golden(),e));
  }
  for(const [offset,n] of [[104,12],[106,33]]){
    const b=golden();new DataView(b).setUint16(offset,n,true);
    assert.throws(()=>parseInspectionFrame(b,expected()));
  }
  const e=expected();e.epoch='00'.repeat(16);assert.throws(()=>parseInspectionFrame(golden(),e));
});
test('borrowed pixels require caller ownership until upload completes',()=>{
  const buffer=golden(),frame=parseInspectionFrame(buffer,expected());
  new Uint8Array(buffer)[128]=99;
  assert.equal(frame.pixels[0],99); // intentionally not an immutable copy
});
