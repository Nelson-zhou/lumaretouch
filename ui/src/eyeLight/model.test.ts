// UNRUN fixtures, not typecheck or integration evidence.
import {describe,it,expect} from 'vitest';
import {check,neutral,degrees,patchEye,setLinked} from './model';
describe('independent and atomically linked eye-light recipe',()=>{
 it('preserves baseline rotation endpoints',()=>{expect(degrees(-100)).toBe(-180);expect(degrees(100)).toBe(180);});
 it('starts inactive on both sides',()=>{expect(check(neutral()).left.strength).toBe(0);expect(check(neutral()).right.strength).toBe(0);});
 it('rejects identity in preset',()=>expect(()=>check({...neutral(),personId:'other'})).toThrow());
 it('updates linked eyes atomically',()=>{const r=patchEye(neutral(),'left',{strength:50,horizontal:20});expect(r.left).toEqual(r.right);});
 it('persists independent side transforms',()=>{let r=setLinked(neutral(),false,'left');r=patchEye(r,'left',{strength:40,rotation:30});r=patchEye(r,'right',{strength:60,rotation:-25,flip:true});expect(r.left.rotation).toBe(30);expect(r.right.rotation).toBe(-25);expect(r.left.flip).toBe(false);});
 it('linking uses explicitly selected reference side',()=>{let r=patchEye(setLinked(neutral(),false,'left'),'right',{strength:70});r=setLinked(r,true,'right');expect(r.left.strength).toBe(70);expect(r.right.strength).toBe(70);});
 it('rejects nonfinite positions',()=>expect(()=>patchEye(neutral(),'left',{horizontal:NaN})).toThrow());
});
