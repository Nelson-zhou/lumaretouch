import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {parseCaptureFrame} from './captureFrame.ts';
import type {CaptureDescriptor} from './captureModel';
const descriptor:CaptureDescriptor={version:1,epoch:'0102030405060708090a0b0c0d0e0f10',
  shm_instance:'1112131415161718191a1b1c1d1e1f20',capture_id:'2122232425262728292a2b2c2d2e2f30',
  seq:'9007199254740993',generation:'17',document_id:'123',ticket:'22',width:1,height:1,presentation_width:1,presentation_height:1,
  domain:'proxy-output',quality:'proxy-float-output',profile:'working-srgb'};
function golden(){const text=readFileSync(new URL('../../docs/protocols/color-capture-v1.hex',import.meta.url),'utf8').trim();
  return Uint8Array.from(text.match(/../g)!.map(x=>parseInt(x,16))).buffer;}
test('golden identified frame retains u64 precision and exact pixels',()=>{
  const result=parseCaptureFrame(golden(),descriptor);
  assert.equal(result.descriptor.seq,'9007199254740993');assert.deepEqual([...result.rgba],[10,20,30,255]);
});
test('each identity and geometry field must match, not only sequence',()=>{
  for(const field of ['epoch','shm_instance','capture_id','seq','generation','document_id','ticket'] as const)
    assert.throws(()=>parseCaptureFrame(golden(),{...descriptor,[field]:'0'}));
  for(const field of ['width','height','presentation_width','presentation_height'] as const)
    assert.throws(()=>parseCaptureFrame(golden(),{...descriptor,[field]:2}));
});
test('wrong header, reserved data, truncated pixels and trailing bytes are rejected',()=>{
  for(const index of [0,4,6,112]){const b=golden();new Uint8Array(b)[index]^=1;assert.throws(()=>parseCaptureFrame(b,descriptor));}
  assert.throws(()=>parseCaptureFrame(golden().slice(0,131),descriptor));
  const extra=new Uint8Array(133);extra.set(new Uint8Array(golden()));assert.throws(()=>parseCaptureFrame(extra.buffer,descriptor));
});
