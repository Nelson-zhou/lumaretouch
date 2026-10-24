// AUTHORED / UNRUN. No application, imports, tests, network or model execution.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fetchDecorationImage,type DecorationImageReply,type DecorationImageTransport} from './visualTransport';
const base64='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jGq0AAAAASUVORK5CYII=';
async function fixture(preset=false){
 const bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0));const sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
 const request={...(preset?{id:'preset'}:{}),documentId:'doc',preflightToken:'a'.repeat(32),revision:'2',side:'before' as const,sha256,requestId:'read'};
 const image={mime:'image/png' as const,width:1,height:1,sha256,base64};
 const reply:DecorationImageReply={...(preset?{id:'preset',protocol:1,outcome_unknown:false}:{}),request_id:'read',action:'face_decoration_visual',success:true,document_id:'doc',preflight_token:request.preflightToken,revision:'2',side:'before',sha256,image};
 let calls=0;const api:DecorationImageTransport={request:async()=>{calls++;return {requested:true};},read:async request_id=>({phase:'done',request_id,result:reply})};
 const {base64:_,...expected}=image;return {api,request,reply,expected,image,calls:()=>calls};
}
test('one immutable image page verifies actual PNG bytes, dimensions and full correlation',async()=>{
 for(const preset of [false,true]){const f=await fixture(preset);assert.deepEqual(await fetchDecorationImage(f.api,f.request,f.expected,()=>true),f.image);assert.equal(f.calls(),1);}
});
test('wrong token, id, side, source document, revision or malformed bytes cannot authorize display',async()=>{
 for(const field of ['preflight_token','id','side','document_id','revision','sha256','request_id']){const f=await fixture(true);(f.reply as any)[field]='wrong';await assert.rejects(fetchDecorationImage(f.api,f.request,f.expected,()=>true));}
 for(const mutate of [(r:any)=>{r.image.base64='iVBORbad';},(r:any)=>{r.image.width=2;},(r:any)=>{r.outcome_unknown=true;},(r:any)=>{delete r.protocol;}]){const f=await fixture(true);mutate(f.reply);await assert.rejects(fetchDecorationImage(f.api,f.request,f.expected,()=>true));}
});
test('navigation cancels publication but does not claim the underlying read stopped',async()=>{
 const f=await fixture();await assert.rejects(fetchDecorationImage(f.api,f.request,f.expected,()=>false));assert.equal(f.calls(),1);
});
