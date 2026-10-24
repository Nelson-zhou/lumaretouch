// AUTHORED / UNRUN. No network, app, model or test execution during authoring.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fetchCollarboneImage,type CollarboneImageTransport,type CollarboneImageReply} from './visualTransport';
const base64='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jGq0AAAAASUVORK5CYII=';
async function fixture(){
 const bytes=Uint8Array.from(atob(base64),x=>x.charCodeAt(0));
 const sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
 const request={preflightToken:'a'.repeat(32),documentId:'b'.repeat(32),revision:'1',side:'before' as const,sha256,requestId:'read-image-1'};
 const image={mime:'image/png' as const,width:1,height:1,sha256,base64};
 const reply:CollarboneImageReply={request_id:request.requestId,action:'collarbone_visual',success:true,preflight_token:request.preflightToken,document_id:request.documentId,revision:request.revision,side:request.side,sha256,image};
 const calls:unknown[]=[];const api:CollarboneImageTransport={request:async r=>{calls.push(r);return {requested:true};},read:async id=>({phase:'done',request_id:id,result:reply})};
 const {base64:_,...expected}=image;return {request,image,reply,api,expected,calls};
}
test('read-only page accepts only actual bytes with exact frozen identity and dimensions',async()=>{
 const {api,request,expected,image,calls}=await fixture();assert.deepEqual(await fetchCollarboneImage(api,request,expected),image);assert.equal(calls.length,1);
});
test('wrong token document revision side hash or read request is rejected',async()=>{
 for(const field of ['preflight_token','document_id','revision','side','sha256','request_id'] as const){const f=await fixture();(f.reply as any)[field]='wrong';await assert.rejects(fetchCollarboneImage(f.api,f.request,f.expected));}
});
test('bad bytes and unexpected dimensions never become displayed verified evidence',async()=>{
 for(const mutate of [(r:any)=>{r.image.base64='iVBORbad';},(r:any)=>{r.image.width=2;},(r:any)=>{r.outcome_unknown=true;},(r:any)=>{r.success=false;}]){const f=await fixture();mutate(f.reply);await assert.rejects(fetchCollarboneImage(f.api,f.request,f.expected));}
});
test('stale target cancellation cannot finish a read or mutate',async()=>{
 const f=await fixture();await assert.rejects(fetchCollarboneImage(f.api,f.request,f.expected,()=>false));assert.equal(f.calls.length,1);
});
