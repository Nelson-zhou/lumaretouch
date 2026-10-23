// UNRUN. Source fixture only, not a test report.
import {describe,it,expect} from 'vitest';
import {checked,neutral,primaries} from './model';
describe('primary calibration recipe',()=>{
 it('has six independent neutral controls',()=>{for(const k of primaries)expect(checked(neutral())[k]).toEqual({hue:0,saturation:0});});
 it('rejects unknown space and invalid values',()=>{
  const r=neutral();r.red.hue=NaN;expect(()=>checked(r)).toThrow();
  expect(()=>checked({...neutral(),working_space:'display-p3'} as never)).toThrow();
 });
 it('does not alias control objects',()=>{const r=neutral();r.red.hue=10;expect(r.blue.hue).toBe(0);});
});
