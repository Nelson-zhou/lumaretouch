// UNRUN: runner requires the separately authorized local validation pass.
import {describe,it,expect} from 'vitest';
import {PATTERNS,check,neutral,patches,OP} from './model';
describe('iris makeup portable intent',()=>{
 it('has 11 distinct original names',()=>expect(new Set(PATTERNS.map(p=>p[0])).size).toBe(11));
 it('does not transfer anatomy or invent official controls',()=>{for(const key of ['pupil','left','colour','size'])expect(()=>check({...neutral(),[key]:1})).toThrow();});
 it('uses canonical parameter patches',()=>expect(patches(neutral()).every(p=>p.operation_id===OP)).toBe(true));
 it('rejects nonfinite strength',()=>expect(()=>check({...neutral(),strength:NaN})).toThrow());
});
