// UNRUN: source fixtures only, pending authorized local runner.
import {describe,it,expect} from 'vitest';
import {checked,neutral,wheelAt} from './model';
describe('colour grading recipe',()=>{
  it('preserves independent global wheel and all tonal controls',()=>{const r=neutral();r.global.saturation=40;r.balance=75;expect(checked(r)).toEqual(r);expect(r.shadows.saturation).toBe(0);});
  it('wheel radius is saturation and center retains hue',()=>{expect(wheelAt(1,0,neutral().global).saturation).toBe(100);expect(wheelAt(0,0,{hue:240,saturation:40,luminance:0})).toEqual({hue:240,saturation:0,luminance:0});});
  it('rejects malformed values without silent clamp',()=>{expect(()=>checked({...neutral(),balance:101})).toThrow();expect(()=>checked({...neutral(),blending:NaN})).toThrow();});
});
