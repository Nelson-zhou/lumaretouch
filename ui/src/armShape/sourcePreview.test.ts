// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED UNRUN. Mapping fixtures are not image, runtime, or visual acceptance.
import {describe,it} from 'node:test';
import assert from 'node:assert/strict';
import {armSourcePreview} from './sourcePreview.ts';
import type {SourcePreview} from '../legShape/sourcePreview.ts';
const source:SourcePreview={mime:'image/png',base64:'cG5n',source_sha256:'a'.repeat(64),source_width:640,source_height:480,decoded_width:640,decoded_height:480,width:640,height:480,mapping:'normalized_full_frame',orientation:'exif_normalized_once'};
describe('arm canonical-source preview adapter',()=>{
 it('retains whole source identity and pixel-center mapping',()=>{const preview=armSourcePreview(source);assert.ok(preview);assert.equal(preview.domain,'canonical-source');assert.equal(preview.source_sha256,source.source_sha256);assert.equal(preview.width,640);assert.equal(preview.displayWidth,640);assert.equal(preview.viewport,'-0.5 -0.5 640 480');});
 it('does not accept missing, edited, cropped, or impossible mapping metadata',()=>{assert.equal(armSourcePreview(null),null);assert.equal(armSourcePreview({...source,mapping:'edited-preview'} as unknown as SourcePreview),null);assert.equal(armSourcePreview({...source,width:639}),null);assert.equal(armSourcePreview({...source,source_sha256:'wrong'}),null);});
});
