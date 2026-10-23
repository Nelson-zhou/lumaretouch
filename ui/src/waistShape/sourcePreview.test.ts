// SPDX-License-Identifier: GPL-3.0-or-later
// Authored UNRUN; metadata/coordinate fixtures are not actual source pixels.
import test from 'node:test';
import assert from 'node:assert/strict';
import {previewImage,matchesSource,sourceViewport,type SourcePreview} from './sourcePreview.ts';
const source:SourcePreview={mime:'image/png',base64:'fixture',source_sha256:'a'.repeat(64),source_width:4000,source_height:3000,decoded_width:2048,decoded_height:1536,width:1280,height:960,mapping:'normalized_full_frame',orientation:'exif_normalized_once'};
test('thumbnail retains original, decoded and actual display dimensions separately',()=>{
 const image=previewImage(source);assert.ok(image);
 assert.equal(image.source.width,4000);assert.equal(image.decodedWidth,2048);assert.equal(image.displayWidth,1280);
 assert.equal(matchesSource(image,{...image.source,sha256:'b'.repeat(64)}),false);
 assert.equal('canonical_original' in image,false);
});
test('unproven crop, enlarging decode and missing mapping are refused',()=>{
 assert.equal(previewImage({...source,decoded_width:1600}),null);
 assert.equal(previewImage({...source,height:800}),null);
 assert.equal(previewImage({...source,decoded_width:4008}),null);
 assert.equal(previewImage({...source,mapping:'cropped'} as unknown as SourcePreview),null);
});
test('source pixel-centre coordinates match whole decoded pixel-edge image extent',()=>{
 const image=previewImage(source);assert.ok(image);
 const [x,y,w,h]=sourceViewport(image).split(' ').map(Number);
 for(const n of [0,.25,.5,.75,1]){
  assert.ok(Math.abs((n*(image.source.width-1)-x)/w-(n*(image.decodedWidth-1)+.5)/image.decodedWidth)<1e-12);
  assert.ok(Math.abs((n*(image.source.height-1)-y)/h-(n*(image.decodedHeight-1)+.5)/image.decodedHeight)<1e-12);
 }
});
