// AUTHORED UNRUN. Test execution belongs to local QA owner.
import {describe,it,expect} from 'vitest';
import {check,neutral,receipt,Request} from './model';
describe('extended tone protocol',()=>{
  it('rejects aliases and out-of-range parameters',()=>{expect(()=>check({...neutral(),exposure:1})).toThrow();expect(()=>check({...neutral(),whites:101})).toThrow();});
  it('requires exact post-commit recipe and identities',()=>{const r:Request={cmd:'extended_tone',request_id:'a',document_id:'d',revision:0,action:'set',spec:{...neutral(),texture:10}};const result={event:'extended_tone_result',protocol:1,request_id:'a',document_id:'d',success:true,outcome_unknown:false,requires_reload:false,spec:r.spec};expect(receipt(result,r).success).toBe(true);expect(()=>receipt({...result,document_id:'other'},r)).toThrow();expect(()=>receipt({...result,spec:neutral()},r)).toThrow();});
});
