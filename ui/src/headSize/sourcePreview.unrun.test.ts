// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. Metadata fixtures never claim photographic/UI acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {matchesSource,previewImage,sourceViewport,type SourcePreview} from './sourcePreview.ts';
const preview=():SourcePreview=>({mime:'image/png',base64:'fixture-only-not-a-real-image',source_sha256:'a'.repeat(64),source_width:800,source_height:1200,decoded_width:800,decoded_height:1200,width:800,height:1200,mapping:'normalized_full_frame',orientation:'exif_normalized_once'});
test('only canonical normalized full-frame source mapping is acceptable',()=>{
 const result=previewImage(preview());assert.ok(result);assert.equal(result.displayWidth,800);assert.equal(result.source.width,800);assert.equal(sourceViewport(result),'-0.5 -0.5 800 1200');
 assert.equal(matchesSource(result,result.source),true);assert.equal(matchesSource(result,{...result.source,sha256:'b'.repeat(64)}),false);
 for(const patch of [{mapping:'crop'},{orientation:'raw'},{source_sha256:'invalid'},{width:400},{decoded_width:1600},{height:0},{source_width:NaN}])assert.equal(previewImage({...preview(),...patch} as SourcePreview),null);
});
test('thumbnail dimensions remain distinct from original pixel coordinates',()=>{
 const result=previewImage({...preview(),source_width:1600,source_height:2400,decoded_width:1600,decoded_height:2400,width:853,height:1280});
 assert.ok(result);assert.equal(result.source.width,1600);assert.equal(result.displayWidth,853);assert.equal(sourceViewport(result),'-0.5 -0.5 1600 2400');
});
