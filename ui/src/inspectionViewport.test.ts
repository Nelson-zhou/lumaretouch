import {test} from 'node:test';
import assert from 'node:assert/strict';
import {inspectionLayout} from './inspectionViewport.ts';
for(const dpr of [1,1.25,2])test(`source 1:1 aligns absolute device pixels at DPR ${dpr}`,()=>{
  const box={left:11.3,top:7.7,width:800,height:600};
  const l=inspectionLayout(box,6000,4000,{zoom:1,x:13.2,y:-8.7},dpr,true)!;
  assert.ok(Math.abs(l.rect.width*dpr-6000)<1e-9);
  assert.ok(Math.abs(l.rect.height*dpr-4000)<1e-9);
  assert.ok(Math.abs((box.left+l.rect.left)*dpr-Math.round((box.left+l.rect.left)*dpr))<1e-9);
  assert.ok(l.roi && l.patch);
  assert.ok(l.roi.width<=Math.ceil(box.width*dpr)+1);
  assert.ok(l.roi.height<=Math.ceil(box.height*dpr)+1);
  assert.ok(Math.abs(l.patch.width*dpr-l.roi.width)<1e-9);
});
test('small source and offscreen viewport do not allocate imaginary pixels',()=>{
  const box={left:0,top:0,width:800,height:600};
  assert.deepEqual(inspectionLayout(box,96,64,{zoom:1,x:0,y:0},1,true)!.roi,{x:0,y:0,width:96,height:64});
  assert.equal(inspectionLayout(box,96,64,{zoom:1,x:10000,y:0},1,true)!.roi,null);
});
test('cropped/rotated full output aspect is independent from proxy dimensions',()=>{
  const l=inspectionLayout({left:0,top:0,width:800,height:600},1000,3000,{zoom:1,x:0,y:0},2,true)!;
  assert.equal(l.rect.width,500);assert.equal(l.rect.height,1500);
});
test('invalid dimensions never produce a request',()=>{
  for(const width of [0,-1,NaN,Infinity,2.5,0x100000000])assert.equal(inspectionLayout({left:0,top:0,width:800,height:600},width,100,{zoom:1,x:0,y:0},1,true),null);
});
