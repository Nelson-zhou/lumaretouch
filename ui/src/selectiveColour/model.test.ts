// Authored, UNRUN. Existing local Vitest harness can run after integration.
import {describe,it,expect} from 'vitest';
import {checked,neutral,ranges,requirements} from './model';
describe('selective colour strict recipe',()=>{
 it('keeps all nine families independent',()=>{const r=neutral();r.ranges.reds.cyan=20;expect(r.ranges.yellows.cyan).toBe(0);expect(checked(r)).toEqual(r);expect(ranges).toHaveLength(9);expect(Object.keys(requirements)).toHaveLength(16);});
 it('rejects unknown fields and nonfinite amounts',()=>{expect(()=>checked({...neutral(),extra:true} as never)).toThrow();const r=neutral();r.ranges.blacks.black=NaN;expect(()=>checked(r)).toThrow();});
 it('has independent mode and channel amounts',()=>{const r=neutral();r.method='absolute';r.ranges.neutrals.yellow=-35;expect(checked(r).method).toBe('absolute');expect(checked(r).ranges.neutrals.yellow).toBe(-35);});
});
