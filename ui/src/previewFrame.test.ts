import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {parseFrameHead} from './previewFrame.ts';
function golden(){const h=readFileSync(new URL('../../docs/protocols/preview-frame-v1.hex',import.meta.url),'utf8').trim();return Uint8Array.from(h.match(/../g)!.map(x=>parseInt(x,16))).buffer;}
test('preview golden preserves identity independently of raster and presentation dimensions',()=>{
 const f=parseFrameHead(golden());assert.equal(f.seqId,'9007199254740993');assert.equal(f.w,2);assert.equal(f.h,2);
 assert.equal(f.presentation?.width,4000);assert.equal(f.presentation?.documentId,'4');assert.equal(f.headerBytes,128);
 assert.deepEqual([...f.pixels],Array.from({length:16},(_,i)=>i));
});
test('invalid version, geometry, reserved fields, partial rows and payload lengths rejected',()=>{
 for(const offset of [4,6,76,96,100]){const b=golden();new DataView(b).setUint32(offset,0xffffffff,true);assert.throws(()=>parseFrameHead(b));}
 for(const n of [0,39,127,143,145]){const b=new Uint8Array(n);b.set(new Uint8Array(golden()).subarray(0,n));assert.throws(()=>parseFrameHead(b.buffer));}
 const b=golden();new DataView(b).setUint32(44,1,true);assert.throws(()=>parseFrameHead(b));
});
test('legacy header remains unidentified and zero-payload benchmark frames do not claim pixels',()=>{
 const b=new ArrayBuffer(44),v=new DataView(b);v.setBigUint64(0,7n,true);v.setUint32(24,1,true);v.setUint32(28,1,true);v.setUint32(32,4,true);
 const old=parseFrameHead(b);assert.equal(old.presentation,null);assert.equal(old.instance,null);assert.equal(old.headerBytes,40);
 const zero=golden().slice(0,128);new DataView(zero).setUint32(40,0,true);assert.equal(parseFrameHead(zero).rows,0);
});
