// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. Not acceptance evidence.
import {describe,it,expect} from 'vitest';
import {adjust,check,neutral,IDS,OPERATION_ID} from './model';
describe('original longitudinal recipe contract',()=>{
 it('overall atomically sets only two components',()=>{expect(adjust({version:1,thigh:.1,calf:.7},'overall',.4)).toEqual({version:1,thigh:.4,calf:.4});});
 it('segment edit preserves the other segment',()=>{expect(adjust({version:1,thigh:.1,calf:.7},'thigh',.4).calf).toBe(.7);});
 it('neutral is exact and negative/NaN rejected',()=>{expect(neutral()).toEqual({version:1,thigh:0,calf:0});expect(()=>check({version:1,thigh:-1,calf:0})).toThrow();expect(()=>check({version:1,thigh:NaN,calf:0})).toThrow();});
 it('does not alias width identity',()=>{expect(OPERATION_ID).toBe('lnx.leg_length.v1');expect(IDS.overall).toBe('LNX-REF-PC-32473-C-d79658697a');});
});
