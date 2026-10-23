// AUTHORED UNRUN. Do not execute except in authorized local QA.
import {describe,it,expect} from 'vitest';
import {check,neutral,receipt,Request} from './model';
describe('photo detail typed protocol',()=>{
 it('rejects aliases and unsupported ranges',()=>{expect(()=>check({...neutral(),texture:10})).toThrow();expect(()=>check({...neutral(),sharpen_radius:0})).toThrow();expect(()=>check({...neutral(),luma_detail:NaN})).toThrow();});
 it('matches exact receipt identity and recipe',()=>{const r:Request={cmd:'photo_detail',request_id:'r',document_id:'d',revision:1,action:'set',spec:{...neutral(),luma_amount:70}};const a={event:'photo_detail_result',protocol:1,request_id:'r',document_id:'d',success:true,outcome_unknown:false,requires_reload:false,spec:r.spec};expect(receipt(a,r).success).toBe(true);expect(()=>receipt({...a,document_id:'other'},r)).toThrow();expect(()=>receipt({...a,spec:neutral()},r)).toThrow();});
});
