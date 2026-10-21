import {test} from 'node:test';
import assert from 'node:assert/strict';
import {composition,sameDisplay,frameAdmission,type DisplayGeometry} from './previewComposition.ts';
const edited:DisplayGeometry={rasterW:1200,rasterH:800,width:4000,height:4000,documentId:'1',geometry:'5',kind:1,instance:'a'};
const original:DisplayGeometry={...edited,width:6000,height:4000,geometry:'6',kind:2};
test('ordinary display retains square composition despite a 3:2 proxy raster',()=>{
 const c=composition(edited,null,'single');assert.equal(c.width,1200);assert.equal(c.height,800);assert.equal(c.displayWidth/c.displayHeight,1);
});
test('split and wipe retain independent whole-image aspect ratios',()=>{
 for(const mode of ['split','swipe'] as const){const c=composition(edited,original,mode);
 assert.equal(c.edited.width/c.edited.height,1);assert.equal(c.original!.width/c.original!.height,1.5);assert.equal(c.compositionOnly,true);
 assert.ok(c.width<=4096&&c.height<=4096);}
});
test('same-sized other documents and other crop positions are not the displayed geometry',()=>{
 assert.equal(sameDisplay(edited,{...edited,documentId:'2'}),false);assert.equal(sameDisplay(edited,{...edited,geometry:'7'}),false);
 assert.equal(composition(edited,{...original,documentId:'2'},'swipe').original,null);
});


test('new consumers and changed geometry require full pixels; skipped/original captures never adopt',()=>{
 const frame={seq:1,seqId:'1',tEmitNs:0,tPullNs:0,w:1200,h:800,pixelLen:1200*4*100,y0:0,rows:100,headerBytes:128,
   pixels:new Uint8Array(1200*4*100),instance:'a',presentation:{documentId:'1',width:4000,height:4000,geometry:'5',kind:1 as const}};
 assert.equal(frameAdmission(null,frame,'single',false,false).recoverFull,true);
 assert.equal(frameAdmission(edited,frame,'single',false,false).usable,true);
 assert.equal(frameAdmission(null,frame,'single',false,true).recoverFull,false);
 assert.equal(frameAdmission(null,{...frame,pixelLen:0,rows:0},'single',false,false).usable,false);
 const full={...frame,pixelLen:1200*4*800,rows:800};
 assert.equal(frameAdmission(null,full,'single',false,false).usable,true);
 const originalFrame={...full,presentation:{...frame.presentation,kind:2 as const}};
 assert.equal(frameAdmission(null,originalFrame,'swipe',false,false).usable,false);
 assert.equal(frameAdmission(null,originalFrame,'single',false,false).usable,false);
 assert.equal(frameAdmission(null,originalFrame,'single',true,false).usable,true);
});
