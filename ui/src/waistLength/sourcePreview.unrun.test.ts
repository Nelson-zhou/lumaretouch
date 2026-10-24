// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. Source mapping fixtures are not runtime or visual acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {matchesSource,previewImage,sourceViewport,type SourcePreview} from './sourcePreview.ts';
const preview=():SourcePreview=>({mime:'image/png',base64:'fixture-only-not-rendered',source_sha256:'a'.repeat(64),source_width:800,source_height:1200,decoded_width:800,decoded_height:1200,width:800,height:1200,mapping:'normalized_full_frame',orientation:'exif_normalized_once'});
test('only matching whole-source hash/size/orientation is reviewable; no cropped or edited proxy',()=>{
 const source=previewImage(preview());assert.ok(source);assert.equal(matchesSource(source,source.source),true);
 assert.equal(matchesSource(source,{...source.source,sha256:'b'.repeat(64)}),false);assert.equal(matchesSource(source,{...source.source,width:801}),false);assert.equal(matchesSource(null,source.source),false);
 assert.equal(previewImage({...preview(),mapping:'cropped_proxy'} as never),null);assert.equal(previewImage({...preview(),orientation:'unknown'} as never),null);
 assert.equal(previewImage({...preview(),width:799}),null);assert.equal(previewImage({...preview(),source_sha256:'guess'}),null);
});
test('source pixel-centre viewport maps decoded full-frame edges rather than nominal source edges',()=>{
 const direct=previewImage(preview());assert.ok(direct);assert.equal(sourceViewport(direct),'-0.5 -0.5 800 1200');
 const aligned=previewImage({...preview(),source_width:1600,source_height:2400,decoded_width:800,decoded_height:1200});assert.ok(aligned);
 const sx=1599/799,sy=2399/1199;assert.equal(sourceViewport(aligned),`${-.5*sx} ${-.5*sy} ${800*sx} ${1200*sy}`);
 assert.equal(previewImage({...preview(),source_width:1600,source_height:2400,decoded_width:801,decoded_height:1200,width:801}),null);
});
